# SHA-3 – Họ hàm băm mật mã dựa trên cấu trúc sponge

**SHA-3 (Secure Hash Algorithm 3)** là họ **hàm băm mật mã** được chuẩn hóa trong **NIST FIPS 202**. SHA-3 nhận dữ liệu đầu vào có độ dài tùy ý và tạo ra giá trị băm (digest) có độ dài xác định; các biến thể mở rộng SHAKE có thể tạo đầu ra với độ dài được chỉ định. SHA-3 được xây dựng trên họ thiết kế **Keccak** và cấu trúc **sponge**, khác với cấu trúc truyền thống của SHA-2.

Trong chương **Hash và MAC** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, hiểu SHA-3 giúp chọn đúng cơ chế kiểm tra toàn vẹn, phân biệt **hash không có khóa** với **MAC có khóa**, dùng SHA-3 cùng chữ ký số, và bảo vệ vòng đời khóa mật mã từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy. Nội dung còn liên hệ đến AES, mật mã bất đối xứng, KMS/HSM, envelope encryption, phân quyền và kiểm toán.

> **Phân biệt ngay từ đầu:** SHA3-256 là **hàm băm công khai, không dùng khóa bí mật**. Bất kỳ ai biết dữ liệu đều có thể tính cùng digest. Vì thế SHA-3 thuần túy **không thay thế HMAC/KMAC, chữ ký số hay mã hóa dữ liệu**.

## 1. SHA-3 giải quyết bài toán gì?

Hàm băm mật mã biến một thông điệp thành dấu vân tay số. Ví dụ, SHA3-256 luôn tạo ra **256 bit (32 byte)** đầu ra, bất kể dữ liệu là chuỗi vài byte hay một tệp có kích thước lớn.

Một hàm băm mật mã hướng đến ba thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Liên hệ thực tế |
| --- | --- | --- |
| **Kháng tiền ảnh (preimage resistance)** | Biết digest, khó tìm một thông điệp có digest đó. | Không thể coi digest như bản mã có thể giải ngược để lấy dữ liệu. |
| **Kháng tiền ảnh thứ hai (second-preimage resistance)** | Biết thông điệp ban đầu, khó tìm thông điệp khác có cùng digest. | Chống thay tệp đã biết bằng một tệp khác có cùng giá trị băm. |
| **Kháng va chạm (collision resistance)** | Khó tìm bất kỳ hai thông điệp khác nhau có cùng digest. | Cần cho nhiều quy trình ký và kiểm tra tính toàn vẹn. |

**Hai dữ liệu khác nhau về mặt toán học vẫn có thể cho cùng digest**, bởi đầu vào không giới hạn mà đầu ra hữu hạn. “Kháng va chạm” có nghĩa việc tìm được cặp như vậy phải có chi phí tính toán rất lớn theo mô hình an toàn dự kiến, không có nghĩa va chạm tuyệt đối không tồn tại.

Hàm băm còn có hiệu ứng **avalanche**: một thay đổi rất nhỏ ở đầu vào thường làm digest thay đổi đáng kể. Nhưng quan sát hai digest khác nhau **không chứng minh ai** đã thay đổi dữ liệu hoặc dữ liệu vốn do ai tạo ra.

### 1.1. Băm không phải mã hóa

- **Hash:** tính digest một chiều, không dùng khóa để giải mã và khôi phục dữ liệu gốc.
- **Encryption:** biến plaintext thành ciphertext và cần khóa tương ứng để giải mã.
- **MAC:** kết hợp **khóa bí mật chia sẻ** với thông điệp để tạo thẻ xác thực, nhằm phát hiện sửa đổi và xác thực nguồn theo bên có khóa.
- **Digital signature:** dùng **private key để ký**, public key để xác minh; giúp bên xác minh không cần chia sẻ khóa bí mật ký.

SHA3-256 có thể băm dữ liệu trước hoặc trong quá trình ký số theo thuật toán/giao thức phù hợp, nhưng bản thân digest **không phải chữ ký**.

## 2. Các biến thể trong FIPS 202

FIPS 202 chuẩn hóa bốn hàm SHA-3 với đầu ra cố định và hai hàm **SHAKE** có đầu ra mở rộng (**XOF – Extendable-Output Function**).

| Thuật toán | Đầu ra | Mức kháng va chạm lý tưởng (xấp xỉ) | Trường hợp thường gặp |
| --- | ---: | ---: | --- |
| **SHA3-224** | 224 bit | 112 bit | Yêu cầu định dạng digest 224 bit. |
| **SHA3-256** | 256 bit | 128 bit | Digest tệp, dấu vân tay, thành phần giao thức. |
| **SHA3-384** | 384 bit | 192 bit | Giao thức/chính sách yêu cầu digest dài hơn. |
| **SHA3-512** | 512 bit | 256 bit | Quy trình yêu cầu digest 512 bit. |
| **SHAKE128** | Tùy chọn | Phụ thuộc độ dài xuất; mục tiêu mức an toàn đến 128 bit theo thiết kế | Lấy số byte đầu ra theo yêu cầu giao thức. |
| **SHAKE256** | Tùy chọn | Phụ thuộc độ dài xuất; mục tiêu mức an toàn đến 256 bit theo thiết kế | Giao thức cần độ dài đầu ra linh hoạt. |

Với một hàm băm đầu ra **n bit**, công tìm va chạm kiểu birthday attack lý tưởng thường có cấp độ **2^(n/2)**, trong khi tìm tiền ảnh lý tưởng khoảng **2^n** nếu không có giới hạn cấu trúc làm giảm mức an toàn. Đây là trực giác về độ dài digest, không phải cam kết rằng một hệ thống dùng SHA3-512 sẽ có “512 bit an toàn” trong mọi tình huống.

**SHAKE không có một digest dài cố định.** Ví dụ, SHAKE256 xuất 32 byte và SHAKE256 xuất 64 byte có quan hệ theo tính chất XOF; đầu ra dài hơn tiếp tục chuỗi byte, không phải một thuật toán băm khác. Giao thức phải quy định rõ số byte cần lấy, mã định danh thuật toán và cách sử dụng; không được đổi số byte tùy ý giữa các bên.

Các thuật toán mở rộng dựa trên SHA-3 trong **NIST SP 800-185** gồm **cSHAKE**, **KMAC**, **TupleHash** và **ParallelHash**. Trong đó **KMAC** là cơ chế MAC có khóa được thiết kế cho các ứng dụng cần xác thực thông điệp; cần phân biệt với SHA3-256 không khóa.

## 3. SHA-3 khác SHA-2 ở đâu?

SHA-2 (ví dụ SHA-256, SHA-512) và SHA-3 đều là các họ hàm băm chuẩn hóa, hiện được sử dụng rộng rãi khi triển khai đúng. SHA-3 được bổ sung để cung cấp **một cấu trúc thiết kế khác**, tăng lựa chọn và tính đa dạng thuật toán.

| Tiêu chí | SHA-2 | SHA-3 |
| --- | --- | --- |
| Thiết kế nền tảng | Dựa trên hàm nén và cấu trúc băm tương ứng. | **Keccak sponge**, hấp thụ dữ liệu rồi sinh đầu ra. |
| Ví dụ | SHA-256, SHA-384, SHA-512. | SHA3-256, SHA3-384, SHA3-512, SHAKE. |
| Độ dài digest | Theo biến thể cố định. | SHA3-* cố định; **SHAKE** có thể xuất nhiều độ dài. |
| Length extension cổ điển | Một số biến thể như SHA-256 dễ bị khai thác nếu dùng ngây thơ làm MAC kiểu hash(secret || message). | SHA-3 sponge không có lỗi length extension cổ điển theo kiểu đó. |
| Dùng làm MAC | Dùng **HMAC-SHA-256** hoặc cơ chế MAC chuẩn. | Dùng **HMAC-SHA3-256** hoặc **KMAC** theo giao thức phù hợp. |

**Không kết luận SHA-2 đã “bị phá” chỉ vì có SHA-3.** Lựa chọn thường phụ thuộc tiêu chuẩn bảo mật, tính tương thích giao thức, hiệu năng provider, khả năng phần cứng và yêu cầu quản lý thuật toán.

**Không dùng SHA3(secret || message) làm thiết kế MAC tự phát** dù SHA-3 khác SHA-2 về length extension. HMAC và KMAC có định nghĩa rõ ràng, bao gồm xử lý khóa/định dạng và giới hạn an toàn; giao thức tự sáng tạo dễ mắc lỗi khi phân tách miền, nối trường hoặc xác thực metadata.

## 4. Cấu trúc sponge hoạt động như thế nào?

SHA-3 sử dụng một **trạng thái nội bộ 1600 bit** trong Keccak-f[1600]. Trạng thái được chia logic thành:

- **Rate (r):** phần tham gia hấp thụ dữ liệu đầu vào và sinh đầu ra.
- **Capacity (c):** phần còn lại góp vào mức an toàn của cấu trúc; với SHA-3 dùng trạng thái 1600 bit thì **r + c = 1600**.

Thuật toán xử lý dữ liệu theo hai giai đoạn:

1. **Absorb:** thêm phần đệm theo chuẩn và giá trị phân tách miền, chia đầu vào thành các khối phù hợp với rate. Các khối được đưa vào trạng thái với phép XOR và hoán vị Keccak-f[1600].
2. **Squeeze:** rút byte từ trạng thái; nếu cần thêm đầu ra thì tiếp tục hoán vị và rút dữ liệu. Các biến thể SHA3-* dừng sau đủ số bit digest; SHAKE có thể tiếp tục đến độ dài yêu cầu.

~~~mermaid
flowchart LR
    M["Thông điệp đầu vào"] --> PAD["Padding + domain separation"]
    PAD --> BLOCK["Chia khối theo rate r"]
    BLOCK --> ABSORB["Absorb: XOR + Keccak-f[1600]"]
    ABSORB --> SQUEEZE["Squeeze: lấy byte đầu ra"]
    SQUEEZE --> OUT["Digest SHA3-* hoặc đầu ra SHAKE"]
    SQUEEZE --> MORE{"Cần thêm byte?"}
    MORE -->|Có| PERM["Hoán vị trạng thái tiếp"]
    PERM --> SQUEEZE
    MORE -->|Không| STOP["Kết thúc"]
~~~

Ví dụ **SHA3-256** dùng **rate 1088 bit** và **capacity 512 bit**, với đầu ra 256 bit. **SHA3-512** có rate thấp hơn và capacity cao hơn, với digest 512 bit. Không nhầm **độ dài digest** với **rate** hay **capacity**.

**Domain separation** rất quan trọng: cùng một hoán vị Keccak có thể được dùng trong nhiều chức năng, nhưng cách đệm và phân tách miền đảm bảo những hàm chuẩn khác nhau không bị dùng lẫn ngữ nghĩa. Vì vậy **SHA3-256 không cho cùng digest với Keccak-256 thường gặp trong một số hệ sinh thái blockchain** cho cùng đầu vào. Tránh thay một tên thuật toán bằng tên gần giống mà không kiểm tra chuẩn và test vector.

## 5. Ví dụ Java 17: SHA3-256 và HMAC-SHA3-256

Java 17 có API **MessageDigest** cho SHA3-256 qua **Java Cryptography Architecture (JCA)**. Với provider hỗ trợ thuật toán MAC tương ứng, có thể dùng **Mac** và tên **HmacSHA3-256**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class Sha3Example {
    private static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmacSha3(byte[] key, byte[] message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA3-256");
        mac.init(new SecretKeySpec(key, "HmacSHA3-256"));
        return mac.doFinal(message);
    }

    public static void main(String[] args) throws Exception {
        // 1. Băm không khóa: bất kỳ ai có dữ liệu cũng tính được digest.
        byte[] message = utf8("tenant=A;order=123;amount=4200");
        MessageDigest hash = MessageDigest.getInstance("SHA3-256");
        byte[] digest = hash.digest(message);
        System.out.println("SHA3-256: " + HexFormat.of().formatHex(digest));

        // 2. MAC có khóa: dùng bí mật chia sẻ, không dùng digest thường.
        byte[] macKey = new byte[32];
        new SecureRandom().nextBytes(macKey);
        byte[] tag = hmacSha3(macKey, message);

        // Giả lập phía nhận đã lấy tag và thông điệp qua giao thức.
        byte[] receivedTag = tag.clone();
        boolean valid = MessageDigest.isEqual(
                hmacSha3(macKey, message), receivedTag);

        // Thông điệp bị sửa mà giữ tag cũ phải xác thực thất bại.
        byte[] modified = utf8("tenant=A;order=123;amount=9900");
        boolean modifiedValid = MessageDigest.isEqual(
                hmacSha3(macKey, modified), receivedTag);

        System.out.println("Original HMAC valid: " + valid);       // true
        System.out.println("Modified HMAC valid: " + modifiedValid); // false

        // Chỉ xóa bản sao byte[] này, không đảm bảo toàn bộ bản sao trong JVM.
        Arrays.fill(macKey, (byte) 0);
    }
}
~~~

**Giải thích:**

- **MessageDigest.getInstance("SHA3-256")** tính digest không khóa; digest có thể xuất hiện công khai.
- **Mac.getInstance("HmacSHA3-256")** khởi tạo và dùng khóa bí mật để xác thực message. Đây là **HMAC sử dụng SHA3-256**, khác với KMAC dù cùng liên quan SHA-3.
- **MessageDigest.isEqual(...)** giúp so sánh hai chuỗi byte bằng cách tránh nhánh so sánh dừng ngay ở byte sai đầu tiên trong cách dùng thông thường. Tuy nhiên tính an toàn tổng thể còn phụ thuộc nơi khác trong luồng kiểm tra và cách xử lý đầu vào.
- Demo cố ý giữ khóa MAC trong bộ nhớ ứng dụng; sản xuất nên lấy khóa từ hệ thống quản lý bí mật được kiểm soát hoặc dùng KMS/HSM có API MAC tương ứng. **Không log hoặc hard-code khóa**.

**Tương thích:** tên thuật toán có sẵn tùy JDK/provider và cấu hình bảo mật. Khi chọn KMAC/SHAKE, không mặc định mọi provider của Java 17 có sẵn API hoặc tên thuật toán tương ứng; hãy xác minh khả năng hỗ trợ trước khi tích hợp.

### 5.1. Test vector SHA3-256

Một cách kiểm tra cấu hình hoặc triển khai SHA-3 là sử dụng test vector công khai. Với dữ liệu văn bản ASCII **abc** (không có dấu xuống dòng), giá trị SHA3-256 là:

~~~text
Input (UTF-8/ASCII): abc
SHA3-256:
3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532
~~~

Nếu code cho digest khác, cần kiểm tra bytes đầu vào, encoding, ký tự xuống dòng, tên thuật toán và xem có nhầm **SHA-256**, **SHA3-256** hay **Keccak-256** không.

## 6. SHA-3, HMAC và KMAC: chọn đúng mức xác thực

Giả sử dịch vụ A truyền dữ liệu tới dịch vụ B:

- Nếu A chỉ gửi **message + SHA3-256(message)** qua một kênh không xác thực, kẻ tấn công có thể sửa message và **tự tính lại digest**. Digest thường không chứng minh bản tin do A phát hành.
- Nếu A và B **chia sẻ khóa MAC** và xác minh **HMAC-SHA3-256**, bên không biết khóa khó tạo tag hợp lệ cho message đã thay đổi.
- Nếu cần bên thứ ba xác minh công khai mà không biết bí mật chung, dùng **chữ ký số** như Ed25519/RSA-PSS/ECDSA theo giao thức phù hợp.
- Nếu cần **bảo mật nội dung**, dùng **mã hóa có xác thực** như AES-GCM hoặc giải pháp mật mã phù hợp; HMAC/SHA-3 không che giấu plaintext.

| Giải pháp | Có khóa bí mật? | Tính bí mật dữ liệu? | Ai xác minh? | Công dụng |
| --- | --- | --- | --- | --- |
| **SHA3-256** | Không | Không | Bất kỳ ai | Digest, kiểm tra dữ liệu so với digest tin cậy. |
| **HMAC-SHA3-256** | Có, khóa chung | Không | Bên biết khóa chung | Xác thực thông điệp và tính toàn vẹn. |
| **KMAC128/KMAC256** | Có, khóa chung | Không | Bên biết khóa chung | MAC dựa trên Keccak/cSHAKE theo SP 800-185. |
| **Chữ ký số** | Private key để ký | Không | Người có public key đáng tin | Xác minh chữ ký số và nguồn ký. |
| **AES-GCM** | Khóa AES đối xứng | Có | Bên có khóa AES phù hợp | Bảo mật và xác thực bản mã. |

**HMAC với SHA3-256 và KMAC256 không tương thích đầu ra**: đó là hai cơ chế khác nhau. Hai bên giao thức phải thống nhất **tên thuật toán, kích thước tag, định dạng thông điệp, mã định danh khóa và ngữ cảnh xác thực**.

### 6.1. Ràng buộc ngữ cảnh và chống phát lại

Ngay cả HMAC đúng cũng **không tự ngăn replay**: một thông điệp và tag cũ có thể được gửi lại nguyên vẹn và xác minh thành công. Cần thêm **request ID, sequence number, timestamp/expiry, nonce nghiệp vụ** và trạng thái chống xử lý trùng theo chính sách.

Đầu vào MAC phải có **biểu diễn chuẩn, không mơ hồ**. Ví dụ, nếu nối các trường bằng ký tự phân tách mà nội dung trường có thể chứa chính ký tự đó, hai bộ trường có thể tạo cùng chuỗi bytes. Hãy chọn định dạng canonical có quy tắc encoding rõ ràng, prefix độ dài cho các trường hoặc một định dạng cấu trúc được chuẩn hóa.

**Không nhận tenant ID, quyền sở hữu hay key ID từ client rồi dùng tag hợp lệ làm bằng chứng phân quyền.** MAC cho biết bên tạo tag biết khóa tương ứng và bytes đã được xác thực; ứng dụng vẫn phải kiểm tra danh tính caller, quyền đối tượng và hạn sử dụng.

## 7. Vai trò SHA-3 trong hệ thống quản lý khóa

Trong vòng đời khóa mật mã, SHA-3 và các biến thể có thể tham gia nhiều khâu, nhưng cần phân biệt hoạt động **không khóa** và **có khóa**.

### 7.1. Fingerprint của public key

Có thể dùng SHA3-256 tính fingerprint trên **encoding công khai có quy tắc rõ** của public key, ví dụ SPKI DER. Fingerprint là mã nhận diện giúp đối chiếu key pair và phiên bản; **nó không chứng minh khóa thuộc đúng chủ thể** nếu chưa có nguồn phân phối tin cậy hoặc cơ chế xác thực ngoài băng.

Khi thay key pair bất đối xứng, fingerprint mới có thể được đưa vào kiểm kê để đối soát. Đối với chứng chỉ, fingerprint **của chứng chỉ** và fingerprint **của public key** là hai giá trị khác nhau vì bytes được băm khác nhau.

### 7.2. Xác thực metadata và nhật ký kiểm toán

SHA3-256 có thể hỗ trợ phát hiện thay đổi nếu **digest tham chiếu được lưu và bảo vệ bằng nguồn tin cậy**. Ví dụ, sau khi phát hành một gói phần mềm, hệ thống ký một manifest chứa digest SHA3-256 của gói. Người nhận xác minh **chữ ký manifest** rồi mới so khớp digest tệp.

Tự lưu digest ở cùng thư mục mà kẻ tấn công được quyền sửa cả tệp lẫn digest **không đảm bảo tính xác thực**. Đối với audit log, cần cơ chế chống sửa đổi, chữ ký số hoặc MAC theo thiết kế; chỉ băm từng dòng log không ngăn người có quyền ghi thay đổi toàn bộ bản ghi.

### 7.3. KMS/HSM và khóa MAC

**KMS** cung cấp API/policy quản lý khóa; **HSM** có cơ chế phần cứng bảo vệ vật liệu khóa. Hệ thống có thể giữ khóa HMAC/KMAC trong môi trường được phân quyền, nhưng **không mặc định mọi KMS/HSM đều hỗ trợ HMAC-SHA3 hoặc KMAC**. Đặc tả dịch vụ quyết định thuật toán, key usage, khả năng export và API generate/verify MAC có sẵn.

Một ứng dụng có quyền gọi API tạo MAC **vẫn có thể làm giả thông điệp hợp lệ theo chính sách xác thực** dù khóa không thể xuất. Bởi vậy phải bảo vệ cả **quyền sử dụng**, giới hạn tenant, mục đích, tốc độ sử dụng và theo dõi audit.

### 7.4. SHA-3 không thay thế envelope encryption

**Envelope encryption** bảo vệ dữ liệu bằng **DEK đối xứng**, thường AES-GCM, rồi bọc DEK dưới **KEK** trong KMS/HSM. SHA3-256 không mã hóa DEK và không đóng vai trò wrapping key. HMAC/KMAC có thể dùng để xác thực một số metadata hoặc giao thức nếu được thiết kế phù hợp, nhưng không thay cho cơ chế **wrap/unwrap** và mã hóa dữ liệu.

Hệ thống cũng không nên tùy ý lấy SHA3-256(private key || text) để “sinh DEK”. Dẫn xuất khóa phải dùng **KDF chuẩn** phù hợp với loại bí mật đầu vào, ngữ cảnh, độ dài và mô hình bảo mật.

## 8. Quản lý vòng đời khóa HMAC/KMAC

Khác với SHA3-256 thuần túy, **HMAC/KMAC cần khóa bí mật**. Vì vậy khóa MAC phải có vòng đời tương tự các khóa mật mã khác.

| Giai đoạn | Công việc cần làm | Rủi ro nếu thực hiện sai |
| --- | --- | --- |
| **Sinh khóa** | Tạo secret có entropy cao bằng CSPRNG/KMS/HSM; chọn độ dài phù hợp và thuật toán MAC được hỗ trợ. | Khóa yếu, đoán được hoặc sử dụng lại mật khẩu người dùng. |
| **Cấp phát** | Gắn key ID, phiên bản, owner, dịch vụ/tenant, mục đích và chính sách sử dụng. | Dùng chung khóa giữa các tenant, môi trường hoặc chức năng không liên quan. |
| **Lưu trữ** | Dùng kho bí mật/KMS/HSM; giới hạn export, cache, bản sao lưu và quyền đọc. | Lộ secret trong Git, log, cấu hình hoặc dump. |
| **Sử dụng** | Hạn chế quyền generate/verify MAC; dùng canonical message, so sánh tag an toàn và chống replay. | Lạm dụng API ký MAC, vượt quyền hoặc nhận thông điệp cũ. |
| **Xoay vòng** | Sinh khóa mới, phát hành key ID/phiên bản, chuyển phát sinh MAC mới, hỗ trợ xác minh tag cũ có thời hạn. | Gián đoạn hệ thống hoặc chấp nhận MAC cũ lâu hơn cần thiết. |
| **Thu hồi** | Vô hiệu hóa khóa/phiên bản và cập nhật bên xác minh theo mức độ sự cố. | Kẻ tấn công còn được quyền tạo/đưa tag hợp lệ. |
| **Hủy** | Kiểm kê hệ thống, cache, bản sao và thời hạn lưu giữ trước khi xóa vật liệu khóa. | Tag cũ không xác minh được dù vẫn có yêu cầu lưu giữ, hoặc khóa vẫn tồn dư. |

**Không dùng cùng một secret cho mọi mục đích** như HMAC, mã hóa AES và token nghiệp vụ. Nếu cần nhiều khóa, dùng các khóa độc lập hoặc **KDF chuẩn với domain separation rõ ràng**, tránh tái dùng vật liệu bí mật giữa những giao thức có tính chất khác nhau.

Khi xoay khóa MAC từ **M1** sang **M2**, bên gửi có thể bắt đầu dùng M2 sau khi bên nhận đã biết M2 và key ID tương ứng. Trong khoảng chuyển tiếp, bên nhận có thể chấp nhận tag của M1 cho **thông điệp còn hợp lệ** theo thời hạn. Nếu M1 lộ, cần đánh giá từ chối M1 sớm hơn, vô hiệu hóa các phiên bị ảnh hưởng và chấp nhận chi phí chuyển đổi.

Hủy secret M1 khác với việc ngừng dùng M1 để **tạo MAC mới**; kế hoạch lưu giữ và kiểm toán quyết định còn cần xác minh thông điệp lịch sử bằng M1 đến thời điểm nào. Với bài toán bằng chứng lâu dài hoặc xác minh công khai bởi bên thứ ba, cân nhắc **chữ ký số** và lưu bằng chứng tin cậy thay vì phụ thuộc một khóa MAC chia sẻ đã bị hủy.

## 9. Tình huống: bảo vệ sự kiện giữa Order Service và Billing Service

Giả sử **Order Service** tạo sự kiện đơn hàng, **Billing Service** tiếp nhận để lập hóa đơn. Hai dịch vụ cùng thuộc một miền tin cậy và được cấp khóa HMAC theo phiên bản.

1. **Thiết kế khóa:** tạo khóa **MAC-ORDERS-v1** bằng CSPRNG/KMS, giới hạn quyền dùng cho đúng hai dịch vụ hoặc, khi có dịch vụ tạo MAC thay mặt, phân tách quyền generate và verify theo khả năng nền tảng.
2. **Chuẩn hóa dữ liệu:** sự kiện gồm event ID, order ID, amount, currency, issued-at, expiry và version. Dùng định dạng canonical không mơ hồ để tất cả bên tính cùng chuỗi byte.
3. **Tạo tag:** Order Service sử dụng HMAC-SHA3-256, thêm **key ID và algorithm ID** như phần ngữ cảnh được ràng buộc theo giao thức, gửi thông điệp cùng tag. Không gửi secret.
4. **Xác minh:** Billing Service kiểm tra caller, nguồn key ID cho phép, thuật toán đã ghim trong cấu hình, thời hạn và việc event ID đã xử lý hay chưa; sau đó xác minh MAC trước khi ghi sổ.
5. **Xoay vòng:** tạo MAC-ORDERS-v2, cấp phát trước cho bên xác minh rồi chuyển bên gửi sang v2. Giữ khả năng xác minh v1 trong cửa sổ đã công bố nếu chính sách cho phép.
6. **Kiểm toán:** ghi key ID, phiên bản, danh tính dịch vụ, event ID, thời gian, kết quả xác minh và lý do từ chối; không ghi khóa, token bí mật hay thông tin thanh toán nhạy cảm.

**Hai giới hạn cần nhớ:** HMAC không mã hóa amount và thông tin hóa đơn; muốn bảo mật dữ liệu truyền phải có lớp truyền tải hoặc mã hóa thích hợp. Và vì **cả hai dịch vụ đều biết secret**, riêng một tag HMAC không thể chứng minh công khai dịch vụ nào đã tạo tag nếu hai bên cùng có quyền sinh MAC. Nếu cần bằng chứng người ký, dùng chữ ký số và mô hình tin cậy phù hợp.

## 10. Những sai lầm phổ biến

| Sai lầm | Tác động | Cách phòng tránh |
| --- | --- | --- |
| Dùng SHA3-256(message) như thẻ MAC | Kẻ tấn công sửa dữ liệu rồi tính lại hash. | Dùng HMAC/KMAC hoặc chữ ký số theo bài toán. |
| Hash(secret || message) làm MAC tự chế | Thiết kế khó kiểm chứng, có thể lộ lỗi giao thức. | Chọn HMAC-SHA3/KMAC chuẩn. |
| Nhầm SHA3-256 với Keccak-256 hoặc SHA-256 | Digest khác nhau, không thể xác minh chéo. | Ghim tên thuật toán, dùng test vector và kiểm tra encoding. |
| Dùng digest để chứng minh chủ sở hữu public key | Có thể chấp nhận khóa giả có fingerprint tự tạo. | Xác thực nguồn key, chứng chỉ hoặc đối chiếu fingerprint qua kênh tin cậy. |
| Dùng SHA3-256 trực tiếp để lưu mật khẩu | Không có cơ chế memory-hard/chống dò ngoại tuyến phù hợp. | Dùng Argon2id, scrypt hoặc PBKDF2 theo chính sách mật khẩu. |
| Không xác thực các trường ngữ cảnh | Bên khác có thể tráo key ID, tenant hoặc algorithm. | Canonicalize và ràng buộc metadata, kiểm tra chính sách key usage. |
| Chỉ kiểm MAC, không chống replay | Thông điệp cũ hợp lệ có thể được xử lý lại. | Kiểm tra expiry, event ID, sequence number và trạng thái đã xử lý. |
| In secret MAC vào log hoặc hard-code vào mã nguồn | Bị lộ khóa, nhiều message có thể bị làm giả. | KMS/HSM/kho bí mật, giới hạn quyền, kiểm toán và xoay khóa. |
| Chấp nhận thuật toán bất kỳ do client chỉ định | Có thể bypass xác thực hoặc thuật toán không phù hợp. | Ghìm danh sách thuật toán được phép theo giao thức và key ID. |
| Xoay khóa nhưng quên dịch vụ xác minh | Token/sự kiện mới bị từ chối hoặc bản cũ còn được tin quá lâu. | Phân phối khóa mới trước, kế hoạch chuyển tiếp và giám sát. |
| Dùng cùng khóa MAC cho nhiều tenant hoặc API | Sự cố một miền ảnh hưởng miền khác. | Tách khóa theo tenant, mục đích và môi trường. |
| Chọn SHA3-512 nhưng không bảo vệ secret | Tăng kích thước digest không cứu được secret bị lộ. | Bảo vệ cả vật liệu khóa và quyền gọi MAC API. |

## 11. Câu hỏi tự kiểm tra

1. SHA3-256 tạo ra bao nhiêu byte digest? Tại sao digest không phải ciphertext có thể giải mã?
2. Ba thuộc tính preimage, second-preimage và collision resistance khác nhau ở đâu?
3. **SHA3-256** và **Keccak-256** có luôn cho cùng digest không? Vì sao phải chú ý domain separation?
4. SHAKE khác nhóm SHA3-224/256/384/512 ở đặc điểm đầu ra nào?
5. Nếu kẻ tấn công sửa một message và tự băm lại SHA3-256, bên nhận có cách nào nhận biết chỉ bằng digest đó không?
6. Vì sao cần HMAC-SHA3-256 hoặc KMAC thay cho SHA3-256 thông thường để xác thực message?
7. Một MAC hợp lệ có tự ngăn replay hoặc chứng minh quyền truy cập tenant của người gọi không?
8. Khi khóa HMAC bị lộ, cần xử lý những điều gì trong vòng đời khóa?
9. SHA-3 có thay thế AES-GCM, chữ ký số và KEK trong envelope encryption được không?
10. Nếu dùng SHA3-256 làm fingerprint, còn cần cơ chế nào để tin rằng public key thuộc người nhận thật?

**Ghi nhớ:** **SHA-3** là một họ hàm băm mật mã mạnh với cấu trúc **Keccak sponge**, gồm các biến thể digest cố định và SHAKE có đầu ra linh hoạt. **Hash không có khóa giúp tạo dấu vân tay**, còn **HMAC/KMAC có khóa** giúp xác thực thông điệp theo mô hình bí mật chia sẻ. Hệ thống an toàn vẫn cần kết hợp mã hóa đối xứng, chữ ký số, kiểm soát truy cập, chống phát lại, KMS/HSM và quản lý vòng đời khóa có kiểm toán.
