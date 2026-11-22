# 5.1 MAC chứng minh điều gì khi hai bên cùng giữ một khóa bí mật

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích chính xác ý nghĩa của một **Message Authentication Code (MAC)** trong hệ thống có hai bên cùng biết khóa bí mật; chỉ ra những giả định phải đúng trước khi tin kết quả xác thực; phân biệt xác thực thông điệp với chứng minh danh tính và chống chối bỏ; triển khai HMAC-SHA-256 trong Java 17+; đồng thời thiết kế quy trình kiểm tra MAC, bảo vệ khóa và chống phát lại ở mức giao thức.

**Câu trả lời cốt lõi:** Khi Bob kiểm tra MAC của thông điệp M bằng khóa bí mật K mà Alice và Bob cùng giữ, kết quả hợp lệ cung cấp **bằng chứng mật mã, trong giới hạn giả định an toàn**, rằng M đã được xác thực bằng K và chưa bị sửa theo cách mà MAC không phát hiện. Bob có thể kết luận **một chủ thể biết K đã tạo tag hợp lệ** (hoặc đã có một sự giả mạo với xác suất rất nhỏ). Nhưng **Bob không thể dùng MAC để chứng minh cho người thứ ba chính Alice đã tạo tag**, vì Bob cũng có thể tự tạo đúng tag bằng cùng K.

Điểm phân biệt đó quyết định cách dùng MAC trong API, webhook, giao tiếp dịch vụ và hệ thống cần truy vết trách nhiệm.

## 1. MAC là gì, các bên chia sẻ điều gì?

Giả sử Alice là dịch vụ gửi yêu cầu và Bob là dịch vụ nhận yêu cầu. Hai bên đã nhận cùng một **khóa bí mật K** qua một quy trình phân phối khóa an toàn. K không được công khai cho người quan sát mạng.

MAC có hai thao tác khái niệm:

- **Tạo tag:** T = MAC(K, M), từ khóa K và chuỗi byte thông điệp M tạo ra mã xác thực T.
- **Xác minh tag:** Verify(K, M, T) trả hợp lệ hoặc không hợp lệ. Với HMAC, bên xác minh tính lại tag dự kiến từ K và M rồi so sánh an toàn với T nhận được.

Luồng điển hình:

~~~text
Alice                                          Bob
Có cùng khóa K                           Có cùng khóa K

M = dữ liệu yêu cầu
T = MAC(K, M)
              M, T  --------------------->
                                         T' = MAC(K, M)
                                         So sánh T' với T
                                         Khớp -> MAC hợp lệ
                                         Sai  -> Từ chối
~~~

**Thông điệp M không nhất thiết được mã hóa bí mật.** Trong sơ đồ này, người nghe lén có thể đọc M nếu không có TLS hay encryption. MAC bổ sung cơ chế kiểm tra tính toàn vẹn và tính xác thực dựa trên quyền sở hữu khóa, chứ không làm dữ liệu trở nên khó đọc.

Một đặc điểm quan trọng: **cùng khóa và cùng chuỗi byte đầu vào** cho cùng tag trong các MAC tất định như HMAC. Nếu Bob tự chạy MAC(K, M), anh ấy sẽ tạo kết quả đúng như Alice, vì hệ thống không có khóa ký riêng của Alice.

## 2. MAC hợp lệ thực sự cho biết điều gì?

### 2.1 Tính toàn vẹn của thông điệp (message integrity)

Nếu M bị sửa thành M' nhưng người sửa không biết K, tag T được tạo cho M thường sẽ **không xác thực được cho M'**. Vì vậy MAC giúp phát hiện sửa đổi trái phép đối với **những byte thực sự nằm trong phần đầu vào được MAC bảo vệ**.

Ví dụ: Alice gửi yêu cầu thanh toán có số tiền 100. Kẻ tấn công thay dữ liệu thành 900 nhưng giữ nguyên tag. Bob tính lại MAC cho thông điệp đã thay đổi; tag cũ không khớp và Bob từ chối.

Tuy nhiên, MAC không tự hiểu các trường nghiệp vụ. Nếu Alice chỉ MAC trường amount nhưng bỏ qua currency, recipient hoặc operation, kẻ tấn công có thể sửa những trường **ngoài phạm vi MAC** mà kết quả kiểm tra vẫn hợp lệ. Việc chọn chính xác dữ liệu được ký xác thực là một phần bắt buộc của thiết kế giao thức.

### 2.2 Tính xác thực dựa trên khóa chung (shared-key message authentication)

Với thuật toán MAC an toàn, K được giữ bí mật và không có lỗ hổng quy trình, đối thủ **không biết K** không thể tự tạo tag hợp lệ cho thông điệp mới với xác suất đáng kể, kể cả khi họ đã quan sát nhiều cặp thông điệp–tag hợp lệ.

Vì vậy kết quả kiểm tra thành công là bằng chứng rằng tag **phù hợp với một bên biết K**, hoặc là kết quả của một sự giả mạo thành công rất khó xảy ra. Đó là ý nghĩa của **message authentication** trong mô hình khóa đối xứng.

Cần nói chính xác:

- Bob biết **K và byte thông điệp M khớp với tag T**.
- Bob có cơ sở tin rằng **một chủ thể nắm K đã tạo hoặc có quyền tạo tag** trong mô hình đe dọa đã xác định.
- Bob **không có bằng chứng mật mã độc lập** xác định chính xác chủ thể nào trong nhóm giữ K đã tạo tag.

Nếu chỉ Alice và Bob giữ K, Bob biết bản thân không tạo tag và K chưa lộ, Bob có thể **suy luận theo ngữ cảnh vận hành** rằng Alice đã gửi. Nhưng đây là suy luận dựa trên các giả định ngoài phép toán MAC; bằng chứng MAC một mình không phân biệt được Alice với Bob.

### 2.3 MAC không tạo bằng chứng không thể chối bỏ (non-repudiation)

Giả sử Bob đem thông điệp “Alice đồng ý chuyển tiền” và tag MAC ra trước một trọng tài. Alice có thể phản biện: “Bob cũng biết K, Bob có thể tự tạo cặp M, T đó”. Vì cả hai cùng có khả năng tính MAC(K, M), trọng tài **không thể chỉ dựa vào MAC mà kết luận Alice đã tạo tag**.

Đây là giới hạn cơ bản của **mật mã đối xứng với khóa chung**, không phải lỗi riêng của HMAC.

Để cần bằng chứng có thể xác minh bằng khóa công khai và liên kết với một người ký, thường dùng **chữ ký số**: chỉ bên giữ private key ký; bên khác có public key để kiểm tra. Chữ ký số cho phép mô hình quy trách nhiệm mạnh hơn, nhưng tính chống chối bỏ thực tế còn phụ thuộc quyền kiểm soát khóa riêng, danh tính gắn với khóa, thời điểm, quy trình cấp chứng chỉ và xử lý sự cố. Không nên hứa rằng bất kỳ chữ ký số nào cũng tự động tạo giá trị pháp lý.

## 3. Những điều MAC không chứng minh

| Khẳng định thường gặp | Có được MAC chứng minh không? | Lý do |
| --- | --- | --- |
| “Thông điệp này khớp với một tag hợp lệ theo khóa K.” | **Có, nếu kiểm tra chính xác.** | MAC kiểm tra sự ràng buộc giữa K, byte thông điệp và tag. |
| “Dữ liệu được bảo vệ không bị thay đổi bởi người không biết K.” | **Có, trong giả định an toàn của MAC.** | Thay byte làm tag cũ không còn hợp lệ với xác suất áp đảo. |
| “Chính Alice, chứ không phải Bob, đã tạo tag.” | **Không.** | Alice và Bob đều biết K, đều có thể tạo tag. |
| “Alice không thể chối đã gửi thông điệp.” | **Không.** | Một bên cùng nắm K có thể tạo bằng chứng giả tương đương. |
| “Nội dung được giữ bí mật.” | **Không.** | MAC không mã hóa plaintext; cần encryption/TLS khi cần bí mật. |
| “Đây là yêu cầu mới, chưa từng gửi.” | **Không.** | Cặp M, T hợp lệ có thể bị phát lại nguyên vẹn. |
| “Dữ liệu được gửi đúng thứ tự và đúng thời điểm.” | **Không.** | MAC không tự có đồng hồ, số thứ tự hoặc trạng thái giao thức. |
| “Người gửi được phép thực hiện nghiệp vụ này.” | **Không.** | Xác thực thông điệp không thay thế authorization, policy và kiểm tra tài nguyên. |
| “Nội dung là thật, đúng nghiệp vụ và không có lỗi.” | **Không.** | Một bên biết K vẫn có thể gửi dữ liệu sai hoặc gian lận. |
| “Khóa chưa bao giờ bị lộ.” | **Không.** | MAC hợp lệ không nói trạng thái bảo mật của K; khóa lộ cho phép giả mạo. |

**Vì vậy, hãy luôn gọi đúng tên bảo đảm:** MAC hỗ trợ toàn vẹn thông điệp và xác thực bên **sở hữu khóa chung**. Nó không tự chứng minh danh tính duy nhất của người tạo, sự mới mẻ của yêu cầu hay tính đúng đắn của nghiệp vụ.

## 4. Điều kiện tiên quyết để tin kết quả MAC

Không nên diễn giải Verify = true độc lập với hệ thống. Ít nhất các điều kiện sau phải được xác minh:

1. **K thực sự bí mật và đủ mạnh.** Khóa cần được tạo từ nguồn ngẫu nhiên mật mã an toàn (hoặc KDF được thiết kế cho mục tiêu phù hợp), không hardcode vào source, không in trong log, không chia sẻ cho nhiều chủ thể vượt phạm vi tin cậy.
2. **Thuật toán và tham số an toàn.** Chọn MAC được nghiên cứu, chẳng hạn HMAC-SHA-256, với tag đủ dài và thuật toán được cố định bởi giao thức; không tạo MAC bằng cách tự nối secret với thông điệp rồi hash.
3. **Hai bên MAC cùng một chuỗi byte.** Charset, thứ tự trường, phép chuẩn hóa, header, đường dẫn, phương thức HTTP và body phải được xác định chính xác. Byte khác làm tag khác.
4. **Đã bảo vệ mọi trường ảnh hưởng đến ý nghĩa yêu cầu.** Ví dụ operation, path, tenant, user, amount, currency, recipient, payload version, request ID và timestamp nếu cần.
5. **Tag được kiểm tra trước khi thực hiện thao tác có tác dụng.** Xác minh thất bại phải từ chối xử lý. Không chấp nhận request rồi mới ghi lỗi MAC.
6. **Đã có cơ chế chống phát lại khi nghiệp vụ yêu cầu.** Một MAC hợp lệ cũ vẫn có thể hợp lệ hôm nay nếu hệ thống không kiểm tra timestamp/nonce/sequence.
7. **Kiểm tra quyền nghiệp vụ độc lập.** Bên sở hữu khóa K có thể được phép gọi API, nhưng vẫn có thể bị cấm chuyển tiền từ tài khoản cụ thể hoặc đọc dữ liệu của tenant khác.
8. **Biết phạm vi các bên đang dùng K.** Nếu nhiều dịch vụ dùng chung một khóa, MAC chỉ chứng minh chủ thể thuộc **nhóm giữ K**, không quy về một dịch vụ riêng.

Trong mô hình bảo mật tiêu chuẩn, một MAC an toàn thường được kỳ vọng chống **giả mạo tag cho thông điệp mới ngay cả khi kẻ tấn công từng thấy các tag hợp lệ** (được gọi là unforgeability under chosen-message attack). Đây không phải lời hứa tuyệt đối với mọi hệ thống: dùng khóa yếu, xử lý sai byte đầu vào hoặc lộ khóa có thể phá toàn bộ mô hình.

## 5. HMAC-SHA-256: MAC thường dùng trong Java

### 5.1 HMAC không phải SHA-256 thuần

**SHA-256** là hàm băm không có khóa: ai biết thông điệp đều có thể tự tính SHA-256(M). Vì vậy gắn một SHA-256 digest công khai vào request **không chứng minh nguồn gốc**; người sửa request chỉ việc tính digest mới.

**HMAC-SHA-256** dùng một **khóa bí mật K** kết hợp với SHA-256 theo cấu trúc HMAC chuyên dụng, nên chỉ các bên có K mới dự kiến tạo được tag hợp lệ cho thông điệp mới. Về trực giác:

~~~text
SHA-256(M)          : ai có M đều tính được.
HMAC-SHA-256(K, M)  : cần có K để tính đúng tag.
~~~

Cấu trúc khái niệm của HMAC:

~~~text
HMAC(K, M) = H( (K' XOR opad) || H( (K' XOR ipad) || M ) )
~~~

Trong đó H là hash bên dưới, K' là khóa được chuẩn bị theo kích thước block, ipad/opad là hai hằng theo định nghĩa HMAC và || là phép nối byte. **Không tự triển khai cấu trúc này** cho ứng dụng: Java đã có Mac của JCA/JCE.

Không thay HMAC bằng các mẫu tự chế như SHA256(K || M). Đặc biệt khi dùng hash cấu trúc Merkle–Damgård, cách nối khóa trước thông điệp có thể chịu tấn công length extension trong những thiết kế phổ biến. HMAC được xây dựng để tránh các sai lầm này.

### 5.2 API Java 17+

Java cung cấp:

- **javax.crypto.Mac**: khởi tạo thuật toán, cấu hình khóa, nhận byte và tạo tag.
- **javax.crypto.KeyGenerator**: sinh khóa cho thuật toán HMAC khi provider hỗ trợ.
- **javax.crypto.SecretKey**: kiểu biểu diễn khóa đối xứng.
- **javax.crypto.spec.SecretKeySpec**: bao bọc key bytes đã có nếu ứng dụng nhận khóa hợp lệ từ hệ thống quản lý khóa.
- **java.security.MessageDigest.isEqual**: so sánh hai mảng byte digest/tag theo cơ chế tránh phụ thuộc vào nội dung, thích hợp hơn phép so sánh thông thường cho tag.

Tên thuật toán chuẩn thường dùng trong JCA là **HmacSHA256**; HMAC-SHA-256 cho tag đầy đủ **32 byte (256 bit)**. Khi truyền dưới dạng text, tag có thể được biểu diễn bằng Base64 hoặc hex. Việc đổi sang Base64/hex chỉ để tương thích giao thức; **khóa K không được xuất ra text hay gửi kèm thông điệp**.

Một đối tượng **Mac có trạng thái và không nên dùng chung đồng thời giữa các luồng** nếu không có cách đồng bộ/quản lý riêng. Mỗi thao tác có thể tạo một instance mới, hoặc dùng cơ chế quản lý instance an toàn cho mỗi thread/request.

## 6. Ví dụ Java 17+: hai bên cùng có khóa, kiểm tra sửa đổi và phát lại

Ví dụ dùng **KeyGenerator** tạo khóa HMAC 256 bit cho một lần chạy; biến sharedKey tượng trưng cho khóa mà Alice và Bob đã trao đổi qua kênh an toàn từ trước. Trong hệ thống thật, cả hai tiến trình phải nhận **cùng khóa một cách an toàn** từ KMS/secret manager hoặc giao thức phân phối khóa; KeyGenerator chạy riêng trên hai tiến trình sẽ sinh **hai khóa khác nhau** và không thể xác thực lẫn nhau.

Tạo tệp **SharedKeyMacDemo.java** (UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class SharedKeyMacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TAG_BYTES = 32;

    private static byte[] mac(SecretKey key, byte[] message)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance(ALGORITHM);
        hmac.init(key);
        return hmac.doFinal(message);
    }

    private static boolean verify(SecretKey key, byte[] message,
                                  byte[] receivedTag)
            throws GeneralSecurityException {
        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }

        byte[] expectedTag = mac(key, message);
        return MessageDigest.isEqual(expectedTag, receivedTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance(ALGORITHM);
        generator.init(256);
        SecretKey sharedKey = generator.generateKey();

        // Trong ví dụ, cả Alice và Bob dùng cùng sharedKey.
        byte[] original = "amount=100|currency=VND"
                .getBytes(StandardCharsets.UTF_8);
        byte[] modified = "amount=900|currency=VND"
                .getBytes(StandardCharsets.UTF_8);

        // Alice tính tag và gửi original + aliceTag.
        byte[] aliceTag = mac(sharedKey, original);

        // Bob dùng cùng khóa để kiểm tra.
        System.out.println("Bob kiểm tra bản gốc: "
                + verify(sharedKey, original, aliceTag));

        // Người trên mạng thay 100 bằng 900, nhưng không có khóa.
        System.out.println("Bob kiểm tra bản sửa: "
                + verify(sharedKey, modified, aliceTag));

        // Bob cũng có thể tự tạo đúng tag cho cùng byte thông điệp.
        byte[] bobTag = mac(sharedKey, original);
        System.out.println("Bob có thể tạo cùng tag: "
                + MessageDigest.isEqual(aliceTag, bobTag));

        // MAC không lưu trạng thái: phát lại nguyên thông điệp vẫn hợp lệ.
        System.out.println("Phát lại vẫn hợp lệ theo MAC: "
                + verify(sharedKey, original, aliceTag));

        // Tag có thể đóng gói dạng text; không hề chứa khóa K.
        String encodedTag = Base64.getEncoder().encodeToString(aliceTag);
        System.out.println("Độ dài tag byte: " + aliceTag.length);
        System.out.println("Độ dài Base64: " + encodedTag.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SharedKeyMacDemo.java
java SharedKeyMacDemo
~~~

Kết quả thông thường của Java 17+:

~~~text
Bob kiểm tra bản gốc: true
Bob kiểm tra bản sửa: false
Bob có thể tạo cùng tag: true
Phát lại vẫn hợp lệ theo MAC: true
Độ dài tag byte: 32
Độ dài Base64: 44
~~~

Giải thích theo từng kết quả:

1. **Bản gốc hợp lệ:** Bob tính lại HMAC(K, original) bằng cùng K nên tag khớp.
2. **Bản sửa bị từ chối:** đổi một byte có thể làm tag khác; với HMAC-SHA-256 an toàn, xác suất một thông điệp sửa đổi vô tình có cùng tag là cực nhỏ.
3. **Bob tạo được tag giống Alice:** đây chính là lý do **không thể suy ra ai là người tạo tag chỉ từ bằng chứng MAC**.
4. **Phát lại hợp lệ về mặt MAC:** MAC tất định cho cùng K và M không có bộ nhớ về lần đã được sử dụng. Hệ thống cần quy tắc freshness/nonce/sequence bên ngoài.
5. **32 byte và 44 ký tự:** đó là byte tag và cách biểu diễn Base64 có padding; Base64 không phải bằng chứng an toàn hay khóa bí mật.

Ví dụ dùng payload văn bản đơn giản để dễ quan sát, **không phải định dạng request xác thực đủ an toàn cho sản xuất**: còn cần canonicalization, scope, thời gian, nonce, chống phát lại, quyền và chính sách lưu khóa. Chương trình không ghi hoặc hiển thị key bytes.

**Về tính xác thực kết quả:** các dòng true/false dựa trên cùng khóa và byte hoặc byte đã sửa; một trường hợp HMAC va chạm với thông điệp sửa là cực kỳ khó xảy ra về mặt mật mã. Giá trị tag Base64 cụ thể thay đổi giữa các lần chạy vì khóa được tạo ngẫu nhiên, nên ví dụ chỉ in **độ dài** của tag, không khẳng định tag cụ thể.

## 7. HMAC kiểm tra byte, không kiểm tra “ý nghĩa”

### 7.1 Vấn đề ghép trường nhập nhằng

Hãy xem hai bộ trường:

~~~text
Bộ 1: user="ab", action="c"
Bộ 2: user="a",  action="bc"
~~~

Nếu cả hai phía tạo message bằng phép nối thẳng **user + action**, thì hai bộ đều trở thành **abc**. MAC vẫn đúng với byte **abc**, nhưng không phân biệt được hai cách phân tách trường. Đây là lỗi **biểu diễn dữ liệu để xác thực**, không phải lỗi thuật toán HMAC.

Cách phòng tránh:

- Dùng định dạng có **độ dài từng trường**, tag kiểu rõ ràng hoặc serializer có canonicalization và schema được thỏa thuận.
- Khóa chặt **phiên bản giao thức** để hai bên dùng cùng cách diễn giải.
- Bảo vệ **mọi trường có thể đổi ý nghĩa hoặc quyền**: method, path, query, body, tenant, user ID, amount, currency, recipient, timestamp, nonce và operation type khi phù hợp.
- Phân biệt rõ các miền dùng khóa hoặc thông điệp, ví dụ yêu cầu và phản hồi. Khi chia sẻ khóa cho nhiều mục đích, nên dùng **khóa riêng** cho từng mục đích hoặc cơ chế phân tách miền (domain separation) được thiết kế rõ.

Ví dụ cấu trúc đầu vào MAC theo giao thức:

~~~text
version = 1
context = "payment-request"
method = "POST"
path = "/v1/payments"
timestamp = "1730000000"
nonce = "request-unique-id"
bodySha256 = SHA-256(rawBodyBytes)

MAC_input =
    encodeWithLengths(version, context, method, path,
                      timestamp, nonce, bodySha256)
tag = HMAC-SHA-256(K, MAC_input)
~~~

Đây là **mô tả thuật toán đóng gói**, không phải mã Java độc lập và không phải tiêu chuẩn giao thức cụ thể. Hàm encodeWithLengths phải được **định nghĩa một cách duy nhất cho cả hai bên**. Cách lấy path/query, encode Unicode, header, body và timestamp phải được thỏa thuận trước, không tùy ý thay đổi sau khi triển khai.

Nếu MAC dựa trên raw HTTP body, verifier cần xác thực **chính các byte body mà bên gửi đã MAC**. Parse JSON rồi serialize lại tùy thư viện có thể đổi thứ tự key, khoảng trắng hoặc biểu diễn số và gây sai tag. Nếu muốn ký nội dung đã chuẩn hóa, chọn một **quy tắc canonical JSON có đặc tả** dùng nhất quán ở cả hai phía.

### 7.2 Thứ tự xác minh và kiểm soát đầu vào

Một quy trình nhận request hợp lý:

1. Giới hạn kích thước request và đọc các trường metadata tối thiểu cần thiết.
2. Xác định key ID/thuật toán **chỉ từ danh sách được phép**; dữ liệu do client gửi không được ép server dùng thuật toán yếu hoặc khóa tùy ý.
3. Tái tạo chính xác byte được bảo vệ theo phiên bản giao thức và thuật toán đã thống nhất.
4. Tính tag kỳ vọng và so sánh với tag nhận được bằng cơ chế an toàn.
5. Kiểm tra cửa sổ thời gian, nonce/sequence hoặc idempotency theo chính sách chống replay; làm bước ghi nhận nonce **nguyên tử** khi có nhiều instance.
6. Kiểm tra danh tính phía gọi và **phân quyền tài nguyên/nghiệp vụ**.
7. Chỉ sau khi các điều kiện cần thiết đạt mới tiến hành tác dụng nghiệp vụ.

Cách sắp xếp bước 4–6 có thể phụ thuộc kiến trúc (ví dụ cần tra cứu khóa theo tenant trước khi xác minh), nhưng yêu cầu bất biến là **không thực thi tác dụng nhạy cảm trước khi các xác minh bắt buộc thành công**. Trả lỗi có kiểm soát; tránh đưa khóa, tag đầy đủ, thông điệp nhạy cảm hoặc payload gốc vào log.

## 8. MAC hợp lệ vẫn có thể bị phát lại

### 8.1 Replay attack

Giả sử Alice gửi:

~~~text
POST /transfer
amount=100
requestId=R1
tag=HMAC(K, protectedRequestBytes)
~~~

Kẻ tấn công không sửa gì, chỉ **ghi lại rồi gửi lại nguyên request và tag**. Bob vẫn tính đúng tag. Nếu nghiệp vụ chuyển tiền chạy hai lần, MAC đã làm đúng công việc của nó nhưng **giao thức chưa có cơ chế nhận biết yêu cầu cũ**.

Những biện pháp bổ sung thường phối hợp:

- **Timestamp được MAC bảo vệ:** giới hạn tuổi yêu cầu, ví dụ vài phút tùy môi trường và sai lệch đồng hồ cho phép. Timestamp chỉ hữu ích khi server **thực sự kiểm tra giới hạn thời gian**.
- **Nonce hoặc request ID duy nhất được MAC bảo vệ:** server nhớ nonce đã xử lý trong cửa sổ chống replay và từ chối sử dụng lại. Việc ghi nhận phải an toàn giữa nhiều server, tránh hai request chạy song song cùng được chấp nhận.
- **Sequence number:** phù hợp một phiên hoặc kênh có thứ tự; cần trạng thái và xử lý mất gói/khôi phục.
- **Idempotency key và ràng buộc nghiệp vụ:** đặc biệt với thanh toán, lặp lại cùng request ID không được thực hiện giao dịch lần hai. Cần lưu kết quả/khóa idempotency theo chính sách.

**Chỉ đưa timestamp hoặc nonce vào chuỗi MAC mà không kiểm tra tính mới/trùng lặp vẫn chưa chống replay.** Tương tự, MAC thành công không cho biết thông điệp đã được xử lý trước đó hay chưa.

### 8.2 Chống replay không thể thay quyền hạn

Một request mới, hợp lệ theo K và nonce, vẫn có thể yêu cầu truy cập tài khoản không thuộc về client. MAC bảo vệ nguyên vẹn yêu cầu đó, nhưng **authorization** phải từ chối. Trên API, không được xem “biết khóa” là quyền vô hạn với mọi tài nguyên.

## 9. Vì sao “ai giữ khóa” quyết định khả năng quy trách nhiệm?

### 9.1 Chỉ Alice và Bob giữ K

Bob nhận được tag hợp lệ: trong một quy trình mà Bob chắc chắn anh ấy không tạo request, K không bị lộ và không có bên thứ ba giữ K, Bob có thể dùng tag làm **cơ sở xác thực đối tác trong hệ thống**. Nhưng khi xảy ra tranh chấp, Bob không thể chứng minh cho người ngoài rằng chính Alice tạo tag vì Bob có cùng năng lực tạo bằng chứng.

**Đây là sự khác nhau giữa xác thực vận hành và chứng minh công khai.**

### 9.2 Một nhóm dịch vụ cùng giữ K

Nếu các dịch vụ A, B, C và D cùng dùng K, mọi dịch vụ đều tạo được tag hợp lệ. Nhận một tag chỉ cho phép nói rằng **một người nắm K** đã tạo nó (trong giả định chưa lộ khóa). Không thể quy chính xác cho A mà chỉ dựa trên tag.

Thiết kế tốt hơn khi cần phân biệt dịch vụ: dùng **khóa riêng theo từng client/service hoặc cặp quan hệ tin cậy**, key ID gắn với danh tính và quyền rõ ràng; không cấp khóa của client này cho client khác. Tuy nhiên, máy chủ verifier giữ cùng khóa với một client vẫn có khả năng tạo tag của client đó: MAC hai chiều **vẫn không tạo chống chối bỏ trước bên thứ ba**.

### 9.3 K bị đánh cắp hoặc người giữ khóa bị chiếm quyền

Nếu K bị lộ, kẻ tấn công tạo được MAC hợp lệ và có thể mạo danh bất kỳ chủ thể nào được hệ thống đồng nhất với K. Verifier không phát hiện điều này chỉ bằng phép so sánh tag. Khi có nghi ngờ lộ khóa, cần thu hồi, luân chuyển khóa, hạn chế quyền, rà soát request và sự cố.

Các bản ghi log và audit đáng tin có thể bổ sung điều tra (thời điểm, máy chủ, mTLS identity, request ID, luồng phân quyền), nhưng **log do cùng bên nắm khóa kiểm soát không tự biến MAC thành chứng cứ chống chối bỏ**.

## 10. MAC, hash, chữ ký số, AEAD và TLS: dùng đúng mục đích

| Cơ chế | Khóa và bên kiểm tra | Điều cung cấp chính | Điều không tự cung cấp |
| --- | --- | --- | --- |
| **SHA-256 thuần** | Không có khóa; ai cũng tính được | Digest để kiểm tra trùng/đối chiếu theo ngữ cảnh | Không xác thực nguồn gốc trước đối thủ có thể sửa dữ liệu và tính lại hash |
| **HMAC-SHA-256** | Các bên cùng giữ khóa bí mật | Toàn vẹn và xác thực thông điệp theo khóa chung | Không giữ bí mật, không phân biệt chính xác từng chủ thể giữ khóa, không chống replay |
| **Chữ ký số** (ví dụ Ed25519, RSA-PSS) | Người ký giữ private key, người kiểm tra dùng public key | Xác thực theo private key được gắn với danh tính, xác minh công khai | Không tự giữ bí mật; cần quản lý trust/danh tính/khóa, kiểm tra freshness theo ứng dụng |
| **AEAD** (ví dụ AES-GCM) | Bên mã hóa/giải mã dùng khóa đối xứng | Bí mật dữ liệu và xác thực toàn vẹn của ciphertext/AAD | Không chứng minh bên nào giữ khóa đã tạo bản mã; không tự chống replay |
| **TLS** | Thỏa thuận khóa phiên, xác thực đầu cuối theo cấu hình | Bảo vệ lưu lượng trong từng kết nối TLS | Không bảo vệ tự động dữ liệu sau khi kết thúc TLS ở proxy, log, DB hoặc hệ thống downstream |

Một request qua HTTPS có thể vẫn cần HMAC ứng dụng nếu hệ thống muốn xác thực **payload độc lập với kết nối** giữa các bên/qua nhiều trung gian. Ngược lại, HMAC ứng dụng **không thay thế TLS** khi payload hoặc credential cần giữ bí mật và cần xác thực kênh truyền.

Đối với dữ liệu cần vừa bí mật vừa toàn vẹn, ưu tiên **AEAD với giao thức được thiết kế đúng**. Không tự chế cơ chế phối hợp encryption và MAC tùy tiện hoặc dùng một key cho nhiều mục đích mà không đánh giá an toàn.

## 11. Quản lý khóa chung trong ứng dụng Java

### 11.1 Phân phối và giới hạn phạm vi khóa

Dùng **SecureRandom/KeyGenerator** hoặc hệ thống KMS/HSM phù hợp để tạo key bytes có entropy cao, với chính sách độ dài phù hợp. Cả hai bên cần nhận cùng K thông qua kênh bí mật có xác thực hoặc được cấp quyền sử dụng khóa qua dịch vụ quản lý khóa. Không đưa K vào URL, frontend, repository, artifact, image container, log, trace hay file cấu hình công khai.

Dùng **khóa riêng theo môi trường**, client/service và mục đích. Không tái sử dụng cùng khóa HMAC cho tất cả tenant, tất cả hệ thống và mọi vai trò. Nếu cần dẫn xuất nhiều khóa từ một secret gốc, dùng KDF được thiết kế cho dẫn xuất và ngữ cảnh phân tách khóa, ví dụ HKDF theo kiến trúc phù hợp.

**Key ID** (định danh khóa không bí mật) có thể đi cùng request để verifier chọn đúng khóa. Key ID phải nằm trong vùng kiểm soát của server, gắn với quyền/tenant và không trở thành cơ chế cho phép client tự yêu cầu khóa bất kỳ. Đưa những định danh ảnh hưởng ngữ nghĩa vào nội dung được xác thực khi giao thức yêu cầu để chống nhầm khóa hoặc nhầm ngữ cảnh.

### 11.2 Rotation, thời hạn và audit

- Định kỳ đổi khóa theo chính sách hoặc ngay khi nghi lộ; tránh dùng một khóa vô thời hạn.
- Khi luân chuyển, xác định thời gian cho phép key cũ, liên kết key ID với key hiện hành và key hết hạn.
- Tránh chấp nhận thuật toán yếu chỉ để tương thích ngược; danh sách thuật toán được server kiểm soát.
- Giám sát nhiều lần xác minh thất bại, replay và dùng khóa không đúng quyền. Nhật ký nên chứa **metadata cần thiết, đã lọc dữ liệu nhạy cảm**, không chứa secret hoặc toàn bộ payload nếu không cần.
- Thu hồi quyền của bên đã bị compromise; nếu nhiều bên dùng một K, sự cố của **một bên có thể buộc đổi khóa cho toàn nhóm**.
- Quy trình phục hồi cần đảm bảo hai bên không vô tình dùng key ID giống nhau nhưng trỏ tới key bytes khác nhau.

### 11.3 Thực hành JCA/JCE và so sánh tag

**MessageDigest.isEqual(expectedTag, receivedTag)** phù hợp hơn **Arrays.equals** khi so sánh tag vì không dừng sớm dựa trên vị trí byte đầu tiên sai. Vẫn cần:

1. Kiểm tra độ dài tag đúng chuẩn trước khi so sánh (ví dụ 32 byte nếu giao thức dùng HMAC-SHA-256 đầy đủ).
2. Giới hạn độ dài đầu vào trước khi tính HMAC; việc đọc một payload cực lớn vẫn tiêu tốn CPU/bộ nhớ.
3. Không log tag hoặc payload nhạy cảm trong thông báo lỗi. Tag có thể công khai về mặt thiết kế MAC nhưng request có thể chứa secret, PII và metadata nhạy cảm.
4. Xử lý lỗi giải mã Base64/hex của tag đúng cách; reject chuỗi sai alphabet/độ dài và không tự cắt/sửa dữ liệu.
5. Khởi tạo **Mac với key đúng cho từng request**; không chia sẻ instance mutable không đồng bộ giữa threads.
6. Không chấp nhận các biến thể MAC/tag length tùy ý do client tự công bố nếu không được giao thức thiết kế và server cho phép.

Độ dài tag có thể bị cắt ngắn theo một **giao thức được thiết kế và đánh giá rõ ràng**, nhưng việc tự rút tag thành vài byte hoặc chấp nhận mọi prefix sẽ làm tăng xác suất giả mạo. Với bài học này, ví dụ giữ nguyên 32 byte HMAC-SHA-256.

## 12. Những lỗi phổ biến cần nhận ra

1. **“Tag đúng, vậy chắc Alice tạo.”** Không đúng nếu Bob cũng giữ K; Bob tự tạo được tag.
2. **“MAC là một loại chữ ký số chống chối bỏ.”** Không; MAC là xác thực với khóa bí mật đối xứng, còn chữ ký số có khóa ký riêng và khóa kiểm tra công khai.
3. **“MAC che giấu thông tin.”** Không; muốn bí mật cần TLS/encryption thích hợp.
4. **“MAC đúng nghĩa là không bị replay.”** Không; tag cũ vẫn đúng với byte thông điệp cũ.
5. **“Đã ký amount, không cần ký currency/recipient.”** Sai: trường không được bảo vệ có thể bị sửa.
6. **“Dùng SHA256(secret || message) là HMAC.”** Sai: đó là cấu trúc khác, có thể không an toàn; dùng JCA HmacSHA256.
7. **“Đặt cùng khóa cho mọi service giúp dễ quản lý mà vẫn xác định người gửi.”** Sai: khả năng quy trách nhiệm giảm, vùng ảnh hưởng khi lộ khóa tăng.
8. **“Tag là Base64 thì khó giả mạo vì khó đọc.”** Sai: Base64 chỉ đổi biểu diễn, sức mạnh đến từ HMAC và khóa bí mật.
9. **“Hai bên hiểu JSON giống nhau thì byte MAC chắc chắn giống.”** Sai: thứ tự field, khoảng trắng, encoding, biểu diễn số và chuẩn hóa Unicode có thể khác.
10. **“Dùng Arrays.equals là đủ cho mọi ứng dụng bảo mật.”** Không nên; so sánh tag bằng cơ chế chống phụ thuộc nội dung như MessageDigest.isEqual và kiểm tra độ dài cố định.
11. **“MAC hợp lệ đồng nghĩa user được thực hiện mọi thao tác.”** Sai: authorization phải đánh giá quyền theo ngữ cảnh nghiệp vụ.
12. **“Không cần đổi khóa dù một client dùng K đã bị xâm nhập.”** Sai: mọi chủ thể có K đều có khả năng tạo tag hợp lệ; sự cố phải dẫn đến đánh giá thu hồi/rotation và tác động hệ thống.

## 13. Tình huống phân tích

### Tình huống A — Hai bên tranh chấp người tạo yêu cầu

Alice và Bob dùng K giống nhau. Bob đưa ra một request và tag hợp lệ rồi tuyên bố “Alice chắc chắn tạo request này”. Bằng chứng đó không đủ vì **Bob có thể tự tính MAC(K, request)**. Trong hệ thống nội bộ Bob vẫn có thể dùng MAC để lọc request giả từ người **không biết K**, nhưng không thể nâng nó thành chứng cứ độc lập rằng Alice là tác giả.

### Tình huống B — Webhook thanh toán

Nhà cung cấp gửi webhook kèm HMAC(K, canonicalRequest). Server xác minh thành công rồi xử lý thanh toán. Một kẻ khác ghi lại webhook thật và gửi lại. HMAC vẫn thành công vì cặp request/tag không đổi. Cách sửa là ràng buộc và **kiểm tra** event ID, thời gian, nonce/idempotency, đồng thời bảo vệ các trường này trong MAC input; server xử lý idempotently để tránh phát sinh giao dịch lặp.

### Tình huống C — Hai tenant dùng chung một khóa

Tenant A và tenant B cùng được cấp K. Nếu tenant A tạo tag cho request với tenantId=B, phía nhận có thể thấy MAC hợp lệ. Nếu server không kiểm tra quyền tenant hoặc không có khóa riêng, MAC **không phân biệt được** A/B. Cần khóa theo tenant/client và kiểm tra authorization; ký MAC cả tenantId cũng **không đủ** nếu cả hai vẫn có cùng K và được phép lựa chọn tenantId tùy ý.

### Tình huống D — Proxy biến đổi request

Alice tính tag trên byte JSON gốc; proxy parse rồi xuất lại JSON với thứ tự thuộc tính khác. Bob tính HMAC trên byte mới và thấy sai tag, dù object JSON về mặt logic có thể tương đương. Hãy quy định ký raw bytes đầu vào hoặc một chuẩn canonical được cả hai phía đồng ý; tránh tự loại bỏ những trường hoặc ký tự ảnh hưởng tới ý nghĩa nghiệp vụ.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Nếu Bob xác minh HMAC(K, M) thành công, điều gì được bảo đảm trong mô hình K bí mật?

**Trả lời:** tag đúng theo K và chính xác những byte M đã được bảo vệ; đối thủ không có K không dễ tạo tag cho dữ liệu mới. Không biết duy nhất người tạo khi nhiều bên có K.

**Câu 2.** Vì sao Bob không thể đem MAC làm bằng chứng pháp lý thuần túy rằng Alice đã ký một thông điệp?

**Trả lời:** Bob cũng biết K nên có thể tạo thông điệp và tag tương tự. Bằng chứng MAC không có tính xác minh công khai phân biệt người tạo.

**Câu 3.** Nếu kẻ tấn công sửa 100 thành 900 trong thông điệp, MAC có phát hiện không?

**Trả lời:** Có, **nếu số tiền nằm trong byte được bảo vệ** và K không bị lộ; xác suất giả mạo thành công với HMAC an toàn là cực nhỏ.

**Câu 4.** Nếu kẻ tấn công phát lại nguyên thông điệp và tag thì sao?

**Trả lời:** MAC vẫn hợp lệ. Muốn từ chối replay, hệ thống phải kiểm tra timestamp, nonce/sequence, idempotency hoặc trạng thái nghiệp vụ.

**Câu 5.** SHA-256(M) khác HMAC-SHA-256(K, M) thế nào?

**Trả lời:** SHA-256 không cần khóa, ai có M cũng tính được; HMAC dùng K bí mật nên cung cấp xác thực theo khóa chung.

**Câu 6.** Gửi tag dưới dạng Base64 có làm MAC an toàn hơn không?

**Trả lời:** Không. Base64 chỉ biểu diễn tag dạng text; an toàn đến từ HMAC, key management, phạm vi dữ liệu được bảo vệ và verification đúng.

**Câu 7.** Nếu Alice, Bob, Carol cùng chia sẻ K, Bob có thể biết chính Alice gửi tag không?

**Trả lời:** Không thể từ MAC đơn lẻ. Tag chỉ phù hợp với việc một bên biết K đã tạo; cần chia khóa theo danh tính và bổ sung cơ chế định danh/xác thực phù hợp.

**Câu 8.** Tag hợp lệ có cho phép truy cập tài khoản của người khác không?

**Trả lời:** Không. Authorization độc lập phải xác minh quyền thao tác trên tài nguyên và ranh giới tenant.

**Câu 9.** Vì sao phải MAC những byte đã chuẩn hóa theo một quy tắc rõ ràng?

**Trả lời:** HMAC chỉ biết byte. Dữ liệu logic giống nhau nhưng serialize khác cho tag khác; phép ghép nhập nhằng còn cho phép những tập field khác nhau dẫn đến cùng byte được ký.

**Câu 10.** Khi nào cân nhắc chữ ký số thay vì MAC?

**Trả lời:** Khi cần người kiểm tra **không giữ quyền tạo chữ ký** và có thể xác minh theo public key của người ký, phục vụ mô hình quy trách nhiệm mạnh hơn; vẫn phải quản lý danh tính và private key đúng cách.

---

**Ghi nhớ:** Trong hệ thống hai bên chia sẻ một khóa bí mật, MAC cho phép xác minh rằng **thông điệp được bảo vệ phù hợp với khóa đó** và làm cho kẻ không có khóa rất khó giả mạo thông điệp mới. Vì **cả bên gửi lẫn bên nhận đều có thể tự tạo cùng tag**, MAC không một mình chứng minh ai là tác giả và không cung cấp chống chối bỏ. Chống replay, bảo vệ bí mật, phân quyền và quản lý khóa phải được thiết kế bổ sung.
