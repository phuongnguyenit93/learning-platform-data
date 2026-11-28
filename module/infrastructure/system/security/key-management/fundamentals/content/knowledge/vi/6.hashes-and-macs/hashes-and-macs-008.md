# MAC key — Khóa bí mật dùng để xác thực thông điệp

## 1. MAC key là gì và vì sao quan trọng?

**MAC key** là khóa bí mật được dùng bởi một thuật toán **Message Authentication Code (MAC)** để tạo và kiểm tra mã xác thực của thông điệp. Bên gửi và bên nhận hợp lệ biết hoặc có quyền sử dụng cùng vật liệu khóa, hoặc các khóa tương ứng theo giao thức đối xứng được thiết kế. Một mã xác thực hợp lệ cho biết thông điệp được tạo bằng khóa được tin cậy và không bị thay đổi trong phạm vi thuật toán, dữ liệu và ngữ cảnh được xác thực.

Ví dụ, một dịch vụ thanh toán gửi webhook về đơn hàng. Nếu chỉ gửi JSON chứa trạng thái đơn hàng, bên thứ ba có thể sửa số tiền, trạng thái hoặc tự tạo yêu cầu giả. Khi hai dịch vụ chia sẻ một **MAC key đủ mạnh**, bên gửi tính HMAC trên nội dung và các trường ngữ cảnh đã quy định; bên nhận tính lại HMAC bằng khóa tương ứng và chỉ chấp nhận thông điệp khi giá trị kiểm tra khớp.

Trong chương **Hash và MAC** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, điều cần hiểu không chỉ là cách gọi hàm HMAC. MAC key phải được tạo đúng, phân phối đến đúng bên, giữ bí mật, giới hạn phạm vi sử dụng, xoay vòng, thu hồi và hủy có kiểm soát. Các cơ chế **KMS/HSM, kiểm soát truy cập, kiểm toán** và đôi khi **envelope encryption** giúp hệ thống thực hiện các công việc đó.

> **Điểm cốt lõi:** MAC key dùng để tạo bằng chứng xác thực **giữa các bên cùng tin cậy bí mật chung**. MAC không mã hóa dữ liệu, không tự xác nhận danh tính của một người gửi cụ thể trong nhóm biết khóa và không tự ngăn việc gửi lại thông điệp cũ.

## 2. MAC key, MAC tag và thông điệp được bảo vệ

Một sơ đồ MAC điển hình có hai phép toán:

~~~text
tag = MAC.Generate(secretKey, messageBytes)

isValid = MAC.Verify(secretKey, messageBytes, receivedTag)
~~~

Trong đó:

| Thuật ngữ | Ý nghĩa | Yêu cầu bảo vệ |
| --- | --- | --- |
| **MAC key** | Bí mật mà thuật toán MAC sử dụng | Phải giữ bí mật, đủ entropy, đúng phạm vi và mục đích |
| **Message bytes** | Chuỗi byte được đưa vào tính MAC | Hai bên phải thống nhất chính xác cách biểu diễn và các trường được bảo vệ |
| **MAC tag** | Kết quả của phép tính MAC | Có thể gửi kèm thông điệp, nhưng phải kiểm tra đúng trước khi chấp nhận |
| **Algorithm / key ID** | Thuật toán và định danh khóa dùng để tính tag | Phải được quản lý, không cho bên không tin cậy tự ý hạ cấu hình |
| **Context** | Mục đích, tenant, phiên bản giao thức, thời gian, nonce nghiệp vụ… | Phải đưa vào phần dữ liệu được MAC xác thực nếu quyết định bảo mật phụ thuộc vào chúng |

~~~mermaid
sequenceDiagram
    participant A as Dịch vụ gửi A
    participant B as Dịch vụ nhận B
    Note over A,B: Đã cấp phát cùng MAC key theo kênh an toàn
    A->>A: tag = HMAC(key, message + context)
    A->>B: message + context + keyId + tag
    B->>B: Xác định keyId hợp lệ và dựng đúng message bytes
    B->>B: expectedTag = HMAC(key, message + context)
    B->>B: So sánh tag an toàn và kiểm tra chống replay
    alt Hợp lệ, chưa dùng lại và đủ quyền
        B-->>A: Chấp nhận
    else Tag sai, quá hạn hoặc trùng request
        B-->>A: Từ chối
    end
~~~

**Vì tag không phải bí mật**, việc đối thủ nhìn thấy tag không làm lộ trực tiếp MAC key khi sơ đồ MAC đủ mạnh và được dùng đúng cách. Nhưng **nếu key bị lộ**, đối thủ có thể tự tạo tag hợp lệ cho thông điệp giả. Bảo vệ MAC key quan trọng không kém việc chọn thuật toán.

### 2.1. Tính toàn vẹn và tính xác thực khác tính bí mật

MAC giúp phát hiện thay đổi thông điệp và chứng minh người tạo tag có khả năng dùng đúng khóa. Nó **không làm plaintext trở nên bí mật**: người quan sát vẫn có thể đọc nội dung JSON hoặc HTTP body nếu không có lớp mã hóa phù hợp như TLS hoặc AEAD.

Nếu cần đồng thời **giữ bí mật và xác thực nội dung**, ưu tiên cơ chế **AEAD** như AES-GCM hoặc ChaCha20-Poly1305 theo giao thức được thiết kế. Trong AEAD, authentication tag là một phần của cơ chế mã hóa có xác thực; ứng dụng không mặc định phải tự thêm một MAC key HMAC bên ngoài.

### 2.2. MAC không phải chữ ký số

Vì cả A và B đều có thể tạo HMAC hợp lệ bằng bí mật chung, khi kiểm tra thành công B chỉ có thể kết luận rằng **một chủ thể có quyền dùng khóa** đã tạo tag. B không thể dùng tag đó như bằng chứng mật mã độc lập rằng chỉ A mới có thể là người ký.

Đối với **chữ ký số**, private key của người ký được giữ bí mật và bên xác minh dùng public key đã được xác thực. Đây là mô hình phù hợp khi cần bên thứ ba xác minh nguồn gốc chữ ký theo chính sách danh tính. MAC thường phù hợp cho giao tiếp dịch vụ đã chia sẻ bí mật và muốn xác thực thông điệp với hiệu năng tốt.

## 3. Phân biệt hash, MAC, chữ ký số và AEAD

| Cơ chế | Có khóa bí mật? | Bảo vệ chính | Có che nội dung? | Ghi chú |
| --- | --- | --- | --- | --- |
| **SHA-256 thông thường** | Không | Tạo giá trị băm, phát hiện thay đổi khi digest gốc được bảo vệ độc lập | Không | Đối thủ sửa message có thể tính lại hash, nên hash đơn thuần không xác thực người gửi |
| **HMAC-SHA-256** | Có: MAC key | Toàn vẹn và xác thực bằng bí mật chung | Không | Các bên giữ cùng bí mật đều có thể tạo tag |
| **AES-CMAC / AES-GMAC** | Có: khóa AES | MAC với tính chất và điều kiện của từng cơ chế | Không | GMAC đòi hỏi nonce/IV đúng quy tắc |
| **Chữ ký số** | Có private key của người ký | Toàn vẹn, xác minh chữ ký bằng public key | Không | Public key phải gắn đúng danh tính người ký |
| **AES-GCM (AEAD)** | Có khóa mã hóa bí mật | Mã hóa + xác thực ciphertext và AAD | **Có**, đối với plaintext được mã hóa | Tag thuộc AEAD; nonce phải được quản lý đúng |

Một phép hash như **SHA-256(message)** không dùng bí mật. Kẻ tấn công thay đổi message có thể tính lại SHA-256 của phiên bản đã sửa. Ngược lại, HMAC dùng khóa bí mật theo một cấu trúc đã được chuẩn hóa để bên ngoài khó tạo tag mới khi không biết khóa.

**Không tự xây MAC bằng cách nối trực tiếp key và message rồi hash**, chẳng hạn SHA-256(key || message) hoặc SHA-256(message || key). Một số cấu trúc đơn giản có thể chịu tấn công phụ thuộc đặc tính hàm băm và cách ghép dữ liệu. Hãy dùng HMAC, CMAC, GMAC, KMAC hoặc cơ chế được chuẩn hóa phù hợp với yêu cầu.

## 4. Những thuật toán MAC sử dụng loại key nào?

### 4.1. HMAC: MAC dựa trên hàm băm

**HMAC (Hash-based Message Authentication Code)** kết hợp một khóa bí mật và hàm băm mật mã theo cấu trúc được định nghĩa, ví dụ **HMAC-SHA-256** hoặc **HMAC-SHA-384**.

Một cách hình dung đơn giản:

~~~text
tag = HMAC-SHA-256(macKey, messageBytes)
~~~

Các điểm cần nhớ:

- HMAC-SHA-256 thường cho **tag đầy đủ 256 bit (32 byte)**; đây là kích thước đầu ra, **không tự quy định MAC key phải dài 256 bit**.
- Với thiết kế mới, khóa HMAC được sinh ngẫu nhiên **256 bit (32 byte)** là một cấu hình phổ biến và dễ quản lý; mức an toàn thật còn phụ thuộc entropy, độ dài tag chấp nhận và cách sử dụng.
- HMAC có quy tắc xử lý khóa dài/ngắn theo chuẩn. Tăng chiều dài khóa vượt mức hợp lý **không tự tăng vô hạn mức độ mạnh**, nhất là khi entropy nguồn không tăng.
- Có thể dùng tag rút gọn **nếu giao thức đã quy định rõ** và đã đánh giá xác suất giả mạo, giới hạn số yêu cầu cùng chính sách bảo mật; không tùy tiện cắt tag để tiết kiệm băng thông.

HMAC thường được dùng trong webhook, xác thực yêu cầu giữa các dịch vụ, KDF và một số giao thức mạng. Tuy cùng xuất hiện trong HKDF, **MAC key phục vụ xác thực thông điệp** và **khóa/PRK dùng trong dẫn xuất khóa** cần được quản lý theo mục đích riêng.

### 4.2. AES-CMAC: MAC dựa trên mã khối

**CMAC (Cipher-based MAC)** có thể sử dụng AES làm primitive bên dưới. Khi đó MAC key là khóa AES với kích thước hợp lệ **128, 192 hoặc 256 bit**, tùy thuật toán/provider/chính sách. AES-CMAC tạo tag có độ dài tối đa bằng kích thước khối AES là **128 bit**, thường được giao thức quyết định cách sử dụng hoặc rút gọn.

Không dùng một khóa AES cho cả **mã hóa dữ liệu** và **CMAC** theo hai mục đích độc lập nếu thiết kế không có cơ chế tách khóa hợp lệ. Ưu tiên khóa riêng hoặc dẫn xuất các khóa con tách mục đích bằng KDF được chuẩn hóa.

### 4.3. AES-GMAC: MAC dùng nền tảng GCM

**GMAC** là trường hợp xác thực thông điệp dựa trên chế độ GCM mà không mã hóa plaintext. MAC key là khóa AES thích hợp, nhưng **nonce/IV là tham số quan trọng** và không phải MAC key.

Đối với GMAC/GCM, việc **tái sử dụng cùng nonce với cùng khóa** có thể dẫn tới phá hủy tính an toàn nghiêm trọng. Không chọn GMAC chỉ vì đã có một khóa AES nếu ứng dụng chưa có cách quản lý nonce đủ tin cậy. Khi chọn thuật toán cần xem giới hạn số lượt sử dụng, quy tắc tạo IV và yêu cầu của tiêu chuẩn đang áp dụng.

### 4.4. Poly1305 và cơ chế dùng một lần

**Poly1305** là một MAC có khóa xác thực một lần. Khi dùng Poly1305 độc lập, phải tuân thủ yêu cầu **không tái sử dụng cùng one-time key** để xác thực các thông điệp khác nhau. Trong **ChaCha20-Poly1305**, khóa Poly1305 cho từng thông điệp được tạo theo cách giao thức quy định từ khóa ChaCha20 và nonce; vì thế nonce cũng cần được quản lý nghiêm ngặt.

Không lấy một chuỗi bí mật cố định rồi tùy tiện dùng nó làm khóa Poly1305 cho mọi thông điệp. Đó là lỗi khác với HMAC, vốn được thiết kế để dùng một khóa bí mật qua nhiều thông điệp trong phạm vi sử dụng hợp lý.

### 4.5. KMAC và các lựa chọn khác

**KMAC** là họ MAC dựa trên cấu trúc SHA-3/cSHAKE và có tham số khóa, độ dài đầu ra, ngữ cảnh theo đặc tả. Hỗ trợ của JDK, provider hoặc KMS/HSM có thể khác với HMAC. Khi chọn thuật toán, cần biết chính xác **họ MAC**, độ dài và loại khóa, tham số, mức an toàn mục tiêu và khả năng tương thích thực tế.

## 5. Chọn MAC key size và tạo khóa an toàn

### 5.1. Key size không đồng nghĩa độ dài tag

| Ví dụ | Kích thước MAC key | Độ dài tag | Điểm cần chú ý |
| --- | --- | --- | --- |
| HMAC-SHA-256 với khóa ngẫu nhiên 32 byte | **256 bit** | Đầy đủ **256 bit** | Hai số có thể bằng nhau ở cấu hình này nhưng giữ vai trò khác nhau |
| HMAC-SHA-256 với khóa ngẫu nhiên 64 byte | **512 bit** | Đầy đủ **256 bit** | Khóa dài hơn không làm digest SHA-256 dài hơn |
| AES-CMAC với AES-128 | **128 bit** | Tối đa **128 bit** | Tag có thể bị rút gọn theo giao thức phù hợp |
| AES-GMAC với AES-256 | **256 bit** | Thường **128 bit** | Còn phải quản lý nonce/IV chính xác |
| Poly1305 độc lập | Khóa một lần theo đặc tả **256 bit** | **128 bit** | Không tái sử dụng one-time key cho nhiều thông điệp |

**Entropy (độ khó đoán)** quan trọng hơn việc một biến có đúng số byte mong muốn. Khóa HMAC 32 byte được sinh bằng **CSPRNG** phù hợp có thể có 256 bit entropy trong mô hình lý tưởng. Nhưng mật khẩu ngắn được đệm thành 32 byte chỉ có mức entropy của mật khẩu ban đầu.

### 5.2. Tạo MAC key thế nào?

Với khóa cấp cho dịch vụ:

1. Chọn thuật toán MAC được hỗ trợ, mức bảo mật mục tiêu và độ dài khóa theo chuẩn/giao thức.
2. Sinh vật liệu khóa bằng **CSPRNG** hoặc **KMS/HSM** có chức năng tương ứng; không dùng timestamp, hàm random thông thường, ID đơn hàng hay chuỗi đoán được.
3. Gắn **key ID, version, algorithm, owner, purpose, trạng thái** và chính sách truy cập.
4. Cấp phát cho đúng workload qua cơ chế xác thực và được bảo vệ; tránh đưa khóa dạng rõ qua email, chat, Git hoặc container image.
5. Giữ khóa tách biệt theo môi trường, đối tác, tenant và mục đích khi cần giới hạn phạm vi sự cố.

Nếu bắt buộc dùng bí mật nguồn là mật khẩu người dùng, cần một **password-based KDF** phù hợp với salt và tham số chống đoán mật khẩu. KDF tăng chi phí tấn công nhưng **không thể bù hoàn toàn entropy yếu**. Đối với giao tiếp server-to-server, thường nên dùng **khóa ngẫu nhiên dài** thay vì mật khẩu do con người chọn.

### 5.3. Tách khóa theo mục đích

Trong cùng hệ thống có thể tồn tại:

- **DEK:** Khóa đối xứng mã hóa dữ liệu, ví dụ AES-GCM.
- **KEK:** Khóa bảo vệ hoặc wrap DEK và có thể bảo vệ cả MAC key theo một thiết kế phù hợp.
- **MAC key:** Bí mật tạo/kiểm tra mã xác thực thông điệp.
- **Private key chữ ký số:** Khóa bất đối xứng tạo chữ ký, khác MAC key dùng chung.
- **Root key:** Khóa cấp cao trong một hệ phân cấp khóa, có thể bảo vệ nhiều khóa khác.

Không dùng một khóa duy nhất làm tất cả các vai trò chỉ để giảm số lượng bí mật phải lưu. Khi một bí mật gốc cần tạo nhiều khóa con, dùng KDF được chuẩn hóa như HKDF với **nhãn mục đích và ngữ cảnh khác nhau**, cùng cơ chế quản lý phiên bản. Việc dẫn xuất khóa vẫn yêu cầu bí mật gốc đủ mạnh và có quy trình thu hồi phù hợp.

~~~mermaid
flowchart TD
    R["Root secret / secret gốc<br/>Bảo vệ nghiêm ngặt"] --> KDF["KDF được chuẩn hóa<br/>Tách miền bằng context"]
    KDF --> M1["MAC key cho webhook partner A"]
    KDF --> M2["MAC key cho webhook partner B"]
    KDF --> E["Encryption key riêng"]
    M1 --> T1["HMAC cho message của A"]
    M2 --> T2["HMAC cho message của B"]
    E --> C["Mã hóa dữ liệu"]
~~~

Sơ đồ chỉ minh họa **domain separation**. Không phải mọi KMS hỗ trợ xuất khóa con từ root secret; cũng không nên tự triển khai cấu trúc khóa nhiều tầng nếu có giao thức/KMS đã đáp ứng yêu cầu.

## 6. Định nghĩa chính xác dữ liệu được MAC xác thực

Một MAC tag chỉ bảo vệ **những byte thật sự đưa vào phép tính**. Nếu bên gửi và bên nhận không thống nhất cách biểu diễn, thông điệp hợp lệ có thể bị từ chối; nguy hiểm hơn, một cấu trúc ghép trường mơ hồ có thể cho phép thay đổi cách hiểu mà vẫn giữ nguyên chuỗi byte.

Ví dụ cách ghép yếu:

~~~text
MAC(key, userId || amount)

userId="12", amount="345" -> "12345"
userId="123", amount="45" -> "12345"
~~~

Hai bộ dữ liệu khác nhau tạo cùng chuỗi đầu vào **vì cách ghép mơ hồ**, dù HMAC không bị phá. Cần dùng định dạng **canonical, không nhập nhằng**: độ dài trường, mã hóa nhị phân có schema, phân tách có quy tắc escaping hoặc chuẩn serialization được hai bên thống nhất.

Khi xác thực HTTP request/webhook nên quyết định rõ:

- **Method, path và query:** Có nằm trong MAC không? Việc mã hóa URL, chữ hoa/thường và thứ tự query được chuẩn hóa thế nào?
- **HTTP body:** Xác thực chính xác byte nhận được hay JSON canonical? Nếu một bên parse rồi serialize lại JSON, khoảng trắng hoặc thứ tự trường có thể làm tag sai.
- **Timestamp và request ID/nonce nghiệp vụ:** Có được MAC cùng message để tránh bị thay đổi không?
- **Tenant, recipient, purpose và API version:** Có được đưa vào dữ liệu xác thực để chống chuyển thông điệp giữa các ngữ cảnh không?
- **Key ID và thuật toán:** Hệ thống xác định bộ khóa và thuật toán theo cấu hình đáng tin cậy nào? Có chấp nhận thuật toán yếu do client yêu cầu không?

**Không chỉ MAC mỗi payload** nếu quyền, số tiền, môi trường hoặc đích nhận được quyết định bởi header/path nằm ngoài payload. Những trường đó cũng cần được xác thực hoặc ràng buộc bằng một cơ chế đáng tin cậy khác.

### 6.1. Tách ngữ cảnh (domain separation)

Nếu một MAC key phải phục vụ nhiều định dạng do ràng buộc hệ thống, nên thiết kế **nhãn mục đích và phiên bản** trong dữ liệu xác thực, chẳng hạn một prefix cố định, duy nhất cho giao thức. Tốt hơn nữa là sử dụng **MAC key riêng cho từng giao thức hoặc mục đích**.

Ví dụ, cùng byte nội dung có thể được dùng ở thông báo hoàn tiền và xác nhận đơn hàng. Nếu cả hai loại sử dụng cùng khóa và cùng thông điệp tính MAC mà không có nhãn loại yêu cầu, tag từ một ngữ cảnh có thể bị diễn giải sai ở ngữ cảnh khác.

## 7. Thực hành Java: tạo và kiểm tra HMAC-SHA-256

Java hỗ trợ HMAC thông qua **Java Cryptography Architecture (JCA)**, với lớp **javax.crypto.Mac**. Ví dụ dưới đây minh họa:

1. Sinh **32 byte ngẫu nhiên** làm MAC key, thay vì lấy từ mật khẩu.
2. Tính **HMAC-SHA-256** trên chính xác các byte của thông điệp, cùng một nhãn ngữ cảnh cố định.
3. Kiểm tra tag đầy đủ bằng **MessageDigest.isEqual** để giảm rủi ro so sánh lệ thuộc vào nội dung.
4. Từ chối thông điệp khi một byte đã bị thay đổi.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

public final class MacKeyDemo {
    private static final byte[] DOMAIN =
            "orders-webhook:v1".getBytes(StandardCharsets.UTF_8);
    private static final int TAG_SIZE_BYTES = 32; // HMAC-SHA-256 đầy đủ

    private MacKeyDemo() {}

    static SecretKey newHmacKey() {
        byte[] raw = new byte[32]; // 256 bit ngẫu nhiên
        new SecureRandom().nextBytes(raw);
        try {
            // SecretKeySpec giữ bản sao các byte của key trong ví dụ này.
            return new SecretKeySpec(raw, "HmacSHA256");
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }

    static byte[] computeTag(SecretKey key, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);

        // Tách ngữ cảnh: prefix độ dài cố định và nội dung domain.
        mac.update((byte) DOMAIN.length);
        mac.update(DOMAIN);
        mac.update(message);
        return mac.doFinal();
    }

    static boolean verifyTag(
            SecretKey key, byte[] message, byte[] suppliedTag
    ) throws GeneralSecurityException {
        if (suppliedTag == null || suppliedTag.length != TAG_SIZE_BYTES) {
            return false;
        }
        byte[] expected = computeTag(key, message);
        return MessageDigest.isEqual(expected, suppliedTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newHmacKey();
        byte[] payload = "orderId=42;status=PAID"
                .getBytes(StandardCharsets.UTF_8);

        byte[] tag = computeTag(key, payload);
        System.out.println("Original valid: "
                + verifyTag(key, payload, tag));

        byte[] tampered = Arrays.copyOf(payload, payload.length);
        tampered[tampered.length - 1] ^= 1;
        System.out.println("Modified valid: "
                + verifyTag(key, tampered, tag));
    }
}
~~~

Kết quả mong đợi:

~~~text
Original valid: true
Modified valid: false
~~~

**Giải thích các điểm bảo mật trong ví dụ:**

- HMAC-SHA-256 tạo tag **32 byte**; khóa ví dụ cũng 32 byte nhưng hai kích thước có ý nghĩa khác nhau.
- Hàm **computeTag** khởi tạo đối tượng **Mac mới** cho mỗi thao tác. Đối tượng Mac có trạng thái và không nên dùng chung đồng thời giữa các luồng nếu không có cơ chế đồng bộ an toàn.
- **MessageDigest.isEqual** được thiết kế để so sánh digest theo cách giảm phụ thuộc thời gian vào nội dung; bước kiểm tra độ dài tag có thể từ chối sớm vì độ dài yêu cầu là cố định. Không tự viết vòng lặp trả về ngay khi tìm thấy byte khác đầu tiên.
- Prefix **orders-webhook:v1** phân tách mục đích của tag. Trong giao thức thật, cần quản lý cả thuật toán, key ID/version, sender ID, method/path và quy tắc serialization của toàn bộ message.
- **Arrays.fill** chỉ xóa một mảng tạm mà ứng dụng nắm giữ. Nó không bảo đảm xóa mọi bản sao do JVM/provider tạo; không ghi khóa vào log và tránh giữ bí mật trong bộ nhớ lâu hơn cần thiết.
- Ví dụ chỉ xác minh sự thay đổi byte. **Nó chưa chống replay và chưa thực hiện phân quyền nghiệp vụ**; hai phần đó phải có ở tầng ứng dụng.

Trong production, MAC key không nên được tạo mỗi lần ứng dụng khởi động rồi bị mất: bên gửi và nhận cần một bí mật được **cấp phát, lưu, phiên bản hóa và khôi phục** theo quy trình quản lý khóa. Nếu sử dụng KMS/HSM có hỗ trợ tạo và xác minh HMAC nội bộ, ứng dụng có thể gọi API đó thay vì nạp key bytes vào bộ nhớ; mức hỗ trợ thực tế tùy dịch vụ.

## 8. Ví dụ webhook: xác thực nội dung và chống replay

Giả sử một dịch vụ gửi thông báo trạng thái đơn hàng tới hệ thống đối tác. Hệ thống định nghĩa đầu vào ký một cách rõ ràng:

~~~text
signature-input (định dạng minh họa, phải được đặc tả chính xác):
  protocolVersion
  senderId
  method
  canonicalPath
  issuedAt
  requestId
  SHA-256(rawBody)

tag = HMAC-SHA-256(macKeyForSender, canonicalEncode(signature-input))

Headers gửi kèm:
  Key-Id: partner-a-v3
  Timestamp: ...
  Request-Id: ...
  Signature: <tag đã mã hóa theo định dạng quy định>
~~~

Đây là **một sơ đồ giao thức minh họa**, không phải format chuẩn phổ quát. Cần chọn cơ chế encode không nhập nhằng (ví dụ trường có tiền tố độ dài), bảo vệ timestamp/requestId trong dữ liệu được HMAC xác thực và chỉ tin key ID theo danh sách đã cấu hình; không lấy key ID từ request rồi tùy ý tra một bí mật có quyền rộng.

**Bên nhận** nên thực hiện các bước:

1. Kiểm tra schema, kích thước yêu cầu và thuật toán/phiên bản được cho phép; xác định đúng đối tác, tenant và MAC key được chấp nhận.
2. Tạo lại **canonical bytes** theo đặc tả từ request nhận được. Với raw body, kiểm tra chính xác byte đã nhận, không tự serialize JSON theo cách khác.
3. Tính lại MAC và dùng hàm so sánh tag phù hợp; không chấp nhận tag sai hoặc tag có độ dài không hợp lệ.
4. Kiểm tra **khoảng thời gian cho phép** của timestamp và **requestId đã từng được xử lý hay chưa**; việc ghi nhận chống replay cần mang tính nguyên tử trong phạm vi chia sẻ giữa các instance.
5. Kiểm tra quyền nghiệp vụ: sender có được thao tác đơn hàng này không, trạng thái chuyển đổi có hợp lệ không, dữ liệu có thuộc đúng tenant không?
6. Xử lý nghiệp vụ theo cơ chế idempotency, ghi log metadata cần thiết và tránh log MAC key/credential/plaintext nhạy cảm.

### 8.1. Vì sao MAC không tự chặn replay?

Kẻ tấn công có thể sao chép một **message + tag hợp lệ** rồi gửi lại nguyên vẹn. HMAC vẫn đúng vì không có byte nào thay đổi. Nếu đây là lệnh hoàn tiền, việc xử lý lại có thể gây hậu quả.

Để chống replay, đặt timestamp, requestId, phiên bản hoặc sequence number vào dữ liệu được MAC và áp dụng **giới hạn thời gian + nơi ghi nhận yêu cầu đã dùng**. Chỉ dùng timestamp mà không nhớ requestId thường chưa đủ để ngăn phát lại trong cùng một cửa sổ thời gian.

### 8.2. Vì sao xác thực MAC không thay thế authorization?

Một đối tác có MAC key hợp lệ có thể gửi yêu cầu hợp lệ về mặt mật mã nhưng **không được phép** sửa đơn hàng của đối tác khác. Phải kiểm tra quan hệ sender–tenant–resource và quyền nghiệp vụ. Khi nhiều đối tác dùng chung một MAC key, việc xác định nguồn gây sự cố và thu hồi một đối tác trở nên khó hơn; nên **tách key theo đối tác** khi có thể.

## 9. MAC key trong KMS/HSM và envelope encryption

### 9.1. Lưu MAC key ở đâu?

Một hệ thống có thể sử dụng:

- **KMS/HSM có chức năng MAC:** Tạo và xác minh HMAC trong ranh giới an toàn mà không xuất vật liệu khóa cho ứng dụng, nếu dịch vụ hỗ trợ thuật toán và API tương ứng.
- **Kho bí mật được quản lý:** Lưu MAC key đã được bảo vệ, phân quyền cho đúng workload, cung cấp qua kênh xác thực và hạn chế xuất hiện trong log/bản build.
- **Envelope encryption:** Bảo vệ MAC key như một bí mật được wrap dưới KEK, rồi chỉ unwrap trong phạm vi ứng dụng cần sử dụng và được cho phép.

Không phải mọi **KMS key** đều có thể làm HMAC key. Một KMS có thể phân biệt **symmetric encryption key** và **HMAC key**, với mục đích, kích thước, API và policy khác nhau. Không lấy một AES KEK hiện có dùng trực tiếp cho HMAC chỉ vì cả hai đều là bí mật đối xứng.

~~~mermaid
flowchart LR
    A["Workload A"] --> AUTH["Xác thực + quyền sử dụng"]
    B["Workload B"] --> AUTH
    AUTH --> KMS["KMS/HSM hoặc kho bí mật"]
    KMS --> MAC["MAC key dùng đúng mục đích"]
    MAC --> G["Generate / Verify MAC"]
    G --> AUDIT["Audit: key ID, actor, action, result"]
~~~

Nếu MAC key không xuất được khỏi HSM, bên gửi/nhận có thể dùng API GenerateMac/VerifyMac tương ứng nếu thiết kế cho phép. Nếu phải phân phối bản sao bí mật đến một đối tác độc lập, cần có cơ chế **xuất/cấp phát được phê duyệt** hoặc chọn mô hình mật mã khác. **Không xuất khóa gốc hoặc thay đổi chính sách non-exportable chỉ để “dễ tích hợp”.**

### 9.2. Ranh giới phân quyền và kiểm toán

Phân biệt các quyền:

- **Generate MAC:** Có thể tạo tag hợp lệ cho thông điệp mới, nên là quyền nhạy cảm.
- **Verify MAC:** Có thể kiểm tra tag bằng khóa hoặc qua dịch vụ; giới hạn theo yêu cầu, khóa và phạm vi nghiệp vụ.
- **Manage key:** Tạo, đổi chính sách, xoay vòng, vô hiệu hóa hoặc xóa khóa.
- **Export/import key:** Thường nhạy cảm nhất; chỉ cho phép khi mô hình và chính sách thực sự cần.

Log nên ghi **ai**, **thao tác nào**, **key ID/version**, **kết quả** và ngữ cảnh phù hợp. Không ghi MAC key dạng rõ, bản sao key, token xác thực hoặc dữ liệu nghiệp vụ nhạy cảm không cần thiết. Cảnh báo các sự kiện bất thường như nhiều lần Verify thất bại, Generate từ workload lạ hoặc thay đổi quyền ngoài quy trình.

## 10. Vòng đời MAC key: tạo đến hủy

| Giai đoạn | Mục tiêu và công việc | Lỗi cần tránh |
| --- | --- | --- |
| **Tạo (generation)** | Chọn HMAC/CMAC/GMAC phù hợp; sinh khóa đủ entropy và đúng độ dài theo thuật toán | Khóa từ mật khẩu ngắn, timestamp, RNG không dùng cho mật mã |
| **Cấp phát (provisioning)** | Gắn khóa với đúng đối tác/workload, tenant, mục đích; truyền qua kênh đáng tin cậy | Gửi khóa qua email/chat, commit vào Git, chia sẻ một khóa cho tất cả đối tác |
| **Lưu trữ (storage)** | Mã hóa/wrap hoặc giữ trong KMS/HSM; hạn chế truy cập, sao lưu có kiểm soát | Đặt raw key trong source, container image, file cấu hình công khai |
| **Sử dụng (usage)** | MAC đúng byte và ngữ cảnh, giới hạn quyền, xác minh tag, chống replay | Ký thiếu trường quan trọng, so sánh tag không an toàn, tái sử dụng nonce GMAC |
| **Xoay vòng (rotation)** | Tạo khóa mới, ký mới bằng key mới, xác minh khóa cũ có giới hạn trong giai đoạn chuyển tiếp | Đổi khóa đột ngột làm mọi webhook hợp lệ đang trên đường truyền bị từ chối |
| **Thu hồi / vô hiệu hóa** | Ngăn tạo hoặc xác minh bằng khóa bị lộ theo kế hoạch ứng phó; xử lý cache và các bản sao | Chỉ xóa một biến cấu hình nhưng các instance khác vẫn dùng khóa |
| **Hủy (destruction)** | Xác minh không còn nghiệp vụ/tài liệu cần kiểm tra bằng key cũ, xử lý bản sao và backup theo chính sách | Hủy trước khi hết cửa sổ xác minh, hoặc để key đã thu hồi tồn tại không kiểm soát |

### 10.1. Xoay vòng không làm gián đoạn giao tiếp

Ví dụ dịch vụ đang dùng MAC key phiên bản **v1**, muốn chuyển sang **v2**:

1. Sinh v2 bằng nguồn ngẫu nhiên an toàn, lưu trong KMS/HSM hoặc kho bí mật, gắn key ID và chính sách.
2. Phân phối v2 đến đúng bên và kiểm thử xác thực trong môi trường được phép.
3. Chuyển **bên gửi sang chỉ tạo tag bằng v2** từ thời điểm được quy định.
4. Trong cửa sổ chuyển tiếp có kiểm soát, bên nhận có thể **xác minh bằng v2 và v1** tùy key ID, hạn chế thời hạn và lưu lượng hợp lệ.
5. Theo dõi tần suất thông điệp v1, trạng thái các đối tác/instance, rồi ngừng chấp nhận v1 khi cửa sổ đã hết.
6. Vô hiệu hóa và hủy v1 khi không còn nghĩa vụ xác minh phù hợp, đồng thời xử lý cache/bản sao/backup theo chính sách.

**Không nên thử tất cả các khóa đang lưu một cách vô hạn** cho mỗi yêu cầu. Dùng key ID đã được kiểm soát, giới hạn phiên bản được phép, theo dõi lỗi và tránh biến API Verify thành nơi dò tìm cấu hình khóa. Key ID giúp chọn khóa nhưng **không phải bằng chứng xác thực riêng** nếu kẻ tấn công có thể tự thay nó.

### 10.2. Khi MAC key bị lộ

Nếu đối thủ có MAC key, họ có thể **giả mạo tag** cho các thông điệp mà hệ thống sẽ chấp nhận dưới khóa đó. Quy trình xử lý thường gồm:

- Chặn hoặc hạn chế các chủ thể/dịch vụ có thể đang lạm dụng khóa; điều tra đường lộ và bảo toàn log.
- Xác định những đối tác, tenant, mục đích và khoảng thời gian đã sử dụng key bị ảnh hưởng.
- Sinh, phân phối và kích hoạt khóa mới; thu hồi hoặc ngừng chấp nhận key cũ sớm theo mức độ sự cố.
- Kiểm tra các thông điệp/transaction đã được chấp nhận trong khoảng ảnh hưởng để tìm giả mạo, replay hoặc chỉnh sửa nghiệp vụ.
- Sửa nguồn lộ khóa ở source, log, backup, IAM/policy, hệ thống build và các bản sao trước khi kết thúc ứng phó.

**Thay MAC key không thể tự vô hiệu hóa giao dịch giả đã được xử lý**, và không che được nội dung thông điệp đã truyền ở dạng rõ. Sự cố cần được đánh giá ở cả tầng mật mã lẫn tầng nghiệp vụ.

## 11. Những lỗi triển khai hay gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ gửi SHA-256(message) để “xác thực” | Kẻ sửa message có thể tạo hash mới | Dùng MAC có bí mật hoặc chữ ký số theo yêu cầu |
| Dùng một mật khẩu dễ đoán làm HMAC key | Có thể thử đoán khóa từ các thông điệp/tag quan sát được | Dùng CSPRNG/KMS; bảo vệ entropy và vòng đời |
| So sánh tag từng byte và dừng khi khác | Có thể làm lộ thông tin qua timing trong mô hình tấn công phù hợp | Dùng API so sánh digest an toàn, kiểm soát độ dài tag |
| Tính HMAC trên chuỗi ghép mơ hồ | Các bộ trường khác nhau có thể có cùng bytes để ký | Canonical encoding, length-prefix hoặc serialization đúng chuẩn |
| Bỏ path, timestamp hoặc tenant khỏi MAC | Có thể chuyển thông điệp sang ngữ cảnh khác | Ràng buộc tất cả trường ảnh hưởng quyền/quyết định bảo mật |
| Tin rằng tag hợp lệ nghĩa là không bị replay | Thông điệp cũ vẫn có tag đúng | Timestamp được xác thực, request ID duy nhất và kho chống replay |
| Dùng chung một MAC key cho mọi đối tác | Khó thu hồi từng đối tác, tăng phạm vi ảnh hưởng | Tách khóa, key ID và quyền theo đối tác/tenant |
| Dùng cùng khóa cho AES-GCM và HMAC tùy tiện | Trộn mục đích, khó phân tích độ an toàn của tổ hợp | Tách khóa hoặc KDF có domain separation |
| Dùng GMAC mà lặp lại nonce với cùng key | Rủi ro giả mạo và phá tính an toàn | Quản lý nonce nghiêm ngặt, giới hạn sử dụng và rotation |
| Dùng lại khóa Poly1305 một lần cho nhiều thông điệp | Vi phạm giả định an toàn của Poly1305 | Dùng cơ chế dẫn xuất one-time key đúng chuẩn theo giao thức |
| Rotate chỉ ở một instance | Gửi/nhận lỗi không ổn định và phiên cũ vẫn sống | Điều phối phiên bản, cache, thời hạn chấp nhận key cũ |
| Lưu MAC key trong log hoặc image triển khai | Lộ khóa dẫn đến giả mạo thông điệp | Secrets/KMS/HSM, hạn chế xuất khóa và kiểm toán |

## 12. Checklist đánh giá MAC key trong hệ thống thực

Khi review một dịch vụ dùng MAC, hãy trả lời:

1. **Thuật toán:** HMAC-SHA-256, CMAC, GMAC hay Poly1305? Tại sao chọn và có đáp ứng giao thức không?
2. **Nguồn khóa:** MAC key được sinh bằng CSPRNG/KMS/HSM đủ entropy hay đến từ chuỗi dễ đoán?
3. **Độ dài:** Key size, tag size, nonce/IV và mức an toàn mục tiêu có được phân biệt rõ không?
4. **Phân phối:** Những bên nào giữ cùng MAC key? Có tách theo tenant/đối tác/môi trường/mục đích?
5. **Dữ liệu ký:** Có đặc tả canonical bytes và ràng buộc method, path, body, context, thời gian, ID theo nhu cầu?
6. **Kiểm tra tag:** Có kiểm tra đúng thuật toán, version, độ dài và so sánh bằng API an toàn không?
7. **Replay/authorization:** Có chống phát lại và xác minh quyền nghiệp vụ sau khi MAC hợp lệ?
8. **Lưu trữ:** Khóa được bảo vệ trong KMS/HSM/kho bí mật; có tránh source, log, dump và bản sao lưu thiếu bảo vệ?
9. **Vòng đời:** Có key ID/version, cửa sổ chuyển tiếp khi rotate, quy trình thu hồi/hủy, thử khôi phục khi cần?
10. **Kiểm toán:** Có thể truy vết ai tạo/xác minh/sửa quyền đối với khóa, và phát hiện bất thường mà không lộ bí mật?

## 13. Ghi nhớ

- **MAC key là bí mật dùng để tạo/xác minh mã xác thực thông điệp.** MAC bảo vệ tính toàn vẹn và xác thực theo bí mật chung, **không mã hóa dữ liệu**.
- **HMAC-SHA-256** là lựa chọn phổ biến; khóa ngẫu nhiên 256 bit thuận tiện trong nhiều thiết kế. **Key size khác tag size và entropy**.
- **HMAC, CMAC, GMAC và Poly1305** có các quy tắc dùng khóa khác nhau. Đặc biệt, GMAC/GCM phụ thuộc quản lý nonce; Poly1305 độc lập có yêu cầu one-time key.
- **Một tag đúng không tự xác minh người gửi duy nhất, không chống replay và không thay thế authorization.** Phải ràng buộc đúng message bytes, ngữ cảnh, timestamp/request ID và quyền nghiệp vụ.
- **KMS/HSM, phân tách khóa, kiểm toán và quy trình tạo–cấp phát–lưu trữ–sử dụng–xoay vòng–thu hồi–hủy** quyết định khả năng bảo vệ MAC key trong thực tế.

Khi thiết kế cơ chế MAC cho một hệ thống Java, hãy bắt đầu bằng ba câu hỏi: **Ai được giữ hoặc dùng MAC key? Chính xác những byte và ngữ cảnh nào được xác thực? Điều gì xảy ra nếu key bị lộ hoặc phải xoay vòng?** Trả lời rõ ba câu hỏi này giúp tránh nhiều lỗi mà việc chọn thuật toán mạnh một mình không giải quyết được.
