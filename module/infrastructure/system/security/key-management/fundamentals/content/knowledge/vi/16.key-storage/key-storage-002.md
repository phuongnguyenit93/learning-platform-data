# In-memory key: Quản lý khóa mật mã trong bộ nhớ an toàn

Một dịch vụ Java nhận dữ liệu khách hàng, gọi KMS để mở khóa một **DEK (Data Encryption Key)**, rồi dùng **AES-GCM** giải mã trong JVM. Đội phát triển tự tin rằng KEK được giữ trong HSM và database chỉ chứa ciphertext cùng wrapped DEK. Tuy nhiên, trong một đợt điều tra lỗi, hệ thống tự ghi **heap dump** và tải dump lên một kho dùng chung. Dump có thể chứa **DEK bản rõ, đối tượng SecretKey, plaintext hoặc dữ liệu trung gian**. Về mặt lưu trữ trên đĩa, chính sách key wrapping được thiết kế đúng; về mặt **in-memory key management**, bí mật vẫn có nguy cơ bị lộ.

**In-memory key** là key material hoặc đối tượng đại diện cho khóa đang hiện diện trong **không gian nhớ của tiến trình hay môi trường thực thi** để phục vụ các phép toán mật mã. Nó có thể là byte array của AES/HMAC, private-key object, một key được dẫn xuất từ HKDF, key handle của provider, hoặc bản sao tạm thời do thư viện/JVM/native code tạo ra. **Key handle không nhất thiết chứa raw key bytes**: một handle tới khóa non-exportable trong HSM có thể chỉ là tham chiếu. Vì vậy, trước khi nói “khóa nằm trong bộ nhớ”, phải phân biệt **raw material**, **object chứa material** và **tham chiếu tới material nằm ở ranh giới khác**.

Trong chương **Key storage** thuộc mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này kết nối bảo vệ key material trong RAM với vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**; đồng thời liên hệ KMS/HSM, envelope encryption, AES-GCM, chữ ký số, HMAC, KDF, kiểm soát truy cập và kiểm toán. Một ứng dụng được thiết kế tốt không chỉ hỏi **khóa được mã hóa ở đâu khi nghỉ**, mà còn hỏi **plaintext key ở đâu, do ai nắm giữ, sống bao lâu, có thể bị sao chép/ghi ra đâu và điều gì xảy ra khi quyền bị thu hồi**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **plaintext key bytes trong RAM**, **SecretKey/PrivateKey object**, **provider key handle**, **wrapped DEK** và **key ID**.
2. Mô tả đường đi của DEK từ KMS/HSM tới một crypto operation và xác định mọi nơi có thể giữ bản sao material.
3. Phân tích giới hạn của **zeroization bằng Arrays.fill**, garbage collection, Destroyable, direct buffer và các kỹ thuật khóa trang bộ nhớ.
4. Xây dựng giới hạn **scope, lifetime, TTL, cache size, đồng thời, tenant và key version** cho material trong RAM.
5. Thiết kế quy trình **load → authorize → use → release** và xử lý lỗi, KMS outage, rotation/revocation mà không vô tình giữ khóa quá lâu.
6. Viết ví dụ **Java 17** dùng AES-GCM và secret ngắn hạn, có AAD/nonce, close/expiry, không log bí mật và kiểm thử thao tác trái phép.
7. Đề xuất kiểm soát **heap dump, core dump, swap, snapshot, telemetry, crash report, container/host access**, cùng audit và incident response.

## 2. Định nghĩa chính xác: Thứ gì đang ở trong RAM?

### 2.1. Ba dạng dễ bị nhầm

| Dạng | Ví dụ | Khóa có thật sự nằm trong tiến trình? | Ý nghĩa bảo mật |
|---|---|---|---|
| **Raw key bytes** | byte[] gồm 32 byte AES-256, HMAC secret bytes | **Có**, trong ít nhất một vùng nhớ của tiến trình | Có thể bị copy, dump, serialize và dùng offline |
| **Key object chứa material** | SecretKeySpec, một số implementation của SecretKey/PrivateKey | **Có thể có**, tùy provider | Object có thể giữ bản sao, không mặc nhiên zeroizable |
| **Opaque/non-exportable handle** | Provider token liên kết HSM partition hoặc KMS resource | **Không nhất thiết**; có thể chỉ là ID/handle | Giảm raw-key exposure nhưng caller vẫn có thể lạm dụng quyền crypto |

Thêm hai đối tượng cần phân biệt:

- **Wrapped/encrypted key:** DEK được bọc dưới KEK, lưu ở database hoặc storage. Nó không phải plaintext DEK. Tuy nhiên muốn mở bằng KMS cần **Unwrap/Decrypt authorization**, và output có thể trở thành raw key trong RAM.
- **Key identifier và metadata:** key ID, version, owner, purpose, state, provider path; chúng thường không phải secret, nhưng phải có **tính toàn vẹn, phạm vi tenant và khả năng resolve đúng version**.

**Một biến đặt tên aesKey không chứng minh key material nằm trong vùng an toàn**, và một Java object implementing SecretKey không chứng minh khóa non-exportable. Thuộc tính quan trọng là **đường đi thực tế của bytes và hợp đồng provider**.

### 2.2. Dữ liệu nào dễ xuất hiện cạnh khóa?

Một phép giải mã có thể đưa vào memory:

~~~text
Ciphertext + nonce + tag + AAD
          |
          v
Wrapped DEK -- KMS Decrypt/Unwrap --> Plaintext DEK
                                     |
                                     v
                              SecretKey / Cipher
                                     |
                                     v
                                   Plaintext
~~~

Ngoài plaintext DEK, **plaintext, AAD chứa metadata nhạy cảm, PRK/OKM dẫn xuất, MAC state, nonce counter, token hoặc private-key intermediate** cũng có thể xuất hiện trong heap/native memory. **Bảo vệ raw key không thay thế chính sách bảo vệ plaintext**.

### 2.3. Nơi một key có thể hiện diện

| Khu vực | Ví dụ | Rủi ro |
|---|---|---|
| **Java heap** | byte[], SecretKeySpec, cache object, một số provider objects | Heap dump, debugging, serialization, GC không xóa theo lịch |
| **Thread stack** | Local reference, primitive state, temporary arrays | Stack/native dump hoặc instrumentation; tuổi thọ không hoàn toàn do source code quyết định |
| **Native memory** | JCA/JCE native provider, OpenSSL/PKCS#11 bridge, direct buffer | Core dump, lỗi native, quản lý giải phóng ngoài GC |
| **CPU registers/cache** | Intermediate secrets khi phép toán chạy | Không thể kiểm soát trực tiếp bằng Arrays.fill; phụ thuộc nền tảng |
| **OS memory management** | Swap, hibernation, paging, compressed memory | Secret có thể bị ghi xuống storage hoặc snapshot |
| **VM/container snapshot** | Memory capture, live migration, core dump | Bản sao có thể tồn tại ngoài host đang chạy |
| **Debug/observability** | Java Flight Recorder, profiler, heap dump, APM breadcrumbs | Secret có thể đi tới hạ tầng telemetry hoặc support |
| **Remote component** | Crypto sidecar, secret agent, HSM firmware, remote KMS | Ranh giới tin cậy khác; cần đánh giá provider và network |

**Java heap, direct buffer và native memory không tạo ra ba mức “an toàn mặc định”.** Off-heap có thể giảm một số kiểu copy/GC pressure, nhưng **không tự chống memory dump, process compromise hay copy bởi native library**.

## 3. Threat model cho khóa nằm trong bộ nhớ

Không có một biện pháp duy nhất bảo vệ được mọi loại đối thủ. Cần phân biệt **kẻ tấn công có quyền gì**:

| Kẻ tấn công/khả năng | Có thể làm gì? | Biện pháp thường hữu ích | Giới hạn |
|---|---|---|---|
| Chỉ đọc **database ciphertext** | Lấy wrapped DEK, envelope metadata | KEK trong KMS/HSM, IAM, authenticated envelope | Nếu có Decrypt API quá rộng, vẫn có thể lấy plaintext |
| Đọc **file/backup** của ứng dụng | Lấy key file, dump, cấu hình, token | Không lưu plaintext key, disk/backup ACL, dump controls | Disk encryption không tự chặn process đã unlock |
| Có quyền **đọc heap/core dump** | Tìm key bytes, plaintext, session token | Giảm lifetime, khóa quyền dump, giới hạn snapshot | Best-effort wipe không chắc loại tất cả bản sao |
| Có quyền chạy mã trong **JVM** | Gọi crypto API, copy object, lấy key handles | Least privilege, sandbox/process isolation, kiểm soát dependency | Nếu tiến trình được cấp key bytes, RCE có thể lấy hoặc lạm dụng chúng |
| Có quyền **KMS Decrypt/Sign** | Dùng khóa theo quyền mà không biết raw material | IAM per principal/key/tenant/purpose, audit, limits | Non-exportable vẫn có thể thành decrypt/sign oracle |
| Kiểm soát **host/kernel/hypervisor** | Đọc memory, snapshot và điều khiển tiến trình | Host hardening, isolation, confidential computing khi phù hợp | Cần xem provider/threat model; không bảo đảm tuyệt đối |
| Có quyền **đổi metadata/alias** | Chọn sai key version/tenant hoặc policy | Authenticated metadata, key registry, signed change/audit | AEAD tag không thay thế authorization trước lookup |

Như vậy, **giữ DEK trong RAM thật ngắn** giảm thời gian phơi lộ nhưng **không thể bảo đảm chống lại một attacker đang thực thi mã trong chính tiến trình đúng lúc DEK được dùng**. Với mức nhạy cảm cao, một lựa chọn khác là **không xuất key material**, đưa operation vào HSM/KMS hoặc crypto service có ranh giới tin cậy mạnh hơn, chấp nhận trade-off về latency, throughput, tính năng và độ sẵn sàng.

## 4. Vòng đời cụ thể của một in-memory key

~~~mermaid
flowchart TD
    A["Key material sinh hoặc được unwrap"] --> B["Authorize principal, tenant, purpose, key version"]
    B --> C["Đưa material vào crypto boundary được chấp thuận"]
    C --> D["Giới hạn owner, TTL, số bản sao, cache/lease"]
    D --> E["Encrypt/Decrypt/Sign/MAC/DeriveKey theo policy"]
    E --> F{"Còn operation hợp lệ trong lifetime?"}
    F -->|"Có"| E
    F -->|"Không"| G["Ngừng cho truy cập mới, đóng lease"]
    G --> H["Cleanup best effort + drop references"]
    H --> I["Audit usage, expiry, result và lifecycle state"]
~~~

### 4.1. Acquire: Sinh hoặc lấy khóa

Các phương án thường gặp:

1. **KeyGenerator trong JVM:** provider tạo secret AES/HMAC để local crypto, có thể trả SecretKey object trong process. Cần kiểm tra provider, thuật toán, key size, nguồn CSPRNG và khả năng xuất.
2. **KMS GenerateDataKey hoặc Decrypt/Unwrap:** KMS giữ KEK, trả plaintext DEK cho caller được phép và bản wrapped DEK để lưu. **Phải coi output plaintext là secret** từ thời điểm nhận tới khi kết thúc.
3. **PKCS#11/HSM Key handle:** operation được thực thi bằng handle; có thể không có raw private/secret key trong JVM. Cần phân biệt handle lifetime với lifetime của material ở HSM.
4. **HKDF từ root secret:** process hoặc provider có thể có **IKM/PRK/OKM**. Nếu root/PRK có mặt trong RAM, phạm vi ảnh hưởng có thể lớn hơn một DEK đơn lẻ.
5. **TLS/key agreement:** ephemeral private key và session traffic secret do giao thức/tầng TLS quản lý; ứng dụng không nên tự đọc hoặc persist nếu không cần.

**Không dùng java.util.Random, ThreadLocalRandom, timestamp hoặc seed cố định để sinh cryptographic key.** Với Java, ưu tiên API JCA/JCE và provider được tổ chức chấp thuận; với KMS/HSM, làm đúng contract của provider.

### 4.2. Use: Phạm vi tối thiểu

Lý tưởng là raw DEK chỉ xuất hiện trong một **vùng xử lý dữ liệu đã được ủy quyền**, không trả DEK qua API nghiệp vụ, không cho controller/web layer serialize nó và không lưu nó vào đối tượng session người dùng. Tách:

- **Authorization layer:** xác thực caller, tenant, resource, purpose và trạng thái khóa.
- **Key resolution layer:** resolve key ID/version qua registry đáng tin, không theo alias động cho dữ liệu cũ.
- **Crypto layer:** nhận/unwrap key và thực hiện thuật toán được phép.
- **Audit layer:** ghi actor/keyRef/version/operation/outcome, **không ghi secret**.

**Tính toàn vẹn và phân quyền** phải được kiểm tra trước khi sử dụng material. Nếu một tenant có thể đưa keyId của tenant khác vào request và service dùng KMS role đủ rộng để Decrypt, đó là lỗi *confused deputy*; TTL thấp không sửa lỗi này.

### 4.3. Release: Hết tham chiếu khác với xóa byte

Trong ngôn ngữ quản lý bộ nhớ, **giải phóng reference, zeroization, garbage collection và crypto-erasure là bốn khái niệm khác nhau**:

| Hành động | Điều thường đạt được | Điều không bảo đảm |
|---|---|---|
| Gán tham chiếu bằng null / kết thúc scope | Đối tượng có thể được GC khi không còn tham chiếu | Byte key được xóa ngay |
| **Arrays.fill(byte[], 0)** | Ghi đè chính mảng do code giữ ở thời điểm gọi | Các bản copy do SecretKeySpec/Cipher/provider, snapshot, dump cũ |
| Gọi **Destroyable.destroy()** nếu implementation hỗ trợ | Có thể kích hoạt quy trình destroy theo provider contract | Mọi implementation xóa sạch bộ nhớ hoặc ngăn mọi copy |
| **GC / System.gc()** | JVM có thể thu hồi object theo chính sách runtime | Thời điểm, zeroization và xóa các vùng nhớ cũ |
| **KMS Disable/DestroyKey** | Thay đổi khả năng dùng material trong ranh giới KMS | Xóa DEK/private key đã export, cache JVM hoặc backup ngoài phạm vi |
| Kết thúc process / restart container | Xóa quyền truy cập sống tới bộ nhớ process trong điều kiện vận hành | Xóa swap, core dump, snapshot và copied secrets đã tồn tại |

**Không quảng cáo “secure memory wipe” tuyệt đối trong Java thuần chỉ nhờ finally + Arrays.fill.** Việc làm sạch có ích để giảm lifetime của buffer gốc, nhưng phải kết hợp hạn chế bản sao, kiểm soát dump/host, provider semantics và quyền truy cập.

## 5. Java/JCA: SecretKey, SecretKeySpec và provider handles

### 5.1. SecretKey không có nghĩa tự xóa được

~~~java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);
SecretKey key = generator.generateKey();
// Dùng qua Cipher theo provider và policy.
~~~

Ở đây ứng dụng cầm **một Java SecretKey object**. Một số provider có thể lưu bytes trong JVM; số khác trả handle tới phần cứng/crypto module. **Không được suy từ class/interface rằng key non-exportable hoặc hỗ trợ destroy**. Đặc biệt, đừng gọi **getEncoded()** chỉ để xem khóa có “an toàn” không: với provider non-exportable nó có thể trả null, còn với khóa có thể xuất thì thao tác đó tạo **thêm bản sao key bytes**.

### 5.2. SecretKeySpec sao chép bytes

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.spec.SecretKeySpec;

byte[] rawDek = new byte[32];
new SecureRandom().nextBytes(rawDek);
try {
    SecretKeySpec key = new SecretKeySpec(rawDek, "AES");
    // SecretKeySpec giữ một bản sao của vùng bytes được truyền vào.
    // Những phép toán với key có thể tạo bản copy khác ở provider.
} finally {
    Arrays.fill(rawDek, (byte) 0);
}
~~~

**Arrays.fill(rawDek, 0)** giúp xử lý mảng gốc, nhưng **không xóa bản copy trong SecretKeySpec**. Do đó không thể nói key đã bị hủy hoàn toàn chỉ vì rawDek trở thành toàn byte 0. Để giảm rủi ro, ưu tiên **key handle/crypto provider hỗ trợ vòng đời rõ ràng**, thời gian giữ object ngắn và không lan truyền đối tượng chứa secret qua nhiều lớp ứng dụng.

### 5.3. Heap, off-heap và native code

- **Heap object:** dễ quản lý logic nhưng chịu rủi ro heap dumps và copy do API/JVM.
- **Direct ByteBuffer/off-heap:** có thể tránh một số bản copy và cho phép ghi đè buffer do ứng dụng kiểm soát, nhưng **không tự có mlock/zeroization**, và provider có thể sao chép vào vùng khác.
- **Native secure allocator:** có thể hỗ trợ locked pages, explicit zeroization hoặc page protections trên một nền tảng cụ thể, nhưng cần đánh giá thư viện, quyền OS, giới hạn bộ nhớ và JNI lifecycle.
- **HSM/KMS handle:** giúp material không đi qua memory ứng dụng trong những operation được provider hỗ trợ; bản thân **handle/session credential** vẫn là capability phải bảo vệ.

**Mã hóa secret ngay trong RAM bằng một key khác nằm cùng tiến trình** có thể giảm một số kiểu exposure khi không dùng, nhưng không phải giải pháp tuyệt đối trước RCE/process compromise: chương trình vẫn phải có cách mở secret và đối thủ có thể lợi dụng thao tác đó. Nếu dùng mô hình này, phải xác định rõ threat model và vị trí master/unwrap key.

## 6. KMS/HSM và envelope encryption: Plaintext DEK xuất hiện khi nào?

~~~mermaid
sequenceDiagram
    participant App as Java crypto service
    participant KMS as KMS/HSM giữ KEK
    participant DB as Database/Object storage
    App->>KMS: GenerateDataKey / Unwrap theo keyId và policy
    KMS-->>App: Plaintext DEK (nhạy cảm) + wrapped DEK
    App->>App: AES-GCM Encrypt/Decrypt dùng DEK trong RAM
    App->>DB: Ciphertext, nonce, tag, wrapped DEK, keyRef
    Note over App: Chấm dứt lease/cache và cleanup best effort
    Note over KMS: KEK không cần xuất dạng bản rõ tới App
    App->>DB: Đọc bản ghi lịch sử
    DB-->>App: Envelope, wrapped DEK, keyId/version
    App->>KMS: Unwrap với đúng key/version/context và IAM
    KMS-->>App: Plaintext DEK theo policy
    App->>App: Verify GCM tag trước khi dùng plaintext
~~~

Đây là **một pattern kiến trúc**, không phải hợp đồng của mọi nhà cung cấp: có sản phẩm cho caller nhận plaintext DEK, có sản phẩm cho phép thực hiện mã hóa trong module mà không xuất DEK, và một số KMS không có API GenerateDataKey. Phải kiểm tra **đúng API, nơi key material hiện diện, phiên bản khóa, điều kiện xuất và backup/recovery** của provider.

### 6.1. Tại sao wrapped DEK có thể lưu cạnh ciphertext?

DEK được wrap dưới KEK độc lập; database có thể giữ:

~~~json
{
  "formatVersion": 1,
  "tenantId": "tenant-42",
  "recordId": "customer-123",
  "contentAlgorithm": "AES-256-GCM",
  "wrappingKeyRef": {
    "keyId": "tenant-42-kek",
    "version": "v3"
  },
  "wrappedDek": "<BASE64_WRAPPED_DEK>",
  "nonce": "<BASE64_96_BIT_NONCE>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_AND_TAG>"
}
~~~

Các trường trong dấu ngoặc nhọn là **placeholder**, không phải giá trị khóa hay bản mã thật. **Wrapped DEK là ciphertext của khóa**, không phải DEK bản rõ. Mức an toàn phụ thuộc vào KEK, cách wrap, IAM/Unwrap permission, metadata integrity, tenant isolation và khả năng bảo vệ plaintext DEK khi trả về ứng dụng.

### 6.2. Key ID/version, AAD và quyền truy cập

Một schema AAD có thể ràng buộc **tenant, record, algorithm, content key ID/version**, nhưng AAD **không thay thế IAM**. Ngay cả khi tag GCM phát hiện metadata bị sửa, ứng dụng vẫn phải **kiểm tra quyền đối với record/tenant trước khi yêu cầu KMS Unwrap**.

Nếu **wrapping key version** được đưa vào content AAD, việc **rewrap DEK từ KEK-v3 sang v4** mà chỉ sửa version có thể làm **GCM tag không khớp**. Vì vậy thiết kế phải tách rõ metadata của **content encryption** và metadata của **key wrapping**, cùng cách bảo vệ integrity của mỗi lớp.

### 6.3. KEK không có mặt trong JVM vẫn chưa đủ

Giữ KEK non-exportable trong HSM có lợi vì **blast radius của host compromise** có thể bị giới hạn ở những DEK mà workload đã được phép unwrap và những API còn hoạt động. Nhưng ứng dụng vẫn có khả năng bị lạm dụng làm **decryption oracle** nếu KMS Decrypt grants quá rộng; local DEK còn tồn tại có thể tiếp tục giải mã offline. Cần giới hạn:

1. IAM theo **workload identity, key ID/version, tenant, purpose và context**.
2. Số lượng DEK một workload có thể unwrap theo scope và rate limits nếu phù hợp.
3. Key cache TTL/size và nơi raw DEK được phép đi tới.
4. Application-level authorization đối với record, không chỉ KMS key permission.
5. Audit KMS Unwrap và các operation local có metadata phù hợp, không ghi key bytes.

## 7. Key caching: Tối ưu hiệu năng nhưng không kéo dài rủi ro vô hạn

Giải mã bằng một DEK qua KMS cho mọi request có thể tốn latency, chi phí và phụ thuộc mạng. Một số ứng dụng cache **plaintext DEK** hoặc đối tượng SecretKey để tái sử dụng khi dữ liệu cần đọc nhiều lần. **Cache không sai tuyệt đối**, nhưng nó là một **storage location chứa secret**, phải được quản trị như key material, không phải cache nghiệp vụ thông thường.

### 7.1. Chọn mô hình sử dụng

| Mô hình | Ưu điểm | Nhược điểm |
|---|---|---|
| **Không cache DEK bản rõ** | Lifetime ngắn, ít material đồng thời trong RAM | Tăng KMS unwrap calls, latency/chi phí, KMS outage làm đọc khó |
| **Cache DEK theo request/batch nhỏ** | Giảm unwrap khi xử lý nhiều phần cùng key | Exposure trong thời gian batch; cần cleanup khi request kết thúc |
| **Cache DEK có TTL và giới hạn số phần tử** | Hiệu năng tốt hơn cho hot data | Plaintext key ở RAM lâu hơn; cần tenant/key-version isolation |
| **Crypto service/HSM thực hiện operation** | Không cần trả raw secret cho business JVM khi được hỗ trợ | API limitations, throughput, latency, cost và HA |
| **Cache wrapped DEK/metadata** | Không giữ raw DEK trực tiếp | Mỗi lần sử dụng vẫn cần unwrap; scope và integrity của metadata phải đúng |

**Đừng tối ưu cache chỉ bằng hit rate.** Nên đánh giá **số raw key đang tồn tại**, lifetime lớn nhất, tổng tenant/key versions trong một process, hiệu quả revoke, tỷ lệ miss và chi phí recovery.

### 7.2. Cache key phải được key bởi những trường nào?

Một lỗi nghiêm trọng là cache theo **key alias** hoặc **tenantId đơn lẻ**:

~~~text
SAI:
cache["current-data-key"] = plaintext DEK

KẾT QUẢ:
  alias chuyển sang version mới
  cache vẫn giữ DEK version cũ
  encryption có thể dùng sai version hoặc metadata
~~~

Khóa cache nên có scope không nhập nhằng, ví dụ:

~~~text
CacheKey(
  providerAccount,
  regionOrPartition,
  tenantId,
  immutableKeyId,
  keyVersion,
  encryptionContextOrPurpose,
  wrappedDekFingerprintOrRecordReference
)
~~~

**Không dùng fingerprint của secret raw key làm public cache ID** nếu chưa có đánh giá bảo mật; có thể dùng **record ID của wrapped DEK**, phiên bản và những metadata đã được xác thực. Không dùng cùng một DEK được unwrap cho tenant khác chỉ vì hai bên có alias trùng tên.

### 7.3. TTL, capacity và lease

Một cache policy cần quy định:

- **TTL tối đa** tính theo thời gian từ khi unwrap/sinh hoặc từ khi cấp lease, không kéo dài vô hạn chỉ vì có lượt đọc.
- **Maximum entries/bytes** và số DEK plaintext đồng thời trên một JVM/host.
- **Không chia sẻ vượt phạm vi tenant**, environment, purpose và key version.
- **Eviction/cleanup** best effort; xóa reference không đủ chứng minh bytes đã bị xóa khỏi heap.
- **Concurrency:** close/evict không được chạy xen giữa thao tác mã hóa đang sử dụng buffer mutable theo cách gây lỗi hoặc mất an toàn.
- **In-flight operation:** khi key bị revoked phải định nghĩa liệu request đã bắt đầu được hoàn tất hay buộc dừng.
- **KMS outage:** không tự tăng TTL vô hạn hoặc chuyển sang khóa hardcode; mức chấp nhận stale lease phải được quyết định trước.
- **Observability:** metric về số lease/cache entries/expired/denied không được chứa key bytes.

### 7.4. Khi nào cache sai mục tiêu?

Đối với **private signing key non-exportable**, việc tạo local PEM cache có thể phá chính sách sử dụng HSM. Nếu KMS/HSM hỗ trợ Sign bằng key handle, **cache handle/session (theo contract) khác hoàn toàn cache raw private key**.

Đối với **KDF root** bảo vệ mọi tenant, cache root trong mỗi microservice mở rộng rất lớn blast radius. Có thể tốt hơn khi giữ root tại một provider và chỉ trả **derived key có phạm vi hẹp**, hoặc thực hiện derivation trong crypto boundary.

Đối với **AES-GCM**, cache DEK đồng nghĩa nhiều operation với cùng key. Phải quản lý **nonce uniqueness trên toàn bộ các instance cùng DEK** và giới hạn số encrypt, không chỉ đặt TTL cho cache.

## 8. Memory hygiene: Giảm số bản sao và xử lý lifetime

### 8.1. Các quy tắc thực hành trong Java

1. **Không nhét raw key vào String** nếu có thể tránh: String immutable và vòng đời không dễ kiểm soát.
2. **Không đưa key vào log/toString/JSON/metrics**: đặc biệt tránh Base64(keyBytes) trong error/debug.
3. **Không gọi getEncoded tùy tiện** trên SecretKey/PrivateKey vì có thể tạo thêm bản sao raw material.
4. **Tránh generic cache/object graph giữ tham chiếu lâu dài**: session attributes, singleton, request logger, tracing context.
5. **Dùng try/finally hoặc try-with-resources** khi sở hữu buffer mutable; zeroize best effort và drop references.
6. **Không giả định byte[] là immutable**: nếu truyền mảng qua nhiều hàm, caller có thể sửa hoặc giữ bản sao; cần ownership rõ ràng và tránh sharing.
7. **Không xem Destroyable là lời bảo đảm chung**: kiểm tra provider implementation và behavior được tài liệu hóa.
8. **Tách public metadata khỏi material**: log key ID/version, owner, purpose, operation thay vì raw key.
9. **Kiểm tra thư viện crypto/JNI**: một provider có thể sao chép key trong Cipher/Mac state và native allocations.
10. **Thử chính sách crash/dump** trong vận hành, không chỉ kiểm tra source code có Arrays.fill.

### 8.2. Tại sao zeroization trong managed runtime khó?

GC, JIT optimizer, copy-on-write, allocation và native boundary khiến ứng dụng **không sở hữu mọi vị trí lưu key bytes**. Ví dụ:

~~~java
byte[] secret = getPlaintextDekFromApprovedProvider();
byte[] copy = secret.clone();
try {
    // Crypto operation dùng secret hoặc copy.
} finally {
    java.util.Arrays.fill(secret, (byte) 0);
}
// Biến copy vẫn giữ bản key bytes nếu chưa được wipe.
~~~

Ngay cả khi code xóa cả hai mảng, provider có thể có thêm bản sao. Vì thế:

- **Giảm số lần materialization/copy** trước, thay vì chỉ tăng số lần gọi wipe.
- **Giới hạn thời gian material sống** và bề mặt truy cập.
- **Dùng provider có security contract rõ** nếu cần bảo đảm mạnh hơn Java thuần.
- **Không tuyên bố cryptographic erasure của memory** từ việc gọi một phương thức trên Java object.

**Zeroization best effort vẫn hữu ích:** nó giảm khả năng tìm secret trong buffer gốc về sau và có thể được dùng như một defense-in-depth. Điểm cần tránh là nâng nó thành bằng chứng mọi bản sao đã biến mất.

### 8.3. Không sao chép key khi chuyển giữa các tầng

Một API thiết kế kém:

~~~text
Controller
   -> KeyService.getRawDekAsBase64String()
   -> DTO/JSON serializer
   -> BusinessService
   -> CryptoService
   -> audit interceptor
~~~

Ở đây key material có thể đi qua nhiều object/loggers không cần thiết. Một thiết kế tốt hơn:

~~~text
Controller (không nhận DEK)
   -> Business authorization
   -> CryptoService.performAuthorizedOperation(keyRef, recordRef, input)
        -> KMS/KeyStore acquire bên trong crypto boundary
        -> Cipher/Mac/Sign trong phạm vi được phép
        -> cleanup best effort
   -> Controller nhận ciphertext/plaintext theo quyền
~~~

Nếu ứng dụng cần trả plaintext cho caller, **plaintext vẫn nhạy cảm** và cần quyền/ngữ cảnh, TLS, logging policy và response handling riêng. Crypto boundary chỉ giúp giảm phạm vi xuất raw key, không loại bỏ mọi rủi ro dữ liệu.

## 9. Hệ điều hành, container và quan sát hệ thống

### 9.1. Heap dump/core dump

Heap dump là một công cụ debug mạnh, đồng thời có thể chứa **DEK, HMAC secret, private-key object, token, plaintext**, tùy tiến trình và thời điểm. Một số nguồn tạo dump:

- Công cụ quản trị JVM/profiler/debugger có quyền attach.
- Tự động tạo dump khi **OutOfMemoryError** hoặc process crash.
- APM/support agent hoặc Java diagnostic command.
- Snapshot VM hoặc core dump của OS.
- Phương thức thu thập memory dành cho incident response.

Không bật các cơ chế này trên hệ thống giữ raw secret mà không có **đánh giá rủi ro, quyền thu thập, nơi ghi, mã hóa, retention, audit và quy trình xử lý**. Khi cần dump để điều tra, coi dump là **tài sản có độ nhạy cao**, giới hạn người xem và không upload lên ticket công khai.

**Không nên xử lý rủi ro bằng cách tự động xóa mọi log/dump đang liên quan đến sự cố trước khi có điều tra có thẩm quyền**. Cần cân bằng bảo toàn chứng cứ và bảo vệ bí mật, đồng thời rotate material nếu có nguy cơ bị lộ.

### 9.2. Swap, hibernation, snapshot và core files

Nội dung RAM có thể bị OS đưa xuống **swap**, **hibernation image**, **VM snapshot** hoặc bản sao memory khi live migration. Các kiểm soát cần xét:

- Mã hóa và ACL với swap/hibernation/snapshot theo khả năng nền tảng.
- Không cấp quyền đọc dump/snapshot rộng hơn quyền đọc khóa.
- Kiểm soát backup, retention và export của VM/container images có memory.
- Quản lý crash report và thư mục lưu core files.
- Khi có yêu cầu assurance cao, đánh giá **memory locking** hoặc cơ chế confidential computing/secure enclave theo sản phẩm và threat model.

**mlock hoặc lock-pages chỉ giảm nguy cơ paging một vùng nhớ cụ thể**, không tự chống RCE, hypervisor compromise, heap copy hoặc debug dump. Trong Java, rất khó bảo đảm mọi vùng chứa key đều được khóa; đừng coi lock-pages là biện pháp hoàn chỉnh.

### 9.3. Container isolation và host compromise

Container không tự tạo một ranh giới mật mã ngang HSM. Nếu workload bị RCE hoặc node bị truy cập đặc quyền, in-memory key có thể bị đọc hoặc thao tác từ tiến trình. Cần:

1. Chạy workload **non-root**, quyền OS tối thiểu và filesystem/network policy phù hợp.
2. Hạn chế **ptrace, process debugging, privileged containers, hostPID, volume mounts** và quyền truy cập runtime.
3. Bảo vệ **service-account credentials** dùng gọi KMS; một attacker có token hợp lệ có thể yêu cầu cấp thêm DEK.
4. Tách **tenant/workload rủi ro khác nhau** khi cần; không cache DEK của mọi tenant trong một singleton không có scope.
5. Kiểm soát **CI/CD, dependency và images** để giảm đường RCE/supply chain.
6. Giám sát KMS usage bất thường và thao tác xuất/unwrap, nhưng không ghi raw key.

**Memory encryption trên host hoặc máy ảo nếu có** chỉ giải quyết những threat cụ thể theo kiến trúc; không có công nghệ nào tự bảo đảm rằng một ứng dụng độc hại đã được cấp quyền Encrypt/Decrypt không thể lạm dụng key handle.

## 10. Tác động tới các loại khóa khác nhau

### 10.1. AES-GCM DEK

DEK raw trong JVM thường được dùng nhiều lần để Encrypt/Decrypt. **Nonce AES-GCM cần không trùng với cùng DEK**, kể cả khi có nhiều replica, restart, retry, snapshot hoặc reactivation. Một nonce 96 bit ngẫu nhiên từ CSPRNG có **xác suất collision**, không bảo đảm zero collision nếu số lần gọi quá lớn.

Khi cache DEK cùng key version, **không được reset nonce counter** sau restart nếu dùng nonce cấu trúc, không tự cấp lại cùng prefix/counter cho nhiều instance. Nếu dùng nonce ngẫu nhiên, phải có **invocation limit** và kế hoạch rotate theo thiết kế/khuyến nghị phù hợp.

### 10.2. HMAC key

HMAC cần secret cả để GenerateMac lẫn VerifyMac. Đưa HMAC key vào RAM của nhiều service làm tăng số nơi có khả năng tạo MAC hợp lệ. Nếu một người hoặc service biết HMAC key, họ có thể **tạo tag**; HMAC không cho non-repudiation như chữ ký số bất đối xứng. Cần hạn chế purpose, phân phối secret, key version và anti-replay ở tầng giao thức.

Khi rotate HMAC key, verifier có thể cần chấp nhận tag cũ trong một khoảng theo policy, nhưng phải xác định **expiry, key ID/version và ngày dừng dùng key cũ**. Không dùng một HMAC key dài hạn làm secret “chung cho mọi dịch vụ”.

### 10.3. Private signing key

Một private key dùng **Ed25519, ECDSA hoặc RSA-PSS** trong JVM có thể là đối tượng chứa key material hoặc provider key handle. Với key ký có giá trị cao, ưu tiên **Sign trong HSM/KMS** khi đáp ứng thuật toán và yêu cầu vận hành, tránh serialize key ra PEM để “cache hiệu năng”.

Thu hồi quyền Sign ở KMS **không vô hiệu hóa private key đã được xuất**. Nếu raw private key bị lộ, cần rotate/revoke trust/JWKS/certificate theo giao thức, đánh giá chữ ký và token có thể bị giả. Một chữ ký lịch sử vẫn có thể **Verify toán học** bằng public key cũ; việc **chấp nhận** nó phụ thuộc trạng thái trust và thời điểm.

### 10.4. HKDF root, PRK và derived keys

HKDF có thể dẫn xuất nhiều derived keys từ **IKM/root** và thông tin salt/info. Đưa root hoặc PRK vào process làm tăng phạm vi hậu quả hơn so với chỉ đưa một derived key cho **tenant + purpose** cụ thể. Một thay đổi nhãn info không sửa được việc **root secret bị lộ**. Nếu root còn tồn tại, một derived key có thể được tái tạo; xóa OKM cached không bảo đảm crypto-erasure.

### 10.5. TLS, ECDH và session secrets

Giao thức TLS/KeyAgreement có thể tạo ephemeral private keys và traffic secrets. Khi session secret đã được thiết lập, vô hiệu hóa long-term signing/key agreement credential **không nhất thiết kết thúc mọi phiên đã có**. Khả năng tiếp tục sử dụng phụ thuộc giao thức, session resumption, TTL và cách quản lý phiên. Không tự lấy TLS traffic secret từ provider chỉ để đưa vào application cache.

### 10.6. Passwords và password-derived keys

Password do con người chọn thường entropy thấp; không biến nó thành key mạnh chỉ vì dùng **SHA-256** hoặc HKDF. Khi cần lưu password verifier, dùng password hashing theo policy (ví dụ **Argon2id**, scrypt hoặc PBKDF2 phù hợp), lưu salt/tham số và bảo vệ pepper riêng nếu dùng. Password có thể đi qua RAM khi xác thực; giảm lifetime/plaintext logging vẫn quan trọng, nhưng nó là bài toán khác với lưu raw AES-256 DEK được sinh từ CSPRNG.

## 11. Rotation và revocation: DEK đã vào RAM thì sao?

### 11.1. KMS key state không điều khiển local bytes

Giả sử KMS KEK-v3 đã chuyển sang **SUSPENDED**:

~~~text
T1: App unwrap DEK-v7 qua KEK-v3, lưu DEK-v7 trong RAM
T2: Security suspend KEK-v3 ở KMS
T3: App vẫn có DEK-v7, Cipher.doFinal có thể chạy offline
~~~

Vì vậy **suspend KEK không đủ để chặn DEK cached**. Cần quyết định ranh giới:

- **Key-use lease:** kiểm tra trạng thái/expiry ở crypto gateway và định nghĩa thời gian tối đa có thể stale.
- **Local cache invalidation:** thông báo rotation/revocation tới instance theo key version và xử lý race.
- **Workload/session control:** thu hồi quyền điều khiển process, terminate instance hoặc cô lập ứng dụng nếu sự cố nghiêm trọng.
- **Provider enforcement:** với key non-exportable, chặn Sign/Decrypt ngay tại nơi key material tồn tại.
- **Audit:** ghi mốc sự kiện, operation có thể đã hoàn thành sau suspend và những phiên chưa nhận state.

### 11.2. KEK rotation không tự đổi DEK

~~~text
Payload = AES-GCM(DEK-7, plaintext, nonce, AAD)
WrappedDEK-old = Wrap(KEK-v3, DEK-7)

Khi KEK rotation:
WrappedDEK-new = Wrap(KEK-v4, DEK-7)
Payload có thể giữ nguyên nếu content AAD và protocol cho phép.

Nếu DEK-7 bị lộ:
Tạo DEK-8, re-encrypt dữ liệu bị ảnh hưởng và điều tra.
~~~

Nếu **DEK-7 đã bị lộ**, rewrap bằng KEK-v4 không khiến DEK-7 trở lại bí mật. Nếu **KEK-v3 lộ**, phải khoanh vùng tập wrapped DEKs và nguy cơ ciphertext, chứ không chỉ đổi alias. Với KMS/HSM, cần xem chính sách **retire/destroy**, trạng thái backup và khả năng mở dữ liệu lịch sử.

### 11.3. Chính sách khi KMS bị outage

Không nên tự chuyển từ KMS sang **hardcoded plaintext key** hoặc tự lưu KEK raw trên disk để “duy trì availability”. Cần thiết kế trước:

- **Có chấp nhận read/decrypt trong thời gian cache lease hợp lệ không?** Nếu có, giới hạn rõ TTL và loại dữ liệu.
- **Có cho Encrypt mới không?** Tùy khả năng cấp nonce, key state và policy; không mặc định continue mãi.
- **Khi cache expired:** fail closed hoặc đường DR được phê duyệt, không âm thầm kéo dài TTL.
- **Làm sao recovery:** region/provider failover, secure backup, owner/quorum, key ID/version và restore tests.

Đối với dữ liệu nhạy cảm, **availability** phải được cân bằng với rủi ro giữ plaintext key trong memory. Mục tiêu RTO/RPO và security policy cần thống nhất trước khi xảy ra sự cố.

## 12. Java 17: Demo một DEK lease ngắn hạn cho AES-GCM

Ví dụ sau mô hình hóa **một raw DEK được sở hữu bởi một lease**, có TTL, tenant, key ID/version và phương thức close. Ứng dụng không trả key bytes ra caller, chỉ cung cấp **Encrypt/Decrypt** trên dữ liệu được cho phép. Đây là mô hình học thuật với key material sinh từ **SecureRandom trong JVM** để có thể chạy độc lập, **không phải một KMS/HSM integration**.

Các nguyên tắc được minh họa:

- **Nguồn key:** 32 byte từ SecureRandom cho AES-256, không dùng java.util.Random.
- **Ownership:** tạo một bản sao private trong lease, xóa best effort buffer gốc ngay khi bàn giao.
- **Scope:** lease chỉ phục vụ một tenant và một key ID/version bất biến.
- **Lifetime:** chỉ được gọi operation trước hạn TTL và trước khi close.
- **Thread safety:** synchronized ngăn close xen vào phần code dùng key bytes trong chính lease.
- **Crypto:** AES/GCM/NoPadding, nonce 96 bit mới cho mỗi lần Encrypt, tag 128 bit và AAD có length-prefix.
- **Envelope:** nonce, ciphertext và metadata được sao chép phòng việc caller sửa buffer ngoài ý muốn.
- **Denial/tamper:** chặn sai tenant, từ chối ciphertext sai authentication tag, và chặn dùng sau close.

**Giới hạn quan trọng:** code sẽ tạo **SecretKeySpec từ byte[] trong lease**; SecretKeySpec và provider **có thể tạo bản sao** mà close không xóa được. TTL trong ví dụ được **kiểm tra khi có request**, không phải một cơ chế tự động xóa khi không có request. Không dùng chính class này làm kho khóa production mà không có kiến trúc provider, policy và đánh giá đầy đủ.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Arrays;
import java.util.Objects;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class InMemoryKeyLifecycleDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int AES_KEY_BYTES = 32; // AES-256
    private static final int NONCE_BYTES = 12;   // 96-bit GCM nonce
    private static final int TAG_BITS = 128;
    private static final String ALGORITHM = "AES-256-GCM";

    // Envelope chỉ chứa metadata và ciphertext, KHÔNG chứa raw DEK.
    record Envelope(
            String tenantId,
            String recordId,
            String keyId,
            int keyVersion,
            byte[] nonce,
            byte[] ciphertextWithTag) {
        Envelope {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(recordId);
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(nonce);
            Objects.requireNonNull(ciphertextWithTag);
            nonce = nonce.clone();
            ciphertextWithTag = ciphertextWithTag.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertextWithTag() {
            return ciphertextWithTag.clone();
        }
    }

    private static void writeField(
            DataOutputStream out, String field) throws Exception {
        byte[] value = field.getBytes(StandardCharsets.UTF_8);
        out.writeInt(value.length);
        out.write(value);
    }

    // Canonical AAD: 1 format version + độ dài từng UTF-8 field.
    private static byte[] aad(
            String tenantId, String recordId, String keyId,
            int keyVersion) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(1);
            writeField(out, ALGORITHM);
            writeField(out, tenantId);
            writeField(out, recordId);
            writeField(out, keyId);
            out.writeInt(keyVersion);
        }
        return buffer.toByteArray();
    }

    static final class DekLease implements AutoCloseable {
        private final byte[] material;
        private final String keyId;
        private final int version;
        private final String tenantId;
        private final long expiresAtNanos;
        private boolean closed;

        DekLease(
                byte[] source,
                String keyId,
                int version,
                String tenantId,
                Duration ttl) {
            Objects.requireNonNull(source);
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(ttl);
            if (source.length != AES_KEY_BYTES || keyId.isBlank()
                    || tenantId.isBlank() || version < 1
                    || ttl.isZero() || ttl.isNegative()
                    || ttl.compareTo(Duration.ofMinutes(5)) > 0) {
                throw new IllegalArgumentException("Invalid DEK lease");
            }
            this.material = source.clone();
            this.keyId = keyId;
            this.version = version;
            this.tenantId = tenantId;
            this.expiresAtNanos = System.nanoTime() + ttl.toNanos();
        }

        private void requireLive() {
            if (closed) {
                throw new IllegalStateException("DEK lease closed");
            }
            if (System.nanoTime() - expiresAtNanos >= 0) {
                close();
                throw new IllegalStateException("DEK lease expired");
            }
        }

        private void requireTenant(String authenticatedTenant) {
            if (!tenantId.equals(authenticatedTenant)) {
                throw new SecurityException("Tenant is not authorized");
            }
        }

        synchronized Envelope encrypt(
                String authenticatedTenant,
                String recordId,
                byte[] plaintext) throws Exception {
            requireLive();
            requireTenant(authenticatedTenant);
            Objects.requireNonNull(plaintext);
            if (recordId == null || recordId.isBlank()) {
                throw new IllegalArgumentException("Invalid record");
            }

            byte[] nonce = new byte[NONCE_BYTES];
            RNG.nextBytes(nonce);

            // SecretKeySpec và Cipher có thể copy material.
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(material, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(
                    tenantId, recordId, keyId, version));
            byte[] ciphertextWithTag = cipher.doFinal(plaintext);
            return new Envelope(
                    tenantId, recordId, keyId, version,
                    nonce, ciphertextWithTag);
        }

        synchronized byte[] decrypt(
                String authenticatedTenant,
                String requestedRecordId,
                Envelope envelope) throws Exception {
            requireLive();
            requireTenant(authenticatedTenant);
            Objects.requireNonNull(envelope);
            if (!tenantId.equals(envelope.tenantId())
                    || !Objects.equals(
                            requestedRecordId, envelope.recordId())
                    || !keyId.equals(envelope.keyId())
                    || version != envelope.keyVersion()) {
                throw new SecurityException("Envelope scope mismatch");
            }

            byte[] nonce = envelope.nonce();
            byte[] ciphertextWithTag = envelope.ciphertextWithTag();
            if (nonce.length != NONCE_BYTES
                    || ciphertextWithTag.length < TAG_BITS / 8) {
                throw new IllegalArgumentException("Invalid GCM envelope");
            }

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(material, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(
                    envelope.tenantId(), envelope.recordId(),
                    envelope.keyId(), envelope.keyVersion()));
            // doFinal xác minh tag trước khi trả plaintext.
            return cipher.doFinal(ciphertextWithTag);
        }

        @Override
        public synchronized void close() {
            if (!closed) {
                // Chỉ xóa mảng sở hữu; KHÔNG bảo đảm xóa JCA copies.
                Arrays.fill(material, (byte) 0);
                closed = true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] raw = new byte[AES_KEY_BYTES];
        byte[] input = "Demo payload only".getBytes(
                StandardCharsets.UTF_8);
        RNG.nextBytes(raw);

        DekLease lease = null;
        try {
            lease = new DekLease(
                    raw, "customer-dek-v1", 1,
                    "tenant-42", Duration.ofSeconds(30));
            // Mảng raw ban đầu không còn cần sau khi lease nhận copy.
            Arrays.fill(raw, (byte) 0);

            try (DekLease active = lease) {
                Envelope encrypted = active.encrypt(
                        "tenant-42", "record-123", input);
                byte[] recovered = active.decrypt(
                        "tenant-42", "record-123", encrypted);
                try {
                    System.out.println(
                            "Round-trip verified: "
                            + Arrays.equals(input, recovered));
                } finally {
                    Arrays.fill(recovered, (byte) 0);
                }

                try {
                    active.decrypt(
                            "tenant-OTHER", "record-123", encrypted);
                    throw new AssertionError("Tenant isolation failed");
                } catch (SecurityException expected) {
                    System.out.println("Cross-tenant access denied");
                }

                byte[] tamperedBytes = encrypted.ciphertextWithTag();
                tamperedBytes[0] ^= 1; // Chỉ là ciphertext demo.
                Envelope tampered = new Envelope(
                        encrypted.tenantId(), encrypted.recordId(),
                        encrypted.keyId(), encrypted.keyVersion(),
                        encrypted.nonce(), tamperedBytes);
                try {
                    active.decrypt("tenant-42", "record-123", tampered);
                    throw new AssertionError("Tampered data accepted");
                } catch (AEADBadTagException expected) {
                    System.out.println("Tampered ciphertext rejected");
                }
            }

            try {
                lease.encrypt("tenant-42", "record-456", input);
                throw new AssertionError("Closed lease was reused");
            } catch (IllegalStateException expected) {
                System.out.println("Use after close denied");
            }
        } finally {
            if (lease != null) {
                lease.close();
            }
            Arrays.fill(raw, (byte) 0);
            Arrays.fill(input, (byte) 0);
        }
        // Không in key/DEK hoặc plaintext dữ liệu thật.
    }
}
~~~

Lưu thành **InMemoryKeyLifecycleDemo.java**, sau đó dùng JDK 17+:

~~~bash
javac InMemoryKeyLifecycleDemo.java
java InMemoryKeyLifecycleDemo
~~~

Kết quả logic kỳ vọng:

~~~text
Round-trip verified: true
Cross-tenant access denied
Tampered ciphertext rejected
Use after close denied
~~~

### 12.1. Vì sao thiết kế dùng lease?

Một **lease** mô tả quyền sở hữu object và thời hạn code **được phép dùng key material**. Dùng try-with-resources làm cho thời điểm close rõ trong source code; synchronized giảm một kiểu race giữa close và operation **trên cùng một lease**. Nếu caller cố tiếp tục dùng sau close, phương thức phải từ chối thay vì lặng lẽ mã hóa bằng buffer đã bị ghi đè.

Tuy nhiên lease chỉ kiểm soát **đối tượng này**. Nó không ngăn các nguồn khác giữ bản sao material, không thay thế **KMS IAM**, không bảo đảm GC/JIT/native cleanup, và không tự thu hồi một DEK đã được lưu trong object khác. Production thường cần thêm **provider key handle**, scope từ authenticated identity, cache eviction, monitoring và state checks.

### 12.2. Các giới hạn kỹ thuật cần nhận diện

1. **Không có KMS/HSM:** key raw được sinh trong JVM, không đáp ứng yêu cầu non-exportable của mọi hệ thống.
2. **Không bảo đảm zeroization tuyệt đối:** SecretKeySpec/Cipher có thể giữ bytes ở các bản sao ngoài mảng material.
3. **TTL chỉ được kiểm tra khi sử dụng:** nếu không có operation tiếp, object còn sống sẽ giữ material cho đến close/GC; production cần lifecycle quản trị thực.
4. **Không kiểm soát nonce toàn cụm:** mỗi encryption dùng random nonce 96 bit; production phải giới hạn số lần mã hóa với cùng DEK, theo dõi cross-instance/restart hoặc dùng chiến lược uniqueness được thiết kế.
5. **Không có IAM thật:** callerTenant được truyền vào bởi demo; trong ứng dụng phải lấy tenant từ danh tính/authorization đáng tin.
6. **Không có key state/cryptoperiod từ registry:** việc suspended/retired/compromised cần được kiểm tra trước từng operation theo contract và threat model.
7. **Không có wrapping/backup:** Envelope trong demo không chứa wrapped DEK. Bản demo không được lưu làm dữ liệu production vì **không có đường giải mã sau khi lease bị hủy**.
8. **Không có multi-region/cache invalidation:** một lease chỉ đại diện một object trong một JVM.
9. **Plaintext trong byte[] cũng nhạy cảm:** việc cleanup byte[] đầu vào của demo không chứng minh mọi bản sao String/provider đã biến mất.
10. **Thời hạn nanoTime phục vụ elapsed time:** không dùng nanoTime làm audit timestamp hoặc thay thế cryptoperiod/revocation theo thời gian tuyệt đối của control plane.
11. **Ciphertext bị sửa chỉ là test AEAD:** lỗi AEADBadTagException không chứng minh key ID/tenant đã được phân quyền trước KMS unwrap.
12. **Không có security QA/provider assurance:** phải đánh giá JVM/OS, key generation, KMS policy, host isolation, logging, backup và khôi phục.

Điểm quan trọng nhất của code không phải là thuật toán AES-GCM (đã có trong JCA), mà là **giới hạn nơi lưu raw key, quyền dùng, vòng đời object và điều kiện thất bại**. Một code sample không thể tự bảo đảm chống kẻ tấn công có quyền đọc/điều khiển toàn bộ tiến trình.

## 13. Kiểm thử in-memory key đúng cách

### 13.1. Contract tests cho key lifecycle

| Test case | Kết quả mong đợi | Giới hạn |
|---|---|---|
| Chỉ key đúng tenant/purpose được dùng | **ALLOW/DENY** đúng policy | Tenant phải đến từ identity đáng tin, không do HTTP body tự khai |
| Key có version sai so với envelope | **DENY** trước crypto operation | Key registry phải có reference không nhập nhằng |
| Dùng key sau khi lease close | **DENY** bằng lỗi rõ ràng | Không chứng minh mọi bản sao key đã bị wipe |
| Dùng sau TTL | **DENY** khi kiểm tra lifetime | Nếu không gọi gì, object có thể còn ở RAM đến cleanup |
| Close đồng thời với operation | Không mất an toàn trạng thái/đọc key bị wipe giữa chừng | Chỉ bảo vệ scope synchronization đã thiết kế |
| AES-GCM ciphertext hoặc AAD bị sửa | **Authentication failure** | AEAD không thay thế IAM và anti-replay |
| Gọi Encrypt với nonce strategy sai | Test/config phải phát hiện sai phạm theo thiết kế | Không thể chứng minh uniqueness bằng vài nghìn mẫu ngẫu nhiên |
| Key suspended ở KMS | Operation KMS bị từ chối theo provider contract | Local cached DEK có thể vẫn hoạt động |
| KMS outage khi chưa có DEK | Fail closed hoặc đường DR có phê duyệt | Không fallback sang static key hay cache vô hạn |
| Cache đạt capacity/TTL | Evict/deny theo policy; không kéo dài secret vô hạn | Eviction không có nghĩa mọi copy biến mất |
| Request từ tenant khác có key ID hợp lệ | **DENY**, tránh key confusion | Service-role có quyền rộng vẫn cần tenant/resource checks |
| Log thành công và lỗi | Chỉ metadata/operation/outcome, không secret | Cần kiểm tra cả structured logging, traces và exception |

Các test nên có cả **positive path** cho workload hợp lệ và **negative path** cho principal/tenant/version sai. Nếu tất cả request đều bị từ chối thì an ninh nghiệp vụ và availability cũng chưa đạt.

### 13.2. Kiểm thử memory hygiene không được tạo lộ bí mật

Không nên lấy **heap dump của production** rồi tìm chuỗi key thật bằng cách gửi dữ liệu đến dịch vụ phân tích bên ngoài. Một bài kiểm thử có thể dùng **khóa tổng hợp hoàn toàn không liên quan production** trong môi trường cô lập, đo thời gian giữ reference, kiểm tra redaction và tính năng dump theo quyền, sau đó xóa dữ liệu test theo policy.

Có thể kiểm tra:

1. **Source/API scan:** không có key.getEncoded hoặc Base64(rawKey) trong đường logging/serialization không cần thiết.
2. **Test với sample secret giả:** không xuất hiện trong structured logs, traces, audit payload và error reporting.
3. **Cache tests:** TTL, max size, tenant boundaries, eviction, restart, disabled/rotated versions.
4. **Dump policy tests:** runtime user có quyền tạo/đọc heap/core dump không, dump được đưa đi đâu, TTL và access review.
5. **Failure paths:** exception từ Cipher/KMS không bỏ qua finally/close, không đưa plaintext/key vào message.
6. **Concurrency:** nhiều thread cùng yêu cầu key, close/evict/race không cho phép use-after-close hoặc ghi đè không nhất quán.
7. **Provider behavior:** có cần import/export raw key không, handle có sống qua session restart không, Destroyable có tác dụng đúng contract không.

**Không coi việc không tìm thấy key bytes trong một heap dump nhỏ là bằng chứng không có khóa ở đâu cả.** Khóa có thể ở native memory, vào RAM tại thời điểm khác, hoặc nằm trong một process/region khác. Ngược lại, tìm thấy raw key trong môi trường test là dấu hiệu cần phân tích đường đi và ownership của material.

### 13.3. Chaos/recovery tests

Các kịch bản đáng kiểm tra trong môi trường được kiểm soát:

- **KMS latency/timeout:** hệ thống giới hạn retry, không tạo credential fallback yếu.
- **Key version rotated:** ciphertext cũ vẫn resolve đúng DEK/KEK theo policy; key mới không ghi đè cache của key cũ.
- **KMS key disabled:** unwrap mới bị deny; local DEK lease đã cấp được xử lý theo cửa sổ revocation đã chấp nhận.
- **Pod/process restart:** không phụ thuộc vào static key trong memory không backup; khởi động từ approved key source.
- **VM snapshot/restore:** không làm quay lùi nonce counter với cùng DEK và không âm thầm tái sử dụng session key quá hạn.
- **Multi-region propagation:** stale event không được kích hoạt lại key đã suspended/revoked.
- **Memory pressure/OOM:** dump và logs được bảo vệ, không vô ý gửi secret qua support tools.
- **DR restore:** key ID/version, wrapped DEK, encryption context và quyền truy cập phù hợp để khôi phục dữ liệu lịch sử.

Đối với hệ thống dùng AES-GCM, kiểm tra **nonce uniqueness** có tính quan trọng tương đương bảo vệ DEK trong RAM. Một khóa không bị lộ nhưng nonce bị lặp lại cùng key vẫn có thể gây mất bí mật và toàn vẹn dữ liệu.

## 14. Audit và monitoring: Không biến quan sát thành nguồn rò rỉ

Một đội an ninh cần biết **khóa nào được dùng bởi ai, ở đâu, để làm gì và trạng thái ra sao**. Điều đó **không** đòi hỏi ghi nội dung key vào log.

| Sự kiện | Metadata nên có | Không nên ghi |
|---|---|---|
| **KMS GenerateDataKey/Unwrap** | principal, key ID/version, tenant/purpose, time, success/failure | Raw DEK hoặc response plaintext |
| **Local crypto operation** | key reference, caller context, operation, ciphertext record reference, outcome | Plaintext/key bytes, full credential |
| **Cache insert/evict/expire** | cache entry reference đã che PII, key version, TTL tier, reason, count | Key/nonce series ở dạng nhạy cảm |
| **Key rotation/suspend** | actor, policy revision, effective time, affected references | Raw KEK, exported private key |
| **Heap/core dump request** | actor, host/process ref, justification, destination, access review | Memory contents trong audit message |
| **Break-glass/migration** | approvals, scope, expiry, ticket và outcome | Secret được khôi phục |
| **Error/AEAD failure** | request ID, operation, generic failure class | Token, plaintext, material hoặc nội dung lỗi chứa secret |

**Key ID thường không phải bí mật**, nhưng có thể chứa tenant/account/environment hoặc thông tin cá nhân. Nên giới hạn truy cập log, dùng retention và metadata masking khi cần. Một audit record phải đủ để **truy vết** nhưng không được làm tăng blast radius bằng việc nhân bản secret.

### 14.1. Các chỉ số vận hành hữu ích

- **Số plaintext DEK leases/cache entries đang sống** theo workload, không công bố raw material.
- **Phân bố TTL/cache age**, lần vượt hạn, số eviction và cache hit/miss.
- **Số KMS Unwrap calls** và tỷ lệ denied theo principal/tenant/purpose.
- **Key version/cryptoperiod** đang được sử dụng so với inventory.
- **Số heap/core dumps** được tạo, người có quyền đọc, thời hạn lưu và nơi lưu.
- **Phát hiện key export hoặc secret logging** không được phê duyệt.
- **Tần suất key errors/AEADBadTagException** bất thường để điều tra, không tiết lộ ciphertext/secret.
- **Thời gian thu hồi quyền sau sự cố**, propagation lag và stale lease còn mở.
- **Số workload có quyền Decrypt hoặc Sign quá rộng** và tiến độ sửa quyền.

Không suy ra một hệ thống “an toàn 100%” chỉ vì metric **zero leaked keys**; không có log lộ bí mật không chứng minh **mọi memory dump/native copy** đều sạch.

## 15. Ứng phó sự cố khi in-memory key có thể đã lộ

### 15.1. Sự cố minh họa: Heap dump bị truy cập sai quyền

Giả sử một pod xử lý hồ sơ khách hàng bị OOM. Heap dump được tạo tự động, chứa đối tượng liên quan DEK, và một tài khoản ngoài nhóm vận hành được phép đọc file dump. **Không được tự kết luận có ai đã lấy DEK chỉ vì dump tồn tại**, nhưng phải xem đây là một **đường exposure đáng điều tra**.

Runbook:

1. **Phát hiện và bảo toàn chứng cứ có kiểm soát:** xác định dump path, storage, principal đọc được, mốc tạo, retention và access logs.
2. **Cô lập:** gỡ quyền đọc trái phép, ngăn dump mới xuất hiện ở kho không phù hợp, kiểm soát kênh phân phối/copy.
3. **Khoanh vùng key material:** process nào đã xử lý **key IDs/versions, tenants và datasets** gì tại thời điểm dump; inventory và KMS audit có coverage tới đâu?
4. **Đánh giá khả năng lộ:** liệu raw DEK, plaintext, private key hay bearer token có thể đã nằm trong memory và những ai có quyền tiếp cận?
5. **Quyết định mitigation:** revoke credential, terminate workload hoặc session, thay phiên bản key, re-encrypt dữ liệu nếu raw DEK thực sự có nguy cơ bị lộ.
6. **Với private signing key:** nếu private material có thể bị copy, xem xét rotate/revoke public-key trust/JWKS/certificate, token/session impact.
7. **Với root/KEK:** rà các nhánh derived/wrapped DEK phụ thuộc; chỉ rewrap không sửa được một DEK đã lộ.
8. **Khôi phục:** dùng KMS/HSM được chấp thuận, kiểm tra dữ liệu lịch sử và backup trước khi destroy material cũ.
9. **Hậu kiểm:** cập nhật dump policy, host IAM, secret lifecycle, cache TTL, observability và detection; lưu audit mà không đưa raw key vào ticket.

### 15.2. Bảng quyết định theo loại secret có thể bị lộ

| Material | Nếu bị lộ thì ảnh hưởng chính | Hướng xử lý |
|---|---|---|
| **Plaintext DEK** | Ciphertext dùng DEK đó có thể bị giải mã nếu đối thủ có bản mã | Thay DEK, đánh giá re-encrypt và phạm vi dữ liệu |
| **KEK/root key** | Có thể ảnh hưởng nhiều wrapped/derived keys | Thay root/KEK, rà nhánh, unwrap/migrate theo đường được phê duyệt |
| **Private signing key** | Có thể giả mạo chữ ký offline | Rotate/revoke trust, xử lý certificate/JWKS/session và chữ ký liên quan |
| **HMAC secret** | Có thể tạo MAC hợp lệ | Rotate secret, giới hạn grace period, anti-replay |
| **KDF IKM/PRK** | Có thể dẫn xuất các derived keys tương ứng | Thay root/PRK khi cần và các nhánh bị ảnh hưởng |
| **Plaintext nghiệp vụ** | Dữ liệu đã bị tiếp cận ngoài quyền | Ứng phó dữ liệu, không chỉ rotation key |
| **KMS/HSM session token hoặc key handle** | Có thể gọi API khi token còn hiệu lực | Revoke session/credential và IAM, điều tra operation logs |

### 15.3. Đừng xóa khóa vội vì một memory alert

Một cảnh báo không rõ nguyên nhân có thể cần **suspend/limit key use**, nhưng **DestroyKey** thường là hành động khó đảo ngược, có thể làm mất dữ liệu mã hóa và khả năng khôi phục. Trước khi destroy:

- Xác minh key material nào thực sự bị ảnh hưởng.
- Kiểm tra ciphertext, wrapped DEK và archive đang cần phiên bản khóa nào.
- Xác định vùng/backup/escrow còn material hay không.
- Quyết định rewrap, re-encrypt, revoke trust và migration theo loại khóa.
- Thử restore/verification được kiểm soát và ghi phê duyệt.

**Một vòng đời khóa an toàn phải bảo vệ cả confidentiality và availability**. Đánh giá in-memory exposure không phải lý do bỏ qua quyền và recovery runbook.

## 16. Case study: Customer Data Service và cache DEK trên nhiều node

### 16.1. Bối cảnh

Một nền tảng Java có:

- **Customer Data Service** chạy nhiều pod, mã hóa hồ sơ bằng **AES-256-GCM**.
- **KMS** giữ KEK-v3 và có API mở wrapped DEK.
- **Database** giữ ciphertext, nonce, tag, wrapped DEK, key ID/version và record metadata.
- **Key inventory** ghi owner, tenant, purpose, state và dữ liệu phụ thuộc.
- **Security team** chịu trách nhiệm IAM, audit và key rotation.

Đội phát triển muốn tăng throughput bằng cách giữ plaintext DEK trong cache JVM **trong nhiều giờ**, dùng chung cho nhiều request và tenants, đồng thời bật heap dump tự động khi memory pressure tăng.

### 16.2. Những rủi ro phải phát hiện

1. **Cache nhiều tenant:** một lỗi lookup có thể trả DEK sai tenant, gây key confusion và vượt ranh giới dữ liệu.
2. **TTL không giới hạn theo key version:** key cũ tiếp tục được dùng sau rotation, làm ciphertext metadata sai hoặc giữ exposure lâu.
3. **KMS grant quá rộng:** service bị lạm dụng để unwrap DEK của tenant khác dù KEK non-exportable.
4. **AES-GCM nonce collision:** nhiều pod có thể encrypt với cùng DEK nhưng mỗi pod không theo dõi tổng số lần dùng/nonce.
5. **Suspend không chặn cache:** KMS từ chối Unwrap mới, nhưng plaintext DEK vẫn nằm trong JVM.
6. **Heap dump:** memory data có thể được upload/backup sang nơi người không được phép đọc.
7. **Crash/failover:** process restart mất DEK cache; nếu database chỉ có ciphertext mà thiếu wrapped DEK/keyRef thì không restore được.
8. **KMS outage:** tăng TTL vô hạn và fail-open có thể phá chính sách bảo mật.

### 16.3. Thiết kế có kiểm soát

~~~mermaid
flowchart TD
    R["Request: identity + tenant + record"] --> A["Authorize resource/tenant"]
    A --> V["Resolve immutable keyId/version từ envelope"]
    V --> C{"Lease DEK hợp lệ đúng scope?"}
    C -->|"Có"| X["Crypto operation trong boundary"]
    C -->|"Không"| K["KMS Unwrap với IAM và encryption context"]
    K --> L["Lease TTL/capacity giới hạn, audit"]
    L --> X
    X --> G["AES-GCM tag/AAD verification hoặc Encrypt nonce mới"]
    G --> Z["Cleanup/evict theo lifetime"]
    Z --> O["Audit metadata và metrics an toàn"]
~~~

**Phương án triển khai:**

1. **Giữ KEK ở KMS/HSM**; ứng dụng chỉ được Unwrap đúng tenant/record theo IAM và authorization.
2. **Scope key cache** bởi key ID/version, tenant, purpose và wrapped DEK reference; không dùng alias chung hoặc global DEK cho mọi tenant.
3. **Giới hạn TTL/capacity** và cleanup best effort, xử lý không đồng bộ eviction/crypto theo thiết kế thread-safe.
4. **Đặt nonce policy riêng**: đảm bảo uniqueness với cùng DEK trên toàn cụm và rotation/usage limits.
5. **Giới hạn heap/core dump và telemetry**, bảo vệ artifact debug như dữ liệu có độ nhạy cao.
6. **Ghi keyRef thực tế trong envelope**, lưu wrapped DEK đủ để phục hồi, phân tách content AAD với wrapping metadata.
7. **Giảm KMS grants** theo workload, owner, tenant và purpose; rà direct API bypass/metadata giả mạo.
8. **Khi rotate KEK**, xử lý rewrap/decrypt history; khi DEK bị lộ, đánh giá re-encrypt.
9. **Test failure/revocation** ở provider thật và cache behavior trong nhiều replica/region.
10. **Audit** operation/key version/lease events, giữ log không chứa key material/plaintext.

### 16.4. Kết quả mong đợi

Thiết kế cho phép **cân bằng latency và exposure** theo threat model, giảm số DEK sống đồng thời trong JVM, có khả năng xác định key version cho dữ liệu cũ và xử lý sự cố có phạm vi. Tuy nhiên, không thể bảo đảm rằng **RCE trong một process đang cầm plaintext DEK** không đọc được DEK. Nếu yêu cầu ngăn điều đó, cần thay đổi **ranh giới xử lý phép toán** hoặc môi trường bảo vệ, không chỉ tinh chỉnh TTL.

## 17. Sai lầm phổ biến

| Ngộ nhận/lỗi | Vì sao nguy hiểm | Hướng xử lý |
|---|---|---|
| **DEK ở RAM nên không phải “stored”** | RAM, swap, dump và snapshot đều có exposure | Có memory policy riêng, inventory raw key locations |
| **GC sẽ xóa key ngay khi scope kết thúc** | Không bảo đảm thời điểm/overwrite | Lifetime/cleanup best effort, giảm copies, dump controls |
| **Arrays.fill xóa mọi bản SecretKeySpec** | SecretKeySpec đã tạo bản sao | Không overclaim wipe, dùng provider contract phù hợp |
| **getEncoded chỉ để debug** | Có thể xuất thêm raw key bytes | Không export material nếu không thật cần và được phép |
| **Direct buffer luôn an toàn hơn heap** | Native/off-heap vẫn dump/copy được | Threat-model và kiểm soát provider/native lifecycle |
| **Mật khẩu keystore nằm trong env là không thể lộ** | Env/process/config dump có thể lộ secret | Secret distribution, IAM/host controls, không log |
| **KMS giữ KEK nên app không có secret** | KMS có thể trả plaintext DEK | Inventory data-key flow và lease |
| **Disable KEK sẽ ngừng mọi decrypt** | DEK cached vẫn dùng offline | Cache invalidation, workload/session controls |
| **Cache theo alias current-key** | Rotate alias có thể trỏ version khác | Immutable key ID/version và correct cache scope |
| **Cache shared across tenant để tăng hit rate** | Cross-tenant key reuse/lookup confusion | Tenant/purpose isolation |
| **Dùng cùng nonce GCM sau restart** | Phá AEAD confidentiality/integrity | Uniqueness strategy và invocation limits |
| **Plaintext DEK được log Base64 thì vẫn “encoded”** | Encoding không phải encryption | Không log hoặc serialize key |
| **Decrypt KMS role được cấp cho mọi microservice** | KMS trở thành decryption oracle | Least privilege theo principal/key/tenant/context |
| **Mã hóa key trong RAM bằng key nằm cùng JVM là đủ** | Process compromise có thể lấy/đòi unwrap | Ranh giới tin cậy mạnh hơn nếu cần |
| **Heap dump có thể upload vào ticket công khai** | Phát tán material/plaintext ngoài quyền | Secure diagnostic artifacts và incident handling |
| **Xóa DEK cache là crypto-erasure dữ liệu** | Bản khác/KEK/root có thể mở hoặc dẫn xuất lại | Xem mọi đường recovery, backup và copies |
| **KMS timeout thì fallback sang static key** | Bypass security controls, khóa yếu/dùng chung | DR được phê duyệt hoặc fail closed |
| **Rewrap một DEK đã lộ là đủ** | Attacker vẫn có raw DEK | Thay DEK, đánh giá re-encrypt |

## 18. Checklist thiết kế In-memory key trước production

1. **Data flow:** biết raw DEK/KEK/HMAC/private key/IKM/PRK/OKM đi qua những process/thread/native boundaries nào?
2. **Provider:** phân biệt raw key object với opaque/non-exportable key handle, có bằng chứng export restrictions đúng provider?
3. **Generation:** dùng CSPRNG và API key generation được chấp thuận, không seed thời gian hoặc static secret?
4. **Authorization:** caller, tenant, record, purpose, key state và key version được kiểm tra từ nguồn đáng tin trước operation?
5. **Boundary:** raw key chỉ có mặt trong crypto service/layer được phép, không đi qua DTO/JSON/controller/log?
6. **Lifetime:** mọi raw key có TTL/scope rõ, ownership, try/finally/close và cleanup best effort?
7. **Copies:** không dùng getEncoded/Base64/String tùy tiện; biết SecretKeySpec/provider/native có thể tạo bản sao?
8. **Caching:** cache có max entries/bytes, TTL, tenant/key-version scope, eviction và fail behavior?
9. **Concurrency:** close/evict/race và in-flight operations đã được định nghĩa, test phù hợp?
10. **AES-GCM:** nonce unique với cùng DEK trên nhiều replica/restart và có usage/rotation limits?
11. **AAD:** tenant/record/content metadata được xác thực; không dùng AAD thay IAM; rewrap key version có kế hoạch?
12. **KMS/HSM:** KEK/private keys non-exportable khi policy yêu cầu, grants ít quyền và audit được kiểm tra?
13. **Rotation:** phân biệt rewrap KEK, re-encrypt DEK, signing/HMAC/KDF root rotation và phụ thuộc dữ liệu cũ?
14. **Revocation:** KMS suspend/disable không được giả định xóa plaintext DEK cached hay session keys đã cấp?
15. **Dump controls:** heap/core dump, crash report, profiler, APM và hỗ trợ kỹ thuật có quyền/retention an toàn?
16. **OS/host:** swap, snapshots, privileged containers, debugging và remote support được kiểm soát theo threat model?
17. **Backup/DR:** wrapped DEK, key ID/version, KEK continuity và restore testing không phụ thuộc cache RAM?
18. **Error handling:** không đưa key/plaintext vào exception; KMS outage không tự fail-open hoặc tăng TTL vô hạn?
19. **Audit:** ghi principal/keyRef/operation/outcome và lease metrics mà không ghi raw material?
20. **Incident response:** có cách khoanh vùng keys từng ở trong dump/process và quyết định revoke/rotate/re-encrypt?
21. **Independent verification:** negative tests, cache/expiry/revocation tests và data-plane provider checks được thực hiện?
22. **Assurance claims:** không nói “secure zeroization” tuyệt đối khi chỉ dùng Java Arrays.fill hoặc GC?

### Câu hỏi tự kiểm tra

**Câu 1.** DEK chỉ được dùng trong RAM thì có hoàn toàn tránh rủi ro lưu trữ bí mật không?

**Trả lời:** **Không.** Key bytes có thể xuất hiện trong heap, native memory, dumps, swap, snapshots hoặc bản sao do provider tạo ra. Cần memory policy và giới hạn quyền/lifetime.

**Câu 2.** SecretKeySpec được tạo từ rawDek rồi rawDek được Arrays.fill bằng 0. SecretKeySpec có chắc đã mất key bytes?

**Trả lời:** **Không.** SecretKeySpec tạo bản sao bytes. Việc wipe mảng gốc không xóa các bản sao trong object/provider.

**Câu 3.** Một HSM trả key handle non-exportable cho JVM có giống KMS trả plaintext DEK không?

**Trả lời:** **Không.** Handle có thể không chứa raw material; plaintext DEK là key bytes trong JVM. Cả hai vẫn cần kiểm soát quyền sử dụng.

**Câu 4.** Tại sao không gọi SecretKey.getEncoded() chỉ để xác nhận key có đúng 32 byte?

**Trả lời:** Có thể tạo một bản sao raw key và gây exposure. Với key non-exportable, phương thức có thể không trả raw bytes; nên xác minh key type/size và provider attributes qua contract được phép.

**Câu 5.** Khi KMS suspend KEK, DEK đã unwrap và cache trong JVM có tự bị vô hiệu không?

**Trả lời:** **Không.** JVM có thể dùng DEK offline. Cần giới hạn lease/cache, quyền điều khiển workload, invalidation và điều kiện thực thi cụ thể.

**Câu 6.** Direct ByteBuffer hoặc memory locking có bảo đảm chống mọi loại memory dump hoặc RCE không?

**Trả lời:** **Không.** Chúng có thể giảm một số đường rò tùy nền tảng, không ngăn mọi bản sao trong process/native provider hoặc kẻ tấn công điều khiển tiến trình.

**Câu 7.** AES-GCM nonce 96 bit được SecureRandom sinh có đảm bảo không bao giờ trùng trên mọi pod cùng dùng DEK không?

**Trả lời:** **Không.** Đây là chiến lược theo xác suất. Cần phân tích collision risk, giới hạn invocation hoặc dùng cơ chế uniqueness cấu trúc phù hợp với toàn cụm.

**Câu 8.** Tại sao key cache theo alias **current-key** có thể gây lỗi sau rotation?

**Trả lời:** Alias có thể đổi sang material/version mới trong khi cache còn key cũ. Cần immutable key ID/version và tenant/purpose scope.

**Câu 9.** KMS Unwrap đã có IAM, vậy ứng dụng có cần kiểm tra quyền truy cập record trước đó không?

**Trả lời:** **Có.** Một KMS principal có quyền unwrap rộng vẫn có thể bị ứng dụng lợi dụng làm confused deputy nếu tenant/record không được kiểm tra.

**Câu 10.** Nếu plaintext DEK đã lộ qua heap dump, chỉ rewrap bằng KEK mới có đủ không?

**Trả lời:** **Không.** Đối thủ sở hữu DEK vẫn có thể giải mã ciphertext dùng DEK đó. Cần đánh giá thay DEK, re-encrypt và phạm vi dữ liệu ảnh hưởng.

**Câu 11.** Trong Java, try-with-resources và Arrays.fill có phải bằng chứng tất cả key bytes đã được xóa khỏi process không?

**Trả lời:** **Không.** Đó là cleanup best effort của object/buffer do code sở hữu; không bảo đảm với JIT, GC, Cipher, SecretKeySpec hoặc native copies.

**Câu 12.** Nếu xóa key cache khi ứng dụng tắt, có thể chắc chắn khôi phục toàn bộ ciphertext mà không cần KMS/backup không?

**Trả lời:** **Không.** Ciphertext cần đúng material/version. Với envelope encryption, phải có wrapped DEK, KEK/KMS access và metadata/backup hợp lệ; cache RAM không phải nguồn khôi phục lâu dài.

**Điểm cốt lõi:** **In-memory key** là một giai đoạn tồn tại thực tế của key material, không phải vùng an toàn mặc định. Thiết kế tốt phải xác định **raw key hiện diện ở đâu, quyền dùng, tenant/version, lifetime, số bản sao, cache, nonce và failure mode**; giảm exposure bằng **KMS/HSM/non-exportable handle khi phù hợp**, dọn buffer best effort, bảo vệ **heap/core dump, swap, host, telemetry** và có **audit, rotation, revocation, incident response**. Trong Java, **giảm việc đưa raw key vào process và giảm thời gian tồn tại** thường quan trọng hơn việc tuyên bố một lời hứa zeroization mà JVM/provider không thể bảo đảm.
