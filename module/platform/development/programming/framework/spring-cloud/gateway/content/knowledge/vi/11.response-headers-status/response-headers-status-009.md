# Đồng bộ header, body và mã trạng thái khi tạo phản hồi tại gateway

## 1. Bài toán: một HTTP response phải nhất quán từ đầu đến cuối

Trong kiến trúc microservices, **Spring Cloud Gateway** thường nhận HTTP request, chọn route bằng **route predicate**, thực thi **filter chain** rồi chuyển tiếp đến service được tìm qua URI cố định hoặc service discovery. Ngoài việc proxy dữ liệu, Gateway còn có thể **tạo phản hồi ngay tại biên**: từ chối request thiếu xác thực, giới hạn lưu lượng, trả fallback khi backend lỗi, chuyển hướng URL cũ hoặc gửi phản hồi của một handler nội bộ.

Khi tự tạo hoặc biến đổi phản hồi, cần đồng bộ **ba phần của HTTP response**:

1. **Mã trạng thái (status code):** request đã thành công, bị từ chối, không có nội dung hay cần thử lại?
2. **Response headers:** mô tả loại nội dung, độ dài, cache, bảo mật, vị trí tài nguyên hoặc điều kiện kết nối như thế nào?
3. **Response body:** có nội dung hay không, dữ liệu có đúng định dạng và ngữ nghĩa mà status/headers công bố không?

Ví dụ về phản hồi **mâu thuẫn**:

~~~http
HTTP/1.1 204 No Content
Content-Type: application/json
Content-Length: 27

{"message":"Đã hoàn tất"}
~~~

Mã **204 No Content** biểu thị không có nội dung phản hồi. Gửi body cùng một thông báo `Content-Length` như trên trái ngữ nghĩa HTTP, có thể khiến client/proxy diễn giải dữ liệu không đúng.

Ví dụ khác: Gateway sửa JSON body nhưng vẫn giữ `Content-Length` từ upstream. Số byte thực tế không còn khớp header, dẫn đến response bị cắt, client chờ thêm byte hoặc connection bị đóng với lỗi giao thức.

**Mục tiêu của bài:** viết và cấu hình các response filter trong **Spring Cloud Gateway Server WebFlux** để status, header và body cùng mô tả **một** kết quả HTTP hợp lệ; xử lý đúng thời điểm response commit; tránh rò rỉ dữ liệu, sai caching và lỗi khi stream. Bài thuộc chương **Header và trạng thái**, vì vậy tập trung vào phản hồi HTTP thay vì đi sâu toàn bộ cơ chế xác thực, rate limiting hay circuit breaker.

Sau bài học, bạn cần có khả năng:

- Nhận biết vòng đời response trong filter chain và thời điểm header/status không thể thay đổi.
- Dùng `ServerHttpResponse.setStatusCode(...)`, `getHeaders()`, `writeWith(...)`, `setComplete()` và `beforeCommit(...)` đúng trường hợp.
- Tạo một phản hồi lỗi JSON ngắn tại Gateway mà không tiếp tục proxy request.
- Phân biệt phản hồi có body và không body: 200, 201, 202, 204, 304, 401, 403, 429, 503, HEAD, redirect và partial content.
- Biết khi nào `Content-Length`, `Content-Type`, `Content-Encoding`, `ETag`, `Location` và các header khác phải được tính lại.
- Kiểm thử response trực tiếp từ Gateway, response proxy upstream và các lỗi xảy ra sau khi response đã bắt đầu truyền.

> **Phạm vi phiên bản:** Ví dụ Java hướng tới **Spring Cloud Gateway Server WebFlux** với Spring WebFlux/Reactor. Ở các dòng Spring Cloud Gateway khác nhau, một số package, tên starter hoặc namespace YAML có thể thay đổi; Server Web MVC có cách tùy biến khác. Hãy đối chiếu API với đúng phiên bản đang dùng.

## 2. Ba phần của response và hợp đồng HTTP

Mô hình response:

~~~mermaid
flowchart TD
    R[HTTP response] --> S[Status code]
    R --> H[Response headers]
    R --> B[Response body hoặc không có body]
    S --> C[Hợp đồng HTTP nhất quán]
    H --> C
    B --> C
~~~

Một số header cần chú ý:

| Header | Mô tả | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| `Content-Type` | Kiểu media của body, có thể kèm charset | Body có thực sự là JSON, text, SSE hoặc binary như đã khai báo không? |
| `Content-Length` | Độ dài phần nội dung theo **byte** trong trường hợp áp dụng | Body đã đổi nhưng header cũ còn nguyên không? |
| `Content-Encoding` | Phép mã hóa nội dung như gzip | Header còn đúng sau khi giải nén/nén lại body không? |
| `Transfer-Encoding` | Cơ chế truyền HTTP/1.1 như chunked | Có để HTTP server quản lý thay vì tự gắn tùy tiện không? |
| `Location` | URI của tài nguyên mới hoặc URL redirect | Status có tương ứng 201/3xx; host và query có an toàn không? |
| `Cache-Control` | Chính sách lưu cache | Nội dung chứa dữ liệu riêng tư có bị cache công khai không? |
| `ETag` | Validator cho representation | Body đổi mà ETag cũ vẫn được giữ không? |
| `Vary` | Những request header ảnh hưởng lựa chọn representation | Proxy/cache có biết response thay đổi theo `Origin`, `Accept-Encoding` hoặc `Accept-Language` không? |
| `Retry-After` | Thời gian khuyến nghị thử lại (giây hoặc HTTP-date) | Có phù hợp với 429/503 và chính sách retry không? |
| `WWW-Authenticate` | Thông tin thử thách xác thực | Response 401 có challenge thích hợp với cơ chế bảo vệ không? |

Quy tắc cốt lõi: **không thể suy ra toàn bộ hợp đồng từ một status code duy nhất**. Chẳng hạn, 200 có thể trả JSON, tệp nhị phân hoặc SSE; 404 có thể có body lỗi; 204 bắt buộc không gửi body; 206 cần mô tả phần nội dung được trả về một cách chính xác.

### Ví dụ phản hồi 429 có body hợp lệ

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 5

{"code":"RATE_LIMITED","message":"Thử lại sau"}
~~~

Nếu Gateway muốn gửi `Content-Length`, nó phải phản ánh **độ dài byte sau khi encode**, không phải số ký tự Unicode trong chuỗi. Với UTF-8, các ký tự tiếng Việt thường dùng nhiều byte nên `String.length()` không tương đương kích thước trên mạng.

## 3. Response được tạo ở đâu trong Spring Cloud Gateway?

Một request có thể được xử lý theo hai đường:

- **Proxy upstream:** route được chọn; gateway filters chuẩn bị request; routing filter gửi đến microservice; header/status/body từ backend được xử lý và ghi ra client, có thể kèm các thay đổi có chủ đích của Gateway.
- **Short-circuit tại Gateway:** một filter quyết định không gửi đến upstream, thiết lập status/header, viết body (nếu cần) và trả publisher hoàn tất response.

~~~mermaid
flowchart TD
    C[Client request] --> M[RoutePredicateHandlerMapping]
    M --> F[FilteringWebHandler + filter chain]
    F --> Q{Tiếp tục proxy?}
    Q -->|Có| U[Routing filter gọi upstream]
    U --> UR[Upstream status + headers + body]
    UR --> RF[Gateway response filters / write response]
    Q -->|Không| L[Local response: status + headers + body]
    L --> W[ServerHttpResponse]
    RF --> W
    W --> C2[Client]
~~~

Trong **Server WebFlux**, `ServerWebExchange` chứa `ServerHttpResponse`:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
~~~

Đây mới chỉ là **chuẩn bị metadata**. Nếu có body, phải ghi body qua publisher tương ứng. Nếu không có body, kết thúc response bằng API phù hợp. Việc lựa chọn cách hoàn tất response cần nhất quán với status và headers.

Một `GlobalFilter` hoặc `GatewayFilter` thường trả `Mono<Void>`. Giá trị này biểu diễn **tiến trình bất đồng bộ**, không có nghĩa HTTP response không có nội dung. Body được ghi bởi `ServerHttpResponse` trong quá trình xử lý của publisher.

### Giới hạn phạm vi của GlobalFilter

`GlobalFilter` là thành phần trong chuỗi lọc **của các request đã được Spring Cloud Gateway định tuyến**; nó không tự động bao phủ mọi WebFlux controller hoặc HTTP request không khớp route. Nếu muốn xử lý lỗi/bảo mật ở cấp ứng dụng hoặc WebFlux endpoint độc lập, cần xem thêm `WebFilter`, Spring Security WebFlux và cơ chế exception handling. Đừng coi một GlobalFilter là lớp bảo vệ thay thế hoàn toàn cho cấu hình bảo mật.

## 4. Trạng thái "committed": ranh giới quan trọng nhất

Trong HTTP, status line và response headers phải được gửi **trước** body. Khi response đã được commit, không thể quay về sửa status/header như thể chưa gửi gì.

Với Spring WebFlux, kiểm tra:

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

Các trạng thái ý tưởng:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaCommit: Chưa ghi response
    ChuaCommit --> ChuanBi: setStatusCode / set headers
    ChuanBi --> DangCommit: writeWith hoặc setComplete
    DangCommit --> DaCommit: Header được gửi
    DaCommit --> HoanTat: Body kết thúc
    DaCommit --> LoiGiuaLuong: Lỗi hoặc client hủy
    HoanTat --> [*]
    LoiGiuaLuong --> [*]
~~~

Sơ đồ mang tính khái niệm: framework có thể commit trong quá trình bắt đầu ghi body hoặc khi hoàn tất response không có body. Điều cần nhớ là **không đợi đến khi `chain.filter(exchange)` kết thúc mới thử sửa status hoặc header**, vì downstream có thể đã commit chúng.

### Trường hợp chuẩn bị response trước khi ghi

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
response.getHeaders().setCacheControl("no-store");
return response.setComplete();
~~~

Vì `setComplete()` chủ ý kết thúc response **không có body**, không nên vừa gọi `setComplete()` rồi sau đó mới gọi `writeWith(...)` cho cùng response.

### beforeCommit giúp cập nhật header đúng thời điểm

Spring WebFlux cung cấp `beforeCommit` để đăng ký công việc thực hiện trước khi response commit:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();

    response.beforeCommit(() -> {
        response.getHeaders().set("X-Gateway-Processed", "true");
        return Mono.empty();
    });

    return chain.filter(exchange);
}
~~~

Đây là đoạn phương thức bên trong một `GlobalFilter` hoặc `GatewayFilter`; các import/bean đăng ký được lược bỏ để nhấn mạnh cơ chế. Callback được đăng ký **trước khi tiếp tục chuỗi**. Nó phù hợp với thao tác nhẹ, có tính quyết định và không blocking như thêm một header quan sát. `beforeCommit` không phải giải pháp để đọc và ghép toàn bộ body sau khi nó đã gửi.

Nếu cần bổ sung status/header tùy kết quả upstream, phải hiểu **thứ tự các filter** và thời điểm metadata có sẵn. Một callback `beforeCommit` có thể nhìn thấy status đã được downstream đặt vào thời điểm chuẩn bị commit, nhưng không nên dùng nó để tùy tiện ghi đè mọi status do backend trả.

## 5. Tạo phản hồi JSON và short-circuit đúng cách

Ví dụ đầy đủ sau minh họa một `GlobalFilter` tự trả **429** cho đường dẫn thử nghiệm `/api/demo/limited`. Nó cố ý **không gọi `chain.filter(exchange)`** ở nhánh từ chối:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DemoRateLimitResponseFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getPath().value();

        if (!"/api/demo/limited".equals(path)) {
            return chain.filter(exchange);
        }

        String json = "{\"code\":\"RATE_LIMITED\",\"message\":\"Thử lại sau\"}";
        byte[] payload = json.getBytes(StandardCharsets.UTF_8);

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setContentLength(payload.length);
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().set(HttpHeaders.RETRY_AFTER, "5");

        DataBuffer buffer = response.bufferFactory().wrap(payload);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

**Phân tích tính nhất quán:**

1. `HttpStatus.TOO_MANY_REQUESTS` có mã 429, phù hợp việc từ chối vì giới hạn lưu lượng.
2. `Content-Type: application/json` phù hợp chuỗi JSON được tạo.
3. `Content-Length` lấy từ **payload.length**, tức số byte UTF-8 chính xác trong ví dụ **không nén hoặc biến đổi body ở tầng sau**.
4. `Cache-Control: no-store` hạn chế nguy cơ phản hồi lỗi có nội dung riêng tư bị lưu cache.
5. `Retry-After: 5` là gợi ý thử lại sau 5 giây; không phải bảo đảm backend sẽ sẵn sàng ở giây thứ năm.
6. `response.writeWith(...)` trả `Mono<Void>` gắn vòng đời ghi body với pipeline WebFlux.
7. Vì nhánh bị từ chối không trả `chain.filter(exchange)`, Gateway không gọi upstream trên đường đi đó.

**Quan trọng:** Điều kiện từ chối theo path trên chỉ phục vụ **học cách tạo response**, không phải một thuật toán rate limiting. Trong ứng dụng thực, hãy dùng `RequestRateLimiter` hoặc cơ chế hạn mức thích hợp dựa trên định danh đáng tin cậy, quota và nhiều instance. Để filter được chạy trong ví dụ, ứng dụng phải có **route khớp `/api/demo/limited`**; nếu không có route, một GlobalFilter của Gateway không nhất thiết được gọi.

Không tạo `DataBuffer` rồi tự gọi `subscribe()` bên trong filter. Hãy **trả publisher** do `writeWith` tạo ra để framework quản lý việc ghi, lỗi và hủy. Nếu thao tác trực tiếp trên pooled DataBuffer, phải hiểu vòng đời retain/release; đoạn trên bọc mảng byte rồi chuyển quyền xử lý cho response writer.

### Khi không có body

Một phản hồi từ chối đơn giản có thể chỉ có status và headers:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.FORBIDDEN);
response.getHeaders().setCacheControl("no-store");
return response.setComplete();
~~~

Đừng đặt `Content-Type: application/json` rồi không gửi nội dung JSON nếu hợp đồng dự kiến có payload lỗi. Ngược lại, nếu contract cho phép body rỗng, không cần gắn Content-Type mô tả body tưởng tượng.

## 6. Chọn status phù hợp với việc có hay không có body

Status quyết định ngữ nghĩa của response. Một bảng thực hành:

| Status/phương thức | Có thể gửi body? | Điều cần giữ nhất quán |
| --- | --- | --- |
| **200 OK** | Có thể | Đúng Content-Type, encoding, body và độ dài nếu công bố |
| **201 Created** | Có thể | Nếu trả Location, URI phải xác định đúng tài nguyên được tạo |
| **202 Accepted** | Có thể | Thể hiện request được nhận nhưng xử lý chưa hoàn tất; response không được giả vờ đã thành công cuối cùng |
| **204 No Content** | **Không** | Không viết body; không gửi Content-Length như response có payload |
| **304 Not Modified** | **Không có response body** | Giữ thông tin cache validator phù hợp, không viết body; Content-Length chỉ hợp lệ theo điều kiện chuẩn HTTP |
| **HEAD (bất kỳ status phù hợp)** | **Không có response body** | Metadata mô tả response GET tương ứng khi áp dụng; không tự đặt Content-Length bằng 0 nếu representation thực có kích thước khác |
| **206 Partial Content** | Có, theo phạm vi | Content-Range, Content-Length và bytes thực gửi phải khớp |
| **301/302/307/308** | Có thể có nội dung giải thích | Location phải đúng; cân nhắc method/body khi client theo redirect |
| **401 Unauthorized** | Thường có thể có body | Thử thách WWW-Authenticate phù hợp với cơ chế xác thực |
| **403 Forbidden** | Có thể | Không đưa chi tiết tài nguyên nhạy cảm hoặc quyền nội bộ vào body |
| **429 Too Many Requests** | Có thể | Retry-After khi phù hợp; không che nguồn gốc chính sách rate limit |
| **503 Service Unavailable** | Có thể | Thể hiện tình trạng không sẵn sàng; tránh fallback body có dữ liệu nghiệp vụ sai |

Một số lưu ý:

**204 No Content:** Không gọi `writeWith` để gửi JSON hay văn bản. Không gắn `Content-Length` như thể gửi body. Nếu không có thông tin bổ sung, chỉ cần status và headers được phép rồi `setComplete()`.

**304 Not Modified:** Chỉ phù hợp khi điều kiện caching/validator tương ứng được áp dụng. Không gửi body. Khác với 204, chuẩn HTTP cho phép một số metadata về representation, kể cả `Content-Length` **nếu** giá trị tương ứng chính xác với response 200 sẽ được gửi; đừng máy móc đặt 0 hoặc sao chép độ dài tùy ý.

**HEAD:** Phản hồi không mang body nhưng metadata có thể mô tả kích thước của body mà GET tương ứng sẽ tạo. Việc cố “sửa” mọi HEAD bằng `Content-Length: 0` có thể làm sai hợp đồng.

**206 Partial Content:** Nếu một gateway filter sửa tệp hoặc nén phần body sau khi upstream đã tính range, các header `Content-Range`, `Accept-Ranges` hoặc Content-Length có nguy cơ sai. Không tự viết lại response range trừ khi hiểu rõ việc xử lý byte.

**401 và 403:** 401 thường gắn với yêu cầu xác thực/challenge, 403 với từ chối truy cập. Dùng status chính xác và đặt response metadata theo chuẩn cơ chế bảo mật. Khi dùng Spring Security, ưu tiên để authentication entry point / access denied handler quản lý thay vì tự phát 401/403 từ một filter tùy ý.

## 7. Đồng bộ Content-Length với dữ liệu thực được gửi

**Content-Length là số byte**, không phải số ký tự hoặc phần tử trong `Flux`.

Ví dụ:

~~~java
String text = "Đã xử lý";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

response.getHeaders().setContentType(
        new MediaType("text", "plain", StandardCharsets.UTF_8));
response.getHeaders().setContentLength(bytes.length);
return response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes)));
~~~

Vì ký tự Unicode có thể chiếm nhiều byte UTF-8, dùng `text.length()` để điền Content-Length sẽ sai.

Khi **không biết trước độ dài**, chẳng hạn SSE hoặc một response streaming dài, thường nên **không tự đặt Content-Length**. HTTP runtime có thể chọn cơ chế truyền phù hợp: HTTP/1.1 có thể dùng chunked transfer encoding khi thích hợp, còn HTTP/2 dùng data frames và flow control riêng, không dùng `Transfer-Encoding: chunked`.

### Khi nào Content-Length có thể trở nên lỗi thời?

| Tình huống | Vì sao có thể sai? | Hướng xử lý |
| --- | --- | --- |
| Gateway thêm trường vào JSON body | Số byte mới khác số byte cũ | Tính lại độ dài sau biến đổi hoặc bỏ Content-Length để writer quyết định framing |
| Gateway đổi charset | Encoding có thể thay đổi số byte | Dùng byte thực sau encode |
| Gateway giải nén rồi gửi plain body | Body không còn cùng dạng content-encoded | Đồng bộ Content-Encoding, Content-Length, validator và các header liên quan |
| Gateway nén thêm response | Bytes truyền trên mạng khác trước nén | Để thành phần nén/HTTP writer quản lý metadata phù hợp |
| Backend trả SSE/NDJSON streaming | Chưa biết tổng số byte | Không tự đặt Content-Length tùy ý |
| Gateway biến đổi partial response | Content-Range và kích thước segment không còn đúng | Tránh biến đổi range hoặc triển khai xử lý range đúng chuẩn |

**Không tự gắn đồng thời Content-Length và Transfer-Encoding theo suy đoán.** Đây là các metadata giao thức có thể bị thay đổi bởi HTTP server/proxy. Các cách thể hiện độ dài mâu thuẫn còn liên quan đến rủi ro HTTP request/response smuggling ở hạ tầng không thống nhất.

## 8. Khi Gateway biến đổi response body

Một filter thay body phải xem body như **một representation hoàn chỉnh có metadata liên quan**, không phải chỉ là một chuỗi ký tự. Ví dụ backend trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 15
ETag: "old-v1"

{"status":"ok"}
~~~

Nếu Gateway thêm trường `"source":"gateway"` vào JSON, body mới dài hơn. Ngoài `Content-Length`, validator `ETag` có thể không còn mô tả cùng representation. Nếu có `Content-Encoding: gzip`, byte mà filter đọc hoặc ghi có thể đã ở dạng nén tùy vị trí xử lý; không được chỉ sửa chuỗi JSON rồi chuyển tiếp header gzip cũ.

Các bước cần thiết khi biến đổi body:

1. Xác định body đang là byte gốc, đã decode bằng codec hay đã giải nén.
2. Chọn đúng kiểu dữ liệu và media type (JSON, text, binary, SSE...) cho phép biến đổi.
3. Tạo body mới bằng encoding/serializer phù hợp.
4. Cập nhật hoặc để framework tái tính `Content-Length` và `Content-Encoding` khi cần.
5. Xử lý `ETag`, cache validator, Content-Range và checksum liên quan: giữ chỉ khi vẫn đúng, tính lại nếu có cơ chế hợp lệ hoặc loại bỏ khi không còn đúng.
6. Kiểm tra lỗi, cancellation và trường hợp response bắt đầu stream trước khi filter xử lý xong.

**ModifyResponseBody:** Spring Cloud Gateway Server WebFlux có **ModifyResponseBody GatewayFilter Factory** để biến đổi body qua codec. API/cách đăng ký của tính năng này gắn với **Java DSL**, không nên tự giả định mọi phiên bản đều hỗ trợ cấu hình tương đương qua YAML. Khi dùng, cần cân nhắc bộ nhớ, loại response và khả năng tập hợp body; **không mặc định filter biến đổi body vẫn giữ đặc tính streaming của SSE hoặc tệp lớn**.

Nếu chỉ cần sửa một header, ưu tiên dùng filter response header có sẵn, tránh đọc và tái ghi body. Nếu chỉ cần trả một thông báo lỗi ở biên, thường đơn giản và an toàn hơn khi **tạo response lỗi nhất quán ngay tại Gateway** trước khi proxy thay vì sửa response backend sau khi đã bắt đầu gửi.

## 9. Các filter có sẵn để điều chỉnh status và header

Spring Cloud Gateway cung cấp nhiều filter ở cấp response. Các tên dưới đây minh họa nhóm khả năng thường gặp; cần kiểm tra tài liệu đúng phiên bản khi cấu hình:

| Filter | Công dụng | Lưu ý về tính nhất quán |
| --- | --- | --- |
| `SetStatus` | Ghi đè HTTP status theo cấu hình route | **Không tự sửa body** để khớp mã mới |
| `AddResponseHeader` | Thêm response header | Có thể tạo nhiều giá trị; chỉ nên thêm header hợp lệ |
| `SetResponseHeader` | Thay một response header | Không tự bảo đảm header mới khớp body |
| `RemoveResponseHeader` | Xóa response header | Tránh vô tình xóa metadata bắt buộc của response |
| `RewriteResponseHeader` | Sửa giá trị header bằng regex/replacement | Hữu ích với giá trị Location/Cookie tùy trường hợp; phải kiểm soát encoding |
| `DedupeResponseHeader` | Xử lý response header bị trùng giá trị | Thường hữu ích khi Gateway và upstream cùng thêm header CORS |
| `ModifyResponseBody` | Biến đổi representation của body | Xem lại Content-Length, encoding, validator và buffering |

Ví dụ một route nhận response từ backend và thêm header thông báo:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Route, orders-api
                - RemoveResponseHeader=Server
~~~

`lb://` yêu cầu cơ chế giải quyết service instance và load balancing được cấu hình (chẳng hạn Spring Cloud LoadBalancer kết hợp service discovery). Ví dụ trên chỉ chỉnh header; **không tự động thay nội dung response**. Với các phiên bản Spring Cloud Gateway WebFlux cũ, namespace route có thể là `spring.cloud.gateway.routes` thay cho `spring.cloud.gateway.server.webflux.routes`.

### Thận trọng với SetStatus

Giả sử backend trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"O-42","state":"CREATED"}
~~~

Nếu thêm `SetStatus=503` mà không thay body, client có thể thấy **503** cùng JSON mô tả đơn hàng thành công. Việc này không nhất quán về ngữ nghĩa nghiệp vụ, dù gói tin HTTP vẫn có thể hợp lệ. **Không dùng SetStatus để che giấu kết quả thật**; hãy thiết kế chính sách lỗi/fallback có status, body và metadata phù hợp.

Trong chiều ngược lại, đổi **404** thành **200** không tự sinh tài nguyên hoặc dữ liệu hợp lệ. Cần giữ nguyên contract kết quả mà client có thể dựa vào.

## 10. CORS, cache và header bảo mật

Gateway thường là nơi áp dụng CORS, TLS, xác thực và một số response header bảo mật cho các client web/mobile. Nếu nhiều tầng đều ghi các header này, có thể tạo ra kết quả mâu thuẫn hoặc lộ dữ liệu.

### CORS: Gateway và upstream đừng cùng trả giá trị xung đột

Ví dụ response không tốt:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Header `Access-Control-Allow-Origin` trùng/xung đột có thể làm browser từ chối response. Khi `Access-Control-Allow-Credentials: true`, không dùng wildcard `*` làm Allowed-Origin. Với chính sách phản hồi theo Origin, thường cần kiểm soát nguồn gốc được phép và `Vary: Origin` thích hợp để các cache phân biệt response.

Chọn **một nguồn sở hữu chính sách CORS** (ví dụ Gateway) hoặc phối hợp tường minh. `DedupeResponseHeader` có thể giúp giảm trùng giá trị khi cả Gateway và downstream thêm CORS headers, nhưng nó **không tự giải quyết một chính sách CORS sai**.

### Cache: status, body và validator phải thống nhất

- Response có dữ liệu cá nhân, token hoặc kết quả ủy quyền riêng thường cần chính sách cache nghiêm ngặt, chẳng hạn `Cache-Control: no-store` nếu phù hợp.
- Nếu representation thay đổi theo `Accept-Language`, `Origin` hoặc `Accept-Encoding`, cân nhắc `Vary` đúng và nhất quán.
- Nếu Gateway biến đổi body, **ETag của upstream có thể không còn hợp lệ**; không tiếp tục khẳng định nội dung mới có cùng validator.
- Với conditional GET, `304 Not Modified` phải gắn với validator thực của representation được cache; không biến một body lỗi thành 304 chỉ để tiết kiệm băng thông.

### Header bảo mật và hop-by-hop headers

Các header như `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options` hoặc `Referrer-Policy` cần được cấu hình theo chính sách của ứng dụng và cách TLS được triển khai. Đừng copy một bộ header bất kỳ lên mọi loại response mà không xét ngữ cảnh.

**Hop-by-hop headers**, chẳng hạn `Connection` và những field được Connection chỉ định, thuộc từng kết nối HTTP riêng; proxy không nên chuyển tiếp tùy ý sang kết nối khác. HTTP stack/Gateway có cơ chế xử lý các trường hợp này. Không tự giữ `Transfer-Encoding: chunked` khi response phía client dùng HTTP/2.

Khi ứng dụng tạo redirect hoặc đường dẫn tuyệt đối, chỉ tin `Forwarded`, `X-Forwarded-Proto` và `X-Forwarded-Host` nếu nguồn proxy được kiểm soát; nếu không, client có thể giả mạo chúng để tạo URL sai hoặc **open redirect**.

## 11. Lỗi, retry và fallback: đã commit thì không thể thay response

Một response có thể gặp lỗi ở hai thời điểm:

~~~mermaid
flowchart TD
    A[Gateway đang xử lý request] --> B{Response đã commit?}
    B -->|Chưa| C[Có thể thiết kế response lỗi mới]
    B -->|Rồi| D[Không thể đổi status/header đã gửi]
    C --> E[Thiết lập status + headers + body lỗi]
    D --> F[Ghi nhận lỗi, đóng hoặc hủy stream, client xử lý partial data]
~~~

### Lỗi trước khi response commit

Giả sử Gateway gọi backend và nhận lỗi kết nối trước khi gửi dữ liệu cho client. Tùy cấu hình, một error handler, CircuitBreaker fallback hoặc cơ chế xử lý lỗi thích hợp có thể tạo phản hồi **503** với JSON:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store
Retry-After: 10

{"code":"UPSTREAM_UNAVAILABLE","message":"Tạm thời không thể xử lý"}
~~~

Status 503, header Retry-After và body thông báo đều phải đúng với tình huống đã được phân loại. Không tùy tiện biến mọi exception thành 503: lỗi dữ liệu không hợp lệ, lỗi phân quyền hoặc lỗi lập trình có ngữ nghĩa khác nhau. Nếu có cơ chế retry, cần bảo vệ những thao tác **không idempotent** như tạo đơn hàng, thanh toán.

### Lỗi sau khi response đã commit

Với SSE hoặc NDJSON, Gateway có thể đã gửi status 200 và vài sự kiện rồi backend bị ngắt:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

event: progress
data: 20

<connection interrupted>
~~~

Sau thời điểm này, **không thể quay lại trả status 503 trên cùng response đã commit**. Cần ghi nhận lỗi giữa stream, cancellation, thời điểm ngắt và để client áp dụng contract reconnect/resume khi có hỗ trợ. Retry toàn bộ một stream đã gửi dữ liệu có thể làm trùng sự kiện hoặc bản ghi.

Một đoạn logic phòng vệ cơ bản trong custom filter:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> {
            ServerHttpResponse response = exchange.getResponse();
            if (response.isCommitted()) {
                return Mono.error(error);
            }
            // Chỉ minh họa: lỗi phải được phân loại ở logic thực tế.
            response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
            response.getHeaders().setCacheControl("no-store");
            return response.setComplete();
        });
~~~

**Không dùng nguyên đoạn này làm error handler production.** Nó chuyển mọi lỗi trước commit thành 503, không đảm bảo metadata cũ đã được xóa hoặc trạng thái là đúng với lỗi. Trong môi trường thật, xử lý lỗi nên phân loại exception, kiểm tra/cập nhật headers liên quan, ghi metrics/traces và dùng cơ chế exception handling phù hợp. Đoạn này chỉ minh họa việc **phải kiểm tra commit state**.

## 12. Tạo redirect hoặc phản hồi không có body

### Redirect với Location

Một HTTP redirect có thể được Gateway tạo bằng filter `RedirectTo` hoặc logic response phù hợp:

~~~yaml
predicates:
  - Path=/old-docs
filters:
  - RedirectTo=308, https://docs.example.test/guide
~~~

Điểm cần đồng bộ:

- Mã **308** mang ý nghĩa redirect vĩnh viễn, client theo redirect phải giữ method/body theo quy tắc HTTP.
- `Location` phải trỏ tới URL đúng và không lấy host tùy ý từ client không đáng tin.
- Không mặc định query string của URL cũ tự động xuất hiện trong Location mới.
- Nếu viết response redirect thủ công, phải đảm bảo status, Location và body (nếu có) không mâu thuẫn.

### Trả 204 cho hành động thành công không có nội dung

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.NO_CONTENT);
response.getHeaders().remove(HttpHeaders.CONTENT_LENGTH);
return response.setComplete();
~~~

Đây là ví dụ thiết lập 204 khi **chưa có body nào được ghi**. Nếu một upstream thực sự trả nội dung, không nên đổi status thành 204 rồi vẫn để response writer gửi body. Hãy chọn 204 ngay ở đường xử lý đúng và để HTTP stack quản lý framing.

### 201 Created và Location

Nếu một API tạo tài nguyên `/api/orders/O-42` và cần gửi 201, URL trong Location phải có ý nghĩa với client. Đừng để lộ URI nội bộ `http://orders-service:8080/orders/O-42` nếu endpoint công khai chỉ đi qua `https://api.example.test/api/orders/O-42`. Khi Gateway đứng sau ingress, hãy xác định scheme/host công khai từ cấu hình hoặc proxy tin cậy.

## 13. Kiểm thử tính nhất quán của response

Kiểm thử không nên chỉ xác nhận một status `200`. Hãy kiểm tra **status, headers và body như một bộ ba**.

### Ví dụ gọi thử với curl

Giả sử ứng dụng đã định nghĩa route khớp `/api/demo/limited` và đăng ký `DemoRateLimitResponseFilter` ở phần 5:

~~~bash
# Kiểm tra status line, response headers và JSON body:
curl -i http://localhost:8080/api/demo/limited

# Kiểm tra chính xác response headers và đường xử lý ở giao thức:
curl -v http://localhost:8080/api/demo/limited

# Với stream SSE, tránh buffer hiển thị ở curl:
curl -i -N http://localhost:8080/api/stream/events
~~~

Các lệnh trên là **hướng dẫn kiểm chứng**, không phải kết quả chạy thật của bài. `curl -I` gửi HEAD; nó **không** tương đương xem headers của một GET thông thường nếu server xử lý HEAD khác. Khi test phản hồi không body, dùng method và status cụ thể thay vì dựa vào một phép đo nội dung chung.

Đối với demo 429:

| Thành phần | Kỳ vọng |
| --- | --- |
| Status | `429 Too Many Requests` |
| Content-Type | `application/json` |
| Retry-After | `5` |
| Cache-Control | `no-store` |
| Content-Length | Bằng đúng số byte UTF-8 của JSON truyền đi nếu không có tầng biến đổi tiếp theo |
| Body | JSON hợp lệ có `code` và `message` |
| Upstream | **Không bị gọi** trên nhánh short-circuit |

### Kiểm thử bằng WebTestClient

Trong integration test với Gateway đang chạy hoặc được bind đúng cách, có thể kiểm tra:

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/demo/limited")
        .exchange()
        .expectStatus().isEqualTo(429)
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().valueEquals("Retry-After", "5")
        .expectBody()
        .jsonPath("$.code").isEqualTo("RATE_LIMITED");
~~~

Đoạn test minh họa cần dependency và import `WebTestClient` cùng `MediaType`, ngoài ra **Gateway phải có route match và filter hoạt động**. Test trên chưa đo Content-Length từng byte, chưa chứng minh upstream không bị gọi và chưa kiểm tra lỗi khi stream; bổ sung kiểm thử tương ứng bằng stub backend và client/HTTP test phù hợp.

### Ma trận kiểm thử nên có

| Tình huống | Status | Header cần xem | Body cần xem |
| --- | --- | --- | --- |
| Proxy GET JSON thành công | 200 | Content-Type, Content-Length nếu có, Cache-Control | JSON đúng contract |
| Short-circuit vượt hạn mức | 429 | Retry-After, Content-Type, Cache-Control | JSON lỗi đúng |
| Thiếu xác thực | 401 | WWW-Authenticate theo cơ chế đã chọn | Không lộ token/stack trace |
| Không đủ quyền | 403 | Cache-Control nếu cần | Không tiết lộ thông tin nhạy cảm |
| Thành công không có dữ liệu | 204 | Không có Content-Length sai | **Không có body** |
| Conditional GET hợp lệ | 304 | ETag/Vary/metadata caching đúng | **Không có body** |
| HEAD tới tài nguyên | Theo GET tương ứng | Metadata hợp lệ, có thể có kích thước representation | **Không có body** |
| Download một phần | 206 | Content-Range, Content-Length tương ứng | Đúng bytes được yêu cầu |
| Redirect URL cũ | 301/302/307/308 | Location an toàn | Body tùy contract |
| SSE upstream bị lỗi giữa luồng | Có thể đã là 200 | Headers đã commit, không đổi lại | Partial stream và ngắt kết nối được ghi nhận |
| Gateway đổi JSON upstream | Phù hợp hợp đồng mới | Content-Length, ETag, Content-Encoding đã được xử lý lại | JSON hợp lệ sau biến đổi |

## 14. Các lỗi và phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `response.setStatusCode(204)` rồi gửi JSON | Body vi phạm ngữ nghĩa 204 | Trả 200/202 có body hoặc 204 không body |
| `setComplete()` rồi mới `writeWith(...)` | Response đã/đang kết thúc, body không được ghi đúng | Chỉ chọn một đường hoàn tất |
| Sửa header trong `.then(...)` sau downstream | Có thể quá muộn do response đã commit | Đăng ký `beforeCommit` đúng thời điểm |
| Thay JSON nhưng giữ Content-Length upstream | Header độ dài sai | Tính lại độ dài hoặc bỏ để HTTP writer xử lý |
| Thay body nhưng giữ Content-Encoding/ETag cũ | Client giải mã sai hoặc caching sai | Đồng bộ/xóa/tính lại metadata |
| Ghi Content-Length theo `String.length()` | Sai byte count với UTF-8 | Dùng `byte[].length` của body được encode thực sự |
| Trả 401 không có challenge khi cơ chế yêu cầu | Client không biết cách xác thực lại | Dùng Spring Security và WWW-Authenticate phù hợp |
| CORS do Gateway/upstream ghi hai giá trị khác nhau | Browser từ chối response | Một nguồn sở hữu policy, dedupe có kiểm soát |
| Retry/fallback sau khi SSE đã gửi dữ liệu | Không thể thay status; có thể trùng event | Kiểm tra commit, thiết kế reconnect/resume |
| Tin Forwarded/Host từ client để tạo Location | Open redirect hoặc rò rỉ thông tin | Chỉ tin proxy đáng tin cậy; allowlist URL |
| Log toàn body, Authorization hoặc Set-Cookie | Lộ dữ liệu và tăng áp lực bộ nhớ | Log route ID/status/latency an toàn |
| Đổi upstream 503 thành 200 mà body vẫn báo lỗi | Client hiểu nhầm tình trạng | Chọn chính sách fallback đồng bộ ngữ nghĩa |

Với response streaming, một lỗi **sau khi commit** không thể sửa bằng cách “trả thêm” một body JSON lỗi cuối stream. Kết thúc kết nối và ghi nhận tín hiệu lỗi/hủy là một phần của contract; client cần biết cách xử lý dữ liệu thiếu.

## 15. Bài thực hành tổng hợp

**Bối cảnh:** Gateway đứng trước Orders, Catalog và Notification service. Gateway có xác thực, rate limiting, circuit breaker, retry, TLS và tracing; nhóm cần bảo đảm mọi phản hồi từ biên tới client nhất quán.

### Phần A — Tạo response tại Gateway

1. Thêm route thử nghiệm khớp `/api/demo/limited` và đăng ký `DemoRateLimitResponseFilter`.
2. Dùng GET để xác minh Gateway trả 429, `Retry-After: 5`, JSON hợp lệ và Content-Length bằng số byte.
3. Dùng một backend stub/spy để chứng minh nhánh short-circuit **không gọi upstream**.
4. Thử thay thông báo JSON bằng tiếng Việt dài hơn. Đảm bảo Content-Length thay đổi theo UTF-8 bytes chứ không theo số ký tự.

### Phần B — Tạo các status có quy tắc body khác nhau

1. Tạo một response 204 cho thao tác thành công không cần body; kiểm tra client không nhận payload.
2. Tạo một response 503 khi một dependency lỗi **trước commit**, với body và cache headers phù hợp.
3. Gọi HEAD trên một endpoint thử nghiệm có GET tương ứng; kiểm tra không có body nhưng metadata vẫn có ý nghĩa.
4. Tạo redirect 307 hoặc 308 tới một URL có allowlist, kiểm tra Location, method và behavior khi client không tự theo redirect.

### Phần C — Biến đổi response upstream

1. Backend trả JSON kèm Content-Length và ETag. Trong **môi trường thử nghiệm**, sửa JSON qua một filter phù hợp.
2. Kiểm tra metadata được cập nhật hoặc loại bỏ đúng; không để validator cũ khẳng định body mới.
3. Thử response được nén và một response 206. Ghi lại tại sao không nên sửa body nếu chưa xử lý Content-Encoding hoặc range.

### Phần D — Lỗi giữa stream và bảo mật

1. Backend gửi SSE rồi ngắt sau vài event; xác nhận Gateway không thể thay status đã commit.
2. Kiểm tra CORS khi cả Gateway và upstream cùng thêm header; cấu hình một nguồn chính sách rõ ràng.
3. Thử các giá trị Host/Forwarded giả ở lớp biên và đảm bảo Location không trỏ sang host tùy ý.
4. Bật trace/metrics theo route, nhưng không log body chứa dữ liệu cá nhân, Authorization hoặc Cookie.

**Tiêu chí đạt:** Mỗi nhánh trả đúng status, headers mô tả chính xác body thực gửi (hoặc không có body); không có Content-Length/Content-Encoding/ETag lỗi thời; CORS và cache policy nhất quán; response sau commit được xử lý như partial stream, không bị viết lại status trái giao thức; mọi kiểm chứng có bằng chứng từ HTTP client và backend stub.

## 16. Ghi nhớ

- Một phản hồi tại API Gateway là **bộ ba không tách rời**: **status, headers, body**. Thay một phần phải kiểm tra các phần còn lại.
- **Response chưa commit** mới cho phép điều chỉnh status/header một cách đáng tin cậy. Đăng ký `beforeCommit` sớm; đừng sửa response tùy tiện sau khi downstream hoàn tất.
- Trong WebFlux, `writeWith(...)` ghi body qua publisher; `setComplete()` dùng khi chủ ý kết thúc response không có body. **Trả `Mono<Void>` cho framework**, không tự subscribe.
- **204, 304 và HEAD không có response body**; 206 phải đồng bộ range; 201/3xx có Location cần đúng nguồn và an toàn.
- **Content-Length là số byte**, không phải số ký tự. Khi sửa body, kiểm tra lại `Content-Type`, `Content-Encoding`, `ETag`, cache metadata và độ dài.
- Các filter như `SetStatus`, `SetResponseHeader`, `DedupeResponseHeader` hoặc `ModifyResponseBody` có trách nhiệm khác nhau; **không filter nào tự bảo đảm hợp đồng nghiệp vụ đúng chỉ vì status đã đổi**.
- Với lỗi sau commit, streaming, redirect, CORS và forwarded headers, hãy kiểm chứng **end-to-end** qua Gateway và backend. Tính đúng đắn, bảo mật và khả năng quan sát phải đi cùng nhau.
