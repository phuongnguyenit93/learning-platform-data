# JCEKS

Java cung cấp `KeyStore` như một API thống nhất để lưu và truy xuất khóa mật mã cùng chứng thư số. Khi một ứng dụng cần giữ khóa AES, khóa riêng của một cặp khóa hoặc chứng thư CA, nó có thể dùng API này thay vì tự xây dựng định dạng lưu trữ. **JCEKS** là một loại keystore gắn với hệ sinh thái Java, từng được dùng để lưu cả khóa bí mật đối xứng và khóa riêng.

JCEKS hữu ích khi phải duy trì một ứng dụng Java cũ hoặc đọc một kho khóa đã tồn tại. Tuy nhiên, đây là định dạng độc quyền của Java và cơ chế bảo vệ khóa trong triển khai truyền thống đã cũ. Khi thiết kế mới, cần đánh giá PKCS12, KMS hoặc HSM theo yêu cầu tương thích, khả năng bảo vệ khóa và vận hành của hệ thống.

## 1. KeyStore trong Java dùng để làm gì?

`java.security.KeyStore` là lớp API cho phép ứng dụng thao tác với một kho chứa các entry có tên định danh. Mỗi entry được truy xuất thông qua một **alias**. Ứng dụng có thể nạp kho từ tệp, tạo kho mới, thêm hoặc lấy entry, rồi lưu lại.

Các loại entry quan trọng gồm:

| Loại entry | Nội dung | Ví dụ sử dụng |
|---|---|---|
| `PrivateKeyEntry` | Khóa riêng và chuỗi chứng thư xác nhận khóa công khai tương ứng | Khóa riêng TLS, khóa ký số |
| `SecretKeyEntry` | Khóa bí mật đối xứng | Khóa AES dùng mã hóa dữ liệu ứng dụng |
| `TrustedCertificateEntry` | Một chứng thư được tin cậy, không kèm khóa riêng | Chứng thư CA gốc hoặc chứng thư đối tác |

KeyStore là API và mô hình lưu trữ. Định dạng tệp, thuật toán bảo vệ entry và khả năng hỗ trợ từng loại entry phụ thuộc vào **loại keystore** cùng provider triển khai nó. Vì vậy, gọi `KeyStore.getInstance("JCEKS")` có ý nghĩa chọn một định dạng và cách triển khai cụ thể, không chỉ là đặt tên tệp có đuôi `.jceks`.

## 2. JCEKS là gì?

JCEKS là viết tắt của *Java Cryptography Extension KeyStore*. Đây là loại keystore độc quyền do provider SunJCE trong các bản JDK của Oracle/OpenJDK cung cấp. JCEKS mở rộng khả năng của JKS truyền thống, đặc biệt ở việc lưu `SecretKeyEntry` bên cạnh khóa riêng và chứng thư.

JCEKS thường được nhận diện bằng:

- Loại keystore được chọn bằng tên `JCEKS` trong Java API hoặc `-storetype JCEKS` trong `keytool`.
- Tệp lưu trữ có cấu trúc nhị phân riêng của hệ sinh thái Java, không phải định dạng trao đổi chuẩn phổ biến như PKCS12.
- Có thể chứa khóa bí mật đối xứng, khóa riêng và chứng thư tin cậy.
- Việc đọc tệp phụ thuộc vào provider có hỗ trợ JCEKS và khả năng tương thích của phiên bản Java.

Tên tệp thường dùng phần mở rộng `.jceks`, nhưng phần mở rộng không quyết định loại keystore. Khi nạp tệp, ứng dụng phải chỉ định đúng loại và provider tương ứng.

### JCEKS, JKS và PKCS12

| Tiêu chí | JKS | JCEKS | PKCS12 |
|---|---|---|---|
| Bản chất | Định dạng keystore truyền thống của Java | Định dạng keystore độc quyền của Java Cryptography Extension | Định dạng trao đổi mật mã được chuẩn hóa |
| Khóa riêng và chứng thư | Có | Có | Có |
| Khóa bí mật đối xứng | Triển khai JKS truyền thống không hỗ trợ `SecretKeyEntry` theo cách chuẩn của KeyStore API | Hỗ trợ `SecretKeyEntry` | Khả năng lưu khóa bí mật phụ thuộc JDK/provider và mức tương thích cần kiểm chứng |
| Khả năng trao đổi với công cụ khác | Hạn chế | Hạn chế hơn do tính đặc thù của Java | Rộng hơn, được nhiều nền tảng và công cụ hỗ trợ |
| Vai trò hiện nay | Chủ yếu gặp trong hệ thống cũ | Thường gặp khi duy trì kho khóa Java cũ có khóa đối xứng | Lựa chọn phổ biến cho kho khóa cần tương thích rộng |

Từ Java 9, PKCS12 trở thành loại keystore mặc định khi ứng dụng không chỉ định loại khác. Điều này không làm JCEKS tự động biến mất: ứng dụng cũ vẫn có thể cần đọc hoặc ghi JCEKS. Tuy nhiên, khi tạo hệ thống mới, nên chọn định dạng dựa trên yêu cầu hiện tại thay vì mặc định chọn JCEKS chỉ vì ứng dụng được viết bằng Java.

## 3. Alias, entry và các lớp bảo vệ

Một keystore có thể chứa nhiều entry với alias khác nhau. Ví dụ, một ứng dụng có thể dùng alias `tls-server` cho khóa riêng TLS, `data-encryption` cho khóa AES và `partner-ca` cho chứng thư CA đối tác. Alias giúp ứng dụng định vị entry, nhưng bản thân alias không phải cơ chế phân quyền.

Khi làm việc với JCEKS, cần phân biệt hai lớp mật khẩu:

| Mật khẩu | Mục đích |
|---|---|
| Keystore password | Được dùng khi nạp và lưu kho; triển khai JCEKS kiểm tra tính toàn vẹn của dữ liệu kho bằng mật khẩu này. |
| Entry password | Bảo vệ khóa của một entry, chẳng hạn `SecretKeyEntry` hoặc `PrivateKeyEntry`, khi ghi và đọc entry đó. |

Hai mật khẩu có thể được đặt giống nhau, nhưng tách biệt giúp giới hạn phạm vi khi một thông tin xác thực bị lộ. Ứng dụng cần quản lý cả hai bằng cơ chế cấp phát bí mật phù hợp, không ghi mật khẩu vào mã nguồn, tệp cấu hình công khai, log hoặc tham số dòng lệnh có thể bị quan sát.

`TrustedCertificateEntry` chỉ chứa chứng thư công khai nên không có khóa riêng cần bảo vệ bằng entry password. Dù vậy, ứng dụng vẫn phải kiểm tra nguồn gốc và chính sách tin cậy của chứng thư trước khi thêm nó vào kho.

## 4. Cơ chế bảo vệ và giới hạn bảo mật của JCEKS

JCEKS bảo vệ dữ liệu kho và mã hóa khóa được lưu trong các entry. Trong triển khai SunJCE truyền thống, cơ chế bảo vệ khóa gắn với thuật toán password-based encryption `PBEWithMD5AndTripleDES`. Đây là lựa chọn lịch sử; MD5 và Triple DES không nên được xem là nền tảng mật mã hiện đại cho một thiết kế mới.

Một số hệ quả cần hiểu rõ:

- Mật khẩu mạnh làm tăng chi phí đoán mật khẩu, nhưng không biến một thuật toán bảo vệ cũ thành thuật toán hiện đại.
- Mã hóa tệp keystore không bảo vệ khóa nếu ứng dụng hoặc tiến trình đang chạy đã bị chiếm quyền và có thể lấy mật khẩu hoặc yêu cầu provider giải mã entry.
- JCEKS là kho lưu trữ phần mềm. Nó không cung cấp ranh giới bảo vệ vật lý và khả năng chống trích xuất khóa như HSM.
- Quyền truy cập tệp, bản sao lưu, snapshot, quyền của tài khoản chạy ứng dụng và cách phân phối mật khẩu đều ảnh hưởng đến mức an toàn thực tế.

Do đó, JCEKS có thể đáp ứng nhu cầu tương thích của một hệ thống cũ, nhưng không nên được coi là giải pháp thay thế KMS/HSM cho các khóa có yêu cầu bảo vệ cao. Với hệ thống mới, hãy đánh giá PKCS12 cho nhu cầu lưu trữ tệp và KMS/HSM cho nhu cầu kiểm soát khóa tập trung, audit, phân quyền và thao tác mật mã trong ranh giới bảo vệ chuyên dụng.

## 5. Tạo và kiểm tra JCEKS bằng keytool

`keytool` là công cụ dòng lệnh của JDK để quản lý keystore. Ví dụ sau tạo một khóa AES 256 bit và lưu nó dưới dạng `SecretKeyEntry` trong JCEKS:

```bash
keytool -genseckey \
  -alias application-aes \
  -keyalg AES \
  -keysize 256 \
  -keystore application-keys.jceks \
  -storetype JCEKS
```

Khi được hỏi, nhập keystore password và key password theo chính sách của tổ chức. Có thể đặt hai mật khẩu khác nhau để tách quyền mở kho và quyền sử dụng khóa của entry. Không đưa mật khẩu thật trực tiếp vào câu lệnh hoặc lưu câu lệnh có chứa mật khẩu trong lịch sử shell.

Liệt kê các entry để xác nhận alias và loại entry:

```bash
keytool -list -v \
  -keystore application-keys.jceks \
  -storetype JCEKS
```

Kết quả giúp kiểm tra loại keystore, alias, loại entry và một số metadata. Không dùng việc liệt kê thành công làm bằng chứng duy nhất rằng khóa có thể thực hiện đúng thao tác mã hóa hoặc giải mã trong ứng dụng; cần kiểm tra khả năng nạp entry và thực hiện thao tác dự kiến trong môi trường kiểm thử.

Một số lệnh quản trị khác:

```bash
# Xem danh sách entry
keytool -list -keystore application-keys.jceks -storetype JCEKS

# Xóa một alias khỏi kho
keytool -delete -alias application-aes \
  -keystore application-keys.jceks -storetype JCEKS
```

Xóa alias chỉ loại bỏ entry khỏi cấu trúc keystore đang được cập nhật. Nó không bảo đảm mọi bản sao của khóa đã biến mất khỏi ổ đĩa, journal, snapshot, bản sao lưu hoặc hệ thống lưu trữ bên dưới. Khi cần hủy khóa, phải xử lý toàn bộ bản sao và quy trình lưu trữ theo chính sách vòng đời khóa.

## 6. Đọc và ghi SecretKeyEntry bằng Java

Ví dụ sau minh họa cách tạo một keystore mới hoặc nạp keystore hiện có, lưu một khóa AES và đọc lại khóa theo alias. Đoạn mã dùng Java 11 trở lên và nhận mật khẩu từ bên gọi để ứng dụng có thể lấy chúng từ một nguồn bí mật được kiểm soát.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class JceksExample {
    private static final String TYPE = "JCEKS";
    private static final String ALIAS = "application-aes";

    public static void createNewEntry(
            Path file,
            char[] storePassword,
            char[] entryPassword) throws Exception {

        KeyStore keyStore = KeyStore.getInstance(TYPE);

        if (Files.exists(file)) {
            try (InputStream input = Files.newInputStream(file)) {
                keyStore.load(input, storePassword);
            }
        } else {
            keyStore.load(null, storePassword);
        }

        if (keyStore.containsAlias(ALIAS)) {
            throw new IllegalStateException(
                    "Alias already exists; handle key rotation explicitly");
        }

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey secretKey = generator.generateKey();

        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(entryPassword);
        try {
            keyStore.setEntry(
                    ALIAS,
                    new KeyStore.SecretKeyEntry(secretKey),
                    protection);
        } finally {
            protection.destroy();
        }

        try (OutputStream output = Files.newOutputStream(file)) {
            keyStore.store(output, storePassword);
        }
    }

    public static SecretKey loadSecretKey(
            Path file,
            char[] storePassword,
            char[] entryPassword) throws Exception {

        KeyStore keyStore = KeyStore.getInstance(TYPE);
        try (InputStream input = Files.newInputStream(file)) {
            keyStore.load(input, storePassword);
        }

        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(entryPassword);
        try {
            KeyStore.Entry entry = keyStore.getEntry(ALIAS, protection);
            if (!(entry instanceof KeyStore.SecretKeyEntry)) {
                throw new IllegalStateException(
                        "Alias does not contain a SecretKeyEntry");
            }
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        } finally {
            protection.destroy();
        }
    }
}
```

Trong ứng dụng thực tế, bên gọi cần xóa nội dung các mảng `char[]` khi không còn cần dùng, chẳng hạn bằng `java.util.Arrays.fill(password, '\0')` trong khối `finally`. Việc xóa mảng giảm thời gian bí mật tồn tại trong bộ nhớ do ứng dụng kiểm soát, nhưng không bảo đảm xóa mọi bản sao do JVM hoặc provider có thể đã tạo.

Các điểm cần chú ý trong ví dụ:

1. `KeyStore.getInstance("JCEKS")` chọn đúng loại keystore; nếu provider không có sẵn hoặc bị cấu hình loại bỏ, ứng dụng cần xử lý lỗi khởi tạo.
2. `load(null, storePassword)` khởi tạo kho mới. Khi tệp đã tồn tại, phải nạp kho bằng mật khẩu tương ứng thay vì tạo lại và ghi đè dữ liệu.
3. `SecretKeyEntry` biểu diễn khóa đối xứng; `PasswordProtection` cung cấp entry password để bảo vệ khóa khi lưu và truy xuất.
4. `store(output, storePassword)` ghi kho xuống tệp và áp dụng cơ chế bảo vệ toàn vẹn của keystore.
5. Ứng dụng không nên log đối tượng khóa, `getEncoded()` hoặc nội dung mật khẩu trong quá trình xử lý.

Trong hệ thống cần độ sẵn sàng cao, thao tác cập nhật tệp nên được thiết kế để tránh ghi dở dang, ví dụ ghi ra tệp tạm trong cùng filesystem, đồng bộ dữ liệu theo yêu cầu rồi thay thế tệp đích bằng thao tác phù hợp với nền tảng. Đồng thời cần khóa đồng bộ khi nhiều tiến trình cùng cập nhật một keystore để tránh mất thay đổi.

## 7. Dùng JCEKS để lưu khóa riêng và chứng thư

JCEKS cũng có thể lưu `PrivateKeyEntry`. Entry này gồm khóa riêng và chuỗi chứng thư liên quan. Ứng dụng có thể đọc khóa riêng sau khi xác minh mật khẩu entry và dùng chứng thư đi kèm để xây dựng danh tính hoặc chuỗi chứng thư.

Ví dụ khởi tạo một keystore từ tệp hiện có:

```java
KeyStore keyStore = KeyStore.getInstance("JCEKS");
try (InputStream input = Files.newInputStream(Path.of("identity.jceks"))) {
    keyStore.load(input, storePassword);
}

KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(privateKeyPassword);
try {
    KeyStore.Entry entry = keyStore.getEntry("tls-identity", protection);
    if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
        throw new IllegalStateException("Unexpected entry type");
    }
    KeyStore.PrivateKeyEntry identity =
            (KeyStore.PrivateKeyEntry) entry;
    // Dùng private key và certificate chain theo mục đích đã được cấp quyền.
} finally {
    protection.destroy();
}
```

Không phải cứ lấy được `PrivateKeyEntry` là có thể sử dụng khóa an toàn. Ứng dụng cần kiểm tra chuỗi chứng thư, mục đích sử dụng, thời hạn, thuật toán, độ dài khóa và chính sách tin cậy. Quyền sử dụng khóa riêng cũng cần được giới hạn theo vai trò và mục đích nghiệp vụ.

## 8. Quản lý mật khẩu và tệp JCEKS trong vận hành

JCEKS thường được lưu dưới dạng tệp, do đó bảo mật phụ thuộc đáng kể vào hệ điều hành và quy trình triển khai. Các biện pháp vận hành cần có gồm:

- Đặt quyền đọc/ghi tệp chỉ cho tài khoản dịch vụ thực sự cần truy cập; hạn chế quyền của người dùng và tiến trình khác.
- Không commit keystore hoặc mật khẩu vào Git, image container, artifact công khai hay hệ thống log.
- Lấy mật khẩu từ secret manager hoặc cơ chế cấp phát bí mật được kiểm soát; giới hạn người và dịch vụ có thể truy cập.
- Bảo vệ bản sao lưu, snapshot và bản sao trong pipeline triển khai với mức kiểm soát tương đương tệp gốc.
- Ghi nhận ai hoặc dịch vụ nào đã truy cập, thay thế, sao lưu hay khôi phục keystore; cảnh báo các thay đổi bất thường.
- Phân tách môi trường phát triển, kiểm thử và sản xuất; không dùng chung một khóa giữa các môi trường.
- Có quy trình xoay vòng khóa, thay mật khẩu, thu hồi chứng thư và phục hồi khi tệp hoặc mật khẩu bị lộ.

Đổi keystore password không đồng nghĩa với xoay vòng khóa mật mã. Nếu khóa AES đã bị lộ, cần tạo khóa mới, chuyển dữ liệu hoặc quy trình mã hóa sang khóa mới, xác định cách xử lý dữ liệu cũ và thu hồi khóa cũ theo kế hoạch. Tương tự, sao chép tệp sang vị trí mới không tạo ra một khóa mới.

## 9. Di chuyển từ JCEKS sang định dạng hoặc dịch vụ khác

Việc di chuyển thường cần thiết khi ứng dụng cần trao đổi kho khóa với công cụ ngoài Java, muốn dùng chuẩn phổ biến hơn hoặc chuyển sang quản lý khóa tập trung. Với entry khóa riêng và chứng thư, `keytool` có thể hỗ trợ nhập kho từ JCEKS sang PKCS12:

```bash
keytool -importkeystore \
  -srckeystore legacy.jceks \
  -srcstoretype JCEKS \
  -destkeystore migrated.p12 \
  -deststoretype PKCS12
```

Lệnh sẽ yêu cầu thông tin xác thực của kho nguồn và kho đích. Trước khi áp dụng trong sản xuất, cần kiểm tra phiên bản JDK/provider và khả năng chuyển đổi của từng loại entry. Đặc biệt, không được giả định mọi triển khai PKCS12 đều giữ được `SecretKeyEntry` theo cùng cách JCEKS đã lưu.

Quy trình di chuyển nên gồm các bước:

1. Kiểm kê alias, loại entry, mục đích sử dụng, chủ sở hữu và ứng dụng đang phụ thuộc vào từng khóa.
2. Sao lưu kho nguồn và kiểm soát quyền truy cập bản sao.
3. Tạo kho đích, chuyển các entry được hỗ trợ và ghi nhận lỗi hoặc entry không thể chuyển.
4. Đọc lại từng alias, xác minh loại entry, chuỗi chứng thư và khả năng sử dụng khóa bằng thao tác kiểm thử phù hợp.
5. Cập nhật ứng dụng để chỉ định rõ loại keystore và provider; chạy thử trên môi trường tương đương sản xuất.
6. Chuyển lưu lượng hoặc ứng dụng theo kế hoạch có khả năng quay lui; chỉ ngừng dùng kho cũ khi đã xác nhận mọi phụ thuộc.
7. Xử lý bản sao cũ theo chính sách lưu trữ và hủy khóa khi vòng đời của chúng kết thúc.

Nếu mục tiêu là chuyển khóa sang KMS/HSM, cần đánh giá API import hoặc cơ chế tạo khóa trực tiếp trong dịch vụ đích. Một số khóa có thể không được phép xuất khỏi ranh giới bảo vệ; khi đó phải tạo khóa mới trong KMS/HSM và mã hóa lại dữ liệu hoặc thay đổi quy trình sử dụng khóa.

## 10. Khi nào nên tiếp tục dùng JCEKS?

JCEKS có thể vẫn cần thiết khi một ứng dụng Java hiện hữu phụ thuộc vào `SecretKeyEntry`, định dạng lưu trữ này đã được kiểm thử và tổ chức có kế hoạch duy trì tương thích trong một giai đoạn xác định. Khi đó, cần giới hạn phạm vi sử dụng, kiểm soát tệp và mật khẩu, kiểm kê khóa, giám sát truy cập và có lộ trình thay thế.

Với hệ thống mới, hãy chọn theo nhu cầu:

| Nhu cầu | Hướng lựa chọn nên đánh giá |
|---|---|
| Lưu khóa riêng và chứng thư theo định dạng dễ trao đổi giữa các nền tảng | PKCS12 |
| Duy trì tương thích với ứng dụng Java cũ có `SecretKeyEntry` trong JCEKS | JCEKS trong phạm vi được kiểm soát, kèm kế hoạch chuyển đổi |
| Quản lý khóa tập trung, audit, phân quyền và xoay vòng | KMS |
| Bảo vệ khóa trong phần cứng chuyên dụng, hạn chế trích xuất khóa | HSM hoặc dịch vụ KMS được hỗ trợ bởi HSM |

Không nên chọn JCEKS chỉ vì tên gọi có chữ “Cryptography Extension”. Mức bảo vệ thực tế phụ thuộc vào thuật toán của provider, cách quản lý mật khẩu, quyền truy cập tệp, khả năng kiểm toán và nơi khóa được sử dụng. Khi khóa có giá trị cao hoặc cần kiểm soát chặt, hãy đưa việc bảo vệ khóa vào kiến trúc KMS/HSM và chính sách quản lý khóa tổng thể.

## 11. Checklist rà soát một kho JCEKS

- Xác định rõ provider, phiên bản JDK và loại keystore mà ứng dụng đang sử dụng.
- Liệt kê alias, loại entry, chủ sở hữu, mục đích và ứng dụng phụ thuộc.
- Phân biệt keystore password với entry password; lưu chúng trong hệ thống quản lý bí mật.
- Xác minh quyền truy cập tệp, bản sao lưu, snapshot và log triển khai.
- Kiểm tra thuật toán, độ dài khóa, chuỗi chứng thư và mục đích sử dụng của từng entry.
- Không ghi mật khẩu, dữ liệu khóa hoặc kết quả `getEncoded()` vào log.
- Kiểm thử nạp, đọc, ghi và sử dụng khóa sau khi triển khai hoặc nâng cấp JDK/provider.
- Có quy trình sao lưu, khôi phục, xoay vòng, thu hồi và xử lý khi mật khẩu hoặc khóa bị lộ.
- Đánh giá chuyển đổi sang PKCS12 hoặc KMS/HSM khi có yêu cầu tương thích hay bảo vệ cao hơn.

JCEKS là một phần của lịch sử quản lý khóa trong Java và vẫn có thể xuất hiện trong các hệ thống đang vận hành. Hiểu đúng loại entry, cách bảo vệ mật khẩu và giới hạn của định dạng giúp đội ngũ duy trì hệ thống cũ an toàn hơn, đồng thời có cơ sở lập kế hoạch chuyển sang cơ chế quản lý khóa phù hợp với yêu cầu hiện đại.
