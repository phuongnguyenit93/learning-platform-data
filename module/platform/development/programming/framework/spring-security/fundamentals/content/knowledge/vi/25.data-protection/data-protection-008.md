# Nhật ký kiểm toán phải cân bằng khả năng truy vết với bảo vệ dữ liệu cá nhân

## 1. Nhật ký kiểm toán là bằng chứng về hoạt động, không phải kho sao chép dữ liệu

Trong một ứng dụng có Spring Security, **nhật ký kiểm toán (audit log / audit trail)** giúp trả lời những câu hỏi quan trọng sau sự cố:

- **Ai** đã cố đăng nhập, được xác thực, bị từ chối quyền, đọc hoặc sửa tài nguyên?
- **Hành động nào** đã được yêu cầu và **trên loại tài nguyên nào**?
- **Khi nào**, ở **hệ thống nào**, với **kết quả gì** và **theo quy tắc nào**?
- Có thể liên kết sự kiện với một request, một giao dịch hoặc một lần thay đổi quyền để điều tra hay không?

Tuy nhiên, nếu ghi nguyên vẹn tất cả request/response, mỗi dòng log có thể chứa mật khẩu, access token, session cookie, email, số điện thoại, địa chỉ, nội dung hồ sơ, dữ liệu kinh doanh hoặc thông tin sức khỏe. Nhật ký lúc đó trở thành **nguồn rò rỉ dữ liệu thứ hai**, đôi khi còn khó kiểm soát hơn cơ sở dữ liệu chính vì được sao chép sang nhiều hệ thống thu thập và giám sát.

Nguyên tắc thiết kế: **ghi đủ sự kiện để truy vết quyết định bảo mật, nhưng chỉ giữ những thuộc tính cần thiết cho mục đích kiểm toán**. Phải bảo vệ nhật ký theo chính sách dữ liệu, phân quyền truy cập và thời gian lưu giữ phù hợp.

Ví dụ khi một người dùng không được phép đọc tài liệu `doc-42`, bản ghi hữu ích có thể là:

```json
{
  "eventType": "DOCUMENT_READ",
  "occurredAt": "2026-11-05T02:15:30Z",
  "actorRef": "actor-8f23",
  "resourceType": "DOCUMENT",
  "resourceRef": "doc-42",
  "action": "READ",
  "outcome": "DENIED",
  "reasonCode": "NOT_VISIBLE",
  "requestId": "e6baf6f7-780a-4a60-9469-c914cf5a8ed1"
}
```

Bản ghi **không cần** chứa password, Bearer token, Cookie, nguyên nội dung tài liệu hoặc toàn bộ thông tin của người dùng. Giá trị trên chỉ minh họa định dạng; timestamp và request ID trong thực tế phải được tạo khi sự kiện xảy ra, không cố định như ví dụ.

### Phân biệt audit log, application log và access log

| Loại log | Mục tiêu chính | Ví dụ |
| --- | --- | --- |
| **Audit log** | Xác định hoạt động và quyết định liên quan tới quyền/dữ liệu | Ai đổi quyền, ai bị từ chối khi mở tài liệu, thao tác nhạy cảm thành công hay thất bại |
| **Application log** | Chẩn đoán luồng chương trình và lỗi vận hành | Service khởi động, lỗi kết nối, timeout, ngoại lệ |
| **Access log** | Theo dõi lượt gọi ở gateway/web server | Phương thức HTTP, đường dẫn đã xử lý an toàn, status, độ trễ |
| **Security alert** | Cảnh báo từ tín hiệu đã tổng hợp | Nhiều lần đăng nhập thất bại, tăng bất thường số lần bị chặn |

Các loại này có thể chia sẻ nền tảng thu thập log nhưng **không nên có cùng trường dữ liệu, quyền xem hoặc thời gian lưu mặc định**. Audit log cần tính nhất quán và khả năng truy vết; access log có tần suất lớn và dễ chứa URL/query nhạy cảm; debug log có thể phải tắt hoặc hạn chế mạnh trong production.

## 2. Thiết kế schema sự kiện: đủ trả lời câu hỏi, tránh dữ liệu thừa

Một schema audit tốt nên xác định rõ **mục đích** của từng trường trước khi triển khai.

| Trường | Mục đích | Lưu ý bảo vệ dữ liệu |
| --- | --- | --- |
| `eventId` | Chống ghi trùng, đối chiếu khi vận chuyển | ID ngẫu nhiên ổn định cho sự kiện; không chứa danh tính |
| `occurredAt` | Sắp xếp theo thời gian, điều tra | Timestamp UTC, đồng bộ thời gian; tách thời điểm xảy ra và thời điểm nhận nếu cần |
| `eventType` / `action` | Phân loại hoạt động | Danh mục cố định như `AUTHN_FAILURE`, `DOCUMENT_READ`, `ROLE_CHANGED` |
| `actorRef` | Liên kết các hành động của một danh tính đã xác thực | Dùng ID nội bộ mờ nghĩa hoặc giá trị giả danh có kiểm soát, hạn chế email/tên thật |
| `subjectRef` / `resourceRef` | Xác định đối tượng bị tác động | Chỉ lưu định danh cần thiết; có thể mã hóa/giả danh nếu bản thân ID nhạy cảm |
| `resourceType` | Xác định loại tài nguyên | Mã loại cố định thay vì lưu body |
| `outcome` | Biết thành công, bị từ chối hay gặp lỗi | Phân biệt `ALLOWED`, `DENIED`, `ERROR`; không đánh đồng |
| `reasonCode` | Biết quy tắc dẫn tới kết quả | Mã ổn định như `OWNER_MISMATCH`; không ghi biểu thức quyền, exception text nhạy cảm |
| `requestId` / `traceId` | Liên kết sự kiện trong một lần xử lý | Nên do hệ thống đáng tin tạo/xác minh; không xem client-supplied ID là bằng chứng |
| `service` / `environment` | Khoanh vùng nơi ghi sự kiện | Không chèn server secret hoặc chi tiết cấu hình nhạy cảm |
| `policyVersion` | Giải thích quyết định theo chính sách tại thời điểm đó | Hữu ích với hệ thống có chính sách thay đổi hoặc phê duyệt |

Không phải mỗi sự kiện phải chứa tất cả các trường. Chẳng hạn, **đăng nhập thất bại** chưa chứng minh người gửi là ai: không nên gán `actorRef` đã xác thực chỉ vì người gửi nhập username của người khác. Có thể ghi `actorRef=unverified` và `reasonCode=INVALID_CREDENTIALS`; nếu cần phân tích cuộc tấn công theo tài khoản bị nhắm tới, lưu **target-account reference được bảo vệ** theo chính sách riêng, thay vì coi nó là người thực hiện.

### Phân biệt danh tính đã xác minh và dữ liệu do client tự khai

Giả sử request mang:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=incorrect-value
```

Bản ghi `AUTHN_FAILURE actorRef=alice` là **khẳng định thiếu căn cứ**: người gửi có thể là bất kỳ ai đang thử mật khẩu của Alice. Sự kiện xác thực thất bại chỉ chứng minh **một lần thử** với thông tin nào đó đã bị từ chối, không chứng minh danh tính người thử.

Ngược lại, sau xác thực thành công, `Authentication` được hệ thống xác thực đáng tin thiết lập có thể dùng để tra mã người dùng nội bộ. Dù vậy, **đã xác thực không có nghĩa đã được phân quyền trên mọi tài nguyên**: audit nên ghi cả quyết định truy cập đối tượng khi liên quan.

### Không lấy `requestId` do client gửi làm bằng chứng

Header `X-Request-Id` từ Internet có thể được giả hoặc trùng. Nếu muốn dùng header từ gateway, gateway phải tạo/kiểm tra/chuẩn hóa header và loại bỏ giá trị giả mạo trước khi chuyển cho backend. Trong trường hợp đơn giản, server tự sinh UUID cho mỗi request. `requestId` hỗ trợ **nối các dấu vết**, không chứng minh người dùng là ai.

## 3. Những gì tuyệt đối không nên đưa vào audit log thông thường

**Không ghi nguyên văn** các trường sau, kể cả khi việc đó có vẻ tiện khi debug:

- Mật khẩu, mã OTP, mã khôi phục, security answer, khóa API, private key, OAuth client secret.
- Bearer token, JWT nguyên chuỗi, refresh token, HTTP Basic header, session ID, CSRF token, session cookie, toàn bộ `Authorization`/`Cookie`.
- Toàn bộ request body, response body, file upload, nội dung tài liệu hoặc bản ghi nghiệp vụ chỉ để “cho dễ điều tra”.
- Dữ liệu cá nhân không liên quan mục đích audit: email/điện thoại/địa chỉ/định danh nhà nước, dữ liệu y tế, thông tin thanh toán.
- Chuỗi lỗi hoặc stack trace đi kèm dữ liệu do client gửi nếu chưa có kiểm soát; có thể chứa credential, SQL parameter và PII.
- URL nguyên vẹn khi query/path có token, email hoặc dữ liệu nhạy cảm. Nên log tên endpoint được chuẩn hóa, ví dụ `/api/documents/{id}`, không lấy toàn bộ `request.getRequestURL()` rồi cộng `getQueryString()`.

Ví dụ phản diện:

```java
// SAI: có thể ghi token và thông tin nhạy cảm.
log.info("Headers: {}", request.getHeaderNames());
log.info("Authorization: {}", request.getHeader("Authorization"));
log.info("Body: {}", rawRequestBody);
log.info("User sent id: {}", request.getParameter("userId"));
```

Đoạn trên minh họa hành vi cần tránh; không đưa nó vào luồng xử lý thật. **Che bớt vài ký tự** của token hoặc mật khẩu không mặc nhiên an toàn: phần còn lại vẫn có thể dùng để liên kết tài khoản hay khôi phục thông tin, tùy cấu trúc bí mật.

Thay vào đó, tạo **allowlist trường được phép ghi** theo từng loại sự kiện. Đừng xây logger nhận toàn bộ đối tượng `HttpServletRequest`, `Authentication`, `UserDetails` hoặc entity rồi serialize tự động: các đối tượng này có thể mở rộng thêm trường nhạy cảm ở phiên bản khác.

### Pseudonymization không đồng nghĩa anonymization

Một `actorRef` được ánh xạ từ ID người dùng sang mã giả danh giúp giảm việc lộ tên thật, nhưng **vẫn là dữ liệu có thể liên kết với cá nhân** nếu hệ thống có thể tra ngược hoặc nối các sự kiện. Vì vậy:

- Quản lý bảng ánh xạ actor ID → người dùng thật ở kho riêng, hạn chế quyền tra cứu.
- Nếu sử dụng HMAC trên user ID để có một mã giả danh ổn định, bảo vệ khóa bằng kho bí mật, cân nhắc phạm vi khóa và vòng đời xoay khóa.
- Không coi `SHA-256(email)` không khóa là cách ẩn danh chắc chắn: email có thể đoán và thử theo từ điển.
- Nếu không cần liên kết hành động theo người dùng, có thể chỉ lưu dữ liệu tổng hợp hoặc không ghi `actorRef`.

Ví dụ thuật toán **minh họa riêng**, không dùng khóa hard-code. Java 17 có thể tạo HMAC-SHA-256 như sau:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditPseudonym {
    private AuditPseudonym() {}

    public static String hmacId(String userId, byte[] secretKey)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
        byte[] value = mac.doFinal(
            userId.getBytes(StandardCharsets.UTF_8)
        );
        return HexFormat.of().formatHex(value);
    }
}
```

Đây là **lớp Java độc lập** nếu đặt trong tệp `AuditPseudonym.java`; lớp yêu cầu khóa bí mật đủ mạnh được cấp từ cơ chế quản lý secret. Việc thêm HMAC chỉ là một phần của chiến lược giả danh, không tự giải quyết quyền truy cập log, thời hạn lưu giữ hoặc nghĩa vụ bảo vệ dữ liệu.

## 4. Audit trong Spring Security: ghi đúng điểm và đúng ngữ nghĩa

Trong ứng dụng Spring Boot 3.x / Spring Security 6.x dạng Servlet, thông tin liên quan audit có thể xuất hiện ở nhiều lớp:

| Nguồn sự kiện | Có thể biết gì? | Lưu ý |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | Một lần cơ chế xác thực hoàn thành thành công | Với HTTP Basic stateless, có thể xảy ra **mỗi request**, không nhất thiết một lần “login” |
| `AbstractAuthenticationFailureEvent` | Có lần xác thực thất bại | Principal nhập vào là **chưa được xác minh**; không log credentials |
| `AuthorizationManager` / `AuthorizationDeniedEvent` khi được cấu hình | Quyết định phân quyền ở tầng Security | Không phải mọi ứng dụng đều tự publish đầy đủ mọi sự kiện quyền; phải xác minh cấu hình thực tế |
| Service nghiệp vụ | Đọc, đổi chủ, xuất dữ liệu, cập nhật role, chuyển trạng thái | Có bối cảnh nghiệp vụ mà filter HTTP không có |
| Controller/gateway | Request ID, endpoint, status, thời gian | Có thể không biết nguyên nhân quyền hoặc không biết giao dịch đã commit |

**Đừng coi mọi HTTP 200 là một thao tác dữ liệu thành công**: service có thể không thay đổi bản ghi nào; một transaction có thể rollback sau khi log “success”; một workflow nền có thể hoàn thành sau request đầu. Audit nghiệp vụ quan trọng nên gắn với **kết quả đã được xác nhận** của hành động. Nếu cần bảo đảm ghi audit cùng cập nhật dữ liệu, có thể dùng một bảng audit trong cùng transaction hoặc **transactional outbox**, sau đó vận chuyển sự kiện ra kho audit; thiết kế phù hợp tùy yêu cầu nhất quán và thất bại của hệ thống.

Cũng không nên viết một `OncePerRequestFilter` rồi coi nó đã bao phủ mọi quyết định bảo mật: filter không nhất thiết biết chủ sở hữu tài nguyên, quyền nghiệp vụ ở service, hoặc kết quả cuối cùng khi giao dịch bất đồng bộ.

### Sự kiện xác thực và sự kiện nghiệp vụ khác nhau

**Xác thực thành công** cho biết thông tin đăng nhập hợp lệ. Nó không nói người dùng đọc được tài liệu cụ thể. Audit việc đọc tài liệu nên được phát từ điểm có thể biết **tài liệu nào** và **phép kiểm tra quyền nào** đã xảy ra. Ngược lại, log trong controller không quan sát được yêu cầu bị từ chối ở filter trước khi controller chạy; muốn ghi 401/403 toàn diện phải quan sát thêm các security handler hoặc event publisher.

## 5. Ví dụ chạy được trong dự án Spring Boot: audit có chọn lọc

Ta tạo API nhỏ với hai tài khoản:

- Alice là chủ tài liệu `doc-a`.
- Bob là chủ tài liệu `doc-b`.

Mục đích học tập: khi ai đó thử xem một tài liệu, log **event, actorRef, resourceRef, outcome, reasonCode, requestId**; không ghi mật khẩu, nội dung tài liệu hoặc header xác thực. Xác thực HTTP Basic phát sự kiện thành công/thất bại; controller phát audit khi có quyết định quyền trên tài liệu.

**Nền tảng:** Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet. Tạo dự án Gradle từ Spring Initializr với **Spring Web** và **Spring Security**. Đặt mã sau vào đúng tệp:

```text
src/main/java/demo/audit/SafeAuditApplication.java
```

Đây là **chương trình Spring Boot đầy đủ trong dự án có các dependency trên**; không thể biên dịch chỉ với `javac SafeAuditApplication.java` nếu chưa có thư viện Spring. Tài khoản, dữ liệu và cơ chế log sử dụng cho thực hành cục bộ, không phải kiến trúc lưu audit production.

```java
package demo.audit;

import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuditApplication.class, args);
    }

    // Thông tin nội bộ; không serialize thẳng thành JSON.
    public record StoredDocument(
        String id,
        String ownerUsername,
        String content
    ) {}

    // DTO chỉ chứa thông tin được cho phép trả về.
    public record DocumentView(String id, String content) {}

    static final class DocumentStore {
        private final Map<String, StoredDocument> documents = Map.of(
            "doc-a",
            new StoredDocument(
                "doc-a", "alice", "Noi dung cua Alice"
            ),
            "doc-b",
            new StoredDocument(
                "doc-b", "bob", "Noi dung cua Bob"
            )
        );

        StoredDocument find(String id) {
            return documents.get(id);
        }
    }

    @Bean
    DocumentStore documentStore() {
        return new DocumentStore();
    }

    // Bản demo minh họa danh tính đã xác thực -> mã mờ nghĩa.
    // Production: lấy actor ID nội bộ hoặc mã giả danh từ
    // kho dữ liệu tin cậy, không dùng tên/email trong log.
    static final class AuditTrail {
        private static final Logger LOG =
            LoggerFactory.getLogger(AuditTrail.class);

        private final Map<String, String> actorRefs = Map.of(
            "alice", "actor-1001",
            "bob", "actor-1002"
        );

        String actorRef(Authentication authentication) {
            if (authentication == null
                    || !authentication.isAuthenticated()) {
                return "unverified";
            }
            return actorRefs.getOrDefault(
                authentication.getName(), "actor-unmapped"
            );
        }

        void record(
                String event,
                String actorRef,
                String resourceRef,
                String outcome,
                String reasonCode,
                String requestId) {

            // Chỉ ghi các trường có chủ đích; không stringify
            // Authentication, HttpServletRequest hay entity.
            LOG.info(
                "audit event={} actor_ref={} resource_ref={} "
                    + "outcome={} reason_code={} request_id={}",
                event, actorRef, resourceRef,
                outcome, reasonCode, requestId
            );
        }

        @EventListener
        void authenticationSucceeded(AuthenticationSuccessEvent event) {
            record(
                "AUTHN_SUCCESS",
                actorRef(event.getAuthentication()),
                "none",
                "ALLOWED",
                "CREDENTIAL_ACCEPTED",
                "unavailable"
            );
        }

        @EventListener
        void authenticationFailed(AbstractAuthenticationFailureEvent event) {
            // Không đọc username chưa xác minh hoặc credentials
            // trong event.getAuthentication().
            record(
                "AUTHN_FAILURE",
                "unverified",
                "none",
                "DENIED",
                "AUTHN_FAILED",
                "unavailable"
            );
        }
    }

    @Bean
    AuditTrail auditTrail() {
        return new AuditTrail();
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        // Bật công bố các sự kiện xác thực phổ biến
        // từ AuthenticationManager/ProviderManager.
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/**"
                ).authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @RestController
    static final class DocumentController {
        private final DocumentStore documents;
        private final AuditTrail audit;

        DocumentController(DocumentStore documents, AuditTrail audit) {
            this.documents = documents;
            this.audit = audit;
        }

        @GetMapping("/api/documents/{documentId}")
        ResponseEntity<?> readDocument(
                @PathVariable String documentId,
                Authentication authentication) {

            // ID do máy chủ tạo: không tin giá trị client tự khai.
            String requestId = UUID.randomUUID().toString();
            String actorRef = audit.actorRef(authentication);
            StoredDocument document = documents.find(documentId);

            boolean allowed = authentication != null
                && authentication.isAuthenticated()
                && document != null
                && document.ownerUsername().equals(
                    authentication.getName()
                );

            if (!allowed) {
                // Không ghi nguyên documentId khi không tìm thấy
                // bản ghi tin cậy. Không phân biệt ID không tồn
                // tại với ID mà caller không được phép xem.
                String resourceRef =
                    document == null ? "unknown" : document.id();

                audit.record(
                    "DOCUMENT_READ",
                    actorRef,
                    resourceRef,
                    "DENIED",
                    "NOT_VISIBLE",
                    requestId
                );

                return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .header("X-Request-Id", requestId)
                    .build();
            }

            audit.record(
                "DOCUMENT_READ",
                actorRef,
                document.id(),
                "ALLOWED",
                "OWNER_MATCH",
                requestId
            );

            return ResponseEntity
                .ok()
                .header("X-Request-Id", requestId)
                .body(new DocumentView(
                    document.id(), document.content()
                ));
        }
    }
}
```

### Giải thích ranh giới bảo mật của ví dụ

**`AuditTrail.record(...)` dùng allowlist field.** Tất cả giá trị `event`, `outcome` và `reasonCode` được tạo trong code từ tập giá trị có chủ đích. `actorRef` lấy từ ánh xạ server-side của danh tính đã được Spring Security xác thực. `resourceRef` lấy từ bản ghi tin cậy nếu tồn tại; ID người dùng thử đoán không được ghi thẳng khi bản ghi không tồn tại. `requestId` tạo bằng UUID trên server trong controller. Không log body, password, Authorization header, Cookie hoặc exception message.

**`AuthenticationEventPublisher` cung cấp sự kiện xác thực.** `DefaultAuthenticationEventPublisher` chuyển những kết quả xác thực tương ứng thành sự kiện Spring. Listener `authenticationSucceeded(...)` dùng principal đã được xác minh; listener `authenticationFailed(...)` **không** ghi username mà client đã nhập, vì người gửi chưa chứng minh mình sở hữu username đó. Việc nhận một loại event cụ thể còn phụ thuộc loại authentication provider và exception thực tế; không mặc định mọi lỗi xác thực ở mọi tích hợp bên ngoài đều phát event giống nhau.

**Với HTTP Basic stateless, AUTHN_SUCCESS có thể xuất hiện cho nhiều request liên tiếp của cùng một tài khoản.** Đây là **sự kiện xác thực thành công cho request**, không nhất thiết biểu thị “người dùng bắt đầu một phiên đăng nhập mới”. Nếu gom thành “số lần đăng nhập”, thống kê sẽ sai. Với form login/session, ngữ nghĩa có thể khác. Phải định nghĩa rõ đơn vị sự kiện trước khi xây báo cáo bảo mật.

**`DOCUMENT_READ` được ghi tại nơi kiểm tra quyền sở hữu.** Tên controller có tham số `documentId`, nhưng actor không lấy từ URL hoặc JSON do client gửi. Dù Alice gửi Basic credentials hợp lệ, đọc `doc-b` vẫn bị chặn; event ghi `DENIED`. Đối với bản ghi không tồn tại và bản ghi bị chặn, API cùng trả **404** để hạn chế tiết lộ sự tồn tại; đây là lựa chọn cho demo, không phải mọi API đều phải dùng 404 thay 403.

**`requestId` trong ví dụ chỉ được tạo khi controller chạy.** Vì vậy các sự kiện `AUTHN_SUCCESS`/`AUTHN_FAILURE` phát từ filter dùng `request_id=unavailable` và chưa liên kết với controller request ID. Trong sản phẩm thật, muốn nối từ gateway đến Security filter rồi business event, phải triển khai cơ chế correlation ID tại **đầu request**, tạo/chuẩn hóa bằng thành phần đáng tin và dọn context sau request. Không khẳng định ví dụ ngắn này đã có end-to-end tracing.

**Log SLF4J là công cụ minh họa**, chưa có cơ chế lưu không thể sửa, hạn chế quyền người xem, mã hóa, retention, chuẩn hóa thời gian hay giao hàng bền vững. Các phần đó cần được thiết kế khi triển khai sản phẩm. Tính nhất quán của audit với transaction cần được bảo đảm riêng; log “ALLOWED” trước khi xử lý ghi thực tế không đồng nghĩa dữ liệu đã commit.

### Chạy dự án và thử các kịch bản

Trong thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

Trong terminal khác, gọi các request HTTP GET:

```bash
# 1. Không đăng nhập: xử lý ở Security filter, thường 401.
curl -i http://localhost:8080/api/documents/doc-a

# 2. Sai mật khẩu: xác thực bị từ chối.
curl -i -u alice:wrong http://localhost:8080/api/documents/doc-a

# 3. Alice đọc tài liệu của mình: 200.
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-a

# 4. Alice thử đọc tài liệu Bob: 404 theo chính sách demo.
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-b

# 5. Bob đọc tài liệu của mình: 200.
curl -i -u bob:bob123 http://localhost:8080/api/documents/doc-b
```

Nếu PowerShell dùng alias `curl` khác cú pháp curl truyền thống, hãy dùng `curl.exe`. Không dùng credentials mẫu trên hệ thống công khai. HTTP Basic chỉ an toàn khi được bảo vệ bằng HTTPS trên mạng thực, vì Base64 không phải mã hóa.

Kết quả cần xác minh:

| Tình huống | HTTP status | Audit kỳ vọng |
| --- | --- | --- |
| Không có Basic credentials | 401 | Có thể không phát `AUTHN_FAILURE`; đây là yêu cầu **chưa gửi credentials**, khác với xác thực sai |
| Basic credentials sai | 401 | `AUTHN_FAILURE` nếu AuthenticationEventPublisher/provider phát sự kiện phù hợp |
| Alice đọc `doc-a` | 200 | `AUTHN_SUCCESS` và `DOCUMENT_READ ALLOWED` |
| Alice đọc `doc-b` | 404 | `AUTHN_SUCCESS` và `DOCUMENT_READ DENIED` |
| Bob đọc `doc-b` | 200 | `AUTHN_SUCCESS` và `DOCUMENT_READ ALLOWED` |

Ví dụ **hình dạng** các dòng audit trong console (thứ tự, timestamp và request ID thay đổi theo lần chạy; phần tiền tố log framework được lược bỏ):

```text
audit event=AUTHN_FAILURE actor_ref=unverified resource_ref=none outcome=DENIED reason_code=AUTHN_FAILED request_id=unavailable
audit event=AUTHN_SUCCESS actor_ref=actor-1001 resource_ref=none outcome=ALLOWED reason_code=CREDENTIAL_ACCEPTED request_id=unavailable
audit event=DOCUMENT_READ actor_ref=actor-1001 resource_ref=doc-a outcome=ALLOWED reason_code=OWNER_MATCH request_id=<server-generated-request-id>
audit event=DOCUMENT_READ actor_ref=actor-1001 resource_ref=doc-b outcome=DENIED reason_code=NOT_VISIBLE request_id=<server-generated-request-id>
```

Các dòng trên chỉ cho biết **kiểu sự kiện và trường được ghi**; đừng coi chúng là stdout cố định của một lần chạy. Khi kiểm thử audit, so sánh danh mục sự kiện, outcome, mã lý do và sự hiện diện của ID được tạo; tránh so sánh timestamp hay UUID nguyên văn.

## 6. Thu thập từ đâu để vừa đủ truy vết?

Một hệ thống cần kiểm toán tốt phải có **bản đồ điểm phát sự kiện**. Không có một listener duy nhất nào luôn biết tất cả:

1. **Authentication layer:** ghi các lần xác thực thành công/thất bại với nghĩa đúng của cơ chế (form login, Basic, token refresh, OAuth2/OIDC, MFA...).
2. **Authorization layer:** ghi những quyết định từ chối có ý nghĩa. Một request có thể bị `AuthorizationFilter`, `@PreAuthorize`, CSRF filter, policy engine hoặc service nghiệp vụ từ chối; cần lựa chọn điểm ghi để không mất hoặc nhân đôi sự kiện.
3. **Business service:** ghi những hành động đáng kiểm toán như xem/xuất dữ liệu nhạy cảm, sửa quyền, đổi chủ sở hữu, duyệt giao dịch, xóa/khôi phục bản ghi. Sự kiện phải phản ánh kết quả cuối cùng, không chỉ “controller được gọi”.
4. **Background worker:** có thể thao tác không có HTTP request. Ghi **service identity/job identity** và ngữ cảnh người khởi tạo nếu được truyền hợp lệ, không lấy lại ThreadLocal của một request đã kết thúc.
5. **Gateway/proxy:** cung cấp correlation ID, endpoint và tín hiệu vận hành; không tự giả định biết quyền sở hữu ở tầng dữ liệu.

Nếu mọi tầng đều phát `AUTHN_FAILURE` cho cùng một lần gọi, thống kê sẽ bị nhân đôi. Nên định nghĩa **sự kiện có chủ sở hữu rõ ràng**: ví dụ AUTHN từ hệ thống xác thực, DOCUMENT_READ từ service tài liệu, ROLE_CHANGED từ dịch vụ phân quyền. Khi có nhiều hệ thống gửi trùng, dùng `eventId` hoặc cơ chế idempotency để khử trùng phù hợp.

### Ghi thất bại và thành công khác nhau

- **Một thao tác bị chặn:** ghi thời điểm, loại hành động, actor đã xác minh nếu có, tài nguyên đã chuẩn hóa hoặc mã giả danh phù hợp, outcome `DENIED` và mã lý do an toàn. Không cần tiết lộ điều kiện phân quyền chi tiết cho client.
- **Một thao tác đọc thành công:** nếu thuộc loại nhạy cảm và có yêu cầu audit, ghi “ai đọc loại tài liệu nào”, không sao chép toàn bộ tài liệu vào log.
- **Một thao tác ghi thành công:** ghi thay đổi ở mức cần thiết như loại cập nhật, actor, resource, kết quả commit. Tránh ghi toàn bộ “trước–sau” của các trường nhạy cảm vào một kho log dễ truy cập.
- **Một lỗi hệ thống:** ghi outcome `ERROR` và mã lỗi; chi tiết stack trace dùng application log riêng với kiểm soát dữ liệu. Không đổi một lỗi transport thành `DENIED` chỉ để giảm số loại sự kiện.

## 7. Bảo vệ audit log sau khi đã ghi

**Ghi ít dữ liệu là bước đầu; kho log vẫn cần bảo vệ như hệ thống lưu dữ liệu quan trọng.**

### 7.1. Phân quyền xem và tách nhiệm vụ

Người phát triển, vận hành, hỗ trợ khách hàng và kiểm toán viên không mặc nhiên cần cùng một quyền xem. Có thể thiết kế:

- Dashboard vận hành hiển thị sự kiện tổng hợp, mã lý do và thống kê, không cho tra danh tính thực.
- Người phụ trách điều tra được cấp quyền tra `actorRef` sang danh tính thật qua thủ tục được kiểm soát, có lý do, thời hạn và nhật ký truy cập riêng.
- Tài khoản ứng dụng chỉ được **append/write** sự kiện, không thể sửa hoặc xóa bản ghi đã ghi.
- Nhân viên có quyền quản trị cơ sở dữ liệu nghiệp vụ không đồng thời mặc nhiên có quyền sửa lịch sử kiểm toán.

Cần ghi cả **ai đã truy cập kho audit và vì sao**, tránh để hệ thống kiểm toán trở thành công cụ theo dõi cá nhân tùy ý.

### 7.2. Bảo vệ đường truyền và lưu trữ

Dùng kết nối được xác thực và mã hóa từ dịch vụ đến hệ thống thu thập log; bật mã hóa dữ liệu lưu khi phù hợp; quản lý khóa, rotation và backup theo chính sách riêng. Không đặt secret của pipeline logging trong file cấu hình công khai hoặc log chính nó. Với dữ liệu audit cần bảo đảm toàn vẹn mạnh, cân nhắc lưu append-only, WORM/immutable retention, chữ ký/HMAC chuỗi băm hoặc kho bảo đảm bất biến, kèm kiểm chứng độc lập. **Một trường checksum tự tính bên cạnh bản ghi, cùng nằm trong kho mà quản trị viên có thể sửa cả hai, không đủ để chứng minh không ai chỉnh sửa.**

Đồng bộ đồng hồ máy chủ (UTC/NTP) và ghi cả thời điểm tiếp nhận nếu hệ thống phân tán cần phân tích độ trễ. Correlation ID giúp nối dấu vết, nhưng điều tra nhiều dịch vụ cần xem cả độ tin cậy của timestamp, log bị trễ và lần thử gửi lại.

### 7.3. Retention và xóa dữ liệu

Không áp dụng quy tắc “audit log giữ vĩnh viễn” cho mọi trường hợp. Xác định mục đích sử dụng, thời gian cần điều tra, nghĩa vụ pháp lý/hợp đồng và quy định hiện hành để đặt **thời hạn lưu khác nhau theo loại sự kiện**. Ví dụ log vận hành có thể có vòng đời ngắn hơn sự kiện thay đổi quyền đặc biệt; đây là quyết định của chính sách tổ chức, không có một số ngày chung cho mọi sản phẩm.

Cần quản lý cả bản sao ở collector, data lake, index tìm kiếm, backup và hệ thống alert. Một lịch xóa ở bảng chính **không có nghĩa** dữ liệu đã hết tồn tại ở mọi bản sao. Nếu có yêu cầu hạn chế hoặc xóa dữ liệu cá nhân, phải đánh giá nghĩa vụ lưu chứng cứ và cơ sở pháp lý tương ứng thay vì tùy tiện xóa hoặc từ chối mọi trường hợp.

### 7.4. Giảm rủi ro từ log injection

Nếu ghi thông tin do client gửi như username, path hoặc user agent, chuỗi có thể chứa ký tự xuống dòng hoặc ký tự điều khiển nhằm giả dòng log mới. Biện pháp phù hợp là **không ghi giá trị không cần thiết**, chuẩn hóa dữ liệu và chỉ dùng structured logging/encoder có escape đúng. Với trường cần ghi, giới hạn độ dài, ký tự và format theo schema trước khi gửi tới sink. Đừng nối string tùy ý vào mẫu log nếu có thể dùng trường cố định đã kiểm soát.

## 8. Audit của ứng dụng đa tenant và hệ thống có dữ liệu nhạy cảm

Một actor có thể thuộc nhiều tenant hoặc truy cập dữ liệu theo ủy quyền. Khi đó `actorRef` riêng lẻ không đủ giải thích quyết định; có thể cần thêm `tenantRef`, `actingOnBehalfOfRef`, `policyVersion` hoặc `delegationRef`, nhưng chỉ khi các trường đó thật sự phục vụ mục đích kiểm toán và được lấy từ nguồn đáng tin.

Ví dụ, người quản trị tenant A truy cập tài nguyên tenant B:

```json
{
  "eventType": "DOCUMENT_EXPORT",
  "actorRef": "actor-1001",
  "tenantRef": "tenant-a",
  "resourceRef": "doc-tenant-b-1",
  "outcome": "DENIED",
  "reasonCode": "CROSS_TENANT_ACCESS"
}
```

Bản ghi nêu **lý do loại quyền** thay vì sao chép hồ sơ người dùng hoặc toàn bộ điều kiện nội bộ. Nếu tenant ID hoặc document ID tự nó là thông tin nhạy cảm, cần dùng định danh mờ nghĩa, mã giả danh có kiểm soát hoặc ẩn một phần theo quyền của người xem.

Cần tránh hai lỗi ngược nhau:

- **Ghi quá nhiều** để điều tra nhanh nhưng lộ hồ sơ cá nhân, mật khẩu, nội dung giao dịch.
- **Ghi quá ít** đến mức không thể phân biệt tài khoản hợp lệ đã thay quyền, lỗi xác thực, trục trặc hệ thống hay một lần truy cập trái quyền.

Lựa chọn đúng dựa trên các **câu hỏi kiểm toán cụ thể**. Ví dụ “Ai thay role ADMIN và thao tác đã commit chưa?” cần actor, target account reference, action, quyền trước/sau ở mức mã hóa/giới hạn thích hợp, kết quả commit, thời điểm và sự kiện tương quan. Không nhất thiết cần tên, email, toàn bộ request body và mọi trường trong tài khoản.

## 9. Kiểm thử cả khả năng truy vết lẫn nguy cơ lộ dữ liệu

Một kiểm thử audit tốt có **hai nhánh chứng minh đồng thời**:

1. Sự kiện bảo mật quan trọng **đã được ghi đủ trường cần thiết**.
2. Những giá trị nhạy cảm **không xuất hiện** trong log, collector hoặc nơi có thể xem thông thường.

| Kịch bản | Sự kiện cần có | Nội dung không được xuất hiện |
| --- | --- | --- |
| Basic credentials sai | `AUTHN_FAILURE` với actor chưa xác minh | Password, Basic header, username chưa xác minh nếu không có chính sách lưu mục tiêu riêng |
| Alice đọc tài liệu của mình | `DOCUMENT_READ ALLOWED`; actorRef mờ nghĩa | Mật khẩu, toàn bộ request, token |
| Alice thử đọc tài liệu Bob | `DOCUMENT_READ DENIED` | Nội dung tài liệu Bob, thông tin riêng của Bob |
| Người dùng chưa có credentials | Có thể có access/security event “authentication required” theo thiết kế | Không gán họ thành một tài khoản có danh tính |
| Người quản trị đổi quyền | `ROLE_CHANGED` với actor và target reference phù hợp, outcome sau commit | Credential, phiên đăng nhập, mọi thuộc tính cá nhân không liên quan |
| Client gửi query chứa token hoặc email | Ghi endpoint chuẩn hóa nếu cần | Query nguyên văn chứa token/email |
| Request cố chứa newline trong header | Event vẫn có cấu trúc hợp lệ nếu trường đó được thu thập | Không tạo dòng log giả hoặc vượt độ dài cho phép |
| Collector không hoạt động | Có tín hiệu giám sát thất bại, queue/retry hoặc cơ chế theo chính sách | Không âm thầm đánh dấu “audit đã ghi bền vững” nếu chưa có xác nhận |
| Xóa dữ liệu theo retention | Bản ghi hết hạn được xử lý theo chính sách trên các bản sao | Không sót index/backup ngoài phạm vi kiểm soát đã công bố |

Với ứng dụng demo, hãy kiểm tra `curl` và console cho 401, 200, 404 như mục 5; sau đó tự thử gửi query `?password=secret-value` tới một URL có thể truy cập. **Không được thấy `secret-value` trong dòng audit của `AuditTrail`**, vì mã không log URL/query. Tuy nhiên, reverse proxy hoặc access log bên ngoài **có thể** vẫn ghi query nếu cấu hình như vậy; cần kiểm tra cả pipeline, không chỉ logger trong mã Java.

Không đặt token thật hoặc dữ liệu cá nhân thật vào test kiểm tra rò rỉ. Dùng giá trị giả có thể nhận diện để xác minh bộ lọc dữ liệu không ghi nó, và xác nhận cả raw log, structured event, collector, dashboard lẫn backup phù hợp.

## 10. Checklist triển khai thực tế

1. **Xác định câu hỏi audit** trước khi chọn trường: yêu cầu điều tra nào cần được trả lời, ai được xem kết quả.
2. **Định nghĩa schema sự kiện** với event ID, UTC time, actor/resource reference, action, outcome, reason, correlation ID và nguồn sự kiện khi thực sự cần.
3. **Lấy actor từ xác thực đáng tin**; không xem username vừa nhập trong một lần login thất bại là người gọi đã xác minh.
4. **Lấy thuộc tính tài nguyên từ server**; không tin owner, role hoặc tenant do client tự khai.
5. **Allowlist dữ liệu ghi**, cấm credential/token/session/cookie và body/response nhạy cảm.
6. **Tách authentication, authorization và business audit**, tránh bỏ sót hoặc đếm trùng.
7. **Ghi kết quả đúng thời điểm**, chú ý transaction, retry, async job và sự kiện rollback.
8. **Kiểm soát quyền đọc, tìm kiếm, xuất và sửa log**, bảo vệ đường truyền, lưu trữ, tính toàn vẹn và bản sao.
9. **Định nghĩa retention và quy trình xóa/hạn chế xử lý dữ liệu** theo mục đích và nghĩa vụ áp dụng.
10. **Kiểm thử cả sự kiện cần có và thông tin không được ghi**, theo dõi collector lỗi và sự thay đổi khi nâng version framework.

**Điểm cần nhớ:** nhật ký kiểm toán tốt không phải nhật ký chứa càng nhiều dữ liệu càng tốt. Nó là **chuỗi bằng chứng có cấu trúc, có mục đích, đáng tin và được kiểm soát truy cập**, đủ để giải thích các hành động bảo mật mà vẫn giảm tối đa việc lưu giữ dữ liệu cá nhân và bí mật.

### Tài liệu tham khảo

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security API — DefaultAuthenticationEventPublisher](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP User Privacy Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)
