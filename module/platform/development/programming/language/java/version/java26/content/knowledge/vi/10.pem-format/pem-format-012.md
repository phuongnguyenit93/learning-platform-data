# Đóng tài nguyên đọc, ghi và tránh ghi khóa riêng vào log

PEM là định dạng văn bản chứa dữ liệu mã hóa Base64 của khóa, chứng chỉ hoặc dữ liệu mật mã khác. Một tệp PEM có thể chứa khóa công khai, chứng chỉ công khai hoặc khóa riêng. Vì vậy, không phải mọi nội dung PEM đều có cùng mức độ nhạy cảm: phần chứa PRIVATE KEY hoặc ENCRYPTED PRIVATE KEY phải được bảo vệ như bí mật xác thực.

Khi xử lý PEM trong Java, cần phân biệt vòng đời của luồng I/O với vòng đời của đối tượng mật mã. InputStream và OutputStream giữ tài nguyên hệ điều hành nên phải được đóng đúng lúc. PEMDecoder và PEMEncoder là các đối tượng cấu hình bất biến, an toàn cho nhiều thread và không phải tài nguyên cần đóng. Riêng dữ liệu PEM đã mã hóa ra byte array, password và PrivateKey cần được giữ trong phạm vi nhỏ nhất có thể; tuyệt đối không ghi chúng vào log.

Trong JDK 26, PEMDecoder, PEMEncoder, PEM và DEREncodable thuộc JEP 524 – PEM Encodings of Cryptographic Objects (Second Preview). Đây là preview API, cần bật preview khi biên dịch và chạy. Tính đến ngày 27/11/2026, JDK 27 đã GA và API tiếp tục là preview lần thứ ba theo JEP 538. Không coi API của một preview là hợp đồng ổn định giữa các bản JDK.

## 1. Xác định API và phiên bản JDK

Trong JDK 26, API nằm trong package java.security:

| Thành phần | Vai trò | Có cần đóng không? |
|---|---|---|
| PEMDecoder | Đọc PEM thành PrivateKey, PublicKey, X509Certificate, EncryptedPrivateKeyInfo hoặc PEMRecord | Không |
| PEMEncoder | Chuyển đối tượng mật mã thành PEM byte array hoặc String | Không |
| InputStream | Cung cấp dữ liệu PEM từ file hoặc nguồn khác | Có, nếu code của bạn sở hữu stream |
| OutputStream | Ghi dữ liệu PEM ra file hoặc đích khác | Có, nếu code của bạn sở hữu stream |
| byte[] từ PEMEncoder.encode() | Bộ đệm chứa nội dung PEM đã mã hóa | Không có close(); có thể xóa nội dung best-effort sau khi dùng |
| char[] password | Mật khẩu dùng để mã hóa hoặc giải mã khóa riêng | Không có close(); xóa mảng do ứng dụng sở hữu sau khi dùng |
| PrivateKey | Đối tượng khóa riêng đã giải mã | Không phải stream; không có bảo đảm xóa bộ nhớ chung cho mọi provider |

Biên dịch và chạy mã dùng PEM API preview bằng cùng JDK 26:

~~~powershell
javac --enable-preview --release 26 -d out src\PemResourceDemo.java
java --enable-preview -cp out PemResourceDemo
~~~

Phải bật preview ở cả compiler và runtime. Chỉ đặt JAVA_HOME thành JDK 26 mà thiếu --enable-preview vẫn không đủ để dùng các API preview.

Không cần đặt PEMDecoder hoặc PEMEncoder trong try-with-resources. Chúng không triển khai AutoCloseable và không sở hữu file descriptor. Điều cần đóng là stream mà ứng dụng mở để đọc hoặc ghi.

## 2. Xác định ai sở hữu stream

Quy tắc đóng tài nguyên phụ thuộc vào nơi tạo stream:

- Nếu phương thức tự gọi Files.newInputStream() hoặc Files.newOutputStream(), phương thức đó sở hữu stream và phải đóng nó.
- Nếu caller truyền một InputStream hoặc OutputStream đang được quản lý ở tầng bên ngoài, hãy làm rõ quyền sở hữu trong hợp đồng phương thức. Không tự đóng một stream mà caller vẫn cần dùng.
- Nếu tạo stream wrapper như BufferedInputStream hoặc BufferedOutputStream, đóng wrapper sẽ đóng stream bên dưới. Tránh đóng nhiều lần theo các nhánh code khác nhau.
- Nếu đọc PEM thất bại do lỗi I/O, vị trí đọc của InputStream có thể không còn nhất quán. Đóng stream đó và mở stream mới nếu cần thử lại; không tiếp tục decode từ vị trí không xác định.

PEMDecoder.decode(InputStream) đọc đến PEM footer hoặc đến hết stream. API này không quản lý vòng đời file mà ứng dụng đã mở. Hãy dùng try-with-resources quanh stream:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PublicKey;

static PublicKey readPublicKey(Path path) throws Exception {
    PEMDecoder decoder = PEMDecoder.of();

    try (InputStream input = Files.newInputStream(path)) {
        return decoder.decode(input, PublicKey.class);
    }
}
~~~

Trong ví dụ, stream được đóng ngay cả khi decode phát sinh IOException, IllegalArgumentException hoặc ClassCastException. Decoder không cần đóng và có thể được tái sử dụng.

Nếu phương thức nhận stream từ caller, không tự đóng stream:

~~~java
static PublicKey decodePublicKey(InputStream input) throws IOException {
    return PEMDecoder.of().decode(input, PublicKey.class);
}
~~~

Ở đây caller mở và đóng input. Ghi rõ quy ước này trong tài liệu API của phương thức để tránh rò rỉ tài nguyên hoặc đóng nhầm stream dùng chung.

## 3. Giải mã khóa riêng và đóng InputStream đúng cách

Với khóa riêng được lưu dưới dạng ENCRYPTED PRIVATE KEY, dùng decoder đã cấu hình giải mã. Nên yêu cầu kiểu trả về mong đợi bằng decode(InputStream, Class) thay vì nhận một kiểu PEM tổng quát rồi tự xử lý không kiểm soát.

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PEMDecoder;
import java.security.PrivateKey;
import java.util.Arrays;

static PrivateKey readEncryptedPrivateKey(
        Path pemFile,
        char[] password) throws IOException {

    try {
        PEMDecoder decoder =
                PEMDecoder.of().withDecryption(password);

        try (InputStream input = Files.newInputStream(pemFile)) {
            return decoder.decode(input, PrivateKey.class);
        }
    } finally {
        // Phương thức nhận quyền sử dụng và xóa mảng password do caller cấp.
        Arrays.fill(password, '\0');
    }
}
~~~

Đoạn mã thể hiện các điểm sau:

1. Password được truyền bằng char[] để ứng dụng có thể ghi đè mảng sau khi dùng.
2. withDecryption() tạo một decoder mới đã cấu hình giải mã.
3. decode(input, PrivateKey.class) yêu cầu kết quả là PrivateKey.
4. try-with-resources đóng InputStream khi decode thành công hoặc thất bại.
5. finally xóa mảng password mà phương thức nhận từ caller.

Nếu đọc khóa không mã hóa, dùng PEMDecoder.of().decode(input, PrivateKey.class) và bỏ bước cấu hình password. Không yêu cầu mật khẩu cho một tệp PRIVATE KEY không mã hóa.

Không gọi decode() nhiều lần trên cùng stream sau khi một lần decode đã gặp lỗi I/O. Javadoc cảnh báo vị trí đọc có thể không nhất quán. Đóng stream, ghi nhận lỗi bằng mã sự kiện an toàn và mở lại file nếu quy trình được phép thử lại.

Nếu file chứa nhiều khối PEM, hãy xác định rõ khối nào là đầu vào của thao tác. Không dùng một decoder không ràng buộc kiểu rồi ghi toàn bộ đối tượng PEM trả về vào log để tìm hiểu nội dung. Trong JDK 26, loại PEM không được ánh xạ thành đối tượng mật mã có thể được trả về dưới dạng PEMRecord; đối tượng này có thể chứa nội dung Base64 của dữ liệu gốc.

## 4. Mã hóa và ghi PEM ra file

PEMEncoder không ghi trực tiếp vào OutputStream. Phương thức encode() trả về byte[]; encodeToString() trả về String. Khi mã hóa khóa riêng, ưu tiên byte[] để tránh tạo thêm một String bất biến chứa toàn bộ PEM.

Ví dụ ghi khóa riêng đã mã hóa bằng password:

~~~java
import java.io.OutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.PEMEncoder;
import java.security.PrivateKey;
import java.util.Arrays;

static void writeEncryptedPrivateKey(
        Path destination,
        PrivateKey privateKey,
        char[] password) throws IOException {

    byte[] pemBytes = null;
    boolean outputCreated = false;

    try {
        PEMEncoder encoder =
                PEMEncoder.of().withEncryption(password);

        pemBytes = encoder.encode(privateKey);

        OutputStream opened = Files.newOutputStream(
                destination,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);

        outputCreated = true;

        try (OutputStream output = opened) {
            output.write(pemBytes);
        }

    } catch (IOException | RuntimeException | Error failure) {
        if (outputCreated) {
            try {
                Files.deleteIfExists(destination);
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
        }
        throw failure;

    } finally {
        if (pemBytes != null) {
            Arrays.fill(pemBytes, (byte) 0);
        }
        Arrays.fill(password, '\0');
    }
}
~~~

Phương thức trên nhận quyền sử dụng và xóa mảng password do caller truyền vào. Nó cũng xóa byte array PEM trong finally, kể cả khi ghi file thất bại.

CREATE_NEW yêu cầu file đích chưa tồn tại. Cách này tránh vô tình ghi đè một file khóa đang được sử dụng. Nếu tạo file thất bại trước khi OutputStream được mở, outputCreated vẫn false nên code không xóa nhầm file đã có từ trước.

Trong production, thư mục chứa khóa phải được bảo vệ trước khi ghi:

- Trên hệ thống POSIX, giới hạn quyền thư mục và file cho tài khoản dịch vụ cần sử dụng khóa, thường là thư mục chỉ owner truy cập và file chỉ owner đọc/ghi.
- Trên Windows, cấu hình ACL của thư mục cho đúng service account và quản trị viên được phép. File mới kế thừa ACL của thư mục; kiểm tra ACL thực tế trước khi đưa vào vận hành.
- Không ghi khóa vào thư mục tạm dùng chung, thư mục upload công khai, workspace source code hoặc thư mục log.
- Không tạo file với quyền rộng rồi mới sửa quyền sau khi ghi khóa. File có thể bị tiến trình khác đọc trong khoảng thời gian đó.

CREATE_NEW và try-with-resources giúp quản lý file và stream. Chúng không tự thiết lập ACL an toàn. Quyền truy cập phải được cấu hình tại thư mục hoặc bằng thuộc tính hệ thống phù hợp trước khi dữ liệu nhạy cảm xuất hiện.

Nếu ghi file lỗi sau khi file đã được tạo, code cố gắng xóa file chưa hoàn chỉnh và gắn lỗi cleanup thành suppressed exception. Việc xóa file không bảo đảm dữ liệu đã biến mất vật lý khỏi SSD, snapshot, journal hoặc backup. Với khóa quan trọng, thiết kế lưu trữ và vòng đời backup phải được kiểm soát riêng.

## 5. Không nhầm PEMEncoder với OutputStream

Hai bước mã hóa và ghi là hai hoạt động riêng:

~~~text
PrivateKey
    |
    v
PEMEncoder.encode(privateKey)
    |
    v
byte[] chứa PEM
    |
    v
OutputStream.write(byte[])
    |
    v
File đích
    |
    v
OutputStream.close()
~~~

PEMEncoder không mở file và không giữ file descriptor. OutputStream không biết dữ liệu nó nhận là khóa, chứng chỉ hay văn bản thông thường. Do đó:

- Đóng OutputStream để giải phóng file handle và hoàn tất ghi dữ liệu.
- Xóa byte[] nếu nó chứa khóa riêng và không còn cần dùng.
- Không cố gọi close() trên PEMEncoder.
- Không giả định đóng OutputStream sẽ xóa byte[] hoặc PrivateKey khỏi heap.
- Không dùng encodeToString(privateKey) nếu không cần String; String không thể được ghi đè sau khi tạo.

Nếu cần truyền PEM đến một API nhận OutputStream, áp dụng cùng quy tắc ownership. Nếu API bên ngoài sở hữu stream, hãy để bên gọi quyết định thời điểm đóng.

## 6. Password và bản sao trong PEMEncoder/PEMDecoder

JDK 26 quy định withEncryption(char[]) và withDecryption(char[]) sao chép mảng password rồi lưu bản sao trong instance được cấu hình. Vì vậy, có hai vùng dữ liệu cần phân biệt:

1. Mảng char[] ban đầu do ứng dụng cấp.
2. Bản sao password được giữ bên trong PEMEncoder hoặc PEMDecoder đã cấu hình.

Arrays.fill(password, '\0') chỉ ghi đè mảng ban đầu. Nó không truy cập và không xóa bản sao riêng bên trong encoder hoặc decoder.

Các biện pháp phù hợp:

- Lấy password từ secret manager, vault hoặc nguồn nhập bí mật được kiểm soát.
- Tránh hardcode password trong source code, file cấu hình, tham số dòng lệnh hoặc log.
- Dùng char[] và xóa mảng caller-owned ngay khi thao tác hoàn tất.
- Chỉ tạo encoder/decoder đã cấu hình encryption/decryption trong phạm vi cần thiết.
- Không giữ instance đã cấu hình password trong singleton, static field, cache hoặc service tồn tại lâu.
- Không chia sẻ một decoder giữ password giữa các thành phần không cần quyền giải mã.
- Không chuyển char[] thành String chỉ để tiện truyền qua nhiều lớp.

Ví dụ lấy password từ một thành phần cung cấp bí mật:

~~~java
char[] password = secretProvider.readPassword();
PrivateKey privateKey = readEncryptedPrivateKey(keyPath, password);
// readEncryptedPrivateKey đã xóa mảng password trước khi trả về.
usePrivateKey(privateKey);
~~~

Hợp đồng sở hữu password phải rõ ràng. Trong ví dụ trước, readEncryptedPrivateKey() xóa mảng password trong finally, do đó caller không được giả định mảng còn giá trị sau khi gọi.

Việc xóa mảng chỉ là biện pháp giảm thời gian tồn tại của bí mật trong heap. JVM, provider mật mã hoặc API có thể tạo bản sao nội bộ khác. Không có bảo đảm chung rằng mọi bản sao của password hay khóa riêng được xóa tức thì khỏi bộ nhớ.

PEMEncoder và PEMDecoder mặc định là immutable và thread-safe nên có thể tái sử dụng cho dữ liệu không cần password. Instance tạo từ withEncryption() hoặc withDecryption() vẫn immutable, nhưng giữ bản sao password; hãy giới hạn thời gian sống của chúng.

## 7. Mã hóa khóa riêng không thay thế bảo vệ file

PEM có thể chứa PRIVATE KEY không mã hóa hoặc ENCRYPTED PRIVATE KEY. Mã hóa khóa bằng password giúp bảo vệ dữ liệu khi file bị đọc trái phép, nhưng password phải được quản lý độc lập.

Không lưu password giải mã cạnh file khóa trong cùng thư mục hoặc cùng repository. Nếu kẻ tấn công lấy được cả file và password, lớp mã hóa không còn bảo vệ được khóa.

Đối với khóa được lưu lâu dài:

- Ưu tiên secret manager, KMS hoặc HSM khi yêu cầu bảo vệ và kiểm soát truy cập cao.
- Nếu buộc phải xuất PEM, dùng mã hóa PKCS #8 được tổ chức phê duyệt, bảo vệ ACL và giới hạn quyền đọc.
- Kiểm tra thuật toán và tham số PBE do provider sử dụng; không giả định mặc định giống nhau giữa mọi provider.
- Kiểm tra khả năng giải mã của các hệ thống đích trước khi triển khai luân chuyển khóa.
- Không đưa file khóa vào Git, artifact build, image container, gói cài đặt hoặc backup không được bảo vệ.
- Xác định chính sách rotation, thu hồi và xóa bản sao khóa trong các kho lưu trữ.

Trong JDK 26, thuật toán mã hóa mặc định của PEMEncoder.withEncryption() được xác định bởi security property jdk.epkcs8.defaultAlgorithm; tham số mặc định còn phụ thuộc provider. Nếu cần thuật toán hoặc tham số khác, API EncryptedPrivateKeyInfo cung cấp cách mã hóa với cấu hình rõ ràng. Hãy chọn theo chính sách mật mã hiện hành của tổ chức và kiểm thử khả năng tương thích của provider.

Nếu khóa được tạo trong HSM hoặc provider không cho phép xuất khóa, không cố lấy byte[] bằng PrivateKey.getEncoded() để tạo PEM. Khóa không xuất được cần được dùng trực tiếp qua provider cho ký hoặc giải mã. Không phải mọi PrivateKey đều có encoding khả dụng.

## 8. Tránh ghi khóa riêng vào log

PEM của khóa riêng là bí mật. Chỉ một dòng log vô tình chứa phần Base64 hoặc toàn bộ khối PEM cũng có thể làm lộ khóa cho người đọc log, hệ thống thu thập log, APM, bản sao lưu hoặc người có quyền truy cập pipeline.

Không ghi các dữ liệu sau:

- Nội dung file PEM, bao gồm cả phần header/footer và Base64.
- Giá trị byte[] trả về từ PEMEncoder.encode().
- Chuỗi trả về từ PEMEncoder.encodeToString().
- PrivateKey, KeyPair hoặc đối tượng chứa khóa bằng cách truyền trực tiếp vào logger.
- Kết quả PrivateKey.getEncoded() hoặc dữ liệu PKCS8EncodedKeySpec.
- Password, mảng char[] hoặc thông tin bí mật dùng để giải mã.
- PEMRecord hoặc PEM object nếu chúng chứa nội dung khóa.
- Request body, exception message hoặc debug dump có thể chứa toàn bộ PEM.
- Fingerprint của khóa riêng nếu không có nhu cầu nghiệp vụ đã được phê duyệt.

Không dựa vào việc toString() hiện tại của provider không hiển thị khóa. Cách biểu diễn đối tượng có thể khác giữa provider hoặc phiên bản JDK. Không đưa đối tượng khóa vào logger ngay cả khi chỉ muốn xem algorithm.

Có thể ghi metadata không bí mật và đã được kiểm soát:

| Trường log | Có thể ghi? | Điều kiện |
|---|---|---|
| Mã alias hoặc ID tham chiếu khóa | Có | Không phải giá trị bí mật; dùng ID đã được phê duyệt |
| Loại thao tác | Có | Ví dụ load, rotate, export hoặc decode |
| Thuật toán | Có | Ví dụ RSA hoặc EC; không kèm vật liệu khóa |
| Kết quả | Có | success hoặc failure |
| Mã lỗi ổn định | Có | Không chứa nội dung PEM hoặc password |
| Đường dẫn file | Có điều kiện | Tránh đường dẫn chứa username, tenant, bí mật hoặc thông tin nội bộ không cần thiết |
| Nội dung PEM/Base64 | Không | Có thể làm lộ khóa riêng |
| Password | Không | Bí mật xác thực |
| PrivateKey/KeyPair object | Không | Không phụ thuộc toString() của provider |

Ví dụ log an toàn:

~~~java
logger.info(
        "private-key-loaded alias={} algorithm={} result=success",
        keyAlias,
        privateKey.getAlgorithm());
~~~

Ví dụ ghi nhận lỗi mà không đưa dữ liệu PEM vào message:

~~~java
catch (RuntimeException failure) {
    logger.warn(
            "private-key-load-failed alias={} errorType={} eventId={}",
            keyAlias,
            failure.getClass().getSimpleName(),
            eventId);

    throw failure;
}
~~~

Nếu hệ thống cần stack trace để chẩn đoán, hãy xác minh trước rằng exception và cause không chứa dữ liệu đầu vào nhạy cảm. Có thể gửi chi tiết kỹ thuật vào kênh chẩn đoán có kiểm soát quyền truy cập, nhưng không đưa PEM, password hoặc key object vào message.

Không viết:

~~~java
// Sai: log toàn bộ khóa riêng.
logger.debug("Private key PEM: {}", pemString);

// Sai: log byte array chứa PEM.
logger.debug("Encoded key: {}", Arrays.toString(pemBytes));

// Sai: log object khóa.
logger.info("Loaded private key: {}", privateKey);

// Sai: log password.
logger.debug("PEM password: {}", password);
~~~

Việc thêm bộ lọc hoặc redaction vào log pipeline không thay thế việc ngăn bí mật đi vào logger. Không tạo log chứa bí mật rồi trông chờ hệ thống downstream che giấu nó.

## 9. Kiểm soát log, trace, metric và dữ liệu chẩn đoán

Log ứng dụng chỉ là một trong các nơi có thể lưu dữ liệu nhạy cảm. Kiểm tra cả:

- Log framework và log appender.
- HTTP access log và request/response body logging.
- APM agent, distributed tracing và span attributes.
- Metric labels hoặc tag được tạo từ alias, đường dẫn hay nội dung request.
- CI output, test report và snapshot.
- Heap dump, core dump, crash report và diagnostic bundle.
- JFR event tùy chỉnh do ứng dụng phát ra.
- Log tập trung, archive, backup và bản sao ở hệ thống phân tích.

Không đưa password, PEM hoặc key bytes vào tên metric, tag, span attribute hay custom JFR event. Không bật logging nội dung request/response ở môi trường production nếu request có thể chứa khóa.

JDK 27 bổ sung JEP 536 – JFR In-Process Data Redaction, có khả năng redaction command-line arguments và giá trị ban đầu của environment variables/system properties trong recording. Đây là lớp bảo vệ hữu ích cho dữ liệu được ghi ở các trường đó; nó không tự quét và xóa nội dung PEM do ứng dụng ghi vào log, custom event, heap dump hoặc chuỗi trong bộ nhớ. Vẫn phải tránh đưa bí mật vào những dữ liệu này ngay từ đầu.

## 10. Xử lý lỗi mà không làm lộ dữ liệu

Các lỗi khi đọc/ghi PEM có thể đến từ file không tồn tại, quyền truy cập, dữ liệu bị cắt, sai định dạng, loại PEM không mong đợi, sai password hoặc provider không hỗ trợ thuật toán.

| Hiện tượng | Cách xử lý |
|---|---|
| IOException khi đọc | Đóng stream bằng try-with-resources; không decode tiếp trên stream có vị trí không nhất quán |
| IllegalArgumentException khi PEM sai định dạng | Ghi mã lỗi và nguồn tham chiếu; không log nguyên văn file đầu vào |
| ClassCastException do sai loại PEM | Dùng decode(InputStream, Class) với kiểu mong đợi; kiểm tra loại dữ liệu ở tầng kiểm soát |
| Giải mã thất bại | Ghi event ID và loại lỗi; không ghi password, PEM hoặc key bytes |
| CREATE_NEW thất bại | Xác minh file đích đã tồn tại và quy trình rotation; không tự xóa file cũ |
| OutputStream.close() phát sinh IOException | Coi thao tác ghi chưa hoàn tất; không công bố file là khóa hợp lệ |
| Xóa file tạm không thành công | Ghi nhận cleanup failure riêng, giới hạn quyền file và xử lý theo quy trình sự cố |
| Provider không hỗ trợ encoding | Kiểm tra provider và khả năng export; không cố ép xuất khóa từ HSM |

Khi một thao tác ghi khóa thất bại, không được xem file đích là hoàn chỉnh. Quy trình triển khai nên dùng file tạm trong thư mục được bảo vệ, xác nhận ghi hoàn tất rồi mới chuyển file sang vị trí sử dụng bằng thao tác move phù hợp với filesystem. Việc chuyển file phải bảo đảm cùng filesystem nếu cần atomic move và phải xử lý trường hợp file đích đã tồn tại.

Không đưa nguyên nội dung exception vào log nếu exception được tạo từ dữ liệu do bên ngoài cung cấp. Có thể ghi exception class, mã lỗi, event ID và alias đã được kiểm soát để tra cứu.

## 11. Kiểm thử việc đóng tài nguyên và bảo vệ log

Tạo một bộ kiểm thử với khóa dùng riêng cho môi trường test. Không sử dụng private key production hoặc password thật trong test fixture.

Các kiểm tra nên thực hiện:

1. Đọc một PEM hợp lệ từ file bằng InputStream trong try-with-resources.
2. Đọc một file sai định dạng và xác nhận stream vẫn được đóng.
3. Thử sai password với một khóa mã hóa; xác nhận lỗi được xử lý mà không ghi nội dung file hoặc password vào log.
4. Ghi khóa riêng mã hóa bằng PEMEncoder.encode(), ghi byte[] vào file và xác nhận OutputStream được đóng.
5. Cố ghi vào file đã tồn tại bằng CREATE_NEW; xác nhận code không ghi đè hoặc xóa file cũ.
6. Giả lập lỗi ghi để xác nhận file chưa hoàn chỉnh được xử lý và byte[]/password caller-owned được xóa trong finally.
7. Kiểm tra quyền thư mục và file bằng công cụ hệ điều hành; xác nhận chỉ service account và vai trò được phê duyệt có thể đọc khóa.
8. Dùng log test appender để tìm các chuỗi nhạy cảm như BEGIN PRIVATE KEY, BEGIN ENCRYPTED PRIVATE KEY, Base64 của fixture và password sentinel.
9. Kiểm tra log của APM, tracing và CI để xác nhận không có request body hoặc secret attribute.
10. Chạy test bằng đúng JDK 26 với --enable-preview; khi nâng cấp, chạy lại trên JDK mục tiêu và cập nhật API tương ứng.

Một phép kiểm tra log có thể dùng chuỗi sentinel giả trong fixture:

~~~java
String forbidden = "TEST_ONLY_PRIVATE_KEY_SENTINEL";

String capturedLogs = testLogAppender.getCapturedText();

if (capturedLogs.contains(forbidden)
        || capturedLogs.contains("BEGIN PRIVATE KEY")
        || capturedLogs.contains("BEGIN ENCRYPTED PRIVATE KEY")) {
    throw new AssertionError("Sensitive PEM data appeared in logs");
}
~~~

Đây chỉ là kiểm tra bổ sung. Nó không chứng minh mọi secret đều được loại bỏ; hãy kiểm tra các logger, appender, trace exporter và hệ thống lưu trữ thực tế.

## 12. Khác biệt khi nâng cấp từ JDK 26 lên JDK 27

PEM API vẫn là preview trong JDK 27, nhưng đã có thay đổi về kiểu dữ liệu và một số tên phương thức. JDK 27 dùng JEP 538 – PEM Encodings of Cryptographic Objects (Third Preview).

| Thành phần | JDK 26 – JEP 524 | JDK 27 – JEP 538 |
|---|---|---|
| Trạng thái | Second Preview | Third Preview |
| Interface nền | DEREncodable | BinaryEncodable |
| Kiểu biểu diễn PEM không ánh xạ thành crypto object | PEMRecord | PEM |
| Cấu hình provider của decoder | withFactory(Provider) | withFactoriesOf(Provider) |
| Lỗi giải mã/decryption | IllegalArgumentException và RuntimeException theo API JDK 26 | Có CryptoException preview cho lỗi decryption |
| API đọc/ghi stream | decode(InputStream, Class), encode trả byte[] | Vẫn có decode(InputStream, Class), encode trả byte[] |

Khi nâng cấp:

1. Dùng compiler và runtime JDK 27, bật preview của chính JDK 27.
2. Đổi các kiểu DEREncodable sang BinaryEncodable nếu mã nguồn tham chiếu trực tiếp interface.
3. Cập nhật PEMRecord thành PEM khi xử lý loại PEM không ánh xạ thành đối tượng mật mã.
4. Đổi withFactory() thành withFactoriesOf().
5. Cập nhật xử lý lỗi decryption theo CryptoException của JDK 27.
6. Giữ nguyên nguyên tắc ownership: code mở stream phải đóng stream; không cố đóng PEMDecoder hoặc PEMEncoder.
7. Kiểm tra lại password handling và logging vì các thay đổi API preview không làm giảm yêu cầu bảo vệ bí mật.

Không trộn class file hoặc preview API đã biên dịch từ JDK 26 với runtime JDK 27. Hãy biên dịch và kiểm thử lại bằng đúng JDK mục tiêu. Nếu cần dùng API PEM trong sản phẩm cần tương thích lâu dài, cân nhắc trì hoãn phụ thuộc cho đến khi API trở thành chính thức hoặc cô lập nó sau một adapter nội bộ có kiểm thử nâng cấp.

## 13. Bài thực hành tổng hợp

Thực hiện trên JDK 26 với preview:

1. Tạo một khóa riêng test và xuất thành PEM mã hóa bằng PEMEncoder.withEncryption().
2. Dùng Files.newOutputStream() với try-with-resources để ghi byte[] PEM ra file trong thư mục đã bảo vệ.
3. Xóa byte[] PEM và password caller-owned sau khi ghi.
4. Đọc lại file bằng PEMDecoder.withDecryption() và Files.newInputStream() trong try-with-resources.
5. So sánh algorithm và public key tương ứng để xác nhận cặp khóa đã giải mã đúng. Không in private key hoặc dữ liệu PEM ra console.
6. Thử file sai định dạng, sai password và file không có quyền đọc. Xác nhận stream luôn được đóng.
7. Thử file đích đã tồn tại và lỗi ghi giữa chừng. Xác nhận file cũ không bị ghi đè và file chưa hoàn chỉnh không được dùng.
8. Bật log ở mức debug trong test. Xác nhận log chỉ có alias, algorithm, event ID và kết quả.
9. Kiểm tra log appender, trace, metric và test report để chắc chắn không có PEM body, Base64, password hoặc private key object.
10. Chạy lại các bước trên JDK 27 sau khi chuyển API sang JEP 538 Third Preview.

**Tiêu chí hoàn thành:** phân biệt được resource cần close và đối tượng không cần close; đóng stream ở đúng nơi sở hữu; xử lý lỗi mà không tiếp tục dùng stream có vị trí không xác định; xóa buffer/password caller-owned theo best-effort; hiểu bản sao password bên trong encoder/decoder; ghi khóa với ACL phù hợp; thiết kế log chỉ chứa metadata an toàn; nhận diện các thay đổi PEM preview giữa JDK 26 và JDK 27.

## 14. Tài liệu tham khảo chính thức

- [JEP 524: PEM Encodings of Cryptographic Objects (Second Preview)](https://openjdk.org/jeps/524) — phạm vi PEM API trong JDK 26.
- [Java 26 PEMDecoder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMDecoder.html) — decode từ String/InputStream, chọn kiểu kết quả và cấu hình giải mã.
- [Java 26 PEMEncoder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html) — encode ra byte[]/String và mã hóa khóa riêng bằng password.
- [Java 26 JCA Reference Guide – PEM Transport Format](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — cách dùng PEMDecoder, PEMEncoder, EncryptedPrivateKeyInfo và PEM.
- [Java 26 AutoCloseable API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html) — quy tắc đóng tài nguyên bằng try-with-resources.
- [RFC 7468: Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468.html) — cấu trúc PEM text và các nhãn dữ liệu mật mã.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu cần loại khỏi log, bao gồm encryption keys và các bí mật xác thực.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — xác nhận PEM API là Third Preview theo JEP 538 và các thay đổi liên quan.
- [Java 27 PEMDecoder API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMDecoder.html) — BinaryEncodable, PEM, withFactoriesOf() và CryptoException.

Tài liệu của đúng JDK là nguồn chuẩn để xác định API preview và exception. Dù PEM API thay đổi giữa các release, ownership của stream và nguyên tắc không ghi khóa riêng vào log vẫn là yêu cầu cần giữ trong mọi phiên bản.

