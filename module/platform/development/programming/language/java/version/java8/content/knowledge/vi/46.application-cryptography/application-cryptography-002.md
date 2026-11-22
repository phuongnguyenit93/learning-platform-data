# Cipher, khóa, nonce và dữ liệu xác thực bổ sung (AAD) trong Java 8+

## 1. Bài toán: bảo mật dữ liệu bằng mã hóa có xác thực

Một ứng dụng phải bảo vệ một số bản ghi nhạy cảm khi lưu trữ hoặc truyền qua một tầng trung gian. Chỉ che giấu nội dung **chưa đủ**: bên nhận cũng cần phát hiện dữ liệu hoặc metadata liên quan đã bị thay đổi.

Cách tiếp cận hiện hành trong Java là dùng **AEAD (Authenticated Encryption with Associated Data)**. Một lựa chọn phổ biến, được Java Standard Names hỗ trợ, là **AES/GCM/NoPadding** với **javax.crypto.Cipher**:

- **AES** là thuật toán mã hóa đối xứng dùng cùng khóa bí mật cho mã hóa và giải mã.
- **GCM** là chế độ cung cấp bảo mật nội dung (**confidentiality**) và xác thực tính toàn vẹn (**integrity/authenticity**) bằng **authentication tag**.
- **Nonce/IV** là giá trị duy nhất theo từng lần mã hóa với cùng khóa, không phải bí mật và không được tái sử dụng với cùng khóa.
- **AAD (Additional Authenticated Data)** là dữ liệu bổ sung được xác thực cùng ciphertext nhưng **không được mã hóa**.
- **Cipher** là đối tượng vận hành mã hóa/giải mã, cấu hình với thuật toán, mode, khóa, nonce và AAD.

Một thao tác thành công có dạng:

~~~text
Plaintext + Secret key + Unique nonce + AAD
            |
       AES-GCM encrypt
            v
    Ciphertext || Authentication tag
            |
Decryption dùng cùng key, nonce, AAD
            v
     Plaintext hoặc lỗi xác thực
~~~

**Mục tiêu của bài:** biết cách dùng đúng Cipher/SecretKey/GCMParameterSpec/updateAAD/doFinal, định dạng gói dữ liệu, tránh nonce reuse, xử lý AEADBadTagException, và phân biệt xác thực với các khả năng mà GCM **không tự cung cấp** (chống phát lại, phân quyền, vòng đời khóa).

Chỉ sử dụng các API hiện còn được hỗ trợ trong Java SE hiện hành. Không khuyến nghị ECB, DES, mã hóa không xác thực hoặc tự ghép một thuật toán mật mã ad hoc làm thiết kế mới.

## 2. Khóa, nonce, AAD và tag có vai trò khác nhau

| Thành phần | Giữ bí mật? | Cần giống khi giải mã? | Công dụng |
| --- | --- | --- | --- |
| **AES key** | **Có** | Có | Bí mật trung tâm cho cả mã hóa và giải mã |
| **Nonce/IV của GCM** | Không | Có, nonce thuộc bản mã đó | Bảo đảm tính duy nhất giữa các lần mã hóa cùng khóa |
| **AAD** | **Không bảo mật bởi GCM** | Có, cùng chuỗi byte | Ràng buộc metadata/ngữ cảnh với bản mã |
| **Plaintext** | Có nếu cần bảo mật | Được khôi phục sau xác thực | Nội dung nhạy cảm ban đầu |
| **Ciphertext** | Không cần bí mật | Có | Nội dung đã được mã hóa |
| **Authentication tag** | Không cần bí mật | Có, phải hợp lệ | Kiểm tra ciphertext, AAD và dữ liệu gắn với khóa/nonce |

**Hai yêu cầu khác nhau:**

- **Giữ kín khóa:** ai có khóa có thể giải mã và có thể tạo bản mã/tag hợp lệ.
- **Không tái sử dụng cặp khóa–nonce:** dù khóa không lộ, tái sử dụng nonce với cùng khóa dưới GCM có thể phá vỡ bảo đảm mật mã nghiêm trọng.

Không được dùng một chuỗi mật khẩu hoặc một giá trị thời gian thông thường làm khóa AES bằng cách cắt byte tùy tiện. Không được tạo nonce bằng **System.currentTimeMillis()**, tên user, ID đoán được, hoặc một counter không được quản lý đồng bộ.

**AAD không che giấu thông tin.** Nếu AAD gồm tenant ID, loại dữ liệu hoặc header, đối tượng trung gian có thể biết nó nếu hệ thống truyền AAD dưới dạng rõ. **Không đặt bí mật vào AAD** chỉ vì nó được xác thực.

## 3. Java Cipher và tên transformation cần ghi tường minh

Trong JCA/JCE:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Đây là transformation gồm **algorithm/mode/padding**. Ghi đủ ba thành phần để tránh phụ thuộc cấu hình provider mặc định.

**Đừng viết Cipher.getInstance("AES") rồi mặc nhiên coi đó là AES-GCM.** Một số provider có thể chọn mode mặc định khác, kể cả mode không cung cấp authentication tag. Mã mới cần chọn transformation rõ.

**NoPadding không có nghĩa dữ liệu không an toàn.** Trong AES-GCM, đây là tên transformation chuẩn; GCM có thể mã hóa input có chiều dài bất kỳ mà không cần block padding kiểu CBC. Authentication tag vẫn được tạo và kiểm tra.

Cipher có trạng thái (mode, key, IV, AAD, dữ liệu đã xử lý); **không chia sẻ cùng Cipher instance giữa các thread**. Nên tạo một instance cho mỗi thao tác độc lập hoặc quản lý lifecycle rất chặt. Tái sử dụng instance sau doFinal có giới hạn theo mode/implementation; với GCM không nên trông đợi tự reset để mã hóa tiếp cùng key/nonce.

**Mẫu an toàn:** mỗi lần mã hóa tạo một nonce mới, khởi tạo Cipher với nonce đó, cấp AAD, gọi doFinal và lưu/truyền nonce cùng kết quả.

## 4. Chọn AES-256 hay AES-128?

AES hỗ trợ khóa 128, 192 và 256 bit. Với ứng dụng Java hiện đại, **AES-256-GCM** là lựa chọn mạnh phổ biến; **AES-128-GCM** cũng là một mức bảo vệ được sử dụng rộng rãi khi phù hợp chính sách bảo mật.

Không tự tạo khóa bằng chuỗi literal. Dùng **KeyGenerator** và **SecureRandom**:

~~~java
SecureRandom random = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, random);
SecretKey key = generator.generateKey();
~~~

Đây là snippet trong method có import java.security.SecureRandom, javax.crypto.KeyGenerator và javax.crypto.SecretKey.

**Bản Java 17+ của bài dùng AES-256. Bản Java 8 dùng AES-128** để dễ chạy cả trong môi trường JDK 8 cũ từng có giới hạn cấu hình độ dài khóa. Hiện nay, giới hạn và năng lực thực tế phải được xác minh theo provider/JDK được triển khai; không suy rằng mọi JDK 8 cũ hỗ trợ AES-256 giống bản JDK mới.

**SecretKey** phải được tạo, lưu giữ, cấp phát, thu hồi và xoay vòng theo quy định của ứng dụng. Ví dụ chỉ tạo khóa ngẫu nhiên trong RAM để kiểm thử; nó **không phải mẫu quản lý khóa bền vững**. Nếu muốn giải mã dữ liệu sau khi process khởi động lại, khóa phải được bảo vệ và có cơ chế phục hồi được.

## 5. SecureRandom tạo entropy; không dùng Random cho khóa/nonce

**java.security.SecureRandom** là API hiện hành dùng để tạo byte khó dự đoán cho các mục đích mật mã:

~~~java
byte[] nonce = new byte[12];
SecureRandom random = new SecureRandom();
random.nextBytes(nonce);
~~~

**Không dùng java.util.Random, Math.random hay UUID.randomUUID().toString().getBytes(...) làm một lựa chọn thay thế thiếu thiết kế** cho nonce 96-bit của GCM. UUID có định dạng và biểu diễn riêng; không tự cắt byte của chuỗi UUID và gọi đó là nonce đã đúng contract.

**Nonce ngẫu nhiên không tương đương bảo đảm tuyệt đối sẽ không trùng.** Với nonce 96-bit sinh từ RNG tốt, nguy cơ collision tăng khi số bản mã dưới cùng một khóa tăng. Một hệ thống có nhiều instance, khối lượng cao hoặc tuổi thọ khóa dài cần **giới hạn số lần mã hóa mỗi khóa, theo dõi phân vùng nonce và có chiến lược key rotation** theo chính sách mật mã được đánh giá.

Trong một số protocol, nonce được thiết kế bằng counter được cấp phát bền vững và phối hợp giữa các writer. Khi dùng counter, yêu cầu lớn nhất là **không lặp giá trị sau restart hoặc giữa nhiều máy**; đừng tự thiết kế bộ đếm mà không giải quyết concurrency và crash recovery.

**Không thử lại một lần mã hóa bằng cùng key+nonce** ngay cả khi request application gặp timeout mà chưa chắc lần trước đã ghi thành công. Quyết định retry và định dạng protocol cần bảo đảm key–nonce uniqueness.

## 6. Vì sao nonce 96-bit và tag 128-bit?

Với GCM, cấu hình rất phổ biến là:

- Nonce/IV dài **12 byte = 96 bit**.
- Authentication tag dài **16 byte = 128 bit**.

Java biểu diễn thông số này bằng:

~~~java
int tagBits = 128;
byte[] nonce = new byte[12];
random.nextBytes(nonce);
GCMParameterSpec spec = new GCMParameterSpec(tagBits, nonce);
~~~

**GCMParameterSpec nhận độ dài tag tính bằng bit**, không phải byte. Viết **new GCMParameterSpec(16, nonce)** không tương đương tag 128-bit. Nhà cung cấp có thể từ chối tLen không được hỗ trợ.

**12 byte nonce là lựa chọn thực hành chuẩn và tiện cho GCM**, nhưng **mấu chốt bảo mật là tính duy nhất của nonce đối với cùng một key**, không chỉ chiều dài 12 byte.

**128-bit tag** giúp tránh hạ thấp mức xác thực không cần thiết; cắt tag xuống quá ngắn phải có cơ sở trong một protocol được thiết kế/đánh giá riêng, không chỉ để giảm vài byte trong payload.

Nonce cần được giữ lại để giải mã; nó có thể nằm rõ trong gói dữ liệu. **Không nhầm nonce với khóa bí mật và không dùng nonce như một salt sinh khóa nếu không có một KDF/protocol phù hợp.**

## 7. Khởi tạo Cipher đúng cách

Mã hóa:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.ENCRYPT_MODE,
        key,
        new GCMParameterSpec(128, nonce));
~~~

Giải mã:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.DECRYPT_MODE,
        key,
        new GCMParameterSpec(128, nonceFromMessage));
~~~

Đây là hai snippet minh họa **trong method** có key và nonce tương ứng. Một phiên giải mã cần lấy **nonce của bản mã cụ thể**, không tự tạo nonce mới.

**Cipher.ENCRYPT_MODE** và **Cipher.DECRYPT_MODE** là hai chế độ khác nhau, không thể sử dụng lẫn. **Một SecretKey hợp lệ với đúng thuật toán và kích cỡ** phải có sẵn tại hai đầu.

**Không dùng Cipher.init(ENCRYPT_MODE,key) rồi quên persist IV**. Một provider có thể tự sinh IV trong một số trường hợp, nhưng nếu định dạng gói không lưu lại IV tương ứng, bên nhận không thể giải mã đáng tin cậy. Với thiết kế minh bạch, tự sinh nonce mới bằng SecureRandom và truyền GCMParameterSpec rõ ràng.

Mỗi thao tác mã hóa một message mới cần **nonce mới**, kể cả khi plaintext và AAD giống lần trước.

## 8. AAD: xác thực metadata nhưng không mã hóa metadata

Giả sử một bản ghi thuộc **tenant=blue** và **type=note**. Ứng dụng muốn ngăn kẻ tấn công lấy ciphertext của tenant này rồi gán sang tenant khác.

Có thể xác thực thông tin ngữ cảnh:

~~~java
byte[] aad = "tenant=blue|type=note"
        .getBytes(StandardCharsets.UTF_8);
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
~~~

Khi giải mã, phải cung cấp **chính các byte AAD đó** trước doFinal. Nếu dùng tenant khác, tag check thất bại (AEADBadTagException).

**AAD KHÔNG được mã hóa.** Nếu dữ liệu AAD được lưu bên ngoài gói bản mã, mọi bên cần đọc/giải mã phải biết hoặc tái tạo đúng nó. Nếu nó được gửi cùng ciphertext thì người quan sát có thể đọc AAD; vì vậy không chứa secret trong AAD.

**Đừng nhầm AAD với plaintext.** Metadata cần giữ kín phải nằm trong phần plaintext trước khi mã hóa, không nằm trần trong AAD.

**AAD hỗ trợ ràng buộc ngữ cảnh** nhưng không tự quyết định người dùng được phép xem tenant nào. Phân quyền, xác minh danh tính và mapping tenant↔key vẫn là trách nhiệm riêng của ứng dụng.

## 9. Thứ tự updateAAD trước update/doFinal là bắt buộc

Theo API Cipher và hướng dẫn JCA, tất cả AAD cho GCM phải được cấp **trước khi xử lý ciphertext/plaintext** bằng update hoặc doFinal:

~~~java
cipher.init(Cipher.ENCRYPT_MODE, key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(headerBytes);
cipher.updateAAD(contextBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
~~~

Không gọi:

~~~java
cipher.update(plaintext);
// Sai thứ tự trong GCM: không gọi updateAAD ở đây.
// cipher.updateAAD(contextBytes);
~~~

Nếu API chưa được khởi tạo, đã chuyển sai state hoặc cấp AAD sau khi bắt đầu xử lý data, **IllegalStateException** có thể được ném theo hợp đồng của Cipher/provider.

**Không dựa vào việc updateAAD "có vẻ chạy" ở một provider để làm sai thứ tự.** Khi có nhiều phần AAD, có thể gọi updateAAD nhiều lần **trước update/doFinal**, nhưng mọi bên phải kết hợp chúng thành **cùng chuỗi byte theo cùng thứ tự**.

**A và B viết AAD thành các byte khác nhau cũng tương đương sai AAD.** Chuỗi Java nhìn giống nhau nhưng khác encoding, normalization hoặc cách ghép field có thể tạo byte AAD khác và làm giải mã thất bại.

## 10. Canonical encoding của AAD và chống nhầm ngữ cảnh

Mẫu:

~~~text
tenant=blue|type=note
~~~

dễ học, nhưng **chỉ an toàn khi các giá trị có tập ký tự bị giới hạn rõ và cách encode được định nghĩa**. Nếu tenant hoặc type cho phép ký tự phân cách, nối chuỗi kiểu "a|b" có thể gây mơ hồ giữa các cặp field khác nhau.

Trong protocol production nên xác định:

1. Danh sách field AAD (version, tenant ID, record ID, content type...).
2. Thứ tự field và tên được cố định.
3. Encoding, thường **UTF-8**, với normalization/quy tắc chuyển byte rõ.
4. Độ dài bằng length prefix, encoding nhị phân có schema, hoặc canonical serialization được kiểm thử.
5. Cách xử lý giá trị null/thiếu field và versioning.
6. Giới hạn chiều dài, tránh chấp nhận AAD quá lớn từ client một cách vô hạn.
7. Cách đối chiếu AAD với **ngữ cảnh tin cậy** (tenant của người đăng nhập, record ID từ route đã được kiểm tra).

**Một attacker có thể gửi cả ciphertext lẫn AAD từ một tenant khác**, và tag vẫn có thể hợp lệ nếu cả hai vốn là bộ dữ liệu hợp lệ dưới một key mà attacker được phép gửi. Vì thế ứng dụng phải tự so sánh tenant AAD với tenant đã được xác thực, không dùng tag như cơ chế phân quyền.

**Version header/key ID cũng nên được đưa vào AAD.** Ví dụ Java 17 xác thực byte version cùng AAD, tránh trường hợp thay header không được phát hiện theo chủ đích.

## 11. doFinal trả về ciphertext cùng authentication tag

Sau khi cấp key, nonce và AAD:

~~~java
byte[] encryptedAndTag = cipher.doFinal(plaintext);
~~~

Trong GCM với Java Cipher, **tag được gắn vào phần ciphertext đầu ra khi mã hóa**, và được kiểm tra khi giải mã. Nếu plaintext dài **n byte** và tag chọn 16 byte, phần trả về thông thường có chiều dài **n + 16 byte**.

**Đừng cắt mất 16 byte cuối** khi persist/copy payload. Nếu thiếu tag, bên nhận không thể xác thực bản mã.

**Giải mã cũng chỉ dùng doFinal sau khi cấp lại cùng key, nonce, AAD**:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] plaintext = cipher.doFinal(encryptedAndTag);
~~~

Nếu tag không khớp, doFinal ném **AEADBadTagException** (một dạng BadPaddingException trong API). Trường hợp này có thể đến từ **sai key, sai nonce, sai AAD, ciphertext/tag bị sửa hoặc dữ liệu hỏng**.

**Không dùng kết quả giải mã trước khi xác thực thành công.** Nếu cần streaming rất lớn, phải lựa chọn thiết kế chunked-AEAD riêng được đánh giá và chỉ công bố plaintext của chunk sau xác thực phù hợp. Các ví dụ của bài sử dụng doFinal một lần để tránh lộ dữ liệu chưa được xác thực.

## 12. Định dạng gói: lưu version, nonce, ciphertext/tag

Cipher **không tự định nghĩa một file format có thể trao đổi giữa các service**. Bạn phải quy định cách sắp byte, giải mã, version, thuật toán, độ dài nonce/tag, AAD và key reference.

Ví dụ tối thiểu một phiên bản:

~~~text
[1 byte version=1]
[12 byte nonce]
[N byte ciphertext]
[16 byte authentication tag]
~~~

Với input plaintext n byte, gói trên có tổng **1 + 12 + n + 16 = n+29 byte**. Với plaintext rỗng, vẫn cần version, nonce và tag, vì vậy gói có **29 byte**.

**Không đưa key bí mật vào gói**. Trong hệ thống có nhiều key, có thể thêm một key ID **không nhạy cảm** và bind key ID vào AAD; key ID chỉ để tra cứu KMS/keystore, không phải bản thân key. Nếu thêm field vào header, phải cập nhật schema version, parser, authentication và minimum length.

**Nonce được để rõ** vì bên nhận cần nó. AAD có thể được lưu ở metadata riêng, tái tạo từ context hoặc đi cùng gói ở dạng không mã hóa. Ví dụ Java 17 bên dưới **không serialize AAD vào gói**: caller cung cấp cùng AAD khi encrypt/decrypt.

**Đừng giải mã Base64 như text UTF-8 tùy ý rồi nối tay từng trường.** Nếu cần vận chuyển trong JSON, Base64 encode toàn bộ byte packet rồi truyền như chuỗi text; khi nhận phải Base64 decode và kiểm tra tối thiểu kích thước/phiên bản trước decrypt.

## 13. Chương trình Java 17 hoàn chỉnh: AEAD envelope và kiểm thử sửa dữ liệu

Đây là một chương trình độc lập dùng **Java 17+**, không cần thư viện ngoài. Mỗi lần encrypt sinh **nonce ngẫu nhiên mới**. AAD gồm byte version và context. Khi decrypt, chương trình đọc version/nonce từ packet, cấp AAD trước doFinal và xác thực tag.

**Tên file: AesGcmEnvelopeDemo.java**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmEnvelopeDemo {
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();

    static SecretKey newKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] {VERSION});
        cipher.updateAAD(context);
        byte[] encryptedAndTag = cipher.doFinal(plaintext);

        byte[] envelope = new byte[1 + NONCE_BYTES + encryptedAndTag.length];
        envelope[0] = VERSION;
        System.arraycopy(nonce, 0, envelope, 1, NONCE_BYTES);
        System.arraycopy(encryptedAndTag, 0, envelope, 1 + NONCE_BYTES,
                encryptedAndTag.length);
        return envelope;
    }

    static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws Exception {
        if (envelope.length < 1 + NONCE_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("invalid envelope length");
        }
        byte version = envelope[0];
        if (version != VERSION) {
            throw new IllegalArgumentException("unsupported version");
        }

        byte[] nonce = Arrays.copyOfRange(envelope, 1, 1 + NONCE_BYTES);
        byte[] encryptedAndTag = Arrays.copyOfRange(
                envelope, 1 + NONCE_BYTES, envelope.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] {version});
        cipher.updateAAD(context);
        return cipher.doFinal(encryptedAndTag);
    }

    @FunctionalInterface
    interface Attempt { void run() throws Exception; }

    static void expectInvalidTag(String label, Attempt attempt)
            throws Exception {
        try {
            attempt.run();
            throw new AssertionError("expected AEADBadTagException: " + label);
        } catch (AEADBadTagException expected) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newKey();
        byte[] aad = "tenant=blue|type=note".getBytes(StandardCharsets.UTF_8);
        byte[] text = "Xin chao, Java AES-GCM!".getBytes(StandardCharsets.UTF_8);

        byte[] packet = encrypt(key, text, aad);
        byte[] plaintext = decrypt(key, packet, aad);
        System.out.println("round trip: " + Arrays.equals(text, plaintext));
        System.out.println("nonce bytes: " + NONCE_BYTES);
        System.out.println("tag bytes: " + TAG_BYTES);
        System.out.println("envelope length valid: " +
                (packet.length == 1 + NONCE_BYTES + text.length + TAG_BYTES));
        System.out.println("AAD visible in packet: " +
                (new String(packet, StandardCharsets.ISO_8859_1)
                        .contains("tenant=blue")));

        byte[] tamperedCiphertext = packet.clone();
        tamperedCiphertext[1 + NONCE_BYTES] ^= 1;
        expectInvalidTag("ciphertext tampering", () ->
                decrypt(key, tamperedCiphertext, aad));

        byte[] tamperedTag = packet.clone();
        tamperedTag[tamperedTag.length - 1] ^= 1;
        expectInvalidTag("tag tampering", () ->
                decrypt(key, tamperedTag, aad));

        byte[] tamperedNonce = packet.clone();
        tamperedNonce[1] ^= 1;
        expectInvalidTag("nonce tampering", () ->
                decrypt(key, tamperedNonce, aad));

        expectInvalidTag("wrong AAD", () ->
                decrypt(key, packet,
                        "tenant=red|type=note".getBytes(StandardCharsets.UTF_8)));

        SecretKey otherKey = newKey();
        expectInvalidTag("wrong key", () -> decrypt(otherKey, packet, aad));

        byte[] badVersion = packet.clone();
        badVersion[0] = 2;
        try {
            decrypt(key, badVersion, aad);
            throw new AssertionError("expected invalid version");
        } catch (IllegalArgumentException expected) {
            System.out.println("unsupported version: rejected");
        }

        byte[] empty = encrypt(key, new byte[0], aad);
        System.out.println("empty plaintext packet bytes: " + empty.length);
        System.out.println("empty plaintext decoded bytes: " +
                decrypt(key, empty, aad).length);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AesGcmEnvelopeDemo.java
java AesGcmEnvelopeDemo
~~~

**Stdout đã quan sát khi biên dịch với javac --release 17 và thực thi trên JDK hiện đại:**

~~~text
round trip: true
nonce bytes: 12
tag bytes: 16
envelope length valid: true
AAD visible in packet: false
ciphertext tampering: rejected
tag tampering: rejected
nonce tampering: rejected
wrong AAD: rejected
wrong key: rejected
unsupported version: rejected
empty plaintext packet bytes: 29
empty plaintext decoded bytes: 0
~~~

**Cách đọc kết quả:**

- **round trip: true**: đúng key, nonce và AAD thì giải mã khôi phục lại plaintext.
- **nonce bytes / tag bytes**: thể hiện cấu hình 96-bit nonce và 128-bit tag.
- **envelope length valid**: packet chứa version+nonce+ciphertext/tag đúng định dạng đã xây.
- **AAD visible in packet: false** chỉ là phép dò chuỗi *minh họa một lần chạy*: code này không serialize context AAD vào packet. **Không dùng phép dò chuỗi trong ciphertext làm bài test bảo mật**; AAD vẫn không được mã hóa bởi GCM và sẽ hiển thị rõ nếu bạn chủ động truyền nó bên ngoài.
- **ciphertext/tag/nonce tampering: rejected**: sửa một byte làm tag check thất bại.
- **wrong AAD / wrong key: rejected**: tag không còn xác thực được khi thay ngữ cảnh hoặc khóa.
- **unsupported version**: ứng dụng từ chối envelope format không biết trước khi gọi Cipher; version hợp lệ còn được đưa vào AAD.
- **empty plaintext**: AEAD vẫn tạo tag và kiểm chứng dữ liệu rỗng, gói tối thiểu 29 byte.

**Đừng assert ciphertext/Base64 cụ thể**: nonce được sinh ngẫu nhiên ở mỗi lần encrypt nên byte packet khác nhau giữa các lượt chạy. Các dòng stdout phía trên là kết quả kiểm chứng hành vi, không công bố khóa hoặc ciphertext.

## 14. Ví dụ Java 8 độc lập: AES-GCM, AAD và thay đổi ciphertext

Trong hệ Java 8, các API **Cipher, SecureRandom, SecretKey, GCMParameterSpec, AEADBadTagException** đã tồn tại. Ví dụ dưới đây chỉ dùng cú pháp và API tương thích Java 8, khóa AES-128 được tạo ngẫu nhiên.

**Tên file: AesGcmJava8Demo.java**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmJava8Demo {
    private static final int NONCE_SIZE = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] aad)
            throws Exception {
        byte[] nonce = new byte[NONCE_SIZE];
        RANDOM.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextTag = cipher.doFinal(plaintext);
        byte[] packet = new byte[NONCE_SIZE + ciphertextTag.length];
        System.arraycopy(nonce, 0, packet, 0, NONCE_SIZE);
        System.arraycopy(ciphertextTag, 0, packet,
                NONCE_SIZE, ciphertextTag.length);
        return packet;
    }

    static byte[] decrypt(SecretKey key, byte[] packet, byte[] aad)
            throws Exception {
        if (packet.length < NONCE_SIZE + TAG_BITS / 8) {
            throw new IllegalArgumentException("invalid encrypted packet");
        }
        byte[] nonce = Arrays.copyOfRange(packet, 0, NONCE_SIZE);
        byte[] ciphertextTag = Arrays.copyOfRange(
                packet, NONCE_SIZE, packet.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey key = generator.generateKey();
        byte[] aad = "tenant=team-a".getBytes(StandardCharsets.UTF_8);
        byte[] text = "Dữ liệu của tôi".getBytes(StandardCharsets.UTF_8);
        byte[] packet = encrypt(key, text, aad);
        System.out.println("AES key bits: " + (key.getEncoded().length * 8));
        System.out.println("round trip: " +
                Arrays.equals(text, decrypt(key, packet, aad)));
        System.out.println("packet bytes correct: " +
                (packet.length == NONCE_SIZE + text.length + TAG_BITS / 8));

        try {
            decrypt(key, packet,
                    "tenant=team-b".getBytes(StandardCharsets.UTF_8));
            throw new AssertionError("wrong AAD accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("wrong AAD rejected: true");
        }

        byte[] changed = packet.clone();
        changed[NONCE_SIZE] ^= 1;
        try {
            decrypt(key, changed, aad);
            throw new AssertionError("tampered ciphertext accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("modified ciphertext rejected: true");
        }
    }
}
~~~

Biên dịch với JDK hỗ trợ target Java 8:

~~~bash
javac --release 8 AesGcmJava8Demo.java
java AesGcmJava8Demo
~~~

Nếu biên dịch bằng **chính JDK 8**, dùng **javac AesGcmJava8Demo.java** vì --release là tùy chọn của javac mới hơn.

**Stdout đã kiểm chứng khi biên dịch --release 8 và chạy:**

~~~text
AES key bits: 128
round trip: true
packet bytes correct: true
wrong AAD rejected: true
modified ciphertext rejected: true
~~~

**Tại sao có bản Java 8 riêng?** Nó chứng minh các API GCM/AAD của bài vẫn thuộc bộ API đã có từ thời Java 8, không cần cú pháp mới, nhưng được sử dụng theo cách phù hợp bảo mật hiện hành. Không có nghĩa mọi runtime Java 8 cũ đều còn được nhà cung cấp hỗ trợ cập nhật bảo mật; hệ thống production nên dùng runtime/JDK được tổ chức duy trì hỗ trợ.

## 15. Khi tag sai: AEADBadTagException và ứng xử an toàn

Khi Cipher ở **DECRYPT_MODE**, nếu tag không khớp, doFinal ném **AEADBadTagException**.

~~~java
try {
    byte[] plaintext = cipher.doFinal(ciphertextAndTag);
    // Chỉ sau doFinal thành công mới sử dụng plaintext.
} catch (AEADBadTagException invalid) {
    // Từ chối packet; không đưa dữ liệu chưa xác thực cho caller.
}
~~~

Đây là snippet bên trong method có Cipher đã được init để giải mã và đã gọi updateAAD nếu có.

**Các lý do thường cùng dẫn đến tag sai:**

- Sai SecretKey (ví dụ dùng key version khác).
- Sai nonce/IV.
- Sai AAD, thứ tự AAD, encoding hoặc ngữ cảnh.
- Ciphertext bị thay đổi, cắt thiếu byte hoặc bị hỏng.
- Authentication tag bị thay đổi.
- Protocol parameters/format không khớp.

**Không trả thông báo chi tiết ra client phân biệt "sai khóa" với "sai AAD" khi đó là thông tin nhạy cảm**. Có thể trả lỗi chung "invalid encrypted payload" và ghi metric/log an toàn cho hệ thống vận hành. Đừng log key, plaintext hoặc raw ciphertext nhạy cảm để debug.

**Tag hợp lệ không chứng minh người gửi là một danh tính cụ thể.** Nó chỉ cho biết dữ liệu xác thực bằng key mà bên nhận dùng. Nếu nhiều actor chia sẻ key, vẫn cần xác thực/phân quyền và ràng buộc danh tính ở tầng ứng dụng.

## 16. Không tái sử dụng cặp key + nonce: điều kiện bắt buộc

GCM có yêu cầu khắt khe: **cùng một khóa AES không được dùng với cùng nonce trong hai lần mã hóa khác nhau**. Kể cả plaintext khác hay AAD khác, reuse là lỗi thiết kế nghiêm trọng.

**Không viết mã mẫu để chủ động mã hóa lại cùng cặp key–nonce rồi so sánh ciphertext.** Việc đó không dạy cách dùng GCM an toàn. Hãy kiểm tra tính duy nhất của nonce bằng cách kiểm tra chính sách tạo nonce, khả năng đồng bộ giữa writer và quy trình rotation.

Hai hướng thường gặp:

1. **Random 96-bit nonce** từ SecureRandom. Cần quản lý giới hạn số message mỗi key và đánh giá nguy cơ collision theo NIST và workload. Không chạy vô hạn dưới một khóa.
2. **Counter-based nonce có phân vùng** (node/epoch/sequence) do một protocol được thiết kế kỹ. Phải bảo đảm không tái sử dụng khi crash, restore backup, rollback hoặc scale-out.

**Đổi key trước khi chạm ngưỡng chính sách**. Mỗi key có lifetime, số lần encrypt tối đa, cơ chế rotation và cách truy cập phiên bản cũ để decrypt. Không có một ngưỡng "phù hợp mọi sản phẩm" chỉ dựa vào tuổi thọ theo ngày mà bỏ qua số lần mã hóa.

Nếu một request bị retry sau lỗi mạng, **không tái dùng cặp key–nonce để tạo bản mã mới**. Nếu cần idempotency, lưu một packet đã tạo thành công cùng operation ID, hoặc áp dụng protocol quản lý nonce/commit được đánh giá.

## 17. Vòng đời khóa: sinh, lưu, định danh, xoay vòng

Mã demo tạo SecretKey trong RAM để chạy test, nhưng ứng dụng thật phải có **quản lý khóa**:

- Sinh khóa bằng **KeyGenerator + SecureRandom** hoặc hệ thống key management được đánh giá.
- Bảo vệ key trong **KMS/HSM/secret manager/keystore** thích hợp, giới hạn quyền truy cập và audit.
- Không hard-code key, không commit key vào source, không gửi trong telemetry/log.
- Có **key ID/version không bí mật** để tìm đúng key khi decrypt. Ràng buộc key ID vào AAD nếu nó ảnh hưởng ngữ nghĩa protocol.
- Áp dụng rotation, quản lý bản mã cũ, thu hồi key theo policy và backup/restore an toàn.
- Tránh cùng key dùng lung tung cho nhiều mục đích; dùng **key separation** khi cần nhiều protocol/tenant/chức năng.
- Không kết luận "đã xóa byte[]" chắc chắn xóa sạch bí mật khỏi toàn bộ JVM/heap/provider; Java quản lý memory, nên yêu cầu xóa key nhạy cảm cần thiết kế và thư viện/provider phù hợp.

**Một string password không phải SecretKey AES có entropy phù hợp.** Nếu đầu vào là mật khẩu người dùng, cần KDF có salt và tham số được đánh giá (ví dụ PBKDF2WithHmacSHA256 trong JCA hoặc giải pháp chuyên dụng theo chính sách), thay vì gọi **new SecretKeySpec(password.getBytes(), "AES")**.

**Salt của KDF**, **nonce của GCM** và **key ID** là các thành phần có chức năng riêng, không thay thế nhau.

## 18. AAD không thay thế chống replay hay phân quyền

GCM bảo đảm một packet và AAD **chưa bị sửa mà không bị phát hiện** dưới key tương ứng, nhưng **không biết một packet đã từng xuất hiện trước đó hay chưa**. Một attacker có thể sao chép lại **toàn bộ bản mã hợp lệ**, nonce, tag và AAD y nguyên; tag vẫn hợp lệ.

Nếu ứng dụng cần chống replay, thiết kế thêm:

- **Record ID / message ID / request nonce** ở protocol và store phát hiện duplicate.
- **Sequence number/counter** hoặc timestamp với cửa sổ chấp nhận phù hợp.
- Trạng thái chống phát lại bền vững qua restart, nếu mô hình đe dọa yêu cầu.
- Bind những trường liên quan vào **AAD đã được canonical hóa**, rồi vẫn kiểm tra tính mới và quyền ở tầng ứng dụng.

**Authentication tag không phải access token.** Không cho phép đọc dữ liệu của tenant khác chỉ vì packet hợp lệ: đối chiếu AAD tenant ID với identity/authorization của caller.

**Aead encryption không thay thế TLS khi vận chuyển**, không ngăn metadata traffic analysis, không ngăn lỗi logging plaintext, không bảo vệ khi attacker đã có quyền truy cập key.

## 19. Dữ liệu đầu vào không tin cậy và kiểm tra envelope

Trước khi decrypt, input packet có thể đến từ client, file hoặc message queue. Cần kiểm tra:

1. Packet có **độ dài tối thiểu** cho version+nonce+tag không?
2. **Version** có được hỗ trợ không, có policy deprecation cho version cũ không?
3. Các field header/length có mâu thuẫn không?
4. **Algorithm/key ID** có nằm trong tập cho phép và được bind vào AAD nếu có ảnh hưởng protocol không?
5. Packet có vượt giới hạn dung lượng đã được ứng dụng cho phép không?
6. Byte AAD có được lấy từ context tin cậy hoặc đối chiếu với quyền người dùng không?
7. Input có bị xử lý an toàn trước khi tạo buffer lớn hoặc cấp tài nguyên tốn kém không?
8. Khi xác thực sai, chương trình có **không** dùng plaintext một phần và trả lỗi thống nhất không?

**Không cấp phát mảng theo length lấy thẳng từ packet không tin cậy** mà chưa kiểm tra giới hạn; phải ngăn memory exhaustion.

**Version check diễn ra trước decrypt trong demo.** Header version còn được đưa vào AAD để ràng buộc cryptographic context cho phiên bản hợp lệ.

**Chú ý byte-level:** Java String là chuỗi Unicode, nhưng Cipher nhận **byte[]**. Chuyển plaintext và AAD bằng UTF-8 tường minh, kiểm tra normalization và serialization. Không assume các chuỗi nhìn giống nhau luôn tạo ra cùng bytes.

## 20. Các lỗi thường gặp khi dùng Cipher/AES-GCM

1. **Cipher.getInstance("AES")** thay vì transformation tường minh. Dễ phụ thuộc provider/mode không đúng.
2. **Chọn AES/ECB** để mã hóa dữ liệu nhạy cảm. ECB không cung cấp authenticated encryption và lộ pattern.
3. **Chỉ mã hóa CBC không authentication**, rồi coi dữ liệu không thể bị sửa. Thiết kế mới nên ưu tiên AEAD phù hợp.
4. **Dùng cùng key và nonce cho hai lần encrypt**. Vi phạm nghiêm trọng điều kiện GCM.
5. **Lấy nonce từ timestamp hoặc Random thường**, hoặc tái tạo một nonce sau restart mà không quản lý uniqueness.
6. **Coi nonce là secret** và không lưu cùng ciphertext; bên nhận mất thông số cần giải mã.
7. **Đưa key AES vào cùng packet**. Mất mục đích bảo mật.
8. **Nhầm GCMParameterSpec(16,nonce) thành tag 16 byte**. Đối số tLen tính bằng bit, cần 128.
9. **Gọi updateAAD sau update/doFinal**. Sai thứ tự GCM.
10. **Coi AAD được mã hóa**. Nó chỉ được xác thực và có thể công khai.
11. **Không cấp AAD giống nhau khi decrypt**. Tag check sẽ thất bại.
12. **Ghép chuỗi AAD mơ hồ**, để người gửi/nhận tạo bytes khác hoặc xuất hiện collision schema.
13. **Bỏ tag khi lưu ciphertext**. Không thể kiểm chứng toàn vẹn.
14. **Coi AEADBadTagException là lỗi có thể bỏ qua** rồi trả plaintext. Phải từ chối packet.
15. **Phân biệt lỗi sai key/sai tag ra client quá chi tiết** khi điều đó làm lộ thông tin.
16. **Chia sẻ Cipher giữa nhiều thread**. Cipher có state, không thread-safe theo giả định chung.
17. **Tự tái dùng Cipher sau doFinal với nonce cũ**. Cần Cipher/nonce mới cho lần encrypt mới.
18. **Dùng một khóa mật khẩu bytes thô làm AES key**. Thiếu KDF và kiểm soát entropy.
19. **Không rotate key, không giới hạn số bản mã/key**. Random 96-bit nonce không phải vé dùng vô hạn.
20. **Không có key ID hoặc policy decrypt phiên bản cũ**. Key rotation làm dữ liệu cũ không đọc được.
21. **Coi AEAD xác thực danh tính user hoặc chống replay**. Cần identity/ACL/sequence riêng.
22. **Dùng Base64 như một dạng mã hóa bảo mật**. Base64 chỉ biểu diễn bytes dưới dạng text.
23. **Không giới hạn size packet/AAD**. Untrusted payload có thể gây từ chối dịch vụ.
24. **Log plaintext, AES key, nonce+key cùng nhau** trong debug hoặc exception trace. Nonce có thể công khai nhưng khóa phải được giữ kín.
25. **Viết một protocol binary tùy tiện mà không version hóa/test chéo**. Cần spec byte order, field length, AAD schema và test vector theo phiên bản.

## 21. Test matrix cho chức năng AEAD

| Ca test | Dữ liệu thay đổi | Kết quả đúng |
| --- | --- | --- |
| Round-trip | Không | Plaintext sau decrypt bằng plaintext đầu |
| Sửa ciphertext | Một byte ở ciphertext | AEADBadTagException |
| Sửa tag | Một byte ở tag | AEADBadTagException |
| Sửa nonce | Một byte nonce | AEADBadTagException với packet cụ thể |
| Sai AAD | Tenant/type khác | AEADBadTagException |
| Sai key | Key ngẫu nhiên khác | AEADBadTagException |
| Version không hỗ trợ | Byte version khác | Bị parser từ chối |
| Plaintext rỗng | 0 byte nội dung | Packet vẫn có tag và decrypt trả 0 byte |
| Plaintext UTF-8 | Văn bản Unicode | Round-trip giữ đúng bytes |
| Truncated packet | Thiếu header/tag | Parser từ chối trước Cipher |
| Nhiều message | Encrypt nhiều lần cùng key | Có chính sách cấp nonce khác nhau và giới hạn sử dụng/key |
| Crash/restart | Nonce manager khởi động lại | Không lặp key+nonce |
| Wrong context | AAD từ context khác | Không cấp plaintext |
| Tampered metadata | Header/key ID/tenant bị sửa | Được bind vào AAD và phát hiện hoặc từ chối format |
| Replay | Gửi lại packet hợp lệ | Tầng anti-replay phát hiện theo policy; GCM đơn lẻ không phát hiện |
| Scale-out | Hai node cùng encrypt | Nonce uniqueness phối hợp toàn hệ thống |
| Rotation | Key đổi version | Đọc dữ liệu cũ bằng key version phù hợp theo policy |

**Không assert ciphertext cố định khi nonce được tạo ngẫu nhiên**. Test chính phải kiểm tra round-trip, xác thực tag, reject tampering và định dạng gói. Với test kiểm tra nonce manager, dùng interface để cấp các nonce được kiểm soát và assert không trùng trong phạm vi policy; không biến unit test thành lời chứng minh toán học rằng RNG không bao giờ collision.

**Không test security bằng cách tìm xem chuỗi plaintext hoặc AAD có xuất hiện trong ciphertext hay không.** Một mẫu ngẫu nhiên không chứng minh an toàn mật mã; dựa vào hợp đồng thuật toán, cấu hình, threat model và kiểm thử thay đổi dữ liệu.

## 22. Triển khai với streaming/big files: đừng trả plaintext chưa xác thực

Ví dụ bài dùng **doFinal(byte[])** cho một message nằm trong RAM. Khi xử lý file lớn, nhiều vấn đề phát sinh:

- Một ciphertext+tag được xác thực **sau khi xử lý dữ liệu**; đừng phát nội dung giải mã chưa xác thực cho người tiêu dùng cuối.
- Một số API streaming có thể trả dữ liệu theo đoạn trước lúc tag cuối được kiểm tra; ứng dụng phải không công bố/commit plaintext trước khi xác thực.
- Dữ liệu lớn đòi giới hạn kích thước thông điệp GCM và chính sách nonce/key theo NIST, không stream vô hạn trong một message.
- Nếu cần stream hiệu quả, có thể dùng một **format chia chunk được mã hóa/xác thực độc lập**, mỗi chunk có key/nonce/sequence/AAD rõ và chống reorder/truncation/replay theo thiết kế được đánh giá.

**Không tự triển khai chunked-GCM bằng cách lặp cùng nonce cho từng chunk** hoặc chỉ thay position tùy tiện mà không có protocol được phân tích. Đối với dữ liệu nhạy cảm quy mô lớn, dùng thư viện/format đáng tin cậy có tài liệu và khả năng tương tác phù hợp hơn.

**Không trộn AES-GCM với GZIP/padding tùy tiện khi dữ liệu và attacker-controlled text có cùng kênh lộ kích thước** mà chưa đánh giá side channel. Tính riêng tư của độ dài, traffic patterns và metadata là vấn đề thêm ngoài AEAD.

## 23. Lỗi theo loại: parsing, crypto setup, authentication, domain

Ứng dụng nên phân loại vấn đề ở đúng tầng:

| Tầng | Ví dụ lỗi | Chính sách |
| --- | --- | --- |
| Format | Envelope quá ngắn, version không hỗ trợ | Từ chối trước decrypt, giới hạn bộ nhớ |
| Cấu hình | Không có transformation/provider hoặc key sai kích thước | Fail fast, không chọn thuật toán yếu làm fallback |
| Tham số | Nonce/tag spec không hợp lệ | Sửa cấu hình/protocol, không thử ngẫu nhiên tùy ý |
| Xác thực | AEADBadTagException | Từ chối, không cung cấp plaintext |
| Nghiệp vụ | Tenant record không được phép | Chặn bằng authorization, không dựa vào tag |
| Replay | Packet cũ được gửi lại nguyên vẹn | Chặn qua anti-replay/idempotency |
| Storage | Không lấy được key từ KMS | Không tự sinh key mới rồi giả vờ giải mã dữ liệu cũ |

**Sai key, nonce và AAD thường đều thành tag mismatch**; đừng tự suy một nguyên nhân chính xác chỉ từ AEADBadTagException. Nếu cần debug, kiểm tra key version, thông số payload và logging an toàn tại server, không tiết lộ secret.

**Không dùng fallback không xác thực** như tự giải mã ECB/CBC khi GCM thất bại. Đó là đường downgrade gây suy yếu chính sách bảo mật.

## 24. Bài tập thực hành có đáp án

**1.** AES-GCM có mã hóa AAD không? — **Không**. AAD được xác thực nhưng không ẩn.

**2.** Nonce có phải là AES key không? — **Không**. Key là bí mật; nonce là thông số phải duy nhất cho mỗi lần encrypt với cùng key.

**3.** Cùng key, plaintext và AAD, có dùng lại cùng nonce cho lần mã hóa thứ hai không? — **Không**, tuyệt đối tránh reuse key–nonce.

**4.** GCMParameterSpec(128,nonce) có nghĩa gì? — **128 bit tag**, kèm nonce/IV; 128 không phải số byte.

**5.** Nonce 12 byte tương đương bao nhiêu bit? — **96 bit**.

**6.** Cipher.getInstance("AES") có bảo đảm dùng GCM không? — **Không**. Phải chỉ định "AES/GCM/NoPadding".

**7.** Khi cấp AAD, gọi trước hay sau doFinal? — **Trước cả update lẫn doFinal**.

**8.** Khi decrypt sai AAD, điều gì thường xảy ra? — **AEADBadTagException**; không trả plaintext.

**9.** Mất nonce nhưng giữ ciphertext/tag và key có giải mã đúng được không? — **Không có thông số đúng để decrypt**. Cần persist nonce từng packet.

**10.** Packet có thể lưu nonce ở dạng rõ không? — **Có**, nonce không phải secret.

**11.** Có được lưu khóa AES kèm ciphertext để tiện giải mã không? — **Không**. Khóa cần được bảo vệ riêng.

**12.** Authentication tag có xác định chính xác ai gửi packet không? — **Không**; nó xác thực theo key, không phải định danh người dùng.

**13.** Gửi lại nguyên packet hợp lệ có bị GCM tự phát hiện replay không? — **Không**. Anti-replay là tầng riêng.

**14.** Nếu hai writer nhiều máy mã hóa dưới cùng key, yêu cầu về nonce là gì? — **Không trùng trên mọi writer**, kể cả restart hoặc scale-out.

**15.** Tại sao không dùng String.getBytes() không chỉ định charset? — Encoding mặc định có thể không như protocol; dùng **StandardCharsets.UTF_8**.

**16.** Vì sao AAD cần canonical serialization? — Hai bên phải dùng đúng bytes và tránh cách ghép metadata mơ hồ.

**17.** Có được gọi updateAAD sau cipher.update(plaintext) không? — **Không**, thứ tự GCM không cho phép.

**18.** Nếu tag sai nhưng ứng dụng đã stream một phần plaintext ra client, đó là gì? — **Lỗi thiết kế bảo mật**; không công bố dữ liệu chưa xác thực.

**19.** AES-128 có tự động bị loại bỏ chỉ vì AES-256 tồn tại? — **Không**. Cả hai là lựa chọn chuẩn tùy yêu cầu; dùng khóa có entropy phù hợp và nonce đúng.

**20.** Nếu ứng dụng cần một password-derived key, có thể lấy password UTF-8 làm AES key trực tiếp không? — **Không**; cần KDF với salt/tham số được đánh giá.

## 25. Checklist production: trước khi phát hành một API mã hóa

- **Transformation:** dùng AES/GCM/NoPadding hoặc một AEAD chuẩn được sản phẩm và provider hỗ trợ; không phụ thuộc mode mặc định.
- **Key:** nguồn sinh đủ entropy, lưu trong hệ quản lý khóa thích hợp; không hard-code, không log, có key rotation và key ID.
- **Nonce:** dài/cấu trúc đúng chuẩn; duy nhất trên mọi encryption dưới cùng key; có quota, cơ chế tránh collision và chính sách khi restart/scale-out.
- **Tag:** 128-bit nếu phù hợp policy; serialize đầy đủ và kiểm tra ở doFinal.
- **AAD:** xác định rõ trường, encoding, version, canonicalization, giới hạn size, ngữ cảnh tin cậy; supply trước update/doFinal.
- **Envelope:** version/nonce/ciphertext/tag có format byte cố định, giới hạn kích thước, không nhầm key với key ID; metadata ảnh hưởng bảo mật được authenticate.
- **Key separation:** không dùng cùng key cho nhiều mục đích không được đánh giá; liên kết tenant, record, version và protocol context.
- **Errors:** reject AEADBadTagException, không trả plaintext chưa xác thực, thông báo bên ngoài không làm lộ bí mật.
- **Threading:** Cipher instance không dùng chung giữa nhiều thread; mã hóa mỗi message là một operation mới với nonce mới.
- **Replay/authorization:** kiểm tra danh tính, quyền truy cập và duplicate/sequence riêng, không nhầm authentication tag là bằng chứng tất cả các điều đó.
- **Testing:** round-trip, tamper ciphertext/tag/nonce/AAD/key, version, empty input, Unicode, limits, concurrency và key rotation.
- **Logging/ops:** không lộ key/plaintext; có metrics cho tag mismatch, invalid format, key unavailable và tỷ lệ mã hóa theo key để quyết định rotation.
- **Dependencies:** cập nhật JDK và crypto provider được hỗ trợ; không cố fallback sang cấu hình yếu khi thuật toán mong muốn không khả dụng.

## 26. Tài liệu chính thức và kết luận

**Tài liệu Oracle Java SE 26 (API vẫn còn được hỗ trợ):**

- **Cipher** — AES/GCM/NoPadding, updateAAD trước update/doFinal, tag appended/verified, nonce reuse và AEADBadTagException: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html
- **GCMParameterSpec** — chiều dài tag tLen tính bằng bit và nonce/IV: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html
- **AEADBadTagException** — lỗi xác thực AEAD: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/AEADBadTagException.html
- **KeyGenerator** — tạo SecretKey với kích thước và nguồn entropy phù hợp: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/KeyGenerator.html
- **SecureRandom** — RNG dành cho bảo mật: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html
- **Java Cryptography Architecture Reference Guide** — ví dụ AES-GCM với AAD, quy tắc thay IV giữa các lần mã hóa: https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html
- **Oracle JCA Guide dành cho Java 8** — hỗ trợ AES-GCM/AAD và yêu cầu không tái dùng key–IV: https://docs.oracle.com/javase/8/docs/technotes/guides/security/crypto/CryptoSpec.html

**NIST SP 800-38D về GCM:** https://csrc.nist.gov/pubs/sp/800/38/d/final . Đây là tài liệu nền tảng cho GCM, nhấn mạnh tính duy nhất IV/nonce và những ràng buộc về giới hạn sử dụng; tham khảo thông báo rà soát/cập nhật của NIST khi thiết kế hệ thống mới.

**Mức kiểm chứng của bài:** cả AesGcmEnvelopeDemo trên Java 17 và AesGcmJava8Demo với javac --release 8 đã biên dịch và chạy thành công. Chương trình Java 17 kiểm thử round-trip, tamper ciphertext/tag/nonce, sai AAD, sai key, version và plaintext rỗng; chương trình Java 8 xác nhận round-trip, AAD mismatch và tamper bị từ chối. Kết quả là các kiểm thử API thực sự dùng Cipher của JDK, **không phải** kiểm thử một hệ KMS, protocol đa node hoặc ứng dụng production hoàn chỉnh.

**Gói kiến thức chính:** **key phải bí mật**, **nonce phải duy nhất theo key**, **AAD được xác thực nhưng không mã hóa**, **tag phải được giữ và kiểm tra**. Chỉ sau khi Cipher.doFinal ở chế độ giải mã thành công mới công bố dữ liệu đã xác thực. Kết hợp những điều này với key management, authorization và anti-replay để tạo một hệ thống bảo mật có ý nghĩa thực tế.
