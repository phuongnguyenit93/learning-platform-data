# Key identifier: Định danh khóa trong hệ thống kiểm kê và quản lý vòng đời

Một nền tảng có nhiều dịch vụ Java, hàng trăm tenant và hàng chục nghìn khóa dùng cho AES-GCM, HMAC, RSA, Ed25519 và envelope encryption. Khi cần giải mã một bản ghi từ ba năm trước, hệ thống phải biết **chính xác khóa nào đã được dùng**, phiên bản nào còn khả năng giải mã, ai được phép gọi KMS/HSM, và liệu khóa đã bị xoay vòng hoặc ngừng hoạt động. Nếu chỉ lưu chuỗi như **main-key**, **default** hoặc **customer-key**, ứng dụng rất dễ chọn nhầm khóa khi một alias được thay đổi.

**Key identifier (định danh khóa)** là một giá trị dùng để **nhận diện và tham chiếu một đối tượng khóa trong một phạm vi được quy định rõ**. Key identifier không phải chính **key material** và không tự tạo ra quyền sử dụng khóa. Nó cần được kết hợp với **namespace, phiên bản, metadata, trạng thái vòng đời và chính sách truy cập** để một hệ thống kiểm kê khóa (*key inventory*) giải quyết chính xác câu hỏi: *khóa nào, của ai, dùng cho mục đích gì, đang ở trạng thái nào và được phép dùng trong thao tác nào?*

Trong chương **Key inventory** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, key identifier là cầu nối giữa các kỹ thuật mật mã đối xứng/bất đối xứng, chữ ký số, HMAC, KMS/HSM và envelope encryption với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Định danh đúng làm cho hệ thống có khả năng kiểm toán và phục hồi; định danh sai có thể dẫn tới sai khóa, lộ dữ liệu giữa tenant hoặc mất khả năng giải mã dữ liệu lịch sử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **key identifier** và phân biệt nó với **key material**, **key alias**, **key version**, **key handle**, **public-key fingerprint** và **certificate identifier**.
2. Xác định yêu cầu về **scope, tính duy nhất, tính ổn định, không tái sử dụng và khả năng truy vết** khi thiết kế định danh khóa.
3. Thiết kế một bản ghi **key inventory** liên kết key ID với owner, tenant, purpose, algorithm, state, provider và chính sách.
4. Dùng key ID/version trong **envelope encryption**, **AES-GCM AAD**, **JWKS/JWS**, **KMS/HSM** mà không nhầm metadata với bằng chứng tin cậy.
5. Đề xuất cách tìm đúng phiên bản khóa lịch sử, xoay vòng và ngừng sử dụng khóa cũ mà không làm hỏng khả năng phục hồi dữ liệu.
6. Viết ví dụ Java 17 kiểm tra **key reference, tenant, purpose, state** khi chọn khóa để mã hóa/giải mã.
7. Nhận diện rủi ro **key confusion, alias drift, cross-tenant lookup, thuật toán bị hạ cấp, ID collision và metadata giả mạo**.

## 2. Key identifier đại diện cho cái gì?

Một key identifier có thể nhận diện **một đối tượng khóa cụ thể**, **một phiên bản khóa**, hoặc **một thực thể logic chứa nhiều phiên bản**, tùy hợp đồng của hệ thống. Trước khi chọn định dạng chuỗi, phải chốt ý nghĩa của nó.

Ví dụ có hai mô hình hợp lệ:

~~~text
Mô hình A - ID vật liệu khóa bất biến:
  keyId = 8fa2...e7b1  -> key material v1
  keyId = 4ac6...1f90  -> key material v2
  alias = billing-current -> trỏ keyId v2

Mô hình B - ID logic + version:
  keyId = billing-signing-key
    version = 1 -> material v1
    version = 2 -> material v2
  alias = billing-current -> (keyId, version=2)
~~~

Cả hai đều có thể an toàn nếu **mỗi tham chiếu tới key material được giải nghĩa không nhập nhằng**, có registry đáng tin và có chính sách version. Nhưng **không được trộn hai mô hình**: nếu một nhà cung cấp sinh key ID mới cho mỗi lần rotate, không được giả định rằng tăng trường version là đủ để tìm private key cũ.

### 2.1. Phân biệt các thuật ngữ

| Thuật ngữ | Bản chất | Có phải key material? | Lưu ý |
|---|---|---|---|
| **Key identifier (key ID)** | Giá trị nhận diện key object/slot trong một scope | **Không** | Phải có quy tắc uniqueness và lookup |
| **Key version** | Phiên bản cụ thể của key material hoặc key record | Không | Quan trọng để đọc ciphertext/chữ ký lịch sử |
| **Key alias** | Tên thuận tiện, có thể chuyển tới key ID/version khác | Không | **Không nên dựa vào alias động để giải mã lịch sử** |
| **Key reference** | Tham chiếu đầy đủ có thể bao gồm namespace + key ID + version | Không | Có thể là URI, handle, resource path hoặc cấu trúc có trường |
| **Key handle** | Token/đối tượng provider dùng để thao tác với khóa | Không nhất thiết; có thể là opaque reference | Không đảm bảo portable hoặc dùng ngoài provider |
| **Key material** | SecretKey, private key, public key hoặc byte bí mật cấu thành khóa | **Có** | Bảo vệ theo độ nhạy và purpose |
| **Public-key fingerprint/thumbprint** | Digest/cấu trúc tính từ biểu diễn public key | Không phải khóa | Có thể giúp so khớp, **không tự xác lập trust** |
| **Certificate serial/SKI/AKI** | Các trường liên quan chứng thư, public key và issuer | Không | Có phạm vi và quy tắc riêng trong PKI |
| **Key owner/tenant** | Chủ thể chịu trách nhiệm/miền dữ liệu | Không | Không phải chuỗi ID tự động được ủy quyền |
| **Key state** | Active, suspended, deactivated, destroyed... | Không | Quyết định phép toán có được phép theo policy |

Không gọi một chuỗi **KeyId** được trả từ KMS là “khóa AES”. Nó thường chỉ là **metadata hoặc resource reference**; thực hiện được Encrypt/Decrypt/Sign hay không còn phụ thuộc **key type, key purpose, policy, IAM và trạng thái**.

### 2.2. Key ID, alias và version trong một truy vấn

~~~mermaid
flowchart TD
    R["Request kèm key reference"] --> V["Xác thực principal và tenant"]
    V --> L["Tra key registry trong namespace được phép"]
    L --> K["Resolve keyId + version chính xác"]
    K --> S["Kiểm tra state, purpose, algorithm và IAM"]
    S --> P["Lấy provider key handle / KMS resource ID"]
    P --> O["Thực hiện crypto operation theo policy"]
    A["Alias: current-encryption"] --> B["Chỉ dùng cho lựa chọn khóa mới"]
    B --> L
    H["Ciphertext lịch sử ghi v3"] --> K
~~~

Khi **mã hóa dữ liệu mới**, ứng dụng có thể dùng alias đáng tin **current-encryption** để lấy phiên bản hiện tại và sau đó **ghi key reference thực tế đã sử dụng**. Khi **giải mã dữ liệu cũ**, ứng dụng nên resolve đúng key version đã gắn với ciphertext, không tự chọn alias hiện tại.

**Một alias không phải cơ chế authorization.** Nếu attacker có quyền sửa alias và đẩy nó tới khóa do họ kiểm soát, dữ liệu mới có thể bị mã hóa sai nơi nhận hoặc một quy trình ký có thể chọn nhầm danh tính. Thay đổi alias cần được kiểm soát và audit.

## 3. Những thuộc tính cần có của một key identifier

### 3.1. Tính duy nhất phải được định nghĩa trong một phạm vi

Câu hỏi không chỉ là **“ID có duy nhất không?”** mà phải là **“duy nhất ở đâu và trong bao lâu?”**

| Phạm vi | Ví dụ | Yêu cầu |
|---|---|---|
| Trong một **provider/account/region** | ID do KMS cung cấp | Không được giả định duy nhất toàn cầu nếu provider không cam kết |
| Trong một **tenant** | tenant-42 / customer-data | Không cho phép tham chiếu chéo tenant do namespace mơ hồ |
| Trong một **application/environment** | prod / billing / signing | Không để test key bị resolve thành prod key |
| Trong một **key family** | billing-sign + version | Không cho hai material khác nhau dùng cùng key ID/version |
| Trong **toàn bộ inventory doanh nghiệp** | internal opaque ID / UUID | Cần index/constraint, quy tắc import và đồng bộ nhiều provider |

Khi tích hợp nhiều KMS/HSM, hệ thống có thể xây **key reference có namespace**:

~~~text
keyRef = {
    provider: "enterprise-kms-a",
    accountOrPartition: "prod-main",
    location: "region-1",
    keyId: "b8e2df83-4efe-4eb9-8ed2-f76a7c0b534e",
    version: "v3"
}
~~~

Đây là cấu trúc ví dụ, không phải schema của một nhà cung cấp cụ thể. Không đặt định dạng tùy ý này vào API provider nếu provider không hỗ trợ; tại boundary ứng dụng, hãy **map** sang resource identifier và version theo hợp đồng.

### 3.2. Tính ổn định và không tái sử dụng

Một ID được lưu trong hàng triệu bản ghi ciphertext cần **giữ ý nghĩa ổn định** trong suốt thời gian các bản ghi đó tồn tại. Sau khi hủy khóa, nên có **tombstone/record lưu vết** để ID không bị tái sử dụng cho material mới, phù hợp chính sách lưu trữ và tránh định danh cũ trỏ nhầm.

Không nên:

~~~text
2025: keyId = "customer-key-01" -> DEK cũ
2026: DEK cũ bị hủy
2026: keyId = "customer-key-01" -> DEK mới không liên quan
~~~

Nếu ciphertext năm 2025 còn ghi **customer-key-01**, ứng dụng có thể chọn nhầm DEK mới. Ngay cả khi AES-GCM xác minh tag thất bại, dịch vụ vẫn gây downtime và audit sai; với hệ thống/giao thức thiếu kiểm tra xác thực, hậu quả có thể nghiêm trọng hơn.

Hãy dùng **ID không tái sử dụng** và version/key record bất biến. Sự kiện hủy khóa không nhất thiết đồng nghĩa xóa mọi metadata của inventory; thông tin tham chiếu thường cần phục vụ audit, điều tra và chứng minh lifecycle.

### 3.3. Tính opaque, độ dài và khả năng dự đoán

Key ID **không cần bí mật** và không nhất thiết phải khó đoán như token đăng nhập. UUID hoặc chuỗi opaque do KMS cấp là lựa chọn thuận tiện khi cần tránh trùng và lộ ngữ nghĩa. ID dự đoán được như **key-000001** không tự làm lộ AES key, **nếu mọi thao tác đều được xác thực và phân quyền đúng**.

Tuy nhiên ID có thể gây **rò metadata** nếu chứa email, mã khách hàng, ID hợp đồng, tên môi trường hoặc thông tin tổ chức. Khi public-facing, cân nhắc opaque ID thay cho chuỗi mang PII. Không sử dụng **key ID như bearer token**, mật khẩu, API key hoặc chứng cứ sở hữu khóa.

### 3.4. Chuẩn hóa và bảo vệ lookup

- Định nghĩa **case sensitivity**, Unicode, ký tự hợp lệ, giới hạn độ dài và định dạng version.
- Tránh **string concatenation mơ hồ**, ví dụ ghép tenant + ":" + keyId khi giá trị có thể chứa dấu phân cách.
- Ưu tiên **các trường typed tách biệt** hoặc mã hóa có prefix độ dài khi đưa vào cấu trúc ký/AAD.
- Dùng **unique constraint** theo namespace và key material identity; xử lý race khi import/rotate.
- Không sử dụng input key ID không kiểm tra để tạo đường dẫn tệp, truy vấn SQL động hoặc gọi URL tùy ý.
- Với key ID do client gửi, tra cứu trong **registry được phép**, không tự chuyển nó thành quyền dùng khóa.

## 4. Bản ghi Key inventory nên gồm những trường nào?

Một inventory hữu ích không chỉ là danh sách ID, mà là **sổ đăng ký key object, key usage và lifecycle state**.

| Nhóm | Trường đề xuất | Mục đích |
|---|---|---|
| **Identity** | inventoryId, providerKeyId, keyVersion, namespace | Phân biệt các khóa/version, tìm đúng resource |
| **Ownership** | owner, tenantId, application, environment | Xác định miền quản trị và phạm vi dữ liệu |
| **Crypto type** | symmetric/asymmetric/HMAC, algorithm, size/curve | Ngăn chọn sai thuật toán/loại khóa |
| **Purpose** | Encrypt, Decrypt, Wrap, Unwrap, Sign, Verify, MAC, Derive | Kiểm tra key usage hợp lệ |
| **Provider** | KMS/HSM name, partition/account, region, key handle | Locate key mà không cần lưu raw material |
| **Lifecycle** | state, createdAt, activatedAt, retiredAt, destruction schedule | Theo dõi chuyển trạng thái và cryptoperiod |
| **Rotation** | parent key family, previous/next version, rotation policy | Duy trì luồng migrate và khả năng đọc lịch sử |
| **Access policy** | policy reference/version, IAM scope, allowed principals | Phân biệt identity với authorization |
| **Audit** | creator, reviewer, lastUsedAt, lastOperation, incident reference | Truy vết và điều tra |
| **Dependencies** | data sets, services, encrypted DEKs, certificates/JWKS | Xác minh an toàn trước khi deactivate/destroy |

Một inventory **không được chứa plaintext DEK/private key chỉ vì cần “đủ thông tin”**. Inventory giữ **metadata và references**, còn key material được bảo vệ trong KMS/HSM hoặc kho khóa có chính sách phù hợp.

### 4.1. Ví dụ record minh họa

~~~json
{
  "inventoryId": "inv-key-8f3c",
  "namespace": "production/customer-data",
  "provider": "enterprise-kms-a",
  "providerKeyId": "b8e2df83-4efe-4eb9-8ed2-f76a7c0b534e",
  "keyVersion": "v3",
  "tenantId": "tenant-42",
  "owner": "customer-data-service",
  "purpose": ["ENCRYPT", "DECRYPT"],
  "algorithm": "AES-256-GCM",
  "lifecycleState": "ACTIVE",
  "createdAt": "2026-01-10T10:00:00Z",
  "policyRef": "policy/customer-tenant-keys/v4",
  "rotationGroup": "tenant-42/customer-records",
  "previousVersion": "v2",
  "keyMaterial": "NOT_STORED_IN_INVENTORY"
}
~~~

Record trên chỉ là **schema đào tạo**. Trong thực tế, provider có thể không cho ứng dụng tự tạo mọi trường, và **một KMS KEK** thường có purpose/wrapping operation khác với **DEK AES-GCM**. **Không gắn thuật toán AES-GCM cho một resource chỉ vì ứng dụng dùng DEK được KMS bảo vệ**; cần phân biệt key material và operation tại từng lớp.

### 4.2. Kết nối với vòng đời khóa

~~~mermaid
flowchart TD
    A["Generate/Import key material"] --> B["Đăng ký keyId, version, owner và purpose"]
    B --> C["Provisioning + kiểm tra IAM/KMS"]
    C --> D["Activate đúng key reference"]
    D --> E["Operation log: keyId/version + principal + result"]
    E --> F["Rotate: version/keyId mới, chuyển alias nếu có"]
    F --> G["Giữ reference lịch sử cho Decrypt/Verify khi được phép"]
    G --> H["Deactivate/Disable/Revoke theo policy"]
    H --> I["Kiểm tra phụ thuộc, backup và restore"]
    I --> J["Destroy material khi đủ điều kiện"]
    J --> K["Giữ tombstone/audit metadata theo retention"]
~~~

**Sự kiện rotation không được ghi đè thông tin về material cũ.** Nếu key ID được cấp lại cho material khác trong khi ciphertext cũ còn tồn tại, hệ thống mất tính xác định của việc resolve lịch sử. Một inventory tốt cho phép trả lời **ciphertext hoặc chữ ký nào còn phụ thuộc key version cũ** trước khi xóa.

## 5. Key ID trong KMS, HSM, PKI và giao thức

Không phải mọi nơi đều dùng từ **key identifier** với cùng phạm vi.

### 5.1. KMS/HSM

Trong KMS có thể có **resource name/key ID, key version và alias**; HSM/PKCS#11 có thể dùng **slot/session, object handle, label và CKA_ID** theo provider. Các trường này phục vụ lookup theo cách khác nhau:

- **Resource ID/version:** dùng để xác định đối tượng hoặc phiên bản trong API của provider.
- **Alias:** tiện cho lựa chọn key hiện tại nhưng có thể đổi target.
- **Key handle:** có thể chỉ hợp lệ trong session/partition nhất định; không tự portable khi restart hoặc đổi HSM.
- **PKCS#11 CKA_ID/label:** là thuộc tính object theo ngữ nghĩa PKCS#11/provider; **không nên tự giả định luôn duy nhất toàn HSM** nếu chưa có kiểm soát namespace/unique constraint.

Khi ứng dụng có nhiều provider, cần một lớp **mapping có kiểm soát** từ **inventory key ID + version** tới resource reference chính xác. Không đưa **key ID do người gọi tự khai** thẳng vào API **Decrypt/Unwrap/Sign** mà bỏ qua tenant/purpose/IAM.

### 5.2. JWK/JWKS và JWS

Trong **JSON Web Key (JWK)**, trường **kid** (*key ID*) là gợi ý nhận diện khóa để bên nhận chọn đúng candidate trong bộ khóa. Trong **JWS/JWT**, **kid** trong header được dùng để tra khóa xác minh; nó **không phải chứng cứ rằng khóa được tin cậy**.

Ví dụ minh họa một JWKS:

~~~json
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "issuer-a-sign-v5",
      "x": "<BASE64URL_PUBLIC_KEY>"
    },
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "issuer-a-sign-v4",
      "x": "<BASE64URL_OLD_PUBLIC_KEY>"
    }
  ]
}
~~~

Các giá trị trong dấu ngoặc nhọn là **placeholder**, không phải public key thật. Một hệ thống Verify đúng phải:

1. Xác định **issuer/trust domain** đáng tin từ cấu hình/chính sách, không chỉ từ chuỗi kid.
2. Lấy JWKS từ **endpoint đã tin cậy** và bảo vệ đường truyền, cache, TTL và fail behavior.
3. Giới hạn **alg, kty, key usage, issuer, audience** theo policy; không để attacker tự chọn thuật toán hay URL khóa.
4. Dùng **kid trong phạm vi JWKS/issuer** chứ không giả định một kid duy nhất cho mọi tổ chức.
5. Khi rotate, công bố khóa mới trước khi bắt đầu ký mới và giữ public key cũ đủ lâu cho token/chữ ký còn hợp lệ, trừ khi có sự cố phải revoke.

**JWK thumbprint** tính từ biểu diễn public JWK theo quy tắc chuẩn có thể hỗ trợ định danh/so khớp; nhưng thumbprint chỉ chứng minh **tính nhất quán với bộ byte public key**, không tự chứng minh nó thuộc về issuer hợp pháp. Cũng không được cho JWS header điều khiển một URL tải JWKS tùy ý, dẫn đến SSRF hoặc tráo trust anchor.

### 5.3. Chứng thư X.509

Một chứng thư có thể được nhận diện theo **issuer + serial number**, và chứa **Subject Key Identifier (SKI)** hoặc **Authority Key Identifier (AKI)** để hỗ trợ xử lý khóa và xây chuỗi chứng thư. Các trường đó **không thể đánh đồng tùy tiện với providerKeyId của KMS**.

Ví dụ cùng một cặp public/private key có thể được dùng trong những chứng thư khác nhau theo điều kiện cấp chứng thư; certificate identifier và key-material identity là các quan hệ khác nhau. Một chứng thư bị thu hồi cũng không đồng nghĩa HSM đã hủy private key. Registry cần map các đối tượng này đúng phạm vi và thời gian sử dụng.

### 5.4. Định danh khóa bên gửi và bên nhận

Trong hệ thống mật mã bất đối xứng, nên tách **recipient encryption key ID** và **sender signing key ID**:

~~~text
Encrypted payload:
    recipientKeyRef -> public/private key dùng bảo vệ DEK
    payloadKeyRef   -> DEK/KEK tham chiếu nếu có

Signed payload:
    signerKeyRef    -> public/private signing key
    signatureAlg    -> Ed25519 / ECDSA / RSA-PSS tùy policy
~~~

Một key ID có tên **sign-v4** không nên bị hiểu là khóa giải mã chỉ vì cả hai cùng thuộc tenant-42. Cần **purpose** và **key type** được đăng ký, giới hạn trong KMS và kiểm tra khi gọi.

## 6. Key identifier không phải authorization hoặc nguồn tin cậy

**Biết một key ID không có nghĩa được phép Encrypt, Decrypt, Sign hay Unwrap.** Key ID thường là metadata không bí mật; kẻ tấn công có thể nhìn thấy nó trong envelope, JWT, audit hoặc file cấu hình. Nếu API chỉ cần keyId là thực hiện Decrypt, lỗi nằm ở **access control**, không phải ở độ dài chuỗi ID.

### 6.1. Thứ tự kiểm tra an toàn

~~~text
Authenticated principal
    |
    +--> Xác thực tenant/environment từ identity đáng tin
    |
    +--> Parse key reference, kiểm tra format và namespace
    |
    +--> Resolve ID/version bằng registry được kiểm soát
    |
    +--> Kiểm tra owner, tenant, purpose, algorithm và lifecycle state
    |
    +--> IAM/key policy cho operation cụ thể
    |
    +--> Gọi KMS/HSM hoặc crypto provider
    |
    +--> Audit actor, key reference, operation, outcome
~~~

**Key ID do input đưa vào chỉ là một đề nghị lookup, không phải lệnh cấp quyền.** Tầng ứng dụng phải đối chiếu với tenant/record đang được truy cập; tầng KMS/HSM phải tiếp tục thực thi policy theo principal và key reference phù hợp. Không phụ thuộc chỉ vào một lớp kiểm tra.

### 6.2. Key confusion và cross-tenant lookup

Một lỗi thiết kế:

~~~text
GET /api/decrypt?keyId=customer-key-v2

Client A gửi keyId của tenant B.
Service resolve keyId trong global map rồi dùng service-role có Decrypt mọi khóa.
=> Service trở thành confused deputy, giúp A giải mã dữ liệu của B.
~~~

Biện pháp: liên kết key reference với **tenant của authenticated principal**, loại dữ liệu, purpose, resource/record, IAM và encryption context nếu hỗ trợ. Quyền **Decrypt** ở KMS của một service role toàn hệ thống phải được hạn chế thêm bởi thiết kế tenant isolation hoặc phân đoạn key policy.

**Không dùng key ID được hash hoặc UUID khó đoán để thay quyền.** Khi ID bị lộ, cơ chế bảo mật vẫn phải đúng. Một số API phải che khả năng liệt kê key ID để tránh lộ metadata, nhưng đó là lớp bảo vệ bổ sung, không phải authorization.

### 6.3. Alias drift và algorithm confusion

- **Alias drift:** alias **primary** được đổi sang material mới, bản ghi cũ chỉ lưu alias và không thể resolve đúng khóa đã dùng.
- **Algorithm confusion:** hệ thống nhận trường **algorithm** từ input rồi chọn cách xử lý không kiểm tra key type/purpose, có thể chấp nhận thuật toán không được phép.
- **Namespace confusion:** cùng **kid=v1** tồn tại ở nhiều issuer; verifier dùng global key cache không ràng buộc issuer.
- **Key version mismatch:** ứng dụng đổi version trên metadata mà không đổi wrapped DEK/ciphertext/AAD tương ứng.
- **Provider mapping drift:** key ID nội bộ trỏ nhầm sang account/partition/region khác sau migration.

Kiểm soát các trường hợp này bằng **key registry tin cậy, typed reference, allowlist thuật toán, version bất biến, audit và kiểm thử migration**. Với các metadata có ý nghĩa bảo mật, cần xác định cơ chế **xác thực tính toàn vẹn** chứ không chỉ kiểm tra chúng có tồn tại.

### 6.4. Key ID có nên bị che khỏi log?

Key ID **thường không phải bí mật**, và ghi đúng ID/version có ích cho audit. Nhưng chuỗi ID có thể tiết lộ **tenant, môi trường, địa chỉ tài nguyên hoặc quan hệ đối tác**. Vì vậy:

- Chỉ log trong **audit channel có phân quyền** với principal, operation, key ID/version, result, correlation ID và thời điểm.
- Không log **raw DEK/KEK/private key, password, bearer token**, encrypted key export nhạy cảm hoặc plaintext khách hàng.
- Nếu cần log công khai, dùng **inventory reference nội bộ** không lộ PII hoặc giảm độ chi tiết theo policy.
- Không dùng một **hash(keyId)** như lời bảo đảm ẩn danh nếu keyId có không gian nhỏ/dễ đoán; nó vẫn có thể bị thử ngược bằng dictionary.

## 7. Key identifier trong envelope encryption và AES-GCM AAD

Trong **envelope encryption**, **DEK** mã hóa payload bằng AES-GCM; một **KEK** hoặc public-key wrapping mechanism bảo vệ DEK. Bản ghi lưu trữ thường cần cả **DEK/wrapping key reference** và các thông số mã hóa.

~~~mermaid
sequenceDiagram
    participant App as Java Service
    participant Reg as Key Registry
    participant KMS as KMS/HSM
    participant DB as Database
    App->>Reg: Lấy active key reference cho tenant/purpose
    Reg-->>App: keyId + version + algorithm + provider mapping
    App->>KMS: GenerateDataKey / WrapDEK với ref đã được cấp quyền
    KMS-->>App: DEK tạm + wrapped DEK / key metadata
    App->>App: AES-GCM Encrypt với nonce + AAD
    App->>DB: ciphertext+tag, nonce, wrapped DEK, keyId/version
    Note over Reg,KMS: Key version được rotate
    App->>DB: Đọc bản ghi cũ
    DB-->>App: envelope chứa ref version cũ
    App->>Reg: Resolve đúng keyId/version cũ, kiểm tra policy
    App->>KMS: Unwrap DEK với đúng key version
    KMS-->>App: DEK được cấp quyền
    App->>App: AES-GCM Verify tag rồi Decrypt
~~~

Một envelope minh họa:

~~~json
{
  "formatVersion": 1,
  "tenantId": "tenant-42",
  "recordId": "customer-123",
  "payloadAlgorithm": "AES-256-GCM",
  "wrappingKeyRef": {
    "namespace": "production/customer-data",
    "keyId": "kek-customer-42",
    "keyVersion": "v3"
  },
  "wrappedDek": "<BASE64_WRAPPED_DEK>",
  "nonce": "<BASE64_12_BYTE_NONCE>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_AND_TAG>"
}
~~~

**Tất cả chuỗi Base64 ở đây là placeholder**. Base64 chỉ là encoding, không phải encryption. Trong một hệ thống dùng DEK được dẫn xuất trực tiếp từ root secret thay vì wrapped DEK, phải lưu **KDF ID, root version, salt, info schema** phù hợp. Không giả định mọi envelope đều có cùng bộ trường.

### 7.1. Đưa key ID vào AAD để làm gì?

**AES-GCM** cung cấp authenticated encryption. **AAD (Additional Authenticated Data)** được xác thực cùng ciphertext nhưng không được mã hóa. Có thể ràng buộc các trường quan trọng như:

~~~text
AAD = EncodeCanonical(
    "customer-record-format-v1",
    tenantId,
    recordId,
    payloadAlgorithm,
    keyId,
    keyVersion
)
~~~

Nếu một bản ghi bị sửa keyId/version hoặc tenant/record ID, kiểm tra authentication tag có thể thất bại khi **AAD được tái tạo đúng**, giúp phát hiện tráo metadata. Tuy nhiên, có ba giới hạn quan trọng:

1. **AAD không xác thực caller:** tenantId phải được so với danh tính/quyền từ nguồn tin cậy, không đơn giản tin một trường do attacker đưa vào.
2. **AAD được xác thực sau khi có đúng DEK:** phần lookup key và quyết định KMS permission diễn ra trước tag verification nên phải có validation và IAM riêng.
3. **Rotation ảnh hưởng AAD:** nếu gắn wrapping key version vào AAD payload rồi rewrap DEK từ KEK-v3 sang KEK-v4, **chỉ sửa keyVersion sẽ làm tag sai**. Phải thiết kế ranh giới metadata wrapping và content AAD rõ: hoặc xác thực metadata wrapping bằng một cơ chế khác, hoặc re-authenticate/re-encrypt payload theo quy trình khi thay AAD.

**Key ID không mang bí mật**, nhưng **tính chính xác, tính toàn vẹn và phạm vi của key ID** rất quan trọng. Ghi lại một khóa đúng nhưng ở sai tenant có thể khiến dịch vụ trở thành confused deputy; ghi alias thay key version có thể khiến mất khả năng phục hồi.

### 7.2. Rewrap khác re-encrypt

Giả sử payload được mã hóa bởi **DEK-7** còn lớp bảo vệ DEK dùng **KEK-v3**:

~~~text
Payload ciphertext = AES-GCM(DEK-7, plaintext, nonce, aad)
Wrapped DEK        = Wrap(KEK-v3, DEK-7)

Sau rotation KEK:
Wrapped DEK mới    = Wrap(KEK-v4, DEK-7)
Payload ciphertext có thể giữ nguyên nếu AAD/content contract không đổi.
~~~

Nếu **DEK-7 bị lộ**, rewrap bằng KEK mới **không** khắc phục việc đối thủ có DEK. Phải cân nhắc thay DEK và re-encrypt payload. Nếu key ID/KEK version nằm trong AAD payload, luồng rewrap phải xử lý **xác thực metadata** phù hợp như đã trình bày, không đơn giản sửa một trường JSON.

### 7.3. Hash của DEK có thay thế key ID?

**Không nên dùng digest của secret key như một định danh phổ biến nếu không có nhu cầu/protocol được phân tích rõ.** Hash(DEK) không phải wrapped DEK, không thể khôi phục DEK; việc đưa fingerprint của secret vào log/metadata có thể làm lộ thông tin hoặc đi ngược policy quản lý key material.

Với **public key**, một fingerprint được xác định theo chuẩn có thể phục vụ đối chiếu và định danh, nhưng **fingerprint vẫn phải được kiểm tra từ nguồn tin cậy**. Với **secret/private key**, ưu tiên ID do registry/KMS tạo và mapping qua key handle được bảo vệ.

## 8. Quy trình chọn khóa cho một crypto operation

Một tầng quản lý key ID nên đứng **giữa giao thức nghiệp vụ và provider mật mã**. Không tự đưa một giá trị JSON **keyId** vào phương thức giải mã ngay khi nhận request.

### 8.1. Encrypt dữ liệu mới

1. Xác thực **principal** và tenant/resource được phép.
2. Theo policy, lấy **alias/key family hiện tại** từ registry tin cậy cho đúng purpose và thuật toán.
3. Resolve alias thành **key ID/version cụ thể** và kiểm tra trạng thái Active, IAM, cryptoperiod, key type.
4. Gọi KMS/HSM hoặc crypto provider để lấy quyền dùng khóa; nếu không được phép thì **fail closed**, không dùng khóa khác ngầm định.
5. Sinh nonce thích hợp, mã hóa bằng AEAD, ghi rõ **key ID/version thực sự được dùng** và metadata đủ để giải mã.
6. Audit **principal, operation, key reference, tenant, outcome, thời điểm** mà không ghi raw key/plaintext.

### 8.2. Decrypt dữ liệu lịch sử

1. Xác thực caller và xác minh quyền truy cập **bản ghi** trước khi mở DEK.
2. Parse envelope với giới hạn độ dài/định dạng, dùng **key ID/version của bản ghi** như thông tin lookup chưa được tin cậy.
3. Resolve key reference trong **namespace/tenant cho phép**, validate thuật toán/purpose và policy sử dụng khóa lịch sử.
4. Gọi đúng key version qua KMS/HSM hoặc provider, không tự lấy alias hiện tại.
5. Tái tạo AAD từ metadata và **ngữ cảnh tin cậy**, xác minh authentication tag AES-GCM **trước khi sử dụng plaintext**.
6. Trả lỗi nhất quán, tránh để key lookup lỗi trở thành công cụ liệt kê khóa của tenant khác; ghi audit.

### 8.3. Key ID trong dữ liệu nhận từ bên ngoài

Khi nhận file đã ký hoặc gói ciphertext của đối tác, **key ID của bên gửi chỉ là một claim**. Hệ thống cần kiểm tra:

- Đối tác/issuer đã được xác thực hay chưa.
- Key ID/version có nằm trong **bộ khóa thuộc đúng đối tác/issuer** đã được trust không.
- Thuật toán trong gói có được phép cho **đúng key type/purpose** không.
- Public key/certificate có nằm trong khoảng tin cậy thích hợp và có đáp ứng yêu cầu revocation policy không.
- Khi có chữ ký, **chính xác những bytes nào được ký**, metadata bảo vệ ở đâu, có replay hay không.

Không tự động dùng một URL **jku/x5u** hoặc path do gói đầu vào cung cấp để tải bất kỳ public key nào rồi chấp nhận nội dung. Key identifier không thể tự dựng một chuỗi tin cậy từ đầu.

## 9. Ví dụ Java 17: Key ID + version + tenant + purpose trong AES-GCM

Ví dụ dưới đây dùng **Java Cryptography Architecture (JCA)** để minh họa **lookup và kiểm tra quyền** trước khi dùng AES-GCM. Trong demo, registry giữ **SecretKey** ngay trong JVM chỉ để code tự chạy độc lập. Trong production, registry thường chỉ giữ **key reference/handle**, còn key material và phép toán nên được quản lý trong KMS/HSM hoặc crypto service được cấp quyền.

Ví dụ có **hai version của cùng key ID logic**, một version cũ chuyển sang **DECRYPT_ONLY** và version mới **ACTIVE**. Nó chứng minh:

- Encryption mới chỉ dùng version ở trạng thái **ACTIVE**.
- Decryption bản ghi cũ vẫn dùng chính version được lưu, nếu policy cho phép.
- Key reference không vượt được **tenant isolation**.
- **AAD** ràng buộc keyId/version, tenant, record ID và thuật toán.
- Sửa metadata record ID sẽ khiến **AEAD tag** không còn hợp lệ.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyIdentifierExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_LENGTH = 12; // 96 bit
    private static final int TAG_BITS = 128;
    private static final String ALGORITHM = "AES-256-GCM";
    private static final String PURPOSE = "DATA_ENCRYPTION";

    enum State {
        ACTIVE, DECRYPT_ONLY, SUSPENDED
    }

    // Ở demo: keyId là ID logic, version xác định material.
    record KeyRef(String keyId, int version) {
        KeyRef {
            if (keyId == null || keyId.isBlank() || version <= 0) {
                throw new IllegalArgumentException("Invalid key reference");
            }
        }
    }

    record KeyRecord(
            KeyRef ref,
            String tenantId,
            String purpose,
            State state,
            SecretKey material) {}

    // Base64 là encoding, không phải một lớp bảo mật khác.
    record Envelope(
            int formatVersion,
            String algorithm,
            String keyId,
            int keyVersion,
            String tenantId,
            String recordId,
            String nonceBase64,
            String ciphertextWithTagBase64) {}

    // Registry này chỉ dành cho minh họa; chưa có IAM thật.
    static final class Registry {
        private final Map<KeyRef, KeyRecord> records = new HashMap<>();

        void register(KeyRecord record) {
            if (records.putIfAbsent(record.ref(), record) != null) {
                throw new IllegalStateException("Key reference already exists");
            }
        }

        void changeState(KeyRef ref, State next) {
            KeyRecord old = records.get(ref);
            if (old == null) {
                throw new IllegalArgumentException("Unknown key");
            }
            records.put(ref, new KeyRecord(
                    old.ref(), old.tenantId(), old.purpose(),
                    next, old.material()));
        }

        KeyRecord resolve(
                String authenticatedTenant,
                KeyRef ref,
                String requiredPurpose,
                boolean forEncryption) {
            KeyRecord record = records.get(ref);
            if (record == null
                    || !record.tenantId().equals(authenticatedTenant)
                    || !record.purpose().equals(requiredPurpose)) {
                // Không tiết lộ tenant/key nào bị thiếu.
                throw new SecurityException("Key is not available");
            }

            if (forEncryption) {
                if (record.state() != State.ACTIVE) {
                    throw new SecurityException("Key is not active");
                }
            } else if (record.state() != State.ACTIVE
                    && record.state() != State.DECRYPT_ONLY) {
                throw new SecurityException("Key cannot decrypt");
            }
            return record;
        }
    }

    // AAD dùng UTF-8 và prefix độ dài từng trường.
    private static void writeField(DataOutputStream out, String value)
            throws Exception {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }

    private static byte[] aad(
            int formatVersion,
            String algorithm,
            String tenantId,
            String recordId,
            String keyId,
            int keyVersion) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(formatVersion);
            writeField(out, algorithm);
            writeField(out, tenantId);
            writeField(out, recordId);
            writeField(out, keyId);
            out.writeInt(keyVersion);
        }
        return bytes.toByteArray();
    }

    private static KeyRecord newKey(
            String keyId, int version, String tenant) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return new KeyRecord(
                new KeyRef(keyId, version),
                tenant, PURPOSE, State.ACTIVE, generator.generateKey());
    }

    static Envelope encrypt(
            Registry registry, String authenticatedTenant,
            String recordId, KeyRef ref, byte[] plaintext)
            throws Exception {
        KeyRecord key = registry.resolve(
                authenticatedTenant, ref, PURPOSE, true);

        byte[] nonce = new byte[NONCE_LENGTH];
        RANDOM.nextBytes(nonce);
        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, key.material(),
                new GCMParameterSpec(TAG_BITS, nonce));
        aes.updateAAD(aad(1, ALGORITHM, authenticatedTenant,
                recordId, ref.keyId(), ref.version()));
        byte[] ciphertextWithTag = aes.doFinal(plaintext);

        return new Envelope(
                1, ALGORITHM, ref.keyId(), ref.version(),
                authenticatedTenant, recordId,
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextWithTag));
    }

    static byte[] decrypt(
            Registry registry, String authenticatedTenant,
            String requestedRecordId, Envelope envelope)
            throws Exception {
        if (envelope.formatVersion() != 1
                || !ALGORITHM.equals(envelope.algorithm())) {
            throw new IllegalArgumentException("Unsupported format");
        }
        if (!authenticatedTenant.equals(envelope.tenantId())
                || !requestedRecordId.equals(envelope.recordId())) {
            throw new SecurityException("Record scope mismatch");
        }

        KeyRef ref = new KeyRef(
                envelope.keyId(), envelope.keyVersion());
        KeyRecord key = registry.resolve(
                authenticatedTenant, ref, PURPOSE, false);

        byte[] nonce = Base64.getDecoder().decode(envelope.nonceBase64());
        byte[] ciphertextWithTag = Base64.getDecoder().decode(
                envelope.ciphertextWithTagBase64());
        if (nonce.length != NONCE_LENGTH
                || ciphertextWithTag.length < TAG_BITS / 8) {
            throw new IllegalArgumentException("Invalid envelope size");
        }

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.DECRYPT_MODE, key.material(),
                new GCMParameterSpec(TAG_BITS, nonce));
        aes.updateAAD(aad(envelope.formatVersion(), envelope.algorithm(),
                envelope.tenantId(), envelope.recordId(),
                envelope.keyId(), envelope.keyVersion()));
        return aes.doFinal(ciphertextWithTag); // Xác thực tag
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry();
        String logicalKeyId = "key-" + UUID.randomUUID();
        KeyRecord v1 = newKey(logicalKeyId, 1, "tenant-42");
        registry.register(v1);

        Envelope oldRecord = encrypt(
                registry, "tenant-42", "customer-123", v1.ref(),
                "Hồ sơ cũ".getBytes(StandardCharsets.UTF_8));
        registry.changeState(v1.ref(), State.DECRYPT_ONLY);

        KeyRecord v2 = newKey(logicalKeyId, 2, "tenant-42");
        registry.register(v2);
        Envelope newRecord = encrypt(
                registry, "tenant-42", "customer-456", v2.ref(),
                "Hồ sơ mới".getBytes(StandardCharsets.UTF_8));

        System.out.println("Old version: " + oldRecord.keyVersion());
        System.out.println("New version: " + newRecord.keyVersion());
        System.out.println("Old plaintext: " + new String(
                decrypt(registry, "tenant-42", "customer-123", oldRecord),
                StandardCharsets.UTF_8));

        try {
            encrypt(registry, "tenant-42", "customer-789", v1.ref(),
                    "not allowed".getBytes(StandardCharsets.UTF_8));
            throw new AssertionError("DECRYPT_ONLY key was used to encrypt");
        } catch (SecurityException expected) {
            System.out.println("Old version cannot encrypt");
        }

        try {
            decrypt(registry, "tenant-OTHER", "customer-123", oldRecord);
            throw new AssertionError("Tenant isolation failed");
        } catch (SecurityException expected) {
            System.out.println("Cross-tenant access denied");
        }

        Envelope tampered = new Envelope(
                oldRecord.formatVersion(), oldRecord.algorithm(),
                oldRecord.keyId(), oldRecord.keyVersion(),
                oldRecord.tenantId(), "customer-999",
                oldRecord.nonceBase64(),
                oldRecord.ciphertextWithTagBase64());
        try {
            decrypt(registry, "tenant-42", "customer-999", tampered);
            throw new AssertionError("Tampered AAD accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered record ID rejected by GCM");
        }

        // Demo in plaintext giả để minh họa. Production không log
        // private key, DEK hoặc dữ liệu khách hàng thật.
    }
}
~~~

Lưu thành **KeyIdentifierExample.java**, chạy với JDK 17+:

~~~bash
javac KeyIdentifierExample.java
java KeyIdentifierExample
~~~

Kết quả dự kiến:

~~~text
Old version: 1
New version: 2
Old plaintext: Hồ sơ cũ
Old version cannot encrypt
Cross-tenant access denied
Tampered record ID rejected by GCM
~~~

Định danh logic có thể thay đổi qua mỗi lần chạy vì UUID mới được tạo để minh họa. **UUID ở đây chỉ là key identifier**, không phải AES key hay một bearer token. **KeyGenerator** mới sinh key material; AES-GCM dùng nonce 96 bit mới và authentication tag 128 bit.

### 9.1. Giới hạn quan trọng của ví dụ

1. **Key material nằm trong JVM** để code tự chạy. Production nên resolve **KMS/HSM handle** qua registry đáng tin và dùng provider/crypto service có policy thích hợp.
2. **Registry dùng HashMap không có concurrency control**. Không dùng logic này làm kho khóa thực trong nhiều instance; cần unique constraint, transaction, revision và consistency theo threat model.
3. **Tham số authenticatedTenant là giá trị đã được xác thực theo giả định**. Nếu đơn thuần lấy từ HTTP request, check tenant trong ví dụ không tạo ra isolation thực.
4. **DECRYPT_ONLY là policy minh họa**. Với khóa Suspended/Compromised, decrypt cũng có thể phải bị chặn theo quy trình; không tự mở exception.
5. **Không có KMS IAM, audit, backup và crypto-erasure**. Những phần này là yêu cầu vận hành, không được thay bằng Map trong bộ nhớ.
6. **Một nonce ngẫu nhiên 96 bit không đảm bảo không bao giờ trùng** nếu dùng lâu dài một khóa AES. Demo chỉ mã hóa vài bản ghi; production phải giới hạn invocations/rotate và quản lý nonce trên tất cả instance dùng cùng key.
7. **Không có cơ chế chống replay**: một envelope còn nguyên vẫn có thể được giải mã nhiều lần. Message ID/sequence/idempotency là trách nhiệm tầng nghiệp vụ.
8. **AAD xác thực metadata nhưng không tự cấp quyền**; registry và IAM phải kiểm tra owner/tenant/purpose trước khi dùng khóa.
9. **Không tự dùng key ID/version từ input làm resource KMS nếu chưa resolve/validate**. Demo dùng in-memory registry; production phải map tới đúng key reference do provider cấp.
10. **Không có crypto-agility negotiation**: chỉ chấp nhận AES-256-GCM và format v1, đúng tinh thần allowlist; khi nâng cấp phải có migration/version schema riêng.

## 10. Key ID trong vòng đời: Tạo, rotate, suspend, revoke và destroy

**Key identifier là tham chiếu xuyên suốt vòng đời**, không phải trạng thái. Khi trạng thái hoặc quyền thay đổi, ID thường vẫn cần tồn tại để hệ thống biết khóa đã bị tác động ra sao.

### 10.1. Khi tạo và cấp phát

Một lần **GenerateKey/ImportKey** nên có quy trình:

1. **Tạo hoặc nhận key material** từ CSPRNG, KMS/HSM hoặc cơ chế nhập được phê duyệt.
2. Gán **key reference duy nhất** trong đúng namespace; khóa mới không chiếm ID của key material khác.
3. Ghi **key type, algorithm, purpose, owner, tenant, provider location, version** và trạng thái ban đầu.
4. Thiết lập IAM/key policy, phân tách quyền **Create/Sign/Decrypt/Rotate/Destroy**.
5. Đưa khóa vào trạng thái sử dụng chỉ sau approval/test; không để quy trình tạo khóa tự cấp mọi quyền dùng.
6. Ghi **audit event** về ai tạo/cấp phát và với chính sách nào, không ghi secret trong event.

Khi import khóa từ hệ thống cũ, không tự tin rằng **legacyKeyId** chưa từng trùng hoặc là duy nhất toàn cầu. Dùng **mapping bảng chuyển đổi** có kiểm tra và immutable source reference. Không đổi key material chỉ để tránh trùng tên khi chưa có kế hoạch re-encrypt/migration.

### 10.2. Khi rotate

Có hai chiến lược thường dùng:

| Chiến lược | Cách ID thay đổi | Điều bắt buộc |
|---|---|---|
| **ID bất biến theo material** | Tạo key ID mới; alias/key family chuyển sang ID mới | Gói lịch sử giữ key ID cũ; registry mapping còn truy xuất được |
| **ID logic và version** | Giữ logical key ID, tăng version để trỏ material mới | Gói lịch sử giữ đủ cả ID và version; version cũ không bị ghi đè |

Quy trình tốt có thể **công bố key version mới trước**, chuyển mới Encrypt/Sign sang version mới, giữ quyền **Decrypt/Verify** cũ trong khoảng cho phép, thực hiện rewrap/re-encrypt khi cần, rồi mới retire/hủy theo dependency review.

**Không chỉ cập nhật alias và coi dữ liệu cũ đã được rotate.** Alias chỉ thay đổi điểm lựa chọn cho thao tác mới; ciphertext được bảo vệ bằng khóa cũ vẫn phụ thuộc khóa cũ trừ khi migration thật sự diễn ra.

### 10.3. Khi suspend/disable/revoke

Inventory nên giữ **key ID/version, state, effective time, reason, incident ID, actor và policy revision**. Tuy nhiên:

- **Suspended/Disabled** trong KMS chặn một số API theo provider; bản sao private key/DEK đã export có thể vẫn sử dụng offline.
- **Revoke certificate** thuộc hệ thống tin cậy PKI; không tương đương với hủy private key hoặc disable resource KMS.
- **Revoke token/session** là biện pháp khác với rotate signing key; JWT đã ký bằng khóa cũ có thể vẫn được verifier chấp nhận nếu trust cache chưa cập nhật.
- **Retired/Decrypt-only** có thể được dùng cho dữ liệu lịch sử trong một số kiến trúc; phải có policy rõ, không mặc định mọi khóa disabled vẫn decrypt được.

Vì thế **key identifier phải đi cùng state và effective policy**, chứ không phải bản thân ID tự nói lên những quyền còn tồn tại.

### 10.4. Khi destroy và crypto-erasure

**Destroy key material** không đồng nghĩa xóa key ID khỏi inventory. Có thể vẫn cần một **tombstone** và audit record để chứng minh khóa từng tồn tại, đã bị hủy vào lúc nào và những bản ghi nào chịu ảnh hưởng.

Ngược lại, **xóa key ID khỏi database** không hủy khóa ở HSM, backup hoặc cache. Crypto-erasure chỉ có ý nghĩa khi những bản sao/đường phục hồi của key material cần thiết không còn dùng được theo threat model.

Với khóa được dẫn xuất từ một **root secret bằng HKDF**, xóa record của derived key không đủ nếu có thể **tái dẫn xuất** nó từ root và context. Với encrypted DEK còn được wrap bằng KEK, hủy nhầm KEK trước khi kiểm tra phụ thuộc có thể làm dữ liệu cũ **mất khả năng khôi phục**.

## 11. Thiết kế hệ thống quản lý key inventory và audit

### 11.1. Tách control plane và data plane

~~~mermaid
flowchart TD
    A["Security Admin / Key Owner"] --> C["Key Inventory & Policy Control Plane"]
    C --> R[("Registry: ID, version, owner, purpose, state, mapping")]
    C --> U["Approval, lifecycle transitions, audit"]
    W["Authenticated Workload"] --> G["Crypto Gateway / KMS Client"]
    G --> R
    R --> P["Resolve KMS/HSM handle/version"]
    G --> I["IAM + tenant/resource authorization"]
    I --> P
    P --> H["KMS/HSM thực thi cryptographic operation"]
    H --> O["Kết quả được phép"]
    G --> L[("Usage audit: actor, keyRef, operation, result")]
    U --> L
~~~

**Control plane** quản lý đăng ký, chính sách, phiên bản, trạng thái và phê duyệt. **Data plane** xử lý những thao tác như Encrypt/Decrypt/Sign/Unwrap với khóa thực tế. Một key registry là nguồn thông tin để chọn khóa, nhưng **không thay thế enforcement ngay tại nơi thực hiện phép mật mã**.

### 11.2. Các bảng hoặc chỉ mục cần thiết

Một hệ thống có thể có những nhóm dữ liệu logic:

| Nhóm record | Khóa/định danh | Vai trò |
|---|---|---|
| **Key family** | familyId + namespace | Gom version và alias nghiệp vụ |
| **Key version** | provider-scoped keyId/version hoặc immutable materialId | Map chính xác một key material/handle và trạng thái |
| **Alias mapping** | namespace + alias + target reference + revision | Phát hành active version và kiểm tra drift |
| **Key policy** | policyId + revision + principal/tenant/purpose | Kiểm soát thao tác |
| **Dependency record** | dataSet/artifactId + keyRef | Biết dữ liệu/chữ ký nào phụ thuộc khóa |
| **Lifecycle event** | eventId + keyRef + timestamp + actor | Lịch sử thay đổi không sửa lại được tùy thiết kế |
| **Usage audit** | requestId + keyRef + operation + outcome | Giám sát và điều tra |

Đây là **logical design**, không bắt buộc mỗi nhóm là một bảng vật lý riêng. Cần **unique constraints** và kiểm soát giao dịch khi create/import/rotate/alias switch. Khi dùng multi-region hoặc event-driven, state/event cần revision có thứ tự và chính sách giải quyết conflict.

### 11.3. Audit những gì, tránh ghi những gì?

Nên ghi **thời điểm, authenticated principal, tenant, keyId/version, provider/resource scope, operation, policy decision, outcome, request/correlation ID**, reason khi rotate/suspend/delete và thông tin phê duyệt theo yêu cầu.

Không ghi **raw DEK, KEK, private key, seed, secret/password, plaintext nhạy cảm**. Nếu key ID chứa PII hoặc cấu trúc nội bộ, audit phải được phân quyền và retention phù hợp. Một giá trị log **keyId** vẫn cần ghi rõ **namespace/version** để không gây nhầm giữa provider hoặc tenant.

### 11.4. Đối soát inventory định kỳ

Một inventory trong database có thể **trôi** khỏi trạng thái thật ở KMS/HSM nếu một operator thao tác trực tiếp trên provider, có import không qua quy trình, key bị xóa ngoài kế hoạch hoặc alias đổi mà không đồng bộ.

Quy trình reconciliation có thể:

1. Đối chiếu **provider resource ID, version, algorithm, state, owner** với registry theo quyền read-only được cấp.
2. Phát hiện khóa **orphaned** trong KMS nhưng không có inventory owner, hoặc inventory entry tham chiếu resource không còn tồn tại.
3. Phát hiện **alias drift** và quyền IAM/key policy khác với bản approved.
4. So sánh key usage/audit và dependency để tìm khóa không dùng hoặc khóa được dùng ngoài mục đích.
5. Tạo ticket xử lý sai lệch, **không tự xóa/hủy material chỉ vì không còn thấy ứng dụng dùng**.

Việc reconciliation phải tôn trọng giới hạn API/permission của provider. Nên có quy trình riêng cho key được quản lý bởi tổ chức đối tác hoặc đang ở trạng thái legal hold.

## 12. Threat model: Những rủi ro bắt nguồn từ định danh khóa

| Sai lầm | Hậu quả có thể xảy ra | Biện pháp |
|---|---|---|
| Chỉ lưu **alias** của khóa mã hóa | Rotate alias làm mất khả năng resolve bản mã lịch sử | Ghi immutable key ID/version thực dùng |
| **Tái sử dụng key ID** cho material khác | Chọn nhầm khóa, audit và migration sai | ID/version không tái sử dụng, tombstone |
| Không có **namespace** | ID trùng giữa region, account, tenant hoặc issuer | Qualified reference, unique constraints |
| Lấy key ID từ request làm **quyền Decrypt** | Cross-tenant access và confused deputy | IAM, principal/tenant validation, KMS policy |
| Cho caller tự chọn key ID và algorithm | Algorithm/key confusion, downgrade | Allowlist, kiểm tra key type/purpose |
| Tin **kid** trong JWT là bằng chứng signer | Token giả có thể khiến verifier dùng khóa attacker | Issuer-scoped trusted JWKS, alg/aud/iss validation |
| Tải JWK từ URL không tin cậy | SSRF, trust-anchor substitution | Endpoint allowlist, không tin header điều khiển URL |
| Hash public key nhưng không xác thực fingerprint | MITM/tráo khóa vẫn có thể xảy ra | Pin/trust chain từ nguồn độc lập đáng tin |
| Không giữ **key version** trong envelope | Không xác định material sau rotation | Versioned reference và backup/restore |
| Chỉ sửa **keyVersion** trong metadata | AAD/tag sai hoặc wrong wrapped DEK | Migration đúng rewrap/re-encrypt và content binding |
| **Key ID chứa PII** lộ trong URL/JWT/log | Rò metadata/khả năng liên kết dữ liệu | Opaque ID, hạn chế public metadata và audit access |
| Alias/registry drift so với KMS | Chọn sai resource hoặc state | Reconciliation, owner, revision và monitoring |
| Delete inventory record thay vì key material | Key vẫn tồn tại hoặc sử dụng được | KMS/HSM destruction workflow, kiểm tra bản sao |
| Hủy provider key mà không kiểm tra dependency | Ciphertext lịch sử không decrypt, chữ ký khó Verify | Dependency inventory, migration và restore test |
| Cấp **service role Decrypt tất cả keys** | Key ID của tenant khác trở thành đường vượt quyền | Least privilege, tenant isolation, encryption context |
| Audit chỉ ghi alias mà thiếu version | Không biết key thực sự dùng ở thời điểm sự cố | Log resolved key ID/version, actor, operation và outcome |

## 13. Case study: Xoay vòng khóa dữ liệu khi hệ thống có nhiều tenant

Một nền tảng đặt hồ sơ khách hàng trong database, dùng **AES-GCM** với **DEK theo bản ghi**, còn các DEK được **wrap bởi KEK của tenant** trong KMS. Dịch vụ ký hóa đơn dùng private key trong HSM; public key được công bố qua JWKS hoặc một trust store tương ứng.

### 13.1. Vấn đề ban đầu

Team chỉ lưu **keyName=customer-current** trong metadata ciphertext. Khi chuyển alias sang KEK mới, một số bản ghi cũ không còn giải mã đúng. Đồng thời, API ký dùng **kid=signing** ở nhiều môi trường; Gateway có nguy cơ dùng sai public key nếu cache không ràng buộc issuer/environment.

### 13.2. Thiết kế sửa

1. **Inventory ID bất biến:** mỗi provider key material có một reference không tái sử dụng; logic **tenant-42/customer-key** được quản lý như key family/alias.
2. **Version ghi tại thời điểm Encrypt:** envelope lưu **wrappingKeyId/version** thực dùng, không chỉ alias hiện tại. Key ID/version được ràng buộc phù hợp với metadata/AAD.
3. **Cross-tenant permission:** tenant được suy ra từ caller identity, service kiểm tra record ownership, provider policy chỉ cấp đúng key scope; key ID gửi từ client không được tin như authorization.
4. **Rotation:** tạo KEK mới, kiểm tra quyền, chuyển thao tác **Wrap** mới sang version mới; dữ liệu cũ vẫn resolve v3 hoặc được rewrap qua quy trình có phê duyệt.
5. **AAD:** nếu wrapping version nằm trong AAD payload, phải xử lý migration có kiểm tra tag. Không chỉ sửa metadata.
6. **Signature trust:** issuer A và issuer B có registry/JWKS riêng; **kid** chỉ được resolve trong issuer/trust domain đã được xác thực.
7. **Audit:** theo dõi key ref đầy đủ, principal, tenant, Encrypt/Decrypt/Sign/Unwrap result và sự kiện đổi alias.
8. **Retirement:** trước khi hủy KEK cũ, quét dependency, xác nhận wrapped DEK đã chuyển đổi hoặc có đường khôi phục, thử restore bản ghi mẫu.

### 13.3. Kết quả mong đợi và giới hạn

Hệ thống có thể phân biệt **khóa hiện tại cho thao tác mới** và **khóa lịch sử cần đọc hoặc Verify**, giảm nguy cơ downtime do alias drift và rủi ro cross-tenant lookup. Nhưng key identifier đúng **không chữa được** một DEK bị lộ, nonce AES-GCM lặp, private key bị chiếm hoặc IAM quá rộng. Các cơ chế mật mã và kiểm soát vòng đời vẫn phải được vận hành đồng bộ.

## 14. Checklist thiết kế key identifier và kiểm kê khóa

1. **Identity semantics:** key ID chỉ material bất biến hay logical family? Version có ý nghĩa và phạm vi chính xác?
2. **Namespace:** định danh duy nhất theo provider/account/region/tenant/environment nào; cần qualified reference không?
3. **No reuse:** có unique constraint, tombstone và chính sách tránh cấp lại ID đã dùng?
4. **Alias:** chỉ dùng alias cho lựa chọn active key mới? Gói lịch sử có lưu resolved key ID/version không?
5. **Inventory metadata:** owner, tenant, purpose, algorithm, key type, state, provider location, policy và dependency có đủ?
6. **IAM:** ai được resolve và sử dụng key? Có kiểm tra principal/tenant/resource và KMS key policy ở enforcement point?
7. **Trust:** public key/JWKS/certificate lấy từ nguồn đã xác thực? kid có bị giới hạn theo issuer và algorithm?
8. **Envelope:** keyRef, format, nonce, tag, wrapped DEK và AAD đủ để giải mã lịch sử và phát hiện metadata bị tráo?
9. **Rotation:** đổi key ID/version/alias có kế hoạch rewrap/re-encrypt, phục hồi dữ liệu cũ và audit?
10. **Lifecycle:** suspend, retire, revoke, destroy có thay đổi key usage thế nào, đã có dependency review?
11. **Reconciliation:** inventory có được đối soát với KMS/HSM, alias và quyền thực tế không?
12. **Audit:** có ghi key ID/version, namespace, actor, operation, outcome mà không lộ secret?
13. **Failure handling:** key không tồn tại, version chưa được phép, KMS timeout hoặc tag GCM sai có fail-closed không?
14. **Tests:** có test cross-tenant, key version mismatch, stale alias, wrong purpose, retry/rotation và restore dữ liệu cũ?
15. **Incident response:** khi key bị lộ, có thể nhanh chóng xác định dữ liệu/tenant/dịch vụ phụ thuộc và triển khai revoke/rotate không?

### Câu hỏi tự kiểm tra

**Câu 1.** Key ID có phải là AES key hoặc private key không?

**Trả lời:** **Không.** Key ID là định danh/metadata dùng lookup. Key material là bí mật hoặc public key thực sự được phép toán mật mã sử dụng.

**Câu 2.** Một người biết key ID của tenant khác có được phép gọi KMS Decrypt không?

**Trả lời:** **Không.** Phải kiểm tra principal, tenant, resource, purpose và IAM/key policy. ID không phải bearer credential.

**Câu 3.** Vì sao không chỉ lưu alias **current-key** trong ciphertext?

**Trả lời:** Alias có thể đổi target khi rotation. Muốn giải mã lịch sử phải biết chính xác key ID/version đã bảo vệ dữ liệu lúc mã hóa.

**Câu 4.** Cùng kid=sign-v2 trong JWKS của hai issuer có chắc là cùng khóa không?

**Trả lời:** **Không.** Kid thường chỉ giúp chọn khóa trong tập của một issuer/trust domain. Verifier phải ràng buộc issuer, thuật toán và nguồn JWKS đã tin cậy.

**Câu 5.** Tính fingerprint SHA-256 của public key có tự chứng minh khóa đó thuộc về đối tác B?

**Trả lời:** **Không.** Fingerprint giúp so khớp public key, nhưng phải lấy giá trị tin cậy qua kênh hoặc chứng cứ đã xác thực.

**Câu 6.** Khi rewrap DEK dưới KEK-v4, nếu KEK-v3 nằm trong AAD của ciphertext, có thể chỉ đổi trường keyVersion sang v4?

**Trả lời:** **Không.** AAD thay đổi sẽ làm tag AES-GCM không còn hợp lệ. Phải thiết kế ranh giới metadata và migration phù hợp, có bước xác thực lại hoặc re-encrypt theo quy trình.

**Câu 7.** Key ID đã bị xóa khỏi inventory có chứng minh key material trong HSM bị hủy chưa?

**Trả lời:** **Không.** Metadata deletion khác key destruction; cần kiểm tra provider, backup, các bản sao và đường phục hồi.

**Câu 8.** Sau rotation, có nhất thiết destroy ngay private signing key cũ và xóa public key cũ khỏi JWKS?

**Trả lời:** **Không mặc định.** Private key cũ nên ngừng Sign theo policy, còn public key cũ có thể cần cho Verify tài liệu/token chưa hết thời hạn, trừ trường hợp sự cố đòi hỏi revoke.

**Câu 9.** KMS trả một key resource ID duy nhất, vậy có thể bỏ toàn bộ metadata purpose/owner/tenant/state không?

**Trả lời:** **Không.** ID chỉ giúp định vị resource. Quản lý vòng đời, phân quyền, audit và kiểm soát sử dụng đúng mục đích vẫn cần metadata và policy.

**Câu 10.** Nếu DEK đã lộ, đổi alias sang KEK mới và rewrap DEK có đủ bảo vệ dữ liệu không?

**Trả lời:** **Không.** Kẻ tấn công có DEK vẫn có thể giải mã dữ liệu liên quan. Cần đánh giá thay DEK, re-encrypt và phạm vi bản mã bị ảnh hưởng.

**Điểm cốt lõi:** **Key identifier là địa chỉ đáng tin cậy để tìm đúng khóa, không phải bản thân khóa hoặc quyền sử dụng khóa.** Một hệ thống key inventory an toàn cần **định danh không nhập nhằng, namespace/version, không tái sử dụng, mapping provider được kiểm soát, IAM, key purpose, trạng thái, audit và dependency inventory**. Khi kết hợp với KMS/HSM, chữ ký số và envelope encryption, phải lưu **key reference thực sự được dùng** để xoay vòng, phục hồi và hủy khóa mà không làm mất dữ liệu hoặc phá ranh giới tenant.
