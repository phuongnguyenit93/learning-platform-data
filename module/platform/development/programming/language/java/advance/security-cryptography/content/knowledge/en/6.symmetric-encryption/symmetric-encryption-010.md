# 6.10 Xử lý AEADBadTagException, BadPaddingException và bản mã bị cắt

## Mục tiêu

Sau bài học, bạn có thể xác định chính xác ý nghĩa của `AEADBadTagException` và `BadPaddingException` trong Java Cryptography Architecture (JCA/JCE), phân biệt **bản mã bị cắt ngắn** với **xác thực AEAD thất bại**, thiết kế cấu trúc bản mã (envelope) có đủ thông tin để kiểm tra độ dài, xây dựng quy trình giải mã AES-GCM không phát tán plaintext khi tag chưa được xác minh, và xử lý lỗi đủ an toàn để không tạo thêm thông tin cho đối thủ.

Bài thuộc chủ đề **6. Mã hóa đối xứng**. Trọng tâm là `AES/GCM/NoPadding`, nhưng cần biết `BadPaddingException` cũng xuất hiện ở các chế độ cũ như `AES/CBC/PKCS5Padding`. Mục tiêu là **chẩn đoán đúng, từ chối an toàn và giữ giao thức nhất quán**; ngoại lệ không phải bằng chứng duy nhất để xác định liệu dữ liệu bị sửa, truyền thiếu, khóa sai hay tham số giải mã không khớp.

## 1. Điều gì được xác thực trong AES-GCM?

AES-GCM là một chế độ **AEAD (Authenticated Encryption with Associated Data)**: nó bảo mật nội dung (confidentiality) đồng thời kiểm tra tính toàn vẹn và tính xác thực của bản mã cùng dữ liệu liên kết (integrity/authenticity), với điều kiện khóa, nonce và cách sử dụng đúng.

Một lần mã hóa AEAD sử dụng:

- **Khóa bí mật** `K`: cùng khóa phù hợp ở bên mã hóa và giải mã.
- **Nonce/IV** `N`: không cần giữ bí mật, nhưng **phải không lặp lại với cùng khóa AES-GCM**. Thực tế thường chọn nonce ngẫu nhiên 12 byte (96 bit) bằng nguồn ngẫu nhiên mật mã.
- **Plaintext** `P`: dữ liệu cần bảo mật.
- **AAD**: dữ liệu không mã hóa nhưng vẫn được đưa vào kiểm tra tính xác thực, ví dụ phiên bản envelope hoặc ngữ cảnh request.
- **Ciphertext** `C` và **authentication tag** `T`: đầu ra mà bên nhận phải kiểm tra đầy đủ trước khi tin tưởng plaintext.

Trong Java, thao tác phổ biến là:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

Đây là **đoạn minh họa bên trong phương thức**, không phải chương trình độc lập; cần import `javax.crypto.Cipher`, `javax.crypto.spec.GCMParameterSpec`, cùng biến `key`, `nonce`, `aad`, `ciphertextAndTag` đúng định dạng. Với `GCMParameterSpec(128, nonce)`, tag dài **128 bit = 16 byte**. JCE thường nhận ciphertext **và tag nối tiếp nhau** trong đầu vào giải mã: `C || T`. Một số giao thức lưu tag ở trường riêng; khi dùng `Cipher.doFinal` cần ghép lại đúng thứ tự mà provider yêu cầu.

**“NoPadding” không có nghĩa là không có authentication tag.** GCM không dùng PKCS#5/#7 padding của CBC, nhưng vẫn bắt buộc xử lý tag xác thực. Thiếu hoặc sai tag khiến bên nhận không được chấp nhận plaintext.

### Envelope và overhead tối thiểu

Để truyền nhận an toàn, hai phía phải thống nhất format. Ví dụ minh họa trong bài:

```text
+------------+----------------+----------------------+-------------------+
| version    | nonce          | ciphertext           | GCM tag           |
| 1 byte     | 12 byte        | 0..n byte            | 16 byte           |
+------------+----------------+----------------------+-------------------+
```

Overhead tối thiểu là **1 + 12 + 16 = 29 byte**; kể cả plaintext rỗng, tag 16 byte vẫn phải có. Các byte đầu của envelope không tự được mã hóa, nhưng **version phải được đưa vào AAD** để bảo vệ khỏi sửa đổi mà vẫn giữ tính linh hoạt của format. Ví dụ cũng đưa một `context` do hai phía thống nhất vào AAD, chẳng hạn “POST /orders”.

Giao thức thực có thể cần thêm key ID, độ dài, thuật toán, tham số phiên bản, loại nội dung. Chúng phải có encoding đơn nghĩa, giới hạn kích thước, được liên kết mật mã phù hợp và được kiểm tra trước khi phân tích dữ liệu đầu vào.

## 2. Quan hệ giữa các ngoại lệ Java

Sơ đồ kế thừa quan trọng:

```text
Exception
  └─ GeneralSecurityException
       ├─ BadPaddingException
       │    └─ AEADBadTagException
       ├─ IllegalBlockSizeException
       ├─ InvalidKeyException
       ├─ InvalidAlgorithmParameterException
       └─ NoSuchAlgorithmException
```

`javax.crypto.AEADBadTagException` **kế thừa** `javax.crypto.BadPaddingException`. Do đó:

- `catch (BadPaddingException e)` cũng bắt được `AEADBadTagException`.
- Nếu muốn xử lý chi tiết ở tầng bên trong, phải bắt **`AEADBadTagException` trước `BadPaddingException`**; đảo ngược thứ tự sẽ làm nhánh cụ thể không thể truy cập và Java báo lỗi biên dịch.
- `IllegalBlockSizeException` là một nhánh **khác** của `GeneralSecurityException`, không kế thừa `BadPaddingException`.
- Các lỗi kiểm tra format do ứng dụng tự ném, ví dụ `IllegalArgumentException`, không thuộc các loại checked exception trên; nên đặt mã phân loại lỗi rõ ràng tại ranh giới giao thức.

| Ngoại lệ | Thường xuất hiện ở đâu | Điều có thể kết luận |
| --- | --- | --- |
| `AEADBadTagException` | `Cipher.doFinal` khi giải mã AEAD và tag không xác minh thành công | **Không xác thực được** tổ hợp key, nonce, AAD, ciphertext và tag đã cung cấp |
| `BadPaddingException` (loại thường) | `doFinal` ở chế độ có padding như CBC/PKCS5Padding; một số provider có thể dùng lỗi tổng quát khi xử lý AEAD | Padding cuối không hợp lệ hoặc thao tác giải mã thất bại theo provider; không đủ để chỉ ra nguyên nhân |
| `IllegalBlockSizeException` | `doFinal` với dữ liệu không phù hợp độ dài block/chế độ | Input không phù hợp cách xử lý block; có thể do truyền thiếu, sai mode hoặc framing |
| `InvalidKeyException` | `Cipher.init` | Key sai loại, không phù hợp hoặc bị provider/policy từ chối |
| `InvalidAlgorithmParameterException` | `Cipher.init` | IV/nonce/parameters không hợp lệ hoặc không được provider hỗ trợ |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | `Cipher.getInstance` | Transformation không được cung cấp bởi provider đã chọn |

**Không kết luận từ tên ngoại lệ rằng có một “cuộc tấn công”.** Với GCM, `AEADBadTagException` có thể do một byte bị hỏng vô ý, sai khóa, nonce không đúng, AAD khác, tag thiếu, cắt gói hoặc cố ý giả mạo. Các trường hợp đó có cùng biểu hiện mật mã: xác thực thất bại.

Cụ thể, `AEADBadTagException` là ngoại lệ chính xác hơn cho thất bại xác thực AEAD trên các provider tuân theo API; nhưng một số provider hoặc cách bao bọc API có thể trả lỗi ít đặc hiệu hơn. Ứng dụng cần xử lý `GeneralSecurityException`/lỗi định dạng phù hợp ở ranh giới, thay vì phụ thuộc vào chuỗi message hoặc tên một provider.

## 3. Bản mã bị cắt (truncation) có những dạng nào?

“Bản mã bị cắt” có thể xảy ra ở **tầng vận chuyển**, **tầng format envelope** hoặc ngay **phần ciphertext/tag**:

1. **Thiếu một phần header:** không đủ byte để đọc version hoặc nonce; phải chặn trước khi khởi tạo `Cipher`. Ví dụ envelope chỉ dài 10 byte, không thể có đủ nonce 12 byte và tag 16 byte.
2. **Có đủ header nhưng không đủ tag:** với layout 1 + 12 + C + 16 byte, đầu vào ít hơn 29 byte chắc chắn không hợp lệ. Từ chối bằng kiểm tra độ dài/phạm vi trước khi gọi `doFinal`.
3. **Mất một vài byte phần cuối nhưng vẫn dài ít nhất 29 byte:** ứng dụng có thể không nhận ra ngay từ tổng độ dài nếu không biết độ dài message mong đợi. GCM sẽ đọc 16 byte cuối hiện tại làm tag; tag không còn đúng nên **xác thực thất bại**, thường ném `AEADBadTagException`.
4. **Mất byte giữa ciphertext hoặc thay đổi thứ tự:** phép xác thực tag không khớp, thường cũng báo lỗi AEAD.
5. **Đọc sai ranh giới nhiều bản tin:** nối hai record hoặc cắt giữa record do framing sai, thường cho lỗi xác thực tương tự. Không coi việc tạo `Cipher` thành công là bằng chứng record đã đầy đủ.

Vì lỗi có thể mang cùng biểu hiện, **không thể phân biệt chắc chắn “bị cắt”, “bị sửa”, “AAD sai” và “khóa sai” chỉ dựa trên `AEADBadTagException`**. Muốn biết record thiếu byte ở mức giao thức, cần khung dữ liệu/độ dài rõ ràng (ví dụ length prefix đã giới hạn, Content-Length được kiểm soát, record length trong protocol), đọc đủ record, và so với số byte thực nhận.

### Khi biết độ dài trước

Nếu giao thức có trường `recordLength` từ một nguồn đáng tin/được kiểm soát, hãy kiểm tra:

```text
receivedBytes == expectedRecordLength
expectedRecordLength >= minimumEnvelopeLength
expectedRecordLength <= maximumAllowedRecordLength
```

Trường độ dài là dữ liệu **chưa được xác thực** nếu nằm ngoài tag; phải ràng buộc giới hạn và liên kết nó vào metadata xác thực nếu cần. Không cấp phát mảng theo độ dài do client cung cấp mà chưa giới hạn. Nếu nhận ít hơn số byte cần thiết, đó là **truncated record** ở tầng vận chuyển; dù vậy, thông điệp trả cho client không nên tiết lộ thêm chi tiết có ích cho việc khai thác.

### Khi không biết độ dài trước

Đọc hết record theo quy ước EOF/frame của protocol trước khi giải mã. `doFinal` xác nhận tag chỉ trên **chính những byte đã cung cấp**. Nếu đầu vào ngắn hơn minimum envelope, có thể phân loại malformed/truncated ngay; nếu dài hơn minimum mà thiếu một phần, lỗi xác thực là kết luận đúng, còn nguyên nhân vật lý cần chẩn đoán qua log/transport metrics.

## 4. Mẫu Java 17 chạy được: kiểm tra bản mã GCM bị sửa hoặc cắt

Chương trình dưới đây cố ý tạo một khóa AES ngẫu nhiên và một nonce ngẫu nhiên **cho từng lần mã hóa**, ghi bản mã dưới format `[version:1][nonce:12][ciphertext][tag:16]`. `version` cùng `context` là AAD. Phần xử lý lỗi trả các mã kết quả **chỉ để học cách phân loại bên trong**; ở API public, hãy gom các lỗi không hợp lệ về một phản hồi xác thực thất bại thống nhất.

Tạo đúng tệp **`AeadFailuresDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadFailuresDemo {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 1 + NONCE_BYTES;
    private static final byte VERSION = 1;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] { VERSION });
        cipher.updateAAD(context);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        byte[] envelope = new byte[HEADER_BYTES + ciphertextAndTag.length];
        envelope[0] = VERSION;
        System.arraycopy(nonce, 0, envelope, 1, NONCE_BYTES);
        System.arraycopy(ciphertextAndTag, 0, envelope, HEADER_BYTES,
                ciphertextAndTag.length);
        return envelope;
    }

    private static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws GeneralSecurityException {
        if (envelope == null || envelope.length < HEADER_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Invalid envelope length");
        }
        if (envelope[0] != VERSION) {
            throw new IllegalArgumentException("Unsupported version");
        }

        byte[] nonce = Arrays.copyOfRange(envelope, 1, HEADER_BYTES);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] { envelope[0] });
        cipher.updateAAD(context);
        return cipher.doFinal(envelope, HEADER_BYTES,
                envelope.length - HEADER_BYTES);
    }

    private static String status(SecretKey key, byte[] envelope, byte[] context) {
        try {
            decrypt(key, envelope, context);
            return "ACCEPT";
        } catch (AEADBadTagException e) {
            return "REJECT_AUTH";
        } catch (BadPaddingException | IllegalBlockSizeException e) {
            return "REJECT_CRYPTO";
        } catch (IllegalArgumentException e) {
            return "REJECT_FORMAT";
        } catch (GeneralSecurityException e) {
            return "REJECT_CRYPTO_SETUP";
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] context = "POST /orders".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "pay=100".getBytes(StandardCharsets.UTF_8);
        byte[] envelope = encrypt(key, plaintext, context);

        byte[] changedTag = envelope.clone();
        changedTag[changedTag.length - 1] ^= 1;

        byte[] changedNonce = envelope.clone();
        changedNonce[1] ^= 1;

        byte[] truncated = Arrays.copyOf(envelope, envelope.length - 1);
        byte[] tooShort = Arrays.copyOf(envelope,
                HEADER_BYTES + TAG_BYTES - 1);

        byte[] changedVersion = envelope.clone();
        changedVersion[0] = 2;

        System.out.println("valid: " + status(key, envelope, context));
        System.out.println("tag changed: " + status(key, changedTag, context));
        System.out.println("nonce changed: " + status(key, changedNonce, context));
        System.out.println("tail truncated: " + status(key, truncated, context));
        System.out.println("too short: " + status(key, tooShort, context));
        System.out.println("AAD changed: " + status(key, envelope,
                "POST /other".getBytes(StandardCharsets.UTF_8)));
        System.out.println("version changed: "
                + status(key, changedVersion, context));
        System.out.println("round-trip: "
                + Arrays.equals(plaintext, decrypt(key, envelope, context)));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AeadFailuresDemo.java
java AeadFailuresDemo
```

**Stdout trên JDK thử nghiệm với provider AES-GCM hỗ trợ tag 128 bit** (đã biên dịch với chế độ Java 17):

```text
valid: ACCEPT
tag changed: REJECT_AUTH
nonce changed: REJECT_AUTH
tail truncated: REJECT_AUTH
too short: REJECT_FORMAT
AAD changed: REJECT_AUTH
version changed: REJECT_FORMAT
round-trip: true
```

**Diễn giải cụ thể:**

- `valid: ACCEPT` và `round-trip: true` cho thấy cùng key, nonce, AAD và ciphertext/tag cho plaintext ban đầu.
- Thay một bit **tag**, một bit **nonce**, hoặc đổi **AAD** làm xác thực GCM không thành công; trên provider thử nghiệm, Java ném `AEADBadTagException` và hàm trả `REJECT_AUTH`.
- Cắt một byte cuối của ciphertext+tag nhưng vẫn đủ 29 byte cho envelope khiến tag diễn giải ở cuối không hợp lệ; `REJECT_AUTH` là **thất bại xác thực**, chưa thể chỉ ra bên nào làm mất byte.
- `too short` chỉ còn 28 byte: thiếu tối thiểu một byte để có đủ version/nonce/tag, nên mã ứng dụng từ chối **trước khi gọi provider**.
- Đổi version thành `2` được chặn bởi kiểm tra schema. Khi version hợp lệ nhưng bị thay theo cách không bị chặn ở parser, ràng buộc version vào AAD giúp đảm bảo thay đổi sẽ làm tag không khớp.
- Dù nonce được sinh ngẫu nhiên, ciphertext thực tế khác nhau giữa các lần chạy, các **nhóm kết quả** trên ổn định trong cấu hình đã kiểm thử. Một provider khác có thể dùng lớp ngoại lệ tổng quát hơn cho một số lỗi; chức năng bắt lỗi không phụ thuộc message cụ thể.

**Chú ý về thiết kế demo:** khóa do `KeyGenerator` tạo là khóa thử nghiệm trong bộ nhớ; format và `context` chỉ là ví dụ. Ứng dụng thật phải xác định encoding của context và giới hạn message, lưu khóa trong cơ chế phù hợp, dùng nonce **duy nhất cho từng lần mã hóa dưới cùng khóa**, và phân phối nonce/tag cùng ciphertext. Không dùng ciphertext đã chỉnh sửa để “phục hồi” dữ liệu hoặc tự đoán lại nonce.

## 5. Viết `catch` đúng thứ tự và ánh xạ lỗi ở boundary

Khi muốn ghi chẩn đoán nội bộ cho engine `Cipher`, mẫu chung có thể là:

```java
try {
    byte[] plaintext = cipher.doFinal(ciphertextAndTag);
    // Chỉ xử lý plaintext sau khi doFinal thành công.
} catch (AEADBadTagException e) {
    // GCM/AEAD: tag không được xác thực.
} catch (BadPaddingException e) {
    // Lỗi padding hoặc lỗi giải mã tổng quát theo provider.
} catch (IllegalBlockSizeException e) {
    // Input không phù hợp kích thước block/mode.
}
```

Đây chỉ là **khối minh họa**: `cipher` đã được khởi tạo trước với khóa, IV/AAD đúng; `ciphertextAndTag` là `byte[]`; các loại ngoại lệ cần import từ `javax.crypto`. Nếu sửa thứ tự bằng cách bắt `BadPaddingException` trước `AEADBadTagException`, nhánh cụ thể sẽ không thể bắt được và mã không biên dịch.

### Phản hồi bên ngoài nên thống nhất

Ví dụ một API nhận bản mã do người dùng gửi, hệ thống bên trong có thể phân loại:

| Mã nội bộ | Trường hợp | Phản hồi bên ngoài |
| --- | --- | --- |
| `MALFORMED_ENVELOPE` | Thiếu header/tag, sai version, trường kích thước bất thường | `Invalid encrypted payload` |
| `AUTHENTICATION_FAILED` | GCM xác thực tag không thành công | `Invalid encrypted payload` |
| `DECRYPTION_FAILED` | Provider báo lỗi padding/block khi giải mã | `Invalid encrypted payload` |
| `KEY_OR_PROVIDER_CONFIG_ERROR` | Key/provider cấu hình sai hoặc không khả dụng | Lỗi dịch vụ chung, không tiết lộ khóa/thuật toán nội bộ |

Mức HTTP status cụ thể phụ thuộc hợp đồng API; quan trọng là **không xây một oracle phân biệt chi tiết** như “tag sai ở byte thứ 7”, “khóa đúng nhưng padding sai”, “nonce đúng” hoặc trả dữ liệu plaintext chưa xác thực. Ứng dụng có thể log mã lỗi, số byte nhận, format version và correlation ID trong kênh vận hành được bảo vệ, nhưng **không log khóa bí mật, plaintext, token, toàn bộ ciphertext/tag nhạy cảm**.

Với lỗi do triển khai hoặc provider bị thiếu, nên giám sát và xử lý đúng cấu hình. **Không fallback tự động** từ AES-GCM sang AES-CBC, đổi tag length, bỏ AAD hoặc thử hàng loạt key/nonce tùy tiện nhằm “giải được bằng mọi giá”.

## 6. `BadPaddingException` với AES-CBC/PKCS5Padding khác gì GCM?

Một hệ thống cũ có thể dùng:

```java
Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
```

Đoạn trên chỉ tạo engine, **chưa mã hóa/giải mã và chưa chỉ định khóa/IV**. Trong CBC với padding:

- Plaintext được đệm để có độ dài theo block AES (16 byte).
- Bên nhận phải kiểm tra và bỏ padding sau khi giải mã block cuối.
- Nếu byte cuối sau giải mã **không tạo padding hợp lệ**, provider thường ném `BadPaddingException`.
- Nếu byte input không phù hợp số block, provider có thể ném `IllegalBlockSizeException`; tên ngoại lệ chính xác phụ thuộc provider và thao tác.
- Ciphertext bị sửa, sai key hoặc record không đầy đủ **có thể** gây ra các lỗi trên; nhưng cũng có trường hợp CBC trả plaintext sai mà **không ném ngoại lệ** vì padding tình cờ hợp lệ.

Vì vậy, **CBC + padding không cung cấp tính xác thực chỉ bằng việc kiểm tra padding**. Việc trả phản hồi khác nhau giữa “padding đúng/sai” có thể tạo *padding oracle* nguy hiểm trong các hệ thống mã hóa không có xác thực. Hệ thống mới ưu tiên AEAD như AES-GCM; hệ thống legacy cần xem lại giao thức xác thực và có kế hoạch di chuyển chặt chẽ. Không “sửa” lỗi padding bằng cách bỏ `PKCS5Padding`, tự đệm zero, cắt block, loại bỏ byte cuối hoặc trả dữ liệu đã giải mã dở.

### Vì sao GCM vẫn có `BadPaddingException`?

Do mô hình kế thừa API Java, `AEADBadTagException extends BadPaddingException`. Điều này là **lý do về phân loại ngoại lệ**, không có nghĩa GCM sử dụng PKCS#5 padding. Nếu một middleware chỉ bắt `BadPaddingException`, nó có thể đang gộp cả lỗi tag xác thực GCM lẫn lỗi padding của CBC. Khi phân tích log, phải biết **transformation** và **provider** đã sử dụng.

## 7. Plaintext trước khi xác thực: lỗi nghiêm trọng khi streaming

Với AEAD, plaintext chỉ đáng tin khi **authentication tag đã được xác minh thành công**. Một số chế độ/provider có thể phát sinh các byte plaintext tạm thời từ `Cipher.update(...)` trước `doFinal(...)`, trong khi tag chưa được kiểm tra. Đó là **dữ liệu chưa xác thực**.

Quy tắc an toàn:

1. **Không** gửi plaintext tạm thời đến client, parser nghiệp vụ, queue, database hay hệ thống thực thi trước khi xác thực hoàn tất.
2. Với bản tin nhỏ, dùng `Cipher.doFinal(...)` trên toàn bộ ciphertext/tag và chỉ trả dữ liệu khi lời gọi thành công.
3. Với bản tin lớn, nếu API/provider trả byte trước khi xác thực, giữ chúng trong vùng cách ly (bộ nhớ hoặc file tạm có kiểm soát), chỉ publish/commit **sau khi `doFinal` thành công**; hủy sạch dữ liệu chưa tin cậy khi xác thực thất bại.
4. Không dùng kết quả một phần để cập nhật trạng thái, phát hành thanh toán, giải nén dữ liệu theo cách gây tác dụng phụ hoặc suy luận “đã giải mã được phần đầu nên key đúng”.

**Lưu ý `CipherInputStream`:** tài liệu Java mô tả rằng lớp này có thể bắt các ngoại lệ kiểm tra toàn vẹn như `BadPaddingException` mà không ném lại đầy đủ cho client; do đó nó **có thể không phù hợp cho giải mã có xác thực** như GCM. Khi việc nhận biết tag thất bại là bắt buộc, sử dụng `Cipher` trực tiếp và quản lý output chưa xác thực theo chính sách rõ ràng.

Việc giải mã một file lớn thành file đích có thể gây mất an toàn nếu ghi trực tiếp rồi người khác đọc ngay. Ưu tiên file tạm không được truy cập bởi ứng dụng khác, giải mã/kiểm tra đầy đủ, sau đó mới **đổi tên/commit atomically nếu filesystem hỗ trợ**; khi lỗi, xóa/hủy file tạm theo chính sách.

## 8. Thiết kế framing để xử lý bản mã bị cắt đáng tin cậy

### 8.1 Xác định một record trước khi giải mã

Cần định nghĩa **một record** là bao nhiêu byte, giới hạn đầu vào và số lượng record. Chẳng hạn:

```text
recordLength (4 bytes, unsigned, network byte order)
version (1 byte)
nonce (12 bytes)
ciphertext (variable)
tag (16 bytes)
```

Độ dài này chỉ là ví dụ framing, **không phải** định dạng từ chương trình `AeadFailuresDemo` (demo nhận sẵn đúng một envelope). Ứng dụng đọc đúng `recordLength` byte trước khi giải mã, từ chối nếu EOF đến sớm hoặc vượt giới hạn kích thước. Nếu một trường độ dài được dùng để cấp phát buffer, phải xác nhận giá trị nằm trong giới hạn và tránh tràn số khi cộng header/tag.

Khi metadata quan trọng nằm ngoài ciphertext, cần ràng buộc vào AAD và định nghĩa rõ thứ tự, độ dài từng trường, phiên bản schema. Nếu protocol gửi record length, header version, key ID và thuật toán, tất cả phải được kiểm tra theo danh sách cho phép; những trường ảnh hưởng ý nghĩa nội dung cũng cần được xác thực đúng cách.

### 8.2 Không “sửa” record bị cắt bằng cách đoán tag

Một lỗi phổ biến là thấy `AEADBadTagException` rồi thử thêm byte zero, tự cắt 16 byte cuối, thay nonce, thay AAD, hoặc giải mã một phần. Các cách đó thay đổi dữ liệu/giao thức ban đầu, không khôi phục bản mã xác thực. Khi truyền nhận không đầy đủ, giải pháp đúng là **đọc lại từ nguồn đáng tin** theo cơ chế retry ở tầng giao thức, sử dụng record mới đầy đủ và xác minh lại từ đầu.

Nếu retry một **lần giải mã** trên cùng record với cùng khóa/AAD là cần thiết để chẩn đoán thì kết quả bảo mật sẽ không khác; không dùng vòng lặp thử khóa/tag để âm thầm vượt qua yêu cầu xác thực. Với **mã hóa**, không bao giờ retry bằng cách mã hóa plaintext khác với cùng key+nonce của AES-GCM.

### 8.3 Giữ format và kích thước đã cam kết

Nếu bạn dùng tag GCM 128 bit khi mã hóa, bên nhận phải biết đúng tag length 128 bit. Không lấy `length - 16` để tách tag khi chưa xác định header, trailer và phép framing đã đúng; không chấp nhận một tag bị cắt rồi so sánh vài byte đầu do attacker cung cấp. Nếu giao thức hỗ trợ tag ngắn hơn, đây phải là **quyết định thiết kế tường minh** được đánh giá bảo mật, thống nhất bên gửi/nhận, và truyền đạt không mơ hồ; không phải cách xử lý lỗi.

## 9. Kiểm tra lỗi theo quy trình

Khi điều tra một `AEADBadTagException`/`BadPaddingException` trên hệ thống thật, thực hiện theo thứ tự:

1. **Đọc transformation thực tế:** `AES/GCM/NoPadding` hay `AES/CBC/PKCS5Padding`? Nếu là GCM, kiểm tra tag length và AAD; nếu CBC, đánh giá nguy cơ padding oracle và thiếu authentication.
2. **Kiểm tra byte framing:** tổng số byte, header/version, số byte nonce/tag, record length và liệu stream có bị EOF sớm. Từ chối record ngắn trước bước crypto khi có thể.
3. **Kiểm tra chọn đúng key:** key ID, phiên bản rotation, provider/keystore; tránh log key. Khi key sai, tag GCM không khớp giống hệt trường hợp ciphertext bị sửa.
4. **Kiểm tra nonce/IV:** hai phía phải dùng byte nonce giống hệt; nonce 12 byte và tag 16 byte là quyết định format của ví dụ, không được tự suy ra từ ciphertext nếu giao thức khác.
5. **Kiểm tra AAD:** đúng byte và thứ tự, encoding, version và ngữ cảnh request. Sai một byte AAD cũng làm tag không xác minh.
6. **Kiểm tra ciphertext/tag và transport:** có bị hex/Base64 decode sai, newline, whitespace, reverse byte, chuyển charset, cắt record hoặc lỗi buffer size hay không?
7. **Kiểm tra provider bằng test độc lập:** round-trip với key/nonce/AAD trong môi trường thử nghiệm và dữ liệu test đã biết; không thử sửa dữ liệu production để bỏ qua lỗi.
8. **Kiểm tra chính sách xuất dữ liệu:** chỉ publish plaintext khi `doFinal` thành công; mọi exception cần rollback/xóa output tạm.

### Bảng chẩn đoán nhanh

| Dấu hiệu | Có thể do | Hành động |
| --- | --- | --- |
| GCM ném `AEADBadTagException` | Tag, key, nonce, AAD hoặc ciphertext không khớp; record bị sửa/cắt | Từ chối plaintext, kiểm tra format/nguồn byte bằng dữ liệu test, giữ phản hồi public thống nhất |
| GCM thiếu ít nhất 16 byte tag theo format | Input không đủ tối thiểu | Chặn trước `Cipher.init/doFinal`, báo malformed/truncated nội bộ |
| Ciphertext bị cắt một byte nhưng vẫn đủ minimum | Tag vẫn được diễn giải từ các byte cuối hiện có và không xác thực | Từ chối record; kiểm tra expected length/EOF |
| CBC ném `BadPaddingException` | Padding không hợp lệ, key sai, ciphertext thay đổi, lỗi format | Không xem đây là thông tin có thể công bố; đánh giá thiết kế CBC và thay bằng AEAD khi phù hợp |
| CBC ném `IllegalBlockSizeException` | Đầu vào không phù hợp số block hoặc mode | Kiểm tra framing, block size, loại dữ liệu |
| CBC không ném exception nhưng plaintext sai | Padding tình cờ hợp lệ; không có kiểm tra toàn vẹn | Không coi giải mã thành công là xác thực; cần AEAD/MAC |
| `InvalidAlgorithmParameterException` | Nonce/IV/tag length không hợp lệ hoặc provider từ chối | Kiểm tra transformation, `GCMParameterSpec` và provider |
| Kết quả khác giữa hai môi trường | Provider/JDK/cấu hình hoặc byte đầu vào khác | Ghi version, provider, transformation, kích thước record, test vector; không ghi khóa bí mật |
| GCM decrypt stream trả dữ liệu dù tag sai | Kết quả tạm hoặc wrapper nuốt lỗi xác thực | Không publish plaintext trước `doFinal`; tránh dùng wrapper che lỗi |

## 10. Checklist tích hợp vào dịch vụ

- [ ] Giao thức nêu rõ algorithm/mode, kích thước nonce/tag, thứ tự byte, version và AAD.
- [ ] AES-GCM dùng nonce **không trùng dưới cùng key**; key được quản lý đúng và không nằm trong log.
- [ ] Bên nhận kiểm tra version, tổng độ dài tối thiểu, giới hạn kích thước và framing trước giải mã.
- [ ] Không tự giả định mọi lỗi tag đều do giả mạo; phân biệt nguyên nhân vận hành bằng log/transport metrics có kiểm soát.
- [ ] Bắt `AEADBadTagException` trước `BadPaddingException` ở mã cần phân loại cụ thể.
- [ ] Không tiết lộ thông tin padding/tag/key chi tiết trên API public.
- [ ] Plaintext chỉ được sử dụng hoặc publish **sau khi kiểm tra tag thành công**.
- [ ] Có test round-trip, đổi một bit ciphertext/tag/nonce, sai AAD, bản mã cắt ngắn và thiếu header.
- [ ] Nếu lưu nhiều record, mỗi record có ranh giới và authentication đúng; không trộn các record.
- [ ] Không fallback sang mode không xác thực, không bỏ tag hoặc tự sửa data lỗi.

## 11. Bài tập thực hành

1. Chạy `AeadFailuresDemo.java`. Giải thích vì sao thay đổi tag, nonce và AAD đều dẫn đến `REJECT_AUTH` dù nguyên nhân bên trong khác nhau.
2. Đổi `Arrays.copyOf(envelope, envelope.length - 1)` thành cắt còn **28 byte**. Vì sao trạng thái chuyển từ `REJECT_AUTH` sang `REJECT_FORMAT` trong ví dụ?
3. Thêm một trường `keyId` (kiểu byte) vào header envelope. Thiết kế quy tắc chọn khóa và cách đưa trường đó vào AAD; làm sao tránh cho attacker điều khiển bất kỳ key nào được dùng?
4. Nếu nhận 32 MiB ciphertext qua stream, mô tả cách giữ output trong file tạm và chỉ publish sau khi tag xác thực thành công.
5. Phân biệt hậu quả của `BadPaddingException` trong CBC với `AEADBadTagException` trong GCM. Vì sao giải mã CBC thành công mà không báo exception vẫn chưa đủ để tin plaintext?
6. Thiết kế tập test với phiên bản header không hợp lệ, record vượt quá kích thước, ciphertext bị thiếu byte, base64 bị hỏng và các provider khác nhau; chỉ ra lỗi nào nên chặn ở parser và lỗi nào cần để `Cipher.doFinal` xác minh.

## Nguồn tham khảo chính thức

- [Java SE 17 — `AEADBadTagException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): xác thực tag AEAD thất bại và quan hệ kế thừa `BadPaddingException`.
- [Java SE 17 — `BadPaddingException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/BadPaddingException.html): lỗi padding khi giải mã và các ngoại lệ liên quan.
- [Java SE 17 — `IllegalBlockSizeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/IllegalBlockSizeException.html): đầu vào không phù hợp thao tác block.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation, `updateAAD`, `doFinal`, xử lý GCM và ngoại lệ.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): độ dài tag (bit) và IV/nonce.
- [Java SE 17 — `CipherInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): cảnh báo khi dùng với chế độ giải mã có xác thực.
- [NIST SP 800-38D — GCM/GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): đặc tả GCM, tag và yêu cầu với IV/nonce.
