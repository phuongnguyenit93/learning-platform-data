# Tạo phản hồi thành công, lỗi và dữ liệu không hợp lệ

Khi kiểm thử HTTP client, chỉ kiểm tra một response `200 OK` là chưa đủ. Client cần xử lý đúng nhiều kết quả từ dịch vụ bên ngoài: dữ liệu hợp lệ, lỗi nghiệp vụ `4xx`, lỗi máy chủ `5xx`, response có cấu trúc sai, dữ liệu không thỏa mãn quy tắc nghiệp vụ và cả trường hợp không nhận được response do lỗi kết nối.

Các bài test này nên điều khiển response từ một HTTP server giả lập. Test gửi request qua HTTP client thật của ứng dụng, sau đó server giả trả status, header và body đã định trước. Cách làm đó kiểm tra được URL, method, header, serialization, deserialization và chính sách xử lý lỗi của client trong cùng một luồng.

Spring cung cấp `MockRestServiceServer` cho `RestTemplate` và `RestClient`. Với `WebClient`, có thể dùng MockWebServer hoặc WireMock để tạo một HTTP server cục bộ. Ngoài ra, có thể mock trực tiếp `ExchangeFunction`, nhưng cách đó kiểm tra ở mức thấp hơn và không xác nhận đầy đủ việc client tạo HTTP request qua transport.

## 1. Phân loại response cần kiểm thử

Giả sử ứng dụng có một HTTP client để đọc thông tin tồn kho từ dịch vụ Inventory. Một request có thể nhận các nhóm kết quả sau:

| Kịch bản | Response hoặc tình huống | Điều client cần làm |
|---|---|---|
| Thành công | `200 OK` với JSON hợp lệ | Deserialize đúng DTO và trả dữ liệu cho tầng gọi. |
| Tạo mới thành công | `201 Created` cùng `Location` và body | Đọc dữ liệu mới tạo và giữ metadata cần thiết. |
| Không có nội dung | `204 No Content` | Xử lý body rỗng theo hợp đồng. |
| Request không hợp lệ | `400 Bad Request` với lỗi validation | Chuyển thành lỗi đầu vào hoặc lỗi domain có ý nghĩa. |
| Không tìm thấy | `404 Not Found` | Chuyển thành lỗi không tồn tại hoặc kết quả vắng mặt theo thiết kế. |
| Không được phép | `401` hoặc `403` | Báo lỗi xác thực/phân quyền, không coi là thành công. |
| Dịch vụ gặp sự cố | `500`, `502`, `503`, `504` | Phát sinh lỗi upstream và áp dụng retry/fallback nếu chính sách cho phép. |
| JSON sai định dạng | `200 OK` nhưng body không parse được | Báo lỗi decode, không tạo DTO giả hoặc dữ liệu mặc định. |
| JSON hợp lệ nhưng sai nghiệp vụ | `200 OK` nhưng trường bắt buộc thiếu hoặc giá trị ngoài miền hợp lệ | Từ chối dữ liệu không hợp lệ trước khi dùng cho nghiệp vụ. |
| Lỗi transport | DNS, connection refused, reset hoặc timeout | Xử lý lỗi kết nối riêng với HTTP status. |

Nên tạo từng response theo một mục tiêu cụ thể. Ví dụ `404` không tương đương `500`; JSON sai định dạng trong response `200` cũng khác với một response `400` báo request của client không hợp lệ.

## 2. Tạo response giả bằng MockRestServiceServer

`MockRestServiceServer` là công cụ thuộc Spring Test để kiểm thử code sử dụng `RestTemplate` hoặc `RestClient`. Nó gắn vào request factory của client và cho phép khai báo kỳ vọng về request, sau đó trả về response giả mà không cần mở cổng HTTP thật.

Ví dụ DTO và client đọc tồn kho:

```java
public record InventoryItem(long id, String sku, int availableQuantity) {
}
```

Với Spring Framework 6.1 trở lên, `MockRestServiceServer` có thể bind vào `RestClient.Builder`:

```java
import org.springframework.web.client.RestClient;

class InventoryClient {

    private final RestClient restClient;

    InventoryClient(RestClient restClient) {
        this.restClient = restClient;
    }

    InventoryItem findById(long id) {
        return restClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Tạo builder trước, bind mock server vào builder, rồi mới build client:

```java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://inventory.example.test");

MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
RestClient restClient = builder.build();

InventoryClient inventoryClient = new InventoryClient(restClient);
```

Việc bind vào builder bảo đảm request của `RestClient` đi qua request factory do `MockRestServiceServer` kiểm soát. Nếu build client trước rồi mới tạo mock server theo một builder khác, client sẽ không tự động dùng cấu hình mock đó.

## 3. Response thành công

Kịch bản cơ bản nhất là server trả `200 OK`, `Content-Type: application/json` và JSON có cấu trúc khớp với DTO.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryClientTest {

    @Test
    void mapsSuccessfulJsonResponseToInventoryItem() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.example.test");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        InventoryClient client = new InventoryClient(builder.build());

        server.expect(requestTo("https://inventory.example.test/inventory/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "id": 42,
                          "sku": "BOOK-42",
                          "availableQuantity": 12
                        }
                        """, MediaType.APPLICATION_JSON));

        InventoryItem item = client.findById(42);

        assertThat(item.id()).isEqualTo(42);
        assertThat(item.sku()).isEqualTo("BOOK-42");
        assertThat(item.availableQuantity()).isEqualTo(12);
        server.verify();
    }
}
```

Test xác nhận nhiều điều cùng lúc:

- Client gọi đúng URL và dùng đúng HTTP method.
- Response `200` được đọc như JSON.
- Các trường JSON được ánh xạ vào đúng thuộc tính DTO.
- `server.verify()` xác nhận tất cả request expectation đã được thực hiện.

Không nên chỉ assert rằng `item` khác `null`. Assertion theo từng trường giúp phát hiện sai tên thuộc tính, sai kiểu dữ liệu hoặc mapping không đúng.

### Kiểm tra header của request và response

Nếu client cần gửi API version hoặc authorization header, có thể thêm matcher:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header("Accept", MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header("X-Client-Name", "order-service"))
        .andRespond(withSuccess("""
                {"id":42,"sku":"BOOK-42","availableQuantity":12}
                """, MediaType.APPLICATION_JSON));
```

Nếu cần kiểm tra response header như `ETag` hoặc `Location`, `MockRestServiceServer` có các response creator hoặc builder cho phép thêm header. Điều quan trọng là kiểm tra metadata mà client thực sự sử dụng, không chỉ body.

## 4. Response lỗi HTTP

Mặc định, `RestClient.retrieve()` chuyển response `4xx` và `5xx` thành exception thuộc nhóm `RestClientResponseException`, trừ khi code cấu hình `onStatus(...)` để xử lý riêng. `RestTemplate` cũng có `ResponseErrorHandler` mặc định để chuyển các status lỗi thành exception.

### Kiểm tra 404 Not Found

Ví dụ server trả `404` cùng body JSON mô tả lỗi:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

import org.springframework.http.HttpStatus;

server.expect(requestTo("https://inventory.example.test/inventory/999"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"code":"ITEM_NOT_FOUND","message":"Item 999 does not exist"}
                        """));

assertThatThrownBy(() -> client.findById(999))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

server.verify();
```

Trong test thực tế, `client` phải được tạo với builder đã bind vào `server` như phần trước. Assertion exception xác nhận client không coi response lỗi là một DTO thành công.

Nếu ứng dụng có quy ước chuyển `404` thành `Optional.empty()` hoặc `ItemNotFoundException`, hãy kiểm tra quy ước đó thay vì luôn mong đợi exception mặc định. Ví dụ client có thể khai báo:

```java
InventoryItem findById(long id) {
    return restClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    (request, response) -> {
                        throw new ItemNotFoundException(id);
                    })
            .body(InventoryItem.class);
}
```

Khi đó test nên xác nhận `ItemNotFoundException`, có thể kiểm tra thêm id và thông tin nguyên nhân nếu exception giữ lại response body.

### Kiểm tra lỗi 400 và lỗi validation

Response `400 Bad Request` thường biểu thị dữ liệu request không hợp lệ. Nếu API bên ngoài trả mã lỗi ổn định, client có thể chuyển mã đó thành lỗi domain:

```json
{
  "code": "INVALID_QUANTITY",
  "message": "quantity must be greater than zero",
  "field": "quantity"
}
```

Test cần xác nhận status và cách client diễn giải body lỗi. Nếu client giữ nguyên `RestClientResponseException`, có thể kiểm tra status và response body trong exception. Nếu client chuyển thành exception riêng, hãy kiểm tra mã lỗi và field được trích xuất.

Không nên giả định mọi `400` đều có JSON hợp lệ. Dịch vụ có thể trả body rỗng, HTML từ gateway hoặc một schema lỗi khác. Client cần có chính sách rõ ràng khi không parse được error body; bài test nên bao phủ trường hợp đó nếu hệ thống có thể gặp.

### Kiểm tra lỗi 5xx

Server có thể trả `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` hoặc `504 Gateway Timeout`. Có thể tạo các status này bằng `withStatus(...)`:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"code":"INVENTORY_UNAVAILABLE"}
                        """));

assertThatThrownBy(() -> client.findById(42))
        .isInstanceOf(HttpServerErrorException.ServiceUnavailable.class);
```

Nếu client có retry, không chỉ assert exception cuối cùng. Cần xác nhận số lần gọi, khoảng backoff hoặc request cuối cùng đã thành công sau một số lần lỗi. Khi không có retry policy, một response `503` thường nên được truyền thành lỗi rõ ràng để tầng trên quyết định.

## 5. Phản hồi thành công nhưng JSON sai định dạng

Một trường hợp quan trọng là server trả status `200 OK` nhưng body không thể deserialize thành DTO. Đây là lỗi dữ liệu response, không phải lỗi status HTTP.

Ví dụ JSON bị cắt cụt:

```json
{"id":42,"sku":"BOOK-42",
```

Test với `MockRestServiceServer`:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withSuccess(
                "{\"id\":42,\"sku\":\"BOOK-42\",",
                MediaType.APPLICATION_JSON));

assertThatThrownBy(() -> client.findById(42))
        .isInstanceOf(RestClientException.class);

server.verify();
```

`RestClient` dùng `HttpMessageConverter` để đọc body. Khi JSON không hợp lệ hoặc không thể chuyển thành DTO, client thường ném `RestClientException` có nguyên nhân decode ở bên dưới. Nếu code ứng dụng có bọc exception thành lỗi domain, hãy assert loại exception và nguyên nhân theo hợp đồng của lớp client.

Không nên bắt mọi exception rồi trả một DTO rỗng hoặc giá trị mặc định. Làm vậy khiến dữ liệu hỏng trông giống dữ liệu thành công và có thể dẫn đến lỗi nghiệp vụ khó truy vết.

## 6. JSON hợp lệ nhưng dữ liệu không hợp lệ về nghiệp vụ

Không phải mọi payload sai đều là JSON sai cú pháp. Ví dụ body sau parse được hoàn toàn:

```json
{
  "id": 42,
  "sku": "BOOK-42",
  "availableQuantity": -5
}
```

Nhưng số lượng tồn kho âm có thể vi phạm hợp đồng của dịch vụ. Deserialize thành công không có nghĩa dữ liệu đáng tin cậy. Lớp HTTP client hoặc adapter cần kiểm tra các invariant mà ứng dụng phụ thuộc.

Ví dụ một client kiểm tra dữ liệu sau khi đọc:

```java
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    InventoryItem findById(long id) {
        InventoryItem item = restClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryItem.class);

        if (item == null || item.id() <= 0 || item.availableQuantity() < 0) {
            throw new InvalidInventoryResponseException(
                    "Inventory service returned invalid item data");
        }

        return item;
    }
}
```

Test tạo một response `200` nhưng chứa giá trị âm:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withSuccess("""
                {
                  "id": 42,
                  "sku": "BOOK-42",
                  "availableQuantity": -5
                }
                """, MediaType.APPLICATION_JSON));

assertThatThrownBy(() -> gateway.findById(42))
        .isInstanceOf(InvalidInventoryResponseException.class);
```

Các invariant nên được chọn theo hợp đồng thực tế: id phải dương, trường bắt buộc không được null, số lượng không âm, currency code hợp lệ hoặc trạng thái thuộc tập cho phép. Không nên tự đặt quy tắc nghiệp vụ không có trong hợp đồng dịch vụ.

### Phân biệt dữ liệu thiếu, null và sai kiểu

Ba payload sau có thể tạo ra ba hành vi khác nhau:

```json
{"id":42,"sku":"BOOK-42","availableQuantity":12}
```

```json
{"id":42,"sku":"BOOK-42"}
```

```json
{"id":"not-a-number","sku":"BOOK-42","availableQuantity":"many"}
```

Payload thứ nhất đầy đủ. Payload thứ hai thiếu trường; kết quả có thể là `null`, giá trị mặc định hoặc lỗi tùy DTO và cấu hình Jackson. Payload thứ ba sai kiểu dữ liệu và thường gây lỗi decode. Nếu trường bắt buộc phải tồn tại, hãy kiểm tra sau deserialize hoặc cấu hình mapping để phát hiện trường bị thiếu. Không dựa vào giá trị primitive mặc định như `0` để suy luận rằng server đã gửi trường đó.

## 7. Dùng MockWebServer để kiểm thử WebClient

`MockRestServiceServer` dành cho API đồng bộ `RestTemplate`/`RestClient`. `WebClient` dùng reactive HTTP connector và không sử dụng `ClientHttpRequestFactory` theo cùng cách. Một lựa chọn thực tế là MockWebServer của OkHttp: nó mở một server cục bộ, nhận request HTTP thật và trả response do test xếp hàng.

Thêm dependency test tương ứng với phiên bản OkHttp đang được dự án quản lý:

```groovy
testImplementation 'com.squareup.okhttp3:mockwebserver'
```

Ví dụ client reactive:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<InventoryItem> findById(long id) {
        return webClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
```

### Response thành công qua WebClient

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.StepVerifier;

class ReactiveInventoryClientTest {

    @Test
    void readsSuccessfulResponseAndSendsExpectedRequest() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("""
                            {"id":42,"sku":"BOOK-42","availableQuantity":12}
                            """));
            server.start();

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .build();
            ReactiveInventoryClient client = new ReactiveInventoryClient(webClient);

            StepVerifier.create(client.findById(42))
                    .assertNext(item -> {
                        assertThat(item.id()).isEqualTo(42);
                        assertThat(item.sku()).isEqualTo("BOOK-42");
                        assertThat(item.availableQuantity()).isEqualTo(12);
                    })
                    .verifyComplete();

            RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/inventory/42");
        }
    }
}
```

MockWebServer nhận request qua HTTP cục bộ, nên test có thể kiểm tra method, path, query, header và body thực sự được gửi. `StepVerifier` kiểm tra kết quả reactive mà không cần gọi `block()` trong test.

### Response lỗi qua WebClient

Mặc định, `retrieve()` chuyển response `4xx` hoặc `5xx` thành `WebClientResponseException`. Có thể kiểm tra status và body lỗi:

```java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"code":"ITEM_NOT_FOUND"}
                """));

StepVerifier.create(client.findById(999))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(WebClientResponseException.NotFound.class);
            WebClientResponseException responseError =
                    (WebClientResponseException) error;
            assertThat(responseError.getStatusCode().value()).isEqualTo(404);
            assertThat(responseError.getResponseBodyAsString())
                    .contains("ITEM_NOT_FOUND");
        })
        .verify(Duration.ofSeconds(2));
```

Nếu client dùng `onStatus(...)` để chuyển lỗi thành exception riêng, test cần xác nhận exception riêng đó. Ví dụ:

```java
Mono<InventoryItem> findById(long id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    response -> Mono.error(new ItemNotFoundException(id)))
            .bodyToMono(InventoryItem.class);
}
```

`onStatus` nhận predicate và hàm chuyển response thành `Mono<? extends Throwable>`. Việc chuyển lỗi tại adapter giúp các tầng nghiệp vụ không phải phụ thuộc vào chi tiết HTTP nếu đó là ranh giới kiến trúc của ứng dụng.

### JSON sai định dạng qua WebClient

MockWebServer cũng có thể trả `200` với JSON không hợp lệ:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,"));

StepVerifier.create(client.findById(42))
        .expectError()
        .verify(Duration.ofSeconds(2));
```

Trong test cụ thể, nên thay `expectError()` bằng assertion cho loại decode exception hoặc exception domain mà ứng dụng cam kết phát ra. Với WebClient, lỗi giải mã thường là `DecodingException` hoặc một exception được bọc trong lỗi reactive; loại cụ thể phụ thuộc codec và phiên bản. Nếu loại exception là một phần của hợp đồng public của client, hãy kiểm tra chính xác nó và nguyên nhân.

## 8. Dữ liệu request không hợp lệ và response 400

HTTP client cũng cần gửi dữ liệu đúng hợp đồng. Ví dụ client tạo request JSON với trường `quantity` bằng `0`, nhưng dịch vụ từ chối bằng `400 Bad Request`.

Với `RestClient`, test có thể kiểm tra body được gửi và response lỗi:

```java
server.expect(requestTo("https://orders.example.test/orders"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentType(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {"sku":"BOOK-42","quantity":0}
                """))
        .andRespond(withStatus(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "code":"INVALID_QUANTITY",
                          "field":"quantity"
                        }
                        """));
```

Test nên xác nhận client không âm thầm bỏ qua lỗi validation từ server. Nếu ứng dụng validate request trước khi gọi HTTP, cần có unit test riêng chứng minh request không hợp lệ bị chặn ở phía client và không gửi request ra ngoài. Hai hành vi này khác nhau:

- Client gửi request và server trả `400`: kiểm tra cách client xử lý lỗi response.
- Client từ chối dữ liệu trước khi gửi request: kiểm tra validation phía ứng dụng và xác nhận không có HTTP request.

## 9. Kiểm tra lỗi transport và timeout

Lỗi HTTP là response có status. Lỗi transport xảy ra khi không có response hợp lệ được nhận, ví dụ server không lắng nghe, kết nối bị reset, DNS không phân giải được hoặc timeout. Không nên gộp hai loại này vào cùng một nhánh xử lý nếu ứng dụng cần retry khác nhau.

Với WebClient, có thể kiểm tra timeout bằng một server giả trì hoãn response:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("{\"id\":42}")
        .setBodyDelay(2, TimeUnit.SECONDS));

StepVerifier.create(client.findById(42).timeout(Duration.ofMillis(200)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
```

Đây là timeout được áp dụng trong Reactor pipeline của test/client. Nếu ứng dụng cấu hình timeout ở HTTP connector, hãy kiểm tra cấu hình đó qua client thật và xác nhận exception phát sinh từ transport. Không nên chỉ thêm `Mono.timeout(...)` vào test rồi kết luận connector đã được cấu hình timeout.

Với lỗi kết nối, có thể tắt MockWebServer trước khi gửi request hoặc trỏ client đến một cổng không có server, nhưng test đó dễ phụ thuộc môi trường. Tốt hơn là dùng server giả có thể chủ động đóng kết nối hoặc một connector test fixture được kiểm soát. Dù chọn cách nào, assertion cần xác nhận client phát lỗi transport và không trả về dữ liệu thành công.

## 10. Kiểm thử retry và fallback

Nếu client có retry policy, server giả có thể xếp hàng nhiều response theo thứ tự. Ví dụ lần đầu trả `503`, lần tiếp theo trả `200`:

```java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"id":42,"sku":"BOOK-42","availableQuantity":12}
                """));
```

Sau khi gọi client có retry, test cần xác nhận kết quả cuối cùng và số request thực tế:

```java
StepVerifier.create(client.findById(42))
        .expectNextMatches(item -> item.id() == 42)
        .verifyComplete();

assertThat(server.getRequestCount()).isEqualTo(2);
```

Chỉ dùng cách này khi retry thực sự là chính sách của client. Không nên tự động retry mọi lỗi `4xx`: `400`, `401`, `403` hoặc `404` thường không tự hết khi gửi lại cùng request. Với `503` hoặc lỗi transport tạm thời, retry có thể hợp lý nhưng cần giới hạn số lần, backoff và idempotency.

Nếu client dùng fallback, test nên xác nhận fallback chỉ chạy cho nhóm lỗi được quy định. Ví dụ `503` có thể trả dữ liệu cache, còn `404` phải giữ nguyên nghĩa không tìm thấy. Một fallback chung cho mọi exception dễ che giấu lỗi dữ liệu hoặc lỗi lập trình.

## 11. Reset và xác minh mock server

Mỗi test nên có expectation riêng và xác minh chúng đã được sử dụng. Với `MockRestServiceServer`, gọi `verify()` sau khi client hoàn tất. Nếu tái sử dụng cùng server trong nhiều test, reset expectation giữa các test bằng API phù hợp hoặc tạo fixture mới cho mỗi test.

Với MockWebServer, enqueue response trước request, sau đó đọc `RecordedRequest` để kiểm tra request đã đến. Dùng timeout khi lấy request để tránh chờ vô hạn. Luôn dừng server trong `finally` hoặc dùng `try-with-resources` nếu phiên bản thư viện hỗ trợ `AutoCloseable`.

Không để nhiều test song song dùng chung một MockWebServer nếu chúng cùng enqueue response và đọc request từ cùng hàng đợi. Mỗi test nên có server riêng hoặc cơ chế đồng bộ rõ ràng, nếu không response có thể bị test khác tiêu thụ.

## 12. Những lỗi thường gặp khi tạo response giả

### Chỉ trả status mà không có `Content-Type`

Client có thể chọn codec theo header response. Nếu test muốn xác nhận JSON decoding, hãy đặt `Content-Type: application/json`. Nếu cố ý kiểm tra server thiếu header, hãy coi đó là một kịch bản riêng.

### Dùng response body không khớp DTO

Một payload có thể deserialize nhưng các trường quan trọng lại thành `null` hoặc giá trị mặc định. Hãy assert các trường và kiểm tra invariant sau deserialize, không chỉ assert object tồn tại.

### Nhầm lỗi HTTP với lỗi decode

`404` là response HTTP hợp lệ nhưng báo tài nguyên không tồn tại. `200` với JSON sai cú pháp là response thành công ở mức status nhưng dữ liệu không đọc được. Client có thể cần hai loại exception và hai chính sách retry khác nhau.

### Không kiểm tra request đã gửi

Một test chỉ enqueue response và assert dữ liệu có thể bỏ qua việc client gọi sai method hoặc path. Với `MockRestServiceServer`, khai báo request expectation; với MockWebServer, đọc `RecordedRequest`.

### Dùng mock object thay cho HTTP response khi cần kiểm tra serialization

Mock service hoặc mock `ExchangeFunction` có thể hữu ích cho unit test nhỏ, nhưng chúng có thể bỏ qua request encoding, header và transport. Nếu mục tiêu là kiểm tra client gửi/nhận HTTP đúng, dùng mock HTTP server.

### Retry làm test chậm hoặc chập chờn

Retry có delay thật có thể làm test kéo dài. Cấu hình backoff test ngắn hoặc dùng scheduler có thể kiểm soát nếu retry logic hỗ trợ. Không dùng `Thread.sleep` để chờ retry; quan sát số request và kết quả bằng cơ chế đồng bộ thích hợp.

## 13. Chọn công cụ theo HTTP client

| Client trong ứng dụng | Công cụ tạo response giả | Phạm vi chính |
|---|---|---|
| `RestTemplate` | `MockRestServiceServer.bindTo(restTemplate)` | Request expectation và response giả ở request factory. |
| `RestClient` (Spring Framework 6.1+) | `MockRestServiceServer.bindTo(builder)` | Kiểm tra API đồng bộ mới của Spring qua request factory giả. |
| `WebClient` | MockWebServer hoặc WireMock | Server HTTP cục bộ, kiểm tra request/response qua connector. |
| `WebClient` unit test rất hẹp | Mock `ExchangeFunction` | Kiểm tra logic mapping response mà không xác nhận HTTP transport. |

Chọn công cụ dựa trên client đang được ứng dụng sử dụng và hành vi cần xác nhận. Với `RestClient`/`RestTemplate`, `MockRestServiceServer` tích hợp trực tiếp với Spring Test. Với `WebClient`, MockWebServer tạo được response HTTP thực qua một cổng cục bộ và cho phép kiểm tra request đã gửi.

## 14. Checklist cho response thành công, lỗi và dữ liệu không hợp lệ

- [ ] Có response thành công với status, content type và JSON hợp lệ.
- [ ] Có assertion cho từng trường DTO quan trọng sau deserialize.
- [ ] Có test các status lỗi thuộc hợp đồng như `400`, `401`, `403`, `404` và `5xx` khi cần.
- [ ] Có xác nhận client chuyển status lỗi thành exception hoặc kết quả domain theo thiết kế.
- [ ] Có test `200 OK` với JSON sai cú pháp.
- [ ] Có test JSON hợp lệ nhưng thiếu trường hoặc chứa giá trị vi phạm invariant.
- [ ] Có phân biệt lỗi response HTTP, lỗi decode và lỗi transport.
- [ ] Có kiểm tra request method, URI, header và body đã gửi.
- [ ] Nếu có retry/fallback, có kiểm tra số lần gọi và nhóm lỗi được retry.
- [ ] Mock server được reset/đóng và expectation được xác minh sau mỗi test.

Tạo response giả thành công, lỗi và dữ liệu không hợp lệ giúp kiểm thử HTTP client tại đúng ranh giới tích hợp. Hãy kiểm tra cả request được gửi lẫn response được diễn giải, phân biệt status lỗi với payload sai và bảo đảm client không biến dữ liệu không đáng tin cậy thành kết quả thành công. Khi có retry, fallback hoặc timeout, kiểm tra chúng như chính sách riêng với giới hạn và điều kiện rõ ràng.
