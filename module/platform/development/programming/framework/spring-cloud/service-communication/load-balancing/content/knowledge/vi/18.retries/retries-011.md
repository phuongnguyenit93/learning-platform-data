# Khả năng phát lại request body, upload và streaming

Khi **Spring Cloud LoadBalancer** hoặc HTTP client thử gửi lại một request thất bại, vấn đề không chỉ là chọn `ServiceInstance` cũ hay bản sao khác. Với request có body — đặc biệt là **upload file, multipart hoặc streaming** — client còn phải trả lời: **có thể tạo lại chính xác dữ liệu cần gửi cho lần thử tiếp theo không?**

Một request có thể được retry về mặt mạng nhưng **không phát lại được body** vì nguồn dữ liệu đã bị tiêu thụ. Ngược lại, client có thể phát lại đầy đủ body nhưng vẫn gây **ghi trùng nghiệp vụ**, vì server đã xử lý lần gửi đầu tiên trước khi client gặp timeout.

Bài trong chương **Gửi lại yêu cầu** làm rõ hai thuộc tính độc lập:

- **Replayability (khả năng phát lại):** nguồn body có thể được đọc hoặc tạo lại ở mỗi attempt hay không?
- **Idempotency (tính lũy đẳng ở mức nghiệp vụ):** gửi lại cùng một thao tác có làm phát sinh tác dụng phụ không mong muốn hay không?

Mục tiêu là biết khi nào có thể retry an toàn với `RestClient`, `WebClient` và OpenFeign; khi nào phải từ chối retry; và khi nào cần thiết kế **upload tiếp tục từ checkpoint** thay vì gửi lại một luồng dữ liệu lớn từ đầu.

## 1. Retry một request không chỉ là gửi lại URL

Ví dụ `order-service` gửi một bản ghi lên `media-service`:

~~~http
POST http://media-service/uploads
Content-Type: application/octet-stream
Idempotency-Key: operation-123

<binary body>
~~~

Trong lần thử đầu, LoadBalancer có thể chọn `media-1`. Sau khi server đã nhận hết body nhưng trước lúc client nhận response, kết nối bị mất. Client không thể biết chắc server đã lưu dữ liệu hay chưa.

Nếu retry được kích hoạt:

1. Policy xem lỗi có đáng thử lại không.
2. Client/supplier xác định có chọn lại cùng `ServiceInstance` hay chọn instance khác.
3. HTTP client tạo request mới.
4. **Nguồn request body phải cung cấp dữ liệu một lần nữa.**
5. Server cần nhận diện thao tác bị gửi lặp nếu muốn tránh ghi trùng.

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant LB as LoadBalancer
    participant Stream as Body source
    participant S1 as media-1
    participant S2 as media-2
    App->>LB: POST /uploads, operation-123
    LB-->>App: Chọn media-1
    App->>Stream: Đọc body lần 1
    Stream-->>App: Bytes của file
    App->>S1: Gửi body attempt 1
    S1->>S1: Có thể đã lưu file
    S1--xApp: Mất response / kết nối lỗi
    Note over App: Có retry? Body có thể tạo lại?
    App->>LB: Chọn instance cho attempt 2
    LB-->>App: Có thể chọn media-2
    App->>Stream: Đọc body lần 2
    Stream-->>App: Phải cung cấp lại bytes
    App->>S2: POST cùng operation-123
    Note over S1,S2: Backend cần trạng thái idempotency dùng chung
~~~

Chọn `media-2` không làm dữ liệu ở `media-1` tự trở nên “chưa xử lý”. Nếu hai instance lưu vào hai nơi độc lập mà không có cơ chế phối hợp/idempotency chung, retry sang instance khác còn có thể khiến dữ liệu bị trùng hoặc phân kỳ.

## 2. Phân biệt ba điều kiện: lỗi được retry, body phát lại được và nghiệp vụ an toàn

| Câu hỏi | Ví dụ kết quả | Nếu không đáp ứng |
|---|---|---|
| **Lỗi có phù hợp để retry?** | Lỗi kết nối tạm thời, một số 502/503/504 theo policy | Không retry, trả lỗi hoặc dùng xử lý dự phòng |
| **Body có thể tạo lại?** | Mảng `byte[]` còn nguyên, file có thể mở lại | Không được tự phát lại stream đã tiêu thụ |
| **Nghiệp vụ có chịu được lặp?** | PUT có version check, POST có idempotency key được server thực thi | Có nguy cơ tạo đơn hàng/upload/billing trùng |

Ba câu hỏi phải được trả lời **độc lập**. Chẳng hạn, mã HTTP 503 có thể đủ để policy *cân nhắc* retry nhưng không chứng minh server chưa thực thi nghiệp vụ. Một `InputStream` chỉ đọc một lần có thể khiến retry thất bại trước khi request thứ hai gửi đủ body, kể cả khi nghiệp vụ tương đối an toàn.

### HTTP method không thể thay cho phân tích nghiệp vụ

- `GET` thông thường không có body và có thể retry theo policy, nhưng endpoint thực tế vẫn cần được thiết kế không gây side effect.
- `PUT` có ngữ nghĩa idempotent theo HTTP nếu server xử lý đúng; việc điều kiện hóa bằng ETag/version giúp tránh ghi đè ngoài ý muốn.
- `DELETE` theo ngữ nghĩa HTTP là idempotent, nhưng response của lần thứ hai có thể khác (ví dụ 404), và side effect như gửi sự kiện có thể cần deduplication.
- `POST` upload/tạo đơn thường **không an toàn để retry mù quáng** nếu thiếu idempotency key, transaction hoặc cơ chế nhận diện thao tác lặp.
- `PATCH` có thể không idempotent tùy dạng patch; không tự suy ra an toàn.

Tùy version và adapter, Spring Cloud LoadBalancer retry có thể mặc định giới hạn loại operation được retry. **Không bật retry cho mọi method chỉ vì body “đọc lại được”.**

## 3. Những loại body nào phát lại được?

Khả năng phát lại phụ thuộc **nguồn dữ liệu**, không chỉ phụ thuộc việc HTTP client có hỗ trợ retry.

| Nguồn body | Khả năng phát lại thông thường | Điều kiện và lưu ý |
|---|---|---|
| `String` / `byte[]` bất biến cho một operation | Thường dễ phát lại | Giữ nguyên snapshot; không sửa mảng giữa các attempt |
| DTO JSON | Có thể serialize lại | Cùng dữ liệu/version/headers; tránh DTO có trường time/random thay đổi mỗi lần |
| `FileSystemResource` | Có thể mở lại stream từ file | File tồn tại, nội dung không đổi, mỗi attempt mở stream riêng |
| `ByteArrayResource` | Có thể đọc lại bytes | Giữ bytes trong RAM; không phù hợp file rất lớn |
| `InputStream` đã mở | Thường **một lần** | Không giả định `reset()` dùng được; cần nguồn tạo stream mới |
| `InputStreamResource` bọc stream một lần | Không nên coi là replayable | Mỗi attempt có thể đọc stream đã hết hoặc bị đóng |
| Multipart form gồm chuỗi + file ổn định | Có thể tạo lại | **Mọi part** phải repeatable; kiểm tra encoder và boundary/header |
| `Flux` cold sinh dữ liệu lại theo subscription | Có thể nếu thiết kế đúng | Nguồn phải tái tạo dữ liệu; không tái sử dụng `DataBuffer` đã release |
| `Flux` hot / queue sống / socket / stdin | Không replay mặc định | Các phần tử đã phát có thể không tồn tại cho subscriber mới |
| SSE hoặc luồng sự kiện dài vô hạn | Không thể đơn giản “gửi lại nguyên luồng” | Cần offset, event ID, cursor hoặc giao thức resume |

“Có thể” trong bảng không phải bảo đảm chung của mọi HTTP transport. Một client có thể serialize trước và buffer body; client khác có thể gửi trực tiếp qua socket. Cần xét **request factory, encoder, subscription và retry implementation** thực tế.

### Replayability không đồng nghĩa dữ liệu tái tạo đúng

Một file có thể được mở lại ở attempt 2 nhưng đã bị tác vụ khác ghi đè, nên bytes không còn như attempt 1. Một DTO cũng có thể có field được sinh tự động tại thời điểm serialize. Do đó, **nội dung của một operation nên được đóng băng** bằng bản snapshot, checksum hoặc file bất biến.

## 4. Các thời điểm lỗi quyết định mức độ bất định

| Lỗi xảy ra ở đâu? | Server có thể đã nhận body? | Điều kiện retry đáng chú ý |
|---|---|---|
| Chưa chọn được `ServiceInstance` | Chưa gửi HTTP tới backend | Kiểm tra discovery/policy; body có thể chưa được tiêu thụ |
| Chưa mượn được connection từ pool | Thường chưa gửi request | Có thể thử lại sau khi giảm contention nếu policy cho phép |
| TCP connect thất bại trước khi gửi | Thường chưa gửi body | Có thể retry nếu endpoint khác hoặc điều kiện mạng thay đổi |
| Đứt kết nối giữa upload | **Có thể nhận một phần body** | Nguồn phải phát lại; server cần dọn upload dang dở |
| HTTP 503 sau khi server đã đọc đủ body | **Đã nhận body**, nhưng không biết chắc side effect | Idempotency và xác minh trạng thái xử lý rất quan trọng |
| Timeout khi đọc response | Có thể đã hoàn tất xử lý | Không suy ra operation thất bại; cân nhắc truy vấn trạng thái theo operation ID |
| Client bị cancel giữa stream | Có thể đã nhận một số chunk | Cần offset/checkpoint hoặc cơ chế hủy/resume |

**Timeout là quan sát từ client, không phải bằng chứng rollback ở server.** Một request bị timeout có thể đã được ghi vào database, lưu file hoặc tạo sự kiện.

## 5. Thực hành: tạo backend chứng minh body được gửi lại

Để quan sát rõ ràng, tạo endpoint lab nhận **đầy đủ body** rồi cố ý trả 503 cho attempt đầu tiên của cùng `X-Lab-Request-Id`. Server ghi lại SHA-256 và số lần nhận.

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class UploadReplayLabController {

    private final ConcurrentMap<String, AtomicInteger> received =
            new ConcurrentHashMap<>();

    @PostMapping(
            path = "/lab/uploads",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    ResponseEntity<String> upload(
            @RequestHeader("X-Lab-Request-Id") String requestId,
            @RequestBody byte[] body
    ) throws NoSuchAlgorithmException {

        int number = received
                .computeIfAbsent(requestId, id -> new AtomicInteger())
                .incrementAndGet();

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(body);
        String hash = HexFormat.of().formatHex(digest);
        String observation =
                "requestId=" + requestId
                + " attempt=" + number
                + " bytes=" + body.length
                + " sha256=" + hash;

        System.out.println(observation);

        if (number == 1) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(observation);
        }

        return ResponseEntity.ok(observation);
    }
}
~~~

**Đây là bộ mô phỏng, không phải thiết kế upload production.** Endpoint đọc toàn bộ body vào RAM nên chỉ dùng file nhỏ; map đếm là dữ liệu trong bộ nhớ **của một tiến trình**. Khi thử nhiều instance, mỗi instance có map riêng, vì vậy không thể dùng code này để chứng minh idempotency xuyên instance.

Kịch bản 503 ở đây xảy ra **sau khi server đã nhận và băm hết body**. Nó không mô phỏng đứt kết nối giữa upload. Nếu muốn mô phỏng lỗi giữa luồng, cần proxy/fault injection có kiểm soát và quan sát bytes/chunks đã nhận.

### Kết quả quan sát mong muốn

~~~text
requestId=lab-001 attempt=1 bytes=4096 sha256=<digest>
HTTP 503 (sau khi server nhận body)
requestId=lab-001 attempt=2 bytes=4096 sha256=<digest>
HTTP 200
~~~

Nếu SHA-256 ở hai attempt giống nhau, bài thử cho thấy **đã gửi lại cùng nội dung** đến server lab. Nó vẫn **không chứng minh thao tác upload ngoài đời an toàn khi lặp**, vì endpoint chỉ đếm và băm bytes.

## 6. RestClient: dùng nguồn có thể mở lại cho mỗi attempt

### 6.1. Cấu hình client gọi theo service ID

Đối với Spring Framework có `RestClient` (6.1+) và Spring Cloud LoadBalancer tương thích:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class UploadClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder uploadRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient mediaRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.baseUrl("http://media-service").build();
    }
}
~~~

Cần có nguồn `ServiceInstance` cho `media-service`. Với cấu hình một instance đơn giản:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            media-service:
              - uri: http://127.0.0.1:8081
    loadbalancer:
      retry:
        enabled: false
~~~

Trong lab, đặt `spring.cloud.loadbalancer.retry.enabled=false` để tránh **retry ngầm** ở tầng LoadBalancer làm nhiễu số attempt do mã thực hành điều khiển. Hành vi mặc định và cơ chế retry hỗ trợ có thể khác theo version/integration. Khi dùng HTTP client hoặc resilience middleware khác, cũng cần kiểm tra retry ở những tầng đó.

### 6.2. Mỗi attempt tạo request mới và đọc lại file

Ví dụ ứng dụng giữ một file ổn định ở `Path`. `FileSystemResource` là nguồn file có thể mở lại; mã tạo resource mới cho mỗi attempt để dễ quan sát ranh giới vòng đời:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

class ReplayableFileUploader {

    private final RestClient client;

    ReplayableFileUploader(RestClient client) {
        this.client = client;
    }

    ResponseEntity<String> upload(
            Path file, String operationId) {

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                return client.post()
                        .uri("/lab/uploads")
                        .header("X-Lab-Request-Id", operationId)
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .body(new FileSystemResource(file.toFile()))
                        .retrieve()
                        .toEntity(String.class);
            } catch (HttpServerErrorException ex) {
                boolean expected503 =
                        ex.getStatusCode().value() == 503;

                if (attempt == 2 || !expected503) {
                    throw ex;
                }
                // Chỉ lab: gửi lại cùng operationId, từ nguồn file.
            }
        }

        throw new IllegalStateException("Upload attempts exhausted");
    }
}
~~~

Đoạn code retry **tối đa một lần** cho đúng HTTP 503, nhằm thử khả năng phát lại file; nó **không phải retry policy production**. Khi triển khai thực tế cần giới hạn kích thước, tổng deadline, backoff/jitter, error classification, idempotency và cơ chế dừng đúng.

Để hai lần gửi mang cùng bytes, file phải không bị chỉnh sửa trong thời gian thử nghiệm. Nếu file có thể thay đổi, nên chuyển vào một snapshot bất biến hoặc lưu checksum/metadata mà server kiểm tra.

### 6.3. Vì sao InputStreamResource là nguồn nguy hiểm?

Ví dụ không nên dùng làm nguồn chung cho retry:

~~~java
InputStream input = Files.newInputStream(file);
InputStreamResource body = new InputStreamResource(input);

// Không được mặc định rằng "body" có thể được đọc lại
// khi một retry interceptor chạy sau lần gửi đầu tiên.
~~~

`InputStreamResource` bọc một stream đã mở và thường mang ngữ nghĩa chỉ đọc một lần. Một request factory có thể buffer dữ liệu hoặc triển khai một cách khác, nhưng việc retry có phát lại đầy đủ hay không sẽ **phụ thuộc transport và lifecycle**, không phải bảo đảm chung.

Nếu cần streaming để tiết kiệm RAM, cung cấp **hàm tạo nguồn mới** cho mỗi attempt hoặc dùng một `Resource` có thể mở lại (chẳng hạn file ổn định), thay vì chia sẻ một `InputStream` đã bị tiêu thụ.

## 7. Multipart upload: phải phát lại tất cả các part

Spring `RestClient` hỗ trợ multipart bằng `MultiValueMap<String, Object>`, mỗi part có thể là text, object, `Resource` hoặc `HttpEntity` với headers riêng.

Ví dụ dùng file nhỏ/ổn định:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

static String sendMultipart(
        RestClient client, Path file, String operationId) {

    MultiValueMap<String, Object> parts =
            new LinkedMultiValueMap<>();

    parts.add("description", "profile-photo");
    parts.add("file", new FileSystemResource(file.toFile()));

    return client.post()
            .uri("/multipart-uploads")
            .header("Idempotency-Key", operationId)
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(parts)
            .retrieve()
            .body(String.class);
}
~~~

Nếu retry, hãy **xây dựng lại multipart request và xác minh từng part có thể đọc lại**. Multipart boundary, headers hay thứ tự encode có thể khác giữa các attempt dù **nội dung logic** giống nhau; không nên mặc định toàn bộ raw bytes của multipart request sẽ giống hệt. Điều này đặc biệt quan trọng nếu body được ký bằng HMAC hoặc server dùng hash theo raw payload để deduplicate.

| Part trong multipart | Điều cần kiểm tra trước retry |
|---|---|
| Chuỗi hoặc field bất biến | Giá trị có đổi giữa attempt không? |
| File từ `FileSystemResource` | File còn tồn tại, không bị thay nội dung, stream được mở lại? |
| `ByteArrayResource` | Byte snapshot có nguyên vẹn và hợp giới hạn RAM? |
| `InputStreamResource` | Có phải stream một lần, đã bị tiêu thụ chưa? |
| Part JSON tạo từ DTO | Serializer có tính quyết định, field có ổn định? |
| Part đến từ HTTP inbound stream | Có lưu/chụp lại được hay chỉ forward một lần? |

Khi proxy một multipart request nhận từ upstream tới downstream, stream request **đến từ caller** cũng có thể chỉ đọc một lần. Không thể coi `MultipartFile` hoặc `Part` như một cơ chế tự động hỗ trợ replay vô hạn; phải xác nhận storage lifecycle hoặc lưu tạm hợp lệ.

## 8. WebClient: retry thường có nghĩa là subscribe lại

Trong mô hình reactive, `retryWhen` làm publisher nguồn **được subscribe lại** khi một lỗi phù hợp xảy ra. Điều đó chỉ phát lại body nếu **publisher cung cấp body tái tạo dữ liệu trên lần subscribe mới**.

- `Flux.defer(...)` tạo publisher mới cho mỗi subscription.
- `Mono.fromSupplier(...)` có thể tạo lại dữ liệu khi subscribe, nhưng supplier vẫn phải tạo **cùng nội dung logic**.
- `Flux` đọc từ một file ổn định có thể phát lại nếu mở file lại trên mỗi subscription.
- `Sinks.Many`/hot publisher lấy dữ liệu trực tiếp từ queue/sensor không mặc nhiên phát lại các phần đã phát.
- `DataBuffer` có reference counting không được lưu và phát lại bừa bãi khi nó đã được release.

### Ví dụ body được tạo lại từ file theo từng lần subscribe

~~~java
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

static Mono<String> uploadReactive(
        WebClient client, Path path, String operationId) {

    Flux<DataBuffer> body = Flux.defer(() ->
            DataBufferUtils.read(
                    path,
                    new DefaultDataBufferFactory(),
                    64 * 1024));

    return client.post()
            .uri("http://media-service/lab/uploads")
            .header("X-Lab-Request-Id", operationId)
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(BodyInserters.fromDataBuffers(body))
            .retrieve()
            .bodyToMono(String.class)
            .retryWhen(
                    Retry.backoff(1, Duration.ofMillis(200))
                            .filter(error ->
                                    error instanceof WebClientResponseException ex
                                    && ex.getStatusCode().value() == 503));
}
~~~

Mẫu trên giả định `WebClient` đã được tạo từ `@LoadBalanced WebClient.Builder` và đã có `media-service` trong discovery. `Retry.backoff(1, ...)` cho phép **một lần retry sau lần gửi đầu**; filter chỉ retry HTTP 503 do `retrieve()` chuyển thành `WebClientResponseException`.

Việc tạo `Flux` qua `defer` cho phép mở lại file khi resubscribe; không dùng lại các `DataBuffer` đã gửi. Spring `DataBufferUtils.read(...)` là API đọc file theo các đợt, nhưng cần kiểm tra cách quản lý bộ nhớ, hủy/cancel và backpressure thực tế theo version/connector. Không sửa file trong khi hai attempts có thể chạy.

### Không phải mọi retryWhen đều an toàn

Ví dụ nguy hiểm về ý nghĩa:

~~~java
Flux<byte[]> hotEvents = eventSource.asFlux();

return webClient.post()
        .uri("/stream")
        .body(hotEvents, byte[].class)
        .retrieve()
        .bodyToMono(Void.class)
        .retryWhen(Retry.max(1));
~~~

Nếu `eventSource` là luồng hot/`Sinks.Many`, các phần tử đã phát trong lần đầu **không tự phát lại** khi retry resubscribe. Attempt 2 có thể bắt đầu từ phần dữ liệu mới hoặc nhận luồng không đầy đủ. Cần thiết kế cơ chế snapshot/log/offset hoặc **không retry ở tầng HTTP**.

### Timeout và retry đặt ở đâu?

~~~java
Mono<String> oneOperationBudget =
        uploadReactive(webClient, file, operationId)
                .timeout(Duration.ofSeconds(5));
~~~

`timeout` bên ngoài chuỗi có thể giới hạn tổng thời gian operation, gồm cả retry/backoff. Nếu đặt timeout **bên trong** publisher được retry, mỗi attempt có thể được cấp lại toàn bộ thời gian chờ. Thời điểm cancel ở client không chứng minh rằng server đã hủy công việc.

## 9. OpenFeign: không nhầm Feign Retryer với khả năng replay

Spring Cloud OpenFeign mặc định tạo bean `Retryer.NEVER_RETRY` để **tắt retry của Feign**, khác với Feign thuần vốn có thể retry một số I/O error. Retry ở Spring Cloud LoadBalancer, transport hoặc tầng application nếu được bật có quy tắc riêng.

Một interface upload body nhỏ có thể khai báo:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "media-service")
interface MediaFeignClient {

    @PostMapping(
            path = "/lab/uploads",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    String upload(
            @RequestHeader("X-Lab-Request-Id") String operationId,
            @RequestBody byte[] payload);
}
~~~

Với `byte[]` nhỏ đã được giữ cố định, ứng dụng có một nguồn byte dễ tái sử dụng hơn nguồn stream chỉ đọc một lần. Nhưng muốn retry HTTP 503 cần **policy tường minh** phù hợp với Spring Cloud OpenFeign, hoặc một tầng gọi bao ngoài có giới hạn. Đừng giả định Feign sẽ tự retry chỉ vì interface sử dụng `@FeignClient`.

Đối với file lớn, dùng `byte[]` khiến cả file được giữ trong RAM. Một số Feign encoder/transport có thể buffer request body khi encode, trong khi một số cách streaming lại không có khả năng phát lại. Vì vậy, **mẫu upload multipart/streaming của OpenFeign phải được kiểm thử trên encoder, Feign Client và retry policy thực tế**; không khẳng định mọi `MultipartFile`, `Resource` hoặc `InputStream` đều replayable.

Nếu Feign sử dụng LoadBalancer, việc chọn lại service instance khi retry **không bảo đảm body cũng được encode/đọc lại đúng**. Hai vấn đề thuộc hai tầng khác nhau.

## 10. Streaming và upload lớn: vì sao retry nguyên request thường là sai?

Với file 20 KB, retry từ đầu có thể chấp nhận được trong lab. Với video 4 GB đã gửi được 3,8 GB rồi đứt kết nối, retry nguyên POST có thể:

- Gửi lại lượng dữ liệu rất lớn, tăng băng thông và chi phí.
- Làm client và backend giữ socket/thread/buffer lâu hơn.
- Tạo nhiều file tạm hoặc upload session bị bỏ dở.
- Gây lặp dữ liệu nếu server đã commit phần trước hoặc toàn bộ file.
- Làm vượt thời gian chờ nghiệp vụ và kích hoạt thêm retry chồng nhau.

Với một luồng dữ liệu **không có điểm kết thúc** (sensor events, live audio/video, SSE hoặc sự kiện log), “phát lại toàn bộ body” thường không phải yêu cầu hợp lý. Cần xác định **event nào được xác nhận, event nào chưa**, rồi tiếp tục từ cursor hoặc sequence number.

### Thiết kế upload tiếp tục từ checkpoint

Một giao thức upload có thể chia thành:

~~~mermaid
flowchart TD
    A["Tạo upload session và uploadId"]
    B["Chia file thành các phần: part 1, 2, 3..."]
    C["Gửi part k với checksum và offset"]
    D{"Server xác nhận đã lưu part k?"}
    E["Đánh dấu part k hoàn tất"]
    F["Truy vấn trạng thái upload / kiểm tra checksum"]
    G["Gửi lại chỉ part chưa được xác nhận"]
    H["Complete upload bằng operationId cố định"]
    I["Server commit đúng một lần"]
    A --> B --> C --> D
    D -->|"Có"| E --> H
    D -->|"Không / timeout"| F --> G --> C
    H --> I
~~~

Ví dụ hợp đồng HTTP minh họa (không phải endpoint có sẵn trong Spring Cloud):

~~~http
POST /uploads
Idempotency-Key: operation-123

HTTP/1.1 201 Created
Location: /uploads/upload-789

PUT /uploads/upload-789/parts/4
Content-Range: bytes 3145728-4194303/8388608
X-Content-SHA256: <sha256-of-part>

GET /uploads/upload-789/status

POST /uploads/upload-789/complete
Idempotency-Key: operation-123
~~~

Các trường `uploadId`, part number, offset, checksum và operation ID cho phép server nhận diện phần đã lưu. Server phải bảo đảm tính nhất quán của việc ghi từng part, từ chối checksum sai, tránh ghi đè không hợp lệ và chỉ commit kết quả cuối một lần.

Giải pháp thực tế có thể dùng multipart upload của object storage, giao thức resumable upload hoặc API riêng có upload sessions. Không nên tự tạo cơ chế resume phức tạp nếu hạ tầng lưu trữ đã cung cấp giao thức chuẩn và SDK phù hợp.

## 11. Idempotency-Key: gửi cùng body vẫn chưa đủ

Idempotency key **không tự tạo ra tính lũy đẳng** chỉ vì client thêm một header. Backend phải thực thi:

1. Lưu key theo phạm vi phù hợp (client/tenant/operation), và gắn với checksum hoặc thông tin định danh payload.
2. Dùng transaction/unique constraint hoặc cơ chế atomic để một key không tạo hai side effects khi request đến đồng thời.
3. Ghi kết quả hoặc trạng thái xử lý đủ bền để client retry trên instance khác có thể truy vấn/nhận lại.
4. Nếu cùng key nhưng payload khác, từ chối có kiểm soát thay vì âm thầm dùng kết quả cũ.
5. Định nghĩa TTL/retention, xử lý request đang chạy, rollback và cách client khôi phục sau timeout.

**Ví dụ:** attempt đầu đến `media-1` đã commit file rồi response bị mất; attempt hai đến `media-2`. Chỉ khi hai instance dùng chung kho trạng thái idempotency và storage hợp lệ thì lần hai mới có thể trả lại kết quả của lần một mà không tạo file thứ hai.

Trong bài lab ở mục 5, `X-Lab-Request-Id` chỉ là khóa đếm để quan sát. Nó **không phải** cài đặt idempotency thực tế.

## 12. Chi phí và giới hạn bộ nhớ khi muốn replay

| Chiến lược | Bộ nhớ | Khả năng retry | Đánh đổi |
|---|---|---|---|
| Buffer `byte[]` trong RAM | Tỷ lệ với kích thước body | Dễ tái phát nếu giữ snapshot | OOM/GC khi nhiều upload lớn |
| Lưu vào file tạm rồi gửi | Ít RAM hơn, tiêu thụ disk | Có thể mở file lại | I/O đĩa, dọn file, mã hóa và quota |
| Đọc file ổn định trực tiếp mỗi attempt | RAM thấp, disk/network lặp lại | Có nếu file không đổi | Có thể tốn thời gian gửi lại toàn bộ |
| Cold publisher tạo lại dữ liệu | Phụ thuộc nguồn | Có nếu nguồn tái tạo được | Kiểm soát cancellation/backpressure khó hơn |
| Hot publisher/socket stream | Thường không lưu lịch sử | Không replay tự nhiên | Cần offset/log/resume |
| Chunked/resumable upload | Buffer từng phần | Retry từng phần đã xác định | Server và protocol phức tạp hơn |

Không tự tăng giới hạn `maxInMemorySize` của WebClient để “giải quyết retry upload”. Cấu hình này thường liên quan bộ nhớ dùng cho codec/aggregation; không biến một hot stream thành body phát lại được. Nếu chọn buffer RAM, phải tính cả concurrency: 100 request, mỗi request 50 MB có thể tạo áp lực nhiều GB chưa kể overhead.

Tập tin tạm có thể chứa dữ liệu nhạy cảm; cần quyền truy cập, mã hóa theo yêu cầu, giới hạn dung lượng và cơ chế xóa khi operation kết thúc hoặc hết hạn.

## 13. Checklist retry với Spring Cloud LoadBalancer

Spring Cloud LoadBalancer hỗ trợ retry ở các integration tương thích khi được bật và đủ dependency, nhưng việc **chọn instance** là phần riêng với **phát lại request body**.

Trước khi bật retry cho upload:

- **Nguồn body:** Mỗi attempt có thể tạo lại nội dung từ đầu hay đang dùng stream một lần?
- **Điều kiện retry:** Chỉ retry lỗi tạm thời đã phân loại, không retry mọi 4xx/5xx?
- **Method:** Có cho phép retry `POST`/`PATCH` không; server có hỗ trợ idempotency thực sự?
- **Chọn instance:** Retry giữ instance cũ hay chọn bản sao khác? Các bản sao có chia sẻ state/storage không?
- **Timeout/deadline:** Tổng attempts, backoff và số byte lặp lại có trong budget?
- **Body size:** Có cần buffer ra RAM/disk hay nên chunk/resume?
- **Các tầng retry:** Feign, HTTP transport, LoadBalancer và resilience layer có bị bật đồng thời?
- **Resource lifecycle:** Stream/file/`DataBuffer` được mở và đóng đúng theo mỗi attempt?
- **Quan sát:** Log được attempt number, operation ID, body size/hash và kết quả commit mà không lộ nội dung nhạy cảm?
- **Hủy bỏ:** Khi client cancel/timed out, backend có đang tiếp tục ghi dữ liệu không?

Không dùng `spring.cloud.loadbalancer.retry.retryOnAllOperations=true` như một cách bật nhanh retry upload mà chưa kiểm tra idempotency, nguồn body và integration cụ thể.

### Phân biệt “server không có instance” với “body không replay được”

Nếu LoadBalancer không tìm thấy server cho `media-service`, lỗi xuất hiện trước khi gửi HTTP tới backend. Nếu chọn được instance nhưng attempt 2 không có dữ liệu hoặc bị lỗi `stream closed`, nguyên nhân nằm ở nguồn body/encoder/lifecycle. Nếu body được gửi lại đầy đủ mà server xuất hiện hai bản ghi, lỗi là **idempotency nghiệp vụ**, không phải lỗi chọn instance.

## 14. Bài thực hành kiểm chứng hai yếu tố độc lập

Chạy backend ở cổng `8081`, dùng `SimpleDiscoveryClient` một instance như mục 6, rồi tạo một file 4 KB có nội dung không đổi.

| Thí nghiệm | Body | Cơ chế lỗi | Điều cần kiểm chứng |
|---|---|---|---|
| A | `byte[]` hoặc `FileSystemResource` | Server trả 503 ở attempt 1 sau khi đọc body | Attempt 2 gửi lại đủ bytes, SHA-256 như lần đầu |
| B | `InputStreamResource` từ stream đã mở | Bật retry và yêu cầu đọc lại | Không giả định attempt 2 có body; ghi nhận lỗi hoặc body thiếu |
| C | Multipart text + file | Trả 503 sau khi đọc request | Mọi part có thể tạo lại, nội dung logic giống nhau |
| D | `Flux.defer` đọc file | Server trả 503 | Có subscriber mới; file được đọc lại đúng |
| E | Hot Flux | Server trả 503/cancel | Các event đã phát không tự xuất hiện lại |
| F | File lớn chia part | Mất kết nối sau khi đã xác nhận vài part | Chỉ retry part chưa được xác nhận, không gửi lại toàn file |
| G | Body repeatable, không có dedup server | Trả 503 sau side effect | Có thể tạo trùng nghiệp vụ dù SHA-256 hai lần giống nhau |

Với mỗi lần thử, ghi nhận:

~~~text
operationId=operation-123
attempt=1
serviceId=media-service
instanceId=media-1
bodyBytes=4096
bodySha256=<digest>
result=HTTP_503
serverReceived=true
serverCommitted=<unknown|true|false>

operationId=operation-123
attempt=2
instanceId=media-1
bodyBytes=4096
bodySha256=<same digest>
result=HTTP_200
~~~

Đây là **định dạng log gợi ý**, không phải trường mặc định của Spring Cloud LoadBalancer. `serverCommitted` phải dựa vào ghi nhận trạng thái thực tế ở backend chứ không tự suy ra từ HTTP status.

### Tiêu chí hoàn thành bài thực hành

1. Biết phân biệt một body **có thể tái tạo** với một nguồn stream **chỉ đọc được một lần**.
2. Chứng minh được hai attempt gửi cùng nội dung bằng bytes/hash và log server, không chỉ bằng “retry đã chạy”.
3. Giải thích vì sao 503 hoặc read timeout không chứng minh server chưa xử lý.
4. Chỉ ra tác dụng của retry trên cùng instance hoặc instance khác trong Spring Cloud LoadBalancer.
5. Đề xuất được cách tránh ghi trùng cho POST upload bằng idempotency key thực thi ở server.
6. Với upload lớn/streaming, đề xuất được chunk/offset/checkpoint thay vì retry vô hạn nguyên request.

## 15. Nguyên tắc thiết kế nên nhớ

- **Replayable ≠ idempotent.** Có thể gửi lại cùng bytes không có nghĩa nghiệp vụ an toàn khi nhận lại bytes đó.
- **Retry phải có điều kiện.** Chỉ thử lại những lỗi phù hợp, giới hạn số attempts/backoff và tổng deadline.
- **Không tái sử dụng body stream đã tiêu thụ.** Đối với file, mở lại mỗi lần; đối với publisher, tạo dữ liệu mới khi subscribe.
- **Không dùng HTTP status để khẳng định rollback.** Server có thể đã commit trước khi phản hồi bị mất.
- **Không mặc định multipart/Feign streaming replayable.** Phải thử với encoder, request factory và transport cụ thể.
- **Không nhầm LB retry với replay body.** LoadBalancer chọn instance; HTTP client/encoder và nguồn dữ liệu quyết định có phát lại được request.
- **Upload lớn nên hỗ trợ resume.** Chunk ID, offset, checksum và trạng thái upload giúp giảm dữ liệu gửi lại.
- **Idempotency cần backend thực thi.** Key phải ổn định xuyên attempts và được kiểm soát đồng thời, dữ liệu và kết quả.
- **Quan sát từng attempt.** Đo attempt, instance, bytes/hash, nguyên nhân lỗi và kết quả commit mà không ghi dữ liệu nhạy cảm.

**Kết luận:** Trong Spring Cloud LoadBalancer, việc retry có thể chọn lại một `ServiceInstance` nhưng **không thể tự hồi sinh một `InputStream` đã hết, một hot `Flux` đã phát sự kiện hay một request body chỉ tồn tại trong RAM/socket tạm thời**. Với `RestClient`, `WebClient` và OpenFeign, cần thiết kế nguồn body phát lại được, chính sách retry có giới hạn và idempotency ở server. Với upload hoặc streaming lớn, giải pháp đáng tin cậy thường là **giao thức resumable**, không phải gửi lại nguyên request một cách mù quáng.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Retrying Failed Requests](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients, request body và multipart](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – WebClient Request Body](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
- [Spring Cloud OpenFeign – Retryer và Feign client configuration](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Project Reactor – Retry và resubscription](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)

