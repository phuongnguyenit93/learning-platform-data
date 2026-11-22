# 6.7 GCMParameterSpec, độ dài tag và yêu cầu không lặp IV dưới cùng một khóa

Trong Java, khi dùng `Cipher.getInstance("AES/GCM/NoPadding")`, ta cần nắm vững hai tham số mà `GCMParameterSpec` biểu diễn: **IV/nonce** dùng cho lần mã hóa và **độ dài authentication tag** dùng để kiểm tra tính toàn vẹn/xác thực của kết quả. Một lời gọi API đúng cú pháp vẫn có thể tạo ra hệ thống không an toàn nếu **tái sử dụng IV với cùng một khóa AES**.

Sau bài này, bạn có thể:
- Giải thích cơ chế AES-GCM và vai trò của IV/nonce, tag, AAD.
- Phân biệt **tag length tính bằng bit** với **IV length tính bằng byte** trong `GCMParameterSpec`.
- Chọn độ dài tag phù hợp, hiểu giới hạn của chuẩn NIST và provider Java.
- Sinh, lưu và khôi phục IV cho từng bản mã; duy trì quy tắc **không lặp cặp (key, IV)** ở quy mô nhiều lần mã hóa, nhiều tiến trình và nhiều node.
- Viết Java 17+ encrypt/decrypt với `GCMParameterSpec`, xử lý `AEADBadTagException` và đối chiếu kết quả với test vector.

## 1. GCM là gì và bốn dữ liệu cần phân biệt

**GCM (Galois/Counter Mode)** là chế độ mã hóa đối xứng có xác thực (**AEAD**, Authenticated Encryption with Associated Data). Kết quả gồm phần dữ liệu đã mã hóa (**ciphertext**) và **authentication tag**. Khi giải mã, tag được kiểm tra để phát hiện việc ciphertext, AAD hoặc thông số mật mã không khớp. Không chấp nhận plaintext nếu xác thực thất bại.

| Thành phần | Vai trò | Có cần giữ bí mật? | Khi giải mã |
| --- | --- | --- | --- |
| **AES key** (`SecretKey`) | Khóa bí mật được dùng để mã hóa và tính tag. | **Có.** | Phải sử dụng đúng khóa. Quản lý trong keystore/KMS hoặc hệ thống quản lý bí mật phù hợp. |
| **IV/nonce** | Xác định một lần mã hóa với khóa cụ thể; tham gia tính trạng thái GCM. | **Không** với AES-GCM thông thường. | Phải có **đúng IV** đã dùng khi mã hóa. |
| **Plaintext / ciphertext** | Dữ liệu cần giữ kín và bản mã. | Plaintext cần bảo vệ; ciphertext có thể lưu/truyền. | Chỉ dùng plaintext sau khi xác thực hoàn tất. |
| **Authentication tag** (`T`) | Giá trị kiểm tra tính toàn vẹn/xác thực, thường gắn ở cuối ciphertext. | Không phải khóa bí mật. | Thiếu hoặc tag sai phải khiến giải mã thất bại. |
| **AAD** (Additional Authenticated Data) | Metadata được **xác thực nhưng không mã hóa**. | Không mặc định. | Phải cung cấp đúng byte AAD đã dùng khi mã hóa. |

Các thuật ngữ IV và nonce cùng trỏ đến tham số trong trường hợp AES-GCM này: **không cần tạo hai mảng riêng** chỉ vì tài liệu dùng hai tên. IV mang tính không bí mật nhưng có yêu cầu **duy nhất với từng khóa**.

Sơ đồ một bản ghi:

~~~text
Khóa K (bí mật) ─────────────────────────┐
IV N (mới với K) ───────────────────────┤
AAD (metadata xác thực) ────────────────┤ AES-GCM encrypt
Plaintext P ────────────────────────────┘
                                           |
                                           v
                     Ciphertext C + authentication tag T

Lưu/truyền: {version, keyId, N, C, T, AAD/context}
Giải mã: lấy đúng K, N, AAD, C và T -> verify tag -> plaintext
~~~

**AAD không phải ciphertext**, nên không được kỳ vọng AAD được mã hóa. Ví dụ có thể đưa `recordType` hoặc `tenantId` vào AAD khi muốn phát hiện sửa metadata. Nếu hệ thống mã hóa nội dung cho tenant A nhưng bỏ qua định danh tenant trong AAD/context, bản mã có thể bị dùng nhầm ngữ cảnh.

## 2. `GCMParameterSpec` thực sự lưu những gì?

Lớp `javax.crypto.spec.GCMParameterSpec` thực hiện `AlgorithmParameterSpec` và chứa **hai giá trị**:

- `tLen`: độ dài **authentication tag**, đơn vị **bit**.
- `IV`: dãy byte của initialization vector, được lưu như mảng byte, độ dài do `iv.length` xác định.

Các API quan trọng:

~~~java
// IV dài 12 byte; tag dài 128 bit (16 byte):
byte[] iv = new byte[12]; // CHỈ là ví dụ về độ dài; không dùng IV toàn 0 để mã hóa thực!
GCMParameterSpec spec = new GCMParameterSpec(128, iv);

// Lấy thông số:
int tagBits = spec.getTLen();   // 128
byte[] ivCopy = spec.getIV();   // mảng mới, dài 12 byte
~~~

Đây là **mảnh minh họa API**, không phải chương trình mã hóa độc lập. Chương trình chạy đầy đủ sử dụng IV an toàn nằm ở mục 6.

Hai constructor chính:

| API | Ý nghĩa |
| --- | --- |
| `new GCMParameterSpec(int tLen, byte[] src)` | Sao chép toàn bộ `src` làm IV và lưu độ dài tag theo **bit**. |
| `new GCMParameterSpec(int tLen, byte[] src, int offset, int len)` | Sao chép `len` byte bắt đầu tại `offset` từ `src` để làm IV; không tự chọn IV ngẫu nhiên. |
| `spec.getTLen()` | Trả về độ dài tag, **bit**, không phải byte. |
| `spec.getIV()` | Trả về **một mảng mới** mỗi lần gọi; thay đổi mảng trả về không làm đổi IV đã lưu trong spec. |

Constructor sao chép mảng IV để tránh việc người gọi sửa byte nguồn rồi âm thầm làm thay đổi tham số. Nhưng `GCMParameterSpec` **không tự sinh IV**, **không quản lý lịch sử IV**, cũng **không bảo đảm IV không trùng dưới cùng khóa**. Trách nhiệm cấp IV an toàn thuộc về chương trình/giao thức.

**Đừng nhầm đơn vị:**

~~~text
int IV_BYTES = 12;       // 12 byte = 96 bit (độ dài IV phổ biến)
int TAG_BITS = 128;      // 128 bit = 16 byte (độ dài tag phổ biến)

new GCMParameterSpec(TAG_BITS, iv);   // ĐÚNG nếu iv dài 12 byte
new GCMParameterSpec(16, iv);         // SAI ý nghĩa: 16 bit, không phải 16 byte
new GCMParameterSpec(IV_BYTES, iv);   // SAI ý nghĩa: truyền 12 làm tag length
~~~

Java API chỉ kiểm tra một số tính hợp lệ cơ bản của tham số khi tạo `GCMParameterSpec`. **Provider thực thi `Cipher.init` mới quyết định giá trị tag/IV cụ thể có được hỗ trợ hay không**. Do đó không coi việc constructor chạy được là bằng chứng cấu hình GCM hợp lệ và an toàn.

## 3. Độ dài authentication tag: 128 bit nghĩa là gì?

GCM tạo authentication tag `T`, thường chọn **128 bit (16 byte)**. Tag cho phép bên giải mã phát hiện sửa bản mã, metadata AAD hoặc sử dụng khóa/IV không khớp, với xác suất giả mạo thành công phụ thuộc cả độ dài tag lẫn giới hạn sử dụng GCM.

Theo NIST SP 800-38D, các độ dài tag thông thường được định nghĩa là **128, 120, 112, 104 hoặc 96 bit**. **64 hoặc 32 bit** chỉ được phép trong một số ứng dụng có ràng buộc đặc biệt về độ dài dữ liệu, lượng thông điệp và vòng đời khóa; không chọn chúng cho hệ thống thông thường.

| `tLen` (bit) | Độ dài tag (byte) | Định hướng |
| --- | --- | --- |
| **128** | **16** | Lựa chọn thực hành ưu tiên trong ví dụ và phần lớn ứng dụng mới. |
| 120 | 15 | Theo chuẩn GCM, nhưng phải kiểm tra provider/giao thức và nhu cầu tương thích. |
| 112 | 14 | Tương tự; tag ngắn hơn cần phân tích giới hạn bảo mật. |
| 104 | 13 | Tương tự; không tự ý rút ngắn để tiết kiệm vài byte. |
| 96 | 12 | Theo chuẩn, bảo đảm xác thực thấp hơn tag 128 bit; dùng khi giao thức quy định và đánh giá đúng giới hạn. |
| 64 hoặc 32 | 8 hoặc 4 | **Trường hợp đặc biệt theo NIST**, kèm ràng buộc nghiêm ngặt; tránh dùng nếu không có thiết kế được duyệt. |

Chú ý:
1. `tLen` là thông số **tag**, không phải số bit của khóa AES. Khóa có thể là AES-128/192/256; `GCMParameterSpec(128, iv)` không quyết định độ dài key.
2. Tag 128 bit **không đồng nghĩa** IV 128 bit. Lựa chọn phổ biến là **IV 96 bit (12 byte)** + **tag 128 bit (16 byte)**.
3. **Tag ngắn hơn làm tăng khả năng giả mạo khi đối thủ thử nhiều lần**, đồng thời các giới hạn an toàn/khối lượng dữ liệu có thể chặt hơn. Không rút ngắn tag để cố vừa một payload nhỏ mà không thay giao thức.
4. NIST yêu cầu một độ dài tag cố định, được hỗ trợ, gắn với một khóa trong cấu hình GCM; không thay độ dài tag tùy tiện giữa các thông điệp cùng khóa.
5. Không phải provider Java nào cũng hỗ trợ mọi `tLen` chuẩn. Khi `Cipher.init` gặp thông số không được hỗ trợ có thể ném `InvalidAlgorithmParameterException`. Ví dụ bên dưới chủ ý dùng 128 bit để tránh khác biệt không cần thiết.
6. Không dùng giá trị `256` làm tag length với ý nghĩ “bảo mật gấp đôi”: GCM chuẩn không có tag 256 bit.

### Tag xuất hiện ở đâu trong Java?

Với `Cipher.getInstance("AES/GCM/NoPadding")` và `TAG_BITS=128`, Java `doFinal(plaintext)` tạo **ciphertext kèm tag**, về mặt biểu diễn có thể xem là:

~~~text
ciphertextAndTag = ciphertext || tag
len(ciphertextAndTag) = len(plaintext) + 16 byte

Ví dụ plaintext 8 byte:
  8 byte ciphertext + 16 byte tag = 24 byte ciphertextAndTag

Nếu envelope có IV 12 byte:
  IV(12) || ciphertextAndTag(24) = 36 byte
~~~

`NoPadding` là tên transformation đúng cho GCM, **không có nghĩa GCM bỏ authentication tag**. Tag nằm trong kết quả `doFinal`, không tự động nằm ở `GCMParameterSpec`. `GCMParameterSpec` chỉ chứa **tham số kỳ vọng** gồm tLen và IV, chứ không giữ tag đã sinh.

Nếu phải tương tác với thư viện/protocol tách trường ciphertext và tag riêng, hãy xác định rõ **độ dài tag bằng byte**, tách/ghép đúng thứ tự và dùng một định dạng được version hóa. Không nhầm 16 byte tag với 12 byte IV.

## 4. Quy tắc sống còn: không lặp IV dưới cùng khóa

**Bất biến của AES-GCM: với mỗi khóa K, mỗi lần mã hóa phải sử dụng một IV/nonce N chưa từng sử dụng với K.** Nói cách khác, cặp **(K, N)** phải là duy nhất trong toàn bộ vòng đời sử dụng khóa cho encryption.

### 4.1. Điều gì xảy ra nếu tái sử dụng?

GCM dùng cách mã hóa dựa trên counter cùng cơ chế tính authentication tag. Nếu cùng `K` và `N` được dùng cho hai plaintext khác nhau, phần keystream có thể lặp. Trên cùng vị trí byte, quan hệ có dạng:

~~~text
C1 = P1 XOR stream(K, N)
C2 = P2 XOR stream(K, N)

C1 XOR C2 = P1 XOR P2   (ở những phần cùng vị trí)
~~~

Kẻ tấn công có thể suy ra quan hệ giữa plaintext và khai thác điểm yếu xác thực; **reusing IV còn dẫn đến nguy cơ giả mạo tag**, không chỉ lộ thông tin. Đây không phải lỗi có thể “chữa” bằng việc tạo tag dài 128 bit, thêm AAD hoặc thay plaintext. Nếu cùng (K, N) đã dùng cho encryption thì tính an toàn thiết kế đã bị vi phạm.

**Phân biệt các trường hợp:**

| Trường hợp | Có hợp lệ theo quy tắc IV? |
| --- | --- |
| Cùng key, **IV mới** cho từng encrypt | Có thể hợp lệ, nếu thực sự bảo đảm không trùng và các điều kiện khác của GCM được đáp ứng. |
| Cùng key, cùng IV cho **hai lần encrypt** khác nhau | **Không hợp lệ**, kể cả plaintext/AAD khác. |
| Cùng key, cùng IV dùng để **decrypt bản mã vừa tạo** | **Bắt buộc**, vì decrypt phải dùng đúng IV của ciphertext; đây không phải encrypt thêm lần nữa. |
| Đổi sang key mới, IV trùng một giá trị của key cũ | Quy tắc duy nhất áp dụng theo cặp (key, IV); cần quản lý key đúng, không giả định một cấu hình đổi key đã thành công nếu chưa xác minh. |
| Hai node cùng dùng K và cùng chọn N | **Không hợp lệ**, kể cả node và JVM khác nhau. |
| Restart làm bộ đếm nonce quay về 0 trong khi dùng lại key | **Không hợp lệ**. |
| Tạo `new GCMParameterSpec(128, oldIV)` cho lần encrypt mới | Vẫn **không hợp lệ** nếu oldIV đã được dùng với cùng key; đối tượng spec mới không khiến IV mới. |

### 4.2. Tại sao IV 96 bit (12 byte) thường được chọn?

GCM xử lý IV **96 bit** theo đường đi đơn giản và hiệu quả: giá trị đầu của counter được tạo từ IV nối với hằng số cuối theo đặc tả. Khi IV dài khác 96 bit, GCM phải xử lý IV qua phép GHASH trước khi xây dựng trạng thái counter; một số provider có thể hỗ trợ nhưng không nên xem độ dài tùy ý là cấu hình mặc định.

96 bit ở đây là **độ dài IV**, không phải độ dài tag. Ví dụ dùng **nonce 12 byte và tag 16 byte** không có mâu thuẫn.

IV không cần bí mật. Có thể lưu công khai ngay trước ciphertext; nhưng phải dùng đúng IV khi giải mã, và **không được tái sử dụng cho một phép mã hóa mới dưới cùng khóa**.

### 4.3. Sinh IV ngẫu nhiên không phải bảo đảm tuyệt đối

Đối với mỗi lần encrypt có thể tạo 12 byte bằng `SecureRandom.nextBytes`:

~~~java
byte[] iv = new byte[12];
new java.security.SecureRandom().nextBytes(iv);
GCMParameterSpec spec = new GCMParameterSpec(128, iv);
~~~

Đây là **mảnh minh họa**; thực tế nên quản lý đối tượng CSPRNG và vòng đời khóa theo thiết kế. CSPRNG tạo byte khó dự đoán; với IV ngẫu nhiên, **xác suất trùng là nhỏ nhưng không bằng 0**. Với không gian 96 bit, xác suất đụng sau nhiều lần sinh tăng theo hiệu ứng birthday (xấp xỉ tăng theo bình phương số lần dùng). NIST quy định các giới hạn số lần invocation dưới cùng key và các cách xây dựng IV tương ứng.

Đối với hệ thống lưu lượng thấp với chính sách xoay khóa thích hợp, IV 96 bit ngẫu nhiên là một phương án thông dụng. Đối với hệ thống nhiều node, lưu lượng lớn hoặc cần **bảo đảm không trùng mạnh hơn xác suất**, nên dùng thiết kế cấp nonce có trạng thái/bộ đếm với cách phân vùng thích hợp.

Không tự chọn một ngưỡng “an toàn” vô hạn cho `SecureRandom`. Giới hạn thực tế cần dựa trên đặc tả GCM, mức chấp nhận rủi ro, kích thước dữ liệu, số bản mã, kiến trúc và chính sách quản lý khóa.

### 4.4. Bộ đếm nonce có thể dùng, nhưng phải quản lý toàn hệ thống

Một chiến lược khác là cấp mỗi encryption một **giá trị duy nhất** từ bộ đếm hoặc không gian nonce phân vùng:

~~~text
96-bit IV = prefix riêng của key/node || counter tăng một chiều

Node A -> prefixA || 000001, prefixA || 000002, ...
Node B -> prefixB || 000001, prefixB || 000002, ...
                   ^ prefixA khác prefixB và được cấp không trùng
~~~

Sơ đồ chỉ minh họa ý tưởng, **không quy định một cách chia bit cụ thể cho mọi hệ thống**. Muốn an toàn thực sự cần xác định:

- Ai cấp prefix/namespace và làm sao biết hai node không nhận cùng prefix.
- Làm sao lưu trạng thái counter **bền vững**, không lặp lại sau crash, restore backup, scale-out hoặc rollback deployment.
- Làm sao xử lý nhiều thread/request cùng lúc để không cấp một IV hai lần.
- Giới hạn tối đa của counter và việc thay key trước khi bộ đếm quay vòng.
- Vòng đời key, version/key ID và cơ chế rotate phối hợp cùng thuật toán sinh IV.
- Chính sách của chuẩn/giao thức: không tự phối trộn cơ chế IV random và deterministic với cùng key khi không được đặc tả/đánh giá.

**Không dùng timestamp trực tiếp làm IV vì nghĩ thời gian luôn tăng**: độ phân giải đồng hồ, điều chỉnh thời gian, nhiều node và restart có thể gây trùng.

### 4.5. `Cipher` không thay hệ thống quản lý uniqueness

Một số provider có thể phát hiện việc **cùng một đối tượng `Cipher`** được khởi tạo lại cho encryption bằng một cặp key/IV vừa sử dụng. Đây không phải cơ chế chống reuse trên toàn hệ thống. Một đối tượng `Cipher` mới, JVM mới hoặc node khác không có danh sách toàn cục của mọi IV mà khóa đã từng dùng. **Không dựa vào exception của provider như lớp bảo vệ cuối cùng.**

## 5. Chu trình đúng của một phép mã hóa/giải mã AES-GCM

### 5.1. Encryption

1. Lấy đúng khóa AES `K` (và quyền sử dụng khóa) từ hệ thống quản lý khóa.
2. Cấp IV **mới với K** theo chiến lược đã chọn; ví dụ 12 byte từ CSPRNG dưới mức tải được thiết kế.
3. Tạo `GCMParameterSpec(128, iv)`; gọi `Cipher.getInstance("AES/GCM/NoPadding")`.
4. `cipher.init(Cipher.ENCRYPT_MODE, key, spec)`.
5. Nếu có AAD, gọi `cipher.updateAAD(aad)` **trước** bất kỳ `update(...)` hoặc `doFinal(...)` nào xử lý plaintext.
6. Gọi `doFinal(plaintext)` nhận ciphertext và tag; lưu/truyền cùng IV, version, key ID, AAD/context được định nghĩa trong giao thức.

### 5.2. Decryption

1. Kiểm tra version, kích thước tối thiểu, kích thước IV và tag theo định dạng **đã thỏa thuận**; không để attacker chọn tag length tùy ý.
2. Lấy đúng khóa K bằng key ID/phiên bản tin cậy; đọc IV đã đi kèm ciphertext.
3. `cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv))`.
4. Cung cấp **chính xác cùng byte AAD** (nếu có) trước xử lý ciphertext.
5. `doFinal(ciphertextAndTag)`: nếu xác thực thất bại, xử lý `AEADBadTagException` và **từ chối dữ liệu**. Không dùng plaintext chưa xác thực.

**Không phải sinh IV mới lúc decrypt.** IV mới chỉ cần cho **lần encrypt mới** với cùng key; decrypt phải dùng IV đã lưu của bản mã ban đầu.

### 5.3. AAD và thứ tự gọi API

`updateAAD` dành cho metadata cần xác thực nhưng không giấu. Ví dụ encrypt dữ liệu thuộc record `"record:v1"`: phải truyền đúng byte `"record:v1"` khi decrypt, nếu truyền `"record:v2"` thì tag không hợp lệ. Trong Java JCE, mọi AAD của GCM phải được cung cấp **trước khi bắt đầu xử lý dữ liệu** bằng `update`/`doFinal`.

GCM xác thực dữ liệu **sau khi nhận đủ input và tag**. Nếu dùng chế độ streaming hoặc provider trả ra dữ liệu trước khi xác minh, ứng dụng không được thực thi, hiển thị hoặc phát tán plaintext chưa được xác thực; chỉ chấp nhận nó sau khi `doFinal` thành công.

## 6. Java 17+: chương trình encrypt/decrypt hoàn chỉnh

Ví dụ tạo khóa AES-128 chỉ trong bộ nhớ, sử dụng IV 12 byte mới và tag 128 bit, lưu envelope dạng `IV || ciphertext || tag`. Chương trình dùng `"xin chao"` (8 byte UTF-8) để kết quả về độ dài là cố định dù IV ngẫu nhiên mỗi lần.

**Tệp: `GcmRecordDemo.java`**

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmRecordDemo {
    static final int IV_BYTES = 12;
    static final int TAG_BITS = 128;
    static final int TAG_BYTES = TAG_BITS / 8;
    static final SecureRandom RNG = new SecureRandom();

    static byte[] seal(SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        RNG.nextBytes(iv);

        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        enc.updateAAD(aad);
        byte[] ciphertextAndTag = enc.doFinal(plaintext);

        return ByteBuffer.allocate(iv.length + ciphertextAndTag.length)
                .put(iv).put(ciphertextAndTag).array();
    }

    static byte[] open(SecretKey key, byte[] envelope, byte[] aad)
            throws GeneralSecurityException {
        if (envelope.length < IV_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Envelope too short");
        }

        byte[] iv = Arrays.copyOfRange(envelope, 0, IV_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                envelope, IV_BYTES, envelope.length);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        dec.updateAAD(aad);
        return dec.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator keys = KeyGenerator.getInstance("AES");
        keys.init(128);
        SecretKey key = keys.generateKey();

        byte[] message = "xin chao".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] envelope = seal(key, message, aad);

        System.out.println("Tag bits: " + TAG_BITS);
        System.out.println("IV bytes: " + IV_BYTES);
        System.out.println("Envelope bytes: " + envelope.length);
        System.out.println("Recovered: " + new String(
                open(key, envelope, aad), StandardCharsets.UTF_8));

        byte[] tampered = envelope.clone();
        tampered[tampered.length - 1] ^= 1;
        try {
            open(key, tampered, aad);
            throw new AssertionError("Tampered record was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered record rejected: true");
        }

        try {
            open(key, envelope, "record:v2".getBytes(StandardCharsets.UTF_8));
            throw new AssertionError("Wrong AAD was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD rejected: true");
        }
    }
}
~~~

Chạy bằng Java 17+ ở thư mục chứa tệp:

~~~bash
javac GcmRecordDemo.java
java GcmRecordDemo
~~~

Stdout kiểm chứng (không in IV ngẫu nhiên):

~~~text
Tag bits: 128
IV bytes: 12
Envelope bytes: 36
Recovered: xin chao
Tampered record rejected: true
Wrong AAD rejected: true
~~~

**Giải thích từng phần:**

- `keys.init(128)` là độ dài khóa AES **128 bit**; `TAG_BITS=128` là độ dài **tag 128 bit**; `IV_BYTES=12` là **IV 96 bit**. Ba tham số mang ý nghĩa khác nhau.
- `seal` luôn sinh IV mới trước một lần encrypt. Không dùng một biến IV toàn cục cố định, không dùng `new byte[12]` làm IV thực.
- `enc.updateAAD(aad)` xác thực metadata không mã hóa. `enc.doFinal(message)` trả **8 byte ciphertext + 16 byte tag = 24 byte**. Envelope thêm **12 byte IV**, tổng **36 byte**.
- `open` lấy IV từ envelope; không sinh IV mới. Đồng thời nó kiểm tra độ dài tối thiểu 12 + 16 byte trước khi cắt mảng.
- Đảo một bit ở cuối envelope (trong tag) dẫn đến `AEADBadTagException`; AAD khác cũng bị từ chối. Đó là hành vi mong muốn; không xử lý ngoại lệ bằng cách trả về dữ liệu chưa xác thực.
- Đây là **ví dụ API trên một process**, chưa có giới hạn lượng bản mã, rotation, key ID hay phối hợp nonce xuyên node. Không triển khai nguyên xi như dịch vụ mã hóa nhiều node ở quy mô lớn.

Mỗi lời gọi `seal` tạo một `Cipher` mới. `Cipher` là đối tượng có trạng thái, không nên chia sẻ giữa các luồng để encrypt/decrypt cùng lúc. `SecureRandom` có thể được quản lý như một nguồn CSPRNG dùng chung theo hợp đồng API; sự phù hợp về an toàn nonce ở quy mô hệ thống vẫn phải do ứng dụng bảo đảm.

## 7. Java 17+: kiểm tra tag, IV copy và test vector cố định

Ví dụ thứ hai **chỉ phục vụ kiểm thử** dùng khóa AES-128 toàn byte 0, IV 96 bit toàn byte 0 và plaintext 16 byte toàn byte 0. Đây là **known-answer test vector** được dùng trong tài liệu/kiểm thử AES-GCM; **không dùng key/IV cố định này để encrypt dữ liệu thật**.

Bài test chứng minh:
- `getTLen()` trả **bit**, còn IV lấy ra là **mảng byte**.
- Constructor và `getIV()` sao chép IV để tránh thay đổi ngầm.
- Với plaintext 16 byte, `doFinal` trả 16 byte ciphertext + 16 byte tag = 32 byte.
- Ciphertext và tag đúng giá trị chuẩn dự kiến.

**Tệp: `GcmKnownAnswerDemo.java`**

~~~java
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class GcmKnownAnswerDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] key = new byte[16];
        byte[] iv = new byte[12];
        byte[] plaintext = new byte[16];

        GCMParameterSpec params = new GCMParameterSpec(128, iv);
        iv[0] = 1; // Mảng nguồn đổi, IV trong params không đổi.
        byte[] ivCopy = params.getIV();
        ivCopy[1] = 1; // Mảng trả về đổi, params vẫn giữ IV ban đầu.

        System.out.println("IV is copied: "
                + Arrays.equals(params.getIV(), new byte[12]));
        System.out.println("Tag bits: " + params.getTLen());
        System.out.println("Tag bytes: " + params.getTLen() / 8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), params);
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        String expected = "0388dace60b6a392f328c2b971b2fe78"
                        + "ab6e47d42cec13bdf53a67b21257bddf";
        System.out.println("Ciphertext+tag bytes: " + ciphertextAndTag.length);
        System.out.println("Known vector matches: " + expected.equals(
                HexFormat.of().formatHex(ciphertextAndTag)));

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(key, "AES"), params);
        System.out.println("Recovered zero block: "
                + Arrays.equals(plaintext, decrypt.doFinal(ciphertextAndTag)));
    }
}
~~~

~~~bash
javac GcmKnownAnswerDemo.java
java GcmKnownAnswerDemo
~~~

Stdout:

~~~text
IV is copied: true
Tag bits: 128
Tag bytes: 16
Ciphertext+tag bytes: 32
Known vector matches: true
Recovered zero block: true
~~~

Chú ý không sao chép ý tưởng `new byte[12]` làm IV cố định từ **test vector** sang production. Chương trình trên **chỉ mã hóa một lần với một key/IV kiểm thử**, sau đó decrypt cùng ciphertext bằng đúng thông số.

## 8. Thiết kế định dạng bản mã và quản lý khóa/IV

Một hệ thống thực thường cần **envelope có version** để xác định các tham số được hỗ trợ. Ví dụ định dạng logic:

~~~text
Record {
  version: 1,
  algorithm: "AES/GCM/NoPadding",    // cố định theo version
  keyId: "key-2026-10",             // tra đúng khóa trong KMS
  tagBits: 128,                    // cố định/được kiểm tra theo version
  iv: 12-byte nonce,
  aadContext: metadata đã ràng buộc với record,
  ciphertextAndTag: ciphertext || 16-byte authentication tag
}
~~~

Đây là mô hình thiết kế, **không phải JSON chứa key**; trường `keyId` chỉ là định danh. Nếu encode byte bằng Base64URL/hex, phải decode/validate về đúng số byte. Không tin cậy giá trị do người gửi tự khai như `tagBits=32` để lách chính sách; thông số hợp lệ phải xuất phát từ định dạng/giao thức đã chọn. Giá trị `keyId` và metadata cần được ràng buộc/xác thực phù hợp, ví dụ nằm trong AAD của record.

Nếu dùng `Cipher.init(Cipher.ENCRYPT_MODE, key)` mà **để provider tự tạo IV**, vẫn phải lấy IV sau init (ví dụ `cipher.getIV()` hoặc `cipher.getParameters().getParameterSpec(GCMParameterSpec.class)` nếu được hỗ trợ), xác minh độ dài/tag theo giao thức và lưu lại cùng kết quả. Không giả định decrypt tự suy ra IV từ ciphertext hoặc Java tự lưu nonce trên disk.

Các hệ thống thực tế nên có:

1. **Key ID và rotation:** biết ciphertext được mã hóa bằng khóa nào; quản lý khóa trước và sau rotation.
2. **Quy tắc cấp IV/nonce:** cấp phát mới, không lặp trong phạm vi key, bảo vệ trước restart/rollback/multi-node.
3. **Giới hạn sử dụng mỗi khóa:** lượng encryption, kích thước dữ liệu, độ dài tag, thuật toán và giới hạn của NIST/protocol.
4. **Metadata và AAD:** các trường liên quan đến ngữ cảnh (tenant, loại bản ghi, version, quyền truy cập) được xác thực nhất quán.
5. **Kiểm tra đầu vào:** giới hạn kích thước trước khi cấp bộ nhớ, validate IV/tag và phiên bản; tránh dữ liệu hỏng làm cạn bộ nhớ.
6. **Xử lý lỗi:** log thông tin an toàn về bản ghi/loại lỗi; không log khóa, plaintext nhạy cảm hay ghi nhận ciphertext giả mạo là đã giải mã.
7. **Chống rollback/replay theo nghiệp vụ:** AEAD xác thực bản mã nhưng **không tự ngăn việc phát lại một bản mã cũ vẫn hợp lệ**. Nếu cần freshness/thứ tự phiên bản, phải có state/version/sequence kiểm chứng ở tầng ứng dụng.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả / nguyên nhân | Cách đúng |
| --- | --- | --- |
| `new GCMParameterSpec(16, iv)` vì muốn tag 16 byte | `tLen` tính bằng **bit**; truyền 16 có thể bị provider từ chối và sai bảo mật. | `new GCMParameterSpec(128, iv)`. |
| Cho rằng IV 12 byte tức tag 12 byte | Hai tham số độc lập. | IV 12 byte, tag 16 byte là cấu hình thông dụng. |
| `new GCMParameterSpec(128, constantIV)` cho mọi encrypt | Tái sử dụng (K, IV) khi dùng lại key. | Cấp IV mới thực sự cho **mỗi encryption**. |
| Dùng cùng key/IV nhưng AAD hoặc plaintext khác | Vẫn vi phạm uniqueness; tag mới không cứu thiết kế. | Cặp (key, IV) không bao giờ lặp cho encryption. |
| Sinh random 96 bit rồi cho rằng “không thể trùng” | Random có xác suất va chạm, tăng theo lượng bản mã. | Giới hạn invocation/rotation hoặc cấu trúc cấp IV bảo đảm uniqueness. |
| Bộ đếm reset về 0 khi service restart | Có thể phát sinh cặp (key, IV) cũ. | Counter bền vững, dự phòng rollback, prefix/node được cấp không trùng. |
| Tự cho rằng provider phát hiện mọi nonce reuse | Provider không có registry toàn hệ thống. | Bảo đảm ở tầng giao thức/ứng dụng. |
| Không lưu IV rồi tạo IV mới khi decrypt | Không xác thực/giải mã được ciphertext. | Lưu IV công khai cùng ciphertext; dùng đúng IV cũ khi decrypt. |
| `updateAAD` sau `update`/`doFinal` | Trái thứ tự GCM; có thể ném `IllegalStateException`. | AAD **trước** dữ liệu ciphertext/plaintext. |
| Bỏ tag hoặc tách nhầm tag khỏi ciphertext | Xác thực thất bại hoặc sai định dạng. | Cấu hình tLen cố định; truyền đúng ciphertext + tag. |
| Bắt `AEADBadTagException` rồi trả plaintext “thử được” | Chấp nhận dữ liệu chưa được xác thực. | Từ chối bản mã và báo lỗi có kiểm soát. |
| Nhìn thấy `GCMParameterSpec` được tạo là nghĩ cấu hình được hỗ trợ | Constructor không kiểm tra đầy đủ mọi hạn chế provider. | Kiểm tra tại `Cipher.init` và chạy thử trên provider môi trường đích. |
| Giảm tag xuống 32/64 bit để tiết kiệm băng thông | Giảm an toàn, cần ràng buộc đặc biệt theo NIST. | Ưu tiên tag 128 bit khi không có yêu cầu đã đánh giá riêng. |
| Dùng `Cipher.getInstance("AES")` không chỉ định mode | Mode/padding phụ thuộc provider, không nhất thiết là GCM. | Dùng `"AES/GCM/NoPadding"` tường minh. |
| Coi IV bí mật hơn khóa hoặc log plaintext/key | Sai ưu tiên bảo vệ. | Giữ kín khóa và plaintext; IV thường công khai nhưng phải đúng và unique. |
| Dùng cùng `Cipher` từ nhiều thread | `Cipher` có trạng thái và không được xem là thread-safe. | Tạo instance riêng cho mỗi thao tác. |
| Chỉ có GCM rồi tưởng đã chống replay | Ciphertext hợp lệ cũ có thể được phát lại nguyên vẹn. | Thêm sequence/version, freshness và policy cấp ứng dụng khi cần. |

## 10. Tình huống chẩn đoán

**Tình huống A: `InvalidAlgorithmParameterException` khi `init`.** Trước tiên kiểm tra `spec.getTLen()` là 128 **bit**, `spec.getIV().length` là 12 **byte** và provider có hỗ trợ thông số không. Phân biệt lỗi này với `AEADBadTagException` khi xác thực decrypt.

**Tình huống B: Encrypt chạy tốt, decrypt luôn `AEADBadTagException`.** Kiểm tra cùng khóa đúng version, IV đúng 12 byte gốc, đúng cách ghép ciphertext||tag, AAD byte-for-byte giống nhau, cùng tag length. Không thử “bỏ kiểm tra tag” để làm cho decrypt hoạt động.

**Tình huống C: Mỗi service đều tạo `SecureRandom` và mỗi request sinh 12 byte IV.** Cách này có xác suất va chạm rất thấp ở tải phù hợp, nhưng không cho bằng chứng tuyệt đối về uniqueness xuyên service; phải đánh giá số lần encrypt trên cùng key và chính sách xoay khóa.

**Tình huống D: Hai node dùng cùng key và cùng counter tăng từ 0.** Đây là **lỗi chắc chắn**: khi cả hai cùng cấp nonce 0, 1, 2... sẽ tái sử dụng (K, IV). Cần phân vùng nonce và cấp prefix/namespace không trùng hoặc sử dụng dịch vụ điều phối counter.

**Tình huống E: Tag 128 bit nhưng người vận hành đổi tLen xuống 96 để giảm kích thước record.** Giảm 4 byte trên mỗi bản mã không phải thay đổi định dạng vô hại; phải có protocol/version mới, thẩm định giới hạn và kiểm chứng provider. Với cùng khóa, không thay tLen tùy ý.

**Tình huống F: Đổi IV của record lưu trữ và thử decrypt.** GCM không nhận sai IV; xác thực thất bại với xác suất áp đảo. Tình huống này khác với **encrypt lại cùng key + old IV** vốn đã vi phạm giới hạn sử dụng ngay khi thực hiện.

## 11. Câu hỏi tự kiểm tra (kèm đáp án)

**Câu 1.** `new GCMParameterSpec(128, new byte[12])` có nghĩa IV dài 128 bit hay tag dài 128 bit?

**Đáp án:** Tag dài 128 bit (**16 byte**); IV dài 12 byte (**96 bit**). Mảng IV toàn 0 ở ví dụ câu hỏi không được tái sử dụng trong encryption thực.

**Câu 2.** Dùng lại cùng (key, IV) để decrypt chính bản mã đã lưu có vi phạm không?

**Đáp án:** Không. **Decrypt phải dùng đúng key và IV đã encrypt**. Quy tắc không lặp áp dụng cho **các lần encryption mới** dưới cùng key.

**Câu 3.** Có thể sinh nonce bằng bộ đếm 64-bit không?

**Đáp án:** Có thể trong một thiết kế tạo IV 96 bit theo giao thức phù hợp, nếu kết hợp prefix/namespace và quản lý bộ đếm để toàn bộ IV không trùng với cùng khóa, kể cả multi-node/restart. Không lấy con số 64 bit rồi truyền vào mọi API như IV hợp lệ mặc định.

**Câu 4.** Tag 128 bit có ngăn tác hại tái sử dụng IV cùng key không?

**Đáp án:** Không. Reuse khiến GCM có nguy cơ mất cả bí mật và xác thực; tag dài không sửa được lỗi nonce reuse.

**Câu 5.** Sau khi mã hóa GCM, byte `cipher.doFinal` trả ra đã bao gồm tag chưa?

**Đáp án:** Có. `Cipher` AEAD của Java gắn tag vào ciphertext khi encrypt, và xác minh tag khi decrypt. Nếu envelope còn có IV thì phải tự ghép/lưu IV như giao thức quy định.

**Câu 6.** Nếu AAD không cần mã hóa, có thể bỏ qua nó khi decrypt không?

**Đáp án:** Không nếu AAD đã được dùng khi encrypt. Decrypt phải cung cấp đúng AAD byte-for-byte để tag khớp.

**Câu 7.** Constructor `GCMParameterSpec(32, iv)` chạy được có nghĩa tag 32 bit dùng an toàn không?

**Đáp án:** Không. Constructor không đủ để đánh giá chuẩn, provider và chính sách bảo mật. Tag 32 bit chỉ có phạm vi ứng dụng đặc biệt với ràng buộc nghiêm ngặt của NIST và không phù hợp làm cấu hình chung.

**Câu 8.** Nếu một record dùng key K1, IV N; record khác dùng key K2, IV N thì có chắc chắn lặp nonce dưới cùng key không?

**Đáp án:** Không, nếu K1 và K2 thực sự là hai khóa AES khác nhau. Ràng buộc uniqueness là trên cặp (K, IV). Tuy nhiên việc xác định khóa và rotation phải đáng tin cậy.

## 12. Tài liệu tham khảo

- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` theo bit, các constructor, sao chép IV và `getIV()`.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AEAD, thứ tự `updateAAD`, tag kèm ciphertext, yêu cầu không lặp IV.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): tạo byte ngẫu nhiên thích hợp cho bảo mật.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): độ dài tag hợp lệ, xây dựng IV 96 bit và các giới hạn sử dụng GCM.
- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116): AEAD interface và cách nhìn tổng thể về nonce, plaintext, ciphertext và AAD.
