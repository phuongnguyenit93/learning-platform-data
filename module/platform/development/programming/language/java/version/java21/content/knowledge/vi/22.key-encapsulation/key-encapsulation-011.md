# Phân biệt API KEM với khả năng kháng lượng tử của thuật toán được chọn

Java 21 chuẩn hóa API Key Encapsulation Mechanism (KEM) qua JEP 452. API này cung cấp một giao diện thống nhất để một bên tạo shared secret cùng dữ liệu encapsulation, còn bên kia dùng private key tương ứng để khôi phục shared secret. Tuy nhiên, việc sử dụng `javax.crypto.KEM` không tự làm cho kết nối có khả năng kháng lượng tử.

Khả năng kháng lượng tử phụ thuộc vào thuật toán KEM cụ thể, bộ tham số, cách triển khai của security provider và giao thức sử dụng kết quả KEM. Ví dụ, DHKEM dựa trên Diffie–Hellman cổ điển như X25519 không có khả năng kháng máy tính lượng tử đủ mạnh; ML-KEM được chuẩn hóa trong FIPS 203 mới được thiết kế cho mục tiêu kháng lượng tử. API Java chỉ là lớp trừu tượng để gọi thuật toán mà provider cung cấp.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần hiểu riêng ba lớp: API KEM của Java, thuật toán KEM được chọn và giao thức bảo vệ dữ liệu sử dụng shared secret. Không suy luận mức an toàn hậu lượng tử chỉ từ việc chương trình biên dịch hoặc chạy thành công với `KEM`.

## KEM làm nhiệm vụ gì?

Key Encapsulation Mechanism là cơ chế thiết lập một bí mật chung thông qua khóa công khai. Người gửi sử dụng public key của người nhận để tạo:

- Một shared secret chỉ người có private key tương ứng mới có thể khôi phục theo thuật toán KEM.
- Một chuỗi dữ liệu encapsulation được gửi tới người nhận.

Người nhận dùng private key và dữ liệu encapsulation để decapsulate, thu được shared secret tương ứng. Hai bên sau đó có thể dùng secret này làm đầu vào cho một KDF để dẫn xuất khóa mã hóa đối xứng.

```text
Người gửi                                      Người nhận
   |                                               |
   | <---------- Public key đã xác thực ---------- |
   |                                               |
   | Encapsulate(public key)                       |
   |       |                                       |
   |       +--> Shared secret                      |
   |       +--> Encapsulation -------------------->|
   |                                               | Decapsulate(private key,
   |                                               |             encapsulation)
   |                                               +--> Shared secret
   |                                               |
   +------ Hai bên dẫn xuất khóa từ secret --------+
                          |
                          v
                   KDF + AEAD
```

KEM không phải là thuật toán mã hóa dữ liệu ứng dụng. Nó không tự mã hóa một file hay HTTP body, cũng không tự xác thực danh tính người gửi. Trong một hệ thống hoàn chỉnh, KEM thường là một bước trong quy trình thiết lập khóa; KDF và AEAD đảm nhiệm dẫn xuất khóa và bảo vệ dữ liệu.

## API KEM trong Java 21 cung cấp điều gì?

API `javax.crypto.KEM` được đưa vào Java 21 để ứng dụng có thể làm việc với nhiều cơ chế encapsulation thông qua một mô hình chung. Các thành phần chính gồm:

| Thành phần | Vai trò |
| --- | --- |
| `KEM.getInstance(algorithm)` | Lấy implementation KEM theo tên thuật toán từ security provider |
| `KEM.newEncapsulator(publicKey)` | Tạo đối tượng dùng public key để encapsulate |
| `KEM.Encapsulator.encapsulate()` | Sinh dữ liệu encapsulation và shared secret phía người gửi |
| `KEM.Encapsulated` | Mang `SecretKey`, dữ liệu encapsulation và tham số liên quan |
| `KEM.newDecapsulator(privateKey)` | Tạo đối tượng dùng private key để decapsulate |
| `KEM.Decapsulator.decapsulate(encapsulation)` | Khôi phục shared secret phía người nhận |

`KEM` là API provider-based. Java định nghĩa hợp đồng gọi, còn provider cung cấp implementation của thuật toán. `KEM.getInstance("...")` chỉ thành công nếu một provider đã đăng ký service có tên tương ứng. Vì vậy, tên thuật toán có thể biên dịch trong mã nguồn nhưng không nhất thiết có sẵn trên mọi runtime hoặc mọi provider.

Có thể kiểm tra implementation thực tế sau khi lấy instance:

```java
KEM kem = KEM.getInstance("DHKEM");

System.out.println("Algorithm: " + kem.getAlgorithm());
System.out.println("Provider: " + kem.getProvider().getName());
```

Việc ghi nhận tên provider và phiên bản provider trong triển khai giúp kiểm soát thay đổi khi nâng cấp JDK hoặc cài đặt provider mới. Nếu chính sách bảo mật yêu cầu một provider cụ thể, hãy chọn provider theo cấu hình đã được kiểm duyệt thay vì phụ thuộc ngầm vào thứ tự provider toàn cục.

## Ví dụ KEM cổ điển với DHKEM và X25519

Ví dụ sau minh họa luồng encapsulate/decapsulate trên một provider có hỗ trợ thuật toán `DHKEM` với khóa X25519:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class DhKemExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");

        // Phía gửi: dùng public key của người nhận.
        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(recipientKeys.getPublic())
                .encapsulate();

        SecretKey senderSecret = encapsulated.key();
        byte[] encapsulation = encapsulated.encapsulation();

        // Gửi encapsulation tới người nhận qua giao thức đã xác thực.

        // Phía nhận: dùng private key tương ứng để khôi phục secret.
        SecretKey recipientSecret = kem
                .newDecapsulator(recipientKeys.getPrivate())
                .decapsulate(encapsulation);

        // Hai SecretKey đại diện cho shared secret tương ứng.
        // Không ghi secret hoặc private key vào log.
        System.out.println("Encapsulation bytes: " + encapsulation.length);
        System.out.println("KEM provider: " + kem.getProvider().getName());
    }
}
```

Ví dụ yêu cầu runtime/provider hỗ trợ cả `DHKEM` và loại khóa X25519 tương ứng; nếu không, thao tác lấy instance hoặc tạo encapsulator sẽ thất bại. Tên service và tập khóa hỗ trợ phải được xác nhận trên provider thực tế.

`DHKEM` dựa trên Diffie–Hellman. Khi dùng với X25519, độ an toàn dựa trên bài toán logarithm rời rạc trên đường cong elliptic, là nền tảng mật mã khóa công khai cổ điển. Một máy tính lượng tử đủ lớn chạy thuật toán Shor có thể phá vỡ giả định này. Vì vậy, ví dụ trên minh họa API KEM của Java, nhưng không phải ví dụ về KEM kháng lượng tử.

`senderSecret` và `recipientSecret` là các đối tượng `SecretKey`; không nên in nội dung khóa ra console hoặc log. Trong hệ thống thực tế, cần dùng KDF được giao thức quy định để dẫn xuất khóa AEAD, quản lý nonce và associated data đúng cách. Không tự thiết kế cách ghép secret thành khóa mã hóa nếu giao thức đã định nghĩa quy trình dẫn xuất.

## API KEM không quyết định thuật toán có kháng lượng tử hay không

API KEM mô tả cách gọi, không áp đặt một thuật toán duy nhất. Cùng một chuỗi thao tác `newEncapsulator()`, `encapsulate()` và `decapsulate()` có thể được provider thực hiện bằng các họ thuật toán có giả định an toàn rất khác nhau.

| Thuật toán/họ thuật toán | Nền tảng mật mã | Kháng lượng tử? | Ghi chú |
| --- | --- | --- | --- |
| DHKEM với X25519 hoặc đường cong elliptic cổ điển | Diffie–Hellman trên nhóm elliptic | Không | Phù hợp với mô hình an toàn cổ điển, không phải post-quantum KEM |
| DHKEM với nhóm Diffie–Hellman cổ điển khác | Bài toán logarithm rời rạc hoặc biến thể cổ điển | Không | Đổi nhóm hoặc tăng kích thước khóa cổ điển không biến nó thành PQC |
| ML-KEM-512 | Module-lattice, chuẩn FIPS 203 | Có, được thiết kế cho mục tiêu hậu lượng tử | Mức tham số thấp nhất trong ba bộ ML-KEM chuẩn hóa |
| ML-KEM-768 | Module-lattice, chuẩn FIPS 203 | Có, được thiết kế cho mục tiêu hậu lượng tử | Thường được cân nhắc cho mức bảo vệ cân bằng; phải theo chính sách và đánh giá triển khai |
| ML-KEM-1024 | Module-lattice, chuẩn FIPS 203 | Có, được thiết kế cho mục tiêu hậu lượng tử | Bộ tham số lớn hơn; có chi phí và kích thước dữ liệu khác |

ML-KEM là tên chuẩn hóa của thuật toán trước đây được biết đến rộng rãi qua họ CRYSTALS-Kyber. FIPS 203 xác định ba bộ tham số ML-KEM-512, ML-KEM-768 và ML-KEM-1024. Khả năng kháng lượng tử đến từ cấu trúc toán học và phân tích an toàn của thuật toán cùng bộ tham số, không đến từ interface Java.

Không nên gọi một thuật toán là “quantum-safe tuyệt đối”. Các thuật toán hậu lượng tử được thiết kế để chống lại những tấn công đã biết, bao gồm mô hình đối thủ có máy tính lượng tử đủ năng lực; việc đánh giá vẫn phụ thuộc vào nghiên cứu mật mã, triển khai, tham số và các cập nhật tiêu chuẩn.

## ML-KEM có sẵn trong Java 21 hay không?

Java 21 cung cấp API KEM qua JEP 452, nhưng việc có API không đồng nghĩa mọi thuật toán KEM đã được triển khai trong mọi JDK 21 provider. ML-KEM được chuẩn hóa trong FIPS 203 sau khi Java 21 phát hành. Do đó, không thể giả định một bản cài đặt Java 21 bất kỳ đã có service ML-KEM trong provider mặc định.

Nếu ứng dụng cần ML-KEM trên nền Java 21, phải kiểm tra provider đã cài đặt và cấu hình có đăng ký implementation tương ứng hay không. Provider có thể dùng tên service hoặc cách cấu hình bộ tham số theo tài liệu riêng. Ví dụ về cách lấy instance dưới đây chỉ thành công khi provider thực tế đã đăng ký tên được yêu cầu:

```java
import javax.crypto.KEM;

// Chỉ hoạt động nếu provider đã cài đặt đăng ký service tên ML-KEM.
KEM kem = KEM.getInstance("ML-KEM");
System.out.println(kem.getProvider().getName());
```

Đoạn mã trên minh họa việc tra cứu service; nó không chứng minh ML-KEM có sẵn trong mọi JDK 21. Một số provider có thể yêu cầu chỉ định tham số ML-KEM-768 hoặc chọn biến thể theo tên/parameter spec riêng. Hãy dùng đúng tài liệu của provider, kiểm tra khả năng tương thích với Java 21 và thử nghiệm interoperability trước khi triển khai.

Không tự thay `"DHKEM"` thành `"ML-KEM"` rồi cho rằng hệ thống đã chuyển sang hậu lượng tử. Cần xác minh thuật toán được provider thực thi, bộ tham số, định dạng public key, private key, encapsulation và khả năng hai đầu giao tiếp tương thích.

## Bộ tham số quan trọng như thế nào?

Ngay cả khi hai implementation đều gọi là ML-KEM, ứng dụng vẫn cần thống nhất bộ tham số. FIPS 203 định nghĩa ba lựa chọn:

| Bộ tham số | Mức phân loại an toàn NIST tương ứng | Cân nhắc |
| --- | --- | --- |
| ML-KEM-512 | Category 1 | Kích thước và chi phí thấp hơn; chỉ chọn khi chính sách và phân tích rủi ro cho phép |
| ML-KEM-768 | Category 3 | Mức cân bằng thường được đánh giá cho nhiều hệ thống tổng quát |
| ML-KEM-1024 | Category 5 | Mức phân loại cao hơn, đi kèm dữ liệu và chi phí tính toán lớn hơn |

Category là phân loại mức an toàn theo tiêu chí của NIST, không phải số bit khóa đối xứng. Không thể so sánh trực tiếp con số 768 với khóa AES-768 hay suy ra kích thước ciphertext từ tên bộ tham số. Hãy kiểm tra bảng kích thước và yêu cầu của FIPS 203 cùng tài liệu provider.

Hai đầu giao tiếp phải thống nhất thuật toán, bộ tham số, encoding và cách dẫn xuất khóa. Nếu một bên dùng ML-KEM-768 còn bên kia dùng ML-KEM-1024, chúng không thể tự động decapsulate dữ liệu của nhau chỉ vì đều gọi API `KEM`.

## KEM không thay thế xác thực và giao thức bảo mật

KEM giải quyết việc tạo shared secret, nhưng tự nó không xác minh public key thuộc về đúng người nhận. Nếu kẻ tấn công thay public key trên đường truyền bằng khóa của họ, người gửi có thể encapsulate với khóa giả và thiết lập secret với kẻ tấn công.

Vì vậy, public key dùng cho KEM phải được xác thực bằng một cơ chế phù hợp, chẳng hạn chứng thư số, chữ ký số, pinning hoặc một giao thức đã xác định danh tính peer. Cần xem xét cả thuật toán chữ ký: nếu hệ thống cần khả năng kháng lượng tử đầu cuối, việc chỉ thay KEM nhưng vẫn dùng chữ ký cổ điển có thể để lại điểm yếu hậu lượng tử.

Sau khi có shared secret, giao thức thường cần:

1. Dẫn xuất khóa bằng KDF có thiết kế phù hợp, gắn context và transcript cần thiết.
2. Dùng AEAD như AES-GCM hoặc ChaCha20-Poly1305 để bảo vệ dữ liệu, với nonce duy nhất theo yêu cầu của thuật toán.
3. Xác thực danh tính và ràng buộc public key, tham số, phiên bản giao thức vào quá trình handshake.
4. Xử lý lỗi decapsulation, replay, downgrade và thay đổi tham số một cách nhất quán.
5. Quản lý vòng đời private key, backup, rotation, quyền truy cập và xóa khóa an toàn.

Không tự ghép KEM, KDF và AEAD thành giao thức mới nếu chưa có chuyên môn mật mã và đánh giá độc lập. Ưu tiên giao thức chuẩn hóa, thư viện được kiểm toán và cấu hình được tổ chức phê duyệt.

## Hybrid KEM trong giai đoạn chuyển đổi

Một số hệ thống có thể cần kết hợp cơ chế cổ điển và hậu lượng tử trong giai đoạn chuyển đổi để bảo vệ trước rủi ro triển khai mới hoặc tương thích với peer cũ. Đây thường được gọi là hybrid key establishment.

Việc kết hợp không nên được thực hiện bằng cách nối hai shared secret theo một quy tắc tự nghĩ ra. Giao thức phải định nghĩa rõ cách kết hợp secret, domain separation, transcript binding, định dạng thông điệp và cách thương lượng thuật toán. Nếu một giao thức chuẩn hóa hỗ trợ hybrid KEM hoặc hybrid key exchange, hãy tuân thủ đúng đặc tả và profile triển khai của nó.

Java `KEM` API cung cấp primitive để gọi KEM; nó không tự định nghĩa chính sách hybrid, thương lượng thuật toán, xác thực peer hay wire protocol. Những phần này thuộc về giao thức và thư viện cấp cao hơn.

## Cách kiểm tra thuật toán đang thực sự được sử dụng

Trong triển khai, cần kiểm tra không chỉ mã nguồn mà cả cấu hình runtime:

- Ghi nhận `kem.getAlgorithm()` và `kem.getProvider()` sau khi tạo instance.
- Kiểm tra provider version, nguồn phân phối và chính sách cập nhật bảo mật.
- Xác nhận bộ tham số thực tế được chọn, không dựa vào tên lớp hoặc giả định mặc định.
- Kiểm tra thuật toán được hỗ trợ trên cả phía encapsulation và decapsulation.
- Thử nghiệm interoperability với implementation độc lập hoặc peer thực tế.
- Kiểm tra kích thước key/encapsulation, hiệu năng, lỗi input không hợp lệ và xử lý side-channel theo tài liệu provider.
- Đảm bảo private key và shared secret không xuất hiện trong log, exception message hoặc telemetry.

Việc gọi thành công `KEM.getInstance()` chỉ xác nhận provider có một service với tên đó. Nó không chứng minh thuật toán đạt mức bảo vệ hậu lượng tử, được cấu hình đúng hoặc phù hợp với chính sách mật mã của hệ thống.

## Quy trình chọn KEM cho ứng dụng Java 21

1. **Xác định mục tiêu an toàn.** Hệ thống chỉ cần bảo vệ theo giả định cổ điển hay phải chống lại đối thủ có năng lực lượng tử trong vòng đời dữ liệu?
2. **Chọn thuật toán và bộ tham số.** Phân biệt DHKEM cổ điển với ML-KEM theo FIPS 203; chọn bộ tham số theo chính sách an toàn và hiệu năng.
3. **Kiểm tra provider.** Xác nhận provider triển khai thuật toán, tên service, tham số, key format và tương thích Java 21.
4. **Dùng API KEM đúng vai trò.** Public key để encapsulate; private key tương ứng để decapsulate; chuyển encapsulation qua giao thức đã xác thực.
5. **Xác thực public key và peer.** Không để KEM trở thành điểm trao khóa không xác thực.
6. **Dùng giao thức hoàn chỉnh.** Dẫn xuất khóa bằng KDF và bảo vệ payload bằng AEAD; ưu tiên chuẩn/giao thức đã được đánh giá.
7. **Kiểm thử interoperability và vận hành.** Đo kích thước dữ liệu, độ trễ, lỗi decapsulation, khả năng rotation và tương thích giữa các provider.
8. **Ghi nhận cấu hình mật mã.** Lưu thuật toán, bộ tham số, provider và phiên bản để có thể kiểm toán và nâng cấp có kiểm soát.

API KEM của Java 21 giúp ứng dụng gọi các cơ chế encapsulation theo một giao diện thống nhất. Khả năng kháng lượng tử lại do thuật toán và bộ tham số được provider thực thi quyết định. DHKEM với X25519 vẫn là cơ chế cổ điển; ML-KEM theo FIPS 203 được thiết kế cho môi trường hậu lượng tử nhưng phải được cung cấp và cấu hình thực sự. Hãy đánh giá cả xác thực, KDF, AEAD và giao thức bao quanh trước khi kết luận một hệ thống đã sẵn sàng cho mật mã hậu lượng tử.
