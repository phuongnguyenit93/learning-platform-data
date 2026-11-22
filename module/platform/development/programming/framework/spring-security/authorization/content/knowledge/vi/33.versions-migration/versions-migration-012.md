# Chuyển đổi phân quyền theo giai đoạn với ma trận quyền làm chuẩn hồi quy

## 1. Vì sao chuyển đổi phân quyền cần một chuẩn hồi quy?

Khi thay đổi Spring Security — chẳng hạn chuyển từ `authorizeRequests` và `AccessDecisionVoter` sang `authorizeHttpRequests`/`AuthorizationManager`, tách nhiều `SecurityFilterChain`, đổi cách ánh xạ role, hoặc chuyển kiểm tra quyền từ controller vào service — code có thể biên dịch và endpoint vẫn trả 200 nhưng **ý nghĩa quyền truy cập đã thay đổi**. Một lỗi nghiêm trọng là user được cấp thêm quyền ngoài ý định, ngay cả khi mọi unit test hiện có đều xanh.

Giải pháp là tạo **ma trận quyền (permission matrix) được phê duyệt** trước khi migrate. Mỗi hàng mô tả một tình huống thực tế đủ dữ liệu để đánh giá, cùng **kết quả chuẩn (golden expected decision)**. Chúng ta dùng ma trận đó để chạy chính sách cũ, chính sách mới và bài kiểm thử HTTP/method security ở nhiều giai đoạn. Kết quả chính sách cũ là **baseline để so sánh**, không tự động là chân lý: nếu chính sách cũ từng có lỗ hổng, golden phải ghi nhận hành vi đúng do chủ sở hữu nghiệp vụ và bảo mật thống nhất.

Sau bài học, bạn có thể:
- Xây dựng golden matrix bao gồm user/role/authority, tenant, tài nguyên, hành động, trạng thái, tính xác thực và nhánh phủ định.
- Chia chuyển đổi thành các giai đoạn có điều kiện vào/ra, cơ chế so sánh thụ động, canary, rollback và loại bỏ đường cũ.
- Phân biệt **quyền bị thu hẹp**, **quyền được mở rộng** và **khác biệt hợp lệ đã phê duyệt**.
- Tạo regression gate có thể chạy bằng Java 17, sau đó mở rộng sang Spring Security `MockMvc` và method security.
- Tránh sai lệch vì matcher, thứ tự filter chain, `hasRole`/`hasAuthority`, anonymous, CSRF, proxy và dữ liệu tài nguyên.

**Phạm vi:** Spring Security trên Servlet/MVC, tập trung vào chính sách HTTP và method authorization. Với WebFlux, áp dụng cùng phương pháp ma trận/hồi quy nhưng dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và công cụ kiểm thử phù hợp.

## 2. Cố định ngữ nghĩa trước khi cố định implementation

### 2.1. Một hàng của ma trận nên mang những trường nào?

| Trường | Câu hỏi kiểm thử |
| --- | --- |
| `scenarioId` và nguồn phê duyệt | Ai định nghĩa kỳ vọng? Yêu cầu/ADR/chính sách phiên bản nào? |
| Identity / authentication | Anonymous, user đã xác thực, principal nào, issuer/tenant nào? |
| Authority/role | `ROLE_REVIEWER`, `SCOPE_documents.read` hay permission nội bộ nào? |
| Đích / hành động | `GET /documents/{id}`, `POST /documents/{id}/approve`, method `approve`? |
| Ngữ cảnh tài nguyên | Chủ sở hữu, tenant, trạng thái `DRAFT`/`PUBLISHED`, mức độ nhạy cảm |
| Kỳ vọng logic | `PERMIT`, `DENY`; nếu API có abstain/error, phải tách thành trạng thái riêng |
| Kỳ vọng HTTP | 200/201, 401/403 hoặc lỗi có kiểm soát tùy cơ chế xác thực |
| Side effect | Có được ghi DB, phát message, gọi API khác hay không? |
| Độ ưu tiên/rủi ro | Admin, cross-tenant, dữ liệu nhạy cảm, public endpoint |
| Version và hiệu lực | Policy version nào, fixture/snapshot/clock nào tạo ra quyết định? |

**Không lấy mỗi URL và role làm toàn bộ test case.** Quyền theo sở hữu, tenant và trạng thái nghiệp vụ có thể khác nhau cho hai request cùng endpoint. Với endpoint có body/query/path variable hoặc HTTP method khác nhau, thêm chiều tương ứng vào ma trận.

### 2.2. Ma trận minh họa cho hệ thống tài liệu

Giả sử hệ thống có các quy tắc đã được phê duyệt:

1. `PUBLIC_READ` công khai cho mọi người.
2. `PRIVATE_READ` chỉ cho user đã đăng nhập, là owner và cùng tenant với tài liệu.
3. `APPROVE` chỉ cho user đã đăng nhập có role `REVIEWER`, cùng tenant với tài liệu, khi tài liệu còn `DRAFT`.
4. Mọi trường hợp khác bị từ chối. Role của hệ thống không tự tạo quyền cross-tenant.

| ID | Principal / vai trò | Hành động | Tenant người dùng → tài liệu | Ngữ cảnh | Golden |
| --- | --- | --- | --- | --- | --- |
| `P01` | Anonymous | PUBLIC_READ | không áp dụng | Tài liệu công khai | PERMIT |
| `P02` | Anonymous | PRIVATE_READ | — → acme | Owner=false | DENY |
| `P03` | alice / STAFF | PRIVATE_READ | acme → acme | Owner=true | PERMIT |
| `P04` | alice / STAFF | PRIVATE_READ | acme → beta | Owner=true trong fixture | **DENY** |
| `P05` | reviewer / REVIEWER | APPROVE | acme → acme | DRAFT | PERMIT |
| `P06` | reviewer / REVIEWER | APPROVE | acme → beta | DRAFT | **DENY** |
| `P07` | reviewer / REVIEWER | APPROVE | acme → acme | PUBLISHED | DENY |
| `P08` | staff / STAFF | APPROVE | acme → acme | DRAFT | DENY |
| `P09` | bob / STAFF | PRIVATE_READ | acme → acme | Owner=false | DENY |

Hai hàng `P04` và `P06` được cố ý tạo để bắt **lỗ hổng lọt quyền cross-tenant** của một policy cũ chỉ nhìn owner/role mà quên tenant. Đây là trường hợp golden đúng theo chính sách nghiệp vụ được duyệt, mặc dù implementation cũ có thể trả PERMIT.

Ngoài các hàng trên, với hệ thống thật cần thêm route không tồn tại, HTTP method khác, thiếu authority, user disabled, resource deleted, owner thay đổi, annotation ở method khác, request `ERROR/FORWARD`, và việc rơi khỏi mọi security filter chain. Các hàng âm (negative cases) phải đủ nhiều để tìm ra quyền mở rộng ngoài ý định.

### 2.3. Thống nhất ba lớp kỳ vọng

~~~text
Golden business decision (PERMIT / DENY / ERROR / ABSTAIN nếu có)
           │
           ├── policy-level test: AuthorizationManager / domain policy
           │
           ├── method-level test: proxy / @PreAuthorize / method invocation
           │
           └── HTTP-level test: SecurityFilterChain + authentication
                                 + exception translation + controller/side effect
~~~

`DENY` logic có thể thành **401** nếu client chưa xác thực và cơ chế `AuthenticationEntryPoint` đưa ra thử thách đăng nhập, hoặc **403** nếu đã xác thực nhưng thiếu quyền. Không dùng status 401/403 thay thế việc xác minh quyết định logic, và không cố ép status cố định khi đã thay đổi authentication mechanism một cách có chủ đích. `CSRF`, path matcher hoặc gateway cũng có thể tạo 403/404 trước khi policy được gọi.

## 3. Quy trình chuyển đổi theo giai đoạn

| Giai đoạn | Việc cần làm | Điều kiện đi tiếp |
| --- | --- | --- |
| **0. Inventory** | Liệt kê tất cả `SecurityFilterChain`, request matcher, role mapping, method security, custom voter/manager, actuator và entry point | Biết endpoint/method nào chịu chính sách nào; không còn “vùng không rõ” |
| **1. Golden freeze** | Cùng chủ sở hữu nghiệp vụ/bảo mật duyệt ma trận; lưu `policyVersion`, dataset, source và expected | Mọi tình huống critical có positive/negative/cross-tenant; ma trận version-controlled |
| **2. Baseline** | Chạy policy cũ với golden, phân loại lệch đã biết; tạo báo cáo ban đầu | Mọi lệch cũ đã được xử lý hoặc có quyết định khắc phục/waiver có hạn |
| **3. Build candidate** | Viết `AuthorizationManager`/DSL mới; test theo ma trận tại lớp domain, method, HTTP | Candidate đạt golden, không có unexpected PERMIT |
| **4. Shadow compare** | Policy cũ thực thi; policy mới đánh giá **thụ động** trên cùng input/snapshot an toàn | Diff được phân loại; không thực hiện hành vi ghi thứ hai; overhead trong ngân sách |
| **5. Canary** | Bật policy mới cho tập user/tenant/traffic được chọn bằng cơ chế rollout đã duyệt | Không phát sinh unauthorized grant; lỗi/latency/deny anomalies trong ngưỡng |
| **6. Expand** | Tăng dần phạm vi bật candidate, quan sát quyền thực tế và rollback gate | Đạt tiêu chí an toàn trong từng cửa sổ quan sát |
| **7. Retire** | Loại code/policy cũ sau khi có bằng chứng; giữ golden tests, audit, playbook | Không còn đường thực thi cũ hoặc matcher trùng gây mơ hồ |

Không hiểu shadow comparison là “cho cả hai policy điều khiển cùng request”. **Chỉ một policy quyết định việc tiếp tục request**, policy còn lại quan sát. Tuyệt đối không replay POST/approve/transfer để so quyền; test shadow phải gọi hàm quyết định không có side effect và dùng cùng dữ liệu snapshot hoặc phải ghi nhận sai lệch do dữ liệu thay đổi giữa hai lần đánh giá.

### 3.1. Bảo toàn baseline trong từng giai đoạn

Nên lưu cùng một revision:
- Golden permission matrix có ID ổn định, nguồn chấp thuận, kỳ vọng và mức độ rủi ro.
- Mã policy cũ và mới (commit/version), cấu hình flag/route, dữ liệu fixture chuẩn.
- Báo cáo CI: scenario ID, expected, actual legacy, actual candidate, nguyên nhân diff.
- Gate release: số unexpected permit = 0, critical scenario pass 100%, ngưỡng latency/canary và rollback owner.

Với trường hợp cố ý mở thêm quyền, **không cập nhật golden chỉ để test xanh**. Thực hiện change request có phê duyệt, thêm test cho phạm vi quyền mới và giới hạn tác động; giữ dấu vết thay đổi golden giữa version trước/sau.

### 3.2. Phân loại diff

| Legacy | Candidate | Golden | Diễn giải |
| --- | --- | --- | --- |
| PERMIT | DENY | DENY | **Sửa lỗ hổng cũ**, diff hợp lệ nếu đã duyệt |
| DENY | PERMIT | PERMIT | **Mở rộng đúng chính sách**, vẫn cần duyệt vì tăng quyền |
| PERMIT | DENY | PERMIT | Regression làm mất quyền hợp lệ |
| DENY | PERMIT | DENY | **Unexpected privilege expansion**, chặn rollout |
| PERMIT | PERMIT | DENY | Cả hai policy đều sai; diff bằng 0 không có nghĩa an toàn |
| DENY | DENY | PERMIT | Cả hai bỏ quyền hợp lệ; cần sửa trước release |

Vì thế có ít nhất hai cổng kiểm thử độc lập: **candidate-vs-golden** và **old-vs-candidate**. Kết quả diff = 0 chỉ nói hai implementation giống nhau trên những case được thử, không chứng minh chúng đúng hoặc ma trận đủ bao phủ.

## 4. Java 17 chạy độc lập: gate hồi quy từ golden matrix

Để thấy rõ cơ chế mà không phải khởi động Spring Boot, ví dụ sau viết hai policy thuần Java: legacy bỏ kiểm tra tenant, candidate kiểm tra tenant. Tất cả hàng có `expectedPermit` độc lập với code implementation. Khi chạy, chương trình tính số sai lệch và **ném AssertionError nếu candidate vi phạm golden**. Dữ liệu fixture chỉ phục vụ học tập, không phải một hệ phân quyền production.

Tạo file **`PermissionMatrixMigrationDemo.java`**:

~~~java
import java.util.List;

public final class PermissionMatrixMigrationDemo {

    enum Action { PUBLIC_READ, PRIVATE_READ, APPROVE }

    record Scenario(
            String id,
            String principal,
            String role,
            String callerTenant,
            String documentTenant,
            boolean owner,
            boolean draft,
            Action action,
            boolean expectedPermit) {}

    // Mô phỏng chính sách cũ lỗi: thiếu đối chiếu tenant.
    static boolean legacy(Scenario s) {
        if (s.action() == Action.PUBLIC_READ) {
            return true;
        }
        if (s.principal() == null) {
            return false;
        }
        return switch (s.action()) {
            case PUBLIC_READ -> true;
            case PRIVATE_READ -> s.owner();
            case APPROVE -> "REVIEWER".equals(s.role()) && s.draft();
        };
    }

    // Policy mới: giữ quyền hợp lệ, chặn truy cập chéo tenant.
    static boolean candidate(Scenario s) {
        if (s.action() == Action.PUBLIC_READ) {
            return true;
        }
        if (s.principal() == null
                || s.callerTenant() == null
                || !s.callerTenant().equals(s.documentTenant())) {
            return false;
        }
        return switch (s.action()) {
            case PUBLIC_READ -> true;
            case PRIVATE_READ -> s.owner();
            case APPROVE -> "REVIEWER".equals(s.role()) && s.draft();
        };
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Scenario> golden = List.of(
            new Scenario("P01", null, null, null, "acme",
                    false, false, Action.PUBLIC_READ, true),
            new Scenario("P02", null, null, null, "acme",
                    false, false, Action.PRIVATE_READ, false),
            new Scenario("P03", "alice", "STAFF", "acme", "acme",
                    true, false, Action.PRIVATE_READ, true),
            new Scenario("P04", "alice", "STAFF", "acme", "beta",
                    true, false, Action.PRIVATE_READ, false),
            new Scenario("P05", "reviewer", "REVIEWER", "acme", "acme",
                    false, true, Action.APPROVE, true),
            new Scenario("P06", "reviewer", "REVIEWER", "acme", "beta",
                    false, true, Action.APPROVE, false),
            new Scenario("P07", "reviewer", "REVIEWER", "acme", "acme",
                    false, false, Action.APPROVE, false),
            new Scenario("P08", "staff", "STAFF", "acme", "acme",
                    false, true, Action.APPROVE, false),
            new Scenario("P09", "bob", "STAFF", "acme", "acme",
                    false, false, Action.PRIVATE_READ, false)
        );

        int legacyMismatches = 0;
        int candidateMismatches = 0;
        int unexpectedPermits = 0;

        for (Scenario s : golden) {
            boolean oldDecision = legacy(s);
            boolean newDecision = candidate(s);
            if (oldDecision != s.expectedPermit()) {
                legacyMismatches++;
            }
            if (newDecision != s.expectedPermit()) {
                candidateMismatches++;
                System.err.println("GOLDEN MISMATCH: " + s.id());
            }
            if (newDecision && !s.expectedPermit()) {
                unexpectedPermits++;
            }
        }

        System.out.println("Scenarios: " + golden.size());
        System.out.println("Legacy mismatches: " + legacyMismatches);
        System.out.println("Candidate mismatches: " + candidateMismatches);
        System.out.println("Candidate unexpected permits: " + unexpectedPermits);

        require(legacyMismatches == 2,
                "Fixture should expose two legacy tenant bugs");
        require(candidateMismatches == 0,
                "Candidate does not match approved golden matrix");
        require(unexpectedPermits == 0,
                "Unexpected permission expansion");
        System.out.println("Regression gate: PASS");
    }
}
~~~

Chạy trong thư mục có JDK 17+:

~~~bash
javac -encoding UTF-8 PermissionMatrixMigrationDemo.java
java PermissionMatrixMigrationDemo
~~~

**Stdout chính xác**:

~~~text
Scenarios: 9
Legacy mismatches: 2
Candidate mismatches: 0
Candidate unexpected permits: 0
Regression gate: PASS
~~~

Giải thích: legacy sai tại `P04` và `P06` vì cho phép truy cập chéo tenant; candidate giữ hai case đúng quyền và chặn hai lỗ hổng đó. `Legacy mismatches: 2` **không phải** lỗi gate trong fixture này vì chúng là sai lệch cũ đã được phát hiện và ghi nhận. Ở hệ thống thật, chỉ waiver/phương án khắc phục được phê duyệt mới cho phép đi tiếp, không hardcode `2` rồi bỏ qua mọi bug cũ.

Đây là engine logic hai giá trị PERMIT/DENY. Trong Spring Security thực, manager có thể trả `null` (abstain) hoặc ném ngoại lệ. **Không tự ép abstain thành deny/permit và không coi lỗi policy là thiếu quyền**; cần mô hình hóa loại kết quả, fallback và error policy theo phiên bản API/chính sách rồi thêm hàng riêng vào golden matrix.

## 5. Di chuyển vào Spring Security mà vẫn giữ đúng kết quả

### 5.1. Các thay đổi dễ làm biến dạng chính sách

| Chủ đề | Rủi ro khi migrate | Hành động kiểm thử |
| --- | --- | --- |
| `authorizeRequests` → `authorizeHttpRequests` | Chuyển từ `FilterSecurityInterceptor`/voter sang `AuthorizationFilter`/`AuthorizationManager` có thể đổi semantics của custom logic | Golden cho grant/deny/abstain, custom expression và exception |
| `securityMatcher` vs `requestMatchers` | `securityMatcher` giới hạn **toàn chain**; `anyRequest` chỉ áp dụng trong chain đã được chọn | Test chain coverage, route ngoài `/api/**`, catch-all |
| Nhiều `SecurityFilterChain` | Chain đầu tiên khớp được chọn, không gộp mọi chain | Test `@Order` và matcher theo servlet path/method |
| `hasRole` vs `hasAuthority` | `hasRole("ADMIN")` thường tìm authority `ROLE_ADMIN`; `hasAuthority` so chuỗi chính xác | Test role prefix, authority từ JWT, custom `GrantedAuthoritiesMapper` |
| `@EnableMethodSecurity`/proxy | Method có thể bị gọi qua `this.` và bypass proxy; nhiều annotation/advisor có thể chồng nhau | Test service bean qua Spring context, cả trực tiếp trong một class và từ caller khác |
| `@PreAuthorize` vs `@PostAuthorize` | Check trước và sau method khác thời điểm, hậu kiểm không ngăn side effect đã xảy ra | Test kết quả và side effect trước/sau |
| Anonymous / remember-me / session | `authenticated()`, `fullyAuthenticated()` có nghĩa khác | Test anonymous, authenticated, remember-me và session timeout nếu dùng |
| CSRF / HTTP method | POST bị 403 vì thiếu CSRF dù quyền hợp lệ, hoặc GET không đại diện POST | Test phương thức, token CSRF theo kiến trúc client, HTTP response thật |
| `permitAll` vs `web.ignoring` | `ignoring` bỏ qua security filters, có thể thiếu security headers | Test security chain và headers cho route public |
| Default/fallback rules | URL mới hoặc management path rơi ngoài mọi chain, hoặc bị permitAll quá rộng | Test endpoint inventory và `anyRequest().denyAll()` ở fallback hợp lý |

**Điểm dễ nhầm:** nếu một chain dùng `securityMatcher("/api/**")` rồi bên trong gọi `anyRequest().denyAll()`, URL `/admin/report` có thể **không khớp chain đó**. Golden cho route admin phải chạy qua filter chain thực, không chỉ chạy hàm policy nội bộ.

### 5.2. Một cấu hình HTTP tham khảo

Đoạn sau là **trích đoạn cấu hình**; cần bổ sung imports, Spring Boot project, authentication mechanism và controller của ứng dụng. Nó xác thực người dùng ở HTTP, còn quyền tài liệu theo tenant/owner/state được kiểm tra tại service:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Điều này **không tự cấp quyền `APPROVE`** chỉ nhờ `authenticated()`. Một service có thể dùng policy riêng như sau (trích đoạn, cần implementation bean `documentPolicy` và repository kiểm tra tenant/tài nguyên):

~~~java
@PreAuthorize("@documentPolicy.canApprove(authentication, #documentId)")
public void approve(@P("documentId") String documentId) {
    // Update state within a transaction with appropriate integrity checks.
}
~~~

Với `@PreAuthorize`, test phải gọi **bean được Spring quản lý qua proxy** và kiểm tra side effect. Quyền theo tài nguyên có thể thay đổi sau khi tiền kiểm; với thao tác nhạy cảm, cần kiểm tra lại điều kiện trong cùng transaction hoặc conditional database update để tránh TOCTOU.

### 5.3. Golden matrix đi qua HTTP

Một hàng golden “manager của tenant acme không được approve tài liệu tenant beta” có thể biểu diễn trong `MockMvc` của ứng dụng đã cấu hình controller/fixtures:

~~~java
// Fragment trong @SpringBootTest + @AutoConfigureMockMvc;
// DB fixture: document D-42 thuộc tenant beta, principal thuộc acme.
mockMvc.perform(post("/api/documents/D-42/approve")
        .with(user("reviewer").roles("REVIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

Đoạn này **không phải chương trình độc lập**; cần `spring-security-test`, static imports, đúng cấu hình authentication, security context chứa tenant của principal, fixture resource và controller. Nếu app là stateless bearer-token API không dùng browser cookies, CSRF có thể được cấu hình khác theo threat model thực; không tắt CSRF toàn ứng dụng chỉ để test pass.

Các assertion bổ sung bắt buộc:
- Test cấp quyền: trả success và **chỉ một** mutation/side effect nghiệp vụ.
- Test từ chối: response theo policy, **không** mutate DB/gửi message.
- Test route public: không yêu cầu authentication nhưng vẫn đi qua filters phù hợp.
- Test người dùng khác tenant, người dùng bị disable, tài nguyên thay đổi trạng thái và request method khác.
- Test một request không khớp chain nào, nếu phát hiện thì fail coverage gate.

Khi migrate policy thể hiện nhiều kết quả, hãy tách test cho `AuthorizationResult.isGranted()`, `null`/abstain, `AccessDeniedException`, và lỗi service phân quyền; đừng gộp mọi exception thành 403.

## 6. Shadow traffic: đánh giá song song không làm thay đổi hành vi

Đánh giá shadow là kỹ thuật **so sánh quyết định** trên cùng một snapshot dữ liệu, không phải nhân bản HTTP request có side effect.

Ví dụ pseudocode cho một lớp domain policy thuần:

~~~java
// Minh họa kiến trúc; PolicyInput/Decision/metrics thuộc ứng dụng.
Decision enforced = legacyPolicy.evaluate(input);
Decision observed = candidatePolicy.evaluate(input);

if (!observed.equals(enforced)) {
    metrics.recordPolicyDiff(
            policyVersion, input.scenarioClass(), enforced, observed);
}

// Chỉ enforced quyết định việc tiếp tục request khi đang shadow.
return enforced;
~~~

Các điều kiện bắt buộc:
1. Cả hai policy phải có logic đánh giá **không tạo side effect**. Không gọi lại method approve, không phát message, không ghi log PII nhạy cảm.
2. Dùng cùng identity/tenant/resource snapshot; nếu một policy truy vấn DB sau khi dữ liệu đã đổi, báo diff do stale snapshot trước khi kết luận code sai.
3. Ghi diff theo **scenario class, action, policy version và nhóm rủi ro**, không phát token, body, secret hoặc resource ID nhạy cảm vào telemetry.
4. Shadow không thay golden: vẫn cần test expected và review mọi **DENY → PERMIT**.
5. Nếu shadow timeout, định nghĩa timeout/budget, circuit breaker và cách bỏ qua telemetry; không để policy quan sát làm request đang enforce bị treo hoặc mở quyền.
6. Với policy dùng thời gian, random, feature flag hoặc dữ liệu phân tán, cố định clock/seed và context trong test để so sánh có ý nghĩa.

Khi các diff đã giải quyết, mới đưa candidate thành policy enforce cho canary theo tenant/cluster được duyệt, với metrics và công tắc rollback. Phân vùng canary phải ổn định cho một user/request class; nếu không, hai request gần nhau có thể thấy hai chính sách khác nhau, gây hành vi khó giải thích.

## 7. Canary, rollback và điều kiện nghiệm thu

### 7.1. Gate bảo mật và vận hành

| Chỉ tiêu | Ví dụ điều kiện | Hệ quả nếu không đạt |
| --- | --- | --- |
| Critical golden tests | 100% pass | Dừng merge/deploy |
| Candidate unexpected PERMIT | **0** trên golden và canary signals kiểm chứng | Dừng rollout, rollback |
| Privilege cross-tenant | 0 request vượt quyền trong test/e2e | Dừng rollout ngay |
| Unexpected DENY | Không vượt ngưỡng được nghiệp vụ duyệt | Giữ canary, điều tra |
| Authorization error/timeout | Dưới ngưỡng availability/latency đã đặt | Dừng mở rộng, áp fail-safe |
| p95/p99 authorization latency | Trong SLO của API | Tối ưu truy vấn/caching, không bỏ check |
| Coverage | Không route nhạy cảm nào ngoài filter chain/policy | Chặn rollout |
| Audit/telemetry | Đầy đủ policy version và source, không lộ PII | Sửa observability trước khi mở rộng |

**Không đặt “mismatch rate nhỏ hơn 1%” làm điều kiện cho phép cấp thêm quyền**: chỉ một case critical bị cấp sai cũng có thể nghiêm trọng. Metrics từ lưu lượng thật không thay thế golden tests vì không phải mọi trường hợp hiếm/nhạy cảm đều xuất hiện trong canary.

### 7.2. Thiết kế rollback trước khi bật

Rollback phải phục hồi **policy đã biết an toàn** và cấu hình đồng bộ:
- Lưu phiên bản code/rules/mapping trước rollout, đường chuyển flag hoặc redeploy đã thử.
- Ghi lại những quyền mới vừa được chính thức phê duyệt; rollback không được vô tình tái kích hoạt một lỗ hổng legacy đã biết nếu trước đó đã sửa.
- Đặt policy version trong audit để biết request đã được đánh giá bởi phiên bản nào.
- Nếu có migration dữ liệu grant/schema, phải có kế hoạch tương thích ngược hoặc rollback riêng; feature flag chỉ đảo code không khôi phục được dữ liệu.
- Sau rollback, chạy lại golden matrix và canary smoke tests; xác minh trạng thái trên API thực thay vì chỉ nhìn flag.

Nếu policy legacy bị chứng minh có privilege expansion, dùng **safe fallback** đã được duyệt (có thể deny một số thao tác nhạy cảm) khi khẩn cấp, thay vì đảo flag về lỗ hổng. Canary rollout là công cụ kiểm soát tác động, không phải lý do giảm chuẩn bảo mật.

## 8. Kiểm thử tự động hóa từ một nguồn ma trận

Trong project thật, hãy đưa golden matrix vào một nguồn dữ liệu có thể review, ví dụ JSON/YAML với `scenarioId`, `policyVersion`, fixture reference và kỳ vọng. Một biến thể trong CI:

~~~yaml
policyVersion: 17
cases:
  - id: P04
    principal: alice
    role: STAFF
    action: PRIVATE_READ
    callerTenant: acme
    documentTenant: beta
    owner: true
    expected: DENY
  - id: P05
    principal: reviewer
    role: REVIEWER
    action: APPROVE
    callerTenant: acme
    documentTenant: acme
    state: DRAFT
    expected: PERMIT
~~~

Đây là **dữ liệu ví dụ**, không phải schema có sẵn của Spring Security. Khi đọc YAML/JSON, kiểm tra enum/field bắt buộc và fail nếu case thiếu expected; tuyệt đối không default expected về PERMIT. Golden matrix phải có owner phê duyệt và diff review khi chỉnh sửa.

Trong JUnit 5 có thể dùng `@ParameterizedTest` và `@MethodSource` cho từng scenario, đồng thời tạo kiểm thử Spring Boot/MockMvc để xác nhận hiệu lực của config thực. **Không bỏ tầng HTTP**: policy domain có thể đúng nhưng `SecurityFilterChain` matcher hoặc order sai khiến endpoint không được bảo vệ.

Gợi ý chia test trong pipeline:
- **Unit:** evaluate từng case, cả expected deny, error/abstain; nhanh và deterministic.
- **Component:** `AuthorizationManager`, mapper authority, bean Spring AOP và repository ACL trên data fixtures.
- **Integration:** `MockMvc` hoặc test server thực với filter chain, CSRF, authentication entry point, HTTP method, role prefix, tenant.
- **Contract/e2e:** token/IdP mapping, session invalidation, nhiều chain, gateway và dữ liệu đã migrate; cân bằng số lượng vì tốn thời gian.
- **Performance:** benchmark chính sách có DB/cache và shadow overhead; không bỏ query/tenant check chỉ để đạt latency.

Chạy CI tối thiểu với tập critical trước merge, chạy toàn bộ bộ regression trước promote. Kết quả build cần gắn policy version và dữ liệu ma trận, tránh dùng fixture đã đổi âm thầm giữa hai lần so sánh.

## 9. Rủi ro phổ biến khi chuyển đổi và cách nhận biết

1. **Lấy kết quả policy cũ làm golden:** lỗ hổng cũ được hợp thức hóa. Tách baseline legacy và expected nghiệp vụ đã duyệt.
2. **Chỉ so khớp số lượng DENY/PERMIT:** hai case cấp sai có thể bù nhau. So sánh theo `scenarioId` với nguyên nhân diff.
3. **Đổi role prefix:** `hasRole("REVIEWER")` thường cần authority `ROLE_REVIEWER`, trong khi `hasAuthority("REVIEWER")` so chuỗi đúng tên.
4. **Nhầm `securityMatcher` với `requestMatchers`:** `anyRequest` của chain hẹp không bao phủ ứng dụng; test mọi endpoint nhạy cảm.
5. **Bỏ qua method security:** test controller pass nhưng gọi service từ một đường khác có thể bypass check; kiểm tra service qua proxy.
6. **Chạy shadow tạo side effect:** phép so sánh không được thực thi lại yêu cầu nghiệp vụ hoặc cấp quyền hai lần.
7. **Gộp null-abstain và error vào deny:** mất semantics của manager/composer, có thể tạo bypass hoặc chặn sai.
8. **Không phân biệt 401, 403, CSRF:** status khác không nhất thiết do authorization; xác minh tầng đã từ chối.
9. **Chỉ test user hợp lệ:** thiếu anonymous, cross-tenant, disabled, owner khác, tài nguyên không tồn tại, HTTP method khác.
10. **Canary không ổn định:** cùng principal/tài nguyên lúc áp cũ lúc áp mới, khó điều tra và rollback.
11. **Đổi policy và grant/schema cùng lúc:** không xác định nguồn gây diff; tách migration hoặc có version dữ liệu tương thích.
12. **Chỉ theo dõi % diff:** một allow ngoài ý định cho endpoint xuất dữ liệu nhạy cảm vẫn phải chặn rollout.
13. **Không kiểm tra tính toàn vẹn sau rollback:** flag đảo thành công nhưng cache, DB hoặc policy mapping cũ còn lệch.
14. **Xóa golden tests sau khi xong migration:** lần đổi Spring Security tiếp theo có thể tái tạo lỗi cũ.

## 10. Checklist thực hành

- [ ] Inventory đầy đủ endpoint, method, filter chain, role mapping và các custom voter/manager.
- [ ] Golden matrix có owner phê duyệt, version, case ID và nhánh PERMIT/DENY/ABSTAIN/ERROR khi có.
- [ ] Cover anonymous, role, tenant, owner, trạng thái, HTTP method, resource chưa tồn tại và fallback chain.
- [ ] Candidate-vs-golden và legacy-vs-candidate được tính **riêng**, phân loại diff rõ.
- [ ] Không có unexpected PERMIT; các thay đổi mở rộng quyền có yêu cầu phê duyệt.
- [ ] Shadow không làm side effect, có cùng dữ liệu đầu vào và không lộ token/PII.
- [ ] Test Spring-managed proxy, HTTP filter chain, status, CSRF và side effect.
- [ ] Đã xác định canary cohort, SLO/alert, rollback path và phiên bản policy trong audit.
- [ ] Đã chạy lại ma trận sau rollback/promote; loại code cũ sau khi đủ bằng chứng.
- [ ] Ma trận vẫn được giữ như hợp đồng hồi quy cho những lần nâng cấp sau.

## 11. Tài liệu tham khảo

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, `authorizeHttpRequests`, thứ tự matcher, `hasRole`/`hasAuthority`.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, chuyển từ voter/decision manager, contract kết quả.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và proxy.
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): kiểm thử quyền cho Servlet/MVC.
- [JUnit 5 – Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): tạo tập case từ nguồn dữ liệu.

**Thông điệp cần nhớ:** migrate theo giai đoạn chỉ an toàn khi bạn có **định nghĩa quyền đúng, độc lập với code cũ**. Golden matrix quyết định pass/fail; shadow comparison giúp quan sát, canary giới hạn tác động, và rollback bảo vệ khi dữ liệu thực phát sinh vấn đề. Kết quả thành công là *quyền nghiệp vụ vẫn đúng* qua mỗi lần thay đổi phiên bản, không chỉ việc Spring Security khởi động được.
