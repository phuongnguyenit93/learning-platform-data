# Đọc request body trong custom authentication filter dùng HMAC

## 1. Vì sao đọc request body là một phần quan trọng của xác thực HMAC?

Một HTTP API có thể dùng **shared secret** để tạo chữ ký HMAC nhằm xác minh nguồn gửi và tính toàn vẹn của request. Nếu hợp đồng ký bao gồm body, server phải tính chữ ký trên **đúng dữ liệu mà client đã ký**. Chỉ một byte khác nhau, chẳng hạn dấu cách, xuống dòng hoặc cách encode JSON, có thể làm kết quả HMAC thay đổi hoàn toàn.

Trong Spring Security, custom authentication filter thường chạy **trước controller**. Filter cần đọc body để lấy SHA-256 digest hoặc các bytes phục vụ canonical request, nhưng controller cũng cần đọc chính body đó thông qua `@RequestBody`. Servlet request body thông thường được cung cấp dưới dạng stream, nên một lần đọc ở filter có thể khiến downstream thấy stream đã đến cuối.

Ví dụ client gọi:

~~~http
POST /api/hmac/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-v3
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 9d73f4de-8b9f-4e7a-99f4-8498ed6e57da
X-Signature: <chu-ky-base64-minh-hoa>

{"orderId":"o-100","amount":120000}
~~~

Ở đây `X-Signature` là chỗ giữ chỗ, chưa phải chữ ký được tính. Một hợp đồng HMAC minh họa có thể ký method, canonical URI, key ID, timestamp, nonce và **SHA-256 của body bytes**. Filter phải giải quyết đồng thời ba vấn đề:

1. Lấy body đúng dạng bytes do Servlet container cung cấp, không tự ý deserialize rồi serialize lại.
2. Tái cung cấp **cùng body bytes** cho controller hoặc các filter phía sau.
3. Không làm mất các kiểm tra khác: trạng thái key, canonical request, chữ ký HMAC, timestamp/nonce chống replay và phân quyền.

Đây là trọng tâm của bài **Đọc request body** trong chương **Custom authentication filter** thuộc module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`.

## 2. Body trong Servlet API: stream đọc một lần

Với Spring MVC chạy trên Servlet, `HttpServletRequest` thường cung cấp nội dung request qua:

- `getInputStream()`: nhận `ServletInputStream` chứa các byte request body.
- `getReader()`: đọc nội dung theo encoding được công bố/định nghĩa.
- `getParameter(...)`: với một số content type, đặc biệt form URL-encoded, có thể kích hoạt parse body và ảnh hưởng cách đọc stream.
- Bộ chuyển đổi của Spring MVC: `@RequestBody` thường đọc body qua `HttpMessageConverter` sau khi filter chạy.

Đừng giả định có thể gọi `request.getInputStream().readAllBytes()` hai lần và thu được cùng dữ liệu. Servlet container có thể chỉ cung cấp một stream gốc; lần hai thường trả rỗng hoặc đã đi tới EOF.

Ví dụ **sai**:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    byte[] body = request.getInputStream().readAllBytes();
    String bodyHash = sha256Hex(body);
    verifyHmac(request, bodyHash); // Giả định có hàm của ứng dụng

    chain.doFilter(request, response);
    // Controller dùng @RequestBody có thể nhận body rỗng.
}
~~~

Đây là lỗi vòng đời stream, không phải lỗi HMAC. Ngay cả khi chữ ký xác minh đúng, nghiệp vụ phía sau vẫn có thể không nhận được body.

### Body bytes khác với object JSON

Hai body sau có cùng dữ liệu JSON theo cách hiểu thông thường nhưng **khác bytes**:

~~~json
{"orderId":"o-100","amount":120000}
~~~

~~~json
{
  "orderId": "o-100",
  "amount": 120000
}
~~~

Nếu hợp đồng quy định `SHA-256(rawBodyBytes)`, hai body sinh digest khác nhau. Tương tự:

- `{"a":1,"b":2}` khác `{"b":2,"a":1}`.
- `"\u00e9"` và `"é"` có thể biểu diễn giá trị JSON tương đương nhưng bytes khác nhau.
- Dấu xuống dòng `LF` và `CRLF` khác nhau.
- UTF-8, UTF-16, BOM, khoảng trắng cuối body có thể làm digest khác.
- Body rỗng `byte[0]` khác JSON `{}` hoặc chuỗi văn bản `null`.

Vì vậy, **không parse JSON rồi dùng `ObjectMapper.writeValueAsBytes(...)` để tái tạo body ký** trừ khi giao thức đã định nghĩa và kiểm thử một chuẩn canonical JSON cụ thể.

## 3. Đọc body ở thời điểm nào trong SecurityFilterChain?

Một kiến trúc HMAC dùng Spring Security 6 (Java 17, Jakarta Servlet API) có thể gồm:

~~~mermaid
flowchart TD
    A["HTTP client ký request"] --> B["Servlet container / reverse proxy"]
    B --> C["SecurityFilterChain"]
    C --> D["HmacAuthenticationFilter: đọc body có giới hạn"]
    D --> E["Tạo replayable request + body digest"]
    E --> F["AuthenticationManager / HmacAuthenticationProvider"]
    F --> G{"Credential, HMAC, timestamp, nonce hợp lệ?"}
    G -->|Không| X["Từ chối xác thực"]
    G -->|Có| H["Thiết lập SecurityContext"]
    H --> I["AuthorizationManager"]
    I -->|Được phép| J["Controller @RequestBody đọc lại cùng body"]
    I -->|Bị từ chối| Y["403 theo chính sách"]
~~~

Filter HMAC phải chạy trước điểm cần một principal đã xác thực. Đồng thời, **không được để một filter/interceptor trước đó tiêu thụ body** mà không cung cấp lại bytes chính xác. Cần kiểm tra ảnh hưởng của request logging, multipart resolver, form parsing, request wrapper hoặc bộ kiểm tra payload được áp dụng trước HMAC filter.

Việc đặt filter trước `UsernamePasswordAuthenticationFilter` chỉ là một cách bố trí thường gặp; thứ tự chính xác phụ thuộc các chain và filter đã cài. `SecurityFilterChain` phải match đúng endpoint HMAC, không để một chain khác tiếp nhận request trước. Nếu custom filter vừa được đăng ký làm Servlet filter toàn cục vừa nằm trong Spring Security chain, nó có thể chạy hai lần, đọc body hai lần hoặc ghi nonce hai lần.

**Ranh giới tin cậy:** body digest là một thành phần của canonical request, nhưng filter không được gán danh tính chỉ vì đã đọc body. Danh tính xuất hiện sau khi `AuthenticationManager` xác minh credential, chữ ký và các điều kiện chống replay. Sau đó, authorization mới quyết định principal có quyền gọi endpoint, tenant và resource hay không.

## 4. ContentCachingRequestWrapper: hữu ích nhưng không tự phát lại body

Spring Web cung cấp `ContentCachingRequestWrapper`. Wrapper này **lưu vào cache những bytes được đọc qua stream/reader của nó**, giúp một số tình huống logging hoặc kiểm tra nội dung sau khi request được xử lý.

Ví dụ:

~~~java
var wrapper = new ContentCachingRequestWrapper(request);
byte[] beforeRead = wrapper.getContentAsByteArray();
// Có thể vẫn rỗng vì body chưa từng được đọc qua wrapper.

byte[] read = wrapper.getInputStream().readAllBytes();
byte[] cached = wrapper.getContentAsByteArray();
// Lúc này cache có thể chứa những bytes đã đọc.
~~~

Có ba hiểu lầm cần tránh:

1. **Bọc request không tự động đọc body.** `getContentAsByteArray()` có thể rỗng nếu chưa có code nào đọc stream.
2. **Cache để xem lại khác với stream có thể đọc lại.** Sau khi filter đọc hết `wrapper.getInputStream()`, downstream không mặc nhiên có thể gọi lại và đọc từ đầu.
3. **Cache limit không thay thế giới hạn kích thước request.** Giới hạn của cache có thể chỉ làm cache dừng lưu thêm, trong khi luồng body thực tế vẫn có nhiều dữ liệu. Nếu ký digest trên cache đã bị cắt, server có thể xác minh một payload khác với payload được nghiệp vụ nhận.

Khi mục tiêu là vừa đọc body **trước khi gọi AuthenticationManager** vừa cho controller đọc lại, cần một **replayable request wrapper** thật sự hoặc một pipeline có khả năng chia sẻ dữ liệu gốc mà không làm mất stream.

Nếu chỉ muốn quan sát body **sau khi controller đã đọc**, `ContentCachingRequestWrapper` có thể phù hợp. Với HMAC ký body, thường phải xác minh trước khi controller thực hiện nghiệp vụ, nên cách đọc trước và phát lại có giới hạn cần được thiết kế chủ động.

## 5. Hợp đồng canonical request và body digest

Giả sử hợp đồng ký `HMAC-REQUEST-V1` dùng chuỗi UTF-8, mỗi trường ở một dòng, không tự động thêm dòng trống cuối:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/orders?currency=VND
partner-a
partner-a-v3
2026-11-28T04:00:00Z
9d73f4de-8b9f-4e7a-99f4-8498ed6e57da
<sha256-lowercase-hex-cua-raw-body-bytes>
~~~

Dòng cuối là placeholder; vector ký hoàn chỉnh phải dùng SHA-256 hex thật của body. Công thức:

\[
\operatorname{bodyDigest} =
\operatorname{HexLower}(\operatorname{SHA256}(\operatorname{rawBodyBytes}))
\]

\[
\operatorname{signature} =
\operatorname{Base64}
\left(
\operatorname{HMAC\mbox{-}SHA256}
(\operatorname{sharedSecret}, \operatorname{UTF8}(\operatorname{canonicalRequest}))
\right)
\]

Ở đây **body digest khác chữ ký HMAC**. Body digest không phải bí mật và tự nó không xác thực người gửi. HMAC phải bao gồm body digest (cùng các trường theo hợp đồng) để ràng buộc bytes body với danh tính sở hữu secret.

Các bên phải thỏa thuận rõ:

| Thành phần | Điều cần cố định để client và server tương thích |
| --- | --- |
| Method | Viết hoa? Dùng method container thấy hay method trước proxy? |
| URI | Path/query sau chuẩn hóa nào? Có giữ duplicate query và percent-encoding không? |
| Signed headers | Tên header, thứ tự, case, khoảng trắng, giá trị trùng và cách nối |
| Body | Bytes nguyên gốc tại lớp ứng dụng hay nội dung sau giải nén? |
| Body digest | SHA-256 hex lowercase, Base64 hoặc format khác? |
| Newline | Ký tự phân cách `LF`, có dòng cuối hay không? |
| Timestamp/nonce | Chuỗi định dạng chuẩn, cửa sổ cho phép và cách chống replay |
| Key ID / tenant | Ràng buộc vào canonical string và kiểm tra owner/policy |

**Không tự chọn cách chuẩn hóa khác ở gateway và service.** Nếu proxy giải nén, thay query, chuẩn hóa URL hoặc đổi encoding, bytes mà client ký và bytes mà verifier dùng có thể không còn giống nhau.

### Mẫu tính SHA-256 trực tiếp từ bytes

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class BodyDigest {
    static String sha256Hex(byte[] body) {
        try {
            byte[] digest =
                MessageDigest.getInstance("SHA-256").digest(body);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Với body rỗng (không có bytes), SHA-256 hex phải là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

**Không bỏ dòng body hash khỏi canonical request chỉ vì request không có body.** Nếu hợp đồng ký có trường body digest, hãy sử dụng digest của mảng bytes rỗng, trừ khi hợp đồng định nghĩa một giá trị khác một cách tường minh.

## 6. Xây dựng replayable HttpServletRequest với giới hạn kích thước

Một cách phù hợp cho **API JSON nhỏ, xử lý Servlet đồng bộ** là buffer body tối đa một ngưỡng định sẵn, sau đó mỗi lần `getInputStream()` tạo một stream mới đọc từ buffer bất biến trong phạm vi request. Ví dụ dưới đây dùng Java 17 và Jakarta Servlet API.

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

public final class ReplayableBodyRequest extends HttpServletRequestWrapper {
    private final byte[] body;

    // Giới hạn được quyết định theo endpoint/policy, ví dụ 1 MiB.
    public static ReplayableBodyRequest capture(
            HttpServletRequest request, int maxBytes) throws IOException {

        if (maxBytes < 0 || maxBytes == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid body limit");
        }

        // Chỉ đọc tối đa maxBytes + 1; không gọi readAllBytes()
        // trên một payload có thể lớn vô hạn.
        InputStream original = request.getInputStream();
        byte[] read = original.readNBytes(maxBytes + 1);
        if (read.length > maxBytes) {
            throw new BodyTooLargeException();
        }

        return new ReplayableBodyRequest(request, read);
    }

    private ReplayableBodyRequest(
            HttpServletRequest request, byte[] rawBody) {
        super(request);
        this.body = rawBody.clone();
    }

    public String sha256Hex() {
        try {
            byte[] digest =
                MessageDigest.getInstance("SHA-256").digest(body);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public byte[] bodySnapshot() {
        return body.clone();
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream source = new ByteArrayInputStream(body);
        return new ServletInputStream() {
            @Override
            public int read() {
                return source.read();
            }

            @Override
            public int read(byte[] b, int off, int len) {
                return source.read(b, off, len);
            }

            @Override
            public boolean isFinished() {
                return source.available() == 0;
            }

            @Override
            public boolean isReady() {
                // Wrapper này chỉ dùng cho luồng Servlet đồng bộ.
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException(
                    "Non-blocking I/O requires a separate adapter");
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

    public static final class BodyTooLargeException extends IOException {
        public BodyTooLargeException() {
            super("Request body exceeds configured limit");
        }
    }
}
~~~

Đây là **wrapper cho luồng xử lý đồng bộ, body nhỏ**; nó có giới hạn quan trọng:

- `isReady()` và `setReadListener()` không triển khai đúng hợp đồng Servlet **non-blocking I/O**. Không sử dụng wrapper này cho pipeline `ReadListener`, servlet async hoặc streaming reactive; cần adapter tuân thủ API async riêng.
- `readNBytes(maxBytes + 1)` giới hạn số bytes đi vào bộ nhớ cho mỗi request nhưng vẫn phải cấu hình giới hạn tổng request ở reverse proxy/Servlet container, timeout đọc và giới hạn số request đồng thời. `maxBytes` phải là ngưỡng nhỏ, do server quyết định, không nhận từ client.
- Trong thực tế có thể cần xử lý thêm `getParameterMap()` cho `application/x-www-form-urlencoded`, multipart và khả năng wrapper giữ metadata của entity. Đừng giả định body form đã được đọc bằng `getParameter` trước khi filter này chạy.
- `getReader()` phục vụ downstream đọc text theo encoding. **Để tính HMAC luôn dùng bytes**, không chuyển qua `Reader` rồi encode lại.
- `bodySnapshot()` trả bản sao, tránh code khác thay đổi mảng buffer được dùng để tính digest hoặc phát lại body.

Khi body lớn hoặc streaming, chiến lược buffer toàn bộ sẽ không phù hợp. Cần thiết kế khác, ví dụ vừa tính digest khi stream đi qua vừa lưu tạm có giới hạn để service đọc lại, hoặc xác minh ở điểm có thể dùng cùng một luồng bytes trước khi thực thi nghiệp vụ. Cơ chế lưu tạm phải có phân quyền, giới hạn dung lượng, hủy an toàn và kiểm thử sự cố.

### Vì sao giới hạn bộ nhớ rất quan trọng?

Nếu mỗi request được buffer tối đa 1 MiB và hệ thống đang giữ 2.000 request đồng thời, riêng dữ liệu body đã có thể chiếm gần 2 GiB, chưa kể bản sao, object Java, parser và overhead GC. Một lệnh `readAllBytes()` không giới hạn có thể tạo lỗ hổng từ chối dịch vụ.

Cần xác định giới hạn theo loại endpoint, kích thước JSON dự kiến, số request đồng thời, budget heap và chính sách từ chối; thông thường trả **413 Content Too Large** (nhiều stack vẫn dùng tên cũ Payload Too Large) nếu vượt ngưỡng. Không đọc tiếp vô hạn hoặc bỏ qua bytes vượt ngưỡng rồi xác minh trên body bị cắt.

## 7. Tích hợp wrapper vào custom authentication filter

Filter cần chuẩn bị một request đã buffer trước khi gọi `AuthenticationManager`, rồi truyền **chính wrapper đó** tới filter chain phía sau. `AuthenticationManager` và provider xác minh HMAC theo canonical request, trạng thái credential, timestamp/nonce; controller đọc lại body sau khi filter thành công.

Một cách tách trách nhiệm:

- `ReplayableBodyRequest`: đọc body có giới hạn, giữ bytes và tạo các stream phát lại.
- `HmacEvidenceExtractor`: parse signed headers, canonical URI, xây chuỗi ký với body digest.
- `AuthenticationManager`: gọi provider HMAC tương ứng, xác minh secret và replay.
- `AuthenticationEntryPoint`: tạo phản hồi xác thực thất bại.
- `AuthorizationManager`: kiểm tra principal, tenant và quyền endpoint.

Ví dụ cấu trúc Spring Security 6, bỏ qua phần triển khai extractor cụ thể:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

interface HmacEvidenceExtractor {
    // Trả Authentication chưa được xác thực; dùng các
    // giá trị từ HTTP thực tế và bodyDigest do wrapper tạo.
    Authentication extract(
        HttpServletRequest request,
        String bodyDigestHex
    ) throws AuthenticationException;
}

public final class HmacBodyAuthenticationFilter
        extends OncePerRequestFilter {

    private static final int MAX_BODY_BYTES = 1024 * 1024;

    private final AuthenticationManager manager;
    private final AuthenticationEntryPoint entryPoint;
    private final HmacEvidenceExtractor extractor;

    public HmacBodyAuthenticationFilter(
            AuthenticationManager manager,
            AuthenticationEntryPoint entryPoint,
            HmacEvidenceExtractor extractor) {
        this.manager = manager;
        this.entryPoint = entryPoint;
        this.extractor = extractor;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {

        ReplayableBodyRequest wrapped;
        Authentication authenticated;

        try {
            wrapped = ReplayableBodyRequest.capture(
                request, MAX_BODY_BYTES);

            Authentication candidate =
                extractor.extract(wrapped, wrapped.sha256Hex());

            authenticated = manager.authenticate(candidate);
            if (authenticated == null
                    || !authenticated.isAuthenticated()) {
                throw new BadCredentialsException(
                    "authentication_failed");
            }

        } catch (ReplayableBodyRequest.BodyTooLargeException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(
                HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE);
            return;

        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, ex);
            return;
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(wrapped, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Giới hạn của mẫu filter:** đây là ví dụ kiến trúc, không phải một hệ thống xác thực chạy độc lập. `HmacEvidenceExtractor` phải dựng canonical request từ method, URI, query và signed headers theo hợp đồng, **không dùng chuỗi canonical do client tự cung cấp**. `AuthenticationManager` phải được nối với provider HMAC có kiểm tra trạng thái credential, secret, timestamp và nonce. Endpoint khác có thể cần chain riêng.

Nếu việc đọc body gây `IOException` do kết nối lỗi hoặc input stream bị hỏng, filter không được bỏ qua HMAC rồi cho controller chạy; ví dụ để lỗi lan truyền sang cơ chế xử lý lỗi hạ tầng. Cần bảo đảm response lỗi nhất quán, không lộ secret/stack trace.

Nếu filter đặt trước `ExceptionTranslationFilter`, một `AuthenticationException` phát sinh ngay trong filter không mặc nhiên được filter phía sau bắt. Bởi vậy ví dụ tự bắt lỗi xác thực và gọi `AuthenticationEntryPoint`. Khi dùng `AbstractAuthenticationProcessingFilter`, có thể sử dụng success/failure handler tương ứng, nhưng vẫn phải giữ body cho downstream.

**Lưu ý về `SecurityContext`:** tạo context mới khi xác thực thành công, chỉ chứa principal/authorities từ server. Với filter tự quản lý context, dọn sau request để tránh thông tin của client trước bị rò sang request sau trên thread pool. Nếu có async dispatch, cần một chiến lược propagation/lifecycle thích hợp; ví dụ này dành cho request đồng bộ.

## 8. Request body nào cần ký và canonical hóa ở đâu?

### JSON và text

Đối với JSON, nên định nghĩa rõ hợp đồng ký trên **raw bytes** hay JSON canonical. Ký raw bytes đơn giản hơn về mặt xác định dữ liệu; client phải ký đúng bytes được gửi, không ký object trước khi một thư viện HTTP tự serialize.

Với text, cần thống nhất charset và `Content-Type` nếu có trong danh sách signed headers. Không dùng `request.getReader()` để tính digest vì bước chuyển đổi sang ký tự có thể thay bytes.

### application/x-www-form-urlencoded

`getParameter()` hoặc `getParameterMap()` có thể kích hoạt parse body. Nếu filter ở phía sau đã bị code khác đọc form parameters, `getInputStream()` có thể không còn giữ nguyên bytes. Vì vậy cần quyết định từ đầu: HMAC filter chạy trước form parser hoặc xác thực được thực hiện trên một representation chuẩn được hợp đồng định nghĩa rõ. Kiểm thử order và encoding với các trường lặp.

### multipart/form-data

Multipart có boundary, thứ tự part, Content-Disposition và bytes file. Ký raw body có nghĩa **boundary và các metadata part cũng nằm trong digest**. Không tái dựng multipart bằng thư viện khác trước khi verify, vì các boundary/bytes có thể khác. Buffer toàn bộ file lớn có thể vượt giới hạn; giải pháp streaming/temp-storage cần thiết kế riêng. Không cho multipart resolver tự tiêu thụ body trước khi bộ xác minh có quyền quan sát bytes cần ký.

### Body rỗng và các method ít gửi body

`GET`, `HEAD` thường không có body, nhưng giao thức HTTP và các framework vẫn có các trường hợp đặc biệt. Hợp đồng phải quyết định endpoint nào cho phép entity body, dùng digest của bytes rỗng nếu không có body và từ chối các dạng không được hỗ trợ. Không tự bỏ qua xác thực body chỉ vì method là GET.

### Content-Encoding và proxy

Nếu client gửi body gzip cùng `Content-Encoding: gzip`, cần quy định đang ký **bytes entity nén** hay bytes sau giải nén. Servlet container/reverse proxy có thể xử lý transfer framing, compression hoặc request transformation trước khi filter thấy body.

- Nếu ký bytes sau giải nén, client và server phải có chính xác cùng quy tắc giải nén, giới hạn decompressed size và signed `Content-Encoding` phù hợp.
- Nếu ký bytes entity đã nén, proxy không được thay chúng trước điểm xác minh.
- Không nhầm `Transfer-Encoding: chunked` (framing) với nội dung entity body cần ký. Bytes framing mạng không nhất thiết là bytes mà `ServletInputStream` trả về.
- Kiểm tra `Content-Length` chỉ để hỗ trợ sàng lọc sớm, **không tin hoàn toàn** vào header này để xác định số bytes đã đọc.

Đảm bảo signed method/URI/header/body là dữ liệu mà service sẽ thực sự xử lý. Gateway thay query string, rewrite path hoặc normalize signed headers mà không có hợp đồng thống nhất là nguyên nhân phổ biến của HMAC mismatch.

## 9. Giới hạn bảo mật khi đọc body trước xác thực

Đọc body là thao tác tốn CPU, bộ nhớ và thời gian network xảy ra **trước khi biết client có hợp lệ không**. Đây là bề mặt DoS cần kiểm soát.

| Rủi ro | Biện pháp |
| --- | --- |
| Body rất lớn | Giới hạn ở proxy, container và HMAC filter; đọc tối đa `limit + 1` |
| Client gửi body cực chậm | Read timeout, connection timeout, rate limit và quota trước xác thực |
| Compression bomb | Giới hạn cả kích thước nén lẫn sau giải nén nếu có decompress |
| Nhiều request đồng thời | Concurrency limit, queue/heap budget và backpressure |
| Payload được đọc nhưng chữ ký sai | Không deserialize/ghi dữ liệu trước khi xác thực |
| Body bị cắt khi cache tràn | Từ chối 413; không ký trên phần bị truncate |
| Multipart/file lớn | Dùng giải pháp streaming, storage tạm bảo mật và cleanup |
| Leak trong log/exception | Không log secret, chữ ký, body nhạy cảm hoặc canonical request đầy đủ |
| Header trùng hoặc bất thường | Parser từ chối sớm theo hợp đồng ký |
| JSON parser chạy trước HMAC | Kiểm soát filter order, không xử lý nghiệp vụ khi chưa xác thực |

Có thể kiểm tra cú pháp và độ dài của các header HMAC trước khi buffer body để loại request hiển nhiên không hợp lệ. Tuy nhiên **không thể tin vào key ID hoặc timestamp client khai** như chứng cứ xác thực trước khi chữ ký được kiểm tra.

Khi hết dung lượng bộ nhớ hoặc storage tạm, phải fail closed và trả lỗi phù hợp. Không chuyển sang đường xử lý “bỏ body hash nhưng vẫn xác thực header” vì làm thay đổi hợp đồng ký ở thời điểm rủi ro cao.

### Không xem digest body là dữ liệu công khai vô hại trong mọi trường hợp

SHA-256 digest của body không chứa body dưới dạng rõ, nhưng digest của dữ liệu có entropy thấp hoặc body dự đoán được vẫn có thể hỗ trợ suy đoán giá trị. Hạn chế log digest của payload nhạy cảm; tránh dùng digest của body làm key cache toàn hệ thống nếu chưa đánh giá rò dữ liệu.

## 10. Timestamp, nonce và key rotation khi filter đọc body

Body digest chỉ bảo vệ tính toàn vẹn **nếu nó được bao gồm trong dữ liệu ký HMAC đã xác minh**. Các lớp bảo vệ khác vẫn bắt buộc.

### Chống replay

Server kiểm tra `X-Timestamp` so với đồng hồ server trong cửa sổ chấp nhận. Sau khi HMAC đúng, đăng ký `(credentialId, nonce)` bằng thao tác nguyên tử chỉ nhận lần đầu trong một kho dùng chung giữa các verifier. TTL phải bao phủ toàn bộ khoảng thời gian request cũ còn có thể được chấp nhận.

Không ghi nonce trước khi HMAC đúng, vì kẻ không có secret có thể gửi nonce bất kỳ để gây lỗi cho client hợp lệ. Nếu replay store không khả dụng, từ chối theo chính sách fail closed; không bỏ qua nonce chỉ vì đọc body đã tốn chi phí.

### Rotation và thu hồi

Key ID xác định **một secret cụ thể**. Nếu K3 và K4 cùng ACTIVE trong thời gian rotation, một request khai K4 phải được xác minh bằng đúng K4. Không fallback K3 khi chữ ký K4 sai. Credential REVOKED, RETIRED hoặc hết hạn phải bị từ chối dù body hash và HMAC vẫn đúng với secret cũ.

Cache trạng thái credential cần độ mới phù hợp: một node còn snapshot ACTIVE sau khi nguồn đã REVOKED có thể tiếp tục chấp nhận request. Điều đó không liên quan đến cách buffer body, nhưng là một phần bắt buộc của đường xác thực HMAC đầy đủ.

### Multi-client và multi-tenant

Client ID, key ID, tenant ID do request khai phải được ràng buộc nhất quán với canonical request và quan hệ key → principal → tenant trong registry. Chữ ký hợp lệ chỉ xác thực quyền sở hữu secret; không chứng minh client được phép truy cập tenant khác. `AuthorizationManager` hoặc policy nghiệp vụ phải kiểm tra principal, effective tenant, action và resource.

## 11. Unit test cho replayable request wrapper

Các test dưới đây minh họa cách kiểm tra lớp wrapper **bằng một request thực của Spring Test**, không cần chạy server. Dùng Java 17, JUnit Jupiter và `MockHttpServletRequest` trong dependency `spring-test`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class ReplayableBodyRequestTest {

    @Test
    void readBodyTwiceReturnsSameBytes() throws Exception {
        byte[] expected = """
            {"orderId":"o-100","amount":120000}
            """.getBytes(StandardCharsets.UTF_8);

        MockHttpServletRequest original =
            new MockHttpServletRequest("POST", "/api/hmac/orders");
        original.setContentType("application/json");
        original.setContent(expected);

        ReplayableBodyRequest wrapped =
            ReplayableBodyRequest.capture(original, 1024);

        assertArrayEquals(
            expected, wrapped.getInputStream().readAllBytes());
        assertArrayEquals(
            expected, wrapped.getInputStream().readAllBytes());
    }

    @Test
    void digestMatchesTheExactBufferedBytes() throws Exception {
        byte[] expected = "{\"a\":1,\"b\":2}"
            .getBytes(StandardCharsets.UTF_8);

        MockHttpServletRequest original =
            new MockHttpServletRequest("POST", "/api/hmac/orders");
        original.setContent(expected);

        ReplayableBodyRequest wrapped =
            ReplayableBodyRequest.capture(original, 1024);

        assertEquals(BodyDigest.sha256Hex(expected),
            wrapped.sha256Hex());
    }

    @Test
    void emptyBodyUsesTheDefinedEmptySha256Digest() throws Exception {
        MockHttpServletRequest original =
            new MockHttpServletRequest("POST", "/api/hmac/orders");
        original.setContent(new byte[0]);

        ReplayableBodyRequest wrapped =
            ReplayableBodyRequest.capture(original, 1024);

        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            wrapped.sha256Hex());
    }

    @Test
    void rejectsBodyExceedingLimit() {
        MockHttpServletRequest original =
            new MockHttpServletRequest("POST", "/api/hmac/orders");
        original.setContent(new byte[1025]);

        assertThrows(
            ReplayableBodyRequest.BodyTooLargeException.class,
            () -> ReplayableBodyRequest.capture(original, 1024));
    }

    @Test
    void bodySnapshotCannotMutateStoredBytes() throws Exception {
        byte[] content = {1, 2, 3};
        MockHttpServletRequest original =
            new MockHttpServletRequest("POST", "/api/hmac/orders");
        original.setContent(content);

        ReplayableBodyRequest wrapped =
            ReplayableBodyRequest.capture(original, 1024);

        byte[] copy = wrapped.bodySnapshot();
        copy[0] = 9;

        assertArrayEquals(
            new byte[]{1, 2, 3},
            wrapped.getInputStream().readAllBytes());
    }
}
~~~

Đây là test cho wrapper; chưa phải test xác thực HMAC end-to-end. Các test HMAC đầy đủ phải có signer độc lập, secret test, `AuthenticationManager`, `ReplayStore` và controller thực sự đọc body.

## 12. Integration test: HMAC đúng và controller thấy chính body đã ký

Một bộ integration test `MockMvc` hoặc HTTP thật cần kiểm tra cả hai đầu: filter đọc bytes và controller nhận bytes không đổi. Đừng chỉ assert `200 OK` khi có thể controller đã nhận body rỗng hoặc bị serialize lại.

| Test ID | Input | Kỳ vọng |
| --- | --- | --- |
| BODY-01 | JSON dưới giới hạn, HMAC đúng | Filter xác thực, controller nhận đúng bytes |
| BODY-02 | JSON đúng nhưng thêm 1 dấu cách sau ký | HMAC sai, controller không chạy |
| BODY-03 | JSON đổi thứ tự field sau ký | HMAC sai nếu ký raw bytes |
| BODY-04 | Body rỗng, digest SHA-256 rỗng | Chấp nhận hoặc từ chối theo endpoint policy, dùng digest đúng |
| BODY-05 | Body `{}` thay body rỗng | Digest khác; chữ ký không thể dùng lại |
| BODY-06 | Body đúng bằng giới hạn | Được đọc đầy đủ nếu các điều kiện khác hợp lệ |
| BODY-07 | Body lớn hơn giới hạn 1 byte | 413, không gọi manager/controller |
| BODY-08 | `Content-Length` khai nhỏ hơn bytes thực | Không dựa hoàn toàn vào header để chấp nhận quá giới hạn |
| BODY-09 | Mã hóa UTF-8/BOM/Unicode | HMAC tính trên bytes thống nhất, không tái encode |
| BODY-10 | `CRLF` thay `LF` | HMAC sai nếu bytes ký ban đầu khác |
| BODY-11 | Form URL-encoded đã bị parser đọc trước | Phát hiện lỗi filter order, không xác thực trên body thiếu |
| BODY-12 | Multipart có boundary khác | Ký đúng raw multipart bytes hoặc từ chối theo policy |
| BODY-13 | Gateway rewrite path/query | Server dùng canonical URI đúng hợp đồng |
| BODY-14 | Client giả mạo `X-Original-URI` | Không được điều khiển canonical URI bằng header không tin cậy |
| BODY-15 | Key đã REVOKED, body/HMAC đúng | Từ chối trạng thái credential |
| BODY-16 | HMAC đúng nhưng nonce trùng | Từ chối replay |
| BODY-17 | HMAC đúng nhưng principal thiếu quyền | Authorization từ chối, không thực thi nghiệp vụ |
| BODY-18 | Hai request liên tiếp cùng thread | Không rò `SecurityContext` hoặc body của request trước |
| BODY-19 | Filter bị đăng ký hai lần | Phát hiện chạy lặp, không đánh dấu nonce sai |
| BODY-20 | Backend đọc body qua `getReader()` | Nội dung đúng charset theo hợp đồng, không thay digest đã ký |

Thêm negative test khi kết nối bị cắt giữa chừng, request body chậm, chunked transfer, `Content-Encoding` nén, timeout, và giới hạn tổng bộ nhớ trong tải cao. Với non-blocking Servlet I/O, phải dùng adapter khác và bộ test async tương ứng; wrapper đồng bộ ở trên **không được coi là đã hỗ trợ async**.

### Test vector độc lập

Nên lưu cố định các trường sau cho từng vector:

~~~yaml
id: HMAC-BODY-001
method: POST
canonicalTarget: /api/hmac/orders?currency=VND
contentType: application/json
bodyEncoding: UTF-8
bodyExactText: '{"orderId":"o-100","amount":120000}'
keyId: partner-a-v3
timestamp: '2026-11-28T04:00:00Z'
nonce: 9d73f4de-8b9f-4e7a-99f4-8498ed6e57da
expectedBodyDigest: computed_from_exact_body_bytes
expectedSignature: computed_by_independent_signer
expectedControllerBody: exactly_equal_to_signed_body
~~~

YAML chỉ là mẫu dữ liệu kiểm thử, không phải một test vector hoàn chỉnh có giá trị hash/chữ ký cố định. Người triển khai cần thay hai giá trị `computed_...` bằng hash/HMAC chuẩn đã tính độc lập và assert bytes cụ thể; không lấy kết quả từ chính verifier đang được kiểm thử để làm expected result.

## 13. Lỗi triển khai điển hình và cách nhận biết

### Lỗi A: Cache body sau khi một filter khác đã đọc

HMAC filter đọc request nhưng `getInputStream()` trả rỗng; digest là SHA-256 của body rỗng trong khi client ký JSON thực. Kiểm tra thứ tự filter, parameter parser và logging filter. Không “chữa” bằng cách tắt ký body; sửa điểm thu bytes.

### Lỗi B: Cache body đúng nhưng gọi `chain.doFilter(request, response)`

Wrapper đã được tạo nhưng downstream vẫn nhận request gốc đã hết stream. Cần truyền **wrapped request** vào chain. Unit test wrapper đơn lẻ không bắt được lỗi này; phải có integration test controller.

### Lỗi C: Dùng `ContentCachingRequestWrapper` rồi cho rằng `getInputStream()` đã rewind

Cache giữ bản sao của bytes được đọc nhưng stream gốc đã đến EOF. Cần wrapper thực sự cấp stream mới, hoặc thiết kế điểm tiêu thụ body khác.

### Lỗi D: Tin hoàn toàn vào Content-Length

Server đặt giới hạn 1 MiB nhưng client khai `Content-Length: 128` rồi gửi payload vượt giới hạn qua cách framing không hợp lệ hoặc proxy có lỗi. Không chỉ kiểm tra header; giới hạn **số bytes thực sự đọc**. Proxy và server cũng cần cấu hình từ chối framing HTTP không hợp lệ để giảm nguy cơ request smuggling.

### Lỗi E: Băm object JSON thay vì bytes gốc

Signer và verifier serialize JSON khác thứ tự field hoặc whitespace, HMAC mismatch. Dùng raw bytes, hoặc thiết kế canonical JSON có chuẩn rõ ràng nếu thật sự cần.

### Lỗi F: Log body để debug chữ ký

Để điều tra mismatch, nhóm vận hành log toàn bộ request body và shared secret. Đây là rò rỉ mới. Ghi correlation ID, tên hợp đồng ký, route, mã lỗi, độ dài body (khi phù hợp) và metadata không nhạy cảm; dùng fixture test để đối chiếu canonical bytes.

### Lỗi G: Nonce được ghi trước khi HMAC đúng

Một người không có secret có thể gửi request dùng nonce dự đoán được và khiến client thật bị từ chối. Đăng ký nonce sau chữ ký hợp lệ, thao tác nguyên tử và TTL đúng.

### Lỗi H: Bộ đệm body không có giới hạn trong tải đồng thời

Mỗi request có body vài chục MiB, nhiều kết nối cùng giữ buffer. Hệ thống hết heap và từ chối dịch vụ. Đặt giới hạn theo endpoint, heap budget và concurrent requests; nếu cần file lớn, dùng streaming/storage tạm với cleanup và kiểm tra toàn vẹn ở điểm an toàn.

## 14. Bài tập thực hành

Một dịch vụ dùng custom filter trước `UsernamePasswordAuthenticationFilter` để xác minh `POST /api/hmac/transfers`. Filter có đoạn:

~~~java
byte[] body = request.getInputStream().readAllBytes();
String json = new String(body, StandardCharsets.UTF_8);
String digest = sha256Hex(
    objectMapper.writeValueAsBytes(objectMapper.readTree(json)));

authenticateUsingDigest(digest);
chain.doFilter(request, response);
~~~

Client thực tế ký **raw body bytes**. Khi triển khai, các request đôi lúc nhận 401 do HMAC mismatch; những request HMAC thành công lại khiến controller nhận body rỗng. Một khách hàng khác có thể gửi body 50 MiB và khiến heap tăng đột ngột.

Hãy xác định:

1. Hai nguyên nhân khác nhau gây HMAC mismatch và body rỗng là gì?
2. Tại sao deserialize–serialize JSON không phù hợp khi hợp đồng ký raw bytes?
3. Cần thay `readAllBytes()` bằng cách đọc có giới hạn nào? Khi vượt giới hạn trả mã gì?
4. Sau khi tạo wrapper, phải truyền đối tượng nào vào `chain.doFilter(...)`?
5. Nếu `GET` không có body, digest nào được dùng theo hợp đồng có trường body hash?
6. Nếu gateway đổi `Content-Encoding` hoặc canonical URI, cần test điều gì?
7. Nếu chữ ký đúng nhưng nonce trùng hoặc key đã REVOKED, request có được vào controller không?
8. Sau khi HMAC đúng, client có mặc nhiên được phép truy cập tài khoản của tenant khác không?

**Hướng giải:** đọc đúng raw bytes có giới hạn; tính digest trước khi xử lý JSON; dùng replayable wrapper và chuyển wrapper xuống downstream; dùng SHA-256 của mảng rỗng cho body rỗng nếu hợp đồng quy định; từ chối 413 khi vượt giới hạn; thống nhất bytes/URI trước và sau proxy; tiếp tục kiểm tra trạng thái credential, timestamp/nonce và phân quyền tenant/resource. Không được bỏ chữ ký body hoặc bypass replay chỉ để giải quyết lỗi vận hành.

## 15. Checklist áp dụng cho production

Trước khi đưa custom authentication filter HMAC vào sử dụng, xác nhận:

- Hợp đồng canonical request quy định rõ method, URI, signed headers, body bytes/digest, key ID, timestamp và nonce.
- Body được đọc tại một điểm đáng tin, **trước khi bị parse/tiêu thụ bởi filter khác** hoặc có cơ chế chia sẻ bytes chính xác.
- Giới hạn kích thước được kiểm tra trên **bytes thực tế**, không chỉ `Content-Length`; có timeout, concurrency limit và chính sách tải lớn.
- Digest dùng body bytes thực tế, không JSON object được serialize lại; body rỗng được xử lý theo hợp đồng.
- Controller nhận đúng body đã được ký; wrapper chuyển tới downstream, hỗ trợ reader/input stream ở mức cần thiết.
- Cơ chế sync/async được phân định rõ; không dùng wrapper đồng bộ cho Servlet non-blocking mà chưa bổ sung xử lý.
- Multipart, form parsing, encoding, compression và gateway rewrite được kiểm thử nếu endpoint hỗ trợ.
- HMAC xác minh đúng key ID và trạng thái credential; key rotation không tạo fallback sang key khác.
- Timestamp và nonce chống replay, nonce store dùng chung và ghi nguyên tử sau HMAC hợp lệ.
- AuthenticationManager tạo principal tin cậy; SecurityContext được dọn; authorization kiểm tra quyền tenant/resource.
- Test gồm unit wrapper, canonical vector độc lập, integration `@RequestBody`, proxy end-to-end và trường hợp body quá lớn.
- Log và metric không làm lộ shared secret, HMAC signature, canonical request hoặc payload nhạy cảm.

**Đọc request body trong custom authentication filter là một phần của ranh giới toàn vẹn dữ liệu.** Filter phải tính HMAC trên đúng bytes theo hợp đồng, giữ nguyên dữ liệu để nghiệp vụ xử lý, giới hạn tài nguyên trước xác thực và không bỏ qua trạng thái credential, chống replay hoặc phân quyền. Khi body digest, canonical request và downstream cùng dùng một nguồn bytes đáng tin, việc xác thực HMAC qua Spring Security và proxy/gateway trở nên có thể kiểm chứng được.
