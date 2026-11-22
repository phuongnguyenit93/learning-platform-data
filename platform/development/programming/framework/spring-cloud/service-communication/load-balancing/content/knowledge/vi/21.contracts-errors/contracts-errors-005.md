# Xử lý response rỗng, dữ liệu sai kiểu và content type không phù hợp

Trong hệ thống microservices dùng **Spring Cloud LoadBalancer**, client có thể tìm đúng `ServiceInstance` của `catalog-service`, mở kết nối thành công và nhận HTTP 200 nhưng vẫn **không đọc được dữ liệu nghiệp vụ**. Nguyên nhân thường nằm ở **hợp đồng HTTP/JSON**: response không có body, trường dữ liệu không đúng kiểu, JSON bị hỏng hoặc `Content-Type` không tương thích với kiểu mà client muốn decode.

Đây là chủ đề của chương **Hợp đồng và lỗi**: cần phân biệt lỗi **chọn bản sao**, **truyền HTTP**, **HTTP status**, **message conversion** và **semantic validation**. Nếu gộp tất cả thành “lỗi gọi service” rồi retry, ứng dụng có thể liên tục gọi một bản sao có schema không tương thích, che khuất lỗi triển khai hoặc làm tăng tải.

Bài học sử dụng `RestClient`, `WebClient` và Spring Cloud OpenFeign để minh họa; các ví dụ giả định Spring Boot/Spring Cloud tương thích, có nguồn discovery cho service ID `catalog-service` và JSON codec (thường qua Jackson).

## 1. LoadBalancer chọn instance, nhưng không bảo đảm hợp đồng response

Một request logic:

~~~http
GET http://catalog-service/products/7
Accept: application/json
~~~

Có thể đi theo luồng:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi catalog-service"]
    B["Spring Cloud LoadBalancer<br/>chọn ServiceInstance"]
    C["HTTP transport tới host:port"]
    D{"Nhận HTTP response?"}
    E["Lỗi network/timeout"]
    F["Kiểm tra status, headers"]
    G{"Body và Content-Type<br/>đáp ứng hợp đồng?"}
    H["Giải mã JSON thành ProductDto"]
    I["Kiểm tra dữ liệu nghiệp vụ"]
    J["Trả ProductDto hợp lệ"]
    K["Contract / decoding / validation error"]
    A --> B --> C --> D
    D -->|"Không"| E
    D -->|"Có"| F --> G
    G -->|"Không"| K
    G -->|"Có"| H --> I
    I -->|"Hợp lệ"| J
    I -->|"Không hợp lệ"| K
~~~

| Tầng | Ví dụ lỗi | Cách xử lý |
|---|---|---|
| Discovery/LoadBalancer | Không có bản sao nào cho `catalog-service` | Kiểm tra service ID, registry, supplier, health/zone filter |
| Network/HTTP transport | `Connection refused`, connect/read timeout | Kiểm tra URI của instance, network, timeout, retry có điều kiện |
| HTTP status | `404`, `409`, `429`, `503` | Ánh xạ theo hợp đồng nghiệp vụ và error response |
| Body decoding | JSON hỏng, kiểu dữ liệu không tương thích | Kiểm tra schema, decoder và content type |
| Semantic validation | JSON decode được nhưng thiếu `id`, tên rỗng | Kiểm tra ràng buộc và contract version |

**HTTP 200 chỉ xác nhận request được trả một response thành công ở mức HTTP; nó không chứng minh body hợp lệ theo hợp đồng ứng dụng.** LoadBalancer không hiểu rằng `ProductDto.id` phải là số hoặc `Content-Type` phải là JSON.

## 2. Phân biệt 204, 200 rỗng, JSON null, object rỗng và list rỗng

Một client kỳ vọng `ProductDto` với hai trường bắt buộc:

~~~java
public record ProductDto(Long id, String name) {}
~~~

Các response sau **không tương đương**:

| Phản hồi | Ý nghĩa ở mức HTTP/payload | Nếu client yêu cầu `ProductDto` |
|---|---|---|
| `204 No Content`, không body | Thành công nhưng có chủ đích không có representation | Không được tự bịa `ProductDto`; có thể dùng `ResponseEntity<Void>` |
| `200 OK`, body dài 0 byte | Thành công nhưng body rỗng | Với contract bắt buộc có object: **vi phạm hợp đồng** |
| `200` + body `null` và `application/json` | Một JSON literal `null` hợp lệ | Java object có thể được decode thành `null` hoặc không phát phần tử reactive |
| `200` + body `{}` | JSON object rỗng | Có thể decode thành DTO với các field `null` nếu không có validation |
| `200` + body `[]` | JSON array rỗng | Hợp lệ cho `List<ProductDto>` nếu contract yêu cầu danh sách |
| `200` + body `{"id":7,"name":"Tea"}` | JSON object có đủ field | Có thể decode thành `ProductDto` |
| `200` + body `{"id":"oops","name":"Tea"}` | Giá trị `id` không đúng kiểu mong muốn | Thường gặp lỗi deserialization với đích `Long` |
| `200` + JSON bị cắt dở | Payload không phải JSON hoàn chỉnh | Lỗi parse/decoding, không phải thiếu instance |
| `404 Not Found` | Tài nguyên không tồn tại theo hợp đồng | Xử lý 404 rõ ràng; không suy 204/200 rỗng |

Phân biệt thêm:

- **Trường thiếu hoặc `null`**: một số decoder vẫn tạo object Java có trường `null`. Cần kiểm tra field bắt buộc ở tầng contract/validation.
- **Chuỗi `""`**: không bằng `null` và không bằng object rỗng. Nếu trường tên sản phẩm không được trống, cần ràng buộc riêng.
- **Mảng `[]`**: hợp lệ khi API trả danh sách không có phần tử; **không** hợp lệ nếu API được khai báo trả một object duy nhất.
- **`204`**: dùng tốt cho thao tác không có payload phản hồi, chẳng hạn một số `DELETE`, nếu đã định nghĩa trong contract. Không nên biến mọi lỗi tìm kiếm thành `204` cho tiện.

### Quy tắc thiết kế nhất quán

Ví dụ API có hai endpoint:

~~~text
GET /products/7         -> 200 + ProductDto, hoặc 404 nếu không tồn tại
GET /products?category=x -> 200 + [] nếu danh sách rỗng
DELETE /products/7      -> 204 nếu xóa thành công mà không trả body
~~~

Đây là **một đề xuất hợp đồng nhất quán**, không phải quy định bắt buộc cho mọi API. Điều quan trọng là client và server **thống nhất trước**, đồng thời version hóa khi thay đổi.

## 3. Content-Type, Accept và Content-Encoding là ba khái niệm khác nhau

Ví dụ:

~~~http
GET /products/7
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip

<compressed JSON bytes>
~~~

- **`Accept`**: request header cho biết client mong muốn loại representation nào; server/proxy có thể không tuân thủ đúng.
- **`Content-Type`**: response header mô tả **kiểu dữ liệu đang trả**, được HTTP message converter/codec dùng để chọn decoder.
- **`Content-Encoding`**: nêu cách representation được mã hóa/nén (ví dụ `gzip`), không thay thế `Content-Type`.

Nếu client đặt `Accept: application/json` nhưng server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<html><body>Proxy maintenance page</body></html>
~~~

thì **HTTP status thành công không làm body HTML trở thành `ProductDto`**. Tầng decode nên coi đây là lỗi contract cho lời gọi kỳ vọng JSON. Đừng âm thầm parse HTML, bỏ qua `Content-Type` hoặc trả một DTO giả để “cứu” request.

### JSON media types và vendor types

`application/json` là thông dụng; một API có thể dùng `application/vnd.example.product+json`. Suffix `+json` biểu thị representation liên quan JSON nhưng **vẫn cần thoả thuận contract** để đảm bảo decoder, schema và version phù hợp.

`application/problem+json` thường dùng cho cấu trúc thông báo lỗi như Problem Details; không được mặc nhiên decode thành `ProductDto` trên nhánh thành công. Nếu response status là 4xx/5xx, nên xử lý status/error contract trước khi decode một DTO nghiệp vụ.

## 4. Tạo server giả lập để tái hiện lỗi hợp đồng

Dùng một controller **chỉ cho môi trường lab** chạy ở `8081`. Nó trả các response khác nhau theo tên kịch bản:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ContractLabController {

    @GetMapping("/lab/products/{scenario}")
    ResponseEntity<?> product(
            @PathVariable String scenario) {

        return switch (scenario) {
            case "valid" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":7,"name":"Tea"}
                          """);

            case "empty-204" ->
                    ResponseEntity.noContent().build();

            case "empty-200" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("");

            case "json-null" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("null");

            case "object-empty" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{}");

            case "field-null" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":null,"name":""}
                          """);

            case "wrong-type" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":"oops","name":"Tea"}
                          """);

            case "malformed" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"id\":7,\"name\":");

            case "json-as-text" -> ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("""
                          {"id":7,"name":"Tea"}
                          """);

            case "html" -> ResponseEntity.ok()
                    .contentType(MediaType.TEXT_HTML)
                    .body("<html><body>Maintenance</body></html>");

            default -> ResponseEntity.notFound().build();
        };
    }
}
~~~

**Lưu ý:** ở đây body JSON được viết dưới dạng `String` và ép `Content-Type` để cố ý tạo các tình huống sai. Trong controller production, thông thường nên trả DTO để framework chọn JSON converter; không nên xây dựng JSON thủ công bằng nối chuỗi.

Bảng thử nghiệm:

| Đường dẫn | Status | Content-Type | Body |
|---|---:|---|---|
| `/lab/products/valid` | 200 | `application/json` | Object hợp lệ |
| `/lab/products/empty-204` | 204 | Có thể không có | Không body |
| `/lab/products/empty-200` | 200 | `application/json` | 0 byte |
| `/lab/products/json-null` | 200 | `application/json` | `null` |
| `/lab/products/object-empty` | 200 | `application/json` | `{}` |
| `/lab/products/field-null` | 200 | `application/json` | Field `null`/rỗng |
| `/lab/products/wrong-type` | 200 | `application/json` | Kiểu field không tương thích |
| `/lab/products/malformed` | 200 | `application/json` | JSON thiếu phần kết |
| `/lab/products/json-as-text` | 200 | `text/plain` | Nội dung trông giống JSON |
| `/lab/products/html` | 200 | `text/html` | HTML |

Nếu có proxy/CDN/API gateway, phải kiểm tra response thực sự tới client vì proxy có thể thay đổi header/status/body.

## 5. Cấu hình RestClient đi qua Spring Cloud LoadBalancer

Một client dùng `@LoadBalanced RestClient.Builder` nhận URL chứa service ID để Spring Cloud chọn instance:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Trong bài lab, có thể dùng `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

Ứng dụng cần dependency `spring-cloud-starter-loadbalancer` và các HTTP/JSON dependencies tương thích. `RestClient` được giới thiệu ở Spring Framework 6.1, nên không áp dụng nguyên mã cho các ứng dụng Framework 6.0. Khi dùng Boot auto-customizers (tracing, codecs, observability), cần cân nhắc `RestClientBuilderConfigurer` thay vì luôn tạo builder thô.

### Gọi có kiểu và kiểm tra kết quả

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogRestGateway {

    private final RestClient client;

    CatalogRestGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    ProductDto fetchProduct(String scenario) {
        ResponseEntity<ProductDto> response = client.get()
                .uri("/lab/products/{scenario}", scenario)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(ProductDto.class);

        if (response.getStatusCode().value() == 204) {
            throw new DownstreamContractException(
                    "Expected product body but received 204");
        }

        ProductDto body = response.getBody();

        if (body == null || body.id() == null
                || body.name() == null
                || body.name().isBlank()) {
            throw new DownstreamContractException(
                    "Product response is missing required fields");
        }

        return body;
    }
}

record ProductDto(Long id, String name) {}

class DownstreamContractException extends RuntimeException {
    DownstreamContractException(String message) {
        super(message);
    }

    DownstreamContractException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ý nghĩa:

1. `retrieve().toEntity(ProductDto.class)` cho phép xem **status, headers và body**, không chỉ body.
2. `204` được xử lý rõ theo hợp đồng yêu cầu sản phẩm, thay vì coi `null` là thành công.
3. `200` có body 0 byte hoặc JSON `null` có thể dẫn tới `body == null`. Client từ chối dữ liệu thiếu.
4. `{}` hoặc `{"id":null,"name":""}` có thể decode thành DTO nhưng bị kiểm tra trường bắt buộc từ chối.
5. `wrong-type` hoặc `malformed` có thể gây exception **ngay ở bước decode**, trước khi mã kiểm tra field chạy.

**Điểm giới hạn:** vì `toEntity(ProductDto.class)` decode body trước khi trả `ResponseEntity`, nó có thể ném lỗi content type/JSON trước khi bạn tự kiểm tra header. Nếu hợp đồng yêu cầu kiểm tra `Content-Type` **trước khi deserialize**, cần đi qua API cho phép đọc raw response có kiểm soát.

## 6. Strict contract: kiểm tra status, Content-Type và body trước khi parse

Với một API mà **thành công bắt buộc là `200 application/json` và một object đầy đủ**, có thể kiểm tra raw response trong `RestClient.exchange(...)`.

Ví dụ sau dùng `ObjectMapper`, giới hạn response body **64 KiB cho lab**, rồi validate bắt buộc:

~~~java
import java.io.IOException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

class StrictCatalogGateway {

    private static final int MAX_BYTES = 64 * 1024;

    private final RestClient client;
    private final ObjectMapper mapper;

    StrictCatalogGateway(RestClient client, ObjectMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    ProductDto fetch(long productId) {
        return client.get()
                .uri("/products/{id}", productId)
                .accept(MediaType.APPLICATION_JSON)
                .exchange((request, response) -> {
                    int status = response.getStatusCode().value();

                    if (status == 204) {
                        throw new DownstreamContractException(
                                "Product endpoint unexpectedly returned 204");
                    }

                    if (status != 200) {
                        throw new DownstreamContractException(
                                "Unexpected status: " + status);
                    }

                    MediaType mediaType =
                            response.getHeaders().getContentType();

                    if (mediaType == null
                            || !MediaType.APPLICATION_JSON
                                    .isCompatibleWith(mediaType)) {
                        throw new DownstreamContractException(
                                "Expected application/json, got: "
                                + mediaType);
                    }

                    byte[] bytes = response.getBody()
                            .readNBytes(MAX_BYTES + 1);

                    if (bytes.length == 0) {
                        throw new DownstreamContractException(
                                "HTTP 200 with an empty body");
                    }

                    if (bytes.length > MAX_BYTES) {
                        throw new DownstreamContractException(
                                "Response exceeds lab size limit");
                    }

                    ProductDto body;
                    try {
                        body = mapper.readValue(
                                bytes, ProductDto.class);
                    } catch (JsonProcessingException ex) {
                        throw new DownstreamContractException(
                                "Malformed or incompatible ProductDto JSON",
                                ex);
                    }

                    if (body == null || body.id() == null
                            || body.name() == null
                            || body.name().isBlank()) {
                        throw new DownstreamContractException(
                                "ProductDto violates required fields");
                    }

                    return body;
                });
    }
}
~~~

Đây là mẫu **strict cho một contract cụ thể**, không phải cách thay thế toàn bộ message converter của Spring:

- `exchange(...)` đưa quyền kiểm soát status, headers, response body trực tiếp cho callback. **Status handlers cấu hình qua `retrieve().onStatus(...)` không được tự áp dụng cho `exchange(...)`**; vì vậy phải chủ động xử lý status ở đây.
- `readNBytes(MAX_BYTES + 1)` đặt ngưỡng đọc trong thí nghiệm. Nếu response lớn hơn ngưỡng, callback ném lỗi và response được đóng theo vòng đời `exchange`; trong production cân nhắc streaming, quota, timeout và ràng buộc dữ liệu cụ thể.
- Kiểm tra ở đây **chỉ chấp nhận `application/json` tương thích**. Nếu API chính thức hỗ trợ vendor `+json`, cần mở rộng allowlist một cách có chủ đích.
- `ObjectMapper` nên là bean được ứng dụng quản lý với cấu hình JSON phù hợp; không tạo một mapper mới cho mỗi request.

Không đọc `Content-Type` bằng cách so khớp chuỗi tuyệt đối như `"application/json;charset=UTF-8"`; framework `MediaType` hiểu tham số charset và media type.

## 7. RestClient: phân loại exception trước khi quyết định retry

Các nhánh lỗi thường gặp:

| Tình huống | Nhóm lỗi có thể xuất hiện | Đặc điểm |
|---|---|---|
| HTTP 404/409/429/503 | `RestClientResponseException` hoặc subclass tương ứng | Đã nhận HTTP status lỗi khi dùng `retrieve()` mặc định |
| `200 text/html` → `ProductDto` | `UnknownContentTypeException` hoặc lỗi converter tương ứng | Không tìm được converter phù hợp kiểu đích + media type |
| `200` JSON sai cú pháp | `RestClientException`, cause là lỗi JSON/Jackson | HTTP thành công nhưng body không parse được |
| `200` kiểu field bất tương thích | `RestClientException`, cause là lỗi binding/deserialization | Cần xem trường và hợp đồng schema |
| `200` object thiếu field | Có thể decode bình thường | Phải validation ở tầng contract |
| HTTP 204 / 200 body rỗng | Body có thể `null` | Phải quyết định body là tùy chọn hay bắt buộc |
| Không có instance / connect timeout | Lỗi LoadBalancer hoặc transport | Không đồng nghĩa lỗi JSON |

Tên exception cụ thể phụ thuộc Spring Framework, Jackson, request factory và cách gọi `retrieve`/`exchange`. Chẩn đoán nên ghi **toàn bộ cause chain** và các header cần thiết, thay vì hardcode xử lý duy nhất theo một exception class.

### Không “sửa” response sai định dạng bằng retry vô điều kiện

Giả sử một instance trả `{"id":"oops"}`. Retry vào cùng instance gần như chỉ lặp lại lỗi. Retry sang instance khác đôi khi “may mắn” thành công nếu có phiên bản triển khai không đồng nhất, nhưng đây là **triệu chứng contract drift** cần sửa tại backend/version, không phải chính sách phục hồi dài hạn đáng tin cậy.

## 8. WebClient: response rỗng tạo Mono.empty() như thế nào?

`WebClient` thường dùng `retrieve().bodyToMono(ProductDto.class)`. Với response thành công **không có giá trị body để decode**, publisher có thể hoàn thành **không phát phần tử**. Một `Mono.empty()` không phải là `Mono.just(null)`; Reactive Streams không cho phép phần tử `null`.

Ví dụ client đã được tạo từ `@LoadBalanced WebClient.Builder`:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogGateway {

    private final WebClient client;

    ReactiveCatalogGateway(WebClient client) {
        this.client = client;
    }

    Mono<ProductDto> fetch(String scenario) {
        return client.get()
                .uri("/lab/products/{scenario}", scenario)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductDto.class)
                .switchIfEmpty(Mono.error(
                        new DownstreamContractException(
                                "Expected ProductDto, received empty body")))
                .map(body -> {
                    if (body.id() == null
                            || body.name() == null
                            || body.name().isBlank()) {
                        throw new DownstreamContractException(
                                "Invalid ProductDto fields");
                    }
                    return body;
                });
    }
}
~~~

Điều này xử lý **204**, **200 body 0 byte**, hoặc response JSON `null` nếu decoder kết thúc không phát phần tử. Nhưng `switchIfEmpty` **không tự cho biết response status**. Muốn phân biệt 204 hợp lệ với 200 rỗng vi phạm contract, phải xem status và body ở mức `ClientResponse`.

### WebClient.exchangeToMono để phân biệt status/media type

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<ProductDto> strictFetch(
        WebClient client, long productId) {

    return client.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                HttpStatusCode status = response.statusCode();

                if (status.value() == 204) {
                    return response.releaseBody()
                            .then(Mono.error(
                                    new DownstreamContractException(
                                            "204 is invalid for product")));
                }

                if (!status.is2xxSuccessful()) {
                    return response.createException()
                            .flatMap(Mono::error);
                }

                MediaType type = response.headers()
                        .contentType().orElse(null);

                if (type == null ||
                        !MediaType.APPLICATION_JSON.isCompatibleWith(type)) {
                    return response.releaseBody()
                            .then(Mono.error(
                                    new DownstreamContractException(
                                            "Unexpected content type: "
                                            + type)));
                }

                return response.bodyToMono(ProductDto.class)
                        .switchIfEmpty(Mono.error(
                                new DownstreamContractException(
                                        "Empty product payload")))
                        .map(dto -> {
                            if (dto.id() == null || dto.name() == null
                                    || dto.name().isBlank()) {
                                throw new DownstreamContractException(
                                        "Invalid product data");
                            }
                            return dto;
                        });
            });
}
~~~

Với `exchangeToMono`, Spring quản lý việc release body còn dư sau khi publisher trả về hoàn tất. Trong các nhánh không đọc body, gọi `releaseBody()` minh họa ý định giải phóng tài nguyên trước khi báo lỗi. Không dùng `exchange()` đời cũ rồi bỏ qua body mà không nắm vòng đời connection.

**Khác biệt quan trọng:** lỗi decode WebClient có thể xuất hiện dưới dạng `DecodingException` hoặc lỗi codec, trong khi HTTP 4xx/5xx thường phát thành `WebClientResponseException` khi dùng `retrieve()`. Không đồng nhất hai nhóm này.

## 9. OpenFeign: decoder, return type và lỗi dữ liệu

Spring Cloud OpenFeign thường dùng `ResponseEntityDecoder` bọc `SpringDecoder`, kết hợp các HTTP message converter của Spring. Nếu Feign có LoadBalancer trên classpath và không khai báo URL cố định, `FeignBlockingLoadBalancerClient` chọn instance trước khi Feign decoder xử lý response.

Ví dụ:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping(
            value = "/products/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ProductDto> product(@PathVariable("id") long id);
}
~~~

Ở đây:

- `ResponseEntity<ProductDto>` cho phép caller xem status và body sau khi Feign/SpringDecoder xử lý.
- `@GetMapping(produces = ...)` thể hiện kỳ vọng media type theo contract Feign/Spring MVC; **không bảo đảm server/proxy thực sự gửi đúng `Content-Type`**.
- Body vẫn có thể `null` khi no-content. Caller cần chủ động kiểm tra trường hợp endpoint bắt buộc trả object.
- Phản hồi status lỗi thường đi theo **Feign error handling**, ví dụ `FeignException` hoặc `ErrorDecoder` đã tùy biến.
- Phản hồi 2xx có JSON hỏng/sai kiểu có thể phát ra lỗi từ decoder (thường `DecodeException` hoặc cause liên quan Jackson/converter). Không được coi đây là 503 hoặc lỗi discovery.

### Kiểm tra sau khi gọi

~~~java
ResponseEntity<ProductDto> response = catalogFeignClient.product(7L);

if (response.getStatusCode().value() == 204) {
    throw new DownstreamContractException(
            "Product endpoint returned 204");
}

ProductDto body = response.getBody();

if (body == null || body.id() == null
        || body.name() == null
        || body.name().isBlank()) {
    throw new DownstreamContractException(
            "Product response violates contract");
}
~~~

Mã kiểm tra này chỉ chạy **nếu Feign decode thành công**. Với `Content-Type` không phù hợp hoặc JSON sai cú pháp, exception có thể xuất hiện trước khi `product(...)` trả về.

### Không đặt một Decoder toàn cục chỉ để che giấu lỗi

Có thể viết Feign `Decoder` riêng để kiểm tra status/content type hoặc xử lý format đặc biệt. Tuy nhiên, việc áp dụng một decoder “tự đoán JSON dù header là HTML/text” cho tất cả client có nguy cơ:

- Che giấu proxy error page hoặc lỗi phiên bản backend.
- Biến JSON sai thành DTO mặc định, làm sai dữ liệu nghiệp vụ.
- Bỏ qua yêu cầu xử lý no-content/404 của từng endpoint.
- Gây xung đột với `ResponseEntityDecoder` hoặc cấu hình của các named clients.

Nếu thật sự cần decoder tùy biến, nên giới hạn theo **named client/contextId**, kiểm thử với toàn bộ status/media types và duy trì contract riêng cho API liên quan.

## 10. Khi nào cần @Valid hoặc Bean Validation?

Jackson/message converter chủ yếu đảm nhiệm **chuyển bytes thành object**. Việc đọc được một JSON object **không bảo đảm dữ liệu thỏa ràng buộc nghiệp vụ**.

Có thể khai báo DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProductDto(
        @NotNull Long id,
        @NotBlank String name
) {}
~~~

Nếu ứng dụng có Jakarta Bean Validation provider, hãy **gọi validation rõ ràng** cho DTO đọc từ downstream:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

class ProductContractValidator {

    private final Validator validator;

    ProductContractValidator(Validator validator) {
        this.validator = validator;
    }

    ProductDto requireValid(ProductDto product) {
        if (product == null) {
            throw new DownstreamContractException(
                    "Product is required");
        }

        Set<ConstraintViolation<ProductDto>> errors =
                validator.validate(product);

        if (!errors.isEmpty()) {
            throw new DownstreamContractException(
                    "Downstream product violates Bean Validation");
        }

        return product;
    }
}
~~~

**Không mặc định `@NotNull` và `@NotBlank` sẽ tự chạy chỉ vì RestClient/WebClient/Feign decode DTO.** Ràng buộc có thể được áp dụng tự động ở một số entry point có `@Valid`/method validation, nhưng ở mã client đọc response nên có bước validate rõ hoặc một tầng adapter hợp đồng được kiểm thử.

Ví dụ `{"id":null,"name":""}` có thể decode thành `ProductDto(null, "")`; sau đó `Validator` mới báo sai ràng buộc. Nếu `id` là chuỗi không parse thành số, lỗi sẽ xảy ra ở **deserialization**, trước validation.

## 11. Phân biệt lỗi hợp đồng và tình huống nghiệp vụ rỗng hợp lệ

Với endpoint trả danh sách sản phẩm, `[]` là kết quả rỗng hợp lệ:

~~~java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

List<ProductDto> products = catalogRestClient.get()
        .uri("/products?category=unknown")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ProductDto>>() {});
~~~

Tuy nhiên, nếu response thực sự có body rỗng, lời gọi có thể cho `null` thay vì `List.of()`. **Không tự biến mọi `null` thành danh sách rỗng** nếu muốn phát hiện upstream vi phạm contract.

Một quy tắc API rõ ràng thường là:

| Endpoint | Response thành công theo thiết kế | Khi không có dữ liệu |
|---|---|---|
| `GET /products/{id}` | `200 + ProductDto` | `404` theo hợp đồng |
| `GET /products?category=x` | `200 + List<ProductDto>` | `200 + []` |
| `DELETE /products/{id}` | `204` | Không có body là chủ đích |
| `POST /jobs` bất đồng bộ | `202 + Location/status contract` | Không yêu cầu cùng DTO như GET |

Ứng dụng nên quy định ngay từ đầu: **optional field**, **optional resource**, **empty collection** và **no-content status** khác nhau như thế nào. Đây là ranh giới contract, không phải lựa chọn mà LoadBalancer tự quyết định.

## 12. Content negotiation không sửa được backend sai kiểu

Ví dụ:

~~~java
ProductDto product = catalogRestClient.get()
        .uri("/products/7")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ProductDto.class);
~~~

`Accept: application/json` giúp yêu cầu server trả JSON, nhưng các trường hợp sau vẫn có thể xuất hiện:

1. Một bản sao cũ trả field `id` dạng chuỗi trong khi bản sao mới trả số.
2. API gateway/WAF trả login/maintenance HTML nhưng giữ status 200.
3. Backend trả JSON body nhưng header `text/plain`.
4. Response `Content-Type` là `application/problem+json` dù status 2xx do bug.
5. Proxy cắt response giữa chừng khiến JSON không đầy đủ.
6. Backend gửi charset/encoding không phù hợp hoặc gzip bị hỏng.

Cách xử lý nên được chọn theo nguyên nhân:

| Nguyên nhân | Giải pháp ưu tiên |
|---|---|
| Backend đặt sai `Content-Type` | Sửa server/proxy và kiểm tra contract test |
| Schema đổi không tương thích | Version hóa API, triển khai tương thích ngược hoặc phối hợp rollout |
| Trả HTML do proxy/login redirect | Sửa routing/auth/proxy; không cố decode HTML thành DTO |
| Thiếu trường bắt buộc | Bổ sung validation, sửa dữ liệu nguồn hoặc contract |
| JSON bị cắt do network/transport | Kiểm tra transfer encoding, timeout, proxy, body truncation |
| Hệ thống chủ động hỗ trợ vendor `+json` | Cấu hình decoder/media type allowlist theo API, không mở rộng tùy tiện |

Có thể chọn đọc `String` để **chẩn đoán** body text/plain, nhưng phải hạn chế kích thước và bảo vệ dữ liệu nhạy cảm. Không nên “cứ đọc String rồi dùng Jackson parse” làm đường mặc định của production chỉ để bỏ qua lỗi Content-Type.

## 13. Retry và LoadBalancer: lỗi dữ liệu không tự hết khi chuyển instance

Spring Cloud LoadBalancer và các HTTP client có thể hỗ trợ retry trong điều kiện phù hợp, nhưng **response contract error** thường không phải lỗi transient để retry vô điều kiện.

Một trường hợp triển khai lệch phiên bản:

~~~text
catalog-service:
  catalog-1 (v1) -> {"id":"7","name":"Tea"}
  catalog-2 (v2) -> {"id":7,"name":"Tea"}

order-service (new client) -> expects Long id
~~~

Với JSON mapper có coercion, chuỗi `"7"` có thể được chuyển thành `Long 7`, khiến lỗi **không xuất hiện**. Vì vậy test cần dùng giá trị thực sự không tương thích như `"oops"` hoặc bật cấu hình strict coercion nếu contract yêu cầu. Đừng kết luận schema hoàn toàn tương thích chỉ vì một sample được parse thành công.

Nếu `catalog-1` trả lỗi decode:

- Retry theo same instance có thể lặp lại cùng lỗi.
- Retry sang `catalog-2` có thể thành công và **che giấu rollout sai**, khiến lỗi chỉ xuất hiện theo xác suất.
- Không có bảo đảm rằng một codec exception được load-balancer retry policy tự động xem là retryable.
- Việc tự retry mọi exception có thể làm bùng nổ request và che khuất root cause.

**Cách đúng:** phát hiện sự khác biệt theo instance/version, sửa hợp đồng hoặc rollback/canary, dùng contract tests và phân biệt lỗi thuộc server từ lỗi transport.

### Khi nào retry là hợp lý?

Retry có thể hữu ích cho lỗi mạng tạm thời hoặc một số HTTP 502/503/504 theo policy, khi thao tác có thể lặp an toàn và body request phát lại được. **Không bật retry cho JSON decode failure hoặc sai Content-Type chỉ vì muốn “thử bản sao khác”** mà chưa có nguyên nhân rõ và cơ chế kiểm soát.

Với POST/PUT có tác dụng phụ, phải xem cả idempotency và tổng deadline.

## 14. Quan sát và phân loại lỗi để không chẩn đoán nhầm

Nên ghi đủ các chiều sau, thông qua interceptor/observation nếu được cấu hình:

| Trường | Ý nghĩa |
|---|---|
| `serviceId` | Tên dịch vụ logic của LoadBalancer |
| `instanceId` / host:port | Instance thực tế đã được chọn |
| `httpStatus` | Có nhận HTTP response và status nào? |
| `responseContentType` | Media type thực tế từ response |
| `expectedType` | DTO hoặc schema mà client muốn decode |
| `bodyLength` (giới hạn và quyền riêng tư) | Phân biệt 0 byte với JSON `null`/`{}` |
| `errorCategory` | NO_INSTANCE, NETWORK, HTTP_STATUS, MEDIA_TYPE, DECODE, VALIDATION |
| `contractVersion` | Phiên bản client/server nếu được cung cấp |
| `traceId` / `requestId` | Đối chiếu với log backend/gateway |
| `attempt` | Phân biệt lần thử đầu và retry |

Ví dụ log đề xuất:

~~~text
traceId=demo-42 serviceId=catalog-service instanceId=catalog-2
httpStatus=200 responseContentType=text/html expectedType=ProductDto
errorCategory=MEDIA_TYPE bodyLength=37 attempt=1
~~~

Đây **không phải những field mặc định** mà Spring Cloud tự sinh. Cần lấy từ HTTP client, response handler và tracing, có giới hạn cardinality để không đưa URL đầy đủ có ID tùy ý thành metric tag.

**Không log toàn bộ body production** khi có token, dữ liệu khách hàng, cookie hoặc tài liệu nhạy cảm. Nếu cần điều tra, ghi content type, độ dài, hash hoặc một đoạn body đã được lọc và giới hạn theo chính sách bảo mật.

### Một sơ đồ quyết định chẩn đoán

~~~mermaid
flowchart TD
    A["Lời gọi downstream thất bại"]
    B{"Đã chọn ServiceInstance?"}
    C["Kiểm tra discovery / LoadBalancer"]
    D{"Đã nhận HTTP response?"}
    E["Kiểm tra network / timeout"]
    F{"Status là 2xx?"}
    G["Map status / error contract"]
    H{"Body có bắt buộc?"}
    I["204/200 empty theo contract"]
    J{"Content-Type phù hợp?"}
    K["Media type mismatch"]
    L{"Decode thành công?"}
    M["JSON / schema mismatch"]
    N{"Validation hợp lệ?"}
    O["Dữ liệu thiếu/sai nghĩa"]
    P["Thành công"]
    A --> B
    B -->|"Không"| C
    B -->|"Có"| D
    D -->|"Không"| E
    D -->|"Có"| F
    F -->|"Không"| G
    F -->|"Có"| H
    H -->|"Không / rỗng"| I
    H -->|"Có dữ liệu"| J
    J -->|"Không"| K
    J -->|"Có"| L
    L -->|"Không"| M
    L -->|"Có"| N
    N -->|"Không"| O
    N -->|"Có"| P
~~~

Sơ đồ mang tính hướng dẫn: việc xác định “đã chọn instance” và “đã nhận response” cần dữ liệu instrumentation, không chỉ suy ra từ một exception.

## 15. Bài thực hành và ma trận kiểm thử

### Phần A — RestClient và server giả lập

1. Khởi chạy controller ở mục 4 trên port `8081`.
2. Khai báo `catalog-service` trong `SimpleDiscoveryClient` và `@LoadBalanced RestClient.Builder`.
3. Gọi từng endpoint trong bảng dưới, trước tiên bằng `retrieve().toEntity(ProductDto.class)`.
4. Ghi status, `Content-Type`, có body hay không, loại exception và cause.
5. Dùng gateway strict ở mục 6 để kiểm tra lỗi **trước deserialize**; so sánh lỗi với cách decode thông thường.
6. Với `object-empty` và `field-null`, xác nhận rằng **decode được chưa có nghĩa hợp lệ**.
7. Thử đổi client target sang `String.class` để xem body text có thể đọc được; **không dùng việc đọc được chuỗi để coi API đã đúng contract**.

### Phần B — WebClient

1. Tạo `WebClient` từ `@LoadBalanced WebClient.Builder`.
2. Gọi cùng các endpoint bằng `bodyToMono(ProductDto.class)`.
3. Dùng `switchIfEmpty` để từ chối response không có giá trị.
4. Dùng `exchangeToMono` để tách 204 khỏi 200 rỗng và kiểm tra `Content-Type`.
5. Quan sát lỗi decode/codec khác với `WebClientResponseException` của HTTP status.

### Phần C — OpenFeign

1. Đăng ký `@FeignClient(name="catalog-service")` và bật `@EnableFeignClients`.
2. Sử dụng return type `ResponseEntity<ProductDto>` và gọi server giả lập.
3. Quan sát no-content có thể được xử lý tại caller; JSON sai kiểu có thể ném exception ở decoder.
4. Chứng minh trường hợp `200 text/html` không phải “không có instance” bằng trace chọn đích và header phản hồi.
5. Không bật retry mặc định cho mọi lỗi decode.

### Bảng kiểm kết quả mong đợi

| Scenario | RestClient `toEntity(ProductDto.class)` | WebClient `bodyToMono(ProductDto.class)` | Kết luận |
|---|---|---|---|
| `valid` | DTO hợp lệ | Phát DTO hợp lệ | PASS |
| `empty-204` | Không có DTO; status 204 | Thường hoàn thành không phát DTO | Hợp lệ chỉ nếu contract cho phép |
| `empty-200` | Body có thể `null` | Thường `Mono.empty()` | Vi phạm nếu bắt buộc body |
| `json-null` | Có thể không có DTO | Thường không phát DTO | JSON hợp lệ nhưng thiếu object |
| `object-empty` | Có thể DTO với fields `null` | Có thể phát DTO với fields `null` | Cần validation |
| `field-null` | Có thể DTO với field null/rỗng | Tương tự | Cần validation |
| `wrong-type` | Thường lỗi deserialization | Thường lỗi decoding | Sai schema |
| `malformed` | Lỗi parse JSON | Lỗi parse JSON | Body không hợp lệ |
| `json-as-text` | Thường không có converter phù hợp `ProductDto` | Thường lỗi unsupported media type | Sai `Content-Type` |
| `html` | Thường không decode thành `ProductDto` | Thường lỗi media type | Có thể lỗi proxy/gateway |
| Endpoint không tồn tại | Status 404, `retrieve()` mặc định báo lỗi | `retrieve()` mặc định báo lỗi status | Xử lý HTTP error contract |

“Thường” là chủ ý: Jackson coercion, codecs, custom converters, error handlers và HTTP client versions có thể thay đổi exception hoặc cách biểu diễn empty response. **Bài kiểm thử phải ghi lại hành vi của stack version thực tế.**

## 16. Checklist trước khi đưa vào production

- Endpoint có quy định rõ khi nào trả 204, 404, 200 với `[]` và 200 với object không?
- DTO client có những field **bắt buộc**, optional và constraints nào?
- `Accept` và response `Content-Type` có phù hợp media types mà API hỗ trợ?
- Có phân biệt HTTP 200 body 0 byte, JSON `null` và JSON `{}`?
- JSON converter/codec và các thiết lập coercion có tương thích phiên bản server/client?
- Body có được validate **sau deserialize** thay vì chỉ dựa vào annotation?
- RestClient/WebClient/Feign đang dùng error handling đúng cho status và decode?
- Lỗi decoder có bị biến thành `null`/DTO mặc định, gây mất dữ liệu hoặc che giấu lỗi không?
- Retry có chỉ áp dụng cho lỗi transient an toàn, không dùng để che contract drift?
- Log có xác định được `serviceId`, selected instance, status, content type, lỗi decode và contract version?
- Contract tests có phủ cả no-content, malformed JSON, sai kiểu, thiếu field và sai media type?
- Trong rolling deployment, các bản sao có giữ **tương thích ngược** với client đang chạy không?

**Kết luận:** Spring Cloud LoadBalancer đảm nhiệm **chọn `ServiceInstance`**; phần đọc response thuộc `RestClient`, `WebClient` hoặc Feign decoder. Để giao tiếp giữa dịch vụ ổn định, cần phân biệt **không có body**, **body có nhưng sai JSON/schema**, **Content-Type không phù hợp**, **HTTP status lỗi**, và **lỗi transport/discovery**. Chỉ khi phân loại đúng mới có thể xử lý null, validate dữ liệu, điều chỉnh contract, chẩn đoán instance hoặc retry một cách phù hợp.

**Tài liệu tham khảo chính thức:**

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Cloud OpenFeign – Features](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

