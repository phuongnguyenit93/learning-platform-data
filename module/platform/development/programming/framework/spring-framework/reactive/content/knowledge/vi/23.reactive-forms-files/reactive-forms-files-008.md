# Kiểm chứng tải lên, tải xuống lớn mà không gom hết vào bộ nhớ

Trong **Spring WebFlux**, xử lý file lớn cần giữ dữ liệu ở dạng luồng từ lúc nhận request đến lúc ghi xuống storage, và từ lúc đọc storage đến lúc gửi response. Mục tiêu là bộ nhớ chỉ giữ một số buffer có kích thước giới hạn, thay vì tạo một mảng byte hoặc danh sách chứa toàn bộ file.

Có ba lựa chọn phổ biến cho upload:

- **`FilePart.transferTo(Path)`**: phù hợp với form multipart thông thường. Multipart reader có thể chuyển phần file lớn sang file tạm theo ngưỡng cấu hình; ứng dụng chuyển file tới vị trí lưu cuối.
- **`Flux<PartEvent>`**: xử lý multipart tuần tự theo từng event và buffer. Đây là lựa chọn khi cần streaming trực tiếp, xử lý nhiều part hoặc relay dữ liệu mà không gom toàn bộ multipart thành map.
- **`@RequestBody Flux<DataBuffer>`**: phù hợp với raw upload có body là byte stream, ví dụ `application/octet-stream`.

Với download, có thể trả `FileSystemResource` để Resource message writer đọc file theo từng phần, hoặc tự tạo `Flux<DataBuffer>` bằng `DataBufferUtils.read` rồi ghi vào response. Client cũng cần tiêu thụ response theo luồng, chẳng hạn `bodyToFlux(DataBuffer.class)` và ghi từng buffer xuống file.

Bài này tập trung vào cách thiết kế, kiểm chứng và vận hành luồng upload/download lớn, bao gồm backpressure, bộ đệm, checksum, giới hạn multipart, cancellation, xử lý lỗi và test không tự gom response vào RAM.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt upload/download streaming với cách đọc toàn bộ file vào `byte[]`.
2. Dùng `FilePart.transferTo` để lưu file multipart với mức dùng RAM được giới hạn.
3. Dùng `Flux<PartEvent>` để xử lý multipart theo từng part và từng buffer.
4. Dùng `Flux<DataBuffer>` và `DataBufferUtils.write/read` cho raw upload/download.
5. Trả `Resource` để WebFlux ghi file lớn theo luồng.
6. Giữ backpressure bằng cách trả publisher và tránh `block()`/`subscribe()` thủ công.
7. Quản lý ownership của DataBuffer, release đúng lúc và xử lý cancellation.
8. Cấu hình ngưỡng memory, disk quota, số lượng part và giới hạn request.
9. Kiểm chứng nội dung bằng kích thước và SHA-256 theo từng chunk.
10. Viết WebTestClient test upload/download file lớn mà không dùng `expectBody(byte[].class)` để gom response.
11. Phân biệt test chức năng với đo memory thực tế bằng load test, JFR và metrics.

## 2. Vì sao không nên gom toàn bộ file vào RAM?

Cách làm đơn giản nhưng nguy hiểm là đọc toàn bộ request body thành byte array:

~~~java
@PostMapping("/upload")
Mono<String> upload(@RequestBody Mono<byte[]> body) {
    return body.flatMap(bytes -> {
        // Ghi toàn bộ bytes xuống file.
        return save(bytes);
    });
}
~~~

Với file 500 MiB, cách này có thể cần một mảng ít nhất 500 MiB cho mỗi request, chưa tính bản sao, object overhead, multipart parser và các request đồng thời. Mười request cùng lúc có thể tạo áp lực hàng gigabyte.

Một lỗi tương tự ở phía download là:

~~~java
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok(bytes);
~~~

Nó đọc toàn bộ file vào heap trước khi response được gửi.

Cách streaming giữ một chuỗi nhỏ các buffer:

~~~text
Upload:
HTTP chunks
   |
   v
WebFlux DataBuffer stream
   |
   v
FilePart / PartEvent / Flux<DataBuffer>
   |
   v
File writer
   |
   v
Disk

Download:
Disk
   |
   v
Resource writer / DataBufferUtils.read
   |
   v
DataBuffer stream
   |
   v
HTTP response chunks
   |
   v
Client
~~~

Khi downstream chậm, backpressure giúp upstream không phát dữ liệu vô hạn. Bộ nhớ sử dụng thường phụ thuộc vào kích thước buffer, số buffer đang chờ, mức prefetch, số request đồng thời và các lớp trung gian. Streaming giảm đáng kể nhu cầu heap, nhưng không tự giới hạn tổng dung lượng file, disk hoặc concurrency.

## 3. Các kiểu upload trong Spring WebFlux

### 3.1. Multipart với FilePart

Với browser form hoặc REST multipart, nhận file qua `FilePart`:

~~~java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<UploadReceipt> upload(@RequestPart("file") FilePart file) {
    Path destination = createServerSidePath();

    return file.transferTo(destination)
        .then(Mono.fromCallable(() -> inspect(destination)));
}
~~~

`FilePart.transferTo(Path)` trả về `Mono<Void>`. Publisher hoàn tất khi file đã được chuyển tới đích hoặc phát lỗi. Code không cần biến file thành `byte[]`.

Với multipart reader mặc định, file part vượt ngưỡng `maxInMemorySize` được ghi ra disk tạm; vì vậy đây là mô hình bounded-memory có thể sử dụng disk tạm. Ứng dụng sau đó chuyển part tới vị trí lưu cuối. Cần tính đến dung lượng disk có thể tăng trong lúc file tạm và file đích cùng tồn tại.

Ưu điểm:

- API controller ngắn và dễ đọc.
- Phù hợp với form multipart có metadata và một vài file.
- Không cần tự quản lý từng DataBuffer.
- Dễ kết hợp với validation và các field form.

Giới hạn:

- Multipart reader vẫn phải phân tích cấu trúc request.
- Với truy cập theo tên part hoặc map nhiều part, framework có thể cần parse và giữ metadata/part collection.
- Nếu cần xử lý từng part ngay khi nhận hoặc relay file lớn trực tiếp, `PartEvent` phù hợp hơn.

### 3.2. Multipart streaming với PartEvent

Spring WebFlux hỗ trợ `@RequestBody Flux<PartEvent>` để xử lý multipart tuần tự. Một form field tạo `FormPartEvent`; file upload tạo một hoặc nhiều `FilePartEvent`. File lớn có thể được chia thành nhiều DataBuffer event.

Các event cuối cùng của mỗi part có `isLast() == true`. Có thể dùng `windowUntil(PartEvent::isLast)` để chia stream thành từng part, sau đó `switchOnFirst` để xác định part là field hay file.

~~~java
@PostMapping(
    path = "/streaming-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<Void> uploadStreaming(@RequestBody Flux<PartEvent> allEvents) {
    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
            partEvents.switchOnFirst((signal, events) -> {
                if (!signal.hasValue()) {
                    return events.then();
                }

                PartEvent event = signal.get();

                if (event instanceof FormPartEvent formEvent) {
                    String value = formEvent.value();

                    // Xử lý field; tiêu thụ/release content buffer.
                    return events
                        .map(PartEvent::content)
                        .doOnNext(DataBufferUtils::release)
                        .then();
                }

                if (event instanceof FilePartEvent fileEvent) {
                    String originalFilename = fileEvent.filename();

                    // Chọn đích do server tạo, không dùng filename làm path.
                    Path destination = createServerSidePath();

                    Flux<DataBuffer> content =
                        events.map(PartEvent::content);

                    // Overload Path tiêu thụ và release buffer đã ghi.
                    return DataBufferUtils.write(content, destination);
                }

                return Mono.error(
                    new IllegalArgumentException("Unsupported part event")
                );
            })
        )
        .then();
}
~~~

Đây là snippet mô tả cách tổ chức streaming; các hàm tạo path, kiểm tra quyền, lưu metadata và cleanup file lỗi cần được triển khai trong ứng dụng. Không dùng `originalFilename` làm đường dẫn filesystem. Khi xử lý `PartEvent`, phải tiêu thụ, relay hoặc release content buffer của mọi part, kể cả field không cần dùng; bỏ qua buffer có thể gây leak.

Dùng `concatMap` để xử lý từng part tuần tự khi thứ tự và giới hạn concurrency quan trọng. Nếu xử lý song song, phải cân nhắc thứ tự part, disk I/O, giới hạn file đang mở và lượng buffer được giữ đồng thời.

### 3.3. Raw upload với Flux<DataBuffer>

Nếu client gửi raw byte stream thay vì multipart, controller có thể nhận `Flux<DataBuffer>`:

~~~java
@PostMapping(
    path = "/raw",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
Mono<Void> uploadRaw(@RequestBody Flux<DataBuffer> body) {
    Path destination = createServerSidePath();
    return DataBufferUtils.write(body, destination);
}
~~~

`DataBufferUtils.write(Publisher<DataBuffer>, Path)` trả `Mono<Void>` hoàn tất khi ghi xong. Overload ghi vào Path quản lý việc release các buffer đã ghi. Nếu dùng overload nhận channel hoặc OutputStream, phải đọc tài liệu contract của overload đó: một số overload trả lại Flux buffer và không tự release chúng.

Raw upload không có tên part, filename hoặc multipart metadata. Nếu cần thông tin mô tả file, truyền metadata qua header hoặc endpoint riêng và xác thực dữ liệu đó.

## 4. FilePart.transferTo và nơi lưu file

### 4.1. Không dùng filename do client gửi làm path

Filename trong multipart là dữ liệu do client kiểm soát. Không viết:

~~~java
Path destination = uploadDirectory.resolve(file.filename());
~~~

Tên có thể chứa dấu phân cách đường dẫn, chuỗi traversal hoặc ký tự đặc biệt. Thay vào đó, tạo ID ở server:

~~~java
UUID id = UUID.randomUUID();
Path destination = uploadDirectory.resolve(id + ".bin");
~~~

Nếu cần giữ tên gốc để hiển thị, lưu riêng dưới dạng metadata đã kiểm tra; không dùng nó để quyết định vị trí lưu.

### 4.2. Tạo thư mục và thực hiện I/O blocking

Các thao tác như `Files.createDirectories`, `Files.size` và đọc checksum qua `InputStream` là blocking. Trong WebFlux, không chạy chúng trực tiếp trên event-loop. Dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` cho đoạn I/O blocking.

`FilePart.transferTo` là API reactive; trả publisher và ghép với các bước tiếp theo:

~~~java
return Mono.fromCallable(() -> Files.createDirectories(uploadDirectory))
    .subscribeOn(Schedulers.boundedElastic())
    .then(file.transferTo(destination))
    .then(Mono.fromCallable(() -> inspect(destination))
        .subscribeOn(Schedulers.boundedElastic()));
~~~

Không gọi `block()` hoặc tự `subscribe()` trong controller để chờ việc ghi file. Khi trả publisher, WebFlux quản lý subscription, lỗi và cancellation theo request.

### 4.3. Kiểm tra file sau upload

Không chỉ dựa vào việc `transferTo` hoàn tất. Một receipt có thể chứa ID do server tạo, kích thước byte và SHA-256.

Để tính SHA-256 cho file lớn, đọc file theo chunk:

~~~java
static String sha256(Path path) throws IOException {
    MessageDigest digest;
    try {
        digest = MessageDigest.getInstance("SHA-256");
    }
    catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException(ex);
    }

    try (InputStream input = Files.newInputStream(path)) {
        byte[] chunk = new byte[64 * 1024];
        int read;

        while ((read = input.read(chunk)) != -1) {
            digest.update(chunk, 0, read);
        }
    }

    return HexFormat.of().formatHex(digest.digest());
}
~~~

Mỗi lần chỉ giữ 64 KiB trong mảng đọc. Không dùng `Files.readAllBytes` hoặc tạo một buffer có kích thước bằng toàn bộ file để tính hash.

Kích thước và checksum giúp xác minh tính toàn vẹn sau khi ghi. Nếu client gửi checksum kỳ vọng, so sánh với checksum server tính được trước khi đánh dấu file sẵn sàng.

## 5. Download file lớn

### 5.1. Trả FileSystemResource

Cách đơn giản cho file trên disk là trả `FileSystemResource`:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<Resource>> download(@PathVariable UUID id) {
    Path path = uploadDirectory.resolve(id + ".bin");

    return Mono.fromCallable(() -> {
        if (!Files.isRegularFile(path)) {
            return ResponseEntity.<Resource>notFound().build();
        }

        Resource resource = new FileSystemResource(path);

        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .contentLength(Files.size(path))
            .header(
                HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                    .filename(id + ".bin")
                    .build()
                    .toString()
            )
            .body(resource);
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

`ResourceHttpMessageWriter` đọc Resource và ghi nội dung theo luồng. Không cần tạo `byte[]` chứa cả file. `Files.size` được gọi trên boundedElastic vì đây là file-system operation.

Dùng `Resource` khi chỉ cần phục vụ file. Dùng `DataBufferUtils.read` khi cần điều khiển kích thước chunk, transform byte hoặc tích hợp với một pipeline byte-level.

### 5.2. Download bằng DataBufferUtils.read

Khi cần kiểm soát chunk size hoặc response pipeline, có thể đọc file thành Flux<DataBuffer>:

~~~java
@GetMapping("/stream/{id}")
Mono<Void> downloadStream(
        @PathVariable UUID id,
        ServerWebExchange exchange) {

    Path path = uploadDirectory.resolve(id + ".bin");

    return Mono.fromCallable(() -> Files.size(path))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(size -> {
            ServerHttpResponse response = exchange.getResponse();

            response.getHeaders().setContentType(
                MediaType.APPLICATION_OCTET_STREAM
            );
            response.getHeaders().setContentLength(size);

            Flux<DataBuffer> body = DataBufferUtils.read(
                path,
                response.bufferFactory(),
                64 * 1024
            );

            return response.writeWith(body);
        });
}
~~~

Snippet này giả định file đã tồn tại; ứng dụng cần xử lý `NoSuchFileException` và trả 404 theo hợp đồng API. `DataBufferUtils.read` đọc file thành các buffer có kích thước tối đa khoảng 64 KiB. `writeWith` tiếp nhận publisher và ghi ra response; khi đã chuyển buffer cho response writer, không release buffer thêm lần nữa ở controller.

### 5.3. Content-Length, chunked transfer và range

- Nếu biết kích thước file, đặt `Content-Length` để client biết số byte mong đợi.
- Nếu không biết trước kích thước hoặc stream được tạo động, server có thể dùng cơ chế transfer framing phù hợp với HTTP version.
- Nếu hỗ trợ resume, cần thiết kế Range/Content-Range và status 206 Partial Content đúng chuẩn. Không tự trả 206 nếu chưa thực sự giới hạn byte range.
- Với file tĩnh hoặc object storage, cân nhắc cơ chế phục vụ file/range chuyên dụng thay vì tự viết lại toàn bộ protocol.

## 6. WebClient tải lên và tải xuống theo luồng

Client cũng có thể vô tình gom toàn bộ body vào RAM.

### 6.1. Upload từ Resource

Có thể gửi multipart với `FileSystemResource`:

~~~java
Mono<UploadReceipt> result = webClient.post()
    .uri("/api/files")
    .body(BodyInserters.fromMultipartData(
        "file",
        new FileSystemResource(sourcePath)
    ))
    .retrieve()
    .bodyToMono(UploadReceipt.class);
~~~

Resource được đọc để tạo request body. Tránh đọc file trước bằng `Files.readAllBytes` rồi gửi byte array.

### 6.2. Download vào file

Không dùng `bodyToMono(byte[].class)` với file lớn. Dùng `bodyToFlux(DataBuffer.class)` và `DataBufferUtils.write`:

~~~java
Mono<Void> download = webClient.get()
    .uri("/api/files/{id}", id)
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .as(buffers -> DataBufferUtils.write(buffers, destination));
~~~

Overload ghi vào Path hoàn tất khi các buffer đã được ghi và release. Publisher chỉ chạy khi được subscribe; hãy trả publisher cho tầng gọi để lifecycle và cancellation được quản lý.

Nếu cần xử lý lỗi HTTP trước khi bắt đầu ghi file, dùng `exchangeToMono`/`exchangeToFlux` để kiểm tra status và chọn cách tiêu thụ body phù hợp. Không bỏ qua response body lỗi mà không giải phóng/tiêu thụ đúng cách.

## 7. Multipart limits và giới hạn tài nguyên

Streaming không có nghĩa là bỏ hết giới hạn. Một upload có thể không tốn nhiều heap nhưng vẫn làm đầy disk, giữ file descriptor hoặc chiếm băng thông quá lâu.

Với Spring Boot WebFlux, có thể cấu hình các thuộc tính multipart trong `application.properties`:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=10
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=./var/multipart-tmp
~~~

Ý nghĩa:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| max-in-memory-size | Ngưỡng memory cho non-file part; với file part là ngưỡng trước khi ghi nội dung ra disk. |
| max-disk-usage-per-part | Giới hạn disk cho từng part được lưu ra disk. |
| max-parts | Giới hạn số part trong một multipart request. |
| max-headers-size | Giới hạn kích thước header của từng part. |
| file-storage-directory | Thư mục lưu part tạm vượt ngưỡng memory. |

Các giới hạn trên không phải giới hạn tổng request size ở mọi tầng. Hãy đặt thêm giới hạn tại reverse proxy/gateway, server connector và tầng nghiệp vụ. Kiểm tra disk quota và quyền truy cập thư mục tạm. Đảm bảo thư mục storage tồn tại và process có quyền ghi.

Với `PartEvent` streaming, nội dung part được xử lý trực tiếp theo event; cơ chế file tạm của multipart reader không áp dụng theo cùng cách. Khi dùng chế độ đó, ứng dụng chịu trách nhiệm consume/relay/release buffer và quản lý file đích.

### 7.1. maxInMemorySize không phải tổng dung lượng file

Không diễn giải `max-in-memory-size=256KB` thành “file upload tối đa 256 KiB”. Với multipart reader mặc định:

- Non-file part vượt giới hạn có thể bị từ chối.
- File part vượt ngưỡng được ghi ra disk.
- Disk quota riêng quyết định dung lượng part có thể lưu.
- max-parts giới hạn số part, không phải byte.
- Gateway/server vẫn cần giới hạn tổng request và thời gian nhận.

Nếu đặt `max-in-memory-size=-1`, nội dung có thể được giữ toàn bộ trong memory; điều này không phù hợp cho file lớn trong môi trường production.

### 7.2. Giới hạn đồng thời và timeout

Ngoài kích thước file, cần quản lý số upload/download đồng thời, tốc độ tối thiểu hoặc thời gian nhận tối đa, số file tạm và dung lượng còn trống, file descriptor/channel đang mở, retry và thời gian giữ kết nối, quota theo người dùng/tenant và dọn file upload dở dang.

Đừng đặt concurrency quá cao chỉ vì mỗi request dùng ít heap. Disk I/O, network và file descriptor vẫn có giới hạn.

## 8. Backpressure, cancellation và DataBuffer ownership

### 8.1. Giữ pipeline reactive

Để backpressure có hiệu lực:

- Trả Mono/Flux từ controller/service.
- Dùng các operator ghép publisher như map, flatMap, concatMap và then.
- Không tự subscribe để chạy nền.
- Không collect toàn bộ DataBuffer vào List.
- Không gọi join trên toàn bộ file lớn.
- Không cache body stream nếu không có giới hạn và lý do rõ.

`collectList()`, `reduce` thành một mảng lớn hoặc `DataBufferUtils.join` toàn bộ body có thể biến streaming thành aggregation. Dùng chúng chỉ khi dữ liệu có giới hạn nhỏ và giới hạn đó được kiểm soát.

### 8.2. Release buffer đúng ownership

Một số server như Reactor Netty dùng pooled DataBuffer có reference count. Khi code tự nhận DataBuffer:

- Nếu tự tiêu thụ và không chuyển buffer cho writer khác, release sau khi đọc xong.
- Nếu chuyển publisher sang `DataBufferUtils.write(Path)`, overload này quản lý việc release buffer đã ghi.
- Nếu chuyển buffer sang `response.writeWith`, response writer tiếp nhận việc ghi và release theo contract; controller không release lần nữa.
- Nếu dùng overload `DataBufferUtils.write` nhận channel hoặc OutputStream, đọc contract vì có overload trả lại buffer và không tự release.
- Nếu buffer có thể bị discard do filter, skip, error hoặc cancellation, custom pipeline cần cleanup thích hợp, ví dụ `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở nơi phù hợp.

Không release hai lần và không dùng buffer sau khi đã release. Buffer ownership là trách nhiệm của code đã nhận hoặc chuyển quyền sở hữu.

### 8.3. Cancellation

Client có thể ngắt kết nối giữa chừng. Khi đó publisher có thể nhận cancellation; file đang ghi có thể dở dang.

Ứng dụng nên để cancellation truyền qua publisher chain, đóng channel/stream khi publisher kết thúc hoặc bị hủy, đánh dấu file chưa hoàn chỉnh hoặc ghi vào tên tạm, chỉ đổi tên sang file chính thức sau khi upload hoàn tất và checksum hợp lệ, dọn file dở dang bằng cleanup logic hoặc scheduled maintenance, và không đánh dấu metadata file là ready trước khi ghi xong.

Một pattern an toàn là ghi vào file có hậu tố tạm, xác minh kích thước/checksum, sau đó move/rename sang vị trí chính thức. Nếu cần atomic move, kiểm tra filesystem có hỗ trợ và source/destination cùng filesystem.

## 9. Kiểm chứng nội dung mà không đọc toàn bộ file vào RAM

### 9.1. Kích thước

Sau khi upload hoàn tất, dùng `Files.size(path)` để lấy số byte. Kích thước nên được so sánh với Content-Length hoặc metadata client gửi, nhưng không tin giá trị client nếu chưa kiểm tra thực tế.

### 9.2. Checksum

Tính SHA-256 theo chunk bằng `MessageDigest.update(byte[], offset, length)` hoặc `update(ByteBuffer)`. Với download stream, cập nhật digest từng DataBuffer rồi release buffer ngay.

### 9.3. So sánh nguồn và đích

Đối với một transfer test:

1. Tạo file nguồn bằng cách ghi từng block nhỏ.
2. Tính SHA-256 của file nguồn bằng stream.
3. Upload nguồn dưới dạng Resource.
4. So sánh kích thước và checksum trong receipt.
5. Download file đã lưu dưới dạng Flux<DataBuffer>.
6. Cộng số byte và cập nhật checksum trong lúc nhận từng buffer.
7. Release mỗi buffer ngay sau khi đọc.
8. So sánh byte count và checksum cuối cùng với nguồn.

Cách này kiểm tra nội dung đầu-cuối mà không cần giữ toàn bộ file nguồn hoặc response trong RAM. Nếu chỉ kiểm tra status 200/201, có thể bỏ sót file bị cắt ngắn hoặc hỏng nội dung.

### 9.4. Kiểm tra response headers

Download test nên xác minh status 200 với file tồn tại, Content-Type đúng, Content-Length khớp kích thước thực, Content-Disposition phù hợp nếu API yêu cầu attachment, status 404 với ID không tồn tại và nếu hỗ trợ Range thì test 206, Content-Range và số byte trả về.

## 10. Ví dụ Java 17 chạy được: upload và download file lớn

Ví dụ dùng Java 17, Spring Boot 3.3.5 và WebFlux. File được lưu vào thư mục tạm riêng của demo; production nên dùng storage có quota, quyền truy cập và lifecycle rõ ràng.

### 10.1. Cấu trúc dự án

~~~text
large-file-demo/
├── build.gradle
├── src/main/resources/application.properties
├── src/main/java/demo/LargeFileApplication.java
├── src/main/java/demo/FileController.java
└── src/test/java/demo/FileTransferTest.java
~~~

### 10.2. build.gradle

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 10.3. application.properties

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=10
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=./var/multipart-tmp
~~~

### 10.4. LargeFileApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LargeFileApplication {

    public static void main(String[] args) {
        SpringApplication.run(LargeFileApplication.class, args);
    }
}
~~~

### 10.5. FileController.java

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

record UploadReceipt(UUID id, long sizeBytes, String sha256) {}

@RestController
@RequestMapping("/api/files")
class FileController {

    static final Path STORAGE_DIR = Path.of(
        System.getProperty("java.io.tmpdir"),
        "webflux-large-file-demo"
    );

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        UUID id = UUID.randomUUID();
        Path destination = STORAGE_DIR.resolve(id + ".bin");

        return Mono.fromCallable(() -> Files.createDirectories(STORAGE_DIR))
            .subscribeOn(Schedulers.boundedElastic())
            .then(file.transferTo(destination))
            .then(Mono.fromCallable(() -> {
                long size = Files.size(destination);
                String hash = sha256(destination);
                return new UploadReceipt(id, size, hash);
            }).subscribeOn(Schedulers.boundedElastic()))
            .map(receipt -> ResponseEntity
                .created(URI.create("/api/files/" + id))
                .body(receipt));
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<Resource>> download(
            @PathVariable UUID id) {

        Path path = STORAGE_DIR.resolve(id + ".bin");

        return Mono.fromCallable(() -> {
            if (!Files.isRegularFile(path)) {
                return ResponseEntity.<Resource>notFound().build();
            }

            Resource resource = new FileSystemResource(path);

            return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(path))
                .header(
                    HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                        .filename(id + ".bin")
                        .build()
                        .toString()
                )
                .body(resource);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private static String sha256(Path path) throws IOException {
        final MessageDigest digest;

        try {
            digest = MessageDigest.getInstance("SHA-256");
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }

        try (InputStream input = Files.newInputStream(path)) {
            byte[] chunk = new byte[64 * 1024];
            int read;

            while ((read = input.read(chunk)) != -1) {
                digest.update(chunk, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Những điểm quan trọng trong controller:

- ID được tạo bởi server; filename client không được dùng làm đường dẫn.
- `FilePart.transferTo` ghi file mà không tạo một byte array bằng kích thước file.
- `Files.size` và việc tính SHA-256 là blocking file I/O, nên chạy trên boundedElastic.
- `FileSystemResource` được trả cho writer; WebFlux đọc file theo luồng.
- Receipt chứa kích thước và checksum để client/test xác minh.
- Demo chưa triển khai database, antivirus scan, authorization hoặc cleanup file lỗi; bổ sung các bước đó theo chính sách lưu trữ thực tế.

### 10.6. FileTransferTest.java

Test sau tạo file nguồn 8 MiB bằng buffer 64 KiB, gửi nó dưới dạng FileSystemResource, rồi nhận response download thành từng DataBuffer. Test chỉ cộng số byte và tính digest; không dùng `expectBody(byte[].class)` để gom response.

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FileTransferTest {

    @Autowired
    WebTestClient client;

    @Test
    void uploadsAndDownloadsLargeFileAsAStream() throws Exception {
        Path source = Files.createTempFile("large-source-", ".bin");
        UUID uploadedId = null;

        try {
            long expectedSize = createLargeFile(source, 8L * 1024 * 1024);
            String expectedHash = sha256(source);

            UploadReceipt receipt = client.post()
                .uri("/api/files")
                .body(BodyInserters.fromMultipartData(
                    "file",
                    new FileSystemResource(source)
                ))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(UploadReceipt.class)
                .returnResult()
                .getResponseBody();

            assertNotNull(receipt);
            uploadedId = receipt.id();

            assertEquals(expectedSize, receipt.sizeBytes());
            assertEquals(expectedHash, receipt.sha256());

            FluxExchangeResult<DataBuffer> download = client.get()
                .uri("/api/files/{id}", uploadedId)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.APPLICATION_OCTET_STREAM
                    )
                .expectHeader()
                    .contentLength(expectedSize)
                .returnResult(DataBuffer.class);

            MessageDigest downloadedDigest =
                MessageDigest.getInstance("SHA-256");

            Mono<Long> downloadedBytes = download.getResponseBody()
                .map(buffer -> {
                    try {
                        int count = buffer.readableByteCount();
                        ByteBuffer view = buffer.asByteBuffer();
                        downloadedDigest.update(view);
                        return (long) count;
                    }
                    finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .reduce(0L, Long::sum);

            StepVerifier.create(downloadedBytes)
                .expectNext(expectedSize)
                .verifyComplete();

            String downloadedHash =
                HexFormat.of().formatHex(downloadedDigest.digest());

            assertEquals(expectedHash, downloadedHash);
        }
        finally {
            Files.deleteIfExists(source);

            if (uploadedId != null) {
                Files.deleteIfExists(
                    FileController.STORAGE_DIR.resolve(uploadedId + ".bin")
                );
            }
        }
    }

    private static long createLargeFile(Path path, long size)
            throws IOException {

        byte[] chunk = new byte[64 * 1024];

        for (int i = 0; i < chunk.length; i++) {
            chunk[i] = (byte) (i % 251);
        }

        try (OutputStream output = Files.newOutputStream(path)) {
            long written = 0;

            while (written < size) {
                int count = (int) Math.min(
                    chunk.length, size - written
                );
                output.write(chunk, 0, count);
                written += count;
            }
        }

        return size;
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] chunk = new byte[64 * 1024];
            int read;

            while ((read = input.read(chunk)) != -1) {
                digest.update(chunk, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Test không lưu response vào byte array. Mỗi DataBuffer được đếm, đưa vào SHA-256 rồi release ngay. `StepVerifier` xác nhận tổng byte bằng kích thước nguồn và checksum cuối cùng khớp. Upload source là Resource trên disk, không phải byte array 8 MiB.

### 10.7. Chạy ứng dụng và test

Chạy test:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Chạy server:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Ví dụ test trên kiểm tra đường đi dữ liệu và tính toàn vẹn. Nó không tự chứng minh một giới hạn heap tuyệt đối; để đo memory thực tế, cần chạy tải đồng thời với file lớn và quan sát heap/direct memory.

## 11. Kiểm thử với WebTestClient mà không vô tình aggregate

### 11.1. Tránh expectBody(byte[])

Cách này gom response vào bộ nhớ:

~~~java
.expectBody(byte[].class)
~~~

Nó phù hợp với response nhỏ, nhưng không phải cách kiểm thử download nhiều gigabyte.

Thay vào đó, nhận stream:

~~~java
FluxExchangeResult<DataBuffer> result =
    client.get()
        .uri("/api/files/{id}", id)
        .exchange()
        .expectStatus().isOk()
        .returnResult(DataBuffer.class);
~~~

Sau đó consume từng buffer, tính số byte/checksum và release buffer.

### 11.2. Kiểm tra upload bằng Resource

Dùng `FileSystemResource` trong multipart inserter. Tránh `Files.readAllBytes(sourcePath)` và `bodyValue(byteArray)` trong test file lớn vì chính test client sẽ tạo một mảng lớn.

### 11.3. Kiểm tra cancellation và lỗi

Bên cạnh happy path, nên có test cho file ID không tồn tại, client hủy download giữa chừng, upload vượt giới hạn disk/part, multipart thiếu file, file ghi lỗi hoặc disk hết dung lượng, checksum không khớp và filename traversal.

Khi test cancellation, xác minh file tạm hoặc file đích dở dang được đánh dấu/xóa đúng chính sách. Đừng để một test chỉ assert status mà bỏ qua tài nguyên còn sót lại.

## 12. Đo và quan sát memory khi chạy tải lớn

Một bài test chức năng không đủ để kết luận ứng dụng dùng ít RAM dưới tải. Để kiểm chứng memory envelope:

1. Tạo file ở nhiều kích thước, ví dụ 100 MiB, 1 GiB và mức gần giới hạn nghiệp vụ.
2. Chạy nhiều upload/download đồng thời, không chỉ một request.
3. Đo heap usage và GC bằng JFR hoặc Java Flight Recorder.
4. Theo dõi direct memory nếu dùng Reactor Netty pooled buffers.
5. Theo dõi disk usage, file descriptor, tốc độ ghi và thời gian request.
6. Kiểm tra memory sau khi client hủy request và sau khi mọi request hoàn tất.
7. So sánh mức tăng memory theo số request đồng thời, không chỉ theo kích thước file.
8. Bật Netty leak detection trong môi trường test khi cần tìm DataBuffer leak; chế độ chi tiết có chi phí hiệu năng.

Nếu memory tăng gần tỷ lệ với kích thước file, tìm các điểm aggregation như byte[], collectList, join, cache hoặc bodyToMono. Nếu memory tăng theo concurrency, kiểm tra prefetch, queue, buffer size, số transfer đồng thời và các publisher được giữ lại.

## 13. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Files.readAllBytes` cho upload/download | Toàn bộ file được đưa vào heap | Dùng FilePart, Resource hoặc DataBuffer stream |
| Dùng `@RequestBody byte[]` cho file lớn | Request body bị aggregate thành một mảng | Dùng `FilePart` hoặc `Flux<DataBuffer>` |
| Dùng `expectBody(byte[].class)` trong test download lớn | Test tự gom toàn bộ response vào RAM | Dùng `returnResult(DataBuffer.class)` và consume từng buffer |
| Dùng `collectList()` trên DataBuffer | Giữ nhiều buffer cho đến khi stream kết thúc | Xử lý từng buffer và release ngay |
| Dùng `DataBufferUtils.join` cho file không giới hạn | Gom body thành một buffer lớn | Dùng `DataBufferUtils.write` hoặc Resource |
| Dùng filename client làm path | Path traversal hoặc ghi đè file | Tạo ID/path từ server |
| Không giới hạn disk usage | Upload đồng thời có thể làm đầy disk | Đặt maxDiskUsagePerPart, quota và cleanup |
| Chỉ cấu hình maxInMemorySize rồi nghĩ đã giới hạn tổng file | File part lớn vẫn có thể được spool xuống disk | Đặt giới hạn disk, request và nghiệp vụ riêng |
| Trả byte[] thay vì Resource | Server phải giữ toàn bộ file trong heap | Trả FileSystemResource hoặc Flux<DataBuffer> |
| Gọi block/subscribe trong controller | Chặn event-loop hoặc tách lifecycle request | Ghép publisher và trả về |
| Release DataBuffer hai lần | IllegalReferenceCountException hoặc buffer đã giải phóng | Theo dõi ownership; không release sau khi handoff |
| Quên release buffer khi tự xử lý | Direct memory leak | Release sau khi đọc; dùng doOnDiscard khi phù hợp |
| Không xử lý cancellation | File dở dang hoặc tài nguyên bị giữ | Cleanup trong lifecycle và dùng file tạm |
| Chỉ kiểm tra status 201/200 | Không phát hiện file bị cắt/hỏng | Kiểm tra kích thước và checksum |
| Chỉ test một request | Không phát hiện áp lực concurrency | Chạy load test và đo heap/direct memory |
| Dùng FilePart khi cần xử lý multipart tuần tự | Parser có thể cần xử lý collection/part metadata trước | Dùng `Flux<PartEvent>` khi cần streaming từng part |
| Dùng WebClient bodyToMono cho file lớn | Client aggregate response | Dùng bodyToFlux(DataBuffer.class) và ghi xuống disk |

## 14. Checklist triển khai upload/download lớn

Trước khi đưa endpoint vào production, kiểm tra:

1. **Đường đi dữ liệu:** từ request đến disk và từ disk đến response có giữ dạng stream không?
2. **API:** FilePart, PartEvent, Flux<DataBuffer> hoặc Resource có phù hợp không?
3. **Aggregation:** có byte[], readAllBytes, collectList, join hoặc bodyToMono nào giữ toàn bộ file không?
4. **Buffer:** kích thước chunk và số buffer đang chờ có giới hạn không?
5. **Ownership:** buffer được consume, release hoặc chuyển cho writer đúng một lần chưa?
6. **Backpressure:** downstream chậm có làm upstream phát dữ liệu vô hạn không?
7. **Disk:** multipart temp directory, quota, dung lượng trống và cleanup đã được cấu hình chưa?
8. **Security:** filename, content type, extension, authorization, virus scan và path traversal đã được xử lý chưa?
9. **Integrity:** size và checksum có được xác minh trước khi đánh dấu file hoàn tất không?
10. **Cancellation:** client ngắt giữa chừng có đóng stream và dọn file dở dang không?
11. **Download headers:** Content-Type, Content-Length, Content-Disposition và Range có đúng hợp đồng không?
12. **Tests:** WebTestClient có upload bằng Resource và consume response theo DataBuffer không?
13. **Load:** đã thử file lớn và nhiều request đồng thời, theo dõi heap/direct memory/disk chưa?
14. **Operations:** có metrics, log không chứa dữ liệu nhạy cảm, cảnh báo disk và cơ chế cleanup không?

**Ghi nhớ:** một transfer thực sự streaming không giữ toàn bộ file trong một object Java. Dùng `FilePart.transferTo` cho multipart đơn giản, `PartEvent` khi cần xử lý multipart tuần tự, `Flux<DataBuffer>` cho raw byte stream và `Resource`/`DataBufferUtils.read` cho download. Kiểm chứng bằng kích thước và checksum theo chunk; trong test, consume từng DataBuffer và release ngay. Giới hạn memory, disk, concurrency và thời gian request là các phần riêng của cùng một thiết kế.

## Tài liệu tham khảo

- Spring Framework — Multipart Content and PartEvent: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework — Reactive Core, Multipart Limits and DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — DataBufferUtils API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Boot — Common Application Properties, WebFlux Multipart: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Framework — WebClient Request Body and Multipart Streaming: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
