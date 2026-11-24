# Token storage encryption

## 1. Mã hóa token khi lưu trữ bảo vệ điều gì?

Token khôi phục thường là một bí mật mang quyền: người có token hợp lệ có thể được phép đặt lại mật khẩu hoặc thực hiện một bước khôi phục đã được phê duyệt. Nếu raw token xuất hiện trong database, queue, file tạm hoặc backup, bên đọc được dữ liệu đó có thể sử dụng quyền trước khi token hết hạn.

**Token storage encryption** là mã hóa dữ liệu token tại những nơi cần lưu bản có thể khôi phục, với khóa và quyền giải mã được quản lý riêng. Mục tiêu là hạn chế việc lộ bí mật khi một lớp lưu trữ bị đọc trái phép.

Cần xác định rõ tình huống muốn chống:

| Tình huống | Câu hỏi thiết kế |
| --- | --- |
| Mất ổ đĩa hoặc snapshot | Lớp lưu trữ vật lý có được mã hóa không? |
| Lộ bản dump logic của database | Dump chứa raw token hay ciphertext ở cấp ứng dụng? |
| Lộ dữ liệu queue gửi email | Payload có chứa liên kết khôi phục dùng được không? |
| Một dịch vụ bị cấp quyền đọc quá rộng | Nó có đồng thời được giải mã token không? |
| Tiến trình ứng dụng bị chiếm quyền | Kẻ tấn công có thể dùng quyền giải mã của tiến trình đến đâu? |

OWASP nhấn mạnh việc chọn lớp mã hóa phải dựa trên mô hình đe dọa và khuyến nghị dùng chế độ mã hóa có xác thực khi phù hợp. Xem [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).

Mã hóa lưu trữ không tự làm token dùng một lần, không gắn token với đúng tài khoản và không quyết định quyền thay MFA. Các điều kiện đó vẫn thuộc logic khôi phục phía máy chủ.

## 2. Trước hết, có cần khôi phục raw token không?

Nếu hệ thống chỉ cần kiểm tra token người dùng trình bày, thường có thể lưu một **bộ kiểm chứng một chiều** thay vì một bản token có thể giải mã.

Ví dụ:

```text
token bí mật ngẫu nhiên
    -> gửi cho người dùng

bộ kiểm chứng token
    -> lưu cùng account, purpose, expiry và trạng thái
```

Với token ngẫu nhiên có entropy cao, một thiết kế có thể dùng hàm băm mật mã hoặc HMAC phù hợp để kiểm chứng. Mã OTP ngắn cần được phân tích riêng vì không gian đoán nhỏ; giới hạn thử và chống lạm dụng vẫn rất quan trọng.

Phân biệt các kỹ thuật:

| Kỹ thuật | Có khôi phục bí mật ban đầu không? | Vai trò |
| --- | --- | --- |
| Base64 hoặc hex | Có, bằng giải mã biểu diễn | Chuyển dữ liệu thành chuỗi; không cung cấp tính bí mật |
| Hash | Không có thao tác giải mã | Tạo bộ kiểm chứng một chiều cho thiết kế phù hợp |
| HMAC | Không có thao tác giải mã | Tạo bộ kiểm chứng có khóa |
| Mã hóa có xác thực | Có, khi có khóa đúng | Giữ bản có thể khôi phục và phát hiện sửa đổi |

Một lý do thực tế để lưu token có thể giải mã là xử lý gửi thông điệp bất đồng bộ: token đã được tạo, nhưng worker cần lấy bí mật để dựng liên kết khi gửi hoặc retry trong một khoảng thời gian ngắn.

Trong trường hợp đó, có thể thiết kế hai nơi lưu riêng:

- **Kho kiểm chứng:** giữ verifier và trạng thái sử dụng, không cần raw token.
- **Kho chuyển thông điệp:** giữ payload token được mã hóa, chỉ tồn tại trong thời gian cần gửi.

Các ví dụ phía dưới dùng mô hình này. Đây là một lựa chọn kiến trúc minh họa, không bắt buộc mọi hệ thống phải có hai kho.

Không mã hóa mật khẩu người dùng để có thể lấy lại sau này. Mật khẩu mới của luồng khôi phục phải đi qua cơ chế băm mật khẩu của ứng dụng.

## 3. Phân biệt mã hóa ổ đĩa, database và ứng dụng

Một hệ thống có thể dùng nhiều lớp bảo vệ, nhưng mỗi lớp có giới hạn khác nhau.

| Lớp | Giá trị bảo vệ điển hình | Giới hạn cần hiểu |
| --- | --- | --- |
| Mã hóa ổ đĩa | Hạn chế đọc dữ liệu từ thiết bị lưu trữ ngoại tuyến | Tiến trình đã được hệ điều hành cho phép vẫn có thể đọc dữ liệu |
| TDE hoặc mã hóa vật lý của database | Bảo vệ file dữ liệu và các thành phần được sản phẩm hỗ trợ | Truy vấn hợp lệ có thể trả plaintext; cần xét riêng dump logic |
| Mã hóa trường ở ứng dụng | Database có thể chỉ nhận ciphertext của trường nhạy cảm | Ứng dụng có quyền giải mã vẫn thấy plaintext |
| Mã hóa backup | Bảo vệ bản sao lưu theo cơ chế backup | Khóa backup và các bản export khác cũng cần được quản lý |

Ví dụ, raw token được lưu trong cột `token_value` của database có TDE. Khi một công cụ xuất dữ liệu thực hiện truy vấn và ghi kết quả ra CSV, dữ liệu xuất có thể chứa token đọc được. TDE không tự mã hóa nội dung của mọi file được công cụ bên ngoài tạo ra.

Ngược lại, nếu ứng dụng đã mã hóa trường token trước khi gửi đến database, một dump chỉ chứa ciphertext của trường đó sẽ cần quyền truy cập khóa để giải mã.

Bảo đảm này phụ thuộc việc phân tách quyền. Nếu cùng một tài khoản có thể tải toàn bộ dump và gọi API giải mã không giới hạn, lợi ích cách ly bị giảm đáng kể.

## 4. Dùng mã hóa có xác thực và quản lý nonce đúng cách

Khi cần lưu token có thể giải mã, nên sử dụng một cơ chế **AEAD — Authenticated Encryption with Associated Data** đã được thư viện hỗ trợ, chẳng hạn AES-GCM.

Mô hình:

```text
ciphertext, authenticationTag = AEAD_Encrypt(
    key,
    nonce,
    plaintextToken,
    associatedData
)
```

Khi đọc lại:

```text
plaintextToken = AEAD_DecryptAndVerify(
    key,
    nonce,
    ciphertext,
    authenticationTag,
    associatedData
)
```

Nếu kiểm tra toàn vẹn thất bại, dữ liệu không được dùng để dựng liên kết hoặc thực hiện khôi phục. Không trả về plaintext từng phần và không tự chuyển sang cách giải mã yếu hơn.

### Vai trò của từng thành phần

- **Key:** bí mật quyết định khả năng giải mã.
- **Nonce hoặc IV:** dữ liệu dùng cho lần mã hóa; không cần giữ bí mật, nhưng phải đáp ứng yêu cầu của thuật toán.
- **Ciphertext:** phần dữ liệu đã mã hóa.
- **Authentication tag:** dữ liệu để kiểm tra toàn vẹn.
- **AAD:** dữ liệu không mã hóa nhưng được đưa vào kiểm tra toàn vẹn.

Với AES-GCM, nonce không được lặp lại dưới cùng một khóa. Một cấu hình minh họa là nonce 12 byte và tag 128 bit. Nếu sinh nonce ngẫu nhiên, vẫn phải xét xác suất trùng, tổng số lần dùng khóa, nhiều instance và cơ chế luân chuyển; ngẫu nhiên không tạo ra bảo đảm duy nhất tuyệt đối.

Không dùng cùng một nonce cố định cho mọi token. Không lấy account ID rồi dùng mãi làm nonce khi mỗi tài khoản có thể nhận nhiều token.

Nonce được lưu cùng ciphertext. Việc giấu nonce không sửa được lỗi tái sử dụng nonce.

## 5. Ràng buộc ciphertext với ngữ cảnh bằng AAD

Một ciphertext không nên được chuyển tùy ý từ bản ghi này sang bản ghi khác mà vẫn có thể được dùng cho một đối tượng khác.

AAD có thể chứa những thuộc tính ổn định như:

```text
AAD = canonicalEncode(
    schemaVersion,
    tokenRecordId,
    tenantId,
    accountId,
    purpose
)
```

Khi giải mã, máy chủ dựng lại đúng AAD từ ngữ cảnh mong đợi và các tham chiếu có thẩm quyền. Nếu ciphertext bị chuyển từ token của A sang bản ghi của B mà AAD mong đợi không khớp, kiểm tra tag phải thất bại.

Cần lưu ý:

1. Cách mã hóa AAD phải có ranh giới trường rõ ràng, kiểu dữ liệu ổn định và quy tắc phiên bản.
2. AAD được xác thực nhưng không được che giấu; không đưa bí mật vào đó với kỳ vọng được mã hóa.
3. Việc thay một trường AAD có thể yêu cầu mã hóa lại dữ liệu với nonce mới.
4. Một biến trạng thái thường xuyên thay đổi, như số lần gửi, không nên vô tình làm mọi ciphertext không thể đọc lại.
5. AAD không thay thế kiểm tra tenant, account và quyền của bên yêu cầu giải mã.

Nếu kẻ tấn công thay toàn bộ ciphertext cùng tất cả metadata mà ứng dụng tiếp nhận mù quáng, chỉ có AAD chưa đủ để bảo đảm đối tượng đúng. Ứng dụng phải gắn bản ghi với ngữ cảnh được xác định tin cậy, thay vì lấy tài khoản đích từ một gói dữ liệu tự khai.

### Một envelope lưu trữ minh họa

```json
{
  "schemaVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyVersion": "delivery-key-v3",
  "tokenRecordId": "rt_demo_42",
  "nonce": "BASE64URL_CUA_NONCE",
  "ciphertextAndTag": "BASE64URL_CUA_CIPHERTEXT_VA_TAG"
}
```

Các giá trị trên chỉ là placeholder. Trong ví dụ, tag được đóng gói cùng ciphertext theo quy ước thư viện; không được làm mất tag khi tách hoặc chuyển định dạng.

`keyVersion` là định danh, không phải khóa bí mật. Bên đọc cần kiểm tra nó thuộc tập phiên bản khóa và thuật toán được ứng dụng cho phép. Không để dữ liệu lưu trữ tự chỉ định một thuật toán tùy ý hoặc một khóa ngoài phạm vi dịch vụ.

## 6. Ví dụ Java: mã hóa một payload token bằng AES-GCM

Ví dụ dưới đây dùng API JCE có sẵn, minh họa thao tác mã hóa và giải mã một payload nhỏ. `SecretKey` được cung cấp từ tích hợp quản lý khóa phù hợp; ví dụ không tạo khóa cố định trong mã nguồn.

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class RecoveryPayloadCipher {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record EncryptedPayload(
            byte[] nonce,
            byte[] ciphertextAndTag) {}

    public static EncryptedPayload encrypt(
            SecretKey dataKey,
            byte[] plaintext,
            byte[] aad) throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        return new EncryptedPayload(nonce, cipher.doFinal(plaintext));
    }

    public static byte[] decrypt(
            SecretKey dataKey,
            EncryptedPayload payload,
            byte[] expectedAad) throws GeneralSecurityException {

        if (payload.nonce().length != NONCE_BYTES
                || payload.ciphertextAndTag().length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Invalid payload format");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, payload.nonce()));
        cipher.updateAAD(expectedAad);

        return cipher.doFinal(payload.ciphertextAndTag());
    }
}
```

Theo tài liệu Java, các chế độ AEAD xác thực cả ciphertext và AAD; tag được kiểm tra khi giải mã. AAD phải được cung cấp trước dữ liệu cần xử lý. Xem [Java SE 21 — Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html).

Các điều kiện sử dụng của đoạn mã:

- Ứng dụng chọn đúng khóa AES đã quản lý, chẳng hạn khóa 256 bit theo cấu hình của ví dụ envelope.
- Bên gọi giải mã tự xác định `expectedAad` từ ngữ cảnh tin cậy.
- Metadata như phiên bản schema và khóa được quản lý bên ngoài kiểu dữ liệu nhỏ trong ví dụ.
- Bên gọi giới hạn kích thước payload trước khi xử lý.
- Cần kiểm soát tổng số lần mã hóa và cơ chế sinh nonce dưới mỗi khóa.
- Khi có lỗi xác thực tag, không gửi token, không dùng dữ liệu và không ghi plaintext vào log lỗi.

Record trong ví dụ chỉ đóng gói hai mảng byte để thể hiện luồng API. Khi truyền qua nhiều thành phần, cần quản lý quyền sửa và sao chép các mảng, cùng vòng đời của dữ liệu nhạy cảm.

Không dùng `Cipher` chia sẻ giữa nhiều request đồng thời. Ví dụ tạo một đối tượng mới cho mỗi thao tác và chỉ nhận plaintext sau `doFinal` thành công.

Đoạn mã này không cung cấp API cấp quyền giải mã cho người dùng. Quyền truy cập, lựa chọn bản ghi, trạng thái token và việc gửi thông điệp vẫn phải được kiểm tra ở lớp dịch vụ.

## 7. Quản lý khóa và envelope encryption

Mã hóa trường chỉ có ý nghĩa khi kẻ đọc dữ liệu không mặc nhiên có cùng quyền sử dụng khóa. Cần xác định riêng:

- Ai có thể đọc ciphertext?
- Dịch vụ nào được phép giải mã?
- Dịch vụ nào chỉ cần kiểm chứng token?
- Ai có quyền đổi chính sách khóa?
- Những lần sử dụng khóa nào được ghi nhận và cảnh báo?

Một mô hình envelope encryption gồm:

```text
raw token
    -- mã hóa bằng DEK --> ciphertext token

DEK
    -- bảo vệ bằng KEK trong KMS/HSM --> wrapped DEK
```

DEK là khóa mã hóa dữ liệu; KEK bảo vệ DEK. Wrapped DEK có thể được lưu cùng ciphertext khi KEK được bảo vệ riêng và việc unwrap bị kiểm soát.

Tùy kiến trúc, DEK có thể dành cho một payload, một nhóm nhỏ hoặc một khoảng thời gian. Lựa chọn này ảnh hưởng số lần gọi hệ thống khóa, phạm vi ảnh hưởng khi lộ khóa và khả năng xóa dữ liệu theo nhóm.

Không lưu raw DEK hoặc KEK cạnh ciphertext trong cùng một bản export. Không đặt khóa thật vào repository, câu lệnh SQL mẫu, log cấu hình hoặc một endpoint trả cấu hình chẩn đoán.

Bộ phận gửi thông điệp có thể cần quyền giải mã payload chờ gửi. Bộ phận kiểm tra token khi người dùng hoàn tất khôi phục có thể chỉ cần kho verifier. Việc tách quyền này hạn chế số tiến trình có thể lấy lại bí mật.

Một KMS kiểm soát khóa không tự loại bỏ mọi rủi ro từ ứng dụng đã bị chiếm quyền. Nếu tiến trình có quyền gọi giải mã, kẻ kiểm soát tiến trình có thể lợi dụng quyền đó trong phạm vi được cấp. Cần giới hạn principal, khóa, môi trường, mục đích và khả năng truy cập dữ liệu.

## 8. Luồng phát hành, gửi và xóa bản có thể giải mã

Một luồng minh họa cho đặt lại mật khẩu:

```text
1. Máy chủ tạo token bí mật bằng nguồn ngẫu nhiên mật mã.
2. Ghi verifier và metadata cấp quyền vào kho kiểm chứng.
3. Mã hóa payload cần gửi với khóa và AAD đã chọn.
4. Lưu payload mã hóa cùng ý định gửi trong ranh giới nhất quán.
5. Worker được phép đọc lấy payload chờ gửi.
6. Worker kiểm tra yêu cầu còn cho phép gửi.
7. Giải mã và xác thực payload.
8. Gửi liên kết qua kênh đã chọn bằng kết nối được bảo vệ.
9. Xóa bản token có thể giải mã khi không còn cần cho việc gửi.
```

Việc ghi token và ý định gửi cần tránh tình trạng email đã chứa token nhưng không có bản ghi kiểm chứng tương ứng, hoặc token được cấp mà công việc gửi bị mất. Khi hai phần nằm cùng database, transactional outbox là một lựa chọn để ghi chúng nhất quán.

Payload outbox phải được mã hóa trước khi lưu nếu mục tiêu là không để kho này giữ raw token. Mã hóa thông điệp chỉ sau khi đã đọc raw payload từ outbox không bảo vệ bản đã được ghi trước đó.

### Retry và dead-letter queue

Retry có thể cần giữ payload mã hóa trong một khoảng ngắn. Kho retry và dead-letter queue cũng nằm trong phạm vi lưu trữ cần bảo vệ.

Không để worker bắt exception rồi ghi toàn bộ URL khôi phục vào log. Không tự giải mã payload để đưa vào công cụ hỗ trợ xem lỗi.

Khi retry, worker kiểm tra lại thời hạn và trạng thái hiện hành. Việc giải mã thành công không chứng minh token vẫn còn quyền sử dụng.

Giữa lúc worker kiểm tra trạng thái và lúc thông điệp được chuyển đi, token vẫn có thể bị thu hồi hoặc tiêu thụ. Vì vậy, endpoint sử dụng token phải kiểm tra trạng thái có thẩm quyền; nhận được email không bảo đảm liên kết còn dùng được.

### Gửi lại thông điệp

Nếu bản có thể giải mã đã được xóa, verifier không giúp lấy lại token ban đầu. Hệ thống cần một chính sách gửi lại rõ ràng, chẳng hạn tạo token mới theo cùng các kiểm soát chống lạm dụng và thu hồi phù hợp.

Không giữ raw token dài hạn chỉ để một chức năng gửi lại tùy ý có thể hoạt động. Thời gian lưu cần xuất phát từ yêu cầu gửi cụ thể.

Một nhà cung cấp email hoặc SMS sẽ có thể nhìn thấy nội dung mà dịch vụ chuyển cho họ. Mã hóa trong database không che token khỏi chính bên được giao nhiệm vụ chuyển thông điệp; quyền truy cập và retention của kênh gửi cũng cần được xem xét.

## 9. Luân chuyển khóa, sự cố và khôi phục backup

### Luân chuyển định kỳ

Một cơ chế thường dùng:

```text
khóa phiên bản mới:
    dùng để mã hóa payload mới

khóa phiên bản cũ:
    chỉ giữ quyền giải mã trong giai đoạn còn cần dữ liệu cũ
```

Nếu payload token tồn tại rất ngắn, có thể chờ các payload cũ được gửi, hết hạn hoặc xóa rồi ngừng giữ quyền giải mã cũ. Nếu cần mã hóa lại, phải tạo nonce mới và thay envelope bằng thao tác tránh ghi đè cập nhật đang diễn ra.

Luân chuyển KEK bằng cách rewrap DEK có thể không cần mã hóa lại ciphertext token. Luân chuyển DEK là một thao tác khác và cần đánh giá riêng.

Luân chuyển khóa không được gia hạn token hoặc làm sống lại yêu cầu đã kết thúc.

### Khi khóa bị lộ

Cần xác định những payload, tenant, khoảng thời gian và bản sao liên quan. Dừng dùng khóa bị ảnh hưởng cho dữ liệu mới và xử lý các quyền khôi phục có nguy cơ đã bị lộ theo chính sách sự cố.

Chỉ mã hóa lại bằng khóa mới không thu hồi một token mà kẻ tấn công đã giải mã. Muốn ngăn token đó sử dụng, phải thay đổi trạng thái cấp quyền có thẩm quyền hoặc phiên bản thu hồi tương ứng.

OWASP phân biệt việc quản lý khóa bị lộ với việc luân chuyển thông thường, đồng thời nêu giới hạn của xóa khóa khi vẫn còn bản sao có thể khôi phục. Xem [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html#key-compromise-and-recovery).

### Khi khôi phục backup

Một backup có thể chứa token từng ở trạng thái ACTIVE, nhưng token đó đã được dùng hoặc thu hồi sau thời điểm backup.

Khôi phục backup không được làm quyền cũ hoạt động trở lại. Trước khi mở dịch vụ, cần một quy trình đối soát hoặc vô hiệu hóa token đã khôi phục phù hợp với kiến trúc, thời gian hiện tại và nguồn trạng thái có thẩm quyền.

Đây là vấn đề tính mới của trạng thái, không được giải quyết chỉ bằng việc ciphertext có tag hợp lệ.

Cũng cần lập kế hoạch khả dụng khóa: backup mã hóa nhưng không còn cách truy cập khóa cần thiết có thể không sử dụng được. Ngược lại, giữ mọi khóa cũ vô thời hạn làm tăng phạm vi dữ liệu có thể bị lộ.

## 10. Thời gian lưu, bản sao và dữ liệu trong bộ nhớ

Mỗi nơi lưu cần có mục đích và thời gian giữ rõ ràng:

| Nơi lưu | Dữ liệu nên được xem xét |
| --- | --- |
| Database chính | Verifier, metadata cấp quyền và payload mã hóa nếu còn cần |
| Cache | Token hoặc plaintext có vô tình được cache không? |
| Queue và outbox | Payload chờ gửi, retry và dead-letter |
| Log và trace | Query string, request body, exception và span attribute |
| File export | Bản dump logic, CSV và file hỗ trợ xử lý sự cố |
| Backup | Ciphertext, khóa bảo vệ, thời gian giữ và quy trình restore |
| Bộ nhớ tiến trình | Token đã giải mã, DEK và các bản sao tạm |

TTL của một kho dữ liệu có thể phục vụ dọn dẹp, nhưng endpoint vẫn phải kiểm tra thời hạn sử dụng token. Một ciphertext chưa bị xóa sau hạn không được làm token tiếp tục hợp lệ.

Xóa một dòng database không bảo đảm ngay lập tức mọi bản sao vật lý, transaction log hoặc backup đã bị xóa. Nếu dùng xóa bằng cách hủy khóa, cần bảo đảm không còn bản sao khóa có thể dùng, wrapped key có thể mở hoặc plaintext đã được lưu ở nơi khác.

Dùng một khóa chung cho nhiều payload cũng ảnh hưởng độ chi tiết của việc hủy khóa: hủy nó có thể làm mất khả năng đọc dữ liệu khác vẫn còn cần. Phạm vi khóa phải được thiết kế phù hợp với yêu cầu retention.

Trong Java, giảm việc chuyển token và khóa thành chuỗi bất biến có thể giúp hạn chế một số bản sao khó kiểm soát. Ghi đè một mảng byte chỉ là nỗ lực tốt nhất trong môi trường quản lý bộ nhớ; không được coi đó là bảo đảm đã xóa mọi bản sao khỏi heap, swap hoặc crash dump.

Mã hóa tại nơi lưu cũng cần đi cùng bảo vệ đường truyền. Không giải mã token rồi gửi nó qua một kết nối nội bộ không được bảo vệ chỉ vì hai dịch vụ nằm cùng mạng.

## 11. Các tình huống cần có kết quả rõ ràng

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Chỉ cần kiểm tra token khi hoàn tất | Ưu tiên thiết kế không cần lấy lại raw token |
| Có nhu cầu gửi bất đồng bộ | Giữ payload có thể giải mã trong phạm vi và thời gian cần thiết |
| Ciphertext hoặc tag bị sửa | Từ chối dữ liệu; không gửi hoặc sử dụng plaintext |
| AAD khác tài khoản hoặc tenant | Không chấp nhận ciphertext như dữ liệu của đối tượng mới |
| Metadata yêu cầu thuật toán không được cho phép | Từ chối định dạng ngoài hợp đồng |
| Không truy cập được hệ thống khóa | Xử lý lỗi có kiểm soát; không lưu hay gửi plaintext làm phương án tạm |
| Token giải mã được nhưng đã bị thu hồi | Không chấp nhận quyền sử dụng token |
| Retry sau khi token hết hạn | Không gửi như một quyền còn hiệu lực |
| Khóa bị lộ và token có thể đã bị đọc | Xử lý cả khóa lẫn trạng thái quyền, không chỉ mã hóa lại |
| Backup đưa lại trạng thái ACTIVE cũ | Không phục hồi quyền khôi phục đã kết thúc |
| Dữ liệu chỉ được Base64 | Không coi đó là mã hóa bảo mật |

Một thiết kế lưu trữ token cần trả lời được: **vì sao cần bản có thể giải mã, ai được phép giải mã, ciphertext gắn với ngữ cảnh nào, khóa được quản lý ra sao và mọi bản sao tồn tại bao lâu**. Với token chỉ cần kiểm chứng, loại bỏ nhu cầu lưu bí mật có thể khôi phục thường giúp giảm đáng kể phạm vi cần bảo vệ.
