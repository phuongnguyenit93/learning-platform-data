# RequestAttributeSecurityContextRepository và HttpSessionSecurityContextRepository trong Spring Security Servlet

Trong Spring Security cho **Servlet/Spring MVC**, một request có thể đã được xác thực nhưng câu hỏi quan trọng tiếp theo là: **`SecurityContext` chứa thông tin xác thực đó được giữ ở đâu, và request sau có lấy lại được không?** Hai implementation của `SecurityContextRepository` giúp trả lời ở hai phạm vi khác nhau:

- `RequestAttributeSecurityContextRepository`: giữ `SecurityContext` trong **attribute của chính HTTP request**, hữu ích khi request có nhiều lần dispatch như `ERROR`.
- `HttpSessionSecurityContextRepository`: lưu `SecurityContext` trong **HTTP session**, cho phép request tiếp theo của **cùng phiên** lấy lại ngữ cảnh khi cơ chế session hoạt động.

Đây là bài về **vòng đời ngữ cảnh bảo mật và cơ chế lưu/đọc** trong Servlet stack. Phần lớn ví dụ tương ứng với cách sử dụng Spring Security 6.x / Spring Boot 3.x và Java 17+. Với phiên bản khác, đối chiếu tài liệu API của phiên bản đang dùng; đặc biệt chú ý thay đổi hành vi **explicit save** giữa các thế hệ.

## 1. Ba đối tượng dễ bị nhầm: Authentication, SecurityContext và Repository

**`Authentication`** biểu diễn danh tính và trạng thái xác thực: principal, credentials (nếu còn), authorities và cờ authenticated. Sau khi xác thực thành công, framework thường đưa đối tượng này vào một `SecurityContext`.

**`SecurityContext`** là container cho `Authentication`. Một context trống có thể trả về `null` khi gọi `getAuthentication()`; vì vậy **không phải cứ có `SecurityContext` là người dùng đã đăng nhập**.

**`SecurityContextHolder`** cho phép mã hiện tại truy cập context đang gắn với quá trình xử lý. Trong Servlet stack, chiến lược thường gặp dựa vào thread, nhưng web security filter còn chịu trách nhiệm thiết lập và dọn dẹp holder theo vòng đời request. Holder **không phải kho lưu lâu dài giữa hai HTTP request**.

**`SecurityContextRepository`** chịu trách nhiệm **nạp và lưu** context qua các ranh giới phù hợp. Nó là interface; chọn implementation nào sẽ quyết định context được lưu trong request attribute, HTTP session, hay không lưu lại.

```text
Request bắt đầu
    |
SecurityContextHolderFilter
    |-- hỏi SecurityContextRepository: loadDeferredContext(request)
    |-- đặt cơ chế tra cứu context vào SecurityContextHolder
    |
Các filter xác thực / phân quyền, controller, service
    |-- đọc SecurityContextHolder / Authentication khi cần
    |-- sau xác thực có thể thay SecurityContext
    |
Nếu muốn lưu: SecurityContextRepository.saveContext(context, request, response)
    |
Kết thúc request: web filter dọn SecurityContextHolder
    |
Request mới: chỉ có context cũ nếu repository tương ứng đã lưu
và cơ chế request mới có đủ thông tin để nạp lại.
```

Trong Spring Security 6 với cơ chế `SecurityContextHolderFilter`, **lưu context là thao tác tường minh**. Các authentication filter chuẩn như form login có thể tự đảm nhận việc lưu khi xác thực thành công. Nếu bạn tự xây flow đăng nhập bằng controller/custom filter, cần hiểu đúng việc gọi `saveContext`; chỉ gán vào holder chưa đủ để bảo đảm context tồn tại sau request.

## 2. RequestAttributeSecurityContextRepository: phạm vi của một HTTP request

`RequestAttributeSecurityContextRepository` lưu context dưới dạng một attribute gắn vào `HttpServletRequest`. Không cần một HTTP session để chứa context của implementation này.

Điều đó dẫn đến ba tính chất:

1. **Trong cùng một request:** các thành phần xử lý và các lần Servlet dispatch dùng cùng request có thể đọc context đã lưu trong request attribute.
2. **Qua một lần dispatch lỗi (`ERROR`):** có Servlet container sẽ dọn holder trước khi tạo một dispatch riêng cho trang lỗi. Request attribute giúp nạp lại context khi security chain được áp dụng cho dispatch tương ứng. Nhờ vậy trang xử lý lỗi có thể biết người dùng nào đã xác thực trong request gốc.
3. **Sang HTTP request mới:** attribute của request cũ không còn là kho lưu của request mới. Ngay cả khi trình duyệt tiếp tục gửi cùng cookie, chỉ request-attribute repository không tự khôi phục context của request trước.

Ví dụ một request truy cập `/orders/42`, hệ thống lưu `Authentication` vào request attribute, rồi controller gặp exception dẫn tới trang lỗi:

```text
HTTP request #1
  REQUEST dispatch --------------> context lưu trong request attribute
                                        |
  ERROR dispatch (cùng request) --> có thể nạp lại cùng context
                                        |
  response kết thúc -------------> request attribute hết vòng đời

HTTP request #2
  request object mới ------------> KHÔNG có attribute của request #1
```

Lưu ý: tình huống ERROR phụ thuộc **loại dispatch có được Spring Security xử lý không**, cấu hình authorization, cách container thực hiện dispatch và thời điểm context được lưu. Request attribute giúp giữ context xuyên dispatch của **cùng request**; nó không bảo đảm một request đã bị chặn sẽ tự đi tới error page có quyền truy cập.

### Không đồng nhất với request scoped bean

Một bean Spring `@RequestScope` cũng gắn với vòng đời request, nhưng không vì vậy mà thay thế `RequestAttributeSecurityContextRepository`. Repository tuân theo hợp đồng `SecurityContextRepository` để Spring Security filter nạp/lưu context. Không tự viết một request-scoped bean rồi coi nó tương đương với cơ chế security repository.

## 3. HttpSessionSecurityContextRepository: phạm vi nhiều request trong cùng session

`HttpSessionSecurityContextRepository` sử dụng `HttpSession` của Servlet API để giữ context. Khi request sau gửi session identifier hợp lệ (thường là cookie `JSESSIONID`), container tìm lại session; repository có thể nạp context đã lưu.

```text
HTTP request #1: xác thực thành công
     |
SecurityContext chứa Authentication
     |
HttpSessionSecurityContextRepository.saveContext(...)
     |
HttpSession: SPRING_SECURITY_CONTEXT = SecurityContext
     |
Response + session identifier (nếu tạo session mới)
     |
HTTP request #2 với cùng session hợp lệ
     |
HttpSessionSecurityContextRepository.loadDeferredContext(request)
     |
SecurityContextHolder -> Authentication từ session
     |
Authorization kiểm tra quyền -> controller
```

Tên attribute mặc định do Spring Security sử dụng là `SPRING_SECURITY_CONTEXT`. Đây là **chi tiết triển khai** được framework quản lý; không khuyến nghị code nghiệp vụ trực tiếp đọc/ghi session attribute này, vì sẽ bỏ qua các hợp đồng và thao tác an toàn của repository.

Một số điểm cần hiểu đúng:

- **Không có nghĩa request nào cũng tạo session.** Repository có cơ chế hạn chế tạo session khi chưa cần lưu context xác thực; việc tạo session cũng chịu ảnh hưởng cấu hình và thành phần khác của ứng dụng.
- **Không có nghĩa đăng nhập vĩnh viễn.** Context còn có thể mất khi session hết hạn, bị invalidate khi logout, bị thay đổi do concurrency/session fixation policy, hoặc server bị khởi động lại nếu session không được lưu bền/chia sẻ.
- **Không có nghĩa được sao chép qua mọi thiết bị.** Session là phạm vi phiên của client, không phải kho danh tính chung hay SSO.
- **Không có nghĩa mọi application server chia sẻ session.** Ở cụm nhiều instance, cần session affinity hoặc một giải pháp session chia sẻ như Spring Session phù hợp, cùng cấu hình bảo vệ cookie và vận hành.
- **Không có nghĩa application tự tin mọi dữ liệu trong context mãi đúng.** Khi quyền của user thay đổi hoặc tài khoản bị thu hồi, ứng dụng cần một chiến lược cập nhật/invalidate context/session theo yêu cầu bảo mật.

Với context trống hoặc xác thực anonymous, repository có thể tránh lưu session. Tạo ra một `HttpSession` không đồng nghĩa đã lưu một `Authentication` hợp lệ. Ngược lại, có session nhưng client không gửi session identifier đúng thì request mới không thể tìm lại phiên cũ.

### Cookie phiên và bảo mật

Khi dựa vào session, cần cấu hình HTTPS và cookie phù hợp (`Secure`, `HttpOnly`, `SameSite` tùy luồng), kiểm soát CSRF ở ứng dụng dùng credential tự gửi qua cookie, session fixation, timeout và logout. Repository giữ security context **trong session phía server**, không mặc định mã hóa toàn bộ `Authentication` và đặt nó trong cookie của trình duyệt.

## 4. So sánh nhanh hai repository

| Tiêu chí | `RequestAttributeSecurityContextRepository` | `HttpSessionSecurityContextRepository` |
|---|---|---|
| Vị trí lưu | Attribute của `HttpServletRequest` | `HttpSession` |
| Giới hạn vòng đời | Một HTTP request, có thể qua nhiều dispatch | Nhiều HTTP request dùng cùng session hợp lệ |
| Qua `ERROR` dispatch trong cùng request | Hỗ trợ lấy lại context từ request attribute | Có thể nạp context nếu đã lưu vào session và dispatch có session; không nên dựa riêng vào điều này |
| Qua redirect thành HTTP request mới | Không tự duy trì | Có thể duy trì qua session |
| Yêu cầu session để lưu | Không | Có, khi context thực sự cần lưu qua session |
| Stateless API bearer token | Có ích trong phạm vi một request/dispatch khi cần | Thường không dùng để duy trì xác thực giữa các request |
| Rủi ro dùng sai | Tưởng rằng đăng nhập sẽ còn ở request kế tiếp | Vô tình dùng server session khi muốn stateless; stale context khi quyền thay đổi |
| Ý nghĩa của `saveContext` | Ghi vào request attribute hiện tại | Ghi vào session theo policy và điều kiện của repository |

**Một request có thể đồng thời cần cả hai hành vi.** Ví dụ login thành công phải giữ trạng thái ở request tiếp theo bằng session; đồng thời cần biết Authentication trong một ERROR dispatch của request hiện tại. Đó là lý do Spring Security hỗ trợ cơ chế kết hợp.

## 5. DelegatingSecurityContextRepository: kết hợp nhiều nguồn lưu

Trong cấu hình Servlet phổ biến của **Spring Security 6**, cơ chế mặc định thường là `DelegatingSecurityContextRepository` sử dụng **`RequestAttributeSecurityContextRepository` trước, rồi `HttpSessionSecurityContextRepository`**.

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

Đây là **đoạn code minh họa**; để chạy độc lập cần một project Spring Security Web và các import tương ứng. Hành vi khái niệm:

- **Khi nạp:** tìm một delegate có context phù hợp, ưu tiên delegate đầu tiên tìm thấy context. Theo thứ tự trên, request attribute có thể được ưu tiên trong cùng request trước khi đọc session.
- **Khi lưu:** gọi lưu tới các delegate thích hợp. Với hai implementation trên, context có thể vừa sống trong request hiện tại vừa được lưu qua session cho request kế tiếp.
- **Tác dụng:** xử lý tốt hơn ranh giới ERROR dispatch và phiên đăng nhập. Khi redirect tạo HTTP request mới, chỉ phần lưu session mới có khả năng giữ context qua ranh giới request.

Đừng hiểu việc kết hợp là một kiểu đồng bộ dữ liệu phân tán hoặc lưu người dùng vĩnh viễn. Chỉ các delegate có mặt, được cấu hình và được gọi đúng thời điểm mới tham gia.

### Khi nào cần tự khai báo repository?

Với nhiều ứng dụng Servlet dùng Spring Security 6 và form login mặc định, **không cần tự tạo repository** vì framework đã thiết lập cấu hình phù hợp. Chỉ override nếu có yêu cầu cụ thể đã được kiểm thử, chẳng hạn tích hợp custom authentication, thay đổi phạm vi lưu ngữ cảnh hoặc kiểm soát state trong API.

Ví dụ class cấu hình đầy đủ cho một Spring Boot 3.x Servlet app, lựa chọn rõ hai delegate:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .securityContext(context -> context.securityContextRepository(repository))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Có thể bỏ import `SecurityContext` nếu không dùng trong class trên; việc có import dư không thay đổi logic. Ví dụ cấu hình này **không phải chương trình độc lập chỉ với `javac`**. Nó cần dependency Spring Boot MVC/Security, entry point ứng dụng và các controller tương ứng. Vì đây là website dùng form login/session, mặc định CSRF vẫn được áp dụng; không tắt CSRF chỉ để test đăng nhập dễ hơn.

Không ghép ví dụ này với cấu hình `SessionCreationPolicy.STATELESS` rồi ngầm kỳ vọng session tiếp tục giữ context. Nếu chọn stateless, phải thiết kế repository/cơ chế xác thực tương ứng.

## 6. Lưu tường minh trong Spring Security 6: saveContext quan trọng thế nào?

Từ Spring Security 6, `SecurityContextHolderFilter` là mô hình load context phổ biến. Filter này **nạp hoặc cung cấp khả năng nạp context rồi dọn holder**, nhưng **không tự lưu context sau khi logic xử lý kết thúc**. Do đó:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Việc này giúp mã trong cùng luồng xử lý nhìn thấy `authentication` hiện tại; **chưa phải bằng chứng context đã được lưu vào request attribute hoặc HTTP session**.

Nếu logic xác thực do bạn tự cài đặt và muốn lưu lâu hơn, cần thao tác tương tự:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Đây là **mảnh code bên trong component có sẵn các biến** `authentication` (đã được xác thực an toàn), `request`, `response` và `securityContextRepository`; không phải endpoint đăng nhập hoàn chỉnh. Phải lưu **trước khi response được commit** khi cần gửi cookie session, xử lý redirect hay đảm bảo context đã nằm ở repository. Không tự coi một username nhận từ query parameter là bằng chứng xác thực.

Phân biệt với một số ví dụ Spring Security 5 cũ: `SecurityContextPersistenceFilter` từng quản lý cả nạp và lưu tự động khi context thay đổi. Nếu dùng tài liệu cũ để viết custom login ở Security 6, chỉ đặt context vào holder rồi redirect có thể khiến request kế tiếp mất authentication. Hãy đọc cấu hình thực tế của filter và migration guide của phiên bản đang dùng.

**Lưu ý về cơ chế xác thực chuẩn:** Spring Security form login, HTTP Basic, OAuth2 Login và Resource Server có các flow/handler riêng; không nên chèn `saveContext` vào mọi nơi một cách máy móc. Đặc biệt, bearer-token API thường xác thực lại mỗi request; lưu token authentication vào server session có thể đi ngược mục tiêu stateless.

## 7. Demo chạy được với Java 17+ và JUnit: kiểm chứng trực tiếp repository

Ví dụ này tránh tạo một HTTP endpoint “đăng nhập giả” không an toàn. Thay vào đó, dùng **MockHttpServletRequest, MockHttpServletResponse và MockHttpSession** từ Spring Test để kiểm tra chính xác khả năng lưu/nạp của hai repository.

Cấu hình minh họa: **Spring Boot 3.3.5** (quản lý Spring Security 6.x), **Java 17**, Maven. Đây là mốc tái tạo ví dụ, **không khẳng định bản Boot này là bản mới nhất hoặc còn trong kỳ hỗ trợ**. Khi khởi tạo sản phẩm thực tế, chọn một phiên bản còn được hỗ trợ và xác minh dependency, JDK, behavior của chính bản đó.

### 7.1. Tệp pom.xml

Tạo một thư mục mới, đặt `pom.xml` trong thư mục gốc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-context-repositories-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Phụ thuộc Spring Test/AssertJ/JUnit Jupiter có trong `spring-boot-starter-test`. Không tự ép các module Spring Security sang phiên bản khác với BOM Spring Boot.

### 7.2. Tệp test Java

Tạo chính xác tệp `src/test/java/example/securitycontext/SecurityContextRepositoryTest.java`:

```java
package example.securitycontext;

import jakarta.servlet.DispatcherType;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class SecurityContextRepositoryTest {

    private SecurityContext authenticatedContext() {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    @Test
    void requestAttributeSurvivesDispatchWithinTheSameRequest() {
        SecurityContextRepository repository =
            new RequestAttributeSecurityContextRepository();

        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        repository.saveContext(authenticatedContext(), request, response);

        assertThat(repository.loadDeferredContext(request)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        // Vẫn là cùng request object; chỉ đổi loại dispatch.
        request.setDispatcherType(DispatcherType.ERROR);
        assertThat(repository.loadDeferredContext(request)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        MockHttpServletRequest nextRequest = new MockHttpServletRequest();
        assertThat(repository.loadDeferredContext(nextRequest)
                .get().getAuthentication())
            .isNull();
    }

    @Test
    void httpSessionPersistsContextAcrossRequestsSharingTheSession() {
        SecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        MockHttpServletRequest first = new MockHttpServletRequest();
        repository.saveContext(
            authenticatedContext(), first, new MockHttpServletResponse());

        MockHttpSession session = (MockHttpSession) first.getSession(false);
        assertThat(session).isNotNull();

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession(session);
        assertThat(repository.loadDeferredContext(next)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        // Request khác, không có cùng session -> không có authentication cũ.
        MockHttpServletRequest withoutSession = new MockHttpServletRequest();
        assertThat(repository.loadDeferredContext(withoutSession)
                .get().getAuthentication())
            .isNull();
    }

    @Test
    void delegatingRepositoryCanServeCurrentRequestAndNextSessionRequest() {
        SecurityContextRepository repository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        MockHttpServletRequest first = new MockHttpServletRequest();
        repository.saveContext(
            authenticatedContext(), first, new MockHttpServletResponse());

        assertThat(repository.loadDeferredContext(first)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession((MockHttpSession) first.getSession(false));
        assertThat(repository.loadDeferredContext(next)
                .get().getAuthentication().getName())
            .isEqualTo("alice");
    }

    @Test
    void settingTheThreadLocalHolderDoesNotSaveToRepository() {
        SecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        MockHttpServletRequest request = new MockHttpServletRequest();

        SecurityContextHolder.setContext(authenticatedContext());
        try {
            // Chưa gọi repository.saveContext(...).
            assertThat(request.getSession(false)).isNull();
            assertThat(repository.loadDeferredContext(request)
                    .get().getAuthentication())
                .isNull();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

**Điều demo kiểm chứng được:**

- Test 1: request attribute sống trong cùng request object qua mô phỏng `DispatcherType.ERROR`, nhưng không tự tồn tại ở request object mới. Đổi dispatcher type trong unit test **không mô phỏng toàn bộ filter dispatch thực tế của Servlet container**; để kiểm chứng integration ERROR flow còn cần test chạy qua Servlet/Spring Security filter chain.
- Test 2: session repository giữ được authentication qua request khác khi cấp cùng `MockHttpSession`; không có session thì không lấy lại context cũ.
- Test 3: delegating repository vừa phục vụ request hiện tại vừa duy trì thông tin qua session.
- Test 4: `SecurityContextHolder.setContext` không tự thay thế thao tác lưu của repository. Dọn holder trong `finally` để test không rò context vào test khác.

### 7.3. Chạy test

Trên máy có JDK 17+ hỗ trợ Maven và tải được dependencies:

```bash
java -version
mvn -version
mvn test
```

Nếu chạy đúng cấu trúc project ở trên, kỳ vọng **4 test thành công**, không có lỗi biên dịch. stdout Maven khác nhau theo môi trường, plugin, cache và phiên bản; không khẳng định một log build cụ thể nếu chưa thực thi. Các test không cần khởi động web server, bởi chúng kiểm chứng trực tiếp contract của repository bằng mock Servlet objects.

**Tại sao không dùng `javac` một mình?** Test phụ thuộc Spring Security Web, Spring Test, JUnit và AssertJ nên phải biên dịch với classpath do Maven resolve. Với một chương trình Java chuẩn chỉ dùng JDK, `javac`/`java` có thể chạy trực tiếp, còn ví dụ ở đây là một module test của project Spring.

## 8. Chọn repository theo chiến lược session

`SessionCreationPolicy` của Spring Security giúp kiểm soát cách sử dụng HTTP session trong authentication và security context.

| Chính sách | Mục đích | Tác động cần nhớ |
|---|---|---|
| `ALWAYS` | Spring Security có thể chủ động tạo session | Phù hợp khi đã thiết kế sử dụng state/session |
| `IF_REQUIRED` | Chỉ tạo session khi cần | Phổ biến với website dùng login/session |
| `NEVER` | Spring Security không tự tạo session nhưng có thể dùng session đã có | Không tương đương stateless hoàn toàn |
| `STATELESS` | Spring Security không tạo session và không dùng session để lấy SecurityContext | Phù hợp API xác thực lại mỗi request, ví dụ bearer token |

`STATELESS` không tự động vô hiệu mọi cơ chế có thể tạo session trong **toàn bộ ứng dụng**: controller, Servlet component hoặc framework khác vẫn có thể sử dụng session nếu tự được cấu hình như vậy. Nó cũng **không tự tắt CSRF**; quyết định CSRF phải dựa trên cách client gửi credentials, nhất là khi trình duyệt tự gửi cookie.

Ví dụ đối chiếu một API bearer-token Servlet (đoạn cấu hình, không phải file Java độc lập):

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .build();
}
```

Ứng dụng REST stateless phải thêm starter Resource Server và cấu hình issuer/JWK tin cậy, issuer/audience theo yêu cầu. Với API như vậy, mỗi request cung cấp và được kiểm chứng bằng bearer token; **không sử dụng HTTP session repository để thay thế việc kiểm chứng token**. Security context vẫn có thể tồn tại trong một request để xử lý endpoint và method security.

Ngược lại, website form login thường cần duy trì context qua session. Chọn duy nhất `RequestAttributeSecurityContextRepository` cho flow login kiểu session sẽ làm mất khả năng khôi phục authentication ở request tiếp theo, trừ khi có một cơ chế khác độc lập cung cấp lại context.

## 9. ERROR dispatch, FORWARD, async và ranh giới request

Một Servlet request có thể đi qua nhiều lần dispatch:

- **`REQUEST`:** xử lý request từ client.
- **`FORWARD`:** chuyển nội bộ tới resource khác trong cùng request.
- **`ERROR`:** dispatch tới error page khi có lỗi, có thể xảy ra sau khi security filter dọn holder theo trình tự container.
- **`ASYNC`:** có thể tiếp tục xử lý bất đồng bộ với thread/dispatch khác.

`RequestAttributeSecurityContextRepository` giữ dữ liệu gắn với request object; nhưng **không được suy ra mọi thread bất đồng bộ tự động mang SecurityContextHolder**. Với async execution hoặc thread pool, chiến lược truyền context còn liên quan tích hợp async, Reactor/Executor wrapper và cấu hình bảo mật. Đây là hai câu hỏi riêng: “context lưu ở đâu?” và “context được truyền tới đoạn thực thi nào?”.

Nếu một request vào endpoint bảo vệ rồi forward sang resource khác, đừng coi các authorization rules của dispatcher type đương nhiên giống nhau. Spring Security có thể áp dụng filter cho các dispatcher type được cấu hình; cần xác định quyền đối với FORWARD/ERROR và dùng test để tránh chặn nhầm error page hoặc mở quá rộng.

**Ví dụ cần kiểm thử tích hợp thực tế:** một user hợp lệ truy cập endpoint ném exception; lỗi được xử lý bởi `/error` sau một dispatch mới. Bạn muốn trang lỗi thể hiện đúng principal nhưng không muốn cấp quyền xem dữ liệu nhạy cảm. Cần kiểm tra đồng thời (1) mapping/filter chạy cho ERROR dispatch; (2) request attribute còn sống; (3) authorization của ERROR endpoint hợp lệ; (4) response cuối cùng không rò thông tin ngoài dự định.

## 10. Thời điểm lưu, context mới và an toàn luồng

Khi tự đăng nhập, nên tạo context mới bằng `SecurityContextHolder.createEmptyContext()` rồi đặt Authentication đã được xác thực, thay vì sửa một context có thể đang được dùng/chia sẻ ngoài ý muốn:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

**Đây là pseudocode Java ở phạm vi custom authentication handler**: biến `authenticatedAuthentication` phải đến từ cơ chế xác thực hợp lệ; `request`, `response`, `securityContextRepository` phải được inject/trao đúng vòng đời. Không coi chuỗi username hoặc header tùy ý là danh tính đã được chứng minh.

- **Lưu trước redirect / commit response:** trong session flow, nếu phải tạo session mới thì response cần cơ hội gửi session cookie về client.
- **Dọn context khi kết thúc request:** holder có chiến lược thread-local ở Servlet stack; web security filter dọn holder sau request. Custom thread pool cần cơ chế propagation và clear context phù hợp.
- **Logout:** dùng cơ chế logout của Spring Security để xóa authentication, xử lý session và security context theo chính sách. Việc chỉ `SecurityContextHolder.clearContext()` trong một thread không nhất thiết xóa context đã lưu trong session cho request sau.
- **Session fixation/concurrency:** session management cần bảo vệ riêng khi đăng nhập, thay session id theo cấu hình hỗ trợ và kiểm soát số phiên nếu nghiệp vụ yêu cầu.
- **Nhất quán quyền:** nếu roles/authorities đổi khi session còn tồn tại, có thể cần cập nhật context, reauthenticate hoặc hủy session. Repository không phải công cụ tự động đồng bộ quyền với IAM.

Đừng tùy ý gọi `HttpSession.invalidate()` từ nhiều nơi rồi kỳ vọng tất cả security context/cookie downstream được xử lý đúng; dùng logout/session management mechanism được xác định và kiểm thử.

## 11. Chẩn đoán lỗi thường gặp

| Hiện tượng | Cơ chế nên kiểm tra | Cách điều tra |
|---|---|---|
| Login trả redirect thành công nhưng request kế tiếp thành anonymous | Context chỉ gắn request hoặc custom login quên `saveContext`; session cookie không đi qua | Kiểm tra repository đang dùng, log save/load, `Set-Cookie`/`Cookie`, redirect timing |
| ERROR page không thấy Authentication đã xác thực | Holder bị dọn trước ERROR dispatch, thiếu request-attribute delegate hoặc filter mapping khác | Kiểm tra dispatch type, request attribute, chain và rule cho `/error` |
| App API bearer token tạo session ngoài ý muốn | Flow/form login, CSRF, MVC component hoặc custom code sử dụng HttpSession | Kiểm tra chain, `SessionCreationPolicy`, `JSESSIONID`, các thành phần tạo session |
| `SecurityContextHolder.getContext().getAuthentication()` trả `null` | Không có Authentication cho request hoặc chưa được load | Kiểm tra filter security, thứ tự, repository, credential và loại dispatch |
| Sau logout request kế tiếp vẫn thấy user | Session context chưa bị xóa/invalidated hoặc IdP/login flow xác thực lại | Kiểm tra logout handler, session, cookie, remember-me và SSO |
| Qua request khác vẫn có user dù chỉ khai báo request-attribute repository | Một cơ chế khác đang xác thực lại hoặc còn session/security chain thứ hai | Kiểm tra các bean `SecurityFilterChain`, filter khác, bearer/basic credentials |
| Test chạy độc lập pass nhưng chạy cả suite fail | SecurityContextHolder không được clear hoặc MockHttpSession dùng lại bất ngờ | Xóa context trong `finally`, cô lập mock request/session từng test |
| Trên cụm nhiều node, login lúc được lúc mất | Session không được chia sẻ/affinity thiếu, cookie/secret khác | Kiểm tra hạ tầng Servlet sessions/Spring Session và proxy routing |
| Ở async thread không thấy principal | Context chưa được propagate qua thread/executor | Kiểm tra async wrapper và thời điểm capture/clear security context |

Đừng chẩn đoán “session không hoạt động” chỉ dựa vào `SecurityContextHolder` trống sau khi response kết thúc. Việc holder được dọn là bình thường; câu hỏi là **repository có giữ và nạp đúng context cho request tiếp theo không**.

## 12. Quy trình lựa chọn trong ứng dụng Servlet

1. **Xác định cách xác thực:** form login/session, HTTP Basic, OAuth2 Login hay stateless bearer JWT/opaque token. Từng cơ chế có cách duy trì authentication khác nhau.
2. **Xác định độ dài vòng đời cần thiết:** chỉ request hiện tại, nhiều dispatch của cùng request, hay nhiều request trong cùng session.
3. **Đọc cấu hình thực tế:** có bao nhiêu `SecurityFilterChain`, dùng `SecurityContextHolderFilter` hay filter đời cũ, có custom repository không, policy session là gì.
4. **Giữ mặc định khi đáp ứng yêu cầu:** với ứng dụng Spring Security 6 dạng web login, delegating repository kết hợp request attribute và session thường đã giải quyết tốt hai phạm vi.
5. **Nếu custom authentication:** kiểm tra context mới được đặt vào holder và được lưu qua repository đúng lúc, trước khi commit response.
6. **Nếu stateless:** không dựa vào session giữ authentication; xác thực bằng chứng mỗi request; không tắt CSRF tùy tiện khi client còn dùng browser cookies.
7. **Kiểm thử hai góc nhìn:** cùng request qua dispatch khác và request mới với/không có session, thêm login/logout, error handling, session timeout và chạy sau redirect.

### Tự kiểm tra

**Câu 1.** `RequestAttributeSecurityContextRepository` đã lưu context cho `REQUEST` dispatch. Khi xảy ra `ERROR` dispatch cùng request, context có thể được nạp lại không?  
**Đáp án:** Có, nếu dispatch thực sự dùng cùng request attributes và Spring Security/security chain có tải repository; mục đích chính là giữ context qua các dispatch của cùng request.

**Câu 2.** Vì sao request mới dùng cùng `JSESSIONID` có thể tìm lại authentication từ `HttpSessionSecurityContextRepository`?  
**Đáp án:** Vì server dùng session identifier để tìm lại `HttpSession` chứa context đã được lưu. Điều này phụ thuộc session hợp lệ, context đã save và cấu hình security repository.

**Câu 3.** Custom authentication đặt `SecurityContextHolder.setContext(context)` rồi redirect nhưng không `saveContext`. Request sau chắc chắn còn đăng nhập chứ?  
**Đáp án:** Không. Trong mô hình explicit-save của Spring Security 6, holder chỉ phục vụ quá trình xử lý hiện tại; context cần được lưu vào repository phù hợp nếu muốn tồn tại qua redirect.

**Câu 4.** Ứng dụng dùng `SessionCreationPolicy.STATELESS` có nên dựa vào `HttpSessionSecurityContextRepository` để giữ JWT authentication không?  
**Đáp án:** Không. Stateless Resource Server nên kiểm tra bearer token ở mỗi request; không coi server session là nơi duy trì trạng thái xác thực.

**Câu 5.** Dùng delegating repository có phải tất cả request đều tự tạo session?  
**Đáp án:** Không. Delegate HttpSession có logic tránh tạo session không cần thiết; tạo session còn phụ thuộc context, cấu hình và các thành phần khác của ứng dụng.

**Ghi nhớ:** `RequestAttributeSecurityContextRepository` giải quyết **vòng đời bên trong một HTTP request, kể cả dispatch khác**; `HttpSessionSecurityContextRepository` giải quyết **khôi phục SecurityContext giữa nhiều request của cùng session**. `DelegatingSecurityContextRepository` có thể kết hợp cả hai. Repository quyết định nơi lưu, còn web security filter, authentication mechanism và lời gọi `saveContext` quyết định thời điểm nạp/lưu context an toàn.