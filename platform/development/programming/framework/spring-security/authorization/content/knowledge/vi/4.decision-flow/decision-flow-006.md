# Cho phép, từ chối, không đưa ra quyết định và cách xử lý mặc định trong Spring Security

> **Ngữ cảnh:** Luồng quyết định (authorization decision flow) trong Spring Security cho ứng dụng Servlet/Spring MVC. Bài này giải thích **ALLOW/GRANT**, **DENY** và **ABSTAIN/không đưa ra quyết định**, cách nhiều chính sách phối hợp, và cách thiết kế điểm quyết định cuối với nguyên tắc **default deny**.

## 1. Ba trạng thái trong một quyết định phân quyền

Khi người dùng gửi yêu cầu, hệ thống cần trả lời: **chủ thể này có được làm hành động này trên tài nguyên này hay không?** Một bộ kiểm tra quyền riêng lẻ có thể đưa ra ba loại kết quả:

| Trạng thái | Ý nghĩa của bộ kiểm tra | Ví dụ |
| --- | --- | --- |
| **ALLOW / GRANT** | Chính sách xác định rõ yêu cầu thỏa điều kiện được phép | Alice là chủ tài liệu nên được xem tài liệu của mình |
| **DENY** | Chính sách xác định rõ yêu cầu bị cấm hoặc không đủ điều kiện | Alice thiếu quyền `report:write` để sửa báo cáo |
| **ABSTAIN / NO DECISION** | Chính sách **không quyết định** yêu cầu này; thường vì nó không có trách nhiệm xét tình huống đó | Một rule chỉ xử lý tài liệu tài chính nhận yêu cầu đọc hồ sơ nhân sự |

Đây là **trạng thái của một policy/authorization manager**, chưa chắc là câu trả lời HTTP cuối cùng. Đặc biệt:

- **ALLOW** không có nghĩa “bỏ qua mọi tầng bảo mật”. Một bộ kiểm tra cho phép nhưng tầng khác (method security, điều kiện tenant, kiểm tra trạng thái bản ghi) vẫn có thể từ chối.
- **DENY** là quyết định không cho phép. Trong Spring Security, nó thường dẫn đến ngoại lệ bảo mật; từ đó cơ chế xử lý ngoại lệ trả 401, 403 hoặc chuyển hướng tùy ngữ cảnh xác thực.
- **ABSTAIN không phải ALLOW**; nó cũng **không tự động bằng DENY** trong mọi API. Đó là dấu hiệu **chưa có kết luận từ bộ kiểm tra hiện tại**, nên phải có quy tắc kết hợp và xử lý cuối rõ ràng.

Có thể biểu diễn đơn giản:

~~~text
policy(subject, action, resource, context)
    |
    +-- ALLOW   -> policy này đồng ý cấp quyền
    +-- DENY    -> policy này từ chối cấp quyền
    +-- ABSTAIN -> policy này không có kết luận

finalDecision(...) -> ALLOW hoặc DENY
                   (ABSTAIN phải được xử lý có chủ đích)
~~~

**Nguyên tắc thiết kế:** *một thao tác nhạy cảm chỉ được thực thi khi hệ thống thu được một quyết định cấp quyền hợp lệ theo hợp đồng chính sách*. Không được dùng “không có rule nào chặn” làm bằng chứng có quyền.

## 2. Nhận diện đúng lý do không có quyết định

Các trường hợp sau thường bị trộn lẫn:

1. **Rule không áp dụng:** rule “kiểm soát hạn mức thanh toán” nhận request xem hồ sơ. Nếu hệ thống hỗ trợ rule nhiều phạm vi, nó có thể trả `ABSTAIN` để rule khác xử lý.
2. **Không tìm thấy rule khớp URL:** request `/api/new-feature` chưa được khai báo trong `authorizeHttpRequests`. Đây là **khoảng trống cấu hình**, cần fallback như `anyRequest().denyAll()`.
3. **Đã khớp rule nhưng người dùng thiếu quyền:** `hasAuthority("invoice:approve")` trả **DENY**, không phải abstain, nếu thiếu authority.
4. **Chưa xác thực:** khi endpoint được bảo vệ yêu cầu đăng nhập, thiếu credential không phải lý do hợp lệ để “không quyết định rồi cho đi tiếp”; Spring Security dùng authentication entry point theo cấu hình.
5. **Dữ liệu thiếu hoặc không đáng tin:** bản ghi không tồn tại, chưa đọc được tenant/owner, hoặc policy service lỗi. Với security-sensitive operation, phải **fail closed** (từ chối hoặc trả lỗi không thực hiện thao tác), thay vì diễn giải thiếu dữ liệu thành ALLOW.
6. **Endpoint cố ý công khai:** `permitAll()` là **quy tắc cho phép tường minh**; nó không đồng nghĩa với “không viết rule”.
7. **Policy bị lỗi kỹ thuật:** timeout hay exception từ kho quyền không phải một phiếu ALLOW. Cách trả HTTP có thể là 5xx hoặc 403 theo hợp đồng hệ thống, nhưng **không thực hiện thao tác bị bảo vệ**.

Bảng phân biệt:

| Tình huống | Kết quả logic nên quan sát | Cách xử lý thực tế |
| --- | --- | --- |
| Có grant hợp lệ, các điều kiện bắt buộc đều đạt | ALLOW | Đi tiếp tới endpoint/service |
| Authority/role không đạt | DENY | Từ chối; trả lỗi phù hợp |
| Rule riêng không phụ trách request | ABSTAIN | Chuyển cho quy tắc phù hợp khác hoặc fallback |
| Không có rule HTTP nào được khai báo cho đường dẫn | Không có chính sách khớp | Áp dụng `anyRequest().denyAll()` |
| Policy cần dữ liệu nhưng kho dữ liệu lỗi | Không đánh giá được an toàn | Dừng request; không được mặc nhiên cho phép |
| URL được khai báo công khai | ALLOW từ `permitAll()` | Cho đi tiếp; các cơ chế bảo vệ khác vẫn có thể áp dụng |

## 3. Dòng chảy quyết định ở phía Servlet

Luồng khái niệm cho request có bảo vệ:

~~~text
Client
  |
  v
Spring Security filter chain
  |
  +-- Authentication filters
  |     -> xác định người gọi, thiết lập SecurityContext nếu phù hợp
  |
  +-- AuthorizationFilter
  |     -> chọn AuthorizationManager phù hợp với request
  |     -> AuthorizationResult:
  |          granted=true  -> cho request tiếp tục
  |          granted=false -> từ chối, xử lý ngoại lệ
  |          null          -> manager không ra quyết định
  |                           (không được coi là DENY toàn cục nếu
  |                            chưa có cơ chế fallback rõ ràng)
  |
  +-- DispatcherServlet -> Controller
          |
          +-- Method security (@PreAuthorize), nếu được bật
          |     -> có thể tiếp tục cho phép hoặc từ chối độc lập
          |
          +-- Dữ liệu/logic nghiệp vụ
                -> tenant, ownership, trạng thái, các điều kiện khác
~~~

Sơ đồ chỉ mô tả những điểm liên quan đến quyết định quyền, không phải danh sách đầy đủ mọi filter. `AuthorizationFilter` làm việc với `AuthorizationManager`; `ExceptionTranslationFilter` tham gia biến các ngoại lệ xác thực/phân quyền thành phản hồi HTTP.

**Quan trọng:** không nên dùng một điểm quyết định duy nhất rồi mặc định mọi phần còn lại an toàn. Ví dụ HTTP có thể cho phép `GET /api/documents/101` vì người gọi đã đăng nhập, nhưng service vẫn cần kiểm tra người gọi có được đọc **document 101** hay không.

### 401 và 403 không phải cách đặt tên cho ALLOW/DENY/ABSTAIN

- **401 Unauthorized** thường xuất hiện khi cần xác thực nhưng chưa cung cấp/không chấp nhận credential, ví dụ với HTTP Basic.
- **403 Forbidden** thường xuất hiện khi người dùng đã xác thực nhưng không đủ quyền hoặc có quy tắc từ chối.
- Với form login, trường hợp chưa đăng nhập có thể nhận **302 redirect** đến trang login.
- CSRF, các filter khác và exception handler được tùy biến cũng có thể ảnh hưởng status.

Do đó: **ABSTAIN không có “mã HTTP mặc định” riêng**. Kết quả HTTP phụ thuộc **quyết định cuối** và ngữ cảnh xử lý ngoại lệ.

## 4. `AuthorizationManager` trong Spring Security hiện đại

Spring Security dùng API `AuthorizationManager<T>` thay thế hướng tùy biến cũ `AccessDecisionManager`/`AccessDecisionVoter` cho nhiều use case.

Ở Spring Security **6.5**, phương thức:

`AuthorizationResult authorize(Supplier<Authentication> authentication, T object)`

có thể trả một kết quả phân quyền hoặc **`null` khi không có quyết định**. Các implementation thông dụng trả `AuthorizationDecision`, chứa trạng thái boolean qua `isGranted()`.

| Giá trị trả về của manager | Ý nghĩa |
| --- | --- |
| `new AuthorizationDecision(true)` | ALLOW từ manager |
| `new AuthorizationDecision(false)` | DENY từ manager |
| `null` | ABSTAIN / chưa quyết định |

API `check(Supplier<Authentication>, T)` có dạng trả `AuthorizationDecision`, nhưng trong Spring Security 6.5 được đánh dấu **deprecated**, khuyến nghị dùng `authorize`; các method lambda/kế thừa cụ thể cần kiểm tra phiên bản khi triển khai custom manager.

`AuthorizationManager#verify(...)` gọi đánh giá và ném `AccessDeniedException` khi gặp quyết định phủ định. **Không nên mặc định rằng `verify`, `AuthorizationFilter` hoặc mọi interceptor sẽ tự đổi `null` thành DENY**. Nếu chính sách của ứng dụng đòi từ chối khi không có quyết định, hãy làm cho manager/điểm tổng hợp cuối **trả `AuthorizationDecision(false)` tường minh**.

### Vì sao `null` có ích ở manager trung gian?

Giả sử một hệ thống có:

- Rule A kiểm tra quyền đọc tài liệu tài chính.
- Rule B kiểm tra quyền xem hồ sơ nhân sự.
- Rule C kiểm tra quyền quản trị hệ thống.

Rule A không nên tự cấp hay từ chối hồ sơ nhân sự nếu không chịu trách nhiệm về loại resource đó; nó có thể abstain để bộ tổng hợp xét Rule B. **Nhưng nếu cả A, B, C đều abstain, hệ thống phải có default rõ ràng.** Đây là hai công việc khác nhau: *biết rule nào áp dụng* và *quyết định cho phép cuối cùng*.

## 5. Ghép nhiều quyết định: OR, AND, ưu tiên từ chối

Khi kết hợp policy, cần chọn một hợp đồng rõ ràng. Những chiến lược thường dùng là:

### 5.1. “Any permit” — chỉ cần một quy tắc cấp phép

Một yêu cầu có thể được đọc khi **là owner hoặc được chia sẻ quyền READ**. Đây là kiểu kết hợp OR trong nghiệp vụ. Tuy nhiên, điều kiện cấm tuyệt đối (ví dụ khác tenant) không nên bị một grant yếu hơn vô hiệu hóa.

### 5.2. “All required” — mọi điều kiện bắt buộc phải qua

Quyền sửa hóa đơn có thể cần **có authority `invoice:write`, cùng tenant và trạng thái `DRAFT`**. Chỉ một điều kiện bị từ chối là không được sửa. Các điều kiện bắt buộc phải được đánh giá; **không thể mặc nhiên thay điều kiện chưa được xét bằng true**.

### 5.3. “Deny overrides” — deny ưu tiên trước permit

Với các ràng buộc chặn bắt buộc (tenant boundary, tài khoản bị khóa, tài nguyên bị cấm), có thể định nghĩa quy tắc tổng hợp:

1. Nếu có **DENY** từ ràng buộc bắt buộc: kết quả **DENY**.
2. Nếu không có deny và có ít nhất một **ALLOW** từ nguồn cấp quyền phù hợp: kết quả **ALLOW**.
3. Nếu tất cả rule đều **ABSTAIN**: kết quả **DENY** (default deny).

Đây là **một chính sách tổng hợp do ứng dụng lựa chọn**, không phải kết luận rằng mọi API Spring Security đều tổng hợp phiếu theo đúng thứ tự này.

### 5.4. Factory `AuthorizationManagers`

Spring Security có các factory `AuthorizationManagers.allOf(...)` và `anyOf(...)`. Từ Spring Security 6.3, các overload nhận một `AuthorizationDecision allAbstainDefaultDecision` giúp **đặt mặc định tường minh khi không có manager hoặc tất cả đều abstain**:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Fragment minh họa bên trong cấu hình có các manager first, second:
AuthorizationManager<RequestAuthorizationContext> oneOf =
    AuthorizationManagers.anyOf(
        new AuthorizationDecision(false), first, second
    );

AuthorizationManager<RequestAuthorizationContext> allRequired =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false), first, second
    );
~~~

Đây là **fragment**, không phải một lớp chạy độc lập: `first` và `second` cần được khai báo với cùng kiểu manager. Overload với fallback giúp tránh phụ thuộc vào hành vi khi **tất cả** rule abstain. Không được tự suy diễn rằng OR hoặc AND luôn có logic “deny overrides” theo ý nghiệp vụ: hãy đọc contract factory, nhất là khi rule có thể abstain.

Các overload không truyền default cũng tồn tại và có quy tắc riêng với manager trống/abstain. Với hệ thống cần *fail closed*, dùng overload tường minh hoặc tự thiết kế bộ tổng hợp và test các tình huống all-abstain.

## 6. Ví dụ Java 17 thuần: ABSTAIN được xử lý thành DENY ở cuối

Ví dụ độc lập dưới đây có ba rule:

- `tenantBoundary`: từ chối truy cập tenant khác, còn cùng tenant thì **ABSTAIN** (rule này không tự cấp quyền).
- `ownerGrant`: cấp quyền nếu là owner, còn không thì **ABSTAIN**.
- `sharedReaderGrant`: cấp quyền **READ** nếu được chia sẻ, còn lại **ABSTAIN**.
- `finalDecision`: **DENY** nếu gặp cấm tenant; **ALLOW** nếu có grant hợp lệ; **DENY** khi tất cả abstain.

Điều đó ngăn một permission trên tài liệu bị áp dụng sai tenant hoặc một người không được chia sẻ vẫn được xem tài liệu.

Tạo tệp **`DecisionFlowDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;

public class DecisionFlowDemo {

    enum Decision { ALLOW, DENY, ABSTAIN }
    enum Action { READ, EDIT }

    record Subject(String username, String tenant) {}

    record Document(
        String id,
        String tenant,
        String owner,
        Set<String> sharedReaders
    ) {}

    @FunctionalInterface
    interface Rule {
        Decision decide(Subject subject, Action action, Document document);
    }

    static Decision tenantBoundary(
            Subject subject, Action action, Document document) {
        if (!subject.tenant().equals(document.tenant())) {
            return Decision.DENY;
        }
        return Decision.ABSTAIN;
    }

    static Decision ownerGrant(
            Subject subject, Action action, Document document) {
        return subject.username().equals(document.owner())
            ? Decision.ALLOW : Decision.ABSTAIN;
    }

    static Decision sharedReaderGrant(
            Subject subject, Action action, Document document) {
        return action == Action.READ
                && document.sharedReaders().contains(subject.username())
            ? Decision.ALLOW : Decision.ABSTAIN;
    }

    static Decision finalDecision(
            Subject subject, Action action, Document document) {
        List<Rule> rules = List.of(
            DecisionFlowDemo::tenantBoundary,
            DecisionFlowDemo::ownerGrant,
            DecisionFlowDemo::sharedReaderGrant
        );

        boolean hadGrant = false;
        for (Rule rule : rules) {
            Decision vote = rule.decide(subject, action, document);
            if (vote == Decision.DENY) {
                return Decision.DENY; // Ràng buộc bắt buộc từ chối.
            }
            if (vote == Decision.ALLOW) {
                hadGrant = true;
            }
        }

        // Tất cả ABSTAIN -> DENY, không mở quyền ngầm.
        return hadGrant ? Decision.ALLOW : Decision.DENY;
    }

    static void show(Subject s, Action a, Document d) {
        System.out.println(
            s.username() + " " + a + " " + d.id()
                + " = " + finalDecision(s, a, d)
        );
    }

    public static void main(String[] args) {
        Subject alice = new Subject("alice", "acme");
        Subject bob = new Subject("bob", "acme");
        Subject carol = new Subject("carol", "orbit");
        Subject maya = new Subject("maya", "acme");

        Document doc101 = new Document(
            "doc-101", "acme", "alice", Set.of("bob")
        );

        show(alice, Action.EDIT, doc101);
        show(bob, Action.READ, doc101);
        show(bob, Action.EDIT, doc101);
        show(carol, Action.READ, doc101);
        show(maya, Action.READ, doc101);

        System.out.println(
            "ownerRule(bob) = " + ownerGrant(bob, Action.READ, doc101)
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ trong thư mục chứa tệp:

~~~bash
javac DecisionFlowDemo.java
java DecisionFlowDemo
~~~

**Stdout chính xác:**

~~~text
alice EDIT doc-101 = ALLOW
bob READ doc-101 = ALLOW
bob EDIT doc-101 = DENY
carol READ doc-101 = DENY
maya READ doc-101 = DENY
ownerRule(bob) = ABSTAIN
~~~

Giải thích:

- Alice được EDIT vì là owner và đúng tenant.
- Bob được READ do được chia sẻ; EDIT không có grant nào nên **tất cả rule ngoài tenant boundary đều abstain** và quyết định cuối là DENY.
- Carol bị DENY do khác tenant, ngay cả khi các rule khác có thể cấp quyền theo điều kiện đơn giản.
- Maya cùng tenant nhưng không sở hữu/không được chia sẻ. Rule tenant chỉ abstain; cả hệ thống vẫn **DENY**.
- Kết quả `ownerRule(bob) = ABSTAIN` là **phiếu của một rule**, trong khi kết quả `bob READ doc-101 = ALLOW` là **phán quyết cuối** vì rule chia sẻ cấp quyền.

Đây là chương trình mô phỏng policy, **không sử dụng Spring Security**; nó giúp làm rõ logic trước khi ghép vào framework. Trong thực tế, phải nạp tenant, owner và danh sách chia sẻ từ nguồn server đáng tin, xử lý lỗi dữ liệu, quản lý vòng đời quyền và kiểm thử việc thay đổi quyền.

## 7. Spring Boot Java 17+: fallback DENY khi manager không biết xử lý

Ở backend Servlet, có thể dùng `authorizeHttpRequests` để đặt chính sách HTTP rõ ràng. Ví dụ dưới đây:

- `GET /public/info` được **ALLOW tường minh** bằng `permitAll()`.
- `GET /api/reports/summary` được custom manager đánh giá quyền `report:read` và trả ALLOW/DENY.
- `GET /api/reports/archived` đi vào custom manager nhưng policy nội bộ **không có rule tương ứng** (candidate = `null`); **manager cuối cùng chuyển thành DENY**.
- `GET /other` không nằm trong các matcher trên, bị `anyRequest().denyAll()` chặn.
- Không có request API nào được mở chỉ vì policy không biết xử lý.

Tạo một ứng dụng Maven với **Java 17+**, dependency **Spring Web** và **Spring Security** (ví dụ Spring Boot 3.x tương thích). Đặt mã vào tệp **`src/main/java/com/example/decision/DecisionApplication.java`**:

~~~java
package com.example.decision;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DecisionApplication {

    public static void main(String[] args) {
        SpringApplication.run(DecisionApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> reportPolicy)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .requestMatchers("/api/reports/**").access(reportPolicy)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> reportPolicy() {
        return (authentication, context) -> {
            String route = context.getRequest().getServletPath();

            // Rule nội bộ chỉ phụ trách /api/reports/summary.
            AuthorizationDecision candidate = null;
            if ("/api/reports/summary".equals(route)) {
                boolean canRead = authentication.get().getAuthorities()
                    .stream()
                    .anyMatch(a -> "report:read".equals(a.getAuthority()));
                candidate = new AuthorizationDecision(canRead);
            }

            // Bảo đảm manager cuối không để ABSTAIN lọt ra ngoài.
            return candidate != null
                ? candidate
                : new AuthorizationDecision(false);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("ROLE_USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class ReportController {

        @GetMapping("/public/info")
        String info() {
            return "public info";
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "quarterly summary";
        }

        @GetMapping("/api/reports/archived")
        String archived() {
            return "archived report";
        }

        @GetMapping("/other")
        String other() {
            return "unlisted endpoint";
        }
    }
}
~~~

Mã trên dùng API `AuthorizationManager<RequestAuthorizationContext>` theo cách Spring Security 6.x hỗ trợ. Lambda của manager trả `AuthorizationDecision` cho mọi yêu cầu; biến `candidate` biểu diễn kết quả nội bộ có thể thiếu quyết định.

**Tại sao không trả `null` trực tiếp ra `AuthorizationFilter`?** Ở cấp API, `null` biểu thị abstain chứ **không phải** một quyết định phủ định. Điểm cuối của chính sách bảo mật cần một kết quả rõ ràng để không phụ thuộc ngầm vào cách interceptor/manager khác xử lý abstain. Đây là chủ đích *fail closed*.

**Phạm vi ví dụ:** đường dẫn được so sánh bằng `getServletPath()` với ứng dụng chạy tại context path mặc định và servlet mapping thông thường. Nếu ứng dụng có context path, gateway rewrite, path matcher động hoặc nhiều servlet, hãy dùng thông tin matcher/path variables phù hợp và kiểm thử routing thực tế. Mã chỉ dùng GET để trình bày quyết định, không thay đổi dữ liệu; với thao tác ghi, vẫn cần authorization theo action và CSRF theo cơ chế xác thực.

### Chạy và quan sát

Tại thư mục dự án:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Thử từng request khi ứng dụng đã khởi động ở `localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/info
curl -i http://localhost:8080/api/reports/summary
curl -i -u alice:demo123 http://localhost:8080/api/reports/summary
curl -i -u bob:demo456 http://localhost:8080/api/reports/summary
curl -i -u alice:demo123 http://localhost:8080/api/reports/archived
curl -i -u alice:demo123 http://localhost:8080/other
~~~

| Request | HTTP kỳ vọng | Điều được minh họa |
| --- | --- | --- |
| Public, không credential | 200, `public info` | `permitAll()` là ALLOW chủ động |
| Summary, không credential | 401 (HTTP Basic) | Cần authentication/authority |
| Summary, Alice | 200, `quarterly summary` | Có `report:read`; manager trả ALLOW |
| Summary, Bob | 403 | Thiếu `report:read`; manager trả DENY |
| Archived, Alice | 403 | Rule nội bộ abstain; manager cuối trả DENY |
| `/other`, Alice | 403 | Không khớp các matcher trước, `anyRequest().denyAll()` |

**Lưu ý mã lỗi:** Với form login, request chưa đăng nhập có thể nhận redirect. Với anonymous truy cập một endpoint bị `denyAll()`, `ExceptionTranslationFilter` có thể khởi chạy entry point tương ứng thay vì 403; bảng dùng tài khoản Alice cho hai trường hợp fallback để quan sát DENY rõ ràng.

Các password chỉ phục vụ demo, không dùng trong môi trường thật; HTTP Basic phải đi cùng HTTPS ở production.

## 8. `permitAll`, `denyAll` và `anyRequest` là các quyết định tường minh

Một cấu hình dễ kiểm toán:

~~~java
// Fragment cấu hình, đặt bên trong http.authorizeHttpRequests:
.requestMatchers("/public/**").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

Những điều cần hiểu:

- Các matcher được đánh giá **theo thứ tự khai báo**; quy tắc đầu tiên phù hợp được sử dụng.
- `permitAll()` cho phép những request được khớp, nhưng không tắt toàn bộ security filter chain hoặc mọi tầng method/domain authorization.
- `denyAll()` cấm request theo quy tắc tương ứng.
- `authenticated()` chỉ yêu cầu danh tính đã xác thực theo logic của Spring Security; không kiểm tra role/ownership cụ thể.
- `anyRequest().denyAll()` là **fallback cho URL chưa khai báo**. Nó giúp tránh endpoint mới vô tình được mở.
- Nếu đặt một matcher rộng như `/api/**` trước matcher cụ thể `/api/admin/**` thì matcher cụ thể sau có thể không còn được xét. Hãy sắp quy tắc từ cụ thể đến bao quát.

**Tầng HTTP có fallback rõ ràng chưa đảm bảo method và dữ liệu an toàn.** Ví dụ `/api/docs/{id}` có thể yêu cầu `authenticated()`, còn service phải kiểm tra xem user có quyền trên **đối tượng doc id này** và **tenant này** hay không.

## 9. Trạng thái ABSTAIN của mô hình voter cũ

Trước `AuthorizationManager`, Spring Security sử dụng các thành phần `AccessDecisionManager` và `AccessDecisionVoter` (hiện là hướng API cũ/deprecated trong các nhánh hiện đại).

`AccessDecisionVoter` có ba giá trị số:

- `ACCESS_GRANTED` — phiếu đồng ý.
- `ACCESS_DENIED` — phiếu phản đối.
- `ACCESS_ABSTAIN` — voter không áp dụng/không tham gia quyết định.

Các `AccessDecisionManager` cũ từng có chiến lược như:

| Manager cũ | Ý tưởng tổng hợp |
| --- | --- |
| `AffirmativeBased` | Có ít nhất một phiếu GRANT thì cho phép theo quy tắc affirmative |
| `UnanimousBased` | Bị từ chối nếu có phiếu DENY; xét grant theo quy tắc unanimous |
| `ConsensusBased` | So sánh phiếu GRANT/DENY; hòa phiếu theo cấu hình |
| `AbstractAccessDecisionManager` | Cung cấp cấu hình khi **mọi voter đều abstain**; mặc định thường từ chối |

Các chiến lược có tùy chọn và điều kiện riêng; bảng chỉ nêu **ý tưởng**, không phải đặc tả đầy đủ mọi góc cạnh. Một `ACCESS_ABSTAIN` ở voter legacy khác về kiểu dữ liệu với `null` ở `AuthorizationManager` hiện đại, dù cùng thể hiện “không quyết định”. **Không sao chép cấu hình all-abstain của voter cũ sang API mới rồi cho rằng hành vi giống hệt.**

Khi bắt gặp tài liệu cũ có `allowIfAllAbstainDecisions`, cần biết đó là tùy chọn của mô hình cũ. Với code mới, ưu tiên `AuthorizationManager`, default tường minh và test được mọi kết quả.

## 10. Xây chính sách “default deny” xuyên các tầng

**Ở HTTP:** khai báo `anyRequest().denyAll()` cho request không khớp rule. Với matcher tùy biến, bảo đảm trường hợp “policy không áp dụng” không rơi qua thành kết quả cấp quyền.

**Ở method:** bảo vệ các service operation nhạy cảm bằng `@EnableMethodSecurity` và `@PreAuthorize`/`@PostAuthorize` hoặc manager phù hợp. Các phương thức **không có annotation bảo mật** không tự bị cấm chỉ bởi việc bật method security; cần thiết kế coverage và test. `@PreAuthorize("hasAuthority('invoice:approve')")` chỉ kiểm permission; kiểm tra invoice instance có thể còn cần owner/tenant/trạng thái.

**Ở dữ liệu:** không lấy dữ liệu đã truy xuất rồi chỉ kiểm quyền sau khi trả response. Đặc biệt với `LIST/SEARCH`, lọc theo tenant/quyền ngay trong query để tránh lộ số lượng bản ghi, phân trang hoặc thông tin không được phép.

**Với lỗi kỹ thuật:** nếu server không thể kiểm tra quyền do database/policy engine lỗi, chọn cơ chế **dừng hoạt động** và phản hồi lỗi phù hợp. Không được bắt mọi exception rồi trả `new AuthorizationDecision(true)`, hoặc tự diễn giải `null` thành ALLOW để “không làm gián đoạn dịch vụ”.

**Với thay đổi quyền:** session/JWT/cache có thể giữ authority cũ. Đảm bảo chiến lược thu hồi, cập nhật, TTL và kiểm thử khi user bị bỏ role hoặc thay đổi tenant.

## 11. Ma trận kiểm thử bắt buộc

Không chỉ kiểm tra “user đúng thì 200”. Cần kiểm cả trạng thái không quyết định:

| Kịch bản | Quyết định mong đợi | Vì sao |
| --- | --- | --- |
| Rule khớp và user có authority | ALLOW | Cấp quyền tường minh |
| Rule khớp nhưng thiếu authority | DENY | Từ chối tường minh |
| Rule nội bộ không nhận ra loại resource | ABSTAIN ở tầng rule, **DENY ở cuối** | Fallback fail closed |
| Mọi rule đều abstain | DENY ở cuối | Không có bằng chứng cấp quyền |
| Vào endpoint mới chưa có matcher | DENY | `anyRequest().denyAll()` |
| Endpoint công khai đã khai báo | ALLOW | `permitAll()` |
| Hợp lệ ở HTTP, sai quyền service | DENY | Nhiều tầng bảo vệ |
| User đúng role nhưng khác tenant | DENY | Chính sách dữ liệu |
| Database quyền không sẵn sàng | Không thực hiện thao tác | Không được fail open |
| Client tự gửi role/owner giả | DENY | Dữ liệu quyền phải được xác minh ở server |

Khi kết hợp `AuthorizationManagers.anyOf/allOf`, viết test cho **ALLOW + ABSTAIN**, **DENY + ABSTAIN**, **ALLOW + DENY**, **mọi ABSTAIN** và **không có manager**; kỳ vọng phụ thuộc contract tổ hợp đã chọn. Mục đích là chứng minh **không có tổ hợp nào vô tình cho phép một request đáng lẽ phải bị cấm**.

## 12. Những sai lầm thường gặp

1. **“ABSTAIN nghĩa là không cấm nên cho phép.”** Sai. Đây là “chưa có kết luận”; cần quyết định cuối rõ ràng.
2. **“Không tìm thấy route matcher thì chắc Spring Security tự deny.”** Đừng dựa vào giả định này. Khai báo `anyRequest().denyAll()`.
3. **“Chỉ có DENY mới nguy hiểm; null thì vô hại.”** Nguy hiểm ở điểm tổng hợp không xử lý abstain. Tạo fallback DENY và test.
4. **“Nếu có một ALLOW thì chắc chắn được vào.”** Có thể vẫn còn tenant boundary, method security hoặc điều kiện cấm bắt buộc khác.
5. **“Trả 401 nghĩa là bị từ chối quyền.”** 401 thường liên quan xác thực, trong khi 403 thường là từ chối quyền với user đã xác thực; response cuối phụ thuộc entry point/handler.
6. **“`permitAll` và thiếu rule có cùng nghĩa.”** Sai: một bên là cho phép được chủ động khai báo, bên còn lại là khoảng trống cấu hình.
7. **“Thêm `@EnableMethodSecurity` là mọi service method tự bảo vệ.”** Không: cần khai báo chính sách trên những thao tác cần kiểm tra.
8. **“Để authorization service lỗi thì tạm cho phép.”** Là hành vi fail open; có thể làm lộ dữ liệu. Phải dừng hành động bị bảo vệ khi không thể xác minh quyền.
9. **“Có quyền một endpoint là có quyền trên mọi bản ghi.”** Cần kiểm permission theo resource instance, tenant, ownership và trạng thái.
10. **“Kết quả all-abstain ở voter legacy giống hệt manager mới.”** Không bảo đảm; API và default strategy khác nhau.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Rule A chỉ phụ trách invoice, nhận request mở hồ sơ nhân sự. Nó nên trả gì trong thiết kế nhiều rule?  
**Trả lời:** ABSTAIN (không áp dụng). Điểm cuối phải có rule phù hợp hoặc default DENY.

**Câu 2.** Rule owner abstain, rule chia sẻ cấp ALLOW, không có điều kiện cấm nào. Quyết định cuối theo chính sách OR grant ví dụ?  
**Trả lời:** ALLOW, vì quyền chia sẻ hợp lệ.

**Câu 3.** Rule owner cấp ALLOW nhưng tenant boundary trả DENY. Theo chính sách deny-overrides?  
**Trả lời:** DENY. Không được cho phép vượt tenant.

**Câu 4.** Mọi rule đều abstain, hệ thống muốn fail closed. Phải trả gì ở điểm cuối?  
**Trả lời:** DENY tường minh, ví dụ `new AuthorizationDecision(false)`.

**Câu 5.** `@PreAuthorize("hasAuthority('report:read')")` gặp người đã đăng nhập nhưng thiếu authority. Đây là ABSTAIN hay DENY?  
**Trả lời:** DENY cho điều kiện quyền đã được áp dụng.

**Câu 6.** Endpoint `/api/new` chưa nằm trong rule HTTP và có `anyRequest().denyAll()`. Kết quả?  
**Trả lời:** DENY. Status HTTP có thể khác nhau tùy người gọi đã xác thực hay chưa.

**Câu 7.** `AuthorizationDecision(true)` có tự bỏ qua tất cả `@PreAuthorize` và tenant checks?  
**Trả lời:** Không. Các tầng kiểm tra còn lại có thể từ chối độc lập.

**Câu 8.** Vì sao phải test trường hợp mọi manager đều abstain?  
**Trả lời:** Để phát hiện đường xử lý thiếu chính sách và xác nhận fallback có chủ đích, tránh fail open.

**Ghi nhớ:** Một policy có thể trả **ALLOW**, **DENY** hoặc **ABSTAIN**. **ABSTAIN là trạng thái trung gian**, còn quyền truy cập cuối phải được quyết định bởi chính sách rõ ràng. Với tài nguyên được bảo vệ, hãy thiết kế **mặc định từ chối**, chỉ cho phép khi điều kiện cấp quyền hợp lệ đã được kiểm chứng.

## Tài liệu chính thức

- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — `AuthorizationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 — `AuthorizationManagers` composition APIs: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html
- Spring Security 6.5 — `AuthorizationResult` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationResult.html
- Spring Security 6.5 — `AbstractAccessDecisionManager` (legacy): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/vote/AbstractAccessDecisionManager.html
