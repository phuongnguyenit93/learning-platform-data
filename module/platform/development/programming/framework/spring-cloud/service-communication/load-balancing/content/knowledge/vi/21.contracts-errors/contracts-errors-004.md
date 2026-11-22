# Ánh xạ ngoại lệ của từng HTTP client về mô hình ứng dụng

Trong kiến trúc microservices, cùng một tình huống **`catalog-service` trả HTTP 404** có thể xuất hiện dưới dạng `RestClientResponseException` ở **RestClient**, `WebClientResponseException` ở **WebClient** hoặc `FeignException.NotFound` ở **OpenFeign**. Nếu service nghiệp vụ trực tiếp phụ thuộc vào các loại ngoại lệ này, việc thay client hoặc thêm retry sẽ làm lan rộng mã xử lý lỗi. Nghiêm trọng hơn, **không chọn được instance**, **mất kết nối** và **đã nhận HTTP 503** rất dễ bị đánh đồng, khiến ứng dụng retry sai hoặc trả phản hồi sai cho người dùng.

Bài thuộc chương **Hợp đồng và lỗi** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là xây dựng một **mô hình lỗi ứng dụng nhất quán**, rồi ánh xạ tín hiệu từ **RestClient**, **WebClient** và **OpenFeign** khi gọi theo service ID qua Spring Cloud LoadBalancer. Chúng ta cũng phân biệt ảnh hưởng của **discovery, health check, chính sách chọn `ServiceInstance`, timeout, retry và khả năng quan sát** để không che mất nguyên nhân gốc.

> Nguyên tắc: ngoại lệ của HTTP library là **chi tiết tầng giao tiếp**; tầng ứng dụng nên làm việc với **ý nghĩa lỗi** và **chính sách khôi phục**. Tuy nhiên, không “làm phẳng” mọi lỗi thành một mã `SERVICE_UNAVAILABLE` vì sẽ mất khác biệt quan trọng giữa hợp đồng API và lỗi hạ tầng.

## 1. Một tình huống, ba kiểu exception

Giả sử `order-service` gọi endpoint:

~~~http
GET /api/items/42 HTTP/1.1
Host: catalog-service
Accept: application/json
~~~

Server có thể trả:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://example.invalid/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "The requested item does not exist",
  "code": "ITEM_NOT_FOUND"
}
~~~

*Đây là mẫu JSON minh họa theo định dạng Problem Details; `code` là phần mở rộng do ứng dụng quy định, không phải một trường bắt buộc của chuẩn.*

| Client | Tín hiệu điển hình khi dùng cấu hình mặc định | Chú ý |
|---|---|---|
| RestClient + `retrieve()` | `RestClientResponseException` hoặc subclass tương ứng status | Có HTTP response |
| WebClient + `retrieve()` | `WebClientResponseException` trong tín hiệu `onError` | Reactive publisher |
| OpenFeign với error handling mặc định | `FeignException.NotFound` hoặc `FeignException` | Có thể thay đổi qua `ErrorDecoder` |
| Ứng dụng | `CatalogItemNotFound` hoặc `RESOURCE_NOT_FOUND` | Phụ thuộc ý nghĩa 404 theo hợp đồng |

Điểm cốt lõi: **404 chỉ là status vận chuyển**. Nếu endpoint là `GET /api/items/{id}`, nó có thể mang nghĩa *item không tồn tại*. Nếu endpoint `/api/items/42` không tồn tại vì cấu hình sai path, cùng status đó lại là *lỗi tích hợp*, không nên nói với người dùng rằng item chắc chắn không có.

Vì vậy, ánh xạ cần có **ngữ cảnh operation**: đang gọi endpoint nào, kỳ vọng response gì, có thể xảy ra side effect hay không, và code lỗi downstream là gì.

## 2. Các tầng có thể tạo lỗi khi gọi theo service ID

Một lời gọi qua Spring Cloud LoadBalancer trải qua nhiều bước:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi CatalogPort.getItem(id)"] --> B["RestClient / WebClient / Feign"]
    B --> C{"Discovery/supplier có instance?"}
    C -->|Không| D["Lỗi chọn đích / không có ServiceInstance"]
    C -->|Có| E["LoadBalancer chọn instance"]
    E --> F{"Kết nối và gửi request thành công?"}
    F -->|Không| G["Connect, TLS, network, pool, timeout"]
    F -->|Có| H{"Nhận được HTTP response?"}
    H -->|Không| I["Response timeout / reset / unknown outcome"]
    H -->|Có| J{"HTTP status và body"}
    J -->|4xx/5xx| K["Lỗi hợp đồng hoặc backend/gateway"]
    J -->|2xx| L{"Decode thành DTO?"}
    L -->|Không| M["Lỗi schema/media type/codec"]
    L -->|Có| N["Kết quả ứng dụng"]
~~~

**Các lớp lỗi này không cùng bản chất**:

1. **Không có ứng viên:** danh sách `ServiceInstance` rỗng do service ID sai, discovery chưa đồng bộ, health/filter loại hết instance hoặc supplier gặp vấn đề.
2. **Không thiết lập/gửi được HTTP:** lỗi connection pool, DNS/transport, TLS, connect timeout hoặc reset trước response.
3. **Không nhận response đúng hạn:** server có thể vẫn xử lý hoặc đã hoàn tất request.
4. **Đã nhận HTTP status lỗi:** HTTP response tồn tại, nhưng cần đọc đúng ý nghĩa contract.
5. **Response 2xx không giải mã được:** có thể là thay đổi schema không tương thích hoặc lỗi serialization, không mặc nhiên retry.
6. **Ứng dụng tự từ chối dữ liệu:** ví dụ giá trị không hợp lệ dù JSON decode thành công; đây là business validation, khác lỗi HTTP client.

**LoadBalancer không phải HTTP error decoder.** Nó chọn một instance dựa vào supplier và chính sách; response/exceptions xuất hiện ở client transport hoặc adapter. Trong một số tích hợp, tình huống không có instance có thể biểu hiện thành exception hay response lỗi được tạo ở tầng client/LB; không thể suy nguồn chỉ từ status nếu không quan sát đường đi.

## 3. Phân biệt bốn nhóm thông tin trước khi mapping

Mỗi failure nên mang ít nhất bốn đặc tính:

| Trường | Câu hỏi | Ví dụ |
|---|---|---|
| **Kind** | Chuyện gì xảy ra? | `RESOURCE_NOT_FOUND`, `TRANSPORT_FAILURE`, `RESPONSE_TIMEOUT` |
| **Origin** | Tín hiệu xuất phát ở đâu? | Server response, load balancer, client transport, codec |
| **HTTP status** | Có status thật từ downstream không? | 404, 429, 503 hoặc không có |
| **Outcome certainty** | Có thể kết luận tác dụng phụ đã diễn ra chưa? | `KNOWN_SUCCESS`, `KNOWN_REJECTED`, `UNKNOWN` |

Tính **retryable** nên là một **đánh giá theo operation và ngân sách thời gian**, không chỉ thuộc tính cố định của status. Ví dụ GET bị lỗi kết nối có thể retry có giới hạn; POST sau response timeout chỉ retry an toàn nếu server thực sự hỗ trợ idempotency.

Cũng cần phân biệt:

- **Tín hiệu quan sát:** `WebClientRequestException` cho biết lỗi request/transport, không tự cho biết DB server đã commit chưa.
- **Nguyên nhân gốc:** lỗi TLS handshake, pool acquire timeout, HTTP status 503 hoặc dữ liệu sai schema.
- **Ý nghĩa nghiệp vụ:** có thể trả “không tìm thấy”, “thử lại sau”, “đang xác minh kết quả” hay “tích hợp gặp lỗi”.

Một bộ phân loại tốt **không nuốt cause**: nó giữ exception gốc để chẩn đoán nhưng không phơi ra raw stack trace cho người dùng.

## 4. Thiết kế một mô hình lỗi thống nhất cho tầng ứng dụng

Ví dụ Java 17+, định nghĩa loại lỗi mà các HTTP adapters cùng sử dụng.

~~~java
package demo.catalog.port;

public enum FailureKind {
    RESOURCE_NOT_FOUND,
    VALIDATION_REJECTED,
    CONFLICT,
    AUTHENTICATION_REJECTED,
    AUTHORIZATION_REJECTED,
    RATE_LIMITED,
    DOWNSTREAM_REJECTED,
    DOWNSTREAM_UNAVAILABLE,
    NO_SERVICE_INSTANCE,
    CONNECT_FAILURE,
    RESPONSE_TIMEOUT,
    DECODE_FAILURE,
    UNEXPECTED_FAILURE
}
~~~

~~~java
package demo.catalog.port;

public enum OutcomeCertainty {
    KNOWN_REJECTED,
    UNKNOWN
}
~~~

`UNKNOWN` ở đây dùng cho **failure** mà caller chưa xác minh được kết quả của một thao tác có side effect; với GET thuần chỉ đọc, thường không có side effect nghiệp vụ cần đối soát. `KNOWN_REJECTED` chỉ nên gắn khi hợp đồng API cho phép kết luận operation bị từ chối/chưa tạo thay đổi, chứ không áp dụng chung cho mọi response 5xx.

Định nghĩa thêm **nguồn tạo tín hiệu**, độc lập với ý nghĩa lỗi:

~~~java
package demo.catalog.port;

public enum FailureOrigin {
    HTTP_RESPONSE,
    LOAD_BALANCER,
    TRANSPORT,
    CODEC
}
~~~

Một record mang metadata an toàn:

~~~java
package demo.catalog.port;

public record DownstreamFailure(
    String serviceId,
    String operation,
    FailureKind kind,
    FailureOrigin origin,
    Integer downstreamHttpStatus,
    OutcomeCertainty outcome,
    String diagnosticCode
) {
}
~~~

Và exception ứng dụng:

~~~java
package demo.catalog.port;

public final class DownstreamCallException extends RuntimeException {

    private final DownstreamFailure failure;

    public DownstreamCallException(
        DownstreamFailure failure,
        Throwable cause
    ) {
        super(failure.kind().name(), cause);
        this.failure = failure;
    }

    public DownstreamFailure failure() {
        return failure;
    }
}
~~~

**Vì sao không thêm trực tiếp `retryable=true` vào tất cả lỗi?** Vì cùng một `RESPONSE_TIMEOUT` có thể retry được đối với GET nhưng rất nguy hiểm với POST tạo đơn chưa có idempotency. Tốt hơn nên có **RetryPolicy** xét `FailureKind` + operation semantics + số lần thử + deadline còn lại.

`diagnosticCode` nên là mã ổn định và không nhạy cảm, ví dụ `CATALOG_HTTP_503`. Không đưa response body chứa PII, header Authorization hoặc URL có token vào `DownstreamFailure`.

### Hợp đồng business port

Tầng nghiệp vụ có thể định nghĩa port riêng:

~~~java
package demo.catalog.port;

public interface CatalogPort {
    ItemDto getItem(String id);
}
~~~

~~~java
package demo.catalog.port;

public record ItemDto(String id, String name, int stock) {
}
~~~

RestClient/WebClient/OpenFeign là **adapter** của port. Business service biết `CatalogPort` và `DownstreamCallException`, không cần import `FeignException` hay `WebClientResponseException`.

## 5. Quy tắc ánh xạ HTTP status dựa trên contract

Một bảng ánh xạ tham khảo cho `GET /api/items/{id}`:

| Tín hiệu từ downstream | Ý nghĩa thường gặp | Mô hình ứng dụng gợi ý | Retry? |
|---|---|---|---|
| 400 | Input/query không hợp lệ | `VALIDATION_REJECTED` nếu có contract | Không máy móc |
| 401 | Không xác thực được | `AUTHENTICATION_REJECTED` | Thường sửa credentials trước |
| 403 | Không đủ quyền | `AUTHORIZATION_REJECTED` | Không retry cùng quyền |
| 404 + `ITEM_NOT_FOUND` | Item không tồn tại | `RESOURCE_NOT_FOUND` | Không |
| 404 nhưng URL/mapping sai | Lỗi tích hợp | `DOWNSTREAM_REJECTED`/`UNEXPECTED_FAILURE` | Sửa contract |
| 409 | Xung đột trạng thái/phiên bản | `CONFLICT` | Tùy cách resolve |
| 422 | Semantics input không hợp lệ | `VALIDATION_REJECTED` | Thường không |
| 429 | Rate limited | `RATE_LIMITED` | Có điều kiện, xét `Retry-After` |
| 500 | Server lỗi | `DOWNSTREAM_UNAVAILABLE` hoặc lỗi upstream khác theo contract | Có điều kiện |
| 502/503/504 | Gateway/availability/timeout | `DOWNSTREAM_UNAVAILABLE` | Có điều kiện |
| 2xx, JSON không decode được | Contract mismatch | `DECODE_FAILURE` | Thường điều tra thay vì retry |
| Không có HTTP response | Connection/timeout/discovery | `CONNECT_FAILURE`, `RESPONSE_TIMEOUT`, `NO_SERVICE_INSTANCE` | Theo operation |

Đây là **ma trận gợi ý**, không phải luật mặc định của Spring. Đặc biệt, một HTTP 500 có thể xảy ra **sau khi server đã ghi dữ liệu**; nếu là thao tác ghi, không thể suy kết quả chắc chắn là FAILED chỉ dựa trên status.

Đối với endpoint `GET`, 404 có thể là **kết quả nghiệp vụ hợp lệ** (trả `Optional.empty()`) thay vì exception. Nếu chọn thiết kế đó, lớp application port có thể trả `Optional<ItemDto>`, nhưng cần xác minh rằng 404 chỉ mang nghĩa resource thiếu, không phải API route sai.

## 6. Tạo bộ phân loại HTTP status dùng chung

Để các adapter diễn giải nhất quán, có thể tập trung quy tắc status trong một helper:

~~~java
package demo.catalog.port;

public final class CatalogHttpFailureMapper {

    private CatalogHttpFailureMapper() {}

    public static FailureKind classify(
        int status,
        String downstreamCode
    ) {
        return switch (status) {
            case 400, 422 -> FailureKind.VALIDATION_REJECTED;
            case 401 -> FailureKind.AUTHENTICATION_REJECTED;
            case 403 -> FailureKind.AUTHORIZATION_REJECTED;
            case 404 ->
                "ITEM_NOT_FOUND".equals(downstreamCode)
                    ? FailureKind.RESOURCE_NOT_FOUND
                    : FailureKind.DOWNSTREAM_REJECTED;
            case 409 -> FailureKind.CONFLICT;
            case 429 -> FailureKind.RATE_LIMITED;
            case 500, 502, 503, 504 ->
                FailureKind.DOWNSTREAM_UNAVAILABLE;
            default -> FailureKind.DOWNSTREAM_REJECTED;
        };
    }
}
~~~

Trong thực tế, `downstreamCode` phải được trích xuất từ **error response hợp lệ** theo schema đã thống nhất. Không tự coi mọi response 404 đều có mã `ITEM_NOT_FOUND`, cũng không cố deserialize lỗi từ payload không giới hạn kích thước.

Ví dụ dưới đây tập trung ánh xạ theo status; khi chưa parse được error code thì truyền `null`. Điều đó khiến status 404 được phân loại thành `DOWNSTREAM_REJECTED` cho đến khi có bằng chứng chắc chắn là item không tồn tại.

### Tạo exception theo cùng định dạng

~~~java
package demo.catalog.port;

public final class CatalogFailureFactory {

    private CatalogFailureFactory() {}

    public static DownstreamCallException fromHttp(
        String operation,
        int status,
        String contractCode,
        Throwable cause
    ) {
        FailureKind kind =
            CatalogHttpFailureMapper.classify(status, contractCode);

        OutcomeCertainty certainty =
            switch (kind) {
                case RESOURCE_NOT_FOUND,
                     VALIDATION_REJECTED,
                     AUTHENTICATION_REJECTED,
                     AUTHORIZATION_REJECTED,
                     CONFLICT -> OutcomeCertainty.KNOWN_REJECTED;
                default -> OutcomeCertainty.UNKNOWN;
            };

        return new DownstreamCallException(
            new DownstreamFailure(
                "catalog-service",
                operation,
                kind,
                FailureOrigin.HTTP_RESPONSE,
                status,
                certainty,
                "CATALOG_HTTP_" + status
            ),
            cause
        );
    }

    public static DownstreamCallException fromTransport(
        String operation,
        FailureKind kind,
        Throwable cause
    ) {
        return new DownstreamCallException(
            new DownstreamFailure(
                "catalog-service",
                operation,
                kind,
                kind == FailureKind.NO_SERVICE_INSTANCE
                    ? FailureOrigin.LOAD_BALANCER
                    : kind == FailureKind.DECODE_FAILURE
                        ? FailureOrigin.CODEC
                        : FailureOrigin.TRANSPORT,
                null,
                OutcomeCertainty.UNKNOWN,
                "CATALOG_" + kind.name()
            ),
            cause
        );
    }
}
~~~

**Điều kiện của ví dụ:** `KNOWN_REJECTED` chỉ áp dụng khi hợp đồng downstream thực sự bảo đảm không có side effect cho nhóm lỗi đó. Với API POST có semantics khác, cần mapper theo operation thay vì tái sử dụng máy móc. `UNKNOWN` cũng không có nghĩa server chắc chắn đã thành công; nó nghĩa là **không thể kết luận** từ bằng chứng đang có.

Bộ phân loại này minh họa việc **tách error taxonomy khỏi từng HTTP library**, không thay thế một thiết kế contract chi tiết cho mọi downstream.

## 7. RestClient: map HTTP response và lỗi I/O

Với Spring Framework 6.1+ và Spring Cloud tương thích, tạo RestClient có LoadBalancer:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Trong adapter, `retrieve()` thường chuyển HTTP 4xx/5xx thành `RestClientResponseException` hoặc lớp con. Lỗi transport có thể xuất hiện dưới dạng `ResourceAccessException`; lỗi decode có thể thuộc `RestClientException` hoặc cause của một converter.

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
class RestCatalogAdapter implements CatalogPort {

    private final RestClient client;

    RestCatalogAdapter(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    @Override
    public ItemDto getItem(String id) {
        try {
            return client.get()
                .uri("/api/items/{id}", id)
                .retrieve()
                .body(ItemDto.class);
        } catch (RestClientResponseException ex) {
            throw CatalogFailureFactory.fromHttp(
                "getItem", ex.getStatusCode().value(), null, ex);
        } catch (ResourceAccessException ex) {
            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.CONNECT_FAILURE, ex);
        } catch (RestClientException ex) {
            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.DECODE_FAILURE, ex);
        }
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**

- `RestClientResponseException` dành cho lỗi có **HTTP status từ response mà client nhận được**, nhưng nếu một tầng trung gian tạo response thì status đó không nhất thiết do instance nghiệp vụ gốc phát ra.
- `ResourceAccessException` có thể bọc nhiều lỗi I/O, kể cả read timeout hoặc connection reset. Gắn tất cả vào `CONNECT_FAILURE` như ví dụ tối giản là **phân loại thô**; production cần kiểm tra cause và giai đoạn request để phân biệt `RESPONSE_TIMEOUT` với lỗi kết nối trước khi gửi.
- Không nên coi **mọi** `RestClientException` còn lại là lỗi decode: có thể là lỗi request/codec khác. Cần dùng exception chain và integration test để điều chỉnh taxonomy.
- Tình huống **không tìm được `ServiceInstance`** có thể là exception khác hoặc được tích hợp trả response khác tùy phiên bản; không đảm bảo ba catch trên bao phủ hết.
- Nếu `body(ItemDto.class)` có thể trả `null` (ví dụ 204/response rỗng), cần kiểm tra contract thay vì trả null vào business code mà không xử lý.

### Khi muốn phân loại timeout cụ thể hơn

Một hàm phân loại cause có thể đi theo chuỗi ngoại lệ và tìm dấu hiệu như `SocketTimeoutException`, `ConnectException` hoặc timeout của HTTP transport. Tuy nhiên, **chỉ tìm tên exception không đủ để biết chắc request đã được server xử lý hay chưa**. Với các POST, read timeout nên đánh dấu outcome `UNKNOWN` và sử dụng idempotency/query status trước khi retry.

## 8. RestClient: dùng onStatus để chuyển lỗi tại biên HTTP

Ngoài try/catch bên ngoài, `retrieve().onStatus(...)` có thể chuyển HTTP status thành exception:

~~~java
ItemDto item = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw CatalogFailureFactory.fromHttp(
                "getItem", 404, "ITEM_NOT_FOUND", null);
        }
    )
    .onStatus(
        status -> status.is5xxServerError(),
        (request, response) -> {
            throw CatalogFailureFactory.fromHttp(
                "getItem", response.getStatusCode().value(), null, null);
        }
    )
    .body(ItemDto.class);
~~~

Trong đoạn này, `"ITEM_NOT_FOUND"` được hardcode như **giả định hợp đồng** cho endpoint `GET /api/items/{id}`; với API thực cần xác minh error body/code thay vì suy từ status 404. Nếu cần giữ cause đầy đủ, hãy dùng một exception riêng biểu thị HTTP response và thêm metadata có thể đọc được. Với `onStatus`, mặc định của `retrieve()` sẽ áp dụng cho các status không bị handler tùy biến xử lý.

Không dùng `onStatus` để bắt lỗi không chọn được instance hay kết nối chưa thành lập: các lỗi này có thể xuất hiện **trước khi có response**.

### exchange() khác retrieve()

Với `RestClient.exchange(...)`, callback có quyền truy cập request và response và **không sử dụng status handlers của retrieve**. Nếu ứng dụng dùng exchange, nó phải tự kiểm tra HTTP status và convert body:

~~~java
int status = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .exchange((request, response) ->
        response.getStatusCode().value()
    );
~~~

Đoạn trên chỉ trả status để minh họa; việc xử lý body/error schema phải được bổ sung theo contract. Không viết một mapper chỉ xử lý `RestClientResponseException` rồi giả định nó cũng xử lý mọi HTTP 404 khi dùng `exchange()`.

## 9. WebClient: ánh xạ qua reactive error signal

`WebClient` hoạt động theo mô hình reactive. `retrieve().bodyToMono(ItemDto.class)` trả về một `Mono<ItemDto>`; lỗi HTTP/transport/codec thường xuất hiện **khi subscription chạy**, không nhất thiết ngay tại lúc gọi method Java.

Cấu hình WebClient có LoadBalancer:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder")
        WebClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Một adapter reactive nên có **port reactive riêng** (không giả vờ nó là port blocking):

~~~java
package demo.catalog.port;

import reactor.core.publisher.Mono;

public interface ReactiveCatalogPort {
    Mono<ItemDto> getItem(String id);
}
~~~

Và ánh xạ exception:

~~~java
import org.springframework.core.codec.DecodingException;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

@Component
class ReactiveCatalogAdapter implements ReactiveCatalogPort {

    private final WebClient client;

    ReactiveCatalogAdapter(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    @Override
    public Mono<ItemDto> getItem(String id) {
        return client.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class)
            .onErrorMap(
                WebClientResponseException.class,
                ex -> CatalogFailureFactory.fromHttp(
                    "getItem", ex.getStatusCode().value(), null, ex)
            )
            .onErrorMap(
                WebClientRequestException.class,
                ex -> CatalogFailureFactory.fromTransport(
                    "getItem", FailureKind.CONNECT_FAILURE, ex)
            )
            .onErrorMap(
                DecodingException.class,
                ex -> CatalogFailureFactory.fromTransport(
                    "getItem", FailureKind.DECODE_FAILURE, ex)
            );
    }
}
~~~

**Lưu ý:**

- `WebClientResponseException` thường chỉ ra response HTTP lỗi. Với `retrieve()`, xử lý mặc định cho status 4xx/5xx tạo error signal.
- `WebClientRequestException` biểu thị lỗi request/transport và **không tự xác nhận** server chưa có side effect.
- `DecodingException` chỉ là một nhóm lỗi codec thường gặp; những lỗi deserialize khác có thể nằm trong cause riêng.
- `timeout(Duration)` trong Reactor có thể phát `TimeoutException` không đi qua ba nhánh trên; nếu cần thống nhất taxonomy, map riêng và giữ nguyên ngữ cảnh deadline/operation.
- Không dùng `onErrorMap(Throwable.class, ...)` để biến mọi lỗi thành lỗi downstream: nó có thể nuốt bug trong mã ứng dụng, hủy luồng sai semantics hoặc che lỗi validation nội bộ.

### Khi dùng exchangeToMono

`exchangeToMono(...)` cho phép tự phân nhánh theo `ClientResponse.statusCode()`. Nếu chọn cách này, ứng dụng cần đọc/giải phóng response body theo API đúng và tự chuyển status lỗi; không giả định status 404/503 luôn phát `WebClientResponseException` như đường `retrieve()`.

## 10. WebClient: phân loại cancellation, timeout và retry

Một số tín hiệu reactive cần xử lý riêng:

| Tín hiệu | Ý nghĩa | Phân loại đề xuất |
|---|---|---|
| `onError(WebClientResponseException)` | Đã nhận HTTP status lỗi | HTTP contract mapping |
| `onError(WebClientRequestException)` | Lỗi I/O/transport khi request | `CONNECT_FAILURE` hoặc loại transport cụ thể |
| `onError(DecodingException)` | Không giải mã được response | `DECODE_FAILURE` |
| `onError(TimeoutException)` | Deadline/operator timeout | `RESPONSE_TIMEOUT` hoặc `DEADLINE_EXCEEDED` nếu mô hình có |
| `cancel` | Downstream không tiếp tục subscription | **Không mặc nhiên là error** |
| `onComplete` không có value | Mono rỗng hợp lệ hoặc thiếu dữ liệu theo contract | Kiểm tra business contract |

Ví dụ map timeout operator vào failure:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

Mono<ItemDto> result = reactiveCatalogPort.getItem("42")
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(
        TimeoutException.class,
        ex -> CatalogFailureFactory.fromTransport(
            "getItem", FailureKind.RESPONSE_TIMEOUT, ex)
    );
~~~

Trong trường hợp này, timeout xảy ra ở **publisher sau khi adapter đã được gọi**; với request HTTP có side effect, không suy rằng cancellation làm server rollback. Retry cũng không được bật chỉ vì `onErrorMap` đã tạo exception chuẩn.

Nếu muốn retry có giới hạn, thiết kế policy xét `DownstreamFailure.kind()`, method/operation, attempt number và deadline. Đừng retry không giới hạn một `Flux` streaming hoặc POST không idempotent. Một lần resubscribe có thể tạo HTTP request mới và khiến LoadBalancer chọn instance khác.

## 11. OpenFeign: FeignException, RetryableException và ErrorDecoder

OpenFeign thường xây proxy từ `@FeignClient`:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

Với cấu hình `@EnableFeignClients` và integration Spring Cloud LoadBalancer phù hợp, Feign có thể gọi `catalog-service` theo service ID. Client stack, retry policy và error handling tùy dependency/release train.

Thông thường:

- HTTP response lỗi được thể hiện bằng `FeignException` hoặc lớp con như `FeignException.NotFound`.
- Một số lỗi retryable có thể xuất hiện thành `RetryableException`.
- `ErrorDecoder` có thể biến HTTP status thành exception khác.
- `Retryer` quyết định Feign có thực hiện lại request hay không trước khi exception cuối tới business code.

**Không đánh đồng `RetryableException` với “không có HTTP response”.** Một `ErrorDecoder` có thể tạo một `RetryableException` cho HTTP status cụ thể, nên vẫn phải xét status và cause.

### Ánh xạ tại adapter Feign

~~~java
import feign.FeignException;
import feign.RetryableException;
import org.springframework.stereotype.Component;

@Component
class FeignCatalogAdapter implements CatalogPort {

    private final CatalogFeignClient client;

    FeignCatalogAdapter(CatalogFeignClient client) {
        this.client = client;
    }

    @Override
    public ItemDto getItem(String id) {
        try {
            return client.getItem(id);
        } catch (RetryableException ex) {
            if (ex.status() > 0) {
                throw CatalogFailureFactory.fromHttp(
                    "getItem", ex.status(), null, ex);
            }

            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.CONNECT_FAILURE, ex);
        } catch (FeignException ex) {
            if (ex.status() > 0) {
                throw CatalogFailureFactory.fromHttp(
                    "getItem", ex.status(), null, ex);
            }

            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.UNEXPECTED_FAILURE, ex);
        }
    }
}
~~~

**Đây là mapper tối giản, không phải mọi ngoại lệ Feign có thể phát sinh.** `ErrorDecoder` do dự án cấu hình có thể trả về exception tùy biến không thuộc `FeignException`. Đồng thời `RetryableException.status()` phải được kiểm tra theo version Feign; nếu status không phải HTTP status thật, cần phân loại theo cause, không suy từ subclass.

Spring Cloud OpenFeign có thể cấu hình `Retryer.NEVER_RETRY` làm mặc định trong các phiên bản nhất định, khác mặc định của Feign core. Do đó không nên suy rằng thấy `RetryableException` nghĩa là đã có nhiều attempts. Kiểm tra cấu hình `Retryer` và số request thực tế.

## 12. OpenFeign: ErrorDecoder và quan hệ với mapper ứng dụng

Nếu muốn chuyển một status cụ thể thành exception riêng ngay khi Feign nhận response, có thể dùng `ErrorDecoder`:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

final class CatalogFeignErrorDecoder implements ErrorDecoder {

    private final ErrorDecoder fallback = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return CatalogFailureFactory.fromHttp(
                methodKey,
                status,
                "ITEM_NOT_FOUND",
                null
            );
        }

        return fallback.decode(methodKey, response);
    }
}
~~~

Đây chỉ là mẫu tối giản **giả định** rằng 404 của method tương ứng mang nghĩa `ITEM_NOT_FOUND`. Nếu decoder được áp cho nhiều method, cần xét `methodKey` và contract từng endpoint trước khi gắn mã lỗi. Decoder cũng phải tránh đọc raw body lớn/nhạy cảm không giới hạn.

Một cấu hình Feign riêng theo client:

~~~java
import feign.codec.ErrorDecoder;
import org.springframework.context.annotation.Bean;

class CatalogFeignConfiguration {

    @Bean
    ErrorDecoder catalogErrorDecoder() {
        return new CatalogFeignErrorDecoder();
    }
}
~~~

Và đăng ký:

~~~java
@FeignClient(
    name = "catalog-service",
    configuration = CatalogFeignConfiguration.class
)
interface CatalogFeignClient {
    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

Hai snippet `CatalogFeignClient` ở phần 11 và phần này là **các phương án thay thế**; không khai báo cả hai cùng tên trong một package. Cấu hình Feign riêng nên được đặt ngoài component scan chung nếu không muốn `ErrorDecoder` vô tình tác động tới client khác.

Lựa chọn giữa **ErrorDecoder** và **adapter mapper**:

- ErrorDecoder hợp lý khi cần **xử lý response HTTP theo Feign contract**.
- Adapter mapper hợp lý khi cần chuẩn hóa **cả lỗi HTTP, transport, decode và lỗi từ LoadBalancer** thành model ứng dụng.
- Có thể dùng cả hai nhưng phải tránh **map hai lần** hoặc che mất cause. Nếu ErrorDecoder đã trả `DownstreamCallException`, adapter có thể để nó đi qua thay vì bắt và bọc lại thành lỗi khác.

## 13. HTTP Interface proxy cũng phải theo adapter nền

Với Spring Framework HTTP Service Interface dùng `@HttpExchange` và `HttpServiceProxyFactory`:

- Proxy qua `RestClientAdapter` nhận semantics lỗi của RestClient.
- Proxy qua `WebClientAdapter` nhận semantics lỗi của WebClient.
- Chỉ có interface Java không tạo một loại “HTTP Interface exception” chung cho tất cả adapters.

Do đó khi viết `CatalogPort`, hãy đặt mapper **theo HTTP adapter thực thi**, không dựa vào tên annotation của interface. Đây cũng là lợi ích của mô hình port/adapters: thay Feign sang HTTP Interface không bắt buộc sửa toàn bộ business service chỉ để đổi `FeignException.NotFound` thành `RestClientResponseException`.

Nếu chuyển HTTP Interface từ RestClientAdapter sang WebClientAdapter, phải tính tới thay đổi **blocking → reactive**, kiểu return `Mono`/`Flux` và cách xử lý lỗi bằng tín hiệu. Không thể thay HTTP stack mà giữ nguyên assumption về thread và timeout.

## 14. Có phải mọi HTTP 404 đều chuyển thành lỗi nghiệp vụ?

Không. Xét ba API khác nhau:

| API | HTTP 404 có thể có nghĩa | Ánh xạ phù hợp |
|---|---|---|
| `GET /api/items/{id}` | Item không tồn tại, theo contract | `RESOURCE_NOT_FOUND` hoặc `Optional.empty()` |
| `POST /api/orders` | Route sai hoặc endpoint chưa triển khai | `DOWNSTREAM_REJECTED` / tích hợp lỗi |
| `GET /api/orders/by-key/{key}` | Chưa thấy operation trong store được hỏi | Trạng thái chưa rõ, **không tự suy operation chưa tới** |

Ngay cả với `GET /api/items/{id}`, backend có thể dùng 404 để che sự tồn tại của resource do chính sách bảo mật. Nếu caller tự biến nó thành `ItemMissing` cho người dùng mà không xét contract quyền truy cập, có thể tạo phản hồi sai.

### Ưu tiên mã lỗi ổn định thay vì so sánh chuỗi detail

Một error schema nên cung cấp `code` ổn định như `ITEM_NOT_FOUND`, `RATE_LIMIT_EXCEEDED`, `INSUFFICIENT_STOCK` và `REQUEST_CONFLICT`. Không dựa vào `detail` bằng ngôn ngữ tự nhiên để viết logic:

~~~json
{
  "type": "https://example.invalid/problems/insufficient-stock",
  "title": "Insufficient stock",
  "status": 409,
  "code": "INSUFFICIENT_STOCK",
  "traceId": "trace-example"
}
~~~

`traceId` và `code` là các trường extension theo contract của ứng dụng; các dịch vụ phải thống nhất schema và tránh lộ dữ liệu nội bộ. Phía caller cũng phải kiểm tra status, Content-Type và giới hạn độ lớn response trước khi deserialize error body.

## 15. Phân biệt lỗi không có instance và HTTP 503

Một lỗi thường xuyên bị phân loại sai:

~~~mermaid
flowchart TD
    A["Caller yêu cầu catalog-service"] --> B{"Supplier có ServiceInstance?"}
    B -->|Không| C["Không có đích: NO_SERVICE_INSTANCE"]
    B -->|Có| D["Gửi request đến instance đã chọn"]
    D --> E{"Nhận được response?"}
    E -->|Không| F["CONNECT_FAILURE / RESPONSE_TIMEOUT"]
    E -->|Có, HTTP 503| G["DOWNSTREAM_UNAVAILABLE"]
~~~

Nếu `ServiceInstanceListSupplier` trả danh sách rỗng, có thể không có request HTTP tới một backend nghiệp vụ. Tùy tích hợp, client có thể ném exception hoặc tạo/surfacing một HTTP response lỗi giả. Do đó, **`status=503` không đủ để khẳng định catalog-service đã trả 503**.

Cách kiểm chứng:

1. Ghi `serviceId` và số ứng viên từ supplier.
2. Quan sát có `ServiceInstance` được chọn hay không.
3. Kiểm tra HTTP request đã được gửi tới backend chưa.
4. Nếu có response, phân biệt nguồn backend, gateway hoặc một lớp trung gian.
5. Gắn correlation/trace ID và nguyên nhân tới failure model.

`NO_SERVICE_INSTANCE` mang ngữ cảnh lỗi discovery, cache, health check hoặc route policy; `DOWNSTREAM_UNAVAILABLE` từ response 503 có thể mang ý nghĩa quá tải/bảo trì ở backend. Hai loại có thể có cùng quyết định trả một HTTP status tới người dùng, nhưng **vẫn cần được phân loại khác trong log/metrics và vận hành**.

## 16. Retryability không được tính chỉ từ exception class

Một quy tắc đơn giản “cứ `IOException` là retry” có thể sai với thao tác ghi. Cần biết **operation có side effect hay không** và liệu server có **idempotency**.

| Loại failure | GET chỉ đọc | POST tạo đơn có idempotency | POST tạo đơn không idempotency |
|---|---|---|---|
| Không có instance | Có thể thử lại có giới hạn nếu discovery đang hồi phục | Chỉ theo deadline và key ổn định | Không tự retry vô hạn |
| Connect failure rõ ràng trước khi gửi | Có thể retry | Có thể retry cùng key | Cần xác minh transport |
| Read/response timeout | Có thể retry theo budget | UNKNOWN; query/retry cùng key | **Không retry mù** |
| HTTP 429 | Xem `Retry-After`, deadline | Chỉ khi contract cho phép | Thận trọng |
| HTTP 503/504 | Retry có điều kiện | UNKNOWN nếu side effect có thể đã xảy ra | Không tự coi thất bại là rollback |
| HTTP 400/401/403 | Thường không retry cùng request | Sửa input/credentials | Sửa input/credentials |
| HTTP 404 resource missing | Không | Không áp dụng tương tự | Không áp dụng tương tự |
| Decode failure sau HTTP 2xx | Điều tra schema; có thể không retry | Tránh tạo tác dụng phụ lặp | Không retry mù |

Một `retryable` flag duy nhất trong `DownstreamFailure` là tiện cho logging nhưng dễ gây lạm dụng. Quyết định cuối nên thuộc **resilience policy** ở boundary có đủ thông tin:

~~~text
shouldRetry = errorKind có thể phục hồi
              AND operation cho phép lặp / có idempotency
              AND attempts còn trong giới hạn
              AND deadline còn đủ thời gian
              AND retry budget toàn hệ thống cho phép
~~~

Nếu client, LoadBalancer, gateway và service mesh cùng retry, số HTTP attempts có thể bị nhân lên. Tầng ứng dụng nên biết tổng attempt count thay vì chỉ nhìn retry cấu hình trong một thư viện.

## 17. Kết quả không xác định với thao tác ghi

Ví dụ `POST /api/orders` được server xử lý thành công nhưng response bị mất. Caller có thể chỉ thấy `ResourceAccessException`, `WebClientRequestException` hoặc `RetryableException`, tùy client và transport.

~~~mermaid
sequenceDiagram
    participant C as order-service
    participant LB as LoadBalancer
    participant A as inventory-a
    participant DB as Database
    participant B as inventory-b

    C->>LB: POST key=K
    LB-->>C: Chọn A
    C->>A: POST /reserve key=K
    A->>DB: COMMIT reservation #101
    A--xC: Response bị mất
    Note over C: Caller timeout => UNKNOWN
    C->>LB: Retry cùng key K nếu policy cho phép
    LB-->>C: Có thể chọn B
    C->>B: POST /reserve key=K
    B->>DB: Tra cứu key K ở shared store
    DB-->>B: Đã có #101
    B-->>C: Trả kết quả #101, không tạo thêm
~~~

Nếu hệ thống gắn failure `RESPONSE_TIMEOUT` với `outcome=KNOWN_REJECTED`, nó có thể tạo đơn trùng khi retry với key mới. **Outcome certainty phải phản ánh bằng chứng hiện có**, không phải mong muốn của caller.

Quy tắc cho thao tác ghi:

- Tạo và giữ **Idempotency-Key** cố định cho toàn bộ business operation.
- Dùng **shared durable dedup store** với unique key/transaction hoặc cơ chế tương đương.
- Có endpoint query status theo operation ID/key để đối soát.
- Không biến `UNKNOWN` thành `FAILED` chỉ vì caller đã ngừng chờ.
- Khi retry qua LoadBalancer có thể chọn instance khác, không được chỉ lưu key trong RAM của một instance.
- Với side effect ngoài DB, cần giao thức chống trùng riêng hoặc outbox/saga/reconciliation.

## 18. Trả lỗi cho API inbound: không rò thông tin downstream

Một service caller thường đồng thời là HTTP server cho client khác. Sau khi adapter chuyển failure thành `DownstreamCallException`, tầng inbound có thể ánh xạ sang **ProblemDetail** của Spring Framework:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiFailureAdvice {

    @ExceptionHandler(DownstreamCallException.class)
    ResponseEntity<ProblemDetail> onDownstreamFailure(
            DownstreamCallException ex) {

        FailureKind kind = ex.failure().kind();

        HttpStatus outboundStatus = switch (kind) {
            case RESOURCE_NOT_FOUND -> HttpStatus.NOT_FOUND;
            case VALIDATION_REJECTED -> HttpStatus.BAD_REQUEST;
            case CONFLICT -> HttpStatus.CONFLICT;
            case RATE_LIMITED -> HttpStatus.SERVICE_UNAVAILABLE;
            case NO_SERVICE_INSTANCE,
                 DOWNSTREAM_UNAVAILABLE,
                 CONNECT_FAILURE,
                 RESPONSE_TIMEOUT -> HttpStatus.SERVICE_UNAVAILABLE;
            default -> HttpStatus.BAD_GATEWAY;
        };

        ProblemDetail problem = ProblemDetail.forStatus(outboundStatus);
        problem.setTitle("Unable to complete request");
        problem.setDetail(
            "The requested operation could not be completed at this time");
        problem.setProperty(
            "code",
            ex.failure().kind().name()
        );

        return ResponseEntity.status(outboundStatus).body(problem);
    }
}
~~~

**Đây là policy minh họa chứ không phải mapping bắt buộc.** API công khai có thể chọn status khác theo contract, ví dụ `502 Bad Gateway` khi downstream vi phạm hợp đồng hoặc `504 Gateway Timeout` cho một gateway thực sự timeout. Không được tự chuyển HTTP 401 của downstream thành HTTP 401 cho end user nếu vấn đề chỉ là **credential của service-to-service**: nó có thể gây đăng nhập lại vô ích hoặc lộ thông tin nội bộ.

Hãy chú ý:

1. **HTTP 404 downstream** không phải lúc nào cũng tương đương resource mà API inbound của caller công bố không tồn tại.
2. **HTTP 409 downstream** có thể là conflict nghiệp vụ nhưng cũng có thể là lỗi version/contract nội bộ.
3. **HTTP 429 downstream** không nhất thiết là caller bên ngoài đã vượt quota; có thể do chính caller-service bắn quá nhiều request.
4. Không đưa `serviceId`, host/port, raw response body, stack trace hay access token vào public ProblemDetail mặc định.
5. Với một thao tác ghi `UNKNOWN`, nên có hợp đồng riêng về trạng thái chờ xác minh/operation ID; thông báo “đã thất bại chắc chắn” sẽ sai.

## 19. Không dùng fallback để che lỗi hợp đồng

Fallback có thể hữu ích nếu một thông tin phụ có thể không sẵn sàng, nhưng dễ tạo sai lệch khi lỗi mang ý nghĩa business.

| Tình huống | Fallback có thể chấp nhận | Fallback nguy hiểm |
|---|---|---|
| Danh sách gợi ý sản phẩm lỗi | Trả danh sách rỗng có đánh dấu degraded | Đánh dấu order đã hoàn tất |
| Catalog đọc sản phẩm lỗi | Dùng cache đọc có TTL/đánh dấu stale | Tự sinh giá/tồn kho không được xác nhận |
| Payment request timeout | Trả `UNKNOWN/PENDING` và operation ID | Trả success giả hoặc tạo payment mới |
| HTTP 404 có nghĩa item không tồn tại | Trả NotFound nghiệp vụ | Retry hàng loạt hoặc trả object giả |
| Decoder không đọc được schema mới | Báo lỗi tích hợp, cảnh báo | Im lặng bỏ trường dữ liệu quan trọng |

Một fallback phải làm rõ **độ tin cậy của dữ liệu**, không biến hệ thống lỗi thành kết quả có vẻ thành công. Với reactive pipeline, tránh `onErrorResume(error -> Mono.empty())` cho mọi lỗi: nó có thể khiến tầng sau không biết dependency đã hỏng.

## 20. Logging, tracing và các thông số không được bỏ

Khi phân loại lỗi vào một model chung, vẫn phải giữ nguồn gốc để vận hành:

| Metadata | Vai trò |
|---|---|
| `serviceId` | Dịch vụ logic được gọi |
| Operation/route template | Endpoint và ý nghĩa nghiệp vụ; tránh URL có PII |
| `selectedInstance` nếu có | Đích LoadBalancer chọn, phục vụ chẩn đoán |
| Exception class/cause gốc | Phân biệt HTTP, I/O, TLS, codec |
| HTTP status và nguồn response | Biết status từ backend/gateway hay giả định |
| `FailureKind` và `diagnosticCode` | Nhóm lỗi ổn định cho ứng dụng |
| Request attempt / retry count | Biết có bao nhiêu lần thử |
| Timeout loại nào | Pool, connect, read, total deadline |
| `OutcomeCertainty` | Tránh nhận định sai về side effect |
| Trace ID/correlation ID | Liên kết caller, LoadBalancer và server |
| Time-to-first-byte, duration | Tìm giai đoạn chậm |
| Response schema/media type | Phân tích lỗi decode |

Không đưa **request ID hoặc idempotency key raw** vào nhãn metric có cardinality cao. Nếu cần log chi tiết, che dữ liệu nhạy cảm và dùng trace/log có kiểm soát. Server, gateway và caller có thể đều ghi HTTP status khác nhau cho cùng transaction; dùng trace và operation ID để phân biệt các ranh giới.

### Vì sao không nên chỉ đếm 5xx?

Một request có thể thất bại **trước HTTP response**, nên metric `http.client.response.status=5xx` có thể không đếm được lỗi connect, pool acquire hay không chọn được instance. Cần thêm metric error cause, `NO_SERVICE_INSTANCE` và outcome UNKNOWN.

## 21. Kiểm thử hợp đồng mapping cho từng client

Dùng cùng API mock/stub (ví dụ WireMock, MockWebServer hoặc server thử nghiệm) và cùng bảng test cho RestClient, WebClient, OpenFeign. Unit test có thể mock ngoại lệ client để kiểm tra mapper, còn integration test phải gửi HTTP thật để xác minh response/cause.

| Kịch bản | RestClient | WebClient | OpenFeign | FailureKind kỳ vọng |
|---|---|---|---|---|
| HTTP 404 + `ITEM_NOT_FOUND` | `RestClientResponseException` | `WebClientResponseException` | `FeignException.NotFound` | `RESOURCE_NOT_FOUND` |
| HTTP 404 sai route | HTTP response | HTTP response | HTTP response | `DOWNSTREAM_REJECTED` |
| HTTP 409 business conflict | HTTP response | HTTP response | HTTP response | `CONFLICT` |
| HTTP 429 | HTTP response | HTTP response | HTTP response | `RATE_LIMITED` |
| HTTP 503 backend | HTTP response | HTTP response | HTTP response | `DOWNSTREAM_UNAVAILABLE` |
| Không có `ServiceInstance` | Theo LB integration | Theo LB integration | Theo LB integration | `NO_SERVICE_INSTANCE` khi xác minh nguồn |
| Connect refused | `ResourceAccessException` hoặc cause | `WebClientRequestException` hoặc cause | Feign transport exception | `CONNECT_FAILURE` |
| Read timeout | I/O exception/cause | Request/timeout signal | Feign transport/cause | `RESPONSE_TIMEOUT` |
| HTTP 200 nhưng JSON sai | Converter exception | Codec/DecodingException | Feign decoder exception | `DECODE_FAILURE` |
| POST đã commit nhưng response mất | I/O failure | Request/error signal | Feign exception | `UNKNOWN` outcome |

**Điểm khó của test:** nếu mapper chỉ dựa status mà không đọc code hợp đồng, nó **không thể tự phân biệt** hai hàng 404 đầu tiên. Cần bổ sung parser error body hợp lệ, contract từng operation và test tương ứng.

### Kiểm thử LoadBalancer với hai instance

Với `SimpleDiscoveryClient`, có thể tạo hai instance `catalog-a` và `catalog-b`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Các thử nghiệm quan trọng:

1. Service ID hợp lệ và hai instance healthy: request có thể đến cả hai.
2. Gỡ hết instance khỏi supplier: xác minh **không gửi request** tới backend và ánh xạ `NO_SERVICE_INSTANCE` theo integration thực tế.
3. Instance A chết nhưng supplier còn A: lỗi kết nối được tách khỏi HTTP 503 do B trả.
4. Proxy/gateway trả 503: ghi nhận nguồn response để không nhầm `NO_SERVICE_INSTANCE`.
5. Backend trả 200 nhưng body sai: bảo đảm không map thành `DOWNSTREAM_UNAVAILABLE` chung chung.
6. POST timeout sau commit: giữ outcome UNKNOWN và không retry với idempotency key mới.

## 22. Checklist trước khi triển khai mô hình lỗi

- Đã có **taxonomy lỗi ứng dụng** độc lập với RestClient, WebClient và Feign chưa?
- Có phân biệt **lỗi chọn instance, transport, response status, decode và business validation** chưa?
- HTTP status được map theo **operation và contract code**, không chỉ theo một con số chưa?
- Có giữ lại exception cause và metadata an toàn để debug không?
- Với Feign, có kiểm tra `ErrorDecoder` và `Retryer` thực tế không?
- Với RestClient, đã phân biệt `retrieve()` và `exchange()` chưa?
- Với WebClient, lỗi được map trong reactive pipeline, không biến mọi cancel thành error chưa?
- Có phân loại read timeout/unknown outcome của POST không?
- Retry policy có xét idempotency, deadline và attempt budget không?
- Error response inbound có tránh lộ URL, token, body và stack trace không?
- HTTP 401/403/404/409/429 downstream có thật sự cùng nghĩa với API inbound không?
- Có test cả HTTP 2xx body sai schema và không có `ServiceInstance` không?
- Có traces/logs cho `selectedInstance` và response source không?
- Với fallback, có ghi nhận trạng thái degraded/unknown thay vì giả success không?
- Có giám sát các sự cố trước HTTP response, không chỉ biểu đồ 5xx không?

## 23. Kết luận

**RestClient**, **WebClient** và **OpenFeign** có những kiểu exception và API xử lý lỗi khác nhau. Chúng chỉ là các **adapter giao tiếp**; tầng ứng dụng nên nhận một **mô hình lỗi thống nhất** biểu diễn **FailureKind, nguồn tín hiệu, HTTP status nếu có, outcome certainty và cause**. Ánh xạ đúng cần dựa trên **hợp đồng của endpoint**, không chỉ status hoặc tên exception.

Trong Spring Cloud LoadBalancer, các vấn đề từ **discovery, health check, cache và chính sách chọn `ServiceInstance`** có thể khiến request chưa từng đến server. Ngược lại, timeout hoặc lỗi nhận response có thể xảy ra **sau khi server đã tạo side effect**. Phân biệt hai khả năng này giúp lựa chọn đúng cách trả lỗi, retry có ngân sách, idempotency, fallback và đối soát. Một mô hình lỗi tốt không che mất chi tiết hạ tầng; nó **chuyển chúng thành ngữ nghĩa ổn định cho nghiệp vụ, đồng thời giữ đủ bằng chứng để vận hành và kiểm thử**.

