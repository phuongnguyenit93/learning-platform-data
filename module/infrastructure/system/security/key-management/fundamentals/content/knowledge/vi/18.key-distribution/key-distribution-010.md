# Không gửi key qua plaintext channel (Không phân phối khóa mật mã qua kênh truyền không được bảo vệ)

## 1. Tại sao không được gửi khóa qua kênh plaintext?

**Key distribution (phân phối khóa)** là quá trình đưa **khóa mật mã hoặc khả năng sử dụng khóa** đến đúng thực thể được ủy quyền. Nếu một **khóa bí mật** đi qua kênh truyền không có bảo vệ thích hợp, người nghe lén, một thành phần trung gian hoặc người quản trị sai phạm có thể sao chép khóa rồi dùng nó để giải mã dữ liệu hoặc giả mạo thông điệp.

Một khóa **AES-256** được sinh từ CSPRNG đáng tin vẫn mất khả năng bảo vệ nếu ứng dụng gửi 32 byte khóa đó qua HTTP không mã hóa. Mật mã của dữ liệu có thể hoàn toàn đúng, nhưng **đường cấp phát khóa** tạo ra điểm thất bại.

Ví dụ sai:

~~~text
Service A -- HTTP plaintext:
  POST /keys/distribute
  {
    "tenant": "shop-42",
    "aesKeyBase64": "BASE64_SECRET_KEY"
  }
                         --> Service B
              ^
              |
       Người có thể đọc lưu lượng mạng
       hoặc bản ghi proxy thấy secret
~~~

**Base64/hex/JSON là mã hóa biểu diễn (encoding), không bảo vệ bí mật**. Đổi key thành một chuỗi có vẻ dài hoặc chia thành nhiều phần không biến HTTP plaintext thành kênh bí mật.

Trong chương **Key distribution** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, quy tắc **Không gửi key qua plaintext channel** nối trực tiếp việc **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa** với **TLS/mTLS, KMS/HSM, envelope encryption, IAM, chữ ký số, kiểm toán và ứng phó sự cố**.

**Nguyên tắc cốt lõi:** Secret key chỉ được cấp phát tới **đúng bên nhận đã được xác thực và có quyền**, thông qua một **kênh bảo mật thích hợp hoặc một vật liệu đã được bọc/mã hóa cho bên nhận**, kèm kiểm soát toàn bộ điểm cuối, logging và vòng đời.

## 2. Phân loại thông tin trước khi quyết định có thể truyền gì

Không phải mọi dữ liệu chứa chữ **key** đều phải được giữ bí mật.

| Thông tin | Có phải secret? | Lưu ý khi truyền |
|---|---|---|
| **Plaintext DEK** | Có | Chỉ tới workload đã được phép, hạn chế export; ưu tiên wrapped DEK/KMS |
| **Plaintext KEK / master key** | Rất nhạy cảm | Thường không được đưa ra ngoài KMS/HSM; cần quy trình đặc biệt nếu export/import |
| **Private signing key** | Có | Không gửi dạng rõ; ưu tiên tạo, giữ và dùng trong HSM/KMS |
| **HMAC key / PSK** | Có | Cần kênh bí mật và xác thực đúng hai đầu, quản lý scope/replay |
| **Recovery secret / key share** | Có | Bảo vệ theo quyền, dual control/split knowledge tùy mô hình |
| **Password / KDF secret** | Có | Không đặt trong URL, log hoặc message queue công khai |
| **Encrypted/wrapped DEK** | Không phải DEK dạng rõ | Có thể đi cùng ciphertext, nhưng vẫn cần bảo vệ tính toàn vẹn, scope và metadata |
| **KMS key reference / alias / key ID** | Thường không | Không phải token cấp quyền; vẫn có thể nhạy cảm về hạ tầng |
| **Public key** | Không | **Phải xác thực danh tính/ràng buộc trust** để tránh bị tráo key |
| **Certificate/JWKS** | Chủ yếu công khai | Kiểm tra CA/issuer, chain, policy, rotation và trust source |
| **Nonce/IV/AEAD tag** | Thường không | Nonce phải dùng đúng quy tắc; tag phải được verify |

**Phân biệt quan trọng:** Không được gửi **private key** dạng rõ, nhưng có thể **phân phối public verification key công khai**. Với public key, vấn đề chính thường là **xác thực người sở hữu và ngăn thay thế**, không phải giấu bytes.

### 2.1. Khóa không nên “chuyển đi” khi có cách tránh

Trong nhiều hệ thống, tốt hơn là **không export plaintext KEK/private key**:

- Client gửi dữ liệu cần Sign tới HSM theo API đã xác thực, HSM trả chữ ký; private key không rời HSM.
- Ứng dụng yêu cầu KMS bọc/giải bọc DEK, còn KEK vẫn nằm trong KMS.
- Hai đầu phiên mạng thực hiện authenticated key agreement để có traffic keys riêng, thay vì gửi sẵn khóa phiên qua mạng.

**Hạn chế việc có một bản sao khóa mới** thường giảm rủi ro hơn chỉ mã hóa thêm một đường truyền.

## 3. “Plaintext channel” được hiểu như thế nào?

Một **plaintext channel** là con đường truyền hoặc chia sẻ mà **nội dung bí mật có thể bị đọc bởi những thành phần không được ủy quyền**, hoặc không có biện pháp xác thực/tính toàn vẹn cần thiết.

Những con đường rõ ràng:

- **HTTP** không TLS, kết nối TCP/UDP tự thiết kế gửi key bytes.
- **FTP, Telnet**, message bus hoặc websocket không có bảo vệ cần thiết trên đoạn truyền.
- **Email, chat hoặc ticket** gửi nguyên secret ở dạng text, không có cơ chế bảo mật đầu-cuối/phân quyền tương ứng.
- **URL query string** như tham số secretKey, token; URL có thể xuất hiện trong browser history, proxy, analytics, referer hoặc access logs.
- **Command-line argument, console output, CI job log**, dù không phải gói mạng, vẫn là đường tiết lộ plaintext secret.
- **Clipboard, screenshot, cấu hình public repository, artifact/container image** được chia sẻ cho nhiều bên.
- **Thông điệp queue hoặc event** chứa key rõ, dù network đến broker dùng TLS, nếu nhiều consumer/admin có thể đọc payload.
- **Backup, database dump, trace và crash report** xuất hiện trong chuỗi phân phối thông tin.

### 3.1. Có TLS trên một đoạn không bảo vệ mọi đoạn

~~~mermaid
flowchart LR
    A["App A"] -->|TLS| P["Ingress / API gateway"]
    P -->|HTTP nội bộ không bảo vệ| B["Service B"]
    P --> L["Access / debug logs"]
    X["Operator có quyền xem logs"] --> L
~~~

Khi TLS bị **termination** tại gateway, secret xuất hiện dạng rõ tại gateway và có thể được forward tiếp qua một đoạn khác. Vì vậy cần kiểm tra **end-to-end data flow**, không chỉ hỏi “client có dùng HTTPS không?”.

### 3.2. Kênh được mã hóa chưa chắc là kênh được ủy quyền

Gửi plaintext DEK qua HTTPS tới một máy chủ do attacker điều khiển vẫn là **lộ DEK cho attacker**. HTTPS có thể bảo vệ khỏi nghe lén trên đường nhưng không thay thế câu hỏi **đây có đúng bên nhận, đúng workload, đúng tenant và đúng mục đích không?**

## 4. Mô hình đe dọa trong phân phối khóa

| Đối thủ/điểm lỗi | Năng lực | Nguy cơ | Kiểm soát trọng tâm |
|---|---|---|---|
| Người nghe lén mạng | Đọc traffic plaintext | Sao chép DEK/HMAC/private key | TLS đã xác thực, key wrapping |
| Active MITM | Thay endpoint/gói/key exchange | Đưa public key giả, chiếm secret | Xác thực peer, certificate/identity validation |
| Proxy/log operator | Đọc request body, URL, logs | Lộ key dù TLS ngoài hoạt động | Không log secret, scope quyền, audit |
| Service principal bị chiếm | Dùng quyền nhận/Unwrap secret | Decryption oracle hoặc bulk extraction | IAM tối thiểu, key scope, detection |
| Malicious insider | Tự thêm recipient hoặc export key | Lộ hoặc chia sẻ ngoài policy | SoD, approval, dual control, HSM |
| Storage/broker reader | Đọc queue/object | Đọc key rõ trong payload | Wrapped key + access control |
| CI/CD compromise | Đọc env/secret, sửa pipeline | Secret trong build artifacts | JIT creds, protected pipelines, secret scanning |
| Client endpoint compromise | Đọc RAM/process | Lấy key sau Decrypt | Device hardening, giảm key lifetime |
| Replay attacker | Gửi lại thông điệp phân phối cũ | Cài key cũ, dùng sai epoch | Version, TTL, anti-replay, idempotency |
| Metadata attacker | Tráo recipient/keyRef/context | Cấp sai key hoặc giải mã sai scope | Authenticated metadata, binding, allowlist |

### 4.1. Bảo mật truyền tải có ba yêu cầu khác nhau

1. **Confidentiality:** secret không bị quan sát bởi thực thể không có quyền.
2. **Integrity:** secret/key reference/context không bị chỉnh sửa khi đi qua kênh.
3. **Peer authentication:** sender/recipient được nhận diện đúng theo hệ thống trust.

Ngoài ra **authorization** quyết định dù đã xác thực, principal có được **nhận hoặc sử dụng key này** không. Các yêu cầu này phối hợp với **freshness, anti-replay, audit, key lifecycle và availability**.

### 4.2. Không đủ bằng chứng chỉ vì kiểm thử chức năng pass

Một demo gửi khóa qua HTTP rồi receiver giải mã thành công chứng minh **hai bên nhận cùng key**, không chứng minh người khác không nhìn thấy key.

## 5. Các kênh phân phối: điều gì an toàn, điều gì không?

| Phương thức | Đánh giá | Điều kiện và giới hạn |
|---|---|---|
| **HTTP plaintext chứa key rõ** | **Không dùng** | Người trên đường có thể đọc/chỉnh sửa |
| **TCP custom gửi key rõ** | **Không dùng** | Không có giao thức xác thực/bảo mật chuẩn |
| **HTTPS TLS xác thực đúng peer, kiểm soát IAM** | Có thể chấp nhận theo threat model | Endpoint/proxy/log vẫn thấy key rõ nếu payload chứa key rõ |
| **mTLS giữa hai workload** | Thường mạnh hơn về xác thực workload | mTLS chưa thay business authorization; quản lý client certificates |
| **TLS + wrapped DEK chỉ recipient unwrap được** | Defense in depth tốt | Xác thực recipient key, authenticated wrap và context |
| **KMS/HSM API chỉ trả key reference hoặc phép toán** | Giảm export plaintext | Vẫn cần kiểm soát grants, API misuse và audit |
| **Authenticated ECDHE/TLS session key agreement** | Phù hợp giao thức truyền thông | Không phải phương án phân phối một persistent DEK cho storage |
| **Public key/certificate qua nguồn tin cậy** | Được | Cần certificate validation hoặc out-of-band binding |
| **Private key gửi qua email/chat** | **Không dùng** | Không kiểm soát được bản sao, forwarding, retention |
| **Secret trong URL/query** | **Không dùng** | Dễ xuất hiện trong log/history/analytics |
| **Message queue chứa plaintext key** | Thường không phù hợp | TLS đến broker không hạn chế mọi consumer/admin của broker |
| **Offline key transfer dưới key-wrapping/quorum** | Có thể có trong quy trình đặc biệt | Cần chain of custody, dual control, key origin và audit |

**Không có một giao thức đơn lẻ phù hợp mọi loại khóa.** Phân phối một DEK của object khác với thiết lập traffic key trong TLS, tạo HMAC shared secret cho đối tác, hay đưa private signing key vào HSM.

## 6. TLS: lớp bảo vệ cơ bản khi gửi thông tin nhạy cảm qua mạng

**TLS** là giao thức cung cấp bảo mật kênh truyền khi hai đầu được xác thực và sử dụng cấu hình mạnh. Trong hệ thống hiện đại, **TLS 1.3** thường là lựa chọn được ưu tiên khi các hệ thống liên quan hỗ trợ; một số môi trường còn dùng **TLS 1.2** với cipher suites và cấu hình an toàn phù hợp chính sách.

Những yêu cầu cốt lõi:

- **Không bỏ xác thực certificate chain và hostname/identity**.
- Chỉ dùng protocol versions và cipher suites được phê duyệt.
- Kiểm tra **đúng tên host/endpoint** mà policy cho phép.
- Cân nhắc **mTLS** nếu cả hai workload cần xác thực bằng chứng chỉ.
- Quản lý trust store/CA, expiration, revocation và certificate rotation.
- Chặn chuyển hướng từ HTTPS sang HTTP hoặc sang một endpoint không được duyệt.
- Không đưa secret vào URL, logs hoặc telemetry.
- Chặn bất kỳ network hop nào chuyển về HTTP plaintext khi đang mang key rõ.

### 6.1. TLS bảo vệ đến đâu?

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant N as Network / untrusted transport
    participant B as Authorized Service B
    A->>B: TLS handshake + verify peer identity
    B-->>A: Authenticated secure channel
    A->>N: Encrypted TLS application records
    N->>B: Forward traffic không thấy raw secret
    B->>B: Application nhận plaintext sau TLS
~~~

Sơ đồ khái niệm thể hiện bảo mật **trên đường truyền**. Nó không cam kết receiver không log key, không bị compromise, hoặc luôn được phép nhận key.

### 6.2. Tránh các cách “bỏ qua lỗi TLS”

Không viết **TrustManager chấp nhận mọi certificate**, không tắt **hostname verification**, và không tự tạo SSLContext giả an toàn chỉ để bypass lỗi chứng chỉ ở staging.

Nếu client báo certificate error, phải sửa **trust chain, DNS/hostname, certificates, clocks hoặc cấu hình proxy**, không disable xác thực rồi đem vào production.

### 6.3. Forward secrecy có nghĩa gì?

Các phiên TLS hiện đại với authenticated ephemeral (EC)DHE thường có **forward secrecy**: trong những giả định xác định, lộ private authentication key dài hạn về sau không tự giải mã được những traffic sessions cũ đã ghi lại nếu ephemeral/session secrets không bị lộ.

**Nó không xóa nguy cơ secret đã truyền tới endpoint không đáng tin, bị log, hoặc nằm trong RAM/cache**, cũng không cứu các phiên khi attacker kiểm soát endpoint tại thời điểm truyền.

### 6.4. Không dùng “encryption in transit” làm bằng chứng duy nhất

Một request chứa plaintext KEK qua TLS có thể vẫn vi phạm key export policy. **TLS là điều kiện cần cho nhiều đường truyền, nhưng không phải giấy phép export mọi key**.

## 7. mTLS và xác thực workload

**Mutual TLS (mTLS)** cho phép hai bên trình bày và xác thực danh tính chứng chỉ trong quá trình thiết lập kênh, thường phù hợp giao tiếp microservices hoặc service-to-service trên miền quản lý.

~~~mermaid
flowchart LR
    A["Service A\nworkload identity A"] -->|mTLS| B["Service B\nworkload identity B"]
    B --> P["Authorization policy:\nCan A receive key for tenant X?"]
    P --> K["KMS/HSM unwrap / operation"]
    K --> L["Audit: caller, purpose, keyRef"]
~~~

### 7.1. mTLS không thay phân quyền tài nguyên

mTLS chứng minh client có identity phù hợp với trust policy, **không chứng minh** client được phép lấy mọi DEK. Receiver cần kiểm tra:

- Workload identity nào đã xác thực?
- Scope production/staging, region, tenant nào?
- Có được gọi action **ReceiveWrappedKey/Decrypt/Unwrap** không?
- Key ID/material version có thuộc phạm vi của client không?
- Có approval/incident context khi thực hiện action nhạy cảm không?

### 7.2. Quản lý chứng chỉ và identities

Quy trình phải có certificate issuance/rotation/revocation, trust anchors, client identity mapping và khả năng xử lý expired/revoked credentials. Nếu user có thể tự sửa trust store hoặc phát hành client certificate với quyền không giới hạn, mTLS có thể bị phá từ control plane.

### 7.3. Mesh/sidecar termination

Service mesh dùng mTLS có thể bảo vệ traffic giữa sidecars nhưng traffic **sidecar → ứng dụng** hoặc giữa các proxy khác có thể có ranh giới riêng. Cần đánh giá toàn bộ path cùng quyền đọc logs, socket và container namespaces.

## 8. Public key distribution: không bí mật nhưng bắt buộc đáng tin

Public encryption key và public verification key có thể công khai. Tuy nhiên, nếu attacker **thay public key của người nhận bằng key của họ**, sender có thể wrap DEK cho attacker dù sử dụng một thuật toán mã hóa công khai mạnh.

Ví dụ MITM:

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant M as Attacker / key directory giả
    participant R as Recipient
    S->>M: Yêu cầu public key của Recipient R
    M-->>S: Public key của M, gắn nhãn R
    S->>M: Encrypt/Wrap DEK dưới public key giả
    M->>M: Decrypt DEK bằng private key của M
    Note over R: R chưa nhận đúng DEK
~~~

Do đó cần **binding danh tính ↔ public key** bằng certificate chain đáng tin, issuer policy, authenticated key directory, fingerprint verification qua kênh độc lập hoặc cơ chế giao thức có trust model rõ.

### 8.1. Certificate không chỉ là một file PEM

Một certificate phải được kiểm tra chain, thời gian, identity, key usage, certificate policies (nếu liên quan) và revocation theo yêu cầu. Public key gửi qua HTTP công khai **có thể được tải về** nhưng không mặc nhiên được tin chỉ vì có extension .pem.

### 8.2. JWKS và trường kid

Trong hệ sinh thái JWT, **kid** là hint để chọn key; nó **không phải bằng chứng issuer đáng tin**. Verifier cần kiểm tra issuer, audience, signature algorithm allowlist, nguồn JWKS đáng tin và chính sách rotation. Không tin URL khóa công khai do token chưa xác thực tự chỉ tới nếu policy không cho phép.

### 8.3. Pinning chỉ khi hiểu rủi ro vận hành

Certificate/public-key pinning có thể tăng bảo vệ trong một mô hình cụ thể nhưng tạo rủi ro **mất kết nối khi rotate key/certificate**. Nếu dùng pinning, cần dự phòng, cập nhật và recovery có kiểm soát; không cứng nhắc hard-code một fingerprint duy nhất mà không có kế hoạch thay.

## 9. Không dùng URL, redirect và các kênh phụ làm chỗ giấu secret

Một lỗi phổ biến:

~~~text
GET https://api.example.test/distribute?key=SECRET_BYTES
~~~

Dù URL bắt đầu bằng HTTPS, **query string** có thể bị thu thập bởi proxy logs, browser history, monitoring, analytics, redirect handling hoặc lỗi debug.

### 9.1. Những nơi secret có thể rơi ra ngoài TLS

| Nơi xuất hiện | Rủi ro | Kiểm soát |
|---|---|---|
| HTTP URL/query/path | Logs/history/referrer | Không đặt key/token vào URL |
| Header tùy biến | Reverse proxy/APM có thể log | Mask hoặc không vận chuyển plaintext key nếu tránh được |
| Request/response body | Debug traces, middleware body logging | Cấm log body nhạy cảm, giới hạn quyền |
| Authorization token | Logs/traces có thể copy credential | Redaction, token lifetime/scope, secret scanner |
| Redirect | Có thể gửi payload tới host khác | Disable hoặc allowlist redirect |
| Error/exception | In ra key hoặc buffer | Chỉ dùng error code và correlation ID |
| Service mesh sidecar | Plaintext sau termination | Quyền đọc sidecar/app, secure hop và audit |
| Temporary file/swap | Bản sao secret ngoài RAM | Hạn chế file, memory handling, encrypt-at-rest |
| CI job/build artifacts | Secret biến thành lịch sử lâu dài | JIT secrets, masked logs và artifact policy |

**Không đưa cả ciphertext và plaintext key vào log chung** chỉ để chẩn đoán encryption failures.

### 9.2. Không nhầm “server không nhìn thấy URL” với “URL không rò”

HTTP request line/path/query có thể xuất hiện trong các hệ thống giám sát, truy vết hoặc logs ở nhiều ranh giới. Với browser, URL còn có thể đi vào history và những cơ chế khác. **Secret phải nằm trong đúng giao thức và đúng miền lưu trữ bí mật**, không phải một tham số query.

## 10. TLS và key wrapping là hai lớp bổ sung, không thay nhau

**TLS** bảo vệ đường truyền. **Key wrapping/envelope encryption** bảo vệ key material khi nó được lưu, chuyển qua broker, backup hoặc qua nhiều miền quyền.

~~~mermaid
flowchart TB
    A["Ứng dụng Sender"] --> W["KMS/HSM: bọc DEK cho Recipient"]
    W --> E["Wrapped DEK + authenticated metadata"]
    E -->|TLS/mTLS| N["Network / broker"]
    N --> R["Authorized Recipient"]
    R --> K["KMS/HSM unwrap dưới policy"]
    K --> U["DEK dùng tạm / handle"]
    U --> D["Encrypt/Decrypt đúng dữ liệu"]
~~~

Bọc DEK bảo đảm người không có KEK/recipient private key không dễ lấy DEK rõ; TLS bảo vệ **kênh, xác thực peer và metadata/operation trên đường truyền**.

### 10.1. Khi nào có thể gửi plaintext DEK qua TLS?

Có một số API thiết kế trả **plaintext DEK tạm cho ứng dụng được phép**, ví dụ KMS GenerateDataKey/Decrypt trả material cho client để dùng AES-GCM. Đây có thể là mô hình hợp lệ **nếu** key export/usage policy cho phép, TLS và identity được kiểm tra, quyền tối thiểu, memory/logging được quản lý.

Tuy nhiên, **không nên chủ động phân phối plaintext DEK qua nhiều services** nếu có thể phân phối **wrapped DEK/handle** hoặc dùng KMS operation. Mỗi service nhận plaintext key là thêm một bản sao có thể bị compromise.

### 10.2. Không tự phát minh “encryption của key”

Các cách như **XOR key với một hằng số**, đảo bytes, Base64, một lần SHA-256, AES-ECB với key hard-code hoặc dùng một “master password” dễ đoán không phải cơ chế key wrapping tốt.

Chọn **KMS Encrypt/Decrypt/Wrap/Unwrap**, authenticated key wrap hoặc **hybrid public-key encryption** qua thư viện/giao thức được đánh giá, với ràng buộc recipient/context phù hợp.

### 10.3. Plaintext key và encrypted key blob là hai loại dữ liệu khác

Một encrypted DEK có thể nằm cạnh ciphertext trong database, object storage hoặc một envelope được truyền giữa services. Nhưng **không nên coi encrypted DEK là vô hại tuyệt đối**: nó vẫn mang metadata, có thể bị tráo/replay và có thể trở nên giải mã được nếu KEK/grants bị lộ về sau.

## 11. Key distribution cần ràng buộc đúng recipient và context

Một thông điệp phân phối khóa tốt cần xác định:

- **Sender identity**: ai phát hành key hoặc wrapped key?
- **Recipient identity**: ai được unwrap/nhận?
- **Key purpose**: Encrypt, Decrypt, HMAC, Sign hay Wrap?
- **Key ID/version/algorithm**: vật liệu nào, thuật toán nào?
- **Tenant/object/scope**: phạm vi dữ liệu và quyền?
- **Freshness/expiry/epoch**: có bị replay hoặc gửi key đã retired không?
- **Context binding**: thông điệp có được bảo vệ tính toàn vẹn/authentication không?
- **Audit/operation ID**: phân biệt retry, phê duyệt, incident và kết quả?

Một envelope record có thể lưu **wrapped DEK** và key reference; nhưng **đừng chỉ dựa vào tên recipient tự khai trong JSON** để quyết định principal nào được giải bọc.

### 11.1. Không đồng nhất identity của mạng với identity của dữ liệu

Ví dụ Service A được mTLS xác thực là workload production, nhưng object thuộc tenant B. Network authentication của A **chưa đủ** để A có quyền lấy DEK của B. IAM/KMS policy và business authorization cần cùng đúng scope.

### 11.2. Bảo vệ chống replay và downgrade

Ngay cả khi thông điệp phân phối khóa được mã hóa, attacker có thể cố gửi lại một **wrapped DEK cũ**, đổi key version hoặc đưa recipient sang thuật toán yếu. Receiver phải kiểm tra key state, version/epoch, allowed algorithms, TTL, expected owner và idempotency.

**Một key đã revoked không được tự động trở lại ACTIVE chỉ vì một message cũ tới muộn.**

## 12. Phân phối khóa đối xứng: bài toán “bí mật ban đầu”

Với mã hóa đối xứng như AES hoặc HMAC, hai bên phải có một **bí mật thích hợp**. Việc đưa khóa đó từ bên tạo đến bên sử dụng tạo ra **key-distribution problem**: nếu đã có một kênh bảo mật mạnh để gửi secret, cơ chế nào tạo ra kênh đó và ai giữ thông tin xác thực?

### 12.1. Một số mô hình khả thi

| Mô hình | Cách vận hành | Đánh đổi |
|---|---|---|
| **KMS GenerateDataKey / Wrap** | KMS quản lý KEK, cấp encrypted DEK/unwrap theo quyền | IAM, availability, quota, audit và key lifecycle |
| **Recipient-specific key wrapping** | Sender mã hóa DEK cho khóa công khai/KEK của recipient | Phải xác thực public key và bảo vệ private/KEK |
| **Authenticated key agreement** | Hai bên thiết lập secret chung qua protocol | Chủ yếu tạo session secret mới, không tự chuyển persistent DEK |
| **Trusted provisioning/secret manager** | Hệ thống provisioning cấp HMAC/PSK qua API được bảo vệ | Secret manager và mọi consumer đều phải được bảo vệ |
| **HSM key transport/import** | Bọc key theo chức năng HSM và nhận bằng key import được phê duyệt | Vendor interoperability, import format, dual control |
| **Offline recovery ceremony** | Key/share được trao theo thủ tục đặc biệt | Nhân lực, chain of custody và kiểm toán |

### 12.2. Không gửi raw symmetric key chỉ vì “nội mạng tin cậy”

Một VLAN, VPN hoặc mạng Kubernetes nội bộ có thể giảm rủi ro, nhưng không tự bảo đảm mọi workload trong mạng được quyền đọc khóa. **Network location không thay identity và authorization**. Mạng nội bộ vẫn có compromised host, packet capture, proxy và operator.

### 12.3. Master PSK chung cho mọi dịch vụ nguy hiểm

Nếu nhiều services đều biết một PSK chung, một service bị lộ có thể ảnh hưởng toàn bộ hệ thống. Cần tách key theo purpose, tenant/workload, cryptoperiod và giới hạn nơi material tồn tại. Khi thay secret, tất cả peers hợp lệ cần cập nhật có kiểm soát.

## 13. Phân phối DEK bằng mật mã bất đối xứng và hybrid encryption

Một kiến trúc có thể dùng **public key của recipient** để bảo vệ DEK. Người gửi không cần có private key của recipient; người nhận dùng private key được bảo vệ để mở.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant P as Trusted key directory / PKI
    participant R as Recipient
    S->>P: Lấy public encryption key của R
    P-->>S: Key + authenticated identity binding
    S->>S: Generate random DEK
    S->>S: Wrap/Encrypt DEK cho R
    S->>R: Wrapped DEK + metadata qua kênh đã xác thực
    R->>R: Kiểm tra sender, recipient, scope, version
    R->>R: Decrypt/Unwrap bằng private key được bảo vệ
~~~

### 13.1. Mã hóa khóa cho đúng người nhận, không cho public key bất kỳ

Nếu key directory bị thay, sender có thể bọc DEK cho public key của attacker. Vì vậy cần:

- Xác minh nguồn public key/chứng chỉ, issuer, key usage và identity.
- Kiểm tra recipient ID, environment, tenant và thuật toán được phép.
- Ghi public-key fingerprint hoặc key reference để kiểm toán, nhưng fingerprint từ nguồn chưa tin cậy không tự đủ.
- Quản lý rotation/revocation của recipient public key và encrypted key blobs.

### 13.2. RSA-OAEP và giới hạn

RSA-OAEP có thể dùng để mã hóa vật liệu kích thước nhỏ phù hợp tham số của khóa, **không dùng RSA trực tiếp mã hóa dữ liệu lớn**. Trong triển khai mới, có thể cân nhắc các mô hình **hybrid public-key encryption/HPKE** nếu hệ sinh thái hỗ trợ và được đánh giá.

Không tự kết hợp RSA, AES và KDF bằng một protocol tự nghĩ ra, và không sử dụng **RSA PKCS#1 v1.5 encryption** theo cách dễ dẫn tới oracle nếu có lựa chọn an toàn hơn theo chính sách.

### 13.3. Mã hóa cho recipient không tự xác thực sender

Một người biết public key của recipient cũng có thể tạo ciphertext gửi tới recipient. Nếu yêu cầu xác minh **ai cấp khóa**, cần cơ chế nhận diện sender riêng: authenticated channel, chữ ký số, MAC/chứng cứ phát hành qua KMS và audit. Phải ràng buộc **sender/recipient/keyRef/purpose/context** với dữ liệu được xác thực.

### 13.4. ECDSA/Ed25519 không phải thuật toán bọc khóa

ECDSA/Ed25519 là chữ ký, không dùng public signing key trực tiếp làm encryption key. X25519/ECDH là key agreement; một giao thức mã hóa lai có thể xây trên kết quả agreement **với KDF, AEAD và xác thực identity đúng chuẩn**. Không hoán đổi key usage tùy tiện.

## 14. Authenticated key agreement khác việc gửi sẵn khóa

Một số hệ thống không cần đưa **DEK cố định** từ A sang B. Thay vào đó, hai bên thiết lập một **session secret mới** thông qua giao thức xác thực như TLS 1.3 với ephemeral key exchange.

~~~mermaid
flowchart LR
    A["Client ephemeral private/public"] --> H["Authenticated key exchange"]
    B["Server ephemeral private/public"] --> H
    I["Peer identity verification"] --> H
    H --> K["Shared secret + protocol KDF"]
    K --> C["Traffic keys cho phiên"]
~~~

### 14.1. Secret chung không được phát công khai

Ở DH/ECDHE, hai bên trao đổi **public shares**, không trao private scalar. Shared secret được tính tại mỗi bên và chuyển qua **key schedule** của giao thức để có traffic keys.

Một observer có public shares nhưng không có private material tương ứng không dễ tính secret theo giả định bảo mật của giao thức. Tuy nhiên, nếu public shares không được **xác thực đúng peer**, attacker có thể thực hiện MITM bằng hai phiên agreement riêng.

### 14.2. Không dùng raw ECDH output trực tiếp làm AES key

Phải dùng protocol/KDF được thiết kế để dẫn xuất keying material phù hợp, ràng buộc transcript, role, direction và version nếu giao thức yêu cầu. Một **HKDF** đúng nơi trong key schedule khác hoàn toàn với việc hash một password dễ đoán rồi gọi là khóa mạnh.

### 14.3. Khóa phiên khác khóa bảo vệ dữ liệu lâu dài

Traffic key của TLS bảo vệ kết nối, không tự thay thế **DEK cần mở backup trong nhiều năm**. Nếu dữ liệu cần giải mã lại sau kết thúc phiên, cần thiết kế key management riêng cho data at rest.

## 15. KMS/HSM: chuyển khả năng sử dụng khóa thay vì chuyển plaintext key

Trong nhiều môi trường doanh nghiệp, nên tổ chức **key distribution** như việc phân phối **identity, grants, key reference và encrypted DEK**, thay vì cho nhiều ứng dụng tải master key dạng rõ.

### 15.1. Ba mức bảo vệ

1. **Key material ở KMS/HSM:** KEK/private key không export, hoặc export chỉ trong điều kiện rất chặt nếu provider hỗ trợ.
2. **Authenticated API:** workload sử dụng certificate/identity/token được bảo vệ để gọi KMS operation theo policy.
3. **Application authorization:** trước khi Decrypt/Sign/Unwrap, ứng dụng xác thực user và dữ liệu/purpose tương ứng.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant O as Object service
    participant K as KMS/HSM
    participant S as Storage
    participant R as Reader service
    O->>K: GenerateDataKey dưới KEK được phép
    K-->>O: DEK rõ tạm + encrypted DEK (nếu API hỗ trợ)
    O->>S: AES-GCM ciphertext + encrypted DEK + metadata
    R->>S: Read envelope thuộc object được phép
    S-->>R: Ciphertext + wrapped DEK
    R->>K: Unwrap DEK bằng workload identity
    K-->>R: DEK rõ tạm hoặc handle theo provider
    R->>R: AEAD Verify và trả plaintext theo authz
~~~

**Không phải KMS nào cũng hỗ trợ cùng API GenerateDataKey hoặc trả plaintext DEK.** Thiết kế phải dựa trên capability được xác minh, không tự giả định raw KEK có thể xuất ra.

### 15.2. Wrapping context và metadata integrity

Thông tin như **tenant, object, purpose, format version, key ID/material version** có thể được ràng buộc vào KMS encryption context nếu provider hỗ trợ, và vào AAD của payload khi phù hợp.

**KMS encryption context và payload AAD là hai lớp khác nhau**. Việc có một trong hai không tự thiết lập quyền của người dùng cuối. Receiver phải đối chiếu metadata với **trusted expected scope** trước khi dùng key.

### 15.3. Shared KEK và phạm vi ảnh hưởng

Một KEK dùng chung cho nhiều DEK/tenant có thể hợp lý theo chi phí và policy, nhưng tăng blast radius khi principal có Decrypt rộng hoặc KEK bị compromise. Cân nhắc KEK scope theo environment, application, tenant hoặc domain nhạy cảm, đồng thời đánh giá quota, latency và nhu cầu rotation.

### 15.4. Key ID có thể truyền công khai nhưng không phải credential

Biết keyRef không tự cấp quyền gọi KMS. Tránh để API nhận một keyRef tùy ý và gọi KMS với service role đầy quyền mà không kiểm tra object ownership.

## 16. Phân phối khóa trong toàn bộ vòng đời

~~~mermaid
flowchart LR
    G["Generate đúng entropy/algorithm"] --> P["Approve distribution policy"]
    P --> D["Protect & deliver / wrap key"]
    D --> U["Use trong scope + cryptoperiod"]
    U --> R["Rotate/redistribute material mới"]
    R --> V["Revoke recipients / stop old use"]
    V --> X["Dependency checks + destroy"]
    A["Inventory + audit"] --> D
    A --> R
    A --> V
    A --> X
~~~

| Giai đoạn | Trách nhiệm với đường phân phối |
|---|---|
| **Create** | Generate key bằng CSPRNG/KMS/HSM, đặt owner, usage, environment |
| **Approve** | Xác định recipient identities, quyền, phương thức transport/wrap |
| **Provision** | Cấp encrypted key/handle qua authenticated channel và audit |
| **Store** | Không lưu plaintext master key trong cùng nơi ciphertext/logs |
| **Use** | Giới hạn operation, cryptoperiod, endpoint và dữ liệu |
| **Rotate** | Tạo vật liệu mới, chuyển producer/consumer đúng version |
| **Revoke** | Chặn grants/credentials, ngừng dùng key cũ, cập nhật trust/cache |
| **Destroy** | Xác minh encrypted DEKs, backups và recovery dependencies trước hủy |

### 16.1. Không coi “delivery success” là “key activated”

Một HTTP 200/queue ACK chỉ chứng minh một endpoint/broker nhận message, **không chứng minh** consumer có quyền, đã unwrap đúng key, đã chuyển sang version mới, hoặc không còn dùng material cũ.

### 16.2. Inventory recipient và phiên bản

Key registry nên biết **recipient principals**, key ID/material version, key type, key usage, epoch, cryptoperiod, issuer/source, distribution method, wrapping key reference và audit operation ID. Nếu có sự cố, thông tin này giúp tìm **những bên đã nhận key rõ hoặc có khả năng sử dụng key**.

### 16.3. Cấp phát một lần hay theo nhu cầu

Phân phối trước một HMAC secret lâu dài cho mọi dịch vụ tăng số bản sao. Có thể cân nhắc:
- **On-demand key access** qua KMS/secret manager có IAM, timeout/audit.
- **Short-lived credentials/derived session keys** theo protocol.
- **Recipient-specific wrapped DEK** được lưu trong envelope khi cần đọc lâu dài.

Mỗi lựa chọn có đánh đổi về availability, latency, cost, recovery và blast radius.

## 17. Separation of duties trong key distribution

| Vai trò | Có thể làm | Không mặc nhiên được làm |
|---|---|---|
| **Key owner** | Quyết định purpose, recipient policy và lifecycle | Tự bypass mọi IAM |
| **Distribution requester** | Đề nghị cấp key cho workload hợp lệ | Tự duyệt high-risk export |
| **Security approver** | Duyệt recipient và key export exception | Tự xóa audit |
| **KMS/HSM operator** | Vận hành key policy/rotation theo approval | Tự Decrypt dữ liệu nghiệp vụ |
| **Recipient workload** | Unwrap/Sign/Decrypt đúng scope | ChangeKeyPolicy, ExportKEK hoặc Destroy |
| **IAM administrator** | Quản lý identities/grants theo policy | Tự nâng quyền rồi đọc secret |
| **Auditor** | Đọc events, kiểm tra recipient/key use | Thay hoặc xóa evidence |

### 17.1. Kiểm tra quyền bắc cầu

Một người không có Decrypt nhưng có quyền sửa IAM, cấp grants hoặc assume role Decryptor có thể tự mở đường lấy key. Cần kiểm tra **effective permissions** và privilege escalation paths, không chỉ tên role.

### 17.2. Dual control cho hành động đặc biệt

Export private signing key, recovery master material, thay trusted recipient public key hoặc phân phối KEK diện rộng là những thao tác cần cân nhắc **maker-checker, independent approval, HSM quorum hoặc split knowledge**, tùy policy/rủi ro.

### 17.3. Break-glass không đồng nghĩa chia sẻ key lên chat

Trong sự cố, đội phản ứng có thể cần quyền tạm để DisableKey/RevokeGrant hoặc phục hồi dữ liệu. Hãy dùng **JIT/break-glass role có audit và TTL**, không gửi raw KEK trong Slack/email/ticket để “xử lý nhanh”.

## 18. Chia sẻ secret qua queue, event và object store

Một message broker có TLS có thể bảo vệ kết nối đến broker, nhưng **nội dung message có thể được lưu, replay, backup, mirror hoặc đọc bởi nhiều consumers/operators**.

### 18.1. Quy tắc cho asynchronous key distribution

1. Ưu tiên gửi **wrapped DEK/key reference**, không raw key.
2. Xác thực **publisher và recipient consumer**, đồng thời kiểm tra business scope.
3. Quản lý broker ACL/topic permissions và storage encryption, retention, DLQ.
4. Đưa **key ID/version, recipient, purpose, expiry/epoch, operation ID** vào metadata được xác thực.
5. Đảm bảo receiver **idempotent**, không chấp nhận stale/revoked key activation.
6. Giới hạn event body/debug logging và quan sát quyền truy cập DLQ/replay.
7. Khi đổi recipient, kiểm tra họ có còn bản sao plaintext key từ trước hay không.

### 18.2. Key references và capability tokens khác nhau

Một keyRef có thể công khai, còn **presigned URL, temporary credential hoặc bearer token** có thể trực tiếp cấp khả năng truy cập. Không đánh đồng hai loại và không bỏ token vào log/query không kiểm soát.

### 18.3. Data at rest của broker cũng phải được quản lý

TLS chỉ bảo vệ trên đường. Nếu broker giữ plaintext DEK trong event 30 ngày hoặc gửi tới analytics, thông điệp vẫn là điểm rò rỉ. Phải đánh giá **retention, encryption at rest, consumer ACL, backups, export và deletion**.

## 19. Java: ba cách gửi key sai cần nhận diện

### 19.1. HTTP POST chứa key rõ

~~~java
// KHÔNG AN TOÀN — anti-pattern, không dùng production.
java.net.URI endpoint = java.net.URI.create(
    "http://internal-service.example.test/distribute");
byte[] plaintextDek = getPlaintextDekFromSomewhere();
// Nếu gửi plaintextDek qua HTTP, mọi observer có thể đọc.
~~~

### 19.2. URL/query chứa secret

~~~java
// KHÔNG AN TOÀN: secret xuất hiện trong URL/log/history.
String url = "https://api.example.test/key?secret="
    + java.net.URLEncoder.encode(
        "SAMPLE_SECRET_NOT_REAL",
        java.nio.charset.StandardCharsets.UTF_8);
~~~

Ngay cả khi HTTPS hoạt động, query vẫn có thể bị proxy/monitoring ghi log.

### 19.3. Bỏ xác thực certificate

~~~text
Anti-pattern:
- TrustManager chấp nhận tất cả X509 certificates.
- Tắt kiểm tra hostname vì self-signed certificate.
- Thử HTTPS lỗi rồi tự động retry HTTP.
- Cho phép redirect từ HTTPS đến HTTP.
~~~

Những “giải pháp tạm” này có thể loại bỏ chính sự bảo vệ chống MITM cần thiết cho đường phân phối key.

### 19.4. Gửi private key để bên nhận tự ký

Nếu service chỉ cần chức năng Sign, không nên cấp private key dạng rõ. Dùng HSM/KMS signing API theo policy, hoặc một kiến trúc ký phân tán được thiết kế đúng mục tiêu. **Bảo vệ private key không chỉ là mã hóa file chứa key trước khi gửi**.

## 20. Java 17: gửi wrapped DEK qua HTTPS, không gửi raw DEK

Đoạn mẫu dưới đây minh họa **transport của một wrapped key envelope đã được tạo bởi KMS/key wrapping service**. Nó **không** generate/export KEK và **không thực hiện wrap bằng key hard-code**. Bản ghi truyền gồm recipient, keyRef, tenant, purpose, phiên bản và encrypted DEK.

Code dùng:

- **java.net.http.HttpClient** và URL **HTTPS cố định trong allowlist**.
- TLS validation mặc định của Java, **không** tùy biến TrustManager cho phép mọi certificate.
- **Không cho redirect**, tránh mang wrapped key/metadata tới host khác.
- **POST body nhị phân length-prefixed**, không đặt key trong URL/query.
- Timeout, request/response status check và giới hạn đầu vào.
- Không log response body chứa thông tin nhạy cảm.

**Chú ý:** Ví dụ chỉ là một client vận chuyển đã có **wrapped key**. Production cần thêm workload authentication (ví dụ mTLS/OAuth workload identity), service authorization, recipient proof, KMS-backed wrapping, anti-replay, idempotency, audit và schema validation tại bên nhận.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

public final class WrappedKeyTransportExample {
    private static final URI ENDPOINT = URI.create(
        "https://keys.internal.example.test/v1/distributions");
    private static final int MAGIC = 0x4B455931; // "KEY1"
    private static final int FORMAT_VERSION = 1;

    public record WrappedKeyEnvelope(
        String recipientId,
        String tenantId,
        String purpose,
        String keyRef,
        int keyEpoch,
        byte[] wrappedDek
    ) {}

    private static void writeText(
        DataOutputStream out, String value) throws Exception {
        Objects.requireNonNull(value);
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                "Invalid text field length");
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    private static byte[] encode(
        WrappedKeyEnvelope env) throws Exception {
        Objects.requireNonNull(env);
        if (env.keyEpoch() < 1
                || env.wrappedDek() == null
                || env.wrappedDek().length == 0
                || env.wrappedDek().length > 8192) {
            throw new IllegalArgumentException(
                "Invalid wrapped key envelope");
        }

        ByteArrayOutputStream bytes =
            new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(MAGIC);
            out.writeInt(FORMAT_VERSION);
            writeText(out, env.recipientId());
            writeText(out, env.tenantId());
            writeText(out, env.purpose());
            writeText(out, env.keyRef());
            out.writeInt(env.keyEpoch());
            out.writeInt(env.wrappedDek().length);
            out.write(env.wrappedDek());
        }
        return bytes.toByteArray();
    }

    private static void validateDestination(URI uri) {
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || !"keys.internal.example.test"
                    .equalsIgnoreCase(uri.getHost())
                || !(uri.getPort() == -1 || uri.getPort() == 443)
                || !"/v1/distributions".equals(uri.getPath())
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new SecurityException(
                "Destination outside allowlist");
        }
    }

    public static int transmit(
            WrappedKeyEnvelope envelope) throws Exception {
        validateDestination(ENDPOINT);
        byte[] payload = encode(envelope);

        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(5))
            // Mặc định dùng TLS trust/hostname validation.
            // Không cài TrustManager chấp nhận mọi certificate.
            .build();

        HttpRequest request = HttpRequest.newBuilder(ENDPOINT)
            .timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/octet-stream")
            .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
            .build();

        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {
            throw new SecurityException(
                "Distribution transport rejected");
        }
        // HTTP 2xx không có nghĩa recipient đã activate key.
        // Cần audit/operation ack và consumer-side verification.
        return response.statusCode();
    }
}
~~~

### 20.1. Code này bảo vệ điều gì?

- Không chuyển secret sang **HTTP plaintext**.
- Không đặt secret hay encrypted key trong query string.
- Không tự tắt TLS peer validation.
- Không cho redirect tự động sang một host khác.
- Chỉ gửi **wrapped DEK**, không gửi plaintext DEK.
- Có **key epoch** và recipient metadata để hệ thống đích áp policy.
- Có giới hạn kích thước payload cho bản tin mẫu.

### 20.2. Code chưa giải quyết điều gì?

- **Authentication sender:** mặc định Java HTTPS client kiểm tra server, nhưng đoạn mẫu chưa thiết lập client certificate hoặc workload access token. Production phải có cơ chế chứng thực caller phù hợp.
- **Authorization recipient:** endpoint phải xác thực client, kiểm tra receiver, tenant/purpose/keyRef từ nguồn đáng tin và action được phép.
- **Authenticated wrapping:** encrypted DEK phải do KMS/crypto library đúng chuẩn tạo, ràng buộc context/recipient.
- **Replay protection:** receiver cần lưu operation ID, epoch, sequence/expiry và trạng thái key.
- **Audit:** cần record các hoạt động Request/Approve/Deliver/Unwrap/Activate mà không log key bytes.
- **Delivery acknowledgment:** HTTP 2xx không phải bằng chứng key đã được import/unwrap hay recipient đã chuyển version.
- **Secret lifetime:** payload là wrapped key, nhưng plaintext DEK tồn tại ở sender/recipient/KMS vẫn phải được quản lý.
- **Protocol versioning:** Wire format cần có parser đầy đủ, xác thực canonical metadata và công bố compatibility policy.
- **Input controls:** giới hạn at-rest, IPC, KMS/SDK response và serialization ở các lớp khác.

### 20.3. Vì sao không xây TLS stack bằng tay?

TLS đòi hỏi rất nhiều chi tiết về handshake, certificate validation, key schedule, phiên bản giao thức và downgrade protection. Hãy dùng **HTTP client/TLS stack được duy trì và cấu hình đúng**; không tự xây AES/TCP và gọi đó là “HTTPS tự chế”.

### 20.4. Nếu muốn dùng mTLS

Triển khai thật có thể cấu hình Java SSLContext với **KeyManagerFactory**, **TrustManagerFactory** dùng key store/trust store được quản lý và client identity hợp lệ. Không tạo custom TrustManager bỏ kiểm tra chứng chỉ. Certificate của client cần rotation/revocation và server cần ánh xạ cert identity sang quyền nhận wrapped keys.

## 21. Quy trình cấp key cho đối tác hoặc vận hành thủ công

Không phải mọi recipient là một Java service. Có lúc cần cấp secret cho đối tác, thiết bị ngoại tuyến hoặc HSM của bên thứ ba.

### 21.1. Trước khi phân phối

1. Xác định **recipient identity** và business purpose được phê duyệt.
2. Thống nhất thuật toán, key length, format, key usage, cryptoperiod và key version.
3. Chọn **authenticated protected channel** hoặc **recipient-specific key wrap**.
4. Xác minh public key/certificate/wrapping key của recipient qua nguồn tin cậy.
5. Thiết lập ownership, approval, SoD và audit/chain of custody.
6. Quy định cách recipient xác nhận **đã nhận đúng key** mà không gửi lại secret.
7. Chuẩn bị phương án rotate, revoke, hủy bản sao và incident response.

### 21.2. Offline HSM key transport

Một số HSM có chức năng **wrap/export/import key theo policy** để di chuyển key giữa miền bảo vệ. Quy trình có thể yêu cầu dual control, key ceremony, backup shares hoặc cơ chế manufacturer-specific.

**Không gửi KEK/private key dạng rõ trong file đính kèm** chỉ vì thiết bị đích tạm không có mạng. Nếu có ngoại lệ key material export, phải đánh giá tính hợp pháp, rủi ro, cơ chế bọc, người giữ, chain of custody và xóa bản sao tạm.

### 21.3. Hai kênh độc lập để xác nhận recipient

Trong trường hợp trao public key cho đối tác ngoài tổ chức, có thể xác nhận **fingerprint** qua kênh độc lập đáng tin. Tuy nhiên, chỉ đọc fingerprint của cùng email chứa public key **không tạo xác minh độc lập** nếu email đó có thể bị giả mạo.

### 21.4. Không gửi toàn bộ secret để “test” bàn giao

Proof-of-possession có thể được thực hiện bằng một cơ chế chứng minh cryptographic operation phù hợp và an toàn; không yêu cầu bên nhận gửi lại raw key lên chat/ticket để bên gửi đối chiếu.

## 22. Bảo vệ key tại endpoint, cache và đường phục hồi

Dù kênh truyền và key wrap đã đúng, **plaintext key** có thể xuất hiện tại sender, recipient hoặc KMS SDK trong những thời điểm nhất định. Phải thiết kế **key lifetime** ở endpoint.

### 22.1. Những nơi dễ chứa bản sao key

- Java heap, native crypto buffer, process memory.
- Secret manager SDK response cache, shared application cache.
- Thread dumps, heap dumps, crash reports, application traces.
- Container filesystem, swap, temporary files hoặc snapshot.
- Debugger, profiler, error reporting và APM instrumentation.
- CI/CD variables và deployment manifests.
- DLQ/message replay, offline exports và backups.
- Một service khác được cấp cùng HMAC/PSK hoặc DEK.

**TLS không bảo vệ secret sau khi đã được giải mã ở endpoint.** Nếu ứng dụng cố ý lưu key rõ 24 giờ trong cache chung, việc truyền qua TLS chỉ giảm rủi ro trên mạng, không giải quyết cache compromise.

### 22.2. Giảm thời gian giữ plaintext key

1. Unwrap chỉ sau **authorization** và đúng object/purpose.
2. Hạn chế DEK ở scope nhỏ nhất, không làm field static dùng chung mọi tenant.
3. Tránh chuyển key sang String bất biến, logs hoặc exception.
4. Xóa best-effort các byte arrays thuộc sở hữu code khi xong.
5. Cấu hình heap/core dump và debug theo chính sách production.
6. Nếu dùng plaintext DEK cache, đặt **TTL, maximum uses/bytes, key version, scope** và điều kiện invalidate.
7. Ưu tiên HSM key handle/API khi yêu cầu giữ private/KEK non-exportable.

**Arrays.fill trên một mảng trong Java không bảo đảm xóa mọi bản sao nội bộ JCE/provider**, nên không tuyên bố zeroization tuyệt đối.

### 22.3. Availability và fail-safe

Nếu KMS hoặc kênh phân phối bị outage, không chuyển sang **HTTP plaintext, key hard-code, skip certificate validation hoặc shared emergency password**. Cần thiết kế trước khả năng DR, cache được phê duyệt theo hạn dùng, quorum và recovery policy mà vẫn giữ ranh giới bảo mật.

## 23. Audit, inventory và chính sách phân phối khóa

Để biết ai nhận được key và có thể sử dụng key, cần kết nối **inventory** với **audit events**.

### 23.1. Những trường nên có trong inventory

| Nhóm | Thuộc tính |
|---|---|
| **Key identity** | key ID, material version, algorithm, key usage, origin |
| **Key ownership** | owner, custodian, data owner, environment |
| **Recipient** | identity, tenant/workload, account/region, approved role |
| **Distribution** | method (KMS ref, wrapped DEK, mTLS, HSM import), issuer, operation ID |
| **Security policy** | approval reference, exportability, key context, allowed operations |
| **Lifecycle** | activated, rotated, retired, revoked, destroyed; cryptoperiod |
| **Dependencies** | encrypted DEKs, ciphertext datasets, devices, backups, consumers |
| **Verification** | delivery ACK, KMS observed state, consumer cutover, last attestation |

### 23.2. Một audit event minh họa

~~~json
{
  "eventType": "WRAPPED_KEY_DISTRIBUTION",
  "operationId": "dist-op-902",
  "keyRef": "kms/prod/orders-kek",
  "keyMaterialVersion": "v4",
  "recipientId": "orders-reader-prod",
  "tenantRef": "tenant-42",
  "purpose": "invoice-storage-decrypt",
  "actor": "key-provisioner-prod",
  "approvedBy": "approval-117",
  "transport": "authenticated-https",
  "payloadType": "WRAPPED_DEK",
  "deliveryResult": "ACCEPTED",
  "recipientActivation": "PENDING_VERIFICATION",
  "occurredAt": "2026-11-28T03:10:00Z"
}
~~~

Đây là **schema minh họa**, không phải format chuẩn của mọi KMS/PKI. Không ghi plaintext DEK/KEK, private key, HMAC secret, token hoặc raw password vào logs.

### 23.3. Điều gì được coi là “đã phân phối thành công”?

Nên tách rõ:

- **Transport delivered:** mạng/broker báo đã nhận bytes.
- **Recipient authenticated:** endpoint nhận đã được xác thực và nằm trong allowlist.
- **Authorized:** recipient được phép nhận vật liệu/key version đó.
- **Integrity verified:** wrapping/metadata/signature/protocol check đạt.
- **Key activated:** consumer thực sự dùng đúng material/version theo policy.
- **Old key stopped:** producer/consumer không còn phát sinh hoạt động cấm dưới key cũ.
- **Audited:** có operation ID và evidence cho mỗi bước.

**HTTP 200 không chứng minh tất cả điều kiện trên**, và việc gọi KMS thành công không tự xác minh business authorization cho end user.

### 23.4. Những chỉ số hữu ích

- Số lần **plaintext key export** trong môi trường production, theo policy exceptions.
- Số recipient/workloads có key access nhưng **không có owner hoặc approval**.
- Tỷ lệ **mTLS/TLS authenticated** trên tất cả key distribution hops.
- Số lần gửi secret tới **host ngoài allowlist** bị chặn.
- Số request chứa sensitive params trong **URL/logging** được phát hiện.
- Số old key versions vẫn còn active sau cutover.
- Số key-distribution events không có audit hoặc không có recipient acknowledgment.
- Số failed unwrap do wrong context, expired key hoặc stale version.
- Số endpoints chưa xoay certificate/trust khi đến hạn.
- Số sự cố lộ secret và thời gian containment có evidence.

**Không chỉ đếm “TLS connections thành công”**: cần xác minh endpoint đúng, key usage đúng và secret không bị sao chép sang logs/queue.

## 24. Ứng phó khi một khóa đã đi qua kênh plaintext

Một lần gửi **plaintext DEK, KEK, private signing key hoặc HMAC secret** qua một kênh mà người ngoài có thể quan sát phải được đánh giá như **sự cố an toàn khóa**, ngay cả khi chưa phát hiện ai đã nghe lén.

### 24.1. Phân biệt exposed và confirmed stolen

- **Exposed / potentially compromised:** có đường truyền hoặc bản sao vượt ranh giới bảo mật, chưa biết attacker đã đọc chưa.
- **Confirmed compromise:** có chứng cứ key/credential đã bị tiết lộ cho bên không có quyền hoặc bị sử dụng sai.

Mức xử lý cần dựa trên **loại key, phạm vi truyền, thời gian, log visibility, encryption mode, blast radius và khả năng thu thập của đối thủ**.

~~~mermaid
flowchart TD
    A["Phát hiện key gửi qua plaintext/log"] --> B["Cô lập đường truyền và credentials liên quan"]
    B --> C["Khoanh vùng key material/version, recipients, thời gian"]
    C --> D["Xác định ciphertext / MAC / signatures phụ thuộc"]
    D --> E["Generate material mới bằng CSPRNG/KMS/HSM"]
    E --> F{"Loại khóa?"}
    F -->|DEK| G["Thay DEK và đánh giá re-encrypt"]
    F -->|KEK| H["Thay KEK, rewrap + đánh giá DEKs đã lộ"]
    F -->|HMAC/PSK| I["Phân phối secret mới, revoke old acceptance"]
    F -->|Signing private| J["Tạo key pair mới, cập nhật verifiers/trust"]
    G --> K["Verify IAM, KMS, cache, backup, audit"]
    H --> K
    I --> K
    J --> K
    K --> L["Retire/revoke/destroy theo dependency clearance"]
~~~

### 24.2. Hành động đầu tiên

1. Dừng code path gửi secret qua HTTP/query/log/queue trái policy.
2. Thu hồi hoặc hạn chế credential đã dùng, nếu có nguy cơ chiếm quyền.
3. Kiểm tra nơi secret có thể tồn tại: proxy, network capture, APM, monitoring, CI logs, DLQ, backups.
4. Lưu **evidence an toàn** nhưng không nhân bản plaintext key trong báo cáo.
5. Thông báo key owner, security response và data owner theo severity.
6. Tạo phương án thay key/redistribution tránh lặp lại đường plaintext.

### 24.3. Cách thay khác nhau theo loại khóa

| Secret đã gửi sai | Rủi ro còn lại | Biện pháp chính |
|---|---|---|
| **Plaintext DEK** | Đối thủ có thể giải mã bản mã đã thu thập | DEK mới, re-encrypt dữ liệu có nguy cơ, incident assessment |
| **Plaintext KEK** | Có thể unwrap nhiều encrypted DEK | KEK mới, rewrap và đánh giá DEK đã có thể lộ |
| **Private signing key** | Có thể ký giả **ngoài KMS/HSM** | Key pair mới, revoke/update public trust, rà soát signatures |
| **HMAC/PSK** | Có thể giả mạo MAC/đăng nhập giữa peers | Phân phối secret mới, ngừng chấp nhận old key, anti-replay |
| **Recovery secret/share** | Đường phục hồi có thể bị lạm dụng | Đánh giá quorum/rotation/reconstitution và phụ thuộc |
| **KMS bearer token** | Attacker có thể gọi KMS dưới identity hợp lệ | Revoke token/session, grants, IAM review và audit |

### 24.4. Rewrap không cứu plaintext DEK đã lộ

Nếu attacker có plaintext DEK, bọc DEK đó dưới KEK mới **không làm DEK cũ trở lại bí mật**. Khi dữ liệu tương ứng có thể đã bị lộ, phải đánh giá replace DEK/re-encrypt và ảnh hưởng dữ liệu đã bị giải mã.

### 24.5. Không xóa KEK vội khi còn backup

Containment có thể cần Disable/Revoke quyền nguy hiểm, nhưng **Destroy KEK sớm** có thể làm mất encrypted DEK trong archives. Kiểm kê dependencies, restore path và retention trước khi thực hiện irreversible destruction.

### 24.6. Không kết luận an toàn vì không thấy log nghe lén

Một kẻ nghe lén mạng có thể không để lại dấu vết trong application logs. **Sự vắng mặt của bằng chứng quan sát không đồng nghĩa bí mật chưa bị lộ**. Báo cáo phải nêu rõ phạm vi và độ bao phủ điều tra.

## 25. Case study A: Java service gửi DEK qua HTTP nội bộ

Một service mã hóa hóa đơn dùng AES-256-GCM, rồi gửi DEK cho một batch reader qua HTTP nội bộ:

~~~text
POST http://batch-reader.internal/keys
body: {"dek":"BASE64_PLAINTEXT_DEK","invoiceId":"901"}
~~~

Nhóm phát triển cho rằng cluster network đáng tin và không cần TLS.

### 25.1. Vấn đề

- Một compromised pod/node hoặc network observer có thể thu key.
- Proxy/application debug có thể ghi request body.
- Thay invoiceId có thể gây nhầm scope nếu không được xác thực.
- DEK có thể được lưu trong queue hoặc cache của batch reader.
- Hệ thống không biết rõ ai còn nắm bản sao DEK sau khi job hoàn thành.

### 25.2. Thiết kế thay thế

1. Tạo **DEK bằng CSPRNG/KMS** và mã hóa hóa đơn theo AEAD.
2. Dùng KMS bọc DEK dưới KEK được phê duyệt.
3. Lưu ciphertext, wrapped DEK, nonce/tag và metadata.
4. Batch reader lấy envelope theo quyền business/tenant.
5. Batch reader dùng **workload identity + TLS/mTLS + KMS IAM** để Unwrap đúng scope.
6. Không gửi raw DEK qua API riêng hoặc broker khi không cần.
7. Thêm audit OperationID, key version, purpose và giới hạn cache.
8. Test negative IAM và quan sát logs/sidecars có vô tình chứa secret không.

**Giá trị chính:** KMS quản lý KEK và IAM, trong khi mỗi workload có thể dùng DEK tạm theo đúng scope. Lộ một bản sao storage không tự đồng nghĩa lộ plaintext key.

## 26. Case study B: tráo public key khi trao đổi secret với đối tác

Một nhà cung cấp gửi public key của Partner B qua email không được xác thực. Attacker chiếm email hoặc thay attachment rồi đặt public key của chính mình vào file có tên giống của B.

Sender bọc DEK dưới public key giả, gửi qua HTTPS. Mọi HTTPS request tới endpoint sender định gửi vẫn có thể được TLS bảo vệ; nhưng **recipient key binding đã sai trước khi truyền**.

### 26.1. Điều gì xảy ra?

Nếu attacker có được wrapped DEK tương ứng, họ có thể dùng private key của mình mở DEK. Việc sender “đã mã hóa DEK bằng RSA/HPKE” không giúp gì nếu **encrypt cho sai recipient**.

### 26.2. Kiểm soát

- Lấy recipient key từ registry/PKI được quản lý hoặc cơ chế có danh tính đáng tin.
- Xác minh certificate chain, key usage, identity và public-key fingerprint qua kênh độc lập khi phù hợp.
- Ràng buộc recipient ID, key version, purpose và expiry vào wrapped message/associated data theo protocol.
- Kiểm tra sender authorization và recipient proof/ack theo cơ chế được phê duyệt.
- Audit việc **thay recipient public key** như một thay đổi quyền rủi ro cao.
- Có phương án revoke/rotate nếu đã phân phối key cho recipient sai.

**Bài học:** bảo vệ kênh truyền không thay thế xác thực **public key thuộc đúng người nhận**.

## 27. Case study C: message broker dùng TLS nhưng key vẫn bị lộ

Một service phát event:

~~~json
{
  "eventType": "KEY_ROTATED",
  "keyVersion": "v9",
  "tenantId": "tenant-42",
  "plaintextHmacSecret": "BASE64_SECRET_MATERIAL"
}
~~~

Publisher và broker dùng TLS, nhưng topic có một analytics consumer, DLQ retention dài và chức năng export events cho support.

### 27.1. Vì sao TLS chưa đủ?

Broker giải mã TLS khi nhận và **lưu plaintext secret trong event payload**. Những bên có quyền đọc topic, DLQ, archive hoặc export đều có thể lấy secret. Đường transport tới broker an toàn nhưng **phân phối dữ liệu** không giới hạn đúng recipients.

### 27.2. Khắc phục

1. Loại plaintext HMAC secret khỏi schema event.
2. Event chỉ chứa **key reference/version/rotation event ID**, hoặc encrypted secret đã bọc riêng cho recipient.
3. Consumer lấy secret qua secret manager/KMS theo IAM và TLS/mTLS.
4. Thu hồi secret đã lộ qua broker, cấp version mới và ngừng chấp nhận version cũ.
5. Kiểm kê logs, DLQ, snapshots, analytics exports và backups.
6. Giới hạn topic ACL, retention, auditing và consumer identity.
7. Thêm static/schema validation để cấm những field có khả năng chứa raw secret.

**Bài học:** “Encryption in transit” và “authorization tại broker/consumer” là những lớp kiểm soát khác nhau.

## 28. Ma trận kiểm thử bảo mật key distribution

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Gửi raw key tới HTTP URL | Bị client/policy chặn |
| HTTPS hostname không đúng certificate | TLS validation thất bại |
| Certificate chain không tin cậy | Kết nối bị từ chối; không disable verification |
| TLS redirect tới HTTP | Không follow, không gửi payload |
| Redirect tới host ngoài allowlist | Không gửi payload |
| Sử dụng ciphers/protocol bị policy cấm | Kết nối bị từ chối |
| mTLS client thiếu chứng chỉ hợp lệ | Server từ chối truy cập nếu mTLS là yêu cầu |
| mTLS thành công nhưng client sai tenant | Application/KMS authz từ chối |
| Service chỉ có Encrypt gọi KMS Unwrap | IAM/key policy deny |
| Recipient key được thay bằng public key giả | Trust validation từ chối |
| Public key hết hạn hoặc revoked | Trust policy xử lý đúng, không tin tùy tiện |
| kid/JWKS source do token tự khai | Verifier không tin key ngoài issuer policy |
| Query chứa key/token | Security scanner phát hiện; không gửi |
| Key bytes xuất hiện trong HTTP/debug logs | Logging policy chặn và cảnh báo |
| Proxy termination rồi forward HTTP raw key | Architecture test phát hiện insecure hop |
| Message broker có raw key trong DLQ | Schema test từ chối và rà soát retention |
| KMS wrapped DEK qua HTTPS | Recipient unwrap đúng scope, tag/context hợp lệ |
| Wrapped key sai recipient/context | Unwrap hoặc authorization thất bại |
| Recipient gửi keyRef ngoài allowlist | Từ chối trước KMS call |
| Wrapped DEK bị chỉnh sửa | Authenticated wrap hoặc payload verification thất bại |
| Replay message key version cũ | Epoch/state guard ngăn tái kích hoạt |
| Retry cùng distribution operation ID | Idempotent; không cấp thêm quyền/key ngoài dự định |
| Envelope bị đổi tenant/object | Business authz/AAD/context từ chối |
| KMS outage | Fail-safe, không fallback plaintext channel |
| DEK plaintext trong cache quá TTL | Cache invalidation và giới hạn usage hoạt động |
| Private signing key cố bị export | KMS/HSM policy từ chối nếu non-exportable |
| Service cố tự CreateGrant/ChangeKeyPolicy | SoD/IAM từ chối |
| Rotate HMAC/PSK | Old acceptance bị chặn sau cutover theo policy |
| Signing key compromise | Verifier/trust được cập nhật, không chỉ DisableSign |
| Backup ciphertext còn phụ thuộc KEK v1 | Không destroy KEK v1 trước dependency clearance |
| Emergency break-glass | Scope/TTL/audit đúng; không dùng chat gửi raw KEK |
| Audit | Đủ actor, approval, key ID/version, outcome; không raw secret |

**Negative tests là bắt buộc**: kiểm tra rằng một identity hoặc endpoint **không được** nhận key thật sự bị chặn ở tầng IAM/KMS/application, không chỉ UI ẩn nút.

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Thay bằng |
|---|---|---|
| Gửi AES/HMAC/private key qua HTTP | Người nghe lén lấy secret | TLS/mTLS và tốt hơn là wrapped key/KMS |
| Base64 key rồi cho là an toàn | Key vẫn dạng rõ sau decode | Key wrap/encryption đúng cơ chế |
| Gửi key trong URL/query | Logs/history/analytics lộ key | Không đưa secret vào URL |
| Tin mạng nội bộ là an toàn tuyệt đối | Lộ từ node/proxy/compromised service | Authenticated channel + IAM |
| Disable TLS certificate verification | Dễ bị MITM | Valid chain + hostname validation |
| Tự retry HTTP khi HTTPS lỗi | Mở kênh plaintext ngoài dự kiến | Fail-safe và sửa cấu hình trust |
| Cho redirect không kiểm soát | Gửi payload sang host khác | Fixed endpoint allowlist, no redirect |
| Tin TLS đủ để gửi master KEK cho mọi service | Tăng bản sao secret | Non-exportable KMS/HSM + key references |
| Public key lấy từ email chưa kiểm tra | Key substitution | Authenticated PKI/recipient binding |
| Nhầm public signing key với public encryption key | Dùng sai thuật toán/usage | Dùng đúng key purpose/giao thức |
| Dùng DH public shares mà không xác thực peer | MITM | Authenticated key agreement |
| Tự viết crypto transport | Lỗi protocol/handshake | TLS/HPKE/KMS được đánh giá |
| Chỉ dùng mTLS, không kiểm tra quyền tenant | Authorized transport nhưng unauthorized data | Business authz + KMS scope |
| KMS service role có Decrypt mọi tenant | Blast radius rất lớn | Least privilege, per-scope grants |
| KeyRef bị coi là secret token | Bypass theo tên key | Identity/authorization độc lập |
| Message broker TLS nhưng chứa raw keys | Consumer/DLQ/backup lộ secret | Chỉ gửi wrapped key/ref |
| Debug log request body chứa DEK | Secret vẫn bị lộ | Redaction/field policy |
| HMAC key dùng chung quá nhiều services | Một điểm lộ ảnh hưởng diện rộng | Key separation và rotation |
| Chỉ đổi alias khi rotate | Old key material vẫn dùng | New key material/version, cutover |
| Gửi raw secret cũ để xác nhận recipient | Tăng bản sao secret | Secure proof/ack và metadata |
| Chỉ disable signing key bị lộ | Attacker có thể ký ngoài HSM | Revoke verifier trust và key replacement |
| Rewrap DEK đã bị lộ | Attacker vẫn biết DEK | Thay DEK và đánh giá re-encrypt |
| Hủy KEK ngay sau incident | Mất khả năng mở backups | Containment + inventory + recoverability |
| Chỉ xem HTTP 200 là activation thành công | Consumer có thể chưa đổi key | Consumer acknowledgment, version check |
| Không kiểm tra replay | Key cũ có thể được dùng lại | Epoch/TTL/idempotency/state guard |
| Audit lưu plaintext key | Tạo thêm data breach | Metadata + outcome không raw secret |

## 30. Câu hỏi tự kiểm tra

**Câu 1. Vì sao không gửi AES key qua HTTP plaintext dù key được sinh ngẫu nhiên mạnh?**

**Trả lời:** Người nghe lén có thể lấy raw key và giải mã hoặc giả mạo dữ liệu. Sức mạnh thuật toán không bù cho đường phân phối bị lộ.

**Câu 2. Base64 một DEK có làm nó được mã hóa không?**

**Trả lời:** Không. Base64 là encoding có thể đảo ngược, không thêm confidentiality.

**Câu 3. Gửi plaintext key qua HTTPS có luôn là thiết kế tốt không?**

**Trả lời:** Không. HTTPS bảo vệ kênh, nhưng phải kiểm tra recipient và policy export, endpoint, IAM, logging, key lifetime. Ưu tiên wrapped key hoặc KMS operation khi có thể.

**Câu 4. mTLS xác thực workload thì có tự cấp quyền lấy mọi DEK không?**

**Trả lời:** Không. Vẫn cần KMS IAM, key scope, tenant/object business authorization và purpose checks.

**Câu 5. Public key có cần giữ bí mật không?**

**Trả lời:** Không, nhưng phải xác thực nó thuộc đúng recipient hoặc signer qua trust binding đáng tin để tránh MITM/key substitution.

**Câu 6. Vì sao một certificate PEM tải từ URL chưa chứng minh người sở hữu?**

**Trả lời:** File có thể bị tráo. Cần xác minh chain/issuer, identity, key usage, trust policy và phiên bản.

**Câu 7. ECDHE khác việc gửi sẵn khóa đối xứng như thế nào?**

**Trả lời:** Hai bên trao public shares và dẫn xuất session secret từ key agreement; không gửi private key/secret trực tiếp. Phải xác thực peer để chống MITM.

**Câu 8. TLS 1.3 có làm biến mất raw key ở receiver không?**

**Trả lời:** Không. Endpoint vẫn nhận plaintext sau TLS; key có thể nằm trong RAM, logs hoặc cache.

**Câu 9. Tại sao không đặt secret trong query string của HTTPS URL?**

**Trả lời:** URL dễ đi vào proxy logs, history, analytics, monitoring, redirect và các hệ thống hỗ trợ khác.

**Câu 10. Wrapped DEK có thể nằm trong event payload không?**

**Trả lời:** Có thể, nếu KMS/wrapping an toàn, recipient/context binding đúng và broker/consumer được kiểm soát. Không được thay raw DEK bằng wrapped blob rồi bỏ qua IAM/authz/replay.

**Câu 11. KMS non-exportable có chống lạm dụng Decrypt/Sign API không?**

**Trả lời:** Không hoàn toàn. Principal được cấp quyền có thể yêu cầu phép toán trái mục đích; cần least privilege, approval, rate controls và audit.

**Câu 12. Nếu recipient public key bị tráo, mã hóa RSA/HPKE có còn bảo vệ DEK khỏi attacker không?**

**Trả lời:** Không nếu DEK được mã hóa cho key của attacker và attacker lấy được ciphertext tương ứng. Phải xác thực recipient key.

**Câu 13. Một HTTP 200 từ service nhận key đã chứng minh consumer dùng key mới chưa?**

**Trả lời:** Chưa. Cần acknowledgment đáng tin, operation/version checks, consumer cutover và giám sát old key usage.

**Câu 14. Vì sao xóa HMAC key khỏi message broker chưa chắc thu hồi được secret?**

**Trả lời:** Consumers, DLQ, snapshots, logs và backups có thể đã giữ bản sao; phải rotate secret và ngừng chấp nhận old version.

**Câu 15. Vì sao chỉ rewrap DEK không khắc phục DEK plaintext đã lộ?**

**Trả lời:** Kẻ tấn công vẫn có thể dùng DEK cũ giải mã ciphertext liên quan; cần đánh giá thay DEK/re-encrypt.

**Câu 16. Forward secrecy có bảo vệ secret được log ở endpoint không?**

**Trả lời:** Không. Forward secrecy có giới hạn trong mô hình lộ authentication key dài hạn sau phiên, không làm biến mất dữ liệu được log hoặc session key bị lộ.

**Câu 17. Khi KMS outage có nên gửi master key qua chat để tiếp tục hoạt động không?**

**Trả lời:** Không. Dùng DR/break-glass đã phê duyệt, audit, IAM tạm và giới hạn scope; không chuyển bí mật qua kênh thiếu bảo vệ.

**Câu 18. Có thể đóng incident “key qua HTTP” chỉ vì không thấy log của attacker không?**

**Trả lời:** Không. Phải xét khả năng thu thập, thời gian và phạm vi key, ciphertext/consumers, thay key và residual risk; nghe lén mạng có thể không tạo application log.

## 31. Checklist thiết kế key distribution an toàn

Trước khi triển khai hoặc kiểm toán đường phân phối key, hãy kiểm tra:

- **Loại khóa:** raw DEK/KEK, HMAC/PSK, private signing key, recovery share, wrapped DEK hay public key được phân biệt?
- **Key purpose:** Encrypt/Decrypt, Sign/Verify, MAC, Wrap/Unwrap hay agreement được định nghĩa?
- **Key generation:** material sinh bằng CSPRNG/KMS/HSM, không từ từ khóa dễ đoán?
- **Export policy:** key có thực sự cần xuất raw không; có thể dùng HSM handle/KMS operation/wrapped key thay thế?
- **Recipient identity:** đúng workload/đối tác/tenant và public-key binding đáng tin?
- **Channel:** mọi network hop có TLS/mTLS thích hợp, chain/hostname validation và cipher policy?
- **No downgrade:** không fallback HTTP, tắt TLS validation hoặc follow redirect ngoài allowlist?
- **Out-of-band secret leaks:** URL, logs, APM, proxy, CI, DLQ, backups có chứa raw key/token không?
- **Authorization:** business scope và KMS key usage/grants được kiểm tra độc lập với TLS identity?
- **Wrapping:** wrapped DEK được tạo bởi cơ chế được đánh giá, recipient/context binding đúng?
- **Metadata:** keyRef, version/epoch, recipient, purpose, expiry và replay protection được xử lý?
- **Asymmetric:** public key đúng identity, algorithm/key usage; không dùng signing key như encryption key?
- **Agreement:** nếu dùng ECDHE/X25519, giao thức có peer authentication và key schedule đúng?
- **SoD:** người đề nghị, người duyệt, operator và auditor có tách quyền hợp lý?
- **Runtime:** DEK/secret có tồn tại tối thiểu trong RAM/cache và không đi vào traces/heap dumps?
- **Queue:** broker consumer ACL, DLQ, replay/retention, exports và encrypted payload đã được đánh giá?
- **Audit:** có operation ID, actor, recipient, key material version, result, approval mà không log raw secret?
- **Rotation:** producer/consumer cutover, key version pinning, KEK rewrap hay DEK re-encrypt đúng?
- **Revocation:** grants/credentials, recipient trust, caches và old-key acceptance được xử lý?
- **Backup/DR:** encrypted DEK/key availability/restore được kiểm thử; không copy plaintext KEK để “dự phòng”?
- **Incident response:** có playbook khi lộ qua HTTP/chat/log/broker, phân biệt key types và residual risk?
- **Negative tests:** HTTP blocked, invalid TLS certificate, wrong recipient/tenant, replay, redirect, tampering, KMS outage được kiểm tra?

**Ghi nhớ:** **Không gửi key qua plaintext channel** không chỉ là thay HTTP bằng HTTPS. Đó là nguyên tắc **giảm tối đa số bản sao secret**, **xác thực đúng người nhận**, **giới hạn quyền sử dụng khóa**, **bảo vệ mọi hop và endpoint**, đồng thời ưu tiên **wrapped DEK, key reference, KMS/HSM và authenticated key agreement** thay cho việc phân phối raw KEK/private key. Khi đi cùng **IAM, SoD, envelope encryption, audit, rotation, revocation, backup/DR và incident response**, đường phân phối khóa mới thực sự đáp ứng mục tiêu bảo mật suốt vòng đời.


