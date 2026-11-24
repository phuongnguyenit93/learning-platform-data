# Thiết kế thông báo lỗi đủ chẩn đoán và tránh lộ dữ liệu nhạy cảm

Trong hệ thống RSocket, lỗi có thể xuất hiện khi mở kết nối, thiết lập phiên, xử lý một stream hoặc thực thi nghiệp vụ. Một thông báo lỗi tốt cần giúp client biết nên làm gì tiếp theo và giúp đội vận hành tìm đúng sự cố. Tuy nhiên, nếu trả nguyên exception, stack trace, câu SQL hoặc thông tin nội bộ cho client, hệ thống có thể vô tình tiết lộ dữ liệu nhạy cảm và cấu trúc bên trong.

Thiết kế an toàn cần tách hai mục đích: thông tin công khai dành cho peer và dữ liệu chẩn đoán nội bộ dành cho log, metric và tracing. Hai phần có thể cùng tham chiếu một correlation ID hoặc error ID, nhưng mức chi tiết phải khác nhau.

## 1. Phân biệt lỗi theo phạm vi trong RSocket

Trước khi thiết kế thông báo, cần xác định lỗi thuộc phạm vi nào. RSocket phân biệt lỗi cấp kết nối và lỗi cấp stream bằng `stream ID` trong frame `ERROR`.

| Phạm vi | Dấu hiệu giao thức | Ảnh hưởng |
| --- | --- | --- |
| Connection-level | `ERROR` có `stream ID = 0` | Lỗi ảnh hưởng kết nối; peer thường đóng kết nối |
| Stream-level | `ERROR` có `stream ID` khác `0` | Interaction tương ứng kết thúc; các stream khác trên kết nối có thể tiếp tục |
| Application error (loại lỗi) | Lỗi do validation, quyền, trạng thái nghiệp vụ hoặc xử lý dữ liệu | Thường được biểu diễn bằng application error trên một stream hoặc thành payload lỗi theo hợp đồng ứng dụng |
| Cancellation | Frame `CANCEL` hoặc tín hiệu hủy tương ứng | Dừng interaction theo yêu cầu; không đồng nghĩa với lỗi nghiệp vụ |

Ví dụ lỗi cấp kết nối có thể xảy ra khi `SETUP` không hợp lệ, phiên bản hoặc MIME type không được hỗ trợ, kết nối bị đóng hoặc quá trình resume bị từ chối. Lỗi cấp stream có thể là một request không hợp lệ hoặc một exception phát sinh khi xử lý command.

Frame `ERROR` mang error code và error data. Code cho biết nhóm lỗi theo giao thức, còn error data là nội dung đi kèm; không nên dùng chuỗi error data tùy ý làm hợp đồng máy đọc được nếu chưa định nghĩa format ổn định. Lỗi ứng dụng thường dùng mã `APPLICATION_ERROR`; các lỗi setup, kết nối hoặc request bị từ chối có nhóm mã tương ứng của giao thức. Hãy để thư viện RSocket xử lý mã giao thức và chỉ ánh xạ mã nghiệp vụ ở tầng ứng dụng.

Khi một `Flux` phát `onError`, đó là tín hiệu kết thúc của publisher. Subscriber không nhận thêm `onNext` từ publisher đó sau lỗi. Với RSocket, lỗi stream được truyền trong phạm vi stream tương ứng; không nên mặc định mọi lỗi của một stream đều làm hỏng toàn bộ kết nối.

`CANCEL` là tín hiệu hủy, không phải cách thay thế cho thông báo lỗi. Ví dụ người dùng rời màn hình và hủy stream thì server nên dọn tài nguyên; không cần ghi nhận đó là một sự cố ứng dụng nếu không có lỗi thực sự.

## 2. Phân biệt lỗi giao thức, lỗi vận chuyển và lỗi nghiệp vụ

Một hệ thống dễ chẩn đoán hơn khi phân loại lỗi trước khi quyết định cách phản hồi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transport | TCP reset, WebSocket đóng, timeout mạng | Theo dõi vòng đời kết nối, cân nhắc reconnect và retry có giới hạn |
| Setup / protocol | Setup bị từ chối, MIME type không hỗ trợ, frame không hợp lệ | Ghi nhận lỗi kết nối, sửa cấu hình hoặc phiên bản tương thích |
| Authentication | Token hết hạn hoặc không hợp lệ | Trả mã lỗi an toàn, yêu cầu xác thực lại nếu phù hợp |
| Authorization | Peer không có quyền điều khiển thiết bị | Từ chối thao tác, không tiết lộ tài nguyên ngoài phạm vi |
| Validation | Thiếu field, sai kiểu hoặc giá trị vượt giới hạn | Trả mã lỗi ổn định và chỉ rõ field an toàn cần sửa |
| Business state | Thiết bị đang bảo trì, lệnh xung đột trạng thái | Trả lỗi nghiệp vụ có thể xử lý theo quy trình |
| Dependency | Database hoặc dịch vụ downstream tạm thời không khả dụng | Ghi nhận nguyên nhân nội bộ và quyết định retry theo chính sách |
| Internal | Lỗi lập trình hoặc trạng thái không mong đợi | Trả thông báo chung, giữ chi tiết trong hệ thống chẩn đoán nội bộ |

Không nên gộp mọi lỗi thành một thông báo `Something went wrong`. Client cần biết lỗi có thể sửa bằng cách thay request, xác thực lại, chờ thử lại hay cần người vận hành can thiệp. Ngược lại, không cần trả tên class exception, hostname database hoặc stack trace để client đưa ra quyết định đó.

## 3. Thiết kế hợp đồng lỗi công khai

Thông tin trả cho peer nên ngắn, ổn định và có cấu trúc. Một hợp đồng ứng dụng có thể gồm:

| Trường | Mục đích |
| --- | --- |
| `code` | Mã lỗi máy đọc được, ổn định giữa các phiên bản |
| `message` | Diễn giải ngắn, không chứa chi tiết nội bộ |
| `correlationId` | ID để đối chiếu với log hoặc trace |
| `retryable` | Gợi ý lỗi có thể thử lại theo chính sách hay không |
| `field` | Tên field cần sửa, chỉ dùng với lỗi validation và không chứa giá trị nhạy cảm |

Ví dụ một lỗi nghiệp vụ được biểu diễn dưới dạng payload JSON:

```json
{
  "code": "DEVICE_NOT_READY",
  "message": "Thiết bị hiện chưa sẵn sàng để thực hiện lệnh.",
  "correlationId": "req-8f31c2",
  "retryable": true
}
```

`code` là phần client nên dùng để rẽ nhánh logic. `message` có thể được bản địa hóa hoặc thay đổi câu chữ mà không làm hỏng tích hợp. Không dùng nội dung `message` để quyết định retry hoặc phân quyền.

Đây là một payload theo hợp đồng ứng dụng, không phải cấu trúc bắt buộc của frame RSocket `ERROR`. Nếu API trả error envelope như một payload bình thường, client sẽ nhận một response hợp lệ và cần kiểm tra trường `code`. Nếu để lỗi kết thúc stream, RSocket sẽ truyền lỗi ở cấp stream và client nhận tín hiệu lỗi. Hãy chọn một quy ước nhất quán cho từng route và ghi rõ trong hợp đồng API.

Với lỗi giao thức hoặc lỗi nội bộ bất ngờ, thông tin công khai nên khái quát hơn. Ví dụ: `INTERNAL_ERROR` cùng thông điệp “Không thể hoàn tất yêu cầu lúc này” và một correlation ID. Chi tiết thực tế được lưu ở server để đội vận hành tra cứu.

## 4. Không đưa thông tin nhạy cảm vào thông báo lỗi

Không trả trực tiếp các dữ liệu sau cho client:

- Stack trace, tên package, tên class hoặc đường dẫn file nội bộ.
- Câu SQL, tên bảng, cấu trúc schema, thông tin kết nối database.
- Hostname, IP nội bộ, port, topology hoặc tên dịch vụ downstream.
- Access token, refresh token, API key, cookie, mật khẩu hoặc secret trong metadata.
- Payload đầy đủ có dữ liệu cá nhân, thông tin thiết bị riêng tư hoặc dữ liệu nghiệp vụ nhạy cảm.
- Chi tiết xác thực có thể giúp dò tài khoản, ví dụ phân biệt rõ tài khoản tồn tại và mật khẩu sai khi chính sách yêu cầu thông báo chung.

Thông báo lỗi cũng cần tránh phản chiếu nguyên văn input không tin cậy. Một chuỗi chứa ký tự xuống dòng hoặc nội dung điều khiển có thể làm giả nhiều dòng log, gây khó kiểm tra. Nếu cần đưa giá trị đầu vào vào thông báo validation, hãy giới hạn độ dài, chuẩn hóa và chỉ đưa tên field hoặc vị trí lỗi an toàn.

Ví dụ không an toàn:

```text
Database error: password authentication failed for user app_prod
at com.company.internal.payment.DbRepository.save(DbRepository.java:184)
SQL: INSERT INTO customer_payment_card (...)
```

Thông báo công khai an toàn hơn:

```text
code=INTERNAL_ERROR
message=Không thể lưu yêu cầu lúc này.
correlationId=req-8f31c2
```

Stack trace và nguyên nhân database vẫn có thể được ghi trong hệ thống log nội bộ có kiểm soát quyền truy cập, sau khi áp dụng chính sách redaction phù hợp.

## 5. Correlation ID và tracing giúp tìm đúng sự cố

Một thông báo chung chỉ hữu ích khi người vận hành có thể tìm được sự kiện tương ứng. Correlation ID kết nối thông tin giữa client, server và các dịch vụ downstream.

Luồng xử lý có thể như sau:

```text
Client tạo correlation ID
          |
          v
Gửi ID qua metadata hoặc message context
          |
          v
RSocket server nhận và xác thực định dạng ID
          |
          v
Ghi ID vào log và trace context
          |
          v
Gọi database / service downstream
          |
          v
Lỗi xảy ra -> tạo errorId, giữ correlation ID
          |
          v
Trả mã lỗi an toàn + correlation ID
```

Nếu client không gửi correlation ID, server có thể tạo ID mới. Nếu client gửi, server không nên tin tưởng giá trị tùy ý: giới hạn độ dài, ký tự cho phép và không dùng giá trị này làm căn cứ xác thực. Với tracing phân tán, ưu tiên chuẩn trace context và span ID phù hợp thay vì tự xây dựng một hệ thống ID không tương thích.

Correlation ID có thể được đặt trong metadata hoặc trong message envelope theo hợp đồng ứng dụng. Metadata không tự động được xác thực và không nên chứa secret. Khi đi qua nhiều service, cần truyền trace context đúng chuẩn và ghi nhận span cho từng bước quan trọng.

## 6. Ghi log có cấu trúc ở phía server

Log nên chứa đủ ngữ cảnh để chẩn đoán mà không sao chép toàn bộ payload. Một bản ghi có cấu trúc có thể gồm:

| Trường log | Ví dụ |
| --- | --- |
| `timestamp` | Thời điểm sự cố |
| `service` | `rsocket-device-service` |
| `route` | `devices.control` |
| `interaction` | `REQUEST_CHANNEL` |
| `correlationId` | `req-8f31c2` |
| `errorId` | `err-31a0f9` |
| `errorCode` | `DEVICE_NOT_READY` |
| `streamId` | ID stream nếu có ý nghĩa trong log |
| `durationMs` | Thời gian trước khi lỗi xảy ra |
| `retryAttempt` | Số lần thử hiện tại |
| `outcome` | `REJECTED`, `FAILED` hoặc `CANCELED` |

Ví dụ log dạng JSON:

```json
{
  "timestamp": "2026-11-22T11:30:00Z",
  "service": "rsocket-device-service",
  "route": "devices.control",
  "interaction": "REQUEST_CHANNEL",
  "correlationId": "req-8f31c2",
  "errorId": "err-31a0f9",
  "errorCode": "DEVICE_NOT_READY",
  "durationMs": 84,
  "outcome": "REJECTED"
}
```

Không ghi access token, mật khẩu, cookie, raw authentication metadata hoặc toàn bộ payload. Với dữ liệu có thể định danh người dùng hoặc thiết bị, chỉ ghi định danh nội bộ đã được phê duyệt hoặc dạng rút gọn/hash phù hợp. Log có stack trace cần được lưu ở nơi có quyền truy cập hạn chế và thời gian lưu phù hợp.

`doOnError` phù hợp để quan sát lỗi trong pipeline, nhưng nó không xử lý hoặc phục hồi lỗi. Nếu cần chuyển lỗi sang một trạng thái khác, phải dùng operator như `onErrorMap`, `onErrorResume` hoặc để lỗi lan tới tầng xử lý cao hơn. Không dùng `onErrorComplete()` một cách tùy tiện vì có thể biến một thất bại thực sự thành hoàn tất bình thường và che giấu sự cố.

## 7. Ví dụ Spring RSocket: log nội bộ, thông báo an toàn

Giả sử client gọi route `devices.state`. Server có thể ghi nhận lỗi nội bộ với correlation ID rồi để lỗi được ánh xạ thành application error theo cấu hình của Spring/RSocket:

```java
@Controller
public class DeviceController {

    private final DeviceService deviceService;
    private final DiagnosticLogger diagnostics;

    public DeviceController(
            DeviceService deviceService,
            DiagnosticLogger diagnostics) {
        this.deviceService = deviceService;
        this.diagnostics = diagnostics;
    }

    @MessageMapping("devices.state")
    public Mono<DeviceState> state(DeviceQuery query) {
        return deviceService.findState(query.deviceId())
                .switchIfEmpty(Mono.error(new DeviceNotFoundException()))
                .doOnError(error -> diagnostics.recordFailure(
                        "devices.state",
                        query.correlationId(),
                        error
                ));
    }
}
```

`DiagnosticLogger` là thành phần nội bộ của ứng dụng. Nó cần lọc dữ liệu nhạy cảm và ghi exception ở nơi được kiểm soát quyền truy cập. Không đưa `error.getMessage()` hoặc `error.toString()` trực tiếp vào response gửi client.

Có thể ánh xạ lỗi nghiệp vụ sang mã lỗi công khai bằng một lớp riêng:

```java
public final class SafeApplicationException extends RuntimeException {
    private final String code;

    public SafeApplicationException(String code) {
        super(code); // Chỉ chứa mã công khai, không chứa nguyên nhân nội bộ.
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Ví dụ chuyển một lỗi đã biết:

```java
return deviceService.findState(query.deviceId())
        .switchIfEmpty(Mono.error(new DeviceNotFoundException()))
        .onErrorMap(DeviceNotFoundException.class,
                error -> new SafeApplicationException("DEVICE_NOT_FOUND"));
```

Với exception bất ngờ, hãy ánh xạ sang mã chung như `INTERNAL_ERROR` ở tầng biên thích hợp. Không nên biến mọi lỗi thành cùng một mã nếu client cần phân biệt lỗi validation, quyền truy cập và trạng thái nghiệp vụ.

Trong Spring RSocket, có thể dùng cơ chế xử lý exception của Spring như `@MessageExceptionHandler` hoặc `@ControllerAdvice` tùy phiên bản và phạm vi controller. Nếu handler trả về một DTO `ErrorResponse`, cần hiểu đó là payload theo hợp đồng ứng dụng; client nhận một response bình thường và tự kiểm tra mã lỗi. Nếu muốn lỗi kết thúc stream bằng RSocket application error, hãy để exception được ánh xạ thành lỗi stream theo cơ chế của framework. Không trộn hai quy ước trên trong cùng route mà không định nghĩa rõ.

## 8. Xử lý lỗi ở client mà không làm mất ngữ cảnh

Client cần phân biệt lỗi nghiệp vụ có thể hiển thị cho người dùng, lỗi có thể retry và lỗi kết nối cần tái lập session.

Ví dụ một request-response:

```java
Mono<DeviceState> state = requester
        .route("devices.state")
        .data(query)
        .retrieveMono(DeviceState.class)
        .timeout(Duration.ofSeconds(3))
        .doOnError(error -> clientDiagnostics.recordFailure(
                query.correlationId(), error))
        .onErrorMap(error -> classifyForClient(error));
```

`classifyForClient` nên chuyển exception kỹ thuật thành nhóm lỗi mà tầng giao diện hiểu được, đồng thời giữ correlation ID để hỗ trợ. Không hiển thị nguyên văn message từ server nếu chưa biết nó đã được làm sạch. Với các lỗi stream, client cần xử lý terminal error và quyết định có mở interaction mới hay thông báo người dùng.

Không retry mọi exception. Một chính sách tham khảo:

| Lỗi | Retry? | Hành động |
| --- | --- | --- |
| Validation (`INVALID_ARGUMENT`) | Không | Sửa dữ liệu đầu vào |
| Authentication (`UNAUTHENTICATED`) | Không tự động vô hạn | Làm mới thông tin xác thực hoặc yêu cầu đăng nhập |
| Authorization (`FORBIDDEN`) | Không | Kiểm tra quyền |
| Not found (`NOT_FOUND`) | Thường không | Kiểm tra ID hoặc trạng thái tài nguyên |
| Conflict (`CONFLICT`) | Tùy nghiệp vụ | Đọc trạng thái mới rồi quyết định |
| Rate limited / quota | Có thể | Chờ theo chính sách và giới hạn thử lại |
| Dependency unavailable | Có thể | Backoff có jitter, giới hạn số lần thử |
| Connection reset / transient timeout | Có thể | Reconnect rồi retry nếu thao tác an toàn |
| Internal error không rõ nguyên nhân | Không retry vô hạn | Ghi nhận error ID và áp dụng chính sách giới hạn |

Với thao tác có side effect, retry có thể tạo kết quả trùng nếu server đã thực hiện nhưng response bị mất. Dùng idempotency key hoặc command ID ổn định, và chỉ retry khi hợp đồng nghiệp vụ cho phép.

## 9. Lỗi theo từng interaction model

Các interaction model có cách thể hiện kết quả và lỗi khác nhau:

| Interaction | Khi có lỗi | Điều client cần lưu ý |
| --- | --- | --- |
| Request-response | Response có thể kết thúc bằng lỗi stream hoặc trả error envelope theo hợp đồng | Phân biệt terminal error với payload có `code` lỗi |
| Fire-and-forget | Không có response nghiệp vụ tương ứng cho từng request | Không dựa vào FNF để nhận biên nhận xử lý; cần log, metric hoặc kênh xác minh riêng |
| Request-stream | Lỗi terminal kết thúc stream kết quả | Các phần tử đã nhận vẫn có thể hợp lệ; không chờ thêm `onNext` sau `onError` |
| Request-channel | Lỗi terminal có thể chấm dứt channel | Xác định lỗi command riêng hay lỗi toàn channel; dọn tài nguyên ở hai phía |

Với stream hoặc channel, nếu một phần tử đầu vào lỗi nhưng các phần tử tiếp theo vẫn có thể xử lý, hãy cân nhắc biểu diễn thất bại đó thành một event dữ liệu như `CommandEvent(status=FAILED)`. Cách này cho phép stream tiếp tục. Nếu lỗi khiến giao thức hoặc trạng thái channel không còn an toàn, hãy phát lỗi terminal thay vì che giấu nó thành một event bình thường.

Với Fire-and-Forget, client không có response payload để biết server đã lưu hoặc xử lý xong. Nếu cần xác nhận, dùng request-response riêng để tra cứu trạng thái bằng ID, hoặc chọn interaction model có ACK phù hợp.

## 10. Bảo vệ log và thông báo khỏi dữ liệu không tin cậy

Ngay cả khi không trả stack trace, thông báo lỗi vẫn có thể bị khai thác nếu chứa dữ liệu do client kiểm soát. Hãy áp dụng các nguyên tắc sau:

- Giới hạn độ dài của `message`, `field`, `correlationId` và các giá trị đưa vào log.
- Loại bỏ hoặc escape ký tự điều khiển và xuống dòng trong chuỗi không tin cậy để tránh log injection.
- Không dùng dữ liệu đầu vào làm tên field, tên logger hoặc câu truy vấn động.
- Không phản chiếu raw payload khi validation thất bại.
- Redact token và secret trước khi log; ưu tiên allowlist các trường được phép ghi.
- Tách log vận hành khỏi audit log; chỉ audit những sự kiện cần thiết theo chính sách và giới hạn dữ liệu lưu.
- Đặt retention và quyền truy cập cho log, trace và error store; dữ liệu chẩn đoán cũng cần được bảo vệ.

Correlation ID cũng có thể là dữ liệu do peer gửi. Giới hạn ký tự và độ dài, không dùng ID này làm bằng chứng danh tính, và tránh để một client cố tình tạo ID chứa thông tin cá nhân hoặc chuỗi điều khiển.

## 11. Kiểm thử hợp đồng lỗi

Kiểm thử cần xác nhận cả nội dung công khai và thông tin nội bộ được ghi đúng nơi.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Validation lỗi | Có mã ổn định và thông tin field an toàn; không phản chiếu toàn bộ input |
| Không có quyền | Thông báo không tiết lộ tài nguyên hoặc tài khoản ngoài phạm vi |
| Dependency lỗi | Client nhận mã chung; server log có error ID và ngữ cảnh chẩn đoán |
| Exception bất ngờ | Không có stack trace, SQL hoặc hostname trong response |
| Correlation ID hợp lệ | ID xuất hiện nhất quán trong log/trace và thông tin lỗi |
| Correlation ID sai định dạng | Bị giới hạn, chuẩn hóa hoặc thay bằng ID do server tạo |
| Stream lỗi | Nhận `onError` một lần và không có phần tử sau terminal error |
| Cancel | Tài nguyên được dọn dẹp, không ghi nhầm thành lỗi ứng dụng |
| FNF thất bại ở server | Có log/metric hoặc kênh xác minh phù hợp; client không giả định có ACK |
| Retry side effect | Idempotency key ngăn xử lý trùng theo hợp đồng |

Ví dụ kiểm thử một lỗi validation trong service:

```java
StepVerifier.create(deviceService.validateAndLoad(invalidQuery))
        .expectErrorSatisfies(error -> {
            assertThat(error).isInstanceOf(InvalidDeviceQueryException.class);
        })
        .verify();
```

Với kiểm thử tích hợp RSocket, hãy gọi route thật và xác minh client nhận đúng nhóm lỗi hoặc error envelope đã định nghĩa. Đồng thời kiểm tra log test appender để chắc chắn correlation ID được ghi và secret giả lập không xuất hiện. Không chỉ assert rằng “có exception”; cần kiểm tra mã lỗi, phạm vi stream/kết nối và nội dung không bị lộ.

## 12. Checklist thiết kế thông báo lỗi

- [ ] Phân loại lỗi là transport, setup/protocol, application, validation, authorization hay dependency.
- [ ] Xác định lỗi thuộc connection-level hay stream-level.
- [ ] Dùng mã lỗi công khai ổn định để client xử lý.
- [ ] Giữ message ngắn và không chứa stack trace, SQL, hostname hoặc secret.
- [ ] Gắn correlation ID hoặc error ID để tra cứu log/trace.
- [ ] Ghi log có cấu trúc ở server và redaction trước khi lưu.
- [ ] Phân biệt error frame với error envelope là payload bình thường.
- [ ] Xử lý `onError` đúng cách; không nuốt lỗi bằng `onErrorComplete()` tùy tiện.
- [ ] Chỉ retry lỗi tạm thời và bảo vệ side effect bằng idempotency key.
- [ ] Xử lý riêng FNF, stream, channel và cancellation theo semantics của từng interaction.
- [ ] Kiểm thử response không làm lộ dữ liệu nhạy cảm.

Thông báo lỗi tốt không cần phơi bày toàn bộ nguyên nhân kỹ thuật. Client chỉ cần mã lỗi và hướng xử lý an toàn; đội vận hành cần correlation ID cùng log, metric và trace đủ chi tiết trong môi trường được bảo vệ. Tách hai lớp thông tin này giúp hệ thống RSocket dễ chẩn đoán, giữ được hợp đồng ổn định và hạn chế rò rỉ dữ liệu nhạy cảm.
