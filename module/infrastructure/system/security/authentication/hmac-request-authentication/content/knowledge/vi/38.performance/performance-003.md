# Chi phí đọc body khi xác thực HTTP request bằng HMAC

## 1. Bối cảnh: bảo vệ tính toàn vẹn có chi phí

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client ký HTTP request bằng **HMAC với shared secret**. Hợp đồng ký có thể chứa method, canonical URI, signed headers, timestamp, nonce và **digest của request body**. Verifier phải dùng đúng secret/key ID, xác minh chữ ký, trạng thái credential, timestamp và nonce chống replay trước khi cho nghiệp vụ chạy. Sau đó, authorization vẫn kiểm tra principal, tenant, action và resource.

Để ký body, hai bên phải thống nhất **đúng tập byte** được băm. Nếu client ký SHA-256 của raw body bytes thì server phải tính digest của cùng bytes, không được parse JSON rồi serialize lại. Trên đường HTTP, việc đọc body trước controller tạo ra chi phí không chỉ ở phép tính SHA-256:

- **Thời gian mạng:** đợi client gửi đủ body để hoàn tất digest.
- **CPU:** copy bytes, SHA-256, HMAC canonical request, chuyển đổi dữ liệu.
- **Bộ nhớ:** vùng đệm HTTP, heap `byte[]`, Netty direct/pooled buffers, các bản sao replay và DTO.
- **Độ trễ:** thời gian chờ network, garbage collection, blocking I/O, secret manager và nonce store.
- **Khả năng chịu tải:** nhiều request chưa được xác thực cùng giữ buffer và connection.

Bài **Chi phí đọc body** thuộc chương **Performance**, tập trung vào việc thiết kế chiến lược đọc hiệu quả, đo đúng các chi phí trên Spring MVC/Spring WebFlux và bảo toàn mọi điều kiện bảo mật.

**Nguyên tắc:** giảm chi phí bằng cách giới hạn body, giảm copy và chọn kiến trúc phù hợp; **không** tối ưu bằng cách bỏ body digest, bỏ chống replay hoặc bỏ kiểm tra quyền.

## 2. Body được đọc ở đâu trong luồng xác thực?

~~~mermaid
flowchart TD
    A["HTTP client ký HMAC"] --> B["CDN / API Gateway / Proxy"]
    B --> C["HTTP server / container / Netty"]
    C --> D["Security filter: nhận raw body bytes"]
    D --> E["Giới hạn byte và giữ/replay body"]
    E --> F["SHA-256 body digest"]
    F --> G["Canonical request + HMAC verifier"]
    G --> H{"Key state, MAC, timestamp, nonce hợp lệ?"}
    H -->|Không| X["Từ chối request; không thực thi nghiệp vụ"]
    H -->|Có| I["Trusted principal"]
    I --> J{"Authorization tenant/action/resource?"}
    J -->|Không| Y["403 hoặc 404 theo chính sách"]
    J -->|Có| K["MVC/WebFlux handler đọc body đã xác minh"]
    K --> L["Deserialize + nghiệp vụ + HTTP response"]
~~~

Mỗi tầng có thể giữ một số bytes tạm thời. Gateway có thể đã buffer body trước khi chuyển cho backend; Servlet container và Reactor Netty có những cơ chế cấp phát khác nhau. Không nên mặc định mọi request có chính xác hai hay ba bản sao; cần đo bằng implementation thực.

### Phân tách ba miền chi phí

| Miền | Điều cần đo | Yêu cầu tính đúng |
| --- | --- | --- |
| Ingress và body capture | Network wait, bytes, timeout, buffer memory | Body size limit; không tin hoàn toàn Content-Length |
| Digest và authentication | SHA-256 time, credential lookup, MAC verify, nonce claim | Ký đúng canonical bytes; key/timestamp/nonce đầy đủ |
| Body replay và downstream | Copy, decode JSON, authorization, business latency | Controller thấy đúng body; chưa có quyền thì không xử lý |

Nếu số liệu p99 xấu do Redis nonce store chậm, việc tối ưu SHA-256 chưa chắc đem lại khác biệt. Nếu p99 xấu do upload chậm, microbenchmark HMAC cũng không giải thích được.

## 3. Mô hình chi phí: byte, bản sao và độ đồng thời

Gọi `B` là kích thước body (bytes), `C` là số request đang cùng giữ body, `k` là số bản sao body đầy đủ tương đương tồn tại tại một thời điểm.

Lượng bộ nhớ tối thiểu cho các bản sao là:

\[
M_{\mathrm{copies}}\approx B\times C\times k
\]

Ví dụ, `B = 1 MiB`, `C = 2.000` và `k = 2` thì lượng dữ liệu của riêng các bản sao raw body khoảng **4.000 MiB**, xấp xỉ **3,91 GiB**. Đây chưa phải peak RSS: còn có buffer của container/gateway, heap object, Jackson DTO, thread stack, direct memory và GC retention.

Với SHA-256, chi phí tính digest tăng gần tuyến tính theo số bytes:

\[
T_{\mathrm{hash}}(B)\approx \alpha B+\beta
\]

Ở đây `α` phụ thuộc CPU, thư viện và hardware acceleration; `β` là overhead khởi tạo/call. Nhưng latency xác thực thực tế còn nhiều thành phần:

\[
T_{\mathrm{auth}}\approx
T_{\mathrm{receive}}+T_{\mathrm{copy}}+T_{\mathrm{hash}}+
T_{\mathrm{credential}}+T_{\mathrm{nonce}}+T_{\mathrm{other}}
\]

Công thức là mô hình gần đúng cho pipeline có phần tuần tự, không phải phép cộng bắt buộc trong mọi triển khai async. Khi các bước overlap, phải đo wall-clock thực thay vì cộng những timer có thể chồng nhau.

### Ví dụ sizing

| Body limit | Concurrent captures | Một bản sao raw body | Hai bản sao raw body |
| --- | ---: | ---: | ---: |
| 16 KiB | 1.000 | ~15,6 MiB | ~31,3 MiB |
| 256 KiB | 1.000 | ~250 MiB | ~500 MiB |
| 1 MiB | 2.000 | ~1,95 GiB | ~3,91 GiB |
| 1 MiB | 5.000 | ~4,88 GiB | ~9,77 GiB |

Bảng là **ước lượng upper bound theo kích thước body cố định**. Trong tải thực, body size phân phối không đồng đều, các bản sao xuất hiện và mất đi ở những thời điểm khác nhau. Dù vậy, bảng đủ để bác bỏ suy nghĩ “1 MiB mỗi request là nhỏ nên có thể buffer vô hạn request”.

## 4. Body bytes là hợp đồng mật mã, không phải object JSON

Xét hai payload:

~~~json
{"orderId":"o-401","amount":180000}
~~~

~~~json
{
  "orderId": "o-401",
  "amount": 180000
}
~~~

Chúng có thể biểu diễn cùng dữ liệu nghiệp vụ nhưng **khác bytes**, vì có thêm khoảng trắng/xuống dòng. Nếu hợp đồng ký raw bytes, SHA-256 phải khác.

Những biến thể thường gây mismatch và tốn thêm CPU nếu cố normalize:

- JSON property order, khoảng trắng, định dạng số.
- UTF-8/UTF-16, Unicode escape, BOM.
- Ký tự `LF` và `CRLF`.
- Form URL-encoded có percent-encoding hoặc field trùng.
- Multipart boundary, Content-Disposition và dữ liệu file.
- Gateway đổi Content-Encoding, giải nén/recompress body.
- Proxy rewrite URI/query/Host và signed headers.

**Không** chuyển sang `String`, gọi Jackson `readTree` rồi `writeValueAsBytes` để có body ký “chuẩn” trừ khi giao thức đã quy định canonical JSON cụ thể và có test vectors độc lập.

Nếu hợp đồng ký digest do client gửi trong header, verifier vẫn phải tính digest trên **body thực nhận** để đối chiếu với header đã được ký. Chỉ tin `X-Content-SHA256` mà không kiểm tra payload cho phép thay body mà chữ ký trên header vẫn còn nguyên.

## 5. Servlet / Spring MVC: một lần đọc có thể làm mất body của controller

Với Spring MVC trên Jakarta Servlet, `HttpServletRequest.getInputStream()` là luồng body; không mặc định có khả năng rewind. Nếu HMAC filter đọc hết body bằng:

~~~java
byte[] raw = request.getInputStream().readAllBytes();
String digest = sha256Hex(raw);
verifyHmac(request, digest);
chain.doFilter(request, response);
~~~

thì controller dùng `@RequestBody` có thể không nhận được body nữa. `readAllBytes()` ở đây còn **không có giới hạn kích thước**, đặc biệt nguy hiểm trước khi biết client có HMAC hợp lệ không.

`ContentCachingRequestWrapper` hữu ích khi cần quan sát dữ liệu đã đọc, nhưng:

1. Bọc request **không tự động đọc** body; `getContentAsByteArray()` có thể rỗng trước khi có consumer.
2. Cache nội dung đã đọc **không đồng nghĩa** `getInputStream()` đã tự rewind cho controller.
3. Giới hạn cache không được coi là giới hạn an toàn của toàn bộ body; không hash một cache bị cắt trong khi downstream nhận body đầy đủ.

Với API JSON nhỏ, phương án thực tế là **bounded replayable request wrapper**: capture có giới hạn, giữ body byte array dưới quyền quản lý riêng của request, hash một lần, rồi phát stream mới từ cùng bytes cho MVC controller.

## 6. Java 17: replayable wrapper có giới hạn và ít copy

Mẫu sau dành cho Servlet xử lý **đồng bộ**, ví dụ Spring Boot 3 + Spring Security 6:

~~~java
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class BoundedReplayableRequest
        extends HttpServletRequestWrapper {

    private final byte[] body;

    private BoundedReplayableRequest(
            HttpServletRequest request, byte[] captured) {
        super(request);
        // captured được tạo riêng tại capture() và không
        // xuất ra ngoài; tránh một lần clone không cần thiết.
        this.body = captured;
    }

    static BoundedReplayableRequest capture(
            HttpServletRequest request, int maxBytes)
            throws IOException {

        if (maxBytes <= 0 || maxBytes >= Integer.MAX_VALUE - 1) {
            throw new IllegalArgumentException("Invalid size limit");
        }

        // Đọc tối đa limit + 1 byte để nhận biết overflow.
        // Không gọi readAllBytes() trên request chưa tin cậy.
        InputStream input = request.getInputStream();
        byte[] data = input.readNBytes(maxBytes + 1);
        if (data.length > maxBytes) {
            throw new BodyTooLargeException();
        }
        return new BoundedReplayableRequest(request, data);
    }

    String sha256LowerHex() {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(body));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }

    @Override
    public ServletInputStream getInputStream() {
        var input = new ByteArrayInputStream(body);
        return new ServletInputStream() {
            @Override
            public int read() {
                return input.read();
            }

            @Override
            public int read(byte[] b, int off, int len) {
                return input.read(b, off, len);
            }

            @Override
            public boolean isFinished() {
                return input.available() == 0;
            }

            @Override
            public boolean isReady() {
                // Chỉ hỗ trợ đường Servlet synchronous.
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException(
                    "Non-blocking I/O needs a different adapter");
            }
        };
    }

    @Override
    public BufferedReader getReader() throws IOException {
        String name = getCharacterEncoding();
        Charset charset = name == null
            ? StandardCharsets.UTF_8
            : Charset.forName(name);
        return new BufferedReader(
            new InputStreamReader(getInputStream(), charset));
    }

    @Override
    public int getContentLength() {
        return body.length;
    }

    @Override
    public long getContentLengthLong() {
        return body.length;
    }

    static final class BodyTooLargeException
            extends IOException {}
}
~~~

### Phân tích chi phí của ví dụ

- `readNBytes(maxBytes + 1)` có thể cấp phát/copy trong quá trình đọc nhưng **giới hạn tổng byte thu về**; vẫn phải có limit và timeout tại ingress/container.
- `ByteArrayInputStream` tạo một object stream mới tham chiếu `byte[]` và **không copy toàn bộ mảng**.
- Mẫu không cung cấp `bodySnapshot()` vì trả bản sao mảng sẽ tốn một full-body copy; khi thật sự cần snapshot, có thể clone có chủ đích.
- Digest được tính từ **mảng bytes lưu trong request**, không từ `Reader`/`String`.
- Constructor chỉ nhận mảng được tạo bởi chính `capture()`, không phải mảng mutable mà caller bên ngoài còn giữ.
- Không dùng trực tiếp mẫu này cho Servlet async/non-blocking: `setReadListener` chưa tuân thủ chế độ đó.
- `getParameter()` cho form URL-encoded hoặc multipart resolver có thể làm body bị parse trước; cần adapter và filter order phù hợp.

Chỉ tối ưu clone/copy khi có bằng chứng **ownership** rõ. Nếu nhiều component có thể sửa cùng mảng, phải ưu tiên tính toàn vẹn và tạo bản sao bảo vệ.

## 7. Tích hợp vào HMAC filter: không đo lẫn nghiệp vụ

Một `OncePerRequestFilter` nên capture, hash và xác thực trước khi cho controller chạy:

~~~java
BoundedReplayableRequest wrapped;
try {
    wrapped = BoundedReplayableRequest.capture(
        request, MAX_BODY_BYTES);
} catch (BoundedReplayableRequest.BodyTooLargeException ex) {
    response.sendError(413);
    return;
}

String bodyDigest = wrapped.sha256LowerHex();

// evidenceParser lấy method, URI, signed headers và digest
// từ request thực tế theo hợp đồng ký.
Authentication candidate =
    evidenceParser.parse(wrapped, bodyDigest);

Authentication verified =
    authenticationManager.authenticate(candidate);
// Provider phải kiểm tra key ACTIVE, đúng secret, MAC,
// timestamp và atomic nonce claim; không được fail open.

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
try {
    chain.doFilter(wrapped, response);
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Đây là **mảnh code minh họa**, không phải filter hoàn chỉnh: các biến, parser và error handlers chưa khai báo. `AuthenticationException` từ chính bước xác thực cần được đưa về `AuthenticationEntryPoint`/failure handler phù hợp; lỗi body quá lớn phải là 413, lỗi dependency phải fail closed.

**Đo latency của authentication tới lúc manager trả kết luận**, không lấy thời gian chạy toàn bộ `chain.doFilter` rồi gọi là HMAC latency. Phần chain sau còn chứa authorization, controller, DB và response serialization. HMAC đã hợp lệ nhưng controller trả 500 vẫn phải được phân biệt trong metric.

Không đăng ký cùng filter hai lần (global Servlet filter + SecurityFilterChain), vì điều đó có thể đọc body hai lần, tăng overhead và claim nonce lần hai thành replay giả.

## 8. WebFlux: backpressure không tự giới hạn số byte

Trong Spring WebFlux, body được biểu diễn dưới dạng `Flux<DataBuffer>`. Reactive Streams backpressure điều tiết **số phần tử được yêu cầu**, không đặt giới hạn tổng bytes mà request có thể gửi.

Ví dụ không an toàn:

~~~java
Mono<DataBuffer> unlimited =
    DataBufferUtils.join(exchange.getRequest().getBody());

Mono<List<DataBuffer>> alsoUnlimited =
    exchange.getRequest().getBody().collectList();
~~~

Hai cách trên có thể giữ body không giới hạn trong RAM. Với Netty pooled/direct buffers, tự thu gom rồi không release khi error/cancel còn tạo memory leak ngoài heap.

### Capture với giới hạn và release

~~~java
import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Mono;

final class BoundedWebFluxBody {

    static Mono<byte[]> capture(
            Publisher<? extends DataBuffer> body,
            int maxBytes) {

        if (maxBytes <= 0) {
            return Mono.error(new IllegalArgumentException(
                "maxBytes must be positive"));
        }

        return DataBufferUtils.join(body, maxBytes)
            .map(joined -> {
                try {
                    byte[] copy =
                        new byte[joined.readableByteCount()];
                    joined.read(copy);
                    return copy;
                } finally {
                    DataBufferUtils.release(joined);
                }
            })
            .defaultIfEmpty(new byte[0]);
    }
}
~~~

`DataBufferUtils.join(body, maxBytes)` thu tối đa `maxBytes` theo contract và phát `DataBufferLimitException` khi vượt ngưỡng. Khi có joined buffer thành công, caller chịu trách nhiệm release nó. Operator quản lý buffer đã tích lũy khi cancel/lỗi theo contract; cần kiểm thử pooled-buffer lifecycle trên stack đang dùng.

**Chi phí:** một hoặc nhiều `DataBuffer` được Netty quản lý, bước join có thể sử dụng composite buffers, còn `new byte[]` tạo **một full-body copy** để giữ dữ liệu cho bước verify/replay. Đây không phải zero-copy hoàn toàn, nhưng đơn giản và phù hợp cho body nhỏ có limit.

### Replay downstream

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import reactor.core.publisher.Flux;

final class ReplayableWebFluxRequest
        extends ServerHttpRequestDecorator {

    private final byte[] body;
    private final DataBufferFactory factory;

    ReplayableWebFluxRequest(
            ServerHttpRequest original,
            byte[] capturedBody,
            DataBufferFactory factory) {
        super(original);
        this.body = capturedBody.clone();
        this.factory = factory;
    }

    @Override
    public Flux<DataBuffer> getBody() {
        return Flux.defer(() ->
            Flux.just(factory.wrap(body.clone())));
    }
}
~~~

Mẫu chủ động copy sang mảng bất biến theo request, rồi tạo thêm bản sao cho từng subscription. Nó dùng nhiều memory hơn phiên bản chỉ một subscriber, nhưng tránh phát lại **cùng pooled buffer đã release** và dễ kiểm soát hơn khi framework có subscriber khác. Nếu tối ưu bớt copy, phải chứng minh chỉ có một consumer và dữ liệu không bị mutate/release sớm.

**Không** `cache()` một `Flux<DataBuffer>` pooled không giới hạn để “cho controller đọc lại”. Không gọi `block()` hoặc SDK Redis/vault blocking trên event loop; nếu bắt buộc dùng API blocking, cần cô lập với scheduler và giới hạn concurrency/timeout, nhưng driver reactive thường phù hợp hơn.

## 9. So sánh chi phí giữa Spring MVC và Spring WebFlux

| Tiêu chí | Spring MVC/Servlet | Spring WebFlux |
| --- | --- | --- |
| Nguồn body | `ServletInputStream`, `Reader` | `Flux<DataBuffer>` |
| Chờ I/O | Thường chờ theo thread mô hình Servlet | Reactive publisher/subscriber |
| Buffer/replay | `HttpServletRequestWrapper` | `ServerHttpRequestDecorator` |
| Memory thường thấy | Heap `byte[]` + downstream DTO | Heap `byte[]` + pooled/direct buffers |
| Limit cho custom HMAC | Đọc tối đa limit+1 byte | `DataBufferUtils.join(body, limit)` |
| Rủi ro | Thread giữ lâu, heap/GC | Buffer leak, cancel/release, event-loop blocking |
| Đọc lại body gốc | Không mặc nhiên đọc hai lần | Không mặc nhiên subscribe lại source |
| Chính sách HMAC | Verify trước nghiệp vụ, giữ raw bytes | Tương tự, qua reactive chain |
| Security context | Servlet `SecurityContext` | Reactor Context / reactive security |

Không thể kết luận một stack luôn nhanh hơn chỉ dựa trên mô hình I/O. Phải đo với **cùng body sizes, signing contract, network, gateway, dependency và concurrency**. WebFlux không loại bỏ CPU hash hay chi phí giữ body; MVC không nhất thiết phải copy toàn bộ body khi tạo một stream replay mới.

## 10. Streaming SHA-256: giảm memory nhưng body vẫn cần nơi lưu

SHA-256 là thuật toán có thể cập nhật incremental. Ví dụ blocking `InputStream`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class StreamingSha256 {

    static String hashHex(InputStream input, long maxBytes)
            throws IOException {
        if (maxBytes <= 0) {
            throw new IllegalArgumentException("Invalid limit");
        }
        try {
            MessageDigest sha =
                MessageDigest.getInstance("SHA-256");
            byte[] scratch = new byte[8192];
            long count = 0;
            int n;

            while ((n = input.read(scratch)) != -1) {
                count += n;
                if (count > maxBytes) {
                    throw new IOException("body_too_large");
                }
                sha.update(scratch, 0, n);
            }
            return HexFormat.of().formatHex(sha.digest());

        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                "SHA-256 unavailable", e);
        }
    }
}
~~~

Bộ nhớ scratch của đoạn này gần 8 KiB bất kể body lớn đến đâu. Nhưng sau khi đọc hết request, **controller vẫn cần body**. Nếu không lưu, bạn không thể replay bytes đã đi qua stream HTTP.

Các lựa chọn:

| Chiến lược | Bộ nhớ | I/O bổ sung | Khi phù hợp |
| --- | --- | --- | --- |
| Buffer đầy đủ có limit trong RAM | O(B), theo concurrency | Ít khi controller đọc từ RAM | JSON nhỏ |
| Stream digest + ghi temp file, verify xong replay | O(chunk) + metadata | Ghi và đọc storage tạm | Upload lớn |
| Signed manifest / chunk-level signing protocol | Theo chunk đã chứng thực | Có thể giảm staging | Streaming thật, hợp đồng bảo mật riêng |
| Digest trên body do proxy đã staging | Backend có thể nhẹ hơn | Chi phí chuyển sang gateway | Edge có trust boundary và assertion đúng |

Nếu chữ ký HMAC bao gồm digest **của toàn bộ body**, không được cho handler tạo side effect trước khi thấy byte cuối và xác minh xong chữ ký. Giao thức chunk signing phải có quy tắc về thứ tự, offset, tổng length, kết thúc stream và replay; **không** chỉ là gọi HMAC riêng trên mỗi `DataBuffer` vì chunk transport có thể thay đổi.

Storage tạm cần quota, encryption/access control, timeout, cleanup khi error/cancel và chống đọc chéo tenant. “Không buffer ở heap” không có nghĩa “không có chi phí”.

## 11. CPU cost: một digest body và một HMAC canonical request

Một hợp đồng minh họa:

~~~text
HMAC-REQUEST-V1
POST
/api/orders?currency=VND
partner-a-k4
2026-11-28T04:00:00Z
b1d76e89-fb93-4de5-9c2d-6f5a836b5d14
<sha256-hex-cua-raw-body>
~~~

Dòng cuối là placeholder, không phải vector có digest thực. Các bên phải thống nhất UTF-8, newline, canonical query, signed headers, body encoding, key ID và cách thể hiện digest.

Quy trình điển hình:

1. Nhận đúng raw body bytes.
2. Tính `SHA-256(body)` **một lần**.
3. Đưa digest (hex/Base64 theo contract) vào canonical request.
4. Dùng `HmacSHA256` trên canonical bytes với **secret của key ID được chỉ định**.
5. So sánh chữ ký theo thao tác an toàn về timing; kiểm tra credential state, timestamp, nonce.

Nếu canonical request ngắn, HMAC trên canonical string có thể rất rẻ so với hash body nhiều MiB. Đừng tối ưu bằng cách parse JSON để lấy “những field quan trọng” rồi bỏ toàn vẹn phần còn lại; đó là **đổi hợp đồng ký**.

### Tránh String conversion vô ích

~~~java
// Không nên nếu hợp đồng ký raw bytes:
String text = new String(rawBody, StandardCharsets.UTF_8);
byte[] reconstructed = text.getBytes(StandardCharsets.UTF_8);
String bodyHash = sha256Hex(reconstructed);
~~~

Bước encode/decode tăng allocation và có thể không bảo toàn bytes nếu input không hợp lệ hoặc charset khác. Hash trực tiếp từ nguồn bytes mà giao thức xác định.

Một request-scoped `BodyEvidence` có thể giữ body length và digest đã tính, để các tầng không hash lại:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

record BodyEvidence(long byteCount, String sha256Hex) {}

final class BodyEvidenceFactory {
    static BodyEvidence fromBytes(byte[] body) {
        try {
            byte[] digest =
                MessageDigest.getInstance("SHA-256")
                    .digest(body);
            return new BodyEvidence(
                body.length,
                HexFormat.of().formatHex(digest));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                "SHA-256 unavailable", e);
        }
    }
}
~~~

`BodyEvidence` **không** là authentication result. Hash không phải bí mật, nên chưa chứng minh ai sở hữu secret.

## 12. Content-Length, transfer encoding và body limits

`Content-Length` có thể giúp từ chối sớm những request quá lớn, nhưng không được tin nó để quyết định kích thước **thực tế**. Có trường hợp header thiếu, bị proxy sửa hoặc request dùng chunked transfer encoding.

Sai:

~~~java
if (request.getContentLengthLong() <= MAX_BYTES) {
    byte[] body = request.getInputStream().readAllBytes();
    // Có thể đọc quá giới hạn mong muốn.
}
~~~

Đúng hơn là:

- Từ chối sớm nếu Content-Length đã được validate và vượt giới hạn.
- Dù header nói gì, vẫn áp **byte-count limit trên stream thực đọc**.
- Từ chối ambiguity ở `Content-Length`/`Transfer-Encoding` tại ingress/proxy để giảm request smuggling.
- Trả 413 khi quá lớn, **không hash body bị cắt** rồi cho xử lý.
- Với gateway giải nén, giới hạn cả bytes nén lẫn bytes sau giải nén để tránh compression bomb.
- Đặt body limit, read timeout, connection limit và rate limit ở ingress **cũng như** HMAC capture.

Trong WebFlux, giới hạn codec như `maxInMemorySize` hữu ích cho decoder nhưng không tự giới hạn một custom `WebFilter` đang join raw body không hạn mức.

## 13. Slow clients, timeout và chi phí trước xác thực

Giả sử hai client đều gửi body 8 KiB:

~~~text
Client A: truyền đủ body trong 3 ms
Client B: truyền đủ body trong 45 giây
~~~

SHA-256 xử lý số byte gần như nhau, nhưng `T_receive` khác lớn. Nếu đợi đủ body trước HMAC, client B có thể giữ socket, thread hoặc reactive subscription lâu **trước khi server biết client có hợp lệ hay không**.

Biện pháp:

1. Giới hạn số kết nối, in-flight captures và timeout đọc request.
2. Đặt deadline/idle timeout phù hợp với endpoint, không dựa riêng vào byte limit.
3. Rate limit lưu lượng trước xác thực, tránh cho một IP hoặc một nhóm kết nối chiếm hết tài nguyên.
4. Có budget riêng cho CPU hashing, heap/direct memory, secret lookup và replay store.
5. Theo dõi tách biệt `time-to-first-byte`, `time-to-last-byte`, body read time, digest time, manager decision time.
6. Trong WebFlux, cleanup buffer/storage tạm trên `cancel` cũng như `error` và `complete`.

### Expect: 100-continue

HTTP/1.1 hỗ trợ `Expect: 100-continue` để client đợi phản hồi sơ bộ trước khi gửi body. Server/gateway có thể từ chối sớm dựa vào header, route, Content-Length đã validate hoặc policy. Nhưng **không thể xác minh chữ ký HMAC trên digest của toàn body trước khi đã nhận toàn body**. Vì vậy, 100-continue chỉ là một tối ưu giao thức có điều kiện, không phải bằng chứng authentication.

## 14. Concurrency và admission control

Một ngưỡng body nhỏ chưa đủ nếu số request đồng thời không giới hạn. Công thức sizing sơ bộ:

~~~text
maxConcurrentCaptures
  × maxBodyBytes
  × estimatedSimultaneousCopyFactor
  ≤ memoryBudgetForHmacBodies
~~~

Cần dự phòng cho memory không tính trong công thức: Netty direct buffers, HTTP/2 flow-control queues, TLS buffers, GC, DTO, heap allocations và temporary disk.

**Admission control** có thể hạn chế số request HMAC đang nhận/capture hoặc số byte đang được giữ. Khi quá tải, hệ thống trả lỗi theo hợp đồng (thường 429 hoặc 503), thay vì để JVM hết memory hoặc tự động bỏ HMAC.

Dấu hiệu cần đo:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| In-flight body captures | Số request chưa hoàn tất capture |
| Buffered bytes / estimated buffer memory | Áp lực heap/direct memory do body |
| Request body size distribution | Phân phối thực tế, không chỉ max limit |
| Allocation rate, GC pause, heap occupancy | Giá của nhiều bản sao body |
| Direct memory và pooled-buffer health | WebFlux/Netty pooling, leak |
| Body read p50/p95/p99 | Chi phí network và capture |
| SHA-256 duration, bytes hashed/s | Chi phí CPU crypto |
| Nonce/secret lookup p95/p99 | Độ trễ dependency không thuộc hash |
| 413/429/503 | Giới hạn tài nguyên hoặc lỗi phụ trợ |

Một gateway có thể buffer body trước khi forward và làm **backend read time** nhỏ đi, nhưng chi phí không biến mất: nó chuyển sang gateway, nơi cũng cần memory/disk/timeouts. Đo end-to-end trước khi kết luận throughput tăng.

## 15. Gateway/proxy: tối ưu có thể thay đổi bytes được ký

| Hành vi tại gateway | Ảnh hưởng chi phí | Điều cần chứng minh |
| --- | --- | --- |
| TLS termination | CPU TLS tại edge, backend nhẹ hơn | Backend phải tin đúng gateway qua mTLS/assertion |
| Request buffering | Backend nhận body nhanh hơn | Limit/temp cleanup tại gateway |
| Route rewrite | Routing tiện hơn | Canonical external/internal target đúng contract |
| JSON transform | Có thể tối ưu payload | Không làm raw-body digest khác chữ ký |
| Gzip decompress/recompress | Tăng CPU và memory tại proxy | Ký bytes trước hay sau transform? |
| Header normalize | Có thể giảm lỗi client | Duplicate/signed header không đổi nghĩa |
| Gateway HMAC verification | Giảm crypto tại backend | Principal assertion bind method/target/body và audience |
| Credential cache | Giảm secret lookup | Key rotation/revocation freshness được đảm bảo |

Không tin `X-Original-URI`, `X-Authenticated-Client` hoặc `X-Forwarded-Host` do client ngoài gửi để “sửa” canonical request. Gateway tin cậy phải strip đầu vào, tạo metadata theo trust contract, và backend xác minh nguồn qua kênh đã xác thực.

Cũng không cache kết quả “signature này hợp lệ” rồi dùng lại để cho cùng request chạy lần nữa. Một request gửi lại với **cùng nonce/signature** phải bị coi là replay dù digest đúng. Cache credential/secret chỉ an toàn khi vẫn kiểm tra **đúng key version và trạng thái revoked/disabled đủ mới**.

## 16. Chọn chiến lược theo endpoint

| API | Chiến lược ưu tiên | Đánh đổi |
| --- | --- | --- |
| GET/body rỗng | Dùng digest của mảng rỗng nếu contract có body hash | Không cần body buffer |
| POST JSON vài KiB | Bounded heap buffer, hash một lần, replay | Đơn giản, predictable |
| POST JSON vài trăm KiB | Buffer limit + concurrency budget | GC/heap đáng quan sát |
| Multipart/file vài GiB | Stream digest tới storage tạm, verify trước commit | Disk I/O, quota, cleanup |
| Long-lived streaming | Signed chunks/manifest đã thiết kế riêng | Protocol phức tạp |
| Gateway-verified webhook | Verify ở edge, internal assertion/mTLS vào service | Gateway trở thành security boundary |

**Không** tăng `maxBodyBytes` của mọi endpoint lên mức của upload lớn. Phân tách route, policy và backpressure/admission theo workload để tránh một loại request chiếm hết tài nguyên của hệ thống.

## 17. Benchmark SHA-256 và load test toàn tuyến

### Microbenchmark

Có thể dùng JMH để đo SHA-256 cho những kích thước body đại diện. Ví dụ:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(1)
public class Sha256BodyBenchmark {

    @Param({"0", "1024", "65536", "1048576"})
    int size;

    byte[] payload;

    @Setup(Level.Trial)
    public void prepare() {
        payload = new byte[size];
        new java.security.SecureRandom().nextBytes(payload);
    }

    @Benchmark
    public byte[] digest()
            throws NoSuchAlgorithmException {
        return MessageDigest.getInstance("SHA-256")
            .digest(payload);
    }
}
~~~

JMH cần thư viện/plugin benchmark, không phải class có sẵn trong Spring Boot. Bài test trên không đo heap copies, HTTP upload, secret store, nonce Redis hoặc controller. Dùng kết quả JMH để **so sánh chi phí digest**, không suy ra capacity toàn hệ thống.

### Load test end-to-end

Nên kiểm thử theo ma trận:

| Trục | Kịch bản |
| --- | --- |
| Body | 0 B, 1 KiB, 16 KiB, 256 KiB, 1 MiB, limit+1 |
| Concurrent clients | 1, 10, 100, 1.000 và mức thực tế |
| Network | LAN/WAN, slow upload, connection reset |
| HMAC | Valid, wrong signature, bad timestamp, replay |
| Credential | ACTIVE, REVOKED, K3/K4 rotation |
| Dependencies | Redis/vault nhanh, chậm, timeout, failover |
| Proxy | Buffered, streamed, URI rewrite, gzip |
| Memory | Heap, direct memory, GC, pooled-buffer cleanup |
| Response | 2xx, 401, 403, 413, 429, 503 |

Mỗi request valid trong test throughput phải có **timestamp và nonce riêng**; nếu load tool dùng lại nonce, đa số request bị chặn replay và kết quả đo không đại diện cho đường valid. Một nhóm test khác phải cố ý replay để chứng minh chỉ một attempt qua được guard.

Báo cáo không chỉ throughput, mà còn **p95/p99, body-read duration, digest duration, allocation rate, CPU, memory peak, 413 rate và không có side effect từ request lỗi**.

## 18. Micrometer: đo body read, digest và kết quả xác thực riêng

Ví dụ helper Micrometer với route group cố định, không gắn ID người gọi vào labels:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

final class HmacBodyMetrics {
    private final Timer read;
    private final Timer hash;
    private final DistributionSummary bytes;

    HmacBodyMetrics(MeterRegistry registry) {
        Objects.requireNonNull(registry);
        read = Timer.builder("hmac.body.read.duration")
            .tag("route", "orders")
            .register(registry);
        hash = Timer.builder("hmac.body.hash.duration")
            .tag("route", "orders")
            .register(registry);
        bytes = DistributionSummary.builder("hmac.body.size")
            .baseUnit("bytes")
            .tag("route", "orders")
            .register(registry);
    }

    void captured(long startedNanos, long size) {
        read.record(
            System.nanoTime() - startedNanos,
            TimeUnit.NANOSECONDS);
        bytes.record(size);
    }

    void hashed(long startedNanos) {
        hash.record(
            System.nanoTime() - startedNanos,
            TimeUnit.NANOSECONDS);
    }
}
~~~

Sử dụng trong adapter:

~~~java
long readStart = System.nanoTime();
BoundedReplayableRequest wrapped =
    BoundedReplayableRequest.capture(request, MAX_BYTES);
metrics.captured(
    readStart, wrapped.getContentLengthLong());

long hashStart = System.nanoTime();
String digest = wrapped.sha256LowerHex();
metrics.hashed(hashStart);

// Sau đây mới lookup credential, verify HMAC,
// kiểm tra timestamp/nonce và tạo principal.
~~~

Đoạn trên ghi số liệu trên **đường thành công**; production cần thêm xử lý 413, timeout, cancel, IOException và dependency failures trong nhánh outcome thích hợp. Không gọi request có body capture thành công là **HMAC valid**: chỉ sau **key/HMAC/timestamp/nonce đều hợp lệ** mới được ghi auth-result valid.

Timer dùng `System.nanoTime()` đơn điệu; không dùng wall clock để đo duration. Ngược lại, kiểm tra `X-Timestamp` của HMAC cần thời gian UTC đáng tin từ server và cửa sổ được định nghĩa.

### Các metric không nên gộp

| Metric | Kết luận |
| --- | --- |
| Body read duration | Thời gian chờ + capture body |
| Body digest duration | Chi phí SHA-256/body |
| Authentication duration | Credential + canonical HMAC + timestamp/nonce |
| Authorization duration | Policy principal/tenant/resource |
| HTTP server duration | Toàn request, gồm business |
| Authentication outcome | Valid, invalid, not evaluated, unavailable, error |

Không dùng `client_id`, `key_id`, `nonce`, `tenant_id`, raw URI hay body hash làm Prometheus labels: chúng có cardinality cao hoặc nhạy cảm. Chỉ dùng route group, result, reason enum, contract version và region từ allowlist.

## 19. Các tối ưu nguy hiểm cần tránh

### A. Bỏ kiểm tra body khi request quá lớn

Nếu body thuộc canonical contract, việc bỏ hash trong chế độ quá tải làm mất bảo vệ toàn vẹn. **Trả 413 hoặc áp luồng upload riêng**, không chuyển sang ký header-only.

### B. Chỉ tin header digest do client cung cấp

HMAC có thể ký header digest, nhưng server vẫn phải xác minh header này khớp body thực nhận; nếu không, body bị tráo sau khi ký có thể lọt qua.

### C. Deserialize rồi serialize JSON để tính digest

Vừa tăng CPU/allocation vừa đổi bytes khi format khác. Hash raw bytes hoặc định nghĩa canonical JSON rõ ràng trong giao thức.

### D. Cache quyết định authenticated theo signature

Request cùng signature và nonce là **replay** ở lần sau. Không lấy cache hit làm lý do bỏ nonce store.

### E. Ghi nonce trước khi signature được xác nhận

Attacker không biết secret vẫn có thể gửi nonce đoán được để chiếm nonce của client hợp lệ. Claim **sau** khi HMAC đúng và bằng thao tác atomic.

### F. Chỉ dựa vào Content-Length

Header không đáng tin tuyệt đối, nhất là qua proxy/chunked. Áp giới hạn bytes thực đọc, timeout và concurrency budget.

### G. Bỏ kiểm tra revocation để dùng credential cache nhanh

Key đã REVOKED vẫn có thể tạo HMAC hợp lệ với secret cũ. Cache phải tuân thủ freshness và fail closed khi không chứng minh được state.

### H. Reuse pooled DataBuffer sau khi release

Tối ưu không copy mà chưa chứng minh lifecycle có thể gây dữ liệu hỏng hoặc leak direct memory. Test cả success/error/cancel.

### I. Ghi raw body vào log để debug latency

Payload có thể chứa thông tin cá nhân, thanh toán hoặc secrets. Chỉ ghi size, route, duration, reason và correlation ID được quản lý; không dump body hoặc chữ ký.

### J. Cho nghiệp vụ chạy trước khi verify full-body digest

Với HMAC ký digest toàn body, server chưa thể kết luận chữ ký đúng trước byte cuối. Không phát event/ghi DB trước khi verify hoặc trước một giao thức staging-commit được thiết kế đầy đủ.

## 20. Ma trận kiểm thử correctness và performance

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| PERF-01 | Body rỗng | Hash của byte[0] đúng hợp đồng |
| PERF-02 | Body JSON nhỏ | HMAC đúng; handler đọc đúng bytes |
| PERF-03 | Body chia nhiều chunks | Digest không phụ thuộc chunk boundary |
| PERF-04 | Body đúng size limit | Được xét tiếp khi signature hợp lệ |
| PERF-05 | Body vượt limit 1 byte | 413; không đọc/buffer vô hạn |
| PERF-06 | Không có Content-Length | Vẫn áp byte limit |
| PERF-07 | Content-Length khai sai | Không được vượt limit |
| PERF-08 | Thay whitespace/CRLF/Unicode sau khi ký | HMAC mismatch trên raw bytes |
| PERF-09 | JSON deserialize-serialize | Negative test phát hiện bytes thay đổi |
| PERF-10 | HMAC sai | Không claim nonce, không side effect |
| PERF-11 | Nonce replay qua hai gateway | Chỉ một claim thành công |
| PERF-12 | Key REVOKED | Không bypass bằng cache nhanh |
| PERF-13 | HMAC valid nhưng tenant B bị deny | 403/404 theo policy, không truy cập B |
| PERF-14 | Slow upload dưới limit | Read timeout/admission limit hoạt động |
| PERF-15 | Nhiều request gần size limit | Memory/GC/direct buffer trong budget |
| PERF-16 | WebFlux cancel giữa chừng | Không leak DataBuffer/temp storage |
| PERF-17 | Multipart/file quá lớn | 413 hoặc đúng staging path |
| PERF-18 | Gateway rewrite URI | Canonical target đúng hoặc signature fail |
| PERF-19 | Gzip/compression bomb | Limit cả compressed/decompressed size |
| PERF-20 | Redis/secret store timeout | Fail closed, không 2xx |
| PERF-21 | Double filter registration | Không claim nonce hai lần |
| PERF-22 | Retry sau network timeout | Nonce mới + idempotency nghiệp vụ |
| PERF-23 | Metrics exporter lỗi | Không làm bypass authentication |
| PERF-24 | Timestamp ở biên window | Không mở rộng cửa sổ do tối ưu |
| PERF-25 | WebFlux subscribe lại body | Không reuse pooled buffer đã release |
| PERF-26 | Proxy trả 413 trước backend | Ingress metrics ghi đúng; backend không thấy |
| PERF-27 | p99 tăng sau bật body signing | Tách read/hash/key/nonce/downstream latency |
| PERF-28 | Body limit bằng 0 theo policy route | Xử lý rõ request body rỗng hoặc reject, không đọc vô hạn |

### Unit test MVC cho wrapper

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class BoundedReplayableRequestTest {

    @Test
    void bodyCanBeReadTwiceWithoutChanges() throws Exception {
        byte[] content = "{\"id\":\"o-401\"}"
            .getBytes(StandardCharsets.UTF_8);

        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/api/orders");
        request.setContent(content);

        BoundedReplayableRequest wrapped =
            BoundedReplayableRequest.capture(request, 1024);

        assertArrayEquals(
            content, wrapped.getInputStream().readAllBytes());
        assertArrayEquals(
            content, wrapped.getInputStream().readAllBytes());
    }

    @Test
    void rejectsPayloadOverLimit() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/api/orders");
        request.setContent(new byte[1025]);

        assertThrows(
            BoundedReplayableRequest.BodyTooLargeException.class,
            () -> BoundedReplayableRequest.capture(request, 1024));
    }
}
~~~

Đây là test của wrapper, **chưa kiểm chứng HMAC đầy đủ**. Cần test với signer độc lập, credential registry/key rotation, timestamp/nonce store, SecurityFilterChain và controller thật. Với WebFlux, dùng `StepVerifier`/`WebTestClient` và test pooled Netty buffer dưới cancellation. Load test phải ghi nhận resource budgets đồng thời với assertions bảo mật.

## 21. Bài tập phân tích bottleneck

Một hệ thống Spring MVC ký raw JSON body nhưng filter hiện thực như sau:

~~~java
byte[] first = request.getInputStream().readAllBytes();
String json = new String(first, StandardCharsets.UTF_8);
byte[] reconstructed = objectMapper.writeValueAsBytes(
    objectMapper.readTree(json));
String digest = sha256Hex(reconstructed);
verifyHmac(digest);
chain.doFilter(request, response);
~~~

Ở peak traffic, có 3.000 request đồng thời và p99 tăng mạnh. Ingress có thể gzip payload, rewrite path và Redis nonce store có p99 cao. Nhóm kỹ thuật đề xuất tăng heap và bỏ body digest với request hơn 100 KiB.

Hãy trả lời:

1. Vì sao cách tính digest hiện tại có thể sai hợp đồng raw bytes?
2. Có những allocation/copy không cần thiết nào?
3. Vì sao controller có thể nhận body rỗng?
4. Nếu mỗi request giữ 1 MiB, 3.000 request đồng thời, riêng một bản raw body có thể chiếm bao nhiêu bộ nhớ?
5. Vì sao tối ưu SHA-256 không chắc giải quyết p99?
6. Cần đo các đoạn read, copy, SHA-256, secret lookup, nonce claim thế nào?
7. Có thể dùng `ContentCachingRequestWrapper` để tự động rewind không?
8. Khi gateway giải nén gzip, phải xác định bytes được ký ở điểm nào?
9. Khi body vài GiB, chiến lược nào cho phép verify trước side effect mà không giữ toàn bộ RAM?
10. Những tối ưu nào bị cấm vì phá ranh giới xác thực hoặc phân quyền?

**Định hướng:** dùng bounded replayable request; digest raw bytes đúng hợp đồng, không JSON round-trip; giới hạn concurrency và ingress; đo p99 theo giai đoạn; cải thiện dependency gây bottleneck. Nếu payload quá lớn, chọn storage tạm/streaming protocol có kiểm chứng. **Không** bỏ body hash, atomic nonce, key revocation hoặc tenant authorization.

## 22. Checklist production cho chi phí đọc body

- Canonical request đã định nghĩa method/URI/signed headers/body digest/key ID/timestamp/nonce chính xác theo bytes.
- Digest được tính trực tiếp từ raw body bytes, không deserialize/serialize lại khi hợp đồng ký raw bytes.
- Body-size limit có tại ingress/container và HMAC capture; kiểm tra bytes thực nhận, không tin riêng Content-Length.
- Spring MVC phát lại body bằng wrapper thực sự; không giả định `ContentCachingRequestWrapper` rewind tự động.
- WebFlux giới hạn `DataBufferUtils.join` hoặc có streaming guard; quản lý release/cancel của pooled buffers đúng.
- Tránh full-body copies không cần thiết nhưng vẫn giữ immutable ownership cho bytes đã verify.
- Có timeout/slow-client policy, concurrency admission và memory budget bao gồm heap/direct memory/GC/storage tạm.
- Hash body một lần; không hash lại ở mọi filter nếu có thể chia sẻ request-scoped digest đáng tin.
- Credential key ID/version/ACTIVE/REVOKED được kiểm tra; secret cache không được bypass revocation.
- Nonce/timestamp được ký, claim nguyên tử **sau HMAC đúng** và không bỏ qua khi replay store lỗi.
- Principal HMAC hợp lệ vẫn phải qua authorization tenant/action/resource.
- Gateway rewrite, Host/forwarded headers và Content-Encoding được kiểm thử theo hợp đồng ký; không tin metadata do client tự khai.
- API upload lớn dùng staging/chunk-signing protocol riêng thay vì buffer hàng GiB trong HMAC filter.
- Microbenchmark SHA-256 và load test toàn HTTP được tách biệt; không suy capacity chỉ từ JMH.
- Dashboard có body bytes/read p95/p99, SHA-256 time, auth decision time, nonce latency, heap/direct memory và rejection rates.
- Metric labels có cardinality hữu hạn; không log body nhạy cảm, HMAC signature, shared secret hay canonical request đầy đủ.
- Test security và performance cùng chạy; request sai chữ ký, replay hoặc vượt limit không tạo side effect.
- Test bao gồm slow clients, gzip, multipart, gateway rewrite, cancellation, key revoke, Redis timeout/failover và multi-instance.
- Khi quá tải, hệ thống từ chối/giới hạn đúng policy, không chuyển sang chế độ bỏ ký body.
- Mọi tối ưu phải được so sánh trước/sau bằng workload tương đương, đồng thời kiểm tra lại test vectors HMAC độc lập.

**Chi phí đọc body cho HMAC là tổng hợp của thời gian nhận dữ liệu, CPU hashing, memory copies, khả năng replay downstream và áp lực concurrency.** Tối ưu hiệu quả là đặt giới hạn ở đúng tầng, giảm copy không cần thiết, đo từng giai đoạn và dùng streaming/staging cho payload lớn. Các tối ưu này chỉ được coi là thành công khi vẫn bảo vệ nguyên vẹn HMAC canonical request, timestamp/nonce chống replay, key rotation và authorization độc lập.
