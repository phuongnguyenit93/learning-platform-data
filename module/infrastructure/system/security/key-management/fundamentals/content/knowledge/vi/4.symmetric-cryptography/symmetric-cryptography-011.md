# Associated data (AAD): xác thực metadata mà không cần mã hóa

## 1. Vì sao dữ liệu đã mã hóa vẫn cần associated data?

Giả sử một hệ thống nhiều khách hàng (multi-tenant) lưu hóa đơn đã mã hóa bằng **AES-256-GCM**. Mỗi bản ghi gồm nội dung mã hóa, nonce và mã xác thực (*authentication tag*). Ứng dụng còn giữ các cột không mã hóa như **tenant ID**, **invoice ID** và **schema version** để tìm kiếm, phân quyền và chọn cách giải mã.

Kẻ tấn công có quyền sửa dữ liệu trong kho lưu trữ có thể cố tình **chuyển bản mã của hóa đơn A sang vị trí hóa đơn B**, hoặc đổi tenant ID trong metadata. Nếu hệ thống chỉ kiểm tra nội dung bản mã mà không ràng buộc bản mã với ngữ cảnh nghiệp vụ được kỳ vọng, ứng dụng có thể xử lý nhầm một bản ghi hợp lệ dưới danh tính hoặc vị trí không hợp lệ.

**Associated data**, thường gọi là **Additional Authenticated Data (AAD)** trong nhiều API, cho phép thuật toán mã hóa có xác thực bảo vệ tính toàn vẹn của **metadata không cần mã hóa** cùng với nội dung mã hóa. AAD có thể chứa định danh tenant, ID tài liệu, phiên bản định dạng hoặc mục đích sử dụng khóa. Thuật toán sẽ kết hợp AAD vào phép tính authentication tag.

**Thông điệp chính:** AAD giúp phát hiện **bản mã bị tách khỏi ngữ cảnh đã được xác thực**. AAD **không bí mật**, không thay thế kiểm tra quyền truy cập, và không tự chống phát lại.

Sau bài này, người học có thể:

- Giải thích AAD là gì, khác thế nào với plaintext, ciphertext, nonce và authentication tag.
- Biết AAD tác động đến **AEAD** như AES-GCM, ChaCha20-Poly1305.
- Thiết kế AAD ràng buộc dữ liệu với tenant, tài nguyên, mục đích và định dạng mà không mắc lỗi chuẩn hóa byte.
- Sử dụng **AES/GCM/NoPadding** trong Java để cung cấp AAD ở cả bước mã hóa và giải mã.
- Phân tích giới hạn của AAD trước giả mạo ngữ cảnh, replay, lộ khóa và những sai sót IAM/KMS/HSM.
- Gắn AAD với chiến lược quản lý khóa, envelope encryption, rotation và kiểm toán.

## 2. Từ mã hóa đối xứng đến AEAD

### 2.1. Mã hóa và xác thực là hai tính chất khác nhau

**Confidentiality (tính bí mật)** giúp bên không có khóa khó đọc được plaintext. **Integrity/authenticity (tính toàn vẹn và xác thực mật mã)** giúp phát hiện thông điệp đã bị sửa và xác nhận nó được tạo bởi bên có quyền sử dụng khóa phù hợp.

Một thuật toán chỉ mã hóa mà không xác thực có thể không phát hiện được sự can thiệp vào bản mã hoặc metadata; tùy chế độ mã hóa, việc sửa bản mã có thể tạo ra thay đổi có kiểm soát ở bản rõ sau giải mã. **AEAD (Authenticated Encryption with Associated Data)** kết hợp mã hóa và kiểm tra toàn vẹn/xác thực trong cùng một cơ chế.

Biểu diễn khái niệm:

~~~text
Encrypt(key, nonce, plaintext, AAD) -> (ciphertext, tag)
Decrypt(key, nonce, ciphertext, tag, AAD)
     -> plaintext nếu xác thực thành công
     -> lỗi xác thực nếu dữ liệu không khớp
~~~

Các đầu vào và kết quả cần hiểu đúng:

| Thành phần | Vai trò | Có bắt buộc giữ bí mật? |
| --- | --- | --- |
| **Key** | Bí mật dùng cho phép mã hóa/xác thực | **Có** |
| **Plaintext** | Nội dung cần bảo vệ | Thường có |
| **Ciphertext** | Nội dung đã mã hóa | Không, nhưng vẫn cần kiểm soát truy cập và lưu trữ |
| **Nonce/IV** | Giá trị cho mỗi thao tác mã hóa theo quy tắc thuật toán | Thường **không**; phải tuân thủ yêu cầu duy nhất/không lặp |
| **AAD** | Byte ngữ cảnh cần xác thực nhưng không mã hóa | **Không**; nên tránh đưa thông tin nhạy cảm vào AAD |
| **Authentication tag** | Giá trị giúp kiểm tra ciphertext và AAD có tương ứng với key/nonce không | Không, nhưng phải bảo quản nguyên vẹn và xác thực |
| **Key ID/version** | Hỗ trợ chọn khóa đúng khi giải mã | Thường không, nhưng nên ràng buộc an toàn với bản ghi theo thiết kế |

Một ứng dụng có thể lưu **nonce, ciphertext, tag và AAD hoặc những trường dùng tạo lại AAD** cùng nhau. Việc AAD không được mã hóa không có nghĩa nó được bỏ qua khi giải mã.

### 2.2. AAD được xác thực ra sao?

Trong AES-GCM, authentication tag phụ thuộc vào khóa, nonce, ciphertext **và AAD**. Do đó:

- Nếu ciphertext bị thay đổi, xác thực thông thường thất bại.
- Nếu AAD bị thay đổi nhưng ciphertext và tag vẫn giữ nguyên, xác thực thất bại.
- Nếu dùng **sai key hoặc nonce**, xác thực thông thường cũng thất bại.
- Nếu tất cả thành phần đúng, kết quả xác thực hợp lệ **dưới khóa đang sử dụng**.

Tính bảo đảm này dựa trên việc dùng AEAD đúng chuẩn, **không tái sử dụng nonce với cùng khóa**, quản lý khóa an toàn và kiểm tra tag đúng. Không có nghĩa AAD đã được giữ bí mật, cũng không có nghĩa mọi đối tượng có quyền giải mã đều là người dùng hợp lệ.

~~~mermaid
flowchart TD
    K["Key trong KMS/HSM hoặc ứng dụng tin cậy"] --> E["AEAD Encrypt"]
    N["Nonce hợp lệ"] --> E
    P["Plaintext hóa đơn"] --> E
    A["AAD: tenant + invoice + version"] --> E
    E --> C["Ciphertext"]
    E --> T["Authentication tag"]
    C --> D["AEAD Decrypt"]
    T --> D
    K --> D
    N --> D
    A --> D
    D --> R{"Kiểm tra tag thành công?"}
    R -->|Có| O["Trả plaintext cho bên đã được phân quyền"]
    R -->|Không| X["Từ chối và ghi sự kiện phù hợp"]
~~~

Sơ đồ mô tả cùng một AAD đã được xây dựng từ **ngữ cảnh đáng tin cậy ở hai thời điểm**. Khi sử dụng giao diện AEAD của thư viện, không nhất thiết có bước tính tag riêng tại ứng dụng.

### 2.3. Điều AAD không làm được

- **Không mã hóa metadata.** Giá trị AAD có thể bị đọc được nếu lưu ngoài bản mã, kể cả khi được xác thực.
- **Không tự chứng minh danh tính người dùng.** Tag hợp lệ cho thấy dữ liệu khớp với khóa và tham số mật mã; quyền xem hóa đơn phải được kiểm tra riêng.
- **Không tự ngăn replay.** Một bộ hợp lệ gồm ciphertext + nonce + tag + AAD có thể được gửi/lưu lại nếu ứng dụng không có kiểm soát freshness, phiên bản, thứ tự hoặc trạng thái.
- **Không ngăn người đang có quyền mã hóa bằng khóa tạo bản mã/tag hợp lệ.** Một dịch vụ với quyền Encrypt quá rộng vẫn có thể tạo dữ liệu hợp lệ cho ngữ cảnh bị lạm dụng.
- **Không sửa được sai sót của thuật toán/nonce/key.** GCM bị dùng lại nonce dưới cùng key là lỗi nghiêm trọng, bất kể AAD có đầy đủ hay không.
- **Không tự ngăn di chuyển nguyên cả bản ghi** nếu nơi nhận vẫn chấp nhận cùng ngữ cảnh. Phải so sánh AAD với tài nguyên/tenant **được yêu cầu và đã phân quyền**, không chỉ tin metadata từ kho dữ liệu.

## 3. Chọn những gì đưa vào associated data

AAD phù hợp với các trường **không cần giữ bí mật nhưng phải có tính toàn vẹn và được ràng buộc vào bản mã**. Khi cần giữ bí mật một trường, nên đưa trường đó vào plaintext được mã hóa hoặc có chính sách bảo vệ riêng.

| Trường | Có thể đưa vào AAD? | Mục đích và lưu ý |
| --- | --- | --- |
| **Tenant ID** | Có, nếu không nhạy cảm theo chính sách | Ràng buộc bản mã với tenant; tenant xác thực phải đến từ server/identity |
| **Document/record ID** | Có | Chống tráo nội dung giữa hai tài nguyên khi bên giải mã kiểm tra ID kỳ vọng |
| **Loại dữ liệu / purpose** | Có | Tách hóa đơn khỏi dữ liệu xác thực, bản ghi thanh toán hoặc mục đích khác |
| **Phiên bản định dạng** | Có | Phát hiện sửa phiên bản hoặc sử dụng nhầm quy tắc phân tích dữ liệu |
| **Protocol/message type** | Có | Ràng buộc nội dung với đúng thông điệp/protocol đã định |
| **Key ID/version** | Có thể | Ràng buộc lựa chọn khóa hoặc version khi thiết kế cần; không thay thế kiểm soát key usage |
| **Timestamp, sequence number** | Có thể | Hỗ trợ cơ chế chống replay của giao thức; **chỉ xác thực timestamp** không tự ngăn replay |
| **Secret, access token, mật khẩu** | Thông thường **không** | AAD không mã hóa; có thể xuất hiện trong log/metadata |
| **Dữ liệu cá nhân nhạy cảm** | Tránh nếu không cần công khai | Phân loại dữ liệu; nếu cần bí mật, đưa vào phần được mã hóa |
| **Nonce** | Thường là đầu vào riêng của AEAD | Không cần mặc định lặp lại nonce trong AAD; vẫn phải quản lý nonce đúng quy tắc |

### Ví dụ A: chống tráo hóa đơn giữa các tenant

Khi mã hóa hóa đơn số 154 cho tenant A:

~~~text
plaintext  = nội dung hóa đơn 154
AAD        = Encode("billing/v1", tenant="A", document="154")
key        = khóa AES-GCM đã được cấp quyền
nonce      = nonce duy nhất dưới key
(ciphertext, tag) = AEAD.Encrypt(key, nonce, plaintext, AAD)
~~~

Khi tenant B yêu cầu đọc hóa đơn có cùng document ID, server xây AAD từ **tenant B đã xác thực** và tài nguyên đang được yêu cầu:

~~~text
AAD kỳ vọng = Encode("billing/v1", tenant="B", document="154")
~~~

Nếu server lấy bộ ciphertext/tag của tenant A và thử giải mã với AAD của B dưới **cùng khóa**, phép xác thực sẽ thất bại (trong điều kiện AEAD được dùng đúng). Nếu mỗi tenant sử dụng khóa khác nhau, kiểm tra cũng sẽ thất bại khi dùng khóa sai; việc tách khóa và AAD có thể bổ trợ cho nhau.

**Điểm dễ mắc lỗi:** nếu server đọc tenant ID **chỉ từ record trong database có thể bị sửa** rồi dùng chính nó làm AAD, kẻ tấn công có thể di chuyển **nguyên cả record hợp lệ** sang vị trí khác. Do đó, AAD phải được đối chiếu với **ngữ cảnh bên ngoài bản ghi** mà server đã xác thực và phân quyền.

### Ví dụ B: bảo vệ định dạng, không thay thế kiểm tra nghiệp vụ

Một bản mã dùng AAD chứa phiên bản định dạng **v2**. Nếu metadata bị sửa thành **v1** mà ciphertext và tag không đổi, giải mã sẽ thất bại khi cả hai phiên bản được mã hóa AAD đúng quy tắc. Nhưng nếu kẻ có quyền Encrypt tạo hẳn một bản ghi v1 mới với tag hợp lệ, AAD không tự xác định v1 có còn được phép sử dụng không. Ứng dụng cần **chính sách cho phép version/algorithm** riêng.

### Ví dụ C: thông điệp mạng

Trong một giao thức thông điệp tự thiết kế, header gồm message type, protocol version và sequence number có thể được dùng làm AAD; payload được mã hóa. Đó mới là phần **ràng buộc mật mã**. Việc quyết định sequence number nào hợp lệ, cửa sổ chấp nhận replay rộng bao nhiêu và thông điệp nào được phép xử lý vẫn do giao thức đảm nhận.

**TLS 1.3** sử dụng AEAD theo quy tắc ghi bản tin và các giá trị AAD quy định bởi giao thức. Khi dùng TLS trong Java, hãy sử dụng thư viện TLS chuẩn, **không tự chắp ghép AES-GCM, AAD và xử lý handshake** để xây TLS riêng.

## 4. AAD là byte: chuẩn hóa dữ liệu để không bị lỗi

Một lỗi triển khai phổ biến là hai phía nhận **cùng ý nghĩa nghiệp vụ** nhưng tạo ra **hai chuỗi byte AAD khác nhau**. Với AEAD, chỉ khác một byte cũng khiến authentication tag không khớp.

Ví dụ về cách nối chuỗi dễ nhập nhằng:

~~~text
tenant = "ab" , document = "c"   --> concat = "abc"
tenant = "a"  , document = "bc"  --> concat = "abc"
~~~

Nếu lập trình viên dùng nối chuỗi không có dấu phân cách hoặc cấu trúc, hai ngữ cảnh có thể thành **cùng byte AAD**, phá mục đích ràng buộc tenant/document.

### 4.1. Quy tắc mã hóa AAD nên có

1. **Danh sách trường và thứ tự cố định:** ví dụ namespace, version, purpose, tenant, document; không phụ thuộc thứ tự duyệt của map.
2. **Kiểu dữ liệu rõ ràng:** số nguyên, chuỗi UTF-8 và byte array có quy tắc mã hóa xác định; nếu cần Unicode normalization thì phải chỉ định và áp dụng nhất quán.
3. **Chống nhập nhằng:** mã hóa từng trường dạng **length-prefix**, TLV, hoặc chuẩn canonical được quy định rõ.
4. **Phiên bản hóa định dạng:** thêm trường mới phải có chiến lược tương thích dữ liệu cũ; đừng thay AAD v1 âm thầm.
5. **Nguồn dữ liệu tin cậy:** tenant và document ID dùng xác thực phải khớp ngữ cảnh nghiệp vụ; không tin header client hay cột database khi chưa kiểm tra.
6. **Lưu đủ metadata:** bên giải mã phải biết chọn key/nonce/version và tái tạo AAD đã dùng ban đầu. Bỏ một trường sẽ gây lỗi giải mã.
7. **Ràng buộc và kiểm tra quyền:** dù AAD đúng, ứng dụng vẫn cần quyền đọc/ghi đối với tài nguyên thực tế.

Ví dụ một định dạng không nhập nhằng:

~~~text
AAD bytes =
  Length("invoice-service") || UTF8("invoice-service") ||
  Int32(1)                                    // AAD format version
  Length("invoice-content") || UTF8("invoice-content") ||
  Length(trustedTenantId) || UTF8(trustedTenantId) ||
  Length(documentId) || UTF8(documentId)
~~~

Ở đây **Length** chỉ số byte theo quy tắc mã hóa đã thống nhất; **Int32** dùng cùng byte order ở mọi bên. Không dùng số ký tự Unicode làm độ dài nếu thực tế ghi byte UTF-8. Nếu nghiệp vụ cần định danh ổn định, nên thống nhất chuẩn biểu diễn ID ngay từ lúc tạo đối tượng.

### 4.2. Có thể dùng JSON làm AAD không?

Có thể, **nếu byte JSON được tạo lại một cách xác định** theo quy tắc chung. Hai chuỗi JSON sau có thể tương đương về mặt dữ liệu nhưng khác byte:

~~~json
{"tenant":"A","document":"154"}
~~~

~~~json
{ "document": "154", "tenant": "A" }
~~~

Khác thứ tự trường, khoảng trắng, cách escape hoặc cách biểu diễn số/Unicode đều có thể làm tag khác. Vì thế hoặc lưu chính xác byte AAD đã dùng, hoặc dùng **canonical JSON** theo chuẩn được thống nhất, hoặc chọn định dạng nhị phân xác định. **Không tự giả định JSON serialization mặc định của hai thư viện sẽ cho cùng byte.**

Nếu lưu AAD chính xác bên cạnh bản mã, hãy nhớ **nội dung AAD có thể bị đọc được**. Hơn nữa, trong bài toán chống tráo bản ghi, cần so sánh AAD đã lưu với **tenant/record kỳ vọng đã xác thực**, nếu không vẫn có thể chuyển cả AAD và bản mã nguyên vẹn.

## 5. Triển khai Java 17+: AES-GCM với AAD

Ví dụ sau sử dụng **Java Cryptography Architecture (JCA)** để minh họa vòng đời mã hóa/giải mã có AAD. Chương trình tạo khóa AES-256 để chạy demo; ứng dụng production nên nhận **DEK được bảo vệ và cấp phát an toàn**, thường thông qua KMS/envelope encryption.

Mã **đầy đủ có thể biên dịch** trong Java 17+, không cần thư viện bên ngoài. Các giá trị tenant/document là giả định **đã được xác thực ở tầng ứng dụng**.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

import javax.crypto.spec.GCMParameterSpec;

public final class AssociatedDataDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;       // 96-bit nonce
    private static final int TAG_BITS = 128;
    private static final int AAD_VERSION = 1;

    public record EncryptedRecord(
        byte[] nonce, byte[] ciphertextAndTag, int aadVersion) {}

    public static EncryptedRecord encrypt(
            SecretKey dataKey,
            byte[] plaintext,
            String trustedTenantId,
            String documentId) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);  // Demo: phải không trùng cho cùng key.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            dataKey,
            new GCMParameterSpec(TAG_BITS, nonce)
        );

        // Phải cấp AAD trước khi xử lý plaintext/ciphertext.
        cipher.updateAAD(aad(trustedTenantId, documentId, AAD_VERSION));

        // Trong JCA, doFinal trả ciphertext || tag.
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new EncryptedRecord(nonce, ciphertextAndTag, AAD_VERSION);
    }

    public static byte[] decrypt(
            SecretKey dataKey,
            EncryptedRecord stored,
            String authorizedTenantId,
            String authorizedDocumentId) throws Exception {

        if (stored.aadVersion() != AAD_VERSION) {
            throw new IllegalArgumentException("Unsupported AAD version");
        }
        if (stored.nonce().length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid nonce length");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            dataKey,
            new GCMParameterSpec(TAG_BITS, stored.nonce())
        );

        // Lấy tenant/document từ request đã được xác thực và phân quyền.
        // Không sử dụng metadata có thể bị giả mạo để tự cấp quyền.
        cipher.updateAAD(
            aad(authorizedTenantId, authorizedDocumentId, stored.aadVersion())
        );

        // Tag sai sẽ phát sinh AEADBadTagException (hoặc lỗi xác thực
        // tương đương ở provider). Chỉ dùng plaintext sau doFinal.
        return cipher.doFinal(stored.ciphertextAndTag());
    }

    private static byte[] aad(
            String tenantId, String documentId, int version) {

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            putString(out, "billing-service");
            out.writeInt(version);
            putString(out, "invoice-content");
            putString(out, tenantId);
            putString(out, documentId);
        } catch (IOException e) {
            throw new IllegalStateException("Unable to encode AAD", e);
        }
        return bytes.toByteArray();
    }

    private static void putString(DataOutputStream out, String value)
            throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length); // Độ dài byte, big-endian.
        out.write(encoded);
    }

    public static void main(String[] args) throws Exception {
        // Chỉ dùng để demo. Production cần quản lý khóa qua KMS/HSM.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dataKey = generator.generateKey();

        byte[] invoice = "amount=250;currency=VND".getBytes(
            StandardCharsets.UTF_8);

        EncryptedRecord stored = encrypt(
            dataKey, invoice, "tenant-A", "invoice-154");

        byte[] restored = decrypt(
            dataKey, stored, "tenant-A", "invoice-154");
        System.out.println(
            "Correct context: " + Arrays.equals(invoice, restored));

        try {
            decrypt(dataKey, stored, "tenant-B", "invoice-154");
            throw new AssertionError("Expected authentication failure");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong tenant: authentication rejected");
        }

        try {
            decrypt(dataKey, stored, "tenant-A", "invoice-999");
            throw new AssertionError("Expected authentication failure");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong document: authentication rejected");
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Correct context: true
Wrong tenant: authentication rejected
Wrong document: authentication rejected
~~~

### 5.1. Giải thích chi tiết

- **AES/GCM/NoPadding** là chế độ AEAD: ciphertext và authentication tag đều được tính từ ngữ cảnh phù hợp. Không cần thêm một HMAC tự phát minh lên bản mã.
- **Nonce 12 byte (96 bit)** là độ dài được khuyến nghị phổ biến cho AES-GCM; ở đây lấy ngẫu nhiên bằng SecureRandom. Ngẫu nhiên **không bảo đảm tuyệt đối không trùng**: hệ thống lưu lượng cao, dùng lâu dài hoặc cần bảo đảm chặt nên có chiến lược nonce duy nhất theo từng khóa và giới hạn số lần mã hóa theo mô hình của nó.
- **Tag 128 bit** được cấu hình bằng GCMParameterSpec; Java trả kết quả doFinal khi mã hóa thường là **ciphertext nối tag**. Nếu thiết kế lưu tag riêng, phải tách theo quy ước nhất quán.
- **updateAAD** phải được gọi **sau init, trước khi xử lý dữ liệu** trong luồng JCA này. Bên giải mã cung cấp lại **cùng byte AAD**.
- **Length-prefix** và thứ tự cố định loại bỏ nhập nhằng giữa tenant/document, đồng thời ràng buộc purpose và version.
- **authorizedTenantId** phải đến từ danh tính đã xác thực. **authorizedDocumentId** phải được kiểm tra quyền đọc ở tầng nghiệp vụ **trước** khi cho phép giải mã.
- **AEADBadTagException** thể hiện không thể xác thực dữ liệu theo khóa/nonce/AAD đã cung cấp. Tầng API nên trả lỗi tổng quát, tránh tiết lộ dữ liệu nhạy cảm hoặc dấu hiệu nội bộ của hệ thống.

Ví dụ chỉ kiểm tra việc AAD thay đổi khiến giải mã thất bại. Nó **không** tự triển khai IAM, kiểm soát chủ sở hữu hóa đơn, lưu trữ an toàn, lựa chọn key version, chống replay hay bảo vệ khóa production. Không phải mọi provider đều có hành vi lỗi hoàn toàn giống nhau; ứng dụng cần xử lý lỗi xác thực một cách an toàn.

### 5.2. Không đưa plaintext ra ngoài trước khi xác thực tag

Trong những API giải mã hỗ trợ **streaming**, một số cơ chế có thể trả về byte chưa được xác thực trước khi toàn bộ tag được kiểm tra. Ứng dụng không được hiển thị, lưu vĩnh viễn hoặc thực hiện giao dịch theo dữ liệu đó trước khi phép xác thực hoàn tất. Trong ví dụ Java, dữ liệu chỉ được sử dụng sau khi **doFinal** thành công.

Nếu giải mã thất bại, không “cố mở” bằng cách tắt xác thực tag hoặc thử lại với AAD rỗng. Việc chấp nhận AAD rỗng như phương án dự phòng có thể phá cơ chế ràng buộc tenant/record mà hệ thống kỳ vọng.

## 6. AAD và quản lý khóa: DEK, KEK, KMS/HSM

Mục đích của AAD là **ràng buộc ngữ cảnh với một phép AEAD cụ thể**. Trong **envelope encryption**, thường có hai tầng thao tác khác nhau:

1. **DEK (Data Encryption Key):** dùng AES-GCM mã hóa hóa đơn. AAD của tầng dữ liệu có thể là tenant, invoice ID, schema version và purpose.
2. **KEK (Key Encryption Key):** giữ trong KMS/HSM để **bọc DEK**. Nếu API KMS hỗ trợ một **encryption context** hoặc cơ chế AAD, nó có thể được dùng để ràng buộc wrapped DEK với tenant/purpose ở tầng bọc khóa.

Hai tầng phải được xử lý **độc lập**. Không thể giả định encryption context của KMS **tự trở thành AAD của AES-GCM** do ứng dụng thực hiện hoặc ngược lại.

~~~mermaid
sequenceDiagram
    participant A as InvoiceService
    participant K as KMS/HSM
    participant D as Database
    Note over A,K: Mã hóa dữ liệu
    A->>K: GenerateDataKey với KEK và context KMS
    K-->>A: DEK dạng rõ tạm thời + wrappedDEK
    A->>A: AES-GCM(plaintext, DEK, nonce, AAD dữ liệu)
    A->>D: Lưu nonce, ciphertext, tag, wrappedDEK, metadata
    Note over A,K: Đọc dữ liệu
    A->>A: Xác thực tenant, tài nguyên và quyền đọc
    A->>D: Đọc bản ghi đã mã hóa
    D-->>A: nonce, ciphertext, tag, wrappedDEK, metadata
    A->>K: Unwrap/Decrypt với context KMS tương ứng
    K-->>A: DEK nếu được cấp quyền
    A->>A: AES-GCM Decrypt với AAD dữ liệu đúng ngữ cảnh
    A->>A: Chỉ chấp nhận plaintext khi tag hợp lệ
~~~

### 6.1. Tầng dữ liệu: AAD AES-GCM

Giả sử dữ liệu lưu dạng:

~~~json
{
  "tenantId": "tenant-A",
  "documentId": "invoice-154",
  "formatVersion": 1,
  "kekId": "kms-billing-prod",
  "kekVersion": "v3",
  "wrappedDek": "<base64 wrapped data key>",
  "nonce": "<base64 nonce>",
  "ciphertextAndTag": "<base64 ciphertext with GCM tag>"
}
~~~

Đây là minh họa cấu trúc, **không phải bản mã thật**. Ứng dụng có thể tái tạo AAD từ namespace, purpose, format version, **tenant/document đã phân quyền**. Nếu cần ràng buộc cả key ID/version, phải định nghĩa rõ byte encoding và cách giải mã cũ sau rotation.

**Không giữ DEK dạng rõ** trong record này. **Nonce, wrapped DEK và metadata** không nhất thiết bí mật, nhưng wrapped DEK cần cơ chế wrapping phù hợp và metadata phải được xác thực/đối chiếu đúng chỗ.

### 6.2. Tầng KMS: encryption context không phải lúc nào cũng giống AAD

Một số API của KMS hỗ trợ **encryption context** là tập cặp khóa/giá trị dùng khi tạo encrypted data key và cần đúng khi giải bọc. Tính năng, cách mã hóa, chính sách IAM có thể ràng buộc theo context, giới hạn dữ liệu và hành vi khi dùng sai context **phụ thuộc nhà cung cấp và loại khóa**.

Ví dụ context khái niệm:

~~~json
{
  "service": "billing",
  "tenant": "tenant-A",
  "purpose": "invoice-data-key"
}
~~~

Không đưa **password, access token, thông tin cá nhân nhạy cảm hoặc dữ liệu bí mật** vào encryption context; một số hệ thống có thể ghi context vào audit log. Không tin giá trị tenant do người dùng tự khai: phải ràng buộc với **identity đã xác thực và chính sách nghiệp vụ**.

**KMS/HSM không thay thế AAD và IAM của ứng dụng.** Nếu tài khoản ứng dụng có quyền Unwrap quá rộng, kẻ chiếm danh tính đó vẫn có thể lấy DEK. Nếu người dùng có quyền xem sai tài nguyên, tag hợp lệ không thể sửa lỗi phân quyền.

### 6.3. Rotation khóa và AAD version

Khi đổi KEK hoặc DEK, bản mã cũ có thể vẫn phụ thuộc vào phiên bản khóa và byte AAD cũ. Phân biệt các thao tác:

| Thao tác | Tác động tới dữ liệu và AAD |
| --- | --- |
| **Rotate KEK** | Có thể chuyển wrapped DEK mới sang KEK mới; ciphertext/AAD dữ liệu cũ không tự đổi |
| **Rewrap DEK** | Thay lớp bọc của cùng DEK; không cần mã hóa lại dữ liệu hay đổi AAD của lớp dữ liệu |
| **Thay DEK và re-encrypt** | Tạo ciphertext, nonce, tag mới; cung cấp AAD theo định dạng đang áp dụng |
| **Đổi AAD format/version** | Phải giữ quy tắc giải mã AAD cũ hoặc giải mã và mã hóa lại dữ liệu theo định dạng mới |
| **Thu hồi/xóa khóa cũ** | Có thể làm mất khả năng giải mã những bản mã và backup chưa được chuyển đổi |

Nếu KEK hoặc DEK **đã bị lộ**, chỉ thêm AAD hay thay format version **không bảo vệ lại bản mã cũ**. Phải điều tra phạm vi, khóa nào đã lộ và có cần thay DEK, re-encrypt dữ liệu hoặc vô hiệu hóa quyền KMS.

## 7. Threat model: AAD chống được gì, không chống được gì?

| Tình huống | AAD/AEAD có thể giúp gì? | Kiểm soát cần bổ sung |
| --- | --- | --- |
| Kẻ tấn công sửa 1 byte trong metadata đã ràng buộc | Khi bên giải mã dùng AAD kỳ vọng, tag không khớp | Nguồn dữ liệu AAD đáng tin, xử lý lỗi xác thực |
| Kẻ tấn công sửa ciphertext/tag | Xác thực thất bại theo bảo đảm của AEAD | Chặn dữ liệu chưa xác thực, giám sát và khôi phục bản sao đúng |
| Đổi ciphertext giữa hai invoice nhưng giữ ID kỳ vọng của invoice đích | Nếu invoice ID ở AAD và được xây từ yêu cầu hợp lệ, kiểm tra thất bại | Kiểm tra quyền đối với invoice ID |
| Chuyển cả ciphertext + AAD + tag + nonce sang cùng ngữ cảnh khác vẫn được chấp nhận | AAD không tự phát hiện nếu ngữ cảnh kỳ vọng không thay đổi | Ràng buộc ID/owner bên ngoài bản ghi và kiểm tra quyền |
| Phát lại nguyên thông điệp hợp lệ | Tag vẫn hợp lệ; AAD không tự chống replay | Sequence/nonce cấp giao thức, timestamp có kiểm tra, ID idempotency hoặc state |
| Lộ DEK | Kẻ có DEK có thể tạo bản mã/tag hợp lệ cho AAD tùy ý | Rotation, re-encrypt dữ liệu ảnh hưởng, quản lý khóa và điều tra |
| Workload có quyền Encrypt/Decrypt quá rộng | Tag hợp lệ dù hành vi bị lạm dụng | IAM, kiểm tra nghiệp vụ, quota, cảnh báo bất thường |
| Dùng lại nonce với cùng key AES-GCM | AAD không khắc phục được lỗi mật mã nghiêm trọng | Chiến lược nonce duy nhất, giới hạn sử dụng và rotation |
| AAD chứa thông tin nhạy cảm | Nội dung AAD vẫn có thể bị đọc | Phân loại thông tin, mã hóa phần cần bí mật, bảo vệ log |
| Server thay đổi thứ tự/encoding của trường AAD | Byte AAD khác khiến dữ liệu hợp lệ không mở được | Canonical encoding, versioning và kiểm tra tương thích |

### 7.1. Replay không giống sửa đổi thông điệp

Giả sử một giao dịch thanh toán hợp lệ có timestamp trong AAD. Kẻ tấn công phát lại **cùng bộ ciphertext + nonce + tag + timestamp**. Phép xác thực AEAD vẫn có thể thành công vì toàn bộ dữ liệu giống hệt lúc tạo. Chỉ khi ứng dụng **kiểm tra timestamp còn trong cửa sổ hợp lệ**, lưu transaction ID đã xử lý, hoặc theo dõi sequence number thì mới có thể từ chối yêu cầu phát lại theo quy tắc nghiệp vụ.

Việc dùng timestamp trong AAD bảo đảm timestamp không bị sửa một cách âm thầm, nhưng **không làm timestamp tự động trở thành bằng chứng mới**.

### 7.2. AAD và xác thực danh tính

Nếu một ứng dụng nhận yêu cầu:

~~~text
GET /tenants/B/invoices/154
~~~

và tài khoản đăng nhập thuộc tenant A, trước hết phải **từ chối ở tầng phân quyền**. Không nên gọi KMS/AEAD chỉ để xem có giải mã được hay không. Việc giải mã thành công hay thất bại là kiểm tra tính toàn vẹn dữ liệu, **không phải hệ thống cấp quyền xem hóa đơn**.

Nếu có quyền giải mã đối với tenant B, ứng dụng phải tạo AAD từ **tenant B và invoice 154 đã được xác nhận hợp lệ**. Việc đưa ID do request cung cấp thẳng vào AAD khi chưa phân quyền có thể dẫn tới hành vi giải mã trái phép hoặc khiến audit log sai.

## 8. Xử lý lỗi, quan sát và kiểm toán

Các sự cố liên quan AAD thường có hai nhóm: **dữ liệu bị can thiệp** và **triển khai không nhất quán**. Cả hai đều gây lỗi xác thực AEAD. Không nên luôn kết luận có tấn công chỉ vì một authentication tag sai; cần điều tra ngữ cảnh.

Những tín hiệu đáng theo dõi:

- Tỷ lệ **authentication failures** tăng sau một lần triển khai, đổi format hoặc thay thư viện serialization.
- Nhiều truy vấn từ một workload cố giải dữ liệu thuộc tenant khác hoặc dùng ID không hợp lệ.
- Số lần giải bọc DEK tại KMS tăng bất thường, đặc biệt cùng dữ liệu và các context khác nhau.
- Thay đổi bất thường của key policy, role được cấp quyền, lịch rotation hay key version.
- Xuất hiện dữ liệu dùng AAD version cũ ngoài thời hạn chuyển đổi được cho phép.

Nhật ký có thể ghi: **request ID, key ID/version, loại lỗi, schema/AAD version, resource ID không nhạy cảm hoặc đã được xử lý phù hợp, principal/workload, thời gian**. **Không ghi plaintext, DEK rõ, KEK, access token, dữ liệu cá nhân nhạy cảm hoặc chính byte AAD nếu chúng chứa thông tin mật**. Bảo vệ nhật ký khỏi đọc/sửa/xóa trái phép và xác định thời hạn lưu giữ.

Với API bên ngoài, nên trả lỗi tổng quát như **không thể xác minh bản ghi** hoặc **không thể xử lý yêu cầu**, tùy trường hợp và chính sách. Tránh để thông báo lỗi tiết lộ dữ liệu thuộc tenant khác, nội dung bản rõ hoặc cấu trúc khóa.

Nếu phát hiện lỗi do rollout thay đổi AAD serialization, cần xem xét **phiên bản định dạng, lựa chọn khóa, nonce, tag và byte AAD thực tế** tại môi trường thử nghiệm có dữ liệu mẫu không nhạy cảm. Đừng tạo một đường giải mã dự phòng bỏ AAD hoặc bỏ kiểm tra tag để “cứu” dữ liệu.

## 9. Quy trình triển khai AAD cho dữ liệu tồn tại lâu dài

Đối với hệ thống Java dùng KMS/HSM và envelope encryption, quy trình thực tế có thể tổ chức theo các bước sau.

1. **Xác định ranh giới tin cậy:** dịch vụ nào tạo hóa đơn, ai có quyền đọc, tenant/document ID nào được lấy từ identity hoặc từ kho định danh đã kiểm tra.
2. **Chọn các trường AAD:** namespace, purpose, version, tenant, document. Chỉ chọn trường cần tính toàn vẹn; tránh trường thay đổi liên tục hoặc thông tin bí mật.
3. **Định nghĩa byte encoding:** length-prefix hoặc canonical format, thứ tự và kiểu trường, charset, quy tắc Unicode, phân biệt giá trị rỗng/không có.
4. **Chọn AEAD đúng chuẩn:** ví dụ AES-256-GCM với tag 128 bit; tạo DEK ngẫu nhiên, quản lý nonce duy nhất theo DEK.
5. **Bảo vệ DEK:** wrapped DEK dưới KEK được quản lý bởi KMS/HSM, IAM với quyền tối thiểu và kiểm toán các thao tác nhạy cảm.
6. **Lưu metadata giải mã:** nonce, ciphertext/tag, wrapped DEK, key ID/version, AAD format version và giá trị cần thiết để tái tạo ngữ cảnh tin cậy.
7. **Kiểm tra ở tầng nghiệp vụ:** xác thực principal/tenant, kiểm tra quyền đọc tài nguyên trước khi dùng KMS và giải mã.
8. **Giải mã và xác thực:** cung cấp lại đúng byte AAD, dùng kết quả chỉ khi kiểm tra tag thành công; xử lý lỗi nhất quán.
9. **Thiết kế rotation/migration:** kiểm thử giải mã dữ liệu cũ, dữ liệu đã migrate và backup trước khi hủy phiên bản khóa/định dạng.
10. **Giám sát sự cố:** theo dõi lỗi tag, truy cập chéo tenant, lạm dụng Decrypt, thay chính sách và kế hoạch điều tra khóa lộ.

### Bảng đối chiếu cách lưu AAD

| Cách lưu | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| Lưu chính xác byte AAD cùng ciphertext | Dễ tái hiện phép xác thực | Không bảo đảm AAD khớp tenant/document mong đợi nếu chỉ tin byte đã lưu; có thể làm lộ metadata |
| Lưu các trường và dựng lại AAD | Linh hoạt truy vấn, metadata có cấu trúc | Phải chuẩn hóa byte và phân quyền nguồn trường; migration cần versioning |
| Dựng AAD từ định danh tài nguyên đáng tin ở server | Giúp ràng buộc bản mã với tài nguyên đang được yêu cầu | Cần có nguồn ID/ownership bền vững; đổi định danh có thể đòi hỏi re-encrypt |
| Bỏ AAD (dùng AAD rỗng) | AEAD vẫn có thể bảo vệ ciphertext | Không có ràng buộc mật mã bổ sung với metadata nghiệp vụ |

**AAD rỗng không tự động làm AEAD mất an toàn:** nếu ứng dụng không có metadata cần ràng buộc, mã hóa xác thực vẫn bảo vệ ciphertext. Vấn đề xuất hiện khi nghiệp vụ **cần** gắn bản mã với một ngữ cảnh mà hệ thống lại bỏ trống hoặc xây sai AAD.

## 10. Những hiểu nhầm thường gặp

**“AAD được mã hóa cùng plaintext.”** Không đúng. AAD được **xác thực** nhưng **không được mã hóa** bởi thao tác AEAD. Nếu muốn giấu tenant hoặc nội dung trường, phải thiết kế riêng cơ chế bảo mật cho trường đó.

**“Nếu đổi AAD mà giải mã thất bại thì hệ thống đã có phân quyền tốt.”** Không đúng. Giải mã thất bại có thể chứng minh ngữ cảnh không khớp theo AEAD; phân quyền vẫn cần kiểm tra người dùng có được đọc tenant/record hay không.

**“Thêm tenant ID vào AAD luôn ngăn mọi cuộc tấn công tráo bản ghi.”** Chỉ đúng trong mô hình mà bên giải mã xây **AAD kỳ vọng từ nguồn đáng tin**. Nếu chuyển cả bản mã và tenant ID rồi ứng dụng tin metadata bị thay thế, AAD có thể không ngăn được.

**“AAD làm timestamp chống phát lại.”** Xác thực timestamp chỉ ngăn sửa giá trị timestamp mà không có khóa; nó không cấm dùng lại một thông điệp hợp lệ đã xuất hiện trước đó.

**“Key ID đã lưu trong JSON là xác thực rồi.”** Key ID chỉ giúp chọn khóa. Nếu cần ràng buộc key ID/version vào một bản ghi, phải xác định rõ cách xác thực và tránh tin khóa do client tùy ý chỉ định.

**“Mọi mã hóa đối xứng đều có updateAAD.”** Không đúng. AAD là tính năng của cơ chế **AEAD** phù hợp; API AES-CBC không tự có khả năng này. Chuyển một hệ thống CBC sang AEAD cần thiết kế định dạng, di chuyển dữ liệu và xử lý lỗi đúng cách.

**“Có AAD nên không cần quan tâm nonce.”** Không đúng. Với AES-GCM, **tái sử dụng nonce dưới cùng khóa** có thể làm mất cả bí mật và toàn vẹn dữ liệu.

**“Tag sai thì thử giải mã không có AAD.”** Đây là cách hạ cấp bảo mật nguy hiểm nếu ứng dụng đang dùng AAD để ràng buộc tenant/document. Phải xử lý lỗi và điều tra nguyên nhân.

## 11. Checklist và câu hỏi tự kiểm tra

### Checklist

1. Metadata nào cần **toàn vẹn** nhưng không cần mã hóa?
2. AAD có chứa thông tin bí mật hoặc dữ liệu cá nhân cần che giấu không?
3. Byte AAD được mã hóa xác định theo **schema, charset, thứ tự, length-prefix và version** chưa?
4. Tenant/document ID có lấy từ **nguồn đã xác thực và phân quyền** không?
5. Bên mã hóa và giải mã có dùng **cùng AAD bytes** dưới đúng key/nonce không?
6. Có bảo đảm **nonce không trùng dưới cùng AES-GCM key** và quản lý giới hạn sử dụng khóa không?
7. Có lưu đúng **ciphertext, tag, nonce, key ID/version, wrapped DEK và AAD version** cho dữ liệu lâu dài không?
8. Có kiểm tra quyền **trước KMS Decrypt/Unwrap** và không phát plaintext trước khi tag hợp lệ không?
9. Có chống replay/idempotency ở tầng nghiệp vụ nếu thông điệp là giao dịch hoặc sự kiện không?
10. Có kế hoạch **rotation, migration AAD version, backup/restore, audit và xử lý tag sai** không?

### Câu hỏi 1: AAD có phải một phần của plaintext được mã hóa?

**Trả lời:** Không. AAD được đưa vào phép xác thực AEAD, nhưng không được mã hóa bởi thao tác đó. Bên giải mã phải cung cấp cùng AAD để kiểm tra tag.

### Câu hỏi 2: Vì sao đưa tenant ID từ bản ghi database vào AAD vẫn có thể không ngăn được tráo bản ghi?

**Trả lời:** Nếu attacker có thể chuyển cả ciphertext, tag, nonce và tenant ID nguyên vẹn, ứng dụng có thể dùng chính tenant ID giả/được di chuyển làm AAD và giải mã thành công. Hệ thống phải ràng buộc AAD với **tenant từ identity và quyền đối với tài nguyên**.

### Câu hỏi 3: AAD chứa timestamp thì có chống replay không?

**Trả lời:** AAD xác thực timestamp không bị thay đổi; nhưng bộ thông điệp cũ hợp lệ có thể được gửi lại. Chống replay cần thêm cửa sổ thời gian, trạng thái, sequence, idempotency hoặc quy tắc giao thức phù hợp.

### Câu hỏi 4: Nếu thay dấu phân cách hoặc thứ tự trường trong AAD, dữ liệu cũ có còn giải mã được không?

**Trả lời:** Có thể **không**, vì byte AAD khác làm tag không khớp. Phải lưu hoặc xác định phiên bản cấu trúc cũ, hỗ trợ giải mã đúng quy tắc cũ và lập kế hoạch di chuyển.

### Câu hỏi 5: AES-GCM xác thực AAD có giúp phục hồi an toàn khi DEK bị lộ không?

**Trả lời:** Không. Người có DEK có thể tạo bản mã và tag mới hợp lệ với AAD tùy ý. Cần điều tra, thu hồi quyền, thay khóa và re-encrypt dữ liệu liên quan nếu cần.

### Câu hỏi 6: KMS encryption context có tự động thay thế updateAAD của AES-GCM trong Java không?

**Trả lời:** Không. KMS context có thể bảo vệ/ràng buộc **wrapped DEK** ở tầng KMS; updateAAD bảo vệ **ciphertext nội dung** ở tầng AEAD của ứng dụng. Hai phạm vi phải được thiết kế và kiểm tra riêng.

## Kết luận

**Associated data (AAD) là metadata được xác thực nhưng không được mã hóa** trong một phép AEAD. Khi được xây từ ngữ cảnh tin cậy và mã hóa thành byte nhất quán, AAD giúp bảo vệ mối liên hệ giữa ciphertext với **tenant, tài nguyên, phiên bản, mục đích hoặc header giao thức**.

AAD phát huy giá trị khi đi cùng **AES-GCM hoặc AEAD phù hợp, nonce duy nhất, DEK/KEK được bảo vệ bởi KMS/HSM, quyền truy cập tối thiểu, rotation có kế hoạch và audit**. Chính sách kiểm tra chủ thể/tài nguyên và chống replay vẫn thuộc tầng giao thức/nghiệp vụ. Một hệ thống quản lý khóa an toàn cần đồng thời bảo vệ **vật liệu khóa**, **quyền sử dụng khóa** và **ngữ cảnh mà dữ liệu được phép giải mã**.
