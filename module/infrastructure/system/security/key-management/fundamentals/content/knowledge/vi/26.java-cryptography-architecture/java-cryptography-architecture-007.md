# Mac

Trong Java Cryptography Architecture (JCA), **Mac** là lớp API dùng để tạo và xác minh mã xác thực thông điệp (Message Authentication Code). MAC là một giá trị được tính từ thông điệp và khóa bí mật dùng chung. Bên nhận có cùng khóa có thể tính lại giá trị đó để kiểm tra thông điệp có bị thay đổi hay không và có được tạo bởi một bên biết khóa hay không.

Với hệ sinh thái Java, lớp **javax.crypto.Mac** cung cấp giao diện thống nhất cho nhiều thuật toán MAC. Ứng dụng có thể yêu cầu thuật toán như **HmacSHA256**, còn provider được chọn sẽ cung cấp phần triển khai mật mã thực tế. Điều này kết nối trực tiếp API JCA với quản lý khóa: khóa MAC phải được sinh an toàn, lưu trữ có kiểm soát, cấp cho đúng thành phần, xoay vòng và thu hồi khi cần.

## 1. MAC giải quyết vấn đề gì?

Khi gửi dữ liệu qua mạng hoặc lưu dữ liệu ở nơi không hoàn toàn tin cậy, ứng dụng cần biết dữ liệu có còn nguyên vẹn và có đến từ một bên được cấp khóa hay không. MAC cung cấp cơ chế xác thực dựa trên bí mật dùng chung.

Giả sử dịch vụ A và dịch vụ B cùng sở hữu khóa bí mật K. A tính:

\[
T = MAC(K, M)
\]

Trong đó M là thông điệp và T là thẻ xác thực (authentication tag). A gửi M cùng T cho B. B dùng K để tính lại thẻ từ M nhận được, rồi so sánh với T. Nếu hai giá trị khớp, B có bằng chứng mật mã rằng thông điệp không bị thay đổi kể từ khi được tạo bởi một bên có K.

MAC cung cấp hai thuộc tính chính:

- **Toàn vẹn (integrity):** phát hiện thông điệp bị sửa đổi.
- **Xác thực nguồn ở mức sở hữu khóa (message authentication):** xác nhận thông điệp được tạo bởi một bên có khóa bí mật tương ứng.

MAC không mã hóa nội dung. Người quan sát vẫn có thể đọc thông điệp nếu ứng dụng không dùng thêm cơ chế mã hóa. MAC cũng không tự ngăn việc phát lại một thông điệp hợp lệ. Nếu giao thức cần chống replay, phải bổ sung nonce, số thứ tự, timestamp hoặc trạng thái chống phát lại và đưa dữ liệu đó vào phần được xác thực.

## 2. MAC, hash, chữ ký số và AEAD khác nhau thế nào?

Các cơ chế này đều có thể liên quan đến tính toàn vẹn, nhưng mô hình tin cậy khác nhau.

| Cơ chế | Có dùng khóa bí mật? | Ai có thể tạo giá trị xác thực? | Đặc điểm |
|---|---|---|---|
| Hàm băm mật mã (hash) | Không | Bất kỳ ai có dữ liệu | Tạo dấu vân tay dữ liệu; tự nó không xác thực người gửi |
| MAC, ví dụ HMAC | Có, khóa đối xứng dùng chung | Bất kỳ bên nào có khóa | Xác thực thông điệp giữa các bên cùng tin cậy một khóa |
| Chữ ký số | Có cặp khóa riêng/công khai | Bên giữ khóa riêng | Bên nhận dùng khóa công khai xác minh; phù hợp khi cần xác minh độc lập |
| AEAD, ví dụ AES-GCM | Có khóa bí mật | Bên có khóa | Mã hóa và xác thực dữ liệu trong cùng một cơ chế |

Với MAC, cả bên gửi và bên nhận đều có thể tạo thẻ hợp lệ vì cùng giữ bí mật. Do đó, MAC không cung cấp tính chống chối bỏ như chữ ký số: bên nhận không thể chứng minh với bên thứ ba rằng chỉ bên gửi mới có thể tạo thông điệp.

Không nên nhầm HMAC với SHA-256 thông thường. SHA-256 chỉ băm dữ liệu, còn HMAC-SHA-256 kết hợp SHA-256 với khóa bí mật theo cấu trúc HMAC. Kẻ tấn công có thể tự tính SHA-256 của dữ liệu đã sửa, nhưng không thể tạo HMAC hợp lệ nếu không biết khóa.

Khi cần mã hóa dữ liệu đồng thời xác thực dữ liệu và một số metadata, nên ưu tiên một chế độ AEAD đã được thiết kế cho mục đích đó, chẳng hạn AES-GCM. Không tự ghép MAC và mã hóa theo thứ tự tùy ý; thiết kế sai có thể làm mất các bảo đảm an toàn.

## 3. HMAC và các thuật toán MAC trong JCA

**HMAC (Hash-based Message Authentication Code)** là cơ chế MAC dựa trên hàm băm mật mã. HMAC kết hợp khóa bí mật với hàm băm theo cấu trúc được thiết kế để tránh những vấn đề phát sinh khi chỉ nối khóa vào dữ liệu rồi băm.

Một số tên thuật toán thường gặp trong Java:

| Tên thuật toán | Mô tả | Độ dài thẻ thường gặp |
|---|---|---:|
| **HmacSHA256** | HMAC dùng SHA-256 | 32 byte |
| **HmacSHA384** | HMAC dùng SHA-384 | 48 byte |
| **HmacSHA512** | HMAC dùng SHA-512 | 64 byte |
| **HmacSHA3-256** | HMAC dùng SHA3-256, nếu provider hỗ trợ | 32 byte |

Tên thuật toán và mức hỗ trợ cụ thể phụ thuộc JDK, provider và môi trường triển khai. **HmacSHA256** là lựa chọn phổ biến cho nhiều hệ thống mới. Khi chọn thuật toán, cần kiểm tra yêu cầu tương thích, chính sách mật mã của tổ chức và danh sách thuật toán được provider triển khai.

Độ dài thẻ là độ dài đầu ra của thuật toán. Nó không đồng nghĩa với độ dài khóa. Ví dụ, HmacSHA256 tạo thẻ 32 byte; ứng dụng có thể sinh một khóa HMAC 256 bit. Không nên tùy tiện cắt ngắn thẻ. Nếu giao thức yêu cầu thẻ rút gọn, độ dài phải được quy định rõ, được đánh giá theo mức an toàn cần thiết và được áp dụng thống nhất ở cả hai phía.

JCA cũng có thể cung cấp các thuật toán MAC khác, chẳng hạn AES-CMAC hoặc Poly1305, tùy provider. Ứng dụng nên yêu cầu đúng thuật toán theo giao thức và xác minh provider triển khai thuật toán đó.

## 4. Vị trí của Mac trong kiến trúc JCA

JCA cung cấp các lớp API cấp cao gọi là **engine class**. Các lớp này định nghĩa cách ứng dụng yêu cầu một dịch vụ mật mã mà không cần phụ thuộc trực tiếp vào mã triển khai của từng nhà cung cấp.

Với MAC, các thành phần chính là:

- **javax.crypto.Mac:** API ứng dụng dùng để khởi tạo, cập nhật dữ liệu và lấy thẻ xác thực.
- **javax.crypto.MacSpi:** lớp trừu tượng thuộc Service Provider Interface (SPI), được provider kế thừa để thực hiện phép tính MAC.
- **java.security.Provider:** đăng ký tên thuật toán và lớp triển khai dịch vụ.
- **SecretKey:** đối tượng đại diện cho khóa bí mật được dùng để khởi tạo Mac.

Luồng xử lý thường diễn ra như sau:

1. Ứng dụng gọi **Mac.getInstance("HmacSHA256")**.
2. JCA tìm provider đã đăng ký có cung cấp dịch vụ MAC cho thuật toán đó.
3. Ứng dụng gọi **init(key)** để nạp khóa vào đối tượng Mac.
4. Ứng dụng truyền thông điệp qua **update(...)** hoặc trực tiếp vào **doFinal(...)**.
5. Provider thực hiện phép tính và trả về thẻ xác thực.

Có thể yêu cầu provider cụ thể bằng overload nhận tên provider hoặc đối tượng Provider. Việc chỉ định provider hữu ích khi triển khai có yêu cầu tương thích, chứng nhận hoặc khi khóa nằm trong thiết bị bảo mật. Nếu không có yêu cầu đó, để JCA chọn provider theo cấu hình hệ thống thường giúp ứng dụng linh hoạt hơn.

Provider có thể là triển khai phần mềm thuần Java hoặc kết nối tới HSM/token thông qua PKCS#11. Khi dùng HSM, đối tượng SecretKey có thể đại diện cho khóa nằm trong thiết bị; khóa không nhất thiết phải xuất ra bộ nhớ ứng dụng. Ứng dụng vẫn gọi API Mac, còn provider chuyển thao tác tới vùng bảo vệ.

## 5. Các thao tác cơ bản của lớp Mac

Các phương thức quan trọng của **javax.crypto.Mac** gồm:

| Phương thức | Vai trò |
|---|---|
| **getInstance(algorithm)** | Tạo đối tượng Mac cho thuật toán được yêu cầu |
| **init(key)** | Khởi tạo phép tính với khóa bí mật |
| **init(key, params)** | Khởi tạo với khóa và tham số thuật toán nếu cần |
| **update(data)** | Nạp toàn bộ hoặc một phần thông điệp |
| **doFinal()** | Hoàn tất phép tính và trả về thẻ MAC |
| **doFinal(data)** | Nạp dữ liệu rồi hoàn tất phép tính |
| **reset()** | Đưa đối tượng về trạng thái đã khởi tạo |
| **getMacLength()** | Trả về độ dài thẻ tính bằng byte |
| **getAlgorithm()** | Trả về tên thuật toán |
| **getProvider()** | Trả về provider đang cung cấp triển khai |

Trình tự sử dụng cơ bản là tạo đối tượng, khởi tạo bằng khóa, nạp dữ liệu và gọi **doFinal**. Sau khi hoàn tất, đối tượng Mac được đưa về trạng thái đã khởi tạo để có thể thực hiện phép tính tiếp theo với khóa đó. Khi đổi khóa, phải gọi **init** lại.

Một đối tượng Mac không nên được chia sẻ đồng thời giữa nhiều luồng. Trạng thái bên trong thay đổi theo từng lần gọi update và doFinal. Hãy tạo một đối tượng riêng cho mỗi phép tính hoặc mỗi luồng xử lý độc lập.

## 6. Sinh khóa HMAC an toàn

Khóa MAC phải được tạo bằng bộ sinh khóa mật mã của JCA hoặc hệ thống quản lý khóa được tin cậy. Không dùng mật khẩu người dùng trực tiếp làm khóa HMAC, không tự tạo khóa bằng cách ghép chuỗi, timestamp hoặc số ngẫu nhiên thông thường.

Ví dụ sinh khóa HmacSHA256 bằng **KeyGenerator**:

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class HmacKeys {
    private HmacKeys() {
    }

    public static SecretKey generate() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        return generator.generateKey();
    }
}
~~~

Ví dụ yêu cầu bộ sinh khóa tạo khóa 256 bit. Khả năng hỗ trợ kích thước khóa cụ thể phụ thuộc provider. Trong môi trường sản xuất, nên xác minh chính sách khóa và khả năng của provider đang triển khai.

Sau khi sinh, khóa cần được lưu bằng cơ chế phù hợp. Tùy kiến trúc, có thể dùng KeyStore với **SecretKeyEntry**, KMS hoặc HSM. Hạn chế quyền truy cập theo dịch vụ và mục đích sử dụng. Không ghi khóa vào log, không commit khóa vào mã nguồn và không truyền khóa qua kênh không bảo vệ.

Với khóa được tạo trong HSM hoặc KMS, hãy ưu tiên thao tác MAC trực tiếp trên đối tượng khóa do provider cung cấp. Không gọi **getEncoded()** để xuất khóa nếu hệ thống được thiết kế để giữ khóa không thể xuất.

## 7. Tạo và xác minh HMAC bằng Java

Ví dụ sau minh họa việc tạo thẻ HMAC-SHA-256 và xác minh thẻ nhận được. Khóa được truyền vào từ thành phần quản lý khóa; ví dụ không nhúng vật liệu khóa vào mã nguồn.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class HmacService {
    private static final String ALGORITHM = "HmacSHA256";

    private HmacService() {
    }

    public static byte[] createTag(
            SecretKey key,
            byte[] message) throws GeneralSecurityException {

        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(key);
        return mac.doFinal(message);
    }

    public static boolean verifyTag(
            SecretKey key,
            byte[] message,
            byte[] receivedTag) throws GeneralSecurityException {

        if (receivedTag == null) {
            return false;
        }

        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(key);

        byte[] expectedTag = mac.doFinal(message);

        if (receivedTag.length != expectedTag.length) {
            return false;
        }

        return MessageDigest.isEqual(expectedTag, receivedTag);
    }
}
~~~

Trong ví dụ:

- **Mac.getInstance(ALGORITHM)** yêu cầu JCA cung cấp triển khai HmacSHA256.
- **mac.init(key)** gắn khóa bí mật với phép tính.
- **mac.doFinal(message)** tính thẻ từ toàn bộ mảng byte của thông điệp.
- Khi xác minh, ứng dụng tự tính thẻ mong đợi rồi so sánh với thẻ nhận được.
- **MessageDigest.isEqual** thực hiện phép so sánh phù hợp cho dữ liệu digest/tag, tránh cách so sánh thông thường có thể dừng ngay tại byte khác biệt đầu tiên.

Ứng dụng cần quy định độ dài thẻ hợp lệ theo giao thức. Với HmacSHA256 đầy đủ, thẻ có 32 byte. Nếu giao thức sử dụng thẻ rút gọn, hãy thay điều kiện độ dài bằng độ dài cố định đã được chuẩn hóa và đánh giá an toàn. Không chấp nhận độ dài tùy ý từ phía gửi.

Không nên chuyển thẻ MAC sang chuỗi để so sánh bằng **String.equals**. Hãy giữ dữ liệu ở dạng byte và dùng phép so sánh thích hợp. Nếu thẻ được truyền dưới dạng Base64 hoặc hexadecimal, giải mã và kiểm tra định dạng trước khi xác minh.

## 8. Xử lý thông điệp lớn theo từng phần

Không bắt buộc phải nạp toàn bộ thông điệp vào bộ nhớ. Mac hỗ trợ cập nhật từng phần bằng nhiều lần gọi **update**. Cách này hữu ích khi xác thực tệp lớn, luồng mạng hoặc dữ liệu được đọc theo từng khối.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.security.GeneralSecurityException;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class HmacStream {
    private HmacStream() {
    }

    public static byte[] createTag(
            SecretKey key,
            InputStream input)
            throws GeneralSecurityException, IOException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);

        byte[] buffer = new byte[8192];
        int bytesRead;

        while ((bytesRead = input.read(buffer)) != -1) {
            mac.update(buffer, 0, bytesRead);
        }

        return mac.doFinal();
    }
}
~~~

Đoạn mã giả định luồng đầu vào do bên gọi quản lý và được đóng ở nơi sở hữu luồng. Mỗi lần gọi update chỉ đưa phần byte thực tế vừa đọc vào phép tính. Không đưa toàn bộ buffer nếu số byte đọc được nhỏ hơn kích thước buffer, vì các byte còn lại có thể là dữ liệu cũ từ lần đọc trước.

Khi xác minh tệp, bên nhận cần tính MAC trên đúng chuỗi byte mà bên gửi đã xác thực. Nếu dữ liệu được giải nén, chuyển mã hoặc chuẩn hóa trước khi tính ở một phía nhưng không làm tương tự ở phía còn lại, thẻ sẽ không khớp.

## 9. Xác thực đúng dữ liệu và ngăn replay

MAC chỉ xác thực những byte thực sự được đưa vào phép tính. Nếu ứng dụng chỉ MAC phần nội dung mà bỏ qua thông tin định tuyến, định danh người dùng, phương thức HTTP hoặc phiên bản giao thức, kẻ tấn công có thể chuyển một thông điệp hợp lệ sang ngữ cảnh khác.

Vì vậy, cần xác định rõ cấu trúc dữ liệu được xác thực. Với một yêu cầu API, dữ liệu MAC có thể bao gồm:

- Phiên bản giao thức và định danh dịch vụ.
- Key ID hoặc phiên bản khóa được dùng để xác minh.
- Phương thức HTTP và đường dẫn đã chuẩn hóa.
- Timestamp hoặc nonce.
- Content-Type và các trường quan trọng khác.
- Hash của phần thân hoặc toàn bộ phần thân theo quy tắc giao thức.

Các trường phải được mã hóa theo một định dạng không nhập nhằng. Không chỉ nối các chuỗi tùy ý: ví dụ cặp trường ("ab", "c") và ("a", "bc") có thể tạo cùng chuỗi byte nếu không có dấu phân cách hoặc độ dài trường. Có thể dùng định dạng chuẩn hóa đã được định nghĩa, mã hóa độ dài trước từng trường hoặc cấu trúc nhị phân có schema rõ ràng.

MAC không tự ngăn replay. Một thông điệp cũ vẫn có thẻ hợp lệ nếu nội dung và khóa không đổi. Để chống replay, giao thức phải xác thực nonce, timestamp hoặc số thứ tự cùng thông điệp, đồng thời phía nhận phải kiểm tra tính mới và lưu trạng thái cần thiết để từ chối giá trị đã dùng. Timestamp chỉ có tác dụng khi đồng hồ và cửa sổ chấp nhận được quản lý phù hợp.

## 10. Quản lý vòng đời khóa MAC

Độ an toàn của HMAC phụ thuộc trực tiếp vào độ an toàn của khóa. Vì vậy, triển khai MAC phải tuân thủ chính sách quản lý khóa của hệ thống.

- **Tạo khóa:** dùng KeyGenerator, KMS hoặc HSM với nguồn ngẫu nhiên mật mã phù hợp. Không dùng mật khẩu hoặc dữ liệu dễ đoán làm khóa.
- **Lưu trữ:** lưu khóa dưới dạng SecretKeyEntry hoặc trong KMS/HSM. Bảo vệ bản sao lưu và giới hạn quyền đọc, sử dụng.
- **Cấp phát:** chỉ cấp quyền cho dịch vụ thực sự cần tạo hoặc xác minh MAC. Alias hay key ID chỉ là định danh, không phải cơ chế phân quyền.
- **Sử dụng:** dùng đúng khóa và thuật toán đã quy định. Không tái sử dụng một khóa cho HMAC và mã hóa đối xứng với mục đích khác.
- **Xoay vòng:** tạo khóa mới, gắn key ID hoặc phiên bản vào giao thức, chuyển bên tạo sang khóa mới và duy trì khả năng xác minh dữ liệu cũ trong thời gian chuyển tiếp nếu chính sách yêu cầu.
- **Thu hồi:** khi khóa bị lộ hoặc không còn được phép sử dụng, chặn quyền truy cập và chuyển sang khóa mới. Đánh giá các thông điệp đã được xác thực bằng khóa bị lộ.
- **Hủy:** loại bỏ khóa khỏi kho đang hoạt động và xử lý các bản sao, bản sao lưu, cache hoặc thiết bị theo chính sách hủy khóa.

Trong giai đoạn xoay vòng, hệ thống có thể cần xác minh bằng khóa hiện tại và một số khóa cũ còn hiệu lực. Mỗi thông điệp nên mang định danh khóa để phía nhận chọn đúng khóa theo chính sách; định danh này phải nằm trong phần dữ liệu được MAC xác thực để kẻ tấn công không thể đổi key ID mà vẫn giữ thẻ hợp lệ. Giới hạn số khóa cũ được chấp nhận và thời gian chuyển tiếp; không thử vô hạn mọi khóa có sẵn vì làm tăng rủi ro và chi phí xử lý.

Nếu dùng một khóa gốc để dẫn xuất nhiều khóa, hãy sử dụng KDF phù hợp và nhãn dẫn xuất riêng cho từng mục đích, thuật toán và dịch vụ. Không dùng cùng một giá trị khóa thô cho cả MAC và mã hóa chỉ vì cả hai API đều nhận SecretKey.

## 11. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Dùng SHA-256 thay cho HMAC-SHA-256 | Không có xác thực bằng bí mật; kẻ tấn công có thể tự tính lại hash | Dùng thuật toán MAC có khóa như HmacSHA256 |
| Dùng mật khẩu hoặc chuỗi cố định làm khóa | Khóa dễ đoán, có thể bị khôi phục từ mã nguồn hoặc cấu hình | Sinh khóa bằng KeyGenerator hoặc KMS/HSM |
| So sánh thẻ bằng phép so sánh thông thường | Có thể tạo kênh rò rỉ thời gian theo vị trí byte khác biệt | Dùng MessageDigest.isEqual và kiểm tra định dạng thẻ |
| Không xác thực metadata quan trọng | Thông điệp hợp lệ có thể bị chuyển sang ngữ cảnh khác | Đưa các trường định danh và ngữ cảnh vào dữ liệu MAC |
| Cho rằng MAC tự chống replay | Kẻ tấn công có thể gửi lại thông điệp và thẻ cũ | Xác thực nonce/timestamp/số thứ tự và kiểm tra trạng thái |
| Chia sẻ một đối tượng Mac giữa nhiều luồng | Trạng thái update/doFinal có thể bị xen kẽ | Tạo Mac riêng cho mỗi phép tính hoặc luồng |
| Dùng lại khóa MAC cho nhiều mục đích | Tăng tác động khi lộ khóa và phá vỡ ranh giới giữa các giao thức | Dùng khóa riêng hoặc dẫn xuất khóa theo mục đích |
| Xóa khóa cũ ngay khi tạo khóa mới | Không thể xác minh dữ liệu hợp lệ được tạo trước khi xoay vòng | Lập kế hoạch chuyển tiếp và thời hạn xác minh khóa cũ |
| Tự chọn thuật toán mà không kiểm tra provider | Ứng dụng có thể lỗi khi triển khai ở môi trường khác | Kiểm tra thuật toán và provider trên môi trường đích |

## 12. Nguyên tắc triển khai an toàn

- Ưu tiên HMAC với thuật toán hash hiện đại được chính sách hệ thống chấp thuận, chẳng hạn HmacSHA256.
- Dùng khóa ngẫu nhiên có độ mạnh phù hợp và lưu trong KeyStore, KMS hoặc HSM.
- Xác thực chính xác toàn bộ dữ liệu có ý nghĩa bảo mật, gồm cả metadata, phiên bản và định danh ngữ cảnh.
- Dùng MessageDigest.isEqual để so sánh thẻ; kiểm tra độ dài và định dạng theo giao thức.
- Bổ sung nonce, timestamp hoặc số thứ tự nếu cần chống replay.
- Không dùng MAC thay cho mã hóa khi dữ liệu cần giữ bí mật.
- Không tự thiết kế cách kết hợp mã hóa và MAC; ưu tiên AEAD khi cần vừa mã hóa vừa xác thực.
- Không chia sẻ một đối tượng Mac có trạng thái giữa các luồng.
- Thiết kế key ID, quy trình xoay vòng, thời gian chấp nhận khóa cũ và quy trình xử lý khi khóa bị lộ.
- Ghi log sự kiện sử dụng khóa ở mức cần thiết, nhưng không ghi khóa bí mật, thẻ nhạy cảm hoặc dữ liệu xác thực có thể bị phát lại.

Trong kiến trúc Java, Mac là điểm nối giữa API JCA và vật liệu khóa do provider quản lý. Khi ứng dụng giữ đúng ranh giới này, nó có thể thay đổi provider hoặc chuyển khóa sang HSM/KMS mà không phải viết lại toàn bộ logic xác thực thông điệp. Điều kiện quan trọng là thuật toán, định dạng thông điệp, cách xác minh và chính sách vòng đời khóa phải được các thành phần tham gia thống nhất.
