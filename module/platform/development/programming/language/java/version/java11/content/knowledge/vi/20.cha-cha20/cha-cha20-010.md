# Java 11+ — ChaCha20: Quản lý khóa, định dạng thông điệp và metadata cần truyền

## 1. Mục tiêu: mã hóa để hai phía có thể trao đổi thông điệp an toàn

**ChaCha20** là một thuật toán mã hóa dòng; **ChaCha20-Poly1305** kết hợp ChaCha20 và Poly1305 thành một thuật toán **AEAD** (*Authenticated Encryption with Associated Data*). Java 11 hỗ trợ các thuật toán này qua `javax.crypto.Cipher`, `KeyGenerator`, `SecretKey` và các lớp parameter spec chính thức.

Khi gửi một thông điệp đã mã hóa qua mạng, không thể chỉ gọi `cipher.doFinal(plaintext)` rồi đưa mảng byte kết quả đến người nhận. Cả hai phía còn phải thống nhất:

- **Khóa bí mật** nào được sử dụng, được tạo và bảo vệ thế nào, khi nào xoay vòng.
- **Nonce** nào đi với bản tin, làm sao bảo đảm không bao giờ mã hóa bằng nonce đã dùng trước đó **với cùng khóa**.
- **Thuật toán/phiên bản** nào dùng để giải mã; không tự động thử lại cipher yếu hoặc định dạng không được cho phép.
- **Ranh giới dữ liệu**: header ở đâu, ciphertext dài bao nhiêu byte, tag xác thực ở đâu.
- **Metadata** nào cần nằm trong gói tin và metadata nào phải được ràng buộc bằng `updateAAD`.
- **Kiểm tra input** và giới hạn bộ nhớ: dữ liệu, length, version, key ID, type từ mạng đều chưa đáng tin trước khi xác thực.
- **Chống phát lại** nếu nghiệp vụ không cho phép cùng bản tin được xử lý hai lần.

Một schema thông điệp tốt phải cho phép người nhận biết **cách kiểm tra** ciphertext nhưng **không tiết lộ khóa bí mật**. Bài này giải thích các nguyên tắc vẫn áp dụng trên JDK hiện đại, đồng thời cung cấp ví dụ Java 11 có thể biên dịch, chạy và thử các trường hợp giả mạo.

## 2. ChaCha20 thuần khác gì ChaCha20-Poly1305?

| Tiêu chí | `ChaCha20` thuần | `ChaCha20-Poly1305` |
| --- | --- | --- |
| Mục đích | Stream cipher, mã hóa và giải mã byte. | AEAD: mã hóa **và** kiểm tra tính toàn vẹn dưới khóa bí mật. |
| Transformation JCE | `Cipher.getInstance("ChaCha20")`. | `Cipher.getInstance("ChaCha20-Poly1305")`. |
| Key size | **32 byte/256 bit**. | **32 byte/256 bit**. |
| Nonce | **12 byte/96 bit** (biến thể IETF). | **12 byte/96 bit** theo RFC 8439. |
| Counter | Gồm **initial block counter 32-bit** do caller truyền. | Counter được xử lý **bên trong AEAD**, không truyền từ code ứng dụng. |
| Java parameter | `ChaCha20ParameterSpec(nonce, initialCounter)`. | `IvParameterSpec(nonce)`. |
| Tag | **Không** tạo authentication tag. | **16 byte/128 bit**, được xác minh khi giải mã. |
| AAD | Không cung cấp AEAD AAD. | Dùng `Cipher.updateAAD(...)`. |
| Phát hiện sửa ciphertext | **Không bảo đảm** nếu dùng riêng. | Tag xác thực không hợp lệ khiến giải mã thất bại. |
| Phù hợp message cần bảo mật | Chỉ khi một protocol đã có cơ chế MAC chính xác và được thẩm định. | **Thông thường ưu tiên** khi cần confidentiality và integrity. |

Dùng ChaCha20 thuần như sau chỉ minh họa sự khác nhau về API; **không phải giải pháp hoàn chỉnh để bảo vệ message ứng dụng**:

```java
// Minh họa trong phương thức có xử lý GeneralSecurityException.
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher stream = Cipher.getInstance("ChaCha20");
stream.init(Cipher.ENCRYPT_MODE, key,
        new ChaCha20ParameterSpec(nonce, 1));
byte[] ciphertext = stream.doFinal(plaintext);
```

Trong đoạn này, `key` là `SecretKey` 256-bit và `plaintext` là byte[] được chuẩn bị trước. Mã hóa dòng không có MAC cho phép attacker sửa bit ciphertext, làm plaintext sau giải mã thay đổi tương ứng. Không “sửa” vấn đề bằng cách thêm checksum không có khóa.

**ChaCha20-Poly1305** sử dụng API khác:

```java
Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
aead.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
aead.updateAAD(headerBytes); // Trước khi xử lý plaintext.
byte[] ciphertextAndTag = aead.doFinal(plaintext);
```

`ciphertextAndTag` chứa **ciphertext nối với tag 16 byte**. Phần tag không phải chuỗi plaintext và không nên tách/cắt bớt tùy ý. `headerBytes` là AAD: được **xác thực nhưng không mã hóa**. RFC 8439 quy định dùng ChaCha20 block 0 tạo khóa Poly1305 một lần và mã hóa payload từ counter 1; với JCE ChaCha20-Poly1305, caller **không** đặt counter riêng.

## 3. Sinh và quản lý khóa ChaCha20

### 3.1. Sinh secret key bằng JCA

```java
SecureRandom random = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
generator.init(256, random);
SecretKey key = generator.generateKey();
```

Java 11 cung cấp `KeyGenerator` mang tên thuật toán **`ChaCha20`** cho cả ChaCha20 và ChaCha20-Poly1305. Không nhất thiết có một `KeyGenerator` riêng với tên `"ChaCha20-Poly1305"`. Dùng nguồn `SecureRandom` phù hợp thay vì `Random`, `Math.random()`, thời gian hệ thống hay seed tĩnh.

**Key material là secret, không phải metadata.** Người nhận cần có cùng secret qua một cơ chế **đã được xác thực và bảo vệ**: một key-management service, kênh phân phối tin cậy hoặc một key schedule trong protocol đã được thẩm định. Không đặt khóa vào header cùng ciphertext để người nhận “tiện lấy ra”.

Nếu secret được dẫn xuất từ shared secret của một handshake, dùng **KDF/key schedule chính thức** (thường HKDF với salt và context). Không lấy một đoạn `String`/password rồi gọi `getBytes(UTF_8)` làm ChaCha20 key. Password cần KDF chuyên dùng (chẳng hạn Argon2id từ thư viện được thẩm định, hoặc PBKDF2 với tham số chính sách phù hợp). Không sử dụng ChaCha20-Poly1305 như một password-hashing function.

### 3.2. Vòng đời khóa

| Giai đoạn | Yêu cầu | Lỗi cần tránh |
| --- | --- | --- |
| **Tạo/cấp khóa** | Key 256-bit từ CSPRNG hoặc KDF an toàn; gắn với đúng phạm vi sử dụng. | Seed dự đoán được, key hard-code, dùng chung key cho quá nhiều môi trường. |
| **Phân phối** | Chỉ cho các phía được ủy quyền; bảo vệ ở trạng thái lưu trữ và truyền. | Gửi key qua email/HTTP plaintext, gắn trong URL hoặc message envelope. |
| **Lưu giữ** | KMS/HSM/keystore/provider được kiểm chứng khi phù hợp; quyền truy cập tối thiểu. | Để key trong repository, log, crash dump không kiểm soát. |
| **Sử dụng** | Dùng key ID để chọn secret và nonce domain riêng; giới hạn số bản tin/đời sống key. | Hai sender dùng chung key nhưng nonce allocation không phối hợp. |
| **Rotation** | Cấp key mới + ID mới, xác định thời điểm bắt đầu mã hóa. | Ghi đè key cũ nhưng giữ ID cũ khiến dữ liệu cũ không giải mã được. |
| **Giữ để giải mã** | Tạm giữ decryption keys cũ theo retention có giới hạn. | Hủy key quá sớm hoặc cho phép mã hóa tiếp bằng key đã retire. |
| **Thu hồi và dọn** | Dừng sử dụng, xóa các bản sao có thể xóa, thu hồi quyền truy cập. | Tưởng rằng `Arrays.fill` xóa được mọi bản sao bên trong JVM/provider. |

`SecretKey` có thể hoặc không cho phép xuất raw bytes tùy provider. Không log `key.getEncoded()` và không lưu raw secret trong tệp không được bảo vệ. Nếu tự xử lý `byte[]` chứa secret, hạn chế bản sao, giữ phạm vi sống ngắn và ghi đè mảng mình sở hữu bằng `Arrays.fill(bytes,(byte)0)` khi thích hợp; **đây chỉ là best effort**, không bảo đảm mọi bản sao do provider/JIT/native code tạo đã biến mất.

### 3.3. Key ID không phải secret

Bên nhận có thể có nhiều khóa đang dùng:

```java
Map<Integer, SecretKey> keyRing = Map.of(7, key);
SecretKey selected = keyRing.get(frameKeyId);
if (selected == null) {
    throw new IllegalArgumentException("Unknown key ID");
}
```

Đoạn này minh họa, cần khai báo `frameKeyId` và `key`. Key ID là nhãn lookup, thường có thể truyền plaintext, **không phải** cách tạo khóa. Bài học sẽ đưa key ID vào AAD để việc thay key ID (trong một gói có ID hợp lệ khác) gây thất bại xác thực.

Khi rotation, ID mới tương ứng key material mới; không dùng cùng một ID cho nhiều key khác nhau trong cùng phạm vi protocol. Nếu một gói cũ được giải mã trong giai đoạn migration, chọn đúng key cũ rồi xác minh tag; hết retention thì hủy quyền giải mã và xử lý dữ liệu lưu trữ theo chính sách.

## 4. Nonce: không cần bí mật nhưng tuyệt đối không được lặp với cùng khóa

Nonce của ChaCha20-Poly1305 là **12 byte**. Nó có thể được đưa vào header plaintext, nhưng **mỗi lần mã hóa dưới cùng key phải dùng nonce khác**.

> Quy tắc quan trọng nhất: **không được dùng lại cặp `(key, nonce)` để mã hóa hai bản tin.**

Với cùng key/nonce, ChaCha20 có thể tái tạo keystream, làm lộ quan hệ giữa plaintext; cấu trúc Poly1305 cũng chịu rủi ro nghiêm trọng về xác thực. Không có bảo đảm rằng `Cipher` sẽ nhớ tất cả nonce đã dùng trong các instance JVM, các tiến trình và các lần restart.

### 4.1. Hai chiến lược nonce thường gặp

**Nonce ngẫu nhiên:** sử dụng `SecureRandom.nextBytes(new byte[12])`. Điều này đơn giản nhưng uniqueness mang tính xác suất, không phải cam kết tuyệt đối. Với số bản tin lớn, thời gian dùng key dài hoặc nhiều sender, cần đánh giá xác suất va chạm và hạn mức.

**Nonce counter có phân vùng:** chia 96 bit thành prefix riêng của một nonce domain và counter không lặp, thí dụ:

```text
          96-bit nonce (12 byte)
+---------------------+---------------------------------+
| Prefix 32 bit       | Counter 64 bit, big-endian      |
| thuộc một domain    | 0, 1, 2, ...                   |
+---------------------+---------------------------------+
```

Trong demo, `NonceSequence` có một prefix ngẫu nhiên được tạo một lần và `long` counter tăng đồng bộ. **Khóa ChaCha20 cũng được sinh mới mỗi lần chạy**, nên đây chỉ là mô hình **một key/một tiến trình trong một phiên chạy**. Khi counter bắt đầu âm (đã vượt vùng dùng được), code từ chối cấp thêm nonce.

**Cảnh báo production:** 4 byte prefix ngẫu nhiên **không chứng minh** hai process dùng cùng key sẽ có prefix khác nhau. Nếu service dùng chung key, cần phân chia nonce domain không giao nhau hoặc key riêng cho mỗi instance/direction. Nếu dùng lại key sau crash/restart, phải giữ counter/prefix bền vững và không rollback, hoặc phát key mới. Không dùng timestamp, tên luồng hay request ID không duy nhất làm nonce.

### 4.2. Nonce không phải ChaCha20 block counter

`ChaCha20ParameterSpec` cho stream cipher có **nonce 12 byte + initial counter 32 bit**. Trong ChaCha20-Poly1305, thuật toán AEAD tự thực hiện phần counter theo RFC 8439. Java dùng `IvParameterSpec(nonce)` chứ không thêm initial block counter.

Một lỗi phổ biến là cố thay counter trong một cách tự chế để “cho phép reuse nonce” với ChaCha20-Poly1305. Không làm vậy: **mỗi AEAD invocation với cùng khóa phải có nonce riêng**.

### 4.3. Nonce và replay protection khác nhau

Nonce uniqueness đảm bảo **bên gửi không mã hóa hai lần với cùng key/nonce**. Nhưng nếu attacker lấy nguyên **gói hợp lệ đã mã hóa** gửi lại nguyên vẹn, tag vẫn có thể hợp lệ: AEAD không tự đánh dấu gói đã xử lý.

Một giao thức thực sự chống replay cần sequence/message ID, replay window hoặc idempotency state, ràng buộc với sender/session/key ID. Kiểm tra anti-replay **sau khi tag đã xác thực**, và quản lý memory/retention thay vì giữ vô hạn các nonce đã thấy trong một `HashSet`.

## 5. Những metadata cần truyền kèm ciphertext

| Trường | Có thể gửi plaintext? | Tại sao cần và kiểm soát gì? |
| --- | --- | --- |
| **Magic/protocol ID** | Có | Phân biệt format; nên xác thực bằng AAD. |
| **Version** | Có | Chọn cách parse được hỗ trợ; không downgrade ngầm. |
| **Cipher suite ID** | Có | Xác định transformation và chính sách; không chấp nhận thuật toán không được duyệt. |
| **Key ID** | Có | Chọn đúng decryption key; không được coi là secret. |
| **Message type** | Có | Text/binary/lệnh ứng dụng, ảnh hưởng cách parse; đưa vào AAD. |
| **Nonce** | Có | 12 byte, bên nhận phải dùng **đúng nonce bên gửi** đã dùng. |
| **Ciphertext length** | Có | Xác định byte framing, hạn mức và nơi kết thúc tag; nên đưa vào AAD. |
| **Ciphertext** | Có | Mang dữ liệu được mã hóa. |
| **Poly1305 tag** | Có | 16 byte, xác minh toàn vẹn của ciphertext và AAD. |
| **Secret key bytes** | **Không bao giờ gửi cùng packet** | Phải được phân phối bảo mật hoặc dẫn xuất bằng key-management protocol. |
| **External AAD** | Có thể tái tạo từ session context | Hai phía phải cung cấp **chính xác cùng byte**, cùng thứ tự. |

**AAD = authenticated, không phải encrypted.** Header metadata có thể bị người khác nhìn thấy, nhưng không thể sửa một cách tùy ý để vượt qua tag verification nếu key chưa lộ. Không đưa token, mật khẩu hay thông tin cá nhân vào AAD với kỳ vọng chúng được che giấu.

Một số hệ thống không cần trường length trong AEAD envelope vì transport đã cung cấp framing tin cậy; số khác cần length-prefix. Dù chọn cách nào, phải chỉ rõ byte order, maximum length, encoding, ranh giới tag và cơ chế kiểm tra lỗi.

## 6. Định dạng message minh họa có byte layout cố định

Ví dụ Java 11 sử dụng **format tự định nghĩa chỉ cho mục đích học tập**:

```text
Offset   Độ dài     Trường                          Giá trị ví dụ
0        4 byte     Magic ASCII                     C20P
4        1 byte     Version                         1
5        1 byte     Suite ID                        1 = ChaCha20-Poly1305
6        4 byte     Key ID                          7 (big-endian)
10       1 byte     Type                            1=text, 2=binary
11       12 byte    Nonce                           prefix4 || counter8
23       4 byte     Ciphertext+tag length           29 (big-endian)
---------------------------------------------------------------
27       N byte     Ciphertext || tag               13 byte + 16 byte
```

**Header là 27 byte**. Gói chứa plaintext `"HELLO JAVA 11"` dài 13 byte UTF-8 sẽ có ciphertext 13 byte và authentication tag 16 byte. Tổng chiều dài: **27 + 13 + 16 = 56 byte**.

Tất cả 27 byte header được đưa vào **`cipher.updateAAD(header)`**. Bên nhận cần dùng chính những byte đó làm AAD khi decrypt. `ByteBuffer.putInt/getInt` mặc định là **big-endian**, nên format khai báo byte order tường minh.

### Vì sao vừa parse header trước, vừa gọi nó là “chưa đáng tin”?

Trước khi verify tag, ứng dụng phải **đọc tối thiểu đủ header** để biết nonce, key ID, length. Tuy nhiên header nhận từ mạng có thể bị giả mạo. Vì thế:

1. Chỉ đọc trong giới hạn mảng; reject frame quá ngắn.
2. Kiểm tra magic/version/suite/type có thuộc danh sách được phép.
3. Kiểm tra ciphertext+tag length tối thiểu 16, tối đa quota và **đúng bằng byte thực nhận**.
4. Chọn key theo key ID một cách có kiểm soát.
5. Khởi tạo AEAD với nonce, dùng header gốc làm AAD, gọi `doFinal`.
6. **Chỉ sau khi tag đúng** mới xử lý message type, nội dung và các metadata như một yêu cầu đáng tin.

Một version/type sai có thể bị reject ngay trước decrypt. Với type vẫn nằm trong tập được cho phép nhưng bị thay, tag verification phải thất bại vì AAD không khớp.

**Không xử lý các side effect nghiệp vụ dựa trên header chưa được xác thực.** Thông báo lỗi khác nhau cho unknown key/tag failure có thể tạo một “oracle” lộ thông tin trạng thái hệ thống; ở ranh giới public cân nhắc trả một lỗi xác thực chung, trong nội bộ vẫn ghi metric an toàn.

## 7. Bên gửi và bên nhận làm gì?

### Bên gửi

```text
Cấp mới / tìm SecretKey 256-bit theo key ID
             |
             v
Tạo nonce mới duy nhất trong nonce domain của key đó
             |
             v
Chuyển plaintext thành byte[], kiểm tra quota
             |
             v
Tạo header: magic/version/suite/keyId/type/nonce/length
             |
             v
Cipher.getInstance("ChaCha20-Poly1305")
  init(ENCRYPT_MODE, key, IvParameterSpec(nonce))
  updateAAD(header)
  doFinal(plaintext) => ciphertext||tag
             |
             v
Gửi header || ciphertext || tag
```

Khi nonce đã cấp nhưng mã hóa hoặc gửi thất bại, **bỏ qua nonce đó** thay vì trả counter về giá trị cũ. Bỏ lỡ một số counter không đáng kể so với rủi ro reuse.

### Bên nhận

```text
Nhận frame, kiểm tra tổng kích thước và quota
             |
             v
Đọc header 27 byte, kiểm tra format/key ID/length
             |
             v
Lấy đúng SecretKey theo key ID
             |
             v
Cipher.getInstance("ChaCha20-Poly1305")
  init(DECRYPT_MODE, key, IvParameterSpec(nonce from frame))
  updateAAD(header bytes from frame)
  doFinal(ciphertext||tag)
             |
           +----+----+
           |         |
        Tag sai    Tag đúng
           |         |
           v         v
        Reject   kiểm tra replay, schema, quyền
                     |
                     v
                xử lý message
```

**Bên nhận không tự sinh nonce mới** để decrypt. Với ciphertext đã nhận, cần dùng lại nonce từ envelope. Điều kiện uniqueness áp dụng cho **những lần mã hóa khác nhau**, không phải bắt giải mã một ciphertext cũ phải dùng nonce mới.

`Cipher` là object có state; tránh dùng chung một instance mutable giữa nhiều thread, nhiều message và nhiều lần mã hóa. Tạo cipher theo từng operation là cách đơn giản để kiểm soát lifecycle và tránh reuse parameters.

## 8. Chương trình Java 11 hoàn chỉnh: envelope, nonce và negative tests

Chương trình không mở socket, không cần Internet và không ghi secret ra file. Nó kiểm tra:

- Sinh key ChaCha20 256-bit; hai lần encrypt cùng plaintext dùng **nonce khác**.
- Giải mã một frame có **version, suite, key ID, type, nonce, length** và tag hợp lệ.
- Sửa byte tag, AAD header, nonce hoặc dùng khóa khác: bắt **`AEADBadTagException`**.
- Version lạ, length bị cắt và key ID không có: từ chối bằng lỗi format.
- Header và payload có độ dài **chính xác**, không cắt hay đoán kết quả stdout.

Lưu thành **`ChaCha20EnvelopeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;

public final class ChaCha20EnvelopeDemo {
    private static final byte[] MAGIC = {'C', '2', '0', 'P'};
    private static final byte VERSION = 1;
    private static final byte SUITE = 1;
    private static final byte TYPE_TEXT = 1;
    private static final byte TYPE_BINARY = 2;
    private static final int HEADER_BYTES = 27;
    private static final int TAG_BYTES = 16;
    private static final int MAX_PLAINTEXT = 4096;
    private static final int TYPE_OFFSET = 10;
    private static final int NONCE_OFFSET = 11;

    static final class NonceSequence {
        private final int prefix;
        private long nextCounter;

        NonceSequence(SecureRandom random) {
            prefix = random.nextInt();
        }

        synchronized byte[] nextNonce() {
            if (nextCounter < 0) {
                throw new IllegalStateException("Nonce sequence exhausted");
            }
            return ByteBuffer.allocate(12)
                    .putInt(prefix)
                    .putLong(nextCounter++)
                    .array();
        }
    }

    static final class Opened {
        final byte type;
        final byte[] plaintext;
        Opened(byte type, byte[] plaintext) {
            this.type = type;
            this.plaintext = plaintext;
        }
    }

    static byte[] seal(SecretKey key, int keyId, byte type, byte[] plaintext,
                       NonceSequence nonces) throws Exception {
        if (type != TYPE_TEXT && type != TYPE_BINARY) {
            throw new IllegalArgumentException("Unsupported message type");
        }
        if (plaintext.length > MAX_PLAINTEXT) {
            throw new IllegalArgumentException("Message too long");
        }
        byte[] nonce = nonces.nextNonce();
        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
                .put(MAGIC).put(VERSION).put(SUITE).putInt(keyId)
                .put(type).put(nonce).putInt(plaintext.length + TAG_BYTES)
                .array();

        Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
        aead.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        aead.updateAAD(header);
        byte[] ciphertextAndTag = aead.doFinal(plaintext);
        return ByteBuffer.allocate(header.length + ciphertextAndTag.length)
                .put(header).put(ciphertextAndTag).array();
    }

    static Opened open(Map<Integer, SecretKey> keyRing, byte[] frame)
            throws Exception {
        if (frame.length < HEADER_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Frame too short");
        }
        ByteBuffer h = ByteBuffer.wrap(frame, 0, HEADER_BYTES);
        for (byte m : MAGIC) {
            if (h.get() != m) throw new IllegalArgumentException("Bad magic");
        }
        byte version = h.get();
        byte suite = h.get();
        if (version != VERSION || suite != SUITE) {
            throw new IllegalArgumentException("Unsupported version or suite");
        }
        int keyId = h.getInt();
        byte type = h.get();
        if (type != TYPE_TEXT && type != TYPE_BINARY) {
            throw new IllegalArgumentException("Unsupported message type");
        }
        byte[] nonce = new byte[12];
        h.get(nonce);
        int length = h.getInt();
        if (length < TAG_BYTES || length > MAX_PLAINTEXT + TAG_BYTES
                || length != frame.length - HEADER_BYTES) {
            throw new IllegalArgumentException("Invalid body length");
        }
        SecretKey key = keyRing.get(keyId);
        if (key == null) throw new IllegalArgumentException("Unknown key ID");

        Cipher aead = Cipher.getInstance("ChaCha20-Poly1305");
        aead.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        aead.updateAAD(frame, 0, HEADER_BYTES);
        return new Opened(type, aead.doFinal(frame, HEADER_BYTES, length));
    }

    static boolean rejectedByTag(Map<Integer, SecretKey> keys, byte[] frame)
            throws Exception {
        try {
            open(keys, frame);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    static boolean rejectedByFormat(Map<Integer, SecretKey> keys, byte[] frame)
            throws Exception {
        try {
            open(keys, frame);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("ChaCha20");
        generator.init(256, random);
        SecretKey key = generator.generateKey();
        Map<Integer, SecretKey> keys = Map.of(7, key);
        NonceSequence nonces = new NonceSequence(random);

        byte[] content = "HELLO JAVA 11".getBytes(StandardCharsets.UTF_8);
        byte[] first = seal(key, 7, TYPE_TEXT, content, nonces);
        byte[] second = seal(key, 7, TYPE_TEXT, content, nonces);
        Opened opened = open(keys, first);

        System.out.println("key-algorithm=" + key.getAlgorithm());
        System.out.println("frame-bytes=" + first.length);
        System.out.println("roundtrip=" +
                new String(opened.plaintext, StandardCharsets.UTF_8));
        System.out.println("message-type-text=" + (opened.type == TYPE_TEXT));
        System.out.println("nonces-unique=" + !Arrays.equals(
                Arrays.copyOfRange(first, NONCE_OFFSET, NONCE_OFFSET + 12),
                Arrays.copyOfRange(second, NONCE_OFFSET, NONCE_OFFSET + 12)));

        byte[] tamperedBody = first.clone();
        tamperedBody[tamperedBody.length - 1] ^= 1;
        System.out.println("tampered-tag-rejected=" +
                rejectedByTag(keys, tamperedBody));

        byte[] tamperedType = first.clone();
        tamperedType[TYPE_OFFSET] = TYPE_BINARY;
        System.out.println("tampered-aad-rejected=" +
                rejectedByTag(keys, tamperedType));

        byte[] tamperedNonce = first.clone();
        tamperedNonce[NONCE_OFFSET] ^= 1;
        System.out.println("tampered-nonce-rejected=" +
                rejectedByTag(keys, tamperedNonce));

        KeyGenerator anotherGenerator = KeyGenerator.getInstance("ChaCha20");
        anotherGenerator.init(256, random);
        SecretKey wrongKey = anotherGenerator.generateKey();
        System.out.println("wrong-key-rejected=" +
                rejectedByTag(Map.of(7, wrongKey), first));

        byte[] wrongVersion = first.clone();
        wrongVersion[4] = 2;
        System.out.println("unknown-version-rejected=" +
                rejectedByFormat(keys, wrongVersion));

        byte[] truncated = Arrays.copyOf(first, first.length - 1);
        System.out.println("truncated-frame-rejected=" +
                rejectedByFormat(keys, truncated));

        System.out.println("unknown-keyid-rejected=" +
                rejectedByFormat(Map.of(9, key), first));
    }
}
```

### Biên dịch và chạy

Dùng JDK 11 trở lên. `--release 11` kiểm tra cú pháp và public API có từ Java 11:

```bash
javac -encoding UTF-8 --release 11 ChaCha20EnvelopeDemo.java
java ChaCha20EnvelopeDemo
```

**Stdout đã được kiểm thử:**

```text
key-algorithm=ChaCha20
frame-bytes=56
roundtrip=HELLO JAVA 11
message-type-text=true
nonces-unique=true
tampered-tag-rejected=true
tampered-aad-rejected=true
tampered-nonce-rejected=true
wrong-key-rejected=true
unknown-version-rejected=true
truncated-frame-rejected=true
unknown-keyid-rejected=true
```

Giải thích:

1. `key-algorithm=ChaCha20`: secret key được sinh bằng factory tên `ChaCha20`; cipher dùng transformation `ChaCha20-Poly1305`.
2. `frame-bytes=56`: `27` byte header + `13` byte ciphertext + `16` byte tag. Đây là gói theo schema minh họa, không phải một header JCE tự động sinh.
3. `roundtrip=HELLO JAVA 11`: payload được giải mã đúng với key, nonce và AAD.
4. `message-type-text=true`: type 1 được chấp nhận và **đã qua xác thực** khi AEAD `doFinal` thành công.
5. `nonces-unique=true`: hai lần `seal` dùng cùng key và cùng `NonceSequence` nhưng counter tăng nên nonce khác nhau. Không suy rộng kết quả này sang multi-process/restart.
6. `tampered-tag-rejected=true`: đổi một bit ở tag khiến xác thực thất bại.
7. `tampered-aad-rejected=true`: đổi type hợp lệ từ 1 sang 2 trong header khiến tag không còn khớp.
8. `tampered-nonce-rejected=true`: sửa nonce trong header sẽ làm việc giải mã/tag verification thất bại.
9. `wrong-key-rejected=true`: key material khác cho cùng ID không thể xác minh ciphertext/tag.
10. `unknown-version-rejected=true`: version ngoài tập cho phép bị từ chối khi parse.
11. `truncated-frame-rejected=true`: số byte thực tế không còn bằng length đã khai báo, bị từ chối trước decrypt.
12. `unknown-keyid-rejected=true`: key ring không có ID được yêu cầu nên không có key hợp lệ để giải mã.

**Giới hạn bài thực hành:** mọi thành phần chạy trong một JVM với khóa mới được sinh tại mỗi lần chạy; không có network, KMS, persistent state, replay window hoặc cơ chế xác thực người gửi. Đây là minh họa AEAD và envelope, **không phải giao thức bảo mật production đã được thẩm định**.

## 9. Ranh giới byte, text, binary và AAD

Sau khi decrypt, người nhận mới quyết định xử lý plaintext dựa trên **type đã được xác thực**:

- Với **text**, protocol cần chỉ rõ charset, thường là UTF-8. Encode bằng `text.getBytes(StandardCharsets.UTF_8)` và decode theo charset tương ứng; `String.length()` đếm đơn vị UTF-16, **không** phải độ dài wire byte.
- Với **binary**, giữ nguyên byte[], sau đó dùng codec thích hợp (Protobuf, CBOR, image, file format riêng). Không cố decode mọi ciphertext thành text.
- Với **header**, giữ byte order big-endian cố định. Nếu có metadata ngoài header (tenant ID, session ID, sequence), hoặc truyền và đưa vào AAD, hoặc bảo đảm hai phía có thể tái tạo **chính xác cùng bytes**.
- Với **AAD**, tất cả trường ảnh hưởng cách xử lý (version, suite, key ID, content type, length, sender/session/role khi cần) phải được ràng buộc theo định dạng không mơ hồ. Nếu ghép nhiều trường biến độ dài, dùng length-prefix/schema rõ ràng thay vì nối tùy tiện.
- Với **secret data**, không đưa vào metadata plaintext/AAD vì AAD chỉ được xác thực chứ không che giấu.

Dùng `Cipher.updateAAD(...)` **trước** `doFinal`. Nếu có nhiều đoạn AAD, hai phía phải xác định đúng thứ tự và tập byte đã sử dụng. Ciphertext có 16 byte tag ở cuối theo quy ước ChaCha20-Poly1305; không được bỏ tag hoặc “rút ngắn tag cho nhẹ”.

## 10. Nhiều máy, khởi động lại và xoay vòng khóa

**Trường hợp một process với key mới:** `NonceSequence` trong demo cấp các counter khác nhau theo từng lời gọi. Nó đủ để minh họa nonce uniqueness **trong phạm vi một key mới và một instance sequence**.

**Trường hợp key tồn tại sau restart:** nếu lưu lại key nhưng reset counter về 0, có thể phát sinh reuse. Production cần ghi bền vững trạng thái counter và cấp phát an toàn trước crash, hoặc rotate key khi tạo lại nonce state. Prefix ngẫu nhiên 32-bit **không bảo đảm** rằng mọi lần restart dùng key cũ sẽ nhận prefix khác.

**Trường hợp nhiều node:** hai node có cùng key và cùng counter không thể tự phát gói an toàn chỉ vì chúng ở hai máy khác nhau. Cần nonce ranges độc quyền, prefix được cấp theo authority, hoặc **key khác nhau cho từng node/direction**. Thông thường key schedule có domain separation cho chiều client→server, server→client và từng session.

**Trường hợp rotation:** gói mới mang key ID mới, nonce domain mới. Gói cũ có thể được giải mã bằng key cũ cho đến hết retention có giới hạn. Nếu key cũ bị thu hồi hoặc nghi lộ, không tiếp tục dùng để encrypt; xử lý re-encryption/invalidating dữ liệu và session theo policy.

**Trường hợp ciphertext hợp lệ được gửi lại:** authentication tag vẫn hợp lệ. Cần replay window, message counter hoặc idempotency logic sau khi tag verify. Không coi việc nhận cùng nonce trong một packet replay là “sự kiện ChaCha20 tự phát hiện” nếu protocol không thiết kế lưu state.

## 11. Lỗi đầu vào và nguyên tắc fail closed

| Lỗi | Cách xử lý |
| --- | --- |
| Không đủ header hoặc tag | Reject trước khi parse; không đọc ngoài biên array. |
| Magic/version/suite/type không hỗ trợ | Reject rõ ràng; không thử cipher yếu hơn theo ý attacker. |
| Key ID không có | Không sinh key mới từ ID và không lấy key mặc định. |
| Độ dài âm/quá mức/không khớp frame | Reject trước cấp phát hoặc gọi crypto; áp dụng quota tổng packet. |
| Nonce bị sửa | AEAD authentication fail nếu frame còn qua validation. |
| Ciphertext hoặc tag bị sửa | `AEADBadTagException`; không sử dụng plaintext. |
| AAD (metadata) thay đổi | Tag không khớp; không xử lý action theo header chưa xác thực. |
| Khóa bí mật sai | Tag fail; kiểm tra key-provisioning bằng metric nội bộ an toàn. |
| Provider không hỗ trợ thuật toán | `NoSuchAlgorithmException` hoặc lỗi JCE liên quan; **không tự fallback**. |
| Gửi lại ciphertext đã từng hợp lệ | AEAD vẫn có thể xác thực; chống replay phải ở tầng protocol. |
| Dữ liệu sau decrypt sai schema | Parse/validate theo nghiệp vụ; không coi thành công mật mã là thành công nghiệp vụ. |

Ở ranh giới public, không nhất thiết trả thông điệp phân biệt “không có key ID”, “tag sai”, “sai nonce” cho client không tin cậy, vì có thể tạo side-channel/oracle. Có thể phân loại nội bộ qua log có kiểm soát mà **không ghi raw key, plaintext nhạy cảm, token hoặc full packet**.

Nếu dùng streaming AEAD, không giao plaintext chưa xác thực cho handler nghiệp vụ trước khi toàn bộ authentication tag được xác minh. Ví dụ dùng `doFinal(byte[])` nên chỉ trả `Opened` khi kiểm tra tag hoàn tất.

## 12. Kế hoạch kiểm thử thực tế

| Test | Điều cần assert |
| --- | --- |
| Round-trip đúng | Giải mã đúng byte, type và metadata đã xác thực. |
| Độ dài | `frame.length == header + ciphertext + tag`; UTF-8 tính byte. |
| Nonce distinct | Hai gói mã hóa cùng key nhận nonce khác trong một nonce domain. |
| Tamper tag/ciphertext | Thay 1 bit làm authentication failure. |
| Tamper AAD | Đổi một trường header vẫn hợp lệ về syntax làm tag fail. |
| Tamper nonce | Header nonce sửa khiến giải mã/tag fail. |
| Sai key | Dùng secret key khác bị reject. |
| Unknown key ID | Reject mà không lấy key không có/không tạo key giả. |
| Version/suite lạ | Fail closed, không tự downgrade. |
| Frame bị cắt/dài thừa | Reject chính xác trước khi cấp phát theo length giả. |
| Empty plaintext | Frame vẫn có tag 16 byte; policy quyết định cho phép hay không. |
| Binary payload | Giữ nguyên byte không hợp lệ UTF-8, không tự decode text. |
| Key rotation | Gói mới dùng key ID/nonce domain mới, gói cũ theo retention. |
| Restart và multi-node | Không lặp nonce với key còn hiệu lực, kể cả khi có crash. |
| Replay | Protocol reject lần gửi lại nếu nghiệp vụ đòi at-most-once. |
| Interoperability | Test vectors RFC 8439 và byte-format golden files giữa các implementation. |

Ngoài round-trip (mã hóa và giải mã cùng một implementation), cần test bằng **RFC 8439 test vectors** để xác nhận algorithm, nonce, AAD và tag đúng. Hai hàm encoder/decoder cùng mắc một lỗi framing vẫn có thể round-trip được, nhưng không tương thích một hệ thống khác.

Không dùng khóa trong test vector làm khóa production. Không benchmark tính an toàn của CSPRNG bằng một vài lần gọi random rồi nhìn thấy giá trị khác nhau; cần dựa vào provider, cấu hình entropy và review security.

## 13. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “ChaCha20 tự có authentication tag.” | Chỉ **ChaCha20-Poly1305** là AEAD, ChaCha20 thuần không có tag. |
| “`ChaCha20ParameterSpec` dùng cho Poly1305 mode.” | AEAD Java 11 dùng `IvParameterSpec` 12-byte nonce. |
| “Chỉ cần khóa dài, nonce trùng cũng không sao.” | Reuse `(key,nonce)` có thể phá confidentiality và authentication. |
| “Nonce là bí mật, không cần gửi.” | Nonce có thể truyền plaintext và người nhận phải biết đúng nó. |
| “Random nonce không bao giờ trùng.” | Chỉ có xác suất va chạm nhỏ; scale và key lifetime vẫn cần kiểm soát. |
| “Một counter trong RAM luôn đủ kể cả khi restart.” | Sai khi phục hồi cùng key mà counter/prefix bị reset. |
| “Hai máy cùng key nhưng counter độc lập là an toàn.” | Có thể dùng cùng nonce, cần phân chia domain hoặc key riêng. |
| “Key ID có thể tạo lại key material.” | Key ID chỉ định danh secret đã được bảo vệ. |
| “Có thể gửi key trong header rồi mã hóa body.” | Làm lộ toàn bộ bảo mật của ciphertext. |
| “AAD bị mã hóa.” | Không; AAD chỉ được **xác thực**. |
| “Có tag thì header không cần đưa vào AAD.” | Metadata ảnh hưởng cách hiểu/định tuyến phải được xác thực. |
| “Tag 16 byte có thể cắt còn 4 byte.” | Trái với format ChaCha20-Poly1305 chuẩn RFC 8439. |
| “Authentication tag đúng nghĩa là message chưa từng gửi.” | Không; replay gói hợp lệ vẫn có tag đúng. |
| “Đúng tag nghĩa là user đã có quyền thực hiện action.” | Phân quyền/identity còn là logic riêng của protocol. |
| “Độ dài message là `String.length()`.” | Độ dài wire là byte sau encoding, không phải đơn vị UTF-16. |
| “`Cipher` dùng chung thread-safe như singleton.” | Cipher là object có state; không sử dụng đồng thời không đồng bộ. |
| “Thấy `AEADBadTagException` thì thử ChaCha20 không tag.” | Nguy hiểm: downgrade bỏ bảo đảm xác thực. |
| “Envelope ví dụ đã là format được audit.” | Đây là format bài học, không nên tự phát triển protocol production chỉ từ demo. |

## 14. Checklist triển khai Java 11+

1. Chọn `ChaCha20-Poly1305` cho message cần confidentiality và integrity; không thay bằng ChaCha20 thuần khi không có authentication protocol.
2. Sinh hoặc dẫn xuất secret key **256-bit** bằng JCA/KDF đúng, không dùng mật khẩu hoặc PRNG thường làm key.
3. Duy trì key ID, phạm vi sử dụng, key provisioning, rotation, retention và revocation.
4. Thiết kế nonce 12-byte **unique per key** cho mọi sender, session, direction, process và restart.
5. Định nghĩa format packet với version, suite, key ID, message type, nonce, length và ciphertext||16-byte tag.
6. Đưa các metadata ảnh hưởng ý nghĩa message vào AAD và truyền/cấu trúc theo byte-order thống nhất.
7. Dùng `IvParameterSpec(nonce)` cho `ChaCha20-Poly1305` và gọi `updateAAD` trước `doFinal`.
8. Kiểm tra length/quota và allowlist của version/suite/type trước decrypt; chỉ tin metadata nghiệp vụ sau tag verify.
9. Không trả plaintext hoặc side effects khi tag sai; không downgrade sang cipher không xác thực.
10. Nếu cần at-most-once semantics, bổ sung anti-replay state/idempotency; AEAD một mình không đảm bảo.
11. Phân biệt UTF-8 text và binary; kiểm tra schema, authorization sau khi decrypt.
12. Kiểm thử negative cases và các tình huống multi-node, crash/restart, key rotation, tamper AAD/nonce/tag.
13. Ưu tiên protocol đã được thẩm định khi bảo vệ kết nối thực tế (ví dụ TLS 1.3), thay vì tự biến envelope demo thành giao thức Internet.
14. Đánh giá provider và runtime **JDK** thực tế; các API ChaCha20 có từ Java 11 và vẫn dùng trên các phiên bản hiện đại.

### Tài liệu chính thức

- [Oracle Java SE 11 — `Cipher`, ChaCha20/ChaCha20-Poly1305, nonce và AEAD](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html)
- [Oracle Java SE 11 — `ChaCha20ParameterSpec` và initial counter của ChaCha20 thuần](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html)
- [Oracle Java SE 11 — Standard Algorithm Names: ChaCha20 và ChaCha20-Poly1305](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html)
- [Oracle Java SE 11 — SunJCE provider và các transformations](https://docs.oracle.com/en/java/javase/11/security/oracle-providers.html)
- [Oracle Java SE 11 — `IvParameterSpec`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/IvParameterSpec.html)
- [Oracle Java SE 11 — `KeyGenerator` và `SecureRandom`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/KeyGenerator.html)
- [Oracle Java SE 25 — `ChaCha20ParameterSpec` hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html)
- [RFC 8439 — ChaCha20, Poly1305 và AEAD, nhất là mục `2.8`](https://www.rfc-editor.org/rfc/rfc8439.html)
