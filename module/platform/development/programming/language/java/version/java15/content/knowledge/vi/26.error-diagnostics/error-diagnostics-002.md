# Giới hạn thông tin khi exception do chương trình tự tạo (Java 15+)

## 1. Vấn đề: exception là công cụ chẩn đoán, không phải phản hồi công khai

Khi tự tạo và ném một exception trong Java, lập trình viên thường muốn biết **điều gì đã sai, tại vị trí nào và phải khắc phục ra sao**. Nhưng một exception có thể đi qua các tầng xử lý, logger, HTTP framework, message queue hoặc hệ thống giám sát rồi trở thành dữ liệu mà **người dùng/đối tượng không tin cậy** có thể xem.

Ví dụ sai về an toàn thông tin:

```java
// Phản ví dụ, KHÔNG dùng trong production:
throw new IllegalArgumentException(
        "Could not authorize account=" + accountId
        + "; token=" + accessToken
        + "; databaseHost=" + internalHost);
```

Ngay cả khi exception chỉ được ném ở service nội bộ, chuỗi này có thể bị lộ nếu caller dùng `ex.getMessage()`, trả `ex.toString()` qua API, in stack trace, hoặc cấu hình logger tự động kèm exception.

**Mục tiêu của bài trong nhóm “Chẩn đoán lỗi”:**

- Giới hạn **thông tin được phép nằm trong exception message** ngay từ lúc tạo lỗi.
- Phân biệt **thông báo cho client** với **chi tiết vận hành nội bộ**.
- Không làm lộ thông tin bí mật trong `message`, `cause`, `suppressed exceptions`, stack trace hoặc object được serialize.
- Vẫn chẩn đoán được lỗi bằng **mã lỗi ổn định, correlation/request ID, log nội bộ có kiểm soát** và công cụ quan sát.
- Xử lý lỗi không che giấu hành vi nguy hiểm hoặc biến lỗi bảo mật thành thành công.

Những quy tắc này áp dụng cho `Exception`, `RuntimeException`, exception tùy chỉnh và cơ chế `Throwable` hiện hành trong Java 15+. Bài sử dụng API **vẫn được hỗ trợ trong Java hiện đại**, không dựa vào cơ chế logging/exceptions đã lỗi thời.

## 2. Tại sao thông tin trong exception có thể nguy hiểm?

Một exception chứa nhiều thành phần hơn một chuỗi `message`:

| Thành phần | API | Rủi ro nếu để lộ ra client/log không kiểm soát |
| --- | --- | --- |
| **Detail message** | `Throwable.getMessage()` | Token, mật khẩu, thông tin cá nhân, path, SQL, raw request |
| **Localized message** | `getLocalizedMessage()` | Có thể trả cùng dữ liệu như `getMessage()`; bản dịch không tự làm sạch |
| **Loại exception** | `getClass().getName()` / `toString()` | Có thể lộ class/package/framework, cấu trúc hệ thống |
| **Stack trace** | `getStackTrace()`, `printStackTrace()` | Lộ class, method, file, line number, đường xử lý |
| **Cause chain** | `getCause()` | Lộ message/stack của lỗi tầng dưới, đôi khi chứa bí mật |
| **Suppressed exceptions** | `getSuppressed()` | Lộ lỗi khi đóng resource hoặc các ngoại lệ đi kèm |
| **Fields riêng của exception** | Các getter trên custom exception | Lộ raw payload, account ID, credential, query, path |
| **Serialization tự động** | Framework/serializer/observability agent | Có thể thu exception object và duyệt cả message/cause/stack |

**Điểm dễ bỏ sót:** Đổi message của exception ngoài thành `"Operation failed"` **không xóa** message trong exception nguyên nhân (`cause`) hoặc suppressed exceptions. Nếu framework ghi `logger.log(..., ex)` hoặc trực tiếp serialize exception, thông tin nội bộ vẫn có thể xuất hiện.

Ngược lại, không phải tất cả thông tin lỗi đều phải bí mật: một thông báo **đã được kiểm duyệt** như `"Quantity must be positive."` giúp người dùng sửa đầu vào mà không hé lộ dữ liệu nhạy cảm.

## 3. Nguyên tắc tách ba tầng thông tin

```text
  Lỗi tại domain / adapter / database / remote service
                     |
                     v
          Exception nội bộ (Throwable)
         code, safe message, optional cause
                     |
            Error boundary / mapper
            /                     \
           v                       v
   Phản hồi công khai          Telemetry nội bộ
   - mã lỗi ổn định            - request ID
   - thông báo an toàn         - error code / category
   - request ID không nhạy cảm - loại lỗi đủ để điều tra
   - HTTP status phù hợp       - stack trace chỉ nếu an toàn
   KHÔNG exception object      - access control / retention
```

Ba tầng có vai trò khác nhau:

1. **Domain/application:** ném exception có kiểu và ý nghĩa đúng. Dữ liệu đầu vào không tin cậy **không được** tự động ghép vào error message.
2. **Boundary/API adapter:** ánh xạ exception sang **cấu trúc phản hồi riêng**; chỉ xuất code/message thuộc danh sách được phép và request ID do server kiểm soát.
3. **Vận hành/chẩn đoán:** ghi log/trace/metrics tối thiểu cần thiết cho điều tra, có kiểm soát truy cập và lọc dữ liệu nhạy cảm.

Không dùng exception làm đối tượng HTTP response trực tiếp. Một `Throwable` vốn là cấu trúc chẩn đoán, không phải DTO công khai.

### 3.1. Danh sách dữ liệu nên tránh trong lỗi

- Mật khẩu, API key, session cookie, `Authorization` header, bearer token, private key, seed.
- Dữ liệu cá nhân: email/số điện thoại đầy đủ, số giấy tờ, địa chỉ, thông tin sức khỏe/tài chính.
- Raw request body, raw JWT, OAuth authorization code, toàn bộ query string có token.
- Chuỗi kết nối DB, hostname nội bộ, đường dẫn file riêng tư, tên bucket, câu SQL chứa parameter.
- Trạng thái phân quyền hoặc thông tin cho phép **user enumeration**: ví dụ trả kết quả khác nhau cho tài khoản có tồn tại và không tồn tại nếu điều đó là nhạy cảm.
- Nội dung record của tenant khác hoặc các ID giúp suy đoán tài nguyên không được phép truy cập.
- Stack trace, tên class/package nội bộ và phiên bản dependency trong phản hồi công khai.

**Không phải ID nào cũng nhạy cảm như nhau:** một request ID ngẫu nhiên do server sinh và chỉ dùng để tương quan thường có thể trả công khai; còn ID tài khoản, session token hoặc trace metadata có khả năng suy đoán phải qua chính sách riêng.

## 4. Thiết kế custom exception có mã lỗi ổn định

Một cách thực tế là **không cho code truyền tùy ý message động**, mà tạo một `enum` chứa mã lỗi và thông báo công khai đã được duyệt:

```java
enum ErrorCode {
    INVALID_QUANTITY("Quantity must be positive."),
    DEPENDENCY_UNAVAILABLE("Service temporarily unavailable."),
    INTERNAL_ERROR("Request could not be completed.");

    final String publicMessage;

    ErrorCode(String publicMessage) {
        this.publicMessage = publicMessage;
    }
}
```

Điểm tốt của mô hình:

- Mã lỗi có tính **ổn định**, phù hợp cho monitoring và client behavior.
- Thông báo không ghép trực tiếp token, raw input hoặc chi tiết triển khai.
- Người dùng vẫn có thông tin hành động được khi lỗi là input hợp lệ để công khai.
- Có thể địa phương hóa thông báo bằng **bộ template được kiểm duyệt**, không bằng cách đưa `ex.getLocalizedMessage()` ra client.
- Khi đổi dependency nội bộ, public error contract không cần thay đổi.

Ở class exception tùy chỉnh:

```java
static final class AppException extends RuntimeException {
    private final ErrorCode code;

    AppException(ErrorCode code) {
        super(code.publicMessage);
        this.code = code;
    }

    AppException(ErrorCode code, Throwable cause) {
        super(code.publicMessage, cause);
        this.code = code;
    }

    ErrorCode code() {
        return code;
    }
}
```

Đây là **các khai báo minh họa cần đặt trong lớp Java**, chưa phải một file chạy độc lập. Chương trình đầy đủ có ở phần 7.

**Lưu ý quan trọng:** Constructor có `cause` chỉ an toàn khi **vòng đời exception và đường log/serialize được kiểm soát**. Dù message bên ngoài là chuỗi an toàn, `cause` vẫn có thể chứa thông tin nhạy cảm. **Không tự động xem mọi `Throwable` của thư viện tầng dưới là an toàn để lưu hoặc log.**

### 4.1. Nên dùng checked hay unchecked exception?

Java phân biệt `Exception` (checked, trừ subclasses của `RuntimeException`) và `RuntimeException` (unchecked). Quyết định checked/unchecked tùy **hợp đồng gọi API và khả năng phục hồi**, chứ **không** quyết định exception có làm lộ thông tin hay không.

- Một lỗi domain không thể phục hồi ở điểm gọi có thể được biểu diễn bằng một `RuntimeException` có code.
- Một tình huống caller phải xử lý rõ (ví dụ lỗi đọc file được khai báo qua `IOException`) có thể dùng checked exception.
- Cả checked và unchecked đều có thể làm lộ thông tin nếu message/cause/log không được kiểm soát.
- Không dùng `Error` làm lớp lỗi nghiệp vụ bình thường.

Không biến mọi lỗi thành `RuntimeException` chung chung rồi mất mã phân loại; nhưng cũng đừng tạo hàng trăm custom exception class khi enum/mapping theo domain đã đủ.

## 5. Đặt giới hạn ngay tại nơi ném exception

### 5.1. Khi validate đầu vào

**Sai**:

```java
// Phản ví dụ: raw input có thể chứa PII, token hoặc ký tự điều khiển.
throw new IllegalArgumentException("Invalid user value: " + rawInput);
```

**Đúng hơn**:

```java
// Snippet trong method; AppException và ErrorCode đã được định nghĩa.
throw new AppException(ErrorCode.INVALID_QUANTITY);
```

Thông báo `Quantity must be positive.` cho phép người dùng sửa dữ liệu nhưng không in nguyên dữ liệu đã nhập. Nếu cần nêu tên field, dùng **field identifier thuộc allowlist** (ví dụ `"quantity"`), không dùng field name do client gửi tùy ý.

Một biểu thức `Objects.requireNonNull(value, "Missing token="+secret)` cũng có nguy cơ rò rỉ nếu message được log. **Thông điệp tự thiết kế luôn phải được xem như dữ liệu có thể thoát khỏi ranh giới hiện tại.**

### 5.2. Khi lỗi dịch vụ phụ thuộc

**Sai**:

```java
// Phản ví dụ:
throw new RuntimeException(
        "DB error: " + sql + "; username=" + dbUser
        + "; password=" + dbPassword, cause);
```

**Đúng hơn**:

```java
// Snippet trong method, cần định nghĩa/kiểm soát cause:
throw new AppException(ErrorCode.DEPENDENCY_UNAVAILABLE, cause);
```

Thông báo public được chọn cố định. Nhưng cần **đánh giá cause**: một driver exception có thể chứa SQL/connection URL hoặc tham số đã nạp; nếu cause chứa secret, không nên tự động log/serialize toàn bộ cây lỗi. Trong một số thiết kế cần **không giữ raw cause** trong exception được truyền qua các tầng rộng hoặc boundary; thay vào đó ghi nhận một **diagnostic event an toàn** và tạo exception được làm sạch.

### 5.3. Lỗi không xác định

Không nên phản hồi công khai:

```text
java.lang.NullPointerException: Cannot invoke ...
at com.internal.billing.SecretCredentialProvider.java:137
```

Ánh xạ lỗi ngoài dự kiến thành mã `INTERNAL_ERROR` và thông báo an toàn như `Request could not be completed.`. Ở log nội bộ, chỉ ghi những trường đã được phép để phục vụ điều tra; không có nghĩa mọi exception phải bị nuốt và hệ thống vẫn tiếp tục thực hiện giao dịch.

### 5.4. Giới hạn độ dài và dữ liệu động

Mã lỗi và template cố định giúp tránh nội dung quá dài, nhưng trong thực tế vẫn cần kiểm tra:

- **Chiều dài message:** không đưa raw payload hoặc stack vào một trường hiển thị ngắn.
- **Ký tự xuống dòng/điều khiển:** nếu có dữ liệu từ ngoài trong log, phải áp dụng structured logging/escaping thích hợp để tránh log forging/injection.
- **Encoding:** tránh đặt các byte không kiểm chứng trực tiếp thành message Unicode.
- **Phân loại dữ liệu:** PII/secrets phải được xử lý theo chính sách bảo vệ dữ liệu, không chỉ cắt chuỗi bằng `substring`.

**Cắt một message đang chứa secret xuống 200 ký tự không làm nó tự động an toàn.** Cách tốt hơn là **chọn thông tin được phép công khai ngay từ đầu**, thay vì “đổ tất cả vào rồi che đi một phần”.

## 6. Phân biệt `message`, `cause`, `suppressed` và stack trace

### 6.1. Cơ chế `Throwable` hiện hành

Theo Java API, `Throwable` có:

```java
String message = ex.getMessage();
String localized = ex.getLocalizedMessage();
Throwable cause = ex.getCause();
Throwable[] suppressed = ex.getSuppressed();
StackTraceElement[] frames = ex.getStackTrace();
```

Đoạn minh họa giả định một biến `ex` kiểu `Throwable` đã tồn tại. Các thành phần khác nhau:

| Lấy gì? | Thực chất | Rủi ro |
| --- | --- | --- |
| `getMessage()` | Message gắn với throwable hiện tại | Có thể chứa dữ liệu developer đã ghép |
| `getLocalizedMessage()` | Mô tả địa phương hóa, thường mặc định giống message | Không phải bộ lọc thông tin |
| `getCause()` | Exception gốc/tầng dưới | Có thể chứa secret/path/SQL |
| `getSuppressed()` | Exception bị giữ lại khi exception khác được ưu tiên, ví dụ cleanup | Có thể có log/credential từ resource |
| `getStackTrace()` | Frames chứa class/method/file/line | Tiết lộ cấu trúc code |
| `printStackTrace()` | In stack và thông tin cause/suppressed | **Không dùng trong HTTP response** |
| `toString()` | Tên class + localized message nếu có | Không phù hợp để in ra client |

Đừng coi `getLocalizedMessage()` là cách loại bỏ PII: Java không có cơ chế mặc định bảo đảm điều đó.

### 6.2. Bẫy constructor chỉ nhận `cause`

`Throwable(Throwable cause)` tạo message mặc định dựa trên `cause.toString()`. Nếu cause chứa thông tin không muốn lộ, **dù không gọi `cause.getMessage()` trực tiếp**, message của exception bọc ngoài vẫn có thể lộ nội dung từ cause.

Ví dụ phản mẫu:

```java
// Sai nếu underlyingException có message nhạy cảm:
throw new RuntimeException(underlyingException);
```

Nên định nghĩa **message an toàn tường minh** khi wrap:

```java
// Phải bảo đảm không đưa exception này ra phía client hoặc logger không kiểm soát:
throw new RuntimeException("Internal operation failed", underlyingException);
```

Cách thứ hai chỉ làm message **lớp ngoài** an toàn hơn; cause nguyên gốc vẫn nằm bên trong. Khi một root cause có bí mật, giải pháp tốt nhất là **không đưa bí mật vào message ngay từ nơi tạo lỗi**. Nếu thư viện không kiểm soát được, cần thiết kế vùng chẩn đoán có policy; không serialize/log raw tree tùy tiện.

### 6.3. Suppressed exceptions và try-with-resources

Với `try-with-resources`, exception khi đóng resource có thể được thêm vào `getSuppressed()` của exception chính. Vì vậy một công cụ ghi toàn bộ stack trace có thể in cả **lỗi chính lẫn lỗi cleanup**.

Không nên tắt suppressed exceptions hoặc xóa stack trace cho toàn hệ thống chỉ để “giảm thông tin lộ”. Việc đó có thể phá khả năng điều tra. **Giải pháp là kiểm soát ranh giới phản hồi và quyền truy cập log**, đồng thời ngăn secret được đưa vào các message ngay từ đầu.

### 6.4. Không tắt stack trace như một cách “bảo mật”

`Throwable` có constructor đặc biệt cho phép điều khiển suppression và writable stack trace trong subclass phù hợp. Nhưng chọn `writableStackTrace=false` **không làm message/cause tự an toàn** và có thể làm việc truy tìm lỗi khó hơn.

Chỉ cân nhắc tối ưu stack trace đối với một loại lỗi đặc biệt sau khi có số liệu hiệu năng, và vẫn phải tuân thủ quy tắc công khai/riêng tư. Không khuyến nghị vô hiệu stack trace đại trà, cũng không dùng `printStackTrace()` để trả dữ liệu cho người dùng.

## 7. Ví dụ Java 17+ hoàn chỉnh: trả thông báo an toàn nhưng vẫn nhận diện lỗi

Ví dụ minh họa một service tạo đơn hàng:

- Request hợp lệ: không có exception.
- Số lượng sai: ném `AppException` với code/message an toàn.
- Dependency lỗi: wrap một cause có **chuỗi nhạy cảm giả dùng để kiểm thử**; *cố ý cho thấy dữ liệu nguy hiểm có thể nằm trong cause*.
- Lỗi không dự kiến: rơi vào `INTERNAL_ERROR`.
- Tầng response chỉ ánh xạ sang `PublicError`, **không** trả object `Throwable` ra ngoài.
- Tầng audit chỉ in **loại lỗi** và việc có cause hay không, không in message/raw cause/stack.

**Chú ý:** `DUMMY_SECRET_NOT_REAL` là **marker giả, không phải credential thật**; nó chỉ xuất hiện trong chương trình kiểm thử để chứng minh phản hồi không làm lộ. **Không nên tạo và giữ một cause chứa secret thật như trong bài test này ở production**, vì các hệ thống auto-logging/APM có thể tự thu exception chain.

Tạo file **`SafeExceptionDemo.java`**:

```java
public class SafeExceptionDemo {
    enum ErrorCode {
        INVALID_QUANTITY("Quantity must be positive."),
        DEPENDENCY_UNAVAILABLE("Service temporarily unavailable."),
        INTERNAL_ERROR("Request could not be completed.");

        final String publicMessage;

        ErrorCode(String publicMessage) {
            this.publicMessage = publicMessage;
        }
    }

    static final class AppException extends RuntimeException {
        private final ErrorCode code;

        AppException(ErrorCode code) {
            super(code.publicMessage);
            this.code = code;
        }

        AppException(ErrorCode code, Throwable cause) {
            super(code.publicMessage, cause);
            this.code = code;
        }

        ErrorCode code() {
            return code;
        }
    }

    record PublicError(String code, String message, String requestId) {}

    static PublicError toPublicError(RuntimeException failure, String requestId) {
        ErrorCode code = failure instanceof AppException app
                ? app.code() : ErrorCode.INTERNAL_ERROR;
        return new PublicError(code.name(), code.publicMessage, requestId);
    }

    static void createOrder(int quantity, boolean dependencyFails) {
        if (quantity <= 0) {
            throw new AppException(ErrorCode.INVALID_QUANTITY);
        }
        if (dependencyFails) {
            // Deliberately unsafe cause in this TEST ONLY.
            RuntimeException unsafeCause =
                    new IllegalStateException("credential=DUMMY_SECRET_NOT_REAL");
            throw new AppException(ErrorCode.DEPENDENCY_UNAVAILABLE, unsafeCause);
        }
    }

    static void run(String scenario) {
        String requestId = "req-demo-001";
        try {
            switch (scenario) {
                case "valid" -> createOrder(2, false);
                case "invalid" -> createOrder(0, false);
                case "dependency" -> createOrder(2, true);
                case "unknown" -> throw new IllegalStateException(
                        "internal path=/srv/private; credential=DUMMY_SECRET_NOT_REAL");
                default -> throw new IllegalArgumentException("unknown scenario");
            }
            System.out.println(scenario + " client=OK");
        } catch (RuntimeException failure) {
            PublicError response = toPublicError(failure, requestId);
            String publicText = response.code() + " | " + response.message()
                    + " | " + response.requestId();
            if (publicText.contains("DUMMY_SECRET_NOT_REAL")
                    || publicText.contains("/srv/private")) {
                throw new AssertionError("Sensitive data leaked to client");
            }
            System.out.println(scenario + " client=" + publicText);
            // Demonstration of an internal-only audit with no raw messages:
            String causeType = failure.getCause() == null ? "none"
                    : failure.getCause().getClass().getSimpleName();
            System.out.println(scenario + " audit=type:"
                    + failure.getClass().getSimpleName() + ",cause:" + causeType);
        }
    }

    public static void main(String[] args) {
        run("valid");
        run("invalid");
        run("dependency");
        run("unknown");
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 SafeExceptionDemo.java
java SafeExceptionDemo
```

**Stdout chính xác**, đã biên dịch thành Java 17 và chạy trên JDK 24:

```text
valid client=OK
invalid client=INVALID_QUANTITY | Quantity must be positive. | req-demo-001
invalid audit=type:AppException,cause:none
dependency client=DEPENDENCY_UNAVAILABLE | Service temporarily unavailable. | req-demo-001
dependency audit=type:AppException,cause:IllegalStateException
unknown client=INTERNAL_ERROR | Request could not be completed. | req-demo-001
unknown audit=type:IllegalStateException,cause:none
```

### 7.1. Giải thích chính xác

1. **`valid client=OK`:** trường hợp thành công không cần exception.
2. **`invalid`:** chỉ public code `INVALID_QUANTITY` và message đã duyệt được trả; không in raw input.
3. **`dependency`:** exception ngoài giữ một cause; nhưng phản hồi công khai chỉ thấy `DEPENDENCY_UNAVAILABLE`. Đây không phải bằng chứng cause an toàn để log, mà chỉ chứng minh **boundary mapper không lộ cause**.
4. **`unknown`:** `IllegalStateException` ngoài dự kiến bị map thành `INTERNAL_ERROR`, tránh lộ đường dẫn nội bộ/marker.
5. **`audit`:** phần minh họa in exception type và cause type, không in message/stack. Trong sản phẩm, đây phải là hệ thống logging nội bộ có quyền truy cập, retention và cảnh báo phù hợp, không phải thông tin trả trong HTTP response.
6. **Assertion chống lộ:** nếu public string chứa marker giả hoặc path `/srv/private`, ví dụ ném `AssertionError` để phép kiểm thử thất bại.

**Output của lần chạy khác vẫn giống nhau** vì chương trình dùng request ID giả cố định và không chứa thời gian ngẫu nhiên. Trong production, request/correlation ID nên được tạo hoặc chuẩn hóa bởi tầng hạ tầng tin cậy, không lấy nguyên chuỗi tùy ý do client cung cấp.

### 7.2. Những gì ví dụ không tự bảo đảm

Ví dụ chỉ mô phỏng tầng mapping, **không phải một HTTP server**. Nó không cấu hình TLS, authorization, structured logging framework hoặc sanitization trên mọi thư viện.

Lệnh `System.out.println` được dùng để làm bài học dễ kiểm chứng. **Không xem stdout chứa audit records là kênh bảo mật** nếu nó có thể hiển thị ra client/console chia sẻ. Trong production, cần logger được cấu hình rõ ràng, có kiểm soát quyền truy cập và phân loại dữ liệu.

Đặc biệt, nhánh dependency/unknown **cố tình tạo cause message nguy hiểm** để kiểm tra không lộ qua phản hồi. Không tái sử dụng mẫu chứa credential trong exception khi triển khai; nên tránh gắn secret vào message từ gốc.

## 8. Lớp boundary: ánh xạ exception sang API response an toàn

Trong HTTP API, thay vì trả:

```json
{
  "exception": "java.sql.SQLException",
  "message": "password=...; sql=...; host=...",
  "stackTrace": ["com.internal.module.Service.java:123"]
}
```

hãy trả một DTO ổn định được thiết kế riêng, ví dụ:

```json
{
  "code": "DEPENDENCY_UNAVAILABLE",
  "message": "Service temporarily unavailable.",
  "requestId": "req-demo-001"
}
```

**Đoạn JSON đầu là phản ví dụ**, không phải dữ liệu thực cần ghi log. Đoạn thứ hai có thông điệp đã kiểm duyệt và một request ID ví dụ.

Nếu hệ thống áp dụng **Problem Details for HTTP APIs**, chuẩn hiện hành là **RFC 9457** (`application/problem+json`), đã thay thế RFC 7807. Có thể biểu diễn an toàn:

```json
{
  "type": "https://api.example.org/problems/service-unavailable",
  "title": "Service unavailable",
  "status": 503,
  "detail": "Request could not be completed at this time.",
  "instance": "/problems/req-demo-001"
}
```

Đây là **minh họa giao thức**, không phải URI đang hoạt động. Chọn HTTP status, `type`, `detail` và `instance` theo API contract. **Không đưa stack trace, SQL, secrets hoặc cause chain vào Problem Details**: RFC 9457 là định dạng mô tả lỗi cho client, không phải cơ chế chuyển debug data.

### 8.1. Mapping phải nhất quán với HTTP status và quyền

| Loại lỗi | Mã lỗi công khai | HTTP status minh họa | Thông tin công khai |
| --- | --- | --- | --- |
| Số lượng không hợp lệ | `INVALID_QUANTITY` | `400 Bad Request` hoặc `422 Unprocessable Content` tùy contract | Tên field và quy tắc đã công khai |
| Dịch vụ phụ thuộc tạm lỗi | `DEPENDENCY_UNAVAILABLE` | `503 Service Unavailable` khi phù hợp | “Service temporarily unavailable.” |
| Lỗi nội bộ chưa phân loại | `INTERNAL_ERROR` | `500 Internal Server Error` | Thông báo tổng quát và request ID |
| Không có quyền xem tài nguyên | Mã thuộc auth policy | `403` hoặc `404` theo chính sách | Không tiết lộ tài nguyên tồn tại nếu nhạy cảm |
| Không xác minh được chữ ký/token | Mã authentication/authorization phù hợp | Từ chối truy cập | Không bật bypass; không tiết lộ credential |

Các mã HTTP chỉ minh họa. Đừng dùng `500` cho mọi input error nếu hợp đồng API có thể trả lỗi có ích; nhưng cũng không cung cấp thông tin làm lộ trạng thái tài khoản/tài nguyên mà client không được biết.

### 8.2. Không serialize exception object

Một framework có thể tự serialize các getter của object được trả về. **Không trả thẳng `Throwable` hoặc custom exception** rồi hy vọng framework sẽ ẩn `getMessage()`, `getCause()` và `getStackTrace()`.

Nên dùng một DTO **chỉ chứa các trường allowlist**:

```java
record PublicError(String code, String message, String requestId) {}
```

Cấu trúc này là Java record hiện hành (Java 16+), tương thích với ví dụ Java 17+. Nó không chứa reference tới `Throwable`, nên không có đường serialize vô ý toàn bộ exception chain. Tuy nhiên vẫn phải bảo đảm **giá trị chuỗi** được sinh từ nguồn tin cậy/đã kiểm duyệt.

## 9. Logging và chẩn đoán không làm lộ dữ liệu

### 9.1. Tách thông tin người dùng và vận hành

Phản hồi công khai nên ưu tiên:

- `errorCode` hoặc `type` ổn định.
- Thông báo ngắn, giúp người dùng sửa lỗi **nếu được phép tiết lộ**.
- `requestId`/correlation ID ngẫu nhiên hoặc do server chuẩn hóa.
- HTTP status phù hợp với quy tắc xử lý.

Log nội bộ có thể có thêm:

- Service/component, timestamp, environment, event ID.
- Error code/classification và exception **type** đã kiểm soát.
- Operation name/phase (giá trị tĩnh đã định nghĩa).
- Dependency category, retry count, latency, correlation ID.
- Stack trace/cause chain **chỉ khi nội dung đã được xem xét và được phép**.

**Không log bằng mọi giá:** password, access token, session cookie, số định danh nhạy cảm, raw request body/headers và raw exception message không đáng tin.

### 9.2. Cẩn thận với logger tự động in Throwable

Một số logging frameworks có overload nhận `Throwable`; khi truyền exception làm tham số, chúng có thể ghi stack trace và **cả cause chain/suppressed exceptions**:

```java
// Phản ví dụ nếu exception chưa được kiểm duyệt:
logger.log(java.util.logging.Level.SEVERE, "Operation failed", exception);
```

Câu lệnh là snippet giả định `logger` và `exception` đã có. Bản thân overload này **không lỗi thời** và rất hữu ích khi cause đã an toàn. Vấn đề là **nó có thể in dữ liệu nhạy cảm do ứng dụng/thư viện đưa vào exception**.

Cách giảm rủi ro:

1. Hạn chế việc đưa secret vào exception từ nguồn.
2. Dùng error code và metadata đã kiểm duyệt cho telemetry thường kỳ.
3. Chỉ ghi full stack trace ở kênh có quyền/retention phù hợp và khi đã đánh giá nguồn dữ liệu.
4. Cấu hình redaction có kiểm thử, nhưng **đừng dựa duy nhất vào regex** để che mọi secret có thể xuất hiện.
5. Không đặt nội dung raw đầu vào làm message template hoặc structured-log key.
6. Giới hạn tốc độ và dung lượng log để tránh spam/DoS từ client gửi nhiều request sai.

**Đặc biệt:** Nếu một thư viện cấp thấp tạo exception chứa credential, log `ex.getClass().getSimpleName()` **không chứa message gốc**, nhưng không được hiểu rằng mọi cơ chế auto-capture APM đều sẽ bỏ qua message/cause. Cần review cấu hình toàn bộ logging/tracing pipeline.

## 10. Định danh tương quan và dữ liệu an toàn

Dùng request/correlation ID giúp người dùng báo lỗi mà không cần gửi stack trace:

```text
Client: Request failed. Reference: req-demo-001.
Support: Tìm event nội bộ có cùng requestId và errorCode.
```

Quy tắc thực tế:

- ID nên khó đoán nếu dùng để tra cứu dữ liệu nhạy cảm; cần kiểm tra authorization khi cho phép tra cứu incident.
- Không tái sử dụng **session token** làm request ID.
- Nếu nhận `X-Request-ID` từ client, cần validate giới hạn độ dài, ký tự, provenance và chính sách thay thế/chuẩn hóa.
- Không dùng request ID làm bằng chứng người dùng có quyền xem toàn bộ log của trace đó.
- Dùng format nhất quán nhưng không đưa dữ liệu cá nhân hoặc bí mật vào ID.
- Correlation ID là **đầu mối hỗ trợ**, không phải lớp bảo mật thay thế authentication hoặc authorization.

Trong ví dụ, ID cố định chỉ phục vụ stdout tái lập được. Trong dịch vụ thật, một middleware/tracing component đáng tin cậy thường quản lý giá trị này.

## 11. Không biến lỗi thành bypass hoặc kết quả sai

Giới hạn thông tin không có nghĩa **nuốt mọi exception**:

```java
// SAI: Không áp dụng trong xử lý yêu cầu có xác thực bắt buộc.
try {
    verifySignature();
} catch (RuntimeException ex) {
    return true; // Lỗi bị biến thành cho phép.
}
```

Đoạn trên chỉ là phản ví dụ trong một method giả định. Khi không xác minh được chữ ký, cần **từ chối** hoặc báo lỗi theo hợp đồng; không trả thành công chỉ để tránh lộ nội dung exception.

Tương tự:

- Không trả `200 OK` nếu thao tác thất bại.
- Không ghi dữ liệu/commit transaction sau khi nhận lỗi không cho phép tiếp tục.
- Không retry vô hạn một lỗi với side effect không idempotent.
- Không dùng `catch (Throwable)` để nuốt mọi lỗi JVM, ví dụ `OutOfMemoryError` hoặc `StackOverflowError`. Các lỗi nghiêm trọng cần chiến lược phục hồi/giám sát riêng.
- Không catch quá rộng rồi che mất lý do điều tra; vẫn ghi metadata an toàn ở kênh nội bộ.
- Khi dùng `try-with-resources`, vẫn phải cleanup resource đúng cách dù response công khai được làm gọn.

**An toàn thông tin và tính đúng đắn của hệ thống phải đi cùng nhau**: response ngắn không thể bù cho việc xác thực sai hoặc ứng dụng tiếp tục khi trạng thái không còn tin cậy.

## 12. Kiểm thử tự động các điểm rò rỉ

Một bộ test chất lượng nên kiểm tra cả **phản hồi**, **log/telemetry** và **cấu hình framework**.

| Ca test | Dữ kiện | Điều kiện PASS |
| --- | --- | --- |
| Input sai | `quantity <= 0` | Trả `INVALID_QUANTITY`, không echo raw request |
| Dependency fail | Lỗi adapter với cause nội bộ | Trả code/message an toàn, không lộ cause |
| Unknown runtime exception | `IllegalStateException` | Map `INTERNAL_ERROR`, status thích hợp |
| Cause chứa marker giả | `DUMMY_SECRET_NOT_REAL` | Marker không xuất hiện trong JSON/HTML response |
| Suppressed chứa marker giả | Resource cleanup exception | Không xuất hiện trong phản hồi và log công khai |
| Stack trace | Ném lỗi qua class nội bộ | Không xuất hiện class/method/file/line trong client payload |
| SQL/connection detail | Driver exception giả lập | Không lộ URL/password/query params |
| PII | Raw user fields | Không lộ email/số điện thoại/tài khoản không được phép |
| Error mapping | Unknown error code | Fallback an toàn, không chuyển `getMessage()` ra client |
| Request ID | Header dài, ký tự xuống dòng | ID được chuẩn hóa/tạo lại; không log injection |
| User enumeration | Tài khoản tồn tại vs không tồn tại | Hành vi/response không tiết lộ trạng thái nhạy cảm |
| Auth failure | Verify lỗi hoặc exception | Từ chối, không bypass |
| Serialization | Framework serialize Error DTO | Không có `cause`, `stackTrace`, `suppressed` |
| Production diagnostics | Tracing/APM bật | Không tự thu raw exception chứa dữ liệu nhạy cảm |

**Đừng chỉ assert `getMessage()` của custom exception an toàn.** Test HTTP response thực tế và logging/tracing pipeline, bởi một serializer có thể vô tình duyệt `cause` hoặc stack trace mặc dù error mapper đã được viết đúng.

### 12.1. Ví dụ assertion bảo mật

Trong chương trình phần 7:

```java
if (publicText.contains("DUMMY_SECRET_NOT_REAL")
        || publicText.contains("/srv/private")) {
    throw new AssertionError("Sensitive data leaked to client");
}
```

Đây là phép kiểm tra cơ bản, không phải hệ thống redaction hoàn chỉnh. Trong automated tests thực tế, cần thêm các pattern nhạy cảm, kiểm tra headers, JSON fields, HTML error pages, tracing spans và log appenders. Khi tích hợp framework, cần test cả **error handler mặc định** trong điều kiện production, không chỉ một `toPublicError()` thuần Java.

### 12.2. Các nguyên tắc thiết kế test

- Dùng **dữ liệu bí mật giả** để test, không dùng credentials thật.
- Assert mã lỗi và status chính xác, không chỉ “response không chứa stack”.
- Assert mọi trường public đến từ allowlist, không từ `Throwable.toString()`.
- Thử nhiều lớp nested causes và suppressed exceptions.
- Thử dữ liệu có newline, Unicode và chuỗi rất dài để phát hiện log injection.
- Kiểm tra cả client không được cấp quyền và client có quyền khác nhau.
- Thử tình huống framework tự bật debug mode trong cấu hình kiểm thử tương đương production.
- Không trộn audit event an toàn và raw debug logs vào một kênh mà client có thể đọc.

## 13. Ranh giới giữa “quá ít” và “quá nhiều” thông tin

Một lỗi **quá ít thông tin** gây khó dùng: `"Something went wrong"` cho mọi tình huống input thông thường không giúp người dùng sửa request. Nhưng lỗi **quá nhiều thông tin** như raw SQL/stack/credential lại tạo rủi ro.

Cách cân bằng:

| Loại lỗi | Thông báo nên công khai | Không nên công khai |
| --- | --- | --- |
| Validation | Tên field trong allowlist + điều kiện hợp lệ | Toàn bộ giá trị nhạy cảm người dùng nhập |
| Resource missing | Mô tả phù hợp authorization policy | Xác nhận tồn tại của dữ liệu tenant khác |
| Duplicate request | Mã lỗi/retry guidance đã duyệt | Nội dung giao dịch hoặc ID nội bộ không được phép |
| Database failure | `"Service temporarily unavailable."` | SQL, DB username/password, hostname, schema |
| Unexpected exception | `"Request could not be completed."` | Class name, stack trace, line number, path |
| Rate limit | Trạng thái/điều kiện retry được phép | Chi tiết thuật toán chống lạm dụng cần giữ kín |
| Authentication failure | Thông báo thống nhất theo policy | Chi tiết tài khoản/token/khóa không hợp lệ |

Với lỗi dự kiến từ input, có thể cung cấp **chi tiết hữu ích** nếu dữ liệu đó được phép xuất hiện. Ví dụ `"quantity must be between 1 and 10"` là một quy tắc validation tĩnh. Còn `"user john@example.net is blocked in tenant X"` có thể vô tình tiết lộ thông tin không cần thiết.

### 13.1. Quốc tế hóa thông báo

Nếu ứng dụng đa ngôn ngữ, hãy dùng **error code hoặc message key** ổn định để tra các bản dịch đã được duyệt. Đừng coi `getLocalizedMessage()` trên một exception đến từ database/provider là chuỗi “đã được chuẩn hóa để công khai”. Việc dịch phải không được biến một string nội bộ thành nội dung gửi client.

## 14. Sai lầm thường gặp

1. **Ghép raw input vào `new IllegalArgumentException(...)`:** có thể lộ token/PII qua logs và response.
2. **Chỉ đổi exception message bên ngoài, giữ raw cause và log toàn bộ:** cause vẫn có thể lộ secret.
3. **Dùng `new RuntimeException(cause)` rồi công khai `getMessage()`:** message có thể dựa trên `cause.toString()`.
4. **Trả `ex.toString()` cho client:** lộ tên class và message.
5. **Trả `printStackTrace()`/stackTrace ra HTML/JSON:** lộ thông tin triển khai.
6. **Serialize trực tiếp custom exception:** serializer có thể duyệt `cause`, `suppressed`, `stackTrace`.
7. **Dùng `getLocalizedMessage()` như bộ lọc bí mật:** nó không có hợp đồng sanitization.
8. **Cắt chuỗi lỗi nhạy cảm để coi là an toàn:** phần đầu vẫn có thể chứa secret.
9. **Log mọi exception object ở mức INFO/WARN cho request không tin cậy:** tạo kho dữ liệu nhạy cảm và tốn tài nguyên.
10. **Dùng regex redaction mà không kiểm thử:** bỏ sót biến thể token, encoding hoặc nested structures.
11. **Đặt request ID bằng raw input không kiểm chứng:** dễ gây log injection hoặc lộ dữ liệu.
12. **Hiển thị nội dung lỗi framework mặc định trên production:** có thể lộ stack/framework versions.
13. **Dùng thông báo khác nhau làm lộ user/resource tồn tại:** nguy cơ enumeration.
14. **Nuốt exception rồi trả thành công:** phá tính đúng đắn, có thể bypass bảo mật.
15. **Tắt stack trace toàn hệ thống để tránh rò rỉ:** làm giảm khả năng chẩn đoán mà không xử lý nguyên nhân.
16. **Gửi toàn bộ lỗi vào APM ngoài mà không kiểm tra chính sách dữ liệu:** có thể chuyển secret sang hệ thống khác.
17. **Không kiểm tra suppressed exceptions:** đường cleanup có thể làm lộ thông tin.
18. **Bắt `Throwable` bừa bãi:** có thể che giấu sự cố nghiêm trọng của JVM.
19. **Dùng HTTP 200 cho lỗi thật:** client có thể hiểu sai trạng thái.
20. **Thiếu correlation ID:** người dùng buộc phải gửi stack/log thô để được hỗ trợ, tăng rủi ro lộ thông tin.

## 15. Checklist trước khi triển khai

- [ ] Custom exception dùng **error code** và thông báo đã duyệt, không ghép token/PII/raw payload?
- [ ] Các constructor exception nhận `cause` chỉ được dùng khi **cause chain có chính sách kiểm soát**?
- [ ] Không sử dụng `new RuntimeException(cause)` như phản hồi công khai?
- [ ] Response mapper chỉ tạo **DTO allowlist**, không serialize `Throwable`?
- [ ] Lỗi không dự kiến được ánh xạ sang message tổng quát, có status phù hợp?
- [ ] Validation errors cung cấp thông tin sửa lỗi vừa đủ mà không echo dữ liệu nhạy cảm?
- [ ] `getMessage()`, `getLocalizedMessage()`, `toString()`, `getCause()`, `getSuppressed()` và stack trace được phân loại đúng?
- [ ] Log/tracing/APM không tự lưu thông tin nhạy cảm hoặc chuyển tới kênh không được phép?
- [ ] Request/correlation ID không chứa token/PII và được xác thực/chuẩn hóa nếu đến từ client?
- [ ] Các nhánh lỗi xác thực/phân quyền đều **fail closed**?
- [ ] Cleanup resource và trạng thái transaction vẫn đúng khi exception xảy ra?
- [ ] Có kiểm thử response, headers, logs, error pages và serialization trong cấu hình production?
- [ ] Có test nested causes, suppressed, SQL message, user enumeration và Unicode/control chars?
- [ ] Mức log, quyền truy cập, retention và alert được vận hành theo chính sách?
- [ ] Không coi việc tắt stack trace hoặc che message đơn thuần là thay thế cho việc kiểm soát dữ liệu?

**Kết luận:** Giới hạn thông tin trong exception do chương trình tự tạo bắt đầu **ngay tại chỗ ném lỗi**: dùng mã lỗi ổn định, thông báo public cố định/được kiểm duyệt, không đưa raw input hoặc secrets vào message. Ở ranh giới API, **chuyển `Throwable` thành DTO có các trường cho phép**, không trả cause/stack; ở tầng vận hành, giữ thông tin chẩn đoán vừa đủ và có kiểm soát. Hãy nhớ **message an toàn không tự làm cause/suppressed/logging an toàn**. Đây là cách xử lý exception đúng và còn áp dụng trong Java hiện đại.

## 16. Tài liệu chính thức và chuẩn hiện hành

- [Oracle Java SE 26 — Throwable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html): `getMessage()`, `getCause()`, `getSuppressed()`, `getStackTrace()`, `printStackTrace()`, constructors và exception chaining.
- [Oracle Java SE 26 — RuntimeException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/RuntimeException.html): unchecked exception và constructors.
- [Oracle Java SE 26 — try-with-resources / AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): quản lý resource, suppressed exceptions trong cleanup.
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): không đưa stack trace và chi tiết backend ra error response.
- [OWASP Developer Guide — Handle Errors and Exceptions](https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/): xử lý tập trung, phản hồi không lộ dữ liệu nhạy cảm, audit an toàn, deny by default.
- [MITRE CWE-209 — Generation of Error Message Containing Sensitive Information](https://cwe.mitre.org/data/definitions/209.html): mô tả lỗi thông tin và cách giảm thiểu rò rỉ.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng `application/problem+json` hiện hành, thay thế RFC 7807; trường `detail` dành cho client, không dùng để debug internals.

Bài học chỉ sử dụng cơ chế exception và tiêu chuẩn xử lý lỗi còn áp dụng hiện nay, không dùng những cách logging/exception đã trở thành legacy hoặc không an toàn.