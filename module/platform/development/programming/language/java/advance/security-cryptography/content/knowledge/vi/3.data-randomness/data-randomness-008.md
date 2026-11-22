# 3.8 Thiết kế định dạng dữ liệu có phiên bản, độ dài và mã định danh thuật toán

## 1. Vì sao dữ liệu mật mã cần một định dạng được đặc tả?

Một mảng byte sau khi mã hóa **không tự nói lên cách giải mã**. Ứng dụng cần biết dữ liệu thuộc phiên bản nào, dùng thuật toán và tham số nào, chọn khóa nào, nonce/IV nằm ở đâu, có bao nhiêu byte ciphertext và authentication tag. Nếu các thông tin này chỉ nằm trong mã nguồn hoặc được đoán từ dữ liệu, việc đọc lại dữ liệu cũ, chuyển hệ thống, luân chuyển khóa và xử lý bản ghi lỗi đều trở nên khó khăn.

Bài này thiết kế một **binary envelope** (bản ghi bao dữ liệu mật mã) phục vụ lưu trữ/truyền tải. Ba thành phần cốt lõi là:

- **Version**: quy định *cấu trúc và quy tắc diễn giải* byte của bản ghi.
- **Length**: cho phép xác định ranh giới trường một cách duy nhất, kiểm tra truncation/trailing bytes và giới hạn chi phí xử lý đầu vào.
- **Algorithm identifier**: ánh xạ một số nguyên ổn định sang một **bộ thuật toán + tham số cụ thể**, không phụ thuộc tên provider JDK.

Một định dạng tốt còn cần **magic**, **key identifier**, **nonce/IV**, quy tắc encoding/endianness, cách xác thực metadata và chính sách từ chối dữ liệu không hỗ trợ.

> Ví dụ bên dưới là **định dạng minh họa do ứng dụng tự định nghĩa**, không phải chuẩn file của Java SE, JCA hay RFC 5116. Trong dự án thực tế có thể dùng chuẩn giao thức/envelope đã được kiểm chứng (ví dụ JWE khi phù hợp) thay vì tự tạo giao thức mới. Mục tiêu của bài là hiểu cách đặc tả và triển khai cấu trúc byte không mơ hồ.

## 2. Tách format version, algorithm suite và key ID

| Trường | Trả lời câu hỏi | Không nên hiểu nhầm |
| --- | --- | --- |
| `magic` | “Đây có phải họ định dạng mà parser hiểu?” | Magic **không** phải chữ ký hay bằng chứng dữ liệu đáng tin. |
| `version` | “Các byte tiếp theo được bố trí và kiểm tra theo schema nào?” | Version của **file/protocol** không phải version Java hoặc độ mạnh mật mã. |
| `suite_id` | “Dùng thuật toán, mode, độ dài khóa, nonce và tag nào?” | Không được ánh xạ tùy ý sang chuỗi `Cipher.getInstance()` lấy trực tiếp từ file. |
| `key_id` (`kid`) | “Nên tra khóa ứng viên nào trong kho khóa tin cậy?” | ID **không phải khóa**, không bí mật, không được tự cấp quyền truy cập. |
| `nonce`/`IV` | “Giá trị khởi tạo duy nhất cho lần mã hóa bằng khóa này là gì?” | Không phải mật khẩu/salt; việc nonce có thể công khai **không** cho phép tái sử dụng với cùng khóa AES-GCM. |
| `length` | “Trường kế tiếp dài bao nhiêu byte?” | Độ dài đến từ dữ liệu ngoài và phải được kiểm tra **trước khi cấp phát**. |
| `ciphertext` + `tag` | “Dữ liệu đã mã hóa và bằng chứng toàn vẹn ở đâu?” | Chỉ được trả plaintext sau khi kiểm tra tag thành công. |

**Version và suite không thay thế nhau.** Có thể giữ `version=1` khi thêm một suite mới nếu cách ghi byte không đổi; khi thay thứ tự trường, encoding hoặc ý nghĩa trường bắt buộc, cần version/schema mới. Bảng ánh xạ `suite_id` là một phần của tài liệu giao thức: ID không được tái sử dụng để mang ý nghĩa khác.

Đối với ứng dụng lưu lâu dài, `kid` cho phép chọn khóa cũ trong thời gian đọc dữ liệu đã mã hóa sau khi hệ thống đổi khóa ghi mới. Khóa thật phải được lấy từ key store/KMS/HSM hoặc kho khóa đã xác thực; không lấy khóa từ chính bản ghi chưa đáng tin.

## 3. Đặc tả cụ thể: envelope nhị phân v1

Giả sử ứng dụng chỉ chấp nhận `suite_id = 0x01`, định nghĩa là:

- **AES-128-GCM**, JCA transformation `AES/GCM/NoPadding`.
- Khóa **16 byte** (128 bit), nonce **12 byte**, authentication tag **16 byte** (128 bit).
- Payload plaintext dài từ **0 đến 1.048.576 byte** (1 MiB).
- Ciphertext được nối với tag: `body = ciphertext || tag`, dài **plaintext_length + 16**.
- `key_id` là ASCII thuộc `[A-Za-z0-9._-]`, dài **1–32 byte**; ví dụ `key-A`.
- Tất cả độ dài trong bảng dưới là **số byte**, không phải số ký tự Unicode. Số nguyên nhiều byte ghi theo **big-endian (network byte order)**.

### 3.1 Layout chính xác

| Offset, tính từ 0 | Số byte | Trường | Quy tắc |
| --- | ---: | --- | --- |
| `0..3` | 4 | `magic` | ASCII `JENC` (`4A 45 4E 43` hex) |
| `4` | 1 | `version` | Unsigned `0x01` |
| `5` | 1 | `suite_id` | Unsigned `0x01` = AES-128-GCM/nonce-96/tag-128 |
| `6` | 1 | `kid_length` | Unsigned, phải trong `[1,32]` |
| `7` | 1 | `nonce_length` | Unsigned, phải bằng `12` trong v1/suite 1 |
| `8..11` | 4 | `body_length` | Unsigned 32-bit big-endian, phải trong `[16,1.048.592]` |
| `12..(11+k)` | `k` | `key_id` | ASCII hợp lệ, `k = kid_length` |
| `(12+k)..(23+k)` | 12 | `nonce` | 12 byte sinh cho lần mã hóa |
| `(24+k)..(23+k+c)` | `c` | `body` | Ciphertext nối tag 16 byte, `c = body_length` |

`fixed_header_length = 12`, `authenticated_header_length = 12 + k + 12 = 24 + k` và `total_record_length = authenticated_header_length + body_length`. Parser phải yêu cầu **đúng** số byte này; không âm thầm bỏ qua byte thừa.

```text
+----------+---------+----------+---------+-----------+----------------+
| MAGIC(4) | VER(1)  | SUITE(1) | KIDLEN(1)| NONCELEN(1)| BODYLEN(4 BE)  |
+----------+---------+----------+---------+-----------+----------------+
| KEY_ID (k bytes) | NONCE (12 bytes) | ENCRYPTED_BODY (c bytes: C || TAG16) |
+------------------+------------------+--------------------------------------+
<------------ Authenticated header / AES-GCM AAD ------------->
```

Ví dụ với plaintext ASCII `Hello Java` (10 byte) và `key_id = "key-A"` (5 byte): header dài `12 + 5 + 12 = 29` byte, `body` dài `10 + 16 = 26` byte, toàn bản ghi dài **55 byte**. Giá trị nonce, ciphertext và tag ngẫu nhiên theo lần mã hóa, nên không thể dự đoán toàn bộ hex output.

### 3.2 Bảng ID phải do code đáng tin kiểm soát

```text
version 1, suite 0x01:
  algorithm      = AES
  JCA transform  = AES/GCM/NoPadding
  key bits       = 128
  nonce bytes    = 12
  tag bits       = 128
  body encoding  = ciphertext || 16-byte tag
```

Nếu cần suite mới, cấp **ID mới** và viết đặc tả + bộ kiểm thử riêng. Không đặt chuỗi JCA như `"AES"`, `"AES/ECB/PKCS5Padding"` hoặc tên provider vào dữ liệu rồi gọi trực tiếp theo chuỗi đó: đầu vào có thể bị sửa để ép một thuật toán không an toàn hoặc không được triển khai. **Không fallback tự động** về thuật toán yếu hơn khi suite được yêu cầu không có.

Trong v1, `nonce_length` có mặt để minh họa trường độ dài và dễ kiểm tra cấu trúc; nó **không cho phép** thay nonce sang 8 hoặc 16 byte tùy ý. Giá trị hợp lệ vẫn cố định bằng 12 theo suite 1. Các giá trị có thể thay đổi phải được mô tả bằng giới hạn và thuật toán rõ ràng.

## 4. Metadata phải được xác thực cùng ciphertext

Đối với **AEAD** như AES-GCM, dữ liệu được chia thành:

- **Plaintext** `P`: được mã hóa và xác thực.
- **Associated Authenticated Data** (AAD) `A`: không mã hóa nhưng được tag xác thực.
- **Nonce** `N`: được gửi công khai; phải đáp ứng điều kiện duy nhất theo mỗi khóa.
- **Ciphertext + authentication tag** `C || T`: kết quả bên gửi; bên nhận chỉ chấp nhận khi kiểm tra tag thành công.

Trong envelope v1, ta đặt **nguyên byte header từ offset `0` đến hết nonce** vào AAD:

```text
A = MAGIC || VERSION || SUITE || KIDLEN || NONCELEN
    || BODYLEN || KEY_ID || NONCE

(C || T) = AES-GCM-Encrypt(key, nonce, P, A)
P       = AES-GCM-Decrypt(key, nonce, C || T, A)
```

Vì vậy nếu đối thủ sửa `version`, `suite_id`, `key_id`, `length` hoặc `nonce`, một bản ghi được chấp nhận phải vượt qua cả **kiểm tra cú pháp/allowlist** và **xác thực tag**. Một trường header không hợp lệ có thể bị parser từ chối trước khi tới bước xác thực; việc đọc trường ở giai đoạn này chỉ nhằm **định tuyến/kiểm tra**, chưa biến dữ liệu thành đáng tin.

Cần dùng **chính xác byte gốc** của header để tính AAD khi giải mã. Tránh giải mã thành đối tượng rồi tuần tự hóa lại AAD với thứ tự, case, charset hoặc dạng Unicode khác. Nếu có dữ liệu ngữ cảnh bên ngoài như tenant ID, object ID, mục đích sử dụng hay protocol domain, hai bên phải ràng buộc chúng vào AAD bằng encoding duy nhất (thường length-prefix + domain separator), để không thể chuyển một ciphertext hợp lệ sang ngữ cảnh khác.

> **AES-GCM không tự chống replay.** Kẻ tấn công có thể gửi lại *nguyên bản ghi hợp lệ* mà tag vẫn đúng. Nếu ứng dụng yêu cầu freshness/chống replay, cần thêm sequence number, record ID, timestamp theo chính sách và trạng thái theo dõi bản ghi đã dùng; đặt các trường ảnh hưởng tới quyết định vào AAD hoặc plaintext đã xác thực.

## 5. Ví dụ Java 17: tạo, đọc và xác thực envelope

Chương trình sau minh họa đầy đủ `seal()` và `open()` cho đúng **v1/suite 1**. Nó dùng `ByteBuffer` big-endian, `Byte.toUnsignedInt()`, giới hạn kích thước **trước khi cấp phát**, danh sách khóa tin cậy theo `kid`, và `Cipher.updateAAD()` **trước** `doFinal()`.

Tạo file **`EnvelopeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class EnvelopeDemo {
    private static final byte[] MAGIC = "JENC".getBytes(StandardCharsets.US_ASCII);
    private static final int VERSION = 1;
    private static final int SUITE_AES128_GCM = 1;
    private static final int FIXED_HEADER = 12;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BYTES = 16;
    private static final int MAX_KID_BYTES = 32;
    private static final int MAX_PLAIN_BYTES = 1_048_576;
    private static final int MAX_BODY_BYTES = MAX_PLAIN_BYTES + TAG_BYTES;
    private static final SecureRandom RNG = new SecureRandom();

    private static boolean validKid(String kid) {
        return kid != null && kid.matches("[A-Za-z0-9._-]{1,32}");
    }

    private static void requireAes128(SecretKey key) throws GeneralSecurityException {
        if (key == null || !"AES".equalsIgnoreCase(key.getAlgorithm())
                || key.getEncoded() == null || key.getEncoded().length != 16) {
            throw new GeneralSecurityException("AES-128 key required");
        }
    }

    public static byte[] seal(byte[] plain, SecretKey key, String kid)
            throws GeneralSecurityException {
        requireAes128(key);
        if (plain == null || plain.length > MAX_PLAIN_BYTES || !validKid(kid)) {
            throw new GeneralSecurityException("Invalid input");
        }

        byte[] kidBytes = kid.getBytes(StandardCharsets.US_ASCII);
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        int bodyLength = plain.length + TAG_BYTES;

        ByteBuffer headerBuffer = ByteBuffer
                .allocate(FIXED_HEADER + kidBytes.length + NONCE_BYTES)
                .order(ByteOrder.BIG_ENDIAN);
        headerBuffer.put(MAGIC);
        headerBuffer.put((byte) VERSION);
        headerBuffer.put((byte) SUITE_AES128_GCM);
        headerBuffer.put((byte) kidBytes.length);
        headerBuffer.put((byte) NONCE_BYTES);
        headerBuffer.putInt(bodyLength);
        headerBuffer.put(kidBytes);
        headerBuffer.put(nonce);
        byte[] header = headerBuffer.array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(header);
        byte[] body = cipher.doFinal(plain);
        if (body.length != bodyLength) {
            throw new GeneralSecurityException("Unexpected ciphertext length");
        }

        byte[] record = Arrays.copyOf(header, header.length + body.length);
        System.arraycopy(body, 0, record, header.length, body.length);
        return record;
    }

    public static byte[] open(byte[] record, Map<String, SecretKey> keyRing)
            throws GeneralSecurityException {
        if (record == null || record.length < FIXED_HEADER
                || record.length > FIXED_HEADER + MAX_KID_BYTES
                        + NONCE_BYTES + MAX_BODY_BYTES) {
            throw new GeneralSecurityException("Invalid record size");
        }

        ByteBuffer buffer = ByteBuffer.wrap(record).order(ByteOrder.BIG_ENDIAN);
        byte[] magic = new byte[MAGIC.length];
        buffer.get(magic);
        int version = Byte.toUnsignedInt(buffer.get());
        int suite = Byte.toUnsignedInt(buffer.get());
        int kidLength = Byte.toUnsignedInt(buffer.get());
        int nonceLength = Byte.toUnsignedInt(buffer.get());
        int bodyLength = buffer.getInt();

        if (!Arrays.equals(magic, MAGIC) || version != VERSION
                || suite != SUITE_AES128_GCM) {
            throw new GeneralSecurityException("Unsupported format");
        }
        if (kidLength < 1 || kidLength > MAX_KID_BYTES
                || nonceLength != NONCE_BYTES
                || bodyLength < TAG_BYTES || bodyLength > MAX_BODY_BYTES) {
            throw new GeneralSecurityException("Invalid field length");
        }

        int headerLength = FIXED_HEADER + kidLength + nonceLength;
        if (record.length != headerLength + bodyLength) {
            throw new GeneralSecurityException("Length mismatch");
        }

        byte[] kidBytes = new byte[kidLength];
        buffer.get(kidBytes);
        String kid = new String(kidBytes, StandardCharsets.US_ASCII);
        if (!validKid(kid)) {
            throw new GeneralSecurityException("Invalid key ID");
        }
        byte[] nonce = new byte[nonceLength];
        buffer.get(nonce);

        SecretKey key = keyRing.get(kid);
        if (key == null) {
            throw new GeneralSecurityException("Unknown key ID");
        }
        requireAes128(key);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(record, 0, headerLength);
        return cipher.doFinal(record, headerLength, bodyLength);
    }

    private static String check(byte[] record, Map<String, SecretKey> keyRing) {
        try {
            open(record, keyRing);
            return "ACCEPTED";
        } catch (GeneralSecurityException e) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();
        Map<String, SecretKey> keyRing = Map.of("key-A", key);
        byte[] plain = "Hello Java".getBytes(StandardCharsets.US_ASCII);
        byte[] record = seal(plain, key, "key-A");

        System.out.println("Round-trip: " + Arrays.equals(plain, open(record, keyRing)));
        System.out.println("Record bytes: " + record.length);

        byte[] nonceChanged = record.clone();
        nonceChanged[FIXED_HEADER + "key-A".length()] ^= 1;
        System.out.println("Nonce modified: " + check(nonceChanged, keyRing));

        byte[] tagChanged = record.clone();
        tagChanged[tagChanged.length - 1] ^= 1;
        System.out.println("Tag modified: " + check(tagChanged, keyRing));

        byte[] truncated = Arrays.copyOf(record, record.length - 1);
        System.out.println("Truncated: " + check(truncated, keyRing));
    }
}
```

Biên dịch/chạy từ thư mục chứa file, dùng JDK 17+:

```bash
javac --release 17 EnvelopeDemo.java
java EnvelopeDemo
```

Stdout (nội dung ổn định dù khóa và nonce sinh ngẫu nhiên):

```text
Round-trip: true
Record bytes: 55
Nonce modified: REJECTED
Tag modified: REJECTED
Truncated: REJECTED
```

**Giải thích những điểm quan trọng:**

1. `KeyGenerator` tạo khóa AES-128 minh họa. Trong production, khóa sống ngoài bản ghi; `keyRing` là ánh xạ đáng tin `key_id → key`, dùng để đọc lại dữ liệu mã hóa bằng khóa cũ. Không xuất khóa ra file envelope.
2. `SecureRandom` sinh nonce 96-bit. Ví dụ phù hợp với số bản ghi hạn chế; **không bảo đảm tránh trùng nonce tuyệt đối** ở quy mô lớn hoặc nhiều máy. Với một khóa AES-GCM, phải có chiến lược bảo đảm nonce duy nhất, giới hạn lượng bản ghi và luân chuyển khóa theo nguy cơ va chạm; hệ thống nhiều writer cần phối hợp hoặc tách khóa.
3. `GCMParameterSpec(128, nonce)` cố định tag 128-bit; JCA `Cipher.doFinal()` trả `ciphertext || tag` khi mã hóa, kiểm tra tag khi giải mã. `updateAAD(header)` được gọi trước khi xử lý ciphertext.
4. `open()` kiểm tra kích thước tổng, magic/version/suite, độ dài, charset, key ID và **đúng toàn bộ số byte** trước khi giải mã. Không suy ra phần còn lại từ `available()` hoặc tin vào chiều dài chưa giới hạn.
5. Việc thay 1 byte nonce/tag khiến bản ghi không được chấp nhận; cắt mất 1 byte khiến `record.length` không khớp độ dài khai báo. Hai tình huống đầu chủ yếu thất bại ở **authentication tag**, tình huống cuối bị **parser** từ chối trước khi gọi cipher.
6. `requireAes128()` kiểm tra `key.getEncoded()` được vì ví dụ dùng khóa xuất được (`KeyGenerator`). Khóa HSM/KMS không xuất được thường trả `null`; khi dùng chúng, phải kiểm tra loại/kích thước bằng metadata từ nhà cung cấp khóa và tích hợp provider phù hợp, **không coi `getEncoded() == null` là khóa không hợp lệ**.
7. Đây là ví dụ bản ghi nhỏ, giữ toàn bộ ciphertext trong bộ nhớ. Dữ liệu lớn cần **chunked authenticated format** riêng, với chỉ số chunk/độ dài/tổng số chunk hoặc marker kết thúc được xác thực; không được tùy tiện cắt GCM ciphertext rồi tự giải mã từng mảnh như những bản ghi độc lập.

Chương trình tự khởi tạo `Cipher` mới cho mỗi bản ghi. Việc dùng lại đối tượng `Cipher` không được phép dẫn tới dùng lại cùng cặp **key + nonce**.

## 6. Giới hạn độ dài và chuẩn hóa byte là yêu cầu an toàn

### 6.1 Parse các trường không đáng tin theo thứ tự an toàn

Luồng đọc khuyến nghị:

1. **Kiểm tra tổng kích thước input** (ít nhất 12 byte và không quá giới hạn toàn bản ghi). Không dành bộ nhớ theo độ dài do file cung cấp khi chưa kiểm tra.
2. Đọc cố định 12 byte đầu để kiểm tra `magic`, `version`, `suite_id`, ba trường độ dài; dùng **unsigned** cho trường 1 byte.
3. Kiểm tra mọi `length` với **cận trên do giao thức đặt ra**, so với số byte thực tế còn lại và kiểm tra phép cộng có khả năng overflow trước khi cấp phát.
4. Chỉ khi đã chứng minh `record.length == fixed_header + kid_length + nonce_length + body_length` mới trích `key_id`, `nonce` và body.
5. Tra khóa ứng viên từ nguồn tin cậy, kiểm tra key/suite, đặt AAD đúng byte gốc, **xác minh tag thành công** rồi mới chuyển plaintext cho logic nghiệp vụ.
6. Không sử dụng riêng trạng thái header chưa xác thực để đưa ra quyết định cấp quyền hay ghi dữ liệu lâu dài.

Ở ví dụ, `body_length` lưu trên 4 byte unsigned nhưng code Java đọc `int` có dấu. Do giới hạn hợp lệ nhỏ hơn 2 GiB, mọi giá trị có bit dấu bật sẽ bị loại bởi phép so sánh phạm vi; không cần cấp phát bộ nhớ theo số unsigned rất lớn. Nếu cần định dạng hỗ trợ hơn 2 GiB, thiết kế một **streaming parser** và phép tính kích thước `long` có kiểm soát riêng.

### 6.2 Encoding phải duy nhất

Các quy tắc cần cố định trong đặc tả, không dựa vào mặc định hệ thống:

- `ByteOrder.BIG_ENDIAN` hay một thứ tự byte được nêu rõ. Tránh `DataInputStream`/`ByteBuffer` và ngôn ngữ khác diễn giải không đồng nhất.
- `length` luôn đo **byte của encoding đã chọn**, không dùng `String.length()` thay số byte UTF-8.
- Với chuỗi tùy biến, chọn **UTF-8 chuẩn**, nêu rõ cách xử lý chuỗi lỗi encoding, normalization Unicode, quy tắc case, thứ tự trường. Ví dụ v1 giới hạn `key_id` thành ASCII để loại bỏ nhập nhằng.
- Không cho phép nhiều encoding khác nhau cùng đại diện một bản ghi ngữ nghĩa nếu định dạng dùng cho chữ ký, hashing/canonicalization; tránh field trùng, thứ tự không xác định, whitespace/case linh động.
- Không thêm byte cuối file, bỏ qua unknown field, hay tự thay `version=0` khi parse thất bại.

Khi đóng gói các trường metadata thay đổi độ dài để tính AAD hoặc chữ ký, phải có ranh giới rõ ràng, ví dụ `type || length || value` với quy tắc duy nhất. Ghép `userId || tenantId` trực tiếp có thể nhập nhằng (`"ab" + "c"` bằng `"a" + "bc"`). Nếu dùng TLV/CBOR/Protocol Buffers, phải quy định xử lý trường bắt buộc, field trùng, thứ tự/canonical encoding và khả năng tương thích cụ thể; **format version** vẫn cần định nghĩa ý nghĩa cấu trúc.

### 6.3 Kích thước ghi trong header chưa đồng nghĩa nội dung đã được xác thực

`body_length` giúp biết cần bao nhiêu byte để parse, nhưng trước khi xác minh tag, đối thủ có thể sửa nó. Vì vậy:

- **Bound trước, authenticate sau:** dùng length để từ chối ngay những bản ghi sai/hại tài nguyên, rồi bao length trong AAD để bảo vệ ý nghĩa của dữ liệu được chấp nhận.
- Tránh `new byte[untrustedLength]` trước khi kiểm tra `0 <= length <= MAX`.
- Tránh lấy `ciphertext.length` thay cho trường độ dài khi giao thức yêu cầu kiểm tra tính nhất quán; phải phát hiện file bị cắt/thêm byte.
- Với file lưu trữ lớn, phải có quy tắc chống quá tải khi giải mã, nén/decompress (nếu có), và parser streaming thay vì giữ toàn bộ trong RAM.

## 7. Nâng cấp phiên bản, đổi thuật toán và vòng đời khóa

**Trường hợp 1: thay thuật toán nhưng giữ layout.** Nếu ngày mai hệ thống hỗ trợ suite khác, cấp ID mới và chỉ đưa vào allowlist sau khi có đặc tả và test vector. `suite_id=2` chẳng hạn phải nêu rõ JCA transformation, kích thước khóa/nonce/tag, format body và kiểm thử; không được đọc `suite_id=2` rồi tự đoán thuật toán từ tên hoặc mặc định provider.

**Trường hợp 2: đổi bố cục bản ghi.** Ví dụ cần `context_id`, `created_at`, `KDF parameters` hoặc nhiều đoạn ciphertext. Thiết kế `version=2` với layout và parser riêng. Các byte version và trường metadata của mỗi phiên bản phải được xác thực trong phạm vi AAD hoặc chữ ký tương ứng. Không tự động đoán version dựa trên độ dài, không chấp nhận thiếu trường bắt buộc và không cho phép downgrade “thử lại v1 cho tới khi chạy được”.

**Trường hợp 3: xoay khóa.** Tạo khóa ghi mới, cấp `key_id` mới, giữ khóa đọc cũ trong thời gian cần đọc dữ liệu lịch sử. Nếu giải mã rồi mã hóa lại, tạo **nonce mới cho khóa mới**, xác thực bản ghi cũ trước, ghi/đổi trạng thái theo cách tránh mất dữ liệu; sau khi hoàn tất di trú có thể xóa quyền đọc khóa cũ theo chính sách. `key_id` phải gắn với **tenant/purpose/quyền sử dụng** trong kho khóa đáng tin, không cho phép định tuyến chéo tùy ý.

**Trường hợp 4: mã hóa từ mật khẩu thay vì khóa đã tạo.** Một format khác có thể cần **KDF ID, salt, iteration/work factor và thông số KDF** để tái tạo khóa. Những trường này phải có encoding, độ dài, giới hạn chi phí và khả năng xác thực rõ ràng. **Salt của KDF** và **nonce của AEAD** là hai giá trị khác mục đích; không lấy một giá trị thay bừa cho giá trị kia. Không đưa mật khẩu, raw key hay thông tin bí mật nhạy cảm vào header.

**Chống downgrade:** Cho phép đọc v1 vì dữ liệu lịch sử là một **chính sách tương thích**; chấp nhận một suite lỗi thời trong giao thức mới là quyết định bảo mật khác. Viết mới bằng phiên bản/suite đã phê duyệt, chỉ cho phép legacy trong phạm vi cần thiết, ghi nhận thời điểm hết hỗ trợ.

## 8. Test bắt buộc đối với bộ đọc/ghi

| Trường hợp | Kết quả kỳ vọng | Vì sao |
| --- | --- | --- |
| Round-trip plaintext rỗng, ngắn và tối đa 1 MiB | Dữ liệu sau giải mã khớp từng byte | Biên độ body hợp lệ từ 16 byte tag đến giới hạn đã công bố |
| Sửa một byte `nonce`, `key_id` hoặc body/tag | Bị từ chối | Header và ciphertext/tag không thể bị tráo đổi âm thầm |
| Sửa `magic`, `version` hoặc `suite_id` sang giá trị không hỗ trợ | Bị từ chối ngay | Không thử fallback ngầm |
| `kid_length=0`, `kid_length=255`, `nonce_length != 12` | Bị từ chối trước cấp phát | Bounds và invariant của suite |
| `body_length` âm khi đọc bằng `int`, lớn quá mức hoặc nhỏ hơn tag | Bị từ chối trước cấp phát | Không bị integer overflow/memory DoS |
| File thiếu 1 byte hoặc có 1 byte thừa | Bị từ chối | Ranh giới bản ghi chính xác |
| `key_id` lạ hoặc key sai | Không giải mã được | Chỉ đọc khóa thuộc keyring tin cậy |
| Key đúng nhưng context bên ngoài sai (nếu format có context binding) | Authentication thất bại | Ngăn chuyển bản ghi giữa ngữ cảnh |
| Nhiều bản ghi cùng key/nonce | Phải ngăn tại phía ghi và kiểm tra chiến lược nonce | AES-GCM yêu cầu nonce duy nhất với mỗi khóa |
| V2/schema mới hoặc suite mới | Chỉ parser đúng phiên bản hỗ trợ mới chấp nhận | Nâng cấp có kiểm soát và tương thích rõ ràng |

Ngoài unit test, nên có **test vector** chứa header hex, plaintext, key thử nghiệm, nonce cố định **chỉ trong test**, ciphertext/tag kỳ vọng; kiểm thử giữa Java và ngôn ngữ khác nếu giao thức liên nền tảng. Không dùng key/nonce cố định từ test vector để mã hóa thực tế.

## 9. Những lỗi thiết kế thường gặp

1. **Không có version:** dữ liệu cũ được giải mã bằng format hoặc thuật toán mặc định mới và không thể khôi phục khi hệ thống nâng cấp.
2. **Chỉ ghi tên `"AES"` hoặc `"RSA"`:** thiếu mode, padding, kích thước khóa, tag/nonce; provider có thể có mặc định khác. Mã hóa có xác thực nên chọn transformation rõ ràng như `AES/GCM/NoPadding`.
3. **Nhận chuỗi thuật toán từ file và gọi thẳng JCA:** cho dữ liệu chưa xác thực quyết định thuật toán. Dùng **numeric suite ID → allowlist cố định**.
4. **Độ dài không giới hạn hoặc đo sai đơn vị:** parser có thể cấp phát quá mức, đọc lệch khung hoặc chấp nhận trường bị cắt. Dùng byte lengths, unsigned parsing, checked arithmetic, exact-consumption.
5. **Metadata không nằm trong AAD/chữ ký:** có thể tráo `key_id`, version, context hoặc tham số mà không được bảo vệ đầy đủ; phải ràng buộc đúng byte.
6. **Tái dùng nonce AES-GCM với cùng khóa:** làm suy yếu nghiêm trọng bảo mật và tính toàn vẹn. Không sinh bằng `Random`; `SecureRandom` cũng cần giới hạn số bản ghi/chiến lược tránh trùng thích hợp.
7. **Trả plaintext từng phần trước khi xác minh tag:** dữ liệu có thể bị lợi dụng dù cuối cùng tag sai. Chỉ công bố kết quả sau khi `doFinal` xác thực thành công.
8. **Coi Base64, magic, CRC hoặc checksum là bảo mật:** chúng hỗ trợ vận chuyển/phát hiện lỗi ngẫu nhiên, **không thay thế authentication tag/chữ ký**.
9. **Dùng Java object serialization làm wire format tùy biến:** phụ thuộc class/JDK, tăng rủi ro giải tuần tự hóa và không có schema mật mã rõ ràng. Dùng định dạng nhị phân có phiên bản và kiểm tra biên.
10. **Nhầm xác thực với chống replay hay xác thực danh tính người gửi:** AES-GCM chứng minh bản ghi hợp lệ với người giữ khóa; cần cơ chế khác để chống gửi lại hoặc chứng minh một bên đã ký.

## 10. Checklist trước khi lưu trữ hoặc công bố format

- [ ] Có đặc tả byte chính thức: magic, version, suite registry, thứ tự trường, endianness, charset, độ dài/giới hạn và quy tắc lỗi.
- [ ] Mỗi suite quy định đầy đủ algorithm/mode/padding, loại và kích thước khóa, nonce, tag, format ciphertext.
- [ ] Toàn bộ header quan trọng được đưa vào AAD (hoặc chữ ký); context/purpose cần ràng buộc cũng được xác thực.
- [ ] Parser reject unknown version/suite, malformed/truncated/trailing bytes, duplicate fields và mọi length ngoài giới hạn **trước khi cấp phát lớn**.
- [ ] Không dùng bản ghi làm nguồn tin cậy cho khóa hoặc quyền; key ID chỉ tra khóa ứng viên trong registry đáng tin.
- [ ] Chiến lược nonce uniqueness, key rotation, compatibility và chính sách cấm downgrade đã được thiết kế rõ.
- [ ] Có test vector, test biên, kiểm thử tamper, test nhiều runtime/provider và chính sách xử lý replay nếu cần.
- [ ] Quy trình ghi dữ liệu đủ tin cậy khi restart/crash; với chunked format, thứ tự, số chunk và điểm kết thúc đều được bảo vệ.

## Tài liệu gốc

- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html): biểu diễn AEAD, AAD không mơ hồ, nonce uniqueness; định nghĩa AES-128-GCM với nonce 12 byte và tag 16 byte.
- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): yêu cầu về GCM, IV/nonce và xác thực.
- [Java SE 17 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation, `updateAAD`, `doFinal` và authentication tag.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` tính bằng bit, IV/nonce truyền cho GCM.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): quy tắc đọc/ghi byte và thứ tự byte.

**Ghi nhớ:** Một format mật mã an toàn phải vừa **tự mô tả đủ để đọc**, vừa **không tin dữ liệu tự mô tả cho tới khi đã kiểm tra ranh giới và xác thực**. Version, length và algorithm ID là nền móng cho khả năng tiến hóa, còn AAD/tag, nonce và kiểm tra parser là nền móng cho an toàn.
