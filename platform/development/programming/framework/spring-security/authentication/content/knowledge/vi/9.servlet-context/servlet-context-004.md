# SecurityContextRepository: tải, lưu và phạm vi tồn tại của ngữ cảnh

**Module:** Spring Security – authentication. **Chủ đề cha:** Ngữ cảnh Servlet.

## 1. Vấn đề: login thành công trong request hiện tại nhưng request sau lại bị 401

Một tình huống phổ biến khi lập trình Spring Boot Servlet:

~~~java
Authentication verified = authenticationManager.authenticate(token);
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

Trong **request hiện tại**, code bên dưới có thể nhìn thấy `Authentication` vừa được gán. Nhưng browser gửi `GET /profile` ở request kế tiếp lại bị coi là chưa đăng nhập.

Tại sao? Vì **`SecurityContextHolder` và `SecurityContextRepository` không làm cùng một việc**:

- `SecurityContextHolder` giữ `SecurityContext` **đang dùng trong luồng xử lý hiện tại** (mặc định qua `ThreadLocal` trên Servlet stack).
- `SecurityContextRepository` định nghĩa **nơi lấy lại và nơi lưu** context để có thể sử dụng trong một lần xử lý tiếp theo, tùy implementation: request attribute, `HttpSession` hoặc không lưu.
- `SecurityContextHolderFilter` đọc repository để cung cấp context cho request và dọn holder khi xử lý xong. Trong Spring Security 6, filter này **không tự động ghi mọi thay đổi** của holder xuống repository.
- Một authentication mechanism tích hợp sẵn, như form login được cấu hình đúng, có thể **chủ động lưu context khi đăng nhập thành công**. Khi tự viết filter/controller login, lập trình viên cần thực hiện bước lưu nếu muốn giữ đăng nhập qua nhiều request.

**Nguyên tắc trọng tâm: đặt `Authentication` vào holder chỉ ảnh hưởng context đang sử dụng; muốn nó tồn tại sau request phải lưu đúng repository, đúng thời điểm và đúng chính sách session.**

Không được nhầm “dữ liệu user vẫn còn trong database” với “browser còn session đã xác thực”: kho tài khoản không thay thế việc gắn `Authentication` vào request sau.

## 2. Tách bốn vai trò trước khi đọc code

| Thành phần | Chức năng | Mục tiêu lưu trữ/vòng đời |
| --- | --- | --- |
| `Authentication` | Principal, authorities, credentials/details và trạng thái đã xác thực | Một kết quả xác thực cụ thể; có thể được đặt trong context |
| `SecurityContext` | Container chứa `Authentication` hiện tại | Đại diện danh tính bảo mật tại thời điểm xử lý |
| `SecurityContextHolder` | Cho code đang chạy lấy/đặt context qua một `SecurityContextHolderStrategy` | Thường là **ThreadLocal của luồng xử lý request**, không phải database hay session |
| `SecurityContextRepository` | Tải/lưu context theo request/response và backend | Có thể là request attribute, `HttpSession`, custom store hoặc không lưu |
| `SecurityContextHolderFilter` | Kết nối repository với holder trong Servlet filter chain | Đọc trước controller và dọn holder sau request; **không tự persist** |
| `SecurityContextPersistenceFilter` | Lối xử lý cũ có thể tự lưu context khi request kết thúc | Chủ yếu cần hiểu để migrate ứng dụng cũ; **không đặt chung** với HolderFilter |

Hình dung:

~~~text
Browser ---- HTTP REQUEST ----> Spring Security Filter Chain
                                   |
                                   v
                          SecurityContextHolderFilter
                                   |
                  loadDeferredContext(request)
                                   |
                                   v
                      SecurityContextRepository
                        |            |
                        |            +--> HttpSession (nếu cấu hình)
                        +--> request attribute
                                   |
                                   v
                      SecurityContextHolder (ThreadLocal)
                                   |
                                   v
                      Controller/Service/Authorization
                                   |
                           Authentication verified
                                   |
                      setContext + saveContext
                                   |
                                   v
                      SecurityContextRepository
                                   |
                         dùng lại ở request sau
                                   |
                            finally: clear holder
~~~

**Ý nghĩa:** Holder là “điểm truy cập nội bộ theo ngữ cảnh xử lý”; repository là “chiến lược tải và lưu”. `saveContext` không làm cho `SecurityContext` trở thành dữ liệu nghiệp vụ, và `loadDeferredContext` không xác thực lại raw password mỗi lần theo mặc định.

## 3. API SecurityContextRepository: ba phương thức hiện đại và một phương thức cũ

Package: `org.springframework.security.web.context`. Giao diện `SecurityContextRepository` trong Spring Security **6.5.11** có các thành viên quan trọng:

~~~java
// Các chữ ký API được rút gọn để học, không phải class standalone.
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);

// API legacy/deprecated:
SecurityContext loadContext(HttpRequestResponseHolder holder);
~~~

**Lưu ý:** `loadDeferredContext` là default method trong interface và trả `DeferredSecurityContext`; `loadContext(HttpRequestResponseHolder)` đã deprecated. Các class triển khai có thể override cách tải và lưu.

### 3.1. loadDeferredContext(request)

Trả một đối tượng **trì hoãn việc lấy context cho đến khi cần**; nó có method `get()` trả `SecurityContext`, và method `isGenerated()` để biết context có được tạo mới hay không trong API deferred.

~~~java
DeferredSecurityContext deferred =
        repository.loadDeferredContext(request);

SecurityContext context = deferred.get();
~~~

Đây là **snippet minh họa trong ứng dụng Servlet có repository và request**, chưa phải một chương trình Java đầy đủ. Không nên suy ra việc gọi `loadDeferredContext` luôn tức thì đọc `HttpSession`/database; đó là mục đích của deferred loading.

Khi request chưa có ngữ cảnh xác thực, repository trả một **context trống**, không trả null. Nhưng `SecurityContext.getAuthentication()` có thể là null cho request chưa được xác thực.

### 3.2. saveContext(context, request, response)

Yêu cầu repository **lưu** context theo policy của implementation. Đối với session repository, đây có thể là cập nhật thuộc tính trong `HttpSession`; đối với request attribute repo, là đặt attribute trên request; đối với null repo, là no-op.

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);

repository.saveContext(context, request, response);
~~~

Điểm quan trọng: **truyền cả request lẫn response**. Repository có thể cần response để xử lý cam kết HTTP/session cookie. Khi tự viết login Servlet, hãy save **trước khi response bị commit/redirect** để tránh bỏ lỡ `Set-Cookie` hoặc lưu sau khi quá muộn.

### 3.3. containsContext(request)

Trả `true` nếu repository nhận biết có context trong phạm vi liên quan tới request đó. Nó **không phải** API “kiểm tra user đã đăng nhập hợp lệ chưa”.

Ví dụ:

- Request attribute có thể chứa context trống sau khi logout.
- Session có thể có context cũ dù quyền user đã bị thu hồi trong DB.
- Repository có context không có nghĩa user có `ROLE_ADMIN`, chưa hết hạn hay được phép truy cập tài nguyên.
- Một context của authentication mechanism có thể được tạo mới trong request nhưng chưa được lưu.

Để phân quyền, dùng `AuthorizationManager`, `@PreAuthorize`, kiểm tra `Authentication` và các chính sách hiện hành; không dựa vào riêng `containsContext`.

### 3.4. loadContext(...) deprecated

`loadContext(HttpRequestResponseHolder)` liên quan cơ chế load/save implicit và response wrapper của mô hình cũ. Trong Spring Security 6, nên hiểu cách tiếp cận hiện đại là **deferred loading và explicit save**; không viết code mới dựa vào API deprecated chỉ vì thấy nó trong ví dụ Spring Security 5.

## 4. Bốn repository có sẵn: RequestAttribute, HttpSession, Null và Delegating

| Implementation | Lưu ở đâu? | Tồn tại qua request HTTP kế tiếp? | Khi phù hợp |
| --- | --- | --- | --- |
| `RequestAttributeSecurityContextRepository` | Attribute trên đối tượng `ServletRequest` | **Không** khi request kế tiếp là request mới | Giữ context qua các dispatch của **cùng request** (ví dụ error dispatch) |
| `HttpSessionSecurityContextRepository` | Thuộc tính `SecurityContext` trong `HttpSession` | **Có**, nếu browser gửi đúng session ID và session còn hợp lệ | Form login và web dùng HTTP session |
| `NullSecurityContextRepository` | Không lưu | **Không** | API stateless, không muốn security context tồn tại qua request |
| `DelegatingSecurityContextRepository` | Giao nhiều repository theo thứ tự | **Tùy delegates** | Kết hợp request attribute và session |

### 4.1. Mặc định trong Spring Security 6

Spring Security 6 Servlet thường dùng:

~~~java
new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
);
~~~

Đây là **đoạn tạo object minh họa**; cấu hình được Spring Security cung cấp theo mặc định trong luồng session-based, không cần khai báo lại chỉ để “bật đăng nhập qua session”. Thứ tự delegates có ý nghĩa lúc tải context. Khi save, delegating repository phân phối save cho các delegates.

**Hai tầng giúp giải quyết hai nhu cầu khác nhau:**

1. Trong **cùng một request** có nhiều dispatch (`REQUEST`, `ERROR`...), request attribute có thể giúp khôi phục context mà servlet container đã khiến holder bị dọn ở giữa.
2. Giữa **hai HTTP requests độc lập**, `HttpSession` cho phép browser giữ danh tính sau login thành công.

Đừng gọi request attribute là “session không cần cookie”; nó **không sống sang HTTP request mới**.

## 5. RequestAttributeSecurityContextRepository: phạm vi trong một Servlet request

### 5.1. Tại sao cần nó?

Giả sử một request đã xác thực rồi lỗi xảy ra:

~~~text
GET /orders/42 (đã xác thực)
      |
      v
Controller/Filter -> phát sinh exception
      |
      v
Servlet ERROR dispatch
      |
      v
/error được render trong cùng request
      |
      +--> Có thể cần principal để hiển thị/sử dụng policy
~~~

Trong một số cách container xử lý `ERROR` dispatch, `SecurityContextHolder` đã được clear trước khi trang lỗi chạy. Nếu context đã được lưu ở request attribute, repository có thể phục hồi nó trong lần dispatch cùng request.

### 5.2. Những gì request attribute không làm

- Không cấp session cookie.
- Không biến request kế tiếp thành authenticated.
- Không lưu identity trong database hoặc Redis.
- Không bảo đảm mọi filter và dispatch type đều chạy lại theo cùng cách; cấu hình Servlet dispatcher types và filter chain vẫn có ảnh hưởng.
- Không tự kiểm tra password hoặc refresh authorities.

**RequestAttributeSecurityContextRepository là cách giữ dữ liệu theo phạm vi request**, không phải phương án mặc định để “ghi nhớ người dùng đã đăng nhập”.

## 6. HttpSessionSecurityContextRepository: phạm vi nhiều request

### 6.1. Đọc từ session

Khi có session hợp lệ, repository tìm `SecurityContext` đã lưu trong `HttpSession`; key mặc định là `SPRING_SECURITY_CONTEXT`. Nếu không thấy giá trị hợp lệ, nó cung cấp context mới/trống.

Mô tả:

~~~text
POST /login (username/password)
     |
     +--> authenticate() thành công
     +--> saveContext(...) vào HttpSession
     +--> Response có session cookie, ví dụ JSESSIONID

GET /account (trình duyệt gửi lại JSESSIONID)
     |
     +--> SecurityContextRepository tải context từ session
     +--> SecurityContextHolder được populate
     +--> Authorization biết Authentication đã được lưu
~~~

`JSESSIONID` hoặc `SESSION` là **tên cookie phụ thuộc container/Spring Session và cấu hình**; không phải mọi ứng dụng đều dùng cùng một tên. Cookie chỉ mang **session identifier**, không phải nguyên văn `SecurityContext`. Nội dung context được giữ server-side theo session store đang cấu hình.

### 6.2. Không phải cứ loadContext là tạo session

Với `HttpSessionSecurityContextRepository` chuẩn:

- **Đọc** context không tự động tạo session mới nếu chưa có.
- Khi **save** context được coi là đã thay đổi và cần lưu, implementation **có thể tạo session** nếu chưa có, tùy `allowSessionCreation` và security policy.
- Trường hợp context trống hoặc anonymous có thể không cần tạo session; implementation dùng `AuthenticationTrustResolver` để phân biệt anonymous.
- Nếu session creation bị cấm, việc gọi `saveContext` không có nghĩa ép session xuất hiện.
- Một component **khác** của ứng dụng (ví dụ request cache) vẫn có thể tạo session theo chính sách riêng.

Vì vậy, “tôi thấy `HttpSession` được tạo dù đặt `SessionCreationPolicy.NEVER`” không đủ kết luận `SecurityContextRepository` hoạt động sai. Cần xác định bộ phận nào gọi `request.getSession()` hay lưu saved request.

### 6.3. Lưu vào session không đồng nghĩa quyền còn mới

Nếu admin thu hồi vai trò sau login, `Authentication.getAuthorities()` trong session có thể vẫn là snapshot cũ. Repository **không tự gọi `UserDetailsService` ở mỗi request**, không phải cơ chế cache invalidation hoặc hệ thống thu hồi token/session.

Nếu yêu cầu quyền mới có hiệu lực sớm, cần thêm chiến lược invalidate session, reauthenticate, so `authVersion` hoặc tra cứu trạng thái/permission mới tại điểm nhạy cảm.

## 7. NullSecurityContextRepository: khi không muốn duy trì context

`NullSecurityContextRepository` là implementation không lưu context sang nơi bền hơn request. Nó thường được dùng trong ứng dụng:

- Resource server xác thực bearer token trên **mỗi HTTP request**.
- HTTP Basic xác thực credential ở mỗi request theo cơ chế stateless.
- Dịch vụ API có policy `SessionCreationPolicy.STATELESS` và không dựa vào server-side login session.

~~~java
// Cấu hình minh họa trong một Spring Security Servlet app:
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Spring Security 6 có thể cấu hình `NullSecurityContextRepository` và không dùng session để lấy security context với policy stateless. **Không** suy ra rằng ứng dụng không bao giờ có bất cứ `HttpSession` nào vì code khác vẫn có thể gọi Servlet session API theo cấu hình, hoặc một filter tùy biến tạo session. Cần test hành vi thật.

**Ranh giới:** Stateless không có nghĩa API bỏ qua xác thực. Nó nghĩa là không phụ thuộc vào **security context đã được lưu trong session trước đó**; mỗi request mang bằng chứng riêng (bearer token, Basic credentials) hoặc cơ chế xác thực stateless tương ứng.

Không lưu raw bearer token/refresh token trong session hoặc logs chỉ để thuận tiện gỡ lỗi.

## 8. DelegatingSecurityContextRepository: kết hợp phạm vi chứ không gộp mọi loại storage

Spring Security 6 dùng `DelegatingSecurityContextRepository` để lưu context vào nhiều delegates và lấy từ delegate phù hợp theo thứ tự. Ví dụ mặc định là request-attribute trước, HttpSession sau:

~~~text
                               DelegatingSecurityContextRepository
                                     /                \
                                    v                  v
                  RequestAttributeRepository    HttpSessionRepository
                   (cùng request/dispatch)     (nhiều HTTP requests)
                                    \                  /
                                     \                /
                               SecurityContextHolder
~~~

Nếu tự cấu hình một repository **chỉ có `HttpSessionSecurityContextRepository`**, bạn có thể bỏ lợi ích khôi phục context trong một số `ERROR` dispatch. Nếu chỉ có request attribute, user không giữ được login sang request sau.

**Thứ tự đọc quan trọng:** Nếu request attribute đã có context, nó có thể được chọn thay vì context trong session ở cùng request. Khi tự xây custom delegating repository, hãy xác định chính xác thứ tự và semantics. Không để một delegate kém tin cậy đưa principal/authority chưa được xác thực vào chuỗi repository.

**Save cũng có thể không bảo đảm mọi nơi đều ghi thành công:** các delegate custom/remote có thể lỗi, bị giới hạn session hoặc có chiến lược consistency riêng. Cần quyết định failure policy trước khi cấp quyền hoặc redirect.

## 9. Spring Security 5 và 6: implicit save so với explicit save

### 9.1. Mô hình cũ – SecurityContextPersistenceFilter

Trong mô hình implicit save, `SecurityContextPersistenceFilter` tải context rồi theo dõi thay đổi, và khi request kết thúc/cam kết response có thể tự ghi lại vào repository. Chỉ gọi:

~~~java
SecurityContextHolder.setContext(context);
~~~

có thể đủ để persistence filter tự lưu, tùy cấu hình cũ. Tuy nhiên, đây là nền tảng migration, không phải hành vi cần mặc định cho Spring Security 6.

### 9.2. Mô hình mới – SecurityContextHolderFilter

Spring Security 6 đặt `SecurityContextHolderFilter` vào luồng mặc định với `requireExplicitSave=true`:

~~~text
request -> load context vào holder
               |
               v
       authentication/controller
               |
               +--> setContext(context) chỉ đổi holder
               |
               +--> saveContext(context, request, response) nếu muốn persist
               |
               v
       response, filter clears holder
~~~

`SecurityContextHolderFilter` **chỉ tải và dọn**; nó không giám sát thay đổi và không tự save. Nếu custom login chỉ `setContext` rồi redirect, request kế tiếp có thể mất đăng nhập. Sửa bằng **save tường minh trước khi commit response**.

### 9.3. Cấu hình migration

~~~java
// Trong cấu hình HttpSecurity của Spring Security 6:
http.securityContext(sc -> sc.requireExplicitSave(true));
~~~

Spring Security 6 đã áp dụng hành vi này theo mặc định trong cấu hình phù hợp; câu lệnh trên làm rõ chủ ý. Có thể dùng `requireExplicitSave(false)` như một lựa chọn tương thích khi nâng cấp từ code cũ, nhưng không nên gắn cả `SecurityContextHolderFilter` lẫn `SecurityContextPersistenceFilter` trong cùng chain.

**Lưu ý:** Không phải mọi authentication mechanism tích hợp sẵn đều yêu cầu bạn tự gọi `saveContext` trong controller. Form login do framework quản lý đã có hooks thích hợp. Vấn đề thường xảy ra khi bạn tự tạo authentication flow, thay filter, hoặc thiết kế login API custom.

## 10. Demo Java 17 chạy được: request attribute, HTTP session, stateless và logout

Ví dụ chạy độc lập bằng Gradle với **Spring Security Web 6.5.11**, **Spring Framework Test 6.2.15** và mock Servlet request/response. Nó không cần server hoặc database và **không xác minh credential thật**: token authenticated chỉ được tạo từ mã demo **đáng tin**, nhằm thử đúng hành vi của `SecurityContextRepository`.

**Tuyệt đối không** xây một endpoint cho client gửi username/role rồi gọi `UsernamePasswordAuthenticationToken.authenticated(...)` như demo; trong hệ thống thật, phải dùng `AuthenticationManager.authenticate(...)` trước khi tạo context đáng tin.

### 10.1. Cấu trúc thư mục

~~~text
security-context-repository-demo/
├── build.gradle
└── src/main/java/example/ContextRepositoryDemo.java
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
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework:spring-web:6.2.15'
    implementation 'org.springframework:spring-test:6.2.15'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.ContextRepositoryDemo'
}
~~~

Các dependency Servlet/Spring Test phục vụ mock trong chương trình. Trong Spring Boot thực, ưu tiên version alignment do BOM của Boot quản lý thay vì copy các version thủ công từ ví dụ.

**File `src/main/java/example/ContextRepositoryDemo.java`:**

~~~java
package example;

import java.util.List;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

public final class ContextRepositoryDemo {

    public static void main(String[] args) {
        // Hai lớp repository gần với mặc định của Spring Security 6.
        SecurityContextRepository repository =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository()
                );

        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse loginResponse =
                new MockHttpServletResponse();

        System.out.println("before.contains="
                + repository.containsContext(login));

        // Chỉ tạo token authenticated ở demo đáng tin.
        // Trong web app, AuthenticationManager phải xác minh trước.
        Authentication trusted =
                UsernamePasswordAuthenticationToken.authenticated(
                        "an", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(trusted);
        SecurityContextHolder.setContext(context);

        // Holder đã có danh tính, repository vẫn CHƯA có dữ liệu.
        System.out.println("holder.name="
                + SecurityContextHolder.getContext()
                        .getAuthentication().getName());
        System.out.println("beforeSave.contains="
                + repository.containsContext(login));

        // Chính lời gọi này giúp context được giữ trong session.
        repository.saveContext(context, login, loginResponse);

        System.out.println("afterSave.contains="
                + repository.containsContext(login));

        MockHttpSession session = (MockHttpSession) login.getSession(false);
        System.out.println("session.created=" + (session != null));

        // Mô phỏng filter dọn ThreadLocal sau request login.
        SecurityContextHolder.clearContext();
        System.out.println("holder.afterClear.empty="
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));

        // Request HTTP MỚI có cùng session: đọc được identity.
        MockHttpServletRequest next =
                new MockHttpServletRequest("GET", "/account");
        next.setSession(session);

        SecurityContext restored =
                repository.loadDeferredContext(next).get();

        System.out.println("next.name="
                + restored.getAuthentication().getName());
        System.out.println("next.contains="
                + repository.containsContext(next));

        // Repo chỉ theo request attribute.
        RequestAttributeSecurityContextRepository requestOnly =
                new RequestAttributeSecurityContextRepository();
        MockHttpServletRequest oneRequest =
                new MockHttpServletRequest("GET", "/error");
        requestOnly.saveContext(
                context, oneRequest, new MockHttpServletResponse());

        System.out.println("attribute.sameRequest="
                + (requestOnly.loadDeferredContext(oneRequest).get()
                        .getAuthentication() != null));

        MockHttpServletRequest anotherRequest =
                new MockHttpServletRequest("GET", "/next");
        System.out.println("attribute.nextRequest="
                + (requestOnly.loadDeferredContext(anotherRequest).get()
                        .getAuthentication() != null));

        // Repo stateless không lưu context.
        SecurityContextRepository nullRepository =
                new NullSecurityContextRepository();
        MockHttpServletRequest apiRequest =
                new MockHttpServletRequest("GET", "/api/resource");
        nullRepository.saveContext(
                context, apiRequest, new MockHttpServletResponse());

        System.out.println("null.contains="
                + nullRepository.containsContext(apiRequest));
        System.out.println("null.loadEmpty="
                + (nullRepository.loadDeferredContext(apiRequest).get()
                        .getAuthentication() == null));

        // Logout logic: lưu context TRỐNG qua repository tương ứng.
        SecurityContext empty = SecurityContextHolder.createEmptyContext();
        repository.saveContext(
                empty, next, new MockHttpServletResponse());

        MockHttpServletRequest afterLogout =
                new MockHttpServletRequest("GET", "/account");
        afterLogout.setSession(session);
        System.out.println("afterLogout.empty="
                + (repository.loadDeferredContext(afterLogout).get()
                        .getAuthentication() == null));

        SecurityContextHolder.clearContext();
    }
}
~~~

### 10.2. Chạy chương trình

Sử dụng JDK **17+**, Gradle tương thích và network lần đầu để tải dependencies:

~~~bash
gradle -q run
~~~

Với Gradle Wrapper đã có sẵn: `./gradlew -q run` hoặc trên Windows `gradlew.bat -q run`.

**Stdout mong đợi** từ `System.out.println` (không bao gồm log thư viện/Gradle nếu môi trường bật thêm):

~~~text
before.contains=false
holder.name=an
beforeSave.contains=false
afterSave.contains=true
session.created=true
holder.afterClear.empty=true
next.name=an
next.contains=true
attribute.sameRequest=true
attribute.nextRequest=false
null.contains=false
null.loadEmpty=true
afterLogout.empty=true
~~~

### 10.3. Phân tích kết quả

- `before.contains=false`: chưa có context trong repository.
- `holder.name=an` nhưng `beforeSave.contains=false`: holder đang thấy authenticated principal nhưng **chưa được lưu**; bằng chứng trực tiếp cho khác biệt giữa hai thành phần.
- `afterSave.contains=true` và `session.created=true`: delegating repository lưu qua request attribute và session.
- `holder.afterClear.empty=true`: xóa ThreadLocal không xóa context đã lưu trong session.
- `next.name=an`: request mới có cùng session đã tải context từ repository.
- `attribute.sameRequest=true`, `attribute.nextRequest=false`: request attribute có thể giúp cùng request (kể cả dispatch) nhưng không giữ qua request mới.
- `null.contains=false`, `null.loadEmpty=true`: null repository là no-op; mỗi request stateless phải tự xác thực theo cơ chế đã cấu hình.
- `afterLogout.empty=true`: mô phỏng lưu context trống vào repository để bỏ authentication khỏi session. **Trong ứng dụng thật nên dùng logout support** để dọn thêm session/cookie/CSRF/remember-me và các thành phần thích hợp.

**Giới hạn demo:** Chương trình gọi repository trực tiếp trên mock request, không chạy `SecurityContextHolderFilter`, không phát session cookie qua network, không làm session fixation protection, không xác thực password và không kiểm tra phân quyền. Các giá trị boolean chỉ minh họa storage semantics; chúng **không thay thế** integration test với `SecurityFilterChain` trong ứng dụng của bạn.

## 11. Tích hợp trong Spring Boot Servlet: cấu hình repository rõ ràng

Với một ứng dụng dùng session-based authentication, có thể cấu hình:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            SecurityContextRepository contextRepository) throws Exception {

        http
            .securityContext(sc -> sc
                    .securityContextRepository(contextRepository)
                    .requireExplicitSave(true))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **mã minh họa tích hợp**: cần imports của Spring Config/Security, dependencies Servlet starter và templates/login phù hợp; không phải chương trình standalone. Nếu để mặc định của Spring Security 6 session-based, đa số ứng dụng **không phải tự khai báo repository bean này**. Đưa code lên đây để thấy điểm hook `http.securityContext(...).securityContextRepository(...)`, không phải khuyến nghị ghi đè cấu hình mặc định vô cớ.

**Cảnh báo:** Khi tùy biến `SecurityContextRepository`, phải đảm bảo repository thực sự được dùng **đồng nhất** bởi `SecurityContextHolderFilter` và các authentication filters/success handlers liên quan. Tạo một bean mà controller save vào một instance còn filter load từ instance khác là nguồn lỗi khó tìm.

### 11.1. Các chính sách session

~~~java
// Mã tích hợp minh họa, không phải class độc lập:
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

| Policy | Ý nghĩa thực dụng |
| --- | --- |
| `ALWAYS` | Spring Security chủ động tạo session theo cấu hình phù hợp |
| `IF_REQUIRED` | Tạo session khi cần cho cơ chế bảo mật; thường thích hợp web form login |
| `NEVER` | Spring Security không chủ động tạo session mới nhưng có thể dùng session đã tồn tại |
| `STATELESS` | Spring Security không tạo hoặc dùng `HttpSession` để lấy security context; thường chọn null repository cho security |

Sự tồn tại của `HttpSession` trong thực tế còn do **Servlet application code, request cache, các filters khác và Spring Session**. Khi debug, kiểm tra ai gọi `getSession()` và có saved request hay không, thay vì gộp mọi nguyên nhân cho repository.

## 12. Custom login: đúng thứ tự để không mất authentication sau redirect

Nếu bạn **chủ động** viết controller hoặc filter login, và có một `AuthenticationManager` xử lý credentials, các bước đúng cơ bản là:

~~~text
Bước 1: Nhận credential qua HTTPS
Bước 2: AuthenticationManager.authenticate(unauthenticated token)
Bước 3: Nếu thành công, chạy session strategy cần thiết
Bước 4: Tạo SecurityContext mới chứa Authentication đã xác minh
Bước 5: Đặt context vào SecurityContextHolder
Bước 6: saveContext(context, request, response)
Bước 7: Sau đó mới redirect/commit response
~~~

Đoạn minh họa đường đi **không độc lập biên dịch** (nằm trong service/controller có dependencies và đã có policy session):

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginBody.username(), loginBody.password());

Authentication verified =
        authenticationManager.authenticate(requestToken);

// Nếu tự xây authentication flow, phải đảm bảo SessionAuthenticationStrategy
// được gọi phù hợp trước khi lưu, bao gồm chống session fixation.
SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);

securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(
        context, httpServletRequest, httpServletResponse);

// Chỉ sau khi lưu thành công mới hoàn tất response/redirect.
~~~

**Điểm rất dễ bỏ sót: session fixation protection.** Cấu hình form login có sẵn triển khai các chiến lược session thích hợp. Nếu bạn viết custom controller gọi trực tiếp `authenticate(...)` rồi `saveContext(...)`, bạn **không tự động** sao chép toàn bộ `SessionAuthenticationStrategy`, concurrent session control, CSRF, remember-me và success/failure handling chỉ bằng vài dòng. Cần tích hợp trọn vẹn hoặc ưu tiên cơ chế login do framework cung cấp.

Không bao giờ tạo trusted `Authentication` bằng `UsernamePasswordAuthenticationToken.authenticated(...)` từ payload client **trước khi xác minh**. API đó không tự chứng minh password đúng.

### Vì sao save trước redirect?

Nếu server gọi `sendRedirect(...)` hoặc ghi body khiến HTTP response **committed**, việc tạo session mới hoặc đặt cookie sau đó có thể không còn hiệu lực như mong muốn. Luồng explicit save giúp tránh một class lỗi do response commit sớm trong mô hình implicit save.

## 13. Logout, clearContext và lưu trạng thái rỗng

### 13.1. Clear holder chưa phải là xóa session

~~~java
SecurityContextHolder.clearContext();
~~~

Thao tác này dọn holder của luồng hiện tại. Nếu `HttpSession` vẫn lưu `SecurityContext` đã xác thực, một request sau có thể khôi phục nó. Do đó, logout phải xử lý **cả holder và persistence**.

Spring Security Servlet có logout support như `SecurityContextLogoutHandler` và các handler khác để:

- Dọn `SecurityContextHolder`.
- Xóa/ghi context rỗng theo repository cấu hình thích hợp.
- Invalidate session theo policy.
- Xử lý cookies, remember-me, CSRF tokens hoặc các integration khác nếu có.

Trong cơ chế explicit save, **xóa authentication cũng là một thay đổi cần persistence**. Có thể lưu context trống khi tự xử lý logout (cẩn thận với repo/session và thứ tự), nhưng không nên thay hoàn toàn framework logout bằng một dòng `saveContext(empty)` vì còn session fixation, cookie, token và integration.

### 13.2. JWT và refresh token là luồng riêng

Nếu client có bearer access token còn hiệu lực, clear session cookie hoặc save context trống **không thu hồi tự động token đã ký**. Với resource server stateless, mỗi request mang bearer token riêng; để thu hồi cần TTL ngắn, token version/revocation/denylist hoặc introspection tùy kiến trúc.

Không hứa “logout tất cả thiết bị” nếu hệ thống chỉ invalidate một session đang dùng.

## 14. Bất đồng bộ, thread pool và Servlet dispatch: scope không phải global

### 14.1. ThreadLocal mặc định

`SecurityContextHolder` mặc định dùng chiến lược `MODE_THREADLOCAL`. Context có thể truy cập trong cùng luồng mà không cần truyền tham số, nhưng không mặc định xuất hiện trên **một thread khác**.

Ví dụ:

~~~java
Authentication auth = SecurityContextHolder.getContext()
        .getAuthentication();
// Đoạn trên đúng trong context của thread đang xử lý.
// Một Runnable do executor chạy trên thread khác KHÔNG tự có auth.
~~~

Đây là code minh họa, không phải lời khẳng định mọi async integration đều mất context: Spring Security có `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và integration hỗ trợ propagation theo từng môi trường.

Nếu dùng thread pool hoặc `@Async`, cần giải pháp propagation được hỗ trợ, dọn context sau tác vụ, và tránh giữ credential/Principal mutable quá lâu. Không tự sử dụng `MODE_GLOBAL` cho server đa người dùng. `MODE_INHERITABLETHREADLOCAL` không phải giải pháp tự động an toàn cho thread pool tái sử dụng.

### 14.2. Servlet ERROR/FORWARD/ASYNC dispatch

Một HTTP request có thể trải qua nhiều kiểu dispatch; container và filter mapping quyết định security filters chạy lại ở đâu. Request attribute repo giúp context còn ở **cùng đối tượng request** qua dispatch. Session repo phục vụ **request HTTP khác**.

Đừng đánh đồng “cùng HTTP request” với “cùng Java thread”: asynchronous processing có thể chuyển thread, cần phối hợp Servlet async integration/context propagation. Một số trường hợp `ERROR` dispatch diễn ra sau khi holder bị clear; request attribute có thể giúp khôi phục, nhưng bạn vẫn cần cấu hình đúng dispatcher types cho filter chain.

### 14.3. Thread leak nếu không clear

Nếu một custom filter đặt `SecurityContextHolder.setContext(context)` nhưng không dọn theo `finally` (hoặc đi ngoài filter chain chuẩn), một thread pool có thể tái sử dụng thread ở request sau và giữ danh tính cũ. Trong Spring Security chuẩn, filter quản lý việc dọn holder. Khi tự viết code chạy ngoài chain hoặc trong test, hãy clear context đúng vòng đời.

~~~java
try {
    SecurityContextHolder.setContext(context);
    // Logic thực hiện dưới danh tính đã xác minh.
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Đây là ví dụ bảo vệ thread-local khi **tự quản lý context**; không có nghĩa mọi controller phải gọi clear thủ công khiến các filters không còn nhìn thấy context.

## 15. Request cache không phải security context repository

Có ít nhất ba khái niệm dễ trộn:

| Thành phần | Chức năng |
| --- | --- |
| `SecurityContextRepository` | Lưu/tải **ngữ cảnh xác thực** |
| `RequestCache` | Lưu HTTP request gốc để quay lại sau login (ví dụ deep link) |
| `HttpSession` | Một cơ chế lưu trữ phía server có thể được **cả hai** sử dụng |

Khi thấy `JSESSIONID` xuất hiện dù chưa login, nguyên nhân có thể là `HttpSessionRequestCache` lưu URL đích trước khi redirect đến trang login; không nhất thiết `SecurityContextRepository` đã lưu một người dùng authenticated.

Spring Security 6 tối ưu việc đọc `RequestCache` so với phiên bản cũ. Nếu chọn stateless cho API, cần kiểm soát cả session policy và request cache để không vô tình lưu saved request làm ứng dụng hoạt động không như mong muốn.

**Không dùng `containsContext` để hỏi “đã có saved request nào chưa?”**. Đây là hai hợp đồng khác nhau.

## 16. Tùy biến repository: chọn theo nhu cầu, không viết lại bằng thói quen

Một ứng dụng có thể cần lưu context vào nguồn khác vì multi-node hoặc lưu session phân tán. Có hai cách lớn:

1. Tiếp tục dùng `HttpSessionSecurityContextRepository`, nhưng **đưa session store ra Redis/database** qua Spring Session hoặc container-compatible session strategy. Trong trường hợp này repository vẫn dựa vào `HttpSession`, chỉ backing storage thay đổi.
2. Viết `SecurityContextRepository` riêng với behavior load/save/contains và lỗi mạng/serialization rõ ràng. Đây là công việc nhạy cảm, cần tuân thủ authorization và session lifecycle.

Khi thiết kế custom repository, phải làm rõ:

- Khóa identity/session được tạo như thế nào; chống fixation/hijacking, TTL, rotation và cookie flags.
- `loadDeferredContext` có lazy loading không; trường hợp không tìm thấy trả context trống chứ không null.
- `saveContext` có bền vững trước khi báo success không; xử lý response committed ra sao.
- `containsContext` chỉ phản ánh dữ liệu lưu, không xác nhận quyền của principal đã lâu.
- Repository có lưu anonymous/empty context không; có thể làm tăng dữ liệu vô ích.
- Serialize `SecurityContext` chứa implementation principal nào, có tương thích qua deploy nhiều phiên bản không.
- Khi logout/session expire, key/token/entry được thu hồi theo chính sách, tránh tái xuất hiện bởi cache replication race.
- Phân vùng key theo app/environment/tenant để tránh va chạm và lộ cross-tenant.
- Store mất kết nối thì fail closed cho thao tác bảo mật nhạy cảm hay fallback như thế nào; không “authenticate anonymous thành admin” do lỗi deserialize.
- Logging, tracing, metrics không chứa raw password, access token hay toàn bộ object principal.
- Test concurrency và nhiều node thực sự, không chỉ unit test một implementation.

**Một custom repository không thay thế `AuthenticationManager` và authorization.** Nó chỉ quyết định lưu/tải context; nếu bạn cho dữ liệu không đáng tin tự định nghĩa một `Authentication(isAuthenticated=true)` rồi lưu, đó là lỗi bảo mật ở nguồn xác thực.

## 17. Multi-chain: một endpoint dùng repo này, endpoint khác dùng repo khác

Trong Spring Security Servlet, ứng dụng có thể có nhiều `SecurityFilterChain`:

~~~text
/api/**          --> stateless bearer auth + NullSecurityContextRepository
/web/**          --> form login + session-based repository
/admin/**        --> web session + revalidation/step-up policy
~~~

Đây là **sơ đồ kiến trúc**, không phải routing mặc định. Với mỗi chain phải xác định:

- `securityMatcher` nào thực sự khớp request.
- Có `formLogin`, `httpBasic`, `oauth2ResourceServer` hoặc custom filter nào.
- Repository nào phục vụ `SecurityContextHolderFilter` và filter xác thực cụ thể.
- Có áp dụng `SessionCreationPolicy.STATELESS` đúng chain hay không.
- Cookie/session đã phát hành ở web có vô tình được dùng để vượt qua API stateless hay không.
- Thứ tự chain: cấu hình order và matcher chính xác, tránh “catch-all” chain chọn trước làm chain chuyên biệt không chạy.

Ví dụ **minh họa tích hợp**:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Đoạn này không độc lập biên dịch: cần dependencies OAuth2 resource server và cấu hình issuer/JWK/decoder hợp lệ. Nó chỉ nêu ý rằng API stateless không nên dựa vào session, **không** phải một resource server production hoàn chỉnh.

## 18. Tính nhất quán: context đã lưu có thể mang quyền cũ

Repository có thể khôi phục một `Authentication` hợp lệ theo session từ nhiều phút trước; điều đó **không bảo đảm** user chưa bị khóa, role chưa bị thu hồi hoặc tenant membership còn đúng.

| Thay đổi trong DB/IdP | Context trong session có thể thế nào? | Cơ chế cần thêm |
| --- | --- | --- |
| Admin thu hồi `ROLE_ADMIN` | `Authentication.getAuthorities()` có thể vẫn chứa role cũ | Invalidate/revalidate session hoặc check permission mới |
| User bị disable | Session cũ có thể tiếp tục được khôi phục | Account-status recheck, session revocation |
| Password reset do nghi compromise | Session của attacker có thể còn active | Logout all sessions, token refresh revocation, audit |
| Username/email đổi | `Authentication.getName()` có thể là tên cũ | Dùng stable userId, refresh profile/session theo policy |
| Chuyển tenant | Tenant claim/authorities trong session có thể cũ | Tenant membership check, context refresh |
| Redis/session store bị lỗi | Không thể load context như trước | Degraded/failure policy và giám sát; không tự cấp quyền |

Cache `UserDetails`, `SecurityContextRepository`, session store và JWT introspection là **những lớp khác nhau**. Evict UserDetails không tự xóa session; clear ThreadLocal không tự thu hồi JWT. Cần tách rành mạch các thao tác quản trị và chính sách revocation.

## 19. Cách kiểm thử chính xác trong Spring Security Servlet

### 19.1. Những ca kiểm thử quan trọng

1. **Sau login thành công:** cùng request nhìn thấy `Authentication` đúng; response tạo session/cookie theo policy.
2. **Request kế tiếp:** mang session cookie hợp lệ, tải đúng identity/authorities; không xác thực lại password không cần thiết.
3. **Không gọi saveContext trong custom login:** request login hiện tại có thể thấy auth nhưng request sau vẫn là anonymous; test này phát hiện lỗi migration.
4. **Không có cookie/session:** request mới không tự “nhớ” principal.
5. **Stateless:** mang bearer token request nào thì auth request đó; không có security context persisted qua HttpSession.
6. **Logout:** dọn holder và session; request sau với cookie cũ không còn authenticated.
7. **RequestAttribute:** `ERROR` dispatch vẫn có context khi filter mapping và repo được cấu hình phù hợp, request độc lập không có.
8. **Response commit sớm:** login phải save trước redirect/commit; kiểm tra cookie và request tiếp theo.
9. **SessionCreationPolicy.NEVER:** tìm nguồn tạo session khi request cache có hiệu lực.
10. **Concurrent sessions/session fixation:** session ID phải được thay đổi hoặc bảo vệ theo strategy phù hợp sau login.
11. **Multi-chain:** kiểm tra API stateless và web session đúng matcher.
12. **Principal serialization:** nếu dùng session store phân tán, verify serialize/deserialize và không giữ JPA entity graph quá lớn.
13. **Thu hồi quyền:** thay DB role/disable, đo request kế tiếp mất quyền theo policy/SLO.
14. **Async/errors:** context propagation, dispatcher types, holder cleanup đúng.
15. **Store unavailable:** cách xử lý lỗi không tạo identity giả, không silently fail-open.

### 19.2. MockMvc cần chạy qua Spring Security Filter Chain

Ví dụ assertion **phác thảo**, không phải test standalone (yêu cầu Spring Boot test config, beans, seeded users và Spring Security Test):

~~~java
// Các request này phải thực sự chạy qua SecurityFilterChain.
MvcResult login = mvc.perform(formLogin().user("an").password("correct"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) login.getRequest().getSession(false);

mvc.perform(get("/profile").session(session))
        .andExpect(authenticated());

mvc.perform(logout().session(session))
        .andExpect(unauthenticated());
~~~

Nếu dùng helper `logout()` của Spring Security Test, hãy xác nhận API đúng version và cách gắn session; việc sau logout dùng lại session đã invalidated có thể cần request mới/cookie mô phỏng thay vì truyền object session không hợp lệ. **Đoạn trên chỉ thể hiện ý định test**, không phải chương trình JUnit hoàn chỉnh.

### 19.3. Logs/metrics hữu ích

- `context_repository_load` / `save` / `miss` và backend session read latency.
- Số lần custom login thành công nhưng request sau unauthenticated.
- `HttpSession` created/invalidated, session store errors và cross-node read failures.
- Tần suất request có session mà authorities đã stale theo version.
- Lỗi save sau response commit, redirect dẫn đến thiếu session cookie.
- Các trường hợp principal không serialize được.

Giữ audit ID, request ID và loại lỗi; **không log full context, password, bearer token hoặc serialized session object**.

## 20. Bảng chẩn đoán nhanh lỗi thường gặp

| Hiện tượng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Login API trả 200, request sau 401 | Chỉ `SecurityContextHolder.setContext` nhưng không `saveContext` | Explicit save, dùng đúng repository/response |
| Có session cookie nhưng vẫn anonymous | Context chưa được lưu, session ID sai, session expire hoặc filter chain khác | Inspect `SecurityContextRepository` và cookie/session scope |
| `NullSecurityContextRepository` mà mong nhớ login | Stateless repo không lưu | Chọn session-based flow hoặc gửi credential mỗi request |
| Chỉ dùng RequestAttributeRepository, request sau mất login | Request attribute không tồn tại sang request mới | Thêm HttpSession delegate nếu cần stateful |
| `/error` không thấy principal | ERROR dispatch không khôi phục holder hoặc không có request-attribute repo | Cấu hình dispatcher/filter và repo phù hợp |
| Save gọi sau `sendRedirect`, cookie thiếu | Response đã committed | Save trước response commit |
| `SecurityContextPersistenceFilter` và `SecurityContextHolderFilter` cùng chain | Hai cơ chế không nên cùng hoạt động | Chọn migration path, không gắn cả hai |
| Session đột nhiên được tạo trước login | `RequestCache`, filter khác, app gọi `getSession` | Phân tích nguồn tạo, đừng chỉ đổ lỗi repository |
| Session restore được nhưng role cũ | `Authentication` là snapshot, DB đã đổi | Revoke/revalidate authorities theo policy |
| Custom authentication tạo session nhưng fixation không bảo vệ | Bỏ qua `SessionAuthenticationStrategy` | Tích hợp strategy hoặc dùng framework login |
| JWT bị logout rồi vẫn dùng được | Clear session không revoke access token | Token revocation/TTL/version/introspection |
| Context mất trong `@Async` | ThreadLocal không tự truyền qua thread pool | DelegatingSecurityContext executor/propagation |
| Principal A xuất hiện trong request của B | ThreadLocal không dọn trong custom code | `finally clearContext` và kiểm tra filter chain |
| Chỉ tạo repository bean nhưng không có hiệu lực | Filter/login sử dụng repo khác | Cấu hình trên HttpSecurity/filter đúng chain |
| `containsContext=true` bị hiểu là login còn hợp lệ | Method chỉ báo storage có context | Kiểm tra Authentication/trust và authorization mới |
| Logout chỉ `clearContext` | Session còn context | Dùng logout support, invalidate/save empty context |
| Multi-node session mất giữa các node | Session local không đồng bộ hoặc cookie routing không nhất quán | Spring Session/distributed store và test routing |
| Read-only request tạo nhiều session không cần | Custom code hoặc request cache chủ động tạo | Đo session creation và dùng IF_REQUIRED đúng cách |

## 21. Checklist review trước production

1. **Chỉ rõ yêu cầu vòng đời:** session-based, stateless hay hybrid; request nào được phép tạo `HttpSession`.
2. **Chọn repository:** mặc định delegating cho Servlet session phù hợp, `NullSecurityContextRepository` cho stateless khi đúng mục tiêu.
3. **Ghi rõ source of authentication:** chỉ `AuthenticationManager`/provider đáng tin tạo authenticated result.
4. **Explicit save:** custom login sau khi xác thực phải `setContext` và `saveContext` trước commit; không dựa vào implicit save mặc định của Spring Security 6.
5. **Đồng nhất repo:** filter chain, authentication filters, logout handlers và custom controller dùng repository tương thích.
6. **Session fixation:** mọi login flow custom cần thực thi strategy liên quan; đừng tưởng saveContext là toàn bộ login security.
7. **Logout:** clear holder, invalidate session, save empty context theo policy; xử lý remember-me/CSRF/token riêng khi cần.
8. **Request vs session:** request attribute không qua HTTP request mới, session phụ thuộc cookie/id/TTL; Null không lưu.
9. **Thread safety:** không giữ identity ở biến static/global; dọn ThreadLocal; truyền context cho async theo cơ chế chuẩn.
10. **Principal tối thiểu:** không lưu JPA entity graph, raw credential hoặc secret trong session; cân nhắc serialization và privacy.
11. **Quyền tươi mới:** session auth có thể stale; thiết kế revocation/reauth/permission checks.
12. **Nhiều chain:** test matcher/order và session policy của từng vùng API.
13. **Response commit:** test redirect, error dispatch, saved request và cookie.
14. **Multi-node:** session backing store, TTL, invalidation, object version và fail-closed chính sách nhạy cảm.
15. **Tests end-to-end:** login → request mới → logout → request mới; stateless, async, error, concurrency và failure cases.
16. **Quan sát vận hành:** metrics load/save/session created/invalidated, không log raw security context.

## 22. Tự kiểm tra kiến thức

**1.** `SecurityContextHolder.setContext(context)` có tự lưu ngữ cảnh vào session trong Spring Security 6 mặc định không?  
**Đáp:** Không. `SecurityContextHolderFilter` đọc/clear, còn custom login phải lưu bằng `SecurityContextRepository.saveContext(context, request, response)` nếu muốn persist.

**2.** Request attribute repo và session repo khác nhau ở đâu?  
**Đáp:** Request attribute sống cùng một Servlet request (có thể qua dispatch), session tồn tại qua nhiều HTTP request có chung session ID và chưa hết hạn.

**3.** `NullSecurityContextRepository` có nghĩa request không được authentication không?  
**Đáp:** Không. Request stateless vẫn được xác thực mỗi lần bằng Basic/Bearer hoặc mechanism khác; chỉ không lưu context để dùng lại qua session.

**4.** Vì sao `containsContext(request)` không đủ kết luận user được phép xem `/admin`?  
**Đáp:** Nó chỉ hỏi repository có context, không kiểm tra roles, trạng thái account, expiry hoặc quyền mới nhất.

**5.** Trong Spring Security 6, mặc định `DelegatingSecurityContextRepository` thường kết hợp hai delegates nào?  
**Đáp:** `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`.

**6.** Một custom controller gọi `authenticate(...)` và `saveContext(...)` thì đã thay thế đầy đủ form login chuẩn chưa?  
**Đáp:** Chưa. Còn session fixation protection/SessionAuthenticationStrategy, CSRF, success/failure handlers, concurrent sessions, cookie và policy khác.

**7.** Người dùng logout bằng `SecurityContextHolder.clearContext()`, nhưng request sau với cookie cũ vẫn authenticated. Vì sao?  
**Đáp:** Context cũ còn trong session/repository; cần logout support hoặc lưu context trống và invalidate session đúng cách.

**8.** Vì sao hai request chạy trên hai threads không tự chia sẻ context qua `SecurityContextHolder`?  
**Đáp:** Mặc định holder dùng `ThreadLocal`; context được nạp theo request từ repository, async cần propagation được cấu hình.

**9.** API có `SessionCreationPolicy.NEVER` nhưng tạo session. Nguyên nhân nào khác cần xem?  
**Đáp:** RequestCache lưu saved request, filter/ứng dụng gọi `getSession`, hoặc component khác; không chỉ repo auth.

**10.** Sau khi admin gỡ role nhưng session vẫn có role cũ, `SecurityContextRepository` có lỗi không?  
**Đáp:** Không nhất thiết. Nó lưu snapshot authentication; authorization freshness cần chiến lược refresh/revoke/revalidate riêng.

**11.** Vì sao nên save trước redirect?  
**Đáp:** Response commit có thể ngăn việc set session cookie hoặc ghi context đúng thời điểm; explicit save tránh race này.

**12.** Một request `ERROR` cần thấy principal dù holder vừa được clear. Repository nào hữu ích?  
**Đáp:** `RequestAttributeSecurityContextRepository`, với điều kiện cùng Servlet request và filter/dispatcher types phù hợp.

## 23. Tham khảo tài liệu chính thức

- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): repository customization, lưu authentication thủ công, stateless, logout và `requireExplicitSave`.
- [Spring Security 6.5 – Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/persistence.html): RequestAttribute, HttpSession, Null và Delegating repository; phân biệt HolderFilter/PersistenceFilter.
- [Spring Security 6.5.11 – SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext`, `containsContext` và legacy `loadContext`.
- [Spring Security 6.5.11 – HttpSessionSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html): key session, session creation policy và lưu empty/anonymous context.
- [Spring Security 6.5.11 – RequestAttributeSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html): phạm vi request attribute/dispatch.
- [Spring Security 6.5.11 – DelegatingSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html): delegate load/save.
- [Spring Security 6.5.11 – SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html): load context into holder, cleanup và explicit save.
- [Spring Security 6.5 – Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): Spring Security 5 implicit save sang 6 explicit save và default repository.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContext`, `SecurityContextHolder`, `Authentication` và filter chain.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): dọn context, session và các handler.
- [Spring Security 6.5 – Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): chuyển SecurityContext sang tác vụ khác và cleanup.

**Ghi nhớ:** `SecurityContextHolder` trả lời **“request/thread đang dùng danh tính nào?”**; `SecurityContextRepository` trả lời **“lấy/lưu context đó ở đâu, có sống sang request khác không?”**. Với Spring Security 6, **custom authentication phải explicit save** nếu muốn tồn tại giữa requests. `RequestAttribute` phục vụ cùng request/dispatch, `HttpSession` phục vụ nhiều requests, `Null` không lưu và `Delegating` phối hợp các phạm vi. Session context vẫn là snapshot, không thay thế authorization/revocation policy.
