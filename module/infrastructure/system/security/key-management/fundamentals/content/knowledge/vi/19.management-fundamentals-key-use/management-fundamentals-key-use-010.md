# Tách key theo môi trường – Cô lập khóa mật mã giữa development, testing, staging và production

**Tách key theo môi trường** là nguyên tắc **không chia sẻ cùng vật liệu khóa mật mã hoặc quyền sử dụng khóa vượt qua các ranh giới môi trường không được tin cậy tương đương nhau**. Thông thường, môi trường **development, testing, staging và production** phải có **khóa, danh tính workload, IAM policy, key registry, secret management, bản sao lưu và đường kiểm toán** được phân tách theo mức độ rủi ro. Khóa ở môi trường ít được bảo vệ hơn **không được trở thành đường truy cập dữ liệu hoặc giả mạo danh tính của production**.

Trong chương **Key use** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, phân tách môi trường không chỉ là đặt tên khóa `dev` và `prod` khác nhau. Nó là một **ranh giới bảo mật có hiệu lực ở nơi gọi phép toán mật mã**, liên kết với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, KMS/HSM, mật mã đối xứng, bất đối xứng, chữ ký số, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** **Một lần compromise ở development không được mặc nhiên cho phép Decrypt, Unwrap, Sign hay thay key policy của production.** Muốn đạt điều đó cần **key material độc lập + identity độc lập + quyền thực thi độc lập + dữ liệu/trust đúng môi trường**. Đổi alias, thêm tag `env=prod`, hoặc dùng hai biến cấu hình khác nhau **không đủ** nếu cuối cùng chúng cùng tham chiếu một secret hoặc một principal có quyền trên cả hai phía.

## 1. Môi trường là gì trong quản lý khóa?

“Môi trường” có thể chỉ **dev, test, staging, production**, nhưng trong kiến trúc bảo mật cần phân biệt ba khái niệm:

- **Deployment environment:** nơi triển khai một workload, chẳng hạn cluster development hoặc account production.
- **Cryptographic security domain (miền tin cậy mật mã):** tập hợp tài nguyên và principal được phép dùng **một họ khóa** theo một chính sách và mức bảo vệ nhất định.
- **Data/tenant boundary:** phạm vi dữ liệu của khách hàng, loại dữ liệu hoặc đơn vị nghiệp vụ; đây là ranh giới **khác với** môi trường triển khai.

Một account cloud, region, cluster Kubernetes hay namespace **không tự tương đương** với một security domain. Có thể có nhiều miền trong cùng account; cũng có thể có **production và production-DR** ở hai region nhưng cùng thuộc **một miền phục hồi production được phê duyệt**.

### 1.1. Mục tiêu khi tách key

1. **Giới hạn blast radius:** quyền truy cập hoặc vật liệu khóa bị lộ ở dev không dẫn tới decrypt dữ liệu production.
2. **Ngăn giả mạo danh tính:** khóa ký thử nghiệm không được các verifier production tin như production signer.
3. **Ngăn nhầm cấu hình:** workload staging không thể gọi nhầm KMS key/secret của production.
4. **Đơn giản hóa rotation:** có thể xoay khóa hoặc thử migration ở staging mà không thay material/trust của production.
5. **Bảo vệ dữ liệu thực:** dữ liệu production không được giải mã trong môi trường ít được bảo vệ chỉ để debug.
6. **Tách quyền vận hành:** developer/test automation không cần quyền `Decrypt`, `Sign` hoặc `ChangeKeyPolicy` trên production.
7. **Kiểm soát audit:** hoạt động production có owner, approval, monitoring và retention tương ứng với độ nhạy cảm.
8. **Phục hồi đáng tin:** key versions trong backup/DR phải được khôi phục đúng miền, không biến DR thành cửa hậu để lộ khóa.

### 1.2. Ví dụ có và không có cô lập

| Thành phần | Thiết kế sai | Thiết kế có phân tách |
| --- | --- | --- |
| **AES DEK** | Cùng `AES_KEY` hard-code cho dev/staging/prod. | Mỗi security domain có nguồn sinh DEK và key lifecycle riêng. |
| **KMS KEK** | `billing-kek` dùng chung tất cả môi trường. | KEK độc lập theo prod vs non-prod; key references được duyệt cho từng miền. |
| **Signing key** | Private key ký event dùng ở staging cũng ký production. | Signer key độc lập và verifier trust khác nhau. |
| **HMAC/PSK** | Token staging được prod chấp nhận vì cùng secret. | Secret, issuer/audience và acceptance policy tách biệt. |
| **KMS credential** | CI dev runner có quyền `kms:*` cả production. | Workload identity ngắn hạn, IAM chỉ trên tài nguyên được phép. |
| **Backup** | Snapshot production và KEK copy sang staging để test. | Dữ liệu giả/được khử nhạy cảm và mã hóa lại bằng khóa non-prod. |
| **Audit** | Chung log có secrets của mọi môi trường, quyền xem rộng. | Audit có phân quyền, scope, retention và correlation được bảo vệ. |

**Tách về logic** có thể là bước đầu, nhưng với production có rủi ro cao, thường cần **tách tài khoản/dự án KMS, role, service identity và khả năng quản trị**. Mức tách cụ thể phải dựa vào threat model và khả năng nền tảng.

## 2. Threat model: tại sao một key dùng chung giữa các môi trường nguy hiểm?

Hãy giả sử một developer được phép chạy code tùy ý trong dev. Nếu dev và prod cùng có **HMAC secret** hoặc cùng được cấp quyền KMS Sign, developer có thể tạo token hoặc chữ ký **được production coi là hợp lệ**. Từ đây, một lỗi cô lập môi trường trở thành lỗi xác thực và phân quyền thực tế.

~~~mermaid
flowchart TD
    DEV["Development: CI, debug, test fixtures"] --> BAD["Dùng chung key material hoặc principal"]
    STAGE["Staging: pre-release và test automation"] --> BAD
    BAD --> PROD["Production: dữ liệu thật, thanh toán, chữ ký"]
    BAD --> LOSS["Rủi ro: giải mã dữ liệu / giả mạo chữ ký / token / phá key"]
    DEV --> ID1["Workload identity dev"]
    ID1 --> K1["KMS/KEK/Signer dev"]
    STAGE --> ID2["Workload identity staging"]
    ID2 --> K2["KMS/KEK/Signer staging"]
    PROD --> ID3["Workload identity prod"]
    ID3 --> K3["KMS/KEK/Signer prod"]
~~~

Các nhánh riêng ở dưới chỉ an toàn khi **KMS và IAM thực sự từ chối** principal dev/staging dùng production key, không chỉ khi ứng dụng có câu lệnh `if (env == "prod")`.

### 2.1. Các đường tấn công cần kiểm soát

| Mối đe dọa | Điều có thể xảy ra | Biện pháp |
| --- | --- | --- |
| **Lộ khóa non-prod** | Shared KEK/DEK giúp giải mã ciphertext prod. | Key material độc lập, KMS/IAM scope và data-key separation. |
| **Signer confusion** | Chữ ký staging được Ledger production chấp nhận. | Signer/issuer/trust registry/audience riêng, không chỉ đổi `kid`. |
| **Token/MAC confusion** | JWT/HMAC token dev được API prod xác thực. | Secret độc lập + xác minh issuer, audience, algorithm, environment. |
| **CI credential pivot** | Runner test có thể gọi KMS prod. | Phân biệt IAM role/account, hạn chế OIDC trust conditions và network. |
| **Config/key alias injection** | Một request hoặc deployment chỉ sang key production. | Approved registry từ nguồn tin cậy, kiểm tra canonical resource IDs. |
| **Snapshot dữ liệu thật** | Staging nhận ciphertext, wrapped DEK hoặc plaintext prod. | Chỉ cấp dữ liệu đã được phê duyệt, sanitization/re-encryption đúng cách. |
| **Recovery bypass** | HSM/DR backup được mở từ nhóm có quyền non-prod. | Recovery domain, quorum và quyền độc lập. |
| **Cross-env administration** | Key admin dev sửa policy hoặc schedule deletion của prod. | Tách quyền quản trị, approval và audit ngoài miền prod. |
| **Metadata rollback** | Restore cấu hình non-prod làm prod trỏ về key cũ. | Signed/approved registry, phiên bản và state chống rollback. |
| **Debug/observability leak** | Dev đọc log chứa production DEK hoặc KMS token. | Không log secret, giới hạn audit/log access và export. |

### 2.2. Phân tách không chỉ bảo vệ tính bí mật

Các hậu quả quan trọng còn gồm:

- **Integrity:** attacker có quyền ký ở test tạo event hợp lệ dưới trust của prod.
- **Authenticity:** certificate/JWKS/trust store của staging gắn nhầm với issuer prod.
- **Availability:** người có quyền ở dev vô tình hoặc cố ý `DisableKey`/`ScheduleDeletion` prod.
- **Recoverability:** thao tác rotation ở staging làm thay material của KEK còn cần cho backup prod.
- **Auditability:** tất cả thao tác dùng chung principal, không xác định được môi trường nào đã gọi Sign/Decrypt.

Vì vậy “tách key” cần đồng thời tách **đường quản trị và đường sử dụng khóa**.

## 3. Chọn ranh giới tách: môi trường, tenant và purpose

Một hệ thống có thể có:

~~~text
security-domain: production
  account/project: prod
  service: Billing
  tenant: A/B/C
  KEK: billing-production-kek
  DEK: theo invoice hoặc partition
  purpose: DATA_ENCRYPTION

security-domain: staging
  account/project: nonprod-staging
  service: Billing
  tenant: synthetic/test
  KEK: billing-staging-kek
  DEK: chỉ dữ liệu thử
  purpose: DATA_ENCRYPTION

security-domain: production-dr
  account/region: recovery zone
  membership: production recovery trust domain, theo approval
  KEK/replica/re-wrap: tùy provider và DR plan
~~~

Ví dụ này phân biệt **môi trường triển khai** với **miền mật mã**. Production-DR có thể được phép dùng khóa production thông qua replication/provider-native key relationship **nếu được thiết kế như một phần miền production**, có IAM/DR/quorum và kiểm toán tương đương. Không được gắn nhãn DR để đưa production secret vào một lab staging không có kiểm soát.

### 3.1. Tách đến mức nào là đủ?

| Phạm vi | Khi nào cân nhắc | Điều phải bảo vệ |
| --- | --- | --- |
| **Khác DEK theo object/partition** | Hạn chế tác động khi DEK lộ; key usage/nonce budgets. | DEK lineage, wrapped DEK, ciphertext metadata. |
| **Khác KEK theo môi trường** | Mặc định hợp lý giữa dev/test/staging và production. | KMS identities, policy, key usage, account/project. |
| **Khác KEK theo tenant** | Dữ liệu nhiều khách hàng hoặc yêu cầu isolation mạnh. | Tenant mapping, least privilege và chi phí vận hành. |
| **Khác signer theo môi trường** | Event, JWT, release signing hoặc mTLS. | Trust anchor, issuer/audience, rotation/revocation. |
| **Khác CA/trust root theo môi trường** | Tránh chứng chỉ test được tin ở prod. | PKI namespace, certificate policies, issuance/approval. |
| **Tách KMS account/project/admin** | Production có yêu cầu nghiêm ngặt. | Đường leo thang IAM, backup/DR và audit quyền quản trị. |
| **Production recovery domain** | RTO/RPO yêu cầu đọc được dữ liệu prod khi disaster. | Quan hệ backup/replication có chủ đích và thử nghiệm. |

**Không có định mức một-key-mỗi-env đúng cho tất cả.** Bài toán là xác định **đường mà key ở miền kém tin cậy có thể cấp quyền trên dữ liệu/danh tính thuộc miền nhạy cảm hơn**, rồi chặn bằng cơ chế thực thi.

### 3.2. Một region hay namespace không tự tạo key isolation

Hai workload ở namespace khác nhau vẫn có thể dùng cùng IAM principal hoặc cùng KMS key. Hai key objects ở hai region có thể là **replica cùng vật liệu khóa** nếu provider hỗ trợ; tên khác nhau không chứng minh entropy độc lập.

Muốn xác nhận tách key cần kiểm tra **origin, canonical key IDs, phiên bản, IAM principals, key policy, grants, key usage và quan hệ replication/backup**. Với key non-exportable, không cần xuất key bytes để “so sánh khóa”; dùng **metadata có thẩm quyền và kiến trúc provisioning đã được xác minh**.

## 4. Tách vật liệu khóa theo từng loại

### 4.1. DEK dùng AES-GCM

**DEK** là khóa trực tiếp mã hóa dữ liệu. Môi trường dev và production không nên có cùng plaintext DEK, kể cả khi:

- Cả hai cùng dùng thuật toán `AES-256-GCM`.
- Cùng tên biến `BILLING_DEK`.
- Cùng tên alias `current-data-key`.
- Cùng dữ liệu test trông giống dữ liệu thật.

Nếu dùng **data-key caching**, phải tách cache theo cryptographic domain, tenant/purpose và hạn sử dụng; không truyền cached DEK từ pod prod sang worker staging. Mỗi DEK có giới hạn sử dụng và **nonce uniqueness** riêng; không khởi động lại một bộ nonce counter rồi dùng lại cùng key.

**Sử dụng khác key material không tự chữa lỗi AEAD**. AES-GCM vẫn cần nonce không lặp theo cùng DEK, tag verification, AAD đúng và chính sách giới hạn dữ liệu theo key.

### 4.2. KEK và root/master key của KMS

**KEK** dùng để wrap/unwrap DEK. Nếu staging và production cùng dùng KEK, một principal staging có quyền KMS `DecryptDataKey` rộng có thể mở DEK của production nếu có wrapped blob và không có context/policy ngăn chặn.

Khuyến nghị theo mục tiêu:

1. Sinh KEK **độc lập** trong miền quản lý riêng hoặc security boundary được phê duyệt.
2. Chỉ cấp `GenerateDataKey`, `Wrap`, `DecryptDataKey`, `Unwrap` cho workload đúng purpose/miền.
3. Không cấp mặc định quyền `ChangeKeyPolicy`, `ExportKey` hoặc `ScheduleDeletion` cho application/CI.
4. Tách **KMS administrators** của production khỏi quyền chỉnh khóa test.
5. Kiểm tra **provider-native replication**: chỉ dùng chung key material trong các recovery zones thuộc **miền production được phê duyệt**, không với staging.
6. Key inventory phải ghi **domain, owner, material origin, key ID/version, predecessor, usage và dependencies**.

**Key alias/tag không thay ranh giới KMS.** Một KMS policy cho phép principal dev dùng key prod vẫn là lỗi dù alias hiển thị `prod-only`.

### 4.3. Private signing key và verifier trust

Nếu Payment Service ký sự kiện bằng **Ed25519**, private signing key production phải tách với staging/dev. Những người có quyền tạo dữ liệu test không được tạo chữ ký mà Ledger production chấp nhận như sự kiện thanh toán thật.

~~~mermaid
flowchart LR
    STAGESIGN["Staging signer S-stage"] --> STAGETRUST["Ledger staging trust registry"]
    PRODSIGN["Production signer S-prod"] --> PRODTRUST["Ledger production trust registry"]
    STAGESIGN -. "PHẢI BỊ TỪ CHỐI" .-> PRODTRUST
    PRODSIGN -. "KHÔNG TỰ CHO PHÉP" .-> STAGETRUST
~~~

Verifier cần kiểm:

- **Trusted issuer** và **key ID** từ registry/JWKS/PKI đã xác thực.
- **Audience, environment, tenant và purpose**, không chỉ signature toán học.
- **Algorithm/key usage** đúng; không chấp nhận key do request tự khai.
- **Revocation và version** tại thời điểm xử lý.
- **Event ID, replay/idempotency** đối với giao dịch nghiệp vụ.

**Public key không phải secret**, nhưng trust binding giữa public key và môi trường cần chính xác. Một public key stage có thể công khai mà vẫn **không được** là trust anchor của prod.

### 4.4. HMAC/JWT signing secret, PSK, pepper và session keys

Nếu một `HS256` JWT signing secret được dùng cho mọi môi trường, token do môi trường dev phát hành có thể xác thực thành công ở production khi verifier bỏ qua issuer/audience/claims. Vì vậy:

- Dùng **HMAC/PSK secrets riêng** theo môi trường và purpose.
- Gắn `iss`, `aud`, thời hạn, tenant/workload identity vào token/protocol và **xác minh đầy đủ**.
- Không để staging có quyền tạo production session hoặc thay JWT trust config.
- Với **password pepper**, xem nó là secret trong secret manager/KMS theo policy; đừng dùng cùng pepper production trong test logs hoặc fixtures.
- Với **session keys**, dùng TLS/AKE chuẩn; session secrets do giao thức dẫn xuất theo phiên, không hard-code “test-session-key” dùng lại ở prod.

Nếu dùng JWT chữ ký bất đối xứng, **production private signing key** cũng phải tách khỏi staging và consumer trust phải kiểm issuer. Thay algorithm từ HMAC sang bất đối xứng **không tự giải quyết** lỗi trộn môi trường nếu chính sách verifier sai.

### 4.5. mTLS certificates và PKI roots

- Môi trường có thể dùng **CA hoặc policy/namespace cấp chứng chỉ riêng**.
- Production server/client phải xác minh đúng **service identity, certificate chain, key usage và trust domain**.
- Nếu nhiều môi trường dùng chung CA, cần chính sách identity namespace, SAN/SPIFFE ID, issuance quyền hạn và verifier restrictions đủ chặt.
- Không đưa private key mTLS production vào development image để test.
- Không tắt hostname/certificate validation để staging nói chuyện với production KMS.

**mTLS xác thực workload**, không thay authorization trên từng key/tenant. Một client có chứng chỉ hợp lệ nhưng từ **môi trường staging** vẫn không nên được cấp Decrypt production chỉ vì chain tin cậy.

## 5. KMS/HSM: cấu trúc cô lập hiệu quả

Một mô hình tham khảo:

~~~mermaid
flowchart TB
    subgraph NONPROD["Miền non-production"]
      DEV["Dev/test workloads"] --> IDDEV["Identity non-prod"]
      STAGE["Staging workloads"] --> IDSTG["Identity staging"]
      IDDEV --> KMSTEST["KMS test keys"]
      IDSTG --> KMSSTG["KMS staging keys"]
    end
    subgraph PRODUCTION["Miền production"]
      PROD["Production workloads"] --> IDPROD["Identity production"]
      IDPROD --> KMSPROD["KMS prod KEK / Signer"]
      KMSPROD --> AUDITPROD["Audit độc lập / SOC"]
    end
    IDDEV -. "DENY" .-> KMSPROD
    IDSTG -. "DENY" .-> KMSPROD
    IDPROD -. "DENY theo mặc định" .-> KMSSTG
~~~

### 5.1. Các lớp bảo vệ

| Lớp | Điều cần triển khai | Điều lớp đó **không** thay thế |
| --- | --- | --- |
| **Cloud account/project** | Tách principal, administrative boundary và quota khi phù hợp. | IAM policy sai vẫn có thể cấp quyền cross-account. |
| **Workload identity** | Identity ngắn hạn, gắn đúng account/namespace/service. | Không tự xác định user cuối có được đọc dữ liệu không. |
| **KMS key policy / IAM** | Resource + action + principal + context/conditions có hỗ trợ. | Không sửa lỗi plaintext DEK từng bị lộ trong app. |
| **HSM key custody** | Non-exportable/secure import, quyền Sign/Unwrap theo policy. | API Sign/Decrypt vẫn có thể bị lạm dụng nếu caller được cấp quá rộng. |
| **Approved key registry** | Mapping logical purpose/env → canonical key ID và metadata. | Registry label không thay KMS IAM thực thi. |
| **Data authorization** | Kiểm user/tenant/object trước KMS và DB. | Không thay bảo vệ raw key trong RAM/log. |
| **Audit & monitoring** | Detect cross-env operations và privileged changes. | Audit không tự chặn tác vụ đang diễn ra. |
| **CI/CD policy** | Promotion rõ, không truyền secret xuyên môi trường. | Không thay runtime IAM hoặc DR kiểm thử. |

### 5.2. KMS key references: tên khác chưa chắc khóa khác

Ví dụ cấu hình minh họa:

~~~properties
# Tham chiếu key, không phải raw key material.
dev.billing.kekRef=kms://nonprod/dev/billing/kek
staging.billing.kekRef=kms://nonprod/staging/billing/kek
prod.billing.kekRef=kms://production/billing/kek
~~~

Những chuỗi trên chỉ là **logical references giả**, không phải URI KMS chuẩn của một provider. Trong hệ thống thật, registry phải lưu **canonical provider key ID, account/project, key usage, state, owner và approved environment/domain**; kiểm tra chúng với nguồn có thẩm quyền.

Không cho **request body, header hoặc biến cấu hình do user thao túng** tự chọn arbitrary KMS endpoint hoặc key ID. Một “prod-looking alias” trong account test cũng không được coi là production key hợp lệ.

### 5.3. Tách quyền dùng khóa và quyền quản trị khóa

Một IAM principal **production application** có thể cần `GenerateDataKey`/`DecryptDataKey` trên KEK thuộc Billing-prod, nhưng không được `ScheduleDeletion`, sửa grants hoặc export private signing key.

Một **developer** có thể tạo và xoay key dev/test nhưng không có quyền đổi key policy prod. Một **production security approver** có thể phê duyệt rotation nhưng không mặc định có quyền giải mã toàn bộ dữ liệu khách hàng.

Khi HSM hỗ trợ quorum/dual control cho recovery hoặc key import, thiết kế phải dùng **cơ chế thật của sản phẩm**. Hai lần click từ cùng identity không thay thế phê duyệt độc lập.

## 6. Key inventory và lineage theo môi trường

Để chứng minh key separation, inventory nên theo dõi:

| Trường | Tác dụng |
| --- | --- |
| **Key family/ID/version** | Định danh khóa và thế hệ vật liệu khóa. |
| **Cryptographic domain** | Production, non-prod, staging hoặc production recovery domain đã định nghĩa. |
| **Cloud account/project/region** | Nơi quản lý key; không tự chứng minh material isolation. |
| **Owner và purpose** | Ai chịu trách nhiệm và key được phép dùng cho gì. |
| **Algorithm/key usage** | AES-GCM DEK, wrap KEK, Ed25519 Sign, HMAC... |
| **Material origin** | Sinh trong KMS/HSM, BYOK/import, replicated hoặc recovery source. |
| **Custody/exportability** | Non-exportable, key import policy và backup path. |
| **IAM principals / policy version** | Actor nào được phép dùng và quản trị key. |
| **Predecessor/successor** | Quan hệ key rotation; không nhầm với relation wrap. |
| **WRAPS / ENCRYPTS / SIGNS** | Dependency graph tới DEK, dataset, events, artifacts. |
| **Backup/DR dependencies** | Snapshot nào cần material version nào. |
| **Status/cryptoperiod** | Active, retired, disabled, pending deletion và thời điểm. |

### 6.1. Key names, tags và alias không phải bằng chứng độc lập

Một key được gắn tag `environment=prod` vẫn có thể là imported material vốn đã dùng ở staging. Hai key objects khác ID có thể **chứa cùng bytes** nếu tổ chức import key giống nhau vào hai miền.

Để phân tách thật:

1. Sinh key **riêng** từ nguồn entropy tin cậy trong từng domain theo policy.
2. Không copy raw secret/seed hoặc key backup từ prod sang non-prod.
3. Kiểm soát quyền tạo/import/replicate key, tránh người quản trị non-prod thao tác trên prod material.
4. Kiểm tra canonical identifiers và metadata provider, không dùng tag một mình để cấp quyền.
5. Theo dõi mọi **đường replication, BYOK, migration và secure backup** có thể làm key đi qua domain.

**Không xuất private key hoặc KEK để so sánh hai môi trường có trùng bytes hay không.** Kiểm bằng provenance, provisioning records, provider semantics và audit.

## 7. Envelope encryption và tách DEK/KEK xuyên môi trường

Một mô hình thường dùng:

~~~mermaid
sequenceDiagram
    participant App as Billing production
    participant IAM as IAM/KMS policy production
    participant KMS as Production KMS
    participant DB as Production DB
    App->>IAM: Identity production + approved keyRef
    IAM->>KMS: GenerateDataKey(KEK-prod, context prod)
    KMS-->>App: DEK tạm + wrapped DEK prod
    Note over App: AES-GCM, nonce mới, AAD gắn domain/tenant/object
    App->>DB: Ciphertext/tag + nonce + wrapped DEK + keyRef/version
    DB-->>App: Record được cấp quyền
    App->>IAM: DecryptDataKey/Unwrap theo context
    IAM->>KMS: Chỉ resource/operation được phép
    KMS-->>App: DEK tạm nếu policy cho phép
    Note over App: Verify tag trước khi dùng plaintext
~~~

Một môi trường staging riêng phải gọi **KMS staging** và dùng **wrapped DEK staging**, không lấy plaintext DEK hoặc KEK của production để dùng thử.

### 7.1. AAD và encryption context giúp giữ đúng domain

Ví dụ AAD của dữ liệu Billing:

~~~text
format         = "billing-aead-v1"
securityDomain = "production"
tenant         = "tenant-A"
object         = "invoice-123"
purpose        = "billing-invoice"
~~~

Ví dụ KMS encryption context khi bọc DEK:

~~~text
securityDomain = "production"
tenant         = "tenant-A"
object         = "invoice-123"
purpose        = "billing-dek-wrap-v1"
~~~

**AES-GCM AAD** xác thực metadata cùng ciphertext nếu các bytes AAD ở lúc decrypt trùng lúc encrypt. **KMS encryption context** có thể ràng buộc thao tác wrap/unwrap theo khả năng provider, đồng thời có thể xuất hiện trong audit nên không được coi là secret.

Nhưng cần hiểu đúng:

- **AAD/context không thay IAM và application authorization.** Nếu cùng principal có quyền prod và kẻ tấn công kiểm soát được context, họ vẫn có thể gọi sai thao tác.
- Gắn **domain ổn định** vào AAD giúp phát hiện việc chuyển ciphertext giữa môi trường có domain khác mà không làm lại encryption.
- Nếu mục tiêu là **khôi phục production ở production-DR**, domain trong AAD thường nên là **cryptographic domain production**, không nhất thiết là region hoặc tên cluster vật lý.
- Không gắn một thuộc tính **dễ thay** như alias current hoặc vùng đang chạy vào AAD nếu migration dự kiến không re-encrypt; đổi AAD sẽ làm GCM tag fail.
- Nếu thay domain khi đưa dữ liệu vào staging, cần **decrypt theo quyền trong prod → sanitize → re-encrypt dưới key staging với AAD staging**, không sửa metadata rồi mong tag vẫn hợp lệ.

### 7.2. Lưu metadata theo domain

Một record minh họa:

~~~yaml
schemaVersion: "billing-envelope-v1"
cryptographicDomain: "production"
tenantRef: "tenant-A"
objectRef: "invoice-123"
dataAlgorithm: "AES-256-GCM"
kekRef: "kms://production/billing/kek-v4"
keyVersionRef: "provider-or-registry-version"
nonce: "<encoded-nonce>"
ciphertextWithTag: "<encoded-ciphertext-tag>"
wrappedDek: "<encoded-kms-data-key>"
~~~

Dữ liệu giả này **không chứa key rõ**. Một số provider mã hóa metadata key vào blob và không công khai material version; hãy dùng đúng SDK/format thực tế. **Key ID/version, nonce/tag, AAD schema, wrapped DEK và ciphertext phải nhất quán** để khôi phục hoặc rotate.

### 7.3. Nếu một bản ghi prod được copy sang staging thì sao?

Nếu staging không có quyền unwrap KEK-prod và không có plaintext DEK, việc copy blob **không tự cho staging khả năng giải mã**. Đó là một lớp phòng vệ hữu ích, **không đồng nghĩa bản copy được phép**: ciphertext có thể chứa metadata nhạy cảm, còn môi trường staging có nguy cơ bị cấp nhầm quyền sau này.

Vì vậy data governance vẫn phải kiểm soát **data movement**, retention và mục đích; **“không decrypt được” không phải giấy phép tự do đưa dữ liệu production sang test**.

## 8. Java 17: kiểm tra miền khóa trước khi mã hóa/giải mã

Ví dụ sau mô phỏng **đường tích hợp KMS** với các lớp độc lập:

- `TrustedRuntime`: cung cấp **environment, cryptographic domain và workload identity** đã được xác thực từ nền tảng triển khai (không lấy từ request body hoặc một biến `ENV` tự khai).
- `ApprovedRegistry`: ánh xạ domain + purpose tới **key reference/canonical key ID/account** đã được duyệt.
- `KmsPort`: SDK adapter truy cập KMS, lấy metadata có thẩm quyền, tạo/giải bọc DEK. **KMS IAM vẫn phải thực thi quyền tại API thật**.
- `DataAuthorization`: kiểm tra principal có quyền với đúng tenant/object.
- `EnvironmentBoundEnvelopeService`: chỉ dùng một key object nếu khớp domain, canonical identity, account và usage; dùng AES-GCM với AAD chứa domain ổn định.

> **Phạm vi của code:** Minh họa nguyên tắc **không hard-code raw secret, không tin client chọn môi trường, chặn sai canonical key, kiểm tra app authorization và dùng KMS**. Đây **không phải SDK production**. Chỉ có interfaces cho hệ danh tính và KMS, vì mỗi provider có semantics/IAM/version khác nhau. Đừng triển khai interface bằng một secret cố định trong code.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EnvironmentBoundEnvelopeService {
    private static final String PURPOSE = "billing-invoice";
    private static final String FORMAT = "billing-envelope-v1";
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int KEY_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    enum Environment { DEV, TEST, STAGING, PRODUCTION }

    // Nguồn identity phải dựa vào attestation/service identity
    // của nền tảng; các field không do HTTP client tự đặt.
    record RuntimeIdentity(
            Environment environment,
            String cryptographicDomain,
            String workloadId) {}

    interface TrustedRuntime {
        RuntimeIdentity currentIdentity();
    }

    record ApprovedBinding(
            Environment environment,
            String domain,
            String keyRef,
            String canonicalKeyId,
            String providerAccountId) {}

    interface ApprovedRegistry {
        ApprovedBinding activeKey(
                Environment environment, String purpose);

        ApprovedBinding approvedForDecrypt(
                Environment environment, String domain, String keyRef);
    }

    record ProviderKeyMetadata(
            String canonicalKeyId,
            String providerAccountId,
            String algorithm,
            boolean enabled,
            boolean canGenerateDataKey,
            boolean canUnwrapDataKey) {}

    record DataKey(
            byte[] plaintextDek,
            byte[] wrappedDek,
            String keyRef) {}

    interface KmsPort {
        ProviderKeyMetadata describeKey(String keyRef)
                throws Exception;

        DataKey generateDataKey(
                String keyRef, Map<String, String> context)
                throws Exception;

        byte[] unwrapDataKey(
                String keyRef, byte[] wrappedDek,
                Map<String, String> context) throws Exception;
    }

    interface DataAuthorization {
        // Quyền principal + object/tenant phải dựa trên
        // session/workload identity đã xác thực.
        void requireAllowed(String workloadId, String tenant,
                            String objectId, String operation);
    }

    // Record chứa byte[] không tự deep immutable:
    // production phải defensive-copy ở mọi trust boundary.
    record EncryptedRecord(
            String domain, String tenant, String objectId,
            String keyRef, byte[] wrappedDek, byte[] nonce,
            byte[] ciphertextWithTag) {}

    private final TrustedRuntime runtime;
    private final ApprovedRegistry registry;
    private final KmsPort kms;
    private final DataAuthorization authorization;

    public EnvironmentBoundEnvelopeService(
            TrustedRuntime runtime, ApprovedRegistry registry,
            KmsPort kms, DataAuthorization authorization) {
        this.runtime = Objects.requireNonNull(runtime);
        this.registry = Objects.requireNonNull(registry);
        this.kms = Objects.requireNonNull(kms);
        this.authorization = Objects.requireNonNull(authorization);
    }

    private RuntimeIdentity trustedIdentity() {
        RuntimeIdentity id = runtime.currentIdentity();
        if (id == null || id.environment() == null
                || id.cryptographicDomain() == null
                || id.cryptographicDomain().isBlank()
                || id.workloadId() == null
                || id.workloadId().isBlank()) {
            throw new SecurityException("Missing trusted workload identity");
        }
        return id;
    }

    private void verifyBinding(
            RuntimeIdentity id, ApprovedBinding binding,
            boolean forEncrypt) throws Exception {
        if (binding == null
                || binding.environment() != id.environment()
                || !Objects.equals(binding.domain(),
                                   id.cryptographicDomain())
                || binding.keyRef() == null || binding.keyRef().isBlank()
                || binding.canonicalKeyId() == null
                || binding.providerAccountId() == null) {
            throw new SecurityException("Unapproved environment key");
        }

        // Đối chiếu canonical identity/account do provider trả về,
        // không chỉ kiểm tra alias hay tag env tự khai.
        ProviderKeyMetadata meta = kms.describeKey(binding.keyRef());
        if (meta == null || !meta.enabled()
                || !binding.canonicalKeyId().equals(
                        meta.canonicalKeyId())
                || !binding.providerAccountId().equals(
                        meta.providerAccountId())
                || !"AES-256".equals(meta.algorithm())
                || (forEncrypt && !meta.canGenerateDataKey())
                || (!forEncrypt && !meta.canUnwrapDataKey())) {
            throw new SecurityException("KMS key metadata mismatch");
        }
    }

    private static Map<String, String> context(
            String domain, String tenant, String objectId) {
        return Map.of(
                "domain", domain,
                "tenant", tenant,
                "object", objectId,
                "purpose", PURPOSE);
    }

    private static byte[] aad(
            String domain, String tenant, String objectId)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        // Domain ở đây phải ổn định qua các region/DR thuộc
        // cùng miền production theo thiết kế đã phê duyệt.
        for (String field : new String[] {
                FORMAT, domain, PURPOSE, tenant, objectId }) {
            byte[] b = field.getBytes(StandardCharsets.UTF_8);
            out.writeInt(b.length);
            out.write(b);
        }
        out.flush();
        return buffer.toByteArray();
    }

    public EncryptedRecord encrypt(
            String tenant, String objectId, byte[] plaintext)
            throws Exception {
        Objects.requireNonNull(plaintext);
        if (tenant == null || tenant.isBlank()
                || objectId == null || objectId.isBlank()) {
            throw new SecurityException("Invalid object reference");
        }

        RuntimeIdentity id = trustedIdentity();
        authorization.requireAllowed(
                id.workloadId(), tenant, objectId, "ENCRYPT");
        ApprovedBinding binding = registry.activeKey(
                id.environment(), PURPOSE);
        verifyBinding(id, binding, true);

        DataKey generated = kms.generateDataKey(
                binding.keyRef(),
                context(id.cryptographicDomain(), tenant, objectId));
        byte[] dek = generated == null ? null : generated.plaintextDek();

        try {
            if (dek == null || dek.length != KEY_BYTES
                    || generated.wrappedDek() == null
                    || generated.wrappedDek().length == 0
                    || !binding.keyRef().equals(generated.keyRef())) {
                throw new SecurityException("Invalid KMS data key");
            }

            // Một DEK mới cho mỗi object-encryption trong demo;
            // provider/adapter phải thực sự bảo đảm điều này.
            byte[] nonce = new byte[NONCE_BYTES];
            RANDOM.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(
                    id.cryptographicDomain(), tenant, objectId));
            byte[] ciphertextWithTag = cipher.doFinal(plaintext);

            return new EncryptedRecord(
                    id.cryptographicDomain(), tenant, objectId,
                    binding.keyRef(), generated.wrappedDek().clone(),
                    nonce, ciphertextWithTag);
        } finally {
            // Giảm thời gian giữ key trên mảng này; JVM/provider
            // có thể giữ các bản sao không xóa được tuyệt đối.
            if (dek != null) Arrays.fill(dek, (byte) 0);
        }
    }

    public byte[] decrypt(
            String tenant, String objectId, EncryptedRecord record)
            throws Exception {
        Objects.requireNonNull(record);
        RuntimeIdentity id = trustedIdentity();
        authorization.requireAllowed(
                id.workloadId(), tenant, objectId, "DECRYPT");

        if (tenant == null || tenant.isBlank()
                || objectId == null || objectId.isBlank()
                || !id.cryptographicDomain().equals(record.domain())
                || !tenant.equals(record.tenant())
                || !objectId.equals(record.objectId())
                || record.keyRef() == null
                || record.wrappedDek() == null
                || record.wrappedDek().length == 0
                || record.nonce() == null
                || record.nonce().length != NONCE_BYTES
                || record.ciphertextWithTag() == null
                || record.ciphertextWithTag().length < TAG_BITS / 8) {
            throw new SecurityException("Wrong data domain or format");
        }

        // Registry cho phép predecessor/version cũ còn hợp lệ
        // trong cùng domain, không tự fallback sang key của prod.
        ApprovedBinding binding = registry.approvedForDecrypt(
                id.environment(), id.cryptographicDomain(),
                record.keyRef());
        verifyBinding(id, binding, false);
        if (!record.keyRef().equals(binding.keyRef())) {
            throw new SecurityException("Key reference mismatch");
        }

        byte[] dek = kms.unwrapDataKey(
                binding.keyRef(), record.wrappedDek(),
                context(id.cryptographicDomain(), tenant, objectId));
        try {
            if (dek == null || dek.length != KEY_BYTES) {
                throw new SecurityException("Invalid unwrapped DEK");
            }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, record.nonce()));
            cipher.updateAAD(aad(
                    id.cryptographicDomain(), tenant, objectId));
            // doFinal phải xác minh tag trước khi trả plaintext.
            return cipher.doFinal(record.ciphertextWithTag());
        } finally {
            if (dek != null) Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

### 8.1. Code bảo vệ điều gì?

1. **Không hard-code raw key:** ứng dụng không chứa DEK/KEK/private key cố định.
2. **Không cho client tự chọn env:** `TrustedRuntime` là **nguồn identity được xác thực từ platform**, không lấy từ URL/header hoặc `ENV=production` do caller tự khai.
3. **Key registry có thẩm quyền:** tham chiếu đang active và các key predecessor được phép Decrypt do chính sách server-side cung cấp.
4. **Canonical KMS validation:** kiểm key ID/account/algorithm/usage/enablement từ provider, không chỉ alias/tag.
5. **IAM thực thi ở KMS:** ứng dụng không thể tự cấp quyền bằng việc thay biến Java; SDK/KMS phải từ chối service identity không có quyền.
6. **Application authorization:** workload vẫn phải có quyền đối với tenant/object **trước** khi gọi KMS.
7. **Context và AAD cùng domain:** bản mã production được ràng buộc với **domain production ổn định**, không mang sang staging rồi tự decrypt.
8. **Fail closed:** key reference/metadata/tenant/domain sai, GCM tag sai, IAM AccessDenied hoặc KMS lỗi không có fallback hard-coded.
9. **Key hygiene:** DEK rõ tồn tại tạm trong RAM, không log, cố gắng zero mảng sau thao tác.
10. **Old-key read có policy:** migration/rotation vẫn có thể đọc ciphertext cũ bằng **approved predecessors**, không phải chọn mọi KEK.

### 8.2. Code **chưa** đủ cho production

- `TrustedRuntime` phải được triển khai bằng **trusted service identity/attestation hoặc cơ chế platform đáng tin**. Một `System.getenv("ENV")` có thể bị cấu hình sai, không phải chứng cứ chống attacker.
- `ApprovedRegistry` cần **integrity, phân quyền, source of truth và version**, đồng thời tách quyền sửa policy khỏi developer non-prod.
- `KmsPort` phải dùng SDK provider, xác minh KMS endpoint, IAM auth, key metadata và encryption context semantics. Không phải provider nào trả keyRef/algorithm như interface minh họa.
- Tên `AES-256` là **giá trị contract giả định** giữa adapter và ứng dụng; metadata KMS thật có thể dùng tên/loại khác, cần map chính xác.
- Nếu bản ghi dùng **material version** hoặc format khác theo provider, cần lưu/đọc đúng key version; không tin `current alias` thay lịch sử.
- `DataAuthorization` không biết user cuối chỉ từ workload ID; **implementation thật** cần user/session/tenant permission được xác thực ở lớp API.
- Các `record` chứa `byte[]` **không deep immutable**. Cần defensive copies, giới hạn input size, transaction và persistence an toàn.
- `Arrays.fill` không bảo đảm xóa mọi bản sao plaintext DEK trong JCE/JVM hoặc crash dump.
- Nonce ngẫu nhiên 96 bit là minh họa phù hợp khi **KMS sinh DEK mới cho từng lần encrypt**. Khi cache/reuse DEK, phải quản lý **nonce uniqueness và key usage budgets**.
- Không có rate limiting, retry/backoff, timeout, circuit breaker, DR/key inventory integration, audit pipeline hoặc complete unit/integration tests.
- **Không chạy hoặc thay thế KMS bằng fake production credentials** để kiểm tra demo; mục tiêu là thấy nơi phải enforce domain, không tuyên bố code là protocol production.

## 9. Chính sách IAM và quyền điều hành theo môi trường

Một thiết kế cần bảo đảm hai điều độc lập:

1. **Identity dev/staging không gọi được `Decrypt`, `Unwrap`, `Sign` trên production key**.
2. **Dữ liệu/ứng dụng production không tin token, chữ ký hoặc key material phát hành từ non-prod**, kể cả khi attacker có access vật lý tới non-prod key.

### 9.1. Ma trận quyền ví dụ

| Principal | Key non-prod | Key production | Hành động quản trị prod |
| --- | --- | --- | --- |
| **developer-dev** | Được làm thử nghiệm theo policy. | **Deny**. | **Deny**. |
| **test-runner** | Được dùng key test trên dữ liệu giả. | **Deny**. | **Deny**. |
| **staging-service** | Chỉ key staging/approved usage. | **Deny** theo mặc định. | **Deny**. |
| **production-billing** | Không cần theo mặc định. | GenerateDataKey/DecryptDataKey đúng Billing KEK. | **Deny** Delete/ChangePolicy/Export. |
| **production-payment** | Không cần theo mặc định. | Sign đúng Payment signing key. | **Deny** KeyDeletion/Export. |
| **production-security-operator** | Theo nhiệm vụ riêng. | Quản trị key lifecycle có phê duyệt. | Chỉ trong scope và workflow. |
| **DR-recovery-workload** | Không mặc định. | Quyền phục hồi **giới hạn cho miền production** khi có sự cố. | Không cấp vô hạn. |
| **auditor/SOC** | Đọc audit đã lọc theo quyền. | Đọc audit đã lọc theo quyền. | Không có quyền dùng raw key/Sign/Decrypt. |

**Deny phải được hiện thực bằng policy thật**, không phải chỉ là ô bảng. Một principal có quyền **tạo grants, assume role, sửa IAM policy hoặc key policy** vẫn có thể leo thang quyền gián tiếp; review phải xét **đường leo thang**, không chỉ các API crypto trực tiếp.

### 9.2. CI/CD OIDC và environment promotion

Pipeline deployment thường dùng **OIDC/federated workload identity** hoặc hệ tương đương để nhận credential ngắn hạn. Tuy nhiên:

- Role production cần ràng buộc **repo, branch/tag, workflow/job, protected environment hoặc provenance** theo khả năng nền tảng.
- PR từ untrusted fork không được nhận token có thể gọi production KMS.
- Pipeline test không được in secret hoặc copy KMS response vào artifacts.
- Promotion phải chuyển **code và cấu hình đã phê duyệt**, **không copy raw key material** từ staging sang prod.
- Khi deploy prod, runtime phải dùng **production service account** và registry production.
- Một job staging **không được tự chọn `env=prod`** và được platform cấp production role chỉ vì tham số đó.
- Chỉnh quyền deployment/assume-role cần review độc lập; kiểm audit cả những lần không được cấp credential.

**Một service chạy cùng binary ở staging và production vẫn an toàn hơn khi nó được cấp identity/key reference theo môi trường**, thay vì đóng cả hai secret vào cùng image rồi dùng cờ để chọn.

### 9.3. Secret manager và environment variables

Secret manager có thể dùng KMS để bảo vệ secret at rest, nhưng **cùng secret value** được lưu dưới hai tên ở dev/prod vẫn là **bí mật dùng chung**. Tách folder/path trong secret manager chưa đủ nếu value, policy hoặc quyền đọc vẫn trùng.

Environment variables chỉ là **cơ chế truyền cấu hình**, không phải nơi chứng minh security domain. Không in `System.getenv()` toàn bộ khi startup; không đưa raw KEK/DEK/private key vào image, Dockerfile, Helm chart hoặc log.

## 10. Thiết lập môi trường bằng Infrastructure as Code

### 10.1. Policy-as-code cần kiểm gì?

Một linter/reviewer cho IaC có thể phát hiện:

- Role dev/staging được cấp `kms:Decrypt`, `kms:Sign`, `kms:CreateGrant` trên production key.
- Key policy production chứa `Principal=*` hoặc scope quá rộng không có lý do.
- KMS grants/provisioning có `env=dev` nhưng resource account là prod.
- Cấu hình container được inject secret prod vào test runner.
- Tag và canonical key IDs không khớp registry đã duyệt.
- Shared recovery password/seed hoặc imported key material được nhân bản qua môi trường.
- Staging JWKS URL trỏ tới prod issuer hoặc production verifier tin stage signing key.
- Backup restore job có quyền decrypt prod rồi export plaintext vào test bucket.
- Các đoạn code fallback khi KMS lỗi sang key mặc định hard-coded.

**Policy-as-code không thay kiểm runtime.** IAM và KMS phải từ chối trực tiếp; scanner/linter không thấy mọi kiểu assume-role chain hoặc quyền cấp sau deploy.

### 10.2. Cấu hình deployment theo hướng reference

~~~yaml
# Minh họa: config chứa key reference, KHÔNG chứa raw key.
application: "billing-service"
deploymentEnvironment: "staging"
cryptographicDomain: "staging"
crypto:
  purpose: "billing-invoice"
  keyRegistryRef: "registry://nonprod/staging/billing"
  allowedKmsAccountRef: "nonprod-staging-account"
  envelopeSchema: "billing-envelope-v1"
~~~

Một file cấu hình như vậy giúp người vận hành nhìn mapping, nhưng **không có quyền quyết định độc lập** rằng ứng dụng được dùng key nào. `allowedKmsAccountRef` và domain phải được kiểm với **trusted platform identity và registry có thẩm quyền**, đồng thời được KMS IAM thực thi.

**Không ghi raw cloud credentials hoặc DEK/KEK** vào YAML, kể cả khi repository là private.

## 11. Dữ liệu production trong staging: trường hợp dễ phá vỡ key isolation

Đôi khi cần tái hiện một lỗi production ở staging. Việc đưa **production database snapshot** vào staging có thể kéo theo ciphertext, wrapped DEK, PII và metadata tenant.

### 11.1. Quy tắc mặc định

**Không cấp KEK/DEK production cho staging chỉ để đọc bản snapshot đó.** Các lựa chọn an toàn hơn, tùy phân loại dữ liệu và chính sách:

1. Dùng **synthetic data/test fixtures** để tái hiện lỗi.
2. Trích xuất **đúng phần dữ liệu tối thiểu** đã được phép, khử nhạy cảm theo quy trình được đánh giá.
3. Nếu bắt buộc chuyển dữ liệu, thực hiện thao tác trong **miền production có kiểm soát**: decrypt theo quyền, sanitize/mask/tokenize phù hợp, kiểm chất lượng kết quả và **re-encrypt bằng DEK/KEK staging độc lập**.
4. Không đưa raw production key, KMS credential hoặc recovery shares vào staging.
5. Ghi audit **nguồn dữ liệu, phê duyệt, tập record, mục đích, thời gian lưu và người nhận**.
6. Kiểm tra staging không thể gọi production KMS, kể cả sau job migration.
7. Dọn dữ liệu thử nghiệm theo retention và bảo vệ những trường vẫn có thể tái định danh.

**Pseudonymization/tokenization không mặc định đồng nghĩa dữ liệu đã trở thành vô hại**. Nếu vẫn có thể liên kết danh tính hoặc dữ liệu nhạy cảm, phải áp chính sách bảo vệ tương ứng.

### 11.2. Vì sao không chỉ “re-wrap DEK production sang KEK staging”?

Nếu **giữ nguyên DEK production** và chỉ re-wrap nó dưới KEK staging, staging có thể giải mã **mọi ciphertext từng được bảo vệ bởi DEK đó** nếu có dữ liệu tương ứng. Điều này làm **cùng raw DEK** tồn tại trong hai security domains.

Nếu mục tiêu là **tách key material thật**, cần **sinh DEK staging mới và re-encrypt dữ liệu đã được phép**, sau khi xử lý privacy requirements. Re-wrap phù hợp với migration/DR **trong cùng hoặc giữa các miền đã được phê duyệt theo threat model**, không phải giải pháp mặc định để chuyển dữ liệu production sang môi trường kém tin cậy.

### 11.3. Bảo đảm không tự bật lại production trust khi restore

Một bản snapshot còn chứa:

- Key references và wrapped DEK production.
- IAM role/policy/secret manager paths cũ.
- JWT issuer/JWKS settings và private key test hay production.
- Trust stores/certificate mappings đã revoked.
- Database rows chứa dữ liệu khách hàng.

Khi restore vào staging phải **loại bỏ/ghi đè các cấu hình quyền và trust không phù hợp**, đồng thời đối chiếu với current revocation state. Không để backup cũ tự khôi phục một public key đã bị thu hồi hay re-enable production service account ở môi trường khác.

## 12. Production DR: ngoại lệ có chủ đích, không phải staging

Một điểm tinh tế: **production DR không nhất thiết cần key material hoàn toàn độc lập với production primary**. Nếu DR phải phục hồi ciphertext production mà không re-encrypt toàn bộ, nó cần **đường unwrap/restore hợp lệ** đối với DEK production.

Có một số chiến lược tùy provider:

| Chiến lược DR | Cách tiếp cận | Rủi ro/cần kiểm |
| --- | --- | --- |
| **Provider-managed multi-region key/replica** | Cùng hoặc có quan hệ material được provider hỗ trợ giữa vùng production. | Quản trị replica, IAM, revocation propagation, failure domain. |
| **Secure HSM backup/restore** | Key material phục hồi qua cơ chế native/quorum, không export raw cho ứng dụng. | Bảo vệ recovery tokens, backup độc lập, thử restore. |
| **Re-wrap DEK sang DR KEK** | Có thêm wrapped DEK dưới KEK ở vùng phục hồi đã phê duyệt. | Cùng DEK có nhiều wrapping paths; audit và crypto-shredding phải xét tất cả. |
| **Re-encrypt ở DR bằng DEK khác** | Tách key material mạnh hơn nhưng thay ciphertext. | Chi phí migration, nhất quán snapshot và RPO/RTO. |
| **Key recovery từ secure escrow** | Một phương án phục hồi đặc biệt được quản lý riêng. | Quorum, access, tamper evidence, key destruction. |

**Điểm chung:** DR là **một phần security domain production được quản trị tương đương**, không phải một account test tự gọi production KMS. Các quyết định chia sẻ material trong DR phải được phê duyệt rõ và phản ánh trong **key inventory, backup catalog, RPO/RTO và runbook**.

### 12.1. RPO/RTO và key-version coverage

Một snapshot dữ liệu có **wrapped DEK dưới KEK v4**, nhưng DR chỉ có vật liệu v3, có thể không giải mã được. Ngược lại, một snapshot cũ dùng v3 vẫn cần đường recovery theo retention ngay cả khi production active key đã là v4.

Trong drill cần kiểm:

1. Data snapshot và key metadata cùng điểm phục hồi tương thích.
2. Wrapped DEK, encryption context, AAD, nonce/tag có đầy đủ và đúng.
3. IAM/identity của DR chỉ có quyền đã được phê duyệt.
4. Key/trust đã bị revoked ở thời điểm hiện tại không bị bật lại từ snapshot cũ.
5. Có thể decrypt và verify AEAD tag của dữ liệu đại diện.
6. Khi kết thúc DR, session/grants tạm được thu hồi theo chính sách.

**KMS replication không tự là backup chống xóa nhầm**: hành động xóa hoặc thay policy có thể lan theo replica tùy sản phẩm. Cần xem **failure domain và recovery options**.

## 13. Key rotation khi đã tách môi trường

### 13.1. Rotation độc lập theo domain

Một kế hoạch có thể cho staging thử **KEK v2 → v3**, kiểm tra migration rồi mới đề xuất một kế hoạch khác cho production. Nhưng **không lấy KEK staging v3 làm KEK production v3**; chỉ **quy trình/học được từ thử nghiệm** được chuyển sang production.

~~~text
Staging:
  KEK-stage-v2 -> KEK-stage-v3
  DEK-stage-* -> wrapped dưới stage-v3
  ciphertext staging -> giữ nguyên nếu chỉ re-wrap

Production:
  KEK-prod-v7 -> KEK-prod-v8
  DEK-prod-* -> wrapped dưới prod-v8
  ciphertext prod -> xử lý theo policy production
~~~

**Các số version không cần trùng**. Mỗi domain có cryptoperiod, owner, audit và dependency graph riêng.

### 13.2. Re-wrap không phải rotate DEK

- **KEK rotation** thay khóa bảo vệ DEK.
- **Re-wrap DEK** giữ nguyên DEK, thay wrapped blob dưới KEK mới.
- **DEK rotation** sinh DEK mới; dữ liệu cũ cần kế hoạch **re-encrypt** nếu muốn chuyển bảo vệ sang DEK mới.
- Nếu DEK đã bị lộ từ staging/prod, re-wrap dưới KEK khác **không làm ciphertext cũ bí mật trở lại**.
- Nếu signing private key production bị lộ, phải **rotate signer và cập nhật verifier trust**, không chỉ đổi key alias.

Không tự dùng một quy trình rotation giống nhau cho **AES DEK, KMS KEK, Ed25519 private signer, HMAC secret và mTLS credential**. Mỗi loại có consumer, usage và hậu quả khác nhau.

### 13.3. Read compatibility không mở cửa cho cross-env

Khi production rotate KEK v7 → v8, app production có thể cần đọc dữ liệu cũ dùng v7 theo policy, trong khi new writes dùng v8.

Điều này **không có nghĩa app staging được đọc v7**. Một registry có thể cho production các **approved predecessors**, nhưng chỉ trong **cùng cryptographic domain**, với quyền thực thi KMS vẫn giới hạn đúng principal.

## 14. Nếu phát hiện đã dùng chung key giữa staging và prod?

Đây là sự cố cần phân loại, không chỉ là “dọn lại config”. Giả sử một DEK hoặc private signing key đã vô tình được sử dụng cả ở staging và production.

~~~mermaid
flowchart TD
    FIND["Phát hiện cross-env key reuse"] --> SCOPE["Xác minh loại key, material origin, nơi dùng, thời gian"]
    SCOPE --> CONTAIN["Chặn cấp mới và thu hồi quyền sai"]
    CONTAIN --> DATA{"Secret/key material đã có thể lộ ở non-prod?"}
    DATA -->|Có| ROTATE["Đánh giá rotate DEK/KEK/Signer/PSK theo loại"]
    DATA -->|Chưa rõ| INVEST["Điều tra KMS audit, artifacts, credentials, logs"]
    INVEST --> ROTATE
    ROTATE --> MIGRATE["Migration rewrap/re-encrypt/trust update đúng trường hợp"]
    MIGRATE --> VERIFY["Verify IAM, data, signatures, backups, negative tests"]
    VERIFY --> REVIEW["Hậu kiểm và loại bỏ shared-key paths"]
~~~

### 14.1. Ma trận phản ứng

| Phát hiện | Việc cần làm | Điều không đủ |
| --- | --- | --- |
| **DEK rõ giống nhau ở dev/prod** | Xác định dữ liệu, new DEK và re-encrypt khi cần; kiểm tra cipher/nonce usage. | Đổi env variable rồi giữ ciphertext cũ. |
| **KEK material dùng chung** | Tạo KEK độc lập, kiểm wrapped DEK và quyền unwrap; đánh giá DEK bị lộ. | Chỉ đổi alias hoặc rewrap nếu DEK đã compromised. |
| **Private signing key dùng chung** | Tạo prod signer mới trong KMS/HSM, cập nhật trust và xem chữ ký đã phát hành. | Chỉ xóa private key ở staging. |
| **HMAC/PSK giống nhau** | Rotate secret, giới hạn token/session acceptance và kiểm issuer/audience. | Giữ verifier prod chấp nhận secret cũ vô hạn. |
| **KMS IAM dev dùng được prod key** | Thu hồi IAM/grants/session; điều tra Sign/Decrypt usage và material exposure. | Giả định không có rủi ro vì key non-exportable. |
| **Public key stage nằm trong prod trust registry** | Xóa/sửa binding theo current policy, kiểm event đã được Verify và anti-rollback. | Chỉ thay `kid` mà bỏ trust state cũ. |
| **Production ciphertext ở staging** | Xác định data governance, wrapped DEK/context và khả năng decrypt; cô lập bản copy. | Giả định ciphertext luôn vô hại. |
| **DR key dùng chung có chủ đích** | Xác nhận DR thuộc production trust domain và được phép, audit/quorum đầy đủ. | Coi mọi replication giống lỗi staging-prod. |

### 14.2. Không thể “làm người nhận quên key”

Nếu raw DEK/KEK/private key đã được copy vào một môi trường người khác có quyền đọc, việc đổi quyền truy cập **không làm vật liệu đã sao chép mất đi**. Cần đánh giá **khóa mới, dữ liệu/chữ ký cũ, logs/artifacts/backups, phạm vi lưu plaintext và khả năng đã bị truy cập**.

**Một lần Sign/Decrypt từ principal không được phép** phải được điều tra ngay cả khi key **non-exportable**. Quyền sử dụng API có thể đủ để tạo chữ ký giả hoặc lấy plaintext DEK.

### 14.3. Giữ khả năng phục hồi sau sự cố

Khi rotate/disable vì compromise, tránh hủy production KEK khi **backup hoặc encrypted records** vẫn phụ thuộc vào nó. Việc xử lý phải cân bằng **containment** và **availability**, có phê duyệt của Security/data owner/incident commander.

Sau khi phục hồi, cần đối chiếu **active keys, old-key read policy, revocation, IAM, data inventory, log retention và key destruction evidence**.

## 15. Kiểm thử tách key giữa các môi trường

Một bài test “dev có key ID khác prod” **chưa đủ**. Phải test hành vi **bị từ chối**.

| Kiểm thử | Kết quả an toàn mong đợi |
| --- | --- |
| **Dev principal gọi production KMS Decrypt** | KMS/IAM từ chối độc lập với application config. |
| **Staging principal gọi prod Sign** | Không có quyền ký bằng prod signer. |
| **Prod JWT verifier nhận token do dev issuer ký** | Từ chối theo issuer/audience/key trust. |
| **Ledger prod Verify event bằng public key staging** | Từ chối dù chữ ký hợp lệ toán học dưới key staging. |
| **Dev role chỉnh prod key policy/grant** | IAM/administrative boundary từ chối. |
| **Client gửi `env=prod` trong request** | Không thay trusted runtime environment hoặc KMS principal. |
| **Ứng dụng staging trỏ config sang prod key alias** | Provider resource/key binding check và IAM từ chối. |
| **Tag của key bị sửa `env=prod`** | Không đổi được canonical resource/approval/IAM. |
| **Ciphertext prod được gửi vào staging** | Authorization/domain/context hoặc unwrap từ chối; không trả plaintext. |
| **GCM AAD domain bị sửa** | Tag verification thất bại; không bỏ qua lỗi. |
| **Dùng sai tenant với key trong cùng prod** | App authorization/KMS context từ chối theo khả năng. |
| **KMS AccessDenied hoặc timeout** | Không fallback sang hard-coded shared secret. |
| **Key đã disabled/revoked** | Không tạo encryption/signature mới trái policy. |
| **Prod new writes khi rotate** | Chỉ dùng active KEK mới; dữ liệu cũ có read compatibility đúng domain. |
| **Staging data migration** | Có data approval/sanitization, DEK mới và KEK staging độc lập. |
| **Production DR restore** | Decrypt đúng dữ liệu, quyền DR hạn chế, current revocation không bị rollback. |
| **CI job từ fork không đáng tin** | Không được nhận credential để gọi prod KMS. |
| **Audit access** | Dev không đọc được key material hoặc audit nhạy cảm của prod. |
| **KMS response/log scan** | Không có raw DEK/KEK/private key, token hoặc secret trong log. |
| **Rollback deployment** | Không mở lại trust/key version đã compromise. |

### 15.1. Kiểm tra runtime và provider IAM thật

Unit test cho Java policy gate giúp phát hiện cấu hình sai ở application. Nhưng cần **integration tests hoặc kiểm tra policy có kiểm soát** với **principal dev/staging thật** để xác minh provider KMS **từ chối** operation production.

**Không dùng production data/key trong test nếu không được cho phép.** Test negative permissions nên dùng key test có policy tương ứng hoặc cơ chế xác nhận IAM được phê duyệt; tránh vô ý tạo audit hoặc thao tác production ngoài phạm vi.

### 15.2. Phân biệt unit test và dữ liệu cryptographic test

Một **test vector cố định** để xác minh AES/HMAC/Ed25519 implementation có thể hợp lệ trong unit test **nếu chỉ là key thử nghiệm, không được sử dụng ở production**, và không bị đóng gói làm fallback.

Với integration tests về environment isolation, quan trọng hơn là **hai miền có identity/key policy khác nhau**, không phải dùng cùng một khóa cố định rồi đổi tên `dev` và `prod`.

## 16. Audit, metric và bằng chứng thực thi

Để điều tra cross-env access, cần audit cả **provider KMS** và **ứng dụng**.

### 16.1. Mẫu event được lọc

~~~json
{
  "eventType": "ENVIRONMENT_KEY_USE",
  "runtimeDomain": "staging",
  "workloadRef": "billing-staging",
  "requestedKeyRef": "billing-production-kek",
  "resolvedProviderAccountRef": "production-account",
  "operation": "DECRYPT_DATA_KEY",
  "outcome": "DENIED",
  "reasonCode": "ENVIRONMENT_KEY_MISMATCH",
  "policyVersion": "key-use-policy-v4",
  "correlationId": "opaque-request-id"
}
~~~

**Đây là event minh họa, không phải log thật.** KeyRef, accountRef và workloadRef là metadata cần kiểm soát quyền xem. Không log raw DEK/KEK, private key, seed, wrapped key blob lớn, token, plaintext hoặc KMS response chưa được lọc.

### 16.2. Các chỉ số và cảnh báo

- Số lần **principal non-prod gọi key resource thuộc production**.
- Thay đổi **key policy, IAM grants, assume-role trust** ảnh hưởng production.
- Tỷ lệ KMS `AccessDenied` sau deployment/rotation.
- **Signer production** bị dùng từ workload hoặc workflow ngoài danh sách được phép.
- Issuer/JWKS trust changes cho phép **stage public key** ở prod.
- Data restoration hoặc export liên quan **production ciphertext vào non-prod**.
- Tỷ lệ new writes còn dùng **retired KEK** trong mỗi domain.
- Backup/DR restore failures do thiếu key version hoặc context.
- Khóa giống nhau về **provenance/import source** trong các domains không được phép chia sẻ.
- Mọi lần dùng **break-glass** để cấp quyền cross-domain và việc thu hồi sau đó.

**Cảnh báo không tự chứng minh hành vi xấu**: ví dụ một job DR đã được phê duyệt có thể có quyền đặc biệt hợp lệ. Audit nên gắn **incident/change ID, approval và scope** để phân loại chính xác.

## 17. Tình huống thực tế: Billing, Payment và Ledger

Giả sử nền tảng có ba dịch vụ:

- **Billing Service:** mã hóa hóa đơn bằng AES-256-GCM; DEK được KMS sinh và bọc dưới KEK theo domain.
- **Payment Service:** ký payment event bằng private key Ed25519 trong KMS/HSM.
- **Ledger Service:** Verify chữ ký bằng public key từ trust registry và kiểm tra quyền giao dịch.

### 17.1. Thiết kế sai

~~~text
Shared config repository:
  billing.aesKey = ONE-STATIC-KEY-FOR-DEV-STAGING-PROD
  payment.signingPrivatePem = SAME-FILE-IN-ALL-IMAGES
  ledger.jwksUrl = https://test-key-registry.example/keys

CI:
  test-runner can assume production-kms-admin-role
  staging restores prod DB snapshot as-is
~~~

Tất cả chuỗi chỉ là **placeholder giả để minh họa**, không phải secret hoặc endpoint thật.

Lỗi được nối chuỗi:

1. Dev lộ AES key cố định → có thể decrypt production ciphertext dùng cùng DEK.
2. Staging signer private key bị lộ → production Ledger có thể chấp nhận event giả nếu trust sai.
3. CI role non-prod có thể sửa hoặc gọi production KMS.
4. Dữ liệu thật trong staging có thể bị đọc bởi người có quyền non-prod.
5. Khi xuất hiện sự cố, không thể biết rõ môi trường nào đã tạo chữ ký hoặc thay secret.

### 17.2. Kiến trúc cải thiện

1. Billing-dev và Billing-staging dùng **KEK/DEK độc lập**, production dùng key family production.
2. KMS production chỉ chấp nhận **production workload identity** với đúng operations.
3. Database production chứa ciphertext/wrapped DEK, AAD/context gắn **production cryptographic domain, tenant, object**.
4. Payment signer production không xuất private key khỏi KMS/HSM; stage/dev có signer key độc lập.
5. Ledger production chỉ tin **production issuer và public-key registry** theo policy; key stage không được chấp nhận.
6. CI/CD promotion chuyển code/config được duyệt, không copy raw secret hoặc credential production vào test.
7. Staging dùng **synthetic data**, hoặc một pipeline sanitization được phê duyệt và **re-encrypt bằng DEK staging**.
8. Production DR giữ đường phục hồi keys/data theo provider-native mechanism và quorum, **trong miền production**.
9. Key inventory theo dõi account, domain, owner, key version, successor và WRAPS/ENCRYPTS/SIGNS dependencies.
10. Auditors/SOC theo dõi cross-domain AccessDenied và policy changes, không ghi secret vào log.

### 17.3. Rollout khi đang có một key production cũ dùng chung

Nếu đã phát hiện shared key, không thể chỉ “đổi tên alias”:

- Security phân loại raw key/credential nào đã lộ và bên nào có quyền truy cập.
- Thu hồi quyền non-prod dùng production key, loại bỏ shared-key distribution path.
- Sinh key successor theo từng domain và kiểm owner/usage/IAM.
- Với **DEK đã lộ**, đánh giá **re-encrypt dữ liệu**. Với **KEK compromise**, kiểm wrapped DEKs và dữ liệu phụ thuộc. Với **signing key**, cập nhật cả signer và verifier trust.
- Migrate từng nhóm dữ liệu/workloads, bảo vệ consistency/CAS và khả năng đọc lịch sử theo policy.
- Đối soát logs, archives, snapshots và DR, không xóa KEK khi còn ciphertext cần khôi phục.
- Thử negative tests dev→prod và staging→prod; chỉ đóng sự cố khi residual risk đã được đánh giá.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đổi tên `dev-kek` thành `prod-kek` | Cùng material hoặc policy vẫn dùng chung. | Sinh key độc lập và đối chiếu canonical IDs/provenance. |
| Cùng secret HMAC/JWT cho mọi env | Token thử nghiệm có thể hợp lệ tại prod. | Secret, issuer, audience, trust tách biệt. |
| Cùng private signer giữa staging và prod | Staging có thể ký như production. | Signer riêng và verifier trust policy riêng. |
| Cấp `kms:*` cho CI runner | Runner có thể Decrypt/Sign/Delete production. | Scoped OIDC role, identity và key policy. |
| Tin `ENV=prod` từ user request | Client chọn miền KMS đặc quyền hơn. | Trusted runtime identity và IAM tại KMS. |
| Dựa duy nhất vào tag `env=prod` | Tag bị sửa hoặc không được policy thực thi. | Canonical key/resource/account binding và KMS enforcement. |
| Dùng cùng imported key bytes ở hai KMS objects | Có hai ID nhưng vẫn là một bí mật. | Key generation/provenance độc lập, kiểm import paths. |
| Coi khác region là độc lập vật liệu | Replicated key có thể cùng material theo provider. | Kiểm replication semantics và trust domain. |
| Đưa production DB snapshot vào staging | Rò ciphertext/PII, có thể cả key/credential. | Synthetic/sanitized data và re-encrypt under staging keys. |
| Re-wrap DEK production dưới KEK staging | Cùng raw DEK tồn tại ở hai domains. | Tạo DEK staging mới và re-encrypt nếu chuyển miền thật. |
| Đưa `prodKeyRef` vào image staging như fallback | Misconfiguration hoặc attack chuyển KMS. | Approved registry + IAM deny, không fallback. |
| Cache plaintext DEK qua môi trường | Key lộ trong RAM/cache non-prod. | Cache riêng, TTL/usage limits, xóa và audit theo policy. |
| Lấy key ID từ body request chưa xác thực | Caller có thể chọn key của tenant/môi trường khác. | Server-side mapping và authorization. |
| Không tách production key admin với developer | Dev có thể tự mở quyền prod dù app role bị deny. | Separation of duties và review IAM escalation. |
| Test JWT bằng staging key trên prod API | Vô tình trộn trust và acceptance rules. | Test môi trường riêng, negative validation. |
| Dùng test CA được mọi production client tin | Test cert có thể giả mạo workload prod. | Tách CA/policy namespace và service identity restrictions. |
| Bỏ qua AES-GCM nonce/tag khi migration | Lộ thông tin hoặc mất integrity. | AEAD đúng, AAD ổn định và verify tag. |
| Restore backup IAM/trust cũ vào prod | Tái bật key/role đã revoked. | Reconcile với current security state. |
| Coi DR là một môi trường staging | Mất đường recovery hoặc mở rộng production secret vào lab. | Tách DR production trust domain rõ ràng. |
| Xóa KEK cũ trước dependency scan | Mất khả năng giải mã ciphertext/archive. | Inventory, retention và DR drill trước destruction. |
| Log raw key vì muốn so sánh env | Secret rò qua log/CI/APM. | Provenance, canonical metadata, no-secret audit. |
| Không test các thao tác phải bị từ chối | Một IAM misconfiguration có thể tồn tại lâu. | Negative integration tests và policy review. |
| Rotate KEK nhưng DEK đã lộ vẫn giữ nguyên | Ciphertext cũ còn nguy cơ giải mã. | Đánh giá DEK rotation/re-encryption. |
| Chỉ bảo vệ key nhưng không kiểm user tenant | Cross-tenant data exposure trong cùng prod env. | KMS IAM + application authorization + context/AAD. |

## 19. Checklist thiết kế key separation

1. **Environment model:** có phân biệt deployment environment, security domain và tenant boundary không?
2. **Key inventory:** key objects/versions có metadata domain, account, owner, purpose và material origin không?
3. **Key material:** dev/test/staging có thực sự dùng bytes khóa độc lập với production không?
4. **KMS/HSM:** production key custody, IAM, grants và admin roles có tách khỏi non-prod không?
5. **Identity:** workload lấy danh tính được xác thực từ platform, không chọn qua request/env tự khai?
6. **Registry:** key references có đến từ source of truth đã phê duyệt, đối chiếu canonical IDs và account không?
7. **DEK/KEK:** DEK và KEK có tách theo domain/purpose và có encryption context đúng không?
8. **AEAD:** AES-GCM nonce/tag và AAD domain/tenant/object có được thực hiện đúng, không phụ thuộc field dễ thay không?
9. **Signing keys:** production private signer không có bản copy ở staging/dev, verifier trust không chấp nhận key test?
10. **HMAC/PSK:** secrets và issuer/audience/token acceptance policies có tách theo môi trường không?
11. **mTLS/PKI:** production kiểm service identity/trust root/CA policy, không tin nhầm test cert?
12. **IAM policy:** dev/staging có bị deny trực tiếp khi gọi KMS production không? Quyền assume-role và CreateGrant đã được xét chưa?
13. **CI/CD:** runner non-prod không có credential/role production; promotion không copy secret?
14. **Config:** app không hard-code key material hoặc fallback key; key reference là metadata được bảo vệ?
15. **Staging data:** có dùng dữ liệu giả/sanitized và re-encrypt dưới staging DEK khi chuyển dữ liệu hợp lệ không?
16. **DR:** production-DR có được định nghĩa rõ là cùng miền phục hồi hoặc domain được phê duyệt, bảo vệ theo RPO/RTO không?
17. **Version/rotation:** mỗi domain có key successors riêng, hỗ trợ read compatibility đúng domain và không dùng `current` thay history?
18. **Revocation:** compromised dev key có thể bị revoke mà không ảnh hưởng production không?
19. **Backup/destruction:** snapshot, archive, wrapped DEK và key versions được đối soát trước hủy không?
20. **Audit:** có cảnh báo cross-env Sign/Decrypt/Grant nhưng không ghi raw keys/credentials không?
21. **Testing:** đã kiểm các test deny dev→prod, staging→prod, sai tenant, sai AAD và trust rollback chưa?
22. **Governance:** người chịu trách nhiệm key policy, emergency access, rotation, data movement và DR có được xác định không?

## 20. Câu hỏi tự kiểm tra

1. “Tách key theo môi trường” khác “đặt hai alias key khác nhau” ở điểm nào?
2. Vì sao cùng một key material trong hai KMS objects khác ID vẫn nguy hiểm?
3. Deployment environment, cryptographic security domain và tenant khác nhau như thế nào?
4. Có nên coi **production-DR** là một bản staging bình thường và luôn tạo key không đọc được dữ liệu prod không? Vì sao?
5. Khi một dev principal có quyền `kms:Decrypt` trên prod KEK, việc key non-exportable có bảo vệ mọi dữ liệu không?
6. Một public key staging vô hại về bí mật có thể gây lỗi gì nếu Ledger production tin nó?
7. Vì sao cần tách HMAC/JWT signing secret bên cạnh kiểm issuer/audience?
8. mTLS có tự ngăn service staging gọi KMS prod nếu các policy IAM cho phép không?
9. Hai bản mã dùng KEK khác nhau nhưng cùng raw DEK có thực sự tách key material không?
10. AES-GCM AAD chứa domain có thay KMS IAM và application authorization không?
11. Tại sao không nên dùng region/alias current làm AAD nếu hệ thống cần DR/rotation mà không re-encrypt?
12. Nếu staging sao chép production ciphertext/wrapped DEK nhưng không có quyền unwrap, còn rủi ro gì?
13. Muốn đưa dữ liệu production đã được phép sang staging và vẫn tách DEK, cần pipeline thế nào?
14. Nếu chỉ re-wrap production DEK dưới staging KEK, điều gì vẫn được chia sẻ?
15. Tại sao `System.getenv("ENV")` không đủ để chứng minh runtime đang ở miền tin cậy production?
16. KMS provider metadata và registry cùng cần được kiểm ở bước nào?
17. Vì sao reviewer phải xét quyền `CreateGrant`, `ChangeKeyPolicy`, `AssumeRole` chứ không chỉ `Decrypt`?
18. Trong CI/CD, điều kiện OIDC/federation nào có thể giúp ngăn runner từ fork nhận production credential?
19. Khi production rotate KEK v7→v8, staging có cần dùng cùng v8 không?
20. Vì sao re-wrap không đủ khi plaintext DEK đã bị lộ từ dev?
21. Khi DR restore snapshot cũ, phải kiểm tra key version và revocation state nào?
22. Những negative tests nào chứng minh tách key **có hiệu lực ở KMS**, không chỉ trong code?
23. Key inventory cần ghi những mối quan hệ WRAPS/ENCRYPTS/SIGNS nào để đánh giá compromise?
24. Vì sao audit cần ghi canonical key ref và operation nhưng tránh raw key material?

**Ghi nhớ:** **Tách key theo môi trường** là xây dựng **ranh giới sử dụng và quản trị khóa có hiệu lực**, không chỉ là đặt tên hay phân thư mục cấu hình. Mỗi miền dev/test/staging/production cần **key material độc lập theo chính sách, workload identity và IAM riêng, KEK/DEK và signing/MAC keys đúng purpose, trust registry chính xác, application authorization và audit**. **Production-DR** có thể chia sẻ đường phục hồi mật mã theo thiết kế được phê duyệt, nhưng **staging không phải DR**. Khi dữ liệu hoặc key đã vượt ranh giới sai, phải đánh giá **raw key exposure, rotation, re-encryption, trust update, backup và ảnh hưởng lịch sử**, không chỉ thu hồi một alias hay role. Mục tiêu cuối là **một sự cố ở môi trường ít tin cậy không làm mất tính bí mật, toàn vẹn, xác thực hoặc khả năng phục hồi của production**.
