# Không lộ stack trace

## 1. Mục tiêu của yêu cầu

Một request lỗi không nên trở thành cách tải về thông tin triển khai của hệ thống. Khi client gửi dữ liệu sai, một dependency ngừng hoạt động hoặc chương trình gặp lỗi bất ngờ, phản hồi vẫn phải tuân theo một hợp đồng công khai đã được thiết kế trước.

Trong chương Error handling, yêu cầu **không lộ stack trace** có nghĩa là thông tin chẩn đoán nội bộ không vượt qua ranh giới tới người hoặc thành phần không được phép nhận thông tin đó. Phạm vi không chỉ là response JSON: trang HTML lỗi, header, luồng sự kiện, thông báo trên giao diện và công cụ hỗ trợ cũng có thể làm lộ cùng dữ liệu.

Trong module đặc tả yêu cầu bảo mật, câu “ẩn lỗi trên production” chưa đủ. Cần chỉ rõ:

- Thông tin nào được phép xuất hiện ở từng đầu ra.
- Tầng nào chịu trách nhiệm khi lỗi xảy ra trước hoặc sau controller.
- Cách hỗ trợ điều tra mà không đưa chi tiết nội bộ cho client.
- Cách kiểm chứng trên đường thành công, đường lỗi và cấu hình triển khai thực tế.
- Người chịu trách nhiệm cho yêu cầu, bằng chứng và rủi ro còn lại.

Sau bài này, người học có thể biến một nguy cơ lộ thông tin qua lỗi thành yêu cầu đo được, gắn yêu cầu với thiết kế xử lý lỗi và viết tiêu chí nghiệm thu tương ứng.

## 2. Stack trace tiết lộ những gì?

Stack trace mô tả chuỗi lời gọi tại thời điểm một exception được tạo hoặc ghi nhận. Trong Java, đầu ra chẩn đoán thường đi kèm tên exception, message, các frame và có thể có chuỗi nguyên nhân hoặc exception bị suppressed.

Ví dụ minh họa bằng dữ liệu tổng hợp:

```text
com.example.persistence.QueryExecutionException:
  failed query against table internal_customer_record
    at com.example.customer.CustomerRepository.load(CustomerRepository.java:184)
    at com.example.customer.CustomerService.find(CustomerService.java:73)
Caused by: java.lang.IllegalStateException: configuration rejected
```

Nếu nội dung này xuất hiện trong response công khai, nó có thể tiết lộ:

| Nhóm thông tin | Ví dụ | Giá trị đối với hành vi lạm dụng |
|---|---|---|
| Cấu trúc chương trình | Package, class, method, tên module | Suy luận thành phần và đường đi của request |
| Chi tiết triển khai | Tên file, số dòng, đường dẫn nội bộ | Đối chiếu lỗi với phiên bản hoặc cấu trúc triển khai |
| Hạ tầng | Hostname, cổng, tên database hoặc service | Lập bản đồ các thành phần phía sau API |
| Dữ liệu và truy vấn | Tên bảng, câu truy vấn, tham số | Hiểu mô hình dữ liệu hoặc nhận dữ liệu vốn không được phép xem |
| Bí mật bị đưa vào message | Token, connection string, thông tin xác thực | Có thể tạo ra rủi ro trực tiếp vượt quá việc nhận diện công nghệ |

Không phải mọi stack trace đều có mọi nhóm trên. Mức tác động phụ thuộc vào nội dung cụ thể, quyền truy cập và khả năng kết hợp với thông tin khác.

Ngược lại, **không có frame stack trace chưa đồng nghĩa không lộ thông tin**. Những phản hồi sau vẫn không phù hợp nếu chưa được cho phép trong hợp đồng công khai:

```json
{"error":"Connection refused at db-internal.example:5432"}
```

```json
{"error":"Failed SQL: select * from internal_customer_record"}
```

Một dòng `exception.getMessage()` hoặc `exception.toString()` có thể đã chứa dữ liệu cần bảo vệ. Vì vậy, yêu cầu phải kiểm soát cả trace và thông tin chẩn đoán liên quan, thay vì chỉ xóa những dòng bắt đầu bằng `at`.

## 3. Rủi ro và ranh giới tin cậy

### 3.1. Kịch bản đe dọa cần được ghi thành quan hệ nhân quả

Một kịch bản có thể viết như sau:

> Khi một request gây lỗi truy vấn, bộ xử lý lỗi mặc định đưa exception message và stack trace vào response. Một người gọi API không cần quyền quản trị có thể lặp lại request để thu thập tên bảng, class và địa chỉ nội bộ, từ đó hỗ trợ thăm dò hoặc khai thác các điểm yếu khác.

Một kịch bản khác không cần người gọi cố tình gây lỗi:

> Khi giao diện hiển thị nguyên response lỗi, dữ liệu cá nhân trong exception message xuất hiện trên màn hình dùng chung hoặc được gửi tiếp trong ảnh chụp hỗ trợ.

Hai kịch bản dẫn tới yêu cầu khác nhau nhưng liên quan: kiểm soát response ở server và kiểm soát cách client trình bày hoặc chuyển tiếp lỗi.

### 3.2. Ranh giới “nội bộ” phải được xác định cụ thể

| Đầu ra | Đối tượng nhận | Chính sách nên có |
|---|---|---|
| API hoặc trang lỗi cho người dùng | Người gọi theo hợp đồng sản phẩm | Chỉ nhận thông tin công khai đã cho phép |
| API service-to-service | Service với quyền và mục đích cụ thể | Có hợp đồng lỗi riêng; không mặc định được nhận toàn bộ trace |
| Log vận hành | Vai trò vận hành được cấp quyền | Chỉ nhận trường cần thiết, theo quy tắc giảm dữ liệu |
| Kho chẩn đoán chuyên sâu | Nhóm điều tra được ủy quyền | Kiểm soát truy cập, thời hạn lưu và quy trình sử dụng chặt hơn |
| Ticket hoặc file xuất hỗ trợ | Nhân sự và bên nhận theo quy trình | Giảm dữ liệu trước khi chia sẻ, không tự đính kèm trace thô |

Một service nằm trong private network vẫn có thể được nhiều đội hoặc nhiều tenant gián tiếp sử dụng. Vị trí mạng không tự xác lập quyền xem exception nội bộ.

Mã theo dõi request cũng không phải bằng chứng ủy quyền. Biết một request ID không cho phép người gọi mở log, tải trace hay xem lỗi của người khác.

## 4. Thiết kế hợp đồng lỗi công khai

### 4.1. Phản hồi phải hữu ích và nằm trong tập dữ liệu cho phép

Ví dụ lỗi bất ngờ của một API HTTP:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store

{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu lúc này.",
  "requestId": "8fcfe14d-69dd-4db4-97f0-50ac5c148186"
}
```

Các trường có trách nhiệm riêng:

- `code`: mã ổn định để client xử lý theo hợp đồng, không phải tên class exception.
- `message`: nội dung công khai đã được phê duyệt; có thể dịch theo ngôn ngữ mà vẫn giữ nguyên ý nghĩa.
- `requestId`: định danh ngẫu nhiên, không chứa dữ liệu cá nhân hoặc bí mật, dùng để đối chiếu với sự kiện nội bộ.

Không cần biến mọi lỗi thành “đã có lỗi”. Lỗi nhập liệu có thể chỉ rõ quy tắc công khai bị vi phạm:

```json
{
  "code": "INVALID_REQUEST",
  "message": "Ngày kết thúc phải sau ngày bắt đầu.",
  "requestId": "c2cf4aa9-f219-48bc-91bc-5a56db52d0e8"
}
```

Điều kiện là thông báo này được tạo từ quy tắc nghiệp vụ đã cho phép công khai, không phải lấy nguyên message từ thư viện hoặc database. Với lỗi nhiều field, có thể bổ sung danh sách mã field và mã quy tắc theo allowlist; không cần phản chiếu lại giá trị nhạy cảm mà người dùng đã gửi.

### 4.2. Những trường không nên tự xuất hiện

Hợp đồng công khai không có các trường sau nếu chúng chỉ phục vụ chẩn đoán nội bộ:

```text
exception
exceptionClass
stackTrace
cause
suppressed
sql
internalHost
debugDump
```

Chỉ kiểm tra tên trường là chưa đủ. Trace có thể bị nhét vào `message`, header hoặc một chuỗi JSON bên trong `details`. Kiểm soát đúng phải bắt đầu từ nguồn tạo dữ liệu và kiểu dữ liệu response.

### 4.3. Giữ đúng ngữ nghĩa giao thức và nghiệp vụ

Che thông tin không có nghĩa là đổi tất cả lỗi thành HTTP 200 hoặc HTTP 500. Với API HTTP được thiết kế theo status, lỗi request không hợp lệ, không được phép thực hiện, xung đột trạng thái và lỗi server cần được phân biệt theo hợp đồng.

Không tự công khai sự tồn tại của tài khoản hoặc tài nguyên chỉ để làm thông báo cụ thể hơn. Thông báo và status trong các luồng nhạy cảm phải tuân theo chính sách chống dò tìm của chính luồng đó.

Không mặc định yêu cầu người dùng gửi lại mọi request lỗi. Một thao tác ghi có thể đã hoàn tất ở dependency trước khi phản hồi bị lỗi. Quy tắc retry, idempotency và đối soát phải được đặc tả riêng; thông báo lỗi không được cam kết thao tác “chưa xảy ra” khi hệ thống chưa biết điều đó.

## 5. Chuyển mục tiêu thành yêu cầu kiểm chứng được

Mỗi yêu cầu cần có phạm vi, hành vi, trường hợp lỗi và bằng chứng. Từ “không bao giờ lộ lỗi” quá rộng nếu không xác định những kênh và thành phần nằm trong phạm vi kiểm soát.

Một bộ yêu cầu minh họa:

| ID | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| ERR-01 | Mọi phản hồi lỗi của các endpoint công khai trong danh mục phải dùng schema lỗi được phép, trừ ngoại lệ giao thức đã ghi rõ | Ma trận endpoint, schema và kết quả kiểm thử |
| ERR-02 | Response không chứa stack frame, exception message nội bộ, cause hoặc suppressed exception từ các lỗi được kích hoạt trong bộ thử | So sánh phản hồi đã giải mã với marker và fixture nội bộ |
| ERR-03 | Lỗi nghiệp vụ được ánh xạ qua danh sách mã và thông báo công khai; lỗi chưa được ánh xạ dùng thông báo lỗi bất ngờ cố định | Bảng ánh xạ và thử một exception chưa biết |
| ERR-04 | Header, trang HTML lỗi và dữ liệu gửi tới client không chứa nội dung chẩn đoán bị cấm | Kiểm tra toàn bộ response và giao diện lỗi |
| ERR-05 | Mỗi lỗi thuộc phạm vi đối chiếu có request ID do thành phần tin cậy tạo; response và sự kiện nội bộ dùng cùng ID khi việc ghi sự kiện thành công | Bằng chứng liên kết response với bản ghi thử |
| ERR-06 | Tham số, header hoặc quyền người dùng thông thường không thể bật trace công khai trong môi trường triển khai | Thử các cơ chế debug đã nhận diện trong inventory |
| ERR-07 | Lỗi trước controller, trong serializer và ở trang lỗi mặc định được xử lý bởi tầng có trách nhiệm | Thử lỗi tại từng tầng, không chỉ lỗi nghiệp vụ |
| ERR-08 | Khi hệ thống logging gặp lỗi, handler vẫn giữ hợp đồng lỗi an toàn và không dùng trace công khai làm fallback | Fault injection vào logging và kiểm tra response |
| ERR-09 | Dữ liệu chẩn đoán được giảm dữ liệu trước khi tới sink không có quyền nhận dữ liệu gốc | Kiểm tra trường, redaction và quyền truy cập |
| ERR-10 | Cấu hình triển khai được kiểm tra không cho phép chế độ hiển thị lỗi phát triển trên các route công khai | Cấu hình hiệu lực và bằng chứng kiểm tra trên bản triển khai |
| ERR-11 | Đường lỗi sau khi response đã bắt đầu gửi không nối thêm trace hoặc dump vào stream | Thử lỗi giữa luồng và quan sát dữ liệu thực nhận |
| ERR-12 | Client không hiển thị hoặc gửi tiếp trace thô nhận được từ upstream ngoài hợp đồng | Kiểm thử UI, telemetry và quy trình hỗ trợ |

Các yêu cầu này là mẫu để đặc tả dự án. Chúng chưa chứng minh một sản phẩm cụ thể đã đáp ứng hoặc bộ thử đã bao phủ toàn bộ không gian lỗi.

### 5.1. Đặc tả sâu hơn cho ERR-02

```text
Phạm vi:
  Các response lỗi trên route công khai của bản triển khai được nghiệm thu.

Hành vi:
  Không đưa Throwable hoặc cấu trúc chẩn đoán nội bộ vào DTO công khai.
  Message công khai chỉ được tạo từ danh sách thông báo đã xác nhận.

Các kênh cần kiểm tra:
  Body, header, trang HTML thay thế và phần dữ liệu đã gửi của stream.

Điều kiện đạt của bộ thử:
  Không có marker chẩn đoán nội bộ trong các kênh trên.
  Schema và status đúng hợp đồng của từng ca.
  Không có trace từ cause hoặc suppressed exception được chèn gián tiếp.

Giới hạn bằng chứng:
  Kết luận chỉ áp dụng cho các route, cấu hình và nhánh đã kiểm tra.
```

Nếu chỉ viết “không xuất hiện chữ Exception”, kiểm thử có thể bỏ sót một trace đã đổi định dạng, đồng thời báo sai với dữ liệu hợp lệ có chứa từ đó. Oracle phải dựa vào hợp đồng và fixture, có thể bổ sung heuristic để phát hiện bất thường.

## 6. Kiến trúc xử lý lỗi ở nhiều tầng

Một luồng HTTP thường có nhiều nơi tạo lỗi:

```text
Client
  -> CDN / reverse proxy / gateway
  -> HTTP server và bộ lọc
  -> xác thực, phân quyền, giới hạn lưu lượng
  -> giải mã request và validation
  -> controller và service
  -> database hoặc dependency
  -> serializer và ghi response
  -> Client
```

Bộ xử lý exception của controller chỉ kiểm soát được một phần luồng. Nó có thể không nhận lỗi do gateway từ chối request, lỗi parser xảy ra trước điểm xử lý, lỗi ghi response hoặc lỗi ở background task.

Vì vậy cần chỉ định chủ sở hữu ở từng tầng:

| Tầng | Loại lỗi minh họa | Trách nhiệm |
|---|---|---|
| Edge hoặc gateway | Upstream timeout, request quá lớn, upstream không sẵn sàng | Dùng trang hoặc body lỗi an toàn của tầng edge |
| Bộ lọc và bảo mật | Không xác thực được, bị từ chối quyền, vượt giới hạn | Giữ hợp đồng tương ứng, không đính kèm exception của middleware |
| Parser và validation | JSON hỏng, kiểu dữ liệu sai | Trả lỗi nhập liệu an toàn, không echo payload hoặc thông tin parser nội bộ |
| Ứng dụng | Lỗi miền nghiệp vụ, lỗi dependency, lỗi bất ngờ | Ánh xạ lỗi theo policy trung tâm |
| Serializer | Không thể chuyển object thành response | Dùng fallback tối giản nếu chưa commit response |
| Luồng đã bắt đầu gửi | Stream đang chạy gặp lỗi | Theo hợp đồng kết thúc luồng; không nối stack trace vào dữ liệu |
| Job hoặc consumer | Lỗi không nằm trong vòng đời request | Ghi trạng thái và sự kiện nội bộ; payload lỗi công khai vẫn phải an toàn |

Fallback phải đơn giản, ít phụ thuộc vào thành phần đang lỗi. Một trang lỗi cần truy vấn database có thể thất bại đúng lúc database ngừng hoạt động.

Không thể bảo đảm một response JSON hoàn chỉnh nếu kết nối đã bị đóng hoặc tiến trình không còn hoạt động. Yêu cầu phù hợp trong trường hợp đó là không gửi thêm dữ liệu chẩn đoán, đóng hoặc kết thúc theo giao thức và để tầng bao ngoài áp dụng hành vi lỗi an toàn trong khả năng của nó.

## 7. Ví dụ ánh xạ lỗi trong Java

### 7.1. Mẫu nguy hiểm

```java
// Không dùng làm response công khai.
return Map.of(
    "message", exception.getMessage(),
    "exception", exception.toString(),
    "trace", exception.getStackTrace()
);
```

Các biến thể vẫn có vấn đề:

- Đưa nguyên exception vào một object để JSON serializer tự xử lý.
- Chỉ dùng message của root cause vì nghĩ rằng đã bỏ trace.
- Ghép `exception` vào chuỗi thông báo, làm gọi `toString()` gián tiếp.
- Chỉ cắt trace còn vài dòng đầu; phần đầu có thể chứa dữ liệu nhạy cảm nhất.
- Mã hóa hoặc nén trace rồi trả cho client; client vẫn nhận được dữ liệu.

### 7.2. DTO công khai chỉ chứa dữ liệu được phép

Ví dụ sau dùng cú pháp Java 17 trở lên. Đây là policy ánh xạ ở mức mã nguồn, chưa phải một HTTP server hoàn chỉnh.

```java
import java.util.UUID;

public final class PublicErrorPolicy {
    private PublicErrorPolicy() {}

    public record ErrorBody(
        String code,
        String message,
        String requestId
    ) {}

    public record ErrorReply(int status, ErrorBody body) {}

    // Kiểu lỗi miền có ý nghĩa xác định bởi ứng dụng.
    // Internal message không được chuyển thành public message.
    public static final class InputRejected extends RuntimeException {
        public InputRejected(String internalMessage) {
            super(internalMessage);
        }
    }

    public static final class StateConflict extends RuntimeException {
        public StateConflict(String internalMessage) {
            super(internalMessage);
        }
    }

    public static ErrorReply map(Exception failure, UUID requestId) {
        if (failure instanceof InputRejected) {
            return reply(
                400, "INVALID_REQUEST",
                "Dữ liệu yêu cầu không hợp lệ.", requestId
            );
        }
        if (failure instanceof StateConflict) {
            return reply(
                409, "STATE_CONFLICT",
                "Không thể thực hiện thao tác ở trạng thái hiện tại.",
                requestId
            );
        }
        return reply(
            500, "INTERNAL_ERROR",
            "Không thể xử lý yêu cầu lúc này.", requestId
        );
    }

    private static ErrorReply reply(
        int status, String code, String message, UUID requestId
    ) {
        return new ErrorReply(
            status,
            new ErrorBody(code, message, requestId.toString())
        );
    }
}
```

Những quyết định bảo mật nằm trong mẫu này:

- DTO không chứa `Throwable`, cause hoặc trường trace.
- Message được chọn từ literal công khai, không đọc message của exception.
- Hai loại lỗi miền được phân biệt rõ với lỗi chưa biết.
- `requestId` là kiểu UUID do tầng tin cậy cung cấp, không phải chuỗi header thô.
- Status và mã lỗi là dữ liệu riêng, giúp adapter HTTP giữ đúng hợp đồng.

Ứng dụng cần tạo ID ở đầu vòng đời request, trước các thao tác có khả năng lỗi, rồi truyền cùng ID tới policy và logging. Nếu cần lưu correlation ID từ client, hãy coi đó là dữ liệu không tin cậy: có giới hạn và trường lưu riêng; không để nó thay thế ID nội bộ hoặc tạo dòng log giả.

Adapter HTTP phải đặt status thực từ `ErrorReply.status()`, dùng JSON serializer cho `body` và áp dụng header theo policy. Trả nguyên object `ErrorReply` với status HTTP 200 sẽ làm sai hợp đồng.

Không suy diễn rằng mọi `IllegalArgumentException` đều là lỗi nhập liệu của người gọi. Nó có thể phát sinh từ bug bên trong. Chỉ ánh xạ những loại lỗi mà ứng dụng đã xác định rõ ngữ nghĩa công khai; các lỗi chưa biết đi theo nhánh an toàn.

### 7.3. Những phần mẫu ánh xạ chưa giải quyết

Policy trên chưa xử lý lỗi parser, gateway, serializer, logging hoặc response đã commit. Nó cũng chưa xác minh dữ liệu miền đầu vào, phân quyền hay idempotency.

Không nên bắt toàn bộ `Throwable` rồi giả định tiến trình có thể tiếp tục bình thường. Các lỗi nghiêm trọng của JVM có thể làm cho việc tạo response hoặc ghi log không còn đáng tin cậy. Cần có thiết kế vận hành và tầng bao ngoài phù hợp; đường lỗi không được phát hành trace công khai như một cơ chế dự phòng.

## 8. Giữ khả năng chẩn đoán mà không tạo kênh lộ mới

### 8.1. Tách hợp đồng công khai khỏi dữ liệu điều tra

Một sự kiện vận hành tối thiểu có thể chứa:

```json
{
  "event": "request_failed",
  "requestId": "8fcfe14d-69dd-4db4-97f0-50ac5c148186",
  "routeId": "customer.read",
  "publicCode": "INTERNAL_ERROR",
  "failureCategory": "DEPENDENCY_FAILURE",
  "deploymentRevision": "candidate-build-12"
}
```

Các giá trị trên là ví dụ tổng hợp. `routeId` là tên route ổn định, không phải URL thô chứa query string hoặc định danh cá nhân. `failureCategory` được ánh xạ theo danh sách nội bộ, không được ghép từ input tùy ý.

Khi điều tra cần stack trace, việc thu thập phải theo policy riêng cho kênh chẩn đoán. Không suy từ yêu cầu “client không thấy trace” rằng có thể đẩy toàn bộ exception vào mọi sink logging.

Trace thường đi kèm message của exception, cause và suppressed exception. Bất kỳ phần nào cũng có thể chứa token, dữ liệu người dùng hoặc thông tin kết nối. Vì vậy cần xem xét toàn bộ cây exception khi quyết định dữ liệu nào được lưu.

### 8.2. Yêu cầu cho kênh chẩn đoán

- Chỉ thu dữ liệu có mục đích điều tra rõ ràng và trong phạm vi quyền được cấp.
- Giảm hoặc loại nội dung nhạy cảm trước khi chuyển tới sink không được phép nhận dữ liệu gốc.
- Không ghi authorization header, cookie, password hoặc toàn bộ body theo mặc định.
- Giới hạn kích thước, số cause, số frame và tần suất để giảm áp lực lưu trữ; giới hạn kích thước không thay thế redaction.
- Xác định thời hạn giữ, quyền tìm kiếm, quyền export và người được chia sẻ.
- Kiểm soát SDK báo lỗi, tracing agent và dịch vụ thu thập bên thứ ba như những bên nhận dữ liệu thực sự.
- Dùng dữ liệu tổng hợp để kiểm chứng đường đi của dữ liệu nhạy cảm và các quy tắc loại bỏ.

Một lời gọi kiểu `logger.error("failed", exception)` có thể tự render cả exception message và trace. Cần xác minh formatter, appender và agent đang dùng; thêm một bộ lọc vào message thông thường chưa chứng minh phần exception đã được xử lý.

Đối với bí mật có cấu trúc không dự đoán trước được, regex đơn lẻ thường không đủ làm ranh giới bảo mật. Ưu tiên không đưa dữ liệu không cần thiết vào exception từ đầu, ghi trường theo allowlist và dùng cơ chế xử lý chẩn đoán được thiết kế rõ.

### 8.3. Khi logging lỗi

Logging có thể timeout, đầy dung lượng, sai cấu hình hoặc gặp lỗi serialization. Không được để lỗi này khiến handler trả exception mới cho client, hoặc rơi về `printStackTrace()` trong response.

Thiết kế cần xác định đường fallback có giới hạn, tín hiệu cảnh báo không chứa payload và cách tránh vòng lặp “ghi lỗi của logger bằng chính logger đang lỗi”.

Nếu sự kiện nội bộ chưa được lưu thành công, không nên cam kết mọi request ID đều tìm thấy trace. Có thể theo dõi số lần ghi thất bại bằng telemetry tối thiểu, đồng thời giữ hợp đồng response an toàn.

## 9. Cấu hình môi trường và cơ chế debug

### 9.1. Kiểm tra cấu hình hiệu lực

Một file cấu hình ghi “tắt trace” không đủ nếu biến môi trường, profile khác hoặc cấu hình framework ghi đè nó khi triển khai.

Cần kiểm tra những nhóm cấu hình phù hợp với stack công nghệ thực tế:

| Nhóm | Điều cần xác minh |
|---|---|
| Error renderer | Không thêm trace, exception message hoặc dump vào body |
| Trang lỗi mặc định | Không hiển thị trang phát triển khi route lỗi không có mapping |
| Debug và development mode | Không bật công khai trong môi trường triển khai |
| Content negotiation | JSON, HTML và các định dạng hỗ trợ đều áp dụng policy |
| Gateway hoặc web server | Trang lỗi thay thế không chứa upstream dump hoặc đường dẫn cấu hình |
| Debug endpoint | Không cho người dùng thông thường xem trace hoặc cấu hình nội bộ |
| SDK và client telemetry | Không tự gửi response thô tới bên nhận ngoài phạm vi cho phép |

Tên property và giá trị cụ thể phụ thuộc framework và phiên bản. Phải xác minh trên stack của dự án trước khi đưa thành yêu cầu cấu hình; không sao chép tên property từ ví dụ của một công nghệ khác rồi coi là đã bảo vệ.

### 9.2. Không mở debug bằng dữ liệu request không tin cậy

Những cơ chế như query parameter `debug=true`, header tự đặt hoặc cookie phát triển có thể tạo kênh bật chi tiết lỗi nếu được nối trực tiếp vào error renderer.

Trong môi trường có người dùng thực, một vai trò quản trị sản phẩm không tự đồng nghĩa có quyền xem stack trace của backend. Nếu tổ chức cần công cụ chẩn đoán từ xa, đó phải là một chức năng nội bộ có xác thực, phân quyền và audit riêng; không phải một tùy chọn biến API công khai thành trang debug.

### 9.3. Môi trường ngoài production cũng có ranh giới

Staging truy cập rộng hoặc có dữ liệu sao chép từ thật vẫn cần kiểm soát lỗi phù hợp. Tên môi trường không quyết định mức nhạy cảm của dữ liệu và khả năng truy cập.

Trên máy phát triển cô lập, trace có thể hữu ích cho lập trình viên. Cần bảo đảm cấu hình thuận tiện đó không tự đi vào artifact hoặc cấu hình triển khai tiếp theo.

## 10. Những đường lỗi dễ bị bỏ sót

### 10.1. Đầu vào không đi tới controller

JSON sai cú pháp, content type không hỗ trợ, body vượt kích thước, path sai kiểu hoặc multipart hỏng có thể được xử lý trước controller. Mỗi trường hợp cần được kiểm tra tại tầng thực sự nhận lỗi.

Thông báo validation cũng cần được kiểm soát. Một thông báo hiển thị toàn bộ rejected value có thể làm lộ password hoặc nội dung riêng tư dù không có trace.

### 10.2. Lỗi được upstream bọc lại

Không trả nguyên body lỗi của database gateway, dịch vụ thanh toán hay HTTP client cho người dùng cuối. Upstream có thể dùng hợp đồng chẩn đoán khác và chứa thông tin mà downstream không được công khai.

Cần ánh xạ lỗi tại ranh giới sở hữu của ứng dụng. Khi muốn truyền một mã lỗi nghiệp vụ của upstream, chỉ truyền mã và nội dung thuộc allowlist đã thống nhất.

### 10.3. Lỗi trong serialization hoặc template

Nếu DTO chứa object miền hoặc exception, serializer có thể duyệt sâu và làm lộ thuộc tính ngoài ý định. Một template lỗi cũng có thể vô tình render biến chẩn đoán.

Sử dụng DTO lỗi tối giản, không cho tùy ý gắn `Map<String, Object>` từ context nội bộ. Với HTML, áp dụng cơ chế escape phù hợp và không chèn input thô vào template; escape giúp bảo vệ cách render, còn việc thông tin nào được công khai vẫn cần policy riêng.

### 10.4. GraphQL, RPC và stream

Với GraphQL, cần kiểm soát nội dung của từng error và phần mở rộng do thư viện hoặc ứng dụng thêm vào. Không dựa hoàn toàn vào status HTTP để xác định lỗi an toàn.

Với RPC, kiểm tra status description, metadata và trường chi tiết lỗi. Đổi tên `stackTrace` thành `details` không thay đổi mức nhạy cảm.

Với WebSocket hoặc server-sent events, cần hợp đồng riêng cho sự kiện lỗi hoặc cách đóng kết nối. Khi một phần dữ liệu đã được gửi, không nối một trang HTML debug hay trace vào cuối luồng.

### 10.5. Dữ liệu lỗi bị lưu ở client hoặc cache

Browser console, công cụ theo dõi lỗi frontend, mobile crash reporter, cache và ticket hỗ trợ có thể giữ response lâu hơn request ban đầu.

`Cache-Control: no-store` là một phần policy cho response không nên được lưu bởi cache tuân thủ chỉ dẫn. Nó không thu hồi bản sao đã tạo, không xóa screenshot và không thay thế việc kiểm soát body lỗi. Cần kiểm tra cả cấu hình cache ở edge và cách client xử lý lỗi.

## 11. Thiết kế kiểm thử theo bằng chứng

### 11.1. Dùng marker tổng hợp và kích hoạt lỗi có chủ đích

Có thể tạo một exception thử với message chứa marker như:

```text
DIAGNOSTIC_ONLY_7C9B
INTERNAL_HOST_FIXTURE_4D2A
SYNTHETIC_SECRET_DO_NOT_EXPORT_8E31
```

Đặt marker khác nhau vào message cấp ngoài, cause và suppressed exception. Sau đó kích hoạt lỗi trong môi trường kiểm soát và xác minh marker không có ở những kênh bị cấm.

Không dùng token đang hoạt động, thông tin khách hàng hay dữ liệu thật để chứng minh cơ chế chống lộ hoạt động.

Marker là một oracle có thể tái hiện, nhưng không phát hiện mọi hình thức tiết lộ. Cần kết hợp kiểm tra schema, xem đường tạo response và quan sát các loại lỗi khác nhau. Nếu có nén hoặc encoding, kiểm tra nội dung sau khi client giải mã; chỉ tìm trên byte nén có thể cho kết quả âm tính giả.

### 11.2. Ma trận kiểm thử minh họa

| Ca | Cách kích hoạt | Điều cần kiểm tra |
|---|---|---|
| TC-01 | Exception ứng dụng chưa được ánh xạ | Mã lỗi bất ngờ cố định; không có message hoặc frame nội bộ |
| TC-02 | Lỗi miền đã được ánh xạ | Status và mã nghiệp vụ đúng; message nội bộ không bị dùng thay thế |
| TC-03 | Exception có nhiều tầng cause và suppressed | Marker ở mọi tầng đều không xuất hiện công khai |
| TC-04 | JSON sai cú pháp hoặc kiểu dữ liệu sai | Parser không trả class, vị trí mã nguồn hoặc payload nhạy cảm |
| TC-05 | Lỗi ở bộ lọc xác thực hoặc phân quyền | Hợp đồng của tầng bảo mật được giữ; không có trace middleware |
| TC-06 | Dependency timeout hoặc trả body lỗi có marker | Body upstream không được chuyển thẳng tới client |
| TC-07 | Serializer hoặc template phát sinh lỗi | Fallback an toàn nếu chưa commit; không có trang debug |
| TC-08 | Yêu cầu cùng route bằng các định dạng hỗ trợ | Body JSON, HTML và header đều tuân theo policy |
| TC-09 | Bật các tùy chọn debug đã nhận diện bằng request | Người gọi thông thường không bật được trace |
| TC-10 | Logger hoặc sink chẩn đoán thất bại | Response vẫn an toàn, không lặp lỗi hoặc đính kèm trace fallback |
| TC-11 | Lỗi sau khi stream đã bắt đầu | Không có trace, dump hoặc template debug nối thêm |
| TC-12 | Gateway tạo lỗi do upstream không sẵn sàng | Trang lỗi của gateway không làm lộ thông tin bị cấm |
| TC-13 | Client nhận response lỗi có marker từ server thử | UI và telemetry không phát tán nội dung thô trái policy |
| TC-14 | Gửi correlation header tùy ý hoặc quá dài | ID nội bộ không bị thay thế; không có log injection hoặc echo không giới hạn |

Một ca thử cần chứng minh đã kích hoạt đúng nhánh lỗi. Nếu dependency thực tế không timeout, việc response không có trace không xác minh được handler timeout.

### 11.3. Đọc cả phần cho phép và phần bị cấm

Một response rỗng do kết nối bị lỗi không đủ để kết luận handler đạt yêu cầu. Với ca phải trả được hợp đồng JSON, cần xác nhận đồng thời:

1. Lỗi thử đã thực sự xảy ra ở tầng mục tiêu.
2. Status và schema phản hồi đúng hợp đồng.
3. Mã lỗi, message và request ID thuộc tập cho phép.
4. Không có marker hoặc thông tin chẩn đoán bị cấm trong body và header.
5. Sự kiện nội bộ liên kết được với request nếu logging được thiết kế thành công trong ca đó.
6. Sự kiện và kênh chẩn đoán cũng không vi phạm policy về dữ liệu nhạy cảm.

Đối với ca cố ý làm đứt stream hoặc tắt tiến trình, oracle phải dùng hợp đồng tương ứng. Không áp yêu cầu “luôn trả JSON hoàn chỉnh” cho những điều kiện không còn khả năng gửi response.

### 11.4. Định lượng trong phạm vi đã chốt

Một tiêu chí nghiệm thu có thể là:

> Trên candidate build và cấu hình được ghi trong hồ sơ, mọi ca thuộc ma trận lỗi bắt buộc cho các route đã liệt kê đều có kết quả; không ca nào phát hành marker chẩn đoán ở kênh bị cấm, và tất cả ca yêu cầu response có cấu trúc đều đạt schema cùng status đã đặc tả.

Tiêu chí này đo được vì biết tập route, tập ca, bản build và điều kiện đạt. Nó không tuyên bố đã chứng minh mọi lỗi có thể xảy ra trong tương lai.

Để lại phần chưa bao phủ dưới dạng bằng chứng còn thiếu hoặc rủi ro cần xử lý, không gộp vào số ca PASS. Khi có route mới, framework mới hoặc error renderer mới, cập nhật ma trận theo phạm vi thay đổi.

## 12. Truy vết rủi ro, thiết kế và tiêu chí nghiệm thu

Một chuỗi truy vết minh họa:

```text
Rủi ro:
  Exception của dependency làm lộ cấu trúc và dữ liệu nội bộ.
    -> Yêu cầu ERR-02, ERR-03, ERR-07
    -> Thiết kế DTO công khai + policy ánh xạ + handler tại từng tầng
    -> Ca TC-01, TC-03, TC-06, TC-07
    -> Bằng chứng response, cấu hình và sự kiện tổng hợp
    -> Quyết định về phần đã đạt và phần chưa được kiểm chứng
```

Một ticket triển khai nên chỉ rõ:

| Trường | Nội dung ví dụ |
|---|---|
| Rủi ro | Người gọi nhận message và trace của dependency |
| Phạm vi | Route và middleware được liệt kê; edge có hạng mục riêng |
| Yêu cầu | Không phát hành trace, cause và message nội bộ; giữ status đúng |
| Thiết kế | DTO công khai, mapper và fallback tối giản |
| Chủ sở hữu | Đội ứng dụng cho mapper; đội nền tảng cho trang lỗi edge |
| Bằng chứng | Response đã giải mã, cấu hình hiệu lực, kết quả ca thử |
| Điều kiện đóng | Các ca bắt buộc đạt; không còn nhánh trong phạm vi chưa có chủ sở hữu |
| Giới hạn | Những giao thức, route hoặc điều kiện chưa được kiểm chứng |

Việc merge một mapper không tự chứng minh gateway hoặc client đã an toàn. Điều kiện đóng phải dựa vào phạm vi yêu cầu, không chỉ tên file được sửa.

Các bằng chứng cũng cần được giảm dữ liệu. Không đính kèm response thực chứa bí mật vào ticket rộng quyền để chứng minh rằng đã tìm thấy lộ thông tin.

## 13. Các cách làm dễ tạo cảm giác đã bảo vệ

| Cách làm | Vấn đề còn lại | Cách đặc tả tốt hơn |
|---|---|---|
| Xóa riêng trường `stackTrace` | Message, cause hoặc HTML vẫn chứa chi tiết | Dùng allowlist cho toàn bộ dữ liệu công khai |
| Trả `getMessage()` cho dễ hỗ trợ | Message có thể chứa truy vấn, input hoặc token | Dùng mã ổn định và request ID |
| Chỉ bắt lỗi ở controller | Parser, middleware, gateway hoặc serializer nằm ngoài | Giao trách nhiệm cho từng tầng |
| Bật debug cho tài khoản quản trị sản phẩm | Quyền nghiệp vụ bị dùng thay quyền chẩn đoán hạ tầng | Có chức năng chẩn đoán nội bộ với quyền riêng |
| Đổi mọi lỗi thành status thành công | Client mất khả năng xử lý đúng, có thể retry sai | Giữ ngữ nghĩa lỗi theo giao thức |
| Chuyển toàn bộ trace sang logging | Log và dịch vụ thu thập trở thành kênh lộ mới | Giảm dữ liệu và phân quyền các sink |
| Dùng regex làm biện pháp duy nhất | Không biết trước mọi định dạng message hoặc bí mật | Giới hạn nguồn dữ liệu và dùng DTO cho phép |
| Chỉ thử một lỗi service | Không bao phủ trước controller và sau commit | Dùng ma trận theo tầng, giao thức và cấu hình |
| Chỉ kiểm tra file cấu hình trong repository | Cấu hình hiệu lực có thể khác khi triển khai | Xác minh cả artifact và môi trường thực thi |
| Bật cảnh báo rồi đóng yêu cầu | Phát hiện không ngăn việc phát hành dữ liệu | Có kiểm soát tại nguồn và tiêu chí nghiệm thu |

## 14. Thực hành đặc tả cho một API đơn hàng

Một API tạo đơn hàng gọi dịch vụ tồn kho và thanh toán. Khi thanh toán timeout, HTTP client tạo exception chứa URL nội bộ và một đoạn body của upstream. Controller hiện trả `exception.getMessage()` cho frontend; frontend gửi toàn bộ lỗi tới dịch vụ theo dõi bên ngoài. Gateway có trang lỗi riêng cho trường hợp backend không sẵn sàng.

Hãy xây dựng một đặc tả gồm:

1. Hai kịch bản rủi ro: một cho response API, một cho kênh telemetry frontend.
2. Danh sách đầu ra và đối tượng được phép nhận từng loại thông tin.
3. Schema lỗi công khai, mã lỗi ổn định và cách tạo request ID.
4. Quy tắc phân biệt lỗi nhập liệu, xung đột và lỗi chưa biết.
5. Hành vi khi kết quả thanh toán chưa xác định, tránh thông báo sai rằng giao dịch chắc chắn chưa xảy ra.
6. Yêu cầu cho handler ứng dụng, trang lỗi gateway và formatter logging.
7. Ca thử có marker trong outer message, cause, suppressed exception và body upstream.
8. Ca thử logger ngừng hoạt động và ca frontend nhận lỗi ngoài hợp đồng.
9. Điều kiện nghiệm thu gắn với build, cấu hình và danh mục route cụ thể.
10. Chủ sở hữu và bằng chứng còn thiếu của từng yêu cầu.

Sản phẩm của bài thực hành là một hợp đồng lỗi có thể kiểm chứng và một chuỗi truy vết từ rủi ro đến bằng chứng. Khả năng hỗ trợ điều tra đến từ mã lỗi, request ID và kênh chẩn đoán được kiểm soát, trong khi phản hồi công khai chỉ chứa những gì người nhận được phép biết.
