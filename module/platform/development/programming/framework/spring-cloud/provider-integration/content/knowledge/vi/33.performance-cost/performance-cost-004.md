# Truyền dữ liệu dạng luồng để giới hạn bộ nhớ

Một endpoint nhận file vài gigabyte không nên biến toàn bộ nội dung thành một `byte[]` trước khi gọi cloud storage. Cách đó làm heap tăng theo kích thước file, tạo thêm bản sao khi encode/serialize và có thể gây Full GC hoặc OutOfMemoryError. Với streaming, ứng dụng nhận một phần dữ liệu, chuyển phần đó tới nơi lưu trữ, giải phóng buffer rồi mới yêu cầu phần tiếp theo. Bộ nhớ được giữ gần như ổn định theo kích thước chunk và số luồng đồng thời, thay vì tăng theo tổng kích thước object.

Bài học này tập trung vào đường truyền dữ liệu lớn qua Spring WebFlux và các SDK storage. Bạn sẽ thiết kế pipeline có backpressure, chọn chunk size và concurrency, giải phóng pooled buffer đúng vòng đời, xử lý cancellation/retry và so sánh cách truyền stream của Amazon S3, Azure Blob Storage và Google Cloud Storage.

Bài thuộc chương **Hiệu năng và chi phí** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt streaming, buffering, aggregation và file staging.
- Giải thích vì sao `byte[]`, `readAllBytes()`, `collectList()` và `downloadContent()` có thể làm bộ nhớ tăng theo kích thước object.
- Xây dựng endpoint WebFlux nhận và trả dữ liệu theo từng chunk.
- Quản lý vòng đời `DataBuffer`, đặc biệt với pooled/direct buffer của Reactor Netty.
- Upload/download S3 bằng AWS SDK for Java 2.x với async body, response publisher và multipart.
- Cấu hình Azure Blob async upload/download theo block size và max concurrency.
- Dùng Google Cloud Storage `ReadChannel`, `WriteChannel` và resumable upload.
- Chọn khi nào stream trực tiếp, khi nào stage ra file tạm để hỗ trợ retry/replay.
- Tính ngân sách memory theo chunk size, concurrency và số bản sao.
- Xử lý timeout, cancellation, checksum, cleanup và kiểm thử tải lớn.

## 2. Buffer toàn bộ dữ liệu làm bộ nhớ tăng theo file size

Một cách triển khai dễ viết nhưng không phù hợp với file lớn:

~~~java
byte[] content = inputStream.readAllBytes();
s3Client.putObject(request, RequestBody.fromBytes(content));
~~~

`readAllBytes()` đọc toàn bộ stream vào heap. Nếu file 2 GiB, riêng mảng byte đã cần xấp xỉ 2 GiB; trong thực tế còn có thể có bản sao từ HTTP decoder, byte array, compression, SDK và response processing. Nếu nhiều request chạy cùng lúc, memory tăng theo tổng kích thước của tất cả file.

Các API/operation cần xem xét kỹ:

| Cách làm | Hành vi | Rủi ro |
| --- | --- | --- |
| `InputStream.readAllBytes()` | Đọc hết stream vào một mảng | Heap tỷ lệ với toàn bộ payload |
| `DataBufferUtils.join()` | Ghép nhiều buffer thành một buffer | Aggregation; phải có giới hạn byte |
| `Flux.collectList()` | Giữ toàn bộ item trong list | Memory tăng theo số item và payload |
| `Mono<byte[]>` / `@RequestBody byte[]` | Decode toàn body thành mảng | Không phù hợp với file lớn |
| Azure `downloadContent()` | Đọc toàn bộ blob thành BinaryData | Không phải streaming API |
| GCS `readAllBytes()` | Trả toàn bộ object trong byte[] | Memory tỷ lệ với object size |
| S3 `AsyncResponseTransformer.toBytes()` | Thu toàn bộ response body thành bytes | Không phù hợp khi muốn chuyển tiếp stream |

Streaming giữ từng phần dữ liệu nhỏ trong một khoảng thời gian ngắn. Sau khi downstream tiêu thụ xong chunk, upstream mới tiếp tục phát chunk kế tiếp theo demand.

## 3. Mô hình streaming và backpressure

Một luồng upload WebFlux thường có dạng:

~~~mermaid
flowchart LR
    A[HTTP client] --> B[Flux DataBuffer]
    B --> C[Giới hạn request size]
    C --> D[Chuyển đổi chunk]
    D --> E[Cloud SDK upload]
    E --> F[Storage service]
    E -. demand .-> D
    D -. request next .-> C
    C -. backpressure .-> B
~~~

Các bước không cần giữ toàn bộ object:

1. Web server nhận một buffer.
2. Controller chuyển buffer sang SDK hoặc một staging sink.
3. SDK ghi chunk vào request/multipart part.
4. Buffer được tiêu thụ và giải phóng.
5. Pipeline yêu cầu chunk tiếp theo.

Backpressure chỉ có hiệu lực khi từng tầng tôn trọng Reactive Streams demand. Nếu controller gọi `subscribe()` độc lập, đẩy dữ liệu vào unbounded queue hoặc gom tất cả buffer trước khi upload, ứng dụng đã phá vỡ flow control.

Không dùng `onBackpressureBuffer()` không giới hạn để che giấu downstream chậm. Nếu cần queue, đặt giới hạn theo cả item count và bytes, rồi chọn hành vi khi đầy: chờ upstream, từ chối request, lưu bền vững hoặc hủy operation.

## 4. Spring WebFlux: nhận và trả dữ liệu theo chunk

### 4.1. Dùng Flux<DataBuffer> cho raw body

Với endpoint nhận binary body, có thể nhận trực tiếp `Flux<DataBuffer>`:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class UploadController {

    private final ObjectStorageService storage;

    UploadController(ObjectStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(
        path = "/objects",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Mono<Void> upload(@RequestBody Flux<DataBuffer> body) {
        return storage.upload("incoming/object.bin", body);
    }
}
~~~

Controller trả về `Mono<Void>` gắn với toàn bộ operation. Không gọi `subscribe()` bên trong controller; nếu tự subscribe, request lifecycle có thể kết thúc trước khi upload hoàn tất và lỗi sẽ không được truyền về HTTP response.

### 4.2. Giới hạn bộ nhớ của codec

WebFlux có `maxInMemorySize` cho decoder/message reader cần buffer một phần hoặc toàn bộ nội dung để tạo object. Có thể đặt rõ giới hạn cho default codecs:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Giới hạn này áp dụng cho dữ liệu codec phải buffer, ví dụ một JSON object hoặc một phần dữ liệu cần decode. Nó không phải giới hạn tổng kích thước file upload khi body được xử lý dạng stream. Ứng dụng vẫn cần kiểm tra tổng byte đã nhận, quota người dùng, disk budget và giới hạn số upload đồng thời.

Không tăng `maxInMemorySize` lên hàng trăm megabyte chỉ để một payload lớn không còn báo `DataBufferLimitException`. Nếu use case là file lớn, hãy truyền theo chunk; nếu use case là JSON document lớn, giới hạn kích thước document theo nghiệp vụ.

### 4.3. Multipart upload theo PartEvent

Nếu cần nhận form field và file trong cùng multipart request, WebFlux hỗ trợ `Flux<PartEvent>`. File lớn có thể được chia thành nhiều event; không cần ghép toàn bộ file thành một `FilePart`/byte array trước khi xử lý.

~~~java
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.FormPartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Void> handleMultipart(Flux<PartEvent> events) {
    return events
        .windowUntil(PartEvent::isLast)
        .concatMap(part -> part.switchOnFirst((signal, partEvents) -> {
            if (!signal.hasValue()) {
                return partEvents.then();
            }

            PartEvent event = signal.get();
            if (event instanceof FormPartEvent form) {
                return saveFormField(form.name(), form.value());
            }
            if (event instanceof FilePartEvent file) {
                Flux<DataBuffer> content =
                    partEvents.map(PartEvent::content);
                return storage.upload(file.filename(), content);
            }
            return Mono.error(
                new IllegalArgumentException("Part không được hỗ trợ"));
        }))
        .then();
}
~~~

Đây là cấu trúc minh họa; `saveFormField` và `storage.upload` là service của ứng dụng. Nội dung của từng part phải được tiêu thụ, chuyển tiếp hoặc release hoàn toàn. Nếu bỏ qua một part, hãy release các buffer của part đó để tránh leak pooled memory.

## 5. Vòng đời DataBuffer và pooled memory

### 5.1. Vì sao phải release?

WebFlux có thể dùng Netty pooled/direct buffers. Một `DataBuffer` khi đó là wrapper của vùng nhớ được quản lý bằng reference count. Khi ứng dụng giữ buffer sau khi callback kết thúc hoặc bỏ buffer mà không release, vùng nhớ có thể không được trả về pool.

Các quy tắc:

- Nếu tự đọc/tiêu thụ buffer, release sau khi hoàn tất.
- Nếu chuyển buffer sang API khác và API đó giữ buffer bất đồng bộ, không release trước khi API đọc xong.
- Nếu operator discard buffer do filter/skip/cancel/error, dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`.
- Không release cùng một buffer hai lần.
- Nếu cần giữ buffer qua nhiều callback, phải hiểu và dùng retain/release đúng reference count.

### 5.2. Giải phóng buffer khi chuyển sang ByteBuffer

Azure Blob async nhận `Flux<ByteBuffer>`. Ví dụ dưới đây copy một chunk sang byte array độc lập, sau đó release pooled `DataBuffer` ngay:

~~~java
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;

Flux<ByteBuffer> toByteBuffers(Flux<DataBuffer> source) {
    return source
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .map(dataBuffer -> {
            byte[] copy = new byte[dataBuffer.readableByteCount()];
            dataBuffer.read(copy);
            DataBufferUtils.release(dataBuffer);
            return ByteBuffer.wrap(copy);
        });
}
~~~

Đổi lại, mỗi chunk có một lần copy. Đây là lựa chọn rõ ràng về ownership; nếu tối ưu zero-copy, phải bảo đảm SDK không đọc ByteBuffer sau khi DataBuffer gốc đã được release.

### 5.3. DataBufferUtils.write không tự release buffer

Khi ghi stream vào `WritableByteChannel`, `OutputStream` hoặc `AsynchronousFileChannel`, `DataBufferUtils.write(...)` trả về Flux chứa các buffer đã ghi và không tự release chúng. Phải gắn `DataBufferUtils.releaseConsumer()` hoặc release tương đương sau khi write hoàn tất:

~~~java
DataBufferUtils.write(source, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

Trong code production, đặt discard hook trên source trước khi gọi `write`, sau đó release từng buffer được phát ra sau khi ghi thành công. Ví dụ:

~~~java
Flux<DataBuffer> safeSource = source
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);

return DataBufferUtils.write(safeSource, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

Method trên chỉ minh họa vòng đời buffer; channel do ứng dụng mở phải được đóng riêng. Nếu dùng `DataBufferUtils.write(source, path)`, kiểm tra hành vi lifecycle theo phiên bản Spring đang dùng và vẫn kiểm thử pooled buffer/leak khi cancel hoặc error.

### 5.4. subscriberInputStream có demand hữu hạn

Khi SDK chỉ cung cấp API `InputStream`, Spring có `DataBufferUtils.subscriberInputStream(publisher, demand)`. Tham số `demand` giới hạn số DataBuffer được yêu cầu/giữ trong queue nội bộ. Khi InputStream đóng, subscription bị cancel và buffer đang chờ được release. Đây là cầu nối hữu ích giữa WebFlux request body và SDK blocking/stream API.

Ví dụ:

~~~java
InputStream input = DataBufferUtils.subscriberInputStream(requestBody, 4);
~~~

Với demand 4, queue giữ tối đa xấp xỉ bốn buffer theo cơ chế demand của API, chưa tính buffer đang được đọc và buffer ở các tầng khác. Luôn đóng InputStream khi upload hoàn tất, lỗi hoặc bị hủy.

## 6. Giới hạn tổng dung lượng request

Giới hạn codec không phải giới hạn tổng file. Có thể đếm byte theo từng buffer trước khi chuyển tới storage:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<DataBuffer> enforceMaxBytes(
        Flux<DataBuffer> source,
        long maxBytes) {
    return Flux.defer(() -> {
        AtomicLong received = new AtomicLong();
        return source.concatMap(buffer -> {
                long total = received.addAndGet(
                    buffer.readableByteCount());
                if (total > maxBytes) {
                    DataBufferUtils.release(buffer);
                    return Mono.error(new PayloadTooLargeException());
                }
                return Mono.just(buffer);
            }, 1)
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
    });
}
~~~

`PayloadTooLargeException` là exception của ứng dụng, nên map sang HTTP 413. Bộ đếm được tạo trong `Flux.defer` để mỗi subscription có bộ đếm riêng. Khi vượt giới hạn, buffer gây vượt ngưỡng được release và subscription bị lỗi; discard hook release các buffer còn nằm trong operator queue.

Ngoài max bytes, cần có:

- Giới hạn upload đồng thời theo user/tenant.
- Timeout toàn bộ upload và timeout từng request/chunk.
- Giới hạn số part và kích thước field trong multipart.
- Quota dung lượng lưu trữ và chính sách xóa file tạm.
- Kiểm tra content type, file signature và quyền ghi object key.

## 7. Ngân sách bộ nhớ cho streaming

Ước lượng đơn giản cho một upload:

**M_upload ≈ U × B + P × C + M_codec + M_copy**

Trong đó:

- **U:** số upstream DataBuffer có thể được giữ đồng thời.
- **B:** kích thước trung bình/p95 của một DataBuffer.
- **P:** số part/chunk của cloud SDK đang xử lý song song.
- **C:** chunk size của một part.
- **M_codec:** buffer của HTTP decoder, TLS và network stack.
- **M_copy:** byte array/ByteBuffer bản sao do ứng dụng tạo.

Ví dụ SDK đang upload 4 part song song, mỗi part 8 MiB:

**P × C = 4 × 8 MiB = 32 MiB**

Đây mới là phần buffer multipart ước lượng; chưa tính request buffers, response, direct memory, TLS và các upload khác.

Nếu có 20 upload đồng thời với cùng cấu hình:

**M_parts ≈ 20 × 4 × 8 MiB = 640 MiB**

Vì vậy, phải giới hạn cả:

1. Số upload đang chạy.
2. Số part song song trong mỗi upload.
3. Chunk size.
4. Buffer/prefetch ở upstream.
5. Số bản sao được tạo trong ứng dụng.

Streaming giúp bộ nhớ không tăng theo tổng file size, nhưng không có nghĩa memory là hằng số bất kể concurrency/chunk configuration.

## 8. AWS S3: async streaming và multipart transfer

### 8.1. Bật multipart cho S3AsyncClient

Java-based S3 async client hỗ trợ parallel multipart upload/download từ AWS SDK for Java 2.x phiên bản 2.27.5 trở lên. Cấu hình `multipartEnabled(true)` để bật transfer song song; threshold và minimum part size mặc định hiện là 8 MiB.

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .multipartEnabled(true)
    .build();
~~~

Client là resource sống lâu do Spring quản lý. Không tạo/đóng S3 client cho từng request upload.

### 8.2. Upload file với AsyncRequestBody.fromFile

Nếu request đã được stage thành file tạm, SDK có thể đọc file theo nhu cầu và tự chia multipart:

~~~java
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

CompletableFuture<PutObjectResponse> uploadFile(
        Path stagedFile,
        String bucket,
        String key) {

    return s3.putObject(
        PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build(),
        AsyncRequestBody.fromFile(stagedFile));
}
~~~

File có thể được đọc lại khi SDK cần retry, nên cách này phù hợp khi cần retry/replay. File staging dùng disk thay cho heap; cần quota disk, quyền thư mục, cleanup khi request lỗi/cancel và chính sách xóa file tạm khi process restart.

### 8.3. Upload InputStream chưa biết content length

Với stream chưa biết kích thước, S3 async client có thể nhận `AsyncRequestBody.fromInputStream(input, null, executor)`. Khi multipart đã bật, SDK xử lý phân đoạn stream:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

InputStream input = obtainInputStream();

AsyncRequestBody body =
    AsyncRequestBody.fromInputStream(input, null, s3InputReaderExecutor);

CompletableFuture<PutObjectResponse> upload = s3.putObject(
    PutObjectRequest.builder().bucket(bucket).key(key).build(),
    body);

upload.whenComplete((result, error) -> {
    try {
        input.close();
    } catch (IOException closeError) {
        log.warn("Không đóng được input stream", closeError);
    }
});
~~~

`obtainInputStream`, `log` và `s3InputReaderExecutor` thuộc ứng dụng; executor nên là một Spring bean dùng chung với thread pool và queue hữu hạn, không tạo một thread pool mới cho mỗi request. SDK đọc InputStream trên executor được cung cấp; không đọc blocking stream trên Netty event loop. Đóng InputStream khi future hoàn tất; Spring đóng executor khi ApplicationContext shutdown. Nếu stream đến từ HTTP request one-shot, hãy kiểm tra cancellation và retry semantics. Với yêu cầu retry chắc chắn, stage vào file hoặc dùng source có thể mở lại từ đầu.

Ví dụ executor dùng chung với 8 worker và queue 32 task:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class S3InputReaderConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService s3InputReaderExecutor() {
        return new ThreadPoolExecutor(
            8, 8, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(32),
            new ThreadPoolExecutor.AbortPolicy());
    }
}
~~~

Khi queue đầy, executor reject task để ứng dụng trả lỗi overload có kiểm soát. Kết hợp giới hạn này với số upload đồng thời và memory budget của multipart.

### 8.4. Nối WebFlux request body vào InputStream

Có thể dùng bounded bridge của Spring để tránh gom request body:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

Mono<PutObjectResponse> uploadRequestBody(
        String bucket,
        String key,
        Flux<DataBuffer> requestBody,
        ExecutorService reader) {

    return Mono.defer(() -> {
        InputStream input =
            DataBufferUtils.subscriberInputStream(requestBody, 4);

        AsyncRequestBody body =
            AsyncRequestBody.fromInputStream(input, null, reader);

        return Mono.fromFuture(() -> s3.putObject(
                PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build(),
                body))
            .doFinally(signal -> {
                try {
                    input.close();
                } catch (IOException ignored) {
                    // Đã kết thúc/cancel; ghi log nếu cần.
                }
            });
    });
}
~~~

Đây là ví dụ stream trực tiếp one-shot. `subscriberInputStream` giới hạn số DataBuffer được lấy trước và khi đóng sẽ cancel upstream/release buffer đang chờ. Vì body không thể phát lại từ đầu, không dựa vào retry tự động để phát lại toàn bộ HTTP request. Nếu cần khả năng retry khi network failure, ghi request ra file tạm trước rồi dùng `AsyncRequestBody.fromFile`.

### 8.5. Download S3 bằng ResponsePublisher

Để chuyển tiếp object ra HTTP response mà không tải toàn bộ vào heap, dùng `AsyncResponseTransformer.toPublisher()`:

~~~java
import java.nio.ByteBuffer;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<ByteBuffer> downloadObject(String bucket, String key) {
    return Mono.fromFuture(() -> s3.getObject(
            GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build(),
            AsyncResponseTransformer.toPublisher()))
        .flatMapMany(publisher -> Flux.from(publisher));
}
~~~

`ResponsePublisher` là API nâng cao. Ứng dụng phải subscribe và điều khiển backpressure; publisher có timeout mặc định 60 giây bắt đầu khi body bắt đầu stream. Nếu không subscribe trong khoảng đó, subscription có thể bị cancel. Future hoàn tất khi response và stream publisher sẵn sàng, không phải khi toàn bộ body đã đọc xong; lỗi xảy ra giữa stream cần được xử lý ở tầng stream, ví dụ resume bằng range nếu có thể xác định offset an toàn. Nếu chỉ cần ghi file, dùng `AsyncResponseTransformer.toFile(path)` để stream xuống disk.

Không dùng `AsyncResponseTransformer.toBytes()` cho object lớn nếu mục tiêu là giữ memory ổn định.

## 9. Azure Blob Storage: Flux<ByteBuffer> và block transfer

### 9.1. Upload theo block

Azure Blob async SDK nhận `Flux<ByteBuffer>` cho `BlobAsyncClient.upload`. `ParallelTransferOptions` cho phép đặt block size và số request song song.

~~~java
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.models.BlockBlobItem;
import com.azure.storage.blob.models.ParallelTransferOptions;
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<BlockBlobItem> uploadBlob(
        BlobAsyncClient blob,
        Flux<DataBuffer> requestBody) {

    ParallelTransferOptions transfer = new ParallelTransferOptions()
        .setBlockSizeLong(4L * 1024 * 1024)
        .setMaxConcurrency(2);

    Flux<ByteBuffer> chunks = requestBody
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .map(buffer -> {
            byte[] copy = new byte[buffer.readableByteCount()];
            buffer.read(copy);
            DataBufferUtils.release(buffer);
            return ByteBuffer.wrap(copy);
        });

    return blob.upload(chunks, transfer, true);
}
~~~

Ví dụ dùng block 4 MiB và tối đa 2 request song song cho một transfer. Đây là giá trị minh họa để benchmark, không phải mặc định tối ưu. `upload(..., true)` cho phép overwrite blob hiện có; nếu không muốn ghi đè, truyền false hoặc dùng request condition phù hợp.

Azure SDK có thể buffer dữ liệu của từng subupload để hỗ trợ retry. Do đó, block size nhỏ hơn giúp giảm lượng dữ liệu phải buffer/retry trên mỗi request; maxConcurrency tăng throughput nhưng cũng tăng memory/network pressure. Không cho nhiều process ghi đồng thời cùng một blob key nếu không có concurrency control/ETag condition.

### 9.2. Download bằng downloadStream

`downloadStream()` trả `Flux<ByteBuffer>` và phù hợp với streaming. API `download()` cũ đã deprecated trong một số phiên bản; dùng `downloadStream()`.

~~~java
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Flux;

Flux<DataBuffer> downloadBlob(
        BlobAsyncClient blob,
        ServerHttpResponse response) {

    DataBufferFactory factory = response.bufferFactory();
    return blob.downloadStream().map(chunk -> {
        byte[] copy = new byte[chunk.remaining()];
        chunk.get(copy);
        return factory.wrap(copy);
    });
}
~~~

Mỗi chunk được copy sang buffer do WebFlux response factory tạo. WebFlux chịu trách nhiệm ghi và giải phóng response DataBuffer theo contract của server. Nếu tối ưu zero-copy, phải bảo đảm ownership và lifetime của ByteBuffer từ Azure SDK trước khi trả nó ra khỏi callback.

## 10. Google Cloud Storage: ReadChannel và resumable upload

### 10.1. Download bằng ReadChannel

Google Cloud Storage Java `Storage.reader(...)` trả `ReadChannel`, một channel đọc dữ liệu theo từng buffer. `DataBufferUtils.readByteChannel` có thể chuyển channel thành Flux<DataBuffer> và tự đóng channel khi stream complete, error hoặc cancel.

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<DataBuffer> downloadGcsObject(
        Storage storage,
        String bucket,
        String objectName,
        DataBufferFactory factory) {

    return DataBufferUtils.readByteChannel(
            () -> storage.reader(BlobId.of(bucket, objectName)),
            factory,
            64 * 1024)
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`ReadChannel` là API blocking; `subscribeOn(boundedElastic())` chuyển thao tác đọc khỏi event loop. Buffer ứng dụng ở đây tối đa 64 KiB mỗi DataBuffer. Khi client HTTP hủy response, Flux bị cancel và DataBufferUtils đóng channel.

### 10.2. Upload bằng resumable InputStream

Java Storage client hỗ trợ resumable upload qua `Storage.createFrom(BlobInfo, InputStream, bufferSize)` hoặc `Storage.writer(BlobInfo)`. Với request body WebFlux, có thể dùng bounded InputStream bridge và chạy thao tác blocking trên boundedElastic:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Blob> uploadGcsObject(
        Storage storage,
        BlobInfo blobInfo,
        Flux<DataBuffer> requestBody) {

    return Mono.fromCallable(() -> {
        try (InputStream input =
                 DataBufferUtils.subscriberInputStream(requestBody, 4)) {
            return storage.createFrom(blobInfo, input, 8 * 1024 * 1024);
        }
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là blocking bridge có giới hạn demand 4 buffer ở đầu vào. `createFrom` dùng resumable upload; ví dụ đặt buffer size 8 MiB. Java client hiện có default buffer 15 MiB và minimum 256 KiB; chunk lớn thường tăng throughput nhưng cũng tăng memory giữ lại để retry. Chọn buffer size là bội số phù hợp của 256 KiB và benchmark với số upload đồng thời thực tế.

### 10.3. WriteChannel và semantics của close

Nếu ứng dụng tự tạo dữ liệu theo chunk, `Storage.writer(BlobInfo)` trả `WriteChannel`. Có thể gọi `setChunkSize` để điều chỉnh ngưỡng flush; dữ liệu được buffer và gửi khi đạt ngưỡng hoặc khi channel đóng. `WriteChannel` là blocking, nên chỉ dùng trên worker thread/boundedElastic, không ghi trên WebFlux event loop.

`WriteChannel.close()` flush phần buffer còn lại và hoàn tất việc ghi object. Vì vậy, không xem `close()` là thao tác abort an toàn cho một producer đã lỗi giữa chừng: try-with-resources có thể gọi close khi thoát do exception và hoàn tất dữ liệu chỉ mới ghi được một phần. Phân biệt rõ EOF thành công với cancellation/error; nếu cần resume/cancel phiên upload, dùng cơ chế resumable session tương ứng. Với HTTP request body one-shot, ví dụ `Storage.createFrom(..., InputStream, bufferSize)` ở phần trước là lựa chọn đơn giản hơn vì SDK quản lý resumable upload.

### 10.4. Lưu ý checksum khi đọc streaming

Cloud Storage streaming/range reads không luôn cung cấp checksum xác nhận cho từng đoạn byte tùy ý trước khi ứng dụng xử lý. Nếu yêu cầu nghiệp vụ là xác minh checksum toàn object trước khi tiêu thụ dữ liệu, cần tải/đọc đủ object để tính và so sánh checksum trước khi thực hiện side effect, hoặc dùng phương thức/API hỗ trợ checksum end-to-end theo từng chunk. Không giả định một range stream bất kỳ đã được xác minh bằng checksum toàn object.

## 11. Chọn stream trực tiếp hay stage ra file tạm

| Phương án | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Stream trực tiếp từ HTTP tới SDK | Không cần giữ file tạm; latency thấp | Body one-shot, retry/replay phức tạp; phải phối hợp cancellation giữa hai hệ thống |
| Stage vào file tạm rồi upload | Có thể đọc lại, retry dễ hơn, biết content length | Cần disk quota, cleanup và thêm một lượt I/O |
| Buffer toàn bộ vào RAM | Đơn giản với payload nhỏ | Không phù hợp file lớn hoặc concurrency cao |

Chọn stream trực tiếp khi upstream/downstream hỗ trợ backpressure, request có deadline rõ và chấp nhận xử lý lỗi theo semantics one-shot. Chọn staging khi cần antivirus scan, checksum toàn file trước khi publish, retry chắc chắn, resume sau khi process restart hoặc cần biết kích thước chính xác trước khi upload.

Nếu dùng file tạm:

- Sinh tên file ngẫu nhiên ở thư mục riêng, không lấy trực tiếp đường dẫn từ tên file client.
- Giới hạn dung lượng tối đa và tổng dung lượng staging.
- Xóa file khi success/error/cancel và có job dọn file mồ côi sau process crash.
- Không trả đường dẫn file tạm cho client.
- Dùng storage client upload từ file/path để nguồn có thể replay khi retry.

## 12. Chunk size và concurrency

Chunk size ảnh hưởng số request, memory, retry cost và throughput:

| Chunk size | Tác động thường gặp |
| --- | --- |
| Nhỏ | Memory mỗi part thấp, retry lại ít byte; nhiều request hơn và overhead cao hơn |
| Lớn | Ít request hơn, throughput có thể cao hơn; memory mỗi part và chi phí retry lớn hơn |

Concurrency điều khiển số chunk/request được truyền song song. Tăng concurrency khi network chưa được tận dụng có thể tăng throughput; tăng quá mức sẽ làm memory, socket, TLS buffer và cloud throttling tăng.

Một công thức ước lượng cho SDK transfer:

**M_transfer ≈ uploadConcurrency × partConcurrency × chunkSize**

Ví dụ 6 upload đồng thời, mỗi upload 3 part song song, chunk 8 MiB:

**M_transfer ≈ 6 × 3 × 8 MiB = 144 MiB**

Đây là phần chunk buffer ước lượng, chưa gồm buffer WebFlux, SDK metadata, direct memory và copy. Nếu mỗi request còn giữ 4 DataBuffer 64 KiB:

**M_ingress ≈ 6 × 4 × 64 KiB = 1,5 MiB**

Tổng memory thực tế lớn hơn hai số này; dùng chúng để hiểu xu hướng và đặt headroom, sau đó đo heap/direct memory/RSS bằng load test.

## 13. Backpressure, cancellation và timeout

### 13.1. Propagate cancellation

Khi client HTTP ngắt kết nối, WebFlux có thể cancel subscription. Pipeline phải truyền cancellation xuống SDK, đóng InputStream/channel và ngừng đọc dữ liệu mới. Không tạo một upload background detached bằng `subscribe()` nếu không có job model và durable state riêng.

### 13.2. Đặt timeout theo từng tầng

- Request body receive timeout: giới hạn thời gian client gửi dữ liệu.
- Upload overall deadline: giới hạn tổng thời gian upload.
- Per-request/chunk timeout: giới hạn một lần truyền block/part.
- Idle timeout: phát hiện stream không còn tiến triển.
- Cleanup timeout: giới hạn thời gian chờ đóng resource.

Không đặt timeout ngắn hơn thời gian upload hợp lệ của file lớn. Nếu upload dài, dùng upload session/resumable protocol và cho client tiếp tục từ offset đã xác nhận.

### 13.3. Retry chỉ khi có thể xác định byte range an toàn

Retry toàn bộ stream one-shot có thể thất bại vì source không phát lại được. Với multipart/resumable transfer, retry theo part/chunk đã biết offset và checksum an toàn hơn. Với stream trực tiếp từ client, nếu nguồn không thể replay, lỗi giữa chừng thường yêu cầu client gửi lại hoặc ứng dụng stage dữ liệu để có nguồn replay.

Không retry lỗi validation, permission hoặc quota vĩnh viễn. Với throttling/transient network error, dùng backoff và jitter, giới hạn số lần retry và tổng deadline.

## 14. Checksum, content length và tính toàn vẹn

### 14.1. Content length phải chính xác

Nếu SDK yêu cầu content length, cung cấp đúng số byte. Giá trị thấp hơn thực tế có thể tạo object bị truncate; giá trị cao hơn có thể làm upload lỗi hoặc connection chờ mãi. Nếu không biết kích thước, dùng API hỗ trợ unknown-length/multipart/resumable thay vì ước lượng.

### 14.2. Checksum theo chunk và toàn object

Với file lớn, có thể tính checksum tăng dần khi đọc từng chunk:

~~~java
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import org.springframework.core.io.buffer.DataBuffer;

MessageDigest digest = MessageDigest.getInstance("SHA-256");

void updateDigest(DataBuffer buffer) {
    ByteBuffer view = buffer.asByteBuffer(
        buffer.readPosition(),
        buffer.readableByteCount());
    digest.update(view);
}
~~~

Đoạn này minh họa cập nhật digest trên view của buffer; không giữ toàn bộ file. Sau khi stream hoàn tất, lấy digest và so sánh với checksum do client gửi hoặc metadata đã xác thực. Nếu dùng buffer pooled, chỉ đọc trong thời gian buffer còn hợp lệ và vẫn release theo đúng ownership.

`MessageDigest` không thread-safe; cập nhật các chunk của cùng một object theo thứ tự trên một pipeline tuần tự hoặc dùng cơ chế checksum song song có bước kết hợp được định nghĩa rõ.

### 14.3. Không publish metadata hoàn tất quá sớm

Chỉ đánh dấu upload là READY sau khi cloud SDK xác nhận object đã hoàn tất, multipart/resumable session đã commit và checksum/size đã kiểm tra. Với staging workflow, có thể upload vào object key tạm rồi đổi trạng thái/metadata hoặc copy sang key chính sau validation.

## 15. Bảo mật khi stream file

- Không tin filename hoặc Content-Type do client gửi.
- Dùng object key do server sinh hoặc kiểm tra chặt chẽ prefix/tenant.
- Giới hạn bytes và thời gian upload để chống resource exhaustion.
- Không ghi access token, signed URL hoặc nội dung nhạy cảm vào log.
- Dùng workload identity/managed identity và quyền tối thiểu cho bucket/container.
- Xác thực file signature khi loại file ảnh hưởng tới nghiệp vụ.
- Nếu cần antivirus/DLP, stage vào quarantine trước khi công bố object.
- Cấu hình lifecycle để dọn multipart upload chưa hoàn tất và object tạm.

## 16. Quan sát streaming trong production

Theo dõi các chỉ số:

| Metric | Câu hỏi cần trả lời |
| --- | --- |
| Active uploads/downloads | Có bao nhiêu transfer đồng thời? |
| Bytes received/sent | Throughput thực tế của stream là bao nhiêu? |
| Chunk size và part concurrency | Mỗi transfer giữ bao nhiêu buffer? |
| Backpressure wait time | Upstream phải chờ downstream bao lâu? |
| Upload duration p50/p95/p99 | Tail latency có tăng theo file size không? |
| Retry count và failed part count | Network/service có làm upload lặp lại nhiều không? |
| Cancellation count | Client rời đi có được propagate đúng không? |
| Heap/direct memory/RSS | Có leak hoặc buffer accumulation không? |
| Temp disk usage | Staging có đầy hoặc còn file mồ côi không? |
| Incomplete multipart/resumable sessions | Có transfer bị bỏ dở không? |

Không chỉ theo dõi heap. Netty pooled buffers và SDK có thể sử dụng direct/native memory; container RSS và direct buffer metrics giúp phát hiện leak mà heap chart không thể hiện.

## 17. Kiểm thử streaming và giới hạn bộ nhớ

1. Upload file nhỏ, file gần giới hạn và file lớn hơn heap một cách có kiểm soát.
2. So sánh stream trực tiếp với `byte[]`/aggregation để thấy khác biệt memory.
3. Tăng upload concurrency 1, 4, 8, 16; đo memory peak và throughput.
4. Thử chunk 1, 4, 8, 16 MiB và quan sát retry/latency.
5. Làm chậm cloud endpoint hoặc dùng mock server để xác minh backpressure.
6. Ngắt client giữa upload và kiểm tra upstream subscription, InputStream, channel và multipart cleanup.
7. Giả lập lỗi một part/chunk và kiểm tra retry không gửi sai byte range.
8. Gửi payload vượt max bytes và xác minh HTTP 413 cùng cleanup.
9. Dùng file có checksum sai và xác minh object không được đánh dấu READY.
10. Chạy nhiều giờ để phát hiện direct-memory leak và file staging không được xóa.

## 18. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `readAllBytes()` hoặc `collectList()` | Heap tăng theo file size | Dùng Flux/chunk stream |
| `DataBufferUtils.join()` không giới hạn | Aggregation lớn và DataBufferLimitException/OOM | Chỉ join payload nhỏ, đặt max byte |
| Không release pooled DataBuffer | Direct memory leak | Release sau consume và doOnDiscard |
| Release buffer trước khi SDK đọc xong | Corrupted data/use-after-release | Chuyển ownership hoặc copy chunk |
| Dùng `downloadContent()` cho object lớn | Buffer toàn object | Dùng `downloadStream()` hoặc channel |
| AWS `toBytes()` | Giữ toàn response body trong memory | Dùng ResponsePublisher hoặc toFile |
| S3 AsyncRequestBody publisher one-shot bị retry | Retry không phát lại đầy đủ body | Dùng file/replayable source hoặc upload session |
| Azure block size/concurrency quá cao | Nhiều chunk bị buffer đồng thời | Giảm block size/concurrency |
| GCS ReadChannel chạy trên event loop | Chặn request khác | Chạy trên boundedElastic |
| Không đóng InputStream/channel | Resource leak và upload không kết thúc | using/try-with-resources/doFinally |
| Không propagate cancel | Cloud transfer tiếp tục sau khi client rời đi | Gắn SDK operation với subscription lifecycle |
| Không có disk quota cho staging | Disk đầy | Giới hạn bytes/concurrency và cleanup |

## 19. Quy trình thiết kế streaming

~~~mermaid
flowchart TD
    A[Đo file size, throughput và concurrency] --> B[Chọn stream trực tiếp hay staging]
    B --> C[Đặt max request bytes và codec limits]
    C --> D[Chọn chunk size và part concurrency]
    D --> E[Kiểm soát DataBuffer ownership/release]
    E --> F[Thiết lập retry, checksum và cancellation]
    F --> G[Load test với client chậm/ngắt kết nối]
    G --> H{Memory và disk nằm trong budget?}
    H -->|Không| I[Giảm chunk/concurrency hoặc staging budget]
    I --> G
    H -->|Có| J[Chốt metrics, alert và cleanup policy]
~~~

Checklist trước production:

1. Không có operation nào vô tình materialize toàn bộ object?
2. Tổng request bytes có giới hạn ở application layer?
3. Mỗi DataBuffer được release đúng một lần trên success/error/cancel?
4. SDK chunk size và parallelism có nằm trong memory budget?
5. Blocking SDK/channel có chạy trên worker thread phù hợp?
6. Retry có nguồn dữ liệu replayable hoặc resume offset an toàn?
7. Cancellation có đóng stream/channel và dừng transfer?
8. Multipart/resumable upload chưa hoàn tất có được cleanup?
9. Checksum/size được xác minh trước khi object chuyển sang READY?
10. Có metrics heap, direct memory, disk usage và transfer concurrency?

## 20. Bài tập thực hành

**Bài tập 1 — WebFlux streaming.** Tạo endpoint nhận `Flux<DataBuffer>` và upload file 1 GiB. Xác minh heap không tăng tuyến tính theo file size.

**Bài tập 2 — DataBuffer lifecycle.** Tạo pipeline có filter/cancel; bật Netty leak detection và chứng minh buffer được release sau success, error và cancel.

**Bài tập 3 — AWS S3 multipart.** Bật `multipartEnabled(true)`, upload stream không biết content length và đo part concurrency, throughput và retry.

**Bài tập 4 — AWS ResponsePublisher.** Stream object từ S3 tới HTTP response. Làm client đọc chậm và kiểm tra backpressure/cancel; so sánh với `toBytes()`.

**Bài tập 5 — Azure Blob.** Thử block size 2, 4, 8 MiB với maxConcurrency 1, 2, 4. Tính memory budget và đo timeout/retry.

**Bài tập 6 — Google Cloud Storage.** Upload bằng resumable `createFrom` với buffer 8 MiB; download bằng ReadChannel và DataBufferUtils. Xác minh channel đóng khi client cancel.

**Bài tập 7 — Direct stream vs staging.** So sánh upload one-shot trực tiếp với stage ra file rồi upload. Làm đứt mạng giữa chừng và kiểm tra khả năng retry/replay.

**Bài tập 8 — Size guard.** Đặt giới hạn 100 MiB, gửi file 101 MiB và xác minh HTTP 413, buffer được release và không có object hoàn chỉnh.

**Bài tập 9 — Checksum.** Tính SHA-256 theo chunk, so sánh checksum kỳ vọng và bảo đảm object sai checksum không chuyển sang READY.

**Bài tập 10 — Concurrency.** Chạy 10, 50 và 100 upload đồng thời; theo dõi heap/direct memory/RSS và chọn concurrency phù hợp với giới hạn container.

## 21. Ghi nhớ

- Streaming giữ dữ liệu theo chunk; `byte[]`, `readAllBytes()`, `collectList()` và `downloadContent()` có thể materialize toàn object.
- Backpressure chỉ bảo vệ memory khi từng tầng tôn trọng demand và không có unbounded queue.
- `DataBuffer` có thể là pooled/direct buffer; release đúng ownership và thêm `doOnDiscard` cho buffer bị bỏ.
- `DataBufferUtils.write` với channel/OutputStream không tự release buffer; dùng `releaseConsumer()` hoặc release tương đương.
- AWS S3 async multipart hỗ trợ stream không biết content length; `AsyncRequestBody.fromPublisher` yêu cầu source replayable nếu SDK retry.
- AWS `AsyncResponseTransformer.toPublisher()` cho download streaming nhưng ứng dụng phải subscribe và quản lý backpressure.
- Azure Blob `upload(Flux<ByteBuffer>, ...)` và `downloadStream()` hỗ trợ reactive stream; block size và maxConcurrency ảnh hưởng trực tiếp memory.
- Google Cloud Storage `ReadChannel`/`WriteChannel` là channel API; Java client hỗ trợ resumable upload với buffer size có thể cấu hình.
- Chunk size × concurrency × số upload đồng thời quyết định phần lớn transfer buffer memory.
- Cancellation, checksum, retry/replay, disk quota và cleanup là một phần của thiết kế streaming.

## 22. Tài liệu tham khảo

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Reactive Core and codec memory limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — Multipart streaming with PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [AWS SDK for Java 2.x — Uploading streams to S3](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices-s3-uploads.html)
- [AWS SDK for Java 2.x — Async client streaming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
- [AWS SDK for Java 2.x — S3 async multipart transfers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-async-client-multipart.html)
- [AWS SDK for Java 2.x — AsyncRequestBody API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/core/async/AsyncRequestBody.html)
- [Azure Storage — Performance tuning for Java uploads and downloads](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-tune-upload-download-java)
- [Azure Storage — BlobAsyncClient Java API](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.blobasyncclient)
- [Google Cloud Storage — Java Storage API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Google Cloud Storage — Resumable uploads](https://docs.cloud.google.com/storage/docs/resumable-uploads)
- [Google Cloud Storage — Streaming reads and checksum limitations](https://docs.cloud.google.com/storage/docs/streaming-reads)
