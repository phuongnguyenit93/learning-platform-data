# Ánh xạ kiểu phản hồi, mã trạng thái và ngoại lệ

**RestClient** là HTTP client đồng bộ có API fluent của Spring Framework. Khi dùng RestClient trong hệ thống Spring Cloud LoadBalancer, một lời gọi từ **Order Service** đến **inventory-service** thường trải qua hai chặng: trước tiên LoadBalancer chọn một **ServiceInstance** theo service ID, sau đó HTTP client gửi request đến instance thực tế và xử lý response. Chặng thứ hai bao gồm ba quyết định quan trọng: **đọc body thành kiểu Java nào**, **diễn giải HTTP status ra sao** và **biến tình huống lỗi thành ngoại lệ nào**.

Ví dụ cùng một endpoint GET /api/stock/BOOK-01 có thể trả:

| Phản hồi | Ý nghĩa | Cách caller nên diễn giải |
| --- | --- | --- |
| 200 + JSON hợp lệ | Lấy tồn kho thành công | Deserialize thành StockResponse |
| 204, không có body | Không có nội dung trả về | Không ép thành DTO bắt buộc |
| 404 + error body | SKU không tồn tại | Có thể đổi thành lỗi nghiệp vụ StockNotFound |
| 409 + error body | Xung đột trạng thái | Không mặc định retry |
| 429 + Retry-After | Downstream giới hạn tốc độ | Áp dụng retry/backoff có kiểm soát |
| 503 + error body | Downstream hoặc tầng LB không phục vụ | Phân biệt có HTTP response hay lỗi chọn instance |
| Timeout hoặc lỗi kết nối | Không nhận response HTTP hợp lệ | Xử lý transport exception riêng |
| 200 + JSON sai schema | Có response nhưng không decode được | Xử lý lỗi contract/message conversion |

Mục tiêu của bài là xây dựng một **hợp đồng lỗi rõ ràng giữa lớp HTTP và lớp nghiệp vụ**, tránh hiểu sai rằng mọi response đều trả DTO hoặc mọi lỗi đều là HTTP 500.

**Phạm vi phiên bản:** Các ví dụ ưu tiên API chung từ Spring Framework 6.1 trở lên, nơi RestClient được giới thiệu. Một số API mới hơn, chẳng hạn requiredBody() từ các bản Spring Framework 7.0.x, được nêu riêng để không gây nhầm lẫn khi dự án đang chạy Spring 6.x. Hãy dùng BOM Spring Boot–Spring Cloud tương thích với hệ thống thực tế.

## 1. Ba tầng cần phân biệt trước khi xử lý response

~~~mermaid
flowchart TD
    A["Client gọi http://inventory-service/..."] --> B["LoadBalancer tìm ServiceInstance"]
    B --> C{"Chọn được instance?"}
    C -->|Không| D["Lỗi chọn đích / không có instance"]
    C -->|Có| E["Kết nối HTTP đến host:port thật"]
    E --> F{"Nhận HTTP response?"}
    F -->|Không| G["Lỗi mạng, DNS, TLS, timeout"]
    F -->|Có| H{"HTTP status"}
    H -->|"2xx / status được chấp nhận"| I["Chuyển đổi body sang DTO"]
    I --> J{"Decode thành công?"}
    J -->|Có| K["Kết quả typed cho nghiệp vụ"]
    J -->|Không| L["Lỗi message conversion / contract"]
    H -->|"4xx / 5xx"| M["Status handler hoặc mặc định ném exception"]
~~~

Khi điều tra lỗi, cần tách:

1. **Không tìm thấy instance:** danh sách discovery rỗng hoặc filter loại hết ứng viên; bước gửi HTTP có thể chưa diễn ra.
2. **Transport failure:** đã có URI đích nhưng không thiết lập kết nối, TLS handshake lỗi, connection reset hoặc timeout; thông thường chưa có HTTP status đáng tin cậy.
3. **HTTP error response:** server hoặc gateway thật sự trả 4xx/5xx; có status, headers và có thể có error body.
4. **Decode failure:** HTTP response có thể là 200, nhưng body không phù hợp với kiểu Java, JSON sai hoặc Content-Type không được hỗ trợ.

RestClient chỉ xử lý HTTP client; Spring Cloud LoadBalancer phụ trách discovery và chọn ServiceInstance. Việc ánh xạ ngoại lệ ở adapter của Order Service nên giữ được sự phân biệt này để retry, observability và cảnh báo vận hành không sai.

## 2. Tạo RestClient đúng cách trong ứng dụng có LoadBalancer

Với URL có host là service ID, cần một RestClient.Builder được tích hợp Spring Cloud LoadBalancer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Trong client nghiệp vụ:

~~~java
@Service
class InventoryHttpClient {

    private final RestClient client;

    InventoryHttpClient(@LoadBalanced RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Để code hoạt động, ứng dụng cần **spring-cloud-starter-loadbalancer** và nguồn instance, ví dụ Eureka, Consul hoặc SimpleDiscoveryClient. Spring Cloud tích hợp **BlockingLoadBalancerClient** để đổi service ID thành host/port thực trước khi gửi HTTP request.

**Không nhầm lỗi discovery với lỗi response mapping.** Nếu không có instance của inventory-service, RestClient không thể deserialize một HTTP error body từ server vì không có server nào được gọi. Tùy adapter và release train, lỗi có thể được thể hiện bằng exception hoặc một HTTP error response do tầng load balancing tạo; cần kiểm tra trace và nơi phát sinh thay vì cố định mọi trường hợp thành một exception type.

Nếu client gọi endpoint đối tác có URL cố định, thông thường nên dùng RestClient không gắn LoadBalancer. Có thể tạo các bean/builder riêng để tránh đưa host thật như api.partner.example vào cơ chế tìm service ID.

## 3. Từ JSON sang DTO: body(Class<T>)

RestClient cung cấp cách đọc body trực tiếp:

~~~java
record StockResponse(
        String sku,
        int available,
        String warehouse) {
}

StockResponse result = client.get()
        .uri("/api/stock/{sku}", "BOOK-01")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(StockResponse.class);
~~~

Với response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"BOOK-01","available":7,"warehouse":"HCM"}
~~~

Spring chọn **HttpMessageConverter** phù hợp với Content-Type và kiểu đích. Khi Jackson được cấu hình, JSON có thể được chuyển thành record StockResponse.

Cần hiểu bốn điều:

- body(StockResponse.class) trả **StockResponse hoặc null** nếu không có body.
- Đối tượng Java **không bao gồm status, headers**; muốn kiểm tra chúng, dùng toEntity().
- Nếu response có HTTP status lỗi 4xx/5xx, mặc định status handler ném exception **trước khi** bạn nhận được DTO.
- Nếu HTTP status được chấp nhận nhưng body không deserialize được, đây là lỗi **mapping/contract**, không phải tự động lỗi 404 hoặc 503.

### 3.1. Không suy diễn rằng 200 luôn có body hợp lệ

API có thể trả 200 với body rỗng, JSON null, hoặc JSON thiếu trường quan trọng. Không nên gán null về một DTO nghiệp vụ hợp lệ hoặc tiếp tục xử lý mà không kiểm tra.

~~~java
StockResponse response = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);

if (response == null) {
    throw new InvalidInventoryResponseException(
            "Inventory returned no body");
}
~~~

InvalidInventoryResponseException ở đây là **exception domain do ứng dụng tự tạo**, không phải class có sẵn của Spring. Tùy yêu cầu, nên kiểm tra thêm giá trị sku, available, warehouse và các invariant sau deserialize; Jackson không tự bảo đảm mọi quy tắc nghiệp vụ.

### 3.2. requiredBody() chỉ có ở các phiên bản mới

Trong Spring Framework 7.0.4 trở lên, **ResponseSpec.requiredBody(...)** yêu cầu kết quả không null và ném IllegalStateException nếu không có body. Với Spring Framework 6.1/6.2 hoặc các bản 7.0 trước đó, không được sử dụng API này nếu chưa xác minh tính sẵn có; thay bằng kiểm tra null minh bạch như ví dụ trên.

## 4. Ánh xạ JSON generic: ParameterizedTypeReference

Class<T> không biểu diễn đầy đủ các kiểu generic như List<StockResponse> hoặc PageResponse<StockResponse> do Java type erasure. Khi API trả danh sách hoặc wrapper generic, dùng **ParameterizedTypeReference<T>**:

~~~java
List<StockResponse> stocks = client.get()
        .uri("/api/stocks?warehouse={warehouse}", "HCM")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(new ParameterizedTypeReference<List<StockResponse>>() {});
~~~

Response minh họa:

~~~json
[
  {"sku":"BOOK-01","available":7,"warehouse":"HCM"},
  {"sku":"BOOK-02","available":4,"warehouse":"HCM"}
]
~~~

Đối với một wrapper:

~~~java
record PageResponse<T>(
        List<T> content,
        int page,
        int totalPages) {
}

PageResponse<StockResponse> page = client.get()
        .uri("/api/stocks?page={page}", 0)
        .retrieve()
        .body(new ParameterizedTypeReference<PageResponse<StockResponse>>() {});
~~~

Đừng dùng body(List.class) rồi ép kiểu List<StockResponse>; các phần tử có thể trở thành map thay vì DTO, dẫn đến ClassCastException hoặc lỗi âm thầm ở tầng nghiệp vụ.

**Lưu ý:** ParameterizedTypeReference giúp giữ thông tin kiểu đích cho converter. Nó không sửa JSON sai schema, không biến 404 thành danh sách rỗng và không bảo đảm biến thể JSON bất kỳ luôn deserialize thành công.

## 5. Khi cần status và header: toEntity()

Khi service trả thêm ETag, Location, Retry-After hoặc mã HTTP cần được tầng adapter kiểm tra, dùng **ResponseEntity<T>**:

~~~java
ResponseEntity<StockResponse> entity = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .toEntity(StockResponse.class);

HttpStatusCode status = entity.getStatusCode();
HttpHeaders headers = entity.getHeaders();
StockResponse stock = entity.getBody();
~~~

Ưu điểm của toEntity():

- Trả được **status** và **headers**, kể cả response hợp lệ mà không có body.
- Deserialize body sang kiểu khai báo khi có nội dung.
- Giữ dữ liệu cho các trường hợp 201 Created có Location hoặc 200 có ETag.
- Cũng có overload nhận ParameterizedTypeReference<T> cho kiểu generic.

**Điều dễ nhầm:** toEntity(...) **không mặc định trả ResponseEntity cho 404 hoặc 500**. Khi đi qua retrieve(), các status lỗi vẫn bị xử lý bởi onStatus/default status handler và thường ném RestClientResponseException. Nếu nghiệp vụ cần xử lý 404 như một nhánh bình thường, phải định nghĩa policy rõ ràng.

### 5.1. Chỉ cần status và header: toBodilessEntity()

~~~java
ResponseEntity<Void> entity = client.post()
        .uri("/api/reservations")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ReserveRequest(sku, quantity))
        .retrieve()
        .toBodilessEntity();

HttpStatusCode status = entity.getStatusCode();
URI location = entity.getHeaders().getLocation();
~~~

Đây là lựa chọn phù hợp nếu API trả **201 Created** kèm Location nhưng không có payload hữu ích, hoặc trả **204 No Content**.

Không cố parse DTO từ response 204 chỉ để biết request thành công; status code đã là kết quả quan trọng cần ghi nhận.

## 6. Đọc HTTP status theo ngữ nghĩa thay vì chỉ so sánh 200

| Status | Trường hợp phổ biến | Mapping gợi ý |
| --- | --- | --- |
| 200 OK | Trả dữ liệu đã lấy | body(DTO) hoặc toEntity(DTO) |
| 201 Created | Tạo tài nguyên mới | toEntity()/toBodilessEntity(), lấy Location nếu cần |
| 202 Accepted | Đã nhận xử lý bất đồng bộ | Chưa coi là đã hoàn thành nghiệp vụ; dùng operation ID để kiểm tra sau |
| 204 No Content | Thao tác thành công, body rỗng | toBodilessEntity() hoặc kết quả domain dạng void |
| 206 Partial Content | Phản hồi theo Range | Cần contract tải từng phần, Content-Range |
| 304 Not Modified | Điều kiện cache cho biết nội dung chưa đổi | Không kỳ vọng JSON DTO; xử lý có điều kiện/cache |
| 400 Bad Request | Request không hợp lệ | Lỗi validation/contract, thường không retry |
| 401 Unauthorized | Thiếu hoặc sai xác thực | Kiểm tra token, auth flow |
| 403 Forbidden | Không có quyền | Lỗi phân quyền, không retry mù |
| 404 Not Found | Không tồn tại hoặc endpoint không đúng | Mapping tùy domain; phân biệt resource thiếu và route sai |
| 409 Conflict | Xung đột phiên bản/trạng thái | Domain conflict; cần giải quyết điều kiện trước khi thử lại |
| 412 Precondition Failed | ETag/If-Match không còn hợp lệ | Refresh state rồi quyết định tiếp |
| 422 Unprocessable Content | Dữ liệu hợp cú pháp nhưng sai ngữ nghĩa | Lỗi nghiệp vụ đầu vào |
| 429 Too Many Requests | Rate limiting | Xem Retry-After, backoff, deadline |
| 500 Internal Server Error | Lỗi phía server | Báo lỗi downstream; chỉ retry nếu policy an toàn |
| 502 Bad Gateway | Proxy/gateway upstream lỗi | Quan sát hạ tầng, retry có giới hạn |
| 503 Service Unavailable | Downstream không sẵn sàng | Phân biệt backend 503 và LB không có instance |
| 504 Gateway Timeout | Gateway timeout khi gọi upstream | Thực thi có thể đã xảy ra; tránh retry thiếu idempotency |

Không coi mọi **2xx** là cùng kết quả nghiệp vụ. Ví dụ, **202** là nhận xử lý, chưa phải hoàn tất; **204** không có body; **206** đòi hỏi logic ghép dữ liệu nếu đang tải theo range.

Các status **3xx** phụ thuộc cấu hình redirect của HTTP request factory. Khi response 304 được trả tới RestClient, không giả định converter sẽ tự truy xuất cache hay tạo DTO từ body không có. Các request được gửi qua LoadBalancer cũng không tự tái dựng mọi Location header hoặc quyết định có theo redirect sang host khác hay không.

### 6.1. Không đồng nhất HTTP status với domain status

Một API có thể trả 200 với payload:

~~~json
{"sku":"BOOK-01","status":"OUT_OF_STOCK"}
~~~

Đây là **HTTP thành công** nhưng **nghiệp vụ có trạng thái hết hàng**. Không nên biến nó thành 503 để kích hoạt retry hạ tầng. Domain status cần được kiểm tra sau deserialize và xử lý theo contract.

Tương tự, response 409 vì optimistic locking không giống 503 do instance mất kết nối; áp dụng cùng retry policy cho hai trường hợp này là sai.

## 7. Ngoại lệ mặc định của retrieve()

Theo Spring Framework, retrieve() mặc định xem **4xx và 5xx** là lỗi HTTP. Các exception phổ biến nằm trong cây phân cấp:

~~~text
RestClientException
├── RestClientResponseException
│   ├── HttpStatusCodeException
│   │   ├── HttpClientErrorException  (4xx)
│   │   └── HttpServerErrorException  (5xx)
│   └── các response exception khác tùy API/phiên bản
├── ResourceAccessException          (I/O, timeout, TLS ...)
└── các ngoại lệ khác về message conversion hoặc request
~~~

Đây là **sơ đồ khái niệm các nhánh quan trọng**, không phải sơ đồ đầy đủ mọi subclass của mọi phiên bản. Khi sử dụng API trong release cụ thể, đối chiếu Javadoc nếu cần catch một subclass chính xác.

Ví dụ mặc định:

~~~java
try {
    StockResponse stock = client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);

    return stock;
} catch (HttpClientErrorException.NotFound ex) {
    // HTTP 404 thật từ server/adapter.
    throw new StockNotFoundException(sku, ex);
} catch (HttpServerErrorException ex) {
    throw new InventoryUnavailableException("Inventory returned 5xx", ex);
} catch (ResourceAccessException ex) {
    throw new InventoryTransportException("Cannot reach inventory", ex);
}
~~~

Trong ví dụ, ba exception **StockNotFoundException**, **InventoryUnavailableException** và **InventoryTransportException** là lớp domain do ứng dụng tự định nghĩa. Nên giữ nguyên **cause** để không mất stack trace gốc, nhưng không trả toàn bộ exception/cause cho người dùng cuối.

### 7.1. Lấy thông tin từ RestClientResponseException

~~~java
catch (RestClientResponseException ex) {
    int code = ex.getStatusCode().value();
    HttpHeaders headers = ex.getResponseHeaders();
    String rawBody = ex.getResponseBodyAsString();

    log.warn("Inventory HTTP failure: status={}, bytes={}",
            code, rawBody.length());

    throw new DownstreamHttpException(code, ex);
}
~~~

RestClientResponseException có thể cung cấp status, headers và response body. Tuy nhiên, không tự động log nguyên body: error payload có thể chứa token, thông tin khách hàng hoặc dữ liệu nhạy cảm. Nếu muốn log, nên giới hạn kích thước và redact thông tin trước.

Khi API có JSON lỗi ổn định, có thể dùng **getResponseBodyAs(ErrorDto.class)** ở phiên bản hỗ trợ decode error body hoặc tự decode với ObjectMapper đã cấu hình, nhưng phải xử lý trường hợp body rỗng/không phải JSON. **Không coi mọi exception HTTP đều mang error DTO đúng schema.**

## 8. onStatus(): ánh xạ 404/409/429/5xx theo nghiệp vụ

**onStatus(Predicate<HttpStatusCode>, ErrorHandler)** gắn một quy tắc xử lý cho response của lời gọi retrieve hiện tại. Đây là cách rõ ràng để biến status HTTP thành exception domain.

~~~java
StockResponse stock = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                (request, response) -> {
                    throw new StockNotFoundException(sku);
                })
        .onStatus(
                status -> status.value() == 409,
                (request, response) -> {
                    throw new StockConflictException(sku);
                })
        .onStatus(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new InventoryUnavailableException(
                            "Inventory status " + response.getStatusCode());
                })
        .body(StockResponse.class);
~~~

Ở đây exception custom đều là **unchecked exception** do ứng dụng tạo. Quy tắc chạy sau khi client nhận HTTP response; nó không bắt được trực tiếp lỗi network trước khi có response.

Các điều cần nhớ:

- Predicate có thể khớp **một status cụ thể** hoặc cả nhóm, ví dụ HttpStatusCode::is5xxServerError.
- Mỗi handler có thể ném exception domain, hoặc có thể không ném nếu thật sự muốn bỏ qua một lỗi HTTP cụ thể.
- Khi **không có handler phù hợp**, quy tắc lỗi mặc định của retrieve vẫn áp dụng cho 4xx/5xx.
- Thứ tự và phạm vi handler cần được thiết kế tránh chồng lấp mơ hồ, chẳng hạn handler mọi 4xx đặt trước handler riêng 404.
- Handler có quyền đọc response body nếu cần, nhưng nếu đã tiêu thụ stream thì cần có chính sách rõ ràng về việc chuyển đổi tiếp; thông thường nên **ném ngoại lệ sau khi đọc error body**.

### 8.1. Mapping 404 thành Optional.empty(): nên làm ở adapter

Không phải mọi 404 đều có nghĩa giống nhau:

- GET /stock/{sku}: 404 có thể là **SKU chưa tồn tại**, hợp đồng domain chấp nhận kết quả rỗng.
- GET /api/stocks: 404 có thể là **sai route hoặc phiên bản API**, cần báo lỗi.
- 404 từ một reverse proxy có thể báo **không tìm thấy backend**, không phải tài nguyên nghiệp vụ.

Khi contract xác nhận 404 tương đương không tìm thấy resource, cách dễ bảo trì là giữ default HTTP behavior rồi đổi exception ở adapter:

~~~java
Optional<StockResponse> findStock(String sku) {
    try {
        return Optional.ofNullable(client.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class));
    } catch (HttpClientErrorException.NotFound ex) {
        return Optional.empty();
    }
}
~~~

Ưu điểm: mọi response 404 vẫn được phân loại đúng ở tầng HTTP, còn **quyết định rằng 404 tương đương Optional.empty()** chỉ nằm ở API nghiệp vụ phù hợp. Không cần cấu hình một handler nuốt 404 trên toàn client rồi làm mất tín hiệu lỗi của endpoint khác.

Nếu caller thật sự muốn suppress 404 bằng onStatus để trả DTO/null, cần kiểm thử rõ liệu body của response 404 còn được converter đọc và decode hay không. Không nên coi handler không ném exception là phép tự động biến 404 thành 204.

### 8.2. Dùng onStatus để xử lý lỗi có header quan trọng

Ví dụ status 429 có Retry-After:

~~~java
.onStatus(
        status -> status.value() == 429,
        (request, response) -> {
            String retryAfter = response.getHeaders()
                    .getFirst(HttpHeaders.RETRY_AFTER);
            throw new InventoryRateLimitedException(retryAfter);
        })
~~~

Header Retry-After có thể là **số giây** hoặc **HTTP-date**. Không chuyển thẳng chuỗi thành số nguyên mà không xét hai định dạng, giới hạn chờ tối đa và tổng deadline. Việc ném exception ở đây **không tự lập lịch retry**.

## 9. Cấu hình status handler dùng chung bằng RestClient.Builder

Nếu một nhóm API sử dụng cùng hợp đồng lỗi, có thể cấu hình defaultStatusHandler trên builder:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder()
            .defaultStatusHandler(
                    HttpStatusCode::is5xxServerError,
                    (request, response) -> {
                        throw new DownstreamUnavailableException(
                                response.getStatusCode().value());
                    });
}
~~~

Khi có nhiều downstream, không nên dùng một handler global quá chuyên biệt, ví dụ luôn chuyển mọi 404 thành StockNotFoundException: 404 của payment-service và inventory-service có thể mang ý nghĩa khác nhau.

Một cách tổ chức tốt:

- **Global default handler:** chỉ xử lý lỗi chung như lỗi hạ tầng hoặc quy tắc an toàn toàn ứng dụng.
- **Per-client builder:** ánh xạ lỗi theo contract của từng downstream.
- **Per-request onStatus:** ánh xạ riêng cho endpoint.
- **Service adapter:** biến HTTP exception thành kết quả domain ổn định cho nghiệp vụ.

Theo hợp đồng API, handler trên từng request được xem xét trước các default handlers; các default handler áp dụng khi không có handler ở mức request phù hợp. Các handler có thể được kết hợp theo thứ tự đăng ký, nên tránh các predicate quá rộng vô tình nuốt trường hợp đặc biệt.

**Không thêm một defaultStatusHandler ném lỗi cho mọi status**: 200/201/204 cần được trả bình thường. Hãy chọn predicate thật sự đại diện cho lỗi cần xử lý.

## 10. exchange(): linh hoạt hơn, nhưng tự chịu trách nhiệm status

RestClient có phương thức **exchange(...)** cho phép ứng dụng truy cập raw request/response trong một callback.

~~~java
int resultStatus = client.get()
        .uri("/api/stock/{sku}", sku)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            if (status >= 400) {
                throw new InventoryUnavailableException(
                        "Inventory returned " + status);
            }
            return status;
        });
~~~

**Cảnh báo quan trọng:** khi dùng exchange(), **các status handler được cấu hình qua retrieve().onStatus() hoặc defaultStatusHandler không được áp dụng**. Callback exchange tự kiểm tra status và quyết định có ném ngoại lệ, đọc body hay giữ stream.

Khi thực sự cần đọc body từ exchange, cần xử lý các vấn đề:

1. Đọc stream trong phạm vi callback khi response vẫn còn mở.
2. Kiểm tra status trước khi deserialize theo contract.
3. Xác nhận Content-Type và charset.
4. Đảm bảo không đọc body stream hai lần.
5. Không giữ ClientHttpResponse hoặc InputStream để dùng sau khi callback kết thúc mà không quản lý vòng đời.

Ví dụ đọc raw error body với giới hạn:

~~~java
String responseText = client.get()
        .uri("/api/stock/{sku}", sku)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            byte[] bytes = response.getBody().readNBytes(4096);
            String text = new String(bytes, StandardCharsets.UTF_8);

            if (status >= 400) {
                throw new DownstreamHttpException(status);
            }
            return text;
        });
~~~

Đây là ví dụ minh họa đọc **tối đa 4 KiB** chứ không tự động decode JSON, và giả định body UTF-8. Trong ứng dụng thật, đọc charset từ Content-Type, giới hạn kích thước body, kiểm tra response status và tránh ghi raw dữ liệu nhạy cảm. Nếu cần mapping DTO thông thường, **retrieve().body()/toEntity() dễ dùng và ít lỗi hơn exchange()**.

## 11. Phân biệt lỗi HTTP với lỗi kết nối, timeout, TLS và decode

| Nhóm lỗi | Ví dụ | Exception/tín hiệu thường gặp | Có HTTP status đáng tin cậy? |
| --- | --- | --- | --- |
| HTTP 4xx | 404, 409, 429 | HttpClientErrorException hoặc RestClientResponseException | Có |
| HTTP 5xx | 500, 503, 504 | HttpServerErrorException hoặc RestClientResponseException | Có |
| Timeout kết nối/đọc | SocketTimeoutException | ResourceAccessException bọc IOException | Thường không |
| DNS/connection refused | UnknownHostException, ConnectException | ResourceAccessException hoặc lỗi request tương ứng | Thường không |
| TLS | SSLHandshakeException | ResourceAccessException với cause SSLException | Thường không |
| JSON sai | Trường JSON không đúng kiểu | RestClientException/message conversion exception | Có thể HTTP 200 |
| Content-Type sai | Không có converter phù hợp | UnknownContentTypeException hoặc RestClientException | Có thể HTTP 200 |
| Service discovery | Không có ServiceInstance | Lỗi từ LoadBalancer/adapter, phụ thuộc integration | Có thể chưa kết nối |
| Callback/app domain | StockNotFoundException | Exception tự định nghĩa | Phụ thuộc nơi phát sinh |

**Cách xử lý nên đi từ cụ thể đến tổng quát**. Ví dụ:

~~~java
try {
    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
} catch (HttpClientErrorException.NotFound ex) {
    throw new StockNotFoundException(sku, ex);
} catch (HttpClientErrorException.TooManyRequests ex) {
    throw new InventoryRateLimitedException(
            ex.getResponseHeaders() == null
                    ? null
                    : ex.getResponseHeaders().getFirst(HttpHeaders.RETRY_AFTER),
            ex);
} catch (HttpServerErrorException ex) {
    throw new InventoryUnavailableException("Inventory returned 5xx", ex);
} catch (ResourceAccessException ex) {
    throw new InventoryTransportException("Inventory transport failure", ex);
} catch (RestClientException ex) {
    throw new InventoryProtocolException("Unexpected inventory response", ex);
}
~~~

Các exception domain trong ví dụ đều do ứng dụng tự định nghĩa; constructor được minh họa theo ý tưởng. Việc phân loại rõ ràng giúp tầng trên quyết định retry theo nhóm lỗi thay vì **catch(Exception)** rồi coi tất cả là lỗi hạ tầng.

Không suy đoán rằng một timeout có nghĩa server chưa xử lý: server có thể đã ghi database và gửi response nhưng client không kịp nhận. Đây là nguyên nhân phải thiết kế retry an toàn cho request có side effect.

## 12. Error body có cấu trúc: JSON domain hoặc ProblemDetail

Nhiều API trả dữ liệu lỗi theo một schema thống nhất, ví dụ **application/problem+json** hoặc JSON nội bộ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://errors.example.net/stock-conflict",
  "title": "Inventory conflict",
  "status": 409,
  "detail": "Reservation was changed by another request"
}
~~~

Trong Spring MVC, **ProblemDetail** là kiểu dữ liệu biểu diễn problem details của HTTP. Tuy nhiên, client không được mặc định mọi HTTP 409 đều có body cùng schema, bởi gateway, proxy và downstream phiên bản cũ có thể trả HTML, text hoặc JSON khác.

Một adapter có thể giữ contract riêng:

~~~java
record ApiError(
        String code,
        String message,
        String traceId) {
}
~~~

Nếu defaultStatusHandler của RestClient đã ném RestClientResponseException, có thể lấy response body rồi thử giải mã:

~~~java
try {
    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
} catch (HttpClientErrorException.Conflict ex) {
    ApiError error = null;
    try {
        error = objectMapper.readValue(
                ex.getResponseBodyAsByteArray(),
                ApiError.class);
    } catch (IOException | IllegalArgumentException ignored) {
        // Error body có thể rỗng hoặc không đúng JSON contract.
    }

    String code = error == null ? "STOCK_CONFLICT" : error.code();
    throw new StockConflictException(code, ex);
}
~~~

Trong ví dụ, **objectMapper** là Jackson ObjectMapper được inject từ ứng dụng; StockConflictException do ứng dụng tự định nghĩa. Đoạn code minh họa việc ưu tiên structured error body nhưng vẫn fallback nếu body không decode được.

**Tránh swallow exception quá rộng** trong tầng HTTP: chỉ fallback cho lỗi parse error payload đã được dự kiến. Không dùng catch(Exception) để che mất lỗi lập trình, null pointer hoặc lỗi luồng nghiệp vụ.

### 12.1. Vấn đề đọc body đúng một lần

Trong **onStatus((request, response) -> ...)**, nếu tự đọc response.getBody() rồi tiếp tục trả về bình thường, converter sau đó có thể không còn dữ liệu để đọc. Thiết kế ít lỗi hơn:

1. Handler nhận status lỗi.
2. Đọc một lần error body, giới hạn kích thước và xác minh charset/Content-Type.
3. Tạo exception domain có status, message an toàn và cause cần thiết.
4. Ném exception ngay từ handler.

Không lưu toàn bộ ClientHttpResponse vào một đối tượng được sử dụng sau khi request kết thúc. Stream kết nối có vòng đời giới hạn; xử lý/đóng đúng tài nguyên là quan trọng để connection pool không cạn.

## 13. Response rỗng, Optional và contract trả về

Một trong những bug phổ biến là viết:

~~~java
StockResponse stock = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);

int available = stock.available();  // Có thể NullPointerException!
~~~

Nếu HTTP response không có body, body(Class) trả null theo hợp đồng API. Do đó, cần định nghĩa contract theo từng endpoint:

| Endpoint | Response hợp lệ | Cách xử lý |
| --- | --- | --- |
| GET /stock/{sku} | 200 có StockResponse bắt buộc | Null là lỗi contract |
| GET /stock/{sku} | 404 khi SKU không tồn tại | Optional.empty() hoặc domain not-found theo quyết định |
| DELETE /reservations/{id} | 204 không có body | toBodilessEntity() hoặc method trả void |
| POST /reservations | 201 có Location | Kiểm tra Location; body có thể tùy contract |
| POST /jobs | 202 có job ID | Trả kết quả pending, không coi như completed |
| GET /stocks | 200 với [] | Danh sách rỗng hợp lệ, khác với response body null |

Đừng nhầm **[]** với **null** hoặc **404**:

- **[]**: server đã trả một danh sách hợp lệ với 0 phần tử.
- **null**: không có body (hoặc JSON null) nên không có danh sách typed để sử dụng.
- **404**: HTTP error theo mặc định, cần xử lý theo contract endpoint.

Đối với POST/DELETE không trả body, dùng:

~~~java
ResponseEntity<Void> result = client.delete()
        .uri("/api/reservations/{id}", reservationId)
        .retrieve()
        .toBodilessEntity();

if (!result.getStatusCode().is2xxSuccessful()) {
    throw new IllegalStateException("Unexpected reservation status");
}
~~~

Trong trường hợp mặc định, response 4xx/5xx đã sinh exception trước dòng kiểm tra is2xxSuccessful(); điều kiện còn hữu ích khi contract chỉ chấp nhận 2xx và không muốn vô tình coi status khác là thành công.

## 14. Mapping lỗi thành domain result: một adapter hoàn chỉnh

Lớp HTTP adapter nên có trách nhiệm **chuyển đổi từ HTTP semantics sang domain semantics**, để service nghiệp vụ không cần catch trực tiếp HttpClientErrorException hoặc hiểu chi tiết của LoadBalancer.

Một kiểu kết quả đơn giản:

~~~java
record StockDto(String sku, int available) {
}

interface InventoryPort {
    Optional<StockDto> findStock(String sku);
}
~~~

Implement bằng RestClient:

~~~java
@Service
class RestClientInventoryAdapter implements InventoryPort {

    private final RestClient client;

    RestClientInventoryAdapter(@LoadBalanced RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @Override
    public Optional<StockDto> findStock(String sku) {
        try {
            StockDto stock = client.get()
                    .uri("/api/stock/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(StockDto.class);

            if (stock == null) {
                throw new InventoryProtocolException("Missing stock body");
            }
            return Optional.of(stock);

        } catch (HttpClientErrorException.NotFound ex) {
            // Contract: 404 là SKU chưa tồn tại.
            return Optional.empty();
        } catch (HttpClientErrorException.TooManyRequests ex) {
            throw new InventoryRateLimitedException(ex);
        } catch (HttpServerErrorException ex) {
            throw new InventoryUnavailableException("Inventory 5xx", ex);
        } catch (ResourceAccessException ex) {
            throw new InventoryTransportException("Inventory transport", ex);
        } catch (RestClientException ex) {
            throw new InventoryProtocolException("Invalid inventory response", ex);
        }
    }
}
~~~

Các exception domain là thành phần dự án tự khai báo. Không cần đổi trực tiếp HTTP status thành 500 ở mọi tầng; một REST controller bên ngoài có thể ánh xạ InventoryUnavailableException sang 503, nhưng nếu đây là batch job, nó có thể chuyển thành trạng thái task thất bại và áp dụng lịch thử lại riêng.

**Vì sao catch từng nhánh?**

- 404 trở thành Optional.empty() theo contract đã xác minh.
- 429 và 5xx được phân loại để tầng retry quan sát.
- Lỗi transport có thể chưa có HTTP status.
- Lỗi deserialization/contract không nên bị retry như một lỗi availability.

Không cần đưa tất cả các ngoại lệ này lên chữ ký của interface InventoryPort; adapter có thể cung cấp một taxonomy domain ổn định cho toàn bộ ứng dụng.

## 15. Retry: chỉ một số exception/status phù hợp để thử lại

Trong một hệ thống có LoadBalancer, retry có thể chọn **ServiceInstance khác**. Nhưng **chọn lại instance** và **gửi lại cùng thao tác** là hai việc khác nhau. Một timeout sau POST tạo reservation có thể xảy ra khi server đã ghi transaction thành công.

| Tình huống | Có nên retry? | Điều kiện |
| --- | --- | --- |
| 400 validation | Thông thường không | Sửa request trước |
| 401/403 | Thông thường không | Chỉ refresh auth theo policy hợp lệ, không loop |
| 404 resource không tồn tại | Không trong contract thông thường | Chỉ thử lại nếu hệ thống có eventual consistency được xác nhận |
| 409 optimistic locking | Tùy nghiệp vụ | Đọc trạng thái mới và giải quyết xung đột, không retry y nguyên |
| 429 rate limiting | Có thể | Tôn trọng Retry-After, giới hạn attempts/deadline |
| 502/503/504 | Có thể | Chỉ với thao tác retry-safe và backoff |
| Timeout/connection reset | Có thể | Không giả định server chưa xử lý; xét idempotency |
| JSON schema sai | Không | Sửa contract, mapping hoặc version |
| Không tìm thấy instance | Có thể sau discovery refresh | Tránh loop liên tục nếu registry trống |

### 15.1. Retry không phải chức năng của onStatus()

onStatus chỉ **phân loại response thành exception hoặc một cách xử lý tùy biến**. Nó không tự gửi lại request. Việc retry cần một cơ chế riêng như Spring Cloud LoadBalancer retry, Spring Retry, Resilience4j hoặc orchestration tại tầng nghiệp vụ.

Đặt retry ở nhiều tầng có thể làm tăng số request thực tế. Ví dụ 3 attempts ở adapter và 3 attempts tại proxy có thể khiến downstream nhận đến 9 lần gọi cho một yêu cầu logic, gây retry storm.

### 15.2. Giữ Idempotency-Key qua các lần thử

Ví dụ tạo reservation:

~~~java
ReserveResponse reserve(
        String sku, int quantity, String operationId) {

    return client.post()
            .uri("/api/reservations")
            .header("Idempotency-Key", operationId)
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ReserveRequest(sku, quantity))
            .retrieve()
            .body(ReserveResponse.class);
}
~~~

Nếu một lớp retry tái phát request, **operationId phải giữ nguyên** trong toàn bộ các lần thử của cùng thao tác logic. Backend cần lưu key với fingerprint và kết quả để deduplicate; chỉ gửi header không tự bảo đảm an toàn.

Một domain exception do timeout không nên mặc nhiên chuyển thành trạng thái “giao dịch thất bại”. Với thao tác có side effect, có thể cần API kiểm tra trạng thái theo operationId để giải quyết kết quả chưa xác định.

## 16. Kiểm thử ánh xạ response và exception

**MockRestServiceServer** trong spring-test phù hợp để kiểm tra RestClient gọi đúng URL, mapping body, headers và exceptions mà không cần chạy server thật.

### 16.1. Unit test: 200 + JSON thành DTO

~~~java
@Test
void mapsJsonResponseToDto() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/BOOK-01"))
            .andRespond(withSuccess(
                    "{\"sku\":\"BOOK-01\",\"available\":7}",
                    MediaType.APPLICATION_JSON));

    StockDto result = client.get()
            .uri("/api/stock/{sku}", "BOOK-01")
            .retrieve()
            .body(StockDto.class);

    assertEquals("BOOK-01", result.sku());
    assertEquals(7, result.available());
    server.verify();
}
~~~

Trong đoạn test, StockDto là record đã khai báo ở mục 14. Cần import JUnit, MockRestServiceServer, requestTo, withSuccess và các class Spring Test tương ứng. **Không gắn @LoadBalanced trong unit test này:** mục tiêu là kiểm tra body mapping, không phải chọn instance.

### 16.2. Unit test: mặc định 404 sinh exception

~~~java
@Test
void maps404ToHttpClientErrorException() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/UNKNOWN"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":\"STOCK_NOT_FOUND\"}"));

    assertThrows(HttpClientErrorException.NotFound.class, () ->
            client.get()
                    .uri("/api/stock/{sku}", "UNKNOWN")
                    .retrieve()
                    .body(StockDto.class));

    server.verify();
}
~~~

Các static imports cho ví dụ: requestTo, withStatus, assertThrows. Test xác nhận **mặc định retrieve không trả DTO cho 404**, mà ném exception.

### 16.3. Unit test: 204 không có body

~~~java
@Test
void handlesNoContentWithoutDto() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");
    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/reservations/123"))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

    ResponseEntity<Void> response = client.delete()
            .uri("/api/reservations/{id}", "123")
            .retrieve()
            .toBodilessEntity();

    assertEquals(HttpStatus.NO_CONTENT, response.getStatusCode());
    assertNull(response.getBody());
    server.verify();
}
~~~

### 16.4. Unit test: onStatus ánh xạ 409 thành domain exception

~~~java
@Test
void mapsConflictToDomainException() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");
    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/BOOK-01"))
            .andRespond(withStatus(HttpStatus.CONFLICT));

    assertThrows(StockConflictException.class, () ->
            client.get()
                    .uri("/api/stock/{sku}", "BOOK-01")
                    .retrieve()
                    .onStatus(
                            s -> s.value() == 409,
                            (req, resp) -> {
                                throw new StockConflictException("BOOK-01");
                            })
                    .body(StockDto.class));

    server.verify();
}
~~~

StockConflictException là exception domain do ứng dụng định nghĩa. Test xác nhận logic ánh xạ chứ không yêu cầu triển khai registry.

### 16.5. Unit test: exchange() không áp dụng status handler

Một bài test cần có để tránh lỗi logic:

~~~java
int status = client.get()
        .uri("/api/stock/{sku}", "MISSING")
        .exchange((request, response) ->
                response.getStatusCode().value());
~~~

Nếu server mô phỏng HTTP 404, **status có thể bằng 404 mà không bị handler mặc định ném exception**, bởi exchange() bỏ qua status handlers. Hãy thêm test so sánh với retrieve() cùng một mock response để xác minh.

### 16.6. Ma trận test nên có

| Input mock | API gọi | Kỳ vọng |
| --- | --- | --- |
| 200 JSON DTO | body(Class) | StockDto hợp lệ |
| 200 JSON array | body(ParameterizedTypeReference) | List<StockDto> |
| 201 + Location | toBodilessEntity | Lấy được status và Location |
| 204 rỗng | body(Class) / toBodilessEntity | null hoặc ResponseEntity<Void> |
| 404 | retrieve mặc định | HttpClientErrorException.NotFound |
| 409 | onStatus custom | StockConflictException |
| 429 + Retry-After | onStatus custom | RateLimit exception với thông tin Retry-After |
| 503 | retrieve mặc định | HttpServerErrorException hoặc RestClientResponseException |
| 200 JSON không hợp lệ | body(Class) | Lỗi deserialization |
| 200 Content-Type không hỗ trợ | body(Class) | Lỗi converter |
| 404 | exchange() | Callback tự xử lý hoặc trả status |
| Read timeout | HTTP server mock thực tế | ResourceAccessException/transport error |

MockRestServiceServer không đủ để khẳng định **timeout thật, TLS, connection pooling hoặc ServiceInstance selection**. Muốn kiểm thử I/O và LoadBalancer, dùng server stub đang chạy (ví dụ WireMock/MockWebServer) cùng SimpleDiscoveryClient hoặc registry test, rồi kiểm tra đích kết nối đã được tái dựng.

## 17. Kiểm thử trong hệ thống có Spring Cloud LoadBalancer

Để xác minh mapping trong một request từ Order Service sang Inventory Service, có thể khai báo hai instance bằng SimpleDiscoveryClient:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Hai stub server trả response với trường instanceId khác nhau:

~~~json
{"sku":"BOOK-01","available":7,"instanceId":"inventory-a"}
~~~

~~~json
{"sku":"BOOK-01","available":4,"instanceId":"inventory-b"}
~~~

Gửi nhiều request qua RestClient được tạo từ **@LoadBalanced RestClient.Builder**, rồi xác minh:

1. URI trong code là **http://inventory-service/api/stock/BOOK-01**.
2. LoadBalancer chọn một trong hai instance đã khai báo.
3. Body được deserialize theo DTO như mong đợi.
4. Server trả 404/503 được xử lý như HTTP error thật.
5. Tắt một stub server làm lỗi transport, khác với server vẫn chạy nhưng trả 503.
6. Khi không còn instance được supplier cung cấp, lỗi có thể phát sinh trước khi gửi HTTP.
7. Tracing/log chỉ ra service ID, instance đã chọn và loại lỗi mà không làm lộ token hoặc raw body nhạy cảm.

**Đừng nhầm ba tình huống 503**:

- Inventory server trực tiếp trả HTTP 503.
- Gateway trung gian trả HTTP 503 khi không gọi được upstream.
- LoadBalancer không tìm thấy instance và adapter báo một lỗi ở tầng chọn đích, có thể biểu diễn bằng status hoặc exception tùy integration.

Chúng có thể giống nhau về status ở tầng controller nhưng khác nơi phát sinh, chính sách retry và khả năng điều tra sự cố.

## 18. Observability, logging và bảo mật khi ánh xạ lỗi

Khi xử lý exception, cố gắng giữ các thuộc tính có giá trị vận hành:

| Thuộc tính | Mục đích | Lưu ý |
| --- | --- | --- |
| serviceId | Biết downstream logic nào | inventory-service |
| instanceId | Biết bản sao được chọn | Không phải lúc nào client cũng có sẵn |
| HTTP method | Phân biệt GET và POST có side effect | Không log request body |
| Path template | Biết endpoint | Tránh ghi dữ liệu nhạy cảm từ path thật |
| Status code | Phân loại 4xx/5xx | Chỉ có khi nhận HTTP response |
| Error category | HTTP, transport, decode, discovery | Hữu ích cho cảnh báo |
| Duration/timeout | Theo dõi SLO | Tách tổng deadline và từng attempt |
| Retry attempt | Phát hiện retry storm | Theo dõi số lần gửi thực tế |
| Trace/correlation ID | Ghép các service call | Không sử dụng như dữ liệu bảo mật |

Tránh log toàn bộ URL nếu query có access token, email hoặc thông tin khách hàng. Tránh ghi toàn bộ **getResponseBodyAsString()** lên log. Với body lỗi, lưu status, một error code đã được chuẩn hóa và tối đa một đoạn message an toàn.

Trong Spring Boot, HTTP client observations có thể sử dụng Micrometer Observation. Khi tạo RestClient.Builder bằng **new RestClient.builder()** hoặc cấu hình bean thủ công, cần kiểm tra các observation registry, interceptors, auth và timeout có được gắn đúng hay không. Mapping exception không nên làm mất trace ID/cause.

Không coi **RestClientResponseException** là lỗi có thể retry mặc định; cần kiểm tra **status**, HTTP method và idempotency.

## 19. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng body(DTO) cho mọi status rồi kiểm tra status sau | 4xx/5xx đã ném exception trước | Dùng toEntity cho response thành công, onStatus/catch cho lỗi |
| Coi 204 là JSON DTO bắt buộc | Null hoặc lỗi sau đó | Dùng toBodilessEntity và contract rõ ràng |
| Dùng body(List.class) | Mất kiểu phần tử generic | ParameterizedTypeReference<List<DTO>> |
| Trả Optional.empty với mọi 404 | Che lỗi route/registry khác | Chỉ áp dụng cho endpoint có contract 404 = không tồn tại |
| Nuốt mọi 4xx trong defaultStatusHandler | Request sai vẫn đi tiếp | Handler hẹp, có chủ đích |
| Dùng exchange() và kỳ vọng onStatus hoạt động | 404/503 có thể lọt sang nhánh thành công | Tự kiểm tra status trong callback |
| Catch(RestClientException) rồi retry tất cả | Retry lỗi validation hoặc JSON schema | Tách HTTP/transport/decode trước khi quyết định |
| Dùng onStatus như retry mechanism | Không retry thật | Cấu hình retry độc lập với budget và idempotency |
| Log full error body | Rò rỉ dữ liệu nhạy cảm | Redaction, size limit và structured logging |
| Dùng RestClient không @LoadBalanced với service ID | UnknownHost hoặc không qua LB | Đúng bean/builder và dependency |
| Không cấu hình timeout | Thread blocking quá lâu | Set connect/read/pool timeout theo request factory |
| Coi timeout POST là chắc chắn thất bại | Duplicate side effect khi retry | Idempotency key và kiểm tra trạng thái operation |

## 20. Checklist thực hành

- [ ] Có RestClient được cấu hình đúng HTTP client factory, timeout và LoadBalancer khi gọi bằng service ID.
- [ ] Mỗi endpoint xác định rõ DTO, generic body, response rỗng hay ResponseEntity.
- [ ] Không dereference body() trước khi kiểm tra null nếu contract không bảo đảm.
- [ ] Dùng ParameterizedTypeReference cho kiểu generic.
- [ ] Phân biệt 200/201/202/204/206 theo contract.
- [ ] Ánh xạ 404/409/422 theo nghiệp vụ; không coi mọi 4xx là retryable.
- [ ] Đọc Retry-After theo đúng định dạng khi xử lý 429/503 có policy retry.
- [ ] Dùng onStatus ở mức phù hợp; hiểu thứ tự per-request và global default handlers.
- [ ] Với exchange(), tự kiểm tra status và đọc response đúng vòng đời.
- [ ] Tách HTTP error, transport error, decode error và discovery error.
- [ ] Giữ cause, service ID, status và trace ID khi tạo exception domain.
- [ ] Retry có giới hạn attempts, backoff, deadline và bảo vệ idempotency.
- [ ] Có unit test cho 2xx/4xx/5xx, body rỗng, JSON lỗi và custom onStatus.
- [ ] Có integration test riêng cho @LoadBalanced và URI/service instance thực tế.
- [ ] Không log credential, token, cookie hoặc raw response body nhạy cảm.

## 21. Kết luận

**Ánh xạ phản hồi của RestClient gồm ba trách nhiệm tách biệt:** chuyển body HTTP thành kiểu Java; quyết định cách diễn giải HTTP status; và chuyển lỗi HTTP/transport/deserialize thành exception hoặc kết quả domain phù hợp.

Với **retrieve()**, body(Class) và body(ParameterizedTypeReference) trả DTO hoặc null nếu không có body; toEntity() giữ status/headers; toBodilessEntity() dành cho response không cần nội dung. Mặc định 4xx/5xx tạo HTTP exception, có thể thay bằng onStatus() hoặc defaultStatusHandler(). Với **exchange()**, ứng dụng phải tự quản lý status và body vì handler mặc định không được áp dụng.

Trong Spring Cloud LoadBalancer, danh sách ServiceInstance và thuật toán chọn đích chỉ quyết định **request được gửi đến đâu**. Chúng không tự định nghĩa nghiệp vụ của 404, 409, 429, 503, timeout hay JSON sai. Thiết kế đúng một lớp HTTP adapter, một taxonomy lỗi rõ ràng và bộ test theo ma trận status sẽ giúp RestClient giao tiếp giữa dịch vụ ổn định, dễ chẩn đoán và retry an toàn hơn.

## 22. Tài liệu tham khảo

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, mapping body, ResponseEntity, onStatus và exchange.
- [RestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestClient.ResponseSpec.html): body, requiredBody (version-specific), toEntity, toBodilessEntity, onStatus và mặc định lỗi.
- [RestClient.RequestHeadersSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html): retrieve, exchange và cách làm việc với request.
- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): tích hợp RestClient, BlockingLoadBalancerClient, instance supplier và retry.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestClient.Builder và service discovery.
- [Spring Framework Testing – Client-side REST Tests](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer để kiểm thử HTTP client.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa HTTP status, safe/idempotent methods.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng chuẩn để trả thông tin lỗi qua HTTP API.
