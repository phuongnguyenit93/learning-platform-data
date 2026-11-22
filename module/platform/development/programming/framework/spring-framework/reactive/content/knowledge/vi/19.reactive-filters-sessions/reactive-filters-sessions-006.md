# Request attributes và sự khác biệt với Reactor Context

Trong **Spring WebFlux**, một request có thể đi qua nhiều WebFilter, controller và service trước khi hoàn tất. Các thành phần đó đôi khi cần chia sẻ metadata như request ID, tenant đã được xác định, thông tin locale hoặc dữ liệu đã được một filter kiểm tra. Spring cung cấp hai cơ chế thường gặp nhưng có phạm vi khác nhau:

- **Request attributes** thuộc về một đối tượng ServerWebExchange cụ thể. Chúng phù hợp để một WebFilter đặt dữ liệu rồi controller hoặc thành phần khác đọc lại trong cùng HTTP request.
- **Reactor Context** thuộc về một reactive subscription. Nó truyền metadata theo subscriber chain, kể cả khi pipeline chuyển scheduler/thread, và được đọc qua ContextView.

Hai cơ chế này không tự đồng bộ với nhau. Gọi contextWrite không tự ghi vào exchange.getAttributes(); đặt request attribute cũng không tự tạo key trong Reactor Context. Spring có một cầu nối riêng để đưa chính ServerWebExchange vào Reactor Context, nhưng cầu nối đó không tự sao chép toàn bộ request attributes.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích request attribute được lưu ở đâu và có vòng đời gắn với HTTP exchange như thế nào.
2. Đặt request attribute trong WebFilter và đọc bằng ServerWebExchange hoặc @RequestAttribute.
3. Giải thích Reactor Context là dữ liệu theo subscriber/subscription, không phải biến theo thread.
4. Dùng contextWrite, deferContextual và ContextView để truyền/đọc metadata trong reactive pipeline.
5. Phân biệt hướng truyền Context với hướng phát tín hiệu onNext/onError/onComplete.
6. Hiểu ServerWebExchangeContextFilter và cách lấy exchange từ Reactor Context khi filter đó hiện diện.
7. Chọn đúng cơ chế cho request metadata, tracing, security, transaction và dữ liệu nghiệp vụ.
8. Tránh các lỗi như tự subscribe, giữ exchange trong singleton, chia sẻ mutable state hoặc kỳ vọng request attributes tự xuất hiện trong Reactor Context.
9. Kiểm thử request isolation và context propagation bằng WebTestClient và StepVerifier.

## 2. Request attributes là gì?

Trong WebFlux, mỗi HTTP request được đại diện bởi một ServerWebExchange. Exchange chứa request, response, session và một map các attribute dùng trong phạm vi request hiện tại.

Các API quan trọng:

~~~java
Map<String, Object> attributes = exchange.getAttributes();

exchange.getAttributes().put("app.requestId", "req-42");

String requestId =
    exchange.getAttribute("app.requestId");

String tenant =
    exchange.getAttributeOrDefault("app.tenant", "public");
~~~

- getAttributes() trả về map mutable của exchange hiện tại.
- getAttribute(name) đọc attribute nếu tồn tại; giá trị có thể null.
- getRequiredAttribute(name) đọc giá trị bắt buộc và báo lỗi nếu không tồn tại.
- getAttributeOrDefault(name, defaultValue) đọc hoặc trả về giá trị mặc định.

Request attributes thường được tạo bởi server-side code: WebFilter, handler hoặc một thành phần xử lý request trước controller. Ví dụ filter xác thực một header, tra tenant từ host, tạo request ID hoặc lưu kết quả phân tích request để controller sử dụng.

**Request attribute không phải HTTP header và không tự đến từ client.** Client chỉ gửi dữ liệu qua protocol như path, query, header, cookie và body. Server code quyết định có đặt dữ liệu đó vào exchange attributes hay không. Nếu giá trị được suy ra từ input của client, vẫn phải validate và áp dụng quy tắc tin cậy trước khi sử dụng.

### 2.1. Vòng đời và phạm vi

Request attributes gắn với một ServerWebExchange:

~~~text
HTTP request A
    |
    v
ServerWebExchange A
    |
    +-- attributes: requestId=A
    +-- attributes: tenant=tenant-1
    |
    +-- WebFilter
    +-- Controller
    +-- Service (nếu được truyền exchange/giá trị)
    |
    v
Response A hoàn tất
~~~

Request B có exchange riêng và map attributes riêng. Không nên lưu request attribute vào field của một singleton bean rồi dùng cho request tiếp theo. Cũng không nên giữ ServerWebExchange trong cache/global map sau khi request kết thúc.

Request attributes là map mutable. Dù exchange thuộc một request, pipeline có thể có nhiều callback bất đồng bộ. Hãy ghi dữ liệu ở một bước rõ ràng trước khi gọi chain tiếp theo, ưu tiên value bất biến, và tránh nhiều nhánh đồng thời sửa cùng một map hoặc object mutable.

### 2.2. Đọc attribute trong controller bằng @RequestAttribute

Spring WebFlux hỗ trợ @RequestAttribute để lấy một attribute đã được tạo trước đó, ví dụ bởi WebFilter:

~~~java
@GetMapping("/debug/request")
Mono<String> debug(
        @RequestAttribute("app.requestId") String requestId) {
    return Mono.just("requestId=" + requestId);
}
~~~

Nếu attribute không bắt buộc, có thể khai báo required=false hoặc dùng Optional theo kiểu tham số và resolver phù hợp:

~~~java
@GetMapping("/debug/optional")
Mono<String> debugOptional(
        @RequestAttribute(
            name = "app.client", required = false
        ) Optional<String> client) {
    return Mono.just(client.orElse("unknown"));
}
~~~

Nếu attribute bắt buộc nhưng filter không đặt, argument resolver không thể cung cấp giá trị và request sẽ đi vào xử lý lỗi. Đây thường là lỗi cấu hình/lifecycle: filter chưa được đăng ký, thứ tự filter không phù hợp, hoặc key giữa nơi ghi và nơi đọc không thống nhất.

### 2.3. Đọc trực tiếp qua ServerWebExchange

Khi handler cần nhiều thuộc tính hoặc cần thao tác response/request, nhận exchange trực tiếp:

~~~java
@GetMapping("/debug/exchange")
Mono<Map<String, String>> debug(ServerWebExchange exchange) {
    String requestId =
        exchange.getAttributeOrDefault("app.requestId", "missing");

    String path = exchange.getRequest().getURI().getPath();

    return Mono.just(Map.of(
        "requestId", requestId,
        "path", path
    ));
}
~~~

Cách này tường minh và tiện khi cần request/response/session. Tuy nhiên, nếu một service chỉ cần request ID, truyền String hoặc một DTO metadata thường dễ kiểm thử và giảm phụ thuộc Spring WebFlux hơn là truyền toàn bộ ServerWebExchange xuống sâu trong tầng nghiệp vụ.

## 3. Tạo request attributes trong WebFilter

WebFilter là điểm tự nhiên để tạo hoặc chuẩn hóa metadata trước khi request đến controller. Filter nhận ServerWebExchange và WebFilterChain:

~~~java
@Component
class RequestMetadataFilter implements WebFilter {

    static final String REQUEST_ID_ATTRIBUTE = "app.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(
            REQUEST_ID_ATTRIBUTE, requestId
        );

        return chain.filter(exchange);
    }
}
~~~

Ví dụ trên tạo một ID mới cho mỗi request. Vì attribute được đặt **trước** lời gọi chain.filter(exchange), các filter/controller tiếp theo có thể đọc nó.

Nếu cần nhận một ID do client gửi, hãy xác thực định dạng và giới hạn chiều dài trước khi dùng. Ví dụ:

~~~java
String candidate =
    exchange.getRequest().getHeaders().getFirst("X-Request-Id");

String requestId =
    candidate != null && candidate.matches("[A-Za-z0-9._-]{1,64}")
        ? candidate
        : UUID.randomUUID().toString();

exchange.getAttributes().put(
    RequestMetadataFilter.REQUEST_ID_ATTRIBUTE, requestId
);
~~~

Không đưa chuỗi header chưa kiểm tra thẳng vào log hoặc response. Ký tự điều khiển/newline có thể gây log injection hoặc tạo vấn đề ở các hệ thống downstream.

### 3.1. Filter chain và thứ tự

Các WebFilter được gọi theo một chuỗi. Filter ngoài có thể chuẩn bị dữ liệu trước khi delegate; filter sau đó và controller đọc dữ liệu đã chuẩn bị.

~~~text
Request
  |
  v
Filter A: tạo requestId
  |
  v
Filter B: kiểm tra/ghi tenant
  |
  v
DispatcherHandler
  |
  v
Controller
  |
  v
Response
~~~

Nếu filter B cần dữ liệu do filter A tạo, phải bảo đảm A chạy trước B bằng cấu hình order phù hợp. Không dựa vào thứ tự ngẫu nhiên của bean discovery. Khi một giá trị phụ thuộc authentication, hãy đặt filter sau bước xác thực tương ứng; không tự chọn thứ tự cao nhất nếu điều đó làm filter chạy trước security.

### 3.2. Trả publisher từ filter

Một WebFilter phải trả Mono<Void> đại diện cho toàn bộ request processing:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    exchange.getAttributes().put("app.started", Boolean.TRUE);

    return chain.filter(exchange)
        .doOnSuccess(ignored ->
            exchange.getAttributes().put("app.completed", Boolean.TRUE)
        );
}
~~~

Đây là snippet minh họa lifecycle. Không gọi chain.filter(exchange).subscribe() bên trong filter. Gọi subscribe thủ công tạo một subscription phụ, tách lifecycle khỏi request chính và làm khó truyền lỗi/cancellation. Hãy trả publisher đã ghép để WebFlux quản lý subscription.

## 4. Reactor Context là gì?

Reactor Context là một key-value context gắn với subscriber/subscription trong Reactor. Nó được thiết kế để mang metadata xuyên qua reactive chain mà không cần truyền cùng một tham số qua mọi lambda.

Các kiểu/API thường dùng:

| API | Vai trò |
| --- | --- |
| Context | Context có thể tạo/cập nhật bằng các thao tác bất biến như put, delete, putAll. |
| ContextView | Góc nhìn chỉ đọc, dùng để đọc các key hiện có. |
| contextWrite(...) | Tạo Context mới cho các operator upstream tại vị trí đặt nó. |
| Mono.deferContextual(...) | Đọc Context của subscription khi publisher được subscribe. |
| Flux.deferContextual(...) | Tương tự cho Flux. |
| view.get(key) | Lấy giá trị; báo lỗi nếu key không tồn tại. |
| view.getOrDefault(key, fallback) | Lấy giá trị hoặc fallback. |
| view.hasKey(key) | Kiểm tra key có tồn tại. |

Ví dụ thuần Reactor:

~~~java
static final String REQUEST_ID_KEY = "app.requestId";

Mono<String> result = Mono.deferContextual(view -> {
    String requestId =
        view.getOrDefault(REQUEST_ID_KEY, "missing");

    return Mono.just("requestId=" + requestId);
}).contextWrite(context ->
    context.put(REQUEST_ID_KEY, "req-42")
);
~~~

Khi subscribe, publisher đọc được giá trị req-42. Giá trị đó không được lưu trong một thread cụ thể; nó nằm trong Context của subscription.

### 4.1. Context không phải ThreadLocal

ThreadLocal gắn dữ liệu với Java thread hiện tại. Reactor Context gắn dữ liệu với subscriber chain.

~~~text
ThreadLocal:
  Thread A -> value A
  Thread B -> value B hoặc null

Reactor Context:
  Subscription A -> requestId=A
  Subscription B -> requestId=B
~~~

Một reactive chain có thể chạy trên nhiều thread do publishOn, subscribeOn hoặc I/O bất đồng bộ. Context vẫn có thể được đọc đúng qua các operator Reactor vì nó được truyền theo subscription. ThreadLocal thuần túy không tự theo request khi callback đổi thread.

Context cũng không phải một biến global: cùng một Mono có thể được subscribe nhiều lần với Context khác nhau. Điều này giúp mỗi request giữ metadata riêng nếu ứng dụng không tự chia sẻ mutable object bên trong Context.

### 4.2. Context bất biến, nhưng value có thể mutable

Các thao tác put/delete tạo Context mới; chúng không sửa một Context chung:

~~~java
Context first = Context.of("app.requestId", "A");
Context second = first.put("app.requestId", "B");

// first vẫn có A; second có B.
~~~

Tuy vậy, value được lưu có thể là object mutable. Nếu đưa một HashMap, list hoặc object có state dùng chung vào Context rồi sửa từ nhiều callback, vẫn có nguy cơ race condition. Ưu tiên String, UUID, immutable DTO hoặc giá trị nhỏ có vòng đời rõ.

### 4.3. Context được truyền theo hướng nào?

Luồng tín hiệu dữ liệu thường đi từ source về subscriber:

~~~text
source -- onNext --> map --> flatMap --> subscriber
~~~

Context được cung cấp trong quá trình subscribe theo hướng ngược lại, từ downstream về upstream:

~~~text
subscriber -- Context --> contextWrite --> flatMap --> map --> source
~~~

Vì vậy contextWrite thường được đặt **phía downstream** của đoạn code cần đọc Context. Ví dụ:

~~~java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("app.mode", "default"))
);

Mono<String> result = source
    .contextWrite(context -> context.put("app.mode", "request"));
~~~

Nguồn source nhìn thấy giá trị request. Nếu đặt contextWrite ở phía upstream của operator cần đọc, Context mới có thể không nằm trong subscription context mà operator đó nhìn thấy.

## 5. Request attributes và Reactor Context khác nhau như thế nào?

| Tiêu chí | Request attributes | Reactor Context |
| --- | --- | --- |
| Nơi lưu | Map của ServerWebExchange | Context của subscriber/subscription |
| Phạm vi | Một HTTP exchange | Một reactive subscription |
| Kiểu dữ liệu | Map mutable | Cấu trúc Context bất biến; value vẫn có thể mutable |
| Cách ghi | exchange.getAttributes().put(...) | contextWrite(...) |
| Cách đọc | getAttribute(...), @RequestAttribute | deferContextual(...), ContextView |
| Đổi thread | Không dựa vào thread; truy cập qua exchange | Theo subscriber chain của Reactor |
| Ai có thể đọc | Thành phần có exchange hoặc argument resolver | Operator/publisher có ContextView |
| Tự động đồng bộ | Không | Không |
| Dùng phù hợp | Filter-to-controller metadata trong một request | Tracing, transaction/security context và metadata xuyên reactive chain |

### 5.1. Khi nào dùng request attributes?

Dùng request attributes khi:

- Một WebFilter đã phân tích request và muốn controller đọc lại kết quả.
- Cần lưu thông tin liên quan trực tiếp đến ServerWebExchange, ví dụ một quyết định route hoặc metadata do filter tạo.
- Controller cần truy cập dữ liệu qua @RequestAttribute.
- Một thành phần xử lý HTTP cần chia sẻ kết quả với thành phần khác trong cùng exchange.

Ví dụ: filter xác định tenant từ host đã được xác minh, lưu tenant ID vào exchange; controller đọc tenant bằng @RequestAttribute.

### 5.2. Khi nào dùng Reactor Context?

Dùng Reactor Context khi:

- Nhiều operator/service trong cùng reactive subscription cần correlation ID.
- Cần truyền tracing/transaction/security metadata xuyên qua flatMap hoặc scheduler.
- Không muốn truyền cùng metadata qua nhiều lambda chỉ để phục vụ cross-cutting concern.
- Thư viện/framework reactive đã có integration với Reactor Context.

Ví dụ: một service dùng Mono.deferContextual để lấy trace ID rồi gắn vào telemetry hoặc một client reactive.

### 5.3. Khi nào truyền tham số tường minh?

Nếu dữ liệu là đầu vào nghiệp vụ, hãy truyền qua tham số hoặc DTO:

~~~java
Mono<Order> createOrder(
        String tenantId,
        CreateOrderCommand command) {
    // ...
}
~~~

Tenant ID trong ví dụ là một phần của hợp đồng nghiệp vụ và cần được kiểm tra quyền. Đưa mọi dữ liệu vào Reactor Context làm code khó thấy dependency và khó kiểm thử hơn. Context phù hợp với metadata cross-cutting; tham số tường minh phù hợp với dữ liệu mà logic cần để quyết định kết quả.

## 6. Không tự động chuyển request attributes sang Reactor Context

Hai đoạn sau tác động lên hai nơi khác nhau:

~~~java
exchange.getAttributes().put("app.requestId", "req-42");
~~~

~~~java
return publisher.contextWrite(context ->
    context.put("app.requestId", "req-42")
);
~~~

Đoạn đầu cập nhật exchange attribute map. Đoạn thứ hai cung cấp key trong Reactor Context cho subscription upstream. Không có quy tắc mặc định nào tự copy tất cả attributes vào Context hoặc ngược lại.

Nếu controller dùng @RequestAttribute thì nó đọc exchange. Nếu service dùng deferContextual thì nó đọc Context. Muốn cả hai nhóm thành phần có cùng một request ID, filter phải chủ động đưa cùng giá trị vào cả hai cơ chế, hoặc thiết kế chỉ dùng một cơ chế và truyền tham số phù hợp.

Không tạo hai giá trị độc lập cho cùng một metadata nếu chúng có thể lệch nhau. Trong filter, tạo một requestId duy nhất, sau đó ghi cùng biến đó vào exchange attributes và Context.

## 7. Cầu nối ServerWebExchangeContextFilter

Spring cung cấp ServerWebExchangeContextFilter để đặt **chính ServerWebExchange** vào Reactor Context dưới một key dành riêng. Điều này cho phép code reactive lấy exchange từ ContextView mà không phải truyền exchange qua từng method.

API chính:

- ServerWebExchangeContextFilter.EXCHANGE_CONTEXT_ATTRIBUTE: key lưu exchange.
- ServerWebExchangeContextFilter.getExchange(ContextView): trả Optional<ServerWebExchange> nếu exchange có mặt trong Context.
- Class này có từ Spring Framework 5.2.

Ví dụ:

~~~java
Mono<String> requestId = Mono.deferContextual(view -> {
    return ServerWebExchangeContextFilter.getExchange(view)
        .map(exchange ->
            Mono.just(exchange.getAttributeOrDefault(
                "app.requestId", "missing"
            ))
        )
        .orElseGet(() -> Mono.just("exchange-not-available"));
}).flatMap(publisher -> publisher);
~~~

Đây là snippet tích hợp với import org.springframework.web.filter.reactive.ServerWebExchangeContextFilter. Cầu nối chỉ làm exchange có thể truy cập từ Reactor Context; nó **không tự copy từng key trong exchange.getAttributes() thành key riêng trong Context**. Code vẫn phải lấy attribute từ exchange.

### 7.1. Bảo đảm filter có trong chain

Javadoc mô tả getExchange(ContextView) hoạt động khi ServerWebExchangeContextFilter có trong filter chain. Nếu ứng dụng cần dùng API này, hãy xác nhận filter đã được đăng ký trong chain; có thể khai báo bean WebFilter trong cấu hình WebFlux:

~~~java
@Configuration
class WebFilterConfiguration {

    @Bean
    ServerWebExchangeContextFilter serverWebExchangeContextFilter() {
        return new ServerWebExchangeContextFilter();
    }
}
~~~

Không tạo nhiều bản đăng ký trùng lặp. Nếu ứng dụng/framework đã thêm filter này, dùng bản hiện có. Việc filter có trong chain và thứ tự các filter khác nhau là một phần cấu hình cần kiểm thử.

### 7.2. Không dùng cầu nối như kho dữ liệu toàn cục

Exchange trong Context vẫn thuộc request/subscription đó. Không lấy exchange từ Context rồi lưu vào singleton, cache toàn cục hoặc task chạy sau khi response hoàn tất. Chỉ dùng nó trong phạm vi request đang xử lý; nếu một service cần một giá trị đơn giản, đọc giá trị rồi truyền tham số sẽ giảm phụ thuộc vào WebFlux.

## 8. Ví dụ hoàn chỉnh: một WebFilter ghi cả hai loại context

Ví dụ sau dùng Java 17 và Spring Boot WebFlux. Filter tạo request ID, ghi vào exchange attributes để controller đọc bằng @RequestAttribute, đồng thời ghi cùng ID vào Reactor Context để service reactive đọc bằng deferContextual.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.2. src/main/java/demo/RequestContextApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestContextApplication.class, args);
    }
}
~~~

### 8.3. src/main/java/demo/RequestMetadataFilter.java

~~~java
package demo;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class RequestMetadataFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        "app.requestId";

    public static final String REQUEST_ID_CONTEXT_KEY =
        "app.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String candidate =
            exchange.getRequest().getHeaders()
                .getFirst("X-Request-Id");

        String requestId =
            candidate != null
                && candidate.matches("[A-Za-z0-9._-]{1,64}")
                    ? candidate
                    : UUID.randomUUID().toString();

        // Dành cho @RequestAttribute hoặc exchange.getAttribute(...).
        exchange.getAttributes().put(
            REQUEST_ID_ATTRIBUTE, requestId
        );

        // Dành cho các operator/service trong reactive subscription.
        return chain.filter(exchange)
            .contextWrite(context ->
                context.put(REQUEST_ID_CONTEXT_KEY, requestId)
            );
    }
}
~~~

Cùng một giá trị requestId được ghi vào hai cơ chế. Filter không cần gọi subscribe; publisher từ chain được trả về cho WebFlux. Header do client gửi chỉ được chấp nhận nếu khớp định dạng cho phép, nếu không server tự tạo UUID.

### 8.4. src/main/java/demo/RequestMetadataService.java

~~~java
package demo;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class RequestMetadataService {

    public Mono<Map<String, String>> currentRequest() {
        return Mono.deferContextual(view -> {
            String requestId = view.getOrDefault(
                RequestMetadataFilter.REQUEST_ID_CONTEXT_KEY,
                "missing"
            );

            return Mono.just(Map.of(
                "source", "reactor-context",
                "requestId", requestId
            ));
        });
    }
}
~~~

Service không cần nhận ServerWebExchange. Nó đọc metadata từ subscription hiện tại. Nếu publisher được subscribe ngoài WebFilter chain, key có thể vắng mặt; ví dụ dùng giá trị missing để thể hiện trường hợp đó. Với dữ liệu bắt buộc, nên fail rõ hoặc truyền tham số tường minh thay vì âm thầm dùng fallback.

### 8.5. src/main/java/demo/RequestMetadataController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class RequestMetadataController {

    private final RequestMetadataService service;

    public RequestMetadataController(RequestMetadataService service) {
        this.service = service;
    }

    @GetMapping("/debug/request-attribute")
    Mono<Map<String, String>> fromRequestAttribute(
            @RequestAttribute(
                RequestMetadataFilter.REQUEST_ID_ATTRIBUTE
            ) String requestId) {

        return Mono.just(Map.of(
            "source", "request-attribute",
            "requestId", requestId
        ));
    }

    @GetMapping("/debug/reactor-context")
    Mono<Map<String, String>> fromReactorContext() {
        return service.currentRequest();
    }
}
~~~

Hai endpoint đọc cùng một request ID nhưng từ hai nguồn khác nhau:

- /debug/request-attribute dùng argument resolver của @RequestAttribute.
- /debug/reactor-context gọi service đọc ContextView của subscription.

Nếu hai endpoint được gọi với cùng header X-Request-Id hợp lệ, cả hai trả cùng giá trị do filter đã tạo. Nếu gọi ngoài filter chain, request attribute bắt buộc có thể không resolve được và Context key cũng có thể không tồn tại.

### 8.6. Chạy và gọi thử

Khởi động:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Gọi endpoint request attribute:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/debug/request-attribute
~~~

Body dự kiến:

~~~json
{"source":"request-attribute","requestId":"req-42"}
~~~

Gọi endpoint Reactor Context:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/debug/reactor-context
~~~

Body dự kiến:

~~~json
{"source":"reactor-context","requestId":"req-42"}
~~~

Nếu bỏ header, filter tạo UUID mới nên body vẫn có requestId nhưng giá trị thay đổi ở mỗi request. Không có stdout cố định cho UUID được tạo ngẫu nhiên.

## 9. Context vẫn theo reactive chain khi đổi scheduler

Một lợi ích quan trọng của Reactor Context là dữ liệu không phụ thuộc thread hiện tại. Ví dụ:

~~~java
Mono<String> result = Mono.just("work")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.deferContextual(view -> {
            String requestId =
                view.getOrDefault("app.requestId", "missing");

            return Mono.just(
                value + " for " + requestId
            );
        })
    )
    .contextWrite(context ->
        context.put("app.requestId", "req-42")
    );
~~~

Khi subscribe, kết quả là work for req-42. publishOn có thể chuyển callback phía sau sang worker khác, nhưng Context vẫn được truyền qua các operator Reactor.

Điều này không có nghĩa mọi async API ngoài Reactor tự động giữ Context. Nếu code gọi một ExecutorService hoặc CompletableFuture thuần và chạy callback bên ngoài subscriber chain, hãy truyền giá trị cần thiết qua biến/argument hoặc dùng cơ chế context propagation tương thích. Đừng giả định Reactor Context tự động biến thành ThreadLocal.

## 10. Tách request attributes, Reactor Context và các loại context khác

Các tên gọi gần giống nhau nhưng vai trò khác nhau:

| Cơ chế | Phạm vi | Ví dụ sử dụng |
| --- | --- | --- |
| ServerWebExchange attributes | Một HTTP exchange | Filter lưu request ID/tenant đã xác định cho controller đọc |
| Reactor Context | Một subscription | Trace ID, transaction/security metadata trong reactive chain |
| WebSession attributes | Session người dùng | Tùy chọn giao diện, dữ liệu session cần lưu qua nhiều request |
| HTTP headers/cookies | Protocol request/response | Authorization, Accept-Language, correlation header |
| Spring ApplicationContext | Application/container | Bean, cấu hình, lifecycle ứng dụng |
| ThreadLocal/MDC | Java thread | Thư viện imperative hoặc logging có bridge/restore phù hợp |

Không đặt thông tin cần sống qua nhiều request vào exchange attributes. Không dùng Reactor Context thay cho database/session. Không dùng Spring ApplicationContext làm nơi lưu dữ liệu request. Không dùng ThreadLocal thuần để truyền metadata qua pipeline có thể đổi thread.

### 10.1. Spring Security reactive

Thông tin xác thực trong WebFlux nên truy cập qua API reactive của Spring Security, chẳng hạn ReactiveSecurityContextHolder, thay vì tự lưu Authentication vào một request attribute tùy ý rồi xem nó như nguồn quyền tin cậy.

Spring Security reactive dùng cơ chế context gắn với reactive execution. Không tự ghi đè key nội bộ của framework. Nếu cần tenant hoặc request ID, hãy tách rõ chúng khỏi Authentication và kiểm tra quyền theo chính sách bảo mật.

### 10.2. Reactive transaction

Reactive transaction manager gắn transaction context với reactive execution. Khi dùng TransactionalOperator hoặc @Transactional trên reactive method đúng cách, giữ công việc trong cùng publisher chain để transaction được áp dụng đúng. Gọi subscribe() thủ công tạo subscription phụ có thể tách khỏi transaction dự kiến.

Request attributes có thể giữ một mã tham chiếu nghiệp vụ hoặc thông tin request, nhưng không thay thế transaction context.

### 10.3. Tracing và correlation

Một request ID đơn giản có thể được lưu vào exchange attribute để controller đọc, và vào Reactor Context để service reactive đọc. Với distributed tracing, ưu tiên Micrometer Tracing/propagation chuẩn để trace/span context đi qua HTTP hoặc message broker. Reactor Context trong một process không tự truyền qua network sang service khác.

## 11. Rủi ro bảo mật và thiết kế

### 11.1. Không tin dữ liệu chỉ vì nó nằm trong request attributes

Request attribute thường do server code đặt, nhưng giá trị có thể bắt nguồn từ header, query hoặc cookie của client. Ví dụ, tenantId đọc từ X-Tenant chưa chứng minh người gọi có quyền truy cập tenant đó.

Quy trình đúng:

1. Đọc input từ request.
2. Validate định dạng và tra tenant/user theo nguồn tin cậy.
3. Xác minh principal được phép truy cập tenant.
4. Sau khi xác minh mới đặt metadata đã kiểm tra vào exchange attributes hoặc Reactor Context.
5. Tầng nghiệp vụ vẫn kiểm tra authorization tại boundary cần thiết.

### 11.2. Tránh key collision

Không dùng key quá chung như id, user hoặc tenant trong một ứng dụng có nhiều filter/thư viện. Dùng namespace ổn định như app.requestId, app.tenant hoặc hằng số static final.

Với Reactor Context, có thể dùng một key object riêng được chia sẻ giữa nơi ghi và nơi đọc. Không tạo hai object key mới độc lập rồi kỳ vọng chúng bằng nhau.

### 11.3. Không lưu dữ liệu nhạy cảm không cần thiết

Không đưa access token, mật khẩu, toàn bộ request body hoặc dữ liệu cá nhân vào Context/attributes chỉ để tiện truy cập. Metadata có thể bị log, dump hoặc được một thành phần khác đọc. Chỉ lưu giá trị tối thiểu và kiểm soát nơi tiêu thụ.

### 11.4. Không chia sẻ mutable object giữa nhánh xử lý

Context bất biến không làm object bên trong tự bất biến. Request attributes map cũng mutable. Nếu nhiều nhánh flatMap truy cập cùng object và sửa, phải đồng bộ hoặc thay bằng immutable data. Cách đơn giản nhất thường là ghi một lần trước khi chain chạy và sau đó chỉ đọc.

### 11.5. Không giữ exchange quá vòng đời request

ServerWebExchange chứa request/response và tài nguyên gắn với quá trình xử lý. Không đưa nó vào static field, singleton state hoặc queue chạy nền sau khi response hoàn tất. Nếu cần công việc nền, trích xuất các giá trị nhỏ cần thiết thành command/DTO độc lập trước khi kết thúc request.

## 12. Kiểm thử với WebTestClient và StepVerifier

Kiểm thử cần xác nhận hai cơ chế hoạt động riêng và không rò dữ liệu giữa request/subscription.

Tạo test trong dự án ở mục 8:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.filter.reactive.ServerWebExchangeContextFilter;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class RequestMetadataTest {

    private final WebTestClient client =
        WebTestClient.bindToController(
            new RequestMetadataController(
                new RequestMetadataService()
            )
        )
        .webFilter(
            new RequestMetadataFilter(),
            new ServerWebExchangeContextFilter()
        )
        .build();

    @Test
    void requestAttributeIsCreatedByFilter() {
        client.get()
            .uri("/debug/request-attribute")
            .header("X-Request-Id", "req-A")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.source")
            .isEqualTo("request-attribute")
            .jsonPath("$.requestId")
            .isEqualTo("req-A");
    }

    @Test
    void reactorContextIsCreatedByFilter() {
        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "req-B")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.source")
            .isEqualTo("reactor-context")
            .jsonPath("$.requestId")
            .isEqualTo("req-B");
    }

    @Test
    void twoRequestsDoNotShareRequestId() {
        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "request-one")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.requestId")
            .isEqualTo("request-one");

        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "request-two")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.requestId")
            .isEqualTo("request-two");
    }

    @Test
    void contextIsIsolatedPerSubscription() {
        Mono<String> shared = Mono.deferContextual(view ->
            Mono.just(view.get("app.requestId"))
        );

        StepVerifier.create(
                shared.contextWrite(Context.of("app.requestId", "A"))
            )
            .expectNext("A")
            .verifyComplete();

        StepVerifier.create(
                shared.contextWrite(Context.of("app.requestId", "B"))
            )
            .expectNext("B")
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Hoặc trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Bốn test xác minh:

- Filter đặt request attribute trước khi controller argument resolver chạy.
- Filter đặt Reactor Context cho publisher được WebFlux subscribe.
- Hai HTTP request có request ID riêng, không dùng lại dữ liệu của request trước.
- Cùng một Mono có thể được subscribe với hai Context độc lập.

Test dùng WebTestClient bind trực tiếp controller và thêm WebFilter vào test chain. Nếu dùng @WebFluxTest hoặc @SpringBootTest, cấu hình filter như ứng dụng thật và xác minh order/registration trong application context. Test unit Context không thay thế test tích hợp filter chain.

## 13. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ exchange.getAttributes().put tự thêm key vào Reactor Context | Service dùng deferContextual không tìm thấy key | Ghi riêng vào Context bằng contextWrite hoặc truyền tham số |
| Nghĩ contextWrite cập nhật request attributes | @RequestAttribute không thấy giá trị | Ghi vào exchange.getAttributes() trong filter |
| Đặt attribute sau chain.filter(exchange) | Controller có thể đã chạy trước khi giá trị được ghi | Đặt trước khi delegate sang chain |
| Gọi subscribe() trong WebFilter/service | Tạo subscription phụ, tách lỗi/cancellation/context | Trả publisher đã ghép |
| Dùng ThreadLocal để thay cho Context | Metadata có thể mất hoặc lẫn khi thread được tái sử dụng | Dùng Reactor Context hoặc bridge có kiểm soát |
| Dùng @RequestAttribute nhưng không có filter tạo key | Argument resolver không có giá trị bắt buộc | Đăng ký filter, thống nhất key, hoặc cho phép optional |
| Đưa mọi dữ liệu nghiệp vụ vào Context | Dependency bị ẩn, khó test và bảo trì | Truyền tham số/DTO tường minh |
| Lưu ServerWebExchange vào singleton | Dữ liệu request có thể rò sang request khác, giữ tài nguyên quá lâu | Chỉ dùng trong lifecycle request |
| Nghĩ Context bất biến nghĩa là value cũng bất biến | Mutable object vẫn có thể race | Dùng immutable values |
| Tin tenantId chỉ vì nó nằm trong request attribute | Có thể tin input client chưa được xác thực | Xác minh identity và authorization trước khi lưu |
| Nghĩ ServerWebExchangeContextFilter copy toàn bộ attributes | ContextView không có từng key attribute như mong đợi | Lấy exchange qua getExchange rồi đọc attribute, hoặc put key riêng |
| Dùng Context như cơ chế truyền qua network | Service khác không nhận được metadata | Dùng HTTP/message headers và tracing propagation |
| Tạo key object khác nhau ở nơi ghi và đọc | Context lookup không tìm thấy key | Dùng cùng static final key |
| Bỏ qua filter order | Filter sau đọc metadata trước khi filter tạo nó | Cấu hình order và test filter chain |
| Dùng request attribute cho background job | Exchange có thể đã hoàn tất khi job chạy | Trích xuất DTO/value cần thiết trước khi enqueue |

## 14. Checklist chọn cơ chế

Trước khi lưu metadata, hãy xác định:

1. **Metadata thuộc về ai?** Một HTTP exchange, một reactive subscription, session người dùng hay toàn ứng dụng?
2. **Ai cần đọc?** Controller cần @RequestAttribute, thành phần cần exchange, hay các service/operator reactive cần ContextView?
3. **Dữ liệu có phải đầu vào nghiệp vụ?** Nếu có, truyền bằng tham số hoặc DTO thay vì giấu trong Context.
4. **Đã xác thực nguồn dữ liệu chưa?** Header/query/cookie do client gửi không tự trở thành thông tin tin cậy khi đưa vào attributes.
5. **Filter nào tạo giá trị?** Bảo đảm filter chạy trước thành phần tiêu thụ và ghi trước khi delegate.
6. **Có cần cả hai cơ chế?** Nếu có, tạo một giá trị duy nhất rồi ghi cùng giá trị vào exchange và Context.
7. **Có đổi scheduler hoặc nested publisher không?** Kiểm thử Context xuyên qua flatMap/publishOn và tránh subscribe thủ công.
8. **Có ranh giới ngoài Reactor không?** Truyền metadata rõ ràng hoặc cấu hình context propagation cho executor/library.
9. **Giá trị có mutable hoặc nhạy cảm không?** Ưu tiên immutable metadata nhỏ, key namespace và giới hạn quyền truy cập.
10. **Đã test isolation chưa?** Gửi hai request có ID khác nhau và xác minh không lẫn dữ liệu.

**Ghi nhớ:** Request attributes là dữ liệu gắn với ServerWebExchange, thuận tiện cho việc chia sẻ metadata giữa WebFilter và controller trong cùng HTTP request. Reactor Context là dữ liệu gắn với subscriber/subscription, phù hợp để truyền metadata xuyên reactive chain và qua các lần đổi scheduler. Hai cơ chế tách biệt; chỉ bridge hoặc ghi rõ ràng mới kết nối chúng. Hãy dùng tham số tường minh cho dữ liệu nghiệp vụ, và giữ metadata trong đúng phạm vi vòng đời của nó.

## Tài liệu tham khảo

- Spring Framework — WebFlux @RequestAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestattrib.html
- Spring Framework — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — ServerWebExchangeContextFilter API: https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/web/filter/reactive/ServerWebExchangeContextFilter.html
- Spring Framework — WebFlux WebFilter and WebHandler: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
