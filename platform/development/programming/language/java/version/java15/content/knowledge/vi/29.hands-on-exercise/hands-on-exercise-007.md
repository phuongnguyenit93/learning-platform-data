# Ký và xác minh tài liệu bằng Ed25519 hoặc Ed448

**Bài thực hành Java 15+**: dùng Java Security API (`java.security`) để tạo cặp khóa Ed25519/Ed448, ký chính xác **các byte** của một tài liệu, lưu chữ ký và kiểm tra rằng tài liệu không bị thay đổi. Bài thực hành có chương trình CLI Java 17+ chạy độc lập và các kiểm thử hồi quy bằng JUnit Jupiter. Kiến thức dùng ở đây vẫn áp dụng trên các JDK hiện đại; hỗ trợ chuẩn EdDSA được đưa vào OpenJDK từ **JDK 15 (JEP 339)**.

**Kết quả mong đợi:** bạn có thể tạo khóa một lần, ký tệp bằng khóa **bí mật**, kiểm tra chữ ký bằng khóa **công khai** ở tiến trình khác, nhận biết tệp/chữ ký/khóa không khớp và hiểu giới hạn an toàn của thao tác xác minh.

> **Phạm vi an toàn:** ví dụ tạo tệp khóa bí mật dưới dạng **PKCS#8 DER chưa mã hóa** để dễ thực hành trong thư mục thử nghiệm cá nhân. Khi triển khai thực tế, bảo vệ khóa bằng keystore, KMS hoặc HSM và quy trình phân quyền/luân chuyển khóa phù hợp. Đừng đưa khóa bí mật vào Git, log, artifact CI hoặc gửi cho bên xác minh.

## 1. Ký số giải quyết vấn đề gì?

Chữ ký số được tạo từ nội dung tài liệu và **private key** của người ký. Người nhận dùng **public key** tương ứng cùng nội dung và chữ ký để xác minh.

```text
                         NGƯỜI KÝ
tài liệu (byte[]) ─┐
                   ├── Signature(Ed25519/Ed448) ── chữ ký (byte[])
private key ───────┘

                       NGƯỜI XÁC MINH
tài liệu nhận ─────┐
chữ ký nhận ───────┼── Signature.verify(...) ── true / false
public key đã tin ─┘
```

Một kết quả `true` khẳng định chữ ký hợp lệ với **đúng chuỗi byte**, thuật toán và khóa công khai được cung cấp. Nó không tự chứng minh danh tính pháp lý của người ký: người nhận phải biết vì sao có thể **tin cậy public key**, ví dụ khóa được phân phối qua kênh đã xác thực, một chứng thư và hệ thống PKI, hoặc định danh khóa đã ghim theo chính sách.

Chữ ký số cung cấp khả năng kiểm tra **tính toàn vẹn** và **nguồn gốc gắn với khóa**. Nó **không mã hóa** nội dung: người sở hữu tệp được ký vẫn có thể đọc tệp nếu tệp không được mã hóa riêng. Chữ ký cũng không tự cung cấp timestamp đáng tin, không chống phát lại một thông điệp cũ và không thay thế quy trình phê duyệt tài liệu.

### 1.1. EdDSA, Ed25519 và Ed448

**EdDSA** là họ thuật toán chữ ký số dùng đường cong Edwards, được mô tả trong [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032). **Ed25519** và **Ed448** là hai lựa chọn cụ thể. Trong Java hiện đại có thể dùng trực tiếp các tên chuẩn này với:

```java
KeyPairGenerator.getInstance("Ed25519");
Signature.getInstance("Ed25519");

KeyPairGenerator.getInstance("Ed448");
Signature.getInstance("Ed448");
```

| Đặc điểm | Ed25519 | Ed448 |
| --- | --- | --- |
| Mục đích | Chữ ký số | Chữ ký số |
| Kích thước chữ ký chuẩn | **64 byte** | **114 byte** |
| Kích thước khóa công khai thô theo RFC 8032 | 32 byte | 57 byte |
| Kích thước secret seed thô theo RFC 8032 | 32 byte | 57 byte |
| Mức an toàn mục tiêu xấp xỉ | 128-bit | 224-bit |
| Lựa chọn thực tế | Thường là điểm khởi đầu thuận tiện nhờ chữ ký ngắn và độ phổ biến | Dùng khi yêu cầu chính sách, độ an toàn hoặc giao thức quy định Ed448 |

Các con số **khóa thô** trong bảng không phải kích thước tệp `*.spki`/`*.pk8` do Java xuất: những tệp đó chứa cấu trúc mã hóa và metadata thuật toán, nên dài hơn. Cũng không suy ra Ed448 luôn nhanh hơn hoặc an toàn hơn trong **mọi** hệ thống: phải xét khả năng tương tác, thư viện nhận chữ ký, chính sách bảo mật và hiệu năng.

Đây là các biến thể chữ ký **Ed25519/Ed448 chuẩn**. `X25519`/`X448` là các thuật toán **trao đổi khóa** thuộc mục đích khác; không dùng khóa X25519 để thay thế Ed25519 chỉ vì tên gần giống. `SHA256withECDSA` là họ chữ ký khác và không thể thay bằng Ed25519 mà giữ nguyên dữ liệu/định dạng cũ.

### 1.2. Vì sao không tự gọi `MessageDigest` trước khi ký?

Thông thường dùng:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(documentBytes);
byte[] signature = signer.sign();
```

**Hãy đưa chính các byte tài liệu** vào `Signature.update(...)`. Thuật toán Ed25519/Ed448 chuẩn thực hiện xử lý băm cần thiết bên trong. Nếu tự tính `SHA-256` trước rồi ký 32 byte digest, bạn đang ký **một thông điệp khác** (digest), không còn tương đương với giao thức ký tài liệu thô ở ví dụ này. Hai bên sẽ không xác minh chéo được nếu một bên ký tài liệu còn bên kia ký digest.

Các biến thể prehash/context được RFC 8032 mô tả là chủ đề giao thức riêng. Bài này chỉ dùng cách gọi chuẩn có sẵn `Ed25519` hoặc `Ed448`; không tự pha trộn các biến thể, domain separator hoặc encoding tùy ý.

## 2. Các bước Java Security API

Quy trình luôn có ba giai đoạn rõ ràng:

1. **Tạo khóa:** `KeyPairGenerator.getInstance(algorithm).generateKeyPair()` trả `PrivateKey` và `PublicKey`.
2. **Ký:** `Signature.getInstance(algorithm)` → `initSign(privateKey)` → một hoặc nhiều `update(bytes)` → `sign()`.
3. **Xác minh:** `Signature.getInstance(algorithm)` → `initVerify(publicKey)` → `update` **đúng dữ liệu đã ký** → `verify(signatureBytes)`.

`Signature` là đối tượng có trạng thái. Tránh dùng cùng một instance cho hai luồng đồng thời hoặc cho nhiều tài liệu mà không khởi tạo lại đúng chế độ. Để mã dễ kiểm tra, ví dụ tạo một `Signature` mới cho mỗi lần ký/xác minh.

### 2.1. Ký byte, không ký cách hiển thị

Ví dụ hai văn bản trông giống nhau nhưng khác byte:

- `"A\nB\n"` dùng LF, còn `"A\r\nB\r\n"` dùng CRLF.
- Unicode có thể được biểu diễn theo các chuỗi code point khác nhau nhưng nhìn tương tự.
- Thêm dấu cách, BOM, đổi encoding, chuyển PDF sang phiên bản khác hoặc chỉ thay metadata cũng có thể làm byte khác.

**Chữ ký có thể không còn hợp lệ sau bất kỳ thay đổi byte nào**, dù giao diện hiển thị vẫn tương tự. Phải thống nhất rõ mình ký toàn bộ file thô, một dạng biểu diễn chuẩn hóa hay một cấu trúc dữ liệu được serial hóa nhất quán. Bài thực hành chọn **ký byte file nguyên trạng** để không có bước chuẩn hóa ngầm.

Nếu sản phẩm muốn chữ ký giữ hiệu lực sau khi JSON được sắp xếp lại thuộc tính hoặc thay line endings, cần định nghĩa một chuẩn canonicalization và kiểm thử chính chuẩn đó. Không tự dùng `trim()`, `replace()` hoặc parse rồi stringify ngay trong luồng xác minh để “sửa” dữ liệu.

### 2.2. Key encoding khi lưu và khôi phục

Java thường cung cấp:

- `privateKey.getEncoded()`: dữ liệu **PKCS#8 DER**, khi provider cho phép xuất private key.
- `publicKey.getEncoded()`: dữ liệu **X.509 SubjectPublicKeyInfo DER (SPKI)**, không phải một chứng thư X.509 hoàn chỉnh.
- `new PKCS8EncodedKeySpec(bytes)` và `new X509EncodedKeySpec(bytes)` để nạp lại qua `KeyFactory.getInstance("Ed25519")` hoặc `"Ed448"`.

Tệp SPKI công khai **không xác nhận ai sở hữu khóa**; phải có cơ chế phân phối và liên kết khóa với danh tính độc lập. Không trộn PKCS#8 với tệp PEM, SSH public key hoặc các blob seed thô. Nếu dữ liệu xuất/nhập là PEM, chỉ mã hóa Base64 quanh đúng đối tượng DER và đúng nhãn PEM theo giao thức của hai phía.

## 3. Bài thực hành đầy đủ: chương trình `SignedFiles.java`

Chương trình sau dùng API có sẵn trên JDK 17+, không cần thư viện bên ngoài và hỗ trợ bốn thao tác:

- `keygen <algorithm> <private.pk8> <public.spki>`: tạo cặp khóa để dùng qua nhiều lượt chạy.
- `sign <algorithm> <private.pk8> <document> <signature.bin>`: ký byte tài liệu bằng private key đã lưu.
- `verify <algorithm> <public.spki> <document> <signature.bin>`: kiểm tra với public key, in `VALID` hoặc `INVALID`.
- Chỉ chấp nhận `Ed25519` hoặc `Ed448` để người học không vô tình chọn nhầm họ thuật toán.

Lưu vào **`SignedFiles.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

public final class SignedFiles {
    private static final int BUFFER_SIZE = 8192;

    private SignedFiles() {
    }

    private static String checkedAlgorithm(String name) {
        if (!"Ed25519".equals(name) && !"Ed448".equals(name)) {
            throw new IllegalArgumentException(
                    "Algorithm must be Ed25519 or Ed448");
        }
        return name;
    }

    private static void requireCount(String[] args, int count) {
        if (args.length != count) {
            throw new IllegalArgumentException(
                    "Usage: keygen ALG PRIVATE PUBLIC | "
                    + "sign ALG PRIVATE DOCUMENT SIGNATURE | "
                    + "verify ALG PUBLIC DOCUMENT SIGNATURE");
        }
    }

    private static void feedFile(Signature engine, Path file)
            throws IOException, SignatureException {
        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[BUFFER_SIZE];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (count > 0) {
                    engine.update(buffer, 0, count);
                }
            }
        }
    }

    static byte[] signFile(String algorithm, PrivateKey privateKey,
                           Path document)
            throws IOException, GeneralSecurityException {
        Signature signer = Signature.getInstance(checkedAlgorithm(algorithm));
        signer.initSign(privateKey);
        feedFile(signer, document);
        return signer.sign();
    }

    static boolean verifyFile(String algorithm, PublicKey publicKey,
                              Path document, byte[] signatureBytes)
            throws IOException, GeneralSecurityException {
        Signature verifier =
                Signature.getInstance(checkedAlgorithm(algorithm));
        verifier.initVerify(publicKey);
        feedFile(verifier, document);
        return verifier.verify(signatureBytes);
    }

    private static PrivateKey readPrivate(String algorithm, Path file)
            throws IOException, GeneralSecurityException {
        byte[] encoded = Files.readAllBytes(file);
        return KeyFactory.getInstance(algorithm)
                .generatePrivate(new PKCS8EncodedKeySpec(encoded));
    }

    private static PublicKey readPublic(String algorithm, Path file)
            throws IOException, GeneralSecurityException {
        byte[] encoded = Files.readAllBytes(file);
        return KeyFactory.getInstance(algorithm)
                .generatePublic(new X509EncodedKeySpec(encoded));
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            requireCount(args, 4);
        }

        String operation = args[0];
        String algorithm = checkedAlgorithm(args[1]);

        switch (operation) {
            case "keygen" -> {
                requireCount(args, 4);
                KeyPair pair = KeyPairGenerator.getInstance(algorithm)
                                              .generateKeyPair();

                // Chỉ dùng trong thư mục demo: PKCS#8 chưa mã hóa.
                Files.write(Path.of(args[2]), pair.getPrivate().getEncoded(),
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE);
                Files.write(Path.of(args[3]), pair.getPublic().getEncoded(),
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE);
                System.out.println("KEYGEN " + algorithm);
            }
            case "sign" -> {
                requireCount(args, 5);
                PrivateKey privateKey =
                        readPrivate(algorithm, Path.of(args[2]));
                byte[] signed = signFile(algorithm, privateKey,
                                         Path.of(args[3]));
                Files.write(Path.of(args[4]), signed,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE);
                System.out.println("SIGNED " + algorithm + " "
                                   + signed.length + " bytes");
            }
            case "verify" -> {
                requireCount(args, 5);
                PublicKey publicKey =
                        readPublic(algorithm, Path.of(args[2]));
                byte[] signed = Files.readAllBytes(Path.of(args[4]));

                boolean valid;
                try {
                    valid = verifyFile(algorithm, publicKey,
                                       Path.of(args[3]), signed);
                } catch (SignatureException invalidEncoding) {
                    valid = false;
                }

                System.out.println(valid ? "VALID" : "INVALID");
                if (!valid) {
                    System.exit(2);
                }
            }
            default -> throw new IllegalArgumentException(
                    "Unknown operation: " + operation);
        }
    }
}
```

**Giải thích cấu trúc:**

- `checkedAlgorithm` chọn tường minh Ed25519/Ed448, tránh dùng nhầm `X25519` hoặc đổi thuật toán giữa các phía.
- `feedFile` đọc file theo từng khối 8192 byte, chuyển đúng các byte đọc được vào `Signature.update`. Nhờ vậy code không cần tạo `byte[]` chứa toàn bộ tài liệu ở tầng ứng dụng. **Không được suy luận** rằng mọi provider EdDSA đều dùng RAM hằng số: một số implementation có thể đệm thông điệp nội bộ; đo RAM với file lớn trên đúng JVM/provider.
- `signFile` và `verifyFile` có thể được gọi trực tiếp từ unit test; không gắn logic ký với việc ghi console.
- `KeyFactory` dùng đúng chuẩn encoding của hai loại khóa; ký dùng private key, xác minh dùng public key.
- `Files.write(..., CREATE_NEW)` không ghi đè tệp đã tồn tại. Nếu lệnh `keygen` tạo được tệp private rồi gặp lỗi khi ghi public, thao tác **không có tính transaction**: hãy xử lý cặp tệp chưa hoàn chỉnh, tránh giữ private key bị bỏ quên.
- `verify` trả về kết quả qua stdout và **exit code**: `0` khi hợp lệ; `2` khi nội dung/chữ ký không hợp lệ; lỗi môi trường như thiếu file, key encoding sai hoặc thuật toán/provider không có sẽ ném exception và kết thúc bất thường. Một ứng dụng sản xuất nên phân loại lỗi rõ và không in dữ liệu nhạy cảm vào log.
- Chỉ bắt `SignatureException` khi chữ ký sai định dạng để coi đó là không hợp lệ. Không nên gộp mọi lỗi như mất file hoặc sai quyền truy cập thành `INVALID`, vì khi đó hệ thống giám sát không phân biệt được lỗi vận hành với chữ ký bị sửa.

**Lưu ý khóa:** `getEncoded()` ở ví dụ hoạt động với khóa có thể xuất từ provider điển hình. Khóa nằm trong HSM, KMS hoặc một provider khác có thể **không cho xuất private key** (`getEncoded()` có thể trả `null`). Với khóa được quản lý, hãy yêu cầu provider thực hiện chữ ký trực tiếp và dùng luồng phân quyền của hệ thống đó.

## 4. Chạy thử trên Java 17+

Kiểm tra JDK:

```bash
java -version
javac -version
```

Biên dịch:

```bash
javac -encoding UTF-8 SignedFiles.java
```

Tạo một tài liệu văn bản UTF-8 thật để ký. Ví dụ trên shell POSIX:

```bash
printf 'Hop dong so 42\nGia tri 100\n' > document.txt
```

Ở đây ta cố tình dùng nội dung ASCII và LF để dễ tái hiện; trên PowerShell có thể tạo file tương ứng bằng API ghi UTF-8, nhưng **đừng mặc định hai công cụ tạo cùng byte** nếu một phía chèn BOM hoặc đổi line ending. Vì chữ ký phụ thuộc byte, hãy ký và xác minh đúng cùng file.

Tạo cặp khóa:

```bash
java SignedFiles keygen Ed25519 signer.pk8 signer.spki
```

**Stdout:**

```text
KEYGEN Ed25519
```

Ký tài liệu:

```bash
java SignedFiles sign Ed25519 signer.pk8 document.txt document.sig
```

**Stdout:**

```text
SIGNED Ed25519 64 bytes
```

Xác minh chữ ký bằng **khóa công khai**:

```bash
java SignedFiles verify Ed25519 signer.spki document.txt document.sig
```

**Stdout:**

```text
VALID
```

Thử sửa đúng một byte bằng một file khác, để giữ nguyên tài liệu gốc:

```bash
printf 'Hop dong so 42\nGia tri 101\n' > changed.txt
java SignedFiles verify Ed25519 signer.spki changed.txt document.sig
```

**Stdout của lần xác minh thất bại:**

```text
INVALID
```

Lệnh cuối trả mã thoát `2`; trong CI, shell hoặc script hãy coi đây là **kết quả chữ ký không đạt**. Chữ ký và public key không biến tài liệu bị sửa thành tài liệu gốc. Nếu sửa luôn `document.txt` rồi khôi phục, cần giữ bản gốc chính xác từng byte để test kết quả trở lại `VALID`.

Đổi sang **Ed448** bằng bộ file mới và thay đúng tên thuật toán trong cả ba lệnh:

```bash
java SignedFiles keygen Ed448 signer448.pk8 signer448.spki
java SignedFiles sign Ed448 signer448.pk8 document.txt document448.sig
java SignedFiles verify Ed448 signer448.spki document.txt document448.sig
```

**Stdout tương ứng:**

```text
KEYGEN Ed448
SIGNED Ed448 114 bytes
VALID
```

Kích thước **chữ ký thô** 64/114 byte là theo RFC 8032; tệp khóa DER không có kích thước giống hệt seed/public key thô. Nếu bộ JDK đã lược bỏ provider hoặc hệ thống bảo mật giới hạn thuật toán, có thể gặp `NoSuchAlgorithmException`; hãy kiểm tra bản phân phối JDK và provider thực tế.

### 4.1. Kết quả chữ ký EdDSA có lặp lại được không?

Với biến thể Ed25519/Ed448 **pure** đúng RFC 8032, cùng private key và cùng thông điệp tạo chữ ký tất định (*deterministic*). Bạn có thể ký lại cùng nội dung và so sánh hai file chữ ký:

```bash
java SignedFiles sign Ed25519 signer.pk8 document.txt document2.sig
```

Nếu dùng cùng key, cùng file và thuật toán, `document.sig` và `document2.sig` phải có **cùng byte**. Tên tệp đầu ra khác không làm thay đổi chữ ký. Tính tất định **không đồng nghĩa** với an toàn khi khóa bí mật bị lộ hoặc khi dữ liệu ký không có phiên bản/domain rõ ràng.

### 4.2. Kiểm chứng byte thực của tài liệu

Nếu quá trình xuất tài liệu có nguy cơ chuyển encoding hoặc line endings, dùng `MessageDigest` **để quan sát fingerprint của file**, tách biệt với hoạt động ký:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

// Trong một phương thức đã khai báo throws Exception:
byte[] data = Files.readAllBytes(Path.of("document.txt"));
byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
System.out.println(HexFormat.of().formatHex(digest));
```

Đây là **đoạn minh họa đặt trong một lớp/phương thức Java**, không phải chương trình độc lập. Nó đọc toàn bộ file vào RAM, phù hợp để debug các file nhỏ; với file lớn có thể dùng streaming digest. SHA-256 ở đây giúp so sánh hai phiên bản byte **và không thay thế chữ ký Ed25519/Ed448**. Hàm băm không tự chứng minh ai đã tạo tài liệu.

## 5. Kiểm thử hồi quy bằng JUnit Jupiter

Bài kiểm thử cần xác minh **cả ca thành công và thất bại**. Các trường hợp quan trọng:

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Tài liệu gốc + chữ ký hợp lệ + public key đúng | `verifyFile(...) == true` |
| Tài liệu bị sửa một byte | `false` |
| Chữ ký gốc nhưng public key của cặp khóa khác, cùng thuật toán | `false` |
| File rỗng được ký bởi private key đúng | `true` |
| Ký lại cùng byte bằng cùng khóa Ed25519/Ed448 | `byte[]` chữ ký giống nhau |
| Nạp lại public key từ SPKI DER | Vẫn xác minh đúng |
| Chữ ký bị cắt hoặc sai định dạng | `false` hoặc `SignatureException`; cả hai đều phải được coi là không hợp lệ |
| Khóa private/public khác họ thuật toán | Từ chối ở bước nạp khóa/khởi tạo hoặc thao tác ký/xác minh |
| Thiếu file, sai quyền hoặc provider không hỗ trợ | Báo lỗi vận hành; không coi là xác minh thành công |

Thêm dependency **JUnit Jupiter** và bộ chạy JUnit Platform theo cấu hình sẵn của dự án. Ví dụ với Gradle Groovy DSL và một version JUnit được dự án quản lý:

```groovy
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
}

test {
    useJUnitPlatform()
}
```

Nếu dự án chưa quản lý version bằng BOM/version catalog, phải chọn một phiên bản JUnit Jupiter hiện được hỗ trợ thay vì dùng dependency thiếu version. Các đoạn sau là **tệp test JUnit**, không chạy bằng `javac` thuần nếu thiếu JUnit trên classpath.

Lưu **`SignedFilesTest.java`** trong test source set, cùng package với `SignedFiles`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SignedFilesTest {
    @TempDir
    Path tempDir;

    @ParameterizedTest
    @ValueSource(strings = {"Ed25519", "Ed448"})
    void validSignaturesAndTampering(String algorithm) throws Exception {
        Path file = tempDir.resolve(algorithm + ".txt");
        Files.writeString(file, "Hop dong A\nGia tri: 100\n",
                          StandardCharsets.UTF_8);

        KeyPair pair = KeyPairGenerator.getInstance(algorithm)
                                      .generateKeyPair();
        byte[] signature =
                SignedFiles.signFile(algorithm, pair.getPrivate(), file);

        assertEquals("Ed25519".equals(algorithm) ? 64 : 114,
                     signature.length);
        assertTrue(SignedFiles.verifyFile(
                algorithm, pair.getPublic(), file, signature));

        // Pure Ed25519/Ed448 là tất định với cùng khóa và byte.
        assertArrayEquals(signature,
                SignedFiles.signFile(algorithm, pair.getPrivate(), file));

        // Một public key khác không xác minh được chữ ký cũ.
        KeyPair other = KeyPairGenerator.getInstance(algorithm)
                                       .generateKeyPair();
        assertFalse(SignedFiles.verifyFile(
                algorithm, other.getPublic(), file, signature));

        // Nạp lại public key từ SubjectPublicKeyInfo DER.
        PublicKey decoded = KeyFactory.getInstance(algorithm)
                .generatePublic(new X509EncodedKeySpec(
                        pair.getPublic().getEncoded()));
        assertTrue(SignedFiles.verifyFile(
                algorithm, decoded, file, signature));

        // Thay nội dung dù chỉ một con số.
        Files.writeString(file, "Hop dong A\nGia tri: 101\n",
                          StandardCharsets.UTF_8);
        assertFalse(SignedFiles.verifyFile(
                algorithm, pair.getPublic(), file, signature));
    }

    @ParameterizedTest
    @ValueSource(strings = {"Ed25519", "Ed448"})
    void emptyDocumentCanAlsoBeSigned(String algorithm) throws Exception {
        Path file = tempDir.resolve(algorithm + "-empty.bin");
        Files.write(file, new byte[0]);

        KeyPair pair = KeyPairGenerator.getInstance(algorithm)
                                      .generateKeyPair();
        byte[] signature =
                SignedFiles.signFile(algorithm, pair.getPrivate(), file);

        assertTrue(SignedFiles.verifyFile(
                algorithm, pair.getPublic(), file, signature));
    }

    @Test
    void rejectsUnexpectedAlgorithm() {
        assertThrows(IllegalArgumentException.class,
                () -> SignedFiles.signFile("X25519", null,
                                          Path.of("not-used.txt")));
    }
}
```

Giải thích `rejectsUnexpectedAlgorithm`: `signFile()` kiểm tra thuật toán ngay khi gọi `Signature.getInstance(checkedAlgorithm(...))`, **trước** khi truy cập private key hoặc file, nên ném `IllegalArgumentException` ổn định. Test này kiểm tra cơ chế chỉ cho phép Ed25519/Ed448, không cần một file thật.

**Tính năng kiểm thử quan trọng:**

- `@TempDir` tạo thư mục tạm để các test độc lập và tự dọn sau khi chạy.
- `@ParameterizedTest` chạy cùng phép kiểm chứng cho **cả Ed25519 và Ed448**, tránh chỉ kiểm tra một thuật toán nhưng tuyên bố chương trình hỗ trợ cả hai.
- Test `validSignaturesAndTampering` chứng minh đúng key/content → `true`; sai key/sửa content → `false`.
- Test signature deterministic chỉ áp dụng cho các biến thể pure đang dùng; không mở rộng tuyên bố đó sang mọi thuật toán chữ ký số khác.
- Empty file được ký hợp lệ, vì EdDSA xử lý thông điệp có độ dài 0 theo RFC 8032.

Một test bổ sung đáng làm khi tích hợp thực tế là xác minh ở **hai tiến trình** hoặc **hai service** khác nhau sau khi chuyển public key và chữ ký theo giao thức. Việc gọi `verifyFile()` trong cùng JVM chủ yếu kiểm chứng API; test tích hợp mới xác nhận encoding, phân phối khóa, metadata và file bytes qua mạng/đĩa được giữ nguyên.

## 6. Thiết kế gói dữ liệu ký để hai hệ thống hiểu nhau

Ba thành phần cốt lõi phải được giữ nguyên:

1. **Tài liệu hoặc hash đã được quy định đúng trong giao thức** (ở bài này là tài liệu byte-thô; không ký hash rời).
2. **Chữ ký**, dưới dạng byte array; nếu truyền qua JSON thì mã hóa Base64 của **chính chữ ký thô**, không phải một chữ ký khác do serializer tạo.
3. **Thuật toán và thông tin định danh khóa công khai đáng tin** để bên nhận biết phải dùng Ed25519 hay Ed448 và khóa nào.

Một manifest giả định:

```json
{
  "signatureAlgorithm": "Ed25519",
  "keyId": "signing-key-v3",
  "signatureEncoding": "base64",
  "signature": "<base64-cua-64-byte-chu-ky>"
}
```

Đây là **ví dụ hình dạng dữ liệu**, không phải chữ ký thật và không tự định nghĩa một chuẩn file ký. Một gói triển khai có thể bổ sung `contentType`, `documentVersion`, `signedAt` và chính sách xác minh. `keyId` chỉ dùng để **chọn** khóa từ kho đã tin cậy; không chấp nhận một public key tùy ý từ chính manifest không xác thực rồi suy luận người gửi đáng tin. Các trường metadata nào cần chống sửa đổi phải được đưa vào **chính dữ liệu được ký** theo đặc tả giao thức. Ở bài demo chỉ các **byte của document** được ký: sửa metadata bên ngoài mà không sửa document sẽ không làm chữ ký document thất bại.

### 6.1. Chuẩn hóa dữ liệu khi ký JSON, XML hoặc PDF

- **JSON:** thứ tự trường, dấu cách và biểu diễn Unicode có thể khác nhau sau khi serialize. Nếu hai hệ thống muốn ký “cùng nội dung logic”, phải thống nhất một chuẩn canonical JSON, chẳng hạn một chuẩn được cả hai bên hỗ trợ, thay vì tự `toString()` theo từng thư viện.
- **XML:** namespace và whitespace có ngữ nghĩa riêng; cần chuẩn hóa đúng chuẩn chữ ký XML nếu hệ thống yêu cầu.
- **PDF:** nhiều thao tác lưu/chèn metadata tạo byte mới. Chữ ký PDF có quy tắc byte range và cấu trúc riêng; ký toàn bộ byte PDF bằng `SignedFiles` **không tự tạo chữ ký PDF hiển thị trong phần mềm đọc PDF**.

Trong chương trình thực hành, tệp được ký là **byte file nguyên trạng**. Đây là một chữ ký tách rời (*detached signature*): `document.sig` nằm ngoài `document.txt`. Để tích hợp với định dạng tài liệu có đặc tả chữ ký riêng, phải dùng hoặc tuân theo đặc tả đó.

### 6.2. Phân phối và luân chuyển public key

Hãy lưu khóa trong một danh mục có `keyId`, thuật toán, trạng thái và thời điểm còn hiệu lực. Khi luân chuyển khóa, cần giữ bản public key cũ theo chính sách để xác minh tài liệu đã ký trước đây, đồng thời không tiếp tục cho phép ký bằng khóa đã hết hiệu lực hoặc đã bị lộ. Chữ ký có thể **hợp lệ toán học** ngay cả khi khóa đã bị thu hồi; quyết định **chấp nhận** còn phụ thuộc chính sách tin cậy và thời gian ký được xác thực.

Không lấy fingerprint/public key từ cùng nguồn không tin cậy với tài liệu rồi gọi đó là xác minh nguồn gốc. Nếu cần gắn người ký với một danh tính, dùng kênh phân phối khóa đã xác thực hoặc một hạ tầng chứng thư đáng tin.

## 7. Các lỗi phổ biến khi triển khai

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng private key để xác minh hoặc public key để ký | API lỗi hoặc không thực hiện được thao tác | `initSign(privateKey)`, `initVerify(publicKey)` |
| Đổi LF thành CRLF, thêm BOM hoặc sửa một ký tự | Chữ ký cũ không còn hợp lệ | Ký/xác minh byte nguyên trạng; test encoding |
| Tự hash tài liệu ở bên ký, bên nhận xác minh byte gốc | Giao thức hai phía không tương đương | Thống nhất chính xác message bytes trước khi ký |
| Tin public key lấy từ chính đối tượng chưa được xác thực | Kẻ tấn công có thể thay cả nội dung, chữ ký và khóa | Liên kết `keyId` với trust store đáng tin |
| Nhầm `Ed25519` với `X25519` | Sai mục đích và không tương thích thuật toán | Chỉ dùng tên `Ed25519`/`Ed448` trong JCA chữ ký |
| Coi SPKI `.spki` là certificate | Không có chuỗi tin cậy hay danh tính được chứng thực | Phân biệt public-key encoding và X.509 certificate |
| Đưa private PKCS#8 chưa mã hóa lên Git/CI | Mất khóa bí mật, ai có khóa cũng có thể ký | Keystore/KMS/HSM, phân quyền và kiểm soát secret |
| Chuyển raw signature sang định dạng riêng mà không mô tả | Bên nhận không thể verify | Chuẩn hóa Base64/DER/PEM/metadata theo hợp đồng |
| Dùng kết quả `verify == true` như bằng chứng timestamp hoặc quyền ký | Quyết định nghiệp vụ sai | Kiểm tra chính sách khóa, nguồn cấp khóa và thời điểm được chứng thực |
| Dùng một `Signature` chung giữa nhiều request/luồng | Trạng thái ký/xác minh bị trộn | Khởi tạo `Signature` riêng theo yêu cầu |
| Giả định `update` theo buffer là không tốn RAM | Có thể thiếu bộ nhớ với file rất lớn ở provider cụ thể | Benchmark/giám sát memory và kiểm tra giới hạn provider |
| Chấp nhận exception từ việc đọc file như một chữ ký “INVALID” | Che lỗi triển khai hoặc storage | Phân loại lỗi I/O, lỗi khóa và xác minh sai |
| Sao chép hướng dẫn yêu cầu preview/incubator từ bản JDK cũ | Cấu hình thừa hoặc không khởi động | EdDSA JCA đã là API chuẩn từ JDK 15; xác nhận hỗ trợ trên JVM hiện dùng |

## 8. Checklist hoàn thành và mở rộng bài tập

- [ ] Có một JDK 17+ hỗ trợ Ed25519/Ed448 trong cấu hình provider thực tế.
- [ ] Tạo hai cặp khóa **riêng** để kiểm tra cả khóa đúng và khóa sai.
- [ ] Ký và xác minh **cùng byte tài liệu**, bao gồm cả newline ở cuối.
- [ ] Chỉnh một chữ số hoặc một byte trong bản sao tài liệu → xác minh `INVALID`.
- [ ] Chạy Ed25519 và Ed448, kiểm tra độ dài chữ ký 64 và 114 byte.
- [ ] Xác minh từ **public key khôi phục bằng SPKI DER** ở tiến trình chạy khác.
- [ ] Thử tài liệu rỗng và ký lặp cùng nội dung; có test bảo vệ các bất biến.
- [ ] Không in hoặc commit private key và không gọi API ký cho dữ liệu không được phép ký.
- [ ] Ghi rõ định dạng và nguồn tin cậy của public key, không đánh đồng việc verify với xác minh danh tính.
- [ ] Khi làm production, chuyển khỏi tệp PKCS#8 chưa mã hóa sang hệ quản lý khóa có kiểm soát.
- [ ] Theo dõi lỗi key/algorithm/provider và version giao thức khi triển khai đa hệ thống.

**Bài tập tự làm:** đổi tên thư mục đích và thử xác minh từ một JVM mới; thử sửa một byte ngay giữa tệp, thêm LF cuối, và dùng public key của cặp khóa khác. Sau đó bổ sung `keyId` từ một kho khóa tin cậy và viết test chứng minh rằng khi `keyId` sai hoặc khóa đã bị thu hồi, hệ thống **từ chối** tài liệu dù chữ ký có thể đúng về mặt toán học.

## 9. Tài liệu chính thức và tiêu chuẩn

- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA), JDK 15](https://openjdk.org/jeps/339).
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm: Ed25519 and Ed448](https://www.rfc-editor.org/rfc/rfc8032).
- [Java SE 25 — Security Standard Algorithm Names: Ed25519, Ed448, EdDSA](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html).
- [Java SE 25 — `Signature`: initSign, update, sign, initVerify, verify](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html).
- [Java SE 25 — `KeyFactory`: khôi phục khóa từ key specifications](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html).
- [Java SE 25 — `KeyPairGenerator` và quy trình tạo khóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html).

**Kết quả cốt lõi:** thực hành ký file bằng Ed25519/Ed448 không khó khi dùng API chuẩn của Java. Độ tin cậy của hệ thống nằm ở việc bảo toàn **đúng byte tài liệu**, quản lý private key, phân phối đúng public key và kiểm thử cả ca hợp lệ lẫn ca bị sửa. Chữ ký hợp lệ là một kiểm chứng mật mã; quyết định tin người ký vẫn cần một chính sách riêng.
