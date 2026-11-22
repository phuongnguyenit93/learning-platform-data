# Hash dữ liệu định danh trong Java Core Logging

## 1. Vì sao không nên log định danh gốc?

Trong ứng dụng Java, log giúp nối các thao tác của cùng một đối tượng qua nhiều request: người dùng, khách hàng, tài khoản, thiết bị, session hoặc giao dịch. Tuy nhiên, ghi trực tiếp email, số điện thoại, số giấy tờ, địa chỉ IP, mã khách hàng có thể nhận dạng được cá nhân hoặc các khóa định danh nhạy cảm vào log sẽ làm tăng phạm vi lộ dữ liệu khi console, file, collector, dashboard hay bản backup bị truy cập sai.

**Hash dữ liệu định danh** trong bối cảnh logging là thay giá trị nhận dạng gốc bằng một mã dẫn xuất (token) để vẫn **tương quan các bản ghi** mà không phải lưu trực tiếp định danh gốc. Với các định danh có thể bị đoán, cách làm phù hợp thường là **HMAC-SHA-256 có khóa bí mật**, phân tách theo mục đích và phạm vi, chứ không phải chỉ gọi `SHA-256(email)`.

~~~text
Không nên:
  event=login_failed email=an@example.com phone=+84900000000

Có thể phù hợp khi cần liên kết nhiều log trong phạm vi cho phép:
  event=login_failed userRef=v1_xxxxxxxxxxxxxxxxxxxxxx requestId=req-42

Nếu chỉ cần theo dõi một request:
  event=login_failed requestId=req-42
  (không cần thêm userRef)
~~~

`userRef` là ví dụ về một định danh giả (pseudonymous identifier), **không phải bằng chứng dữ liệu đã vô danh tuyệt đối**. Người có quyền đối chiếu hoặc người nắm khóa HMAC và danh sách ID ứng viên có thể tái liên kết nó. Ngay cả khi không biết ID gốc, một mã ổn định cũng có thể giúp theo dõi hành vi của cùng một đối tượng theo thời gian.

**Nguyên tắc đầu tiên là giảm dữ liệu**: nếu việc điều tra chỉ cần `requestId`/`traceId` hoặc một số liệu tổng hợp thì **đừng tạo token định danh lâu dài** chỉ để cho đủ trường log. Không được log mật khẩu, private key, mã OTP hoặc credential dưới dạng gốc hay “chỉ hash một lần” với lý do debug; token truy cập, session ID và các bí mật khác cũng cần chính sách loại trừ chặt chẽ.

## 2. Hash, HMAC, mã hóa, masking và tokenization khác nhau thế nào?

| Kỹ thuật | Cách hoạt động | Có thể liên kết cùng đầu vào? | Rủi ro/ứng dụng trong log |
| --- | --- | --- | --- |
| **SHA-256 thuần** | `SHA256(identifier)`, không dùng khóa | Có, mọi nơi dùng cùng thuật toán và chuẩn hóa | Dễ thử danh sách ứng viên khi email/số điện thoại/ID có không gian nhỏ |
| **Hash với salt công khai cố định** | `SHA256(salt || identifier)` | Có nếu dùng cùng salt | Không chống tốt việc tra từ điển khi salt đã biết; đổi salt có thể làm mất khả năng join |
| **Hash với salt ngẫu nhiên mỗi record** | Mỗi event dùng salt khác nhau và lưu salt | Thường không thể so sánh trực tiếp các record | Có ích ở bài toán khác, nhưng không tiện liên kết log của cùng user |
| **HMAC có khóa bí mật** | `HMAC-SHA256(secret, domain || identifier)` | Có trong cùng key + domain, nếu chuẩn hóa nhất quán | Phù hợp tạo token xác định; vẫn là pseudonym, phải bảo vệ key |
| **Mã hóa** | Chuyển plaintext thành ciphertext với key | Tùy thuật toán/mode | Có thể giải mã bởi người có quyền; nếu không cần giải mã, không nên dùng chỉ để route log |
| **Masking** | Che một phần giá trị, ví dụ `a***@example.com` | Có thể liên kết một phần | Dễ nhìn khi hỗ trợ, nhưng vẫn có thể lộ thông tin nhận dạng |
| **Surrogate/random ID** | Sinh mã ngẫu nhiên gắn với request/phiên hoặc một bảng ánh xạ | Tùy vòng đời ID/bảng ánh xạ | Có thể tránh đưa ID thật vào log; cần quản lý ánh xạ và quyền truy cập |

**HMAC không mã hóa dữ liệu**: không có thao tác “giải mã HMAC” để lấy ID ban đầu. Nó cho phép người có khóa **tính lại mã** của một ứng viên và so sánh. Cũng không phải `hashCode()` của Java: `String.hashCode()` chỉ phục vụ cấu trúc dữ liệu, không có tính chất bảo mật cần cho việc bảo vệ định danh.

### Vì sao SHA-256(email) vẫn rủi ro?

Email, số điện thoại, mã vùng hoặc ID tuần tự có **entropy thấp** so với không gian 256 bit của SHA-256. Kẻ có file log có thể tạo hàng triệu ứng viên phổ biến hoặc lấy một danh sách email công khai, tính SHA-256 từng giá trị rồi đối chiếu với token trong log. Hàm hash mạnh không làm cho một tập đầu vào dễ đoán trở nên bí mật.

Ví dụ về một phép đối chiếu từ điển:

~~~text
Log lộ:       userHash = SHA256("an@example.com")
Người xem:    tính SHA256 cho danh sách email ứng viên
Kết quả:      hash khớp => có thể nhận ra email gốc
~~~

Đổi sang `SHA256("static-salt" + email)` khi salt có trong code/repo hoặc log chỉ khiến người tấn công thêm salt khi tính thử. Muốn tạo token xác định, HMAC với **key được bảo vệ độc lập với log** giúp ngăn việc tính ứng viên khi kẻ tấn công chỉ có bản ghi và **không có key**.

Nếu key lộ, người tấn công lại có thể tính token cho danh sách ứng viên; vì vậy hệ thống vẫn cần phân quyền, retention và xử lý sự cố lộ khóa.

## 3. Đặc tả token trước khi triển khai

Trước khi chọn thuật toán, định nghĩa rõ contract của trường log:

- **Mục đích:** cần liên kết log của cùng user trong một request, trong một tenant, trong một dịch vụ hay xuyên nhiều dịch vụ? Đừng mở phạm vi rộng hơn nhu cầu.
- **Nguồn ID:** dùng định danh canonical đã được xác thực/kiểm tra của hệ thống; không tin trực tiếp chuỗi `email`/`userId` do client gửi khi mục tiêu là truy vết người dùng đã xác thực.
- **Kiểu ID:** `user` và `account` có thể cùng chuỗi `"42"` nhưng là hai thực thể khác nhau. Cần đưa loại ID vào phép tính.
- **Phạm vi tenant:** một mã user trùng nhau ở hai tenant phải được xử lý theo chính sách đã định. Với cách ly tenant, đưa tenant canonical vào dữ liệu HMAC hoặc dùng khóa tenant riêng.
- **Phiên bản:** ghi prefix `v1_` hoặc trường `tokenVersion=v1` để phân biệt các lần đổi key/chuẩn hóa về sau.
- **Độ dài đầu ra:** token nguyên HMAC-SHA-256 là 32 byte; có thể cắt còn 16 byte (128 bit) nếu đã đánh giá quy mô và xác suất va chạm. Cắt sau HMAC, **không dùng MD5 để lấy ngắn**.
- **Đích sử dụng:** token phục vụ correlation và chẩn đoán, **không** dùng làm bằng chứng danh tính, authorization token hoặc định danh khóa nghiệp vụ duy nhất.

Một schema log đơn giản:

~~~json
{
  "event": "invoice_lookup_failed",
  "requestId": "req-42",
  "tenantRef": "tenant-a",
  "userRef": "v1_<base64url-truncated-hmac>",
  "tokenVersion": "v1",
  "outcome": "not_found"
}
~~~

Chuỗi `<base64url-truncated-hmac>` ở trên là ký hiệu mô tả format, không phải token tính từ dữ liệu thật. `tenantRef` có thể vẫn là thông tin nhạy cảm đối với hệ thống; việc để tenant ở dạng dễ đọc phải theo chính sách riêng. Với dữ liệu audit nhạy cảm, log correlation thông thường không thay thế bản ghi audit được bảo vệ và thiết kế lưu trữ phù hợp.

## 4. Chuẩn hóa đầu vào: nguyên nhân phổ biến khiến “cùng user” ra hai token

HMAC là phép biến đổi xác định với **cùng byte đầu vào và cùng key**, không tự biết hai cách viết biểu thị một danh tính.

Các cặp dưới đây có thể là cùng hoặc khác ID tùy quy tắc hệ thống:

~~~text
"AN@example.com" so với "an@example.com"
"+84 90 000 0000" so với "0900000000"
"café" viết bằng Unicode ký tự dựng sẵn so với tổ hợp dấu
"00123" so với "123"
" tenant-a" so với "tenant-a"
~~~

**Chỉ chuẩn hóa theo contract của nguồn định danh**:

1. Nếu là **ID nội bộ dạng UUID/canonical string**, dùng nguyên định danh chuẩn từ database/identity service. Không tự xóa leading zero hay lower-case ID case-sensitive.
2. Nếu là **email**, đừng tự động lower-case toàn bộ local-part rồi khẳng định hai địa chỉ là một; quy tắc so sánh phải do hệ thống identity sử dụng quyết định. Nếu có thể, chuyển email thành **user ID nội bộ đã xác thực** trước khi token hóa.
3. Nếu là **số điện thoại**, chuẩn hóa theo quy tắc đã được nghiệp vụ chấp thuận, ví dụ E.164, không tự loại ký tự khiến hai thuê bao bị hiểu thành một.
4. Nếu cần Unicode normalization, quy định NFC/NFKC cùng logic kiểm thử và cùng version cho mọi dịch vụ. Không thay đổi normalization khi nâng cấp mà không đánh giá việc token bị đổi.
5. Từ chối input null, chuỗi không hợp lệ và key thiếu ở tầng thích hợp. Không âm thầm “sửa” ID rồi vô tình gộp hai người.

Với nhiều ngôn ngữ/dịch vụ tính token giống nhau, contract phải ghi rõ **UTF-8**, cấu trúc dữ liệu đưa vào HMAC, tên thuật toán, cách cắt output, encoding, prefix và version. Chỉ ghi công thức `HMAC(tenant + id)` là chưa đủ: nối chuỗi mơ hồ có thể làm `("ab","c")` và `("a","bc")` thành cùng bytes. Dùng độ dài từng field hoặc một định dạng serialization canonical có ranh giới rõ ràng.

## 5. Ví dụ Java 17 độc lập: HMAC-SHA256 cho định danh log

Chương trình sau chỉ dùng JDK 17. Nó tạo token từ **tenant + loại định danh + ID đã được canonical hóa**, có **domain separation** và **length-prefix** để tránh nhầm ranh giới field.

**Cảnh báo:** key cố định bên dưới chỉ để bài học có thể chạy không cần cấu hình. Vì được công khai trong mã, key này **không bảo vệ dữ liệu thực tế**; tuyệt đối không dùng trong ứng dụng, log production, unit test có dữ liệu thật hoặc tài liệu chứa PII thật.

Lưu file **`LogIdentifierHmacDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class LogIdentifierHmacDemo {
    // DEMO ONLY. Không dùng key hard-code trong môi trường thực.
    private static final byte[] DEMO_KEY =
            "DEMO_ONLY_NOT_A_REAL_SECRET_123456"
                    .getBytes(StandardCharsets.UTF_8);

    // Phân tách field bằng độ dài bytes theo big-endian.
    private static void field(Mac mac, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        mac.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
        mac.update(bytes);
    }

    private static String token(String tenant, String type, String id)
            throws Exception {
        // Mac là đối tượng có trạng thái: tạo mới cho mỗi phép tính.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_KEY, "HmacSHA256"));

        // Prefix domain tránh dùng chung với HMAC phục vụ mục đích khác.
        mac.update("log-ref:v1".getBytes(StandardCharsets.UTF_8));
        field(mac, tenant);
        field(mac, type);
        field(mac, id);

        byte[] digest = mac.doFinal();
        // Cắt còn 128 bit minh họa; không tùy tiện cắt ngắn hơn.
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(Arrays.copyOf(digest, 16));
        return "v1_" + encoded;
    }

    public static void main(String[] args) throws Exception {
        String first = token("tenant-a", "user", "user-0042");

        System.out.println("stable=" + first.equals(
                token("tenant-a", "user", "user-0042")));
        System.out.println("tenant_scoped=" + !first.equals(
                token("tenant-b", "user", "user-0042")));
        System.out.println("type_scoped=" + !first.equals(
                token("tenant-a", "account", "user-0042")));
        System.out.println("prefix=" + first.startsWith("v1_"));
        System.out.println("length=" + first.length());
    }
}
~~~

Biên dịch/chạy với Java 17 trở lên:

~~~bash
javac -encoding UTF-8 LogIdentifierHmacDemo.java
java LogIdentifierHmacDemo
~~~

**Stdout xác định** (logic đã thử tương đương với JShell/JDK):

~~~text
stable=true
tenant_scoped=true
type_scoped=true
prefix=true
length=25
~~~

Giải thích:

1. `Mac.getInstance("HmacSHA256")` và `SecretKeySpec` dùng HMAC-SHA-256 của JCA. Cùng **key + bytes + thuật toán** cho cùng kết quả. Vì chỉ in các boolean, chương trình không đưa cả ID gốc lẫn token đầy đủ lên stdout.
2. `"log-ref:v1"` là domain cố định cho **mục đích tạo mã định danh log**. Không tái sử dụng cùng phép tính làm MAC cho xác thực message hoặc một protocol khác.
3. `field(...)` đưa chiều dài bytes UTF-8 (4 byte) rồi giá trị vào phép HMAC. Điều này phân biệt chính xác các tổ hợp field, miễn mọi hệ thống tuân theo contract.
4. `tenant` và `type` tạo **scope**: cùng `id` nhưng tenant/type khác thì token khác với xác suất rất cao. Đây là phân tách correlation, **không thay thế kiểm tra quyền tenant**.
5. `Arrays.copyOf(digest, 16)` lấy 16 byte đầu của HMAC; `Base64.getUrlEncoder().withoutPadding()` mã hóa thành **22 ký tự**. Thêm `v1_` (3 ký tự) tạo độ dài 25.
6. `Mac` không được chia sẻ giữa nhiều thread vì nó có trạng thái và không có bảo đảm thread-safe. Tạo mới mỗi lần như trên là cách minh họa an toàn; có thể tối ưu sau khi đo thực tế.
7. Ví dụ nhận ID **đã canonical hóa**. Code không tự chuẩn hóa input để tránh biến đổi sai ý nghĩa ID. Ở production, ràng buộc null/empty/định dạng và quyền của tenant phải được kiểm tra trước khi gọi.
8. Kết quả `tenant_scoped=true` là tính chất của **những input demo cụ thể** và HMAC ổn định; trong lý thuyết, đầu ra cắt ngắn vẫn có xác suất collision nhỏ, không phải bảo đảm duy nhất tuyệt đối.

### Tại sao không dùng `MessageDigest.getInstance("SHA-256")`?

`MessageDigest` dùng cho hash **không có khóa**. Khi định danh có ít ứng viên, nó cho phép ai có bản log tự tính hash của danh sách ID và dò khớp. HMAC yêu cầu key bí mật để tính token, tạo thêm rào cản đáng kể khi key được bảo vệ tốt. Chỉ “hash kỹ hơn” bằng nhiều vòng SHA-256 hoặc ghép một static salt trong mã không thay thế quản trị secret.

## 6. Dùng khóa bí mật thế nào ở production?

Ví dụ vừa rồi minh họa phép tính, **không phải bộ quản lý khóa sẵn sàng production**. Khi triển khai thực tế cần:

- **Sinh key đủ ngẫu nhiên:** ví dụ 32 byte (256 bit) do CSPRNG/secret manager tạo. Không dùng password người vận hành, key ngắn đoán được, tên tenant hoặc chuỗi cố định từ code.
- **Lưu ở nơi quản trị bí mật:** secret manager/KMS hoặc cơ chế tương đương với ACL, audit và vòng đời. Nếu ứng dụng nhận key qua biến môi trường/file secret, bảo vệ cấu hình process, quyền truy cập và đường deploy; không log giá trị môi trường.
- **Không nhúng vào source, jar, image, config trong Git hoặc test snapshot.** Mọi người đọc source chứa demo key phải hiểu nó không có tác dụng bảo mật.
- **Phân quyền đúng nhu cầu:** chỉ service cần tính token mới nhận key. Dashboard và collector thường **không cần key**, chỉ lưu token.
- **Phân lập phạm vi:** với dữ liệu giữa tenant/môi trường không được tương quan, đưa scope vào MAC message và cân nhắc tách key theo môi trường/tenant khi có yêu cầu cách ly mạnh hơn.
- **Không fallback khi key thiếu:** không tự chuyển sang `SHA256(rawId)` hoặc log thẳng rawId. Nên chặn khởi động hoặc vô hiệu hóa trường userRef có cảnh báo vận hành an toàn, tùy yêu cầu hệ thống.

Ví dụ **snippet** về cách đọc một key Base64 đã được hệ thống secret phân phối (không phải chương trình độc lập; không thực hiện lấy key trực tiếp từ cloud):

~~~java
import java.util.Base64;
import javax.crypto.spec.SecretKeySpec;

String configured = System.getenv("LOG_PSEUDONYM_KEY_B64");
if (configured == null || configured.isBlank()) {
    throw new IllegalStateException("logging pseudonym key missing");
}
byte[] keyBytes = Base64.getDecoder().decode(configured);
if (keyBytes.length != 32) {
    throw new IllegalStateException("logging pseudonym key has invalid size");
}
SecretKeySpec hmacKey = new SecretKeySpec(keyBytes, "HmacSHA256");
// Truyền hmacKey cho helper được quản lý vòng đời; tuyệt đối không log keyBytes.
~~~

Đây chỉ là cách nhận key từ **một kênh cấu hình**, không có nghĩa biến môi trường là nơi an toàn tuyệt đối; secret manager, quản lý truy cập process và chính sách deploy vẫn rất quan trọng. Khi có lỗi Base64/key size, không in chuỗi key vào exception hoặc telemetry.

Trong ví dụ chạy thật, nên **tiêm key** vào lớp tính HMAC thay vì giữ `DEMO_KEY` như mã học tập. Dùng `SecretKey` đã tiêm và tạo một đối tượng `Mac` mới cho từng phép tính. Không để logging backend tự đọc dữ liệu nhạy cảm từ cấu hình người dùng rồi chuyển không kiểm soát tới appender.

## 7. Key rotation và khả năng liên kết log theo thời gian

Giả sử một người có token `v1_abc...` từ khóa `K1`. Khi đổi sang `K2`, cùng người đó thường có token `v2_xyz...`. Đây là điều bình thường vì HMAC phụ thuộc key. **Đổi key không đổi được token đã tồn tại trong log cũ.**

Thiết kế rotation nên trả lời:

1. Khi nào `v1` ngừng được dùng để **ghi mới** và khi nào `v2` có hiệu lực? Có phải tất cả instance dùng cùng version tại cùng thời điểm?
2. Có cần join log cũ–mới không? Nếu cần, giới hạn thời gian và vai trò được phép nối; tránh tạo đường tương quan vĩnh viễn không cần thiết.
3. Có giữ key cũ không? Nếu lưu, phải có thời hạn, quyền đặc biệt, audit; xóa đúng lúc theo retention/policy.
4. Nếu key lộ, liệu có cần ngừng sử dụng ngay, điều tra các record đã xuất, thu hồi quyền hoặc xóa/restrict log theo chính sách?
5. Token từ nhiều service có cần khớp không? Chúng phải thống nhất serialization, canonicalization, domain và key/scope theo quy định; không chia sẻ key rộng chỉ vì tiện tìm kiếm.

**Gắn version vào token hoặc field log** để người điều tra biết sự kiện dùng quy tắc nào. Không lấy prefix `v1_` làm key ID bí mật; prefix chỉ là metadata. Một số hệ thống chọn token khác nhau cho từng ngày hoặc request để **giảm khả năng theo dõi lâu dài**; đánh đổi là khó join sự kiện giữa các khoảng đó.

Không khuyến khích ghi đồng thời cả token v1 và v2 của mọi người dùng suốt thời gian dài chỉ để join thuận tiện: việc này tăng khả năng liên kết và bề mặt dữ liệu. Nếu thật sự cần migration mapping, cần mục đích, thời gian tồn tại, quyền và kiểm toán riêng.

## 8. Tích hợp vào logger: biến đổi trước khi phát sự kiện

Hash/HMAC phải được tạo **trước khi giá trị đi vào hệ thống log**. Gắn nguyên ID vào `MDC` rồi hy vọng một formatter nào đó che lại là không an toàn: appender phụ, error handler, async queue, collector hoặc JSON encoder khác vẫn có thể xuất ID nguyên.

Với backend dùng SLF4J, ý tưởng cấu trúc:

~~~java
// Snippet trong service: không phải chương trình độc lập.
String userRef = tokenService.forUser(verifiedTenantId, canonicalUserId);
logger.info("event=profile_loaded userRef={} requestId={}",
        userRef, requestId);
~~~

`tokenService` phải quản lý HMAC key thật, phạm vi tenant/type và version; các biến lấy từ thành phần ứng dụng đã xác thực. **Không** log `canonicalUserId` trong debug message bên cạnh `userRef` vì như vậy vô hiệu hóa mục đích bảo vệ.

Nếu nhiều đoạn code cần context:

~~~java
// Snippet minh họa SLF4J MDC.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("userRef", userRef);          // Đã HMAC trước đó.
    MDC.put("requestId", requestId);     // ID tương quan riêng của request.
    logger.info("event=profile_loaded");
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
~~~

Đoạn trên cần import `java.util.Map` và `org.slf4j.MDC`; không phải chương trình JDK thuần. Layout như Logback `%X{userRef}` có thể hiện token đã đưa vào MDC. Khi dùng thread pool, MDC có thể không tự truyền từ producer sang worker; capture/restore theo boundary, luôn dọn ở `finally` để không gắn token của user A lên event của user B.

**Hash ở async appender sau khi enqueue không phải lựa chọn mặc định tốt** nếu event đã chứa raw ID. Các buffer/sink khác có thể đã nhìn thấy giá trị thô, và worker có thể không còn context đúng. Cần thực thi chính sách ở điểm tạo event hoặc tại một lớp logging facade bắt buộc và đã kiểm thử.

### Structured logging và ngoại lệ

Một event JSON an toàn có thể chứa:

~~~json
{
  "event": "profile_lookup_failed",
  "userRef": "v1_<token>",
  "requestId": "req-42",
  "status": "not_found"
}
~~~

Không nên cho `Throwable.getMessage()`, stack trace, URL query hoặc payload được đưa vào log **không kiểm soát** nếu chúng có thể chứa email, số điện thoại, API key hoặc ID thô. Ngay cả khi field `userRef` được tạo đúng, một câu `log.error("lookup failed for " + rawEmail, e)` vẫn làm lộ dữ liệu.

Parameterized logging (ví dụ SLF4J `"userRef={}"`) giúp định dạng, nhưng **không tự ẩn dữ liệu nhạy cảm**. Hash một field không thay thế masking, redaction, xử lý log injection, chính sách lưu trữ hay quyền truy cập log.

## 9. HMAC không thay thế cơ chế bảo vệ quyền riêng tư

Pseudonymization giảm việc xuất hiện định danh trực tiếp, nhưng có những rủi ro còn lại:

| Tình huống | Rủi ro còn lại | Biện pháp bổ sung |
| --- | --- | --- |
| Token ổn định nhiều năm | Có thể theo dõi người dùng theo thời gian | Giảm retention, thu hẹp scope/key và vòng đời token |
| Key bị lộ | Kẻ tấn công có thể thử các ID ứng viên | Secret management, rotation, phản ứng sự cố và giới hạn truy cập |
| Input có tập ứng viên nhỏ | Token có thể bị xác nhận khi key/ánh xạ rò | Kiểm soát key, không gọi HMAC là vô danh tuyệt đối |
| Log chứa thêm email trong message | Trường `userRef` an toàn hơn nhưng event vẫn lộ PII | Redact mọi field, stack trace và request metadata |
| Tenant A và B dùng cùng ID nội bộ | Có thể link chéo nếu không có scope | Đưa tenant canonical/type/purpose vào phép HMAC |
| Token dùng làm authorization | Token dự đoán/quan sát được có thể bị lạm dụng | Không dùng log token làm credential hoặc chứng cứ quyền |
| Hai định danh khác nhau cùng token do cắt ngắn | Va chạm dẫn đến join nhầm hiếm gặp | Chọn đủ bit, định lượng rủi ro, không làm khóa nghiệp vụ |
| Log bị sao chép qua collector/backup | Tăng bề mặt lưu giữ và truy cập | RBAC, encryption, retention, xóa và audit theo chính sách |

**Dữ liệu đã HMAC vẫn có thể là dữ liệu cá nhân trong nhiều bối cảnh pháp lý** nếu có khả năng liên kết lại với một người hoặc được sử dụng để theo dõi. Quyết định tuân thủ phụ thuộc quy định, loại dữ liệu, mục đích và khả năng tái nhận dạng; cần đánh giá cùng đội bảo mật/pháp chế thay vì tuyên bố “hash xong là được phép giữ mãi”.

### Những dữ liệu không nên “cứ hash rồi log”

- **Mật khẩu, private key, mã OTP, recovery code:** không ghi vào log, kể cả bản hash; không dùng hệ thống log làm kho credential.
- **Access token, refresh token, session cookie:** ưu tiên không log. Nếu cần theo dõi phiên cho điều tra, cân nhắc ID tương quan ít đặc quyền hoặc HMAC trong phạm vi và TTL chặt, theo chính sách được phê duyệt.
- **Dữ liệu y tế, tài chính, giấy tờ định danh hoặc vị trí chính xác:** chỉ xử lý nếu thật sự có mục đích được phép; HMAC không xóa rủi ro privacy.
- **Email/điện thoại:** nếu cần liên hệ người dùng, thực hiện qua hệ thống nghiệp vụ được cấp quyền thay vì “đảo ngược token” từ log.

## 10. Hiệu năng và thread safety

HMAC-SHA-256 thường đủ nhanh cho ID ngắn, nhưng không nên biến mỗi lần log thành một chuỗi tính toán đắt đỏ mà không đo. Chú ý:

1. Với **DEBUG** có thể bị tắt, tránh tạo token/format dữ liệu tốn kém trước khi biết event có thực sự cần phát. Có thể kiểm tra `logger.isDebugEnabled()`, nhưng không vì thế mà bỏ các log audit/security bắt buộc.
2. `Mac` là đối tượng có trạng thái và không có cam kết thread-safe. Không chia sẻ một instance `Mac` giữa nhiều thread. Tạo mỗi lần như ví dụ hoặc thiết kế pooling/thread-local đã kiểm thử và dọn đúng khi key rotation.
3. **Caching** token có thể giảm phép HMAC lặp lại, nhưng cache phải giới hạn dung lượng/TTL và có biện pháp bảo vệ ID gốc trong memory; không tạo map ID nhạy cảm tồn tại vô hạn.
4. Nếu log quá nhiều userRef, cardinality trong **log field** có thể chấp nhận được; nhưng không đưa một token riêng mỗi user vào **nhãn metric**, vì có thể bùng nổ số time series.
5. Nếu không có nhu cầu join giữa request, dùng `requestId` ngẫu nhiên theo request thay vì HMAC trên định danh lâu dài, vừa ít dữ liệu vừa dễ vận hành.

Việc cắt token 16 byte chỉ giảm kích thước hiển thị; vẫn có phép tính HMAC-SHA-256 đầy đủ. Mã output 128 bit không có bảo đảm duy nhất toán học, nên không làm primary key cho nghiệp vụ.

## 11. Kiểm thử đúng chức năng và an toàn

### Test chức năng

Với một key, một domain và ID canonical cố định:

- Cùng tenant/type/ID → **token ổn định**; có thể nối các log hợp lệ cùng phạm vi.
- Cùng ID, **khác tenant** → token khác; kiểm tra không liên kết chéo theo schema đã quy định.
- Cùng ID, **khác type/purpose** → token khác; tránh đụng nhau giữa user và account.
- Cùng input, **khác key/version** → token khác; cần xác minh khi rotation.
- Chuỗi Unicode, input rỗng, null, ID dài và dữ liệu không canonical → được xử lý theo chính sách rõ ràng, không tạo sai ID hoặc log raw value.
- Trong hệ thống phân tán, cùng contract và cùng key/scope → tạo token tương thích giữa các service **được phép** tương quan.
- Token có prefix/version và encoding phù hợp; khi cắt 16 byte HMAC, `Base64url` không padding có 22 ký tự, cộng prefix `v1_` là 25.

### Test chống rò dữ liệu

1. Tạo dữ liệu thử có marker như `TEST_PRIVATE_ID_12345` rồi phát các log INFO/DEBUG/WARN/ERROR, kể cả exception.
2. Tìm marker **trong mọi đầu ra**: stdout, file, async appender, collector, index, dashboard, error reporting và trace attributes. Kết quả kỳ vọng: không xuất hiện raw marker ở nơi không được phép.
3. Kiểm tra khi **key không tồn tại hoặc sai định dạng**: không có fallback ghi thẳng ID hay SHA256 không khóa; lỗi cấu hình được nhận biết nhưng không in secret.
4. Kiểm tra khi **MDC chạy trong thread pool**: task A rồi B trên cùng thread không mang userRef/tenant của nhau.
5. Kiểm tra khi rotation: không có hai version bị trộn không rõ lý do, điều tra vẫn đọc được phiên bản, key cũ được hạn chế đúng cách.
6. Kiểm tra policy storage: người chỉ được xem log của tenant A không tìm/đọc được event tenant B bằng cách sửa truy vấn.
7. Thử lộ một phần pipeline: dữ liệu trong log riêng lẻ không đủ để tra ngược ID chỉ bằng SHA-256 dictionary; nếu key bị lộ, đánh giá quy trình ứng phó.

**Không dùng email/số điện thoại thật làm test vector trong output của bài test.** Test fixture nên là dữ liệu giả, không bị tái sử dụng như key production.

## 12. Các lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `String.hashCode()` | Hash không dành cho bảo mật, va chạm dễ, không có secret | Dùng cơ chế pseudonymization có đánh giá rủi ro |
| Dùng `SHA256(email)` rồi gọi “ẩn danh” | Có thể thử từ điển các email/phone | Hạn chế dữ liệu trước; nếu cần join, dùng HMAC với key bí mật |
| Đặt static salt/pepper trong Git | Người đọc code có thể thử ứng viên | Quản lý key độc lập trong secret manager/KMS |
| Dùng salt ngẫu nhiên mỗi event nhưng muốn join | Mỗi bản ghi có token khác, không so sánh trực tiếp được | Dùng HMAC xác định theo scope/phiên bản |
| HMAC không phân biệt tenant/type | Có thể link ID qua các ngữ cảnh không được phép | Domain separation, tenant/type trong MAC input |
| Lower-case ID tùy tiện | Hai ID khác nhau có thể bị gộp | Chuẩn hóa theo identity system |
| Hash ở appender nhưng raw nằm trong message/MDC | Đầu ra khác vẫn lộ giá trị gốc | Token hóa trước khi tạo log và kiểm thử end-to-end |
| Key bị thiếu thì log raw | Một sự cố cấu hình dẫn tới lộ dữ liệu nghiêm trọng | Fail closed cho trường nhạy cảm; cảnh báo an toàn |
| Gắn token dài hạn vào metrics labels | Tăng cardinality và khả năng theo dõi người | Dùng nhãn có tập giá trị nhỏ; correlation trong log field có kiểm soát |
| Coi hash là authorization | Ai đọc token có thể bị nhầm là chủ tài khoản | Authorization dựa trên principal đã xác thực |
| Chỉ bảo vệ log hiện tại, bỏ quên backup | Bản cũ vẫn giữ PII/token | RBAC, retention và xóa theo toàn bộ vòng đời |
| Reuse một `Mac` giữa các thread | Đối tượng có trạng thái, có thể sai kết quả | Mỗi phép tính một instance hoặc quản lý thread-local có kiểm chứng |

## 13. Checklist đưa vào production

1. **Hỏi có thực sự cần định danh liên kết nhiều log không.** Nếu không, chỉ giữ `requestId` hoặc `traceId`.
2. **Phân loại dữ liệu nguồn** và xác nhận mục đích được phép; không ghi raw ID bí mật hay credential.
3. **Chọn HMAC-SHA-256 có key bí mật** khi cần token xác định cho các ID có thể đoán; không dùng hash không khóa làm lớp bảo vệ chính.
4. **Viết contract byte-level**: canonical ID, tenant, type, domain, UTF-8, length-prefix, version, độ dài token và output encoding.
5. **Giữ key ngoài mã nguồn**, quản lý theo vai trò, môi trường và quy trình rotation; không có fallback làm lộ raw ID.
6. **Token hóa trước logger**, bảo đảm exception, MDC, structured JSON, async pipeline không lộ dữ liệu thô.
7. **Thử tính ổn định và tính phân tách**, cả trường hợp null, Unicode, key rotation, nhiều service và thread pool.
8. **Giữ log trong phạm vi quyền truy cập/retention**, theo dõi việc xuất PII ở mọi sink và bản sao lưu.
9. **Đừng coi userRef là credential hoặc ID nghiệp vụ**, và đừng dùng token dài hạn để theo dõi khi không cần thiết.
10. **Đánh giá lại định kỳ**: trường log nào đang được thu, ai đọc, thời gian giữ, key nào còn hoạt động và việc liên kết có vượt mục đích ban đầu không.

**Ghi nhớ:** Hash giúp thay đổi hình thức định danh nhưng **không tự làm dữ liệu vô danh**. Đối với ID có thể đoán và cần correlation, HMAC với key bí mật, canonicalization rõ ràng, scope và version được kiểm soát thường hữu ích hơn SHA-256 thuần. Giải pháp an toàn nhất vẫn là **không log dữ liệu không cần thiết**, kết hợp bảo vệ key, phân quyền, xóa theo retention và kiểm thử rò rỉ đầu-cuối.

### Tài liệu tham khảo

- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): các loại dữ liệu cần loại trừ, giảm/che dữ liệu nhạy cảm, bảo vệ log khi lưu và truyền.
- Java SE 17 — [Java Cryptography Architecture Reference Guide: Mac/HMAC](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html).
- Java SE 17 — [`javax.crypto.Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html), [`SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html), [`Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html) và [Manual](https://www.slf4j.org/manual.html).