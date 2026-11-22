# 1.6 Bảo vệ dữ liệu khi truyền, khi lưu trữ và trong bộ nhớ

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt ba trạng thái của dữ liệu (đang truyền, đang lưu trữ, đang được xử lý trong bộ nhớ), chỉ ra ranh giới bảo vệ của từng biện pháp, chọn cơ chế bảo vệ phù hợp trong ứng dụng Java và nhận diện những lỗi triển khai thường khiến dữ liệu nhạy cảm bị lộ dù hệ thống đã “bật mã hóa”.

## 1. Nhìn từ vòng đời dữ liệu và mô hình đe dọa

Một giá trị nhạy cảm như thông tin cá nhân, token, khóa bí mật hoặc dữ liệu thanh toán thường đi qua nhiều trạng thái:

1. **Data in transit (đang truyền):** dữ liệu di chuyển qua mạng, ví dụ trình duyệt → API, API → cơ sở dữ liệu, ứng dụng → message broker hoặc dịch vụ nội bộ.
2. **Data at rest (đang lưu trữ):** dữ liệu nằm trên ổ đĩa, bảng cơ sở dữ liệu, object storage, cache có lưu bền, bản sao lưu, snapshot hoặc tệp log.
3. **Data in use (đang xử lý trong bộ nhớ):** dữ liệu đã được giải mã/đọc vào Java heap, bộ nhớ native, buffer, cache trong tiến trình hoặc thanh ghi CPU để ứng dụng thực hiện nghiệp vụ.

| Trạng thái | Rủi ro điển hình | Kiểm soát cốt lõi | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Đang truyền | Nghe lén, giả mạo đầu cuối, sửa gói tin | TLS, xác thực chứng chỉ, mTLS khi cần, phân quyền API | TLS bảo vệ **đoạn kết nối** giữa hai đầu TLS; dữ liệu có thể được giải mã ở proxy/gateway |
| Đang lưu trữ | Lộ ổ đĩa, backup, snapshot, truy cập trái phép vào kho dữ liệu | Mã hóa ổ đĩa/kho lưu trữ; mã hóa cấp ứng dụng bằng AEAD; KMS; IAM | Tiến trình được cấp quyền đọc vẫn có thể lấy bản rõ; khóa đặt cạnh bản mã làm giảm giá trị bảo vệ |
| Trong bộ nhớ | Heap dump, debug trái phép, crash dump, ghi log, rò rỉ qua cache | Hạn chế bản sao và thời gian tồn tại; kiểm soát dump/log/debug; giảm quyền tiến trình | Java và GC không bảo đảm xóa sạch mọi bản sao của dữ liệu ngay lập tức |

**Mã hóa bảo vệ trước một nhóm mối đe dọa cụ thể; không thay thế xác thực, phân quyền, quản lý khóa, kiểm soát truy cập máy chủ hay giám sát.** Hãy hỏi: dữ liệu nào cần bảo vệ, ai có thể truy cập, điểm nào chuyển sang bản rõ, ai giữ khóa và bản sao nào còn tồn tại.

Ví dụ một luồng thực tế:

~~~text
Ứng dụng khách -- HTTPS/TLS --> API Java -- TLS/mTLS --> Cơ sở dữ liệu
                                    |
                               Java heap (bản rõ
                               khi xử lý nghiệp vụ)
                                    |
                              Lưu bản mã xuống DB
                              + backup mã hóa
                              + khóa trong KMS
~~~

Nếu TLS kết thúc tại load balancer, đường từ load balancer tới API là **một kết nối khác** và cần đánh giá bảo vệ riêng. Nếu DB lưu bản mã nhưng API phải đọc dữ liệu, API vẫn có lúc giữ bản rõ trong RAM.

## 2. Bảo vệ dữ liệu khi truyền: TLS và danh tính đầu cuối

### 2.1 TLS cung cấp điều gì?

**TLS (Transport Layer Security)** dùng để bảo vệ kết nối mạng bằng ba thuộc tính quan trọng:

- **Bí mật (confidentiality):** bên nghe lén đường truyền không đọc được nội dung ứng dụng.
- **Toàn vẹn (integrity):** thay đổi trái phép đối với dữ liệu được bảo vệ sẽ bị phát hiện.
- **Xác thực đầu cuối (authentication):** phía khách xác minh máy chủ đang kết nối qua chuỗi chứng chỉ và tên miền; mTLS bổ sung xác thực chứng chỉ phía khách nếu được cấu hình.

Ở mức khái niệm, TLS handshake thương lượng thuật toán, xác thực và thiết lập khóa phiên; sau đó dữ liệu ứng dụng được bảo vệ bằng cơ chế mã hóa có xác thực. Các phiên TLS hiện đại dùng trao đổi khóa tạm thời để đạt **forward secrecy**: rò rỉ khóa riêng của máy chủ về sau không tự động giải mã được toàn bộ lưu lượng cũ đã ghi lại, với điều kiện khóa phiên tạm thời không bị lộ.

Ưu tiên **TLS 1.3** khi các hệ thống hỗ trợ và duy trì **TLS 1.2 cấu hình an toàn** nếu cần tương thích. Không sử dụng SSL cũ, TLS 1.0/1.1 hay bộ mã yếu. Việc “dùng HTTPS” chỉ là điểm khởi đầu; cấu hình chứng chỉ, phiên bản giao thức và điểm kết thúc TLS vẫn quyết định mức an toàn thực tế.

### 2.2 Chứng chỉ, truststore, keystore và hostname verification

- **Certificate (chứng chỉ X.509):** liên kết khóa công khai với danh tính của máy chủ hoặc khách; phải kiểm tra chuỗi tin cậy, thời hạn và danh tính phù hợp.
- **Truststore:** tập CA/chứng chỉ mà chương trình tin để xác minh đối tác. Java thường sử dụng truststore mặc định của JVM nếu ứng dụng không cấu hình riêng.
- **Keystore:** nơi lưu khóa riêng cùng chứng chỉ của bên cần tự chứng minh danh tính; ví dụ máy chủ TLS hoặc client có chứng chỉ mTLS.
- **Hostname verification:** tên miền trong URL phải phù hợp với danh tính trong chứng chỉ (thường ở trường Subject Alternative Name). Chỉ tin CA mà bỏ kiểm tra tên miền là chưa đủ.

**mTLS** yêu cầu cả hai phía dùng chứng chỉ để xác thực ở tầng TLS. Nó hữu ích giữa các dịch vụ, nhưng không tự thay thế kiểm tra quyền nghiệp vụ: một client được TLS xác thực vẫn chỉ được phép thực hiện những thao tác mà danh tính đó được cấp quyền.

Tuyệt đối tránh các mẫu “trust all certificates”, bỏ qua lỗi chứng chỉ hoặc vô hiệu hóa hostname verification để sửa lỗi kết nối. Nếu hệ thống dùng CA nội bộ, nhập CA phù hợp vào truststore và quản lý vòng đời chứng chỉ; không phá bỏ bước xác thực.

### 2.3 Ví dụ Java 17+: HTTPS bằng HttpClient chuẩn

Tệp **TlsClientDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class TlsClientDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac TlsClientDemo.java
java TlsClientDemo
~~~

Ví dụ dùng HTTPS và cơ chế kiểm tra chứng chỉ mặc định của Java. Giá trị HTTP status phụ thuộc phản hồi thực tế của máy chủ; nếu mạng, DNS hoặc xác thực chứng chỉ có vấn đề, lệnh có thể báo lỗi thay vì in trạng thái. Đừng bắt ngoại lệ TLS rồi chuyển sang HTTP thường. Khi cần cấu hình CA riêng hoặc mTLS, cung cấp SSLContext với trust manager/key manager phù hợp, đồng thời duy trì kiểm tra danh tính máy chủ.

**Phạm vi TLS:** TLS không bảo vệ nội dung khỏi chính đầu cuối đã giải mã, admin có quyền truy cập tiến trình, log chứa payload, hoặc chặng mạng phía sau một proxy kết thúc TLS. Vì vậy mọi kết nối giữa API, DB, broker, cache và dịch vụ nội bộ đều phải được xét riêng; dữ liệu cực nhạy cảm có thể cần thêm mã hóa cấp ứng dụng.

## 3. Bảo vệ dữ liệu khi lưu trữ: chọn đúng lớp mã hóa

### 3.1 Các lớp bảo vệ bổ sung cho nhau

- **Mã hóa ổ đĩa/volume hoặc dịch vụ lưu trữ:** bảo vệ khi ổ đĩa, snapshot, thiết bị hay phương tiện sao lưu bị lấy đi; thường trong suốt với ứng dụng. Tuy nhiên tài khoản hoặc tiến trình hợp lệ có quyền đọc dữ liệu sau khi ổ đĩa được mở khóa.
- **Mã hóa ở tầng cơ sở dữ liệu:** ví dụ mã hóa file dữ liệu/log/backup; bảo vệ kho lưu trữ vật lý, song truy vấn bằng tài khoản có quyền vẫn có thể trả bản rõ tùy kiến trúc.
- **Mã hóa cấp ứng dụng/cấp trường:** ứng dụng mã hóa một số giá trị **trước khi** lưu. Cơ sở dữ liệu chỉ giữ bản mã; quyền giải mã và khóa phải được kiểm soát riêng. Cần thiết kế việc tìm kiếm, sắp xếp và lập chỉ mục cho dữ liệu đã mã hóa.
- **Phân quyền, audit và backup:** giới hạn quyền đọc/xuất dữ liệu; mã hóa tất cả bản sao, kiểm tra khôi phục và thiết lập thời gian lưu giữ. Không để log, export CSV hay môi trường kiểm thử trở thành bản sao bản rõ ngoài kiểm soát.

Không phải thông tin nào cũng nên mã hóa thuận nghịch. **Mật khẩu đăng nhập** cần được xử lý bằng hàm băm mật khẩu chậm, có salt riêng cho từng mật khẩu, chẳng hạn Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số phù hợp; không lưu mật khẩu dưới dạng AES có thể giải mã và không dùng SHA-256 đơn thuần để lưu mật khẩu. **Hash** dùng cho mục tiêu kiểm chứng/đối chiếu không đồng nghĩa với **encryption**; Base64 chỉ là mã hóa biểu diễn, không cung cấp bí mật.

### 3.2 AES-GCM: vừa giữ bí mật vừa phát hiện sửa đổi

Với dữ liệu nhạy cảm cần giải mã, ưu tiên thuật toán **AEAD (Authenticated Encryption with Associated Data)** như AES-GCM thay vì tự ghép mã hóa và mã kiểm tra toàn vẹn.

Các thành phần của một bản ghi AES-GCM:

- **Key:** khóa AES bí mật, ví dụ 256 bit, được tạo từ nguồn sinh ngẫu nhiên an toàn và quản lý bằng KMS/secret manager phù hợp.
- **Nonce/IV:** thường dài 12 byte với GCM; **không được trùng khi dùng cùng một khóa**. Nonce không cần bí mật và có thể lưu kèm bản mã. Việc dùng ngẫu nhiên phải có giới hạn lưu lượng/chu kỳ xoay khóa để kiểm soát xác suất va chạm; hệ thống mã hóa số lượng rất lớn cần chiến lược cấp nonce duy nhất rõ ràng.
- **Ciphertext và authentication tag:** dữ liệu đã mã hóa cùng tag (thường 128 bit) cho phép phát hiện sai khóa, sai AAD hoặc sửa đổi bản mã. Trong JCA, Cipher.doFinal() của AES/GCM thường trả phần ciphertext kèm tag.
- **AAD (Additional Authenticated Data):** dữ liệu không cần bí mật nhưng phải gắn chặt với bản mã, ví dụ định danh bản ghi/tenant và phiên bản lược đồ. Bên giải mã phải cung cấp **đúng cùng AAD**. AAD không tự ngăn phát lại bản mã cũ; chống replay cần phiên bản/sequence và kiểm tra nghiệp vụ.
- **Version:** thông tin định dạng và phiên bản khóa (hoặc key ID) để hỗ trợ giải mã và thay đổi khóa về sau; không ghi khóa bí mật vào bản ghi.

**Không tái sử dụng nonce với cùng khóa AES-GCM**; điều đó có thể phá hỏng tính bí mật và toàn vẹn. Không dùng AES/ECB hoặc AES/CBC thiếu cơ chế xác thực cho dữ liệu có khả năng bị đối thủ sửa đổi. Không tự thiết kế thuật toán mã hóa.

### 3.3 Ví dụ Java 17+: mã hóa, giải mã và phát hiện bản mã bị sửa

Đây là chương trình độc lập minh họa một định dạng đơn giản: byte phiên bản + 12 byte nonce + ciphertext có tag. KeyGenerator tạo khóa mới **chỉ cho một lần chạy**; ứng dụng thực tế cần quản lý khóa bền vững và key ID riêng bằng KMS/HSM hoặc secret manager.

Lưu thành **AesGcmDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmDemo {
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(byte[] plaintext, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce); // Mới cho mỗi lần mã hóa cùng khóa.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(1 + NONCE_BYTES + ciphertextAndTag.length)
                .put(VERSION)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    static byte[] decrypt(byte[] payload, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        if (payload.length < 1 + NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Payload khong hop le");
        }

        ByteBuffer input = ByteBuffer.wrap(payload);
        if (input.get() != VERSION) {
            throw new IllegalArgumentException("Version khong ho tro");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] aad = "record:42".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Dữ liệu nhạy cảm"
                .getBytes(StandardCharsets.UTF_8);
        byte[] packed = encrypt(plaintext, key, aad);
        byte[] restored = decrypt(packed, key, aad);

        try {
            System.out.println("Khôi phục đúng: "
                    + Arrays.equals(plaintext, restored));

            packed[packed.length - 1] ^= 1; // Giả lập sửa một byte của tag.
            try {
                decrypt(packed, key, aad);
                System.out.println("Không phát hiện chỉnh sửa");
            } catch (AEADBadTagException expected) {
                System.out.println("Phát hiện chỉnh sửa: true");
            }
        } finally {
            Arrays.fill(plaintext, (byte) 0);
            Arrays.fill(restored, (byte) 0);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 AesGcmDemo.java
java AesGcmDemo
~~~

Kết quả khi chạy với provider JCA AES-GCM thông dụng của JDK:

~~~text
Khôi phục đúng: true
Phát hiện chỉnh sửa: true
~~~

Diễn giải: dữ liệu mã hóa được khôi phục với khóa và AAD ban đầu. Khi sửa một byte tag, phép giải mã ném AEADBadTagException trước khi trả bản rõ. Trường hợp cung cấp sai AAD hoặc sai khóa cũng làm xác thực thất bại. Tag phát hiện chỉnh sửa **không chứng minh ai đã tạo bản mã** nếu nhiều chủ thể cùng giữ khóa và không tự chống replay.

**Giới hạn của ví dụ:** khóa chỉ sống trong RAM nên không thể giải mã dữ liệu từ lần chạy khác; việc dùng nonce ngẫu nhiên cần đánh giá quy mô trước khi đưa vào sản xuất; chương trình chưa giải quyết lưu trữ an toàn, xoay khóa, kiểm soát quyền, chống replay, xử lý lỗi và tránh bản sao dữ liệu trong bộ nhớ. Không in khóa, plaintext hay byte[] nhạy cảm ra console/log. Khi lưu bản ghi thật, quản lý version, key ID, thuật toán, nonce và ciphertext/tag theo định dạng được kiểm chứng và quy trình vận hành rõ ràng.

### 3.4 Quản lý khóa quan trọng không kém thuật toán

Một thiết kế thường dùng là **envelope encryption**:

1. KMS/HSM quản lý khóa gốc/khóa mã hóa khóa (KEK) theo quyền riêng.
2. Ứng dụng tạo hoặc yêu cầu **data encryption key (DEK)** để mã hóa dữ liệu.
3. Lưu ciphertext dữ liệu cùng DEK đã được bọc/mã hóa bằng KEK, key ID, nonce và metadata cần thiết; không lưu DEK bản rõ cạnh dữ liệu.
4. Khi cần đọc, thành phần có quyền yêu cầu KMS mở bọc DEK, giải mã trong thời gian tối thiểu rồi giải phóng bản sao kiểm soát được.

Áp dụng least privilege cho quyền sử dụng khóa; tách quyền đọc DB khỏi quyền giải mã nếu mô hình cho phép; quản lý audit, quota và thu hồi. **Rotation** cần tính cả dữ liệu cũ: đổi KEK, bọc lại DEK hoặc mã hóa lại dữ liệu theo kế hoạch. Phân biệt mất khóa (mất khả năng khôi phục dữ liệu) với lộ khóa (nguy cơ lộ dữ liệu). Backup khóa phải được bảo vệ và có quy trình phục hồi kiểm chứng.

Không hardcode khóa vào Java source, application.yml, Git, Docker image, biến môi trường được dump/log, URL hoặc file cấu hình phân phối rộng. Biến môi trường/secret injection có thể là kênh cấp phát, nhưng ứng dụng vẫn cần kiểm soát ai có quyền xem process configuration, dump và log.

## 4. Bảo vệ dữ liệu khi đang ở trong bộ nhớ JVM

Mã hóa đường truyền và ổ đĩa **không làm cho bản rõ tự biến mất trong bộ nhớ**: để xử lý nghiệp vụ, JVM thường phải có thời điểm nhìn thấy bản rõ hoặc giữ tham chiếu tới đối tượng chứa dữ liệu đó.

### 4.1 Những nơi dữ liệu có thể tồn tại

- **Java heap:** String, char[], byte[], DTO, collections, exception message, cache và object graph.
- **Bộ nhớ native/off-heap:** direct ByteBuffer, thư viện JNI/native, TLS provider, driver và các buffer I/O.
- **Bản sao ngoài ý muốn:** chuyển byte[] sang String, nối chuỗi, serialize JSON, tracing, log request/response, bộ nhớ của profiler.
- **Hiện vật chẩn đoán:** heap dump, core dump, crash dump, debugger/JMX/JFR hoặc bản sao do sự cố và công cụ vận hành tạo ra.

GC thu hồi đối tượng không đồng nghĩa với việc xóa mọi byte dữ liệu cũ trên RAM đúng thời điểm. **String là bất biến** nên ứng dụng không thể xóa nội dung String theo cách đáng tin; ngay cả khi xóa một mảng byte[]/char[] mà mình sở hữu, JVM, thư viện hoặc OS vẫn có thể giữ các bản sao khác. Bảo đảm zeroization tuyệt đối không phải là tính chất mặc định của Java.

### 4.2 Biện pháp thực tế

1. **Giảm dữ liệu và thời gian giữ bản rõ:** chỉ giải mã đúng trường cần xử lý, không giữ payload dài hạn trong session/cache và giải phóng tham chiếu khi xong. Không đọc toàn bộ hồ sơ nhạy cảm nếu nghiệp vụ chỉ cần một trường.
2. **Dùng vùng dữ liệu có thể xóa khi API cho phép:** với mật khẩu nhận từ terminal, Console.readPassword() trả char[]. Bọc sử dụng trong try/finally và gọi Arrays.fill(password, '\0') ở finally; không chuyển sang String không cần thiết. Với byte[] bản rõ do ứng dụng kiểm soát, dùng Arrays.fill(bytes, (byte) 0) sau sử dụng. Đây là giảm rủi ro, không phải cam kết xóa toàn bộ bản sao.
3. **Giảm số lần sao chép/serialize:** tránh toString() trên secret object, logging DTO, dump stack chứa tham số nhạy cảm; chỉ log mã định danh đã che hoặc metadata phi nhạy cảm.
4. **Bảo vệ công cụ vận hành:** hạn chế quyền attach debugger, JMX, heap dump, core dump; kiểm soát file dump và nơi lưu artifact CI/CD, support ticket, object storage. Với cờ tạo heap dump khi OOM, phải có quy trình bảo vệ/xóa dump vì nó có thể chứa plaintext và khóa.
5. **Hạn chế quyền runtime:** tài khoản OS/service riêng, container/host isolation, quyền truy cập secret và KMS tối thiểu, cập nhật thư viện/JDK và kiểm soát người có quyền truy cập môi trường.
6. **Thu hẹp quyền dùng khóa:** khóa có thể nằm trong RAM của ứng dụng khi cần mã hóa, nhưng HSM/KMS có thể giữ khóa gốc ngoài tiến trình; tránh lưu bản sao khóa bền vững trong singleton/cache khi không cần.

Ví dụ luồng nhập mật khẩu trong Java nên ưu tiên phương thức trả char[] như Console.readPassword(); luôn kiểm tra trường hợp không có console trong IDE hoặc khi chạy dưới service. Không dùng Arrays.fill cho một mảng sau khi đã để lộ nội dung qua String/log mà kỳ vọng các bản sao kia tự biến mất.

**Không có “bật một flag là mã hóa toàn bộ heap an toàn”.** Nếu đối thủ có quyền điều khiển tiến trình, attach debugger hoặc đọc bộ nhớ của service, phần lớn dữ liệu ứng dụng cần xử lý đều có nguy cơ bị lộ. Hãy xác định và giảm quyền truy cập đó theo mô hình đe dọa thực tế.

## 5. Ghép ba lớp bảo vệ trong kiến trúc Java

Giả sử một API Java nhận thông tin khách hàng, lưu trong DB và trả kết quả cho dịch vụ khác:

| Bước | Thiết kế đề xuất | Điều cần xác minh |
| --- | --- | --- |
| Client gọi API | HTTPS/TLS, xác thực user và kiểm tra quyền ở API | Chứng chỉ/tên miền hợp lệ; không có HTTP fallback; dữ liệu nhạy cảm không nằm trên URL |
| Gateway gọi ứng dụng | TLS riêng cho chặng gateway → service; mTLS nếu thích hợp | Điểm kết thúc TLS và danh tính hai phía |
| Service gọi DB/broker | TLS cho từng kết nối; tài khoản riêng, quyền tối thiểu | Không mặc nhiên tin mạng nội bộ; chứng chỉ và quyền truy cập đúng |
| Service lưu trường nhạy cảm | AES-GCM/AEAD cấp ứng dụng khi mô hình đe dọa yêu cầu; mã hóa disk, backup, snapshot | Nonce duy nhất theo khóa; AAD gắn đúng ngữ cảnh; không lộ key/DEK |
| Service dùng bản rõ | Giải mã sát nơi dùng, hạn chế cache và bản sao, che log/trace | Không để plaintext/khóa trong exception, heap dump, báo cáo lỗi |
| Vận hành và khôi phục | KMS/IAM/audit, rotation, backup/restore và xử lý sự cố | Có thể khôi phục dữ liệu hợp lệ, thu hồi quyền và phát hiện truy cập bất thường |

**Defense in depth:** TLS bảo vệ đường truyền; mã hóa at-rest bảo vệ bản sao lưu trữ; quản lý bộ nhớ và quyền runtime giảm khả năng lộ khi xử lý. Ba lớp phối hợp với xác thực, phân quyền, quản lý khóa và quy trình vận hành. Không một lớp nào tự bao phủ các lớp còn lại.

## 6. Những nhầm lẫn và lỗi phổ biến

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “Có HTTPS thì dữ liệu an toàn ở mọi nơi.” | HTTPS bảo vệ các kết nối TLS được cấu hình; plaintext vẫn có thể ở đầu cuối, gateway, DB, cache và log. |
| “DB đã mã hóa ổ đĩa, nhân viên có quyền SQL cũng không đọc được dữ liệu.” | Mã hóa ổ đĩa thường trong suốt sau khi mở khóa; vẫn cần phân quyền và có thể cần mã hóa cấp trường. |
| “Dùng AES là đủ, không cần integrity.” | AES-GCM với tag/AAD cung cấp mã hóa có xác thực; AES/ECB và CBC không xác thực dễ bị lạm dụng. |
| “GCM nonce giống salt, tái sử dụng cũng được.” | Nonce **phải duy nhất theo từng khóa**; tái sử dụng với GCM có thể gây hậu quả nghiêm trọng. |
| “Base64 hoặc SHA-256 là mã hóa dữ liệu bí mật.” | Base64 chỉ đổi cách biểu diễn; hash không phải mã hóa thuận nghịch; mật khẩu cần password hashing chuyên dụng. |
| “Xóa char[] là chắc chắn không còn mật khẩu trong RAM.” | Chỉ xóa mảng đang quản lý; có thể còn bản sao trong JVM/native/OS. |
| “mTLS tự quyết định service nào được xem hồ sơ.” | mTLS xác thực danh tính kết nối; nghiệp vụ vẫn phải phân quyền từng tài nguyên/hành động. |
| “Khóa và bản mã nằm cùng DB vẫn bảo vệ tốt trước lộ DB.” | Nếu cùng quyền truy cập đọc được cả khóa lẫn dữ liệu, kẻ tấn công có thể giải mã; cần tách quyền quản lý khóa. |

## 7. Tự kiểm tra bằng tình huống

**Tình huống A:** API chạy HTTPS, DB kết nối không TLS trong cùng VPC, còn backup được xuất ra object storage. Hãy chỉ ra ba ranh giới cần đánh giá: đường API → DB, quyền đọc backup và trạng thái dữ liệu trong RAM của API. Bổ sung TLS cho chặng DB, mã hóa và phân quyền backup, rà soát log/dump và quyền tiến trình; HTTPS phía client chưa bao phủ các điểm này.

**Tình huống B:** một cột đã mã hóa bằng AES-GCM nhưng mỗi bản ghi dùng lại cùng IV cố định. Đây là lỗi thiết kế nghiêm trọng vì tái sử dụng nonce với cùng key. Phải thiết kế cơ chế tạo nonce duy nhất, quản lý key/rotation, đánh giá dữ liệu đã bị ảnh hưởng và mã hóa lại an toàn; không chỉ đổi tên biến hoặc thêm Base64.

**Tình huống C:** ứng dụng che mật khẩu trong giao diện nhưng ghi toàn bộ request body và lưu heap dump sau OOM. Dữ liệu vẫn có nguy cơ rò rỉ qua log/dump. Hãy bỏ secret khỏi log, giới hạn dữ liệu tồn tại trong JVM, bảo vệ/khoanh vùng artifact chẩn đoán và kiểm tra quyền truy cập.

**Bộ câu hỏi tự đánh giá:**

1. TLS bảo vệ đoạn nào của một kiến trúc có reverse proxy? → Từng đoạn kết nối TLS, theo vị trí điểm kết thúc.
2. Có thể lưu nonce AES-GCM cạnh ciphertext không? → Có; nonce không phải bí mật, nhưng bắt buộc duy nhất theo khóa.
3. Sai AAD ảnh hưởng gì khi giải mã bằng AES-GCM? → Xác thực tag thất bại, không được sử dụng bản rõ.
4. Tại sao mã hóa ổ đĩa chưa đủ cho một DB có nhiều tài khoản ứng dụng? → Tài khoản đã được cho phép truy vấn có thể đọc bản rõ; cần quyền chi tiết và đôi khi mã hóa cấp trường.
5. Vì sao Arrays.fill() là biện pháp giảm rủi ro chứ không phải bảo đảm tuyệt đối? → Nó chỉ ghi đè mảng được tham chiếu; bản sao do JVM/thư viện/OS tạo có thể còn tồn tại.

**Nguyên tắc mang đi:** xác định rõ dữ liệu ở đâu, ai có thể đọc, nó được giải mã tại điểm nào và khóa được bảo vệ thế nào. Dùng TLS cho từng chặng truyền, AEAD cùng quản lý khóa tốt cho dữ liệu cần mã hóa khi lưu, và giảm tối đa bản rõ cùng dấu vết nhạy cảm trong bộ nhớ, log và công cụ chẩn đoán.
