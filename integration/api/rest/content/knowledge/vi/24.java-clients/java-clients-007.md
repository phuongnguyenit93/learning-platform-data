# RestClient đồng bộ và các thao tác trao đổi mức thấp

## 1. Khi ứng dụng Java phải gọi một REST API khác

Một dịch vụ **Order Service** cần gọi **Inventory API** để lấy tồn kho trước khi xác nhận đơn. Inventory API trả JSON thông thường, nhưng cũng hỗ trợ **ETag/If-None-Match**, trả **304 Not Modified** khi dữ liệu không đổi và **429 Too Many Requests** khi quá tải. Đôi khi Order Service phải tải một tệp CSV lớn từ Inventory.

Nếu viết client chỉ theo kiểu “GET URL rồi parse JSON”, nhiều tình huống dễ bị hiểu sai: 304 không có body, 404 có thể là dữ liệu không tồn tại theo nghiệp vụ, 429 yêu cầu điều chỉnh nhịp gọi, còn response lớn không thể an toàn nếu đọc toàn bộ vào RAM.

**Spring Framework RestClient** cung cấp API HTTP **đồng bộ, dạng fluent**, xuất hiện từ Spring Framework **6.1** (thường dùng với Spring Boot 3.2 trở lên). Có hai đường xử lý quan trọng:

- **retrieve()**: đường thông thường để lấy Java object hoặc ResponseEntity qua các message converters và cơ chế xử lý HTTP error status.
- **exchange()**: đường mức thấp, cho callback trực tiếp nhận **ClientHttpRequest** và **ClientHttpResponse**, tự quyết cách đọc status, headers, bytes và lỗi.

Bài trong module **INTEGRATION_API_REST** kết nối Java client với hợp đồng resource/URI, phương thức và mã HTTP, conditional requests, idempotency, xác thực, bảo mật, lỗi và kiểm thử. Trọng tâm là **chọn đúng tầng trừu tượng** và biết rõ điều gì xảy ra khi rời bỏ sự tiện lợi của retrieve().

### Sau bài này, bạn có thể

1. Cấu hình RestClient với base URL, request factory, connect/read timeout và header theo từng request.
2. Dùng **retrieve()** để đọc JSON, tạo resource và ánh xạ lỗi khi response đơn giản.
3. Dùng **exchange()** cho **200/304/404/429**, body giới hạn byte, thông tin header và luồng tải xuống.
4. Phân biệt **HTTP error status**, lỗi đọc body, lỗi truyền tải và timeout; không retry tùy tiện.
5. Kiểm thử bằng **MockRestServiceServer** và HTTP mock server thật, gồm auth, ETag, lỗi và streaming.

## 2. RestClient là HTTP client đồng bộ, không phải HTTP server

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant C as RestClient
    participant I as Inventory API
    O->>C: get stock(sku)
    C->>I: GET /stocks/{sku}
    I-->>C: 200 JSON + ETag
    C-->>O: StockView hoặc ResponseEntity
~~~

**Đồng bộ**: thread gọi chờ response, lỗi hoặc timeout. RestClient không tự biến request chặn thành reactive; nếu ứng dụng cần chuỗi tác vụ bất đồng bộ/non-blocking, xem xét **WebClient**. **RestTemplate** vẫn có thể tồn tại trong dự án cũ; **JDK HttpClient** là lựa chọn thuần Java nếu không cần tầng tích hợp Spring.

| Công cụ | Điểm khác biệt |
|---|---|
| **RestClient** | Fluent, đồng bộ, **retrieve()/exchange()**, Spring converters |
| **WebClient** | Reactive, hỗ trợ composition non-blocking |
| **RestTemplate** | API template-style của Spring, phổ biến trong code cũ |
| **java.net.http.HttpClient** | HTTP client JDK, tự thiết kế DTO/serialization integration |

**HTTP status vẫn quyết định kết quả:** 200 có representation; 201 tạo resource (Location theo contract); 202 mới tiếp nhận job; 204 và 304 **không có response body**; 400/422 báo input; 404 có thể là “SKU chưa có”; 409 là conflict nghiệp vụ; 412 báo If-Match không thỏa; 429/503 có thể cần backoff. **200 không có nghĩa “còn hàng”**: số lượng thực tế nằm trong DTO. RestClient ở **phía gọi API**, không phải một Spring MVC controller.

## 3. Khởi tạo RestClient một lần và cấu hình transport rõ ràng

Ví dụ Spring Boot 3.2+ sử dụng **Java 17+**, **JdkClientHttpRequestFactory**, các thời hạn minh họa và một host Inventory đã kiểm soát:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryClientConfig {
    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        HttpClient jdk = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(jdk);
        factory.setReadTimeout(Duration.ofSeconds(5));

        return builder
            .baseUrl("https://inventory.internal.example")
            .requestFactory(factory)
            .defaultHeader("Accept",
                MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}
~~~

**Ý nghĩa cấu hình:** tái sử dụng RestClient thay vì tạo mỗi request; **connect timeout** cho kết nối và **read/request timeout** cho chờ phản hồi, kèm deadline tổng cho workflow. JdkClientHttpRequestFactory hỗ trợ PATCH; lựa chọn request factory cần tính tới TLS/proxy/pooling. **Redirect.NEVER** tránh tự chuyển credential sang location lạ. Trong production, nạp host/timeout từ cấu hình đã validate, không hardcode ví dụ.

**Timeout không bảo đảm server chưa thực hiện request.** Nếu POST đã ghi dữ liệu nhưng response tới trễ, client có thể gặp timeout dù giao dịch thành công. Vì vậy retry phải xem **idempotency và trạng thái nghiệp vụ**, không chỉ ngoại lệ mạng.

### 3.1. Ai nắm token và headers?

Không nên đặt access token cá nhân cố định qua **defaultHeader("Authorization", ...)** trong singleton client. Token nên lấy từ nguồn credential hợp lệ theo request/use case:

~~~java
StockView stock = client.get()
    .uri("/stocks/{sku}", sku)
    .headers(headers -> headers.setBearerAuth(accessToken))
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(StockView.class);
~~~

**accessToken** phải đến từ OAuth2/token provider đáng tin, đúng audience/scope; không tự chuyển token sang host khác hoặc ghi Authorization vào log.

### 3.2. URI template và dữ liệu người dùng

~~~java
client.get()
    .uri(uriBuilder -> uriBuilder
        .path("/stocks/{sku}")
        .queryParam("warehouse", warehouseCode)
        .build(sku))
    .retrieve()
    .body(StockView.class);
~~~

Dùng URI template/builder, validate và encode path/query. Không cho người dùng chọn toàn bộ URL đích của client có bearer token: nguy cơ **SSRF và lộ token**.

## 4. Đường thông thường: retrieve() tự chuyển đổi representation

Nếu Inventory API trả:

~~~http
GET /stocks/SKU-101 HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
ETag: "stock-SKU-101-v12"
Content-Type: application/json

{"sku":"SKU-101","availableQuantity":18}
~~~

Java DTO:

~~~java
record StockView(String sku, long availableQuantity) {}
~~~

Khi chỉ cần body:

~~~java
StockView stock = client.get()
    .uri("/stocks/{sku}", "SKU-101")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(StockView.class);
~~~

Khi cần cả status, ETag hoặc các header:

~~~java
ResponseEntity<StockView> response = client.get()
    .uri("/stocks/{sku}", "SKU-101")
    .retrieve()
    .toEntity(StockView.class);

String etag = response.getHeaders().getETag();
StockView body = response.getBody();
~~~

**HTTP message converters** (thường Jackson với Spring Boot đã cấu hình JSON) chuyển body sang **StockView**. Nếu provider hoặc type không tương thích, client có thể lỗi deserialize; **đó không phải bằng chứng server trả 404 hay 409**. Nếu response có body rỗng, **body()** có thể trả null; ứng dụng cần kiểm tra theo contract thay vì unbox/dereference mù quáng.

### 4.1. POST, Content-Type và Location

~~~java
record CreateReservation(String sku, long quantity) {}
record ReservationView(String id, String status) {}

ResponseEntity<ReservationView> created = client.post()
    .uri("/reservations")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .headers(h -> h.setBearerAuth(accessToken))
    .header("Idempotency-Key", operationKey)
    .body(new CreateReservation("SKU-101", 2))
    .retrieve()
    .toEntity(ReservationView.class);

if (created.getStatusCode().value() != 201 ||
        created.getHeaders().getLocation() == null) {
    throw new UpstreamProtocolException("Expected 201 + Location");
}
~~~

Đây là ví dụ cho API **đã hứa 201 + Location**. Không mọi POST đều tạo resource hoặc trả body. **Idempotency-Key** trong ví dụ là tính năng **theo hợp đồng upstream**, không phải header tự động khiến mọi REST API deduplicate. Nếu response là **202**, phải theo dõi monitor theo contract thay vì xem là reservation đã hoàn tất.

### 4.2. PATCH có điều kiện để tránh lost update

~~~java
ResponseEntity<StockView> updated = client.patch()
    .uri("/stocks/{sku}", "SKU-101")
    .contentType(MediaType.valueOf("application/merge-patch+json"))
    .header("If-Match", strongEtagFromEarlierGet)
    .body(java.util.Map.of("displayName", "Bút mới"))
    .retrieve()
    .toEntity(StockView.class);
~~~

**If-Match** là precondition: **412** nghĩa ETag không còn thỏa; **428** có thể nghĩa server yêu cầu header bị thiếu. Client không được lặng lẽ GET ETag mới rồi áp PATCH cũ nếu chưa có quy tắc merge/ý định người dùng. Với **application/merge-patch+json**, body có ngữ nghĩa Merge Patch (bao gồm field vắng mặt/null) theo hợp đồng; nếu chỉ hỗ trợ thao tác riêng, công bố media type và semantics chính xác.

## 5. retrieve(): status handler và ba loại lỗi cần phân biệt

Với **retrieve()**, phản hồi HTTP **4xx/5xx** mặc định được xử lý như lỗi, thường qua **RestClientResponseException**. Có thể ánh xạ status thành exception domain bằng **onStatus**:

~~~java
StockView loadStock(RestClient client, String sku) {
    return client.get()
        .uri("/stocks/{sku}", sku)
        .retrieve()
        .onStatus(s -> s.value() == 404, (request, response) -> {
            throw new StockNotFoundException(sku);
        })
        .onStatus(HttpStatusCode::is5xxServerError,
            (request, response) -> {
                throw new InventoryUnavailableException(
                    "Inventory API unavailable");
            })
        .body(StockView.class);
}
~~~

Các exception tự định nghĩa cần bổ sung; **HttpStatusCode** là kiểu Spring. Không log toàn bộ error body có thể chứa PII hoặc secret. **400/409/412/429** cần mapping theo use case nếu caller thực sự xử lý chúng.

| Loại vấn đề | Cách hiểu |
|---|---|
| **404/409/412/429/503** | Có **HTTP response** từ upstream; có thể đọc status/header |
| **ResourceAccessException**, timeout/DNS/connection reset | Lỗi **transport**, có thể chưa có response |
| 200 với JSON sai, schema sai hoặc body quá lớn | Lỗi **decode/protocol**, không biến thành 404/409 |

Đừng bắt tất cả **RestClientException** rồi tuyên bố “upstream trả 500”. Dùng **retrieve()** cho **200 JSON**, **201 ResponseEntity**, **204 toBodilessEntity()**. Khi cần **304, 404 như kết quả thông thường, nhiều body types hoặc stream**, chuyển sang **exchange()** và tự xử lý status.

## 6. exchange(): quyền kiểm soát đầy đủ đi cùng trách nhiệm đầy đủ

Theo API Spring, **exchange()** nhận một callback có **request** và **response** mức thấp. Đây là lựa chọn thay cho retrieve(), không phải bước tiếp theo trong chain sau retrieve().

~~~java
String decision = client.get()
    .uri("/stocks/{sku}", "SKU-101")
    .exchange((request, response) -> {
        int status = response.getStatusCode().value();
        if (status == 304) return "NOT_MODIFIED";
        if (status == 200) return "FRESH";
        if (status == 404) return "MISSING";
        throw new UpstreamProtocolException(
            "Unexpected upstream HTTP status: " + status);
    });
~~~

**Ba sự khác biệt quan trọng:**

1. **Không áp dụng các status handlers của retrieve(), kể cả defaultStatusHandler của builder.** Callback phải tự xử lý **4xx, 5xx, redirect, 304, body và header** đúng hợp đồng.
2. Response trả từ **exchange() được Spring đóng sau khi callback kết thúc** (với overload thông thường). Không trả trực tiếp **response.getBody()** hoặc InputStream/response object ra ngoài callback rồi đọc sau.
3. Khi xử lý response entity ở mức thấp, **không mặc định converter tự deserialize thành DTO**: bạn có thể dùng ObjectMapper/decoder riêng, đọc stream có giới hạn, hoặc chọn thao tác phù hợp.

### 6.1. Ví dụ đầy đủ: trả về kết quả GET có điều kiện

Inventory API hỗ trợ **GET /stocks/{sku}** với **If-None-Match**. Thay vì gán 304 thành “null stock”, định nghĩa các kết quả khác nhau:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

sealed interface StockLookup permits FreshStock, UnchangedStock,
                                      MissingStock {}
record FreshStock(StockView stock, String etag)
        implements StockLookup {}
record UnchangedStock(String etag) implements StockLookup {}
record MissingStock() implements StockLookup {}

final class InventoryGateway {
    private static final int MAX_JSON_BYTES = 256 * 1024;
    private final RestClient client;
    private final ObjectMapper mapper;

    InventoryGateway(RestClient client, ObjectMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    StockLookup getStock(String sku, String cachedEtag) {
        return client.get()
            .uri("/stocks/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .headers(h -> {
                if (cachedEtag != null) {
                    h.set(HttpHeaders.IF_NONE_MATCH, cachedEtag);
                }
            })
            .exchange((request, response) -> {
                int status = response.getStatusCode().value();
                String etag = response.getHeaders().getETag();

                if (status == 304) {
                    return new UnchangedStock(etag);
                }
                if (status == 404) {
                    return new MissingStock();
                }
                if (status == 200) {
                    MediaType actual =
                        response.getHeaders().getContentType();
                    if (actual == null ||
                            !MediaType.APPLICATION_JSON
                                .isCompatibleWith(actual)) {
                        throw new UpstreamProtocolException(
                            "Expected application/json");
                    }
                    byte[] bytes = readAtMost(
                        response.getBody(), MAX_JSON_BYTES);
                    StockView stock =
                        mapper.readValue(bytes, StockView.class);
                    return new FreshStock(stock, etag);
                }

                // Không coi 429/503/3xx hoặc body lỗi là StockView.
                throw new UpstreamStatusException(status,
                    response.getHeaders().getFirst(
                        HttpHeaders.RETRY_AFTER));
            });
    }

    private static byte[] readAtMost(InputStream in, int max)
            throws IOException {
        ByteArrayOutputStream out =
            new ByteArrayOutputStream(Math.min(max, 8192));
        byte[] chunk = new byte[8192];
        int total = 0;
        int n;
        while ((n = in.read(chunk)) != -1) {
            if (n > max - total) {
                throw new UpstreamPayloadTooLargeException();
            }
            out.write(chunk, 0, n);
            total += n;
        }
        return out.toByteArray();
    }
}
~~~

**Các exception** ở ví dụ là kiểu ứng dụng tự khai báo. Đoạn code giả định đã có **StockView** ở phần 4 và **ObjectMapper Jackson**. Trong một file Java thật, phải khai báo các record/class ở vị trí và phạm vi visibility phù hợp, thêm dependencies và imports cần thiết. Đây là implementation có chủ đích cho một API nhỏ; validation JSON schema và quy tắc stock có thể cần bổ sung.

**Tại sao readAtMost quan trọng?** **Content-Length** có thể thiếu hoặc không đáng tin; nếu chỉ dựa vào header rồi đọc **readAllBytes()** có thể tạo rủi ro cạn RAM. Với body nhỏ/giới hạn, buffer đến **256 KiB** hợp lý; với file lớn phải **stream xuống storage**. Lỗi parse JSON hoặc dữ liệu quá lớn không nên bị dịch thành 404.

### 6.2. 304 không đồng nghĩa có cached body

Nếu **UnchangedStock** được trả về, tầng gọi chỉ được tái sử dụng một bản cache **còn hợp lệ theo ETag, phạm vi quyền, variant và cache policy**. Không có bản cache mà nhận 304 thì không thể dựng StockView từ response rỗng: cần truy vấn lại không có điều kiện hoặc xử lý như protocol inconsistency theo hợp đồng. **ETag là validator**, không tự là cơ chế phân quyền hoặc định danh người dùng.

### 6.3. 429, 503 và Retry-After

Đối với **429** hoặc **503**, callback có thể giữ **status + Retry-After** trong exception/result có kiểu rõ; không trả “availableQuantity=0” khi upstream tạm quá tải. Retry-After có thể là **delay-seconds hoặc HTTP-date**, phải parse đúng, áp dụng giới hạn tối đa và deadline. Tránh biến mọi response khác 200 thành lỗi chung làm mất nguyên nhân.

## 7. Tải dữ liệu lớn: đọc và đóng response đúng vòng đời

Với **GET /exports/{id}** trả CSV, đừng làm:

~~~java
// Phản mẫu: lấy toàn bộ file lớn vào RAM.
byte[] csv = client.get()
    .uri("/exports/{id}", id)
    .retrieve()
    .body(byte[].class);
~~~

Nếu file có thể lớn, dùng **exchange() để đọc InputStream ngay trong callback** và ghi ra nơi có kiểm soát. Một phiên bản giản lược:

~~~java
long copyWithLimit(InputStream in, OutputStream out, long limit)
        throws IOException {
    byte[] buffer = new byte[16 * 1024];
    long total = 0;
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > limit - total) {
            throw new UpstreamPayloadTooLargeException();
        }
        out.write(buffer, 0, n);
        total += n;
    }
    return total;
}

void downloadExport(RestClient client, String id,
                    OutputStream trustedDestination) {
    client.get()
        .uri("/exports/{id}", id)
        .accept(MediaType.valueOf("text/csv"))
        .exchange((request, response) -> {
            if (response.getStatusCode().value() != 200) {
                throw new UpstreamStatusException(
                    response.getStatusCode().value(), null);
            }
            MediaType type = response.getHeaders().getContentType();
            if (type == null ||
                    !MediaType.valueOf("text/csv").isCompatibleWith(type)) {
                throw new UpstreamProtocolException("Expected text/csv");
            }
            copyWithLimit(response.getBody(), trustedDestination,
                50L * 1024 * 1024);
            return null;
        });
}
~~~

**OutputStream** và các exception là do ứng dụng cung cấp; cần imports Java/Spring thích hợp. Trong production, **đích tải xuống nên là file tạm private**, có quota và cleanup khi lỗi; sau khi tải xong mới xác minh checksum/định dạng và **atomic move** để công bố file hoàn chỉnh. Không ghi đè file theo tên từ **Content-Disposition** của upstream. Nếu callback thất bại sau khi đã ghi một phần, **không để file tạm trở thành dữ liệu thành công**.

**Không trả response InputStream ra ngoài exchange()**: response đã bị đóng sau callback, nên người gọi có thể nhận một stream không còn dùng được. Không đọc XML/CSV/binary từ nguồn không tin cậy rồi thực thi nội dung bằng quyền của service. Với số lượng tải đồng thời lớn, cần giới hạn concurrency, connection pool, deadline và dung lượng lưu.

## 8. Conditional requests, retry và tính an toàn

**GET với If-None-Match** giúp tái xác nhận cache:
 
~~~http
GET /stocks/SKU-101 HTTP/1.1
If-None-Match: "stock-SKU-101-v12"

HTTP/1.1 304 Not Modified
ETag: "stock-SKU-101-v12"
~~~

**304 không mang body**; client chỉ dùng lại StockView khi cache còn hợp lệ theo ETag, quyền/tenant, Vary và Cache-Control. Không có bản cache mà nhận 304 thì phải truy vấn lại không điều kiện hoặc xử lý mismatch. **412** với PATCH là precondition thất bại; không tự thay ETag mới để ghi đè. **409** là xung đột nghiệp vụ, cần quyết định khác.

| Tình huống | Hướng xử lý |
|---|---|
| GET timeout | Có thể retry giới hạn nếu deadline và policy cho phép |
| 429/503, có Retry-After | Parse delay-seconds/HTTP-date, backoff + jitter, có cap |
| POST timeout sau khi gửi | **Không biết đã commit chưa**; chỉ retry an toàn nếu upstream có idempotency contract |
| PATCH stale nhận 412 | GET và giải quyết xung đột trước khi gửi thay đổi mới |
| 400/401/403 do request/quyền | Không lặp vô hạn cùng request |
| Redirect 301/302/307/308 | Chỉ follow host/method/credential theo chính sách tin cậy |

Đặt **retry budget, tổng deadline và concurrency limit**; retry vô hạn khi upstream quá tải gây retry storm. **Retry-After** không thay thế quyết định tác vụ có thực sự retry-safe không.

## 9. Bảo mật, quan sát và ranh giới trust

| Rủi ro | Kiểm soát |
|---|---|
| **SSRF/redirect/token leak** | Chỉ gọi HTTPS host đã duyệt, chặn redirect ngoài allowlist, không tắt xác minh TLS |
| Credential sai audience hoặc bị log | Lấy token từ nguồn đáng tin, scope tối thiểu, không đặt token trong URL/query/log |
| URI/path do người dùng ghép chuỗi | Validate dữ liệu, dùng URI template/builder với encoding |
| Response JSON/CSV lớn hoặc sai Content-Type | Kiểm type, byte cap, parser limits, cleanup khi lỗi |
| Cache/ETag dùng lẫn tenant | Scope theo principal, quyền, variant và cache policy |
| HTTP call đồng bộ treo hàng loạt | Timeout, connection/concurrency limit, deadline và circuit breaker khi phù hợp |
| Log/metrics gây rò PII | Dùng route template/status class/latency/retry count; không gắn token, raw SKU/tenant ID |

**HTTP 200 không chứng minh content đáng tin** hoặc được phép sử dụng cho caller khác. Khi service của bạn cũng cung cấp REST API, hãy ánh xạ lỗi upstream thành **Problem Details an toàn** theo hợp đồng của mình, không trả nguyên raw HTML/SQL/stack trace từ upstream. Chỉ chuyển tiếp status khi thật sự cùng ngữ nghĩa, ví dụ upstream 404 SKU có thể trở thành domain conflict khi đặt chỗ.

## 10. Kiểm thử RestClient qua MockRestServiceServer và HTTP thật

**MockRestServiceServer** tích hợp với Spring RestClient để bắt request và tạo response giả mà không cần mở cổng mạng. Gắn mock server **vào builder trước khi build() client**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryGatewayTest {
    @Test
    void returnsFreshStockFor200() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryGateway gateway = new InventoryGateway(
            builder.build(), new ObjectMapper());

        server.expect(requestTo(
                "https://inventory.example.test/stocks/SKU-101"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                "{\"sku\":\"SKU-101\",\"availableQuantity\":18}",
                MediaType.APPLICATION_JSON));

        StockLookup result = gateway.getStock("SKU-101", null);
        assertInstanceOf(FreshStock.class, result);
        assertEquals(18L,
            ((FreshStock) result).stock().availableQuantity());
        server.verify();
    }

    @Test
    void preservesNotModifiedWithoutParsingBody() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://inventory.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        InventoryGateway gateway = new InventoryGateway(
            builder.build(), new ObjectMapper());

        server.expect(requestTo(
                "https://inventory.example.test/stocks/SKU-101"))
            .andExpect(header("If-None-Match",
                "\"stock-SKU-101-v12\""))
            .andRespond(withStatus(HttpStatus.NOT_MODIFIED));

        StockLookup result = gateway.getStock(
            "SKU-101", "\"stock-SKU-101-v12\"");
        assertInstanceOf(UnchangedStock.class, result);
        server.verify();
    }
}
~~~

**Các kiểu InventoryGateway, StockLookup, FreshStock, UnchangedStock** nằm ở phần 6. Unit test còn phải bao phủ **404 → MissingStock**, **503/429 → UpstreamStatusException**, 200 JSON hỏng, sai Content-Type và body vượt 256 KiB.

### 10.1. Chứng minh exchange() bỏ qua status handlers

Một phép thử có giá trị: cấu hình builder **defaultStatusHandler** để ném một marker exception nếu response 5xx. Gọi cùng upstream stub 503:

- Qua **retrieve()**, handler tùy biến phải được áp dụng.
- Qua **exchange()**, callback **không** chạy handler đó; test phải nhận **UpstreamStatusException** do callback tự ném.

Test này giúp ngăn refactor “retrieve → exchange để lấy ETag” nhưng quên giữ logic xử lý lỗi. Tương tự, test **204/304** phải bảo đảm không cố deserialize JSON từ body trống.

### 10.2. Test transport với mock web server

MockRestServiceServer **không mô phỏng đầy đủ TCP/TLS, redirect, streaming timing và network failures**. Với **WireMock, OkHttp MockWebServer hoặc HTTP test server** chạy thật, hãy dùng cùng request factory/timeouts như production để kiểm:

| Tình huống | Kỳ vọng |
|---|---|
| Connection refused / read timeout | Lỗi transport được phân biệt với HTTP status |
| Trả 429/503 có Retry-After | Backoff theo contract, không retry storm |
| Response 200 có Content-Length sai hoặc streaming lớn | Byte limit vẫn hiệu lực; dữ liệu không lưu công khai khi thất bại |
| Redirect sang host ngoài allowlist | Không chuyển token/không tự follow |
| 200 với media type hoặc JSON sai | Protocol/decoding error, không trả stock giả |
| POST timeout sau khi upstream commit | Retry chỉ theo Idempotency-Key; không tạo reservation trùng |

Với test chạy qua proxy/API gateway, cần kiểm **TLS, base path, Authorization redaction, tracing headers và hành vi 304/429** sau toàn bộ tuyến. Mock chỉ xác minh logic local; integration test kiểm sự khác biệt giữa HTTP client thực và runtime.

## 11. Bài thực hành: client đặt chỗ có cache và giới hạn lỗi

Xây một **ReservationGateway** đồng bộ cho API:

~~~text
GET  /stocks/{sku}       -> 200 JSON + ETag | 304 | 404
POST /reservations       -> 201 + Location | 409 | 429 | 503
GET  /exports/{id}       -> 200 text/csv, tối đa 50 MiB
~~~

**Yêu cầu:** (1) cấu hình RestClient với HTTPS host, connect/read timeout và không follow redirect tùy tiện; (2) dùng **retrieve()** cho POST có JSON, thêm **Idempotency-Key** từ operation ID hợp lệ; (3) dùng **exchange()** cho GET stock để xử lý 304/404 mà không deserialize body trống; (4) stream CSV vào file tạm, giới hạn byte thực và dọn khi lỗi; (5) viết test **304 + ETag**, **429 Retry-After**, **timeout sau POST**, **trả sai Content-Type**, **response quá giới hạn**.

**Gợi ý:** Có thể dùng các result type **Fresh/Unchanged/Missing** cho stock. Chỉ dùng cache khi đúng principal/variant. **201** cần Location theo contract; **409** yêu cầu xử lý nghiệp vụ, **429/503** áp dụng backoff có giới hạn, timeout sau POST không tự chứng minh reservation chưa tạo. Khi export thành công, mới atomic move tệp tạm sang tệp đích. Test cả status/headers lẫn dữ liệu cuối, không chỉ DTO.

## 12. Checklist trước khi đưa client vào production

- [ ] RestClient được cấu hình tái sử dụng; có **base URL, TLS, timeouts, redirect policy** và giới hạn concurrency phù hợp.
- [ ] Dùng **retrieve()** khi status/body đơn giản; dùng **exchange()** khi cần status/header/stream mức thấp và **tự xử lý mọi status**.
- [ ] **Không trả InputStream từ exchange()** ra ngoài callback; stream được xử lý/đóng trong vòng đời response.
- [ ] Không tin Content-Length là giới hạn duy nhất; có byte cap, parser validation và cleanup partial download.
- [ ] Phân biệt **HTTP 4xx/5xx, lỗi network/timeout và lỗi decode**, không che thành một status chung.
- [ ] Conditional GET **304** dùng cache đúng scope; **412** không tự retry với ETag mới.
- [ ] POST retry có **idempotency contract**; 429/503 retry theo Retry-After, backoff, jitter, deadline.
- [ ] Credentials không lọt sang host redirect, URL/query/log; có auth scope và kiểm SSRF.
- [ ] Có test **MockRestServiceServer** cho mapping, **mock HTTP server** cho transport, và contract tests với API thật.
- [ ] Monitoring đo lỗi theo route/status class, retry budget, timeout và latency mà không lộ PII.

Tài liệu tham khảo: [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html); [Spring — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html); [Spring 6.1 — JdkClientHttpRequestFactory API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html); [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [OpenAPI Specification](https://spec.openapis.org/oas/latest.html).

**Ghi nhớ:** **RestClient** giúp Java gọi REST đồng bộ với fluent API. **retrieve()** tối ưu cho chuyển body thông thường; **exchange()** cho quyền kiểm soát status, header và byte ở mức thấp, nhưng yêu cầu tự xử lý lỗi, giới hạn dữ liệu và vòng đời response. Một HTTP client đáng tin phải tuân thủ ngữ nghĩa API **và** được kiểm thử qua cả mock lẫn transport thật.
