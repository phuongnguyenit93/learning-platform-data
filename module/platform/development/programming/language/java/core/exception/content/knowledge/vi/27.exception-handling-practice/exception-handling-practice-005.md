# Tạo ngoại lệ nghiệp vụ có `cause` và dữ liệu ngữ cảnh trong Java

Khi tầng lưu trữ ném `IOException`, tầng nghiệp vụ có thể cần thông báo cho caller rằng thao tác **“không thể tải hồ sơ”** đã thất bại. Nếu chỉ ném `new RuntimeException("lỗi")`, người đọc mất nguyên nhân kỹ thuật và khó xác định request hoặc đối tượng liên quan. Nếu chỉ truyền nguyên `IOException`, API nghiệp vụ lại buộc caller hiểu chi tiết của kho lưu trữ.

Giải pháp là thiết kế **ngoại lệ nghiệp vụ (business/domain exception)** có hợp đồng rõ ràng: một **mã lỗi ổn định**, một thông điệp mô tả, một **`cause` giữ nguyên lỗi gốc** khi đang bọc lỗi, và **dữ liệu ngữ cảnh** có chọn lọc để hỗ trợ chẩn đoán. Bài thực hành thuộc **Java Core – Exception / Thực hành**, dùng cú pháp Java 17+. Các chương trình độc lập có lệnh `javac`/`java` và kết quả xác định; các ví dụ tích hợp với JUnit/logger sẽ được ghi rõ.

## 1. Vấn đề: lỗi kỹ thuật và lỗi nghiệp vụ không cùng mức trừu tượng

Một luồng xử lý thường có dạng:

```text
HTTP/CLI/Job boundary
       |
       v
ProfileService.loadProfile("P-17")
       |
       v
ProfileRepository.read("P-17")
       |
       +-- IOException("storage offline")
               |
               v
Service thêm ngữ cảnh nghiệp vụ:
    BusinessException(
      code=PROFILE_UNAVAILABLE,
      message="Không tải được hồ sơ",
      cause=<IOException gốc>,
      context={operation=profile.load, profileId=P-17}
    )
               |
               v
Boundary phân loại, ghi log kèm Throwable,
trả mã lỗi công khai hoặc đánh dấu job thất bại
```

Ở repository, `IOException` cho biết **cách phụ thuộc kỹ thuật đã lỗi**. Ở service, `PROFILE_UNAVAILABLE` cho biết **thao tác nghiệp vụ nào không hoàn tất**. Boundary có thể quyết định trả response, hiển thị thông báo, retry hoặc dừng job mà không phụ thuộc toàn bộ chi tiết implementation của repository.

**Không tạo một wrapper nghiệp vụ cho mọi exception một cách mù quáng.** Nếu lỗi là bug (`NullPointerException` do mã sai), bọc thành “không tìm thấy hồ sơ” có thể che nguyên nhân và báo sai loại sự cố. Chỉ chuyển loại exception khi tầng hiện tại có đủ thông tin để xác lập một ý nghĩa nghiệp vụ chính xác.

## 2. Bốn phần quan trọng của ngoại lệ nghiệp vụ

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Loại exception** | Đánh dấu họ lỗi thuộc miền nghiệp vụ | `BusinessException extends RuntimeException` |
| **Error code** | Mã ổn định cho logic xử lý, metric, API contract | `PROFILE_UNAVAILABLE` |
| **Message** | Diễn giải thất bại để đọc log; có thể thay đổi theo ngôn ngữ | `"Không tải được hồ sơ"` |
| **Cause** | Giữ `Throwable` gốc để bảo toàn stack, loại và thông tin lỗi nguồn | `IOException("storage offline")` |
| **Context** | Trường được chọn, có thể xử lý bằng máy | `operation`, `profileId`, `requestId` |

Mã lỗi nên có ý nghĩa **ổn định hơn câu chữ**. Ví dụ controller có thể map `PROFILE_UNAVAILABLE` sang một kết quả API phù hợp, còn message nội bộ có thể được chỉnh sửa mà không phá contract phía client. Context cho phép tìm đúng sự kiện trong log và đối chiếu request, miễn là chỉ chứa dữ liệu được phép ghi.

Một số nguyên tắc thiết kế:

1. **Giữ cause**, đừng chỉ chép `cause.getMessage()` vào chuỗi mới.
2. **Dữ liệu ngữ cảnh là immutable theo góc nhìn người dùng**, tránh bị thay đổi sau khi exception được tạo.
3. **Không nhét thông tin nhạy cảm** như password, token, cookie, key, nội dung cá nhân hoặc payload thô vào message/context.
4. **Không biến exception thành vật chứa mọi trạng thái**: chỉ giữ những trường cần để quyết định lỗi hoặc điều tra.
5. **Không trả nguyên stack trace cho người dùng cuối**. Mã lỗi công khai và thông báo an toàn là một hợp đồng khác với thông tin kỹ thuật nội bộ.
6. Một exception được ném chỉ khi có thất bại theo hợp đồng. Đừng tạo Throwable trên happy path chỉ để dự phòng.

## 3. Chọn `RuntimeException` hay checked `Exception`?

Có hai cách hợp lệ, phụ thuộc thiết kế API:

- `extends RuntimeException`: caller không bị compiler bắt buộc `catch`/`throws`; phù hợp nếu đây là thất bại nghiệp vụ được xử lý tại ranh giới ứng dụng hoặc phần lớn caller không thể phục hồi ngay.
- `extends Exception`: caller phải catch hoặc khai báo; phù hợp nếu API **chủ ý yêu cầu** người gọi xét khả năng thất bại và chọn đường phục hồi.

Không có nguyên tắc rằng *mọi business exception đều phải unchecked* hoặc *mọi business exception đều phải checked*. Quan trọng là API diễn đạt được **khả năng phục hồi, tính dự kiến và trách nhiệm xử lý**.

Ví dụ class unchecked tối thiểu:

```java
public final class ProfileUnavailableException
        extends RuntimeException {
    public ProfileUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **một định nghĩa class độc lập có thể lưu trong** `ProfileUnavailableException.java`. Tuy nhiên nó chỉ giữ message/cause; muốn phân loại nhiều tình huống và đính kèm context, ta sẽ làm đầy đủ hơn ở ví dụ tiếp theo.

Nếu một lỗi **đã là domain exception có mã/context đúng**, tầng bên trên có thể truyền tiếp thay vì bọc thêm loại tương tự. Bọc chồng không thêm ngữ nghĩa tạo stack trace dài, dễ tạo nhiều lớp `Caused by` không cần thiết.

## 4. Bài thực hành chính: exception có mã lỗi, `cause` và context bất biến

Tạo tệp `BusinessExceptionDemo.java`:

```java
import java.io.IOException;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class BusinessExceptionDemo {
    enum ErrorCode {
        PROFILE_UNAVAILABLE
    }

    static final class BusinessException extends RuntimeException {
        private final ErrorCode code;
        private final Map<String, String> context;

        BusinessException(
                ErrorCode code,
                String message,
                Throwable cause,
                Map<String, String> context) {
            super(message, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.context = Map.copyOf(
                    Objects.requireNonNull(context, "context"));
        }

        ErrorCode code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    @FunctionalInterface
    interface ProfileSource {
        String read(String profileId) throws IOException;
    }

    static String loadProfile(
            String profileId, ProfileSource source) {
        Objects.requireNonNull(profileId, "profileId");
        Objects.requireNonNull(source, "source");

        try {
            return source.read(profileId);
        } catch (IOException cause) {
            throw new BusinessException(
                    ErrorCode.PROFILE_UNAVAILABLE,
                    "Không tải được hồ sơ",
                    cause,
                    Map.of(
                            "operation", "profile.load",
                            "profileId", profileId));
        }
    }

    public static void main(String[] args) {
        String value = loadProfile("P-17", id -> "Lan");
        System.out.println("success = " + value);

        try {
            loadProfile("P-17", id -> {
                throw new IOException("storage offline");
            });
        } catch (BusinessException error) {
            System.out.println("code = " + error.code());
            System.out.println("message = " + error.getMessage());
            System.out.println("cause = "
                    + error.getCause().getClass().getSimpleName()
                    + ": " + error.getCause().getMessage());
            System.out.println("context = "
                    + new TreeMap<>(error.context()));
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac BusinessExceptionDemo.java
java BusinessExceptionDemo
```

Đầu ra chính xác:

```text
success = Lan
code = PROFILE_UNAVAILABLE
message = Không tải được hồ sơ
cause = IOException: storage offline
context = {operation=profile.load, profileId=P-17}
```

### Giải thích từng thành phần

- `ErrorCode` là enum. `PROFILE_UNAVAILABLE` dùng để phân loại lỗi, không phụ thuộc nội dung message tiếng Việt.
- `BusinessException extends RuntimeException` giữ lại toàn bộ hành vi `Throwable`, gồm stack trace, `getCause()` và `getSuppressed()`.
- `super(message, cause)` là dòng quan trọng nhất cho **exception chaining**. Nó nối lỗi nghiệp vụ với `IOException` gốc.
- `context` là `Map<String,String>`. `Map.copyOf(...)` tạo một map không cho sửa qua API thông thường; ví dụ chỉ dùng các giá trị `String`, vốn immutable.
- `Objects.requireNonNull(...)` từ chối `code` hoặc map context bị null ngay khi khởi tạo; `Map.copyOf` không chấp nhận key/value null.
- `ProfileSource` đóng vai trò dependency có thể thay bằng fake lambda. Không cần database hay mạng để tái hiện đường thành công/thất bại.
- Tầng service mới biết nghiệp vụ `"profile.load"` và `"P-17"`, nên nó thêm đúng ngữ cảnh tại đây.
- `new TreeMap<>(error.context())` dùng **riêng cho việc in ví dụ** nhằm có thứ tự khóa xác định. `Map.copyOf` không cam kết iteration order phù hợp để hard-code output.

Ở đường thành công, không có business exception nào được tạo. Ở đường lỗi, caller nhận thông tin nghiệp vụ, còn `getCause()` vẫn giữ lỗi kỹ thuật. Khi logger in `Throwable` đầy đủ, stack trace có thể hiển thị nhánh `Caused by:` của `IOException`.

### Vì sao không đưa map trực tiếp vào constructor rồi giữ nguyên tham chiếu?

Nếu chỉ làm:

```java
this.context = context;
```

caller còn giữ `HashMap` gốc có thể thay các trường sau khi exception được tạo. Khi đến lúc ghi log, context đã không còn phản ánh tình huống thất bại ban đầu. Với `Map.copyOf`, các cặp key/value được sao chép sang collection không sửa qua map trả về.

Lưu ý: **immutable map không đồng nghĩa deep immutable nếu value là object mutable**. Dùng `Map<String,String>` hoặc những value bất biến có kích thước giới hạn làm việc kiểm soát đơn giản hơn `Map<String,Object>` chứa entity, session, request body hoặc các object có trạng thái có thể đổi.

## 5. Kiểm tra tính bất biến và identity của cause

Một business exception tốt có thể được sử dụng qua nhiều tầng sau khi khởi tạo. Các tầng ấy phải nhìn thấy cùng mã lỗi, cùng ngữ cảnh đã chốt và cùng root cause đã được truyền vào.

Tệp `BusinessExceptionInvariantDemo.java`:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class BusinessExceptionInvariantDemo {
    static class BusinessException extends RuntimeException {
        private final String code;
        private final Map<String, String> context;

        BusinessException(
                String code, String message,
                Throwable cause, Map<String, String> context) {
            super(message, cause);
            this.code = code;
            this.context = Map.copyOf(context);
        }

        String code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("disk error");

        Map<String, String> input = new HashMap<>();
        input.put("operation", "report.export");

        BusinessException error = new BusinessException(
                "REPORT_UNAVAILABLE",
                "Không xuất được báo cáo",
                original,
                input);

        input.put("operation", "changed later");

        System.out.println("code = " + error.code());
        System.out.println("cause identity = "
                + (error.getCause() == original));
        System.out.println("snapshot = "
                + error.context().get("operation"));

        try {
            error.context().put("operation", "tampered");
        } catch (UnsupportedOperationException expected) {
            System.out.println("context modifiable = false");
        }
    }
}
```

Lệnh:

```bash
javac BusinessExceptionInvariantDemo.java
java BusinessExceptionInvariantDemo
```

Kết quả:

```text
code = REPORT_UNAVAILABLE
cause identity = true
snapshot = report.export
context modifiable = false
```

Ý nghĩa:

1. Sau khi tạo exception, việc thay đổi `input` không thay đổi context được lưu.
2. `error.getCause() == original` chứng minh **chính đối tượng nguyên nhân** đã được giữ, không phải tạo một exception mới cùng message.
3. Caller không thể sửa map trả về bằng `put`.
4. Message và mã lỗi cung cấp hai tầng contract khác nhau: diễn giải và phân loại.

Chương trình minh họa dùng constructor tối giản chưa ràng buộc `code != null`. Trong thiết kế production nên thêm kiểm tra cho các tham số bắt buộc và có test tương ứng. Điều này không thay đổi ý nghĩa bài thực hành về snapshot context/cause.

## 6. Trường dữ liệu ngữ cảnh nào là hữu ích?

**Context không phải bản sao toàn bộ request.** Nó nên trả lời một số câu hỏi chẩn đoán thiết yếu:

- **Đang làm gì?** `operation=invoice.export`, `resource=profile`.
- **Liên quan đối tượng nào?** `profileId=P-17`, `orderId=O-42`, với ID đã qua kiểm soát.
- **Có thể nối log với nhau không?** `requestId=R-103`, `traceId` được hệ thống sinh/quản lý.
- **Thất bại ở pha nào?** `phase=repository.read`, `attempt=3`, `dependency=profile-store`.
- **Có error code nào để gom nhóm?** `PROFILE_UNAVAILABLE` nên là trường riêng, không cần nhét vào mỗi message.

Thông tin **không nên** có trong exception context hoặc message: password, JWT, cookie, authorization header, API key, credit card, request body thô, thông tin y tế/cá nhân nhạy cảm, hoặc toàn bộ entity có `toString()` không kiểm soát.

Chỉ sử dụng một danh sách trường **được cho phép** (allowlist). Kể cả ID cũng nên bị giới hạn độ dài và tuân theo chính sách ghi nhận dữ liệu. Dữ liệu từ client chưa được xác thực không nên được đưa thẳng vào log như một ID đáng tin.

### Những lựa chọn biểu diễn

| Cách biểu diễn | Ưu điểm | Điểm cần lưu ý |
|---|---|---|
| `Map<String,String>` | Mở rộng thuận tiện, dùng tốt với structured logging | Phải quản lý key, giá trị, kích thước và tránh key viết sai |
| Field rõ ràng như `orderId`, `operation` | Compiler giúp kiểm soát kiểu và sự bắt buộc | Tăng số constructor/kiểu khi nhiều nhóm lỗi |
| `record ErrorContext(...)` | Immutable theo cấu trúc Java 17, biểu đạt schema | Cần xác định trường nào chung cho mọi lỗi |
| Một chuỗi `details` | Đơn giản ban đầu | Khó tìm kiếm/phân loại và dễ trộn dữ liệu nhạy cảm |
| `Map<String,Object>` tùy ý | Linh hoạt | Khó bảo đảm deep immutability và an toàn serialization |

Nếu một domain có vài loại lỗi chính với trường cố định, một class/record context **mạnh kiểu** có thể tốt hơn map. Nếu cần hệ thống lỗi thống nhất qua nhiều operation, map có allowlist/validation cũng có giá trị.

### Cách giới hạn context trước khi tạo exception

Ví dụ **mảnh mã minh họa**:

```java
static String safeId(String raw) {
    if (raw == null || !raw.matches("[A-Za-z0-9_-]{1,32}")) {
        return "unavailable";
    }
    return raw;
}
```

Phương thức trên minh họa cách hạn chế độ dài và ký tự của **ID kỹ thuật**. Không dùng regex này cho tên người hoặc dữ liệu quốc tế hóa nếu mục đích khác. Trên đường lỗi, tránh tính ngữ cảnh bằng một cuộc gọi DB/HTTP mới chỉ để làm message đẹp hơn; thao tác phụ đó có thể cũng lỗi và che nguyên nhân ban đầu.

## 7. `cause` khác dữ liệu ngữ cảnh

`cause` là một **đối tượng Throwable**, có kiểu, message và stack riêng. Context là **metadata phục vụ hiểu thao tác**, không phải nguyên nhân.

Ví dụ:

```text
BusinessException
  code    = PROFILE_UNAVAILABLE
  message = Không tải được hồ sơ
  context = {profileId=P-17, operation=profile.load}
  cause   = IOException("storage offline")
```

Cần tránh hai sai lầm:

1. Chỉ lưu `context.put("rootCause", e.toString())` mà không truyền `e` vào constructor. Điều này đánh mất type/stack và chuỗi `Caused by` chuẩn.
2. Chỉ truyền cause, không thêm ngữ cảnh ở ranh giới biết operation. Caller sau đó có thể biết `"connection refused"` nhưng không biết nó thuộc thao tác nghiệp vụ nào.

**Không cần bọc nhiều lần nếu ngữ cảnh đã đủ.** Ngoại lệ nghiệp vụ có thể đi qua controller, job runner hoặc mapper; những tầng này thường đọc code/context, không nhất thiết tạo wrapper mới.

Nếu `Throwable` bắt nguồn từ một callback bất đồng bộ, có thể gặp `CompletionException` hoặc `ExecutionException` ở tầng quan sát. Hãy phân loại đúng **lớp lỗi quan sát** và giữ cause thực sự; không tạo wrapper chỉ vì nhìn thấy tên `CompletionException`.

## 8. Checked business exception: lựa chọn khác cho hợp đồng công khai

Một tác vụ xuất báo cáo có thể công khai rằng caller **phải xét đến thất bại nghiệp vụ**. Khi đó dùng `extends Exception` là một lựa chọn có cơ sở.

Tệp `CheckedBusinessExceptionDemo.java`:

```java
import java.io.IOException;

public class CheckedBusinessExceptionDemo {
    static final class ExportException extends Exception {
        private final String code;
        private final String reportId;

        ExportException(
                String code, String reportId,
                String message, Throwable cause) {
            super(message, cause);
            this.code = code;
            this.reportId = reportId;
        }

        String code() {
            return code;
        }

        String reportId() {
            return reportId;
        }
    }

    @FunctionalInterface
    interface ReportSource {
        String read() throws IOException;
    }

    static String export(
            String reportId, ReportSource source)
            throws ExportException {
        try {
            return source.read();
        } catch (IOException cause) {
            throw new ExportException(
                    "REPORT_SOURCE_FAILED",
                    reportId,
                    "Không xuất được báo cáo",
                    cause);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("success = "
                    + export("R-7", () -> "ready"));

            export("R-7", () -> {
                throw new IOException("source disconnected");
            });
        } catch (ExportException error) {
            System.out.println("code = " + error.code());
            System.out.println("reportId = " + error.reportId());
            System.out.println("cause = "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac CheckedBusinessExceptionDemo.java
java CheckedBusinessExceptionDemo
```

Kết quả:

```text
success = ready
code = REPORT_SOURCE_FAILED
reportId = R-7
cause = IOException
```

`export(...)` khai báo `throws ExportException`. Caller phải catch hoặc propagate checked exception này. `reportId` được biểu diễn là field cụ thể: nếu đây là một trường domain bắt buộc, field rõ ràng giúp API có hợp đồng mạnh hơn một map key tùy ý.

Ví dụ cố tình không có các dependency ngoài JDK. Trong hệ thống thật, cân nhắc constructor kiểm tra `code`/`reportId` null, chính sách giới hạn độ dài ID và bảo vệ thông tin chẩn đoán.

## 9. Có cần constructor không nhận `cause`?

Không phải mọi business exception đều do một exception khác gây ra. Validation như “số lượng phải dương” có thể được phát hiện **trực tiếp**:

```java
if (quantity <= 0) {
    throw new BusinessException(
            ErrorCode.INVALID_QUANTITY,
            "Số lượng phải lớn hơn 0",
            null,
            Map.of("field", "quantity"));
}
```

Đây là **mảnh mã minh họa** dùng cấu trúc class/enum tương tự ví dụ chính; `INVALID_QUANTITY` phải được thêm vào enum tương ứng. Ở trường hợp này **không có Throwable nguồn**, nên `cause == null` là hợp lý. Đừng tạo một `IllegalArgumentException` giả chỉ để constructor luôn có cause.

Nếu class phục vụ cả lỗi trực tiếp lẫn lỗi bọc, có thể cung cấp hai constructor:

```java
BusinessException(
        ErrorCode code, String message,
        Map<String, String> context) {
    this(code, message, null, context);
}

BusinessException(
        ErrorCode code, String message,
        Throwable cause, Map<String, String> context) {
    super(message, cause);
    this.code = Objects.requireNonNull(code);
    this.context = Map.copyOf(context);
}
```

Đây là **các constructor minh họa nằm bên trong class `BusinessException`** với các field `code`, `context`; cần imports `Map`, `Objects`. Chúng không tạo một class độc lập khi chỉ copy hai đoạn.

Các constructor nên có thứ tự tham số thống nhất và được tài liệu hóa; API có quá nhiều tham số giống kiểu `String` rất dễ bị truyền nhầm vị trí. Nếu context nhiều trường, cân nhắc dùng đối tượng `ErrorContext` riêng hoặc factory có tên rõ ràng.

## 10. Đừng để ngoại lệ nghiệp vụ phụ thuộc vào logging framework

Business exception nên là **dữ liệu về lỗi và cơ chế truyền lỗi**, không phải nơi trực tiếp quyết định ghi log, trả HTTP hay retry.

Tránh:

```java
BusinessException(...) {
    logger.error("...", cause);
    // rồi caller phía ngoài lại log thêm cùng lỗi
}
```

Đây là ý tưởng **không khuyến nghị**. Constructor tự log có thể tạo một bản `ERROR` ngay cả khi caller sẽ phục hồi; cũng khiến test và class domain phụ thuộc hạ tầng logging.

Thay vào đó:

```text
Repository: ném lỗi kỹ thuật thích hợp
Service: bổ sung ngữ cảnh/cause nghiệp vụ nếu cần
Controller/Job boundary: quyết định xử lý và log theo một chính sách
Error mapper: tạo response công khai an toàn
```

Nếu lỗi được phục hồi ở service (ví dụ fallback), service có thể báo metric hoặc event phù hợp. Nếu lỗi không được phục hồi và đi tới boundary cuối, một log có đầy đủ Throwable/cause/context thường giá trị hơn nhiều log giống nhau ở từng `catch`.

Một ngoại lệ domain cũng không nên tự mở kết nối mạng, truy vấn kho dữ liệu hoặc làm I/O khi được tạo. Điều đó có thể làm đường xử lý lỗi chậm hơn hoặc phát sinh ngoại lệ mới che lỗi gốc.

## 11. Khi cleanup thất bại: giữ `Suppressed` cùng cause

Một lỗi thực tế có thể chứa **nhiều sự cố**:

1. Thân xử lý ném `IOException("write failed")`.
2. `close()` cũng ném `IOException("close failed")`.
3. Service bọc lỗi chính thành business exception.

Nếu sử dụng `try-with-resources`, lỗi close thường được lưu **ở `getSuppressed()` của lỗi chính**, không tự chuyển thành `getCause()` của business exception. Khi bọc, điều quan trọng là **giữ nguyên Throwable nguồn**, bởi nó chứa cả thông tin suppressed.

Tệp `BusinessExceptionSuppressedDemo.java`:

```java
import java.io.IOException;

public class BusinessExceptionSuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static final class ExportException extends RuntimeException {
        ExportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void writeReport() throws IOException {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("write failed");
        }
    }

    static void exportReport() {
        try {
            writeReport();
        } catch (IOException cause) {
            throw new ExportException(
                    "Không thể ghi báo cáo", cause);
        }
    }

    public static void main(String[] args) {
        try {
            exportReport();
        } catch (ExportException error) {
            Throwable root = error.getCause();
            System.out.println("outer = "
                    + error.getClass().getSimpleName());
            System.out.println("cause = " + root.getMessage());
            System.out.println("suppressed count = "
                    + root.getSuppressed().length);
            System.out.println("suppressed = "
                    + root.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac BusinessExceptionSuppressedDemo.java
java BusinessExceptionSuppressedDemo
```

Đầu ra:

```text
outer = ExportException
cause = write failed
suppressed count = 1
suppressed = close failed
```

`BusinessException` ở đây được đơn giản hóa thành `ExportException` chỉ chứa message/cause nhằm làm rõ cơ chế `Suppressed`. Trong mẫu domain exception đầy đủ, hãy bổ sung error code và context như ví dụ chính.

**Đừng ghi đè cause bằng ngoại lệ cleanup.** `Caused by` trả lời mối liên hệ nguyên nhân giữa wrapper và lỗi nguồn, còn `Suppressed` giữ lỗi phụ của cleanup. Một business exception có thể có chính nó một mảng suppressed riêng nếu mã gọi `addSuppressed`; trong ví dụ, suppressed nằm ở **root `IOException`**. Vì thế `error.getSuppressed()` có thể rỗng trong khi `error.getCause().getSuppressed()` có phần tử.

## 12. Ở ranh giới API: tách thông tin nội bộ khỏi response

Một exception nghiệp vụ có thể có dữ liệu điều tra phong phú, nhưng response công khai phải theo một **hợp đồng riêng**.

Ví dụ ý tưởng:

```text
BusinessException nội bộ:
    code    = PROFILE_UNAVAILABLE
    message = Không tải được hồ sơ
    cause   = IOException("storage offline")
    context = {profileId=P-17, operation=profile.load}

Response công khai:
    errorCode = PROFILE_UNAVAILABLE
    message   = Dịch vụ tạm thời không khả dụng
    requestId = R-103
```

Đây là **mô tả dữ liệu**, không phải JSON/API schema chuẩn bắt buộc. Không đưa nguyên stack trace, đường dẫn file, cấu trúc DB, SQL, credential hoặc nội dung exception nguồn vào HTTP body.

Ví dụ Java thuần để minh họa phân loại:

```java
static int httpStatusFor(String code) {
    return switch (code) {
        case "INVALID_QUANTITY" -> 400;
        case "PROFILE_UNAVAILABLE" -> 503;
        default -> 500;
    };
}
```

Đây là **phương thức minh họa** trong class, không phải HTTP server hoàn chỉnh. 400/503 chỉ là chính sách gợi ý cho tình huống tương ứng. Với lỗi không tìm thấy tài nguyên, xung đột trạng thái hoặc quyền truy cập, hãy quyết định status dựa theo contract dịch vụ, không dựa duy nhất vào tên class.

**Cẩn trọng với 4xx/5xx:** một `IllegalArgumentException` có thể bắt nguồn từ bug server, không phải input client. Chỉ map thành 400 khi có bằng chứng lỗi thuộc trách nhiệm request. Đừng phân loại toàn bộ unchecked exception thành “lỗi người dùng”.

### Mảnh ví dụ tích hợp logger

Với logger theo API SLF4J tương thích:

```java
logger.error(
        "operation={} errorCode={} requestId={} context={}",
        operation,
        businessError.code(),
        requestId,
        businessError.context(),
        businessError);
```

Đây là **mảnh mã tích hợp**, cần thư viện/logger và các biến đã khai báo. `businessError` là **đối tượng Throwable ở đối số cuối**; với API hỗ trợ cách gọi này, logger có thể in stack trace, cause và suppressed. Hãy kiểm tra overload/structured-logging API của phiên bản thư viện bạn dùng.

Trong production, đôi khi không cần in nguyên context dưới dạng `toString()`: logger có thể ghi các trường có cấu trúc và áp dụng masking/retention tốt hơn. Tránh ghi cả ở repository, service lẫn global handler nếu chúng đang nói về **cùng một thất bại cuối**.

## 13. Mẫu chuẩn: chuyển lỗi ở ranh giới biết đủ ngữ cảnh

Có thể phân chia trách nhiệm:

```text
Repository
  readProfile(id) throws IOException
      |
      +-- không tự tạo code nghiệp vụ chỉ thuộc service
      |
Service
  loadProfile(id)
      |
      +-- bắt IOException có thể quy về lỗi domain
      +-- tạo BusinessException(P... , cause, context đã kiểm tra)
      |
Boundary
  onFailure(BusinessException)
      |
      +-- phân loại code, metric, log, response/job outcome
```

Câu hỏi review khi thấy `catch`:

- **Tầng này có thật sự hiểu nguyên nhân theo nghiệp vụ không?** Nếu không, truyền tiếp hoặc dùng exception kỹ thuật có ý nghĩa.
- **Đã có business exception tương đương chưa?** Nếu có, thường không cần bọc thêm.
- **Context nào tầng hiện tại biết chắc?** Đừng tạo `requestId` giả hoặc suy diễn transaction ID.
- **Có giữ đúng Throwable gốc không?** Không chỉ giữ message.
- **Người dùng cuối nên thấy gì?** Đây là trách nhiệm boundary/API mapper.
- **Có cần ghi log ngay không?** Nếu sẽ ném tiếp và handler cuối đã log, tránh phát sinh log trùng.

Khi một operation có retry, context có thể thêm `attempt=3` hoặc `retryExhausted=true` dưới dạng trường an toàn. Nhưng đừng log `ERROR` toàn stack cho mọi attempt chưa kết thúc; một lỗi cuối có ngữ cảnh đủ tốt thường phản ánh đúng kết quả.

## 14. Thiết kế context có kiểu mạnh khi nhu cầu cố định

Với vài trường bắt buộc, `record` trong Java 17 cho một lựa chọn rõ ràng:

```java
record ErrorContext(
        String operation,
        String resourceId,
        String correlationId) {
}
```

Đây là **một record có thể đặt trong tệp riêng hoặc cùng package phù hợp**. Bản thân record có các component final và accessor; tuy nhiên nếu component là đối tượng mutable, record không tự deep-copy. Với `String`, dữ liệu là immutable.

Có thể dùng class business exception chứa:

```java
private final ErrorContext context;

BusinessException(
        ErrorCode code,
        String message,
        Throwable cause,
        ErrorContext context) {
    super(message, cause);
    this.code = Objects.requireNonNull(code);
    this.context = Objects.requireNonNull(context);
}
```

Đây là **mảnh constructor minh họa** thuộc class có các field `code`, `context` đã khai báo. Ưu điểm: compiler giúp phát hiện nhầm tên trường, IDE hỗ trợ navigation và các field quan trọng hiện diện ngay trong API. Nhược điểm: schema ít linh hoạt hơn map với nhiều loại operation.

Cần phân biệt `record` cho **context** với việc dùng record làm **exception**: Java record ngầm kế thừa `java.lang.Record`, nên một record **không thể đồng thời extends `RuntimeException`**. Muốn tạo Throwable riêng, dùng `class extends Exception/RuntimeException`.

## 15. Context không thay thế stack trace và message

Một anti-pattern:

```java
throw new IllegalStateException(
        "PROFILE_UNAVAILABLE; "
        + "profileId=" + id
        + "; cause=" + cause.getMessage());
```

Đây là **mảnh mã minh họa** trong `catch`. Nó trộn error code, context và lời mô tả cause thành một chuỗi. Nếu không truyền `cause` cho constructor, caller mất **loại Throwable gốc và stack trace**. Chuỗi message còn khó parse, dễ bị thay đổi do ngôn ngữ hoặc escaping.

Mẫu tốt hơn:

```java
throw new BusinessException(
        ErrorCode.PROFILE_UNAVAILABLE,
        "Không thể tải hồ sơ",
        cause,
        Map.of("profileId", id, "operation", "profile.load"));
```

Đây là **mảnh minh họa** dùng định nghĩa exception trong mục 4. Error code dùng để quyết định, context dùng để lọc log, message cho người đọc, cause cho nguyên nhân kỹ thuật. Các vai trò bổ sung nhau.

Đừng dựa vào `Throwable.toString()` như một định dạng lưu trữ máy cần parse; `toString()` chủ yếu kết hợp tên lớp và `getLocalizedMessage()`. Cần máy đọc, hãy sử dụng field/code riêng.

## 16. Test đầy đủ hợp đồng error code, cause, context và đường thành công

JUnit Jupiter giúp test loại exception và field. Phần dưới là **ví dụ tích hợp JUnit 5**, giả định class `BusinessExceptionDemo` ở mục 4 có thể được truy cập từ test trong cùng package.

Tệp `BusinessExceptionContractTest.java`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class BusinessExceptionContractTest {
    @Test
    void returnsProfileOnSuccess() {
        String value = BusinessExceptionDemo.loadProfile(
                "P-17", id -> "Lan");

        assertEquals("Lan", value);
    }

    @Test
    void keepsBusinessCodeCauseAndContextOnFailure() {
        IOException root = new IOException("storage offline");

        BusinessExceptionDemo.BusinessException error =
                assertThrows(
                    BusinessExceptionDemo.BusinessException.class,
                    () -> BusinessExceptionDemo.loadProfile(
                        "P-17", id -> { throw root; }));

        assertEquals(
                BusinessExceptionDemo.ErrorCode.PROFILE_UNAVAILABLE,
                error.code());
        assertSame(root, error.getCause());
        assertEquals("P-17", error.context().get("profileId"));
        assertEquals("profile.load",
                error.context().get("operation"));
        assertThrows(
                UnsupportedOperationException.class,
                () -> error.context().put("other", "value"));
    }
}
```

Test cần dependency `org.junit.jupiter` và test runner của Maven/Gradle/IDE. Không chạy trực tiếp với `java BusinessExceptionContractTest` mà chưa thiết lập môi trường test. Class lồng của ví dụ chính có visibility mặc định package-private, nên đặt test cùng package nếu giữ nguyên mã.

**Vì sao các assertion này hữu ích?**

- Test success chứng minh đường hợp lệ không ném business exception và trả đúng giá trị.
- `assertThrows` khẳng định **đúng loại exception theo hợp đồng**; nó chấp nhận subclass. Nếu contract đòi chính xác class, cân nhắc `assertThrowsExactly` khi JUnit hỗ trợ.
- `assertSame(root, error.getCause())` khẳng định giữ **đúng đối tượng nguyên nhân**, không chỉ tạo mới một Throwable tương tự.
- Hai assertion context khẳng định ngữ cảnh còn chính xác khi lỗi được truyền.
- Thử `put` xác nhận view map context không sửa được.

### Kiểm thử một lỗi validation không có cause

Nếu API tạo business exception **trực tiếp** vì input sai, kỳ vọng có thể là:

- `error.code() == INVALID_QUANTITY`.
- `error.getCause() == null` nếu không có lỗi nguồn.
- Context chỉ chứa tên trường/constraint an toàn.
- Không có side effect trên kho dữ liệu.

Đừng ép mọi exception phải có cause khác null. **Cause bắt buộc khi bọc một lỗi thực sự; cause không nhất thiết tồn tại khi tự phát hiện vi phạm nghiệp vụ.**

## 17. Test thuần JDK không cần framework

Nếu muốn kiểm tra nhanh một hợp đồng không cần JUnit, bạn có thể tự assert. Tệp `BusinessExceptionSmokeTest.java`:

```java
import java.io.IOException;
import java.util.Map;

public class BusinessExceptionSmokeTest {
    static final class DomainFailure extends RuntimeException {
        private final String code;
        private final Map<String, String> context;

        DomainFailure(
                String code, Throwable cause,
                Map<String, String> context) {
            super("read failed", cause);
            this.code = code;
            this.context = Map.copyOf(context);
        }

        String code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Contract violated");
        }
    }

    static String read(boolean fail) {
        if (!fail) {
            return "OK";
        }

        IOException root = new IOException("offline");
        throw new DomainFailure(
                "READ_UNAVAILABLE",
                root,
                Map.of("operation", "data.read"));
    }

    public static void main(String[] args) {
        check("OK".equals(read(false)));
        System.out.println("success tested");

        try {
            read(true);
            throw new AssertionError("Expected DomainFailure");
        } catch (DomainFailure e) {
            check("READ_UNAVAILABLE".equals(e.code()));
            check(e.getCause() instanceof IOException);
            check("data.read".equals(
                    e.context().get("operation")));

            System.out.println("failure tested");
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac BusinessExceptionSmokeTest.java
java BusinessExceptionSmokeTest
```

Output:

```text
success tested
failure tested
cause = IOException
```

Đây là ví dụ test một class exception nhỏ độc lập, không phụ thuộc demo đầu tiên. Nếu code bị sửa để **nuốt lỗi** và trả `"OK"`, test đường thất bại ném `AssertionError`. Nếu bỏ cause hoặc mã lỗi, các phép kiểm tra cũng phát hiện. Những assertion tùy biến này minh họa tư duy hợp đồng; trong dự án lớn nên dùng thư viện test để có báo cáo, fixture và quản lý suite tốt hơn.

## 18. Kiểm soát log và khả năng quan sát

Ngoại lệ nghiệp vụ có context không tự mang ý nghĩa rằng phải in log tại mỗi tầng. Quyết định log nên thuộc thành phần biết **kết quả cuối cùng** của request/job.

Một chính sách thực hành:

| Trường hợp | Hành động | Log phù hợp |
|---|---|---|
| Repository ném `IOException`, service sẽ bọc | Ném lỗi lên, giữ cause | Thường không cần `ERROR` trùng |
| Service nhận lỗi có thể phục hồi bằng fallback | Trả dữ liệu dự phòng, báo metric | `INFO`/`WARN` hoặc metric theo tác động |
| BusinessException đến global handler và request thất bại | Map error code/status, log Throwable đầy đủ một lần | `ERROR` nếu là thất bại không dự kiến/cần điều tra |
| Input client sai theo contract | Tạo lỗi validation có code rõ | Có thể `INFO`/metric, không mặc định stack `ERROR` |
| Cancellation/interrupt dự kiến | Hợp tác dừng và cleanup | Thường không phải error nghiệp vụ |
| Có lỗi cleanup gây hậu quả riêng | Giữ suppressed, đánh giá sự cố | Có thể log sự kiện riêng nếu có ý nghĩa độc lập |

Để liên kết log giữa các tầng, dùng request ID hoặc trace ID được tạo ở entry boundary và truyền qua context/telemetry. Nếu dùng `ThreadLocal`/MDC trong tác vụ bất đồng bộ, bảo đảm cơ chế propagation và cleanup đúng; không giả định thread mới tự có context của caller.

Không nên đưa một toàn bộ stack trace vào `context` dưới dạng chuỗi. `Throwable` đã giữ thông tin stack, `Caused by` và `Suppressed`; logger nên được cấu hình để ghi các cấu trúc đó khi cần.

## 19. Các lỗi triển khai thường gặp

### 19.1. Tạo exception mới nhưng không truyền cause

Sai:

```java
catch (IOException e) {
    throw new BusinessException(
            ErrorCode.PROFILE_UNAVAILABLE,
            "Không tải được hồ sơ",
            null,
            Map.of("operation", "profile.load"));
}
```

Mảnh mã trên dùng class ví dụ chính. `null` khiến chuỗi nguyên nhân bị mất dù `e` đang tồn tại. Sửa bằng cách truyền `e` vào tham số cause.

### 19.2. Chỉ giữ nguyên văn `getMessage()` của lỗi kỹ thuật

```java
throw new RuntimeException("Source failed: " + e.getMessage());
```

Mảnh mã minh họa này có thể bỏ mất loại exception và stack gốc; message có thể thay đổi theo thư viện/JDK. Nếu cần bọc, dùng constructor nhận Throwable, rồi để logger in cause.

### 19.3. Biến exception thành nơi ghi log tự động

Constructor `BusinessException` gọi `logger.error` làm mỗi lần khởi tạo tạo log, kể cả khi caller phục hồi. Hãy tách event logging khỏi dữ liệu lỗi, tránh lặp stack trace nhiều tầng.

### 19.4. Cho context tham chiếu đến map mutable

Giữ nguyên tham chiếu `HashMap` đầu vào có thể làm context bị sửa sau khi lỗi xảy ra. Sử dụng `Map.copyOf`, `Collections.unmodifiableMap` trên bản sao hoặc record có value immutable.

### 19.5. Dùng `Map<String,Object>` chứa toàn entity

Object có thể thay đổi, `toString()` đắt hoặc lộ dữ liệu. Chỉ lưu trường an toàn, đã chuẩn hóa, có hạn mức.

### 19.6. Dùng error message làm error code

So sánh `"Không tìm thấy hồ sơ"` trong logic điều khiển rất dễ hỏng khi đổi ngôn ngữ hay chỉnh câu chữ. Sử dụng enum/string code ổn định.

### 19.7. Map mọi `RuntimeException` thành lỗi đầu vào

`NullPointerException` từ bug server không đương nhiên là HTTP 400. Phải xác định lỗi có phải do client vi phạm hợp đồng hay không.

### 19.8. Bọc lại business exception ở từng tầng

Ba tầng cùng làm `throw new BusinessException(..., caught)` gây nhiều lớp wrapper không cần thiết; điều tra trở nên khó và thông tin context dễ trùng. Chỉ thêm wrapper nếu thay đổi **ngữ nghĩa** hoặc hợp đồng của tầng.

### 19.9. Dùng exception chứa dữ liệu nhạy cảm

Đừng nhét token, secret, SQL chứa dữ liệu, địa chỉ riêng hoặc payload người dùng vào context. Log được lưu và truy cập ở những nơi khác với luồng xử lý nghiệp vụ; quyền riêng tư phải là một phần của thiết kế ngoại lệ.

### 19.10. Để hàm tạo message gây lỗi mới

Một message supplier thực hiện I/O hoặc serialize object quá lớn có thể tạo lỗi thứ hai, che lỗi chính. Message và context nên được chuẩn bị từ **thông tin sẵn có, rẻ và đáng tin** trên đường lỗi.

### 19.11. Nhầm cause với suppressed

Một lỗi `close()` xảy ra sau lỗi xử lý chính thường là **suppressed**. Đừng tự thay cause bằng lỗi cleanup; dùng `try-with-resources` hoặc cơ chế bảo toàn cả hai exception.

### 19.12. Test chỉ kiểm tra có `RuntimeException`

Test quá rộng có thể xanh vì một `NullPointerException` bất ngờ. Kiểm tra đúng business exception, code, cause và context; thêm test success để tránh thay đổi hành vi bình thường.

## 20. Quy trình xây dựng business exception trong dự án thực tế

Có thể áp dụng theo thứ tự:

1. **Liệt kê tình huống nghiệp vụ thật sự cần phân loại**: validation sai, tài nguyên không khả dụng, xung đột, phụ thuộc lỗi, thao tác bị từ chối.
2. **Xác định contract với caller**: checked/unchecked, loại exception, mã lỗi công khai, tính có thể retry, thông điệp hiển thị.
3. **Chọn schema context**: ID/operation/correlation ID đã kiểm soát, whitelist và giới hạn kích thước; không lưu thông tin bí mật.
4. **Định nghĩa immutable exception fields**: `final`, getter chỉ đọc, `Map.copyOf` hoặc record context có dữ liệu immutable.
5. **Giữ nguyên cause** khi bọc lỗi kỹ thuật ở ranh giới đủ ngữ nghĩa.
6. **Bảo toàn suppressed** nếu cleanup cũng lỗi; ưu tiên `try-with-resources`.
7. **Chỉ bọc tại tầng phù hợp**, không log-and-throw trùng ở mỗi `catch`.
8. **Mapping ở boundary**: dịch `ErrorCode` thành response/job result an toàn, log Throwable có ngữ cảnh ở nơi chịu trách nhiệm.
9. **Kiểm thử hai đường**: success, failure, cause identity, context snapshot, field bắt buộc, cleanup side effects.
10. **Theo dõi thực tế**: metric theo error code/operation, trace ID, tỷ lệ lỗi, retry outcome và chính sách bảo vệ log.

### Checklist nhanh trước khi merge

- Loại exception có phản ánh đúng hợp đồng và caller có biết cách xử lý?
- `ErrorCode` có ổn định và không phụ thuộc câu chữ thông báo?
- Constructor bọc lỗi có gọi `super(message, cause)`?
- Nếu là validation tự phát hiện, việc cause bằng `null` có đúng?
- Context có immutable, chỉ gồm các trường an toàn, ổn định và vừa đủ?
- Có tránh truyền nguyên entity, request body, token và đối tượng mutable?
- Có bảo toàn cause/suppressed nếu cả xử lý và cleanup đều thất bại?
- Có một tầng chịu trách nhiệm map kết quả/log hay đang ghi lặp ở nhiều tầng?
- Test có xác minh success, loại exception, mã lỗi, `getCause()`, context, và side effects?
- Response công khai có tách khỏi thông tin kỹ thuật nhạy cảm trong Throwable?

**Kết luận:** một ngoại lệ nghiệp vụ tốt là **hợp đồng lỗi có cấu trúc**, không phải một chuỗi message dài. Dùng loại exception phù hợp, **mã lỗi ổn định**, thông điệp có ích, `super(message, cause)` để giữ nguyên nhân và **context bất biến, an toàn** cho chẩn đoán. Chỉ chuyển loại lỗi ở nơi hiểu ngữ nghĩa nghiệp vụ, giữ suppressed khi cleanup thất bại và kiểm thử cả đường thành công lẫn đường lỗi.
