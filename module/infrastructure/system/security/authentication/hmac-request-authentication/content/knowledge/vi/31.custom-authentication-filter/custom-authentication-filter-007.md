# Từ chối request trong custom authentication filter

## 1. Bối cảnh và mục tiêu

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, hệ thống xác thực HTTP request bằng HMAC với shared secret và một **canonical request** được hai phía thống nhất (phương thức HTTP, URI, các header được ký và/hoặc hash của body). Ngoài kiểm tra chữ ký, hệ thống còn phải kiểm soát timestamp, nonce, vòng đời khóa và sự thay đổi request khi đi qua proxy/gateway.

Ở chương **Custom authentication filter**, câu hỏi của bài này là: **khi request không đạt yêu cầu xác thực, filter phải từ chối thế nào để request không tới nghiệp vụ, trả đúng HTTP status và không làm lộ thông tin bảo mật?**

Giả sử đối tác gọi `POST /api/signed/payments` kèm các header theo hợp đồng:

~~~http
POST /api/signed/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: 9b90c54a-2c2a-42ab-bdd6-d6bead9e5fb8
X-Signature: <gia-tri-chu-ky-base64>

{"amount":125000,"currency":"VND"}
~~~

Ví dụ chỉ minh họa các trường dữ liệu. Cách sắp xếp canonical request, định dạng timestamp, thuật toán, encoding chữ ký, giới hạn độ lệch đồng hồ và các trường thực sự được ký **phải do hợp đồng HMAC quy định**; server không được tùy ý suy ra từ tên header.

Khi signature sai hoặc nonce đã dùng, endpoint tạo thanh toán không được chạy. Filter phải kết thúc xử lý bằng một response từ chối nhất quán. Ngược lại, request được ký đúng nhưng principal không có quyền tạo thanh toán sẽ bị từ chối ở bước **phân quyền**, sau khi đã xác thực.

## 2. Ai chịu trách nhiệm từ chối?

Một custom authentication filter có ba đường xử lý chính:

1. **Bỏ qua** nếu request không thuộc tập endpoint do filter phụ trách. Việc bỏ qua phải dựa trên cấu hình route rõ ràng; không tự suy đoán rằng thiếu HMAC nghĩa là có thể bỏ qua.
2. **Chấp nhận xác thực** sau khi xác minh thành công key, timestamp, canonical request, signature và điều kiện chống replay; đặt `Authentication` đáng tin cậy vào `SecurityContext` rồi chuyển tiếp filter chain.
3. **Từ chối** nếu request thuộc phạm vi HMAC nhưng không có chứng thực hợp lệ; xóa authentication context liên quan, ghi response lỗi và **`return` ngay**, không gọi tiếp `chain.doFilter(...)`.

~~~mermaid
flowchart TD
    A[HTTP request] --> B{Thuộc API yêu cầu HMAC?}
    B -- Không --> C[Đường xử lý khác theo cấu hình]
    B -- Có --> D[Kiểm tra credential và canonical request]
    D -- Thiếu / sai / hết hạn / replay --> E[AuthenticationEntryPoint: 401]
    D -- Hạ tầng xác thực không sẵn sàng --> F[Fail closed: 503]
    D -- Hợp lệ --> G[Tạo Authentication và SecurityContext]
    G --> H{Đủ authority?}
    H -- Không --> I[AccessDeniedHandler: 403]
    H -- Có --> J[Controller / nghiệp vụ]
    E --> K[Không thực thi nghiệp vụ]
    F --> K
    I --> K
~~~

**Fail closed** nghĩa là khi không thể xác minh chữ ký hoặc tính duy nhất của nonce, hệ thống không cho request đi qua chỉ vì cơ chế xác thực đang lỗi. Điều này không đồng nghĩa mọi lỗi hạ tầng đều là “sai mật khẩu”: cần phân loại nguyên nhân để trả mã phù hợp.

## 3. Chọn HTTP status đúng với nguyên nhân

| Tình huống | Nơi quyết định | Phản hồi đề xuất | Lý do |
|---|---|---|---|
| Thiếu `X-Key-Id`, timestamp, nonce hoặc signature trên endpoint bắt buộc ký | HMAC filter | **401 Unauthorized** | Chưa có chứng thực hợp lệ |
| Key ID không tồn tại, key đã bị thu hồi, chữ ký không khớp, timestamp ngoài cửa sổ, nonce bị dùng lại | HMAC verifier/filter | **401 Unauthorized** | Không xác thực được request |
| Header HMAC có cú pháp sai | HMAC filter | **401** theo chính sách ví dụ; **400** cũng có thể dùng nếu hợp đồng phân loại lỗi cú pháp riêng | Chọn một quy tắc nhất quán, tránh lộ quá nhiều chi tiết |
| Chữ ký đúng, principal đã xác thực nhưng thiếu quyền `payments:write` | Authorization layer | **403 Forbidden** | Xác thực thành công nhưng không được phép |
| Không truy cập được kho nonce/key cần cho xác minh | Verifier/filter | **503 Service Unavailable** (hoặc lỗi server phù hợp) | Không thể xác minh an toàn; tuyệt đối không cho qua |
| Kích thước body vượt giới hạn cấu hình | HTTP/container/gateway hoặc tầng kiểm tra giới hạn | **413 Content Too Large** | Từ chối kích thước trước khi xử lý tốn tài nguyên |
| Bị giới hạn tần suất theo chính sách độc lập | Gateway/rate limiter | **429 Too Many Requests** | Phản ánh giới hạn tần suất, không tự coi là chữ ký sai |

Trong HTTP, **401** chỉ ra request chưa có thông tin xác thực hợp lệ; **403** chỉ ra server từ chối thực hiện dù đã hiểu request, điển hình là principal đã được xác thực nhưng thiếu authority. Tên “Unauthorized” của 401 dễ gây nhầm với “không có quyền”: trong thiết kế Spring Security, lỗi *authentication* và *authorization* cần được xử lý ở hai vị trí khác nhau.

Với phản hồi 401, HTTP yêu cầu server gửi header `WWW-Authenticate` chứa challenge áp dụng cho tài nguyên. Nếu API sử dụng scheme HMAC tự định nghĩa, có thể thỏa thuận challenge như `WWW-Authenticate: HMAC realm="signed-api"`; đây là **hợp đồng riêng** của API, không mặc nhiên biến `X-Signature` thành một scheme chuẩn chung. Client vẫn cần tài liệu cụ thể về cách ký và truyền các header.

### Thông tin trả về client

Thường chỉ cần lỗi ổn định, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="signed-api"

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

Không trả về shared secret, canonical string thực tế, chữ ký kỳ vọng, trạng thái tồn tại của key ID hoặc lý do chi tiết “nonce này đã xuất hiện lúc ...”. Các nguyên nhân cụ thể có thể lưu trong log nội bộ đã kiểm soát quyền truy cập, với mã lỗi an toàn, và liên kết bằng request/correlation ID.

## 4. Phối hợp với Spring Security

Spring Security có hai cơ chế quan trọng:

- **`AuthenticationEntryPoint`**: khởi tạo phản hồi khi chưa xác thực hợp lệ, thường là 401.
- **`AccessDeniedHandler`**: phản hồi khi một principal đã xác thực nhưng bị từ chối quyền, thường là 403.

`ExceptionTranslationFilter` bắt `AuthenticationException` và `AccessDeniedException` được ném ra từ **những filter chạy phía sau nó**. Một HMAC filter tự thêm bằng `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` thường chạy **trước `ExceptionTranslationFilter`**, nên exception ném ngay trong HMAC filter không được filter phía sau đó tự động bắt. Vì vậy, khi dùng `OncePerRequestFilter` theo cách này, hãy xử lý lỗi xác thực ngay tại HMAC filter bằng cách gọi `AuthenticationEntryPoint`, hoặc chủ động chọn một cấu trúc authentication filter/handler phù hợp khác.

`@ControllerAdvice` xử lý exception thuộc luồng MVC và không phải nơi đáng tin cậy để bắt lỗi phát sinh từ servlet security filter trước controller.

Một cấu hình phù hợp cần bảo đảm:

- Filter chỉ áp dụng cho các route bắt buộc HMAC, kể cả trường hợp **thiếu hoàn toàn** credential.
- Chỉ một nơi chịu trách nhiệm ghi response từ chối cho một request.
- Lỗi xác thực bị chặn trước nghiệp vụ; lỗi phân quyền do authorization layer giải quyết.
- Không đăng ký vô tình cùng một filter hai lần, chẳng hạn vừa là servlet `Filter` tự động đăng ký bởi Spring Boot vừa thêm vào `SecurityFilterChain`.

## 5. Ví dụ triển khai filter từ chối request

Ví dụ dùng Java 17+, Spring Security 6 và Jakarta Servlet. `HmacRequestVerifier` là hợp đồng của thành phần xác minh HMAC; bài này tập trung vào **cách từ chối**, vì việc xây canonical request, hash body, truy xuất key và lưu nonce nguyên tử cần triển khai riêng theo hợp đồng của hệ thống.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public interface HmacRequestVerifier {
    // Thành công: trả Authentication đã xác thực, với authorities
    // lấy từ cấu hình server gắn với client/key, không tin giá trị tự khai báo.
    // Credential không hợp lệ: ném BadCredentialsException.
    // Kho key/nonce không sẵn sàng: ném AuthenticationServiceException.
    Authentication authenticate(HttpServletRequest request)
            throws AuthenticationException;
}
~~~

Một response writer nhỏ giúp entry point, denied handler và lỗi hạ tầng dùng chung định dạng lỗi:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class HmacProblemResponses {
    private HmacProblemResponses() {}

    public static void write(HttpServletResponse response, int status)
            throws IOException {
        if (response.isCommitted()) {
            return; // Đã gửi headers/body thì không thể thay HTTP status.
        }

        final String body = switch (status) {
            case 401 -> "{\"type\":\"about:blank\",\"title\":\"Unauthorized\",\"status\":401}";
            case 403 -> "{\"type\":\"about:blank\",\"title\":\"Forbidden\",\"status\":403}";
            case 503 -> "{\"type\":\"about:blank\",\"title\":\"Service Unavailable\",\"status\":503}";
            default -> throw new IllegalArgumentException("Unsupported status");
        };

        response.resetBuffer();
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");
        if (status == 401) {
            // Scheme HMAC phải được API định nghĩa trong hợp đồng HTTP.
            response.setHeader("WWW-Authenticate", "HMAC realm=\"signed-api\"");
        }
        response.getWriter().write(body);
    }
}
~~~

Filter dưới đây chỉ bắt exception trong **giai đoạn verify**. Đặt `chain.doFilter` ngoài khối `catch` là chủ ý: nếu một filter phân quyền phía sau phát sinh lỗi, cơ chế exception handling của Spring Security vẫn xử lý lỗi ấy đúng ngữ nghĩa.

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

public final class HmacAuthenticationFilter extends OncePerRequestFilter {
    private final HmacRequestVerifier verifier;
    private final AuthenticationEntryPoint entryPoint;

    public HmacAuthenticationFilter(
            HmacRequestVerifier verifier,
            AuthenticationEntryPoint entryPoint) {
        this.verifier = verifier;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        final Authentication authentication;
        try {
            authentication = verifier.authenticate(request);
            if (authentication == null || !authentication.isAuthenticated()) {
                throw new BadCredentialsException("Invalid HMAC authentication");
            }
        } catch (AuthenticationServiceException unavailable) {
            // Ví dụ: kho nonce đang lỗi; không thể kiểm tra replay.
            SecurityContextHolder.clearContext();
            HmacProblemResponses.write(
                    response, HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            return;
        } catch (AuthenticationException rejected) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, rejected);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Các điểm cần đọc kỹ:

1. **Không gọi `chain.doFilter` sau khi từ chối.** Hai nhánh `catch` đều có `return`; controller không được thực thi đối với request đó.
2. **Không phân loại mọi exception thành 401.** Lỗi hạ tầng được nhận diện riêng (`AuthenticationServiceException` là quy ước của ví dụ), đóng đường truy cập và trả 503. Ngoại lệ lập trình hay lỗi hệ thống khác phải được xử lý như lỗi server, có quan sát và cảnh báo phù hợp.
3. **Không dùng dữ liệu client để tự nâng quyền.** `Authentication` thành công phải chứa principal/authority đã đối chiếu với dữ liệu đáng tin cậy phía server.
4. **Không nuốt exception từ các filter phía sau.** Chỉ lỗi của bộ xác minh HMAC mới được chuyển thành lỗi authentication tại đây.
5. **Quản lý `SecurityContext` theo request.** Ví dụ dùng session stateless, tạo context mới và dọn sau khi filter chain hoàn tất để tránh rò authentication sang request dùng lại thread.

### Đấu nối vào SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SignedApiSecurityConfig {
    @Bean
    SecurityFilterChain signedApiChain(
            HttpSecurity http,
            HmacRequestVerifier verifier) throws Exception {

        AuthenticationEntryPoint entryPoint =
                (req, res, ex) -> HmacProblemResponses.write(res, 401);
        AccessDeniedHandler deniedHandler =
                (req, res, ex) -> HmacProblemResponses.write(res, 403);

        return http
                .securityMatcher("/api/signed/**")
                .sessionManagement(sm -> sm
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Ví dụ dành riêng cho API máy-máy không dùng cookie session.
                .csrf(csrf -> csrf.disable())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.POST, "/api/signed/payments")
                        .hasAuthority("payments:write")
                        .anyRequest().authenticated())
                .addFilterBefore(
                        new HmacAuthenticationFilter(verifier, entryPoint),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

Ở ví dụ này, `securityMatcher` giới hạn toàn bộ chain cho `/api/signed/**`, nên filter trong chain chỉ xử lý tập endpoint đó. Nếu ứng dụng có nhiều `SecurityFilterChain`, phải cấu hình thứ tự và chain phụ trách các route còn lại một cách tường minh. Không tự động tắt CSRF cho các endpoint dùng cookie trình duyệt; việc tắt ở đây chỉ phù hợp với giả định **API stateless, máy gọi máy, không dựa vào cookie để xác thực**.

Trong sản phẩm thực tế, nên cấu hình chung `AuthenticationEntryPoint`, `AccessDeniedHandler`, cách tạo correlation ID và format lỗi cho các đường xác thực liên quan để client nhận phản hồi nhất quán.

## 6. Từ chối ở từng bước xác minh HMAC

HMAC không chỉ là so sánh hai chuỗi signature. Verifier nên đưa ra kết quả chặt chẽ theo thứ tự có chủ đích:

1. **Kiểm tra input và giới hạn tài nguyên.** Chỉ chấp nhận những header, encoding, độ dài và thuật toán đã định nghĩa; giới hạn body trước khi buffer/hash; loại bỏ các biểu diễn mơ hồ của header hoặc đường dẫn. Việc chuẩn hóa query, path, header và body phải giống hệt hợp đồng ký.
2. **Xác định key có thể sử dụng.** Tìm key theo key ID trong phạm vi client/tenant đã xác định; kiểm tra trạng thái hiệu lực, rotation và chính sách thời hạn. Một key ID do client gửi không tự chứng minh danh tính của client.
3. **Kiểm tra timestamp.** Parse đúng format rồi kiểm tra cửa sổ thời gian so với clock server, ví dụ ±5 phút **nếu hợp đồng chọn giá trị đó**; sai, thiếu hoặc quá cũ đều không xác thực.
4. **Tính lại HMAC.** Tạo đúng canonical request từ biểu diễn mà server đã quy định, dùng secret gắn với key; so sánh chữ ký dạng byte bằng phép so sánh **constant-time** thay cho so sánh chuỗi thông thường. Trong Java có thể dùng `MessageDigest.isEqual(expected, provided)` sau khi decode hợp lệ.
5. **Chống replay.** Sau khi signature hợp lệ, thực hiện thao tác **atomic insert-if-absent** cho nonce theo client/key và thời hạn đủ bao phủ cửa sổ timestamp; nonce đã tồn tại thì từ chối. Thao tác kiểm tra rồi ghi tách rời sẽ tạo race condition khi hai request đến đồng thời.
6. **Tạo principal đáng tin cậy.** Chỉ sau khi tất cả kiểm tra đạt, ánh xạ key/client sang authority từ cấu hình server. Quyền truy cập còn phải được xét riêng.

Đối với lỗi credential, nên trả phản hồi 401 chung thay vì phân biệt công khai “unknown key”, “bad MAC”, “expired key” hay “reused nonce”; server vẫn cần phân biệt các nhóm này trong số liệu quan sát nội bộ.

Một số tình huống dễ bỏ sót:

- **Proxy/gateway viết lại path hoặc header:** nếu client ký `/api/v1/payments` nhưng backend kiểm tra `/payments`, chữ ký sẽ sai. Phải xác định nguồn path/host đáng tin cậy, chuẩn hóa thống nhất ở ranh giới gateway và kiểm thử xuyên tầng. Không tin các header `X-Forwarded-*` tùy ý từ Internet.
- **Body bị đọc trước:** nếu filter tiêu thụ input stream mà không cung cấp lại body cho controller, request hợp lệ vẫn lỗi nghiệp vụ. Nếu cần đọc body, dùng wrapper thực sự hỗ trợ replay input stream, áp dụng hạn mức dung lượng; `ContentCachingRequestWrapper` đơn thuần không tự bảo đảm controller có thể đọc lại stream đã tiêu thụ.
- **Key rotation:** nhận các key đang còn trong giai đoạn chuyển tiếp theo key ID và hiệu lực đã cấu hình; key bị thu hồi phải bị từ chối, không “fallback” sang secret bất kỳ để thử cho đến khi khớp.
- **Kho nonce mất kết nối:** tuyệt đối không bỏ qua bước chống replay để request tiếp tục. Trả 503 và giám sát sự cố; cân nhắc `Retry-After` khi có căn cứ rõ ràng về thời gian phục hồi.
- **Chữ ký đúng nhưng thiếu quyền:** trả 403 tại authorization layer. Một chữ ký chứng minh quyền sở hữu secret theo hợp đồng, không tự cấp quyền gọi mọi API.
- **Retry hợp lệ sau lỗi mạng:** việc dùng lại cùng nonce có thể bị xem là replay. Client cần cơ chế sinh nonce mới và, riêng với các thao tác ghi, idempotency key/ngữ nghĩa retry được thiết kế độc lập với nonce HMAC.

## 7. Kiểm thử hành vi từ chối

Các test quan trọng phải kiểm tra đồng thời **HTTP response** và việc **nghiệp vụ không bị gọi**. Chỉ assert mã 401 là chưa đủ nếu filter đã lỡ gọi tiếp controller.

| Test case | Kết quả mong đợi |
|---|---|
| Thiếu toàn bộ header HMAC trên route yêu cầu chữ ký | 401, challenge theo hợp đồng, không gọi controller |
| Sai signature hoặc đổi một byte trong phần đã ký của body | 401; không có hiệu ứng nghiệp vụ |
| Timestamp quá cũ hoặc vượt độ lệch cho phép | 401; không có hiệu ứng nghiệp vụ |
| Gửi lại cùng nonce sau request hợp lệ | Lần đầu thành công nếu đủ quyền; lần sau 401 |
| Hai request đồng thời dùng cùng nonce đã ký hợp lệ | Tối đa một request vượt qua kiểm tra atomic nonce |
| Key đang rotation và key đã bị thu hồi | Key trong thời gian cho phép hoạt động; key bị thu hồi nhận 401 |
| HMAC hợp lệ nhưng thiếu `payments:write` | 403 từ `AccessDeniedHandler` |
| Hạ tầng nonce không sẵn sàng | 503; nghiệp vụ không chạy, không bỏ qua replay |
| Gateway thay đổi path/header được ký | Kết quả tuân thủ canonical contract đã thống nhất; không có “chế độ bỏ qua chữ ký” |
| Body lớn hơn giới hạn | 413 hoặc phản hồi giới hạn đã thỏa thuận, không buffer không giới hạn |
| Endpoint công khai nằm ngoài chain ký | Không bị filter HMAC chặn; tiếp tục theo security chain áp dụng |

Ví dụ kiểm thử bằng MockMvc (giả định đã cấu hình Spring Security test và mock `verifier`/`paymentService`):

~~~java
given(verifier.authenticate(any()))
        .willThrow(new BadCredentialsException("Invalid signature"));

mockMvc.perform(post("/api/signed/payments")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"amount\":125000}"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(header().string(
                "WWW-Authenticate", "HMAC realm=\"signed-api\""));

verifyNoInteractions(paymentService);
~~~

Với test tích hợp thực, không chỉ mock verifier: hãy dùng cùng bộ test vector chữ ký ở client và server, cố định clock trong test, kiểm tra so sánh signature, lưu nonce đồng thời, cập nhật key và request đi qua cấu hình proxy/gateway gần production nhất.

## 8. Logging, vận hành và các lỗi triển khai thường gặp

**Logging và đo lường:** có thể ghi request ID, route dạng template, key/client ID đã làm mờ hoặc băm an toàn, nhóm lý do từ chối, timestamp nhận, elapsed time và mã response. Không log shared secret, header signature nguyên văn, canonical request chứa dữ liệu nhạy cảm, body thanh toán hoặc nonce nguyên văn khi không có nhu cầu và chính sách bảo vệ phù hợp. Theo dõi tỷ lệ 401/403, replay, clock skew, lỗi kho nonce và độ trễ xác minh để phân biệt tấn công với lỗi tích hợp.

**Không gửi lỗi hai lần:** sau khi gọi `AuthenticationEntryPoint.commence(...)` hoặc ghi response 503, phải `return`. Nếu response đã commit, không cố đặt status/header lần nữa. Kiểm soát error dispatch của servlet để không vô tình ghi đè response lỗi hoặc lặp lại quy trình xác thực.

**Không trả 403 cho signature sai:** khi chưa xác minh được danh tính, đó là lỗi authentication. Ngược lại, không gắn mọi `AccessDeniedException` với “chữ ký sai” nếu principal đã hợp lệ.

**Không bỏ qua route vì thiếu signature:** đường dẫn được bảo vệ là quyết định phía server. Nếu muốn một số endpoint không cần HMAC (ví dụ health check), hãy khai báo matcher/chain riêng; không dùng logic “nếu không có header thì cho qua”.

**Không chuyển nguyên lỗi verifier ra HTTP:** nội dung exception hoặc stack trace có thể chứa key ID, canonical string hoặc đường dẫn nội bộ. Sử dụng response chung cho client; tách thông tin chẩn đoán vào kênh log được kiểm soát.

**Không coi chữ ký là phân quyền:** filter xác thực request, rồi authority/ownership/tenant policies quyết định request có được thực hiện nghiệp vụ hay không. Đối với đa tenant, principal được xác thực phải được ràng buộc với tenant/resource; không lấy tenant từ request rồi mặc nhiên tin là được quyền.

## 9. Checklist áp dụng

- [ ] Tập endpoint bắt buộc HMAC được xác định rõ trong `SecurityFilterChain`.
- [ ] Header thiếu/sai, key không hợp lệ, timestamp hết hạn, signature sai và replay đều dừng chain với response 401 nhất quán.
- [ ] Response 401 có `WWW-Authenticate` theo hợp đồng, không tiết lộ secret hoặc khác biệt nội bộ không cần thiết.
- [ ] Lỗi backend khóa/nonce không cho qua xác thực; được ghi nhận và trả lỗi server phù hợp.
- [ ] Request hợp lệ tạo `Authentication` từ dữ liệu server; lỗi thiếu authority được xử lý thành 403.
- [ ] Xác minh canonical request tương thích client/gateway; đọc body an toàn và có giới hạn dung lượng.
- [ ] Nonce được kiểm tra và lưu nguyên tử, key rotation và revoke được kiểm thử.
- [ ] Test chứng minh mọi nhánh bị từ chối đều không chạy thao tác nghiệp vụ; test có cả retry, đồng thời và proxy.
- [ ] Log/metric đủ chẩn đoán nhưng loại bỏ credential và dữ liệu nhạy cảm.

**Điểm cần nhớ:** một custom authentication filter được thiết kế đúng phải tạo ra **ranh giới dừng chắc chắn** cho request không xác thực được. Với HMAC, ranh giới ấy bao gồm canonical signature, timestamp, nonce, key lifecycle và các sự cố xác minh; sau khi qua ranh giới xác thực, hệ thống vẫn phải kiểm tra phân quyền độc lập.
