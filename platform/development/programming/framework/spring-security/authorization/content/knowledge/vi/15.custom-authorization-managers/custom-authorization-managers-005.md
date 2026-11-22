# AuthorizationManagers.allOf, anyOf và ngữ nghĩa khi không có quyết định

> **Phạm vi:** Spring Security – authorization, nhóm **AuthorizationManager tùy chỉnh**. Bài này giải thích cách ghép nhiều `AuthorizationManager` bằng `AuthorizationManagers.allOf(...)`, `anyOf(...)` và đặc biệt là trường hợp delegate **không đưa ra quyết định** (*abstain*). Các ví dụ chính dùng Spring Security 6.5+ (các overload có giá trị mặc định cho all-abstain xuất hiện từ 6.3), Spring Boot Servlet và Java 17+. Quyết định cuối phụ thuộc phiên bản thư viện thực tế, nên kiểm chứng với dependency đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba trạng thái của một `AuthorizationManager`: **GRANT**, **DENY** và **ABSTAIN**; tránh nhầm `null` với `false`.
2. Dự đoán đúng kết quả của `allOf` và `anyOf` khi có nhiều manager, khi tất cả đều abstain và khi danh sách manager rỗng.
3. Sử dụng overload `allOf(AuthorizationDecision, ...)` và `anyOf(AuthorizationDecision, ...)` để chỉ định quyết định dự phòng.
4. Hiểu vì sao một delegate trả `null` có thể dẫn tới **cho phép ngoài ý muốn** trong `allOf`.
5. Thiết kế custom manager có miền áp dụng rõ ràng, trả DENY khi tài nguyên cần kiểm tra nhưng thiếu dữ liệu; chọn chính sách “deny by default”.
6. Viết test cho tích hợp web/request và cho chính logic composition, kể cả đánh giá ngắn mạch (*short-circuit*).

## 2. AuthorizationManager đưa ra quyết định gì?

`AuthorizationManager<T>` đánh giá liệu một chủ thể đã xác thực có được tương tác với đối tượng bảo vệ loại `T` hay không. `T` có thể là `RequestAuthorizationContext` (quy tắc URL Servlet), `MethodInvocation` (quyền trên lời gọi method) hoặc một đối tượng tùy chỉnh.

Phương thức trung tâm trong Spring Security hiện đại:

~~~java
// Chữ ký khái niệm của API hiện đại (Spring Security 6.4+/7.x).
AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T object);
~~~

`AuthorizationResult` có phương thức `isGranted()`. Trong Spring Security 6.5, `authorize(...)` là default method và `check(...)` cũ đã bị đánh dấu deprecated; ở Spring Security 7.x, các mã mới hướng tới `authorize(...)`. Không nên xây thiết kế mới phụ thuộc sâu vào API `check` cũ.

Ba trạng thái khi đánh giá một delegate:

| Trạng thái | Giá trị trả về tiêu biểu | Nghĩa |
| --- | --- | --- |
| **GRANT** | `new AuthorizationDecision(true)` | Delegate đã đánh giá và đồng ý |
| **DENY** | `new AuthorizationDecision(false)` | Delegate đã đánh giá và từ chối |
| **ABSTAIN** | `null` | Delegate **không đưa ra quyết định**, ví dụ quy tắc không áp dụng |

**ABSTAIN không phải DENY.** Delegate nói “tôi không quyết định” khác với “tôi không cho phép”. Một composite manager có quyền áp dụng quyết định mặc định khi mọi delegate đều abstain.

`AuthorizationManager#verify(...)` gọi kiểm tra quyền và ném `AccessDeniedException` khi nhận **kết quả phủ định**. Không nên coi `null` từ một custom manager là một cơ chế từ chối; hãy trả rõ `new AuthorizationDecision(false)` khi cần chặn.

### 2.1. Ví dụ policy có thể abstain

Một hệ thống có hai loại tài nguyên: `/api/orders/**` và `/api/reports/**`. Custom manager cho báo cáo chỉ nhận trách nhiệm ở một số lời gọi. Khi không thuộc miền của nó, một thiết kế có thể trả `null` để cho manager khác quyết định.

~~~java
// Mã trích đoạn: RequestAuthorizationContext là kiểu Servlet.
// Dùng trong Spring Security project; không phải chương trình JDK độc lập.
AuthorizationManager<RequestAuthorizationContext> reportOnly =
        (authentication, context) -> {
            String path = context.getRequest().getRequestURI();
            if (!path.startsWith("/api/reports/")) {
                return null; // ABSTAIN: quy tắc báo cáo không áp dụng
            }

            Authentication current = authentication.get();
            boolean canRead = current != null
                    && current.getAuthorities().stream()
                        .anyMatch(a -> "report:read".equals(a.getAuthority()));
            return new AuthorizationDecision(canRead);
        };
~~~

Quan trọng: quy tắc trả `null` chỉ hợp lý khi thực sự có **delegate hoặc router khác chịu trách nhiệm**. Nếu composite được gắn vào một URL nhạy cảm và tất cả delegate đều bỏ phiếu trắng, có thể xảy ra cho phép ngoài ý muốn.

## 3. allOf: hợp nhất theo AND, nhưng abstain được bỏ qua

Khai báo cơ bản:

~~~java
AuthorizationManager<T> composite =
        AuthorizationManagers.allOf(managerA, managerB, managerC);
~~~

**Ngữ nghĩa thực tế** của overload không có default tùy chỉnh:

1. Duyệt các manager theo thứ tự truyền vào.
2. Nếu một delegate trả **DENY**, kết quả composite là **DENY** ngay; các delegate sau có thể không được gọi.
3. Delegate trả `null` (**ABSTAIN**) bị bỏ qua.
4. Nếu ít nhất một delegate GRANT và không ai DENY, composite **GRANT**.
5. Nếu **tất cả abstain**, composite **GRANT** theo mặc định.
6. Nếu **không truyền manager nào**, `allOf()` cũng **GRANT**.

Kết quả có vẻ giống AND khi chỉ có GRANT/DENY, nhưng **không giống phép AND ba giá trị với abstain là deny**. Đây là chi tiết cần ghi nhớ: `allOf` với tất cả delegate “không biết” **không tự deny**.

### Bảng quyết định allOf mặc định

Ký hiệu: `G` = GRANT, `D` = DENY, `A` = ABSTAIN.

| Kết quả delegate theo thứ tự | `allOf(...)` trả | Lý do |
| --- | --- | --- |
| `[G, G]` | G | Mọi quyết định thực tế đều đồng ý |
| `[G, A]` | G | A bị bỏ qua, còn G |
| `[A, G]` | G | A bị bỏ qua, còn G |
| `[D, A]` | D | Có một DENY |
| `[A, D]` | D | Có một DENY |
| `[G, D]` | D | DENY là điều kiện chặn |
| `[A, A]` | **G** | Tất cả abstain → mặc định của allOf |
| `[]` | **G** | Danh sách rỗng → mặc định của allOf |

**Rủi ro:** giả sử tenant checker, ACL checker và ownership checker đều trả `null` cho loại resource mới chưa được cấu hình. `AuthorizationManagers.allOf(...)` có thể trả **GRANT**. Nếu code chỉ nhìn rằng “đã ghép ba rule bằng AND” mà không test đường abstain, hệ thống có thể bỏ qua rào chắn bảo mật.

## 4. anyOf: hợp nhất theo OR và fallback mặc định là deny

Khai báo:

~~~java
AuthorizationManager<T> composite =
        AuthorizationManagers.anyOf(managerA, managerB, managerC);
~~~

Ngữ nghĩa thực tế:

1. Duyệt các manager theo thứ tự truyền vào.
2. Nếu một delegate **GRANT**, composite **GRANT** ngay; không cần hỏi các delegate sau.
3. Delegate `null` (**ABSTAIN**) bị bỏ qua.
4. Nếu không có GRANT nhưng có ít nhất một **DENY**, composite **DENY**.
5. Nếu **tất cả abstain**, composite **DENY** theo mặc định.
6. Nếu **không có delegate nào**, `anyOf()` **DENY**.

### Bảng quyết định anyOf mặc định

| Kết quả delegate theo thứ tự | `anyOf(...)` trả | Lý do |
| --- | --- | --- |
| `[G, G]` | G | Có một GRANT |
| `[D, G]` | G | Một GRANT thắng theo OR |
| `[G, D]` | G | GRANT ngắn mạch trước D |
| `[G, A]` | G | Có một GRANT |
| `[A, G]` | G | Có một GRANT |
| `[D, A]` | D | A bỏ qua, còn D |
| `[A, D]` | D | A bỏ qua, còn D |
| `[D, D]` | D | Không ai GRANT |
| `[A, A]` | **D** | Tất cả abstain → mặc định của anyOf |
| `[]` | **D** | Danh sách rỗng → mặc định của anyOf |

**Không diễn giải Javadoc “granted or abstained” thành “chỉ cần một abstain thì được phép”.** Trong cách cài đặt, `null` bị bỏ qua; trường hợp hoàn toàn không có kết quả rõ ràng dùng fallback. Với `anyOf(DENY, ABSTAIN)`, kết quả là DENY.

### 4.1. So sánh song song

| Danh sách delegate | allOf mặc định | anyOf mặc định |
| --- | --- | --- |
| `[G, G]` | GRANT | GRANT |
| `[G, D]` | DENY | GRANT |
| `[G, A]` | GRANT | GRANT |
| `[D, A]` | DENY | DENY |
| `[A, A]` | **GRANT** | **DENY** |
| `[]` | **GRANT** | **DENY** |

Cùng một danh sách **toàn abstain** có thể cho hai kết quả khác nhau. Đây là tính năng của cách tổng hợp, không phải lỗi của Spring Security.

## 5. Đặt quyết định mặc định khi tất cả abstain

Từ Spring Security **6.3**, có overload:

~~~java
AuthorizationManagers.allOf(
        new AuthorizationDecision(false), managerA, managerB);

AuthorizationManagers.anyOf(
        new AuthorizationDecision(false), managerA, managerB);
~~~

Tham số đầu tiên là `allAbstainDefaultDecision`: **chỉ dùng khi không có delegate nào trả một quyết định rõ ràng** (bao gồm cả danh sách rỗng). Đây là lựa chọn rất phù hợp cho chính sách nhạy cảm cần **fail closed** khi không có manager nào nhận trách nhiệm.

| Cấu hình | Khi tất cả delegate A | Khi danh sách rỗng |
| --- | --- | --- |
| `allOf(managers...)` | GRANT | GRANT |
| `anyOf(managers...)` | DENY | DENY |
| `allOf(new AuthorizationDecision(false), managers...)` | **DENY** | **DENY** |
| `anyOf(new AuthorizationDecision(false), managers...)` | **DENY** | **DENY** |
| `allOf(new AuthorizationDecision(true), managers...)` | GRANT | GRANT |
| `anyOf(new AuthorizationDecision(true), managers...)` | GRANT | GRANT |

### 5.1. Fallback không có nghĩa mọi abstain trở thành DENY

Hãy phân biệt hai ví dụ:

~~~java
// A là một manager luôn abstain.
// G là một manager trả GRANT.
AuthorizationManagers.allOf(new AuthorizationDecision(false), A, A);
// → DENY: tất cả abstain, dùng fallback

AuthorizationManagers.allOf(new AuthorizationDecision(false), G, A);
// → GRANT: đã có một GRANT, A bị bỏ qua; fallback KHÔNG chạy
~~~

**Đây là ngộ nhận nguy hiểm nhất:** `allOf(DENY_DEFAULT, permissionManager, tenantManager)` **không bắt buộc** `tenantManager` trả GRANT. Nếu `permissionManager` trả GRANT còn `tenantManager` trả `null`, composite vẫn GRANT.

Vì thế, nếu **mỗi điều kiện đều bắt buộc**, custom manager của điều kiện đó phải đưa ra quyết định rõ ràng cho mọi lời gọi nằm trong phạm vi bảo vệ. Thiếu tenant, thiếu bản ghi ACL, không parse được ID, policy service mất kết nối... phải có chính sách rõ (thường DENY hoặc error có xử lý bảo mật) chứ không âm thầm ABSTAIN.

### 5.2. Khi nào dùng default GRANT?

Overload cho phép truyền `new AuthorizationDecision(true)`. Chỉ sử dụng khi *chủ đích nghiệp vụ* xác định không có manager nào áp dụng thì được phép (ví dụ vùng public đã được phân loại tường minh). Không nên để fallback GRANT cho các tài nguyên chưa được định tuyến hoặc một hệ thống policy đang thiếu cấu hình.

## 6. Short-circuit: không phải mọi manager đều được gọi

Một composite manager có thể dừng ngay khi gặp quyết định đủ để kết luận:

~~~text
allOf(G, G, D, expensivePolicy)
     G  G  D  không gọi expensivePolicy
             -> DENY

anyOf(D, A, G, expensivePolicy)
     D  A  G  không gọi expensivePolicy
             -> GRANT
~~~

Điều này có các hệ quả:

- Đặt check **rẻ, dứt khoát** ở trước có thể giảm độ trễ.
- Không đặt side effect bắt buộc (ví dụ audit “phải chạy mọi lần”) vào một delegate và mặc định nó sẽ được gọi.
- Khi log/debug, không suy luận manager không xuất hiện trong log là đã GRANT hay DENY: có thể nó **chưa được đánh giá**.
- Nếu custom policy gọi dịch vụ ngoài, xác định cách xử lý lỗi mạng/timeout; không tự động biến **lỗi hạ tầng** thành ABSTAIN rồi vô tình grant qua `allOf`.
- Với anyOf, quyền của một nhánh GRANT có thể cho phép dù nhánh khác DENY. Điều đó đúng cho OR nhưng **không phù hợp** với điều kiện “bị khóa tài khoản thì luôn từ chối”. Với quy tắc deny bắt buộc, dùng `allOf(requiredAccountActive, anyOf(roleA, roleB))`.

### Ví dụ: điều kiện bắt buộc và lựa chọn thay thế

Yêu cầu: người dùng **phải đang hoạt động** và **phải có** quyền `invoice:read` **hoặc** `invoice:audit`.

~~~java
// Mã trích đoạn có tính minh họa trong ứng dụng Spring Security.
// T = RequestAuthorizationContext hoặc MethodInvocation tùy nơi sử dụng.
AuthorizationManager<T> policy = AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        activeAccountManager,
        AuthorizationManagers.anyOf(
                new AuthorizationDecision(false),
                invoiceReadManager,
                invoiceAuditManager));
~~~

`activeAccountManager` cần trả DENY cho tài khoản khóa, và không dùng ABSTAIN cho một tài khoản mà nó có trách nhiệm kiểm tra. Các manager còn lại cũng phải có phạm vi rõ. Không dùng `anyOf(activeAccount, hasAuthority)` nếu tài khoản bị khóa cần veto tất cả quyền khác.

## 7. Chương trình Java 17 độc lập để nhìn rõ bảng quyết định

Chương trình sau **mô phỏng đúng thuật toán kết hợp trên ba trạng thái**, không tự nhận là mã nguồn Spring Security và không yêu cầu thư viện Spring. Mục đích là cho người học tự chạy, thay thứ tự các kết quả và hiểu fallback.

Lưu thành `CompositionTruthTableDemo.java`:

~~~java
public class CompositionTruthTableDemo {
    enum Vote { GRANT, DENY, ABSTAIN }

    static Vote allOf(Vote onAllAbstain, Vote... votes) {
        boolean anyGrant = false;
        for (Vote vote : votes) {
            if (vote == Vote.DENY) {
                return Vote.DENY;
            }
            if (vote == Vote.GRANT) {
                anyGrant = true;
            }
        }
        return anyGrant ? Vote.GRANT : onAllAbstain;
    }

    static Vote anyOf(Vote onAllAbstain, Vote... votes) {
        boolean anyDeny = false;
        for (Vote vote : votes) {
            if (vote == Vote.GRANT) {
                return Vote.GRANT;
            }
            if (vote == Vote.DENY) {
                anyDeny = true;
            }
        }
        return anyDeny ? Vote.DENY : onAllAbstain;
    }

    public static void main(String[] args) {
        System.out.println("allOf(G,A)=" +
                allOf(Vote.GRANT, Vote.GRANT, Vote.ABSTAIN));
        System.out.println("allOf(A,A)=" +
                allOf(Vote.GRANT, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("allOf(A,A) fallback DENY=" +
                allOf(Vote.DENY, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("anyOf(D,A)=" +
                anyOf(Vote.DENY, Vote.DENY, Vote.ABSTAIN));
        System.out.println("anyOf(A,A)=" +
                anyOf(Vote.DENY, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("anyOf(A,A) fallback GRANT=" +
                anyOf(Vote.GRANT, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("allOf()=" + allOf(Vote.GRANT));
        System.out.println("anyOf()=" + anyOf(Vote.DENY));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CompositionTruthTableDemo.java
java CompositionTruthTableDemo
~~~

**stdout chính xác:**

~~~text
allOf(G,A)=GRANT
allOf(A,A)=GRANT
allOf(A,A) fallback DENY=DENY
anyOf(D,A)=DENY
anyOf(A,A)=DENY
anyOf(A,A) fallback GRANT=GRANT
allOf()=GRANT
anyOf()=DENY
~~~

Hãy thử thay `Vote.ABSTAIN` bằng `Vote.DENY` trong `allOf(G,A)`: khi có một DENY, kết quả trở thành DENY bất kể fallback. Thay bằng `Vote.GRANT` trong `anyOf(D,A)`: có một GRANT, kết quả trở thành GRANT.

**Ranh giới mô phỏng:** Trong Spring Security thật, mỗi delegate trả `AuthorizationResult` hoặc `null`. Kết quả composite có thể là một loại decision có metadata; logic mô phỏng chỉ quan tâm `isGranted()`, không mô phỏng exception, AOP hay filter chain.

## 8. Ví dụ gọi trực tiếp AuthorizationManagers trong ứng dụng Spring Security

Đoạn này chạy **trong một dự án đã có spring-security-core 6.5+** (có thể thuộc Spring Boot Starter Security). Khác ví dụ JDK ở trên, code gọi chính factory của Spring Security, không tự viết thuật toán.

Tạo `src/main/java/demo/composition/CompositionManagerDemo.java`:

~~~java
package demo.composition;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;

public class CompositionManagerDemo {
    static final AuthorizationManager<String> GRANT =
            (authentication, object) -> new AuthorizationDecision(true);

    static final AuthorizationManager<String> DENY =
            (authentication, object) -> new AuthorizationDecision(false);

    static final AuthorizationManager<String> ABSTAIN =
            (authentication, object) -> null;

    static String result(AuthorizationManager<String> manager) {
        AuthorizationResult decision = manager.authorize(() -> null, "resource");
        return decision == null ? "ABSTAIN"
                : decision.isGranted() ? "GRANT" : "DENY";
    }

    public static void main(String[] args) {
        System.out.println("allOf G,A: " +
                result(AuthorizationManagers.allOf(GRANT, ABSTAIN)));
        System.out.println("allOf A,A: " +
                result(AuthorizationManagers.allOf(ABSTAIN, ABSTAIN)));
        System.out.println("allOf A,A deny fallback: " +
                result(AuthorizationManagers.allOf(
                        new AuthorizationDecision(false), ABSTAIN, ABSTAIN)));
        System.out.println("anyOf D,A: " +
                result(AuthorizationManagers.anyOf(DENY, ABSTAIN)));
        System.out.println("anyOf A,A: " +
                result(AuthorizationManagers.anyOf(ABSTAIN, ABSTAIN)));
        System.out.println("anyOf A,A grant fallback: " +
                result(AuthorizationManagers.anyOf(
                        new AuthorizationDecision(true), ABSTAIN, ABSTAIN)));
        System.out.println("not(A): " +
                result(AuthorizationManagers.not(ABSTAIN)));
    }
}
~~~

**Kết quả khi chạy trong runtime Spring Security 6.5+/7.x tương thích:**

~~~text
allOf G,A: GRANT
allOf A,A: GRANT
allOf A,A deny fallback: DENY
anyOf D,A: DENY
anyOf A,A: DENY
anyOf A,A grant fallback: GRANT
not(A): ABSTAIN
~~~

Có thể chạy main class bằng cơ chế classpath của dự án, chẳng hạn IDE hoặc Gradle `JavaExec` task đã cấu hình. **Không thể biên dịch riêng file này bằng `javac CompositionManagerDemo.java` mà không có JAR Spring Security trên classpath.**

Vì sao dùng `() -> null` cho `Supplier<Authentication>` trong demo? Ba delegate `GRANT`, `DENY` và `ABSTAIN` cố ý **không đọc Authentication** để cô lập logic kết hợp. Ứng dụng thật phải nhận `Authentication` do framework xác thực cung cấp và xử lý null/anonymous phù hợp. Không sao chép supplier null này vào policy production.

### 8.1. Lưu ý tương thích 6.5 và 7.x

- `AuthorizationManagers.allOf`/`anyOf` tồn tại từ Spring Security 5.8; **overload nhận `AuthorizationDecision` đầu tiên có từ 6.3**.
- `AuthorizationManager#authorize(...)` có từ 6.4; với 6.5 interface vẫn còn `check(...)` deprecated. Các lambda trong ví dụ trả `AuthorizationDecision`, loại phù hợp cho cả các target signature hiện đại; Spring Security 7.x hướng tới `authorize(...)`.
- Khi chuyển ứng dụng từ 5.8 hoặc 6.2 sang 6.3+, kiểm tra phiên bản trước khi sao chép overload có tham số fallback.
- Khi nâng Spring Security, kiểm thử contract authorization thực tế thay vì chỉ biên dịch thành công: **abstain và empty-manager** có hệ quả an ninh rõ ràng.

## 9. Ví dụ Servlet thực tế: quyền đọc và quyền tenant đều bắt buộc

Yêu cầu endpoint: `GET /api/invoices` chỉ được truy cập khi:

1. Người gọi có authority `invoice:read`.
2. Tenant do client yêu cầu **thực sự là tenant được gán cho principal**.

Điều kiện (2) không được abstain khi thiếu tenant. Truyền tenant qua header chỉ là **selector không tin cậy**; manager so với dữ liệu gắn với principal ở phía server. Trong ví dụ, bản đồ actor→tenant đặt cố định để dễ học; hệ thống thực phải tra nguồn danh tính/ACL đáng tin, không tin header để cấp quyền.

Tạo `src/main/java/demo/authorization/CompositeAuthorizationApplication.java` trong dự án Spring Boot Servlet:

~~~java
package demo.authorization;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CompositeAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompositeAuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthorizationManager<RequestAuthorizationContext> canRead =
                AuthorityAuthorizationManager.hasAuthority("invoice:read");

        // Đây là dữ liệu phía server trong demo, không lấy từ client.
        Map<String, String> assignedTenant = Map.of(
                "alice", "tenant-a",
                "bob", "tenant-b");

        AuthorizationManager<RequestAuthorizationContext> sameTenant =
                (authentication, context) -> {
                    Authentication current = authentication.get();
                    String tenantFromRequest =
                            context.getRequest().getHeader("X-Tenant");
                    String tenantForActor = current == null
                            ? null
                            : assignedTenant.get(current.getName());

                    boolean allowed = tenantForActor != null
                            && tenantForActor.equals(tenantFromRequest);
                    // Không có tenant/không map được => DENY tường minh.
                    return new AuthorizationDecision(allowed);
                };

        AuthorizationManager<RequestAuthorizationContext> policy =
                AuthorizationManagers.allOf(
                        new AuthorizationDecision(false),
                        canRead,
                        sameTenant);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/invoices")
                            .access(policy)
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("invoice:read").build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("invoice:read").build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read").build());
    }
}

@RestController
class InvoiceController {
    private final Map<String, List<String>> invoices = Map.of(
            "tenant-a", List.of("INV-A-1", "INV-A-2"),
            "tenant-b", List.of("INV-B-1"));

    @GetMapping("/api/invoices")
    List<String> list(@RequestHeader("X-Tenant") String tenant) {
        // Policy đã xác minh selector tenant trước khi tới controller.
        return invoices.getOrDefault(tenant, List.of());
    }
}
~~~

**Dependencies** trong một ứng dụng đã bật Spring Boot Gradle plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Khối này là một phần `build.gradle` của dự án đã có, không phải file Gradle hoàn chỉnh. Password `{noop}` là **chỉ cho demo**; ứng dụng production phải dùng password encoder an toàn. Ứng dụng có thể chạy bằng `./gradlew bootRun` (Unix) hoặc `gradlew.bat bootRun` (Windows) với wrapper và dependency Spring Boot thích hợp.

Nếu app đang chạy ở `localhost:8080`, có thể thử:

~~~bash
curl -i -u alice:demo -H "X-Tenant: tenant-a" http://localhost:8080/api/invoices
curl -i -u alice:demo -H "X-Tenant: tenant-b" http://localhost:8080/api/invoices
curl -i -u viewer:demo -H "X-Tenant: tenant-a" http://localhost:8080/api/invoices
curl -i -u bob:demo -H "X-Tenant: tenant-b" http://localhost:8080/api/invoices
~~~

| Người gọi | Authority | Header tenant | Kết quả |
| --- | --- | --- | --- |
| Alice | `invoice:read` | `tenant-a` | 200, chỉ danh sách tenant-a |
| Alice | `invoice:read` | `tenant-b` | 403 do sameTenant DENY |
| Viewer | Chỉ `profile:read` | `tenant-a` | 403 do canRead DENY |
| Bob | `invoice:read` | `tenant-b` | 200, chỉ danh sách tenant-b |
| Alice | `invoice:read` | Không có `X-Tenant` | 403 do sameTenant DENY |
| Chưa xác thực | Không có principal đã xác thực | `tenant-a` | Thường 401 với HTTP Basic |

Lưu ý: `allOf` dừng ở DENY đầu tiên, nên nếu Viewer thiếu `invoice:read` thì `sameTenant` có thể không được gọi. Đây không phải lỗi test; đó là thiết kế short-circuit.

### 9.1. Vì sao sameTenant trả DENY thay vì ABSTAIN?

Giả sử viết sai:

~~~java
// Phản ví dụ: tenant thiếu thì ABSTAIN.
if (tenantFromRequest == null) {
    return null;
}
~~~

Với Alice có `invoice:read`, `canRead` đã GRANT. `sameTenant` abstain, còn `allOf(new AuthorizationDecision(false), canRead, sameTenant)` vẫn **GRANT**. Fallback DENY **không cứu được** vì không phải tất cả delegate abstain. Sau đó controller gặp header bắt buộc bị thiếu thì có thể trả 400, nhưng trên một controller khác thiếu guard, có thể mở ra dữ liệu ngoài ý muốn.

Cách sửa: rule bắt buộc trong phạm vi endpoint phải trả `new AuthorizationDecision(false)` khi không thể xác minh tenant; controller, repository và business layer cũng cần bảo đảm giới hạn dữ liệu. Tránh nhầm “không đủ thông tin” với “không áp dụng rule”.

### 9.2. Dùng manager trong DSL không đồng nghĩa tự bảo vệ mọi caller

`SecurityFilterChain` và `RequestAuthorizationContext` chỉ áp dụng cho request đi qua Servlet filter chain. Một background job gọi repository/service sẽ không tự chạy URL authorization. Với dữ liệu cần bảo vệ tại mọi đường gọi, đặt policy ACL/tenant ở service/data layer, có thể gắn method security hoặc interceptor dùng `AuthorizationManager<MethodInvocation>` được cấu hình đúng. Một biến manager tự tạo trong bean **không tự biến thành annotation**.

## 10. Kiểm thử Spring Boot qua MockMvc

Tạo `src/test/java/demo/authorization/CompositeAuthorizationApplicationTest.java` (cùng package như ứng dụng):

~~~java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CompositeAuthorizationApplicationTest {
    @Autowired MockMvc mvc;

    @Test
    void aliceCanReadAssignedTenant() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo"))
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0]").value("INV-A-1"));
    }

    @Test
    void aliceCannotReadAnotherTenant() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo"))
                    .header("X-Tenant", "tenant-b"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingRequiredAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("viewer", "demo"))
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingTenantIsDeniedByPolicy() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/invoices")
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy test bằng Gradle wrapper dự án. Kỳ vọng 401/403 ở đây dựa trên cấu hình HTTP Basic, filter chain và exception handling trong demo. Các dự án có custom authentication entry point/handler có thể dùng mã khác. Đây là **integration test**, không thay thế unit test của thuật toán composition.

### 10.1. Unit test cần thêm cho custom manager

Bên cạnh MockMvc, viết test trực tiếp `manager.authorize(authenticationSupplier, context)` để kiểm chứng:
- Trả GRANT khi policy xác minh được tất cả điều kiện.
- Trả DENY khi không xác minh được tenant, ACL, owner hoặc dữ liệu cần thiết.
- Chỉ ABSTAIN khi đối tượng nằm ngoài miền áp dụng **và** có định tuyến chịu trách nhiệm phù hợp.
- Nếu một delegate ném exception, kết quả không bị đổi ngầm thành ABSTAIN.
- Gọi delegate có side effect/log xem chúng có bị bỏ qua do short-circuit không.

Lớp kiểm thử bảng quyết định nên có riêng hai ca **tất cả abstain** và **manager list rỗng**. Chỉ kiểm tra GRANT/DENY mà quên `null` là bỏ sót cốt lõi của bài này.

## 11. Khi kết hợp manager ở method security

`AuthorizationManager<T>` là generic; các factory `allOf`/`anyOf` không chỉ dành cho URL. Với method security, đối tượng bảo vệ thường là `MethodInvocation`; có thể tạo:

~~~java
// Trích đoạn type-level: chỉ tạo manager, chưa đăng ký AOP interceptor.
AuthorizationManager<MethodInvocation> securedMethod =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                methodAuthorityManager,
                methodOwnershipManager);
~~~

Để chạy tự động, cần tích hợp manager vào cơ chế interception thích hợp, chẳng hạn `AuthorizationManagerBeforeMethodInterceptor` hoặc chính sách method security hiện có. Đừng giả định cấu hình `.access(policy)` cho URL sẽ áp dụng khi service được gọi từ queue/scheduled job.

Trong method security, `@PreAuthorize("hasAuthority('invoice:read')")` diễn đạt một điều kiện quyền khác với việc viết `AuthorizationManagers.allOf(...)`. Khi cần logic tùy biến phức tạp và reusable, manager có thể có lợi; khi quy tắc đơn giản, annotation/DSL thường dễ đọc. Dù ở đâu, nếu check bắt buộc không thể đánh giá được thì đừng ABSTAIN rồi hy vọng composite tự từ chối.

**Phân biệt không có quyết định với không có Authentication:** `authentication.get() == null` hoặc một principal anonymous không tự cho bạn kết quả ABSTAIN. Nếu rule yêu cầu người dùng xác thực và không có identity đáng tin, nên DENY hoặc để tầng authentication xử lý theo hợp đồng; không phát một phiếu “tôi không có ý kiến” vào `allOf`.

## 12. not(...) và các trường hợp ngoài GRANT/DENY

`AuthorizationManagers.not(manager)` đảo quyết định đã xác định:

| Delegate | `not(delegate)` |
| --- | --- |
| GRANT | DENY |
| DENY | GRANT |
| ABSTAIN | **ABSTAIN** |

Vì vậy `not(abstainingManager)` vẫn **không có quyết định**. Kết quả cuối nếu đặt `not(...)` trong một `allOf`/`anyOf` vẫn phụ thuộc vào cách composite xử lý tình huống all-abstain.

Không xem exception là trạng thái thứ tư tương đương ABSTAIN. Delegate có thể ném lỗi khi policy provider không khả dụng; đó là một đường thất bại cần chiến lược an toàn và observability. Không tự bắt tất cả exception rồi trả `null` trừ khi thực sự muốn tuyên bố “không có quyết định” và đã đảm bảo fallback không tạo privilege escalation.

### 12.1. Ví dụ về sai lầm khi xử lý lỗi

~~~java
// Phản ví dụ: lỗi hạ tầng bị nuốt thành ABSTAIN.
AuthorizationManager<RequestAuthorizationContext> externalAcl =
        (authentication, context) -> {
            try {
                return new AuthorizationDecision(
                        remoteAclService.isAllowed(authentication.get(),
                                context.getRequest()));
            } catch (Exception ignored) {
                return null; // NGUY HIỂM trong allOf
            }
        };
~~~

Đoạn trích minh họa phụ thuộc `remoteAclService` của ứng dụng, **không phải file hoàn chỉnh**. Nếu một authority checker khác GRANT, `allOf` có thể GRANT dù ACL service thất bại. Cần phân biệt lỗi “không áp dụng”, lỗi “không có hồ sơ ACL” và lỗi “hạ tầng không truy cập được”. Chọn một hợp đồng fail closed, có log/correlation và chính sách retry/breaker phù hợp, không làm phát sinh allow ngoài ý muốn.

## 13. Cách thiết kế policy có cấu trúc

Một nguyên tắc hữu ích là chia predicate thành hai nhóm:

- **Điều kiện bắt buộc (must):** tài khoản active, cùng tenant, đúng owner, không bị khóa, quyền sử dụng tính năng. Thiết kế để mọi request trong phạm vi đều được trả GRANT hoặc DENY. Ghép bằng `allOf`.
- **Lựa chọn thay thế (may satisfy by one):** có `invoice:read` **hoặc** `invoice:audit`, thuộc nhóm approver A **hoặc** có delegation hợp lệ. Ghép bằng `anyOf`.

Ví dụ cấu trúc:

~~~text
allOf(
  accountActive,                      // bắt buộc
  sameTenant,                         // bắt buộc
  anyOf(invoiceRead, invoiceAudit)    // một trong hai quyền
)
~~~

Trong ứng dụng thật, phần accountActive và sameTenant không được abstain cho một request thuộc phạm vi quản lý của chúng. Nếu có danh sách policy tải động từ cấu hình, kiểm tra **danh sách rỗng** ngay khi startup; với `allOf()` rỗng, kết quả mặc định GRANT. Nếu cấu hình thiếu, fail startup hoặc deny mặc định tốt hơn âm thầm cho phép.

### 13.1. Tránh mã hóa policy bằng “không có kết quả = đồng ý”

Hãy đặt tên rõ:
- `isTenantAllowed` trả boolean quyết định tường minh.
- `isApplicableToRequest` xác định phạm vi nếu cần router.
- `authorize(...)` chỉ trả `null` khi manager thực sự không chịu trách nhiệm.

Nên tách **chọn policy áp dụng** khỏi **quyết định quyền**. Một router request matcher chọn manager cụ thể, manager đó thường phải đưa ra quyết định xác định. Không dựa vào việc ba manager nào cũng có thể abstain trên một request nhạy cảm.

### 13.2. Theo dõi reason và metadata

`AuthorizationDecision` chỉ mang granted boolean; các loại `AuthorizationResult` hoặc implementation của ứng dụng có thể mang thêm chi tiết. Khi composite đánh giá, một số delegate có thể bị bỏ qua do short-circuit. Nếu cần audit giải thích “ai đã từ chối vì điều gì”, thiết kế logging/decision trace không tiết lộ PII, token và quyền nội bộ cho client. Không trông chờ rằng mọi delegate luôn ghi được audit entry.

## 14. Các lỗi thực tế cần tránh

### Lỗi 1: “AND với toàn abstain sẽ DENY”

Sai với `AuthorizationManagers.allOf(managers...)` mặc định: toàn abstain **GRANT**. Viết test all-abstain, empty-list và cân nhắc overload fallback DENY.

### Lỗi 2: “Đã truyền default DENY thì từng manager phải GRANT”

Sai: default chỉ dùng **nếu tất cả** abstain. `allOf(DENY_DEFAULT, GRANT, ABSTAIN)` trả GRANT. Với điều kiện bắt buộc, trả DENY tường minh khi thiếu dữ liệu.

### Lỗi 3: “ABSTAIN chính là false”

Sai: `null` khác `AuthorizationDecision(false)`. Khi bất kỳ nhánh nào DENY trong `allOf`, composite bị chặn; khi một nhánh ABSTAIN, nhánh đó bị bỏ qua.

### Lỗi 4: “anyOf(DENY, ABSTAIN) sẽ GRANT vì một nhánh abstain”

Sai: không có GRANT, còn một DENY, nên composite DENY. `anyOf` không coi riêng một ABSTAIN là vé cho phép.

### Lỗi 5: “Không có manager nào nghĩa là không có quyền”

`anyOf()` rỗng đúng là DENY, nhưng `allOf()` rỗng lại GRANT. Đừng xây policy từ danh sách động mà không validate số lượng/loại manager.

### Lỗi 6: “Có manager yêu cầu tài khoản active, OR vẫn đủ”

`anyOf(activeAccount, hasAuthority)` cho phép nếu một trong hai GRANT, kể cả manager còn lại DENY. Nếu account active là điều kiện bắt buộc, đặt nó bên ngoài OR và dùng AND.

### Lỗi 7: “Manager nào cũng phải chạy để ghi log”

Composites dùng short-circuit. Đừng đặt side effect bắt buộc trong hàm authorization. Logging/auditing trung tâm nên gắn với quyết định cuối và các policy thực sự được gọi.

### Lỗi 8: “Missing tenant là không áp dụng quy tắc tenant”

Nếu route đang truy cập dữ liệu theo tenant thì tenant check là bắt buộc. Trả null do thiếu header/ID có thể làm quyền bị nới rộng. Trả DENY khi không xác minh được phạm vi, validate payload riêng nếu cần.

### Lỗi 9: “Lỗi mạng đến policy engine có thể mặc định abstain”

Không nên. Hãy chọn fail closed hoặc xử lý lỗi tường minh theo threat model. Nuốt timeout thành `null` dễ biến allOf thành cho phép khi rule khác GRANT.

### Lỗi 10: “Kết quả của composite đồng nghĩa HTTP response”

Composite chỉ quyết định quyền; mapping 401/403/404 phụ thuộc filter chain, authentication entry point, exception translation và policy API. Với method security không qua HTTP, có thể chỉ có exception ở service.

### Lỗi 11: “Đọc kết quả từ một version rồi áp cho mọi version”

Overload fallback được thêm từ 6.3; API `authorize` từ 6.4. Kiểm tra dependency runtime, Javadoc tương ứng, rồi khóa hành vi bằng test.

## 15. Ma trận QA nên có trước khi phát hành

| Case | allOf mặc định | anyOf mặc định | Kỳ vọng cần test |
| --- | --- | --- | --- |
| Tất cả GRANT | GRANT | GRANT | đường thành công |
| Có một DENY, còn lại GRANT | DENY | GRANT | ngữ nghĩa AND/OR |
| Có một DENY, còn lại ABSTAIN | DENY | DENY | abstain không phủ quyết/không mở khóa |
| Có một GRANT, còn lại ABSTAIN | GRANT | GRANT | abstain bị bỏ qua |
| Tất cả ABSTAIN | **GRANT** | **DENY** | fallback mặc định |
| Zero managers | **GRANT** | **DENY** | policy config rỗng |
| Default DENY + tất cả ABSTAIN | DENY | DENY | overload từ 6.3 |
| Default DENY + một GRANT và các ABSTAIN | GRANT | GRANT | fallback không can thiệp |
| Delegate ném exception | Không có kết quả thành công bình thường | Không có kết quả thành công bình thường | fail closed/exception handling |
| Thứ tự G,D so với D,G | Chỉ manager trước kết quả chặn chạy | Chỉ manager trước kết quả chặn chạy | short-circuit |
| Thiếu tenant/owner/ACL bắt buộc | DENY do manager có trách nhiệm | Phụ thuộc cấu trúc OR | không lộ dữ liệu |
| Danh sách manager lấy từ cấu hình trống | Startup fail hoặc explicit DENY | Explicit DENY | kiểm tra config |

Không dùng bảng này làm lý do cho phép mọi quyết định rỗng. Mỗi endpoint/tính năng cần xác định chính sách **fail closed** khi rule không áp dụng, data thiếu hoặc config bị lỗi.

## 16. Bài tập áp dụng

**Tình huống 1:** Một ứng dụng ghép `allOf(hasReadPermission, optionalAclCheck)`. Alice có `report:read`. `optionalAclCheck` trả `null` vì thiếu bảng ACL. Alice có được xem báo cáo không?

**Đáp án:** Với `allOf` mặc định, có: hasReadPermission GRANT, ACL ABSTAIN, kết quả GRANT. Nếu ACL là rào chắn **bắt buộc**, thiết kế này không an toàn; ACL checker phải trả DENY khi không xác minh được quyền, hoặc policy phải được tái cấu trúc.

**Tình huống 2:** Chuyển sang `allOf(new AuthorizationDecision(false), hasReadPermission, optionalAclCheck)` có khắc phục tình huống 1 không?

**Đáp án:** **Không.** Một delegate vẫn GRANT nên fallback “all abstain” không được dùng. Chỉ khi **mọi** delegate abstain mới áp dụng DENY fallback.

**Tình huống 3:** `anyOf(managerA, managerB)` với `A=DENY` và `B=ABSTAIN` có cho phép không?

**Đáp án:** Không. Không có GRANT, đã có DENY, nên trả DENY.

**Tình huống 4:** Tất cả delegate ABSTAIN; thay `allOf` bằng `anyOf` không đổi nội dung các manager. Kết quả?

**Đáp án:** Từ GRANT mặc định chuyển sang DENY mặc định. Tốt nhất thiết kế điều kiện cần quyết định tường minh và kiểm thử để không phụ thuộc vào tình cờ abstain.

**Tình huống 5:** Quy tắc “tài khoản active AND (editor OR admin)” nên dùng cấu trúc gì?

**Đáp án:** `allOf(activeManager, anyOf(editorManager, adminManager))`. `activeManager` phải DENY khi bị khóa; không được đặt nó vào `anyOf` cùng role rồi để một role khác ghi đè việc khóa.

## Tài liệu chính thức

- [Spring Security API – AuthorizationManagers](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, overload fallback từ 6.3, `not` và mô tả abstain.
- [Spring Security API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`, `verify`, `check` deprecated.
- [Spring Security Reference – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): mô hình `AuthorizationManager`, các manager tích hợp và quyết định quyền.
- [Spring Security Reference – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): cấu hình `SecurityFilterChain`, `authorizeHttpRequests` và `AuthorizationManager` cho request.
- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): áp dụng quyền trong Spring service.
