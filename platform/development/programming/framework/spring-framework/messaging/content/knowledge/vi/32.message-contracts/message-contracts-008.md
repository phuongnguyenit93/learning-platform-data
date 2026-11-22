# Giới hạn kích thước và truyền tham chiếu thay cho dữ liệu lớn

> Phạm vi: thiết kế payload RSocket có giới hạn, hiểu frame size và fragmentation, truyền dữ liệu theo stream có backpressure, và dùng object reference để chuyển các tệp lớn qua object storage.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt kích thước frame, payload của một message và tổng dữ liệu của một stream.
- Giải thích giới hạn frame 24-bit của RSocket và vai trò của fragmentation/reassembly.
- Cấu hình ngưỡng fragment và giới hạn payload được reassemble trong RSocket Java.
- Dùng `Flux` và `RSocketRequester.data(Publisher)` để truyền nhiều chunk có backpressure.
- Chọn thời điểm gửi dữ liệu trực tiếp, truyền stream hay gửi reference tới object storage.
- Thiết kế upload/download lớn bằng upload intent, signed URL, multipart và xác minh checksum.
- Kiểm thử kích thước, bộ nhớ, timeout, hủy stream và quyền truy cập object.

## 2. Phân biệt frame, message và stream

Trong RSocket, ba khái niệm này có liên quan nhưng không đồng nghĩa:

- **Frame** là đơn vị dữ liệu trên wire. Frame có header, loại frame, flags và có thể có metadata/data.
- **Message/payload logic** là nội dung ứng dụng gửi trong một request hoặc một lần phát `onNext`. Một payload logic có thể cần nhiều frame nếu bị fragment.
- **Stream** là chuỗi sự kiện của một interaction. Ví dụ `REQUEST_STREAM` tạo một request ban đầu và sau đó responder gửi nhiều payload; `REQUEST_CHANNEL` cho phép hai phía gửi các payload theo stream.

Một request-response có thể mang một payload đơn lớn. RSocket có thể chia payload đó thành nhiều frame ở tầng giao thức, sau đó ghép lại trước khi ứng dụng nhận được payload hoàn chỉnh. Vì vậy, fragmentation không tự biến một message lớn thành một stream ứng dụng gồm nhiều phần độc lập.

Khi thiết kế giới hạn kích thước, cần hỏi rõ đang giới hạn:

1. Kích thước tối đa của một frame trên transport.
2. Kích thước tối đa của một payload logic sau khi reassembly.
3. Kích thước mỗi phần tử trong stream ứng dụng.
4. Tổng dung lượng hoặc thời gian của toàn bộ upload/download.

Các giới hạn này cần phối hợp với nhau. Giới hạn frame thấp không tự giới hạn tổng kích thước của một message đã được chia nhỏ; giới hạn số phần tử stream cũng không tự giới hạn số byte nếu từng phần tử có thể lớn tùy ý.

## 3. Giới hạn frame của RSocket

### 3.1. Giới hạn giao thức

RSocket định nghĩa trường Frame Length 24-bit cho transport cần đóng khung dữ liệu. Giá trị unsigned lớn nhất là `16,777,215` byte. Theo protocol specification, toàn bộ RSocket frame gồm header và payload không được vượt quá `16,777,215` byte, kể cả khi transport tự bảo toàn ranh giới message và không cần trường Frame Length.

Trên TCP, Frame Length được thêm phía trước frame và bản thân trường prefix không được tính vào độ dài frame. WebSocket đã bảo toàn ranh giới message nên không cần prefix này. Quy tắc đóng khung của transport không làm thay đổi giới hạn tối đa của RSocket frame.

Đây là giới hạn giao thức, không phải kích thước payload ứng dụng nên nhắm tới. Header, metadata, encoding và các giới hạn của transport hoặc proxy đều chiếm ngân sách. Một hệ thống có thể đặt giới hạn thấp hơn đáng kể để kiểm soát bộ nhớ và độ trễ.

### 3.2. Giới hạn thực tế của hệ thống

Kích thước có thể bị giới hạn ở nhiều lớp:

| Lớp | Ví dụ giới hạn cần kiểm tra |
| --- | --- |
| RSocket protocol | Frame tối đa 16,777,215 byte |
| RSocket Java | Transport max frame length, fragment MTU, max inbound reassembled payload |
| WebSocket transport | Max frame/message payload của WebSocket server, client hoặc proxy |
| Network edge | Load balancer, ingress, gateway, firewall và timeout |
| Serialization | Kích thước sau encode; JSON/base64 có thể làm dữ liệu phình lên |
| Ứng dụng | Dung lượng file cho phép, quota tenant, số chunk, thời gian xử lý và bộ nhớ |

Không giả định mọi thành phần đều dùng cùng một giới hạn. Kiểm tra cấu hình ở cả requester, responder, transport và hạ tầng trung gian. Nếu một proxy giới hạn WebSocket message ở 64 KiB, việc RSocket protocol cho phép frame lớn hơn không giúp request đi qua proxy đó.

### 3.3. Kích thước sau serialization

Giới hạn cần tính trên dữ liệu thực tế được encode, không chỉ trên kích thước object Java hoặc file gốc. Ví dụ:

- JSON có thể thêm tên field, dấu phân cách và escape.
- Mã hóa binary thành Base64 làm tăng số byte so với dữ liệu gốc.
- Composite metadata, route và authentication metadata cũng chiếm chỗ.
- Compression có thể giảm byte truyền nhưng vẫn cần CPU và bộ nhớ để nén/giải nén.

Không dùng compression để thay thế giới hạn kích thước. Cần giới hạn cả dữ liệu đã giải nén và chú ý các payload nén có tỷ lệ mở rộng bất thường.

## 4. Fragmentation và reassembly

### 4.1. Cách hoạt động

Protocol cho phép fragment các `REQUEST_*` frame và `PAYLOAD` frame khi nội dung không vừa kích thước frame mục tiêu. Flag `F` (Follows) cho biết còn fragment tiếp theo. Với request bị fragment, frame request ban đầu được gửi trước, sau đó các fragment tiếp theo được truyền bằng `PAYLOAD` frame. Metadata phải được truyền hoàn tất trước phần data.

Sau khi nhận đủ fragment, implementation reassemble chúng thành payload logic và chuyển cho tầng xử lý. Các fragment của cùng một payload không được tính thành nhiều message demand riêng: một payload đã fragment vẫn tương ứng một phần tử theo flow-control của stream.

### 4.2. Fragmentation không phải streaming ở tầng ứng dụng

Giả sử ứng dụng gửi một `byte[]` 40 MB trong một request-response. Với fragmentation, RSocket có thể truyền nội dung đó bằng nhiều frame nhỏ hơn. Nhưng phía nhận vẫn cần reassemble payload logic 40 MB trước khi handler xử lý nó.

Điều này có thể gây:

- Tăng bộ nhớ đỉnh do nhiều fragment và payload đã reassemble cùng tồn tại trong quá trình xử lý.
- Tăng thời gian chờ trước khi handler bắt đầu làm việc.
- Tăng áp lực GC nếu payload được copy nhiều lần.
- Tăng nguy cơ một request đơn lẻ chiếm phần lớn ngân sách bộ nhớ.

Fragmentation hữu ích để phù hợp MTU hoặc giới hạn frame của transport. Nó không thay thế streaming khi dữ liệu lớn cần được xử lý tăng dần.

### 4.3. Cấu hình fragmentation trong RSocket Java

`RSocketConnector.fragment(mtu)` đặt ngưỡng MTU để frame lớn hơn được chia thành fragment. `RSocketServer.fragment(mtu)` cung cấp cấu hình tương ứng ở server. Trong Spring Boot với standalone RSocket server, thuộc tính `spring.rsocket.server.fragment-size` cấu hình kích thước fragment ở phía server.

Ví dụ cấu hình requester:

```java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.fragment(64 * 1024))
        .tcp("localhost", 9898);
```

Ví dụ cấu hình standalone server trong Spring Boot:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
      fragment-size: 64KB
```

Các giá trị `64 KiB` ở trên chỉ là ví dụ cấu hình, không phải giá trị bắt buộc hay tối ưu cho mọi môi trường. Chọn MTU theo transport, proxy, latency, throughput và kết quả đo thực tế. Hai phía cần tương thích với giới hạn frame mà mỗi phía có thể nhận.

### 4.4. Giới hạn payload sau reassembly

RSocket Java cung cấp `maxInboundPayloadSize(...)` trên `RSocketConnector` và `RSocketServer` để giới hạn kích thước payload sau khi reassemble. Nếu không cấu hình, mức giới hạn reassembled payload có thể không được kiểm soát bởi tùy chọn này.

Có một ràng buộc quan trọng: `maxInboundPayloadSize` phải lớn hơn hoặc bằng `Transport.maxFrameLength()`, vì một frame đơn lẻ đã có thể vượt ngưỡng reassembly nếu cấu hình nhỏ hơn giới hạn frame transport.

Ví dụ khi tự tạo RSocket server:

```java
RSocketServer.create(acceptor)
        .fragment(64 * 1024)
        .maxInboundPayloadSize(32 * 1024 * 1024)
        .bind(transport);
```

Con số 32 MiB chỉ minh họa cho một policy cụ thể và phải được đối chiếu với `Transport.maxFrameLength()` của transport đang dùng. Đừng sao chép giá trị này mà không kiểm tra frame limit. Ở production, đặt ngưỡng đủ lớn cho frame đơn nhưng vẫn giới hạn tổng payload reassembled theo ngân sách bộ nhớ.

### 4.5. Khi nào dùng fragmentation?

Dùng fragmentation khi một payload đơn có kích thước hữu hạn, đã được giới hạn rõ và cần đi qua transport có MTU nhỏ hơn payload đó. Không dùng fragmentation như giải pháp mặc định cho file rất lớn hoặc dữ liệu có kích thước không dự đoán được.

## 5. Streaming dữ liệu theo chunk

### 5.1. Backpressure của RSocket

RSocket triển khai Reactive Streams semantics qua network. Với `REQUEST_STREAM` và `REQUEST_CHANNEL`, requester gửi demand; responder chỉ nên phát số phần tử mà phía nhận đã yêu cầu. Demand được thể hiện bằng số message, không phải tổng số byte.

Do đó, backpressure chỉ kiểm soát tốt bộ nhớ khi mỗi phần tử stream cũng có kích thước được giới hạn. Một stream gồm 10 phần tử, mỗi phần tử 100 MB, vẫn có thể gây áp lực bộ nhớ rất lớn.

Chọn chunk size cố định hoặc giới hạn trên cho từng phần tử. Kích thước bắt đầu từ 64–256 KiB có thể là điểm thử nghiệm trong một số hệ thống, nhưng cần benchmark với payload thực, số kết nối đồng thời, latency và throughput. Đây là gợi ý đo thử, không phải giới hạn của protocol.

### 5.2. Chọn interaction type

| Interaction | Mẫu sử dụng |
| --- | --- |
| Request-Response | Gửi metadata hoặc một request nhỏ, nhận một kết quả |
| Request-Stream | Gửi một yêu cầu nhỏ, nhận nhiều chunk hoặc record |
| Request-Channel | Gửi nhiều chunk và đồng thời nhận ACK/progress hoặc kết quả theo stream |
| Fire-and-Forget | Gửi một thông báo nhỏ, không cần response nghiệp vụ |

Đối với download, `REQUEST_STREAM` phù hợp khi client gửi một request có object id rồi server phát nhiều chunk. Đối với upload cần ACK hoặc progress, `REQUEST_CHANNEL` cho phép client gửi chunk và server phát phản hồi tương ứng. Nếu upload chỉ cần một kết quả cuối, thiết kế interaction phải phù hợp với cardinality mà Spring RSocket hỗ trợ; không gom toàn bộ input stream thành một object lớn chỉ để trả một response.

### 5.3. Gửi stream bằng RSocketRequester

`RSocketRequester.RequestSpec.data(Object)` nhận một Reactive Streams `Publisher`, bao gồm `Flux` và `Mono`. Với publisher nhiều phần tử, có thể chỉ rõ kiểu phần tử bằng overload `data(publisher, elementClass)` để tránh phải suy luận kiểu cho từng phần tử.

Ví dụ client gửi các `ByteBuffer` theo từng chunk và nhận ACK stream:

```java
Flux<ByteBuffer> chunks = readFileInChunks(path, 128 * 1024);

Flux<UploadAck> acknowledgements = requester
        .route("asset.upload.{uploadId}", uploadId)
        .data(chunks, ByteBuffer.class)
        .retrieveFlux(UploadAck.class);
```

`readFileInChunks` đại diện cho publisher đọc file theo từng buffer có kích thước giới hạn. Publisher phải đọc tăng dần, không gọi `Files.readAllBytes` rồi mới tạo `Flux`. Các `ByteBuffer` được phát phải giữ nguyên nội dung cho tới khi encoder hoàn tất xử lý.

Responder có thể nhận một stream chunk và xử lý tuần tự:

```java
record UploadAck(long sequence, String status) {}

@MessageMapping("asset.upload.{uploadId}")
Flux<UploadAck> upload(
        @DestinationVariable String uploadId,
        Flux<ByteBuffer> chunks) {

    return chunks.index()
            .concatMap(indexed ->
                    storage.append(uploadId, indexed.getT1(), indexed.getT2())
                            .thenReturn(new UploadAck(indexed.getT1(), "stored")));
}
```

Đây là ví dụ minh họa contract; `storage.append(...)` là API lưu từng chunk của ứng dụng. `concatMap` xử lý tuần tự để giữ thứ tự chunk và giới hạn số thao tác ghi đồng thời. Nếu dùng `flatMap`, hãy đặt concurrency và prefetch có giới hạn, đồng thời bảo đảm storage layer hỗ trợ ghi song song đúng cách.

Với `UploadAck`, hai phía cần có codec phù hợp trong `RSocketStrategies`. `ByteBuffer` được hỗ trợ bởi các codec cơ bản; kiểu record cần codec tương ứng, ví dụ JSON, CBOR hoặc Protobuf. Không serialize byte array thành Base64 JSON nếu mục tiêu là truyền binary hiệu quả.

### 5.4. Stream download

Một download có thể được biểu diễn thành nhiều buffer:

```java
Flux<ByteBuffer> fileChunks = requester
        .route("asset.download.{assetId}", assetId)
        .retrieveFlux(ByteBuffer.class);
```

Phía server phát từng buffer từ file/object stream. Phía client ghi từng buffer ra file hoặc storage đích. Tránh `.collectList()`, `.reduce(...)` thành một mảng byte khổng lồ hoặc giữ tất cả chunk trong bộ nhớ trước khi ghi.

Nếu client chỉ cần file, có thể tải trực tiếp từ object storage bằng signed URL thay vì đưa toàn bộ bytes qua service RSocket. RSocket vẫn có thể trả trạng thái, metadata hoặc ticket download.

### 5.5. Những điều cần kiểm soát khi streaming

- Giới hạn kích thước mỗi chunk và số chunk tối đa.
- Giới hạn số thao tác ghi đồng thời và prefetch.
- Dùng backpressure thật; tránh chuyển sang unbounded queue hoặc buffer toàn bộ stream.
- Hủy stream khi client ngắt kết nối hoặc upload session hết hạn.
- Ghi nhận sequence number để phát hiện thiếu, trùng hoặc sai thứ tự chunk.
- Có checksum theo chunk hoặc checksum toàn object để phát hiện dữ liệu lỗi.
- Có timeout và chính sách retry idempotent; retry một chunk phải không ghi trùng nội dung.
- Đóng file, channel và buffer đúng vòng đời; nếu dùng Netty reference-counted buffer/zero-copy, tuân thủ quy tắc release.

## 6. Truyền reference thay cho dữ liệu lớn

### 6.1. Tách control plane và data plane

Với file lớn, cách thường hiệu quả hơn là dùng RSocket cho điều khiển và object storage cho dữ liệu:

- **Control plane qua RSocket:** tạo upload session, kiểm tra quyền, trả thông tin upload, thông báo hoàn tất, truy vấn trạng thái và cấp quyền download.
- **Data plane qua object storage:** truyền bytes trực tiếp tới S3-compatible storage, Google Cloud Storage, Azure Blob Storage hoặc dịch vụ lưu trữ tương đương.

Service không cần nhận rồi chuyển tiếp toàn bộ file nếu không có yêu cầu xử lý bắt buộc. Cách này giảm memory copy, CPU, network hop và tải trên service RSocket.

### 6.2. Reference nên chứa gì?

Một reference nội bộ có thể mô tả object mà không mang nội dung file:

```java
public record AssetReference(
        String assetId,
        String version,
        long sizeBytes,
        String mediaType,
        String sha256) {}
```

`assetId` là định danh opaque do server quản lý. `version` giúp tham chiếu một phiên bản bất biến. `sizeBytes`, `mediaType` và `sha256` hỗ trợ kiểm tra contract. Không nhất thiết đưa bucket name hoặc storage key nội bộ vào reference công khai.

Một reference không nên được xem là quyền truy cập. Khi nhận `assetId`, server vẫn phải xác minh principal, tenant, trạng thái object và quyền đọc/ghi. Không tin `sizeBytes`, `mediaType` hay checksum do client khai báo nếu chưa đối chiếu với object thực tế.

### 6.3. Quy trình upload qua signed URL

Một luồng upload phổ biến:

1. Client gửi RSocket request `asset.upload.prepare` với tên file, kích thước dự kiến, media type và checksum nếu đã có.
2. Server xác thực người dùng, kiểm tra quota/tenant, áp dụng giới hạn file và tạo upload session.
3. Server tạo signed URL hoặc multipart upload grant giới hạn vào đúng object key, đúng HTTP method và thời gian ngắn; trả URL cùng upload id và các yêu cầu header.
4. Client upload bytes trực tiếp qua HTTPS tới object storage. Với file lớn, dùng multipart/resumable upload để có thể tiếp tục các phần chưa hoàn tất.
5. Client gửi RSocket request `asset.upload.complete` với upload id, part etags hoặc checksum cần thiết.
6. Server kiểm tra trạng thái object ở storage, kích thước thực, checksum, owner/tenant và các bước kiểm tra nội dung như malware scan nếu cần.
7. Khi xác minh thành công, server đánh dấu object sẵn sàng và trả `AssetReference`.

Ví dụ contract điều khiển:

```java
record UploadPrepare(String fileName, long sizeBytes, String mediaType) {}
record UploadGrant(String uploadId, URI uploadUri, Instant expiresAt) {}
record UploadComplete(String uploadId, String checksum) {}

Mono<UploadGrant> grant = requester
        .route("asset.upload.prepare")
        .data(new UploadPrepare(fileName, sizeBytes, mediaType))
        .retrieveMono(UploadGrant.class);
```

`uploadUri` là capability có thể cấp quyền ghi trong phạm vi hẹp. Người sở hữu URL có thể dùng quyền đó cho tới khi URL hết hạn hoặc bị vô hiệu hóa theo khả năng của storage provider. Không ghi URL đầy đủ vào log, analytics hoặc exception. Chỉ cấp quyền cho một object/method cụ thể và thời gian ngắn; dùng multipart grant nếu upload chia phần.

Không nhận một URL tùy ý từ client rồi để backend tải về mà không kiểm tra. Nếu backend cần fetch URL do người dùng cung cấp, phải có chính sách chống SSRF: allowlist scheme/host, chặn địa chỉ private/link-local/metadata service, kiểm soát redirect và giới hạn byte/time.

### 6.4. Quy trình download

1. Client gửi `asset.download.prepare` với `assetId` và phiên bản mong muốn.
2. Server kiểm tra quyền đọc, tenant, trạng thái object và retention policy.
3. Server tạo signed URL chỉ có quyền GET, đúng object/version và thời hạn ngắn.
4. Client tải trực tiếp từ storage qua HTTPS và ghi xuống đĩa theo stream.

Nếu cần watermark, giải mã, biến đổi hoặc lọc dữ liệu trước khi trả, service có thể stream object từ storage qua pipeline xử lý rồi phát chunk qua RSocket. Khi đó vẫn cần backpressure, giới hạn kích thước và timeout.

### 6.5. Bảo vệ object reference

Một `assetId` khó đoán không thay thế authorization. Hãy:

- Kiểm tra quyền truy cập ở mỗi lần tạo signed URL.
- Gắn object với tenant/owner trong database và kiểm tra quan hệ đó.
- Dùng signed URL có TTL ngắn, method và object scope cụ thể.
- Không coi signed URL là URL công khai hoặc lưu nó như định danh bền vững.
- Lưu object key ở server-side; client chỉ cần opaque id.
- Xác minh kích thước, checksum và version trước khi đánh dấu upload hoàn tất.
- Có lifecycle rule cho upload dang dở, multipart chưa hoàn tất và object hết hạn.
- Bảo vệ object bằng encryption at rest và quyền storage tối thiểu.
- Xác thực media type từ nội dung thực khi phù hợp; không chỉ tin file extension.

## 7. Chọn chiến lược phù hợp

| Trường hợp | Cách truyền đề xuất | Lý do |
| --- | --- | --- |
| Metadata, command, object nhỏ có giới hạn | Inline trong một RSocket payload | Đơn giản, ít round trip |
| Một payload vừa phải nhưng lớn hơn frame MTU | Fragmentation có giới hạn | Vẫn là một message logic; không cần tự quản lý chunk |
| Dữ liệu sinh ra hoặc tiêu thụ tăng dần | `Flux` chunk qua Request-Stream/Channel | Backpressure giúp điều tiết tốc độ |
| File lớn, upload/download dài hoặc cần multipart/resume | Object storage + reference/signed URL | Tránh giữ file trong service RSocket và tận dụng khả năng lưu trữ |
| Dữ liệu cần xử lý trước khi lưu hoặc trả về | Stream qua service với bounded buffers | Service có thể kiểm tra/biến đổi mà không gom toàn bộ file vào RAM |

Một ngưỡng kích thước chung cho mọi ứng dụng không tồn tại. Hãy chọn inline limit dựa trên ngân sách bộ nhớ, concurrency, transport và latency. Một service có thể cho phép JSON request tối đa vài chục KiB, trong khi một pipeline khác chấp nhận stream chunk vài trăm KiB; đó là policy của hệ thống, không phải giới hạn mặc định của RSocket.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Frame bị từ chối hoặc connection đóng | Frame vượt giới hạn của protocol/transport | Đo kích thước frame sau encode; kiểm tra max frame của cả hai phía và proxy |
| Request nhỏ hoạt động, file lớn thất bại | Reassembled payload vượt giới hạn hoặc bộ nhớ không đủ | Kiểm tra fragment MTU và `maxInboundPayloadSize` |
| Fragment được truyền nhưng handler vẫn nhận một payload lớn | Nhầm fragmentation với application streaming | Chuyển sang `Flux` chunk hoặc object reference |
| WebSocket thất bại nhưng TCP thành công | WebSocket container/proxy có max message/frame nhỏ hơn | Kiểm tra WebSocket frame payload length và gateway limits |
| RAM tăng theo tổng file | Dùng `readAllBytes`, `collectList`, `join` hoặc buffer không giới hạn | Chuyển sang incremental read/write, giới hạn prefetch và concurrency |
| Upload bị lặp chunk sau retry | Thiếu sequence/idempotency key hoặc commit logic không idempotent | Ghi nhận upload id + chunk index/checksum và xử lý duplicate an toàn |
| File upload thành công nhưng server không nhận | Client không gọi complete hoặc server không kiểm tra object state | Dùng upload state machine và xác minh storage trước khi chuyển sang READY |
| Người dùng đọc được object của tenant khác | Dựa vào object id hoặc signed URL mà không kiểm tra owner | Kiểm tra tenant/owner trước khi phát signed URL |
| Signed URL hết hạn giữa upload | TTL ngắn hơn thời gian upload hoặc upload multipart không được gia hạn | Cấp URL theo part, gia hạn grant có xác thực hoặc tạo session mới |
| Checksum không khớp | Client/server tính trên representation khác nhau hoặc thiếu byte | Quy định rõ checksum trên bytes gốc, encoding và thuật toán |

## 9. Đo lường và kiểm thử

Theo dõi tối thiểu:

- Kích thước payload sau serialization và kích thước frame lớn nhất.
- Kích thước reassembled payload và số lần vượt giới hạn.
- Số fragment trung bình/tối đa trên một payload.
- Số chunk, kích thước chunk, throughput và thời gian upload/download.
- Số request đang chạy, concurrency ghi storage và queue depth.
- Heap usage, direct memory, GC pause và Netty buffer leak.
- Tỷ lệ upload thành công, multipart bị bỏ dở, checksum mismatch và retry.
- Số signed URL được phát, thời gian sống và lỗi authorization; không log URL bí mật.

Bộ kiểm thử nên bao gồm:

1. Payload nhỏ hơn inline limit được xử lý bình thường.
2. Payload ngay dưới và ngay trên giới hạn ứng dụng cho kết quả đúng.
3. Payload fragment qua nhiều frame được reassemble chính xác.
4. Payload reassembled vượt `maxInboundPayloadSize` bị từ chối có kiểm soát.
5. Request qua TCP và WebSocket được kiểm tra với giới hạn transport thực tế.
6. Stream nhiều chunk giữ đúng thứ tự và không vượt bộ nhớ khi consumer chậm.
7. Hủy stream giải phóng file handle, buffer và upload session.
8. Retry cùng chunk không tạo dữ liệu trùng hoặc sai thứ tự.
9. Upload multipart thiếu part hoặc checksum sai không được đánh dấu READY.
10. Signed URL hết hạn hoặc dùng sai method/object bị storage từ chối.
11. Người dùng/tenant không có quyền không thể lấy reference hoặc signed URL của object khác.
12. File vượt quota, số chunk tối đa hoặc thời gian upload bị từ chối theo policy.

Đừng chỉ kiểm thử một file mẫu nhỏ trên máy local. Hãy đo với số kết nối đồng thời và tốc độ mạng gần với môi trường triển khai.

## 10. Checklist thiết kế

- [ ] Đã phân biệt frame limit, payload reassembly limit và stream element limit.
- [ ] Đã đo kích thước sau serialization, bao gồm metadata.
- [ ] Inline payload có giới hạn nghiệp vụ cụ thể.
- [ ] Fragment MTU tương thích với transport và proxy.
- [ ] `maxInboundPayloadSize` được cấu hình và lớn hơn hoặc bằng `Transport.maxFrameLength()`.
- [ ] Payload lớn được stream theo chunk có kích thước giới hạn hoặc lưu ngoài RSocket.
- [ ] Stream có backpressure, concurrency và prefetch hữu hạn.
- [ ] Không gom toàn bộ file vào RAM bằng `readAllBytes`, `collectList` hoặc buffer vô hạn.
- [ ] Chunk có sequence/idempotency và checksum khi cần.
- [ ] Object reference dùng opaque id/version, không lộ storage key.
- [ ] Signed URL có method/object scope và TTL ngắn.
- [ ] Server kiểm tra quyền, quota, size, checksum và trạng thái object.
- [ ] Có lifecycle cleanup cho upload dang dở và multipart chưa hoàn tất.
- [ ] Có metric cho payload size, memory, throughput, retry và lỗi.

## 11. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, backpressure, `RSocketRequester`, `data(Publisher)` và codecs.
- [RSocket Protocol — Framing](https://github.com/rsocket/rsocket/blob/master/Protocol.md#framing): frame header và giới hạn frame 24-bit.
- [RSocket Protocol — Fragmentation and Reassembly](https://github.com/rsocket/rsocket/blob/master/Protocol.md#fragmentation-and-reassembly): flag `F`, thứ tự metadata/data và cách ghép fragment.
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): `fragment(mtu)`, `maxInboundPayloadSize` và payload decoder.
- [RSocket Java — RSocketServer API](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketServer.html): cấu hình fragmentation và giới hạn reassembled payload ở server.
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rsocket.server.fragment-size` và các thuộc tính RSocket server.

Các ngưỡng cụ thể phụ thuộc phiên bản RSocket Java, Spring Boot, transport và proxy. Kiểm tra Javadoc của dependency đang dùng trước khi triển khai cấu hình giới hạn.
