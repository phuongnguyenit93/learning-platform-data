# 8.9 Giới hạn của việc dùng thuật toán bất đối xứng thay cho mã hóa dữ liệu khối lớn

**Mã hóa bất đối xứng (public-key encryption)** giải quyết bài toán quan trọng: người gửi có thể sử dụng **khóa công khai** của người nhận để mã hóa một bí mật mà chỉ người giữ **khóa riêng** tương ứng có khả năng giải mã, với điều kiện thuật toán và giao thức được dùng đúng. Nhưng điều đó **không có nghĩa** RSA hoặc các primitive khóa công khai là lựa chọn phù hợp để mã hóa trực tiếp một file vài MB/GB, một luồng video hoặc toàn bộ dữ liệu trong cơ sở dữ liệu.

Cách làm thực tế thường là **mã hóa lai (hybrid encryption)**: thuật toán bất đối xứng/KEM hoặc giao thức thỏa thuận khóa đảm nhận việc **thiết lập/bảo vệ một khóa phiên nhỏ**; thuật toán đối xứng **AEAD** như AES-GCM mã hóa và xác thực **dữ liệu lớn**. Bài này tập trung vào giới hạn kỹ thuật của bất đối xứng khi thay mã hóa khối lớn, cách tính đúng kích thước RSA-OAEP, vì sao “cắt file thành nhiều đoạn rồi RSA từng đoạn” không phải giải pháp, và cách thiết kế envelope encryption trong Java 17+.

## 1. Bất đối xứng và đối xứng đảm nhận hai công việc khác nhau

| Khía cạnh | Mã hóa bất đối xứng / cơ chế khóa công khai | Mã hóa đối xứng AEAD |
| --- | --- | --- |
| Vật liệu khóa | Khóa công khai/khóa riêng, hoặc cặp khóa và shared secret trong giao thức thỏa thuận khóa | Một khóa bí mật chia sẻ hoặc data-encryption key (DEK) |
| Công việc điển hình | Mã hóa/đóng gói khóa phiên nhỏ, trao đổi/thiết lập bí mật, chữ ký số (là primitive khác) | Mã hóa lượng dữ liệu tùy ý **trong giới hạn mỗi thuật toán/giao thức**, đồng thời xác thực ciphertext và AAD |
| Chi phí tính toán | Thường lớn hơn đáng kể mỗi phép toán; RSA private-key operation đặc biệt đắt | Thường hiệu quả cho lượng byte lớn; có hỗ trợ tăng tốc trên nhiều CPU |
| Độ dài input trực tiếp | Với RSA-OAEP bị giới hạn bởi modulus và hash/padding, thường vài trăm byte | Dựa vào mode và giới hạn nonce/message; không bị ràng buộc kiểu “190 byte RSA-2048” |
| Kích thước output | Một phép RSA encryption trả ciphertext dài bằng modulus, bất kể plaintext ngắn thế nào | Thường xấp xỉ độ dài plaintext cộng tag/nonce/metadata nếu giao thức đóng gói |
| Xác thực nguồn gửi | **RSA encryption chỉ dùng khóa công khai người nhận không xác thực danh tính người gửi** | AEAD xác thực dữ liệu dưới khóa đã biết, không tự gắn danh tính người gửi |
| Điểm cần quản lý | Tin cậy public key, key ID, chứng chỉ, private key, padding, thuật toán và key rotation | Sinh/quản lý key, nonce/IV duy nhất, AAD, tag, integrity, rotation và policy |

**Định nghĩa quan trọng:** RSA encryption, RSA signature, ECDSA signature, ECDH key agreement và KEM là các primitive **khác nhau**, dù đều nằm trong thế giới khóa công khai. Không thể lấy chữ ký số rồi gọi đó là mã hóa, hoặc gọi ECDH là hàm mã hóa dữ liệu file.

Một câu tóm tắt dễ nhớ:

> **Khóa công khai bảo vệ hoặc thiết lập khóa dữ liệu; khóa dữ liệu đối xứng bảo vệ phần lớn byte của tài liệu.**

## 2. Giới hạn kích thước plaintext của RSA-OAEP

RSA làm việc với một modulus `n`, và ciphertext của một phép RSA encryption là một giá trị được mã hóa vào đúng kích thước modulus. Với **RSA-2048**, modulus thông thường dài **2.048 bit = 256 byte**. Nhưng **đầu vào tối đa không phải 256 byte**, vì cơ chế padding RSA-OAEP cần vùng dữ liệu để đảm bảo an toàn.

### 2.1. Công thức RSAES-OAEP

Theo cơ chế RSAES-OAEP trong PKCS #1 (RFC 8017), nếu:

- `k` = số **byte** cần để biểu diễn modulus RSA;
- `hLen` = số byte đầu ra của hash dùng trong OAEP;
- `mLen` = số byte plaintext;

thì cần:

```text
mLen <= k - 2 * hLen - 2
```

Đây là **giới hạn kích thước byte**, không phải giới hạn số ký tự Unicode hoặc Java `String.length()`.

Với modulus 2.048 bit, `k = 256`. Khi OAEP dùng SHA-256, `hLen = 32`, nên:

```text
maxPlaintext = 256 - 2 * 32 - 2 = 190 bytes
RSA ciphertext length = 256 bytes
```

Nếu file chứa **191 byte**, một phép RSA-2048 + OAEP SHA-256 trực tiếp không thể mã hóa nó. Việc “RSA có khóa 2.048 bit” hoàn toàn không có nghĩa có thể nạp plaintext 2.048 bit hoặc nhiều hơn vào cùng phép toán.

### 2.2. So sánh các cấu hình

| Modulus RSA | `k` | Hash OAEP / `hLen` | Plaintext tối đa mỗi RSA-OAEP operation | Ciphertext mỗi operation |
| --- | ---: | --- | ---: | ---: |
| RSA-2048 | 256 byte | SHA-1 / 20 byte | 214 byte | 256 byte |
| RSA-2048 | 256 byte | SHA-256 / 32 byte | **190 byte** | **256 byte** |
| RSA-3072 | 384 byte | SHA-256 / 32 byte | 318 byte | 384 byte |
| RSA-4096 | 512 byte | SHA-256 / 32 byte | 446 byte | 512 byte |
| RSA-2048 | 256 byte | SHA-512 / 64 byte | 126 byte | 256 byte |

Các giá trị là giới hạn **về kích thước**, không phải khuyến nghị bảo mật cho từng tổ hợp. SHA-1 trong bảng chỉ để thấy hiệu ứng của `hLen`; thiết kế mới nên sử dụng thuật toán và profile được chính sách bảo mật hiện hành cho phép, không chọn SHA-1 chỉ để tăng kích thước input. RSA-2048 cũng không có “độ mạnh 2.048 bit”: mức bảo mật cổ điển ước lượng chỉ khoảng **112 bit**, khác hoàn toàn kích thước modulus. Chọn RSA-3072/4096 hay giải pháp khóa công khai khác phải cân nhắc chính sách, thời gian bảo vệ dữ liệu và hiệu năng.

### 2.3. Các tham số OAEP phải xác định đầy đủ

Trong Java thường thấy chuỗi transformation `"RSA/ECB/OAEPPadding"` hoặc `"RSA/ECB/OAEPWithSHA-256AndMGF1Padding"`. Chữ **ECB** trong tên transformation RSA là quy ước API, **không có nghĩa RSA đang mã hóa khối dữ liệu giống AES-ECB**; RSA không dùng chế độ ECB cho file.

Để tránh mơ hồ giữa **hash của OAEP** và **hash dùng trong MGF1**, nên chỉ định cả hai qua `OAEPParameterSpec`:

```java
OAEPParameterSpec oaep = new OAEPParameterSpec(
    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT
);
Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, oaep);
```

Đây là **đoạn minh họa đặt tham số**, chưa phải chương trình độc lập: `recipientPublicKey` phải là `PublicKey` đã được xác minh nguồn tin cậy; các `import` sẽ có trong chương trình hoàn chỉnh phía sau.

Không phụ thuộc mặc định của provider rồi giả định mọi JVM/hệ thống sẽ tự chọn cùng một OAEP hash/MGF1 hash. Sai tham số có thể dẫn đến không giải mã được hoặc sự cố tương thích. RSA-OAEP hỗ trợ tùy chọn label `PSource.PSpecified`; phía mã hóa và giải mã cũng phải dùng đúng label theo giao thức.

### 2.4. Tăng kích thước khóa RSA có giải quyết được file lớn?

**Không.** RSA-4096 với OAEP SHA-256 vẫn chỉ xử lý tối đa **446 byte/plaintext operation**, trong khi file có thể dài hàng triệu hoặc hàng tỷ byte. Tăng modulus vừa làm key/ciphertext lớn hơn vừa thường làm phép toán private-key chậm hơn đáng kể.

Với **RSA-2048/OAEP SHA-256**, một file **1 MiB = 1.048.576 byte** nếu cố cắt thành các đoạn tối đa 190 byte sẽ cần:

```text
numberOfRSAOperations = ceil(1,048,576 / 190) = 5,519
ciphertextSize = 5,519 * 256 = 1,412,864 bytes
overhead = 1,412,864 - 1,048,576 = 364,288 bytes
```

Đây mới là **chi phí kích thước** của phép chia khối, chưa gồm framing, sequence, thuật toán, khóa, version hay bảo vệ toàn vẹn. Hệ thống còn phải thực hiện **5.519 RSA encrypt operations** và tương ứng hàng nghìn **RSA private-key decrypt operations** thay vì một phép toán RSA bọc khóa nhỏ và một lượt AES trên file.

## 3. Vì sao “chia nhỏ file rồi RSA từng chunk” là thiết kế tệ?

### 3.1. Hiệu năng không phù hợp với throughput lớn

RSA dựa trên phép toán số học modulo big integer, có chi phí lớn hơn hẳn các round cipher đối xứng trên lượng dữ liệu dài. Chia file thành 5.519 khối tạo hàng nghìn phép toán khóa công khai, tải CPU và độ trễ tăng theo số lượng chunk; khi dùng HSM/KMS còn gặp overhead RPC, giới hạn throughput và chi phí vận hành.

Đối xứng như **AES-GCM** được tối ưu cho xử lý lượng byte lớn, có hỗ trợ tăng tốc AES/CLMUL ở nhiều nền tảng. **Không cần gán một tỷ lệ tốc độ cố định** cho mọi CPU/provider: hãy benchmark trong môi trường thực, nhưng cấu trúc công việc khác nhau rất rõ.

### 3.2. Mỗi block RSA có overhead đáng kể

Một block plaintext 190 byte trở thành block ciphertext 256 byte. Nếu block cuối chỉ có 1 byte, nó vẫn chiếm **256 byte**. Padding OAEP cần ngẫu nhiên, nên mã hóa cùng plaintext bằng cùng public key thường cho ciphertext khác nhau; không thể tự cắt overhead đi sau khi mã hóa.

Với file lớn, size của hàng nghìn block cộng metadata làm truyền/lưu trữ tốn hơn so với cách mã hóa dữ liệu bằng AES-GCM chỉ thêm tag nhỏ và phần header/nonce.

### 3.3. RSA-OAEP không biến các chunk thành một file được xác thực

RSA-OAEP cung cấp cơ chế mã hóa an toàn khi dùng đúng và trong mô hình phù hợp, nhưng **không phải một giao thức AEAD cho toàn bộ file**. Nếu tự chia file thành các chunk, bạn phải tự xử lý:

- Thứ tự chunk và số thứ tự; chống đảo thứ tự/ghép chunk từ file khác.
- Chống thiếu chunk, lặp chunk, cắt cụt phần đuôi và thay thế nội dung.
- Xác thực metadata như file ID, độ dài dự kiến, content type, version.
- Phát hiện sửa đổi theo một chính sách thống nhất, không chỉ biết từng RSA operation có giải mã ra byte hay không.
- Xử lý lỗi và padding oracle/leak qua thông điệp lỗi hoặc timing.

Cài đặt thiếu một trong những lớp trên có thể tạo lỗi nghiêm trọng. Mã hóa từng block RSA và ghép lại không tự biến thành *secure file encryption*. **Đừng tự phát minh “RSA chunk mode”** để né giới hạn `mLen`.

### 3.4. Nguy cơ thiết kế/API

- Đừng dùng `RSA/ECB/NoPadding` như một mẹo để nạp được nhiều byte hơn: **raw/textbook RSA không an toàn** và không giải quyết bài toán bulk encryption.
- Đừng chuyển sang `RSA/ECB/PKCS1Padding` chỉ vì nó cho plaintext dài hơn OAEP một chút: RSAES-PKCS1-v1_5 có rủi ro padding-oracle và không phải lựa chọn mặc định cho thiết kế mới.
- Đừng dùng RSA **signature** để “mã hóa bằng private key”. Chữ ký phục vụ xác thực/tính toàn vẹn theo chuẩn chữ ký; nó **không tạo bí mật dữ liệu**.
- Đừng mã hóa một file trực tiếp bằng khóa công khai EC/ECDSA: ECDSA là chữ ký số; ECDH/X25519 là cơ chế **thỏa thuận khóa**, không phải `Cipher.doFinal(file)` để mã hóa trực tiếp.

## 4. Giải pháp đúng: Hybrid encryption / envelope encryption

Trong mô hình RSA-OAEP + AES-GCM, một file có một **data-encryption key (DEK)** ngẫu nhiên ngắn. Phần bất đối xứng **chỉ bọc DEK**; phần đối xứng mã hóa toàn bộ file.

### 4.1. Luồng mã hóa

```text
                   Bên gửi
   [PublicKey người nhận đã xác thực]
                     |
    Tạo AES-256 data key ngẫu nhiên (32 byte)
                     |
             +-------+--------+
             |                |
    RSA-OAEP encrypt(DEK)   AES-GCM encrypt(file, DEK, nonce, AAD)
             |                |
      wrappedKey (256 B)    ciphertext || tag
             |                |
             +-------+--------+
                     |
       Envelope: header + keyId + wrappedKey
                  + nonce + ciphertext + tag
                     |
              Lưu / truyền cho người nhận
```

Các bước:

1. **Xác minh public key của người nhận** bằng certificate/PKI, danh bạ khóa đã pin hoặc kênh cung cấp khóa được xác thực. Nếu đối thủ thay public key bằng của họ, toàn bộ file có thể bị mã hóa để đối thủ mở.
2. **Sinh một DEK ngẫu nhiên mới** (ví dụ AES-256 = 32 byte) bằng CSPRNG/KeyGenerator; không dùng mật khẩu hoặc `new Random()` làm key.
3. **Bọc DEK** bằng public key RSA của người nhận và RSA-OAEP có tham số xác định; output là một RSA ciphertext nhỏ, ví dụ 256 byte với RSA-2048.
4. **Sinh nonce/IV đúng yêu cầu AEAD**; với AES-GCM thường dùng 96 bit = 12 byte. Với cùng một AES key, **nonce không được lặp**. Tạo DEK mới cho mỗi file giúp đơn giản hóa chiến lược nonce, nhưng vẫn phải quản lý sao cho không reuse cặp key/nonce.
5. **Mã hóa file bằng AES-GCM** với DEK, nonce và AAD đã chuẩn hóa; kết quả gồm ciphertext và authentication tag, ví dụ tag 128 bit = 16 byte.
6. **Đóng gói envelope** có version, thuật toán, key ID, wrapped key, nonce, ciphertext, tag và AAD/metadata cần thiết; kiểm tra giới hạn độ dài và chính sách parse trước khi giải mã.

### 4.2. Luồng giải mã

```text
                  Bên nhận
     Envelope và metadata đã kiểm tra sơ bộ
                     |
    Xác định keyId + phiên bản + thuật toán hợp lệ
                     |
      PrivateKey --> RSA-OAEP decrypt(wrappedKey)
                     |           |
                     |        AES data key
                     |           |
              ciphertext, nonce, AAD
                     |           |
              AES-GCM decrypt + verify tag
                     |
           Chỉ chấp nhận plaintext khi
           authentication tag đã hợp lệ
```

**Thứ tự bảo mật:** không coi plaintext là đáng tin trước khi AEAD tag được kiểm tra; một file có tag sai phải bị từ chối toàn bộ. Nếu giải mã theo stream để ra disk, hãy cân nhắc **ghi vào file tạm cô lập** rồi chỉ công bố/rename sau khi hoàn thành xác thực, không cho các thành phần nghiệp vụ đọc trước.

### 4.3. Kích thước thật của envelope ví dụ

Với RSA-2048 OAEP SHA-256 bọc một **AES-256 key 32 byte**, và AES-GCM mã hóa đúng **1 MiB plaintext**:

| Thành phần | Số byte |
| --- | ---: |
| AES data key (chỉ tồn tại trong bộ nhớ, **không** gửi plaintext key) | 32 |
| `wrappedKey` RSA-OAEP của DEK | 256 |
| GCM nonce | 12 |
| Dữ liệu ciphertext của 1 MiB plaintext | 1.048.576 |
| GCM tag 128 bit | 16 |
| `ciphertext || tag` từ `Cipher.doFinal` | **1.048.592** |
| `wrappedKey || nonce || ciphertext || tag` | **1.048.860** |
| Header, key ID, version, lengths, AAD metadata | **Thêm tùy định dạng** |

Đối chiếu với 1.412.864 byte khi mã hóa trực tiếp 1 MiB theo 5.519 block RSA, hybrid có **overhead binary chỉ 284 byte trong ví dụ chưa tính header**, và chỉ cần **một RSA operation** để bọc DEK; khối dữ liệu lớn đi qua AES-GCM.

Không hiểu số “32 byte AES key” là một thành phần được truyền ở dạng plaintext; nó nằm bên trong `wrappedKey`. Việc nhân bản/ghi raw DEK vào envelope sẽ phá hoàn toàn tính bí mật.

### 4.4. Vấn đề cần đặt trong header và AAD

Một envelope đủ dùng thật không chỉ là nối bốn mảng byte tùy ý. Phải định nghĩa schema không nhập nhằng, ví dụ:

```text
version
suiteId / asymmetricKeyId / recipientId
wrappedKeyLength + wrappedKey
nonceLength + nonce
ciphertextLength + ciphertext || tag
associatedData (metadata được xác thực)
```

- **Định dạng ranh giới byte:** length-prefix, TLV, CBOR/protobuf schema được giới hạn và chuẩn hóa. Không đoán độ dài chỉ dựa vào delimiter trong binary.
- **AAD (additional authenticated data):** đưa các metadata cần bảo vệ tính toàn vẹn (version, algorithm suite, document ID, tenant/recipient context, hoặc key binding) vào AAD theo quy tắc canonical rõ ràng. AAD **được xác thực nhưng không mã hóa**.
- **Không tin dữ liệu điều khiển từ envelope:** `suiteId`, `keyId`, độ dài và version là input không tin cậy. Server chỉ chấp nhận allowlist thuật toán, scope key và kích thước phù hợp; không để attacker điều khiển đường dẫn đọc private key hay chọn thuật toán yếu.
- **RSA-OAEP và AES-GCM phải phối hợp thống nhất:** khi receiver unwrap đúng DEK và dùng đúng nonce + AAD, AES-GCM sẽ xác thực ciphertext/tag. Nếu metadata cần được xác thực nhưng nằm ngoài AAD thì có nguy cơ bị thay mà vẫn xác minh GCM thành công.
- **Ràng buộc người nhận:** nếu nhiều người nhận, policy và metadata liên quan danh tính/khóa cần được bảo vệ phù hợp; khóa bất đối xứng được chọn phải được xác minh trước.

## 5. Java 17+: thử giới hạn RSA-OAEP và mã hóa lai file 1 MiB

Đây là một chương trình Java 17+ **độc lập, biên dịch và chạy được**, thực hiện cả hai thử nghiệm:

- Tạo RSA-2048 và dùng OAEP với **hash SHA-256 + MGF1 SHA-256 được khai báo tường minh**. Mã hóa trực tiếp 190 byte thành công, 191 byte bị từ chối.
- Tạo AES-256 key ngẫu nhiên, **RSA-OAEP chỉ mã hóa 32 byte DEK**, còn AES-GCM mã hóa **1.048.576 byte dữ liệu**. Giải mã lại, kiểm tra round-trip và phát hiện thay đổi ciphertext.

Chương trình chỉ in các số đo và kết luận boolean, **không in khóa bí mật hoặc ciphertext**. Để minh họa đơn giản nó giữ 1 MiB trong RAM; đây **không phải code xử lý file nhiều GB hoặc định dạng envelope production**.

Lưu file **HybridCryptoDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class HybridCryptoDemo {
    static final OAEPParameterSpec OAEP = new OAEPParameterSpec(
            "SHA-256", "MGF1",
            MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT);
    static final byte[] AAD =
            "file-envelope:v1".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        // Bên nhận: minh họa tạo cặp khóa RSA 2048 bit.
        KeyPairGenerator rsaGen = KeyPairGenerator.getInstance("RSA");
        rsaGen.initialize(2048);
        KeyPair receiver = rsaGen.generateKeyPair();

        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.ENCRYPT_MODE, receiver.getPublic(), OAEP);
        byte[] direct = rsa.doFinal(new byte[190]);
        boolean tooLargeRejected = false;
        try {
            rsa.doFinal(new byte[191]);
        } catch (IllegalBlockSizeException expected) {
            tooLargeRejected = true;
        }
        System.out.println("RSA-OAEP 190-byte input -> "
                + direct.length + "-byte ciphertext");
        System.out.println("RSA-OAEP 191-byte input rejected: "
                + tooLargeRejected);

        // Bên gửi: một khóa đối xứng mới, chỉ bọc khóa bằng RSA.
        KeyGenerator aesGen = KeyGenerator.getInstance("AES");
        aesGen.init(256);
        SecretKey dataKey = aesGen.generateKey();
        // Khởi tạo lại Cipher sau phép thử đầu vào quá dài.
        rsa.init(Cipher.ENCRYPT_MODE, receiver.getPublic(), OAEP);
        byte[] wrappedKey = rsa.doFinal(dataKey.getEncoded());

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] file = new byte[1024 * 1024];
        new SecureRandom().nextBytes(file);

        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");
        gcm.init(Cipher.ENCRYPT_MODE, dataKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        byte[] sealed = gcm.doFinal(file);

        System.out.println("AES key: "
                + dataKey.getEncoded().length + " bytes");
        System.out.println("RSA-wrapped key: "
                + wrappedKey.length + " bytes");
        System.out.println("nonce: " + nonce.length + " bytes");
        System.out.println("file: " + file.length + " bytes");
        System.out.println("AES-GCM ciphertext+tag: "
                + sealed.length + " bytes");
        System.out.println("envelope binary bytes (without header): "
                + (wrappedKey.length + nonce.length + sealed.length));

        // Bên nhận: unwrap khóa rồi xác minh/giải mã GCM.
        rsa.init(Cipher.DECRYPT_MODE, receiver.getPrivate(), OAEP);
        byte[] unwrapped = rsa.doFinal(wrappedKey);
        SecretKeySpec recoveredKey = new SecretKeySpec(unwrapped, "AES");

        gcm.init(Cipher.DECRYPT_MODE, recoveredKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        byte[] restored = gcm.doFinal(sealed);
        System.out.println("round-trip OK: "
                + Arrays.equals(file, restored));

        // Một byte ciphertext bị sửa thì GCM không được chấp nhận.
        byte[] changed = sealed.clone();
        changed[0] ^= 1;
        gcm.init(Cipher.DECRYPT_MODE, recoveredKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        boolean tamperRejected = false;
        try {
            gcm.doFinal(changed);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("tampered ciphertext rejected: "
                + tamperRejected);

        Arrays.fill(unwrapped, (byte) 0);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 HybridCryptoDemo.java
java HybridCryptoDemo
```

Stdout kỳ vọng (các giá trị độ dài không phụ thuộc vào byte khóa/nonce được sinh ngẫu nhiên; đã kiểm tra bằng Java):

```text
RSA-OAEP 190-byte input -> 256-byte ciphertext
RSA-OAEP 191-byte input rejected: true
AES key: 32 bytes
RSA-wrapped key: 256 bytes
nonce: 12 bytes
file: 1048576 bytes
AES-GCM ciphertext+tag: 1048592 bytes
envelope binary bytes (without header): 1048860
round-trip OK: true
tampered ciphertext rejected: true
```

### 5.1. Vì sao kết quả như vậy?

1. **190 byte:** công thức OAEP SHA-256 trên RSA-2048 có input tối đa 190 byte; `doFinal(new byte[190])` mã hóa thành 256 byte.
2. **191 byte:** `IllegalBlockSizeException` xuất hiện ở provider JDK thông dụng vì message quá lớn. Demo bắt lỗi như một thử nghiệm, không biến `doFinal` lỗi thành đường xử lý nghiệp vụ.
3. **AES-256:** `KeyGenerator.init(256)` nhận độ dài **bit**; secret key exportable trong provider phần mềm demo dài 32 byte. HSM/provider không xuất khóa có thể trả `getEncoded() == null`; ở sản phẩm không ép lấy raw key nếu API wrap/unwrap/derive có khả năng xử lý khóa trong HSM.
4. **Wrapped key:** RSA chỉ xử lý 32 byte input nên luôn dưới giới hạn 190 byte; output là 256 byte.
5. **AES-GCM:** tag 128 bit = 16 byte. Với 1 MiB plaintext, `doFinal` tạo 1.048.576 + 16 = **1.048.592 byte**. Nonce 12 byte được giữ tách riêng, không có sẵn trong output của `Cipher.doFinal()`.
6. **Tổng binary:** 256 byte wrapped key + 12 byte nonce + 1.048.592 byte GCM result = **1.048.860 byte**, chưa gồm header/schema/key ID.
7. **Xác thực:** chỉnh một byte ở ciphertext làm tag không khớp nên `AEADBadTagException` được phát ra khi giải mã. Cả ciphertext **và AAD** phải khớp bản đã dùng khi mã hóa.

### 5.2. Những giới hạn của chương trình minh họa

- Nó tạo RSA keypair và file ngẫu nhiên mỗi lần chạy; sản phẩm phải **xác thực public key người nhận**, quản lý private key và đặt rõ key ID/rotation.
- Nó giữ cả 1 MiB file, sealed và restored trong RAM; **không dùng nguyên mẫu để xử lý file khổng lồ**.
- Nó không serialize/parse envelope, không lưu version/key ID và không tạo AAD theo header động. Khi triển khai cần định dạng chuẩn và policy chặt.
- Nó chỉ dùng AAD cố định để minh họa API; trong sản phẩm AAD có thể phải chứa metadata của file và recipient, được canonicalize và đồng nhất ở hai phía.
- Nó tạo DEK mới mỗi lần chạy; không tái sử dụng key + nonce. **Trùng nonce dưới cùng khóa GCM có thể phá tính bí mật và toàn vẹn**.
- `Arrays.fill(unwrapped, (byte) 0)` chỉ dọn mảng tạm theo khả năng; không chứng minh xóa được mọi bản sao trong `SecretKeySpec`, JVM hoặc provider. Trong môi trường đòi hỏi bảo vệ khóa cao, xem xét HSM/KMS và khóa không xuất được.
- Mặc dù AES-GCM xác minh dữ liệu dưới DEK, demo **không xác minh danh tính bên gửi** và không chứng minh ai tạo envelope, vì bất kỳ ai có public key người nhận cũng có thể tự tạo một DEK mới rồi mã hóa file khác. Cần lớp xác thực người gửi riêng nếu nghiệp vụ yêu cầu.

## 6. Xử lý file thực sự lớn: streaming, bộ nhớ và kiểm tra tag

Hybrid encryption giải quyết giới hạn kích thước RSA, nhưng **“dùng AES-GCM” không đồng nghĩa hệ thống có thể cấp phát một mảng byte kích thước file vài GB**. Khi file lớn hơn bộ nhớ, thiết kế luồng I/O, giới hạn độ dài mỗi message và cách công bố plaintext là rất quan trọng.

### 6.1. Streaming encryption

Về mặt ý tưởng, hệ thống đọc file qua `InputStream` theo các buffer nhỏ, đẩy vào `Cipher.update(...)` / cơ chế stream encryption thích hợp và ghi ciphertext ra file tạm/đích theo một framing có version. Cuối stream gọi `doFinal()` để thu tag cuối và hoàn thiện envelope.

**Không sử dụng `new byte[(int)file.length()]`** làm đường đi mặc định cho file nhiều GB: có thể tràn int hoặc gây `OutOfMemoryError`. Cần giới hạn input, dùng file/stream, phân biệt metadata và ciphertext, kiểm soát I/O errors và cleanup.

Cấu trúc ý tưởng (**pseudocode**, không phải Java có thể chạy trực tiếp):

```text
create fresh DEK and unique nonce
wrap DEK with recipient's verified public key
write validated envelope header
initialize AEAD encryptor with DEK, nonce and exact AAD
while input has more bytes:
    read bounded chunk
    encrypt and write bytes (preserve order)
finalize AEAD encryption and append authentication tag
finish/commit envelope only after successful completion
```

Pseudocode không thay thế thư viện/giao thức được kiểm định. Với AES-GCM một message rất lớn, phải tuân thủ **giới hạn kích thước và giới hạn sử dụng theo khóa/nonce** của tiêu chuẩn và provider; khi vượt ngưỡng, thiết kế giao thức record/chunk AEAD thay vì nối vô hạn vào một GCM invocation.

### 6.2. Streaming decryption: không được dùng plaintext chưa xác thực

Khi giải mã AES-GCM, integrity tag thường chỉ được xác minh hoàn chỉnh **ở cuối message**. Một API stream/provider có thể trả các byte trước khi xác minh cuối cùng, hoặc giữ chúng tùy implementation; tuyệt đối **không dựa vào giả định “có output nghĩa là đã xác thực”**.

Đối với file lớn:

- Ghi plaintext tạm vào vùng không cho ứng dụng khác sử dụng, giới hạn truy cập.
- Chỉ commit, rename hoặc phân phối plaintext khi AEAD tag của **toàn bộ message** hợp lệ.
- Nếu tag sai, xóa bản tạm và báo lỗi chung; không để một file một phần được hệ thống tiêu thụ.
- Không bỏ qua exception ở `Cipher.doFinal()`, không tự chỉ kiểm tra 16 byte tag theo so sánh thủ công rồi bỏ qua dữ liệu AAD.
- Với nhiều message/chunk AEAD, **mỗi chunk phải được xác thực**, và toàn bộ chuỗi cần ràng buộc thứ tự, vị trí, file ID, tổng chunk, độ dài/cuối file để chống reorder, rollback và truncate.

### 6.3. Mã hóa theo chunk đúng cách

Nếu ứng dụng cần random-access hoặc file quá lớn so với giới hạn một message AEAD, có thể sử dụng một **định dạng mã hóa theo record/chunk** được thiết kế và kiểm định phù hợp:

- Mỗi chunk có nonce/sequence **không trùng dưới cùng khóa**.
- AAD ràng buộc **file ID, version, sequence index, total length hoặc final marker** theo thiết kế.
- Hệ thống xác minh tính toàn vẹn **toàn bộ file** và tính liên tục của chunk; “mọi chunk riêng lẻ có tag đúng” chưa đủ để chống thiếu chunk/đảo thứ tự nếu không ràng buộc dữ liệu.
- Giới hạn số lượng chunk trên một DEK, tổng dữ liệu mã hóa trên khóa và trạng thái sử dụng nonce; tuân theo giới hạn thuật toán/giao thức.
- Khi có thư viện/giao thức authenticated streaming encryption thích hợp và được hỗ trợ, ưu tiên nó thay vì tự phát minh cách đặt nonce, index, tag hay metadata.

## 7. ECC, ECDH, KEM và HPKE: vẫn cần thuật toán đối xứng cho payload lớn

Không phải mọi public-key primitive đều giống RSA encryption. Với các hệ thống hiện đại, có các cách thiết lập shared secret hoặc encapsulate key material:

| Cơ chế | Tác dụng | Có trực tiếp mã hóa file MB/GB không? |
| --- | --- | --- |
| **RSA-OAEP** | Mã hóa bí mật nhỏ/DEK cho public key người nhận | **Không phù hợp**; RSA có giới hạn `mLen` và chi phí lớn |
| **ECDH / X25519** | Hai bên tính shared secret từ khóa riêng và public key của nhau | **Không**; cần KDF và AEAD để mã hóa dữ liệu |
| **KEM (key encapsulation mechanism)** | Encapsulate bí mật và decapsulate ở người nhận | **Không**; sau KEM thường dùng KDF và AEAD |
| **HPKE (RFC 9180)** | Kết hợp KEM, KDF và AEAD theo suite và mode của chuẩn | **Có thể dùng để mã hóa ứng dụng qua giao thức**, nhưng payload lớn vẫn do AEAD xử lý; phải tuân theo giới hạn suite/context |

### 7.1. ECDH không phải “AES với khóa EC”

ECDH/X25519 cho hai bên tính ra shared secret theo thuật toán thỏa thuận khóa. **Không dùng trực tiếp raw shared secret làm AES key bằng cách cắt byte tùy tiện**; áp dụng KDF được đặc tả (thường HKDF) và context cần thiết để dẫn xuất key/nonce, đồng thời đảm bảo public key, bên nhận và giao thức được xác thực.

Nếu một thiết kế ECDH không có xác thực, **kẻ trung gian có thể thay public key** và thiết lập secret riêng với mỗi phía. Việc dùng ECDH không tự bảo đảm bạn đang nói chuyện đúng người nhận.

### 7.2. Hybrid không có nghĩa hai thuật toán đều mã hóa toàn bộ file

Một mô hình KEM + KDF + AEAD cũng là dạng hybrid:

```text
KEM.encapsulate(recipientPublicKey) -> encapsulation + sharedSecret
HKDF(sharedSecret, protocolContext) -> AEAD key/nonce material
AEAD.encrypt(file, key, nonce, AAD) -> ciphertext + tag
envelope -> encapsulation + ciphertext + tag + metadata
```

Không cần “RSA encrypt(file) rồi AES encrypt(lại file)” để có hai lớp. Điều quan trọng là **kiểm soát nguồn public key, bảo vệ/thiết lập DEK và mã hóa/xác thực payload đúng cách**. Tên gọi “hybrid encryption” có thể dùng cho nhiều bộ thuật toán; thiết kế phải ghi rõ suite và mục tiêu bảo mật.

## 8. Bảo mật hệ thống: hybrid giải quyết cái gì và không giải quyết cái gì?

### 8.1. Bí mật dữ liệu ở nơi lưu trữ

Nếu public key người nhận đáng tin và private key được bảo vệ, bọc DEK bằng RSA-OAEP kết hợp AES-GCM có thể cung cấp **bí mật của file** khi chỉ ciphertext/envelope được lưu. Để an toàn thật, không để DEK lọt vào log, cache không kiểm soát, exception, metadata hoặc nơi chứa plaintext.

Nhưng nếu private key RSA bị lộ, các DEK cũ bọc bằng key đó có thể bị unwrap từ envelope được lưu. Do đó đây **không mặc định có forward secrecy** cho dữ liệu đã lưu. Một giao thức có ephemeral secret và key erasure đúng có thể có những tính chất khác, nhưng phải phân tích theo giao thức cụ thể.

### 8.2. Kiểm chứng public key là một phần của mã hóa

Dùng public key tải từ đường dẫn do attacker cung cấp không tạo bí mật **cho đúng người nhận**. Phải có cơ chế tin cậy: chứng chỉ hợp lệ, key pinning, authenticated directory, HSM/KMS identity hoặc quy trình provisioning được bảo vệ.

Không chọn khóa bằng `kid` do file tự khai mà bỏ qua tenant/recipient scope; không tự tải URI trong header để lấy public key rồi coi là key tin cậy.

### 8.3. AEAD không tự xác thực danh tính người gửi

Một file AES-GCM có tag đúng chỉ cho biết file/metadata không bị đổi so với khóa AEAD đã sử dụng (trong giả định thuật toán đúng). Trong mô hình public-key hybrid nơi **bất cứ ai** có public key nhận cũng có thể tạo DEK mới, **một ciphertext hợp lệ không chứng minh ai gửi nó**.

Nếu nghiệp vụ đòi hỏi danh tính, cần xác thực nguồn riêng: TLS endpoint đã xác thực, chữ ký số trên nội dung/envelope có ngữ cảnh phù hợp, hoặc giao thức gửi nhận authenticated được chuẩn hóa. Chữ ký số phải có cơ chế phân phối/trust khóa công khai người ký tương ứng.

### 8.4. Mức bảo mật không bằng kích thước AES key một cách máy móc

Bộ RSA-2048 + AES-256 có thể có **điểm yếu hơn AES-256** do mức bảo mật cổ điển của RSA-2048 và rủi ro quản lý private key. Mức an toàn của toàn hệ thống là bài toán tổng thể: thuật toán yếu nhất, key length, key distribution, AEAD nonce, lifecycle, lỗi phần mềm, authorization và mô hình tấn công. Đừng chọn “AES-256” rồi coi mọi yếu tố khác đạt bảo mật 256 bit.

### 8.5. Khi có nhiều người nhận

Để gửi **cùng một file** cho nhiều người nhận, thường có thể mã hóa payload **một lần** bằng một DEK và **bọc DEK riêng** cho public key của từng người nhận:

```text
file --AEAD(DEK)--> ciphertext+tag
             DEK --recipient A public key--> wrappedKeyA
             DEK --recipient B public key--> wrappedKeyB
             DEK --recipient C public key--> wrappedKeyC
```

Bằng cách này payload lớn không bị mã hóa lại bằng RSA theo từng người nhận; overhead chủ yếu tăng theo số wrapped keys. Tuy nhiên cần ràng buộc recipients/key IDs và metadata trong thiết kế envelope và xử lý việc thu hồi người nhận. Người đã có DEK hoặc plaintext **không thể bị thu hồi quyền đọc bản sao đã lấy chỉ bằng cách xóa entry**.

## 9. Thiết kế hệ thống Java: ranh giới API, lựa chọn công cụ và vận hành

### 9.1. Xác định API theo vai trò

- **RSA:** `Cipher.getInstance("RSA/ECB/OAEPPadding")`, `OAEPParameterSpec` và public/private key từ key store/KMS đã được quản lý. Đối với DEK ngẫu nhiên 16/32 byte, RSA-OAEP phù hợp hơn mã hóa data khối lớn.
- **AES-GCM:** `Cipher.getInstance("AES/GCM/NoPadding")`, `GCMParameterSpec` và key ngẫu nhiên, nonce phù hợp; xác minh AEAD tag khi decrypt.
- **Bộ sinh khóa:** `KeyGenerator.getInstance("AES")` với kích thước bit được policy hỗ trợ; `SecureRandom` để sinh nonce và byte ngẫu nhiên khác nếu cần.
- **Quản lý khóa:** private key nên ở keystore/HSM/KMS/secret manager có kiểm soát access; ứng dụng không cần tự xuất private key nếu provider hỗ trợ phép toán cần thiết.
- **Key rotation:** envelope cần key ID và version để unwrap DEK bằng private key đúng; các file còn phải đọc được cần chiến lược giữ khóa cũ/rewrap phù hợp.

Không lưu private key RSA cạnh ciphertext trong một thư mục public. Nếu private key và dữ liệu đều bị lộ, lớp bất đối xứng mất tác dụng. Khi cần backup/restore, có chính sách giữ và bảo vệ khóa cũ đủ lâu để phục hồi tài liệu.

### 9.2. Chi phí RSA/KMS vẫn tồn tại nhưng chỉ trên dữ liệu nhỏ

Hybrid không loại bỏ hoàn toàn RSA cost; nó giảm số phép toán khóa công khai từ **hàng nghìn mỗi file** về **một hoặc vài phép toán bọc/unwrap DEK** tùy số người nhận. Khi dùng HSM/KMS, vẫn phải xét latency, quota API, failover, audit và cache policy; nhưng không đưa mỗi 190 byte file đi gọi RSA.

Với hệ thống có KMS hỗ trợ symmetric data-key/envelope encryption, có thể dùng chức năng tạo DEK và bọc DEK của dịch vụ, thay vì ứng dụng tự thực hiện RSA. Mô hình “envelope” **không bắt buộc phải dùng RSA**; KMS symmetric wrapping hoặc KEM tương ứng cũng có thể phù hợp theo kiến trúc.

### 9.3. File lớn, API phản hồi và lỗi

- Áp **giới hạn request/file size**, định dạng hợp lệ và giới hạn độ dài từng trường envelope trước khi cấp phát bộ nhớ.
- Không để các lỗi khác nhau của RSA/OAEP/GCM tạo oracle tiết lộ chi tiết bí mật qua response, log hoặc timing.
- Với GCM, lỗi tag phải là **thất bại xác thực file**; đừng dùng plaintext đã phát ra một phần.
- Tách key-encryption-key/wrapping key và data-encryption-key để dễ **rewrap DEK khi rotation** thay vì luôn giải mã/mã hóa lại cả file, nhưng chỉ thực hiện khi policy và định dạng cho phép.
- Đặt version thuật toán, key ID, suite và metadata trong một cấu trúc được kiểm tra, không dựa vào chuỗi tên transformation do client tùy ý cung cấp.
- Khi cần sửa hoặc tải một phần file theo random-access, thiết kế authenticated chunking/format chuyên dụng; **đừng tự cắt tag GCM rồi xác minh từng phần**.

## 10. Các lỗi thường gặp

| Cách nghĩ hoặc cách làm sai | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| “RSA-2048 mã hóa được 2.048 bit plaintext.” | Modulus length không phải độ dài payload cho phép | Dùng công thức OAEP `k - 2*hLen - 2` |
| “Không đủ thì chia file thành nhiều đoạn RSA.” | Tốn CPU/overhead và không xác thực file tổng thể | Bọc DEK nhỏ bằng RSA, mã hóa file bằng AEAD |
| “Chọn RSA-4096 để mã hóa file 1 GB trực tiếp.” | Vẫn chỉ vài trăm byte/operation | Chọn hybrid/envelope hoặc giao thức mã hóa file phù hợp |
| “RSA encryption bằng public key chứng minh người gửi.” | Bất cứ ai có public key đều có thể mã hóa | Dùng chữ ký số hoặc authenticated channel cho sender |
| “RSA signature bằng private key là mã hóa.” | Signature không bảo mật plaintext | Phân biệt ký số và encryption |
| “EC public key có thể đưa thẳng vào AES Cipher.” | ECDH không tự mã hóa payload | Key agreement/KEM + KDF + AEAD đúng chuẩn |
| “Dùng RSA/NoPadding để bỏ giới hạn.” | Raw RSA không an toàn | Sử dụng scheme padding chuẩn và hybrid |
| “Dùng RSA/PKCS1Padding vì plaintext tối đa dài hơn.” | Có rủi ro legacy/padding-oracle | Ưu tiên RSA-OAEP có tham số chính xác cho thiết kế mới |
| “OAEPWithSHA-256 nghĩa MGF1 tự giống nhau ở mọi provider.” | Có thể sai tham số và interop | `OAEPParameterSpec` explicit cho digest, MGF1 và label |
| “Nonce GCM chỉ cần đúng 12 byte.” | Nonce lặp lại dưới cùng key nguy hiểm | Thiết kế/kiểm tra **tính duy nhất của nonce** |
| “GCM trả plaintext là đã xác minh xong.” | Có thể dùng dữ liệu trước khi tag được kiểm tra | Chỉ commit sau toàn bộ AEAD verification |
| “Header/key ID không cần MAC vì chỉ là metadata.” | Có thể bị sửa ngữ cảnh hoặc key lookup | Bind AAD/metadata và kiểm tra key scope/version |
| “AES-256 làm RSA-2048 mạnh 256 bit.” | Mức bảo mật là của hệ thống, không chỉ DEK | Đánh giá độ mạnh khóa công khai, policy và lifecycle |
| “Mã hóa file một lần là xong key rotation.” | Private key cũ vẫn cần để unwrap các DEK cũ | Có key version/rewrap/retention policy |
| “Chỉ phải kiểm tra tag mỗi chunk riêng lẻ.” | Có thể đảo, cắt, thay thế chunk | Gắn sequence, length, file ID và finalization vào authenticated structure |

## 11. Checklist trước khi triển khai bulk encryption

1. **Mục tiêu:** dữ liệu cần giữ bí mật trước đối tượng nào? Người nhận là ai, và cần xác thực danh tính người gửi không?
2. **Key trust:** public key đến từ nguồn được xác minh chưa? Private key có ở nơi được quản lý an toàn không?
3. **Thuật toán:** đã chọn một suite rõ ràng cho key encapsulation/wrapping + AEAD chưa? Có tránh raw RSA/legacy padding không?
4. **RSA capacity:** nếu dùng RSA-OAEP, chỉ đưa vật liệu khóa nhỏ vào RSA và kiểm tra `mLen <= k - 2*hLen - 2` chưa?
5. **Data key:** mỗi file/envelope có DEK ngẫu nhiên phù hợp? Có đảm bảo không log hoặc truyền DEK dạng plaintext không?
6. **AEAD nonce/tag:** nonce duy nhất trên mỗi key; tag độ dài chuẩn; AAD/metadata phải đúng byte và được xác minh?
7. **Envelope:** version/key ID/lengths/algorithm suite có parser giới hạn kích thước, chống ambiguity và đảm bảo integrity không?
8. **File lớn:** dùng streaming/chunking authenticated phù hợp, tránh tải cả file vào RAM, không công bố plaintext trước tag validation?
9. **Vận hành:** có rotation, rewrap, backup/recovery, revoke, audit, quota KMS và xử lý lỗi an toàn?
10. **Kiểm thử:** thử đúng/sai public key, sai OAEP params, byte ciphertext/tag bị sửa, nonce khác, AAD khác, missing/truncated chunk, file lớn và nhiều người nhận?

## 12. Bài tập tự kiểm tra

**Câu 1.** RSA-2048 + OAEP SHA-256 cho phép bao nhiêu byte plaintext trong một RSA operation?  
**Đáp án:** **190 byte** vì `256 - 2*32 - 2 = 190`; ciphertext dài **256 byte**.

**Câu 2.** Muốn RSA-OAEP mã hóa một chuỗi 500 ký tự Unicode trong một lần vì “500 ký tự là ít”, có đúng không?  
**Đáp án:** **Không**. Phải đếm **số byte sau encoding UTF-8** và áp công thức modulus/padding; RSA-2048 OAEP SHA-256 tối đa 190 **byte**, kể cả nội dung chỉ vài chục ký tự Unicode vẫn có thể dài nhiều byte.

**Câu 3.** Nếu có file 1 MiB, chia thành block 190 byte rồi RSA-2048 từng block cần bao nhiêu ciphertext byte?  
**Đáp án:** `ceil(1,048,576/190) = 5,519` block, mỗi block 256 byte, tổng **1.412.864 byte**, chưa metadata.

**Câu 4.** Với RSA-2048 bọc AES-256 key, AES-GCM mã hóa 1 MiB file, tag 16 byte và nonce 12 byte, cần ít nhất bao nhiêu byte cho wrappedKey + nonce + ciphertext + tag?  
**Đáp án:** **256 + 12 + 1.048.576 + 16 = 1.048.860 byte**, chưa header.

**Câu 5.** Một file được mã hóa AES-GCM thành công dưới DEK bọc bằng public key của Bob. Có chứng minh Alice là người gửi không?  
**Đáp án:** **Không**. Ai có public key Bob cũng có thể tạo DEK riêng và mã hóa file. Cần xác thực người gửi bằng cơ chế phù hợp.

**Câu 6.** Có thể lưu nonce/GCM tag bên cạnh ciphertext không?  
**Đáp án:** **Có**; nonce và tag không cần giữ bí mật. Nhưng nonce phải duy nhất với cùng key; tag và metadata phải được xử lý/xác thực chính xác.

**Câu 7.** Nếu giải mã stream trả một số plaintext trước khi kiểm tra tag cuối, có thể để chương trình khác sử dụng phần plaintext đó ngay không?  
**Đáp án:** **Không nên**. Cần giữ cách ly/không công bố cho tới khi tag toàn message hợp lệ, hoặc dùng giao thức authenticated chunk phù hợp.

**Câu 8.** Đổi RSA modulus từ 2.048 lên 4.096 bit là cách tối ưu chính để mã hóa file 5 GB?  
**Đáp án:** **Không**. Chỉ tăng input RSA-OAEP lên vài trăm byte mỗi operation và tăng chi phí phép toán; nên dùng hybrid encryption.

**Câu 9.** Tại sao hybrid dùng cùng một DEK mã hóa toàn bộ file rồi bọc DEK cho nhiều người nhận lại hiệu quả?  
**Đáp án:** Payload được mã hóa đối xứng **một lần**; chỉ việc bọc một DEK nhỏ được lặp theo người nhận. Cần bảo vệ metadata và hiểu rằng người đã có DEK có thể giữ bản sao riêng.

**Câu 10.** Nếu RSA unwrap key thành công nhưng GCM tag sai, có chấp nhận một phần dữ liệu vì “RSA đã xác minh khóa” không?  
**Đáp án:** **Không**. RSA unwrap thành công không thay thế AEAD integrity. Phải coi file không hợp lệ và không công bố plaintext.

### Ghi nhớ

**Mã hóa bất đối xứng không thay thế mã hóa dữ liệu khối lớn.** RSA-OAEP có giới hạn plaintext theo modulus và padding, chi phí phép toán cao, và không cung cấp giao thức xác thực file khi tự chia chunk. Thiết kế phù hợp là **khóa công khai/KEM để bảo vệ hoặc thiết lập DEK nhỏ + AEAD đối xứng để mã hóa payload lớn**, kết hợp kiểm chứng public key, nonce/AAD, định dạng envelope, streaming an toàn và key lifecycle.
