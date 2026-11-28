# AES-GCM: Mã hóa đối xứng có xác thực và quản lý khóa an toàn

Khi mã hóa thông tin khách hàng, dữ liệu đơn hàng hoặc bản sao lưu, chỉ che giấu nội dung là chưa đủ. Hệ thống còn cần phát hiện bản mã bị sửa, tráo hoặc giải mã dưới ngữ cảnh không phù hợp. **AES-GCM (Advanced Encryption Standard – Galois/Counter Mode)** là chế độ mã hóa đối xứng có xác thực (*Authenticated Encryption with Associated Data*, viết tắt **AEAD**): cùng một phép mã hóa cung cấp **tính bí mật của plaintext** và **khả năng kiểm tra tính toàn vẹn, tính xác thực mật mã của ciphertext và dữ liệu liên kết**.

AES-GCM được sử dụng rộng rãi để bảo vệ dữ liệu ứng dụng, gói tin và bản ghi lưu trữ. Tuy nhiên, an toàn của AES-GCM phụ thuộc nghiêm ngặt vào cách quản lý **key material**, **nonce/IV**, **authentication tag** và **associated data (AAD)**. Đặc biệt, **tái sử dụng cùng nonce với cùng khóa AES-GCM có thể phá vỡ nghiêm trọng cả tính bí mật lẫn tính xác thực**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này kết nối AES-GCM với vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy; đồng thời giải thích vai trò của KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích AES-GCM là gì, nó bảo vệ những gì và khác gì so với chỉ mã hóa bằng AES-CBC.
2. Phân biệt **khóa AES**, **nonce/IV**, **AAD**, **ciphertext** và **authentication tag**.
3. Thiết kế nonce không trùng trong phạm vi **cùng khóa**, kể cả khi hệ thống có nhiều instance, retry và khôi phục sau sự cố.
4. Mã hóa/giải mã AES-GCM bằng Java 17 với AAD và xử lý lỗi xác thực.
5. Dùng AES-GCM cùng DEK, KEK, KMS/HSM và quy trình rotation/recovery mà không đánh đồng mã hóa dữ liệu với quản lý khóa.

## 2. AES-GCM là gì?

**AES** là thuật toán mã khối đối xứng sử dụng một khóa bí mật để mã hóa và giải mã. AES có **kích thước khối 128 bit**, hỗ trợ độ dài khóa **128, 192 hoặc 256 bit**. **GCM** là một chế độ vận hành của mã khối AES, kết hợp cơ chế kiểu **counter mode (CTR)** để mã hóa với phép xác thực dựa trên **GHASH** để tạo authentication tag.

Không gọi GCM là một thuật toán khóa bất đối xứng: cùng một **khóa bí mật AES** được sử dụng ở hai đầu mã hóa và giải mã. Thông số **AES-256-GCM** có nghĩa **khóa AES dài 256 bit**, còn kích thước khối của AES vẫn là 128 bit.

Một lần mã hóa AEAD có dạng khái niệm:

~~~text
Encrypt(
    key        = AES secret key,
    nonce      = giá trị duy nhất với key này,
    plaintext  = dữ liệu cần giữ bí mật,
    aad        = dữ liệu cần xác thực nhưng không mã hóa
) -> ciphertext + authenticationTag

Decrypt(
    key, nonce, ciphertext, authenticationTag, aad
) -> plaintext nếu xác thực thành công
   -> lỗi xác thực nếu key/nonce/ciphertext/tag/aad không hợp lệ
~~~

### 2.1. Hai cam kết bảo mật của AEAD

| Thuộc tính | AES-GCM thực hiện thế nào? | Giới hạn phải hiểu |
|---|---|---|
| **Confidentiality – bí mật** | Che nội dung plaintext bằng khóa AES và nonce | Nonce trùng với cùng khóa có thể làm rò rỉ quan hệ giữa các plaintext |
| **Integrity/authenticity – toàn vẹn và tính xác thực mật mã** | Authentication tag giúp phát hiện thay đổi dữ liệu được bảo vệ khi giải mã | Không chứng minh **danh tính người gửi** như một chữ ký số; các bên giữ cùng symmetric key đều có thể tạo tag |
| **AAD binding – ràng buộc ngữ cảnh** | Dữ liệu AAD được đưa vào tính tag nhưng không được mã hóa | AAD không được giữ bí mật; cả hai phía phải dùng đúng cùng byte AAD |
| **Replay resistance – chống phát lại** | **Không có sẵn** | Bản mã cũ nguyên vẹn có thể được phát lại và vẫn xác minh thành công; cần sequence ID/version/policy ở tầng ứng dụng |

AES-GCM **không thay thế IAM, authorization, chữ ký số hoặc KMS**. Một người có quyền gọi dịch vụ giải mã có thể đọc plaintext qua API dù không thể lấy byte khóa từ HSM.

## 3. Năm thành phần cần quản lý chính xác

| Thành phần | Vai trò | Bí mật? | Lưu ý |
|---|---|---|---|
| **AES key** | Key material bí mật dùng để mã hóa và xác thực | **Có** | Dùng CSPRNG/KMS sinh; không ghi vào code, log hoặc metadata bản ghi |
| **Nonce/IV** | Đầu vào biến đổi cho mỗi lần mã hóa với một khóa | Không | 96 bit (12 byte) là lựa chọn thông dụng của GCM; **phải duy nhất trong phạm vi cùng khóa** |
| **Plaintext** | Dữ liệu cần bảo vệ | Thường có | Không ghi vào log hay phát cho bên chưa được cấp quyền |
| **AAD** | Metadata được xác thực nhưng **không mã hóa** | Không theo cơ chế AEAD | Ví dụ tenant ID, loại dữ liệu, record ID, key ID/version theo quy tắc chuẩn hóa |
| **Authentication tag** | Giá trị xác thực của bản mã và AAD | Không | Thông dụng 128 bit (16 byte); không bỏ qua kết quả xác minh tag |
| **Ciphertext** | Dữ liệu sau mã hóa | Không phải khóa | Thường lưu cùng nonce, tag và metadata cần thiết |

Nonce không phải khóa, cũng không cần che giấu. Tuy nhiên, **không được dùng lại nonce với cùng một khóa**, kể cả khi hai lần mã hóa có plaintext khác nhau hoặc diễn ra trên hai máy khác nhau. Tag có thể lưu cùng ciphertext; việc công bố tag không đồng nghĩa để lộ khóa.

### 3.1. Luồng mã hóa và giải mã

~~~mermaid
flowchart LR
    P["Plaintext"] --> E["AES-GCM Encrypt"]
    K["AES key bí mật"] --> E
    N["Nonce duy nhất / key"] --> E
    A["AAD"] --> E
    E --> C["Ciphertext"]
    E --> T["Authentication tag"]
    C --> D["AES-GCM Decrypt + Verify"]
    T --> D
    K --> D
    N --> D
    A --> D
    D -->|Tag hợp lệ| OK["Plaintext"]
    D -->|Tag sai| FAIL["Từ chối giải mã"]
~~~

Ở Java/JCA, khi dùng **AES/GCM/NoPadding**, lệnh **Cipher.doFinal** khi mã hóa thường trả về **ciphertext ghép với tag** trong cùng mảng byte; cách đóng gói có thể khác giữa thư viện và giao thức. Nếu lưu một trường **ciphertextWithTag**, không tự giả định tag đã được lưu riêng.

### 3.2. Vì sao GCM không cần padding?

AES có kích thước khối 16 byte, nhưng GCM vận hành phần mã hóa theo kiểu counter stream nên xử lý được plaintext không chia hết cho 16 byte. Vì vậy Java dùng tên biến đổi **AES/GCM/NoPadding**. **NoPadding** không có nghĩa không kiểm tra toàn vẹn; GCM vẫn tạo và xác minh authentication tag.

## 4. Nonce/IV: điều kiện sống còn của AES-GCM

Với một khóa AES cố định, GCM biến nonce và các counter thành luồng khóa dùng XOR với plaintext. Nếu lặp lại **cùng khóa + cùng nonce**, các luồng khóa sẽ trùng nhau. Khi đó hai ciphertext có thể bộc lộ quan hệ:

\[
C_1 \oplus C_2 = P_1 \oplus P_2
\]

trong phần được mã hóa bằng cùng luồng khóa. Nếu một plaintext đã biết hoặc dễ đoán, kẻ tấn công có thể suy ra nội dung của plaintext khác. Tái sử dụng nonce còn gây hậu quả nghiêm trọng cho **xác thực GCM**, có thể dẫn tới giả mạo tag trong những điều kiện tấn công phù hợp. Vì vậy đây không phải lỗi “chỉ làm yếu bảo mật một chút”.

### 4.1. Nonce 96 bit và tag 128 bit

- **Nonce 96 bit (12 byte)** là dạng phổ biến, được GCM xử lý hiệu quả và thuận lợi cho thiết kế tương thích.
- **Tag 128 bit (16 byte)** là lựa chọn mặc định hợp lý trong nhiều hệ thống mới. Một số chuẩn cho phép độ dài tag khác, nhưng việc rút ngắn tag giảm biên độ chống giả mạo và chịu các giới hạn sử dụng nghiêm ngặt hơn.
- Độ dài khóa AES 128 hoặc 256 bit **không tự bù được** cho lỗi trùng nonce; đổi từ AES-128 lên AES-256 không sửa được thiết kế nonce sai.
- Nonce có thể được lưu công khai cạnh ciphertext. Điều quan trọng là **không trùng cho mỗi lần sử dụng cùng khóa**, không phải “nonce phải ngẫu nhiên tuyệt đối”.

### 4.2. Hai chiến lược cấp nonce phổ biến

| Cách cấp nonce | Ưu điểm | Những điều kiện phải kiểm soát |
|---|---|---|
| **Ngẫu nhiên 96 bit bằng CSPRNG** | Đơn giản, không cần chia sẻ bộ đếm giữa các instance | Có xác suất va chạm tăng theo số lần mã hóa cùng khóa; phải giới hạn lượng invocation theo key và xoay key đúng hạn |
| **Nonce xác định, không trùng (unique counter/sequence)** | Có thể chứng minh không trùng nếu cấp phát đúng | Phải phối hợp nhiều instance, persistence qua crash/restore, chống reset, rollover và trùng phạm vi prefix |

Ví dụ bố trí nonce xác định 96 bit: một **prefix phân vùng duy nhất trong phạm vi khóa** kết hợp bộ đếm tăng đơn điệu. Nếu dùng hai instance, chúng không được tự chọn cùng prefix. Nếu restore snapshot khiến bộ đếm quay lùi, bản ghi mới có thể tái sử dụng nonce đã dùng trước đây. Cần cơ chế phân phối, lưu trạng thái bền vững và ngăn tái sử dụng sau failover.

Khi dùng nonce random, xác suất va chạm tuân theo hiệu ứng *birthday*: về xấp xỉ, sau \(n\) lần mã hóa với một khóa, xác suất có ít nhất một cặp nonce 96 bit trùng nhau khoảng \(n(n-1)/2^{97}\) khi xác suất còn nhỏ. Do đó không có nghĩa “96 bit đủ để mã hóa vô hạn lần”. Hướng dẫn GCM như **NIST SP 800-38D** đặt các điều kiện và giới hạn số lần invocation tùy cách xây dựng IV; thiết kế production phải thực hiện giới hạn chặt hơn nếu chính sách hoặc nhà cung cấp yêu cầu.

**Không tạo nonce bằng mỗi timestamp, ID người dùng, hash plaintext hoặc bộ đếm được reset khi khởi động.** Không tái sử dụng nonce cho một yêu cầu retry nếu retry thực sự thực hiện **lần mã hóa mới** với cùng khóa. Nếu cần xử lý retry, hãy lưu kết quả đã mã hóa như một thao tác idempotent hoặc cấp nonce mới an toàn.

### 4.3. Khi nào xoay khóa thay vì tăng nonce?

Nonce chỉ cần duy nhất **trong phạm vi một khóa**: hai khóa AES khác nhau có thể dùng cùng giá trị nonce mà không tạo ra lỗi reuse cùng key. Nhưng vòng đời khóa phải có giới hạn số lần mã hóa và lượng dữ liệu theo chính sách. Khi sắp chạm giới hạn nonce, số lượng thao tác, thời gian sử dụng hoặc xuất hiện nghi vấn rò rỉ, hãy tạo **DEK/phiên bản khóa mới** và ngừng mã hóa mới bằng khóa cũ. Dữ liệu cũ vẫn cần cơ chế giải mã phù hợp.

## 5. AAD: ràng buộc dữ liệu mã hóa với đúng ngữ cảnh

**Associated Authenticated Data (AAD)** là dữ liệu được xác thực bởi GCM nhưng **không được mã hóa**. Phía giải mã phải cung cấp **chính xác chuỗi byte AAD đã dùng khi mã hóa**. Chỉ cần thay đổi một byte, kiểm tra tag sẽ thất bại với xác suất rất cao.

Ví dụ một ciphertext chứa thông tin của khách hàng thuộc tenant A:

| Trường | Đưa vào AAD? | Lý do |
|---|---|---|
| **tenantId** | Có, nếu cần ràng buộc tenant | Ngăn bản mã dùng sai tenant khi ứng dụng xác thực đúng tenant |
| **objectId / recordId** | Có, nếu cần ràng buộc vị trí dữ liệu | Hạn chế tráo ciphertext giữa các record khác nhau |
| **keyId / keyVersion** | Có thể và thường hữu ích | Gắn phép xác thực với tham chiếu khóa/phiên bản được sử dụng |
| **schemaVersion / formatVersion** | Nên có khi định dạng thay đổi theo thời gian | Ngăn parse nhầm các phiên bản nội dung |
| **plaintext bí mật** | **Không** | AAD không được mã hóa; plaintext phải nằm trong đầu vào cần mã hóa |

**AAD không thay thế kiểm tra quyền.** Ví dụ request B gửi kèm giá trị tenantId=A không được phép để ứng dụng tự dùng AAD=A rồi giải mã dữ liệu của tenant A. Tenant phải được suy ra từ **danh tính đã xác thực** và chính sách truy cập, sau đó mới tạo AAD.

Thứ tự trường, encoding, kiểu số, chữ hoa/thường và cách biểu diễn JSON có thể làm byte AAD khác nhau. Với nhiều trường, nên dùng định dạng chuẩn hóa, **có version và có độ dài trường** hoặc một canonical encoding rõ ràng. Tránh ghép chuỗi bằng dấu phân cách tùy ý: nếu dữ liệu có chứa dấu phân cách, hai bộ giá trị khác nhau có thể thành cùng chuỗi.

## 6. Ví dụ Java 17: AES-256-GCM với AAD và xác minh tag

Đoạn mã sử dụng **Java Cryptography Architecture (JCA)**, có thể chạy với JDK 17+. Ví dụ minh họa cấu trúc lưu trữ AES-GCM và cách ràng buộc **tenant, key ID, key version** vào AAD. Để dễ quan sát, chương trình sinh một khóa trong bộ nhớ; hệ thống production cần kết nối với bộ cấp phát khóa/KMS và kiểm soát quyền sử dụng thích hợp.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_SIZE = 12; // 96 bit
    private static final int TAG_BITS = 128;

    public record EncryptedRecord(
            String keyId,
            String keyVersion,
            String nonceBase64,
            String ciphertextWithTagBase64
    ) {}

    // AAD có cấu trúc ổn định: mỗi trường UTF-8 có prefix độ dài.
    // Bên mã hóa và giải mã phải dùng cùng formatVersion và thứ tự trường.
    private static byte[] aad(String tenantId, String keyId,
                              String keyVersion) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(out)) {
            for (String field : List.of(
                    "format-v1", "AES-256-GCM",
                    tenantId, keyId, keyVersion)) {
                byte[] value = field.getBytes(StandardCharsets.UTF_8);
                data.writeInt(value.length);
                data.write(value);
            }
        }
        return out.toByteArray();
    }

    public static EncryptedRecord encrypt(
            SecretKey dek, String tenantId, String keyId,
            String keyVersion, byte[] plaintext) throws Exception {
        byte[] nonce = new byte[NONCE_SIZE];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(tenantId, keyId, keyVersion));

        // Với JCA: ciphertext và authentication tag cùng trong byte[].
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);
        return new EncryptedRecord(
                keyId,
                keyVersion,
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextWithTag));
    }

    public static byte[] decrypt(SecretKey resolvedDek,
                                 String authenticatedTenant,
                                 EncryptedRecord record) throws Exception {
        byte[] nonce = Base64.getDecoder().decode(record.nonceBase64());
        if (nonce.length != NONCE_SIZE) {
            throw new GeneralSecurityException("Invalid nonce length");
        }

        byte[] ciphertextWithTag = Base64.getDecoder()
                .decode(record.ciphertextWithTagBase64());
        if (ciphertextWithTag.length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Missing authentication tag");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, resolvedDek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(authenticatedTenant,
                record.keyId(), record.keyVersion()));
        return cipher.doFinal(ciphertextWithTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey demoDek = generator.generateKey();

        EncryptedRecord stored = encrypt(
                demoDek, "tenant-42", "customer-data-key", "v1",
                "Thông tin bí mật".getBytes(StandardCharsets.UTF_8));

        byte[] restored = decrypt(demoDek, "tenant-42", stored);
        System.out.println(new String(restored, StandardCharsets.UTF_8));

        try {
            decrypt(demoDek, "tenant-OTHER", stored);
            throw new IllegalStateException("Must reject wrong tenant");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong tenant AAD rejected");
        }

        // Không log demoDek.getEncoded(), raw DEK hay plaintext thực tế.
    }
}
~~~

Lưu chương trình thành **AesGcmExample.java** và chạy bằng:

~~~bash
javac AesGcmExample.java
java AesGcmExample
~~~

Kết quả minh họa gồm plaintext đã khôi phục và dòng **Wrong tenant AAD rejected**. Nếu thay ciphertext, tag, nonce, key hoặc AAD, thao tác xác minh thông thường thất bại, trong JCA thường bằng **AEADBadTagException**.

### 6.1. Điều quan trọng khi chuyển từ demo sang production

1. **Khóa mã hóa phải được resolve đúng.** Trong demo, hàm **decrypt** được truyền sẵn **resolvedDek**. Chuỗi **keyId** và **keyVersion** không tự tìm ra khóa, cũng không tự chứng minh người gọi được quyền giải mã. Tầng KMS/repository phải thực hiện resolve, kiểm tra tenant và authorization trước khi dùng khóa.
2. **Nonce random không dành cho số lần mã hóa vô hạn.** Ví dụ tạo nonce ngẫu nhiên 12 byte cho mỗi lần, phù hợp demo. Hệ thống thực tế phải theo dõi/giới hạn số lần dùng **mỗi DEK**, có kế hoạch rotation hoặc cấp phát nonce xác định duy nhất.
3. **AAD phải có cùng cách đóng gói ở hai phía.** Code dùng chuỗi UTF-8 có prefix độ dài và format version. Nếu đổi thuật toán, schema hoặc định dạng AAD, phải version hóa và duy trì khả năng đọc dữ liệu cũ.
4. **Không trả plaintext trước khi xác minh xong tag.** Nếu thư viện/luồng xử lý cung cấp plaintext từng phần trước khi AEAD hoàn thành, không phát các byte chưa được xác thực ra API, file hoặc nghiệp vụ.
5. **Tag thất bại phải được xử lý như lỗi xác thực.** Không thử tự giải mã bằng mode không xác thực, không bỏ qua lỗi tag, không in plaintext hay secret ra log.
6. **String và byte[] chứa plaintext vẫn tồn tại trong bộ nhớ.** Ví dụ đơn giản không xử lý xóa dữ liệu nhạy cảm/GC. Hệ thống thực tế cần giảm thời gian sống của plaintext và hạn chế heap dump, trace, log.
7. **AES-GCM không cung cấp chữ ký số.** Nếu bên nhận cần xác minh tác giả theo public key hoặc cần bằng chứng độc lập giữa các bên, có thể phải thêm chữ ký số hoặc một giao thức xác thực thích hợp.

## 7. AES-GCM và envelope encryption với KMS/HSM

Trong thiết kế **envelope encryption**, ứng dụng dùng khóa **DEK (Data Encryption Key)** để AES-GCM mã hóa dữ liệu. Một khóa khác, **KEK (Key Encryption Key)**, bảo vệ DEK bằng cơ chế **wrap/unwrap** thích hợp. KEK thường được giữ và sử dụng trong KMS/HSM.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS/HSM chứa KEK
    participant DB as Database/Object storage
    App->>KMS: GenerateDataKey(KEK ref, context)
    KMS-->>App: Plaintext DEK + wrapped DEK (nếu API hỗ trợ)
    App->>App: AES-GCM Encrypt(plaintext, DEK, nonce, AAD)
    App->>DB: ciphertext+tag, nonce, wrapped DEK, metadata
    Note over App: Giảm thời gian plaintext DEK tồn tại trong bộ nhớ
    App->>DB: Đọc bản ghi khi cần giải mã
    DB-->>App: ciphertext+tag, nonce, wrapped DEK, metadata
    App->>KMS: Decrypt/Unwrap(wrapped DEK, context)
    KMS-->>App: Plaintext DEK nếu được cấp quyền
    App->>App: AES-GCM Decrypt + Verify(AAD, tag)
~~~

Đây là luồng **minh họa cho API KMS cho phép trả plaintext DEK**, không phải mọi KMS/HSM đều hoạt động giống nhau. Trong một số mô hình, phép mã hóa/giải mã diễn ra ngay trong ranh giới tin cậy và ứng dụng chỉ nhận kết quả.

| Thành phần lưu cùng bản ghi | Vai trò | Có phải key material? |
|---|---|---|
| **ciphertext + tag** | Dữ liệu được mã hóa và tag xác thực | Không |
| **nonce** | Tham số của lần mã hóa GCM | Không |
| **wrapped DEK** | Bản DEK được bảo vệ bằng KEK | **Có, ở dạng đã mã hóa** |
| **keyId, keyVersion, algorithm, formatVersion** | Metadata xác định cách đọc/khôi phục | Không |
| **AAD context** | Ngữ cảnh cần tái tạo chính xác khi giải mã | Không; thường có thể đọc rõ |
| **KEK trong KMS/HSM** | Khóa bảo vệ DEK | **Có, bí mật** |

Ví dụ bản ghi minh họa, toàn bộ chuỗi Base64 là **placeholder, không phải khóa thật**:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyId": "kms/customer-data-kek",
  "keyVersion": "v3",
  "wrappedDek": "<BASE64_WRAPPED_DEK>",
  "nonce": "<BASE64_12_BYTE_NONCE>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_PLUS_16_BYTE_TAG>",
  "aadContext": {
    "tenantId": "tenant-42",
    "objectId": "customer-123"
  }
}
~~~

**wrappedDek không phải một chuỗi metadata vô hại.** Nó là key material được bảo vệ; nếu KEK bị lộ hoặc bị lạm dụng quyền unwrap, DEK và dữ liệu đi kèm có thể bị ảnh hưởng. **Base64 chỉ là biểu diễn**, không phải bảo vệ mật mã.

Nếu bản ghi chứa trường metadata như **keyId** và **objectId**, AAD nên ràng buộc các trường có ý nghĩa an ninh vào ciphertext và các giá trị ấy cần được đối chiếu với **ngữ cảnh đã xác thực**. Không lấy tenantId do request bất kỳ cung cấp rồi tự tin giải mã cho tenant đó. Nếu context của KMS cũng đóng vai trò AAD cho việc wrap DEK, phải khôi phục đúng context ấy khi unwrap; nó là lớp bảo vệ **khác** với AAD ở tầng AES-GCM của ứng dụng.

### 7.1. KMS/HSM giải quyết được điều gì?

- **Quản lý material:** tạo/nhập khóa, cấm hoặc giới hạn export, thực thi wrap/unwrap, gán ID/phiên bản.
- **Phân quyền:** cho phép thao tác theo service account, vai trò, tenant, mục đích, thời điểm và policy.
- **Vòng đời:** kích hoạt, xoay vòng, vô hiệu hóa, lên lịch hủy theo khả năng dịch vụ.
- **Kiểm toán:** ghi nhận việc sử dụng KEK, thay đổi policy, nhập/xuất và thao tác quản trị.

KMS/HSM **không tự bảo đảm** ứng dụng cấp nonce không trùng hoặc dựng AAD đúng cho AES-GCM bên ngoài. Ngược lại, một thuật toán AEAD triển khai đúng cũng không cứu được dữ liệu nếu API **Decrypt** bị cấp quyền quá rộng.

## 8. Vòng đời khóa AES-GCM: tạo, dùng, xoay, thu hồi và hủy

~~~mermaid
flowchart TD
    A["Tạo DEK ngẫu nhiên hoặc nhận từ KMS"] --> B["Đăng ký key ID, version, purpose, owner"]
    B --> C["Lưu an toàn / wrap DEK bằng KEK"]
    C --> D["Encrypt với nonce mới, AAD đúng, tag 128 bit"]
    D --> E["Giám sát số lần dùng khóa, audit và cảnh báo"]
    E --> F["Đến hạn rotation hoặc có sự cố"]
    F --> G["Tạo DEK mới cho dữ liệu mới"]
    G --> H["Giữ decrypt-only hoặc re-encrypt dữ liệu cũ"]
    H --> I["Vô hiệu hóa khi hết phụ thuộc"]
    I --> J["Hủy theo quy trình kiểm soát"]
~~~

| Sự kiện | Key material thay đổi? | Tác động đến AES-GCM |
|---|---|---|
| **Tạo DEK** | Có, sinh khóa bí mật mới | Đặt key ID/version, purpose, giới hạn sử dụng, nonce strategy |
| **Encrypt dữ liệu mới** | Thường không | Phải cấp nonce mới **không trùng với khóa đó**, xác định AAD và ghi tag |
| **Decrypt dữ liệu cũ** | Thường không | Cần đúng DEK, nonce, ciphertext, tag, AAD và quyền |
| **Rotate DEK** | **Có**, tạo DEK khác | Bản mã mới dùng DEK mới; dữ liệu cũ vẫn gắn với DEK cũ cho đến khi re-encrypt |
| **Rotate KEK** | **Có**, thay khóa bảo vệ DEK | Có thể **rewrap DEK** mà không thay DEK hoặc nonce/ciphertext dữ liệu |
| **Disable/revoke quyền dùng khóa** | Không nhất thiết | Chặn Encrypt/Decrypt theo policy; lưu ý tác động đến dữ liệu cũ |
| **Destroy key** | Có, mất khả năng dùng material | Mất DEK hoặc KEK cần thiết có thể khiến dữ liệu không giải mã được |

**Rewrap không sửa lỗi trùng nonce đã xảy ra.** Rewrap chỉ thay đổi lớp bảo vệ DEK; nếu cùng DEK đã được dùng với nonce trùng, rủi ro vẫn tồn tại. Khi phát hiện nonce reuse hay nghi DEK lộ, cần ngừng dùng DEK cho mã hóa mới, tạo DEK mới và đánh giá dữ liệu bị ảnh hưởng, gồm khả năng cần mã hóa lại từ plaintext tin cậy.

### 8.1. Rotation có hai tác vụ khác nhau

1. **Thay DEK:** tạo khóa mã hóa dữ liệu mới. Mỗi ciphertext phải lưu đủ tham chiếu để tìm lại **DEK đúng**. Có thể chỉ dùng DEK mới cho dữ liệu mới hoặc re-encrypt dữ liệu cũ tùy chính sách.
2. **Thay KEK:** đổi khóa bảo vệ DEK trong KMS/HSM. Thường thực hiện **unwrap rồi rewrap** an toàn hoặc API **ReEncrypt** do dịch vụ hỗ trợ. Khi đó AES-GCM ciphertext dữ liệu có thể giữ nguyên vì DEK không đổi.

Việc đổi một alias từ **v2** sang **v3** không đồng nghĩa tất cả bản mã cũ được tự động mã hóa lại. Hủy DEK cũ hoặc KEK cũ trước khi xác nhận khả năng khôi phục có thể gây mất dữ liệu.

### 8.2. Multi-instance và hệ thống phân tán

Đặc biệt thận trọng khi nhiều service instance cùng dùng một DEK:

- Nếu nonce là **counter**, phải cấp phát không gian counter không trùng, lưu giá trị sau failover và chống reset do snapshot/restore.
- Nếu nonce là **random**, phải bảo đảm CSPRNG đúng và **giới hạn tổng số lần mã hóa theo khóa** trên toàn hệ thống, không tính riêng từng máy.
- Khi job retry/backfill, phải xác định có **mã hóa lại** hay **phát lại đúng ciphertext đã lưu**; nếu mã hóa lại, vẫn cần nonce mới.
- Khi lưu dữ liệu, phải ghi **ciphertext, nonce, tag, key reference và định dạng** một cách nhất quán; cập nhật dở dang có thể làm dữ liệu không khôi phục được.
- Khi rotate, nên có khoảng chuyển tiếp hỗ trợ khóa cũ để decrypt, nhưng kiểm soát không dùng khóa cũ cho encrypt mới theo chính sách.

## 9. Những lỗi AES-GCM thường gặp và cách phòng tránh

| Lỗi | Rủi ro | Biện pháp |
|---|---|---|
| **Tái sử dụng key + nonce** | Lộ quan hệ plaintext, có thể phá vỡ xác thực | Cấp nonce duy nhất theo key; giới hạn invocation; rotate DEK |
| **Dùng AES-ECB hoặc CBC không xác thực để thay thế tạm thời** | Không có bảo đảm AEAD; có thể bị sửa bản mã hoặc phát sinh oracle tùy thiết kế | Dùng AES-GCM/AEAD được kiểm chứng; không tự tạo thuật toán kết hợp |
| **Bỏ qua lỗi tag** | Dữ liệu bị sửa vẫn đi vào nghiệp vụ | Chỉ sử dụng plaintext sau khi xác thực hoàn tất |
| **Không dùng AAD cho metadata nhạy về ngữ cảnh** | Bản mã có thể bị tráo giữa tenant/record nếu ứng dụng thiếu bảo vệ khác | Xác thực metadata cần ràng buộc; kiểm tra quyền độc lập |
| **Dùng AAD làm nơi chứa bí mật** | Lộ thông tin vì AAD không được mã hóa | Đưa secret vào plaintext cần mã hóa |
| **Truncate tag tùy ý** | Giảm khả năng chống giả mạo | Mặc định tag 128 bit và tuân thủ giới hạn chuẩn nếu cần giá trị khác |
| **Lưu AES key trong Git, log, config không bảo vệ** | Mất bảo mật toàn bộ bản mã dùng khóa đó | Cấp key qua KMS/HSM, tránh plaintext export, secret scanning |
| **Không lưu key ID/version hoặc nonce** | Không tìm được khóa/không đủ dữ liệu giải mã | Version hóa định dạng và lưu đủ tham chiếu |
| **Cho mọi service account quyền unwrap DEK** | Một service bị chiếm có thể giải mã dữ liệu vượt phạm vi | Least privilege, tách tenant/purpose, audit và cảnh báo |
| **Hủy KEK/DEK quá sớm** | Mất khả năng giải mã dữ liệu tồn lưu | Rewrap/re-encrypt, backup và thử restore trước khi hủy |
| **Phát lại ciphertext hợp lệ** | AEAD vẫn giải mã thành công nhưng nghiệp vụ thực hiện lại giao dịch cũ | Dùng message ID, monotonic sequence, thời hạn, trạng thái xử lý |
| **Nhầm tag với chữ ký số** | Giả định sai rằng bên thứ ba có thể chứng minh người gửi | Nếu cần xác thực bất đối xứng, thiết kế chữ ký số và phân phối public key tin cậy |

AES-GCM-SIV là một **chế độ AEAD khác** có các đặc tính giảm thiểu hậu quả của việc lỡ tái sử dụng nonce trong phạm vi thiết kế của nó. Không được coi nó là cách tùy ý đổi tên **AES/GCM/NoPadding** hoặc lý do để bỏ quản lý nonce; cần giao thức, thư viện và định dạng dữ liệu hỗ trợ phù hợp.

## 10. Tình huống kiến trúc: bảo vệ hồ sơ khách hàng

Một hệ thống Java lưu hồ sơ khách hàng trên database, triển khai nhiều instance và dùng KMS để quản lý KEK. Thiết kế:

1. **Tạo khóa:** khi cần mã hóa một hồ sơ, dịch vụ nhận DEK theo quy trình đã được cấp quyền (ví dụ API **GenerateDataKey** trả DEK bản rõ tạm thời và wrapped DEK). KEK được bảo vệ trong KMS.
2. **Định danh:** hồ sơ gắn với **key reference**, **formatVersion**, **tenantId**, **recordId** và các thuộc tính nghiệp vụ cần ràng buộc. Thiết kế lưu wrapped DEK riêng từng bản ghi hoặc theo lô tùy mô hình.
3. **Mã hóa:** ứng dụng cấp nonce 96 bit phù hợp, tạo AAD có cấu trúc từ tenantId, recordId, key reference và formatVersion; thực hiện **AES-256-GCM**.
4. **Lưu trữ:** ghi nguyên vẹn **nonce + ciphertextWithTag + wrapped DEK + key metadata**; không ghi plaintext DEK hoặc dữ liệu gốc vào log.
5. **Giải mã:** lấy tenant từ danh tính đã xác thực, kiểm tra quyền đọc record, gọi KMS unwrap theo policy, tái tạo AAD từ nguồn tin cậy rồi xác minh tag trước khi sử dụng plaintext.
6. **Kiểm toán:** ghi người gọi, operation, key reference, kết quả, timestamp và correlation ID. Không log DEK, dữ liệu khách hàng hoặc secret-bearing context.
7. **Xoay vòng:** thay KEK bằng rewrap nếu cần; thay DEK khi đến hạn hoặc có sự cố, có kế hoạch chuyển đổi dữ liệu cũ. Bảo đảm dữ liệu backup vẫn có cách giải mã hoặc được chuyển đổi trước khi hủy khóa.

**Một thiết kế khác:** sinh một DEK cho một nhóm bản ghi thay vì mỗi record giúp giảm số lời gọi KMS, nhưng làm tăng phạm vi dữ liệu bị ảnh hưởng nếu DEK lộ và **tổng số lần mã hóa dùng cùng DEK**. Khi chọn phạm vi DEK, cần cân bằng hiệu năng, số lượng thao tác, quản trị nonce, quyền truy cập và mức độ nhạy cảm của dữ liệu.

## 11. Checklist thiết kế AES-GCM an toàn

1. **Chọn AEAD đúng:** dùng thư viện chuẩn, thuật toán AES-GCM được hỗ trợ, key size phù hợp và tag 128 bit.
2. **Sinh/giữ khóa:** DEK được tạo bằng CSPRNG/KMS, không xuất/lưu raw key ngoài phạm vi cần thiết.
3. **Chiến lược nonce:** bảo đảm duy nhất theo mỗi DEK, kể cả multi-instance, retry, restore và rotation; theo dõi giới hạn số lần dùng key.
4. **AAD:** xác định trường nào phải xác thực, encoding chuẩn hóa và format version; không đưa secret vào AAD.
5. **Ràng buộc tenant:** xác thực danh tính và kiểm tra quyền trước khi resolve key/unwrap; đối chiếu AAD với tenant/record thực tế.
6. **Bản ghi:** lưu đủ nonce, ciphertext, tag, wrapped DEK nếu có, key ID/version và định dạng.
7. **Xử lý lỗi:** thất bại tag nghĩa là phải từ chối; không trả plaintext chưa xác thực hoặc tự chuyển sang chế độ không xác thực.
8. **Vòng đời:** phân biệt DEK rotation với KEK rewrap, chuẩn bị đường giải mã dữ liệu cũ và thời điểm hủy.
9. **KMS/HSM:** giới hạn Encrypt/Decrypt/GenerateDataKey/Unwrap theo workload và purpose; audit thao tác quan trọng.
10. **Kiểm thử an ninh:** kiểm tra sửa ciphertext, tag, nonce, tenant và key version đều bị phát hiện hoặc chặn phù hợp; kiểm tra không tái sử dụng nonce khi concurrency/retry.

### Câu hỏi tự kiểm tra

**Câu 1.** AES-256-GCM dùng khóa 256 bit. Có phải kích thước khối AES là 256 bit?

**Trả lời:** **Không.** Kích thước khối AES luôn 128 bit; con số 256 chỉ độ dài khóa.

**Câu 2.** Nonce 96 bit có cần được giữ kín như DEK không?

**Trả lời:** **Không.** Nonce có thể được lưu cùng ciphertext nhưng **phải không trùng với cùng DEK**.

**Câu 3.** Nếu người dùng thay **tenantId** trong request, ứng dụng chỉ cần dùng tenantId đó làm AAD rồi giải mã?

**Trả lời:** **Không.** Tenant phải được xác thực từ danh tính và quyền truy cập; AAD chỉ ràng buộc mật mã dữ liệu với ngữ cảnh đã được kiểm tra.

**Câu 4.** Sau khi rewrap DEK từ KEK-v1 sang KEK-v2, bản mã AES-GCM có tự dùng DEK mới không?

**Trả lời:** **Không.** Rewrap thay khóa **bảo vệ DEK**; DEK và bản mã dữ liệu vẫn giữ nguyên nếu không có re-encrypt.

**Câu 5.** Một ciphertext hợp lệ bị gửi lại lần thứ hai cùng nonce, tag và AAD. GCM có tự từ chối vì replay không?

**Trả lời:** **Không.** Nếu dữ liệu vẫn nguyên vẹn và khóa/đầu vào đúng, tag vẫn có thể hợp lệ. Chống replay là trách nhiệm của giao thức và logic nghiệp vụ, khác với yêu cầu nonce duy nhất khi **thực hiện các lần mã hóa**.

**Điểm cốt lõi:** AES-GCM bảo vệ **bí mật và tính xác thực mật mã của dữ liệu** khi khóa, nonce, AAD và tag được dùng đúng. Quản lý key material bằng DEK/KEK, KMS/HSM, IAM, audit và vòng đời rotation/recovery là phần không thể tách rời của một hệ thống AES-GCM an toàn.
