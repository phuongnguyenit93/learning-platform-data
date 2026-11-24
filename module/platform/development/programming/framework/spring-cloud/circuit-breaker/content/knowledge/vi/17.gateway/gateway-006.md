# Truyền nguyên nhân fallback và tránh lộ chi tiết nội bộ

Spring Cloud Gateway có thể dùng CircuitBreaker GatewayFilter để bảo vệ một route gọi đến dịch vụ phía sau. Khi lời gọi thất bại hoặc Circuit Breaker từ chối request, filter có thể chuyển luồng xử lý đến một fallback endpoint nội bộ. Endpoint này cần biết nguyên nhân để ghi nhận và chọn cách phản hồi phù hợp, nhưng không được đưa exception, địa chỉ nội bộ hay thông tin triển khai ra response công khai.

Gateway cung cấp nguyên nhân kích hoạt fallback qua thuộc tính của ServerWebExchange. Với Gateway reactive, handler có thể đọc thuộc tính này, phân loại exception, ghi log cùng request ID và trả một response đã được chuẩn hóa. Cách làm đúng giúp nhóm vận hành điều tra sự cố mà client chỉ nhận được mã lỗi và thông báo an toàn.

## 1. Luồng fallback của CircuitBreaker GatewayFilter

CircuitBreaker GatewayFilter bao quanh lời gọi route. Nếu downstream trả kết quả bình thường và không có điều kiện lỗi được cấu hình, response tiếp tục về client. Nếu lời gọi phát sinh exception hoặc response status nằm trong danh sách được cấu hình để xem là lỗi, filter có thể chuyển request đến fallback URI.

Với Gateway reactive, fallback URI thường dùng scheme forward để chuyển tiếp nội bộ đến một handler trong cùng ứng dụng Gateway. Đây là forward nội bộ, không phải HTTP redirect đến một URL bên ngoài.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Client gửi request] --> B[Spring Cloud Gateway route]
    B --> C[CircuitBreaker GatewayFilter]
    C --> D{Lời gọi downstream}
    D -- Thành công --> E[Trả response downstream]
    D -- Exception hoặc status được cấu hình --> F[Forward đến fallback URI]
    F --> G[Đọc nguyên nhân từ ServerWebExchange]
    G --> H[Phân loại nguyên nhân nội bộ]
    H --> I[Ghi log và metric an toàn]
    I --> J[Trả response fallback đã chuẩn hóa]
~~~

Nguyên nhân lỗi được lưu trong thuộc tính exchange có tên hằng số:

~~~java
ServerWebExchangeUtils.CIRCUITBREAKER_EXECUTION_EXCEPTION_ATTR
~~~

Hằng số này thuộc lớp ServerWebExchangeUtils của Spring Cloud Gateway. Handler fallback có thể lấy Throwable từ ServerWebExchange để biết lỗi nào đã dẫn đến fallback.

Không nên nhầm cơ chế này với FallbackFactory của OpenFeign. OpenFeign truyền nguyên nhân vào phương thức create(Throwable) của FallbackFactory. Gateway filter lưu nguyên nhân vào attribute của ServerWebExchange để fallback handler đọc trong request context.

## 2. Cấu hình route với fallbackUri

Ví dụ Gateway chuyển tiếp các request tồn kho đến dịch vụ inventory và dùng fallback endpoint nội bộ khi Circuit Breaker kích hoạt:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
                statusCodes:
                  - 500
                  - 503
~~~

Giải thích:

- inventory-route là ID của route Gateway.
- lb://inventory-service yêu cầu cơ chế service discovery/load balancer phân giải dịch vụ đích.
- Path xác định request được route xử lý.
- CircuitBreaker filter dùng instance có tên inventory.
- fallbackUri chuyển nội bộ đến handler /fallback/inventory.
- statusCodes liệt kê những HTTP status downstream cần được xem là lỗi để Circuit Breaker xử lý.

Danh sách statusCodes là tùy chọn. Nếu downstream trả HTTP 503 như một response bình thường và status đó không được cấu hình là lỗi, Gateway có thể chuyển response về client thay vì chạy fallback. Hãy chọn status theo hợp đồng API của downstream; không nên coi mọi mã 4xx là lỗi hạ tầng vì 404 hoặc 409 có thể là kết quả nghiệp vụ hợp lệ.

Tên inventory trong cấu hình Circuit Breaker nên thống nhất với tên instance Resilience4j nếu ứng dụng dùng Resilience4j. Cần bật starter Circuit Breaker reactive phù hợp với phiên bản Spring Cloud Gateway và Spring Boot của dự án.

Fallback URI với forward scheme phải trỏ đến handler nội bộ có thể được Gateway dispatch. Không đặt một URL public tùy ý vào fallbackUri với kỳ vọng filter sẽ thực hiện redirect. Nếu cần gọi một dịch vụ fallback từ xa, hãy thiết kế lời gọi đó như một dependency riêng, có timeout và cơ chế bảo vệ riêng.

## 3. Đọc nguyên nhân từ ServerWebExchange

Fallback controller có thể nhận ServerWebExchange và đọc attribute do CircuitBreaker GatewayFilter đặt:

~~~java
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class InventoryFallbackController {

    @RequestMapping("/fallback/inventory")
    public Mono<ResponseEntity<GatewayFallbackResponse>> inventoryFallback(
            ServerWebExchange exchange) {

        Throwable cause = exchange.getAttribute(
                ServerWebExchangeUtils.CIRCUITBREAKER_EXECUTION_EXCEPTION_ATTR);

        String requestId = exchange.getRequest().getId();
        FailureKind kind = classify(cause);

        // Chỉ ghi thông tin đã được kiểm soát vào log vận hành.
        logFallback(requestId, kind, cause);

        GatewayFallbackResponse response = new GatewayFallbackResponse(
                "INVENTORY_TEMPORARILY_UNAVAILABLE",
                "Dịch vụ tồn kho hiện chưa thể xử lý yêu cầu.",
                requestId
        );

        return Mono.just(
                ResponseEntity.status(publicStatus(kind)).body(response)
        );
    }
}
~~~

Ví dụ dùng một DTO công khai:

~~~java
public record GatewayFallbackResponse(
        String code,
        String message,
        String requestId) {
}
~~~

Attribute có thể không tồn tại trong một số đường xử lý khác hoặc khi handler được gọi trực tiếp. Vì vậy, cần xử lý trường hợp cause là null và phân loại thành UNKNOWN thay vì giả định luôn có exception.

Request ID của exchange có thể dùng để đối chiếu log ở Gateway. Nếu hệ thống đã có correlation ID hoặc trace ID từ tracing infrastructure, hãy dùng giá trị đã được xác thực và quản lý bởi hệ thống. Không tin tưởng vô điều kiện một header do client tự gửi để làm định danh đáng tin cậy.

## 4. Phân loại nguyên nhân mà không đưa exception ra client

Fallback handler thường cần phân biệt một số nhóm lỗi:

- Circuit Breaker OPEN: lời gọi mới bị từ chối trước khi gửi đến downstream.
- Timeout: downstream hoặc đường truyền không phản hồi trong thời hạn.
- Lỗi kết nối: không thể thiết lập hoặc duy trì kết nối.
- Lỗi upstream khác: downstream trả lỗi hoặc client phát sinh exception khác.
- Unknown: không tìm được nguyên nhân cụ thể.

Có thể phân loại bằng loại exception trong cause chain:

~~~java
import java.net.ConnectException;
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

enum FailureKind {
    CIRCUIT_OPEN,
    TIMEOUT,
    CONNECTION_FAILURE,
    UPSTREAM_FAILURE,
    UNKNOWN
}

private FailureKind classify(Throwable cause) {
    if (hasCause(cause, CallNotPermittedException.class)) {
        return FailureKind.CIRCUIT_OPEN;
    }

    if (hasCause(cause, TimeoutException.class)) {
        return FailureKind.TIMEOUT;
    }

    if (hasCause(cause, ConnectException.class)) {
        return FailureKind.CONNECTION_FAILURE;
    }

    if (cause != null) {
        return FailureKind.UPSTREAM_FAILURE;
    }

    return FailureKind.UNKNOWN;
}

private boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return false;
}
~~~

Các exception thực tế phụ thuộc HTTP client, adapter Circuit Breaker và phiên bản thư viện. Ví dụ, timeout có thể xuất hiện dưới dạng exception của Reactor Netty, WebClient hoặc một wrapper của framework. Lỗi DNS, TLS và connection reset cũng có thể có kiểu khác ConnectException.

Do đó, helper trên là điểm khởi đầu. Hãy quan sát cause chain thực tế ở môi trường phát triển, rồi bổ sung loại exception cần thiết. Tránh phân loại dựa trên nội dung message vì message có thể thay đổi theo phiên bản hoặc chứa chi tiết nhạy cảm.

## 5. Ánh xạ nguyên nhân nội bộ sang response công khai

Ứng dụng có thể giữ nguyên nhân chi tiết trong log, nhưng response cho client nên dùng mã lỗi ổn định và thông báo tổng quát.

Ví dụ ánh xạ status:

~~~java
private HttpStatus publicStatus(FailureKind kind) {
    return switch (kind) {
        case TIMEOUT -> HttpStatus.GATEWAY_TIMEOUT;
        case CIRCUIT_OPEN,
             CONNECTION_FAILURE,
             UPSTREAM_FAILURE,
             UNKNOWN -> HttpStatus.SERVICE_UNAVAILABLE;
    };
}
~~~

Có thể dùng cùng một response body tổng quát cho nhiều nguyên nhân để tránh tiết lộ cấu trúc nội bộ:

~~~json
{
  "code": "INVENTORY_TEMPORARILY_UNAVAILABLE",
  "message": "Dịch vụ tồn kho hiện chưa thể xử lý yêu cầu.",
  "requestId": "a-server-generated-request-id"
}
~~~

Client biết rằng thao tác chưa thể hoàn tất và có requestId để cung cấp khi liên hệ hỗ trợ. Client không cần biết Circuit Breaker đang OPEN, hostname nào bị lỗi, class exception nào được ném ra hoặc port nội bộ của downstream.

Nếu API có quy ước lỗi chung, hãy dùng cùng envelope và tên field với các endpoint còn lại. Không nên để mỗi fallback endpoint tự tạo một định dạng response khác nhau.

## 6. Thông tin nào không được trả ra ngoài?

Throwable có thể chứa nhiều dữ liệu hữu ích cho người vận hành nhưng không phù hợp với client công khai. Không trả trực tiếp cause.getMessage(), cause.toString() hoặc stack trace trong response.

Các thông tin cần giữ trong vùng log/trace nội bộ:

- Tên class exception và cause chain.
- Hostname, IP, port hoặc URI nội bộ của downstream.
- Chi tiết DNS, TLS, connection pool và network.
- Tên route nội bộ, tên service discovery và topology.
- Stack trace, tên package và vị trí dòng code.
- SQL, câu lệnh nội bộ hoặc nội dung request/response.
- Token, cookie, header xác thực và dữ liệu cá nhân.
- Tên instance Circuit Breaker và cấu hình vận hành nếu không cần công khai.

Một response công khai an toàn chỉ nên có:

- Mã lỗi ổn định để client xử lý.
- Thông báo ngắn, không mô tả hạ tầng.
- HTTP status phù hợp.
- Request ID hoặc correlation ID đã được kiểm soát.
- Có thể có retry hint nếu chính sách API hỗ trợ và giá trị đó có căn cứ.

Không nên trả một thông báo kiểu "Connection refused at inventory-db.internal:8443" hoặc "CallNotPermittedException from inventoryCircuitBreaker". Những chi tiết đó có thể giúp người ngoài suy ra kiến trúc, tên host và công nghệ nội bộ.

## 7. Ghi log nguyên nhân trong vùng vận hành

Fallback cần tạo đủ thông tin để nhóm vận hành điều tra. Nên ghi request ID, route ID, failure kind, tên dependency và exception type. Stack trace có thể được ghi ở log nội bộ có kiểm soát khi cần điều tra, nhưng phải tránh ghi token, payload nhạy cảm hoặc toàn bộ header.

Ví dụ:

~~~java
private void logFallback(
        String requestId,
        FailureKind kind,
        Throwable cause) {

    String exceptionType = cause == null
            ? "none"
            : cause.getClass().getName();

    log.warn(
            "Gateway fallback activated: route=inventory, requestId={}, kind={}, exceptionType={}",
            requestId,
            kind,
            exceptionType
    );

    if (cause != null) {
        log.debug(
                "Gateway fallback cause details: requestId={}",
                requestId,
                cause
        );
    }
}
~~~

Nếu bật debug log để ghi stack trace, cần bảo đảm log sink có quyền truy cập phù hợp, retention hợp lý và cơ chế che dữ liệu nhạy cảm. Không ghi nguyên nhân chi tiết ở mức INFO/WARN nếu message có thể chứa URL hoặc dữ liệu đầu vào không đáng tin cậy.

Không nên chỉ ghi "fallback happened" mà thiếu request ID và loại nguyên nhân. Khi nhiều request đồng thời gặp lỗi, log không có correlation sẽ khó liên kết với trace hoặc request của client.

## 8. Fallback có thể trả dữ liệu suy giảm hoặc lỗi có kiểm soát

Không phải fallback nào cũng cần trả 503. Lựa chọn phụ thuộc nghiệp vụ:

- Nếu không có dữ liệu thay thế an toàn, trả 503 hoặc 504 với error envelope chuẩn.
- Nếu có cache đủ mới và nghiệp vụ cho phép dữ liệu cũ, có thể trả dữ liệu cache cùng metadata thể hiện nguồn dữ liệu và thời điểm cập nhật.
- Nếu một phần response vẫn dùng được, có thể trả kết quả suy giảm có đánh dấu rõ ràng.
- Nếu thao tác là giao dịch quan trọng như thanh toán hoặc tạo đơn hàng, không giả vờ thành công khi không xác định được kết quả phía downstream.

Ví dụ DTO thể hiện dữ liệu cache:

~~~java
public record InventoryFallbackResponse(
        String sku,
        Integer availableQuantity,
        boolean degraded,
        String source,
        Instant cachedAt) {
}
~~~

Nếu dùng cache, fallback cần kiểm tra freshness. Dữ liệu tồn kho cũ có thể gây oversell; dữ liệu thanh toán cũ có thể dẫn đến quyết định sai. Fallback phải tuân thủ quy tắc nghiệp vụ của endpoint, không chỉ cố trả HTTP 200.

Một fallback cũng không nên gọi lại chính downstream đang lỗi. Nếu fallback cần gọi dependency khác, dependency đó phải có timeout, giới hạn tài nguyên và cơ chế bảo vệ riêng. Nếu không, đường fallback có thể tạo thêm một chuỗi lỗi.

## 9. Phân biệt exception fallback và status code fallback

CircuitBreaker GatewayFilter có thể kích hoạt fallback do exception hoặc do status code được khai báo trong statusCodes.

Hai tình huống khác nhau:

| Tình huống | Ví dụ | Cần kiểm tra |
|---|---|---|
| Exception | Timeout, lỗi kết nối, CallNotPermittedException | Cause attribute và cause chain |
| Status được cấu hình | Downstream trả 500 hoặc 503 | Danh sách statusCodes và cách adapter chuyển response thành lỗi |
| Status không được cấu hình | Downstream trả 404 bình thường | Response có thể đi thẳng về client |
| Lỗi fallback handler | Controller fallback tự phát sinh exception | Xử lý lỗi của chính fallback và response cuối |

Khi status code được cấu hình, Gateway có thể chuyển response đó thành tình huống lỗi để Circuit Breaker ghi nhận và kích hoạt fallback. Cần kiểm thử đúng status mà downstream trả về, vì hành vi phụ thuộc cấu hình filter và phiên bản.

Nếu status 404 mang nghĩa "không tìm thấy sản phẩm", thường không nên đưa nó vào statusCodes chỉ để kích hoạt fallback chung. Nếu status 503 thể hiện dependency không thể phục vụ, có thể đưa vào danh sách và trả lỗi tạm thời đã chuẩn hóa.

## 10. Không để fallback endpoint trở thành route công khai ngoài ý muốn

Fallback URI forward được gọi nội bộ bởi Gateway filter, nhưng endpoint fallback vẫn là một mapping trong ứng dụng. Nếu route hoặc security configuration cho phép truy cập trực tiếp, client có thể gọi fallback endpoint mà không đi qua Circuit Breaker.

Cần xem xét:

- Đặt fallback path trong vùng namespace nội bộ, ví dụ /internal/fallback/inventory.
- Không tạo route public riêng trỏ đến path fallback nếu không có nhu cầu.
- Dùng security rules phù hợp để tránh client bên ngoài gọi trực tiếp endpoint nội bộ.
- Không dựa vào việc tên path khó đoán như một cơ chế bảo mật.
- Nếu handler được gọi trực tiếp mà không có cause attribute, trả phản hồi mặc định an toàn hoặc từ chối theo chính sách.
- Không dùng header do client tự gửi để giả lập nguyên nhân lỗi hoặc đánh dấu request đã đi qua Circuit Breaker.

Việc forward nội bộ không tự động bảo đảm endpoint chỉ được gọi bởi filter. Kiểm tra route matching và security chain để bảo đảm đường fallback không trở thành một API public ngoài ý muốn.

## 11. Theo dõi fallback mà không làm lộ nguyên nhân

Nên có metric riêng cho fallback và loại nguyên nhân đã phân loại. Ví dụ các metric có thể đếm số lần fallback theo route và failure kind:

- Số lần Circuit Breaker OPEN.
- Số lần timeout.
- Số lỗi kết nối.
- Số response status downstream bị đưa vào fallback.
- Số lần fallback handler tự phát sinh lỗi.
- Tỷ lệ response được phục vụ bằng cache hoặc dữ liệu suy giảm.
- Thời gian xử lý của fallback.

Nhãn metric nên có cardinality thấp. Có thể dùng route ID và failure kind đã chuẩn hóa; không đưa request ID, user ID, URL đầy đủ hoặc exception message vào nhãn vì sẽ tạo quá nhiều time series và có thể làm lộ dữ liệu.

Log và trace có thể giữ thông tin chi tiết hơn trong phạm vi được kiểm soát. Metric phục vụ xu hướng và cảnh báo; log/trace phục vụ điều tra từng request.

## 12. Kiểm thử nguyên nhân và response an toàn

Một bài kiểm thử fallback nên xác minh cả hai phía: nguyên nhân nội bộ được ghi nhận đúng và response công khai không tiết lộ thông tin.

Các tình huống nên có:

| Tình huống | Nguyên nhân nội bộ mong đợi | Response công khai |
|---|---|---|
| Circuit Breaker OPEN | CallNotPermittedException | 503 và mã lỗi tổng quát |
| Downstream timeout | Timeout exception | 504 hoặc status theo hợp đồng API |
| Connection refused | Lỗi kết nối | 503 và thông báo an toàn |
| Downstream trả 503 được cấu hình | Status fallback theo filter | 503 với error envelope chuẩn |
| Downstream trả 404 không cấu hình | Không kích hoạt fallback chung | 404 theo hợp đồng API |
| Cause attribute không có | UNKNOWN | Phản hồi mặc định an toàn hoặc từ chối |
| Fallback handler lỗi | Exception của handler | Error handler chung, không trả stack trace |

Khi kiểm thử, cần xác nhận:

1. Route thực sự dùng CircuitBreaker GatewayFilter.
2. Fallback URI được forward đến đúng handler.
3. Handler đọc đúng attribute exception của Gateway.
4. Cause chain được phân loại đúng với loại exception của HTTP client thực tế.
5. Response không chứa exception message, stack trace, hostname hoặc URI nội bộ.
6. Request ID có thể liên kết response với log/trace.
7. Fallback handler không gọi lại dependency đang lỗi.
8. Endpoint fallback không bị lộ thành một API public ngoài ý muốn.

Có thể kiểm tra response body bằng assertion để chắc chắn không chứa tên class exception, hostname nội bộ, port hoặc stack trace. Đồng thời, kiểm tra log nội bộ để bảo đảm vẫn có đủ request ID và failure kind phục vụ điều tra.

## 13. Những lỗi thường gặp

- **Không đọc exception attribute**: fallback handler chỉ trả một thông báo chung và làm mất khả năng điều tra nguyên nhân.
- **Giả định attribute luôn có giá trị**: handler cần xử lý cause null và các đường gọi trực tiếp.
- **Trả cause.getMessage() cho client**: message có thể chứa host, URI, thông tin xác thực hoặc dữ liệu nội bộ.
- **Trả stack trace trong JSON**: tiết lộ class, package, cấu trúc và chi tiết triển khai.
- **Chỉ phân loại exception ngoài cùng**: nguyên nhân gốc có thể nằm trong cause chain.
- **Dùng message để nhận diện timeout**: message không ổn định bằng exception type hoặc mã lỗi.
- **Cấu hình statusCodes quá rộng**: có thể coi lỗi nghiệp vụ 404/409 là lỗi hạ tầng.
- **Fallback gọi lại cùng downstream**: tạo vòng lặp hoặc tiếp tục làm tăng tải.
- **Không bảo vệ fallback endpoint**: client có thể gọi trực tiếp handler nội bộ.
- **Ghi exception message vào metric label**: cardinality tăng và dữ liệu nội bộ có thể bị lộ.
- **Không có request ID**: khó liên kết response fallback với log và trace.
- **Fallback trả 200 cho mọi lỗi**: che giấu sự cố và làm caller hiểu sai trạng thái nghiệp vụ.

## 14. Quy trình triển khai

Khi triển khai CircuitBreaker GatewayFilter và fallback handler trong Spring Cloud Gateway, có thể thực hiện theo trình tự:

1. Xác định route và các exception hoặc status downstream cần kích hoạt fallback.
2. Cấu hình CircuitBreaker GatewayFilter với tên instance và fallbackUri dùng forward nội bộ.
3. Khai báo handler fallback nhận ServerWebExchange.
4. Đọc Throwable từ CIRCUITBREAKER_EXECUTION_EXCEPTION_ATTR và xử lý trường hợp không có cause.
5. Phân loại nguyên nhân theo exception type/cause chain đã quan sát từ HTTP client thực tế.
6. Ghi log nội bộ có request ID, route ID và failure kind; bảo vệ log và lọc dữ liệu nhạy cảm.
7. Ánh xạ nguyên nhân sang status, error code và thông báo công khai đã chuẩn hóa.
8. Không đưa exception message, stack trace, hostname, URI nội bộ hoặc token vào response.
9. Kiểm soát quyền truy cập fallback endpoint và không tạo route public không cần thiết.
10. Kiểm thử exception, statusCodes, cause null, fallback handler error và response không rò rỉ thông tin.
11. Theo dõi metric fallback với nhãn cardinality thấp và liên kết log/trace bằng request ID.

Gateway fallback cần giữ được hai mục tiêu: nhóm vận hành biết nguyên nhân thật để điều tra, còn client chỉ nhận thông tin đủ để xử lý request. Đọc nguyên nhân từ ServerWebExchange, phân loại theo kiểu exception và giữ chi tiết trong log nội bộ giúp đạt mục tiêu đó. Response công khai nên dùng status và error code ổn định, thông báo tổng quát cùng request ID; không trả exception message hoặc cấu trúc hạ tầng của dependency.
