# Phân biệt thông tin chẩn đoán nội bộ với thông báo dành cho người dùng trong Java Exception

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **thông tin chẩn đoán nội bộ** (*diagnostic information*) với **thông báo công khai** (*user-facing error message*) khi một thao tác Java thất bại.
- Hiểu vì sao không nên trả trực tiếp `exception.getMessage()`, stack trace, đường dẫn file, câu SQL hoặc thông tin hạ tầng cho người dùng.
- Giữ ngoại lệ gốc và cause chain ở nơi chẩn đoán phù hợp, đồng thời thiết kế **loại lỗi, mã lỗi và thông điệp ổn định** cho ranh giới API.
- Phân loại lỗi validation, không tìm thấy tài nguyên, lỗi nghiệp vụ và lỗi hệ thống thay vì biến tất cả thành một thông báo hoặc một HTTP status giống nhau.
- Thiết kế `requestId`/`correlationId` để người dùng có thể báo sự cố mà không cần nhìn chi tiết kỹ thuật.
- Ghi log có cấu trúc, tránh rò rỉ dữ liệu nhạy cảm và tránh ghi cùng một lỗi lặp lại ở nhiều tầng.
- Kiểm thử rằng thông báo công khai không tiết lộ bí mật trong `Throwable` và vẫn giữ đủ thông tin để kỹ sư điều tra.

Bài sử dụng Java 17+ và ví dụ độc lập không phụ thuộc framework. Các đoạn về HTTP và thư viện logging được ghi rõ là minh họa ở ranh giới ứng dụng, không phải một HTTP server thực sự.

## 2. Một sự cố — hai nhóm người nhận thông tin

Giả sử chức năng đọc hóa đơn gọi tầng lưu trữ. Một lần đọc thất bại với `IOException` chứa chuỗi kỹ thuật như đường dẫn nội bộ, tên server hoặc địa chỉ kết nối.

**Kỹ sư vận hành** cần biết exception type, call stack, cause, thao tác nào lỗi, thời điểm, request ID và thành phần liên quan để tìm nguyên nhân.

**Người dùng** cần biết thao tác nào không thực hiện được, có thể làm gì tiếp theo, có nên thử lại không và cách cung cấp mã tham chiếu để bộ phận hỗ trợ tra cứu. Họ thường không cần biết địa chỉ máy chủ, tên lớp Java hoặc stack trace.

| Tiêu chí | Chẩn đoán nội bộ | Thông báo cho người dùng |
| --- | --- | --- |
| Mục đích | Phát hiện, phân loại, điều tra và khắc phục lỗi | Hiểu vấn đề và biết bước tiếp theo |
| Đối tượng | Kỹ sư/nhân sự có quyền phù hợp | Người dùng, client API hoặc hệ thống tích hợp |
| Nội dung | Throwable, stack trace, cause, suppressed, request ID, component và ngữ cảnh cần thiết | Mã lỗi ổn định, mô tả an toàn, hướng dẫn hợp lý, mã tham chiếu |
| Độ chi tiết | Có thể cao nhưng vẫn phải kiểm soát dữ liệu nhạy cảm | Chỉ mức chi tiết cần thiết, không hé lộ triển khai |
| Vòng đời | Log, tracing, hệ thống giám sát, incident record | UI, HTTP response, CLI, email, thông báo sản phẩm |
| Tính ổn định | Có thể thay theo phiên bản code, thư viện, cấu trúc hệ thống | Nên ổn định theo hợp đồng API và có thể dịch ngôn ngữ |
| Ví dụ | `IOException` trong `InvoiceRepository` gây `InvoiceLoadException` | “Không thể tải hóa đơn lúc này. Vui lòng thử lại sau. Mã tham chiếu: RQ-1042.” |

**Nguyên tắc cốt lõi:** không gửi bản ghi chẩn đoán nguyên trạng cho người dùng. Hãy **dịch lỗi tại ranh giới tin cậy**: giữ dữ liệu phù hợp cho kỹ sư, nhưng công bố một hợp đồng lỗi an toàn và dễ hiểu.

~~~text
Client gửi yêu cầu
        |
        v
Application / API boundary
        |
        v
Repository gọi hạ tầng
        |
        +--> IOException("host=db-private, path=/var/...")  [chi tiết nội bộ]
                    |
                    v
          InvoiceLoadException(message, cause)
                    |
          +---------+---------------------------------+
          |                                           |
          v                                           v
  Chẩn đoán nội bộ                              Public error
  type, cause, stack trace                     code + safe message
  requestId, operation                         + requestId
  log/traces có kiểm soát                      không lộ hạ tầng
~~~

## 3. Throwable chứa những gì và vì sao không công khai nguyên trạng?

Một `Throwable` trong Java có nhiều nguồn thông tin:

- `getClass().getName()`: tên lớp exception, thường phản ánh thư viện hoặc công nghệ đang dùng.
- `getMessage()`: văn bản chi tiết có thể do tầng I/O, JDBC, thư viện HTTP, framework hoặc lập trình viên tạo.
- `getCause()`: ngoại lệ nguyên nhân, có thể lại có cause riêng.
- `getStackTrace()`: đường gọi với tên class, phương thức, tệp nguồn và số dòng khi có.
- `getSuppressed()`: ngoại lệ bổ sung được giữ trong một số cơ chế, đặc biệt `try-with-resources`.
- `printStackTrace()`: cách biểu diễn Throwable, các nguyên nhân và những ngoại lệ suppressed phục vụ chẩn đoán.

Tất cả thông tin này **không có nghĩa là an toàn để xuất ra client**. Ví dụ `SQLException` có thể chứa chi tiết SQL và tên bảng; `IOException` có thể chứa đường dẫn máy chủ; exception từ SDK có thể mang endpoint, response body hoặc ID tài nguyên nội bộ. Một exception message không phải văn bản đã được duyệt về bảo mật và tính dễ hiểu.

### Ba lỗi công khai thường gặp

**Lỗi 1 — trả thẳng message của exception:**

~~~java
return error.getMessage();
~~~

Đây là **mã minh họa** trong một phương thức trả chuỗi. `getMessage()` có thể là `null`, khó hiểu, thay đổi giữa các phiên bản hoặc chứa thông tin nội bộ.

**Lỗi 2 — trả nguyên stack trace:**

~~~java
StringWriter writer = new StringWriter();
error.printStackTrace(new PrintWriter(writer));
return writer.toString();
~~~

Đây là **mã minh họa** giả định `error` là `Throwable` và đã import các lớp `java.io`. Nó đưa dữ liệu chẩn đoán vào lời đáp công khai. Stack trace có thể lộ tên package, class, phương thức, đường dẫn, thông tin nhạy cảm có trong message/cause.

**Lỗi 3 — che giấu tất cả bằng câu vô nghĩa:** người dùng chỉ nhận “Error” mà không biết yêu cầu nào bị từ chối, liệu thao tác có thể thử lại hoặc cần chỉnh input. Bảo mật **không đòi loại bỏ mọi thông tin hữu ích**; cần công bố thông tin an toàn, đúng hợp đồng, có thể hành động.

## 4. Tách ba tầng: nguyên nhân kỹ thuật, lỗi theo ý nghĩa API và thông báo công khai

Hãy phân biệt:

1. **Nguyên nhân kỹ thuật:** ví dụ `IOException`, `SQLException` hoặc lỗi kết nối tới dịch vụ phụ thuộc.
2. **Ngoại lệ tại tầng trừu tượng:** ví dụ `InvoiceLoadException`, `PaymentRejectedException` hoặc `DocumentNotFoundException`.
3. **Biểu diễn cho người dùng/client:** ví dụ `{code, message, requestId}` với HTTP status phù hợp.

Ranh giới repository/service có thể chuyển ngoại lệ kỹ thuật thành ngoại lệ tầng ứng dụng:

~~~java
try {
    return storage.read(invoiceId);
} catch (IOException original) {
    throw new InvoiceLoadException(
            "Không thể đọc hóa đơn " + invoiceId, original);
}
~~~

Đây là **đoạn minh họa**, giả định các biến/lớp tương ứng tồn tại và constructor `InvoiceLoadException(String, Throwable)` đã được khai báo.

Tầng service vẫn giữ **cause là chính đối tượng** `IOException` gốc để điều tra. Nhưng `InvoiceLoadException.getMessage()` **không nhất thiết** là message public: nó có thể chứa một ID nội bộ hoặc bối cảnh chỉ dành cho log.

Tại ranh giới HTTP/UI, một error mapper quyết định mã lỗi và thông điệp công khai theo loại lỗi đã được phân loại. Tầng giao tiếp **không** nên dùng nguyên tên class exception để tạo thông báo, vì tên class là chi tiết triển khai.

**Giữ cause phục vụ truy vết; lọc thông tin công khai phục vụ hợp đồng và bảo mật.** Đây là hai trách nhiệm tương hỗ, không mâu thuẫn.

## 5. Thiết kế error contract cho người dùng

Một dạng dữ liệu lỗi công khai có thể gồm:

~~~json
{
  "code": "DOCUMENT_UNAVAILABLE",
  "message": "Không thể tải tài liệu lúc này. Vui lòng thử lại sau.",
  "requestId": "RQ-1042"
}
~~~

Đây là **mẫu JSON minh họa**, không phải response của một HTTP server được chạy trong bài.

Các trường nên có hợp đồng rõ:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `code` | Mã lỗi có ý nghĩa ổn định cho client | Không gắn vào tên lớp/driver có thể thay đổi |
| `message` | Câu diễn đạt ngắn, dễ hiểu và an toàn | Không sao chép stack trace hoặc message kỹ thuật |
| `requestId` | Mã tham chiếu để tra log/trace | Không nhúng secret, token hoặc định danh nhạy cảm; kiểm soát độ dài/định dạng |
| `details` (tùy hợp đồng) | Thông tin có cấu trúc giúp sửa input | Chỉ chứa trường dữ liệu được phép công bố |
| HTTP status (nếu API HTTP) | Nhóm nguyên nhân ở lớp giao thức | Phải phản ánh đúng lỗi và hợp đồng nghiệp vụ |

Có thể hiển thị message bằng ngôn ngữ người dùng, trong khi `code` giữ ổn định để client ra quyết định mà không so sánh chuỗi ngôn ngữ tự nhiên.

Ví dụ lỗi validation:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Vui lòng nhập địa chỉ email hợp lệ.",
  "details": [
    {"field": "email", "reason": "invalid_format"}
  ],
  "requestId": "RQ-1043"
}
~~~

Đây cũng chỉ là **ví dụ biểu diễn JSON**. Trả tên trường như `email` có thể hợp lý nếu đây là input của chính người dùng; không tự động trả giá trị bí mật mà họ vừa nhập.

### Nội dung nào hữu ích cho người dùng?

- **Xác định hành động:** “Không thể tải tài liệu”, “Không thể lưu thay đổi” thay vì “Lỗi hệ thống”.
- **Trạng thái có thể hành động:** “Vui lòng kiểm tra định dạng email” đối với lỗi validation.
- **Khả năng thử lại có cơ sở:** với lỗi tạm thời, có thể hướng dẫn thử lại sau, nhưng tránh khuyên retry vô điều kiện các thao tác có tác dụng phụ.
- **Mã tham chiếu:** giúp hỗ trợ tra cứu mà không cần người dùng gửi stack trace, token hoặc thông tin riêng tư.
- **Không khẳng định quá mức:** timeout không chứng minh giao dịch chưa được thực hiện; thông báo phải thận trọng, đặc biệt với thanh toán hoặc tạo đơn hàng.

Thông điệp công khai nên ổn định về nghĩa, nhưng có thể thay đổi văn phong, bản dịch và phương thức hiển thị theo sản phẩm. Client không nên phân tích `message` để điều khiển logic; hãy sử dụng `code` và các trường có cấu trúc.

## 6. Ví dụ Java 17 độc lập: giữ cause, không để lộ chi tiết nội bộ

Tạo tệp **SafeErrorBoundaryDemo.java** với toàn bộ nội dung sau. Chương trình không gọi mạng hoặc cơ sở dữ liệu thật; nó giả lập lỗi I/O có chứa thông tin hạ tầng để kiểm chứng rằng public message không làm lộ thông tin đó.

~~~java
import java.io.IOException;

public class SafeErrorBoundaryDemo {

    static final class DocumentLoadException extends RuntimeException {
        DocumentLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record PublicError(String code, String message, String requestId) {
    }

    static String loadDocument(String id) {
        try {
            throw new IOException(
                    "host=db-private.local; path=/srv/private; password=secret");
        } catch (IOException original) {
            throw new DocumentLoadException(
                    "Không đọc được tài liệu " + id, original);
        }
    }

    static PublicError toPublicError(
            DocumentLoadException error, String requestId) {
        return new PublicError(
                "DOCUMENT_UNAVAILABLE",
                "Không thể tải tài liệu lúc này. Vui lòng thử lại sau.",
                requestId);
    }

    public static void main(String[] args) {
        String requestId = "RQ-1042";

        try {
            loadDocument("invoice-7");
        } catch (DocumentLoadException error) {
            Throwable cause = error.getCause();

            // Thông tin chẩn đoán mẫu, cố ý không in message nhạy cảm.
            System.out.println("INTERNAL type: "
                    + error.getClass().getSimpleName());
            System.out.println("INTERNAL cause type: "
                    + cause.getClass().getSimpleName());
            System.out.println("INTERNAL cause retained: "
                    + (cause instanceof IOException));

            // Cấu trúc này mới là dữ liệu dành cho client.
            PublicError response = toPublicError(error, requestId);

            System.out.println("PUBLIC code: " + response.code());
            System.out.println("PUBLIC message: " + response.message());
            System.out.println("PUBLIC requestId: "
                    + response.requestId());

            boolean leaksSecret =
                    response.message().contains("db-private")
                    || response.message().contains("password")
                    || response.message().contains("/srv/private");

            System.out.println("PUBLIC leaks internals: " + leaksSecret);
        }
    }
}
~~~

Biên dịch và chạy với Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 SafeErrorBoundaryDemo.java
java SafeErrorBoundaryDemo
~~~

**Stdout dự kiến, xác định:**

~~~text
INTERNAL type: DocumentLoadException
INTERNAL cause type: IOException
INTERNAL cause retained: true
PUBLIC code: DOCUMENT_UNAVAILABLE
PUBLIC message: Không thể tải tài liệu lúc này. Vui lòng thử lại sau.
PUBLIC requestId: RQ-1042
PUBLIC leaks internals: false
~~~

### Những điểm quan trọng của ví dụ

1. Lỗi `IOException` được giả lập với message có hostname, đường dẫn và mật khẩu dạng chữ. Không dùng thông tin thật; các chuỗi này chỉ nhằm kiểm thử nguy cơ tiết lộ.
2. Tầng đọc dữ liệu tạo `DocumentLoadException` và truyền `original` làm cause bằng `super(message, cause)`. Thông tin lỗi vẫn được bảo toàn bên trong.
3. Tầng giao tiếp tạo `PublicError` từ loại lỗi và một `requestId` hợp lệ. Nó không gọi `error.getMessage()` hoặc `cause.getMessage()` để tạo lời đáp.
4. Các dòng `INTERNAL` minh họa **thông tin an toàn đã chọn** để in cho lớp học. Trong hệ thống thật, chẩn đoán thường được gửi tới logger/tracing có quyền truy cập; ví dụ không cố ý in toàn bộ cause nhạy cảm ra console.
5. Dòng `PUBLIC leaks internals: false` xác nhận public message không chứa những marker đã đưa vào exception gốc. Ở dự án thật, kiểm thử nên bao phủ **toàn bộ payload public** chứ không chỉ riêng trường message.
6. `PublicError` là record Java 17, dùng accessor `code()`, `message()`, `requestId()`. Chương trình có thể chạy độc lập, không cần dependency framework.

**Điểm giới hạn:** kiểm tra `contains` ở ví dụ là một phép thử minh họa, không thay thế rà soát bảo mật nội dung xuất ra. Một hệ thống có nhiều loại secret, identifier và payload cần cơ chế lọc, review hợp đồng và kiểm thử thích hợp hơn.

## 7. Phân loại lỗi: không phải lỗi nào cũng có một public message

Đối với API, đặc biệt là API HTTP, cần phân biệt lỗi do input, trạng thái tài nguyên, quy tắc nghiệp vụ và hạ tầng. Ví dụ định hướng:

| Tình huống | Loại lỗi tầng ứng dụng | HTTP status thường phù hợp | Ví dụ lời báo an toàn |
| --- | --- | --- | --- |
| Yêu cầu sai định dạng | Validation exception | 400 Bad Request | “Dữ liệu nhập không hợp lệ.” |
| Không xác thực hợp lệ | Authentication failure | 401 Unauthorized | “Vui lòng đăng nhập lại.” |
| Không có quyền thực hiện | Authorization failure | 403 Forbidden | “Bạn không có quyền thực hiện thao tác này.” |
| Tài nguyên không được tìm thấy theo hợp đồng | Not-found exception | 404 Not Found | “Không tìm thấy tài liệu.” |
| Xung đột trạng thái hoặc nghiệp vụ | Conflict/domain exception | 409 Conflict, nếu hợp đồng phù hợp | “Dữ liệu đã thay đổi. Vui lòng tải lại.” |
| Hạ tầng tạm thời không khả dụng | Service unavailable | 503 Service Unavailable nếu đúng tình trạng | “Dịch vụ tạm thời không khả dụng.” |
| Lỗi ngoài dự kiến ở server | Internal error | 500 Internal Server Error | “Không thể xử lý yêu cầu lúc này.” |

Bảng chỉ là **định hướng**; lựa chọn mã HTTP cụ thể phải dựa vào ý nghĩa và hợp đồng API. Không chuyển tất cả exception thành 500 chỉ để code ngắn hơn, cũng không gắn 503 cho mọi `IOException` nếu chưa chứng minh được tính “tạm thời không khả dụng”.

### Không lộ sự tồn tại của tài nguyên khi không được phép

Một yêu cầu truy cập tài liệu có thể dẫn tới 403 hoặc 404 tùy chính sách bảo mật. Có hệ thống cố ý không tiết lộ sự tồn tại của tài nguyên mà người dùng không có quyền xem. Vì vậy, việc ánh xạ exception vào thông điệp “tài liệu X tồn tại nhưng bạn không được xem” có thể tạo lỗ hổng về thông tin.

Nếu một ID không hợp lệ, thông báo chỉ nên bao gồm những phần input được phép hiển thị. Không đưa nguyên token, session ID hoặc thông tin của người dùng khác vào error response.

### Không khẳng định thao tác chưa được thực hiện chỉ vì timeout

Ví dụ API thanh toán bị timeout: backend có thể đã thực hiện giao dịch, nhưng kết quả chưa đến client. Thông báo “Thanh toán thất bại, hãy bấm gửi lại ngay” có thể dẫn tới thao tác trùng. Trong trường hợp này nên cung cấp trạng thái thận trọng, mã tham chiếu và cách kiểm tra kết quả/idempotency theo hợp đồng.

## 8. Ví dụ Java 17 độc lập: mapper chọn thông báo theo loại lỗi

Tệp **ErrorClassificationDemo.java** sau minh họa phân loại bốn tình huống và tạo các thông báo khác nhau. Nó **không** khởi động HTTP server; trường `status` chỉ mô phỏng mã trạng thái cần dùng ở adapter HTTP.

~~~java
import java.io.IOException;

public class ErrorClassificationDemo {

    static final class DocumentMissingException extends RuntimeException {
        DocumentMissingException(String message) {
            super(message);
        }
    }

    static final class BackendUnavailableException extends RuntimeException {
        BackendUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record ApiError(int status, String code, String message) {
    }

    static void execute(String scenario) {
        switch (scenario) {
            case "invalid" ->
                    throw new IllegalArgumentException("internal field x invalid");
            case "missing" ->
                    throw new DocumentMissingException("path=/srv/private/42");
            case "down" ->
                    throw new BackendUnavailableException(
                            "Storage backend failed",
                            new IOException("host=db-private.local"));
            case "unexpected" ->
                    throw new IllegalStateException("internal state corrupted");
            default -> {
                // Thành công: không ném ngoại lệ.
            }
        }
    }

    static ApiError mapToPublic(RuntimeException error) {
        if (error instanceof IllegalArgumentException) {
            return new ApiError(
                    400, "INVALID_INPUT", "Dữ liệu nhập không hợp lệ.");
        }
        if (error instanceof DocumentMissingException) {
            return new ApiError(
                    404, "NOT_FOUND", "Không tìm thấy tài liệu.");
        }
        if (error instanceof BackendUnavailableException) {
            return new ApiError(
                    503, "SERVICE_UNAVAILABLE",
                    "Dịch vụ tạm thời không khả dụng.");
        }
        return new ApiError(
                500, "INTERNAL_ERROR",
                "Không thể xử lý yêu cầu lúc này.");
    }

    public static void main(String[] args) {
        String[] scenarios = {
                "invalid", "missing", "down", "unexpected", "ok"
        };

        for (String scenario : scenarios) {
            try {
                execute(scenario);
                System.out.println(scenario + " -> SUCCESS");
            } catch (RuntimeException error) {
                ApiError response = mapToPublic(error);
                System.out.println(scenario + " -> "
                        + response.status() + " "
                        + response.code() + " | "
                        + response.message());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ErrorClassificationDemo.java
java ErrorClassificationDemo
~~~

**Stdout dự kiến, xác định:**

~~~text
invalid -> 400 INVALID_INPUT | Dữ liệu nhập không hợp lệ.
missing -> 404 NOT_FOUND | Không tìm thấy tài liệu.
down -> 503 SERVICE_UNAVAILABLE | Dịch vụ tạm thời không khả dụng.
unexpected -> 500 INTERNAL_ERROR | Không thể xử lý yêu cầu lúc này.
ok -> SUCCESS
~~~

Ví dụ minh họa được logic:

- `IllegalArgumentException` của yêu cầu đã chọn được ánh xạ thành lỗi input. Trong hệ thống thực, không nên bắt **mọi** `IllegalArgumentException` toàn cục rồi mặc định đổ lỗi cho client: lỗi cũng có thể xuất phát từ bug server. Adapter cần phân biệt exception do kiểm tra input có chủ đích với exception bất ngờ.
- `DocumentMissingException` biểu đạt chính sách tài nguyên không tìm thấy. Việc công khai 404 chỉ hợp lệ khi không làm lộ thông tin bị giới hạn truy cập.
- `BackendUnavailableException` có cause `IOException` giữ trong ứng dụng, nhưng response không tiết lộ hostname.
- `IllegalStateException` không dự kiến rơi vào nhánh lỗi server chung với message an toàn, thay vì trả `internal state corrupted`.
- Nhánh `ok` không ném exception, được xử lý như thành công. Không tạo “error envelope” cho một hoạt động vốn đã thành công.

Trong sản phẩm, nên định nghĩa các loại exception rõ nghĩa hơn thay vì dựa vào những exception hệ thống quá chung chung khi ánh xạ public code.

## 9. Ghi log nội bộ: cần đủ chẩn đoán, không đồng nghĩa ghi mọi dữ liệu

Ở tầng chẩn đoán, cần biết thao tác, kết quả, bối cảnh và exception. Một log event hữu ích thường chứa:

| Trường | Ví dụ | Lý do |
| --- | --- | --- |
| Timestamp | Thời điểm sự cố theo hệ thống log | Ghép sự kiện theo thời gian |
| Severity | `WARN`, `ERROR` | Phân loại mức ảnh hưởng theo chính sách |
| Event name | `document.load.failed` | Truy vấn/đếm theo loại sự kiện ổn định |
| Request/correlation ID | `RQ-1042` | Nối log và request/tracing |
| Component | `DocumentService` | Biết thành phần phát sinh |
| Operation | `loadDocument` | Biết thao tác đang làm |
| Safe resource reference | ID đã được kiểm soát/mã hóa nếu được phép | Khoanh vùng sự cố mà không lộ thông tin |
| Exception type | `DocumentLoadException` | Nhóm nguyên nhân |
| Cause chain, stack trace | Theo quyền và chính sách bảo mật | Chẩn đoán vị trí, bản chất và đường lan lỗi |

**Log nội bộ không mặc nhiên là nơi an toàn tuyệt đối.** Log có thể được xuất sang dịch vụ bên thứ ba, lưu lâu, nhân bản qua môi trường hoặc được nhiều người truy cập. Không có chính sách nào cho phép tự do ghi mật khẩu, access token, cookie xác thực, private key, dữ liệu thanh toán hay thông tin cá nhân chỉ vì log có nhãn “internal”.

### Java built-in logging

JDK có `java.util.logging.Logger`. Trong một lớp có biến `logger` và exception `error`, có thể dùng:

~~~java
logger.log(
        java.util.logging.Level.SEVERE,
        "document.load.failed requestId=" + requestId,
        error);
~~~

Đây là **đoạn mã minh họa**, giả định `logger` đã được tạo, `requestId` là giá trị an toàn và `error` là `Throwable`. Overload `Logger.log(Level, String, Throwable)` ghi nhận exception để logger/handler định dạng chi tiết khi phù hợp. Nó có ích hơn chỉ ghép `error.getMessage()`, vì cause và stack trace không bị chủ động loại bỏ.

Tuy nhiên, logger/formatter có thể in message của toàn bộ cause chain, trong đó **có thể chứa secret**. Vì thế “truyền Throwable cho logger” phải đi cùng thiết kế bảo mật dữ liệu, cấu hình nơi lưu, quyền truy cập, masking và kiểm thử. Nếu exception bên thứ ba có khả năng chứa bí mật, cần một chính sách lọc/redact đáng tin cậy trước khi xuất dữ liệu, không chỉ dựa vào việc đổi public message.

### Với SLF4J hoặc logging framework khác

Một thư viện logging thông dụng có thể cung cấp overload tương tự:

~~~java
logger.error("document.load.failed requestId={}", requestId, error);
~~~

Đoạn này là **mã minh họa sử dụng API của SLF4J**, không phải Java SE standalone; cần dependency và cấu hình logging cụ thể. Mục đích là chỉ ra cách truyền đối tượng exception cho logger thay vì chèn stack trace trực tiếp vào thông báo cho client. Với mọi logger, phải kiểm tra đúng overload/phiên bản thư viện được sử dụng và cách backend format Throwable.

Trường `requestId` nên nằm trong structured context nếu công cụ hỗ trợ, thay vì mã hóa mọi dữ liệu thành một chuỗi khó truy vấn. Nhưng cấu trúc log không thay thế yêu cầu loại trừ dữ liệu nhạy cảm.

## 10. Correlation ID và việc liên kết hai phía

**Request ID** là một mã tham chiếu cho một yêu cầu. **Correlation ID** có thể theo suốt nhiều hoạt động hoặc nhiều dịch vụ liên quan. **Trace ID** thường gắn với hệ thống distributed tracing. Tên gọi khác nhau theo hạ tầng; không coi chúng luôn là cùng một khái niệm.

Luồng đơn giản:

~~~text
Client -> API nhận request RQ-1042
              |
              +--> Service: loadDocument
              |          |
              |          +--> Adapter: IOException
              |
              +--> Log event: document.load.failed
              |       requestId = RQ-1042
              |       internal Throwable / safe context
              |
              +--> Response:
                      code = DOCUMENT_UNAVAILABLE
                      message = Không thể tải tài liệu lúc này.
                      requestId = RQ-1042
~~~

Người dùng có thể báo “Mã tham chiếu RQ-1042” cho hỗ trợ; kỹ sư có quyền phù hợp tra cứu log theo cùng mã.

### Những nguyên tắc quan trọng

- Tạo hoặc chuẩn hóa ID tại một ranh giới đáng tin cậy. Không mặc định tin mọi header ID do client gửi và ghi nguyên vào log.
- Kiểm soát định dạng và độ dài của ID để tránh log injection, dữ liệu tùy ý hoặc các giá trị quá lớn.
- ID nên không chứa secret, access token, email hay thông tin có thể định danh người dùng nếu không cần thiết.
- Truyền ID qua các thành phần theo cơ chế rõ ràng. Trường log nào cũng cần nhận đúng ID của request hiện tại.
- Giữ quyền truy cập và thời gian lưu log phù hợp. Một ID công khai không phải cơ chế cấp quyền tra cứu dữ liệu nội bộ.

Khi dùng thread pool hoặc callback async, không giả định mọi `ThreadLocal` tự động đi theo tác vụ. Nếu thư viện hỗ trợ MDC, cần truyền context theo cách framework quy định, dọn sạch context trong `finally` khi trả thread về pool và tránh ghép nhầm request ID của người dùng khác. Java SE không tự cung cấp một cơ chế MDC thống nhất tương đương mọi framework logging.

## 11. Ghi log ở đâu để tránh lặp cùng một lỗi?

Một lỗi có thể đi qua nhiều tầng:

~~~text
Repository -> Service -> Controller/API mapper -> HTTP response
~~~

Nếu repository, service và controller đều gọi `logger.error(..., error)` rồi ném lại cùng exception, một request lỗi có thể tạo ba bản stack trace giống nhau. Hệ thống theo dõi có thể đếm nhầm đây là ba sự cố, làm nhiễu chẩn đoán và tăng chi phí log.

Một nguyên tắc thực dụng:

- **Tầng biết nguyên nhân và phục hồi được:** có thể xử lý hoặc ghi sự kiện phục hồi nếu có giá trị quan sát.
- **Tầng chỉ thêm ý nghĩa API:** chuyển exception với cause; không nhất thiết log toàn bộ stack trace ở đó.
- **Ranh giới chịu trách nhiệm báo thất bại cuối cùng:** ghi log theo chính sách một lần với request ID, loại lỗi, bối cảnh và Throwable phù hợp.
- **Hệ thống giám sát ngoài ứng dụng:** có thể nhận metric/trace theo policy, không mặc định ghi trùng mọi stack trace.

Không có quy định rằng mọi ứng dụng chỉ được log một lần trong mọi hoàn cảnh. Nếu các tầng thêm **thông tin độc lập và có giá trị**, nhiều sự kiện mức độ phù hợp có thể hợp lý. Nhưng cần tránh lặp log giống nhau không có ngữ cảnh mới.

**Lưu ý:** lỗi validation mà người dùng tự sửa được thường không nên log ở mức nghiêm trọng tương đương sự cố mất database. Mức severity phải phản ánh tác động và kỳ vọng vận hành, không chỉ việc có exception.

## 12. Giữ nguyên cause chain và suppressed exceptions cho chẩn đoán

Khi chuyển lỗi kỹ thuật sang ngoại lệ có ý nghĩa hơn:

~~~java
public final class InvoiceLoadException extends RuntimeException {
    public InvoiceLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là **lớp Java độc lập** nếu lưu trong tệp `InvoiceLoadException.java` và sử dụng trong ngữ cảnh cùng tên. Constructor hai tham số giúp giữ `getCause()` là đối tượng Throwable gốc.

Phân biệt:

- `getMessage()` của wrapper: bối cảnh của tầng trừu tượng hiện tại.
- `getCause()`: ngoại lệ gây ra lỗi, gồm type, message, stack trace của chính nó.
- `getSuppressed()`: những exception phụ được giữ lại khi cần, ví dụ lỗi đóng tài nguyên trong `try-with-resources`.
- `printStackTrace()`: hình thức hiển thị chuỗi nguyên nhân phục vụ debug có kiểm soát.

Nếu chỉ sao chép `original.getMessage()` rồi tạo ngoại lệ mới không có cause, bạn có thể mất stack trace và suppressed exceptions quan trọng. Nếu chỉ nối tên lớp/method vào public message để “có đủ thông tin”, bạn làm rò chi tiết triển khai mà vẫn không tạo ra một cause chain có cấu trúc.

**Không nên tái tạo một exception từ message gốc** nếu có thể truyền trực tiếp Throwable ban đầu. Kiểm thử có thể dùng `assertSame(original, translated.getCause())` để chắc chắn giữ cùng đối tượng.

Dù vậy, **việc giữ cause không đồng nghĩa có quyền công bố cause cho tất cả các đối tượng**. Ở public boundary, mã lỗi và message vẫn phải được ánh xạ riêng.

## 13. Những nguy cơ dữ liệu nhạy cảm trong log và error response

Dữ liệu có thể bị rò qua nhiều kênh:

1. **Message của ngoại lệ nguồn:** thư viện có thể chèn SQL, URL, tên file, response body hoặc header chứa token.
2. **Message wrapper do ứng dụng viết:** lập trình viên tự ghép toàn bộ request payload hoặc input chứa PII vào lỗi.
3. **Structured log fields:** trường `requestBody`, `email`, `sessionId` hay `Authorization` có thể bị log vô tình.
4. **Stack trace và cause chain:** có thể kèm message nhạy cảm ở bất cứ cấp nào.
5. **Monitoring/tracing metadata:** tag hoặc baggage có thể chứa identifier nhạy cảm nếu gắn tùy tiện.
6. **Thông báo người dùng:** màn hình, email, CLI, chatbot hỗ trợ hoặc API có thể làm lộ chi tiết nội bộ cho bên không có quyền.
7. **Log injection:** dữ liệu không tin cậy có newline, ký tự điều khiển hoặc payload dài có thể gây nhiễu định dạng log nếu không xử lý.

### Biện pháp giảm rủi ro

- **Không đưa secret vào exception message ngay từ đầu** khi có quyền kiểm soát lớp ném exception.
- Chỉ log các trường thật sự cần chẩn đoán, áp dụng quy tắc loại trừ/masking nhất quán cho PII, credential và nội dung nhạy cảm.
- Kiểm tra và cấu hình logger/formatter, export pipeline, tracing agent và chính sách retention.
- Phân quyền cho hệ thống log/tracing và có quy trình xử lý sự cố dữ liệu.
- Từ chối hoặc chuẩn hóa chuỗi không tin cậy dùng trong log/ID, tránh phụ thuộc vào việc cắt chuỗi thủ công trong từng catch.
- Viết kiểm thử với canary secret giả: chèn marker vào cause, assert payload công khai không chứa marker.
- Với public message, ưu tiên **mã và template đã duyệt** thay vì xử lý “lọc từ cấm” trên message kỹ thuật không có cấu trúc.

**Không có danh sách từ khóa cố định nào chứng minh một chuỗi đã sạch toàn bộ dữ liệu nhạy cảm.** Cách đáng tin cậy nhất là kiến trúc chỉ cho phép dữ liệu công khai được chọn theo contract, thay vì xuất dữ liệu kỹ thuật rồi cố loại bỏ các chuỗi nguy hiểm.

## 14. Lỗi dự kiến và lỗi bất ngờ nên có mức công khai khác nhau

### Validation: nêu phần cần sửa, không tiết lộ quá mức

Ví dụ một form nhập số lượng sản phẩm. Thông báo “Số lượng phải lớn hơn 0” là hữu ích và thường an toàn. Nhưng không cần in tên class `NumberFormatException`, vị trí `Integer.parseInt` hay request JSON đầy đủ. Nếu đầu vào là mật khẩu, OTP hoặc token, tuyệt đối không trả nguyên giá trị đã nhập.

### Nghiệp vụ: truyền đạt trạng thái chính xác

Ví dụ đặt chỗ hết hạn hoặc số dư không đủ. Đây có thể là trạng thái nghiệp vụ dự kiến; người dùng cần biết cách xử lý, và kỹ sư có thể không cần ERROR stack trace cho mỗi trường hợp nếu hệ thống coi đó là normal rejection.

Tuy nhiên, nếu một quy tắc nghiệp vụ liên quan thông tin người dùng khác, phải xem xét quyền hiển thị. Không công bố “tài khoản khác đang sở hữu tài nguyên” nếu đó là thông tin bị hạn chế.

### Sự cố hạ tầng: thông báo an toàn, không suy đoán

Lỗi timeout, DNS, JDBC, storage hoặc service dependency có thể khiến thao tác không hoàn thành theo kỳ vọng. Public message thường chỉ nên nói thao tác hiện không thể xử lý và cung cấp mã tham chiếu. Nếu thực sự chứng minh lỗi tạm thời, có thể hướng dẫn thử lại theo chính sách.

Đừng ngụ ý retry là luôn an toàn đối với thanh toán, gửi email, tạo đơn hàng hoặc tác vụ có side effect. Khi không biết kết quả cuối, nên yêu cầu kiểm tra trạng thái giao dịch bằng một mã/idempotency key hoặc theo luồng sản phẩm đã định.

### Lỗi lập trình: không đổ trách nhiệm cho người dùng

Một `NullPointerException` hoặc `IllegalStateException` bất ngờ trong server thường không phải lỗi input của người dùng. Public mapping không nên nói “Bạn nhập sai” chỉ vì thấy tên exception. Hãy báo lỗi hệ thống an toàn, đồng thời giữ thông tin chẩn đoán đầy đủ trong phạm vi bảo mật.

## 15. Xử lý ngoại lệ tại ranh giới API

Một ranh giới xử lý lỗi có thể gồm:

~~~text
try {
    result = service.perform(request);
    return successResponse(result);
} catch (KnownValidationException e) {
    return safeValidationResponse(e);
} catch (KnownBusinessException e) {
    return safeBusinessResponse(e);
} catch (RuntimeException e) {
    logUnexpectedFailureWithContext(e);
    return safeInternalErrorResponse();
}
~~~

Đây là **pseudocode minh họa**, không phải Java standalone. Trong dự án, các hàm cần được định nghĩa và phân quyền dữ liệu đầu ra. Phải xử lý exception có phạm vi cụ thể, không bắt `Throwable` rồi tự động biến cả `Error` nghiêm trọng thành một response thành công giả.

Nếu ứng dụng dùng Spring, Jakarta REST, Servlet hoặc framework khác, nơi xử lý lỗi cuối thường là exception mapper, controller advice, filter hoặc lớp middleware phù hợp. Tên hook và cơ chế cụ thể phụ thuộc framework; nguyên tắc **thông điệp công khai riêng với diagnostic nội bộ** không thay đổi.

### Khi nào không nên trả lỗi kỹ thuật cho bên gọi?

Nếu public API dành cho lập trình viên, **có thể** trả một số thông tin kỹ thuật đã được thiết kế thành contract (mã validation, trường sai, tham số được phép công bố). Điều cần tránh là vô tình trả thông tin triển khai không ổn định hoặc nhạy cảm như raw SQL, nội dung token, địa chỉ nội bộ, stack trace và exception class.

Nói cách khác, “public API cho developer” không đồng nghĩa “debug endpoint không giới hạn”. Debug information phải qua quyền truy cập và chính sách bảo mật riêng.

## 16. Kiểm thử: public payload, cause và logging policy

Một bộ kiểm thử tốt xác minh hai phía **độc lập**.

| Trường hợp | Điều phải kiểm chứng |
| --- | --- |
| Lỗi I/O có cause chứa chuỗi nhạy cảm | Public code/message không chứa chuỗi đó |
| Lỗi được chuyển tại service | `translated.getCause()` là cùng Throwable gốc |
| Validation có loại lỗi đã biết | Client nhận code và thông điệp đúng |
| Lỗi backend không khả dụng | Client nhận message an toàn, không nhận host/path |
| Lỗi bất ngờ | Client nhận lỗi hệ thống chung, không nhận stack trace |
| Request ID | Có cùng mã hợp lệ trong response và sự kiện chẩn đoán được phép |
| Normal success | Không tạo lỗi hoặc ghi ERROR không cần thiết |
| Nhiều request đồng thời | Context không bị lẫn request ID giữa các luồng |
| Exception có suppressed/cause chain | Hệ thống chẩn đoán có thể truy vết theo chính sách |
| Lỗi validation lặp đi lặp lại | Severity/metrics không tạo cảnh báo sự cố không cần thiết |

### JUnit 5 — kiểm tra không rò thông tin từ message gốc

Đoạn sau **chỉ minh họa trong test project có JUnit 5** và lớp `SafeErrorBoundaryDemo` được truy cập đúng phạm vi:

~~~java
IOException original = new IOException("password=canary-secret");
SafeErrorBoundaryDemo.DocumentLoadException internal =
        new SafeErrorBoundaryDemo.DocumentLoadException(
                "Lỗi tầng lưu trữ", original);

SafeErrorBoundaryDemo.PublicError response =
        SafeErrorBoundaryDemo.toPublicError(internal, "RQ-TEST");

assertSame(original, internal.getCause());
assertEquals("DOCUMENT_UNAVAILABLE", response.code());
assertFalse(response.message().contains("canary-secret"));
assertFalse(response.message().contains("password="));
assertEquals("RQ-TEST", response.requestId());
~~~

Đoạn code này cần import `java.io.IOException` và các static assertion từ `org.junit.jupiter.api.Assertions`. Nó không phải chương trình Java độc lập. Một kiểm thử sản phẩm đầy đủ nên serialize cả API response rồi assert **toàn bộ payload** không chứa marker; cũng cần kiểm tra các field validation và thông báo lỗi phát sinh từ nhiều adapter.

### Kiểm thử logging không nên đòi từng dòng stack trace cố định

Tên tệp, số dòng, vị trí class và format logger có thể đổi theo JDK, phiên bản dependency hoặc môi trường. Nên kiểm tra những phần có hợp đồng như event name, request ID, loại lỗi, cause identity và chính sách redaction. Nếu muốn kiểm tra log một cách có cấu trúc, dùng appender/test handler phù hợp thay vì phân tích một chuỗi console mong manh.

Một phép kiểm tra “không có password trong public response” **không bảo đảm log nội bộ cũng an toàn**. Cần test riêng phần logging/export đối với secret giả, quyền truy cập và trường nhạy cảm theo yêu cầu bảo mật.

## 17. Lỗi phổ biến và cách sửa

1. **Trả thẳng `e.getMessage()`:** thay bằng public error mapper có code/message theo hợp đồng.
2. **Trả `e.toString()`:** nó thường chứa tên class và message kỹ thuật, không phải văn bản dành cho người dùng.
3. **Trả nguyên stack trace:** giữ cho chẩn đoán được phân quyền; response chỉ chứa thông tin được cho phép.
4. **Gộp tất cả vào “Lỗi không xác định”:** phân loại các lỗi dự kiến để người dùng có hướng xử lý.
5. **Mọi lỗi đều 500 hoặc 200 với `success=false`:** với HTTP API, chọn status theo nghĩa hợp đồng thay vì che mất phân loại.
6. **Mọi `IllegalArgumentException` đều là lỗi người dùng:** cần phân biệt lỗi validation có chủ đích với bug server.
7. **Bỏ cause khi chuyển lỗi:** dùng constructor nhận `Throwable cause` để giữ stack trace/nguyên nhân.
8. **Chỉ ghi `e.getMessage()` vào log:** có thể mất cause chain; thiết kế log exception theo chính sách bảo mật.
9. **Ghi mọi Throwable và request body nguyên trạng:** có thể rò secret hoặc PII vào log bên thứ ba.
10. **Ghi stack trace ở mọi tầng:** gây log trùng, nhiễu cảnh báo và tăng chi phí.
11. **Đưa token hoặc email vào requestId:** tạo định danh công khai chứa dữ liệu nhạy cảm.
12. **Tin request ID không kiểm soát:** có thể gây log injection, nhầm tương quan hoặc dữ liệu quá dài.
13. **Không dọn MDC/ThreadLocal trong thread pool:** có thể trộn ngữ cảnh giữa các request.
14. **So sánh client logic bằng message tiếng Việt/tiếng Anh:** nên dựa vào code có cấu trúc.
15. **Hướng dẫn retry mọi lỗi:** có thể gây thao tác lặp đối với hoạt động có side effect.
16. **Thông báo “không tồn tại” khi chính sách không cho phép tiết lộ:** cần thiết kế quyền truy cập và public status.
17. **Đồng nhất public safety với che tất cả:** thông báo phải an toàn **và** đủ hữu ích.
18. **Cho rằng “log internal” nên không cần bảo mật:** log vẫn cần kiểm soát dữ liệu, retention, quyền truy cập và export.
19. **Bắt mọi `Throwable` để xuất 500:** có thể che `Error` nghiêm trọng và làm sai vòng đời ứng dụng.
20. **Chỉ test message mà không test response body hoàn chỉnh:** có thể rò bí mật từ một trường khác.

## 18. Checklist review trước khi phát hành

Trước khi đưa tính năng xử lý lỗi vào vận hành, hãy kiểm tra:

- Đã tách rõ exception/cause nội bộ với public error DTO chưa?
- Mỗi loại lỗi dự kiến đã có code ổn định và thông điệp phù hợp chưa?
- Có trường thông tin người dùng có thể hành động, thay vì một câu lỗi quá chung, khi được phép công bố không?
- HTTP status hoặc trạng thái API đã phản ánh đúng nguyên nhân/contract chưa?
- Có trường `requestId` an toàn giúp hỗ trợ đối chiếu log không?
- Error response có lộ stack trace, exception type kỹ thuật, SQL, path, hostname, token, body nhạy cảm hay không?
- Log có đủ thông tin để phân biệt lỗi và truy cause, nhưng vẫn đáp ứng chính sách bảo mật không?
- Có tránh ghi log cùng một exception nhiều lần khi các tầng chỉ ném tiếp không?
- Khi dùng thread pool/async, có truyền và dọn correlation context đúng cách không?
- Thông báo retry có phù hợp với tính idempotent và thực tế giao dịch chưa chắc đã thất bại không?
- Kiểm thử đã cấy secret giả vào cause/message và kiểm tra **toàn bộ public response** chưa?
- Lỗi dự kiến, lỗi hệ thống bất ngờ và nhánh thành công đều được kiểm thử riêng chưa?

**Kết luận:** Một exception của Java chứa thông tin phong phú để **kỹ sư chẩn đoán nguyên nhân**, nhưng không phải mọi thông tin đó đều phù hợp hoặc an toàn cho **người dùng**. Thiết kế tốt giữ cause và ngữ cảnh cần thiết tại tầng nội bộ được kiểm soát; tại ranh giới giao tiếp, nó chuyển lỗi thành code ổn định, thông báo dễ hiểu, an toàn và mã tham chiếu có thể tra cứu. Hai kênh phải hỗ trợ nhau mà không đánh đổi bảo mật hoặc khả năng điều tra.