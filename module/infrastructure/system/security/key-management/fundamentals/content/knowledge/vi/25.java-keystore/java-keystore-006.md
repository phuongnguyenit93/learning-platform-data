# KeyStore entry

Trong Java KeyStore, một **entry** là một mục được lưu trong kho khóa, đại diện cho một loại tài liệu mật mã hoặc thông tin chứng thực cụ thể. Ứng dụng truy cập entry thông qua một **alias** (tên định danh), còn kiểu entry cho biết mục đó chứa khóa riêng, khóa bí mật hay chứng chỉ tin cậy.

Hiểu đúng entry giúp ứng dụng chọn đúng API, bảo vệ đúng loại vật liệu mật mã và tránh nhầm lẫn giữa việc lưu một chứng chỉ với việc lưu khóa riêng tương ứng. Đây là một phần của quản lý vòng đời khóa: tạo hoặc nhập khóa, lưu trữ, cấp quyền sử dụng, thay thế khi xoay vòng và loại bỏ khi không còn cần thiết.

## 1. Entry nằm ở đâu trong mô hình KeyStore?

**KeyStore** là API Java đại diện cho một kho chứa khóa và chứng chỉ. Kho có thể được lưu trong tệp, được cung cấp bởi một nhà cung cấp mật mã (provider), hoặc ánh xạ tới thiết bị bảo mật như HSM hay token PKCS#11. Vì vậy, đối tượng KeyStore trong chương trình không đồng nghĩa với một định dạng tệp cụ thể.

Khi làm việc với một entry, cần phân biệt ba yếu tố:

- **Alias:** tên mà ứng dụng dùng để tìm entry. Alias không phải khóa và cũng không phải mật khẩu.
- **Vật liệu mật mã:** dữ liệu được entry lưu, chẳng hạn khóa riêng cùng chuỗi chứng chỉ, khóa đối xứng hoặc chứng chỉ tin cậy.
- **Tham số bảo vệ (ProtectionParameter):** thông tin được truyền cho API để provider bảo vệ hoặc truy cập entry, thường là mật khẩu nhưng cũng có thể là cơ chế khác.

Java biểu diễn các mục này bằng giao diện lồng **KeyStore.Entry**. Ba lớp entry phổ biến là **PrivateKeyEntry**, **SecretKeyEntry** và **TrustedCertificateEntry**.

| Loại entry | Vật liệu được lưu | Trường hợp sử dụng |
|---|---|---|
| **PrivateKeyEntry** | Một khóa riêng và chuỗi chứng chỉ tương ứng | Danh tính máy chủ, mTLS, ký số |
| **SecretKeyEntry** | Một khóa bí mật, thường dùng cho mật mã đối xứng | Mã hóa hoặc giải mã dữ liệu |
| **TrustedCertificateEntry** | Một chứng chỉ được cấu hình làm chứng chỉ tin cậy | Truststore, xác minh chuỗi chứng chỉ |

Provider và loại KeyStore quyết định những loại entry nào được hỗ trợ cũng như cách chúng được tuần tự hóa và bảo vệ. Không nên giả định mọi định dạng đều hỗ trợ mọi loại entry theo cùng một cách.

## 2. Ba loại entry chính

### 2.1. PrivateKeyEntry

**PrivateKeyEntry** chứa một đối tượng **PrivateKey** cùng một mảng chứng chỉ (**Certificate[]**) tạo thành chuỗi chứng chỉ của khóa đó.

Phần tử đầu tiên trong chuỗi phải là chứng chỉ chứa khóa công khai tương ứng với khóa riêng. Các phần tử tiếp theo là chứng chỉ của tổ chức phát hành ở các cấp cao hơn. Việc có đưa chứng chỉ gốc vào chuỗi hay không phụ thuộc cấu hình PKI và yêu cầu trao đổi với bên nhận.

Ví dụ, một máy chủ HTTPS có thể lưu khóa riêng dùng cho TLS cùng chứng chỉ máy chủ và các chứng chỉ trung gian trong một PrivateKeyEntry. Khi máy chủ bắt tay TLS, thư viện TLS sử dụng khóa riêng để chứng minh quyền sở hữu danh tính và gửi chuỗi chứng chỉ cho phía bên kia kiểm tra.

Điểm cần nhớ:

- Chứng chỉ chứa khóa công khai và thông tin định danh; nó không chứa khóa riêng.
- Khóa riêng và chuỗi chứng chỉ phải khớp nhau. Nếu ghép nhầm, thao tác ký hoặc bắt tay TLS có thể thất bại.
- Entry này cần được bảo vệ phù hợp vì lộ khóa riêng có thể cho phép kẻ tấn công giả mạo danh tính hoặc giải mã dữ liệu trong một số giao thức và cấu hình.
- Không phải provider nào cũng cho phép xuất khóa riêng dưới dạng byte. Với khóa nằm trong HSM, đối tượng PrivateKey có thể chỉ là một tham chiếu tới khóa không thể xuất.

### 2.2. SecretKeyEntry

**SecretKeyEntry** chứa một đối tượng **SecretKey**, thường là khóa đối xứng như AES hoặc HMAC. Cùng một khóa có thể được dùng để mã hóa và giải mã, hoặc để tạo và xác minh mã xác thực thông điệp, tùy thuật toán.

Ví dụ, một dịch vụ có thể lưu khóa AES dùng để giải mã dữ liệu đã mã hóa. Ứng dụng lấy entry theo alias, sau đó chuyển đối tượng khóa cho API mật mã phù hợp.

Khóa bí mật không có chuỗi chứng chỉ như PrivateKeyEntry. Việc provider có hỗ trợ lưu loại khóa này hay không phụ thuộc định dạng và provider đang sử dụng. Cần xác minh khả năng tương thích trên đúng JDK và môi trường triển khai trước khi chọn định dạng cho hệ thống.

### 2.3. TrustedCertificateEntry

**TrustedCertificateEntry** lưu một chứng chỉ được ứng dụng cấu hình là tin cậy. Entry này không chứa khóa riêng.

Một truststore có thể chứa chứng chỉ CA gốc hoặc chứng chỉ được tin cậy trực tiếp theo chính sách của tổ chức. Khi xác minh kết nối TLS, thành phần quản lý trust có thể dùng các chứng chỉ này làm cơ sở xây dựng và kiểm tra chuỗi chứng chỉ.

Sự hiện diện của một chứng chỉ trong KeyStore tự nó không chứng minh chứng chỉ đó hợp lệ trong mọi ngữ cảnh. Ứng dụng vẫn phải áp dụng kiểm tra chuỗi, thời hạn, mục đích sử dụng, trạng thái thu hồi và chính sách tin cậy phù hợp.

Không dùng TrustedCertificateEntry để lưu chứng chỉ đi kèm khóa riêng của chính ứng dụng. Với danh tính có khóa riêng, hãy dùng PrivateKeyEntry để giữ khóa và chuỗi chứng chỉ trong cùng một entry.

## 3. Alias định danh entry

Alias là tên logic mà ứng dụng dùng để thao tác với một entry. Ví dụ:

- **api-server-tls**
- **partner-root-ca**
- **customer-data-aes-v3**

Alias nên ngắn gọn, ổn định và thể hiện mục đích sử dụng. Không đưa mật khẩu, khóa, token truy cập hoặc dữ liệu nhạy cảm vào alias. Không dùng alias làm cơ chế phân quyền: biết alias không có nghĩa là người gọi được phép sử dụng khóa.

Khi thiết kế alias, cần lưu ý:

- Xem alias là không phân biệt chữ hoa và chữ thường để tránh xung đột khi chuyển đổi giữa provider hoặc định dạng.
- Đặt quy tắc đặt tên và quy tắc phiên bản thống nhất giữa các dịch vụ.
- Kiểm tra alias đã tồn tại trước khi thêm entry. Các thao tác ghi vào alias hiện có có thể thay thế entry cũ.
- Không dựa vào thứ tự liệt kê alias để xác định entry mới nhất hoặc quan trọng nhất.
- Không coi ngày tạo do **getCreationDate** trả về là bằng chứng kiểm toán duy nhất; thông tin này phụ thuộc provider và có thể không đủ cho yêu cầu audit.

Một alias có thể được kiểm tra bằng **containsAlias**. Có thể dùng **entryInstanceOf**, **isKeyEntry** hoặc **isCertificateEntry** để xác định loại entry trước khi lấy vật liệu mật mã.

## 4. Bảo vệ entry và bảo vệ toàn bộ kho

Java tách API truy cập entry khỏi cách provider lưu trữ và bảo vệ dữ liệu. Hai lớp bảo vệ thường gặp là:

1. **Bảo vệ kho:** mật khẩu được truyền vào **load** hoặc **store** có thể được provider dùng để kiểm tra tính toàn vẹn, bảo vệ nội dung hoặc thực hiện các xử lý đặc thù của định dạng.
2. **Bảo vệ entry:** tham số **ProtectionParameter** được truyền vào **getEntry** hoặc **setEntry** để provider bảo vệ vật liệu của entry. Cơ chế phổ biến là **KeyStore.PasswordProtection**.

Hai lớp này có thể dùng cùng một mật khẩu hoặc dùng thông tin xác thực khác nhau. Hành vi cụ thể phụ thuộc định dạng và provider. Không nên suy luận rằng mọi loại KeyStore đều có cùng cách mã hóa khóa riêng, kiểm tra tính toàn vẹn hoặc xử lý mật khẩu entry.

Ví dụ về bảo vệ bằng mật khẩu:

~~~java
KeyStore.PasswordProtection protection =
    new KeyStore.PasswordProtection(entryPassword);

try {
    keyStore.setEntry(
        "api-server-tls",
        new KeyStore.PrivateKeyEntry(privateKey, certificateChain),
        protection
    );
} finally {
    try {
        protection.destroy();
    } finally {
        Arrays.fill(entryPassword, '\0');
    }
}
~~~

Ví dụ này minh họa việc truyền thông tin bảo vệ khi ghi entry và chủ động hủy bản sao mật khẩu do PasswordProtection quản lý. Trong mã thực tế, cần xử lý ngoại lệ khi hủy, bảo đảm mảng mật khẩu thuộc quyền quản lý của đoạn mã gọi và không xóa mảng vẫn đang được thành phần khác sử dụng.

**ProtectionParameter** là một abstraction. Ngoài PasswordProtection, provider hoặc ứng dụng có thể dùng cơ chế khác được API hỗ trợ. Không nên gắn cứng giả định rằng mọi entry đều được bảo vệ bằng mật khẩu.

## 5. Thao tác với entry bằng Java API

### 5.1. Tạo KeyStore và thêm entry

Ví dụ dưới đây tạo một kho PKCS#12 mới, thêm khóa riêng cùng chuỗi chứng chỉ, rồi ghi kho ra tệp. Đoạn mã giả định ứng dụng đã có PrivateKey, chuỗi chứng chỉ hợp lệ và các mật khẩu được lấy từ một nguồn bảo mật.

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.util.Arrays;

public class KeyStoreEntryWriter {
    public static void create(
            Path path,
            PrivateKey privateKey,
            Certificate[] certificateChain,
            char[] storePassword,
            char[] entryPassword) throws Exception {

        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        keyStore.load(null, storePassword);

        KeyStore.PasswordProtection protection =
            new KeyStore.PasswordProtection(entryPassword);

        try {
            KeyStore.PrivateKeyEntry entry =
                new KeyStore.PrivateKeyEntry(privateKey, certificateChain);

            keyStore.setEntry("api-server-tls", entry, protection);
        } finally {
            try {
                protection.destroy();
            } finally {
                Arrays.fill(entryPassword, '\0');
            }
        }

        try (OutputStream output = Files.newOutputStream(path)) {
            keyStore.store(output, storePassword);
        }
    }
}
~~~

Trong ví dụ:

- **getInstance("PKCS12")** chọn rõ loại KeyStore để tránh phụ thuộc cấu hình mặc định của môi trường.
- **load(null, storePassword)** khởi tạo một kho mới chưa có dữ liệu.
- **PrivateKeyEntry** gom khóa riêng và chuỗi chứng chỉ thành một mục logic.
- **setEntry** ghi entry dưới alias **api-server-tls** và nhận tham số bảo vệ entry.
- **store** ghi trạng thái kho ra tệp. Mật khẩu kho được provider xử lý theo quy tắc của PKCS#12 và provider tương ứng.

Đây là ví dụ minh họa API. Khi triển khai, cần bảo đảm thư mục lưu trữ có quyền truy cập phù hợp, tệp không bị ghi đè ngoài ý muốn, mật khẩu không nằm trong mã nguồn và provider đang dùng hỗ trợ loại entry mong muốn.

Có thể thêm chứng chỉ tin cậy bằng API chuyên biệt:

~~~java
keyStore.setCertificateEntry("partner-root-ca", trustedCertificate);
~~~

API này tạo một entry chứa chứng chỉ tin cậy. Nếu cần lưu khóa đối xứng, có thể dùng SecretKeyEntry khi provider hỗ trợ:

~~~java
KeyStore.SecretKeyEntry entry =
    new KeyStore.SecretKeyEntry(secretKey);

keyStore.setEntry(
    "customer-data-aes-v3",
    entry,
    new KeyStore.PasswordProtection(entryPassword)
);
~~~

### 5.2. Đọc và kiểm tra entry

Để đọc một kho đã tồn tại, ứng dụng tải dữ liệu bằng loại KeyStore và thông tin xác thực phù hợp. Sau đó, ứng dụng lấy entry theo alias và kiểm tra kiểu trước khi sử dụng.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.util.Arrays;

public class KeyStoreEntryReader {
    public static PrivateKey readPrivateKey(
            Path path,
            String alias,
            char[] storePassword,
            char[] entryPassword) throws Exception {

        KeyStore keyStore = KeyStore.getInstance("PKCS12");

        try (InputStream input = Files.newInputStream(path)) {
            keyStore.load(input, storePassword);
        }

        if (!keyStore.containsAlias(alias)) {
            throw new IllegalArgumentException("Alias không tồn tại: " + alias);
        }

        if (!keyStore.entryInstanceOf(
                alias, KeyStore.PrivateKeyEntry.class)) {
            throw new IllegalArgumentException(
                "Entry không chứa khóa riêng: " + alias
            );
        }

        KeyStore.PasswordProtection protection =
            new KeyStore.PasswordProtection(entryPassword);

        try {
            KeyStore.Entry entry = keyStore.getEntry(alias, protection);

            if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
                throw new IllegalStateException(
                    "Kiểu entry không đúng như mong đợi"
                );
            }

            KeyStore.PrivateKeyEntry privateKeyEntry =
                (KeyStore.PrivateKeyEntry) entry;

            return privateKeyEntry.getPrivateKey();
        } finally {
            try {
                protection.destroy();
            } finally {
                Arrays.fill(entryPassword, '\0');
            }
        }
    }
}
~~~

**getEntry** trả về một đối tượng thuộc kiểu **KeyStore.Entry**. Sau khi xác nhận kiểu, ứng dụng có thể truy cập vật liệu phù hợp:

- **PrivateKeyEntry.getPrivateKey()** lấy khóa riêng.
- **PrivateKeyEntry.getCertificateChain()** lấy chuỗi chứng chỉ.
- **SecretKeyEntry.getSecretKey()** lấy khóa bí mật.
- **TrustedCertificateEntry.getTrustedCertificate()** lấy chứng chỉ tin cậy.

Có thể dùng **getKey(alias, password)** khi chỉ cần lấy khóa. Tuy nhiên, getEntry giúp thể hiện rõ kiểu entry và cho phép xử lý cả chứng chỉ gắn với khóa riêng. Không gọi getKey rồi giả định kết quả luôn là khóa riêng: kết quả có thể là khóa bí mật.

Khi dùng khóa từ HSM hoặc provider không cho xuất khóa, không nên giả định **getEncoded()** sẽ trả về byte của khóa. Giá trị có thể là null hoặc khóa được biểu diễn bằng một đối tượng không thể xuất. Ứng dụng nên chuyển đối tượng khóa trực tiếp cho API mật mã tương thích.

### 5.3. Liệt kê, thay thế và xóa entry

Một số API thường dùng để quản lý entry:

| API | Mục đích |
|---|---|
| **aliases()** | Liệt kê các alias hiện có |
| **containsAlias(alias)** | Kiểm tra alias có tồn tại |
| **entryInstanceOf(alias, type)** | Kiểm tra entry có thuộc kiểu chỉ định |
| **isKeyEntry(alias)** | Kiểm tra alias trỏ tới entry chứa khóa |
| **isCertificateEntry(alias)** | Kiểm tra alias trỏ tới entry chứng chỉ |
| **getEntry(alias, protection)** | Lấy entry theo alias |
| **setEntry(alias, entry, protection)** | Thêm hoặc thay entry tại alias |
| **deleteEntry(alias)** | Xóa entry khỏi kho |
| **getCertificate(alias)** | Lấy chứng chỉ gắn với alias nếu có |
| **getCertificateChain(alias)** | Lấy chuỗi chứng chỉ của key entry |

Cần đặc biệt cẩn trọng với thao tác ghi vào alias đang tồn tại. Nếu ứng dụng vô tình dùng lại alias, entry cũ có thể bị thay thế. Với khóa đang phục vụ giao dịch, hãy kiểm tra trạng thái sử dụng và kế hoạch chuyển đổi trước khi thay thế.

Xóa entry chỉ loại bỏ mục khỏi KeyStore mà thao tác đó tác động. Việc này không bảo đảm mọi bản sao của khóa đã bị xóa khỏi bộ nhớ, bản sao lưu, máy chủ khác hoặc thiết bị khác. Tương tự, xóa một chứng chỉ khỏi truststore không đồng nghĩa với việc CA hoặc tổ chức phát hành đã thu hồi chứng chỉ đó trên toàn hệ thống.

## 6. Entry trong vòng đời quản lý khóa

Entry là đơn vị thao tác quan trọng trong từng giai đoạn quản lý khóa:

1. **Tạo hoặc nhập:** sinh khóa trong provider phù hợp hoặc nhập khóa theo quy trình được kiểm soát. Với khóa riêng, chuẩn bị chuỗi chứng chỉ khớp với khóa.
2. **Đặt alias và lưu:** chọn alias theo quy ước, chọn loại entry đúng mục đích và cung cấp tham số bảo vệ thích hợp.
3. **Cấp quyền sử dụng:** giới hạn tiến trình, tài khoản hệ điều hành và thành phần ứng dụng được mở kho hoặc yêu cầu provider sử dụng khóa. Alias không thay thế kiểm soát truy cập.
4. **Sử dụng:** lấy đúng entry, xác minh kiểu và dùng khóa trực tiếp trong thao tác mật mã cần thiết. Hạn chế xuất khóa ra định dạng byte hoặc sao chép không cần thiết.
5. **Xoay vòng:** tạo entry cho phiên bản khóa mới, cập nhật ứng dụng sử dụng khóa mới, kiểm tra hoạt động và chỉ loại bỏ entry cũ khi chính sách lưu giữ, giải mã dữ liệu cũ hoặc xác minh chữ ký đã được xử lý.
6. **Thu hồi hoặc loại bỏ:** nếu chứng chỉ bị thu hồi, cập nhật chính sách kiểm tra trạng thái chứng chỉ và truststore khi cần. Nếu khóa không còn được phép sử dụng, chặn quyền truy cập và thực hiện quy trình loại bỏ trên mọi nơi có bản sao.
7. **Sao lưu và khôi phục:** bảo vệ bản sao KeyStore cùng thông tin cần thiết để khôi phục. Bản sao lưu chứa khóa riêng hoặc khóa bí mật phải có mức bảo vệ tương đương kho đang hoạt động.

Một quy ước alias có phiên bản như **customer-data-aes-v3** giúp ứng dụng nhận biết khóa đang dùng và hỗ trợ chuyển đổi có kiểm soát. Tuy nhiên, chỉ đổi alias không tạo ra khóa mới; hệ thống phải thực sự sinh hoặc nhập vật liệu khóa mới và cập nhật các tham chiếu liên quan.

## 7. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Lưu chứng chỉ máy chủ bằng TrustedCertificateEntry trong khi cần khóa riêng | Ứng dụng không có khóa riêng để ký hoặc chứng minh danh tính | Dùng PrivateKeyEntry với khóa riêng và chuỗi chứng chỉ |
| Lấy entry nhưng không kiểm tra kiểu | Ép kiểu sai hoặc sử dụng nhầm loại khóa | Dùng entryInstanceOf hoặc kiểm tra kiểu đối tượng |
| Cho rằng mọi provider hỗ trợ SecretKeyEntry | Lỗi khi lưu hoặc đọc khóa đối xứng trên môi trường triển khai | Kiểm tra khả năng hỗ trợ trên đúng provider và phiên bản JDK |
| Dùng lại alias mà không kiểm tra | Entry cũ có thể bị thay thế ngoài dự kiến | Kiểm tra tồn tại, quản lý phiên bản và kiểm soát thao tác ghi |
| Ghi mật khẩu trong mã nguồn hoặc log | Người có quyền đọc mã/log có thể truy cập kho hoặc entry | Lấy bí mật từ secret manager hoặc cơ chế cấp phát phù hợp; không ghi log |
| Cho rằng xóa entry đã hủy mọi bản sao khóa | Khóa vẫn có thể tồn tại trong bản sao lưu hoặc hệ thống khác | Thực hiện quy trình loại bỏ trên toàn bộ phạm vi lưu trữ và sử dụng |
| Cho rằng chứng chỉ trong truststore luôn hợp lệ | Có thể bỏ qua thời hạn, thu hồi hoặc chính sách xác minh | Thực hiện đầy đủ kiểm tra chứng chỉ và chính sách tin cậy |

## 8. Nguyên tắc thiết kế an toàn

- Chọn rõ loại KeyStore và provider trong cấu hình triển khai. Không để hành vi phụ thuộc ngầm vào loại mặc định của JDK.
- Dùng PrivateKeyEntry cho danh tính có khóa riêng, SecretKeyEntry cho khóa bí mật và TrustedCertificateEntry cho chứng chỉ được cấu hình tin cậy.
- Tách biệt trách nhiệm quản trị kho, cấp quyền sử dụng khóa và vận hành ứng dụng. Người có thể đọc tệp không nhất thiết phải có quyền sử dụng mọi khóa trong đó.
- Bảo vệ mật khẩu và PIN bằng cơ chế quản lý bí mật. Không lưu chúng cùng tệp KeyStore theo cách khiến một sự cố lộ tệp đồng thời làm lộ thông tin mở khóa.
- Hạn chế quyền đọc và ghi tệp KeyStore, bảo vệ đường dẫn lưu trữ và kiểm soát quyền truy cập bản sao lưu.
- Với khóa có giá trị cao, cân nhắc provider kết nối HSM hoặc thiết bị bảo mật để giữ khóa trong vùng bảo vệ và hạn chế khả năng xuất khóa.
- Ghi nhận các thao tác tạo, thay thế, đọc hoặc xóa entry ở hệ thống kiểm toán phù hợp. Log chỉ nên chứa alias, định danh thao tác, thời điểm và kết quả cần thiết; tuyệt đối không ghi vật liệu khóa hay mật khẩu.
- Kiểm thử quy trình khôi phục và xoay vòng. Một entry được lưu thành công chưa chứng minh ứng dụng có thể khôi phục và sử dụng khóa sau sự cố.

Khi thiết kế API nội bộ cho ứng dụng, nên đóng gói thao tác lấy entry trong một thành phần có trách nhiệm kiểm tra alias, kiểu entry, quyền truy cập và xử lý lỗi. Các thành phần nghiệp vụ chỉ nên nhận đối tượng khóa cần thiết cho thao tác mật mã, tránh tự mở kho và tự quản lý mật khẩu ở nhiều nơi.
