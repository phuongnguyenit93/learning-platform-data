# Tránh làm lộ dữ liệu nhạy cảm qua chuỗi biểu diễn của record

> **Chủ đề:** Java 14 → Giá trị record. Record từng là tính năng *preview* ở Java 14 nhưng đã **chính thức từ Java 16** (JEP 395). Bài này chỉ sử dụng ngữ nghĩa record vẫn còn áp dụng trong Java hiện đại. Các ví dụ biên dịch với `--release 17` bằng JDK được cập nhật như JDK 21/25; không cần cài JDK 14 hay bật `--enable-preview`.

## 1. Điều cần hiểu và làm được

Một `record` mô tả tập dữ liệu có tên, kiểu rõ ràng. Java tự sinh `toString()` để tiện quan sát, nhưng chuỗi đó có thể chứa **giá trị mọi component**. Nếu component chứa token, password, mã xác thực, email hoặc dữ liệu cá nhân, chỉ một lệnh log đối tượng cũng có thể gây rò rỉ.

Sau bài học, bạn cần:

1. Giải thích việc Java tạo `toString()` mặc định và tại sao `private final` không khiến dữ liệu được che giấu trong chuỗi.
2. Tìm các đường chuyển record thành chuỗi: `println`, nối chuỗi, `String.valueOf`, formatter, logger, exception.
3. Viết `public String toString()` tường minh để loại bỏ dữ liệu nhạy cảm.
4. Thiết kế record dành riêng cho audit/log với các component an toàn, thay vì phụ thuộc vào redaction ở mọi nơi.
5. Kiểm tra record lồng nhau, danh sách và đối tượng tham chiếu có `toString()` riêng.
6. Viết kiểm thử ngăn token mẫu xuất hiện trong chuỗi; hiểu vì sao việc này **không** tự bảo vệ JSON, component accessor, bộ nhớ hoặc hệ thống tracing.

## 2. Cơ chế `toString()` được Java tự sinh

Ví dụ:

~~~java
record LoginData(String account, String accessToken) {}
~~~

Record có canonical constructor, hai accessor `account()` và `accessToken()`, cùng `equals`, `hashCode` và `toString` nếu không tự khai báo. Java Language Specification `8.10.3 quy định `toString()` mặc định sinh chuỗi từ **tên record và tên/biểu diễn giá trị các component**. Với component là kiểu tham chiếu, việc biểu diễn dựa trên `toString()` của giá trị tham chiếu. Java không tự biết component nào là secret.

Trên JDK hiện đại, chuỗi thường trông như sau (chỉ là **minh họa**):

~~~text
LoginData[account=demo, accessToken=FAKE_TOKEN_FOR_LESSON]
~~~

**Không phụ thuộc vào chính xác dấu ngoặc, dấu phẩy, khoảng trắng hay cách sắp chữ** của `toString()` do Java sinh. Đặc tả không cung cấp định dạng để ứng dụng parse như JSON/CSV. Điều cần lưu ý về an toàn là **giá trị nhạy cảm nằm trong biểu diễn**.

Thực tế, `record` là một loại class có các component field `private final`, nhưng accessor vẫn là phương thức `public`. Không có setter không đồng nghĩa “giá trị không thể đọc” hay “bí mật được mã hóa”. Chuỗi mặc định được tạo để hỗ trợ quan sát dữ liệu, không phải chính sách kiểm soát thông tin.

### Ví dụ chạy được: nhận diện nguy cơ mà không in bí mật

Tạo tệp **`RecordLeakDemo.java`**:

~~~java
record LoginData(String account, String accessToken) {}

public class RecordLeakDemo {
    public static void main(String[] args) {
        String fakeToken = "FAKE_TOKEN_FOR_LESSON";
        LoginData data = new LoginData("demo", fakeToken);
        String description = data.toString();

        System.out.println(description.contains(fakeToken));
        System.out.println(description.contains("accessToken"));
    }
}
~~~

Biên dịch và chạy bằng JDK có hỗ trợ mức đích 17:

~~~bash
javac --release 17 RecordLeakDemo.java
java RecordLeakDemo
~~~

**Kết quả chính xác:**

~~~text
true
true
~~~

Đoạn mã không in token mà chỉ in kết quả kiểm tra sự xuất hiện của token **giả**. Hai dòng `true` chứng tỏ việc đưa `data` vào console/log có nguy cơ làm lộ giá trị component.

**Không dùng mật khẩu hoặc token thật làm dữ liệu thực hành**, kể cả trên máy cá nhân: terminal, log CI và báo cáo kiểm thử cũng có thể được lưu hoặc chia sẻ.

## 3. Những chỗ có thể gọi `toString()` ngoài ý muốn

| Biểu thức / cơ chế | Điều xảy ra | Rủi ro |
| --- | --- | --- |
| `System.out.println(record)` | Chuyển object thành chuỗi, thường qua `String.valueOf` và `toString` | Nội dung record xuất ra console. |
| `"value=" + record` | Nối chuỗi yêu cầu biểu diễn object | Secret có thể đi vào log hoặc exception. |
| `String.valueOf(record)` | Dùng `toString()` khi tham chiếu khác `null` | Tạo bản sao bí mật dưới dạng `String`. |
| `String.format("%s", record)` | `%s` sử dụng chuỗi biểu diễn object | Dữ liệu có thể xuất ở thông báo hoặc báo cáo. |
| `logger.info("{}", record)` trong một số thư viện | Formatter có thể gọi `toString()` hoặc xử lý object theo cấu hình | Secret có thể đi tới hệ thống log tập trung. |
| `throw new IllegalStateException("Bad: " + record)` | Tạo exception message từ chuỗi của record | Stack trace/tracker có thể lưu bí mật. |
| `record Wrapper(Inner inner)` | `Wrapper.toString()` có thể đưa `Inner.toString()` vào chuỗi | Rò rỉ gián tiếp qua dữ liệu lồng. |

**Không giả định mọi logging framework đều hoạt động giống nhau.** Một logger có thể gọi `toString()`, một structured encoder có thể lấy component dưới dạng trường JSON. Đừng dựa vào một cơ chế redaction đơn lẻ để kết luận mọi kênh đã được bảo vệ.

Vấn đề không biến mất chỉ vì log level là `DEBUG`: log này có thể được bật trong lúc xử lý sự cố, thu thập bởi APM hoặc sao lưu. Ưu tiên loại dữ liệu bí mật **trước khi nó đi vào kênh quan sát**.

## 4. Cách 1: override `toString()` để che toàn bộ

Bạn có thể tự viết `public String toString()` trong record. Đây là cách kiểm soát riêng phần **chuỗi biểu diễn** của object.

Khi không có lý do cần đưa component vào log, sử dụng **chuỗi cố định**. Tránh nối raw component trong phương thức này.

### Ví dụ độc lập: biểu diễn an toàn

Tạo tệp **`RedactedRecordDemo.java`**:

~~~java
import java.util.Objects;

record ApiCredential(String clientId, String secret) {
    ApiCredential {
        Objects.requireNonNull(clientId, "clientId");
        Objects.requireNonNull(secret, "secret");
    }

    @Override
    public String toString() {
        return "ApiCredential[REDACTED]";
    }
}

public class RedactedRecordDemo {
    public static void main(String[] args) {
        String fakeSecret = "FAKE_SECRET_FOR_LESSON";
        ApiCredential credential =
                new ApiCredential("client-demo", fakeSecret);

        System.out.println(credential);
        System.out.println(credential.toString().contains(fakeSecret));
        System.out.println(credential.secret().equals(fakeSecret));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RedactedRecordDemo.java
java RedactedRecordDemo
~~~

**Kết quả chính xác:**

~~~text
ApiCredential[REDACTED]
false
true
~~~

Điểm cần hiểu:

- `println(credential)` dùng phương thức `toString()` tường minh và chỉ in nhãn `REDACTED`.
- Test `contains(fakeSecret)` cho `false`: không có secret trong chuỗi.
- `credential.secret()` **vẫn trả secret**; `toString()` không xóa dữ liệu và không thay đổi API accessor.
- Java vẫn sinh `equals` và `hashCode` dựa trên component nếu ta không tự khai báo các phương thức đó. **Override `toString()` không thay đổi hợp đồng bằng nhau**.
- `Objects.requireNonNull` ở constructor kiểm tra dữ liệu đầu vào, không phải cơ chế bảo vệ secret.
- `@Override` giúp compiler kiểm tra chữ ký. Phương thức `toString()` ghi đè phải là `public`, trả về `String`, không nhận tham số.

Mã **sai về bảo mật** dù cú pháp Java hợp lệ:

~~~java
@Override
public String toString() {
    return "ApiCredential[secret=" + secret + "]";
}
~~~

Đây là **mảnh mã bên trong record** có component `secret`, không phải chương trình chạy riêng. Nó chỉ thay đổi hình thức câu chữ nhưng vẫn làm lộ toàn bộ bí mật.

**Đừng tự gọi `this.toString()` trong chính `toString()`** để xây dựng nội dung: lời gọi đệ quy không có điểm dừng sẽ dẫn tới `StackOverflowError`. Dùng literal hoặc trường được phép hiển thị.

## 5. Cách 2: chỉ hiển thị metadata đã được cho phép

Đôi khi hệ thống cần xác định **loại sự kiện** và **kết quả**, nhưng không cần token hay định danh cá nhân. Hãy chọn trường hiển thị bằng danh sách cho phép (*allowlist*): chỉ xuất các trường được phê duyệt, không dựa vào danh sách đen vài tên như `password`/`token`.

### Ví dụ độc lập: biểu diễn một sự kiện xác thực

Tạo tệp **`AllowedMetadataDemo.java`**:

~~~java
enum AuthAction {
    LOGIN,
    ROTATE_TOKEN
}

record AuthEvent(
        AuthAction action,
        boolean success,
        String accountId,
        String accessToken) {

    @Override
    public String toString() {
        return "AuthEvent[action=" + action
                + ", success=" + success
                + ", accountId=[REDACTED]"
                + ", accessToken=[REDACTED]]";
    }
}

public class AllowedMetadataDemo {
    public static void main(String[] args) {
        String fakeToken = "FAKE_TOKEN_FOR_LESSON";
        AuthEvent event = new AuthEvent(
                AuthAction.LOGIN, true, "user-demo", fakeToken);

        String rendered = event.toString();
        System.out.println(rendered);
        System.out.println(rendered.contains(fakeToken));
        System.out.println(rendered.contains("user-demo"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AllowedMetadataDemo.java
java AllowedMetadataDemo
~~~

Kết quả **chính xác**:

~~~text
AuthEvent[action=LOGIN, success=true, accountId=[REDACTED], accessToken=[REDACTED]]
false
false
~~~

Tại sao `AuthAction` dùng `enum`? Các giá trị `LOGIN` và `ROTATE_TOKEN` là một danh sách khép kín. Không ghép chuỗi tùy ý từ người dùng vào log, vì ngoài rò rỉ dữ liệu còn có thể có **log injection** qua ký tự xuống dòng hoặc cấu trúc điều khiển.

Ở ứng dụng thật, ngay cả `accountId`, địa chỉ IP, request ID hoặc trạng thái nghiệp vụ cũng có thể nhạy cảm tùy người đọc log và yêu cầu bảo mật. Hãy xác định những trường nào **cần thiết và được phép** xuất trước khi tạo thông điệp. Dạng allowlist dễ được kiểm tra hơn cách mặc định in mọi component rồi tìm một vài giá trị để che.

**Đối với password, API key, session token và mã xác thực, ưu tiên không ghi giá trị**, kể cả bốn ký tự cuối hoặc bản hash tự tạo, nếu không có chính sách chuyên biệt. Việc che một phần không luôn làm giá trị đó vô hại.

## 6. Cách 3: thiết kế record dành riêng cho log

Một record nghiệp vụ có thể phải giữ dữ liệu mà một thành phần được quyền sử dụng. Record dành riêng cho logging thì **không cần** có những component này. Cách thiết kế này tránh rủi ro người khác quên viết hoặc vô tình xóa `toString()` redacted.

### Ví dụ độc lập: DTO audit không mang secret

Tạo tệp **`AuditOnlyDemo.java`**:

~~~java
enum EventKind {
    AUTH_ATTEMPT,
    TOKEN_ROTATION
}

record AuditEntry(EventKind kind, boolean success, int statusCode) {}

public class AuditOnlyDemo {
    public static void main(String[] args) {
        AuditEntry event =
                new AuditEntry(EventKind.AUTH_ATTEMPT, false, 401);

        System.out.println(
                event.kind() + " | "
                + event.success() + " | "
                + event.statusCode());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AuditOnlyDemo.java
java AuditOnlyDemo
~~~

Kết quả chính xác:

~~~text
AUTH_ATTEMPT | false | 401
~~~

`AuditEntry` không có password, token hoặc email. Vì vậy `toString()` mặc định của **record này** cũng không thể lấy chúng từ chính component của nó. Những dữ liệu vận hành được giữ lại vẫn giúp nhận biết loại sự kiện và kết quả.

Khi cần correlation ID, dùng định danh kỹ thuật chuyên biệt đã được đánh giá theo quyền riêng tư, không dùng access token hoặc session cookie làm mã truy vết. Hãy bảo vệ quyền truy cập và thời gian lưu trữ log, vì metadata cũng có thể giúp liên kết các hoạt động.

**Ưu tiên thiết kế:** tạo event an toàn ở nơi phát sinh sự kiện, rồi đưa event vào logger. Đừng truyền toàn bộ credential, request body hoặc object chứa PII qua nhiều lớp với hy vọng tầng log sẽ tự biết loại bỏ chúng.

## 7. Bẫy record lồng nhau, `List` và `Map`

Record chứa component kiểu object tham chiếu. `toString()` mặc định của record bao ngoài có thể gọi biểu diễn chuỗi của object bên trong. Nếu component là record, collection hoặc map chứa secret, rò rỉ có thể diễn ra **mà không có từ “token” trong record ở tầng đầu**.

Ví dụ:

~~~java
record SecretPayload(String token) {}
record Envelope(String operation, SecretPayload payload) {}
~~~

Biểu diễn `Envelope` có thể chứa cả `SecretPayload.toString()`, rồi tới `token`. Đặt tên component là `payload` hoặc `context` không khiến dữ liệu trở nên an toàn.

### Ví dụ độc lập: nhìn thấy rủi ro ở hai tầng

Tạo tệp **`NestedRecordDemo.java`**:

~~~java
record UnsafePayload(String secret) {}

record UnsafeEnvelope(String kind, UnsafePayload payload) {}

record MaskedPayload(String secret) {
    @Override
    public String toString() {
        return "MaskedPayload[REDACTED]";
    }
}

record MaskedEnvelope(String kind, MaskedPayload payload) {
    @Override
    public String toString() {
        return "MaskedEnvelope[REDACTED]";
    }
}

public class NestedRecordDemo {
    public static void main(String[] args) {
        String fakeSecret = "FAKE_SECRET_FOR_LESSON";

        UnsafeEnvelope unsafe = new UnsafeEnvelope(
                "auth", new UnsafePayload(fakeSecret));

        MaskedPayload payload = new MaskedPayload(fakeSecret);
        MaskedEnvelope masked = new MaskedEnvelope("auth", payload);

        System.out.println(unsafe.toString().contains(fakeSecret));
        System.out.println(masked);
        System.out.println(masked.toString().contains(fakeSecret));
        System.out.println(payload.toString().contains(fakeSecret));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NestedRecordDemo.java
java NestedRecordDemo
~~~

Kết quả chính xác:

~~~text
true
MaskedEnvelope[REDACTED]
false
false
~~~

Lý do:

- Hai record `Unsafe...` không tự viết `toString()`. Record bao ngoài có biểu diễn chứa object con, rồi object con làm lộ secret.
- `MaskedPayload` redacted biểu diễn của chính nó.
- `MaskedEnvelope` redacted toàn bộ biểu diễn tầng ngoài để không phụ thuộc vào sự thay đổi của component `kind` hay `payload`.
- Mặc dù hai chuỗi được che, mã Java vẫn đọc được `masked.payload().secret()`. **Không có cơ chế phân quyền nào được tạo ra từ override `toString()`.**

Nếu có `record Batch(List<UnsafePayload> items)` hoặc `record Metadata(Map<String, Object> values)`, `toString()` mặc định của collection có thể gọi `toString()` của các phần tử. Một kiểu nested có `toString()` tự viết cũng có thể vô tình tiết lộ dữ liệu. Hãy review **toàn bộ cấu trúc object được đưa tới kênh log**, không chỉ record ở tầng ngoài.

## 8. Exception và logger là nơi dễ rò rỉ nhất

Khi xử lý lỗi, việc nối object vào thông báo là thói quen dễ gây rủi ro:

~~~java
// Minh họa không an toàn nếu credential chứa dữ liệu nhạy cảm:
throw new IllegalArgumentException("Invalid credential: " + credential);
~~~

Đây là **mảnh lệnh** trong một phương thức có biến `credential`. Nếu `credential.toString()` mặc định mang token, exception message sẽ chứa token. Thông báo ấy có thể đi vào stack trace, log, hệ thống giám sát hoặc API error response.

Thay bằng câu mô tả lỗi không chứa dữ liệu gốc:

~~~java
throw new IllegalArgumentException("Invalid credential");
~~~

Nếu cần chẩn đoán, ghi thêm **mã lỗi, bước xử lý hoặc loại thao tác đã được phép lưu**, không nối raw đầu vào.

Ví dụ cách sử dụng tham số logger trong các framework có placeholder `{}` (đây là **mảnh mã minh họa**, không phải Java SE độc lập):

~~~java
// Có thể lộ dữ liệu nếu formatter biểu diễn toàn bộ object:
logger.info("Credential: {}", credential);

// Chỉ truyền kết quả nghiệp vụ được phép:
logger.info("Authentication success: {}", success);
~~~

**Parameterized logging không tự redaction.** Tác dụng của placeholder phụ thuộc framework, formatter và encoder; nếu tham số chứa secret, nó vẫn có thể bị ghi. Với logger JSON hoặc APM, hãy kiểm chứng **output thực tế**, vì chúng có thể đọc component thay vì gọi `toString()`.

Ngoài rò rỉ dữ liệu, raw user input chứa `\r` hoặc `\n` có thể gây **log injection** trong một số định dạng log văn bản. Dùng schema log nhất quán, encoder/structured logging escape đúng và allowlist dữ liệu đầu vào. Không xem việc thay mọi dấu xuống dòng bằng chuỗi rỗng là giải pháp toàn diện.

**Không coi tắt DEBUG là biện pháp bảo mật:** debug có thể được bật lại, log có thể được chuyển tới nhiều nơi và bản sao lưu có thể tồn tại lâu hơn bản ghi gốc. Giảm dữ liệu thu thập ngay từ nguồn.

## 9. Những gì override `toString()` KHÔNG bảo vệ

| Đường truy cập | `toString()` redacted có đủ không? | Cách xử lý |
| --- | --- | --- |
| `println(record)`, nối chuỗi, `String.valueOf(record)` | Có tác dụng khi đường này thật sự gọi `toString()` | Trả literal redacted hoặc không in record nhạy cảm. |
| Logger dùng formatter văn bản | Có tác dụng tùy cách formatter xử lý object | Ưu tiên audit DTO, kiểm thử logger thực. |
| JSON serialization đọc các record component | **Không** | Cấu hình serializer đúng, DTO cho API response riêng, kiểm thử JSON. |
| `record.secret()` | **Không** | Giới hạn API, vòng đời và nơi có quyền dùng secret. |
| Debugger, heap dump, telemetry tự động | **Không** | Phân quyền công cụ, cấu hình APM, kiểm soát dump và dữ liệu nhạy cảm. |
| Record chứa nested list/map | **Không chắc** | Kiểm tra nội dung và cách biểu diễn của toàn bộ object liên quan. |
| `equals` và `hashCode` của record | Không bị thay đổi chỉ vì override `toString()` | Hiểu component vẫn quyết định ngữ nghĩa giá trị. |
| HTTP request/response logging, headers | **Không** | Loại `Authorization`, `Cookie`, token, password, PII khỏi middleware/tracing theo chính sách. |

Một annotation dùng để bỏ qua trường trong JSON serializer **không mặc nhiên** chặn `record.toString()`. Ngược lại, override `toString()` **không mặc nhiên** khiến Jackson hoặc một thư viện JSON khác bỏ qua accessor. Các thư viện có API và cấu hình riêng; hãy test đúng phiên bản đang sử dụng.

Nếu record chứa `String` secret, redaction không xóa nội dung secret đang tồn tại trong bộ nhớ. Nếu dùng `char[]`, bản thân mảng mutable và có thể bị sao chép hoặc in bằng `Arrays.toString`. Không hứa rằng chỉ đổi kiểu component hoặc override `toString()` đã biến record thành kho credential bảo mật.

Record được thiết kế như **data carrier minh bạch và bất biến nông**. Nếu yêu cầu bảo vệ secret ở mức bộ nhớ, vòng đời, cấp quyền hoặc chống lộ qua serialization, cần thiết kế security cụ thể cho **toàn bộ luồng dữ liệu**.

## 10. Viết test hồi quy để chặn secret khỏi chuỗi

Sử dụng **marker giả** cố định. Test không nên in marker hoặc chứa credential thật; nếu thất bại thì chỉ phát ra thông báo lỗi chung. Có thể kiểm tra nhiều đường tạo chuỗi cùng lúc.

Tạo tệp **`SafeRenderingTestDemo.java`**:

~~~java
record SafeToken(String value) {
    @Override
    public String toString() {
        return "SafeToken[REDACTED]";
    }
}

record AuditWrapper(String event, SafeToken token) {
    @Override
    public String toString() {
        return "AuditWrapper[REDACTED]";
    }
}

public class SafeRenderingTestDemo {
    static void requireSecretAbsent(
            String representation, String forbidden) {
        if (representation.contains(forbidden)) {
            throw new AssertionError("secret appeared in output");
        }
    }

    public static void main(String[] args) {
        String fakeSecret = "FAKE_SECRET_FOR_LESSON";
        SafeToken token = new SafeToken(fakeSecret);
        AuditWrapper wrapper = new AuditWrapper("issued", token);

        requireSecretAbsent(token.toString(), fakeSecret);
        requireSecretAbsent(String.valueOf(token), fakeSecret);
        requireSecretAbsent("event=" + wrapper, fakeSecret);
        requireSecretAbsent(String.format("%s", wrapper), fakeSecret);

        System.out.println("rendering checks passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SafeRenderingTestDemo.java
java SafeRenderingTestDemo
~~~

Kết quả chính xác:

~~~text
rendering checks passed
~~~

Bốn phép thử giúp phát hiện hồi quy nếu có người sửa `toString()` và vô tình ghép secret vào chuỗi. Chúng **chưa chứng minh** kênh JSON, logger/framework cụ thể hoặc request tracing an toàn. Khi triển khai sản phẩm thật, kiểm thử output của **từng serializer, encoder, logger và HTTP response** có liên quan, bằng dữ liệu giả được phân loại rõ.

Một ví dụ hồi quy đáng nhớ:

~~~java
record Result(int status) {}
~~~

Nếu sau này mở rộng thành:

~~~java
record Result(int status, String diagnostics) {}
~~~

`toString()` mặc định bắt đầu đưa component `diagnostics` vào biểu diễn. Nếu component mới chứa raw request, token hoặc thông tin cá nhân, chính một thay đổi schema nhỏ cũng có thể tạo lỗ hổng. Vì vậy **mỗi lần thêm component là một dịp phải review luồng ghi log**.

## 11. Checklist thiết kế trước khi ghi log

1. **Phân loại thành phần:** component nào là public, nội bộ, PII, token, password, session ID, tài chính hoặc thông tin bị hạn chế?
2. **Xác định mục đích log:** cần ghi loại sự kiện, thành công/thất bại, mã lỗi, hay thực sự cần giá trị cụ thể?
3. **Tránh đưa dữ liệu không cần thiết vào event:** có thể tạo record audit chỉ mang trường an toàn, thay vì truyền record nghiệp vụ tới logger?
4. **Kiểm soát `toString()`:** nếu record vẫn có khả năng đi qua chuỗi, viết phương thức tường minh với allowlist hoặc literal redacted.
5. **Kiểm tra object lồng:** mỗi component reference có thể chứa collection, map, record khác hoặc thư viện có `toString()` riêng không?
6. **Kiểm tra mọi điểm xuất:** console, exception, logger, debug, JSON, HTTP, APM, telemetry, báo cáo và tracing.
7. **Kiểm thử bằng token giả:** bắt lỗi nếu marker xuất hiện; với serializer, kiểm tra output thật thay vì giả định `toString()` được dùng.
8. **Kiểm soát truy cập log:** phân quyền, thời gian lưu, mã hóa khi cần và xử lý sự cố nếu log đã từng chứa secret.
9. **Review khi schema thay đổi:** thêm component, thay loại component hoặc cấu trúc nested có thể thay đổi cách biểu diễn của toàn object.

**Quy tắc thiết kế quan trọng:** log phải giúp trả lời **điều gì xảy ra**, không cần tái hiện credential. Với token, mật khẩu và mã xác thực, ưu tiên **không ghi giá trị**. Với PII, chỉ xử lý theo yêu cầu pháp lý, chính sách của ứng dụng và mức quyền cần thiết.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Rủi ro | Cách sửa |
| --- | --- | --- |
| Cho rằng record bất biến nên `toString()` an toàn | Bất biến nông không bảo vệ bí mật khỏi log | Phân loại component và kiểm soát output. |
| In record chứa `password`/`token` | Generated `toString()` có thể đưa mọi component vào chuỗi | Không log record; dùng DTO riêng hoặc override redacted. |
| Override `toString()` nhưng nối `secret` | Chuỗi vẫn tiết lộ đúng giá trị cần che | Trả literal hoặc metadata được duyệt. |
| Chỉ kiểm tra record ở tầng đầu | Nested object/list/map có thể tiết lộ secret | Kiểm tra cả đồ thị object. |
| Tưởng `@Override toString` bảo vệ JSON | Serializer thường đọc component độc lập | Cấu hình và kiểm thử JSON riêng. |
| Đưa raw record vào exception message | Hệ thống giám sát lỗi có thể giữ bí mật | Dùng mã/thông điệp lỗi không chứa raw data. |
| Tin rằng parameterized logging tự che secret | Formatter có thể xuất giá trị của tham số | Chỉ truyền dữ liệu an toàn. |
| Ghi nguyên user input vào log | Có thể có PII và log injection | Allowlist, structured encoder đúng cách, kiểm thử. |
| Tắt log debug để tránh kiểm tra an toàn | Debug có thể bật lại; log vẫn lưu ở nơi khác | Loại secret ngay tại nguồn. |
| Test bằng API key thật | CI/terminal/bản lưu kết quả có thể lộ khóa | Chỉ dùng marker giả vô hại. |
| Parse chuỗi record như định dạng cố định | `toString()` mặc định không phải giao thức ổn định | Dùng JSON/schema có chính sách trường rõ ràng. |
| Chỉ che vài ký tự cuối token | Một phần token vẫn có thể bị khai thác/liên kết | Không log token khi không có chính sách đặc biệt. |

## 13. Bài tập thực hành

### Bài 1 — Giữ `toString()` không chứa mật khẩu

Tạo `record UserCredentials(String username, String password)`. Ghi đè `toString()` để chỉ trả `"UserCredentials[REDACTED]"`; tạo đối tượng với marker giả; xác nhận `toString().contains(fakePassword)` bằng `false`. Giải thích vì sao `password()` vẫn lấy được giá trị và vì sao override không tạo cơ chế phân quyền.

### Bài 2 — Thiết kế audit event riêng

Từ một đối tượng xác thực có email, password và kết quả, thiết kế record `AuthenticationAudit` chỉ giữ **loại sự kiện** và **kết quả**. Viết `main` in ra hai giá trị này. Lý giải vì sao không có component mật khẩu là thiết kế dễ kiểm chứng hơn việc luôn redaction sau khi truyền object.

### Bài 3 — Nhận biết rò rỉ nested

Tạo một record bao ngoài với component chứa record bên trong có secret. Dùng marker giả, kiểm tra `outer.toString().contains(marker)`; thay đổi cách biểu diễn cho phù hợp và kiểm tra lại. Sau đó nêu giới hạn của `toString()` override đối với accessor của record con.

### Bài 4 — Phân biệt chuỗi với JSON

Nếu dự án có một thư viện JSON, thử serialize record với `toString()` redacted. Quan sát JSON thực, kiểm tra có trường nhạy cảm không; nếu có, tạo DTO/API response riêng. Không kết luận dữ liệu đã được che chỉ vì `println(record)` an toàn.

### Bài 5 — Kiểm thử thay đổi schema

Thêm component `String rawPayload` vào một record từng an toàn để log; kiểm tra lại toàn bộ các đường `println`, nối chuỗi, exception, logger và serializer. Chỉ được chấp nhận nếu loại dữ liệu mới đã được đánh giá, không có secret trong output và các test tương ứng được cập nhật.

**Tiêu chí hoàn thành:** bạn giải thích được (a) cách `toString()` mặc định sử dụng component; (b) cách thiết kế chuỗi an toàn hoặc log DTO riêng; (c) rủi ro nested; (d) giới hạn của redaction với JSON/accessor/bộ nhớ; (e) cách dùng test marker giả để ngăn hồi quy.

## 14. Tài liệu kỹ thuật và bảo mật còn áp dụng

- [Java Language Specification, `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.3): quy tắc sinh `toString()` theo tên record và giá trị component; cho phép khai báo phương thức tường minh.
- [Oracle API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): contract cho `equals`, `hashCode` và `toString` của record; định dạng mặc định không phải giao thức cần parse.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record chính thức từ Java 16.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nên loại khỏi log, giới hạn logging, redaction, log injection và kiểm chứng thực tế.
- [OWASP Security Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/): khuyến nghị không ghi password, session identifiers và các thông tin nhạy cảm không cần thiết.

**Ghi nhớ:** `toString()` mặc định của record hữu ích cho quan sát nhưng có thể đưa **mọi component** vào chuỗi. Để giảm rủi ro, hãy **không đưa secret vào đối tượng dành cho log**, chỉ hiển thị metadata được cho phép, kiểm tra nested object và viết test cho từng kênh xuất. Override `toString()` chỉ bảo vệ cách biểu diễn dạng chuỗi; các accessor, serializer và bộ nhớ vẫn phải được bảo vệ riêng.