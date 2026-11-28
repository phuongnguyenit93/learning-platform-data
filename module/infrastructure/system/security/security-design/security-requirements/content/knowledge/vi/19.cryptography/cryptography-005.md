# Authenticated encryption

## 1. Vì sao mã hóa bí mật chưa đủ?

Giả sử hệ thống mã hóa một hồ sơ trước khi lưu vào cơ sở dữ liệu. Nếu cơ chế chỉ bảo vệ tính bí mật, người sửa được ciphertext vẫn có thể làm dữ liệu sau giải mã thay đổi mà ứng dụng không phát hiện đúng.

Yêu cầu cần giải quyết hai câu hỏi:

1. Người không có khóa có đọc được plaintext hay không?
2. Ứng dụng có phát hiện dữ liệu mã hóa hoặc ngữ cảnh liên quan đã bị thay đổi hay không?

Authenticated encryption kết hợp bảo vệ tính bí mật với kiểm tra tính toàn vẹn và xác thực thông điệp theo khóa. AEAD, viết đầy đủ Authenticated Encryption with Associated Data, còn cho phép xác thực một phần dữ liệu ngữ cảnh không được mã hóa.

Mô hình giao diện AEAD được mô tả trong [RFC 5116](https://www.rfc-editor.org/rfc/rfc5116.html).

Trong thiết kế yêu cầu bảo mật, không nên chỉ ghi “mã hóa bằng AES”. Cần xác định mode, tham số, cách cấp nonce, dữ liệu ngữ cảnh, xử lý lỗi và vòng đời khóa. Một tên thuật toán đúng không bù được cho cách dùng sai.

### 1.1. Tài sản và tình huống đe dọa

Những tài sản có thể cần AEAD:

- Nội dung hồ sơ hoặc tài liệu lưu ngoài vùng tin cậy.
- Trường dữ liệu nhạy cảm trong một bản ghi.
- Bản tin cần được bảo vệ ở lớp ứng dụng.
- Dữ liệu trong object storage hoặc bản sao lưu.
- Một envelope mã hóa được truyền giữa các thành phần.

Những tình huống cần xem xét:

| Tình huống | Mục tiêu cần đạt |
|---|---|
| Đọc được ciphertext từ storage | Không khôi phục được plaintext khi thiếu khóa |
| Sửa một phần ciphertext | Không chấp nhận nội dung đã bị can thiệp |
| Chuyển ciphertext sang đối tượng khác | Không giải mã thành dữ liệu hợp lệ trong sai ngữ cảnh |
| Thay metadata thuật toán hoặc phiên bản | Không tạo downgrade ngoài chính sách |
| Khôi phục bản cũ hợp lệ | Cần kiểm soát freshness riêng nếu nghiệp vụ yêu cầu |
| Khóa hoặc nonce bị dùng sai | Phát hiện, giới hạn và có cơ chế xử lý theo thiết kế |

AEAD đáp ứng một phần mô hình này. Những mục như rollback, quyền giải mã và việc quản lý khóa cần các kiểm soát bổ sung.

### 1.2. “Authenticated” không có nghĩa là xác thực người dùng

Tag hợp lệ cho biết dữ liệu phù hợp với phép tạo thông điệp bằng khóa và các đầu vào tương ứng, trong giả định an toàn của cơ chế được dùng.

Nó không tự chứng minh:

- Người gọi API là ai.
- Người gọi có quyền đọc hồ sơ.
- Ai trong những bên cùng giữ khóa đã tạo thông điệp.
- Thông điệp là phiên bản mới nhất.
- Dữ liệu bên trong đúng về nghiệp vụ.

Vì dùng khóa đối xứng, những bên có khả năng tạo tag bằng cùng khóa không được phân biệt như trong một mô hình chữ ký số. Không dùng AEAD làm bằng chứng chống chối bỏ danh tính cá nhân.

## 2. Mô hình đầu vào và đầu ra

Có thể mô tả một phép mã hóa:

```text
C = Encrypt(K, N, P, A)
```

Và phép giải mã:

```text
Decrypt(K, N, C, A) → P hoặc FAIL
```

| Ký hiệu | Ý nghĩa | Có cần giữ bí mật? |
|---|---|---|
| K | Khóa bí mật | Có |
| N | Nonce hoặc IV theo thuật toán | Thường không; phải đáp ứng quy tắc sử dụng |
| P | Plaintext | Theo phân loại dữ liệu |
| A | Additional authenticated data, hay AAD | Không được AEAD mã hóa |
| C | Kết quả mã hóa có thông tin xác thực theo định dạng | Có thể lưu hoặc truyền ngoài vùng tin cậy theo threat model |

Giao diện giải mã chỉ có plaintext hợp lệ hoặc thất bại, thay vì coi dữ liệu chưa xác minh là một kết quả sử dụng được. Đây là một đặc tính quan trọng của [giao diện authenticated decryption trong RFC 5116 §2.2](https://www.rfc-editor.org/rfc/rfc5116.html#section-2.2).

### 2.1. Authentication tag

Một implementation có thể trả ciphertext và tag riêng, hoặc ghép chúng thành một output. Cần quy định định dạng cụ thể cho envelope để các thành phần hiểu giống nhau.

Không tự cắt ngắn tag để giảm dung lượng nếu profile mật mã của hệ thống không cho phép. Độ dài tag, khối lượng dữ liệu và số lần thử xác minh liên quan đến mức bảo đảm xác thực.

Một tag không hợp lệ phải làm thao tác thất bại. Không trả plaintext “có vẻ đúng”, không bỏ qua lỗi và không thử một cơ chế không có xác thực để cứu dữ liệu.

### 2.2. Nonce không phải khóa và không phải salt của mật khẩu

Nonce thường được lưu cùng ciphertext để phục vụ giải mã. Việc nonce công khai không tự làm mất tính bí mật.

Tuy nhiên, nonce có yêu cầu sử dụng riêng theo thuật toán. Đối với AES-GCM, không lặp nonce khi mã hóa bằng cùng khóa là điều kiện thiết yếu.

Salt trong password hashing có mục tiêu và vòng đời khác. Không dùng hai thuật ngữ thay thế nhau hoặc áp dụng quy tắc tạo salt như thể tự đáp ứng hợp đồng nonce của mọi AEAD.

### 2.3. AAD không được mã hóa

Nếu đưa tenantId, loại hồ sơ hoặc một nhãn nghiệp vụ vào AAD, các giá trị đó không được AEAD giữ bí mật.

AAD phù hợp với dữ liệu cần gắn vào kết quả kiểm tra toàn vẹn nhưng có thể tồn tại ở dạng rõ theo chính sách. Nếu chính nội dung ngữ cảnh là bí mật, phải chọn biểu diễn khác hoặc đưa phần bí mật vào plaintext theo thiết kế.

## 3. Chọn một profile thay vì một tên chung

Một profile mật mã là tập tham số được quy định cùng nhau.

Ví dụ profile ứng dụng giả định:

```text
Mục đích: mã hóa một giá trị dữ liệu nhỏ ở lớp ứng dụng
Thuật toán: AES-GCM
Khóa: AES 256 bit, được quản lý bởi thành phần khóa
Nonce: 96 bit, cấp theo cơ chế đã kiểm soát
Tag: 128 bit
AAD: định dạng ngữ cảnh phiên bản 1
Envelope: phiên bản 1, có giới hạn kích thước
Giải mã: không xuất plaintext trước xác minh thành công
```

Đây là ví dụ để diễn đạt yêu cầu, không phải cấu hình áp dụng cho mọi môi trường.

GCM là một mode AEAD được NIST đặc tả trong [SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final). Khi hệ thống cần tuân theo một baseline hoặc chế độ chứng nhận cụ thể, phải xác định cả phiên bản tài liệu áp dụng, provider, môi trường triển khai và quy trình kiểm chứng; chỉ chọn tên AES-GCM không tự chứng minh tuân thủ.

### 3.1. Những quyết định cần ghi vào profile

- Thuật toán và tham số được phép.
- Nguồn khóa và phạm vi sử dụng khóa.
- Cách tạo nonce và bảo đảm theo toàn bộ các instance.
- Giới hạn số lần mã hóa, lượng dữ liệu và lần xác minh thất bại phù hợp.
- Kích thước plaintext, AAD và envelope tối đa.
- Cách serialize AAD.
- Định dạng ciphertext/tag.
- Cơ chế quản lý version và khóa cũ.
- Hành vi khi lỗi hoặc thành phần khóa không khả dụng.

Không để caller chọn tùy ý mode, tag length hoặc thuật toán từ một string trong request.

### 3.2. Không tự ghép các primitive để thay AEAD

Mã hóa bằng một mode bất kỳ rồi thêm một checksum không tự tạo authenticated encryption an toàn. Một hash không khóa có thể được bên sửa dữ liệu tính lại.

Ngay cả cách kết hợp encryption và MAC cũng cần thiết kế đúng về khóa, thứ tự thao tác, encoding và lỗi. Đối với một ứng dụng thông thường, nên sử dụng giao diện AEAD của thư viện được duy trì, thay vì tự xây một giao thức mới từ các primitive.

## 4. Nonce: yêu cầu trên toàn bộ vòng đời khóa

### 4.1. Phạm vi uniqueness là khóa thực tế

Với AES-GCM, quy tắc phải được đánh giá theo khóa mật mã thực tế, không chỉ theo một nhãn keyId.

Nếu hai alias trỏ tới cùng key material, đổi alias không làm một nonce đã dùng trở thành mới. Nếu hai service dùng chung khóa, chúng cũng chia sẻ cùng miền sử dụng nonce.

Yêu cầu có thể viết:

> Mỗi lần mã hóa mới bằng cùng một khóa AES-GCM phải được cấp nonce theo cơ chế bảo đảm không tái sử dụng ngoài giới hạn rủi ro đã được phê duyệt. Phạm vi kiểm soát bao gồm mọi instance, tiến trình, vùng triển khai và đường retry dùng khóa đó.

Đối với GCM, việc tái sử dụng nonce có thể phá cả bảo mật lẫn xác thực. Hướng dẫn nonce và các ràng buộc sử dụng nằm trong [NIST SP 800-38D, các phần 8 và phụ lục liên quan](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf).

### 4.2. Hai chiến lược cần được thiết kế

| Chiến lược | Điều cần chứng minh |
|---|---|
| Bộ cấp nonce có trạng thái | Không trùng qua concurrency, crash, restart và restore |
| Nonce từ nguồn ngẫu nhiên mật mã | Nguồn sinh phù hợp, ngân sách sử dụng và rủi ro va chạm được đánh giá |

Một counter trong bộ nhớ không đủ nếu khóa còn tồn tại sau khi tiến trình restart. Một timestamp cũng không tự tạo uniqueness khi nhiều request hoặc instance có thể dùng cùng thời điểm.

Với random nonce, xác suất va chạm không bằng không. Đặc tả không nên chỉ ghi “dùng SecureRandom nên chắc chắn không trùng”. Cần định nghĩa ngân sách theo khóa và chiến lược thay khóa phù hợp profile.

### 4.3. Backup và khôi phục trạng thái

Một hệ thống dùng counter có thể sao lưu cả khóa lẫn trạng thái cấp nonce. Nếu restore về một counter cũ nhưng tiếp tục dùng khóa cũ, những giá trị từng cấp có thể được cấp lại.

Yêu cầu phục hồi phải xử lý trường hợp đó bằng cơ chế đã thiết kế, chẳng hạn:

- Không tái sử dụng vùng nonce đã cấp.
- Phân phối namespace có thẩm quyền cho instance.
- Giữ trạng thái cấp phát chống quay lùi phù hợp.
- Chuyển sang khóa mới khi không chứng minh được an toàn tiếp tục.

Các lựa chọn cần được đánh giá cùng kiến trúc, không phải ghép một prefix tùy tiện rồi coi vấn đề đã giải quyết.

### 4.4. Retry không đồng nghĩa mã hóa lại với nonce cũ

Nếu một ciphertext đã được tạo hợp lệ nhưng việc ghi storage thất bại, có thể có hai hành vi khác nhau:

- Ghi lại chính envelope đã tạo, không chạy phép mã hóa mới.
- Chạy một phép mã hóa mới, phải xin nonce phù hợp cho lần mới.

Không nên gọi lại encryption với nonce cũ như một cách retry mặc định.

Việc giải mã lại một envelope hợp lệ không phải là tái sử dụng nonce cho mã hóa. Replay và uniqueness là hai vấn đề khác nhau.

### 4.5. Khi không cấp được nonce

Nếu allocator lỗi, mất trạng thái hoặc đạt giới hạn, hệ thống phải dừng mã hóa mới theo chính sách.

Không fallback sang nonce bằng 0, thời gian hiện tại hoặc một bộ đếm mới khởi tạo. Một lỗi khả dụng không được âm thầm chuyển thành vi phạm điều kiện an toàn của thuật toán.

## 5. AAD: gắn dữ liệu với ngữ cảnh

### 5.1. Ngăn chuyển ciphertext sang đối tượng khác

Giả sử hai tài liệu dùng cùng một khóa dữ liệu. Nếu ciphertext của tài liệu A được sao chép vào vị trí tài liệu B, phép giải mã có thể vẫn hợp lệ nếu ứng dụng không gắn ngữ cảnh đối tượng.

Một thiết kế AAD có thể dùng:

```text
formatVersion
purpose
tenantId
objectId
fieldName
contentVersion
```

Khi đọc tài liệu B, service tái tạo expected AAD từ ngữ cảnh B đáng tin. Ciphertext đã tạo cho A không phù hợp với AAD đó.

Điều quan trọng là expected context phải đến từ đối tượng và quyền mà service đã xác định, không chỉ được chép nguyên từ metadata mà bên cung cấp ciphertext tự khai.

### 5.2. Xác thực một lời khai chưa chứng minh lời khai phù hợp

Một envelope có thể mang tenantId trong header và gắn nó vào tag. Điều đó chỉ có ích đúng mục tiêu nếu service còn đối chiếu tenantId với tenant được phép trong request.

Nếu service luôn dùng tenantId từ envelope để giải mã rồi trả dữ liệu cho bất kỳ caller nào, tag hợp lệ không ngăn truy cập chéo tenant.

Luồng đúng:

```text
Xác thực và kiểm tra quyền
    → xác định object/tenant dự kiến
    → tạo expected AAD
    → chọn khóa được phép
    → xác minh và giải mã
    → sử dụng plaintext
```

### 5.3. Encoding AAD phải không nhập nhằng

Ghép chuỗi không có cấu trúc:

```text
tenantId + objectId
```

có thể làm các bộ trường khác nhau tạo cùng một byte string.

Thiết kế cần một định dạng xác định, chẳng hạn trường có độ dài cố định hoặc encoding có chiều dài, kiểu và thứ tự được mô tả rõ. Nếu dùng JSON, phải có quy tắc canonicalization phù hợp; không giả định mọi serializer luôn sinh byte giống nhau.

RFC 5116 yêu cầu cách xây dựng đầu vào nhiều thành phần phải không nhập nhằng. Đây là lý do đặc tả phải nói về byte, charset, thứ tự và version, thay vì chỉ liệt kê tên field.

### 5.4. Chọn thuộc tính ổn định

Nếu đưa title vào AAD, đổi title có thể yêu cầu tạo lại ciphertext hoặc có cơ chế chuyển đổi được thiết kế.

Một số thuộc tính nên ổn định theo tuổi thọ ciphertext; một số khác cần được thay đổi độc lập. Hãy xác định điều đó trước để tránh việc đội vận hành phải bỏ kiểm tra AAD khi dữ liệu đổi.

Đưa timestamp vào AAD không tự làm dữ liệu hết hạn. Hệ thống vẫn phải kiểm tra thời gian theo đồng hồ và policy đáng tin khi expiry là yêu cầu.

## 6. Envelope và quản lý metadata

### 6.1. Một định dạng cần có hợp đồng

Một envelope logic có thể gồm:

```json
{
  "version": 1,
  "profile": "document-aead-v1",
  "keyVersion": "managed-key-version",
  "nonce": "<encoded-bytes>",
  "ciphertextAndTag": "<encoded-bytes>"
}
```

Đây là ví dụ mô hình, không phải dữ liệu mã hóa thực tế.

Cần đặc tả:

- Những field bắt buộc.
- Dạng encoding, padding và quy tắc canonicalization nếu có.
- Độ dài tối đa trước và sau decode.
- Profile và version được phép.
- Cách ràng buộc metadata có ý nghĩa bảo mật.
- Cách tạo expected AAD.
- Hành vi với dữ liệu thiếu hoặc thừa theo schema.

Base64 chỉ biểu diễn byte. Nó không thay encryption, tag hoặc xác thực nguồn dữ liệu.

### 6.2. Metadata chưa được tin chỉ vì đã parse

version hoặc keyVersion có thể cần được đọc trước để chọn đường xử lý. Nhưng các giá trị đó vẫn là đầu vào không tin cậy cho đến khi được kiểm tra phù hợp.

Không cho phép keyVersion là URL tùy ý tới một dịch vụ khóa. Resolver phải chỉ truy cập những key reference trong phạm vi được cấu hình.

Không cho phép profile chọn một thuật toán legacy không có xác thực hoặc một cấu hình tag yếu hơn. Mỗi version cần ánh xạ tới một profile hữu hạn được ứng dụng quản lý.

### 6.3. Bind metadata ở đúng lớp

Thông tin như format version, mục đích và định danh khóa dữ liệu có thể cần được gắn vào AAD theo profile.

Nếu có envelope encryption với DEK được bọc bằng KEK, cần phân biệt:

- Nội dung được mã hóa bằng DEK.
- Metadata xác thực của nội dung.
- DEK đã bọc và metadata của lớp wrapping.
- Những trường được phép đổi khi rewrap.

Không đưa mọi metadata có thể thay đổi vào AAD một cách máy móc. Nếu muốn thay KEK mà giữ nguyên ciphertext dữ liệu, định dạng phải hỗ trợ việc đó mà vẫn bảo vệ những ràng buộc cần thiết.

## 7. Ví dụ Java: primitive AES-GCM với nonce đã cấp

Đoạn code Java 17 trở lên dưới đây minh họa cách gọi JCA. Nó nhận nonce từ một allocator đáng tin ở lớp bao ngoài; không tự thực hiện uniqueness phân tán, quản lý khóa hoặc authorization.

Profile minh họa dùng nonce 12 byte, tag 128 bit và giới hạn dữ liệu nhỏ.

```java
import java.security.GeneralSecurityException;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmPrimitive {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int MAX_PLAINTEXT_BYTES = 1_048_576;
    private static final int MAX_AAD_BYTES = 4_096;

    private AesGcmPrimitive() {
    }

    // freshNonce đã được allocator cấp riêng cho lần mã hóa này,
    // trong miền của đúng key material, không do request tự chọn.
    public static byte[] encryptWithAllocatedNonce(
            SecretKey key,
            byte[] freshNonce,
            byte[] plaintext,
            byte[] aad
    ) throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        requireNonce(freshNonce);
        requireLength(plaintext, MAX_PLAINTEXT_BYTES, "plaintext");
        requireLength(aad, MAX_AAD_BYTES, "aad");

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, freshNonce)
        );
        cipher.updateAAD(aad);

        return cipher.doFinal(plaintext);
    }

    // expectedAad được tạo từ ngữ cảnh ứng dụng đã xác minh.
    public static byte[] decrypt(
            SecretKey key,
            byte[] storedNonce,
            byte[] ciphertextAndTag,
            byte[] expectedAad
    ) throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        requireNonce(storedNonce);
        requireLength(expectedAad, MAX_AAD_BYTES, "expectedAad");
        requireLength(
                ciphertextAndTag,
                MAX_PLAINTEXT_BYTES + TAG_BYTES,
                "ciphertextAndTag"
        );

        if (ciphertextAndTag.length < TAG_BYTES) {
            throw new IllegalArgumentException("Invalid encrypted value");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, storedNonce)
        );
        cipher.updateAAD(expectedAad);

        // Chỉ trả kết quả sau khi doFinal thành công.
        return cipher.doFinal(ciphertextAndTag);
    }

    private static void requireNonce(byte[] nonce) {
        Objects.requireNonNull(nonce, "nonce");

        if (nonce.length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid nonce length");
        }
    }

    private static void requireLength(
            byte[] value,
            int maximum,
            String name
    ) {
        Objects.requireNonNull(value, name);

        if (value.length > maximum) {
            throw new IllegalArgumentException("Invalid " + name + " length");
        }
    }
}
```

JCA mô tả transformation, thứ tự updateAAD và việc gắn/kiểm tra tag trong [Cipher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html). Tham số tag length của [GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html) tính bằng bit, còn buffer nonce trong ví dụ là byte.

### 7.1. Hợp đồng mà code không tự chứng minh

- Key được sinh hoặc cung cấp theo profile và được phép dùng cho mục đích này.
- freshNonce là mới trong miền khóa, kể cả qua nhiều instance.
- AAD có encoding xác định và ngữ cảnh đúng.
- Mảng đầu vào không bị caller thay đổi đồng thời khi xử lý.
- Envelope được lưu đầy đủ và nguyên tử theo yêu cầu storage.
- Caller đã được kiểm tra quyền trước khi giải mã.
- Lỗi được chuyển thành response có kiểm soát, không lộ dữ liệu.
- Ngân sách theo khóa được theo dõi ngoài đoạn primitive.

Kiểm tra độ dài nonce chỉ xác nhận kích thước, không xác nhận uniqueness. Không đưa hàm này thành public API cho người dùng tự gửi key, nonce và dữ liệu để tùy ý mã hóa.

### 7.2. Lỗi tag phải chặn sử dụng plaintext

Khi tag không được chấp nhận, provider có thể báo AEADBadTagException trong hệ thống exception của JCA.

Lớp ứng dụng không được bắt lỗi rồi:

- Trả một buffer đã giải mã dở.
- Bỏ tag và thử lại bằng mode khác.
- Dùng AAD rỗng để cứu dữ liệu.
- Thử mọi tenant hoặc mọi khóa cho tới khi có kết quả.
- Đánh dấu dữ liệu đã xác thực chỉ vì giải mã ra JSON có vẻ hợp lệ.

Phân biệt lỗi cấu hình, lỗi dịch vụ khóa và lỗi xác thực dữ liệu để vận hành, nhưng không trả những chi tiết nhạy cảm không cần thiết cho caller.

### 7.3. Không phát plaintext trước xác minh

Đối với dữ liệu nhỏ, ví dụ gọi doFinal một lần và chỉ trả kết quả sau thành công.

Với file lớn hoặc streaming, không được suy ra rằng mọi API stream đều tự cung cấp ranh giới “chỉ dùng plaintext đã xác thực”. Cần chọn một định dạng hoặc thư viện streaming AEAD được thiết kế phù hợp.

Nếu chia thành các record có xác thực, thiết kế còn phải kiểm soát thứ tự, định danh file, vị trí record và việc cắt ngắn toàn bộ dữ liệu. Không chỉ mã hóa từng chunk độc lập rồi mặc định file đầy đủ và đúng thứ tự.

## 8. Những bảo đảm AEAD không cung cấp một mình

### 8.1. Replay và rollback

Một ciphertext cũ nhưng hợp lệ vẫn có thể vượt qua kiểm tra tag.

Nếu nghiệp vụ cần ngăn:

- Thay bản mới bằng bản cũ.
- Thực hiện lại một lệnh đã xử lý.
- Đọc dữ liệu sau thời điểm hết hạn.
- Khôi phục trạng thái quyền cũ.

thì phải có sequence, version, expiry hoặc trạng thái chống replay thích hợp.

Chỉ thêm contentVersion vào AAD chưa đủ nếu cả version và ciphertext có thể bị quay lùi cùng nhau. Cần một nguồn xác định version hiện hành theo threat model.

### 8.2. Authorization

Một người có thể biết objectId và cung cấp envelope hợp lệ của người khác. Service vẫn phải xác thực, kiểm tra tenant và quyền đối tượng.

Không cung cấp một endpoint giải mã chung cho mọi caller chỉ vì ciphertext có tag. Khả năng gọi decrypt là một quyền nhạy cảm cần giới hạn và audit.

### 8.3. Dữ liệu đã được giải mã

Sau khi xác minh thành công, plaintext có thể vẫn chứa dữ liệu sai nghiệp vụ hoặc không phù hợp với ngữ cảnh xuất ra.

Nếu plaintext là HTML, việc tag hợp lệ không cho phép chèn trực tiếp vào DOM. Nếu nó là một lệnh thanh toán, vẫn cần kiểm tra trạng thái và quyền. Tính toàn vẹn mật mã không thay validation hoặc output encoding.

### 8.4. Metadata và độ dài

AEAD không mặc định che độ dài plaintext hoặc mọi thuộc tính của envelope. Key reference, nonce, AAD và kích thước ciphertext có thể để lộ metadata theo định dạng.

Nếu threat model yêu cầu giảm rò rỉ độ dài hoặc định danh, phải có thiết kế bổ sung. Không tuyên bố “đã mã hóa nên storage không biết gì”.

### 8.5. Khóa bị lộ

Nếu khóa bị lấy, mức bảo vệ của dữ liệu dưới khóa đó bị ảnh hưởng theo khả năng của bên tấn công. Tag không bảo vệ khỏi người đã có đầy đủ quyền tạo dữ liệu hợp lệ bằng khóa.

Cần kiểm soát truy cập khóa, tách quyền, quan sát sử dụng và quy trình ứng phó. Không đặt khóa cạnh ciphertext trong cùng một file cấu hình có cùng quyền truy cập rồi coi đã giải quyết threat model đọc storage.

## 9. Quản lý khóa và migration

### 9.1. Tách mục đích sử dụng

Một key không nên được dùng tùy tiện cho mọi mục đích mã hóa, ký MAC hoặc môi trường.

Thiết kế cần xác định scope:

- Môi trường production và kiểm thử.
- Tenant hoặc nhóm tài nguyên nếu cần.
- Mục đích dữ liệu.
- Phiên bản profile.
- Quyền encrypt và decrypt của từng workload.

Tách key giúp giảm ảnh hưởng khi một miền bị lộ và làm miền nonce dễ quản lý hơn, nhưng không tự thay authorization.

### 9.2. Rotation không chỉ đổi một biến cấu hình

Cần phân biệt:

- Khóa mới dùng cho encryption mới.
- Khóa cũ chỉ được phép decrypt dữ liệu còn tồn tại.
- Dữ liệu được re-encrypt hoặc DEK được rewrap.
- Thời điểm ngừng cho phép giải mã bằng key cũ.
- Backup và thời hạn giữ dữ liệu.

Nếu xóa key trước khi xử lý dữ liệu và backup cần thiết, hệ thống có thể mất khả năng phục hồi. Nếu giữ key cũ không giới hạn mà không kiểm soát, mục tiêu giảm phạm vi rủi ro có thể không đạt.

### 9.3. Migration từ định dạng không có xác thực

Không nên tự coi dữ liệu legacy là hợp lệ chỉ vì giải mã thành công. Một mode cũ không có tag không cung cấp cùng bằng chứng toàn vẹn.

Một kế hoạch migration cần:

- Phân biệt định dạng bằng metadata có kiểm soát.
- Hạn chế ai và đường nào được xử lý legacy.
- Có cách đánh giá nguồn và tính toàn vẹn dữ liệu cũ theo khả năng.
- Ghi lại kết quả chuyển đổi và lỗi.
- Không thử legacy tự động khi tag của định dạng mới thất bại.

Nếu mỗi lỗi AEAD đều kích hoạt fallback legacy, bên sửa envelope có thể lợi dụng đường yếu hơn.

### 9.4. Khi dịch vụ khóa không khả dụng

Chọn hành vi rõ cho encrypt và decrypt:

- Dừng với lỗi có kiểm soát.
- Retry có giới hạn theo loại lỗi.
- Không dùng key mặc định hoặc key test.
- Không ghi plaintext tạm ra storage không được bảo vệ.
- Không bỏ xác minh để tăng khả dụng.

Những lựa chọn cache key, thời hạn và quyền truy cập trong bộ nhớ cần được đánh giá riêng. Đoạn code primitive không tự giải quyết sự cố hạ tầng khóa.

## 10. Chuyển quyết định thành yêu cầu kiểm chứng được

### 10.1. Phát biểu mơ hồ

> Dữ liệu nhạy cảm phải được mã hóa an toàn.

Phát biểu này không nói về toàn vẹn, nonce, AAD hoặc khi nào được dùng plaintext.

### 10.2. Yêu cầu về profile

> Trường nội dung hồ sơ phải được mã hóa bằng profile AEAD được quản lý của sản phẩm. Profile xác định thuật toán, key size, nonce length, tag length, định dạng AAD và envelope. Caller không được tự chọn mode hoặc giảm tag length qua request.

### 10.3. Yêu cầu về nonce

> Mọi phép mã hóa mới bằng cùng key material phải dùng nonce do thành phần cấp nonce có thẩm quyền cung cấp theo profile. Cơ chế phải đáp ứng concurrency, restart, restore và retry. Khi không cấp được nonce phù hợp hoặc đạt ngân sách sử dụng khóa, hệ thống không tạo ciphertext mới bằng khóa đó.

### 10.4. Yêu cầu về AAD

> Expected AAD phải gắn dữ liệu với tenant, đối tượng, mục đích và version theo schema đã công bố. Context được tái tạo từ quyền và tài nguyên đã xác minh, không chỉ từ metadata do caller cung cấp. Encoding có version và không nhập nhằng.

### 10.5. Yêu cầu về giải mã

> Plaintext chỉ được sử dụng hoặc trả ra sau khi xác minh thành công. Khi envelope malformed, tag sai hoặc context không khớp, không có plaintext hoặc tác dụng phụ nghiệp vụ dựa trên dữ liệu chưa xác minh được phát hành.

### 10.6. Yêu cầu về parser và tài nguyên

> Giới hạn kích thước envelope được kiểm tra trước decode tốn kém hoặc cấp bộ nhớ lớn. Profile, key reference và version ngoài danh sách cho phép bị từ chối. Một request không được gây chuỗi thử khóa hoặc tải key từ đích tùy ý.

### 10.7. Mẫu truy vết

```text
ID: CRYPTO-AEAD-01
Tài sản:
    nội dung hồ sơ và tính toàn vẹn ngữ cảnh
Rủi ro:
    đọc, sửa hoặc chuyển ciphertext ngoài phạm vi
Profile:
    profile dữ liệu đã được quản lý
Nonce:
    cấp theo miền khóa và vòng đời đã thiết kế
AAD:
    tenant + object + purpose + version
Ranh giới sử dụng:
    chỉ sau authenticated decryption thành công
Bằng chứng:
    round trip, sửa dữ liệu, sai context, restart và rotation
Chủ sở hữu:
    nhóm dữ liệu, ứng dụng và nền tảng khóa
```

## 11. Ma trận rủi ro và bằng chứng

| Rủi ro | Kiểm soát | Bằng chứng chấp nhận |
|---|---|---|
| Đọc ciphertext từ storage | AEAD với key được bảo vệ | Không có plaintext trong vùng lưu ngoài phạm vi |
| Sửa ciphertext hoặc tag | Xác minh trước sử dụng | Dữ liệu sửa không tạo kết quả hoặc side effect hợp lệ |
| Chuyển envelope sang object khác | Expected AAD từ context đáng tin | Sai tenant/object/purpose bị từ chối |
| Nonce lặp qua instance | Allocator hoặc random budget phù hợp | Kiểm chứng thiết kế cấp phát, giới hạn và concurrency |
| Counter quay lùi sau restore | Policy phục hồi nonce/key | Không mã hóa lại trong miền nonce đã dùng |
| Caller chọn thuật toán yếu | Profile allowlist | Không có downgrade qua metadata |
| Tag sai kích hoạt fallback | Không cứu dữ liệu bằng đường yếu | Lỗi giữ nguyên trạng thái thất bại |
| Replay bản cũ hợp lệ | Freshness/rollback control riêng | Phiên bản cũ bị xử lý theo policy |
| Giải mã thành công nhưng sai quyền | Authorization độc lập | Caller ngoài phạm vi không nhận plaintext |
| Input quá lớn làm cạn tài nguyên | Giới hạn trước parse/decode | Không cấp phát hoặc gọi key service ngoài ngân sách |

## 12. Thiết kế kiểm chứng

Các tình huống trong phần này là tiêu chí cho triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

### 12.1. Round trip

Với dữ liệu tổng hợp:

```text
Decrypt(K, N, Encrypt(K, N, P, A), A) = P
```

Cần bao phủ plaintext rỗng nếu profile cho phép, dữ liệu nhị phân, Unicode được encode theo hợp đồng và các kích thước biên.

Round trip chưa chứng minh toàn bộ an toàn. Hai hàm cùng mắc lỗi định dạng vẫn có thể khôi phục dữ liệu trong một chương trình nhưng không đáp ứng profile hoặc tương thích với thành phần khác.

### 12.2. Thay đổi đầu vào

Kiểm tra những trường hợp:

| Thay đổi | Kết quả mong đợi |
|---|---|
| Ciphertext bị sửa | Xác thực không được chấp nhận |
| Tag bị sửa hoặc thiếu | Từ chối, không phát plaintext |
| Nonce không đúng | Không chấp nhận dữ liệu |
| AAD khác | Không chấp nhận dữ liệu |
| Dùng key khác | Không chấp nhận dữ liệu |
| Tenant/object context khác | Không giải mã thành dữ liệu được phép |
| Envelope sai version/profile | Từ chối theo policy |
| Key reference ngoài phạm vi | Không gọi key tùy ý |
| Payload quá lớn | Từ chối trước công việc vượt ngân sách |

Bảo đảm xác thực có giới hạn xác suất theo cơ chế mật mã; không diễn đạt nó như một khẳng định toán học rằng không tồn tại bất kỳ giả mạo nào. Tiêu chí vận hành cần phù hợp với profile và giới hạn sử dụng đã chọn.

### 12.3. Kiểm tra không có plaintext trước thất bại

Không chỉ kiểm tra exception. Cần quan sát:

- Response không có plaintext.
- File output chưa được công bố.
- Không ghi plaintext vào log lỗi.
- Không có event nghiệp vụ phát ra từ dữ liệu chưa xác minh.
- Parser nghiệp vụ không dùng buffer giải mã dở.
- Cache không lưu kết quả chưa được chấp nhận.

Đây là bằng chứng của ranh giới sử dụng, không chỉ của lời gọi thư viện.

### 12.4. Kiểm tra nonce ở mức kiến trúc

Các tình huống:

- Nhiều thread xin nonce đồng thời.
- Nhiều instance dùng cùng key.
- Tiến trình crash sau cấp nonce nhưng trước lưu ciphertext.
- Retry sau một lỗi storage.
- Restart hoặc restore từ snapshot.
- Counter hoặc quota đạt giới hạn.
- Thay alias nhưng key material không đổi.
- Mất dịch vụ cấp nonce.

Không thấy trùng trong một triệu mẫu ngẫu nhiên không chứng minh uniqueness cho mọi lần sử dụng. Bằng chứng cần gồm thiết kế, miền trạng thái và ngân sách, ngoài kiểm tra hành vi.

### 12.5. Known-answer và tương thích

Nếu cần kiểm chứng primitive hoặc provider theo profile, có thể dùng vector đã công bố với dữ liệu thử cố định. Những key và nonce cố định đó chỉ thuộc bộ thử, không được đưa vào đường encryption thật.

Cần kiểm tra định dạng envelope và AAD giữa các service hoặc ngôn ngữ, đặc biệt:

- Byte order.
- Charset.
- Biểu diễn số và version.
- Vị trí hoặc cách ghép tag.
- Base64 variant.
- Quy tắc canonicalization.

Không khắc phục khác biệt bằng cách thử nhiều encoding cho tới khi một lần thành công; hãy sửa hợp đồng byte cụ thể.

### 12.6. Rotation và phục hồi

Cần xác minh:

- Dữ liệu mới dùng phiên bản khóa dự kiến.
- Dữ liệu cũ còn được giải mã trong thời hạn cho phép.
- Khóa nghỉ không tiếp tục encrypt ngoài policy.
- Envelope đang migration không bị ghi thiếu.
- Backup còn khả năng phục hồi theo cam kết.
- Restore không quay lùi nonce rồi tiếp tục mã hóa sai.
- Việc ngừng khóa có tác động được hiểu trước.

## 13. Quan sát, sự cố và những sai lầm thường gặp

### 13.1. Quan sát đủ mà không lộ bí mật

Có thể theo dõi:

- Số lần encrypt theo profile và phiên bản khóa.
- Trạng thái allocator và ngân sách nonce.
- Số lỗi envelope malformed.
- Số lỗi xác thực dữ liệu.
- Lỗi key service hoặc provider.
- Trạng thái rotation và migration.

Không ghi key material, plaintext hoặc toàn bộ envelope nhạy cảm để debug. Key reference và AAD cũng cần được phân loại; không mặc định chúng luôn có thể công khai chỉ vì không được mã hóa.

### 13.2. Khi nghi nonce đã bị lặp

Cần dừng hoặc giới hạn encryption mới bằng khóa liên quan theo quy trình, xác định miền sử dụng và đánh giá dữ liệu bị ảnh hưởng.

Không chỉ đổi random seed rồi tiếp tục coi ciphertext cũ hoàn toàn an toàn. Vi phạm có thể ảnh hưởng các bảo đảm dưới khóa đó, nên phải xử lý theo đánh giá mật mã và ứng phó sự cố phù hợp.

### 13.3. Khi tag bắt đầu lỗi hàng loạt

Nguyên nhân có thể gồm dữ liệu hỏng, sai AAD, key version không đúng, lỗi migration hoặc can thiệp.

Không bỏ kiểm tra tag để khôi phục khả dụng. Cần phân loại lỗi bằng metadata tối thiểu và đối chiếu thay đổi cấu hình, khóa, encoding hoặc storage.

### 13.4. Những sai lầm cần tránh

- Dùng AES mà không ghi mode và tag.
- Dùng nonce cố định cho mọi bản ghi.
- Dùng timestamp như bằng chứng không trùng.
- Chỉ quản lý nonce trong từng process nhưng chia sẻ key toàn hệ thống.
- Cho AAD lấy hoàn toàn từ lời khai của caller.
- Giải mã rồi dùng plaintext trước khi tag được xác minh.
- Dùng AEAD để thay phân quyền.
- Coi tag hợp lệ là dữ liệu mới nhất.
- Tự fallback sang định dạng không xác thực khi lỗi.
- Xóa key trước khi xử lý dữ liệu và backup còn cần.
- Tạo một định dạng streaming bằng cách ghép chunk tùy ý.
- Đưa key hoặc plaintext vào log để tìm lỗi.

## 14. Điểm cần ghi nhớ

Authenticated encryption kết hợp bí mật với xác thực thông điệp; AEAD còn gắn được ngữ cảnh không mã hóa vào kết quả kiểm tra toàn vẹn.

Sử dụng đúng đòi hỏi một profile đầy đủ, nguồn khóa được bảo vệ, nonce đáp ứng điều kiện của thuật toán, AAD có encoding rõ và ranh giới không phát plaintext trước xác minh thành công.

Yêu cầu bảo mật cần bao phủ cả vòng đời: concurrency, restart, retry, restore, rotation và migration. Replay, authorization, dữ liệu sau giải mã và khả năng lộ metadata vẫn cần được thiết kế riêng. Một lời gọi Cipher đúng chỉ là một phần của hệ thống đáp ứng những yêu cầu đó.
