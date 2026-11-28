# SecretKeyEntry

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích `KeyStore.SecretKeyEntry` dùng để lưu một khóa bí mật đối xứng trong Java KeyStore.
- Phân biệt `SecretKeyEntry`, `PrivateKeyEntry` và `TrustedCertificateEntry`.
- Sử dụng `KeyStore.setEntry`, `getEntry`, `PasswordProtection`, `load` và `store` đúng mục đích.
- Phân biệt mật khẩu bảo vệ file KeyStore với mật khẩu bảo vệ từng entry.
- Nhận diện sự khác nhau giữa các KeyStore type và giới hạn tương thích của provider.
- Thiết kế cách lưu, đọc, xoay vòng, backup và thu hồi secret key an toàn trong ứng dụng Java.
- Xác định khi nào file KeyStore phù hợp và khi nào nên dùng HSM, KMS hoặc secret management service.

## 1. SecretKeyEntry là gì?

`KeyStore.SecretKeyEntry` là một kiểu entry trong Java KeyStore dùng để đại diện cho một `SecretKey`. Secret key là khóa bí mật được dùng trong các thuật toán đối xứng, chẳng hạn AES để mã hóa/giải mã hoặc HMAC để tạo và xác minh message authentication code.

Java KeyStore (JKS API) cung cấp một lớp trừu tượng để quản lý key và certificate theo alias. Thay vì tự ghi key bytes vào file, ứng dụng tạo một `SecretKeyEntry`, đưa entry vào KeyStore bằng `setEntry`, sau đó lưu KeyStore qua provider đang sử dụng.

Ví dụ khái quát:

```java
KeyStore.SecretKeyEntry entry = new KeyStore.SecretKeyEntry(secretKey);
KeyStore.ProtectionParameter protection =
        new KeyStore.PasswordProtection(entryPassword);

keyStore.setEntry("payment-aes-v1", entry, protection);
```

`SecretKeyEntry` chỉ là container cho đối tượng `SecretKey`. Việc entry được mã hóa ra sao, có thể lưu được hay không và cần protection parameter nào phụ thuộc vào KeyStore provider và loại KeyStore được chọn.

## 2. SecretKeyEntry nằm ở đâu trong Java KeyStore?

`java.security.KeyStore` là API quản lý kho khóa. Nó không tự định nghĩa một định dạng file duy nhất. Provider được chọn sẽ cung cấp implementation, định dạng lưu trữ, cơ chế bảo vệ và các khả năng cụ thể.

Một KeyStore có thể chứa nhiều loại entry:

| Entry type | Nội dung | Mục đích thường gặp |
|---|---|---|
| `SecretKeyEntry` | Một khóa bí mật đối xứng | AES, HMAC hoặc secret key khác được provider hỗ trợ |
| `PrivateKeyEntry` | Private key cùng certificate chain | TLS server, ký số, client authentication |
| `TrustedCertificateEntry` | Một trusted certificate | Trust anchor hoặc certificate tin cậy |

`SecretKeyEntry` không phải `PrivateKeyEntry`. Secret key không có certificate chain như private key bất đối xứng. Cũng không phải `TrustedCertificateEntry`, vì certificate công khai không chứa secret key.

## 3. SecretKey và SecretKeyEntry khác nhau thế nào?

`SecretKey` là abstraction của khóa mật mã trong Java Cryptography Architecture (JCA). Nó có thể được tạo bởi `KeyGenerator`, `SecretKeyFactory`, provider HSM hoặc một implementation khác.

`SecretKeyEntry` là đối tượng entry dùng để đưa `SecretKey` vào KeyStore API. Có thể hiểu:

```text
KeyGenerator / KMS / HSM
          |
          v
      SecretKey
          |
          v
  SecretKeyEntry
          |
          v
 KeyStore.setEntry(...)
          |
          v
 Provider-specific storage
```

Một `SecretKey` có thể tồn tại và được sử dụng mà không cần đưa vào KeyStore. Ngược lại, KeyStore chỉ lưu được loại key mà provider của nó hỗ trợ. Việc tạo được `SecretKeyEntry` trong bộ nhớ không chứng minh provider có thể persist entry đó.

## 4. Các API chính của SecretKeyEntry

`KeyStore.SecretKeyEntry` có constructor nhận một `SecretKey` và method `getSecretKey()` để lấy lại key.

```java
SecretKey secretKey = ...;
KeyStore.SecretKeyEntry entry =
        new KeyStore.SecretKeyEntry(secretKey);

SecretKey restored = entry.getSecretKey();
```

Các API liên quan thường dùng:

| API | Vai trò |
|---|---|
| `KeyStore.getInstance(type)` | Chọn KeyStore type/provider |
| `KeyStore.load(...)` | Nạp hoặc khởi tạo KeyStore |
| `KeyStore.setEntry(...)` | Lưu entry cùng protection parameter |
| `KeyStore.getEntry(...)` | Đọc entry theo alias và protection parameter |
| `KeyStore.entryInstanceOf(...)` | Kiểm tra kiểu entry theo alias |
| `KeyStore.containsAlias(...)` | Kiểm tra alias tồn tại |
| `KeyStore.deleteEntry(...)` | Xóa entry theo alias |
| `KeyStore.store(...)` | Ghi KeyStore ra output stream |
| `KeyStore.aliases()` | Liệt kê alias |

Với secret key, `setEntry` và `getEntry` là cặp API rõ ràng vì chúng thể hiện cả kiểu entry và cơ chế bảo vệ entry.

## 5. Vì sao dùng setEntry thay vì tự ghi key bytes?

Tự ghi `secretKey.getEncoded()` ra file thường tạo ra một bản sao plaintext của key material. File đó có thể bị đọc qua backup, log, crash dump, artifact CI/CD, quyền filesystem hoặc bản sao tạm.

KeyStore cung cấp abstraction để provider quản lý cách lưu và bảo vệ entry. Tuy vậy, điều này không có nghĩa mọi KeyStore đều an toàn như HSM. Với software KeyStore, key material có thể được mã hóa trong file bằng cơ chế của provider và được giải mã trong process khi đọc entry.

Ưu điểm của `setEntry` là ứng dụng không cần tự thiết kế định dạng serialization cho key. Ứng dụng vẫn phải chọn provider, bảo vệ password, giới hạn file access và quản lý vòng đời key.

## 6. KeyStore type và khả năng lưu secret key

Khả năng lưu `SecretKeyEntry` phụ thuộc KeyStore type và provider. Một số loại thường gặp:

| Type | Đặc điểm | Lưu SecretKeyEntry |
|---|---|---|
| `JCEKS` | Software KeyStore của JDK, thường được dùng trong ví dụ về secret key | Được implementation JDK hỗ trợ; cần đánh giá thuật toán bảo vệ và mục tiêu tương thích |
| `JKS` | Định dạng KeyStore Java truyền thống | Không nên giả định hỗ trợ secret key; thường dùng cho private key và certificate |
| `PKCS12` | Định dạng trao đổi/lưu trữ chuẩn hóa, phổ biến cho private key và certificate | Hỗ trợ secret key tùy JDK/provider; phải kiểm thử implementation thực tế |
| `PKCS11` | Giao tiếp với token hoặc HSM qua PKCS#11 provider | Phụ thuộc thiết bị, provider và khả năng lưu object secret key |
| Provider-specific | Định dạng riêng của nhà cung cấp | Theo tài liệu và capability của provider |

Không nên chọn type chỉ vì tên phổ biến. Hãy xác minh provider cụ thể có hỗ trợ `SecretKeyEntry`, thuật toán key, protection parameter, backup/restore và khả năng interoperability mà ứng dụng cần.

## 7. JCEKS, PKCS12 và PKCS11 trong thực tế

### JCEKS

JCEKS thường được dùng để minh họa lưu symmetric secret key trong Java. Nó là software KeyStore type gắn với implementation của JDK. Đây là ví dụ dễ chạy trong môi trường Java tiêu chuẩn, nhưng không nên mặc định xem JCEKS là lựa chọn tốt nhất cho một hệ thống mới mà chưa đánh giá thuật toán bảo vệ, khả năng tương thích và yêu cầu vận hành.

### PKCS12

PKCS12 phổ biến để trao đổi private key và certificate. Khả năng lưu secret key có thể khác giữa JDK, provider và công cụ đọc file. Nếu ứng dụng cần lưu `SecretKeyEntry` trong PKCS12, cần kiểm thử cả ghi, đọc, import/export và tương thích với công cụ ngoài Java.

### PKCS11

PKCS11 thường đại diện cho token hoặc HSM. Entry có thể tham chiếu tới object được giữ trong thiết bị thay vì serialize key bytes ra file thông thường. Không phải mọi HSM/provider đều hỗ trợ cùng loại secret key, extractability, persistence hoặc protection parameter.

## 8. Alias là định danh entry

KeyStore dùng alias để định danh entry. Ví dụ:

```text
payments-aes-v1
payments-hmac-v2
tenant-42-data-dek-v3
```

Alias không phải key material và cũng không phải cơ chế phân quyền. Nó là tên để ứng dụng tìm entry. Nếu nhiều môi trường hoặc tenant dùng chung một KeyStore, alias cần có quy ước rõ để tránh nhầm mục đích hoặc phạm vi dữ liệu.

Nên gắn alias với purpose và version, tránh tái sử dụng alias cũ cho key khác mà không có migration. Không đưa dữ liệu cá nhân, token hay secret vào alias. Cũng không nên coi alias khó đoán là một lớp bảo mật.

## 9. ProtectionParameter và PasswordProtection

`KeyStore.ProtectionParameter` là abstraction cho thông tin bảo vệ entry. Với KeyStore software, kiểu thường dùng là `KeyStore.PasswordProtection`.

```java
char[] entryPassword = obtainEntryPassword();
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(entryPassword);

keyStore.setEntry(
        "payments-aes-v1",
        new KeyStore.SecretKeyEntry(secretKey),
        protection);
```

`PasswordProtection` giữ password dùng khi bảo vệ hoặc khôi phục entry. Password này được truyền vào `setEntry` hoặc `getEntry`; provider quyết định cách sử dụng nó.

`PasswordProtection` cũng có constructor cho phép chỉ định protection algorithm và parameters. Không nên tự chọn thuật toán cũ hoặc yếu chỉ vì provider chấp nhận. Cần dùng lựa chọn được provider hỗ trợ và policy bảo mật hiện hành.

## 10. Store password và entry password

Hai lớp password thường bị nhầm:

| Password | Được dùng ở đâu | Mục đích |
|---|---|---|
| KeyStore password | `load(input, storePassword)` và `store(output, storePassword)` | Mở, kiểm tra integrity hoặc bảo vệ toàn bộ KeyStore theo semantics provider |
| Entry password | `PasswordProtection(entryPassword)` khi `setEntry`/`getEntry` | Bảo vệ hoặc khôi phục một entry cụ thể theo provider |

Hai password có thể giống nhau trong một số ví dụ đơn giản, nhưng không nên mặc định gộp chúng trong production. Tách password giúp giảm phạm vi khi một lớp bị lộ và cho phép policy khác nhau.

Không phải provider nào cũng triển khai hai lớp giống nhau. Một số KeyStore type có thể bỏ qua hoặc hạn chế protection parameter ở một số thao tác; provider khác có thể yêu cầu password cụ thể. Cần kiểm thử hành vi thực tế thay vì suy luận từ API chung.

## 11. Khởi tạo KeyStore mới

Để tạo KeyStore mới trong bộ nhớ, gọi `load(null, password)` sau khi lấy instance. Với một số provider, đây là cách khởi tạo kho rỗng.

```java
KeyStore keyStore = KeyStore.getInstance("JCEKS");
keyStore.load(null, storePassword);
```

`load(null, ...)` khác với nạp file đã tồn tại. Nếu file đã có, cần mở input stream và gọi `load(input, storePassword)`. Nếu password sai hoặc file hỏng, provider có thể ném `IOException`, `NoSuchAlgorithmException` hoặc `CertificateException` tùy trường hợp.

## 12. Tạo SecretKey bằng KeyGenerator

Với khóa AES, `KeyGenerator` là API JCA thường dùng. Để tạo key 256-bit:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);
SecretKey key = generator.generateKey();
```

Key generation nên dùng provider và `SecureRandom` phù hợp. Với HSM, key có thể được tạo bên trong thiết bị và không export được. Không nên tự tạo key bằng `new byte[]` chứa giá trị cố định trong source code.

Với HMAC, chọn algorithm phù hợp như `HmacSHA256` và kích thước key theo policy. Không dùng cùng một key cho AES encryption và HMAC chỉ để tiết kiệm entry; tách key theo purpose giúp giảm rủi ro và dễ quản trị.

## 13. Lưu SecretKeyEntry vào KeyStore

Quy trình lưu cơ bản:

1. Lấy KeyStore instance với type/provider đã chọn.
2. Load kho hiện có hoặc khởi tạo kho mới.
3. Tạo `SecretKey` bằng nguồn phù hợp.
4. Tạo `SecretKeyEntry`.
5. Tạo protection parameter cho entry.
6. Gọi `setEntry(alias, entry, protection)`.
7. Gọi `store(output, storePassword)` để ghi thay đổi.
8. Đóng stream và giải phóng password buffer theo khả năng API.

Nếu chỉ gọi `setEntry` mà không gọi `store`, thay đổi có thể chỉ tồn tại trong object KeyStore ở bộ nhớ và mất khi process kết thúc.

## 14. Đọc SecretKeyEntry từ KeyStore

Để lấy entry, ứng dụng load KeyStore từ file, sau đó gọi `getEntry` với alias và protection parameter tương ứng.

```java
KeyStore.Entry value = keyStore.getEntry(
        "payments-aes-v1",
        new KeyStore.PasswordProtection(entryPassword));

if (!(value instanceof KeyStore.SecretKeyEntry secretEntry)) {
    throw new KeyStoreException("Entry is missing or has the wrong type");
}

SecretKey key = secretEntry.getSecretKey();
```

Nếu alias không tồn tại, `getEntry` có thể trả `null`. Nếu password sai hoặc entry không thể khôi phục, provider có thể ném `UnrecoverableEntryException`. Cần phân biệt entry không tồn tại, sai loại và không giải mã được để log và xử lý chính xác.

## 15. getEntry khác getKey thế nào?

`KeyStore.getKey(alias, password)` trả về đối tượng `Key` đã khôi phục từ entry key. Nó có thể là `SecretKey` hoặc `PrivateKey` tùy entry.

`getEntry(alias, protectionParameter)` trả về `KeyStore.Entry`, giúp caller kiểm tra rõ loại entry. Với code quản lý nhiều loại entry, `getEntry` thường dễ đọc và an toàn kiểu hơn.

| API | Kết quả | Dùng khi |
|---|---|---|
| `getKey(alias, password)` | `Key` | Chỉ cần lấy key object và đã biết loại key |
| `getEntry(alias, protection)` | `Entry` | Cần phân biệt `SecretKeyEntry`, `PrivateKeyEntry`, `TrustedCertificateEntry` |

Không nên dùng `getKey` rồi cast mù sang `SecretKey`. Kiểm tra loại entry hoặc kiểm tra kiểu trả về trước khi sử dụng.

## 16. Ví dụ Java 17 hoàn chỉnh: tạo, lưu và đọc SecretKeyEntry

Ví dụ sau dùng JCEKS để minh họa API `SecretKeyEntry`. Mật khẩu được nhập qua console; không đặt password cố định trong source code. Chương trình tạo AES key, lưu entry, nạp lại KeyStore và lấy key ra.

```java
import java.io.Console;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class SecretKeyEntryDemo {
    private static final String STORE_TYPE = "JCEKS";
    private static final String ALIAS = "payments-aes-v1";
    private static final Path STORE_PATH = Path.of("application-secrets.jceks");

    private SecretKeyEntryDemo() {}

    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run from a terminal that provides a Console");
        }

        char[] storePassword = console.readPassword("KeyStore password: ");
        char[] entryPassword = console.readPassword("Entry password: ");
        try {
            createStoreWithAesKey(storePassword, entryPassword);
            SecretKey restored = readAesKey(storePassword, entryPassword);
            System.out.println("Loaded key algorithm: " + restored.getAlgorithm());
            System.out.println("SecretKeyEntry was loaded successfully");
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
        }
    }

    private static void createStoreWithAesKey(char[] storePassword,
                                               char[] entryPassword)
            throws Exception {
        KeyStore keyStore = KeyStore.getInstance(STORE_TYPE);
        if (Files.exists(STORE_PATH)) {
            try (InputStream input = Files.newInputStream(STORE_PATH)) {
                keyStore.load(input, storePassword);
            }
        } else {
            keyStore.load(null, storePassword);
        }

        if (keyStore.containsAlias(ALIAS)) {
            throw new IllegalStateException(
                    "Alias already exists; use a new versioned alias for rotation");
        }

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey secretKey = generator.generateKey();

        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(entryPassword);
        try {
            KeyStore.SecretKeyEntry entry =
                    new KeyStore.SecretKeyEntry(secretKey);
            keyStore.setEntry(ALIAS, entry, protection);

            try (OutputStream output = Files.newOutputStream(STORE_PATH)) {
                keyStore.store(output, storePassword);
            }
        } finally {
            protection.destroy();
        }
    }

    private static SecretKey readAesKey(char[] storePassword,
                                        char[] entryPassword)
            throws Exception {
        KeyStore keyStore = KeyStore.getInstance(STORE_TYPE);
        try (InputStream input = Files.newInputStream(STORE_PATH)) {
            keyStore.load(input, storePassword);
        }

        if (!keyStore.containsAlias(ALIAS)
                || !keyStore.entryInstanceOf(ALIAS,
                        KeyStore.SecretKeyEntry.class)) {
            throw new IllegalStateException("Expected SecretKeyEntry is missing");
        }

        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(entryPassword);
        try {
            KeyStore.Entry loaded = keyStore.getEntry(ALIAS, protection);
            if (!(loaded instanceof KeyStore.SecretKeyEntry secretEntry)) {
                throw new IllegalStateException("Unexpected KeyStore entry type");
            }
            return secretEntry.getSecretKey();
        } finally {
            protection.destroy();
        }
    }
}
```

Ví dụ phục vụ học API, chưa phải một thiết kế production hoàn chỉnh. Nó ghi file trực tiếp vào working directory và minh họa một alias duy nhất. Hệ thống thật cần quyền filesystem hạn chế, đường dẫn được quản trị, cập nhật file an toàn, backup, concurrency control, audit và kế hoạch rotation. Cần kiểm thử JCEKS implementation của JDK đang chạy và không giả định file có thể được mở bởi mọi công cụ hoặc provider khác.

## 17. Sử dụng SecretKey sau khi đọc

Sau khi lấy được `SecretKey`, ứng dụng truyền key cho API mật mã phù hợp. Ví dụ AES-GCM:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
byte[] nonce = new byte[12];
SecureRandom.getInstanceStrong().nextBytes(nonce);
GCMParameterSpec parameters = new GCMParameterSpec(128, nonce);

cipher.init(Cipher.ENCRYPT_MODE, secretKey, parameters);
byte[] ciphertext = cipher.doFinal(plaintext);
```

Trong hệ thống thực tế, nonce cần được quản lý để không tái sử dụng với cùng key. Dữ liệu lưu phải kèm nonce, tag và metadata cần thiết. Với dữ liệu có context như tenant, object ID hoặc purpose, nên dùng Additional Authenticated Data (AAD) để ràng buộc ciphertext với context đó.

Không lưu nonce như bí mật; nonce thường cần được lưu cùng ciphertext. Tuy nhiên, phải bảo đảm tính duy nhất theo yêu cầu của chế độ mã hóa và key.

## 18. SecretKeyEntry cho HMAC

SecretKeyEntry cũng có thể lưu HMAC key nếu provider hỗ trợ. HMAC key dùng chung bí mật giữa bên tạo và bên xác minh MAC.

```java
KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
generator.init(256);
SecretKey hmacKey = generator.generateKey();

KeyStore.SecretKeyEntry entry = new KeyStore.SecretKeyEntry(hmacKey);
keyStore.setEntry("audit-hmac-v1", entry, protection);
```

Không dùng cùng key cho HMAC và AES. Tách key theo thuật toán và purpose giúp giảm tác động khi key bị lộ và làm rõ quyền sử dụng trong inventory. HMAC key cũng cần rotation, backup, access control và quy trình xác minh dữ liệu lịch sử.

## 19. Mật khẩu bảo vệ entry không phải key encryption key dùng cho ứng dụng

Entry password có thể được provider dùng để bảo vệ entry khi lưu trong KeyStore. Nó không phải khóa AES nghiệp vụ mà ứng dụng sử dụng để mã hóa dữ liệu.

```text
Entry password
      |
      v
KeyStore provider protection
      |
      v
Encrypted representation of SecretKeyEntry

SecretKeyEntry -> SecretKey -> AES/HMAC operation
```

Nếu password yếu, bị hardcode hoặc được lưu cạnh file KeyStore, lớp bảo vệ file có thể bị suy giảm. Nếu entry được giải mã trong process, key bytes hoặc key object có thể tồn tại trong memory. Password protection không biến một software KeyStore thành HSM.

## 20. Bảo vệ file KeyStore trên filesystem

Một file KeyStore là tài sản nhạy cảm. Cần bảo vệ cả file, password, bản sao và tiến trình đọc file.

- Giới hạn owner và permission chỉ cho service account cần thiết.
- Không commit KeyStore hoặc password vào Git, Docker image, build artifact hay source repository.
- Không gửi file qua email, chat hoặc hệ thống lưu trữ không được phê duyệt.
- Bảo vệ backup bằng encryption, access control và retention.
- Không ghi nội dung key hoặc password vào log, exception hay telemetry.
- Dùng thư mục riêng, hạn chế symlink và kiểm tra file path trước khi load.
- Khi cập nhật, dùng file tạm có quyền hạn chế, flush dữ liệu và thay thế theo cơ chế atomic phù hợp filesystem.
- Kiểm soát quyền đọc file tạm và xóa bản tạm sau khi hoàn tất.

File KeyStore được mã hóa vẫn có thể bị sao chép. Kẻ tấn công có thể thử password offline nếu format/provider cho phép. Vì vậy, password cần có entropy cao và được lấy từ một secret manager hoặc cơ chế cấp phát đáng tin cậy.

## 21. Quản lý password và bộ nhớ

Không đặt password trong source code, command line argument, environment variable tồn tại lâu dài hoặc log. Tùy môi trường, có thể lấy password từ secret manager, OS credential store, interactive prompt hoặc cơ chế cấp phát ngắn hạn.

Dùng `char[]` giúp ứng dụng có thể ghi đè buffer sau khi dùng; `String` là immutable nên không thể chủ động xóa nội dung. Tuy nhiên, việc ghi đè `char[]` không bảo đảm xóa mọi bản sao do JVM, provider hoặc garbage collector tạo ra.

`KeyStore.PasswordProtection` có method `destroy()` để yêu cầu xóa password nội bộ. Cần gọi sau khi hoàn tất thao tác, đồng thời ghi nhớ rằng provider có thể đã tạo bản sao khác. Không chia sẻ một `PasswordProtection` object cho các luồng đồng thời nếu không hiểu thread-safety của implementation.

## 22. SecretKeyEntry và key không export được

Một số HSM/KMS tạo key object không cho export. `SecretKey.getEncoded()` có thể trả `null` khi key không thể được biểu diễn hoặc export dưới dạng bytes.

Điều này không nhất thiết có nghĩa key không dùng được. Provider có thể cung cấp một object đại diện cho key trong thiết bị; các phép toán được gửi tới HSM thay vì lấy raw key bytes ra JVM.

Tuy nhiên, không phải mọi provider đều biểu diễn opaque key qua `SecretKeyEntry`, và không phải mọi `KeyStore` type đều có thể lưu reference tới object đó. Cần xác minh khả năng `setEntry`, `getEntry`, `getEncoded`, persistence và restart recovery trên HSM thực tế.

Nếu ứng dụng yêu cầu key non-exportable, không nên gọi `getEncoded()` rồi tự serialize. Hãy sử dụng provider và API được thiết kế cho opaque key handle.

## 23. Dùng PKCS11 KeyStore với HSM

Một HSM có thể được tích hợp vào Java qua PKCS#11 provider. Java có thể truy cập token như một KeyStore type, thường cấu hình qua provider và file cấu hình PKCS#11.

Khái niệm cần phân biệt:

- File KeyStore software lưu dữ liệu được provider serialize vào file.
- PKCS11 KeyStore có thể liệt kê và truy cập object nằm trong token/HSM.
- Alias có thể ánh xạ tới object label hoặc object ID trong thiết bị.
- Password/PIN có thể dùng để đăng nhập token, nhưng semantics không giống entry password của file KeyStore.
- Việc tạo, đọc, xóa và backup key object phụ thuộc HSM, token policy và provider.

Không thể thay `JCEKS` bằng `PKCS11` trong code rồi giả định mọi hành vi còn lại giống nhau. Cần cấu hình provider, token slot, login, key attributes, object persistence, HA, backup và audit theo tài liệu HSM.

## 24. Tích hợp với KMS

KMS thường quản lý key material và thực hiện các phép toán mã hóa/giải mã, wrap/unwrap hoặc ký thông qua API. Trong kiến trúc envelope encryption, ứng dụng có thể chỉ lưu wrapped DEK và key identifier trong database, còn KEK được quản lý bởi KMS.

`SecretKeyEntry` phù hợp khi ứng dụng cần lưu secret key trong một KeyStore provider mà ứng dụng trực tiếp truy cập. Nếu KMS cung cấp opaque key handle hoặc remote cryptographic operations, việc đưa key vào SecretKeyEntry có thể không phù hợp.

Một lựa chọn kiến trúc:

| Nhu cầu | Cách tiếp cận |
|---|---|
| Ứng dụng nhỏ, key cục bộ và yêu cầu đơn giản | Software KeyStore với file permission và password quản lý tốt |
| Key phải non-exportable | HSM/PKCS11 provider hoặc API phần cứng tương ứng |
| Nhiều service, nhiều tenant, audit tập trung | KMS với IAM, key policy và audit tập trung |
| Envelope encryption quy mô lớn | DEK cho dữ liệu, KEK trong KMS; lưu wrapped DEK và metadata |
| Secret cấu hình/credential không phải cryptographic key | Secret manager phù hợp thay vì ép mọi secret thành SecretKeyEntry |

Không nên tải raw KEK từ KMS về rồi lưu trong JCEKS nếu mục tiêu ban đầu là giữ KEK non-exportable trong KMS.

## 25. Metadata và purpose của secret key

`SecretKeyEntry` chứa key object, nhưng không cung cấp một mô hình policy nghiệp vụ đầy đủ. Ứng dụng cần quản lý metadata riêng:

- Key ID, alias và version.
- Algorithm và key size.
- Purpose: encryption, decryption, HMAC hoặc wrapping.
- Owner, service, tenant và environment.
- Ngày tạo, trạng thái và cryptoperiod.
- Quyền đọc/sử dụng và approval.
- Dữ liệu hoặc ciphertext phụ thuộc vào key.
- Kế hoạch backup, rotation và destruction.

Không suy ra purpose chỉ từ thuật toán. Một AES key có thể được dùng cho nhiều mục đích khác nhau; policy nên ràng buộc key với đúng operation. Cách tốt hơn là tách key theo purpose và dùng alias/version có quy ước rõ.

## 26. Rotation SecretKeyEntry

Khi rotation, không nên ghi đè key cũ bằng key mới dưới cùng alias nếu dữ liệu lịch sử còn cần key cũ. Một cách làm rõ ràng là dùng alias theo version:

```text
payments-aes-v1  -> old key, decrypt-only
payments-aes-v2  -> current key, encrypt/decrypt
```

Quy trình tổng quát:

1. Tạo key mới bằng `KeyGenerator` hoặc KMS/HSM.
2. Lưu key mới dưới alias/version mới.
3. Cập nhật writer để chỉ mã hóa dữ liệu mới bằng key mới.
4. Reader chọn đúng key theo metadata của ciphertext.
5. Re-encrypt hoặc rewrap dữ liệu cũ theo kế hoạch.
6. Theo dõi dependency, backup và restore.
7. Chỉ xóa key cũ khi không còn ciphertext, backup hoặc archive cần nó.

Trong giai đoạn chuyển đổi, cần dual-read/single-write: đọc được cả key cũ và key mới nhưng chỉ ghi mới bằng key hiện tại. Tránh để nhiều writer cạnh tranh cập nhật alias hoặc key version không đồng bộ.

## 27. Backup và khôi phục

Backup file KeyStore cùng với password trong cùng một thư mục hoặc cùng một backup bundle có thể làm mất ý nghĩa tách lớp bảo vệ. Password và file nên có control plane, quyền truy cập và kênh recovery phù hợp.

Kế hoạch backup cần xác định:

- File KeyStore nào được backup và ai là owner.
- File backup được mã hóa và kiểm tra integrity như thế nào.
- Password được bảo vệ và khôi phục qua kênh nào.
- Ai có quyền đọc, xóa hoặc restore.
- Backup được giữ bao lâu và khi nào phải hủy.
- Cách khôi phục KeyStore và xác minh alias/entry/version.
- Cách xử lý password bị lộ hoặc file bị sửa.

Phải thử restore trong môi trường cô lập. Một backup chỉ được xem là hữu dụng khi có thể load bằng provider tương thích, đọc entry cần thiết và thực hiện phép toán thử mà không làm lộ key material.

## 28. Xóa entry và hủy key

`KeyStore.deleteEntry(alias)` xóa entry khỏi KeyStore object trong bộ nhớ. Muốn lưu thay đổi vào file, cần gọi `store` sau đó.

```java
keyStore.deleteEntry("payments-aes-v1");
try (OutputStream output = Files.newOutputStream(storePath)) {
    keyStore.store(output, storePassword);
}
```

Xóa alias khỏi file không chứng minh mọi bản sao key material đã biến mất. Bản backup, snapshot, bản sao file, process đang chạy hoặc key bytes đã được export có thể còn tồn tại. Nếu cần crypto-erasure, phải kiểm kê và xử lý mọi bản sao, wrapped key, backup, cache và recovery path theo quy trình hủy khóa.

Với HSM/KMS, xóa entry có thể chỉ xóa tham chiếu hoặc object tùy provider. Phải đọc semantics của thiết bị/dịch vụ và xác minh trạng thái cuối cùng. Không đánh đồng `deleteEntry` với thao tác destroy key material trong HSM.

## 29. Đồng thời và cập nhật file an toàn

`KeyStore` object không phải một cơ chế database giao dịch đa tiến trình. Nếu nhiều process cùng load một file, mỗi process sửa rồi store, thao tác sau có thể ghi đè thay đổi của thao tác trước.

Trong môi trường có nhiều writer:

- Dùng một service quản lý KeyStore thay vì cho nhiều process ghi trực tiếp.
- Áp dụng file lock hoặc cơ chế coordination phù hợp.
- Ghi file tạm trên cùng filesystem, flush và thay thế atomic nếu nền tảng hỗ trợ.
- Kiểm tra file version hoặc checksum trước khi thay thế.
- Không để hai process cùng rotate alias/version.
- Có backup và audit trước thay đổi lớn.

Với hệ thống nhiều instance hoặc nhiều node, KMS/HSM/secret manager tập trung thường phù hợp hơn việc đồng bộ một file KeyStore bằng shared filesystem.

## 30. Lỗi thường gặp khi dùng SecretKeyEntry

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `KeyStoreException` khi setEntry | Provider không hỗ trợ SecretKeyEntry hoặc key algorithm | Kiểm tra KeyStore type/provider và capability |
| `UnrecoverableEntryException` | Entry password sai hoặc provider không giải mã được entry | Xác minh password, provider và entry protection |
| `IOException` khi load | File hỏng, sai store password hoặc định dạng không tương thích | Kiểm tra file, password, type và nguồn tạo file |
| Alias không tồn tại | Sai alias hoặc entry chưa được store | Kiểm tra alias, `containsAlias` và lần store gần nhất |
| Entry sai loại | Alias trỏ tới PrivateKeyEntry hoặc TrustedCertificateEntry | Dùng `entryInstanceOf`/`instanceof` trước khi cast |
| Key trả về `getEncoded() == null` | Opaque/non-exportable key hoặc provider không export | Dùng API mật mã của provider, không yêu cầu raw bytes |
| File được ghi nhưng không đọc lại được | Store password, entry password hoặc provider khác nhau | Kiểm thử readback bằng đúng provider/type và cấu hình |
| Thay đổi bị mất | Quên gọi `store` hoặc writer khác ghi đè | Persist sau update và điều phối writer |

Không log password hoặc key bytes để chẩn đoán. Log exception có thể chứa đường dẫn hoặc provider detail; cần kiểm tra trước khi đưa ra hệ thống tập trung.

## 31. Kiểm thử SecretKeyEntry

Test suite nên xác minh cả API và hành vi provider:

- Tạo KeyStore rỗng và lưu được `SecretKeyEntry`.
- Load lại file và đọc được đúng alias.
- `entryInstanceOf` trả đúng loại entry.
- Thuật toán và key size sau readback đúng như mong đợi.
- Sai store password bị từ chối.
- Sai entry password bị từ chối.
- Alias không tồn tại được xử lý rõ ràng.
- Provider không hỗ trợ loại entry được phát hiện trước khi rollout.
- File bị sửa hoặc cắt cụt được xử lý an toàn.
- Rotation giữ được khả năng đọc dữ liệu cũ.
- Backup restore được bằng provider và version được hỗ trợ.
- Quyền filesystem ngăn user không được phép đọc file.
- Không có key bytes hoặc password trong log/artifact.

Với HSM, cần kiểm thử trên sandbox hoặc thiết bị thử nghiệm: login, slot, alias mapping, object persistence, HA/failover, backup/restore và audit. Không dùng thao tác destroy trên key production để kiểm thử.

## 32. Anti-pattern cần tránh

1. **Hardcode password trong source code.** Secret có thể bị lộ qua repository hoặc build artifact.
2. **Đặt file KeyStore cạnh ứng dụng với quyền đọc rộng.** Người dùng cùng máy có thể lấy file và thử password offline.
3. **Dùng chung store password và entry password mà không có lý do.** Mất một password có thể làm lộ cả kho.
4. **Dùng một key cho nhiều purpose.** Làm tăng blast radius và khó rotation.
5. **Ghi đè alias của key cũ.** Có thể khiến dữ liệu lịch sử không còn key để decrypt.
6. **Coi JCEKS là HSM.** Software KeyStore vẫn phụ thuộc bảo mật host và password.
7. **Giả định mọi PKCS12 provider hỗ trợ secret key giống nhau.** Có thể gặp lỗi tương thích khi đổi JDK/provider.
8. **Xuất `getEncoded()` ra log hoặc file tạm.** Tạo thêm bản plaintext của key.
9. **Quên gọi `store`.** Thay đổi không được persist.
10. **Xóa entry rồi tuyên bố key đã bị hủy hoàn toàn.** Backup và bản sao có thể còn tồn tại.
11. **Dùng alias làm authorization.** Alias chỉ là định danh, không phải access control.
12. **Không thử restore.** Backup có thể không dùng được khi sự cố xảy ra.

## 33. Case study: lưu AES key cho dịch vụ thanh toán

Một dịch vụ thanh toán nhỏ cần mã hóa một số trường dữ liệu nhạy cảm trong database. Ứng dụng Java tạo AES key, lưu dưới alias `payments-aes-v1` trong KeyStore software, sau đó đọc key khi khởi động và dùng AES-GCM để mã hóa dữ liệu.

Nhóm vận hành tách password bảo vệ file và entry, cấp quyền đọc file chỉ cho service account, không commit file vào repository, và lưu backup được mã hóa ở kho riêng. Metadata trong database ghi key version cùng nonce và tag để reader biết key nào cần dùng.

Khi rotation, nhóm tạo `payments-aes-v2`, cập nhật writer dùng v2 và giữ v1 để decrypt dữ liệu lịch sử. Họ re-encrypt dữ liệu theo batch, kiểm tra restore từ backup rồi mới xóa entry v1 sau khi xác nhận không còn dependency.

Khi quy mô tăng và cần nhiều instance, audit tập trung và non-exportable key, nhóm chuyển sang KMS/HSM. KeyStore không còn là nơi giữ raw KEK; ứng dụng dùng KMS API để tạo/unwrap DEK và lưu wrapped DEK cùng key ID.

## 34. Checklist triển khai

- [ ] Đã xác định KeyStore type và provider hỗ trợ `SecretKeyEntry`.
- [ ] Đã kiểm thử set, store, load và getEntry trên JDK/provider thực tế.
- [ ] Alias thể hiện purpose và version; không chứa dữ liệu nhạy cảm.
- [ ] Key được tạo bằng `KeyGenerator`, HSM hoặc KMS phù hợp.
- [ ] Password không hardcode và không xuất hiện trong log.
- [ ] Store password và entry password có policy rõ ràng.
- [ ] `PasswordProtection.destroy()` được gọi sau khi sử dụng.
- [ ] File KeyStore có owner/permission hạn chế và backup được bảo vệ.
- [ ] Không export raw key nếu không có yêu cầu và approval.
- [ ] Key được tách theo algorithm, purpose, tenant và environment.
- [ ] Có metadata về owner, key ID, version, trạng thái và cryptoperiod.
- [ ] Có rotation, dual-read/single-write và retention cho key cũ.
- [ ] Có restore test và quy trình hủy mọi bản sao khi hết vòng đời.
- [ ] Có audit, concurrency control và phương án xử lý lỗi provider.
- [ ] Đã đánh giá KMS/HSM khi yêu cầu non-exportable hoặc quản trị tập trung.

## 35. Câu hỏi tự kiểm tra

**1. `SecretKeyEntry` dùng để làm gì?**

Nó đại diện cho một `SecretKey` trong Java KeyStore, thường là khóa đối xứng dùng cho AES, HMAC hoặc thuật toán được provider hỗ trợ.

**2. `SecretKeyEntry` khác `PrivateKeyEntry` thế nào?**

SecretKeyEntry chứa secret key đối xứng; PrivateKeyEntry chứa private key cùng certificate chain.

**3. `SecretKeyEntry` khác `TrustedCertificateEntry` thế nào?**

TrustedCertificateEntry chứa certificate được tin cậy, không chứa secret key.

**4. Vì sao dùng `setEntry`?**

Nó lưu một KeyStore.Entry cùng ProtectionParameter, thể hiện rõ kiểu entry và cơ chế bảo vệ do provider thực hiện.

**5. `PasswordProtection` có vai trò gì?**

Nó cung cấp password hoặc protection settings để provider bảo vệ/khôi phục entry.

**6. Store password và entry password có giống nhau không?**

Không nhất thiết. Store password dùng khi load/store KeyStore; entry password dùng khi set/get một entry theo provider semantics.

**7. Vì sao cần gọi `store` sau `setEntry`?**

Vì `setEntry` thay đổi KeyStore object trong bộ nhớ; `store` mới ghi thay đổi ra output stream.

**8. `load(null, password)` có nghĩa gì?**

Nó khởi tạo KeyStore mới trong bộ nhớ với password theo provider, thay vì nạp một file có sẵn.

**9. Mọi KeyStore type có hỗ trợ SecretKeyEntry không?**

Không. Khả năng phụ thuộc type, provider, JDK và thuật toán key; phải kiểm thử thực tế.

**10. JCEKS có phải HSM không?**

Không. JCEKS là software KeyStore; nó vẫn phụ thuộc host, password và filesystem.

**11. `getEntry` khác `getKey` thế nào?**

getEntry trả KeyStore.Entry để kiểm tra loại; getKey trả đối tượng Key đã khôi phục.

**12. `entryInstanceOf` có ích gì?**

Nó kiểm tra alias có entry thuộc một lớp entry cụ thể hay không trước khi đọc/cast.

**13. `getEncoded()` trả null có nghĩa key hỏng không?**

Không nhất thiết. Key có thể opaque hoặc non-exportable; provider vẫn có thể dùng key qua handle.

**14. Vì sao không dùng cùng key cho AES và HMAC?**

Tách purpose giảm rủi ro sử dụng sai và giới hạn tác động khi key bị compromise.

**15. Vì sao alias theo version hữu ích?**

Nó cho phép giữ key cũ để decrypt trong khi writer chuyển sang key mới.

**16. Xóa entry có đồng nghĩa crypto-erasure không?**

Không. Backup, file copy, memory, wrapped key hoặc recovery path có thể còn tồn tại.

**17. PKCS11 KeyStore khác file KeyStore thế nào?**

PKCS11 thường truy cập object trong token/HSM; file KeyStore lưu dữ liệu qua provider vào file.

**18. Khi nào nên dùng KMS thay vì SecretKeyEntry?**

Khi cần quản lý tập trung, IAM, audit, non-exportable key, multi-service hoặc envelope encryption ở quy mô lớn.

**19. Tại sao phải test backup restore?**

Để xác nhận provider, password, entry và dữ liệu phụ thuộc có thể phục hồi trong điều kiện sự cố.

**20. `PasswordProtection.destroy()` có xóa mọi bản sao password khỏi JVM không?**

Không bảo đảm. Nó yêu cầu xóa password nội bộ của object; JVM/provider có thể đã tạo bản sao khác.

## 36. Kết luận

`KeyStore.SecretKeyEntry` là cách chuẩn hóa trong Java để đưa một `SecretKey` vào KeyStore thông qua provider. Nó giúp ứng dụng quản lý secret key theo alias và protection parameter, nhưng độ an toàn thực tế phụ thuộc KeyStore type, provider, password, filesystem, cách dùng key và quy trình vận hành.

Một triển khai tốt cần xác minh provider support, tách password hợp lý, bảo vệ file và backup, giới hạn việc export key, quản lý alias/version, giữ khả năng đọc dữ liệu cũ trong rotation và xác minh mọi bản sao trước khi hủy. Khi yêu cầu non-exportable key, audit tập trung hoặc nhiều workload dùng chung, hãy cân nhắc HSM/KMS thay vì mở rộng một file KeyStore software vượt quá phạm vi phù hợp của nó.
