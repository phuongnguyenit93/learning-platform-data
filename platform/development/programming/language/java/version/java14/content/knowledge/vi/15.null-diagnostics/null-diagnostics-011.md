# Kiểm soát thông tin nội bộ khi lỗi chẩn đoán null được đưa ra ngoài ứng dụng

## 1. Bối cảnh: Helpful NullPointerExceptions hữu ích nhưng có ranh giới bảo mật

Khi Java gặp một thao tác dùng `null` như gọi phương thức, đọc trường instance hoặc truy cập phần tử mảng, JVM có thể phát sinh `NullPointerException` (NPE). Từ **Java 14, JEP 358 — Helpful NullPointerExceptions**, thông báo của NPE do JVM tạo có thể mô tả cụ thể **thao tác nào không thành công** và **biểu thức nào dẫn tới tham chiếu null**, thay vì chỉ một dòng `java.lang.NullPointerException` chung chung.

Ví dụ, một thông báo phụ thuộc bytecode/JDK có thể trông giống:

```text
Cannot read field "email" because "order.customer" is null
```

Thông báo này **hữu ích trong môi trường chẩn đoán được kiểm soát**. Nhưng nếu ứng dụng gửi thẳng `exception.getMessage()`, `exception.toString()` hoặc stack trace ra HTTP response, màn hình lỗi, webhook hay thông báo cho người dùng, bên ngoài có thể nhìn thấy tên trường, kiểu, method, package, cấu trúc truy cập, thậm chí thông tin riêng từ các ngoại lệ khác.

**Mục tiêu bảo mật:** giữ thông tin chẩn đoán ở kênh **nội bộ có quyền truy cập và chính sách bảo vệ phù hợp**, còn người dùng/API client chỉ nhận **mã lỗi ổn định, trạng thái phù hợp, thông điệp đã duyệt và mã tham chiếu không nhạy cảm**. Không biến thông điệp debug thành hợp đồng API.

**Special Note về kiến thức hiện hành:** JEP 358 là tính năng được giới thiệu trong Java 14 và **vẫn dùng trong Java hiện đại**. Từ **JDK 15**, tùy chọn `ShowCodeDetailsInExceptionMessages` được bật theo mặc định trên HotSpot; vì vậy khi chạy Java 17+, phải giả định rằng NPE do VM sinh ra **có thể chứa chi tiết**. Bài dùng cú pháp và thư viện **Java 17+**, không giới thiệu cơ chế preview hoặc API đã lỗi thời.

Sau bài học, bạn sẽ:

1. Biết vì sao Helpful NPE có thể làm lộ thông tin nội bộ qua bề mặt ứng dụng.
2. Phân biệt `getMessage()`, `toString()` và stack trace, cùng giới hạn của cờ JVM liên quan.
3. Xây dựng **error boundary** để map ngoại lệ thành phản hồi công khai an toàn.
4. Dùng mã lỗi, HTTP status và correlation/reference ID mà không gửi chi tiết implementation.
5. Giữ log nội bộ hữu ích nhưng tránh lưu mật khẩu, token, PII, request body nhạy cảm.
6. Kiểm tra hành vi bằng ví dụ Java 17+ có thể biên dịch/chạy và các bài kiểm thử chống information disclosure.

## 2. Điều gì được tiết lộ bởi một ngoại lệ?

### 2.1. `Throwable.getMessage()`

`exception.getMessage()` là chuỗi mô tả của ngoại lệ. Với NPE do JVM tự phát sinh và tính năng Helpful NPE được bật, nó **có thể** mang thông tin phân tích từ bytecode về đường đi đến `null`. Với ngoại lệ được tạo tường minh như `new NullPointerException("missing config.key")`, chuỗi được người viết mã cung cấp có thể chứa **bất kỳ dữ liệu nào họ đã đưa vào**, kể cả nội dung nhạy cảm.

Các ví dụ về metadata có thể bị lộ:

- Tên trường: `customer`, `credentials`, `profile`, `email`, `tokenProvider`.
- Tên phương thức hoặc kiểu, ví dụ tên DTO, mapper, service, helper.
- Hình dạng chuỗi truy cập: bộ phận nào đang null trong object graph.
- Thông tin từ exception khác như đường dẫn file, câu SQL, endpoint nội bộ hoặc dữ liệu input khi code/library tự đưa chúng vào message.

**Không nên khẳng định rằng Helpful NPE tự động in ra giá trị mật khẩu hoặc toàn bộ object.** JEP 358 chủ yếu mô tả **thao tác và access path**; mức chi tiết phụ thuộc bytecode, JVM, thông tin debug và trường hợp phát sinh. Tuy nhiên, *tên nội bộ* tự nó đã có thể hữu ích cho người dò hệ thống; còn việc sao chép nguyên văn **các loại exception khác** có nguy cơ lộ dữ liệu trực tiếp cao hơn.

### 2.2. `exception.toString()`

Theo cơ chế của `Throwable`, `toString()` thường chứa **tên lớp ngoại lệ** và chuỗi `getMessage()` nếu có. Vì vậy:

```java
String message = exception.toString();
```

**Không an toàn hơn** so với gửi `getMessage()` ra ngoài. Nó còn bổ sung tên kiểu lỗi như `java.lang.NullPointerException` hoặc exception class nội bộ. Đoạn trên là **snippet**; `exception` là một biến `Throwable` trong phương thức.

### 2.3. Stack trace

Stack trace có thể chứa package/class/method, file source, line number, và chuỗi nguyên nhân. Nó rất hữu ích cho người vận hành khi được đặt ở kênh an toàn, nhưng **không được gửi nguyên bản cho client không có quyền chẩn đoán**.

Tránh trả:

```java
// SAI tại ranh giới public API (mã minh họa).
return exception.getMessage();
```

hoặc:

```java
// SAI: in trực tiếp stack vào HTTP response body.
exception.printStackTrace(responseWriter);
```

Hai đoạn trên là minh họa kiểu anti-pattern, **không phải chương trình độc lập**; `responseWriter` biểu thị writer của response. Đừng chỉ giấu stack trace trong giao diện frontend: client vẫn có thể xem raw response qua browser network tab hoặc gọi API trực tiếp.

### 2.4. Ngoại lệ qua nhiều kênh

Thông tin nội bộ có thể thoát ra ở nhiều nơi hơn một trang HTML:

| Kênh | Ví dụ thất thoát | Biện pháp |
| --- | --- | --- |
| HTTP REST/GraphQL | `message`, `debug`, `stackTrace`, `extensions.exception` | Handler chung với allowlist schema và filter thông tin |
| HTML error page | Trang 500 có stack trace và tên server | Error page an toàn, tắt debug detail công khai |
| WebSocket/SSE | Event lỗi kèm `cause.toString()` | Mã lỗi công khai đã duyệt, không gửi stack |
| Webhook/queue response | Payload ném lại cause từ service | Tách payload công khai khỏi chẩn đoán worker |
| Ứng dụng mobile | SDK nhận raw exception từ backend | Hợp đồng lỗi ổn định, không truyền nội dung nội bộ |
| Email/ticket tự động | Toàn bộ lỗi/PII trong nội dung gửi ra | Template đã kiểm duyệt và quyền truy cập |
| Log/telemetry/analytics | Header `Authorization`, cookies, stack, PII | Giảm dữ liệu, phân quyền, masking, retention |
| Proxy/API gateway | Upstream body thô bị chuyển tiếp | Cấu hình tầng biên và test đường lỗi thực tế |

Ranh giới bảo mật là **từng nơi thông tin đi từ vùng tin cậy cao sang vùng tin cậy thấp**. Không nên cho rằng vì một dịch vụ nội bộ an toàn thì việc chuyển toàn bộ cause sang service khác hoặc bên thứ ba cũng an toàn.

## 3. Vì sao Java 14+ cần đặc biệt chú ý Helpful NPE?

JEP 358 cải thiện khả năng chẩn đoán NPE do VM sinh ra bằng cách phân tích bytecode tại điểm xảy ra lỗi, nhưng **không thay đổi nguyên tắc bảo mật**: ngoại lệ là dữ liệu chẩn đoán nội bộ, không phải JSON công khai.

### 3.1. Cờ JVM điều khiển chi tiết do VM sinh ra

Các tùy chọn JVM trên HotSpot:

```bash
# Bật phần mô tả NPE do VM sinh ra:
java -XX:+ShowCodeDetailsInExceptionMessages -cp out HelpfulNpeDemo

# Tắt phần mô tả NPE do VM sinh ra:
java -XX:-ShowCodeDetailsInExceptionMessages -cp out HelpfulNpeDemo
```

Theo Oracle JDK 15 release notes, `ShowCodeDetailsInExceptionMessages` đã được bật mặc định từ JDK 15. Với JDK hiện đại, **đừng giả định `getMessage()` của một VM-thrown NPE là null**.

**Giới hạn bảo vệ của cờ này:**

- Nó kiểm soát **thông điệp Helpful NPE do VM tạo**, không phải giải pháp phân quyền HTTP.
- Nó không xóa mọi stack trace, tên class, dòng source trong các cách in ngoại lệ.
- Nó **không xóa** thông điệp được tạo tường minh bằng `new NullPointerException("...")` hoặc thông điệp từ các exception khác.
- Runtime có thể có khác biệt triển khai, thời điểm sinh thông điệp và mức dữ liệu debug; kiểm thử trên JDK thực tế.
- Dù cờ tắt, ứng dụng vẫn **không được** trả raw exception/stack trace cho bên ngoài.

Cách dùng đúng: coi việc vô hiệu hóa chi tiết JVM (nếu chính sách vận hành yêu cầu) như **biện pháp phòng vệ bổ sung**, không thay cho kiểm soát ở **error boundary**.

### 3.2. Không dựa vào chính xác văn bản Helpful NPE để viết logic

Thông điệp là chi tiết chẩn đoán phụ thuộc JVM/bytecode. Tránh code kiểu:

```java
// SAI: phân loại bằng cách parse văn bản lỗi nội bộ.
if (ex.getMessage().contains("order.customer")) {
    return "INVALID_CUSTOMER";
}
```

Không chỉ có nguy cơ `getMessage() == null`, mà code còn phụ thuộc tên trường và dạng văn bản do VM tạo, có thể thay đổi khi refactor. Hãy phân loại bằng **loại ngoại lệ/domain error code được thiết kế rõ**. NPE phát sinh bất ngờ trong backend thông thường cần được ghi nhận là **lỗi server**, không tự động được chuyển thành lỗi nhập liệu của client.

### 3.3. NPE có thể là lỗi lập trình hoặc dữ liệu, nhưng luôn cần ranh giới

Nếu `customer` null do bug ở mapper/service, việc trả tên `customer` cho bên ngoài không giúp client sửa input đúng cách. Nếu client thực sự thiếu field bắt buộc, hãy **validate ở đầu vào** và trả một thông báo công khai có thể hành động, ví dụ `"Field 'email' is required."` (chỉ nêu tên trường **đã thuộc contract public**).

Đừng để NPE vô tình quyết định HTTP status hoặc nội dung trả về. Lỗi validation có chủ đích khác lỗi lập trình không lường trước.

## 4. Phân tách rõ ba lớp thông tin

Thiết kế phản hồi lỗi bền vững tách:

1. **Public error contract:** HTTP status, `code`, thông điệp đã duyệt, mã tham chiếu. Nội dung không phụ thuộc `Throwable.getMessage()` hay stack.
2. **Internal diagnostic event:** request/correlation ID, mã loại sự cố, component/service, timestamp, severity, thông tin chẩn đoán đã giảm thiểu. Nếu giữ stack trace, lưu trong hệ thống **hạn chế quyền** theo chính sách.
3. **Private operational context:** request metadata, bản ghi liên quan, trace, logs, chỉ những dữ liệu cần thiết để điều tra và được phép thu thập. Không tự ghi body, token hoặc tài khoản vào mọi exception log.

Một quy trình tiêu biểu:

```text
HTTP request / user action
        |
        v
Parse & validate public contract
        |
        v
Business/service operations
        |
        +-- expected domain error ------> sanitized 4xx response
        |
        +-- unexpected NPE / failure ---> secure internal event
                                           |
                                           v
                                  sanitized 5xx response
                                           |
                                           v
                             public code + safe reference
```

**Đặc điểm quan trọng:** chính việc *dịch ngoại lệ thành public response* xảy ra tại ranh giới. Không biến đối tượng `Throwable` thành thành phần của payload công khai, không nối `message` với `ex.toString()` rồi nhờ frontend che giấu.

## 5. Phân loại lỗi và chọn HTTP status chính xác

| Tình huống | Status thường phù hợp | Thông tin công khai có thể trả | Tránh |
| --- | ---: | --- | --- |
| Input sai định dạng hoặc thiếu field đã công khai | 400 Bad Request (đôi khi 422 theo contract) | `INVALID_INPUT` + tên field hợp lệ | Raw parser exception chứa input nhạy cảm |
| Chưa được xác thực | 401 Unauthorized | `AUTHENTICATION_REQUIRED` | Tiết lộ username có tồn tại hay không |
| Đã xác thực nhưng thiếu quyền | 403 Forbidden | `FORBIDDEN` | Tiết lộ cấu trúc policy/role nội bộ |
| Không tìm thấy tài nguyên | 404 Not Found | `NOT_FOUND` | Tiết lộ tài nguyên bị hạn chế tồn tại (xét trả 404 thay 403 nếu phù hợp) |
| Xung đột trạng thái/version | 409 Conflict | `CONFLICT` + hướng xử lý an toàn | Phiên bản/SQL row nội bộ |
| Bị giới hạn yêu cầu | 429 Too Many Requests | `RATE_LIMITED`, `Retry-After` khi hợp lý | Thông tin chiến lược chống lạm dụng nội bộ |
| NPE không dự kiến trong server | **500 Internal Server Error** | `INTERNAL_ERROR`, thông điệp chung, reference ID | `getMessage()`, stack, tên trường/class |
| Phụ thuộc bên ngoài không khả dụng | 502/503/504 tùy gateway và tính chất lỗi | `SERVICE_UNAVAILABLE`, chỉ dẫn thử lại hợp lý | Địa chỉ host, credentials hoặc response nội bộ |

Status cuối cùng phải dựa theo **ngữ nghĩa HTTP và hợp đồng API**. Không nên tùy ý chuyển mọi `IllegalArgumentException` thành 400: thư viện nội bộ cũng có thể ném nó do bug. Trong ví dụ Java phía dưới, code chỉ xử lý 400 cho **`InvalidRequestException` do lớp validation chủ động phát sinh**.

**Ghi nhớ về bảo mật:** mức chi tiết của 4xx có thể cao hơn 5xx **chỉ trong phạm vi contract công khai đã được cho phép**. Đừng dùng chi tiết của 403, 404 hay đăng nhập để cho phép dò tồn tại tài khoản/tài nguyên hoặc thông tin phân quyền.

## 6. Mẫu phản hồi công khai: RFC 9457 Problem Details

**RFC 9457** là chuẩn hiện hành cho *Problem Details for HTTP APIs* (thay thế RFC 7807). Nó định nghĩa media type `application/problem+json` và các trường chuẩn như `type`, `title`, `status`, `detail`, `instance`. Có thể bổ sung extension field khi cần.

Ví dụ một HTTP response **minh họa** cho lỗi NPE nội bộ:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Unexpected server error.",
  "requestId": "req-001"
}
```

Trong mẫu này:

- `status=500` và HTTP status thực tế phải nhất quán.
- `detail` chỉ là thông điệp được phê duyệt; **không** lấy từ `exception.getMessage()`.
- `requestId` là extension field do API tự định nghĩa, trỏ đến mã truy vết **do server sinh/kiểm soát**.
- `type="about:blank"` là kiểu lỗi chung; với problem type riêng, dùng URI đã được thiết kế, công khai và kiểm tra an toàn.
- `requestId` trong bài là chuỗi cố định cho ví dụ có output lặp lại; sản phẩm thực tế nên sinh ID đủ riêng biệt, có định dạng giới hạn độ dài và không chứa bí mật.
- `Cache-Control: no-store` là chính sách cân nhắc hữu ích nếu response có nội dung nhạy cảm hoặc theo yêu cầu sản phẩm; không phải mọi problem response RFC 9457 mặc định có header này.

**Không** đặt `stackTrace`, `exceptionClass`, `sql`, `filePath`, `cause` hoặc toàn bộ request body vào extension fields. RFC 9457 **không phải công cụ debug**. Cách dùng chuẩn đúng là làm rõ lỗi API cho client, không lộ implementation internals.

Ví dụ **không nên trả**:

```json
{
  "status": 500,
  "error": "NullPointerException",
  "detail": "Cannot read field \"email\" because \"order.customer\" is null",
  "stackTrace": "com.example.internal.OrderService.load(OrderService.java:84)",
  "requestBody": {"password": "***"}
}
```

Dù password được thay bằng `***` trong ví dụ, thiết kế cho phép cả `requestBody` đi ra ngoài vẫn không hợp lý: các trường khác có thể chứa dữ liệu riêng tư. Ưu tiên **schema allowlist** chỉ chứa những field công khai được duyệt.

## 7. Java 17+ hoàn chỉnh: xử lý NPE tại ranh giới ứng dụng

Ví dụ dưới đây **không dùng framework ngoài JDK**. Nó mô phỏng ranh giới một API: `Runnable` đại diện cho service operation, `ApiResult` đại diện cho dữ liệu mà HTTP handler sẽ trả; `InternalEvent` đại diện cho metadata chẩn đoán **nội bộ**. Đây **không phải HTTP server thật**; mục đích là chứng minh cách tách thông tin trước khi serializer/controller nhận kết quả.

**Tệp `SafeErrorBoundaryDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;

public class SafeErrorBoundaryDemo {
    record ApiResult(int status, String code, String message, String reference) {}
    record InternalEvent(String reference, String category) {}

    static final class InvalidRequestException extends RuntimeException {}

    record Customer(String email) {}
    record Order(Customer customer) {}

    static void unstableService() {
        Order order = new Order(null);
        // NPE này do JVM tạo. Thông điệp chi tiết có thể chứa
        // tên accessor customer() hoặc email() tùy bytecode/JDK.
        System.out.println(order.customer().email());
    }

    static ApiResult atBoundary(String reference, Runnable action,
                                List<InternalEvent> internalEvents) {
        try {
            action.run();
            return new ApiResult(200, "OK", "Completed.", reference);
        } catch (InvalidRequestException ex) {
            return new ApiResult(400, "INVALID_INPUT",
                    "Input is invalid.", reference);
        } catch (Exception ex) {
            // Chỉ lưu metadata tối thiểu trong ví dụ.
            // Không dùng ex.getMessage() làm response.
            internalEvents.add(new InternalEvent(
                    reference, ex.getClass().getSimpleName()));
            return new ApiResult(500, "INTERNAL_ERROR",
                    "Unexpected server error.", reference);
        }
    }

    public static void main(String[] args) {
        List<InternalEvent> internalEvents = new ArrayList<>();
        ApiResult result = atBoundary(
                "req-001",
                SafeErrorBoundaryDemo::unstableService,
                internalEvents);

        System.out.println("status=" + result.status());
        System.out.println("code=" + result.code());
        System.out.println("message=" + result.message());
        System.out.println("reference=" + result.reference());
        System.out.println("messageHasInternalFields=" +
                (result.message().contains("customer")
                || result.message().contains("email")));
        System.out.println("internalEvent=" +
                internalEvents.get(0).category());

        ApiResult validation = atBoundary(
                "req-002",
                () -> { throw new InvalidRequestException(); },
                internalEvents);
        System.out.println("validationStatus=" + validation.status());
        System.out.println("validationCode=" + validation.code());
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac --release 17 -encoding UTF-8 SafeErrorBoundaryDemo.java
java SafeErrorBoundaryDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
status=500
code=INTERNAL_ERROR
message=Unexpected server error.
reference=req-001
messageHasInternalFields=false
internalEvent=NullPointerException
validationStatus=400
validationCode=INVALID_INPUT
```

### 7.1. Phân tích cơ chế bảo vệ

1. `unstableService()` tạo `Order` có `customer == null`, nên gọi `order.customer().email()` phát sinh NPE. JVM có thể gắn **Helpful NPE message** chứa đường dẫn truy cập.
2. `atBoundary(...)` chỉ catch loại lỗi validation đã được thiết kế (`InvalidRequestException`) để trả 400. NPE bất ngờ đi vào nhánh `catch (Exception ex)` và map thành **500**.
3. Phần công khai `ApiResult` chứa `status`, `code`, `message` và `reference` là dữ liệu được **kiểm soát**. Không có code đọc `ex.getMessage()` hay `ex.getStackTrace()` để đưa vào response.
4. `InternalEvent` chứa metadata tối thiểu `reference` và `category`. In `internalEvent` trong demo chỉ để người học kiểm tra; trong hệ thống thật, các metadata này nên được gửi tới **kênh quan sát nội bộ có kiểm soát**, không phải public response.
5. `req-001` là ID do demo cấp tĩnh để stdout dễ tái hiện. Production phải sinh **server-side** hoặc dùng ID hệ thống có kiểm soát, không tin nguyên chuỗi tùy ý do client gửi.
6. Trong thực tế, HTTP framework/controller/exception handler sẽ **serialize** `ApiResult` sang JSON theo schema an toàn và đặt status HTTP tương ứng. Demo không có HTTP server, không tự động phát response thật.
7. `catch (Exception)` là hợp lý tại **ranh giới yêu cầu** để map lỗi bất ngờ; không nên catch `Throwable` hay nuốt lỗi tại mỗi method. Những vấn đề cấp tiến trình như `Error` cần chính sách riêng.

**Hạn chế có chủ ý của demo:** `List<InternalEvent>` chỉ đóng vai trò bộ nhớ cho test, **không phải hệ thống logging production**. Để điều tra lỗi sâu, một kênh telemetry đã phân quyền có thể lưu stack trace được giảm thiểu/rà soát theo chính sách. Không đưa trace đầy đủ vào `ApiResult`.

### 7.2. Nếu cần sinh mã tham chiếu thực tế

Sử dụng ID không dựa vào dữ liệu nhạy cảm, ví dụ:

```java
String reference = "req-" + java.util.UUID.randomUUID();
```

Đây là **snippet đặt trong request handler**, không có stdout cố định do UUID ngẫu nhiên. Sinh ID trên server, giữ ngắn/gọn và áp dụng quy tắc kích thước, charset, tần suất, retention phù hợp.

**Không** dùng mật khẩu, email, token, số tài khoản hoặc toàn bộ URL có query làm reference ID. Đừng chỉ nhận header `X-Request-ID` từ client rồi tin nó không chứa ký tự nguy hiểm: cần áp dụng quy tắc đáng tin, độ dài và format, đặc biệt trước khi đưa vào log hoặc response.

## 8. Thử trực tiếp cờ Helpful NPE trên JDK hiện đại

**Tệp `HelpfulNpeDemo.java` — Java 17+:**

```java
public class HelpfulNpeDemo {
    static class Profile {
        String email;
    }

    static class Request {
        Profile profile;
    }

    static void brokenPath() {
        Request request = new Request();
        System.out.println(request.profile.email.length());
    }

    public static void main(String[] args) {
        try {
            brokenPath();
        } catch (NullPointerException ex) {
            String message = ex.getMessage();
            System.out.println("exceptionType=" +
                    ex.getClass().getSimpleName());
            System.out.println("hasMessage=" + (message != null));
            System.out.println("mentionsProfile=" +
                    (message != null && message.contains("profile")));
        }
    }
}
```

Biên dịch với thông tin debug cục bộ và chạy:

```bash
javac --release 17 -g -encoding UTF-8 HelpfulNpeDemo.java
java HelpfulNpeDemo
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
```

**Kết quả đã quan sát trên HotSpot JDK 24:**

```text
# Mặc định JDK 24:
exceptionType=NullPointerException
hasMessage=true
mentionsProfile=true

# Khi tắt Helpful NPE:
exceptionType=NullPointerException
hasMessage=false
mentionsProfile=false

# Khi bật Helpful NPE:
exceptionType=NullPointerException
hasMessage=true
mentionsProfile=true
```

Ba nhóm trên được ghép để đối chiếu; từng lệnh `java` chạy **riêng** và in ba dòng, không tự in các dòng chú thích `# ...`. `mentionsProfile` là phép kiểm tra nội dung phục vụ demo, **không phải cách phân loại exception của ứng dụng**.

**Cảnh báo về tính di động:** thông điệp chi tiết NPE **không phải hợp đồng API**. JVM, cờ khởi chạy, bytecode do compiler tạo, tên biến debug, đường lỗi và tình huống serializing exception có thể làm khác giá trị `getMessage()`. Đừng phụ thuộc vào chính xác chuỗi `Cannot... because...` hoặc tên `profile` trong unit test nghiệp vụ. Kiểm thử ranh giới bảo mật nên kiểm tra rằng **public response không chứa raw exception**, bất kể thông điệp VM có hay không.

### 8.1. Cờ tắt không xử lý explicit exception messages

Đoạn sau vẫn có message do người viết code cung cấp, kể cả khi tắt Helpful NPE:

```java
throw new NullPointerException("Missing internal setting: payment.secretKey");
```

Đây là ví dụ cố tình cho thấy **rủi ro**; không nên tạo thông điệp chứa secret/key name như vậy ở kênh có thể công khai. Một khi ứng dụng copy nó sang response, cờ JVM **không giúp gì**. Giải pháp thật sự là **không serialize ngoại lệ không kiểm soát ra ngoài**.

## 9. Ghi log nội bộ sao cho hữu ích mà không tạo thêm lỗ hổng

Một điều dễ nhầm: **không trả chi tiết lỗi cho client** không có nghĩa **ghi mọi dữ liệu vào log**. Log cũng có thể đi tới bên thứ ba, hệ thống quan sát dùng chung, dashboard hỗ trợ hoặc ticket tự động. Theo **OWASP Logging Cheat Sheet**, cần loại/mask/sanitize dữ liệu có mức độ nhạy cảm cao và bảo vệ cả quá trình thu thập, lưu, truy cập, lưu giữ.

### 9.1. Metadata nên cân nhắc lưu

- **Correlation/request ID** do server sinh hoặc xác minh theo policy, để tìm sự kiện liên quan.
- Thời điểm, service/component, environment, severity, mã lỗi/categoria đã duyệt.
- HTTP status, operation name không nhạy cảm, loại exception, đường xử lý tổng quát.
- Stack/cause khi thực sự cần chẩn đoán và nằm trong **kênh hạn chế**, với retention và access control đúng.
- Dấu hiệu có thể hành động như version deploy, build revision hoặc nhóm endpoint, nhưng hạn chế xuất hiện ở public response.

### 9.2. Dữ liệu cần loại hoặc giảm thiểu

Thông thường **không ghi trực tiếp**:

- Mật khẩu, API keys, access/refresh token, cookies, session IDs.
- Authorization headers, private keys, connection strings và mật khẩu DB.
- Body HTTP nguyên vẹn, ảnh/tệp upload riêng tư, câu SQL có literal dữ liệu nhạy cảm.
- PII như email, số điện thoại, thông tin định danh/địa chỉ hoặc thông tin tài chính.
- Dữ liệu khách hàng/tài khoản mà nhóm xem log không có quyền truy cập.
- Các giá trị nhập từ client chưa sanitize, đặc biệt CR/LF có thể tạo **log injection** hoặc làm giả dòng sự kiện.

**Đừng tin hoàn toàn vào regex “che password”** để biến dữ liệu không an toàn thành an toàn. Tốt hơn là **không thu thập các field không cần thiết ngay từ đầu** và dùng allowlist dữ liệu log. Nếu cần trace để điều tra, hạn chế quyền đọc, mã hóa truyền/lưu theo môi trường, ghi lại truy cập và xóa khi hết thời gian retention.

### 9.3. Structured logging và quyền truy cập

Với framework logging thực tế, ưu tiên các trường **có cấu trúc** (`requestId`, `eventCode`, `severity`) thay vì nối chuỗi tùy ý từ exception. Log sink phải kiểm soát độ dài, encode đúng định dạng, vệ sinh ký tự điều khiển, giới hạn quyền và tránh log toàn bộ `request` hoặc `principal`.

Không nên ghi `ex.getMessage()`, `ex.toString()` hoặc stack đầy đủ vào **bất kỳ nơi nào** chỉ vì gọi là “log nội bộ”. Hãy quyết định mức dữ liệu cho từng cấp quyền: log vận hành rộng có thể chỉ giữ metadata; trace chi tiết ở kho hạn chế hơn. Kênh public không được truy cập kho nội bộ thông qua một endpoint hỗ trợ mở.

### 9.4. Correlation ID không phải token cấp quyền

Reference ID giúp người dùng cung cấp một chuỗi cho support mà không cần gửi ảnh chụp stack trace. Tuy nhiên ID ấy **không chứng minh danh tính hoặc quyền được xem log**. API tra cứu nội bộ theo reference vẫn cần xác thực, phân quyền và kiểm tra tenant; không tự cấp quyền chỉ vì biết ID.

Chú ý tới multi-tenant: một mã tham chiếu có thể được trao cho người của tenant A, nhưng hệ thống hỗ trợ phải bảo đảm họ không dùng nó để xem log hoặc dữ liệu của tenant B.

## 10. Những lỗi thiết kế thường gặp

### Lỗi 1 — Trả `ex.getMessage()` trong HTTP 500

```java
// Không nên dùng trong public API:
String publicMessage = ex.getMessage();
```

Thông điệp có thể chứa chuỗi truy cập Helpful NPE hoặc dữ liệu nhạy cảm do code khác đưa vào. **Sửa:** trả thông điệp hằng số/allowlist; lưu chẩn đoán ở kênh phù hợp.

### Lỗi 2 — Trả `ex.toString()` vì nghĩ đã “gọn” hơn stack trace

```java
// Không phải thông điệp công khai an toàn:
String publicMessage = ex.toString();
```

`toString()` vẫn có thể bao gồm exception class và message nội bộ. **Sửa:** mã lỗi ổn định `INTERNAL_ERROR` cùng reference ID.

### Lỗi 3 — Biểu diễn stack trace trong trang lỗi nhưng che bằng CSS

Dù HTML/CSS che giấu, **response payload vẫn chứa dữ liệu**. Bất kỳ client hoặc proxy nào nhìn response đều có thể lấy. **Sửa:** không gửi dữ liệu đó từ backend.

### Lỗi 4 — Tin rằng chỉ tắt `ShowCodeDetailsInExceptionMessages` là đủ

Flag không bảo vệ stack trace hoặc thông điệp ngoại lệ tường minh. **Sửa:** xử lý ở error boundary; cờ JVM chỉ là biện pháp bổ trợ có thể cân nhắc.

### Lỗi 5 — Map mọi NPE thành HTTP 400

NPE trong service có thể là bug, sai dữ liệu nội bộ hoặc lỗi ánh xạ. Đừng đổ cho client nếu validation không chủ động xác định lỗi đầu vào. **Sửa:** dùng domain-specific validation error cho 4xx; lỗi không dự kiến thành 5xx.

### Lỗi 6 — Trả thông điệp “thân thiện” nhưng vẫn nhúng tên cấu trúc nội bộ

Ví dụ `"Your account failed in CustomerRepository.loadV2"` vẫn tiết lộ internal implementation. Dùng thông điệp ổn định, không chứa tên class/method/host/path.

### Lỗi 7 — Đưa toàn bộ exception vào JSON extension

Một số serializer/framework có thể serialize `stackTrace`, `cause`, `suppressed` khi nhận `Throwable` làm field. **Sửa:** DTO chỉ chứa field công khai thuộc allowlist; không có thuộc tính kiểu `Throwable` trong response DTO.

### Lỗi 8 — Tắt stack trace ở UI nhưng bật debug ở gateway khác

Bất kỳ tầng nào (service, gateway, proxy, GraphQL middleware, queue) có thể vô tình trả upstream body thô. **Sửa:** kiểm thử end-to-end cả đường lỗi, không chỉ unit test controller.

### Lỗi 9 — Dùng `message` để định nghĩa giao thức cho client

Nếu client parse văn bản `"Cannot invoke ..."`, một thay đổi JDK/refactor có thể làm hỏng client. **Sửa:** client dựa vào `code`/`status` hoặc problem `type` ổn định.

### Lỗi 10 — Log toàn bộ request/headers để “debug NPE”

Điều này có thể lưu `Authorization`, cookie, PII hoặc payload bí mật vào hệ thống log rộng. **Sửa:** giảm dữ liệu ngay ở nguồn, allowlist metadata, kiểm soát quyền và retention.

### Lỗi 11 — Catch `Throwable` rồi giả vờ mọi thứ đã phục hồi

`Throwable` còn bao gồm `Error`, một số trạng thái JVM không phù hợp để biến thành 500 rồi tiếp tục bình thường. **Sửa:** catch exception ở ranh giới phù hợp; có chính sách riêng cho lỗi tài nguyên/tiến trình, interruption và các trường hợp phải propagate.

### Lỗi 12 — Trả mã tham chiếu do người dùng tùy ý nhập

Header người dùng gửi có thể chứa ký tự CR/LF, nội dung dài, token hoặc chuỗi làm nhiễm log. **Sửa:** sinh ID tin cậy tại server hoặc xác thực strict format, độ dài và encoding.

### Lỗi 13 — Cho phép endpoint `/errors/{id}` trả stack nếu biết ID

Reference ID là định danh, **không phải quyền truy cập**. **Sửa:** endpoint chẩn đoán phải ở vùng quản trị có authn/authz, tenant isolation, audit và rate limit, hoặc không công bố.

### Lỗi 14 — Bỏ qua lỗi validation hợp lệ khiến UX tệ

Bảo mật không đồng nghĩa trả `"Internal server error"` cho mọi thứ. Nếu client gửi sai field public và validator đã phát hiện cụ thể, hãy trả lỗi 4xx an toàn giúp sửa input. **Sửa:** tách các lỗi nghiệp vụ được định nghĩa và lỗi triển khai không dự kiến.

## 11. Chiến lược kiểm thử chống lộ thông tin

Một test tốt cần **gây lỗi thật** rồi kiểm tra response qua ranh giới cuối cùng:

1. **Cố ý tạo NPE** ở các lớp service, mapper và chỗ truy cập nested fields; API trả status 5xx thích hợp, không có `customer.profile`, package, stack trace, tên file hoặc lời giải thích bytecode.
2. **Kiểm tra payload công khai theo allowlist**: chỉ `type`/`title`/`status`/`detail`/`requestId` hoặc schema đã duyệt; không có `Throwable`/`stackTrace`/`cause`.
3. **Đối chiếu nhiều phiên bản/cờ JVM**: bật/tắt `ShowCodeDetailsInExceptionMessages`, public response vẫn giống **về cấu trúc và mức độ chi tiết được cho phép**.
4. **Kiểm tra 400 hợp lệ**: input thiếu field public tạo lỗi validation có chủ đích với 4xx, không bị ép thành 500; không phản chiếu giá trị nhạy cảm người dùng gửi.
5. **Kiểm tra 500**: NPE do bug/không dự kiến không bị chuyển thành 400 và không reveal nội bộ.
6. **Kiểm tra exception khác**: SQL, I/O, JSON parser, timeout, forbidden, và exception tự viết có message chứa chuỗi giả lập nhạy cảm.
7. **Kiểm tra reference ID**: tồn tại và giúp correlate nội bộ; do server kiểm soát, không chứa nội dung bí mật và không cấp quyền xem log.
8. **Kiểm tra headers**: không có debug headers/stack; `Content-Type` và status đúng, cache policy hợp lý.
9. **Kiểm tra đường end-to-end**: gateway, reverse proxy, trang HTML lỗi, GraphQL `errors`, WebSocket và webhook không chuyển lỗi thô sang client.
10. **Kiểm tra log**: sự kiện được ghi để điều tra, không có token, password, cookie, PII trong kênh rộng; có biện pháp chống CR/LF log injection.
11. **Kiểm tra quyền**: người hỗ trợ không thể truy vấn log/trace của tenant khác chỉ bằng reference ID.
12. **Kiểm tra vận hành**: thay đổi cờ JVM, cấu hình debug, release mode, logging level và SDK observability không làm mất ranh giới công khai/nội bộ.

### 11.1. Một cách kiểm tra tối thiểu trong code

Trong chương trình `SafeErrorBoundaryDemo`, dòng:

```java
boolean leaked = result.message().contains("customer")
        || result.message().contains("email");
```

là **một kiểm tra minh họa**, chưa đủ thay thế kiểm thử bảo mật. Nó chỉ xem hai chuỗi cụ thể. Production test nên kiểm tra **toàn bộ response schema và body** theo allowlist, đồng thời chủ động tạo exception chứa marker nhạy cảm và xác nhận marker **không xuất hiện** trong bất kỳ trường nào công khai.

**Khuyến nghị:** dùng các bài test xác định dữ liệu được phép xuất hiện thay vì chỉ tìm vài keyword bị cấm; keyword denylist dễ bỏ sót đường lộ mới.

## 12. Bài tập thực hành

1. **Nhận diện nguy cơ:** xem `"Cannot read field \"passwordHash\" because \"user.account\" is null"`. Hãy phân biệt thông tin **tên trường nội bộ** có thể bị lộ với **giá trị password hash** (không được chứng minh là xuất hiện trong thông điệp đó).
2. **Boundary an toàn:** sửa một handler đang trả `ex.toString()` để chỉ trả `status=500`, `code=INTERNAL_ERROR` và một message cố định.
3. **Phân biệt 400/500:** tạo `InvalidRequestException` khi field public thiếu, và gây một NPE bất ngờ ở service. Kiểm tra status tương ứng.
4. **Reference ID:** thay `"req-001"` ở ví dụ bằng ID do server sinh bằng `UUID.randomUUID()`. Giải thích vì sao client không nên tự quyết định giá trị ID nội bộ.
5. **RFC 9457:** viết `application/problem+json` có `type`, `title`, `status`, `detail` và extension `requestId`; không thêm `stackTrace`.
6. **Flag JVM:** chạy `HelpfulNpeDemo` với `-XX:-ShowCodeDetailsInExceptionMessages` và bật lại. Vì sao khác biệt của message **không được** ảnh hưởng response công khai?
7. **Explicit exception:** tạo `new NullPointerException("secretName")` khi tắt flag. Quan sát `getMessage()` và giải thích vì sao cờ không bảo vệ trường hợp này.
8. **Logs:** định nghĩa các trường tối thiểu `reference`, `eventCode`, `service`, `timestamp`. Liệt kê token/cookie/PII phải loại.
9. **Cross-tenant:** một người dùng có `requestId` của lỗi thuộc tenant khác có được truy cập log không? Vì sao?
10. **End-to-end:** gây lỗi qua API gateway/reverse proxy và kiểm tra raw HTTP body; vì sao test chỉ xem giao diện web chưa đủ?
11. **Schema allowlist:** viết test bảo đảm response chỉ chứa field công khai đã phê duyệt; cài exception giả có field name nhạy cảm và kiểm tra không thoát ra.
12. **Code review:** tìm nơi gọi `getMessage()`, `printStackTrace()`, `toString()` trên exception; phân loại nơi nào là công khai, nơi nào là nội bộ có quyền và cần xử lý gì.

**Đáp án định hướng:** (1) thông điệp có thể tiết lộ *tên* và đường truy cập, không tự cho biết giá trị hash; (2) tuyệt đối không copy raw exception ra ngoài; (3) domain validation 4xx, lỗi không dự kiến 5xx; (4) ID an toàn do server kiểm soát, không chứa bí mật; (5) problem details chỉ giải thích contract API; (6–7) flag chỉ tác động đến thông điệp VM tạo, không phải toàn bộ exception; (8) metadata ít nhất đủ điều tra, dữ liệu nhạy cảm theo OWASP phải giảm thiểu; (9) reference không thay authorization; (10–12) phải kiểm tra mọi kênh nhận response và logging.

## 13. Checklist triển khai trước khi release

- [ ] Có **global error handler** ở ranh giới HTTP/UI/message.
- [ ] Không trả trực tiếp `getMessage()`, `toString()`, stack trace hoặc `Throwable` trong payload public.
- [ ] Có mã lỗi ổn định và HTTP status tương ứng.
- [ ] Mẫu lỗi không chứa package/class/field nội bộ hoặc giá trị bí mật.
- [ ] Lỗi validation có chủ đích được phân loại khác NPE bất ngờ.
- [ ] Có reference ID **do server kiểm soát**, dễ đối chiếu nội bộ.
- [ ] Response body và headers theo schema/public contract đã duyệt.
- [ ] Không để debug mode, proxy, GraphQL, webhook hoặc mobile SDK chuyển tiếp lỗi thô.
- [ ] Log theo allowlist; không thu thập token/cookie/password/PII và không dễ bị log injection.
- [ ] Có phân quyền, audit truy cập, retention và giám sát logs/traces.
- [ ] Có test chạy cả khi Helpful NPE enabled/disabled.
- [ ] Có test lộ thông tin theo **allowlist**, không chỉ dựa trên vài keyword.
- [ ] Có test multi-tenant và kiểm tra support workflow khi sử dụng request ID.

## 14. Nguồn chính thức

- **OpenJDK JEP 358 — Helpful NullPointerExceptions:** cơ chế thông điệp chi tiết ra đời từ Java 14 và tùy chọn JVM: https://openjdk.org/jeps/358
- **Oracle JDK 15 Release Notes — Enable ShowCodeDetailsInExceptionMessages by default:** cảnh báo khả năng lộ thông tin qua web apps và hành vi bật mặc định từ JDK 15: https://www.oracle.com/java/technologies/javase/15-relnote-issues.html
- **Java 17 `NullPointerException` API:** `getMessage()` có thể là mô tả phụ thuộc triển khai hoặc `null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html
- **OWASP Error Handling Cheat Sheet:** xử lý lỗi tập trung, trả thông điệp chung cho người ngoài và giữ chi tiết chẩn đoán nội bộ: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html
- **OWASP Logging Cheat Sheet:** lọc dữ liệu nhạy cảm, interaction ID, chống log injection, phân quyền và thời gian lưu: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **RFC 9457 — Problem Details for HTTP APIs:** chuẩn hiện hành, phần data model và Security Considerations: https://www.rfc-editor.org/rfc/rfc9457.html

**Ghi nhớ:** Helpful NPE là **công cụ debug có giá trị**, nhưng `NullPointerException.getMessage()` và stack trace **không phải public API**. Hãy giữ lỗi chi tiết trong môi trường chẩn đoán nội bộ được kiểm soát; phản hồi cho client chỉ gồm thông tin cho phép, mã lỗi có ý nghĩa và một reference ID an toàn. Tắt chi tiết Helpful NPE có thể giảm một nguồn rò rỉ, **không thay thế xử lý lỗi bảo mật tại ranh giới ứng dụng**.