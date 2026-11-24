# Che thông tin xác thực trong log, trace và thông báo lỗi

RSocket có thể mang thông tin xác thực trong metadata, dữ liệu SETUP hoặc thông tin gắn với transport. Những giá trị này cần được giữ kín trong suốt vòng đời request. Nếu ứng dụng ghi nguyên payload, metadata, header hoặc exception vào log và trace, credential có thể rời khỏi ranh giới bảo mật dù kết nối đã được mã hóa bằng TLS.

Trong module `INTEGRATION_REALTIME_RSOCKET`, bảo vệ thông tin xác thực không chỉ là kiểm tra token khi nhận request. Ứng dụng còn phải kiểm soát dữ liệu được ghi ra log, gửi tới hệ thống tracing/APM và trả về trong thông báo lỗi. Bài viết này trình bày cách xác định nguồn rò rỉ, chọn dữ liệu được phép quan sát, che thông tin nhạy cảm và kiểm thử để chứng minh credential không xuất hiện ngoài ý muốn.

## 1. Credential có thể xuất hiện ở đâu trong một phiên RSocket?

RSocket trao đổi frame trên TCP hoặc WebSocket. Thông tin xác thực có thể được đưa vào nhiều vị trí tùy cơ chế bảo mật mà ứng dụng chọn:

- **SETUP metadata:** thông tin xác thực hoặc thông tin phiên được gửi khi mở logical connection.
- **Request metadata:** credential hoặc token được gửi cùng từng tương tác nếu ứng dụng thiết kế xác thực ở cấp request.
- **Composite metadata:** một frame metadata có thể chứa route cùng các entry metadata khác, trong đó có entry nhạy cảm.
- **Transport handshake:** WebSocket có thể mang `Authorization`, `Cookie` hoặc header xác thực trong HTTP Upgrade.
- **URI:** query parameter như `access_token` có thể bị ghi trong access log, proxy log hoặc exception nếu dùng token trong URL.
- **Payload data:** password, OTP, API key hoặc thông tin cá nhân có thể vô tình được đưa vào DTO nghiệp vụ.
- **Exception:** lỗi xác thực, lỗi codec hoặc lỗi transport có thể chứa giá trị header, URI, metadata hay payload trong message/cause.

Các giá trị thường phải xem là bí mật gồm access token, refresh token, bearer token, API key, client secret, mật khẩu, cookie phiên, mã OTP, private key và thông tin xác thực database. Không dựa vào tên field để cho rằng một giá trị là an toàn; nội dung tự do cũng có thể chứa credential.

## 2. Những đường rò rỉ phổ biến

Credential thường xuất hiện trong hệ thống quan sát do code ghi log quá rộng hoặc do công cụ tự động thu thập dữ liệu:

| Nguồn | Ví dụ rủi ro | Cách kiểm soát |
|---|---|---|
| Application log | Ghi `request`, `payload`, `metadata` hoặc DTO có token. | Log trường đã chọn; không ghi raw object hay body. |
| Exception log | Ghi toàn bộ message và cause chain có chứa header/URI. | Phân loại lỗi, dùng mã lỗi an toàn và chỉ log exception đã kiểm soát. |
| Reactor/Netty wiretap | Ghi byte/frame hoặc HTTP handshake của WebSocket. | Tắt payload-level wiretap trong production; chỉ bật chẩn đoán có kiểm soát. |
| Distributed trace | Gắn token, header hoặc metadata vào span attribute. | Dùng allowlist attribute và bộ lọc trước khi export. |
| Baggage/MDC | Đưa credential vào context để truyền qua nhiều service. | Chỉ truyền correlation ID và thuộc tính không nhạy cảm. |
| Metrics | Dùng token hoặc user identifier làm label. | Chỉ dùng label có cardinality thấp và không nhạy cảm. |
| Proxy/access log | Ghi URI query hoặc WebSocket request headers. | Không đặt token trong URL; cấu hình bỏ header nhạy cảm khỏi log. |

TLS bảo vệ dữ liệu trên đường truyền giữa các endpoint. TLS không che credential khỏi ứng dụng sau khi giải mã, khỏi log ở endpoint, agent tracing, crash dump hoặc hệ thống APM nhận dữ liệu đã giải mã.

## 3. Thiết kế logging theo allowlist

Thay vì ghi toàn bộ request rồi tìm cách xóa bí mật, hãy xác định trước những trường nào được phép ghi. Với một request RSocket, log thường chỉ cần:

- Route template hoặc tên thao tác đã chuẩn hóa.
- Interaction model: Request-Response, Fire-and-Forget, Request-Stream hoặc Request-Channel.
- Correlation ID hoặc trace ID không chứa thông tin xác thực.
- Kết quả xử lý và mã lỗi đã chuẩn hóa.
- Thời gian xử lý, số byte hoặc số phần tử nếu cần cho vận hành.
- Định danh principal dạng nội bộ/pseudonymous chỉ khi chính sách dữ liệu cho phép.

Không ghi raw `Payload`, `ByteBuf`, `DataBuffer`, metadata map, authentication object, DTO chứa secret hoặc `Principal` chưa được đánh giá. Ngay cả `toString()` của một object tưởng như vô hại cũng có thể in mọi field của nó.

Ví dụ log an toàn cho một handler:

```java
@MessageMapping("devices.status.get")
public Mono<DeviceStatus> status(
        @Payload StatusQuery query,
        Principal principal) {

    String correlationId = Correlation.currentId();
    String route = "devices.status.get";

    log.info(
        "RSocket request received route={} interaction={} correlationId={}",
        route,
        "request-response",
        correlationId
    );

    return deviceService.getStatus(query.deviceId(), principal);
}
```

`Correlation.currentId()` là API minh họa của ứng dụng. Correlation ID phải được tạo hoặc xác thực ở ranh giới tin cậy; không lấy một giá trị tùy ý từ client rồi coi nó là định danh an toàn. Ví dụ không ghi `query`, `principal`, metadata hoặc token.

### 3.1. Ghi kết quả xác thực mà không ghi credential

Khi xác thực thất bại, log nên ghi lý do đã phân loại thay vì dữ liệu credential:

```java
void logAuthenticationFailure(String route, String correlationId,
                              AuthenticationFailure failure) {
    log.warn(
        "RSocket authentication rejected route={} code={} correlationId={}",
        route,
        failure.safeCode(),
        correlationId
    );
}
```

`safeCode()` chỉ trả mã đã định nghĩa trước như `TOKEN_EXPIRED`, `TOKEN_INVALID` hoặc `PRINCIPAL_NOT_ALLOWED`. Không đưa token, header, raw exception message hay nội dung metadata vào tham số log. Nếu cần điều tra sâu, dùng event ID và kho chẩn đoán có quyền truy cập hạn chế; không sao chép credential vào đó.

### 3.2. Redaction là lớp phòng vệ thứ hai

Một số hệ thống phải ghi map thuộc tính động. Khi đó, cần lọc key nhạy cảm trước khi log:

```java
private static final Set<String> SENSITIVE_KEYS = Set.of(
    "authorization",
    "proxy_authorization",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "api_key",
    "cookie",
    "set_cookie"
);

static Object safeLogValue(String key, Object value) {
    String normalized = key.toLowerCase(Locale.ROOT).replace('-', '_');

    if (SENSITIVE_KEYS.contains(normalized)
            || normalized.endsWith("_token")
            || normalized.endsWith("_secret")) {
        return "[REDACTED]";
    }

    return value;
}
```

Đây chỉ là ví dụ tối thiểu cho một map phẳng. Trong ứng dụng thật, bộ lọc cần xử lý key không phân biệt hoa thường, map lồng nhau, collection, tên field viết theo nhiều quy ước và các giá trị tự do có thể chứa bí mật. Không coi đoạn code này là bộ lọc hoàn chỉnh cho mọi cấu trúc dữ liệu.

Redaction theo key không thể phát hiện mọi token được nhúng trong chuỗi như `"request failed for Bearer ..."`. Vì vậy, allowlist trường được ghi vẫn là lớp bảo vệ chính; redaction theo key và pattern chỉ là lớp phòng vệ bổ sung.

## 4. Không ghi raw metadata hoặc payload RSocket

Metadata có thể chứa route, authentication metadata, MIME type hoặc context riêng. Payload data có thể chứa DTO nghiệp vụ. Không nên log toàn bộ metadata/payload để tiện debug:

```java
// Không nên: có thể làm lộ credential hoặc dữ liệu nghiệp vụ.
log.debug("RSocket metadata={}", metadata);
log.debug("RSocket payload={}", payload);
```

Hãy trích xuất những trường đã được phép ghi, ví dụ route đã chuẩn hóa và interaction model. Nếu metadata là composite/opaque hoặc chứa entry không biết trước, coi toàn bộ phần đó là nhạy cảm và không log. Không decode credential chỉ để ghi log.

Không đưa token vào route, URI query string hoặc tên stream. Route nên là tên thao tác ổn định; định danh tài nguyên có thể nằm trong payload hoặc route variable theo hợp đồng ứng dụng, nhưng vẫn cần đánh giá PII và cardinality trước khi ghi vào log.

## 5. Che credential trong distributed trace

Trace giúp nối các span qua client, server và downstream service. Span nên mô tả hoạt động và kết quả, không chứa bí mật cần dùng để thực hiện hoạt động đó.

Các thuộc tính thường an toàn hơn khi đã được chuẩn hóa:

| Thuộc tính trace | Giá trị nên ghi |
|---|---|
| Route | Route template hoặc tên thao tác đã chuẩn hóa. |
| Interaction | `request-response`, `fire-and-forget`, `request-stream`, `request-channel`. |
| Transport | `tcp` hoặc `websocket`. |
| Kết quả | `success`, `error` hoặc mã lỗi nội bộ đã chuẩn hóa. |
| Thời lượng | Thời gian xử lý hoặc thời gian chờ. |
| Correlation | Trace ID/span ID do hệ thống tracing quản lý. |

Không gắn các giá trị sau vào span attribute, event hoặc baggage:

- `Authorization`, bearer token, API key, password, cookie hoặc refresh token.
- Raw SETUP metadata, request metadata hoặc payload data.
- URI có query chứa credential.
- Exception message chưa được làm sạch.
- Baggage chứa thông tin xác thực để truyền sang downstream service.

Ví dụ tạo thuộc tính span từ dữ liệu đã được chọn:

```java
span.setAttribute("rsocket.route.template", "devices.status.get");
span.setAttribute("rsocket.interaction", "request-response");
span.setAttribute("rsocket.transport", "tcp");
span.setAttribute("rsocket.outcome", "error");
span.setAttribute("error.code", "AUTHENTICATION_FAILED");
```

Không dùng raw route có chứa giá trị động hoặc principal email làm nhãn nếu không cần thiết. Các giá trị động có thể làm tăng cardinality, lộ thông tin cá nhân và khiến việc tìm kiếm trace khó kiểm soát.

### 5.1. Kiểm soát instrumentation tự động

Agent APM hoặc instrumentation tự động có thể thu thập HTTP header, messaging metadata, exception message và request attributes mà code ứng dụng không gọi `log.info()` trực tiếp. Vì vậy:

1. Kiểm kê các instrumentation đang bật cho Spring, Reactor Netty, RSocket và WebSocket.
2. Tắt capture body/header/metadata nếu không có nhu cầu vận hành đã được phê duyệt.
3. Dùng allowlist cho header và span attribute; loại bỏ `authorization`, `cookie`, `set-cookie` và các trường credential khác.
4. Áp dụng processor/filter trước khi export tới collector hoặc APM.
5. Kiểm tra dữ liệu ở cả ứng dụng, collector và backend; không chỉ kiểm tra log local.

Tên API cấu hình phụ thuộc thư viện tracing/APM và phiên bản đang dùng. Cần cấu hình theo đúng agent/SDK trong hệ thống; không giả định một thuộc tính cấu hình chung sẽ tự lọc mọi loại RSocket metadata.

## 6. Baggage, MDC và context propagation

Baggage và MDC thường được dùng để mang correlation ID, tenant context hoặc thông tin phục vụ chẩn đoán qua nhiều thread và service. Đây là dữ liệu có thể được tự động sao chép vào log hoặc trace của downstream.

Chỉ truyền dữ liệu tối thiểu cần thiết:

- Correlation ID được tạo/kiểm tra tại ranh giới tin cậy.
- Tên service hoặc operation đã chuẩn hóa.
- Tenant reference dạng nội bộ nếu chính sách cho phép.
- Trace context do instrumentation quản lý.

Không đặt access token, refresh token, password, session cookie hoặc API key vào MDC, baggage hay custom context. Nếu downstream cần xác thực, chuyển credential qua kênh xác thực được thiết kế cho mục đích đó; không tái sử dụng tracing context làm kênh truyền bí mật.

Khi nhận correlation ID từ client, giới hạn độ dài, ký tự hợp lệ và loại bỏ giá trị có thể chứa thông tin nhạy cảm. Không dùng correlation ID do người dùng tùy ý cung cấp làm metric label không giới hạn.

## 7. Thông báo lỗi an toàn cho client

Thông báo lỗi gửi về client nên đủ để client biết loại lỗi và cách xử lý tiếp theo, nhưng không tiết lộ credential, cấu trúc nội bộ, host, stack trace hoặc nội dung request.

Một error response có thể chứa:

- Mã lỗi ổn định, ví dụ `AUTHENTICATION_FAILED`, `ACCESS_DENIED`, `INVALID_REQUEST`.
- Thông điệp ngắn, không chứa giá trị đầu vào nhạy cảm.
- Correlation ID để bộ phận hỗ trợ tìm log đã được làm sạch.
- Gợi ý hành động an toàn, ví dụ xác thực lại hoặc liên hệ quản trị viên.

Ví dụ DTO:

```java
public record SafeErrorResponse(
    String code,
    String message,
    String correlationId
) {}
```

Ví dụ xử lý lỗi xác thực:

```java
SafeErrorResponse toSafeError(String correlationId) {
    return new SafeErrorResponse(
        "AUTHENTICATION_FAILED",
        "Authentication failed. Check your credentials and try again.",
        correlationId
    );
}
```

Không trả các thông tin như `Bearer ey...`, token hết hạn có giá trị gì, header nhận được, nội dung metadata, tên secret trong vault hoặc exception message của thư viện xác thực. Cũng không trả stack trace hay cause chain cho client production.

### 7.1. Xử lý lỗi mà không log exception message thô

Exception từ thư viện bên dưới có thể chứa URL, header hoặc giá trị đầu vào. Thay vì log toàn bộ exception trong mọi trường hợp, hãy phân loại lỗi và ghi mã an toàn:

```java
void recordAuthFailure(Throwable error, String correlationId) {
    String code = classifyAuthenticationError(error);
    String type = error.getClass().getSimpleName();

    log.warn(
        "RSocket authentication failed code={} exceptionType={} correlationId={}",
        code,
        type,
        correlationId
    );
}
```

`classifyAuthenticationError` phải ánh xạ sang danh sách mã đã định nghĩa, không lấy `error.getMessage()` làm mã. Ví dụ này không log stack trace. Nếu cần stack trace để điều tra, chỉ ghi ở hệ thống chẩn đoán được kiểm soát sau khi xác nhận cause chain không chứa credential; quyền truy cập và thời gian lưu phải được giới hạn.

### 7.2. Phân biệt lỗi theo interaction model

| Interaction model | Cách lỗi đến client | Nguyên tắc bảo vệ |
|---|---|---|
| Request-Response | Tương tác kết thúc bằng lỗi hoặc application error. | Trả mã lỗi và thông điệp an toàn; không trả exception message thô. |
| Fire-and-Forget | Không có response payload nghiệp vụ. | Ghi nhận lỗi phía server bằng log an toàn; nếu cần xác nhận, thiết kế receipt riêng. |
| Request-Stream | Stream có thể kết thúc bằng lỗi sau một số payload. | Không phát credential trong error frame; kết thúc với mã lỗi đã chuẩn hóa. |
| Request-Channel | Một lỗi có thể kết thúc channel hai chiều. | Làm sạch lỗi ở boundary và dọn tài nguyên của cả hai hướng. |

## 8. Không để debug logging làm lộ dữ liệu

Trong quá trình xử lý sự cố, nhóm phát triển thường bật DEBUG hoặc wiretap để xem frame. Đây là một trong những đường rò rỉ khó phát hiện vì log có thể chứa dữ liệu đã được giải mã ở endpoint.

- Không bật payload-level wiretap hoặc dump raw frame liên tục trong production.
- Kiểm tra mức log của `io.rsocket`, `reactor.netty`, HTTP client/server và các thư viện codec.
- Nếu cần chẩn đoán, dùng dữ liệu test đã giả lập, giới hạn thời gian, phạm vi service và quyền truy cập.
- Tránh ghi raw WebSocket handshake headers hoặc URI query string.
- Tắt chế độ chẩn đoán sau khi hoàn tất và xóa dữ liệu tạm theo chính sách retention.
- Không gửi log có credential tới ticket, chat, email hoặc hệ thống hỗ trợ bên ngoài.

Log level DEBUG không tự động có nghĩa là credential chắc chắn bị ghi; rủi ro phụ thuộc logger/wiretap được cấu hình. Tuy nhiên, cần kiểm tra nội dung thực tế trước khi bật và không giả định TLS sẽ bảo vệ log sau khi dữ liệu đã tới endpoint.

## 9. Quy trình redaction ở các ranh giới

Nên áp dụng kiểm soát theo nhiều lớp:

1. **Lúc nhận request:** không log raw headers, SETUP metadata, composite metadata hoặc payload; chỉ trích xuất route/operation đã được cho phép.
2. **Trong service:** không đưa credential vào DTO loggable, `toString()`, exception message hoặc MDC.
3. **Khi ghi log:** dùng structured logging với allowlist; áp dụng redaction như lớp phòng vệ thứ hai.
4. **Khi tạo trace:** chỉ thêm attribute đã chuẩn hóa; lọc header và event trước khi export.
5. **Khi trả lỗi:** ánh xạ sang error code/message an toàn, không trả cause hoặc stack trace.
6. **Ở hạ tầng:** cấu hình proxy, collector, APM và log backend không lưu header/query nhạy cảm; giới hạn quyền truy cập và retention.

Không dựa vào một bộ lọc regex ở cuối pipeline để sửa tất cả dữ liệu. Tại thời điểm log hoặc trace được tạo, credential đã có thể bị sao chép sang nhiều hệ thống. Ngăn dữ liệu nhạy cảm đi vào telemetry ngay từ đầu là biện pháp đáng tin cậy hơn.

## 10. Kiểm thử không rò rỉ credential

Kiểm thử bảo mật cần chứng minh rằng một credential giả lập không xuất hiện trong log, trace hoặc error response ở cả đường thành công lẫn thất bại.

Một bộ test có thể tạo canary secret riêng cho từng lần chạy:

```java
String canaryToken = "test-secret-DO-NOT-LOG-7f31";

// Gửi request với credential giả lập và cố ý kích hoạt lỗi xác thực.
// Thu log, span attributes/events và response body từ test harness.

assertThat(capturedLogs).doesNotContain(canaryToken);
assertThat(exportedSpans).doesNotContain(canaryToken);
assertThat(errorResponse).doesNotContain(canaryToken);
```

Đoạn code minh họa các điểm cần kiểm tra; `capturedLogs`, `exportedSpans` và `errorResponse` là dữ liệu thu từ test harness của ứng dụng.

Các tình huống nên kiểm tra:

1. Token hợp lệ và không hợp lệ trong authentication metadata.
2. Credential trong SETUP metadata và request metadata.
3. WebSocket `Authorization`/`Cookie` header và URI có query parameter nhạy cảm.
4. Payload chứa password, OTP hoặc API key do client gửi sai hợp đồng.
5. Lỗi từ decoder, authentication provider, transport và downstream client.
6. Exception có cause chain chứa chuỗi canary; xác nhận stack trace không được export vào log/trace thông thường.
7. Bật DEBUG/wiretap trong môi trường test; xác nhận chính sách không thu raw credential hoặc kiểm soát được dữ liệu dump.
8. Kiểm tra log backend, trace collector và APM export, không chỉ kiểm tra log trong bộ nhớ của unit test.

Ngoài kiểm tra `doesNotContain`, hãy xác nhận những trường vận hành an toàn vẫn có mặt như route template, error code và correlation ID. Mục tiêu là giữ khả năng điều tra mà không phải lưu bí mật.

## 11. Checklist trước khi triển khai

- Credential không nằm trong route, URL query string, log message hoặc metric label.
- SETUP/authentication metadata và WebSocket headers được xem là dữ liệu nhạy cảm.
- Không log raw `Payload`, `ByteBuf`, `DataBuffer`, DTO chứa secret hoặc auth object.
- Structured log dùng allowlist và redaction theo key chỉ làm lớp phụ.
- Trace attribute/baggage/MDC không chứa credential; instrumentation tự động đã được kiểm tra.
- Exception message/cause chain không được trả nguyên văn cho client.
- Error response chỉ có mã lỗi, thông điệp an toàn và correlation ID.
- Wiretap/raw frame logging được tắt hoặc kiểm soát chặt.
- Có test canary secret qua log, trace, exception và error response.
- Log/trace backend có quyền truy cập, retention và quy trình xử lý sự cố phù hợp.

## 12. Kết luận

Che credential hiệu quả bắt đầu bằng việc không đưa bí mật vào telemetry. Hãy dùng allowlist cho log và trace, tránh raw payload/metadata/header, không đưa token vào baggage/MDC/URL, và ánh xạ lỗi sang mã cùng thông điệp an toàn. Redaction theo key, bộ lọc instrumentation và kiểm soát backend là các lớp bổ sung. Cuối cùng, dùng canary secret để kiểm thử toàn bộ đường đi từ RSocket SETUP/request đến log, trace, exception và error response, bảo đảm credential không rời khỏi ranh giới xác thực.
