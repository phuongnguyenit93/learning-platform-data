# Associated data và thẻ xác thực trong ChaCha20-Poly1305 (Java 11+)

**Chủ đề cha: ChaCha20.** Khi mã hóa một bản tin, việc giấu nội dung là chưa đủ: ứng dụng cũng phải phát hiện nếu ciphertext, nonce hoặc metadata quan trọng bị thay đổi trên đường truyền. Từ Java 11, JDK hỗ trợ **ChaCha20-Poly1305**, một thuật toán *Authenticated Encryption with Associated Data* (**AEAD**) kết hợp ChaCha20 để mã hóa và Poly1305 để xác thực. Hai khái niệm của bài là **Associated Data (AAD)** — dữ liệu được xác thực nhưng không được mã hóa — và **authentication tag** — thẻ xác thực dùng để phát hiện dữ liệu/metadata không còn khớp.

**Tư tưởng chính:** AAD bảo vệ **ý nghĩa và ngữ cảnh** của bản tin, còn tag xác nhận tính toàn vẹn và tính xác thực theo **khóa bí mật đối xứng**. Không nên xem AAD là dữ liệu bí mật, tag là chữ ký số, hay ChaCha20 thuần là cơ chế tự có kiểm tra toàn vẹn. Các API được trình bày đều còn áp dụng trong Java hiện đại. Ví dụ chạy bằng **JDK 11+ có provider hỗ trợ ChaCha20-Poly1305**, điển hình là SunJCE của OpenJDK/Oracle JDK.

## 1. Phân biệt ChaCha20 thuần và ChaCha20-Poly1305

| Tính chất | `Cipher.getInstance("ChaCha20")` | `Cipher.getInstance("ChaCha20-Poly1305")` |
| --- | --- | --- |
| Bản chất | Stream cipher: tạo keystream để mã hóa/giải mã | AEAD: mã hóa **và** xác thực |
| Khóa | 256 bit = 32 byte | 256 bit = 32 byte |
| Nonce theo dạng IETF | 96 bit = 12 byte | 96 bit = 12 byte |
| Tham số Java 11 | `ChaCha20ParameterSpec(nonce, counter)` | `IvParameterSpec(nonce)` |
| Associated Data | **Không có cơ chế AAD** của ChaCha20 thuần | Có, qua `Cipher.updateAAD(...)` |
| Authentication tag | **Không có** | Tag Poly1305 dài **128 bit = 16 byte** |
| Nếu ciphertext bị sửa | Plaintext giải mã có thể bị thay đổi mà không phát hiện | Kiểm tra tag thất bại |
| Dùng cho dữ liệu ứng dụng mới | Chỉ khi giao thức có cơ chế xác thực riêng được thiết kế đúng | Ưu tiên AEAD khi cần bảo mật + toàn vẹn |

ChaCha20-Poly1305 không có nghĩa bạn tự tạo `Mac("Poly1305")` rồi ghép tùy ý. Thuật toán AEAD được chuẩn hóa xác định cách tạo khóa Poly1305 dùng một lần từ ChaCha20, cách tính tag trên AAD/ciphertext và kích thước dữ liệu. Trong Java, dùng **một transformation `"ChaCha20-Poly1305"`** để để provider xử lý đúng cơ chế đó.

Java 11 bổ sung cả ChaCha20 lẫn ChaCha20-Poly1305 thông qua **JEP 329**. Không cần dùng các thư viện ChaCha20 thử nghiệm cũ hoặc tự triển khai phép toán mật mã để học API.

## 2. AAD là gì và được bảo vệ ra sao?

**Additional Authenticated Data (AAD)** là những bytes **không mã hóa** nhưng được tính vào phép xác thực của bản tin.

Giả sử bản tin là một yêu cầu:

```text
version = 1
tenant  = "team-blue"
message-id = 42
plaintext = "Approve invoice 819"
```

Ta có thể đưa phiên bản, tenant và message-id (sau khi **mã hóa thành byte theo một format thống nhất**) vào AAD; còn nội dung nghiệp vụ vào plaintext để mã hóa.

```text
                       key K + unique nonce N
                               |
plaintext P  ----------------> | ChaCha20 encrypt ----> ciphertext C
                               |
AAD A -------------------------+ Poly1305 authenticate ---> tag T (16 bytes)
ciphertext C ------------------+
                               |
              transmit [nonce N | ciphertext C | tag T]
              along with AAD A or a way to reconstruct exactly A
```

Ở bên nhận:

1. Lấy đúng **key**, **nonce** và **ciphertext+tag**.
2. Tái tạo **chính xác các bytes AAD** đã được dùng khi mã hóa.
3. Gọi `Cipher.updateAAD(aad)` **trước** `doFinal(ciphertextAndTag)`.
4. Nếu kiểm tra xác thực thất bại, **loại bỏ bản tin**; không dùng plaintext không được xác thực.

AAD có thể công khai; nó không được ChaCha20 che giấu. Tag bảo vệ AAD khỏi **sửa đổi không phát hiện** đối với đối thủ không biết khóa, chứ không ngăn người khác *đọc* AAD.

### AAD có thể bao gồm những gì?

- Protocol version, thuật toán/cipher suite đã thỏa thuận.
- ID phiên, số thứ tự bản tin, hướng gửi (client→server hoặc server→client).
- Tenant ID hoặc đối tượng nhận, **nếu** bên nhận thực sự phải ràng buộc ciphertext với tenant đó.
- Message type, resource identifier, metadata không bí mật nhưng ảnh hưởng cách diễn giải nội dung.
- Những trường bắt buộc không được thay đổi trong khi ciphertext vẫn được coi là hợp lệ.

**Không đặt bí mật vào AAD** với hy vọng chúng được bảo vệ khỏi nghe lén. AAD **không được mã hóa**; nếu token hay dữ liệu cá nhân cần giấu, hãy cân nhắc đưa chúng vào plaintext được mã hóa hoặc xử lý bằng giao thức bảo vệ thích hợp.

## 3. Tag Poly1305 là gì?

Với ChaCha20-Poly1305 theo dạng IETF:

- Khóa ChaCha20: **32 byte**.
- Nonce: **12 byte** (96 bit), phải **duy nhất cho từng lần mã hóa với cùng một khóa**.
- Authentication tag: **16 byte** (128 bit).
- `Cipher.doFinal(plaintext)` khi mã hóa trả **ciphertext kèm tag**, trong đó tag nằm **cuối đầu ra**.
- `Cipher.doFinal(ciphertextAndTag)` khi giải mã kiểm tra tag rồi trả plaintext nếu thành công.

Với một lần mã hóa từ `P` có `n` byte:

```text
encrypted = C || T
length(encrypted) = n + 16
```

Nếu ứng dụng tự lưu nonce 12 byte ở trước đầu ra này:

```text
wire = nonce (12) || ciphertext (n) || tag (16)
length(wire) = n + 28
```

Chênh lệch **28 byte** ở ví dụ là **12 nonce + 16 tag**, chưa tính version, key ID, AAD, framing hoặc các metadata khác. JDK không tự gắn nonce vào `doFinal` trong ví dụ cung cấp `IvParameterSpec`; caller chịu trách nhiệm xây envelope hoặc giao thức truyền nonce.

Tag **không phải** chữ ký số và **không** thay thế xác thực danh tính người gửi. Hai bên cùng giữ khóa đối xứng đều có thể tạo tag hợp lệ; tag chỉ xác nhận nội dung phù hợp với khóa, nonce và AAD đã dùng. Muốn biết khóa thuộc về peer nào, phải có cơ chế xác thực/phân phối khóa ở tầng khác.

## 4. Cách Java 11 cấp khóa và cấu hình ChaCha20-Poly1305

Ví dụ tạo một `SecretKey` phù hợp:

```java
KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256);
SecretKey key = generator.generateKey();
```

Đây là đoạn minh họa cần import `javax.crypto.KeyGenerator` và `javax.crypto.SecretKey`. **Tên của KeyGenerator là `"ChaCha20"`**, trong khi transformation của Cipher dùng AEAD là `"ChaCha20-Poly1305"`.

Hoặc, khi bạn có **đúng 32 byte khóa bí mật** từ KDF/keystore:

```java
SecretKey key = new SecretKeySpec(rawKey, "ChaCha20");
```

Đây cũng là đoạn minh họa; phải bảo đảm `rawKey` được tạo bởi cơ chế sinh khóa an toàn và có đúng độ dài, không lấy trực tiếp mật khẩu người dùng làm `rawKey`. Khi nguồn là password, cần password-based KDF phù hợp; khi nguồn là shared secret từ key agreement, cần KDF được thiết kế cho giao thức.

Tạo nonce mới cho một lần mã hóa:

```java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);
```

**Nonce không cần bí mật**, có thể gửi kèm ciphertext, nhưng **không được lặp lại với cùng key**. Ngẫu nhiên 96-bit là cách đơn giản cho demo/khối lượng vừa phải. Với nhiều bản tin, nhiều máy phát, retry hoặc vòng đời khóa dài, hãy thiết kế chiến lược phân bổ nonce duy nhất (ví dụ bộ đếm gắn với session, phân vùng prefix theo người gửi và rekey); không giả định ngẫu nhiên không thể va chạm.

Dùng **`IvParameterSpec`** cho transformation AEAD:

```java
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
```

Đây là đoạn minh họa với import `javax.crypto.Cipher` và `javax.crypto.spec.IvParameterSpec`. **Đừng dùng `ChaCha20ParameterSpec(nonce,counter)` cho `ChaCha20-Poly1305`** trên provider SunJCE; class này dành cho `"ChaCha20"` thuần. Với AEAD, bộ đếm và cách tạo khóa Poly1305 được thuật toán quản lý, không tự đặt counter tùy ý.

## 5. Ví dụ Java 11: AAD + tag và giải mã thành công

Đây là chương trình độc lập, không truy cập Internet. Nó tạo key và nonce mới, bảo vệ plaintext `"hello"` cùng AAD chứa context, sau đó giải mã bằng **đúng ba đầu vào**: key, nonce, AAD.

### Tệp `ChaChaAadBasics.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaAadBasics {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "v1|tenant=blue|seq=7"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "hello"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("ChaCha20-Poly1305");
        encrypt.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("ChaCha20-Poly1305");
        decrypt.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertextAndTag);

        System.out.println("key bytes: " + key.getEncoded().length);
        System.out.println("nonce bytes: " + nonce.length);
        System.out.println("plaintext bytes: " + plaintext.length);
        System.out.println("ciphertext+tag bytes: "
                + ciphertextAndTag.length);
        System.out.println("recovered: "
                + new String(recovered, StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 -encoding UTF-8 ChaChaAadBasics.java
java ChaChaAadBasics
```

Stdout với provider ChaCha20 mặc định của JDK:

```text
key bytes: 32
nonce bytes: 12
plaintext bytes: 5
ciphertext+tag bytes: 21
recovered: hello
```

**Tại sao chiều dài mã hóa bằng 21?** Plaintext 5 byte, phần tag được gắn ở cuối là 16 byte. Nonce chưa được đưa vào mảng `ciphertextAndTag`. Cả key và nonce sinh ngẫu nhiên nên **bytes ciphertext sẽ khác nhau mỗi lượt chạy**, dù những dòng thông tin ở stdout trên vẫn như nhau.

**Điều này chứng minh gì?** AEAD hoạt động khi bên giải mã có đúng key/nonce/AAD/tag và nhận đủ ciphertext. Nó **không** chứng minh người gửi là một người dùng hay server cụ thể; nguồn gốc khóa đối xứng phải được xác thực bởi tầng cấp khóa/giao thức.

## 6. Sửa AAD hoặc ciphertext sẽ làm kiểm tra tag thất bại

`Cipher.doFinal(...)` khi giải mã thực hiện xác thực. Nếu kết quả không khớp, với provider JDK hỗ trợ ChaCha20-Poly1305, thường nhận `AEADBadTagException` (một lớp con của `BadPaddingException`). Không tiếp tục xử lý bản tin đó như hợp lệ, kể cả khi vẫn có bytes đã được xử lý trung gian.

Những thay đổi sau đều phải bị phát hiện, với xác suất giả mạo thành công cực thấp theo tính chất bảo mật của thuật toán:

- **AAD bị sửa:** đổi tenant ID, sequence, phiên bản hoặc bất kỳ byte nào được dùng làm AAD.
- **Ciphertext bị sửa:** đổi một byte nội dung đã mã hóa.
- **Tag bị sửa hoặc bị cắt:** không còn giá trị tag đúng.
- **Nonce bị sửa:** bộ tính keystream/tag nhận input khác; tag không khớp.
- **Dùng khóa sai:** tag không xác thực dưới khóa khác.

### Ví dụ chạy độc lập: `ChaChaAadTamperDemo.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaAadTamperDemo {
    static byte[] encrypt(SecretKey key, byte[] nonce,
                          byte[] aad, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    static boolean rejected(SecretKey key, byte[] nonce,
                            byte[] aad, byte[] ciphertextAndTag)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        cipher.updateAAD(aad);

        try {
            cipher.doFinal(ciphertextAndTag);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();
        SecretKey wrongKey = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "tenant=alice|seq=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] wrongAad = "tenant=bob|seq=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "PAYLOAD"
                .getBytes(StandardCharsets.UTF_8);

        byte[] sealed = encrypt(key, nonce, aad, plaintext);

        System.out.println("correct inputs accepted: "
                + !rejected(key, nonce, aad, sealed));
        System.out.println("wrong AAD rejected: "
                + rejected(key, nonce, wrongAad, sealed));

        byte[] tamperedCiphertext = sealed.clone();
        tamperedCiphertext[0] ^= 1;
        System.out.println("ciphertext tamper rejected: "
                + rejected(key, nonce, aad, tamperedCiphertext));

        byte[] tamperedTag = sealed.clone();
        tamperedTag[tamperedTag.length - 1] ^= 1;
        System.out.println("tag tamper rejected: "
                + rejected(key, nonce, aad, tamperedTag));

        byte[] changedNonce = nonce.clone();
        changedNonce[0] ^= 1;
        System.out.println("wrong nonce rejected: "
                + rejected(key, changedNonce, aad, sealed));

        System.out.println("wrong key rejected: "
                + rejected(wrongKey, nonce, aad, sealed));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ChaChaAadTamperDemo.java
java ChaChaAadTamperDemo
```

Kết quả mong đợi:

```text
correct inputs accepted: true
wrong AAD rejected: true
ciphertext tamper rejected: true
tag tamper rejected: true
wrong nonce rejected: true
wrong key rejected: true
```

Mỗi lời gọi `rejected(...)` tạo **một Cipher mới** để không lẫn trạng thái của các thử nghiệm. Ví dụ này chỉ mã hóa **một lần**; các phép kiểm tra sai nonce/khóa thực hiện **giải mã** để thử phát hiện lỗi, không cố tình mã hóa hai bản tin bằng cùng key/nonce.

Với xác thực 128-bit, xác suất một thay đổi giả mạo qua được kiểm tra là rất nhỏ chứ không phải bất khả thi về mặt toán học. Đừng viết hệ thống an ninh thực tế dựa vào việc lặp thử hàng triệu lần hoặc tiết lộ cho kẻ tấn công nội dung chi tiết của lỗi xác thực.

## 7. Thứ tự gọi API: AAD phải được cung cấp trước data

Trình tự đúng cho cả mã hóa và giải mã là:

```text
Cipher.getInstance("ChaCha20-Poly1305")
       |
       v
init(ENCRYPT_MODE hoặc DECRYPT_MODE, key, IvParameterSpec(nonce))
       |
       v
updateAAD(aadBytes)   [có thể gọi nhiều lần trước data]
       |
       v
update(data)          [tùy chọn]
       |
       v
doFinal(...)          [hoàn tất; tạo/kiểm tra tag]
```

Nếu cần cung cấp AAD thành nhiều phần, các lời gọi phải xảy ra **trước khi xử lý plaintext/ciphertext**:

```java
cipher.updateAAD(versionBytes);
cipher.updateAAD(headerBytes);
byte[] output = cipher.doFinal(messageBytes);
```

Đây là đoạn minh họa, đòi hỏi cả hai bên cung cấp **cùng thứ tự và cùng bytes**. Thêm AAD sau khi đã gọi `update(data)` là sai trạng thái và có thể gây `IllegalStateException`. AAD không phải chuỗi “tự đồng bộ”; thuật toán làm việc với **bytes**, không tự hiểu UTF-8, JSON key order, khoảng trắng, timezone hoặc định dạng số.

**Nếu không có AAD:** có thể bỏ qua `updateAAD(...)`, khi đó AAD được coi là rỗng. Bản tin vẫn được bảo vệ bởi tag trên ciphertext và các thành phần của thuật toán. Nhưng nếu ứng dụng có metadata quyết định ngữ cảnh xử lý mà metadata không được đưa vào AAD, nó **không được ràng buộc mật mã** với ciphertext.

### Cẩn trọng khi dùng update()/doFinal() theo luồng

AEAD chỉ xác nhận toàn bộ bản tin khi **tag được kiểm tra thành công**. Không xuất bản plaintext từng phần cho hệ thống khác trước khi `doFinal` hoàn tất và tag hợp lệ. Một số provider có thể buffer ciphertext/plaintext khác nhau; code bảo mật phải dựa trên yêu cầu xác thực **sau khi kết thúc**, không dựa vào thời điểm `update` trả bytes.

Với dữ liệu cực lớn, đừng tự chia thành các phần AEAD độc lập rồi **tái sử dụng cùng key/nonce**. Nếu cần một giao thức mã hóa theo chunk, mỗi chunk phải có nonce duy nhất, sequence/position được xác thực, định nghĩa final chunk và chống cắt ghép/reorder/truncation. Chọn một giao thức hoặc thư viện streaming AEAD được đánh giá thay vì tự ghép.

## 8. Thiết kế AAD sao cho hai bên có chính xác cùng bytes

Một lỗi phổ biến là gọi:

```java
String aad = tenant + "|" + seq + "|" + messageType;
```

Đây chỉ là minh họa. Ghép chuỗi bằng ký tự `|` có thể **mơ hồ** khi một trường cũng chứa `|`, hoặc khác biệt do chuẩn hóa Unicode, cách viết số, chữ hoa/chữ thường, khoảng trắng hay thứ tự trường. Có thể xảy ra hai input ngữ nghĩa khác nhau tạo cùng AAD byte sequence, hoặc hai bên hiểu cùng input nhưng serialize thành bytes khác nhau.

**Cách tốt hơn:**

1. Định nghĩa format AAD ổn định và có phiên bản.
2. Có thứ tự trường cố định; với trường biến độ dài, dùng **length-prefix** hoặc encoding chuẩn có tính canonical.
3. Định nghĩa charset (thường UTF-8) và biểu diễn số (endianness, kích thước).
4. Bao gồm **purpose/domain separation** và hướng gửi nếu có nhiều loại bản tin hoặc nhiều mục đích sử dụng cùng khóa.
5. Bên nhận tái tạo đúng AAD trước khi gọi `doFinal`, không tự “linh hoạt” bỏ trường hoặc sửa khoảng trắng sau khi nhận.
6. Chỉ dùng metadata cho các quyết định nhạy cảm **sau khi xác minh tag**, ngoại trừ những bước tối thiểu cần để tìm khóa/định tuyến bản tin tới bộ giải mã với chính sách an toàn.

### Ví dụ canonical AAD với version + tenant + sequence

Một format đơn giản phục vụ học tập:

```text
version:   1 byte
tenantLen: 2 byte unsigned, big-endian
tenant:    tenantLen byte UTF-8
sequence:  8 byte signed long, big-endian
```

Đây là format **do ứng dụng định nghĩa**, không phải chuẩn wire format của ChaCha20-Poly1305. Nó cho phép bên nhận biết ranh giới trường và tái tạo bytes một cách rõ ràng. Với production, cần kiểm soát dữ liệu đầu vào, length limit, nonce/sequence policy và nhất quán across language.

## 9. Ví dụ Java 11: gắn ciphertext với tenant và sequence

Ví dụ này mã hóa `"order-42"`, rồi thử mở envelope với **cùng tenant/sequence** và với metadata đã bị đổi. Metadata là AAD: vẫn ở ngoài ciphertext nhưng sửa metadata sẽ gây lỗi xác thực.

Wire format trong ví dụ: **12-byte nonce + (ciphertext || 16-byte tag)**. Tenant/sequence được gửi hoặc biết qua kênh metadata riêng; chúng **không nằm trong mảng wire** của demo, nhưng phải được tái tạo chính xác bởi receiver.

### Tệp `CanonicalAadEnvelopeDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class CanonicalAadEnvelopeDemo {
    static byte[] aad(String tenant, long sequence) {
        byte[] name = tenant.getBytes(StandardCharsets.UTF_8);
        if (name.length > 65535) {
            throw new IllegalArgumentException("Tenant ID too long");
        }
        return ByteBuffer.allocate(1 + 2 + name.length + 8)
                .order(ByteOrder.BIG_ENDIAN)
                .put((byte) 1)
                .putShort((short) name.length)
                .put(name)
                .putLong(sequence)
                .array();
    }

    static byte[] seal(SecretKey key, String tenant,
                       long sequence, byte[] plain) throws Exception {
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        Cipher enc = Cipher.getInstance("ChaCha20-Poly1305");
        enc.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        enc.updateAAD(aad(tenant, sequence));
        byte[] sealed = enc.doFinal(plain);

        return ByteBuffer.allocate(12 + sealed.length)
                .put(nonce).put(sealed).array();
    }

    static byte[] open(SecretKey key, String tenant,
                       long sequence, byte[] wire) throws Exception {
        if (wire.length < 12 + 16) {
            throw new IllegalArgumentException("Envelope too short");
        }

        byte[] nonce = Arrays.copyOfRange(wire, 0, 12);
        byte[] sealed = Arrays.copyOfRange(wire, 12, wire.length);

        Cipher dec = Cipher.getInstance("ChaCha20-Poly1305");
        dec.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        dec.updateAAD(aad(tenant, sequence));
        return dec.doFinal(sealed);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] plaintext = "order-42".getBytes(StandardCharsets.UTF_8);
        byte[] wire = seal(key, "team-A", 42, plaintext);

        byte[] restored = open(key, "team-A", 42, wire);
        System.out.println("valid record: "
                + new String(restored, StandardCharsets.UTF_8));
        System.out.println("wire overhead: "
                + (wire.length - plaintext.length));

        boolean wrongTenantRejected = false;
        try {
            open(key, "team-B", 42, wire);
        } catch (AEADBadTagException expected) {
            wrongTenantRejected = true;
        }
        System.out.println("wrong tenant rejected: "
                + wrongTenantRejected);

        boolean wrongSequenceRejected = false;
        try {
            open(key, "team-A", 43, wire);
        } catch (AEADBadTagException expected) {
            wrongSequenceRejected = true;
        }
        System.out.println("wrong sequence rejected: "
                + wrongSequenceRejected);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 CanonicalAadEnvelopeDemo.java
java CanonicalAadEnvelopeDemo
```

```text
valid record: order-42
wire overhead: 28
wrong tenant rejected: true
wrong sequence rejected: true
```

**Điểm cần hiểu:**

- `wire overhead: 28` = nonce 12 byte + tag 16 byte. Nội dung `"order-42"` có 8 byte ASCII.
- Tenant/sequence được đưa vào AAD. Đổi một trong hai khi giải mã sẽ khiến tag không khớp.
- Đây chỉ là **một ví dụ về serialization có định dạng rõ**. Chưa có cơ chế quản trị nhiều khóa, chống replay, tránh tái dùng nonce trên nhiều máy hay xác thực server/user.
- Trước khi xử lý dữ liệu thật, hãy validate độ dài trường, version được hỗ trợ, sequence hợp lệ, chính sách key ID/tenant và kích thước ciphertext tối đa.
- **AAD không tự chống replay:** attacker có thể gửi lại nguyên bộ `(nonce, AAD, ciphertext, tag)` của một bản tin hợp lệ và nó vẫn qua kiểm tra tag. Hệ thống phải theo dõi sequence/cửa sổ chống replay hoặc trạng thái nghiệp vụ riêng.

### Một AAD đúng chưa đủ cho hệ thống nhiều tenant

Nếu application có dữ liệu tenant A và B, không đủ để tự nhận chuỗi `"tenant=A"` từ bên ngoài rồi đưa vào AAD. Cần chính sách **ai được quyền chọn tenant nào**, key mapping và authorization rõ ràng. Chỉ sau khi AEAD verify thành công mới được tin nội dung metadata đã được **ràng buộc với ciphertext và khóa**; nó không tự chứng minh người yêu cầu có quyền truy cập tenant đó.

## 10. Tag sai phải làm hệ thống fail-closed

Trong code nhận bản tin, hãy coi `AEADBadTagException` là **thất bại xác thực**:

```java
try {
    byte[] plain = decryptCipher.doFinal(ciphertextAndTag);
    // Chỉ sử dụng plain sau khi doFinal thành công.
} catch (AEADBadTagException invalid) {
    // Loại bỏ bản tin; không fallback sang giải mã không xác thực.
}
```

Đây là đoạn minh họa với một `Cipher decryptCipher` đã init đúng và đã cung cấp AAD.

**Không được:**

- Trả về plaintext chưa xác thực do một bước update trung gian tạo ra.
- Bỏ 16 byte cuối của ciphertext cho đủ độ dài rồi gọi mode ChaCha20 thuần để giải mã.
- Bỏ qua tag sau khi retry nhiều lần, hoặc coi `AEADBadTagException` chỉ là cảnh báo.
- Log key, nonce/ciphertext nhạy cảm hoặc toàn bộ plaintext nhằm debug lỗi xác thực.
- Tạo thông báo lỗi quá khác nhau cho “sai tenant”, “sai tag” hoặc “sai key” khi điều đó có thể trở thành oracle cho attacker.

Nếu cần xử lý ngoại lệ an toàn, có thể trả về một lỗi chung cho dữ liệu không xác thực và log một mã nguyên nhân nội bộ **không chứa secret**. Phân biệt lỗi **cú pháp envelope** (số byte quá ngắn, version không hỗ trợ) với lỗi **tag không hợp lệ**, nhưng không tiết lộ quá mức thông tin bên ngoài.

## 11. Quản lý nonce và khóa: điều kiện để tag có ý nghĩa bảo mật

Dù Poly1305 có tag 128-bit, an toàn AEAD vẫn phụ thuộc **không lặp nonce với cùng key**. ChaCha20 là stream cipher; nếu hai bản tin dùng cùng key/nonce, chúng tái sử dụng keystream, gây rò rỉ quan hệ giữa plaintext. Đồng thời tính bảo mật/toàn vẹn của Poly1305 có thể bị phá hỏng nghiêm trọng vì khóa xác thực dùng một lần bị tái tạo.

**Đối với ứng dụng thực:**

1. Sinh key 256-bit bằng CSPRNG hoặc KDF phù hợp; không lấy `String.getBytes()` của password làm key.
2. Mỗi lần mã hóa với cùng key sử dụng một nonce 96-bit **duy nhất**. Bên nhận cần biết nonce đó để giải mã; nonce có thể truyền công khai.
3. Nếu dùng counter, phải định nghĩa byte order, phạm vi giá trị, cách cấp phát an toàn giữa thread/máy và chính sách không lặp khi restart; counter là chính sách **của giao thức**, không phải field tự tăng tồn tại sẵn trong `IvParameterSpec`.
4. Nếu nhiều bên cùng mã hóa, phân vùng không gian nonce theo chiều gửi/session hoặc dùng khóa riêng theo hướng; tránh hai bên vô tình chọn cùng nonce dưới một key.
5. Khi đạt giới hạn thiết kế, thay khóa/rekey đúng quy trình; giữ khóa trong keystore/HSM hoặc secret management phù hợp.
6. Không dùng lại Cipher instance đã mã hóa với cùng key/nonce rồi gọi mã hóa message thứ hai. Tạo hoặc init Cipher cho bản tin mới với nonce khác.
7. Khi cần chia file thành chunk, mỗi chunk có nonce/key và AAD gồm chunk index, file ID, thông tin kết thúc, tổng số chunk/length theo một giao thức được phân tích.

**Nonce không phải tag.** Có thể có nonce giống nhau dưới **hai khóa khác nhau**, nhưng chính sách vận hành vẫn nên tránh nhầm lẫn; điều cấm mật mã quan trọng là **cặp (key, nonce)** không được lặp lại khi mã hóa.

## 12. AAD, tag và chữ ký số: đối chiếu bảo đảm

| Cơ chế | Bí mật hay công khai? | Tác dụng | Không tự làm được |
| --- | --- | --- | --- |
| AAD | Thường công khai | Ràng buộc metadata vào phép xác thực AEAD | Che giấu metadata |
| Poly1305 tag trong AEAD | Có thể gửi công khai kèm ciphertext | Kiểm tra key/nonce/AAD/ciphertext nhất quán | Chữ ký bất đối xứng, xác thực danh tính độc lập |
| Khóa ChaCha20 256-bit | **Bí mật** | Cho phép mã hóa/giải mã và tính/kiểm tra tag | Chứng minh người đang gửi là một danh tính nhất định |
| Nonce 96-bit | Công khai nhưng **duy nhất theo key** | Phân biệt phép mã hóa; ngăn lặp keystream | Đóng vai trò secret/key |
| Chữ ký số (ví dụ Ed25519) | Private signing key bí mật, public verification key công khai | Xác thực thông điệp bằng public key tin cậy | Che giấu message |
| TLS 1.3/HTTPS | Giao thức dùng nhiều primitive | Thiết lập khóa, xác thực peer và bảo vệ dữ liệu vận chuyển | Tự động áp dụng encryption cho dữ liệu đã lưu lâu dài |

**Phân biệt rõ:** Một tag hợp lệ chỉ chứng minh bản tin được tạo bởi bên nào đó biết **cùng khóa** hoặc không bị thay đổi đối với kẻ không biết khóa. Chữ ký số cho phép **verify bằng public key** của một danh tính, nếu nguồn public key đã được xác thực. Không dùng tag như bằng chứng “server Bob đã ký bản tin này”.

## 13. Các lỗi API và lỗi nghiệp vụ thường gặp

| Sai lầm | Hiện tượng/hệ quả | Cách đúng |
| --- | --- | --- |
| Dùng `Cipher.getInstance("ChaCha20")` và gọi đó là AEAD | Không có authentication tag | Dùng `"ChaCha20-Poly1305"` |
| Truyền `ChaCha20ParameterSpec` vào Cipher AEAD trên SunJCE | Tham số không phù hợp | Dùng `IvParameterSpec` 12 byte |
| Dùng key không đủ 256 bit | `InvalidKeyException` hoặc init thất bại | Key 32 byte từ KeyGenerator/KDF |
| Nonce không đúng 12 byte | `InvalidAlgorithmParameterException` | Khởi tạo nonce 96 bit |
| Đưa AAD vào sau `update(data)` | Sai trạng thái | `updateAAD` trước khi xử lý data |
| Bên gửi và nhận dùng AAD khác bytes | `AEADBadTagException` | Serialization canonical và cùng ngữ cảnh |
| Tách bỏ 16-byte tag trước khi `doFinal` | Không xác thực được | Truyền `ciphertext || tag` đầy đủ |
| Tái dùng key/nonce cho hai lần encrypt | Rò rỉ và nguy cơ giả mạo | Nonce duy nhất theo key |
| Coi AAD là secret | Lộ metadata nhạy cảm | Không đưa bí mật vào AAD công khai |
| Coi tag là chữ ký | Sai mô hình xác thực danh tính | Dùng signature/certificate/handshake phù hợp |
| Dùng plaintext trước khi verify thành công | Sử dụng dữ liệu không đáng tin | Chỉ publish sau `doFinal` thành công |
| Không chống replay | Bản tin cũ có tag hợp lệ vẫn dùng lại được | Sequence/window/state được xác thực |
| Dùng chung Cipher mutable qua nhiều thread | Race/sai trạng thái mật mã | Tạo Cipher riêng cho mỗi thao tác hoặc quản lý đồng bộ |
| Mã hóa payload rất lớn không giới hạn | Tăng bộ nhớ/disk, DoS | Giới hạn resource, protocol streaming AEAD chuẩn |
| Tự tạo định dạng JSON AAD không canonical | Hai bên tạo AAD bytes khác nhau | Quy định encoding, thứ tự, field length, version |

**Lưu ý về exception:** Cụ thể exception có thể khác giữa provider và nguyên nhân lỗi. Ví dụ code dùng SunJCE Java 11 thường bắt `AEADBadTagException` cho tag mismatch; nếu provider khác, hãy bám hợp đồng JCA, kiểm tra exception chain và không tự biến lỗi bảo mật thành thành công.

## 14. Bộ kiểm thử hồi quy Java 11 (11 kiểm tra)

Để tránh phụ thuộc ciphertext ngẫu nhiên, ta kiểm tra **thuộc tính**: độ dài key/nonce/tag, roundtrip và các thay đổi phải bị từ chối. Chương trình này không cần mạng/JUnit, không ghi secret ra stdout và không cần JVM option `-ea` vì dùng `AssertionError` trực tiếp.

### Tệp `ChaChaAeadRegression.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public class ChaChaAeadRegression {
    private static int checks = 0;

    static void check(String name, boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    static byte[] seal(SecretKey key, byte[] nonce,
                       byte[] aad, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    static byte[] open(SecretKey key, byte[] nonce,
                       byte[] aad, byte[] ciphertextAndTag)
            throws Exception {
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    static boolean rejects(SecretKey key, byte[] nonce,
                           byte[] aad, byte[] ciphertextAndTag)
            throws Exception {
        try {
            open(key, nonce, aad, ciphertextAndTag);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256);
        SecretKey key = generator.generateKey();
        SecretKey wrongKey = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "v1|tenant=A|seq=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] wrongAad = "v1|tenant=B|seq=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plain = "record-1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] sealed = seal(key, nonce, aad, plain);

        check("32-byte key", key.getEncoded().length == 32);
        check("12-byte nonce", nonce.length == 12);
        check("16-byte tag", sealed.length == plain.length + 16);
        check("roundtrip",
                Arrays.equals(plain, open(key, nonce, aad, sealed)));

        check("wrong AAD rejected",
                rejects(key, nonce, wrongAad, sealed));

        byte[] badCiphertext = sealed.clone();
        badCiphertext[0] ^= 1;
        check("ciphertext tampered",
                rejects(key, nonce, aad, badCiphertext));

        byte[] badTag = sealed.clone();
        badTag[badTag.length - 1] ^= 1;
        check("tag tampered",
                rejects(key, nonce, aad, badTag));

        byte[] wrongNonce = nonce.clone();
        wrongNonce[0] ^= 1;
        check("wrong nonce",
                rejects(key, wrongNonce, aad, sealed));

        check("wrong key",
                rejects(wrongKey, nonce, aad, sealed));

        byte[] nonce2 = new byte[12];
        new SecureRandom().nextBytes(nonce2);
        while (Arrays.equals(nonce2, nonce)) {
            new SecureRandom().nextBytes(nonce2);
        }

        byte[] emptySealed = seal(key, nonce2, aad, new byte[0]);
        check("empty plaintext produces tag",
                emptySealed.length == 16);
        check("empty plaintext roundtrip",
                open(key, nonce2, aad, emptySealed).length == 0);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 ChaChaAeadRegression.java
java ChaChaAeadRegression
```

```text
PASS: 11 checks
```

**Đếm:** 3 điều kiện kích thước, 1 roundtrip, 5 trường hợp sai key/nonce/AAD/ciphertext/tag, 2 trường hợp plaintext rỗng = **11**.

**Vì sao plaintext rỗng vẫn có tag?** AEAD bảo vệ AAD và sự kiện “body rỗng” bằng authentication tag. Không được bỏ tag chỉ vì `plaintext.length==0`. Ở lượt encrypt thứ hai, chương trình chọn **nonce khác** để tuân thủ không lặp cùng key/nonce.

**Giới hạn:** Đây là unit test cho API JCA và một số thuộc tính AEAD, không chứng minh ứng dụng quản lý khóa, nonce, chống replay, quyền truy cập tenant hay chống tấn công mạng đúng. Cần có thêm integration tests và review giao thức khi triển khai thật.

## 15. Checklist triển khai an toàn

1. **Dùng đúng transformation:** `ChaCha20-Poly1305` khi cần AAD và authentication tag; không dùng ChaCha20 thuần rồi nghĩ đã có MAC.
2. **Khóa và nonce:** key 32 byte, nonce 12 byte; nonce phải duy nhất cho mỗi lần encrypt cùng key.
3. **Truyền đủ dữ liệu:** ciphertext **kèm 16-byte tag** và nonce; AAD được gửi kèm hoặc tái tạo chính xác theo protocol.
4. **AAD có schema:** version, domain separation, tenant/session/sequence nếu cần; định dạng byte canonical không mơ hồ.
5. **Đúng thứ tự API:** init → updateAAD → update/doFinal.
6. **Fail-closed:** không cho plaintext chưa được xác thực đi vào cache, database hay bộ xử lý; tag sai thì loại bỏ.
7. **Chống replay:** theo dõi sequence và state; tag đúng không có nghĩa bản tin là mới.
8. **Không rò rỉ bí mật:** key không ghi log, truyền trong URL hay đặt trong AAD; nonce có thể công khai nhưng không lặp.
9. **Giới hạn tài nguyên:** max ciphertext/AAD, tổng số bản tin, timeout, chính sách stream nếu payload lớn.
10. **Quản lý key lâu dài:** sử dụng keystore/KMS và KDF đúng; rotate/rekey khi đạt giới hạn.
11. **Không tự phát minh giao thức:** nếu cần bảo vệ HTTP qua mạng, ưu tiên HTTPS/TLS 1.3, vốn đã có AEAD và giao thức xác thực peer được tiêu chuẩn hóa.
12. **Kiểm thử âm tính:** sửa AAD, ciphertext, tag, nonce, dùng key sai, thiếu tag, sai version, replay và lỗi input.

## 16. Câu hỏi tự luyện

**A.** AAD có được mã hóa bên trong ciphertext không? Nếu không, tác dụng của nó là gì?

**B.** ChaCha20 thuần có tự phát hiện ciphertext bị sửa không?

**C.** Với 9 byte plaintext, `doFinal` khi mã hóa bằng ChaCha20-Poly1305 thường trả bao nhiêu byte nếu không tự gắn nonce?

**D.** Vì sao receiver phải dùng đúng AAD bytes chứ không chỉ “cùng nội dung JSON” theo cách hiểu của con người?

**E.** Khi `doFinal(ciphertextAndTag)` ném `AEADBadTagException`, có nên trả plaintext đã nhận từ `update` không?

**F.** Nếu tag đúng, có chứng minh được chính xác “user Alice đã ký bản tin” không?

**G.** Có thể gửi lại y nguyên bộ (nonce, AAD, ciphertext, tag) và qua kiểm tra tag lần nữa không? Cần thêm gì?

**H.** Khi dùng `Cipher.getInstance("ChaCha20-Poly1305")` trên SunJCE Java 11, dùng `ChaCha20ParameterSpec` hay `IvParameterSpec`?

**Đáp án:**

1. **A:** Không; AAD được **xác thực nhưng không mã hóa**, dùng để ràng buộc metadata/context với ciphertext.
2. **B:** Không; phải có AEAD/MAC được thiết kế đúng, phổ biến là ChaCha20-Poly1305.
3. **C:** **25 byte** (9 ciphertext + 16 tag), nonce 12 byte không tự nằm trong `doFinal` khi init với tham số như bài.
4. **D:** AEAD tính trên **bytes**; khác thứ tự, charset, khoảng trắng hoặc encoding sẽ đổi tag input.
5. **E:** Không; chỉ công bố plaintext khi xác minh tag thành công.
6. **F:** Không; tag đối xứng không phải chữ ký số, danh tính phụ thuộc cách phân phối/xác thực key.
7. **G:** Có thể; cần state/counter/cửa sổ chống replay ở tầng giao thức.
8. **H:** **`IvParameterSpec` với 12-byte nonce**; `ChaCha20ParameterSpec` dành cho ChaCha20 thuần.

## Nguồn tham khảo chính thức

- [OpenJDK JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms (Java 11)](https://openjdk.org/jeps/329).
- [Java SE 11 — Java Security Standard Algorithm Names: ChaCha20, ChaCha20-Poly1305](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html).
- [Java SE 11 — Cipher: AEAD, updateAAD, tag, nonce uniqueness](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html).
- [Java SE 11 — ChaCha20ParameterSpec (dành cho ChaCha20 thuần)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html).
- [Java SE 11 — IvParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html).
- [Java SE 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html).
- [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439).
- [RFC 5116 — Authenticated Encryption with Associated Data (AEAD)](https://www.rfc-editor.org/rfc/rfc5116).
