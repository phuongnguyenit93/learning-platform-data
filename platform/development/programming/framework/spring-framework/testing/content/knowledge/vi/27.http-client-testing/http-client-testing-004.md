# Đặt kỳ vọng URI, method, header và body gửi ra

Khi một service gọi HTTP sang hệ thống khác, test cần xác nhận request mà ứng dụng thực sự gửi đi. Với Spring Framework, `MockRestServiceServer` cho phép kiểm tra request của `RestClient` và `RestTemplate` mà không cần gọi tới server bên ngoài. Test có thể đặt kỳ vọng về URI, HTTP method, query parameter, header và body, sau đó cung cấp response giả để kiểm tra cách ứng dụng xử lý kết quả.

Điểm quan trọng là kiểm thử ở ranh giới HTTP client. Ta muốn biết client gửi đúng địa chỉ, đúng phương thức, đúng dữ liệu và xử lý response theo hợp đồng. Không cần dựng một server thật cho từng test đơn vị của lớp tích hợp HTTP.

## 1. Luồng kiểm thử một HTTP client

Giả sử ứng dụng có `InventoryClient` gọi dịch vụ kho:

~~~text
Service trong ứng dụng
        |
        v
InventoryClient
        |
        |  RestClient / RestTemplate
        v
MockRestServiceServer
        |
        +--> kiểm tra URI
        +--> kiểm tra HTTP method
        +--> kiểm tra header
        +--> kiểm tra request body
        |
        +--> trả response giả
        |
        v
InventoryClient xử lý response
~~~

Test khai báo request mong đợi trước khi gọi code cần kiểm tra. Khi client gửi request, mock server so sánh request thực tế với các matcher đã đăng ký. Nếu request không khớp, test nhận lỗi mô tả kỳ vọng nào không được đáp ứng.

Với Spring `RestClient` và `RestTemplate`, công cụ thường dùng là `MockRestServiceServer` trong module Spring Test. Cơ chế này thay thế request factory để request được xử lý trong test process; nó không mở socket tới host thật.

## 2. Tạo RestClient và gắn MockRestServiceServer

Spring Framework 6.1 trở lên hỗ trợ bind `MockRestServiceServer` trực tiếp vào `RestClient.Builder`. Hãy bind trước khi build `RestClient`, để builder dùng request factory do mock server quản lý.

Ví dụ lớp client:

~~~java
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(InventoryItem.class);
    }
}
~~~

Test:

~~~java
class InventoryClientTest {

    private MockRestServiceServer server;
    private InventoryClient inventoryClient;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.example");

        server = MockRestServiceServer.bindTo(builder).build();
        inventoryClient = new InventoryClient(builder.build());
    }

    @Test
    void sendsGetRequestForSku() {
        server.expect(requestTo(
                        "https://inventory.example/api/items/COFFEE-01"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess("""
                        {
                          "sku": "COFFEE-01",
                          "available": 12
                        }
                        """, MediaType.APPLICATION_JSON));

        InventoryItem item = inventoryClient.findBySku("COFFEE-01");

        assertThat(item.sku()).isEqualTo("COFFEE-01");
        assertThat(item.available()).isEqualTo(12);
        server.verify();
    }
}
~~~

Trong test này:

- `baseUrl` xác định host gốc mà client sử dụng.
- `bindTo(builder)` gắn mock server vào builder.
- `expect(requestTo(...))` kiểm tra URI đầy đủ.
- `andExpect(method(...))` kiểm tra method.
- `andExpect(header(...))` kiểm tra header.
- `andRespond(withSuccess(...))` cung cấp response giả.
- `verify()` xác nhận các kỳ vọng đã được đáp ứng.

Mỗi expectation mặc định yêu cầu request tương ứng xuất hiện một lần. Nếu code không gửi request, gọi sai endpoint hoặc gửi thêm request không được khai báo, test sẽ phát hiện sai lệch.

## 3. Kiểm tra URI và query parameter

URI là một phần quan trọng của hợp đồng tích hợp. Một request có thể đúng method và body nhưng vẫn gọi nhầm host, path hoặc query parameter.

### 3.1. Kiểm tra URI đầy đủ

Matcher `requestTo(...)` kiểm tra URI request:

~~~java
server.expect(requestTo(
                "https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Nên dùng URI đầy đủ khi host, base path hoặc path là một phần quan trọng của cấu hình client. Cách này phát hiện lỗi ghép base URL, thiếu prefix hoặc gọi nhầm endpoint.

### 3.2. Kiểm tra query parameter

Ví dụ client tìm sản phẩm theo từ khóa và phân trang:

~~~java
public List<CatalogItem> search(String keyword, int page, int size) {
    return restClient.get()
            .uri(uriBuilder -> uriBuilder
                    .path("/api/catalog")
                    .queryParam("q", keyword)
                    .queryParam("page", page)
                    .queryParam("size", size)
                    .build())
            .retrieve()
            .body(new ParameterizedTypeReference<>() {});
}
~~~

Đặt kỳ vọng:

~~~java
server.expect(requestTo(
                "https://catalog.example/api/catalog?q=green+tea&page=0&size=20"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
~~~

Có thể dùng matcher `queryParam(...)` để kiểm tra từng tham số mà không phải ghép toàn bộ URI:

~~~java
server.expect(requestTo(
                "https://catalog.example/api/catalog?q=green+tea&page=0&size=20"))
        .andExpect(queryParam("q", "green tea"))
        .andExpect(queryParam("page", "0"))
        .andExpect(queryParam("size", "20"))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
~~~

Khi dùng matcher query parameter, test thể hiện rõ tham số nào thuộc hợp đồng. Nếu thứ tự query parameter không quan trọng, matcher theo từng key thường dễ đọc và ít phụ thuộc cách URI builder sắp xếp tham số.

### 3.3. Ký tự đặc biệt và encoding

Không nên tự nối chuỗi query bằng phép cộng nếu giá trị có dấu cách, dấu cộng, dấu và hoặc ký tự Unicode. Dùng `UriBuilder` để Spring encode đúng giá trị theo ngữ cảnh URI.

Ví dụ từ khóa `tea & coffee` phải được encode để dấu `&` không bị hiểu thành dấu phân tách giữa hai query parameter. Test nên kiểm tra cả giá trị đã giải mã bằng `queryParam(...)` và URI cuối nếu encoding chính xác là điều cần xác nhận.

Path variable cũng cần được encode phù hợp. Dữ liệu định danh có dấu `/`, `?` hoặc `#` không nên được chèn trực tiếp vào path theo cách làm thay đổi cấu trúc URL. Hãy xác định hợp đồng identifier cho phép ký tự nào và kiểm tra cách client tạo URI.

## 4. Kiểm tra HTTP method

Matcher `method(...)` xác nhận client dùng đúng HTTP method:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.PUT))
        .andRespond(withSuccess());
~~~

Những lỗi method thường gặp:

- Dùng `GET` thay cho `POST` khi tạo tài nguyên.
- Dùng `PUT` khi hợp đồng yêu cầu `PATCH` cho cập nhật một phần.
- Dùng `DELETE` tới nhầm path.
- Gửi body bằng method hoặc endpoint không hỗ trợ body đó.

Không nên chỉ kiểm tra URI mà bỏ qua method. Cùng một URI có thể có hành vi hoàn toàn khác nhau theo method.

Ví dụ test update:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.PATCH))
        .andRespond(withSuccess());
~~~

Nếu API yêu cầu `PUT` thay vì `PATCH`, expectation sẽ thất bại khi client gửi sai method.

## 5. Kiểm tra header

Header mang metadata và thông tin điều khiển request. Các header thường cần kiểm tra:

- `Accept`: định dạng response client mong muốn.
- `Content-Type`: định dạng body client gửi.
- `Authorization`: thông tin xác thực.
- `If-Match` hoặc `If-None-Match`: điều kiện cập nhật hoặc cache.
- `Idempotency-Key`: khóa chống xử lý lặp theo hợp đồng API.
- `X-Correlation-ID` hoặc `traceparent`: mã liên kết request trong hệ thống.

Ví dụ:

~~~java
server.expect(requestTo("https://payment.example/api/charges"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header(
                HttpHeaders.CONTENT_TYPE,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header(
                HttpHeaders.AUTHORIZATION,
                "Bearer test-access-token"))
        .andExpect(header("Idempotency-Key", "charge-001"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Đối với header có nhiều giá trị, có thể kiểm tra các giá trị theo matcher header tương ứng. Với header tùy chọn, matcher `headerDoesNotExist(...)` giúp xác nhận client không gửi thông tin không cần thiết.

Không nên đặt token thật trong fixture hoặc log test. Dùng token giả dành riêng cho test và chỉ kiểm tra rằng header được tạo đúng định dạng. Nếu cần xác nhận token được lấy từ cấu hình, inject một giá trị test có thể kiểm soát.

## 6. Kiểm tra request body

Khi client gửi JSON, cần xác nhận cả body lẫn `Content-Type`. Ví dụ:

~~~java
public void createItem(CreateItemRequest request) {
    restClient.post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .toBodilessEntity();
}
~~~

Test:

~~~java
server.expect(requestTo("https://inventory.example/api/items"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 12
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED));
~~~

Matcher `content().json(...)` so sánh body như JSON thay vì so sánh chuỗi byte theo định dạng khoảng trắng. Điều này giúp test tập trung vào nội dung JSON. Nếu khoảng trắng hoặc thứ tự property là điều thực sự quan trọng đối với một giao thức đặc biệt, dùng matcher chuỗi hoặc byte phù hợp.

Với body văn bản:

~~~java
server.expect(requestTo("https://legacy.example/api/commands"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().string("REFRESH CACHE"))
        .andRespond(withSuccess());
~~~

Với body form URL encoded, kiểm tra content type và nội dung form theo hợp đồng:

~~~java
server.expect(requestTo("https://auth.example/token"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_FORM_URLENCODED))
        .andExpect(content().string(
                containsString("grant_type=client_credentials")))
        .andRespond(withSuccess(
                "{\"access_token\":\"test-token\"}",
                MediaType.APPLICATION_JSON));
~~~

Không nên kiểm tra body bằng một chuỗi dài cứng nhắc nếu thứ tự field hoặc khoảng trắng không thuộc hợp đồng. Ngược lại, cũng không nên dùng matcher quá rộng đến mức test không phát hiện field quan trọng bị thiếu.

## 7. Kết hợp nhiều kỳ vọng cho một request

Một expectation có thể kết hợp URI, method, query, header và body:

~~~java
server.expect(requestTo("https://payment.example/api/charges?region=apac"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(queryParam("region", "apac"))
        .andExpect(header(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "orderId": "ORDER-1001",
                  "amount": 250000,
                  "currency": "VND"
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "chargeId": "CHARGE-9001",
                          "status": "ACCEPTED"
                        }
                        """));
~~~

Test này xác nhận request có đúng cấu trúc và cung cấp response đại diện để code client xử lý. Sau khi gọi client, cần assert kết quả trả về hoặc side effect tương ứng, rồi gọi `server.verify()`.

Không nên đặt quá nhiều expectation không liên quan trong một test. Mỗi test nên tập trung vào một hành vi của client, ví dụ tạo charge, retry khi lỗi tạm thời hoặc xử lý response không hợp lệ.

## 8. Kỳ vọng thứ tự và số lần gọi

Theo mặc định, `MockRestServiceServer` mong đợi request xuất hiện theo thứ tự đã khai báo. Nếu client gọi nhiều endpoint theo một chuỗi có ý nghĩa, thứ tự mặc định giúp phát hiện việc đảo thứ tự gọi.

Ví dụ:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("{\"available\":12}",
                MediaType.APPLICATION_JSON));

server.expect(requestTo("https://inventory.example/api/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(withSuccess());
~~~

Nếu thứ tự request không quan trọng, có thể cấu hình expectation manager bỏ qua thứ tự bằng tùy chọn `ignoreExpectOrder(true)` trên builder của mock server. Chỉ dùng khi các request thực sự độc lập; nếu thứ tự là một phần của nghiệp vụ, giữ kiểm tra mặc định.

Để kiểm tra số lần gọi, có thể dùng `ExpectedCount`:

~~~java
server.expect(once(), requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Các kiểu count như `once()`, `twice()`, `times(n)` hoặc `manyTimes()` cho phép xác định số lần request được phép xảy ra. Điều này hữu ích khi kiểm tra retry, caching hoặc bảo đảm một request không bị gửi lặp ngoài ý muốn.

Ví dụ nếu client phải retry tối đa ba lần, hãy khai báo số lần mong đợi đúng với chính sách retry và response cho từng lần. Không dùng `manyTimes()` nếu test cần phát hiện retry quá mức.

## 9. Cung cấp response giả và kiểm tra cách client xử lý

`andRespond(...)` định nghĩa response mà mock server trả về. Một số response creator thường dùng:

~~~java
withSuccess("{\"status\":\"OK\"}", MediaType.APPLICATION_JSON);
withStatus(HttpStatus.NOT_FOUND);
withStatus(HttpStatus.SERVICE_UNAVAILABLE);
withServerError();
withNoContent();
~~~

Response giả cho phép kiểm tra cách client xử lý cả thành công và lỗi mà không phụ thuộc dịch vụ ngoài.

Ví dụ với response 404:

~~~java
server.expect(requestTo("https://inventory.example/api/items/MISSING"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> inventoryClient.findBySku("MISSING"))
        .isInstanceOf(RestClientResponseException.class);

server.verify();
~~~

Nếu lớp client chuyển đổi exception HTTP thành exception domain riêng, hãy kiểm tra exception domain đó. Test nên phản ánh hành vi mà caller của `InventoryClient` nhìn thấy, đồng thời expectation xác nhận request đã gửi đúng.

## 10. Kiểm tra request khi client được quản lý bởi Spring

Trong ứng dụng, `RestClient` có thể được tạo từ bean cấu hình:

~~~java
@Configuration
class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Khi kiểm thử client Spring-managed, cần đảm bảo mock server được gắn vào đúng builder trước khi `RestClient` được tạo. Có thể cấu hình test với builder riêng và tạo client trong fixture test, hoặc dùng cơ chế test context phù hợp để cung cấp builder đã được bind.

Không nên tạo một builder đã bind mock server rồi lại inject một `RestClient` được tạo từ builder khác. Khi đó request đi ra từ client thật không đi qua mock server và test có thể cố gọi mạng thật.

Với `RestTemplate`, cơ chế tương tự:

~~~java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server =
        MockRestServiceServer.createServer(restTemplate);

server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                "{\"sku\":\"COFFEE-01\"}",
                MediaType.APPLICATION_JSON));
~~~

`MockRestServiceServer.createServer(restTemplate)` thay request factory của `RestTemplate` để request được xử lý trong test. Với `RestClient`, dùng builder binding tương ứng như các ví dụ trước.

## 11. Phân biệt RestClient/RestTemplate với WebClient

`MockRestServiceServer` dành cho client đồng bộ dựa trên `RestClient` và `RestTemplate`. `WebClient` là reactive HTTP client và có cơ chế connector riêng. Khi kiểm thử request gửi ra bởi `WebClient`, thường dùng mock HTTP server như MockWebServer hoặc WireMock để kiểm tra request qua HTTP protocol.

| HTTP client | Công cụ kiểm thử request thường dùng |
|---|---|
| `RestClient` | `MockRestServiceServer.bindTo(RestClient.Builder)` |
| `RestTemplate` | `MockRestServiceServer.createServer(RestTemplate)` |
| `WebClient` | MockWebServer, WireMock hoặc server test tương thích HTTP |

Không cố gắn `MockRestServiceServer` vào `WebClient`. Chọn công cụ theo loại client giúp test đi qua đúng request abstraction và tránh cấu hình không tương thích.

## 12. Kiểm tra header, body và URI một cách có ý nghĩa

Một số nguyên tắc giúp expectation vừa chặt chẽ vừa dễ bảo trì:

- Kiểm tra host/path đầy đủ khi định tuyến tới đúng hệ thống là yêu cầu quan trọng.
- Kiểm tra query parameter theo từng key khi thứ tự query không có ý nghĩa.
- Kiểm tra method cho mọi request có tác động hoặc có semantics khác nhau.
- Kiểm tra `Content-Type` khi body được gửi và `Accept` khi client có yêu cầu representation.
- Kiểm tra header xác thực hoặc idempotency nếu chúng là một phần hợp đồng.
- Kiểm tra field JSON quan trọng, không nhất thiết phải cố định mọi field không liên quan.
- Kiểm tra số lần gọi khi retry, caching hoặc chống gửi lặp là yêu cầu.
- Assert response mà lớp client trả về, không dừng ở việc request đã khớp.

Matcher quá chặt có thể khiến test hỏng vì thay đổi không ảnh hưởng hợp đồng, ví dụ thứ tự JSON property. Matcher quá lỏng có thể bỏ sót lỗi thật, ví dụ thiếu `Authorization` hoặc gửi sai amount. Hãy chọn mức kiểm tra theo rủi ro của từng thành phần.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test cố gọi host thật | Client không được tạo từ builder/RestTemplate đã bind mock server | Bind đúng builder trước khi build client |
| Không có request nào được ghi nhận | Code dùng một instance client khác với instance được cấu hình trong test | Kiểm tra dependency injection và builder ownership |
| URI expectation không khớp | Base URL, path, encoding hoặc query parameter khác dự kiến | Kiểm tra URI đầy đủ và dùng URI builder |
| Request có đúng path nhưng test vẫn lỗi | Method hoặc header không khớp | Thêm matcher riêng cho method/header |
| Body JSON khác khoảng trắng làm test thất bại | So sánh chuỗi thay vì JSON structure | Dùng `content().json(...)` nếu whitespace không thuộc hợp đồng |
| `verify()` báo expectation chưa được đáp ứng | Code chưa gọi client hoặc nhánh logic không chạy | Xác nhận test đã kích hoạt đúng hành vi |
| Request được gửi nhiều lần ngoài dự kiến | Retry hoặc logic gọi lặp | Dùng `ExpectedCount` để khóa số lần gọi |
| Thứ tự expectation không khớp | Request được gửi theo thứ tự khác | Giữ thứ tự nếu có ý nghĩa; nếu độc lập, cấu hình ignore order |
| Dùng MockRestServiceServer cho WebClient | Nhầm loại HTTP client | Dùng MockWebServer hoặc WireMock |

## 14. Quy trình viết một test HTTP client

Khi kiểm thử một client gọi dịch vụ ngoài, thực hiện theo trình tự:

1. Tạo `RestClient.Builder` hoặc `RestTemplate` trong phạm vi test.
2. Gắn `MockRestServiceServer` vào đúng builder/client trước khi code cần test sử dụng nó.
3. Đặt expectation về URI, method, query parameter, header và body.
4. Khai báo response giả với status, header và body phù hợp.
5. Gọi phương thức public của lớp client hoặc service tích hợp.
6. Assert dữ liệu trả về hoặc exception mà caller nhìn thấy.
7. Gọi `server.verify()` để xác nhận mọi request mong đợi đã xảy ra.

Test nên gọi phương thức public của lớp client thay vì tự dựng request giống hệt implementation trong test. Nếu test tự tạo request riêng, nó chỉ chứng minh matcher hoạt động, không chứng minh ứng dụng đã gửi đúng request.

`MockRestServiceServer` giúp kiểm tra hợp đồng request ở tầng `RestClient` hoặc `RestTemplate`: URI, method, header và body. Khi kết hợp expectation có ý nghĩa với response giả và assertion kết quả, test sẽ phát hiện được lỗi cấu hình endpoint, serialization, xác thực và logic xử lý response mà không phụ thuộc hệ thống bên ngoài.
