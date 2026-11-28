# Password salt

## 1. Salt bảo vệ điều gì trong lưu trữ mật khẩu?

Khi hệ thống cần kiểm chứng mật khẩu, thông thường không nên lưu mật khẩu có thể đọc lại. Hệ thống lưu một **password verifier** được tạo bởi cơ chế password hashing phù hợp, rồi tính lại kết quả khi người dùng đăng nhập.

Nếu chỉ dùng một hàm xác định trên mật khẩu, hai tài khoản có cùng mật khẩu sẽ có cùng kết quả. Attacker lấy được cơ sở dữ liệu có thể tính một ứng viên rồi đối chiếu với nhiều tài khoản, hoặc tận dụng dữ liệu tính trước cho cùng cơ chế.

**Password salt** là giá trị được đưa vào cơ chế password hashing để tạo sự khác biệt cho từng verifier. Salt thường được sinh ngẫu nhiên riêng khi tạo verifier, lưu cùng metadata và được dùng lại khi xác minh chính verifier đó.

Mô hình khái niệm:

```text
verifier = PasswordKDF(password, salt, costParameters)
```

Đây là cách mô tả đầu vào của một cơ chế chuẩn, không phải hướng dẫn tự ghép chuỗi rồi gọi một hash bất kỳ. Salt không biến SHA-256 một vòng thành một cơ chế lưu mật khẩu có chi phí phù hợp.

Yêu cầu thiết kế cần xác định cả salt và password hashing scheme. [NIST SP 800-63B trong bộ 800-63-4](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver) yêu cầu lưu mật khẩu theo dạng chống tấn công offline, sử dụng salt và cơ chế password hashing phù hợp; salt, verifier và thông tin cơ chế cần được quản lý để có thể xác minh và chuyển đổi.

Mục tiêu của bài học là chuyển câu “mật khẩu phải có salt” thành yêu cầu cụ thể về nguồn sinh, độ dài, vòng đời, lưu trữ và nghiệm thu.

## 2. Salt làm thay đổi chi phí tấn công như thế nào?

### 2.1. Không có salt

Giả sử hai tài khoản dùng cùng mật khẩu P và cùng profile:

```text
Tài khoản A: H(P)
Tài khoản B: H(P)
```

Kết quả giống nhau làm lộ quan hệ giữa các bản ghi. Với một ứng viên Q, attacker chỉ cần tính `H(Q)` một lần rồi so với toàn bộ tập hash cùng cơ chế.

Vấn đề không chỉ là “giải ngược hash”. Attacker thường **đoán mật khẩu**, chạy hàm tương ứng và so kết quả. Salt không phải thứ ngăn một phép giải mã vốn tồn tại; nó làm giảm khả năng tái sử dụng công việc tính toán giữa nhiều verifier.

### 2.2. Salt riêng cho từng verifier

```text
Tài khoản A: PasswordKDF(P, salt_A, profile)
Tài khoản B: PasswordKDF(P, salt_B, profile)
```

Khi `salt_A` khác `salt_B`, kết quả thường khác nhau dù mật khẩu giống nhau. Attacker phải thực hiện phép tính ứng viên với salt tương ứng thay vì dùng nguyên một giá trị tính được cho mọi tài khoản.

Không thể bảo đảm toán học rằng mọi output hữu hạn đều không bao giờ va chạm. Điều cần đạt là construction chuẩn với không gian salt đủ lớn và nguồn sinh đúng, thay vì một thiết kế cho ra cùng verifier chỉ vì người dùng chọn cùng mật khẩu.

Salt cũng làm việc chuẩn bị bảng tính trước cho toàn bộ các salt khả dĩ trở nên khó hơn khi không gian salt đủ lớn. Nó không làm mật khẩu phổ biến trở thành mật khẩu mạnh: attacker vẫn có thể thử ứng viên dễ đoán trên từng bản ghi.

### 2.3. Một salt cố định không đáp ứng mục tiêu

Cách làm cần tránh:

```text
salt = "my-application-salt"
verifier = SHA256(salt || password)
```

Cả salt dùng chung lẫn hàm hash nhanh đều là vấn đề. Một hằng số có thể làm một bảng tính trước chung cho cơ chế khác không dùng trực tiếp được, nhưng sau khi biết hằng số, attacker vẫn tái sử dụng công việc giữa các tài khoản của hệ thống.

Không gọi một hằng số giấu trong source là salt riêng của từng mật khẩu. Nếu hệ thống cần một bí mật bổ sung, đó là một thiết kế pepper hoặc keyed operation khác, phải có chính sách riêng.

## 3. Phân biệt salt, pepper, work factor và khóa

| Thành phần | Vai trò | Có cần giữ bí mật không? | Vòng đời thường gặp |
| --- | --- | --- | --- |
| Salt | Tách phép tính verifier giữa các bản ghi | Không cần là secret | Sinh cho mỗi lần tạo verifier theo profile |
| Work factor | Tăng chi phí mỗi lần đoán mật khẩu | Không | Gắn profile; nâng theo năng lực và rủi ro |
| Pepper hoặc secret của keyed operation | Bổ sung bí mật không nằm cùng kho verifier | Có | Quản lý như secret, có version và kế hoạch thay đổi |
| Verifier | Giá trị dùng để kiểm chứng mật khẩu | Phải bảo vệ quyền truy cập | Gắn credential và profile |
| Khóa mã hóa | Bảo vệ dữ liệu theo cơ chế mã hóa | Có | Theo key policy và mục đích |

Salt có thể được lưu cạnh verifier mà không làm mất mục đích của nó. Thiết kế phải giả định attacker lấy được cả hai khi đánh giá tấn công offline.

“Salt không bí mật” không đồng nghĩa toàn bộ bảng credential nên công khai. Verifier vẫn là dữ liệu nhạy cảm; API thông thường không cần trả salt hoặc verifier cho người dùng. Lộ metadata cũng có thể hỗ trợ đánh giá hệ thống hoặc dò tài khoản nếu thiết kế endpoint không phù hợp.

Pepper không thay salt. Nếu chọn dùng pepper, cần lưu secret tách khỏi kho verifier, kiểm soát quyền dùng, theo dõi version và có kế hoạch khi secret mất hoặc bị lộ. Không chỉ đặt một chuỗi dùng chung vào cùng bảng rồi coi đó là một lớp bảo vệ riêng.

Các vai trò salting, peppering và work factor được giải thích trong [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#methods-for-enhancing-password-storage).

## 4. Đặc tả nguồn sinh và độ dài salt

### 4.1. Dùng nguồn ngẫu nhiên mật mã

Yêu cầu nên ghi rõ salt được tạo ở phía server bởi thư viện password hashing hoặc CSPRNG của nền tảng được chấp nhận. Không nhận trực tiếp salt do client tùy ý chọn cho verifier mới của hệ thống, trừ khi có một giao thức riêng đã được thẩm định.

Không chọn salt từ:

- Một hằng số trong cấu hình.
- Username, email hoặc mã nhân viên.
- Timestamp đơn thuần.
- Counter dùng lại khi khởi động.
- Bộ sinh ngẫu nhiên thông thường không dành cho mật mã.
- Một mảng byte được tạo một lần rồi tái sử dụng cho mọi tài khoản.

Username có thể khác nhau trong một cơ sở dữ liệu nhưng thường dễ dự đoán, có thể trùng giữa nhiều hệ thống và có vòng đời thay đổi riêng. Nếu dùng nó để dẫn xuất salt, đổi username còn có thể ảnh hưởng việc xác minh. Salt ngẫu nhiên độc lập giúp tránh ràng buộc không cần thiết đó.

### 4.2. Độ dài tính bằng byte ngẫu nhiên trước encoding

Một profile minh họa có thể yêu cầu **16 byte salt ngẫu nhiên**, tương đương 128 bit. Đây là lựa chọn của profile trong bài, không phải tuyên bố mọi tiêu chuẩn đều quy định đúng cùng một độ dài. [RFC 9106, mục Argon2 Inputs and Outputs](https://www.rfc-editor.org/rfc/rfc9106.html#section-3.1) khuyến nghị 16 byte cho salt dùng với password hashing Argon2.

Nếu 16 byte được biểu diễn bằng hex, chuỗi có 32 ký tự. Nếu dùng Base64 thông thường có padding, chuỗi có 24 ký tự. Những con số biểu diễn này không làm tăng số bit ngẫu nhiên ban đầu.

Ví dụ một salt chỉ có 4 byte rồi được chuyển thành một chuỗi Base64 dài hơn vẫn chỉ có không gian sinh tương ứng 4 byte. Không nghiệm thu entropy bằng độ dài cột chuỗi sau encoding.

### 4.3. Tính riêng biệt cần được thiết kế theo quy mô

Với b bit ngẫu nhiên và N salt độc lập, xác suất va chạm có thể được ước lượng theo birthday bound khi N còn nhỏ so với không gian giá trị:

```text
p_collision xấp xỉ N * (N - 1) / 2^(b + 1)
```

Đây là lý do chọn không gian lớn và nguồn sinh đúng, không phải lời hứa ngẫu nhiên sẽ không bao giờ trùng. Một kiểm thử phát hiện salt trùng có ích để tìm lỗi dùng lại mảng hoặc seed, nhưng không chứng minh tuyệt đối chất lượng entropy.

Có thể có cơ chế phát hiện bất thường hoặc ràng buộc dữ liệu phù hợp với quy mô, nhưng không thay nguồn ngẫu nhiên bằng một cơ chế tự sáng tác chỉ để có tính “unique” trên giấy. Nếu cần bảo đảm bổ sung, phải đánh giá cả độ tin cậy, import dữ liệu và xử lý va chạm.

## 5. Vòng đời: khi nào tạo salt mới, khi nào dùng salt cũ?

### 5.1. Tạo verifier mới

Các sự kiện thường tạo verifier mới:

- Đăng ký credential mật khẩu.
- Đổi mật khẩu.
- Đặt lại mật khẩu qua quy trình phục hồi đã được phép.
- Rehash sau khi xác minh thành công để nâng thuật toán hoặc work factor.

Trong profile minh họa, mỗi lần tạo verifier phải sinh salt mới. Nếu người dùng được phép chọn lại cùng mật khẩu, verifier mới vẫn dùng một salt mới; chính sách có cho phép dùng lại mật khẩu hay không là một quyết định nghiệp vụ khác.

Không tái sử dụng một salt toàn cục cho cùng user qua mọi lần đổi mật khẩu chỉ vì tài khoản không đổi. Salt gắn với bản ghi verifier, không phải định danh bất biến của con người.

### 5.2. Xác minh verifier hiện có

Khi đăng nhập, hệ thống phải đọc salt đã lưu và tính với **cùng salt đó**, cùng thuật toán và tham số của verifier:

```text
candidate = PasswordKDF(inputPassword, storedSalt, storedProfile)
compare(candidate, storedVerifier)
```

Không sinh salt mới trước phép so sánh rồi kỳ vọng kết quả khớp. Một thư viện mức cao có thể lấy salt từ encoded verifier và thực hiện bước này bên trong; ứng dụng không cần tự tách ra.

Sau khi xác minh thành công, nếu cần nâng profile, hệ thống có thể tạo verifier mới với salt mới và ghi lại theo điều kiện cạnh tranh phù hợp. Đó là bước riêng, không phải thay salt của phép xác minh ban đầu.

### 5.3. Không thay salt mà giữ nguyên verifier

Nếu đổi giá trị salt trong cơ sở dữ liệu nhưng không tính lại verifier từ mật khẩu theo profile, các lần đăng nhập sau sẽ không còn xác minh đúng. Salt không có cơ chế “xoay” độc lập như đổi một nhãn metadata.

Đối với mật khẩu chưa biết plaintext, không thể đơn giản tạo một salt khác rồi tính ra verifier mới tương đương. Cần xác minh khi người dùng cung cấp mật khẩu, yêu cầu reset hoặc dùng một kế hoạch chuyển đổi đã được thiết kế rõ cho dữ liệu legacy.

Việc bọc thêm một hàm quanh verifier cũ có thể là một thiết kế migration riêng trong một số bối cảnh, nhưng không đồng nghĩa đã thay bản ghi đó bằng một password hash mới trực tiếp từ mật khẩu với profile mục tiêu.

## 6. Lưu verifier và metadata để có thể xác minh đúng

### 6.1. Lưu một đơn vị dữ liệu nhất quán

Một bản ghi khái niệm:

```json
{
  "credentialVersion": 7,
  "profileId": "password-profile-v2",
  "saltBase64": "<salt-16-byte-duoc-encode>",
  "verifierBase64": "<ket-qua-password-kdf>",
  "createdAt": "<thoi-diem-tao>"
}
```

Các giá trị trong dấu ngoặc nhọn là placeholder, không phải dữ liệu credential thật. `profileId` phải ánh xạ tới bộ tham số đã được server phê duyệt. Có thể lưu tham số rõ trong định dạng tự mô tả, nhưng phải kiểm tra chúng theo policy trước khi sử dụng.

Nhiều thư viện dùng một encoded verifier chứa algorithm, version, cost, salt và kết quả. Khi định dạng đó đã được thư viện quản lý, không nhất thiết thêm một cột salt riêng rồi duy trì hai bản có thể lệch nhau.

Điều quan trọng là lưu nguyên vẹn theo hợp đồng của thư viện. Không cắt chuỗi do cột quá ngắn, đổi chữ hoa/thường, bỏ ký tự đặc biệt hoặc decode rồi encode lại bằng một biến thể không tương thích.

### 6.2. Ghi nguyên tử với metadata

Salt, verifier và profile phải thuộc cùng một lần cập nhật credential. Không để một transaction ghi salt mới thành công nhưng verifier vẫn là giá trị cũ.

Khi có nhiều thao tác đồng thời, dùng version hoặc cơ chế concurrency phù hợp. Ví dụ, một login đang rehash không được ghi đè mật khẩu mới vừa được reset. Cập nhật rehash có thể yêu cầu credential version vẫn bằng giá trị đã xác minh.

Nếu version đã thay đổi, phải tuân theo chính sách xác thực và cạnh tranh của hệ thống. Chỉ dùng compare-and-swap cho bản ghi không tự giải quyết mọi quyết định về phiên đăng nhập khi có reset mật khẩu đồng thời.

### 6.3. Giới hạn metadata trước khi gọi KDF

Một encoded verifier có thể chứa cost hoặc kích thước bộ nhớ. Nếu bản ghi bị sửa hoặc nguồn import không đáng tin, giá trị cực lớn có thể gây DoS khi ứng dụng cố xác minh.

Yêu cầu nên giới hạn kích thước encoded record, thuật toán, độ dài salt, độ dài output và các tham số được phép. Không truyền profile tùy ý do client cung cấp trực tiếp vào một API tạo hoặc xác minh verifier.

Với salt hoặc verifier thiếu, bị cắt hoặc không parse được, dùng đường lỗi có kiểm soát. Không tự fallback sang hash không salt hoặc một thuật toán legacy chỉ vì metadata không còn hợp lệ.

## 7. Salt không thay work factor hoặc thuật toán phù hợp

Hai mục tiêu bổ sung cho nhau:

```text
Salt riêng: hạn chế tái sử dụng công việc giữa nhiều verifier.
Password KDF với cost phù hợp: tăng chi phí mỗi lần thử một ứng viên.
```

Thêm salt vào SHA-256 vẫn cho phép mỗi lần đoán được tính rất nhanh. Một thiết kế lưu mật khẩu cần profile như Argon2id hoặc password-based KDF phù hợp với chính sách, môi trường và yêu cầu áp dụng.

Work factor cần được đánh giá trên năng lực xác thực và tải đồng thời. Tăng cost vô hạn có thể làm cạn tài nguyên của chính verifier. Cần giới hạn tốc độ, số công việc xác minh đồng thời, kích thước đầu vào và cơ chế xử lý khi quá tải.

Nếu có yêu cầu dùng implementation trong một module được xác nhận, phải kiểm tra phạm vi module và cấu hình thực tế. Việc dùng một tên thuật toán trong JCA không tự chứng minh yêu cầu xác nhận đó đã được đáp ứng.

Không nên mặc định người dùng có mật khẩu mạnh chỉ vì dữ liệu đã có salt. Chính sách mật khẩu, phát hiện credential bị lộ, MFA khi áp dụng và bảo vệ kênh truyền vẫn cần được thiết kế theo rủi ro.

## 8. Ví dụ Java: tạo salt bằng `SecureRandom`

Đoạn nhỏ nhất để thể hiện phần sinh salt:

```java
import java.security.SecureRandom;

public final class PasswordSaltSource {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int SALT_BYTES = 16;

    private PasswordSaltSource() {
    }

    public static byte[] newSalt() {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        return salt;
    }
}
```

Mỗi lần gọi tạo một mảng mới và điền byte từ RNG mật mã. Không seed bằng timestamp, username hoặc một hằng số để làm kết quả lặp lại. Môi trường và provider vẫn cần đáp ứng chính sách entropy của hệ thống. Hợp đồng nền tảng được mô tả trong [Java SE 21 SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html).

Trong sản phẩm, ưu tiên API password hashing được duy trì và tự quản lý salt khi có thể. Khi đó ứng dụng gọi phương thức encode để tạo verifier mới và phương thức verify/matches để kiểm chứng; không tự ghép thêm salt ngoài một định dạng thư viện đã có salt nếu profile không yêu cầu.

Test cần có khả năng kiểm tra nguồn ngẫu nhiên hoặc dùng test double đúng phạm vi, nhưng không được mang seed cố định của test sang production. Việc tạo output lặp lại để dễ snapshot test không phải yêu cầu cho dữ liệu salt thật.

## 9. Ví dụ JCA: phân biệt tạo mới và xác minh

Đoạn dưới minh họa một profile PBKDF2-HMAC-SHA-256 bằng JCA, với salt 16 byte, output 32 byte và 600.000 vòng. Đây là một profile ví dụ để thể hiện vòng đời salt; nó không thay việc chọn thuật toán theo chính sách hoặc benchmark trên hạ tầng thật. Con số vòng không phải giá trị bất biến phù hợp mọi thời điểm.

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class ExamplePasswordVerifier {
    private static final String PROFILE = "pbkdf2-sha256-600k-v1";
    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BYTES = 32;
    private static final int MAX_ENCODED_FIELD_CHARS = 64;
    private static final SecureRandom RANDOM = new SecureRandom();

    private ExamplePasswordVerifier() {
    }

    public record StoredVerifier(
            String profileId, String saltBase64, String verifierBase64) {
    }

    public static StoredVerifier create(char[] password)
            throws GeneralSecurityException {
        Objects.requireNonNull(password, "password");

        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);

        byte[] derived = derive(password, salt);
        try {
            return new StoredVerifier(
                    PROFILE,
                    Base64.getEncoder().encodeToString(salt),
                    Base64.getEncoder().encodeToString(derived));
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(char[] password, StoredVerifier stored)
            throws GeneralSecurityException {
        Objects.requireNonNull(password, "password");
        Objects.requireNonNull(stored, "stored");

        if (!PROFILE.equals(stored.profileId())) {
            throw new IllegalArgumentException("Unsupported verifier profile");
        }

        byte[] salt = decodeField(stored.saltBase64(), SALT_BYTES);
        byte[] expected = decodeField(stored.verifierBase64(), HASH_BYTES);
        byte[] candidate = derive(password, salt);
        try {
            return MessageDigest.isEqual(candidate, expected);
        } finally {
            Arrays.fill(candidate, (byte) 0);
            Arrays.fill(expected, (byte) 0);
        }
    }

    private static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {
        PBEKeySpec specification = new PBEKeySpec(
                password, salt, ITERATIONS, HASH_BYTES * 8);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance(
                    "PBKDF2WithHmacSHA256");
            return factory.generateSecret(specification).getEncoded();
        } finally {
            specification.clearPassword();
        }
    }

    private static byte[] decodeField(String encoded, int expectedBytes) {
        if (encoded == null || encoded.length() > MAX_ENCODED_FIELD_CHARS) {
            throw new IllegalArgumentException("Invalid verifier encoding");
        }
        byte[] decoded = Base64.getDecoder().decode(encoded);
        if (decoded.length != expectedBytes) {
            throw new IllegalArgumentException("Invalid verifier field length");
        }
        return decoded;
    }
}
```

Các điểm cần hiểu đúng:

- `create()` luôn sinh salt mới. `verify()` lấy lại salt đã lưu, không gọi RNG cho phép so sánh đó.
- `profileId` khớp chính xác một profile server cho phép; record không tự chọn số vòng cực lớn hoặc một thuật toán khác.
- Base64 chỉ là định dạng lưu, không thêm entropy và không che giấu verifier.
- Salt có độ dài 16 byte; `HASH_BYTES * 8` trong `PBEKeySpec` là độ dài output tính bằng bit, không phải salt.
- Lỗi provider hoặc record không hợp lệ không được chuyển thành một đường xác minh hash nhanh hơn.

Ứng dụng thật còn cần policy mật khẩu và giới hạn độ dài phía server trước khi gọi, kiểm soát concurrency, lưu nguyên tử, rehash, xử lý lỗi công khai và quản lý provider. Đoạn code không triển khai toàn bộ hệ thống xác thực và không tuyên bố đáp ứng một yêu cầu FIPS cụ thể.

`PBEKeySpec` giữ bản sao nội bộ của password và cung cấp `clearPassword()`; phía gọi vẫn phải quản lý mảng `char[]` đầu vào của mình. Xem [Java SE 21 PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html). Không chuyển qua `String` hoặc log password chỉ để thuận tiện debug; đồng thời không tuyên bố mọi bản sao trong runtime đều được xóa tuyệt đối bởi một lệnh fill.

Việc dùng [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)) cho hai output có độ dài được kiểm soát không làm toàn bộ endpoint trở thành hằng thời gian. Lookup tài khoản, parse record, profile khác nhau và xử lý lỗi vẫn cần được xem xét nếu chống dò tài khoản là yêu cầu.

## 10. Thư viện tự quản lý salt: biết hợp đồng trước khi thêm code

Nhiều password encoder đã sinh salt và nhúng nó trong encoded verifier. Với những API này, hai lần encode cùng mật khẩu có thể tạo hai chuỗi khác nhau, trong khi cả hai vẫn xác minh được bằng cùng mật khẩu.

Không kiểm chứng bằng cách gọi encode lần nữa rồi so chuỗi:

```text
Sai đối với encoder sinh salt mới mỗi lần:
  encode(inputPassword) == storedEncodedVerifier

Đúng theo hợp đồng thư viện:
  matches(inputPassword, storedEncodedVerifier)
```

Không thêm một salt tự tạo vào đầu password rồi lại dùng encoder có salt riêng chỉ vì thấy mỗi lần encode khác nhau. Nếu profile đã phê duyệt một construction cụ thể, phải tuân theo nó; nếu không, lớp ghép bổ sung có thể gây rắc rối về encoding, giới hạn đầu vào và migration.

Cần biết thư viện có tự quản lý salt hay không, salt nằm ở đâu, cách chọn cost và cách xác định cần nâng cấp. Không suy rằng một hàm `hash()` bất kỳ có cùng hợp đồng với một password encoder.

## 11. Nâng cấp verifier và chuyển đổi dữ liệu cũ

### 11.1. Rehash sau xác minh thành công

Luồng thường gặp:

```text
Đọc record hiện tại
    -> kiểm tra định dạng và profile được phép đọc
    -> xác minh mật khẩu bằng salt và tham số đã lưu
    -> nếu thành công và cần nâng cấp:
         sinh salt mới
         tạo verifier theo profile mới từ mật khẩu vừa xác minh
         cập nhật nguyên tử nếu credential version chưa đổi
```

Không rehash bản ghi hiện tại khi người dùng nhập sai mật khẩu. Không ghi salt mới trước khi đã có verifier mới để cập nhật cùng một đơn vị dữ liệu.

Nếu bước rehash tùy chọn thất bại sau khi xác minh đúng, hệ thống phải theo chính sách đã công bố: có thể ghi nhận để thử lại theo thiết kế, hoặc yêu cầu bước khác nếu đây là chuyển đổi bắt buộc. Không tự hạ cấp hoặc làm hỏng verifier đang dùng để cố hoàn thành.

### 11.2. Dữ liệu legacy không có salt

Khi có record legacy, cần một profile đọc cũ được giới hạn rõ và lộ trình chuyển đổi. Không nhận diện legacy bằng cách “thử hash nào khớp thì dùng” không kiểm soát. Trường algorithm/version phải được xác định từ nguồn migration tin cậy và quy tắc đã chốt.

Sau khi người dùng xác thực đúng theo cơ chế cũ được phép, có thể tạo verifier mới bằng mật khẩu vừa nhập, salt mới và profile mục tiêu. Tài khoản không quay lại có thể cần reset theo chính sách retirement; không giữ đường đọc yếu vô hạn chỉ vì migration chưa đạt 100%.

Không thể đơn giản thêm một cột salt ngẫu nhiên vào hash cũ rồi coi việc chuyển đổi đã hoàn tất. Salt phải thực sự tham gia phép tính tạo verifier mà hệ thống kiểm chứng.

### 11.3. Password history và kiểm tra dùng lại

Nếu hệ thống có yêu cầu kiểm tra mật khẩu đã dùng, mỗi verifier lịch sử có salt và profile của nó. Không so hash hiện tại với hash mới để kết luận password khác nhau, vì salt mới khiến kết quả khác ngay cả khi password giống.

Việc kiểm tra cần đi qua cơ chế verify phù hợp với các bản ghi lịch sử còn được giữ. Điều này có chi phí và làm tăng lượng dữ liệu credential nhạy cảm; cần giới hạn số bản ghi, quyền truy cập và thời hạn theo policy. Salt không làm việc lưu mọi verifier lịch sử trở thành không có rủi ro.

## 12. Lỗi sinh salt, lỗi lưu trữ và phục hồi

### 12.1. Không fallback sang salt cố định

Nếu nguồn ngẫu nhiên không đáp ứng yêu cầu hoặc thao tác tạo verifier lỗi, đăng ký/đổi/reset mật khẩu phải kết thúc theo đường lỗi được kiểm soát. Không dùng username, mảng zero hoặc một giá trị “dự phòng” để tiếp tục thành công.

Xác minh record hiện có về bản chất không cần sinh salt mới. Tuy nhiên, nếu luồng đó có rehash hoặc cơ chế bổ sung cần RNG, phải tách rõ bước nào thất bại và cách xử lý theo policy, thay vì gộp mọi lỗi thành “mật khẩu sai”.

### 12.2. Backup phải giữ cả salt và metadata

Backup chỉ có verifier nhưng mất salt hoặc version có thể khiến hệ thống không xác minh được credential. Cần phục hồi nguyên vẹn đơn vị dữ liệu cùng schema và profile cần đọc.

Nếu dùng pepper, khả năng khôi phục còn phụ thuộc secret đúng version. Salt không thay thế secret đó; secret cũng không nên được nhét vào cùng bản backup verifier để làm việc khôi phục “tiện hơn” mà mất ranh giới bảo vệ.

Không tự reset metadata hoặc cắt encoded verifier khi phục hồi sang hệ thống có cột ngắn hơn. Ca restore cần kiểm chứng tài khoản thử đúng và sai mật khẩu, profile cũ còn được phép và tính nguyên tử credential.

### 12.3. Giữ log đủ để chẩn đoán mà không lộ credential

Có thể ghi profile ID, loại lỗi và request ID. Không ghi password, raw verifier hoặc toàn bộ payload đăng nhập. Salt không bí mật nhưng thường cũng không cần xuất hiện trong mọi log; việc ghi nó không được kéo theo cả bản ghi credential.

Nếu phát hiện nhiều salt giống nhau hoặc độ dài sai, cần có quy trình xác định nguồn tạo, release và phạm vi tài khoản ảnh hưởng. Không sửa hàng loạt salt trực tiếp trong cơ sở dữ liệu để làm báo cáo hết lỗi.

## 13. Bộ yêu cầu bảo mật có thể nghiệm thu

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| SALT-01 | Mỗi lần tạo verifier theo profile hiện tại phải dùng salt mới do nguồn mật mã được phép sinh | Kiểm tra luồng đăng ký, đổi, reset và rehash |
| SALT-02 | Profile hiện tại dùng 16 byte salt trước encoding | Decode dữ liệu lưu và đối chiếu số byte |
| SALT-03 | Salt không được dẫn xuất trực tiếp từ định danh, thời gian hoặc hằng số | Đối chiếu nguồn sinh và cấu hình hiệu lực |
| SALT-04 | Verification phải dùng salt, algorithm và cost của đúng verifier | Ca đúng/sai password và record khác salt |
| SALT-05 | Salt, verifier và profile phải được cập nhật nguyên tử | Lỗi lưu giữa chừng và các thao tác đồng thời |
| SALT-06 | Metadata không hợp lệ không được gây fallback sang cơ chế yếu hơn | Record thiếu, sai độ dài, sai encoding hoặc profile lạ |
| SALT-07 | Nâng cấp phải tạo verifier mới với salt mới từ password đã xác minh | Rehash và cạnh tranh với đổi/reset password |
| SALT-08 | Quyền đọc credential, log và backup phải bảo vệ verifier | Kiểm tra output API, log, export và restore |
| SALT-09 | Cost và kích thước record phải được giới hạn theo policy server | Metadata quá lớn, profile ngoài danh mục và tải đồng thời |
| SALT-10 | Lỗi tạo salt không được chuyển thành tạo verifier bằng giá trị cố định | Mô phỏng lỗi nguồn sinh trong môi trường kiểm thử |

Mốc 16 byte là lựa chọn cụ thể của profile minh họa. Khi áp dụng cho sản phẩm khác, cần có cơ sở chính sách và hợp đồng thư viện tương ứng; không sửa salt của verifier cũ thành 16 byte chỉ để đồng nhất cột.

Một yêu cầu hoàn chỉnh có thể ghi:

> Khi đăng ký, đổi, reset hoặc rehash credential mật khẩu theo profile v2, dịch vụ phải tạo salt ngẫu nhiên 16 byte bằng cơ chế mật mã được phê duyệt. Salt và verifier phải lưu nguyên tử cùng profile/version. Khi xác minh, dịch vụ dùng lại salt của record; lỗi định dạng hoặc nguồn sinh không được dẫn đến cơ chế không salt hoặc salt cố định.

## 14. Kế hoạch nghiệm thu và giới hạn của kiểm thử

Các ca sau là kế hoạch kiểm chứng cho thiết kế minh họa, không phải báo cáo đã chạy trên một hệ thống thật.

| Ca | Chuẩn bị | Kết quả cần quan sát |
| --- | --- | --- |
| Hai credential cùng password | Tạo hai verifier độc lập | Salt khác trong ca thử; cả hai verify đúng password |
| Tạo lại cùng tài khoản | Đổi/reset với password được policy cho phép | Salt mới và record mới nhất quán |
| Verification bình thường | Record hiện có và password đúng | Khớp mà không sinh salt mới cho phép so sánh |
| Password sai | Cùng record, password khác | Không khớp; record không bị thay |
| Salt bị đổi | Giữ verifier, thay salt | Không xác minh như record gốc; không tự chữa bằng fallback |
| Salt bị cắt | Thiếu byte hoặc encoding sai | Lỗi record có kiểm soát, không tạo phiên xác thực |
| Profile không biết | Algorithm/version ngoài policy | Không chọn tùy ý một KDF hoặc cost |
| Cost bị nâng bất thường | Record/import có tham số vượt giới hạn | Chặn theo policy trước công việc không giới hạn |
| Unicode | Password có tiếng Việt hoặc ký tự nhiều byte | Đăng ký và verify nhất quán theo hợp đồng encoding |
| Không có RNG hợp lệ | Luồng tạo mới gặp lỗi nguồn sinh | Không tạo credential bằng salt dự phòng |
| Rehash | Xác minh đúng profile cũ được phép | Salt mới, profile mới và verifier đúng |
| Race reset–rehash | Reset xảy ra sau lúc login đọc record | Rehash không ghi đè password mới |
| Lỗi transaction | Ghi credential bị ngắt giữa chừng | Không còn cặp salt/verifier lệch |
| Restore | Khôi phục backup cùng schema và profile | Credential thử được xác minh đúng/sai như kỳ vọng |
| Quan sát output | Kiểm tra response, log và export | Không lộ password/verifier ngoài policy |

### 14.1. Không dùng “mọi salt khác nhau trong test” làm chứng minh duy nhất

Một test như vậy phát hiện được lỗi salt cố định hoặc tái sử dụng mảng, nhưng không đánh giá đầy đủ entropy, chất lượng provider hoặc hành vi sau clone/restore môi trường. Cần đối chiếu nguồn sinh thật và cấu hình vận hành.

Cũng không đặt quy tắc rằng hai output khác nhau chắc chắn do salt đúng. Output có thể khác vì thuật toán hoặc tham số khác; bằng chứng nên kiểm tra chính metadata salt đã decode và luồng tạo verifier.

### 14.2. Encoding và normalization phải nhất quán

Password có thể có nhiều biểu diễn Unicode hoặc khoảng trắng có ý nghĩa với người dùng. Không tự trim, đổi hoa thường hoặc chuẩn hóa theo một cách ở đăng ký và cách khác ở đăng nhập. Nếu sản phẩm có policy chuẩn hóa, phải ghi rõ, áp dụng nhất quán và kiểm thử tương thích provider.

Salt là byte độc lập với password, không phải chuỗi cần được chuẩn hóa ngôn ngữ. Các biến đổi đối với biểu diễn Base64 hoặc định dạng encoded verifier phải theo thư viện, không theo một bộ xử lý văn bản chung.

### 14.3. Chống dò tài khoản là một yêu cầu riêng

Đường tài khoản không tồn tại có thể không chạy KDF, trong khi tài khoản có tồn tại thì có. Nếu chống suy luận qua phản hồi hoặc timing là mục tiêu, cần thiết kế đường xử lý phù hợp, giới hạn tải và thông điệp lỗi thống nhất theo policy.

Không sinh salt ngẫu nhiên mới cho verifier thật trong mỗi lần đăng nhập để giải quyết vấn đề này. Các kỹ thuật như phép kiểm chứng giả trong trường hợp không có tài khoản phải được thiết kế với cost và ngân sách rõ ràng, không làm endpoint trở thành nơi kích hoạt KDF không giới hạn.

## 15. Một hồ sơ yêu cầu gọn cho thiết kế credential

```text
Tài sản: verifier mật khẩu và khả năng xác thực tài khoản hợp lệ.
Đe dọa: lộ kho credential, tái sử dụng tính toán, metadata hỏng,
        dùng salt cố định hoặc cập nhật salt/verifier không nhất quán.

Chính sách salt:
  - Sinh bằng thư viện/CSPRNG được chấp nhận ở phía server.
  - Profile minh họa dùng 16 byte ngẫu nhiên trước encoding.
  - Tạo mới khi tạo verifier; dùng lại salt đã lưu khi verify.
  - Không coi salt là pepper hoặc khóa mã hóa.

Lưu trữ:
  - Salt, verifier, profile và version là một đơn vị nhất quán.
  - Giới hạn định dạng và tham số trước khi gọi KDF.
  - Không xuất credential qua response/log thông thường.

Nâng cấp và lỗi:
  - Rehash sau xác minh đúng, salt mới, cập nhật có điều kiện version.
  - Không fallback sang hash nhanh, không salt hoặc salt cố định.
  - Restore phải giữ metadata cần xác minh và secret riêng nếu có.

Kiểm chứng:
  - Cùng password ở hai credential; đúng/sai password; salt hỏng.
  - Đổi/reset/rehash; race; lỗi lưu; Unicode; restore và tải KDF.
```

Password salt có giá trị khi được sinh và sử dụng đúng vòng đời của verifier, kết hợp với một password hashing profile phù hợp. Salt riêng, metadata nguyên vẹn và việc xác minh bằng đúng salt đã lưu phải trở thành yêu cầu có bằng chứng, thay vì chỉ một trường dữ liệu được thêm vào bảng tài khoản.
