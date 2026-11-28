# Cryptoperiod là gì

> **Chương:** Cryptoperiod và rotation  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Cryptoperiod là gì?

**Cryptoperiod** là **khoảng thời gian một khóa mật mã được cho phép sử dụng bởi các chủ thể đã được ủy quyền cho những thao tác mật mã được quy định**. Khái niệm này giúp tổ chức trả lời: *Khóa được dùng để bảo vệ dữ liệu mới đến lúc nào? Khi nào ngừng dùng khóa đó? Có được tiếp tục dùng để giải mã, unwrap hoặc xác minh dữ liệu cũ không?*

Trong quản lý khóa, câu hỏi quan trọng không chỉ là **khóa mạnh bao nhiêu bit** mà còn là **dùng bao lâu, cho việc gì, với lượng dữ liệu bao nhiêu và dưới những điều kiện tin cậy nào**. Một khóa AES-256 sinh từ CSPRNG vẫn có thể trở thành rủi ro khi bị tái sử dụng không kiểm soát, lưu quá lâu, bị lộ qua ứng dụng hoặc tiếp tục sử dụng sau khi chính sách/thuật toán thay đổi.

Theo cách phân chia thường dùng trong hướng dẫn quản lý khóa như **NIST SP 800-57**, cryptoperiod có thể được mô tả bằng **originator-usage period** (thời kỳ được phép dùng khóa để áp dụng bảo vệ mật mã mới) và **recipient-usage period** (thời kỳ được phép dùng khóa để xử lý/bỏ lớp bảo vệ đã tồn tại), với ý nghĩa cụ thể tùy loại khóa và thao tác.

**Ví dụ:** một KEK `orders-kek/v4` có thể:

- Được **sinh ngày 01/12/2026** nhưng chỉ **kích hoạt ngày 05/12/2026**.
- Được phép **wrap các DEK mới** từ ngày 05/12/2026 đến trước ngày 05/03/2027.
- Sau đó **không được wrap DEK mới**, nhưng có thể còn được **unwrap DEK cũ** đến trước ngày 05/09/2027 để phục vụ rewrap, restore và dữ liệu lịch sử, nếu key state/provider/policy cho phép.
- Bị **revoke ngay lập tức** nếu có bằng chứng lộ khóa, bất kể ngày hết hạn kế hoạch.
- Được **hủy** chỉ khi đã xử lý các phụ thuộc, backup/retention và yêu cầu pháp lý, hoặc có quyết định crypto-erasure chủ đích.

Như vậy, **cryptoperiod không đơn giản là “key có tuổi thọ 90 ngày”**, cũng không phải cứ hết hạn là xóa khóa ngay.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Nêu được định nghĩa cryptoperiod và vì sao cần giới hạn thời gian dùng khóa.
2. Phân biệt **originator/recipient usage**, ngày sinh, ngày kích hoạt, thời hạn chứng thư, data retention, rotation và revocation.
3. Chọn cryptoperiod theo **key class, algorithm, purpose, threat model, lượng sử dụng, HSM/KMS, backup và tác động sự cố**.
4. Thiết kế state machine và **policy gate** kiểm tra thời gian, key state, operation, tenant và quyền trước khi dùng khóa.
5. Hiểu **tại sao rotation không tự xóa mọi nguy cơ**, và khi nào phải rewrap hoặc re-encrypt.
6. Áp dụng ví dụ **Java 17**, metadata key inventory, kiểm toán, runbook và câu hỏi tự kiểm tra.

## 2. Vì sao khóa mật mã cần có cryptoperiod?

### 2.1. Giới hạn cửa sổ bị lộ và lạm dụng

Một secret key tồn tại càng lâu, càng có nhiều cơ hội bị lộ qua **memory dump, log, nhầm quyền IAM, snapshot, key export, backup, thiết bị bị chiếm hoặc người nội bộ lạm quyền**. Việc thay vật liệu khóa có kế hoạch giúp giới hạn **quá trình phát sinh dữ liệu mới phụ thuộc khóa cũ**, nhưng không tự làm dữ liệu cũ trở nên an toàn khi key cũ đã bị lộ.

**Cryptoperiod là biện pháp giảm rủi ro, không phải bằng chứng khóa chưa từng bị compromise.** Một khóa dùng 1 giờ vẫn có thể lộ ngay phút đầu.

### 2.2. Giới hạn lượng sử dụng và giới hạn thuật toán

Một số scheme có **usage limits**: lượng dữ liệu được mã hóa, số message, số operation hoặc yêu cầu **không tái sử dụng nonce**. Ví dụ, AES-GCM yêu cầu không lặp lại cặp **(key, nonce)** trong các lần mã hóa độc lập; việc đạt đến ngưỡng nonce/usage đã được thiết kế có thể bắt buộc rotate **sớm hơn ngày hết hạn trên lịch**.

**Không có quy tắc “AES-256 an toàn nên có thể dùng vô hạn”.** Thời gian và lượng sử dụng là hai chiều khác nhau của chính sách.

### 2.3. Đáp ứng thay đổi về hệ thống và niềm tin

Chính sách có thể phải đổi khi:

- Thuật toán, key size hoặc provider không còn được phê duyệt.
- HSM firmware/KMS configuration phát hiện lỗi.
- Recipient hoặc workload bị offboard, mất quyền hoặc đổi trust domain.
- Tenant chuyển vùng dữ liệu hoặc thay data classification.
- Một key version bị nghi compromise dù chưa đến lịch rotate.

### 2.4. Tránh khóa vĩnh viễn bị bỏ quên

Nếu không theo dõi cryptoperiod, một secret có thể tồn tại nhiều năm dưới tên `current-key`; không còn ai biết key owner, phạm vi, backup hay số bản mã phụ thuộc. Đặt **thời hạn + owner + cảnh báo + rotation plan** giúp biến quản lý khóa thành một quy trình có thể kiểm tra.

## 3. Phân biệt các khái niệm thời gian liên quan

| Thuật ngữ | Ý nghĩa | Có đồng nghĩa cryptoperiod không? |
| --- | --- | --- |
| **`generatedAt` / creation time** | Thời điểm key material được tạo | Không; khóa có thể chưa active |
| **`importedAt`** | Thời điểm vật liệu được nhập vào KMS/HSM | Không; nguồn tạo có thể ở nơi khác và sớm hơn |
| **`activationAt`** | Thời điểm sớm nhất khóa được phép hoạt động theo policy | Một ranh giới có thể dùng để bắt đầu cryptoperiod |
| **Originator-usage period** | Khoảng được áp bảo vệ mới: encrypt, wrap, MAC/sign mới… | Một thành phần thường dùng của cryptoperiod |
| **Recipient-usage period** | Khoảng được xử lý/bỏ bảo vệ cũ: decrypt, unwrap, verify… | Một thành phần thường dùng; semantics phụ thuộc operation |
| **`newUseUntil`** | Mốc chấm dứt **tạo bảo vệ mới** theo policy nội bộ | Mốc kết thúc originator use trong thiết kế này |
| **`oldUseUntil`** | Mốc chấm dứt use cũ theo policy, nếu có | Mốc kết thúc recipient use trong thiết kế này |
| **Rotation** | Chuyển sang **key material/version mới** cho use mới | Một hành động, không phải khoảng thời gian |
| **Retirement/deactivation** | Ngừng use mới hoặc ngừng một nhóm operation | Một trạng thái/hành động lifecycle |
| **Revocation** | Rút quyền hoặc niềm tin vì sự cố/điều kiện | Có thể xảy ra trước lịch cryptoperiod |
| **Destruction** | Hủy key material theo semantics và evidence thích hợp | Không tự được phép khi new-use period kết thúc |
| **Data retention** | Thời gian cần giữ dữ liệu | Có thể dài hơn nhiều cryptoperiod |
| **Certificate validity** | `notBefore/notAfter` của một chứng thư X.509 | Không đồng nghĩa thời gian key được phép ký mới |
| **Session/token TTL** | Thời hạn phiên, token hoặc grant | Khác thời hạn key vật liệu; có thể ngắn hơn |

### 3.1. Một khóa có thể hết hạn tạo bảo vệ mới nhưng vẫn cần tồn tại

Một DEK mã hóa tài liệu hôm qua có thể tiếp tục cần để giải mã sau 5 năm nếu hồ sơ có retention 5 năm. Điều đó **không có nghĩa DEK nên được dùng để mã hóa mọi tài liệu mới trong suốt 5 năm**.

Một KEK có thể dừng wrap mới sau 3 tháng nhưng phải hỗ trợ unwrap wrapped DEK cũ cho đến khi hoàn tất migration và bảo đảm restore. **Cryptoperiod của thao tác mới khác yêu cầu tồn tại của khóa cho việc đọc dữ liệu cũ.**

### 3.2. Cryptoperiod không tự tính từ `createdAt`

Một khóa có thể được **pre-generate** rồi giữ `PRE_ACTIVE` một thời gian để chuẩn bị rollout. Vì vậy, `createdAt + duration` không tự là `newUseUntil` nếu policy định nghĩa thời kỳ bắt đầu từ `activationAt` hay sự kiện khác.

### 3.3. Dữ liệu còn giữ không bắt buộc private key còn online

Đối với chữ ký số, **public key/chứng thư và thông tin xác minh lịch sử** có thể được giữ lâu để verify, trong khi **private signing key** đã bị retire/hủy theo chính sách. Không dùng việc “còn verify chữ ký lịch sử” làm lý do để giữ private signing key luôn có quyền `Sign`.

## 4. Originator-usage period và recipient-usage period

Đây là cặp khái niệm quan trọng nhất của bài.

### 4.1. Originator-usage period: được tạo bảo vệ mới khi nào?

Tùy key purpose:

- **AES DEK:** được phép mã hóa thêm plaintext mới bằng DEK.
- **KEK:** được phép wrap thêm DEK mới.
- **HMAC key:** được phép tạo MAC mới.
- **Private signing key:** được phép tạo chữ ký mới.
- **Key agreement key:** được phép tham gia những lần thiết lập khóa mới theo profile.

Sau khi kết thúc, hệ thống **không được tạo thêm sản phẩm mật mã mới dưới key version đó**, ngay cả khi khóa vẫn tồn tại để xử lý dữ liệu lịch sử.

### 4.2. Recipient-usage period: được xử lý bảo vệ cũ khi nào?

Tùy loại khóa:

- **AES DEK:** được phép giải mã những ciphertext cũ đã được bảo vệ hợp lệ.
- **KEK:** được phép unwrap những DEK cũ.
- **HMAC key:** có thể được phép verify MAC cũ.
- **Asymmetric verification:** dùng public key được tin để xác minh chữ ký lịch sử theo chính sách ký số/PKI.

**Không máy móc áp dụng hai period giống hệt cho mọi khóa.** Key agreement ephemeral có vòng đời rất ngắn; một signing public key có thể được lưu để verify lịch sử sau khi private key ngừng ký; một provider có thể không phân biệt `Wrap` và `Unwrap` trong key status `Disabled`.

### 4.3. Minh họa timeline

~~~mermaid
gantt
    title Ví dụ KEK: thời kỳ wrap mới và unwrap cũ
    dateFormat YYYY-MM-DD
    axisFormat %Y-%m
    section Key v4
    PRE_ACTIVE          :a1, 2026-12-01, 4d
    WRAP_NEW + UNWRAP   :active, a2, 2026-12-05, 90d
    UNWRAP_OLD (nếu policy cho phép) :a3, after a2, 184d
    section Successor
    Chuẩn bị KEK v5     :b1, 2027-02-15, 18d
    KEK v5 wrap mới     :active, b2, 2027-03-05, 180d
~~~

Các mốc và độ dài trong sơ đồ là **ví dụ chính sách giả định**, không phải hạn chuẩn áp dụng cho mọi khóa. Khi key bị compromise, không tiếp tục `UNWRAP_OLD` chỉ vì vẫn còn trong khoảng kế hoạch; cần incident response.

### 4.4. Khoảng thời gian nửa mở

Một cách định nghĩa thuận tiện cho policy là:

\[
\mathrm{originatorAllowed}(t)\iff
  activationAt\leq t<newUseUntil
\]

\[
\mathrm{recipientAllowed}(t)\iff
  activationAt\leq t<oldUseUntil
\]

Với quy ước này, thao tác **tại đúng `newUseUntil` đã bị từ chối**. Nhưng hai công thức chỉ thể hiện **thời gian**. Việc cho phép thực tế còn phụ thuộc **key state, identity/IAM, tenant/purpose, provider state, revocation, usage counters và policy revision**.

## 5. Cryptoperiod là một thuộc tính chính sách, không phải một con số chung

Không có một thời hạn duy nhất phù hợp cho mọi khóa, mọi hệ thống. Việc chọn khoảng thời gian phải dựa trên **loại khóa, thuật toán, lượng sử dụng, thời gian bảo vệ cần thiết, khả năng rotation, mức độ nhạy cảm và các yêu cầu tổ chức/chuẩn áp dụng**.

### 5.1. Các yếu tố thường làm period ngắn hơn

- Key được dùng để **bảo vệ dữ liệu nhạy cảm cao**, có ảnh hưởng lớn khi lộ.
- Rất nhiều message/data được mã hóa hoặc ký dưới cùng key.
- Key xuất hiện dạng rõ ở nhiều host/process hoặc bên thứ ba.
- Có nguy cơ dùng lại nonce, vượt quota/usage limit hoặc keying material bị lộ qua side channel.
- Môi trường dễ bị xâm nhập hoặc nhiều người/quy trình có quyền key operations.
- Thuật toán/provider/thiết bị sắp hết hỗ trợ hay có dấu hiệu bị suy yếu.
- Có khả năng rotate tự động với chi phí thấp.

### 5.2. Các yếu tố làm recipient period dài hơn nhưng không kéo dài originator period

- Dữ liệu ciphertext cần **lưu giữ/khôi phục trong nhiều năm**.
- Backup/snapshot/archives có `wrapped DEK` dưới key version cũ.
- Chữ ký số lịch sử cần được xác minh sau nhiều năm.
- Có giai đoạn chuyển đổi hoặc offboarding dài, yêu cầu đọc tài liệu cũ.

**Đừng vì retention dài mà cho phép encrypt/sign/wrap mới bằng một key mãi mãi.** Thay vào đó, giữ **khả năng xử lý lịch sử có kiểm soát**, hoặc rewrap/re-encrypt khi thích hợp.

### 5.3. Độ tin cậy thực tế của HSM/KMS

Một KEK non-extractable trong HSM có thể giảm rủi ro raw-key export, nhưng **API `Unwrap` vẫn có thể bị lạm dụng**. Do đó độ dài cryptoperiod còn phụ thuộc IAM, audit, approval, isolation, provider assurances và khả năng revoke nhanh.

**FIPS validation không tự định ra hạn dùng khóa**, cũng không chứng minh mọi ứng dụng/gateway bên ngoài HSM đều tuân thủ.

## 6. Cryptoperiod theo loại khóa

| Loại khóa | Originator use | Recipient/old use | Điểm cần quyết định |
| --- | --- | --- | --- |
| **DEK AES-GCM** | Mã hóa dữ liệu mới trong scope cho phép | Giải mã ciphertext lịch sử | Nonce uniqueness, usage limits, dữ liệu phụ thuộc, re-encrypt |
| **KEK / wrapping key** | Wrap DEK mới | Unwrap DEK cũ để đọc/rewrap/restore | Wrapped DEK count, backup, policy provider |
| **HMAC key** | Tạo MAC cho thông điệp/token mới | Verify MAC của thông điệp/token cũ | TTL token/message, replay, key ID/version |
| **Private signing key** | Ký mới | Thường không cần để verify; private key có thể retire | PKI, authorization, signature timestamps, compromise |
| **Public verification key** | Không tự ký; dùng verify theo trust policy | Verify chữ ký hiện tại/lịch sử khi tin cậy | Certificate status, key binding, revocation, LTV |
| **Session traffic key** | Mã hóa/MAC trong phiên/epoch hợp lệ | Giải mã đúng phiên/epoch khi còn cần | Nonce/sequence limits, rekey, forward secrecy |
| **Long-term key agreement key** | Thiết lập secret mới theo profile | Xử lý/khôi phục phiên theo protocol, nếu có | Peer authentication, reuse và compromise |
| **Ephemeral (EC)DHE key** | Một handshake hoặc phạm vi rất hẹp | Thường không lưu dài hạn | Xóa best-effort, transcript binding |
| **Device PSK** | Bảo vệ/khởi tạo phiên trong phạm vi thiết bị | Verify/decrypt giao thức cũ khi policy cho phép | Device offboarding, unique PSK, mass rotation |
| **Password-derived key / pepper** | Bảo vệ secret mới theo thiết kế | Kiểm tra/khôi phục dữ liệu cũ cho migration | KDF, password lifetime, pepper rotation |
| **Root CA/private root key** | Ký chứng thư mới theo chính sách | Verify chains dùng public trust anchor | Ceremonies, HSM, issuance windows, trust retirement |
| **Root KEK/backup wrapping key** | Wrap key cấp dưới/backup mới | Restore được backup cũ | Blast radius, quorum, archival và DR |

### 6.1. Không đánh đồng tất cả key class với “rotation 90 ngày”

Một **ephemeral TLS traffic key** có thể chỉ dùng trong một phiên; một **private CA key** có quy trình key ceremony và trust lifetime riêng; một **DEK per-object** có thể mã hóa đúng một đối tượng và không cần tạo bảo vệ mới nữa. Dán một con số lên tất cả sẽ bỏ qua rủi ro thực tế.

### 6.2. Thời gian bảo vệ dữ liệu có thể vượt thời gian dùng khóa để mã hóa

Nếu một tài liệu được mã hóa năm 2026 và phải giữ đến 2033, hệ thống cần chiến lược cho DEK/KEK và key versions để còn đọc trong những năm tiếp theo. Cryptoperiod **không đồng nghĩa** “mã hóa mất tác dụng” khi hết new-use period; ciphertext có thể vẫn được bảo vệ bởi khóa đã retire, với rủi ro cần quản trị.

## 7. Thời gian không đủ: giới hạn sử dụng, nonce và số thao tác

Thiết kế chỉ dựa trên `now < expiry` có thể không an toàn nếu một key được dùng **quá nhiều lần** trong khoảng thời gian ngắn.

### 7.1. Nonce uniqueness dưới cùng DEK

AES-GCM yêu cầu tránh tái sử dụng **(key, nonce)**. Với 96-bit nonce ngẫu nhiên và `q` lần mã hóa độc lập, xác suất va chạm xấp xỉ, trong miền gần đúng thích hợp:

\[
P_{\mathrm{collision}}\approx\frac{q(q-1)}{2^{97}}
\]

Đây là **mô hình birthday bound đơn giản**, không phải bảo đảm về an toàn tổng thể của AES-GCM. Hệ thống thực tế cần xét **giới hạn scheme, IV construction, tag length, tổng khối dữ liệu, entropy source, number of encryptions và khuyến nghị kỹ thuật áp dụng**. Nếu dùng counter, phải chống trùng giữa node/instance/restore.

**Kết luận:** khi đạt usage/nonce budget, rotate DEK ngay, **không chờ đến ngày hết hạn**.

### 7.2. Signing, MAC và operation quotas

Một key ký số/HMAC có thể có operation count hoặc exposure risk threshold; một KMS có quota/tốc độ gọi API. Hệ thống nên theo dõi:

- `encryptOperations` / `wrappedDekCount` / `signOperations`.
- `messagesOrBytesProtected` theo profile mật mã.
- `nonceAllocationState` hoặc chỉ báo nguy cơ trùng.
- Key material usage từ provider audit khi có.
- `lastUsedAt` và mức sai lệch giữa usage từ ứng dụng và KMS.

**Quota của KMS để điều tiết tải không tự bằng cryptographic usage limit**. Có thể cần cả hai loại.

### 7.3. Policy có nhiều điều kiện kết thúc

Một rule thực dụng:

~~~text
STOP_NEW_USE(key) nếu xảy ra BẤT KỲ:
 - now >= newUseUntil;
 - key state không còn ACTIVE;
 - compromise/revocation;
 - đạt usage/nonce limit;
 - algorithm/provider/key size không còn được duyệt;
 - thiếu owner/policy approval hoặc tenant/purpose mismatch.
~~~

Không dùng một **cờ `expired=false`** để bỏ qua các điều kiện còn lại.

## 8. Các mốc thời gian trong key lifecycle

Một key có thể đi qua nhiều trạng thái độc lập với thời hạn:

~~~mermaid
flowchart TD
    Need[Key owner + policy + cryptoperiod] --> Generate[GENERATE / IMPORT]
    Generate --> Register[INVENTORY + provenance + approval]
    Register --> Pre[PRE_ACTIVE / pending activation]
    Pre --> Active[ACTIVE: đúng operation, thời gian, usage]
    Active --> Retired[RETIRED: ngừng new-use]
    Active --> Suspended[SUSPENDED / COMPROMISED]
    Retired --> Recover[UNWRAP/DECRYPT OLD nếu policy cho phép]
    Suspended --> Incident[Incident response + impact assessment]
    Recover --> Dependencies[Kiểm tra ciphertext, wrapped DEK, backup]
    Incident --> Dependencies
    Dependencies --> Destroy[DESTROYED khi đủ điều kiện]
    Active --> Rotation[ROTATION: tạo successor mới]
    Rotation --> Register
~~~

### 8.1. PRE_ACTIVE

Khóa đã được sinh và đăng ký nhưng **chưa được phép phục vụ operation mới**. Đây là thời điểm chuẩn bị key distribution, thử nghiệm quyền, public key/JWKS, certificates và HSM replication.

### 8.2. ACTIVE

Khóa chỉ được dùng khi **cả policy time gate, key state và IAM/operation authorization** đều cho phép. Ví dụ, private signing key đang active cho `Sign` mới không đồng nghĩa nó được phép `Decrypt` hoặc `Export`.

### 8.3. RETIRED

Trong mô hình bài này, `RETIRED` nghĩa là **cấm tạo bảo vệ mới**, nhưng **có thể được phép xử lý dữ liệu cũ** theo policy. Đây là mô hình nghiệp vụ/registry, không phải API state chung của mọi KMS.

### 8.4. SUSPENDED/REVOKED/COMPROMISED

Nếu key bị nghi lộ, cần **chặn hoặc giới hạn operation tùy sự cố** và đánh giá dữ liệu/recipient bị ảnh hưởng. Không tự dùng period kế hoạch để “cho phép unwrap đến cuối quý” khi rủi ro raw-key compromise chưa được xử lý.

### 8.5. DESTROYED

Key material bị hủy theo bằng chứng và semantics provider. Hủy khóa có thể khiến dữ liệu không thể giải mã; trước thao tác phải xét **wrapped DEK, backup, legal hold, recovery, certificate/trust dependencies và approval**.

## 9. Cryptoperiod khác rotation như thế nào?

**Cryptoperiod là chính sách về khoảng được phép dùng khóa**; **rotation là hành động chuyển sang key material/version mới**. Hai khái niệm gắn với nhau nhưng không đồng nghĩa.

### 9.1. Rotation đúng nghĩa

Một lần rotation thông thường gồm:

1. **Sinh key material mới** trong vùng được duyệt bằng CSPRNG/KMS/HSM.
2. Gán **key ID/version** mới, owner, purpose, policy, cryptoperiod và audit references.
3. Chuẩn bị IAM, backup/DR, dependent services/recipient và activate.
4. Chuyển `primaryForNewUse` từ version cũ sang mới.
5. Cấm new-use version cũ khi hết thời kỳ.
6. Xử lý ciphertext/wrapped DEK/tokens/chữ ký cũ theo recipient period và migration plan.
7. Retire/destroy version cũ khi không còn phụ thuộc hoặc có quyết định khác hợp lệ.

**Đổi alias `current`, đổi tên biến hoặc cập nhật `createdAt` không làm thay key material**.

### 9.2. Rotation định kỳ khác emergency rotation

**Scheduled rotation:** dựa trên cryptoperiod, usage và kế hoạch để giảm rủi ro chủ động. **Emergency rotation:** do nghi lộ khóa, sai cấu hình entropy, provider compromise, key loss hoặc thu hồi trust; có thể cần **re-encrypt** và sự cố pháp lý/incident response, không chỉ đặt key mới cho dữ liệu tương lai.

### 9.3. Rotation không đảo ngược dữ liệu đã lộ

Nếu attacker đã có **DEK và ciphertext**, thay KEK mới hoặc chỉ rewrap DEK **không thu hồi** bản raw DEK đó. Nếu attacker có KEK cũ và bản wrapped DEK cũ, họ vẫn có thể unwrap ngoại tuyến. Khi key material có thể đã lộ, đánh giá **DEK mới + re-encrypt**, dữ liệu bị truy xuất và những bản backup/ciphertext đã bị sao chép.

## 10. Ví dụ timeline KEK, DEK và backup

Giả sử một hệ thống lưu hồ sơ thanh toán lâu dài. KEK `payments-kek/v4` được tạo ngày **01/12/2026**, active ngày **05/12/2026**.

| Thời điểm giả định | Sự kiện | Việc được phép |
| --- | --- | --- |
| **01/12/2026** | Sinh KEK `v4` ở HSM/KMS | Chỉ provisioning/pre-active |
| **05/12/2026** | Kích hoạt `v4` | Wrap DEK mới và unwrap DEK cũ theo quyền |
| **15/02/2027** | Sinh successor `v5` | Chuẩn bị grant, audit, backup, canary |
| **05/03/2027** | Chuyển primary sang `v5` | `v4` không wrap mới; có thể unwrap cũ |
| **03–08/2027** | Rewrap các DEK đang được `v4` bảo vệ | Đọc theo key version đúng, di chuyển có kiểm chứng |
| **05/09/2027** | Kế hoạch đóng old-use của `v4` | Chỉ đóng nếu ciphertext, backup/retention đã được xử lý |
| **Sau dependency sign-off** | Hủy `v4` theo policy | Không còn quyền hoặc vật liệu cũ |

### 10.1. Một thực tế quan trọng: backup có thể sống lâu hơn kế hoạch

Nếu bản backup năm 2026 chứa `wrappedDEK=Wrap(KEK_v4, DEK_A)`, hủy `KEK_v4` trước khi backup có thể được restore bằng kế hoạch thay thế sẽ làm mất khả năng giải mã bản sao lưu. **Cryptoperiod không cho phép bỏ qua sự tồn tại của backup**.

### 10.2. “Hết old-use” có nghĩa gì nếu còn bản mã cũ?

Trong một hệ thống được quản trị đúng, tới `oldUseUntil` phải có **migration/rewrap/re-encrypt hoàn tất, một quyết định không cần dữ liệu cũ nữa, hoặc một ngoại lệ được phê duyệt**. Không đơn giản chạy cron xóa khóa đúng ngày mà không có dependency preflight.

### 10.3. Data retention và cryptoperiod là hai trục độc lập

Một bảng hóa đơn có thể giữ **7 năm**, trong khi KEK wrap mới chỉ được dùng **vài tháng theo policy giả định**. Việc quản lý nhiều key versions và rewrap cho phép vừa giới hạn new-use, vừa đáp ứng retention. Không có thời lượng ví dụ nào ở đây là “khuyến nghị chuẩn 90/180 ngày” cho mọi tổ chức.

## 11. Envelope encryption: cryptoperiod ở hai tầng khóa

Trong **envelope encryption**, DEK mã hóa dữ liệu, KEK wrap DEK. Vì có **hai tầng**, phải quản trị **hai cryptoperiod và các phụ thuộc riêng**.

~~~mermaid
sequenceDiagram
    participant Data as Data service
    participant Policy as Policy/IAM
    participant KMS as KMS/HSM giữ KEK
    participant Store as Database
    Data->>Policy: Check tenant/purpose + DEK/KEK new-use policy
    Policy-->>Data: Allow encrypt + active KEK version
    Data->>Data: Generate DEK + AEAD Encrypt, unique nonce
    Data->>KMS: Wrap DEK bằng KEK v5
    KMS-->>Data: Wrapped DEK + provider key ref
    Data->>Store: Ciphertext/tag/nonce + wrapped DEK + KEK version
    Note over Data,Store: DEK mới có thể ngừng encrypt ngay sau 1 object
    Data->>Policy: Sau này check read authz + old-use policy
    Policy-->>Data: Allow decrypt old data
    Data->>KMS: Unwrap đúng KEK version của record
    KMS-->>Data: DEK hoặc protected operation theo API
    Data->>Data: AEAD Decrypt + verify tag/AAD
~~~

### 11.1. DEK cryptoperiod theo scope

Một **DEK per-object** có thể được tạo và dùng encrypt đúng một đối tượng, sau đó không cần được phép encrypt mới nữa; **recipient/decrypt period** phụ thuộc retention của đối tượng. Một **DEK per-tenant** dùng chung nhiều bản ghi thường cần giới hạn thời gian, operation count, lượng dữ liệu và nonce strategy chặt hơn.

### 11.2. KEK cryptoperiod theo wrapping

KEK `v4` có thể hết hạn **wrap DEK mới** nhưng cần **unwrap DEK cũ** cho migration. Trong nhiều KMS, key state `Disabled` có thể chặn **cả wrap lẫn unwrap**, vì vậy không dùng `Disable` như cách mô phỏng “decrypt-only” nếu provider không hỗ trợ. Thay vào đó có thể điều khiển **operation-level policy và primary version**, kết hợp trạng thái thật của provider.

### 11.3. Rewrap khác re-encrypt

~~~text
REWRAP (KEK rotation, DEK vẫn được tin cậy)
  ciphertext = AEAD_Encrypt(DEK_old, data)   // giữ nguyên
  wrappedDEK = Wrap(KEK_new, DEK_old)        // đổi lớp KEK

RE-ENCRYPT (DEK rotation hoặc compromised DEK)
  DEK_new <- CSPRNG/KMS
  ciphertextNew = AEAD_Encrypt(DEK_new, data, nonceNew)
  wrappedDEKNew = Wrap(KEK_new, DEK_new)
~~~

**Rewrap không làm DEK cũ mạnh hơn**. Nếu DEK bị lộ hoặc entropy yếu, thay KEK và rewrap chưa xử lý nguy cơ đó.

## 12. Cryptoperiod và chữ ký số, chứng thư, PKI

Đối với **private signing key**, originator period là khoảng được phép tạo **chữ ký mới**. Sau khi khóa ngừng ký, **public verification key** có thể tiếp tục được dùng để xác minh chữ ký lịch sử theo trust policy.

### 12.1. Phân biệt các mốc của PKI

| Mốc | Ý nghĩa |
| --- | --- |
| `keyGeneratedAt` | Private/public key pair được sinh |
| `signingActivationAt` | Bắt đầu cho phép `Sign` mới theo signing service policy |
| `certificate.notBefore` | Chứng thư bắt đầu hiệu lực theo X.509 |
| `certificate.notAfter` | Chứng thư hết thời hạn hiệu lực |
| `signingNewUseUntil` | Private key ngừng ký mới |
| `certificateRevokedAt` | Chứng thư bị thu hồi theo CA mechanism |
| `trustedTimestampAt` | Bằng chứng thời gian được gắn với chữ ký trong scheme phù hợp |
| `verificationTime` | Thời điểm bên nhận kiểm tra chữ ký/trust chain |

**`certificate.notAfter` không đồng nghĩa khóa riêng bị hủy**; nó cũng không tự giải quyết việc **xác minh chữ ký được tạo trước thời hạn**, đặc biệt khi certificate đã hết hạn tại thời điểm kiểm tra.

### 12.2. Một chữ ký verify đúng chưa chứng minh được ký đúng hạn

`Signature.verify() == true` chỉ cho biết **chữ ký toán học phù hợp với public key và dữ liệu** trong scheme được dùng. Nó **không tự chứng minh** chữ ký được tạo lúc nào, signer có được ủy quyền hay chứng thư không bị revoke. Với chữ ký cần bảo vệ lịch sử dài hạn, xem xét **trusted timestamp, validation data, certificate chain, CRL/OCSP, key usage, archival validation và chính sách pháp lý**.

### 12.3. HMAC và token phiên bản cũ

Một HMAC key được phép tạo token mới đến `newUseUntil`, sau đó có thể còn được dùng **verify các token cũ** đến khi token TTL cuối cùng hết. Nếu dùng một key cho JWT HS256 hoặc API token HMAC:

- Token phải có **key ID/version** hoặc cách định tuyến đáng tin.
- Signer không được ký token mới bằng version retired.
- Verifier chỉ chấp nhận version cũ trong **recipient period, token exp, issuer/audience và revocation policy**.
- Nếu key bị compromise, không tiếp tục verify như bình thường chỉ vì token TTL chưa hết.

**JWT token expiry không phải cryptoperiod của signing key.** Hai mốc phải được kiểm tra độc lập.

## 13. Cryptoperiod của session, TLS và key agreement

Khóa dùng trong giao thức phiên có **thời gian sống và usage limits khác** khóa lưu trữ lâu dài.

### 13.1. Session traffic key

Trong TLS 1.3, traffic secrets/keys được dẫn xuất theo **key schedule chuẩn**; thay đổi keying material có thể xảy ra khi handshake/new connection hoặc cơ chế key update. Các giới hạn của AEAD, nonce/sequence và giao thức có thể yêu cầu **key update/rekey trước khi hết thời gian phiên**.

Không tự chọn “mỗi 90 ngày thay TLS traffic key” cho một phiên dài mà bỏ qua **record/sequence limits**. Dùng TLS stack được duy trì và policy kiểm soát phiên/algorithm phù hợp.

### 13.2. Ephemeral ECDHE/X25519 keys

Một private key ephemeral có thể chỉ được dùng trong một lần handshake hoặc phạm vi giao thức rất hẹp. Nó có thể **không được lưu dài hạn trong central key inventory** từng phiên; tổ chức có thể ghi protocol/provider profile, session policy và audit cần thiết mà không log raw session key.

### 13.3. Key agreement không tự xác thực peer

Nếu ECDH public key không được xác thực, MITM vẫn có thể tấn công dù key agreement key sống rất ngắn. Cryptoperiod phải đi cùng **peer authentication, transcript binding, KDF/key separation và key usage**.

### 13.4. PSK và khóa thiết bị

Một PSK lưu trên thiết bị IoT có thể sống nhiều tháng/năm vì logistics thay thế, nhưng **không thể lấy độ khó rotate làm lý do mặc định sử dụng mãi mãi**. Cần xác định per-device scope, rekey protocol, firmware/attestation, expiry, offboarding và kế hoạch sự cố. Một PSK chung cho hàng nghìn thiết bị khiến revocation và incident blast radius lớn hơn nhiều.

## 14. Khi key material được tạo, cấp phát, lưu và sử dụng ở nhiều nơi

**Cryptoperiod thuộc về material/version và operation/policy cụ thể**, không đơn thuần thuộc tên alias hoặc vị trí file.

### 14.1. Nguồn sinh và thời điểm tạo

Một khóa được sinh trong HSM ngày 01/12, import sang KMS khác ngày 03/12, active ngày 05/12. Các mốc **generatedAt, importedAt, activationAt** phải được phân biệt. Không ghi `importedAt` là “thời điểm sinh ở KMS đích” nếu vật liệu đã tồn tại ở nguồn trước đó.

### 14.2. Phân phối và recipient

Một recipient có thể được cấp wrapped DEK hoặc KMS grant trong khoảng được phép. **Recipient authorization expiry** có thể ngắn hơn hoặc độc lập với key cryptoperiod. Sau offboarding, việc key còn active không có nghĩa recipient còn quyền.

**Revocation của grant/certificate không xóa raw DEK mà recipient đã nhận**, cũng không xóa ciphertext đã sao chép. Khi cần ngăn truy cập tương lai, xét DEK mới/re-encrypt và quyền dữ liệu.

### 14.3. Bộ nhớ, cache và snapshot

Key material có thể tồn tại trong RAM ứng dụng ngay cả sau khi key state đổi sang retired. Có cache, các window drift và vùng nhớ provider/native library. Chính sách cần TTL/caching scope, zeroization best-effort, security logs và kế hoạch invalidation. **Không coi `state=RETIRED` trong database là đã xóa mọi bản sao secret**.

### 14.4. Ranh giới HSM/KMS

Nếu KEK được tạo và giữ trong HSM dưới thuộc tính non-extractable, tổ chức vẫn phải theo dõi **quyền gọi `Wrap/Unwrap`**, pin/session principal, operator approval và key usage. Với HSM/managed KMS, cần xác minh **provider operation được hỗ trợ** trước khi tuyên bố có khả năng “wrap mới cấm, unwrap cũ vẫn được”.

## 15. Thiết kế chính sách cryptoperiod có thể thực thi

Một tài liệu chính sách ghi “KEK rotate 90 ngày” sẽ chưa đủ nếu không chỉ rõ **mốc bắt đầu, hành động bị chặn, điều kiện ngoại lệ, người chịu trách nhiệm và đường thực thi**.

### 15.1. Một policy tối thiểu

| Thuộc tính | Ví dụ | Lý do |
| --- | --- | --- |
| `keyId`, `version` | `billing-kek/v4` | Áp đúng vật liệu thay vì alias |
| `keyClass` | `KEK` | Phân biệt KEK/DEK/signing/HMAC |
| `owner` | `payments-security` | Trách nhiệm quyết định/rotation |
| `tenantScope` | `production/tenant-42` | Tránh dùng xuyên tenant |
| `algorithm/profile` | `AES-256-KW` | Scheme và strength được duyệt |
| `generatedAt` | `2026-12-01T00:00:00Z` | Provenance |
| `activationAt` | `2026-12-05T00:00:00Z` | Bắt đầu được dùng |
| `newUseUntil` | `2027-03-05T00:00:00Z` | Kết thúc `WRAP_NEW` |
| `oldUseUntil` | `2027-09-05T00:00:00Z` | Kết thúc `UNWRAP_OLD` theo kế hoạch |
| `maxNewUseOperations` | Giá trị từ risk/algorithm profile | Chặn quá giới hạn dù chưa hết thời gian |
| `allowedOperations` | `WRAP_NEW`, `UNWRAP_OLD` | Key usage separation |
| `lifecycleState` | `ACTIVE` / `RETIRED` / ... | Chặn thao tác theo trạng thái |
| `policyRevision` | `42` | Chống dùng cấu hình stale |
| `providerRef` | KMS key version reference | Liên kết key thực thi và evidence |
| `rotationOwner/planRef` | Quy trình được phê duyệt | Không đến hạn mới tìm người xử lý |
| `dependencySummary` | Wrapped DEK/backups | Preflight trước retire/destroy |

### 15.2. JSON mẫu

~~~json
{
  "keyId": "billing-kek",
  "keyVersion": "v4",
  "keyClass": "KEY_ENCRYPTION_KEY",
  "ownerTeam": "payments-security",
  "tenantScope": "production/tenant-42",
  "algorithm": "AES-256-KW",
  "providerKeyRef": "kms://example/billing-kek/v4",
  "generatedAt": "2026-12-01T00:00:00Z",
  "activationAt": "2026-12-05T00:00:00Z",
  "newUseUntil": "2027-03-05T00:00:00Z",
  "oldUseUntil": "2027-09-05T00:00:00Z",
  "allowedNewOperations": ["WRAP_NEW"],
  "allowedOldOperations": ["UNWRAP_OLD"],
  "lifecycleState": "PRE_ACTIVE",
  "maxNewUseOperations": 1000000,
  "policyRevision": 42,
  "rotationPlanRef": "KEY-ROTATION-2027-014",
  "auditEvidenceRef": "audit-generation-00281"
}
~~~

Đây là **schema minh họa**, không phải định dạng KMS tiêu chuẩn. Key reference `kms://example/...` là placeholder. `maxNewUseOperations` chỉ minh họa một **hạn mức do tổ chức đặt**; không phải giới hạn mật mã phổ quát của AES-KW.

Tại thời điểm bài được soạn (28/11/2026), khóa mẫu còn **PRE_ACTIVE**, vì ngày sinh/kích hoạt đều nằm trong tương lai. Không dùng nhãn `ACTIVE` chỉ vì bản ghi inventory đã được tạo.

### 15.3. Các bất biến của policy

- `activationAt < newUseUntil <= oldUseUntil` trong **mô hình hai giai đoạn** này. Có loại khóa không có recipient period theo cách đó; cần schema phù hợp riêng.
- `keyId/version` và `providerKeyRef` phải cùng trỏ tới một vật liệu thực tế.
- Khi key `COMPROMISED/REVOKED/DESTROYED`, không có thời gian kế hoạch nào tự cho phép `Unwrap`.
- Khi chính sách thay đổi, phải ghi **revision và approval**, không âm thầm sửa lịch sử.
- Quá trình dùng key phải có **authenticated principal, tenant/resource/purpose authorization** ngoài mốc thời gian.
- `createdAt` không được ghi đè bởi `importedAt` hoặc timestamp của inventory.
- `oldUseUntil` không được kéo dài vô hạn chỉ vì “backup để đó” mà không có data owner/retention review.

### 15.4. Tách policy hiện tại và lịch sử

Một policy có thể được sửa sau khi review; không nên sửa `newUseUntil` cũ trong log như thể hạn đó **luôn tồn tại**. Lưu **append-only policy history/event**, người duyệt, lý do và effective time; inventory hiện tại chỉ là view của trạng thái đã được phê duyệt.

## 16. Enforce cryptoperiod ở đâu?

**Policy viết trong wiki không bảo vệ khóa nếu đường thực thi bỏ qua nó.** Cần xác định ranh giới có thể ngăn phép mật mã thực sự.

### 16.1. Ba lớp kiểm soát

~~~mermaid
flowchart LR
    Request[Request: principal + tenant + operation] --> Auth[Application resource authorization]
    Auth --> Policy[Cryptoperiod/usage policy gate]
    Policy --> Broker[Key operation broker]
    Broker --> KMS[KMS/HSM API + IAM + key state]
    Policy --> Audit[Protected audit]
    Broker --> Audit
    KMS --> Audit
    Inventory[Key inventory + policy revision] --> Policy
    Monitor[Alerts on expiry/usage/compromise] --> Inventory
~~~

1. **Application authorization:** caller có quyền với dữ liệu/tenant/resource nào?
2. **Key operation policy gate:** key version được phép cho `Encrypt/Wrap/Sign` hay `Decrypt/Unwrap/Verify` tại thời điểm đó, còn usage budget và state không?
3. **KMS/HSM IAM/provider controls:** principal có quyền operation và key còn usable ở provider không?

**Một trong ba lớp không được thay thế toàn bộ hai lớp còn lại.** KMS có thể không hiểu bản ghi hóa đơn của user; application có thể không biết raw KEK đã bị HSM revoke; registry có thể bị stale nếu client cache.

### 16.2. Provider có thể không có đúng khái niệm originator/recipient period

Một KMS key ở trạng thái `Disabled` có thể từ chối **cả `Encrypt` lẫn `Decrypt`**. Nếu muốn nghỉ tạo ciphertext mới nhưng vẫn giải mã dữ liệu cũ, cần **thiết kế application policy, IAM/grants hoặc separate key versions** theo capability được vendor hỗ trợ. Đừng giả định API có chế độ `UNWRAP_ONLY` khi tài liệu nhà cung cấp không xác nhận.

### 16.3. Ngăn đường bypass

Nếu mọi request đi qua API gateway nhưng một service account khác có quyền gọi KMS trực tiếp, attacker có thể bỏ qua policy gate ứng dụng. Với operation rủi ro cao:

- Chỉ **execution broker/principal được duyệt** có quyền KMS.
- Tách `Wrap`, `Unwrap`, `Sign`, `Delete`, `Export` theo least privilege.
- Áp key policy/grants/conditions ở provider khi hỗ trợ.
- Audit trực tiếp tại KMS/HSM để phát hiện operation không qua broker.
- Hành động thay policy, kéo dài period, export/root key và destroy có **separation of duties/quorum approval** theo risk tier.

## 17. Java 17: kiểm tra cryptoperiod trước khi Wrap/Unwrap

Ví dụ sau tạo một **policy gate tự chứa**, minh họa lý do thời gian không đủ. Đoạn mã **không tự sinh, xuất hoặc unwrap secret**: nó quyết định xem **một yêu cầu dùng KEK version cụ thể** có được phép đi tiếp đến KMS/HSM hay không.

Nó kiểm tra:

- `Clock/Instant` theo UTC, khoảng **nửa mở**.
- Key state `ACTIVE` hoặc `RETIRED` theo operation.
- `WRAP_NEW` bị từ chối tại/qua `newUseUntil`.
- `UNWRAP_OLD` chỉ được phép trong `oldUseUntil` và khi key **không compromised**.
- Tenant, identity/authorization, provider state, operation allowlist và **usage budget**.
- Không cho phép `WRAP_NEW` khi key đã `RETIRED`.

**Cảnh báo triển khai:** cờ `authenticated/authorized` trong mẫu là **kết quả giả lập từ security context đáng tin**, không được lấy nguyên từ request của client. Counter và trạng thái trong ví dụ **không có giao dịch phân tán**, nên production phải dùng enforcement atomically/race-safe tại KMS/broker/DB và audit.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class CryptoperiodPolicyDemo {
    enum Operation { WRAP_NEW, UNWRAP_OLD }
    enum State {
        PRE_ACTIVE, ACTIVE, RETIRED,
        SUSPENDED, COMPROMISED, DESTROYED
    }

    record KeyPolicy(
            String keyId,
            String keyVersion,
            String tenant,
            Instant activationAt,
            Instant newUseUntil,
            Instant oldUseUntil,
            Set<Operation> allowedOperations,
            long maxNewUseOperations,
            long currentNewUseOperations,
            State state,
            int policyRevision,
            boolean providerEnabled) {
        KeyPolicy {
            if (keyId == null || keyId.isBlank()
                    || keyVersion == null || keyVersion.isBlank()
                    || tenant == null || tenant.isBlank()
                    || activationAt == null
                    || newUseUntil == null || oldUseUntil == null
                    || !activationAt.isBefore(newUseUntil)
                    || oldUseUntil.isBefore(newUseUntil)
                    || allowedOperations == null
                    || allowedOperations.isEmpty()
                    || maxNewUseOperations <= 0
                    || currentNewUseOperations < 0
                    || policyRevision <= 0
                    || state == null) {
                throw new IllegalArgumentException("Invalid key policy");
            }
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    // Giá trị authenticated/authorized phải đến từ auth service,
    // không phải field người dùng tự khai.
    record UseRequest(
            String requestedKeyId,
            String requestedKeyVersion,
            String tenant,
            Operation operation,
            boolean authenticated,
            boolean authorized) {}

    record Decision(boolean allowed, String reasonCode) {
        static Decision allow() {
            return new Decision(true, "ALLOW");
        }
        static Decision deny(String code) {
            return new Decision(false, code);
        }
    }

    static Decision evaluate(
            KeyPolicy key, UseRequest request, Instant now) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(request);
        Objects.requireNonNull(now);
        if (!request.authenticated() || !request.authorized()) {
            return Decision.deny("IDENTITY_OR_PERMISSION");
        }
        if (!key.keyId().equals(request.requestedKeyId())
                || !key.keyVersion().equals(request.requestedKeyVersion())
                || !key.tenant().equals(request.tenant())) {
            return Decision.deny("KEY_OR_TENANT_MISMATCH");
        }
        if (request.operation() == null
                || !key.allowedOperations().contains(request.operation())) {
            return Decision.deny("OPERATION_NOT_PERMITTED");
        }
        if (!key.providerEnabled()) {
            return Decision.deny("PROVIDER_DISABLED");
        }
        if (key.state() == State.SUSPENDED
                || key.state() == State.COMPROMISED
                || key.state() == State.DESTROYED
                || key.state() == State.PRE_ACTIVE) {
            return Decision.deny("KEY_STATE_DENIED");
        }
        if (now.isBefore(key.activationAt())) {
            return Decision.deny("NOT_YET_ACTIVE");
        }

        if (request.operation() == Operation.WRAP_NEW) {
            if (key.state() != State.ACTIVE) {
                return Decision.deny("NOT_ACTIVE_FOR_NEW_USE");
            }
            if (!now.isBefore(key.newUseUntil())) {
                return Decision.deny("NEW_USE_PERIOD_ENDED");
            }
            if (key.currentNewUseOperations()
                    >= key.maxNewUseOperations()) {
                return Decision.deny("USAGE_BUDGET_EXHAUSTED");
            }
            return Decision.allow();
        }

        // UNWRAP_OLD: ACTIVE hoặc RETIRED đều có thể theo policy.
        if (!now.isBefore(key.oldUseUntil())) {
            return Decision.deny("OLD_USE_PERIOD_ENDED");
        }
        return Decision.allow();
    }

    static void requireAllowed(
            KeyPolicy key, UseRequest req, Clock clock) {
        Decision decision = evaluate(key, req, clock.instant());
        if (!decision.allowed()) {
            // Nội bộ có thể audit reasonCode; bên ngoài trả lỗi tối thiểu.
            throw new SecurityException(
                    "Cryptoperiod/key policy denied: "
                    + decision.reasonCode());
        }
        // Ở hệ thống thật: kiểm tra IAM/provider/key state gần thao tác;
        // chỉ sau đó broker mới gọi KMS/HSM đúng key version.
    }

    static void expectAllowed(
            KeyPolicy key, UseRequest request, String utcInstant,
            boolean expected) {
        boolean actual = evaluate(
                key, request, Instant.parse(utcInstant)).allowed();
        if (actual != expected) {
            throw new AssertionError(
                    "Expected allowed=" + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        KeyPolicy active = new KeyPolicy(
                "billing-kek", "v4", "tenant-42",
                Instant.parse("2026-12-05T00:00:00Z"),
                Instant.parse("2027-03-05T00:00:00Z"),
                Instant.parse("2027-09-05T00:00:00Z"),
                Set.of(Operation.WRAP_NEW, Operation.UNWRAP_OLD),
                1000L, 10L, State.ACTIVE, 42, true);

        UseRequest wrap = new UseRequest(
                "billing-kek", "v4", "tenant-42",
                Operation.WRAP_NEW, true, true);
        UseRequest unwrap = new UseRequest(
                "billing-kek", "v4", "tenant-42",
                Operation.UNWRAP_OLD, true, true);

        expectAllowed(active, wrap, "2026-12-04T23:59:59Z", false);
        expectAllowed(active, wrap, "2026-12-05T00:00:00Z", true);
        expectAllowed(active, wrap, "2027-03-04T23:59:59Z", true);
        expectAllowed(active, wrap, "2027-03-05T00:00:00Z", false);
        expectAllowed(active, unwrap, "2027-03-05T00:00:00Z", true);
        expectAllowed(active, unwrap, "2027-09-05T00:00:00Z", false);

        KeyPolicy retired = new KeyPolicy(
                active.keyId(), active.keyVersion(), active.tenant(),
                active.activationAt(), active.newUseUntil(),
                active.oldUseUntil(), active.allowedOperations(),
                active.maxNewUseOperations(),
                active.currentNewUseOperations(),
                State.RETIRED, active.policyRevision(), true);
        expectAllowed(retired, wrap, "2027-03-06T00:00:00Z", false);
        expectAllowed(retired, unwrap, "2027-03-06T00:00:00Z", true);

        KeyPolicy compromised = new KeyPolicy(
                active.keyId(), active.keyVersion(), active.tenant(),
                active.activationAt(), active.newUseUntil(),
                active.oldUseUntil(), active.allowedOperations(),
                active.maxNewUseOperations(),
                active.currentNewUseOperations(),
                State.COMPROMISED, active.policyRevision(), true);
        expectAllowed(
                compromised, unwrap, "2027-03-06T00:00:00Z", false);

        UseRequest wrongTenant = new UseRequest(
                "billing-kek", "v4", "tenant-99",
                Operation.UNWRAP_OLD, true, true);
        expectAllowed(active, wrongTenant, "2027-01-10T00:00:00Z", false);

        // Clock injection hỗ trợ test tại đúng mốc boundary.
        Clock boundaryClock = Clock.fixed(
                Instant.parse("2027-03-05T00:00:00Z"),
                java.time.ZoneOffset.UTC);
        try {
            requireAllowed(active, wrap, boundaryClock);
            throw new AssertionError("Boundary wrap was accepted");
        } catch (SecurityException expected) {
            // PASS: policy từ chối wrap tại đúng newUseUntil.
        }

        System.out.println("Cryptoperiod policy demo: PASS");
    }
}
~~~

### 17.1. Cách chạy và đọc kết quả

Đặt phần Java vào file `CryptoperiodPolicyDemo.java` trong môi trường học tập Java 17 và biên dịch/chạy như một class độc lập. Không cần cài KMS/HSM vì **code chỉ đánh giá metadata/quyết định**, không truy cập raw key.

Khi chạy, các kiểm tra mong đợi đều đạt và in:

~~~text
Cryptoperiod policy demo: PASS
~~~

### 17.2. Giới hạn quan trọng của demo

1. **Không là hệ thống authorization production.** Boolean `authorized` phải do **IAM/resource policy** cấp và xác thực; không bao giờ do client tự gửi.
2. **Không atomic usage accounting.** Hai worker có thể cùng thấy `current=999` và đều cho phép wrap nếu counter chỉ đọc từ cache. Production cần **reserve/increment atomically**, giới hạn ở provider/broker khi có thể và reconciliation.
3. **Provider state có thể đổi giữa check và use.** Cần kiểm tra tại nơi thực thi và chặn bypass trực tiếp tới KMS.
4. **Reason code nội bộ có thể nhạy cảm**. Không làm lộ tồn tại/không tồn tại của key version hay tenant cho caller không được ủy quyền.
5. **Không mô hình hóa mọi key class.** VERIFY với public key, TLS traffic key và HMAC có semantics khác. Cần policy riêng, không ép mọi khóa vào hai thao tác `WRAP/UNWRAP`.
6. **Không xử lý distributed clock uncertainty** ngoài dùng `Instant` và `Clock`. Cần time synchronization và kiểm tra clock drift.
7. **Không sửa key state thật trong KMS/HSM**; policy gate là lớp ứng dụng, cần IAM/HSM enforcement bổ sung.

### 17.3. Các ca kiểm thử cần bổ sung khi triển khai

Ngoài boundary:

- Token/key ID đúng nhưng **key version khác**.
- Principal chưa xác thực hoặc đã revoke IAM.
- Operation `EXPORT` hoặc `DELETE` bị cấm.
- Provider disabled dù registry báo ACTIVE.
- Current usage bằng max usage.
- Key status `SUSPENDED`, `COMPROMISED`, `DESTROYED`.
- Chính sách stale revision hoặc key generation/import chưa được duyệt.
- Retry/timeouts khi operation vừa được xử lý ở provider.
- Clock skew giữa gateway, worker và KMS audit.

## 18. Đồng hồ, UTC và ranh giới thời gian trong hệ phân tán

Cryptoperiod chỉ có ý nghĩa nếu hệ thống hiểu **chính xác thời điểm nào được tính là hợp lệ**.

### 18.1. Dùng `Instant`/UTC

Ghi các mốc theo ISO 8601 UTC:

~~~text
activationAt  = 2026-12-05T00:00:00Z
newUseUntil   = 2027-03-05T00:00:00Z
oldUseUntil   = 2027-09-05T00:00:00Z
~~~

Không dùng `2027-03-05 07:00` mà không ghi timezone trong hệ thống nhiều vùng. Java `LocalDateTime` không mang offset/timezone; `Instant` phù hợp hơn để so sánh thời điểm tuyệt đối.

### 18.2. Clock skew và timestamp source

Hai node có thể khác nhau vài mili-giây hoặc vài giây. Nếu đúng biên `newUseUntil`, một node cho phép còn node khác từ chối, dẫn tới **enforcement không nhất quán**. Cần time synchronization, drift alerts và quyết định rõ **trusted clock source ở enforcement point**. Không dựa vào timestamp do caller có thể tự gửi.

### 18.3. Đo khoảng thời gian khác xác định deadline

Monotonic clock thích hợp để đo **elapsed duration trong cùng tiến trình**; nó không đại diện cho lịch UTC trên nhiều máy. Có thể dùng monotonic time trong timeout/retry, nhưng **deadline cryptoperiod** phải dựa trên nguồn thời gian được xác thực/quản trị thích hợp.

### 18.4. Không dùng grace period tùy tiện

Một số hệ thống cần buffer để xử lý clock drift hoặc rollout, nhưng **không tự cộng 5 phút sau `newUseUntil` để tiếp tục ký/wrap**. Nếu cần grace period, phải được định nghĩa rõ trong policy, phê duyệt theo risk tier và thực thi nhất quán; với key compromise thì không áp grace theo lịch.

## 19. Automation và kế hoạch rotation trước khi hết hạn

Một thiết kế chỉ cảnh báo **đúng ngày hết cryptoperiod** thường quá muộn, vì còn phải tạo successor, cấp IAM, phân phối public key, migrate dữ liệu và test restore.

### 19.1. Các mốc chuẩn bị

~~~mermaid
flowchart LR
    Discover[Inventory keys + owners + deadlines] --> Plan[Plan rotation + dependency scan]
    Plan --> Generate[Generate successor + provenance]
    Generate --> Validate[Pre-active tests, provider/IAM, backups]
    Validate --> Activate[Cutover primary for new use]
    Activate --> Migrate[Rewrap / re-encrypt + audit]
    Migrate --> Restore[Restore/verification rehearsal]
    Restore --> Retire[Retire old key; deny new use]
    Retire --> Destroy[Destroy when dependencies permit]
~~~

Một workflow thực tế cần owner, approval, migration window, rollback plan, canary và liên kết audit. Hạn triển khai successor nên được tính **trước `newUseUntil` đủ lâu để hoàn thành bước bắt buộc**; không có một khoảng “trước 7 ngày” phù hợp cho mọi key class.

### 19.2. Event-driven rotation

Ngoài lịch định kỳ, có thể kích hoạt rotate sớm khi:

- Usage/nonce threshold đã đạt.
- HSM/KMS key rotation policy hoặc crypto profile thay đổi.
- Provider/firmware có cảnh báo liên quan đến sinh khóa.
- Owner/tenant boundary thay, recipient bị offboard.
- Anomaly và compromise được xác nhận.

### 19.3. Idempotency và rollback

Rotation job có thể bị retry sau timeout. Cần:

- `rotationOperationId` và exact old/new key refs.
- Key creation API idempotency khi provider hỗ trợ; nếu không, reconcile key objects trước retry.
- **CAS/transaction** khi cập nhật `primaryForNewUse`, wrapped DEK và metadata version.
- Canary decrypt/verify mới và cũ.
- Kế hoạch rollback không quay lại **key đã revoked/compromised**.

## 20. Key inventory và audit cho cryptoperiod

Quản trị cryptoperiod đòi hỏi một inventory đủ để trả lời: **version nào được phép làm gì vào thời điểm nào, đã dùng bao nhiêu, ai là owner và data nào còn phụ thuộc**.

### 20.1. Trường inventory quan trọng

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Key identity | `keyId`, `version`, `keyClass` | Chính xác material |
| Source | `generationMethod`, `providerKeyRef`, `generatedAt` | Provenance và security boundary |
| Purpose | `algorithm`, `allowedOperations`, `tenantScope` | Scope mật mã |
| Time | `activationAt`, `newUseUntil`, `oldUseUntil` | Usage periods |
| State | `PRE_ACTIVE/ACTIVE/RETIRED/REVOKED/DESTROYED` | Enforce lifecycle |
| Usage | `wrapCount`, `encryptCount`, `lastUsedAt` | Limits và anomaly |
| Governance | `ownerTeam`, `policyRevision`, `approvalRef` | Trách nhiệm/kiểm soát |
| Dependencies | `wrappedDekCount`, `backupRefs`, `consumers` | Rewrap/restore/destruction |
| Evidence | `providerAuditRef`, `rotationPlanRef` | Kiểm toán |

### 20.2. Event audit mẫu

~~~json
{
  "eventType": "KEY_OPERATION_DENIED",
  "keyId": "billing-kek",
  "keyVersion": "v4",
  "operation": "WRAP_NEW",
  "principal": "billing-data-service",
  "tenantScope": "production/tenant-42",
  "policyRevision": 42,
  "reasonCode": "NEW_USE_PERIOD_ENDED",
  "evaluatedAt": "2027-03-05T00:00:00Z",
  "keyState": "RETIRED",
  "providerRef": "kms://example/billing-kek/v4",
  "operationId": "wrap-request-00281",
  "auditSequence": 18372
}
~~~

**Đây là ví dụ**, không phải log chuẩn của nhà cung cấp. Log thực tế không được tự khẳng định provider đã từ chối thao tác nếu chỉ có lớp application từ chối; tách `APPLICATION_POLICY_DENIED` và `PROVIDER_DENIED` theo nguồn evidence.

### 20.3. Không ghi key material vào log

Audit chỉ cần **key reference/version, principal, operation, scope, timestamp, policy revision, outcome**. **Không log raw DEK, KEK, private key, seed, HMAC key, PSK, bearer token hoặc plaintext**. Ngay cả metadata tenant/key path có thể nhạy cảm và cần access control.

### 20.4. Integrity của lịch sử

Nếu kẻ tấn công sửa được `newUseUntil` và audit, họ có thể hợp thức hóa việc dùng khóa cũ. Cần **append-only hoặc tamper-evident audit**, phân quyền sửa policy/timestamp, độc lập provider logs và kiểm tra revision. Một digest SHA-256 lưu cùng event **không tự làm log bất biến** nếu attacker sửa được cả hai.

## 21. Những metric và cảnh báo nên theo dõi

| Metric / cảnh báo | Ý nghĩa |
| --- | --- |
| `keysWithoutOwner` | Không rõ ai chịu trách nhiệm rotation |
| `keysMissingCryptoperiod` | Không có thời hạn/hard limits rõ |
| `newUseDeadlineSoon` | Sắp hết thời gian encrypt/wrap/sign mới |
| `successorNotReady` | Key mới chưa provision/IAM/activate |
| `newUseAfterDeadline` | Bằng chứng vi phạm chính sách |
| `oldUseAfterDeadline` | Operation cũ vượt period |
| `revokedKeyUsed` | Có bypass hoặc policy stale |
| `usageThresholdNear` | Sắp vượt operation/nonce/keying limits |
| `unexpectedProviderKeyState` | Inventory và KMS/HSM không nhất quán |
| `oldKeyCiphertextDependencies` | Còn nhiều record/DEK/backup dùng key cũ |
| `rewrapOrReencryptBacklog` | Migration chậm hoặc thất bại |
| `restoreFailureWithOldKey` | Backup không đọc được sau rotation |
| `rotationApprovalOverdue` | Quorum/owner chưa duyệt kịp |
| `cryptoperiodPolicyDrift` | Sai revision/clock/IAM giữa node |

### 21.1. Tại sao cảnh báo “còn 3 ngày” chưa đủ?

Một root CA key hoặc KEK bảo vệ hàng tỷ DEK có thể cần **nhiều bước chuẩn bị/kiểm thử**; một DEK per-object có thể rotate gần như tức thì. Alert lead time phải dựa trên **migration time, impact, failure budget và tổ chức vận hành**, không cứng nhắc cho mọi loại key.

### 21.2. Dữ liệu từ đâu?

Ứng dụng có thể ghi `policyGateDecision`, KMS/HSM ghi actual operation, inventory lưu key state, database lưu key version của ciphertext. Đối chiếu các nguồn này thay vì tin tuyệt đối vào một counter tự tăng trong app.

## 22. Khi cryptoperiod bị vượt quá hoặc key bị compromise

Một key có thể bị dùng ngoài cryptoperiod do **đường bypass, deployment stale, clock lỗi, admin grant rộng hoặc thao tác thủ công**. Phân loại sự cố trước khi hành động.

### 22.1. Trường hợp dùng sau `newUseUntil`

1. **Chặn new-use** tại broker và provider theo khả năng.
2. Xác định **key ID/version, operation, thời gian, principal, số bản mã/tài liệu** được tạo trái policy.
3. Kiểm tra **clock skew**, policy revision, bypass IAM và lỗi state transition.
4. Sinh/activate successor nếu chưa có, không chuyển ngầm sang thuật toán hoặc key yếu.
5. Đánh giá cần rewrap/re-encrypt hay tạo chữ ký lại những đối tượng đã được tạo sai hạn hay không.
6. Khắc phục rule, kiểm thử boundary và audit độc lập.

Vi phạm period **không tự đồng nghĩa plaintext bị lộ**; mức độ sự cố phụ thuộc nguyên nhân, mật mã, lượng use và threat model.

### 22.2. Trường hợp raw KEK bị lộ

Nếu attacker có KEK cũ và các wrapped DEK cũ, họ vẫn có thể unwrap ngoại tuyến ngay cả sau khi hệ thống **rewrap bản hiện tại**. Đánh giá **DEK bị ảnh hưởng, ciphertext và backup đã bị sao chép, data access**, thay DEK/re-encrypt khi risk yêu cầu. **Rotation không xóa byte đối thủ đã thu thập**.

### 22.3. Trường hợp private signing key bị lộ

Không chỉ ngừng ký mới. Cần **revoke/replace trust**, xác định những chữ ký nào có thể đã bị giả mạo, kiểm tra PKI/certificate status, trusted timestamps và thông báo các verifier/recipient liên quan.

### 22.4. Trường hợp KMS API credential bị chiếm

Private/secret key có thể vẫn non-extractable, nhưng attacker có thể gọi **`Decrypt/Unwrap/Sign`** dưới quyền hợp lệ. Revoke principal/grants/session, đối chiếu provider audit, xác định DEK/plaintext/chữ ký đã được trả ra và đánh giá thay key/data theo phạm vi thực tế.

### 22.5. Không xóa key sớm để che lỗi

Hủy key cũ ngay khi phát hiện dùng sai hạn có thể làm mất chứng cứ hoặc mất dữ liệu còn cần. Containment nên **ngừng operation, cô lập principal, giữ audit**, sau đó quyết định xử lý phụ thuộc và hủy theo runbook/approval.

## 23. Backup, disaster recovery và cryptographic erasure

**Cryptoperiod policy** và **retention/DR policy** phải được thiết kế cùng nhau.

### 23.1. Restore test là điều kiện trước destruction

Khi hủy KEK cũ, cần kiểm tra:

- Database/backup/snapshot còn **wrapped DEK** dưới key version đó không?
- KMS/HSM key object có được replicate/import/restore vào DR region theo cơ chế được hỗ trợ không?
- Key attributes/permissions có giống môi trường chính không?
- Chứng thư/private signing key hoặc root key có bản sao archive hợp lệ không?
- `Decrypt/Unwrap/Verify` với dữ liệu cũ có được kiểm thử theo policy không?
- Có legal hold và thời hạn lưu chứng cứ cần giữ không?

**Một restore rehearsal thất bại là tín hiệu dừng destruction**, không phải lý do tự export raw KEK ra file.

### 23.2. Đừng nhầm availability với lifetime

Một key có thể đã `RETIRED` nhưng cần tồn tại trong backup/restore boundary; nó không nhất thiết phải **online cho mọi workload**. Tùy provider, có thể dùng archive/recovery controls, tách role và hạn chế operation để giảm exposure.

### 23.3. Crypto-erasure

**Cryptographic erasure** là làm mất khả năng giải mã dữ liệu bằng cách hủy key material cần thiết, với điều kiện **không còn bản sao key/DEK/plaintext có thể khôi phục**. Hủy một KEK trong KMS không chứng minh erasure nếu raw DEK đã nằm trong backup, RAM dump, export hoặc attacker giữ bản sao.

**Hủy key là hành động có thể không đảo ngược.** Cần dependency inventory, data owner approval, key custodian, audit evidence và **quorum approval** theo risk tier khi có tác động rộng.

## 24. Case study: quản lý cryptoperiod cho hệ thống hóa đơn đa tenant

Giả sử một SaaS cung cấp dịch vụ hóa đơn cho **300 tenant**. Dữ liệu nhạy cảm được mã hóa bằng DEK riêng theo đối tượng và bọc bởi **KEK theo tenant** trong managed KMS. Hệ thống cần đáp ứng retention dài, có DR/backup ở nhiều vùng và giảm tác động khi một workload bị chiếm.

### Giai đoạn A — Khảo sát trạng thái ban đầu

Nhóm bảo mật phát hiện:

- Logical key `invoices-kek` có nhiều aliases nhưng inventory không giữ **exact key version**.
- Ứng dụng gọi `GenerateDataKey` từ một KEK đã tồn tại hơn hai năm.
- Không có owner rõ cho kế hoạch rotation, dù dữ liệu mới liên tục được mã hóa.
- Backup có wrapped DEK cũ nhưng không có **restore rehearsal** gần đây.
- Policy ứng dụng chỉ kiểm tra `isEnabled`, không kiểm tra `newUseUntil`.
- KMS IAM cấp quyền `Decrypt` quá rộng cho một service dùng chung.

Mặc dù tất cả key nằm trong KMS, hệ thống vẫn thiếu **cryptoperiod enforcement** và **dependency mapping**.

### Giai đoạn B — Đặt policy theo key class và tenant

Key owner và Data owner định nghĩa:

- **DEK per-object:** dùng encrypt một payload; lưu wrapped DEK, version, nonce/AAD và ciphertext. Không reuse DEK để mã hóa tài liệu mới ngoài scope.
- **KEK per-tenant:** có thời điểm bắt đầu `WRAP_NEW`, kết thúc `WRAP_NEW`, giai đoạn `UNWRAP_OLD` cho migration và backup, kèm usage threshold.
- **Signing key** (nếu có): có originator sign period, public verification trust và certificate lifecycle riêng.
- **KMS principal:** chỉ những workload đã được ủy quyền mới có quyền `Wrap/Unwrap` cho đúng tenant/purpose.
- **Audit:** mỗi operation ghi exact key ID/version, principal, tenant và policy revision; không ghi raw key.

Các mốc thời gian do **risk model và migration constraints** quyết định, không sao chép một con số “90 ngày” từ hệ thống khác.

### Giai đoạn C — Chuẩn bị successor

Nhóm vận hành sinh KEK `tenant-A/v5` trong KMS/HSM boundary được duyệt; xác minh algorithm, entropy/provenance, export policy, IAM, key state, audit và backup path. Key mới được gắn trạng thái **PRE_ACTIVE**, chưa nhận dữ liệu production.

Tại thời điểm được phê duyệt, key được kích hoạt cho `WRAP_NEW`, và ứng dụng chuyển **primary key version** theo tenant. Hệ thống không thay đổi key IDs của những record cũ.

### Giai đoạn D — Rewrap có kiểm soát

Worker đọc các DEK còn được bọc bởi `tenant-A/v4` và dùng KMS API phù hợp để rewrap dưới `v5`:

~~~text
Trước:
  Data ciphertext = AEAD_Encrypt(DEK_A, invoice_123)
  Wrapped DEK     = Wrap(KEK_v4, DEK_A)

Sau khi rewrap:
  Data ciphertext = AEAD_Encrypt(DEK_A, invoice_123)  // không đổi
  Wrapped DEK     = Wrap(KEK_v5, DEK_A)
~~~

Job cập nhật **wrapped DEK + KEK version + metadata** trong cùng transaction với **optimistic concurrency guard**; có checkpoint và retry không ghi đè. Khi migration đang chạy, version `v4` được phép **`UNWRAP_OLD`** theo policy nếu không có nghi compromise; `WRAP_NEW` đã bị cấm.

### Giai đoạn E — Kiểm tra backup và DR

Một snapshot cũ vẫn chứa wrapped DEK dưới `v4`. Nhóm **không hủy `v4`** chỉ vì toàn bộ record trên primary DB đã rewrap xong. Họ kiểm tra khả năng restore, data retention, archive migration và quyền truy cập lịch sử; nếu không thể thay backup cũ, phải có quyết định rõ về cách giữ key cũ an toàn hoặc thay retention plan.

### Giai đoạn F — Xử lý sự cố giả định

Một tháng sau, IAM audit phát hiện credential có quyền `Unwrap` tenant A bị lạm dụng. Security:

1. Chặn principal/grants và endpoint liên quan.
2. Xem actual KMS operations thay vì chỉ app logs.
3. Xác định key versions/DEK nào đã được unwrap và dữ liệu tương ứng.
4. Nếu DEK có thể đã bị lộ, tạo DEK mới và **re-encrypt** các đối tượng theo phạm vi cần thiết.
5. Không tuyên bố “rotate KEK là đã khắc phục toàn bộ” nếu attacker có raw DEK hoặc ciphertext cũ.

**Bài học case study:** cryptoperiod là **một chính sách được thực thi trên key/version/operation, gắn với dữ liệu và quyền thực tế**. Một ngày hết hạn đơn lẻ, hoặc một nhãn `rotated=true`, không đủ chứng minh an toàn.

## 25. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Coi cryptoperiod = tuổi khóa từ `createdAt` | Khóa chưa active cũng bị tính use sai | Xác định `activationAt` và policy semantics |
| Chỉ lưu một trường `expiresAt` | Không phân biệt encrypt-new với decrypt-old | Originator/recipient usage theo key class |
| Coi ngày hết hạn là ngày tự xóa key | Có thể không đọc được backup/ciphertext | Dependency preflight và kế hoạch destruction |
| Dùng chung “rotation 90 ngày” cho tất cả keys | Sai nhu cầu/signing/backup/ephemeral | Risk/usage/algorithm-specific periods |
| Cho phép encrypt mới bằng key retired | Tăng số bản mã phụ thuộc key cũ | Chặn `WRAP_NEW/ENCRYPT_NEW` ở enforcement point |
| Coi `Disabled` trong KMS nghĩa là decrypt-only | Restore/unwrapping có thể bị chặn | Xác minh semantics provider trước rollout |
| Chỉ kiểm tra `now < newUseUntil` | Bỏ qua revoked/tenant/operation/state | Combine time, IAM, state, usage budget |
| Dựa vào clock do client gửi | Có thể backdate và vượt policy | Trusted server/KMS time, UTC và drift monitoring |
| Cộng grace period ngầm sau deadline | Vượt cryptoperiod được duyệt | Chính sách ngoại lệ rõ, không tự gia hạn |
| Dùng key quá usage/nonce limit dù chưa hết ngày | Rủi ro mật mã lớn | Usage gates và rotate theo ngưỡng |
| Một nonce bị reuse dưới cùng AES-GCM key | Rủi ro bảo mật nghiêm trọng | Uniqueness strategy, rekey khi gần giới hạn |
| Đổi alias mà không tạo material mới | “Rotation” giả, risk không đổi | Key generation/version mới |
| Ghi key version chỉ trong cache | Không decrypt được record cũ sau cutover | Lưu exact version/provider key ref với ciphertext |
| Chỉ rewrap DEK khi DEK bị lộ | Attacker vẫn giải mã được | DEK mới + re-encrypt khi cần |
| KEK lộ, rewrap nhưng không xét blob cũ attacker đã lấy | Lộ dữ liệu vẫn tiếp diễn | Incident impact/DEK assessment |
| KMS principal có quyền unwrap mọi tenant | Confused deputy, blast radius | IAM/resource auth, tenant isolation |
| HSM non-extractable nên không cần audit | API misuse không bị phát hiện | Audit actual `Sign/Decrypt/Unwrap` |
| Chính sách chỉ nằm trong wiki | Caller bypass, key vẫn bị dùng sai hạn | Gate ở service/broker/provider và negative tests |
| Chỉ có một counter local cho usage limits | Race condition nhiều node | Atomic accounting/provider enforcement |
| Đến hạn mới bắt đầu chuẩn bị successor | Outage hoặc kéo dài trái phép | Alert/rotation plan trước deadline |
| Xóa KEK cũ khi DB chính rewrap 100% | Backup/DR có thể vô dụng | Dependency scan, archive và restore rehearsal |
| Coi `Signature.verify()` chứng minh thời điểm ký | Chấp nhận chữ ký giả hoặc sai niềm tin | Timestamp/certificate/revocation/trust policy |
| Không giữ public key cũ cho verify lịch sử | Không xác minh được giao dịch cũ | Public trust/retention độc lập private key |
| Một `policyRevision` có thể bị sửa không log | Khó xác minh ai kéo dài cryptoperiod | Append-only policy history/quorum |
| Log raw KEK/DEK để điều tra | Tạo thêm sự cố lộ secret | Chỉ log metadata và provider evidence |

## 26. Checklist triển khai cryptoperiod trong production

- [ ] Đã định nghĩa **cryptoperiod** theo key material/version và các operation được phép?
- [ ] Có phân biệt **originator-usage** và **recipient-usage** với semantics phù hợp từng key class?
- [ ] Đã phân biệt **creation/import, activation, new-use end, old-use end, retirement, revocation, destruction**?
- [ ] Không dùng một duration chung không qua threat modeling cho mọi DEK, KEK, signing, HMAC, PSK và session key?
- [ ] Có chọn thời gian theo **risk, data lifetime, algorithm/provider, key exposure, operation volume và policy**?
- [ ] Các usage/nonce/message limits có thể khiến key ngừng dùng **trước expiry calendar**?
- [ ] Với AES-GCM, đã bảo đảm **nonce uniqueness** và xử lý multi-node/VM snapshot/restart?
- [ ] Key inventory giữ **exact key ID/version**, owner, purpose, tenant scope, generation provenance và provider reference?
- [ ] Timestamp theo **UTC/`Instant`**, khoảng nửa mở và clock synchronization đủ tin cậy?
- [ ] Chặn `WRAP_NEW/ENCRYPT_NEW/SIGN_NEW` đúng **tại `newUseUntil`**, không cộng grace tùy tiện?
- [ ] `UNWRAP_OLD/DECRYPT_OLD/VERIFY_OLD` được quản lý **riêng và phù hợp key state/provider/trust policy**?
- [ ] Nếu key `COMPROMISED/REVOKED`, đã ngừng operation theo runbook **bất kể còn thời gian kế hoạch**?
- [ ] Application có **resource authorization**, IAM least privilege và policy gate không bị bypass bởi direct KMS calls?
- [ ] KMS/HSM key state/grants thực tế được đối chiếu, không giả định `Disabled` là decrypt-only?
- [ ] Có logic kiểm soát **operation count/usage budget** atomically cho workload phân tán?
- [ ] Có **rotation plan** và successor được pre-generate/test trước deadline?
- [ ] Cutover primary key version **không làm mất key reference của dữ liệu cũ**?
- [ ] Đã chọn **rewrap KEK** hoặc **DEK mới + re-encrypt** theo tình trạng compromise thực tế?
- [ ] Signing key rotation có xét **PKI/JWKS/public verifier, certificate validity, revocation và timestamp lịch sử**?
- [ ] TLS/session/PSK có **protocol-specific rekey/epoch/record limits** thay vì period áp cứng?
- [ ] Backups, archives, snapshots, wrapped DEK và dữ liệu cần retention đã được inventory trước retire/destroy?
- [ ] Có **restore rehearsal** chứng minh old ciphertext còn đọc được theo policy?
- [ ] Key owner/Data owner/Security/KMS custodian có trách nhiệm và approval/quorum rõ cho root key/destruction?
- [ ] Có **break-glass containment** để revoke khi nguy hiểm, không phụ thuộc quorum hủy vĩnh viễn?
- [ ] Audit chứa `keyId/version`, operation, principal, policy revision, timestamp, outcome nhưng **không raw key/plaintext**?
- [ ] Có metric/alert cho **deadline sắp tới, usage threshold, new-use trái hạn, old dependency backlog và restore failures**?
- [ ] Có negative tests: trước activation, đúng deadline, sau deadline, wrong tenant, revoked state, stale policy, provider disabled?
- [ ] Đã kiểm tra idempotency, CAS, timeout và concurrency khi rotation/re-encrypt?
- [ ] Mọi ngoại lệ kéo dài thời kỳ use phải có **lý do, người duyệt, TTL và audit**, không chỉnh timestamp ngầm?

## 27. Câu hỏi tự kiểm tra

**1. Cryptoperiod là gì?**  
Là khoảng thời gian một key version được phép dùng bởi chủ thể đã được ủy quyền cho các cryptographic operations nhất định. Nó không phải tuổi thọ vật lý của khóa hoặc ngày xóa file.

**2. Originator-usage period khác recipient-usage period thế nào?**  
Originator period cho phép **tạo bảo vệ mới** như encrypt/wrap/sign; recipient period cho phép **xử lý bảo vệ cũ** như decrypt/unwrap/verify, khi key class và trust policy cho phép.

**3. Vì sao khóa hết `newUseUntil` không nên bị xóa ngay?**  
Ciphertext, wrapped DEK, backup và dữ liệu lịch sử có thể vẫn cần unwrap/decrypt. Phải kiểm tra dependencies và migration/retention trước destruction.

**4. Khóa sinh ngày 1/12 nhưng active ngày 5/12 thì cryptoperiod có tự bắt đầu ngày 1/12 không?**  
Không. Phải dựa trên **định nghĩa chính sách** và `activationAt`/các sự kiện được phê duyệt, không mặc định lấy creation time.

**5. Có thể dùng một cryptoperiod 90 ngày cho mọi key không?**  
Không nên. DEK per-object, KEK, root CA key, HMAC token key và ephemeral TLS key có rủi ro, operation/usage và thời hạn xử lý cũ khác nhau.

**6. Tại sao key AES-GCM có thể phải rotate trước deadline?**  
Vì nonce uniqueness, message/byte/operation limits và rủi ro hiện tại có thể buộc ngừng dùng sớm hơn thời gian trên lịch.

**7. `now == newUseUntil` thì có được `WRAP_NEW` không nếu dùng interval nửa mở?**  
Không. Với `activationAt <= now < newUseUntil`, đúng endpoint đã ở ngoài originator period.

**8. KMS key Disabled có luôn được phép Decrypt Old nhưng cấm Encrypt New không?**  
Không. Nhiều provider chặn tất cả operations khi Disabled. Cần kiểm tra capability và áp operation policy phù hợp.

**9. Rotation có phải chỉ đổi alias từ `v4` sang `v5`?**  
Không. Rotation đúng nghĩa phải có **key material/version mới**, lifecycle, cutover, dependency management và audit.

**10. Khi KEK hết hạn wrap mới, có thể dùng nó unwrap các DEK cũ không?**  
Có thể **nếu** còn trong recipient period, không compromised, có quyền và provider hỗ trợ. Không mặc định mọi trạng thái đều cho phép.

**11. Rewrap DEK khi thay KEK có cần mã hóa lại data ciphertext không?**  
Thường không nếu DEK vẫn tin cậy; chỉ lớp wrapped DEK thay. Nhưng nếu DEK bị lộ hoặc phải đổi AAD/algorithm/data key, có thể cần re-encrypt.

**12. Nếu raw KEK và bản wrapped DEK cũ đã bị lấy, chỉ rewrap bản mới đủ chưa?**  
Không. Attacker có thể unwrap bản cũ ngoại tuyến. Cần đánh giá DEK mới/re-encrypt và ảnh hưởng dữ liệu đã bị sao chép.

**13. Tại sao `Signature.verify()==true` chưa đủ chứng minh chữ ký được tạo trong signing period?**  
Phép verify toán học không chứng minh thời điểm/authorization. Có thể cần trusted timestamp, chain, certificate validity và revocation policy.

**14. JWT `exp` có phải cryptoperiod của HMAC signing key không?**  
Không. `exp` thuộc token cụ thể. Signing key có khoảng tạo token mới và khoảng verify cũ riêng, kết hợp issuer/audience/revocation.

**15. Nếu worker kiểm tra counter dưới max rồi gọi KMS, có chắc không vượt usage budget không?**  
Không khi nhiều worker chạy đồng thời. Cần reservation/increment **atomically** hoặc enforcement tại nơi thực thi phù hợp.

**16. Vì sao dùng clock của client cho cryptoperiod nguy hiểm?**  
Client có thể tự backdate/forward-date hoặc bị lệch giờ. Dùng thời gian từ enforcement service/provider đáng tin, đồng bộ clock và audit.

**17. Một KEK còn phục vụ backup có cần luôn online với quyền `Wrap` không?**  
Không nhất thiết. Có thể giữ khả năng recovery/unwrap được kiểm soát theo capability/provider, đồng thời ngăn tạo bảo vệ mới.

**18. Khi khóa bị nghi compromise trước `newUseUntil`, có được tiếp tục dùng đến hết kỳ không?**  
Không. Containment và incident response có thể yêu cầu ngừng ngay; cryptoperiod kế hoạch không vượt quyền đánh giá an ninh.

**19. Có nên hủy key khi rotation job báo rewrap 100% trên primary DB?**  
Chưa đủ. Cần kiểm tra backup/archives/replicas, trạng thái dữ liệu lịch sử và restore rehearsal.

**20. Một cryptoperiod policy tốt phải được đặt ở đâu?**  
Trong governance/inventory **và tại enforcement point** (application/broker/KMS/HSM/IAM phù hợp), có audit, tests và kiểm soát bypass.

## Ghi nhớ

**Cryptoperiod là khoảng được phép sử dụng một khóa mật mã cho những thao tác cụ thể, không đơn thuần là ngày hết hạn của key file.** Hãy tách **originator-usage** (tạo bảo vệ mới) và **recipient-usage** (xử lý bảo vệ cũ) theo đúng key class, đồng thời phân biệt **ngày sinh, activation, rotation, retirement, revocation, certificate validity, backup retention và destruction**. Cryptoperiod phải dựa trên **rủi ro, thuật toán, usage/nonce limits, cách quản lý DEK–KEK, PKI/signing/TLS, KMS/HSM và dữ liệu phụ thuộc** — không áp một thời lượng cho mọi khóa. Trong production, cần có **key inventory/version rõ, policy gate thực thi bằng UTC/clock đáng tin, IAM và tenant authorization, atomic usage controls, successor preparation, rewrap/re-encrypt đúng tình huống, audit, restore tests và incident response**. Nguyên tắc cuối cùng là: **ngừng tạo bảo vệ mới đúng hạn, duy trì xử lý dữ liệu cũ chỉ khi còn được phép và thật sự cần, và không hủy khóa trước khi hiểu hết hậu quả của việc mất nó**.
