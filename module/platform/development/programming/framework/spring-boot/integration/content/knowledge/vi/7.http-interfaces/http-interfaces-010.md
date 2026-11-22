# Kiểm thử hợp đồng khai báo và hành vi thực tế của proxy HTTP interface trong Spring Boot

Một Java interface có các annotation `@GetExchange`, `@PostExchange`, `@PathVariable`, `@RequestParam` và `@RequestBody` trông giống **hợp đồng HTTP**. Spring Framework có thể tạo một **HTTP service client proxy** từ interface bằng `HttpServiceProxyFactory`, gắn với `RestClient`, `WebClient` hoặc các adapter được hỗ trợ. Tuy nhiên, **khai báo đúng về mặt cú pháp không chứng minh HTTP request được gửi đúng và server hiểu đúng**: một path variable có ký tự đặc biệt có thể được mã hóa khác dự kiến; header có thể thiếu; request body có thể mất field; API trả `204` thay vì JSON; hoặc timeout sau khi server đã commit vẫn khiến client hiểu rằng thao tác thất bại.

Bài thuộc chương **HTTP interface** của module **SPRING_BOOT_INTEGRATION**, nơi nghiên cứu tích hợp Spring Boot qua HTTP client, database, cache, broker thông điệp và các adapter Spring Integration. Trọng tâm của bài là kiểm thử ba cấp:

1. **Hợp đồng khai báo**: annotation, method, tham số và kiểu trả về của interface có diễn đạt đúng API dự kiến không?
2. **Hành vi proxy thực tế**: HTTP method, URL, query encoding, headers, body, codec, phản hồi và exception mà proxy phát ra có giống hợp đồng không?
3. **Tính tương thích giữa các dịch vụ**: request thật do proxy tạo có được provider hiện tại chấp nhận và có đúng ngữ nghĩa dữ liệu, lỗi, idempotency, timeout khi chạy qua network không?

Chúng ta sẽ xây một ví dụ inventory client, kiểm thử bằng **MockRestServiceServer**, **HTTP stub server** và **provider contract/compatibility tests**, sau đó đưa vào CI. Các ví dụ nhắm tới Spring Boot 3.x và Spring Framework 6.1+ với `RestClient`, `HttpServiceProxyFactory` và Spring Test. Những phiên bản Framework 6.0, Boot cũ hơn hoặc Spring Framework 7 có thể có cách tạo factory/adapter, package hoặc hỗ trợ return type khác; đối chiếu API của BOM đang chạy trước khi copy code.

## 1. Interface HTTP là khai báo, proxy mới tạo hành vi mạng

Giả sử `checkout-service` cần gọi `inventory-service` để đọc hàng còn lại và tạo giữ chỗ:

~~~mermaid
flowchart LR
    A["CheckoutService"] --> I["InventoryHttpApi (interface)"]
    I --> P["HttpServiceProxyFactory"]
    P --> AD["RestClientAdapter"]
    AD --> R["RestClient"]
    R --> N["HTTP client / serializer / TLS"]
    N --> S["inventory-service"]
    S --> DB[("PostgreSQL")]
~~~

Ở đây:

- `InventoryHttpApi` là **Java contract** ở phía caller, chứa tên path, HTTP method, tham số, kiểu phản hồi.
- `HttpServiceProxyFactory` phân tích method/annotation và sinh proxy trong runtime.
- `RestClientAdapter` nối proxy với một `RestClient` thực hiện HTTP đồng bộ.
- `RestClient` chịu trách nhiệm phần lớn hành vi runtime: base URL, request interceptors, message converters, network request factory, lỗi HTTP và timeout.
- `inventory-service` có hợp đồng của riêng nó, thường là controller, schema, OpenAPI hoặc specification/provider tests.

**Compile thành công** chỉ chứng minh kiểu Java và annotation hiện diện. Nó không xác nhận URL `/v1/inventory/SKU-1` đã được ghép đúng, `X-Correlation-Id` thực sự được gửi hay lỗi `409 Conflict` đã được mapping thành domain exception.

### Ba mô hình kiểm thử bổ sung nhau

| Lớp kiểm thử | Nhìn thấy điều gì? | Không chứng minh được điều gì? |
| --- | --- | --- |
| Reflection/static contract check | Annotation route, tham số, return type | Proxy gửi byte/header gì, codec hoạt động ra sao |
| Client-proxy HTTP test | Method, URL, headers, JSON, response, exception của proxy thực | Server thật còn hỗ trợ contract đó không |
| Provider contract test | Server có nhận request và trả cấu trúc/status theo hợp đồng không | Client thật đã tạo request tương thích hay chưa |
| End-to-end/integration | Kết hợp client, transport và server trong môi trường tương tự production | Tất cả biến thể lỗi và hợp đồng tương lai |

Muốn bảo vệ hợp đồng thật, cần **ít nhất một test đi qua proxy thực**; không chỉ mock interface bằng Mockito rồi assert service gọi `inventoryApi.reserve(command)`.

## 2. Xây dựng hợp đồng HTTP interface có thể kiểm thử

Một contract inventory tối giản:

~~~http
GET /v1/inventory/{sku}?warehouse={warehouse}
Accept: application/json
X-Correlation-Id: <trace-token>

HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-42","available":5}
~~~

Và thao tác tạo giữ chỗ (có side effect):

~~~http
POST /v1/inventory/reservations
Content-Type: application/json
Accept: application/json
Idempotency-Key: reserve-order-1042
X-Correlation-Id: trace-abc

{"orderId":"ORDER-1042","sku":"SKU-42","quantity":2}
~~~

Response thành công:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"reservationId":"RES-918","status":"RESERVED"}
~~~

Các DTO Java:

~~~java
public record StockDto(String sku, int available) {}

public record ReserveCommand(
        String orderId,
        String sku,
        int quantity
) {}

public record ReservationDto(
        String reservationId,
        String status
) {}
~~~

Và HTTP interface:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/v1/inventory", accept = "application/json")
public interface InventoryHttpApi {

    @GetExchange("/{sku}")
    StockDto getStock(
            @PathVariable("sku") String sku,
            @RequestParam("warehouse") String warehouse,
            @RequestHeader("X-Correlation-Id") String traceId);

    @PostExchange(
            url = "/reservations",
            contentType = "application/json")
    ReservationDto reserve(
            @RequestBody ReserveCommand command,
            @RequestHeader("Idempotency-Key") String key,
            @RequestHeader("X-Correlation-Id") String traceId);

    @DeleteExchange("/reservations/{reservationId}")
    void cancel(
            @PathVariable("reservationId") String reservationId);
}
~~~

**Đây là hợp đồng của client**, không phải controller server. Một số điểm có tính quyết định:

- `@HttpExchange` ở interface xác định prefix URL và media type được chấp nhận.
- `@GetExchange` và `@PostExchange` xác định HTTP verb và path bổ sung.
- `@PathVariable("sku")` nối tham số vào path, liên quan trực tiếp tới URI encoding.
- `@RequestParam("warehouse")` quyết định query parameter; trường hợp null, danh sách hoặc ký tự `+`, dấu cách, Unicode cần có test theo hợp đồng.
- `@RequestHeader` đưa correlation ID và idempotency key vào network request; việc có tham số Java không chứng minh header sẽ xuất hiện đúng.
- `@RequestBody` kích hoạt serialization sang HTTP body qua message converter hoặc encoder.
- `ReservationDto` đòi hỏi proxy xử lý status và response body; server đổi sang `204 No Content` có thể phá kỳ vọng đó.

Hợp đồng cần được thống nhất với provider bằng API specification, contract tests hoặc giao tiếp liên nhóm. Annotation phía consumer **không tự xác minh** những lựa chọn của server.

### Đặt tên route và version có chủ đích

`/v1/inventory` là một phần của API contract. Không đổi `v1` thành `v2` chỉ ở interface rồi mong proxy “tương thích” với server cũ. Thay đổi field, default, enum, path, error code hoặc authentication policy có thể là breaking change dù project Java vẫn biên dịch.

## 3. Tạo proxy đúng bằng HttpServiceProxyFactory

Một Spring Boot application dùng Spring MVC hoặc client blocking có thể tạo bean như sau:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpClientConfiguration {

    @Bean
    InventoryHttpApi inventoryHttpApi(
            RestClient.Builder restClientBuilder,
            @Value("${app.inventory.base-url}") String baseUrl) {

        RestClient restClient = restClientBuilder
                .baseUrl(baseUrl)
                .build();

        var adapter = RestClientAdapter.create(restClient);

        return HttpServiceProxyFactory
                .builderFor(adapter)
                .build()
                .createClient(InventoryHttpApi.class);
    }
}
~~~

`application.yml`:

~~~yaml
app:
  inventory:
    base-url: https://inventory.internal.example
~~~

Những điều cần biết:

1. `RestClient.Builder` do Spring Boot cung cấp (khi classpath/auto-config phù hợp) có thể chứa converter, observation và customizer. Nếu tự `RestClient.builder()`, bạn có thể bỏ qua customizer mà ứng dụng dựa vào.
2. `HttpServiceProxyFactory.builderFor(adapter)` là API tiện ích của các phiên bản Spring Framework hiện đại; không tự giả định nó tồn tại trên mọi version.
3. Nếu tạo nhiều proxy cho các provider khác nhau, mỗi proxy nên có **base URL, timeout, auth policy và naming rõ**, tránh dùng chung một mutable builder đã bị thay đổi.
4. Proxy thường được đăng ký singleton và có thể dùng từ nhiều thread theo client bên dưới; không tạo factory/client mới cho mỗi business request.
5. Chọn client **đồng bộ** `RestClient` hay **reactive** `WebClient` theo loại return type và execution model; không thay backend mà bỏ qua thay đổi semantics.

**Bẫy kiểm thử:** nếu service chỉ test bằng `@MockBean InventoryHttpApi` hoặc Mockito mock, đường `HttpServiceProxyFactory → RestClientAdapter → HTTP` hoàn toàn không chạy. Mock đó hữu ích cho *unit test của service*, nhưng không đạt mục tiêu bài này.

## 4. Định nghĩa một hợp đồng có thể kiểm tra bằng bảng

Trước khi viết test, đặc tả hành vi trên wire bằng một bảng, không chỉ đọc annotation:

| Điều kiện/đầu vào | Request bắt buộc | Response/exception kỳ vọng |
| --- | --- | --- |
| Đọc SKU bình thường | GET `/v1/inventory/SKU-42?warehouse=HCM`, Accept JSON, correlation | 200 JSON → `StockDto` |
| Warehouse chứa dấu cách | Query được URI-encode nhất quán, server decode về giá trị ban đầu | Không đổi nghĩa tham số |
| SKU chứa dấu `/` hoặc Unicode | Path variable được encode theo chính sách API | Không vô tình đổi route hoặc thành hai path segments |
| Tạo giữ chỗ | POST, JSON đúng field, `Idempotency-Key` giữ nguyên qua retries | 201 JSON → `ReservationDto` |
| Body sai schema | JSON thiếu field bắt buộc hoặc type sai | Lỗi client/provider được phân loại |
| SKU không tồn tại | GET đúng đường dẫn | 404 được biểu diễn thành lỗi/domain result đã thỏa thuận |
| Hết hàng | POST đúng payload | 409 Conflict theo hợp đồng |
| Provider quá tải | HTTP 503, có thể `Retry-After` | Không retry vô hạn hoặc nhận nhầm là lỗi dữ liệu |
| Request quá hạn | Client timeout theo cấu hình | Error type được phân loại; kết quả ghi có thể chưa rõ |
| Hủy thành công | DELETE đúng id | 204; proxy không cố deserialize object không có |
| Body response thêm field mới | JSON vẫn hợp lệ theo version policy | Consumer có hoặc không hỗ trợ tùy DTO/codec |

Đây là **bảng quyết định cho test**, không phải cam kết Spring tự xử lý mọi biến thể. Với path encoding và query list, phải test request thực mà proxy tạo; không đoán chỉ từ annotation.

## 5. MockRestServiceServer: kiểm tra request thật do RestClient proxy tạo

`MockRestServiceServer` thuộc Spring Test, có thể gắn vào `RestClient.Builder` trước khi build `RestClient`. Nó chặn các HTTP exchange ở tầng client cho test: **có chạy qua HTTP interface proxy, annotation resolver, RestClient và codecs**, nhưng không cần mở socket mạng thật.

Dependency test (thường đã có trong `spring-boot-starter-test`):

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Một ví dụ JUnit 5 hoàn chỉnh tập trung vào GET:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

class InventoryHttpApiContractTest {

    @Test
    void getStockBuildsCorrectMethodUrlHeadersAndDeserializesBody() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        InventoryHttpApi client = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(builder.build()))
                .build()
                .createClient(InventoryHttpApi.class);

        server.expect(requestTo(
                    "https://inventory.test/v1/inventory/SKU-42?warehouse=HCM"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("X-Correlation-Id", "trace-001"))
                .andExpect(header("Accept", "application/json"))
                .andRespond(withSuccess(
                    """
                    {"sku":"SKU-42","available":5}
                    """,
                    MediaType.APPLICATION_JSON));

        StockDto stock = client.getStock("SKU-42", "HCM", "trace-001");

        assertThat(stock.sku()).isEqualTo("SKU-42");
        assertThat(stock.available()).isEqualTo(5);
        server.verify();
    }
}
~~~

Các giả định của ví dụ:

- `InventoryHttpApi` và `StockDto` đã được khai báo ở mục 2.
- Test sử dụng Jackson/JSON message converters phù hợp; trong ứng dụng Boot có `spring-boot-starter-web`, JSON converter thường đã được thiết lập.
- `MockRestServiceServer.bindTo(builder)` phải chạy **trước `builder.build()`** để request dùng mock request factory.
- Đường dẫn kỳ vọng được viết **đầy đủ** gồm base URL; như vậy test bắt được lỗi ghép prefix URL.
- `server.verify()` xác nhận những expectation đã được thực hiện theo thiết lập của mock server.

Nếu test này được viết bằng `Mockito.when(api.getStock(...))`, nó **không** phát hiện một annotation URL bị gõ sai.

### Vì sao test nên kiểm tra nhiều hơn HTTP 200?

Một test chỉ stub server trả 200 rồi assert `StockDto` có giá trị có thể bỏ sót request gửi nhầm header, query hoặc method. Cần kiểm tra **đủ request contract**: method, URL/path/query, content-type, accept, auth/correlation, payload và các timeout/error mapping liên quan.

Tuy nhiên, không nên assert mọi header mặc định của HTTP client như `User-Agent`, `Connection`, `Content-Length` nếu chúng không thuộc hợp đồng. Assert quá chi tiết những thứ do transport sinh làm test giòn khi nâng phiên bản library.

## 6. Kiểm tra POST: body serialization và Idempotency-Key

Test request ghi phải kiểm tra **toàn bộ payload**, không chỉ “proxy đã gọi method”.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

class ReservationProxyContractTest {

    @Test
    void reserveSendsJsonAndStableIdempotencyKey() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.test");
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        InventoryHttpApi client = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(builder.build()))
                .build()
                .createClient(InventoryHttpApi.class);

        server.expect(requestTo(
                    "https://inventory.test/v1/inventory/reservations"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header("Idempotency-Key",
                        "reserve-order-1042"))
                .andExpect(header("X-Correlation-Id", "trace-abc"))
                .andExpect(content().json(
                    """
                    {"orderId":"ORDER-1042","sku":"SKU-42","quantity":2}
                    """, true))
                .andRespond(withStatus(
                        org.springframework.http.HttpStatus.CREATED)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                            """
                            {"reservationId":"RES-918","status":"RESERVED"}
                            """));

        ReservationDto reply = client.reserve(
                new ReserveCommand("ORDER-1042", "SKU-42", 2),
                "reserve-order-1042",
                "trace-abc");

        assertThat(reply.reservationId()).isEqualTo("RES-918");
        assertThat(reply.status()).isEqualTo("RESERVED");
        server.verify();
    }
}
~~~

`content().json(expected, true)` so sánh JSON theo cấu trúc với chế độ strict phù hợp API của Spring Test; thứ tự property object trong JSON không nhất thiết cần giống nhau. Tùy schema, cần thêm test:

- Field `quantity` phải là JSON number, không phải string.
- Không vô tình serialize dữ liệu bí mật/trạng thái nội bộ vào request DTO.
- Timestamp phải theo ISO-8601/timezone thống nhất; giá trị tiền không mất chính xác.
- Null/missing field khác nhau về mặt domain nếu server phân biệt.
- `schemaVersion` và enum có quy tắc tương thích khi phát triển API.
- Idempotency key phải giữ nguyên **cho cùng operation logic** qua mọi retry, không được sinh lại tại mỗi attempt.
- Response status 201 và body được kiểm tra theo hợp đồng; một provider đổi sang 202 Accepted/job ID là **thay đổi semantics**, dù HTTP vẫn thuộc nhóm 2xx.

### Tránh hardcode test chỉ đúng với một serializer ngẫu nhiên

Nếu provider chấp nhận JSON theo cấu trúc, nên dùng matching theo JSON semantic thay vì so sánh chuỗi byte với whitespace/key ordering cố định. Nếu chữ ký HMAC yêu cầu canonicalization byte-for-byte, đây lại là một **hợp đồng byte-level** cần test khác, gồm charset, newline, content encoding và thứ tự header theo thuật toán ký.

## 7. Kiểm thử URL encoding, query, optional values và headers

Những lỗi nguy hiểm nhất thường không nằm ở `@GetExchange` mà ở cách dữ liệu được biểu diễn trên wire.

### Path variable có ký tự đặc biệt

Ví dụ SKU có dấu cách hoặc ký tự `/`:

~~~text
SKU input: "ABC/2026"
Expected API semantics: một object ID duy nhất, không phải thêm route segment
Potential network paths:
  /v1/inventory/ABC%2F2026
  /v1/inventory/ABC/2026
~~~

Đường đi nào là hợp lệ phụ thuộc hợp đồng server/router/proxy, cách Spring URI encoding được cấu hình và khả năng reverse proxy giữ nguyên encoded slash. Nếu `/` là ký tự hợp lệ trong ID, **test qua HTTP transport thật và ingress**; một test mock URL chỉ kiểm tra phía client chưa phát hiện proxy trung gian giải mã hoặc chặn encoded slash.

Nếu API không cho phép slash trong SKU, hãy validate tại boundary thay vì cố encode. Không dùng raw string concatenation để ghép đường dẫn từ dữ liệu người dùng.

### Query string của giá trị đặc biệt

`@RequestParam` với dữ liệu có khoảng trắng, ký tự `+`, `&`, dấu phẩy, chữ có dấu hoặc list cần test riêng. Tùy hợp đồng, một list có thể dùng:

~~~http
GET /v1/inventory/search?tag=red&tag=large
~~~

hoặc:

~~~http
GET /v1/inventory/search?tag=red,large
~~~

Hai cách **không tương đương** nếu provider chỉ hỗ trợ một kiểu. Khai báo tham số `List<String>` không thay thế test wire. Nên thống nhất OpenAPI style/explode hoặc một schema cụ thể và viết assertion cho request được sinh.

### Header

Các trường hợp nên có test:

- `Authorization` có được gắn vào đúng provider, không rò sang host khác khi redirect.
- `X-Correlation-Id` có được chuyển qua các tầng từ HTTP ingress → client proxy → downstream.
- `Idempotency-Key` ổn định trên retry, không trùng giữa hai command không liên quan.
- `Accept` và `Content-Type` có đúng với codec được dùng; không chỉ assert body.
- Header của người dùng có được validate để không gây header injection/CRLF hoặc vượt kích thước cho phép.
- Nếu dùng cookies/tenant headers, chúng có xuất phát từ identity đáng tin cậy hay chỉ được caller tự điền.

**Security test** nên kiểm tra token/secret không bị log; contract test bình thường không nên ghi Bearer token thật vào fixture hoặc báo cáo CI.

## 8. Kiểm thử lỗi HTTP: 4xx, 5xx, body lỗi và exception mapping

Proxy không chỉ chuyển một HTTP 200 thành DTO; nó phải có policy khi server từ chối hoặc gặp lỗi.

Giả sử inventory server trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type":"https://errors.example/insufficient-stock",
 "title":"Not enough stock",
 "status":409,
 "detail":"Stock is already reserved"}
~~~

Phải quyết định rõ: service gọi proxy nhận **exception HTTP**, domain exception, hay `Result` có trạng thái thất bại? Trong `RestClient` với error handling mặc định của `retrieve()`, response 4xx/5xx thường được biểu diễn thành các `RestClientResponseException` và lớp con như `HttpClientErrorException`. **HTTP interface không tự biết 409 là “hết hàng” trong domain**.

Một test cho hành vi lỗi mặc định của RestClient-backed proxy:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

class ReservationErrorContractTest {

    @Test
    void conflictIsNotSilentlyConvertedToSuccess() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.test");
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        InventoryHttpApi client = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(builder.build()))
                .build()
                .createClient(InventoryHttpApi.class);

        server.expect(requestTo(
                    "https://inventory.test/v1/inventory/reservations"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withStatus(HttpStatus.CONFLICT)
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                        .body(
                            """
                            {"type":"about:blank","title":"Insufficient stock",
                             "status":409}
                            """));

        assertThatThrownBy(() -> client.reserve(
                new ReserveCommand("ORDER-1042", "SKU-42", 99),
                "reserve-order-1042", "trace-abc"))
                .isInstanceOf(HttpClientErrorException.Conflict.class);

        server.verify();
    }
}
~~~

Nếu dự án đã cấu hình custom status handler, kết quả có thể là exception domain khác; test phải assert **hợp đồng của client do ứng dụng định nghĩa**, không cố giữ exception mặc định khi đã chủ động thay đổi.

### Ma trận lỗi cần test

| Phản hồi/thất bại | Câu hỏi phải trả lời | Chính sách tham khảo |
| --- | --- | --- |
| `400 Bad Request` | Do client gửi sai dữ liệu hay schema? | Không retry mù; sửa contract/validation |
| `401 Unauthorized` | Token hết hạn, sai audience, auth misconfig? | Refresh credentials theo provider nếu được hỗ trợ; tránh retry vô hạn |
| `403 Forbidden` | Caller thiếu quyền hay tenant bị từ chối? | Không biến 403 thành 404 hoặc 200 tùy tiện |
| `404 Not Found` | ID không tồn tại; API có trả 404 cho trạng thái hợp lệ không? | Map thành NotFound theo contract, không mặc định null |
| `409 Conflict` | Lỗi tranh chấp có điều kiện hay nghiệp vụ hết hàng? | Phân loại domain, tránh tạo side effect lặp |
| `412 Precondition Failed` | ETag/version không khớp? | Giữ optimistic concurrency |
| `422 Unprocessable Entity` | Payload hợp cú pháp nhưng sai nghiệp vụ? | Trả validation/domain error có field details an toàn |
| `429 Too Many Requests` | Retry-After, quota theo tenant? | Backoff, giới hạn attempts và concurrency |
| `500/502/503/504` | Downstream lỗi/không sẵn sàng/timeout? | Retry hữu hạn cho thao tác an toàn; circuit breaker |
| Connect refused/DNS/TLS | Chưa kết nối được HTTP server | Phân biệt network exception; không kết luận server đã/ chưa xử lý |
| Read timeout sau POST | Server có thể đã commit nhưng client không nhận response | Idempotency + truy vấn lại trạng thái |
| Response JSON sai schema | Server deploy breaking change hoặc data lỗi | Fail rõ, đo contract drift |
| `204 No Content` | Caller có yêu cầu DTO không? | Với `void` có thể hợp lệ; với DTO cần test behavior rõ |

**Không test lỗi bằng cách chỉ mock một method Java ném `RuntimeException`**: như vậy bỏ qua status code, headers, codec, error body và chính sách handler của RestClient/WebClient.

## 9. 204, empty body, ResponseEntity và return type khác nhau

Cùng HTTP 204 nhưng ý nghĩa ở mỗi signature khác nhau:

~~~java
@DeleteExchange("/reservations/{reservationId}")
void cancel(@PathVariable String reservationId);
~~~

Với contract này, việc DELETE thành công không cần response body. Nhưng nếu định nghĩa:

~~~java
@GetExchange("/{sku}")
StockDto getStock(@PathVariable String sku);
~~~

và provider trả 204 không có body, caller có thể nhận null hoặc một lỗi chuyển đổi/giải mã tùy HTTP client adapter, response handling và phiên bản. Đừng giả định cơ chế mapping **tương đương `Optional.empty()`**; nếu 204 là một trạng thái hợp lệ, thiết kế kiểu trả về và test để biểu diễn nó một cách rõ ràng.

Một interface có thể chọn nhận cả metadata:

~~~java
@GetExchange("/{sku}")
ResponseEntity<StockDto> getStockWithStatus(
        @PathVariable("sku") String sku);
~~~

`ResponseEntity` có ích khi consumer cần status/headers như ETag, Cache-Control hoặc version. Nếu dùng return type reactive, hãy xét `Mono<ResponseEntity<T>>` so với `ResponseEntity<Flux<T>>` theo adapter, bởi thời điểm nhận headers và streaming body khác nhau. Không thay đổi return type mà không cập nhật contract test response/status.

### JSON backward compatibility

Một DTO Java record với constructor bắt buộc có thể khó chấp nhận field thiếu hơn một kiểu DTO có default. Ngược lại, field mới ở response có thể được deserializer bỏ qua hoặc làm lỗi tùy Jackson config. Vì vậy luôn có ít nhất hai fixture:

- **Provider cũ → consumer mới**: response thiếu field mới hoặc dùng enum cũ.
- **Provider mới → consumer cũ**: response thêm field hoặc enum value mới.

Không dùng Jackson `FAIL_ON_UNKNOWN_PROPERTIES` hoặc `@JsonIgnoreProperties(ignoreUnknown=true)` như giải pháp tổng quát mà không đánh giá rủi ro mất dữ liệu hoặc che giấu breaking change. Cần chọn *tolerant reader* theo hợp đồng nghiệp vụ.

## 10. Kiểm thử với HTTP stub server thật: WireMock

`MockRestServiceServer` không gửi request qua socket. Nó rất tốt để bắt mapping/serialization, nhưng **không** kiểm tra được DNS, connect/read timeout ở HTTP transport, redirect, chunking, TLS hoặc hành vi khi server cố tình giữ kết nối.

Để đi qua HTTP transport thật, dùng một server stub như WireMock 3. Ví dụ dependency test Maven (phiên bản do project chọn và khóa):

~~~xml
<dependency>
  <groupId>org.wiremock</groupId>
  <artifactId>wiremock</artifactId>
  <version>${wiremock.version}</version>
  <scope>test</scope>
</dependency>
~~~

Test đường GET qua TCP socket thật:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.*;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

class InventoryWireContractTest {

    @Test
    void proxySendsRequestOverActualHttpTransport() {
        WireMockServer server =
                new WireMockServer(wireMockConfig().dynamicPort());
        server.start();
        try {
            server.stubFor(get(urlEqualTo(
                    "/v1/inventory/SKU-42?warehouse=HCM"))
                    .withHeader("X-Correlation-Id",
                            equalTo("trace-wire"))
                    .willReturn(okJson(
                            """
                            {"sku":"SKU-42","available":5}
                            """)));

            RestClient restClient = RestClient.builder()
                    .baseUrl(server.baseUrl())
                    .build();

            InventoryHttpApi client = HttpServiceProxyFactory
                    .builderFor(RestClientAdapter.create(restClient))
                    .build()
                    .createClient(InventoryHttpApi.class);

            StockDto reply =
                    client.getStock("SKU-42", "HCM", "trace-wire");

            assertThat(reply.available()).isEqualTo(5);
            server.verify(1, getRequestedFor(urlEqualTo(
                    "/v1/inventory/SKU-42?warehouse=HCM")));
        } finally {
            server.stop();
        }
    }
}
~~~

Các lợi ích so với mock ở tầng RestClient:

- Đã mở một listener HTTP thật trên port động.
- Client sử dụng request factory/transport thật để gửi qua network stack local.
- Kiểm tra serialization, request target, header và response decode qua đường thực hơn.
- Có thể mô phỏng HTTP 429, 503, delay, connection reset hoặc body lỗi bằng các tính năng stub/fault injection của server.

**Giới hạn:** HTTP stub local vẫn không mô phỏng hoàn chỉnh DNS, ingress/reverse proxy, mTLS, service mesh, retry của load balancer hoặc provider thật. Với những điểm thuộc chính sách hạ tầng, cần integration environment hoặc end-to-end test gần production.

## 11. Timeout và retry: dùng transport test và biết kết quả có thể chưa rõ

Một request bị timeout không chứng minh server chưa chạy. Đặc biệt với `reserve`, server có thể đã tạo reservation rồi TCP response thất lạc.

Ví dụ cấu hình RestClient dùng request factory với timeout giới hạn:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(300); // milliseconds
requestFactory.setReadTimeout(700);    // milliseconds

RestClient restClient = RestClient.builder()
        .baseUrl("https://inventory.internal.example")
        .requestFactory(requestFactory)
        .build();
~~~

Giá trị chỉ để minh họa và phụ thuộc môi trường. `connectTimeout` giới hạn bước kết nối; `readTimeout` giới hạn đọc từ transport, không nhất thiết là **deadline toàn bộ nghiệp vụ**. Các transport khác như Apache HttpClient, JDK HttpClient hoặc Reactor Netty có API và semantics khác. Với ứng dụng có yêu cầu SLA nghiêm ngặt, thêm ngân sách tổng ở tầng orchestration, tránh dựa vào một timeout của socket.

### Test timeout có kiểm soát

Dùng WireMock trả response chậm hơn thời hạn đọc:

~~~java
server.stubFor(get(urlEqualTo(
        "/v1/inventory/SKU-42?warehouse=HCM"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(2000)
                .withHeader("Content-Type", "application/json")
                .withBody(
                    """
                    {"sku":"SKU-42","available":5}
                    """)));
~~~

Proxy của test phải được tạo từ `RestClient` có **read timeout thấp hơn 2000 ms**. Sau khi gọi và bắt exception, kiểm tra cả thời gian hợp lý và loại lỗi transport theo request factory đang dùng; không assert chuỗi message phụ thuộc hệ điều hành hoặc exception nội bộ quá cụ thể.

Không test retry bằng cách tạo 10 lần `WireMockServer` trong một test, hoặc bằng `Thread.sleep` vô hạn. Tạo một scenario có số attempt đo được, đặt timeout ngắn, đóng server sau test và assert tổng attempt/backoff trong ngân sách.

### Bộ kiểm thử retry đáng tin cậy

Các assertion cần kiểm tra:

1. **Lỗi được retry** chỉ khi exception/status thuộc danh sách được cho phép.
2. **Số lần retry** hữu hạn; ví dụ tối đa hai lần retry sau lần đầu.
3. **Idempotency-Key** không thay đổi giữa các attempt của cùng business command.
4. **Payload** không bị tạo lại với object ID ngẫu nhiên hoặc timestamp mới khiến mỗi attempt thành một command khác.
5. **Thời gian tổng** không vượt SLA của caller dù nhiều tầng đều có retry.
6. Lỗi 400/401/403/422 không bị retry mù.
7. Server thành công nhưng response mất **không tạo side effect thứ hai** nếu caller retry.
8. Khi circuit breaker mở, caller nhận fallback/lỗi đã thiết kế chứ không treo.

Một số bộ thư viện thêm retry tại `RestClient`, service layer, API gateway và messaging listener. Nếu mỗi lớp tự retry, số HTTP attempt có thể nhân nhau; test phải đếm **request thực tế tại stub server**, không chỉ số lần gọi method Java ở service.

## 12. WebClient-backed HTTP interface: kiểm thử reactive return types

Trong ứng dụng WebFlux, `HttpServiceProxyFactory` có thể sử dụng `WebClientAdapter`:

~~~java
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

WebClient webClient = WebClient.builder()
        .baseUrl("https://inventory.internal.example")
        .build();

var reactiveProxy = HttpServiceProxyFactory
        .builderFor(WebClientAdapter.create(webClient))
        .build()
        .createClient(ReactiveInventoryHttpApi.class);
~~~

Interface reactive:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange(url = "/v1/inventory", accept = "application/json")
public interface ReactiveInventoryHttpApi {

    @GetExchange("/{sku}")
    Mono<StockDto> getStock(@PathVariable("sku") String sku);
}
~~~

Kiểm thử qua WireMock socket thật và `StepVerifier`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static reactor.test.StepVerifier.*;

import reactor.core.publisher.Mono;

Mono<StockDto> result = reactiveProxy.getStock("SKU-42");

create(result)
        .assertNext(stock -> {
            assertThat(stock.sku()).isEqualTo("SKU-42");
            assertThat(stock.available()).isEqualTo(5);
        })
        .verifyComplete();
~~~

Ví dụ `reactiveProxy` cần được tạo với WebClient trỏ vào stub server thực tế trong test, không trỏ production. `StepVerifier` cung cấp **subscription** và verify sequence. Nếu test chỉ tạo `Mono` rồi không subscribe, HTTP request có thể chưa thực sự được gửi.

### Khác biệt về completion và cancellation

Với `Mono<T>`, test cần xác minh success, error và cancellation/timeout phù hợp. Với `Flux<T>` server streaming, phải kiểm tra số phần tử, thứ tự, completion hoặc stream chạy lâu không hoàn tất, backpressure và việc hủy subscription. Một test dùng `block()` để “xem có data” không thay được test reactive contract.

Khi hủy subscription, client có thể hủy network request nhưng **không đảm bảo** side effect đã bắt đầu trên server bị rollback. Quy tắc idempotency vẫn áp dụng cho thao tác ghi.

### Tránh block trên event loop

Không dùng `RestClient` đồng bộ bên trong WebFlux request handler trên Netty event loop mà không có scheduling/bulkhead phù hợp. `HttpServiceProxyFactory` tạo proxy không tự chuyển code blocking thành non-blocking; backend adapter và kiểu trả về quyết định cách thực thi.

## 13. Kiểm thử từ phía provider: hợp đồng có còn đúng không?

Client test chứng minh proxy đã phát ra request theo kỳ vọng của consumer, nhưng provider có thể đã đổi:

- `/v1/inventory/{sku}` thành `/inventory/{sku}`;
- `warehouse` thành `warehouseId`;
- `available` từ số thành chuỗi;
- 201 Created thành 202 Accepted;
- 409 Conflict thành 422;
- một field mới bắt buộc trong request;
- quy tắc authentication, authorization, ETag hoặc rate limit.

**Provider contract test** kiểm tra API thực thi phía server tương thích với hợp đồng. Có hai cách tiếp cận hữu ích.

### 13.1. Test controller/server dựa trên hợp đồng API

Nếu provider là Spring MVC:

~~~java
@RestController
@RequestMapping("/v1/inventory")
public class InventoryController {

    @GetMapping("/{sku}")
    public StockDto getStock(
            @PathVariable String sku,
            @RequestParam String warehouse) {
        return stockService.find(sku, warehouse);
    }
}
~~~

Test MVC có thể dùng `MockMvc` để kiểm tra route, query và response JSON:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(InventoryController.class)
class InventoryProviderContractTest {

    @Autowired MockMvc mvc;

    @Test
    void servesDocumentedGetStockContract() throws Exception {
        mvc.perform(get("/v1/inventory/SKU-42")
                    .param("warehouse", "HCM"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        org.springframework.http.MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("SKU-42"))
                .andExpect(jsonPath("$.available").isNumber());
    }
}
~~~

Đoạn này giả định provider có cấu hình/mock `stockService` trả fixture ổn định và security/filter được thiết lập phù hợp; nếu không có bean, `@WebMvcTest` cần `@MockBean`/`@MockitoBean` hoặc cấu hình test fixture theo phiên bản Boot. Đây là phác thảo test provider, không phải source hoàn chỉnh của ứng dụng. Nếu test chỉ mock controller trả đúng JSON mà production service mapping khác, vẫn cần một số test chạy qua service layer/database/serialization thực.

### 13.2. Consumer-driven contract (CDC)

Với Spring Cloud Contract hoặc Pact, consumer mô tả request/response mà mình thật sự cần. Provider chạy verification để chứng minh implementation hiện tại thỏa các expectation đó. Quy trình điển hình:

~~~mermaid
flowchart TD
    C["Consumer: định nghĩa contract/stub"] --> AR["Contract artifact/version"]
    AR --> P["Provider: verify contract"]
    P --> CI["Provider CI gate"]
    AR --> CT["Consumer: proxy tests với stub"]
    CT --> CC["Consumer CI gate"]
    CI --> DEP{"Cho phép deploy?"}
    CC --> DEP
~~~

Điểm cần lưu ý:

- **Contract test không thay thế test proxy** nếu consumer test gọi stub qua một HTTP client khác với client thật. Luôn để ít nhất một test gửi request qua `InventoryHttpApi` proxy thực.
- Contract artifact cần được **version hóa** cùng provider/consumer. Một bản hợp đồng luôn trỏ “latest” có thể khiến CI không tái hiện được kết quả.
- Provider verification phải chạy với auth, validation và serializer gần thực tế, không chỉ trả mock object từ endpoint giả.
- Với tương thích ngược, verify provider mới đáp ứng những consumer version đang triển khai, không chỉ consumer source mới nhất.
- Không cất secret thật hoặc PII vào contract examples, stub recordings hay CI logs.

**OpenAPI specification** cũng hữu ích để tạo/đối chiếu HTTP schema. Nhưng OpenAPI và Java `@HttpExchange` không tự sinh ra bảo đảm tương thích lẫn nhau nếu không có test hoặc công cụ xác minh rõ ràng. Một file OpenAPI cập nhật không đồng nghĩa server đã deploy code tương ứng.

## 14. Hợp đồng dữ liệu: kiểm tra cấu trúc và ngữ nghĩa, không chỉ DTO

Hai JSON có thể cùng deserialize thành một DTO nhưng biểu diễn kết quả nghiệp vụ khác nhau:

~~~json
{"sku":"SKU-42","available":0}
~~~

và:

~~~json
{"sku":"SKU-42","available":-1}
~~~

Cả hai đều hợp kiểu `int`, nhưng số lượng âm có thể vi phạm domain contract. Vì vậy cần phân lớp:

| Loại hợp đồng | Ví dụ | Test nên làm gì? |
| --- | --- | --- |
| Cú pháp HTTP | Method, path, query, Content-Type | Assert request trên wire |
| Schema | Required/optional field, type, enum | Decode và schema validation |
| Ngữ nghĩa | `available >= 0`, `quantity > 0` | Domain validation/fixtures |
| Tương thích phiên bản | Thêm field optional, đổi enum | Matrix consumer cũ/mới |
| Phân quyền | Caller không được xem SKU tenant khác | Security contract tests |
| Trạng thái | 201 vs 202, 204 vs 200 | Assert status và ý nghĩa response |
| Tính lặp lại | Idempotency-Key cùng command | Server không tạo reservation hai lần |
| Nhất quán | DB commit và response/HTTP retry | Inject lỗi sau commit, kiểm tra kết quả |

Đặc biệt với numeric data, `double` không thích hợp cho tiền; dữ liệu thời gian phải có timezone/precision và cách encode thống nhất. Với object khác nhau bởi null vs missing, test cả hai. Consumer tolerant với unknown fields không được bỏ qua validation của field **bắt buộc**.

### Chính sách thay đổi contract

Một thay đổi thường **tương đối an toàn** nếu thêm optional response field và consumer cũ bỏ qua unknown fields. Nhưng không thể khẳng định an toàn với mọi consumer (một số decoder nghiêm ngặt). Những thay đổi như đổi path, HTTP verb, xóa field, đổi enum, thay ý nghĩa status hoặc bắt buộc header mới thường cần migration/versioning.

Test suite nên chứa **fixture của version đã chạy production** để phát hiện compatibility drift. Nếu provider dùng blue-green/canary, cần đảm bảo trong giai đoạn trộn phiên bản, tất cả consumer vẫn xử lý được response từ cả hai bản provider.

## 15. Proxy không nằm trong cùng database transaction với remote server

Một method của Spring service có thể được annotate `@Transactional`:

~~~java
@Transactional
public ReservationDto reserveForOrder(ReserveCommand command) {
    orderRepository.markReserving(command.orderId());
    return inventoryHttpApi.reserve(
            command,
            stableIdempotencyKey(command),
            currentTraceId());
}
~~~

**Spring local JDBC transaction không bao trùm HTTP request**. Một số failure mode:

1. DB transaction đã mở, HTTP reserve thành công, sau đó DB commit thất bại → inventory đã giữ chỗ nhưng order SQL rollback.
2. HTTP reserve đã commit ở server, response bị timeout → client có thể retry và tạo reservation thứ hai nếu không có idempotency.
3. DB commit thành công nhưng một bước HTTP sau đó lỗi → cần reconciliation hoặc compensation.
4. Giữ DB transaction/lock khi chờ HTTP lâu khiến connection pool bị cạn và tăng nguy cơ deadlock.

Giải pháp kiến trúc thường là phân tách các pha:

- Ghi trạng thái `PENDING_RESERVATION` và outbox trong SQL transaction ngắn.
- Worker lấy job, gọi proxy với **idempotency key cố định** theo business operation.
- Server inventory ghi biên nhận theo `(callerId, idempotencyKey)` cùng transaction tạo reservation.
- Worker cập nhật trạng thái `RESERVED` hoặc `RETRY_PENDING`, có recovery/reconciliation.
- Khi không thể tiếp tục, thực hiện bù trừ theo business contract thay vì kỳ vọng HTTP rollback.

Một integration test đủ sâu cần **chủ động làm mất response sau khi provider đã commit**, rồi retry cùng key và assert chỉ một reservation được tạo. Mock method trả exception không kiểm tra được cửa sổ lỗi này.

### Hợp đồng của một lần retry

Test phải bảo đảm:

- Không tạo lại `orderId`, `requestId`, idempotency key mới mỗi attempt.
- Retry chỉ xảy ra với loại lỗi được cho phép và trong tổng deadline.
- Provider lưu kết quả của command đầu tiên để trả lại cho retry trùng, kể cả khi client mất response.
- Duplicate request đồng thời được bảo vệ bằng unique constraint/lock chứ không chỉ `SELECT` trước `INSERT`.
- Nếu broker/outbox cũng retry, tổng số attempt vẫn được giới hạn và đo được.

## 16. Bảo mật, cấu hình và quan sát proxy trong production

Một proxy đúng hợp đồng chức năng vẫn có thể không an toàn nếu được khởi tạo sai base URL, gửi nhầm credential hoặc để lộ dữ liệu trong logs.

### Cấu hình môi trường

~~~yaml
app:
  inventory:
    base-url: https://inventory.internal.example
    connect-timeout: 500ms
    read-timeout: 2s
~~~

`connect-timeout` và `read-timeout` ở đây là **application properties do dự án định nghĩa**; Spring Boot không tự áp dụng chúng cho mọi proxy chỉ vì chúng tồn tại dưới prefix `app.inventory`. Cần có `@ConfigurationProperties` và cấu hình request factory/client connector tương ứng.

Để phát hiện sai cấu hình sớm, validate URL scheme/host, timeout dương và format endpoint ở startup. Tránh cho request từ người dùng tự ghi đè base URL tùy ý (nguy cơ SSRF). Với nhiều provider, dùng bean names/qualifiers và test rằng proxy inventory không gửi `Authorization` dành cho payment service.

### Log/tracing/metrics

Một yêu cầu đi qua:

~~~mermaid
sequenceDiagram
    participant U as Checkout API
    participant P as HTTP Interface Proxy
    participant N as RestClient/WebClient
    participant S as Inventory Provider
    U->>P: getStock(SKU-42, HCM, traceId)
    P->>N: GET path + query + headers
    N->>S: HTTP request, trace context
    S-->>N: 200 JSON / 409 / 503
    N-->>P: DTO / exception / reactive signal
    P-->>U: Business result hoặc failure
~~~

Nên theo dõi:

- `client.name`, `peer.service`, operation/route template, HTTP method, status category.
- Latency p50/p95/p99, connect/read timeout, retry attempts, in-flight calls.
- Error class (HTTP 4xx vs 5xx vs network vs deserialization).
- Circuit breaker state, fallback rate, số lần auth refresh.
- Idempotency duplicate hits và số command có kết quả “unknown outcome”.
- Version consumer/provider, contract verification failures trong CI.

Nếu dùng Spring Boot Actuator/Micrometer/Observation, kiểm tra instrumentation thực sự gắn trên `RestClient.Builder` hoặc `WebClient.Builder` đang dùng. Tạo builder thủ công mà không giữ Boot customizer có thể làm mất metrics/tracing mặc dù proxy vẫn hoạt động.

Không tạo metric tag có `orderId`, `sku` không giới hạn, user ID hoặc full URL có query string: dễ tăng cardinality và lộ dữ liệu. Dùng route template, tên provider và status category. Không log Bearer token, API key hoặc toàn bộ payload khách hàng.

### Security tests cần có

- Không gửi token sang host khác do redirect không được phép.
- TLS certificate và trust chain được xác minh; không tắt validation để qua môi trường test.
- Header `Authorization` không xuất hiện trong error message/trace/log.
- Không cho caller điều khiển URL tuyệt đối nếu interface có `URI` override hoặc dynamic URL input.
- Request size, response size và thời gian đọc được giới hạn theo SLA.
- Provider xác thực và phân quyền thật; correlation ID/idempotency key không phải token chứng minh identity.

## 17. Ma trận kiểm thử đầy đủ cho HTTP interface proxy

Một ma trận chuẩn có thể dùng khi review pull request:

| Nhóm | Trường hợp | Lớp test thích hợp |
| --- | --- | --- |
| Mapping | GET đúng verb, prefix, path variable | MockRestServiceServer |
| Query | Khoảng trắng, Unicode, list, optional, null | Mock + WireMock khi có encoding đặc biệt |
| Header | Accept, Content-Type, auth, correlation | MockRestServiceServer |
| Request body | DTO JSON đúng field/type, null/unknown | MockRestServiceServer |
| Response body | 200/201 decode đúng DTO | MockRestServiceServer |
| Empty response | 204 với `void`, body rỗng bất ngờ | MockRestServiceServer |
| Error status | 400/401/403/404/409/422/429/503 | Mock + provider contract |
| Error payload | `application/problem+json`, field/version | Mock + provider verification |
| Connect/read timeout | Server delay, unreachable port | WireMock / transport test |
| TLS/redirect/proxy | Hostname, certificate, redirects | Integration environment |
| Retry | Giới hạn attempt, backoff, stable key | WireMock scenario + provider state |
| Auth rotation | Token hết hạn/refreshed, đúng audience | Integration/security contract |
| Reactive | Mono/Flux success, error, cancel, demand | WireMock + StepVerifier |
| Provider compatibility | Consumer cũ/vừa, response mới/cũ | CDC/OpenAPI + provider test |
| Data consistency | Remote commit nhưng response mất | Full integration/fault injection |
| DB/broker boundary | Transaction outbox, duplicate message | Integration + database thật |
| Observability | Trace propagation, route tags, safe logging | Integration instrumentation test |

Không phải mọi ô đều phải là một bài test end-to-end cực nặng. Phân chia hợp lý:

- Nhiều test nhanh ở tầng proxy/mock để bắt lỗi mapping.
- Một số test HTTP socket thật cho timeout, transport, streaming và retry.
- Provider contract verification mỗi lần provider thay đổi.
- Ít bài test end-to-end có fault injection cho hành vi cực kỳ quan trọng.

## 18. Pipeline CI và quy trình phát hiện contract drift

Một CI hiệu quả tách nhanh/chậm và bảo đảm lỗi contract được phát hiện trước deploy:

~~~mermaid
flowchart TD
    A["Pull request consumer"] --> B["Compile + static contract review"]
    B --> C["Proxy tests / MockRestServiceServer"]
    C --> D["WireMock transport tests"]
    D --> E["Consumer contract artifact versioned"]
    E --> F["Provider CI contract verification"]
    F --> G{"Compatible with deployed consumers?"}
    G -->|Có| H["Release/canary + smoke test"]
    G -->|Không| I["Block deploy / version API / expand-contract"]
~~~

Thực hiện:

1. **Consumer** cập nhật interface và test expected HTTP request/response cùng pull request.
2. Lưu contract artifact/fixtures có version hoặc commit hash, tránh test chỉ dùng một stub “mới nhất” thay đổi ngầm.
3. **Provider** verify các contract mà các consumer đang chạy cần, không chỉ bản consumer source mới nhất.
4. Khi provider thay đổi schema, dùng chiến lược **expand-contract**: thêm khả năng mới tương thích trước, rollout consumers, rồi mới loại bỏ hợp đồng cũ.
5. Với thay đổi lớn về status/route/security, phát hành API version mới hoặc có giai đoạn phục vụ song song.
6. Canary/smoke test sau deploy quan sát 4xx/5xx, deserialize errors, timeout, retry rate và compatibility.
7. Giữ một số fixture response lỗi trong repository kiểm thử và cập nhật có review; không tự ghi đè snapshots rồi coi tất cả thay đổi là hợp lệ.

**Một test proxy pass trong CI consumer không có nghĩa provider hiện tại đang triển khai đúng hợp đồng**. Cần kết nối CI bằng contract verification, hoặc một số integration test chạy against staging/prod-like environment.

## 19. Troubleshooting: proxy compile được nhưng gọi sai

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| 404 dù provider vẫn sống | Prefix URL, route version, path variable encoding sai | Assert request URL ở proxy test, so với route provider |
| Provider nhận sai query | `@RequestParam` tên khác, list/encoding không khớp | WireMock exact query, provider contract |
| 415 Unsupported Media Type | `Content-Type` không đúng, converter thiếu | Inspect request header/body, cấu hình codec |
| 406 Not Acceptable | `Accept` không được provider hỗ trợ | Test declared media type và provider |
| 400 do body thiếu field | DTO serialization, null/default policy khác | Strict JSON fixture và provider validation |
| 401/403 | Token thiếu/sai audience, scope, tenant | Assert auth header đúng destination; security logs an toàn |
| 409 bị coi là lỗi transport retryable | Catch exception quá rộng | Assert `HttpClientErrorException.Conflict`, map domain |
| 503 lặp vô hạn | Retry ở nhiều tầng không có budget | Đếm request thực ở WireMock/metrics |
| Proxy test pass nhưng real network timeout | Test mock không dùng socket/timeout thực | Thêm WireMock delay và request factory timeout |
| Mono trả về nhưng request không xuất hiện | Không có subscriber | StepVerifier/subscription test |
| 204 làm DTO null | Return type không phản ánh empty response | Assert response contract 204 và mapper |
| Response thêm enum value làm decode lỗi | Consumer strict enum/DTO chưa tương thích | Consumer/provider schema compatibility tests |
| Hợp đồng không bị phát hiện khi provider đổi | Chỉ mock interface ở unit test, không có CDC | Tạo contract artifacts và verify provider |
| HTTP POST chạy hai lần sau timeout | Retry command thiếu stable Idempotency-Key | Test mất response sau commit + unique receipt |
| Metrics/tracing trống | Dùng builder không có Boot customizer | Test observation từ RestClient.Builder/WebClient.Builder |
| Connection pool cạn | Quên giới hạn concurrency/timeouts, response stream chưa đóng | Pool metrics, thread dump, transport tests |
| Proxy gửi sai backend | Base URL do profile/config hoặc bean qualifier sai | Assert host trong test, validate environment |

### Quy trình chẩn đoán có thứ tự

1. Đọc **wire contract** mong đợi: method, URL, query, headers, body, status và schema.
2. Xác minh test thực sự gọi **`HttpServiceProxyFactory` proxy**, không gọi Mockito mock.
3. Quan sát request qua `MockRestServiceServer` và WireMock, kiểm tra loại adapter/backend đang dùng.
4. Nếu contract client đúng nhưng provider trả lỗi, kiểm tra provider routes, validation, auth và version thật.
5. Nếu chỉ lỗi ngoài test, kiểm tra DNS, TLS, ingress, redirect, pooling, timeout và instrumentation.
6. Với request ghi có kết quả không rõ, xem database/idempotency receipts trước khi retry hoặc bù trừ.
7. Chốt regression test ở **đúng lớp gây lỗi**, tránh chỉ thêm sleep hoặc tăng timeout không căn cứ.

## 20. Checklist trước khi đưa HTTP interface proxy vào production

- Interface có đường dẫn, HTTP method, media types, tham số, DTO và return type phản ánh API được provider hỗ trợ.
- Proxy được tạo từ `HttpServiceProxyFactory` và đúng adapter `RestClientAdapter`/`WebClientAdapter` theo execution model.
- Ít nhất một **proxy test thật** xác nhận method + URL + query + headers + body + response/exception; không chỉ mock Java interface.
- Test các URL chứa ký tự đặc biệt, list query, body nullable/optional và empty response.
- Có ma trận 4xx/5xx, error body và exception/domain mapping rõ ràng; không biến mọi lỗi thành retryable.
- Có test transport thật cho connection/read timeout, redirect/TLS/ingress khi liên quan, và test publisher reactive có subscription.
- Có hợp đồng đồng thuận với provider (OpenAPI/CDC) và provider verification để phát hiện drift khi deploy.
- Retry có giới hạn, deadline tổng và idempotency key ổn định; các thao tác ghi không được nhân đôi khi response mất.
- Không coi HTTP request là một phần local SQL transaction; dùng outbox, state machine và reconciliation khi cần.
- Cấu hình auth, base URL, timeout, pool, observation theo environment; không lộ credentials/PII trong logs/metrics.
- CI giữ contract fixtures versioned, verify consumer/provider compatibility và có test canary/smoke sau deploy.

### Tài liệu đối chiếu phiên bản

- [Spring Framework Reference – HTTP Interface](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface): annotation `@HttpExchange`, `@GetExchange`, proxy và client adapters.
- [Spring Framework API – HttpServiceProxyFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html): tạo proxy và hỗ trợ resolver.
- [Spring Framework Reference – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, codec và error handling.
- [Spring Framework Reference – MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): test RestClient/RestTemplate với mock request expectations.
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer-driven/provider contract và sinh stubs.
- [WireMock Documentation](https://wiremock.org/docs/): HTTP stub, request matching, fault injection.
- [Pact Documentation](https://docs.pact.io/): consumer-driven contract và provider verification.

**Ghi nhớ:** **Annotation là lời hứa**, **proxy trên wire là hành vi thực tế**, còn **provider verification là bằng chứng tương thích**. Chỉ khi kiểm tra được cả ba, và bao quát thêm timeout, error mapping, idempotency, quyền truy cập, cùng ranh giới SQL/broker, HTTP interface mới đủ tin cậy cho luồng tích hợp Spring Boot.

