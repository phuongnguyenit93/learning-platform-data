# Phân biệt client đồng bộ, bất đồng bộ và mô hình reactive

Khi một Spring Boot service gọi object storage, gửi thông điệp hoặc truy vấn cơ sở dữ liệu managed, ứng dụng phải quyết định **cách chờ kết quả I/O**. Có thể gọi SDK theo kiểu **đồng bộ (synchronous/blocking)**, sử dụng client **bất đồng bộ (asynchronous)** trả về future/callback, hoặc tổ chức một luồng xử lý **reactive** bằng `Mono`, `Flux` và các thành phần hỗ trợ Reactive Streams. Ba cách có thể dùng cùng một dịch vụ cloud nhưng khác nhau đáng kể về cách sử dụng thread, thời điểm bắt đầu thao tác, xử lý lỗi, giới hạn tải và kiểm thử.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Phạm vi mô-đun là thực hành tích hợp Spring Boot với dịch vụ managed của **AWS, Azure và Google Cloud** thông qua các thư viện Spring Cloud tương ứng, từ danh tính và quyền đến storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh provider. Trọng tâm ở đây là lựa chọn mô hình thực thi phù hợp cho lời gọi từ nghiệp vụ qua Spring/SDK tới cloud, đồng thời giữ đúng những bảo đảm của từng provider.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời lời gọi cloud theo kiểu blocking, `CompletableFuture` và Reactor, từ request tới response hoặc lỗi.
- Giải thích sự khác nhau giữa **bất đồng bộ**, **không chặn thread**, **reactive**, **streaming** và **xử lý song song**.
- Sử dụng đúng `S3Client` và `S3AsyncClient` của AWS SDK for Java v2 trong ví dụ; hiểu cách đối chiếu với client Azure và Google Cloud.
- Tích hợp `CompletableFuture` vào `Mono` mà không kích hoạt tác vụ quá sớm hoặc block event loop.
- Chọn mô hình cho REST API, upload lớn, hàng đợi thông điệp, database managed và truy cập secret.
- Thiết kế timeout, retry, idempotency, observability và kiểm thử phù hợp với mô hình thực thi.

## 2. Đồng bộ, bất đồng bộ, reactive: các khái niệm khác nhau

| Đặc điểm | Client đồng bộ | Client bất đồng bộ | Pipeline reactive |
| --- | --- | --- | --- |
| API trả về thường gặp | Kết quả trực tiếp hoặc ném exception | `CompletableFuture<T>`, `CompletionStage<T>`, callback hoặc future khác | `Mono<T>`, `Flux<T>` / `Publisher<T>` |
| Thread gọi phương thức | Thường chờ I/O hoàn tất | Thường được trả về trước khi I/O hoàn tất | Theo scheduler/operator; có thể không chặn nếu nguồn bên dưới hỗ trợ |
| Bắt đầu tác vụ | Trong lúc gọi phương thức | Nhiều SDK **bắt đầu ngay khi gọi** phương thức async | Publisher có thể **lazy**, thường bắt đầu khi có subscriber; phụ thuộc nguồn |
| Nhận kết quả | Lệnh kế tiếp sau lời gọi hoặc `catch` | Callback/continuation/completion | Tín hiệu `onNext`, `onComplete`, `onError` |
| Xử lý nhiều kết quả | Iterator/stream tùy API | Future một kết quả hoặc callback/stream API riêng | `Flux` hỗ trợ 0..N tín hiệu dữ liệu |
| Backpressure theo Reactive Streams | Không có mặc định | Không có chỉ vì API trả future | Có cơ chế demand giữa các thành phần compliant; mức tác động đến SDK/network tùy adapter |
| Phù hợp thường gặp | Use case đơn giản, JDBC, batch ít đồng thời | Nhiều lời gọi I/O độc lập, cần giải phóng thread gọi | Pipeline WebFlux/R2DBC, streaming hoặc xử lý dữ liệu có điều tiết |

**Synchronous không đồng nghĩa xử lý tuần tự toàn hệ thống**: nhiều request vẫn có thể chạy đồng thời trên nhiều thread. **Asynchronous không đồng nghĩa tự động song song**: future biểu diễn hoàn thành về sau; việc bao nhiêu tác vụ chạy đồng thời phụ thuộc executor, connection pool và SDK. **Reactive không đồng nghĩa SDK đã trở thành non-blocking**: `Mono` bọc một lời gọi JDBC/S3 blocking vẫn chứa thao tác chặn nếu không được cô lập lên scheduler thích hợp.

Ngoài ra, `Future` thường biểu diễn **một kết quả cuối**. Một `Flux` biểu diễn **chuỗi tín hiệu** với subscription, demand và cancellation. Không thể kết luận client hỗ trợ streaming tải tệp chỉ vì nó có một phương thức `putObjectAsync`; upload thật sự theo dòng byte là yêu cầu riêng.

## 3. Hình dung đường đi của ba mô hình

Giả sử HTTP handler cần lưu tài liệu lên object storage:

~~~mermaid
flowchart TD
    R[HTTP handler / application service] --> M{Kiểu gọi I/O}
    M -->|Đồng bộ| S[S3Client.putObject]
    S --> W[Thread chờ response]
    W --> X[Trả kết quả / throw exception]
    M -->|Bất đồng bộ| A[S3AsyncClient.putObject]
    A --> F[CompletableFuture]
    F --> C[Completion callback]
    M -->|Reactive| P[Mono hoặc Flux]
    P --> SUB[Subscribe và demand]
    SUB --> N[Non-blocking SDK / reactive driver]
    N --> SIG[onNext / onComplete / onError]
    S --> CLOUD[Managed cloud service]
    A --> CLOUD
    N --> CLOUD
~~~

Ở nhánh **reactive**, lớp `Mono`/ `Flux` là mô hình phối hợp tín hiệu; bên dưới cần sử dụng **async SDK** hoặc **reactive driver** nếu mục tiêu là non-blocking thực sự. Một publisher có thể được tạo mà chưa gọi network. Nhưng nếu future được tạo **trước** publisher, network đã có thể bắt đầu trước khi ai đó subscribe.

### 3.1. Dòng thời gian đơn giản

~~~text
Sync:
thread A: validate -> call SDK ===================> response -> continue
                       (chờ I/O)

Async future:
thread A: validate -> call async SDK -> return future -> continue
                                  ... I/O ...
SDK/executor:                              complete future -> continuation

Reactive với nguồn lazy:
thread A: tạo Mono -> trả Mono
subscriber: subscribe -> khởi động async I/O -> nhận signals -> hoàn tất
~~~

Đây là hình minh họa luồng khái niệm. Thread thực tế của SDK và operator tùy implementation; `CompletableFuture.thenApply` đôi khi chạy trên thread hoàn thành future, còn `thenApplyAsync` dùng executor chung hoặc executor chỉ định.

## 4. Client đồng bộ: dễ theo dõi, thread có thể bị giữ

Với **AWS SDK for Java v2**, `S3Client` cung cấp API đồng bộ. Ví dụ sau giả định Spring Cloud AWS starter đã cấu hình bean `S3Client`, bucket do môi trường cung cấp và workload có quyền `s3:PutObject` tương ứng:

~~~java
// S3BlockingStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3BlockingStorage {
    private final S3Client s3;
    private final String bucket;

    public S3BlockingStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void put(String key, byte[] bytes) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build();

        s3.putObject(request, RequestBody.fromBytes(bytes));
        // Chỉ chạy tới đây sau khi SDK trả về thành công.
    }
}
~~~

Luồng `controller → service → S3BlockingStorage.put → S3Client.putObject → HTTPS → S3` dễ đọc, dễ debug và thích hợp khi mức đồng thời vừa phải. SDK có thể quản lý connection pool, timeout và retry theo cấu hình của nó; **blocking** chỉ mô tả việc thread gọi phải đợi cho tới khi lời gọi hoàn tất.

Nếu dùng **Spring MVC**, request thường được xử lý bởi một thread thuộc servlet container. Thread này sẽ chờ khi service gọi S3 đồng bộ. Với nhiều request I/O dài, giới hạn thread, pool connection và timeout có thể trở thành nút thắt. Java virtual threads có thể giảm chi phí giữ platform thread trong một số ứng dụng blocking, nhưng **không biến SDK synchronous thành reactive**, cũng không xóa giới hạn kết nối, quota hoặc băng thông.

### 4.1. Lỗi trong lời gọi đồng bộ

~~~java
try {
    blockingStorage.put(key, data);
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    // Dịch mã lỗi S3 thành lỗi phù hợp với nghiệp vụ.
    throw ex;
} catch (software.amazon.awssdk.core.exception.SdkClientException ex) {
    // Có thể là lỗi phía client/transport/credential.
    throw ex;
}
~~~

Ví dụ chỉ phân biệt nơi phát sinh lỗi, chưa phải chiến lược exception handling production. Lỗi `403` cần kiểm tra identity/IAM/bucket policy, không nên retry mù quáng; timeout, `429`, throttling và lỗi tạm thời mới có thể phù hợp với retry có giới hạn. Cần tránh ghi access key, token và nội dung tài liệu vào log.

## 5. Client bất đồng bộ: future biểu diễn kết quả về sau

`S3AsyncClient` của AWS SDK v2 trả về `CompletableFuture` cho các thao tác tương ứng. Ví dụ sử dụng `AsyncRequestBody.fromBytes` để giữ minh họa ngắn; cách này vẫn **đưa toàn bộ payload vào bộ nhớ**, dù I/O được thực hiện bất đồng bộ.

~~~java
// AsyncDocumentStorage.java
import java.util.concurrent.CompletableFuture;

public interface AsyncDocumentStorage {
    CompletableFuture<Void> put(String key, byte[] bytes);
}
~~~

~~~java
// S3AsyncDocumentStorage.java
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3AsyncDocumentStorage implements AsyncDocumentStorage {
    private final S3AsyncClient s3;
    private final String bucket;

    public S3AsyncDocumentStorage(
            S3AsyncClient s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public CompletableFuture<Void> put(String key, byte[] bytes) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build();

        return s3.putObject(request, AsyncRequestBody.fromBytes(bytes))
            .thenAccept(response -> {
                // SDK đã nhận phản hồi thành công; không có xử lý blocking.
            });
    }
}
~~~

**Lưu ý về Spring:** Bean `S3AsyncClient` phải thực sự tồn tại. Tùy phiên bản/configuration, starter có thể auto-configure bean async hoặc phải tự khai báo một bean riêng. Không suy ra rằng có `S3Client` nghĩa là luôn có `S3AsyncClient`. Hãy kiểm tra conditional auto-configuration, danh sách bean và BOM của Spring Cloud AWS đang dùng.

Service có thể trả future ra ngoài, không `join()` hay `get()` trong luồng request:

~~~java
// AsyncDocumentService.java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

public class AsyncDocumentService {
    private final AsyncDocumentStorage storage;

    public AsyncDocumentService(AsyncDocumentStorage storage) {
        this.storage = storage;
    }

    public CompletableFuture<String> save(byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            return CompletableFuture.failedFuture(
                new IllegalArgumentException("Document is empty"));
        }

        String key = "documents/" + UUID.randomUUID();
        return storage.put(key, bytes).thenApply(ignored -> key);
    }
}
~~~

**Thời điểm bắt đầu:** `storage.put(...)` đã được gọi khi `save(...)` trả về future; việc lưu có thể đang chạy. `thenApply` chỉ diễn ra khi future đầu tiên thành công. Nếu thất bại, future được complete exceptionally; lời gọi `save()` không nhất thiết ném exception ngay tại dòng đó.

**Không nên** gọi `future.join()` trong Spring WebFlux event loop vì đã biến luồng gọi thành blocking. Đối với Spring MVC, ứng dụng có thể tích hợp kết quả future bằng kiểu xử lý request async được framework hỗ trợ; dùng mô hình phù hợp với controller và stack hiện tại.

### 5.1. Callback, continuation và executor

~~~java
storage.put(key, bytes)
    .whenComplete((ignored, error) -> {
        if (error != null) {
            // Ghi nhận lỗi và hoàn thành workflow theo chính sách.
        } else {
            // Ghi nhận thành công.
        }
    });
~~~

Callback nên **nhanh, không block** vì có thể chạy trên thread hoàn thành tác vụ. Nếu cần xử lý CPU lớn hoặc thao tác blocking, chuyển sang executor được quản lý và giới hạn thích hợp. Việc dùng `thenApplyAsync` có thể chuyển continuation sang executor nhưng **không làm lời gọi network ban đầu nhanh hơn**.

Khi tiếp tục hai thao tác độc lập, có thể kết hợp future bằng `thenCombine` hoặc `allOf`, nhưng phải giới hạn số request đồng thời. Khởi tạo hàng chục nghìn future cùng lúc có thể làm đầy connection pool, tiêu tốn bộ nhớ hoặc chạm quota cloud. API async không tự cung cấp cơ chế backpressure theo Reactive Streams.

## 6. Reactive: phối hợp dữ liệu, tín hiệu và demand

Trong hệ sinh thái Spring, mô hình reactive thường dùng **Project Reactor**: `Mono<T>` phát tối đa một giá trị, còn `Flux<T>` phát nhiều giá trị. Spring WebFlux, Spring Data R2DBC và một số client/reactive integration có thể xây dựng các pipeline non-blocking nếu các nguồn I/O bên dưới thực sự hỗ trợ.

Một `Mono` thường là mô tả công việc: nó được **subscribe** bởi thành phần tiêu thụ, ví dụ Spring WebFlux. Publisher có thể phát `onNext`, `onComplete` hoặc `onError`. Reactive Streams thêm cơ chế **demand** để subscriber thông báo muốn nhận bao nhiêu phần tử. Tuy nhiên, một `Mono` chỉ bọc future thường không mang lại lợi ích streaming/backpressure đáng kể cho **một response đơn lẻ**.

### 6.1. Bọc async SDK vào Mono đúng thời điểm

Giả sử dùng `AsyncDocumentStorage` ở phần 5:

~~~java
// ReactiveDocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDocumentService {
    private final AsyncDocumentStorage storage;

    public ReactiveDocumentService(AsyncDocumentStorage storage) {
        this.storage = storage;
    }

    public Mono<String> save(byte[] bytes) {
        return Mono.defer(() -> {
            if (bytes == null || bytes.length == 0) {
                return Mono.error(
                    new IllegalArgumentException("Document is empty"));
            }

            String key = "documents/" + UUID.randomUUID();
            return Mono.fromFuture(storage.put(key, bytes))
                .thenReturn(key);
        });
    }
}
~~~

`Mono.defer` trì hoãn cả việc tạo key lẫn gọi SDK cho tới khi có **subscription**; mỗi subscription tạo một key mới và có thể gây **một lần ghi object mới**. Cần lưu ý nếu dùng `retry`, `repeat` hoặc subscribe nhiều lần: các operator đó có thể làm thao tác ghi lặp lại. Nếu business yêu cầu idempotency, key và định danh request phải được quản lý ngoài phép gọi ngẫu nhiên cho từng lần thử, hoặc thiết kế sao cho các lần thử cùng dùng một định danh nghiệp vụ.

Ngược lại, code sau có thể kích hoạt I/O **quá sớm**:

~~~java
// Không phù hợp nếu muốn request chỉ bắt đầu khi subscribe:
var future = storage.put(key, bytes); // SDK async có thể chạy ngay.
Mono<Void> publisher = Mono.fromFuture(future);
~~~

`Mono.fromFuture(future)` biểu diễn tín hiệu của future đã tạo, không tự làm tương lai đã bắt đầu trở thành lazy. Với các API có supplier/lazy adapter, vẫn cần xác minh thời điểm gọi thực tế theo phiên bản Reactor và SDK đang sử dụng.

### 6.2. Spring WebFlux controller

~~~java
// DocumentController.java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final ReactiveDocumentService documents;

    public DocumentController(ReactiveDocumentService documents) {
        this.documents = documents;
    }

    @PostMapping(consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ResponseEntity<Map<String, String>>> upload(
            @RequestBody Mono<byte[]> body) {
        return body.flatMap(documents::save)
            .map(key -> ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("key", key)));
    }
}
~~~

Spring WebFlux subscribe/điều phối publisher trong quá trình xử lý response. **Không gọi `subscribe()` bên trong controller hoặc service** chỉ để “chạy” pipeline rồi trả `200`: như vậy dễ tạo tác vụ không được theo dõi, mất xử lý lỗi và trả response trước khi thao tác lưu hoàn tất.

Mẫu `Mono<byte[]>` chỉ để minh họa luồng một payload. Với tệp lớn, nên dùng `Flux<DataBuffer>`, upload streaming được hỗ trợ hoặc direct-to-cloud upload có quyền giới hạn; đọc toàn bộ body vào `byte[]` có thể làm cạn bộ nhớ, dù API bên ngoài là reactive. Chuyển đổi `DataBuffer` sang request body của cloud SDK phải tuân theo hợp đồng streaming, buffer lifecycle và giới hạn bộ nhớ; không mặc nhiên coi hai publisher có thể nối trực tiếp mà không cần adapter.

## 7. Bọc SDK blocking trong Mono: khi nào có thể chấp nhận?

Đôi khi dự án dùng Spring WebFlux nhưng dịch vụ hoặc SDK chỉ có API đồng bộ. Nếu phải giữ SDK blocking, cần **cô lập I/O** khỏi event loop bằng scheduler được quản lý:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<String> saveWithBlockingClient(
        S3BlockingStorage storage, String key, byte[] bytes) {
    return Mono.fromCallable(() -> {
            storage.put(key, bytes);
            return key;
        })
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` trì hoãn lời gọi tới lúc subscribe; `subscribeOn(boundedElastic())` giúp chạy tác vụ blocking trên pool phù hợp hơn event loop. Tuy vậy, **SDK vẫn blocking**; thread và hàng đợi của scheduler cũng có giới hạn. Đây là giải pháp tích hợp thực dụng cho một phần blocking có kiểm soát, **không tạo ra non-blocking I/O** và không thay thế việc đo tải thực tế.

Sai lầm phổ biến:

~~~java
// KHÔNG làm điều này trên event loop của WebFlux:
Mono<String> result = Mono.just(blockingOperation());
// blockingOperation() chạy ngay khi tạo Mono.
~~~

Nếu toàn bộ đường đi sử dụng JDBC, SDK sync và xử lý request kiểu blocking, **Spring MVC** có thể đơn giản và dễ vận hành hơn một ứng dụng WebFlux phải chuyển mọi lời gọi sang `boundedElastic`. Chọn stack theo tính chất tải, nhu cầu streaming và khả năng hỗ trợ non-blocking của dependency, không theo tên framework.

## 8. So sánh hỗ trợ của AWS, Azure và Google Cloud

Không có một API “`CloudAsyncClient`” dùng chung cho cả ba provider. Các thư viện Spring Cloud thường giúp cấu hình bean, template hoặc listener, nhưng **hình thức trả kết quả phụ thuộc SDK và dịch vụ cụ thể**.

| Provider / dịch vụ | API đồng bộ tiêu biểu | API bất đồng bộ / reactive tiêu biểu | Điều cần nhớ |
| --- | --- | --- | --- |
| **AWS S3** | AWS SDK v2 `S3Client` | `S3AsyncClient` trả `CompletableFuture`; body async theo API SDK | `AsyncRequestBody.fromBytes` vẫn giữ payload trong bộ nhớ; streaming cần API phù hợp |
| **AWS SQS** | `SqsClient` | `SqsAsyncClient`; Spring Cloud AWS SQS template/listener theo phiên bản | Queue consumer có poll/ack/visibility; listener không mặc nhiên là pipeline Reactive Streams |
| **Azure Blob Storage** | `BlobClient`, `BlobServiceClient` | `BlobAsyncClient`, `BlobServiceAsyncClient`; nhiều Azure SDK async API trả `Mono`/`Flux` | Phải xác minh luồng đọc/ghi và cấu hình auth/transport khi dùng starter |
| **Azure Service Bus** | Client sender/receiver sync nếu API phiên bản cung cấp | Các client async/processors/callback theo Azure SDK | Complete/abandon/dead-letter, lock và session ảnh hưởng kết quả |
| **Google Cloud Storage** | `Storage` trong Java client thường cung cấp lời gọi blocking | Một số chức năng/phiên bản có API bất đồng bộ hoặc streaming riêng; kiểm tra đúng client/version | Không suy ra mọi lời gọi GCS đều trả future hay Reactor publisher |
| **Google Cloud Pub/Sub** | SDK/abstraction có thao tác tương ứng | Java Publisher thường trả `ApiFuture`; Subscriber dùng callback | `ApiFuture` khác `CompletableFuture` và khác `Mono`; cần adapter nếu tích hợp |
| **Managed PostgreSQL** trên cả ba cloud | JDBC / Spring Data JPA | R2DBC với driver hỗ trợ nếu cần reactive | Cloud hosting không tự biến JDBC thành non-blocking |

Trong Spring Cloud Azure, một số async SDK **đã dùng Reactor** ở API client. Trong Spring Cloud AWS, nhiều SDK async dùng **`CompletableFuture`**. Với Google Cloud Java libraries, `ApiFuture` và API dựa trên callback cũng phổ biến. Do đó, lựa chọn reactive ở **Spring layer** không bảo đảm tất cả adapter theo từng cloud đều có cùng hành vi về cancellation, demand, streaming hay retry.

Nếu triển khai cùng một nghiệp vụ trên nhiều cloud, định nghĩa hợp đồng ổn định (ví dụ `CompletionStage<StorageResult>` hoặc `Mono<StorageResult>`) ở application boundary; trong **provider adapter**, chuyển kết quả SDK sang hợp đồng đó và ghi rõ những tính năng provider-specific cần giữ lại. Không nên ép API SDK blocking vào một `Mono` rồi tuyên bố hệ thống đã non-blocking toàn trình.

## 9. Chọn mô hình nào cho từng tình huống?

| Tình huống | Lựa chọn nên đánh giá đầu tiên | Lý do / giới hạn |
| --- | --- | --- |
| REST API Spring MVC, tải vừa phải, một lệnh lưu nhỏ | Sync SDK với timeout rõ ràng | Mã dễ đọc, chi phí phối hợp thấp; đo số thread chờ và kết nối |
| HTTP endpoint có nhiều I/O độc lập, độ đồng thời cao | Async SDK hoặc WebFlux + async SDK | Không giữ thread request suốt I/O; cần kiểm soát số request đang chạy |
| WebFlux đọc/ghi dữ liệu theo dòng | Reactive/async driver hỗ trợ streaming thật | Tránh buffer toàn bộ payload; xem demand ở mọi ranh giới |
| Sử dụng Spring Data JPA / JDBC là phần chính | Mô hình blocking hoặc tách blocking execution | Chuyển controller sang Mono không biến transaction JDBC thành reactive |
| Database truy vấn reactive có driver R2DBC phù hợp | Spring Data R2DBC/Reactive Streams | Kiểm tra hỗ trợ transaction và SQL theo driver; không thay thế toàn bộ JPA một cách máy móc |
| Worker xử lý queue với ack/retry riêng | Listener + API SDK/template phù hợp | Chọn concurrency, idempotency và ack semantics theo provider |
| Upload rất lớn | SDK streaming/multipart/resumable upload | Async không đồng nghĩa streaming; cần giới hạn memory và kiểm thử retry chunk |
| Đọc secret khi startup hoặc hiếm khi thay | Config integration hoặc sync client có cache | Độ đơn giản có thể quan trọng hơn async; xem TTL/rotation |
| Lấy token/secret nhiều lần giữa các request | Credential/secret client có cache và refresh | Giữ quyền tối thiểu; tránh gọi mạng dư thừa hoặc log bí mật |

Một quyết định đúng cần xét **latency, throughput, concurrency, footprint, streaming, transaction và kinh nghiệm vận hành**, đồng thời kiểm tra tính năng SDK thực tế. Không có mô hình nào luôn nhanh hơn: chuyển callback hoặc publisher thêm overhead, còn bottleneck có thể nằm ở quota cloud, bandwidth, query hoặc serialisation.

## 10. Lỗi, timeout, retry và cancellation

### 10.1. Lỗi đi theo đường nào?

| Kiểu API | Cách báo lỗi | Nơi xử lý |
| --- | --- | --- |
| **Sync** | Exception ném từ lời gọi | `try/catch`, exception handler, boundary của adapter |
| **Async future** | Future complete exceptionally | `exceptionally`, `handle`, `whenComplete`, chuỗi completion |
| **Reactive** | `onError` signal | `onErrorMap`, `onErrorResume`, `retryWhen`, handler của WebFlux |

Trong `CompletableFuture`, lỗi có thể xuất hiện kèm wrapper như `CompletionException`; code adapter cần giữ **root cause** để phân loại lỗi provider. Với Reactor, chỉ chuyển lỗi thành một response “thành công rỗng” khi nghiệp vụ thật sự cho phép; dùng `onErrorResume` vô điều kiện có thể che mất sự cố cloud.

### 10.2. Timeout phải có ngân sách chung

Một request có thể chịu nhiều giới hạn: HTTP inbound timeout, SDK API timeout, socket/connect timeout, token acquisition timeout, `CompletableFuture.orTimeout`, Reactor `timeout` và deadline ở gateway. Những timeout này **không tự đồng bộ với nhau**.

Nếu gateway dừng chờ sau 5 giây mà SDK tiếp tục thử gọi cloud trong 30 giây, hệ thống có thể tạo ra I/O không còn giá trị và tăng áp lực tài nguyên. Hãy thiết kế **deadline tổng**, cấu hình connect/read/API timeout hợp lý, số lần retry có giới hạn và telemetry của mỗi lớp.

### 10.3. Retry có thể thực thi tác vụ nhiều lần

Ví dụ `Mono.defer(() -> Mono.fromFuture(storage.put(...)))` có thể được **subscribe lại** bởi `retryWhen`; mỗi lần sẽ gọi SDK mới. Retry chỉ an toàn nếu thao tác chấp nhận lặp lại hoặc có **idempotency key**, điều kiện ghi hoặc cơ chế khử trùng lặp thích hợp. Một request timeout **có thể đã được cloud xử lý thành công**, nên không mặc định thử lại với object key mới.

Kết hợp retry từ SDK, Spring Retry, Reactor và message broker mà không tính toán có thể nhân số lần gọi lên nhiều lần. Chỉ retry lỗi tạm thời theo thông tin lỗi và khuyến nghị của provider, với backoff, jitter, deadline và giới hạn đồng thời. `403` do thiếu quyền thường phải sửa identity/IAM/RBAC thay vì retry.

### 10.4. Cancellation không phải rollback

Khi client HTTP ngắt kết nối, subscription Reactor có thể bị cancel. Một future cũng có thể bị cancel. **Không có bảo đảm chung rằng thao tác network đã dừng hoặc object/message đã được thu hồi**. Cancel một `Mono` chỉ thay đổi vòng đời subscriber; cloud service có thể đã nhận request.

Với upload hoặc publish, cần dùng object key/operation ID có thể truy vết, idempotency và bước kiểm tra trạng thái khi cần. Transaction của database không tự rollback một object đã ghi hay message đã phát lên cloud.

## 11. Messaging: listener, consumer và reactive là ba chuyện khác nhau

Một hệ thống nhận message từ SQS, Azure Service Bus hoặc Google Pub/Sub thường hoạt động như sau:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue / topic
    participant L as Listener / subscriber
    participant U as Business handler
    P->>Q: Publish message
    Q-->>P: Kết quả chấp nhận message
    Q->>L: Deliver / poll message
    L->>U: Xử lý nghiệp vụ
    alt Thành công
        U-->>L: Success
        L->>Q: Ack / delete / complete
    else Lỗi hoặc timeout
        U-->>L: Error
        Note over Q,L: Có thể giao lại / dead-letter
    end
~~~

Listener chạy dưới cơ chế **event-driven** của framework/broker không đồng nghĩa tác vụ handler là reactive. Một handler có thể blocking, trả future hoặc dùng publisher; thư viện listener phải **thực sự chờ đúng completion signal** trước khi ack nếu hợp đồng yêu cầu. Nếu ack trước khi tác vụ bất đồng bộ hoàn tất, message có thể bị mất về mặt nghiệp vụ khi xử lý phía sau thất bại.

Với nhiều dịch vụ, message có thể được **giao lại ít nhất một lần** trong một số tình huống. Vì vậy, handler cần idempotency, kiểm soát concurrency, retry/DLQ và quan sát trạng thái ack. SQS visibility timeout, Service Bus lock và Pub/Sub ack deadline có các quy tắc riêng; không dùng một cấu hình thời gian chung cho mọi provider mà chưa kiểm chứng.

## 12. Transaction và context propagation khi đổi thread

### 12.1. Database transaction

Với Spring Data JPA/JDBC, `@Transactional` truyền thống gắn với ngữ cảnh transaction của thread xử lý. Nếu trả về future rồi chạy database write ở callback sau khi phương thức đã kết thúc, **không được giả định** transaction ban đầu vẫn còn hiệu lực trên thread callback.

Trong pipeline với driver và transaction manager reactive thật (ví dụ Spring Data R2DBC phù hợp), có thể dùng **reactive transaction**/`TransactionalOperator` theo hợp đồng Spring. Reactive transaction context không tương đương tự động với transaction JDBC blocking.

Dù sync, future hay reactive, transaction database **không tự bao trùm** S3, Azure Blob, Google Cloud Storage, SQS, Service Bus hoặc Pub/Sub. Khi vừa cập nhật database vừa phát event, **transactional outbox** có thể giúp ghi business state và event vào cùng transaction database rồi phát event sau.

### 12.2. Logging, tracing và security context

Code đổi thread hoặc scheduler có thể không mang theo các giá trị **ThreadLocal** mà ứng dụng đang dùng cho MDC, trace, request/security context. Hãy dùng cơ chế **context propagation** được Spring/Micrometer/Reactor và SDK của đúng phiên bản hỗ trợ; không truyền dữ liệu định danh nhạy cảm vào log hoặc dựa vào một ThreadLocal mặc nhiên tồn tại trên thread callback.

Nên theo dõi **operation ID, request ID, tên API, provider, thời lượng, lỗi, retry count và số request đang chạy**. Với async/reactive, cần quan sát cả **thời gian chờ hoàn thành** và **thời gian đang thực thi**, thay vì chỉ đo thời gian phương thức trả về future hoặc publisher.

## 13. Kiểm thử từng mô hình

| Mức kiểm thử | Điều cần chứng minh | Gợi ý |
| --- | --- | --- |
| Unit test **sync** | Service gọi đúng port, xử lý exception | Fake/mock storage, `assertThrows`, không cần cloud |
| Unit test **future** | Future pending/completed/exceptional được nối đúng; không gọi `join()` | `CompletableFuture` do test tự điều khiển |
| Unit test **reactive** | Trước subscribe chưa có I/O; completion và lỗi được phát đúng | Reactor `StepVerifier`, mock async port |
| Spring context test | Đúng client sync/async bean, cấu hình injection | `ApplicationContextRunner`, context test |
| Integration test | SDK thực sự truyền được payload và nhận kết quả; timeout/retry/permission | Emulator hoặc môi trường cloud test tách biệt |
| Kiểm thử tải | Không giữ event loop, memory/concurrency được giới hạn | Đo latency, thread, pool, pending requests, quota |

Ví dụ unit test kiểm chứng service ở phần 6 **thực sự lazy** và hoàn thành qua port:

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveDocumentServiceTest {
    @Test
    void startsOnSubscriptionAndReturnsObjectKey() {
        AsyncDocumentStorage storage = mock(AsyncDocumentStorage.class);
        byte[] bytes = {1, 2, 3};
        when(storage.put(anyString(), same(bytes)))
            .thenReturn(CompletableFuture.completedFuture(null));

        ReactiveDocumentService service =
            new ReactiveDocumentService(storage);
        Mono<String> result = service.save(bytes);

        verifyNoInteractions(storage);

        StepVerifier.create(result)
            .expectNextMatches(key -> key.startsWith("documents/"))
            .verifyComplete();

        verify(storage).put(anyString(), same(bytes));
    }
}
~~~

Test này xác minh **service** không gọi cloud adapter khi chỉ tạo publisher và gọi khi subscribe. Nó không khẳng định network non-blocking, vì port là mock. Cần thêm test future thất bại, cancellation/timeout, gửi lại cùng operation ID và quan sát với SDK thật ở test environment.

Một bài kiểm thử tích hợp có giá trị phải xác minh **danh tính, IAM/RBAC, network, endpoint/project/region, client bean được chọn và behavior của cloud**. LocalStack, Azurite hoặc emulator khác hữu ích nhưng không mô phỏng đầy đủ các cơ chế identity/permission, quota, reliability hoặc streaming của cloud thật. Các tài nguyên thử nghiệm cần quyền tối thiểu và cleanup.

## 14. Những lỗi triển khai thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `join()`, `get()` hoặc `block()` trên WebFlux event loop | Chặn event loop, tăng độ trễ nhiều request | Trả publisher/future về framework, hoặc chuyển riêng công việc blocking sang scheduler phù hợp |
| Dùng `Mono.just(blockingCall())` | Blocking call chạy ngay lúc dựng publisher | Dùng `Mono.fromCallable` kết hợp `boundedElastic` nếu chưa có async API |
| Tạo future trước `Mono.fromFuture` khi muốn lazy | SDK khởi chạy trước subscription | Dùng `Mono.defer` hoặc API factory lazy tương ứng |
| Dùng `AsyncRequestBody.fromBytes` cho file rất lớn | Buffer toàn bộ dữ liệu trong heap | Dùng streaming/multipart/resumable upload được SDK hỗ trợ |
| Tạo hàng nghìn future không giới hạn | Đầy connection pool, quota, memory | Giới hạn concurrency, queue và backpressure tại boundary |
| Bọc mọi SDK bằng `Flux` rồi nghĩ đã reactive | Blocking SDK vẫn chặn thread | Phân loại đúng client và transport, kiểm tra end-to-end |
| Retry publisher thao tác có side effect mà đổi key mỗi lần | Có thể tạo object hoặc nghiệp vụ trùng | Idempotency key, precondition và thiết kế retry rõ ràng |
| Ack message trước khi future/Mono xử lý xong | Mất message về mặt nghiệp vụ khi callback lỗi | Listener phải chờ kết quả theo contract trước khi ack |
| Trông cậy `@Transactional` JDBC truyền qua callback | Transaction có thể đóng trước khi callback chạy | Chọn transaction boundary phù hợp; dùng outbox cho cloud side effect |
| Chỉ đo thời gian phương thức `saveAsync()` trả về | Báo latency thấp giả dù cloud chậm | Đo từ lúc bắt đầu I/O đến completion/ack, kèm retry |

## 15. Tự luyện

**Bài tập 1 — Chọn mô hình.** Một REST API Spring MVC lưu ảnh 100 KB lên S3, dưới 20 request/giây. Nhóm dự kiến chuyển thành WebFlux chỉ để tăng tốc. Hãy nêu những metric cần đo trước, lợi ích/chi phí của sync và async, và lý do đổi framework chưa chắc tăng throughput.

**Bài tập 2 — Sửa luồng blocking.** Một WebFlux controller gọi `Mono.just(s3Client.putObject(...))`. Giải thích chính xác thời điểm SDK được gọi và đề xuất hai cách sửa: dùng `S3AsyncClient` kết hợp `Mono.defer`, hoặc cô lập SDK blocking bằng `Mono.fromCallable(...).subscribeOn(boundedElastic())`.

**Bài tập 3 — Cảnh báo retry.** Một `Mono.defer` sinh UUID mới rồi ghi object; `retryWhen` thử lại sau timeout. Cloud có thể đã ghi thành công trước khi response mất. Hãy thiết kế object key ổn định từ operation ID và mô tả cơ chế xác nhận trạng thái nếu không rõ kết quả.

**Bài tập 4 — So sánh ba provider.** Với ứng dụng ghi object lớn và phát event, phác thảo adapter cho AWS S3/SQS, Azure Blob/Service Bus và Google Cloud Storage/Pub/Sub. Ghi rõ client sync/async, kiểu tín hiệu trả về, cách stream payload, cách ack message và quyền workload.

**Bài tập 5 — Kiểm thử completion.** Viết một fake `AsyncDocumentStorage` trả future chưa complete. Tạo `Mono` từ service, xác minh không gọi port trước subscribe, cho future complete thành công rồi kiểm tra kết quả; lặp lại với future exceptional và cancel.

**Bài tập 6 — Giao dịch.** Một service dùng `@Transactional` JPA để lưu order rồi gọi Pub/Sub Publisher async. Chỉ ra cửa sổ lỗi nếu publish thành công nhưng database rollback hoặc database commit rồi publish thất bại, sau đó mô tả cách transactional outbox giảm rủi ro.

## 16. Ghi nhớ

- **Sync SDK:** kết quả hoặc exception xuất hiện trực tiếp; thread gọi thường bị giữ trong lúc chờ I/O. **Async SDK:** trả future/callback và completion về sau. **Reactive:** mô hình tín hiệu, subscription và demand; cần nguồn hỗ trợ non-blocking nếu muốn hiệu quả non-blocking thật.
- `Mono.fromFuture(future)` không làm future vốn đã chạy trở thành lazy; dùng `Mono.defer` khi cần bắt đầu gọi cloud đúng lúc subscribe.
- **Không block WebFlux event loop** bằng `join()`, `get()`, `block()` hay SDK blocking. `boundedElastic` là giải pháp cô lập blocking có giới hạn; không biến I/O blocking thành async thực sự.
- **Future, reactive và streaming là ba khía cạnh riêng**. Một request body kiểu `byte[]` vẫn có thể tốn nhiều bộ nhớ, dù SDK trả future hoặc service trả `Mono`.
- AWS, Azure và Google Cloud khác nhau về SDK, reactive support, messaging ack, quota và quyền. Chọn client theo **dịch vụ và phiên bản**, rồi đo tải thực tế và kiểm thử identity, network, retry, cancellation.
- Một request bị cancel hoặc timeout **không đồng nghĩa cloud đã rollback**. Idempotency, retry có ngân sách, observability và ranh giới transaction là yêu cầu bắt buộc để vận hành đúng.
