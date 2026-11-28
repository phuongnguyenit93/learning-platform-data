# MessageDigest

MessageDigest là API trong Java Cryptography Architecture (JCA) dùng để tính giá trị băm mật mã (cryptographic hash) từ dữ liệu. Giá trị băm có độ dài cố định theo thuật toán, đại diện cho nội dung đầu vào và thường được dùng để kiểm tra tính toàn vẹn, tạo dấu vân tay dữ liệu hoặc làm thành phần của các giao thức mật mã.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, MessageDigest giúp hiểu cách ứng dụng Java xử lý dữ liệu mật mã và phân biệt hàm băm với mã hóa, MAC và chữ ký số. Hash không phải khóa bí mật và không thể giải mã ngược để lấy dữ liệu ban đầu. Tuy vậy, chọn sai thuật toán hoặc dùng hash sai mục đích có thể làm mất bảo đảm an toàn mà hệ thống cần.

## 1. Hàm băm mật mã là gì?

Hàm băm mật mã nhận một đầu vào có độ dài tùy ý và tạo ra một đầu ra có độ dài cố định, gọi là digest hoặc hash value. Ví dụ, SHA-256 luôn tạo ra 256 bit (32 byte), dù đầu vào là một từ ngắn hay một tệp có kích thước nhiều gigabyte.

Một hàm băm mật mã tốt thường có các đặc tính:

- **Tính xác định:** cùng một chuỗi byte đầu vào luôn tạo cùng một digest.
- **Một chiều:** từ digest rất khó tìm lại đầu vào ban đầu.
- **Kháng va chạm (collision resistance):** rất khó tìm hai đầu vào khác nhau có cùng digest.
- **Kháng tiền ảnh thứ hai (second-preimage resistance):** khi đã biết một đầu vào, rất khó tìm đầu vào khác có cùng digest.
- **Kháng tiền ảnh (preimage resistance):** với một digest cho trước, rất khó tìm đầu vào tạo ra digest đó.
- **Hiệu ứng avalanche:** thay đổi nhỏ ở đầu vào làm digest thay đổi lớn và khó dự đoán.

Digest không phải bản mã. Không có khóa giải mã để khôi phục dữ liệu từ hash. Cũng không nên coi digest là bằng chứng xác thực nguồn gửi nếu không có khóa bí mật hoặc chữ ký số bảo vệ nó.

Hash cũng không che giấu dữ liệu có ít khả năng lựa chọn. Nếu đầu vào là một giá trị dễ đoán như mã PIN hoặc một từ phổ biến, kẻ tấn công có thể thử các ứng viên, tính hash rồi so sánh. Đây là một lý do không dùng MessageDigest trực tiếp để lưu mật khẩu.

## 2. Collision, preimage và giới hạn bảo mật

Ba thuộc tính kháng tiền ảnh và va chạm giải quyết các bài toán khác nhau:

| Thuộc tính | Bài toán của kẻ tấn công | Ý nghĩa |
|---|---|---|
| Preimage resistance | Cho digest H, tìm dữ liệu x sao cho hash(x) = H | Ngăn suy ngược dữ liệu từ digest |
| Second-preimage resistance | Cho dữ liệu x, tìm y khác x sao cho hash(y) = hash(x) | Ngăn thay dữ liệu đã biết bằng dữ liệu khác có cùng hash |
| Collision resistance | Tự tìm hai dữ liệu x và y khác nhau sao cho hash(x) = hash(y) | Ngăn tạo trước hai nội dung khác nhau nhưng cùng digest |

Với hàm băm lý tưởng có đầu ra n bit, tìm va chạm bằng tìm kiếm ngẫu nhiên có độ phức tạp xấp xỉ 2^(n/2) do nghịch lý sinh nhật. Tìm tiền ảnh có độ phức tạp xấp xỉ 2^n. Đây là mô hình lý tưởng; điểm yếu cấu trúc của thuật toán có thể làm chi phí thực tế thấp hơn nhiều.

Ví dụ, SHA-256 có đầu ra 256 bit nên mức bảo đảm lý tưởng trước va chạm vào khoảng 128 bit. MD5 và SHA-1 đã có tấn công va chạm thực tế, vì vậy không nên dùng chúng cho chữ ký số, chứng thực hoặc mục đích bảo mật mới. Một hệ thống cũ có thể cần đọc digest SHA-1 để tương thích, nhưng cần lập kế hoạch thay thế.

## 3. Các thuật toán thường gặp

| Thuật toán | Độ dài digest | Đánh giá và cách dùng |
|---|---:|---|
| MD5 | 128 bit | Đã bị phá vỡ về khả năng kháng va chạm; chỉ dùng cho tương thích hoặc phát hiện lỗi ngẫu nhiên trong bối cảnh không đối kháng |
| SHA-1 | 160 bit | Không còn phù hợp cho mục đích cần kháng va chạm |
| SHA-256 | 256 bit | Lựa chọn phổ biến cho kiểm tra toàn vẹn và thành phần của các cơ chế mật mã hiện đại |
| SHA-384 | 384 bit | Thành viên SHA-2, thường được chọn khi hệ thống cần mức bảo đảm cao hơn hoặc tương thích bộ thuật toán tương ứng |
| SHA-512 | 512 bit | Thành viên SHA-2, đầu ra dài hơn; hiệu năng phụ thuộc nền tảng và provider |
| SHA3-256 | 256 bit | Thành viên SHA-3, cấu trúc sponge khác SHA-2; dùng khi chính sách hoặc hệ thống chọn SHA-3 |

Trong ứng dụng mới, SHA-256 là lựa chọn mặc định hợp lý cho nhiều trường hợp băm dữ liệu. SHA-384, SHA-512 hoặc SHA3-256 có thể phù hợp theo yêu cầu tương thích, chính sách và hiệu năng. Không nên tự chọn thuật toán chỉ vì digest dài hơn; cần xác định mô hình đe dọa và hỗ trợ của nền tảng.

Tên thuật toán mà JCA hỗ trợ phụ thuộc JDK và provider được cài đặt. SHA-3 được chuẩn hóa trong các bản Java hiện đại, nhưng ứng dụng vẫn nên kiểm tra thuật toán có sẵn trong môi trường chạy thay vì giả định mọi provider đều giống nhau.

## 4. MessageDigest trong Java Cryptography Architecture

JCA cung cấp một lớp API thống nhất cho các dịch vụ mật mã. Ứng dụng gọi API theo tên dịch vụ và thuật toán; provider cung cấp phần triển khai thực tế. Với hàm băm, lớp trung tâm là java.security.MessageDigest.

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B[MessageDigest API]
    B --> C[Provider selection]
    C --> D[Provider A: SHA-256]
    C --> E[Provider B: SHA3-256]
    D --> F[Digest bytes]
    E --> F
~~~

Ứng dụng tạo đối tượng bằng getInstance, ví dụ:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
~~~

JCA tìm provider có hỗ trợ thuật toán yêu cầu. Nếu không có thuật toán tương ứng, phương thức ném NoSuchAlgorithmException. Có thể kiểm tra provider được chọn bằng getProvider và tên thuật toán bằng getAlgorithm. Trong môi trường có yêu cầu tuân thủ hoặc chứng nhận mật mã, cần cấu hình provider theo chính sách của tổ chức và kiểm thử đúng cấu hình production.

Không nên tự triển khai SHA-256 hoặc thuật toán hash bằng code ứng dụng. Hãy dùng triển khai đã được nền tảng hoặc provider tin cậy cung cấp.

## 5. Tính digest cho dữ liệu nhỏ

Với dữ liệu đã nằm trong bộ nhớ, có thể chuyển chuỗi thành byte theo một charset xác định rồi gọi digest:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class HashText {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        String message = "Java Cryptography Architecture";
        byte[] input = message.getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(input);

        System.out.println(HexFormat.of().formatHex(hash));
    }
}
~~~

Ví dụ HashText dùng HexFormat, API có từ Java 17. Với JDK cũ hơn, có thể dùng thư viện hoặc hàm chuyển byte sang hexadecimal phù hợp.

Không nên dùng charset mặc định của máy để chuyển chuỗi thành byte. Cùng một chuỗi ký tự có thể được mã hóa thành byte khác nhau nếu charset khác nhau; UTF-8 là lựa chọn phổ biến và cần được quy định thống nhất giữa các hệ thống.

SHA-256 của chuỗi byte ASCII/UTF-8 "abc" là:

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Đây là test vector hữu ích để kiểm tra việc gọi API và biểu diễn digest. Khi so sánh kết quả giữa các hệ thống, cần bảo đảm dữ liệu đầu vào giống hệt ở mức byte, bao gồm encoding, chuẩn hóa Unicode, dấu xuống dòng và khoảng trắng.

## 6. Xử lý dữ liệu theo từng phần

MessageDigest hỗ trợ update để nhận dữ liệu theo nhiều phần. Cách này phù hợp với tệp lớn hoặc dữ liệu truyền qua mạng vì ứng dụng không cần nạp toàn bộ dữ liệu vào bộ nhớ.

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class HashFile {
    public static byte[] sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream input = Files.newInputStream(path)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return digest.digest();
    }
}
~~~

Luồng dữ liệu được xử lý tuần tự: mỗi lần đọc, chỉ phần byte thực sự nhận được được đưa vào update. Khi hết dữ liệu, digest() trả về digest cuối cùng. Kích thước buffer ảnh hưởng đến hiệu năng I/O và bộ nhớ, nhưng không làm thay đổi kết quả hash.

Một lựa chọn khác là DigestInputStream, lớp bọc InputStream và tự cập nhật MessageDigest khi dữ liệu được đọc. Dù dùng cách nào, phải đọc hết luồng nếu muốn hash toàn bộ nội dung. Nếu dừng giữa chừng, digest chỉ đại diện cho phần đã đọc.

## 7. Vòng đời của một đối tượng MessageDigest

Các phương thức chính:

| Phương thức | Chức năng |
|---|---|
| getInstance(algorithm) | Tạo đối tượng cho thuật toán được yêu cầu |
| update(byte) / update(byte[]) | Bổ sung byte vào dữ liệu đang được băm |
| update(buffer, offset, length) | Bổ sung một vùng của mảng byte |
| digest() | Kết thúc thao tác và trả về digest |
| digest(input) | Băm dữ liệu được truyền vào và trả digest |
| reset() | Đưa đối tượng về trạng thái ban đầu |
| getDigestLength() | Trả độ dài digest theo byte, nếu provider cung cấp |
| getAlgorithm() | Trả tên thuật toán |
| getProvider() | Trả provider đang cung cấp triển khai |

Sau khi gọi digest(), đối tượng MessageDigest được reset về trạng thái ban đầu theo hợp đồng API. Có thể dùng lại đối tượng cho một thông điệp khác, nhưng phải bảo đảm không trộn dữ liệu giữa các thông điệp.

MessageDigest không được thiết kế để nhiều luồng cùng gọi update/digest trên một instance mà không đồng bộ. Cách đơn giản và an toàn là tạo instance riêng cho từng thao tác hoặc từng luồng. Không chia sẻ một đối tượng đang giữ trạng thái băm giữa các request đồng thời.

## 8. So sánh digest một cách an toàn

Để kiểm tra tệp có đúng digest mong đợi hay không, tính digest từ dữ liệu nhận được rồi so sánh với digest được lấy từ nguồn tin cậy. Đoạn mã sau là phần minh họa; ứng dụng cần cung cấp các hàm đọc digest tham chiếu và tính digest cho tệp.

~~~java
import java.security.MessageDigest;

byte[] expectedDigest = loadExpectedDigest();
byte[] actualDigest = calculateDigest(file);

boolean matches = MessageDigest.isEqual(
        expectedDigest,
        actualDigest);

if (!matches) {
    throw new SecurityException("Digest mismatch");
}
~~~

MessageDigest.isEqual được cung cấp để so sánh hai mảng digest theo cách phù hợp cho dữ liệu mật mã. Tránh dùng toán tử == với byte[] vì toán tử này so sánh tham chiếu đối tượng, không so sánh nội dung. Cũng không nên tự viết vòng lặp dừng ngay tại byte khác đầu tiên khi so sánh giá trị bí mật.

Quan trọng hơn, digest mong đợi phải đến từ nguồn đáng tin cậy. Nếu kẻ tấn công có thể thay cả tệp lẫn file chứa digest, họ có thể tính lại hash và khiến phép so sánh vẫn thành công. Hash không tự xác thực người tạo ra dữ liệu.

## 9. Hash, HMAC và chữ ký số khác nhau thế nào?

Các cơ chế này đều có thể dùng hàm băm, nhưng cung cấp bảo đảm khác nhau:

| Cơ chế | Có khóa bí mật? | Bảo đảm chính | API Java |
|---|---:|---|---|
| MessageDigest | Không | Tạo digest để nhận diện nội dung và hỗ trợ kiểm tra thay đổi | MessageDigest |
| HMAC | Có khóa bí mật dùng chung | Toàn vẹn và xác thực thông điệp giữa các bên cùng biết khóa | javax.crypto.Mac |
| Chữ ký số | Có private key ký và public key xác minh | Toàn vẹn, xác thực nguồn ký và khả năng kiểm chứng công khai | java.security.Signature |

Nếu cần xác thực thông điệp giữa hai dịch vụ cùng chia sẻ bí mật, dùng HMAC-SHA-256 thay vì chỉ gửi hash. Nếu cần bên thứ ba kiểm chứng nguồn ký mà không biết private key, dùng chữ ký số với khóa riêng và chứng thư phù hợp. Không dùng MessageDigest như thể nó là MAC hoặc chữ ký.

Ví dụ HMAC dùng API Mac (đoạn mã giả định secretKey và messageBytes đã được tạo hoặc nạp từ nguồn phù hợp):

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(secretKey);
byte[] tag = mac.doFinal(messageBytes);
~~~

Khóa HMAC cần được tạo, lưu trữ, phân phối và xoay vòng theo chính sách quản lý khóa. Không nhúng khóa bí mật trực tiếp trong mã nguồn.

## 10. MessageDigest không phù hợp để băm mật khẩu

Không lưu mật khẩu bằng cách gọi SHA-256 một lần rồi lưu digest. Hàm băm mật mã tổng quát được thiết kế để tính nhanh; điều đó có lợi cho kiểm tra toàn vẹn nhưng lại có hại khi bảo vệ mật khẩu trước tấn công đoán ngoại tuyến.

Để lưu mật khẩu, dùng password hashing/KDF chuyên dụng có salt riêng cho từng mật khẩu và chi phí tính toán có thể điều chỉnh, chẳng hạn Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số phù hợp chính sách. Trong Java, PBKDF2 có thể được truy cập qua SecretKeyFactory với thuật toán PBKDF2WithHmacSHA256. Các thư viện và nền tảng có thể cung cấp thêm Argon2id hoặc scrypt.

Salt không phải mật khẩu hay khóa bí mật; nó là giá trị ngẫu nhiên riêng cho mỗi bản ghi để ngăn việc dùng bảng tra cứu dựng sẵn (rainbow table) và làm lộ các mật khẩu trùng nhau qua cùng một digest. Cần lưu salt và tham số KDF cùng verifier để có thể xác minh mật khẩu khi đăng nhập. Pepper, nếu được dùng, là bí mật bổ sung và phải được bảo vệ riêng.

Không nên tự tạo password KDF bằng cách lặp SHA-256 nhiều lần. Hãy dùng thuật toán chuyên dụng và thư viện được duy trì.

## 11. Những lỗi thường gặp khi dùng MessageDigest

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng MD5 hoặc SHA-1 cho chữ ký hoặc xác thực | Không còn bảo đảm kháng va chạm cần thiết | Chuyển sang SHA-256 trở lên theo chính sách |
| Hash chuỗi bằng charset mặc định | Kết quả khác nhau giữa môi trường | Chỉ định UTF-8 hoặc encoding đã thỏa thuận |
| Hash không hết tệp | Digest chỉ đại diện cho một phần dữ liệu | Đọc đến EOF và kiểm tra lỗi I/O |
| So sánh byte[] bằng == | So sánh tham chiếu, không so sánh nội dung | Dùng MessageDigest.isEqual |
| Dùng hash không khóa để xác thực nguồn | Kẻ tấn công có thể thay dữ liệu và digest | Dùng HMAC hoặc chữ ký số |
| Dùng SHA-256 trực tiếp cho mật khẩu | Tấn công đoán mật khẩu có thể chạy rất nhanh | Dùng password hashing/KDF có salt và chi phí phù hợp |
| Chia sẻ một instance giữa nhiều luồng | Trạng thái update có thể bị trộn | Dùng instance riêng cho từng thao tác/luồng |
| Chỉ dựa vào tên thuật toán mà không kiểm tra provider | Có thể chạy với provider hoặc cấu hình ngoài dự kiến | Kiểm tra provider và chính sách runtime |

## 12. Checklist sử dụng trong ứng dụng

- [ ] Chọn thuật toán còn an toàn, thường là SHA-256 hoặc mạnh hơn theo chính sách.
- [ ] Dùng MessageDigest từ JCA thay vì tự triển khai thuật toán hash.
- [ ] Chuyển dữ liệu sang byte với charset được quy định rõ, thường là UTF-8.
- [ ] Với dữ liệu lớn, dùng update theo từng khối và đọc hết luồng.
- [ ] Không chia sẻ một instance MessageDigest giữa các thao tác đồng thời.
- [ ] So sánh digest bằng MessageDigest.isEqual khi cần so sánh giá trị mật mã.
- [ ] Lấy digest tham chiếu từ nguồn tin cậy; dùng HMAC hoặc chữ ký số nếu cần xác thực nguồn.
- [ ] Không dùng MessageDigest tổng quát để lưu mật khẩu.
- [ ] Kiểm tra thuật toán và provider trong môi trường triển khai thực tế.
- [ ] Ghi nhận thuật toán, encoding và quy tắc chuẩn hóa dữ liệu để các hệ thống tạo cùng digest.

MessageDigest là công cụ nền tảng để tạo hash trong Java, nhưng digest chỉ có ý nghĩa khi thuật toán, biểu diễn dữ liệu và nguồn tham chiếu được xác định đúng. Khi thiết kế bảo vệ dữ liệu, cần chọn đúng cơ chế: MessageDigest cho digest, HMAC cho xác thực bằng khóa dùng chung, chữ ký số cho xác thực công khai và KDF chuyên dụng cho mật khẩu.
