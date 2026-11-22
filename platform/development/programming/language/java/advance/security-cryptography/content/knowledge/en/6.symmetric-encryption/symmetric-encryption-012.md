# 6.12 Đóng gói IV, tham số, ciphertext, tag và chỉ sử dụng bản rõ sau khi xác thực thành công

Một bản mã an toàn phải được **lưu và truyền cùng những thông tin cần thiết để giải mã và xác thực đúng cách**. Với mã hóa xác thực như **AES-GCM**, các thành phần thường gồm: phiên bản định dạng, thuật toán/bộ tham số đã được chính sách cho phép, mã nhận diện khóa (*key ID*), IV/nonce, ciphertext, authentication tag và ngữ cảnh dữ liệu xác thực bổ sung (*AAD*, nếu có). Ở phía nhận, chỉ được **đưa bản rõ vào xử lý nghiệp vụ sau khi kiểm tra tag thành công**.

Điểm dễ bỏ sót: IV không phải khóa bí mật; tag không phải ciphertext; AAD không bị mã hóa; tiêu đề (*header*) của gói cũng phải được ràng buộc toàn vẹn nếu nó quyết định cách hiểu dữ liệu. Việc `Cipher.update(...)` có thể trả về byte trong một số chế độ/provider **không có nghĩa những byte đó đã được xác thực**. Trong AES-GCM, tính hợp lệ của toàn bộ ciphertext và AAD chỉ được xác lập khi phép kiểm tra tag ở `doFinal(...)` hoàn tất thành công.

Bài này dùng **Java 17+ và JCA/JCE** để giải thích hợp đồng byte, đề xuất một envelope có version, minh họa mã hóa/giải mã AES-GCM, thử sửa từng phần, và chỉ rõ cách tránh sử dụng bản rõ chưa xác thực trong API, file và pipeline streaming.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt chính xác **IV/nonce**, các tham số thuật toán, **ciphertext**, **tag**, **AAD**, **key ID** và **khóa bí mật**.
2. Thiết kế định dạng binary envelope không mơ hồ, có version và giới hạn kích thước.
3. Hiểu Java `Cipher.getInstance("AES/GCM/NoPadding")`, `GCMParameterSpec`, `updateAAD` và `doFinal`, gồm byte đầu ra `ciphertext || tag` của ví dụ JCA.
4. Giải mã bằng cách parse có kiểm soát, lấy đúng key, xác thực AAD/header và **chỉ công bố bản rõ sau `doFinal` thành công**.
5. Nhận diện lỗi nonce trùng dưới cùng khóa, header có thể bị sửa, nhầm tag length đơn vị bit/byte, xử lý lỗi lộ thông tin và xuất bản rõ quá sớm.
6. Lập test cho đúng gói, sai tag, sai IV, sai AAD, sai key, cắt ngắn, dữ liệu dư, đổi version và concurrency.
7. Xác định giới hạn của cách làm với file lớn, stream, cipher provider, lưu trữ và vòng đời khóa.

## 2. Một encrypted envelope thực chất chứa những gì?

Giả sử dịch vụ Java cần lưu một tài liệu đã được mã hóa. Một gói có thể có dạng:

```text
+----------+---------+--------+-------------+----------------+------------+---------+
| Magic    | Version | Key ID | GCM params  | IV / nonce     | Ciphertext | Tag     |
+----------+---------+--------+-------------+----------------+------------+---------+
       \_________________ authenticated header _______________/
                     \_____________ AAD _____________/
                          (context nghiệp vụ khác cũng có thể làm AAD)
                                     \____ ciphertext+tag ____/
```

Đây là **sơ đồ logic**, không có nghĩa AAD tự xuất hiện dưới dạng đoạn byte riêng trong output của `Cipher.doFinal`. Bên mã hóa cung cấp AAD cho `Cipher.updateAAD(...)`; phía giải mã phải cung cấp **đúng cùng byte AAD theo cùng thứ tự** để xác minh tag. Nếu một metadata cần phục hồi sau nhiều năm, nó có thể được lưu trong header và đưa chính byte header đó làm AAD.

| Thành phần | Chức năng | Có phải bí mật không? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Magic/version** | Nhận dạng định dạng, quy tắc giải mã | Không | Nhận đúng định dạng/version; các byte có ảnh hưởng an ninh phải được xác thực |
| **Algorithm/profile** | Chọn bộ thuật toán và tham số được phép | Không | Chỉ dùng allowlist đáng tin, không tự hạ cấp theo input |
| **Key ID** | Tìm khóa để giải mã trong kho khóa | Không nhất thiết | Giới hạn ID, quyền dùng khóa và vòng đời; xác thực ràng buộc ID với bản mã |
| **IV/nonce** | Giá trị độc nhất theo yêu cầu chế độ mã hóa | Thường không | Đúng độ dài, đúng ràng buộc **không tái sử dụng với cùng khóa** |
| **Ciphertext** | Nội dung đã mã hóa | Không được xem như bản rõ; vẫn cần bảo vệ truy cập | Kiểm tra cấu trúc, giới hạn độ dài, không sử dụng khi chưa xác thực |
| **Authentication tag** | Xác thực ciphertext và AAD | Không | Đúng độ dài, được kiểm trong `doFinal`; không tự bỏ qua |
| **AAD** | Ràng buộc metadata/ngữ cảnh không cần mã hóa | Không được AES-GCM mã hóa | Byte giống nhau giữa mã hóa/giải mã; bao gồm các trường tác động tới cách hiểu hoặc quyền |
| **Khóa bí mật** | Năng lực giải mã và tạo bản mã/tag hợp lệ | **Có** | **Không đóng gói chung với envelope**; lấy qua key store/KMS/HSM được kiểm soát |

Một encryption envelope *không tự động giải quyết phân quyền*. Kể cả khi tag hợp lệ, dịch vụ vẫn phải kiểm người dùng có quyền đọc tài liệu, đúng tenant, đúng hành động và đúng trạng thái nghiệp vụ.

### Vì sao cần version?

Không nên buộc ứng dụng phải đoán xem các byte đầu tiên là IV dài 12 hay 16 byte, tag dài bao nhiêu hay dùng thuật toán nào. Sau khi định dạng được triển khai, các bản mã cũ có thể tồn tại lâu hơn vòng đời của mã nguồn hiện tại. **Version** chỉ tới một đặc tả đủ chặt: thứ tự trường, encoding, độ dài, thuật toán, tag length, xử lý lỗi và phương pháp xác thực metadata.

Khi thay đổi profile, tạo version mới và có chính sách đọc dữ liệu cũ/luân chuyển khóa. Không tự “thử từng thuật toán cho tới khi giải mã ra thứ có vẻ là tiếng Việt”.

## 3. AES-GCM: ciphertext, tag và AAD được tạo ra ở đâu?

AES-GCM là chế độ **AEAD** (*Authenticated Encryption with Associated Data*): bảo mật bản rõ và tạo tag kiểm tra tính toàn vẹn của ciphertext cùng AAD. Hợp đồng API Java điển hình:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
cipher.updateAAD(aadBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintextBytes);
```

Đoạn trên **chỉ minh họa**, giả sử `key` là `SecretKey` AES, `iv` là byte[] phù hợp và `aadBytes`/`plaintextBytes` đã có. Khi dùng JCA AES-GCM theo cách này, output của `doFinal` chứa **ciphertext tiếp theo là authentication tag**; tag thường được nối ở cuối dữ liệu mã hóa. Trong profile minh họa: tag = **128 bit = 16 byte**.

Giải mã tương ứng:

```java
Cipher decipher = Cipher.getInstance("AES/GCM/NoPadding");
decipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
decipher.updateAAD(aadBytes);
byte[] verifiedPlaintext = decipher.doFinal(ciphertextAndTag);
```

Với ciphertext/tag/AAD/key/IV không hợp lệ, `doFinal` phải thất bại; nhiều provider Java báo `AEADBadTagException` (thuộc họ `BadPaddingException`), nhưng ứng dụng nên coi toàn bộ lỗi xác thực là **thất bại, không trả bất kỳ bản rõ nào**. Mỗi lần chạy cần đúng thứ tự `init -> updateAAD -> update/doFinal`; nhiều provider yêu cầu tất cả AAD phải được cung cấp **trước khi xử lý plaintext/ciphertext**.

### Phân biệt length và đơn vị

- `new GCMParameterSpec(128, iv)`: **128 là số bit tag**, không phải 128 byte.
- `iv.length == 12`: IV/nonce **12 byte = 96 bit**, kích thước được dùng phổ biến cho GCM.
- Với profile dùng tag 128 bit, ciphertext của bản rõ dài N byte cũng dài N byte, sau đó thêm tag 16 byte. Đây là quan hệ kích thước của AES-GCM không padding, **không** bao gồm header.
- Base64 hoặc hex chỉ là cách chuyển envelope nhị phân sang dạng văn bản; nó không tăng độ an toàn mật mã.
- `cipher.getIV()` có thể trả IV của cipher đã init; `cipher.getParameters()` có thể biểu diễn các tham số. Để lưu lâu dài và tương thích nhiều runtime, **nên quy định cách serialize rõ ràng** thay vì phụ thuộc vào một opaque encoding của `AlgorithmParameters`.

### Tag khác HMAC độc lập

Với AES-GCM, tag được tạo và kiểm tra bởi thuật toán AEAD gắn liền với ciphertext và AAD. **Không** bỏ tag rồi hy vọng giải mã trả văn bản trông hợp lý là đủ. Một MAC/HMAC độc lập là cơ chế khác với khóa/thiết kế/giao thức riêng; không thể nối tùy ý HMAC vào output AES-GCM rồi coi là cùng profile.

## 4. Một format binary đơn giản có giới hạn và version

Để dễ kiểm thử, bài sử dụng format **demo v1** sau, byte nối nhau đúng thứ tự:

```text
offset  size    field
0       4       magic = ASCII "GCM1"
4       1       version = 0x01
5       4       keyId = 7 (signed 32-bit big-endian, giá trị demo)
9       1       nonceLength = 12
10      12      nonce (ngẫu nhiên cho mỗi lần encrypt)
22      N       ciphertext (cùng độ dài với plaintext)
22+N    16      GCM authentication tag (128 bit)
```

Trong code Java, header cố định dài **22 byte**, nonce 12 byte và tag **16 byte**; envelope của plaintext 13 byte sẽ dài **22 + 13 + 16 = 51 byte**. `ByteBuffer` mặc định là big-endian; profile nên ghi rõ quy ước này dù chỉ có một trường `keyId` dài 4 byte.

**Đây là định dạng ví dụ**, không phải một chuẩn mạng được công nhận. Không dùng trực tiếp nó để xây hệ lưu trữ sản xuất mà bỏ qua thiết kế vòng đời key, nonce uniqueness ở quy mô triển khai, version migration, giới hạn kích thước, lỗi provider và phân quyền.

Những quyết định cần ghi trong spec thật:

1. **Magic và version:** byte giá trị cụ thể, version nào được chấp nhận, policy xử lý version cũ.
2. **Thuật toán:** với v1, `AES/GCM/NoPadding` và tag 128 bit được cấu hình **cố định**, không cho envelope tự yêu cầu thuật toán yếu hơn.
3. **Key ID:** biểu diễn và cách tra cứu đúng key trong key store/KMS, ai có quyền giải mã.
4. **IV:** độ dài 12 byte, nguồn tạo, cơ chế bảo đảm không trùng với cùng key, yêu cầu giới hạn số lần mã hóa.
5. **AAD:** byte của header và chuỗi context nghiệp vụ có cấu trúc; thứ tự và cách frame các trường phải xác định.
6. **Payload:** định dạng plaintext/ciphertext, giới hạn kích thước, byte order khi có trường số và cách xử lý file lớn.
7. **Tag:** 16 byte nằm cuối `ciphertextAndTag`; cần cả hai để giải mã.
8. **Lỗi:** bất kỳ kiểm tra format hay tag nào thất bại đều không tạo dữ liệu được tin cậy.

**Chú ý về header:** magic, version, key ID và nonce đến từ input **chưa xác thực** khi parser mới đọc. Chúng chỉ giúp định tuyến xử lý trong phạm vi đã cho phép; khi header được đưa vào AAD, tag thành công mới chứng minh các byte đó phù hợp với ciphertext và key. Không tạo đối tượng nghiệp vụ hay cấp quyền dựa trên header chưa xác thực.

## 5. Xác thực toàn bộ trước khi sử dụng bản rõ

Mối nguy quan trọng nhất của bài này là **dùng bản rõ trước khi kiểm tra tag hoàn tất**. Luồng an toàn với một envelope kích thước có giới hạn:

```text
receive envelope (không tin cậy)
         |
         v
kiểm format, version, độ dài, quota và khả năng cấp phát
         |
         v
parse header -> chọn key được phép, lấy IV, định nghĩa AAD
         |
         v
Cipher.init(DECRYPT_MODE, key, GCMParameterSpec)
         |
         v
updateAAD(đúng header và context đã thỏa thuận)
         |
         v
doFinal(toàn bộ ciphertext || tag)
       /   \
   lỗi      thành công
    |           |
không trả     plaintext đã xác thực
bản rõ          |
                 v
        kiểm schema/quyền nghiệp vụ
                 |
                 v
       mới lưu/trả/hiển thị/xử lý
```

`Cipher.doFinal(...)` trả về thành công là **điều kiện cần** để coi các byte được giải mã đã qua kiểm tra tag. Trong một số implementation, decryption theo từng khối với `update` có thể tạo output **trước khi tag cuối được kiểm**. Vì vậy, không đưa những byte đó ra HTTP response, file công khai, logger, parser có side effect hay hệ thống thanh toán.

### Những điều bị xem là “đã sử dụng bản rõ”

Không chỉ trả plaintext về client mới nguy hiểm. Các hành động sau cũng sử dụng bản rõ chưa xác thực nếu xảy ra trước `doFinal`:

- Ghi dữ liệu ra file mà thành phần khác có thể đọc.
- Ghi một bản ghi DB, phát Kafka/event hoặc thực hiện thanh toán dựa trên dữ liệu vừa giải mã.
- Parse và thực thi lệnh/biểu thức, gọi service phụ trợ hoặc truy vấn dựa trên nội dung chưa xác thực.
- Log bản rõ hoặc ghi vào trace/metrics có thể truy cập.
- Dùng plaintext để phân quyền hoặc chọn tài nguyên trước khi xác thực tag.

Quy tắc thực hành là **không publish**, **không commit side effect**, **không diễn giải như nguồn tin cậy** cho tới khi nhận được kết quả giải mã/xác thực hoàn chỉnh. Sau đó vẫn phải validate schema và kiểm quyền nghiệp vụ; một message hợp lệ về mật mã không tự biến hành động của người gửi thành được cấp phép.

### Vì sao “try/catch rồi vẫn trả byte” là lỗi?

```java
// MÃ SAI — minh họa anti-pattern, không phải chương trình độc lập
try {
    byte[] tentative = cipher.update(ciphertextChunk);
    response.write(tentative);  // Có thể phát bản rõ trước khi tag được kiểm tra
    cipher.doFinal(tagBytes);
} catch (GeneralSecurityException ex) {
    log.warn("Decryption failed");
}
```

Lỗi có thể được phát hiện **sau khi** dữ liệu nhạy cảm đã thoát khỏi ranh giới bảo vệ. Catch exception không thể thu hồi response, sự kiện hay DB write đã phát đi. Ví dụ này cũng đơn giản hóa `Cipher`/streaming nhằm làm rõ lỗi thiết kế: **không phụ thuộc vào provider có hay không có output sớm** để chứng minh hệ thống an toàn.

## 6. Java 17+ chạy được: tạo và xác minh AES-GCM envelope

Ví dụ sau dùng AES-256-GCM, nonce ngẫu nhiên 12 byte, tag 128 bit, header 22 byte, key ID demo cố định và context AAD. Nó **không trả plaintext cho caller trước khi `doFinal` xác thực thành công**. Mẫu giới hạn envelope tối đa 1.000.000 byte để từ chối dữ liệu quá lớn; đây chỉ là giới hạn demonstration, production phải chọn theo threat model và nhu cầu.

Lưu thành **`GcmEnvelopeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmEnvelopeDemo {
    private static final int MAGIC = 0x47434D31; // "GCM1"
    private static final byte VERSION = 1;
    private static final int KEY_ID = 7;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 4 + 1 + 4 + 1 + NONCE_BYTES;
    private static final int MAX_ENVELOPE_BYTES = 1_000_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] frameContext(byte[] context) {
        return ByteBuffer.allocate(4 + context.length)
                .putInt(context.length).put(context).array();
    }

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
                .putInt(MAGIC).put(VERSION).putInt(KEY_ID)
                .put((byte) NONCE_BYTES).put(nonce).array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(frameContext(context));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(header.length + ciphertextAndTag.length)
                .put(header).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws GeneralSecurityException {
        if (envelope == null || envelope.length < HEADER_BYTES + TAG_BYTES
                || envelope.length > MAX_ENVELOPE_BYTES) {
            throw new GeneralSecurityException("Invalid envelope size");
        }
        ByteBuffer input = ByteBuffer.wrap(envelope);
        int magic = input.getInt();
        byte version = input.get();
        int keyId = input.getInt();
        int nonceLength = Byte.toUnsignedInt(input.get());
        if (magic != MAGIC || version != VERSION || keyId != KEY_ID
                || nonceLength != NONCE_BYTES) {
            throw new GeneralSecurityException("Unsupported envelope");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);

        byte[] header = Arrays.copyOfRange(envelope, 0, HEADER_BYTES);
        byte[] ciphertextAndTag =
                Arrays.copyOfRange(envelope, HEADER_BYTES, envelope.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(frameContext(context));

        // Only this successful doFinal yields plaintext to the caller.
        return cipher.doFinal(ciphertextAndTag);
    }

    @FunctionalInterface
    interface Attempt {
        void run() throws GeneralSecurityException;
    }

    static boolean rejected(Attempt attempt) {
        try {
            attempt.run();
            return false;
        } catch (GeneralSecurityException ex) {
            return true;
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] message = "Hello AES-GCM".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant-A/document-7".getBytes(StandardCharsets.UTF_8);

        byte[] packed = encrypt(key, message, aad);
        String verified = new String(decrypt(key, packed, aad), StandardCharsets.UTF_8);

        byte[] badTag = packed.clone();
        badTag[badTag.length - 1] ^= 1;
        byte[] badNonce = packed.clone();
        badNonce[HEADER_BYTES - 1] ^= 1;
        KeyGenerator anotherGenerator = KeyGenerator.getInstance("AES");
        anotherGenerator.init(256);
        SecretKey wrongKey = anotherGenerator.generateKey();
        byte[] truncated = Arrays.copyOf(packed, HEADER_BYTES + TAG_BYTES - 1);

        System.out.println("Header bytes: " + HEADER_BYTES);
        System.out.println("Nonce bytes: " + NONCE_BYTES);
        System.out.println("Tag bytes: " + TAG_BYTES);
        System.out.println("Ciphertext bytes: " + (packed.length - HEADER_BYTES - TAG_BYTES));
        System.out.println("Envelope bytes: " + packed.length);
        System.out.println("Verified plaintext: " + verified);
        System.out.println("Modified tag rejected: " +
                rejected(() -> decrypt(key, badTag, aad)));
        System.out.println("Modified nonce rejected: " +
                rejected(() -> decrypt(key, badNonce, aad)));
        System.out.println("Wrong AAD rejected: " +
                rejected(() -> decrypt(key, packed,
                        "tenant-B/document-7".getBytes(StandardCharsets.UTF_8))));
        System.out.println("Wrong key rejected: " +
                rejected(() -> decrypt(wrongKey, packed, aad)));
        System.out.println("Truncated envelope rejected: " +
                rejected(() -> decrypt(key, truncated, aad)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 GcmEnvelopeDemo.java
java GcmEnvelopeDemo
```

**Stdout chính xác** (không in nonce/ciphertext ngẫu nhiên):

```text
Header bytes: 22
Nonce bytes: 12
Tag bytes: 16
Ciphertext bytes: 13
Envelope bytes: 51
Verified plaintext: Hello AES-GCM
Modified tag rejected: true
Modified nonce rejected: true
Wrong AAD rejected: true
Wrong key rejected: true
Truncated envelope rejected: true
```

### 6.1 Giải thích từng phần

**`encrypt`:**

1. Tạo nonce 12 byte mới bằng `SecureRandom` cho **mỗi phép mã hóa**. Với cùng một khóa AES-GCM, tuyệt đối không chủ động tái sử dụng nonce; xem mục 8 về yêu cầu uniqueness thực tế.
2. Tạo header chứa magic, version, key ID và nonce. Key ID ví dụ = 7; ở sản phẩm thật, ID dùng tìm secret key từ vùng quản lý khóa, không phải secret được copy vào header.
3. Khởi tạo `Cipher` với `AES/GCM/NoPadding`, key AES và `GCMParameterSpec(TAG_BITS, nonce)`.
4. `updateAAD(header)` bảo vệ những byte mô tả format; `updateAAD(frameContext(context))` bảo vệ ngữ cảnh (ví dụ tenant/document) mà không mã hóa chúng.
5. `doFinal(plaintext)` tạo `ciphertext || tag`. Ghép header và output này tạo envelope.

**`decrypt`:**

1. Từ chối envelope rỗng, quá ngắn để chứa header+tag, hoặc vượt kích thước cho phép **trước khi cấp phát hay giải mã lớn**.
2. Parse đúng byte header và kiểm allowlist profile (magic/version, ID minh họa, nonce length). Những kiểm tra ban đầu dùng input chưa xác thực; không dựa vào chúng để ra quyết định quyền nghiệp vụ.
3. Lấy đúng nonce, đúng byte header và toàn bộ phần `ciphertextAndTag` còn lại. Đưa cùng byte AAD theo cùng thứ tự.
4. Gọi **một** `cipher.doFinal(ciphertextAndTag)`, để provider kiểm tag. Method `decrypt` **chỉ trả byte[] sau khi doFinal thành công**; exception thoát ra nghĩa là không có bản rõ được công bố qua return.
5. Caller chuyển byte hợp lệ sang UTF-8 để hiển thị **sau khi xác thực**, đồng thời phải tiếp tục validate schema/phân quyền nếu dữ liệu đến từ người khác.

**Các test phản ví dụ:** đổi bit của tag, nonce trong header, context AAD, key hoặc cắt ngắn envelope đều bị từ chối. Cùng một message có thể cho ciphertext/tag khác nhau giữa các lượt vì nonce ngẫu nhiên; điều cần kiểm là decrypt đúng message và mọi thay đổi trái phép bị phát hiện.

### 6.2 Giới hạn của ví dụ

- `MAX_ENVELOPE_BYTES` là mức nhỏ cố ý để minh họa bounded input; không dùng `readAllBytes` cho dữ liệu không giới hạn.
- Ví dụ sinh key trong process và không lưu key. Trong hệ thống thật phải có key store/KMS, quyền gọi decrypt, version và rotation. Nếu chạy lại chương trình, key mới **không giải mã được envelope cũ**.
- Key ID = 7 bị cố định và chỉ phục vụ demo. Production cần resolver kiểm tra cấu hình/key ID, hạn chế quyền, logging an toàn và chịu được nhiều key version. Không xem ID do input cung cấp là đã được xác thực trước `doFinal`.
- Ví dụ chỉ xử lý buffer trong bộ nhớ; với lượng dữ liệu lớn, cần chiến lược cách ly bản rõ chưa xác thực và cơ chế chống lộ dữ liệu khi stream.
- Một tag hợp lệ cho context demo không chứng minh caller có quyền đọc đối tượng. Phải xác thực danh tính và phân quyền bằng metadata tin cậy, riêng với kiểm tra tag.
- Ví dụ không cố gắng bảo đảm việc mọi bản sao key/plaintext được xóa khỏi bộ nhớ JVM. Đặc tính này phụ thuộc runtime, provider, secret manager và thiết kế lưu trữ.

## 7. Đóng gói tag nối cuối so với tách thành trường riêng

Các thư viện và giao thức có thể biểu diễn tag theo hai cách:

**Dạng nối (ví dụ JCA AES-GCM):**

```text
header || ciphertext || tag
           \___________/
             doFinal output
```

Trong ví dụ, `Cipher.doFinal(plaintext)` trả byte chứa ciphertext và tag cuối; khi decrypt, gửi toàn bộ đoạn `ciphertext || tag` vào `doFinal`.

**Dạng trường riêng (một số SDK/API/giao thức):**

```text
envelope = { version, keyId, iv, ciphertext, tag }
```

Nếu API yêu cầu `ciphertext` và `tag` riêng, parser có thể tách 16 byte tag cuối sau khi đã kiểm độ dài; khi đưa lại cho JCA, ghép đúng thứ tự với ciphertext theo contract provider đang dùng. Không giả định mọi API AES-GCM đều trả cùng một kiểu đối tượng hoặc cách đặt tag.

### Vì sao không bỏ metadata “có thể tính lại”?

Sau khi ciphertext được lưu, key ID, IV, tag length và AAD context có thể quyết định khả năng giải mã. IV **không thể suy ra** từ ciphertext một cách tổng quát. Tag phải được giữ đầy đủ. Nếu mất thông tin ràng buộc AAD như tenant ID/schema version, tag có thể không xác minh được ở lần đọc sau dù key và ciphertext còn nguyên.

Với định dạng dài hạn, cần ghi rõ **version** và điều kiện tái tạo AAD; các trường metadata không tự động nằm trong tag nếu không được đưa đúng vào `updateAAD` hoặc plaintext được xác thực.

## 8. Nonce/IV: nguyên tắc khó bỏ qua nhất của GCM

**GCM yêu cầu IV/nonce độc nhất đối với cùng một khóa**. IV không cần bí mật, nhưng việc **tái sử dụng cùng nonce với cùng khóa** trong GCM có thể phá hủy bảo mật nghiêm trọng, ảnh hưởng cả tính bí mật và khả năng giả mạo. Đây là yêu cầu về cách triển khai, không phải điều kiện mà `GCMParameterSpec` tự bảo đảm.

- **Không** hard-code `new byte[12]` làm IV cho mọi lần encrypt.
- **Không** dùng timestamp đơn độc hoặc ID dễ trùng khi nhiều node/process cùng mã hóa với một khóa.
- **Không** tưởng `Cipher.init` của một instance khác có thể phát hiện mọi lần tái sử dụng IV đã xảy ra trên toàn hệ thống.
- **Không** dùng IV ngẫu nhiên mà bỏ qua giới hạn số message và xác suất va chạm khi một key được dùng ở quy mô lớn.
- **Có** chính sách cấp IV phù hợp với mô hình tải: 96-bit ngẫu nhiên chất lượng cao với giới hạn số lần mã hóa, hoặc counter/nonce allocation duy nhất được phối hợp đúng và chống rollback, tùy yêu cầu giao thức và khuyến nghị chuẩn GCM.
- **Có** key rotation, telemetry về giới hạn sử dụng, phân phối khóa giữa node và kế hoạch tránh reuse sau crash/restore snapshot.

Trong demo, `SecureRandom` tạo 12 byte mỗi lần. Điều này chỉ minh họa cách sinh ngẫu nhiên; với ứng dụng có tải cao, nhiều vùng/instance hoặc yêu cầu chứng minh không trùng, cần đánh giá chiến lược nonce trên **toàn bộ vòng đời của một key**.

**Đổi key nhưng dùng lại IV?** Yêu cầu uniqueness xét theo **cặp key + IV**. Tuy vậy, không vì thế mà làm key management hoặc IV allocator tùy tiện: phải biết chính xác key nào được dùng và tránh dùng cùng key khi counter bị reset.

## 9. AAD phải ràng buộc đúng metadata/ngữ cảnh nghiệp vụ

AAD là dữ liệu được xác thực nhưng không mã hóa. Với hệ đa tenant, một ciphertext hợp lệ cho tenant A không nên bị gắn sang tenant B mà vẫn được chấp nhận trong ngữ cảnh B. Ví dụ sử dụng:

- Header byte gồm version, key ID, nonce và profile.
- `tenantId`, `documentId`, mục đích sử dụng (ví dụ `document-storage:v1`) và các trường phân biệt nghiệp vụ.
- Thông tin phiên bản schema nếu cần để parse plaintext thống nhất.

Các trường này có thể được ghép bằng cấu trúc có **độ dài rõ ràng** (*length-prefix*) hoặc serialization chuẩn. Không chỉ nối chuỗi thiếu ranh giới, vì `("ab", "c")` và `("a", "bc")` đều cho `"abc"`. Mẫu `frameContext` thêm độ dài int32 cho một context; trong sản phẩm thật nếu context gồm nhiều field, cần định nghĩa đầy đủ việc frame từng field.

Điểm đặc biệt: **thứ tự AAD phải giống nhau**. Phía encrypt gọi `updateAAD(header)` rồi `updateAAD(frameContext(context))`; decrypt phải đưa cùng bytes theo cùng thứ tự. Tag có thể sai khi Unicode normalization, charset, thứ tự JSON field, số phiên bản hoặc khoảng trắng bị đổi. AAD nên dùng một canonical byte representation ổn định và có golden vectors.

Đừng truyền chuỗi tenant từ query param do người dùng tự sửa rồi dùng nó làm ngữ cảnh đáng tin. Tenant/document context phải được **liên kết với tài nguyên đã được xác thực và phân quyền** bằng metadata/identity thực tế; AAD chỉ giúp phát hiện tráo đổi so với chính context được cung cấp.

### Khi metadata thay đổi

Nếu `documentId`/tenant/metadata nằm trong AAD và bạn muốn đổi chúng, không thể tự sửa header hay context rồi mong tag vẫn hợp lệ. Cần quy trình **giải mã đã xác thực bằng context cũ -> xét quyền/quy tắc di chuyển -> mã hóa lại dưới context mới với IV mới**. Giữ hồ sơ migration và key ID/version phù hợp.

## 10. Kiểm tra format và lỗi xác thực là hai tầng khác nhau

Trước khi gọi mật mã, parser phải chịu trách nhiệm kiểm input do đối tác/người dùng kiểm soát:

1. **Giới hạn bytes tổng:** request/file tối đa, timeout và memory quota; không cấp phát dựa trên length tùy ý từ header.
2. **Đúng magic/version/algorithm:** nếu profile không hỗ trợ, từ chối. Không lấy transformation string trực tiếp từ dữ liệu không tin cậy.
3. **Đúng kích thước:** nonce 12, tag 16, envelope tối thiểu 22+16 byte trong demo; tổng các length không overflow khi cộng.
4. **Key ID hợp lệ:** đúng allowlist/namespace và quyền; lookup an toàn, không cho ID trỏ ra ngoài tenant/kho bí mật đã cấp.
5. **AAD có thể dựng chính xác:** không thả trôi context từ nguồn không tin cậy; có version và serialization.
6. **Không thêm byte tùy tiện:** xác định rõ toàn bộ envelope thuộc một thông điệp. Nếu format cho phép nhiều bản tin, phải có framing để xác định ranh giới.
7. **Tag được kiểm và không bị bỏ:** không trả content từ một chế độ giải mã “unauthenticated fallback” khi GCM thất bại.

Đây là kiểm tra **cú pháp và tài nguyên**, cần làm sớm để ngăn DoS. Nhưng magic/version/key ID/IV đã parse vẫn chưa được chứng minh là metadata thật trước khi xác thực tag. Sau `doFinal` thành công mới có bằng chứng toàn vẹn cho dữ liệu được đưa vào AAD và ciphertext.

### Xử lý exception

Tùy lỗi, Java có thể ném:

- `IllegalArgumentException` / lỗi parse nội bộ nếu đưa dữ liệu không hợp lệ vào API; cần chặn ở ranh giới và chuyển thành lỗi yêu cầu hợp lệ.
- `InvalidKeyException`, `InvalidAlgorithmParameterException` hoặc `NoSuchAlgorithmException` khi key/algorithm/parameter không phù hợp.
- `AEADBadTagException` (dẫn xuất `BadPaddingException`) khi kiểm tra tag thất bại.
- `GeneralSecurityException` là họ checked exception hữu ích cho API demo; ở production phân biệt logging nội bộ với phản hồi ngoài.

Không trả về **bản rõ một phần** trong bất kỳ nhánh lỗi nào. Không tự sửa tag, thử cắt tag, chuyển sang `AES/CBC/PKCS5Padding` hay chạy decrypt không xác thực chỉ vì muốn “cứu dữ liệu”. Trả lỗi ngoài theo chính sách nhất quán, tránh tạo oracle tiết lộ khác biệt qua mã lỗi, thời gian hoặc nội dung. Log request ID, key version và mã lỗi đã được làm sạch; không log raw secret, plaintext hay toàn bộ envelope nhạy cảm.

## 11. Lưu trữ và HTTP: không đẩy bản rõ chưa xác thực ra ngoài

### 11.1 File hoặc object nhỏ, có giới hạn rõ

Một chiến lược đơn giản:

1. Xác thực caller và quyền đọc object trước khi làm việc với key hoặc cấp phát lớn.
2. Đọc envelope vào bộ nhớ **chỉ khi kích thước nằm trong giới hạn**.
3. Parse header, gọi `decrypt` như mẫu và giữ `byte[]` kết quả trong phạm vi xử lý hạn chế.
4. Khi `doFinal` trả về thành công, xác thực thêm định dạng nội dung/authorization liên quan.
5. Sau đó mới gửi response hoặc ghi dữ liệu ra nơi đã được chỉ định.

Không dùng `ByteArrayOutputStream` chung rồi ghi từng output chưa xác thực thành response đang mở. Không truyền byte chưa xác thực cho parser tự động ghi DB/event.

### 11.2 Dữ liệu lớn và streaming AEAD

Với file hàng GB, giữ tất cả ciphertext và plaintext trong heap có thể không khả thi; nhưng giải mã streaming AEAD có một vấn đề: **tag thường chỉ biết hợp lệ ở cuối**. Không thể vừa phát bản rõ ra một hệ thống không thể thu hồi, vừa bảo đảm “chỉ sau khi xác thực” bằng cách đơn giản gọi `update` rồi `doFinal`.

Các phương án thiết kế cần đánh giá:

- **Encrypted file nhỏ/vừa:** áp giới hạn kích thước và xác thực toàn bộ trước khi trả. Đơn giản nhất để kiểm tra.
- **Vùng staging riêng, không thể truy cập:** nếu implementation cho plaintext sớm, chỉ ghi vào vùng tạm được cô lập, bảo vệ quyền truy cập, không kích hoạt side effect; **chỉ sau khi doFinal thành công** mới công bố hoặc thực hiện thao tác commit nguyên tử. Khi lỗi, xóa staging và không phát sự kiện. Cần tính đến crash, quyền truy cập temp file, backup, dọn dẹp và rò rỉ trước commit.
- **Chia dữ liệu thành record/chunk AEAD độc lập có cấu trúc:** mỗi chunk có nonce/sequence và tag riêng, xác thực từng record trước khi dùng, bảo vệ thứ tự, số lượng, EOF/truncation, metadata và một final commitment/manifest được xác thực. Không chỉ giải mã thành công từng chunk mà mặc định toàn bộ file đã đầy đủ; thiết kế protocol và nonce allocation rất quan trọng.
- **Cơ chế hoặc thư viện streaming AEAD được thiết kế và review riêng:** dùng abstraction có hợp đồng xác thực rõ ràng, thay vì tự sáng tạo format nối tag.

Đừng dựa trên `CipherInputStream` như bảo đảm mọi lỗi integrity sẽ được truyền nguyên vẹn tới caller. Tài liệu JDK cảnh báo class này có thể bắt một số exception kiểm tra integrity (ví dụ `BadPaddingException`) và không tái ném; vì vậy nó có thể **không phù hợp cho authenticated decryption nếu bắt buộc báo lỗi integrity đầy đủ**. Hãy chọn API được kiểm chứng và kiểm soát chính xác nơi tag được xác nhận.

### 11.3 Những loại side effect phải trì hoãn

- HTTP response body, download link hoặc object storage công khai.
- Event bus, queue, email/webhook hoặc lời gọi side-effect đến service khác.
- DB commit, update trạng thái đơn hàng, cấp quyền hoặc cập nhật số dư.
- Parser có thể thực hiện lệnh hoặc kích hoạt logic dựa trên plaintext.
- Log/trace, crash report và cache chứa dữ liệu nhạy cảm.

Nếu một ứng dụng cần hiển thị tiến trình tải xuống, có thể thông báo số byte ciphertext đã nhận hoặc trạng thái verification, nhưng không đánh dấu nội dung là xác thực khi chưa đọc và kiểm tra xong toàn bộ tag/commitment của giao thức.

## 12. So sánh AES-GCM với các định dạng mã hóa cũ

Một số hệ thống vẫn lưu:

```text
AES-CBC: IV || ciphertext
AES-CBC + HMAC: header || IV || ciphertext || macTag
```

**AES-CBC không có tag xác thực built-in.** Một `IV || ciphertext` không có MAC/AEAD không đáp ứng yêu cầu phát hiện thay đổi. Nếu hệ thống cũ dùng **Encrypt-then-MAC** đúng chuẩn, phải tính MAC trên cấu trúc bao gồm các trường liên quan (thường gồm version/IV/ciphertext và ngữ cảnh), **kiểm MAC trước khi decrypt CBC**, rồi mới giải mã và xử lý padding. Không trả chi tiết lỗi padding cho attacker để tránh padding-oracle. Phần triển khai này đòi hỏi key separation, thuật toán và protocol được thẩm định; không ghép HMAC tùy tiện vào CBC rồi gọi là AEAD an toàn.

Với thiết kế mới, ưu tiên AEAD chuẩn như AES-GCM khi phù hợp yêu cầu và quản lý nonce/key được bảo đảm. Không “fallback sang CBC” nếu GCM tag sai, cũng không chấp nhận một version cũ ngoài chính sách chỉ vì nó giải mã được.

## 13. Vận hành: key ID, rotation và migration

Một envelope dài hạn thường cần biết đã dùng **key nào**, nhưng **không chứa key**. Khi mã hóa, service lấy key theo chính sách đã được cấp, ghi key ID/version vào header và đưa header vào AAD. Khi giải mã, service parse ID để **định tuyến tới key được phép**, rồi tag thành công xác nhận header đã được ràng buộc đúng với bản mã.

Một số yêu cầu:

- **Giới hạn kho key và identity:** client không được chỉ định đường dẫn file key, URI tùy ý hoặc key thuộc tenant khác bằng cách thay key ID.
- **Key rotation:** key mới để encrypt; các key cũ còn được phép decrypt trong thời gian migration có điều kiện, sau đó thu hồi theo chính sách.
- **Re-encrypt:** decrypt+authenticate bằng key/IV/AAD cũ, rồi encrypt bằng key mới và **nonce mới**; không sao chép nguyên ciphertext/tag và chỉ thay key ID.
- **Metadata gắn kết:** key ID, version, tenant, document ID phải ổn định hoặc được di chuyển có chủ đích; thay AAD làm tag cũ không hợp lệ.
- **Không phụ thuộc raw key bytes nằm trong ứng dụng** nếu KMS/HSM có thể hỗ trợ cơ chế theo yêu cầu; khả năng dùng AES-GCM trực tiếp hay dạng envelope encryption phải phù hợp API của nhà cung cấp.
- **Audit:** ghi nhận key version, hành động, tài nguyên, kết quả thành công/thất bại có làm sạch; không log key, plaintext, full AAD nhạy cảm hoặc dữ liệu có thể giúp suy ra bí mật.

Thực tế AES-GCM không giải quyết quyền truy cập storage. IAM, quyền service, tenant isolation, bảo vệ backup và phát hiện truy cập bất thường vẫn cần thiết.

## 14. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Thực hành đúng |
| --- | --- | --- |
| Chỉ lưu ciphertext, bỏ IV/tag | Không thể giải mã/xác thực đáng tin cậy | Lưu envelope đầy đủ, có version và các tham số cần thiết |
| Đóng gói key bí mật cùng ciphertext | Ai có gói sẽ giải mã được | Key ở key manager/KMS/HSM, envelope chỉ chứa key ID |
| Nhầm tag 128 **bit** thành 128 **byte** | Parse sai hoặc lỗi provider | Quy định tag bits khi `GCMParameterSpec`, byte khi lưu |
| Tái sử dụng IV với cùng key | Phá vỡ bảo mật GCM nghiêm trọng | Chính sách uniqueness trên toàn vòng đời key |
| Dùng nonce làm password hoặc secret | Nhầm mục đích, key không được bảo vệ | Nonce có thể công khai, key phải bí mật |
| Không đưa header/ngữ cảnh vào AAD | Có thể tráo metadata ngoài phạm vi xác thực | Bao phủ các trường tác động tới ý nghĩa và quyền |
| Coi field parse trước decrypt là đáng tin | Attacker tự thay version/key ID/tenant | Allowlist và giới hạn trước, chỉ tin sau xác thực và kiểm quyền |
| Gọi `update` rồi stream plaintext ra HTTP | Rò plaintext trước khi tag được kiểm | Buffer/staging cô lập hoặc record AEAD với contract rõ |
| Bắt `AEADBadTagException` rồi vẫn trả kết quả partial | Chấp nhận dữ liệu bị sửa | Fail closed, không publish bất kỳ plaintext nào |
| Dùng `CipherInputStream` mà không xét xử lý lỗi integrity | Có thể che giấu lỗi tag/padding tùy hợp đồng | Dùng phương pháp xác thực hoàn chỉnh có thể kiểm chứng |
| Serialize lại JSON/AAD trước decrypt | Thay byte AAD, tag thất bại | Canonical byte format/version cố định |
| Fallback thuật toán không xác thực sau lỗi | Mở đường downgrade/oracle | Version allowlist, từ chối khi tag sai |
| Key ID không giới hạn | Có thể định tuyến decrypt ngoài phạm vi | Giới hạn key namespace, quyền IAM/KMS và tenant |
| Không giới hạn chiều dài envelope | Có thể gây cấp phát quá lớn/DoS | Check length, quota, timeout trước cấp phát |
| Cho tag hợp lệ đồng nghĩa caller được phép | Lỗ hổng phân quyền | Kiểm danh tính/ACL/tenant/action riêng |
| Tag hợp lệ được dùng lại nhiều lần không kiểm | Replay hành động | Protocol có nonce/sequence/time + idempotency nếu nghiệp vụ cần |
| Thay key ID hoặc AAD mà giữ tag cũ | Tag không còn xác thực | Giải mã xác thực trước, mã hóa lại đúng context/key |

## 15. Bộ kiểm thử cần có

Thiết kế ít nhất các trường hợp sau, dùng key và dữ liệu **kiểm thử**, không dùng secret sản xuất:

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Round trip | Encrypt rồi decrypt với cùng key/IV trong envelope và đúng AAD | Trả nguyên byte plaintext; chỉ sau verify |
| Tag bị sửa | Đổi một bit tag cuối | Giải mã thất bại, không trả plaintext |
| Ciphertext bị sửa | Đổi một bit trong phần ciphertext | Tag thất bại, không có side effect |
| Nonce bị sửa | Đổi byte nonce trong header | Bị từ chối; tag không khớp |
| AAD thay đổi | Đổi tenant/document context | Bị từ chối; không diễn giải plaintext |
| Key khác | Dùng key khác cùng thuật toán | Bị từ chối |
| Header khác | Thay version/key ID/magic | Reject theo profile hoặc tag; không fallback |
| Cắt ngắn | Thiếu header, IV, ciphertext hoặc tag | Reject cú pháp hoặc xác thực, không đọc vượt buffer |
| Dữ liệu dư | Gắn thêm byte ở cuối envelope | Không được lặng lẽ bỏ qua; test phải đảm bảo bị từ chối khi tag sai |
| Plaintext rỗng | Encrypt 0 byte | Envelope vẫn có tag, decrypt đúng mảng rỗng |
| Plaintext Unicode | Encode UTF-8 có quy tắc rõ ràng | Round trip nguyên byte; không đổi charset ngầm |
| Header/AAD canonical | Hai runtime với cùng context được frame giống nhau | Byte AAD và xác minh khớp |
| Nhiều lần encrypt | Cùng key và plaintext với nonce mới | Không dùng lại nonce; ciphertext/tag có thể khác |
| Key rotation | Version cũ còn được cho phép hoặc đã thu hồi | Hành vi theo chính sách, không thử key bừa bãi |
| Envelope quá lớn | Input vượt quota | Reject trước khi cấp phát dữ liệu lớn |
| Streaming lỗi I/O | Nhận 90% ciphertext rồi lỗi | Không commit/publish bản rõ |
| Concurrency | Nhiều request mã hóa/giải mã đồng thời | Mỗi request dùng `Cipher` riêng, không trộn trạng thái |

**Một kiểm thử bảo mật quan trọng hơn việc so tag:** đặt một sink giả (HTTP response, DB commit, event publisher) và cho decrypt nhận ciphertext/tag sai. Xác nhận **sink không hề nhận bản rõ nào**, kể cả trước exception. Đây mới kiểm tra được yêu cầu “chỉ sử dụng bản rõ sau khi xác thực thành công”.

Để kiểm tính tương thích đa ngôn ngữ, dùng **golden vectors độc lập** của algorithm/profile: biết key, IV, AAD, plaintext và expected ciphertext/tag trong môi trường test. Đừng chỉ chứng minh encrypt/decrypt của cùng một method tương thích với chính nó.

## 16. Bài thực hành

### Bài 1 — Kiểm ranh giới byte của envelope

Dùng `GcmEnvelopeDemo`, ghi lại các byte offset của magic/version/key ID/nonce/ciphertext/tag. Với plaintext `Hello AES-GCM` (13 byte UTF-8), giải thích vì sao header = 22, tag = 16, envelope = 51 byte. Thử sửa một byte ở vị trí 22 trong ciphertext và xác nhận không trả bản rõ. Thử sửa byte ở vị trí cuối và chỉ ra đó là tag.

### Bài 2 — Bảo vệ tenant và key ID

Giả sử storage có metadata `tenantId`, `documentId`, `keyVersion`. Thiết kế AAD frame có length-prefix và test tráo metadata. Chứng minh context lấy từ metadata/identity đã được tin cậy; nếu user thay tenant trong request, service không được chuyển sang key của tenant khác chỉ vì header.

### Bài 3 — Từ byte[] sang lưu trữ thực tế

Thiết kế một phương thức `readAndVerify` cho object có giới hạn 1 MiB:

1. Kiểm caller có quyền đọc object bằng metadata đáng tin.
2. Đọc envelope có quota.
3. Parse version/ID/nonce và lấy đúng key.
4. Xác thực tag toàn bộ.
5. Chỉ sau thành công mới parse JSON/binary, ghi audit và trả response.
6. Khi sai tag, sai key, lỗi I/O hoặc metadata bị tráo, không trả bản rõ và không phát event side effect.

### Bài 4 — Thiết kế cho file lớn

Giả sử cần giải mã file 4 GiB và phục vụ download. Giải thích vì sao không nên dùng `Cipher.update` rồi ghi thẳng byte vào HTTP response trước `doFinal`. Đề xuất vùng staging cô lập có atomic publish sau verify, hoặc giao thức record AEAD có sequence/tag/EOF commitment; mô tả cách xử lý crash, retry, nonce uniqueness và file bị cắt cụt.

**Tiêu chí hoàn thành:** bạn có thể khôi phục chính xác IV, version, key ID, ciphertext, tag và AAD từ envelope; biết byte nào thực sự được xác thực; có bằng chứng test rằng tag sai khiến toàn bộ bản rõ bị từ chối; đồng thời phân biệt được **mã hóa đã xác thực** với **quyền truy cập**.

## 17. Tài liệu tham khảo

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `init`, `updateAAD`, `update`, `doFinal` và AEAD.
- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): định nghĩa tag length theo bit và IV.
- [Java SE 17 — AEADBadTagException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): lỗi xác thực tag.
- [Java SE 17 — CipherInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): lưu ý về exception khi xác thực integrity.
- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): mô hình AEAD và yêu cầu IV/nonce.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): chọn chế độ, key management, nonce.
