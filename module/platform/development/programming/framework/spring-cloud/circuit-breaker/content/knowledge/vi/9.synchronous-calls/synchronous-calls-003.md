# Phân biệt lỗi tạo yêu cầu với lỗi nhận phản hồi

## Vì sao cần phân biệt hai nhóm lỗi?

Khi một ứng dụng Spring Cloud gọi dịch vụ phụ thuộc theo kiểu đồng bộ, thread gọi sẽ chờ cho đến khi HTTP client trả kết quả hoặc ném ngoại lệ. Circuit Breaker quan sát kết quả của lời gọi để đánh giá tình trạng dịch vụ phụ thuộc. Vì vậy, cần xác định lỗi phát sinh ở giai đoạn nào và lỗi đó có thực sự phản ánh khả năng phục vụ của dịch vụ đích hay không.

Hai nhóm thường gặp là:

- **Lỗi tạo yêu cầu:** ứng dụng không tạo được request hợp lệ trước khi gửi đi, chẳng hạn dữ liệu đầu vào thiếu, URI sai, tham số không hợp lệ hoặc chuyển đổi body request thất bại ở phía client.
- **Lỗi trong quá trình gửi và nhận phản hồi:** request đã được đưa vào HTTP client nhưng không thể kết nối, không gửi được, hết thời gian chờ, hoặc nhận được phản hồi báo lỗi từ dịch vụ phụ thuộc.

Lỗi ở nhóm đầu thường phản ánh dữ liệu hoặc mã của ứng dụng gọi. Nếu tính chúng vào failure rate, Circuit Breaker có thể mở dù dịch vụ phụ thuộc vẫn hoạt động bình thường. Nhóm thứ hai thường cung cấp tín hiệu về kết nối hoặc khả năng phục vụ của dịch vụ đích và thường cần được ghi nhận.

## Các giai đoạn của một lời gọi đồng bộ

Một lời gọi HTTP đồng bộ có thể được nhìn theo trình tự:

```text
Nhận dữ liệu đầu vào
        |
        v
Kiểm tra dữ liệu và tạo URI/request
        |
        v
Chuyển đổi request body
        |
        v
Lấy kết nối / phân giải DNS / TLS / gửi request
        |
        v
Chờ response headers và body
        |
        v
Phân tích response và xử lý HTTP status
        |
        v
Trả kết quả cho mã nghiệp vụ
```

Lỗi có thể phát sinh ở nhiều điểm. Ví dụ, URI sai có thể được phát hiện trước khi có bất kỳ hoạt động mạng nào. Ngược lại, `Connection refused`, lỗi DNS, lỗi bắt tay TLS hoặc read timeout xuất hiện trong quá trình HTTP client giao tiếp với dịch vụ phụ thuộc. Phản hồi HTTP 500 cho biết server đã trả lời nhưng báo lỗi; đây không phải lỗi tạo request.

Timeout khi chờ response cần được xử lý cẩn thận. Client không nhận được response trong thời hạn quy định, nhưng điều đó không chứng minh server chưa xử lý request. Server có thể đã thực hiện thao tác ghi dữ liệu rồi response bị mất trên đường về. Với thao tác không idempotent như tạo đơn hàng hoặc trừ tiền, retry mù quáng có thể tạo tác động trùng lặp.

## Nhận diện lỗi tạo request

Các lỗi tạo request thường gặp gồm:

| Lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Kiểm tra đầu vào thất bại | Mã sản phẩm rỗng, số lượng âm, thiếu trường bắt buộc. | Trả lỗi validation ở tầng ứng dụng trước khi gọi Circuit Breaker. |
| Tạo URI thất bại | Base URL hoặc path parameter không hợp lệ. | Kiểm tra cấu hình và encode tham số trước lời gọi. |
| Chuyển đổi request body thất bại | Object không thể serialize thành JSON do cấu trúc hoặc converter sai. | Sửa DTO, converter hoặc dữ liệu; không coi đây là lỗi dịch vụ đích. |
| Thiếu cấu hình client | Base URL, header hoặc credential không được thiết lập. | Sửa cấu hình ứng dụng và xác định rõ có cần tính vào chính sách bảo vệ hay không. |

Nên thực hiện validation và tạo các giá trị request có thể kiểm tra trước khi đi vào vùng được Circuit Breaker bảo vệ. Điều này giúp Circuit Breaker chỉ quan sát lời gọi phụ thuộc thực sự. Một số lỗi chuyển đổi body chỉ xảy ra khi HTTP client bắt đầu thực thi; nếu không thể đưa bước đó ra ngoài vùng bảo vệ, hãy nhận diện kiểu ngoại lệ local cụ thể và cấu hình bỏ qua.

Không nên bỏ qua mọi `RuntimeException` hoặc mọi `RestClientException` chỉ vì một số lỗi trong nhóm đó phát sinh ở client. Những lớp ngoại lệ rộng có thể bao gồm lỗi kết nối, lỗi đọc response hoặc lỗi từ server; bỏ qua chúng sẽ khiến Circuit Breaker không còn phát hiện được sự cố cần bảo vệ.

## Nhận diện lỗi gửi request và nhận response

Các lỗi trong quá trình giao tiếp với dịch vụ phụ thuộc thường gồm:

| Lỗi | Ví dụ | Ý nghĩa đối với Circuit Breaker |
| --- | --- | --- |
| Không kết nối được | Connection refused, DNS không phân giải được, TLS handshake thất bại. | Thường ghi nhận là thất bại của lời gọi phụ thuộc. |
| Timeout khi kết nối hoặc đọc | Không thiết lập được kết nối trong thời hạn hoặc chờ response quá lâu. | Thường ghi nhận là thất bại; cần đặt timeout ở HTTP client. |
| Phản hồi server 5xx | HTTP 500, 502, 503, 504. | Thường ghi nhận là thất bại vì dịch vụ hoặc gateway báo không xử lý được request. |
| Phản hồi client 4xx | HTTP 400, 401, 403, 404. | Thường là lỗi request, quyền truy cập hoặc kết quả nghiệp vụ; chính sách thống kê cần được quyết định riêng. |
| Phản hồi giới hạn lưu lượng | HTTP 429. | Có thể xem là tín hiệu quá tải của dịch vụ phụ thuộc và ghi nhận là thất bại; cần xét `Retry-After` và chính sách retry. |
| Body phản hồi sai định dạng | JSON không khớp DTO hoặc thiếu dữ liệu bắt buộc. | Có thể phản ánh lỗi hợp đồng của dịch vụ; cần ghi nhận và điều tra thay vì mặc định coi là lỗi đầu vào của caller. |

HTTP 4xx không đồng nghĩa tất cả đều vô hại. Ví dụ, 404 có thể là kết quả nghiệp vụ bình thường nếu tài nguyên không tồn tại; 401 hoặc 403 có thể cho thấy credential hoặc cấu hình quyền bị sai; 429 có thể cho thấy dịch vụ phụ thuộc đang quá tải. Hãy phân loại theo hợp đồng của API, thay vì áp dụng một quy tắc duy nhất cho mọi mã 4xx.

## Ví dụ với RestTemplate

`RestTemplate` thường ném `ResourceAccessException` cho lỗi truy cập tài nguyên như lỗi kết nối hoặc timeout. Với error handler mặc định, phản hồi HTTP 4xx và 5xx được chuyển thành các ngoại lệ thuộc nhánh `HttpStatusCodeException`: 4xx thuộc `HttpClientErrorException`, còn 5xx thuộc `HttpServerErrorException`.

Ví dụ tạo request trước, sau đó chỉ bảo vệ lời gọi mạng:

```java
@Service
public class CatalogService {
    private final RestTemplate restTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogService(
            RestTemplate restTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restTemplate = restTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public CatalogItem find(String productId) {
        validateProductId(productId);
        URI uri = URI.create("https://catalog.internal/items/" +
            UriUtils.encodePathSegment(productId, StandardCharsets.UTF_8));

        return circuitBreakerFactory.create("catalog").run(
            () -> restTemplate.getForObject(uri, CatalogItem.class),
            error -> CatalogItem.unavailable(productId)
        );
    }

    private void validateProductId(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("productId is required");
        }
    }
}
```

`validateProductId` và việc tạo URI diễn ra trước `run`, do đó lỗi validation hoặc URI không hợp lệ không bị tính là kết quả của lời gọi phụ thuộc. Trong ứng dụng thực tế, nên dùng URI builder để mã hóa path segment đúng cách và tránh ghép chuỗi URL thủ công; đoạn mã trên tập trung minh họa ranh giới giữa chuẩn bị request và lời gọi được bảo vệ.

Fallback trong ví dụ trả về trạng thái chưa xác định của sản phẩm. Ứng dụng cần biểu diễn trạng thái đó rõ ràng để caller không nhầm với trường hợp sản phẩm không tồn tại. Nếu cần phân biệt lỗi 404 với lỗi 503, fallback nên kiểm tra loại ngoại lệ và trả về kết quả nghiệp vụ phù hợp.

## Cấu hình phân loại ngoại lệ

Với error handler mặc định của `RestTemplate`, có thể bỏ qua một số lỗi client đã được xác định là kết quả nghiệp vụ hoặc lỗi request, đồng thời giữ các lỗi kết nối và phản hồi server trong thống kê. Resilience4j cho phép cấu hình predicate bỏ qua ngoại lệ:

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.converter.HttpMessageNotWritableException;
import org.springframework.web.client.HttpClientErrorException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogFailurePolicy() {
    return factory -> factory.configureDefault(id -> {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .ignoreException(error -> {
                if (error instanceof HttpMessageNotWritableException) {
                    return true;
                }
                return error instanceof HttpClientErrorException clientError
                    && clientError.getStatusCode().is4xxClientError()
                    && clientError.getStatusCode().value() != 429;
            })
            .failureRateThreshold(50)
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .build();

        return new Resilience4JConfigBuilder(id)
            .circuitBreakerConfig(config)
            .build();
    });
}
```

Ví dụ này dùng chính sách mặc định của Resilience4j để ghi nhận ngoại lệ, trừ các ngoại lệ được predicate bỏ qua. Các phản hồi 4xx (ngoại trừ 429) được loại khỏi thống kê; `HttpMessageNotWritableException` biểu thị lỗi ghi request body phía client nên cũng bị bỏ qua. 5xx và `ResourceAccessException` vẫn được ghi nhận là thất bại. `HttpMessageNotReadableException` khi phân tích response không bị bỏ qua, vì nó có thể chỉ ra server trả body sai hợp đồng.

Chính sách này chỉ là một lựa chọn mẫu. Nếu 401 hoặc 403 là tín hiệu dịch vụ phụ thuộc mất khả năng xác thực do cấu hình credential hết hạn, nhóm vận hành có thể muốn theo dõi chúng riêng hoặc tính chúng vào một chỉ số khác. Nếu 404 là lỗi nghiệp vụ bình thường, nên chuyển nó thành kết quả domain rõ ràng hoặc bỏ qua trong predicate. Nếu 429 báo quá tải, ví dụ trên cố ý giữ nó trong thống kê thất bại.

Predicate bỏ qua chỉ ảnh hưởng đến thống kê Circuit Breaker. Ngoại lệ vẫn có thể được truyền đến fallback hoặc caller; bỏ qua không có nghĩa là nuốt lỗi.

## Khi HTTP client không ném ngoại lệ cho status lỗi

Một số HTTP client hoặc custom error handler trả response bình thường kể cả khi status là 5xx. Trong trường hợp đó, Circuit Breaker thấy supplier hoàn tất bình thường và có thể ghi nhận thành công. `recordException` không thể phân loại một status nếu không có exception.

Có hai cách xử lý:

1. Cấu hình HTTP client chuyển status cần bảo vệ thành exception có kiểu rõ ràng, rồi dùng predicate ngoại lệ để ghi nhận.
2. Nếu API trả về một kiểu response có status, dùng `recordResult` để đánh giá giá trị trả về theo hợp đồng của phiên bản Resilience4j.

Ví dụ với kiểu response do ứng dụng định nghĩa:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .recordResult(result ->
        result instanceof CatalogResponse response
            && response.statusCode() >= 500
    )
    .build();
```

Không nên đánh dấu tất cả kết quả 4xx là lỗi hạ tầng. Ứng dụng cần phân biệt lỗi validation, không tìm thấy tài nguyên, không có quyền và giới hạn lưu lượng dựa trên ý nghĩa của API.

## Timeout và tính an toàn khi retry

Circuit Breaker không tự đặt thời hạn cho một lời gọi đồng bộ đang chạy. Nếu HTTP client không có connect timeout và response/read timeout, thread gọi có thể bị giữ rất lâu ngay cả khi Circuit Breaker đang `CLOSED`. Cần cấu hình timeout ở HTTP client hoặc dùng `TimeLimiter` phù hợp với cách tích hợp.

Nên phân biệt:

- **Connection timeout:** thời gian tối đa để thiết lập kết nối.
- **Response/read timeout:** thời gian tối đa chờ dữ liệu phản hồi hoặc một lần đọc theo cấu hình client.
- **Overall deadline:** thời gian tổng mà nghiệp vụ cho phép cho toàn bộ lời gọi, gồm các bước kết nối, gửi và nhận dữ liệu.

Khi xảy ra read timeout, client không biết chắc server đã xử lý request đến đâu. Với thao tác ghi, hãy dùng idempotency key hoặc cơ chế chống trùng lặp ở dịch vụ đích trước khi retry. Không tự động retry mọi lỗi timeout, 5xx hoặc 429; retry cần giới hạn số lần, backoff, jitter và phải nằm trong deadline tổng.

## Kiểm tra hành vi bằng các tình huống

Có thể dùng một HTTP server giả lập hoặc mock `RestTemplate` để tạo các tình huống và quan sát metrics:

| Tình huống | Lỗi dự kiến | Kết quả thống kê theo chính sách mẫu |
| --- | --- | --- |
| `productId` rỗng | `IllegalArgumentException` trước `run` | Không đi vào Circuit Breaker. |
| Request body không serialize được | `HttpMessageNotWritableException` | Bị bỏ qua. |
| Không kết nối được server | `ResourceAccessException` | Thất bại. |
| Server trả HTTP 503 | `HttpServerErrorException` | Thất bại. |
| Server trả HTTP 404 | `HttpClientErrorException` | Bị bỏ qua theo chính sách mẫu; ứng dụng vẫn xử lý exception/fallback. |
| Server trả HTTP 429 | `HttpClientErrorException` | Thất bại theo chính sách mẫu. |
| Server trả JSON sai cấu trúc | Lỗi chuyển đổi response | Được ghi nhận nếu exception không bị bỏ qua. |

Kiểm tra cả trạng thái Circuit Breaker, số lời gọi thành công/thất bại và số ngoại lệ bị bỏ qua. Đừng chỉ dựa vào HTTP status mà client cuối cùng nhận được vì fallback có thể biến một ngoại lệ thành response thay thế.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Mọi exception trong lời gọi đồng bộ đều là lỗi dịch vụ phụ thuộc. | Một số lỗi phát sinh khi kiểm tra dữ liệu, tạo URI hoặc serialize request ở phía caller. |
| HTTP 500 là lỗi tạo request. | Đây là response từ server báo lỗi xử lý. |
| HTTP 404 luôn là lỗi hạ tầng. | Có thể là kết quả nghiệp vụ bình thường, tùy hợp đồng API. |
| Bỏ qua exception nghĩa là exception không truyền ra ngoài. | Predicate chỉ điều khiển thống kê; fallback và caller vẫn có thể nhận exception. |
| Read timeout chứng minh server chưa thực hiện thao tác. | Server có thể đã xử lý request nhưng response không đến được client. |
| Circuit Breaker thay thế connect/read timeout. | Timeout cần được cấu hình riêng ở HTTP client hoặc TimeLimiter. |

Khi đặt đúng ranh giới giữa bước chuẩn bị request và lời gọi phụ thuộc, rồi phân loại response và exception theo hợp đồng API, failure rate phản ánh chính xác hơn sức khỏe của dịch vụ đích. Điều đó giúp Circuit Breaker trong Spring Cloud mở mạch khi dịch vụ phụ thuộc thực sự gặp vấn đề, thay vì phản ứng với lỗi dữ liệu cục bộ của ứng dụng gọi.
