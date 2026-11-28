# Không tự phát minh thuật toán

## 1. Mục tiêu và phạm vi

Trong phát triển sản phẩm, “không tự phát minh thuật toán mật mã” có nghĩa là không thay cơ chế đã được phân tích và triển khai đáng tin cậy bằng một phép biến đổi do nhóm ứng dụng tự nghĩ ra. Nguyên tắc này áp dụng không chỉ cho một hàm mã hóa mới, mà còn cho việc tự ghép các primitive thành một scheme hoặc giao thức có những bảo đảm chưa được đánh giá.

Ví dụ, việc dùng AES trong một đoạn code không tự chứng minh toàn bộ thiết kế đã an toàn. Nhóm phát triển vẫn có thể làm sai mode, nonce, kiểm tra tag, liên kết ngữ cảnh hoặc quản lý khóa. Một tập các thành phần tốt không tự tạo thành một tổ hợp tốt.

Trong module yêu cầu bảo mật, mục tiêu là chuyển nguyên tắc thành các ràng buộc triển khai và bằng chứng nghiệm thu: cơ chế nào được phép, được dùng qua thành phần nào, tham số nào phải giữ, thay đổi nào cần đánh giá và điều gì xảy ra khi cơ chế đó không khả dụng.

Sau bài này, người học có thể:

- Phân biệt thuật toán, scheme, giao thức, implementation và profile triển khai.
- Nhận biết các thiết kế “có mã hóa” nhưng chưa có căn cứ về thuộc tính bảo mật cần đạt.
- Đặc tả việc dùng thư viện và profile được phê duyệt thay vì thuật toán tự sáng tác.
- Xác định trách nhiệm của ứng dụng đối với khóa, nonce, ngữ cảnh và vòng đời dữ liệu.
- Viết tiêu chí nghiệm thu vượt ra ngoài việc mã hóa rồi giải mã lại thành công.

Bài nói về hệ thống bảo vệ dữ liệu thật. Việc nghiên cứu hoặc tự triển khai để học có thể diễn ra trong phạm vi thí nghiệm, nhưng kết quả học tập không tự trở thành cơ chế được phép đưa vào sản phẩm.

## 2. Xác định đúng thứ đang được thiết kế

### 2.1. Năm lớp cần phân biệt

| Lớp | Ví dụ | Câu hỏi bảo mật |
| --- | --- | --- |
| Primitive/thuật toán nền | Block cipher, hash, KDF, chữ ký | Thuộc tính nào được cơ chế đó cung cấp và trong giả định nào? |
| Scheme hoặc mode | AEAD, password hashing scheme | Các đầu vào, tham số và cách kết hợp có đáp ứng mục tiêu không? |
| Giao thức | Cách các bên trao đổi thông điệp và xác nhận peer | Ai đang nói chuyện với ai, thứ tự, freshness và lỗi được xử lý thế nào? |
| Implementation | Thư viện, provider hoặc module thực hiện phép tính | Có đúng cơ chế, còn được duy trì và có đáp ứng môi trường triển khai không? |
| Profile ứng dụng | Cấu hình thuật toán, khóa, nonce, định dạng và ngữ cảnh | Dự án dùng đúng những điều kiện nào và kiểm chứng bằng gì? |

AES là một block cipher được mô tả trong FIPS 197. Việc có đặc tả cho block cipher không tự cung cấp thiết kế hoàn chỉnh cho lưu trữ tài liệu hoặc trao đổi thông điệp của ứng dụng. [NIST: FIPS 197](https://csrc.nist.gov/pubs/fips/197/final)

### 2.2. Hai cách “tự làm” đều có thể tạo rủi ro

Một cách dễ thấy là tự tạo phép biến đổi như đảo chuỗi, XOR theo một mẫu cố định rồi Base64 và gọi đó là mã hóa.

Cách khó thấy hơn là chọn những thành phần chuẩn rồi tự ghép: tự tạo giao thức bắt tay, tự thiết kế cách chứng minh người gửi, tự thêm hash để thay authentication tag hoặc tự xử lý lỗi theo một nhánh làm lộ thông tin.

Ở cả hai trường hợp, nhóm ứng dụng có thể đang nhận một trách nhiệm phân tích mật mã mà các test chức năng thông thường không đủ kiểm chứng.

### 2.3. Điều ứng dụng vẫn phải thiết kế

Ứng dụng vẫn phải chọn dữ liệu cần bảo vệ, đối tượng được đọc, vị trí xử lý, profile được phép và cách vận hành khóa. Nó cũng cần thiết kế cấu trúc lưu metadata, phiên bản bản ghi và luồng migration.

Những việc đó không bị cấm bởi nguyên tắc. Ranh giới là chúng phải giữ các điều kiện của cơ chế đã chọn và được đánh giá theo mô hình đe dọa, thay vì tự thêm một công thức mật mã chưa có căn cứ.

## 3. Vì sao tính đúng đắn chức năng chưa đủ?

### 3.1. Round-trip chỉ chứng minh một quan hệ hẹp

Một test có dạng:

```text
decrypt(encrypt(message)) == message
```

có ích để kiểm tra tính tương thích của hai đường xử lý. Nó không tự chứng minh người không có khóa không đọc được dữ liệu, không sửa được thông điệp hoặc không phát lại một thông điệp cũ.

Một phép encoding có thể đảo lại hoàn toàn cũng vượt qua test này. Hai hàm cùng mang một lỗi cũng có thể khớp nhau trong test nhưng không tương thích với đặc tả hoặc implementation độc lập.

### 3.2. Người tấn công không bị giới hạn ở thao tác bình thường

Mô hình đe dọa có thể cho phép một bên đọc nhiều ciphertext, thay một byte, đổi metadata, di chuyển bản ghi giữa tenant hoặc gửi lại một thông điệp hợp lệ. Những hành vi này không xuất hiện trong test chỉ tạo rồi đọc một bản ghi.

Vì vậy, cần xác định thuộc tính cần giữ và những đầu vào đối kháng thuộc phạm vi. Không thể dùng việc ciphertext “trông ngẫu nhiên” hoặc không đọc được bằng mắt làm bằng chứng về độ an toàn.

### 3.3. Giấu công thức không thay cho thiết kế mật mã

Một hệ thống không nên phụ thuộc duy nhất vào việc người ngoài chưa biết cách biến đổi dữ liệu. Mã nguồn, binary, traffic hoặc định dạng lưu có thể bị phân tích hoặc lộ trong vòng đời sản phẩm.

Mô hình bảo vệ cần giữ được mục tiêu khi cơ chế và định dạng đã được biết, còn những secret được thiết kế để giữ kín vẫn nằm trong phạm vi bảo vệ của chúng. Giấu implementation có thể là một lớp vận hành, không phải căn cứ duy nhất cho bảo mật mật mã.

### 3.4. Review cục bộ không tương đương phân tích mật mã

Một reviewer có thể xác nhận code sạch, không có lỗi cú pháp và gọi đúng API mà vẫn chưa đánh giá được một scheme mới. Phân tích các thuộc tính của cơ chế cần kiến thức, giả định và phạm vi khác với code review thông thường.

Do đó, OWASP khuyến cáo không dùng custom cryptographic algorithms trong ứng dụng và ưu tiên các cơ chế phù hợp đã được triển khai đáng tin cậy. [OWASP: Custom Algorithms](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html#custom-algorithms)

## 4. Bắt đầu từ mục tiêu, không bắt đầu từ tên thuật toán

### 4.1. Các mục tiêu không thể thay thế nhau

| Mục tiêu | Điều cần hỏi | Ví dụ nhầm lẫn |
| --- | --- | --- |
| Bí mật dữ liệu | Ai không được đọc plaintext? | Dùng Base64 rồi gọi là mã hóa |
| Toàn vẹn/xác thực dữ liệu | Có phát hiện thay đổi không hợp lệ không? | Chỉ mã hóa mà không có bảo đảm chống sửa |
| Nhận diện bên giao tiếp | Khóa hoặc chứng cứ được gắn với peer nào? | Coi biết cách mã hóa là đã xác định được người gửi |
| Chống phát lại | Thông điệp hợp lệ cũ có còn được chấp nhận không? | Coi tag hợp lệ là bằng chứng thông điệp còn mới |
| Kiểm chứng mật khẩu | Có tăng chi phí đoán ngoại tuyến không? | Hash nhanh một lần thay password KDF |
| Phân quyền | Chủ thể có được thực hiện hành động trên tài nguyên này không? | Coi giải mã được là đã có quyền nghiệp vụ |

Một cơ chế có thể đáp ứng nhiều mục tiêu, nhưng phải có căn cứ cho từng mục tiêu. Không gán thêm thuộc tính chỉ vì cơ chế có tên “secure”, “encrypted” hoặc “signed”.

### 4.2. Chọn scheme phù hợp thay vì tự lắp giao thức

Nếu cần bảo vệ một kênh giao tiếp, nên đánh giá giao thức kênh được hỗ trợ thay vì chỉ mã hóa body rồi tự thiết kế mọi bước xác nhận peer và lỗi.

Nếu cần một scheme mã hóa hybrid tới public key của bên nhận, có các đặc tả như HPKE mô tả sự kết hợp KEM, KDF và AEAD. Việc chọn scheme vẫn phải xét mode và mục tiêu của ứng dụng; không tự suy ra mọi mode đều xác thực người gửi. [RFC 9180: Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html)

Các ví dụ trên chỉ minh họa cách tìm một cấu trúc đã được phân tích cho đúng nhu cầu. Không có một tên scheme nào tự thay toàn bộ thiết kế hệ thống.

### 4.3. Giới hạn thuộc tính của AEAD

AEAD kết hợp bảo vệ bí mật với kiểm tra tính toàn vẹn/xác thực của dữ liệu trong phạm vi khóa và các đầu vào được chỉ định. Associated data được xác thực nhưng không được mã hóa. [RFC 5116: AEAD interface](https://www.rfc-editor.org/rfc/rfc5116.html#section-2)

Ứng dụng vẫn cần xác định khóa thuộc ai, ngữ cảnh nào được ràng buộc và có cần chống replay hay không. Một ciphertext cũ chưa bị sửa có thể vẫn vượt qua kiểm tra mật mã khi được đưa vào lại.

Các thuộc tính bổ sung như khả năng chịu nonce misuse không nên được giả định cho mọi AEAD. RFC 9771 phân biệt những thuộc tính này để tránh gán cùng một bảo đảm cho mọi thuật toán mang nhãn AEAD. [RFC 9771: Properties of AEAD Algorithms](https://www.rfc-editor.org/rfc/rfc9771.html)

## 5. Dùng cơ chế chuẩn nhưng vẫn phải giữ điều kiện sử dụng

### 5.1. Chọn đầy đủ scheme và tham số

Một yêu cầu “dùng AES” thiếu mode, tham số, quản lý khóa và xử lý lỗi. Một profile nên chỉ rõ phép bảo vệ dữ liệu được dùng, độ dài khóa theo policy, nonce/tag, định dạng và giới hạn dữ liệu.

Nếu chọn một AEAD như AES-GCM, không tự thay authentication tag bằng hash, rút ngắn tag tùy ý hoặc bỏ kiểm tra tag để tương thích với dữ liệu lỗi. Cần giữ đúng giao diện và các điều kiện của profile.

### 5.2. Khóa phải đến từ đúng nguồn và đúng mục đích

Không dùng một hằng số trong source code hoặc một giá trị do caller gửi để thay khóa sản phẩm. Quyền dùng khóa, trạng thái khóa, mục đích và phiên bản phải nằm trong hợp đồng quản lý khóa.

Việc dùng thư viện chuẩn không tự giải quyết lộ khóa hoặc cấp quyền giải mã quá rộng. Nếu một dịch vụ nhận mọi key ID từ request rồi giải mã cho mọi caller, vấn đề phân quyền vẫn tồn tại dù phép toán mật mã đúng.

### 5.3. Nonce là một điều kiện kiến trúc

Với GCM, không tái sử dụng nonce/IV cho các lần mã hóa khác nhau bằng cùng một khóa. JDK cũng nêu yêu cầu về IV khác nhau khi sử dụng lại khóa cho mã hóa GCM. [Java SE 21: Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)

Một phép kiểm tra độ dài nonce chỉ xác nhận hình dạng, không chứng minh tính duy nhất. Cần xét nhiều instance, restart, khôi phục backup và giới hạn số lần dùng khóa theo thiết kế nonce đã phê duyệt.

Không chỉ dùng thời gian hệ thống hoặc một counter cục bộ được reset ở mỗi process rồi mặc định không thể trùng. Phương án phân bổ nonce phải đáp ứng profile trên toàn phạm vi dùng chung khóa.

### 5.4. Ràng buộc ngữ cảnh khi cần

Giả sử các bản ghi thuộc tenant A và B có cùng cách mã hóa. Nếu mô hình đe dọa gồm việc chuyển ciphertext giữa bản ghi, ứng dụng có thể cần ràng buộc tenant, resource ID, loại dữ liệu hoặc phiên bản định dạng bằng associated data phù hợp.

Các byte ngữ cảnh phải được tạo từ thông tin đã xác minh và một serialization không mơ hồ. Không ghép chuỗi tùy ý rồi để các bộ ba trường khác nhau tạo cùng chuỗi byte.

Ngữ cảnh dùng để kiểm chứng cũng không được lấy nguyên từ metadata do bên gửi tự khai nếu mục tiêu là xác nhận bản ghi thuộc tài nguyên mà caller được phép truy cập. Ứng dụng cần có giá trị kỳ vọng đáng tin cậy của nó.

### 5.5. Chỉ sử dụng plaintext đã được xác thực

Luồng giải mã cần giữ nguyên điều kiện của scheme: dữ liệu không xác thực không được trở thành kết quả nghiệp vụ. Với xử lý nhiều phần hoặc streaming, không phát plaintext chưa được xác thực tới thành phần khác chỉ vì đã giải được một số byte.

Lỗi tag, sai khóa hoặc sai ngữ cảnh không được chuyển thành nhánh “thử coi input là plaintext”. Nhánh fallback đó có thể phá hủy chính mục tiêu mà mã hóa được thêm vào để bảo vệ.

## 6. Đặc tả yêu cầu bảo mật

### 6.1. Yêu cầu nền tảng

```text
REQ-CRYPTO-DESIGN-01 — Cơ chế mật mã được phê duyệt

Mọi chức năng mật mã bảo vệ dữ liệu sản phẩm phải sử dụng scheme/profile
đã được đánh giá cho mục tiêu và mô hình đe dọa tương ứng, qua implementation
được phê duyệt và còn trong phạm vi duy trì của hệ thống.

Không dùng thuật toán tự sáng tác, bản sửa primitive hoặc tổ hợp mật mã
mới do nhóm ứng dụng tự ghép để thay cơ chế này trong đường xử lý sản phẩm.

Code tích hợp phải giữ các điều kiện về khóa, nonce, tham số, ngữ cảnh,
kiểm tra xác thực và giới hạn sử dụng của profile. Lỗi không được tạo
nhánh bỏ bảo vệ hoặc tự chuyển sang cơ chế ngoài tập cho phép.
```

### 6.2. Những yêu cầu tạo bằng chứng cụ thể

| Mã | Nội dung yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-CRYPTO-DESIGN-02 | Mỗi use case phải nêu thuộc tính cần đạt và scheme đáp ứng thuộc tính đó | Mô hình đe dọa và quyết định thiết kế |
| REQ-CRYPTO-DESIGN-03 | Thuật toán/profile được chọn từ registry hữu hạn do hệ thống kiểm soát | Registry và luồng chọn implementation |
| REQ-CRYPTO-DESIGN-04 | Tham số ảnh hưởng bảo mật phải được ghi rõ và phiên bản hóa | Profile, metadata và cấu hình có hiệu lực |
| REQ-CRYPTO-DESIGN-05 | Nguồn khóa, quyền sử dụng và nonce phải đáp ứng profile trong toàn bộ topology | Quản lý khóa, phân bổ nonce và các tình huống cạnh tranh |
| REQ-CRYPTO-DESIGN-06 | Dữ liệu không xác thực không được phát ra như plaintext hợp lệ | Các trường hợp sửa ciphertext, tag hoặc ngữ cảnh |
| REQ-CRYPTO-DESIGN-07 | Các thuộc tính không do scheme cung cấp phải có cơ chế riêng nếu use case yêu cầu | Quyết định về replay, peer identity và authorization |
| REQ-CRYPTO-DESIGN-08 | Thay thuật toán, thư viện, provider hoặc định dạng phải được đánh giá theo phạm vi thay đổi | Hồ sơ thay đổi và kết quả tương thích |
| REQ-CRYPTO-DESIGN-09 | Không có fallback tự động sang plaintext hoặc profile yếu ngoài policy | Luồng lỗi và các trường hợp thiếu khả năng |

Các yêu cầu này không bắt đội sản phẩm tự chứng minh lại độ an toàn của một primitive chuẩn. Chúng yêu cầu dùng đúng cơ chế đã chọn và cung cấp bằng chứng cho phần trách nhiệm tích hợp mà hệ thống thực sự nắm giữ.

## 7. Ví dụ Java: gọi implementation thay vì viết thuật toán

### 7.1. Profile minh họa

Ví dụ chọn một profile AES-GCM cố định, nonce 12 byte, authentication tag 128 bit và tối đa 1 MiB plaintext cho mỗi lần gọi. Các con số là lựa chọn của profile minh họa, không phải ngưỡng áp dụng cho mọi sản phẩm.

Khóa phải được lấy từ thành phần quản lý khóa theo đúng quyền và mục đích. Nonce cho mỗi lần mã hóa phải được cung cấp từ cơ chế đáp ứng yêu cầu của profile trên toàn phạm vi dùng chung khóa; lớp dưới đây chỉ kiểm tra độ dài, không bảo đảm điều kiện duy nhất.

```java
import java.security.GeneralSecurityException;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadLibraryExample {

    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int MAX_PLAINTEXT_BYTES = 1_048_576;

    private AeadLibraryExample() {
    }

    public static byte[] seal(
            SecretKey key,
            byte[] uniqueNonce,
            byte[] context,
            byte[] plaintext) throws GeneralSecurityException {

        Objects.requireNonNull(plaintext, "plaintext");
        if (plaintext.length > MAX_PLAINTEXT_BYTES) {
            throw new GeneralSecurityException("Input exceeds profile limit");
        }

        return run(Cipher.ENCRYPT_MODE, key, uniqueNonce, context, plaintext);
    }

    public static byte[] open(
            SecretKey key,
            byte[] nonce,
            byte[] expectedContext,
            byte[] ciphertextAndTag) throws GeneralSecurityException {

        Objects.requireNonNull(ciphertextAndTag, "ciphertextAndTag");
        if (ciphertextAndTag.length < TAG_BYTES
                || ciphertextAndTag.length
                        > MAX_PLAINTEXT_BYTES + TAG_BYTES) {
            throw new GeneralSecurityException("Invalid envelope size");
        }

        return run(
                Cipher.DECRYPT_MODE,
                key,
                nonce,
                expectedContext,
                ciphertextAndTag);
    }

    private static byte[] run(
            int mode,
            SecretKey key,
            byte[] nonce,
            byte[] context,
            byte[] input) throws GeneralSecurityException {

        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(nonce, "nonce");
        Objects.requireNonNull(context, "context");

        if (nonce.length != NONCE_BYTES) {
            throw new GeneralSecurityException("Invalid nonce size");
        }

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(mode, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(context);
        return cipher.doFinal(input);
    }
}
```

`GCMParameterSpec` nhận độ dài tag theo bit và IV/nonce theo mảng byte. Code không tự tính tag, tự triển khai AES hoặc thay cấu trúc GCM. [Java SE 21: GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)

### 7.2. Những ràng buộc được thể hiện trong code

Transformation được chọn bởi hằng số của profile, không lấy từ trường `algorithm` do caller gửi. Kích thước đầu vào và nonce được kiểm tra trước khi thực hiện phép toán.

AAD được cung cấp trước khi xử lý dữ liệu. Với API GCM của JDK, kết quả mã hóa mang tag để đường giải mã kiểm tra; không cần ứng dụng tự tạo thêm một hash thay thế. [Java SE 21: Cipher, AEAD](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)

Hàm `open` chỉ trả dữ liệu nếu `doFinal` hoàn tất. Khi không kiểm chứng được authentication tag, API AEAD có thể phát sinh `AEADBadTagException`; lớp tích hợp phải xử lý như dữ liệu không được chấp nhận, không biến thành plaintext hợp lệ. [Java SE 21: AEADBadTagException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/AEADBadTagException.html)

### 7.3. Những điều code chưa chứng minh

Lớp minh họa không cấp quyền dùng khóa, không tạo nonce và không lưu key ID hoặc envelope. Nó cũng không cung cấp xác thực người gửi, chống phát lại, audit hoặc migration.

Nếu caller truyền lại cùng nonce cho hai lần mã hóa bằng cùng khóa, code vẫn có thể chạy nhưng thiết kế đã vi phạm điều kiện quan trọng. Đây là lý do phải kiểm chứng luồng tích hợp, không chỉ đọc tên thuật toán và độ dài mảng.

`expectedContext` cần đến từ một ngữ cảnh đã xác minh của ứng dụng và đúng cách serialization của profile. Nếu lấy nó từ dữ liệu tự khai mà không đối chiếu, ứng dụng có thể vẫn chấp nhận một bản ghi bị chuyển sai phạm vi dù tag của bản ghi đó hợp lệ.

Tên `NoPadding` trong transformation này không phải chỉ thị bỏ kiểm tra tag. Không tự thêm padding hoặc đổi mode để “sửa” dữ liệu không giải mã được; cần giữ đúng profile và xác định nguyên nhân lỗi.

### 7.4. Không dùng wrapper như bằng chứng thay cho cả thiết kế

Một wrapper tập trung có thể giảm số nơi được tự chọn thuật toán và thống nhất hành vi lỗi. Tuy nhiên, việc wrapper gọi đúng thư viện chỉ là một phần của bằng chứng.

Ứng dụng phải chứng minh những đầu vào mà wrapper phụ thuộc thực sự đáp ứng hợp đồng: khóa đúng, nonce phù hợp, ngữ cảnh đúng và caller đã được cấp quyền. Thư viện không thể tự suy ra các điều kiện nghiệp vụ mà nó không biết.

## 8. Định dạng ứng dụng và ranh giới với scheme tự chế

### 8.1. Có thể cần một envelope dữ liệu

Một hệ thống lưu tài liệu có thể cần metadata như:

```text
profileId
formatVersion
keyId
nonce
ciphertextAndTag
```

Việc lưu các trường này không tự đồng nghĩa phát minh thuật toán. Điều cần đánh giá là ý nghĩa từng trường, cách chọn khóa, cách ràng buộc metadata và giới hạn parser có giữ đúng bảo đảm của scheme hay không.

Nếu đã có định dạng hoặc giao thức phù hợp với use case, nên đánh giá việc dùng implementation của nó thay vì tạo thêm một định dạng khó liên thông. Nếu cần envelope ứng dụng riêng, phải giữ nó ở vai trò đóng gói và phiên bản hóa, không tự thêm phép biến đổi mật mã chưa được đánh giá.

### 8.2. Không cho envelope tự quyết định mức bảo vệ

Trường `profileId` trong dữ liệu giúp chọn một profile đã biết, không phải quyền yêu cầu mọi thuật toán mà provider có thể thực hiện. Registry cần giới hạn profile nào được ghi mới, profile nào chỉ được đọc trong giai đoạn chuyển đổi và profile nào bị từ chối.

Không chuyển thẳng chuỗi từ envelope vào một API như `Cipher.getInstance` rồi coi provider sẽ tự quyết định cơ chế có phù hợp sản phẩm không. Khả năng triển khai một thuật toán không đồng nghĩa thuật toán đó được phép cho use case này.

### 8.3. Đối chiếu metadata với ngữ cảnh kỳ vọng

Key ID phải được phân giải trong phạm vi khóa mà dịch vụ và caller được phép sử dụng. Resource ID hoặc tenant trong metadata cần được đối chiếu với yêu cầu nghiệp vụ, không tự tạo quyền đọc.

Nếu version hoặc loại tài liệu tham gia quyết định cách diễn giải plaintext, cần xác định cách bảo vệ những thông tin đó trong profile. Một trường ảnh hưởng ngữ nghĩa không nên bị coi là vô hại chỉ vì nó nằm ngoài ciphertext.

### 8.4. Chống phát lại là một yêu cầu riêng

Một tag hợp lệ chứng minh điều kiện mật mã của bộ đầu vào, không chứng minh thông điệp chưa từng được xử lý. Nếu yêu cầu chỉ cho thực hiện một lần, cần cơ chế như message ID và trạng thái xử lý được thiết kế phù hợp.

Timestamp cũng không tự ngăn được phát lại trong cửa sổ còn hợp lệ. Điều kiện freshness, cơ chế lưu trạng thái và tính nhất quán giữa các instance cần được đặc tả riêng, thay vì tự thêm một trường thời gian rồi tuyên bố giao thức đã chống replay.

## 9. Quy trình lựa chọn và thay đổi cơ chế

### 9.1. Hồ sơ quyết định tối thiểu

Một quyết định mật mã nên trả lời:

1. Dữ liệu và tác nhân nào nằm trong mô hình đe dọa?
2. Cần bí mật, toàn vẹn, nhận diện peer, chống replay hay thuộc tính nào khác?
3. Scheme/profile nào cung cấp phần thuộc tính cần dùng và trong điều kiện gì?
4. Implementation, phiên bản và provider nào được dùng?
5. Ai kiểm soát khóa, nonce, tham số và ngữ cảnh?
6. Dữ liệu lỗi, cơ chế không khả dụng và phiên bản cũ được xử lý thế nào?
7. Bằng chứng nào xác nhận phần implementation và tích hợp của hệ thống?

Không thay hồ sơ bằng một câu “đã dùng thuật toán mạnh”. Những trường chưa được trả lời thường là nơi nhóm ứng dụng vô tình tự thiết kế phần còn thiếu.

### 9.2. Thư viện cần có nguồn và vòng đời rõ

Cần xác định nguồn dependency, phiên bản được triển khai, khả năng cập nhật và phạm vi API được dùng. Một đoạn code lấy từ bài viết, công cụ sinh mã hoặc kho không được duy trì không tự trở thành một implementation có bằng chứng phù hợp.

Nếu implementation có ràng buộc provider, phần cứng hoặc môi trường, hồ sơ triển khai phải ghi đúng chúng. Không suy ra mọi bản build có cùng thuộc tính chỉ vì cùng tên thuật toán.

Không sửa mã lõi mật mã của thư viện để chữa lỗi tương thích hoặc làm nhanh hơn mà không đánh giá lại thay đổi. Nếu vấn đề nằm ở encoding, key ID hoặc định dạng dữ liệu, cần sửa ở đúng ranh giới đó.

### 9.3. Crypto agility không phải tự động chấp nhận mọi thuật toán

Agility là khả năng chuyển đổi có kiểm soát khi policy thay đổi, không phải mở một trường cho caller chọn bất kỳ cơ chế nào. Tập ghi mới và tập đọc cũ cần được quản lý độc lập.

Kế hoạch chuyển đổi phải xác định cách nhận diện profile, đọc dữ liệu cũ, tạo dữ liệu mới, giữ hoặc kết thúc khả năng dùng khóa cũ và kiểm chứng sau migration.

Khi một cơ chế không còn được phép, lỗi giải mã không được kích hoạt nhánh thử lần lượt mọi profile yếu hơn. Việc tương thích phải dựa vào metadata đã kiểm tra và policy, không dựa vào “cách nào đọc được thì dùng”.

### 9.4. Nếu chưa có cơ chế phù hợp

Cần thu hẹp hoặc làm rõ yêu cầu, đánh giá scheme hiện có, xem lại kiến trúc và tìm đánh giá chuyên môn cho phần còn thiếu. Không nên lấp khoảng trống bằng một công thức tự tạo rồi chỉ thêm chú thích cảnh báo.

Một hoạt động nghiên cứu có thể có mục tiêu khác, nhưng phải được tách khỏi đường bảo vệ dữ liệu sản phẩm. Các điều kiện để chuyển một kết quả nghiên cứu sang triển khai cần được xác định riêng; test chức năng của nhóm ứng dụng không tự cấp điều kiện đó.

## 10. Ma trận nghiệm thu

### 10.1. Kiểm chứng thuộc tính thay vì chỉ kiểm chứng round-trip

| Tình huống | Kỳ vọng theo profile mẫu | Bằng chứng |
| --- | --- | --- |
| Dữ liệu hợp lệ, khóa và ngữ cảnh đúng | Khôi phục đúng plaintext | Kết quả tương thích và profile |
| Sửa ciphertext hoặc tag | Không trả plaintext hợp lệ | Lỗi xác thực và không tạo tác động nghiệp vụ từ dữ liệu đó |
| Sai key hoặc expected context | Không chấp nhận dữ liệu | Kết quả kiểm chứng và phạm vi sử dụng khóa |
| Nonce sai kích thước hoặc dữ liệu quá lớn | Từ chối theo giới hạn trước phép tính không cần thiết | Nhánh kiểm tra và tài nguyên sử dụng |
| Đường mã hóa nhiều instance | Giữ yêu cầu nonce theo cùng khóa và giới hạn sử dụng | Thiết kế phân bổ, cạnh tranh, restart và phục hồi |
| Profile không biết hoặc không được phép | Không tự chọn transformation khác | Registry và luồng lỗi |
| Provider hoặc key service lỗi | Không lưu plaintext hoặc giảm bảo vệ để tiếp tục | Tác động dữ liệu và phản hồi lỗi |
| Di chuyển bản ghi sang tenant/resource khác | Bị chặn khi use case yêu cầu ràng buộc phạm vi | Context kỳ vọng và authorization |
| Gửi lại thông điệp hợp lệ | Theo đúng policy replay riêng | Trạng thái nghiệp vụ, không chỉ tag |
| Dữ liệu cũ sau nâng cấp | Chỉ đọc trong phạm vi profile cũ còn được phép | Migration và kế hoạch kết thúc |

Không phải mọi dòng đều được giải quyết bởi thuật toán. Ma trận cho biết phần nào do scheme, phần nào do registry, quản lý khóa hoặc logic nghiệp vụ phải cung cấp.

### 10.2. Dùng test vector và kiểm chứng độc lập đúng vai trò

Test vector công bố cho thuật toán hoặc scheme giúp kiểm tra kết quả triển khai so với giá trị độc lập. Kiểm chứng tương thích với một implementation khác có thể phát hiện những lỗi mà hai hàm cùng tự viết không thấy.

Tuy nhiên, việc vượt qua test vector không chứng minh không có lỗi kênh bên, không chứng minh quản lý khóa đúng hoặc chứng minh toàn bộ giao thức tự ghép an toàn. Đây là bằng chứng có phạm vi, không phải giấy phép tạo một scheme mới.

### 10.3. Kiểm chứng xử lý dữ liệu không xác thực

```text
Given:
  Một bản ghi được tạo bằng profile AEAD được phê duyệt.
  Dịch vụ chỉ được dùng plaintext sau khi xác thực dữ liệu thành công.

When:
  Bản ghi bị thay ciphertext, tag hoặc phần ngữ cảnh được bảo vệ.

Then:
  Không có plaintext được phát ra như kết quả hợp lệ.
  Không có sự kiện hoặc cập nhật nghiệp vụ dựa trên dữ liệu chưa xác thực.
  Không có nhánh chuyển input thành plaintext hoặc bỏ kiểm tra tag.
  Lỗi được quan sát theo policy mà không lộ khóa hoặc nội dung nhạy cảm.
```

### 10.4. Kiểm chứng nonce không chỉ bằng một tập mẫu

Tạo nhiều nonce mà không thấy trùng là một kiểm tra hữu ích, nhưng không chứng minh điều kiện duy nhất trên toàn vòng đời khóa. Cần xem nguồn trạng thái, phân chia giữa instance, các điều kiện cấp lại và hành vi sau khôi phục.

Nếu profile dùng phương án ngẫu nhiên được phê duyệt, phải xét nguồn ngẫu nhiên và giới hạn số lần dùng khóa của phương án đó. Nếu dùng trạng thái, phải xét cách tránh cấp lại cùng không gian nonce sau restart hoặc restore.

### 10.5. Bằng chứng inventory và thay đổi

Danh mục điểm sử dụng mật mã nên chỉ được thành phần gọi, profile, implementation và khóa/nguồn khóa theo vai trò. Nó giúp tìm các đường gọi trực tiếp provider hoặc đoạn code tự tạo nằm ngoài wrapper đã phê duyệt.

Không dựa duy nhất vào việc tìm một tên thuật toán trong source. Logic tự biến đổi dữ liệu hoặc giao thức riêng có thể không dùng từ “crypto”, còn một tên thuật toán xuất hiện có thể chỉ là dữ liệu kiểm thử.

## 11. Những lập luận không đủ để cấp quyền dùng custom crypto

### 11.1. “Thuật toán của mình chưa ai biết”

Đó là một giả định về khả năng tiếp cận, không phải bằng chứng về thuộc tính của cơ chế. Ranh giới bảo vệ không nên sụp đổ chỉ vì cách biến đổi được công khai.

### 11.2. “Đã mã hóa hai lần nên mạnh hơn”

Số lớp không tự tạo bảo đảm tốt hơn. Cách dùng khóa, nonce, thứ tự xác thực, lỗi và giới hạn sử dụng đều có thể làm tổ hợp yếu hoặc khó kiểm chứng hơn.

### 11.3. “Có AES và SHA nên chắc chắn an toàn”

Tên primitive không chứng minh scheme. Một hash không có khóa không tự đóng vai trò MAC, và một block cipher không tự xác thực peer hoặc chống phát lại.

### 11.4. “Thư viện cho phép nên policy cũng cho phép”

Provider có thể hỗ trợ nhiều cơ chế để tương thích. Tập được phép dùng cho dữ liệu mới của hệ thống phải do policy quyết định.

### 11.5. “Chỉ là wrapper nên không cần review”

Wrapper có thể chọn sai profile, cấp lại nonce, dùng sai context hoặc xử lý lỗi không đúng. Nó không tự viết primitive nhưng vẫn là một phần quan trọng của đường bảo vệ.

### 11.6. “Không thấy ai khai thác nghĩa là đủ an toàn”

Thiếu quan sát không xác nhận độ an toàn mật mã. Cần cơ chế có căn cứ phân tích và bằng chứng tích hợp đúng, không đợi xuất hiện sự cố mới đánh giá thiết kế.

## 12. Hồ sơ yêu cầu mẫu

```text
Use case:
  Bảo vệ nội dung yêu cầu bảo mật được lưu theo tenant và resource.

Thuộc tính:
  Bí mật nội dung với bên không có quyền dùng khóa.
  Phát hiện sửa dữ liệu và chuyển ngữ cảnh ngoài hợp đồng.
  Quyền đọc và yêu cầu freshness được kiểm tra độc lập khi cần.

Thiết kế:
  Scheme/profile AEAD đã phê duyệt qua implementation được duy trì.
  Không sửa primitive, không tự tạo mode, tag hoặc giao thức mật mã mới.
  Khóa từ nguồn được quản lý; nonce đáp ứng profile trên toàn phạm vi khóa.
  Context được tạo từ dữ liệu kỳ vọng đã xác minh và serialization rõ ràng.

Định dạng và vòng đời:
  Profile ID, key ID và format version có registry hữu hạn.
  Tập ghi mới, đọc cũ và từ chối được phân biệt.
  Migration, rotation, backup và xử lý lỗi có hợp đồng cụ thể.

Bằng chứng:
  Quyết định thiết kế, nguồn implementation, profile có hiệu lực,
  test vector/tương thích, sửa dữ liệu, sai context, nonce, lỗi provider
  và việc không có plaintext hoặc tác động nghiệp vụ khi xác thực thất bại.
```

Nguyên tắc không tự phát minh thuật toán đạt mục tiêu khi nhóm ứng dụng dùng một cơ chế có căn cứ cho đúng nhu cầu và giữ được các điều kiện của nó trong triển khai. Yêu cầu bảo mật phải kiểm soát cả việc lựa chọn scheme lẫn cách tích hợp, để một tên thuật toán chuẩn không che khuất một thiết kế tự ghép chưa được kiểm chứng.
