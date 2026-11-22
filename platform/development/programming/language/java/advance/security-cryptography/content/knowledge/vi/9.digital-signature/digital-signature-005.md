# 9.5. PSSParameterSpec, digest, MGF1 và độ dài salt của chữ ký

## Mục tiêu học tập

Trong Java Cryptography Architecture (JCA), `RSASSA-PSS` là cơ chế **chữ ký số RSA** dùng phép đệm xác suất (Probabilistic Signature Scheme) được chuẩn hóa trong PKCS #1 (RFC 8017). Để hai bên tạo và kiểm tra chữ ký tương thích, chỉ biết “RSA” hoặc “SHA-256” **chưa đủ**: phải thống nhất cả **digest của thông điệp, hàm MGF, digest bên trong MGF1, số byte salt và trailer field**.

Sau bài này bạn có thể:

- Đọc từng trường của `java.security.spec.PSSParameterSpec` và phân biệt **message digest** với **MGF1 digest**.
- Tạo hồ sơ **RSA-PSS SHA-256 / MGF1-SHA256 / salt 32 byte / trailer 1** trên Java 17+.
- Dùng `Signature.getInstance("RSASSA-PSS")`, `setParameter(...)`, `initSign/initVerify`, `update` và `sign/verify` cho một thông điệp byte chính xác.
- Tính giới hạn độ dài salt theo `modulusBits` của RSA và độ dài digest; biết vì sao thay salt length có thể làm xác minh thất bại.
- Chẩn đoán sai khác giữa Java và OpenSSL/JWS/X.509 hoặc giữa các provider; phân biệt RSA-PSS với RSA PKCS#1 v1.5.

Ví dụ dùng khóa RSA 2048 bit tạo **ngay trong tiến trình chỉ để học API**. Trong ứng dụng thực tế, khóa private phải được quản lý an toàn (KeyStore/KMS/HSM theo kiến trúc), nguồn dữ liệu được ký phải có định dạng/canonicalization nhất quán và phải xác minh public key thực sự đáng tin.

## 1. RSA-PSS hoạt động khác chữ ký RSA PKCS#1 v1.5 như thế nào?

Cả hai đều dùng RSA private key để ký và RSA public key để kiểm tra. Sự khác nhau nằm ở **cách encode thông điệp trước phép toán RSA**:

| Thành phần | RSA PKCS#1 v1.5 (thường `SHA256withRSA` trong JCA) | RSASSA-PSS (`RSASSA-PSS` trong JCA) |
| --- | --- | --- |
| Padding/encoding chữ ký | EMSA-PKCS1-v1_5 | EMSA-PSS |
| Tính ngẫu nhiên | Với message/key cố định, chữ ký theo scheme cơ bản là xác định | Thường dùng **salt ngẫu nhiên mới mỗi lần ký** |
| Tham số cần thống nhất | Hash và scheme, cộng quy tắc về key | Hash, MGF, MGF digest, salt length, trailer field và key |
| Khả năng tương thích | Không thể kiểm tra chữ ký PSS bằng verifier v1.5 | Không thể kiểm tra chữ ký v1.5 bằng verifier PSS |
| Ví dụ JCA | `Signature.getInstance("SHA256withRSA")` | `Signature.getInstance("RSASSA-PSS")` rồi `setParameter(PSSParameterSpec)` |

Tên `SHA256withRSA` **không** đồng nghĩa `RSA-PSS với SHA-256`. Bên ký chọn PSS thì bên xác minh cũng phải chọn PSS với cấu hình khớp. Tên như `SHA256withRSAandMGF1` có thể xuất hiện ở provider/thư viện riêng, nhưng không nên dựa vào alias đó cho code JCA độc lập provider; chọn `RSASSA-PSS` và khai báo `PSSParameterSpec` rõ ràng.

**Chữ ký số không phải mã hóa dữ liệu:** `Signature.sign()` tạo chữ ký cho input đã cung cấp; nó **không** giữ bí mật thông điệp. Verify thành công chỉ xác nhận chữ ký phù hợp với public key và message, còn việc public key có thuộc đúng chủ thể/tổ chức hay không là bước quản lý tin cậy khác (chứng chỉ, trust store, pinning, chính sách định danh...).

## 2. Năm trường của `PSSParameterSpec`

Constructor đầy đủ:

```java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256",                   // message digest
        "MGF1",                      // mask generation function
        MGF1ParameterSpec.SHA256,    // digest dùng bên trong MGF1
        32,                          // salt length tính bằng BYTE
        PSSParameterSpec.TRAILER_FIELD_BC
);
```

Đây là snippet; cần import `java.security.spec.PSSParameterSpec` và `java.security.spec.MGF1ParameterSpec`.

| Trường | API getter | Ý nghĩa | Ví dụ SHA-256 PSS |
| --- | --- | --- | --- |
| Message digest | `getDigestAlgorithm()` | Hàm hash dùng để băm **message** và trong encoding EMSA-PSS | `"SHA-256"` |
| MGF algorithm | `getMGFAlgorithm()` | Hàm tạo mask, thường là **MGF1** | `"MGF1"` |
| Tham số MGF | `getMGFParameters()` | Với MGF1: một `MGF1ParameterSpec` chỉ ra digest dùng trong MGF1 | `MGF1ParameterSpec.SHA256` |
| Salt length | `getSaltLength()` | Số **byte** ngẫu nhiên dùng cho mỗi lần PSS encoding khi ký | `32` byte |
| Trailer field | `getTrailerField()` | Mã nhận diện trailer theo PKCS#1; giá trị `1` ứng với trailer octet `0xBC` | `PSSParameterSpec.TRAILER_FIELD_BC` (giá trị 1) |

**Ba nhầm lẫn cần tránh:**

1. `"SHA-256"` và `MGF1ParameterSpec.SHA256` mô tả **hai vai trò hash** khác nhau. Mặc dù nên khớp theo nhiều profile hiện đại, thiết kế PSS về mặt khái niệm không đồng nhất hai trường; verifier cần đọc chính xác **cả hai**.
2. `saltLength=32` có nghĩa **32 byte = 256 bit**, không phải 32 bit. Nó cũng **không phải** độ dài public/private RSA key và không quyết định kích thước chữ ký RSA.
3. `TRAILER_FIELD_BC` là giá trị constructor **1**; đừng truyền số `0xBC` (188) thay cho tham số trailer. Giá trị 1 biểu thị byte đệm cuối `0xBC` theo định nghĩa scheme.

### Cảnh báo về giá trị mặc định

`PSSParameterSpec.DEFAULT` là profile **lịch sử**: message digest `SHA-1`, `MGF1` với `SHA-1`, salt dài **20 byte**, trailer `1`. Constructor ngắn `new PSSParameterSpec(int saltLen)` cũng dựa trên các mặc định SHA-1/MGF1-SHA1, chỉ thay độ dài salt.

Vì vậy, **`new PSSParameterSpec(32)` không tự chuyển thành SHA-256-PSS**. Trong hệ thống mới, hãy tạo constructor năm tham số dựa trên profile bảo mật đã chọn, không phụ thuộc vào `DEFAULT` hoặc việc provider tự chọn giá trị. SHA-1 trong defaults chỉ giúp đọc legacy/API, không phải một đề xuất cho chữ ký mới.

### `MGF1ParameterSpec` không phải chính `MGF1`

`MGF1ParameterSpec.SHA256` là một đối tượng chứa **tên hash dùng để tạo mask**, không tự ký/hashing dữ liệu. `MGF1` (Mask Generation Function 1) sinh mask có độ dài cần thiết từ seed bằng các lần gọi hàm hash với counter. Việc mã hóa PSS dùng mask đó để che phần dữ liệu encoded; digest của MGF1 **không thay thế** message digest mà signer dùng trên message ban đầu.

## 3. Đi sâu vừa đủ vào cơ chế EMSA-PSS

RFC 8017 mô tả encoding trước phép toán RSA với `emBits = modBits - 1` và `emLen = ceil(emBits / 8)`. Với message `M`:

```text
M (message bytes)
   |
   v
mHash = Hash(M)                  Hash = message digest (ví dụ SHA-256)
   |
   +----------- random salt (sLen byte)
   |                 |
   v                 v
M' = 0x00 (8 byte) || mHash || salt
   |
   v
H = Hash(M')                    Cùng message digest của profile PSS
   |
   v
dbMask = MGF1(H, targetLength)  MGF1 dùng digest riêng từ MGF1ParameterSpec
   |
   v
maskedDB = DB XOR dbMask
   |
   v
EM = maskedDB || H || 0xBC      encoded message trước RSA operation
```

Ở bước này `DB` có dạng `PS || 0x01 || salt`, với `PS` là chuỗi byte zero đệm đủ độ dài; một số bit cao của `maskedDB` được điều chỉnh theo `emBits`. Phép toán RSA sau đó biến `EM` thành signature bytes. Bên verify dùng public key lấy lại encoding, tái tạo/kiểm tra mask, trích salt và đối chiếu hash.

Ý nghĩa của từng thành phần:

- **`mHash`:** hash của **chính xác bytes mà signer nhận qua `Signature.update(...)`**.
- **`salt`:** một chuỗi byte được sinh cho mỗi lần PSS ký, không phải salt dùng cho password hashing; có thể làm hai chữ ký của cùng message/key **khác bytes**. Salt được mã hóa trong phần EMSA-PSS mà verifier kiểm tra; không cần truyền salt ở một trường riêng nếu protocol dùng RSASSA-PSS thông thường.
- **`MGF1`:** sinh mask từ `H`; mask không phải key hay IV của một thuật toán mã hóa.
- **`trailer 0xBC`:** marker cuối của encoding; getter/setter Java dùng mã `1`.
- **`RSA key`:** độ dài modulus ràng buộc tổng không gian cho digest, salt và các byte overhead.

Không tự viết lại EMSA-PSS/MGF1/RSA primitive trong ứng dụng. Dùng Java `Signature` và chỉ hiểu cấu trúc để chọn tham số, điều tra lỗi, cấu hình định dạng chữ ký.

## 4. Vì sao signer và verifier phải khớp toàn bộ profile?

Một bên ký với:

```text
algorithm=RSASSA-PSS
messageDigest=SHA-256
MGF=MGF1
mgfDigest=SHA-256
saltLength=32 bytes
trailerField=1
```

Bên xác minh có thể có đúng public key và message nhưng vẫn **không verify** nếu kỳ vọng saltLength=20, MGF1 dùng SHA-1, message digest=SHA-384 hoặc scheme thành `SHA256withRSA`. Với key/type/params hợp lệ và signature không phù hợp, `Signature.verify` thường trả `false`; nếu thuật toán, provider hoặc tham số không được hỗ trợ, có thể ném exception trước hoặc trong verify. Đừng nuốt mọi lỗi thành một lý do duy nhất.

**Khuyến nghị thực hành:** định nghĩa profile tại một nơi có tên rõ ràng (ví dụ `PSS_SHA256_MGF1_SHA256_SALT32`), dùng cùng profile cho signer và verifier, và có test giao tiếp qua hai tiến trình/thư viện. Trong môi trường phải tương thích chuẩn bên ngoài, profile **phải theo chuẩn đó**, không tự chọn số salt tùy ý.

Cách kiểm tra profile trong ứng dụng Java:

```java
AlgorithmParameters params = signer.getParameters();
if (params != null) {
    PSSParameterSpec actual =
            params.getParameterSpec(PSSParameterSpec.class);
    System.out.println(actual.getDigestAlgorithm());
    System.out.println(actual.getSaltLength());
}
```

Snippet dùng `java.security.AlgorithmParameters` và giả định `signer` là `Signature` đã `setParameter`. `Signature.getParameters()` có thể trả `null` nếu implementation không hỗ trợ xuất đối tượng parameters theo API. Vì vậy nếu cần kiểm chứng tuyệt đối cấu hình protocol, giữ bản `PSSParameterSpec` mà code đã truyền vào, dùng test xác minh thực tế và không suy diễn từ `null` rằng provider đã dùng defaults gì.

## 5. Java 17: ký và xác minh RSASSA-PSS với tham số rõ ràng

Lưu toàn bộ mã sau vào **`RsaPssDemo.java`**. Chương trình tạo một key pair RSA 2048 bit (mục đích demo), ký chuỗi `hello PSS` bằng **hai lần `update`**, sau đó xác minh đủ bốn trường hợp: đúng profile, message bị sửa, salt length khác và MGF digest khác.

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssDemo {
    private RsaPssDemo() {}

    private static PSSParameterSpec profile(int saltBytes,
            MGF1ParameterSpec mgfDigest) {
        return new PSSParameterSpec("SHA-256", "MGF1", mgfDigest,
                saltBytes, PSSParameterSpec.TRAILER_FIELD_BC);
    }

    private static boolean verify(PublicKey key, PSSParameterSpec spec,
            byte[] message, byte[] signature) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(key);
        verifier.setParameter(spec);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(2048);
        KeyPair pair = gen.generateKeyPair();

        PSSParameterSpec spec = profile(32, MGF1ParameterSpec.SHA256);
        byte[] first = "hello ".getBytes(StandardCharsets.UTF_8);
        byte[] second = "PSS".getBytes(StandardCharsets.UTF_8);
        byte[] whole = "hello PSS".getBytes(StandardCharsets.UTF_8);
        byte[] modified = "hello Pss".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(pair.getPrivate());
        signer.setParameter(spec);
        signer.update(first);
        signer.update(second);
        byte[] signature = signer.sign();

        PSSParameterSpec actual = signer.getParameters()
                .getParameterSpec(PSSParameterSpec.class);

        System.out.println("modulusBits=" +
                ((RSAPublicKey) pair.getPublic()).getModulus().bitLength());
        System.out.println("signatureBytes=" + signature.length);
        System.out.println("digest=" + actual.getDigestAlgorithm());
        System.out.println("mgf=" + actual.getMGFAlgorithm());
        System.out.println("mgfDigest=" +
                ((MGF1ParameterSpec) actual.getMGFParameters())
                        .getDigestAlgorithm());
        System.out.println("saltBytes=" + actual.getSaltLength());
        System.out.println("verified=" + verify(pair.getPublic(), spec,
                whole, signature));
        System.out.println("modifiedMessageAccepted=" +
                verify(pair.getPublic(), spec, modified, signature));
        System.out.println("wrongSaltAccepted=" +
                verify(pair.getPublic(),
                        profile(20, MGF1ParameterSpec.SHA256),
                        whole, signature));
        System.out.println("wrongMgfAccepted=" +
                verify(pair.getPublic(),
                        profile(32, MGF1ParameterSpec.SHA1),
                        whole, signature));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 RsaPssDemo.java
java RsaPssDemo
```

**Stdout trên JDK 24/OpenJDK provider đã kiểm tra** (các trường hợp verify sai tương ứng có thể bị provider khác từ chối bằng exception khi xử lý tham số thay vì trả `false`):

```text
modulusBits=2048
signatureBytes=256
digest=SHA-256
mgf=MGF1
mgfDigest=SHA-256
saltBytes=32
verified=true
modifiedMessageAccepted=false
wrongSaltAccepted=false
wrongMgfAccepted=false
```

Điểm học tập:

1. `KeyPairGenerator.getInstance("RSA")` và `initialize(2048)` tạo khóa đủ cho ví dụ, và `Signature.getInstance("RSASSA-PSS")` yêu cầu scheme PSS. Bảo mật thực tế còn phụ thuộc kích thước khóa theo chính sách, nguồn ngẫu nhiên, quyền truy cập private key và vòng đời key.
2. `signer.initSign(privateKey)` chọn private key; `setParameter(spec)` thiết lập digest/MGF/salt/trailer. `update(first)` rồi `update(second)` nạp đúng bytes `hello PSS`, không tự chèn dấu phân cách.
3. `signer.sign()` hoàn tất phép ký, sinh salt ngẫu nhiên theo profile; chữ ký có **256 byte** vì modulus RSA là **2048 bit**, **không** phải vì SHA-256 hoặc sLen=32.
4. `verifier.initVerify(publicKey)` + `verifier.setParameter(spec)` + `update(whole)` + `verify(signature)` trả true khi message/key/profile khớp. Hai lần `update` của signer và một lần của verifier tương đương vì **chuỗi bytes** giống nhau.
5. `modifiedMessageAccepted=false` cho thấy sửa `PSS` thành `Pss` làm thông điệp thay đổi. Đây là hiệu ứng trên bytes sau UTF-8, không có “so sánh chữ tương đương” tự động.
6. `wrongSaltAccepted=false`: verifier kỳ vọng **20 byte salt** nhưng signer đã ký với **32 byte**.
7. `wrongMgfAccepted=false`: verifier kỳ vọng MGF1-SHA1 thay vì MGF1-SHA256. Mặc dù message digest vẫn SHA-256, **MGF digest khác** khiến không khớp.
8. `signer.getParameters()` cho biết cấu hình thực tế trên provider của demo. Ví dụ assume provider hỗ trợ trả về `AlgorithmParameters`; nếu gặp `null` trên provider khác, tự lưu spec đã dùng và chẩn đoán theo contract của provider.

**Không được** lưu private key trong source, không in private key để debug, không chấp nhận public key tùy ý do người gửi dữ liệu không đáng tin cung cấp rồi tuyên bố người gửi “hợp lệ”. Demo tạo cả hai key trong cùng tiến trình chỉ nhằm chứng minh luồng API.

## 6. Digest của message và digest của MGF1 khác nhau ở đâu?

`PSSParameterSpec.getDigestAlgorithm()` cho biết hàm hash tính `mHash = Hash(M)` và `H = Hash(0x00... || mHash || salt)`. `MGF1ParameterSpec.getDigestAlgorithm()` cho biết hash dùng **bên trong MGF1** để tạo mask từ `H`.

| Profile | Message digest | MGF | MGF digest | Salt bytes | Ý nghĩa |
| --- | --- | --- | --- | ---: | --- |
| SHA-256 PSS thường dùng | SHA-256 | MGF1 | SHA-256 | 32 | Tương thích profile PS256 trong JOSE khi các quy tắc khác phù hợp. |
| SHA-384 PSS thường dùng | SHA-384 | MGF1 | SHA-384 | 48 | Profile PS384. |
| SHA-512 PSS thường dùng | SHA-512 | MGF1 | SHA-512 | 64 | Profile PS512. |
| SHA-256 + MGF1-SHA1 | SHA-256 | MGF1 | SHA-1 | 32 | Về mặt cấu trúc PSS có thể mô tả; không phải profile PS256 và khả năng hỗ trợ phụ thuộc provider. |
| `PSSParameterSpec.DEFAULT` | SHA-1 | MGF1 | SHA-1 | 20 | Legacy defaults, không nên ngầm dùng cho chữ ký mới. |

Trong nhiều protocol hiện đại, message digest và MGF digest **phải là cùng loại**; ví dụ RFC 7518 định nghĩa **JOSE PS256** là SHA-256 cho cả hai, saltLength=32, trailer theo mặc định PSS, và key RSA ít nhất 2048 bit. Tương tự PS384 dùng 48 byte salt, PS512 dùng 64 byte salt.

**Không có quy tắc “cứ SHA-256 thì Java tự chọn salt 32 byte” khi bạn chỉ gọi `getInstance("RSASSA-PSS")`.** Độ dài salt là **tham số độc lập**, và yêu cầu protocol cần được khai báo đầy đủ. Nếu phải verify một chữ ký có salt dài 20 dù dùng SHA-256, chỉ dùng profile đó khi đúng giao thức/hệ thống legacy và đã xem xét chính sách chấp nhận.

### Có nên tự gọi `MessageDigest` trước khi `Signature.update`?

**Không** khi dùng `Signature.getInstance("RSASSA-PSS")` với `PSSParameterSpec("SHA-256",...)`. `Signature.update(message)` nhận **message bytes**; engine tự thực hiện hash theo profile. Nếu bạn:

```java
byte[] prehashed = MessageDigest.getInstance("SHA-256").digest(message);
signer.update(prehashed);
```

thì signer PSS sẽ hash **32 byte prehashed** như một thông điệp mới; chữ ký đó **không** là chữ ký trực tiếp trên original `message` theo giao thức thông thường. Code trên chỉ là snippet minh họa lỗi (giả định `message` là `byte[]`, `signer` đã init, đã khai báo/catch exception); không dùng trong luồng chuẩn. Đừng “tối ưu” bằng cách prehash vì engine PSS đã bao gồm hash. Một API prehashed chuyên biệt, nếu tồn tại ở provider/protocol, phải tuân thủ contract riêng và không được nhầm với `Signature` RSASSA-PSS thông thường.

## 7. Salt length bị giới hạn bởi digest và RSA modulus

RFC 8017, EMSA-PSS encoding quy định:

```text
modBits = số bit của RSA modulus n
emBits  = modBits - 1
emLen   = ceil(emBits / 8)       // byte của encoded message
hLen    = số byte output của message digest
sLen    = số byte của salt

Yêu cầu cơ bản: emLen >= hLen + sLen + 2
Hay: sLen <= emLen - hLen - 2
```

Ví dụ **RSA modulus 2048 bit**:

- `emBits=2047`, `emLen=256 byte`.
- SHA-256: `hLen=32`, nên **sLen tối đa = 256 - 32 - 2 = 222 byte** về mặt kích thước encoding.
- SHA-512: `hLen=64`, sLen tối đa **190 byte**.
- Khi sLen=32 với SHA-256, còn nhiều khoảng trống padding, và profile **hoàn toàn vừa** vào RSA-2048.

**Salt length tối đa không có nghĩa đó là lựa chọn cần dùng.** Mỗi protocol có thể yêu cầu salt bằng digest length (ví dụ PS256 sLen=32); tăng lên 222 byte không tự làm chữ ký “mạnh hơn 6,9 lần” và có thể phá tương thích. Một số provider hoặc key RSA-PSS có ràng buộc riêng nghiêm hơn giới hạn toán học; luôn kiểm tra trên implementation và protocol thực tế.

Bảng tính nhanh (khóa RSA có modulus đúng số bit ghi):

| RSA modulus | Message digest | hLen | emLen | sLen tối đa theo công thức |
| ---: | --- | ---: | ---: | ---: |
| 1024 bit | SHA-256 | 32 byte | 128 byte | 94 byte |
| 2048 bit | SHA-256 | 32 byte | 256 byte | 222 byte |
| 2048 bit | SHA-512 | 64 byte | 256 byte | 190 byte |
| 3072 bit | SHA-256 | 32 byte | 384 byte | 350 byte |
| 4096 bit | SHA-512 | 64 byte | 512 byte | 446 byte |

Dòng RSA-1024 chỉ để làm **bài toán kích thước**, **không** là khuyến nghị sử dụng RSA-1024 cho chữ ký mới. Dùng RSA key size theo tiêu chuẩn và chính sách đang áp dụng.

### Java tính budget thay vì đoán

Lưu **`PssSaltBudgetDemo.java`**:

```java
import java.security.MessageDigest;

public final class PssSaltBudgetDemo {
    private PssSaltBudgetDemo() {}

    private static int maxSaltBytes(int modulusBits, int hashBytes) {
        if (modulusBits < 2 || hashBytes < 0) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
        int emBits = modulusBits - 1;
        int emLen = (emBits + 7) / 8;
        return emLen - hashBytes - 2;
    }

    public static void main(String[] args) throws Exception {
        int sha256Bytes = MessageDigest.getInstance("SHA-256")
                .getDigestLength();
        int sha512Bytes = MessageDigest.getInstance("SHA-512")
                .getDigestLength();

        System.out.println("SHA256Bytes=" + sha256Bytes);
        System.out.println("RSA2048_SHA256_MaxSalt=" +
                maxSaltBytes(2048, sha256Bytes));
        System.out.println("RSA2048_SHA512_MaxSalt=" +
                maxSaltBytes(2048, sha512Bytes));
        System.out.println("RSA3072_SHA256_MaxSalt=" +
                maxSaltBytes(3072, sha256Bytes));
        System.out.println("salt32FitsRSA2048_SHA256=" +
                (32 <= maxSaltBytes(2048, sha256Bytes)));
        System.out.println("salt223FitsRSA2048_SHA256=" +
                (223 <= maxSaltBytes(2048, sha256Bytes)));
    }
}
```

```bash
javac -encoding UTF-8 PssSaltBudgetDemo.java
java PssSaltBudgetDemo
```

**Stdout:**

```text
SHA256Bytes=32
RSA2048_SHA256_MaxSalt=222
RSA2048_SHA512_MaxSalt=190
RSA3072_SHA256_MaxSalt=350
salt32FitsRSA2048_SHA256=true
salt223FitsRSA2048_SHA256=false
```

Chương trình chỉ thực hiện **phép tính giới hạn encoding từ RFC**, không thử hỗ trợ của provider, không chứng minh algorithm policy nào được chấp nhận và không tạo chữ ký. Với key có sẵn, lấy bit length thực từ `((RSAPublicKey) publicKey).getModulus().bitLength()`, không giả định key luôn có đúng modulus size như mô tả trong cấu hình.

### Điều gì xảy ra khi salt vượt giới hạn?

Với RSA-2048/SHA-256, yêu cầu sLen=223 làm `hLen+sLen+2=257 > emLen=256`. PSS không thể encode thông điệp theo tham số đó; JCA/provider có thể từ chối tại `setParameter`, `initSign` hoặc `sign` bằng exception phù hợp. Đừng giả định duy nhất một loại exception ở mọi provider. Cần **validate sLen** trước khi thử ký, chọn key đủ lớn và profile đáp ứng protocol.

`sLen=0` được chuẩn định dạng PSS cho phép về mặt encoding; khi đó salt rỗng và tính ngẫu nhiên của chính scheme không còn từ salt. Đây không phải mặc định profile PS256/PS384/PS512; chỉ dùng khi một giao thức/chính sách xác định cụ thể, không tùy tiện đặt 0 để được chữ ký có thể so sánh bytes.

## 8. Sử dụng đúng `Signature`: thứ tự gọi và byte đầu vào

Vòng đời một thao tác ký:

```text
Signature.getInstance("RSASSA-PSS")
   |
initSign(privateKey, [SecureRandom])
   |
setParameter(profile phù hợp)
   |
update(messageByteChunk1)
update(messageByteChunk2)
   |
sign() -> signatureBytes
```

Vòng đời xác minh:

```text
Signature.getInstance("RSASSA-PSS")
   |
initVerify(trustedPublicKey)
   |
setParameter(CÙNG profile)
   |
update(CÙNG message bytes theo thứ tự)
   |
verify(signatureBytes) -> true/false hoặc exception
```

Tùy provider, `setParameter` có thể được phép gọi trước `initSign/initVerify` hoặc chỉ sau khi engine được khởi tạo với key; ví dụ bài dùng thứ tự **init trước, setParameter sau** đã chạy trên provider kiểm thử. Với RSA-PSS key có ràng buộc thuật toán sẵn, engine có thể từ chối profile trái ràng buộc của key.

**Một số lưu ý cần nhớ:**

- `Signature.update(...)` **không** tạo chữ ký từng chunk. Nó chỉ tiếp nhận bytes vào thông điệp đang ký/xác minh. Chia `"hello PSS"` thành hai lần update hay một lần update cho cùng bytes thì kết quả xác minh vẫn đúng.
- `Signature.sign()` trả signature bytes có độ dài theo RSA modulus (RSA-2048 là 256 byte), không bằng SHA-256 digest 32 byte hoặc salt 32 byte.
- Mỗi lần ký PSS thường sinh salt mới; **cùng message và key có thể cho chữ ký bytes khác nhau**. Đừng viết test yêu cầu hai signature PSS phải giống byte. Hãy kiểm tra `verify(...) == true` và xử lý sự khác biệt dự kiến của randomness.
- `initSign(privateKey, SecureRandom random)` có overload cho phép cấp RNG; cần CSPRNG phù hợp, tránh seed bằng hằng số hoặc lộ RNG state. Trong code tiêu chuẩn, provider có cơ chế sinh ngẫu nhiên riêng; không tự tạo và đưa salt như tham số ngoài.
- `Signature` có trạng thái mutable và không nên chia sẻ cùng instance giữa nhiều thread/request; mỗi operation dùng instance riêng hoặc quản lý chặt chẽ.
- Khi chuyển `String` thành bytes, chỉ định `StandardCharsets.UTF_8`. Dữ liệu JSON/XML cần protocol đảm bảo **chuỗi bytes đã chuẩn hóa** giống nhau; ký JSON nguyên gốc rồi verify JSON được sắp xếp/serialize lại có thể làm verify false dù “nội dung logic” tương đương.
- Khi xác minh, public key phải được chọn theo **nguồn tin cậy**; không tin tên thuật toán hoặc đường dẫn key do input không tin cậy yêu cầu. Kiểm tra metadata key/algorithm và chính sách chấp nhận từ cấu hình/định danh đáng tin.

## 9. Liên thông chuẩn JOSE/JWT, X.509 và thư viện khác

### JWS/JWT: PS256 không phải RS256

RFC 7518 `3.5 quy định:

| JWS `alg` | Scheme | Message digest | MGF1 digest | Salt length |
| --- | --- | --- | --- | ---: |
| `PS256` | RSASSA-PSS | SHA-256 | SHA-256 | 32 byte |
| `PS384` | RSASSA-PSS | SHA-384 | SHA-384 | 48 byte |
| `PS512` | RSASSA-PSS | SHA-512 | SHA-512 | 64 byte |
| `RS256` | RSASSA-PKCS1-v1_5 | SHA-256 | Không dùng MGF1 | Không có PSS salt |

Trong JWS, input thực tế được ký là **JWS Signing Input** theo chuẩn (chẳng hạn chuỗi ASCII `BASE64URL(UTF8(protectedHeader)) || "." || BASE64URL(payload)` với các điều kiện `b64` extension tương ứng), không phải tùy tiện đưa JSON đã parse/serialize lại vào `Signature.update`. Nếu áp dụng `PS256`, `PSSParameterSpec` của mục 2 đúng về digest/MGF/salt/trailer, nhưng ứng dụng vẫn phải thực hiện **toàn bộ các quy tắc JWS**, không chỉ gọi raw `Signature` lên phần payload.

**Không để header `alg` chưa tin cậy tự mở quyền chọn scheme/key.** Verifier cần có danh sách thuật toán được phép theo ứng dụng và key cụ thể, không tự động cho phép mọi algorithm do token yêu cầu. Library JWT/JWS có chức năng verify phù hợp sẽ giúp kiểm tra format, key và chính sách; `Signature` trực tiếp thích hợp khi xây giao thức riêng có spec rõ ràng.

### X.509 và thông số được mã hóa

Chữ ký RSASSA-PSS có thể có **algorithm identifier và tham số ASN.1** đi cùng chứng chỉ/cấu trúc giao thức. Java `AlgorithmParameters` có thể xuất thông số PSS từ provider, nhưng những raw `byte[] signature` do `Signature.sign()` trả **không tự chứa mọi trường profile được khai báo trong một header tự mô tả**. Do đó khi truyền chữ ký “thô” cùng file/message, bạn phải định nghĩa/biết trước thuật toán, digest/MGF/saltLen/trailer và khóa tương ứng.

Nếu dùng public key cấu hình cho riêng RSASSA-PSS hoặc certificate có ràng buộc tham số, không được tự đổi digest/salt tùy ý; dùng khóa và thuật toán theo metadata/chính sách được xác minh của chứng chỉ. Không nên tự viết ASN.1 encoder/decoder khi thư viện chuẩn đã có.

### Đối chiếu với OpenSSL

Một bên dùng OpenSSL có thể chọn `rsa_padding_mode:pss`, `rsa_mgf1_md:sha256` và `rsa_pss_saltlen:32` cho RSA-PSS SHA-256. Nếu OpenSSL đang dùng chế độ tự suy salt length (`auto`), max salt hoặc khác chính sách, kết quả có thể không tương thích với verifier yêu cầu đúng saltLength=32. Khi debug, ghi rõ **năm trường profile và độ dài key**, rồi thử verify với test vector đã biết.

Không quy mọi lỗi `verify=false` thành lỗi encoding text. Kiểm tra **cả** input bytes, key, padding mode, digest chính, MGF1 digest, salt length và trailer.

## 10. Checklist chẩn đoán khi chữ ký không xác minh được

| Hiện tượng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Java ký được, OpenSSL/JWS verify false | MGF1 digest hoặc salt length khác | Ghi rõ SHA message/MGF, sLen và protocol profile; đối chiếu ký và verify. |
| `verify=false` dù digest chính cùng SHA-256 | MGF1-SHA1 ở một phía, hoặc sLen 20 vs 32 | Đọc `PSSParameterSpec` và đặt rõ từng trường ở cả hai bên. |
| RSA key đúng nhưng `SHA256withRSA` verify false | PKCS#1 v1.5 khác scheme PSS | Chọn `RSASSA-PSS` và đầy đủ params. |
| `InvalidAlgorithmParameterException` | Provider không chấp nhận profile | Kiểm tra MGF, digest, key constraints và provider. |
| `InvalidKeyException` hoặc `SignatureException` khi ký | RSA key không phù hợp, salt quá dài hoặc key restrictions | Xem modulusBits, emLen/hLen/sLen và thông báo lỗi. |
| `verify=false` chỉ với message có Unicode | Byte/charset/canonicalization khác | So byte input thực trước `Signature.update`; thống nhất UTF-8 và canonicalization. |
| Ký cùng message hai lần cho signature bytes khác | PSS sinh salt ngẫu nhiên | Verify từng chữ ký thay vì so byte signature. |
| Dùng `PSSParameterSpec.DEFAULT` rồi bên ngoài yêu cầu PS256 | DEFAULT dùng SHA-1/MGF1-SHA1/sLen20 | Dùng constructor năm tham số SHA-256/MGF1-SHA256/sLen32/trailer1. |
| Salt length đặt bằng 256 vì “SHA-256 là 256” | Nhầm bit và byte | SHA-256 output 256 bit = 32 byte; sLen=32 cho PS256. |
| Salt length quá lớn với RSA key nhỏ | Không đủ encoding space | Tính `emLen >= hLen+sLen+2`; đổi profile/key theo chuẩn. |
| Lấy `Signature.update(digestBytes)` thay vì message | Engine PSS hash digest như message mới | Đưa original signed-input bytes vào Signature. |
| API trả `getParameters()==null` | Provider không expose AlgorithmParameters | Lưu/kiểm tra spec của ứng dụng và thử interoperability trên provider thật. |
| Verify “đúng” với public key do attacker cung cấp | Chưa xác minh danh tính/key origin | Dùng trust store/certificate chain/chính sách khóa đã được tin cậy. |

**Độ nhạy về lỗi:** khi xử lý chữ ký từ dữ liệu bên ngoài, xử lý input không hợp lệ có kiểm soát. Đừng coi `verify=false` và exception là hai mức “gần đúng” của chữ ký; cả hai đều **không được chấp nhận** nếu chưa được xác minh đầy đủ.

## 11. Bài tập thực hành

1. **Đọc profile:** giải thích từng getter `getDigestAlgorithm`, `getMGFAlgorithm`, `getMGFParameters`, `getSaltLength` và `getTrailerField`. Vì sao `MGF1ParameterSpec.SHA256` không thay thế trường message digest?
2. **Chạy ví dụ:** biên dịch `RsaPssDemo.java`, giải thích vì sao signature có 256 byte trong khi digest và salt đều dài 32 byte.
3. **Thay message:** đổi một chữ cái của `hello PSS` phía verify rồi mô tả kết quả. Giữ nguyên key/profile.
4. **Thay MGF digest:** giữ SHA-256 ở `PSSParameterSpec.getDigestAlgorithm` nhưng đổi MGF1-SHA1 ở verifier; theo RFC và test, vì sao điều này làm chữ ký không khớp? Nếu provider từ chối param khác, đó là lỗi ở bước nào?
5. **Thay sLen:** ký bằng sLen32, verify bằng sLen20. Sau đó ký mới **với cùng sLen20 ở cả hai bên** và giải thích vì sao có thể verify true nhưng không còn là profile JOSE PS256.
6. **Giới hạn encoding:** với RSA-2048/SHA-256, tính emBits, emLen và maxSalt; thử sLen=223 với signer và ghi nhận exception trên provider đang chạy. Đừng dùng tham số vô nghĩa này trong production.
7. **Đổi message digest:** với RSA-2048/SHA-512, tính hLen=64 và maxSalt=190; đề xuất `PSSParameterSpec` tương ứng PS512 (SHA-512, MGF1-SHA512, salt64, trailer1).
8. **Tách chunk:** signer gọi `update("hello ")` và `update("PSS")`, verifier gọi `update("hello PSS")`. Vì sao vẫn verify true? Trường hợp `hello` vs `hello ` khác nhau thế nào?
9. **JWS:** mô tả đủ PS256 và RS256 khác nhau ở đâu, bao gồm message input bytes theo JWS, scheme, MGF và salt length.
10. **Thiết kế API:** phác thảo hàm `verify(byte[] message, byte[] signature, PublicKey trustedKey, PSSParameterSpec approvedProfile)` và nêu vì sao profile phải đến từ chính sách tin cậy, thay vì message chưa xác minh.
11. **Test interoperability:** tạo một test vector qua hai provider/ứng dụng. Ghi metadata algorithm, modulus bit length, hash, mgf, mgf digest, salt length, trailer và chính xác bytes được ký; phân loại từng lỗi `verify=false`/exception.

**Tiêu chí đạt:** bạn tạo được profile PSS rõ ràng, thực hiện `sign/verify` với đúng bytes, phân biệt message digest với MGF1 digest, chọn salt length theo protocol và kiểm tra giới hạn RSA, đồng thời nêu được ít nhất ba nguyên nhân khiến chữ ký PSS không liên thông dù dùng đúng public key.

## Tài liệu chính thức

- [Java SE 17 `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html)
- [Java SE 17 `MGF1ParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html)
- [Java SE 17 `Signature` — `initSign`, `initVerify`, `setParameter`, `update`, `sign`, `verify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [RFC 8017 — PKCS #1 v2.2, `8.1 RSASSA-PSS` và `9.1 EMSA-PSS`](https://www.rfc-editor.org/rfc/rfc8017.html)
- [RFC 7518 3.5 — JWS algorithms PS256, PS384, PS512](https://www.rfc-editor.org/rfc/rfc7518.html)
