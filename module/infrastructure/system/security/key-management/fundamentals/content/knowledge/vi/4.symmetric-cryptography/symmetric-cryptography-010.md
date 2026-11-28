# Nonce uniqueness (Tính duy nhất của nonce)

## 1. Nonce uniqueness là gì?

**Nonce uniqueness** là yêu cầu **không sử dụng lại cùng một nonce với cùng một khóa mật mã trong phạm vi mà thuật toán hoặc giao thức yêu cầu**. Từ *nonce* bắt nguồn từ *number used once* — một giá trị được dùng một lần. Trong nhiều hệ thống, nonce được gọi là **IV (Initialization Vector)**, nhưng thuật ngữ và yêu cầu an toàn chính xác phụ thuộc chế độ mã hóa.

Đối với **AES-GCM**, mỗi lần mã hóa dưới một khóa AES nhất định phải sử dụng một nonce mới, chưa từng được dùng để mã hóa với khóa đó. Nonce thường **không cần giữ bí mật**. Điều bắt buộc là bảo đảm tính duy nhất, đúng kích thước/định dạng và xử lý nhất quán giữa bên mã hóa và giải mã.

Ví dụ:

~~~text
Khóa AES K (một khóa được giữ qua nhiều bản ghi):

  Mã hóa hồ sơ A: nonce = N1  -> hợp lệ
  Mã hóa hồ sơ B: nonce = N2  -> hợp lệ, nếu N2 khác N1
  Mã hóa hồ sơ C: nonce = N1  -> NGUY HIỂM: dùng lại nonce với K

Khóa AES K2 thực sự độc lập với K:
  nonce = N1                    -> có thể dùng lại theo yêu cầu của K2
~~~

**Phạm vi duy nhất là theo khóa**, không phải bắt buộc khác nhau trên toàn thế giới. Tuy nhiên, nếu hai dịch vụ hoặc hai tenant dùng chung **cùng vật liệu khóa**, chúng cũng chia sẻ một phạm vi nonce, dù sử dụng key ID hoặc alias khác nhau.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, yêu cầu này liên kết mật mã đối xứng với **vòng đời khóa, KMS/HSM, envelope encryption, phân quyền và kiểm toán**: hệ thống có thể lưu khóa rất an toàn nhưng vẫn làm lộ dữ liệu nếu cấp phát nonce sai.

## 2. Vì sao dùng lại nonce với cùng khóa AES-GCM nguy hiểm?

**GCM (Galois/Counter Mode)** là chế độ mã hóa có xác thực (**AEAD**): dùng AES ở dạng bộ đếm (CTR) để tạo luồng khóa cho bản rõ, đồng thời dùng cơ chế xác thực để kiểm tra bản mã và Additional Authenticated Data (AAD).

Khi lặp **cả khóa K và nonce N**, phần luồng khóa CTR dùng để mã hóa các vị trí tương ứng cũng bị lặp. Với các byte tương ứng của hai thông điệp:

~~~text
C1 = P1 XOR S
C2 = P2 XOR S

C1 XOR C2 = P1 XOR P2
~~~

Trong đó P là bản rõ, C là bản mã, S là luồng khóa. Kẻ tấn công quan sát được hai bản mã có thể suy ra quan hệ giữa các bản rõ; nếu biết một bản rõ, họ có thể khôi phục phần tương ứng của bản rõ còn lại. Đây **chỉ là một phần rủi ro**: tái sử dụng nonce trong GCM còn có thể phá bảo đảm **xác thực và chống giả mạo** của GCM.

Đặc biệt:

- **Tag khác nhau không cứu được việc trùng nonce**: dù bản rõ hoặc AAD khác nhau, vi phạm tính duy nhất vẫn rất nguy hiểm.
- **Nonce không phải mật khẩu**: giữ nonce bí mật không thay thế yêu cầu không tái sử dụng.
- **Không có bảo đảm rằng chỉ bản mã mới bị ảnh hưởng**: dữ liệu lịch sử đã ghi lại với cặp khóa/nonce trùng có thể bị khai thác.
- **Không phải mọi chế độ mã hóa có rủi ro giống nhau**: AES-GCM và AES-CTR có yêu cầu tránh tái sử dụng luồng khóa; AES-CBC có quy tắc IV khác. Cần đọc yêu cầu của thuật toán cụ thể.

## 3. Đặt nonce vào đúng cấu trúc bản mã AEAD

Một phép mã hóa AES-GCM thường nhận bốn đầu vào:

| Thành phần | Vai trò | Giữ bí mật? | Ràng buộc chính |
|---|---|---|---|
| **Key (K)** | Bí mật AES để mã hóa và xác thực | Có | Được tạo an toàn, giới hạn quyền và tuổi thọ |
| **Nonce/IV (N)** | Chọn luồng khóa cho từng phép mã hóa với K | Thường không | Không trùng cho cùng K |
| **Plaintext (P)** | Nội dung cần giữ bí mật | Có | Chỉ được sử dụng/tiết lộ theo chính sách |
| **AAD (A)** | Metadata được xác thực nhưng không mã hóa | Không nhất thiết | Phải trùng khi giải mã; dùng để ràng buộc ngữ cảnh |

Đầu ra gồm **ciphertext** và **authentication tag**. Bên giải mã cần đúng **K, N, A, ciphertext và tag**. Trong nhiều API, tag được nối vào cuối ciphertext; thứ tự lưu và độ dài phải được quy định rõ.

~~~mermaid
flowchart LR
    K["Khóa AES K"] --> E["AES-GCM encrypt"]
    N["Nonce duy nhất N"] --> E
    P["Bản rõ P"] --> E
    A["AAD"] --> E
    E --> C["Ciphertext + Tag"]
    N --> S["Lưu cùng ciphertext"]
    C --> S
    M["Key ID / version"] --> S
~~~

Lưu nonce bên cạnh ciphertext là thao tác thông thường; ví dụ một bản ghi có thể chứa:

~~~yaml
# Metadata minh họa, không phải format chung của mọi KMS
keyId: kms-records
keyVersion: v8
algorithm: AES-256-GCM
nonce: "<base64 12 bytes>"
ciphertextWithTag: "<base64 ban ma kem tag>"
aadContext:
  tenantId: tenant-42
  recordId: record-901
~~~

Nếu AAD chứa metadata nhạy cảm, nên cân nhắc lưu dưới hình thức phù hợp với chính sách bảo vệ dữ liệu. **AAD không được mã hóa bởi GCM**. Cần dựng đúng AAD khi đọc để ngăn tráo đổi bản mã giữa bản ghi hoặc tenant.

## 4. "Unique" khác "random" như thế nào?

**Unique** nói về **không trùng giá trị trong phạm vi sử dụng của một khóa**. **Random** nói về cách chọn giá trị. Hai khái niệm không đồng nghĩa:

- Một **bộ đếm** tăng đơn điệu, được cấp phát đúng và không tái sử dụng có thể tạo nonce duy nhất mà không cần nonce ngẫu nhiên.
- Một **nonce ngẫu nhiên** tạo từ CSPRNG có xác suất va chạm rất nhỏ nhưng **không được bảo đảm tuyệt đối** là duy nhất.
- Một giá trị như timestamp, ID bản ghi, số thứ tự trong bộ nhớ hoặc UUID tùy ý **không tự chứng minh** đủ duy nhất sau restart, trên nhiều máy hoặc qua quá trình migrate.
- **Đổi nonce nhưng giữ nguyên khóa**, nếu có sai sót trong cách sinh nonce, không xử lý được những cặp đã trùng trước đó.

Đối với AES-GCM, nonce **96 bit (12 byte)** là độ dài phổ biến và được ưu tiên trong nhiều hệ thống vì phù hợp đường xử lý chuẩn của GCM. Thuật toán có thể hỗ trợ độ dài nonce khác theo đặc tả, nhưng ứng dụng phải tuân theo hợp đồng của thư viện, giao thức hoặc dịch vụ KMS đang sử dụng. Không nên tự tùy chỉnh độ dài để "tăng bảo mật" mà không có thiết kế phù hợp.

### 4.1. Cách sinh nonce ngẫu nhiên

Với nonce 96 bit lấy độc lập, đều ngẫu nhiên từ CSPRNG, xác suất xảy ra **ít nhất một va chạm** trong q lần dùng dưới **cùng một khóa** được xấp xỉ theo bài toán ngày sinh (khi xác suất còn nhỏ):

\[
p \approx \frac{q(q-1)}{2 \cdot 2^{96}} = \frac{q(q-1)}{2^{97}}
\]

| Số phép mã hóa q dưới một khóa | Xác suất va chạm xấp xỉ |
|---|---|
| 1.000 | 6,3 × 10⁻²⁴ |
| 1.000.000 | 6,3 × 10⁻¹⁸ |
| 1.000.000.000 | 6,3 × 10⁻¹² |
| 2³² (khoảng 4,29 tỷ) | 1,16 × 10⁻¹⁰ |

Những con số này chỉ minh họa **rủi ro va chạm do sinh nonce ngẫu nhiên lý tưởng**, không phải đánh giá đầy đủ độ an toàn của AES-GCM: GCM còn có giới hạn theo **số lần gọi, số khối dữ liệu, xác suất giả mạo tag và cách triển khai**. Một số tiêu chuẩn đặt giới hạn chặt cho số lần gọi mã hóa với cách xây IV nhất định; phải tuân thủ giới hạn của cấu hình đã chọn.

Khi nhiều instance dùng chung khóa, **q là tổng số lần mã hóa của tất cả instance đó**. Không thể áp dụng giới hạn riêng cho từng instance rồi coi mỗi instance an toàn độc lập.

### 4.2. Cách sinh nonce có cấu trúc xác định

Một phương án thường gặp cho nonce 96 bit là chia thành:

~~~text
Nonce (96 bit) = Prefix (32 bit) || Counter (64 bit)
                 <------>          <------->
                vùng cố định       số tăng dần
~~~

Prefix có thể định danh miền ghi hoặc một giá trị cố định duy nhất trong phạm vi khóa; counter không được lặp trong miền prefix đó. Mỗi tổ hợp **(prefix, counter)** phải là duy nhất cho từng khóa.

Điểm mạnh: có thể bảo đảm tính duy nhất bằng thiết kế, **nếu**:

1. Không hai writer dùng cùng prefix khi counter có khả năng chồng lấn.
2. Counter không quay lại số cũ sau restart, rollback snapshot hoặc failover.
3. Counter không tràn; phải thay khóa hoặc thay namespace trước khi hết dải.
4. Mọi lần thử mã hóa tiêu thụ giá trị được cấp phát; không dùng lại chỉ vì thao tác trước đó lỗi hoặc bị hủy.
5. Việc cấp phát giá trị đi trước thao tác mã hóa được thực hiện đồng bộ và bền vững.

Cấu trúc này là ví dụ thiết kế, **không phải định dạng cố định cho mọi giao thức AES-GCM**. Nếu thư viện hoặc KMS tự sinh nonce, phải tuân thủ và lưu giá trị mà nó trả về thay vì áp cấu trúc riêng.

## 5. Vấn đề khó: nonce duy nhất trong hệ thống phân tán

Một chương trình chạy trên một máy có thể dễ dàng dùng bộ đếm; hệ thống nhiều instance phức tạp hơn vì các lỗi sau:

| Tình huống | Cách trùng nonce xuất hiện | Biện pháp |
|---|---|---|
| **Hai instance bắt đầu từ 0** | Cùng khóa, cùng prefix và cùng counter | Phân vùng namespace cố định duy nhất hoặc cấp phát tập trung |
| **Restart** | Counter chỉ lưu trong RAM bị đặt lại | Ghi trạng thái bền vững trước khi sử dụng |
| **Rollback snapshot/VM restore** | Counter quay về giá trị đã dùng | Cơ chế cấp phát ngoài snapshot hoặc thay khóa sau restore |
| **Failover** | Node dự phòng sử dụng lại dải counter của node chính | Lease/fencing token và dải đã cấp phát không trùng |
| **Autoscaling** | Bản sao service dùng cùng cấu hình prefix | Phân quyền cấp phát prefix, không sao chép cấu hình định danh |
| **Retry sau timeout** | Bản mã có thể đã được tạo nhưng client không nhận phản hồi | Cấp nonce mới cho lần thử mới; không dựa vào kết quả trả về để quyết định tái sử dụng |
| **Nhiều tenant dùng chung DEK** | Tưởng mỗi tenant có không gian nonce độc lập | Tách DEK theo tenant hoặc điều phối nonce chung trong phạm vi thực tế của khóa |
| **Khôi phục từ backup** | Khóa cũ và trạng thái counter cũ trở lại | Rà soát khả năng tái sử dụng; nếu không bảo đảm, dùng khóa mới |
| **Hai key alias cùng vật liệu** | Mỗi alias cấp nonce riêng với counter trùng | Theo dõi key material/version thực sự, không chỉ tên khóa |
| **Vượt dải counter** | Counter tràn và quay vòng | Giới hạn và rotate trước khi hết dải |

### 5.1. Phương án cấp phát dải counter

Nếu chọn chiến lược deterministic, một dịch vụ cấp phát số thứ tự có thể **đặt trước dải số không trùng** bằng cập nhật nguyên tử và bền vững:

~~~text
Key K, prefix cho writer W đã đăng ký:
  durable_next = 1000

Writer W cần 100 nonce:
  1. Atomically reserve [1000, 1099].
  2. Persist durable_next = 1100 thành công.
  3. Writer dùng lần lượt 1000, 1001, ..., 1099.
  4. Crash ở nonce 1030? Dải 1031..1099 có thể bị bỏ.
  5. Khi khởi động lại, xin dải mới từ >= 1100.
~~~

**Bỏ qua nonce chưa dùng thì an toàn; dùng lại nonce có thể đã dùng thì không an toàn.** Nếu không thể bảo đảm cập nhật bền vững trước khi dùng, hệ thống không thể chứng minh uniqueness sau crash.

Trong triển khai đa writer, phải bảo đảm **atomicity, linearizability hoặc cơ chế không chồng lấn tương đương**, cùng xử lý chia vùng và failover. Một biến đếm local hoặc khóa mutex trong một JVM chỉ bảo vệ các thread của JVM đó.

### 5.2. Khi nào nên dùng nonce ngẫu nhiên?

Nonce ngẫu nhiên 96 bit bằng **SecureRandom/CSPRNG** là cách đơn giản cho nhiều ứng dụng có tổng số lần mã hóa giới hạn và có chính sách thay khóa. Nó tránh phụ thuộc vào bộ cấp phát tập trung, nhưng rủi ro xác suất và giới hạn số lần mã hóa vẫn phải được đánh giá trên **toàn bộ lưu lượng cùng khóa**.

Đối với khối lượng mã hóa rất lớn, nhiều vùng triển khai hoặc yêu cầu không chấp nhận rủi ro va chạm theo xác suất, cân nhắc **cấu trúc nonce có bảo đảm không trùng** hoặc **nhiều DEK độc lập hơn**, tùy giao thức và hệ quản trị khóa. Không tùy tiện chuyển chiến lược sinh IV giữa chừng với cùng một khóa nếu các chiến lược có thể chồng lấn giá trị.

## 6. Code Java: mã hóa AES-GCM với nonce ngẫu nhiên

Ví dụ sau dùng **Java Cryptography Architecture (JCA)** để minh họa mỗi lần mã hóa có nonce 12 byte được sinh bằng **SecureRandom**. Khóa AES được tạo một lần để thể hiện phạm vi uniqueness theo khóa, rồi dùng cho hai bản ghi.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class NonceUniquenessExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_SIZE_BYTES = 12;  // 96-bit nonce
    private static final int TAG_SIZE_BITS = 128;

    public record Encrypted(byte[] nonce, byte[] ciphertextWithTag) {}

    public static Encrypted encrypt(
            SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {

        // Không hard-code, không tái sử dụng nonce từ lần mã hóa trước.
        byte[] nonce = new byte[NONCE_SIZE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_SIZE_BITS, nonce)
        );
        cipher.updateAAD(aad);
        return new Encrypted(nonce, cipher.doFinal(plaintext));
    }

    public static byte[] decrypt(
            SecretKey key, Encrypted record, byte[] aad)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_SIZE_BITS, record.nonce())
        );
        cipher.updateAAD(aad);

        // Sai key, nonce, ciphertext/tag hoặc AAD thường gây lỗi xác thực.
        return cipher.doFinal(record.ciphertextWithTag());
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] aad = "tenant=42".getBytes(StandardCharsets.UTF_8);
        Encrypted first = encrypt(
            key, "Ho so A".getBytes(StandardCharsets.UTF_8), aad
        );
        Encrypted second = encrypt(
            key, "Ho so B".getBytes(StandardCharsets.UTF_8), aad
        );

        if (Arrays.equals(first.nonce(), second.nonce())) {
            throw new IllegalStateException("Nonce collision detected");
        }

        byte[] recovered = decrypt(key, first, aad);
        if (!Arrays.equals(
                recovered, "Ho so A".getBytes(StandardCharsets.UTF_8))) {
            throw new IllegalStateException("Decryption mismatch");
        }
        System.out.println("AES-GCM round-trip OK");
    }
}
~~~

**Những điểm cần hiểu đúng:**

- Chương trình tạo **hai nonce khác nhau với xác suất cực cao**, nhưng câu lệnh so sánh chỉ phát hiện trùng trong hai lần gọi này; **không chứng minh tính duy nhất trên toàn hệ thống**.
- Với lưu lượng lớn, phải định lượng rủi ro va chạm, tổng số lần gọi và các giới hạn GCM theo phiên bản khóa. Chiến lược cấp phát deterministic có thể phù hợp hơn.
- Trong JCA, kết quả từ `doFinal` của AES-GCM thường bao gồm ciphertext kèm authentication tag. Khi decrypt, phải cấp đúng nonce và AAD; tag sai sẽ làm xác thực thất bại.
- Bản mã thực tế nên lưu **key ID/version, nonce và ciphertext/tag**. Không lưu **SecretKey dạng rõ** cùng bản mã.
- Mã demo giữ khóa trong RAM để minh họa. Hệ thống sản xuất phải quản lý DEK/KEK qua KMS/HSM hoặc quy trình tương đương và bảo vệ vòng đời khóa.

### 6.1. Pseudocode cho nonce deterministic

Để có bảo đảm mạnh về uniqueness, lớp mã hóa cần nhận một nonce đã được **cấp phát nguyên tử và bền vững**:

~~~java
// Pseudocode, không phải API có sẵn của Java hay nhà cung cấp KMS.
Encrypted encryptWithDurableNonce(
        KeyVersion key, byte[] plaintext, byte[] aad) {

    Nonce nonce = nonceAllocator.reserveNext(key.id(), key.version());
    // reserveNext phải bảo đảm cấp phát không trùng, không rollback,
    // và không tái sử dụng sau crash hay retry.

    return aesGcmEncrypt(
        key, nonce.to96BitArray(), plaintext, aad
    );
}
~~~

**Thứ tự quan trọng:** phải xác nhận nonce được cấp phát thành công và cập nhật trạng thái bền vững **trước khi mã hóa**. Nếu mã hóa không thành công, nonce đã cấp phát được coi là tiêu thụ; đừng trả nó về pool.

## 7. Quản lý nonce cùng key lifecycle

Nonce uniqueness là một **bất biến gắn với khóa thực tế**, nên quy trình tạo, sử dụng, rotation, thu hồi và hủy khóa phải xét đến không gian nonce.

~~~mermaid
flowchart TD
    A["Sinh DEK / key version mới"] --> B["Khởi tạo chiến lược nonce cho khóa"]
    B --> C["Cấp nonce chưa dùng"]
    C --> D["Mã hóa AEAD"]
    D --> E["Lưu ciphertext + nonce + tag + key version"]
    E --> F{"Còn trong giới hạn sử dụng?"}
    F -->|Có| C
    F -->|Không| G["Ngừng encrypt bằng phiên bản cũ"]
    G --> H["Chuyển sang key version mới"]
    H --> A
    G --> I["Chỉ decrypt dữ liệu cũ khi hợp lệ"]
    I --> J["Thu hồi / hủy theo chính sách"]
~~~

| Giai đoạn khóa | Tác động đến nonce |
|---|---|
| **Generation** | Sinh khóa thực sự mới bằng CSPRNG/KMS/HSM; chọn chiến lược nonce và giới hạn cho khóa ấy |
| **Provisioning** | Nếu nhiều writer dùng cùng khóa, phân phối quyền mã hóa kèm phương án cấp phát nonce không trùng |
| **Storage/usage** | Lưu key ID/version và nonce tương ứng với ciphertext; không để nhiều phiên bản bị nhầm lẫn |
| **Rotation** | Khi chuyển sang vật liệu khóa mới độc lập, không gian nonce của khóa mới được xét riêng; không cho phép reset nếu chỉ đổi alias mà giữ nguyên key material |
| **Revocation** | Ngừng mã hóa bằng khóa bị lộ hoặc bị thu hồi; đánh giá các bản mã chịu ảnh hưởng, kể cả sự cố trùng nonce |
| **Destruction** | Xem xét dữ liệu lịch sử và backup trước khi xóa khóa; hủy khóa không "chữa" bản rõ đã lộ |

Lưu ý quan trọng: **AES-GCM cần nonce duy nhất cho hoạt động mã hóa; decrypt dữ liệu cũ bắt buộc dùng lại nonce của bản mã đó**. Đó không phải là vi phạm uniqueness. Điều cấm là tạo **hai phép mã hóa khác nhau với cùng cặp (key, nonce)**.

## 8. Nonce trong envelope encryption và KMS/HSM

Một kiến trúc **envelope encryption** thường dùng DEK để mã hóa dữ liệu bằng AES-GCM và KEK trong KMS để bọc DEK:

~~~text
KMS/HSM quản lý KEK
    |
    +-- wrap DEK A --> encrypted DEK A
    |         |
    |         +-- AES-GCM(key=DEK A, nonce=N1) --> ciphertext A1
    |         +-- AES-GCM(key=DEK A, nonce=N2) --> ciphertext A2
    |
    +-- wrap DEK B --> encrypted DEK B
              |
              +-- AES-GCM(key=DEK B, nonce=N1) --> ciphertext B1
~~~

Đây là ví dụ hai DEK được tạo **độc lập và đủ mạnh**. Có thể có cùng chuỗi nonce N1 dưới DEK A và DEK B vì phạm vi uniqueness được tính riêng theo từng khóa. Tuy nhiên, nếu DEK A và DEK B thực tế là cùng vật liệu khóa dù có ID khác nhau, ví dụ trên **không an toàn**.

**Phân vai rõ:**

- **DEK:** khóa trực tiếp cho AES-GCM; yêu cầu nonce không trùng gắn với DEK này.
- **KEK:** khóa bảo vệ DEK; cơ chế wrap/unwrap có quy tắc riêng theo thuật toán (ví dụ AES Key Wrap, AES-GCM hoặc phương án của nhà cung cấp). Không áp quy tắc của AES-GCM cho mọi thuật toán wrap một cách máy móc.
- **KMS/HSM:** có thể sinh/giữ vật liệu khóa, thực hiện phép toán và cung cấp metadata; nếu KMS thực hiện mã hóa và tự quản lý nonce thì phải làm theo API của nó. Nếu ứng dụng tự dùng DEK dạng rõ để AES-GCM, **ứng dụng chịu trách nhiệm** về nonce của từng lần mã hóa đó.

### Ví dụ phân tách DEK theo đối tượng

Hệ thống lưu tài liệu nhiều tenant có thể chọn **một DEK trên mỗi tài liệu**. Nếu mỗi tài liệu chỉ mã hóa một lần với DEK riêng, nonce uniqueness trở nên dễ quản lý hơn. Nếu tài liệu có nhiều phiên bản/chunk hoặc được chỉnh sửa và ghi lại dưới cùng DEK, vẫn phải cấp nonce khác cho từng lần mã hóa.

Không nên cho rằng "mỗi file có ID khác nhau" có nghĩa mỗi lần mã hóa có nonce khác. Hai lần ghi file có cùng ID không thể dùng nonce cũ khi khóa giữ nguyên.

## 9. Khi nào cần đổi khóa thay vì tiếp tục cấp nonce?

Một khóa có giới hạn về lượng dữ liệu, số lần sử dụng và khoảng thời gian hoạt động. Bất kể dùng counter hay nonce ngẫu nhiên, nên có **ngưỡng an toàn được định nghĩa trước**:

1. Gắn tổng số lần encrypt với **key version** và phạm vi writer thực tế.
2. Xác định giới hạn theo thuật toán, thư viện, tiêu chuẩn nội bộ và mô hình rủi ro; theo dõi trước khi đạt ngưỡng.
3. Chuyển đường mã hóa mới sang DEK/key version mới khi sắp đạt giới hạn.
4. Giữ bản mã lịch sử cùng nonce và key version để giải mã bằng khóa cũ khi còn hợp lệ.
5. Không sử dụng cùng vật liệu khóa dưới tên mới để "làm mới" bộ đếm.
6. Khi không chắc đã có nonce trùng sau restart/restore, ưu tiên **ngừng encrypt bằng khóa liên quan và tạo khóa mới** trong lúc đánh giá ảnh hưởng.

Việc đổi khóa **sau khi phát hiện reuse** chỉ giới hạn tổn hại tương lai. Các bản mã đã tạo bằng cặp (K, N) trùng vẫn cần được đánh giá, có thể phải thay DEK và mã hóa lại nếu còn kiểm soát được bản rõ.

## 10. Các lỗi triển khai thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách phòng tránh |
|---|---|---|
| Gán nonce cố định toàn số 0 cho mọi bản ghi cùng khóa | Lặp keystream và phá xác thực GCM | Sinh/đặt trước nonce mới cho mỗi lần encrypt |
| Dùng timestamp theo mili giây làm nonce | Hai thao tác có thể cùng thời gian; đồng hồ đảo ngược | Dùng CSPRNG phù hợp hoặc bộ đếm được cấp phát bền vững |
| Reset counter sau restart | Nonce cũ được dùng lại | Lưu high-water mark bền vững trước khi mã hóa |
| Clone máy ảo với khóa và counter cùng trạng thái | Hai nhánh tạo trùng nonce | Cấp phát nonce ngoài snapshot hoặc rotate key khi restore |
| Mỗi thread/instance dùng counter bắt đầu từ 1 | Các writer tạo giá trị trùng nhau | Prefix duy nhất, phân dải hoặc service cấp phát tập trung |
| Retry dùng lại nonce đã dùng với bản rõ mới | Có thể tạo bản mã khác dưới cùng cặp (K,N) | Cấp nonce mới cho lần mã hóa mới |
| Chỉ kiểm tra trùng trong một process | Bỏ sót va chạm giữa các instance, vùng hoặc bản sao lưu | Thiết kế uniqueness cho toàn bộ phạm vi khóa |
| Coi UUID hoặc ID bản ghi là nonce duy nhất | Có thể trùng sau cắt độ dài, nhập dữ liệu, tái sử dụng ID | Có chiến lược sinh nonce đã phân tích, tránh chuyển đổi tùy tiện |
| Đổi key alias nhưng tái dùng key material và reset counter | Phạm vi nonce thực tế chưa đổi | Chỉ reset namespace khi dùng khóa mới độc lập |
| Nhầm nonce với AAD/salt | Thêm AAD hay salt không làm nonce cũ thành mới | Tách trách nhiệm từng đầu vào mật mã |
| Không lưu nonce trong ciphertext metadata | Không thể giải mã hoặc nhầm nonce từ bản ghi khác | Lưu nonce và phiên bản đúng cùng bản mã |
| Bỏ qua tag khi decrypt hoặc xử lý lỗi xác thực tùy tiện | Có thể dùng dữ liệu bị sửa hoặc không kiểm tra được | Dùng AEAD và từ chối dữ liệu khi xác thực thất bại |
| Rewrap KEK nhưng nghĩ đã đổi DEK | Không thay phạm vi nonce hay rủi ro đã có ở DEK cũ | Theo dõi đúng vật liệu DEK, quyết định re-encrypt khi cần |

## 11. Giám sát, kiểm thử và kiểm toán nonce uniqueness

Một hệ thống quan trọng cần coi việc cấp phát nonce là **bất biến an toàn có thể kiểm chứng**.

**Những thứ nên kiểm thử:**

- **Nhiều writer đồng thời:** khởi chạy nhiều instance cùng lúc và xác minh cơ chế cấp phát không trả cùng cặp (key version, nonce).
- **Restart/crash:** dừng ngay sau khi cấp dải nonce; khởi động lại và kiểm tra không cấp lại phần đã có thể sử dụng.
- **Retry/timeouts:** gửi lại thao tác sau lỗi mạng; kiểm tra việc không mã hóa bản rõ mới với nonce đã tiêu thụ.
- **Backup/restore/failover:** khôi phục trạng thái cũ và chứng minh không quay lại dải counter từng được sử dụng.
- **Rotate key:** xác minh phiên bản mới dùng vật liệu độc lập, phân biệt rõ metadata và quyền sử dụng.
- **Độ bền của giới hạn:** vượt ngưỡng kiểm soát số lần mã hóa phải báo lỗi hoặc buộc chuyển khóa.
- **AAD/tag:** thay AAD hoặc sửa bản mã/tag phải khiến decrypt thất bại; không chấp nhận dữ liệu chưa xác thực.

Với **nonce ngẫu nhiên**, việc tạo một triệu nonce trong test mà không có va chạm **không chứng minh** không thể xảy ra va chạm; kiểm thử ở đây nhằm phát hiện lỗi lập trình, RNG bị giả lập, seed sai hoặc nhầm lẫn khóa. Đánh giá rủi ro còn cần lập luận xác suất, tiêu chuẩn và giới hạn vận hành.

**Theo dõi khi vận hành:** số lượt mã hóa theo key version, số dải nonce đã cấp, giới hạn gần đạt, thay đổi key policy, số lần decrypt lỗi tag tăng bất thường và sự kiện restore/snapshot. Log cần ghi **key ID/version, sự kiện, danh tính và kết quả** ở mức phù hợp, tránh ghi key material, plaintext hoặc AAD nhạy cảm.

Do nonce thường công khai, việc log **một nonce riêng lẻ** không phải tương đương log khóa bí mật; tuy nhiên metadata và tổ hợp định danh có thể nhạy cảm, và việc kiểm toán phải tuân thủ chính sách bảo vệ dữ liệu.

## 12. Nếu phát hiện nonce đã bị tái sử dụng thì phải làm gì?

Xử lý như một **sự cố mật mã**, không chỉ lỗi format hay lỗi dữ liệu:

1. **Ngừng hoặc cô lập luồng encrypt đang vi phạm**; chặn tạo thêm bản mã bằng khóa và cơ chế sinh nonce liên quan.
2. **Xác định cặp khóa/nonce và phạm vi**: key material hoặc key version thực tế, tenant, đối tượng, thời gian, instances và backup.
3. **Đánh giá dữ liệu đã lộ**: nếu các bản mã với cặp trùng đã bị quan sát, nguy cơ lộ thông tin và giả mạo tag có thể nghiêm trọng; ngay cả khi chưa có dấu hiệu đọc trái phép vẫn cần xem xét ảnh hưởng.
4. **Khắc phục nguyên nhân gốc**: bộ cấp phát, crash/restore, race condition, bộ đếm, thao tác chuyển phiên bản hoặc chiến lược random.
5. **Dùng khóa mới độc lập** cho đường ghi mới; sửa chính sách cấp nonce và quyền sử dụng.
6. **Mã hóa lại những dữ liệu bị ảnh hưởng** với DEK mới và nonce được quản lý đúng khi có thể; cập nhật metadata và kiểm chứng giải mã.
7. **Kiểm toán và phản ứng sự cố** theo quy trình tổ chức; xem xét nghĩa vụ thông báo, lưu chứng cứ và đánh giá các dữ liệu mà bên tấn công đã có thể giải mã.

**Không có phép "sửa nonce" an toàn bằng cách đổi field nonce trong metadata của bản mã cũ.** Để tạo cặp bản mã/nonce mới hợp lệ, phải thực hiện **một phép mã hóa lại** với khóa và nonce thích hợp; thay byte nonce đơn thuần làm kiểm tra xác thực thất bại.

Tương tự, **rotation KEK** trong envelope encryption không tự khắc phục reuse dưới **DEK cũ**. Nếu lỗi nằm ở nonce của DEK, cần đánh giá DEK và các bản mã đã tạo dưới nó.

## 13. Nonce uniqueness và các chế độ mật mã khác

Yêu cầu cụ thể cần đọc từ **thuật toán và giao thức**:

| Chế độ/thuật toán | Điều cần chú ý |
|---|---|
| **AES-GCM** | Tính duy nhất của nonce với mỗi khóa là yêu cầu nghiêm ngặt; reuse có thể phá tính bí mật và xác thực |
| **AES-CTR** | Không được dùng lại cùng luồng counter/keystream với cùng khóa; đảm bảo các khối counter không chồng lấn |
| **ChaCha20-Poly1305 (IETF)** | Nonce 96 bit phải không trùng với cùng khóa; reuse gây hậu quả nghiêm trọng cho cả tính bí mật và xác thực |
| **AES-CBC** | IV có quy tắc riêng, điển hình cần **không thể dự đoán** đối với CBC encryption; không áp dụng máy móc công thức nonce của GCM |
| **AES-GCM-SIV / AES-SIV** | Thiết kế để chống chịu một số tình huống dùng sai nonce tốt hơn GCM, với các đặc tính/giới hạn riêng; không phải lý do bỏ quản lý nonce và khóa |

Một **nonce reuse-resistant AEAD** như AES-GCM-SIV có thể giảm tác hại của một số sai sót, nhưng không thay thế kiểm soát key lifecycle, tính xác thực danh tính, phân quyền hay đánh giá giới hạn và thuật toán. Không tự ý thay đổi chế độ mã hóa khi định dạng dữ liệu và hai bên giao thức chưa tương thích.

**Nonce uniqueness cũng khác chống replay.** Kẻ tấn công có thể phát lại **nguyên bản một ciphertext/tag/nonce hợp lệ** mà không tạo bản mã mới. AES-GCM vẫn có thể xác thực bản mã cũ thành công; chống replay cần **sequence number, timestamp, phiên giao dịch, trạng thái đã xử lý hoặc cơ chế giao thức**. Không có phép mã hóa AEAD nào tự động ngăn replay mọi bản tin.

## 14. Hỏi và đáp nhanh

**Câu 1. Nonce có cần mã hóa hoặc giấu kín như khóa không?**

Không. Với AES-GCM, nonce thường được lưu cùng ciphertext. Tính **duy nhất theo khóa** quan trọng hơn việc giữ nonce bí mật.

**Câu 2. Nếu thay key mới thì có được sử dụng lại chuỗi nonce từng dùng với key cũ không?**

Được nếu **khóa mới có vật liệu độc lập an toàn** và thuật toán cho phép. Phạm vi uniqueness theo key material. Chỉ đổi alias/key ID không đủ.

**Câu 3. Có được dùng lại nonce cũ khi decrypt không?**

Có, **phải** dùng đúng nonce của lần encrypt tạo bản mã ấy. Điều cấm là thực hiện **hai lần mã hóa mới khác nhau** bằng cùng cặp (key, nonce) trong AES-GCM.

**Câu 4. Cùng key, cùng nonce nhưng AAD khác nhau có an toàn không?**

Không. AAD khác không khắc phục reuse của cặp (key, nonce).

**Câu 5. SecureRandom bảo đảm nonce không bao giờ trùng?**

Không. SecureRandom giúp lấy các byte khó dự đoán và phù hợp cho mật mã; với nonce ngẫu nhiên hữu hạn, xác suất va chạm vẫn khác 0. Phải xét giới hạn số lần gọi dưới cùng key.

**Câu 6. Mỗi server có bộ đếm nonce riêng bắt đầu từ 0 có được không?**

Chỉ khi các server được bảo đảm không tạo cùng nonce dưới cùng key, chẳng hạn prefix riêng không trùng hoặc dải counter cấp phát bền vững. Không có cơ chế này thì không an toàn.

**Câu 7. Có thể dùng thời gian hiện tại làm nonce không?**

Timestamp đơn thuần không chứng minh tính duy nhất khi nhiều thao tác cùng thời điểm hoặc đồng hồ bị điều chỉnh/rollback. Cần thiết kế cấp phát thật sự không trùng.

**Câu 8. Sau khi phát hiện trùng nonce, chỉ sửa metadata nonce có giải quyết được không?**

Không. Bản mã GCM gắn với nonce đã dùng khi mã hóa. Phải đánh giá sự cố và mã hóa lại bằng cặp khóa/nonce an toàn nếu cần.

**Câu 9. Mỗi đối tượng có DEK mới thì có cần quan tâm nonce uniqueness?**

Có. Nếu một DEK chỉ mã hóa đúng một đối tượng đúng một lần thì rất dễ đáp ứng; nếu đối tượng được ghi lại, chia chunk hoặc mã hóa nhiều lần dưới cùng DEK, vẫn phải cấp nonce không trùng.

**Câu 10. Nonce duy nhất có ngăn phát lại ciphertext không?**

Không. Cần cơ chế chống replay ở tầng giao thức/ứng dụng.

## 15. Checklist áp dụng trong thiết kế

Trước khi đưa hệ thống AES-GCM vào sản xuất, nên trả lời được các câu hỏi sau:

- **Key scope:** Một DEK được chia sẻ giữa bao nhiêu tenant, bản ghi, worker và vùng triển khai? Làm sao nhận biết các key alias trỏ cùng key material?
- **Nonce construction:** Dùng CSPRNG ngẫu nhiên hay cấu trúc deterministic? Vì sao phù hợp với số lượng encrypt và giới hạn GCM?
- **Uniqueness under failure:** Có chứng minh không trùng sau **crash, restart, retry, rollback, restore, failover và autoscaling** không?
- **Versioning:** Dữ liệu lưu đúng key ID/version, nonce, tag và AAD cần thiết chưa? Có giới hạn số lượt encrypt theo phiên bản không?
- **Lifecycle:** Khi gần hết nonce space, đến cryptoperiod hoặc khóa bị thu hồi, hệ thống tạo khóa mới và chuyển đường ghi ra sao?
- **Controls:** Ai được tạo/đọc DEK, encrypt/decrypt, rotate key và chỉnh allocator? Audit log có đủ để điều tra mà không tiết lộ bí mật không?
- **Incident response:** Nếu phát hiện reuse, có thể dừng ghi, tìm dữ liệu bị ảnh hưởng và mã hóa lại với DEK mới không?

**Ghi nhớ:** **Nonce uniqueness là thuộc tính của cặp (khóa, nonce) và của toàn bộ hệ thống cấp phát, không chỉ một lời gọi hàm mã hóa.** Khi dùng AES-GCM, phải bảo đảm mỗi phép **encrypt** bằng một khóa sử dụng nonce chưa từng dùng trước đó với khóa ấy; quản lý đúng điều này xuyên suốt **ứng dụng, môi trường phân tán, KMS/HSM, envelope encryption và vòng đời khóa**.
