# Bảo vệ thông tin nhạy cảm và tránh để lộ dữ liệu qua tên khóa

## 1. Vì sao tên khóa cũng có thể làm lộ dữ liệu?

Khi nói đến bảo mật cơ sở dữ liệu, nhiều người nghĩ ngay đến việc mã hóa **giá trị** lưu trong bản ghi. Nhưng ở các hệ NoSQL, **khóa dùng để định danh và định tuyến dữ liệu** cũng thường xuất hiện ở nhiều nơi: lệnh truy vấn, nhật ký ứng dụng, công cụ quản trị, chỉ mục, bản sao lưu, thông tin giám sát và các thông báo lỗi.

Hãy xét một hệ thống sử dụng Redis làm bộ nhớ đệm cho hồ sơ người dùng:

~~~text
# Không nên đặt tên khóa như thế này
profile:email:lan.nguyen@example.invalid
customer:phone:+84901234567
session:eyJhbGciOiJIUzI1NiJ9.example.signature
order:citizen-id:012345678901
~~~

Các chuỗi trên đã tiết lộ địa chỉ email, số điện thoại, dữ liệu định danh hoặc một phần thông tin xác thực **ngay ở tên khóa**, kể cả khi giá trị phía sau được mã hóa.

Một quản trị viên có quyền liệt kê keyspace, một bản ghi log truy vấn, hoặc hệ thống quan sát hiệu năng vô tình ghi cả tên khóa đều có thể nhìn thấy thông tin đó. Với khóa chứa session token hoặc mã truy cập, vấn đề còn nghiêm trọng hơn: người thấy khóa có thể nhìn thấy **bí mật mang quyền truy cập**, không chỉ thông tin cá nhân.

Cách thiết kế tốt hơn thường là:

~~~text
profile:v2:user:u_f4b2c7a1
customer:v2:user:u_7ea93d10
session:v2:2gxmI...<opaque digest>
order:v2:o_91c3a45f
~~~

Các ví dụ chỉ minh họa cấu trúc; trong triển khai thật, ID ngẫu nhiên và digest nên đủ dài, khó đoán và sinh bằng cơ chế an toàn. Phần quan trọng là **tên khóa mô tả loại dữ liệu và một mã đại diện không bộc lộ trực tiếp thông tin nhạy cảm**.

> Nguyên tắc cốt lõi: **Hãy xem tên khóa, khóa phân vùng, khóa sắp xếp và định danh bản ghi là dữ liệu có thể bị quan sát**, rồi thiết kế để chúng không tự mang bí mật hay thông tin cá nhân không cần thiết.

## 2. “Khóa” có những nghĩa nào trong NoSQL?

Các hệ NoSQL có nhiều mô hình, nên “khóa” không phải lúc nào cũng là cùng một đối tượng.

| Khái niệm | Ví dụ | Vai trò | Nguy cơ nếu chứa dữ liệu nhạy cảm |
|---|---|---|---|
| Key trong key–value store | Redis key `cache:user:42` | Tìm giá trị theo tên khóa | Có thể lộ khi liệt kê khóa, ghi command log, trace |
| Document ID | MongoDB `_id` | Xác định một tài liệu | Có thể xuất hiện ở API, log, URL, bản export |
| Partition key | Cassandra `user_id`; DynamoDB `PK` | Xác định phân vùng hoặc nhóm dữ liệu | Có thể xuất hiện trong truy vấn, bảng/index, log, backup |
| Sort/clustering key | DynamoDB `SK`; Cassandra clustering column | Sắp thứ tự và tìm bản ghi trong partition | Có thể mã hóa thời điểm, quan hệ hoặc thông tin nghiệp vụ nhạy cảm |
| Secondary index key | Thuộc tính làm khóa GSI/LSI hoặc chỉ mục phụ | Tìm theo lối truy cập khác | Thông tin nhạy cảm vẫn tồn tại trong index, bản sao và hoạt động truy vấn |
| Field name/path | `customer.email`, `profile.phone` | Mô tả cấu trúc dữ liệu | Bản thân tên trường thường ít nhạy cảm, nhưng giá trị động nhét vào tên trường có thể làm lộ dữ liệu |

**Phân biệt quan trọng:** “khóa dữ liệu” trong bài học này là **key/identifier dùng để lưu và truy vấn dữ liệu**. Nó khác với **khóa mật mã (cryptographic key)** dùng cho mã hóa hoặc HMAC. Khóa mật mã phải được giữ bí mật và quản lý riêng, tuyệt đối không đưa vào tên database key.

Một hệ có thể gọi khóa bằng tên khác; điều cần kiểm tra là **giá trị nào được dùng để xác định, phân phối, truy vấn và theo dõi bản ghi**.

## 3. Các loại thông tin không nên đưa trực tiếp vào tên khóa

### 3.1. Thông tin nhận dạng cá nhân

Các ví dụ thường gặp:

- Email, số điện thoại, địa chỉ thường trú, ngày sinh.
- Số giấy tờ định danh, mã số thuế cá nhân, số tài khoản ngân hàng.
- Họ tên đầy đủ gắn với đặc tính hoặc lịch sử nhạy cảm.
- Thông tin y tế, dữ liệu sức khỏe, lịch sử tư vấn.
- Địa chỉ IP hoặc định danh thiết bị khi chúng được coi là thông tin có thể liên kết tới một cá nhân trong ngữ cảnh ứng dụng.

Ví dụ không phù hợp:

~~~text
app:profile:email:lan.nguyen@example.invalid
app:orders:phone:+84901234567
app:health:patient:nguyen-van-a:diagnosis
~~~

Ngay cả khi giá trị trong những khóa đó rỗng, cấu trúc khóa vẫn có thể tiết lộ một sự thật về người dùng hoặc loại dữ liệu.

### 3.2. Bí mật xác thực và quyền truy cập

Cần tránh tuyệt đối việc đặt vào tên khóa:

- Mật khẩu hoặc mã khôi phục mật khẩu.
- Session ID dạng bearer token có thể dùng trực tiếp để đăng nhập.
- Access token, refresh token, API key.
- Mã OTP, mã xác nhận một lần.
- Private key, secret key hoặc khóa mã hóa.

Ví dụ:

~~~text
# Nguy hiểm: người đọc được key có thể thấy bí mật xác thực
auth:session:<raw-access-token>
reset-password:<reset-token>
otp:+84901234567:382914
api-key:<raw-api-key>:usage
~~~

Một số chuỗi ở trên còn có thể bị lộ qua công cụ phân tích vận hành, vì hệ thống thường coi key là metadata để chẩn đoán. Không nên xem phần metadata này như một kho chứa bí mật.

### 3.3. Thông tin nghiệp vụ không nên tiết lộ

Không chỉ dữ liệu cá nhân mới cần bảo vệ. Tên khóa như:

~~~text
salary:employee-name:amount
customer:company-x:contract-price
fraud:account-123:high-risk
treatment:patient-456:oncology
~~~

có thể tiết lộ mức lương, quan hệ khách hàng, trạng thái rủi ro hoặc một đặc tính nhạy cảm, ngay cả khi không cho biết nội dung đầy đủ của bản ghi.

**Tên namespace cũng tiết lộ ngữ nghĩa.** Một tiền tố như `fraud:high-risk:` có thể làm lộ việc một đối tượng bị đánh dấu rủi ro nếu phần ID có thể đối chiếu với người thật. Khi độ nhạy cảm cao, cần đánh giá cả cách đặt namespace lẫn ai có thể nhìn thấy nó.

## 4. Tên khóa có thể bị lộ bằng những đường nào?

### 4.1. Công cụ quản trị và lệnh liệt kê

Với Redis, các công cụ được cấp quyền có thể liệt kê keyspace hoặc quan sát các lệnh đang chạy. Chẳng hạn, việc sử dụng `SCAN` để duyệt khóa có thể đưa tên khóa vào kết quả quản trị. Lệnh giám sát như `MONITOR` có thể ghi nhận lệnh và đối số, tùy cách triển khai, quyền truy cập và cấu hình.

Một tài khoản vận hành được phép kiểm tra cache thường cần biết **số lượng, dung lượng hoặc nhóm khóa**, nhưng không nhất thiết cần đọc email hoặc token được nhúng trong tên khóa.

### 4.2. Log ứng dụng và thông báo lỗi

Một đoạn log tưởng như vô hại:

~~~java
logger.warn("Cache miss for key {}", redisKey);
~~~

có thể đẩy toàn bộ tên khóa vào nền tảng tập trung log. Nếu tên khóa chứa email hoặc session token, dữ liệu nhạy cảm đã bị sao chép sang một hệ thống khác với quyền truy cập, chính sách lưu giữ và cơ chế sao lưu riêng.

Điều tương tự xảy ra khi exception message, stack trace hoặc báo cáo lỗi chứa command và đối số truy vấn.

### 4.3. Tracing, APM và metrics

Các nền tảng quan sát có thể tự động thu thập tên truy vấn, statement, span attribute, tag hoặc tên tài nguyên.

Ví dụ không nên làm:

~~~text
metric: cache_lookup_total{key="profile:email:lan.nguyen@example.invalid"}
trace:  db.redis.key = "session:<raw-token>"
log:    "GET customer:phone:+84901234567"
~~~

Ngoài nguy cơ lộ dữ liệu, metric có nhãn `key` thay đổi theo từng người dùng còn gây **cardinality cao**: số lượng chuỗi thời gian tăng mạnh và làm hệ quan sát tiêu tốn bộ nhớ, dung lượng và chi phí.

Nên ghi thông tin tổng hợp:

~~~text
cache_lookup_total{namespace="profile",result="miss"}
cache_lookup_total{namespace="session",result="hit"}
db_operation_duration{operation="GET",namespace="profile"}
~~~

### 4.4. Sao lưu, bản sao và môi trường thử nghiệm

Tên khóa hoặc giá trị khóa định danh có thể nằm trong:

- Snapshot, backup, bản phục hồi của Redis hoặc NoSQL cluster.
- Bản sao dữ liệu sang môi trường thử nghiệm.
- File xuất dữ liệu phục vụ phân tích.
- Replication stream, change stream hoặc công cụ đồng bộ.
- Bản chụp sự cố phục vụ điều tra.

Dù database gốc có kiểm soát quyền truy cập chặt, bản sao dữ liệu và log có thể được lưu ở nơi khác lâu hơn dự kiến. Nếu cần sao chép dữ liệu thật sang môi trường thấp hơn, phải xem xét **ẩn danh hóa, giả danh hóa và loại bỏ dữ liệu nhạy cảm** ở cả khóa lẫn giá trị.

### 4.5. API, đường dẫn và thông điệp giữa các dịch vụ

Có ứng dụng dùng database key trực tiếp làm URL hoặc cache key:

~~~text
GET /profiles/email:lan.nguyen@example.invalid
GET /cache/session:<raw-token>
~~~

URL có thể đi vào access log, lịch sử trình duyệt, hệ phân tích, proxy hoặc hệ giám sát. Thay khóa database bằng một mã công khai được phép lộ, rồi giải quyết việc ánh xạ ở phía server thường an toàn hơn.

Không sử dụng key chứa thông tin nhạy cảm như một định danh gửi tới hệ thống không có nhu cầu xử lý thông tin đó.

## 5. Thiết kế khóa với ID đại diện không bộc lộ thông tin

### 5.1. Dùng định danh nội bộ thay cho giá trị nghiệp vụ

Giả sử người dùng đăng ký bằng email `lan.nguyen@example.invalid`.

Cách lưu trực tiếp:

~~~text
# Không nên
user:email:lan.nguyen@example.invalid:profile
~~~

Cách lưu bằng định danh:

~~~text
# Mẫu thiết kế tốt hơn
user:v1:u_8e47af59d61b4f59b890a4b6207d9832:profile
~~~

Tài khoản có thể có một ID nội bộ độc lập với email, tên hoặc số điện thoại. Khi email thay đổi, ID người dùng vẫn giữ nguyên. Việc cập nhật hồ sơ cũng không đòi hỏi di chuyển toàn bộ tập khóa được xây dựng từ email cũ.

Lợi ích của định danh nội bộ:

1. Không trực tiếp tiết lộ email/số điện thoại.
2. Không phụ thuộc vào dữ liệu có thể thay đổi.
3. Tránh lỗi xử lý ký tự đặc biệt trong tên khóa.
4. Dễ phân nhóm namespace và thay đổi cách lưu.
5. Giảm khả năng liên kết người dùng với định danh bên ngoài khi key bị lộ.

### 5.2. Sinh ID như thế nào?

Tùy nhu cầu:

- **UUID phiên bản 4:** ID dựa trên giá trị ngẫu nhiên, phù hợp khi cần mã khó đoán và không chứa trực tiếp nội dung cá nhân.
- **Token ngẫu nhiên bằng CSPRNG:** phù hợp khi cần bí mật có độ hỗn loạn cao, ví dụ token phiên, token khôi phục.
- **ULID hoặc UUID phiên bản 7:** hữu ích khi muốn ID có tính sắp xếp gần theo thời gian, nhưng phần biểu diễn thời gian có thể làm lộ thời điểm sinh. Cần cân nhắc nếu thông tin thời điểm cũng nhạy cảm.
- **ID tăng dần:** dễ triển khai và gọn nhưng có thể bị đoán hoặc suy ra thứ tự, số lượng đối tượng. Không phù hợp làm cơ chế bảo vệ tài nguyên chỉ dựa trên tính khó đoán.

Ví dụ Java sử dụng UUID v4:

~~~java
import java.util.UUID;

public class UserIdGenerator {
    public static String newUserId() {
        return "u_" + UUID.randomUUID().toString().replace("-", "");
    }
}
~~~

ID sinh ngẫu nhiên **không thay thế kiểm tra quyền truy cập**. Biết hoặc đoán được ID không được đồng nghĩa với quyền đọc bản ghi. Server vẫn phải xác thực người dùng và kiểm tra quyền với đúng tenant, tổ chức và tài nguyên.

### 5.3. Quy ước cấu trúc key

Một cấu trúc key dễ quản lý có thể gồm:

~~~text
<ứng-dụng>:<phiên-bản>:<namespace>:<định-danh-không-nhạy-cảm>
~~~

Ví dụ:

~~~text
shop:v2:profile:u_8e47af59d61b4f59b890a4b6207d9832
shop:v2:cart:u_8e47af59d61b4f59b890a4b6207d9832
shop:v2:order:o_e77db3a24c7844f99a70d6c7393e63a6
shop:v2:tenant:t_7b3d99a2:user:u_8e47af59d61b4f59b890a4b6207d9832
~~~

Ý nghĩa các thành phần:

| Thành phần | Mục đích | Lưu ý |
|---|---|---|
| `shop` | Nhận biết ứng dụng | Tránh mang thông tin khách hàng |
| `v2` | Phiên bản cách đặt khóa | Hỗ trợ thay đổi cấu trúc khi triển khai |
| `profile`/`cart`/`order` | Phân loại dữ liệu | Chỉ dùng nếu bản thân namespace không tiết lộ đặc tính quá nhạy cảm |
| `u_...`/`o_...` | Định danh nội bộ | Không chứa email, số điện thoại, token |
| `tenant:t_...` | Phạm vi tenant | Dùng ID tenant nội bộ; vẫn cần kiểm tra phân quyền |

Một số hệ dùng ký tự đặc biệt như dấu hai chấm, dấu thăng hoặc dấu ngoặc để tổ chức khóa. Nên giới hạn bộ ký tự của ID (ví dụ UUID hoặc Base64URL an toàn), đồng thời xử lý các thành phần do người dùng cung cấp để tránh nhập nhằng giữa tiền tố và dữ liệu.

**Không tự động nối chuỗi người dùng nhập vào key** khi chuỗi đó có thể chứa dấu phân tách, wildcard hoặc dữ liệu riêng tư. Tốt hơn là dùng mã nội bộ đã được chuẩn hóa và xác thực.

## 6. Nếu bắt buộc cần tra cứu theo email hoặc số điện thoại thì sao?

Không ít nghiệp vụ buộc phải tìm người dùng theo email hoặc điện thoại, ví dụ đăng nhập hoặc tìm tài khoản để gửi thông báo. Câu hỏi đặt ra là làm sao tra cứu nhanh mà không đưa giá trị đó trực tiếp vào tên khóa.

Có hai cách tiếp cận chính.

### 6.1. Cách ưu tiên: tách bảng/chỉ mục ánh xạ khỏi các khóa dữ liệu chính

Lưu hồ sơ bằng `user_id` ngẫu nhiên:

~~~text
profile:u_8e47af59...
~~~

Dữ liệu nguồn hoặc chỉ mục tra cứu email có thể được quản lý trong một hệ lưu trữ được phân quyền chặt chẽ. Sau khi tìm được `user_id`, ứng dụng truy cập tài liệu bằng ID nội bộ.

Thiết kế này làm giảm việc sao chép PII vào hàng loạt cache key. Tuy nhiên, **chỉ mục email ở nguồn vẫn chứa dữ liệu cá nhân** và cần bảo vệ bằng kiểm soát truy cập, mã hóa phù hợp, retention, audit và các chính sách dữ liệu.

### 6.2. Khi cần key tra cứu xác định: dùng HMAC có khóa bí mật

Nếu ứng dụng thật sự cần cùng một email luôn dẫn đến cùng một key, có thể tạo **mã đại diện xác định** từ email đã chuẩn hóa bằng HMAC:

~~~text
email thật       -> chuẩn hóa theo quy tắc nghiệp vụ
                 -> HMAC-SHA-256 với secret của ứng dụng
                 -> mã Base64URL
                 -> lookup:email:v1:<digest>
~~~

HMAC-SHA-256 nhận một **khóa bí mật** và dữ liệu đầu vào, trả ra chuỗi có độ dài cố định. Nếu người ngoài chỉ biết tên Redis key nhưng không biết secret, họ khó kiểm tra một danh sách email đoán trước bằng cách tính lại digest tương ứng.

Điều này khác với băm SHA-256 thông thường:

~~~text
# Không đủ nếu đầu vào là email/số điện thoại dễ đoán
lookup:email:SHA256("lan.nguyen@example.invalid")
~~~

Email và số điện thoại có không gian dự đoán được, nên kẻ tấn công có thể thử danh sách ứng viên rồi so sánh hash. **Base64, URL encoding hay SHA-256 không có khóa bí mật không phải giải pháp giấu PII đáng tin cậy** trong tình huống này.

HMAC vẫn là **pseudonymization (giả danh hóa)**, không phải ẩn danh hóa tuyệt đối. Ai giữ secret hoặc có khả năng gọi chức năng tạo HMAC cho các đầu vào tùy ý có thể kiểm tra các ứng viên. Vì vậy phải bảo vệ cả secret và quyền gọi dịch vụ tra cứu.

### 6.3. Ví dụ Java tạo tên khóa bằng HMAC

Ví dụ sau dùng API có sẵn trong JDK, với secret được **truyền vào từ hệ quản lý bí mật**. Nó tạo namespace khác nhau cho chỉ mục email và session.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeNoSqlKeys {
    private static final SecureRandom RANDOM = new SecureRandom();

    private SafeNoSqlKeys() {}

    // Sinh bearer token ngẫu nhiên 256 bit để gửi cho client qua kênh an toàn.
    public static String newSessionToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    // canonicalEmail phải được chuẩn hóa trước theo quy tắc của sản phẩm.
    public static String emailLookupKey(
            String canonicalEmail,
            byte[] hmacSecret) throws GeneralSecurityException {
        return "lookup:email:v1:"
                + hmacDigest("email-lookup:v1", canonicalEmail, hmacSecret);
    }

    // Không bao giờ dùng raw bearer token làm tên khóa.
    public static String sessionStorageKey(
            String bearerToken,
            byte[] hmacSecret) throws GeneralSecurityException {
        return "session:v1:"
                + hmacDigest("session-storage:v1", bearerToken, hmacSecret);
    }

    private static String hmacDigest(
            String purpose,
            String input,
            byte[] secret) throws GeneralSecurityException {

        if (input == null || input.isEmpty()
                || secret == null || secret.length < 32) {
            throw new IllegalArgumentException("Invalid HMAC input or key");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        // Tách biệt mục đích sử dụng để tránh trùng mã giữa các namespace.
        mac.update(purpose.getBytes(StandardCharsets.UTF_8));
        mac.update((byte) 0);
        byte[] digest = mac.doFinal(input.getBytes(StandardCharsets.UTF_8));

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
    }
}
~~~

Để dùng đúng cách:

1. Nạp `hmacSecret` từ secret manager hoặc cơ chế bảo vệ bí mật tương đương, không hard-code trong mã nguồn hoặc commit vào repository.
2. Dùng secret được tạo ngẫu nhiên có entropy đủ lớn; điều kiện `length >= 32` trong ví dụ chỉ kiểm tra độ dài, **không tự bảo đảm entropy của secret**.
3. Quy định quy tắc canonicalization ổn định. Với email, đừng tự ý đổi phần trước dấu `@` thành chữ thường nếu ứng dụng chưa xác định chính sách; chuẩn hóa sai có thể gộp nhầm hai địa chỉ hoặc làm mất khả năng tra cứu.
4. Với số điện thoại, chuẩn hóa theo định dạng được ứng dụng chấp nhận (ví dụ E.164 nếu phù hợp); không dùng cách loại bỏ tùy tiện ký tự rồi suy đoán mã quốc gia.
5. Dùng namespace/purpose riêng cho email lookup, session, recovery token, external identifier và các hệ thống khác nhau.
6. Có cơ chế luân chuyển secret, gắn phiên bản hoặc key ID với dữ liệu và giai đoạn chuyển đổi.
7. Không log email đầu vào, digest gắn với người dùng hoặc secret khi không có nhu cầu và kiểm soát tương ứng.

**Vì sao cần tách purpose?** Nếu cùng một chuỗi xuất hiện ở hai miền dữ liệu khác nhau, dùng một công thức băm giống nhau có thể tạo cùng digest, cho phép liên kết hai danh sách. Thêm nhãn miền riêng trước khi tính HMAC làm giảm rủi ro liên kết chéo này.

### 6.4. Lưu ý khi thay đổi HMAC secret

Dữ liệu đã lưu dưới key từ secret cũ sẽ không được tìm thấy bằng secret mới. Có thể áp dụng quy trình luân chuyển:

- Gắn phiên bản `v1`/`v2` hoặc key ID không bí mật vào namespace.
- Trong giai đoạn chuyển đổi, ghi key phiên bản mới; đọc có thể thử phiên bản còn hiệu lực theo chính sách.
- Di chuyển hoặc làm mới các bản ghi cần giữ; với cache có TTL, có thể để bản ghi cũ tự hết hạn nếu được phép.
- Theo dõi tiến độ chuyển đổi và thu hồi secret cũ sau khi không còn phụ thuộc.
- Có phương án xử lý trường hợp secret bị lộ, bao gồm vô hiệu hóa phiên/token nếu cần.

Không nên tự động xoay secret rồi giả định mọi ánh xạ dữ liệu trước đó vẫn hoạt động.

## 7. Session token, OTP và token khôi phục: trường hợp đặc biệt

### 7.1. Session token là bí mật xác thực

Một session token thường hoạt động như bằng chứng để truy cập tài khoản. Nếu người khác sở hữu token còn hiệu lực, họ có thể giả mạo phiên tùy cơ chế xác thực.

Không nên:

~~~text
# Tên Redis key chính là token
session:<raw-session-token> -> {"userId":"u_42"}
~~~

Có thể dùng:

~~~text
# Token phía client được tạo ngẫu nhiên đủ mạnh
token = <random 256-bit bearer token>

# Khóa lưu trữ được suy ra bằng HMAC với secret server
session:v1:<HMAC(secret, token)> -> {"userId":"u_42"}
~~~

Hệ thống gửi token cho client qua kênh an toàn, ví dụ cookie với các thuộc tính bảo vệ phù hợp như `Secure`, `HttpOnly` và `SameSite` theo yêu cầu ứng dụng. Khi nhận token, server tính lại HMAC để tìm session. Raw token không cần nằm trong key.

Một phương án khác với bearer token **ngẫu nhiên có entropy cao** là lưu digest bằng hàm băm mật mã phù hợp; HMAC vẫn giúp có secret phía server và tách miền sử dụng. Không áp dụng lý luận “hash không khóa cũng đủ” cho email hoặc mã OTP ngắn vốn dễ đoán.

### 7.2. OTP ngắn không nên làm thành phần của key

Mã OTP 6 chữ số chỉ có một triệu khả năng trước khi xét các giới hạn khác. Đặt OTP vào tên khóa sẽ làm lộ mã; băm không khóa một mình cũng không phải biện pháp bảo vệ đủ mạnh.

Mẫu thiết kế tốt hơn:

~~~text
otp:v1:<opaque-challenge-id> ->
    {
      "userId": "<opaque-user-id>",
      "verificationDigest": "<server-keyed digest of OTP>",
      "expiresAt": "...",
      "attemptsRemaining": 3
    }
~~~

Cần kết hợp thời hạn sống ngắn, giới hạn số lần nhập, chống thử đoán trực tuyến, vô hiệu hóa sau khi dùng và kiểm soát vòng đời phiên xác minh. Chỉ đổi tên khóa không tự bảo vệ được OTP.

### 7.3. Access token hoặc JWT có thể tiết lộ nhiều thông tin

Nếu đưa nguyên JWT vào key, chuỗi đó có thể xuất hiện trong log, trace và bản sao lưu. Payload JWT cũng có thể đọc được nếu token chỉ được ký mà không được mã hóa. Vì thế, key nên chứa ID ngẫu nhiên hoặc digest không bộc lộ token, và các hệ quan sát cần tránh ghi cả token.

## 8. Mã hóa dữ liệu không tự xử lý việc lộ tên khóa

Cần phân biệt các lớp bảo vệ:

| Biện pháp | Bảo vệ được gì? | Không tự bảo vệ được gì? |
|---|---|---|
| TLS khi truyền dữ liệu | Giảm nguy cơ nghe lén trên đường truyền theo cấu hình đúng | Log, trace, keyspace được người có quyền xem |
| Mã hóa lưu trữ/đĩa | Bảo vệ dữ liệu lưu trữ trong phạm vi và mô hình đe dọa của cơ chế mã hóa | Tên khóa hiện rõ khi DB đã giải mã và phục vụ truy vấn |
| Mã hóa trường nhạy cảm | Giảm lộ nội dung trường khi người đọc thiếu khóa giải mã | Tên key nếu vẫn chứa email/token |
| ID ngẫu nhiên hoặc HMAC key | Giảm PII lộ từ định danh và key name | Giá trị nhạy cảm, kiểm soát quyền truy cập, metadata phụ |
| ACL, phân quyền và audit | Giới hạn ai có thể xem/đọc/ghi dữ liệu | Lỗi đặt tên khóa trong log được chia sẻ rộng rãi |
| Ẩn/mặt nạ log | Giảm sao chép dữ liệu nhạy cảm vào observability | Bản ghi/khóa gốc nếu bản thân chúng chứa PII |

Ví dụ, mã hóa giá trị hồ sơ:

~~~text
profile:email:lan.nguyen@example.invalid -> <encrypted profile>
~~~

vẫn làm lộ email ở bên trái. Ngược lại:

~~~text
profile:v2:u_8e47af59... -> <encrypted profile>
~~~

giảm lộ qua tên khóa, nhưng giá trị sau giải mã vẫn phải được kiểm soát quyền truy cập.

**Phòng thủ nhiều lớp:** dùng định danh an toàn, hạn chế quyền, bảo vệ đường truyền và lưu trữ, kiểm soát log, và bảo vệ giá trị nhạy cảm tương ứng với mô hình đe dọa.

## 9. Những lưu ý theo hệ quản trị NoSQL

### 9.1. Redis và các hệ key–value

Redis thường có key name trực tiếp trong lệnh `GET`, `SET`, `DEL`, `EXPIRE` hoặc `SCAN`.

~~~text
# Không nên
GET user:email:lan.nguyen@example.invalid
GET session:<raw-token>

# Nên theo thiết kế phù hợp
GET user:v2:u_8e47af59d61b4f59b890a4b6207d9832
GET session:v1:<opaque-digest>
~~~

Một số điểm cần chú ý:

- Duyệt keyspace bằng công cụ quản trị có thể làm lộ tên khóa.
- Log lệnh, công cụ giám sát hoặc thông báo keyspace có thể làm lộ tên khóa tùy tính năng bật và quyền người nhận.
- File RDB/AOF hoặc bản backup có thể lưu những key cần được bảo vệ tương ứng.
- Redis ACL và chính sách mạng phải giới hạn những lệnh và namespace mà tài khoản được dùng.
- TTL cho cache và session cần phù hợp với thời gian tồn tại dữ liệu; hết TTL không đồng nghĩa mọi bản sao lưu/log đã biến mất.
- Không dùng ký tự người dùng nhập trực tiếp để xây các tên khóa hoặc pattern truy vấn có khả năng gây va chạm namespace.

Giới hạn quyền đọc keyspace và quyền sử dụng lệnh quản trị là quan trọng ngay cả khi tên khóa đã được giả danh hóa.

### 9.2. MongoDB và document ID

Trong MongoDB, `_id` là khóa định danh tài liệu. Nếu dùng email làm `_id`:

~~~json
{
  "_id": "lan.nguyen@example.invalid",
  "displayName": "Lan"
}
~~~

thì email đã được đưa vào trường định danh. Khi API trả `_id`, khi một truy vấn bị log hoặc khi dữ liệu được export, thông tin đó có thể đi theo nhiều nơi.

Có thể dùng:

~~~json
{
  "_id": "u_8e47af59d61b4f59b890a4b6207d9832",
  "email": "lan.nguyen@example.invalid",
  "displayName": "Lan"
}
~~~

Trường email vẫn là PII và cần bảo vệ. Lợi ích là định danh tài liệu không tự lộ email, đồng thời có thể giữ ổn định khi email thay đổi. Hệ có thể dùng ID tự sinh phù hợp; không nhất thiết bắt buộc ID dạng UUID nếu sản phẩm cung cấp cơ chế tốt.

Nếu truy vấn theo email vẫn cần chỉ mục, hãy xem xét quyền đọc trường, cấu hình mã hóa, cách index được lưu và rủi ro log truy vấn. Không nên kết luận rằng đổi `_id` thành UUID là đã bảo vệ toàn bộ email.

### 9.3. DynamoDB: partition key, sort key và GSI

Trong DynamoDB, giá trị của partition key và sort key là thuộc tính thực tế của item. Chúng có thể đi vào biểu thức truy vấn, stream, export và các secondary index.

Không nên mô hình hóa:

~~~text
PK = USER#lan.nguyen@example.invalid
SK = PROFILE
~~~

Có thể dùng:

~~~text
PK = USER#u_8e47af59d61b4f59b890a4b6207d9832
SK = PROFILE
~~~

Khi cần tra cứu theo email, có thể duy trì một GSI hoặc bảng tra cứu chuyên biệt dựa trên mã đại diện HMAC nếu đáp ứng yêu cầu truy vấn. Cần bảo vệ thông tin nguồn, xử lý việc thay đổi email và giới hạn ai được gọi tra cứu.

Không chỉ bảng chính mà **secondary index keys** cũng phải được rà soát. Đưa PII ra khỏi primary key nhưng tiếp tục dùng email nguyên bản làm GSI partition key vẫn để lại một bề mặt lộ thông tin.

### 9.4. Cassandra: partition key và clustering key

Với Apache Cassandra, khóa phân vùng quyết định việc phân bố bản ghi. Ví dụ:

~~~sql
CREATE TABLE events_by_user_day (
    tenant_id text,
    user_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, user_id, event_day), occurred_at, event_id)
);
~~~

Ở đây `tenant_id` và `user_id` là định danh nội bộ phù hợp; `event_day` là thành phần phục vụ truy vấn theo ngày. Nếu thay `user_id` bằng email hoặc số giấy tờ, giá trị đó sẽ nằm trong dữ liệu khóa, đường truy vấn và các bề mặt giám sát.

Không nên băm toàn bộ partition key một cách tùy tiện chỉ vì muốn giấu thông tin: **partition key ảnh hưởng trực tiếp tới phân bố tải và kiểu truy vấn có thể thực hiện**. Cần thiết kế cả khả năng tra cứu, định tuyến, phân trang và phân bố dữ liệu.

### 9.5. Tên trường động và khóa lồng nhau

Trong document database hoặc Redis hash, có hệ thống dùng dữ liệu từ người dùng làm tên thuộc tính:

~~~json
{
  "scoresByEmail": {
    "lan.nguyen@example.invalid": 85
  }
}
~~~

Dù email không nằm ở primary key, nó đã đi vào **tên field** và có thể xuất hiện khi log schema, thống kê tên thuộc tính hoặc export.

Thiết kế khác:

~~~json
{
  "scores": [
    {
      "userId": "u_8e47af59d61b4f59b890a4b6207d9832",
      "score": 85
    }
  ]
}
~~~

Việc lựa chọn cấu trúc mảng, map hay collection riêng còn tùy truy vấn và kích thước dữ liệu, nhưng nguyên tắc không đưa PII vào field name vẫn có ích.

## 10. Giữ tên khóa an toàn nhưng vẫn quản trị được

Một tên khóa hoàn toàn không có cấu trúc sẽ khó debug và quản lý TTL; một tên khóa mô tả quá chi tiết lại có thể làm lộ bí mật. Có thể cân bằng bằng cách dùng **namespace ổn định + ID mờ**.

Ví dụ:

~~~text
app:v3:session:<opaque-token-lookup>
app:v3:profile:<opaque-user-id>
app:v3:cart:<opaque-user-id>
app:v3:order:<opaque-order-id>
app:v3:rate-limit:<opaque-principal-id>
~~~

Nhà vận hành vẫn nhận biết được key thuộc nhóm session, profile hay order, trong khi không nhìn thấy email/số điện thoại của người dùng.

Một số kỹ thuật hỗ trợ vận hành:

- Gắn loại dữ liệu bằng namespace thay vì gắn thông tin cá nhân.
- Ghi metric theo namespace và thao tác, không theo từng key.
- Khi cần truy vết một đối tượng, dùng correlation ID ngẫu nhiên được cấp cho phiên xử lý và kiểm soát quyền tra cứu tương ứng.
- Giữ ánh xạ từ ID nội bộ sang dữ liệu thật ở dịch vụ nguồn có phân quyền.
- Có chính sách retention cho log và backup, bao gồm thời hạn và quyền truy xuất.
- Giới hạn quyền liệt kê toàn bộ keyspace, export hoặc truy cập nội dung thô.
- Khi cần debug có liên quan dữ liệu cá nhân, thực hiện thông qua công cụ có phân quyền và audit thay vì bật log toàn bộ tên khóa.

Cần nhớ rằng **ID mờ vẫn có thể là dữ liệu định danh gián tiếp** nếu nhiều hệ sử dụng cùng ID hoặc một người có thể tra bảng ánh xạ. Do đó không nên tự động công khai mọi ID chỉ vì chúng không chứa chữ cái của email.

## 11. Nhật ký và hệ thống quan sát: ghi gì để vẫn debug được?

### 11.1. Thay giá trị nhạy cảm bằng thuộc tính tổng hợp

Ví dụ với thao tác đọc cache:

~~~java
// Không nên, vì tên khóa có thể chứa thông tin nhạy cảm
logger.debug("cache GET key={}", key);

// Hợp lý hơn: ghi loại thao tác và kết quả, không ghi key
logger.debug("cache read namespace={} hit={}", "profile", cacheHit);
~~~

Có thể thêm `durationMs`, `errorCode`, `retryCount`, `nodeRole` hoặc `tenantTier` nếu các thuộc tính đó đã được đánh giá về quyền riêng tư và số lượng giá trị.

Không ghi full token vào exception, trace, event hoặc tag. Khi thư viện tự động bắt truy vấn, cần kiểm tra khả năng lọc/redact đối số; việc ứng dụng tự không gọi logger chưa bảo đảm driver hoặc APM không ghi.

### 11.2. Hash trong log không mặc định làm dữ liệu vô danh

Có người đề xuất:

~~~text
log_key = SHA256(email)
~~~

Nếu đầu vào là email, một hệ khác vẫn có thể tính hash của danh sách email và dò tìm. Ngoài ra, một hash ổn định cho cùng người dùng có thể cho phép **liên kết hành vi qua nhiều dịch vụ và thời điểm**.

Nếu thực sự cần correlation theo một đối tượng, cân nhắc dùng mã ngẫu nhiên theo yêu cầu/phiên xử lý hoặc HMAC với purpose phù hợp, TTL và kiểm soát quyền, rồi giới hạn phạm vi nơi được lưu. Đừng ghi digest của mọi người dùng vào metric labels.

### 11.3. Khi nào cần redaction?

Những vị trí đáng rà soát:

| Điểm phát sinh | Dữ liệu có thể lộ | Cách xử lý |
|---|---|---|
| Log phía API | URL path, query parameter, header, user ID | Không đặt PII/token vào URL; lọc/redact trường nhạy cảm |
| Log DB driver | Query/command với key hoặc giá trị khóa | Tắt/giới hạn logging chi tiết ở môi trường thật; lọc đối số |
| Trace/APM | Span attributes, câu truy vấn, cache key | Dùng thuộc tính tổng hợp; cấu hình bộ xử lý redaction |
| Metrics | Tag `key`, `email`, `userId` | Chỉ giữ nhãn cardinality thấp đã được duyệt |
| Exception/report | Lệnh thất bại, token, dữ liệu đầu vào | Chuyển thành mã lỗi và context an toàn |
| Backup/export | Key và value thô | Phân quyền, mã hóa, retention, kiểm soát môi trường nhận |

Phải kiểm tra **toàn bộ đường đi của telemetry**, vì log sau khi rời ứng dụng thường được sao chép, lập chỉ mục, giữ lâu và truy cập bởi nhiều nhóm.

## 12. Đa tenant: định danh mờ chưa đủ, phải giữ ranh giới quyền truy cập

Ứng dụng đa khách hàng có thể dùng:

~~~text
tenant:t_a8d2:user:u_41b9:profile
tenant:t_b7e1:user:u_41b9:profile
~~~

Tách namespace theo tenant có ích cho tổ chức dữ liệu, nhưng không chứng minh tính cách ly. Nếu service của tenant A chấp nhận key của tenant B từ tham số đầu vào, nó vẫn có thể đọc nhầm dữ liệu.

Cần kiểm tra:

1. Tenant ID lấy từ **ngữ cảnh xác thực tin cậy**, không tin giá trị tenant do client tự khai báo.
2. Mọi thao tác đọc, ghi, cập nhật và xóa đều được kiểm tra quyền truy cập tài nguyên tương ứng.
3. Chính sách DB/IAM/ACL giới hạn phạm vi dữ liệu nếu công nghệ hỗ trợ.
4. Không cung cấp API đọc trực tiếp theo một key tùy ý do người dùng nhập.
5. Những read model/index phụ cũng giữ cùng phạm vi tenant.
6. Kiểm thử trường hợp cùng ID người dùng nhưng khác tenant, không được truy cập chéo.

**Opaque ID không phải là cơ chế phân quyền.** Một ID không thể đoán không cho phép bỏ qua kiểm tra quyền; nếu ID bị lộ do log hoặc liên kết giữa các hệ, server vẫn phải từ chối truy cập trái phép.

## 13. Chọn cách bảo vệ phù hợp với từng loại khóa

| Trường hợp | Thiết kế được ưu tiên | Điều cần bảo đảm thêm |
|---|---|---|
| Khóa hồ sơ người dùng | ID người dùng ngẫu nhiên/ổn định | Kiểm tra quyền đọc hồ sơ |
| Khóa giỏ hàng | ID người dùng hoặc giỏ hàng mờ | Phân quyền, TTL nếu nghiệp vụ cho phép |
| Khóa tra cứu email | Ánh xạ riêng được kiểm soát; HMAC nếu cần key xác định | Secret manager, quy tắc chuẩn hóa, xử lý đổi email |
| Khóa phiên đăng nhập | Digest/HMAC của bearer token ngẫu nhiên | TTL, thu hồi, cookie an toàn, chống đánh cắp token |
| Khóa OTP | Challenge ID ngẫu nhiên | HMAC mã OTP, giới hạn thử, TTL ngắn |
| Khóa rate limit | Mã principal mờ hoặc HMAC của thuộc tính cần giới hạn | Tránh log IP/email, tránh mất khả năng giới hạn |
| Khóa dữ liệu thiết bị | Device ID nội bộ | Kiểm soát quyền truy vấn và ánh xạ sang chủ sở hữu |
| Khóa phân vùng sự kiện | Tenant/user ID nội bộ + bucket thời gian | Phân phối tải, tránh partition nóng |
| Khóa chỉ mục tìm kiếm | ID tài liệu mờ | Không dựa vào search index để quyết định quyền truy cập |
| Khóa cache query | Digest của biểu diễn truy vấn đã chuẩn hóa, có purpose phù hợp | Không chứa raw query có PII; kiểm soát tính nhất quán và invalidation |

Không có một giải pháp duy nhất áp dụng cho mọi loại khóa. **Định danh ngẫu nhiên** thích hợp khi ứng dụng có thể lưu ánh xạ; **HMAC xác định** hữu ích khi bắt buộc tính lại key từ đầu vào mà không có ánh xạ trước. Cả hai vẫn cần phân quyền và giám sát.

## 14. Bài toán thực tế: thiết kế lại cache hồ sơ khách hàng

### 14.1. Thiết kế ban đầu

Ứng dụng dùng số điện thoại làm định danh cache:

~~~text
cache:customer:+84901234567:profile
cache:customer:+84901234567:orders
cache:customer:+84901234567:cart
~~~

Khi người dùng đổi số điện thoại, ứng dụng phải di chuyển/xóa nhiều key. Ngoài ra, nhân viên vận hành có quyền xem danh sách cache key sẽ nhìn thấy số điện thoại.

### 14.2. Thiết kế cải tiến

Hệ tài khoản cấp `user_id` nội bộ không chứa số điện thoại:

~~~text
cache:v2:profile:u_8e47af59d61b4f59b890a4b6207d9832
cache:v2:orders:u_8e47af59d61b4f59b890a4b6207d9832
cache:v2:cart:u_8e47af59d61b4f59b890a4b6207d9832
~~~

Khi cần tìm tài khoản từ số điện thoại:

1. Ứng dụng xác thực quyền gọi chức năng tra cứu.
2. Số điện thoại được chuẩn hóa theo quy tắc nghiệp vụ.
3. Dịch vụ tài khoản tìm `user_id` từ nguồn dữ liệu được bảo vệ hoặc chỉ mục HMAC tương ứng.
4. Từ `user_id`, ứng dụng truy cập cache key với namespace cố định.
5. Log chỉ ghi loại thao tác, kết quả, thời gian và request ID an toàn.

Số điện thoại thay đổi không nhất thiết ảnh hưởng các key dữ liệu chính vì `user_id` không đổi.

### 14.3. Cần quản lý quá trình chuyển đổi

Nếu ứng dụng đang dùng tên khóa cũ, không nên đổi sang cấu trúc mới và để tất cả chức năng đọc cache gặp lỗi bất ngờ.

Một hướng triển khai có kiểm soát:

- Giới thiệu namespace phiên bản mới `v2`.
- Từ thời điểm chuyển đổi, ghi các key mới và dùng `user_id` nội bộ.
- Với dữ liệu cache có TTL, có thể bỏ dần cache cũ sau khi đường đọc mới vận hành ổn định, nếu nghiệp vụ cho phép.
- Với dữ liệu lưu bền, thực hiện migration có kiểm tra ánh xạ và đầy đủ quyền.
- Loại bỏ chỗ còn tạo khóa từ điện thoại/email trong ứng dụng, job, script và dashboard.
- Xem xét log/backup cũ đã lưu PII theo chính sách retention hiện hành và kế hoạch xử lý tương ứng.

Chú ý: **xóa key cũ không đồng nghĩa đã xóa dữ liệu từ log, backup hoặc bản sao**. Việc đánh giá dữ liệu tồn dư phải theo chính sách lưu trữ và nghĩa vụ của hệ thống.

## 15. Những sai lầm phổ biến

### “Key không phải là value nên không cần bảo vệ.”

Sai. Key có thể chứa PII hoặc bí mật, lại thường đi qua nhiều công cụ quản trị và giám sát. Trong nhiều môi trường, key dễ bị quan sát hơn payload được mã hóa.

### “Chỉ cần Base64 email là đủ.”

Sai. Base64 là mã hóa biểu diễn có thể giải mã trực tiếp, không phải mã hóa bảo mật.

~~~text
Base64("lan.nguyen@example.invalid") != bảo vệ email
~~~

URL encoding, hex hoặc thay dấu chấm bằng gạch dưới cũng không thay đổi bản chất này.

### “Băm SHA-256 số điện thoại là không thể dò lại.”

Sai khi đầu vào dễ đoán. Không cần khôi phục toán học từ digest; có thể tính trước hash của nhiều số điện thoại và dò khớp. Dùng HMAC với secret bảo vệ tốt hơn trong trường hợp cần chỉ mục xác định, nhưng vẫn phải kiểm soát quyền tra cứu.

### “UUID v4 bí mật nên không cần xác thực người dùng.”

Sai. UUID v4 chỉ là định danh khó đoán hơn mã tăng dần. Rò rỉ ID trong link, log hoặc dữ liệu chia sẻ vẫn có thể xảy ra. Mọi tài nguyên phải được phân quyền.

### “Đã bật mã hóa đĩa nên tên key trong log không còn vấn đề.”

Sai. Mã hóa lưu trữ không loại bỏ key name khỏi bộ nhớ ứng dụng, log, metrics và công cụ quản trị đang có quyền sử dụng database.

### “HMAC làm dữ liệu hoàn toàn vô danh.”

Sai. HMAC tạo một mã giả danh có thể tái lập nếu có secret. Nó vẫn cho phép liên kết các bản ghi cùng đối tượng trong cùng miền khóa và không thay thế chính sách bảo vệ dữ liệu cá nhân.

### “Có thể dùng nguyên JWT làm khóa vì token đã được ký.”

Sai. Token được ký có thể vẫn mang payload đọc được, và quan trọng hơn, JWT còn hiệu lực có thể là bearer credential. Việc đưa nó vào key tăng nguy cơ rò rỉ credential.

### “Một tiền tố tenant là đủ ngăn đọc chéo.”

Sai. Ranh giới tenant cần được thực thi trong xác thực, phân quyền, truy vấn và hạ tầng. Tiền tố chỉ là quy ước tổ chức dữ liệu.

### “Ẩn log ở ứng dụng là đủ.”

Chưa đủ. Driver, APM, proxy, công cụ quản trị, stream và backup có thể lưu thêm dữ liệu. Cần nhìn toàn bộ đường đi của metadata.

## 16. Checklist thiết kế một key mới

Trước khi đưa một quy tắc đặt khóa vào production, hãy trả lời:

1. **Key có chứa PII hoặc bí mật không?** Nếu có, thay bằng ID nội bộ hoặc mã đại diện phù hợp.
2. **Key có thể được liệt kê hoặc đi vào log/trace không?** Rà soát công cụ quản trị và telemetry.
3. **ID có ổn định khi email, điện thoại hoặc tên thay đổi không?** Nếu không, cân nhắc ID độc lập.
4. **Key có thể bị đoán hoặc bị lộ không?** Dù câu trả lời là gì, vẫn phải thực thi authorization.
5. **Có cần tra cứu ngược từ dữ liệu nhạy cảm không?** Dùng ánh xạ có phân quyền hoặc HMAC có secret, quản lý canonicalization và rotation.
6. **Đây có phải token truy cập hoặc OTP không?** Không lưu nguyên token trong tên khóa; áp dụng TTL và các kiểm soát xác thực riêng.
7. **Namespace có tiết lộ trạng thái nhạy cảm không?** Đánh giá tiền tố và mã liên kết.
8. **Key có đi vào index hoặc partition khác không?** Rà soát cả primary key, secondary index, field name động và các bản sao.
9. **Key được tạo từ đầu vào không tin cậy không?** Kiểm tra định dạng, ký tự phân tách, giới hạn độ dài và va chạm namespace.
10. **Khi dữ liệu bị xóa hoặc secret bị luân chuyển thì sao?** Chuẩn bị TTL, xóa, migration, backup và phục hồi.
11. **Ai có quyền quan sát key?** Phân quyền công cụ quản trị, log, monitoring và môi trường thử nghiệm.
12. **Đã có test hoặc rà soát quy tắc tạo key chưa?** Nên có biện pháp ngăn mẫu key chứa email, điện thoại, token hoặc thông tin nhạy cảm trước khi đưa vào vận hành.

Các câu hỏi này tập trung vào **mối liên hệ giữa tên khóa và rò rỉ dữ liệu**, đồng thời bảo đảm hệ thống vẫn có thể truy vấn và vận hành được.

## 17. Bài tập áp dụng

### Bài tập 1: phân loại tên khóa

Cho các key:

~~~text
A. profile:email:an@example.invalid
B. profile:u_8e47af59d61b4f59b890a4b6207d9832
C. password-reset:<raw-reset-token>
D. orders:o_e77db3a24c7844f99a70d6c7393e63a6
E. fraud:high-risk:an@example.invalid
F. session:v1:<HMAC-of-random-token>
~~~

Hãy xác định key nào có nguy cơ tiết lộ dữ liệu, key nào có cấu trúc phù hợp hơn.

**Gợi ý:**

- A chứa email; C chứa bí mật; E vừa chứa email vừa tiết lộ trạng thái rủi ro.
- B và D dùng ID đại diện; F chỉ chứa mã HMAC từ token ngẫu nhiên.
- B, D và F vẫn phải có kiểm soát phân quyền, log và quản lý vòng đời.

### Bài tập 2: sửa thiết kế xác minh OTP

Một hệ thống lưu:

~~~text
otp:email:an@example.invalid:482931 -> expires in 5 minutes
~~~

Đề xuất thiết kế không làm lộ email hoặc OTP trong key.

**Một hướng giải:** tạo challenge ID ngẫu nhiên, dùng key `otp:v1:<challenge-id>`, lưu mã xác minh dưới dạng digest có server secret trong value, gắn TTL ngắn, giới hạn số lượt thử và xóa/vô hiệu hóa sau khi thành công. Quy trình xác thực vẫn phải được bảo vệ khỏi brute force.

### Bài tập 3: quyết định giữa ID ngẫu nhiên và HMAC

Hệ A đã có `user_id` nội bộ và muốn lưu cache hồ sơ. Hệ B chỉ có email trong yêu cầu và cần tra cứu cache theo email.

**Gợi ý:**

- Hệ A nên dùng `user_id` nội bộ để tạo tên khóa cache.
- Hệ B nên cân nhắc gọi dịch vụ ánh xạ email → user ID trước. Nếu cần key xác định và chấp nhận độ phức tạp liên quan, có thể dùng HMAC với secret và canonicalization được quản lý.
- Không sử dụng raw email hoặc plain SHA-256 email như giải pháp giấu thông tin nhạy cảm.

### Bài tập 4: phát hiện rò rỉ qua observability

Ứng dụng đã chuyển từ email sang UUID v4 trong Redis. Tuy nhiên, APM vẫn ghi attribute `db.statement` chứa câu truy vấn MongoDB có email nguyên bản, còn metric `cache_access` gắn nhãn `userId` cho mọi người dùng.

**Câu hỏi:** Vì sao vẫn còn rủi ro, và nên sửa điểm nào?

**Gợi ý:** Rủi ro đã dịch chuyển sang đường logging/tracing và metric. Cần lọc/redact truy vấn mang PII, giảm mức ghi dữ liệu không cần thiết và không gắn từng user ID vào metric có cardinality cao. Việc sử dụng UUID trong Redis không giải quyết các kênh rò rỉ khác.

### Bài tập 5: tenant và định danh mờ

Một API cho phép:

~~~text
GET /api/cache/tenant:t_abc:user:u_123:profile
~~~

và trực tiếp đọc Redis key nhận từ URL. Các ID đều là UUID ngẫu nhiên.

**Câu hỏi:** Hệ thống đã an toàn chưa?

**Gợi ý:** Chưa. API không nên cho client chọn key tùy ý. Phải xác thực người gọi, lấy tenant từ ngữ cảnh tin cậy và kiểm tra quyền với tài nguyên trước khi truy cập. Opaque ID chỉ giảm khả năng suy đoán; không ngăn truy cập trái phép khi một key bị lộ.

## 18. Kết luận

Trong NoSQL, **khóa không chỉ là phương tiện tìm dữ liệu; bản thân nó cũng là dữ liệu có thể bị lộ** qua truy vấn, quản trị, log, metrics, backup và API. Một tên khóa chứa email, số điện thoại, giấy tờ định danh hay session token có thể phá vỡ mục tiêu bảo mật ngay cả khi value được mã hóa.

Để giảm rủi ro, hãy:

- Sử dụng ID nội bộ ngẫu nhiên và ổn định cho đối tượng.
- Giữ thông tin cá nhân và bí mật xác thực ra khỏi tên khóa, partition key và sort key bất cứ khi nào có thể.
- Dùng ánh xạ có kiểm soát hoặc HMAC có secret khi thật sự cần tra cứu xác định từ dữ liệu nhạy cảm.
- Thiết kế namespace có cấu trúc nhưng không tiết lộ chi tiết riêng tư.
- Áp dụng phân quyền, mã hóa, redaction, TTL, quản lý secret và kiểm soát vòng đời dữ liệu.
- Kiểm tra cả primary key, secondary index, tên trường động, log, trace và bản sao.

Mục tiêu là giữ **khả năng truy vấn, vận hành và mở rộng của mô hình NoSQL** trong khi tránh để tên khóa trở thành nguồn rò rỉ thông tin nhạy cảm.
