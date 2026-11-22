# Tránh ghi dữ liệu nhạy cảm và đường dẫn nội bộ vào thông báo công khai trong Java I/O

## 1. Mục tiêu và tình huống

Ứng dụng Java thường đọc/ghi file bằng `Files`, `FileChannel`, `InputStream`, `OutputStream`, xử lý upload/download, tệp tạm, archive ZIP/JAR và tài nguyên của người dùng. Khi thao tác thất bại, exception có thể chứa **đường dẫn tuyệt đối trên server**, username hệ điều hành, tên tài liệu, storage key, endpoint hạ tầng, thậm chí một phần dữ liệu input. Nếu lấy nguyên `exception.getMessage()` hoặc stack trace làm nội dung HTTP response, UI, email, webhook hay message gửi khách hàng, thông tin không cần thiết có thể bị rò rỉ.

Ví dụ phản hồi **không nên công khai**:

```text
Could not read /srv/apps/prod/private/customers/42/tax-record.pdf
java.nio.file.AccessDeniedException:
    /srv/apps/prod/private/customers/42/tax-record.pdf
```

Phản hồi an toàn hơn:

```text
status=404
code=RESOURCE_UNAVAILABLE
message=Không thể truy cập tài nguyên được yêu cầu.
requestId=REQ-DEMO-001
```

Bài này giúp bạn:

1. Nhận diện thông tin nhạy cảm trong đường dẫn, exception, request và log.
2. Tạo lỗi công khai từ **allowlist** gồm status, mã lỗi, thông điệp ổn định và mã tương quan.
3. Xử lý `NoSuchFileException`, `AccessDeniedException`, `IOException` mà không phơi lộ chi tiết filesystem.
4. Tách public response với chẩn đoán/log nội bộ cũng phải được bảo vệ.
5. Tránh phản chiếu tên file upload, URL riêng, token, thông tin cá nhân hoặc raw payload.
6. Kiểm tra các đường rò rỉ gián tiếp qua framework error page, serializer, log/trace exporter.
7. Viết chương trình và bài test Java 17+ có stdout xác định.

Nguyên tắc quan trọng: **mục tiêu không phải che mọi lỗi**, mà là cho người dùng thông tin hữu ích trong phạm vi họ được phép biết, trong khi người vận hành vẫn có thể tra cứu sự cố qua một kênh được kiểm soát.

## 2. Thế nào là thông báo công khai?

Bất cứ nội dung nào người không có quyền vận hành nội bộ có thể đọc đều cần coi là bề mặt công khai hoặc bán công khai:

- HTTP API response body/header, GraphQL error, WebSocket message.
- Thông báo lỗi trên web, điện thoại, CLI được phân phối cho khách hàng.
- Email, SMS, notification, webhook gửi cho bên thứ ba.
- File export báo lỗi và trang hỗ trợ kỹ thuật.
- Browser console, client analytics SDK, trace/event exporter có quyền truy cập rộng.
- Trích dẫn log hoặc stack trace được dán vào issue/ticket chia sẻ.
- Trang lỗi mặc định của reverse proxy hoặc web framework.

**Log nội bộ không đương nhiên an toàn**. Log có thể tập trung về dịch vụ SaaS, được sao lưu nhiều năm, xuất sang đối tác hoặc hiện trong dashboard công khai do cấu hình sai. Vì vậy cần kiểm soát quyền truy cập, thời hạn lưu, mã hóa khi phù hợp và tối thiểu hóa dữ liệu ngay từ lúc tạo log.

## 3. Những dữ liệu dễ bị lộ qua I/O

| Loại | Ví dụ | Rủi ro |
| --- | --- | --- |
| Đường dẫn nội bộ | `/srv/prod/private/payroll/2026.csv` | Tiết lộ cấu trúc máy chủ, dữ liệu nghiệp vụ |
| Đường dẫn Windows | `C:\Users\svc\AppData\Local\...` | Tiết lộ tài khoản hệ thống, môi trường |
| UNC/network path | `\\fileserver\finance\salary.csv` | Tiết lộ tên host/share riêng |
| Storage URI | Bucket/key riêng, object-store URL chứa token | Lộ hạ tầng hoặc quyền truy cập |
| Secret | `Authorization`, API key, refresh token, mật khẩu | Có thể bị sử dụng truy cập trái phép |
| PII | Email, điện thoại, ID, họ tên gắn với filename | Lộ dữ liệu cá nhân |
| Nội dung tệp | Dòng CSV/JSON/XML gây lỗi parse | Có thể chứa cả dữ liệu nhạy cảm |
| Stack trace | Package, class, source line, cause | Tiết lộ chi tiết triển khai và vị trí lỗi |
| Query string/filename | Tên file upload, tham số client | Có thể chứa secret và dữ liệu do đối thủ kiểm soát |
| Diagnostics từ provider | Tên disk/mount, endpoint, reason | Lộ cấu hình vận hành |

Tên file chỉ là **basename** không có nghĩa vô hại: `hospital-result_Alice.pdf` vẫn có thể chứa dữ liệu cá nhân. Không hiển thị `Path.getFileName()` trừ khi thuộc tính display name đã được phê duyệt cho đúng đối tượng và đúng bối cảnh.

## 4. Exception của Java I/O không phải dữ liệu an toàn để phản chiếu

Ví dụ các loại cần hiểu:

- `NoSuchFileException` khi không thấy một `Path`.
- `AccessDeniedException` khi không đủ quyền truy cập.
- `FileAlreadyExistsException` nếu entry đích đã tồn tại.
- `FileSystemException` có `getFile()`, `getOtherFile()`, `getReason()`.
- `FileNotFoundException` với message thường chứa file path/hệ thống.
- `InvalidPathException` có thể chứa chuỗi input gây lỗi; đây là unchecked exception.
- `IOException` chung từ file, socket, ZIP, filesystem provider, cloud storage adapter.
- Lỗi parser khi đọc file có thể chứa đoạn nội dung sai định dạng.

Không có hợp đồng nào cho rằng `Throwable.getMessage()` đã xóa secret hoặc path. Cùng một thao tác có thể tạo thông điệp khác nhau giữa các OS/provider/JDK.

Anti-pattern (đoạn minh họa không độc lập):

```java
try {
    return Files.readString(path);
} catch (IOException ex) {
    // SAI nếu string này được gửi cho người dùng không có quyền:
    return "Không đọc được file " + path + ": " + ex.getMessage();
}
```

Các cách gián tiếp khác cũng có thể rò rỉ:

```java
exception.toString()
exception.getLocalizedMessage()
Arrays.toString(exception.getStackTrace())
path.toAbsolutePath().toString()
exception.printStackTrace(new PrintWriter(responseWriter))
```

Đây là biểu thức minh họa cần **tránh tại biên xuất thông tin**, không phải code độc lập. Stack trace có thể chứa nested causes và suppressed exceptions; dữ liệu lộ ra nhiều hơn message đầu tiên.

## 5. Tách public response khỏi thông tin chẩn đoán

Mẫu thiết kế:

```text
Files / Channel / FileStore / Parser
                |
             Exception
                |
       +--------+---------+
       |                  |
       v                  v
 Public Error Mapper   Internal Diagnostics
       |                  |
       v                  v
 PublicError DTO       Structured event
 status, code, msg      code, requestId,
 requestId              category, duration
       |                  |
       v                  v
 HTTP/UI/webhook         Log có quyền kiểm soát
 Không có Throwable      Không log raw secrets
```

Public DTO nên chứa **chỉ những trường được cho phép**. Không thêm các field như `Throwable cause`, `Path internalPath`, raw request hay `StackTraceElement[]` để serializer tự xử lý.

Một hợp đồng thường có:

```text
status:     500
code:       STORAGE_ERROR
message:    Không thể hoàn tất thao tác. Vui lòng thử lại.
requestId:  e.g. một UUID riêng của request
```

Message public giúp định hướng và không xác nhận thông tin ngoài quyền của người dùng. Mã lỗi phục vụ UI và support; requestId phục vụ đối chiếu với log có quyền truy cập. **Request ID không phải access token**, và người biết ID không được tự động xem log liên quan.

## 6. Chọn status/mã lỗi có chủ đích

| Điều kiện | Ví dụ status HTTP | Public code | Nội dung hiển thị |
| --- | --- | --- | --- |
| Resource không có/không thể truy cập theo chính sách | 404 | `RESOURCE_UNAVAILABLE` | Không thể truy cập tài nguyên. |
| Bị cấm và chính sách cho phép tiết lộ việc cấm | 403 | `ACCESS_DENIED` | Bạn không có quyền thực hiện thao tác. |
| Request sai schema/giá trị đầu vào | 400 | `INVALID_REQUEST` | Dữ liệu yêu cầu không hợp lệ. |
| Upload vượt giới hạn | 413 | `UPLOAD_TOO_LARGE` | Tệp vượt giới hạn cho phép. |
| Định dạng file không được hỗ trợ | 415/400 | `UNSUPPORTED_FILE_TYPE` | Định dạng tệp không được hỗ trợ. |
| Lỗi I/O nội bộ bất thường | 500 | `STORAGE_ERROR` | Không thể hoàn tất thao tác. |
| Dịch vụ lưu trữ tạm thời không hoạt động | 503 nếu phù hợp | `STORAGE_UNAVAILABLE` | Dịch vụ tạm thời không khả dụng. |

Đây là **bảng minh họa**, không phải quy tắc status áp dụng cho mọi API.

Trong hệ thống tài nguyên riêng, đôi khi cả “không tồn tại” và “không có quyền xem” đều cần trả **404 với cùng schema/message** để không tạo kênh dò sự tồn tại. Ngược lại, một API phục vụ người dùng đã được xác thực có thể chủ động dùng 403. Lựa chọn phải theo chính sách authorization và được áp dụng nhất quán, không chỉ làm đẹp nội dung.

Cần chú ý **side channel ngoài text**: sự khác biệt quá lớn về status, kích thước body hoặc độ trễ có thể làm lộ việc resource có tồn tại hay không. Không nên hứa đã che giấu hoàn toàn chỉ nhờ thay message.

## 7. Ví dụ chạy được: ánh xạ exception sang `PublicError` (Java 17+)

Lưu thành **`SafePublicErrorDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;

public class SafePublicErrorDemo {
    record PublicError(
            int status, String code, String message, String requestId) {
    }

    static PublicError map(Throwable error, String requestId) {
        if (error instanceof NoSuchFileException
                || error instanceof AccessDeniedException) {
            // Demo: tài nguyên riêng, không xác nhận sự tồn tại.
            return new PublicError(
                    404,
                    "RESOURCE_UNAVAILABLE",
                    "Không thể truy cập tài nguyên được yêu cầu.",
                    requestId);
        }

        if (error instanceof IllegalArgumentException) {
            return new PublicError(
                    400,
                    "INVALID_REQUEST",
                    "Dữ liệu yêu cầu không hợp lệ.",
                    requestId);
        }

        return new PublicError(
                500,
                "STORAGE_ERROR",
                "Không thể hoàn tất thao tác.",
                requestId);
    }

    private static void printSafe(Throwable error, String requestId) {
        PublicError result = map(error, requestId);
        System.out.println(result.status() + " | "
                + result.code() + " | "
                + result.message() + " | "
                + result.requestId());
    }

    public static void main(String[] args) {
        String id = "REQ-DEMO-001"; // cố định CHỈ cho ví dụ

        printSafe(new NoSuchFileException(
                "/srv/private/clients/42/contract.pdf"), id);

        printSafe(new AccessDeniedException(
                "/mnt/secure/reports/finance.csv"), id);

        printSafe(new IOException(
                "storage failed; token=DEMO_SECRET_DO_NOT_DISCLOSE"), id);

        printSafe(new IllegalArgumentException(
                "raw input=/internal/tmp/name.txt"), id);
    }
}
```

Chạy với JDK 17+ và terminal hỗ trợ UTF-8:

```bash
javac -encoding UTF-8 SafePublicErrorDemo.java
java SafePublicErrorDemo
```

Stdout khi thành công:

```text
404 | RESOURCE_UNAVAILABLE | Không thể truy cập tài nguyên được yêu cầu. | REQ-DEMO-001
404 | RESOURCE_UNAVAILABLE | Không thể truy cập tài nguyên được yêu cầu. | REQ-DEMO-001
500 | STORAGE_ERROR | Không thể hoàn tất thao tác. | REQ-DEMO-001
400 | INVALID_REQUEST | Dữ liệu yêu cầu không hợp lệ. | REQ-DEMO-001
```

**Giải thích:**

1. Exception chứa path/token **chỉ ở phía bên trong** object. Mapper không gọi `getMessage()` hoặc `toString()`.
2. Hai lỗi file riêng `NoSuchFileException` và `AccessDeniedException` được ánh xạ giống nhau, giảm nguy cơ tiết lộ trạng thái tồn tại.
3. `IOException` bất thường nhận mã `STORAGE_ERROR`, không phát tán nguyên nhân raw.
4. `record PublicError` có field cố định, không giữ `Throwable`.
5. `IllegalArgumentException` chỉ được dùng minh họa đầu vào sai. Trong ứng dụng thật, không nên ánh xạ **mọi** `IllegalArgumentException` thành lỗi client; lỗi lập trình nội bộ cũng có thể phát sinh loại này. Nên phân loại tại tầng nghiệp vụ bằng exception riêng.
6. ID cố định trong demo tạo stdout xác định; trong hệ thống thật hãy dùng ID server-generated theo từng request.

Ví dụ là **error mapping** thuần Java, chưa phải HTTP server. Nó không thay thế kiểm tra phân quyền trước thao tác đọc file.

## 8. Ví dụ chạy được: xử lý I/O thực và tách stdout/stderr

Lưu **`SafeFileReadDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class SafeFileReadDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("safe-file-");
        String requestId = "REQ-DEMO-002";

        try {
            Path internalPath = directory.resolve("private-record.txt");

            try {
                Files.readString(internalPath);
                System.out.println("status=200");
            } catch (NoSuchFileException ex) {
                // Diagnostic: chỉ các trường cho phép,
                // không in ex, ex.getMessage(), ex.getFile().
                System.err.println(
                        "event=FILE_READ_FAILED"
                        + " type=NoSuchFileException"
                        + " requestId=" + requestId);

                // Public response giả lập.
                System.out.println("status=404");
                System.out.println("code=RESOURCE_UNAVAILABLE");
                System.out.println(
                        "message=Không thể truy cập tài nguyên được yêu cầu.");
                System.out.println("requestId=" + requestId);
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeFileReadDemo.java
java SafeFileReadDemo
```

**Stdout** khi đọc file không tồn tại:

```text
status=404
code=RESOURCE_UNAVAILABLE
message=Không thể truy cập tài nguyên được yêu cầu.
requestId=REQ-DEMO-002
```

**Stderr** khi cùng thao tác thất bại:

```text
event=FILE_READ_FAILED type=NoSuchFileException requestId=REQ-DEMO-002
```

Hai dòng output nằm trên hai luồng khác nhau; IDE/terminal có thể trộn chúng với thứ tự khác nhau nếu hiển thị chung. Nếu stderr được chuyển cho bên ngoài, nó **cũng là kênh công khai**; dùng một hệ thống log có chính sách bảo vệ, không chỉ dựa vào tên stdout/stderr.

Ở đây chương trình tự tạo thư mục mới và cố ý đọc một file chưa tạo, nên `NoSuchFileException` là kết quả dự kiến trong môi trường bình thường. Path tuyệt đối và tên tệp không xuất hiện vì code không in object `internalPath` hoặc exception. Nếu I/O gặp lỗi khác không được bắt, `main` vẫn có thể in stack trace: **server thật bắt buộc có error boundary** chuyển lỗi chưa biết thành public response an toàn, thay vì để runtime tự gửi stack trace ra HTTP.

## 9. Diagnostic logs cũng cần thiết kế allowlist

Log nội bộ có thể hỗ trợ hỗ trợ kỹ thuật, nhưng điều đó không cho phép ghi mọi dữ liệu tùy ý.

**Cách dễ tạo rò rỉ:**

```java
logger.log(Level.SEVERE,
        "Read failed: " + path + " / " + exception.getMessage(),
        exception);
```

Đây là snippet **anti-pattern trong hệ thống log truy cập rộng**. Nó có thể gửi path, message, cause và stack trace sang mọi sink do logger cấu hình. Không có nghĩa tất cả việc ghi stack trace đều bị cấm trong mọi môi trường; cần phân tầng và đánh giá chính sách thông tin.

**Cách kiểm soát trường log hơn:**

```java
logger.log(Level.WARNING,
        "event={0} requestId={1} errorCategory={2}",
        new Object[] {
                "FILE_READ_FAILED",
                requestId,
                "NOT_FOUND_OR_DENIED"
        });
```

Snippet này giả định các biến/logger được khởi tạo. Các field đến từ danh mục cố định, không từ `exception.getMessage()`. Nếu cần stack trace trong một kênh riêng được bảo vệ, phải có quyền truy cập hạn chế, thời hạn lưu và chính sách kiểm tra secret/PII. Một logger gọi là “internal” không thay đổi bản chất dữ liệu nếu nó xuất ra dashboard công khai.

| Field có thể cho phép | Ví dụ | Cảnh báo |
| --- | --- | --- |
| `eventCode` | `FILE_READ_FAILED` | Dùng danh mục cố định |
| `requestId` | UUID kiểm tra hợp lệ | Không mã hóa ID khách hàng/path |
| `operation` | `READ_RESOURCE` | Không ghi raw query/path |
| `errorCategory` | `NOT_FOUND_OR_DENIED` | Không lộ chi tiết quyền riêng |
| `serviceCode` | `DOCUMENT_SERVICE` | Chỉ dùng tên được phép |
| `durationBucket` | `under_100ms` | Tránh dữ liệu không cần thiết |
| `publicErrorCode` | `RESOURCE_UNAVAILABLE` | Dùng cùng mã response |

Không đưa file path, email, token hoặc raw filename thành label của metrics. Điều này gây rủi ro lộ dữ liệu, tăng số giá trị label (*cardinality*) và làm hệ thống giám sát khó vận hành.

## 10. `requestId`: truy vết mà không công khai bí mật

Mã request giúp nhân viên hỗ trợ tra log đúng sự cố mà không yêu cầu người dùng chụp màn hình stack trace.

Nguyên tắc:

1. Tạo ID ở server, ví dụ `UUID.randomUUID().toString()`, hoặc dùng trace ID từ cơ chế đã được kiểm soát.
2. Không ghép `userId + path + token` thành ID và không xuất giá trị hash từ một secret thấp entropy như thể chắc chắn vô hại.
3. Không coi request ID là bằng chứng người dùng có quyền đọc toàn bộ log.
4. Nếu nhận `X-Request-ID` từ client, kiểm tra chiều dài, charset, ký tự điều khiển và chính sách trust; nếu không tin cậy, tự tạo ID.
5. Bảo vệ hệ thống tra cứu log bằng xác thực/authorization; biết request ID **không đủ** để được xem chẩn đoán nội bộ.
6. Không dùng ID cố định của ví dụ trong production.

Snippet:

```java
String requestId = java.util.UUID.randomUUID().toString();
```

Vì ID thực tế ngẫu nhiên, không thể viết stdout cố định cho một chương trình sinh ID mới ở mỗi lần chạy. Hai ví dụ trước dùng `REQ-DEMO-...` chỉ để thuận tiện đối chiếu output.

## 11. Tên file upload không phải dữ liệu tin cậy

Tên file do client gửi có thể chứa path cục bộ hoặc PII:

```text
C:\Users\Alice\Documents\medical-result.pdf
customer-123456789-bank-statement.pdf
../private/secret.txt
```

Không dùng chuỗi này trực tiếp làm đường dẫn lưu trên server hoặc in vào error log public. Các vấn đề bao gồm:

- Path traversal, separator khác nhau giữa Windows/Unix.
- Trùng tên file, cố ý ghi đè.
- Chuỗi rất dài hoặc ký tự điều khiển dùng cho log/header injection.
- Thông tin cá nhân được người dùng đặt trong tên file.
- Nội dung file giả mạo extension hoặc MIME type.

Một chính sách thực dụng:

- Server tạo **storage key** độc lập tên gốc, có đủ tính duy nhất.
- Kiểm tra giới hạn byte upload, loại file thực tế, quyền sở hữu resource.
- Lưu **display name** riêng khi nghiệp vụ thực sự cần; chỉ hiển thị nó cho người được phép.
- Không đưa path lưu file vào HTTP response hoặc URL kiểu file nội bộ.
- Xử lý download header `Content-Disposition` bằng thư viện hỗ trợ encoding/validation phù hợp, không nối raw string chứa CR/LF.

Snippet minh họa, chưa phải upload handler hoàn chỉnh:

```java
String storageKey = java.util.UUID.randomUUID().toString();
Path destination = controlledUploadRoot.resolve(storageKey);
```

`controlledUploadRoot` phải do server sở hữu, có quyền filesystem/sandbox phù hợp. Cần thêm chiến lược ngăn symlink race, kiểm soát dung lượng/quota, scan theo chính sách và xử lý file lỗi/partial write.

## 12. Không tin rằng `normalize()` đã giải quyết bảo mật path

Trong Java NIO, `Path.normalize()` loại bỏ các thành phần đường dẫn cú pháp như `.` và `..`; `toAbsolutePath()` tạo dạng tuyệt đối dựa trên môi trường. Hai lệnh này **không tự xác minh authorization**, không ngăn mọi trường hợp symbolic link/race và không chứng minh file nằm trong root thực được phép.

Ví dụ khi phục vụ download từ resource ID:

```text
request resourceId
        |
        v
authenticate user
        |
        v
authorize resourceId (domain policy)
        |
        v
map ID to server-owned storage key/path
        |
        v
open/read with controlled filesystem permissions
        |
        v
return bytes or safe public error DTO
```

Không dùng raw path do client cung cấp làm chứng cứ quyền truy cập. Nếu ứng dụng xử lý path trong thư mục đối thủ có thể sửa, cân nhắc cơ chế directory handle/phân quyền thích hợp; `SecureDirectoryStream` chỉ dùng khi provider hỗ trợ và còn cần thiết kế chống race tương ứng.

Ẩn path khỏi lỗi là một phần **giảm lộ thông tin**, không thay thế bảo vệ truy cập file thật.

## 13. Các nguồn rò rỉ gián tiếp

Ngay cả khi service đã không trả `ex.getMessage()`, một lớp khác có thể làm lộ:

- Default error page bật debug với `trace` hoặc `exception`.
- JSON serializer gặp DTO có field `Throwable`.
- HTTP filter thêm `X-Error-Detail` nguyên nhân lỗi.
- Middleware phản chiếu query string hoặc upload filename.
- Tracing SDK gửi raw request/exception đến bên thứ ba.
- UI hiển thị nguyên error body từ HTTP client.
- Email hỗ trợ đính kèm toàn bộ server log.
- Structured log exporter đưa raw `path` vào dashboard truy cập rộng.

Cần có **error boundary tập trung** cho mọi exception chưa được phân loại. Dùng response schema allowlist, kiểm tra các HTTP header, tắt trang debug ngoài development, kiểm tra error handler ở framework và hạn chế dữ liệu logging/tracing. Một status 500 không tự bảo vệ nội dung của body.

## 14. Redaction hỗ trợ, nhưng không phải tấm chắn duy nhất

**Redaction** loại bỏ hoặc thay thế một số field như `Authorization`, token hay PII. Khi buộc phải nhận một object raw, có thể redact các trường theo schema trước khi log.

Tuy nhiên regex trên một message bất kỳ không phải chính sách bảo mật hoàn chỉnh:

```java
String sanitized = message.replaceAll(
        "token=[^ ]+", "token=[REDACTED]");
```

Snippet trên **không đủ an toàn** khi token có xuống dòng, encoding, dấu phân cách khác hoặc nằm trong `cause`; path Windows/Unix, JSON/XML và thông tin cá nhân không có một mẫu tổng quát đáng tin.

Thứ tự ưu tiên:

1. Không tạo field public từ raw exception ngay từ đầu.
2. Chọn status/code/message từ bảng cố định.
3. Tối thiểu hóa field log bằng allowlist.
4. Redact những trường bắt buộc phải xử lý ở tầng riêng, kèm kiểm thử.
5. Kiểm soát truy cập log, retention, encryption và nơi xuất.
6. Kiểm tra lại sau thay đổi thư viện/framework vì một error serializer có thể thêm trường mới.

Nếu một hàm tên `sanitize()` được dùng khắp nơi, nó vẫn phải được đánh giá theo dữ liệu đầu vào và đường xuất; **tên hàm không phải bằng chứng chống rò rỉ**.

## 15. Log injection từ nội dung client

Một filename hoặc request ID chưa kiểm soát có thể chứa ký tự xuống dòng:

```text
report.pdf
ERROR admin access granted
```

Nếu hệ thống nối chuỗi trực tiếp vào log, kẻ tấn công có thể tạo bản ghi giả. Đối sách:

- Không log raw input không cần thiết.
- Ưu tiên structured logging có escaping/encoding đúng format.
- Giới hạn độ dài và loại bỏ/kiểm tra các ký tự điều khiển theo policy.
- Không chấp nhận request ID tùy ý từ client nếu không có quy tắc kiểm tra.
- Phân biệt server-generated fields với user-provided fields.
- Giới hạn số lượng event/log và có backpressure tránh log flooding.

`requestId` cố định/được kiểm soát và `eventCode` từ enum thường dễ bảo vệ hơn concatenation của mọi chi tiết request.

## 16. Kiểm thử public error bằng dữ liệu mồi nhạy cảm

Một test tốt chủ động tạo exception có chứa path/token giả, sau đó assert những chuỗi đó **không xuất hiện trong public output**. Không kiểm thử chỉ đường đi thành công.

Tạo **`PublicErrorContractTest.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import java.util.List;

public class PublicErrorContractTest {
    record PublicError(int status, String code, String message) {
        @Override
        public String toString() {
            return status + "|" + code + "|" + message;
        }
    }

    static PublicError map(Throwable error) {
        if (error instanceof NoSuchFileException
                || error instanceof AccessDeniedException) {
            return new PublicError(404, "RESOURCE_UNAVAILABLE",
                    "Tài nguyên không khả dụng.");
        }
        return new PublicError(500, "STORAGE_ERROR",
                "Không thể hoàn tất thao tác.");
    }

    public static void main(String[] args) {
        String privatePath = "/var/private/billing/customer-42.csv";
        String secretToken = "API_TOKEN_TEST_ONLY_123";

        List<Throwable> errors = List.of(
                new NoSuchFileException(privatePath),
                new AccessDeniedException(privatePath),
                new IOException("token=" + secretToken),
                new IllegalStateException(
                        "source path=" + privatePath));

        int passed = 0;
        for (Throwable error : errors) {
            String text = map(error).toString();
            if (text.contains(privatePath)
                    || text.contains(secretToken)
                    || text.contains("/var/private")
                    || text.contains(error.getClass().getName())) {
                throw new AssertionError("Sensitive detail leaked");
            }
            passed++;
        }

        System.out.println("passed=" + passed);
    }
}
```

```bash
javac -encoding UTF-8 PublicErrorContractTest.java
java PublicErrorContractTest
```

Stdout khi thành công:

```text
passed=4
```

Bài test này là **kiểm tra hợp đồng tối thiểu**, không chứng minh toàn bộ server an toàn. Trong thực tế cần test response JSON/headers/body mà framework thực sự xuất, telemetry/log sink, nested causes, Windows/Unix paths, URI, token, Unicode, control characters, user content trong archive và lỗi bất ngờ từ middleware.

### Checklist kiểm thử theo loại lỗi

| Tình huống | Dữ liệu mồi | Điều kiện kiểm tra |
| --- | --- | --- |
| File không tồn tại | Path riêng | Không có path trong response |
| File bị từ chối | `AccessDeniedException` có path | Không lộ tên file/quyền nội bộ |
| I/O bất thường | `IOException` chứa token mồi | Token không xuất ở response/log công khai |
| Input sai | Filename có `../` | Không phản chiếu raw name |
| Upload quá lớn | Tên file chứa email | Chỉ hiển thị code/giới hạn phù hợp |
| Parser lỗi | Dòng CSV chứa PII giả | Không hiện nội dung file |
| Nested cause | Exception chain có path | Serializer không lộ cause/stack |
| Header injection | ID chứa CR/LF | ID bị từ chối hoặc thay thế |
| Logging | Token trong request body | Không ghi vào sink truy cập rộng |

## 17. Phân tầng trách nhiệm

Một kiến trúc dễ kiểm soát gồm:

**File adapter / repository:** biết `Path`, `Files`, `FileChannel` và nguyên nhân I/O thật. Không tự quyết định public message.

**Service nghiệp vụ:** phân loại lỗi theo quyền người dùng, resource và ngữ nghĩa. Quyết định trường hợp nào nên trả 403, trường hợp nào 404 để hạn chế enumeration.

**API boundary:** bắt lỗi đã phân loại và lỗi chưa biết, tạo `PublicError` chỉ có status/code/message/requestId allowlisted. Không đưa `Throwable` trực tiếp vào serializer.

**Diagnostic logging:** ghi event và ID có kiểm soát; audit log riêng nếu cần, với phân quyền và retention. Thông tin chi tiết chỉ được phép theo chính sách bảo vệ rõ ràng.

**Security tests và monitoring:** kiểm tra đường lỗi thật, hệ thống log/exporter và cấu hình framework sau deploy. Không chỉ test một hàm xử lý exception đơn lẻ.

## 18. Những lỗi thiết kế phổ biến

1. Trả `IOException.getMessage()` trực tiếp cho người dùng.
2. Nối `Path.toAbsolutePath()` vào thông báo 404.
3. Serialize `Throwable` hoặc `StackTraceElement[]` trong DTO.
4. Hiển thị trang debug lỗi 500 ở production.
5. Ghi toàn bộ request body/header `Authorization` vào log khi lỗi parser.
6. Để raw filename upload thành server path hoặc log public.
7. Tin rằng `getFileName()` loại hết PII.
8. Phân biệt 403/404 không nhất quán trên resource bí mật, gây enumeration.
9. Dùng error code chứa internal path/storage key.
10. Tạo request ID từ user identifier, filename hoặc secret.
11. Cho người biết request ID xem log mà không authorization.
12. Dùng một regex redaction rồi coi tất cả an toàn.
13. Chưa xử lý CR/LF và log injection từ input.
14. Chỉ kiểm tra controller, bỏ qua middleware, header và serializer.
15. Coi stderr, tracing dashboard hoặc ticket support là kênh không bao giờ công khai.
16. Ghi email/PII thành label metrics, gây rò rỉ và high-cardinality.
17. Dựa vào `Path.normalize()` để thay authorization/symlink safety.
18. Không kiểm tra lỗi chưa dự kiến và stack trace tự động của framework.

## 19. Bài tập thực hành

**Bài A — sửa anti-pattern.** Thay mã sau bằng một public DTO không chứa path/message:

```java
catch (IOException ex) {
    return "Failed: " + path + " / " + ex.getMessage();
}
```

**Bài B — resource bí mật.** Hãy thiết kế phản hồi cho hai trường hợp cùng một ID: không tồn tại và không có quyền xem. Khi nào bạn chọn cùng một 404? Làm sao đảm bảo phép kiểm tra quyền vẫn được thực thi?

**Bài C — filename chứa PII.** Khách hàng tải lên tệp tên chứa họ tên và thông tin y tế. Tại sao tên này không nên dùng trong log công khai? Tạo một storage key phía server và một display name có chính sách riêng.

**Bài D — error serializer.** Một framework trả JSON có `message` và `trace` từ exception. Tạo DTO chỉ có `status`, `code`, `message`, `requestId`; test trên response thực.

**Bài E — chống log injection.** Client gửi request ID chứa dấu xuống dòng và chuỗi giả mạo log. Hãy mô tả cách giới hạn độ dài/charset hoặc thay bằng ID server-generated.

**Bài F — kiểm thử đa nền tảng.** Thêm dữ liệu mồi path Windows, path Linux, UNC path, URL riêng, token và tên file Unicode vào test; đảm bảo không xuất chuỗi đó ở response.

## 20. Tài liệu tham khảo

- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): `getFile()`, `getOtherFile()`, `getReason()`.
- [Java SE 17 — NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html).
- [Java SE 17 — AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html).
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html).
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

## 21. Ghi nhớ

Thông báo công khai cần trả lời **người dùng có thể làm gì tiếp**, không phản chiếu hệ thống lưu file ở đâu, tài nguyên riêng có tồn tại hay không, hoặc token/request payload nào gây ra exception. `NoSuchFileException`, `AccessDeniedException`, `FileSystemException`, `IOException` có thể chứa path, message OS và nested causes; không đưa raw exception vào UI/HTTP/email/webhook.

Mô hình đúng là **lỗi I/O → phân loại và kiểm tra quyền → ánh xạ status/code/message từ allowlist → thêm requestId an toàn → ghi diagnostic có kiểm soát → kiểm thử các nhánh thất bại**. Log, telemetry và thông báo hỗ trợ cũng cần được bảo vệ. Việc ẩn path trong một catch block chỉ là một bước; an toàn thực tế cần phân quyền, kiểm soát dữ liệu xuất ra, chống injection, chính sách log và test hệ thống.
