# Khóa riêng được bảo vệ bằng mật khẩu và quản lý dữ liệu nhạy cảm

Khi cần lưu hoặc trao đổi private key dưới dạng PEM, hãy dùng cấu trúc **PKCS #8 EncryptedPrivateKeyInfo** với nhãn `ENCRYPTED PRIVATE KEY`. Java cung cấp `PEMEncoder` và `PEMDecoder` để mã hóa/giải mã PEM; `EncryptedPrivateKeyInfo` đảm nhiệm phần bảo vệ private key bằng Password-Based Encryption (PBE). Mật khẩu được dùng để dẫn xuất khóa mã hóa; dữ liệu PEM chứa thuật toán và tham số cần thiết để giải mã về sau.

PEM chỉ là định dạng văn bản Base64 có header/footer. Base64 không mã hóa và không bảo vệ bí mật. Một tệp có nhãn `PRIVATE KEY` vẫn chứa private key không mã hóa dù nội dung nhìn như chuỗi ký tự khó đọc. Tệp được bảo vệ bằng mật khẩu phải có nhãn `ENCRYPTED PRIVATE KEY`, và ứng dụng phải thực sự thực hiện PBE trước khi lưu.

**Trạng thái API tại ngày 27-11-2026:** Java 26 cung cấp PEM API ở Second Preview (JEP 524); Java 27 tiếp tục Third Preview (JEP 538). Vì vậy, ví dụ Java 27 trong bài cần `--enable-preview` ở cả compile và run. JEP 542 đã hoàn tất việc đưa PEM API thành API chính thức trong nhánh JDK 28; tài liệu JDK 28 Early Access có các lớp này ở trạng thái final, nhưng JDK 28 chưa GA và lịch hiện công bố dự kiến ngày 09-03-2027. Khi chạy production, dùng JDK đã phát hành và kiểm tra lại tài liệu của đúng bản build. [JEP 538 — Java 27](https://openjdk.org/jeps/538) · [JEP 542 — Java 28](https://openjdk.org/jeps/542) · [Java 27 `PEMEncoder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html) · [JDK 28 Early Access `PEMDecoder`](https://cr.openjdk.org/~djelinski/quic-tls/java.base/java/security/PEMDecoder.html) · [Lịch phát hành JDK](https://ops.java/releases/?lang=en).

## 1. Phân biệt PEM, PKCS #8 và mã hóa bằng mật khẩu

PEM và PKCS #8 giải quyết hai việc khác nhau:

- **PEM (Privacy-Enhanced Mail)** là lớp biểu diễn văn bản: header, Base64 content và footer. Định dạng được mô tả trong RFC 7468; các cấu trúc nhị phân bên trong thường theo PKCS #8, X.509 hoặc các chuẩn liên quan.
- **PKCS #8** mô tả cấu trúc nhị phân lưu private key. `PrivateKey` thường được mã hóa thành `PrivateKeyInfo`/`OneAsymmetricKey`; dạng được bảo vệ bằng mật khẩu là `EncryptedPrivateKeyInfo`.
- **PBE (Password-Based Encryption)** dùng mật khẩu để tạo khóa mã hóa, sau đó mã hóa dữ liệu private key. Các tham số cần thiết cho quá trình giải mã được lưu trong cấu trúc `EncryptedPrivateKeyInfo`.

Hai nhãn PEM thường gặp là `BEGIN PRIVATE KEY`/`END PRIVATE KEY` và `BEGIN ENCRYPTED PRIVATE KEY`/`END ENCRYPTED PRIVATE KEY`. Phần `BEGIN`/`END` cùng dấu gạch là ranh giới văn bản của PEM; nội dung Base64 ở giữa mới là biểu diễn nhị phân được mã hóa hoặc không mã hóa tùy cấu trúc.

| PEM label | Nội dung | Có bảo vệ bí mật bằng mật khẩu? |
|---|---|---|
| `PRIVATE KEY` | Private key PKCS #8 không mã hóa. | Không. Base64 chỉ đổi cách biểu diễn byte. |
| `ENCRYPTED PRIVATE KEY` | PKCS #8 `EncryptedPrivateKeyInfo`, có thuật toán và dữ liệu đã mã hóa. | Có, nếu cấu trúc thực sự được tạo bằng PBE và mật khẩu đủ mạnh. |
| `PUBLIC KEY` | Public key theo SubjectPublicKeyInfo. | Không cần mã hóa để giữ bí mật; public key vốn được chia sẻ. |
| `CERTIFICATE` | Chứng thư X.509. | Chứng thư thường được công khai; bảo vệ tính toàn vẹn và xác thực chuỗi tin cậy là vấn đề khác. |

Không suy luận mức bảo vệ từ phần mở rộng `.pem`, `.key` hoặc từ việc nội dung đã được Base64. Hãy kiểm tra header/footer và cấu trúc thực tế. Với private key cần lưu trữ có mật khẩu, ưu tiên `ENCRYPTED PRIVATE KEY` theo PKCS #8 và xác minh có thể giải mã bằng một quy trình khôi phục đã kiểm thử.

## 2. PBE hoạt động như thế nào?

PBE chuyển một mật khẩu dễ nhớ thành khóa nhị phân dùng cho thuật toán mã hóa. Tùy thuật toán và provider, quá trình có thể sử dụng:

1. **Password:** bí mật do người vận hành hoặc secret manager cung cấp.
2. **Salt:** dữ liệu ngẫu nhiên dùng khi dẫn xuất khóa; giúp tránh việc cùng mật khẩu luôn tạo ra cùng khóa và làm giảm hiệu quả của bảng tra cứu dựng sẵn.
3. **KDF/work factor:** phép dẫn xuất khóa và tham số độ khó, ví dụ số vòng lặp hoặc chi phí tính toán mà thuật toán yêu cầu.
4. **Cipher và tham số:** thuật toán mã hóa dữ liệu, IV/nonce hoặc các tham số liên quan theo đặc tả.
5. **Encrypted data:** byte của cấu trúc private key sau khi mã hóa.

`EncryptedPrivateKeyInfo` lưu `AlgorithmIdentifier` cùng `encryptedData`. Phần tham số của thuật toán mang thông tin cần thiết để giải mã, chẳng hạn salt và số vòng lặp đối với các thuật toán PBE tương ứng. Do đó, khi giải mã, ứng dụng không tự tạo salt mới; nó đọc lại thuật toán và tham số được đóng gói trong tệp.

```text
Mật khẩu
   |
   v
PBE / dẫn xuất khóa <---- salt + tham số KDF
   |
   v
Khóa mã hóa
   |
   v
Mã hóa PKCS #8 private key
   |
   v
EncryptedPrivateKeyInfo
   |-- AlgorithmIdentifier + parameters
   |-- encryptedData
   v
PEM armor: BEGIN/END ENCRYPTED PRIVATE KEY + Base64
```

Tệp mã hóa có thể bị đánh cắp và thử đoán mật khẩu ngoại tuyến. Vì vậy, chất lượng bảo vệ phụ thuộc cả mật khẩu, KDF/work factor, thuật toán, provider và cách quản lý tệp. Một passphrase ngắn hoặc dễ đoán không trở nên mạnh chỉ vì được đặt vào tệp `ENCRYPTED PRIVATE KEY`.

## 3. API Java dùng trong Java 27

Các lớp liên quan nằm trong module `java.base`; không cần thêm module bằng `--add-modules`.

| API | Vai trò |
|---|---|
| `PEMEncoder` | Chuyển các đối tượng có thể mã hóa thành PEM text hoặc byte array. |
| `PEMDecoder` | Đọc PEM và tạo lại đối tượng Java tương ứng. |
| `EncryptedPrivateKeyInfo` | Đại diện cấu trúc PKCS #8 được mã hóa; hỗ trợ mã hóa/giải mã private key hoặc key pair bằng mật khẩu hay khóa giải mã. |
| `BinaryEncodable` | Interface preview để các đối tượng khóa/chứng thư có thể chuyển đổi từ/đến biểu diễn nhị phân. |
| `CryptoException` | Runtime exception preview báo lỗi trong thao tác mã hóa/giải mã mật mã của API mới. |

Các phương thức thường dùng:

- `PEMEncoder.of()` tạo encoder mặc định.
- `PEMEncoder.withEncryption(char[])` trả về một encoder mới được cấu hình để mã hóa private key, `KeyPair` hoặc `PKCS8EncodedKeySpec` bằng mật khẩu và thuật toán mặc định.
- `PEMDecoder.of()` tạo decoder mặc định.
- `PEMDecoder.withDecryption(char[])` trả về một decoder mới có thể giải mã private key được bảo vệ bằng mật khẩu. Decoder này vẫn có thể đọc PEM không mã hóa.
- `PEMDecoder.decode(data, PrivateKey.class)` hoặc `decode(data, KeyPair.class)` yêu cầu kiểu kết quả cụ thể, tránh ép kiểu không kiểm soát.
- `EncryptedPrivateKeyInfo.encrypt(...)` cho phép tạo cấu trúc mã hóa trực tiếp; overload đầy đủ hơn cho phép chỉ định thuật toán PBE, tham số và provider.
- `EncryptedPrivateKeyInfo.getKey(password)` hoặc `getKeyPair(password)` giải mã nội dung bằng mật khẩu.

Khi decoder chưa được cấu hình giải mã, PEM có nhãn `ENCRYPTED PRIVATE KEY` được trả về dưới dạng `EncryptedPrivateKeyInfo`. Đây là lựa chọn hữu ích khi cần kiểm tra thuật toán và tham số trước, rồi mới giải mã. Khi decoder đã cấu hình `withDecryption`, decoder có thể trả thẳng `PrivateKey` hoặc `KeyPair` nếu nội dung có đủ dữ liệu public/private key.

### Thay đổi API qua các release

Không sao chép nguyên xi ví dụ từ preview cũ:

| Release | JEP / trạng thái | Điểm cần biết |
|---|---|---|
| Java 25 | JEP 470 — Preview lần đầu. | Có `DEREncodable`, `PEMEncoder`, `PEMDecoder` và `PEMRecord`. |
| Java 26 | JEP 524 — Second Preview. | Đổi `PEMRecord` thành `PEM`; bổ sung hỗ trợ mã hóa/giải mã `KeyPair` và `PKCS8EncodedKeySpec`. Interface vẫn tên `DEREncodable`. |
| Java 27 | JEP 538 — Third Preview. | `DEREncodable` đổi thành `BinaryEncodable`; `PEM` trở thành class; `withFactory` đổi thành `withFactoriesOf`; có `CryptoException` cho lỗi xử lý mật mã. |
| JDK 28 Early Access | JEP 542 — API chính thức, `Since: 28`. | API không còn cần cờ preview trong build đã tích hợp JEP 542; JDK 28 vẫn chưa GA tại ngày cập nhật bài. |

Ví dụ trong bài dùng chữ ký Java 27 Third Preview và cũng là API đã được tích hợp thành final trong JDK 28. Nếu build bằng JDK 26, hãy mở Javadoc Java 26 và điều chỉnh theo `DEREncodable` cùng chữ ký preview của release đó. [Java 26 Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html) · [Java 27 Preview API List](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html) · [Java 27 `BinaryEncodable`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html).

## 4. Mã hóa một KeyPair thành `ENCRYPTED PRIVATE KEY`

Ví dụ sau tạo một cặp khóa EC, nhận passphrase trực tiếp từ console, mã hóa key pair bằng PBE, rồi ghi PEM byte array ra tệp mới. Không đặt mật khẩu trong mã nguồn, tham số dòng lệnh hoặc log.

```java
import java.io.Console;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PEMEncoder;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;
import javax.crypto.EncryptedPrivateKeyInfo;

public class WriteEncryptedPemKey {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run from a terminal that provides a Console"
            );
        }

        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair keyPair = generator.generateKeyPair();

        char[] password = console.readPassword("Passphrase for private key: ");
        if (password == null) {
            throw new IllegalArgumentException("A passphrase is required");
        }

        byte[] pemBytes = null;
        try {
            if (password.length == 0) {
                throw new IllegalArgumentException("A non-empty passphrase is required");
            }

            // Tạo EncryptedPrivateKeyInfo bằng PBE mặc định của JDK/provider.
            EncryptedPrivateKeyInfo encrypted =
                    EncryptedPrivateKeyInfo.encrypt(keyPair, password);

            // Xem thuật toán và tham số thực tế đã được chọn.
            System.out.println("PBE algorithm: " + encrypted.getAlgName());
            System.out.println("PBE parameters: " + encrypted.getAlgParameters());

            // PEMEncoder đóng gói EncryptedPrivateKeyInfo thành ENCRYPTED PRIVATE KEY.
            pemBytes = PEMEncoder.of().encode(encrypted);

            Path output = Path.of("service-private-key.pem");
            Files.write(
                    output,
                    pemBytes,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );
            System.out.println("Encrypted private key written to " + output);
        } finally {
            // Xóa bản password do ứng dụng sở hữu và buffer PEM tạm trong RAM.
            Arrays.fill(password, '\0');
            if (pemBytes != null) {
                Arrays.fill(pemBytes, (byte) 0);
            }
        }
    }
}
```

`EncryptedPrivateKeyInfo.encrypt(KeyPair, char[])` hỗ trợ `KeyPair` và tạo cấu trúc PKCS #8 v2.0 `OneAsymmetricKey`, có thể mang cả private key và public key. Khi `PEMEncoder` mã hóa đối tượng `EncryptedPrivateKeyInfo`, nhãn được sinh là `ENCRYPTED PRIVATE KEY`.

`CREATE_NEW` giúp ví dụ không vô tình ghi đè tệp khóa đã tồn tại. Trong hệ thống thật, thư mục đích và tệp phải có quyền truy cập hạn chế; trên Linux có thể tạo với quyền `rw-------`, còn Windows cần ACL chỉ cấp cho tài khoản dịch vụ và nhóm quản trị cần thiết. Hãy áp dụng quyền tệp trước khi dữ liệu bí mật được ghi, đồng thời bảo vệ thư mục backup và bản sao triển khai.

### Cách ngắn hơn bằng `PEMEncoder.withEncryption`

Nếu chỉ cần dùng thuật toán mặc định, có thể để `PEMEncoder` thực hiện cả mã hóa và PEM encoding:

```java
byte[] pemBytes = PEMEncoder.of()
        .withEncryption(password)
        .encode(keyPair);
```

Encoder đã cấu hình mã hóa chỉ chấp nhận `PrivateKey`, `KeyPair` và `PKCS8EncodedKeySpec`. Gọi nó với certificate hoặc một đối tượng khác sẽ ném `IllegalArgumentException`. Cách hai bước qua `EncryptedPrivateKeyInfo` hữu ích hơn khi cần kiểm tra thuật toán/tham số hoặc tự chọn PBE provider.

## 5. Đọc và giải mã private key bằng mật khẩu

Có hai cách đọc một tệp `ENCRYPTED PRIVATE KEY`.

### Cách A: cấu hình decoder để giải mã trực tiếp

```java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.PEMDecoder;
import java.util.Arrays;

public class ReadEncryptedPemKey {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException("A terminal Console is required");
        }

        char[] password = console.readPassword("Private key passphrase: ");
        if (password == null) {
            throw new IllegalArgumentException("Passphrase was not supplied");
        }

        try {
            try (InputStream input = Files.newInputStream(
                    Path.of("service-private-key.pem"))) {

                KeyPair keyPair = PEMDecoder.of()
                        .withDecryption(password)
                        .decode(input, KeyPair.class);

                // Dùng keyPair trong tác vụ cần thiết; không log hoặc xuất private key.
                System.out.println("Loaded key algorithm: "
                        + keyPair.getPrivate().getAlgorithm());
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

`decode(input, KeyPair.class)` yêu cầu nội dung có cả public key và private key. Nếu tệp chỉ chứa private key, hãy yêu cầu `PrivateKey.class`. Dùng overload có `Class` giúp compiler và API kiểm tra kiểu kết quả, tránh cast không đúng loại.

### Cách B: đọc `EncryptedPrivateKeyInfo` rồi giải mã

Cách này tách bước đọc PEM khỏi bước dùng mật khẩu:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PrivateKey;
import java.security.PEMDecoder;
import javax.crypto.EncryptedPrivateKeyInfo;

static PrivateKey readPrivateKey(Path path, char[] password) throws Exception {
    EncryptedPrivateKeyInfo encrypted;
    try (InputStream input = Files.newInputStream(path)) {
        encrypted = PEMDecoder.of().decode(
                input,
                EncryptedPrivateKeyInfo.class
        );
    }

    System.out.println("PBE algorithm: " + encrypted.getAlgName());
    System.out.println("PBE parameters: " + encrypted.getAlgParameters());

    return encrypted.getKey(password);
}
```

Ở đây `PEMDecoder.of()` không nhận password nên trả về `EncryptedPrivateKeyInfo`, chưa giải mã private key. Sau khi có thể kiểm tra thuật toán và tham số, `getKey(password)` mới giải mã nội dung. Nếu cấu trúc chứa cả public key, dùng `getKeyPair(password)` để nhận `KeyPair`.

Không ghi private key sau giải mã vào tệp tạm không mã hóa. Nếu chỉ cần ký hoặc giải mã dữ liệu, hãy dùng `PrivateKey` trực tiếp trong thao tác đó rồi bỏ tham chiếu sớm nhất có thể.

## 6. Chọn thuật toán PBE và kiểm tra tham số

Khi dùng `PEMEncoder.withEncryption(char[])` hoặc `EncryptedPrivateKeyInfo.encrypt(BinaryEncodable, char[])`, JDK chọn thuật toán PBE mặc định theo security property `jdk.epkcs8.defaultAlgorithm`. Tham số mặc định cụ thể do provider quyết định. Giá trị mặc định có thể thay đổi theo JDK hoặc provider; không nên hard-code giả định rằng mọi máy đều dùng cùng thuật toán.

JCA Reference Guide mô tả cách kiểm tra:

```java
EncryptedPrivateKeyInfo encrypted =
        EncryptedPrivateKeyInfo.encrypt(privateKey, password);

String algorithm = encrypted.getAlgName();
AlgorithmParameters parameters = encrypted.getAlgParameters();

System.out.println("Algorithm: " + algorithm);
System.out.println("Parameters: " + parameters);
```

Đối với một hệ thống có yêu cầu tuân thủ cụ thể, cần xác định rõ:

- PBE algorithm và cipher được provider hỗ trợ, ví dụ một tổ hợp PBE dùng HMAC-SHA-256 và AES.
- Salt được tạo ngẫu nhiên, không tái sử dụng thủ công giữa các tệp khóa.
- Work factor/iteration count phù hợp chính sách bảo mật và hiệu năng của hệ thống.
- Provider đang được sử dụng và chính sách cryptographic của runtime.
- Khả năng tương thích với công cụ cần đọc tệp khóa, ví dụ OpenSSL hoặc hệ thống quản lý khóa khác.

Nếu cần tự chỉ định thuật toán và tham số, dùng overload:

```java
EncryptedPrivateKeyInfo encrypted = EncryptedPrivateKeyInfo.encrypt(
        privateKey,
        password,
        "PBEWithHmacSHA256AndAES_256",
        pbeParameterSpec,
        provider
);
```

`pbeParameterSpec` và `provider` phải tương thích với thuật toán đã chọn. Ví dụ trên chỉ minh họa hình dạng lời gọi; không sao chép một `PBEParameterSpec` tùy tiện hoặc tự đặt số vòng lặp thấp. Hãy dùng tham số do security/provider team phê duyệt, kiểm tra tài liệu provider và xác minh khả năng giải mã trên runtime đích. Nếu `params` là `null`, provider có thể áp dụng tham số mặc định của nó.

Các tham số thuật toán được lưu cùng `EncryptedPrivateKeyInfo`. Vì thế, thay đổi giá trị `jdk.epkcs8.defaultAlgorithm` trên một JDK tương lai không tự làm cho tệp đã tạo trước đó không thể giải mã; tệp chứa algorithm identifier và tham số cần thiết. Tuy vậy, runtime tương lai vẫn phải hỗ trợ thuật toán/provider tương ứng. Khi chọn thuật toán, ưu tiên thuật toán hiện hành được tổ chức chấp nhận và có lộ trình hỗ trợ dài hạn.

## 7. Quản lý password và dữ liệu nhạy cảm trong bộ nhớ

Mật khẩu và private key đều là dữ liệu nhạy cảm. Cần kiểm soát từ lúc thu thập, truyền vào API, lưu trữ cho đến khi kết thúc thao tác.

### Ưu tiên `char[]` thay vì `String`

`String` là immutable; ứng dụng không thể chủ động ghi đè nội dung của nó sau khi sử dụng. `char[]` cho phép xóa bản dữ liệu do ứng dụng sở hữu:

```java
char[] password = console.readPassword("Passphrase: ");
try {
    // Truyền password vào API mật mã.
} finally {
    Arrays.fill(password, '\0');
}
```

Không chuyển password thành `String` chỉ để tiện nối chuỗi, ghi log hoặc lưu vào cấu hình. Không đặt password trong exception message, log statement, telemetry, crash report, command-line argument hay source control. Với ứng dụng không có `Console`, lấy secret từ secret manager hoặc cơ chế cấp phát bí mật được kiểm soát của nền tảng triển khai.

### Lưu ý về việc API sao chép password

Javadoc của Java 27 nêu rõ `withEncryption(char[])` và `withDecryption(char[])` sao chép mảng password và lưu bản sao trong instance mới. Việc gọi `Arrays.fill(password, '\0')` chỉ xóa mảng gốc do ứng dụng giữ; không xóa được bản sao nội bộ của encoder/decoder. Các lớp này immutable và thread-safe, nhưng không cung cấp API để xóa password nội bộ một cách xác định.

Vì vậy:

- Dùng encoder/decoder cấu hình password trong phạm vi ngắn nhất có thể.
- Không lưu một `PEMEncoder.withEncryption(password)` hoặc `PEMDecoder.withDecryption(password)` đã cấu hình vào singleton, static field hay cache dài hạn.
- Xóa mảng password gốc trong `finally`.
- Nếu cần tránh giữ password trong một codec instance, có thể dùng `EncryptedPrivateKeyInfo.encrypt(...)` hoặc `getKey(...)` với `char[]` cho một thao tác; các phương thức này cũng sao chép mảng trước khi dùng nhưng không tạo một decoder/encoder cấu hình lâu dài.
- Không tuyên bố rằng xóa `char[]` bảo đảm mọi bản sao đã biến mất khỏi heap; provider, runtime hoặc thư viện có thể tạo bản sao tạm khác.

Ví dụ an toàn hơn về vòng đời:

```java
char[] password = console.readPassword("Passphrase: ");
try {
    EncryptedPrivateKeyInfo encrypted =
            EncryptedPrivateKeyInfo.encrypt(keyPair, password);
    byte[] pem = PEMEncoder.of().encode(encrypted);
    try {
        Files.write(
                target,
                pem,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
        );
    } finally {
        Arrays.fill(pem, (byte) 0);
    }
} finally {
    Arrays.fill(password, '\0');
}
```

### Không để private key plaintext tồn tại lâu

Sau khi giải mã, `PrivateKey` là một đối tượng có thể thực hiện ký hoặc giải mã. Việc tệp trên đĩa đã được mã hóa không làm cho đối tượng private key trong heap tự động được mã hóa. Hãy:

- Chỉ giải mã khi sắp thực hiện thao tác cần private key.
- Không gọi `getEncoded()` rồi lưu byte array plaintext nếu không có yêu cầu đặc biệt.
- Không ghi `PrivateKey`, `KeyPair`, PEM content hoặc password vào log.
- Hạn chế số bản sao và phạm vi tham chiếu tới private key; tránh đưa vào cache lâu dài nếu không cần.
- Không giả định garbage collection sẽ xóa dữ liệu nhạy cảm ngay lập tức hoặc xóa sạch mọi bản sao trong heap.

## 8. Lưu trữ, phân phối, backup và rotation

Mã hóa tệp bằng mật khẩu chỉ giải quyết một phần bài toán quản lý khóa. Cần bảo vệ cả tệp, password, bản sao và vòng đời khóa.

| Tài sản | Cách quản lý |
|---|---|
| Tệp `ENCRYPTED PRIVATE KEY` | Lưu trong thư mục hạn chế quyền; không commit vào Git, package công khai hoặc image container. |
| Passphrase | Lưu riêng trong secret manager hoặc cơ chế cấp phát bí mật được bảo vệ; không lưu cùng thư mục với tệp PEM. |
| Bản backup | Mã hóa và kiểm soát quyền tương đương bản chính; kiểm tra khôi phục định kỳ. |
| Public key/certificate | Có thể phân phối rộng hơn, nhưng vẫn cần xác minh nguồn, chuỗi chứng thư, thời hạn và trạng thái thu hồi. |
| Private key sau giải mã | Chỉ giữ trong tiến trình và thời gian cần thiết; không ghi ra file tạm plaintext. |

Nếu passphrase bị lộ, giả định mọi bản PEM dùng passphrase đó có thể bị giải mã. Hãy có quy trình rotation: tạo key pair mới, cập nhật chứng thư hoặc public key ở các hệ thống phụ thuộc, chuyển dịch vụ sang key mới, thu hồi hoặc vô hiệu hóa key cũ khi phù hợp, và kiểm soát backup cũ theo chính sách lưu giữ.

Nếu mất passphrase, dữ liệu `ENCRYPTED PRIVATE KEY` có thể không khôi phục được. Không có API Java nào có thể bỏ qua mật khẩu hợp lệ để khôi phục private key. Do đó, phải kiểm tra backup và quy trình khôi phục trước khi chuyển khóa vào production.

### Khi nào nên dùng keystore hoặc HSM thay cho PEM?

PEM phù hợp cho trao đổi, bootstrap, tích hợp công cụ và lưu trữ file có kiểm soát. Nếu ứng dụng cần quản lý vòng đời khóa, alias, certificate chain và bảo vệ bằng cơ chế của nền tảng, cân nhắc `KeyStore` với loại hiện hành như `PKCS12`. Nếu private key không được phép xuất khỏi thiết bị, dùng HSM, smart card hoặc provider PKCS#11; trong trường hợp đó, PEM export có thể không khả dụng và cũng không nên cố xuất khóa ra ngoài.

Mã hóa PEM bằng mật khẩu không thay thế HSM/KMS, quyền truy cập hệ điều hành, audit, rotation hoặc chính sách phân quyền người vận hành.

## 9. Lỗi thường gặp khi giải mã

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `CryptoException` khi giải mã | Password sai, dữ liệu mã hóa hỏng hoặc provider không thực hiện được thao tác mật mã. | Xác minh secret được cấp, kiểm tra tệp và provider; không log password. |
| `IllegalArgumentException` khi decode | PEM syntax sai, không có PEM block hoặc kiểu PEM không được hỗ trợ. | Kiểm tra header/footer, Base64 và dùng đúng overload `decode(..., Class)`. |
| `ClassCastException` | Loại PEM không khớp class được yêu cầu. | Yêu cầu đúng `PrivateKey.class`, `KeyPair.class` hoặc `EncryptedPrivateKeyInfo.class`. |
| Nhận `EncryptedPrivateKeyInfo` thay vì `PrivateKey` | Decoder chưa được cấu hình giải mã. | Gọi `withDecryption(password)` hoặc gọi `getKey(password)` trên `EncryptedPrivateKeyInfo`. |
| Không đọc được `KeyPair` | Nội dung mã hóa chỉ có private key, không có public key. | Dùng `PrivateKey.class` hoặc tạo PEM từ `KeyPair` nếu cần cả hai. |
| Không hỗ trợ thuật toán PBE | Provider/runtime không có thuật toán được ghi trong `AlgorithmIdentifier`. | Kiểm tra provider, algorithm name và chính sách crypto của runtime; không thay tham số ngẫu nhiên. |
| Tệp bị đọc như văn bản nhưng không giải mã được | PEM chỉ là Base64; có thể nhãn là `PRIVATE KEY` không mã hóa hoặc là định dạng khác. | Kiểm tra PEM label và loại cấu trúc bên trong. |
| Password đã xóa nhưng còn trong codec | `withEncryption`/`withDecryption` giữ bản sao password trong instance. | Dùng instance ngắn hạn; không giữ codec đã cấu hình trong singleton/cache. |

Khi decoder đọc từ `InputStream`, nếu gặp lỗi I/O hoặc lỗi cú pháp, vị trí stream có thể không còn nhất quán. Không tiếp tục decode nhiều block trên cùng stream sau khi đã xảy ra lỗi; mở stream mới hoặc xử lý từng block theo ranh giới rõ ràng.

## 10. Tương thích JDK và cách bật preview

PEM API là preview trong Java 26 và Java 27. Ví dụ dùng chữ ký Java 27 Third Preview:

```bash
# Biên dịch bằng JDK 27
javac --release 27 --enable-preview -d out src/WriteEncryptedPemKey.java

# Chạy bằng JDK 27
java --enable-preview -cp out WriteEncryptedPemKey
```

Phải bật preview ở cả compiler và runtime. Class file dùng preview gắn với release đã biên dịch; không lấy class file preview của Java 27 để chạy bằng JDK 28. Hãy biên dịch lại bằng JDK mục tiêu.

JDK 28 Early Access có JEP 542 đưa PEM API thành chính thức và các Javadoc có `Since: 28`, không còn nhãn preview. Với một build JDK 28 EA đã tích hợp JEP 542, có thể biên dịch/chạy mà không cần `--enable-preview`. Tuy nhiên, JDK 28 chưa GA tại ngày cập nhật bài; không coi Early Access là runtime production được hỗ trợ. Khi JDK 28 phát hành, dùng JDK 28 GA và Javadoc tương ứng để xác nhận hợp đồng cuối cùng.

Không cần `--add-modules` vì các lớp thuộc `java.base`. Với ứng dụng modular, module descriptor không cần thêm `requires` cho `java.base` vì đây là module nền tảng được đọc mặc định.

## 11. Checklist trước khi đưa khóa vào production

- [ ] Đã xác nhận PEM label là `ENCRYPTED PRIVATE KEY` và nội dung là PKCS #8 EncryptedPrivateKeyInfo.
- [ ] Đã hiểu Base64/PEM không tự mã hóa dữ liệu.
- [ ] Đã dùng PBE algorithm/provider được tổ chức phê duyệt và kiểm tra `getAlgName()` cùng `getAlgParameters()`.
- [ ] Đã dùng passphrase có entropy cao; đã tính đến khả năng đoán mật khẩu ngoại tuyến nếu tệp bị đánh cắp.
- [ ] Đã lấy password từ Console hoặc secret manager; không hard-code, không truyền qua command-line, không log.
- [ ] Đã dùng `char[]` và xóa bản do ứng dụng sở hữu trong `finally`.
- [ ] Đã hiểu `withEncryption`/`withDecryption` clone và giữ password trong instance; codec đã cấu hình chỉ tồn tại trong phạm vi ngắn.
- [ ] Đã hạn chế quyền đọc tệp PEM, backup và thư mục chứa khóa.
- [ ] Đã thử giải mã bằng đúng JDK/provider sẽ dùng ở production.
- [ ] Đã thử quy trình sai password, tệp hỏng và khôi phục từ backup.
- [ ] Đã không ghi private key plaintext vào log, file tạm hoặc cache dài hạn.
- [ ] Đã có quy trình rotation, thu hồi và xử lý khi password bị lộ hoặc bị mất.
- [ ] Đã cân nhắc PKCS12 keystore, KMS hoặc HSM nếu cần quản lý vòng đời hoặc khóa không xuất được.
- [ ] Đã xác nhận trạng thái preview/final và biên dịch lại với đúng JDK release.

## Tài liệu tham khảo chính thức

- [JEP 538: PEM Encodings of Cryptographic Objects (Third Preview)](https://openjdk.org/jeps/538)
- [JEP 542: PEM Encodings of Cryptographic Objects (Java 28)](https://openjdk.org/jeps/542)
- [Java SE 27 — `PEMEncoder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html)
- [Java SE 27 — `PEMDecoder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html)
- [Java SE 27 — `EncryptedPrivateKeyInfo`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [Java SE 27 — `BinaryEncodable`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/BinaryEncodable.html)
- [Java Cryptography Architecture Reference Guide — PEM and EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 26 — JDK 26 Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Java SE 27 — JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468)
- [RFC 5958: Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958)
- [JDK Releases and Support Timeline](https://ops.java/releases/?lang=en)

*Cập nhật nội dung: 27-11-2026. Ví dụ API dùng Java 27 Third Preview; JDK 28 Early Access đã tích hợp JEP 542 thành API chính thức nhưng chưa GA. Kiểm tra JDK/provider và chính sách mật mã đang triển khai trước khi lưu hoặc phân phối private key.*
