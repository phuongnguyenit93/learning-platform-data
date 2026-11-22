# 6.6 AEAD, AES/GCM/NoPadding và vai trò của authentication tag

Mã hóa dữ liệu nhằm giữ bí mật là **chưa đủ** khi dữ liệu có thể bị kẻ tấn công thay đổi. Một bản mã vẫn có thể bị chỉnh sửa, tráo ngữ cảnh hoặc thay bằng bản mã khác; ứng dụng cần biết có nên **chấp nhận và xử lý** kết quả giải mã hay không. **AEAD (Authenticated Encryption with Associated Data)** kết hợp tính bí mật của mã hóa và phép kiểm tính toàn vẹn/xác thực dựa trên khóa trong một cơ chế được thiết kế thống nhất. Trong Java, biến thể thực tế phổ biến là **`AES/GCM/NoPadding`**.

Bài học giải thích AEAD, AES-GCM, **authentication tag** (thẻ xác thực), nonce/IV, AAD và các quy tắc dùng `Cipher` an toàn. Ví dụ Java 17+ ở phần 8 minh họa dữ liệu thật được khôi phục và các sửa đổi bị từ chối.

## 1. AEAD giải quyết vấn đề gì?

### 1.1. Tính bí mật và tính toàn vẹn là hai yêu cầu khác nhau

Giả sử một ứng dụng gửi bản ghi chuyển khoản giữa các dịch vụ:

~~~text
Bản rõ P = "amount=100;currency=VND"
             |
             v
          Mã hóa
             |
             v
Bản mã C được truyền qua mạng
~~~

Mã hóa cung cấp **confidentiality (tính bí mật)**: người không có khóa phù hợp không đọc được bản rõ. Tuy nhiên, **không phải mọi chế độ mã hóa đều tự xác thực bản mã**. Với một số cách mã hóa không có xác thực, kẻ tấn công có thể sửa byte, cắt ghép hoặc thay thông điệp và khiến bên nhận xử lý dữ liệu sai mà không có bằng chứng mật mã đáng tin rằng bản mã đã bị sửa.

AEAD thêm cơ chế **authentication tag**. Bên nhận chỉ được chấp nhận thông điệp khi xác minh tag thành công với **đúng khóa, nonce, ciphertext và AAD**.

| Thuộc tính | Ý nghĩa trong AEAD |
| --- | --- |
| **Confidentiality** | Giấu bản rõ trước người không có khóa giải mã. |
| **Integrity** | Phát hiện sửa đổi trái phép đối với ciphertext và dữ liệu liên kết được xác thực. |
| **Key-based authenticity** | Bên nhận có bằng chứng thông điệp/tag hợp lệ được tạo bởi bên có quyền dùng khóa bí mật chung (theo giả định khóa chưa lộ). |
| **Associated-data integrity** | Dữ liệu công khai quan trọng vẫn được xác thực dù không mã hóa. |
| **Không tự chống replay** | Kẻ tấn công có thể phát lại nguyên gói hợp lệ nếu giao thức không quản lý số thứ tự, nonce của thông điệp, phiên hoặc request ID. |
| **Không tự chứng minh cá nhân cụ thể** | Nếu nhiều bên cùng biết khóa đối xứng, tag không chỉ ra bên nào đã tạo thông điệp. Không thay được chữ ký số/PKI hoặc xác thực danh tính. |

**Quan trọng:** “Authenticated” trong AEAD là **xác thực mật mã theo khóa**, không tự động có nghĩa “người dùng đã đăng nhập”, “đúng tenant”, “được phép chuyển tiền”, hay “chắc chắn do công ty X phát hành”. Ứng dụng vẫn phải xác thực danh tính, phân quyền và tin cậy nguồn khóa.

### 1.2. Vì sao không chỉ dùng AES ở bất kỳ mode nào?

Tên `AES` chỉ là thuật toán mã khối; bảo mật ứng dụng còn phụ thuộc vào **mode**, cách dùng IV/nonce và cách xác minh tính toàn vẹn:

- **AES-ECB** không cung cấp bảo mật cần thiết cho các mẫu dữ liệu lặp; không nên dùng cho dữ liệu ứng dụng.
- **AES-CBC** với padding chỉ cung cấp mã hóa nếu đứng riêng; cần một cơ chế xác thực đúng cách và xử lý lỗi cẩn thận. Tự ghép kiểm tra padding/giải mã vào giao thức dễ tạo lỗi bảo mật.
- **AES-CTR** bảo vệ bí mật khi nonce đúng, nhưng ciphertext có tính sửa đổi có kiểm soát nếu không xác thực.
- **AES-GCM** là một mode **AEAD**, kết hợp mã hóa kiểu counter với thẻ xác thực GCM; phù hợp cho nhiều nhu cầu mới khi quản lý khóa/nonce đúng.
- **ChaCha20-Poly1305** cũng là AEAD; lựa chọn thuật toán phải theo thư viện, môi trường, tiêu chuẩn và giao thức cụ thể, không tự trộn cấu phần của hai thuật toán.

Nên ưu tiên **primitive AEAD có sẵn trong thư viện đáng tin**; đừng tự thiết kế bộ “AES + hash”, hoặc giả định `SHA-256(ciphertext)` đủ để ngăn giả mạo vì digest không có khóa.

## 2. Mô hình toán học của AES-GCM

AES-GCM nhận các dữ liệu sau:

| Ký hiệu | Tên | Cần bí mật? | Vai trò |
| --- | --- | --- | --- |
| `K` | AES secret key | **Có** | Bí mật của các bên được phép mã hóa/giải mã. |
| `N` | Nonce/IV | **Không**, nhưng phải duy nhất cho mỗi lần mã hóa dưới cùng khóa | Tạo trạng thái mã hóa GCM; sai quy tắc nonce có thể phá nghiêm trọng an toàn. |
| `P` | Plaintext | Có, nếu ứng dụng cần giữ kín | Nội dung muốn mã hóa. |
| `A` | AAD (Additional Authenticated Data) | **Không** cần giữ bí mật | Metadata phải được ràng buộc và xác thực cùng bản mã. |
| `C` | Ciphertext | Không | Bản mã của `P`, dài bằng `P` trong AES-GCM. |
| `T` | Authentication tag | Không | Thẻ xác thực của ciphertext và AAD trong ngữ cảnh khóa và nonce. |

Mô hình khái quát:

~~~text
                    K (khóa bí mật)        N (nonce duy nhất theo K)
                             \              /
                              \            /
P (plaintext) ----------------> AES-GCM Encrypt <------- A (AAD)
                                      |
                                      v
                              C (ciphertext) + T (tag)

K, N, A, C, T ----------------> AES-GCM Decrypt/Verify
                                      |
                            +---------+---------+
                            |                   |
                       tag hợp lệ          tag không hợp lệ
                            |                   |
                       trả P              báo lỗi/từ chối
~~~

Dưới dạng hàm:

~~~text
(C, T) = AEAD_Encrypt(K, N, P, A)
P      = AEAD_Decrypt(K, N, C, T, A), nếu tag hợp lệ
ERROR  = AEAD_Decrypt(K, N, C, T, A), nếu tag không hợp lệ
~~~

**Không có bước “giải mã thành công rồi kiểm tag tùy chọn”.** Việc chấp nhận dữ liệu phải phụ thuộc vào phép xác thực thành công. Khi dùng API streaming hoặc provider có thể tạo output trung gian, **không được sử dụng plaintext chưa xác thực** cho nghiệp vụ, ghi DB, phản hồi API hay gọi hệ thống khác trước khi xác minh xong.

## 3. AES/GCM/NoPadding nghĩa là gì trong JCA/JCE?

Trong Java, gọi:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Chuỗi transformation có ba thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `AES` | Thuật toán mã khối đối xứng Advanced Encryption Standard; khóa thường 128/192/256 bit theo hệ thống. |
| `GCM` | Galois/Counter Mode: mode AEAD cung cấp mã hóa và authentication tag. |
| `NoPadding` | GCM không dùng kiểu padding như PKCS#5/PKCS#7 cho plaintext; dữ liệu không cần bù thành bội số của 16 byte. |

GCM kết hợp cơ chế tạo keystream kiểu **CTR** để mã hóa với phép xác thực dựa trên phép toán trong trường hữu hạn, thường được mô tả qua **GHASH** và khối tag. Người viết Java **không cần tự tính GHASH, counter hoặc tag**; `Cipher` và provider thực hiện phần thuật toán. Tự viết lại để “tối ưu” là dễ mắc lỗi nghiêm trọng.

Trong cách dùng tiêu chuẩn với provider JCE phổ biến:

- Đặt tag 128 bit bằng `new GCMParameterSpec(128, nonce)`.
- Trên **mã hóa**, `Cipher.doFinal(plaintext)` trả **ciphertext nối với tag**; ví dụ bài này lưu chúng liền nhau dưới tên `ciphertextAndTag`.
- Trên **giải mã**, đưa toàn bộ phần **ciphertext + tag** vào `doFinal(...)`; provider kiểm tag và chỉ trả plaintext khi xác thực thành công.
- Vì GCM dùng `NoPadding`, khi plaintext dài `n` byte, phần ciphertext dài `n` byte; tổng `ciphertextAndTag` dài `n + 16` byte khi tag 128 bit.
- **Tag không phải nonce**: nonce chọn cho một lần mã hóa, còn tag là kết quả phép tính xác thực gắn với nội dung và AAD.
- **Tag không phải mã băm SHA-256**: không thể thay bằng `MessageDigest.digest(...)`, cắt vài byte hash rồi gọi là tag.

### 3.1. Authentication tag bảo vệ điều gì?

Giả sử người nhận có đủ `K, N, A, C, T`. Khi một trong các dữ liệu cần xác thực bị thay đổi mà không có khóa đúng để tạo tag hợp lệ, xác minh GCM sẽ thất bại với xác suất rất cao theo giới hạn bảo mật của thuật toán.

Các tình huống minh họa:

| Thay đổi ở phía nhận | Hành vi mong đợi |
| --- | --- |
| **Ciphertext `C` bị đổi một byte** | Tag không khớp; từ chối. |
| **Tag `T` bị đổi một byte** | Tag không khớp; từ chối. |
| **AAD `A` đổi** | Tag không khớp; từ chối; AAD mặc dù không mã hóa vẫn được xác thực. |
| **Nonce `N` đổi** | Giải mã với nonce khác, xác thực không hợp lệ; từ chối. |
| **Dùng sai khóa `K`** | Không thể xác minh tag hợp lệ; từ chối. |
| **Gửi lại nguyên gói hợp lệ, đúng AAD và khóa** | Tag **vẫn hợp lệ**. AEAD không tự biết thông điệp đã dùng trước đó. |

Với `Cipher` của Java, tag sai khi giải mã GCM thường dẫn tới **`AEADBadTagException`** (là loại `BadPaddingException`). Không catch rồi âm thầm tiếp tục dùng dữ liệu. Đừng tự so sánh tag bằng phép `==`, `Arrays.equals` hoặc tự tạo tag — **provider xác minh tag bên trong `doFinal`**.

Tag 128 bit là lựa chọn thông dụng. Tag dài hơn làm việc giả mạo khó hơn trong mô hình thích hợp; không tùy tiện rút ngắn tag hoặc cho hai bên dùng độ dài tag khác nhau. **Tag có độ dài cố định không bảo đảm tuyệt đối không thể giả mạo**, mà cho xác suất/giới hạn an toàn khi tuân thủ các giả định như nonce duy nhất và giới hạn số lần sử dụng khóa.

## 4. Nonce/IV: có thể công khai nhưng không được tái sử dụng với cùng khóa

### 4.1. Quy tắc then chốt

**Đối với AES-GCM, không bao giờ mã hóa hai thông điệp khác nhau với cùng cặp (key, nonce).** Tái sử dụng nonce dưới cùng khóa có thể làm lộ quan hệ giữa các plaintext và dẫn tới giả mạo tag; không thể “sửa” hậu quả chỉ bằng cách lưu tag dài hơn.

Thông thường Java dùng **nonce 96 bit = 12 byte** cho GCM. Nonce **không cần bí mật**, có thể đặt ngay đầu gói tin. Bên giải mã cần nonce giống hệt để xác minh thành công.

~~~text
Khóa K_A:   N_001, N_002, N_003, ...   (mỗi nonce chỉ dùng 1 lần để mã hóa)
Khóa K_B:   có không gian nonce riêng
LỖI:       Encrypt(K_A, N_001, P1) và Encrypt(K_A, N_001, P2)
~~~

**Hai chiến lược nonce phổ biến:**

1. **Nonce ngẫu nhiên 96 bit:** sinh bằng `SecureRandom` trong bài demo. Mỗi lần có xác suất trùng rất nhỏ ở số lượng thao tác hợp lý, nhưng **không bảo đảm duy nhất tuyệt đối**. Với nhiều bản ghi/tốc độ cao, phải có hạn mức sử dụng khóa, giám sát rủi ro va chạm và xoay khóa theo chính sách.
2. **Nonce đếm/định danh có cấu trúc:** thiết kế prefix định danh instance/partition cùng counter duy nhất, có cơ chế phối hợp và bền vững qua restart. Phải tránh hai process dùng chung khóa cùng cấp lại một nonce. Không tự chế khi chưa có quy tắc phân phối, lưu trạng thái, giới hạn số lượng và kiểm thử rõ ràng.

**Không dùng** nonce cố định cho mọi request, nonce từ timestamp không đảm bảo duy nhất, chuỗi chỉ số ngẫu nhiên yếu hoặc `new Random()` để sinh nonce. Nếu một hệ thống có nhiều process cùng giữ khóa AES, cần giải quyết tính duy nhất nonce **toàn hệ thống**, không chỉ trong một process.

**Không nhầm:** nonce GCM dùng cho yêu cầu **duy nhất khi mã hóa**; nonce/request ID dùng chống replay ở tầng giao thức là một bài toán khác dù có thể cùng tên. Tính duy nhất nonce AES-GCM **không tự ngăn phát lại** một ciphertext + tag hợp lệ.

### 4.2. Vì sao mất nonce sẽ không giải mã được?

Nonce là tham số đầu vào của GCM; giải mã cần cả **khóa và nonce ban đầu**. Nếu chỉ lưu ciphertext + tag mà bỏ nonce, không thể tái tạo nonce ngẫu nhiên sau này. Do đó, định dạng lưu trữ thường đưa nonce vào record bên cạnh ciphertext/tag.

Để phục vụ xoay khóa, record còn cần **key identifier** hoặc cách ánh xạ khóa an toàn. Key ID có thể công khai nhưng phải được xác thực/kiểm soát ngữ cảnh để tránh nhầm khóa hoặc downgrade. Không bao giờ xuất khóa AES cùng gói dữ liệu.

## 5. AAD: metadata không cần mã hóa nhưng phải được bảo vệ khỏi sửa đổi

**AAD (Additional Authenticated Data)** là dữ liệu byte được đưa vào phép tính tag nhưng **không nằm trong ciphertext**. Bên nhận phải tái tạo **chính xác cùng dãy byte AAD** khi giải mã.

Ví dụ bạn mã hóa giá trị một giao dịch:

~~~text
P   = "amount=100;currency=VND"  // cần giữ bí mật
AAD = "v1|tenant=blue|type=transfer"  // được phép công khai

Encrypt(K, N, P, AAD) → C + T

Decrypt(K, N, C, T, "v1|tenant=red|type=transfer") → lỗi tag
~~~

AAD giúp ràng buộc ciphertext vào **ngữ cảnh**. Nếu dữ liệu mã hóa của tenant A bị di chuyển sang tenant B nhưng bên B giải mã với AAD chứa tenant B từ **ngữ cảnh đáng tin**, tag sẽ không khớp. Tuy vậy, AAD không thể thay kiểm tra quyền tenant: nếu ứng dụng tùy tiện **tin giá trị tenant do kẻ tấn công tự gửi trong cùng gói**, việc xác minh tag không tự thực hiện phân quyền.

Các trường thường cân nhắc đưa vào AAD khi phù hợp với thiết kế:

- **Phiên bản định dạng/protocol** để ngăn nhầm định dạng hoặc thuật toán.
- **Record ID, object ID, tenant ID** nếu phải buộc bản mã thuộc một đối tượng/ngữ cảnh xác định.
- **Loại nội dung, endpoint, mục đích sử dụng khóa** nếu một khóa được dùng trong nhiều luồng cần tách ngữ cảnh.
- **Thông tin định danh khác** cần xác thực nhưng không cần che giấu.

Chú ý:

- AAD **không bí mật**: đừng để thông tin nhạy cảm vào AAD rồi tưởng đã được mã hóa.
- **Khác một byte là khác AAD**: UTF-8/UTF-16, newline, thứ tự trường JSON, khoảng trắng, cách viết số và Unicode normalization đều quan trọng. Thiết kế một biểu diễn byte **canonical** rõ ràng.
- Trong API Java, gọi `cipher.updateAAD(aad)` **sau `init` và trước khi đưa plaintext/ciphertext vào `update` hay `doFinal`**. Thứ tự gọi sai có thể gây lỗi API.
- Nếu không có metadata cần ràng buộc, AAD có thể rỗng; không ép phải tạo AAD giả. Nhưng nếu giao thức yêu cầu xác thực metadata, quên `updateAAD` là lỗi thiết kế.
- AAD dùng cho cả mã hóa và giải mã; **hai bên phải trùng byte 100%**. Không nên tùy ý chuyển cấu trúc từ string sang JSON mà không có giao ước phiên bản.

## 6. Định dạng truyền/lưu: nonce, ciphertext và tag nằm ở đâu?

Trong ví dụ Java, bản ghi nhị phân có dạng:

~~~text
+-------------------+--------------------------+----------------+
| nonce (12 byte)   | ciphertext (n byte)      | tag (16 byte)  |
+-------------------+--------------------------+----------------+
<--------------------- packet = 12 + n + 16 byte ---------------->
~~~

Một phần `nonce + ciphertext + tag` có thể được **Base64-encode** để đặt trong JSON. Base64 chỉ là **biểu diễn**, không tự bảo mật dữ liệu. AAD trong ví dụ là chuỗi byte lấy từ **ngữ cảnh ứng dụng** và được truyền/tái tạo riêng, không nằm trong packet.

Trong hệ thống có nhiều phiên bản và khóa, record thực tế thường cần thêm metadata, ví dụ:

~~~text
version | keyId | nonce | ciphertext | authenticationTag
             \                       /
              metadata định dạng được quy định cách xác thực
~~~

Nếu `version` hoặc `keyId` quyết định cách giải mã, cần thiết kế gắn metadata đó vào **AAD và/hoặc hợp đồng kiểm tra tin cậy** để không cho attacker tráo ngữ cảnh. Đặc tả phải nói rõ kiểu/độ dài từng trường, thứ tự byte, giới hạn payload, chế độ cấp nonce và cách xác định khóa. **Đừng cố đoán** tag nằm ở byte nào nếu hệ thống khác có cách lưu tách tag khỏi ciphertext; đó là khác biệt của định dạng giao thức, không phải tự do bỏ tag.

**Ví dụ kích thước:** Plaintext ASCII `"amount=100;currency=VND"` có 23 byte. Với AES-GCM tag 16 byte và nonce 12 byte, packet bài demo dài **51 byte** (`12 + 23 + 16`). Kích thước packet có thể khác nếu định dạng thêm header hoặc các trường khác.

## 7. Chuẩn bị an toàn trước khi lập trình

1. **Khóa:** Tạo bằng `KeyGenerator.getInstance("AES")` với nguồn `SecureRandom`. AES-128 hoặc AES-256 có thể sử dụng theo yêu cầu và chính sách hệ thống; mẫu dưới dùng AES-128 để dễ chạy rộng rãi, **không lưu khóa trong mã nguồn**.
2. **Nonce:** 12 byte mới cho mỗi lần mã hóa dưới cùng khóa; sinh bằng CSPRNG trong ví dụ. Đối với sản xuất nhiều tiến trình, thiết kế cấp nonce không trùng toàn hệ thống.
3. **Tag:** Dùng 128 bit qua `GCMParameterSpec(128, nonce)` ở cả hai phía.
4. **AAD:** Xác định byte ổn định bằng `StandardCharsets.UTF_8` và một quy ước định dạng thống nhất; lấy các thuộc tính nghiệp vụ quan trọng từ ngữ cảnh đã xác minh.
5. **Cipher:** Tạo một `Cipher` riêng cho mỗi thao tác; các đối tượng `Cipher` có trạng thái, không dùng chung không đồng bộ giữa nhiều request/thread.
6. **Lỗi:** Không trả plaintext nếu xác thực thất bại. Không cho phép client phân biệt quá chi tiết sai tag/sai khóa/sai AAD trong thông báo API; log chỉ metadata cần thiết, tránh log plaintext, secret, khóa hoặc các chi tiết nhạy cảm.
7. **Giới hạn dữ liệu:** Kiểm tra độ dài packet trước khi cấp phát/giải mã; đặt giới hạn kích thước theo nghiệp vụ và chính sách GCM của hệ thống. Một lần `doFinal` trên cả payload phù hợp ví dụ ngắn; payload lớn cần cấu trúc record/chunk AEAD được thiết kế riêng để xác thực từng chunk và thứ tự của chúng.

## 8. Ví dụ Java 17+ hoàn chỉnh: mã hóa, giải mã và phát hiện sửa đổi

Ví dụ chạy bằng **JDK chuẩn**, không cần dependency bên ngoài. Nó tạo key tạm, sinh nonce mới cho **một lần mã hóa**, gắn nonce trước `ciphertextAndTag`, rồi thử giải mã đúng và các bản bị sửa. Các dòng stdout dưới đây **không in khóa, nonce hay ciphertext ngẫu nhiên**, do đó có thể kiểm tra ổn định.

Lưu với tên chính xác **`AeadGcmDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AeadGcmDemo {
    static final int NONCE_BYTES = 12;
    static final int TAG_BITS = 128;
    static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(SecretKey key, byte[] plain, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plain);

        // Định dạng ví dụ: 12 byte nonce || ciphertext || 16 byte tag.
        return ByteBuffer.allocate(nonce.length + ciphertextAndTag.length)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    static byte[] decrypt(SecretKey key, byte[] packet, byte[] aad)
            throws GeneralSecurityException {
        if (packet.length < NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Packet too short");
        }

        ByteBuffer source = ByteBuffer.wrap(packet);
        byte[] nonce = new byte[NONCE_BYTES];
        source.get(nonce);
        byte[] ciphertextAndTag = new byte[source.remaining()];
        source.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        // Thành công mới trả plaintext; sai tag ném AEADBadTagException.
        return cipher.doFinal(ciphertextAndTag);
    }

    static boolean rejected(SecretKey key, byte[] packet, byte[] aad)
            throws GeneralSecurityException {
        try {
            decrypt(key, packet, aad);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey key = generator.generateKey();

        byte[] plain = "amount=100;currency=VND"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "v1|tenant=blue|type=transfer"
                .getBytes(StandardCharsets.UTF_8);
        byte[] packet = encrypt(key, plain, aad);

        System.out.println("Plain bytes     = " + plain.length);
        System.out.println("Packet bytes    = " + packet.length);
        System.out.println("Tag bytes       = " + TAG_BITS / 8);
        System.out.println("Restored        = " + new String(
                decrypt(key, packet, aad), StandardCharsets.UTF_8));

        byte[] changedCiphertext = packet.clone();
        changedCiphertext[NONCE_BYTES] ^= 1;
        byte[] changedTag = packet.clone();
        changedTag[changedTag.length - 1] ^= 1;
        byte[] changedNonce = packet.clone();
        changedNonce[0] ^= 1;

        System.out.println("Changed data    = " +
                rejected(key, changedCiphertext, aad));
        System.out.println("Changed tag     = " +
                rejected(key, changedTag, aad));
        System.out.println("Changed nonce   = " +
                rejected(key, changedNonce, aad));
        System.out.println("Changed AAD     = " + rejected(key, packet,
                "v1|tenant=red|type=transfer"
                        .getBytes(StandardCharsets.UTF_8)));

        SecretKey wrongKey = generator.generateKey();
        System.out.println("Wrong key       = " +
                rejected(wrongKey, packet, aad));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AeadGcmDemo.java
java AeadGcmDemo
~~~

Đầu ra kỳ vọng:

~~~text
Plain bytes     = 23
Packet bytes    = 51
Tag bytes       = 16
Restored        = amount=100;currency=VND
Changed data    = true
Changed tag     = true
Changed nonce   = true
Changed AAD     = true
Wrong key       = true
~~~

**Giải thích chính xác:**

1. `encrypt` sinh nonce 12 byte bằng `SecureRandom`, tạo `Cipher` với AES-GCM và tag 128 bit, đưa AAD vào trước khi mã hóa.
2. `doFinal(plain)` tạo ciphertext nối tag 16 byte. Packet là **nonce + ciphertext + tag**; bản rõ 23 byte nên packet 51 byte.
3. `decrypt` lấy nonce từ packet, thiết lập cùng độ dài tag và AAD, sau đó đưa `ciphertextAndTag` vào `doFinal`. Tag hợp lệ thì byte plaintext trả về đúng.
4. Khi sửa byte đầu ciphertext, byte cuối tag, byte nonce, hoặc đổi tenant trong AAD, xác minh thất bại; `rejected` bắt `AEADBadTagException` nên các dòng `Changed ...` in `true` (nghĩa là **bị từ chối**, không phải xác thực thành công).
5. Tạo một khóa AES khác khiến `Wrong key = true`; chứng minh không thể giải mã bằng key khác chỉ vì đã biết nonce/ciphertext/tag.

**Đây là ví dụ học tập:** Khóa sinh tạm mất sau khi chạy, nonce ngẫu nhiên chưa có cơ chế phối hợp cho nhiều instance và packet không chứa version/key ID. Trong hệ thống thật phải thêm quy tắc lưu khóa, cấp nonce, phiên bản schema, giới hạn payload và chống replay khi cần. Đoạn code minh họa nguyên tắc xác minh tag, không phải một thư viện lưu trữ ciphertext hoàn chỉnh.

## 9. Vai trò của tag so với MAC và chữ ký số

AES-GCM là **AEAD**: bên có secret key có thể tạo ciphertext/tag; người có cùng key có thể giải mã và xác minh. Tag được tích hợp trong phép GCM, **không phải đối tượng chứng minh danh tính bên ký độc lập**.

| Cơ chế | Giấu plaintext? | Xác thực/toàn vẹn? | Ai có thể kiểm tra? | Lưu ý |
| --- | --- | --- | --- | --- |
| **AES-GCM (AEAD)** | **Có**, nếu khóa bí mật và nonce đúng | **Có**, với ciphertext và AAD | Bên giữ secret key phù hợp | Tag gắn với mã hóa; nonce phải duy nhất theo key |
| **AES-CTR không có MAC** | Có theo giả định mode/nonce đúng | **Không** | Không có bước kiểm tag | Ciphertext có thể bị chỉnh sửa có chủ đích |
| **HMAC-SHA256** | **Không** | Có, theo khóa chia sẻ | Bên giữ HMAC secret | HMAC không giải mã, không tạo ciphertext |
| **Chữ ký số (Ed25519, RSA-PSS...)** | **Không** | Có, theo khóa ký và message | Bất kỳ ai có public key đáng tin | Ký bằng private key; phục vụ xác minh công khai |
| **SHA-256 không khóa** | Không | Tạo digest; không xác thực nguồn nếu đứng riêng | Ai cũng tính được | Không thay thế tag, HMAC hoặc chữ ký |
| **Base64** | Không | Không | Ai cũng encode/decode | Chỉ biểu diễn packet trong text |

**Không nên “nâng cấp” AES-GCM bằng cách tự nối thêm `SHA-256(ciphertext)`** rồi bỏ tag. Digest không có khóa không ngăn attacker thay bản mã và tạo digest mới. Ngược lại, cũng không cần tự ghép một HMAC riêng vào GCM chỉ để “bảo vệ tag tốt hơn” nếu không có giao thức đặc tả và đánh giá độc lập; dùng AEAD chuẩn đúng cách là đủ cho mục tiêu của nó.

## 10. Bốn tình huống ứng dụng điển hình

### 10.1. Mã hóa một record trong cơ sở dữ liệu

~~~text
DB row:
  id = 42
  tenant = blue
  keyId = k2026-10
  nonce = ...
  ciphertextAndTag = ...

Giải mã:
  key = KMS.resolve(keyId)
  aad = canonical("v1", tenant từ ngữ cảnh tin cậy, row id)
  plaintext = AES-GCM-Decrypt(key, nonce, ciphertextAndTag, aad)
~~~

Nếu ai đó tráo ciphertext giữa hai row mà ứng dụng lấy `row id`/tenant từ **row/ngữ cảnh đã kiểm chứng** vào AAD, việc tráo thường bị phát hiện bằng tag không hợp lệ. Cần thiết kế cách ràng buộc `keyId` và version, chống attacker điều khiển metadata đầu vào không tin cậy. Encryption không thay phân quyền đọc DB, mã hóa ở ổ đĩa hoặc chính sách truy cập.

### 10.2. Nhận request API có thể bị phát lại

Một gói AES-GCM hợp lệ **có thể được gửi lại** nếu vẫn dùng cùng key, nonce, ciphertext/tag và AAD. Tag không chứa lịch sử đã nhận. Với API có tác dụng tạo lệnh thanh toán hoặc sửa dữ liệu, ứng dụng nên ràng buộc request ID, timestamp/expiry hoặc sequence vào giao thức/AAD, **sau đó kiểm tra hiệu lực và chống dùng lại bằng trạng thái tin cậy**. Chỉ đưa timestamp vào AAD mà không kiểm thời gian/không ghi nhận ID đã dùng vẫn không chống replay đầy đủ.

### 10.3. Mã hóa file lớn hoặc dữ liệu streaming

Không đọc file rất lớn vào RAM chỉ để dùng một `doFinal` nếu hệ thống không có bộ nhớ phù hợp. Có thể dùng API `update(...)`, `doFinal(...)` của `Cipher` theo đúng giao thức nhưng **không được tin/tiêu thụ plaintext trung gian trước khi tag hoàn tất**. Thiết kế record/chunk AEAD cho file lớn thường cần:

- Nonce duy nhất cho mỗi chunk, dưới cùng khóa;
- Ràng buộc **file ID, chunk index, tổng số chunk, vị trí/thứ tự** qua AAD;
- Xác minh **đủ các chunk và metadata toàn cục**, chống cắt bớt/đổi thứ tự/thay chunk;
- Giới hạn dung lượng và quản lý quota khóa đúng chuẩn.

Không thể đơn giản coi “mỗi chunk decrypt được” là toàn bộ file chắc chắn hoàn chỉnh nếu kẻ tấn công có thể xóa hoặc hoán vị chunk.

### 10.4. Dữ liệu mã hóa rồi Base64 trong JSON

~~~json
{
  "version": 1,
  "keyId": "k2026-10",
  "payloadBase64": "..."
}
~~~

Trong ví dụ minh họa, `payloadBase64` là Base64 của **nonce || ciphertext || tag**. API cần quy ước AAD và xác minh version/key ID theo hợp đồng. **Giải mã Base64 không phải giải mã AES-GCM**; còn cần khóa, nonce, ciphertext, tag và AAD khớp.

## 11. Những lỗi bảo mật và lỗi API thường gặp

| Lỗi | Vì sao sai/nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| **Tái sử dụng cùng key + nonce khi encrypt** | Có thể phá cả tính bí mật và khả năng xác thực GCM. | Cấp nonce duy nhất theo key, giám sát quota, xoay khóa và thiết kế phối hợp nhiều process. |
| **Dùng nonce 12 byte toàn số 0 cho mọi message** | Mỗi lần với cùng key đều dùng lại nonce. | Sinh/điều phối nonce mới cho mỗi lần mã hóa; nonce không cần giữ bí mật. |
| **Tưởng nonce phải giấu** | Thiếu nonce khiến không giải mã được; giấu nonce không bù việc reuse. | Lưu/truyền nonce cùng ciphertext/tag, nhưng bảo đảm quy tắc duy nhất. |
| **Bỏ 16 byte tag khi lưu ciphertext** | Không thể xác minh bản mã đã được chấp nhận; giải mã sẽ lỗi. | Giữ ciphertext **và** tag nguyên vẹn theo định dạng. |
| **Tự so sánh tag bằng Java `==`/`equals`** | Xác thực GCM phải do primitive thực hiện với khóa và nonce; so sánh sai kiểu không có ý nghĩa. | Truyền nguyên ciphertext+tag vào `Cipher.doFinal` khi decrypt. |
| **Catch `AEADBadTagException` rồi sử dụng dữ liệu đã có** | Dữ liệu chưa xác thực có thể dẫn đến tác động nghiệp vụ. | Từ chối toàn bộ thông điệp, không commit tác dụng phụ từ plaintext chưa xác thực. |
| **Nhầm AAD thành ciphertext** | AAD không được mã hóa nên dữ liệu nhạy cảm có thể lộ. | Chỉ dùng AAD cho metadata cần xác thực và cho phép công khai; plaintext cần bí mật phải đưa vào encrypt. |
| **Đổi AAD giữa hai phía** | Tag không hợp lệ, ví dụ khác encoding, thứ tự trường hoặc tenant. | Quy định canonical byte AAD, dùng UTF-8, cùng schema/version. |
| **Gọi `updateAAD` sau khi xử lý input qua `update`** | Vi phạm trình tự API của AEAD. | `init` → `updateAAD` → `update/doFinal`. |
| **Sử dụng AES/GCM/NoPadding nhưng tin rằng “NoPadding = không có tag”** | “NoPadding” chỉ là không có padding plaintext; GCM vẫn tạo tag. | Luôn xác minh tag đúng độ dài. |
| **Dùng tag 128 bit lúc encrypt, khai báo 96 bit lúc decrypt** | Hai bên hiểu khác độ dài tag/định dạng; xác minh lỗi. | Cố định `GCMParameterSpec` theo giao thức. |
| **Dùng chung một `Cipher` instance cho các thread/request** | Trạng thái Cipher và IV/tag bị trộn hoặc race. | Tạo/init riêng cho từng thao tác, không chia sẻ mutable Cipher giữa luồng. |
| **Tưởng AES-GCM tự chống request phát lại** | Tag hợp lệ cho gói cũ vẫn hợp lệ. | Có protocol state chống replay, expiry/sequence/request ID được kiểm tra. |
| **Dùng key hard-code hoặc ghi key vào log** | Lộ khóa làm mất an toàn nhiều bản ghi. | KMS/secret manager, phân quyền, rotation, audit; không log secret. |
| **Không quản lý phiên bản và key ID** | Không giải mã được sau rotation, dễ nhập nhằng giao thức. | Record có schema version/key ID, metadata nhạy về ngữ cảnh được xác thực. |
| **Đổ toàn bộ lỗi xác thực vào response chi tiết** | Tạo kênh rò rỉ về trạng thái khóa/dữ liệu hoặc hữu ích cho attacker. | Trả lỗi tổng quát an toàn; nội bộ log có kiểm soát và không chứa secrets. |

**Về xử lý lỗi:** `IllegalArgumentException` cho packet quá ngắn trong demo là kiểm tra **định dạng đầu vào**, khác với `AEADBadTagException` khi tag sai. Hệ thống thực tế nên chuẩn hóa cả hai thành lỗi yêu cầu không hợp lệ ở ranh giới không tin cậy, đồng thời giữ telemetry nội bộ phù hợp mà không lộ dữ liệu nhạy cảm.

## 12. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** Một người chặn mạng nhìn thấy nonce 12 byte, ciphertext và tag 16 byte. Họ có thể giải mã ngay chỉ vì nonce không bí mật không?

**Đáp án:** Không. Nonce là tham số công khai; cần khóa AES phù hợp để giải mã và xác minh tag. Bảo mật phụ thuộc khóa bí mật, nonce đúng cách và tính an toàn của thuật toán.

**Câu 2.** Dữ liệu AAD trong AES-GCM có được giữ bí mật không? Nếu AAD đổi từ `tenant=blue` thành `tenant=red` nhưng ciphertext/tag giữ nguyên thì sao?

**Đáp án:** AAD **không được mã hóa**. Thay byte AAD khiến xác minh tag thất bại khi decrypt dưới cùng key/nonce/ciphertext/tag. Ứng dụng phải lấy tenant từ ngữ cảnh đáng tin và kiểm tra quyền riêng.

**Câu 3.** Với AES-GCM tag 128 bit, plaintext 23 byte và nonce 12 byte, packet `nonce || ciphertext || tag` dài bao nhiêu?

**Đáp án:** `12 + 23 + 16 = 51` byte. GCM là NoPadding nên ciphertext dài bằng plaintext trong định dạng ví dụ.

**Câu 4.** Một dịch vụ encrypt với cùng key và cùng nonce cho hai record khác nhau, nhưng mỗi record có AAD khác. Có an toàn không?

**Đáp án:** **Không.** AAD khác nhau không thay thế yêu cầu duy nhất của nonce dưới cùng khóa. Phải tránh mọi lần mã hóa lặp cặp key/nonce.

**Câu 5.** `decrypt` ném `AEADBadTagException`. Có nên trả phần plaintext có thể đã được xử lý trước khi exception xảy ra không?

**Đáp án:** Không. Bỏ toàn bộ dữ liệu chưa xác thực; không dùng plaintext trung gian trong tính toán nghiệp vụ, không commit transaction hay ghi ra nơi khác trước khi tag hợp lệ.

**Câu 6.** Một client gửi lại nguyên vẹn một gói thanh toán GCM hợp lệ mà server đã xử lý hôm qua. Tag có thất bại vì request cũ không?

**Đáp án:** Không. Nếu key/nonce/AAD/ciphertext/tag vẫn khớp, tag vẫn hợp lệ. Server cần quản lý chống replay bằng request ID/sequence và thời hạn hợp lệ.

**Câu 7.** Có nên gửi thêm `SHA-256(ciphertext)` cùng AES-GCM tag để xác minh dữ liệu chưa bị sửa?

**Đáp án:** Không cần cho mục tiêu này. SHA-256 không khóa không chống người thay ciphertext rồi băm lại. Tag AES-GCM đã là cơ chế xác thực tích hợp; hãy ưu tiên dùng đúng primitive và protocol chuẩn.

**Câu 8.** Khi hệ thống có 20 worker cùng mã hóa với một khóa AES, mỗi worker dùng counter nonce bắt đầu từ 0. Có ổn không?

**Đáp án:** Không, vì các worker có thể tạo cùng nonce dưới một khóa. Cần cơ chế phân vùng nonce/điều phối counter/định danh instance đảm bảo không trùng kể cả restart, hoặc chiến lược sinh nonce đã được đánh giá và quota/key rotation phù hợp.

## 13. Checklist áp dụng AES-GCM trong Java

- **Đúng primitive:** `AES/GCM/NoPadding` qua `Cipher` chuẩn; 128-bit authentication tag bằng `GCMParameterSpec`, không thay tag bằng checksum/hash.
- **Đúng secret:** Khóa AES có entropy và quyền truy cập phù hợp, không hard-code; có quản lý vòng đời/rotation.
- **Đúng nonce:** 12 byte theo định dạng phổ biến; **duy nhất mỗi lần encrypt dưới cùng key**; phân phối trên toàn hệ thống.
- **Đúng AAD:** Chỉ metadata công khai cần xác thực; xác định byte UTF-8/canonical, gắn ngữ cảnh đã tin cậy, gọi `updateAAD` trước dữ liệu.
- **Đúng wire format:** Giữ nonce, ciphertext, tag và mọi thông tin version/key ID cần thiết; tránh nhầm Base64 với bảo mật.
- **Đúng cách decrypt:** Đưa nguyên ciphertext+tag cho `doFinal`, chỉ dùng plaintext sau khi xác minh thành công; từ chối mọi lỗi tag.
- **Đúng giao thức:** Thêm chống replay, giới hạn kích thước, phân quyền/định danh, xử lý lỗi và theo dõi hoạt động; AEAD không thay tất cả các tầng bảo mật khác.
- **Đúng vận hành:** Nếu dữ liệu lớn, thiết kế chunk/record AEAD với thứ tự/index và điều kiện hoàn tất được xác thực; không xử lý plaintext streaming chưa kiểm tag.

**Kết luận:** **AEAD = mã hóa có xác thực dữ liệu liên kết**. Với `AES/GCM/NoPadding`, **ciphertext** bảo vệ bí mật của plaintext, **authentication tag** giúp phát hiện sửa đổi của ciphertext và AAD, **nonce** là đầu vào công khai nhưng phải duy nhất dưới cùng khóa, còn **AAD** ràng buộc metadata quan trọng mà không che giấu metadata đó. Trong Java, kiểm tra tag nằm trong `Cipher.doFinal` khi giải mã: **tag không hợp lệ thì không có dữ liệu đáng tin để xử lý**.
