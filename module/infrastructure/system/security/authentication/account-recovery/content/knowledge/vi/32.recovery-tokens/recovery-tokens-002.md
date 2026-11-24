# Recovery token format

## 1. Định dạng token là hợp đồng bảo mật, không chỉ là kiểu chuỗi

Trong khôi phục tài khoản, recovery token là dữ liệu được cấp để chứng minh quyền thực hiện một bước xác định của quy trình. Tùy thiết kế, bước đó có thể là mở một phiên khôi phục hạn chế, xác nhận một kênh đã thiết lập hoặc hoàn tất thao tác đặt lại mật khẩu.

Nếu token hoạt động theo cơ chế **bearer**, người nắm được token có thể sử dụng quyền mà máy chủ gắn với nó, trong phạm vi các điều kiện còn lại. Đối phương không cần hiểu cấu trúc bên trong để dùng một token bị lộ.

Vì vậy, lựa chọn định dạng cần trả lời được các câu hỏi:

- Phần nào là bí mật không thể đoán trước?
- Dữ liệu được biểu diễn bằng bảng chữ cái và quy tắc nào?
- Máy chủ nhận biết phiên bản và loại token ra sao?
- Cách tra cứu, hết hạn, thu hồi và chống dùng lặp được thực hiện ở đâu?
- Token được phép dùng cho tài khoản, case và thao tác nào?

OWASP nêu những nguyên tắc cốt lõi cho token đặt lại mật khẩu: sinh bằng bộ sinh ngẫu nhiên mật mã, đủ khó đoán, lưu an toàn, dùng một lần và hết hạn sau thời gian phù hợp. Định dạng phải hỗ trợ các nguyên tắc đó, nhưng không tự thực hiện tất cả. [Nguồn: OWASP, Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Trong module khôi phục tài khoản, một token đặt lại mật khẩu không mặc nhiên là quyền bỏ MFA hoặc thêm passkey. Những thao tác có tác động khác nhau cần được máy chủ phân biệt bằng mục đích và chính sách.

Bài học sử dụng một định dạng opaque minh họa:

```text
rt1.<secret>
```

`rt1.` là tiền tố phiên bản công khai. `<secret>` là phần bí mật sinh ngẫu nhiên. Đây là quy ước thiết kế của bài, không phải tên hay định dạng chuẩn do một RFC quy định.

## 2. Tách bí mật, biểu diễn và trạng thái sử dụng

Một token an toàn thường liên quan đến ba lớp độc lập.

| Lớp | Vai trò | Điều lớp này không tự bảo đảm |
| --- | --- | --- |
| Bí mật ngẫu nhiên | Làm việc đoán token trở nên khó | Token không bị rò rỉ hoặc dùng lại |
| Biểu diễn văn bản | Cho phép vận chuyển qua URL, JSON hoặc giao diện | Tính bí mật, tính xác thực hoặc quyền sử dụng |
| Bản ghi hoặc cơ chế kiểm soát ở máy chủ | Ràng buộc mục đích, chủ thể, thời hạn và vòng đời | Chất lượng ngẫu nhiên của token được phát |

Base64url là cách **mã hóa biểu diễn**, không phải mã hóa bảo mật. Chuyển một email và timestamp sang Base64url không biến chúng thành bí mật mạnh.

Tương tự, băm dữ liệu dự đoán được rồi dùng kết quả làm token không tự tạo thêm entropy. Nếu đầu vào chỉ gồm ID tài khoản và thời gian gần hiện tại, đối phương vẫn có thể thử các đầu vào khả dĩ.

Tiền tố, dấu phân cách, timestamp công khai, checksum và ID tra cứu không nên được tính như phần bí mật chống đoán. Có thêm nhiều ký tự không đồng nghĩa có thêm nhiều bit ngẫu nhiên.

Không nhầm các thuộc tính sau:

```text
Đúng cú pháp
    không đồng nghĩa với
Được máy chủ phát hành
    không đồng nghĩa với
Còn hiệu lực và chưa dùng
    không đồng nghĩa với
Đủ quyền cho thao tác đang yêu cầu
```

## 3. Chọn độ dài từ entropy trước khi chọn số ký tự

Nếu sinh `b` byte ngẫu nhiên phân bố đều và không dự đoán được, phần bí mật có `8 × b` bit ngẫu nhiên. Khi mã hóa nguyên vẹn, đổi từ byte sang hex hoặc Base64url không tạo thêm entropy.

Bảng sau chỉ tính phần bí mật, chưa tính tiền tố:

| Byte ngẫu nhiên | Bit ngẫu nhiên | Số ký tự hex | Số ký tự Base64url không padding |
| --- | --- | --- | --- |
| 16 | 128 | 32 | 22 |
| 24 | 192 | 48 | 32 |
| 32 | 256 | 64 | 43 |

Với `b` byte, số ký tự hex là `2b`. Số ký tự Base64url không padding là `ceil(8b / 6)`.

Điểm dễ nhầm là 43 ký tự Base64url từ 32 byte **không chứa 258 bit ngẫu nhiên**. Các bit không dùng ở ký tự cuối chịu ràng buộc của phép mã hóa; nguồn ban đầu vẫn chỉ có 256 bit.

Trong mô hình đơn giản, một token mục tiêu có `n` bit bí mật đều nhau và `G` lần đoán cho xác suất trúng không vượt quá `G / 2^n`, với giả định đối phương không có thông tin bổ sung. Đây là cách nhìn về đoán bí mật, không phải số đo toàn bộ nguy cơ chiếm tài khoản.

Nếu endpoint chấp nhận bất kỳ token nào trong một tập lớn token còn hiệu lực, tập mục tiêu rộng hơn so với chỉ một token. Nếu token bị đánh cắp, độ dài gần như không giúp ngăn sử dụng nó. Vì vậy vẫn cần hạn mức, thời hạn, bảo vệ kênh gửi và kiểm soát vòng đời.

Không chọn độ dài chỉ bằng cảm giác “chuỗi này trông phức tạp”. Cũng không cắt chuỗi ngẫu nhiên cho vừa một cột cơ sở dữ liệu mà không đánh giá lại lượng bí mật còn lại.

Mẫu trong bài chọn 32 byte ngẫu nhiên, biểu diễn thành 43 ký tự Base64url. Đây là lựa chọn minh họa cho token liên kết có entropy cao, không phải độ dài bắt buộc cho mọi mã khôi phục nhập tay.

## 4. So sánh các cấu trúc token thường gặp

| Cấu trúc | Cách hiểu | Điểm cần chú ý |
| --- | --- | --- |
| Opaque secret | Chuỗi bí mật trỏ tới bản ghi máy chủ | Đơn giản về dữ liệu phía client; vẫn cần trạng thái vòng đời |
| Selector và secret | Một phần chọn bản ghi, một phần chứng minh quyền | Selector không thay thế phần bí mật |
| Token có chữ ký như JWT | Mang claims được bảo vệ tính toàn vẹn bằng cơ chế mật mã | Có chữ ký không có nghĩa được giữ bí mật hoặc tự dùng một lần |
| Mã ngắn nhập tay | Chuỗi thuận tiện cho người dùng đọc và nhập | Không gian đoán nhỏ hơn; cần hạn mức và ràng buộc phù hợp |

### 4.1. Opaque token

Với dạng `rt1.<secret>`, client không cần đọc subject, thời hạn hoặc purpose từ token. Máy chủ tra cứu bản ghi bằng digest hoặc một cơ chế phù hợp rồi quyết định quyền.

Lợi ích là không phải đưa dữ liệu tài khoản vào URL. Tuy nhiên, “opaque” không có nghĩa token không nhạy cảm. Toàn bộ chuỗi vẫn là bí mật bearer trong thiết kế này.

### 4.2. Selector và secret

Một cấu trúc khác có thể là:

```text
rt1.<selector>.<secret>
```

Selector được dùng để tìm bản ghi, còn secret được đối chiếu với giá trị bảo vệ ở máy chủ. Phải giới hạn và kiểm tra cả hai phần.

Nếu selector là ID công khai, độ an toàn chống giả mạo vẫn phải dựa vào secret. Không cộng số bit của một selector đã lộ vào entropy bí mật.

Mô hình selector cũng cần tránh lỗi phân quyền: tìm được bản ghi không có nghĩa được phép dùng nó cho bất kỳ tài khoản hay purpose nào. Không tin subject mà client gửi bên cạnh token để thay đổi quan hệ đã được máy chủ thiết lập.

### 4.3. JWT hoặc token tự chứa dữ liệu

JWT ký thông thường không che nội dung claims. Đưa email, thông tin định danh hoặc chi tiết case vào payload có thể làm lộ dữ liệu cho bất kỳ ai nhận được chuỗi.

Nếu sử dụng JWT, cần có bộ quy tắc xác minh rõ ràng: thuật toán được chấp nhận, khóa tin cậy, issuer, audience, thời gian và loại token. RFC 8725 khuyến nghị phân biệt loại JWT và dùng các quy tắc xác minh loại trừ việc nhận nhầm token của luồng khác. [Nguồn: RFC 8725, Explicit Typing và Validation Rules](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.11).

Dù chữ ký còn hợp lệ và `exp` chưa đến, một token đã dùng hoặc bị thu hồi vẫn cần bị từ chối. `jti` chỉ là định danh nếu hệ thống không theo dõi và thi hành trạng thái liên quan. Tính tự chứa không tự giải quyết yêu cầu dùng một lần.

Mã hóa payload có thể bảo vệ nội dung theo mô hình mật mã được chọn, nhưng người đánh cắp toàn bộ token vẫn có thể giữ một bearer credential. Bảo mật nội dung và chống sử dụng token bị lộ là hai yêu cầu khác nhau.

### 4.4. Mã ngắn không phải phiên bản cắt bớt tùy ý

Một mã sáu chữ số có một triệu giá trị có thể xảy ra khi sinh đều. Nó không tương đương token 32 byte chỉ vì đều là “mã khôi phục”.

Nếu phải hỗ trợ nhập tay, thiết kế riêng bảng chữ cái, chiều dài, giới hạn số lượt, thời hạn và quan hệ với case. Định dạng hiển thị theo nhóm có thể giúp nhập, nhưng dấu cách hoặc dấu gạch nhóm không tạo thêm bí mật.

Checksum có thể giúp phát hiện nhập sai; đối phương cũng có thể tính checksum. Không tính nó như một lớp xác thực mật mã.

## 5. Đặc tả rõ một định dạng canonical

Với mẫu `rt1.<secret>`, có thể xác định hợp đồng như sau:

| Thuộc tính | Quy định minh họa |
| --- | --- |
| Tiền tố | Chính xác `rt1.`, phân biệt hoa thường |
| Nguồn bí mật | 32 byte từ bộ sinh ngẫu nhiên mật mã |
| Biểu diễn | Base64url không padding |
| Bảng chữ cái secret | `A-Z`, `a-z`, `0-9`, `-` và `_` |
| Chiều dài secret | Chính xác 43 ký tự ASCII |
| Chiều dài toàn token | Chính xác 47 ký tự ASCII |
| Khoảng trắng | Không cho phép ở đầu, cuối hoặc bên trong |
| Padding | Không chấp nhận `=` trong profile này |
| Dạng biểu diễn | Phải khớp kết quả mã hóa lại sau khi giải mã |

RFC 4648 mô tả bảng chữ cái Base64url và vấn đề biểu diễn canonical. Một số chuỗi khác nhau có thể giải mã thành cùng byte nếu bộ giải mã chấp nhận các bit đệm không đúng quy tắc. Bài này chọn yêu cầu biểu diễn duy nhất bằng bước giải mã rồi mã hóa lại. [Nguồn: RFC 4648, Canonical Encoding và Base64url](https://www.rfc-editor.org/rfc/rfc4648.html#section-3.5).

Các lựa chọn ở bảng là **profile của ứng dụng**. Không suy ra rằng mọi chuỗi Base64url hợp lệ theo một giao thức khác đều phải bị xử lý giống hệt.

Một biểu thức như `[A-Za-z0-9_-]{43}` chỉ kiểm tra bảng chữ cái và độ dài. Nó chưa chứng minh chuỗi giải mã thành đúng số byte hoặc có dạng canonical.

Không sửa token để “giúp người dùng” bằng cách:

- Đổi toàn bộ sang chữ thường.
- Thay `O` thành `0` hoặc `l` thành `1`.
- Xóa mọi ký tự không thuộc bảng chữ cái.
- Cắt phần đuôi khi chuỗi dài hơn giới hạn.
- Tự nhận cả hex, Base64 thường và Base64url trên cùng một parser mà không có phiên bản rõ ràng.

Với secret Base64url phân biệt hoa thường, các phép sửa đó có thể đổi credential. Nếu muốn có định dạng thuận tiện cho nhập tay, cần thiết kế profile riêng ngay từ đầu.

Ở lớp HTTP, URL hoặc JSON được giải mã theo quy tắc vận chuyển tương ứng trước khi chuyển chuỗi vào parser token. Không tiếp tục URL-decode lặp lại bên trong parser để chấp nhận một dạng đầu vào khác dự kiến.

## 6. Ví dụ Java: sinh, kiểm tra định dạng và tạo digest

Ví dụ dưới dùng các API của Java để hiện thực profile minh họa. Nó chỉ xử lý định dạng và digest phục vụ tra cứu; không phải toàn bộ dịch vụ khôi phục.

`SecureRandom.nextBytes()` cung cấp byte ngẫu nhiên cho mục đích bảo mật theo provider của runtime. Java cũng có encoder và decoder Base64url trong `java.util.Base64`. [Nguồn: Java SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html), [Java Base64](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html).

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.regex.Pattern;

public final class RecoveryTokenFormat {

    private static final String PREFIX = "rt1.";
    private static final int SECRET_BYTES = 32;
    private static final int SECRET_CHARS = 43;
    private static final int TOKEN_CHARS = PREFIX.length() + SECRET_CHARS;

    private static final SecureRandom RANDOM = new SecureRandom();

    private static final Base64.Encoder ENCODER =
        Base64.getUrlEncoder().withoutPadding();

    private static final Base64.Decoder DECODER =
        Base64.getUrlDecoder();

    private static final Pattern SECRET_PATTERN =
        Pattern.compile("[A-Za-z0-9_-]{43}");

    private RecoveryTokenFormat() {
    }

    public static String issue() {
        byte[] secret = new byte[SECRET_BYTES];
        RANDOM.nextBytes(secret);
        return PREFIX + ENCODER.encodeToString(secret);
    }

    public static void requireCanonicalFormat(String token) {
        if (token == null
                || token.length() != TOKEN_CHARS
                || !token.startsWith(PREFIX)) {
            throw invalidFormat();
        }

        String encoded = token.substring(PREFIX.length());

        if (!SECRET_PATTERN.matcher(encoded).matches()) {
            throw invalidFormat();
        }

        final byte[] decoded;
        try {
            decoded = DECODER.decode(encoded);
        } catch (IllegalArgumentException ex) {
            throw invalidFormat();
        }

        if (decoded.length != SECRET_BYTES
                || !ENCODER.encodeToString(decoded).equals(encoded)) {
            throw invalidFormat();
        }
    }

    public static byte[] digestForLookup(String token) {
        requireCanonicalFormat(token);

        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");

            // Fixed domain separator, followed by a zero byte.
            digest.update(
                "account-recovery-token".getBytes(StandardCharsets.US_ASCII)
            );
            digest.update((byte) 0);

            return digest.digest(token.getBytes(StandardCharsets.US_ASCII));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }

    private static IllegalArgumentException invalidFormat() {
        return new IllegalArgumentException("Invalid recovery token format");
    }
}
```

### Những lựa chọn của ví dụ

**Sinh byte trước, mã hóa sau.** Chương trình không chọn ký tự bằng bộ sinh ngẫu nhiên thông thường và không tự seed bằng thời gian hiện tại. Không thay `SecureRandom` bằng `Random` hoặc `ThreadLocalRandom` để tối ưu mà bỏ qua mục đích bảo mật.

**Kiểm tra chiều dài trước khi giải mã.** Parser không nhận một đầu vào tùy ý dài rồi cấp phát bộ nhớ để giải mã nó.

**Không dùng MIME decoder.** Định dạng token không cho phép xuống dòng hoặc ký tự bị bỏ qua âm thầm. Profile phải được giữ nhất quán giữa nơi phát và nơi kiểm tra.

**Mã hóa lại để kiểm tra canonical.** Cùng một byte secret không được nhận dưới nhiều chuỗi biểu diễn khác nhau trong profile này. Điều đó giúp tránh mâu thuẫn giữa lớp tra cứu, giới hạn lượt và chống phát lại.

**Digest có phân tách miền sử dụng.** Chuỗi cố định và byte phân cách xác định namespace của phép băm. Đây không phải khóa bí mật, không thay thế kiểm tra purpose và không làm dữ liệu đầu vào có thêm entropy.

**Không in token.** Code không có thao tác log token hoặc đưa token vào thông báo lỗi. Khi gói kết quả phát hành vào DTO, cũng cần tránh việc `toString()` tự động hoặc log request làm lộ credential.

`requireCanonicalFormat()` chỉ xác minh cú pháp. Bất kỳ ai cũng có thể tự tạo một chuỗi đúng profile, nên không dùng hàm này như một phép xác minh quyền khôi phục.

## 7. Token thô và giá trị lưu trữ có vai trò khác nhau

Trong mẫu opaque entropy cao, máy chủ có thể lưu digest SHA-256 của toàn bộ token canonical kèm dữ liệu vòng đời. Digest không phải token được gửi cho người dùng.

```text
token_record
    ├── token_digest
    ├── format_version
    ├── subject_id
    ├── recovery_case_id
    ├── purpose
    ├── issued_at
    ├── expires_at
    ├── consumed_at hoặc status
    ├── generation
    └── security_epoch
```

Các trường cụ thể tùy kiến trúc. Điểm quan trọng là secret chỉ chứng minh việc nắm token tương ứng; bản ghi đáng tin xác định token được dùng vào đâu.

Khi nhận token, luồng máy chủ cần:

1. Kiểm tra profile và tính canonical.
2. Tạo digest theo đúng phiên bản.
3. Tra cứu bản ghi tương ứng.
4. Đối chiếu subject, case và purpose với thao tác đang xử lý.
5. Kiểm tra thời hạn, thu hồi, thế hệ và điều kiện bảo mật hiện tại.
6. Tiêu thụ token cùng thao tác được phép theo một cơ chế nguyên tử phù hợp.

Cột digest cần giữ nguyên dữ liệu nhị phân hoặc biểu diễn cố định của nó. Nếu lưu chuỗi, không dùng cấu hình so sánh bỏ qua hoa thường hoặc cắt ký tự cho token thô. Một chỉ mục duy nhất cho digest có thể giúp phát hiện trùng; nếu gặp xung đột thực sự, tạo token mới thay vì ghi đè bản ghi cũ.

Không trả digest lưu trữ cho client rồi đồng thời cho endpoint chấp nhận nó như một định dạng token khác. Làm vậy biến digest thành một bearer credential mới.

Với bí mật ngẫu nhiên entropy cao, băm nhanh phục vụ tra cứu có bối cảnh khác với lưu mật khẩu do người dùng chọn. Không sao chép mô hình này để băm đơn giản một mã số ngắn và coi đã chống được dò ngoại tuyến.

Một hệ thống cũng có thể dùng HMAC với khóa được quản lý riêng để bảo vệ giá trị đối chiếu. Khi đó cần quản lý phiên bản khóa, quyền truy cập và cách xử lý khi xoay khóa. HMAC không thay thế entropy, thời hạn hay chống dùng lặp.

## 8. Định dạng không giải quyết thay vòng đời và quyền

Hai thao tác đồng thời có thể cùng nhận một token đúng và còn hạn. Nếu máy chủ “đọc chưa dùng” ở bước đầu rồi cập nhật ở bước cuối mà không có đồng bộ, cả hai có thể đi qua.

Vì vậy, dùng một lần phải là thuộc tính được máy chủ thi hành, chẳng hạn bằng cập nhật có điều kiện hoặc giao dịch bảo vệ cả trạng thái token và thao tác bảo mật. Thêm hậu tố `one-time` vào token không có tác dụng mật mã.

Thời hạn cũng cần được kiểm tra khi sử dụng, dựa trên thời gian máy chủ. Một expiry ở client chỉ giúp giao diện; một expiry nằm trong token không có bảo vệ toàn vẹn không phải dữ liệu đáng tin.

Các ràng buộc purpose cần đủ cụ thể. Ví dụ:

| Token được phát cho | Điều không tự được cho phép |
| --- | --- |
| Xác nhận địa chỉ khôi phục | Đặt lại mật khẩu |
| Đặt lại mật khẩu | Bỏ MFA hoặc đăng ký passkey mới |
| Mở phiên khôi phục hạn chế | Truy cập toàn bộ tài khoản |
| Một case đã kết thúc | Tạo hoặc hoàn tất case mới |

Nếu nhiều endpoint dùng chung định dạng `rt1.`, chúng vẫn phải kiểm tra purpose ở máy chủ. Tiền tố phiên bản chỉ định parser, không tự trở thành cơ chế phân quyền.

Khi phát lại token hoặc tạo token thay thế, cần xác định token trước còn hiệu lực hay bị thu hồi. Không để “gửi lại” vô tình tạo ra một tập liên kết có quyền tồn tại không giới hạn.

Sau khi khôi phục thành công, xử lý token còn chờ và session phải theo chính sách của luồng tương ứng. Một token dài, đẹp và đúng cú pháp không bảo đảm đối phương đã mất quyền truy cập phiên cũ.

## 9. Vận chuyển token mà không làm mất đặc tính của định dạng

Base64url thuận tiện cho URL vì không sử dụng `+` và `/` như Base64 thường. Tuy nhiên, sự thuận tiện đó không làm URL trở thành nơi lưu bí mật an toàn tuyệt đối.

Một token trong query string có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, hệ thống theo dõi hoặc dữ liệu được chuyển tiếp. Token trong path cũng có thể bị ghi log. Không mặc định đổi vị trí token là đã ngăn rò rỉ.

Các quyết định triển khai nên bao gồm:

- Dùng HTTPS và domain liên kết được cấu hình tin cậy.
- Giảm dữ liệu bên thứ ba trên trang chứa token.
- Kiểm soát referrer, cache và dữ liệu analytics.
- Không cho tham số chuyển hướng tùy ý mang token sang domain khác.
- Loại token khỏi log, tracing, báo lỗi và ảnh chụp chẩn đoán.
- Bảo vệ bản sao token trong hệ thống gửi email hoặc tin nhắn.

Nếu mở liên kết chỉ để hiển thị trang, không tự thực hiện thay đổi tài khoản ngay khi GET. Bộ quét email hoặc tính năng xem trước có thể truy cập trước người dùng. Việc tiêu thụ token và thực hiện thao tác cần gắn với đúng bước chủ động theo giao thức của dịch vụ.

Có thể đổi token thành một phiên khôi phục giới hạn để giảm việc mang token trong các bước tiếp theo. Phiên đó vẫn cần thời hạn, phạm vi và kiểm soát riêng; không được tự trở thành phiên đăng nhập đầy đủ.

Không đưa thông tin cá nhân vào secret chỉ để giúp hỗ trợ đọc token. Hỗ trợ có thể dùng ID case không mang quyền, còn token phải được xem như credential.

## 10. Phiên bản định dạng và khả năng chuyển đổi

Tiền tố phiên bản giúp dịch vụ phân biệt các profile khi thay đổi encoding, chiều dài hoặc cách tạo digest. Nó không phải lý do để chấp nhận mọi thứ bắt đầu bằng `rt`.

Một chính sách parser có thể quy định:

```text
rt1 -> chỉ profile rt1 đã công bố
rt2 -> chỉ profile rt2 đã công bố
phiên bản khác -> từ chối
```

Không thử lần lượt nhiều parser cho đến khi một parser chấp nhận. Cách fallback đó có thể khiến token mới bị xử lý theo quy tắc cũ yếu hơn hoặc làm hai dịch vụ hiểu cùng chuỗi theo hai cách.

Khi có nhiều phiên bản:

1. Mỗi phiên bản có giới hạn chiều dài và grammar riêng.
2. Nơi phát chỉ dùng phiên bản được cấu hình.
3. Nơi nhận chỉ chấp nhận các phiên bản đang được phép.
4. Cách tạo digest hoặc cách xác minh gắn với phiên bản rõ ràng.
5. Token cũ giữ được cơ chế thu hồi và dùng một lần trong thời gian còn được hỗ trợ.

Thay đổi định dạng không tự thay đổi trạng thái tài khoản hoặc cấp thêm quyền cho token cũ. Nếu một phiên bản bị phát hiện yếu, cần quyết định thu hồi theo rủi ro; giữ parser chỉ để tương thích không có nghĩa phải tiếp tục chấp nhận credential không an toàn.

## 11. Những nhầm lẫn thực tế cần nhận ra

**“Chuỗi đã mã hóa Base64 nên người khác không đọc được.”** Base64url chỉ là biểu diễn. Nếu dữ liệu ban đầu là JSON chứa email và thời hạn, người nhận có thể giải mã mà không cần khóa.

**“Token có 64 ký tự nên chắc chắn mạnh hơn token 43 ký tự.”** Token 64 ký tự hex và token 43 ký tự Base64url có thể cùng xuất phát từ 32 byte ngẫu nhiên. Cần so nguồn entropy, không chỉ so số ký tự.

**“Có chữ ký nên không cần lưu trạng thái.”** Chữ ký bảo vệ tính toàn vẹn theo mô hình được chọn. Hết hạn sớm, thu hồi hoặc dùng một lần vẫn cần cơ chế thi hành.

**“Đúng regex là token hợp lệ.”** Regex chỉ là một bước phân tích định dạng. Token vẫn cần được máy chủ nhận biết, còn hiệu lực và đúng quyền.

**“Thêm ID tài khoản vào token sẽ chống dùng nhầm.”** ID tự khai không tạo ra ràng buộc đáng tin. Máy chủ phải đối chiếu quan hệ đã được thiết lập hoặc xác minh toàn vẹn của claims theo giao thức.

**“Nếu người dùng gửi sai vài ký tự thì sửa gần đúng cho họ.”** Với token entropy cao, một thay đổi nhỏ thường là credential khác. Không áp dụng so khớp mờ của văn bản tự nhiên vào secret.

Một định dạng tốt có grammar ngắn gọn, lượng bí mật xác định, cách biểu diễn duy nhất và cơ chế phiên bản rõ ràng. Quyền khôi phục chỉ được xác lập khi định dạng đó được kết hợp với bản ghi đáng tin, kiểm tra purpose và vòng đời được thi hành ở máy chủ.
