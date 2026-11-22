# Không lấy user ID do client gửi làm bằng chứng về danh tính

## 1. Vấn đề: người yêu cầu có thể tự khai mình là bất kỳ ai

Khi gọi API, **client kiểm soát dữ liệu do nó gửi**: tham số URL, query string, JSON body, form field, nhiều HTTP header và cả những giá trị trình duyệt lưu cục bộ. Vì thế, một trường như `userId=u-alice` **chỉ là dữ liệu đầu vào**, không phải bằng chứng người gửi thực sự là Alice.

Một lỗi dễ gặp là viết API:

```http
GET /api/users/u-alice/documents
```

rồi lấy trực tiếp `u-alice` để truy vấn tài liệu:

```java
// Ví dụ SAI: đoạn minh họa, không đặt vào ứng dụng thật.
@GetMapping("/api/users/{userId}/documents")
public List<Document> list(@PathVariable String userId) {
    return repository.findByOwnerUserId(userId);
}
```

Nếu Alice đổi URL thành `/api/users/u-bob/documents` và máy chủ trả dữ liệu của Bob, ứng dụng có lỗi **kiểm soát quyền ở cấp đối tượng** (Broken Object Level Authorization, **BOLA**; còn thường được gọi là IDOR – Insecure Direct Object Reference). Đổi từ số thứ tự sang UUID dài, giấu user ID trong nút giao diện hay kiểm tra ở JavaScript **không giải quyết quyền truy cập**: kẻ gọi có thể tự sửa request bằng DevTools, `curl` hoặc một HTTP client khác.

Nguyên tắc an toàn:

> **Danh tính của người thực hiện hành động phải đến từ kết quả xác thực mà máy chủ đã kiểm chứng.** Mọi user ID hoặc resource ID do client cung cấp chỉ được xem là **đối tượng/đích mà client muốn thao tác**, và phải được kiểm tra quyền trên chính đối tượng đó.

Phân biệt ba khái niệm:

| Khái niệm | Câu hỏi cần trả lời | Nguồn thông tin phù hợp |
| --- | --- | --- |
| **Danh tính người gọi (actor/caller)** | “Ai đang thực hiện yêu cầu?” | `Authentication`/principal được Spring Security tạo sau khi cơ chế xác thực đã kiểm chứng |
| **Định danh tài nguyên (target/resource ID)** | “Người gọi muốn xem/sửa đối tượng nào?” | Có thể nhận từ URL, query hoặc body; phải coi là dữ liệu không đáng tin cho đến khi kiểm tra |
| **Quyết định phân quyền** | “Actor có quyền thực hiện action trên target không?” | Chính sách nghiệp vụ trên bản ghi, tenant, owner, role, trạng thái và các thuộc tính tin cậy phía máy chủ |

Một người dùng có thể được phép **chỉ định ID của người khác**, ví dụ quản trị viên mở hồ sơ khách hàng để hỗ trợ. Trong trường hợp đó, ID trên URL vẫn là **đích truy cập**, không biến người gọi thành khách hàng. Máy chủ phải kiểm tra quyền quản trị và phạm vi quản lý trước khi trả dữ liệu.

## 2. Kẻ tấn công có thể giả mạo user ID qua những chỗ nào?

Các vị trí sau **đều do client điều khiển**:

```http
GET /api/orders?userId=u-bob
X-User-Id: u-bob
Cookie: userId=u-bob
```

```json
{
  "userId": "u-bob",
  "documentId": "doc-982",
  "newTitle": "Update"
}
```

Trên trình duyệt, mã client cũng có thể lưu:

```javascript
// Giá trị chỉ do trình duyệt lưu, có thể thay đổi tùy ý.
localStorage.setItem("userId", "u-bob");
```

Các trường này có thể hữu ích để **chọn tài nguyên**, nhưng không thể thay thế xác thực. Giao diện giấu nút “Sửa của người khác”, dùng input `hidden`, disable form field, đặt user ID trong state của React hoặc mã hóa Base64 cũng không khiến dữ liệu trở thành bằng chứng danh tính.

**Cần phân biệt với token xác thực thật:** access token, session cookie hoặc assertion do client gửi cũng đi qua mạng, nhưng Spring Security (hoặc hệ thống xác thực đáng tin cậy phía trước) phải **xác minh tính hợp lệ và ràng buộc bảo mật** trước khi tạo `Authentication`. Một chuỗi `userId` tùy ý trong cookie khác hoàn toàn với một session ID ngẫu nhiên được máy chủ quản lý hoặc một JWT có chữ ký, issuer/audience/expiry đã được xác minh.

### Ví dụ tấn công BOLA

Giả sử Alice có token của chính mình. API nhận:

```http
GET /api/invoices/invoice-bob-77
Authorization: Bearer <token-hợp-lệ-của-Alice>
```

Nếu server chỉ kiểm tra “token hợp lệ” rồi tải `invoice-bob-77` theo ID, Alice sẽ thấy hóa đơn của Bob. **Xác thực thành công không đồng nghĩa phân quyền trên mọi tài nguyên**. API phải kiểm tra hóa đơn này có thuộc Alice, thuộc tổ chức Alice được tham gia hay được chia sẻ hợp pháp cho Alice không.

Đây là lý do OWASP xếp **Broken Object Level Authorization** là một nhóm rủi ro quan trọng của API: cần kiểm tra quyền tại mọi chức năng xử lý một object ID do client đưa vào, không chỉ ở thời điểm đăng nhập.

## 3. Lấy danh tính đáng tin cậy từ Spring Security

Trong ứng dụng Servlet sử dụng Spring Security, sau khi xác thực thành công, thông tin người dùng hiện tại nằm trong `Authentication` thuộc `SecurityContext`. Spring MVC có thể đưa đối tượng này vào tham số controller:

```java
@GetMapping("/api/me")
public String currentUsername(Authentication authentication) {
    return authentication.getName();
}
```

**Đây là đoạn minh họa một method của controller** trong ứng dụng đã bật Spring Security, không phải chương trình độc lập. `authentication.getName()` lấy tên đã được cơ chế xác thực liên kết với request, không đọc từ `request.getParameter("userId")`.

Cách viết khác khi ứng dụng dùng `UserDetails` làm principal:

```java
@GetMapping("/api/me")
public String currentUsername(
        @AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

Ở ví dụ HTTP Basic, principal thường là `UserDetails`. Trong OAuth2/JWT, kiểu principal có thể là `Jwt`, `JwtAuthenticationToken` hoặc loại khác tùy cấu hình; đừng ép kiểu `UserDetails` cho mọi cơ chế. Khi đã xác thực ở tầng Security, code nghiệp vụ nên lấy **mã người dùng ổn định** từ tài khoản do server lưu hoặc từ danh tính đã được xác minh. Tên đăng nhập/email có thể đổi, nên thường không lý tưởng làm khóa định danh bất biến lâu dài.

**Không tự dựng `Authentication` từ trường client gửi để “giả lập đăng nhập”:**

```java
// SAI: cấp danh tính từ một chuỗi do client tự khai.
String claimedUser = request.getHeader("X-User-Id");
// Không tự coi claimedUser là một principal đã xác thực!
```

`SecurityContextHolder` đáng tin trong phạm vi pipeline **khi** ứng dụng đã bảo vệ đúng bộ lọc và dùng nguồn xác thực đáng tin. Nếu lập trình viên tự đưa principal giả vào `SecurityContext`, hoặc đặt trust sai ở proxy, độ tin cậy đó mất đi. Các luồng chạy nền, async hoặc message consumer cũng phải có cách truyền danh tính/ủy quyền rõ ràng, không mặc nhiên dựa vào ThreadLocal của một request khác.

### Khi dùng JWT hoặc OIDC

Trong ứng dụng cấu hình OAuth2 Resource Server, một JWT chỉ được dùng làm căn cứ danh tính **sau khi** thư viện xác minh chữ ký, thời hạn, issuer, audience (khi ứng dụng yêu cầu) và các ràng buộc theo thiết kế. Với token hợp lệ, `sub` có thể là ID của principal do nhà phát hành gán.

Tuy nhiên:

- Không chỉ gọi Base64 decode payload JWT rồi tin `sub`: payload chưa xác minh có thể bị giả mạo.
- Không tự tin header `X-User-Id` do client gửi là kết quả xác thực. Chỉ tin header danh tính do một proxy/gateway đáng tin tự tạo **sau** khi xác thực, và phải bảo đảm client không thể bỏ qua gateway hay giả header đó.
- Khi nhiều nhà phát hành có thể phát hành cùng `sub`, định danh người dùng thường cần ghép **issuer + subject** hoặc ánh xạ với user ID nội bộ.
- `sub` xác định ai gọi; nó vẫn **không tự cấp quyền** đọc/sửa mọi ID tài nguyên.

## 4. Ví dụ Spring Boot: luôn tra quyền từ user đã xác thực

Ta xây một API đọc tài liệu. Alice sở hữu `doc-a`; Bob sở hữu `doc-b`. Client có thể chỉ định `documentId` trong URL, nhưng không được tự chọn “mình là user nào”. Server tự xác định actor qua `Authentication` và kiểm tra chủ sở hữu bằng dữ liệu đáng tin.

**Dự án:** Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet). Tạo dự án bằng Spring Initializr với dependency **Spring Web** và **Spring Security**; chọn Gradle. Đặt toàn bộ chương trình dưới đây vào:

```text
src/main/java/demo/identity/TrustedIdentityApplication.java
```

Đây là ví dụ **chạy trong dự án có Spring Boot/Security và các dependency vừa nêu**. Không thể biên dịch chỉ với `javac TrustedIdentityApplication.java` khi chưa khai báo thư viện Spring/Jackson. Ví dụ dùng tài khoản và dữ liệu trong bộ nhớ để dễ kiểm thử, không phải thiết kế lưu trữ production.

```java
package demo.identity;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
public class TrustedIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TrustedIdentityApplication.class, args);
    }

    // Username chỉ dùng làm khóa tìm tài khoản trong bản demo.
    // userId là ID ổn định do server quản lý.
    public record UserAccount(String username, String userId) {}

    // Dữ liệu lưu phía server; client không thể tự thay ownerUserId.
    public record StoredDocument(
        String id,
        String ownerUserId,
        String title
    ) {}

    // Chỉ trả những trường client được phép xem.
    public record DocumentView(String id, String title) {}

    static final class DataStore {
        private final Map<String, UserAccount> accounts = Map.of(
            "alice", new UserAccount("alice", "u-alice"),
            "bob", new UserAccount("bob", "u-bob")
        );

        private final Map<String, StoredDocument> documents = Map.of(
            "doc-a",
            new StoredDocument("doc-a", "u-alice", "So tay cua Alice"),
            "doc-b",
            new StoredDocument("doc-b", "u-bob", "So tay cua Bob")
        );

        // Username đã xác thực -> account do server kiểm soát.
        UserAccount currentUser(Authentication authentication) {
            if (authentication == null) {
                return null;
            }
            return accounts.get(authentication.getName());
        }

        List<DocumentView> visibleDocuments(UserAccount caller) {
            return documents.values().stream()
                .filter(doc ->
                    doc.ownerUserId().equals(caller.userId())
                )
                .sorted(Comparator.comparing(StoredDocument::id))
                .map(doc -> new DocumentView(doc.id(), doc.title()))
                .toList();
        }

        DocumentView visibleDocument(
                UserAccount caller,
                String documentId) {

            StoredDocument doc = documents.get(documentId);

            if (doc == null
                    || !doc.ownerUserId().equals(caller.userId())) {
                return null;
            }
            return new DocumentView(doc.id(), doc.title());
        }
    }

    @Bean
    DataStore dataStore() {
        return new DataStore();
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
                .requestMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @RestController
    static final class ApiController {
        private final DataStore store;

        ApiController(DataStore store) {
            this.store = store;
        }

        @GetMapping("/api/me")
        public ResponseEntity<?> me(Authentication authentication) {
            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            return ResponseEntity.ok(
                Map.of(
                    "userId", caller.userId(),
                    "username", caller.username()
                )
            );
        }

        @GetMapping("/api/documents")
        public ResponseEntity<?> list(Authentication authentication) {
            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            return ResponseEntity.ok(
                store.visibleDocuments(caller)
            );
        }

        @GetMapping("/api/documents/{documentId}")
        public ResponseEntity<?> getOne(
                @PathVariable String documentId,
                Authentication authentication) {

            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            DocumentView visible =
                store.visibleDocument(caller, documentId);

            if (visible == null) {
                // Giống hệt khi ID không tồn tại:
                // không tiết lộ tài liệu của người khác.
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok(visible);
        }
    }
}
```

### Giải thích thiết kế

**Bước 1 — xác thực:** `SecurityFilterChain` dùng HTTP Basic cho những yêu cầu GET dưới `/api/**`. Người chưa xác thực sẽ bị yêu cầu cung cấp credentials; Spring Security trả 401 với Basic challenge theo cấu hình và ngữ cảnh HTTP. `SessionCreationPolicy.STATELESS` tránh phụ thuộc HTTP session cho ví dụ đọc dữ liệu. Các method khác bị fallback `denyAll()` từ chối; bảo vệ CSRF mặc định vẫn được giữ và có thể ảnh hưởng đến phương thức ghi nếu sau này bổ sung.

**Bước 2 — lấy actor:** Ở controller, tham số `Authentication authentication` đến từ bối cảnh đã được Spring Security thiết lập. `DataStore.currentUser(...)` tra tên đăng nhập đã xác thực sang `UserAccount` do máy chủ quản lý. ID `u-alice` hoặc `u-bob` **không lấy từ URL/body/header**. Nếu một tài khoản đã xác thực nhưng không có ánh xạ nội bộ, endpoint từ chối 403, không tự tạo account bằng ID mà client tự khai.

**Bước 3 — kiểm tra quyền trên tài nguyên:** `visibleDocument(...)` tải bản ghi theo `documentId` do client yêu cầu, sau đó kiểm tra `ownerUserId` trên bản ghi so với `caller.userId()`. Đây là phép kiểm tra quan trọng hơn việc chỉ xác thực request. Một request có Basic credentials của Alice hợp lệ vẫn bị từ chối nếu nó đòi tài liệu của Bob.

**Bước 4 — giới hạn dữ liệu trả về:** `DocumentView` chỉ có `id` và `title`, tránh gửi kèm cấu trúc nội bộ `ownerUserId` hay các trường nhạy cảm không cần thiết. Kiểm tra quyền ở controller/service và lọc trường JSON giải quyết **hai vấn đề khác nhau**: có được truy cập object và được nhìn thấy property nào.

**Bước 5 — nhất quán về 404:** Khi tài liệu không tồn tại **hoặc** caller không có quyền xem, API trong ví dụ đều trả 404. Đây là lựa chọn giảm việc tiết lộ một ID có thực sự tồn tại hay không. Sản phẩm khác có thể dùng 403 khi thiếu quyền, nhưng phải nhất quán với hợp đồng và chính sách chống lộ thông tin. Đừng xem việc “ẩn bằng 404” là thay thế kiểm tra quyền: chính sách thực sự vẫn nằm ở việc so sánh owner phía server.

### Chạy ví dụ

Trong thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
# PowerShell trên Windows:
# .\gradlew.bat bootRun
```

Nếu dùng PowerShell, `curl` có thể là bí danh của `Invoke-WebRequest`; dùng `curl.exe` cho cú pháp bên dưới. Các ví dụ sau giả định ứng dụng chạy tại `localhost:8080` và chưa thay cổng.

```bash
# 1. Không cung cấp xác thực
curl -i http://localhost:8080/api/me

# 2. Alice xem danh tính do server xác định
curl -i -u alice:alice123 http://localhost:8080/api/me

# 3. Alice xem tài liệu của chính mình
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-a

# 4. Alice thử truy cập tài liệu của Bob
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-b

# 5. Alice giả thêm một user ID vào query parameter
curl -i -u alice:alice123 \
  'http://localhost:8080/api/documents/doc-b?userId=u-bob'

# 6. Bob xem tài liệu của chính mình
curl -i -u bob:bob123 http://localhost:8080/api/documents/doc-b

# 7. Mỗi người chỉ nhận danh sách tài liệu của mình
curl -i -u alice:alice123 http://localhost:8080/api/documents
curl -i -u bob:bob123 http://localhost:8080/api/documents
```

Khi chạy trên PowerShell, viết một lệnh một dòng; ký tự `\` cuối dòng ở đoạn ví dụ là cú pháp nối dòng của Bash.

| Yêu cầu | Status mong đợi | Kết quả quan trọng |
| --- | --- | --- |
| `GET /api/me` không credentials | **401** | Yêu cầu HTTP Basic authentication |
| `GET /api/me` với Alice | **200** | `userId` là `u-alice` từ bản ghi server |
| `GET /api/documents/doc-a` với Alice | **200** | JSON của tài liệu `doc-a` |
| `GET /api/documents/doc-b` với Alice | **404** | Không thể xem object của Bob |
| Cùng request với `?userId=u-bob` giả mạo | **404** | User ID tự khai không thể đổi actor |
| `GET /api/documents/doc-b` với Bob | **200** | JSON của tài liệu `doc-b` |
| `GET /api/documents` với Alice | **200** | Chỉ danh sách tài liệu của Alice |
| `GET /api/documents` với Bob | **200** | Chỉ danh sách tài liệu của Bob |
| `GET /api/documents/khong-ton-tai` với Alice | **404** | Không tìm thấy object phù hợp |

Body dự kiến cho `GET /api/me` bằng Alice (thứ tự key có thể khác):

```json
{
  "userId": "u-alice",
  "username": "alice"
}
```

Body dự kiến cho tài liệu Alice:

```json
{
  "id": "doc-a",
  "title": "So tay cua Alice"
}
```

**Lưu ý về bằng chứng kiểm thử:** không phụ thuộc toàn bộ các header hoặc thứ tự key JSON; xác minh status, body và dữ liệu trả về. Cơ chế HTTP Basic gửi credentials dưới dạng Base64, **không được coi là mã hóa**; chỉ dùng với HTTPS trên mạng thực. Tài khoản/mật khẩu mẫu dùng để học trên máy cục bộ, không đưa vào production.

## 5. Phân biệt “user ID chỉ tài nguyên” và “user ID chứng minh danh tính”

Một hệ thống vẫn có thể có đường dẫn `GET /api/users/{userId}/profile`. Vấn đề không nằm ở việc có tham số `userId`, mà ở việc **dùng nó sai vai trò**.

Ví dụ luồng phân quyền đúng:

1. Máy chủ xác thực request và xác định **actorId = u-alice**.
2. Client yêu cầu **targetUserId = u-bob**.
3. Dịch vụ kiểm tra actor có quyền `READ_PROFILE` trên target không (ví dụ chỉ người dùng tự xem, hoặc quản trị viên được phép xem người cùng tenant).
4. Nếu không đủ quyền thì từ chối; nếu đủ quyền mới truy vấn/trả các trường được cho phép.

Chỉ so sánh `actorId.equals(targetUserId)` có thể đúng cho tính năng **chỉ được xem chính mình**, nhưng **không đủ cho tất cả các bài toán**: quản trị viên, người được chia sẻ, người giám hộ, người được ủy quyền và các luồng doanh nghiệp có thể cần kiểm tra phức tạp hơn. Chiều ngược lại cũng đúng: nếu actor và target khác nhau, không thể tự cấp phép chỉ vì actor có role `ADMIN` mà không kiểm tra tenant/phạm vi quản trị.

Một cách biểu diễn ngắn:

```text
actorId = validatedAuthentication -> serverAccount.id
targetId = request.path / request.query / request.body

allowed = authorizationPolicy.canPerform(
    actorId, action, targetId, trustedResourceAttributes
)
```

Trong đó `trustedResourceAttributes` là dữ liệu về owner, tenant, trạng thái và chia sẻ được lấy từ kho lưu trữ tin cậy. **Không lấy lại owner/tenant từ JSON mà caller gửi để tự chứng minh quyền.**

### Không xem khóa “khó đoán” là phân quyền

Kể cả nếu ID là UUID hoặc chuỗi dài, rò rỉ ID qua link chia sẻ, log, lịch sử trình duyệt, ảnh chụp màn hình, email hoặc một API khác vẫn có thể xảy ra. Không thể dựa vào việc “khó đoán ID” làm căn cứ cho phép truy cập. Nếu sản phẩm thực sự dùng **capability URL** hoặc signed URL như một cơ chế cấp quyền, token của URL đó phải được thiết kế, ký, giới hạn phạm vi/thời hạn và xử lý rò rỉ theo mô hình riêng; một ID thông thường không tự trở thành capability.

### Không dùng role thay cho quyền trên từng object

`hasRole("USER")` chỉ nói người dùng thuộc nhóm USER. Cả Alice và Bob đều có role này; vì thế:

```java
// Chưa đủ cho tài nguyên thuộc từng người.
.requestMatchers("/api/documents/**").hasRole("USER")
```

không bảo đảm Alice chỉ xem tài liệu của Alice. Phải thêm kiểm tra quyền theo **owner hoặc quan hệ chia sẻ** ở service/repository/authorization manager. Đối với hệ thống đa tenant, kiểm tra tenant và quyền trên object trước khi công bố dữ liệu; đừng suy từ tên role rằng người dùng có thể truy cập mọi tenant.

## 6. Đặt kiểm tra quyền gần dữ liệu và thao tác ghi

Ví dụ Java ở mục 4 chỉ đọc dữ liệu bất biến trong bộ nhớ. Trong ứng dụng thật, quy tắc nên được thực thi ở tầng nghiệp vụ, kết hợp truy vấn dữ liệu có ràng buộc.

Ví dụ chỉ cho Alice lấy tài liệu do Alice sở hữu, có thể dùng truy vấn theo **cả ID tài liệu và owner ID đã xác thực**:

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND owner_user_id = :authenticatedUserId;
```

`authenticatedUserId` phải do máy chủ xác định từ principal/định danh nội bộ. `documentId` có thể do client gửi làm đích truy vấn, nhưng phải được bind tham số, không ghép SQL bằng chuỗi.

Đối với thao tác cập nhật, cần kiểm tra quyền ở thời điểm ghi để tránh việc kiểm tra trước một trạng thái rồi ghi sau khi owner/quyền đã thay đổi (time-of-check/time-of-use):

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :documentId
  AND owner_user_id = :authenticatedUserId;
```

Sau đó xác nhận **số bản ghi được cập nhật**. Nếu bằng 0, không thể mặc định coi thao tác thành công; cần xử lý theo hợp đồng (ví dụ 404 cho “không có tài nguyên được phép cập nhật”). Với quy tắc phức tạp (chia sẻ, duyệt nhiều bước, tenant, trạng thái), có thể cần transaction, khóa phù hợp hoặc truy vấn có thêm điều kiện trạng thái.

Không được chỉ tin vào việc frontend đã gọi `GET /api/me` trước đó: trạng thái đăng nhập, quyền, owner hoặc tenant có thể đổi **giữa hai request**. Mỗi thao tác nhạy cảm phải được kiểm tra ở server với danh tính và chính sách hiện hành.

### Tránh mass assignment: user ID và role trong body

Một API cập nhật hồ sơ có thể nhận JSON như:

```json
{
  "displayName": "Alice New",
  "userId": "u-bob",
  "role": "ADMIN"
}
```

Nếu máy chủ map toàn bộ JSON thành entity rồi lưu, client có thể đổi `userId`, `ownerId`, `role`, `tenantId` hoặc trường bảo mật khác. Với endpoint cập nhật **hồ sơ của chính mình**, DTO chỉ nên nhận các trường thực sự cho phép sửa, ví dụ `displayName`; bản ghi cần cập nhật phải được xác định từ actor đã xác thực. Nếu endpoint quản trị cho phép đổi quyền/owner, phải có quyền chuyên biệt và kiểm tra phạm vi, chứ không được bật qua một field tùy ý.

Chính sách tốt thường kết hợp **BOLA** (kiểm tra có được thao tác trên object), **BOPLA/mass assignment** (kiểm tra property nào được đọc/sửa) và **xác thực** (ai thực hiện). Không giải quyết mọi vấn đề chỉ bằng một annotation `@PreAuthorize("isAuthenticated()")`.

## 7. Session, cookie, token, gateway: thế nào là nguồn danh tính đáng tin?

Có sự khác nhau quan trọng giữa **vật mang thông tin xác thực** và **user ID do client tự khai**:

| Thứ client gửi | Có thể dùng để xác thực? | Điều kiện để trở thành cơ sở đáng tin |
| --- | --- | --- |
| `?userId=u-bob` trên URL | Không | Chỉ là đích/thuộc tính request, không có chứng minh |
| `X-User-Id: u-bob` tự gửi | Không | Chỉ tin khi do hạ tầng đáng tin chủ động ghi đè sau xác thực và chặn đường truy cập vòng |
| `Cookie: userId=u-bob` tự viết | Không | Một cookie userId thuần không chứng minh quyền |
| Session cookie mang ID ngẫu nhiên | Có thể | Server xác minh session, ràng buộc principal và thiết lập thuộc tính cookie, session fixation/expiry phù hợp |
| `Authorization: Basic ...` | Có thể | Server xác thực username/password; chỉ truyền qua HTTPS |
| `Authorization: Bearer <JWT>` | Có thể | Resource Server/IdP xác minh chữ ký, issuer, audience/claims áp dụng, thời hạn và chính sách |
| `Authorization: Bearer <opaque-token>` | Có thể | Introspection hoặc cơ chế xác minh token đáng tin, đúng hạn/phạm vi |
| Header danh tính từ gateway | Có điều kiện | Gateway đã xác thực, loại bỏ header do client giả và đường tới backend không cho bypass |

**Ngay cả danh tính đã xác thực cũng chưa đồng nghĩa người đó có quyền xem mọi bản ghi.** Sau xác thực, vẫn phải kiểm tra actor–action–resource trong ngữ cảnh nghiệp vụ.

Đối với web dùng session, cần thêm bảo vệ CSRF cho hành động thay đổi trạng thái, thiết lập cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, quản lý vòng đời session và không đưa session ID vào log. Đối với ứng dụng stateless dùng Bearer token, không vì “stateless” mà bỏ kiểm tra quyền object.

## 8. Những lỗi kỹ thuật phổ biến

### 8.1. Tin `userId` do frontend “đã khóa” trường nhập

`disabled`/`readonly`/hidden input chỉ thay đổi trải nghiệm giao diện, không hạn chế khả năng gửi HTTP request giả. Cách sửa: lấy danh tính ở backend từ `Authentication`; dùng kiểm tra quyền nghiệp vụ mỗi khi truy cập đối tượng.

### 8.2. Lấy `X-User-Id` trực tiếp ở ứng dụng phía sau gateway

Header do client gửi có thể trùng tên header mà hệ thống nội bộ sử dụng. Nếu proxy không xóa header đầu vào và tự tạo lại header xác thực, client có thể chiếm danh tính. Cách sửa: xác định ranh giới trust, cấu hình mTLS hoặc xác thực giữa gateway/backend khi cần, xóa/ghi đè header trước khi chuyển tiếp, bảo đảm backend không truy cập trực tiếp ngoài gateway và audit theo principal đã được kiểm chứng.

### 8.3. Chỉ kiểm tra ID thuộc session khi đăng nhập, rồi tin vào ID sau đó

Quyền, tenant, owner, trạng thái người dùng có thể bị thu hồi hoặc thay đổi. Cần kiểm tra quyền ở mỗi thao tác quan trọng và có chiến lược cache/invalidation rõ ràng; không dùng thông tin lưu cục bộ ở trình duyệt như nguồn sự thật.

### 8.4. Chỉ lọc danh sách, quên endpoint chi tiết hoặc tải xuống

`GET /api/documents` đã lọc theo owner nhưng `GET /api/documents/{id}` tải thẳng ID là lỗi BOLA. Kiểm tra tương tự ở endpoint download, export, preview, update, delete, file attachment, GraphQL resolver và cả batch endpoint. Mỗi đường đi đến object cần cùng chính sách.

### 8.5. Gán quyền từ client trong lệnh ghi

Nếu request cho phép tự gửi `ownerUserId` hoặc `tenantId`, đối tượng mới có thể được tạo/gán sai. Máy chủ phải thiết lập các trường sở hữu dựa vào danh tính được xác thực hoặc kiểm tra quyền gán cụ thể. Không tin `createdBy` hoặc `approvedBy` từ JSON.

### 8.6. Chỉ so tên đăng nhập dưới dạng chuỗi mà không xét namespace

Email/tên đăng nhập có thể thay đổi, tái sử dụng hoặc trùng nhau giữa các nhà cung cấp danh tính. Sau xác thực, hãy ánh xạ đến ID nội bộ ổn định và tenant/issuer đúng. Khi dùng nhiều issuer OIDC, không mặc định hai `sub` giống nhau là cùng một user nếu issuer khác nhau.

### 8.7. Chỉ nhìn status 200 từ các test “happy path”

Một endpoint trả 200 cho Alice chưa chứng minh chặn Bob. Bắt buộc thử client giả userId và truy cập ID object của người khác. Mục tiêu là kiểm tra **quyền sau khi xác thực thành công**. Cũng cần thử tài khoản hợp lệ nhưng bị xóa khỏi hệ thống nội bộ.

## 9. Ma trận kiểm thử để phát hiện lỗi BOLA

Giả sử có hai tài khoản Alice và Bob đều đã đăng nhập hợp lệ:

| Tình huống | Kết quả cần có |
| --- | --- |
| Alice xem `GET /api/me` | Server trả user ID của Alice |
| Alice thêm `?userId=u-bob` vào request `/api/me` | Vẫn là Alice; tham số không đổi actor |
| Alice xem tài liệu `doc-a` của mình | 200 |
| Alice thử xem `doc-b` của Bob bằng cách đổi ID URL | Từ chối (404 trong ví dụ) |
| Alice gửi header `X-User-Id: u-bob` khi xem `doc-b` | Vẫn bị từ chối |
| Bob xem `doc-b` của mình | 200 |
| Không gửi thông tin xác thực | 401/challenge với HTTP Basic trong ví dụ |
| Gửi Basic password sai | 401 |
| Gửi tài liệu không tồn tại | Từ chối theo hợp đồng; ví dụ trả 404 |
| Request cập nhật có field `ownerUserId` hoặc `role` giả | Không được tự thay quyền/sở hữu; phải qua chính sách chuyên biệt |
| Admin của tenant A gọi tài liệu tenant B | Chặn nếu chính sách không cho admin xuyên tenant |
| Quyền bị thu hồi sau khi phiên đăng nhập hình thành | Thao tác tiếp theo phải phản ánh quyền hiệu lực theo thiết kế |

Kiểm thử tích hợp có thể dùng `MockMvc` + Spring Security Test hoặc `curl`/HTTP client. Với chương trình mục 4, kiểm tra status và JSON sau khi ứng dụng khởi động. Khi cần kiểm tra chuyên sâu, tạo thêm dữ liệu với các tenant, tài liệu chia sẻ, quyền thu hồi và kiểm tra các thao tác ghi trong giao dịch.

### Một cách đọc kết quả bảo mật chính xác

- **401**: chưa có xác thực hợp lệ hoặc cần bắt đầu xác thực (ví dụ HTTP Basic).
- **403**: đã xác thực nhưng chính sách từ chối, trong nhiều thiết kế.
- **404**: có thể tài nguyên không tồn tại **hoặc** ứng dụng cố tình không tiết lộ tài nguyên mà người dùng không có quyền nhìn thấy.
- **200**: yêu cầu thành công; cần bảo đảm trả đúng tài nguyên và trường dữ liệu được phép.

Status chính xác cho trường hợp thiếu quyền phụ thuộc hợp đồng sản phẩm; điều không thể thỏa hiệp là **không để lộ tài nguyên của người khác** và không tin user ID do client khai là danh tính.

## 10. Ghi nhớ khi thiết kế API bảo vệ dữ liệu

1. **Actor đến từ xác thực đã được server kiểm chứng.** Trong Spring Security Servlet, lấy `Authentication`/principal ở controller hoặc tầng service theo cơ chế thích hợp.
2. **Resource ID do client chỉ là đích thao tác.** Cho phép client chỉ định tài liệu/hồ sơ cần xử lý nếu phù hợp API, sau đó kiểm tra quyền cụ thể.
3. **Không lấy user ID tùy ý từ path/query/body/header/cookie làm principal.** Dùng session/token được xác minh hoặc ánh xạ đáng tin đến user ID nội bộ.
4. **Kiểm tra quyền object cho mọi điểm truy cập.** List, detail, download, update, delete và batch đều phải được bảo vệ.
5. **Đặt điều kiện owner/tenant/action ở backend**, tốt nhất gần truy vấn/ghi dữ liệu; cân nhắc transaction khi dữ liệu thay đổi đồng thời.
6. **Chặn mặc định khi không rõ quyền.** Không vì mất dữ liệu ánh xạ user hay gặp lỗi policy mà gán ID lấy từ client cho “đỡ lỗi”.
7. **Kiểm thử trường hợp xấu có chủ đích.** Một user hợp lệ giả ID của user khác phải thất bại, ngay cả khi UI không cho nhập ID đó.

### Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
