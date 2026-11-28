# DEK wrapping — Bọc khóa dữ liệu trong Envelope Encryption

## 1. DEK wrapping là gì?

**DEK wrapping** là quá trình **bảo vệ một Data Encryption Key (DEK)** bằng một khóa hoặc cơ chế bảo vệ khác, thường là **Key Encryption Key (KEK)**. Kết quả là một **wrapped DEK**: dữ liệu biểu diễn DEK đã được bảo vệ và chỉ được phục hồi bằng thao tác **unwrap** hợp lệ. Mục tiêu là **không phải lưu hoặc phân phối DEK dạng rõ một cách lâu dài** trong database, object storage, message hay backup.

Trong **envelope encryption**, có hai lớp bảo vệ:

1. **Lớp dữ liệu:** DEK là khóa đối xứng (chẳng hạn AES-256) để mã hóa và xác thực payload bằng **AES-GCM** hoặc một AEAD được phê duyệt.
2. **Lớp khóa:** KEK nằm dưới quyền kiểm soát của **KMS/HSM** hoặc một cơ chế bảo vệ được duyệt; nó bảo vệ DEK bằng **key wrapping** hoặc một cơ chế mã hóa khóa tương đương có bảo vệ toàn vẹn.

Ví dụ, một hệ thống Java lưu hóa đơn đã mã hóa trong database. Mỗi miền dữ liệu có DEK riêng; application mã hóa hóa đơn bằng DEK, sau đó lưu **ciphertext + nonce/tag + wrapped DEK + key reference**, nhưng không lưu DEK dạng rõ. Khi người dùng được phép đọc, hệ thống gọi KMS để lấy lại DEK theo đúng quyền, rồi giải mã dữ liệu và kiểm tra authentication tag.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này kết nối mật mã đối xứng, bất đối xứng, chữ ký số, **KMS/HSM, phân quyền, kiểm toán** và vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**. DEK wrapping giúp giảm số lượng key material cần giữ trong vùng quản trị nhạy cảm nhất, nhưng **không tự thay thế bảo vệ DEK dạng rõ trong bộ nhớ hoặc kiểm soát quyền truy cập dữ liệu**.

> **Nguyên tắc:** **Mã hóa payload bằng DEK; bọc DEK bằng KEK.** Không nhầm việc đổi KEK với việc đổi DEK; không coi wrapped DEK là một định dạng bí mật không cần metadata, và không xem việc KMS trả “success” là bằng chứng người gọi được phép đọc mọi bản ghi nghiệp vụ.

## 2. Bốn thành phần cơ bản và ranh giới tin cậy

| Thành phần | Vai trò | Yêu cầu bảo vệ |
| --- | --- | --- |
| **DEK** | Trực tiếp mã hóa/giải mã dữ liệu bằng AEAD | Bí mật; giới hạn số lượt sử dụng và thời gian xuất hiện ở dạng rõ |
| **KEK** | Bọc/giải bọc DEK; có thể là khóa đối xứng hoặc khóa private phù hợp | Bí mật và quản trị chặt, thường ở KMS/HSM; không phát tán tùy tiện |
| **Wrapped DEK** | Bản được bảo vệ của DEK | Có thể lưu cạnh ciphertext nhưng cần chống tráo đổi, gắn đúng key/context |
| **Envelope metadata** | Key ID/version, thuật toán, nonce, tag, context, định dạng | Phải bảo đảm tính toàn vẹn và diễn giải không mơ hồ |

Một bản ghi thường có cấu trúc khái niệm:

~~~text
Envelope
  version
  payloadAlgorithm             -> AES-256-GCM
  keyWrapAlgorithm             -> AES-KW / KMS-managed / ...
  keyReference                 -> KEK ID hoặc key version được phép
  wrappedDek                   -> DEK đã bọc
  payloadNonce                 -> nonce riêng cho phép mã hóa payload
  payloadCiphertextAndTag      -> bản mã và authentication tag
  bindingMetadata              -> tenant, recordId, purpose, schemaVersion
  wrapNonceAndTag              -> chỉ có khi wrapping scheme yêu cầu
~~~

**Lưu ý:** Đây là **mẫu mô hình**, không phải một định dạng tiêu chuẩn duy nhất cho mọi KMS. AES-KW không có nonce bên ngoài theo cách giống AES-GCM; một API KMS có thể trả về opaque ciphertext blob chứa metadata nội bộ và yêu cầu encryption context khi unwrap.

### 2.1. Không phải ba thứ “key” đều là một

- **DEK:** Khóa để mở bản mã dữ liệu; có thể sinh riêng theo tenant, object, tập dữ liệu hoặc phiên theo thiết kế.
- **KEK:** Khóa bọc DEK; có thể có một hoặc nhiều phiên bản, mỗi phiên bản bảo vệ nhiều DEK.
- **KMS key resource / alias:** Định danh tài nguyên hoặc tham chiếu dịch vụ. Một alias có thể đổi mục tiêu, còn **key ID/version thực** cần được theo dõi để phục hồi và điều tra.

Trong KMS, thuật ngữ **“data key”**, **“KMS key”** và **“encrypted data key”** có ý nghĩa API khác nhau. Không xem mọi blob do KMS trả là AES key có thể đưa trực tiếp vào **Cipher.init**.

### 2.2. Sơ đồ dữ liệu và khóa

~~~mermaid
flowchart TD
    OWNER["Application owner + Data owner<br/>phạm vi dữ liệu và key policy"] --> APP["Java application"]
    APP --> RNG["Sinh DEK đối xứng mới<br/>CSPRNG / KMS GenerateDataKey"]
    RNG --> AEAD["AEAD: mã hóa payload<br/>AES-GCM với nonce mới"]
    RNG --> WRAP["Wrap DEK bằng KEK<br/>theo chính sách KMS/HSM"]
    KEK["KEK được quản trị<br/>KMS/HSM"] --> WRAP
    AEAD --> STORE["Storage: ciphertext, tag, nonce,<br/>wrapped DEK, key reference, metadata"]
    WRAP --> STORE
    STORE --> READER["Reader được xác thực<br/>và đã kiểm tra quyền dữ liệu"]
    READER --> UNWRAP["KMS/HSM unwrap DEK"]
    KEK --> UNWRAP
    UNWRAP --> DECRYPT["AEAD decrypt + verify tag/AAD"]
    STORE --> DECRYPT
~~~

Sơ đồ mô tả **luồng khái niệm**, không khẳng định KMS luôn trả plaintext DEK. Có những kiến trúc provider thực hiện cả phép toán dữ liệu trong vùng bảo vệ, hoặc chỉ cho phép key handle. Cần đọc khả năng API của hệ thống cụ thể.

## 3. Threat model: wrapping DEK bảo vệ trước rủi ro nào?

### 3.1. Kẻ tấn công chỉ có database hoặc object storage

Giả sử attacker lấy được **payload ciphertext, wrapped DEK, nonce, tag và metadata**, nhưng **không có KEK hoặc quyền KMS unwrap**, đồng thời primitive/độ mạnh và nonce usage đều đúng.

Trong mô hình này, attacker không thể chỉ đọc trường wrapped DEK để lấy raw DEK; vì vậy khó giải mã payload. Đây là lợi ích chính của envelope encryption khi dữ liệu và KEK nằm ở **hai ranh giới truy cập khác nhau**.

Tuy nhiên, nếu attacker có **bản sao plaintext khác**, raw DEK từ cache hoặc IAM grant để unwrap, việc wrapping không còn tạo được rào cản tương ứng.

### 3.2. Kẻ tấn công chiếm ứng dụng có quyền Unwrap

Nếu workload identity được KMS cho phép **Unwrap**, attacker chiếm ứng dụng có thể yêu cầu giải bọc DEK và lấy plaintext trong phạm vi API/permission cho phép.

Do đó cần:

- **IAM/KMS least privilege** theo key resource, operation, workload và môi trường.
- **Authorization nghiệp vụ** trước khi truy xuất ciphertext: user, tenant, record và purpose.
- Ràng buộc **encryption context/AAD** với metadata được tin cậy nếu cơ chế hỗ trợ.
- Giới hạn DEK cache, audit các phép Unwrap và giám sát hành vi bất thường.
- Biện pháp giảm blast radius như KEK/DEK theo tenant hoặc data domain khi phù hợp.

**KMS không biết tự động người dùng nào được xem hóa đơn nào** chỉ vì application có một key ID hợp lệ.

### 3.3. Kẻ tấn công lấy được raw DEK hoặc KEK

| Vật liệu/đặc quyền bị xâm phạm | Rủi ro điển hình | Hướng xử lý |
| --- | --- | --- |
| **Raw DEK của một miền dữ liệu** | Có thể mở ciphertext đã lấy trong cùng miền | Ngừng Encrypt mới, tạo DEK khác, đánh giá re-encrypt dữ liệu |
| **Raw KEK** | Có thể unwrap các DEK được bảo vệ bằng KEK đó nếu có wrapped blobs | Kiểm kê phạm vi, thay KEK, đánh giá DEK/ciphertext đã lộ, không chỉ rewrap |
| **Quyền gọi KMS Unwrap** | Truy cập được những DEK mà principal được phép unwrap | Revoke grants/credential, điều tra logs và đầu ra đã nhận |
| **Chỉ wrapped DEK bị lộ** | Tùy primitive; với wrapping đúng và KEK an toàn, không trực tiếp lộ DEK | Rà soát quyền và metadata, đánh giá khả năng bị tráo/đọc |
| **Application cache chứa plaintext DEK** | Lộ dữ liệu bất kể KMS bảo vệ KEK tốt đến đâu | Giảm thời gian cache, bảo vệ process/dumps và rotate khi cần |

**Hủy KEK sau khi bị lộ không làm kẻ tấn công mất bản KEK đã lấy.** Nếu họ đã sao chép KEK và wrapped DEK, dữ liệu cũ có thể vẫn đọc được ở ngoài KMS. Cũng vậy, việc chỉ rewrap **chính DEK bị lộ** dưới một KEK mới không khôi phục tính bí mật của ciphertext cũ.

## 4. Key wrapping khác mã hóa dữ liệu như thế nào?

Từ **wrap** thường ám chỉ phép toán bảo vệ **key material** với những quy tắc kiểm tra tính toàn vẹn/định dạng thích hợp. Trong Java JCE có thể gặp **Cipher.WRAP_MODE** và **UNWRAP_MODE**; trong KMS, provider có thể gọi API **Encrypt/Decrypt**, **GenerateDataKey**, **ReEncrypt** hoặc **WrapKey** tùy thiết kế.

| Tiêu chí | Mã hóa payload bằng DEK | Wrap DEK bằng KEK |
| --- | --- | --- |
| **Đầu vào chính** | Dữ liệu ứng dụng có độ dài tùy ý | Vật liệu khóa DEK cần bảo vệ |
| **Khóa sử dụng** | DEK | KEK hoặc public key/kem context thích hợp |
| **Thuật toán** | AEAD như AES-GCM | AES-KW, AES-KWP, AEAD wrap, RSA-OAEP hoặc KMS-managed tùy yêu cầu |
| **Dữ liệu đầu ra** | Ciphertext, authentication tag, nonce | Wrapped key blob và metadata cần unwrap |
| **Phân quyền** | Quyền đọc/ghi bản ghi và sử dụng DEK | Quyền KMS/HSM Wrap/Unwrap với KEK |
| **Rotation** | Đổi DEK thường cần **re-encrypt payload** | Đổi KEK có thể chỉ **rewrap DEK** |

**Không gọi việc Encrypt payload bằng DEK là “DEK wrapping”**. **Không gọi mọi chuỗi Base64 chứa DEK là wrapped DEK**: Base64 chỉ là encoding, không bảo vệ tính bí mật.

### 4.1. Wrapped DEK không tự xác thực quyền của người đọc

Một ciphertext/tag được tạo hợp lệ có thể được attacker **copy** sang một bản ghi khác. Nếu ứng dụng bỏ qua kiểm tra tenant và record ID, bản mã có thể bị dùng sai ngữ cảnh dù DEK chưa từng lộ.

Do đó **payload AAD** và, khi có khả năng, **wrapping context** nên được gắn với **tenant, purpose, record key/ID và phiên bản định dạng** theo cách không mơ hồ. Chính các trường này phải đến từ nguồn đáng tin cậy; không để client tự chọn tenant rồi cấp quyền Unwrap dựa trên giá trị đó.

## 5. Các cơ chế dùng để bọc DEK

Không có một thuật toán wrapping duy nhất phù hợp mọi môi trường. Điều quan trọng là **mã hóa bí mật khóa, kiểm tra tính toàn vẹn, kiểm soát ngữ cảnh, chống nhầm lẫn thuật toán và khả năng vận hành**.

| Cơ chế | Đặc điểm | Nên dùng khi | Điều phải chú ý |
| --- | --- | --- | --- |
| **AES Key Wrap (AES-KW, RFC 3394)** | Thiết kế chuyên để wrap key material theo bội số 64 bit (và chiều dài tối thiểu theo RFC) | DEK AES có độ dài hợp lệ, provider hỗ trợ | Không có AAD ngoài; integrity check chuyên dụng, không mã hóa payload tùy ý |
| **AES Key Wrap with Padding (AES-KWP, RFC 5649)** | Cho phép wrapping dữ liệu khóa có độ dài linh hoạt hơn | Key material không khớp độ dài AES-KW cơ bản | Provider/định dạng và rules padding phải đúng |
| **AES-GCM để bọc DEK** | AEAD có nonce, tag và AAD | Khi thiết kế cần authenticated context rõ, dùng API đã được thẩm định | **Không tái sử dụng nonce dưới cùng KEK**; lưu nonce/tag chính xác |
| **RSA-OAEP** | Dùng public key đã xác thực để mã hóa một bí mật nhỏ | Bảo vệ DEK cho người nhận có private key phù hợp | Giới hạn kích thước plaintext; tham số OAEP phải khớp, tránh RSA thô |
| **KMS-managed envelope wrapping** | Dịch vụ giữ KEK, trả encrypted data key/blob | Hệ thống dùng KMS/HSM làm trust boundary | Blob có thể opaque; IAM, encryption context và key ID theo API |
| **HPKE/KEM-based envelope** | KEM/KeyAgreement + KDF + AEAD theo giao thức | Chia sẻ DEK qua ranh giới giữa các bên không cùng KEK | Phải xác thực recipient public key và dùng cấu hình suite hợp lệ |

### 5.1. AES-KW và AES-KWP: không phải AES-GCM

AES-KW được thiết kế để wrap các khối key material có kích thước thỏa điều kiện thuật toán; với **DEK AES-256 dài 32 byte**, đây là một trường hợp điển hình. Đầu ra có cơ chế **integrity check** và không sử dụng nonce do ứng dụng cung cấp giống AES-GCM.

**AES-KWP** mở rộng hỗ trợ các kích thước khác với padding. Khi lựa chọn, phải bảo đảm unwrap sử dụng **cùng thuật toán** đã wrap, không thử đoán nhiều thuật toán hoặc fallback không kiểm soát.

AES-KW/KWP không mang **AAD tenant/record** giống AES-GCM. Nếu muốn ràng buộc wrapped DEK với một tenant cụ thể, cần có **kiến trúc kiểm soát ngữ cảnh** bổ sung như metadata được xác thực, KMS encryption context hoặc phân vùng KEK theo tenant. Không tuyên bố AES-KW tự ràng buộc tất cả metadata ngoài blob.

### 5.2. Bọc DEK bằng AES-GCM cần nonce riêng

Nếu chọn AEAD wrapping, một KEK AES-GCM có thể mã hóa serialized DEK làm plaintext, kèm **wrap nonce, wrap tag** và AAD đã được định nghĩa rõ.

**Nonce wrapping không phải payload nonce**. Một hệ thống có thể có:

- **Payload nonce** cho AES-GCM dùng DEK.
- **Wrap nonce** cho AES-GCM dùng KEK.

Hai nonce thuộc **hai phép mã hóa với hai khóa** và phải được quản lý theo từng key riêng; không lấy một nonce rồi dùng lại dưới cùng KEK cho nhiều DEK khác nhau. Với KEK được dùng cho rất nhiều wraps, phải đặc biệt chú ý **quản lý uniqueness và giới hạn usage**.

### 5.3. Bọc DEK bằng public key

Trong hybrid encryption, public key của người nhận có thể bảo vệ DEK:

- **RSA-OAEP:** Mã hóa DEK có kích thước nhỏ và phù hợp giới hạn OAEP bằng public RSA đã xác thực.
- **HPKE:** Sử dụng cơ chế KEM/KDF/AEAD theo suite và mode của giao thức, không phải “EC encrypt” tự chế.

Một ciphertext DEK được tạo bằng public key **không chứng minh nó đã gửi đến đúng người nhận** nếu public key bị đánh tráo. Cần nguồn công khai đáng tin cậy như PKI, trust registry hoặc cơ chế xác thực theo giao thức. Public key không phải bí mật, nhưng **tính xác thực của nó là bắt buộc**.

## 6. Quy trình tạo DEK và wrap trong một hệ thống thực

Có hai kiến trúc phổ biến: **ứng dụng sinh DEK rồi gửi cho dịch vụ wrap**, hoặc **KMS sinh DEK và trả cả plaintext DEK lẫn encrypted/wrapped DEK** khi API hỗ trợ.

### 6.1. Mô hình A — ứng dụng sinh DEK

1. **Application authorization:** Xác minh thao tác tạo dữ liệu thuộc đúng principal, tenant, environment và purpose.
2. **Generate DEK:** Tạo khóa AES đủ độ mạnh bằng CSPRNG/provider được duyệt; không dùng timestamp hoặc ID làm secret.
3. **Encrypt payload:** Tạo nonce mới phù hợp, xác định AAD từ dữ liệu được tin cậy, mã hóa bằng AEAD.
4. **Wrap DEK:** Sử dụng KEK hoặc dịch vụ KMS/HSM theo cơ chế wrapping được phê duyệt.
5. **Lưu envelope:** Ghi payload ciphertext, tag, nonce, wrapped DEK, key reference, phiên bản và metadata để đọc lại.
6. **Giảm thời gian sống raw DEK:** Loại bỏ bản sao có thể kiểm soát; tránh log, dump, cache kéo dài. Không khẳng định JVM xóa mọi bản sao.

Nếu ứng dụng phải gửi **raw DEK** đến KMS để wrap, điều đó mở rộng đường truyền cần bảo vệ. Một số thiết kế yêu cầu **sinh DEK ngay trong KMS** để giảm bề mặt này.

### 6.2. Mô hình B — KMS GenerateDataKey

Một số managed KMS cung cấp API tương tự **GenerateDataKey**. Khi được cho phép và với tham số phù hợp, dịch vụ có thể trả:

- **Plaintext data key**: DEK dạng rõ cho ứng dụng dùng tạm để mã hóa payload.
- **Encrypted data key / ciphertext blob**: DEK đã được bảo vệ bởi KMS key tương ứng.

Ứng dụng dùng plaintext DEK trong thời gian ngắn, lưu encrypted data key cùng ciphertext, **không lưu plaintext DEK**. Lần đọc sau, ứng dụng gọi API KMS phù hợp để giải bọc key blob.

**Chú ý:** API, tên trường và tính năng khác nhau giữa các nhà cung cấp. Có KMS cung cấp chế độ **chỉ trả encrypted data key** hoặc tích hợp mã hóa trong dịch vụ. Không giả định mọi KMS dùng cùng giới hạn plaintext length hoặc encryption context.

### 6.3. Trình tự khái niệm khi ghi dữ liệu

~~~mermaid
sequenceDiagram
    participant U as User / upstream
    participant APP as Java service
    participant IAM as Authorization
    participant KMS as KMS/HSM
    participant DB as Database
    U->>APP: Ghi dữ liệu tenant A, record 42
    APP->>IAM: Kiểm tra quyền ghi tenant A / record 42
    IAM-->>APP: Allow
    APP->>KMS: GenerateDataKey(keyRef, trustedContext)
    KMS-->>APP: Plaintext DEK tạm + encryptedDataKey
    APP->>APP: AES-GCM encrypt(payload, nonce, trustedAAD)
    APP->>DB: Envelope v1: encryptedDataKey, ciphertext, nonce, tag, keyRef
    Note over APP: Giảm thời gian sống plaintext DEK; không log raw key
~~~

Nếu **KMS trả lỗi** hoặc không xác thực được quyền, **không tự tạo một DEK cố định** hoặc chuyển sang lưu plaintext để giữ cho ứng dụng “chạy được”.

## 7. Quy trình unwrap DEK và giải mã an toàn

Đọc dữ liệu thường có các bước bổ sung so với việc chỉ gọi KMS Decrypt:

1. **Xác thực người gọi** và kiểm tra quyền với tenant/record/action.
2. **Đọc envelope** bằng một định dạng phiên bản được hỗ trợ, kiểm tra kích thước trường, thuật toán và key reference.
3. **Tạo expected context** từ danh tính tài nguyên **đã được server xác minh**; không lấy nguyên tenant/purpose chưa kiểm tra từ blob lưu trữ.
4. **Chọn KMS key hoặc routing** theo key ID/version đã được allowlist và xác thực ranh giới môi trường/tenant.
5. **KMS/HSM unwrap DEK** bằng đúng policy, operation và encryption context khi giao thức yêu cầu.
6. **Kiểm tra đầu ra**: thuật toán, kích thước DEK và các ràng buộc logic cần thiết.
7. **AEAD decrypt payload** bằng nonce và AAD mong đợi. Chỉ chuyển plaintext sang tầng nghiệp vụ sau khi authentication tag được kiểm tra thành công.
8. **Dọn các bản sao có thể dọn** của raw DEK, plaintext/buffer và ghi audit metadata, không log nội dung bí mật.

### 7.1. Không fallback tự động qua mọi key

Một anti-pattern là khi Unwrap với KEK v3 thất bại, ứng dụng tự thử KEK v2, KEK v1, khóa của tenant khác hoặc thậm chí một secret hardcode cho đến khi có kết quả.

Hành vi đó có thể:

- **Vượt chính sách thu hồi** của key v1.
- Tăng cơ hội dùng nhầm key/tenant khi metadata bị sửa.
- Tạo oracle quan sát cho attacker và khiến audit sai.
- Gây chi phí/độ trễ cao, làm mất khả năng giải thích bản ghi thuộc phiên bản nào.

Thay vào đó, metadata cần **định danh rõ key reference** và policy chỉ cho phép những đường đọc lịch sử đã được phê duyệt. Nếu key bị revoked, đường khôi phục đặc biệt phải tách khỏi API thông thường.

### 7.2. Trường hợp wrapped DEK bị thay đổi

Nếu wrapped DEK bị bit-flip, AES-KW/AES-KWP hoặc cơ chế AEAD/KMS có integrity check phù hợp phải **từ chối unwrap**. Nhưng **thay toàn bộ wrapped DEK bằng một blob khác cũng hợp lệ** dưới cùng KEK có thể không bị phát hiện ở lớp wrap nếu không có ràng buộc ngữ cảnh.

Ví dụ, attacker tráo wrapped DEK của record B sang record A. Payload decrypt với DEK sai thường bị AES-GCM từ chối nhờ tag; tuy nhiên hệ thống vẫn cần **không mơ hồ tenant/record/purpose, không bỏ qua AAD và không cho blob hợp lệ bị dùng sai nơi**.

**Tính bí mật của DEK, tính toàn vẹn blob và authorization của bản ghi là ba lớp kiểm soát riêng.**

### 7.3. Khi tag AES-GCM không hợp lệ

Ứng dụng phải **từ chối hoàn toàn** và không trả plaintext từng phần cho nghiệp vụ. Với JCE, lỗi kiểu **AEADBadTagException** biểu thị xác thực thất bại; không thử giải mã lại bằng ECB/CBC hoặc bỏ AAD để làm cho request thành công.

Log có thể ghi **key ID/version, record correlation, operation, policy result** ở mức an toàn. Không log DEK, plaintext, AAD chứa PII hoặc toàn bộ ciphertext khi không cần thiết.

## 8. Thiết kế envelope metadata, key ID và AAD

Envelope là một **định dạng dữ liệu phải tồn tại lâu** qua rotation, backup, migration và thay đổi provider. Nếu thiết kế thiếu key ID/version hoặc thuật toán, dữ liệu có thể trở nên khó đọc khi hạ tầng thay đổi.

### 8.1. Mẫu bản ghi phiên bản hóa

~~~json
{
  "envelopeVersion": 1,
  "payloadAlgorithm": "AES-256-GCM",
  "wrappingScheme": "KMS-MANAGED",
  "kekReference": "approved-prod-kms-key-ref",
  "kekVersion": "key-version-3",
  "wrappedDek": "base64-of-opaque-blob",
  "payloadNonce": "base64-of-nonce",
  "payloadCiphertextAndTag": "base64-of-ciphertext-and-tag",
  "binding": {
    "tenantId": "tenant-a",
    "recordId": "invoice-42",
    "purpose": "encrypt-invoice",
    "schemaVersion": 1
  }
}
~~~

Đây là **mẫu logic minh họa**, không phải kết quả API thật hay cách serialize bắt buộc. Các giá trị Base64 chỉ biểu diễn bytes nhị phân. **Không tự coi metadata có trong blob là đáng tin**; khi đọc phải kiểm tra ràng buộc với bản ghi, workload và chính sách.

**Nonce/tag khi dùng AES-KW**: AES-KW có định dạng wrapping riêng; trong mẫu không có wrap nonce/tag vì scheme là **KMS-MANAGED**. Nếu dùng AES-GCM wrapping, phải lưu thêm **wrap nonce/tag** và cung cấp đúng wrap AAD.

### 8.2. Vì sao cần versioning?

Một thiết kế có thể thay đổi:

- DEK length và thuật toán payload.
- KEK/version hoặc nhà cung cấp KMS.
- Wrapping algorithm (AES-KW, AES-KWP, KMS ciphertext blob).
- Cách tạo AAD/encryption context.
- Encoding, tag placement, nonce policy, trường mở rộng.

**Version phải dẫn tới một bộ quy tắc giải mã rõ ràng**, không phải cơ chế thử mò các thuật toán để tìm cái thành công. Từ chối version hoặc thuật toán không được hỗ trợ; migration phải xử lý các bản ghi lịch sử một cách kiểm soát.

### 8.3. Encryption context/AAD phải ổn định và không mơ hồ

Ví dụ ngữ cảnh:

~~~text
purpose = "invoice-at-rest"
tenant = "tenant-a"
record = "invoice-42"
schema = 1
~~~

Với **AES-GCM**, AAD được đưa vào tính tag nhưng **không được mã hóa**, nên không đặt plaintext bí mật vào AAD nếu không cần. Một số **KMS encryption context** cũng có thể hiện trong audit logs và không được xem như secret.

Khi serialise AAD, tránh kiểu nối chuỗi thiếu phân cách hoặc phân cách có thể xuất hiện trong dữ liệu. Ví dụ:

~~~text
"ab" + "c"  ==  "a" + "bc"
~~~

Hai cặp trường khác nhau có thể cho cùng bytes nếu ghép trực tiếp. Dùng **encoding có độ dài trường, tên trường và version** rõ ràng. Trong Java, có thể sử dụng **ByteBuffer** với các trường đã canonicalize, hoặc một định dạng canonical có đặc tả ổn định.

### 8.4. Key ID/version không thay authorization

Không cấp quyền KMS chỉ vì attacker đưa một **KMS key resource** vào metadata. Key reference có thể là **gợi ý để đọc**, nhưng policy phải kiểm tra:

- Key thuộc **account/region/environment được phép**.
- Key purpose và owner khớp dữ liệu.
- Principal/tenant có quyền nghiệp vụ và quyền KMS cần thiết.
- Key state không phải revoked/compromised đối với thao tác đang yêu cầu.
- Encryption context lấy từ nguồn đáng tin cậy, không hoàn toàn dựa trên input chưa xác thực.

### 8.5. Key ID nhạy cảm đến mức nào?

Key ID/alias thường không phải raw secret. Tuy nhiên, metadata có thể tiết lộ **cấu trúc tenant, dịch vụ, region hoặc lịch rotation**. Hãy áp dụng quyền truy cập, retention và phân loại metadata phù hợp; không in toàn bộ encryption context chứa dữ liệu nhạy cảm vào các log công khai.

## 9. Java 17: AES-KW wrap DEK và AES-GCM mã hóa dữ liệu

Ví dụ sau minh họa toàn bộ chu kỳ ở mức **JCA/JCE**: tạo KEK và DEK AES-256, bọc DEK bằng **AESWrap**, mã hóa payload bằng **AES/GCM/NoPadding**, unwrap DEK và giải mã lại. Code dùng **key material trong process memory** để minh họa; **không phải kiến trúc production có KEK được giữ non-exportable trong KMS/HSM**.

Đoạn mã không dùng mật khẩu người dùng làm KEK. Các khóa được sinh bằng **KeyGenerator** với SecureRandom; key ID trong ví dụ là **metadata minh họa**, không phải quyền do KMS cấp.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.security.KeyPair;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class DekWrappingDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int TAG_BITS = 128;
    private static final int NONCE_BYTES = 12;

    record Envelope(
            int formatVersion,
            String kekReference,
            byte[] wrappedDek,
            byte[] nonce,
            byte[] ciphertextAndTag
    ) {}

    static SecretKey generateAes256() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static byte[] trustedAad(String tenant, String recordId) {
        // Minh họa length-prefix encoding. ID phải được lấy từ metadata
        // đã xác thực và có canonical form ổn định trên mọi phiên bản.
        byte[] t = tenant.getBytes(StandardCharsets.UTF_8);
        byte[] r = recordId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + 4 + t.length + 4 + r.length)
                .putInt(0x44454B31) // "DEK1": định dạng AAD v1
                .putInt(t.length).put(t)
                .putInt(r.length).put(r)
                .array();
    }

    static Envelope encrypt(
            byte[] plaintext,
            byte[] trustedAad,
            SecretKey kek
    ) throws Exception {
        SecretKey dek = generateAes256();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher payload = Cipher.getInstance("AES/GCM/NoPadding");
        payload.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        payload.updateAAD(trustedAad);
        byte[] ciphertextAndTag = payload.doFinal(plaintext);

        Cipher wrapping = Cipher.getInstance("AESWrap");
        wrapping.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedDek = wrapping.wrap(dek);

        return new Envelope(
                1, "demo-kek-v1", wrappedDek, nonce, ciphertextAndTag);
    }

    static byte[] decrypt(
            Envelope envelope,
            byte[] expectedTrustedAad,
            SecretKey kek
    ) throws Exception {
        if (envelope.formatVersion() != 1 ||
                !"demo-kek-v1".equals(envelope.kekReference()) ||
                envelope.nonce().length != NONCE_BYTES) {
            throw new SecurityException("Invalid envelope metadata");
        }

        Cipher wrapping = Cipher.getInstance("AESWrap");
        wrapping.init(Cipher.UNWRAP_MODE, kek);
        Key recovered = wrapping.unwrap(
                envelope.wrappedDek(), "AES", Cipher.SECRET_KEY);
        if (!(recovered instanceof SecretKey dek)) {
            throw new SecurityException("Expected AES secret key");
        }

        Cipher payload = Cipher.getInstance("AES/GCM/NoPadding");
        payload.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        payload.updateAAD(expectedTrustedAad);
        return payload.doFinal(envelope.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        SecretKey demoKek = generateAes256();
        byte[] input = "Hoa don 42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = trustedAad("tenant-a", "invoice-42");

        Envelope saved = encrypt(input, aad, demoKek);
        byte[] output = decrypt(
                saved, trustedAad("tenant-a", "invoice-42"), demoKek);
        try {
            System.out.println("Round-trip OK: " +
                    MessageDigest.isEqual(input, output));
            System.out.println("Wrapped DEK bytes: " +
                    saved.wrappedDek().length);
        } finally {
            Arrays.fill(output, (byte) 0);
        }
    }
}
~~~

**Kết quả minh họa (với provider hỗ trợ AESWrap):**

~~~text
Round-trip OK: true
Wrapped DEK bytes: 40
~~~

**Giải thích:** AES-KW theo RFC 3394 với một DEK AES-256 dài **32 byte** thường tạo **wrapped blob dài 40 byte**, gồm phần dữ liệu khóa và vùng kiểm tra của thuật toán. Đây là thuộc tính của **AES-KW trong ví dụ**, không phải kích thước cố định cho mọi wrapped DEK từ KMS hoặc các thuật toán khác.

### 9.1. Phân biệt hai key và hai phép toán

- **demoKek**: KEK AES-256 sinh trong Java để demo. Ở production, KEK nên nằm tại ranh giới KMS/HSM theo chính sách.
- **dek**: DEK AES-256 chỉ dùng mã hóa payload.
- **Cipher "AESWrap"**: Dùng WRAP_MODE/UNWRAP_MODE để bọc DEK; không mã hóa payload trực tiếp.
- **Cipher "AES/GCM/NoPadding"**: Mã hóa payload với nonce mới, tag và AAD.
- **trustedAad**: Ràng buộc tenant/record và định dạng v1, phải được tạo từ dữ liệu đã xác thực ở tầng ứng dụng.

### 9.2. Những ranh giới của code minh họa

1. **Không đưa demoKek thành file, biến môi trường hardcode hoặc config production.** Trong thực tế, dùng KMS/HSM wrap/unwrap API để không phát tán raw KEK.
2. **Không xem Envelope record là đối tượng bất biến sâu**: các trường byte array có thể bị sửa bởi code khác; production cần defensive copy, giới hạn kích thước và parser nghiêm ngặt.
3. **Không lấy tenant/record từ envelope rồi tự coi là expected AAD**; caller phải xác thực quyền truy cập bản ghi và tạo expected context từ nguồn tin cậy.
4. **Không dùng AESWrap trên dữ liệu payload** hay tùy ý sử dụng DEK cho Sign/HMAC.
5. **Không coi Arrays.fill đủ để zeroize provider key material**: SecretKey/provider có thể giữ bản sao trong JVM/native memory.
6. **Không bỏ qua authentication tag khi Decrypt lỗi**. Với AEAD, mọi trường hợp tag/AAD sai phải bị từ chối.
7. **Không tái sử dụng nonce payload dưới cùng DEK**. Sinh ngẫu nhiên 96-bit là lựa chọn phổ biến, nhưng hệ thống mã hóa rất nhiều bản ghi dưới cùng DEK phải quản lý giới hạn sử dụng/xác suất va chạm theo chính sách.
8. **Không coi round-trip demo là kiểm định an ninh provider**. Ở production cần test sai AAD, ciphertext sửa, wrapped DEK sai, key version khác và provider/KMS lỗi.

## 10. Tích hợp KMS/HSM: API unwrap khác JCE local

Ví dụ JCE ở mục trên có thể truy cập cả **KEK và DEK** trong Java process. Trong production, phần lớn hệ thống muốn KEK **không được xuất dạng rõ**. Khi đó ứng dụng gọi KMS/HSM qua **SDK, provider hoặc key handle**, không dùng một SecretKeySpec chứa raw KEK.

### 10.1. Mô hình API có GenerateDataKey

Mã giả thể hiện ranh giới công việc, **không phải API Java của một nhà cung cấp**:

~~~text
function writeInvoice(authenticatedCaller, invoice):
    assertAuthorizedWrite(authenticatedCaller, invoice.tenant, invoice.id)

    trustedContext = canonicalContext(invoice.tenant, invoice.id, "invoice-v1")
    response = kms.generateDataKey(
        approvedKekReference,
        keySpec = "AES_256",
        encryptionContext = trustedContext
    )
    # response: plaintext DEK tạm + encrypted/wrapped DEK

    payloadNonce = newUniqueNonceFor(response.plaintextDek)
    payloadCiphertext = aesGcmEncrypt(
        response.plaintextDek, payloadNonce, trustedContext, invoice.bytes)

    saveAtomically(
        invoice.id, payloadNonce, payloadCiphertext,
        response.encryptedDataKey, approvedKekReference, envelopeVersion=1)

    destroyOrReleaseTemporaryBuffersAccordingToProvider()

function readInvoice(authenticatedCaller, invoiceId):
    assertAuthorizedRead(authenticatedCaller, invoiceId)
    envelope = loadEnvelope(invoiceId)
    validateSchemaAlgorithmKeyReference(envelope)
    trustedContext = canonicalContextFromAuthorizedRecord(invoiceId)

    plaintextDek = kms.unwrapDataKey(
        envelope.encryptedDataKey,
        expectedKeyReference = approvedKeyReference(envelope),
        encryptionContext = trustedContext
    )

    plaintext = aesGcmDecrypt(
        plaintextDek, envelope.payloadNonce,
        trustedContext, envelope.payloadCiphertext)
    return plaintextOnlyAfterTagVerification(plaintext)
~~~

**Trong API KMS thật, operation và context có thể khác.** Ví dụ, KMS có thể dùng **Decrypt** để giải bọc encrypted data key, một provider khác dùng **UnwrapKey**, còn HSM có thể dùng PKCS#11 mechanism. Trường expectedKeyReference/encryptionContext ở đây diễn đạt chính sách; không khẳng định mọi API hỗ trợ tham số giống hệt.

### 10.2. Khi nào raw DEK xuất hiện ở ứng dụng?

Nếu KMS trả **plaintext data key**, bản rõ tồn tại trong phản hồi, thư viện SDK và ứng dụng ít nhất trong thời gian dùng. Điều này đặt ra các ràng buộc:

- Không log response chứa plaintext DEK.
- Hạn chế **heap dumps, crash dumps, profiling, tracing và debug attachments** có thể giữ bí mật.
- Không giữ **DEK cache dùng chung toàn hệ thống** nếu không có mô hình rủi ro và giới hạn thời gian rõ.
- Không chuyển plaintext DEK cho dịch vụ khác qua message queue chỉ vì họ cần Decrypt.
- Kiểm soát quyền của workload với **KMS Decrypt/Unwrap** và quyền đọc ciphertext.

Nếu yêu cầu là “raw DEK không bao giờ rời vùng phần cứng an toàn”, một mô hình GenerateDataKey trả plaintext cho Java **không đáp ứng nguyên văn yêu cầu đó**. Cần xem xét dịch vụ mã hóa trong HSM/KMS hoặc key handle và giới hạn dung lượng/chi phí/API thực tế.

### 10.3. KMS encryption context và IAM conditions

Một số KMS hỗ trợ **encryption context**: cặp khóa–giá trị **không bí mật** được xác thực cùng thao tác cryptographic wrapping và có thể tham gia điều kiện policy.

Ví dụ ngữ cảnh do server xây dựng:

~~~text
application = "billing"
environment = "production"
tenant = "tenant-a"
purpose = "invoice"
~~~

Khi unwrap, phải cung cấp đúng context theo quy tắc provider. Nếu context không khớp, phép toán có thể thất bại nhờ kiểm tra integrity.

Nhưng:

1. Context **không tự chứng minh caller được phép truy cập bản ghi**; ứng dụng phải xác thực và authorization trước.
2. Context thường **không được mã hóa**, có thể hiện trong audit; không đưa PII hoặc secret trực tiếp nếu không có nhu cầu/phê duyệt.
3. Nếu **tự tin context do client gửi**, attacker có thể chọn context của tenant khác trong một ứng dụng có IAM quá rộng.
4. Cần kiểm thử tính nhất quán context qua **rotation, backup restore, migration và schema evolution**.

### 10.4. IAM và phân tách quyền

| Principal/role | Quyền có thể cần | Quyền thường nên hạn chế |
| --- | --- | --- |
| **Writer service** | Tạo data key/Encrypt hoặc Wrap trong scope của mình | Decrypt hàng loạt dữ liệu khác tenant; DeleteKey |
| **Reader service** | Decrypt/Unwrap những blob thuộc scope và đủ quyền nghiệp vụ | Generate/Sign/Export không liên quan |
| **Rotation worker** | Rewrap/migration theo change ticket được duyệt | Quyền key admin vĩnh viễn hoặc mọi tenant |
| **Key administrator** | Create/disable/rotate policy theo phân quyền | Đọc mọi dữ liệu nghiệp vụ theo mặc định |
| **Security auditor** | Đọc metadata/audit, xác minh chính sách | Raw KEK/DEK hoặc decrypt dữ liệu sản xuất |
| **DR workload** | Quyền phục hồi cụ thể khi kích hoạt failover | Unwrap toàn bộ prod keys mọi lúc |

**Least privilege không thể chỉ mô tả trong tài liệu**. Phải cấu hình **KMS key policy, IAM grants, network boundaries, resource policies, audit và workload identity** sao cho quyền kỹ thuật phản ánh scope đã được duyệt.

## 11. Rewrap, rotate và re-encrypt: ba thao tác không giống nhau

### 11.1. Rewrap thay lớp bảo vệ DEK

Giả sử:

~~~text
Ciphertext = AEAD_Encrypt(DEK_v1, plaintext)
WrappedDEK_old = Wrap(KEK_old, DEK_v1)
~~~

**Rewrap** tạo:

~~~text
WrappedDEK_new = Wrap(KEK_new, DEK_v1)
~~~

**DEK_v1 và payload ciphertext không thay đổi**. Nếu AES-GCM nonce/key usage đã gần giới hạn, rewrap **không đặt lại giới hạn** vì vẫn là DEK_v1.

Đây là thao tác phù hợp khi cần thay **KEK nhưng DEK vẫn đủ an toàn**, chẳng hạn migration giữa các KMS keys hoặc phân tách policy theo môi trường. Tùy nền tảng, KMS có thể thực hiện **ReEncrypt từ old key sang new key** đối với ciphertext blob chứa DEK ở phía KMS, nhưng cần hiểu **đó là re-encrypt blob khóa**, không tự re-encrypt payload ứng dụng.

### 11.2. Re-encrypt thay DEK và payload

Nếu cần thay DEK_v1, phải:

1. Có quyền mở payload cũ theo chính sách.
2. Tạo **DEK_v2 mới** với entropy và thuật toán được phê duyệt.
3. Mã hóa lại payload bằng DEK_v2 với nonce/AAD và format hợp lệ.
4. Bọc DEK_v2 bằng KEK được phê duyệt.
5. Cập nhật record phiên bản một cách atomic/transactional phù hợp, kiểm tra đọc.
6. Retire bản cũ theo retention/incident policy, xử lý backup và sao lưu.

Nếu **raw DEK_v1 đã bị lộ**, chỉ rewrap DEK_v1 dưới KEK khác **không khôi phục tính bí mật**. Kẻ tấn công giữ raw DEK_v1 và ciphertext cũ vẫn có thể mở dữ liệu đã lấy.

### 11.3. Rotate key material trong một KMS resource

Một số KMS hỗ trợ **automatic/manual rotation của vật liệu khóa dưới cùng logical resource**, vẫn giữ khả năng giải mã ciphertext tạo với các phiên bản vật liệu cũ theo quy định dịch vụ. Một số khác đòi hỏi tạo **key resource mới** và migrate encrypted data keys.

Vì vậy cần phân biệt:

- **Rotate material dưới cùng KMS key resource**: key ID có thể giữ nguyên; dịch vụ quản lý phiên bản nội bộ.
- **Chuyển alias sang key mới**: tên truy cập thay đổi, nhưng blob đã mã hóa không nhất thiết đổi.
- **Rewrap DEK**: wrapped key blob thay đổi, payload chưa đổi.
- **Re-encrypt payload**: dữ liệu mã hóa lại dưới DEK mới.
- **Revoke/destroy**: chặn thao tác hoặc loại bỏ key material theo chính sách, không phải cách gọi khác của rotation.

**Không tự bắt buộc rewrap mọi DEK sau mỗi lần KMS tự rotate** nếu semantics của KMS đảm bảo đọc blob cũ và chính sách không yêu cầu migration. Ngược lại, đừng xóa KEK cũ trước khi có bằng chứng tất cả đường dữ liệu/backup cần đọc đã được xử lý.

### 11.4. Luồng rewrap an toàn

~~~mermaid
flowchart TD
    INV["Inventory wrapped DEK đang dùng KEK cũ"] --> PLAN["Phân loại tenant/record/retention<br/>và yêu cầu rollback"]
    PLAN --> NEW["Tạo/duyệt KEK mới,<br/>kiểm tra IAM và KMS API"]
    NEW --> UNWRAP["Unwrap DEK cũ<br/>hoặc KMS ReEncrypt blob"]
    UNWRAP --> WRAP["Wrap cùng DEK bằng KEK mới<br/>với context được xác minh"]
    WRAP --> VERIFY["Kiểm tra định dạng, unwrap theo<br/>đường được phép và đọc payload"]
    VERIFY --> UPDATE{"Đối chiếu version và<br/>cập nhật record atomic?"}
    UPDATE -->|"Conflict / lỗi"| RETRY["Không xóa đường cũ;<br/>retry idempotent có kiểm soát"]
    RETRY --> INV
    UPDATE -->|"Đạt"| REPORT["Ghi inventory/audit/migration result"]
    REPORT --> DONE{"Mọi bản ghi và backup<br/>cần giữ đã xử lý?"}
    DONE -->|"Chưa"| INV
    DONE -->|"Đủ"| RETIRE["Retire/destroy KEK cũ<br/>sau retention và phê duyệt"]
~~~

**Không xóa wrapped DEK cũ trước khi bản mới được kiểm thử.** Nhưng cũng không giữ cả hai bản trong thời gian vô hạn mà không biết chúng còn phục hồi được hay không.

### 11.5. Rewrap phải xử lý race condition

Giả sử rotation worker đọc envelope v1, trong khi một request khác đã cập nhật record sang v2. Worker không được ghi đè bằng metadata cũ. Nên áp dụng:

- **Optimistic version/concurrency control** cho envelope record.
- **Idempotency** để retry không tạo nhiều bản sao bất nhất.
- **Atomic update** của wrapped DEK và key reference khi backend cho phép.
- **Read-back verification** của metadata và thử đọc bản mã cần thiết.
- Ghi audit **old key ref → new key ref, record count, result**, không ghi raw DEK.

### 11.6. So sánh ngắn

| Hành động | DEK thay? | Payload ciphertext thay? | Wrapped DEK thay? | Trường hợp tiêu biểu |
| --- | :---: | :---: | :---: | --- |
| **Rewrap với KEK mới** | Không | Không | Có | Migration KEK |
| **Re-encrypt dưới DEK mới** | Có | Có | Có | Raw DEK lộ, thay miền mã hóa |
| **KMS automatic key material rotation** | Không nhất thiết | Không | Không nhất thiết | Rotation managed by provider |
| **Đổi alias** | Không nhất thiết | Không | Không nhất thiết | Định tuyến tới key resource mới |
| **Disable KEK** | Không | Không | Không | Chặn KMS operations, không xóa blob |
| **Destroy KEK/DEK** | Không phải rotation | Không | Không nhất thiết | Crypto-erasure hoặc kết thúc vòng đời |

## 12. Thiết kế DEK wrapping cho nhiều tenant và môi trường

**Multi-tenant encryption** phải quyết định ranh giới khóa dựa trên **mức độ cô lập, data classification, retention, khả năng truy vấn và chi phí vận hành**.

### 12.1. Chọn phạm vi DEK và KEK

| Mô hình | Lợi ích | Đánh đổi |
| --- | --- | --- |
| **Một DEK per record/object** | Blast radius nhỏ, hỗ trợ crypto-erasure theo đối tượng | Nhiều wrapped DEK, metadata và lần unwrap |
| **Một DEK per tenant** | Dễ cô lập tenant và hủy theo tenant | Phải kiểm soát nonce/usage và truy vết bản ghi |
| **Một DEK per data domain/batch** | Cân bằng số lượng và kiểm soát theo nghiệp vụ | Xác định lifecycle của batch/backup phức tạp |
| **KEK riêng per tenant/domain** | Giới hạn quyền KMS và migration từng miền | Số KMS resources/grants và chi phí quản trị lớn |
| **KEK dùng chung có context + IAM chặt** | Ít tài nguyên hơn và có thể đủ trong một số mô hình | Cần kiểm soát IAM, context và blast radius rất cẩn thận |

Không nên khẳng định mọi tenant phải có một KMS key riêng hoặc mọi record phải có DEK riêng. **Thiết kế chuẩn là thiết kế phù hợp threat model**, có thể chứng minh quyền, luồng dữ liệu và khả năng rotation/destroy.

### 12.2. Một môi trường test không được mặc định unwrap prod DEK

Nếu copy database đã mã hóa từ production sang staging:

- Staging có thể đọc được **ciphertext và wrapped DEK**, nhưng phải **không có quyền KMS prod** theo policy.
- Không nên sửa bằng cách cấp rộng quyền KMS prod cho staging.
- Nếu việc dùng dữ liệu thật được phép, cần quy trình **phê duyệt/sanitization/re-encrypt** và key scope của staging.
- Nếu có mục tiêu **DR phục hồi production**, DR là một luồng khác cần policy, identity và điều kiện failover cụ thể.

Tách khóa đúng cũng giúp tránh việc một DEK/AES-GCM nonce counter bị sử dụng không phối hợp bởi nhiều môi trường.

### 12.3. Ràng buộc tenant với unwrap

KMS context có thể chứa tenant nhưng **tenant phải được xác định từ nguồn tin cậy**. Ví dụ, một HTTP client gửi tenantId=B không được khiến service có quyền unwrap KEK của B chỉ vì service không kiểm tra quyền record.

Một luồng an toàn:

1. Xác thực user/workload.
2. Tra bản ghi và xác định **tenant owner đã xác minh**.
3. Kiểm tra quyền user với đúng record/action.
4. Chọn wrapped DEK và key resource theo inventory, không để client chọn tùy ý.
5. Dùng expected encryption context/payload AAD gắn với tenant/record đã xác thực.
6. Gọi unwrap, decrypt và chỉ trả plaintext sau khi AEAD tag hợp lệ.

### 12.4. Encryption context không phải nhãn phân quyền duy nhất

Đừng dùng một trường context tự khai báo như **environment=prod** làm chứng cứ caller là production. Phải dựa vào **IAM/workload identity và nguồn cấu hình deployment đã xác thực**, cùng KMS key policy.

**Encryption context giúp cryptographic binding và policy filtering**, nhưng không tự giải quyết cross-tenant authorization hoặc raw DEK bị lộ từ process.

## 13. Thu hồi, hủy và crypto-shredding đối với wrapped DEK

### 13.1. Hủy một DEK có thể làm mất cả tập ciphertext

Giả sử tenant A dùng **DEK-A**, tất cả ciphertext của A chỉ được đọc qua bản wrapped DEK-A. Nếu hủy mọi bản có thể khôi phục của DEK-A và không còn đường khác, dữ liệu đó có thể không thể giải mã qua hệ thống được quản lý.

Đây là một dạng **cryptographic erasure (crypto-shredding)**, nhưng phải xác minh:

- Không còn plaintext DEK-A trong cache, dumps, local keystore, backup hoặc export package.
- Không có bản wrapped DEK-A dưới một KEK khác vẫn có thể unwrap.
- Không có plaintext copy của dữ liệu bên ngoài lớp mã hóa.
- Không còn legal hold hoặc retention đòi hỏi phục hồi.
- Không có tenant/data domain khác dùng chung DEK-A.

**Xóa một hàng dữ liệu chứa wrapped DEK chưa đủ để kết luận đã xóa mọi bản sao**; snapshot, replica, backup hoặc transaction log có thể giữ nó.

### 13.2. Hủy KEK là thao tác có blast radius lớn

Nếu KEK bảo vệ hàng nghìn DEK, hủy KEK không đúng thời điểm có thể làm mất khả năng giải bọc **tất cả DEK phụ thuộc**, kể cả dữ liệu còn phải giữ.

Trước khi hủy KEK:

1. Kiểm kê tất cả ciphertext blobs hoặc wrapped DEK tham chiếu tới KEK/versions cần hủy.
2. Rewrap khi cần, kiểm tra đọc thật và đối chiếu backup/DR.
3. Kiểm tra quyền, cache, exports và những hệ thống ngoài đường đi hiện tại.
4. Xử lý retention/legal hold, phê duyệt độc lập và blast radius.
5. Theo dõi trạng thái **requested → pending → executed → verified** theo semantics API.
6. Lưu bằng chứng hủy trong đúng phạm vi; không log raw KEK.

### 13.3. Bản sao ngoài quyền kiểm soát vẫn tồn tại

Nếu attacker đã lấy **raw KEK** và toàn bộ wrapped DEK trước khi hủy, việc hủy key trong KMS sau sự cố **không thu hồi được bản sao đó**. Rewrap DEK cũ dưới KEK mới không khiến bản sao raw DEK đã giải ra mất hiệu lực.

Tương tự, nếu attacker lấy **raw DEK và ciphertext**, việc destroy bản DEK trong hệ thống có thể ngăn các request hợp lệ về sau nhưng **không xóa dữ liệu attacker đã lấy**.

### 13.4. Giữ chứng cứ mà không giữ lại secret

Hồ sơ destruction/migration nên giữ **key ID/version, owner, tenant, reason, approval, data dependency inventory, KMS operation ID, effective time, verification result và residual risk**. Không lưu raw key “để làm bằng chứng đã từng tồn tại”.

## 14. Hiệu năng, caching và giới hạn sử dụng DEK

Một thiết kế đúng về mật mã có thể gặp vấn đề vận hành nếu mỗi lần đọc một record đều tạo ra nhiều yêu cầu KMS với độ trễ cao, chi phí lớn hoặc bị throttling.

### 14.1. Bài toán số lần gọi KMS

Ví dụ, ứng dụng đọc nhiều bản ghi trong một request. Nếu **mỗi bản ghi có một DEK**, mỗi lần đọc có thể cần một thao tác unwrap nếu không có cơ chế tối ưu. Điều này tạo **trade-off giữa isolation và số lượt gọi KMS**.

Những chiến lược cần đánh giá:

- Dùng **DEK theo nhóm dữ liệu/tenant** ở những nơi blast radius và giới hạn nonce cho phép.
- Hỗ trợ **batch operations hoặc KMS data key caching** nếu SDK/nhà cung cấp và chính sách cho phép.
- Chỉ giải mã những trường mà nghiệp vụ được quyền truy cập; không đọc và unwrap toàn bộ bảng vì tiện xử lý.
- Theo dõi **KMS latency, throttling, error rate và chi phí** cùng tỷ lệ cache hit.
- Thiết kế **backpressure/retry có giới hạn**; không retry vô tận gây amplification khi KMS đang sự cố.

**Tối ưu hiệu năng không được đưa raw KEK vào ứng dụng**, bỏ IAM KMS hoặc kéo dài plaintext DEK cache không kiểm soát.

### 14.2. Data key cache có rủi ro gì?

Nếu giữ DEK dạng rõ trong cache:

1. Số DEK bị lộ tăng khi process bị chiếm hoặc heap dump bị lấy.
2. Một thao tác **revoke quyền KMS** chưa chắc chặn được DEK vẫn nằm trong cache.
3. DEK có thể vượt **giới hạn số bytes/requests hoặc thời gian sống** do chính sách quy định.
4. Một cache dùng chung nhiều tenant có thể dẫn đến **key confusion** nếu cache key không bao gồm key ID/version, tenant, purpose và context cần thiết.
5. Cache cũ có thể còn giữ DEK sau rotation hoặc trước khi ứng dụng nhận revocation event.

Do đó cần đặt **max age, max uses, max bytes encrypted, cache partitioning, invalidation on revocation và audit** theo threat model. Nếu không có những biện pháp này, giải pháp an toàn hơn có thể là không cache plaintext DEK hoặc chỉ cache trong thời gian rất ngắn.

### 14.3. Ngân sách nonce AEAD

Với **AES-GCM**, **nonce phải duy nhất dưới cùng một DEK**. Một hệ thống dùng DEK lâu dài cho nhiều instance cần có cách bảo đảm uniqueness, hoặc chọn phương án **DEK mới với phạm vi nhỏ**.

Ví dụ thiết kế:

- **DEK per object** cùng một nonce ngẫu nhiên mới cho mỗi object có thể giảm số lần dùng mỗi DEK, nhưng vẫn phải tuân theo chính sách và giới hạn thuật toán.
- **DEK per tenant với hàng tỷ bản ghi** cần một chiến lược phân phối nonce nghiêm ngặt và tính toán giới hạn bảo mật; không cho các instance tự tăng một counter cục bộ từ 0 rồi dùng chung DEK.
- **Rewrap KEK** không thay DEK, vì vậy **không reset nonce budget**.

Nếu không thể bảo đảm nonce uniqueness và usage limits, cần thiết kế lại phạm vi DEK hoặc chọn mode/giao thức đã được thẩm định phù hợp, không tự cho rằng IV ngẫu nhiên luôn tuyệt đối không trùng.

### 14.4. Thời gian sống của DEK trong Java

Trong Java, raw key bytes có thể tồn tại trong **SecretKey, SDK response, Cipher provider, heap, native buffers hoặc memory snapshot**. Dù code cố xóa một byte array, điều đó **không đảm bảo mọi bản sao được zeroize**.

Các bước giảm rủi ro:

- Không serialize SecretKey hoặc KMS response có plaintext vào logger/trace.
- Giới hạn quyền tạo heap dump, debugger, profiler và đọc process memory.
- Không đưa plaintext DEK vào message bus/Redis để các dịch vụ cùng dùng.
- Tránh lưu plaintext DEK qua vòng đời request nếu không thật cần.
- Đo tác động khi giảm cache TTL; chọn giới hạn đáp ứng cả hiệu năng lẫn chính sách an ninh.
- Nếu yêu cầu HSM-only material, thiết kế hoạt động bằng **key handle hoặc provider** thay vì GenerateDataKey trả raw key ra JVM.

## 15. Backup, DR và khả năng khôi phục sau khi rewrap

Một envelope không chỉ sống trong database chính; nó còn có thể nằm trong **snapshot, object version, transaction log, warehouse export, offline backup và vùng disaster recovery (DR)**.

### 15.1. Bốn câu hỏi DR bắt buộc

1. Khi khôi phục ciphertext và wrapped DEK cũ, **KMS key phiên bản nào** có thể unwrap nó?
2. Region/DR account có **quyền thực tế** với key resource cần dùng, hay chỉ có metadata tham chiếu tới một KMS không truy cập được?
3. Khi main region bị ngừng, có cơ chế **KMS/HSM replication/restore** được phê duyệt không?
4. Nếu một KEK đã **revoked/destroyed**, DR có vô tình khôi phục key policy, grants hoặc cache cũ không?

### 15.2. Snapshot trước và sau rotation

Giả sử:

~~~text
T0: DB backup chứa wrappedDEK_v1 dưới KEK_old
T1: Production DB đã rewrap sang KEK_new
T2: KEK_old bị hủy
T3: Khôi phục DB backup tại T0
~~~

Nếu bản backup ở T0 còn dữ liệu cần giữ và **chưa có cơ chế migrate hoặc giải bọc tương ứng**, tại T3 dữ liệu có thể không giải mã được. Vì vậy, điều kiện hủy KEK_old phải xét **backup retention và restore path**, không chỉ số bản ghi đang ở database chính.

Một cách xử lý có thể là:

- Migrate/rewrap cả backup trong phạm vi được quản lý khi khả thi.
- Giữ cơ chế khôi phục được phê duyệt trong thời gian retention, với IAM và audit chặt.
- Thiết kế bản backup với **wrapped DEK dưới key phục hồi riêng** theo policy từ đầu.
- Chỉ hủy khi đã chứng minh không còn nghĩa vụ đọc dữ liệu cũ hoặc đã có đường phục hồi phù hợp.

**Giữ một raw KEK bí mật ngoài inventory để “phòng trường hợp cần restore” không phải backup an toàn.** Nó phá nguyên tắc kiểm soát bản sao, thường làm yếu crypto-shredding.

### 15.3. DR không có quyền mặc định dùng mọi production key

Một workload DR có thể cần quyền Unwrap **những KEK cần cho failover**, nhưng nên có **scope, trigger, thời hạn, approval và logging**. Không trao quyền giải mã toàn bộ mọi tenant cho một principal chỉ vì tên của nó có chữ “backup”.

Nếu DR được tách thành môi trường diễn tập với dữ liệu đã sanitize/re-encrypt, nó có thể dùng **KEK khác** với production. Hai mô hình khác nhau cần được phản ánh trong inventory.

### 15.4. Restore cần đối soát revocation

Khôi phục backup cũ có thể làm sống lại:

- Envelope tham chiếu key đã revoked.
- IAM grants hoặc key aliases đã thay.
- Plaintext data key cache đã từng lưu.
- Metadata context/schema cũ không còn hợp lệ.

Quy trình restore phải đối soát **trusted key registry, key state/tombstone, IAM và schema version** hiện hành trước khi cho workloads đọc/ghi dữ liệu.

## 16. Kiểm toán, giám sát và test cho DEK wrapping

### 16.1. Những bằng chứng nên lưu

| Trường audit/inventory | Mục đích |
| --- | --- |
| **Key ID/version, KEK reference** | Biết DEK được bảo vệ bằng resource nào |
| **Wrapped DEK record reference** | Tìm bản mã phụ thuộc mà không lưu raw DEK |
| **Owner, tenant, environment, purpose** | Xác định phạm vi và người chịu trách nhiệm |
| **Algorithm/schema version** | Phục vụ migration và đánh giá policy |
| **Principal / action / timestamp** | Truy xuất ai gọi Wrap/Unwrap/Decrypt |
| **Policy decision / KMS result** | Phát hiện quyền sai và API bị lạm dụng |
| **Change/incident ID** | Liên kết rotation, revocation, emergency response |
| **Migration progress and validation** | Chứng minh DEK blobs đã rewrap và dữ liệu còn đọc được |
| **Backup/DR status** | Ngăn hủy KEK khi còn phụ thuộc lịch sử |
| **Residual risk / exceptions** | Không báo thành công quá mức chứng cứ |

**Không đưa raw DEK/KEK, plaintext hoặc secret token vào audit logs.** Nếu encryption context chứa tenant ID hoặc business metadata, xác định cách phân loại và retention log phù hợp.

### 16.2. Các tín hiệu nên cảnh báo

- **Unwrap** từ workload, account, region, tenant hoặc thời điểm không mong đợi.
- Một principal có khối lượng Decrypt/Unwrap tăng đột ngột.
- Wrapped DEK không có key ID/version, hoặc key reference không nằm trong inventory.
- Truy vấn production key từ non-production workload.
- Dùng KEK đã **retired/revoked** cho Wrap mới.
- Lỗi authentication tag tăng sau một đợt migration.
- Envelopes còn phụ thuộc KEK cũ sau mốc phải hoàn tất rewrap.
- Backup restore đưa về encryption context hoặc alias đã bị ngừng sử dụng.
- KMS policy thay đổi đột ngột: grants rộng hơn, Export hoặc Disable/Delete ngoài change ticket.

### 16.3. Test matrix bắt buộc

| Test case | Kết quả kỳ vọng |
| --- | --- |
| Wrap DEK hợp lệ, unwrap đúng KEK và context | Khôi phục đúng DEK và giải mã được payload |
| Thay một bit của wrapped DEK | Unwrap thất bại theo integrity check |
| Dùng KEK sai | Unwrap thất bại, không thử fallback tùy tiện |
| Dùng encryption context/AAD sai | KMS hoặc AEAD từ chối, không trả plaintext |
| Đổi tenant/record ID trong request | Authorization và context không cho truy cập record khác |
| Sửa payload ciphertext hoặc tag | AEAD decrypt thất bại |
| Sửa nonce payload | AEAD decrypt thất bại hoặc dữ liệu không xác thực |
| Envelope version/algorithm không hỗ trợ | Từ chối có kiểm soát; không downgrade |
| Workload test gọi prod KMS Unwrap | IAM/KMS từ chối |
| Principal đã bị revoke còn gọi Unwrap | Bị KMS policy từ chối; cache cũ được xử lý |
| Rewrap KEK_old sang KEK_new | Wrapped DEK đổi, payload cũ vẫn đọc được bằng DEK đúng |
| Re-encrypt bằng DEK mới | Payload ciphertext mới, metadata/counter đúng |
| Migration bị dừng giữa chừng | Retry idempotent, version consistency, không mất dữ liệu |
| KMS outage hoặc throttling | Fail closed, retry/backpressure theo policy, không plaintext fallback |
| Restore backup trước rotation | Có đường đọc được phê duyệt hoặc được xác định rõ là không còn cần |
| KEK chuẩn bị hủy vẫn còn wrapped DEK cần đọc | Pre-destruction check chặn |
| Raw DEK có trong heap/trace logs | Test/scan cảnh báo và sửa đường rò |

### 16.4. Kiểm thử âm tính quan trọng ngang round-trip

Một demo chỉ chứng minh **decrypt(encrypt(x)) = x**. Nó **không chứng minh**:

- Blob không bị tráo giữa tenant.
- Authentication tag và nonce được xử lý đúng.
- Key ID/version không bị attacker chỉ định trái phép.
- IAM không cấp quyền đọc data của tenant khác.
- Key đã revoked thật sự không được dùng.
- Backup/DR vẫn khôi phục được sau khi hủy KEK cũ.

Để nghiệm thu, cần **negative tests, access tests, failure-mode tests và restore drills**, không chỉ một unit test thành công.

## 17. Case study: DEK wrapping cho hệ thống hóa đơn nhiều tenant

Một nền tảng Java có các thành phần:

- **Billing API** nhận và trả hóa đơn cho từng tenant.
- **Database** lưu ciphertext và envelope metadata; không lưu plaintext DEK.
- **KMS production** có các KEK và chính sách IAM phù hợp.
- **Application owner** quản lý key inventory, key version, rotation, sự cố và yêu cầu khả dụng.
- **Data owner** quyết định retention của hóa đơn và giới hạn sử dụng dữ liệu.
- **SRE/DR** quản lý backup, rollback và khôi phục dịch vụ.

Nền tảng chọn **DEK riêng theo tập dữ liệu/tenant** theo phân loại rủi ro. Giả sử đối với tenant A, một hóa đơn có thể được bảo vệ bằng DEK-A và wrapped DEK tương ứng; tenant B dùng key domain riêng để giảm blast radius.

### 17.1. Lưu một hóa đơn mới

**Bước 1 — Authorization.** API xác thực caller và kiểm tra quyền tạo hóa đơn cho tenant A. Tenant không được chỉ xác định bằng một trường header do client tự đặt mà không kiểm chứng.

**Bước 2 — Key generation.** App gọi KMS GenerateDataKey hoặc sinh DEK theo policy, lấy raw DEK tạm cùng wrapped key được bảo vệ bởi KEK phù hợp.

**Bước 3 — AAD.** Tạo AAD từ các trường đã được xác nhận: **tenant A, invoice ID, purpose, schema version**. Encoding phải không mơ hồ.

**Bước 4 — Payload encryption.** Dùng **AES-GCM** với nonce mới dưới DEK, tạo ciphertext và authentication tag.

**Bước 5 — Ghi envelope.** Lưu:

~~~text
invoiceId = inv-42
tenantId = tenant-a
envelopeVersion = 1
payloadAlgorithm = AES-256-GCM
keyWrapScheme = managed-kms
kekReference = billing-prod-kek-v3
wrappedDek = <opaque encrypted data key>
nonce = <12-byte AEAD nonce, encoded>
ciphertextAndTag = <encrypted payload + tag>
~~~

Các giá trị trong ngoặc là **minh họa**, không phải bí mật thực. Không lưu raw DEK dưới tên trường phụ, không đẩy KMS response chứa plaintext DEK vào log.

### 17.2. Đọc lại hóa đơn

1. User có quyền đọc hóa đơn inv-42 thuộc tenant A.
2. Ứng dụng đọc envelope và kiểm tra phiên bản/thuật toán/key reference trong **allowlist**.
3. Ứng dụng tạo expected AAD/context từ record ownership trong hệ thống, không tin dữ liệu tùy ý do caller gửi.
4. KMS kiểm tra quyền và unwrap đúng encrypted data key.
5. AES-GCM Decrypt phải kiểm tra tag/AAD trước khi trả nội dung hóa đơn.
6. Kết quả được trả cho user sau khi đủ authorization; audit metadata được lưu.

Nếu một client thuộc tenant B biết **invoiceId của A** nhưng không được quyền đọc, hệ thống phải từ chối **trước hoặc độc lập với** thao tác KMS. Không cho phép “thử decrypt rồi quyết định có trả dữ liệu hay không” như cách kiểm soát truy cập duy nhất.

### 17.3. Rotation định kỳ KEK v3 → v4

Khi KEK-v3 tới lịch rotation:

- Đội KMS tạo/cho phép KEK-v4 và giới hạn đúng principal.
- Rotation worker liệt kê wrapped DEK đang dùng KEK-v3.
- Theo semantics của nhà cung cấp, worker **unwrap rồi wrap** hoặc dùng **KMS ReEncrypt** để chuyển **wrapped DEK blobs**, không nhất thiết đọc/mã hóa lại payload.
- Mỗi update phải đi cùng **keyRef/version mới** một cách nhất quán.
- Kiểm thử decrypt ngẫu nhiên hoặc toàn diện theo chính sách; đối soát kết quả migration và backup/DR.
- Chỉ retire/hủy KEK-v3 sau khi các phụ thuộc dữ liệu còn cần đã được xử lý.

**Dữ liệu không tự trở nên an toàn hơn trước một DEK đã lộ** chỉ vì KEK-v4 được đưa vào sử dụng. Nếu sự cố là **raw DEK exposure**, phải đánh giá re-encrypt payload bằng DEK mới.

### 17.4. Sự cố: quyền Unwrap của service bị chiếm

Giả sử audit phát hiện principal của một API bị lạm dụng để gọi Unwrap nhiều lần:

1. **IR/Security** cô lập principal, thu hồi credential/grants và dừng đường gọi bất thường.
2. **Application owner** cung cấp key inventory và danh sách ciphertext/wrapped DEK mà principal có thể truy cập.
3. Đánh giá từ **KMS logs và application logs**: Những DEK/record nào đã thực sự được trả ra hoặc giải mã?
4. Không tự khẳng định **KEK key bytes đã lộ**, vì trường hợp có thể chỉ là API abuse; cũng không xem DEK an toàn nếu API đã trả plaintext DEK cho attacker.
5. Thay DEK/re-encrypt dữ liệu theo phạm vi đã đánh giá, thay IAM scope, kiểm tra AAD và record-level authorization.
6. Xử lý backup, token/chữ ký liên quan nếu có; lưu bằng chứng và rủi ro tồn dư.

### 17.5. Sự cố: raw KEK bị lộ

Đây là tình huống có **blast radius** lớn hơn, tùy phạm vi dữ liệu đã wrap. Ngoài thu hồi quyền và thay KEK, cần đánh giá các **wrapped DEK attacker có thể đã thu thập**. Nếu đối thủ có raw KEK và blobs cũ, họ có thể unwrap DEK; chỉ rewrap blobs trên hệ thống hôm nay không thay đổi những bản họ đã giữ.

Với dữ liệu cần tiếp tục giữ bí mật, cần xem xét **DEK mới/re-encrypt** và đánh giá thông báo theo chính sách. Quyết định phải dựa trên khả năng lộ dữ liệu thực tế, không chỉ status “rotated”.

## 18. Những anti-pattern thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **Lưu raw DEK cạnh ciphertext** | Mất lợi ích phân tách ranh giới của envelope encryption | Chỉ lưu wrapped DEK và metadata cần thiết |
| **Ghi wrapped DEK ở dạng Base64 rồi coi là mã hóa** | Base64 không bảo vệ key material | Dùng cơ chế wrap/AEAD/KMS được phê duyệt |
| **Dùng một KEK hardcode trong Java/config** | Một lần lộ ảnh hưởng hàng loạt DEK | KEK trong KMS/HSM/keystore phù hợp với quyền chặt |
| **Dùng AES-ECB hoặc RSA thô để wrap** | Không đáp ứng bảo vệ/kiểm tra cần thiết | AES-KW/KWP, AEAD hoặc RSA-OAEP đúng đặc tả |
| **Chọn AES-KW nhưng không kiểm tra độ dài DEK** | Lỗi runtime hoặc format không tương thích | Thực thi giới hạn thuật toán; dùng AES-KWP khi phù hợp |
| **Dùng AES-GCM wrapping nhưng tái sử dụng nonce dưới KEK** | Rủi ro nghiêm trọng về bí mật/toàn vẹn | Quản lý nonce uniqueness theo KEK, kiểm soát usage |
| **Dùng DEK mã hóa payload cũng làm KEK tùy tiện** | Khó tách mục đích, tăng blast radius | Tách key usage và quyền theo chính sách |
| **Không lưu key reference/version** | Không biết dùng KEK nào để unwrap sau rotation | Envelope versioned metadata, inventory |
| **Để client chọn KMS key resource tùy ý** | Cross-tenant/cross-environment access | Allowlist theo workload và record đã xác thực |
| **Tin tenantId trong ciphertext metadata** | Attacker có thể tráo tenant/context | Kiểm tra owner record độc lập, AAD được xác thực |
| **Bỏ qua AAD hoặc tag khi lỗi** | Chấp nhận dữ liệu sai ngữ cảnh/không toàn vẹn | Fail closed khi AEAD authentication thất bại |
| **Khi unwrap lỗi thì thử mọi key cũ** | Vượt revocation policy và che giấu lỗi metadata | Chọn key theo policy; đường recovery tách biệt |
| **Coi rewrap là re-encrypt payload** | DEK cũ vẫn còn, rủi ro raw DEK không được xử lý | Phân biệt mục tiêu KEK rotation với DEK replacement |
| **Rotate KEK làm mới nonce budget của DEK** | Có thể vượt giới hạn AEAD của DEK | Theo dõi usage theo chính DEK |
| **Tắt KMS và fallback lưu plaintext** | Rò bí mật, mất kiểm soát truy cập | KMS HA/DR được duyệt, fail closed |
| **Cache plaintext DEK vô thời hạn** | Revoke KMS không còn chặn được key tại app | TTL/usage limits, phân vùng cache, invalidation |
| **Dùng chung DEK giữa prod và test** | Sự cố non-prod lan sang prod, nonce khó quản lý | Key domains độc lập, phân tách IAM/KMS |
| **Rewrap không atomic** | Wrapped blob và key ref lệch phiên bản, mất khả năng đọc | Concurrency control, transactional update, readback |
| **Hủy KEK sau khi DB chính chuyển xong** | Backup cũ vẫn cần KEK, restore thất bại | Kiểm kê DR/snapshots/retention trước destruction |
| **Xóa wrapped DEK đồng nghĩa xóa dữ liệu** | Bản sao ở backup vẫn còn; plaintext ngoài luồng vẫn tồn tại | Crypto-erasure theo phạm vi và bằng chứng |
| **Cho application admin quyền DeleteKey toàn bộ** | Hủy nhầm hoặc lạm dụng KEK ảnh hưởng nhiều tenant | Separation of duties, dual control, change approval |
| **Log KMS response để debug** | Có thể lộ plaintext DEK hoặc context nhạy cảm | Log metadata tối thiểu và redaction chính xác |

## 19. Checklist đánh giá thiết kế DEK wrapping

Trước khi nghiệm thu cho production, hãy kiểm tra:

1. **Mục đích:** DEK được dùng trực tiếp để mã hóa payload, KEK để wrap DEK, không nhầm vai trò?
2. **Thuật toán:** Wrapping mechanism đã được chọn rõ (AES-KW/KWP, AES-GCM, RSA-OAEP hoặc KMS-managed) với giới hạn phù hợp?
3. **DEK generation:** DEK có entropy tốt, độ dài đúng, sinh từ CSPRNG/KMS theo chính sách?
4. **KEK storage:** KEK thực sự được bảo vệ ở đâu, có non-exportable/backup/replication phù hợp?
5. **Output:** Database chỉ giữ wrapped DEK và ciphertext, không giữ plaintext DEK hay KEK?
6. **Payload AEAD:** Có nonce duy nhất theo DEK, tag đúng kích thước, AAD và key usage limits?
7. **Wrap integrity:** Unwrap sai key, sai blob hoặc sai context có thất bại an toàn?
8. **Metadata:** Có version, algorithm, key ID/version, nonce/tag, wrapped DEK, owner/tenant/purpose?
9. **Canonical context:** AAD được tạo từ các trường có độ dài/encoding rõ và nguồn đáng tin cậy?
10. **Authorization:** Caller được xác thực, kiểm tra quyền record-level trước khi cho phép Decrypt/Unwrap?
11. **IAM:** Workload chỉ có quyền cần thiết đối với KEK và operation; không có admin grants dư?
12. **Multi-tenant:** KEK/DEK được phân vùng đúng threat model, không dùng context tự khai báo để vượt quyền?
13. **Environment:** Test/staging không mặc nhiên có quyền unwrap production blobs; DR là trường hợp được thiết kế rõ?
14. **Provider:** KMS/HSM SDK và API được dùng theo semantics thật, không giả định mọi nhà cung cấp giống nhau?
15. **Raw DEK memory:** Có chính sách cache, thời gian sống, chống log/dump và xử lý buffer phù hợp?
16. **Rotation:** Phân biệt auto KEK material rotation, rewrap, re-encrypt và alias changes?
17. **Migration:** Rewrap có transaction/concurrency control, idempotency, readback và kiểm soát retry?
18. **Compromise:** Khi raw DEK hoặc KEK bị lộ, đã đánh giá ciphertext attacker có thể có, không chỉ đổi KEK?
19. **Backup:** Khóa/ciphertext ở snapshot, DR và archived data đã được kiểm kê trước khi hủy?
20. **Revocation:** Key bị revoked có bị chặn thật tại KMS và cache/workload không, có negative tests?
21. **Crypto-erasure:** Khi dùng hủy DEK/KEK để xóa dữ liệu, có xác minh mọi đường khôi phục và legal hold?
22. **Audit:** Có key ID/version, principal, action, policy result, change/incident ID mà không có raw key?
23. **Testing:** Đã thử sai AAD, tag, blob, key ID, tenant, version, KMS outage và restore trước rotation?
24. **Operations:** Có owner, runbook, KMS latency/quota monitoring, emergency procedure và trách nhiệm phê duyệt?

## 20. Ghi nhớ

- **DEK wrapping là lớp bảo vệ key material** trong envelope encryption: **DEK mã hóa dữ liệu; KEK bảo vệ DEK**.
- **Wrapped DEK có thể lưu cùng ciphertext**, nhưng vẫn cần metadata, key version, ràng buộc ngữ cảnh, IAM và chống tráo đổi.
- **AES-KW, AES-KWP, AEAD wrapping, RSA-OAEP và KMS-managed wrapping** có semantics khác nhau. Chọn đúng primitive, provider và key usage; không dùng Base64 như một cơ chế bảo vệ khóa.
- **GenerateDataKey** trong một số KMS có thể trả cả raw DEK và encrypted data key. Khi đó raw DEK **vẫn tồn tại tạm trong ứng dụng** và phải được bảo vệ.
- **Rewrap là thay KEK bảo vệ cùng DEK; re-encrypt là dùng DEK mới để mã hóa lại dữ liệu**. Một raw DEK đã lộ không được “sửa” bằng rewrap.
- **AAD/encryption context và key ID** giúp ràng buộc đúng dữ liệu, nhưng **không thay authentication/authorization** theo user, tenant, record và workload.
- **KMS/HSM, key inventory, least privilege, audit và dual control** giúp quản lý blast radius của KEK, nhất là với nhiều tenant.
- **Nonce uniqueness, caching, KMS quotas, backup/DR, rotation, revocation và crypto-erasure** đều ảnh hưởng trực tiếp đến việc wrapped DEK có thể được sử dụng an toàn trong suốt vòng đời.

Khi thiết kế **DEK wrapping**, hãy luôn trả lời ba câu hỏi: **“DEK dạng rõ tồn tại ở đâu và trong bao lâu?”, “Ai có quyền giải bọc DEK dưới KEK nào, cho dữ liệu nào?”, “Nếu phải rotate, revoke hoặc destroy KEK/DEK, mọi bản mã và bản sao lưu còn cần có thể được xử lý an toàn không?”** Chỉ khi có câu trả lời dựa trên chính sách, bản đồ phụ thuộc và kết quả kiểm thử, lớp wrapping mới thực sự là một phần đáng tin cậy của hệ thống quản lý khóa.




