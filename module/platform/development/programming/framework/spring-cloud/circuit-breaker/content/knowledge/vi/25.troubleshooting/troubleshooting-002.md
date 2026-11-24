# HTTP trả lỗi nhưng vẫn được ghi nhận là thành công

Một dịch vụ phụ thuộc có thể trả HTTP 500, 503 hoặc 429 nhưng Circuit Breaker vẫn tăng bộ đếm thành công. Tình huống này thường xảy ra khi HTTP client chuyển response lỗi thành một đối tượng kết quả bình thường, hoặc một toán tử xử lý lỗi đã biến tín hiệu lỗi thành tín hiệu hoàn tất thành công trước khi Publisher đi qua Circuit Breaker.

Resilience4j không tự phân tích mọi HTTP status. Circuit Breaker quan sát kết quả mà lời gọi được bảo vệ phát ra: một giá trị trả về được xem là thành công theo mặc định; một exception hoặc error signal được phân loại theo cấu hình mới được tính là failure. Vì vậy, muốn chẩn đoán đúng cần lần theo response từ HTTP client, adapter, ErrorDecoder hoặc WebClient operator tới đúng ranh giới Circuit Breaker.

Bài này thuộc chương **Chẩn đoán sự cố** của module SPRING_CLOUD_CIRCUIT_BREAKER. Nội dung hướng dẫn nhận diện nguyên nhân, sửa cách ánh xạ HTTP status, cấu hình `recordResult` khi chủ ý trả response object, tránh nuốt lỗi trước breaker và xác minh bằng event, metric cùng kiểm thử.

## 1. Circuit Breaker nhìn thấy kết quả nào?

Circuit Breaker không nhìn trực tiếp vào ý nghĩa nghiệp vụ của một response HTTP. Nó quan sát kết quả của Supplier hoặc Publisher nằm bên trong ranh giới được bảo vệ.

| Kết quả từ lời gọi được bảo vệ | Cách Circuit Breaker thường ghi nhận |
|---|---|
| Trả về đối tượng Product hoặc ResponseEntity bình thường | Success |
| Trả về ResponseEntity có status 500 nhưng không ném exception | Success theo mặc định, trừ khi có recordResult |
| Ném exception | Failure theo predicate và cấu hình exception |
| Publisher phát onError | Failure theo predicate và cấu hình exception |
| Publisher hoàn tất onComplete sau khi onErrorResume trả giá trị dự phòng | Success nếu việc phục hồi xảy ra trước breaker |
| Breaker OPEN và từ chối lời gọi | Call not permitted; không phải một lần HTTP request tới dependency |

Ví dụ, adapter có thể trả một đối tượng kết quả như sau:

~~~java
public record CatalogResult(
    int httpStatus,
    String body
) {}
~~~

Nếu lời gọi trả `new CatalogResult(503, "...")` bình thường, Circuit Breaker không tự hiểu rằng status 503 là lỗi. Với breaker, Supplier đã trả về một giá trị hợp lệ. Muốn ghi nhận đó là failure, cần chuyển response thành exception trước khi rời ranh giới hoặc cấu hình predicate `recordResult` để đánh giá kết quả.

Cần phân biệt ba loại trạng thái:

- **HTTP status**: kết quả ở tầng giao thức, ví dụ 404, 429 hoặc 503.
- **Exception/error signal**: cách client truyền lỗi tới code gọi.
- **Circuit Breaker outcome**: success, failure, ignored hoặc not permitted theo cách Resilience4j phân loại kết quả.

Một HTTP 500 có thể trở thành exception, một đối tượng ResponseEntity hoặc một payload chứa mã lỗi trong HTTP 200. Ba cách biểu diễn đó có thể dẫn tới ba kết quả Circuit Breaker khác nhau.

## 2. Dấu hiệu nhận biết lỗi HTTP bị tính là success

Hãy bắt đầu từ các dấu hiệu có thể quan sát:

- Log downstream cho thấy trả 500/503, nhưng metric Circuit Breaker vẫn tăng successful calls.
- Failure rate bằng 0 hoặc thấp bất thường dù API client nhận nhiều response lỗi.
- Breaker không mở dù dependency trả lỗi liên tục và số mẫu đã vượt `minimumNumberOfCalls`.
- Response lỗi được trả về dưới dạng DTO hoặc `ResponseEntity`, thay vì exception.
- Code có `onErrorResume`, `onErrorReturn`, `onErrorComplete` hoặc handler chuyển status lỗi thành giá trị trước khi gọi breaker.
- Custom ErrorDecoder hoặc HTTP status handler trả một đối tượng kết quả thay vì ném exception.
- Payload chứa `status: ERROR` hoặc `success: false` nhưng HTTP status vẫn là 200.

Một breaker không mở ngay sau một response lỗi không nhất thiết là lỗi cấu hình. Nó chỉ đánh giá tỷ lệ sau khi đủ số mẫu tối thiểu, và chỉ mở khi tỷ lệ vượt ngưỡng. Khi điều tra, hãy kiểm tra lần lượt: lời gọi thực tế có đi qua breaker không, breaker ID nào đang được dùng, nó nhận exception hay giá trị, và sliding window đã đủ mẫu chưa.

## 3. Nguyên nhân thường gặp ở các HTTP client

| Client hoặc cách gọi | Hành vi cần kiểm tra |
|---|---|
| OpenFeign | ErrorDecoder có chuyển response non-2xx thành exception hay custom decoder trả kết quả bình thường? Có bật tùy chọn giải mã 404 không? |
| WebClient `retrieve()` | Mặc định 4xx/5xx tạo WebClientResponseException; có `onStatus` nào trả `Mono.empty()` để bỏ qua lỗi không? |
| WebClient `exchangeToMono()` | Nhánh status lỗi có tạo `Mono.error`, hay vẫn decode body thành DTO bình thường? |
| RestTemplate | ResponseErrorHandler mặc định thường ném exception cho 4xx/5xx; custom handler có bỏ qua status lỗi không? |
| RestClient | Status handler có ném exception hay trả response như một giá trị bình thường? |
| HTTP wrapper tự viết | Có chuyển status lỗi thành `ApiResult` mà không ném exception không? |
| API envelope | Server có trả HTTP 200 nhưng body chứa mã lỗi nghiệp vụ hoặc mã lỗi nội bộ không? |

Không nên mặc định tất cả HTTP client có cùng hành vi. Hãy kiểm tra cấu hình và loại return type cụ thể đang được sử dụng. Cùng một server response 503, một client có thể ném exception trong khi client khác trả `ResponseEntity` cho code gọi tự xử lý.

## 4. Sửa với WebClient: giữ error signal trước Circuit Breaker

Với `WebClient.retrieve()`, status 4xx/5xx mặc định được chuyển thành `WebClientResponseException`. Nếu code không ghi đè hành vi đó bằng status handler làm mất lỗi, Circuit Breaker có thể nhận error signal.

Ví dụ:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogService {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakerFactory;

    public ReactiveCatalogService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> breakerFactory) {
        this.webClient = webClient;
        this.breakerFactory = breakerFactory;
    }

    public Mono<Product> findProduct(String id) {
        Mono<Product> remoteCall = webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .onStatus(HttpStatusCode::isError, response ->
                response.createException().flatMap(Mono::error))
            .bodyToMono(Product.class);

        return breakerFactory.create("catalog-read").run(
            remoteCall,
            error -> Mono.error(
                new CatalogUnavailableException(id, error))
        );
    }
}
~~~

Đoạn `onStatus` chuyển response lỗi thành error signal. Khi Publisher được subscribe qua Circuit Breaker, lỗi đó được breaker quan sát. Callback fallback nhận nguyên nhân lỗi và trả một Publisher thay thế hoặc tiếp tục phát lỗi.

Nếu dùng `exchangeToMono()`, hãy kiểm tra status trước khi decode body:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .exchangeToMono(response -> {
        if (response.statusCode().isError()) {
            return response.createException().flatMap(Mono::error);
        }
        return response.bodyToMono(Product.class);
    });
~~~

Đây là cách rõ ràng khi cần tự quyết định cách xử lý từng status. Đừng decode response 503 thành Product hoặc một DTO lỗi rồi phát ra bình thường nếu mục tiêu là để Circuit Breaker tính đó là failure.

### Lỗi thường gặp: onStatus trả Mono.empty()

Đoạn sau chủ động nói với WebClient rằng status khớp predicate không cần chuyển thành lỗi:

~~~java
.retrieve()
.onStatus(HttpStatusCode::isError, response -> Mono.empty())
.bodyToMono(CatalogEnvelope.class);
~~~

Khi callback trả `Mono.empty()`, WebClient không tạo error signal cho status đó và tiếp tục xử lý body như response bình thường. Nếu body được decode thành `CatalogEnvelope`, Circuit Breaker thường ghi nhận success.

Cách này có thể đúng nếu ứng dụng chủ ý xem status đó là kết quả nghiệp vụ bình thường. Nếu 500/503 phải được tính là lỗi availability, hãy tạo exception thay vì trả `Mono.empty()`.

## 5. Sửa với OpenFeign: ErrorDecoder phải trả exception phù hợp

Feign gọi `ErrorDecoder` khi nhận response được xem là non-success theo quy tắc của Feign. Decoder cần trả về một exception để lời gọi kết thúc bằng lỗi. Nếu code custom chuyển status lỗi thành một kết quả bình thường ở tầng khác, Circuit Breaker có thể không nhận được failure.

Ví dụ ErrorDecoder phân loại lỗi:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

public class CatalogErrorDecoder implements ErrorDecoder {
    private final ErrorDecoder delegate = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return new ProductNotFoundException(
                "Không tìm thấy sản phẩm");
        }

        if (status == 503 || status == 502 || status == 504) {
            return new CatalogUnavailableException(
                "Catalog Service tạm thời không khả dụng");
        }

        return delegate.decode(methodKey, response);
    }
}
~~~

Trong ví dụ, 404 là kết quả nghiệp vụ nên được ánh xạ thành exception riêng để ứng dụng có thể bỏ qua trong failure rate nếu cần. Các status 502/503/504 tạo exception availability. Decoder mặc định xử lý các status còn lại.

Nếu 404 được cấu hình để giải mã như response bình thường, chẳng hạn qua tùy chọn dismiss/decode 404 của Feign, hãy xác nhận decoder và return type đang được dùng. Khi đó, response 404 có thể đi vào decoder dữ liệu thay vì ErrorDecoder. Hành vi cụ thể phụ thuộc phiên bản Feign và cấu hình Spring Cloud OpenFeign.

Đừng trả về một DTO `CatalogError` như giá trị hợp lệ cho status 503 nếu breaker cần tính failure. Nếu API contract yêu cầu trả DTO lỗi cho caller, hãy chuyển status thành exception bên trong ranh giới bảo vệ, để fallback hoặc tầng ngoài chuyển exception thành HTTP response phù hợp sau khi breaker đã ghi nhận kết quả.

## 6. Sửa với RestTemplate hoặc RestClient

RestTemplate mặc định dùng ResponseErrorHandler để chuyển nhiều response 4xx/5xx thành exception. Nếu ứng dụng thay handler và cho phép mọi response đi qua như bình thường, Circuit Breaker có thể chỉ thấy một ResponseEntity.

Ví dụ khi chủ ý trả ResponseEntity, cần phân loại kết quả bằng `recordResult` hoặc chuyển status thành exception trong adapter:

~~~java
ResponseEntity<Product> response =
    restTemplate.getForEntity(url, Product.class);

if (response.getStatusCode().isError()) {
    throw new CatalogHttpException(
        response.getStatusCode().value());
}

return response.getBody();
~~~

Cách này khiến lời gọi kết thúc bằng exception với status lỗi. Nếu cần trả ResponseEntity nguyên trạng cho caller, hãy dùng `recordResult` để Circuit Breaker nhận biết status cần tính là failure.

Với RestClient, kiểm tra status handler và cách method trả response. Nếu status handler không ném exception, status lỗi có thể vẫn trở thành kết quả bình thường. Hãy thống nhất quy ước trong adapter để service không phải tự suy đoán status ở nhiều nơi.

## 7. Khi nào nên dùng recordResult?

Có trường hợp ứng dụng cố ý muốn trả response object, ví dụ cần giữ nguyên HTTP status và body cho tầng API gateway hoặc adapter. Khi đó, có thể dùng `recordResult` của Resilience4j để xác định giá trị trả về nào phải được ghi nhận là failure.

Ví dụ với `ResponseEntity`:

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogResultClassification() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .recordResult(result -> {
            if (result instanceof ResponseEntity<?> response) {
                int status = response.getStatusCode().value();
                return status == 429 || status >= 500;
            }
            return false;
        })
        .ignoreExceptions(ProductNotFoundException.class)
        .build();

    return factory -> factory.configure(
        builder -> builder.circuitBreakerConfig(config),
        "catalog-response"
    );
}
~~~

Predicate trả về `true` khi response cần được tính là failure. Trong ví dụ, 429 và mọi status từ 500 trở lên là failure; các status khác là kết quả thành công theo predicate. Hãy thay điều kiện theo hợp đồng API. Ví dụ, 429 do quota người dùng có thể là kết quả nghiệp vụ, còn 409 hoặc 422 thường không nên làm breaker mở nếu dependency đã xử lý request bình thường.

Khi dùng `recordResult`, cần hiểu rằng predicate phải phân loại đầy đủ kiểu kết quả có thể trả về. Một kết quả không khớp predicate sẽ được xem là thành công theo quy tắc recordResult. Không cấu hình predicate chỉ nhận diện 500 nếu ứng dụng còn có 502, 503, 504 hoặc 429 cần được ghi nhận.

Nếu dùng `recordExceptions` để giới hạn các exception được tính là failure, các exception không khớp danh sách có thể bị xem là success, trừ những exception được ignore. Hãy tránh cấu hình danh sách quá hẹp khiến lỗi mới phát sinh bị tính nhầm thành thành công. Khi chỉ cần loại trừ một vài lỗi nghiệp vụ, `ignoreExceptions` thường dễ hiểu hơn.

## 8. Phân biệt HTTP lỗi và lỗi nằm trong payload

Một số API luôn trả HTTP 200 nhưng biểu diễn lỗi ở body:

~~~json
{
  "success": false,
  "code": "CATALOG_UNAVAILABLE",
  "message": "Dependency is unavailable"
}
~~~

Ở tầng HTTP, đây là response thành công. Nếu adapter decode body thành DTO và trả về bình thường, Circuit Breaker ghi nhận success. Nếu hợp đồng ứng dụng quy định `success: false` là lỗi availability, cần chuyển DTO đó thành exception hoặc dùng `recordResult` để phân loại.

Ví dụ chuyển payload thành exception:

~~~java
CatalogEnvelope envelope = catalogClient.fetch(id);

if (!envelope.success()
        && "CATALOG_UNAVAILABLE".equals(envelope.code())) {
    throw new CatalogUnavailableException(envelope.message());
}

return envelope.product();
~~~

Không nên xem mọi `success: false` là lỗi hạ tầng. Một payload có thể biểu diễn không tìm thấy dữ liệu, không đủ quyền hoặc vi phạm quy tắc nghiệp vụ. Chỉ những kết quả phản ánh dependency không thể phục vụ hoặc suy giảm mới nên ảnh hưởng failure rate của breaker.

## 9. Tránh nuốt lỗi trước khi đi vào Circuit Breaker

Với reactive flow, vị trí đặt operator xử lý lỗi quyết định breaker có nhìn thấy lỗi hay không.

Sai nếu mục tiêu là ghi nhận lỗi gốc:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .onErrorResume(error ->
        cache.findUsable(id)); // Lỗi đã được phục hồi trước breaker.

return breaker.run(remoteCall, error -> fallback(id, error));
~~~

Khi cache trả về Product, Publisher hoàn tất bình thường. Circuit Breaker chỉ thấy success và không biết lời gọi Catalog đã thất bại.

Đúng hơn là đặt fallback trong callback của Circuit Breaker:

~~~java
Mono<Product> remoteCall = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);

return breaker.run(
    remoteCall,
    error -> cache.findUsable(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, error)))
);
~~~

Trong trường hợp này, Circuit Breaker quan sát lỗi của lời gọi chính trước khi fallback tạo kết quả thay thế. Nếu muốn xử lý lỗi sau breaker, có thể đặt `onErrorResume` trên Publisher đã được bảo vệ. Tránh đặt operator phục hồi thành giá trị thành công bên trong Publisher gốc trước khi gọi `run`.

Với lời gọi đồng bộ, nguyên tắc tương tự: không bắt exception rồi trả một DTO success-like trước khi Supplier đi vào breaker. Nếu cần đổi loại exception, dùng `throw new ... (cause)` để vẫn giữ error outcome.

## 10. Phân loại lỗi nghiệp vụ để không mở breaker sai

Không phải mọi HTTP 4xx đều là lỗi availability. Một số status thể hiện dependency đã hoạt động bình thường và trả lời theo quy tắc nghiệp vụ.

| Status/kết quả | Phân loại thường gặp | Ảnh hưởng tới breaker |
|---|---|---|
| 404 không tìm thấy sản phẩm | Kết quả nghiệp vụ | Thường ignore |
| 400/422 request không hợp lệ | Lỗi request/nghiệp vụ | Thường ignore |
| 401/403 credential service sai | Lỗi tích hợp hoặc cấu hình | Cảnh báo riêng; quyết định record/ignore có chủ đích |
| 409 xung đột trạng thái | Kết quả nghiệp vụ | Thường ignore |
| 429 throttling từ dependency | Quá tải/rate limit | Có thể record |
| 500/502/503/504 | Lỗi server hoặc gateway | Thường record |
| Timeout/kết nối thất bại | Lỗi hạ tầng | Record |
| HTTP 200 nhưng payload báo dependency unavailable | Lỗi theo hợp đồng ứng dụng | Chuyển thành exception hoặc recordResult |

Cần xác định nguồn gốc 429. Nếu đây là quota nghiệp vụ của khách hàng, không nên mở breaker của dependency. Nếu đây là rate limit do dependency đang quá tải, nó có thể là tín hiệu cần record và có thể retry có giới hạn theo Retry-After.

## 11. Kiểm tra Circuit Breaker có nhận đúng outcome

Sau khi sửa adapter hoặc cấu hình, hãy xác minh bằng một test có kiểm soát. Không chỉ kiểm tra HTTP response mà cần kiểm tra metric hoặc event của đúng breaker ID.

Một kịch bản kiểm tra:

1. Gọi dependency trả 200; xác nhận success tăng.
2. Gọi dependency trả 503; xác nhận failure tăng hoặc recordResult phân loại response là failure.
3. Gọi dependency trả 404; xác nhận lỗi nghiệp vụ được bỏ qua nếu cấu hình yêu cầu.
4. Với WebClient, xác nhận onStatus tạo error signal thay vì trả Mono.empty cho status availability.
5. Với Feign, xác nhận ErrorDecoder trả exception cho status cần record.
6. Với API envelope HTTP 200, xác nhận payload lỗi được ánh xạ theo hợp đồng ứng dụng.
7. Gây đủ số lần lỗi để vượt minimumNumberOfCalls; xác nhận failure rate và trạng thái breaker thay đổi theo threshold.
8. Kiểm tra fallback được gọi sau khi breaker đã quan sát lỗi của lời gọi chính.
9. Mở breaker và gửi request mới; xác nhận CallNotPermitted không tạo thêm HTTP request tới dependency.

Có thể theo dõi các event như `onSuccess`, `onError`, `onIgnoredError`, `onStateTransition` và `onCallNotPermitted`. Metric của Resilience4j thường cung cấp số lời gọi thành công, thất bại, lời gọi chậm và bị từ chối. Tên metric và tag cần được xác nhận theo phiên bản tích hợp.

Nếu log server ghi 503 nhưng breaker success tăng, hãy log thêm:
- Breaker ID được tạo trong `CircuitBreakerFactory.create(...)`.
- HTTP status nhận được từ client.
- Kiểu đối tượng trả về từ Supplier hoặc Publisher.
- Exception class hoặc error signal có đi qua ranh giới không.
- Có `onErrorResume`, custom decoder hoặc status handler nào biến lỗi thành giá trị không.
- Có cấu hình `recordResult`, `recordExceptions` hoặc `ignoreExceptions` nào làm thay đổi phân loại không.

## 12. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Downstream trả HTTP lỗi"] --> B{"HTTP client phát exception/error signal?"}
    B -- "Có" --> C{"Error có đi qua Circuit Breaker?"}
    C -- "Có" --> D{"Exception bị ignore hoặc không được record?"}
    D -- "Có" --> E["Kiểm tra ignoreExceptions / recordExceptions"]
    D -- "Không" --> F["Kiểm tra minimum calls và failure threshold"]
    C -- "Không" --> G["Kiểm tra catch/onErrorResume trước breaker"]
    B -- "Không" --> H["Client trả response object hoặc DTO"]
    H --> I{"Có recordResult phân loại status/payload?"}
    I -- "Có" --> F
    I -- "Không" --> J["Chuyển lỗi thành exception hoặc thêm recordResult"]
~~~

Sơ đồ giúp khoanh vùng nguyên nhân trước khi thay đổi ngưỡng. Không tăng failureRateThreshold hoặc giảm minimumNumberOfCalls để che một lỗi phân loại. Trước hết cần bảo đảm breaker nhận đúng kết quả.

## 13. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Giả định Circuit Breaker tự đọc HTTP status | Response 500 dưới dạng object bị tính success | Chuyển status thành exception hoặc cấu hình recordResult |
| Dùng onStatus trả Mono.empty cho 5xx | WebClient tiếp tục như response bình thường | Phát Mono.error cho status cần record |
| Dùng onErrorResume trước breaker | Lỗi chính được thay bằng giá trị success-like | Đưa fallback vào callback run hoặc đặt xử lý sau breaker |
| Custom ErrorDecoder trả DTO thay vì exception | Feign invocation có thể hoàn tất bình thường | Trả exception cho status cần record |
| Bỏ qua tất cả 4xx/5xx | Breaker không phản ánh availability | Phân loại theo status và hợp đồng API |
| recordExceptions quá hẹp | Exception mới có thể bị xem là success | Kiểm tra predicate và thêm loại lỗi có chủ đích |
| Chỉ nhìn state CLOSED | Bỏ qua failure rate chưa đạt ngưỡng | Kiểm tra metric, event và minimumNumberOfCalls |
| Tăng ngưỡng để breaker không mở | Che giấu lỗi phân loại hoặc lỗi dependency | Sửa adapter và outcome trước, sau đó mới hiệu chỉnh threshold |

## Kết luận

HTTP trả lỗi nhưng Circuit Breaker ghi nhận thành công thường là dấu hiệu status đã được chuyển thành một giá trị bình thường hoặc error signal bị phục hồi trước ranh giới bảo vệ. Hãy kiểm tra hành vi của HTTP client, ErrorDecoder và các status handler; bảo đảm lỗi availability trở thành exception/error signal, hoặc dùng `recordResult` khi chủ ý trả response object. Phân loại riêng lỗi nghiệp vụ, tránh nuốt lỗi trước breaker và xác minh bằng metric cùng event của đúng ID. Khi Circuit Breaker nhận đúng outcome, failure rate và trạng thái CLOSED/OPEN/HALF_OPEN mới phản ánh đúng sức khỏe của dependency.

