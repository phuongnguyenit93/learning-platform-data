# Environment trong Key inventory — Quản lý khóa theo môi trường triển khai

## 1. Environment là gì trong kho kiểm kê khóa?

Trong **key inventory (kho kiểm kê khóa mật mã)**, **Environment** là thông tin xác định **môi trường vận hành hoặc ranh giới triển khai mà một khóa được tạo, quản lý và được phép sử dụng**. Những giá trị thường gặp là **development (dev)**, **test**, **staging/pre-production**, **production (prod)** và **disaster recovery (DR)**. Đây không chỉ là nhãn phục vụ báo cáo: môi trường có thể quyết định **ai được dùng khóa, dữ liệu nào được mã hóa, chính sách KMS/HSM nào áp dụng, khóa được sao lưu ở đâu và khi nào được xoay vòng hoặc hủy**.

Ví dụ, một ứng dụng Java có hai khóa AES-256 dùng để mã hóa hồ sơ:

- **DEK-PROD**: dùng cho dữ liệu khách hàng thật trong production.
- **DEK-TEST**: dùng cho dữ liệu thử nghiệm trong test.

Hai khóa có thể cùng thuật toán, cùng độ dài và cùng mục đích kỹ thuật, nhưng **không được xem là thay thế được cho nhau**. Nếu dịch vụ test có quyền giải mã dữ liệu production hoặc bản sao dữ liệu production còn được bọc bằng khóa production trong môi trường thử nghiệm, một điểm yếu ở test có thể trở thành đường truy cập dữ liệu thật.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Environment là một thuộc tính của khóa cần được kiểm kê cùng **key ID/version, thuật toán, mục đích, chủ sở hữu, vùng triển khai, quyền truy cập, trạng thái và quan hệ phụ thuộc DEK/KEK**. Quản lý đúng thuộc tính này giúp bảo vệ khóa qua vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, kết nối với mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption và kiểm toán.

> **Nguyên tắc:** **Environment là một ranh giới bảo mật cần được thực thi**, không chỉ là một chuỗi như \`"prod"\` hoặc \`"test"\` trong database. Nhãn môi trường hỗ trợ inventory và quyết định chính sách; **danh tính workload, quyền IAM/KMS, cấu hình hạ tầng và luồng dữ liệu** mới quyết định ranh giới đó có thực sự tồn tại hay không.

## 2. Các môi trường thường gặp và mức độ bảo vệ

| Environment | Mục đích | Dữ liệu/khóa nên sử dụng | Kiểm soát tối thiểu |
| --- | --- | --- | --- |
| **Local / Development** | Lập trình, debug, kiểm tra đơn vị | Dữ liệu giả, khóa riêng không dùng ngoài dev | Không giữ khóa production trong mã nguồn, máy cá nhân hoặc log |
| **Test / QA** | Test tích hợp, kiểm thử hồi quy, tải | Dữ liệu nhân tạo hoặc dữ liệu đã xử lý đúng chính sách; khóa riêng cho test | Tách identity, KMS key, secret và quyền khỏi prod |
| **Staging / Pre-production** | Kiểm tra phát hành gần với cấu hình prod | Cấu hình tương đồng nhưng **không mặc định dùng dữ liệu/khóa prod** | Kiểm soát truy cập chặt, giới hạn tài khoản và dòng dữ liệu |
| **Production** | Xử lý dữ liệu và giao dịch thật | Khóa thật, dữ liệu thật | IAM tối thiểu, phân quyền, logging/audit, rotation, DR và xử lý sự cố |
| **Disaster Recovery (DR)** | Phục hồi dịch vụ khi một vùng/hệ thống gặp sự cố | Chỉ bản sao và khóa phục hồi được phép theo thiết kế | Kiểm tra replication/restore, quyền khôi phục, khả năng sử dụng và điều kiện failover |
| **Sandbox / Training** | Thử tính năng hoặc học tập | Dữ liệu giả, khóa ngắn hạn tách biệt | Không liên kết tới key registry production hoặc grants rộng |

Các giá trị này là **ví dụ quy ước**, không phải bộ enum chung được mọi nền tảng KMS chuẩn hóa. Một tổ chức có thể gộp QA vào test, tách production theo vùng hoặc có môi trường **regulated-prod** cho dữ liệu được kiểm soát đặc biệt.

**Điều không nên làm:** Mặc định staging “gần giống production” nên được quyền sử dụng **cùng KEK/DEK**, hoặc sao chép nguyên database production sang test chỉ để kiểm thử tiện hơn.

### 2.1. Environment không phải mức độ nhạy cảm duy nhất

Một hệ thống production có thể chứa cả dữ liệu công khai và dữ liệu nhạy cảm. Một môi trường test có thể cần kiểm soát cao khi được phép dùng dữ liệu thật đã hạn chế phạm vi. Vì vậy, **environment không thay thế data classification**.

Ví dụ, bản ghi:

~~~text
environment = production
dataClassification = confidential
tenant = tenant-a
region = primary-region
purpose = encrypt-customer-profile
~~~

cho biết một phạm vi sử dụng cụ thể hơn nhiều so với chỉ ghi **environment = production**.

## 3. Environment khác region, account, tenant và key purpose

Một lỗi inventory phổ biến là trộn nhiều khái niệm vào cùng một trường \`environment\`.

| Thuộc tính | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Environment** | Khóa thuộc môi trường phát triển/vận hành nào? | \`production\` |
| **Cloud account / project / subscription** | Tài nguyên nằm trong biên quản trị hạ tầng nào? | \`prod-security-account\` |
| **Region / locality** | Khóa hoặc dịch vụ KMS được vận hành tại vị trí logic nào? | \`primary-region\` |
| **Tenant / business domain** | Dữ liệu hoặc đối tượng kinh doanh nào phụ thuộc khóa? | \`tenant-a\`, \`billing\` |
| **Key purpose / usage** | Khóa được phép thực hiện việc gì? | \`encrypt\`, \`wrap\`, \`sign\`, \`verify\` |
| **Key type / algorithm** | Vật liệu và primitive mật mã nào? | \`AES-256\`, \`RSA-PSS\`, \`HMAC-SHA-256\` |
| **Lifecycle state** | Có được sử dụng hiện tại không? | \`active\`, \`retired\`, \`compromised\` |
| **Owner** | Ai chịu trách nhiệm chính sách/rotation/ứng phó? | \`payments-platform\` |

**Không thể suy ra region từ environment**: production có thể chạy ở nhiều region. **Không thể suy ra tenant từ environment**: một hệ thống production có thể phục vụ nhiều tenant. Và một khóa \`production\` không tự được phép làm cả Encrypt, Decrypt, Sign và GenerateMac.

### 3.1. Vì sao cần định danh môi trường chuẩn hóa?

Nếu một nhóm ghi \`prod\`, nhóm khác \`production\`, nhóm thứ ba \`live\`, các báo cáo có thể bỏ sót khóa. Khi xây key inventory, nên:

1. Định nghĩa **tập mã môi trường chuẩn** và ánh xạ tên cũ sang mã chuẩn.
2. Xác định **nguồn có thẩm quyền** cho mỗi workload: tài khoản hạ tầng, namespace, deployment identity hoặc cấu hình kiểm soát.
3. Quy định ai được phép **thay environment của một key record**.
4. Gắn **môi trường hiện tại với key ID/version thực tế**, tránh chỉ suy ra từ tên alias.
5. Theo dõi thay đổi môi trường như một **sự kiện bảo mật**, không cho người dùng sửa nhãn để vượt chính sách.

Không nhất thiết nhúng mọi thuộc tính vào tên khóa; một cấu trúc inventory rõ ràng và nhất quán đáng tin hơn chuỗi tên tự do.

## 4. Những gì cần lưu cho Environment trong key inventory

Một bản ghi kiểm kê cần phục vụ cả người vận hành và chương trình kiểm soát quyền. Ví dụ cấu trúc **minh họa**, không phải schema bắt buộc của một nhà cung cấp:

~~~json
{
  "keyId": "profile-dek-2026-11-v2",
  "keyVersion": 2,
  "environment": "production",
  "cloudAccount": "prod-security-account",
  "region": "primary-region",
  "tenantScope": "tenant-a",
  "owner": "customer-data-platform",
  "keyType": "symmetric",
  "algorithm": "AES-256-GCM",
  "keyPurpose": "encrypt-customer-profile",
  "lifecycleState": "active",
  "kmsKeyReference": "approved-kms-key-reference",
  "parentKeyId": "profile-kek-prod-v3",
  "dataClassification": "confidential",
  "createdAt": "2026-11-01T00:00:00Z",
  "lastReviewedAt": "2026-11-20T00:00:00Z",
  "rotationPolicyId": "customer-profile-dek-policy-v2",
  "auditOwner": "security-platform"
}
~~~

Trong nhiều kiến trúc, ứng dụng **không tạo hoặc nhìn thấy một đối tượng KMS cho từng DEK**. DEK có thể được sinh tạm thời rồi lưu dưới dạng **wrapped DEK** cùng ciphertext. Khi đó \`keyId\`, \`parentKeyId\` và metadata trong inventory là **định danh logic** được thiết kế phù hợp, không nhất thiết là một mã tài nguyên KMS có thể truy vấn trực tiếp.

### 4.1. Trường nào cần được tin cậy?

- \`environment\`, \`tenantScope\`, \`keyPurpose\`, \`lifecycleState\` phải đến từ **registry/configuration có quyền ghi được kiểm soát**, không tin hoàn toàn vào request client.
- \`kmsKeyReference\` cần xác định đúng **resource và môi trường**. Alias có thể thay mục tiêu nên không đủ làm bằng chứng identity vật liệu khóa khi điều tra.
- \`parentKeyId\` và quan hệ wrap giúp xác định **blast radius** nếu KEK/root key bị lộ hoặc chuẩn bị bị hủy.
- \`lastReviewedAt\`, \`owner\` và \`rotationPolicyId\` giúp phát hiện **orphan keys** — khóa còn tồn tại nhưng không còn ai nhận trách nhiệm.
- Các trường metadata không phải secret, nhưng **có thể tiết lộ cấu trúc hệ thống** nên vẫn cần kiểm soát truy cập, toàn vẹn và retention phù hợp.

**Không lưu raw DEK, KEK, private signing key, MAC key hoặc pepper trong inventory.** Inventory nên lưu **tham chiếu, đặc tính, chính sách và trạng thái**; kho bí mật hoặc KMS/HSM giữ vật liệu khóa.

### 4.2. Mối quan hệ giữa key ID, key version và environment

Một khóa có thể đổi **version** trong cùng environment theo rotation. Nhưng việc chuyển nguyên vật liệu khóa từ test sang prod **không phải rotation hợp lệ chỉ vì đổi nhãn environment**.

Nên xem bộ thông tin:

~~~text
(environment, tenant/owner scope, purpose, key ID, key version)
~~~

là cơ sở định vị và xét chính sách. Trong hệ thống thực, **key ID toàn cục** có thể đã chứa một số thành phần; dù vậy, quyết định quyền vẫn phải dựa trên tài nguyên và danh tính đã xác thực, không chỉ giải mã một tên khóa.

## 5. Ranh giới an toàn giữa các environment

Trong quản lý khóa, phân tách môi trường thường được thực thi bằng nhiều lớp đồng thời:

1. **Tách tài khoản/dự án hạ tầng:** Production và non-production được đặt ở các biên quyền quản trị khác nhau khi có thể.
2. **Tách KMS/HSM key material:** Không dùng chung DEK, KEK, HMAC key, signing key hoặc pepper giữa môi trường độc lập nếu không có một thiết kế và phê duyệt rõ.
3. **Tách IAM/service identity:** Workload test không được mặc nhiên có quyền \`Decrypt\` hoặc \`Unwrap\` với khóa production.
4. **Tách mạng và secret distribution:** Credential, token, endpoint KMS và quá trình cấp phát của production không lan vào dev/test.
5. **Tách bản sao dữ liệu:** Backup production có chính sách riêng; muốn dùng dữ liệu cho test phải có quy trình **sanitization/tokenization hoặc re-encrypt** được cho phép.
6. **Tách chính sách và giám sát:** Có audit trail và cảnh báo riêng cho thao tác cross-environment.

~~~mermaid
flowchart TD
    subgraph DEV["Development / Test"]
        TAPP["Ứng dụng test"]
        TKMS["KMS/test key policy"]
        TDATA["Test data + wrapped test DEK"]
        TAPP --> TKMS
        TAPP --> TDATA
    end
    subgraph PROD["Production"]
        PAPP["Ứng dụng production"]
        PKMS["KMS/prod key policy"]
        PDATA["Real data + wrapped prod DEK"]
        PAPP --> PKMS
        PAPP --> PDATA
    end
    SEC["Identity/IAM + key inventory<br/>quản lý ranh giới"]
    SEC --> TKMS
    SEC --> PKMS
    TAPP -.->|"Cross-env Decrypt: DENY"| PKMS
    TAPP -.->|"Cross-env data access: DENY"| PDATA
~~~

**Sơ đồ diễn đạt chính sách mong muốn, không phải cam kết một nhãn tự chặn được truy cập.** Cần dùng chính sách IAM/KMS, kiểm soát mạng, resource policy, service identity và kiểm tra quyền dữ liệu để thực thi.

### 5.1. Cùng thuật toán không có nghĩa cùng khóa

Dev và prod đều có thể dùng **AES-256-GCM**, nhưng nên có **DEK và KEK độc lập**. Cùng thuật toán không tạo bất cứ yêu cầu nào phải chia sẻ key material.

Nếu non-prod được phép nạp bản mã production mà không có key của prod, việc giải mã phải thất bại thay vì âm thầm thử thêm các khóa khác cho đến khi một khóa thành công.

### 5.2. Chính sách theo environment không thay authorization

Một workload trong production có quyền KMS đối với \`prod-key\` vẫn có thể không có quyền xem **hồ sơ của mọi tenant**. Cần kiểm tra ít nhất:

- Workload có đúng môi trường và quyền dùng **KMS key resource**?
- Key purpose/operation có phù hợp: Encrypt, Decrypt, Sign hay Wrap/Unwrap?
- Người dùng/luồng nghiệp vụ có quyền với **tenant và bản ghi**?
- Encryption context/AAD có ràng buộc đúng môi trường, tenant, record ID hay không?

**Encryption context** của một số KMS có thể được xác thực như AAD hoặc dùng trong điều kiện IAM tùy nhà cung cấp; nó **không cần bí mật**, nhưng cũng **không đủ để thay thế authorization** nếu được client tự khai báo không có kiểm tra.

## 6. Environment và phân cấp khóa DEK–KEK–root key

**Envelope encryption** thường bảo vệ dữ liệu bằng DEK rồi bảo vệ DEK bằng KEK. Một cấu trúc lý tưởng có thể có KEK riêng cho mỗi environment, và tùy rủi ro có KEK riêng theo tenant hoặc data domain.

~~~mermaid
flowchart TD
    CONTROL["Key inventory / policy control plane"]
    CONTROL --> PD["Environment: production"]
    CONTROL --> TD["Environment: test"]
    PD --> PKEK["Prod KEK trong KMS/HSM"]
    TD --> TKEK["Test KEK trong KMS/HSM"]
    PKEK --> PDEK1["Wrapped prod DEK: tenant A"]
    PKEK --> PDEK2["Wrapped prod DEK: tenant B"]
    TKEK --> TDEK["Wrapped test DEK"]
    PDEK1 --> PC1["Ciphertext prod A"]
    PDEK2 --> PC2["Ciphertext prod B"]
    TDEK --> TC["Ciphertext thử nghiệm"]
~~~

**Không mặc định một root key duy nhất cho toàn tổ chức** hoặc giả định có thể xem root key nội bộ của nhà cung cấp. Một số KMS thực hiện nhiều tầng khóa và quản lý phần trong cùng; inventory của ứng dụng thường chỉ theo dõi **các key resource và quan hệ mà mình quản lý được**.

### 6.1. Không chuyển dữ liệu qua environment bằng cách chép mỗi ciphertext

Nếu copy ciphertext prod sang test:

- Test có thể **không giải mã được** vì không có quyền KEK/DEK prod — đây thường là hành vi mong muốn.
- Nếu ai đó cấp thêm quyền test lên prod KMS để “chữa lỗi”, ranh giới môi trường có thể bị phá.
- Nếu dữ liệu thật không được phép dùng trong test, ngay cả copy ciphertext cũng có thể vi phạm chính sách dữ liệu, đặc biệt khi metadata hoặc AAD chứa thông tin nhạy cảm.

Đường chuyển dữ liệu đúng thường phải được thiết kế riêng: **phê duyệt việc trích xuất → biến đổi/ẩn danh nếu cần → mã hóa bằng khóa đích mới → cấp quyền theo environment đích → kiểm thử**. Không coi việc có thể \`Decrypt\` là đủ quyền sao chép dữ liệu.

### 6.2. Dùng chung DEK làm khó kiểm soát nonce và vòng đời

Với **AES-GCM**, nonce/IV không được tái sử dụng dưới cùng DEK. Nếu dev và prod dùng chung DEK, hai môi trường có thể cùng sinh nonce mà không phối hợp, tăng rủi ro nghiêm trọng dù mỗi môi trường tự cho rằng đang quản lý số lượt mã hóa an toàn.

Tách DEK theo environment giúp:

- Giảm phạm vi sự cố khi một môi trường bị chiếm.
- Quản lý nonce và giới hạn lượt sử dụng theo phạm vi rõ.
- Thực hiện rotation, retire hoặc destroy một môi trường mà không ảnh hưởng dữ liệu môi trường khác.
- Giảm khả năng rò rỉ bí mật qua debug/log và CI/CD non-prod.

## 7. Environment trong vòng đời khóa

Một key inventory hữu ích không chỉ ghi môi trường tại thời điểm tạo. Nó cần biết **trạng thái, người sở hữu và các thao tác được phép trong từng môi trường**.

| Giai đoạn | Câu hỏi theo environment | Cách kiểm soát |
| --- | --- | --- |
| **Generation** | Khóa được tạo trong môi trường nào, bằng nguồn ngẫu nhiên nào? | Dùng CSPRNG/KMS/HSM phù hợp; tạo key material độc lập theo chính sách |
| **Provisioning** | Workload môi trường nào được nhận/được dùng khóa? | Cấp qua định danh xác thực; không chuyển secrets prod sang test |
| **Storage** | Khóa/metadata/wrapped key nằm ở account, region, backup nào? | Kiểm soát secret storage, KMS policies, replication và key version |
| **Usage** | Có request nào dùng key sai environment, tenant hoặc purpose? | Fail closed, IAM, authorization, audit |
| **Rotation** | Khóa mới thuộc môi trường nào? Dữ liệu lịch sử sử dụng version nào? | Chuyển workload trong từng môi trường, giữ version và migration plan |
| **Deactivation/Revocation** | Key bị ngừng dùng tại môi trường nào và các instance đã nhận trạng thái chưa? | Đồng bộ chính sách, cache invalidation và quyền KMS |
| **Destruction** | Có phụ thuộc từ environment khác hoặc DR/backup chưa xử lý không? | Kiểm kê trước khi hủy và lưu chứng cứ |
| **Incident response** | Lộ khóa trong dev có lan sang prod không? | Tra quan hệ chia sẻ vật liệu/credential, giới hạn blast radius |

### 7.1. Rotation không đồng nghĩa chuyển môi trường

Khi khóa \`prod-dek-v1\` đến hạn rotation, hệ thống nên tạo \`prod-dek-v2\` trong ranh giới production và chuyển dữ liệu/đường dùng theo kế hoạch. Không lấy \`test-dek-v2\` làm khóa thay thế chỉ vì nó mới hơn.

**Đổi environment của một key record từ test sang production không tạo ra key material độc lập.** Nếu key đã từng nằm trong máy developer, build cache hoặc logs, chuyển nhãn không thể làm biến mất các bản sao trước đó.

### 7.2. Compromised state theo environment

Nếu một MAC key dùng cho test bị lộ:

- Nếu **thực sự tách key, quyền và dữ liệu**, phạm vi sự cố có thể chỉ giới hạn ở test.
- Nếu cùng vật liệu MAC key cũng được dùng trong prod, prod cũng có nguy cơ bị giả mạo thông điệp.
- Nếu service account test có quyền truy cập KMS prod, cần điều tra các thao tác prod dù raw test key không giống prod key.

**Không chỉ xem environment tag** khi đánh giá sự cố. Phải kiểm tra quan hệ material, identities, grants và audit logs.

### 7.3. Destroy key theo environment

Hủy key ở \`staging\` phải không làm mất khả năng đọc ciphertext production, nhưng điều này chỉ đúng nếu **khóa và các phụ thuộc đã được phân tách thực sự**. Trước khi destroy, kiểm kê key version, wrapped DEK, backup, DR, tài khoản dùng chung và retention.

## 8. Disaster Recovery (DR) có phải một environment tách biệt?

**DR** có thể là một environment vận hành riêng hoặc một vùng phục hồi của cùng production, tùy kiến trúc. Hai mô hình có tác động bảo mật khác nhau.

### 8.1. Mô hình A — DR là bản phục hồi production

Trong mô hình này, dữ liệu production được backup/replicate tới DR và vẫn phải có khả năng giải mã khi failover. Tổ chức cần:

1. Cấu hình **replication hoặc phương án khôi phục khóa** mà KMS/HSM hỗ trợ, không tự sao chép raw key qua kênh không kiểm soát.
2. Quản lý **quyền của workload DR** được kích hoạt theo điều kiện phù hợp.
3. Kiểm tra key ID/region, bản wrapped DEK và metadata để khôi phục không dùng sai khóa.
4. Thử DR failover/restore trong ranh giới được phê duyệt; ghi kết quả và quyền được mở tạm thời.
5. Thu hồi quyền đặc biệt sau khi kết thúc failover theo chính sách.

Trong mô hình này, DR có thể cần **truy cập những khóa/tài liệu mã hóa phục vụ production**. Điều đó là ngoại lệ được thiết kế và phê duyệt, **không phải giấy phép cho mọi môi trường non-prod dùng khóa prod**.

### 8.2. Mô hình B — DR/test restore độc lập

Một môi trường diễn tập có thể dùng bản sao **đã biến đổi hoặc đã re-encrypt** và khóa riêng để không mở quyền truy cập dữ liệu thật. Điều đó phù hợp khi mục tiêu chỉ là kiểm tra phần mềm hoặc khả năng vận hành, không phải diễn tập khôi phục y hệt dữ liệu production.

**Không gắn nhãn \`dr\` rồi tự suy ra được quyền \`Decrypt\` mọi prod key.** Inventory cần thể hiện **đích phục hồi, chế độ failover, owner và chính sách có quyền trong thời điểm nào**.

### 8.3. Khôi phục backup có thể làm sống lại khóa cũ

Khi restore database hoặc cấu hình cũ, key alias, grants hoặc environment metadata có thể trở lại giá trị trước rotation/revocation. Nếu khóa đã compromised hoặc destroyed, điều phối phục hồi phải giữ **lịch sử trạng thái/tombstone** để không vô tình cấp lại quyền sử dụng.

Một key inventory có **version và mốc thời gian** là nền tảng để đối chiếu hiện trạng trước/sau restore.

## 9. Quy trình kiểm soát cross-environment key usage

**Cross-environment key usage** là trường hợp một workload thuộc môi trường A cố dùng khóa thuộc môi trường B. Phần lớn những yêu cầu này nên bị từ chối; trường hợp được phép như DR failover hoặc migration có thể được xử lý qua **luồng ngoại lệ rõ ràng**.

### 9.1. Preflight để cấp quyền dùng khóa

1. **Xác thực workload** bằng service identity thực tế, không lấy môi trường từ header client tùy ý.
2. **Đọc key metadata từ inventory đáng tin cậy**, gồm environment, owner, purpose, key state, region/account và version.
3. **Đánh giá scope:** Workload được phép ở environment nào, tenant nào, được gọi operation nào?
4. **So khớp dữ liệu:** Dữ liệu/ciphertext đang nằm ở environment và domain nào; có yêu cầu re-encrypt hoặc sanitization không?
5. **Kiểm tra chính sách KMS/HSM/IAM thực tế** trước khi cấp quyền; không dựa duy nhất vào một điều kiện trong code ứng dụng.
6. **Chỉ mở ngoại lệ theo hồ sơ được phê duyệt** có thời hạn, mục đích và audit; nếu không đủ chứng cứ thì từ chối.

~~~mermaid
flowchart TD
    REQ["Workload yêu cầu Encrypt/Decrypt/Unwrap"] --> AUTH["Xác thực identity<br/>xác định environment tin cậy"]
    AUTH --> LOOKUP["Tra key inventory<br/>key ID/version, env, owner, purpose"]
    LOOKUP --> CHECK{"Identity + env + tenant + purpose<br/>được phép và key active?"}
    CHECK -->|"Không"| DENY["DENY + audit"]
    CHECK -->|"Có"| KMS["IAM/KMS/HSM policy kiểm tra tiếp"]
    KMS --> OPS["Thực hiện phép toán được phép"]
    OPS --> LOG["Audit metadata, không log raw key"]
    KMS -.->|"Từ chối"| DENY
~~~

### 9.2. Dữ liệu nào không được tin từ client?

Một request kiểu:

~~~json
{
  "environment": "production",
  "tenant": "tenant-a",
  "keyId": "profile-dek-2026-11-v2",
  "operation": "decrypt"
}
~~~

**Không tự cấp quyền** chỉ vì client gửi \`"environment": "production"\`. Những trường này có thể là **yêu cầu**, nhưng hệ thống phải **đối chiếu với danh tính đã xác thực, quyền trên tài nguyên, policy KMS và quyền đối với dữ liệu**. Đặc biệt, không để client chọn một **key ARN/resource** tùy ý rồi chuyển nguyên đến KMS bằng một service account có quyền rộng.

## 10. Java: kiểm soát Environment bằng metadata đáng tin cậy

Đoạn code Java 17 dưới đây minh họa một **policy gate** trước khi dịch vụ sử dụng khóa. Mục tiêu là:

- Phân biệt môi trường của **workload được xác thực** và môi trường sở hữu **key resource**.
- Kiểm tra **key state, purpose, tenant** cùng environment.
- Mặc định **deny cross-environment**.
- Trường hợp DR/migration phải đi qua workflow riêng được phê duyệt; **không có fallback tự động**.

~~~java
import java.util.Objects;
import java.util.Set;

public final class KeyEnvironmentPolicyDemo {
    enum Environment {
        DEVELOPMENT, TEST, STAGING, PRODUCTION, DR
    }

    enum Operation {
        ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY, GENERATE_MAC
    }

    enum State {
        ACTIVE, DEACTIVATED, SUSPENDED, COMPROMISED, DESTROYED
    }

    record WorkloadIdentity(
            String principalId,
            Environment trustedEnvironment,
            Set<String> permittedTenants,
            Set<Operation> permittedOperations
    ) {}

    record KeyRecord(
            String keyId,
            int version,
            Environment environment,
            String tenantScope,
            State state,
            Set<Operation> permittedPurposes
    ) {}

    static boolean allow(
            WorkloadIdentity workload,
            KeyRecord key,
            String requestedTenant,
            Operation operation
    ) {
        if (workload == null || key == null || operation == null ||
                requestedTenant == null) {
            return false;
        }
        if (workload.principalId() == null ||
                workload.principalId().isBlank()) {
            return false;
        }
        if (workload.trustedEnvironment() == null ||
                key.environment() == null ||
                workload.trustedEnvironment() != key.environment()) {
            return false; // Không tự cho phép cross-environment.
        }
        if (key.version() <= 0 || key.keyId() == null ||
                key.keyId().isBlank() || key.state() != State.ACTIVE) {
            return false;
        }
        if (!Objects.equals(key.tenantScope(), requestedTenant) ||
                !workload.permittedTenants().contains(requestedTenant)) {
            return false;
        }
        return workload.permittedOperations().contains(operation) &&
                key.permittedPurposes().contains(operation);
    }

    public static void main(String[] args) {
        WorkloadIdentity testService = new WorkloadIdentity(
                "orders-test-svc",
                Environment.TEST,
                Set.of("tenant-a"),
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );

        KeyRecord testKey = new KeyRecord(
                "orders-test-v1", 1, Environment.TEST, "tenant-a",
                State.ACTIVE,
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );

        KeyRecord prodKey = new KeyRecord(
                "orders-prod-v2", 2, Environment.PRODUCTION, "tenant-a",
                State.ACTIVE,
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );

        System.out.println("Test key access: " +
                allow(testService, testKey, "tenant-a", Operation.DECRYPT));
        System.out.println("Prod key from test service: " +
                allow(testService, prodKey, "tenant-a", Operation.DECRYPT));
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Test key access: true
Prod key from test service: false
~~~

### 10.1. Đây là lớp bảo vệ bổ sung, không thay IAM/KMS

Ví dụ chỉ có giá trị nếu **WorkloadIdentity.trustedEnvironment** được điền từ **nguồn xác thực đáng tin cậy** (chẳng hạn hệ thống identity của hạ tầng) và **KeyRecord** đến từ inventory có quyền sửa bị kiểm soát. Nếu client được tự tạo hai record này, phép kiểm tra không có giá trị bảo mật.

Trong production cần thêm:

1. **IAM/KMS resource policy** giới hạn đúng key ARN/key resource; không phụ thuộc duy nhất vào phép so chuỗi environment.
2. Quyền người dùng và **record-level authorization** ở tầng ứng dụng; workload có thể đúng prod nhưng người dùng không được đọc mọi tenant.
3. **Encryption context/AAD** ràng buộc môi trường, tenant, mục đích hoặc record ID khi phù hợp. Cần xác thực nguồn dữ liệu của context; context không phải secret.
4. Kiểm tra key version và cấu hình crypto; không cho client **chọn thuật toán yếu hơn** hoặc đổi key resource ngoài policy.
5. Các nhánh **DR/cross-environment migration** phải có workflow, phê duyệt, thời hạn và audit riêng; không nới rộng hàm \`allow\` thành “mọi DR đều được đọc prod”.
6. Đồng bộ/caching inventory an toàn. Khi key đã **revoked/compromised**, instance không được tiếp tục tin một record ACTIVE cũ quá chính sách.

**Không log raw key, plaintext, secret token hay credential** khi ghi nhận quyết định policy; log nên chứa key ID, environment, principal, operation, tenant và lý do từ chối ở mức an toàn.

## 11. Inventory và audit: phát hiện sai môi trường

Khi inventory có trường Environment đủ chuẩn, tổ chức có thể tạo nhiều kiểm tra tự động:

| Tín hiệu / điều kiện | Rủi ro gợi ý | Hành động |
| --- | --- | --- |
| Test workload gọi **Decrypt** trên prod key | Ranh giới môi trường có thể bị phá hoặc credential bị chiếm | Từ chối, cảnh báo, kiểm tra IAM và nguồn request |
| Key không có environment | Không rõ policy/owner hoặc migration cũ | Đưa vào danh sách cần phân loại, hạn chế dùng đến khi xác minh |
| Environment tag và hạ tầng owner/account mâu thuẫn | Metadata sai, tag bị sửa hoặc resource bị di chuyển trái quy trình | Điều tra nguồn tin cậy, không tự chấp nhận tag |
| Prod DEK xuất hiện trong secret manager test | Rò key material hoặc cấp phát nhầm | Cô lập, đánh giá compromise, thay key khi cần |
| Dữ liệu prod được restore sang test với wrapped DEK prod | Có thể dẫn tới cấp quyền cross-env hoặc lộ dữ liệu thật | Chặn, kiểm tra chính sách dữ liệu, re-encrypt/sanitize |
| Key staging vẫn được dùng sau khi dự án đã xóa | Orphan key, tồn đọng secret/chi phí | Kiểm kê owner và retention, rotate/retire/destroy đúng quy trình |
| DR principal có quyền Unwrap mọi key quanh năm | Blast radius lớn, quyền quá rộng | Hạn chế scope, áp dụng điều kiện kích hoạt và review |
| Key registry ghi active nhưng KMS resource đã disabled | Sai lệch trạng thái, rủi ro phục hồi và vận hành | Đối soát inventory với API và audit KMS |

### 11.1. Đối soát inventory với hệ thống thực

Không chỉ dựa vào **bản ghi được khai báo**. Một chương trình inventory nên so sánh định kỳ theo phạm vi được phép với **KMS/HSM key resources, secret manager, certificate inventory, IAM policy và nguồn metadata triển khai**.

Một quy trình đối soát có thể phát hiện:

- **Khóa bị bỏ quên** vì không còn chủ sở hữu.
- Khóa có **environment thiếu hoặc không nhất quán**.
- Khóa vẫn được dùng sau khi chuyển sang **retired/deactivated**.
- Quyền cross-env mới được cấp nhưng không có change record.
- Wrapped DEK/ciphertext còn tham chiếu khóa cũ sắp bị hủy.

**Không quét hoặc xuất raw key material để xây inventory.** Inventory nên dựa trên API metadata, log có kiểm soát, tham chiếu và quan hệ phụ thuộc.

### 11.2. Những thông tin audit hữu ích

Một sự kiện dùng khóa có thể ghi:

~~~text
time
principalId / workloadIdentity
workloadEnvironment (nguồn xác thực)
keyId + keyVersion + keyEnvironment
operation (Encrypt/Decrypt/Sign/Unwrap/...)
tenantScope / dataDomain
policyDecision (allow/deny)
kmsResult / incidentOrChangeId
~~~

Không cần log ciphertext, raw DEK, private key hoặc plaintext để biết workload test đang cố dùng prod key.

### 11.3. Trạng thái và thời gian xem xét

Đối với khóa production, inventory cần biết **khi nào chủ sở hữu đã xác nhận environment/scope là đúng**, không chỉ \`createdAt\`. Review lặp lại có thể tập trung vào **quyền quá rộng, key version cũ, orphaned key và đường sử dụng giữa các môi trường**.

## 12. Các tình huống triển khai quan trọng

### 12.1. Sao chép database production sang staging

**Tình huống:** Nhóm phát triển muốn chạy kiểm thử với dữ liệu thật. Database chứa ciphertext được mã hóa bằng production DEK và metadata tham chiếu production KEK.

**Thiết kế sai:** Cấp service account staging quyền \`kms:Decrypt\` trên KEK production để test chạy nhanh.

**Thiết kế cần cân nhắc:** Đánh giá việc dùng dữ liệu thật có được phép không. Nếu phải tạo dữ liệu thử nghiệm, sử dụng nguồn đã được kiểm soát để **sanitize/tokenize dữ liệu theo chính sách**, sau đó **mã hóa dưới DEK/KEK staging mới**. Không sao chép raw key hoặc quyền prod sang staging. Nếu một chương trình kiểm thử đặc biệt thật sự cần dữ liệu nhạy cảm, phải có ranh giới bảo vệ và phê duyệt tương ứng, không coi đó là staging thông thường.

### 12.2. Dùng lại HMAC key của webhook giữa test và prod

**Tình huống:** Cùng một đối tác gửi webhook test và prod; ứng dụng dùng chung MAC key để tiện cấu hình.

**Rủi ro:** Nếu test key lộ qua log hoặc môi trường debug, kẻ tấn công có thể tạo tag hợp lệ cho những thông điệp mà production tin tưởng, nếu giao thức và quyền không phân biệt môi trường.

**Thiết kế tốt hơn:** Dùng **MAC key riêng cho từng môi trường**, key ID và endpoint riêng, xác thực các trường ngữ cảnh liên quan, chống replay, giới hạn quyền và quản lý rotation độc lập.

### 12.3. Khóa ký số trong CI/CD

**Tình huống:** Pipeline build thử nghiệm được cấp quyền dùng **private code-signing key production** để ký artifact debug.

**Rủi ro:** Tài khoản pipeline hoặc runner ít tin cậy hơn có thể tạo artifact được xác minh là production-signed. Nếu signing key là non-exportable trong HSM, rủi ro **lạm dụng Sign API** vẫn tồn tại.

**Thiết kế tốt hơn:** Tách **test signing key** và **production signing key**, tách quyền ký ở release pipeline, kiểm tra provenance/approval, quản lý public verification key và chính sách nhận artifact theo môi trường.

### 12.4. Khôi phục production sang DR

**Tình huống:** Region chính ngừng hoạt động, dữ liệu mã hóa cần được khôi phục ở vùng dự phòng.

**Thiết kế:** Inventory cần chỉ rõ **keys nào và phiên bản nào phục vụ restore**, cơ chế KMS/HSM hỗ trợ, ranh giới quyền cho DR, điều kiện failover và cơ chế rút quyền sau sự cố. Không phụ thuộc vào việc raw key vô tình tồn tại ở một file backup không được quản lý.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ lưu \`env=prod\` như nhãn trang trí | Workload dev vẫn có thể dùng prod key | Thực thi IAM/KMS, identity và ranh giới dữ liệu |
| Dùng một DEK hoặc KEK cho dev, test, prod | Sự cố non-prod ảnh hưởng prod; khó rotate riêng | Sinh và cấp phát key material tách môi trường |
| Tin \`environment\` do client gửi | Client tự nhận là prod để vượt gate | Lấy environment từ workload identity đã xác thực |
| Suy khóa thật từ alias thay vì resource ID/version | Alias đổi mục tiêu, audit nhầm vật liệu | Kiểm kê key ID/version và nguồn quản lý |
| Không phân biệt environment với tenant/region | Cho quyền sai hoặc báo cáo thiếu | Tách các trường và policy rõ ràng |
| Copy ciphertext prod sang test rồi mở quyền Decrypt prod | Lộ dữ liệu và phá ranh giới tin cậy | Sanitize/re-encrypt và phê duyệt chuyển dữ liệu |
| Dùng chung MAC hoặc signing key giữa môi trường | Giả mạo webhook hoặc artifact production | Key riêng, purpose riêng, kiểm soát Sign/Verify |
| Nghĩ một khóa prod trong DR là dấu hiệu lỗi | Có thể chặn phục hồi hợp lệ | Mô hình hóa DR đúng: replica prod được phép vs test restore |
| Coi mọi DR được quyền giải mã tất cả prod keys | Quyền quá rộng và khó điều tra | Giới hạn theo key, role, điều kiện failover, thời hạn |
| Tự chuyển tag environment khi rotate | Không tạo key mới, không xóa bản sao cũ | Rotation phải thay vật liệu/phiên bản theo policy |
| Chỉ đánh giá usage per instance của AES-GCM | Bỏ sót tổng nonce dưới DEK dùng chung | Theo dõi số lần dùng trên toàn phạm vi key material |
| Hủy key non-prod mà quên backup/DR | Mất dữ liệu phục hồi hoặc còn bản sao key | Dependency inventory và pre-destruction checks |
| Khôi phục backup đưa key compromised trở lại | Hệ thống dùng lại khóa không tin cậy | Lưu tombstone/state bền vững, đối soát khi restore |
| Lưu raw key trong inventory | Inventory trở thành kho bí mật tập trung | Chỉ lưu metadata và tham chiếu, bảo vệ vật liệu ở KMS/HSM |
| Không review orphan key | Khóa tồn tại quá thời hạn hoặc mất owner | Đối soát/assign owner, retire/destroy theo chính sách |

## 14. Checklist kiểm tra Environment trong Key inventory

Trước khi coi inventory đầy đủ, hãy trả lời:

1. **Định nghĩa:** Tập environment chuẩn của tổ chức gồm những giá trị nào? Có quy tắc ánh xạ tên cũ không?
2. **Nguồn tin cậy:** Environment của key lấy từ KMS resource/account hay một metadata tag có thể bị thay đổi? Ai có quyền sửa?
3. **Identity:** Environment của workload được xác định từ danh tính triển khai đã xác thực hay chỉ từ request?
4. **Phân tách:** Dev/test/staging/prod có dùng key material, identity và secret distribution độc lập?
5. **Scope:** Inventory có ghi rõ tenant, account, region, purpose, owner, algorithm, key ID và version riêng với environment?
6. **Permissions:** IAM/KMS/HSM có thực sự chặn thao tác \`Decrypt\`, \`Unwrap\`, \`Sign\` và \`GenerateMac\` cross-env ngoài ngoại lệ được duyệt?
7. **Encryption:** DEK/KEK, key ID và AAD/encryption context có phản ánh đúng ranh giới môi trường khi cần không?
8. **Dữ liệu:** Có quy trình kiểm soát khi xuất/restore dữ liệu production sang môi trường khác, bao gồm sanitization và re-encryption?
9. **DR:** Tài liệu có phân biệt DR là bản phục hồi production với DR/test restore độc lập? Có kiểm thử failover và quyền tương ứng?
10. **Lifecycle:** Rotation, revoke, compromised state và destroy có được thực thi theo đúng environment và key version?
11. **Backup:** Có inventory các bản sao wrapped key, HSM/KMS replica, region và hệ thống restore liên quan?
12. **Audit:** Có ghi workload environment, key environment, key ID/version, operation, tenant và quyết định policy mà không log raw key?
13. **Đối soát:** Có thể phát hiện key thiếu environment, sai account, orphan owner và grants mới không?
14. **Kiểm thử:** Đã thử một workload test gọi prod key, key bị disable, metadata bị sửa, alias đổi mục tiêu và restore backup cũ?
15. **Sự cố:** Khi key non-prod bị lộ, có thể chứng minh độc lập vật liệu khóa/quyền khỏi prod hoặc khoanh vùng rủi ro nhanh chóng không?

## 15. Ghi nhớ

- **Environment trong key inventory** cho biết khóa thuộc ranh giới triển khai nào: dev, test, staging, production hay DR. Đây là **thông tin quản trị và chính sách bảo mật**, không chỉ nhãn báo cáo.
- **Environment khác region, cloud account, tenant, data classification và purpose.** Một bản ghi khóa đủ tốt cần tách các thuộc tính này.
- **Nhãn environment không tự chặn truy cập.** Phải thực thi bằng workload identity, IAM, chính sách KMS/HSM, authorization nghiệp vụ và kiểm toán.
- **Không chia sẻ DEK/KEK/MAC/private signing key/pepper giữa prod và non-prod** nếu không có thiết kế được đánh giá và phê duyệt. Sự tách biệt làm giảm blast radius và hỗ trợ rotation/crypto-erasure.
- **Envelope encryption, key ID/version, AAD và encryption context** giúp mô tả và ràng buộc ngữ cảnh, nhưng không thay quyền sử dụng key và dữ liệu.
- **DR phải được mô hình hóa rõ ràng:** Một bản phục hồi production có thể cần đường khôi phục khóa được cho phép; điều đó không biến staging/test thành miền có quyền prod.
- **Inventory phải được đối soát với hạ tầng thực tế** và sử dụng xuyên suốt tạo, cấp phát, lưu, sử dụng, xoay vòng, thu hồi và hủy.

Khi thấy một khóa trong kho kiểm kê được gắn **Environment = production**, hãy hỏi: **“Ai xác nhận nhãn này?”, “KMS/IAM có thực sự ngăn môi trường khác sử dụng khóa?”, “Nếu khóa bị lộ, xoay vòng hoặc hủy, dữ liệu và các môi trường nào sẽ chịu ảnh hưởng?”** Trả lời được ba câu hỏi đó mới biến trường Environment thành một phần hữu ích của hệ thống quản lý khóa an toàn.
