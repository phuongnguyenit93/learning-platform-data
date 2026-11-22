# 8.8 Cấu hình OAEPParameterSpec, digest, MGF1 và label thống nhất giữa hai phía

## Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích tại sao RSA-OAEP cần **bộ tham số thống nhất** chứ không chỉ thống nhất “RSA, SHA-256”.
2. Phân biệt **OAEP digest**, hàm tạo mặt nạ **MGF1**, **digest bên trong MGF1** và **label (PSource.PSpecified)**.
3. Sử dụng **javax.crypto.spec.OAEPParameterSpec** trong Java 17+ để quy định tường minh cả ba phần, thay vì trông chờ mặc định theo tên transformation hoặc provider.
4. Thực hiện Java 17 RSA-OAEP encrypt/decrypt, kiểm tra cấu hình có hiệu lực, quan sát lỗi khi sai digest, MGF1 digest hoặc label.
5. Thiết kế hợp đồng tương tác Java ↔ Java hay Java ↔ hệ thống khác, xử lý giới hạn kích thước RSA và đưa RSA-OAEP vào mô hình **hybrid encryption** an toàn.

**Điểm nhớ chính:** Hai bên chỉ giải mã RSA-OAEP tương thích nếu **khóa RSA đúng, OAEP hash đúng, MGF đúng, MGF1 hash đúng, label giống hệt từng byte**, đồng thời thống nhất kích thước khóa và định dạng ciphertext. Riêng chuỗi transformation có tên SHA-256 **không đủ để khẳng định MGF1 cũng dùng SHA-256** trên mọi provider.

## 1. Vì sao RSA phải có OAEP?

RSA là thuật toán khóa công khai: bên mã hóa dùng **public key** của người nhận, bên giải mã dùng **private key** tương ứng. RSA nguyên thủy không thể dùng trực tiếp cho dữ liệu ứng dụng với một kiểu “RSA encrypt(raw message)” tùy ý. Việc mã hóa an toàn cần **cơ chế encoding/padding được thiết kế cho RSA encryption**.

**RSAES-OAEP (Optimal Asymmetric Encryption Padding)** là lược đồ mã hóa RSA có ngẫu nhiên hóa theo PKCS #1 / RFC 8017. Nó kết hợp:

- Chuỗi byte thông điệp đầu vào M.
- Một **hash OAEP** dùng trong quá trình cấu trúc khối dữ liệu (đặc biệt tính hash của label).
- Một **mask generation function**, thường là MGF1, với thuật toán hash riêng của MGF1.
- Một label L (có thể rỗng).
- Một seed ngẫu nhiên bên trong OAEP.

Bản mã RSA-OAEP khác nhau giữa các lần mã hóa ngay cả khi public key và plaintext không đổi, bởi OAEP dùng ngẫu nhiên. Người gửi không cần private key để mã hóa; người nhận phải có private key để giải mã.

~~~text
Bên A / Sender                                 Bên B / Recipient

Public key của B                               Private key của B
Plaintext M                                    Ciphertext C
OAEP params P                                  OAEP params P
      |                                              |
  RSAES-OAEP encrypt                               RSAES-OAEP decrypt
      |                                              |
      +---------------- C ------------------------->+
                                                     |
                                               M hoặc lỗi giải mã

P = (OAEP hash, MGF=MGF1, MGF1 hash, label bytes)
~~~

Bên mã hóa và bên giải mã phải dùng **cùng OAEP params P**, nhưng key khác vai trò: public key phía mã hóa, private key phía giải mã.

**Không nhầm OAEP với chữ ký số:** RSA-OAEP là lược đồ **mã hóa** cho người nhận. Bất kỳ ai có public key cũng có thể mã hóa thông điệp cho người nhận; OAEP không tự chứng minh danh tính người gửi. RSA-PSS là cơ chế **chữ ký số** khác, cũng có MGF1 nhưng dùng **PSSParameterSpec**, không phải OAEPParameterSpec.

## 2. Bốn trường quan trọng trong OAEPParameterSpec

Trong Java, class **javax.crypto.spec.OAEPParameterSpec** nhận bốn đối số:

~~~java
new OAEPParameterSpec(
    String mdName,               // Hash chính của OAEP
    String mgfName,              // Tên MGF, thường "MGF1"
    AlgorithmParameterSpec mgfSpec, // Digest bên trong MGF1
    PSource pSrc                 // Label, thường PSource.PSpecified
);
~~~

Đây là chữ ký constructor mang tính giải thích, không phải chương trình độc lập. Để dùng thật, cần đối tượng, import phù hợp và truyền spec cho **Cipher.init(...)**.

| Tham số | Ý nghĩa | Ví dụ tường minh |
| --- | --- | --- |
| **mdName** | Hash chính trong thuật toán OAEP, dùng để tạo lHash của label và xác định độ dài hLen | "SHA-256" |
| **mgfName** | Thuật toán sinh mặt nạ; với lược đồ phổ biến là MGF1 | "MGF1" |
| **mgfSpec** | Tham số của MGF1, thường **MGF1ParameterSpec** chứa hash mà MGF1 dùng | MGF1ParameterSpec.SHA256 |
| **pSrc** | Nguồn encoding input P, trong trường hợp thông thường là **PSpecified(label bytes)** | new PSource.PSpecified(labelBytes) |

### 2.1 OAEP digest và MGF1 digest là **hai lựa chọn riêng**

Ví dụ:

~~~java
OAEPParameterSpec p = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    PSource.PSpecified.DEFAULT
);
~~~

Ở đây:

- OAEP hash = **SHA-256**.
- MGF = **MGF1**.
- MGF1 hash = **SHA-256**.
- Label = **byte[0]** (rỗng).

Cũng có cấu hình OAEP hash = SHA-256 nhưng MGF1 hash = SHA-1. Hai cấu hình này **không tương thích để giải mã bản mã của nhau**, dù cùng được mô tả lỏng lẻo là “RSA OAEP SHA-256”.

Đừng suy luận MGF1 digest bằng cách nhìn mỗi tên **OAEPWithSHA-256AndMGF1Padding**. Tên đó nêu hash OAEP và tên MGF, nhưng **không ghi rõ hash nội bộ của MGF1**.

**Cấu hình tương thích cần chỉ ra cả hai hash độc lập.** Việc dùng cả hai là SHA-256 là một lựa chọn nhất quán thường dùng cho hệ thống mới khi hai phía đều hỗ trợ, nhưng yêu cầu cao nhất vẫn là thỏa thuận theo giao thức và xác minh thực tế.

### 2.2 OAEPParameterSpec.DEFAULT có ý nghĩa gì?

Java SE 17 mô tả **OAEPParameterSpec.DEFAULT** là:

~~~text
OAEP digest = SHA-1
MGF         = MGF1
MGF1 digest = SHA-1
PSource     = PSpecified.DEFAULT = empty byte[]
~~~

Đây là **giá trị mặc định của object OAEPParameterSpec.DEFAULT**, không phải lời khẳng định rằng mọi transformation Java đều dùng các giá trị này khi không có params. Provider và transformation có thể áp dụng các mặc định riêng.

Với dịch vụ mới, **không nên lựa chọn SHA-1 chỉ vì nó là default trong spec**. Hãy thiết kế rõ thuật toán được phép và dùng các thông số an toàn phù hợp yêu cầu hiện tại, ví dụ SHA-256/MGF1-SHA-256.

Nguồn: [Oracle Java SE 17 — OAEPParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html).

### 2.3 “ECB” trong RSA transformation không có nghĩa là block mode ECB của AES

Java JCA có tên transformation phổ biến:

~~~text
RSA/ECB/OAEPPadding
RSA/ECB/OAEPWithSHA-256AndMGF1Padding
~~~

Đối với RSA trong các tên này, **ECB** là phần quy ước tên mode của API, không phải khuyến nghị dùng AES-ECB hoặc kiểu chia dữ liệu thành khối ECB. RSA-OAEP xử lý một thông điệp có kích thước bị giới hạn theo RSA modulus. Không dùng quy tắc ECB của mật mã khối để suy ra tính an toàn hoặc cách stream RSA.

Khi viết code có tính tương tác, có thể chọn **RSA/ECB/OAEPPadding** với OAEPParameterSpec tường minh. Vấn đề quyết định là **bộ tham số thực tế đã truyền vào Cipher.init**, hỗ trợ của provider và kiểm tra giao tiếp giữa hai bên.

## 3. MGF1 là gì và tại sao hash của nó quan trọng?

**MGF (Mask Generation Function)** sinh byte mặt nạ từ seed và độ dài yêu cầu. **MGF1** dùng một hàm hash để tạo mặt nạ có độ dài tùy yêu cầu theo cách được quy định trong PKCS #1.

Ở mức trực giác:

~~~text
MGF1(seed, length, Hash)
            |
    Hash(seed || counter0)
    Hash(seed || counter1)
    Hash(seed || counter2)
            |
  Nối byte rồi lấy đúng độ dài yêu cầu
            |
         mask bytes
~~~

Đây chỉ là sơ đồ khái niệm; ứng dụng không tự lập trình lại MGF1. **java.security.spec.MGF1ParameterSpec** mô tả hash cho MGF1, chẳng hạn **MGF1ParameterSpec.SHA256**.

Sự khác nhau giữa OAEP hash và MGF1 hash là **thành phần giao thức thực**, không phải cách viết khác của cùng tham số:

| Cấu hình | OAEP hash | MGF1 hash | Label |
| --- | --- | --- | --- |
| P1 | SHA-256 | SHA-256 | rỗng |
| P2 | SHA-256 | SHA-1 | rỗng |
| P3 | SHA-256 | SHA-256 | bytes UTF-8 của "app:v1" |
| P4 | SHA-256 | SHA-256 | bytes UTF-8 của "app:v2" |

**P1, P2, P3, P4 là các cấu hình khác nhau**; ciphertext tạo dưới một cấu hình thường không giải mã thành công dưới cấu hình khác. Điều này là cơ chế kiểm tra đúng của OAEP, không phải lỗi thư viện.

Khi hai bên trao đổi yêu cầu kỹ thuật, phải ghi rõ **mgfDigest**, không chỉ “MGF1”.

Nguồn: [Oracle Java SE 17 — MGF1ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html).

## 4. Label OAEP: PSource.PSpecified và việc thống nhất từng byte

### 4.1 Label là gì?

Trong RSAES-OAEP, **label L** là chuỗi byte tùy chọn được kết hợp vào phép encoding. OAEP hash tính **lHash = Hash(L)** và đưa vào cấu trúc được kiểm tra khi giải mã. Vì vậy nếu label phía giải mã khác label phía mã hóa, kiểm tra cấu trúc OAEP sẽ thất bại.

Java dùng **PSource.PSpecified**:

~~~java
byte[] label = "app:v1".getBytes(StandardCharsets.UTF_8);

OAEPParameterSpec params = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(label)
);
~~~

Đây là đoạn minh họa, cần import các class tương ứng; xem chương trình Java đầy đủ ở phần sau.

Mặc định:

~~~java
PSource.PSpecified.DEFAULT
~~~

tương ứng **label rỗng (byte[0])**. Nó **không** phải chuỗi text "DEFAULT", không phải chuỗi có một ký tự null và không phải mật khẩu bí mật.

### 4.2 Label phải giống **byte**, không chỉ giống chữ nhìn thấy

Ví dụ:

~~~text
UTF-8("app:v1")   = 61 70 70 3a 76 31
UTF-8("app:v2")   = 61 70 70 3a 76 32
UTF-8("app:v1 ")  = 61 70 70 3a 76 31 20
empty label       = (0 byte)
~~~

Chỉ cần khác một byte, kết quả OAEP của hai bên đã không tương thích.

Nếu label có Unicode, cần thống nhất **charset** (thường UTF-8), quy tắc normalization, khoảng trắng, chữ hoa/thường và định dạng. Một chuỗi nhìn giống nhau có thể có biểu diễn Unicode khác, dẫn đến **label bytes khác**.

**Đừng dùng default charset qua getBytes() không tham số** hoặc để một bên mã hóa label thành UTF-8, bên còn lại dùng UTF-16. Đừng tự trim/canonicalize một phía mà không quy định ở phía kia.

### 4.3 Label có phải secret hoặc AAD giống AES-GCM không?

**Không.** Label là tham số công khai của phép OAEP; không phải khóa hay bí mật. Nó tạo một ràng buộc giữa bản mã và chuỗi byte đã chọn, nhưng không chứng minh người gửi và **không cung cấp thay thế cho cơ chế xác thực bản tin/metadata của toàn ứng dụng**.

Đặc biệt:

- Label không mã hóa riêng bất kỳ nội dung nào.
- Label không chứng minh danh tính tác giả ciphertext; ai có public key và biết label đều có thể mã hóa.
- Label khác nhau khiến giải mã thất bại, nhưng không tự ngăn phát lại một ciphertext cũ hợp lệ.
- Với hybrid encryption, **AES-GCM AAD** bảo vệ metadata của payload theo thiết kế tương ứng; OAEP label không tự bảo vệ tất cả trường metadata của gói dữ liệu ứng dụng.
- **RFC 8017 mô tả trường hợp label rỗng** theo cấu hình cơ bản và lưu ý các cách dùng label khác nằm ngoài phạm vi sử dụng mặc định của đặc tả. Trong triển khai, chỉ chọn non-empty label khi cả hai thư viện/giao thức đã xác nhận hỗ trợ.

Nếu tích hợp với bên không hỗ trợ custom label, thường phải thỏa thuận **empty label** từ đầu, không tự ý giả định đối phương dùng string label giống phía Java.

Nguồn: [Oracle — PSource.PSpecified](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PSource.PSpecified.html), [RFC 8017 §7.1](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1).

## 5. Một cấu hình OAEP tường minh, thống nhất

Ví dụ hợp đồng giao tiếp (wire contract) có thể ghi:

~~~text
Protocol:              encrypted-key-v1
Asymmetric algorithm:  RSAES-OAEP
RSA modulus:           2048 bits or stronger by policy
OAEP digest:           SHA-256
MGF algorithm:         MGF1
MGF1 digest:           SHA-256
Label bytes:           61 70 70 3a 76 31 (UTF-8 "app:v1")
Ciphertext encoding:   Base64 (RFC 4648 basic, padded)
Public key wire form:  X.509 SubjectPublicKeyInfo (DER or PEM)
Private key storage:   PKCS#8 or secured keystore/KMS
Error handling:        decryption failure -> reject, no plaintext use
~~~

Đây là **ví dụ hợp đồng do ứng dụng tự định nghĩa**, không phải tiêu chuẩn có sẵn mang tên encrypted-key-v1.

Điểm quan trọng là viết **cả ba phần digest/MGF1/label**, thêm cách biểu diễn byte và định dạng khóa. Nếu bên gửi chỉ truyền “SHA-256” hoặc “OAEP”, người nhận vẫn chưa có đủ thông tin để cấu hình chính xác.

### 5.1 Không để dữ liệu bên ngoài tự áp đặt thuật toán

Một bản ghi có thể chứa metadata như version/keyId để bên nhận chọn cấu hình từ **danh sách đã cho phép**. Nhưng không nên lấy một chuỗi do attacker điều khiển rồi dùng trực tiếp làm tên Cipher transformation hoặc tự chấp nhận mode yếu hơn nếu giải mã thất bại.

Tốt hơn:

1. Server có bảng **version → chính sách thuật toán cố định**.
2. Metadata version chỉ chọn trong các version được hỗ trợ.
3. Key ID được kiểm tra thuộc đúng tenant/người nhận/quyền truy cập.
4. Server từ chối version/algorithm lạ; không thử lần lượt hàng loạt cấu hình đến khi “ra plaintext”.
5. Luân chuyển key và phiên bản có quy trình rõ ràng, không bao giờ hạ cấp sang RSA không OAEP chỉ vì bản mã không giải được.

## 6. Java 17+ hoàn chỉnh: đúng spec, sai MGF1, sai label

Tạo tệp **RsaOaepSpecDemo.java** (lưu UTF-8). Chương trình sinh cặp RSA 2048 bit để minh họa, cấu hình OAEP digest SHA-256, MGF1 digest SHA-256, label **app:v1**, và thử ba cấu hình sai.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import java.util.HexFormat;

import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class RsaOaepSpecDemo {
    private static final String TRANSFORMATION = "RSA/ECB/OAEPPadding";

    private static OAEPParameterSpec spec(String digest,
                                          MGF1ParameterSpec mgfDigest,
                                          String label) {
        return new OAEPParameterSpec(
                digest,
                "MGF1",
                mgfDigest,
                new PSource.PSpecified(
                        label.getBytes(StandardCharsets.UTF_8))
        );
    }

    private static byte[] encrypt(PublicKey key,
                                  byte[] plaintext,
                                  OAEPParameterSpec params)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key, params);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(PrivateKey key,
                                  byte[] ciphertext,
                                  OAEPParameterSpec params)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, params);
        return cipher.doFinal(ciphertext);
    }

    private static boolean rejected(PrivateKey key,
                                    byte[] ciphertext,
                                    OAEPParameterSpec wrongParams)
            throws GeneralSecurityException {
        try {
            decrypt(key, ciphertext, wrongParams);
            return false;
        } catch (BadPaddingException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        OAEPParameterSpec correct = spec(
                "SHA-256", MGF1ParameterSpec.SHA256, "app:v1");

        byte[] message = "demo RSA-OAEP"
                .getBytes(StandardCharsets.UTF_8);

        Cipher sender = Cipher.getInstance(TRANSFORMATION);
        sender.init(Cipher.ENCRYPT_MODE, pair.getPublic(), correct);

        // Đọc tham số hiệu lực sau init để tránh chỉ nhìn tên padding.
        AlgorithmParameters effective = sender.getParameters();
        OAEPParameterSpec actual =
                effective.getParameterSpec(OAEPParameterSpec.class);

        System.out.println("OAEP digest: " + actual.getDigestAlgorithm());
        System.out.println("MGF: " + actual.getMGFAlgorithm());
        System.out.println("MGF1 digest: "
                + ((MGF1ParameterSpec) actual.getMGFParameters())
                        .getDigestAlgorithm());
        System.out.println("Label hex: "
                + HexFormat.of().formatHex(
                        ((PSource.PSpecified) actual.getPSource())
                                .getValue()));

        byte[] ciphertext = sender.doFinal(message);
        byte[] restored = decrypt(
                pair.getPrivate(), ciphertext, correct);

        System.out.println("Round-trip: "
                + Arrays.equals(message, restored));
        System.out.println("Ciphertext bytes: " + ciphertext.length);

        OAEPParameterSpec wrongMgf = spec(
                "SHA-256", MGF1ParameterSpec.SHA1, "app:v1");
        OAEPParameterSpec wrongLabel = spec(
                "SHA-256", MGF1ParameterSpec.SHA256, "app:v2");
        OAEPParameterSpec wrongDigest = spec(
                "SHA-1", MGF1ParameterSpec.SHA256, "app:v1");

        System.out.println("Wrong MGF1 rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongMgf));
        System.out.println("Wrong label rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongLabel));
        System.out.println("Wrong OAEP digest rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongDigest));

        // SHA-256 hLen = 32; RSA-2048 k = 256.
        int maxMessageBytes = 256 - 2 * 32 - 2;
        System.out.println("Max message bytes: " + maxMessageBytes);

        boolean overLimitRejected;
        try {
            encrypt(pair.getPublic(),
                    new byte[maxMessageBytes + 1], correct);
            overLimitRejected = false;
        } catch (IllegalBlockSizeException expected) {
            overLimitRejected = true;
        }
        System.out.println("191 bytes rejected: " + overLimitRejected);

        Arrays.fill(message, (byte) 0);
        Arrays.fill(restored, (byte) 0);
    }
}
~~~

Chạy bằng JDK 17+ với SunJCE/RSA provider hỗ trợ các tham số này:

~~~bash
javac -encoding UTF-8 RsaOaepSpecDemo.java
java RsaOaepSpecDemo
~~~

Stdout dự kiến (những dòng sau không phụ thuộc vào ciphertext ngẫu nhiên):

~~~text
OAEP digest: SHA-256
MGF: MGF1
MGF1 digest: SHA-256
Label hex: 6170703a7631
Round-trip: true
Ciphertext bytes: 256
Wrong MGF1 rejected: true
Wrong label rejected: true
Wrong OAEP digest rejected: true
Max message bytes: 190
191 bytes rejected: true
~~~

Giải thích:

1. **actual.getDigestAlgorithm()** trả SHA-256: kiểm tra hash chính OAEP.
2. **((MGF1ParameterSpec) actual.getMGFParameters()).getDigestAlgorithm()** trả SHA-256: kiểm tra hash **bên trong MGF1**, không suy ra từ transformation.
3. **getPSource()** cho biết label thực tế. **6170703a7631** là hex của byte UTF-8 **app:v1**.
4. Public key mã hóa, private key tương ứng giải mã đúng với **cùng spec** nên Round-trip = true.
5. Cố tình đổi **MGF1 SHA-256 → SHA-1**, **label app:v1 → app:v2** hoặc **OAEP SHA-256 → SHA-1** sẽ khiến giải mã thất bại. Ví dụ bắt BadPaddingException khi padding OAEP không hợp lệ.
6. RSA 2048 có modulus dài **256 byte**, nên ciphertext dài **256 byte**. Với SHA-256 hLen = 32 byte, plaintext tối đa **190 byte**; 191 byte vượt giới hạn cho RSA-OAEP theo cấu hình này.

**Lưu ý kỹ thuật:** chương trình tạo cặp RSA ngẫu nhiên mỗi lần chạy nên ciphertext không cố định; kết quả giải mã thành công/thất bại là kết quả mong đợi của cấu hình. Các provider hỗ trợ OAEP khác nhau có thể ném lỗi hoặc từ chối tham số tại thời điểm init khác nhau. Nếu provider không hỗ trợ spec, đó là vấn đề **tương thích cần kiểm tra**, không phải lý do dùng cấu hình mặc định một cách mù quáng.

### 6.1 Tại sao dùng Cipher.doFinal thay vì tự kiểm tra padding?

**RSAES-OAEP có quy trình decode/kiểm tra cấu trúc và label bên trong implementation**. Ứng dụng dùng Cipher.doFinal để nhận plaintext hoặc lỗi; không tự parse mask/seed, kiểm tra byte cấu trúc rồi xuất chi tiết lỗi ra client.

Lỗi OAEP thường biểu hiện bằng **BadPaddingException** khi giải mã. Tùy provider và đầu vào, có thể có exception khác như InvalidKeyException, InvalidAlgorithmParameterException hoặc IllegalBlockSizeException. Trên hệ thống đối mặt với input không tin cậy:

- Từ chối chung với bản mã không hợp lệ, tránh trả các thông báo chi tiết có thể làm oracle.
- Không thử **RSA/ECB/PKCS1Padding** hoặc **RSA/ECB/NoPadding** để “cứu” một bản mã OAEP sai.
- Không coi byte sai label có thể được sửa bằng trim hoặc thay charset sau khi giải mã.
- Không in private key, raw ciphertext nhạy cảm hoặc plaintext vào log chỉ để debug.
- Giới hạn tài nguyên, xác minh định dạng ciphertext và quyền truy cập key trước khi giải mã.

### 6.2 Vì sao chương trình không in ciphertext?

OAEP dùng ngẫu nhiên nên ciphertext của cùng M vẫn khác nhau giữa các lần mã hóa. In ciphertext như một giá trị mẫu rồi bảo người học mong đợi đúng từng byte sẽ không đáng tin. Ví dụ thay bằng **độ dài** và những phép kiểm tra bất biến.

Ngoài ra, **Arrays.fill()** chỉ xóa mảng byte do code quản lý, không đảm bảo xóa mọi bản sao dữ liệu trong JVM. Khóa ví dụ được tạo trong chương trình; ứng dụng thật cần keystore, KMS/HSM và chính sách bảo vệ private key.

## 7. Giới hạn kích thước: RSA-OAEP không dùng để mã hóa file lớn

Theo RFC 8017, với RSAES-OAEP:

~~~text
mLen <= k - 2*hLen - 2

mLen = độ dài plaintext (byte)
k    = độ dài RSA modulus (byte)
hLen = độ dài output của OAEP hash (byte)
~~~

Nếu dùng OAEP SHA-256, hLen = 32:

| Modulus RSA | k (byte) | Plaintext tối đa với OAEP SHA-256 |
| --- | ---: | ---: |
| 2048 bit | 256 | 190 byte |
| 3072 bit | 384 | 318 byte |
| 4096 bit | 512 | 446 byte |

Đây là **số byte**, không phải số ký tự Java String. Một chuỗi Unicode có thể có độ dài UTF-8 lớn hơn String.length().

**MGF1 digest là một tham số riêng**, nhưng trong công thức giới hạn độ dài ở trên, **hLen là hash chính của OAEP**, không phải output length của MGF1 hash. Thay MGF1 SHA-256 bằng SHA-1 không làm công thức k - 2*hLen -2 chuyển theo MGF1.

RSA-OAEP **không dùng để chia file thành các mảnh RSA độc lập tùy ý**. Mã hóa nhiều khối RSA gây overhead và sai lầm giao thức. Thay vì vậy dùng **hybrid encryption**:

~~~text
1. Tạo ngẫu nhiên một khóa AES (DEK).
2. Mã hóa file / dữ liệu bằng AES-GCM với nonce duy nhất.
3. Mã hóa DEK nhỏ bằng public key RSA-OAEP của người nhận.
4. Lưu/gửi:
   version, keyId, OAEP spec id, wrapped DEK,
   GCM nonce, ciphertext + tag, metadata/AAD theo định dạng.
5. Người nhận:
   xác minh version/định dạng và quyền,
   giải mã DEK bằng RSA-OAEP đúng tham số,
   giải mã + xác thực AES-GCM,
   chỉ công bố plaintext khi tag hợp lệ.
~~~

Trong nhiều hệ thống thực tế, KMS/HSM có thao tác **key wrap/unwrap** hoặc envelope encryption chuyên dụng. Khi có thể, ưu tiên giao thức/thư viện mã hóa đã được đánh giá thay vì tự phát minh định dạng phức tạp. OAEP bảo vệ việc trao đổi khóa AES; AES-GCM bảo vệ payload dữ liệu lớn.

**RSA-OAEP là mã hóa với public key, không phải chữ ký số hoặc xác thực người gửi.** Nếu cần xác thực người gửi, thiết kế chữ ký số, MAC hoặc cơ chế xác thực kênh phù hợp. AES-GCM AAD có thể ràng buộc metadata nhưng không tự xác định danh tính người gửi nếu nhiều bên có cùng khóa.

Nguồn: [RFC 8017 — RSAES-OAEP](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1).

## 8. Liên thông Java ↔ Java và Java ↔ ngôn ngữ khác

### 8.1 Cần thỏa thuận thêm gì ngoài hash?

Khi hai bên nói “OAEP SHA-256”, hãy hỏi rõ:

1. RSAES-OAEP hay cơ chế RSA khác?
2. **OAEP digest** là SHA-256 hay SHA-1?
3. **MGF** có phải MGF1?
4. **MGF1 digest** là SHA-256, SHA-1 hay giá trị khác?
5. **Label** chính xác là bytes nào, hay empty byte[]?
6. **Public key** theo X.509 SubjectPublicKeyInfo, PKCS#1 RSA PUBLIC KEY hay kiểu khác?
7. **Private key** theo PKCS#8, PKCS#1 hay trong HSM/keystore?
8. **Ciphertext** là raw RSA bytes hay Base64/hex của bytes đó? Biến thể Base64 Basic hay URL-safe?
9. **Modulus length** và key ID là gì?
10. Khi lỗi, cách từ chối và không tiết lộ thông tin nội bộ là gì?

**Key encoding không phải OAEP encoding.** OAEP là cấu trúc mã hóa một thông điệp; X.509/PKCS#8/PEM là định dạng lưu/trao đổi khóa; Base64 là biểu diễn byte thành text.

### 8.2 Ví dụ ánh xạ khái niệm giữa hai bên

Giả sử bên A là Java và bên B là một dịch vụ dùng thư viện mật mã khác. Hợp đồng định nghĩa:

~~~text
RSAES-OAEP:
    hashAlgorithm = SHA-256
    mgf = MGF1
    mgf1HashAlgorithm = SHA-256
    label = hex(6170703a7631)

Ciphertext:
    256 raw bytes for RSA-2048
    transferred as Base64 Basic (no line breaks)
~~~

Bên A dùng:

~~~java
new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(
        "app:v1".getBytes(StandardCharsets.UTF_8))
);
~~~

Bên B phải có tham số tương đương: **OAEP hash SHA-256, MGF1(SHA-256), label bytes 6170703a7631**. Cách gọi hàm cụ thể của bên B tùy thư viện, nhưng ý nghĩa byte/thuật toán phải giống.

Chú ý: Có thư viện mặc định **label rỗng**, có thư viện không hỗ trợ label tùy chọn; một số thư viện cấu hình OAEP hash và MGF1 hash bằng **hai tùy chọn riêng**, số khác có mặc định nội bộ. Vì vậy cần **test liên thông thực tế**, không chỉ so sánh tên thuật toán trong tài liệu.

### 8.3 Tại sao không đoán MGF1 theo transformation?

Ví dụ bên Java gọi:

~~~java
Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
~~~

Chuỗi trên **không biểu đạt tường minh MGF1 digest**. Trong một số triển khai SunJCE, transformation kiểu này đã được ghi nhận dùng **MGF1 SHA-1** nếu không có OAEPParameterSpec do caller chỉ định, trong khi một provider khác có thể dùng SHA-256 cho MGF1. Chính sự khác nhau đó làm xuất hiện lỗi “cả hai đều ghi SHA-256 nhưng không giải mã được”.

Cách chắc chắn:

- Tạo **OAEPParameterSpec** với digest SHA-256 và **MGF1ParameterSpec.SHA256** nếu đó là hợp đồng.
- Truyền cùng spec vào **Cipher.init(...)** cho cả encrypt/decrypt.
- Có thể đọc lại **Cipher.getParameters().getParameterSpec(OAEPParameterSpec.class)** sau init để kiểm tra provider thực nhận gì, khi provider hỗ trợ trả về parameters.
- Kiểm thử với một ciphertext cố định được sinh từ phía khác và giải mã ngược lại; test cả sai MGF digest, sai label.
- Nếu phải tương thích hệ thống legacy có MGF1 SHA-1, chọn thông số legacy **một cách tường minh, có version và kế hoạch chuyển đổi**, không để mặc định tình cờ quyết định.

### 8.4 Label null, empty và văn bản có nghĩa khác nhau

Trong một số API ngoại ngữ, **null** có thể được thư viện diễn giải là **empty label**. Nhưng **trong Java**, cách thể hiện rõ nhất để chỉ label rỗng là **PSource.PSpecified.DEFAULT** hoặc một **new PSource.PSpecified(new byte[0])**.

Không truyền một chuỗi văn bản "null" hoặc "DEFAULT" thay cho empty label. Nếu hợp đồng sử dụng label "app:v1", phải chuyển đúng byte UTF-8; không để bên A dùng app:v1 trong khi bên B dùng app:v1 kèm newline.

### 8.5 Chuyển public/private key qua định dạng

Java có thể dùng:

~~~java
// Ví dụ minh họa phụ thuộc vào biến encodedPublic/encodedPrivate.
PublicKey pub = KeyFactory.getInstance("RSA").generatePublic(
    new X509EncodedKeySpec(encodedPublic));

PrivateKey priv = KeyFactory.getInstance("RSA").generatePrivate(
    new PKCS8EncodedKeySpec(encodedPrivate));
~~~

Đây là đoạn minh họa, không phải chương trình độc lập; cần import **java.security.KeyFactory**, **java.security.PublicKey/PrivateKey** và các KeySpec tương ứng.

**X509EncodedKeySpec** là dạng X.509 SubjectPublicKeyInfo được Java hỗ trợ phổ biến; **PKCS8EncodedKeySpec** là PKCS#8. Một số file từ bên thứ ba có nhãn PEM kiểu **BEGIN RSA PUBLIC KEY** hoặc **BEGIN RSA PRIVATE KEY** theo cấu trúc PKCS#1 thay vì SubjectPublicKeyInfo/PKCS#8; không thể tự đưa DER PKCS#1 vào X509EncodedKeySpec hoặc PKCS8EncodedKeySpec rồi mong luôn hoạt động. Cần chuyển định dạng an toàn hoặc dùng parser thích hợp.

Không ghi private key bytes vào log hoặc mã nguồn. Public key cần được xác thực nguồn gốc (certificate, trust store, pinning/management) khi có nguy cơ bị kẻ tấn công thay thế bằng public key của họ.

## 9. Ma trận kiểm thử tương thích OAEP

| Trường hợp | Kỳ vọng |
| --- | --- |
| Đúng keypair, SHA-256, MGF1 SHA-256, cùng label | Giải mã chính xác plaintext |
| Đúng keypair, OAEP SHA-256 nhưng MGF1 SHA-1 phía nhận | Giải mã thất bại |
| Đúng keypair, MGF1 SHA-256 nhưng OAEP hash SHA-1 phía nhận | Giải mã thất bại |
| Đúng hash/MGF1 nhưng label khác một byte | Giải mã thất bại |
| Bên gửi empty label, bên nhận non-empty label | Giải mã thất bại |
| Cùng nhãn text nhưng charset/Unicode normalization khác | Có thể giải mã thất bại do bytes khác |
| Sai private key | Giải mã thất bại |
| Ciphertext bị sửa hoặc cắt | Giải mã thất bại, không dùng plaintext |
| Thông điệp 190 byte, RSA-2048 + OAEP SHA-256 | Trong giới hạn độ dài đầu vào |
| Thông điệp 191 byte, RSA-2048 + OAEP SHA-256 | Từ chối vì quá giới hạn |
| RSA-2048, ciphertext raw | Dài 256 byte |
| Cùng plaintext/key/params được mã hóa hai lần | Ciphertext thường khác nhau do OAEP random seed |
| Public key được đọc bằng sai KeySpec | Cần chuyển định dạng hoặc xử lý lỗi |
| Thuật toán bên nhận không được provider hỗ trợ | Từ chối hoặc chọn provider hỗ trợ theo chính sách; không tự downgrade |

### 9.1 Test liên thông nên chạy theo hai chiều

Đối với hệ thống thực, test không chỉ Java tự mã hóa rồi tự giải mã. Cần:

1. **Java encrypt → B decrypt.**
2. **B encrypt → Java decrypt.**
3. Ciphertext được sinh với **empty label** và với **label quy định** (nếu có).
4. Hai trường hợp có **MGF1 SHA-1 và SHA-256** để xác định rõ mismatch, nhưng chỉ dùng cấu hình legacy khi hợp đồng cho phép.
5. Test key serialization, Base64 decoding và việc truyền byte qua JSON/HTTP không làm biến đổi ciphertext.
6. Test phiên bản cũ/mới của provider và tài liệu hóa provider được hỗ trợ.

Ciphertext OAEP thay đổi do seed ngẫu nhiên nên **không so sánh raw ciphertext của hai lần mã hóa** để chứng minh tương thích. Hãy kiểm tra **plaintext giải mã được và error path**.

### 9.2 Kiểm thử lỗi không tạo oracle

Không trả cho người gọi các phản hồi phân biệt chi tiết “sai MGF1”, “sai label”, “sai OAEP digest”, “sai byte padding” cho từng ciphertext không tin cậy. Một ứng dụng thường trả lỗi giải mã chung; nội bộ ghi log ở mức cần thiết và không tiết lộ key/plaintext. Tránh timing hoặc retry behavior làm lộ manh mối. Chỉ sử dụng OAEP trong giao thức có bảo vệ đầu cuối phù hợp và kiểm soát rate/permission.

## 10. Những lỗi thực tế hay gặp

1. **“OAEPWithSHA-256AndMGF1Padding nghĩa là MGF1 chắc chắn SHA-256.”** Không đủ thông tin; MGF1 digest cần spec tường minh hoặc xác minh qua provider.
2. **“Hai bên chỉ cần cùng OAEP digest.”** Sai: phải cùng MGF algorithm, MGF1 digest và label bytes.
3. **“OAEPParameterSpec.DEFAULT đang dùng SHA-256.”** Sai: Java 17 mô tả DEFAULT dùng SHA-1 cho OAEP lẫn MGF1 và empty label.
4. **“MGF1ParameterSpec.SHA256 tự đổi OAEP digest thành SHA-256.”** Sai: đó là riêng hash dùng trong MGF1; mdName là tham số khác.
5. **“Label có cùng text nhìn thấy thì chắc cùng giá trị.”** Sai: charset, normalization, khoảng trắng, newline đều ảnh hưởng byte.
6. **“PSource.PSpecified.DEFAULT là mật khẩu mặc định.”** Sai: nó là label rỗng, không phải secret.
7. **“Đổi label là cách xác thực người gửi.”** Sai: bất kỳ ai có public key và label đều có thể mã hóa; cần xác thực độc lập.
8. **“Có thể mã hóa một file 1 MB trực tiếp bằng một lần RSA-OAEP.”** Sai: độ dài plaintext bị giới hạn theo k - 2hLen -2; dùng hybrid encryption.
9. **“RSA/ECB nghĩa là nên chia payload thành nhiều block RSA kiểu AES-ECB.”** Sai: không áp dụng cách hiểu đó cho RSA.
10. **“RSA-OAEP có thể thay chữ ký số RSA-PSS.”** Sai: mã hóa với public key khác với ký bằng private key.
11. **“Ciphertext Base64 giải mã được nên RSA padding chắc chắn đúng.”** Sai: Base64 chỉ chuyển text thành byte; RSA-OAEP mới kiểm tra cấu trúc theo key/params.
12. **“Sai label thì cứ thử label rỗng hoặc đổi SHA-1 cho đến khi được.”** Nguy hiểm: dễ tạo downgrade và xóa ranh giới giao thức. Phiên bản cấu hình phải cố định/allowlisted.
13. **“Public key từ người gửi là đáng tin chỉ vì key parse được.”** Sai: nguồn gốc key phải được xác thực để tránh encrypt cho attacker.
14. **“Mã hóa bằng public key là bằng chứng người gửi có private key.”** Sai: public key được công khai.
15. **“Ciphertext RSA-OAEP có độ dài đúng thì chắc hợp lệ.”** Sai: giải mã và kiểm tra OAEP mới xác minh được.
16. **“Chỉ so Java round-trip là đủ để đảm bảo Python/Go/OpenSSL giải mã được.”** Sai: cần test giao tiếp chéo với MGF digest, label, key format và encoding thật.

## 11. Tình huống chẩn đoán

### Tình huống A — Java encrypt thành công, service khác luôn báo OAEP decoding error

Bên Java chỉ ghi “RSA/ECB/OAEPWithSHA-256AndMGF1Padding”, bên kia cấu hình OAEP hash SHA-256 và MGF1 SHA-256. Cấu hình thực tế của Java nếu dùng mặc định có thể không cùng MGF1 hash.

**Cách điều tra:** đọc giá trị OAEPParameterSpec hiệu lực phía Java, kiểm tra MGF1 digest phía B, label bytes, key pair và ciphertext raw. Thiết lập spec tường minh rồi thử ciphertext cross-language theo cả hai chiều.

### Tình huống B — Chuyển label từ rỗng sang “app:v1”

Một nhóm thay PSource.PSpecified.DEFAULT thành label app:v1 nhưng service giải mã vẫn để rỗng. Mọi ciphertext mới sẽ không được giải mã theo cấu hình cũ.

**Cách xử lý:** version protocol/key record và rollout hai phía có kiểm soát. Không dùng random fallback liên tục; nếu thật sự cần hỗ trợ hai version, server chọn theo metadata được phép và kiểm tra quyền/nguồn gốc.

### Tình huống C — Text label có Unicode

Bên A dùng chuỗi tên nghiệp vụ có dấu tiếng Việt và UTF-8, bên B dùng chuỗi nhìn tương tự nhưng Unicode normalization khác. Hash label khác làm OAEP decode fail.

**Cách xử lý:** công bố label dưới dạng **hex/Base64 của bytes chính thức** trong hợp đồng, và dùng nguyên chuỗi byte đó. Nếu label được tạo từ text thì quy định UTF-8 và normalization cụ thể.

### Tình huống D — Muốn mã hóa payload JSON 2 KB bằng RSA-2048

RSA-OAEP SHA-256 chỉ chứa tối đa 190 byte; payload 2 KB vượt giới hạn.

**Cách xử lý:** tạo khóa AES ngẫu nhiên, mã hóa payload bằng AES-GCM, dùng RSA-OAEP mã hóa khóa AES. Định nghĩa và xác thực đầy đủ nonce/AAD/tag/version theo format hybrid.

### Tình huống E — Đối tác chỉ hỗ trợ empty label

Dịch vụ Java muốn dùng label tự chọn, còn thư viện đối tác không hỗ trợ OAEP label khác empty. Không thể chỉ thay đổi một phía rồi hy vọng giải mã được.

**Cách xử lý:** nếu chính sách cho phép, thiết kế giao thức với empty label cho cả hai bên và ràng buộc context ở lớp payload/AEAD phù hợp. Không làm label trở thành cơ chế nhận dạng bí mật hoặc bỏ qua kiểm tra tag khi hybrid decrypt.

## 12. Câu hỏi tự kiểm tra

**1. OAEPParameterSpec có những trường quan trọng nào?**

Hash chính OAEP, tên MGF (thường MGF1), tham số MGF1 bao gồm hash riêng, và PSource biểu diễn label bytes.

**2. SHA-256 OAEP với MGF1 SHA-1 có giống SHA-256 OAEP với MGF1 SHA-256 không?**

Không. Đây là hai bộ tham số OAEP khác nhau và không giải mã tương thích.

**3. Chỉ nhìn transformation RSA/ECB/OAEPWithSHA-256AndMGF1Padding đã biết MGF1 digest chưa?**

Chưa thể kết luận portable. Cần cấu hình MGF1ParameterSpec tường minh và/hoặc đọc lại tham số thực tế từ provider.

**4. OAEPParameterSpec.DEFAULT của Java 17 sử dụng gì?**

OAEP hash SHA-1, MGF1 với SHA-1, label rỗng. Không đồng nghĩa mọi transformation đều dùng các default này.

**5. Label app:v1 dùng UTF-8 có hex gì?**

**6170703a7631**. Label bytes phải đúng y hệt ở hai bên; thêm một dấu cách hoặc newline sẽ làm khác.

**6. Có thể dùng OAEP label như password hoặc chứng minh danh tính người gửi không?**

Không. Label không phải secret, và public key có thể dùng bởi bất kỳ ai để mã hóa.

**7. Với RSA-2048, OAEP SHA-256, giới hạn plaintext là bao nhiêu?**

**190 byte**, vì k = 256 và hLen = 32: 256 - 64 - 2 = 190.

**8. Nếu có dữ liệu 1 MB cần mã hóa cho một người nhận RSA thì sao?**

Dùng hybrid encryption: AES-GCM mã hóa dữ liệu, RSA-OAEP mã hóa khóa AES nhỏ và quản lý metadata/nonce/AAD/tag an toàn.

**9. Nếu sai private key, MGF1 digest hoặc label thì có nên thử RSA/ECB/PKCS1Padding để giải mã được không?**

Không. Cần từ chối hoặc xử lý theo phiên bản giao thức đã cho phép; không fallback sang cơ chế yếu.

**10. Vì sao nên kiểm tra Cipher.getParameters() và làm integration test liên ngôn ngữ?**

Vì tên transformation và mặc định provider có thể không mô tả đủ tham số; các phép thử xác minh cả hash, MGF1, label, key format và ciphertext encoding giữa hai triển khai.

## Kết luận

**RSA-OAEP không được cấu hình chỉ bằng một từ “SHA-256”.** Khi tạo hoặc giải mã ciphertext, phải thống nhất **OAEP digest, MGF algorithm, MGF1 digest, label bytes, RSA key và định dạng truyền**. Trong Java 17+, **OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, new PSource.PSpecified(labelBytes))** là cách diễn đạt rõ ràng. Dùng Cipher.init với tham số đã quy định, xác minh thông số thực tế và thử liên thông giữa hai phía. Nếu ciphertext không giải mã được, hãy xem đó là lỗi phải điều tra theo hợp đồng, **không thay bằng mặc định hoặc hạ cấp cơ chế bảo mật**.
