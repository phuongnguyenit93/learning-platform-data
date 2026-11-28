# Algorithm parameters

Trong Java Cryptography Architecture (JCA), **algorithm parameters** là các giá trị cấu hình bổ sung mà một thuật toán mật mã cần để thực hiện đúng thao tác. Chúng xác định cách thuật toán vận hành cùng với khóa, chẳng hạn IV hoặc nonce cho mã hóa, salt và số vòng lặp cho dẫn xuất khóa từ mật khẩu, đường cong elliptic cho sinh khóa, hay hash và MGF cho RSA-OAEP.

Tham số thường không phải là khóa bí mật. Tuy nhiên, một số tham số phải được tạo đúng cách, gắn với đúng khóa và lưu lại cùng dữ liệu mật mã để có thể giải mã hoặc xác minh sau này. Ví dụ, AES-GCM cần nonce duy nhất với mỗi khóa; RSA-PSS cần hai phía thống nhất cấu hình hash, MGF, độ dài salt và trailer field.

JCA cung cấp ba abstraction quan trọng: **AlgorithmParameterSpec**, **AlgorithmParameters** và **AlgorithmParameterGenerator**. Hiểu sự khác nhau giữa chúng giúp ứng dụng cấu hình thuật toán rõ ràng, tương thích giữa các provider và tránh những lỗi nghiêm trọng như tái sử dụng nonce hoặc dùng sai tham số padding.

## 1. Tham số thuật toán là gì?

Một phép toán mật mã thường cần nhiều thông tin hơn tên thuật toán và khóa. Có thể mô tả tổng quát:

- **Thuật toán:** xác định cơ chế mật mã, ví dụ AES/GCM, RSA-OAEP hoặc RSASSA-PSS.
- **Khóa:** vật liệu bí mật hoặc cặp khóa được dùng trong phép toán.
- **Tham số:** cấu hình bổ sung mà thuật toán yêu cầu, ví dụ IV, nonce, salt, đường cong hoặc padding parameters.
- **Dữ liệu đầu vào:** plaintext, ciphertext, thông điệp cần ký hoặc dữ liệu cần xác minh.

Ví dụ, AES-GCM sử dụng khóa AES và nonce để mã hóa, đồng thời tạo authentication tag. Khi giải mã, bên nhận cần đúng khóa, đúng nonce, đúng tag và đúng Additional Authenticated Data (AAD) nếu có.

Tham số có thể được công khai cùng ciphertext. IV, nonce và salt thường không cần giữ bí mật; chúng cần được lưu hoặc truyền chính xác để bên nhận tái tạo phép toán. Tính công khai không có nghĩa là có thể tùy ý tái sử dụng hoặc thay đổi chúng.

## 2. Ba API tham số trong JCA

JCA phân chia việc mô tả, lưu biểu diễn và sinh tham số thành ba API.

| API | Vai trò | Cách sử dụng điển hình |
|---|---|---|
| **AlgorithmParameterSpec** | Đối tượng Java có kiểu, chứa tham số để truyền vào engine API | GCMParameterSpec, IvParameterSpec, OAEPParameterSpec |
| **AlgorithmParameters** | Đại diện cho bộ tham số đã được provider mã hóa hoặc diễn giải | Nhận tham số từ Cipher, tuần tự hóa và khôi phục |
| **AlgorithmParameterGenerator** | Sinh bộ tham số cho thuật toán cần tham số được tạo riêng | Sinh tham số miền cho DH hoặc DSA trong các hệ thống tương thích |

Ba API này không thay thế nhau.

- AlgorithmParameterSpec là cách ứng dụng mô tả tham số bằng một lớp Java cụ thể.
- AlgorithmParameters là đối tượng do JCA/provider quản lý, có thể chuyển tham số sang dạng mã hóa để lưu trữ hoặc trao đổi.
- AlgorithmParameterGenerator tạo ra tham số mới. Nó không sinh khóa mật mã.

Trong nhiều tình huống, ứng dụng chỉ cần tạo một AlgorithmParameterSpec rồi truyền vào Cipher, Signature hoặc KeyPairGenerator. Không phải thuật toán nào cũng cần gọi AlgorithmParameters hay AlgorithmParameterGenerator.

## 3. AlgorithmParameterSpec và các lớp thường gặp

**java.security.spec.AlgorithmParameterSpec** là giao diện đánh dấu (marker interface) cho các đối tượng mô tả tham số thuật toán. Những lớp cụ thể thường nằm trong java.security.spec hoặc javax.crypto.spec.

| Lớp tham số | Thông tin được mô tả | Thuật toán / API thường dùng |
|---|---|---|
| **IvParameterSpec** | Initialization Vector (IV) | AES-CBC và một số chế độ cần IV |
| **GCMParameterSpec** | Độ dài authentication tag và IV/nonce | AES-GCM |
| **PBEParameterSpec** | Salt, số vòng lặp và tham số lồng tùy chọn | Các thuật toán Password-Based Encryption |
| **OAEPParameterSpec** | Hash, MGF, tham số MGF và nguồn dữ liệu OAEP | RSA-OAEP |
| **PSSParameterSpec** | Hash, MGF, độ dài salt và trailer field | RSASSA-PSS |
| **MGF1ParameterSpec** | Hash dùng trong MGF1 | OAEP và PSS |
| **ECGenParameterSpec** | Tên bộ tham số đường cong elliptic | KeyPairGenerator cho EC |
| **DHParameterSpec** | Các tham số miền Diffie-Hellman | KeyPairGenerator và KeyAgreement cho DH |
| **ChaCha20ParameterSpec** | Nonce và bộ đếm khối | ChaCha20 |

Tên lớp và khả năng hỗ trợ cụ thể phụ thuộc phiên bản JDK và provider. Cần đối chiếu thuật toán thực tế với API và provider được triển khai.

### 3.1. IV và nonce

IV là giá trị khởi tạo được dùng bởi một số chế độ mã hóa. Nonce là giá trị được thiết kế để chỉ dùng một lần trong một ngữ cảnh nhất định. Trong thực tế, cách gọi có thể khác nhau theo thuật toán, nhưng yêu cầu an toàn phải tuân theo đặc tả của chế độ mã hóa.

Với AES-CBC, IV thường có độ dài bằng kích thước block của AES, tức 16 byte. IV cần được tạo ngẫu nhiên và truyền cùng ciphertext. CBC không tự cung cấp xác thực dữ liệu; nếu dùng CBC, giao thức phải kết hợp cơ chế xác thực an toàn, chẳng hạn Encrypt-then-MAC được thiết kế đúng. Với ứng dụng mới, nên ưu tiên AEAD nếu cần vừa mã hóa vừa xác thực.

Với AES-GCM, nonce 96 bit (12 byte) là lựa chọn phổ biến và được khuyến nghị trong nhiều triển khai. Nonce phải duy nhất đối với cùng một khóa. Tái sử dụng nonce với cùng khóa có thể làm lộ thông tin plaintext và phá vỡ khả năng xác thực của GCM. Sinh nonce ngẫu nhiên không tự bảo đảm duy nhất tuyệt đối; hệ thống có lưu lượng lớn cần chiến lược quản lý nonce có thể kiểm soát và kiểm toán.

### 3.2. Salt và số vòng lặp

Salt là giá trị ngẫu nhiên hoặc duy nhất được thêm vào quá trình dẫn xuất khóa từ mật khẩu. Salt không cần giữ bí mật và thường được lưu cùng kết quả dẫn xuất. Mục đích là làm cho cùng một mật khẩu không tạo ra cùng một khóa dẫn xuất trong các lần sử dụng độc lập, đồng thời chống việc tái sử dụng bảng băm dựng sẵn.

Số vòng lặp (iteration count) điều khiển chi phí tính toán của một số KDF. Giá trị quá thấp làm giảm khả năng chống dò mật khẩu; giá trị quá cao có thể làm tăng tải xử lý và tạo điều kiện từ chối dịch vụ nếu không giới hạn đầu vào. Chọn tham số theo khuyến nghị hiện hành và đo trên phần cứng triển khai.

Không nhầm salt với nonce. Salt dùng trong dẫn xuất khóa; nonce/IV dùng trong phép toán mã hóa hoặc xác thực. Hai giá trị có thể đều công khai nhưng có yêu cầu khác nhau.

## 4. GCMParameterSpec và AES-GCM

**GCMParameterSpec** mô tả độ dài authentication tag và IV của Galois/Counter Mode. Tham số độ dài tag được truyền bằng bit, không phải byte. Ví dụ 128 tương ứng tag 16 byte.

Ví dụ mã hóa AES-GCM:

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmEncryption {
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    private AesGcmEncryption() {
    }

    public static byte[] encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad,
            byte[] nonce) throws GeneralSecurityException {

        if (nonce == null || nonce.length != NONCE_LENGTH) {
            throw new IllegalArgumentException("Nonce phải có 12 byte");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce);

        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);
        cipher.updateAAD(aad);

        // JCA trả về ciphertext kèm authentication tag ở cuối mảng byte.
        return cipher.doFinal(plaintext);
    }

    public static byte[] newNonce() {
        byte[] nonce = new byte[NONCE_LENGTH];
        new SecureRandom().nextBytes(nonce);
        return nonce;
    }
}
~~~

Phương thức encrypt nhận nonce từ bên gọi để làm rõ trách nhiệm quản lý tính duy nhất. Hàm newNonce minh họa cách tạo nonce ngẫu nhiên 12 byte; ứng dụng phải bảo đảm không tái sử dụng nonce với cùng khóa. Với hệ thống có lưu lượng lớn, nên thiết kế cơ chế cấp phát nonce theo khóa và theo phạm vi triển khai để tránh trùng lặp giữa nhiều instance.

AAD là dữ liệu bổ sung được xác thực nhưng không được mã hóa. Có thể dùng AAD cho metadata như định danh bản ghi, tenant, phiên bản định dạng hoặc key ID. Bên giải mã phải cung cấp chính xác cùng AAD. Nếu tag không hợp lệ hoặc AAD khác, doFinal sẽ thất bại, thường bằng AEADBadTagException.

Ví dụ giải mã:

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmDecryption {
    private AesGcmDecryption() {
    }

    public static byte[] decrypt(
            SecretKey key,
            byte[] ciphertextAndTag,
            byte[] aad,
            byte[] nonce) throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters = new GCMParameterSpec(128, nonce);

        cipher.init(Cipher.DECRYPT_MODE, key, parameters);
        cipher.updateAAD(aad);

        return cipher.doFinal(ciphertextAndTag);
    }
}
~~~

Chỉ sử dụng plaintext sau khi doFinal hoàn tất thành công. Với AEAD, dữ liệu giải mã chưa được xác thực không được chuyển cho logic nghiệp vụ. Không xử lý một phần plaintext trước khi xác thực tag thành công.

## 5. IvParameterSpec và chế độ CBC

**IvParameterSpec** chứa byte của IV. Ví dụ sau minh họa khởi tạo AES-CBC:

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public final class AesCbcEncryption {
    private AesCbcEncryption() {
    }

    public static byte[] encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] iv) throws GeneralSecurityException {

        if (iv == null || iv.length != 16) {
            throw new IllegalArgumentException("AES-CBC cần IV 16 byte");
        }

        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new IvParameterSpec(iv)
        );

        return cipher.doFinal(plaintext);
    }
}
~~~

Đoạn mã minh họa cấu hình IV, không phải một thiết kế lưu trữ hoàn chỉnh. IV phải được tạo mới và truyền cùng ciphertext. CBC không xác thực ciphertext; cần có MAC được thiết kế đúng và phải xác minh trước khi sử dụng plaintext. Không nên xây dựng hệ thống mới chỉ dựa trên CBC mà không có cơ chế xác thực. AES-GCM thường phù hợp hơn khi cần mã hóa có xác thực.

## 6. OAEPParameterSpec cho RSA-OAEP

RSA-OAEP là scheme mã hóa bất đối xứng có padding được thiết kế để bảo vệ dữ liệu nhỏ, thường là khóa phiên hoặc khóa dữ liệu. **OAEPParameterSpec** cho phép chỉ định rõ:

- Hash function dùng trong OAEP.
- Mask Generation Function (MGF), thường là MGF1.
- Hash function dùng bên trong MGF1.
- PSource, thường là PSpecified.DEFAULT.

Ví dụ cấu hình RSA-OAEP với SHA-256 và MGF1-SHA-256:

~~~java
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.spec.MGF1ParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class RsaOaepEncryption {
    private RsaOaepEncryption() {
    }

    public static byte[] encrypt(
            PublicKey publicKey,
            byte[] keyMaterial) throws GeneralSecurityException {

        OAEPParameterSpec parameters = new OAEPParameterSpec(
            "SHA-256",
            "MGF1",
            MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT
        );

        Cipher cipher = Cipher.getInstance(
            "RSA/ECB/OAEPWithSHA-256AndMGF1Padding"
        );

        cipher.init(Cipher.ENCRYPT_MODE, publicKey, parameters);
        return cipher.doFinal(keyMaterial);
    }
}
~~~

Cần thống nhất toàn bộ tham số OAEP giữa bên mã hóa và giải mã. Một số provider hoặc cấu hình mặc định có thể dùng hash cho MGF1 khác với hash chính của OAEP. Vì vậy, chỉ dựa vào tên transformation có thể chưa đủ để bảo đảm hai phía có cùng cấu hình; truyền OAEPParameterSpec tường minh giúp tránh phụ thuộc mặc định.

RSA-OAEP có giới hạn kích thước plaintext theo modulus và độ dài hash. Không dùng nó để mã hóa trực tiếp dữ liệu lớn. Trong envelope encryption, hãy tạo khóa dữ liệu đối xứng, mã hóa dữ liệu bằng AEAD, rồi dùng RSA-OAEP hoặc cơ chế bọc khóa được phê duyệt để bảo vệ khóa dữ liệu.

## 7. PSSParameterSpec cho chữ ký RSA-PSS

RSA-PSS là scheme chữ ký số có tham số. **PSSParameterSpec** mô tả hash, MGF, tham số MGF, độ dài salt và trailer field. Các tham số này phải thống nhất giữa bên ký và bên xác minh.

~~~java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssSigner {
    private RsaPssSigner() {
    }

    public static byte[] sign(
            PrivateKey privateKey,
            byte[] message) throws GeneralSecurityException {

        PSSParameterSpec parameters = new PSSParameterSpec(
            "SHA-256",
            "MGF1",
            MGF1ParameterSpec.SHA256,
            32,
            1
        );

        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(parameters);
        signature.initSign(privateKey);
        signature.update(message);

        return signature.sign();
    }
}
~~~

Trong ví dụ, hash chính là SHA-256, MGF là MGF1 dùng SHA-256, salt dài 32 byte và trailer field là 1. Provider phải hỗ trợ bộ tham số này. Phía xác minh cần cấu hình cùng bộ tham số trước khi gọi verify. Không dựa vào giá trị mặc định của provider nếu giao thức yêu cầu tính tương thích rõ ràng.

## 8. ECGenParameterSpec và tham số đường cong

**ECGenParameterSpec** xác định bộ tham số đường cong elliptic bằng tên chuẩn hoặc tên được provider hỗ trợ. Nó thường được truyền cho **KeyPairGenerator** khi sinh khóa EC.

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;

public final class EcParametersExample {
    private EcParametersExample() {
    }

    public static KeyPair generate() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");

        ECGenParameterSpec parameters =
            new ECGenParameterSpec("secp256r1");

        generator.initialize(parameters, new SecureRandom());
        return generator.generateKeyPair();
    }
}
~~~

Tham số đường cong là dữ liệu công khai nhưng phải được lựa chọn theo chính sách và giao thức. Các bên cần dùng bộ tham số tương thích. Không tự tạo đường cong riêng hoặc chấp nhận tham số do đối tác gửi mà không xác thực và kiểm tra hợp lệ.

## 9. PBEParameterSpec, salt và KDF

**PBEParameterSpec** chứa salt và số vòng lặp cho các thuật toán Password-Based Encryption. Một số thuật toán còn cần tham số lồng, được truyền qua constructor có đối số AlgorithmParameterSpec bổ sung.

Cần phân biệt tham số của PBE cipher với tham số của quá trình sinh khóa bằng PBKDF2:

- Khi dùng **SecretKeyFactory** với PBKDF2, lớp **PBEKeySpec** chứa mật khẩu, salt, iteration count và độ dài khóa cần dẫn xuất.
- Khi một thuật toán mã hóa dựa trên mật khẩu cần tham số lúc khởi tạo Cipher, **PBEParameterSpec** có thể được dùng để cung cấp salt và iteration count.
- Salt và iteration count không phải khóa bí mật. Chúng thường được lưu cùng ciphertext hoặc metadata để bên giải mã có thể tái tạo khóa theo cùng quy tắc.

Ví dụ tạo PBEParameterSpec:

~~~java
import java.security.SecureRandom;
import javax.crypto.spec.PBEParameterSpec;

byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);
int iterationCount = 210_000;

PBEParameterSpec parameters =
    new PBEParameterSpec(salt, iterationCount);
~~~

Giá trị iteration trong ví dụ chỉ để minh họa cách truyền tham số, không phải khuyến nghị chung cho mọi KDF hoặc môi trường. Cần chọn số vòng lặp theo thuật toán, hướng dẫn hiện hành và hiệu năng thiết bị. Với password hashing, hãy dùng password hashing/KDF chuyên dụng và tham số được hiệu chỉnh; không tự thay bằng một vòng hash nhanh.

## 10. AlgorithmParameters: biểu diễn và khôi phục tham số

**java.security.AlgorithmParameters** là đối tượng đại diện cho các tham số đã được provider diễn giải. Nó hỗ trợ khởi tạo từ một AlgorithmParameterSpec hoặc từ dạng byte đã mã hóa, sau đó trích xuất lại một spec có kiểu.

Một số phương thức quan trọng:

| Phương thức | Vai trò |
|---|---|
| **getInstance(algorithm)** | Lấy đối tượng AlgorithmParameters cho thuật toán |
| **init(spec)** | Khởi tạo từ AlgorithmParameterSpec |
| **init(encoded)** | Khởi tạo từ dạng tham số đã mã hóa |
| **getParameterSpec(type)** | Lấy lại tham số dưới dạng lớp spec được yêu cầu |
| **getEncoded()** | Lấy biểu diễn byte mặc định |
| **getEncoded(format)** | Lấy biểu diễn theo định dạng được hỗ trợ |
| **getAlgorithm()** | Tên thuật toán tham số |
| **getProvider()** | Provider đang cung cấp triển khai |

Có thể lấy tham số đã dùng từ Cipher thông qua **getParameters()**. Ví dụ, sau khi khởi tạo Cipher cho chế độ có tham số, ứng dụng có thể lưu biểu diễn tham số cạnh ciphertext để phục vụ giải mã.

~~~java
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import javax.crypto.spec.GCMParameterSpec;

public final class ParameterEncoding {
    private ParameterEncoding() {
    }

    public static GCMParameterSpec restoreGcmParameters(
            AlgorithmParameters original) throws GeneralSecurityException {

        byte[] encoded = original.getEncoded();

        AlgorithmParameters restored = AlgorithmParameters.getInstance(
            original.getAlgorithm(),
            original.getProvider()
        );

        restored.init(encoded);
        return restored.getParameterSpec(GCMParameterSpec.class);
    }
}
~~~

Ví dụ giả định provider trả về AlgorithmParameters tương ứng với GCM và hỗ trợ encoding/decoding đó. Định dạng byte và tên thuật toán tham số phụ thuộc provider; nếu cần trao đổi giữa nhiều nền tảng, phải chọn định dạng chuẩn được các bên hỗ trợ và kiểm thử tương thích. Không nên giả định mọi provider đều dùng cùng encoding.

Tham số như nonce hoặc IV thường được lưu cùng ciphertext. Cần lưu cả metadata cần thiết như thuật toán, phiên bản định dạng, key ID và tag length. Những metadata ảnh hưởng đến cách giải mã nên được xác thực bằng AAD hoặc cơ chế toàn vẹn tương đương.

## 11. AlgorithmParameterGenerator: sinh tham số riêng

Một số thuật toán cần tham số miền (domain parameters) được sinh hoặc lựa chọn trước khi sinh khóa. **AlgorithmParameterGenerator** là engine class để tạo **AlgorithmParameters** cho những trường hợp đó.

Ví dụ minh họa sinh tham số Diffie-Hellman:

~~~java
import java.security.AlgorithmParameterGenerator;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.spec.DHParameterSpec;

public final class DhParameterExample {
    private DhParameterExample() {
    }

    public static DHParameterSpec generate() throws GeneralSecurityException {
        AlgorithmParameterGenerator generator =
            AlgorithmParameterGenerator.getInstance("DH");

        generator.init(2048, new SecureRandom());

        AlgorithmParameters parameters = generator.generateParameters();
        return parameters.getParameterSpec(DHParameterSpec.class);
    }
}
~~~

Đoạn mã sinh tham số DH chứ không sinh cặp khóa. Sau đó, có thể truyền DHParameterSpec cho KeyPairGenerator để sinh cặp khóa tương ứng. Việc tạo tham số DH mới có thể tốn thời gian; trong nhiều giao thức hiện đại, nên dùng nhóm chuẩn hóa đã được phê duyệt và hỗ trợ thay vì tự sinh tham số cho mỗi phiên.

Phân biệt ba bước:

1. **AlgorithmParameterGenerator** tạo tham số miền nếu thuật toán cần.
2. **KeyPairGenerator** dùng tham số đó để sinh cặp khóa.
3. **KeyAgreement** dùng private key và public key của bên kia để tạo bí mật chung.

## 12. Lưu trữ và truyền tham số an toàn

Tham số thường được lưu cùng dữ liệu mã hóa hoặc chữ ký để bên nhận tái tạo đúng phép toán. Một định dạng lưu trữ có thể gồm:

- Tên thuật toán và transformation.
- Phiên bản định dạng dữ liệu.
- Key ID hoặc phiên bản khóa.
- IV/nonce hoặc tham số công khai cần thiết.
- Ciphertext kèm authentication tag.
- Metadata cần được xác thực bằng AAD.

Không lưu khóa bí mật cùng tham số theo cách khiến một người có thể lấy cả hai mà không qua kiểm soát truy cập. IV, nonce và salt thường có thể công khai, nhưng phải được gắn đúng với ciphertext và đúng phiên bản khóa.

Với dữ liệu được mã hóa bằng AES-GCM, lưu nonce cạnh ciphertext là bình thường. Bên nhận cần biết key ID để lấy đúng khóa, nonce để khởi tạo GCM và AAD để xác thực metadata. Nếu thay đổi một trường metadata quan trọng mà không có xác thực, ứng dụng có thể giải mã nhầm dữ liệu hoặc bị tấn công thay thế ngữ cảnh.

Đối với RSA-OAEP và RSA-PSS, tham số phải được chuẩn hóa trong giao thức. Không nên chỉ ghi tên thuật toán chung như RSA rồi để mỗi provider tự chọn padding hoặc hash mặc định khác nhau.

## 13. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Nhầm AlgorithmParameterSpec với AlgorithmParameters | Truyền sai kiểu hoặc khó lưu/khôi phục tham số | Dùng Spec để cấu hình API; Parameters để biểu diễn/encode tham số |
| Tái sử dụng nonce GCM với cùng khóa | Có thể làm lộ plaintext và phá vỡ xác thực | Duy trì nonce duy nhất theo từng khóa |
| Coi IV/nonce là bí mật | Thiết kế trao đổi phức tạp nhưng không tăng an toàn | Công khai khi cần, tập trung bảo đảm đúng định dạng và không tái sử dụng |
| Dùng CBC mà không có MAC | Ciphertext có thể bị sửa mà không được phát hiện an toàn | Ưu tiên AEAD hoặc dùng cấu trúc xác thực đã được thiết kế đúng |
| Nhầm tag length tính bằng byte | Cấu hình GCM sai hoặc không tương thích | GCMParameterSpec nhận độ dài tag bằng bit |
| Để provider tự chọn OAEP/PSS parameters | Hai phía có thể dùng hash hoặc MGF khác nhau | Truyền OAEPParameterSpec/PSSParameterSpec tường minh |
| Dùng salt thay cho nonce hoặc ngược lại | Không đáp ứng yêu cầu riêng của KDF hoặc chế độ mã hóa | Chọn tham số theo đúng thuật toán |
| Không lưu tham số cần thiết cạnh ciphertext | Không thể giải mã hoặc xác minh sau này | Lưu IV/nonce, salt, key ID và metadata theo schema |
| Tin encoding tham số giống nhau giữa provider | Không đọc được dữ liệu khi đổi provider | Dùng encoding chuẩn và kiểm thử liên-provider |
| Cho rằng AlgorithmParameterGenerator sinh khóa | Sai luồng xử lý và API | Dùng ParameterGenerator cho tham số, KeyPairGenerator/KeyGenerator cho khóa |

## 14. Nguyên tắc triển khai an toàn

- Chọn tham số theo thuật toán và giao thức, không dựa vào mặc định không được kiểm soát.
- Ưu tiên AEAD như AES-GCM khi cần mã hóa và xác thực dữ liệu.
- Với GCM, dùng nonce 96 bit theo cấu hình phổ biến, tag đủ mạnh và bảo đảm nonce không lặp với cùng khóa.
- Với OAEP và PSS, chỉ định hash, MGF, salt length và các tham số cần thiết tường minh.
- Với EC, chọn named curve chuẩn được provider và giao thức hỗ trợ.
- Với PBE/KDF, chọn salt ngẫu nhiên và số vòng lặp phù hợp; kiểm soát chi phí xử lý đầu vào.
- Lưu tham số công khai cùng ciphertext nhưng bảo đảm chúng gắn đúng key ID và được xác thực khi cần.
- Kiểm thử khả năng đọc tham số giữa các provider và phiên bản JDK trước khi thay đổi môi trường.
- Không coi việc tham số là công khai đồng nghĩa với việc có thể tái sử dụng tùy ý.
- Gắn việc tạo, lưu, sử dụng và loại bỏ tham số với quy trình quản lý khóa, kiểm toán và vận hành của hệ thống.

Algorithm parameters là một phần của cấu hình mật mã, có ảnh hưởng trực tiếp tới khả năng tương thích và mức an toàn của thao tác. Ứng dụng Java cần mô tả tham số rõ ràng bằng các lớp Spec, dùng AlgorithmParameters khi cần lưu hoặc khôi phục biểu diễn, và chỉ dùng AlgorithmParameterGenerator khi thực sự cần sinh bộ tham số. Cách quản lý này giúp provider, khóa và dữ liệu mật mã phối hợp nhất quán trong suốt vòng đời bảo vệ dữ liệu.
