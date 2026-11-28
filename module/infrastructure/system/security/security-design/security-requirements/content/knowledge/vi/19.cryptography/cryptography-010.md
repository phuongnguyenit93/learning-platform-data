# Message authentication code

## 1. MAC giải quyết vấn đề gì?

Message Authentication Code, viết tắt MAC, là một giá trị xác thực được tính từ thông điệp và khóa bí mật. Bên có quyền sử dụng khóa kiểm tra giá trị này để phát hiện thông điệp bị thay đổi hoặc bị tạo giả bởi bên không có khả năng tạo MAC hợp lệ.

Mô hình đơn giản:

```text
T = MAC(K, M)

Verify(K, M, T) → ACCEPT hoặc REJECT
```

Trong đó:

- K là khóa bí mật.
- M là chuỗi byte cần được xác thực.
- T là authentication tag.
- ACCEPT chỉ có ý nghĩa trong phạm vi thông điệp, khóa và hợp đồng đã định nghĩa.

MAC bảo vệ tính toàn vẹn và xác thực thông điệp theo khóa. Nó không mã hóa nội dung.

Đối với thiết kế yêu cầu bảo mật, câu hỏi quan trọng là:

> Những byte nào và ngữ cảnh nào phải được xác thực trước khi hệ thống được phép sử dụng thông điệp?

Nếu chỉ ghi “thêm HMAC vào request”, một hệ thống vẫn có thể bỏ sót body, tenant, mục đích hoặc kiểm soát replay.

### 1.1. Ví dụ nghiệp vụ

Một dịch vụ nhận sự kiện:

```json
{
  "eventId": "event-example-010",
  "accountId": "account-example",
  "action": "DOCUMENT_PUBLISHED"
}
```

Nếu bên nhận chỉ tin body vì request tới đúng URL, một bên khác có thể gửi nội dung giống vậy. Một MAC hợp lệ theo khóa của đúng tích hợp có thể là một phần của bằng chứng nguồn thông điệp.

Nhưng tag hợp lệ chưa chứng minh sự kiện mới, chưa được xử lý hoặc được phép ảnh hưởng mọi account. Các điều kiện đó phải được đặc tả riêng.

### 1.2. Những tài sản thường cần MAC

- Tính toàn vẹn của webhook hoặc message.
- Ngữ cảnh của một request tích hợp.
- Metadata lưu ngoài vùng tin cậy.
- Cấu trúc dữ liệu cần phát hiện sửa đổi.
- Nội dung được xác thực tại lớp ứng dụng qua nhiều thành phần.

Không phải mọi trường hợp đều nên dùng MAC đối xứng. Nếu nhiều bên cần kiểm chứng công khai nhưng không được tạo thông điệp, chữ ký số có thể phù hợp hơn. Lựa chọn phải xuất phát từ quan hệ tin cậy và quyền của các bên.

## 2. Phân biệt MAC, hash, encryption và chữ ký số

| Cơ chế | Khóa | Bảo đảm chính | Không tự cung cấp |
|---|---|---|---|
| Hash không khóa | Không | Digest của dữ liệu | Xác thực trước bên có thể sửa cả dữ liệu và digest |
| MAC | Khóa bí mật | Toàn vẹn và xác thực thông điệp theo khóa | Bí mật, freshness hoặc quyền nghiệp vụ |
| Encryption chỉ bảo mật | Khóa | Bí mật theo cơ chế | Không mặc định có xác thực dữ liệu |
| AEAD | Khóa và tham số theo thuật toán | Bí mật cùng xác thực dữ liệu/ngữ cảnh | Authorization và chống replay toàn diện |
| Chữ ký số | Khóa riêng và khóa công khai | Xác minh bằng khóa công khai theo cơ chế chữ ký | Tự động chứng minh mọi yếu tố pháp lý hoặc quyền nghiệp vụ |

### 2.1. Hash không khóa không ngăn người sửa dữ liệu tính lại

Giả sử một file đi cùng SHA-256 của chính nó. Nếu bên tấn công sửa được cả file và digest, họ có thể tính digest mới cho dữ liệu đã sửa.

Hash có thể hỗ trợ kiểm tra khi digest chuẩn được nhận từ một nguồn đáng tin. Nhưng một digest nằm cạnh dữ liệu trong cùng vùng có thể sửa không tự là bằng chứng xác thực.

MAC thêm một khóa mà bên không được phép không có. Đây là thay đổi của mô hình tin cậy, không chỉ là một định dạng checksum khác.

### 2.2. MAC không làm thông điệp bí mật

Body và tag có thể được gửi ở dạng rõ. Ai đọc được body vẫn biết nội dung, dù không tạo được tag hợp lệ.

Nếu dữ liệu cần bí mật trên mạng, cần HTTPS hoặc kênh bảo vệ phù hợp. Nếu cần bí mật trong storage hoặc ở lớp ứng dụng, phải có thiết kế encryption, thường cân nhắc AEAD cho nhu cầu kết hợp bí mật và xác thực.

Không dùng câu “đã ký HMAC nên thông tin cá nhân được mã hóa”.

### 2.3. Khóa chung không phân biệt mọi bên giữ khóa

Nếu hai bên cùng biết raw shared secret, cả hai đều có khả năng tính MAC hợp lệ bằng khóa đó. Vì vậy, MAC không tạo cùng mô hình bằng chứng như chữ ký được kiểm chứng bằng public key.

Một dịch vụ quản lý khóa có thể cung cấp quyền verify mà không cho workload lấy khóa hoặc gọi generate-MAC. Đây là giới hạn truy cập API có ích, nhưng primitive mật mã vẫn là đối xứng.

Nếu cần truy vết người tạo cụ thể, phải thiết kế định danh, scope khóa và audit phù hợp. Không dùng một shared secret toàn công ty để tuyên bố xác định chính xác cá nhân nào đã tạo dữ liệu.

## 3. HMAC là một họ MAC dựa trên hash

HMAC kết hợp khóa bí mật với một hàm hash theo cấu trúc đã được phân tích. Cơ chế được mô tả trong [RFC 2104](https://www.rfc-editor.org/rfc/rfc2104.html).

Một profile có thể chọn HMAC-SHA-256. Điều này khác với tự tính:

```text
SHA-256(secret || message)
```

hoặc:

```text
SHA-256(message || secret)
```

Những phép ghép tự thiết kế không được coi là HMAC. Không thay một primitive có cấu trúc bằng một công thức trông tương tự.

### 3.1. MAC không đồng nghĩa với mọi thuật toán HMAC

MAC là khái niệm rộng hơn HMAC. Một hệ thống có thể có những họ MAC khác, với yêu cầu về tham số và cách sử dụng khác.

Trong bài này, các ví dụ triển khai chọn một profile HMAC-SHA-256 cụ thể để dễ diễn đạt. Không suy rộng rằng mọi MAC đều có cùng độ dài tag, yêu cầu nonce hoặc API như HMAC.

### 3.2. Chọn profile đầy đủ

Ví dụ profile ứng dụng giả định:

```text
Mục đích: xác thực message của một tích hợp đã định danh
Thuật toán: HMAC-SHA-256
Khóa: 256 bit từ nguồn mật mã được quản lý
Tag: toàn bộ 32 byte
Dữ liệu: byte string theo schema xác thực phiên bản 1
Encoding tag: một dạng được quy định thống nhất
Giới hạn message: hữu hạn theo endpoint
Replay: timestamp và event ID theo hợp đồng riêng
```

Đây là ví dụ yêu cầu, không phải một giao thức webhook hoàn chỉnh có thể áp dụng nguyên vẹn cho mọi đối tác.

Cần chọn thuật toán và môi trường thực thi theo baseline mật mã hiện hành của sản phẩm. Những ví dụ thuật toán trong một tài liệu lịch sử không tự là khuyến nghị cho hệ thống mới.

### 3.3. Tag đầy đủ hoặc tag rút gọn

Nếu profile dùng toàn bộ HMAC-SHA-256, tag có 32 byte. Không nhận mọi độ dài từ 1 đến 32 rồi so sánh phần đầu mà client gửi.

Nếu một giao thức đã thiết kế tag rút gọn, độ dài phải được cố định và đánh giá theo mức bảo đảm, số lần thử cùng các giới hạn liên quan. Không rút tag vì muốn header ngắn hơn mà không có quyết định mật mã.

Tên thuật toán, độ dài tag và key type cần được gắn với nhau trong profile; caller không được tự nới lỏng qua một trường alg.

## 4. Xác thực đúng thông điệp: vấn đề byte và ngữ cảnh

### 4.1. MAC hoạt động trên byte

Hai văn bản JSON có thể mang cùng ý nghĩa nghiệp vụ nhưng khác byte:

```json
{"a":1,"b":2}
```

và:

```json
{
  "b": 2,
  "a": 1
}
```

Nếu MAC được tính trên body byte gốc, tag của hai biểu diễn không được kỳ vọng giống nhau.

Bên nhận không nên parse rồi serialize lại bằng một thư viện khác trước khi xác minh, trừ khi giao thức quy định một canonicalization rõ ràng mà cả hai bên cùng thực hiện.

### 4.2. Hai mô hình dữ liệu cần phân biệt

| Mô hình | Điều phải đặc tả |
|---|---|
| MAC trên byte gốc | Chính xác những byte nào được giữ lại và xác minh |
| MAC trên biểu diễn chuẩn | Cách chuẩn hóa, schema, charset, thứ tự và kiểu dữ liệu |

Mô hình thứ hai không đơn giản là “sort key JSON”. Cần xử lý số, Unicode, field lặp, giá trị rỗng, trường vắng mặt và những quy tắc parser có thể khác nhau.

Nếu tích hợp đã có giao thức chuẩn, phải dùng đúng cách tạo dữ liệu xác thực của giao thức đó.

### 4.3. Những biến đổi trên đường đi

Cần xác định tác động của:

- Content encoding và giải nén.
- Charset và chuyển đổi string/byte.
- Chuẩn hóa kết thúc dòng.
- Proxy viết lại path hoặc query.
- JSON middleware đọc body trước verifier.
- Message broker thêm hoặc thay metadata.

Không nên yêu cầu MAC trên “request ban đầu” mà không nói về biểu diễn tại điểm tạo và điểm xác minh.

Framing HTTP theo hop và nội dung ứng dụng là hai lớp khác nhau. Giao thức cần xác định body bytes được xác thực, thay vì yêu cầu mọi TCP segment hoặc chunking đều giữ nguyên qua proxy.

### 4.4. Chỉ bảo vệ body có thể bỏ sót ý nghĩa request

Cùng một body có thể có ý nghĩa khác nếu được gửi tới action, account hoặc endpoint khác.

Đặc tả cần xem xét những thành phần điều khiển ý nghĩa, chẳng hạn:

- Version của giao thức xác thực.
- Mục đích hoặc loại sự kiện.
- Tích hợp và audience.
- Tenant hoặc account.
- Method và target nếu gắn với HTTP request.
- Content type khi nó quyết định cách diễn giải.
- Body hoặc digest được kiểm tra đúng.
- Timestamp, event ID hoặc nonce theo policy replay.

Không phải mọi hệ thống cần tất cả trường trên. Nhưng mọi trường có thể đổi ý nghĩa được bảo vệ phải được đánh giá, không chỉ chọn những trường tiện ký.

### 4.5. Cách ghép phải không nhập nhằng

Không dùng phép nối chuỗi tùy tiện:

```text
accountId + action + timestamp + body
```

nếu không có cách phân tách xác định. Những bộ giá trị khác nhau có thể tạo cùng một chuỗi sau khi ghép.

Có thể dùng một encoding có version, độ dài và kiểu rõ ràng. Nếu chọn một signature base theo chuẩn, cần áp dụng đúng quy tắc tạo base.

Đối với HTTP, [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html) định nghĩa cơ chế xác thực các thành phần thông điệp, bao gồm lựa chọn MAC, cách tạo signature base và yêu cầu của ứng dụng. Đoạn code primitive trong bài không phải implementation của RFC đó.

### 4.6. Digest của body phải khớp body thực

Nếu giao thức xác thực một header chứa digest thay vì trực tiếp đưa body vào MAC, bên nhận vẫn phải kiểm tra digest đó với body đã nhận.

Chỉ xác minh MAC của lời khai “digest=...” nhưng không đối chiếu nội dung thực tế không chứng minh body được xác thực.

Những trường bắt buộc được bảo vệ cũng phải do policy bên nhận xác định. Không chấp nhận một tag chỉ phủ một tập field nhỏ hơn rồi cho rằng toàn request đã được bảo vệ.

## 5. Khóa và danh tính của tích hợp

### 5.1. Key ID là tham chiếu, không phải bằng chứng quyền

Một message có thể mang keyId để bên nhận chọn khóa. Giá trị đó là đầu vào chưa được tin.

Resolver cần:

- Chỉ tìm trong những khóa được cấu hình cho tích hợp.
- Kiểm tra profile và phạm vi sử dụng.
- Không tải secret từ URL hoặc đường dẫn tùy ý do caller cung cấp.
- Không quét mọi khóa trong hệ thống cho tới khi có một tag khớp.
- Không cho phép một key của tenant A xác thực thao tác trong tenant B.

Một keyId có vẻ hợp lệ chỉ giúp tìm ứng viên; policy và MAC hợp lệ mới góp phần vào quyết định chấp nhận.

### 5.2. Nguồn khóa

Khóa phải được tạo bằng cơ chế phù hợp mật mã và bảo vệ theo phân loại bí mật.

Không dùng trực tiếp:

- Tên tổ chức.
- ID đối tác.
- Mật khẩu dễ nhớ.
- Một giá trị mặc định giống nhau cho mọi môi trường.
- Chuỗi cố định được commit vào source code.

Nếu key được lưu dưới dạng Base64, cần decode theo hợp đồng trước khi dùng như key bytes. Không vô tình dùng chính những ký tự của chuỗi Base64 như thể đó là raw key, trừ khi giao thức đã định nghĩa rõ như vậy.

### 5.3. Phạm vi và tách mục đích

Có thể tách khóa theo:

- Đối tác hoặc integration.
- Môi trường production và thử nghiệm.
- Chiều gửi/nhận nếu mô hình cần tránh nhầm hướng.
- Loại giao thức hoặc mục đích.
- Tenant hoặc miền dữ liệu.

Không dùng một key cho mọi chức năng chỉ để giảm số secret. Nếu cần suy dẫn key, dùng cơ chế KDF được thiết kế phù hợp; không tự tạo một phép hash ghép chuỗi làm hệ thống quản lý khóa.

Một domain label trong message giúp ràng buộc mục đích nhưng không thay thế mọi lợi ích của tách key và phân quyền sử dụng key.

### 5.4. Rotation và thời hạn chấp nhận

Cần phân biệt:

- Khóa dùng để tạo MAC mới.
- Những khóa cũ còn được chấp nhận để verify trong giai đoạn chuyển tiếp.
- Thời điểm ngừng chấp nhận.
- Cách xử lý message đang chờ hoặc retry hợp lệ.
- Chính sách khi nghi key bị lộ.

Một thời gian chuyển tiếp phải hữu hạn và có chủ sở hữu. Không giữ mọi khóa cũ làm đường verify vĩnh viễn nếu mục tiêu của rotation là giảm phạm vi rủi ro.

## 6. Ví dụ Java: tạo và kiểm tra HMAC-SHA-256

Đoạn code Java 17 trở lên minh họa primitive trên byte string đã được tạo theo hợp đồng. Key đến từ thành phần quản lý khóa, không phải một secret cố định trong code.

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class HmacSha256 {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TAG_BYTES = 32;
    private static final int MAX_MESSAGE_BYTES = 1_048_576;

    private HmacSha256() {
    }

    public static byte[] createTag(
            SecretKey key,
            byte[] authenticatedMessage
    ) throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        requireMessage(authenticatedMessage);

        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(key);

        byte[] tag = mac.doFinal(authenticatedMessage);

        if (tag.length != TAG_BYTES) {
            throw new GeneralSecurityException(
                    "Unexpected MAC output length"
            );
        }

        return tag;
    }

    public static boolean verifyTag(
            SecretKey key,
            byte[] authenticatedMessage,
            byte[] receivedTag
    ) throws GeneralSecurityException {
        Objects.requireNonNull(key, "key");
        requireMessage(authenticatedMessage);

        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }

        byte[] expectedTag = createTag(key, authenticatedMessage);

        return MessageDigest.isEqual(expectedTag, receivedTag);
    }

    private static void requireMessage(byte[] message) {
        Objects.requireNonNull(message, "authenticatedMessage");

        if (message.length > MAX_MESSAGE_BYTES) {
            throw new IllegalArgumentException(
                    "Authenticated message is too large"
            );
        }
    }
}
```

Cách dùng init, update và doFinal của JCA được mô tả trong [Mac API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html).

### 6.1. Những điểm của hợp đồng

- Thuật toán do ứng dụng cố định, không lấy từ request.
- Key phải có nguồn và phạm vi phù hợp profile.
- Message là byte string đã xác định, không tự serialize bên trong primitive.
- Chỉ chấp nhận tag có đúng độ dài profile.
- Tạo Mac instance cho từng thao tác trong ví dụ, không chia sẻ trạng thái xử lý giữa request.
- Không có fallback sang hash không khóa nếu provider hoặc key lỗi.
- Giới hạn message được kiểm tra trước khi tính toán.

Giới hạn một MiB là ví dụ, không phải giá trị khuyến nghị chung. API thật cần giới hạn cả request thô trước khi tạo byte array, không chỉ sau khi toàn bộ body đã được cấp phát.

### 6.2. So sánh tag

Không so sánh tag bằng String.equals hoặc một vòng lặp tự viết dừng ở byte khác đầu tiên.

Ví dụ dùng MessageDigest.isEqual với expectedTag ở vị trí đầu. Tài liệu Java 17 nêu implementation note rằng việc tính so sánh phụ thuộc độ dài mảng thứ nhất, không phụ thuộc nội dung các mảng. Xem [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)).

Điều đó không chứng minh toàn endpoint có thời gian xử lý giống nhau. Parse, key lookup, replay store và lỗi khác vẫn cần được đánh giá theo threat model.

Kiểm tra độ dài công khai của tag trước so sánh không phải là tiết lộ byte bí mật của expected tag. Điều cần tránh là so sánh nội dung theo cách tạo tín hiệu phụ thuộc vào prefix trùng.

### 6.3. Primitive chưa phải một giao thức hoàn chỉnh

Code không tự cung cấp:

- Canonicalization của HTTP hoặc JSON.
- Parser tag từ header.
- Key resolver.
- Ràng buộc integration, tenant hoặc action.
- Timestamp và chống replay.
- Idempotency.
- Authorization.
- Lưu log hoặc giới hạn tốc độ.
- Cơ chế quản lý secret và rotation.

Không đưa createTag thành một API ký tùy ý cho caller không được phép. Nếu bên ngoài được xin MAC cho mọi thông điệp bằng một key nhạy cảm, ranh giới tin cậy của giao thức có thể bị phá vỡ.

### 6.4. HMAC không có quy tắc nonce như AES-GCM

Với HMAC, việc dùng một key cho nhiều message là cách sử dụng bình thường của primitive. Một message giống hệt dưới cùng key tạo cùng tag theo profile xác định.

Nonce trong một giao thức dùng HMAC thường phục vụ chống replay hoặc ràng buộc giao dịch, không phải yêu cầu không lặp nonce của AES-GCM.

Không sao chép máy móc quy tắc của một thuật toán AEAD sang mọi MAC.

## 7. Parser và xác minh trước khi dùng dữ liệu

### 7.1. Giới hạn metadata trước công việc tốn kém

Một verifier cần kiểm tra:

- Header xác thực có mặt theo hợp đồng.
- Không có tham số lặp hoặc tổ hợp nhập nhằng.
- Key ID, timestamp và tag không vượt độ dài cho phép.
- Encoding tag hợp lệ.
- Sau decode, tag có đúng số byte.
- Body không vượt ngân sách.

Không để một chuỗi tag khổng lồ gây cấp phát lớn rồi mới được so sánh.

Nếu cho nhiều chữ ký trong giai đoạn rotation, số lượng và quy tắc lựa chọn phải có giới hạn. Không coi một danh sách tùy ý từ caller là yêu cầu thử không giới hạn.

### 7.2. Giữ raw body khi giao thức yêu cầu

Middleware có thể cần lấy body bytes theo đúng biểu diễn đã thỏa thuận, tính MAC rồi mới chuyển dữ liệu cho parser nghiệp vụ.

Không dùng một body đã bị middleware khác thay đổi mà không có hợp đồng. Nếu framework chỉ cho đọc stream một lần, cần thiết kế buffer hoặc cơ chế tee có giới hạn.

Một giá trị JSON parse thành công chưa được phép tạo tác dụng phụ nếu MAC chưa được chấp nhận.

### 7.3. Luồng xác minh minh họa

```text
Nhận request trong giới hạn kích thước
    → kiểm tra cú pháp metadata
    → chọn integration/key trong phạm vi đã cấu hình
    → tạo authenticated bytes theo profile
    → kiểm tra MAC
    → kiểm tra freshness và replay theo policy
    → xác định quyền và schema nghiệp vụ
    → thực hiện thao tác có idempotency phù hợp
```

Một số kiểm tra rẻ, như timestamp sai định dạng hoặc request quá lớn, có thể được thực hiện sớm. Điều quan trọng là không coi lời khai chưa xác thực là căn cứ để cấp quyền hoặc tạo tác dụng phụ.

### 7.4. Không trả chi tiết không cần thiết

Response lỗi không nên chứa expected tag, key material hoặc các phần bí mật của dữ liệu xác thực.

Hệ thống vận hành có thể phân biệt các mã như:

```text
MALFORMED_AUTH_METADATA
UNKNOWN_OR_DISALLOWED_KEY
MAC_VERIFICATION_FAILED
MESSAGE_EXPIRED
DUPLICATE_EVENT
KEY_SERVICE_UNAVAILABLE
```

Những mã nội bộ này không nhất thiết được trả nguyên vẹn cho caller. Cần cân bằng khả năng chẩn đoán với chính sách tiết lộ thông tin.

Lỗi key service không được chuyển thành ACCEPT. Nếu hệ thống không xác minh được, phải xử lý theo trạng thái thất bại có kiểm soát.

## 8. Freshness, replay và idempotency

### 8.1. Tag hợp lệ không chứng minh message mới

Một bên ghi lại được body và tag hợp lệ có thể gửi lại chính chúng. MAC vẫn đúng nếu mọi đầu vào không thay đổi.

Cần mô tả những lần gửi lại nào được phép và những tác dụng phụ nào không được lặp.

Ví dụ, webhook retry hợp lệ có thể được nhận nhiều lần nhưng một sự kiện chỉ được áp dụng một lần theo eventId.

### 8.2. Timestamp phải được xác thực và kiểm tra

Nếu timestamp tham gia giới hạn tuổi message:

- Nó phải nằm trong dữ liệu được MAC bảo vệ.
- Có quy ước đơn vị và biểu diễn.
- Có giới hạn chênh lệch đồng hồ theo policy.
- Có cách xử lý timestamp quá cũ hoặc quá xa trong tương lai.
- Có nguồn thời gian được quản lý ở bên xác minh.

Một timestamp không được MAC bảo vệ có thể bị thay đổi. Một timestamp được MAC bảo vệ nhưng không được so với thời gian hiện tại không tự tạo hết hạn.

### 8.3. Nonce hoặc event ID cần trạng thái phù hợp

Nếu policy chống replay dùng nonce:

- Namespace cần gắn với đúng key, integration hoặc chủ thể.
- Việc đánh dấu đã dùng phải phù hợp concurrency.
- Thời gian lưu phải bao phủ cửa sổ replay theo hợp đồng.
- Nhiều instance phải có cách nhìn trạng thái nhất quán cần thiết.
- Khi replay store lỗi, phải có hành vi rõ ràng.

Không ghi nhận một nonce do request chưa xác thực đưa ra như đã dùng nếu điều đó cho phép bên ngoài làm cạn tài nguyên hoặc chặn message hợp lệ.

### 8.4. Check-then-act không đủ khi có race

Luồng:

```text
Kiểm tra event chưa có
    → thực hiện thay đổi
    → đánh dấu đã xử lý
```

có thể cho hai request đồng thời cùng vượt qua bước đầu.

Cần có cơ chế claim/insert nguyên tử, ràng buộc duy nhất hoặc transaction phù hợp. Khi có hệ thống bên ngoài và message queue, thiết kế phải xử lý sự cố giữa các bước theo mô hình nhất quán của sản phẩm.

MAC không giải quyết race condition trong idempotency.

### 8.5. Retry hợp lệ không nhất thiết phải bị báo là tấn công

Một message trùng nhưng hợp lệ có thể được trả kết quả đã xử lý thay vì áp dụng side effect lần nữa, theo hợp đồng tích hợp.

Cần phân biệt:

- Dữ liệu không xác thực.
- Message hết hạn.
- Một replay trái policy.
- Một retry được phép nhưng không được lặp tác dụng phụ.

Điều này giúp đặc tả vừa bảo vệ an toàn vừa giữ khả năng phục hồi giao tiếp.

## 9. Ràng buộc quyền và tránh nhầm ngữ cảnh

### 9.1. MAC hợp lệ cho integration không mở mọi tài nguyên

Sau khi tag được chấp nhận, server vẫn phải xác định integration đó được phép làm gì.

Ví dụ:

```text
Key của đối tác A
    → chỉ nhận sự kiện thuộc account đã đăng ký của A
    → chỉ các loại action được cấu hình
    → không sửa tài nguyên của tenant B
```

Nếu accountId chỉ lấy từ body mà không đối chiếu phạm vi integration, một đối tác có key hợp lệ có thể yêu cầu thao tác ngoài quyền của họ.

### 9.2. Tránh dùng một tag cho nhiều mục đích

Cùng một message không nên tự được chấp nhận ở endpoint có ngữ nghĩa khác chỉ vì MAC đúng.

Có thể cần domain separation bằng key riêng hoặc trường purpose được xác thực. Quy tắc phải nêu rõ endpoint nào, chiều giao tiếp nào và loại dữ liệu nào được chấp nhận.

Một tag được tạo cho nội dung preview không được mặc nhiên cấp quyền phát hành tài liệu.

### 9.3. Public client không giữ được shared secret như backend

Nếu nhúng một secret vào JavaScript phân phối tới mọi trình duyệt, người nhận code có thể lấy nó. Một MAC tạo bằng secret đó không chứng minh request đến từ một backend đáng tin.

Tương tự, secret trong một ứng dụng được phân phối rộng cần được đánh giá theo mô hình client có thể bị phân tích. Không dùng HMAC với key chung trong frontend như bằng chứng người dùng không thể tự tạo request.

### 9.4. Dữ liệu lưu trữ và rollback

Một bản ghi cũ cùng MAC cũ vẫn có thể hợp lệ.

Nếu cần phát hiện storage quay về trạng thái cũ, cần một nguồn version hoặc trạng thái đáng tin ngoài phạm vi mà bên tấn công có thể quay lùi đồng thời. Chỉ đưa version vào cùng bản ghi có MAC không tự giải quyết mọi rollback.

## 10. Chuyển rủi ro thành yêu cầu bảo mật

### 10.1. Yêu cầu mơ hồ

> Webhook phải được ký HMAC.

Phát biểu này chưa xác định key, dữ liệu bao phủ, encoding, thời gian hoặc hành vi khi trùng.

### 10.2. Yêu cầu về profile và dữ liệu bao phủ

> Endpoint sự kiện phải xác minh MAC theo profile integration được quản lý trước khi sử dụng dữ liệu để thay đổi trạng thái. Profile xác định thuật toán, key scope, tag length, authenticated bytes và encoding. Bên nhận yêu cầu đầy đủ những thành phần có ý nghĩa bảo mật, không để caller chọn một tập bao phủ nhỏ hơn.

### 10.3. Yêu cầu về quyền

> Khóa được chọn từ resolver theo integration đã cấu hình. Message hợp lệ chỉ được xử lý trong account, tenant và action được cấp cho integration đó. Key ID và account ID do request gửi không tự là bằng chứng quyền.

### 10.4. Yêu cầu về so sánh và lỗi

> Tag phải được decode theo định dạng hữu hạn, có đúng độ dài profile và được so sánh bằng primitive phù hợp. Sai tag hoặc không xác minh được không tạo tác dụng phụ. Response và log không chứa expected tag, key hoặc dữ liệu nhạy cảm không cần thiết.

### 10.5. Yêu cầu chống replay

> Timestamp và định danh sự kiện tham gia dữ liệu xác thực theo profile. Verifier kiểm tra cửa sổ thời gian và sử dụng cơ chế idempotency nguyên tử trong phạm vi integration. Retry được phép không làm tác dụng phụ bị thực hiện lại.

### 10.6. Mẫu truy vết

```text
ID: CRYPTO-MAC-01
Tài sản:
    tính toàn vẹn sự kiện và trạng thái nghiệp vụ
Rủi ro:
    giả mạo, sửa message hoặc gửi lại ngoài policy
Profile:
    HMAC theo baseline của sản phẩm
Dữ liệu bao phủ:
    context + metadata bắt buộc + nội dung theo schema
Khóa:
    riêng theo integration và môi trường
Điểm thực thi:
    verifier trước xử lý nghiệp vụ
Freshness:
    timestamp cùng policy replay/idempotency
Bằng chứng:
    vector, tampering, sai context, retry và race
Chủ sở hữu:
    nhóm tích hợp, ứng dụng và quản lý khóa
```

## 11. Ma trận rủi ro và bằng chứng chấp nhận

| Rủi ro | Kiểm soát | Bằng chứng |
|---|---|---|
| Sửa body | MAC phủ nội dung đúng biểu diễn | Message thay đổi không được áp dụng |
| Sửa action hoặc target | Bao phủ ngữ cảnh quyết định ý nghĩa | Đổi action/target làm xác minh hoặc policy thất bại |
| Thay digest nhưng bỏ body check | Đối chiếu digest với body thực | Body không khớp không được chấp nhận |
| Chọn key ngoài phạm vi | Resolver hữu hạn và gắn integration | Không gọi key hoặc secret tùy ý |
| Tag ngắn được chấp nhận như prefix | Độ dài cố định | Tag thiếu byte bị từ chối |
| Timing phụ thuộc prefix tag | Primitive so sánh phù hợp | Không có vòng lặp tự dừng sớm theo nội dung |
| Replay message hợp lệ | Cửa sổ thời gian và trạng thái replay | Không có side effect ngoài policy |
| Hai retry chạy đồng thời | Idempotency nguyên tử | Chỉ một thay đổi nghiệp vụ được áp dụng |
| Key cũ được nhận mãi | Rotation có thời hạn | Key hết phạm vi không còn verify được |
| Lộ plaintext do nghĩ MAC là encryption | Kênh và storage bảo mật riêng | Dữ liệu nhạy cảm không được truyền rõ ngoài policy |
| Bên có key yêu cầu sai tenant | Authorization sau xác thực | Không thao tác ngoài phạm vi integration |

## 12. Thiết kế kiểm chứng

Những tình huống sau là cơ sở cho việc kiểm thử khi triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

### 12.1. Known-answer vector

Có thể dùng test vector đã công bố để kiểm tra primitive và provider. [RFC 4231](https://www.rfc-editor.org/rfc/rfc4231.html) cung cấp vector cho các biến thể HMAC SHA-2, gồm HMAC-SHA-256.

Key và dữ liệu cố định trong vector chỉ thuộc bộ thử. Không đưa chúng vào cấu hình tích hợp thật.

Known-answer test kiểm tra một lớp, không chứng minh raw body, key scope hoặc replay policy của endpoint đã đúng.

### 12.2. Dữ liệu hợp lệ và trường hợp biên

Bao phủ:

- Message rỗng nếu profile cho phép.
- Dữ liệu nhị phân.
- Chuỗi tiếng Việt sau khi encode theo charset đã định nghĩa.
- Body ở kích thước tối thiểu và tối đa.
- Đúng tag length.
- Đúng key version trong thời gian chuyển tiếp.
- Những kiểu message và action được hỗ trợ.

Cần biết message byte nào đã được tính, không chỉ so một object sau parse.

### 12.3. Tampering và sai context

| Thay đổi | Kết quả mong đợi |
|---|---|
| Một phần nội dung bị sửa | MAC không được chấp nhận |
| Tag bị sửa | Không thực hiện nghiệp vụ |
| Tag bị cắt ngắn | Từ chối theo profile |
| Encoding tag sai | Lỗi có kiểm soát |
| Dùng key khác | Không chấp nhận |
| Account hoặc purpose khác | Không vượt qua ràng buộc context |
| Timestamp bị sửa | Không được chấp nhận như thông điệp gốc |
| Metadata bắt buộc không được phủ | Verifier từ chối profile không đủ coverage |
| Body khác nhưng giữ digest đã xác thực | Kiểm tra nội dung phát hiện không khớp |

Bảo đảm mật mã có giới hạn theo giả định thuật toán, độ dài tag và ngân sách sử dụng. Không mô tả kết quả như một lời hứa rằng không thể tồn tại bất kỳ giả mạo nào với xác suất tuyệt đối bằng không.

### 12.4. Kiểm tra byte qua framework và proxy

Những đường cần quan sát:

- Request trực tiếp tới verifier.
- Request đi qua proxy thực tế.
- Middleware parse JSON trước hoặc sau verifier.
- Nội dung có khoảng trắng và kết thúc dòng khác.
- Content encoding nếu được hỗ trợ.
- Header hoặc metadata lặp theo nhóm bị cấm.
- Path/query được rewrite theo cấu hình.

Điều kiện đạt là hai bên dùng đúng biểu diễn theo hợp đồng. Không khắc phục lỗi tương thích bằng cách thử nhiều cách serialize hoặc nhiều chuỗi ký tới khi tag khớp.

### 12.5. Replay, race và sự cố

Cần kiểm tra:

- Message vừa trong cửa sổ thời gian.
- Message quá cũ hoặc quá xa trong tương lai.
- Hai bản sao cùng event ID đến đồng thời.
- Retry sau khi side effect đã commit nhưng response bị mất.
- Replay store tạm không khả dụng.
- Key resolver hoặc dịch vụ quản lý khóa lỗi.
- Khóa được rotation trong lúc message đang chờ.
- Message hợp lệ thuộc integration khác.

Không chỉ kiểm tra response code. Cần xác nhận trạng thái, event và thao tác bên ngoài không bị lặp hoặc thực hiện trái policy.

### 12.6. Không có tác dụng phụ trước xác minh

Đối với một message không hợp lệ, cần quan sát:

- Không sửa bản ghi.
- Không phát lệnh xử lý tiếp.
- Không gửi email hoặc webhook nghiệp vụ.
- Không cấp một quyền hoặc token mới.
- Không ghi dữ liệu chưa xác thực vào cache được coi là tin cậy.
- Không lưu log làm lộ secret hoặc thông điệp nhạy cảm.

Một response báo lỗi nhưng đã enqueue công việc như hợp lệ không đáp ứng yêu cầu.

## 13. Vận hành và quản lý thay đổi

### 13.1. Chỉ số cần theo dõi

Có thể theo dõi theo endpoint và integration:

- Số message hợp lệ.
- Tỷ lệ MAC verification thất bại.
- Lỗi metadata hoặc tag encoding.
- Message hết hạn.
- Retry và duplicate được xử lý.
- Lỗi key resolver, provider hoặc replay store.
- Sử dụng key cũ trong giai đoạn chuyển tiếp.
- Thời gian tạo authenticated bytes và tính MAC.

Không ghi toàn bộ secret, expected tag hoặc body nhạy cảm để tìm lỗi. Tag của một message có thể bị phát lại trong một số giao thức, nên cũng cần phân loại trước khi lưu.

### 13.2. Rotation không làm mất tương thích âm thầm

Khi đổi key hoặc profile:

- Bên tạo dùng version mới theo kế hoạch.
- Bên nhận có danh sách chấp nhận hữu hạn.
- Message đang chờ có hành vi rõ.
- Thời điểm ngừng key cũ được theo dõi.
- Không bỏ verification khi có lỗi rollout.

Nếu thêm một version mới của canonicalization, phải có định danh và mapping rõ. Không tự đoán phiên bản từ việc lần verify đầu thất bại.

### 13.3. Khi nghi khóa bị lộ

Cần xác định integration, môi trường, thông điệp và khả năng tạo giả trong phạm vi key liên quan.

Quy trình có thể gồm ngừng cấp MAC mới, thu hồi hoặc đổi key, cập nhật verifier và điều tra tác dụng phụ. Không chỉ thay tên keyId trong khi key material thực tế giữ nguyên rồi coi bí mật đã được thay.

MAC hợp lệ trong thời gian key bị lộ không tự là bằng chứng nguồn đáng tin. Kết luận điều tra cần cân nhắc những nguồn dữ liệu độc lập.

### 13.4. Những thay đổi cần đánh giá lại

- Thêm một loại action.
- Thêm account hoặc tenant vào tích hợp.
- Đổi JSON serializer hoặc middleware.
- Thêm compression hoặc proxy rewrite.
- Đổi encoding của tag.
- Nới danh sách key/profile được chấp nhận.
- Đổi cửa sổ thời gian hoặc replay store.
- Tách/gộp endpoint hoặc chiều giao tiếp.

Mỗi thay đổi có thể làm phạm vi dữ liệu xác thực khác đi, dù lời gọi Mac trong code không đổi.

## 14. Những sai lầm thường gặp

### 14.1. Dùng hash ghép secret thay HMAC

Tên gọi không biến một công thức tự tạo thành HMAC. Dùng primitive và profile đã được thiết kế.

### 14.2. Ký một phần nhưng sử dụng cả message

Một trường không được bảo vệ có thể thay đổi ý nghĩa dù tag của phần còn lại hợp lệ. Verifier phải yêu cầu coverage phù hợp với hành động.

### 14.3. Parse rồi serialize lại không có canonicalization

Biến đổi byte ngoài hợp đồng làm hai bên không xác minh cùng dữ liệu. Giữ raw bytes hoặc dùng một chuẩn hóa đã định nghĩa đầy đủ.

### 14.4. So sánh tag như văn bản thông thường

Encoding là lớp biểu diễn; xác minh cần byte đúng độ dài và primitive so sánh phù hợp. Không chấp nhận prefix hoặc nhiều encoding tùy ý để “linh hoạt”.

### 14.5. Tag đúng thì bỏ phân quyền

Khóa integration chỉ có phạm vi được cấp. Không mở quyền chéo account, tenant hoặc action vì MAC hợp lệ.

### 14.6. MAC tự chống replay

Không có trạng thái hoặc freshness policy, bản sao message vẫn có thể hợp lệ. Thiết kế replay và idempotency riêng.

### 14.7. Đưa shared secret vào frontend

Một secret được phân phối cho mọi client không còn là căn cứ để phân biệt backend đáng tin với người dùng tự tạo request.

### 14.8. Verification lỗi thì tiếp tục xử lý

Fail-open phá bỏ toàn bộ kiểm soát. Mất khả năng xác minh phải dẫn đến hành vi có kiểm soát, không trở thành một ngoại lệ cho phép.

## 15. Điểm cần ghi nhớ

MAC xác thực thông điệp theo một khóa bí mật; HMAC là một cách xây dựng MAC dựa trên hash. Nó không mã hóa nội dung, không tự chứng minh người tạo cá nhân và không tự giải quyết replay.

Yêu cầu đầy đủ cần xác định profile, dữ liệu được bao phủ, encoding byte, key scope, cách so tag, ranh giới sử dụng và vòng đời khóa. Freshness, idempotency và authorization phải được gắn vào luồng nghiệp vụ cụ thể.

Bằng chứng chấp nhận cần bao phủ primitive lẫn toàn bộ đường dữ liệu: message hợp lệ, nội dung bị sửa, sai ngữ cảnh, replay, concurrency, proxy, rotation và lỗi phụ thuộc. Một lời gọi HmacSHA256 đúng chỉ có giá trị khi những ranh giới đó cũng đúng.
