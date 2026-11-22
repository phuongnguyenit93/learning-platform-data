# Tiêu thụ hoặc giải phóng body ở mọi nhánh xử lý

Khi dùng **Spring WebClient**, mỗi HTTP response có một body được đọc theo kiểu reactive. Body có thể chứa JSON, text, binary hoặc stream dài. Một response body chưa được tiêu thụ hoặc giải phóng có thể giữ DataBuffer, khiến connection không thể được tái sử dụng đúng cách hoặc tạo áp lực tài nguyên. Vì vậy, mọi nhánh xử lý response cần có quyết định rõ ràng: **decode body**, **drain và release body**, hoặc **chuyển response nguyên vẹn cho downstream để thành phần đó tiêu thụ**.

Quy tắc này đặc biệt quan trọng khi dùng API truy cập trực tiếp response như **exchangeToMono**, **exchangeToFlux**, **ExchangeFilterFunction** hoặc **ExchangeFunction**. Khi dùng **retrieve()**, WebClient cung cấp các bước trích xuất body và xử lý status phổ biến, nhưng custom status handler vẫn phải được thiết kế đúng.

Bài này tập trung vào vòng đời body của WebClient, cách xử lý success/error/not-found/empty response, cách viết filter và retry an toàn, cùng ví dụ Java 17 có kiểm thử cho từng nhánh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao response body phải được tiêu thụ hoặc giải phóng.
2. Phân biệt **retrieve()** với **exchangeToMono()** và **exchangeToFlux()**.
3. Dùng **bodyToMono**, **bodyToFlux**, **toEntity**, **toBodilessEntity** và **releaseBody** đúng mục đích.
4. Xử lý status thành công, 404, 204 và 4xx/5xx mà không bỏ quên body.
5. Hiểu ý nghĩa chính xác của **onStatus** khi handler trả **Mono.empty()**.
6. Viết **ExchangeFilterFunction** sao cho chỉ giữ response khi downstream sẽ tiếp tục tiêu thụ.
7. Xử lý body trong mọi nhánh error, retry, timeout và cancellation.
8. Tránh đọc body nhiều lần hoặc trả **ClientResponse** ra ngoài **exchangeToMono** để decode muộn.
9. Phân biệt **releaseBody()** với **bodyToMono(Void.class)**.
10. Kiểm thử lifecycle bằng MockWebServer, Reactor Test và WebClient.

## 2. Vì sao response body phải được xử lý?

WebClient là HTTP client reactive. Response body thường được cung cấp dưới dạng luồng byte và được giải mã dần qua codec. Với Reactor Netty, byte có thể nằm trong pooled direct memory. Framework cần biết khi nào body đã được đọc xong hoặc khi nào phần còn lại có thể được discard.

Nếu một nhánh nhận response rồi bỏ qua body:

- Buffer có thể không được giải phóng đúng thời điểm.
- Connection có thể không trở về pool để tái sử dụng.
- Request tiếp theo có thể phải mở connection mới.
- Khi nhiều response bị bỏ quên, memory, socket hoặc connection pool có thể chịu áp lực.
- Retry có thể tạo request mới trong khi response trước vẫn chưa được xử lý xong.

Mỗi response body là một tài nguyên có vòng đời. Đọc status hoặc header không đồng nghĩa với việc body đã được tiêu thụ.

### 2.1. Ba lựa chọn hợp lệ cho mỗi nhánh

| Quyết định | Cách làm | Khi phù hợp |
| --- | --- | --- |
| Decode body | bodyToMono, bodyToFlux, toEntity hoặc body(BodyExtractor) | Ứng dụng cần dữ liệu response |
| Discard body | releaseBody() hoặc toBodilessEntity() | Chỉ cần status/header hoặc quyết định bỏ response |
| Chuyển tiếp response | Trả ClientResponse cho downstream | Filter muốn để caller tiếp tục đọc body |

Không được vừa đọc body vừa kỳ vọng một thành phần khác đọc lại cùng body từ đầu. Body là stream một lần; khi đã được tiêu thụ, publisher không thể được phát lại như một object Java thông thường.

### 2.2. Đọc header không tiêu thụ body

Ví dụ sau chỉ kiểm tra status:

~~~java
return webClient.get()
    .uri("/api/items/42")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return Mono.just(response.statusCode().value());
        }
        return Mono.just(response.statusCode().value());
    });
~~~

Callback không đọc body. Với exchangeToMono, Spring sẽ tự giải phóng body còn chưa được tiêu thụ sau khi publisher callback hoàn tất. Đây là safety net hữu ích, nhưng nếu code muốn bỏ body thì gọi releaseBody() tường minh sẽ làm ý định rõ hơn và dễ review hơn.

Nếu dùng raw ExchangeFunction hoặc filter tự giữ/đổi response, trách nhiệm chuyển tiếp hoặc release phải được xác định rõ trong từng nhánh.

## 3. Các API đọc và giải phóng body

### 3.1. bodyToMono và bodyToFlux

Dùng bodyToMono(Type.class) khi response chứa một object hoặc một body cần giải mã thành một giá trị:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Dùng bodyToFlux(Type.class) khi body biểu diễn một stream các phần tử và codec/media type hỗ trợ:

~~~java
Flux<Product> products = webClient.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class);
~~~

Các publisher này tiêu thụ body khi được subscribe và demand dữ liệu. Nếu caller không subscribe, request cũng chưa được thực thi theo cách reactive thông thường. Nếu caller subscribe nhưng hủy sớm, việc xử lý phần còn lại phụ thuộc transport và lifecycle cancellation; không nên coi việc lấy một phần tử là tương đương với việc drain toàn bộ response.

### 3.2. toEntity và toBodilessEntity

toEntity(Product.class) trả về ResponseEntity<Product> có status, headers và body đã decode:

~~~java
Mono<ResponseEntity<Product>> entity = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class);
~~~

toBodilessEntity() trả status và headers nhưng không giữ body. Nó tiêu thụ/giải phóng body và phù hợp với endpoint mà ứng dụng chỉ quan tâm metadata:

~~~java
Mono<ResponseEntity<Void>> result = webClient.delete()
    .uri("/products/{id}", id)
    .retrieve()
    .toBodilessEntity();
~~~

Nếu cần body, không dùng toBodilessEntity() rồi tìm cách decode lại sau đó.

### 3.3. releaseBody()

ClientResponse.releaseBody() trả Mono<Void> và tiêu thụ body để giải phóng nội dung mà ứng dụng không cần:

~~~java
Mono<Void> discarded = response.releaseBody();
~~~

Dùng nó trong nhánh đã quyết định bỏ body, chẳng hạn 404 được ánh xạ thành Optional.empty hoặc filter từ chối response chỉ dựa trên status.

releaseBody() không trả body cho code phía sau. Khi publisher hoàn tất, response body đã được xử lý theo mục đích discard.

### 3.4. bodyToMono(Void.class) không giống releaseBody()

Có thể gặp cách viết:

~~~java
response.bodyToMono(Void.class)
~~~

Tài liệu Spring lưu ý rằng nếu response thực tế có content, cách này có thể khiến connection bị đóng thay vì được đưa trở lại pool, vì body content không được drain theo cách mà releaseBody() thực hiện. Khi mục đích là bỏ body và giải phóng nội dung, ưu tiên releaseBody() hoặc toBodilessEntity().

Nếu API cam kết response không có body, bodyToMono(Void.class) có thể phù hợp, nhưng không nên dùng nó như cách thay thế chung cho release.

## 4. retrieve(): đường xử lý phổ biến

retrieve() phù hợp khi logic chủ yếu là gọi endpoint và decode body. Ví dụ:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Mặc định, response status 4xx hoặc 5xx được ánh xạ thành WebClientResponseException. WebClient tạo exception có thông tin status, headers, request và body response đã được đọc vào exception. Như vậy, body lỗi mặc định cũng được xử lý thay vì bị bỏ quên.

### 4.1. Đọc error body trong onStatus

Khi remote API trả error DTO, có thể decode body rồi tạo exception nghiệp vụ:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(HttpStatusCode::isError, response ->
        response.bodyToMono(ApiError.class)
            .defaultIfEmpty(new ApiError("remote error"))
            .map(error ->
                new RemoteServiceException(error.message())
            )
    )
    .bodyToMono(Product.class);
~~~

Handler onStatus trả Mono<? extends Throwable>. Ví dụ trên đọc body thành ApiError trước khi tạo exception, nên body đã được tiêu thụ.

Nếu body lỗi không cần thiết, có thể release rồi trả exception:

~~~java
.onStatus(
    status -> status.value() == 503,
    response -> response.releaseBody()
        .thenReturn(new RemoteUnavailableException())
)
~~~

Nhánh này bỏ body một cách tường minh trước khi phát lỗi.

### 4.2. Ý nghĩa của Mono.empty() trong onStatus

Đây là quy tắc rất dễ hiểu sai:

~~~java
.onStatus(
    status -> status.value() == 404,
    response -> Mono.empty()
)
.bodyToMono(Product.class);
~~~

Mono.empty() trong handler onStatus có nghĩa là **không tạo error signal cho status đó**. WebClient coi response là bình thường và tiếp tục chuyển response cho bước body extraction phía sau. Nó không tự động có nghĩa “bỏ response body”.

Vì vậy, nếu muốn đọc body 404 như một DTO, có thể suppress status error rồi decode ở downstream. Nếu muốn bỏ body và trả Optional.empty, nên dùng exchangeToMono với releaseBody() để thể hiện rõ cả hai quyết định.

Không đọc body trong onStatus rồi trả Mono.empty() và mong bodyToMono phía sau vẫn thấy nội dung ban đầu. Body đã được tiêu thụ một lần.

### 4.3. onStatus trả exception nhưng không đọc body

Khi custom handler trả lỗi mà không tiêu thụ body, WebClient có cleanup cho status handler để release body chưa được tiêu thụ. Tuy nhiên, trong code review nên làm rõ ý định:

- Cần nội dung lỗi: decode body trong handler.
- Không cần nội dung lỗi: gọi releaseBody rồi tạo exception.
- Muốn xử lý status như response bình thường: trả Mono.empty và để downstream decode body.

Cách viết tường minh giúp tránh phụ thuộc vào việc người đọc phải biết chi tiết cleanup nội bộ.

## 5. exchangeToMono(): mọi nhánh trong callback

exchangeToMono cho phép kiểm tra status/header rồi quyết định cách decode. Đây là lựa chọn tốt khi success, 404, 204 và error có các hợp đồng body khác nhau.

Ví dụ:

~~~java
Mono<Optional<Product>> findProduct(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class)
                    .map(Optional::of)
                    .defaultIfEmpty(Optional.empty());
            }

            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                    .thenReturn(Optional.empty());
            }

            return response.createError();
        });
}
~~~

Mỗi nhánh có một quyết định body rõ ràng:

- 2xx: decode thành Product.
- 404: discard body bằng releaseBody rồi trả Optional.empty.
- Các status khác: createError tạo error từ response và xử lý body lỗi.

Sau khi publisher được callback trả về hoàn tất, Spring kiểm tra response body. Nếu callback không tiêu thụ body, Spring tự release phần chưa đọc để tránh rò memory/connection. Nhưng body không thể được decode thêm ở downstream sau khi callback hoàn tất.

### 5.1. 204 No Content

Với endpoint có thể trả 204, không cần cố decode DTO:

~~~java
if (response.statusCode().value() == 204) {
    return response.toBodilessEntity()
        .thenReturn(Optional.empty());
}
~~~

toBodilessEntity() lấy status/header và discard body nếu có. Với 204 theo HTTP semantics, server không nên gửi response content; cách viết này vẫn thể hiện rõ rằng code không cần body.

### 5.2. Không trả ClientResponse để decode sau callback

Không viết:

~~~java
Mono<ClientResponse> responseMono = webClient.get()
    .uri("/products/42")
    .exchangeToMono(response -> Mono.just(response));

return responseMono.flatMap(response ->
    response.bodyToMono(Product.class)
);
~~~

exchangeToMono quản lý vòng đời response trong callback. Khi callback publisher hoàn tất mà body chưa được tiêu thụ, framework release body. Vì thế code phía sau nhận một response đã hết quyền đọc body như mong muốn.

Hãy decode hoặc release ngay bên trong callback:

~~~java
return webClient.get()
    .uri("/products/42")
    .exchangeToMono(response ->
        response.bodyToMono(Product.class)
    );
~~~

### 5.3. createError và createException

- createException() tạo Mono<WebClientResponseException> chứa status, headers, request và body đã đọc.
- createError() tạo publisher phát exception tương ứng, thuận tiện trong nhánh exchangeToMono.
- Nếu cần kiểu exception riêng, decode error DTO rồi tạo exception nghiệp vụ.
- Nếu không cần body, releaseBody trước khi tạo exception của ứng dụng.

Không gọi createException() hai lần trên cùng response với kỳ vọng có thể đọc body hai lần. Body là tài nguyên một lần.

## 6. exchangeToFlux(): xử lý stream và status

exchangeToFlux áp dụng cùng nguyên tắc cho response nhiều phần tử:

~~~java
Flux<Product> products = webClient.get()
    .uri("/products")
    .exchangeToFlux(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToFlux(Product.class);
        }

        return response.createError().flux();
    });
~~~

Nhánh thành công chuyển body thành Flux<Product>. Nhánh lỗi tạo error từ response. Khi Flux callback hoàn tất, response body chưa được tiêu thụ sẽ được tự động release.

Nếu downstream chỉ lấy một phần stream rồi cancel, transport sẽ nhận cancellation. Với dữ liệu cần bỏ hoàn toàn, chọn releaseBody() trong callback thay vì tạo Flux body rồi để không ai subscribe.

Ví dụ endpoint trả stream nhưng client chỉ cần metadata:

~~~java
Mono<Integer> statusOnly = webClient.get()
    .uri("/exports")
    .exchangeToMono(response ->
        response.releaseBody()
            .thenReturn(response.statusCode().value())
    );
~~~

Nhánh này không decode stream và không giữ DataBuffer cho downstream.

## 7. Xử lý trong ExchangeFilterFunction

Client filter chạy giữa WebClient request và exchange function. Filter nhận response trước khi caller đọc body.

### 7.1. Chỉ sửa request, chuyển response nguyên vẹn

Nếu filter chỉ thêm header request, không cần đọc body:

~~~java
ExchangeFilterFunction addClientHeader =
    (request, next) -> {
        ClientRequest updated = ClientRequest.from(request)
            .header("X-Client-App", "catalog")
            .build();

        return next.exchange(updated);
    };
~~~

Response được chuyển nguyên vẹn về caller. Caller chịu trách nhiệm decode hoặc release body bằng retrieve/exchangeTo.

### 7.2. Filter từ chối response lỗi và không cần body

Nếu filter quyết định biến mọi status lỗi thành exception chung, phải release body trước khi phát lỗi:

~~~java
ExchangeFilterFunction rejectErrorStatus =
    (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().isError()) {
                HttpStatusCode status = response.statusCode();

                return response.releaseBody()
                    .then(Mono.error(
                        new RemoteStatusException(status)
                    ));
            }

            // Success response được chuyển tiếp để caller đọc body.
            return Mono.just(response);
        });
~~~

Nhánh success trả response cho downstream; filter không đọc body. Nhánh error discard body rồi phát exception; không còn response nào được chuyển tiếp.

### 7.3. Filter cần nội dung error body

Nếu filter cần nội dung error để tạo exception:

~~~java
ExchangeFilterFunction mapRemoteErrors =
    (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (!response.statusCode().isError()) {
                return Mono.just(response);
            }

            return response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError("unknown remote error"))
                .flatMap(error ->
                    Mono.error(
                        new RemoteServiceException(error.message())
                    )
                );
        });
~~~

Body được decode trong filter rồi filter phát lỗi. Không trả response đã tiêu thụ cho caller để caller đọc lại.

### 7.4. Filter inspect body rồi vẫn muốn forward

Nếu filter cần đọc body để ghi log nhưng caller vẫn cần body, filter phải thiết kế việc buffer và tái tạo body một cách có giới hạn. Việc đọc body thành byte[] có thể aggregate toàn bộ payload, nên chỉ phù hợp với response nhỏ có giới hạn rõ ràng.

Với file/stream lớn, không nên bật logging body toàn phần. Ưu tiên log status, headers đã lọc, duration, content length và correlation ID. Nếu cần quan sát payload, dùng instrumentation chuyên biệt có giới hạn kích thước và masking.

## 8. Branch matrix: kiểm tra mọi đường đi

Trước khi viết code, liệt kê các kết quả status và quyết định body tương ứng:

| Tình huống | Cần dữ liệu body? | Hành động |
| --- | --- | --- |
| 200 JSON | Có | bodyToMono DTO |
| 200 stream | Có | bodyToFlux và consume theo demand |
| 201 Created | Có hoặc không | bodyToMono/toEntity hoặc toBodilessEntity |
| 204 No Content | Không | toBodilessEntity/releaseBody |
| 404 được coi là empty | Không | releaseBody rồi trả empty |
| 404 cần thông báo chi tiết | Có | decode error body rồi map |
| 401/403 | Có thể không | decode error hoặc release rồi tạo exception |
| 429/503 retry | Tùy | consume/decode hoặc release trước khi phát lỗi để retry |
| 5xx bất ngờ | Có thể cần diagnostic | createError hoặc decode error DTO |
| Status không mong đợi | Không | releaseBody rồi phát lỗi |
| Filter chỉ đổi request | Không đọc response | chuyển nguyên response downstream |
| Filter chặn response | Tùy | consume hoặc release trước khi trả error |

Mỗi hàng là một nhánh độc lập. Không để một status đi qua nhánh return Mono.just(response) nếu không có thành phần downstream nào chịu trách nhiệm đọc body.

## 9. Retry, timeout, cancellation và lỗi decode

### 9.1. Retry sau status lỗi

Retry tạo subscription/request mới. Nếu một response lỗi được chuyển thành exception để retry, body của response trước phải được xử lý trước khi retry tiếp tục.

Ví dụ dùng exchangeToMono:

~~~java
Mono<Product> loadWithRetry(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }

            if (response.statusCode().value() == 503) {
                return response.releaseBody()
                    .then(Mono.error(new RetryableRemoteException()));
            }

            return response.createError();
        })
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(RetryableRemoteException.class::isInstance)
        );
}
~~~

Nhánh 503 release body trước khi error tới retry operator. Nhánh status khác dùng createError để đọc response và phát exception. Không retry mọi lỗi một cách mù quáng; phân biệt lỗi tạm thời, lỗi validation, lỗi authorization và lỗi decode.

### 9.2. Timeout

timeout có thể hủy publisher đang đọc body. Cancellation phải truyền tới transport để ngừng nhận dữ liệu. Nếu code tự giữ DataBuffer hoặc mở file/channel, phải cleanup theo lifecycle cancellation.

Không bắt timeout rồi bỏ publisher/body đang chạy mà không xác định tài nguyên nào còn được giữ. Đặt timeout hợp lý theo loại API, kích thước body và SLA.

### 9.3. Lỗi khi decode

Nếu bodyToMono hoặc bodyToFlux phát lỗi decode, codec chịu trách nhiệm quản lý DataBuffer theo contract của nó. Code ứng dụng không nên tự release buffer đã được codec tiêu thụ. Nếu tự dùng bodyToFlux(DataBuffer.class), ứng dụng nhận ownership ở mức DataBuffer và phải release sau khi đọc hoặc chuyển tiếp đúng cách.

### 9.4. Cancellation khi đọc stream

Nếu caller hủy stream giữa chừng, không tiếp tục giữ subscription hoặc cache body để dùng lại. Với raw DataBuffer stream, release từng buffer đã nhận và bảo đảm buffer bị discard được cleanup nếu pipeline có operator có thể bỏ phần tử.

Nếu mục đích là bỏ toàn bộ response ngay từ đầu, dùng releaseBody() thay vì subscribe một phần rồi cancel.

## 10. Đọc DataBuffer trực tiếp

Thông thường hãy decode body thành DTO/String. Chỉ nhận DataBuffer trực tiếp khi cần byte-level processing, proxy, checksum hoặc ghi stream xuống file.

Ví dụ tính kích thước từng buffer:

~~~java
Mono<Long> countBytes(ClientResponse response) {
    return response.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                return (long) buffer.readableByteCount();
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .reduce(0L, Long::sum);
}
~~~

Ở đây code tự tiêu thụ DataBuffer nên release trong finally. Không release buffer lần nữa ở một operator downstream. Nếu chuyển buffer sang writer hoặc API nhận ownership, để thành phần nhận quản lý theo contract.

Không dùng collectList() để giữ tất cả DataBuffer. Với file lớn, ghi từng buffer xuống file hoặc cập nhật digest rồi release ngay.

## 11. Ví dụ Java 17: WebClient xử lý mọi nhánh

Ví dụ dùng Spring Boot 3.3.5 và Java 17. Client có hai cách gọi:

- findProduct dùng exchangeToMono: 2xx decode DTO, 404 release và trả Optional.empty, status khác tạo error.
- getProductWithRetrieve dùng retrieve: đọc error DTO trong onStatus và tạo exception nghiệp vụ.

### 11.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 11.2. DTO và exception

~~~java
package demo;

record Product(String id, String name) {}
record ApiError(String message) {}

class RemoteServiceException extends RuntimeException {
    RemoteServiceException(String message) {
        super(message);
    }
}
~~~

### 11.3. ProductClient.java

~~~java
package demo;

import java.util.Optional;

import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
class ProductClient {

    private final WebClient client;

    ProductClient(WebClient client) {
        this.client = client;
    }

    Mono<Optional<Product>> findProduct(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty());
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                        .thenReturn(Optional.empty());
                }

                return response.createError();
            });
    }

    Mono<Product> getProductWithRetrieve(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .retrieve()
            .onStatus(HttpStatusCode::isError, response ->
                response.bodyToMono(ApiError.class)
                    .defaultIfEmpty(new ApiError("remote error"))
                    .map(error ->
                        new RemoteServiceException(error.message())
                    )
            )
            .bodyToMono(Product.class);
    }

    Mono<Integer> statusOnly(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .exchangeToMono(response ->
                response.releaseBody()
                    .thenReturn(response.statusCode().value())
            );
    }
}
~~~

Constructor nhận WebClient trực tiếp giúp test cung cấp base URL local. Trong ứng dụng Spring Boot, tạo một bean WebClient đã cấu hình bằng WebClient.Builder rồi inject vào client service.

### 11.4. ProductClientTest.java

~~~java
package demo;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductClientTest {

    private MockWebServer server;
    private ProductClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new ProductClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void successBranchDecodesBody() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findProduct("p-1"))
            .expectNext(Optional.of(
                new Product("p-1", "Keyboard")
            ))
            .verifyComplete();
    }

    @Test
    void notFoundBranchReleasesBodyAndReturnsEmpty() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"not found\"}"));

        StepVerifier.create(client.findProduct("missing"))
            .expectNext(Optional.empty())
            .verifyComplete();
    }

    @Test
    void unexpectedStatusBecomesWebClientResponseException() {
        server.enqueue(new MockResponse()
            .setResponseCode(502)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"gateway failed\"}"));

        StepVerifier.create(client.findProduct("p-2"))
            .expectErrorSatisfies(error -> {
                assertTrue(error instanceof WebClientResponseException);
                WebClientResponseException responseError =
                    (WebClientResponseException) error;
                assertEquals(502, responseError.getStatusCode().value());
                assertTrue(
                    responseError.getResponseBodyAsString()
                        .contains("gateway failed")
                );
            })
            .verify();
    }

    @Test
    void retrieveCustomStatusHandlerConsumesErrorDto() {
        server.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"catalog unavailable\"}"));

        StepVerifier.create(
                client.getProductWithRetrieve("p-3")
            )
            .expectErrorSatisfies(error -> {
                assertTrue(error instanceof RemoteServiceException);
                assertEquals(
                    "catalog unavailable",
                    error.getMessage()
                );
            })
            .verify();
    }

    @Test
    void statusOnlyBranchDiscardsBody() {
        server.enqueue(new MockResponse()
            .setResponseCode(202)
            .addHeader("Content-Type", "text/plain")
            .setBody("accepted"));

        StepVerifier.create(client.statusOnly("p-4"))
            .expectNext(202)
            .verifyComplete();
    }
}
~~~

Các test xác minh nhánh thành công, 404 discard body, status bất ngờ chuyển thành WebClientResponseException có body, custom status handler decode error DTO và nhánh chỉ đọc status release body.

Chạy test:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Ví dụ dùng MockWebServer để tạo response local; không cần gọi dịch vụ bên ngoài. Test xác nhận hành vi xử lý nhánh, nhưng không thay thế load test cho connection pool hoặc memory dưới tải cao.

## 12. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đọc status rồi bỏ response body | Buffer/connection có thể không được giải phóng đúng lúc | Decode hoặc releaseBody trong nhánh |
| Dùng exchangeToMono rồi trả ClientResponse ra downstream | Body có thể đã bị auto-release khi callback hoàn tất | Decode hoặc release ngay trong callback |
| Nghĩ Mono.empty trong onStatus là discard body | Downstream vẫn nhận response và có thể cố decode body | Hiểu nó là suppress error; dùng releaseBody nếu muốn bỏ |
| Gọi bodyToMono hai lần | Body là stream một lần, lần sau không có dữ liệu như kỳ vọng | Decode một lần thành DTO rồi chia sẻ object |
| Dùng bodyToMono(Void.class) để bỏ body lớn | Connection có thể đóng nếu response thực tế có content | Dùng releaseBody hoặc toBodilessEntity |
| Filter đọc body rồi trả response cũ | Downstream nhận body đã tiêu thụ | Tạo response mới có body đã buffer (chỉ body nhỏ) hoặc không inspect body |
| Filter trả Mono.error mà bỏ body | Response không được chuyển tiếp và body chưa xử lý | releaseBody trước khi phát lỗi |
| Filter đọc success body nhưng vẫn trả ClientResponse | Caller không còn body để decode | Chỉ đọc nếu filter chịu trách nhiệm kết quả, hoặc rebuild có giới hạn |
| Retry trước khi response lỗi được xử lý | Connection và buffer của lần thử trước có thể bị giữ | Decode/release body trước khi phát retryable error |
| Dùng bodyToFlux rồi take(1) khi muốn bỏ toàn bộ body | Stream bị cancel sau một phần; không tương đương drain | Dùng releaseBody nếu không cần bất kỳ nội dung nào |
| Dùng createException rồi lại đọc body | Body đã được tiêu thụ để tạo exception | Dùng dữ liệu có trong exception |
| Log toàn bộ error body | Có thể lộ token, thông tin cá nhân và payload lớn | Log status, request ID và message đã lọc |
| Aggregate error body không giới hạn | Có thể tăng memory khi upstream trả payload lỗi lớn | Giới hạn decoder, chỉ đọc DTO nhỏ hoặc release |
| Tự subscribe trong filter | Tạo subscription tách khỏi request lifecycle | Trả publisher đã ghép |
| Không test nhánh 204/404/error | Có thể bỏ sót body ở nhánh ít gặp | Viết branch matrix và test từng nhánh |

## 13. Checklist review mọi nhánh response

Với mỗi đoạn code nhận ClientResponse, kiểm tra lần lượt:

1. **Success:** body được decode bằng bodyToMono/bodyToFlux/toEntity hay chuyển tiếp cho caller?
2. **No content:** dùng toBodilessEntity/releaseBody khi không cần body chưa?
3. **Not found:** có chủ ý trả empty, error DTO hay WebClientResponseException?
4. **4xx/5xx:** body có được decode vào exception hoặc release trước khi phát lỗi?
5. **Unexpected status:** nhánh mặc định có createError hoặc releaseBody không?
6. **Filter:** success response có được chuyển nguyên vẹn cho downstream? Nhánh chặn có release?
7. **Retry:** response trước có được consume/release trước khi retry?
8. **Cancellation:** publisher có dừng đúng và buffer tự quản có được release?
9. **Single consumption:** có gọi nhiều body extraction method trên cùng response không?
10. **Memory:** có aggregate payload lớn hoặc log toàn bộ body không?
11. **Connection:** có dùng releaseBody thay cho bodyToMono(Void.class) khi cần drain?
12. **Tests:** tất cả status branch có test body present và body empty phù hợp không?

**Ghi nhớ:** mỗi HTTP response body phải có một chủ sở hữu rõ ràng. Decode body nếu cần dữ liệu; gọi releaseBody hoặc toBodilessEntity nếu bỏ; chuyển response nguyên vẹn nếu downstream sẽ đọc. Với exchangeToMono/exchangeToFlux, hãy xử lý body ngay trong callback vì Spring tự release phần chưa đọc sau khi callback hoàn tất. Với retrieve/onStatus, nhớ rằng Mono.empty chỉ suppress error và để bước decode phía sau tiếp tục. Viết branch matrix, kiểm thử từng nhánh và tránh đọc body nhiều lần.

## Tài liệu tham khảo

- Spring Framework — WebClient Exchange: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework — WebClient Retrieve: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — ClientResponse API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html
- Spring Framework — ExchangeFilterFunction API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
