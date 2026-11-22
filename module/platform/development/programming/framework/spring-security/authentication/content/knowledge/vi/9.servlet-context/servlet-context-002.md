# Cơ chế ThreadLocal và yêu cầu dọn ngữ cảnh sau xử lý

> **Module:** Spring Security — authentication. **Nhóm kiến thức:** Ngữ cảnh Servlet. Bài học giải thích cách Spring Security liên kết danh tính với thread của Servlet request thông qua `SecurityContextHolder`, tại sao ngữ cảnh phải được dọn khi xử lý xong, và cách truyền context có kiểm soát khi ứng dụng dùng thread pool hoặc bất đồng bộ. Phần thực hành có chương trình Java 17 chạy độc lập trên Spring Security 6.5.11.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt `Authentication`, `SecurityContext`, `SecurityContextHolder`, `SecurityContextHolderStrategy` và `SecurityContextRepository`.
2. Mô tả chính xác mô hình `ThreadLocal`: dữ liệu thuộc về **thread đang chạy**, không tự thuộc về HTTP request, không tự lan sang worker thread khác.
3. Giải thích tại sao một Servlet worker được tái dùng có thể giữ danh tính cũ nếu context không được dọn, dù request trước đã kết thúc.
4. Nhận biết chức năng cleanup của `FilterChainProxy`/`SecurityContextHolderFilter` hoặc `SecurityContextPersistenceFilter` trong cấu hình Spring Security.
5. Dùng `createEmptyContext`, `setContext`, `getContext` và `clearContext` ở đúng ranh giới lifecycle; ưu tiên `try/finally` khi tự quản lý ngữ cảnh.
6. Phân biệt **clear thread**, **persist context**, **invalidate session**, **logout** và **revoke JWT**.
7. Truyền ngữ cảnh vào `ExecutorService` qua `DelegatingSecurityContextExecutorService`, hiểu vì sao `@Async` và `CompletableFuture` không mặc nhiên có context.
8. Viết được test mô phỏng worker reuse, đường exception và yêu cầu cleanup an toàn.
9. Tránh nhầm anonymous authentication, mutable context và các storage mode nguy hiểm trong ứng dụng web nhiều người dùng.

## 2. Phân biệt năm khái niệm trước khi viết code

### 2.1. Authentication — chủ thể và bằng chứng đã được chấp nhận

`Authentication` có principal, credentials, authorities và `isAuthenticated()`. Filter có thể tạo authentication **chưa xác thực** từ request, gọi `AuthenticationManager`/`AuthenticationProvider` để kiểm bằng chứng, rồi nhận authentication **đã xác thực**.

`AuthenticationManager.authenticate(...)` trả object hoặc ném `AuthenticationException`. Nó **không tự lưu result vào ThreadLocal, session hoặc JWT**. Filter/caller của nó chịu trách nhiệm gắn result vào ngữ cảnh phù hợp. Không được tạo token `authenticated(...)` từ username/role do client khai rồi đưa vào holder như thể đã kiểm tra.

### 2.2. SecurityContext — vật chứa Authentication

`SecurityContext` là một object thường có `getAuthentication()` và `setAuthentication(...)`. Nó không phải thread hay session:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication current = context.getAuthentication();
~~~

`getContext()` của holder mặc định trả context (không phải `null`), nhưng `getAuthentication()` **có thể là `null`**. Vì vậy `getContext()!=null` hoàn toàn không đủ để kết luận “người dùng đã đăng nhập”.

### 2.3. SecurityContextHolder — cổng đọc/ghi ngữ cảnh hiện tại

Các API chính:

~~~java
SecurityContextHolder.getContext();
SecurityContextHolder.setContext(context);
SecurityContextHolder.createEmptyContext();
SecurityContextHolder.clearContext();
~~~

`SecurityContextHolder` là facade static tới `SecurityContextHolderStrategy` đã chọn. Đừng dùng nó như kho dữ liệu người dùng toàn cục. Khi sử dụng đúng, method security, authorization và các thành phần cùng thread có thể đọc được authentication của tác vụ đang xử lý.

### 2.4. SecurityContextHolderStrategy — lựa chọn nơi gắn context

Mặc định trong Servlet app là `MODE_THREADLOCAL`. Mỗi thread có slot riêng cho context. `MODE_INHERITABLETHREADLOCAL` cho phép một số thread con thừa hưởng giá trị khi **khởi tạo thread**; `MODE_GLOBAL` có context chung cả JVM. Hai chế độ sau cần đánh giá rất kỹ và không phải sửa nhanh cho web đa người dùng.

### 2.5. SecurityContextRepository — lưu qua request

`SecurityContextRepository` có trách nhiệm lấy/lưu context theo request, session hoặc policy khác. Nó giải quyết **persistence**, không phải cleanup của thread. Spring Security 6 dùng phổ biến `SecurityContextHolderFilter`, chỉ đọc/cung cấp context và yêu cầu **save tường minh** khi caller tự tạo authentication cần persist.

Một câu phân biệt:
- **Propagate:** đưa context tới một thread/tác vụ khác, có ranh giới sống.
- **Persist:** ghi context vào repository để các request tương lai có thể đọc lại.
- **Clear:** bỏ context khỏi holder của thread hiện tại khi kết thúc phạm vi.

Ba việc này có thể liên quan nhưng **không thay thế nhau**.

## 3. ThreadLocal là gì và tại sao Spring Security dùng nó?

Trong Java, `ThreadLocal<T>` cung cấp một chỗ lưu riêng cho từng thread:

~~~java
ThreadLocal<String> identity = new ThreadLocal<>();

identity.set("alice"); // Chỉ liên kết với thread đang gọi set.
String name = identity.get();
identity.remove();     // Dọn giá trị trên chính thread đó.
~~~

Nếu thread A gọi `set("alice")`, thread B thông thường không đọc được giá trị của A. Đó là lý do ThreadLocal phù hợp với phương thức service sâu trong call stack: người lập trình không cần truyền `Authentication` qua mọi tham số.

Tuy nhiên, **ThreadLocal không theo HTTP request**. Nó chỉ theo thread. Một thread xử lý xong một request có thể tiếp tục phục vụ request khác. Nếu không có cleanup, dữ liệu cũ vẫn nằm trong slot của thread đó.

### 3.1. Timeline dễ gây lỗi

~~~text
Thread T-1: xử lý request A của Alice
             setContext(Alice) -> controller chạy xong
             BUG: bỏ qua clearContext()

Thread T-1: được trả lại Servlet thread pool

Thread T-1: xử lý request B chưa đăng nhập
             code đọc SecurityContextHolder.getContext()
             có thể còn Authentication(Alice)
~~~

Đây là mô hình nguy cơ của **code ngoài/vượt ranh giới filter chuẩn** hoặc custom worker quản lý context không đúng. Trong `SecurityFilterChain` Spring Security cấu hình chuẩn, framework có trách nhiệm dọn holder; không phải mọi web app đều mặc nhiên mắc lỗi này.

### 3.2. Hai khái niệm cách ly khác nhau

| Cách ly | MODE_THREADLOCAL bảo đảm gì? | Điều nó không bảo đảm |
| --- | --- | --- |
| Thread A và Thread B đồng thời | Mỗi thread có slot holder riêng | Không cấm code cố ý gán cùng một object mutable vào cả hai |
| Hai task chạy **lần lượt trên cùng thread A** | Cùng slot A được dùng lại | Không tự xóa slot sau khi Task 1 kết thúc |
| Một HTTP request chuyển sang worker khác | Không tự đi cùng task | Không tự propagate Authentication |
| Kết thúc một HTTP request | Không biết request đã kết thúc | Cần filter/framework hoặc caller cleanup |
| Session tồn tại nhiều request | ThreadLocal không phải session store | Không tự persist/thu hồi login |

### 3.3. Context có thể bị chia sẻ dù slot ThreadLocal khác nhau

`ThreadLocal` lưu **tham chiếu object**, không tự deep-copy. Nếu thread A và thread B cùng được gán một `SecurityContext` mutable, mỗi thread có slot riêng nhưng vẫn trỏ tới cùng instance. Khi một bên sửa `setAuthentication(...)`, bên kia có thể quan sát thay đổi, tạo race và nhầm identity.

Vì vậy khi cần **thay** authentication trong một luồng đã được xác thực, dùng `SecurityContextHolder.createEmptyContext()` để tạo object mới rồi gắn result đã verified, thay vì sửa trực tiếp một context có thể được session/worker khác tham chiếu.

## 4. Lifecycle chuẩn của một Servlet request

Một request Servlet thường đi qua `DelegatingFilterProxy` → `FilterChainProxy` → một `SecurityFilterChain` được chọn theo URL và thứ tự chain. Các filter bảo mật có nhiệm vụ nạp context, xác thực, kiểm quyền và cleanup.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant FP as FilterChainProxy
    participant CF as SecurityContextHolderFilter
    participant AF as AuthenticationFilter
    participant AS as Authorization + Controller
    participant SH as SecurityContextHolder
    C->>FP: HTTP request
    FP->>CF: SecurityFilterChain phù hợp
    CF->>SH: Cung cấp context theo repository
    CF->>AF: Đi tiếp trong chain
    AF->>AF: Nếu có credentials: xác thực
    opt Authentication thành công
        AF->>SH: Thiết lập Authentication hợp lệ
    end
    AF->>AS: Đi tiếp
    AS->>SH: Đọc context/Authentication
    AS-->>CF: Response hoặc exception
    Note over CF,SH: finally: clearContext() cho thread hiện tại
    CF-->>C: Hoàn tất HTTP response
~~~

Sơ đồ khái niệm không thể hiện tất cả filter, lazy/deferred context, async dispatch hoặc repository cụ thể. Tài liệu Spring Security nói `FilterChainProxy` đảm bảo holder được dọn khi một request kết thúc; các filter quản lý security context đảm trách vòng đời đó.

### 4.1. SecurityContextHolderFilter trong Spring Security 6

`SecurityContextHolderFilter` thường lấy `Supplier<SecurityContext>` từ `SecurityContextRepository` và thiết lập deferred context vào holder. Sau khi downstream chain chạy, kể cả ném exception, filter dọn holder theo kiểu `finally`.

Pseudocode thể hiện nguyên tắc:

~~~java
try {
    // Thiết lập nguồn SecurityContext từ repository / deferred context.
    filterChain.doFilter(request, response);
}
finally {
    securityContextHolderStrategy.clearContext();
}
~~~

Các biến trong đoạn này thuộc code framework/filter; đây **không phải một class Java độc lập**. Không copy vào controller và gọi clear trong lúc request vẫn cần Authentication.

### 4.2. Vì sao dọn cuối chain, không phải mỗi khi có filter?

Nếu một custom filter gọi `clearContext()` ngay sau khi xác thực rồi vẫn cho request chạy tiếp, `AuthorizationFilter`, method security hoặc controller có thể không thấy principal. Cleanup đúng phải diễn ra **sau toàn bộ phạm vi sử dụng context**.

Một filter ở giữa chain **không nên** tự dọn bừa nếu nó không sở hữu lifecycle. Với framework chuẩn, thường không cần viết filter cleanup bổ sung. Với custom code tự quản lý context bên ngoài framework, tự đặt context và dùng `try/finally` ở phạm vi phù hợp.

### 4.3. Ngoại lệ không được làm bỏ qua cleanup

Một controller ném runtime exception, password provider ném `AuthenticationException` hoặc request bị từ chối bởi authorization — tất cả đều là đường mà thread cuối cùng được trả lại pool. Nếu chủ sở hữu context chỉ clear ở nhánh thành công, dữ liệu có thể còn sót ở nhánh thất bại.

Cấu trúc đúng khi **caller tự quản lý ranh giới context**:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(context);
    executeAuthorizedWork();
}
finally {
    SecurityContextHolder.clearContext();
}
~~~

`verifiedAuthentication` phải đến từ một cơ chế đáng tin. `executeAuthorizedWork()` là logic tích hợp được ứng dụng định nghĩa; đoạn này minh họa `try/finally`, không phải code độc lập hay hướng dẫn tự cấp quyền từ client input.

### 4.4. SecurityContextPersistenceFilter ở cấu hình legacy

Một số hệ thống cũ/đã tùy chỉnh dùng `SecurityContextPersistenceFilter`. Nó quản lý load, save và clear context, trong khi `SecurityContextHolderFilter` của Spring Security 6 thường chỉ load/cung cấp context và clear, yêu cầu save tường minh nếu cần.

Không cấu hình cả hai filter này trong cùng security chain để mong “an toàn gấp đôi”. Hãy xác định filter thực tế đang được dùng, phiên bản framework và cấu hình `requireExplicitSave`.

## 5. Clear, save, logout và token revocation là bốn chuyện khác nhau

| Thao tác | Mục tiêu | Tác dụng |
| --- | --- | --- |
| `SecurityContextHolder.clearContext()` | Vệ sinh thread hiện tại | Loại liên kết context khỏi thread holder theo strategy |
| `securityContextRepository.saveContext(context, request, response)` | Lưu context theo repository | Có thể cho request sau nạp lại context tùy policy |
| Logout / invalidate `HttpSession` | Chấm dứt phiên đang lưu | Phụ thuộc logout handler, session store, cookie và cấu hình |
| JWT / refresh token revocation | Từ chối token đã phát hành | Cần expiry, revoke store/denylist/introspection hoặc chính sách riêng |

### 5.1. Một ví dụ khi cần persist

Nếu ứng dụng tự thực hiện authentication sau khi kiểm bằng chứng thật và muốn lưu trong session:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticationReturnedByManager);
SecurityContextHolder.setContext(context);

// Chỉ khi ứng dụng cần lưu qua request và dùng repository phù hợp:
securityContextRepository.saveContext(context, request, response);
~~~

Đây là **đoạn tích hợp**; phải dùng Authentication do provider xác minh và các object `request`, `response`, `securityContextRepository` của luồng Servlet hợp lệ. Saving không thay cleanup, và cleanup không thay saving.

### 5.2. Spring Security 6 explicit save

Theo tài liệu Spring Security 6, `SecurityContextHolderFilter` **không tự động lưu** mọi thay đổi của `SecurityContext`. Khi tự lập một phiên đăng nhập cần tồn tại qua request sau, ứng dụng phải gọi `saveContext` phù hợp, hoặc dùng authentication mechanism đã xử lý việc đó.

Một request sử dụng `SessionCreationPolicy.STATELESS` hay `NullSecurityContextRepository` vẫn cần clear ThreadLocal sau khi xử lý, dù không có session cần lưu. Đừng nhầm “stateless” với “không có SecurityContext trong thời gian request”.

### 5.3. clearContext không xóa object khỏi mọi nơi

`clearContext()` loại context khỏi holder của **thread đang gọi**. Nếu object ấy đang được giữ bởi `HttpSession`, biến local, task async, cache hoặc reference khác, nó chưa chắc biến mất khỏi memory. Không thể dựa vào clear để thu hồi JWT, kết thúc session hoặc xóa principal khỏi mọi thread.

### 5.4. Vì sao không thay bằng setAuthentication(null)?

~~~java
SecurityContextHolder.getContext().setAuthentication(null);
~~~

Đoạn đó sửa **Authentication bên trong object** đang gắn với thread, nhưng có thể vẫn giữ reference tới `SecurityContext` và có thể tác động một context đang được chia sẻ. Mục tiêu cleanup phải dùng `SecurityContextHolder.clearContext()` — API dọn của đúng strategy.

Tương tự, `SecurityContextHolder.setContext(SecurityContextHolder.createEmptyContext())` tạo một context rỗng mới nhưng vẫn gắn object với thread; không diễn đạt cùng ý nghĩa cleanup bằng `clearContext()`.

## 6. Rủi ro chính: thread pool giữ lại danh tính request trước

Ví dụ:

~~~text
Task 1 trên worker W:
    setContext(Authentication Alice / ROLE_ADMIN)
    xử lý xong, quên clearContext()

Task 2 được giao đúng worker W:
    không thiết lập context
    gọi getContext().getAuthentication()
    nhận Alice còn sót
~~~

Điều đó có thể gây sai audit, giữ thông tin principal quá lâu, memory retention, hoặc tệ hơn là code kiểm quyền sai từ Authentication cũ. Lỗi có thể xuất hiện ngẫu nhiên do task scheduling và thread reuse.

**Cần hiểu ranh giới:** `SecurityFilterChain` được cấu hình đúng có bảo đảm dọn của Spring Security; nguy cơ nói trên đặc biệt liên quan tới **custom worker/executor, code tự setContext, filter chạy ngoài chuỗi bảo mật, callback/batch task** không dùng đúng lifecycle. Đừng đổ lỗi cho ThreadLocal khi thực tế sai là code owner bỏ cleanup.

## 7. Demo Java 17 hoàn chỉnh: chứng minh propagation và cleanup

Chương trình sau chạy không cần Servlet, dùng **Spring Security Core thật**. Nó tạo một single-thread executor để bảo đảm thread worker **được tái sử dụng**; kiểm thử qua `Future.get()` và chủ động kiểm output để thất bại ngay nếu behavior khác dự kiến.

Một đoạn mô phỏng thiếu cleanup có chủ ý **chỉ dành cho lab**, sau đó chương trình xóa trạng thái còn sót. Không sử dụng đoạn đó trong production.

### 7.1. Cấu trúc dự án

~~~text
security-context-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/context/
    └── SecurityContextThreadLocalLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.context.SecurityContextThreadLocalLab'
}
~~~

Spring Boot project thực nên dùng dependency management/BOM để đồng bộ phiên bản framework và bản vá; Gradle bên trên chỉ là demo độc lập về Spring Security Core.

### 7.2. Mã Java đầy đủ

Tệp `src/main/java/example/context/SecurityContextThreadLocalLab.java`:

~~~java
package example.context;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityContextThreadLocalLab {

    private static SecurityContext labContext(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Chỉ dùng một Authentication GIẢ cho thí nghiệm ThreadLocal.
        // Production không được cấp authenticated token từ input chưa kiểm.
        Authentication dummy =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_DEMO")));

        context.setAuthentication(dummy);
        return context;
    }

    private static String currentUser() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return authentication == null
                ? "<none>"
                : authentication.getName();
    }

    private static void verifyAndPrint(
            String label, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    label + " expected " + expected + " but got " + actual);
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) throws Exception {
        SecurityContextHolder.setStrategyName(
                SecurityContextHolder.MODE_THREADLOCAL);

        ExecutorService rawPool = Executors.newSingleThreadExecutor();

        try {
            verifyAndPrint("main-before", currentUser(), "<none>");

            verifyAndPrint(
                    "worker-before",
                    rawPool.submit(SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "<none>");

            // Mô phỏng ngữ cảnh của request đã được xác minh.
            SecurityContextHolder.setContext(labContext("alice"));
            try {
                verifyAndPrint("main-in-request", currentUser(), "alice");

                // Thread worker khác main; không tự kế thừa ThreadLocal.
                verifyAndPrint(
                        "worker-plain",
                        rawPool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "<none>");

                // Wrapper lấy context từ thread submit và
                // đảm bảo dọn context trên worker khi task kết thúc.
                ExecutorService securePool =
                        new DelegatingSecurityContextExecutorService(rawPool);

                verifyAndPrint(
                        "worker-wrapped",
                        securePool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "alice");

                verifyAndPrint(
                        "worker-after-wrapped",
                        rawPool.submit(
                                SecurityContextThreadLocalLab::currentUser)
                                .get(),
                        "<none>");
            }
            finally {
                SecurityContextHolder.clearContext();
            }

            verifyAndPrint("main-after", currentUser(), "<none>");

            // CỐ TÌNH SAI: worker có context nhưng không gọi clear.
            // Chỉ minh họa bug, không phải cách viết ứng dụng thật.
            rawPool.submit(() -> {
                SecurityContextHolder.setContext(labContext("stale-user"));
            }).get();

            verifyAndPrint(
                    "worker-stale-next-task",
                    rawPool.submit(
                            SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "stale-user");

            // Dọn tại CHÍNH worker chứa ThreadLocal.
            rawPool.submit(SecurityContextHolder::clearContext).get();

            verifyAndPrint(
                    "worker-after-clear",
                    rawPool.submit(
                            SecurityContextThreadLocalLab::currentUser)
                            .get(),
                    "<none>");
        }
        finally {
            // Best effort cleanup kể cả khi assertion/worker ném exception.
            try {
                rawPool.submit(SecurityContextHolder::clearContext).get();
            }
            finally {
                rawPool.shutdownNow();
                SecurityContextHolder.clearContext();
            }
        }
    }
}
~~~

### 7.3. Chạy với Gradle

Từ thư mục `security-context-lab`, dùng JDK 17+ cùng Gradle tương thích:

~~~bash
gradle run --quiet
~~~

Nếu có Gradle Wrapper:

~~~bash
./gradlew run --quiet
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat run --quiet
~~~

**Output do `System.out.println` tạo ra** (không tính Gradle):

~~~text
main-before=<none>
worker-before=<none>
main-in-request=alice
worker-plain=<none>
worker-wrapped=alice
worker-after-wrapped=<none>
main-after=<none>
worker-stale-next-task=stale-user
worker-after-clear=<none>
~~~

Các dòng này có kết quả quyết định vì một worker được dùng lại và `main` chờ từng `Future.get()`. Bản demo cố tình tạo một stale context ngắn hạn, rồi dọn ngay sau khi đã chứng minh được rủi ro.

### 7.4. Giải thích chính xác

- `main-before=<none>`: main chưa có Authentication.
- `worker-before=<none>`: worker ban đầu không có Authentication.
- `main-in-request=alice`: main được gắn context demo của Alice.
- `worker-plain=<none>`: worker không tự nhìn thấy `MODE_THREADLOCAL` của main.
- `worker-wrapped=alice`: adapter `DelegatingSecurityContextExecutorService` dùng context tại thời điểm submit task.
- `worker-after-wrapped=<none>`: wrapper đã cleanup khi task xong.
- `main-after=<none>`: `clearContext()` trong `finally` dọn main.
- `worker-stale-next-task=stale-user`: task cố tình không clear, nên task sau thấy danh tính còn sót.
- `worker-after-clear=<none>`: cleanup được thực thi **trên worker**, không phải nhờ clear trên main.

### 7.5. Giới hạn của demo

Authentication ở `labContext(...)` là **giả lập** để nghiên cứu propagation. Nó không kiểm mật khẩu/JWT và không dùng được làm logic đăng nhập. Ứng dụng thật phải lấy Authentication đã được provider/decoder/IdP đáng tin xác minh.

Chương trình minh họa lưu/ngắt context ở Java threads, **không mô phỏng** session, CSRF, authorization, servlet dispatch hay mọi chi tiết filter chain. Những điều đó cần kiểm riêng ở web integration tests.

## 8. Mẫu an toàn khi ứng dụng tự sở hữu context

### 8.1. Dùng try/finally trong worker tùy chỉnh

~~~java
// verifiedAuthentication lấy từ một nguồn được phép tin.
SecurityContext scoped = SecurityContextHolder.createEmptyContext();
scoped.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(scoped);
    runAuthorizedWork();
}
finally {
    SecurityContextHolder.clearContext();
}
~~~

Snippet trên là code tích hợp, không phải class độc lập. Nếu thread có context **cũ hợp lệ** cần được khôi phục sau khi chạy, không tự clear bừa; phải có chính sách save/restore và ranh giới scope. Wrapper Spring Security là lựa chọn tốt cho tác vụ cần propagation.

### 8.2. Không dùng context giả để vượt authentication

Một anti-pattern:

~~~java
// SAI NGHIÊM TRỌNG nếu username/roles đến từ HTTP request chưa verify:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                requestUsername, null, clientSuppliedAuthorities));
SecurityContextHolder.setContext(context);
~~~

Nó tự xác nhận quyền của client mà không có bằng chứng. Với các ứng dụng dùng username/password, gọi `AuthenticationManager` và chỉ dùng result thành công. Với JWT, xác minh signature, issuer, audience/time và claims theo policy trước khi tạo authentication.

### 8.3. Không gọi clear quá sớm bên trong filter

~~~java
// Sai về vòng đời nếu controller phía sau cần authentication.
SecurityContextHolder.setContext(verifiedContext);
SecurityContextHolder.clearContext();
filterChain.doFilter(request, response);
~~~

Đoạn này chỉ là ví dụ **lỗi thứ tự**. Chủ sở hữu security context phải dọn sau downstream xử lý; trong Spring Security chain chuẩn, để hạ tầng filter quản lý.

### 8.4. Không dùng clear thay authorization

`clearContext()` là thao tác vệ sinh state, không phải kết quả quyết định 401/403. Khi một request không được phép, authorization filter hoặc policy phải từ chối, và authentication entry point/access denied handler chịu trách nhiệm biểu diễn HTTP response. Chỉ xóa context rồi mặc nhiên cho controller chạy tiếp có thể làm sai logic hệ thống.

## 9. Async propagation và giới hạn của ThreadLocal

### 9.1. ExecutorService mặc định

`ExecutorService.submit(...)` không tự mang ThreadLocal của thread gọi sang thread được cấp từ pool. Worker có thể có holder rỗng, hoặc tệ hơn là state cũ do một task khác không cleanup.

Spring Security cung cấp `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor` và những adapter liên quan để thiết lập và dọn context theo task.

Ví dụ (đoạn tích hợp):

~~~java
ExecutorService secured =
        new DelegatingSecurityContextExecutorService(rawExecutor);

secured.submit(() -> {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
    useAuthenticatedIdentity(authentication);
});
~~~

Constructor không có context tường minh dùng context tại thời điểm **task được submit** theo API. `useAuthenticatedIdentity` do ứng dụng tự định nghĩa; không áp dụng cho job khi người gửi task chưa được xác thực.

### 9.2. Context cố định không phải context của từng user

Adapter còn có constructor nhận một `SecurityContext` cụ thể:

~~~java
ExecutorService serviceIdentityExecutor =
        new DelegatingSecurityContextExecutorService(
                rawExecutor, serviceSecurityContext);
~~~

Điều này có nghĩa các task dùng context **được cấp sẵn**, không tự lấy user tại thời điểm submit. Chỉ sử dụng khi tác vụ thật sự cần service identity với quyền tối thiểu và đã được tổ chức phê duyệt. Đừng vô tình dùng context admin cố định cho mọi user request.

### 9.3. Capture một reference mutable không phải snapshot bất biến

Context được propagate có thể là reference tới object `SecurityContext` hiện tại; nếu task đợi trong queue và context hoặc authorities bị sửa/thu hồi, không mặc nhiên có snapshot bất biến hay kiểm lại quyền.

Đối với tác vụ chạy nhiều phút/giờ, có thể tốt hơn khi chỉ truyền subject ID, tenant ID và request ID đã kiểm tra, rồi tái kiểm quyền/việc thu hồi tại thời điểm xử lý. Không lưu nguyên bearer token hoặc password thô vào queue để worker “đăng nhập lại”.

### 9.4. @Async, CompletableFuture và Servlet async

- `@Async` thường chạy trên executor khác. Mặc định `MODE_THREADLOCAL` không đảm bảo Spring Security principal tự sang worker. Cần `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế propagation hợp lệ cho executor được dùng.
- `CompletableFuture.supplyAsync(...)` không chỉ định executor có thể dùng common pool. Không tự thấy principal của thread Servlet.
- Spring Security có tích hợp với **Spring MVC `Callable`** thông qua hạ tầng web async, nhưng không nên suy ra mọi `DeferredResult`, callback custom, manual `new Thread(...)` hoặc `CompletableFuture` đều được tự động propagate.
- Servlet async có thể dùng **dispatch khác/thread khác**. Khi cần, xác minh filter dispatch, async integration và cleanup ở từng ranh giới. Không giữ ThreadLocal sau response.
- Scheduled jobs không có request-bound principal; dùng service identity hoặc kiểm quyền khi xử lý, không mượn context cuối cùng đã đăng nhập.

### 9.5. InheritableThreadLocal có giải quyết được không?

`MODE_INHERITABLETHREADLOCAL` cho phép thừa hưởng khi **tạo thread con**, không phải khi **submit task** vào worker đã có từ trước. Trong pool, worker có thể sống qua nhiều request và giữ giá trị thừa hưởng ở một thời điểm không liên quan.

Vì vậy không đổi sang `MODE_INHERITABLETHREADLOCAL` toàn app để “sửa” lỗi `@Async`. Đây là nguy cơ stale identity, không phải giải pháp propagation theo từng task.

## 10. Ba storage mode và trường hợp dùng

| Chiến lược | Đặc điểm | Áp dụng thận trọng |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Mỗi thread có context liên kết riêng | Mặc định phù hợp cho Servlet; cleanup ở cuối scope |
| `MODE_INHERITABLETHREADLOCAL` | Thread con được tạo có thể thừa hưởng context parent | Không phù hợp để dùng rộng với worker pool đa user |
| `MODE_GLOBAL` | Một context chung cho JVM | Không dùng trong web app đa người dùng vì rủi ro trộn danh tính |

Đổi strategy bằng `SecurityContextHolder.setStrategyName(...)` là cấu hình **toàn ứng dụng**, không phải thao tác request. Nếu cần thì quyết định ở startup; thay runtime có thể khiến các thành phần đã giữ strategy khác nhau.

Java virtual threads có semantics ThreadLocal theo thread riêng nhưng không giải quyết thay việc quản lý ngữ cảnh, không tự propagate context từ thread submit. Một số mô hình thực thi có thời gian sống khác platform thread pool; vẫn phải bảo đảm không giữ identity qua scope và không tạo quá nhiều ThreadLocal state không cần thiết.

## 11. Kiểm tra trường hợp anonymous và context rỗng

Trong Spring Security, `AnonymousAuthenticationFilter` có thể đưa `AnonymousAuthenticationToken` vào holder để thể hiện user chưa đăng nhập. Một số class token có `isAuthenticated()==true` theo contract token, nhưng điều đó **không tương đương một user đã chứng minh danh tính thực sự**.

| Biểu thức | Có thể suy ra gì? | Điều không thể suy ra |
| --- | --- | --- |
| `SecurityContextHolder.getContext()!=null` | Có object context | Người dùng đã đăng nhập |
| `getContext().getAuthentication()!=null` | Có Authentication object | Không phải anonymous |
| `auth.isAuthenticated()==true` | Cờ trên token là true | Bằng chứng user đã được xác minh theo policy của endpoint |
| `auth.getAuthorities()` | Các authority trong token | Quyền trên tài nguyên/tenant hiện thời chắc chắn hợp lệ |
| `authorizeHttpRequests().authenticated()` | Policy framework đánh giá dựa trên trust resolver và context | Tự động thu hồi token/session cũ khi DB đổi |

Khi viết phân quyền, dùng `authenticated()`, `hasAuthority(...)`, method security và kiểm tài nguyên/tenant thích hợp. Không dùng kiểu kiểm `getContext() != null` làm bằng chứng được phép truy cập.

## 12. Lưu ý về object mutable và session

### 12.1. Không sửa bừa context từ session

Context nạp từ repository/session có thể được object khác tham chiếu. Code:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(newAuthentication);
~~~

có thể sửa object dùng chung ngoài dự kiến. Khi cần thay Authentication từ một nguồn đã verified, ưu tiên tạo `SecurityContextHolder.createEmptyContext()` rồi gắn và persist theo policy, thay vì đụng object có thể được chia sẻ. Cũng cần thận trọng khi nhiều request cùng session chạy song song.

### 12.2. ThreadLocal clear không phải xóa session

Một request dùng context từ `HttpSessionSecurityContextRepository`. Khi kết thúc:
- holder của thread được dọn;
- `HttpSession` có thể **vẫn giữ context** cho request sau;
- đó là điều bình thường nếu user vẫn đang có session hợp lệ.

Logout yêu cầu luồng/logout handler và chính sách session riêng. Nếu account bị khóa sau khi user đã đăng nhập, chỉ evict `UserDetails` cache và clear thread **không đảm bảo** session/JWT đã bị thu hồi.

### 12.3. Không lưu Authentication vào static field của singleton

Một singleton service lấy `SecurityContextHolder.getContext().getAuthentication()` ở constructor rồi giữ trong field có thể giữ nhầm principal startup/anonymous/user khác. Đọc từ holder tại **thời điểm request hiện hành** nếu cần, hoặc truyền một dữ liệu identity tối thiểu đã kiểm. Không làm một biến `static Authentication currentUser` toàn JVM.

## 13. Những lỗi đặc trưng khi cleanup sai

| Vấn đề | Triệu chứng | Nguyên nhân có thể |
| --- | --- | --- |
| Worker còn principal của task trước | Task B thấy Alice dù không được gán context | Worker tự `setContext` nhưng không clear |
| Controller mất principal sau filter custom | `Authentication` null khi vào controller | Filter dọn quá sớm hoặc thứ tự filter sai |
| @Async không thấy user | Principal null | Thread khác; không có propagation |
| Bật InheritableThreadLocal và lỗi ngẫu nhiên | Worker thấy user của task submit cũ | Pool thừa hưởng tại lúc tạo thread, không theo từng task |
| Stateless JWT request sau thấy user cũ | Cross-request identity confusion | Một custom path không nạp/dọn ngữ cảnh đúng |
| Logout nhưng API session vẫn hoạt động | Phiên chưa bị hủy/thu hồi | Chỉ gọi clear thread mà không invalidate session |
| Repeated request tạo memory retention | Principal/details bị giữ bởi worker lâu | ThreadLocal/reference chưa được dọn |
| Test @WithMockUser luôn xanh | Không phát hiện thiếu cleanup | Mock security context không đi qua logic worker thực tế |
| Lỗi chỉ xuất hiện khi exception | Task ném lỗi trước dòng cleanup | Không dùng finally |
| Principal đúng nhưng authorities cũ | Session/JWT stale | Không nhất thiết do ThreadLocal; cần revalidate/revoke policy |

**Chẩn đoán không nên đoán chỉ từ một log:** phải xác định filter chain nào đã chọn, thread nào chạy code, ai đặt context, khi nào được clear, và nguồn Authentication có thể đến từ session/ID token hay custom cache.

## 14. Kiểm thử có ý nghĩa

### 14.1. Kiểm worker reuse

Chạy hai task tuần tự trên `Executors.newSingleThreadExecutor()`:
1. Task 1 đặt context A rồi kết thúc.
2. Task 2 đọc holder mà không đặt context.
3. Nếu thấy A, cleanup đã thiếu.
4. Thêm `try/finally` hoặc wrapper; task 2 phải thấy empty.
5. Chạy lại với task 1 cố tình ném exception để bảo đảm cleanup vẫn xảy ra.

Đây là lý do demo dùng đúng một worker và chờ `Future.get()`: không may mắn “trúng” thread khác che lỗi.

### 14.2. Test exception trong worker

Đoạn JUnit/pseudocode tích hợp:

~~~java
Future<?> failed = contextualPool.submit(() -> {
    throw new IllegalStateException("simulated failure");
});

assertThrows(ExecutionException.class, failed::get);

// Dùng RAW underlying pool để kiểm không còn context từ wrapper:
Authentication residual = rawPool.submit(() ->
        SecurityContextHolder.getContext().getAuthentication()
).get();
assertNull(residual);
~~~

Các biến `contextualPool`, `rawPool`, `assertThrows`, `assertNull` phải được định nghĩa trong test thích hợp. Đây không phải file độc lập. Chủ đích là đường exception **không được** giữ SecurityContext trên worker.

### 14.3. Test qua Servlet/Spring Security thật

Dùng `MockMvc` với security filter chain hoặc end-to-end HTTP:
- Request Alice authenticated và có ROLE_USER.
- Request tiếp không credential (với chính sách stateless) không thấy Alice.
- Request Bob authenticated riêng, không thấy authorities Alice.
- Request lỗi provider/controller vẫn không để lại context.
- Async `Callable`/`DeferredResult`/`@Async` có behavior đúng với executor thực tế.
- Session và logout được test theo policy riêng.

`MockMvc` có thể dùng test thread và test support tự quản lý context; để kiểm chính xác behavior Servlet thread pool dưới tải, bổ sung integration test với embedded server và kiểm metadata an toàn. Không log raw token/password để phục vụ kiểm thử.

### 14.4. Review custom filters

Dò những nơi gọi:
- `SecurityContextHolder.setContext(...)`;
- `SecurityContextHolder.getContext().setAuthentication(...)`;
- `SecurityContextHolder.clearContext()`;
- tự tạo `ThreadLocal<User>` hoặc `InheritableThreadLocal`;
- `ExecutorService`, `@Async`, `CompletableFuture`, scheduled task;
- custom `SecurityContextRepository`.

Với mỗi nơi, trả lời: **ai tạo Authentication? đã verify chưa? owner lifecycle là ai? bao giờ dọn? có thread hopping không? có persist cần thiết không?**

## 15. Logging và observability không lộ thông tin

Để debug có thể đo:
- request ID/correlation ID an toàn, route template, HTTP status;
- thread ID/name khi điều tra worker reuse;
- loại Authentication/provider và outcome;
- mốc context installed/propagated/cleared trong custom worker;
- số task async bị từ chối hoặc lỗi context propagation.

**Không ghi:** raw `Authorization` header, cookie/session ID, password, bearer/JWT token, toàn bộ `SecurityContext.toString()` hoặc `Authentication.toString()`, full principal/details nhạy cảm. Những object đó có thể chứa credentials, claims hoặc PII.

Nếu thấy “thỉnh thoảng request A có danh tính B”, kiểm các đường custom context và thread reuse; nhưng cũng cần phân biệt với session/cookie từ chính client hoặc token được cache sai. Một lỗi identity có thể bắt nguồn từ nhiều lớp, không chỉ ThreadLocal.

## 16. Anti-pattern và cách sửa

1. **Tự setContext rồi không clear trong background task:** dùng `try/finally` hoặc adapter Spring Security.
2. **Gọi clear trên thread main để xóa worker:** `MODE_THREADLOCAL` chỉ dọn thread đang gọi.
3. **Clear trong filter trước controller:** làm downstream mất principal. Để owner quản lý cuối scope.
4. **Cleanup chỉ sau đường thành công:** exception dễ để sót context. Dùng `finally`.
5. **Dùng MODE_GLOBAL trong Servlet đa user:** trộn danh tính toàn JVM.
6. **Bật MODE_INHERITABLETHREADLOCAL với thread pool:** có thể giữ identity stale từ lúc tạo worker.
7. **Cho rằng context != null nghĩa đã đăng nhập:** context có thể rỗng.
8. **Cho rằng authentication != null luôn nghĩa user thật:** anonymous token cũng tồn tại.
9. **Tự tạo authenticated token từ request:** bỏ qua bước kiểm credential, dẫn tới bypass.
10. **Đọc Authentication tại constructor singleton:** dễ giữ state sai lâu dài.
11. **Cập nhật context mutable chia sẻ tùy tiện:** có nguy cơ race.
12. **Coi clearContext là logout:** session/token vẫn có lifecycle riêng.
13. **Coi clearContext là saveContext:** cleanup không tự persist.
14. **Coi stateless là khỏi clear:** mọi context request vẫn cần lifecycle đúng.
15. **Dùng CompletableFuture default commonPool rồi yêu cầu principal:** không có propagation tự động.
16. **Dùng một admin context cố định cho mọi task:** quá quyền; dùng service identity riêng có phạm vi phù hợp.
17. **Capture Authentication vào job queue lâu dài:** có thể stale sau khi quyền bị thu hồi.
18. **Đặt ThreadLocal<User> khác và nghĩ Spring Security sẽ cleanup nó:** custom holder cần lifecycle riêng.
19. **Không test exception/reuse:** bỏ sót nhánh gây leak.
20. **Log nguyên SecurityContext hoặc Authentication:** có thể lộ credential/PII.
21. **Cấu hình cả hai context filters để “chắc ăn”:** không đúng kiến trúc; chọn đúng một cơ chế.
22. **Phụ thuộc vào một thread name để chứng minh user đã được verify:** tên thread không phải bằng chứng danh tính.

## 17. Câu hỏi tự kiểm tra

**1. Một Servlet thread phục vụ hai request liên tiếp có tự xóa ThreadLocal sau request đầu không?**  
Không theo semantics Java ThreadLocal. Spring Security filter chain phải quản lý cleanup hoặc custom owner dùng `clearContext()`.

**2. Vì sao thread A thấy Alice nhưng thread B thấy Authentication null?**  
`MODE_THREADLOCAL` gắn context theo thread. Không có propagation thì B không tự có context A.

**3. Gọi `clearContext()` trên A có xóa context của B?**  
Không theo strategy ThreadLocal mặc định.

**4. `SecurityContextHolder.getContext() != null` có chứng minh login thành công?**  
Không. Nó có thể trả một empty context; cần kiểm policy Authentication phù hợp.

**5. `Authentication.isAuthenticated()==true` luôn là user đã verify?**  
Không. Anonymous hoặc token do custom code tự tạo có thể có flag true; kiểm cơ chế nguồn và trust resolver/authorization.

**6. SecurityContextHolderFilter có tự save context vào session trong Spring Security 6 không?**  
Không; explicit save cần thiết nếu caller muốn persistence và filter không có cơ chế save khác.

**7. Có thể thay `clearContext()` bằng `getContext().setAuthentication(null)` không?**  
Không tương đương: một thao tác sửa object, một thao tác dọn holder của thread.

**8. @Async không có principal; có nên bật MODE_GLOBAL không?**  
Không. Dùng executor/wrapper truyền context có kiểm soát hoặc subject/service identity riêng.

**9. Vì sao InheritableThreadLocal không khắc phục an toàn thread pool?**  
Nó thừa hưởng lúc tạo thread con, trong khi worker pool được dùng cho nhiều task sau đó.

**10. Một request exception có cần clear không?**  
Có, cleanup ở `finally` của owner hoặc framework.

**11. clearContext có thu hồi JWT đã ký chưa hết hạn không?**  
Không. JWT có cơ chế hết hạn và thu hồi riêng.

**12. Vì sao test cần reuse cùng worker?**  
Nếu task 2 chạy trên worker khác, nó có thể thấy context rỗng dù task 1 đã để lại state trên worker đầu.

**13. DelegatingSecurityContextExecutorService làm hai việc gì?**  
Gắn context phù hợp cho task worker và dọn/khôi phục holder khi task kết thúc.

**14. Gửi một task sau 30 phút với context đã capture, quyền của user đã bị thu hồi: có tự cập nhật không?**  
Không có bảo đảm. Cần revalidate/policy tại thời điểm thực thi với job dài hạn.

**15. Một singleton giữ field Authentication để tránh gọi holder mỗi request có an toàn không?**  
Không. Field singleton được chia sẻ giữa request và có thể giữ identity sai.

## 18. Checklist triển khai

- [ ] Xác định đúng `SecurityFilterChain` và context filter đang dùng cho URL.
- [ ] Kiểm `SecurityContextHolderStrategy`, không thay bằng GLOBAL/INHERITABLE vô cớ.
- [ ] Khi tự set context ngoài framework, có `try/finally` và `clearContext()` trên đúng thread.
- [ ] Không clear quá sớm trước controller/authorization.
- [ ] Exception path cũng cleanup.
- [ ] Không tự tạo authenticated token từ dữ liệu chưa được verify.
- [ ] Khi cần persist, có `SecurityContextRepository.saveContext(...)` theo policy.
- [ ] Không nhầm cleanup với logout/revoke/session invalidation.
- [ ] Kiểm `@Async`, executors, scheduled tasks và CompletableFuture về propagation.
- [ ] Dùng wrapper đúng, không cấp context admin rộng cho mọi task.
- [ ] Tránh chia sẻ mutable SecurityContext không kiểm soát giữa thread.
- [ ] Không giữ Authentication trong singleton static fields.
- [ ] Có test thread reuse và exception, bên cạnh HTTP integration test.
- [ ] Kiểm token/session stale như vấn đề riêng với ThreadLocal cleanup.
- [ ] Logging không chứa token, password, cookies hoặc object context thô.

**Kết luận:** Trong ứng dụng Servlet, `SecurityContextHolder` mặc định dựa trên **ThreadLocal** để các thành phần cùng thread đọc được `Authentication`. Vì thread được tái sử dụng, **không dọn ngữ cảnh sau phạm vi xử lý có thể làm sai danh tính/tạo rò rỉ**. Spring Security quản lý việc này trong security filter chain; code tự tạo thread/task và tự set context phải dùng wrapper thích hợp hoặc `try/finally`. Hãy tách rõ **truyền context sang worker**, **lưu context cho request sau**, và **dọn context trên thread hiện tại**.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — Authentication Architecture và SecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Authentication Persistence/Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Concurrency Support: https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html
- Spring Security 6.5.11 — DelegatingSecurityContextExecutorService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html
- Spring Security 6.5 — SecurityContextHolder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html
- Java SE 17 — ThreadLocal API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
