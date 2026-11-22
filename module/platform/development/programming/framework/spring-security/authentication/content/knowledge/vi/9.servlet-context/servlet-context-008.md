# Tạo ngữ cảnh mới thay vì sửa đối tượng được chia sẻ giữa các yêu cầu

**Module:** Spring Security – authentication. **Mục:** Ngữ cảnh Servlet.

## 1. Bài toán: hai request cùng session nhưng Authentication đổi bất ngờ

Trong một ứng dụng Servlet, developer thường viết:

~~~java
// Dễ gây shared-object mutation nếu SecurityContext đến từ HttpSession.
SecurityContextHolder.getContext().setAuthentication(verifiedAuthentication);
~~~

Code trông hợp lý vì `SecurityContextHolder` mặc định sử dụng `ThreadLocal`: mỗi request thường chạy trên một thread riêng. Tuy nhiên, **ThreadLocal chỉ cô lập vị trí lưu tham chiếu**, không bắt đối tượng được tham chiếu phải là bản sao độc lập.

Một browser có thể gửi song song hai request cùng `JSESSIONID`. Nếu `HttpSessionSecurityContextRepository` tải **cùng một instance `SecurityContext`** từ session vào holder của hai thread, việc request A gọi `setAuthentication` **trực tiếp trên instance đó** có thể làm request B quan sát principal/authorities đã bị thay giữa chừng.

Spring Security 6.5 khuyến nghị trực tiếp:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

Cách này tạo **đối tượng ngữ cảnh mới**, thay reference hiện tại của thread thay vì mutate ngữ cảnh có thể đang được chia sẻ. Với custom authentication Servlet cần duy trì đăng nhập sang request sau, Spring Security 6 còn yêu cầu lưu đúng repository bằng `securityContextRepository.saveContext(context, request, response)`.

**Nguyên tắc của bài:** xác thực đúng → tạo `SecurityContext` mới → gắn `Authentication` đáng tin → đặt context mới vào holder → lưu qua repository khi cần phiên đăng nhập. Không dùng thao tác thay context như một cách tự cấp quyền từ input client.

## 2. Vì sao ThreadLocal không ngăn shared mutable state?

Bốn lớp khái niệm khác nhau:

| Lớp | Chức năng | Điều không tự bảo đảm |
| --- | --- | --- |
| `SecurityContextHolder` | API truy cập ngữ cảnh của scope hiện tại | Không deep-copy context |
| `SecurityContextHolderStrategy` | Quản lý nơi holder lưu reference, mặc định `MODE_THREADLOCAL` | Không biến object được giữ thành immutable |
| `SecurityContext` | Một object chứa `Authentication` | Không bảo đảm chỉ một request sở hữu |
| `Authentication` | Principal, authorities, credentials, details và trạng thái đã xác thực | Không phải dữ liệu vĩnh viễn, có thể chứa mutable nested objects |
| `SecurityContextRepository` | Load/save context theo request/session policy | Không nhất thiết clone object mỗi lần load |
| `HttpSession` | Lưu trạng thái theo session identifier | Một session có thể bị nhiều HTTP requests truy cập cùng lúc |

Minh họa hai ThreadLocal độc lập cùng trỏ đến một object:

~~~text
                        HttpSession S
                       (SPRING_SECURITY_CONTEXT)
                                |
                                v
                      SecurityContext X
                    authentication=ROLE_USER
                          ^            ^
                          |            |
                 Thread A holder   Thread B holder
                 (request A)       (request B)
                   slot riêng       slot riêng
                          |            |
                          +--> cùng X <-+
~~~

`ThreadLocal` hoạt động đúng: slot A và slot B tách biệt. **Object X lại được chia sẻ.** Khi A gọi `X.setAuthentication(ROLE_ADMIN)`, B có thể thấy `ROLE_ADMIN` khi đọc X sau đó, dù B không gọi `SecurityContextHolder.setContext`.

Đây là vấn đề **object aliasing** (nhiều tham chiếu tới cùng object) và **mutability**, không phải bằng chứng ThreadLocal bị lỗi hoặc các request luôn chia sẻ thread.

## 3. Tình huống phổ biến làm hai request cùng giữ context

Một session thường được dùng chung bởi nhiều tab, request nền, AJAX calls và HTTP/2 multiplexing. Ví dụ:

~~~text
09:00:00.000 Session chứa X, Authentication=ROLE_USER
09:00:00.010 Request A: POST /step-up, tải X
09:00:00.020 Request B: GET /transfer, tải X
09:00:00.030 Request B: filter xác định user=linh, ROLE_USER
09:00:00.040 Request A: step-up đã được xác minh
09:00:00.050 Request A: getContext().setAuthentication(authMới)
09:00:00.060 Request B: service đọc lại context -> có thể thấy authMới
~~~

Việc authentication mới có thể hợp lệ không làm hành vi trên đúng về mặt kiến trúc: B bắt đầu một tác vụ với một snapshot, nhưng giữa quá trình logic bản identity bị mutate gián tiếp. Nếu B có nhiều lớp authorization/checks, chúng có thể quan sát trạng thái khác nhau trong cùng request.

Tác động có thể gồm:

- Phân quyền không nhất quán giữa web filter và method security.
- Principal/tenant context thay đổi trong một request đang xử lý.
- Các log/audit ghi identity không khớp với identity được dùng ở bước trước.
- Race condition rất khó tái hiện vì thứ tự threads và requests không cố định.
- Một ứng dụng đang chạy đúng trong một JVM có thể đổi behavior sau khi chuyển session sang Redis hoặc có nhiều nodes.

**Không kết luận mọi session backend đều trả cùng object.** Với session serialization hoặc distributed store, hai request có thể nhận hai bản copy; khi đó vẫn còn vấn đề **stale update/last-write-wins**, dù không có object alias giữa threads. Code nên an toàn trong cả hai tình huống.

## 4. Đoạn code sai và cách thay thế

### 4.1. Cách sửa trực tiếp đối tượng đã có

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

// Nguy cơ: context hiện tại có thể cùng reference với session.
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

`getContext()` trả context **đang được holder giữ**, có thể là object đã tải từ session. `setAuthentication(...)` mutate object đó tại chỗ.

Một side effect tinh vi: khi session lưu trực tiếp reference X trong một JVM, mutate X cũng đồng nghĩa nội dung được tham chiếu từ session đã đổi **dù chưa gọi `saveContext`**. Điều này **không phải** cơ chế persistence đúng: một session backend khác có thể serialize/deep-copy dữ liệu, không nhìn thấy mutation đến khi save. Không thiết kế code dựa vào việc “nó tự được lưu” như vậy.

### 4.2. Cách tạo context mới

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

// Không sửa context đã load từ session.
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);

// Chỉ thay context của holder hiện tại.
SecurityContextHolder.setContext(fresh);
~~~

Ba điểm then chốt:

1. `AuthenticationManager.authenticate(...)` phải trả result trusted; không cho HTTP body tự cấp `isAuthenticated=true` hoặc tự chọn authorities.
2. `createEmptyContext()` cho một object khác context đang giữ.
3. `setContext(fresh)` thay reference của holder hiện tại; request khác đang giữ object cũ không bị thay trạng thái **trực tiếp**.

Cách này cô lập **việc thay container SecurityContext**. Nó chưa đồng nghĩa đã tách sâu toàn bộ principal/Authentication, chưa persist session và chưa xử lý thứ tự hai request cùng save.

### 4.3. Tạo mới rồi lưu khi dùng session-based custom login

~~~java
Authentication verified =
        authenticationManager.authenticate(requestAuthentication);

SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);
SecurityContextHolder.setContext(fresh);

securityContextRepository.saveContext(fresh, request, response);
~~~

Đây là **snippet tích hợp Servlet**, cần có `AuthenticationManager`, `SecurityContextRepository`, `HttpServletRequest`, `HttpServletResponse` và flow hoàn chỉnh trong ứng dụng Spring Security. Với login custom, còn phải thực thi session fixation protection/`SessionAuthenticationStrategy`, CSRF, success/failure handlers và policy liên quan. Đừng coi những dòng trên là authentication endpoint production hoàn chỉnh.

## 5. Cơ chế Spring Security Servlet liên quan

Spring Security có một số thành phần cần phân biệt:

~~~text
Request HTTP
     |
     v
SecurityContextHolderFilter
     |
     v
SecurityContextRepository
     +--> RequestAttributeSecurityContextRepository
     +--> HttpSessionSecurityContextRepository
     |
     v
SecurityContextHolder (mặc định ThreadLocal)
     |
     v
Authentication của request
     |
     v
Controller / Security annotations / Service
     |
     v
Khi thay Authentication: createEmptyContext -> setContext
     |
     v
Khi cần persist: SecurityContextRepository.saveContext(...)
     |
     v
Response, filter dọn holder
~~~

- `SecurityContextHolderFilter` thường tải/defer-load context vào holder và dọn sau request.
- `SecurityContextRepository` định nghĩa cơ chế lưu/tải; nó không phải `AuthenticationManager`.
- `HttpSessionSecurityContextRepository` dùng server-side `HttpSession` để hỗ trợ authenticated state giữa HTTP requests.
- `RequestAttributeSecurityContextRepository` giúp giữ context trong phạm vi cùng Servlet request/dispatch.
- `NullSecurityContextRepository` không lưu context sang request khác; hợp với stateless policy khi được cấu hình tương ứng.
- `DelegatingSecurityContextRepository` thường phối hợp request attribute và HTTP session trong Spring Security 6 Servlet.

**Nguồn gốc của shared object:** nhiều request thuộc **cùng HTTP session** có thể được load từ cùng một server-side context. Nếu thread A và B cùng giữ reference, đừng mutate object đó.

## 6. Explicit save của Spring Security 6

### 6.1. Mô hình cũ: implicit save

Trong cách cấu hình Spring Security 5 dùng `SecurityContextPersistenceFilter`, framework có thể tự theo dõi/ngầm persist context khi response được hoàn tất. Vì vậy, một đoạn code cũ chỉ gọi `SecurityContextHolder.setContext(...)` đôi lúc vẫn có hiệu lực ở request sau.

### 6.2. Mô hình Spring Security 6: explicit save

`SecurityContextHolderFilter` trong cấu hình Spring Security 6 mặc định **đọc và dọn**, nhưng không tự lưu mọi thay đổi của holder. Khi custom filter/controller login quyết định lưu identity cho request sau, phải làm bước:

~~~java
securityContextRepository.saveContext(
        newContext, httpServletRequest, httpServletResponse);
~~~

Nếu tạo new context mà quên save, request hiện tại có thể nhận authenticated `Authentication` nhưng request sau không có session context và trả 401.

**Thứ tự quan trọng:**

~~~text
authenticate -> session strategy -> createEmptyContext
             -> setAuthentication -> setContext
             -> saveContext -> redirect / commit response
~~~

Save trước redirect/response commit vì repository có thể cần thao tác với session và cookie khi response chưa committed.

**Không** thêm cả `SecurityContextPersistenceFilter` và `SecurityContextHolderFilter` vào cùng một chain để cố có cả implicit lẫn explicit behavior. Khi nâng cấp framework, dùng chiến lược migration phù hợp.

### 6.3. Form login chuẩn khác custom login

Nếu bạn dùng `http.formLogin(...)` với các filter mặc định, Spring Security đã tổ chức vòng đời context/session tương ứng. **Không cần** mỗi controller tự save context.

Các cảnh báo trong bài chủ yếu hướng tới:

- Custom login controller/filter.
- Xử lý step-up/reauth hoặc controlled switch-user.
- Code tự xây authentication flow.
- Code thay `Authentication` trong scope của request.
- Các test dùng holder trực tiếp.

## 7. Ví dụ Java 17 chạy được: chứng minh shared reference qua hai threads

Ví dụ này dùng **Spring Security Core 6.5.11** và `CountDownLatch`. Nó **không** chạy Servlet container, không lưu session thật, không xác minh mật khẩu. Hai threads được chủ động cấp cùng context để mô phỏng phần object-sharing có thể xuất hiện khi cùng session phục vụ nhiều requests.

Phần 1 tái hiện cách **không nên** dùng `getContext().setAuthentication(...)`. Phần 2 tạo context mới và minh họa thay reference trong nơi lưu giả lập.

### 7.1. Cấu trúc

~~~text
security-context-copy-demo/
├── build.gradle
└── src/main/java/demo/ContextCopyDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.ContextCopyDemo'
}
~~~

**File `src/main/java/demo/ContextCopyDemo.java`:**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextCopyDemo {

    private static Authentication trustedForDemo(String authority) {
        // Chỉ mô phỏng auth đã được xác minh, KHÔNG dùng với dữ liệu client.
        return UsernamePasswordAuthenticationToken.authenticated(
                "linh", null,
                List.of(new SimpleGrantedAuthority(authority)));
    }

    private static SecurityContext contextWith(String role) {
        SecurityContext result = SecurityContextHolder.createEmptyContext();
        result.setAuthentication(trustedForDemo(role));
        return result;
    }

    private static String role(SecurityContext context) {
        return context.getAuthentication().getAuthorities()
                .iterator().next().getAuthority();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // 1. Hai request giả lập cùng giữ một object context.
        SecurityContext shared = contextWith("ROLE_USER");
        CountDownLatch bRead = new CountDownLatch(1);
        CountDownLatch aMutated = new CountDownLatch(1);
        AtomicReference<String> bBefore = new AtomicReference<>();
        AtomicReference<String> bAfter = new AtomicReference<>();

        Thread requestB = new Thread(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                bBefore.set(role(SecurityContextHolder.getContext()));
                bRead.countDown();
                await(aMutated);
                bAfter.set(role(SecurityContextHolder.getContext()));
            } finally {
                SecurityContextHolder.clearContext();
            }
        }, "request-B");

        Thread requestA = new Thread(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                await(bRead);
                // Sai cho production: sửa trực tiếp object B đang giữ.
                SecurityContextHolder.getContext()
                        .setAuthentication(trustedForDemo("ROLE_ADMIN"));
            } finally {
                aMutated.countDown();
                SecurityContextHolder.clearContext();
            }
        }, "request-A");

        requestB.start();
        requestA.start();
        requestB.join();
        requestA.join();

        System.out.println("unsafe.before=" + bBefore.get());
        System.out.println("unsafe.after=" + bAfter.get());

        // 2. Nơi lưu GIẢ LẬP một session, không phải Servlet HttpSession.
        AtomicReference<SecurityContext> simulatedSession =
                new AtomicReference<>(contextWith("ROLE_USER"));

        SecurityContext aLoaded = simulatedSession.get();
        SecurityContext bLoaded = simulatedSession.get();
        SecurityContextHolder.setContext(aLoaded);

        SecurityContext newContext =
                SecurityContextHolder.createEmptyContext();
        newContext.setAuthentication(trustedForDemo("ROLE_EDITOR"));
        SecurityContextHolder.setContext(newContext);

        System.out.println("safe.isNewObject="
                + (newContext != bLoaded));
        System.out.println("safe.holder=" + role(SecurityContextHolder.getContext()));
        System.out.println("safe.otherBeforeSave=" + role(bLoaded));
        System.out.println("safe.storeBeforeSave="
                + role(simulatedSession.get()));

        // Chỉ MÔ PHỎNG thao tác thay context lưu của repository.
        simulatedSession.set(newContext);

        System.out.println("safe.storeAfterSave="
                + role(simulatedSession.get()));
        System.out.println("safe.otherAfterSave=" + role(bLoaded));

        SecurityContextHolder.clearContext();
        System.out.println("safe.holderEmpty="
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));
    }
}
~~~

### 7.2. Lệnh chạy

Dùng JDK 17+ và Gradle tương thích, từ thư mục `security-context-copy-demo`:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper: `./gradlew -q run`; Windows: `gradlew.bat -q run`. Lần đầu có thể cần tải dependencies.

**Stdout do chính chương trình in** (không kể log Gradle/thư viện nếu được bật):

~~~text
unsafe.before=ROLE_USER
unsafe.after=ROLE_ADMIN
safe.isNewObject=true
safe.holder=ROLE_EDITOR
safe.otherBeforeSave=ROLE_USER
safe.storeBeforeSave=ROLE_USER
safe.storeAfterSave=ROLE_EDITOR
safe.otherAfterSave=ROLE_USER
safe.holderEmpty=true
~~~

### 7.3. Giải thích chính xác output

- `unsafe.before=ROLE_USER`: request B đọc role trước.
- `unsafe.after=ROLE_ADMIN`: nhờ `CountDownLatch`, B đọc lại sau khi request A mutate **chung object**. Kết quả tái lập ổn định, không phải do B tự đổi ThreadLocal.
- `safe.isNewObject=true`: `createEmptyContext()` trả về object khác với context B đang giữ.
- `safe.holder=ROLE_EDITOR`: holder của luồng hiện tại đã trỏ đến object mới.
- `safe.otherBeforeSave=ROLE_USER` và `safe.storeBeforeSave=ROLE_USER`: context cũ không bị mutate.
- `simulatedSession.set(newContext)` **chỉ mô phỏng** `saveContext`; nó không tạo session cookie hay làm Servlet repository thật.
- `safe.storeAfterSave=ROLE_EDITOR`: request mới lấy reference lưu sau thay thế có thể nhận role mới.
- `safe.otherAfterSave=ROLE_USER`: B đang giữ snapshot cũ, không bị A thay đổi nội tại.
- `safe.holderEmpty=true`: xóa holder hiện tại không đồng nghĩa xóa session store.

**Không kết luận tạo context mới tự thu hồi các phiên đã phát hành.** Demo chỉ kiểm tra object aliasing và replacement. Production cần integration tests với SecurityFilterChain, SessionAuthenticationStrategy, repository và session backend thật.

## 8. Cùng một session có thể chịu hai loại race khác nhau

### 8.1. Shared-object mutation

~~~text
Session S -> SecurityContext X
Request A -> X
Request B -> X
A: X.setAuthentication(AUTH_NEW)
B: thấy AUTH_NEW không chủ đích
~~~

Giải pháp chính: **new context** cho việc thay Authentication, không sửa X.

### 8.2. Last-write-wins dù hai request đều tạo object mới

~~~text
Session S -> X
A tạo YA từ identity đã xác minh
B tạo YB từ identity đã xác minh
A saveContext(YA)
B saveContext(YB)
Session có thể lưu YB
~~~

Không còn mutate cùng object, nhưng vẫn có **concurrent writes**. Nếu B dựa trên snapshot cũ, nó có thể ghi đè cập nhật của A. Giải pháp cần thêm:

- Giới hạn các điểm có thể lưu/thay identity.
- Kiểm soát session generation/version ở nơi nhạy cảm.
- Dùng session invalidation/rotation khi đổi identity và policy yêu cầu.
- Đối chiếu `authVersion`/account status với nguồn đáng tin khi thao tác có rủi ro cao.
- Với distributed session store, kiểm tra CAS/locking/serialization semantics thực tế.
- Test hai request cùng session cùng lúc và các request đang chạy khi bị logout/thu hồi quyền.

**Tạo mới context xử lý alias mutation; nó không tự mang transaction isolation tới mọi repository.**

## 9. Tạo context mới và tạo Authentication mới là hai việc khác nhau

Đoạn sau không mutate context cũ:

~~~java
SecurityContext prior = SecurityContextHolder.getContext();
SecurityContext next = SecurityContextHolder.createEmptyContext();
next.setAuthentication(prior.getAuthentication());
SecurityContextHolder.setContext(next);
~~~

Nhưng **`Authentication` có thể vẫn là cùng một object** mà context cũ và mới cùng trỏ tới. Nếu implementation/principal/details mutable, việc mutate bên trong nó có thể vẫn ảnh hưởng bên còn lại.

Một cách tách trách nhiệm:

- **Container mới:** gọi `createEmptyContext()` để không làm bẩn context chung.
- **Authentication mới:** lấy result từ `AuthenticationManager`, identity provider đã được xác minh hoặc luồng reauthentication/step-up đáng tin.
- **Principal rõ ràng:** không dùng JPA entity lớn/`UserDetails` mutable từ cache theo thói quen.
- **Authorities đáng tin:** luôn do server/IdP đã được xác minh cấp, không chuyển nguyên từ JSON client vào authenticated token.
- **Save đúng scope:** chỉ persist khi policy session yêu cầu.

**Không có một hàm deep-copy Authentication chung** an toàn cho mọi subclass. Serialization/deep-copy bằng reflection có thể làm lộ credentials, sai authorities hoặc lỗi với Hibernate proxy.

## 10. Tạm thời dùng một context khác trong trusted scope

Đôi khi code server cần chạy một đoạn ngắn với `Authentication` khác đã được cấp **hợp lệ** (ví dụ hệ thống job nội bộ kiểm soát chặt). Tránh mutate context trước đó:

~~~java
// MÃ MINH HỌA trong component đáng tin, không standalone.
SecurityContext previous =
        securityContextHolderStrategy.getContext();

SecurityContext temporary =
        securityContextHolderStrategy.createEmptyContext();
temporary.setAuthentication(trustedAuthenticationForScope);

try {
    securityContextHolderStrategy.setContext(temporary);
    runAuthorizedScopedOperation();
} finally {
    securityContextHolderStrategy.setContext(previous);
}
~~~

Đây là **scope tạm**. Không `saveContext(temporary, ...)` trừ khi thật sự muốn thay identity trong session theo một use case được authorize rõ ràng.

Không dùng mẫu này để nâng quyền tự phát: `trustedAuthenticationForScope` phải là kết quả được cấp bởi cơ chế đáng tin, và operation phải được authorize. Trong async/thread pool, `ThreadLocal` phải được propagate/clear bằng cơ chế được hỗ trợ; một block `try/finally` trên thread hiện tại không tự bảo vệ mọi worker thread khác.

## 11. Step-up, account switching và login lại

Có các use case hợp lệ cần thay Authentication:

| Use case | Khi nào tạo context mới? | Còn cần điều gì? |
| --- | --- | --- |
| Form login lần đầu | Sau khi AuthenticationManager/provider xác thực | Session fixation, save đúng repo, success/failure handlers |
| Reauthentication | Khi credential được xác minh lại | Xác định session và thời điểm quyền có hiệu lực |
| MFA/step-up | Sau bước kiểm chứng mạnh hơn | Giới hạn thời hạn step-up, audit và policy rõ ràng |
| Controlled switch-user | Sau khi actor được authorize | Ghi nhớ actor thật, audit, không lẫn tenant/scope |
| Logout | Khi clear authenticated state | Logout handlers, invalidate/save empty context và token policy |
| Stateless token per request | Khi filter xác thực token | Không persist session nếu session policy là STATELESS |

**Không nên thay context mới trên mọi request chỉ để lấy username.** Việc đọc bình thường:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

là hợp lệ khi kết hợp kiểm tra authenticated/anonymous và authorization đúng. Tạo context mới dành cho các **thao tác thay identity**, không phải yêu cầu cho mọi controller/service đọc principal.

## 12. Logout: clear holder không đủ, mutate object cũ cũng không đúng

Sai lầm:

~~~java
SecurityContextHolder.getContext().setAuthentication(null);
~~~

Nếu context đang chia sẻ với session và request khác, thao tác này có thể mutate object chung. Đồng thời nó không tự đảm bảo session đã invalidated hoặc refresh token/JWT hết hiệu lực.

Đối với Spring Security Servlet, ưu tiên `LogoutFilter` và `SecurityContextLogoutHandler`, vì logout còn phải xử lý:

- Holder hiện tại.
- `SecurityContextRepository` / HTTP session.
- Session cookie, CSRF/remember-me và các logout integrations được cấu hình.
- Các session hoặc token khác theo chính sách riêng.

Một custom logout cần hiểu cơ chế **lưu context trống/invalidate session** và thứ tự với response, không chỉ `clearContext`. `SecurityContextHolder.clearContext()` đơn thuần dọn slot hiện tại; nếu session vẫn chứa authentication cũ, request sau có thể lại khôi phục identity.

JWT stateless là câu chuyện khác: xóa session context không tự thu hồi token đã ký. Cần TTL, denylist/version/introspection hoặc refresh token revocation theo risk policy.

## 13. UserDetails, cache và nested mutable references

Một `SecurityContext` mới chưa có nghĩa **mọi object bên trong độc lập**:

~~~text
SecurityContext A -> Authentication A -> Principal U
SecurityContext B -> Authentication B -> Principal U
                                            |
                                      shared object
~~~

Nếu `Principal U` là một JPA entity mutable hoặc `UserDetails` lấy từ cache, việc đổi attributes/roles/password hash có thể ảnh hưởng nhiều contexts.

Spring Security `ProviderManager` còn có hành vi `eraseCredentials()` trên authentication result khi được cấu hình mặc định. Nếu principal dùng chung object `UserDetails` với cache, xóa credential trong result có thể làm mất hash ở cache.

Nguyên tắc:

- Trả `UserDetails`/principal nhỏ, riêng biệt cho auth, không nguyên entity nghiệp vụ phức tạp.
- Không chia sẻ mutable `Authentication`/principal object qua requests khi có thể tránh.
- Nếu sử dụng caching, phân biệt object cache và object principal, thiết kế credential erasure đúng.
- Đừng dùng username/tenant từ request chưa xác minh làm khóa lấy principal cao quyền.
- Khi data/roles thay đổi, dùng service/DB, kiểm quyền mới và session invalidation theo policy; không chỉnh tại chỗ `principal.getAuthorities()` rồi tin mọi request đã được cập nhật.

## 14. Async, ThreadLocal và context propagation

Mặc định `SecurityContextHolder` dùng `MODE_THREADLOCAL`. Một task từ `@Async`/`ExecutorService` chạy ở thread khác **không tự có** context của thread gọi. Spring Security có `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và integrations khác.

Khi propagate:

- Phân biệt **truyền reference tới context** với tạo snapshot độc lập.
- Nếu task nhận cùng mutable context và thread gốc mutate, có thể xuất hiện aliasing tương tự.
- Dùng context mới/trusted snapshot hoặc truyền stable userId rồi reauthorize trong task tùy use case.
- Đảm bảo `clearContext()` sau task bằng cơ chế wrapper/finally đáng tin.
- Không dùng `MODE_GLOBAL` cho web server đa người dùng.
- `MODE_INHERITABLETHREADLOCAL` không tự xử lý đúng thread pool tái sử dụng.

**Không tự dùng static `Authentication currentUser`** như bộ nhớ chia sẻ user toàn JVM; sẽ trộn identity giữa khách hàng.

## 15. SessionCreationPolicy và phạm vi context

| Chính sách / repository | Có thể giữ context sang request sau? | Điểm liên quan |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Có nếu session còn hợp lệ và save đúng | Có thể chia sẻ object ở cùng JVM; dùng fresh context khi thay auth |
| `RequestAttributeSecurityContextRepository` | Không qua request HTTP hoàn toàn mới | Dùng trong cùng Servlet request/dispatch |
| `NullSecurityContextRepository` | Không | Stateless auth cần chứng cứ mỗi request |
| `DelegatingSecurityContextRepository` | Tùy delegates | Thường kết hợp request attribute và session |
| `SessionCreationPolicy.IF_REQUIRED` | Có thể tạo session khi cần | Thường dùng web login |
| `SessionCreationPolicy.NEVER` | Không chủ động tạo mới bởi Spring Security, nhưng có thể dùng session đã tồn tại | Đừng nhầm với stateless |
| `SessionCreationPolicy.STATELESS` | Không dùng `HttpSession` làm nguồn security context | Phù hợp bearer stateless với config phù hợp |

Một cookie session có thể xuất hiện do `RequestCache` hoặc code ứng dụng khác; không suy ra chỉ `SecurityContextRepository` tạo session.

## 16. Principal bị cũ và quyền không tự đổi

Tạo context mới là kỹ thuật tránh **shared-object mutation**. Nó **không tự bảo đảm**:

- User vừa bị khóa sẽ bị chặn ở tất cả session còn sống.
- Role vừa thu hồi trong DB lập tức biến mất khỏi JWT/session.
- Các requests đã bắt đầu trước lúc quyền đổi bị hủy ngay.
- Hai nodes dùng cùng session store đều thấy cùng snapshot tức thì.
- Object `UserDetails` cache và principal mới có cùng thời điểm cập nhật.

Ví dụ, admin thu hồi `ROLE_ADMIN` nhưng một session cũ còn `Authentication` với authority đó. Repository chỉ có thể tải lại snapshot; không phải nguồn policy mới nhất. Các biện pháp bổ sung: revalidation account status, token/session revocation, `authVersion`, TTL, object-level authorization và session generation theo yêu cầu.

**Đừng cố “cập nhật mọi request” bằng cách mutate một SecurityContext object chung.** Đó là cách sửa lỗi stale roles bằng rủi ro race khác.

## 17. Vì sao synchronized trên context không phải giải pháp chung?

Một số code thử:

~~~java
synchronized (SecurityContextHolder.getContext()) {
    SecurityContextHolder.getContext().setAuthentication(newAuthentication);
}
~~~

Không nên xem đây là giải pháp mặc định, vì:

- Các filters/controllers khác có thể đọc mà không dùng cùng lock.
- Session distributed có thể deserialize thành object khác, mỗi node có lock khác.
- Lock không xử lý write sau/đọc cũ của hai requests khác nhau.
- Có thể gây contention/deadlock nếu business code giữ lock lâu.
- Vẫn mutate object dùng chung, không cải thiện cấu trúc dữ liệu hoặc ownership.

Thay vì cố đồng bộ mọi nơi đang dùng X, **tạo Y mới**, thay reference ở đúng scope và persist có chủ đích. Khi consistency cực kỳ quan trọng, bổ sung policy session/DB version và concurrency control tại nơi lưu.

## 18. Tích hợp nhiều SecurityFilterChain

Một ứng dụng có thể có:

~~~text
/web/**   -> form login + HttpSession
/api/**   -> JWT bearer + stateless
/admin/** -> session + step-up/revalidation
~~~

Đây là thiết kế ví dụ, không phải matcher mặc định của Spring Security. Mỗi chain cần xác định:

- Filter/`AuthenticationManager` nào thực sự xác minh credential.
- `SecurityContextRepository` nào được holder filter và auth filter sử dụng.
- `SessionCreationPolicy` và `RequestCache` nào có hiệu lực.
- Custom login ở đúng chain hay không.
- Có vô tình lấy session auth ở một API dự định chỉ chấp nhận bearer token không.
- Khi identity đổi, repository lưu cho đúng scope hay lại dùng instance khác.

**Tạo context mới đúng nhưng save vào repository mà filter không dùng** sẽ dẫn đến request sau không thấy identity. Kiểm thử qua URL/filter chain thực, không chỉ gọi một method trực tiếp trong unit test.

## 19. Debug những lỗi thực tế

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai tabs thấy principal/role đổi giữa request | Context shared và bị mutate tại chỗ | Fresh context + setContext |
| Login hiện tại thành công, request sau trả 401 | Custom login chưa save context | `SecurityContextRepository.saveContext` trước redirect |
| Chuyển Redis xong “tự ghi” không còn hoạt động | Trước đó dựa vào alias object trong local session | Explicit save; test session backend |
| Request B ghi đè session của A dù cả hai tạo context mới | Last-write-wins | Session generation/version/revalidation |
| `@Async` mất identity | ThreadLocal không tự propagation | DelegatingSecurityContext executor hoặc boundary có userId |
| Task async thấy identity thay đổi | Truyền cùng mutable context/auth | Snapshot trusted và cleanup đúng |
| Principal hash trong cache biến mất | `eraseCredentials()` ảnh hưởng shared UserDetails object | Tách cached object và principal |
| Logout `clearContext` nhưng request sau vẫn authenticated | Session repository còn context | Logout support/invalidate/save empty |
| Role DB đã gỡ nhưng session vẫn ADMIN | Authentication snapshot cũ | Revalidation/revoke/refresh theo policy |
| “New context” nhưng principal vẫn bị thay | Cùng `Authentication`/JPA entity mutable được share | Tách nested objects/trusted authentication |
| Static context bị dùng cho toàn app | Cross-user contamination | Không dùng global mutable identity |
| Custom filter tạo authenticated token từ request | Bypass authentication | Authenticate qua manager/provider |
| Thay strategy global giữa lúc request đang chạy | Context holder strategy race | Inject strategy nhất quán |
| Save sau `sendRedirect` | Response đã committed | Save trước response commit |
| Chỉ dùng request attribute nhưng muốn nhớ login | Repo không tồn tại qua request mới | Dùng session repository nếu stateful |
| Stateless dùng cookie/session auth cũ | Chain/session policy sai | `STATELESS` và token validation đúng |

## 20. Kiểm thử concurrency một cách xác định

**Không** chỉ chạy một request login rồi kết luận không có race. Cần:

1. Seed một session với authenticated context hợp lệ.
2. Tạo hai requests **đồng thời** có cùng session ID.
3. Đặt test barrier/`CountDownLatch` để request B đọc context trước khi A thực hiện thay Authentication.
4. Nếu code dùng cách cũ, xác minh B có thể thấy Authentication thay đổi ngoài ý muốn; sau khi refactor, B giữ snapshot cũ trong request đang chạy.
5. Khi A save context mới, xác minh request C mới thấy identity theo policy.
6. Khi hai requests đều save, kiểm tra thứ tự và stale update.
7. Kiểm thử servlet session fixation, logout, redirects, session cookies và store phân tán.
8. Với `@Async`, test propagation/cleanup để không lẫn identity giữa các tasks.
9. Kiểm tra còn shared mutable principal/authorities hay không.
10. Khi role bị revoke, đo request bị chặn theo security SLO, không chỉ nhìn context object.

### Integration test qua MockMvc

Đây là **pseudocode**, không phải JUnit độc lập:

~~~java
// Test chạy qua SecurityFilterChain thật với user và config đã seed.
MvcResult login = mvc.perform(
        formLogin().user("linh").password("correct-password"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) login.getRequest().getSession(false);

// Hai request dùng session và latches/barriers trong test service.
// Không dùng Thread.sleep để “may ra” tạo race.
// Kiểm tra role trong B không bị A mutate trước một bước
// reauthentication hoặc session update có chủ ý.
~~~

Nếu session đã invalidated, không tiếp tục truyền object cũ cho request mới; mô phỏng đúng cookie và lifecycle. Với MockMvc không đủ để xác minh store phân tán/multi-node, cần integration test có backend session thật.

## 21. Checklist code review

1. Thay Authentication trong custom Servlet logic có dùng **`createEmptyContext()`** không?
2. Có dùng **`setContext(newContext)`** thay vì sửa object holder hiện tại không?
3. `Authentication` mới có được cấp từ **trusted provider/manager**, không từ role/client payload không?
4. Khi cần session, có **`saveContext(newContext, request, response)`** trước commit không?
5. Custom login có đúng `SessionAuthenticationStrategy`/session fixation/CSRF/success handling không?
6. Holder và repository có dùng cùng `SecurityContextHolderStrategy`/chain không?
7. Có tách `Authentication`/principal mutable khỏi object cache hoặc JPA entity không?
8. Có test hai requests **cùng session** chạy đồng thời không?
9. Có xử lý **last-write-wins** khi hai requests cùng save và vai trò bị revoke không?
10. Có logout support đúng thay vì chỉ mutate context thành null không?
11. Có chính sách authority freshness/account state và token/session revocation không?
12. Có cleanup holder sau custom filter/async tasks không?
13. Có tránh static/global authenticated user không?
14. Có tránh log full `SecurityContext`, credentials, cookie/token không?
15. Có test đa chain, session backend khác nhau và request sau redirect không?

## 22. Câu hỏi tự kiểm tra

**Câu 1.** `ThreadLocal` có nghĩa mỗi request có một `SecurityContext` object riêng?  
**Đáp:** Không. ThreadLocal tách vị trí lưu reference; hai requests có thể giữ cùng object lấy từ một session.

**Câu 2.** Vì sao `getContext().setAuthentication(auth)` có rủi ro?  
**Đáp:** Nó mutate object hiện tại. Nếu object được chia sẻ, request khác có thể thấy principal/role đổi giữa chừng.

**Câu 3.** Pattern thay Authentication đúng là gì?  
**Đáp:** Xác thực qua manager/provider → `createEmptyContext()` → `setAuthentication(verified)` → `setContext(newContext)`.

**Câu 4.** Spring Security 6 custom login set context mới có tự persist qua request sau không?  
**Đáp:** Không mặc định với `SecurityContextHolderFilter`. Cần `SecurityContextRepository.saveContext(...)` nếu muốn giữ session.

**Câu 5.** B đang giữ X, A setContext(Y) và save Y. B có tự đổi sang Y không?  
**Đáp:** Không. B có thể tiếp tục giữ X trong request đang chạy; request sau có thể tải Y.

**Câu 6.** New context nhưng dùng `oldContext.getAuthentication()` có độc lập sâu không?  
**Đáp:** Không. `Authentication` và principal vẫn có thể được share.

**Câu 7.** Vì sao không thể chữa race bằng `synchronized` cục bộ quanh getContext?  
**Đáp:** Nhiều code paths/nodes không cùng lock, và last-write-wins ở session không được xử lý.

**Câu 8.** Có được tạo authenticated token với role từ JSON request chưa xác minh không?  
**Đáp:** Không. Không bypass `AuthenticationManager`/provider và authorization.

**Câu 9.** Thay role trong DB rồi có thể gọi context setter để cập nhật mọi request đang chạy không?  
**Đáp:** Không. Cần session/token revocation, refresh/revalidation và chính sách nhất quán riêng.

**Câu 10.** Demo với `CountDownLatch` đang mô phỏng điều gì?  
**Đáp:** Hai ThreadLocal giữ cùng reference; A mutate object, B nhìn thấy thay đổi. New context thì chỉ thay reference của scope hiện tại.

**Câu 11.** Khi nào không phải tạo context mới?  
**Đáp:** Khi chỉ đọc principal/authorities ở controller/service và không thay Authentication.

**Câu 12.** Logout chỉ `SecurityContextHolder.clearContext()` đã đủ chưa?  
**Đáp:** Không. Session repository, cookies và token có thể vẫn tồn tại; dùng logout support và revocation policy.

## 23. Tài liệu tham khảo

- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): khuyến nghị dùng `createEmptyContext` thay vì `getContext().setAuthentication` để tránh race; `SecurityContextHolder` và `Authentication`.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): holder strategy, session semantics, custom authentication và explicit save.
- [Spring Security 6.5 – Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): các loại `SecurityContextRepository`.
- [Spring Security 6.5 – Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): `SecurityContextPersistenceFilter` so với `SecurityContextHolderFilter`, `requireExplicitSave`.
- [Spring Security 6.5 – SecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `createEmptyContext`, `setContext`, `getContext`, `clearContext`.
- [Spring Security 6.5 – SecurityContextRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `saveContext` và vòng đời persistence.
- [Spring Security 6.5 – SecurityContextHolderStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolderStrategy.html): sử dụng strategy nhất quán.
- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `SessionAuthenticationStrategy` và luồng login Servlet.
- [Spring Security 6.5 – Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): propagation context sang threads.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session cleanup và logout handlers.

**Ghi nhớ:** `ThreadLocal` không làm object trở thành riêng tư. Khi thay identity ở Servlet, dùng **`SecurityContextHolder.createEmptyContext()` → `setAuthentication(verified)` → `SecurityContextHolder.setContext(fresh)`**, rồi **`SecurityContextRepository.saveContext(...)`** nếu cần session. Cách này ngăn tác động phụ do mutate cùng object; **concurrent session writes, mutable principal và revocation vẫn phải giải quyết riêng**.
