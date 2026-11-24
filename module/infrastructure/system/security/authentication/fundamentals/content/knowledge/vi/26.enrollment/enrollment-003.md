# Device enrollment — Đăng ký và thiết lập niềm tin cho thiết bị

> **Chương:** Enrollment  
> **Chủ đề:** Device enrollment  
> **Phạm vi:** Security Authentication Fundamentals — đăng ký thiết bị với tài khoản hoặc tổ chức, thiết lập danh tính thiết bị bằng khóa/chứng chỉ, xác minh quyền giữ khóa, đánh giá trạng thái quản lý và vận hành vòng đời thiết bị.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt device enrollment, device registration, credential enrollment và quản lý thiết bị MDM/UEM.
2. Thiết kế quy trình bootstrap để liên kết một thiết bị với đúng người dùng, tài khoản và tổ chức.
3. Giải thích vai trò của khóa thiết bị, phần cứng bảo vệ khóa, chứng chỉ và attestation.
4. Xây dựng giao thức challenge-response để chứng minh thiết bị đang giữ private key đã đăng ký.
5. Đánh giá khác biệt giữa thiết bị managed, BYOD, shared/kiosk và thiết bị không có phần cứng bảo mật.
6. Quản lý trạng thái pending, active, suspended, lost và revoked; xử lý thay thiết bị, mất thiết bị, offboarding và khôi phục.
7. Xác định các tín hiệu thiết bị có thể dùng trong risk policy và giới hạn của chúng.
8. Kiểm thử enrollment, binding, attestation, proof of possession, thu hồi và cô lập tenant.

## 1. Device enrollment là gì?

**Device enrollment** là quy trình đưa một thiết bị vào phạm vi nhận diện và chính sách của một ứng dụng hoặc tổ chức. Trong quá trình này, hệ thống xác định thiết bị thuộc tài khoản/tổ chức nào, thiết lập một hoặc nhiều bằng chứng mật mã để nhận diện thiết bị, và ghi nhận trạng thái quản lý cũng như quyền được phép của thiết bị.

Ví dụ: Nhân viên mới đăng nhập cổng công ty trên laptop. Sau khi xác minh danh tính, cổng yêu cầu thiết bị tạo một cặp khóa. Private key được giữ trong vùng bảo mật của thiết bị; public key được gửi về server và gắn với tài khoản nhân viên cùng tổ chức. Từ đó, thiết bị có thể chứng minh quyền giữ khóa khi truy cập tài nguyên yêu cầu thiết bị đã đăng ký.

Enrollment tạo ra một quan hệ giữa các thực thể:

- **User/account:** người dùng hoặc tài khoản nội bộ được xác thực;
- **Organization/tenant:** tổ chức sở hữu chính sách và phạm vi quản lý;
- **Device:** thiết bị vật lý hoặc môi trường thiết bị được định danh;
- **Device credential:** public key, certificate hoặc credential dùng để chứng minh quyền giữ khóa;
- **Management authority:** MDM/UEM hoặc hệ thống quản lý thiết bị nếu có;
- **Relying service:** ứng dụng/API chấp nhận bằng chứng thiết bị theo policy.

**Thiết bị đã enrollment không mặc nhiên là an toàn.** Enrollment chỉ thiết lập danh tính và trạng thái ban đầu. Thiết bị có thể bị mất, bị root/jailbreak, bị malware chiếm quyền, bị gỡ quản lý hoặc không còn đáp ứng policy sau đó.

## 2. Phân biệt enrollment với các khái niệm gần nhau

| Khái niệm | Điều gì được thiết lập? | Ví dụ |
| --- | --- | --- |
| **Device enrollment** | Liên kết thiết bị với tài khoản/tổ chức và policy | Đưa laptop của nhân viên vào danh sách thiết bị được phép |
| **Device registration** | Ghi nhận một thiết bị/credential để nhận diện hoặc đăng nhập | Lưu public key của điện thoại cho tài khoản |
| **Credential enrollment** | Tạo một phương thức xác thực | Đăng ký passkey hoặc khóa bảo mật |
| **MDM/UEM enrollment** | Đưa thiết bị vào hệ thống quản lý cấu hình và tuân thủ | Cài profile quản lý, áp dụng screen lock và mã hóa đĩa |
| **Device attestation** | Cung cấp bằng chứng về nguồn gốc hoặc thuộc tính của khóa/nền tảng | Xác minh khóa được tạo trong TPM/secure hardware theo policy |
| **Device authentication** | Chứng minh đang kiểm soát credential của thiết bị | Ký challenge bằng private key đã đăng ký |
| **Device compliance** | Đánh giá thiết bị hiện có đáp ứng policy không | OS còn được hỗ trợ, có mã hóa và không bị jailbreak |

Các hoạt động có thể diễn ra trong cùng một trải nghiệm nhưng trả lời các câu hỏi khác nhau. Một thiết bị có thể đã đăng ký khóa nhưng chưa được MDM quản lý. Ngược lại, một laptop có thể được MDM quản lý nhưng chưa có credential để chứng minh danh tính với một API.

### Device identity không phải user identity

Khóa thiết bị chứng minh quyền kiểm soát một credential gắn với thiết bị hoặc môi trường thiết bị. Nó không tự chứng minh người đang ngồi trước thiết bị là nhân viên nào. Hệ thống thường cần cả:

- Bằng chứng danh tính người dùng;
- Bằng chứng thiết bị đang giữ khóa;
- Chính sách liên kết hai danh tính;
- Kiểm tra account, tenant, quyền và trạng thái hiện hành.

Không dùng một chứng chỉ thiết bị để thay thế hoàn toàn xác thực người dùng, trừ khi hệ thống có mô hình workload/device identity riêng và đã xác định rõ chủ thể được đại diện.

## 3. Mô hình tin cậy và ranh giới bảo mật

Một kiến trúc enrollment thường có các miền tin cậy:

`````````mermaid
flowchart LR
    subgraph USER["Miền người dùng"]
        U["User / Account"]
        APP["Enrollment client"]
    end
    subgraph DEVICE["Miền thiết bị"]
        KEY["Private key"]
        HW["TPM / Secure Enclave / Keystore"]
        KEY --- HW
    end
    subgraph CONTROL["Miền kiểm soát"]
        ENROLL["Enrollment service"]
        REG["Device registry"]
        CA["CA / Key service"]
        MDM["MDM / UEM"]
        ENROLL --> REG
        ENROLL --> CA
        MDM --> REG
    end
    subgraph RESOURCE["Miền tài nguyên"]
        API["Gateway / Resource API"]
        POLICY["Device + user policy"]
        API --> POLICY
    end
    U --> APP
    APP -->|"Challenge / public key / proof"| ENROLL
    HW -->|"Chữ ký hoặc attestation"| ENROLL
    REG --> POLICY
    CA --> REG
    MDM --> POLICY
`````````

Các ranh giới cần bảo vệ:

- **Account binding:** ai được quyền thêm thiết bị vào tài khoản?
- **Tenant binding:** thiết bị thuộc tenant nào và có thể được dùng ở tenant khác không?
- **Key custody:** private key có thể bị export hoặc sao chép không?
- **Attestation trust:** hệ thống tin nhà sản xuất, nền tảng và chuỗi chứng thực nào?
- **Management trust:** trạng thái MDM/compliance đến từ nguồn có thẩm quyền nào?
- **Runtime trust:** bằng chứng cũ còn đủ tin cậy ở thời điểm request hiện tại không?

## 4. Thiết kế bootstrap: xác minh người dùng trước khi đăng ký thiết bị

Enrollment là thao tác có thể làm tăng khả năng truy cập của attacker. Nếu kẻ tấn công đã chiếm session người dùng, chúng có thể đăng ký thiết bị của mình rồi tiếp tục truy cập sau khi session ban đầu bị thu hồi. Vì vậy, việc thêm thiết bị cần được bảo vệ như một thao tác bảo mật nhạy cảm.

### Điều kiện trước enrollment

1. Người dùng đã được xác thực bằng phương thức phù hợp với mức rủi ro.
2. Với tài khoản nhạy cảm, yêu cầu step-up bằng passkey/MFA hoặc phương thức chống phishing.
3. Xác định account và tenant từ dữ liệu server-side; không tin user ID/tenant ID do client tự gửi.
4. Kiểm tra account còn active và người dùng có quyền đăng ký thiết bị.
5. Tạo enrollment transaction riêng, có ID ngẫu nhiên, mục đích, thời hạn và trạng thái pending.
6. Áp dụng giới hạn số thiết bị, số lần thử và tốc độ tạo enrollment.
7. Thông báo cho người dùng hoặc quản trị viên khi có thiết bị mới được thêm.

### Không dùng email đơn lẻ làm bằng chứng enrollment

Một link email có thể là bước xác nhận hoặc kênh thông báo, nhưng không nên là bằng chứng duy nhất để thêm thiết bị có quyền truy cập cao. Email có thể bị chiếm, chuyển tiếp hoặc bị tái sử dụng. Với thao tác nhạy cảm, cần xác minh lại bằng credential đã tin cậy hoặc quy trình recovery có assurance phù hợp.

## 5. Tạo danh tính mật mã cho thiết bị

Một cách phổ biến để nhận diện thiết bị là tạo cặp khóa bất đối xứng:

- Thiết bị tạo **private key** và giữ khóa trong vùng bảo mật phù hợp;
- Server nhận **public key** và lưu cùng device record;
- Khi cần xác thực thiết bị, server gửi challenge mới;
- Thiết bị ký challenge bằng private key;
- Server xác minh chữ ký bằng public key đã lưu.

Private key không cần rời thiết bị. Đây là nền tảng cho proof of possession (PoP).

### Nơi lưu khóa

| Nền tảng/vị trí | Thuộc tính thường có | Giới hạn cần đánh giá |
| --- | --- | --- |
| **TPM** | Phần cứng bảo vệ khóa, có thể hỗ trợ key attestation và policy | Tính năng phụ thuộc thiết bị, firmware và cấu hình |
| **Secure Enclave / Secure Element** | Vùng phần cứng tách biệt để bảo vệ thao tác khóa | API và mức đảm bảo khác nhau theo nền tảng |
| **Hardware-backed Keystore** | Khóa có thể được tạo/giữ trong phần cứng bảo mật | Không phải mọi thiết bị đều hỗ trợ cùng cấp độ |
| **Software Keystore** | Lưu khóa qua cơ chế hệ điều hành/phần mềm | Khả năng chống trích xuất phụ thuộc OS và trạng thái thiết bị |
| **File/key store thông thường** | Dễ triển khai và di chuyển | Private key có thể bị sao chép nếu môi trường bị chiếm |

Nếu policy yêu cầu khóa không xuất được hoặc hardware-backed, cần xác minh thuộc tính đó bằng cơ chế nền tảng phù hợp. Chỉ nhìn tên thiết bị hoặc trường client tự khai không chứng minh khóa được bảo vệ bằng phần cứng.

### Một thiết bị có thể có nhiều khóa

Có thể tách khóa theo mục đích:

- Khóa thiết bị để chứng minh device identity;
- Khóa client certificate cho mTLS;
- Khóa passkey để xác thực người dùng qua WebAuthn;
- Khóa ký dữ liệu hoặc mã hóa cục bộ.

Không nên tái sử dụng một private key cho nhiều giao thức/mục đích nếu policy hoặc chuẩn không yêu cầu. Phân tách giúp giới hạn tác động khi một credential bị lộ hoặc cần thu hồi.

## 6. Challenge-response và proof of possession

Sau enrollment, server cần xác minh thiết bị đang kiểm soát private key tương ứng với public key đã đăng ký. Không nên chỉ dựa vào device ID, serial number hoặc chuỗi định danh do client gửi.

### Luồng challenge-response

1. Client yêu cầu xác thực thiết bị.
2. Server tạo nonce/challenge ngẫu nhiên, có thời hạn và gắn với request, device record, tenant và mục đích.
3. Server trả challenge cho client.
4. Thiết bị ký một thông điệp có cấu trúc chứa challenge cùng context cần thiết.
5. Client gửi chữ ký, key ID và transaction reference về server.
6. Server xác minh chữ ký bằng public key đã đăng ký.
7. Server kiểm tra challenge chưa hết hạn/chưa dùng, đúng device/tenant/purpose và tiêu thụ challenge một cách atomic.
8. Server tiếp tục kiểm tra trạng thái thiết bị và authorization.

### Nội dung cần ràng buộc trong thông điệp ký

- Challenge ngẫu nhiên do server tạo;
- Device credential/key identifier;
- Audience hoặc service nhận proof;
- HTTP method/path hoặc transaction/action nếu proof gắn với request;
- Timestamp/expiry nếu giao thức yêu cầu;
- Tenant/account context lấy từ server;
- Version/algorithm hoặc domain separator để tránh dùng proof ở giao thức khác.

### Pseudocode minh họa

`````````
verifyDeviceProof(deviceId, challengeId, signedPayload, signature):
    device = loadDeviceFromTrustedRegistry(deviceId)
    require(device.status == ACTIVE)
    require(device.tenantId == request.tenantId)

    challenge = loadPendingChallenge(challengeId)
    require(challenge.deviceId == device.id)
    require(challenge.purpose == expectedPurpose)
    require(not challenge.expired)
    require(not challenge.consumed)
    require(payloadBindsChallengeAndRequest(signedPayload, challenge, request))
    require(verifySignature(device.publicKey, signedPayload, signature))

    consumeChallengeAtomically(challenge)
    require(devicePolicyAllowsCurrentUse(device))
    return DEVICE_AUTHENTICATED(device.id)
`````````

Đây là pseudocode khái niệm. Giao thức thật cần dùng serialization và thuật toán chữ ký chuẩn, xử lý canonicalization, domain separation, nonce và replay đúng cách. Không tự thiết kế một giao thức mật mã mới để thay thế chuẩn đã được kiểm chứng.

## 7. Attestation: thiết bị chứng minh điều gì?

**Attestation** là bằng chứng được một thành phần tin cậy ký để mô tả thuộc tính của khóa, authenticator, phần cứng hoặc trạng thái nền tảng. Trong enrollment, attestation có thể giúp server đánh giá liệu khóa được tạo trong TPM/secure hardware hoặc authenticator có đáp ứng policy hay không.

Attestation có thể cung cấp thông tin như:

- Khóa được tạo trong môi trường/phần cứng nào;
- Loại authenticator hoặc model family;
- Chuỗi chứng chỉ và nhà phát hành chứng thực;
- Thuộc tính bảo vệ khóa theo profile;
- Challenge/nonce được gắn với lần attestation cụ thể.

### Attestation không chứng minh mọi điều

Attestation hợp lệ không tự chứng minh:

- Thiết bị chưa từng bị malware hoặc người dùng có quyền quản trị độc hại kiểm soát;
- Hệ điều hành luôn ở trạng thái mới nhất;
- Người đang dùng thiết bị là chủ tài khoản;
- Thiết bị không bị mất hoặc chia sẻ;
- Mọi ứng dụng trên thiết bị đều an toàn;
- Thiết bị luôn compliant trong mọi request tương lai.

Attestation là một tín hiệu có phạm vi. Nó cần được kết hợp với xác thực người dùng, quản lý thiết bị, trạng thái runtime, session risk và authorization.

### Quy trình kiểm tra attestation

1. Chỉ chấp nhận format/profile attestation được cấu hình.
2. Xác minh chữ ký và chuỗi chứng chỉ tới trust anchor đã phê duyệt.
3. Kiểm tra nonce/challenge khớp enrollment transaction.
4. Kiểm tra thời hạn, trạng thái thu hồi và chính sách chứng chỉ nếu áp dụng.
5. Đánh giá model/AAGUID/attestation type hoặc thuộc tính phần cứng theo policy.
6. Kiểm tra format và version; từ chối dữ liệu thiếu hoặc sai cấu trúc.
7. Lưu kết quả đánh giá và metadata cần thiết, không lưu dữ liệu vượt mục đích.

### Quyền riêng tư của attestation

Một số dạng attestation có thể cho phép liên kết nhiều lần đăng ký với cùng một thiết bị hoặc một khóa gốc. Điều này có thể tạo rủi ro theo dõi người dùng. Ưu tiên loại attestation và mức chi tiết phù hợp mục tiêu bảo mật; không yêu cầu unique device identifier toàn cục nếu không cần.

## 8. Device certificate và PKI

Một tổ chức có thể cấp **device certificate** cho thiết bị sau enrollment. Chứng chỉ liên kết public key với một định danh thiết bị hoặc principal theo chính sách của Certificate Authority (CA).

### Luồng cấp chứng chỉ

1. Thiết bị tạo key pair tại nơi lưu khóa phù hợp.
2. Thiết bị tạo Certificate Signing Request (CSR) chứa public key và subject/attributes được phép.
3. Enrollment service xác minh user, tenant, device và policy.
4. CA hoặc certificate service phát hành chứng chỉ theo template/profile đã phê duyệt.
5. Thiết bị cài chứng chỉ và giữ private key tương ứng.
6. Khi dùng mTLS, client chứng minh quyền giữ private key bằng handshake TLS.
7. Resource server kiểm tra certificate chain, EKU, SAN, thời hạn, issuer và trạng thái thu hồi theo policy.

### Device certificate không phải chứng chỉ người dùng

Chứng chỉ thiết bị chứng minh danh tính khóa/thiết bị theo CA đã cấp. Nếu ứng dụng cần biết user nào đang thao tác, vẫn cần xác thực user hoặc một cơ chế delegation rõ ràng. Một laptop dùng chung có thể có một device certificate nhưng nhiều người dùng khác nhau.

### Certificate lifecycle

- Phát hành và cài đặt;
- Gia hạn/rotation trước expiry;
- Thu hồi khi mất thiết bị, compromise hoặc offboarding;
- Cập nhật trust store/CA;
- Kiểm tra CRL/OCSP hoặc cơ chế trạng thái tương ứng;
- Xử lý chứng chỉ hết hạn và private key bị xóa;
- Audit mọi thao tác cấp, gia hạn và thu hồi.

Không dùng serial number hoặc subject DN làm danh tính duy nhất nếu hệ thống không bảo đảm tính duy nhất và namespace. Nên lưu certificate fingerprint, issuer/serial, device record và trạng thái cùng nhau.

## 9. Managed device, BYOD và thiết bị dùng chung

Chính sách enrollment nên phản ánh quyền sở hữu và mức quản lý thực tế.

| Loại thiết bị | Mô hình | Kiểm soát phù hợp |
| --- | --- | --- |
| **Corporate-managed** | Tổ chức sở hữu hoặc quản lý bằng MDM/UEM | Device certificate, compliance, encryption, screen lock, remote wipe theo policy |
| **BYOD** | Nhân viên sở hữu thiết bị cá nhân | Phân vùng dữ liệu công việc, hạn chế thu thập dữ liệu cá nhân, selective wipe, điều kiện truy cập rõ |
| **Shared/kiosk** | Nhiều người dùng dùng chung thiết bị | User authentication riêng từng người, session isolation, khóa thiết bị và auto logout |
| **Contractor device** | Thiết bị của đối tác/nhà thầu | Access scope và thời hạn giới hạn, tenant/resource riêng, offboarding rõ |
| **Unmanaged device** | Không có MDM hoặc không cung cấp compliance evidence | Giới hạn tài nguyên, step-up hoặc từ chối theo risk policy |

### MDM/UEM enrollment

MDM/UEM có thể cung cấp:

- Inventory và device ownership;
- OS version, patch level hoặc compliance state;
- Screen lock, disk encryption và cấu hình bảo mật;
- Certificate/profile deployment;
- Remote lock/wipe hoặc selective wipe;
- Disable thiết bị và báo trạng thái về policy engine.

RP cần xác định nguồn MDM nào có thẩm quyền cho tenant và cách nhận trạng thái. Không tin một trường managed=true do client tự gửi. Nếu dùng attestation/compliance API, cần xác minh chữ ký, audience, freshness và ràng buộc device/account.

### BYOD và quyền riêng tư

Với BYOD, tổ chức nên thu thập ít dữ liệu nhất đủ để đưa ra quyết định bảo mật. Phân biệt dữ liệu thiết bị công việc và dữ liệu cá nhân; giải thích rõ dữ liệu nào được đọc, lưu, xóa và trong hoàn cảnh nào. Remote wipe nên giới hạn theo vùng dữ liệu công việc nếu nền tảng hỗ trợ.

## 10. Liên kết thiết bị với người dùng và tổ chức

Device record cần có định danh nội bộ ổn định và liên kết rõ với owner/tenant. Tránh dùng serial number, hostname hoặc tên do người dùng đặt làm bằng chứng xác thực.

### Metadata gợi ý

`````````yaml
device:
  device_id: dev-7f31
  tenant_id: tenant-42
  owner_account_id: account-1042
  credential:
    key_id: device-key-91
    public_key_thumbprint: sha256:example-fingerprint
    key_protection: hardware_backed
  management:
    state: managed
    provider_id: corporate-mdm
  enrollment:
    transaction_id: enroll-2d81
    enrolled_at: "2026-11-22T06:00:00Z"
  status: active
`````````

Đây là metadata minh họa. Không lưu private key hoặc secret thiết bị trong registry. Các thuộc tính như hostname, model, serial và OS version có thể hỗ trợ inventory nhưng không tự chứng minh device identity.

### Quy tắc binding

- Một device credential thuộc một device record cụ thể;
- Device record thuộc tenant xác định;
- Owner/account được xác minh tại thời điểm enrollment;
- Việc chuyển owner phải có quy trình riêng, audit và step-up;
- Không cho thiết bị của tenant A tự chuyển sang tenant B bằng cách sửa request;
- Có thể hỗ trợ nhiều user trên shared device, nhưng phải tách user identity và device identity;
- Khi credential bị rotate, cập nhật binding có kiểm soát và giữ audit lịch sử.

## 11. Enrollment lifecycle

Device enrollment không phải thao tác một lần rồi quên. Thiết bị và credential cần có trạng thái rõ ràng.

`````````mermaid
stateDiagram-v2
    [*] --> PENDING: Bắt đầu enrollment
    PENDING --> ACTIVE: Xác minh user, key và policy thành công
    PENDING --> REJECTED: Attestation/proof/policy không đạt
    PENDING --> EXPIRED: Enrollment transaction hết hạn
    ACTIVE --> SUSPENDED: Tạm ngừng do risk/compliance
    ACTIVE --> LOST: Người dùng báo mất thiết bị
    ACTIVE --> REVOKED: Thu hồi vĩnh viễn
    SUSPENDED --> ACTIVE: Đánh giá lại và cho phép
    SUSPENDED --> REVOKED: Không còn đáp ứng policy
    LOST --> REVOKED: Xác nhận mất hoặc compromise
    LOST --> ACTIVE: Khôi phục sau xác minh và đánh giá
    REJECTED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
`````````

Ý nghĩa trạng thái:

| Trạng thái | Hành vi |
| --- | --- |
| **PENDING** | Chưa được dùng để cấp quyền; chờ xác minh và phê duyệt |
| **ACTIVE** | Có thể chứng minh device credential và tiếp tục qua policy |
| **SUSPENDED** | Tạm từ chối hoặc giới hạn truy cập trong khi đánh giá |
| **LOST** | Được báo mất; chặn hoặc hạn chế ngay theo policy |
| **REJECTED** | Enrollment không đạt điều kiện |
| **EXPIRED** | Transaction chưa hoàn tất trong thời hạn |
| **REVOKED** | Credential/device không còn được chấp nhận |

Không tái sử dụng record REVOKED cho một thiết bị mới. Enrollment mới nên tạo transaction và credential mới, giữ lịch sử để audit.

## 12. Xác thực thiết bị trong mỗi lần truy cập

Sau enrollment, hệ thống có thể yêu cầu bằng chứng thiết bị ở một số request hoặc phiên. Có nhiều mức:

- **Device credential proof:** ký challenge mới bằng private key;
- **mTLS:** client certificate chứng minh quyền giữ khóa trong TLS handshake;
- **Device-bound token:** token được ràng buộc với khóa thiết bị theo profile/giao thức hỗ trợ;
- **Managed-device assertion:** MDM/attestation service cung cấp bằng chứng compliance có chữ ký;
- **Risk signal:** OS version, network, location hoặc behavioral signals hỗ trợ đánh giá.

Các bằng chứng này không tương đương. mTLS chứng minh client kiểm soát khóa chứng chỉ ở thời điểm handshake; nó không tự chứng minh người dùng đang hoạt động hoặc thiết bị vẫn compliant. Device compliance assertion cần được kiểm tra nguồn, audience, thời gian và device binding.

### Không dùng một lần enrollment thay cho kiểm tra hiện tại

Một laptop được enrollment tháng trước có thể đã bị mất hôm qua hoặc bị gỡ khỏi MDM sáng nay. Resource server cần dùng trạng thái hiện hành hoặc cache có thời hạn phù hợp với rủi ro.

Đối với thao tác nhạy cảm, có thể yêu cầu:

1. User reauthentication/step-up;
2. Device proof mới;
3. Compliance evidence còn freshness;
4. Authorization theo tenant/resource;
5. Risk evaluation và transaction confirmation.

## 13. Thu hồi, mất thiết bị và khôi phục

Khi thiết bị bị mất hoặc nghi bị compromise, mục tiêu đầu tiên là ngăn credential tiếp tục được chấp nhận.

### Quy trình mất thiết bị

1. Người dùng hoặc quản trị viên báo mất thiết bị qua kênh đã xác minh.
2. Đánh dấu device record LOST/SUSPENDED tại nguồn có thẩm quyền.
3. Thu hồi device certificate hoặc credential nếu cần.
4. Thu hồi session, refresh token và token/device binding liên quan.
5. Gửi lệnh lock/wipe qua MDM nếu phù hợp và được phép.
6. Kiểm tra audit từ thời điểm nghi mất: login, API, thay đổi recovery, đăng ký thiết bị mới.
7. Thông báo cho người dùng và chủ sở hữu tổ chức.
8. Nếu cần thiết bị thay thế, chạy enrollment mới sau khi xác minh user và policy.

### Thu hồi có propagation

Một device có thể được cache ở gateway, API, token verifier hoặc policy engine. Cần đo thời gian từ lúc revoke được commit tới khi mọi điểm thực thi từ chối proof của thiết bị.

Với certificate, xử lý CRL/OCSP hoặc cơ chế revocation tương ứng. Với public key registry, cần cập nhật trạng thái và vô hiệu hóa cache. Không coi việc xóa thiết bị khỏi UI quản trị là đã thu hồi toàn bộ quyền.

### Recovery

Người dùng mất thiết bị không nên được phép đăng ký thiết bị mới chỉ bằng một email dễ bị chiếm. Quy trình recovery có thể yêu cầu:

- Passkey/credential dự phòng;
- Xác minh lại qua IdP doanh nghiệp;
- Helpdesk với kiểm tra danh tính và phê duyệt độc lập;
- Quản trị viên tenant xác nhận theo policy;
- Thời gian chờ, cảnh báo và giới hạn giao dịch sau recovery.

Recovery phải có assurance tương xứng với enrollment ban đầu. Sau recovery, đánh giá credential cũ, session cũ và thiết bị đã mất; không tự động kích hoạt lại credential chưa được xác minh.

## 14. Thay đổi thiết bị, rotation và chuyển quyền sở hữu

### Thay khóa

Private key có thể cần thay khi:

- Thiết bị đổi phần cứng hoặc cài lại OS;
- Khóa hết vòng đời hoặc thuật toán bị suy yếu;
- Chứng chỉ sắp hết hạn;
- Khóa có dấu hiệu bị lộ;
- Policy yêu cầu rotation định kỳ.

Quy trình rotation nên xác minh thiết bị/owner hiện tại, tạo key pair mới, xác minh proof/attestation, cập nhật public key/certificate và thu hồi khóa cũ. Nếu khóa cũ bị compromise, không giữ overlap chỉ để tiện chuyển đổi.

### Chuyển thiết bị sang người dùng khác

Đối với laptop dùng chung hoặc chuyển nhân viên:

1. Kết thúc session và xóa dữ liệu/credential thuộc người dùng cũ theo policy;
2. Thu hồi hoặc xóa device-user binding cũ;
3. Xử lý certificate và key cũ;
4. Kiểm tra MDM ownership/compliance;
5. Tạo binding mới sau khi xác minh người dùng mới;
6. Lưu audit cả hành động gỡ liên kết và đăng ký mới.

Không đổi owner ID trên record cũ mà không có bằng chứng. Việc chuyển thiết bị là một sự kiện bảo mật, không chỉ là chỉnh sửa inventory.

## 15. Tín hiệu thiết bị và quyết định risk-based

Một policy engine có thể kết hợp nhiều tín hiệu:

| Tín hiệu | Có thể cho biết | Không chứng minh |
| --- | --- | --- |
| Device key proof | Client đang kiểm soát private key đã đăng ký | Người dùng cụ thể đang thao tác |
| Hardware-backed key attestation | Khóa được tạo/giữ trong môi trường đáp ứng profile | Thiết bị hoàn toàn không bị compromise |
| MDM managed/compliant | Thiết bị đáp ứng trạng thái do MDM báo | Mọi ứng dụng và request đều an toàn |
| OS version/patch level | Mức cập nhật được báo | Không có lỗ hổng chưa vá |
| Screen lock/encryption | Một số kiểm soát nền tảng đang bật | Không có malware hoặc session theft |
| Network/IP reputation | Ngữ cảnh kết nối | Danh tính thiết bị hoặc người dùng |
| Device age/last seen | Lịch sử sử dụng | Thiết bị hiện còn thuộc người dùng |
| Location signal | Tín hiệu rủi ro theo ngữ cảnh | Vị trí chính xác hoặc bằng chứng danh tính |

### Ví dụ policy

`````````
authorizeSensitiveAction(user, device, request):
    require(user.accountStatus == ACTIVE)
    require(user.hasPermission(request.action, request.resource))
    require(device.status == ACTIVE)
    require(device.tenantId == user.tenantId)
    require(device.proofFreshAndValid)
    require(device.complianceState == COMPLIANT)
    require(stepUpSatisfiedFor(request.action))
    return ALLOW
`````````

Đây là pseudocode minh họa. Thực tế cần xác định nguồn dữ liệu, freshness, xử lý lỗi MDM và cách đánh giá risk. Nếu compliance service tạm thời không phản hồi, hành vi phải được quy định rõ theo mức rủi ro; không mặc định một tín hiệu cũ vẫn còn hợp lệ vô thời hạn.

## 16. Threat model: tấn công enrollment và device identity

| Rủi ro | Mô tả | Kiểm soát |
| --- | --- | --- |
| **Unauthorized enrollment** | Attacker chiếm session rồi thêm thiết bị của mình | Step-up, transaction binding, notification, rate limit |
| **Enrollment CSRF** | Browser bị dụ khởi tạo hoặc xác nhận enrollment | CSRF protection, state, user confirmation |
| **Device impersonation** | Client giả device ID/serial/hostname | Challenge-response bằng private key |
| **Key extraction** | Private key bị sao chép khỏi thiết bị | Hardware-backed non-exportable key khi phù hợp, OS protection |
| **Attestation forgery/replay** | Attestation giả hoặc dùng lại bằng chứng cũ | Trust chain, nonce, expiry, profile validation |
| **Tenant mix-up** | Thiết bị được gắn vào tenant khác | Tenant context server-side và unique binding |
| **Stale compliance** | Dùng trạng thái MDM cũ để cấp quyền | Freshness, signed assertion, re-evaluation |
| **Lost device** | Kẻ nhặt được thiết bị tiếp tục dùng session/key | Revoke, remote lock/wipe, short session, user verification |
| **Shared-device leakage** | User trước để lại session/data cho user sau | Session isolation, auto logout, per-user binding |
| **Certificate misuse** | Device certificate bị dùng để giả danh user | Tách device identity và user identity |
| **Weak recovery** | Email/helpdesk yếu hơn enrollment | Recovery assurance, dual control, alerts |
| **Revocation delay** | Cache/gateway vẫn chấp nhận credential đã revoke | SLA, invalidation, post-revoke monitoring |
| **Privacy overcollection** | Thu thập serial/location/attestation quá mức | Data minimization, transparency, retention |

### Giới hạn tin cậy

Thiết bị có thể bị compromise sau khi enrollment. Hardware-backed key làm khó việc trích xuất private key nhưng không ngăn attacker điều khiển thiết bị để yêu cầu ký trong lúc thiết bị đang mở khóa hoặc bị chiếm quyền. Vì vậy, cần kết hợp user verification, session controls, device compliance và authorization.

## 17. Tình huống thiết kế: nhân viên đăng ký điện thoại mới

Nhân viên Mai đang dùng cổng nội bộ trên laptop công ty. Cô muốn thêm điện thoại cá nhân để phê duyệt đăng nhập và nhận thông báo. Cổng cần xác minh người dùng, liên kết điện thoại với đúng tenant và có thể thu hồi khi điện thoại bị mất.

### Thiết kế chưa an toàn

1. Cổng gửi link email; ai mở link cũng có thể thêm thiết bị.
2. Ứng dụng lấy model, serial và device name do client gửi rồi coi đó là danh tính thiết bị.
3. Server không tạo challenge, chỉ lưu public key nhận được.
4. Thiết bị được đánh dấu managed dù không có MDM evidence.
5. Khi Mai báo mất điện thoại, chỉ xóa tên thiết bị khỏi giao diện; API vẫn chấp nhận public key.

### Thiết kế lại

1. Mai đăng nhập bằng passkey trên laptop và thực hiện step-up.
2. Server tạo enrollment transaction gắn account, tenant, purpose và thời hạn.
3. Điện thoại tạo key pair; private key được giữ trong keystore phù hợp.
4. Điện thoại ký challenge enrollment; nếu policy yêu cầu, gửi attestation có nonce.
5. Enrollment service xác minh proof, attestation và trạng thái account/tenant.
6. Server lưu public key, key ID, device record và trạng thái **BYOD**; không gán managed nếu chưa có MDM.
7. Cổng hiển thị thông tin nhận diện phù hợp và gửi thông báo thiết bị mới.
8. Mỗi lần cần device proof, server tạo challenge mới và xác minh chữ ký; thao tác nhạy cảm vẫn yêu cầu user step-up.
9. Khi Mai báo mất điện thoại, server đánh dấu LOST, revoke key/session và kiểm tra propagation tới API.
10. Điện thoại thay thế phải chạy enrollment mới; credential cũ không được tự kích hoạt lại.

### Kết quả mong đợi

- Chỉ Mai sau khi xác minh mới có thể thêm thiết bị vào account của mình;
- Device record gắn đúng tenant và owner;
- Server xác minh quyền giữ private key, không tin device ID do client khai;
- Trạng thái BYOD được phân biệt với managed/compliant;
- Attestation chỉ được dùng trong phạm vi policy đã định;
- Mất thiết bị làm credential/session cũ bị từ chối theo SLA;
- Audit không chứa private key, token hoặc dữ liệu cá nhân không cần thiết.

## 18. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Enrollment hợp lệ** | User đã xác thực, key proof hợp lệ | Tạo device record ACTIVE theo policy |
| **User chưa xác thực** | Gửi yêu cầu enrollment không có transaction hợp lệ | Từ chối |
| **Step-up thiếu** | Tài khoản rủi ro cao thêm thiết bị mà không reauthenticate | Từ chối hoặc yêu cầu step-up |
| **Challenge sai** | Ký challenge không thuộc transaction | Từ chối |
| **Challenge replay** | Gửi lại proof đã dùng | Từ chối |
| **Challenge hết hạn** | Gửi proof sau TTL | Từ chối |
| **Sai tenant** | Sửa tenant ID trong request | Server dùng binding đã lưu và từ chối |
| **Sai owner** | Dùng credential thuộc account khác | Từ chối |
| **Public key thay đổi** | Gửi proof bằng khóa khác với registry | Từ chối |
| **Private key unavailable** | Thiết bị không thể chứng minh possession | Từ chối |
| **Attestation nonce sai** | Attestation không gắn challenge hiện tại | Từ chối nếu policy yêu cầu attestation |
| **Attestation chain không tin cậy** | Dùng certificate chain ngoài trust store | Từ chối hoặc hạ mức theo policy được phê duyệt |
| **Attestation absent** | Thiết bị không hỗ trợ attestation | Xử lý đúng nhánh policy, không tự gán hardware-backed |
| **MDM state spoofing** | Client tự gửi managed=true | Bỏ qua; chỉ dùng nguồn MDM đã xác minh |
| **Stale compliance** | Assertion compliance đã hết hạn | Yêu cầu refresh hoặc từ chối theo policy |
| **Device suspended** | Gửi proof từ thiết bị SUSPENDED | Từ chối hoặc giới hạn theo policy |
| **Device revoked** | Gửi proof từ thiết bị REVOKED | Từ chối tại mọi resource server |
| **Lost device** | Báo mất rồi tiếp tục gọi API | Credential/session bị chặn theo SLA |
| **Shared device** | User A logout, User B đăng nhập | Không đọc được session/dữ liệu của A |
| **Owner transfer** | Đổi owner mà không có quy trình | Từ chối và audit |
| **Key rotation** | Thêm khóa mới rồi thu hồi khóa cũ | Khóa mới hoạt động; khóa cũ bị từ chối sau mốc |
| **Certificate expiry** | Dùng certificate hết hạn | mTLS/certificate validation từ chối |
| **Certificate revoked** | Dùng certificate đã thu hồi | Từ chối theo revocation policy |
| **Enrollment flood** | Tạo nhiều yêu cầu liên tục | Rate limit và alert |
| **Audit redaction** | Kiểm tra application/MDM/audit logs | Không có private key, token, secret hoặc attestation payload nhạy cảm không cần thiết |
| **Recovery** | Mất thiết bị và đăng ký thiết bị thay thế | Chỉ hoàn tất sau recovery assurance và audit |

Kiểm thử nên bao gồm cả enrollment API, device registry, policy engine, gateway và resource server. Chỉ kiểm tra giao diện hiển thị thiết bị mới không chứng minh thiết bị đã được xác minh hoặc thu hồi thực sự.

## 19. Audit, giám sát và chỉ số vận hành

Enrollment cần có audit cho cả thay đổi quản trị và hành vi sử dụng thiết bị.

| Event | Trường dữ liệu gợi ý |
| --- | --- |
| device.enrollment.started | Transaction ID, actor/account reference, tenant, purpose |
| device.enrollment.approved | Device ID, owner, approver, policy version |
| device.enrollment.rejected | Reason code: challenge, attestation, tenant, account, policy |
| device.credential.created | Key ID, public key thumbprint, algorithm, protection level |
| device.certificate.issued/renewed | Certificate fingerprint, issuer, serial, expiry |
| device.status.changed | Old/new state, actor, reason, timestamp |
| device.proof.succeeded/failed | Device reference, request ID, reason code, freshness |
| device.compliance.changed | Management provider, compliance version/state, observed time |
| device.owner.changed | Old/new owner reference, approver, transaction |
| device.revoked | Credential reference, actor, reason, propagation status |
| device.recovery.completed | Recovery method reference, new device reference, approval |

Không ghi private key, secret, raw access token, session cookie hoặc toàn bộ attestation payload nếu không cần. Device serial, hostname, IP và location có thể là dữ liệu nhạy cảm; giới hạn quyền truy cập và retention.

### Chỉ số nên theo dõi

- **Active device inventory:** số thiết bị ACTIVE theo tenant, owner, platform và management state;
- **Unowned device count:** thiết bị không có owner chịu trách nhiệm;
- **Enrollment completion/failure rate:** tỷ lệ hoàn tất và lý do thất bại;
- **Unauthorized enrollment attempts:** yêu cầu bị từ chối do user/tenant/step-up không hợp lệ;
- **Attestation rejection rate:** phân loại lỗi trust chain, nonce, format hoặc policy;
- **Hardware-backed key coverage:** tỷ lệ credential đáp ứng yêu cầu phần cứng trong nhóm policy tương ứng;
- **Compliance freshness:** tỷ lệ thiết bị có compliance evidence còn mới;
- **Device proof failure rate:** số lần proof không hợp lệ hoặc replay;
- **Revocation propagation latency:** thời gian từ commit revoke tới mọi điểm thực thi từ chối;
- **Post-revocation accepted requests:** request vẫn được chấp nhận sau mốc revoke có hiệu lực;
- **Lost-device response time:** thời gian từ báo mất tới chặn credential/session;
- **Recovery abuse rate:** số recovery bất thường hoặc cần ngoại lệ.

Không tối ưu riêng số lượng thiết bị enrolled hoặc completion rate. Một hệ thống có nhiều thiết bị đăng ký nhưng thiếu owner, không thu hồi được khóa hoặc chấp nhận compliance cũ vẫn có rủi ro lớn.

## 20. Checklist triển khai Device enrollment

- **Identity bootstrap:** User được xác thực đủ mạnh trước khi thêm thiết bị?
- **Tenant binding:** Tenant và account được xác định từ server-side context?
- **Transaction:** Enrollment có challenge, transaction ID, expiry, purpose binding và single-use?
- **Key generation:** Private key được tạo bằng CSPRNG/keystore phù hợp và không gửi lên server?
- **Key protection:** Policy có phân biệt hardware-backed và software-backed?
- **Attestation:** Trust anchor, nonce, format, certificate chain và privacy được xử lý rõ?
- **Certificate:** CSR, CA profile, EKU/SAN, expiry, renewal và revocation có quy trình?
- **MDM/UEM:** Managed/compliant lấy từ nguồn có thẩm quyền, có chữ ký/freshness?
- **Device registry:** Device ID, owner, tenant, key/certificate, status và lịch sử được lưu nhất quán?
- **Proof of possession:** Challenge-response ràng buộc request, audience, purpose và chống replay?
- **User/device separation:** Device proof không thay user authentication hoặc authorization?
- **Lifecycle:** Pending, active, suspended, lost, rejected, expired và revoked có semantics rõ?
- **Recovery:** Mất thiết bị có recovery đủ mạnh và enrollment mới?
- **Offboarding:** Disable account/tenant có thu hồi session, credential, certificate và quyền?
- **Privacy:** BYOD và attestation chỉ thu thập dữ liệu cần thiết?
- **Monitoring:** Có owner inventory, compliance freshness, revocation latency và alert?
- **Testing:** Đã thử enrollment trái phép, challenge replay, tenant mix-up, attestation sai, lost device và propagation?

### Câu hỏi tự kiểm tra

1. Device enrollment khác credential enrollment và MDM enrollment như thế nào?
2. Vì sao device ID hoặc serial number do client gửi không đủ để chứng minh thiết bị?
3. Challenge-response chứng minh điều gì về private key?
4. Attestation có thể chứng minh thuộc tính nào và không chứng minh được điều gì?
5. Device certificate khác user certificate ở mục đích và cách dùng nào?
6. Vì sao một thiết bị đã enrollment vẫn cần kiểm tra compliance và trạng thái hiện tại?
7. Khi mất thiết bị, vì sao chỉ xóa record khỏi UI là chưa đủ?
8. Làm thế nào để hỗ trợ BYOD mà không thu thập quá mức dữ liệu cá nhân?
9. Vì sao device proof không thay thế xác thực người dùng?
10. Cần đo chỉ số nào để biết revocation đã lan tới mọi resource server?

## Kết luận

**Device enrollment thiết lập mối liên kết có thể kiểm chứng giữa thiết bị, credential, người dùng và tổ chức.** Một quy trình an toàn xác minh người dùng trước khi thêm thiết bị, tạo khóa phù hợp, kiểm tra proof of possession và attestation theo policy, lưu device record có tenant/owner rõ ràng, rồi đánh giá compliance và trạng thái thiết bị trong suốt vòng đời. Device certificate, MDM enrollment và passkey có vai trò khác nhau; không nên dùng một tín hiệu để thay thế mọi lớp tin cậy. Khi thiết bị mất, đổi owner hoặc bị compromise, hệ thống phải thu hồi khóa, certificate, session và quyền ở mọi điểm thực thi theo thời hạn đo được. Enrollment chỉ là điểm bắt đầu của quản lý niềm tin thiết bị; quyền truy cập vẫn cần xác thực người dùng, authorization và đánh giá rủi ro ở thời điểm sử dụng.
