# 3.3 Phân biệt số bit, số byte, độ dài khóa và độ dài đầu ra

Trong lập trình mật mã Java, các con số **128, 256, 2048, 32 hoặc 64** thường xuất hiện bên cạnh thuật toán và API. Chúng có thể biểu thị số **bit**, số **byte**, độ dài **khóa bí mật**, kích thước **modulus** của khóa bất đối xứng, độ dài **digest/MAC/tag**, hoặc số ký tự của chuỗi đã **mã hóa để hiển thị**. Những đại lượng đó liên quan nhưng **không thể thay thế cho nhau**. Nhầm đơn vị có thể khiến code không chạy, lưu trữ thiếu byte hoặc đánh giá sai độ an toàn.

## 1. Đơn vị nền tảng: bit, byte và cách đổi

- **Bit** là một vị trí nhị phân có giá trị 0 hoặc 1. Ký hiệu thường dùng: **bit** hoặc **b**.
- **Byte** trong Java có **8 bit**: hằng số `Byte.SIZE` bằng 8. Ký hiệu thông dụng cho byte là **B**. Vì vậy **1 B = 8 bit**.
- Nếu có đúng `n` byte, số bit cần để biểu diễn chúng là **8 × n**; nếu số bit chia hết cho 8, số byte là **số bit / 8**.
- Với độ dài bit bất kỳ `n`, số byte **tối thiểu để chứa** giá trị đó là **ceil(n / 8)**, hay với số nguyên không âm: **(n + 7) / 8**. Byte cuối có thể chứa các bit không sử dụng.
- `kB` = 1.000 byte, `KiB` = 1.024 byte. Phân biệt hai hệ đơn vị dung lượng này với các độ dài khóa thường biểu diễn bằng bit.

| Kích thước | Tương ứng byte | Ngữ cảnh thường gặp |
| --- | ---: | --- |
| 64 bit | 8 byte | Giá trị số nguyên 64 bit; nonce 64 bit ở một số giao thức |
| 96 bit | 12 byte | Nonce/IV khuyến nghị thường dùng cho AES-GCM |
| 128 bit | 16 byte | Khóa AES-128; tag GCM 128 bit |
| 192 bit | 24 byte | Khóa AES-192 |
| 256 bit | 32 byte | Khóa AES-256; đầu ra SHA-256 |
| 384 bit | 48 byte | Đầu ra SHA-384 |
| 512 bit | 64 byte | Đầu ra SHA-512 |
| 2.048 bit | 256 byte | Phần modulus của khóa RSA-2048 (độ dài thường dùng) |

**Cần nói rõ đại lượng:** “256 bit” chỉ là số bit; nếu không biết nó là *khóa*, *digest*, *tag*, *nonce* hay *modulus*, không thể suy ra chức năng hoặc độ mạnh bảo mật.

Ví dụ tính trực tiếp: 128 bit / 8 = **16 byte**; 32 byte × 8 = **256 bit**. Một khóa RSA có modulus 2.048 bit chứa khoảng 256 byte biểu diễn modulus; **toàn bộ public/private key được mã hóa theo định dạng tệp thường dài hơn**.

### 1.1. Byte trong Java và chiều dài mảng

Trong Java, `byte` là kiểu nguyên **8 bit có dấu**, biểu diễn các giá trị từ -128 đến 127. Tính có dấu chỉ là cách Java diễn giải mẫu bit thành số; **một phần tử `byte[]` vẫn mang đúng 8 bit**.

- `byte[].length` đếm **số byte trong mảng**, không đếm bit.
- `Byte.SIZE` = 8; `Byte.BYTES` = 1.
- `int` là 32 bit và `long` là 64 bit trong Java, nhưng số bit của kiểu dữ liệu **không phải độ dài của nội dung được serialize hay entropy**.
- Với số byte rất lớn, dùng phép nhân trên kiểu `long` hoặc `Math.multiplyExact` phù hợp để tránh tràn số khi đổi sang bit.

### 1.2. Độ dài chuỗi ký tự không đồng nghĩa độ dài byte

`String.length()` của Java trả về **số đơn vị mã UTF-16**, không phải số ký tự Unicode theo nghĩa code point, càng không phải số byte khi gửi qua mạng.

Ví dụ chuỗi **“Việt”** có 4 đơn vị mã UTF-16, nhưng khi chuyển qua UTF-8 thành **6 byte = 48 bit**, vì ký tự “ệ” chiếm 3 byte UTF-8. Một emoji ngoài BMP thường có 1 code point, 2 đơn vị mã UTF-16 và 4 byte UTF-8.

Cách đếm đúng trước khi đưa text vào hash, MAC, mã hóa hay giao thức:

```java
String text = "Việt";
byte[] data = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int bytes = data.length;
long bits = (long) bytes * Byte.SIZE;
```

**Hệ quả:** kiểm tra “tối đa 256 ký tự” không tương đương giới hạn “tối đa 256 byte”. Khi giới hạn payload, KDF hoặc trường binary, hãy nêu rõ **encoding** và đơn vị đếm.

## 2. Độ dài khóa: kích thước khóa cần khác với số byte của dữ liệu đã mã hóa

**Độ dài khóa (key length/key size)** là số bit của vật liệu khóa hoặc kích thước tham số khóa mà thuật toán định nghĩa. Cách biểu diễn khác nhau giữa các họ thuật toán.

### 2.1. Khóa đối xứng: AES-128, AES-192, AES-256

AES chấp nhận khóa **128, 192 hoặc 256 bit**, lần lượt là **16, 24 hoặc 32 byte**. Con số sau “AES-” là số bit của **khóa**, không phải số byte của bản mã, không phải số vòng tự chọn và cũng không phải tag.

- Trong Java JCA/JCE, `KeyGenerator.getInstance("AES")` tạo bộ sinh khóa AES; `KeyGenerator.init(128)` yêu cầu **128 bit**, không phải 128 byte.
- Với khóa AES thông thường do phần mềm xuất được, `SecretKey.getEncoded()` trả về byte khóa: AES-128 dài 16 byte.
- `SecretKey.getEncoded()` **có thể trả `null`** đối với khóa không được phép xuất, ví dụ một số khóa trên HSM/provider. Đừng xem việc có hay không có byte xuất ra là phép xác minh duy nhất cho mọi loại khóa.
- **AES có block size cố định 128 bit (16 byte)** bất kể khóa AES dài 128, 192 hay 256 bit. Không suy ra block size từ key size.
- Có nhiều byte khóa hơn chưa chắc làm hệ thống an toàn hơn nếu khóa được tạo từ mật khẩu yếu, bị hardcode, lộ qua log hoặc được quản trị sai.

Khi thấy cấu hình `AES-256-GCM`, phải tách ít nhất **khóa 256 bit**, **block AES 128 bit**, **nonce thường 96 bit**, và **tag thường 128 bit**; đây là bốn giá trị khác mục đích.

### 2.2. Khóa bất đối xứng: RSA-2048 và đường cong elliptic

**RSA-2048** nói tới độ dài **modulus n**, thông thường 2.048 bit = 256 byte, **không có nghĩa file chứa public key dài đúng 256 byte**. Public key RSA còn chứa exponent; khóa mã hóa thành X.509 SubjectPublicKeyInfo theo DER có ASN.1 và metadata. Private key PKCS#8 chứa nhiều thành phần hơn, do đó có thể dài hơn đáng kể.

- `RSAPublicKey.getModulus().bitLength()` cho **bit length thực của modulus**.
- `publicKey.getEncoded().length` cho **số byte của cấu trúc public key được mã hóa**. Hai số đo phục vụ hai câu hỏi khác nhau.
- Với RSA-2048, ciphertext RSA sau một phép mã hóa có kích thước modulus, thường **256 byte**, nhưng **plaintext tối đa lại nhỏ hơn nhiều**, phụ thuộc padding; chẳng hạn RSA-OAEP với SHA-256 làm hash OAEP có giới hạn **256 − 2 × 32 − 2 = 190 byte** mỗi lần mã hóa. Lưu ý cấu hình hash cho OAEP/MGF1 cần thống nhất theo giao thức, không tự suy diễn từ tên transformation.
- RSA chữ ký thường có kích thước bằng số byte modulus; đó không phải kích thước private key được lưu trên đĩa.

**P-256** là đường cong có tham số trường và bậc nhóm cỡ 256 bit; **không nên đánh đồng** nó với khóa AES-256 về mức an toàn tương đương. Public key EC có thể là điểm mã hóa dạng nén, không nén hoặc bọc X.509/DER; signature ECDSA cũng có thể ở dạng DER độ dài biến thiên hoặc dạng raw `r || s` cố định theo giao thức. Vì vậy số byte của “public key”/“signature” còn phụ thuộc **định dạng**.

### 2.3. Key size không bằng security strength

**Security strength (độ mạnh bảo mật)** ước lượng mức công việc tấn công, thường quy về số bit bảo mật đối với một mô hình tấn công cụ thể. Nó **không bằng số bit viết trong tên thuật toán**.

| Thuật toán/tham số | Độ dài hay nhìn thấy | Độ mạnh ước lượng cổ điển (xấp xỉ) |
| --- | --- | --- |
| AES-128 | Khóa 128 bit | 128 bit khi khóa ngẫu nhiên, không lộ và thuật toán dùng đúng |
| AES-256 | Khóa 256 bit | 256 bit chống vét cạn khóa trong mô hình lý tưởng |
| RSA-2048 | Modulus 2.048 bit | Khoảng 112 bit |
| RSA-3072 | Modulus 3.072 bit | Khoảng 128 bit |
| ECDSA/ECDH trên P-256 | Tham số đường cong cỡ 256 bit | Khoảng 128 bit |

Các số cuối là **ước lượng cổ điển, phụ thuộc giả định và hướng dẫn mật mã**; không phải cam kết tuyệt đối cho mọi hệ thống, đặc biệt khi có lỗi triển khai, kênh kề, hoặc mô hình máy tính lượng tử. **RSA-2048 không có “bảo mật 2.048 bit”.** Để chọn thuật toán và kích thước khóa cần xét mục tiêu bảo mật, thời gian bảo vệ dữ liệu, chuẩn giao thức và quy định hiện hành.

### 2.4. Độ dài vật liệu khóa và entropy là hai câu hỏi khác

**Entropy** đo độ khó đoán nguồn sinh khóa. Một mảng 32 byte bất kỳ không tự động có 256 bit entropy: 32 byte từ `SecureRandom` được dùng phù hợp là một chuyện; 32 ký tự lặp lại từ mật khẩu yếu là chuyện khác.

- Khóa ngẫu nhiên: dùng nguồn số ngẫu nhiên an toàn, ví dụ `KeyGenerator` hoặc `SecureRandom` của Java theo yêu cầu thuật toán.
- Khóa sinh từ mật khẩu: dùng password KDF phù hợp, kết hợp **salt**, cấu hình chi phí và quản lý khóa; không cắt/đệm chuỗi mật khẩu thành 16 hoặc 32 byte rồi gọi đó là AES-128/AES-256 an toàn.
- KDF có thể cho phép **độ dài đầu ra cấu hình được**. Ví dụ tham số `keyLength` của `PBEKeySpec` là **bit**, trong khi `salt` là **byte[]** và `iterations` là **số vòng lặp**; những con số này không cùng đơn vị.
- Một khóa được “kéo dài” bằng KDF không tự có entropy nhiều hơn mật khẩu đầu vào; độ dài vật lý và mức khó đoán phải được đánh giá riêng.

## 3. Độ dài đầu ra: digest, MAC, tag, ciphertext và encoded text

**Độ dài đầu ra** phải luôn kèm tên thao tác: đầu ra của hash, MAC, signature, encryption hay serialization. Mỗi thao tác có công thức hoặc cấu hình riêng.

### 3.1. Hash/digest: kích thước đầu ra được thuật toán quy định

| Thuật toán hash | Digest nhị phân | Biểu diễn hex thường gặp | Base64 chuẩn có padding |
| --- | ---: | ---: | ---: |
| SHA-256 | 256 bit = **32 byte** | 64 ký tự ASCII | 44 ký tự ASCII |
| SHA-384 | 384 bit = **48 byte** | 96 ký tự ASCII | 64 ký tự ASCII |
| SHA-512 | 512 bit = **64 byte** | 128 ký tự ASCII | 88 ký tự ASCII |
| SHA3-256 | 256 bit = **32 byte** | 64 ký tự ASCII | 44 ký tự ASCII |

Hash nhận đầu vào có độ dài thay đổi nhưng trả digest kích thước cố định theo thuật toán. `MessageDigest.getInstance("SHA-256").digest(bytes)` trả **mảng 32 byte**. Kích thước digest **không phụ thuộc số byte của thông điệp đầu vào**; dữ liệu 3 byte hay 3 GB đều tạo digest SHA-256 dài 32 byte.

**SHA-256 có đầu ra 256 bit không có nghĩa “chống va chạm 256 bit”**. Với hash lý tưởng 256 bit, chống va chạm tổng quát chịu giới hạn birthday khoảng **2^128 phép thử**, trong khi tìm tiền ảnh tổng quát khoảng **2^256**. Độ dài digest là kích thước dữ liệu; các mục tiêu chống tấn công phải nêu rõ loại tấn công.

Đừng nhầm **block size của hàm nén SHA-256** (512 bit = 64 byte mỗi khối nội bộ) với **digest size** (256 bit = 32 byte). Tên SHA-256 nói tới kích thước đầu ra, không phải kích thước khóa (SHA-256 không dùng khóa).

### 3.2. HMAC: độ dài khóa và độ dài tag độc lập

**HmacSHA256** dùng SHA-256 trong cơ chế MAC. Java `Mac.getInstance("HmacSHA256")` thường tạo **tag 32 byte (256 bit)**, dù khóa HMAC đầu vào có thể dài **16, 32 hoặc 64 byte** nếu đáp ứng yêu cầu thiết kế; **tên “SHA256” không bắt khóa phải dài 256 bit**.

- `SecretKey` cho HMAC là khóa bí mật, thường có số byte do chương trình/giao thức chọn.
- `Mac.getMacLength()` cho biết **độ dài MAC đầu ra tính bằng byte** của instance.
- Một giao thức có thể cắt ngắn tag HMAC theo thông số được phê duyệt; khi đó số byte truyền/lưu **khác** digest đầy đủ. Không tự ý truncate ở cả hai đầu mà không có đặc tả về độ dài tag và mức bảo mật.
- HMAC cung cấp bằng chứng về khóa chung và tính toàn vẹn/xác thực thông điệp, **không mã hóa** nội dung.

Một ví dụ phản chứng: khóa HMAC dài 64 byte không khiến HmacSHA256 xuất ra 64 byte; tag mặc định vẫn **32 byte**. Ngược lại, đổi sang HmacSHA512 đổi kích thước tag đầy đủ thành **64 byte**, nhưng không có nghĩa bắt buộc khóa dài 64 byte.

### 3.3. AES-GCM: phân biệt khóa, nonce, tag và toàn bộ output

Trong ví dụ phổ biến dùng **AES-128-GCM** với **nonce 12 byte** và **tag 128 bit = 16 byte**:

| Thành phần | Ví dụ độ dài | Vai trò |
| --- | ---: | --- |
| AES key | 16 byte = 128 bit | Khóa bí mật |
| GCM nonce/IV | 12 byte = 96 bit | Giá trị cần duy nhất dưới cùng khóa; không phải khóa |
| Plaintext | 5 byte | Dữ liệu đầu vào, ví dụ text “hello” UTF-8 |
| Ciphertext thuần | 5 byte | Phần dữ liệu đã mã hóa trong GCM, không tính tag |
| Authentication tag | 16 byte = 128 bit | Bảo vệ toàn vẹn/xác thực ciphertext và AAD |
| Kết quả `Cipher.doFinal(plaintext)` khi mã hóa với GCM trong JCA thông dụng | **21 byte** | **5 byte ciphertext + 16 byte tag** |
| Nếu tự đóng gói `nonce || ciphertext || tag` | **33 byte** | **12 + 5 + 16**, chưa tính version/metadata khác |

Ở đây **`GCMParameterSpec(128, nonce)` nhận độ dài tag theo bit**, còn `nonce` là `byte[]` dài 12 phần tử. **128 ở `GCMParameterSpec` không chỉ độ dài khóa AES**.

Nếu giao thức lưu nonce bên ngoài, `doFinal()` không tự thêm 12 byte nonce vào output. Phải định nghĩa định dạng lưu/truyền có thể giải mã được, bao gồm version, nonce, ciphertext, tag và dữ liệu AAD cần thiết. GCM không dùng padding kiểu PKCS#5 cho plaintext; ví dụ ở trên minh họa đúng độ dài đối với JCA AES/GCM/NoPadding.

**Cảnh báo về nonce:** nonce 96 bit cần được tạo/quản lý sao cho **không lặp lại với cùng khóa**. Nó thường có thể công khai, nhưng việc lặp nonce với AES-GCM có thể phá nghiêm trọng tính bí mật và tính toàn vẹn. Không dùng độ dài “đủ 12 byte” làm bằng chứng rằng nonce là duy nhất.

### 3.4. Encoding làm tăng số byte hiển thị, không tăng độ mạnh mật mã

Một byte nhị phân bất kỳ có thể không phải ký tự văn bản hợp lệ. Khi cần in/lưu byte khóa, digest hoặc ciphertext dưới dạng text, phải chọn **encoding**; kích thước text sẽ khác mảng nhị phân.

- **Hex:** mỗi byte tạo **2 ký tự ASCII**; `n` byte → **2n ký tự**. Digest 32 byte → 64 ký tự hex.
- **Base64 chuẩn có padding:** `n` byte → **4 × ceil(n / 3)** ký tự ASCII. Digest 32 byte → 44 ký tự, thường kết thúc bằng dấu `=`.
- **Base64URL bỏ padding:** dùng bảng ký tự phù hợp URL và có thể ít ký tự hơn bản có padding. Với 32 byte → **43 ký tự** không padding.
- Chuỗi hex/Base64 chứa ký tự ASCII nên khi mã hóa UTF-8 thường có **1 byte mỗi ký tự**. Tuy vậy **32 byte nhị phân ≠ 32 byte chuỗi Base64**, và số ký tự chưa nói gì về entropy mới.

Hex, Base64 và Base64URL **chỉ biểu diễn byte**, không phải mã hóa để bảo mật hoặc hash. Đừng công khai key chỉ vì nó đã được chuyển sang Base64; không log hex của khóa bí mật trong ứng dụng.

### 3.5. Signature, RSA ciphertext và định dạng container

Một chữ ký RSA với modulus 2.048 bit thường dài **256 byte** ở dạng raw signature. Chữ ký Ed25519 theo đặc tả dài **64 byte**, nhưng các định dạng đóng gói tệp có thể thêm header/chứng chỉ. ECDSA có đầu ra là cặp số `(r, s)`, nên độ dài byte phụ thuộc định dạng raw/DER và quy tắc mã hóa.

Với RSA-OAEP, đầu ra mã hóa (ciphertext) có độ dài bằng số byte modulus, nhưng **kích thước plaintext tối đa** bị giới hạn bởi modulus và padding. Ví dụ RSA-2048 + OAEP dùng SHA-256 làm hash OAEP: **tối đa 190 byte plaintext**, không phải 190 ký tự Unicode.

**Kết luận thực hành của mục này:** cần viết rõ “byte của payload nhị phân”, “bit của khóa”, “byte của digest”, “bit của tag”, “byte của file DER”, “ký tự Base64”, thay vì nói chung “độ dài 256”.

## 4. Java 17+: đo trực tiếp độ dài các loại dữ liệu mật mã

Chương trình sau dùng JCA/JCE của Java để so sánh: UTF-8, SHA-256, hex/Base64, AES-128, AES-GCM và HmacSHA256. Các byte khóa/nonce được sinh ngẫu nhiên nên thay đổi giữa các lần chạy, nhưng **những số đo độ dài được in ra là cố định** đối với cấu hình này.

Lưu đúng tên file **CryptoLengthsDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class CryptoLengthsDemo {
    public static void main(String[] args) throws Exception {
        byte[] utf8 = "Việt".getBytes(StandardCharsets.UTF_8);
        System.out.printf("Text UTF-8: %d bytes = %d bits%n",
                utf8.length, utf8.length * Byte.SIZE);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.printf("SHA-256: %d bytes = %d bits%n",
                digest.length, digest.length * Byte.SIZE);
        System.out.printf("SHA-256 hex: %d characters%n",
                HexFormat.of().formatHex(digest).length());
        System.out.printf("SHA-256 Base64: %d characters%n",
                Base64.getEncoder().encodeToString(digest).length());

        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(128);
        SecretKey aesKey = aesGenerator.generateKey();
        System.out.printf("AES-128 key: %d bytes%n",
                aesKey.getEncoded().length);

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] plaintext = "hello".getBytes(StandardCharsets.UTF_8);
        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);
        System.out.printf(
                "GCM nonce: %d bytes; plaintext: %d bytes; output: %d bytes%n",
                nonce.length, plaintext.length, ciphertextAndTag.length);

        KeyGenerator macGenerator = KeyGenerator.getInstance("HmacSHA256");
        macGenerator.init(256);
        SecretKey macKey = macGenerator.generateKey();
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(macKey);
        byte[] hmac = mac.doFinal(plaintext);
        System.out.printf("HmacSHA256 key: %d bytes; tag: %d bytes%n",
                macKey.getEncoded().length, hmac.length);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên, chỉ rõ UTF-8 cho mã nguồn:

```bash
javac -encoding UTF-8 CryptoLengthsDemo.java
java CryptoLengthsDemo
```

Stdout kỳ vọng (các giá trị độ dài đã được kiểm tra bằng JShell):

```text
Text UTF-8: 6 bytes = 48 bits
SHA-256: 32 bytes = 256 bits
SHA-256 hex: 64 characters
SHA-256 Base64: 44 characters
AES-128 key: 16 bytes
GCM nonce: 12 bytes; plaintext: 5 bytes; output: 21 bytes
HmacSHA256 key: 32 bytes; tag: 32 bytes
```

**Đọc kết quả theo đúng đại lượng:**

1. Chữ “Việt” được biến thành 6 byte UTF-8; đây là **dung lượng biểu diễn** của text, không phải 48 bit độ ngẫu nhiên.
2. SHA-256 digest là 32 byte, nhưng biểu diễn hex là 64 ký tự; Base64 chuẩn là 44 ký tự.
3. `aesGenerator.init(128)` nhận **bit**, còn `aesKey.getEncoded().length` đo **byte**.
4. `GCMParameterSpec(128, nonce)` chỉ **tag 128 bit**; kết quả của `doFinal()` là 5 byte ciphertext cộng 16 byte tag; nonce 12 byte đang được giữ **tách riêng**.
5. Khóa HMAC do ta cố ý sinh dài 256 bit = 32 byte; HmacSHA256 trả tag 32 byte **do thuật toán MAC**, không vì chương trình bắt hai độ dài trùng nhau.

Ví dụ dùng khóa có thể xuất byte từ provider phần mềm phổ biến. Đối với HSM hoặc các khóa không cho xuất, `getEncoded()` có thể trả `null`; khi đó lấy thông số khóa từ API/provider được hỗ trợ thay vì cố dump khóa để kiểm tra size. Không log hoặc gửi mảng khóa ra bên ngoài.

## 5. Java 17+: modulus RSA và kích thước tệp khóa là hai số khác nhau

Ví dụ độc lập này tạo cặp khóa RSA 2.048 bit, đo bit length của modulus rồi kiểm tra xem byte mã hóa X.509/PKCS#8 của key object có lớn hơn byte của modulus không.

Lưu **RsaLengthsDemo.java**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;

public class RsaLengthsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        RSAPublicKey publicKey = (RSAPublicKey) pair.getPublic();
        int modulusBits = publicKey.getModulus().bitLength();
        int modulusBytes = (modulusBits + 7) / 8;

        System.out.printf("RSA modulus: %d bits = %d bytes%n",
                modulusBits, modulusBytes);
        System.out.printf("X.509 encoded public key exceeds modulus: %b%n",
                publicKey.getEncoded().length > modulusBytes);
        System.out.printf("PKCS#8 encoded private key exceeds modulus: %b%n",
                pair.getPrivate().getEncoded().length > modulusBytes);
    }
}
```

```bash
javac -encoding UTF-8 RsaLengthsDemo.java
java RsaLengthsDemo
```

Stdout khi dùng provider JDK thông thường:

```text
RSA modulus: 2048 bits = 256 bytes
X.509 encoded public key exceeds modulus: true
PKCS#8 encoded private key exceeds modulus: true
```

**Tại sao?** `getModulus()` trả số nguyên `n` trong RSA; `bitLength()` đếm số bit cần cho `n`. `getEncoded()` của public key thường chứa SubjectPublicKeyInfo X.509, còn private key thường chứa PKCS#8, bao gồm nhiều giá trị và metadata. **Không dùng `getEncoded().length * 8` để phát biểu độ dài modulus RSA hoặc mức bảo mật.**

Việc sinh cặp khóa RSA ngẫu nhiên có thể mất thời gian tùy môi trường, nhưng số đo modulus trong ví dụ không đổi theo byte ngẫu nhiên. Các biểu diễn DER/PEM và nhà cung cấp khác nhau có thể cho độ dài file khác nhau; vì vậy chương trình **không** hardcode số byte chính xác của tệp khóa. Hãy bảo vệ private key, tránh in nội dung khóa hoặc đưa khóa thực vào tài liệu.

## 6. Cách chọn độ dài khi thiết kế API, lưu trữ và kiểm tra đầu ra

Trước khi tạo schema lưu trữ hoặc truyền dữ liệu, xác định **bốn câu hỏi**:

1. **Đại lượng gì?** Khóa bí mật, IV/nonce, salt, hash, MAC/tag, ciphertext, chữ ký, public key hay chuỗi biểu diễn?
2. **Đơn vị gì?** Bit, byte, số ký tự ASCII, UTF-16 code unit hay Unicode code point?
3. **Định dạng gì?** Raw binary, hex, Base64, Base64URL, DER, PEM, định dạng envelope có header/nonce/tag?
4. **Do ai quyết định kích thước?** Thuật toán cố định, tham số cấu hình, độ dài plaintext, tùy chọn padding hoặc giao thức?

Ví dụ triển khai một trường hợp gửi **32 byte digest SHA-256**:

- Với trường binary, kích thước digest là **32 byte**.
- Với trường text hex, cần chứa **64 ký tự ASCII**.
- Với Base64 chuẩn có padding, cần chứa **44 ký tự ASCII**.
- Nếu lưu thêm id thuật toán, version và separator, phải tính **phần overhead** ngoài digest.
- Không biến SHA-256 thành chuỗi bằng cách gọi `new String(digest, UTF_8)`: digest là dữ liệu binary tùy ý, có thể không phải UTF-8 hợp lệ; dùng `HexFormat` hoặc `Base64` nếu thật sự cần text.

Ví dụ lưu kết quả mã hóa AES-GCM của plaintext 1.000 byte với tag 16 byte và nonce 12 byte: `doFinal` trong cấu hình thông thường trả **1.016 byte**, còn envelope `nonce || ciphertext || tag` yêu cầu ít nhất **1.028 byte** trước khi thêm version, AAD metadata và các trường khác. Nếu đem envelope 1.028 byte này đi Base64 chuẩn, đầu ra thành **4 × ceil(1.028/3) = 1.372 ký tự ASCII**. Mỗi bước thêm **định dạng**, không tự gia tăng độ bảo mật.

### 6.1. Dùng API Java theo đúng đơn vị

| API Java | Giá trị/đơn vị quan trọng | Sai lầm cần tránh |
| --- | --- | --- |
| `Byte.SIZE`, `Byte.BYTES` | 8 bit/byte và 1 byte | Xem `byte` là 1 bit do kiểu tên “byte” |
| `byte[].length` | Số byte | Đọc thẳng thành số bit |
| `String.length()` | Đơn vị mã UTF-16 | Coi là byte UTF-8 hoặc code point |
| `getBytes(UTF_8).length` | Byte của văn bản sau UTF-8 | Không chốt encoding |
| `KeyGenerator.init(128)` cho AES | Kích thước khóa tính bằng **bit** | Truyền 16 vì muốn khóa 16 byte |
| `PBEKeySpec(..., keyLength)` | `keyLength` tính bằng **bit** | Nhầm với `salt.length` tính bằng byte |
| `GCMParameterSpec(128, iv)` | Độ dài authentication tag tính bằng **bit** | Hiểu 128 là số byte IV hoặc key size |
| `MessageDigest.digest(...).length` | Byte của digest thực tế | Nhìn tên SHA-256 rồi ghi 256 byte |
| `MessageDigest.getDigestLength()` | Byte của digest (nếu provider hỗ trợ báo độ dài) | Giả định trả bit |
| `Mac.getMacLength()` | Byte của MAC đầy đủ | Coi đó là độ dài khóa MAC |
| `RSAPublicKey.getModulus().bitLength()` | Bit của modulus RSA | Coi `getEncoded().length` là modulus |
| `Key.getEncoded()` | Byte của định dạng xuất khóa, hoặc `null` | Tự suy ra bit security từ byte encoded |

### 6.2. Quy tắc lưu trữ và giới hạn

- Với dữ liệu cryptographic binary, lưu dưới dạng binary nếu hệ thống cho phép; chỉ encode thành text ở ranh giới thật sự cần thiết (JSON, HTTP header, cấu hình). 
- Nếu lưu digest/hash thành hex, giới hạn cột/tệp theo **độ dài chuỗi đã encode**, không chỉ độ dài digest nhị phân.
- Đầu ra mã hóa phụ thuộc chế độ, padding, tag, overhead và plaintext thực tế. Đừng cấp phát buffer chỉ theo kích thước khóa; dùng API hỗ trợ tính output size hoặc xử lý kết quả `doFinal()` trả về.
- Khi thay đổi cấu hình thuật toán (ví dụ SHA-256 → SHA-512 hoặc tag 96 → 128 bit), kiểm tra schema, serialization và compatibility.
- Dữ liệu khóa nhạy cảm không nên lưu/log dưới dạng hex, Base64 hoặc plaintext; các encoding đó không cung cấp bảo mật.

## 7. Lỗi phổ biến và cách suy nghĩ đúng

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “AES-256 cần `byte[256]`.” | AES-256 cần **256 bit = 32 byte** khóa. |
| “Khóa AES-256 tạo ciphertext cố định 256 byte.” | Key size **không quyết định** độ dài ciphertext; nó phụ thuộc plaintext và chế độ/tag/padding. |
| “RSA-2048 public key luôn là 256 byte.” | **Modulus** thường 256 byte; public key được encode có thêm exponent và metadata. |
| “SHA-256 trả 256 byte.” | Digest SHA-256 là **256 bit = 32 byte**. |
| “Chuỗi hex 64 ký tự nghĩa là digest 64 byte.” | 64 ký tự hex biểu diễn **32 byte** binary. |
| “HmacSHA256 buộc key phải đúng 32 byte.” | Key size và tag size là hai đại lượng riêng; tag đầy đủ HmacSHA256 là **32 byte**. |
| “Tag GCM 128 nghĩa là nonce 128 byte.” | `GCMParameterSpec(128, nonce)` có tag **128 bit = 16 byte**; nonce được truyền bằng mảng byte riêng. |
| “Dùng Base64 làm khóa mạnh hơn.” | Base64 chỉ biến đổi biểu diễn; entropy không tăng. |
| “32 byte mật khẩu tự có 256 bit bảo mật.” | Độ mạnh phụ thuộc cách sinh/mật khẩu và KDF, không chỉ số byte. |
| “`String.length()` là byte length của request.” | Nó đếm UTF-16 code units; cần encode thành byte trước khi đo. |

## 8. Bài tập tự kiểm tra

**Câu 1.** KeyGenerator AES cần khóa 192 bit. Mảng byte xuất của khóa AES thông thường dài bao nhiêu?  
**Đáp án:** **24 byte**. Trong Java dùng `aesGenerator.init(192)`, không dùng `init(24)`.

**Câu 2.** SHA-512 băm một file 8 GB. Kết quả digest dài bao nhiêu, nếu chuyển sang hex thì dài bao nhiêu?  
**Đáp án:** **64 byte digest**; **128 ký tự hex**. Dung lượng file không đổi độ dài digest.

**Câu 3.** Một MAC HmacSHA256 dùng khóa 48 byte và không cắt tag. Dự kiến tag dài bao nhiêu?  
**Đáp án:** **32 byte**. Kích thước key 48 byte không biến tag SHA-256 thành 48 byte.

**Câu 4.** AES-GCM mã hóa 20 byte plaintext, dùng tag 128 bit và lưu nonce 12 byte bên cạnh bản mã. Cần bao nhiêu byte cho `nonce || ciphertext || tag` trước header?  
**Đáp án:** **12 + 20 + 16 = 48 byte**. Phần `Cipher.doFinal()` của ví dụ JCA là **36 byte** (ciphertext + tag), chưa chứa nonce.

**Câu 5.** Chuỗi Base64 dài 44 ký tự có chắc chắn giải mã ra đúng 44 byte không?  
**Đáp án:** **Không.** Base64 mang 6 bit dữ liệu mỗi ký tự và có thể có padding; ví dụ 32 byte binary tạo **44 ký tự Base64 chuẩn**. Cần decode để biết byte thực.

**Câu 6.** RSA-2048 có modulus 256 byte; tại sao `publicKey.getEncoded().length` có thể lớn hơn 256?  
**Đáp án:** Vì đó là **định dạng khóa công khai được đóng gói** với exponent, cấu trúc ASN.1 và thông tin thuật toán, không chỉ raw modulus.

**Câu 7.** Một biến `String` có 4 đơn vị mã UTF-16 thì chắc chắn có 4 byte UTF-8?  
**Đáp án:** **Không.** Các code point có thể dùng nhiều byte UTF-8. Chuỗi “Việt” trong ví dụ có 4 đơn vị mã UTF-16 nhưng 6 byte UTF-8.

### Ghi nhớ khi đọc đặc tả

**Luôn ghi kèm “của cái gì” và “đơn vị gì”:** *AES key 256 bit*, *GCM tag 128 bit*, *nonce 12 byte*, *SHA-256 digest 32 byte*, *hex digest 64 ký tự*, *RSA modulus 2.048 bit*, *RSA public key DER dài bao nhiêu byte*. Độ dài vật lý, độ dài sau encoding, độ mạnh bảo mật và entropy là các khái niệm riêng; muốn chọn kích thước đúng cần nhận diện cả bốn.
