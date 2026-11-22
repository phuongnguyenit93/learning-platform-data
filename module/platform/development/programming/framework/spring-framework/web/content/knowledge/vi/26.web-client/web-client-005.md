# ExchangeFilterFunction và cấu hình dùng chung trong WebClient

## 1. Bối cảnh: vì sao WebClient cần bộ lọc?

`WebClient` là HTTP client theo lập trình phản ứng của Spring WebFlux. Một ứng dụng thường gọi nhiều API bên ngoài và các lần gọi đó có những quy tắc lặp lại: đặt địa chỉ gốc, thêm header, gửi thông tin xác thực, ghi log, gắn mã theo dõi hoặc quan sát trạng thái trả về.

Nếu từng phương thức tự lặp lại các việc này, logic nghiệp vụ bị trộn với cách thực hiện HTTP; khi thay đổi chính sách, ta phải sửa nhiều chỗ. `WebClient.Builder` giải quyết phần **cấu hình mặc định dùng chung**, còn `ExchangeFilterFunction` xử lý **logic cắt ngang từng lần trao đổi HTTP**. Hai cơ chế phối hợp với nhau nhưng có nhiệm vụ khác nhau.

Ví dụ: dịch vụ đơn hàng cần gọi API tồn kho. Phần nghiệp vụ chỉ quan tâm “lấy tồn kho của sản phẩm”; cấu hình dùng chung có thể giữ `baseUrl` và `Accept`, còn filter có thể thêm mã truy vết và ghi nhận phương thức, đường dẫn, mã trạng thái. Một request đặc biệt vẫn có thể được tùy chỉnh riêng.

Mục tiêu của bài:

- Hiểu filter chạy ở đâu trong chuỗi gọi `WebClient` và ý nghĩa của `ClientRequest`, `ExchangeFunction`, `ClientResponse`.
- Biết tạo, đăng ký, sắp xếp và kết hợp các `ExchangeFilterFunction`.
- Phân biệt `defaultHeader`, `defaultRequest`, `filter` và `mutate()`; tổ chức cấu hình cho nhiều HTTP client.
- Biết cách đưa dữ liệu riêng từng request vào filter, kiểm thử và tránh các lỗi liên quan đến phản ứng bất đồng bộ, bảo mật, response body.

## 2. Mô hình hoạt động của ExchangeFilterFunction

Một filter có hợp đồng cốt lõi:

```java
Mono<ClientResponse> filter(ClientRequest request, ExchangeFunction next);
```

Trong đó:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ClientRequest` | Request đã được biểu diễn thành phương thức, URL, headers, cookies, body và attributes; về nguyên tắc là đối tượng bất biến. |
| `ExchangeFunction next` | Bước tiếp theo trong chuỗi: có thể là filter kế tiếp hoặc thành phần thực sự gửi HTTP. |
| `ClientResponse` | Phản hồi HTTP gồm trạng thái, headers và body dạng luồng để xử lý tiếp. |
| `Mono<ClientResponse>` | Kết quả bất đồng bộ của một lần trao đổi; filter có thể biến đổi, quan sát hoặc trả về lỗi theo ngữ nghĩa Reactor. |

Một filter tối giản:

```java
ExchangeFilterFunction addClientHeader = (request, next) -> {
    ClientRequest updated = ClientRequest.from(request)
            .headers(headers -> headers.set("X-Client-Name", "inventory-service"))
            .build();

    return next.exchange(updated);
};

WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example")
        .filter(addClientHeader)
        .build();
```

`ClientRequest.from(request)` sao chép dữ liệu request hiện có vào builder để thay đổi phần cần thiết. `headers(...set(...))` đặt một giá trị header; dùng `header("Tên", "giá trị")` để thêm giá trị nếu đó là chủ đích. Trong filter trên, `next.exchange(updated)` giữ chuỗi xử lý tiếp tục. Không gọi `next.exchange` nghĩa là filter chặn đường đi mặc định và phải tự trả một `Mono<ClientResponse>` phù hợp hoặc một tín hiệu lỗi.

**Thời điểm chạy:** lời gọi `client.get().uri(...).retrieve().bodyToMono(...)` tạo mô tả công việc phản ứng. Filter thực thi khi luồng được đăng ký (subscribe), chẳng hạn bởi một tầng trên hoặc `block()` trong chương trình minh họa. Không được mặc định rằng chỉ dựng `Mono` đã phát đi request.

### 2.1 Thứ tự filter: đi và về

Giả sử builder đăng ký `filterA` rồi `filterB`:

```text
Đăng ký luồng
    |
    v
A: trước next.exchange(...)
    |
    v
B: trước next.exchange(...)
    |
    v
Trao đổi HTTP
    |
    v
B: quan sát ClientResponse
    |
    v
A: quan sát ClientResponse
    |
    v
Mã gọi WebClient nhận kết quả
```

Thứ tự phía request là **A → B → HTTP**; khi response quay về qua các bước `flatMap`/`doOnNext` tương ứng, thứ tự là **HTTP → B → A**. Nếu lỗi xảy ra trước khi có `ClientResponse`, các nhánh `doOnError`/`onErrorResume` được đăng ký dọc chuỗi sẽ quan sát hoặc xử lý tín hiệu đó. Mỗi lần đăng ký luồng có thể thực hiện lại trao đổi; lưu ý này đặc biệt quan trọng khi kết hợp `retry`.

Một filter ghi nhận thông tin đầu vào/đầu ra nhưng không tiêu thụ body:

```java
ExchangeFilterFunction logMetadata = (request, next) -> {
    long started = System.nanoTime();
    System.out.println("Request: " + request.method() + " " + request.url().getPath());

    return next.exchange(request)
            .doOnNext(response -> {
                long elapsedMs = (System.nanoTime() - started) / 1_000_000;
                System.out.println("Status: " + response.statusCode().value()
                        + ", elapsedMs=" + elapsedMs);
            })
            .doOnError(error ->
                    System.err.println("Transport/filter failure: "
                            + error.getClass().getSimpleName()));
};
```

Đây là ví dụ học tập; trong ứng dụng thực, dùng logger có cấu hình và thư viện quan sát được tích hợp. Không ghi `Authorization`, `Cookie`, body chứa dữ liệu cá nhân hoặc toàn bộ URL có tham số bí mật. Nếu cần đo thời gian cho từng lần đăng ký hoặc thử lại, đặt thời điểm bắt đầu trong `Mono.defer(...)` hoặc cơ chế đo chuyên dụng để tránh dùng lại mốc thời gian không phù hợp.

## 3. Tạo filter theo từng mục đích

### 3.1 Dạng đầy đủ và dạng bộ chuyển đổi

Dạng lambda hai tham số `(request, next) -> ...` hữu ích khi phải xem cả request và response. Với thao tác một phía, có thể dùng:

```java
ExchangeFilterFunction requestOnly =
        ExchangeFilterFunction.ofRequestProcessor(request ->
                Mono.just(ClientRequest.from(request)
                        .headers(headers -> headers.set("X-Source", "web"))
                        .build()));

ExchangeFilterFunction responseOnly =
        ExchangeFilterFunction.ofResponseProcessor(response -> {
            System.out.println("HTTP " + response.statusCode().value());
            return Mono.just(response);
        });
```

Cần import `reactor.core.publisher.Mono` và các kiểu `org.springframework.web.reactive.function.client.*`. Hai factory ở trên thích hợp khi chỉ biến đổi một phía mà không cần tự quản lý `next.exchange(...)`. Phải trả lại request/response hợp lệ để chuỗi tiếp tục.

Có thể kết hợp hai filter theo thứ tự với `first.andThen(second)`; khi dùng `WebClient.Builder`, gọi `filter(...)` nhiều lần thường trực quan hơn.

### 3.2 Authentication, token và chính sách header

`ExchangeFilterFunctions.basicAuthentication(username, password)` là filter có sẵn để gửi HTTP Basic Authentication, phù hợp khi API thực sự yêu cầu Basic Auth và bí mật được cung cấp an toàn từ cấu hình ngoài mã nguồn.

Nếu cần Bearer token thay đổi theo request, có thể đặt header trực tiếp trên request hoặc xây filter nhận nguồn token tương ứng. Ví dụ cấu trúc cho token đã có sẵn, không truy vấn token qua mạng:

```java
ExchangeFilterFunction bearerToken(String token) {
    return (request, next) -> {
        ClientRequest authorized = ClientRequest.from(request)
                .headers(headers -> headers.setBearerAuth(token))
                .build();
        return next.exchange(authorized);
    };
}
```

Đoạn này là **phương thức minh họa**, được đặt trong một lớp Java và cần token hợp lệ của đúng API. Không hardcode secret thực trong source, không dùng một token cố định cho tất cả người dùng nếu token đại diện cho danh tính từng người. Khi token cần nạp/làm mới bất đồng bộ, trả chuỗi `Mono` từ cơ chế cấp token; không dùng I/O chặn luồng sự kiện (event loop). Chỉ gửi credential tới host tin cậy đã cấu hình; không tự chuyển tiếp header xác thực sang host khác.

### 3.3 Chặn yêu cầu và xử lý phản hồi

Filter có thể kiểm tra chính sách trước khi gửi, ví dụ chặn yêu cầu thiếu một attribute bắt buộc:

```java
ExchangeFilterFunction requireTenant = (request, next) -> {
    if (request.attribute("tenantId").isEmpty()) {
        return Mono.error(new IllegalArgumentException("Missing tenantId"));
    }
    return next.exchange(request);
};
```

Đây là lỗi cục bộ ở client, **không phải** HTTP response có mã 4xx. Nếu muốn tạo một `ClientResponse` giả lập để chặn đường gửi thì phải xác định rõ trạng thái/body của response và ý nghĩa với mã gọi.

**Đặc biệt chú ý body:** filter nhìn thấy `ClientResponse` nhưng body là nội dung cần được tiêu thụ hoặc giải phóng đúng cách. Filter chỉ quan sát metadata rồi `return Mono.just(response)` thường an toàn vì tầng gọi còn nhận response để đọc body. Trái lại, nếu filter tự đọc/loại bỏ response (ví dụ đổi luồng sau HTTP 401), phải giải phóng nội dung cũ, chẳng hạn thông qua `response.releaseBody()`, trước khi thực hiện yêu cầu khác. Không gọi `response.bodyToMono(String.class)` để “log thử” rồi chuyển nguyên response đã bị tiêu thụ sang bên dưới; dễ gây lỗi đọc body hoặc rò tài nguyên.

`retrieve()` thường chuyển HTTP 4xx/5xx thành lỗi theo chính sách mặc định ở tầng xử lý response; bản thân `next.exchange(...)` có thể trả thành công một `ClientResponse` mang trạng thái 404/500. Vì vậy `doOnError` của filter **không thay thế** `doOnNext(response -> kiểm tra status)` để quan sát các HTTP status. Định nghĩa ánh xạ mã lỗi nghiệp vụ nên đặt gần API cụ thể bằng `retrieve().onStatus(...)` khi phù hợp.

## 4. Cấu hình dùng chung với WebClient.Builder

`WebClient.Builder` gom các cấu hình thường dùng trước khi tạo client:

| API trên builder | Dùng khi nào | Điểm cần nhớ |
| --- | --- | --- |
| `baseUrl(String)` | Nhiều request gọi chung một API host/prefix. | Request dùng URL tuyệt đối có thể chỉ định đích riêng; cần kiểm soát để không làm lộ credential. |
| `defaultHeader(name, values...)` | Header mặc định như `Accept` hay định danh ứng dụng. | Chỉ thêm giá trị mặc định nếu request chưa cung cấp header cùng tên. |
| `defaultHeaders(Consumer<HttpHeaders>)` | Thêm, thay hoặc xóa các default header đã khai báo. | Khác với việc thay đổi headers của một request đang đi qua filter. |
| `defaultCookie(...)`, `defaultCookies(...)` | Cookie mặc định cho các request thích hợp. | Không sử dụng cookie nhạy cảm cho client gọi nhiều miền. |
| `defaultRequest(Consumer<RequestHeadersSpec<?>>)` | Tùy biến cấu trúc request mỗi lần tạo, có thể đặt attribute. | Không xử lý response, không dùng thay filter cần quan sát response. |
| `filter(ExchangeFilterFunction)` | Thêm một filter vào cuối chuỗi. | Thứ tự đăng ký quan trọng. |
| `filters(Consumer<List<ExchangeFilterFunction>>)` | Xem/sắp xếp/xóa danh sách filter. | Dùng có chủ đích, tránh thêm trùng. |
| `clientConnector(...)` | Chọn và cấu hình HTTP transport, timeout/kết nối ở lớp thích hợp. | Không nhầm với timeout nghiệp vụ của luồng. |
| `codecs(...)` | Cấu hình bộ mã hóa/giải mã, giới hạn bộ nhớ. | Không thuộc trách nhiệm của filter. |

Ví dụ khai báo một client dùng chung bằng cấu hình Spring; có thể dùng với Spring Framework/Spring Boot có `spring-webflux`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class RemoteClientConfig {

    @Bean
    WebClient inventoryClient(WebClient.Builder sharedBuilder) {
        ExchangeFilterFunction clientTag = (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> {
                        if (!headers.containsKey("X-Client-Tag")) {
                            headers.set("X-Client-Tag", "inventory");
                        }
                    })
                    .build();
            return next.exchange(updated);
        };

        return sharedBuilder.clone()
                .baseUrl("https://inventory.example")
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .filter(clientTag)
                .build();
    }
}
```

`WebClient.Builder` được inject sẵn trong một ứng dụng Spring Boot đã bật tính năng tương ứng; trong ứng dụng Spring Framework thuần, phải tự khai báo builder bean hoặc tạo qua `WebClient.builder()`. `clone()` cô lập các thay đổi cấu hình trên builder khỏi cấu hình của nơi khác sử dụng cùng builder. Không truyền đối tượng `WebClient.Builder` có thể bị thay đổi giữa nhiều luồng để cấu hình động mỗi request.

Ví dụ mã gọi gọn, tái sử dụng bean đã cấu hình:

```java
Mono<String> stockResponse = inventoryClient.get()
        .uri("/api/stocks/{sku}", "SKU-123")
        .retrieve()
        .bodyToMono(String.class);
```

Đây là một **đoạn minh họa bên trong component/service** có quyền truy cập `inventoryClient`; không phải chương trình Java độc lập. Để chạy thực tế cần API, DTO, cấu hình xác thực và xử lý lỗi phù hợp hệ thống.

### 4.1 Chia sẻ lõi cấu hình, tách client theo API

Tổ chức điển hình:

```text
Cấu hình chung của ứng dụng (log an toàn, quan sát, codec/connector)
                  |
                  v
           WebClient.Builder
              /       \
             v         v
     inventoryClient  paymentClient
     baseUrl A         baseUrl B
     headers A         auth/filter B
```

Không nên dùng một `baseUrl`, credential hoặc filter riêng của API A cho API B. Nếu inject cùng một builder có khả năng thay đổi, dùng `clone()` trước khi cấu hình riêng. Tạo một `WebClient` mỗi lần gọi cũng làm phân tán cấu hình; thông thường tạo các instance dùng chung khi khởi động hoặc tạo bản sao có chủ đích.

### 4.2 WebClient bất biến và mutate()

Sau khi `build()`, `WebClient` không có API để sửa trực tiếp cấu hình đã xây. `mutate()` tạo builder mới mang cấu hình hiện tại; gọi `build()` tạo **client mới**, không đổi client cũ:

```java
WebClient original = WebClient.builder()
        .baseUrl("https://inventory.example")
        .filter(requestOnly)
        .build();

WebClient extended = original.mutate()
        .filter(responseOnly)
        .build();
```

Trong ví dụ này, `original` có `requestOnly`; `extended` có cả `requestOnly` và `responseOnly`. Biến `requestOnly` và `responseOnly` là các filter đã định nghĩa ở phần trước. Khi muốn đưa filter lên đầu hoặc loại bỏ filter cũ, có thể dùng `mutate().filters(list -> ...)`. Cần hiểu thứ tự và nhận diện filter trước khi sửa danh sách; thêm một filter mỗi lần một phương thức gọi `mutate()` có thể gây lặp filter không mong muốn.

## 5. Đưa dữ liệu riêng từng request vào filter bằng attributes

`ClientRequest` có một map attributes dùng **nội bộ cho chuỗi filter**, không được tự động gửi qua mạng như HTTP headers. Một request có thể gắn attribute để đổi hành vi filter:

```java
ExchangeFilterFunction selectiveAudit = (request, next) -> {
    boolean skip = Boolean.TRUE.equals(
            request.attribute("skipAudit").orElse(false));

    if (!skip) {
        System.out.println("Audit " + request.method() + " "
                + request.url().getPath());
    }
    return next.exchange(request);
};

WebClient client = WebClient.builder()
        .filter(selectiveAudit)
        .build();

Mono<String> value = client.get()
        .uri("https://service.example/resource")
        .attribute("skipAudit", true)
        .retrieve()
        .bodyToMono(String.class);
```

Trong ví dụ, `skipAudit` chỉ là cờ của client/filter, không phải header HTTP. Muốn truyền dữ liệu cho server, phải chủ động chuyển thành header/body/query parameter theo hợp đồng API.

Với yêu cầu cần dữ liệu theo từng subscriber trong chuỗi phản ứng, phân biệt attributes với Reactor `Context`: attribute được gắn trên một `ClientRequest`, còn `Context` được truyền theo luồng đăng ký. Tránh phụ thuộc tùy tiện vào `ThreadLocal` trong xử lý reactive vì một luồng có thể chuyển thread. `defaultRequest(...)` có thể đặt attribute mặc định, nhưng chính sách lấy thông tin định danh/correlation cần được thiết kế nhất quán.

## 6. Ví dụ chạy độc lập với mạng: xác minh filter và header

Đoạn dưới đây có phương thức `main` hoàn chỉnh; nó dùng một `ExchangeFunction` giả để tạo response nên **không thực hiện HTTP thật**. Cần Java 17+ và các thư viện Spring WebFlux + Project Reactor trên classpath (ví dụ dự án Spring Boot đã khai báo dependency `org.springframework.boot:spring-boot-starter-webflux` và quản lý phiên bản tương thích).

**Tệp `FilterDemo.java`:**

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class FilterDemo {

    public static void main(String[] args) {
        ExchangeFunction fakeTransport = request -> {
            System.out.println(
                    "transport: " + request.headers().getFirst("X-Client-Id"));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN_VALUE)
                    .body("pong")
                    .build());
        };

        ExchangeFilterFunction audit = (request, next) -> {
            System.out.println(
                    "before: " + request.method() + " " + request.url().getPath());
            return next.exchange(request)
                    .doOnNext(response ->
                            System.out.println(
                                    "after: " + response.statusCode().value()));
        };

        WebClient client = WebClient.builder()
                .baseUrl("https://example.invalid")
                .defaultHeader("X-Client-Id", "learning-module")
                .exchangeFunction(fakeTransport)
                .filter(audit)
                .build();

        String body = client.get()
                .uri("/ping")
                .retrieve()
                .bodyToMono(String.class)
                .block(); // Chỉ dùng tại ranh giới đồng bộ của demo.

        System.out.println("body: " + body);
    }
}
```

**Stdout dự kiến, chính xác theo ví dụ (không tính thông báo môi trường/build tool):**

```text
before: GET /ping
transport: learning-module
after: 200
body: pong
```

Lý do:

1. Lúc `block()` đăng ký luồng, filter `audit` chạy và in dòng `before`.
2. `next.exchange(request)` gọi `fakeTransport`. Transport nhận header mặc định `X-Client-Id` và trả `ClientResponse` 200 với body `pong`.
3. `doOnNext` quan sát response rồi in dòng `after`.
4. `retrieve().bodyToMono(String.class)` giải mã body thành chuỗi, cuối cùng `main` in `body`.

Với dự án Spring Boot/Gradle, thêm `implementation 'org.springframework.boot:spring-boot-starter-webflux'` vào dependencies nếu chưa có; đặt `FilterDemo.java` trong source set và chạy `FilterDemo.main` bằng IDE hoặc Java launcher có classpath thư viện từ Gradle. Lệnh `javac FilterDemo.java` đơn lẻ **không đủ** vì cần các JAR Spring/Reactor. `block()` ở đây là ngoại lệ dành cho `main` kiểm chứng; trong luồng xử lý WebFlux server, nên trả `Mono`/`Flux` thay vì chặn event loop.

### 6.1 Thử thay đổi để tự kiểm tra

- Chuyển `.filter(audit)` thành `.filter(audit).filter(secondFilter)` với `secondFilter` in `B-before` trước `next.exchange` và `B-after` qua `doOnNext`. Quan sát thứ tự `A-before → B-before → transport → B-after → A-after`.
- Thêm `.header("X-Client-Id", "override")` ngay trước `.retrieve()`. Transport sẽ thấy `override` vì header của request ưu tiên hơn `defaultHeader`.
- Bỏ `.block()` và không subscribe; phần trao đổi không được thực hiện.
- Trong một client thực, đặt `attribute("skipAudit", true)` và quan sát filter dùng attribute quyết định có log metadata hay không.

## 7. Những nhầm lẫn và rủi ro phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `ExchangeFilterFunction` với server-side `WebFilter` | Can thiệp sai phía của HTTP. | `ExchangeFilterFunction` dành cho request **đi ra** của `WebClient`; `WebFilter` nằm trong pipeline xử lý server WebFlux. |
| Gọi `next.exchange(request)` hai lần hoặc lồng retry tùy tiện | Có thể gửi cùng yêu cầu nhiều lần, nguy hiểm với POST/PUT không idempotent. | Chủ động định nghĩa retry theo HTTP method, mã lỗi, giới hạn và tính idempotent; không gửi lặp vô điều kiện. |
| `doOnError` được dùng để đếm mọi HTTP 4xx/5xx | Bỏ sót status khi `exchange` trả `ClientResponse` bình thường. | Quan sát `response.statusCode()`; xử lý trạng thái nghiệp vụ ở `retrieve().onStatus(...)` khi hợp lý. |
| Đọc body trong filter rồi trả lại nguyên response | Downstream không còn body như kỳ vọng hoặc rò tài nguyên. | Không tiêu thụ body chỉ để log; nếu xử lý và bỏ response, giải phóng body đúng cách. |
| In toàn bộ headers/body | Lộ token, cookie, PII, nội dung thanh toán. | Chỉ ghi method, mẫu đường dẫn, status, thời gian và ID đã kiểm soát. |
| Dùng `ThreadLocal` để lấy token trong luồng reactive | Mất/sai ngữ cảnh khi đổi thread. | Truyền dữ liệu minh bạch qua request attributes hoặc Reactor Context, tùy bài toán. |
| Dùng `block()` trong filter hay controller phản ứng | Chặn event loop, tăng độ trễ và có thể gây lỗi. | Kết hợp bất đồng bộ bằng `flatMap`, `Mono.defer` hoặc publisher phù hợp. |
| Chỉnh lại builder chia sẻ sau khi dùng | Cấu hình giữa các client không nhất quán. | Hoàn tất cấu hình trước `build()`; `clone()`/`mutate()` khi tạo biến thể. |
| Dùng filter để viết toàn bộ logic nghiệp vụ | Khó kiểm thử và khó phân biệt lỗi từng endpoint. | Filter giải quyết vấn đề chung; xử lý response/DTO/trạng thái nghiệp vụ tại tầng client service. |
| Coi filter là cơ chế timeout/connection pool | Không xử lý đúng lỗi cấu hình transport. | Cấu hình `clientConnector`, timeout, pooling và quản lý vòng đời tài nguyên ở lớp phù hợp. |

## 8. Gợi ý tổ chức trong ứng dụng

Trong ứng dụng có nhiều HTTP client, nên tách phần cấu hình toàn cục (quan sát, connector, policy log an toàn) khỏi client của từng dịch vụ (base URL, xác thực, headers riêng). Định nghĩa filter tái sử dụng thành hàm/bean nếu có giá trị kiểm thử độc lập; có thể bổ sung bộ lọc theo thứ tự bằng `filter(...)` và kiểm soát danh sách bằng `filters(...)`. Đặt tham số cấu hình như endpoint, thời gian chờ, tên ứng dụng trong nguồn cấu hình môi trường phù hợp.

Một cách rà soát thiết kế cho mỗi filter:

1. **Nó sửa request, chỉ quan sát response hay kiểm soát chuỗi trao đổi?** Chọn API đơn giản nhất đủ nhiệm vụ.
2. **Nó có cần dữ liệu riêng từng request không?** Dùng header khi server cần biết, attribute khi chỉ client/filter cần, Reactor Context khi cần ngữ cảnh theo subscriber.
3. **Nó có thể tiêu thụ hoặc bỏ response không?** Nếu có, định nghĩa rõ việc đọc/giải phóng body và chính sách lỗi.
4. **Nó có an toàn khi chạy đồng thời và subscribe nhiều lần không?** Tránh state mutable dùng chung thiếu đồng bộ và tác dụng phụ không idempotent.
5. **Có kiểm thử được mà không gọi HTTP thật không?** Dùng `ExchangeFunction` giả như ví dụ, hoặc mock HTTP server khi muốn thử mã hóa, header thật và kết nối.

## 9. Tổng kết kiến thức

- `WebClient.Builder` giữ cấu hình chung; `ExchangeFilterFunction` can thiệp vào một lần trao đổi HTTP qua `ClientRequest → ExchangeFunction → ClientResponse`.
- Filter được chạy khi publisher được subscribe; thứ tự filter quyết định lớp xử lý request và response.
- `ClientRequest.from(request)` tạo request mới khi sửa header/attribute; `next.exchange(...)` chuyển tiếp trao đổi.
- `defaultHeader` đưa giá trị mặc định, `defaultRequest` tùy biến mỗi request, `filter` xử lý cắt ngang; `WebClient.mutate()` tạo client biến thể mà không sửa bản gốc.
- Khi xử lý response trong filter, luôn bảo toàn hoặc giải phóng body đúng cách; không log thông tin nhạy cảm và không chặn luồng phản ứng.

**Tài liệu tham khảo chính thức (Spring Framework):**

- [WebClient — Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [WebClient — Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [WebClient — Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html)
- [Java API — ExchangeFilterFunction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html)
