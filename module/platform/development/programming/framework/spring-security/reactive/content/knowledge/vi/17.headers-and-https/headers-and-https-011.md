# Giới hạn kích thước header, nội dung yêu cầu và tải tệp ở tầng WebFlux, máy chủ

> **Chủ đề cha:** Header và HTTPS trong **Spring Security reactive / Spring WebFlux**. Bài này phân biệt các giới hạn của **HTTP server**, **WebFlux codecs**, **multipart parser**, **application business rules** và **reverse proxy**. Mẫu chính dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring Security 6.x, Reactor Netty**. Một số tên property của Spring Boot **3.4 trở xuống** khác Boot 3.5; bài chỉ rõ thay đổi. Các hạn mức trong ví dụ phục vụ học tập, không mặc định là mức sản phẩm nên sử dụng.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt giới hạn **HTTP request line / headers**, **body bytes thực tế**, **dung lượng buffer để decode** và **một file/part multipart**.
2. Thiết lập `server.max-http-request-header-size` và `server.netty.max-initial-line-length` trong Spring Boot 3.5.
3. Dùng `spring.http.codecs.max-in-memory-size` để khống chế phần bộ nhớ codec có thể dùng khi gom dữ liệu; hiểu rằng đây **không phải giới hạn tổng kích thước của mọi HTTP body**.
4. Cấu hình `spring.webflux.multipart.max-in-memory-size`, `max-disk-usage-per-part`, `max-parts`, `max-headers-size` và hiểu từng ngưỡng.
5. Xây một POST endpoint giới hạn **số byte thật sự đọc** bằng `DataBufferUtils.join(Publisher<DataBuffer>, maxByteCount)`, trả `413 Payload Too Large` khi vượt ngưỡng và giải phóng `DataBuffer` đúng cách.
6. Xử lý upload `FilePart`, không dùng tên file từ client làm đường dẫn lưu, phân biệt temporary storage với final storage.
7. Hiểu vì sao `Content-Length` không đủ để chống body quá lớn, vì request có thể chunked, qua proxy hoặc kích thước byte sau giải mã khác header khai báo.
8. Giữ authentication/authorization/CSRF của **Spring Security WebFlux** hoạt động và kiểm thử giới hạn ứng dụng bằng `WebTestClient`.
9. Nhận diện status có thể gặp: `400`, `401`, `403`, `413`, `414`, `415`, `431`, `5xx` và tình huống server đóng kết nối trước khi WebFlux được gọi.
10. Thiết kế giới hạn nhiều lớp tại **TLS terminator, ingress/reverse proxy, server decoder, codec, multipart reader, service/storage quota** để chống quá tải/DoS.

## 2. Một từ “kích thước request” có nhiều nghĩa

Những giới hạn trong hệ thống WebFlux không thay thế nhau.

| Lớp | Ví dụ giới hạn | Đơn vị và tác động | Không bảo đảm |
| --- | --- | --- | --- |
| HTTP server decoder | Request line, header field length/size | Chặn request bất thường **trước** khi WebFlux controller nhận | Không hạn chế tổng body bytes |
| WebFlux codec | `max-in-memory-size` | Chặn việc **gom input vào buffer** vượt ngưỡng cho những codecs/readers có aggregation | Không phải quota chung cho file streaming hoặc mọi body |
| WebFlux multipart parser | Non-file part buffer, file spill threshold, disk per part, part count, part headers | Giới hạn tài nguyên lúc parse `multipart/form-data` | Không thay thế tổng multipart request limit trên mọi part |
| Application endpoint | MAX_RAW_BYTES, MAX_FILES, MAX_USER_QUOTA | Quy tắc kích thước tài nguyên **thực sự xử lý** | Không cứu server nếu parser/proxy hết tài nguyên từ trước |
| Ingress/reverse proxy | Request body, URL/header, connection/bandwidth/timeouts | Chặn sớm trước app, giảm chi phí upstream | Không bảo vệ business quota nếu cấu hình app sai |
| Security | Authentication, authorization, CSRF, rate limit | Ai được phép gửi và gửi với tần suất nào | Không tự giới hạn kích thước payload |
| Storage | Dung lượng file tổng, file count, thời gian lưu, disk quota | Tránh đầy ổ đĩa và quá chi phí | Không tự ngăn header quá lớn |

**Nguyên tắc cốt lõi:** Một request có thể có **header hợp lệ nhưng body rất lớn**, hoặc một file rất lớn được stream **không làm đầy codec buffer** nhưng vẫn có thể làm đầy disk. Vì thế phải kiểm từng lớp.

### 2.1 Bộ ba giới hạn quan trọng

1. **Header budget:** cho phép bao nhiêu byte ở các trường header/request line (chi tiết phụ thuộc server/protocol).
2. **Memory aggregation budget:** bao nhiêu byte một codec được phép buffer để decode một object/form value.
3. **Body/file budget:** tối đa bao nhiêu byte payload được chấp nhận **tổng cộng** và trên từng upload, kể cả trường hợp stream hoặc client không gửi `Content-Length`.

Không được hiểu 256 KB codec buffer mặc định là “API chỉ chấp nhận file dưới 256 KB”. Với multipart, **file part lớn hơn threshold** thường được ghi tạm xuống disk, không nhất thiết bị từ chối tại ngưỡng 256 KB.

## 3. Đường đi request và vị trí áp dụng giới hạn

```text
Browser / curl / service client
        |
        | HTTPS request (headers + body)
        v
TLS terminator / CDN / ingress
        |  - giới hạn URL, headers, body bytes, rate, timeout
        |  - có thể trả 413/431/400 trước khi request tới backend
        v
Reactor Netty HTTP decoder
        |  - request line, HTTP headers, validation
        |  - nếu vượt ngưỡng: request có thể bị từ chối/connection close
        v
Spring WebFlux WebFilter pipeline
        |
        +-- Spring Security WebFilterChain
        |       - authentication, authorization, CSRF
        |       - user thiếu quyền bị từ chối trước business handler
        |
        +-- Handler / codec / multipart reader
        |       - decoded form/JSON memory budget
        |       - multipart per-part disk & count limits
        |       - body aggregation và DataBuffer lifecycle
        |
        +-- Application rule / quotas
        |       - tổng body bytes, file type, owner, tenant,
        |         max uploads/user, object storage, virus scanning
        v
Service / storage
```

**Không dựa vào chỉ một tầng.** Proxy đặt `client_max_body_size` nhưng môi trường staging chạy bỏ qua proxy? Test trực tiếp backend có thể nhận payload mà bạn tưởng đã giới hạn. Ngược lại, app có `DataBufferUtils.join(..., 1024)` nhưng một HTTP request header khổng lồ vẫn tốn tài nguyên **trước khi vào endpoint**; phải cấu hình server/gateway.

### 3.1 Nếu HTTPS kết thúc ở proxy

Với TLS offload, browser kết nối **HTTPS tới proxy**, nhưng Netty app có thể nhận HTTP nội bộ. Giới hạn TLS handshake, header compression, body bytes và connection phải được áp dụng đúng ở **tầng đang tiếp nhận traffic**. Backend vẫn cần một số hạn mức riêng nếu có đường gọi nội bộ hoặc cấu hình ingress thay đổi.

Không kết luận “đã có HTTPS nên body lớn không gây DoS”; HTTPS bảo vệ tính bí mật và toàn vẹn đường truyền, **không** thay thế size limits, rate limiting, timeout hay disk quota.

## 4. Giới hạn HTTP request header và request line trong Spring Boot/Netty

Trong ứng dụng Spring Boot 3.5 dùng Reactor Netty, có thể đặt:

```yaml
server:
  max-http-request-header-size: 8KB
  netty:
    max-initial-line-length: 4KB
```

**Ý nghĩa từng property:**

- `server.max-http-request-header-size` giới hạn request headers ở embedded server; **default thường 8 KB** trong Spring Boot 3.5. Cách hiểu “tổng” hay “từng header” **phụ thuộc web server**. Tài liệu Spring Boot 3.5 ghi rõ: **Netty áp dụng ngưỡng riêng cho từng header**, trong khi Tomcat tính cả request line và tập headers theo cách khác. Vì vậy không tuyên bố ngưỡng 8 KB ở Netty luôn là tổng của mọi field.
- `server.netty.max-initial-line-length` đặt độ dài tối đa của HTTP/1.1 **request initial line** (method, request target, HTTP version), default ví dụ 4 KB. Nó khác giới hạn tổng URL mà gateway/CDN có thể áp dụng.
- HTTP/2 có header framing/compression và cơ chế kiểm soát riêng; đừng giả định ngưỡng ở mọi server và mọi protocol giống HTTP/1.1. Test đúng phiên bản Reactor Netty, HTTP/1.1 / HTTP/2 và ingress mà sản phẩm dùng.

### 4.1 Request header lớn đến từ đâu?

Một số nguồn phổ biến:

- `Authorization: Bearer <JWT>` mang quá nhiều claims, nested permissions hoặc chuỗi token phình to.
- `Cookie` chứa quá nhiều session/tracking cookies, được browser gom thành một header lớn.
- `X-Forwarded-*` / trace headers hoặc custom metadata lặp lại qua proxy.
- Filename/metadata không đặt trong header đúng cách nhưng client cố đẩy chuỗi rất dài vào custom headers.
- Host/request target bất thường, duplicate/conflicting `Content-Length`, folded/invalid headers, hoặc kẻ tấn công tạo nhiều header names.

Đừng phản xạ tăng header limit lên 64 KB để cho JWT/cookie phình mãi. Trước hết giảm kích thước token/claims, bỏ cookies không cần thiết, xem tác động của proxy và kiểm soát các header nhận từ client. Header chứa token hoặc cookies rất nhạy cảm: **không bật log raw `Authorization`/`Cookie` khi debug giới hạn**.

### 4.2 Ngưỡng request line không phải ngưỡng body

`GET /api/search?filter=...` với query 10 KB có thể bị decoder từ chối ngay trước WebFlux. Nhưng `POST /api/search` với body JSON 10 MB có request line ngắn, nên không chịu tác động từ `server.netty.max-initial-line-length`. Cần giới hạn mỗi loại ở layer phù hợp.

Không đưa PII, access token hay document content dài vào query string chỉ để tránh body limit. URL thường xuất hiện trong browser history, access logs, proxies và telemetry.

### 4.3 Điều gì xảy ra khi header vượt giới hạn?

HTTP có `431 Request Header Fields Too Large` (RFC 6585), `414 URI Too Long`, `400 Bad Request`, và có tình huống server từ chối hoặc đóng connection trước khi WebFlux dispatch.

**Không bảo đảm** Reactor Netty sẽ luôn trả 431 khi một header vượt cấu hình. Decoder có thể phát exception, đóng kết nối hoặc phản hồi status phụ thuộc phiên bản/protocol/proxy. Vì lỗi xảy ra **trước khi application WebFilter được gọi**, `@RestControllerAdvice` hoặc `ServerAuthenticationEntryPoint` không thể luôn biến nó thành một JSON error đẹp.

**Quy tắc test:** xác nhận request bị chặn và tài nguyên app được bảo vệ; không hardcode 431 nếu môi trường thực đôi khi trả 400 hoặc transport error.

### 4.4 Có thể cấu hình trực tiếp Reactor Netty?

Khi cần kiểm soát decoder beyond Boot properties, Reactor Netty có `HttpServer.httpRequestDecoder(...)`, ví dụ:

```java
// Mảnh cấu hình thay thế khi thật sự cần Netty-specific tuning.
@Bean
WebServerFactoryCustomizer<NettyReactiveWebServerFactory> nettyDecoder() {
    return factory -> factory.addServerCustomizers(
        httpServer -> httpServer.httpRequestDecoder(decoder ->
            decoder.maxHeaderSize(8192)
                   .maxInitialLineLength(4096)
                   .validateHeaders(true)
        )
    );
}
```

Đây là **snippet trong `@Configuration`**, cần imports:

```java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.context.annotation.Bean;
```

Mã dành cho Boot 3.x + Reactor Netty 1.x. Nếu đã đặt Boot properties tương ứng, **không nên khai báo thêm customizer với giá trị khác** để tránh xung đột thứ tự thiết lập. `maxHeaderSize` không nên bị nhầm thành tổng body limit; `maxChunkSize` cũ của Netty là decoder chunk setting/deprecated ở một số phiên bản, **không phải cách thay cho upload quota**.

## 5. Giới hạn WebFlux codec in-memory

Một số `Decoder` / `HttpMessageReader` phải **gom byte vào memory** trước khi tạo một object, ví dụ JSON có token/string dài, form URL-encoded, `@RequestBody byte[]`, hay quá trình tách từng record từ streaming content.

Trong **Spring Boot 3.5.x**, property chuẩn là:

```yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
```

**Quan trọng về phiên bản:** Trong **Spring Boot 3.4.x và một số 3.x cũ**, property tương ứng tên là `spring.codec.max-in-memory-size`. Từ Boot **3.5**, bảng *Common Application Properties* dùng `spring.http.codecs.max-in-memory-size`. Hãy tra chính xác trang properties của phiên bản đang chạy; không đặt cả hai tên một cách mù quáng và nghĩ cả hai đều có hiệu lực.

### 5.1 Chính xác giới hạn này áp dụng cho cái gì?

WebFlux codec có hạn mức **buffer khi decode**, không phải “cắt mọi body ngay khi tổng byte > 256 KB”. Tùy reader/decoder:

- Với một object JSON cần buffer, hạn mức có thể áp dụng vào phần được gom để parse.
- Với `application/x-www-form-urlencoded`, nhiều nội dung form phải được aggregate.
- Với stream `Flux<Pojo>` có các JSON objects tách rời, limit có thể **theo từng object/token**, không phải tổng tất cả objects.
- Với `Flux<DataBuffer>` đọc raw bytes trực tiếp, framework có thể chuyển các chunks mà không tự aggregate thành một buffer toàn request; **cần giới hạn tổng số byte riêng** nếu endpoint cần.
- Với multipart, file part có thể spill ra disk thay vì bị giới hạn bằng max-in-memory-size; xem mục multipart.

### 5.2 DataBufferLimitException

Khi codec/buffer aggregation vượt ngưỡng, Spring Framework có thể phát `DataBufferLimitException`. Lỗi này cho biết giới hạn lượng byte được buffer/đọc cho **một phép aggregation/decoder** đã bị vượt. Không tự suy ra HTTP status cố định: tùy nơi exception được ném, nó có thể được wrapped thành exception xử lý input hoặc đi vào error handling framework.

Đối với API công khai, có thể ánh xạ **đúng những lỗi size thực sự nhận diện được** thành `413 Payload Too Large` với thông điệp tổng quát. Tránh bắt mọi `Exception` rồi trả 413 vì có thể che bug server/permission errors.

### 5.3 Tăng max-in-memory-size có phải cách chữa file upload không?

Thường **không**. Tăng `max-in-memory-size` lên `100MB` có thể biến một request lớn thành áp lực RAM cực mạnh, đặc biệt khi nhiều request chạy đồng thời. Với file upload, chọn cơ chế streaming/spooling và giới hạn riêng cho file; không gom toàn bộ file vào `byte[]` hoặc `String`.

Ước lượng chi phí đơn giản: nếu 50 request đồng thời mỗi request có thể buffer 8 MB, riêng vùng buffer này có thể tiêu tốn khoảng 400 MB, chưa kể đối tượng Java, framework và phân mảnh heap. Con số chỉ là ước lượng trực quan; hãy benchmark thực, đặt concurrency/rate limit và memory budgets theo container.

## 6. Giới hạn body bytes thực sự: Content-Length không đủ

`Content-Length` là **metadata từ client**. Nó hữu ích để từ chối request **sớm** nếu hợp lệ và vượt giới hạn, nhưng **không là cơ chế enforcement duy nhất**:

- Client có thể gửi `Transfer-Encoding: chunked` và không có `Content-Length`.
- Proxies có thể thay đổi cách truyền body và headers.
- Byte counts của nội dung đã giải nén/decompressed có thể khác byte counts truyền trên network.
- Client có thể gửi length sai hoặc các headers mâu thuẫn; HTTP decoder/proxy có hành vi riêng khi phân tích.
- Một endpoint streaming có thể nhận dữ liệu theo thời gian, không biết kích thước cuối từ header ban đầu.
- Nhiều file parts cộng lại có thể vượt ngân sách tổng dù mỗi part nằm dưới limit.

Vì thế muốn **chặn tổng payload tại application**, cần đếm hoặc giới hạn **những byte được consumer thực sự đọc**; muốn chặn rất sớm, cũng đặt limit ở ingress/server.

### 6.1 Một ứng dụng Java nhỏ hiểu đúng “size limit”

Xét hai request:

```http
POST /api/raw HTTP/1.1
Content-Type: application/octet-stream
Content-Length: 100
```

và

```http
POST /api/raw HTTP/1.1
Transfer-Encoding: chunked
Content-Type: application/octet-stream
```

Đây là **ví dụ phần đầu HTTP message**, không có body hoặc framing chunk nên không phải raw request hoàn chỉnh để copy. Cả hai có thể cùng gửi 100 byte payload. Một filter chỉ so `Content-Length` rồi cho qua sẽ bỏ qua trường hợp chunked. Consumer đặt hạn mức byte khi đọc body có khả năng kiểm tra **cả hai**.

### 6.2 Khi nào dùng DataBufferUtils.join(body, maxByteCount)?

`DataBufferUtils.join(Publisher<DataBuffer>, int maxByteCount)` gom các `DataBuffer` thành một buffer tổng hợp **đến tối đa số byte chỉ định**; nếu vượt, nó phát `DataBufferLimitException`. Hàm có cơ chế release những buffer đã thu thập khi lỗi/cancel. Khi join thành công, caller sở hữu composite buffer và phải **release khi đọc xong**.

Kỹ thuật này hợp lý cho **request body nhỏ** mà ứng dụng cần đọc toàn bộ, ví dụ tối đa 1 KiB, 32 KiB, vài MB được ngân sách hoá. Nó **không phải lựa chọn tối ưu cho file hàng GB**, vì vẫn gom tất cả byte được phép vào một aggregated buffer. Với file lớn hãy xử lý streaming, đếm byte, spool ra disk/object storage và kiểm quota.

### 6.3 Đừng lạm dụng DataBuffer

Netty thường dùng pooled/reference-counted buffers. Nếu tự tiêu thụ `DataBuffer`, không được để leak; nếu buffer được xử lý bởi WebFlux codec bình thường thì framework quản lý vòng đời phù hợp. Nếu tự gọi `DataBufferUtils.join`, phải release kết quả sau khi dùng; không release nó trước khi đọc; không giữ reference qua async callback không kiểm soát.

**Mẫu đúng:**

```java
return DataBufferUtils.join(request.getBody(), MAX_BYTES)
    .map(buffer -> {
        try {
            return buffer.readableByteCount();
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    });
```

Đây là **snippet bên trong method xử lý body** với `ServerHttpRequest request` và constant `MAX_BYTES`, chưa phải file độc lập. Nếu body vượt ngưỡng, join tự phát lỗi; error mapping phù hợp với endpoint có thể tạo 413. Toàn bộ file chạy được ở phần tiếp theo.

## 7. Multipart upload trong Spring WebFlux: nhiều ngưỡng khác nhau

Spring Boot 3.5 cung cấp các property cụ thể cho WebFlux multipart:

```yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 4MB
      max-headers-size: 8KB
      max-parts: 3
```

**Từng thuộc tính có ngữ nghĩa riêng:**

| Thuộc tính | Ý nghĩa | Không có nghĩa |
| --- | --- | --- |
| `max-in-memory-size` | Bộ nhớ dùng cho **non-file parts**, và ngưỡng file part bắt đầu **ghi tạm xuống disk** | File lớn hơn 64 KB luôn bị từ chối |
| `max-disk-usage-per-part` | Lượng disk tối đa được dùng **mỗi file part đã spool** | Tổng của toàn request ≤ 4 MB |
| `max-headers-size` | Giới hạn lượng memory cho các headers **của mỗi multipart part** | Header HTTP ngoài cùng bị giới hạn bởi property này |
| `max-parts` | Giới hạn số parts trong request multipart | Số bytes của mỗi part hoặc toàn request |
| `file-storage-directory` | Thư mục file tạm cho multipart parsing | Vị trí lưu cuối cùng an toàn hoặc quota mặc định |

Một multipart POST có thể chứa file part, field text, metadata, headers mỗi part, boundary và những bytes framing khác. Một file part 3 MB **và** một file part 3 MB có thể đều dưới 4 MB per-part nhưng **tổng đã lớn hơn 4 MB**, còn chưa tính metadata. Muốn giới hạn toàn request, đặt **ingress body limit** và/hoặc **tổng byte budget** ở application phù hợp.

### 7.1 Những default đáng chú ý

Theo bảng Spring Boot 3.5 Common Application Properties:

- Multipart `max-in-memory-size` mặc định khoảng **256 KB**.
- Multipart `max-headers-size` khoảng **10 KB**.
- `max-disk-usage-per-part` mặc định **-1**, nghĩa là **không giới hạn** ở property này.
- `max-parts` mặc định **-1**, nghĩa là **không giới hạn** ở property này.

Đây là lý do ứng dụng upload production không nên chỉ nghĩ “framework có default là an toàn rồi”. Cần thiết lập theo nhu cầu, đặc biệt khi lưu temporary multipart files trên cùng volume với application.

### 7.2 Không dùng thuộc tính Servlet cho WebFlux

Những property:

```properties
spring.servlet.multipart.max-file-size=4MB
spring.servlet.multipart.max-request-size=6MB
```

là **cơ chế cho Spring MVC/Servlet**, không phải giới hạn toàn cục của Spring WebFlux/Reactor Netty. Đừng copy từ bài Servlet rồi kết luận WebFlux đã enforce upload size. Tài liệu Spring Boot có hai nhóm cấu hình khác nhau.

### 7.3 FilePart và PartEvent là hai lối đi khác nhau

- `@RequestPart("file") FilePart`: WebFlux multipart parser tạo `FilePart`, cho phép `file.transferTo(Path)`. Property parser có thể dùng temporary storage và giới hạn disk per part.
- `@RequestBody Flux<PartEvent>`: cách xử lý **streaming multipart events**. Nội dung có thể đi qua chunks trong `FilePartEvent`; các giới hạn spooling/disk theo reader thông thường **không tự áp dụng giống hệt**, vì không nhất thiết có file tạm. Cần count bytes, số parts, header/metadata limits, release DataBuffer và storage quotas cho streaming parser theo docs và phiên bản cụ thể.

**Cảnh báo:** `FilePart.filename()` là dữ liệu không tin cậy. Không ghép `targetDir.resolve(file.filename())` rồi ghi, vì có nguy cơ path traversal, tên trùng, ghi đè file và nội dung độc hại. Tạo **server-generated filename**, giới hạn content type/extension bằng policy và kiểm tra file content sau upload. Không tin hoàn toàn `Content-Type` từ client.

### 7.4 Temporary storage và application storage

WebFlux parser có thể spool file xuống disk tạm **trước khi controller nhận `FilePart`**. Khi controller gọi `transferTo`, file được chuyển tới đích được bạn chọn. Cần kiểm tra quota và dung lượng tại **cả nơi tạm lẫn nơi lưu cuối**, ownership/permissions, lifecycle và cleanup khi lỗi/cancel. Nếu chạy container, disk tạm có thể chung overlay filesystem dễ đầy.

Một upload thành công HTTP 201 không có nghĩa file đã qua kiểm virus hoặc được public. Với sản phẩm thật, chỉ publish sau khi scan/validate và phân quyền tài nguyên.

## 8. Dự án hoàn chỉnh Java 17+ — header, JSON, raw body và file upload

Bài thực hành có bốn nhóm hành vi:

1. HTTP header và request line được server Netty kiểm qua properties.
2. JSON decoding bị giới hạn bởi codec memory budget.
3. POST `/api/raw` được **chính endpoint** chặn khi body vượt **1024 bytes**, kể cả không có `Content-Length`.
4. Multipart `/api/files` được parser giới hạn theo config, rồi controller ghi file sang thư mục demo với tên do server sinh.

API có HTTP Basic để minh họa lớp Spring Security. **CSRF được giữ bật mặc định**; integration tests cho POST sử dụng `spring-security-test` cấp token, còn request POST thường từ curl không có CSRF sẽ bị từ chối 403. Trong hệ thống machine-to-machine chỉ có token/bearer và không có browser ambient credentials, có thể thiết kế CSRF policy khác có điều kiện; bài này không tắt CSRF toàn cục chỉ để test.

### 8.1 Build dependencies

Tạo project từ Spring Initializr với Java 17, **Spring Boot 3.5.x**, Gradle Groovy, dependencies: Reactive Web, Security, Test, Security Test.

Trong `build.gradle` của project đã có Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` để tránh Spring Boot tự chọn MVC. `ServerHttpSecurity`/`SecurityWebFilterChain` thuộc WebFlux, không phải `HttpSecurity`/`SecurityFilterChain` của Servlet.

### 8.2 File cấu hình: application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  max-http-request-header-size: 8KB
  netty:
    max-initial-line-length: 4KB

spring:
  http:
    codecs:
      max-in-memory-size: 256KB
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 4MB
      max-headers-size: 8KB
      max-parts: 3
```

Các giá trị ở đây là **mẫu minh họa**, chưa phải recommendation cho mọi API. Ngoài ra cần quota tổng ở gateway; thay đổi property theo profile/traffic/khả năng lưu trữ. **Đây là cú pháp của Boot 3.5.x**. Nếu dự án dùng Boot 3.4, thay phần `spring.http.codecs.max-in-memory-size` bằng `spring.codec.max-in-memory-size` theo docs phiên bản đó, không giữ cả hai một cách ngẫu nhiên.

### 8.3 Source layout

```text
src/main/java/com/example/payloadlimits/
  PayloadLimitsApplication.java
  SecurityConfig.java
  PayloadController.java
src/main/resources/
  application.yml
src/test/java/com/example/payloadlimits/
  PayloadLimitsHttpTest.java
```

Mỗi `public class` được lưu ở file riêng, package `com.example.payloadlimits`. Mã dùng Reactor/WebFlux libraries nên chạy qua Gradle project đã có dependency, **không chạy bằng `javac` trần**. Để khỏi phụ thuộc tài khoản hay dịch vụ ngoài, lưu file demo trong `build/upload-demo` chỉ dành cho thử nghiệm.

### 8.4 PayloadLimitsApplication.java

`src/main/java/com/example/payloadlimits/PayloadLimitsApplication.java`:

```java
package com.example.payloadlimits;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PayloadLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PayloadLimitsApplication.class, args);
    }
}
```

### 8.5 SecurityConfig.java: auth trước business data

`src/main/java/com/example/payloadlimits/SecurityConfig.java`:

```java
package com.example.payloadlimits;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/ping").authenticated()
                .pathMatchers(HttpMethod.POST, "/api/**").hasRole("UPLOAD")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var uploader = User.withUsername("uploader")
            .password(encoder.encode("uploader-demo-password"))
            .roles("UPLOAD")
            .build();

        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEW")
            .build();

        return new MapReactiveUserDetailsService(uploader, viewer);
    }
}
```

**Giải thích:** HTTP security không tạo body limit. Nó chỉ xác thực Basic credential và yêu cầu `ROLE_UPLOAD` cho POST endpoints. Người chưa xác thực gọi `GET /api/ping` nhận 401, user `viewer` đã xác thực nhưng không có quyền upload bị 403 khi POST có CSRF token hợp lệ. Không gửi Basic password qua HTTP trên mạng thật; ví dụ dùng localhost với user giả.

Với production, hãy giới hạn người có quyền upload, kích thước theo user/tenant và rate limiting ngay cả khi role hợp lệ. Một user có quyền upload **không** có nghĩa được dùng vô hạn RAM/disk/băng thông.

### 8.6 PayloadController.java: body raw thực sự bounded

`src/main/java/com/example/payloadlimits/PayloadController.java`:

```java
package com.example.payloadlimits;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class PayloadController {

    private static final int MAX_RAW_BYTES = 1024;

    public record SizeReceipt(int bytes) {}
    public record NoteInput(String text) {}
    public record NoteReceipt(int chars) {}
    public record UploadReceipt(String id) {}

    @GetMapping(value = "/public/health", produces = "text/plain")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(value = "/api/ping", produces = "text/plain")
    public Mono<String> ping() {
        return Mono.just("secured");
    }

    @PostMapping(
        value = "/api/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    public Mono<ResponseEntity<SizeReceipt>> raw(
            ServerHttpRequest request) {

        return DataBufferUtils.join(
                request.getBody(), MAX_RAW_BYTES
            )
            .map(buffer -> {
                try {
                    int count = buffer.readableByteCount();
                    return ResponseEntity.ok(new SizeReceipt(count));
                }
                finally {
                    // Caller phải release joined DataBuffer sau khi dùng.
                    DataBufferUtils.release(buffer);
                }
            })
            .switchIfEmpty(
                Mono.just(ResponseEntity.ok(new SizeReceipt(0)))
            )
            .onErrorMap(
                DataBufferLimitException.class,
                error -> new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Raw body exceeds 1024 bytes", error
                )
            );
    }

    @PostMapping(
        value = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<NoteReceipt>> notes(
            @RequestBody Mono<NoteInput> body) {

        // Đường decode JSON dùng WebFlux codecs.
        return body.map(note ->
            ResponseEntity.ok(new NoteReceipt(
                note.text() == null ? 0 : note.text().length()
            ))
        );
    }

    @PostMapping(
        value = "/api/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        MediaType contentType = file.headers().getContentType();
        if (contentType == null
                || !MediaType.TEXT_PLAIN.isCompatibleWith(contentType)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only text/plain uploads are accepted in this demo"
            ));
        }

        // KHÔNG lấy đường dẫn từ file.filename() của client.
        String id = UUID.randomUUID().toString();
        Path directory = Path.of("build", "upload-demo");
        Path target = directory.resolve(id + ".txt");

        return Mono.fromCallable(() -> Files.createDirectories(directory))
            .subscribeOn(Schedulers.boundedElastic())
            .then(file.transferTo(target))
            .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(id)));
    }
}
```

### 8.7 Phân tích controller

**Phần `raw`:**

- `ServerHttpRequest.getBody()` là `Flux<DataBuffer>` chứa byte body **thực nhận**. Nó không cần `Content-Length` để biết khi nào vượt 1024.
- `DataBufferUtils.join(body, 1024)` giới hạn tổng byte **mà endpoint muốn aggregate**. Chỉ request nhỏ hơn hoặc bằng 1024 bytes được xử lý thành công.
- Sau khi join thành công, `DataBufferUtils.release(buffer)` được gọi trong `finally`, tránh giữ pooled buffers. Khi join thất bại/cancel, utility quản lý release những buffers đã tích lũy.
- `DataBufferLimitException` được ánh xạ thành `ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, ...)`, nên khi chưa commit, WebFlux có thể trả **413**.
- `switchIfEmpty` cho body không có bytes nhận 0. Nếu business yêu cầu body bắt buộc, đổi thành 400 bằng validation riêng.
- Để hạn chế upload lớn, **không** dùng `join(..., Integer.MAX_VALUE)`; 1024 ở đây là một budget cố ý nhỏ để test, không phải một giá trị áp dụng chung.

**Phần `notes`:**

- `@RequestBody Mono<NoteInput>` yêu cầu codec decode JSON. `spring.http.codecs.max-in-memory-size` giới hạn phần byte mà codec cần aggregate, tùy JSON decoder và cấu trúc dữ liệu.
- Đếm `note.text().length()` chỉ là số ký tự Java UTF-16 trong string, **không** phải số byte HTTP request. Đừng dùng nó để làm business size enforcement cho JSON payload.
- Nếu cần limit tổng JSON document bất kể cấu trúc, đặt giới hạn actual request body tại gateway hoặc layer đọc bytes phù hợp, và kiểm tra sau giải nén khi có cơ chế decompression.

**Phần `upload`:**

- Spring WebFlux multipart parser nhận file part, áp dụng config trong `application.yml` với đường đi parser thông thường. `file.transferTo(target)` ghi file ở đích được chọn.
- Chúng ta không dùng `file.filename()` để tạo tên trên disk, mà sinh UUID phía server. Việc giới hạn extension/path là bước đầu; nội dung `text/plain` do header client gửi **không chứng minh** file thật là text hợp lệ.
- `Files.createDirectories` là thao tác filesystem blocking; ví dụ dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` để không chạy trên Netty event-loop.
- Code demo **không** triển khai antivirus, disk quota theo user, dọn file partial khi lỗi, timeout hay publish lifecycle. Những việc này là bắt buộc cân nhắc trước production.
- Multipart 4 MB **per part** không tự giới hạn tổng multipart request. Với nhiều file parts, cần toàn-request quota ở ingress và application nếu yêu cầu nghiêm ngặt.

## 9. Kiểm thử WebFlux và Spring Security bằng WebTestClient

Ta dùng test **mock WebFlux context** có Spring Security filter chain và `spring-security-test` để tạo CSRF token cho POST. Test này **không kiểm tra Netty decoder header budget** vì không chạy qua socket Netty; nó kiểm tra body quota trong controller, method security, CSRF và multipart trên WebFlux layer.

Tạo `src/test/java/com/example/payloadlimits/PayloadLimitsHttpTest.java`:

```java
package com.example.payloadlimits;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class PayloadLimitsHttpTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthIsAvailableWithoutPassword() {
        client.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("ok");
    }

    @Test
    void protectedPingNeedsAuthentication() {
        client.get()
            .uri("/api/ping")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void exactly1024RawBytesAreAccepted() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[1024])
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(1024);
    }

    @Test
    void rawBodyAbove1024BytesIsRejectedWith413() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[1025])
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE);
    }

    @Test
    void uploaderCanDecodeSmallJson() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.chars").isEqualTo(5);
    }

    @Test
    void authenticatedViewerCannotUpload() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[20])
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void uploadWithoutCsrfIsForbidden() {
        client.post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[20])
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void smallTextMultipartUploadIsAccepted() {
        var builder = new MultipartBodyBuilder();

        var data = new ByteArrayResource(
            "hello file".getBytes(StandardCharsets.UTF_8)
        ) {
            @Override
            public String getFilename() {
                return "client-supplied-name.txt";
            }
        };

        builder.part("file", data)
            .contentType(MediaType.TEXT_PLAIN);

        client.mutateWith(csrf())
            .post()
            .uri("/api/files")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(BodyInserters.fromMultipartData(builder.build()))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").exists();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*PayloadLimitsHttpTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*PayloadLimitsHttpTest'
```

**Kết quả mong đợi:** các test pass khi project Boot 3.5/WebFlux/Security được tạo đúng như trên. Đây là **kỳ vọng được suy ra từ mã ví dụ, không phải output của một build đã chạy trong môi trường biên soạn bài**. Một test upload thành công sẽ tạo file trong `build/upload-demo`; chỉ dùng trong demo và dọn file sau bài thực hành.

### 9.1 Vì sao dùng csrf() trong POST tests?

Spring Security WebFlux bật CSRF protection cho những HTTP methods thay đổi trạng thái theo policy mặc định. Nếu gửi request POST với password đúng nhưng thiếu CSRF token, request có thể bị 403 **trước khi vào `PayloadController`**, do đó bạn không đo được limit 1024 bytes.

`SecurityMockServerConfigurers.csrf()` tạo request có token hợp lệ trong mock WebTestClient security flow. Điều này giữ nguyên security trong demo, tránh kiểu chữa test bằng `csrf(...disable())` toàn app. Khi dùng real browser, token/cookie/session phải được quản lý đúng; mock CSRF test **không tự chứng minh** browser production flow an toàn.

### 9.2 Tại sao test này không chứng minh 8 KB header limit?

`WebTestClient.bindToApplicationContext(...)` mô phỏng HTTP exchange trong process và gắn Spring Security, **không đi qua Reactor Netty decoder**. Do đó test này không thể xác nhận Netty từ chối một header >8 KB. Muốn kiểm server-level request line/header limits, phải dùng **real port** hoặc client mạng gọi app đang chạy với config thực, có thể thông qua curl/HTTP client và gateway.

### 9.3 Kiểm thử Netty header trong integration/e2e

Dựng server thật với `./gradlew bootRun` rồi sử dụng HTTP client gửi:

- Một request có một custom header `X-Large` với giá trị khoảng **12.000 ký tự ASCII**.
- Một request có request target/query vượt **4 KB**.
- Những request bình thường với header nhỏ để xác nhận app vẫn hoạt động.
- Một request HTTP/2 tương ứng **nếu** TLS/server hỗ trợ HTTP/2.
- Một request qua reverse proxy hoặc ingress thực nếu production có gateway.

**Kết quả an toàn cần kiểm:** các request vượt ngưỡng bị từ chối ở decoder/gateway và không tiêu tốn downstream resources; status có thể là 400/414/431 hoặc client thấy connection close tùy môi trường. **Không** yêu cầu cố định `@ExceptionHandler` trả `ProblemDetail` vì lỗi phát sinh trước Spring WebFlux.

Mỗi embedded server có semantics khác nhau. Không dùng testcase Netty để “chứng minh” cấu hình Tomcat/MVC hoặc gateway CDN có cùng ngưỡng.

## 10. Test thủ công bằng curl và ranh giới CSRF

Khởi động server:

```bash
./gradlew bootRun
```

URL mặc định thường là `http://localhost:8080` nếu server port 8080 khả dụng.

Kiểm endpoint public và protected:

```bash
curl -i http://localhost:8080/public/health
curl -i http://localhost:8080/api/ping
curl -i -u uploader http://localhost:8080/api/ping
```

Lệnh thứ ba để curl **hỏi password tương tác**, nhập `uploader-demo-password`. Không viết password thật ngay trên CLI, không dùng HTTP mạng công cộng để gửi Basic credential.

Đối với `POST /api/raw`, một curl đơn giản gửi 1025 bytes nhưng **không có CSRF token** sẽ có thể nhận 403, **không phản ánh 413 body limit**. Đây là hành vi chính xác của security trước controller. Dùng mock integration test có `csrf()` ở mục 9 hoặc thực hiện browser/session flow có CSRF token hợp lệ, **không tắt CSRF tùy tiện**.

Nếu một service-to-service upload API không dùng browser ambient credentials, kiến trúc production có thể dùng một **security chain riêng** cho Bearer JWT/service identity, và đặt CSRF policy phù hợp với threat model; không khuyến nghị tắt CSRF toàn ứng dụng chỉ vì muốn curl POST chạy nhanh.

## 11. Cách hiểu HTTP status khi request quá lớn

| Mã/status hoặc hiện tượng | Nguồn có thể xảy ra | Ý nghĩa |
| --- | --- | --- |
| `413 Payload Too Large` | App limit/gateway/parser ánh xạ đúng | Request body vượt hạn mức và bị từ chối |
| `431 Request Header Fields Too Large` | Một server/gateway chọn status này | Header quá lớn theo policy |
| `414 URI Too Long` | Request target/query quá dài | Không phải lỗi body |
| `400 Bad Request` | Header/protocol/multipart parser không hợp lệ | Không nhất thiết do kích thước; cần logs |
| `401 Unauthorized` | Thiếu/sai authentication theo Basic | Có thể xảy ra trước khi app đọc body |
| `403 Forbidden` | Thiếu quyền upload hoặc CSRF | Không mặc định là body quá lớn |
| `415 Unsupported Media Type` | App từ chối content type hoặc codec | Khác với file quá lớn |
| `5xx` | Lỗi server, thiếu tài nguyên, exception chưa được ánh xạ | Cần xử lý vận hành; không tuyên bố 5xx là 413 |
| Connection close/reset | Decoder/gateway/transport từ chối sớm | Không phải lúc nào có response body để parse |

**Lưu ý thứ tự xử lý:** nếu một request vừa **chưa xác thực** vừa **có body quá lớn**, status cuối cùng phụ thuộc layer nào từ chối trước. Proxy có thể từ chối 413 khi app chưa nhìn thấy request, còn WebFilter authentication có thể trả 401 khi chưa tiêu thụ body. **Không thiết kế test yêu cầu mọi lớp phải trả đúng một status bất kể đường đi**.

### 11.1 Trả 413 có phải “giảm byte đã truyền” không?

Nếu client đã gửi một body lớn đến proxy trước khi backend phát hiện vượt giới hạn, network bandwidth có thể đã bị tiêu tốn. Chặn ở ingress có lợi hơn khi có thể; cơ chế `Expect: 100-continue` giúp một số clients chờ phản hồi trước khi gửi body, nhưng không phải mọi client/server/proxy đều dùng hoặc tôn trọng nó.

`413` là một cách diễn đạt **policy từ chối payload**, không phải cam kết server đã đọc toàn bộ body hoặc không tốn tài nguyên.

## 12. Tầng reverse proxy / ingress / HTTPS

Một số hệ thống dùng **Nginx** trước WebFlux. Các directives ví dụ minh họa:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    # Chặn request body lớn trước backend theo chính sách ingress.
    client_max_body_size 5m;

    # HTTP header/request line buffers phụ thuộc ngữ nghĩa Nginx.
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

Đây là **mảnh cấu hình Nginx để hiểu vị trí giới hạn**, không phải một file server production hoàn chỉnh: cần certificate/key, TLS versions/ciphers, proxy timeout, real IP/forwarded headers, trusted upstream, HSTS chính sách tương thích và routing. Không copy rồi triển khai ngay.

**Tại sao proxy còn phải có hạn mức?**

- Client từ Internet có thể mở nhiều kết nối, giữ kết nối chậm, gửi rất nhiều bytes trước khi app đọc.
- TLS termination, decompression, HTTP/2 header compression và buffering có thể tạo tài nguyên tiêu tốn ở proxy.
- Một request có thể đi qua nhiều hops, mỗi hop dùng ngưỡng khác nhau. Nếu proxy nhận 20 MB nhưng Netty/app chỉ chịu 4 MB, backend vẫn chịu kết nối và công việc phân tích ban đầu.
- Nếu upload được stream qua proxy, ngưỡng proxy phải tính theo **payload thực** và semantics vendor; không coi timeout hay `proxy_request_buffering off` là body quota.

### 12.1 Chính sách nhất quán nhiều tầng

Ví dụ product yêu cầu **mỗi request upload tối đa 5 MiB tổng cộng**, file part tối đa 4 MiB, tối đa hai file:

- Ingress: từ chối **tổng request body** > 5 MiB.
- Multipart parser: không cho part đơn lẻ dùng disk > 4 MiB; `max-parts` theo số file **và các form fields** thực tế, không nhầm “2 file” thành “2 parts” khi còn metadata fields.
- App: xác minh tổng file bytes và tổng quota user, content type/magic bytes, owner/tenant.
- Storage: chỉ publish file đã được scan và validate; áp dụng quota và retention.
- Security: chỉ identity có `ROLE_UPLOAD`/scope phù hợp mới được upload; rate limit số requests và băng thông theo principal/IP một cách có kiểm soát.

Các ngưỡng phải được tính sao cho upload hợp lệ không bị chặn nhầm vì **multipart boundary và metadata** cũng chiếm bytes. Nếu business limit 4 MiB file content, tổng request có thể >4 MiB do framing; chọn ingress limit hợp lý cao hơn file budget hoặc dùng policy ở app để kiểm đúng file bytes.

### 12.2 HTTPS và giới hạn headers

HTTPS bảo vệ headers/body trong kênh giữa client và TLS terminator; nhưng `Authorization`, `Cookie` và upload metadata có thể bị lộ khi gateway log raw headers. Giảm logging nhạy cảm, bảo vệ nội bộ TLS nếu cần và xác minh hop trust khi dùng `X-Forwarded-*`.

Đừng nâng header budget chỉ để nhét thêm thông tin nhạy cảm vào JWT. Dùng JWT nhỏ, reference token/session handle hoặc backend lookup phù hợp với quy mô. Không để client tự đặt `X-User-Role`, `X-Tenant` hoặc `X-Forwarded-Proto` rồi tin như kết quả của proxy/IdP.

## 13. Giới hạn multipart theo byte: bài toán khó hơn “max file size”

### 13.1 Số part khác số file

Multipart form:

```text
multipart/form-data
  - file: photo.png    (file part)
  - title: "Hello"     (form field)
  - tags: "one,two"    (form field)
```

đã có **3 parts** dù chỉ có **1 file**. Nếu đặt `spring.webflux.multipart.max-parts=2`, request có thể bị từ chối dù file nhỏ. Thiết kế budget dựa trên schema form thực tế, không chỉ số files.

### 13.2 Ngưỡng spill không phải file cap

Một file 100 KiB khi `max-in-memory-size=64KB` có thể được ghi tạm ra disk thay vì bị từ chối ở 64 KB. Chỉ khi vượt giới hạn khác như `max-disk-usage-per-part`, hoặc tổng request limit tại ingress/application, nó mới bị chặn theo chính sách.

Hãy kiểm thử: file vừa dưới memory threshold, vừa trên threshold nhưng dưới disk cap, vượt disk cap, nhiều parts và các part headers bất thường. Không dùng `max-in-memory-size` như nhãn “file size limit”.

### 13.3 FilePart.transferTo không phải antivirus

`file.transferTo(target)` chỉ chuyển bytes tới đích; nó không quét malware, không kiểm MIME magic, không validate extension, không khử dữ liệu độc hại và không đảm bảo quá trình upload có quota hợp lý. Với file từ Internet, upload vào **quarantine/storage private**, scan/validate trước khi publish, từ chối executables nguy hiểm theo business requirements và tránh execute/serve raw HTML dưới trusted origin.

### 13.4 PartEvent streaming cần riêng byte counter

Nếu dùng `Flux<PartEvent>` để stream multipart mà không spool thành `FilePart`, không mặc định rằng tất cả các giới hạn về disk usage của parser thường còn hoạt động. Bạn phải **đếm actual `DataBuffer.readableByteCount()`** và giới hạn theo part/tổng, kèm backpressure, timeout, cleanup và release buffers khi bị từ chối.

**Pseudocode kiến trúc:**

```text
Receive PartEvent stream
  -> kiểm số lượng parts + per-part headers
  -> với từng file part:
       giới hạn tên file/metadata
       cộng số byte đọc được (không chỉ Content-Length)
       nếu vượt per-file hoặc total cap:
          dừng tiêu thụ, hủy subscription, cleanup file tạm
          trả 413 nếu response chưa committed
       nếu hợp lệ:
          stream bytes tới quarantine storage (bounded resources)
  -> scan/validate
  -> atomically publish hoặc mark ready
```

Đây là **pseudocode**, không phải code hoàn chỉnh; tránh viết một WebFilter “cộng byte” ngây thơ rồi làm rò rỉ pooled `DataBuffer`. Hãy test cancellation, Disk I/O lỗi và uploader gửi chunked body không có Content-Length.

## 14. Một chiến lược quota đủ sức chịu tải

Kích thước request chỉ là một chiều của tài nguyên. Ví dụ API upload cho mỗi user:

| Giới hạn | Ví dụ giá trị để lập kế hoạch | Giải quyết |
| --- | --- | --- |
| Request header | 8 KB ở server + ingress tương thích | Cookie/JWT/header flooding |
| Request line | 4 KB ở Netty + gateway tương thích | Query/path bất thường |
| JSON buffered segment | 256 KB | Memory pressure từ JSON/form |
| Raw body endpoint | 1 KB ở demo; business có thể khác | Tổng byte thực xử lý |
| Multipart file part | 4 MB tạm ở demo | Disk fill từ một file |
| Multipart part count | 3 parts ở demo | Part explosion |
| Total upload request | 5 MiB ở edge (mẫu kiến trúc) | Request nhiều file/metadata |
| Total storage per principal | Ví dụ 100 MiB, cần policy thật | Một user dùng hết disk |
| Concurrent uploads | Ví dụ tối đa 2 active/user | Song song làm tăng disk/CPU |
| Upload bandwidth/rate | Theo SLO và threat model | Slow clients hoặc burst |
| Request/idle timeout | Theo mạng/mobile/upload use case | Slowloris và subscriptions treo |

**Những giá trị trong bảng không phải một cấu hình nên copy vô điều kiện.** Hãy lấy đặc tính sản phẩm, lưu lượng thực, máy chủ, RAM, temporary disk, object-storage quota và nhu cầu người dùng để chọn ngưỡng. Các hạn mức đồng thời theo user/tenant phải có state chia sẻ nếu dịch vụ chạy nhiều replicas.

### 14.1 Lỗi concurrency khiến budget bị vượt

Giả sử một user được phép upload 4 MB/file, nhưng có 1.000 uploads song song. Per-file limit vẫn đúng nhưng có thể gây tiêu thụ ~4 GB disk hoặc nhiều file descriptors trước khi user quota được áp dụng. Cần **concurrency control**, queue, rate limit và tổng quota, không chỉ per-request size.

### 14.2 Compression bombs và tỷ lệ giải nén

Khi ứng dụng nhận dữ liệu nén (gzip/zip), kích thước bytes truyền và kích thước **sau giải nén** có thể rất khác. Giới hạn network body 5 MB không có nghĩa nội dung sau giải nén chỉ 5 MB. Nếu backend giải nén archive hoặc decompress request, cần giới hạn **decoded bytes**, số entries, độ sâu đường dẫn, CPU/time budget và traversal của zip entries.

Tương tự với image processing: file ảnh 2 MB có thể expand thành bitmap hàng trăm MB trong memory. Size limit không thay thế content validation/decompression ratio checks.

### 14.3 CPU timeout và backpressure

Reactive backpressure giúp điều tiết dữ liệu trong pipeline, nhưng không bảo đảm attacker không tiêu tốn tài nguyên socket, disk hoặc DB. Dùng bounded queues, timeouts, parallelism caps và circuit breakers theo workload. Đừng thực hiện blocking filesystem/virus scanning trực tiếp trên Netty event-loop.

## 15. Một số câu hỏi thường gặp và lỗi cấu hình

| Triệu chứng | Lỗi/nhận định có thể | Hướng xử lý |
| --- | --- | --- |
| Upload file 1 MB được dù `max-in-memory-size=64KB` | Đúng: file part được spool xuống disk | Kiểm `max-disk-usage-per-part` và total body quota |
| Upload file vượt 4 MB bị reject | Parser per-part disk cap hoặc ingress | Kiểm status/log tầng nào, đừng mặc định mọi trường hợp 413 |
| POST 1025 byte nhận 403 thay vì 413 | Thiếu CSRF hoặc role upload | Dùng `csrf()` trong test, xác minh auth/rules |
| Request có Content-Length nhỏ nhưng stream vẫn lớn | Chỉ check header hoặc chunked | Giới hạn actual body bytes |
| JWT lớn làm request bị 400/431/connection close | Header limit tại Netty/proxy | Giảm token/claims; tăng limit chỉ sau capacity/security review |
| Tăng `spring.http.codecs.max-in-memory-size` không giúp file upload | Codec memory không phải total file cap | Dùng multipart/file limit và ingress |
| Dùng `spring.servlet.multipart.max-file-size` trong WebFlux | Property dành cho Servlet | Dùng `spring.webflux.multipart.*` |
| Dùng `spring.codec.max-in-memory-size` ở Boot 3.5 không hiệu lực | Property đã đổi tên trong 3.5 | Dùng `spring.http.codecs.max-in-memory-size` đúng version |
| Chỉ test mock WebTestClient, header 12 KB vẫn vào app | Mock không qua Netty decoder | Test qua random port hoặc bootRun + real HTTP client |
| App trả 401 cho request large body | Security từ chối trước khi đọc body | Đây có thể đúng; test quota với authenticated+CSRF hợp lệ |
| Upload thành công nhưng disk tăng mãi | Không xóa temporary/partial files, thiếu retention | Quarantine, cleanup, quota, metrics |
| Malicious filename chứa ../ | Ghép filename client vào path storage | Sinh UUID; validate tên hiển thị riêng |
| File text/plain chứa binary | Content-Type client không đáng tin | Kiểm content, signature, scan |
| Multipart có 2 files và 2 fields bị chặn `max-parts=3` | Max parts đếm cả file và fields | Tính đúng multipart schema |
| Client nhận connection reset thay vì JSON 431 | Decoder/proxy từ chối trước app | Không dựa vào @ControllerAdvice cho decoder errors |
| Browser fetch upload bị CORS | CORS preflight/headers không được phép | Cấu hình CorsWebFilter và authentication riêng, không permitAll API |
| WebClient lỗi DataBufferLimitException khi download | Client codec memory budget, không phải server upload limit | Cấu hình WebClient riêng hoặc stream response |
| Upload 5MB dưới app cap nhưng reverse proxy trả 413 | Edge limit nhỏ hơn payload incl framing | Điều chỉnh budget nhất quán |
| Chỉ kiểm max disk per part nhưng request nhiều files | Không có total request cap | Edge total cap + app quota |
| Header HTTP/2 khác hành vi HTTP/1.1 | Decoder/protocol/gateway khác nhau | Test chính xác protocol production |
| HTTPS đúng nhưng DoS vẫn xảy ra | TLS không giới hạn tài nguyên | Thêm rate, timeout, byte budgets, quotas |
| CORS/CSRF bị tắt để “chữa 403” | Che lỗi security và có thể mở tấn công | Xác định nguyên nhân trước khi đổi policy |

## 16. Bài tập tự kiểm tra

**Câu 1.** Đặt `spring.http.codecs.max-in-memory-size=256KB` có nghĩa mọi file >256 KB bị từ chối không?

**Đáp:** Không. Nó liên quan đến codec buffering, và multipart file có thể spill disk hoặc stream. Dùng per-file, disk, total body và user quota riêng.

**Câu 2.** `spring.webflux.multipart.max-in-memory-size=64KB` có phải max file size 64 KB?

**Đáp:** Không. Đây là ngưỡng memory/spooling với file part; non-file parts có bộ nhớ limit phù hợp. File part có thể lớn hơn khi được ghi ra disk trong ngưỡng `max-disk-usage-per-part`.

**Câu 3.** Nếu Netty `server.max-http-request-header-size=8KB`, tổng mọi headers luôn phải ≤8KB?

**Đáp:** Không nên khẳng định. Tài liệu Spring Boot nêu Netty áp ngưỡng riêng trên mỗi header, Tomcat semantics khác. HTTP version/proxy cũng có thể áp dụng hạn mức riêng; test stack thực.

**Câu 4.** `Transfer-Encoding: chunked` không gửi Content-Length. Làm sao chặn body >1KB?

**Đáp:** Đếm/giới hạn bytes **khi stream thực được đọc**, ví dụ `DataBufferUtils.join(request.getBody(), 1024)` với body nhỏ, hoặc streaming byte counter có cleanup đúng.

**Câu 5.** Khi `DataBufferUtils.join` thành công, ai release `DataBuffer`?

**Đáp:** Consumer/đoạn code nhận joined buffer chịu trách nhiệm release sau khi xử lý, ví dụ `DataBufferUtils.release(buffer)` trong `finally`. Utility tự quản lý những buffers tích lũy khi error/cancel.

**Câu 6.** Multipart có hai files và hai text fields, `max-parts=3` có đủ không?

**Đáp:** Không. Đó là **4 parts** (chưa tính chi tiết protocol), request có thể bị từ chối dù chỉ có hai file.

**Câu 7.** Backend dùng WebFlux, có thể áp dụng `spring.servlet.multipart.max-request-size` để chặn tổng upload không?

**Đáp:** Không. Property Servlet không áp dụng thay cho WebFlux multipart parser; đặt total body cap ở ingress và app đúng stack.

**Câu 8.** Tại sao 413 có thể xuất hiện trước controller và không đi qua `@RestControllerAdvice`?

**Đáp:** Proxy/HTTP decoder/early limits có thể từ chối request trước WebFlux dispatcher. Handler trong app không có quyền viết lại response chưa bao giờ đi tới nó.

**Câu 9.** Tại sao POST vượt limit lại nhận 403 trong test thiếu CSRF?

**Đáp:** Security có thể chặn POST trước khi endpoint đọc body. Để kiểm limit, tạo authenticated request đúng role với CSRF hợp lệ trong mock WebTestClient.

**Câu 10.** File có Content-Type text/plain và tên myfile.txt có an toàn để mở public không?

**Đáp:** Không. Metadata do client gửi có thể giả, file có thể chứa binary/malware. Lưu tạm an toàn, scan/validate và áp quyền trước khi publish.

**Câu 11.** Một file 4 MB với số lượng 1.000 uploads song song có thể gây DoS dù per-file cap đúng không?

**Đáp:** Có. Cần concurrency limits, total disk quota, rate limits và cleanup, không chỉ cap từng file.

**Câu 12.** HTTPS có tự chặn header/body lớn không?

**Đáp:** Không. TLS mã hóa giao tiếp, không áp hạn mức nghiệp vụ. TLS terminator/ingress và WebFlux server cần giới hạn riêng.

## 17. Checklist sản xuất

- [ ] Xác nhận HTTP server thực sự là WebFlux Reactor Netty, không vô tình dùng Spring MVC/Servlet.
- [ ] Chọn Boot version cụ thể và **đúng property codec** (`spring.http.codecs.max-in-memory-size` từ 3.5; `spring.codec.max-in-memory-size` ở 3.4).
- [ ] Giới hạn request header và request line ở server/edge, kiểm Netty semantics và HTTP/2.
- [ ] Không log raw `Authorization`/`Cookie`, không tăng header limit chỉ vì token quá lớn.
- [ ] Có codec buffering limit cho JSON/form và hiểu **không phải body size limit**.
- [ ] Với raw streaming body, có total byte enforcement dựa trên **actual DataBuffer bytes** hoặc edge policy.
- [ ] Với multipart, giới hạn file part disk usage, part count, headers và total request bằng nhiều lớp.
- [ ] Kiểm test part count bao gồm **fields + files** và multipart framing overhead.
- [ ] Không lấy `FilePart.filename()` để tạo server-side path; storage target do server sinh.
- [ ] Temporary upload storage có quota/permissions, cleanup partial files và retention policy.
- [ ] Nếu dùng `PartEvent` streaming, có byte counter, resource release, backpressure và cancellation handling riêng.
- [ ] Request lớn bị chặn đúng tầng; HTTP status/connection close được kiểm trên server/gateway thật.
- [ ] Security authentication/authorization và CSRF không bị vô hiệu hóa tùy tiện khi test POST.
- [ ] Có tests small-body, just-at-limit, over-limit, unauthenticated, denied-role và upload multipart.
- [ ] Đã kiểm dung lượng sau decompression và archive extraction; bảo vệ zip bombs/huge image memory.
- [ ] HTTPS/TLS được triển khai đúng, forwarded headers từ trusted proxy, không lộ secrets trong logs.
- [ ] Có rate limits, concurrent upload caps, bandwidth/timeout budgets, disk usage alerts và monitoring 413/400/431.
- [ ] Tổng quan budgets thống nhất giữa CDN/gateway/ingress/app/storage, có rollback khi rollout gây false positives.

## 18. Tổng kết

**Giới hạn kích thước trong WebFlux không phải một tham số duy nhất.** Hãy tách rõ:

1. **Header/request line:** `server.max-http-request-header-size` và `server.netty.max-initial-line-length`, cộng với gateway limits.
2. **Memory aggregation:** Boot 3.5 dùng `spring.http.codecs.max-in-memory-size`, không biến property này thành “max HTTP body size”.
3. **Multipart:** `spring.webflux.multipart.max-in-memory-size` là threshold/buffer; `max-disk-usage-per-part` áp theo part; `max-parts` giới hạn số phần, không thay total request cap.
4. **Actual body bytes và quota:** phải đếm/giới hạn bytes tiêu thụ, giới hạn toàn request ở ingress, file/storage quotas theo user, concurrency và tài nguyên.
5. **Bảo mật:** HTTPS bảo vệ kênh, Spring Security quyết định ai được upload, còn resource limits ngăn request hợp lệ về danh tính nhưng quá lớn hoặc quá tốn tài nguyên.

**Ghi nhớ:** Không dựa duy nhất vào `Content-Length`, không lấy `max-in-memory-size` làm max-file-size, không dùng `spring.servlet.multipart` cho WebFlux, không cho một user upload vô hạn chỉ vì authentication đúng. Test bằng cả **WebTestClient mock** cho policy/codec và **HTTP thật qua Netty/proxy** cho decoder/tầng edge.

### Nguồn tham khảo chính thức

- [Spring Boot 3.5 — Common Application Properties: server request header, Netty, codec và WebFlux multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.4 — Application Properties (spring.codec.max-in-memory-size)](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Spring Framework 6.2 — WebFlux Reactive Core, Codecs, Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Multipart Content và PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — DataBufferUtils.join(Publisher, maxByteCount)](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — DataBuffer handling and reference counts](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html)
- [Reactor Netty — HTTP Server request decoder](https://projectreactor.io/docs/netty/release/reference/http-server.html)
- [Spring Boot 3.5 — NettyReactiveWebServerFactory API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [MDN — 413 Content Too Large / 431 Request Header Fields Too Large](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/413)
