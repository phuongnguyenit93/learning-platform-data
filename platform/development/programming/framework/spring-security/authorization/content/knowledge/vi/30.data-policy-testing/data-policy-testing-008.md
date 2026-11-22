# Kiểm thử dịch vụ chính sách khi timeout, lỗi hoặc trả dữ liệu không hợp lệ

## 1. Bài toán và mục tiêu

Trong Spring Security, ứng dụng có thể chuyển một quyết định phân quyền sang **dịch vụ chính sách** bên ngoài (Policy Decision Point, PDP). Ứng dụng đóng vai trò **Policy Enforcement Point (PEP)**: nhận yêu cầu, xây dựng ngữ cảnh đáng tin cậy, gọi PDP rồi thực thi hoặc từ chối truy cập. Một yêu cầu ví dụ là: người dùng alice có được READ tài nguyên /reports/42 hay không?

Đường đi điển hình:

~~~text
HTTP request
  -> SecurityFilterChain
  -> AuthorizationManager (PEP)
  -> PolicyGateway / HTTP client
  -> Policy service (PDP)
  <- phản hồi chính sách
  -> quyết định cho phép hoặc từ chối
  -> controller chỉ chạy khi được cho phép
~~~

Bài này tập trung kiểm thử **khi PDP không trả được một quyết định đáng tin cậy**: quá thời gian, lỗi mạng/HTTP, phản hồi sai định dạng hoặc sai hợp đồng. Mục tiêu không phải kiểm thử thuật toán viết chính sách ở PDP, mà là kiểm chứng ranh giới tin cậy và hành vi thực thi ở ứng dụng gọi PDP.

Sau bài học, cần chứng minh được các bất biến:

1. **Chỉ phản hồi ALLOW hợp lệ, tương ứng đúng yêu cầu hiện tại, mới cấp quyền.** DENY, thiếu dữ liệu, lỗi và timeout đều không cấp quyền (fail closed).
2. **DENY khác với không xác định được quyết định.** Cả hai đều không cho vào, nhưng phải phân loại khác nhau cho log, metric, điều tra và vận hành.
3. **Ngân sách thời gian hữu hạn.** Không để request treo vô hạn, retry kéo dài hoặc một phản hồi đến trễ tự biến thành quyền truy cập cho request đã kết thúc.
4. **Không đi vào nghiệp vụ khi kiểm tra quyền thất bại.** Test phải xác nhận controller/service ghi dữ liệu không thực thi, không chỉ kiểm tra HTTP status.
5. **Phân biệt lỗi từ PDP với lỗi lập trình của PEP.** Bắt đúng loại lỗi dự kiến; không âm thầm biến mọi exception thành một kết quả khó quan sát.

## 2. Hợp đồng để kiểm thử được

Giả sử giao thức giữa ứng dụng và PDP được thống nhất như sau (đây là **hợp đồng ví dụ**, không phải định dạng bắt buộc của Spring Security):

| Thành phần | Trường / tín hiệu | Điều cần bảo đảm |
| --- | --- | --- |
| Yêu cầu | subject, action, resource | Lấy từ Authentication và tài nguyên đã chuẩn hóa phía server; không tin user tự khai quyền |
| Yêu cầu | requestId | Mã tương quan riêng cho từng lần đánh giá |
| Phản hồi | effect = ALLOW hoặc DENY | Tập giá trị được cho phép rõ ràng; giá trị lạ không tự động được hiểu là ALLOW |
| Phản hồi | requestId | Phải khớp yêu cầu hiện tại; phản hồi của yêu cầu khác là không hợp lệ |
| Phản hồi | policyVersion | Trong hợp đồng ví dụ này là bắt buộc; nếu hệ thống thật không có trường đó thì sửa hợp đồng và test tương ứng |
| Hạ tầng | connect timeout, read/response timeout, deadline tổng | Phải thực sự được client HTTP thực thi; việc chỉ truyền Duration vào method chưa đủ |
| Lỗi | timeout, connection reset, DNS, HTTP 429/5xx, JSON parse error | Chuẩn hóa thành các loại lỗi có thể kiểm thử, không trả về ALLOW |

Có thể mô hình hóa kết quả nội bộ bằng bốn loại:

- **ALLOW**: phản hồi hợp lệ, khớp request, effect chính xác là ALLOW.
- **DENY**: phản hồi hợp lệ, khớp request, effect chính xác là DENY.
- **INVALID**: dữ liệu đầu vào/đầu ra vi phạm hợp đồng: null, thiếu trường, giá trị lạ, JSON sai, requestId không khớp.
- **UNAVAILABLE**: không nhận được phản hồi quyết định do timeout, sự cố kết nối, HTTP lỗi hoặc circuit breaker đang mở.

Chỉ ALLOW ánh xạ sang **granted = true**; ba kết quả còn lại ánh xạ sang **false**. Việc chuẩn hóa HTTP 401/403/429/5xx của PDP thành loại nào cần được xác định trong adapter cụ thể, nhưng **không được biến bất kỳ lỗi đó thành ALLOW**. Trong các hệ thống yêu cầu độ tin cậy hoặc khả dụng đặc biệt, lựa chọn trả HTTP 503 cho request bị từ chối vì PDP không sẵn sàng có thể là một quyết định thiết kế hợp lệ; quy tắc an toàn vẫn là không chạy nghiệp vụ được bảo vệ.

## 3. Ma trận ca kiểm thử bắt buộc

| Ca | Cách mô phỏng | Kết quả gateway | Bất biến cần assert |
| --- | --- | --- | --- |
| ALLOW hợp lệ | PDP trả ALLOW với requestId và trường bắt buộc đúng | ALLOW | Cho phép đúng request được cấp quyền |
| DENY hợp lệ | PDP trả DENY hợp lệ | DENY | Không chạy nghiệp vụ |
| Connect timeout | Không thiết lập được kết nối trong thời hạn | UNAVAILABLE | Từ chối; kết thúc trong deadline |
| Read/response timeout | Kết nối có nhưng PDP không hoàn tất phản hồi | UNAVAILABLE | Từ chối, không treo vô hạn |
| HTTP 500/503 | Stub PDP trả lỗi máy chủ | UNAVAILABLE | Không fallback sang ALLOW |
| DNS/reset/connection refused | Client báo IOException tương ứng | UNAVAILABLE | Không cấp quyền |
| HTTP 429 | PDP giới hạn tốc độ | UNAVAILABLE hoặc loại lỗi vận hành định nghĩa trước | Không bypass; retry trong ngân sách |
| PDP trả JSON sai cú pháp | Decoder phát hiện lỗi parse | INVALID | Không dùng dữ liệu một phần |
| Thiếu/null effect | JSON hợp lệ về cú pháp nhưng thiếu nghĩa | INVALID | Không suy diễn giá trị mặc định |
| Effect lạ (ví dụ PERMIT) | Không thuộc tập enum/hợp đồng | INVALID | Không dùng điều kiện “khác DENY là cho phép” |
| requestId không khớp | Dữ liệu từ request khác | INVALID | Không nhận nhầm quyết định |
| Thiếu trường bắt buộc | policyVersion rỗng theo hợp đồng ví dụ | INVALID | Không cấp quyền |
| Phản hồi null / body rỗng | 204 hoặc body rỗng không hợp lệ | INVALID | Không NPE hoặc vô tình ALLOW |
| Response đến sau deadline | Delay rồi trả ALLOW | UNAVAILABLE của request đã timeout | ALLOW đến trễ không thay đổi quyết định cũ |
| Circuit breaker OPEN | Client không gửi request ra PDP | UNAVAILABLE | Không gọi controller; có metric |
| Đầu vào không hợp lệ | Principal/resource/action/requestId thiếu | INVALID | Không gửi request sai tới PDP |
| Đồng thời nhiều request | Một ALLOW và một timeout, requestId khác nhau | Tách kết quả từng request | Không rò quyết định giữa các request |

Với chính sách có obligation (ví dụ buộc lọc cột/tenant), chữ ký, thời hạn hiệu lực hoặc phiên bản tối thiểu, hãy bổ sung các ca thiếu/sai các trường đó. **ALLOW nhưng thiếu điều kiện thực thi bắt buộc cũng phải bị từ chối.**

## 4. Ví dụ Java 17+ chạy độc lập: lớp gateway và test giả lập

Ví dụ dưới đây dùng một client giả để tạo các kết quả một cách **xác định**, không ngủ chờ và không gọi mạng thật. Client giả ném TimeoutException, IOException hoặc BadPayloadException tương tự như adapter thực đã chuẩn hóa từ HTTP client. Phần kiểm thử timeout trên socket thật nằm ở mục 6.

Lưu nội dung sau trong file **PolicyFailureDemo.java**:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;

public class PolicyFailureDemo {
    private static final Duration BUDGET = Duration.ofMillis(250);
    private static final Request REQUEST =
            new Request("alice", "READ", "/reports/42", "req-42");

    record Request(String subject, String action, String resource, String requestId) {}
    record Reply(String requestId, String effect, String policyVersion) {}

    enum Outcome { ALLOW, DENY, INVALID, UNAVAILABLE }

    static final class BadPayloadException extends Exception {
        BadPayloadException(String message) { super(message); }
    }

    @FunctionalInterface
    interface PolicyClient {
        Reply evaluate(Request request, Duration deadline)
                throws IOException, TimeoutException, BadPayloadException;
    }

    static final class PolicyGateway {
        private final PolicyClient client;

        PolicyGateway(PolicyClient client) { this.client = client; }

        Outcome authorize(Request request) {
            if (request == null || !present(request.subject())
                    || !present(request.action()) || !present(request.resource())
                    || !present(request.requestId())) {
                return Outcome.INVALID;
            }

            try {
                Reply reply = client.evaluate(request, BUDGET);
                if (reply == null || !request.requestId().equals(reply.requestId())
                        || !present(reply.effect()) || !present(reply.policyVersion())) {
                    return Outcome.INVALID;
                }

                return switch (reply.effect()) {
                    case "ALLOW" -> Outcome.ALLOW;
                    case "DENY" -> Outcome.DENY;
                    default -> Outcome.INVALID;
                };
            } catch (BadPayloadException ex) {
                return Outcome.INVALID;
            } catch (TimeoutException | IOException ex) {
                return Outcome.UNAVAILABLE;
            }
        }
    }

    private static boolean present(String text) {
        return text != null && !text.isBlank();
    }

    private static void verify(String label, PolicyClient client, Outcome expected) {
        Outcome actual = new PolicyGateway(client).authorize(REQUEST);
        if (actual != expected) {
            throw new AssertionError(label + ": expected " + expected + ", got " + actual);
        }
        System.out.printf("%s -> %s; granted=%s%n",
                label, actual, actual == Outcome.ALLOW);
    }

    public static void main(String[] args) {
        verify("valid ALLOW", (req, deadline) ->
                new Reply(req.requestId(), "ALLOW", "v1"), Outcome.ALLOW);
        verify("explicit DENY", (req, deadline) ->
                new Reply(req.requestId(), "DENY", "v1"), Outcome.DENY);
        verify("timeout", (req, deadline) -> {
            throw new TimeoutException("deadline exceeded");
        }, Outcome.UNAVAILABLE);
        verify("HTTP 503", (req, deadline) -> {
            throw new IOException("503 Service Unavailable");
        }, Outcome.UNAVAILABLE);
        verify("malformed JSON", (req, deadline) -> {
            throw new BadPayloadException("invalid JSON");
        }, Outcome.INVALID);
        verify("unknown effect", (req, deadline) ->
                new Reply(req.requestId(), "PERMIT", "v1"), Outcome.INVALID);
        verify("wrong requestId", (req, deadline) ->
                new Reply("req-other", "ALLOW", "v1"), Outcome.INVALID);
        verify("missing policy version", (req, deadline) ->
                new Reply(req.requestId(), "ALLOW", ""), Outcome.INVALID);
        verify("null reply", (req, deadline) -> null, Outcome.INVALID);
    }
}
~~~

Biên dịch bằng Java 17 trở lên và chạy:

~~~bash
javac --release 17 PolicyFailureDemo.java
java PolicyFailureDemo
~~~

Stdout chính xác:

~~~text
valid ALLOW -> ALLOW; granted=true
explicit DENY -> DENY; granted=false
timeout -> UNAVAILABLE; granted=false
HTTP 503 -> UNAVAILABLE; granted=false
malformed JSON -> INVALID; granted=false
unknown effect -> INVALID; granted=false
wrong requestId -> INVALID; granted=false
missing policy version -> INVALID; granted=false
null reply -> INVALID; granted=false
~~~

**Giải thích:** Gateway kiểm tra input trước khi gọi PDP; chỉ nhận effect trong tập ALLOW/DENY; kiểm tra requestId và trường bắt buộc; biến lỗi decoder thành INVALID, lỗi hạ tầng thành UNAVAILABLE. Main đóng vai trò test đơn giản: sai một kết quả sẽ ném AssertionError và dừng. Đối với code production, chuyển từng ca thành unit test JUnit 5 với mock/fake, assert số lần gọi client và kiểm tra metric, log theo loại lỗi.

**Giới hạn có chủ ý của demo:** Duration được truyền xuống PolicyClient, nhưng client giả không kiểm tra thời gian thực. Trong triển khai thật, HTTP adapter phải cấu hình deadline, timeout kết nối và timeout đọc; không chỉ hi vọng caller tự ném TimeoutException. Hợp đồng reply ở ví dụ yêu cầu policyVersion; schema dự án thực có thể khác và cần test theo schema đã phê duyệt. Mã không bắt tất cả RuntimeException: lỗi lập trình cần được phát hiện và báo động; tại ranh giới security, mọi đường lỗi vẫn phải bảo đảm không cấp quyền.

## 5. Gắn quyết định vào Spring Security

Ở ứng dụng Servlet dùng Spring Security 6.x, có thể đặt gateway sau AuthorizationManager<RequestAuthorizationContext>. Đây là **trích đoạn tích hợp**, cần có dependencies Spring Security, cấu hình bean và các lớp gateway của dự án; không phải file Java độc lập như mục 4.

~~~java
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

final class PolicyAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final PolicyFailureDemo.PolicyGateway gateway;

    PolicyAuthorizationManager(PolicyFailureDemo.PolicyGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> supplier,
            RequestAuthorizationContext context) {
        Authentication auth = supplier.get();
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        var httpRequest = context.getRequest();
        var input = new PolicyFailureDemo.Request(
                auth.getName(),
                httpRequest.getMethod(),
                httpRequest.getRequestURI(),
                UUID.randomUUID().toString()
        );

        var outcome = gateway.authorize(input);
        return new AuthorizationDecision(
                outcome == PolicyFailureDemo.Outcome.ALLOW
        );
    }
}
~~~

Ví dụ móc vào SecurityFilterChain (trích đoạn nằm trong cấu hình có HttpSecurity):

~~~java
http.authorizeHttpRequests(registry -> registry
    .requestMatchers("/reports/**").access(policyAuthorizationManager)
    .anyRequest().authenticated());
~~~

Khi người dùng đã xác thực nhưng gateway trả DENY, INVALID hoặc UNAVAILABLE, quyết định denied thường dẫn đến **HTTP 403** qua cơ chế xử lý truy cập bị từ chối. Với người dùng chưa xác thực, mã HTTP phụ thuộc AuthenticationEntryPoint và cấu hình xác thực (ví dụ HTTP Basic thường trả 401, form login có thể redirect). Không nên cố định mọi ca lỗi PDP thành HTTP 401/403 nếu kiến trúc có quy tắc riêng; test trước hết phải chứng minh **không có phản hồi thành công để lộ tài nguyên và không chạy side effect**.

Trong production, tên tài nguyên nên được lấy từ định danh đã chuẩn hóa/route đã xác thực (đặc biệt với path chứa tenant hoặc object ID), và action phải phản ánh thao tác nghiệp vụ cần bảo vệ; ví dụ chỉ minh họa từ HTTP method/path. Đừng gửi token thô, thông tin không cần thiết hoặc một danh sách quyền do client tự khai cho PDP. Với Spring Security Reactive, dùng ReactiveAuthorizationManager và pipeline không chặn; áp dụng timeout trên Mono/Flux, chuyển lỗi đã phân loại thành quyết định denied và **không gọi block() trên event loop**.

## 6. Ba lớp kiểm thử và cách xác minh timeout thật

### 6.1. Unit test cho PolicyGateway (nhanh và xác định)

Thay PolicyClient bằng fake/mock, không dùng Thread.sleep để tạo timeout. Cho client trả Reply hoặc ném exception tương ứng từng hàng trong ma trận ở mục 3.

Kiểm tra đồng thời:

- Outcome chính xác và granted chỉ true với ALLOW hợp lệ.
- Một request input hợp lệ chỉ gọi client theo số lần dự định; input thiếu field phải bị chặn trước khi gọi client.
- Deadline truyền cho client đúng cấu hình; timeout/error không kích hoạt fallback dùng quyền mặc định.
- Reply có requestId khác, effect null/lạ, body rỗng, version thiếu đều INVALID dù có chữ ALLOW ở phần khác.
- Tạo hai request đồng thời có requestId khác nhau và ép trả phản hồi đảo thứ tự; mỗi request chỉ nhận kết quả của nó.

Nếu dùng Mockito/JUnit, đặt tên test theo hành vi: shouldDenyWhenPolicyTimesOut, shouldRejectUnknownEffect, shouldRejectMismatchedRequestId, shouldPermitOnlyValidAllow. Với lỗi decoder kiểu unchecked của một thư viện JSON, kiểm thử adapter HTTP chuyển nó thành BadPayloadException (hoặc loại lỗi miền tương đương) trước khi kết quả đi vào gateway.

### 6.2. Integration test cho HTTP adapter / PDP stub

Dùng WireMock hoặc MockWebServer để điều khiển phản hồi HTTP thực; client có deadline tổng hữu hạn và timeout từng pha phù hợp. Với mỗi ca, đo khoảng thời gian hoàn tất với biên hợp lý cho CI, không đòi khớp đúng một mili giây.

1. **Server trì hoãn** lâu hơn read timeout/deadline rồi mới trả ALLOW. Gateway phải ra UNAVAILABLE trong ngân sách, không chờ ALLOW đến trễ.
2. **Socket bị đóng giữa phản hồi** hoặc connection refused. Client chuyển lỗi I/O thành UNAVAILABLE; không có retry vô hạn.
3. **HTTP 503 hoặc 429**. Adapter không parse body lỗi thành một ALLOW giả; số lần retry và tổng thời gian vẫn bị giới hạn.
4. **HTTP 200 nhưng JSON không hợp lệ**, JSON hợp lệ thiếu effect, effect lạ hoặc requestId sai. Phân loại INVALID; không dùng thông tin một phần để cấp quyền.
5. **Kết quả ALLOW hợp lệ trong deadline**. Cho phép, chứng minh lỗi test không làm hỏng nhánh thành công.

Nếu hệ thống sử dụng retry, hãy đặt deadline cho **toàn bộ** lần đánh giá (kể cả retry/backoff), kiểm tra số lần gọi PDP và tác động khi nhiều request cùng timeout. Cancellation trên Future/Mono chỉ là tín hiệu; cần kiểm tra resource/socket thực được giải phóng theo thư viện HTTP sử dụng. Không dựa vào việc cancel chắc chắn dừng mọi công việc remote.

### 6.3. Kiểm thử Spring Security ở biên HTTP

Dùng MockMvc (Servlet) hoặc WebTestClient (Reactive) qua **SecurityFilterChain thật**, mock gateway ở ranh giới phù hợp:

| Tình huống | Assert HTTP/ứng dụng |
| --- | --- |
| Principal hợp lệ + ALLOW | Request đến controller; mã thành công theo API |
| Principal hợp lệ + DENY | Bị chặn, thường 403; method nghiệp vụ không chạy |
| Principal hợp lệ + timeout, 5xx, JSON sai | Bị chặn; không có side effect; kết quả lỗi được log/metric |
| Chưa xác thực | Không vượt qua phân quyền; HTTP response tùy cơ chế xác thực cấu hình |
| Route không được bảo vệ | Chỉ truy cập theo chính sách rõ ràng của route; không vô tình mở rộng matchers |
| Sau một lần ALLOW, PDP lỗi ở request mới | Request mới bị từ chối theo chính sách cache; không dùng nhầm ALLOW cũ |

Với endpoint ghi dữ liệu, thêm verify(service, never()).update(...) hoặc kiểm tra trạng thái database trước/sau; chỉ assert status 403 có thể bỏ sót side effect đã chạy trước kiểm tra quyền. Test dữ liệu nhiều tenant để phát hiện requestId/context bị chia sẻ sai. Nếu cache quyền được cho phép theo yêu cầu nghiệp vụ, khóa cache phải có đủ subject/resource/action/tenant/policy version, có TTL và quy tắc hết hạn rõ ràng; **không tự động cho phép bằng bản ALLOW cũ khi PDP đang lỗi** nếu chưa có chính sách ngoại lệ được phê duyệt.

## 7. Tín hiệu vận hành và lỗi thiết kế thường gặp

**Quan sát được, không rò bí mật.** Ghi metric theo outcome (ALLOW, DENY, INVALID, UNAVAILABLE), nguyên nhân chi tiết (timeout, HTTP 5xx, parse, mismatch) và độ trễ; trace với correlation/requestId. Sử dụng số lượng label giới hạn: không đưa access token, subject cá nhân, resource ID hoặc toàn bộ body PDP thành nhãn metric. Log có mức độ phù hợp và không lộ credential hoặc nội dung nhạy cảm. Test có thể dùng in-memory meter registry/log appender để xác nhận phân loại mà không cần đọc log thủ công.

**Circuit breaker và retry.** Khi breaker mở, kết quả phải bị từ chối theo fail closed và được ghi là không khả dụng. Không retry trên mọi lỗi không phân biệt, không vượt deadline tổng và không tạo cơn bão retry khi PDP đã quá tải. Thất bại của PDP không được làm đường bảo vệ chuyển sang permitAll hoặc bỏ qua AuthorizationManager.

**Phản hồi bất định.** Không dùng các biểu thức kiểu “nếu effect khác DENY thì allow”, “null nghĩa là chính sách không có hạn chế”, hoặc “gọi PDP lỗi thì coi như không có rule”. Mỗi cách trên đều biến sự cố dữ liệu thành lỗ hổng cấp quyền.

**Phân loại rõ.** DENY hợp lệ là kết quả chính sách; INVALID là hợp đồng dữ liệu sai; UNAVAILABLE là sự cố hạ tầng. Gộp cả ba thành một boolean khi trả về Spring Security có thể chấp nhận ở ranh giới cuối, nhưng phải giữ nguyên phân loại ở tầng gateway/telemetry để vận hành và điều tra.

**Tính nhất quán.** Phản hồi PDP chỉ có hiệu lực với yêu cầu đã gửi; requestId, ngữ cảnh tenant và các nghĩa vụ chính sách phải được kiểm tra. Không tái sử dụng kết quả của luồng khác khi request đang chạy đồng thời; bỏ qua ALLOW đến sau timeout. Khi dữ liệu quyền thay đổi, cache và phiên bản chính sách phải có quy tắc vô hiệu hóa.

**Lỗi kiểm thử thường gặp:** chỉ mô phỏng IOException mà bỏ lỗi parse/schema; test timeout bằng sleep dài làm CI chậm và dễ flaky; chỉ gọi trực tiếp gateway mà không đi qua filter chain; chỉ nhìn status mà không xác minh controller không chạy; kỳ vọng 401 cho mọi lỗi; để mock mặc định trả null nhưng không assert lý do; hoặc đo deadline bằng một ngưỡng chính xác tuyệt đối dẫn tới test không ổn định trên máy CI.

## 8. Tiêu chí hoàn thành

Bộ kiểm thử được xem là đủ cho phạm vi bài khi: có phép thử ALLOW/DENY hợp lệ; từng nhóm timeout, lỗi mạng/HTTP và phản hồi không hợp lệ đều bị từ chối; requestId và trường bắt buộc được kiểm tra; deadline thực được test bằng stub mạng; SecurityFilterChain chặn trước nghiệp vụ; lỗi được phân loại có thể quan sát; retry/breaker/cache không tạo đường bypass; và các test chạy ổn định, độc lập với PDP thật.

Nguyên tắc chốt ở mọi tầng: **không có ALLOW hợp lệ cho đúng ngữ cảnh hiện tại thì không cấp quyền**.