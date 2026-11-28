# ChaCha20-Poly1305

> **Chương:** Mật mã đối xứng  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. ChaCha20-Poly1305 là gì và giải quyết bài toán nào?

**ChaCha20-Poly1305** là một cơ chế **mã hóa đối xứng có xác thực (AEAD — Authenticated Encryption with Associated Data)** kết hợp hai thành phần:

- **ChaCha20:** mật mã dòng (stream cipher) tạo luồng byte giả ngẫu nhiên từ khóa bí mật, nonce và bộ đếm; dữ liệu rõ được XOR với luồng này để tạo bản mã.
- **Poly1305:** thuật toán tạo mã xác thực thông điệp (MAC) dùng khóa một lần, cung cấp thẻ xác thực (authentication tag) để kiểm tra tính toàn vẹn và tính xác thực trong phạm vi các bên biết khóa.

Hai thành phần được **kết hợp theo một quy tắc AEAD xác định**, không phải cứ mã hóa bằng ChaCha20 rồi tự nối một MAC tùy ý là thành ChaCha20-Poly1305. Cấu trúc IETF được mô tả trong **RFC 8439**; đây là biến thể thường gặp trong thư viện mật mã và giao thức TLS 1.3.

Giả sử dịch vụ lưu địa chỉ giao hàng hoặc gửi dữ liệu nhạy cảm qua một kênh mạng. Dùng mã hóa đơn thuần có thể che giấu nội dung, nhưng nếu bản mã bị sửa hoặc bị tráo sang đối tượng khác thì ứng dụng phải có cách phát hiện. ChaCha20-Poly1305 giải quyết đồng thời:

1. **Confidentiality — tính bí mật:** người không có khóa không thể khôi phục plaintext một cách khả thi từ ciphertext.
2. **Integrity — tính toàn vẹn:** thay đổi trái phép ciphertext, tag hoặc dữ liệu ngữ cảnh được xác thực sẽ khiến phép giải mã thất bại với xác suất bỏ lọt rất nhỏ, theo giả định an toàn của thuật toán.
3. **Authenticated associated data — xác thực metadata:** có thể ràng buộc ciphertext với tenant, loại thông điệp, ID bản ghi hoặc phiên bản giao thức mà không cần mã hóa những trường đó.

**Điều kiện trọng yếu:** mỗi lần mã hóa bằng một khóa phải dùng **nonce không trùng**. Tái sử dụng cặp **(key, nonce)** là lỗi nghiêm trọng có thể làm mất cả bảo mật nội dung lẫn bảo đảm xác thực.

## 2. Đầu vào và đầu ra của AEAD ChaCha20-Poly1305

| Thành phần | Kích thước / vai trò | Có cần giữ bí mật? |
| --- | --- | --- |
| **Key** | Khóa đối xứng **256 bit (32 byte)** | **Có**; chỉ thành phần được cấp quyền mới được sử dụng |
| **Nonce** | Biến thể IETF dùng **96 bit (12 byte)**, phải duy nhất dưới cùng khóa | Không; nhưng **không được dùng lại** với cùng key |
| **Plaintext** | Dữ liệu cần che giấu | Có, theo chính sách dữ liệu |
| **AAD (Additional Authenticated Data)** | Metadata được xác thực nhưng không mã hóa | Không nhất thiết; phải đúng byte khi giải mã |
| **Ciphertext** | Dữ liệu mã hóa có cùng độ dài plaintext | Có thể lưu hoặc truyền, nhưng vẫn cần kiểm soát truy cập theo dữ liệu |
| **Authentication tag** | **128 bit (16 byte)** với cấu trúc RFC 8439 | Không; phải được kiểm tra trước khi chấp nhận kết quả |

Mô hình khái niệm:

~~~text
(ciphertext, tag) = Seal(key, nonce, plaintext, AAD)

plaintext = Open(key, nonce, ciphertext, tag, AAD)
           hoặc lỗi xác thực nếu dữ liệu không hợp lệ
~~~

Để giải mã thành công, ứng dụng cần **đúng khóa, đúng nonce, ciphertext, tag và chuỗi byte AAD tương ứng**. Không được bỏ qua lỗi xác thực hoặc dùng plaintext đã giải mã một phần sau khi tag không hợp lệ.

### Nonce không phải là khóa

Nonce có thể được lưu cùng ciphertext; tính an toàn không phụ thuộc vào việc giữ bí mật nonce. Nó phụ thuộc vào **tính duy nhất của nonce cho mỗi key**. Một nonce 12 byte lấy từ CSPRNG thường hữu ích trong ví dụ nhỏ, nhưng ở hệ thống có lưu lượng lớn hoặc nhiều instance, phải đánh giá xác suất trùng và cân nhắc chiến lược đếm/định danh có bảo đảm duy nhất. Không dùng timestamp đơn lẻ làm nonce vì nhiều request có thể diễn ra cùng thời điểm.

### AAD được xác thực nhưng không được mã hóa

Ví dụ một bản ghi có ciphertext của số tài khoản và metadata:

~~~json
{
  "tenantId": "tenant-42",
  "recordId": "record-1001",
  "algorithm": "ChaCha20-Poly1305",
  "keyVersion": "v3",
  "nonce": "<base64-of-12-bytes>",
  "ciphertextAndTag": "<base64>"
}
~~~

Ứng dụng có thể dùng **tenant ID + record ID + định dạng dữ liệu** làm AAD. Khi một bản mã bị chuyển sang bản ghi khác mà ngữ cảnh xác thực thay đổi, tag sẽ không còn hợp lệ. Tuy nhiên, **AAD do client tự cung cấp không phải nguồn sự thật về quyền truy cập**. Server phải kiểm tra quyền người dùng và xác định tenant/record từ ngữ cảnh đã được xác thực, đồng thời chuẩn hóa cách mã hóa AAD để cả hai chiều có cùng chuỗi byte.

## 3. ChaCha20 và Poly1305 phối hợp như thế nào?

Trong biến thể IETF, ChaCha20 dùng key 256 bit, nonce 96 bit và bộ đếm khối 32 bit. ChaCha20 xử lý dữ liệu theo các khối luồng khóa **64 byte**; ciphertext được tạo bằng phép XOR plaintext với luồng khóa tương ứng.

Điểm đặc biệt của AEAD là cách dùng ChaCha20 để tạo **khóa Poly1305 dùng đúng một lần cho một bản mã**:

1. Từ key và nonce, **khối ChaCha20 có counter = 0** tạo vật liệu cho khóa Poly1305 một lần (32 byte đầu của khối; cách xử lý nội bộ theo RFC 8439).
2. Dữ liệu được mã hóa bằng ChaCha20, **bắt đầu từ counter = 1**, để không dùng lại khối luồng khóa dành cho Poly1305.
3. Poly1305 tính tag trên AAD và ciphertext, với các phần đệm và trường độ dài theo định dạng AEAD được quy định.
4. Bên nhận tính lại tag dưới cùng key và nonce; chỉ chấp nhận plaintext nếu xác thực thành công.

~~~mermaid
flowchart TD
    K[Key 256 bit] --> B0[ChaCha20 counter = 0]
    N[Nonce 96 bit] --> B0
    B0 --> OTP[Khóa Poly1305 dùng một lần]
    K --> B1[ChaCha20 counter từ 1]
    N --> B1
    P[Plaintext] --> B1
    B1 --> C[Ciphertext]
    C --> M[Định dạng MAC: AAD + đệm + ciphertext + độ dài]
    A[AAD] --> M
    OTP --> T[Poly1305 tạo tag 128 bit]
    M --> T
    C --> O[Đầu ra AEAD]
    T --> O
~~~

Ở mức chi tiết, đầu vào MAC trong RFC 8439 là AAD, phần đệm đến bội số 16 byte, ciphertext, phần đệm tương ứng, sau đó là hai trường độ dài **64 bit little-endian** của AAD và ciphertext. **Không tự triển khai** trình tự này trong ứng dụng: sử dụng primitive AEAD hoàn chỉnh từ thư viện được duy trì để tránh lỗi thứ tự byte, độ dài và kiểm tra tag.

**Giới hạn kỹ thuật:** biến thể IETF có bộ đếm khối 32 bit; dữ liệu được mã hóa của một lần dùng nonce bị giới hạn bởi số khối ChaCha20 có thể sử dụng (xấp xỉ dưới 256 GiB). Các thư viện có thể áp đặt giới hạn chặt hơn. Đây **không phải** lý do để mã hóa hàng trăm GiB thành một bản tin; dữ liệu lớn thường được chia thành các bản ghi/chunk có ràng buộc thứ tự, nonce và tag riêng theo một giao thức đã được thiết kế.

## 4. Vì sao tái sử dụng key và nonce là lỗi nghiêm trọng?

ChaCha20 là mật mã dòng: đối với một key và nonce cố định, nó tạo ra cùng luồng khóa. Nếu mã hóa hai plaintext khác nhau **P1** và **P2** bằng cùng cặp key/nonce thì:

~~~text
C1 = P1 XOR keystream
C2 = P2 XOR keystream

C1 XOR C2 = P1 XOR P2
~~~

Kẻ tấn công có hai ciphertext có thể suy ra quan hệ giữa hai plaintext; nếu biết một plaintext hoặc đoán được cấu trúc, họ có thể khôi phục thêm dữ liệu. Ngoài ra, khóa Poly1305 một lần cũng bị **tái sử dụng** dưới cùng cặp key/nonce, phá vỡ giả định an toàn của cơ chế xác thực và tạo thêm nguy cơ giả mạo.

Đây là vấn đề **đúng sai ở cách dùng thuật toán**, không thể khắc phục bằng cách tăng entropy của key từ 256 bit lên một độ dài tùy ý. **IETF ChaCha20-Poly1305 không có cơ chế chịu lỗi reuse nonce**; đừng nhầm nó với các chế độ AEAD được thiết kế để giảm tác hại khi nonce bị dùng lại.

### Hai chiến lược quản lý nonce

| Cách tạo nonce | Ưu điểm | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Ngẫu nhiên 96 bit từ CSPRNG** | Dễ dùng cho số lượng bản tin giới hạn; không cần bộ đếm bền vững | Xác suất trùng tăng theo số lần mã hóa dưới cùng key; phải giới hạn lưu lượng và rotation |
| **Bộ đếm duy nhất theo key** | Có thể bảo đảm không trùng nếu phân bổ chuẩn | Trùng sau restart/rollback, nhiều máy cùng dùng bộ đếm hoặc tràn bộ đếm |
| **Phân vùng nonce theo instance + counter** | Phù hợp hệ thống phân tán khi thiết kế đầy đủ | Phải cấp phát prefix/namespace duy nhất và dự phòng restart, failover |

Với hệ thống nhiều node, **không để mỗi node tự khởi tạo counter = 0 dưới cùng key**. Nếu dùng bộ đếm, phải lưu trạng thái bền vững hoặc phân phối miền nonce không chồng lấn, bảo vệ trước snapshot rollback và thay đổi topology.

Khóa mới giúp tạo **miền nonce mới**. Tuy nhiên, chọn khóa mới khi nào cần xét khối lượng thông điệp, giới hạn kỹ thuật và chính sách bảo vệ dữ liệu; không nên chỉ dựa vào lịch ngày tháng.

## 5. ChaCha20-Poly1305 bảo vệ được gì và không bảo vệ được gì?

### Bảo đảm khi dùng đúng

- Che giấu plaintext trước người chỉ quan sát ciphertext.
- Phát hiện sửa đổi ciphertext và AAD thông qua xác minh tag.
- Cho phép gắn bản mã với một ngữ cảnh đã định, ví dụ tenant ID và record ID.
- Hoạt động trên nhiều nền tảng mà không đòi hỏi phần cứng tăng tốc AES chuyên dụng để có hiệu năng tốt trong nhiều trường hợp.

### Những việc AEAD không tự giải quyết

- **Replay:** kẻ tấn công có thể phát lại một bản tin AEAD hợp lệ. Cần sequence number, ID giao dịch, timestamp/cửa sổ thời gian và trạng thái chống phát lại ở tầng giao thức nếu ứng dụng yêu cầu.
- **Phân quyền:** biết key hoặc có quyền gọi KMS không có nghĩa được phép đọc mọi dữ liệu. Cần kiểm tra quyền nghiệp vụ với mỗi đối tượng.
- **Xác thực danh tính ngoài giao thức:** tag chứng minh dữ liệu do một chủ thể có quyền dùng key tạo ra, không xác nhận riêng biệt cá nhân nào đã gửi khi nhiều bên chia sẻ key.
- **Chữ ký số / chống chối bỏ:** AEAD dùng secret key chung, không thay cho chữ ký bất đối xứng.
- **Bảo vệ khi endpoint bị chiếm:** plaintext hoặc key đang nằm trong bộ nhớ ứng dụng vẫn có thể bị lộ.
- **Xóa dữ liệu:** xoay key không xóa mọi plaintext, cache, backup hoặc dữ liệu đã bị đọc trước đó.

### So sánh với AES-GCM

| Tiêu chí | ChaCha20-Poly1305 (IETF) | AES-GCM |
| --- | --- | --- |
| Nền tảng mật mã | ChaCha20 (mật mã dòng) + Poly1305 MAC | AES (mật mã khối) ở chế độ GCM |
| Kích thước khóa điển hình | 256 bit | 128, 192 hoặc 256 bit theo AES; triển khai phổ biến dùng 128/256 |
| Nonce thông dụng | 96 bit, **không lặp dưới cùng key** | 96 bit là lựa chọn thông dụng, **không lặp dưới cùng key** |
| Authentication tag thông thường | 128 bit | Thường 128 bit, có cấu hình độ dài khác theo cơ chế cụ thể |
| Hiệu năng | Có thể thuận lợi trên máy không có AES hardware acceleration | Thường rất mạnh trên phần cứng có AES-NI/PMULL hoặc tăng tốc tương đương |
| Tích hợp | TLS 1.3, thư viện AEAD, JCA/JCE hỗ trợ trong JDK phù hợp | TLS, hệ thống lưu trữ, nhiều dịch vụ KMS/HSM |

Không có thuật toán nào **luôn nhanh hơn hoặc luôn an toàn hơn trong mọi môi trường**. Lựa chọn phải dựa trên thư viện, cấu hình hệ thống, yêu cầu tương thích, tiêu chuẩn áp dụng và thử nghiệm trên phần cứng thực tế. Với cả hai, **nonce reuse** đều là lỗi thiết kế rất nghiêm trọng.

## 6. Ví dụ Java 17: mã hóa và xác minh với JCA

Java 11 trở lên có hỗ trợ chuẩn **ChaCha20-Poly1305** qua JCA/JCE trong provider phù hợp. Ví dụ dưới đây chạy trên JDK 17 hỗ trợ thuật toán: sinh key bằng **KeyGenerator**, sinh nonce 12 byte bằng **SecureRandom**, xác thực AAD, mã hóa và giải mã bằng **Cipher**. Dữ liệu thử nghiệm không phải thông tin thật.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaCha20Poly1305Example {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_LENGTH = 12;

    static byte[] encrypt(
            SecretKey key, byte[] nonce, byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        // Với JCA, output chứa ciphertext và authentication tag.
        return cipher.doFinal(plaintext);
    }

    static byte[] decrypt(
            SecretKey key, byte[] nonce, byte[] aad, byte[] ciphertextAndTag)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        // Ném AEADBadTagException nếu tag / AAD / ciphertext sai.
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();

        // Mỗi lần mã hóa dưới cùng key phải dùng nonce duy nhất.
        // Demo chỉ mã hóa một lần; production cần chiến lược nonce đầy đủ.
        byte[] nonce = new byte[NONCE_LENGTH];
        RANDOM.nextBytes(nonce);

        // Ứng dụng thực cần định dạng AAD nhất quán và tin cậy.
        byte[] aad = "tenant-42|record-1001|format-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Du lieu mau"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ciphertextAndTag = encrypt(key, nonce, aad, plaintext);
        byte[] restored = decrypt(key, nonce, aad, ciphertextAndTag);

        if (!Arrays.equals(plaintext, restored)) {
            throw new IllegalStateException("Decryption mismatch");
        }
        System.out.println("AEAD encryption/decryption: OK");

        // Kiểm thử: sửa tag/bản mã phải làm giải mã thất bại.
        byte[] tampered = ciphertextAndTag.clone();
        tampered[tampered.length - 1] ^= 1;
        try {
            decrypt(key, nonce, aad, tampered);
            throw new AssertionError("Tampered message was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered data rejected: OK");
        }
    }
}
~~~

Trong ví dụ này, `nonce` **được dùng lại khi giải mã chính bản mã vừa tạo**, điều đó là bình thường vì giải mã cần đúng nonce đã dùng khi mã hóa. Lệnh cấm là **không mã hóa một thông điệp mới bằng cùng cặp (key, nonce)**.

Lưu ý khi đưa code vào sản phẩm:

1. **Không lưu key dạng rõ cùng ciphertext.** Ví dụ chỉ giữ key trong bộ nhớ để minh họa API; ứng dụng thật cần chiến lược KMS, envelope encryption và kiểm soát quyền.
2. **AAD phải có mã hóa không mơ hồ** (ví dụ protobuf/canonical binary với trường có độ dài rõ ràng), đồng nhất khi mã hóa và giải mã; không dùng cách nối trường thiếu phân tách nếu có thể tạo cùng chuỗi byte từ nhiều bộ giá trị khác nhau.
3. **Không nuốt AEADBadTagException.** Nếu sai tag, phải từ chối toàn bộ bản tin; không tự thử lại bằng key hoặc AAD không phù hợp chỉ để “giải mã được”.
4. **Không log key, nonce–key relationship nhạy cảm, plaintext hay toàn bộ dữ liệu đã giải mã.** Nonce không phải bí mật, nhưng log có thể tiết lộ thông tin ngữ cảnh và tạo bề mặt quan sát không cần thiết.
5. **Đảm bảo nonce không trùng trên toàn bộ các instance dùng chung key.** SecureRandom riêng từng instance giúp tạo giá trị khó đoán nhưng không tạo cam kết tuyệt đối về tính duy nhất khi số lượng bản tin tăng.
6. **Không tự cắt authentication tag.** Định dạng tag và cách đóng gói phụ thuộc API/thư viện; ví dụ JCA trả ciphertext kèm tag.

## 7. Ứng dụng với KMS, HSM và envelope encryption

Với dữ liệu lưu trữ, secret key 256 bit dùng cho ChaCha20-Poly1305 có thể đóng vai trò **DEK (Data Encryption Key)**. Để không phải lưu DEK dạng rõ bên cạnh dữ liệu, kiến trúc thường sử dụng **KEK (Key Encryption Key)** được quản lý bằng KMS/HSM.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS / HSM
    participant Store as Kho dữ liệu
    App->>KMS: Xin tạo / bảo vệ DEK theo quyền
    KMS-->>App: DEK dạng rõ tạm thời + wrapped DEK
    App->>App: Tạo nonce duy nhất và AAD
    App->>App: ChaCha20-Poly1305 Seal(DEK, nonce, plaintext, AAD)
    App->>Store: Lưu ciphertext + tag + nonce + wrapped DEK + metadata
    Store-->>App: Đọc payload đã mã hóa
    App->>KMS: Mở bọc DEK theo quyền
    KMS-->>App: DEK dạng rõ nếu được phép
    App->>App: Open(DEK, nonce, ciphertext, tag, AAD)
~~~

**Điều kiện tích hợp quan trọng:** nhiều dịch vụ KMS cung cấp AES, RSA hoặc API wrap/unwrap riêng; **không được giả định KMS nào cũng cung cấp API ChaCha20-Poly1305 trực tiếp**. Có thể dùng một DEK 256 bit được sinh an toàn cho ChaCha20-Poly1305 ở ứng dụng, còn KMS/HSM bảo vệ DEK qua cơ chế bọc khóa mà nhà cung cấp hỗ trợ. Hợp đồng tạo DEK và cơ chế trả về wrapped DEK khác nhau tùy dịch vụ, cần kiểm tra khả năng tương thích.

Một payload lưu trữ có thể chứa:

~~~json
{
  "formatVersion": 1,
  "algorithm": "ChaCha20-Poly1305",
  "kekId": "customer-data-key",
  "kekVersion": "v3",
  "wrappedDek": "<base64>",
  "nonce": "<base64>",
  "ciphertextAndTag": "<base64>",
  "aadContext": {
    "tenantId": "tenant-42",
    "recordId": "record-1001"
  }
}
~~~

Phải định nghĩa **quy tắc mã hóa AAD thành byte** và lưu đủ thông tin để tái tạo đúng AAD ở lần giải mã sau. Nên đưa những trường cần được chống tráo đổi — chẳng hạn phiên bản định dạng, thuật toán, ID đối tượng và các metadata liên quan — vào ngữ cảnh xác thực theo thiết kế. Định danh khóa và metadata do kho dữ liệu cung cấp chỉ được dùng sau khi kiểm tra tính hợp lệ và quyền; nếu cho phép chọn tùy ý key ID, ứng dụng có thể có rủi ro sử dụng nhầm khóa hoặc vượt tenant.

### Xoay vòng DEK và KEK

- **Rotation KEK:** tạo phiên bản khóa bọc mới; có thể **rewrap DEK** dưới KEK mới mà không cần mã hóa lại dữ liệu bằng ChaCha20-Poly1305, nếu cơ chế bọc hỗ trợ.
- **Rotation DEK:** dữ liệu do DEK cũ mã hóa thường phải được **giải mã rồi mã hóa lại** với DEK mới và nonce mới, sau đó tạo tag mới.
- **Sự cố DEK bị lộ:** việc chỉ rewrap DEK cũ **không loại bỏ** nguy cơ giải mã ciphertext đã bị thu thập; phải đánh giá thay DEK, mã hóa lại dữ liệu, thu hồi quyền và xử lý các bản sao.
- **Cryptoperiod:** thời gian được phép mã hóa dữ liệu mới dưới một DEK có thể kết thúc trước thời gian cần giải mã dữ liệu cũ. Không hủy DEK/KEK khi backup còn phụ thuộc mà chưa có phương án phục hồi.

## 8. ChaCha20-Poly1305 trong TLS 1.3

TLS 1.3 hỗ trợ bộ mã **TLS_CHACHA20_POLY1305_SHA256**. Tên bộ mã cho biết AEAD dùng ChaCha20-Poly1305 và hàm băm dùng trong key schedule là SHA-256. **Không có nghĩa TLS đang dùng một khóa ChaCha20 cố định mãi mãi**.

TLS 1.3 sử dụng cơ chế thiết lập bí mật, dẫn xuất **traffic keys** theo hướng truyền và giai đoạn kết nối, đồng thời quản lý nonce, thứ tự bản ghi, giới hạn bản ghi và key update theo đặc tả. Ứng dụng sử dụng thư viện TLS chuẩn **không cần sinh nonce hoặc tính Poly1305 tag thủ công cho từng bản ghi TLS**.

Chữ ký số và chứng thư của máy chủ phục vụ **xác thực danh tính**, trong khi ChaCha20-Poly1305 bảo vệ dữ liệu phiên theo khóa đối xứng được dẫn xuất. Forward secrecy phụ thuộc vào cơ chế thỏa thuận khóa (ví dụ (EC)DHE) và cách bảo vệ bí mật tạm thời, **không phải một thuộc tính tự động của riêng ChaCha20-Poly1305**.

Ở lớp ứng dụng, nếu dữ liệu còn cần bảo vệ **sau khi TLS được giải mã tại máy chủ**, phải cân nhắc mã hóa dữ liệu lưu trữ hoặc mã hóa đầu cuối riêng. TLS không tự thay thế cho key management của DEK và KEK.

## 9. Các sai sót thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng lại **(key, nonce)** khi mã hóa | Lộ quan hệ plaintext, phá bảo đảm xác thực | Cấp nonce duy nhất hoặc chia miền nonce; rotation đúng giới hạn |
| Chỉ dùng ChaCha20, bỏ Poly1305 trong bài toán AEAD | Không có kiểm tra toàn vẹn và xác thực tương đương | Dùng primitive **ChaCha20-Poly1305** hoàn chỉnh |
| Dùng AAD khác nhau giữa encrypt/decrypt | Giải mã luôn thất bại hoặc tạo lỗi thiết kế | Định dạng AAD canonical; quản lý phiên bản payload |
| Tin tenant ID do client gửi là đủ để phân quyền | Có thể giải mã hoặc truy cập sai tenant | Ràng buộc tenant bằng danh tính đã xác thực và quyền nghiệp vụ |
| Bỏ qua lỗi xác minh tag | Có thể xử lý bản tin đã bị thay đổi | Từ chối toàn bộ thông điệp khi xác thực thất bại |
| Sinh nonce từ timestamp hoặc counter reset | Có thể trùng ở cùng key, đặc biệt giữa nhiều node | CSPRNG có giới hạn sử dụng hoặc counter được phân phối an toàn |
| Lưu DEK dạng rõ trong DB cạnh ciphertext | Lộ DB có thể lộ cả khóa | Envelope encryption, tách KMS/HSM và IAM |
| Coi đổi KEK là đã thay DEK bị lộ | Bản mã cũ vẫn chịu rủi ro | Xác định sự cố, thay DEK/re-encrypt khi cần |
| Không có key ID hoặc phiên bản định dạng | Mất khả năng giải mã sau rotation | Lưu metadata đầy đủ, kiểm tra tương thích |
| Xử lý dữ liệu lớn như một bản tin AEAD không giới hạn | Vượt giới hạn thư viện/thuật toán, khó khôi phục | Dùng giao thức chunked AEAD có nonce, thứ tự và kết thúc được xác thực |
| Dùng tag AEAD như chữ ký số | Không có tính không thể chối bỏ giữa các bên chung khóa | Dùng chữ ký bất đối xứng khi cần bằng chứng ký |
| Tin rằng mã hóa đã chặn replay | Bản tin hợp lệ có thể bị gửi lại | Thêm bảo vệ chống replay ở giao thức/ứng dụng |

## 10. Tình huống thiết kế: dữ liệu khách hàng nhiều tenant

Một nền tảng lưu số điện thoại và địa chỉ giao hàng của nhiều doanh nghiệp. Dữ liệu cần được bảo vệ khi lưu trên cơ sở dữ liệu. Nhóm kỹ thuật chọn ChaCha20-Poly1305 cho mã hóa ứng dụng và dùng KMS để bảo vệ DEK.

**Khi ghi một bản ghi:**

1. API xác thực người gọi và kiểm tra quyền ghi lên đúng tenant/record.
2. Dịch vụ lấy DEK theo chính sách; nếu dùng DEK chung cho nhiều bản ghi thì áp dụng chiến lược nonce không trùng xuyên mọi instance. Một phương án khác là DEK mới cho phạm vi dữ liệu nhỏ hơn để giảm số lần dùng mỗi key.
3. Dịch vụ mã hóa plaintext với nonce mới; AAD ràng buộc tenant ID, record ID và format version theo cách mã hóa byte thống nhất.
4. Dịch vụ lưu ciphertext kèm tag, nonce, wrapped DEK, key ID/version và metadata cần thiết; không lưu DEK dạng rõ.

**Khi đọc:**

1. API kiểm tra quyền đọc dữ liệu từ danh tính người dùng, không chỉ từ yêu cầu gửi lên.
2. Dịch vụ lấy bản mã và metadata đã kiểm tra; KMS xác thực workload và kiểm tra quyền mở bọc DEK.
3. Dịch vụ tái tạo AAD từ tenant và record đã được xác thực, giải mã và kiểm tra tag.
4. Nếu tag sai, dịch vụ từ chối và ghi audit phù hợp; không trả plaintext, không tự “sửa” AAD theo dữ liệu bên ngoài.

**Khi có nghi ngờ một DEK bị lộ:** nhóm vận hành xem phạm vi bản ghi/tenant bị ảnh hưởng, khóa quyền không hợp lệ, điều tra KMS audit, chuyển dữ liệu cần thiết sang DEK mới và xử lý các bản sao plaintext/khóa còn tồn tại. Không chỉ đổi tên key version rồi coi dữ liệu cũ đã an toàn.

**Khi cần xuất dữ liệu lớn:** không chia ciphertext thành các đoạn rồi tùy ý mã hóa lại bằng cùng nonce; nếu chunking, mỗi chunk phải có nonce không trùng, tag riêng, sequence number và cơ chế xác thực tổng thể để phát hiện mất, trùng hoặc hoán đổi chunk.

## 11. Checklist triển khai an toàn

- [ ] Sử dụng **ChaCha20-Poly1305 AEAD** hoàn chỉnh từ thư viện mật mã tin cậy?
- [ ] Secret key dài 256 bit, được sinh bằng nguồn ngẫu nhiên mật mã phù hợp hoặc qua quy trình KMS?
- [ ] Nonce 96 bit **duy nhất với mỗi key** ở mọi node, kể cả sau restart/failover/restore?
- [ ] Thư viện tạo và xác minh đúng tag 128 bit, không cho qua lỗi `AEADBadTagException`?
- [ ] Dùng AAD đúng byte ở cả hai chiều, gắn với context đã xác thực và định dạng không mơ hồ?
- [ ] Có chống replay nếu ứng dụng truyền các thao tác có thể bị phát lại?
- [ ] Có key ID/version, algorithm/version, nonce và wrapped DEK phù hợp trong payload?
- [ ] DEK và KEK có mục đích tách biệt, quyền truy cập tối thiểu và quản lý bởi KMS/HSM khi phù hợp?
- [ ] Có kế hoạch rotation DEK/KEK, readback dữ liệu cũ, backup và hủy khóa?
- [ ] Không đưa key, plaintext hay dữ liệu nhạy cảm vào log, trace, memory dump được chia sẻ?
- [ ] Có giám sát lượng mã hóa theo key, nguy cơ trùng nonce, thất bại tag và thay đổi policy?
- [ ] Với dữ liệu lớn, đã thiết kế chunking có xác thực thứ tự thay vì tái dùng nonce?
- [ ] Đã xác minh tương thích JDK/provider, định dạng ciphertext/tag và yêu cầu tiêu chuẩn hệ thống?

## 12. Câu hỏi tự kiểm tra

**1. ChaCha20 khác Poly1305 ở điểm nào?**  
ChaCha20 là mật mã dòng để che giấu plaintext. Poly1305 là MAC để xác thực nội dung; trong AEAD, khóa Poly1305 một lần được dẫn xuất từ ChaCha20 theo RFC 8439.

**2. Vì sao nonce được lưu công khai mà vẫn phải duy nhất?**  
Nonce không phải vật liệu bí mật. Tuy nhiên, cùng key và nonce sẽ tạo lại luồng ChaCha20 và khóa Poly1305 một lần, có thể phá vỡ bảo mật và xác thực.

**3. AAD có được mã hóa không?**  
Không. AAD được xác thực cùng ciphertext nhưng vẫn ở dạng rõ. Cần kiểm soát nguồn và định dạng AAD để ràng buộc bản mã với đối tượng đúng.

**4. ChaCha20-Poly1305 có chống phát lại bản tin không?**  
Không tự động. Một ciphertext/tag hợp lệ có thể được gửi lại; giao thức phải kiểm soát sequence number, thời gian, ID thông điệp hoặc trạng thái chống replay nếu có yêu cầu.

**5. Vì sao KMS rotation KEK chưa chắc khắc phục sự cố lộ DEK?**  
Vì DEK cũ vẫn là khóa trực tiếp giải mã dữ liệu. Bọc lại DEK bằng KEK mới không vô hiệu hóa bản DEK mà kẻ tấn công đã lấy được.

**6. Vì sao Java cần `updateAAD()` trước `doFinal()`?**  
AAD là ngữ cảnh xác thực phải được đưa vào primitive AEAD trước khi xử lý hoàn tất thông điệp; khi giải mã phải dùng đúng AAD đã dùng lúc mã hóa để tag được xác minh.

**7. ChaCha20-Poly1305 có thay thế chữ ký số hay kiểm soát quyền API không?**  
Không. Tag bảo vệ thông điệp trong phạm vi chủ thể chia sẻ key. Chữ ký số và kiểm tra quyền nghiệp vụ giải quyết những nhu cầu khác.

## Ghi nhớ

**ChaCha20-Poly1305 là AEAD dùng ChaCha20 để mã hóa và Poly1305 để xác thực bản mã cùng AAD.** Biến thể IETF thường dùng **key 256 bit, nonce 96 bit, tag 128 bit**. Để an toàn, phải **không mã hóa hai thông điệp bằng cùng cặp (key, nonce)**, xác minh tag trước khi chấp nhận plaintext, thiết kế AAD đáng tin cậy, kiểm soát replay theo nhu cầu và quản lý khóa xuyên suốt vòng đời. Kết hợp ChaCha20-Poly1305 với DEK/KEK, KMS/HSM, phân quyền tối thiểu, kiểm toán, rotation, thu hồi và khôi phục giúp kiến trúc bảo vệ dữ liệu an toàn hơn cả ở lớp mật mã lẫn vận hành.
