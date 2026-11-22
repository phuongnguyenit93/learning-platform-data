# Sửa exchange qua mutate và decorator

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Filter và phiên

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao request, response và exchange trong WebFlux thường được bọc bằng decorator thay vì sửa object gốc tại chỗ.
2. Dùng `ServerHttpRequest.mutate()` và `ServerWebExchange.mutate()` để tạo request/exchange mới với header, method, URI hoặc response đã được thay thế.
3. Phân biệt builder tiện dụng với `ServerHttpRequestDecorator`, `ServerHttpResponseDecorator` và `ServerWebExchangeDecorator`.
4. Truyền exchange đã mutate tới các filter và handler phía sau bằng `chain.filter(updatedExchange)`.
5. Can thiệp vào response trước commit, quan sát body publisher và xử lý `DataBuffer` mà không phá backpressure hoặc ownership.
6. Chọn đúng abstraction để thêm header nội bộ, rewrite request, ghi metric, thay response body hoặc tích hợp một lớp HTTP trung gian.
7. Kiểm thử hành vi mutate/decorator bằng `WebTestClient` và nhận diện lỗi thường gặp như quên dùng exchange mới, sửa header sau commit, đọc body nhiều lần hoặc tự subscribe.

## 1. Vì sao WebFlux dùng mutate và decorator?

Trong WebFlux, `ServerHttpRequest`, `ServerHttpResponse` và `ServerWebExchange` là abstraction của một lượt HTTP. Nhiều implementation được cung cấp bởi server adapter và có thể xem như những object đại diện cho request/response hiện tại. Chúng không được thiết kế để ứng dụng tùy tiện sửa mọi thuộc tính nội bộ.

Ví dụ, request headers thường được expose dưới dạng không thể sửa trực tiếp. Nếu một `WebFilter` cần thêm header nội bộ cho handler phía sau, cách phù hợp là tạo một request mới dựa trên request hiện tại. `mutate()` cung cấp builder cho việc đó.

Decorator giải quyết nhu cầu rộng hơn: tạo một object bọc quanh object gốc, chuyển tiếp hầu hết hành vi sang delegate, nhưng ghi đè đúng method cần thay đổi hoặc quan sát. Ví dụ, một response decorator có thể đếm số byte buffer được ghi, thêm metadata trước commit hoặc điều chỉnh cách ghi body.

Hai cơ chế thường đi cùng nhau:

- **mutate/builder:** tạo request hoặc exchange mới với một số thuộc tính được thay đổi.
- **decorator:** bọc một request/response/exchange để thay đổi hoặc quan sát hành vi tại một ranh giới cụ thể.

Cả hai đều giữ reactive contract. Chúng không tạo một HTTP request mới tới client, không tự gửi response và không khởi động subscription riêng. Thay đổi chỉ có tác dụng khi object mới được truyền vào phần pipeline tiếp theo.

## 2. Kiến trúc của một exchange đã được bọc

Một `ServerWebExchange` chứa request và response cho cùng một lần xử lý HTTP. Filter có thể tạo request decorator, response decorator, rồi xây dựng exchange mới:

```text
HTTP server adapter
        |
        v
  Original Exchange
   |            |
   v            v
 Request      Response
   |            |
 mutate()     decorator
   |            |
   v            v
Updated Request + Decorated Response
          |
          v
 exchange.mutate().request(...).response(...).build()
          |
          v
 Updated ServerWebExchange
          |
          v
 chain.filter(updatedExchange)
          |
          v
 Filter tiếp theo / Handler / Controller
```

Điểm cần nhớ:

1. Request/response gốc vẫn là delegate của các object bọc.
2. Exchange mới cung cấp request/response mà downstream sẽ nhìn thấy.
3. Filter hiện tại phải return publisher từ `chain.filter(updatedExchange)` để lifecycle tiếp tục được quản lý.
4. Các thành phần đã giữ reference tới exchange cũ không tự động đổi sang exchange mới.
5. Không có thao tác nào ở đây làm thay đổi byte HTTP mà client đã gửi trước khi request tới server.

## 3. ServerHttpRequest.mutate(): tạo request đã chỉnh sửa

`ServerHttpRequest.mutate()` trả về `ServerHttpRequest.Builder`. Builder cho phép điều chỉnh một số thành phần request thường gặp rồi tạo request mới bằng `build()`.

Các thao tác quan trọng gồm:

| Builder method | Tác dụng |
| --- | --- |
| `method(HttpMethod)` | Thay method mà downstream nhìn thấy. |
| `uri(URI)` | Thay URI request được expose. |
| `path(String)` | Thay path theo API builder. |
| `headers(Consumer<HttpHeaders>)` | Điều chỉnh bản headers dùng cho request mới. |
| `build()` | Tạo request mới dựa trên request hiện tại. |

Ví dụ thêm header nội bộ:

```java
ServerHttpRequest updatedRequest = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Internal-Request", "checked"))
        .build();
```

Đây là đoạn minh họa trong `WebFilter`. Request mới giữ các thuộc tính còn lại thông qua cơ chế builder/decorator, đồng thời downstream có thể đọc `X-Internal-Request`. Header này do server thêm vào; không được nhầm nó với header client gửi hoặc dùng nó như bằng chứng xác thực.

### 3.1. Sửa method hoặc URI

Builder cũng cho phép thay method/URI mà các thành phần downstream nhìn thấy:

```java
ServerHttpRequest rewritten = exchange.getRequest()
        .mutate()
        .method(HttpMethod.GET)
        .uri(URI.create("https://internal.example/api/items"))
        .build();
```

Đây là **đoạn minh họa**, không phải cấu hình proxy hoàn chỉnh. Việc đổi URI trong request object không tự gửi request tới host mới. Nó chỉ thay metadata được expose cho các thành phần phía sau; routing, reverse proxy hoặc client outbound phải được thiết kế riêng.

Khi thay URI/path, cần chú ý:

- URI có thể chứa query string, encoded path và context path.
- Thay path không đồng nghĩa tự động thay mọi thành phần liên quan như route predicate, forwarded headers hoặc security decision đã chạy trước đó.
- Không nối chuỗi path từ input không tin cậy mà thiếu chuẩn hóa; tránh path traversal và sai lệch giữa encoded/decoded path.
- Nếu rewrite method, phải xem body và headers như `Content-Length`, `Content-Type`, `Transfer-Encoding` có còn phù hợp hay không.
- Thay đổi request ở một filter chỉ ảnh hưởng downstream; filter chạy trước đó đã quan sát request ban đầu.

Đối với rewrite phức tạp, hãy dùng API URI phù hợp và kiểm thử với các trường hợp encoded path, query nhiều giá trị, context path và dấu slash.

### 3.2. Thêm hoặc thay headers

`headers(Consumer<HttpHeaders>)` cho phép chỉnh bản headers mà builder dùng để tạo request mới:

```java
ServerHttpRequest request = exchange.getRequest()
        .mutate()
        .headers(headers -> {
            headers.remove("X-Client-Override");
            headers.set("X-Internal-Source", "gateway");
            headers.add("X-Trace-Tag", "reactive");
        })
        .build();
```

Trong ví dụ:

- `remove` loại header mà downstream không nên nhận.
- `set` thay toàn bộ giá trị hiện tại bằng một giá trị.
- `add` thêm một giá trị mới và giữ các giá trị đã có.

Headers có thể có nhiều giá trị. Dùng `set` hay `add` phải theo semantics của header đó. Ví dụ `Set-Cookie` có thể có nhiều dòng; gộp sai có thể làm hỏng response. Với header bảo mật hoặc định danh, không tin giá trị client tự gửi nếu cần giá trị server-authoritative: xóa hoặc ghi đè tại trust boundary đã xác định.

### 3.3. Gắn request mới vào exchange

Sau khi build request, tạo exchange mới:

```java
ServerWebExchange updated = exchange.mutate()
        .request(request)
        .build();

return chain.filter(updated);
```

Có thể viết ngắn hơn bằng overload nhận consumer builder:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder ->
                builder.headers(headers ->
                        headers.set("X-Internal-Request", "checked")))
        .build();

return chain.filter(updated);
```

Hai cách đều tạo exchange mới với request đã được điều chỉnh. Cách thứ hai tiện khi thay đổi chỉ nằm trong request builder. Nếu đã tự tạo `ServerHttpRequest` decorator, truyền object đó bằng overload `request(ServerHttpRequest)`.

**Lỗi phổ biến:** gọi `exchange.mutate().request(...).build()` nhưng sau đó vẫn gọi `chain.filter(exchange)`. Khi ấy downstream tiếp tục nhận exchange cũ và không nhìn thấy thay đổi. Luôn truyền đúng object mới.

## 4. ServerWebExchange.mutate(): thay request, response hoặc principal

`ServerWebExchange.mutate()` trả về `ServerWebExchange.Builder`. Builder có thể thay request, response và principal của exchange:

| Builder method | Ý nghĩa |
| --- | --- |
| `request(ServerHttpRequest)` | Dùng request mới. |
| `request(Consumer<ServerHttpRequest.Builder>)` | Điều chỉnh request qua builder. |
| `response(ServerHttpResponse)` | Dùng response mới hoặc response decorator. |
| `principal(Mono<Principal>)` | Thay publisher principal mà exchange expose. |
| `build()` | Tạo exchange decorator mới. |

Ví dụ kết hợp request và response:

```java
ServerHttpRequest request = exchange.getRequest()
        .mutate()
        .headers(headers ->
                headers.set("X-Internal-Request", "checked"))
        .build();

ServerHttpResponse response =
        new ServerHttpResponseDecorator(exchange.getResponse());

ServerWebExchange updated = exchange.mutate()
        .request(request)
        .response(response)
        .build();

return chain.filter(updated);
```

Exchange mới giữ liên hệ với exchange ban đầu và cung cấp request/response đã thay thế. Các attributes của request hiện tại vẫn thuộc scope exchange; không dùng chúng như global cache hoặc state dùng chung giữa nhiều request.

### 4.1. Thay principal cần có chủ đích

Builder có overload `principal(Mono<Principal>)`. Nó dành cho integration cần exchange expose principal khác, ví dụ một lớp authentication adapter đã xác minh danh tính và cung cấp principal theo reactive pipeline.

Không dùng nó để giả lập đăng nhập hoặc nâng quyền. Principal phải được tạo từ kết quả xác thực đáng tin cậy; authorization vẫn cần được Spring Security/policy kiểm soát. Nếu chỉ muốn đọc người dùng hiện tại, hãy dùng `exchange.getPrincipal()` hoặc SecurityContext reactive, không cần mutate principal.

### 4.2. Exchange mới không phải request scope mới

`exchange.mutate().build()` không tạo session mới, không tạo request HTTP mới và không reset toàn bộ attributes. Nó tạo một lớp bọc cho exchange hiện tại, thay các thành phần mà builder chỉ định. Session, principal, locale và các dữ liệu khác vẫn tuân theo lifecycle của request gốc, trừ khi bạn chủ động thay phần tương ứng.

Nếu cần lưu metadata dùng trong cùng request, có thể dùng `exchange.getAttributes()`. Nếu dữ liệu phải đi theo reactive subscriber qua operator, cân nhắc Reactor `Context`. Không đặt request-specific state trong field mutable của singleton filter.

## 5. Decorator là gì?

Decorator là object triển khai cùng abstraction với object được bọc và giữ một delegate bên trong. Khi không cần thay đổi hành vi, decorator chuyển lời gọi xuống delegate. Khi cần can thiệp, nó override đúng method.

Spring cung cấp sẵn các base class:

| Decorator | Object được bọc | Mục tiêu thường gặp |
| --- | --- | --- |
| `ServerHttpRequestDecorator` | `ServerHttpRequest` | Điều chỉnh metadata hoặc body request cho downstream. |
| `ServerHttpResponseDecorator` | `ServerHttpResponse` | Can thiệp header, body write, flush hoặc completion của response. |
| `ServerWebExchangeDecorator` | `ServerWebExchange` | Thay cách exchange expose request/response hoặc hành vi exchange rộng hơn. |

Decorator thường được truyền vào `exchange.mutate()` để handler phía sau sử dụng:

```java
ServerHttpRequest request =
        new ServerHttpRequestDecorator(exchange.getRequest());

ServerHttpResponse response =
        new ServerHttpResponseDecorator(exchange.getResponse());

ServerWebExchange updated = exchange.mutate()
        .request(request)
        .response(response)
        .build();
```

Các base decorator đã delegate phần lớn method sang object gốc. Bạn chỉ cần override phần có hành vi mới. Nếu không override gì, wrapper hầu như chỉ là một lớp bọc; hãy dùng builder trực tiếp khi chỉ cần thay vài thuộc tính chuẩn.

## 6. ServerHttpRequestDecorator: can thiệp request sâu hơn

`ServerHttpRequestDecorator` hữu ích khi builder không đủ để thay đổi cách request được đọc. Nó cho phép override các method của `ServerHttpRequest` như `getHeaders()`, `getURI()` hoặc `getBody()`.

### 6.1. Decorate headers

Ví dụ tạo một request wrapper bổ sung header mà không sửa object gốc:

```java
ServerHttpRequest decoratedRequest =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public HttpHeaders getHeaders() {
                HttpHeaders headers = new HttpHeaders();
                headers.putAll(super.getHeaders());
                headers.set("X-Internal-Request", "checked");
                return HttpHeaders.readOnlyHttpHeaders(headers);
            }
        };
```

Đây là **đoạn minh họa**. Wrapper trả bản headers mới, sao chép headers gốc rồi thêm giá trị. Trả headers read-only giúp downstream không sửa trực tiếp bản metadata mà decorator cung cấp.

Với thay đổi headers thông thường, `request.mutate().headers(...)` ngắn và ít lỗi hơn. Dùng decorator khi cần tùy chỉnh cách expose request hoặc kết hợp nhiều hành vi override.

### 6.2. Decorate URI hoặc path

Một decorator có thể override `getURI()` hoặc `getPath()` để cung cấp view request khác. Khi làm vậy, hãy giữ các API nhất quán: nếu URI thay đổi nhưng path vẫn trả giá trị cũ, routing và code đọc metadata có thể nhìn thấy hai thông tin mâu thuẫn.

Không tự tạo URI bằng phép nối chuỗi đơn giản khi có encoded characters, query parameters hoặc context path. Hãy dùng URI builder, giữ nguyên phần cần bảo toàn và kiểm thử các trường hợp có dấu cách, Unicode, dấu phần trăm, dấu slash và query lặp.

### 6.3. Decorate request body

`getBody()` trả publisher `Flux<DataBuffer>`. Một request decorator có thể wrap publisher này để quan sát hoặc biến đổi byte stream:

```java
@Override
public Flux<DataBuffer> getBody() {
    return super.getBody()
            .doOnNext(buffer ->
                    log.debug("request chunk: {} bytes",
                            buffer.readableByteCount()));
}
```

Đây là **đoạn minh họa bên trong `ServerHttpRequestDecorator`**. Nó chỉ quan sát số byte còn đọc được trong từng buffer, không đọc nội dung và không tiêu thụ buffer. Một chunk không tương ứng một JSON object hay một HTTP packet.

Nếu muốn sửa body, phải tính đến các yếu tố sau:

- Body là stream một lần. Một subscription riêng để log hoặc cache có thể khiến downstream không còn dữ liệu.
- Buffer có thể dùng pooled/native memory. Không giữ buffer sau lifecycle, không release hai lần và không đọc vượt giới hạn.
- Khi thay đổi số byte, các header như `Content-Length` có thể không còn đúng.
- Body có thể lớn hoặc vô hạn; gom toàn bộ vào bộ nhớ làm mất lợi ích streaming và có nguy cơ cạn memory.
- Lỗi/cancel phải truyền đúng theo publisher; không nuốt error hoặc tự subscribe.

Nếu cần đọc lại body, phải xây dựng chiến lược cache/replay có giới hạn và tạo buffer mới đúng cách. Đừng chỉ gọi `getBody()` hai lần rồi giả định server sẽ phát lại byte từ đầu.

## 7. ServerHttpResponseDecorator: can thiệp response

`ServerHttpResponseDecorator` thường được dùng khi cần quan sát hoặc điều chỉnh cách response được ghi. Các method quan trọng được kế thừa từ `ServerHttpResponse`/`ReactiveHttpOutputMessage`:

- `getHeaders()` và `getCookies()` để truy cập metadata response.
- `beforeCommit(...)` để đăng ký thao tác reactive ngay trước commit.
- `writeWith(Publisher<DataBuffer>)` để ghi body.
- `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` để ghi các nhóm buffer và flush theo nhóm.
- `setComplete()` để hoàn tất response không có body do ứng dụng ghi.

### 7.1. Thêm response header trước commit

Ví dụ đăng ký header trên response decorator:

```java
ServerHttpResponseDecorator decorated =
        new ServerHttpResponseDecorator(exchange.getResponse());

decorated.beforeCommit(() -> {
    decorated.getHeaders().set("X-Response-Decorator", "applied");
    return Mono.empty();
});

ServerWebExchange updated = exchange.mutate()
        .response(decorated)
        .build();

return chain.filter(updated);
```

Callback `beforeCommit` trả `Mono<Void>`. Header được thêm trước thời điểm response commit nên có thể được gửi cho client. Không gọi `subscribe()` trong callback; framework sẽ compose và thực thi publisher commit.

Không sửa status/header sau khi response đã commit. Khi body streaming đã bắt đầu, server không thể quay lại thay status đã gửi. Nếu cần thêm metadata cho mọi nhánh response, đăng ký callback trước khi gọi chain để bao phủ cả response có body và response rỗng.

### 7.2. Quan sát body được ghi bằng writeWith

Decorator có thể wrap publisher body để ghi metric mà không tiêu thụ buffer:

```java
@Override
public Mono<Void> writeWith(Publisher<? extends DataBuffer> body) {
    return super.writeWith(
            Flux.from(body)
                    .doOnNext(buffer ->
                            bytesWritten.addAndGet(
                                    buffer.readableByteCount())));
}
```

Đây là **đoạn minh họa bên trong response decorator**; `bytesWritten` là bộ đếm được tạo riêng cho request. `Flux.from(body)` chuyển publisher đầu vào thành Flux để gắn side effect, sau đó vẫn chuyển cùng buffer xuống delegate. Chỉ đọc `readableByteCount`, không gọi `read` để tiêu thụ bytes.

### 7.3. Phải xử lý cả writeAndFlushWith khi hỗ trợ streaming

Một số response streaming ghi body theo nhóm buffer qua `writeAndFlushWith`. Nếu decorator chỉ override `writeWith`, metric hoặc logic quan sát có thể bỏ sót đường ghi theo nhóm.

```java
@Override
public Mono<Void> writeAndFlushWith(
        Publisher<? extends Publisher<? extends DataBuffer>> body) {

    return super.writeAndFlushWith(
            Flux.from(body)
                    .map(group -> Flux.from(group)
                            .doOnNext(buffer ->
                                    bytesWritten.addAndGet(
                                            buffer.readableByteCount()))));
}
```

Đây là **đoạn minh họa**. Mỗi publisher con đại diện một nhóm buffer; decorator wrap từng nhóm và chuyển tiếp nó cho delegate. Không flatten tất cả nhóm nếu semantics flush theo nhóm có ý nghĩa với giao thức streaming.

### 7.4. Giới hạn của metric đếm DataBuffer

Tổng `readableByteCount()` là số byte buffer mà response decorator quan sát được tại vị trí đó. Nó không nhất thiết bằng số byte cuối cùng client nhận qua mạng, vì server có thể nén, mã hóa TLS, thêm framing hoặc gặp lỗi/cancel sau một phần body.

Với response rỗng, metric có thể bằng 0. Với streaming bị cancel, nó chỉ phản ánh những buffer đã đi qua decorator tới thời điểm cancel. Nếu cần số byte trên wire, cần metric ở transport/server hoặc hạ tầng proxy thích hợp.

### 7.5. DataBuffer ownership

Decorator phải giữ đúng ownership của buffer:

- Nếu chỉ quan sát metadata như `readableByteCount`, hãy chuyển nguyên buffer xuống delegate.
- Không giữ tham chiếu tới buffer pooled sau khi write kết thúc.
- Không tự release buffer mà delegate/downstream vẫn còn sở hữu.
- Nếu tạo buffer thay thế, xác định rõ ai release buffer cũ và buffer mới.
- Xử lý error, cancel và discard theo API `DataBufferUtils`/Reactor phù hợp.

Một decorator đọc body để log có thể vô tình làm thay đổi read position, khiến codec hoặc server ghi thiếu dữ liệu. Logging byte stream cần được thiết kế như một thao tác streaming có ownership rõ ràng.

## 8. ServerWebExchangeDecorator: bọc toàn bộ exchange

`ServerWebExchangeDecorator` hữu ích khi muốn tạo exchange wrapper có hành vi tùy chỉnh ngoài việc thay request/response bằng builder. Nó nhận exchange gốc làm delegate và cho phép override `getRequest()`, `getResponse()` hoặc method exchange khác.

Ví dụ khái niệm:

```java
ServerWebExchange decoratedExchange =
        new ServerWebExchangeDecorator(exchange) {
            @Override
            public ServerHttpRequest getRequest() {
                return decoratedRequest;
            }

            @Override
            public ServerHttpResponse getResponse() {
                return decoratedResponse;
            }
        };

return chain.filter(decoratedExchange);
```

Đây là **đoạn minh họa**, giả sử `decoratedRequest` và `decoratedResponse` đã được tạo trước. Decorator mặc định delegate những method khác về exchange gốc. Nếu override thêm session/principal/attributes, phải giữ semantics và lifecycle tương ứng.

Trong phần lớn filter thông thường, `exchange.mutate().request(...).response(...).build()` đã đủ và dễ đọc. Tự viết `ServerWebExchangeDecorator` khi cần một exchange abstraction chuyên biệt, chẳng hạn adapter test hoặc một lớp integration có nhiều hành vi liên quan.

## 9. Ví dụ WebFilter kết hợp mutate và decorator

Filter dưới đây thực hiện ba việc:

1. Thêm header nội bộ vào request để controller phía sau đọc được.
2. Bọc response để thêm header trước commit và đếm byte buffer được ghi.
3. Ghi log kết cục cùng số byte sau khi chain hoàn tất hoặc bị hủy.

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.reactivestreams.Publisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ExchangeMutationFilter implements WebFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ExchangeMutationFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong bytesWritten = new AtomicLong();

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                        headers.set("X-Internal-Request", "checked"))
                .build();

        ServerHttpResponseDecorator response =
                new ServerHttpResponseDecorator(exchange.getResponse()) {

            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {

                return super.writeWith(
                        Flux.from(body)
                                .doOnNext(buffer ->
                                        bytesWritten.addAndGet(
                                                buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>> body) {

                return super.writeAndFlushWith(
                        Flux.from(body)
                                .map(group -> Flux.from(group)
                                        .doOnNext(buffer ->
                                                bytesWritten.addAndGet(
                                                        buffer.readableByteCount()))));
            }
        };

        response.beforeCommit(() -> {
            response.getHeaders()
                    .set("X-Response-Decorator", "applied");
            return Mono.empty();
        });

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .response(response)
                .build();

        return chain.filter(updated)
                .doFinally(signal -> log.info(
                        "method={} path={} bytes={} signal={}",
                        request.getMethodValue(),
                        request.getURI().getPath(),
                        bytesWritten.get(),
                        signal));
    }
}
```

Đây là **class WebFilter hoàn chỉnh**. `AtomicLong` được tạo bên trong mỗi lần filter xử lý một exchange, vì vậy bộ đếm không bị chia sẻ giữa các request. `doFinally` gắn vào publisher của chain để ghi nhận `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`.

Filter không tự subscribe vào chain. Request và response đã bọc được gắn vào exchange mới, rồi exchange mới được truyền xuống bằng `chain.filter(updated)`. Các endpoint phía sau sẽ nhìn thấy header request nội bộ và response decorator sẽ tham gia quá trình ghi body.

Metric byte chỉ tính buffer mà decorator quan sát; nó không phải network-wire metric. Nếu ứng dụng dùng SSE hoặc streaming, override cả `writeWith` và `writeAndFlushWith` để bao phủ hai đường ghi.

## 10. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dưới đây dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và `spring-boot-starter-webflux`. Nó có một WebFilter mutate request, decorate response, controller đọc header nội bộ và hai integration test kiểm tra response.

Cấu trúc:

```text
exchange-mutate-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ExchangeMutationApplication.java
    │   ├── ExchangeMutationFilter.java
    │   └── DemoController.java
    └── test/java/demo/
        └── ExchangeMutationIntegrationTest.java
```

### 10.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>exchange-mutate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.2. ExchangeMutationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeMutationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeMutationApplication.class, args);
    }
}
```

### 10.3. ExchangeMutationFilter.java

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.reactivestreams.Publisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ExchangeMutationFilter implements WebFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ExchangeMutationFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong bytesWritten = new AtomicLong();

        ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers ->
                        headers.set("X-Internal-Request", "checked"))
                .build();

        ServerHttpResponseDecorator response =
                new ServerHttpResponseDecorator(exchange.getResponse()) {
            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {
                return super.writeWith(
                        Flux.from(body)
                                .doOnNext(buffer ->
                                        bytesWritten.addAndGet(
                                                buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>> body) {
                return super.writeAndFlushWith(
                        Flux.from(body)
                                .map(group -> Flux.from(group)
                                        .doOnNext(buffer ->
                                                bytesWritten.addAndGet(
                                                        buffer.readableByteCount()))));
            }
        };

        response.beforeCommit(() -> {
            response.getHeaders()
                    .set("X-Response-Decorator", "applied");
            return Mono.empty();
        });

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .response(response)
                .build();

        return chain.filter(updated)
                .doFinally(signal -> log.info(
                        "method={} path={} bytes={} signal={}",
                        request.getMethodValue(),
                        request.getURI().getPath(),
                        bytesWritten.get(),
                        signal));
    }
}
```

### 10.4. DemoController.java

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    public record InspectResult(
            String method,
            String path,
            String internalRequestHeader) {}

    @GetMapping("/inspect")
    public Mono<InspectResult> inspect(ServerHttpRequest request) {
        return Mono.just(new InspectResult(
                request.getMethodValue(),
                request.getPath().value(),
                request.getHeaders().getFirst("X-Internal-Request")));
    }

    @PostMapping(
            value = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body.map(value -> "echo: " + value);
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.just("first", "second", "third");
    }
}
```

### 10.5. ExchangeMutationIntegrationTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeMutationIntegrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void mutatedRequestAndDecoratedResponseAreVisible() {
        client.get()
                .uri("/inspect")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Decorator", "applied")
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/inspect")
                .jsonPath("$.internalRequestHeader").isEqualTo("checked");
    }

    @Test
    void responseDecoratorPreservesBodyAndAddsHeader() {
        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Decorator", "applied")
                .expectBody(String.class)
                .isEqualTo("echo: hello");
    }
}
```

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Gửi request kiểm tra:

```bash
curl -i http://localhost:8080/inspect
curl -i -X POST http://localhost:8080/echo \
  -H "Content-Type: text/plain" \
  --data "hello"
curl -i -N http://localhost:8080/events
```

Kết quả cần quan sát:

- `GET /inspect` trả JSON có `method` là `GET`, `path` là `/inspect` và `internalRequestHeader` là `checked`.
- Cả hai endpoint có body đều trả header `X-Response-Decorator: applied` do callback `beforeCommit` thêm.
- `POST /echo` trả nguyên nội dung đã xử lý là `echo: hello`; decorator quan sát buffer nhưng không tiêu thụ body.
- `GET /events` trả ba event theo dạng `text/event-stream`. Đường ghi streaming có thể đi qua `writeAndFlushWith`.
- Log filter có method, path, số byte buffer quan sát và signal kết thúc. Giá trị byte phụ thuộc encoding/body và không tính framing/TLS/network overhead.

Chạy integration test:

```bash
mvn test
```

Hai test xác nhận request mới tới được controller, response decorator thêm header trước commit và body vẫn được ghi nguyên vẹn. Ví dụ không kiểm thử việc rewrite raw body hoặc quản lý pooled buffer tùy chỉnh; những thao tác đó cần test riêng cho error/cancel và ownership.

## 11. Khi nào dùng builder, khi nào dùng decorator?

| Nhu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Thêm/xóa/thay request header | `request.mutate().headers(...)` | Ngắn, thể hiện rõ thay đổi metadata. |
| Thay method hoặc URI | `request.mutate()` | Builder có API chuẩn cho các thuộc tính này. |
| Thay request object hoàn toàn | `exchange.mutate().request(request)` | Downstream nhận request đã chuẩn bị. |
| Thêm header response trước commit | `beforeCommit` trên response hoặc response decorator | Đảm bảo thao tác diễn ra trước khi gửi headers. |
| Đếm/quan sát DataBuffer response | `ServerHttpResponseDecorator` | Có thể wrap `writeWith` và `writeAndFlushWith`. |
| Thay đổi cách đọc request body | `ServerHttpRequestDecorator` | Override `getBody()` khi thực sự cần. |
| Tùy chỉnh exchange rộng hơn | `ServerWebExchangeDecorator` | Bọc cả exchange và override hành vi cụ thể. |
| Chỉ lưu trace ID cho filter/controller cùng request | `exchange.getAttributes()` hoặc Reactor `Context` | Không cần tạo decorator chỉ để lưu metadata. |

Builder là lựa chọn đầu tiên cho thay đổi metadata phổ biến. Decorator phù hợp khi cần can thiệp vào hành vi của method hoặc stream. Một decorator chỉ chuyển tiếp mọi lời gọi mà không thêm behavior thường không tạo giá trị rõ ràng.

## 12. Thứ tự filter và phạm vi thay đổi

Một filter chỉ ảnh hưởng tới các thành phần chạy **sau nó** trong chain. Nếu filter A mutate request rồi gọi filter B, filter B và handler có thể đọc request mới. Filter chạy trước A đã quan sát request gốc.

Ví dụ:

```text
Filter A
  |
  v
Filter B: thêm X-Internal-Request
  |
  v
Filter C: đọc X-Internal-Request = checked
  |
  v
Controller: đọc X-Internal-Request = checked
```

Nếu filter cần chạy trước Spring Security hoặc sau authentication, thứ tự filter phải được cấu hình có chủ đích. Không mặc định một header được thêm ở filter bất kỳ sẽ có sẵn cho mọi quyết định bảo mật; quyết định đã diễn ra trước đó không tự chạy lại sau mutation.

Tương tự, response decorator được cài ở filter ngoài sẽ bao bọc response từ các filter/handler bên trong. Nếu một filter phía trong tự thay response lần nữa, thứ tự và delegate chain quyết định decorator nào quan sát được việc ghi. Hãy kiểm thử theo đúng thứ tự filter thực tế của ứng dụng.

## 13. Các lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo exchange mới nhưng vẫn gọi `chain.filter(exchange)` | Downstream không thấy request/response đã mutate | Truyền đúng `updatedExchange` vào chain. |
| Nghĩ `mutate()` sửa object gốc tại chỗ | Thành phần giữ reference cũ không thấy thay đổi | Xem kết quả `build()` là object wrapper mới và truyền nó đi tiếp. |
| Thêm header sau response commit | Header không còn được gửi hoặc thay đổi bị bỏ qua | Đăng ký `beforeCommit` trước khi chain bắt đầu ghi response. |
| Chỉ override `writeWith` khi ứng dụng streaming | Bỏ sót đường `writeAndFlushWith` | Override cả hai khi metric/transform cần bao phủ streaming. |
| Gọi `subscribe()` trong decorator | Tách body write khỏi response lifecycle | Return publisher từ `super.writeWith`/`super.writeAndFlushWith`. |
| Đọc DataBuffer để log rồi chuyển tiếp | Có thể thay đổi read position và làm body thiếu byte | Chỉ quan sát metadata hoặc copy/release theo ownership rõ ràng. |
| Release buffer mà delegate vẫn đang dùng | Double release hoặc lỗi ghi response | Chỉ release khi code thực sự sở hữu buffer và theo đúng API. |
| Cache toàn bộ request body không giới hạn | Tăng memory và mất streaming | Đặt giới hạn body, cân nhắc streaming hoặc replay có giới hạn. |
| Thay body nhưng giữ Content-Length cũ | Server/client có thể đọc sai kích thước | Cập nhật/xóa metadata độ dài phù hợp với body mới. |
| Thay URI bằng nối chuỗi đơn giản | Sai encoded path, query hoặc context path | Dùng URI builder và kiểm thử edge cases. |
| Dùng request header client gửi như thông tin xác thực | Có thể tin dữ liệu giả mạo | Xác minh ở trust boundary và dùng Spring Security. |
| Dùng mutable field trong filter để lưu request hiện tại | Các request đồng thời ghi đè state | Tạo state cục bộ trong mỗi lần filter hoặc dùng exchange attributes/Context. |
| Dùng decorator chỉ để thêm một header đơn giản | Code dài hơn cần thiết | Dùng request builder hoặc response header trước commit. |
| Nghĩ mutate principal là xác thực người dùng | Có thể tạo principal không đáng tin | Chỉ thay principal từ authentication đã xác minh. |
| Ghi metric byte và gọi đó là số byte client nhận | Bỏ qua transport, compression, TLS và cancel | Gọi đúng là byte buffer được quan sát tại decorator. |
| Không kiểm thử cancellation/error | Decorator có thể giữ resource hoặc metric sai | Test complete, error, cancel và streaming khi behavior có ảnh hưởng lifecycle. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ServerHttpRequest.mutate()` trả về gì và dùng để làm gì?  
**Đáp án:** Nó trả về builder để tạo request mới với một số thuộc tính như method, URI, path hoặc headers được điều chỉnh.

**Câu 2.** Vì sao phải gọi `chain.filter(updatedExchange)` sau khi mutate?  
**Đáp án:** Vì object mới chỉ có hiệu lực với downstream khi được truyền vào chain. Nếu truyền exchange gốc, handler không thấy các thay đổi.

**Câu 3.** `ServerWebExchange.mutate()` có thể thay những thành phần nào?  
**Đáp án:** Có thể thay request, response và principal publisher rồi build exchange wrapper mới.

**Câu 4.** Khi nào nên dùng `ServerHttpRequestDecorator` thay builder?  
**Đáp án:** Khi cần override hành vi request như cách expose headers, URI hoặc body mà builder không đủ để biểu diễn.

**Câu 5.** Tại sao response header nên được thêm trong `beforeCommit`?  
**Đáp án:** Callback chạy trước khi response commit, vì vậy header vẫn có thể được gửi. Sau commit không thể đổi headers đã gửi.

**Câu 6.** Vì sao decorator streaming cần cân nhắc `writeAndFlushWith`?  
**Đáp án:** Một số body streaming được ghi theo nhóm buffer và flush từng nhóm qua method này; chỉ quan sát `writeWith` có thể bỏ sót chúng.

**Câu 7.** Đọc `readableByteCount()` có tiêu thụ DataBuffer không?  
**Đáp án:** Không; nó trả số byte còn đọc được. Không gọi thao tác đọc byte nếu mục tiêu chỉ là đếm.

**Câu 8.** Decorator có tự làm body request có thể đọc nhiều lần không?  
**Đáp án:** Không. Request body vẫn là publisher stream với lifecycle riêng. Muốn replay phải cache/recreate body có giới hạn và quản lý DataBuffer đúng cách.

**Câu 9.** Metric byte trong response decorator có bằng số byte client nhận trên wire không?  
**Đáp án:** Không nhất thiết. Nó đếm byte buffer ở vị trí decorator, trước các lớp transport, framing, compression hoặc TLS.

**Câu 10.** Có nên mutate principal chỉ để thêm tên người dùng vào log không?  
**Đáp án:** Không. Hãy đọc principal đã xác thực và ghi log. Chỉ thay principal khi một integration đáng tin cậy cần cung cấp principal khác cho downstream.

## Ghi nhớ

- `mutate()` tạo builder và `build()` tạo object wrapper mới. Thay đổi chỉ đến downstream khi filter truyền đúng exchange mới vào `chain.filter(updated)`.
- Dùng `ServerHttpRequest.mutate()` hoặc `exchange.mutate().request(...)` cho thay đổi method, URI, path và headers thông thường.
- Dùng `ServerHttpRequestDecorator` khi cần override hành vi request, đặc biệt là `getBody()`; body vẫn là stream một lần và DataBuffer có ownership.
- Dùng `ServerHttpResponseDecorator` để quan sát hoặc can thiệp `writeWith`/`writeAndFlushWith`. Đăng ký headers qua `beforeCommit` trước khi response commit.
- `ServerWebExchangeDecorator` cho phép bọc toàn bộ exchange; `exchange.mutate()` thường đủ cho nhu cầu thay request/response thông thường.
- Luôn giữ reactive lifecycle: return/compose publisher, không tự subscribe hoặc block; xử lý error/cancel và pooled DataBuffer đúng cách.

### Tài liệu tham khảo

1. [Spring Framework – ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): builder mutate, request, response và principal.
2. [Spring Framework – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request builder và metadata.
3. [Spring Framework – ServerHttpRequestDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html): decorator cho request.
4. [Spring Framework – ServerHttpResponseDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponseDecorator.html): decorator cho response.
5. [Spring Framework – ServerWebExchangeDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchangeDecorator.html): wrapper cho exchange.
6. [Spring Framework – ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): beforeCommit, writeWith, writeAndFlushWith và setComplete.
7. [Spring Framework – WebFlux Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): filter concepts and reactive chain patterns.
