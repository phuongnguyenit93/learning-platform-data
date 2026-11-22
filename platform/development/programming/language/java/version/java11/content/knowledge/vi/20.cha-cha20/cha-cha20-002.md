# ChaCha20-Poly1305 và mã hóa có xác thực (Java 11)

**ChaCha20-Poly1305** là một thuật toán **mã hóa có xác thực với dữ liệu liên kết** (*Authenticated Encryption with Associated Data — AEAD*). Nó kết hợp **ChaCha20** để mã hóa nội dung và **Poly1305** để kiểm tra tính xác thực/toàn vẹn. Mục đích là bảo vệ đồng thời **tính bí mật** của plaintext và **phát hiện thay đổi trái phép** đối với ciphertext hoặc metadata được xác thực.

Từ **Java 11**, JDK có hỗ trợ ChaCha20 và ChaCha20-Poly1305 thông qua Java Cryptography Architecture/Extension (JCA/JCE), thường được sử dụng qua `javax.crypto.Cipher`:

```java
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
```

Đây là **đoạn mã bên trong phương thức**, có import `javax.crypto.Cipher` và xử lý checked exception. Chỉ tạo `Cipher` **chưa mã hóa dữ liệu**: phải khởi tạo khóa, nonce, AAD và gọi `doFinal`.

**Quan trọng nhất:** với một khóa ChaCha20-Poly1305, **không bao giờ mã hóa hai thông điệp bằng cùng một nonce**. Tái sử dụng cặp **(key, nonce)** có thể làm lộ quan hệ giữa plaintext và phá hỏng các bảo đảm an toàn của chế độ AEAD. Cũng không được bỏ qua lỗi xác thực chỉ để “lấy được plaintext”.

Bài thuộc nhóm **ChaCha20** của Java 11, chỉ trình bày những cơ chế/API vẫn có giá trị trên JDK được bảo trì ngày nay. Hãy sử dụng một JDK có cập nhật bảo mật phù hợp và biên dịch mẫu bằng `javac --release 11` nếu compiler hỗ trợ. Ví dụ dùng provider JCE có hỗ trợ transformation `ChaCha20-Poly1305`; các provider/JVM khác phải được kiểm tra khả năng hỗ trợ thực tế.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **mã hóa thuần ChaCha20** với **ChaCha20-Poly1305 có xác thực**.
2. Giải thích các tham số chuẩn của AEAD ChaCha20-Poly1305: **khóa 32 byte**, **nonce 12 byte**, **authentication tag 16 byte**, plaintext và AAD tùy ý.
3. Dùng `KeyGenerator.getInstance("ChaCha20")`, `Cipher.getInstance("ChaCha20-Poly1305")`, `IvParameterSpec`, `updateAAD` và `doFinal` trong Java 11.
4. Thiết kế định dạng lưu/gửi kết quả gồm **version, nonce, ciphertext và tag**; hiểu nonce không cần giữ bí mật.
5. Giải mã với **cùng khóa, nonce, AAD**; nếu `AEADBadTagException` xảy ra thì từ chối dữ liệu.
6. Bảo đảm AAD được đưa vào **trước nội dung** và được tái tạo đúng từng byte khi giải mã.
7. Nhận diện rủi ro nonce reuse, thay đổi AAD, key rotation, replay attack và phát hành plaintext trước khi xác thực.
8. Viết test cho tamper ciphertext, tag, nonce, AAD, sai khóa, sai version, frame quá ngắn và plaintext rỗng.
9. Kiểm tra kết quả với **test vector RFC 8439** thay vì chỉ dựa vào round-trip tự mã hóa rồi tự giải mã.
10. Phân biệt khả năng bảo vệ của AEAD với các yêu cầu giao thức bên ngoài như xác minh danh tính, phân quyền và chống phát lại.

## 2. Tại sao chỉ ChaCha20 là chưa đủ?

ChaCha20 là **stream cipher**: nó tạo một keystream từ khóa/nonce/counter rồi XOR với plaintext để tạo ciphertext. Nếu chỉ dùng ChaCha20 thuần:

```text
plaintext    XOR keystream(key, nonce, counter) = ciphertext
ciphertext   XOR cùng keystream              = plaintext
```

Điều này **giữ bí mật** nội dung khi sử dụng đúng khóa/nonce. Nhưng kẻ tấn công có thể thay đổi một số bit của ciphertext và gây thay đổi có thể dự đoán ở plaintext sau giải mã, bởi **không có authentication tag để phát hiện**.

Với ChaCha20-Poly1305:

```text
                  KHÓA 256 BIT
                      |
         +------------+------------+
         |                         |
         v                         v
 ChaCha20 mã hóa            Sinh khóa Poly1305
 plaintext                  một lần từ key+nonce
         |                         |
         v                         v
    ciphertext ---------+---- AAD (không mã hóa)
                        |       |
                        v       v
                    Poly1305 xác thực
                        |
                        v
                 TAG 128 BIT
                        |
                        v
              ciphertext || tag

GIẢI MÃ:
  Xác minh tag cho ciphertext + AAD theo cùng key/nonce
  Chỉ chấp nhận plaintext khi xác thực thành công
```

Trong construction chuẩn RFC 8439, **block counter 0** được dùng để tạo khóa Poly1305 một lần, còn dữ liệu ChaCha20 bắt đầu từ **block counter 1**. Khi gọi transformation AEAD Java, **provider tự thực hiện phần này** — ứng dụng **không** cung cấp counter thủ công cho `ChaCha20-Poly1305`.

### So sánh hai API

| Tiêu chí | `ChaCha20` | `ChaCha20-Poly1305` |
| --- | --- | --- |
| Loại | Stream cipher | AEAD |
| Bảo mật nội dung | Có khi cấu hình đúng | Có |
| Kiểm tra ciphertext bị sửa | **Không tích hợp** | Có, với tag Poly1305 |
| Hỗ trợ AAD | Không ở chế độ thuần | **Có** |
| Yêu cầu nonce duy nhất theo khóa | Có | **Có, bắt buộc** |
| Output | Ciphertext bằng số byte plaintext | Ciphertext cùng độ dài plaintext **+ tag 16 byte** |
| Tham số Java phổ biến | `ChaCha20ParameterSpec` (nonce/counter) | **`IvParameterSpec` (nonce 12 byte)** |
| Khuyến nghị cho dữ liệu ứng dụng cần bí mật và toàn vẹn | Cần tự xây authentication an toàn, không nên làm thủ công | **Ưu tiên AEAD đúng hợp đồng** |

Không tự ghép “ChaCha20 + một hash” rồi coi đó là authenticated encryption. Poly1305 trong construction AEAD có quy tắc sinh khóa một lần, thứ tự AAD/ciphertext, padding và phần mã hóa độ dài đã được chuẩn hóa; hãy dùng **implementation có kiểm thử** của provider thay vì tự viết primitive.

## 3. Năm đầu vào quan trọng

RFC 8439 `2.8 xác định các thành phần:

| Thành phần | Độ dài/loại | Ai quản lý? |
| --- | --- | --- |
| **Secret key** | **32 byte = 256 bit** | Giữ bí mật; tạo bằng nguồn ngẫu nhiên mạnh hoặc cơ chế quản lý khóa được phê duyệt |
| **Nonce (IV)** | **12 byte = 96 bit** | **Duy nhất cho mỗi lần mã hóa dưới cùng khóa**; được phép lưu/gửi công khai |
| **Plaintext** | Dữ liệu cần giữ bí mật | Input của ứng dụng, trước mã hóa |
| **AAD** | Bytes metadata cần xác thực nhưng **không mã hóa** | Hai bên phải biết đúng cùng bytes; có thể rỗng |
| **Authentication tag** | **16 byte = 128 bit** | Provider tính khi mã hóa và kiểm tra khi giải mã |

### Nonce có bí mật không?

**Không.** Nonce có thể được đặt ở phần đầu bản tin cùng với ciphertext. Nhưng nonce phải **duy nhất trong phạm vi một khóa** khi mã hóa. Một nonce không thể đoán trước **không đủ** nếu nó bị lặp.

- Với workload nhỏ/giới hạn, ví dụ thực hành có thể tạo nonce ngẫu nhiên 12 byte bằng `SecureRandom`.
- Với hệ thống gửi rất nhiều thông điệp hoặc nhiều process dùng cùng khóa, cần chính sách **không thể trùng** đáng tin cậy hơn: ví dụ định danh sender được phân vùng trong nonce + counter được quản lý và lưu bền vững, hoặc sinh khóa phiên riêng cho từng sender/epoch.
- Sau restart, **không** reset counter về 0 và tiếp tục dùng cùng khóa nếu điều đó làm nonce lặp.
- Thay khóa **không** chữa được ciphertext đã được mã hóa với key/nonce bị lặp. Khi phát hiện reuse, cần ứng phó sự cố và đánh giá dữ liệu đã ảnh hưởng.

Xác suất collision với nonce ngẫu nhiên 96 bit có thể nhỏ trong tập dữ liệu hạn chế, **nhưng không phải bằng 0**. Không gọi cách đó là “bảo đảm không bao giờ trùng”. Đặc tả yêu cầu **uniqueness**, vì thế thiết kế nonce phải phù hợp quy mô và mô hình vận hành.

### AAD dùng để làm gì?

Ví dụ ciphertext chứa thông tin tài khoản, còn metadata ghi:

```text
tenant=7;type=profile;v=1
```

Nếu bạn muốn metadata này **không bị thay đổi mà vẫn giải mã thành công**, đưa **bytes chính xác** của nó vào `cipher.updateAAD(aadBytes)` ở cả hai phía. AAD được xác thực **nhưng không được mã hóa**, nên nội dung AAD không phải thông tin bí mật.

Các ví dụ phù hợp để bind bằng AAD:

- Mã tenant hoặc principal được ủy quyền.
- Loại bản ghi/domain context để chống dùng ciphertext sai mục đích.
- Phiên bản schema/protocol.
- Một phần header định tuyến cần bảo vệ chống sửa.
- ID đối tượng hoặc version nhằm ràng buộc ciphertext với record.

**Không đặt bí mật vào AAD** nếu nó sẽ bị lưu hoặc gửi công khai, vì AEAD không che giấu AAD. **Không dùng AAD để thay thế phân quyền**: server vẫn phải kiểm tra người dùng có quyền truy cập tenant/record hay không.

### AAD phải được canonicalize

Hai chuỗi “có ý nghĩa tương tự” chưa chắc có cùng bytes. Ví dụ:

```text
tenant=7;type=profile;v=1
type=profile;tenant=7;v=1
```

Sự thay đổi thứ tự ký tự dẫn đến AAD bytes khác và **tag không khớp**. Với metadata phức tạp, nên có **định dạng canonical có version**, cố định charset (thường UTF-8), kiểu và độ dài/trật tự trường, và kiểm thử ở hai đầu. Đừng dựa vào `Map.toString()`, thứ tự duyệt map không có hợp đồng hoặc JSON serialization tùy ý để tạo AAD.

## 4. Java 11 JCE API cần nhớ

Đoạn mã đúng cho ChaCha20-Poly1305:

```java
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
cipher.init(Cipher.ENCRYPT_MODE, secretKey,
        new IvParameterSpec(nonce12Bytes));
cipher.updateAAD(aadBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintextBytes);
```

Đây là **snippet bên trong phương thức** đã có `SecretKey secretKey`, `byte[] nonce12Bytes`, `aadBytes` và `plaintextBytes`; cần imports `Cipher`, `IvParameterSpec` và xử lý `GeneralSecurityException`.

**Chú ý khác biệt của Java 11:**

- `Cipher.getInstance("ChaCha20-Poly1305")` dùng đúng tên transformation của AEAD.
- `KeyGenerator.getInstance("ChaCha20")` hoặc `SecretKeySpec(key32, "ChaCha20")` cung cấp khóa 256 bit.
- `new IvParameterSpec(nonce12)` là tham số nonce phù hợp với **ChaCha20-Poly1305** trong JDK SunJCE.
- `ChaCha20ParameterSpec(nonce, counter)` dành cho ChaCha20 stream cipher **thuần**, không phải tham số bạn cần để điều khiển bộ đếm AEAD.
- `updateAAD` phải được gọi **trước** khi xử lý plaintext/ciphertext bằng `update` hoặc `doFinal`.
- `doFinal` của mã hóa AEAD tạo output chứa **ciphertext nối với 16 byte tag** theo provider chuẩn.
- Khi giải mã, `doFinal` nhận **ciphertext+tag**, cùng nonce và AAD; nếu tag sai, ném **`AEADBadTagException`**.

**Không dùng `GCMParameterSpec` cho ChaCha20-Poly1305.** `GCMParameterSpec` dành cho AES-GCM. Hai AEAD có thể bảo vệ mục đích tương tự nhưng sử dụng transformation và parameter specification khác nhau.

### Không cần tự tính Poly1305 tag

Java provider quản lý Poly1305 key generation, padding theo 16 byte, mã hóa độ dài AAD/ciphertext và so sánh tag. App không nên tự cắt tag rồi so sánh bằng `Arrays.equals` hay so sánh chuỗi hex. Hãy giao full ciphertext+tag cho provider để verify.

Không truncate tag nhằm giảm số byte truyền; RFC 8439 yêu cầu sử dụng **đủ 16 byte tag**.

## 5. Ví dụ 1 — chương trình hoàn chỉnh mã hóa, giải mã và từ chối sửa đổi

Chương trình sau thực hiện:

1. Sinh một **khóa ChaCha20 256 bit**.
2. Mỗi lần mã hóa tạo một nonce mới bằng `SecureRandom` trong phạm vi demo.
3. Tạo frame `version (1 byte) || nonce (12 byte) || ciphertext || tag (16 byte)`.
4. Giải mã với cùng key và AAD.
5. Chủ động sửa ciphertext, tag, nonce, AAD; thử khóa sai và version không hỗ trợ để xác nhận **fail closed**.
6. Thử plaintext rỗng: ciphertext không có byte nhưng **vẫn có tag**.

Tạo file **`AeadRoundTripDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class AeadRoundTripDemo {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BYTES = 16;
    private static final int MAX_FRAME_BYTES = 1_048_576;
    private static final byte VERSION = 1;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] seal(byte[] plaintext, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        Cipher encryptor = Cipher.getInstance("ChaCha20-Poly1305");
        encryptor.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        encryptor.updateAAD(aad);
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);
        return ByteBuffer.allocate(1 + NONCE_BYTES + ciphertextAndTag.length)
                .put(VERSION).put(nonce).put(ciphertextAndTag).array();
    }

    static byte[] open(byte[] frame, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        if (frame == null
                || frame.length < 1 + NONCE_BYTES + TAG_BYTES
                || frame.length > MAX_FRAME_BYTES) {
            throw new IllegalArgumentException("Invalid frame size");
        }

        ByteBuffer input = ByteBuffer.wrap(frame);
        if (input.get() != VERSION) {
            throw new IllegalArgumentException("Unsupported frame version");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher decryptor = Cipher.getInstance("ChaCha20-Poly1305");
        decryptor.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        decryptor.updateAAD(aad);
        return decryptor.doFinal(ciphertextAndTag);
    }

    static boolean tagRejected(byte[] frame, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        try {
            open(frame, key, aad);
            return false;
        } catch (AEADBadTagException ex) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();
        SecretKey otherKey = generator.generateKey();
        byte[] aad = "tenant=7;type=profile;v=1".getBytes(
                StandardCharsets.UTF_8);
        byte[] plaintext = "Sensitive payload".getBytes(
                StandardCharsets.UTF_8);

        byte[] frame = seal(plaintext, key, aad);
        System.out.println("Plaintext restored: " +
                new String(open(frame, key, aad),
                        StandardCharsets.UTF_8));
        System.out.println("Envelope version: " + frame[0]);
        System.out.println("Nonce length: " + NONCE_BYTES);
        System.out.println("Authentication tag length: " +
                (frame.length - 1 - NONCE_BYTES - plaintext.length));

        byte[] changedCiphertext = frame.clone();
        changedCiphertext[1 + NONCE_BYTES] ^= 1;
        System.out.println("Tampered ciphertext rejected: " +
                tagRejected(changedCiphertext, key, aad));

        byte[] changedTag = frame.clone();
        changedTag[changedTag.length - 1] ^= 1;
        System.out.println("Tampered tag rejected: " +
                tagRejected(changedTag, key, aad));

        byte[] otherAad = "tenant=8;type=profile;v=1".getBytes(
                StandardCharsets.UTF_8);
        System.out.println("Wrong AAD rejected: " +
                tagRejected(frame, key, otherAad));

        byte[] changedNonce = frame.clone();
        changedNonce[1] ^= 1;
        System.out.println("Wrong nonce rejected: " +
                tagRejected(changedNonce, key, aad));
        System.out.println("Wrong key rejected: " +
                tagRejected(frame, otherKey, aad));

        byte[] changedVersion = frame.clone();
        changedVersion[0] = 2;
        boolean versionRejected;
        try {
            open(changedVersion, key, aad);
            versionRejected = false;
        } catch (IllegalArgumentException expected) {
            versionRejected = true;
        }
        System.out.println("Unsupported version rejected: " +
                versionRejected);

        byte[] empty = new byte[0];
        byte[] emptyFrame = seal(empty, key, aad);
        System.out.println("Empty plaintext round-trip: " +
                Arrays.equals(empty, open(emptyFrame, key, aad)));
        System.out.println("Empty plaintext ciphertext+tag bytes: " +
                (emptyFrame.length - 1 - NONCE_BYTES));
    }
}
```

### Biên dịch và chạy

Với JDK đang được cập nhật và compiler hỗ trợ API Java 11:

```sh
javac --release 11 -encoding UTF-8 AeadRoundTripDemo.java
java AeadRoundTripDemo
```

**Stdout chính xác** (khóa và nonce khác mỗi lượt nhưng chương trình không in chúng):

```text
Plaintext restored: Sensitive payload
Envelope version: 1
Nonce length: 12
Authentication tag length: 16
Tampered ciphertext rejected: true
Tampered tag rejected: true
Wrong AAD rejected: true
Wrong nonce rejected: true
Wrong key rejected: true
Unsupported version rejected: true
Empty plaintext round-trip: true
Empty plaintext ciphertext+tag bytes: 16
```

### Phân tích từng bước

**Sinh khóa.** `KeyGenerator.getInstance("ChaCha20")` tạo khóa được provider hỗ trợ. `generator.init(256)` đặt kích thước 256 bit theo thuật toán. Ở chương trình học, khóa chỉ sống trong bộ nhớ lúc chạy; trong ứng dụng thật cần giải pháp lưu/luân chuyển khóa và backup được tổ chức phê duyệt.

**Tạo nonce mới.** `new byte[12]` rồi `SecureRandom.nextBytes` tạo một giá trị mới cho mỗi lần mã hóa. Đây là ví dụ ngắn phù hợp bài học. Với workload cao, multi-writer hoặc các bản tin dùng chung khóa lâu dài, cần một **nonce allocation scheme bảo đảm uniqueness** thay vì dựa duy nhất vào xác suất ngẫu nhiên.

**Mã hóa.** `Cipher.ENCRYPT_MODE`, `IvParameterSpec(nonce)`, `updateAAD(aad)` trước `doFinal(plaintext)`. `doFinal` trả bytes đã được mã hóa **và 16 byte authentication tag**.

**Đóng gói.** Frame có:

```text
0             1                       13                       END
+-------------+-----------------------+-------------------------+
| version (1) | nonce (12)            | ciphertext || tag       |
+-------------+-----------------------+-------------------------+
                                             ...  | tag (16)
```

Một version giúp parser từ chối định dạng chưa hiểu. Với **format production**, nên định nghĩa thêm algorithm ID/key ID nếu có rotation, giới hạn bản tin và **đưa các header cần bảo vệ (bao gồm version) vào AAD** hoặc một cấu trúc đã xác thực. Demo bind `v=1` trong AAD truyền ngoài, nhưng **không tự xác thực trực tiếp byte version trong frame**; đổi version sang giá trị không hỗ trợ được parser từ chối trước giải mã. Nếu định nghĩa nhiều version trong tương lai, phải thiết kế rõ ràng chống cross-version/cross-protocol confusion.

**Giải mã.** `open` kiểm tra độ dài, version, đọc nonce, lấy ciphertext+tag, khởi tạo `Cipher.DECRYPT_MODE` với cùng khóa/nonce, cung cấp đúng AAD rồi `doFinal`. Không tự tách/so tag bằng một hàm bên ngoài.

**Kiểm thử sửa dữ liệu.** Lật một bit ở ciphertext hoặc tag, đổi AAD, nonce, khóa đều khiến provider phát hiện xác thực thất bại và ném `AEADBadTagException`. Test chỉ trả `true` khi nhận **đúng loại lỗi xác thực**. Khi version không được hỗ trợ, parser trả lỗi cấu trúc, không giả vờ rằng đây là một authentication tag failure.

**Plaintext rỗng.** AEAD vẫn xác thực một message có payload 0 byte: `doFinal(empty)` tạo **16 byte tag**. Với envelope này, tổng frame là `1 + 12 + 16 = 29` byte. Chấp nhận plaintext rỗng hay không là **quy tắc ứng dụng**, không phải điều kiện luôn cấm của thuật toán.

### Giới hạn có chủ đích của ví dụ

- `MAX_FRAME_BYTES` là giới hạn **đầu vào khi giải mã**; `seal` chưa áp giới hạn output. Production cần kiểm tra giới hạn **cả trước mã hóa và trước cấp phát**.
- `SecureRandom` nonce trong demo có rủi ro collision cực nhỏ nhưng **không phải bảo đảm uniqueness toàn hệ thống**. Thiết kế hệ thống dùng chung khóa giữa nhiều process cần nonce manager/counter phù hợp.
- `key` chỉ là khóa tạm một lần chạy. Dữ liệu muốn giải mã lâu dài cần key lifecycle và key ID/rotation phù hợp.
- AAD trong demo là metadata do caller truyền vào, không được lưu trong frame. Ở hệ thống thật, phải bảo đảm receiver tái tạo **cùng bytes AAD** đúng đối tượng; có thể truyền các trường public cùng message và xác thực chúng.
- Demo dùng `byte[]` nên toàn bộ plaintext/ciphertext được giữ trong RAM. Với file lớn, cần thiết kế streaming AEAD có giới hạn/record framing, không tùy tiện xuất plaintext trước khi xác thực thành công.
- **Không có phát hiện replay** nếu người khác gửi lại nguyên frame/AAD hợp lệ: AEAD xác thực nhưng không tự phân biệt lần dùng đầu và lần phát lại.

## 6. `AEADBadTagException`: fail closed thay vì dùng plaintext sai

Nếu decrypt gặp tag không hợp lệ:

```java
try {
    byte[] plaintext = decryptor.doFinal(ciphertextAndTag);
    // Chỉ xử lý plaintext khi doFinal thành công.
} catch (AEADBadTagException invalid) {
    // Từ chối toàn bộ message; không sử dụng plaintext chưa xác thực.
}
```

Đây là **snippet trong phương thức** đã khởi tạo `Cipher decryptor` và có `byte[] ciphertextAndTag`. Không phải chương trình độc lập.

Lý do `AEADBadTagException` có thể xảy ra:

- Ciphertext đã bị sửa.
- Authentication tag bị sửa hoặc bị cắt.
- Khóa sai.
- Nonce sai.
- AAD sai, thứ tự hoặc encoding khác.
- Payload được giải mã theo sai transformation/schema hoặc frame bị hỏng.

**Không nên đưa ra thông tin chi tiết kiểu “khóa đúng nhưng ciphertext sai” cho bên gửi không tin cậy.** Thông báo ở ranh giới API nên là lỗi xác thực/không thể giải mã chung, còn diagnostics nội bộ phải hạn chế nội dung nhạy cảm để tránh oracle và lộ metadata. Không ghi plaintext, raw key, nonce mapping nhạy cảm hoặc tag của dữ liệu sản xuất một cách tùy tiện.

**Không bắt `AEADBadTagException` rồi trả plaintext rỗng, dữ liệu mặc định hoặc một kết quả thành công.** Điều này biến sai lệch bảo mật thành dữ liệu có vẻ hợp lệ.

### Vì sao `update` trong AEAD cần thận trọng?

Một số cách xử lý streaming có thể trả **dữ liệu tạm** khi gọi `Cipher.update` trước khi `doFinal` xác minh tag. Không được ghi hoặc xử lý có tác dụng không thể đảo ngược dựa trên plaintext chưa xác thực. Cách an toàn đơn giản cho bản tin nhỏ là **giữ toàn bộ ciphertext+tag và chỉ giải phóng plaintext sau khi `doFinal` thành công**, như demo.

Nếu dữ liệu lớn bắt buộc streaming, hãy dùng **giao thức record-based AEAD** có mỗi record một nonce duy nhất, AAD liên kết vị trí/sequence, giới hạn record, chống mất/đảo/trùng record và **chỉ xuất bản record sau khi tag của chính record đó được kiểm tra**. Không tự cắt một ciphertext AEAD lớn thành nhiều phần rồi giải mã độc lập bằng cùng nonce.

## 7. Ví dụ 2 — kiểm chứng bằng test vector RFC 8439

Round-trip tự mã hóa rồi tự giải mã **không chứng minh triển khai liên thông đúng chuẩn**: cùng một bug ở hai chiều có thể vô tình “khớp nhau”. Một **known-answer test (KAT)** đối chiếu bytes chính xác với vector của RFC 8439 mạnh hơn.

RFC 8439 `2.8.2 cung cấp:

- Key 32 byte: từ hex `80` đến `9f`.
- Nonce 12 byte: `070000004041424344454647`.
- AAD 12 byte: `50515253c0c1c2c3c4c5c6c7`.
- Plaintext ASCII dài **114 byte**.
- Ciphertext dài **114 byte**, tag **16 byte**.
- Tag chuẩn: `1ae10b594f09e26a7e902ecbd0600691`.

**Khóa/nonce cố định ở phần này CHỈ dùng cho phép thử chuẩn**, hoàn toàn không dùng làm key/nonce của dữ liệu thật. Mục đích là so sánh vector, không phải sinh ciphertext an toàn cho nhiều bản tin.

Tạo file **`Rfc8439VectorDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class Rfc8439VectorDemo {
    static byte[] hex(String text) {
        if ((text.length() & 1) != 0) {
            throw new IllegalArgumentException("Odd hex length");
        }
        byte[] result = new byte[text.length() / 2];
        for (int i = 0; i < result.length; i++) {
            int hi = Character.digit(text.charAt(2 * i), 16);
            int lo = Character.digit(text.charAt(2 * i + 1), 16);
            if (hi < 0 || lo < 0) {
                throw new IllegalArgumentException("Bad hex digit");
            }
            result[i] = (byte) ((hi << 4) | lo);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        byte[] key = hex(
                "808182838485868788898a8b8c8d8e8f"
                + "909192939495969798999a9b9c9d9e9f");
        byte[] nonce = hex("070000004041424344454647");
        byte[] aad = hex("50515253c0c1c2c3c4c5c6c7");
        byte[] plaintext = ("Ladies and Gentlemen of the class of '99: "
                + "If I could offer you only one tip for the future, "
                + "sunscreen would be it.").getBytes(StandardCharsets.US_ASCII);
        byte[] expected = hex(
                "d31a8d34648e60db7b86afbc53ef7ec2"
                + "a4aded51296e08fea9e2b5a736ee62d6"
                + "3dbea45e8ca9671282fafb69da92728b"
                + "1a71de0a9e060b2905d6a5b67ecd3b36"
                + "92ddbd7f2d778b8c9803aee328091b58"
                + "fab324e4fad675945585808b4831d7bc"
                + "3ff4def08e4b7a9de576d26586cec64b"
                + "6116"
                + "1ae10b594f09e26a7e902ecbd0600691");

        SecretKeySpec secret = new SecretKeySpec(key, "ChaCha20");
        Cipher encryptor = Cipher.getInstance("ChaCha20-Poly1305");
        encryptor.init(Cipher.ENCRYPT_MODE, secret,
                new IvParameterSpec(nonce));
        encryptor.updateAAD(aad);
        byte[] produced = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance("ChaCha20-Poly1305");
        decryptor.init(Cipher.DECRYPT_MODE, secret,
                new IvParameterSpec(nonce));
        decryptor.updateAAD(aad);
        byte[] recovered = decryptor.doFinal(produced);

        System.out.println("RFC 8439 vector matched: " +
                Arrays.equals(expected, produced));
        System.out.println("Ciphertext bytes: " +
                (produced.length - 16));
        System.out.println("Tag bytes: 16");
        System.out.println("Round-trip matched: " +
                Arrays.equals(plaintext, recovered));
    }
}
```

### Chạy và kiểm tra đầu ra

```sh
javac --release 11 -encoding UTF-8 Rfc8439VectorDemo.java
java Rfc8439VectorDemo
```

**Stdout chính xác:**

```text
RFC 8439 vector matched: true
Ciphertext bytes: 114
Tag bytes: 16
Round-trip matched: true
```

Bài kiểm tra này xác nhận implementation tạo **114 byte ciphertext + 16 byte tag đúng toàn bộ test vector chuẩn RFC 8439**, không chỉ xác nhận rằng hai phương thức local tương thích nhau. Chỉ cần khác một byte ciphertext/tag, kết quả `Arrays.equals(expected, produced)` sẽ là `false`.

**Khi kiểm thử liên thông với hệ thống khác**, bảo đảm hai bên dùng đúng:
- Biến thể **IETF ChaCha20-Poly1305** với nonce 96 bit.
- Cùng thứ tự và độ dài ciphertext/tag (tag nối sau ciphertext theo giao kèo).
- AAD bytes giống nhau.
- Cùng key/nonce.
- Cùng format version, charset, encoding và các trường AAD được xác thực.

Không nhầm với **XChaCha20-Poly1305** (nonce thường 24 byte, một construction khác), hoặc cơ chế `ChaCha20` thuần có tham số counter riêng. Một format hợp lệ cho biến thể này **không tự liên thông** với biến thể khác.

## 8. Định dạng bản tin và quản lý version, key ID

Một bản tin mã hóa chỉ có ciphertext không đủ để bên nhận biết nonce, thuật toán/phiên bản và khóa giải mã tương ứng. Có thể xây **envelope** có format version.

Ví dụ đơn giản của demo:

```text
[ version: 1 byte ][ nonce: 12 bytes ][ ciphertext: N bytes ][ tag: 16 bytes ]
```

Trong một hệ thống có key rotation, có thể cân nhắc:

```text
[ magic / format version ]
[ algorithm / key-id ]
[ nonce: 12 bytes ]
[ ciphertext: N bytes ]
[ tag: 16 bytes ]
```

**Mọi định dạng thật phải có đặc tả rõ ràng** về field sizes, byte order, maximum payload, charset, nonce policy, AAD, key lookup và cách xác thực header.

### Header nào cần được đưa vào AAD?

Những thông tin ảnh hưởng tới cách sử dụng ciphertext cần được **xác thực**, ví dụ:

- Format version và algorithm identity, để tránh nhầm giao thức/phiên bản.
- Tenant/context hoặc purpose string.
- Object ID, record type, schema version.
- Nonce domain/sender ID nếu nó liên quan khả năng tạo nonce duy nhất.
- Sequence number nếu cần chống reorder/replay.
- Key ID nếu muốn bảo vệ mối liên kết giữa metadata và ciphertext (và phải xử lý vòng phụ thuộc khi chọn key).

Một phương án là **encode header canonical**, rồi dùng nguyên bytes header làm AAD, sau đó append ciphertext+tag. Khi giải mã, trước tiên chỉ đọc tối thiểu header trong một parser an toàn, chọn key theo chính sách, dựng lại đúng AAD bytes từ header rồi mới gọi `doFinal`. Tuyệt đối không tin header chưa được xác thực để quyết định cấp quyền, thao tác tài chính hoặc hiển thị dữ liệu mật.

### Key ID có phải secret?

Thông thường **key ID là metadata**, có thể xuất hiện công khai, nhưng nó vẫn có thể tiết lộ thông tin vận hành. Không chứa secret key, passphrase, raw password hoặc thông tin nhạy cảm không cần thiết trong key ID. Áp access control và audit với key lookup; không trả log chi tiết về key nội bộ cho caller không tin cậy.

## 9. Nonce reuse: lỗi nghiêm trọng nhất

Một nonce **duy nhất theo khóa** là invariant bảo mật, không chỉ là một tham số giúp code chạy.

| Tình huống | Đánh giá |
| --- | --- |
| Cùng key, **nonce mới**, plaintext mới | Đúng điều kiện cơ bản nếu metadata/policy hợp lệ |
| Cùng key, **nonce cũ**, plaintext khác | **Sai nghiêm trọng**; có thể lộ XOR plaintext và tạo điều kiện giả mạo |
| Cùng key, **nonce cũ**, plaintext giống hệt | Vẫn **không phải chính sách mã hóa được khuyến nghị**; hệ thống không được phụ thuộc tái sử dụng nonce |
| Khác key, nonce có thể cùng giá trị | Không vi phạm ràng buộc duy nhất **theo từng key**, nếu các key độc lập đúng cách |
| Khác process dùng cùng key và cùng counter 0 | **Sai** nếu dẫn tới trùng nonce |
| Crash/restart làm counter quay về 0 trong khi key còn cũ | **Sai** nếu tái sử dụng nonce |
| Gửi lại một ciphertext **đã mã hóa sẵn**, không mã hóa lại | Không tạo lần mã hóa mới, nhưng vẫn cần **chống replay** ở protocol/application layer |
| Dùng `SecureRandom` 12 byte với rất nhiều message | Phải đánh giá birthday-bound collision và vòng đời key; không tuyệt đối bảo đảm không trùng |

### Một nonce manager phù hợp cho production

Có thể thiết kế theo hướng:

1. Mỗi key có một **nonce namespace** rõ ràng.
2. Nếu nhiều writer dùng cùng key, cấp các miền nonce khác nhau (sender ID/partition) hoặc cấp key khác nhau.
3. Dùng **counter bền vững/atomic** không bị reset khi process restart, có ngăn overflow và crash consistency.
4. Nếu sử dụng nonce ngẫu nhiên, **giới hạn số bản tin theo key**, đánh giá xác suất collision và key rotation theo tiêu chuẩn bảo mật áp dụng.
5. Không chia sẻ key rộng hơn cần thiết; bảo vệ key ID, quyền phát hành, lưu trữ và rotation.
6. Giám sát khả năng phát hiện counter rollback và lỗi cấp phát nonce.

**Không được lấy thời gian mili giây đơn thuần làm nonce.** Nhiều thread/process có thể mã hóa trong cùng một millisecond; đồng hồ có thể nhảy lùi; và cùng key có thể tồn tại qua restart.

### Tại sao lỗi nonce reuse không chỉ là “hai ciphertext giống nhau”?

Vì ChaCha20 là stream cipher, hai message mã hóa bằng **cùng key và nonce** sử dụng cùng keystream. XOR hai ciphertext có thể làm lộ XOR hai plaintext, làm giảm mạnh tính bí mật. Đồng thời, khóa Poly1305 one-time cũng có nguy cơ bị tái sử dụng, gây hậu quả đối với authentication. **Không cố thử “sửa” bằng cách thêm AAD ngẫu nhiên**: AAD khác không làm keystream và Poly1305 key trở nên độc lập khi key/nonce trùng.

## 10. Khóa: sinh, lưu, xoay vòng và giới hạn truy cập

### Sinh khóa

`KeyGenerator.getInstance("ChaCha20")` có hỗ trợ trong JDK provider tương ứng:

```java
KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256);
SecretKey secretKey = generator.generateKey();
```

Đây là snippet trong phương thức, với imports `KeyGenerator`/`SecretKey` và checked exception. Khóa phải được tạo từ nguồn tin cậy; **không** tạo từ một password bằng `password.getBytes()` rồi cắt/đệm cho đủ 32 byte.

Nếu muốn lấy khóa từ mật khẩu do người dùng nhập, cần một **password-based key derivation function** được phê duyệt và cấu hình phù hợp, với salt và chi phí đủ cao, trước khi sử dụng khóa cho AEAD. Không tự viết một vòng SHA-256 đơn giản rồi gọi là KDF an toàn.

### Lưu khóa

- Ưu tiên KMS/HSM, secret manager hoặc keystore phù hợp với mức độ bảo vệ của hệ thống.
- Không hardcode secret key vào source code, repo, test fixture production, cấu hình được công bố hoặc log.
- Không lưu **secret key cùng ciphertext** theo định dạng mà người không được phép truy cập có thể đọc cả hai.
- Có version/key ID và kế hoạch decrypt dữ liệu cũ sau rotation.
- Phân quyền rõ ứng dụng nào được mã hóa/giải mã dưới từng key.
- Không in `secretKey.getEncoded()`, ciphertext giải mã hoặc toàn bộ memory dump khi xảy ra exception.

### Xoay vòng khóa

Key rotation phải bảo đảm:

1. Key mới được tạo và cấp phát nonce riêng đúng policy.
2. Dữ liệu cũ còn cần đọc được được map tới key cũ (trong thời gian cho phép).
3. App không giải mã nhầm bằng key không đúng.
4. Key cũ được thu hồi/loại bỏ khi không còn dữ liệu cần giữ hoặc theo chính sách.
5. Có quy trình ứng phó khi phát hiện nonce reuse hoặc lộ key, bao gồm đánh giá và có thể mã hóa lại dữ liệu.

Cần phân biệt **rotation theo lịch** với **compromise response**: nếu key bị lộ, đổi key cho dữ liệu mới không tự phục hồi sự bí mật của dữ liệu đã bị đọc bởi kẻ tấn công.

## 11. AAD và identity: mã hóa không phải phân quyền

Một ví dụ quan trọng: ứng dụng có tenant A và tenant B, cùng backend lưu ciphertext. Để tránh nhầm mục đích dữ liệu, có thể đưa `tenantId`, `recordId`, `recordType` vào AAD.

Khi đọc:

1. Ứng dụng **kiểm tra quyền** của caller với tenant/record được yêu cầu.
2. Xác định key đúng theo chính sách.
3. Xây đúng AAD canonical từ ngữ cảnh **đã được kiểm tra quyền**.
4. Giải mã với nonce/ciphertext/tag của envelope.
5. Chỉ trả plaintext nếu `doFinal` thành công và domain validation cũng đạt.

Nếu attacker tráo ciphertext giữa tenant, AAD phải khác và tag sẽ không khớp, **khi key và format được thiết kế đúng**. Nhưng AEAD không tự kiểm tra login, role, quyền truy cập DB hoặc quyền tạo bản ghi. Việc xác thực tag thành công **không** thay thế authorization.

### Replay protection nằm ngoài AEAD

Kẻ tấn công có thể lấy nguyên `version||nonce||ciphertext||tag` hợp lệ rồi gửi lại. Tag vẫn xác thực thành công. Vì vậy, nếu protocol có side effect như thanh toán hoặc cập nhật tồn kho:

- Đưa operation ID/sequence number vào một cấu trúc được AAD xác thực.
- Server kiểm tra **nonce/operation ID đã sử dụng** hoặc sequence monotonic theo một replay window phù hợp.
- Chú ý tính nguyên tử giữa kiểm tra replay ID và commit nghiệp vụ.
- Không chỉ dựa vào “nonce khác mỗi lần mã hóa” để chặn việc **gửi lại ciphertext cũ**.

AEAD bảo vệ **tính xác thực của nội dung**, không tự bảo đảm **tính mới (freshness)** của một message trong business workflow.

## 12. So sánh ChaCha20-Poly1305 với AES-GCM

Cả ChaCha20-Poly1305 và AES-GCM đều là **AEAD** và được sử dụng trong nhiều giao thức hiện đại. Không có kết luận tuyệt đối “một cái tốt hơn” cho mọi nền tảng.

| Tiêu chí | ChaCha20-Poly1305 | AES-GCM |
| --- | --- | --- |
| Mã hóa | ChaCha20 stream cipher | AES block cipher ở GCM mode |
| Authentication | Poly1305 | GHASH/GCM authentication |
| Key size phổ biến | 256 bit | 128 hoặc 256 bit |
| Nonce phổ biến | 96 bit | Thường 96 bit; phải theo contract |
| Authentication tag thường dùng | 128 bit | Thường 128 bit; cấu hình rõ |
| Yêu cầu nonce duy nhất theo key | **Rất quan trọng** | **Rất quan trọng** |
| API JCE | `ChaCha20-Poly1305` + `IvParameterSpec` | `AES/GCM/NoPadding` + `GCMParameterSpec` |
| AAD | Có | Có |
| Hiệu năng | Tốt trên nhiều hệ thống, đặc biệt không có tăng tốc AES | Có thể rất tốt khi phần cứng hỗ trợ AES/GCM |
| Tương thích | Kiểm tra provider và giao thức đối tác | Rộng rãi; kiểm tra provider, key policy, FIPS requirements |

Trong Java 11, **`ChaCha20` thuần và `ChaCha20-Poly1305` không có cùng cấp độ bảo vệ**. Khi yêu cầu là mã hóa dữ liệu và kiểm tra toàn vẹn, nên ưu tiên AEAD phù hợp với hệ sinh thái, giao thức, compliance và quản lý nonce/khóa. Không thay đổi transformation giữa hai thuật toán mà quên thay format và xử lý tag.

### ChaCha20-Poly1305 trong TLS có nghĩa gì?

TLS 1.3 có các AEAD cipher suites, trong đó có `TLS_CHACHA20_POLY1305_SHA256`. Tuy nhiên:

- TLS dùng **handshake**, key schedule và nonce derivation riêng của giao thức.
- Ứng dụng **không cần** gọi `Cipher.getInstance("ChaCha20-Poly1305")` thủ công để dùng HTTPS/TLS với cipher suite này; JSSE thực hiện bên dưới.
- Không tự lấy secret key từ TLS session để mã hóa application record tùy ý.
- Nếu mã hóa end-to-end ở tầng ứng dụng **trên HTTPS**, đó là một lớp bảo vệ khác, có key/nonce/AAD/lifecycle độc lập.

Bài này nói về **mã hóa AEAD trực tiếp qua JCE**, không thay thế quy trình JSSE/TLS hay quản lý chứng chỉ HTTPS.

## 13. Bộ kiểm thử tối thiểu cần có

| Trường hợp | Expected |
| --- | --- |
| Plaintext UTF-8 bình thường | Decrypt đúng cùng bytes |
| Plaintext rỗng | Output chỉ có tag trong phần cipher+tag; decrypt thành mảng rỗng |
| Payload tampered một bit | `AEADBadTagException` |
| Tag tampered một bit | `AEADBadTagException` |
| Nonce sai | `AEADBadTagException` |
| AAD khác một byte | `AEADBadTagException` |
| Sai khóa | `AEADBadTagException` |
| Key sai độ dài | Bị từ chối khi tạo/khởi tạo cipher theo provider |
| Nonce sai độ dài | Bị từ chối khi khởi tạo `Cipher` |
| Frame quá ngắn để có đủ version/nonce/tag | Từ chối trước khi cấp phát lớn |
| Format version lạ | Từ chối theo parser policy |
| Chuyển ciphertext sang tenant/record khác | Tag không khớp nếu context được AAD bind |
| Dùng lại nonce trong một kế hoạch cấp phát | Test **phải phát hiện vi phạm uniqueness** ở nonce allocator |
| RFC 8439 known-answer test | Ciphertext và tag khớp **toàn bộ bytes** |
| Interop với nhà cung cấp khác | Cùng thuật toán, nonce, key, AAD, tag order, version |
| User gửi lại nguyên bản tin cũ | Replay policy/sequence check phải nhận diện nếu workflow yêu cầu |

**Test round-trip chưa đủ.** Kết hợp known-answer test với negative authentication tests, interop tests và kiểm tra **quản lý nonce/khóa**. Không dùng deterministic nonce test vector để mã hóa dữ liệu thật.

## 14. Những lỗi thường gặp

**Lỗi 1 — Dùng `Cipher.getInstance("ChaCha20")` rồi tưởng có authentication.** ChaCha20 thuần không tự tạo tag; khi cần xác thực dùng `ChaCha20-Poly1305`.

**Lỗi 2 — Dùng lại nonce cho cùng key.** Đây là rủi ro mật mã nghiêm trọng; quản lý nonce duy nhất, không reset counter theo process restart.

**Lỗi 3 — Coi nonce là secret cần giấu.** Nonce có thể đi kèm ciphertext; thứ cần giữ bí mật là key. Uniqueness quan trọng hơn tính bí mật của nonce.

**Lỗi 4 — Hardcode key/nonce của test vector vào ứng dụng thật.** Test vector được công bố, hoàn toàn không có tính bí mật hay bảo đảm nonce mới.

**Lỗi 5 — Dùng `ChaCha20ParameterSpec` với transformation AEAD.** ChaCha20 thuần có counter; ChaCha20-Poly1305 chuẩn dùng nonce 12 byte qua `IvParameterSpec`.

**Lỗi 6 — Gửi AAD sau khi đã xử lý payload bằng `update`.** Với AEAD, đưa AAD vào trước nội dung để provider tính tag đúng.

**Lỗi 7 — Đổi thứ tự AAD field/charset giữa hai bên.** AAD bytes không khớp sẽ làm xác thực thất bại. Dùng canonical encoding có version.

**Lỗi 8 — Cắt tag, tự tính tag hoặc so sánh tag theo cách tùy ý.** Dùng tag 16 byte đầy đủ và để `Cipher.doFinal` xác thực.

**Lỗi 9 — Bắt `AEADBadTagException` rồi trả plaintext một phần.** Không sử dụng dữ liệu chưa xác thực; báo lỗi fail-closed.

**Lỗi 10 — Đọc plaintext từ streaming `update` và ghi vào DB trước `doFinal`.** Có thể đã tạo side effect trước khi phát hiện tag giả. Thiết kế buffer/record verification.

**Lỗi 11 — Bỏ giới hạn kích thước frame trước khi cấp phát.** Attacker có thể gửi payload lớn gây áp lực RAM. Dùng size budget phù hợp.

**Lỗi 12 — Coi AAD là encrypted.** AAD chỉ được xác thực; không chứa dữ liệu mật khi truyền công khai.

**Lỗi 13 — Coi tag hợp lệ là caller đã được phân quyền.** Tag chứng minh dữ liệu thuộc ngữ cảnh có key/AAD đúng, không thay authorization.

**Lỗi 14 — Không chống replay.** Một ciphertext+tag hợp lệ vẫn có thể bị gửi lại; cần sequence/operation ID theo protocol.

**Lỗi 15 — Để raw key nằm trong log/URL/config công khai.** Quản lý khóa bằng secret manager/keystore với phân quyền và rotation.

**Lỗi 16 — Dùng password bytes trực tiếp làm secret key.** Cần key generation hoặc KDF phù hợp.

**Lỗi 17 — Tin rằng random nonce 96 bit bảo đảm không bao giờ collision.** Đánh giá quy mô và thiết kế nonce allocator có kiểm soát khi yêu cầu uniqueness mạnh.

**Lỗi 18 — Coi ciphertext được mã hóa hai lần cùng key/nonce là “test thành công”.** Kết quả vẫn có thể giải mã, nhưng chính sách mật mã bị vi phạm; test phải kiểm tra invariant nonce.

**Lỗi 19 — Dùng cùng một đối tượng `Cipher` từ nhiều thread.** `Cipher` không được xem là thread-safe; tạo instance riêng theo operation/thread và khởi tạo nonce riêng.

**Lỗi 20 — Không version hóa envelope/AAD.** Khi đổi thuật toán, schema hoặc key rotation sẽ dễ nhầm format và giải mã sai dữ liệu.

## 15. Bài tập thực hành

### Bài 1 — Giải thích AEAD

Vẽ sơ đồ input `key, nonce, plaintext, AAD` và output `ciphertext, tag`. Giải thích sự khác nhau giữa “bí mật nội dung”, “toàn vẹn dữ liệu” và “chống replay”. Vì sao chỉ có ChaCha20 không đủ để bảo vệ tính toàn vẹn?

### Bài 2 — Chạy ví dụ Java 11

Biên dịch `AeadRoundTripDemo.java`, chạy và đối chiếu 12 dòng output. Mỗi dòng `rejected: true` chứng minh điều gì? Tại sao demo không in chính nonce/ciphertext ngẫu nhiên mà vẫn có stdout chính xác?

### Bài 3 — Sửa AAD

Đổi AAD khi decrypt từ `tenant=7` sang `tenant=8`. Dự đoán exception và kiểm tra kết quả. Thử đổi charset hoặc thứ tự các field, giải thích vì sao cùng “ý nghĩa” không đủ nếu bytes khác.

### Bài 4 — Kiểm tra vector RFC 8439

Chạy `Rfc8439VectorDemo.java`. Thay một byte AAD trong `hex`, quan sát kết quả `RFC 8439 vector matched: false`. Khôi phục vector và xác nhận lại. Không dùng nonce cố định của bài test cho message ngoài đời.

### Bài 5 — Định dạng frame có key ID

Thiết kế `version || keyId || nonce || ciphertext || tag`. Xác định:
- Trường nào được phép công khai?
- Trường nào phải đi vào AAD?
- Làm sao receiver chọn đúng key mà không tin header chưa xác thực cho mục đích phân quyền?
- Làm sao ứng dụng từ chối version lạ và frame quá lớn trước khi decrypt?

### Bài 6 — Quản lý nonce qua nhiều process

Một dịch vụ có 4 writer dùng cùng key. Đề xuất một nonce space partition hoặc cấp key riêng cho mỗi writer để tránh trùng cặp key/nonce. Nếu writer khởi động lại, cần lưu trạng thái nào để counter không quay về đầu? Đưa ra test phát hiện collision.

### Bài 7 — Chống replay

Một API nhận bản tin AEAD có tag hợp lệ nhưng cùng `operationId` được gửi lại 3 lần. Thiết kế replay cache/idempotency store theo key/sequence, có giới hạn thời gian và update atomic cùng nghiệp vụ. Tại sao `AEADBadTagException` không xuất hiện ở lần phát lại?

### Bài 8 — Lỗi giải mã

Giải thích khác biệt giữa:
- Frame version sai hoặc quá ngắn;
- `AEADBadTagException`;
- Khóa không tồn tại ở KMS;
- Input hợp lệ mật mã nhưng JSON/schema nghiệp vụ sai;
- Caller không có quyền đọc bản ghi.

Vì sao không nên trả tất cả như “mã hóa thành công” hoặc sử dụng một giá trị mặc định?

### Checklist hoàn thành

- [ ] Hiểu `ChaCha20-Poly1305` là AEAD, khác ChaCha20 thuần.
- [ ] Nhớ khóa 32 byte, nonce 12 byte, tag 16 byte và AAD chỉ xác thực.
- [ ] Biết dùng `Cipher`, `KeyGenerator`, `IvParameterSpec`, `updateAAD`, `doFinal` tương thích Java 11.
- [ ] Biết cách đóng gói version/nonce/ciphertext/tag và tái tạo AAD.
- [ ] Không mã hóa hai lần dưới cùng key/nonce.
- [ ] Biết `AEADBadTagException` và nguyên tắc từ chối plaintext chưa xác thực.
- [ ] Chạy được hai chương trình Java và đối chiếu output.
- [ ] Kiểm chứng được RFC 8439 test vector.
- [ ] Phân biệt authentication với authorization và replay protection.
- [ ] Có key lifecycle và nonce allocation scheme phù hợp production.

## 16. Tài liệu tham khảo vẫn áp dụng

1. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439) — `2.8` AEAD construction, `2.8.2` test vector, yêu cầu nonce duy nhất và tag 16 byte.
2. [Java SE 11 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html) — tên transformation `ChaCha20-Poly1305`, `ChaCha20`, `KeyGenerator` và provider support.
3. [Java SE 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html) — khởi tạo transformation, `updateAAD`, `doFinal`, AEAD và tag verification.
4. [Java SE 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html) — giải mã thất bại khi authentication tag không đúng.
5. [Java SE 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html) — mô tả nonce/IV trong JCE.
6. [Java SE 11 — KeyGenerator](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/KeyGenerator.html) — sinh secret keys.
7. [Java SE 11 — SecretKeySpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html) — tạo secret key từ bytes khi tích hợp với nguồn khóa hợp lệ.
8. [Java SE 25 — Cipher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html) — xác nhận AEAD API vẫn còn ở dòng JDK hiện đại.

**Kết luận:** khi cần **bí mật và toàn vẹn**, hãy dùng `ChaCha20-Poly1305` thay vì ChaCha20 thuần. Dùng khóa 256 bit, nonce 96 bit **duy nhất cho từng lần mã hóa dưới cùng khóa**, đưa AAD vào đúng thứ tự, giữ nguyên tag 128 bit và **chỉ tin plaintext sau khi `doFinal` xác minh tag thành công**. Trong production, còn phải thiết kế quản lý khóa/nonce, định dạng bản tin, giới hạn dữ liệu, xác thực header và **chống replay** ở tầng ứng dụng.