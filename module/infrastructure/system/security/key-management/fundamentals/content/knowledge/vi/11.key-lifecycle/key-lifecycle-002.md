# Active state

> **Chương:** Key lifecycle  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Active state là gì?

**Active state (trạng thái đang hoạt động)** là trạng thái trong **vòng đời khóa mật mã (key lifecycle)** mà một khóa đã được tạo, cấp phát, kiểm tra và **được hệ thống cho phép sử dụng cho những thao tác mật mã đã quy định**. Nói cách khác, khóa không chỉ tồn tại dưới dạng byte hoặc một đối tượng KMS/HSM; khóa đã đi vào giai đoạn có thể được sử dụng thực tế theo **chính sách, mục đích và thời hạn hiệu lực**.

Ví dụ, một phiên bản KEK (Key Encryption Key) được sinh trong KMS hôm nay nhưng chỉ bắt đầu dùng để bọc DEK (Data Encryption Key) từ ngày mai. Trước thời điểm đó, KEK có thể ở trạng thái **pre-active**; sau khi hệ thống kiểm tra đủ điều kiện, KEK chuyển sang **active**. Khi xoay vòng sang KEK mới, phiên bản cũ có thể ngừng bọc DEK mới nhưng vẫn được dùng để mở bọc những DEK đã tồn tại, tùy chính sách.

**Active không đồng nghĩa với “ai cũng được dùng” hoặc “dùng làm gì cũng được”.** Một thao tác chỉ nên được phép khi đồng thời thỏa mãn:

1. Trạng thái của **đúng khóa/phiên bản khóa** cho phép thao tác đó.
2. **Mục đích sử dụng (key usage)** và thuật toán phù hợp.
3. Thời điểm yêu cầu nằm trong **cryptoperiod** được phép cho thao tác.
4. Chủ thể gọi có **quyền IAM/KMS/HSM** và quyền nghiệp vụ tương ứng.
5. Không có điều kiện ngăn chặn như **khóa bị lộ, bị đình chỉ, bị thu hồi, vượt giới hạn sử dụng** hoặc chính sách an ninh khác.

Ví dụ cụ thể: **ACTIVE + permission `Encrypt` của service account** vẫn chưa đủ để mã hóa dữ liệu của một tenant khác nếu tầng nghiệp vụ không cho phép; tương tự, trạng thái ACTIVE không tự biến một khóa chuyên dùng **`SIGN`** thành khóa được phép **`DECRYPT`**.

### Mục tiêu học tập

- Định nghĩa được Active state và vị trí của nó giữa **tạo, cấp phát, sử dụng, xoay vòng, thu hồi và hủy khóa**.
- Phân biệt Active với **Pre-active, Suspended, Deactivated, Compromised và Destroyed**, đồng thời hiểu rằng cách đặt tên phụ thuộc hệ thống.
- Hiểu mối quan hệ giữa **key state, cryptoperiod, usage policy, key version, IAM và key material**.
- Thiết kế thao tác **mã hóa mới / giải mã dữ liệu cũ**, **ký mới / xác minh chữ ký cũ** không bị gián đoạn khi rotation.
- Triển khai mô hình kiểm soát trước thao tác bằng Java 17 và biết giới hạn của mô hình minh họa.

## 2. Active state trong sơ đồ vòng đời khóa

Một vòng đời quản lý khóa thường chứa những thời điểm: sinh khóa, đưa vào kho an toàn, cấp quyền, kích hoạt, sử dụng, xoay vòng, ngừng dùng, xử lý sự cố và hủy. **State machine cụ thể không hoàn toàn giống nhau** giữa tiêu chuẩn, KMS/HSM và ứng dụng, nên sơ đồ sau là **mô hình khái niệm**:

~~~mermaid
flowchart TD
    NEW[Created / Generated] --> PRE[Pre-active]
    PRE --> ACT[Active]
    ACT --> SUS[Suspended]
    SUS -->|Chỉ khi đủ điều kiện khôi phục| ACT
    ACT --> DEACT[Deactivated]
    DEACT --> DEST[Destroyed]
    ACT --> COMP[Compromised]
    SUS --> COMP
    DEACT --> COMP
    COMP --> DEST
~~~

### Ý nghĩa từng trạng thái

| Trạng thái | Ý nghĩa nghiệp vụ mật mã | Hành vi nên cân nhắc |
| --- | --- | --- |
| **Created / Generated** | Key material hoặc đối tượng khóa vừa được tạo | Chưa mặc nhiên được cấp quyền dùng cho dữ liệu thật |
| **Pre-active** | Đã được chuẩn bị, chờ activation hoặc phê duyệt | Không tạo nội dung bảo vệ mới trước thời điểm kích hoạt |
| **Active** | Có thể dùng cho **những tác vụ và thời hạn được phép** | Cho phép kiểm soát theo usage, IAM, cryptoperiod, hạn mức |
| **Suspended** | Tạm dừng sử dụng trong khi điều tra hoặc chờ khắc phục | Thường từ chối thao tác nhạy cảm; chỉ phục hồi sau phê duyệt |
| **Deactivated** | Không còn dùng cho thao tác tạo bảo vệ mới | Có thể cho phép xử lý dữ liệu cũ theo chính sách và khả năng nền tảng |
| **Compromised** | Được biết/nghi ngờ bí mật không còn được bảo vệ | Ngừng tin cậy theo chính sách; điều tra, thay khóa, xử lý dữ liệu phụ thuộc |
| **Destroyed** | Key material đã bị hủy theo quy trình | Không thể sử dụng khóa đó nữa; cần xem tác động đến backup/dữ liệu cũ |

**Lưu ý kỹ thuật:** một số KMS chỉ có trạng thái như `Enabled`, `Disabled`, `PendingDeletion`, `Deleted` hoặc các phiên bản trạng thái khác; trạng thái **Active** của bài này là khái niệm **lifecycle policy**. Không tự động quy đổi một-một các thuật ngữ đó sang trạng thái chuẩn của mọi cloud provider.

Trong một số thiết kế, **deactivated** vẫn cho phép xác minh chữ ký cũ bằng public key hoặc giải mã dữ liệu cũ bằng key đã nghỉ hưu. Trong thiết kế khác, trạng thái “disabled” của KMS chặn **mọi API**; khi đó muốn giải mã dữ liệu cũ, phải có cơ chế duy trì phiên bản đọc được hoặc kế hoạch **rewrap/re-encrypt** trước khi vô hiệu hóa hoàn toàn.

## 3. Kích hoạt khóa: từ pre-active sang active

Chuyển trạng thái sang Active là một **quyết định quản trị**, không chỉ là đổi tên field trong database. Trước khi cho phép khóa xử lý dữ liệu thật, hệ thống cần xác minh các điều kiện.

### 3.1. Các điều kiện kích hoạt

| Nhóm kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| **Nguồn sinh** | Khóa được sinh bằng CSPRNG/KMS/HSM tin cậy, đúng độ dài và thuật toán chưa? |
| **Mục đích** | Khóa dành cho `ENCRYPT`, `DECRYPT`, `WRAP`, `UNWRAP`, `SIGN`, `VERIFY` hay key agreement? |
| **Chủ sở hữu** | Đã xác định owner, hệ thống, môi trường, tenant và vai trò quản trị chưa? |
| **Định danh** | Có key ID, version và quy tắc tra cứu/alias rõ ràng chưa? |
| **Thời hạn** | Có `activationAt`, `newUseUntil`, thời gian dùng để xử lý dữ liệu cũ và retention phù hợp không? |
| **Quyền** | IAM/KMS policy và quyền ứng dụng có tuân thủ least privilege không? |
| **Phục hồi** | Với khóa phục vụ dữ liệu cần lưu lâu, đã kiểm tra backup, key archive và kế hoạch mất khóa chưa? |
| **Giám sát** | Có audit event, đo lường sử dụng và cảnh báo bất thường chưa? |
| **Phê duyệt** | Thay đổi state đã được phê duyệt/ghi nhận bởi chủ thể có quyền chưa? |

Không nhất thiết mọi khóa đều có quy trình phê duyệt thủ công. Khóa phiên TLS có thể được tạo/kích hoạt tự động trong handshake; KEK dùng để bảo vệ dữ liệu doanh nghiệp có thể có quy trình thay khóa và cấp quyền được kiểm soát chặt hơn.

### 3.2. Kích hoạt không làm tăng độ mạnh của khóa

Nếu DEK được sinh từ `Math.random()` hoặc entropy yếu, việc đổi `PRE_ACTIVE` sang `ACTIVE` **không biến nó thành khóa mạnh**. Trạng thái Active chỉ xác nhận điều kiện vận hành; chất lượng cryptographic material phải được đảm bảo từ **generation**.

Tương tự, một private key RSA/ECDSA ở trạng thái Active nhưng nằm trong log hoặc Git là **khóa bị lộ hoặc có nguy cơ lộ**, không phải “đã an toàn” vì KMS metadata cho thấy Enabled.

## 4. Điều gì được phép khi khóa Active?

Một khóa đang Active phải được kiểm soát theo **mục đích cụ thể**. Dù cùng dùng thuật ngữ Active, các nhóm khóa có mô hình thao tác rất khác nhau.

| Loại khóa | Thao tác có thể cho phép trong Active | Điều không nên suy luận |
| --- | --- | --- |
| **DEK đối xứng** | Mã hóa dữ liệu mới và giải mã dữ liệu được cấp phép | Có quyền đọc mọi record/tenant chỉ vì có DEK |
| **KEK trong KMS** | Wrap/unwrap DEK theo IAM và chính sách | Tự cho phép xuất raw KEK hoặc dùng để ký |
| **Private key ký số** | Tạo chữ ký mới theo role/cryptoperiod | Verifier cũng cần quyền `Sign` hoặc private key |
| **Public key xác minh** | Xác minh chữ ký liên quan đến đúng signer và chính sách tin cậy | Chữ ký hợp lệ tức là giao dịch hợp pháp |
| **Private key giải mã RSA** | Giải mã bí mật/unwrap key theo quyền | Có thể dùng thay cho RSA-PSS signing key |
| **PSK / HMAC key** | Xác thực hoặc dẫn xuất theo giao thức được chỉ định | An toàn nếu dùng một key chung cho mọi tenant |
| **Khóa phiên TLS** | Bảo vệ lưu lượng của kết nối/giai đoạn hiện tại | Có thể giữ traffic key vĩnh viễn hoặc dùng cho database |

### 4.1. Quyền dùng key ≠ quyền nghiệp vụ

Giả sử API có quyền gọi `Decrypt` trong KMS. API vẫn phải kiểm tra **người dùng có quyền đọc đơn hàng hay không**. KMS xác thực workload và policy khóa; tầng ứng dụng đánh giá **owner/tenant, resource, purpose và request**. Nếu bỏ authorization ứng dụng, việc có DEK/KEK hợp lệ có thể trở thành một cách vượt ranh giới dữ liệu.

### 4.2. Active không có nghĩa là mãi mãi Active

Ngay trong trạng thái Active, khóa vẫn có thể bị giới hạn bởi:

- **Số lần dùng/khối lượng dữ liệu:** ví dụ giới hạn bản ghi, nonce hoặc cryptographic operation count theo thuật toán.
- **Thời điểm bắt đầu/kết thúc:** policy có thể ngừng tạo bảo vệ mới trước khi chuyển state thực tế.
- **Thuật toán và usage:** chỉ dùng cho AEAD, ký, unwrap hoặc mục đích đã được phê duyệt.
- **Giới hạn môi trường:** staging key không được dùng ở production.
- **Sự cố:** nghi lộ khóa có thể dẫn tới block khẩn cấp trước khi hệ thống đồng bộ state hoàn toàn.

**Không dựa vào mỗi cờ `isActive=true`** để quyết định cho phép thao tác.

## 5. Active state và cryptoperiod

**Cryptoperiod** là khoảng thời gian một khóa được phép dùng cho **một tập thao tác mật mã xác định**. Trạng thái Active thường liên quan chặt chẽ đến cryptoperiod, nhưng **không đồng nghĩa toàn bộ thời gian tồn tại** của khóa.

Với nhiều loại khóa, cần phân biệt:

- **Originator-usage period:** thời gian khóa được phép **tạo bảo vệ mới**, chẳng hạn mã hóa bản ghi mới, ký tài liệu mới, wrap DEK mới.
- **Recipient-usage period:** thời gian còn được phép **xử lý đối tượng đã bảo vệ trước đó**, như giải mã dữ liệu cũ, unwrap DEK cũ hoặc xác minh chữ ký lịch sử theo chính sách.
- **Retention / archival period:** thời gian cần duy trì khả năng kiểm tra, phục hồi hoặc lưu chứng cứ; có thể lâu hơn thời gian tạo bảo vệ mới.

~~~text
Thời gian ---------->

Pre-active     Active: tạo bảo vệ mới     Retired/Deactivated     Destroyed
    |                 |                           |                  |
    +----activation---+------newUseUntil----------+------------------+
                      |                           |
                      +--- xử lý dữ liệu cũ ------->|----oldUseUntil---+

Lưu ý: dòng trên là minh họa. Các mốc do policy xác định.
~~~

### Ví dụ mốc thời gian

Một KEK phiên bản `kek-v4` được kích hoạt vào **01/12/2026** để bọc các DEK mới. Từ **01/03/2027**, `kek-v5` đảm nhiệm việc wrap mới; `kek-v4` chỉ được giữ để unwrap DEK đã bọc trước đó trong giai đoạn di chuyển. Sau khi mọi DEK liên quan và backup đã được xử lý, mới xem xét đóng quyền unwrap và hủy vật liệu khóa cũ.

Những ngày trên là **ví dụ thiết kế**, không phải thời hạn tiêu chuẩn áp dụng cho mọi KEK. Một cơ chế KMS có thể không hỗ trợ tách `Wrap` và `Unwrap` bằng trạng thái; ứng dụng cần kết hợp IAM, alias/version và kế hoạch migration đúng tính năng nhà cung cấp.

### Không đánh đồng hết hạn với mất khả năng giải mã

Nếu khóa đã hết originator-usage period, ta **không nên tiếp tục mã hóa dữ liệu mới** bằng khóa đó. Tuy nhiên, **xóa ngay key material** có thể khiến ciphertext cũ và backup không thể khôi phục. Quyết định hủy khóa phải dựa trên dữ liệu phụ thuộc, retention, recovery và đánh giá rủi ro.

Ngược lại, nếu khóa **bị lộ**, không thể đơn giản duy trì mọi quyền decrypt/sign cho đến cuối retention: cần áp dụng quy trình xử lý sự cố, cô lập, thay khóa và quyết định đặc biệt cho dữ liệu cũ.

## 6. Active version, alias và rotation

Trong hệ thống lưu nhiều phiên bản khóa, thường có một **phiên bản ưu tiên cho thao tác mới**. Nhưng **primary/current version** và **state Active** không phải là cùng một khái niệm.

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Key ID** | Định danh logic để tìm khóa trong một miền |
| **Key version** | Phiên bản vật liệu khóa cụ thể |
| **Active state** | Phiên bản được phép dùng cho thao tác theo policy |
| **Primary/current** | Phiên bản được lựa chọn **mặc định** cho một loại thao tác mới |
| **Alias** | Tên tham chiếu có thể trỏ tới một key/version hoặc đối tượng quản lý theo provider |
| **Retired/deactivated** | Không dùng cho tạo bảo vệ mới; có thể còn xử lý dữ liệu cũ theo chính sách |

**Có thể có nhiều phiên bản còn được phép giải mã** nhưng chỉ một phiên bản được chọn để **mã hóa mới**. Điều này rất phổ biến trong rotation an toàn.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Registry as Key metadata / policy
    participant KMS as KMS/HSM
    participant DB as Kho dữ liệu
    App->>Registry: Lấy active version cho ENCRYPT_NEW
    Registry-->>App: key-v2
    App->>KMS: Encrypt/Wrap theo key-v2 và quyền
    KMS-->>App: Bản mã hoặc wrapped DEK
    App->>DB: Lưu ciphertext + keyVersion=key-v2
    DB-->>App: Đọc ciphertext cũ + keyVersion=key-v1
    App->>Registry: Kiểm tra policy DECRYPT_OLD cho key-v1
    Registry-->>App: Được phép trong recipient period
    App->>KMS: Decrypt/Unwrap bằng key-v1 theo quyền
    KMS-->>App: Kết quả nếu policy cho phép
~~~

**Không giải mã ciphertext cũ bằng “active alias” nếu nó hiện trỏ đến key mới.** Payload phải lưu **key ID/version**, thuật toán, nonce/tag và metadata cần thiết; sau đó chọn **đúng phiên bản** để xử lý. Với KMS cung cấp versioning nội bộ, sử dụng đúng cơ chế nhận diện phiên bản của nhà cung cấp thay vì tự suy từ tên alias.

### Lộ trình rotation ít gián đoạn

1. **Tạo mới:** sinh `key-v2` trong vùng bảo vệ phù hợp; ở trạng thái chờ kích hoạt.
2. **Phê duyệt và cấp quyền:** xác thực metadata, policy, IAM, khả năng ứng dụng đọc key version.
3. **Kích hoạt:** cho phép `key-v2` thực hiện thao tác bảo vệ mới khi đủ điều kiện.
4. **Chuyển primary:** mọi tác vụ **encrypt/wrap/sign mới** bắt đầu dùng `key-v2`.
5. **Ngừng tạo mới bằng `key-v1`:** chuyển `key-v1` khỏi originator-usage period nhưng duy trì thao tác cũ theo chính sách.
6. **Migration:** rewrap DEK, re-encrypt dữ liệu hoặc điều chỉnh cơ chế xác minh chữ ký nếu có nhu cầu.
7. **Kiểm tra recovery:** xác minh snapshot, backup, dữ liệu ít truy cập và luồng rollback.
8. **Đóng và hủy:** chỉ khi không còn phụ thuộc và được phê duyệt, thu hồi quyền còn lại và hủy vật liệu khóa.

**Không nên xem việc đổi alias là toàn bộ rotation.** Nếu alias đổi mà ứng dụng vẫn cache key version cũ, vẫn có request đang chạy hoặc còn quyền gọi KMS bằng ID cũ, hệ thống có thể tiếp tục tạo bản mã mới dưới key cũ. Cần quan sát và xử lý những request trong giai đoạn chuyển đổi.

## 7. Suspended, deactivated và compromised khác Active ở đâu?

### 7.1. Suspended: dừng tạm thời để xác minh

Một khóa Active có thể bị **suspend** khi cần điều tra cấu hình, nghi vấn phân quyền hoặc có tín hiệu bất thường chưa đủ kết luận lộ khóa. Suspended thường nghĩa là **không thực hiện thao tác mật mã mới theo chính sách bảo thủ**, cho tới khi người có thẩm quyền cho phép phục hồi.

Khôi phục **SUSPENDED → ACTIVE** chỉ được phép sau khi đã chứng minh đủ điều kiện, đánh giá rủi ro và ghi nhận phê duyệt. Không tự động re-enable vì “đã hết thời gian chờ” nếu nguyên nhân chưa được xử lý.

### 7.2. Deactivated: ngừng tạo bảo vệ mới

Một khóa **deactivated** có thể vẫn có giá trị cho:

- **Decrypt/unwrap dữ liệu đã mã hóa/bọc** bằng key version đó.
- **Verify chữ ký lịch sử** bằng public key đã được ràng buộc với danh tính và có chính sách xác minh theo thời điểm.
- **Restore backup** trong phạm vi được phép.

Nhưng các thao tác này **không phải mặc định chung cho mọi dịch vụ KMS**. Có nhà cung cấp từ chối mọi thao tác khi khóa Disabled; lúc đó ứng dụng phải áp dụng cơ chế trạng thái riêng hoặc di chuyển dữ liệu trước.

### 7.3. Compromised: rủi ro thay đổi bản chất

Khi private key hoặc secret key **bị lộ hoặc nghi lộ đủ nghiêm trọng**, cần đánh giá khóa là compromised và **ngừng tin cậy** cho tác vụ liên quan; ưu tiên cô lập, revoke quyền, đổi khóa, đánh giá ciphertext/chữ ký/PSK bị ảnh hưởng.

**Không chuyển COMPROMISED → ACTIVE chỉ bằng cách bật lại một cờ.** Nếu khẳng định trước đó là cảnh báo nhầm thì phải có quy trình xử lý sự cố/phê duyệt rõ ràng; trong nhiều chính sách, khóa được xem là đã lộ sẽ **không bao giờ được tái sử dụng** mà thay bằng khóa mới.

**Ký số là trường hợp đặc biệt:** public key có thể vẫn được giữ để kiểm tra chữ ký lịch sử kèm **bằng chứng thời gian đáng tin**, nhưng một chữ ký có `verify=true` sau khi private key bị lộ **không đủ chứng minh được tạo trước thời điểm compromise**. Cần tách xác minh toán học với quyết định tin cậy lịch sử.

## 8. Java 17: ví dụ chính sách Active state trước khi dùng khóa

Ví dụ sau mô hình hóa **metadata điều khiển thao tác** cho một khóa đối xứng dùng bảo vệ dữ liệu. Hai thao tác được xét là:

- `ENCRYPT_NEW`: tạo bản mã mới, chỉ khi **state ACTIVE** và còn trong originator-usage period.
- `DECRYPT_EXISTING`: giải mã bản mã đã được lưu trước đó, có thể cho phép khi **ACTIVE** hoặc **DEACTIVATED** nếu còn recipient-usage period.

**Đây là policy gate minh họa, không thực hiện AES-GCM/KMS thật.** Triển khai production phải kiểm tra **IAM, phân quyền resource/tenant, key usage tại KMS, thông tin key ID của ciphertext và tình trạng sự cố**. Những kiểm tra đó không thể thay bằng một `if` duy nhất.

~~~java
import java.time.Instant;
import java.util.EnumSet;
import java.util.Set;

public class ActiveKeyStateDemo {
    enum State {
        PRE_ACTIVE, ACTIVE, SUSPENDED, DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum Operation {
        ENCRYPT_NEW, DECRYPT_EXISTING
    }

    record KeyRecord(
            String keyId,
            String version,
            State state,
            Instant activatedAt,
            Instant newUseUntil,
            Instant oldUseUntil,
            Set<Operation> permittedOperations) {
        KeyRecord {
            if (keyId == null || keyId.isBlank()
                    || version == null || version.isBlank()
                    || state == null || activatedAt == null
                    || newUseUntil == null || oldUseUntil == null
                    || permittedOperations == null
                    || !activatedAt.isBefore(newUseUntil)
                    || !newUseUntil.isBefore(oldUseUntil)) {
                throw new IllegalArgumentException("Invalid key policy");
            }
            permittedOperations = Set.copyOf(permittedOperations);
        }
    }

    static boolean mayUse(KeyRecord key, Operation op, Instant now) {
        if (op == null || now == null
                || !key.permittedOperations().contains(op)
                || now.isBefore(key.activatedAt())) {
            return false;
        }

        return switch (op) {
            case ENCRYPT_NEW ->
                    key.state() == State.ACTIVE
                    && now.isBefore(key.newUseUntil());

            case DECRYPT_EXISTING ->
                    (key.state() == State.ACTIVE
                            || key.state() == State.DEACTIVATED)
                    && now.isBefore(key.oldUseUntil());
        };
    }

    public static void main(String[] args) {
        Instant activatedAt = Instant.parse("2026-12-01T00:00:00Z");
        Instant newUseUntil = Instant.parse("2027-03-01T00:00:00Z");
        Instant oldUseUntil = Instant.parse("2027-09-01T00:00:00Z");

        Set<Operation> permissions = EnumSet.allOf(Operation.class);
        KeyRecord active = new KeyRecord(
                "customer-dek", "v4", State.ACTIVE,
                activatedAt, newUseUntil, oldUseUntil, permissions);
        KeyRecord retired = new KeyRecord(
                "customer-dek", "v4", State.DEACTIVATED,
                activatedAt, newUseUntil, oldUseUntil, permissions);

        Instant duringActive = Instant.parse("2027-01-15T00:00:00Z");
        Instant afterRotation = Instant.parse("2027-04-01T00:00:00Z");

        if (!mayUse(active, Operation.ENCRYPT_NEW, duringActive)) {
            throw new AssertionError("Should encrypt during active period");
        }
        if (mayUse(retired, Operation.ENCRYPT_NEW, afterRotation)) {
            throw new AssertionError("Old key cannot encrypt new data");
        }
        if (!mayUse(retired, Operation.DECRYPT_EXISTING, afterRotation)) {
            throw new AssertionError("Old data should remain readable");
        }
        if (mayUse(retired, Operation.DECRYPT_EXISTING, oldUseUntil)) {
            throw new AssertionError("Recipient period must end");
        }
        System.out.println("Active state policy checks passed");
    }
}
~~~

### Giải thích lựa chọn thiết kế

1. **Khoảng thời gian nửa mở `[start, end)`:** `newUseUntil` và `oldUseUntil` **không bao gồm thời điểm kết thúc**. Như vậy tránh lệch nghĩa tại ranh giới đúng 00:00:00.
2. **Tách originator với recipient:** trạng thái `DEACTIVATED` cấm `ENCRYPT_NEW` nhưng có thể cho `DECRYPT_EXISTING` đến hạn đã định; đó là **quy tắc ví dụ**, không được mặc định áp dụng cho mọi KMS.
3. **Deny by default:** mọi trạng thái như `SUSPENDED`, `COMPROMISED`, `DESTROYED` đều bị từ chối bởi cả hai nhánh.
4. **Kiểm tra usage:** ngay cả state ACTIVE cũng từ chối thao tác không nằm trong `permittedOperations`.
5. **Đối chiếu phiên bản:** phải lấy `keyId/version` từ ciphertext có metadata hợp lệ và policy hiện hành; ví dụ không trực tiếp giải mã nên chưa kiểm tra bước này.
6. **Thời gian đáng tin:** dùng thời điểm hệ thống đáng tin và chính sách xử lý clock skew; không nhận `now` do client gửi làm căn cứ cấp phép.
7. **State phải là nguồn sự thật:** nếu state/policy được cache ở ứng dụng, cần cơ chế hết hạn, invalidation và chặn khẩn cấp; **KMS/HSM policy vẫn phải áp dụng quyền trên server**.

**Lưu ý:** Java demo giả định `oldUseUntil` sau `newUseUntil`. Nếu kiến trúc không cần cửa sổ đọc dữ liệu cũ, có thể cho hai mốc bằng nhau trong policy riêng; phải thay ràng buộc cho phù hợp trước khi dùng. Demo không thực hiện các thao tác chuyển state, lưu vết audit hoặc xử lý trạng thái phân tán.

## 9. Tính nhất quán, race condition và rollback

Trong hệ thống phân tán, Active state dễ trở nên **không nhất quán giữa registry, application cache và KMS**. Ví dụ:

1. Registry đổi primary từ `key-v1` sang `key-v2`.
2. Node A vẫn cache `key-v1` và tiếp tục encrypt.
3. Node B đã dùng `key-v2`.
4. KMS vô hiệu hóa `key-v1` trước khi các request cũ kết thúc.
5. Một số thao tác thất bại hoặc sinh ciphertext dùng phiên bản không còn được phép tạo mới.

Không có một giải pháp duy nhất cho mọi hạ tầng, nhưng thiết kế nên có:

- **Versioned policy và atomic update** cho quyết định primary/active.
- **TTL và cache invalidation** rõ ràng, đặc biệt khi revoke khẩn cấp.
- **Audit key ID/version thực tế** được dùng trên từng operation, không chỉ alias logic.
- **Idempotency** cho thao tác mã hóa/rewrap theo mô hình dữ liệu, tránh xử lý hai lần khi retry.
- **Đường rollback có kiểm soát:** rollback code không được tự động kích hoạt lại key đã bị compromised.
- **Giới hạn thời gian chuyển đổi:** định nghĩa lúc nào chắc chắn không còn tạo bản mã mới bằng phiên bản cũ.

### Tránh TOCTOU trong kiểm tra trạng thái

**TOCTOU (time-of-check to time-of-use)** xảy ra khi ứng dụng kiểm tra ACTIVE tại thời điểm A, nhưng trạng thái thay đổi trước khi lệnh `Encrypt` đến KMS tại thời điểm B. Vì vậy, một policy gate ở tầng ứng dụng **không đủ**; dịch vụ quản lý khóa phải kiểm tra quyền/trạng thái tại thời điểm thực hiện nếu khả năng nền tảng cho phép.

Đặc biệt với **compromise**, hãy ưu tiên đường ngắt sử dụng khóa có hiệu lực gần nguồn thực thi và xác minh rằng cache không tạo lỗ hổng chấp nhận thao tác trái chính sách.

## 10. KMS/HSM và envelope encryption trong Active state

**KMS** quản lý key state, policy, quyền và audit theo API của từng sản phẩm. **HSM** có thể giữ key material không xuất được, thực hiện `Encrypt`, `Decrypt`, `Sign`, `Unwrap` trong vùng bảo vệ được thiết kế riêng.

**Cần phân biệt ba lớp trạng thái:**

1. **Trạng thái vật liệu khóa:** khóa tồn tại, bị hủy, bị khóa cứng hoặc mất khả năng sử dụng.
2. **Trạng thái lifecycle theo nghiệp vụ:** active, deactivated, compromised... và cryptoperiod.
3. **Trạng thái quyền:** IAM, key policy, approval, tenant authorization và các điều kiện truy cập.

Ba lớp này có thể tồn tại ở **những hệ thống khác nhau**. Ví dụ, KMS có một KEK ở trạng thái Enabled nhưng ứng dụng quy định phiên bản đó **chỉ được unwrap DEK cũ**, không được wrap mới. Quyết định Active ở tầng nghiệp vụ phải được **enforce** bằng kiến trúc phù hợp, không chỉ lưu metadata để hiển thị.

### 10.1. Tình huống envelope encryption

~~~mermaid
flowchart LR
    Client[Request hợp lệ] --> Policy[Kiểm tra quyền + key version + state]
    Policy -->|Encrypt mới: active DEK/KEK| Encrypt[AEAD bảo vệ dữ liệu]
    Encrypt --> DB[(Ciphertext + tag + nonce + wrapped DEK)]
    DB -->|Đọc record cũ| Reader[Chọn key version đã lưu]
    Reader -->|Decrypt cũ nếu policy cho phép| KMS[KMS/HSM giữ KEK]
    KMS --> Data[Khôi phục DEK và xác minh AEAD]
    Policy -.-> Audit[Audit state/version/operation]
    KMS -.-> Audit
~~~

Khi **KEK active** thay đổi, việc mã hóa dữ liệu mới có thể chuyển sang KEK mới. Nhưng **wrapped DEK cũ** vẫn phải được mở bằng phiên bản cũ hoặc đã được **rewrap** đúng cách. Nếu **DEK** thay đổi, có thể cần **giải mã và mã hóa lại dữ liệu**, không chỉ rewrap.

**Không hủy private key/KEK cũ** khi bản sao lưu còn phụ thuộc mà chưa có phương án khôi phục đã kiểm chứng. Tuy nhiên, nếu khóa bị lộ, việc giữ nó để giải mã cũ phải được kiểm soát như một **ngoại lệ xử lý sự cố** theo mô hình đe dọa, không phải tiếp tục tin tưởng như trước.

### 10.2. Active signing key và public key verification

Private key ký số có thể **ACTIVE** để ký tài liệu mới trong cryptoperiod. Sau rotation, private key cũ có thể bị deactivated hoặc hủy theo retention. **Public key** vẫn có thể được giữ để **xác minh chữ ký lịch sử** cùng chứng thư, bằng chứng thời gian và thông tin thu hồi.

Không nên kết luận “chữ ký cũ không hợp lệ” chỉ vì private signing key hiện đã không còn active. Ngược lại, nếu private key bị lộ, `Signature.verify() = true` chưa đủ để chứng minh chữ ký được tạo **trước thời điểm compromise**; cần bằng chứng tin cậy và chính sách đánh giá phù hợp.

## 11. Kiểm toán và quan sát trạng thái Active

Một hệ thống key management cần ghi nhận được **quá trình chuyển state** và **hành vi sử dụng khóa** mà không làm rò rỉ key material.

### Các trường audit nên có

| Nhóm | Trường gợi ý |
| --- | --- |
| **Định danh khóa** | `keyId`, `keyVersion`, `algorithm`, `purpose` |
| **Chuyển trạng thái** | `fromState`, `toState`, `reason`, `approvedBy`, `changedAt` |
| **Yêu cầu thao tác** | `operation`, `principal`, `tenantId`, `resourceId`, `requestId` |
| **Quyết định chính sách** | `policyVersion`, `effectiveAt`, `allowed`, mã lý do từ chối |
| **Bảo mật vận hành** | Phát hiện sử dụng khóa cũ sau rotation, truy cập trái phép, sự cố KMS, retry bất thường |

**Không ghi** raw DEK/KEK, private key, secret key, plaintext, mật khẩu, ticket secret hoặc token nhạy cảm vào log. Chỉ ghi những metadata thực sự cần cho điều tra, có phân quyền truy cập và thời hạn lưu phù hợp.

### Những cảnh báo có giá trị

- Key đã **deactivated** nhưng vẫn có yêu cầu **encrypt/sign mới**.
- Một key version sắp hết **new-use period** nhưng chưa có successor được kích hoạt.
- Tăng đột ngột lệnh **Decrypt/Unwrap** ở một principal không điển hình.
- Bất thường quanh **Enable/Disable**, thay key policy, alias mapping hoặc quyền IAM.
- Số lượng bản mã dưới một key tăng tới giới hạn **nonce/cryptoperiod**.
- Khóa chuẩn bị **destroy** trong khi backup hoặc record vẫn cần nó.
- Cache/node vẫn gọi key cũ sau thời điểm chuyển primary.

Audit cần kết nối **metadata KMS/HSM** với **request/tenant authorization** ở tầng ứng dụng để phân biệt thao tác kỹ thuật hợp lệ với truy cập dữ liệu trái phép.

## 12. Tình huống thực tế: xoay vòng KEK cho nền tảng đa tenant

Giả sử nền tảng có ba tenant và mã hóa thông tin khách hàng bằng DEK. Mỗi DEK được bọc bởi **KEK trong KMS**. Hệ thống có phiên bản `kek-v8` đang hoạt động và chuẩn bị chuyển sang `kek-v9`.

**Giai đoạn 1 — Chuẩn bị:**

- Sinh `kek-v9` trong KMS/HSM, kiểm tra thuật toán, quyền và audit.
- Đặt `kek-v9` vào **pre-active** cho đến khi hoàn tất kiểm thử và phê duyệt.
- Đảm bảo service có khả năng ghi/đọc **key version** trong payload và không chỉ dựa vào alias.

**Giai đoạn 2 — Kích hoạt:**

- Chuyển `kek-v9` sang **active** và cho hệ thống ưu tiên dùng nó để **wrap DEK mới**.
- Ngừng dùng `kek-v8` để **wrap mới**. Chỉ giữ `Unwrap` cho DEK cũ nếu chính sách và KMS hỗ trợ.
- Audit ghi lại thời điểm đổi primary, owner phê duyệt, số lượng request theo version và sự kiện lỗi.

**Giai đoạn 3 — Di chuyển:**

- Tìm các wrapped DEK dưới `kek-v8`, rewrap dưới `kek-v9` bằng quy trình có kiểm tra toàn vẹn và quyền.
- Đảm bảo rewrap không làm mất ciphertext, nonce, AAD hoặc thông tin nhận diện bản ghi.
- Kiểm thử **restore backup**, vì backup có thể chứa wrapped DEK dưới version cũ dù production đã chuyển xong.

**Giai đoạn 4 — Đóng khóa cũ:**

- Khi không còn phụ thuộc và đã hết recipient period, thu hồi quyền cũ rồi hủy theo chính sách.
- Nếu `kek-v8` có dấu hiệu bị lộ, kích hoạt điều tra, kiểm tra bản sao wrapped DEK đã bị lấy và xem xét **thay DEK/re-encrypt** đối với dữ liệu chịu ảnh hưởng; chỉ rewrap bản hiện tại chưa chắc giải quyết bản sao cũ đã bị thu thập.

### Hai sự cố cần kiểm thử

**Sự cố A — cache alias cũ:** một node vẫn wrap DEK mới bằng `kek-v8` sau thời điểm chuyển primary. Hệ thống phải phát hiện qua audit, ngừng thao tác không hợp lệ và xử lý những DEK vừa bị bọc sai policy.

**Sự cố B — KMS khóa cũ quá sớm:** KMS disable `kek-v8` trước khi backup được rewrap, khiến một số restore thất bại. Kế hoạch rotation phải có **kiểm tra phụ thuộc**, không chỉ deadline để xóa key cũ.

Tình huống cho thấy **Active state là trạng thái quản trị có thể kiểm tra và thực thi**, không phải một cờ hiển thị trong dashboard. Nó phải liên kết với key version, quyền sử dụng, dữ liệu phụ thuộc và quy trình ứng phó sự cố.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem `Active=true` là toàn bộ điều kiện cấp quyền | Có thể sử dụng khóa sai purpose/tenant | Kiểm tra usage, cryptoperiod, IAM và authorization nghiệp vụ |
| Coi `Enabled` trong KMS là `Active` nghiệp vụ ở mọi nơi | Không thực thi được chính sách originator/recipient | Ánh xạ state chính xác theo provider và enforce policy riêng |
| Tạo key mới rồi tự coi đã active | Khóa chưa qua cấp phát/phê duyệt và kiểm tra | Có preflight activation phù hợp mức rủi ro |
| Đổi alias nhưng không đổi policy/version ở các node | Dùng lại key cũ cho dữ liệu mới | Versioned registry, cache invalidation, audit actual key |
| Hủy key cũ ngay sau rotation | Mất khả năng giải mã dữ liệu và backup cũ | Rewrap/re-encrypt, retention và kiểm thử restore |
| Giữ mọi key cũ active vô hạn để “an toàn” | Tăng phạm vi rủi ro, không có cryptoperiod rõ | Tách read-old/write-new, ngừng tạo bảo vệ mới đúng hạn |
| Dùng một key cho cả ký và giải mã vì cùng Active | Sai purpose, mở rộng quyền khi lộ | Tách khóa theo `SIGN`, `DECRYPT`, `WRAP`... |
| Suspend rồi tự động re-enable không điều tra | Có thể mở lại khóa đã nghi lộ | Có điều kiện phục hồi, phê duyệt và audit |
| Compromised nhưng chỉ đổi alias hiển thị | Kẻ tấn công vẫn có secret và ciphertext cũ | Xử lý sự cố thực tế, revoke, rotate, đánh giá re-encrypt |
| Kiểm tra state trên cache rồi tin là luôn đúng | Race/TOCTOU khi state thay đổi | Enforce quyền gần nơi thực thi và invalidate cache |
| Cho rằng private signing key bị hủy thì không xác minh chữ ký cũ được | Mất khả năng kiểm tra hồ sơ lịch sử | Giữ public key/chứng cứ phù hợp và chính sách thời điểm |
| Không audit thao tác `Decrypt/Unwrap` | Khó phát hiện lạm dụng sau khi khóa bị kích hoạt | Ghi request ID, principal, key version, kết quả |
| Chỉ quản lý trạng thái khóa mà không quản lý nonce | Tái dùng AEAD nonce, hỏng bảo mật bản mã | Kiểm soát key scope, nonce uniqueness và usage limits |

## 14. Checklist vận hành Active state

- [ ] Đã phân biệt trạng thái **generated / pre-active / active / suspended / deactivated / compromised / destroyed** theo mô hình hệ thống?
- [ ] Trước khi ACTIVE, đã kiểm tra chất lượng nguồn sinh, mục đích, owner, key ID/version, policy và audit?
- [ ] Có định nghĩa cụ thể **thao tác được phép** trong ACTIVE thay vì một cờ Boolean tổng quát?
- [ ] Đã tách **originator-usage period** với **recipient-usage period** và retention dữ liệu?
- [ ] KMS/HSM state và application lifecycle state đã được ánh xạ rõ, không giả định `Enabled=Active` trong mọi trường hợp?
- [ ] IAM/KMS policy và authorization tầng ứng dụng cùng được kiểm tra, theo least privilege?
- [ ] Trong rotation, primary version cho thao tác mới tách khỏi version dùng đọc dữ liệu cũ?
- [ ] Payload mã hóa lưu đúng key ID/version, thuật toán, nonce, tag và metadata cần thiết?
- [ ] Có cơ chế cache invalidation, policy versioning và emergency revoke xử lý TOCTOU?
- [ ] Khóa chuẩn bị hủy đã được kiểm tra phụ thuộc DEK/KEK, backup, snapshot và dữ liệu ít truy cập?
- [ ] Với khóa ký, có chính sách public key verification, chứng thư và chứng cứ thời gian lịch sử?
- [ ] Có lộ trình xử lý COMPROMISED khác với DEACTIVATED thông thường, bao gồm đánh giá ciphertext đã lộ?
- [ ] Audit ghi được cả key transition và key usage, không log raw key, secret hay plaintext?
- [ ] Đã test các điều kiện biên của thời gian, race, failover, restore và alias stale?

## 15. Câu hỏi tự kiểm tra

**1. Vì sao khóa có trạng thái ACTIVE vẫn có thể bị từ chối thao tác Encrypt?**  
Vì trạng thái ACTIVE không cấp quyền vô điều kiện. Khóa có thể không có usage `ENCRYPT`, đã hết new-use period, caller không có IAM permission hoặc nghiệp vụ không cho phép truy cập dữ liệu.

**2. Active state khác primary key version như thế nào?**  
Active nói về quyền sử dụng của **một version** theo policy; primary chọn **version mặc định** cho thao tác mới. Có thể có một version mới là primary, trong khi version cũ vẫn được phép decrypt dữ liệu cũ.

**3. Vì sao không xóa key-v1 ngay sau khi kích hoạt key-v2?**  
Vì ciphertext, wrapped DEK, backup hoặc hồ sơ lịch sử có thể vẫn cần key-v1. Phải đánh giá phụ thuộc, khả năng rewrap/re-encrypt, retention và recovery.

**4. Có thể cho phép giải mã dữ liệu cũ bằng khóa DEACTIVATED không?**  
Có thể theo chính sách lifecycle có tách recipient period. Nhưng một KMS ở trạng thái Disabled có thể từ chối mọi thao tác, nên phải thiết kế phù hợp năng lực hạ tầng.

**5. Khi private key bị lộ, chỉ đổi trạng thái từ ACTIVE sang SUSPENDED có đủ không?**  
Không. Cần đánh giá compromise, ngăn tiếp tục sử dụng, thay khóa, kiểm tra dữ liệu/chữ ký/PSK chịu ảnh hưởng và thực hiện incident response.

**6. Vì sao xác minh chữ ký cũ khác với việc cho phép private key ký mới?**  
Việc ký mới cần private key còn được phép sử dụng, còn xác minh chữ ký cũ dùng public key và chính sách tin cậy lịch sử. Private key đã nghỉ hưu không tự làm mọi chữ ký cũ vô hiệu.

**7. Nếu registry báo ACTIVE tại thời điểm kiểm tra, có chắc KMS sẽ cho phép sử dụng key sau 10 giây không?**  
Không. State, quyền hoặc policy có thể đã thay đổi; cần kiểm soát TOCTOU và thực thi gần nguồn thực hiện thao tác.

**8. Cryptoperiod là gì trong bối cảnh Active?**  
Là khoảng thời gian khóa được phép dùng cho các thao tác mật mã xác định; có thể tách thời gian tạo bảo vệ mới và thời gian xử lý dữ liệu cũ.

## Ghi nhớ

**Active state là giai đoạn khóa mật mã được phép sử dụng cho những mục đích, đối tượng, thời hạn và quyền đã quy định — không phải giấy phép sử dụng khóa vô điều kiện.** Hệ thống an toàn phải kết hợp **key state, key ID/version, cryptoperiod, operation-level policy, IAM, phân quyền nghiệp vụ và audit**. Khi rotation, nên tách khóa dùng **encrypt/wrap/sign mới** khỏi khả năng **decrypt/unwrap/verify dữ liệu cũ**; không hủy khóa khi backup còn phụ thuộc, nhưng cũng không tái sử dụng khóa đã bị lộ. Việc triển khai Active đúng đòi hỏi liên kết cả **mã hóa đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, nonce uniqueness, quản lý sự cố và key lifecycle** từ sinh khóa đến hủy khóa.
