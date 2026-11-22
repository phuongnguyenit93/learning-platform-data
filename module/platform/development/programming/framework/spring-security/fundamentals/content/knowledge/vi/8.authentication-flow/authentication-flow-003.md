# ProviderManager chọn AuthenticationProvider phù hợp trong Spring Security

Khi một request gửi username/password, HTTP Basic, JWT hoặc một loại credential riêng, Spring Security cần biết **thành phần nào có thể kiểm chứng credential đó**. Một implementation phổ biến của AuthenticationManager là **ProviderManager**: nó duyệt danh sách AuthenticationProvider đã đăng ký, hỏi provider có hỗ trợ kiểu Authentication đang nhận không, rồi ủy quyền xác thực cho provider phù hợp theo thứ tự.

Vấn đề dễ nhầm là **ProviderManager không luôn chọn đúng một provider rồi dừng ngay**. Một provider có thể không hỗ trợ loại token, có thể hỗ trợ nhưng trả null để nhường provider khác, có thể trả Authentication xác thực thành công, hoặc ném AuthenticationException. Thứ tự và loại lỗi ảnh hưởng quyết định tiếp theo.

Bài học thuộc nhóm **Luồng xác thực** của Spring Security fundamentals. Mục tiêu là hiểu chính xác đường đi từ authentication filter tới AuthenticationManager, cách ProviderManager hợp tác với các provider, và cách chẩn đoán những lỗi như BadCredentialsException, ProviderNotFoundException hoặc 401. Phần thực hành dùng **Java 17+, Spring Boot 3.3.6 và Spring Security 6.x**, có project Maven và kiểm thử MockMvc/JUnit cho hai provider khác kiểu: **DaoAuthenticationProvider** và một **AuthenticationProvider tùy biến cho API key**. API key là mô hình thử nghiệm cục bộ, không phải cơ chế cấp API key production hoàn chỉnh.

## 1. Vai trò của ProviderManager trong một request

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["Authentication filter phù hợp"]
    F --> T["Authentication request token: chưa xác thực"]
    T --> M["AuthenticationManager.authenticate(request)"]
    M --> PM["ProviderManager"]
    PM --> P1{"Provider #1 supports(token class)?"}
    P1 -- "Không" --> P2{"Provider #2 supports(token class)?"}
    P1 -- "Có" --> A1["Provider #1 authenticate(token)"]
    A1 --> S{"Kết quả"}
    S -- "Authentication thành công" --> OK["Trả Authentication đã xác thực"]
    S -- "null hoặc lỗi có thể thử tiếp" --> P2
    P2 -- "Có" --> A2["Provider #2 authenticate(token)"]
    P2 -- "Không" --> FALL["Provider kế tiếp / parent nếu có"]
    A2 --> FINAL["Authentication hoặc AuthenticationException"]
    OK --> CTX["Filter sử dụng kết quả và xử lý SecurityContext"]
    FINAL --> CTX
~~~

Sơ đồ giản lược: một số ngoại lệ **dừng ngay** và không thử provider kế tiếp; chính sách parent, event và credentials erasure cũng ảnh hưởng luồng thực tế. Các nhánh này được phân tích bên dưới.

Tách hai trách nhiệm:

- **Authentication filter** đọc request, trích credential, dựng một Authentication request (thường có isAuthenticated=false), gọi AuthenticationManager, sau đó xử lý SecurityContext/response theo cơ chế.
- **ProviderManager** nhận Authentication từ filter, quyết định thử các AuthenticationProvider nào, nhận kết quả hoặc ngoại lệ. Nó **không tự đọc mọi header HTTP**, không tự chuyển một X-API-Key bất kỳ thành token, và không tự ghi SecurityContext chỉ nhờ việc authenticate() được gọi.

Một filter HTTP Basic thường đưa username/password vào **UsernamePasswordAuthenticationToken**; DaoAuthenticationProvider thường có thể xử lý kiểu đó. Một authentication filter cho JWT có thể đưa **BearerTokenAuthenticationToken** hoặc kiểu phù hợp cho cơ chế Bearer; JwtAuthenticationProvider thuộc một cấu hình Resource Server thích hợp. Với một loại API key tự thiết kế, bạn cần cả **token, provider, filter/converter và cấu hình chain** tương ứng nếu muốn gọi qua HTTP.

## 2. Bốn interface/kiểu phải phân biệt

| Thành phần | Contract chính | Trách nhiệm |
| --- | --- | --- |
| **Authentication** | getPrincipal(), getCredentials(), getAuthorities(), isAuthenticated() | Mang yêu cầu xác thực hoặc kết quả xác thực. |
| **AuthenticationManager** | authenticate(Authentication) | Giao diện cấp cao thực hiện xác thực. |
| **ProviderManager** | authenticate(...) với danh sách providers | Implementation của AuthenticationManager, lần lượt ủy quyền cho provider thích hợp. |
| **AuthenticationProvider** | supports(Class<?>), authenticate(Authentication) | Có thể xác thực một hoặc nhiều kiểu Authentication cụ thể. |

Một số kiểu quen thuộc:

| Kiểu | Vai trò điển hình |
| --- | --- |
| **UsernamePasswordAuthenticationToken** | Username/password trong HTTP Basic, form login hoặc một số luồng tự xây. |
| **DaoAuthenticationProvider** | Xác minh username/password thông qua UserDetailsService và PasswordEncoder. |
| **JwtAuthenticationProvider** | Xác minh JWT qua JwtDecoder được cấu hình trong Resource Server. |
| **BearerTokenAuthenticationToken** | Authentication request biểu diễn Bearer token trước khi được xác minh. |
| **AbstractAuthenticationToken** | Lớp cơ sở hữu ích khi tạo token dành cho cơ chế xác thực tùy biến. |
| **SecurityContext** | Chứa Authentication được gắn cho ngữ cảnh bảo mật đang xử lý. |

**Tên AuthenticationProvider không phải một vai trò người dùng.** Một provider quyết định **credential có hợp lệ không và tạo Authentication nào**, còn quy tắc hasRole, hasAuthority, authenticated hoặc chính sách quyền đối tượng được thực hiện ở bước authorization tương ứng.

### 2.1. Authentication request khác kết quả Authentication

Trước xác thực, một token có thể chứa:

~~~text
UsernamePasswordAuthenticationToken
  principal   = "alice"
  credentials = "(password từ request)"
  authenticated = false
  authorities = []
~~~

Sau DaoAuthenticationProvider xác minh thành công, đối tượng trả về có thể chứa:

~~~text
UsernamePasswordAuthenticationToken
  principal   = UserDetails(alice)
  credentials = "(sẽ được xóa nếu cơ chế erase credentials áp dụng)"
  authenticated = true
  authorities = [ROLE_USER]
~~~

Một token sau xác thực **không nhất thiết cùng object** với token đầu vào, dù có thể cùng class. Không dùng flag isAuthenticated=true do client gửi hoặc tự sửa trên một token không đáng tin để thay cho kiểm chứng mật khẩu, chữ ký hay API key.

## 3. Contract supports(Class<?>): bước lọc theo kiểu

Interface AuthenticationProvider có phương thức:

~~~java
boolean supports(Class<?> authentication);
~~~

ProviderManager gọi supports() để biết provider có thể xem xét **class của Authentication request** hay không. Trong custom provider, biểu thức phổ biến:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return DemoApiKeyAuthenticationToken.class
        .isAssignableFrom(authenticationType);
}
~~~

Ý nghĩa:

- Nếu request là DemoApiKeyAuthenticationToken hoặc subclass của nó, provider có thể xử lý.
- Nếu request là UsernamePasswordAuthenticationToken, API-key provider trên thường trả false.
- Nếu supports() trả false, ProviderManager **bỏ qua authenticate() của provider này** và xét provider khác.
- Nếu supports() trả true, điều đó mới có nghĩa **đáng thử xác thực**, chưa phải chứng minh credential hợp lệ. authenticate() vẫn có thể trả null hoặc ném AuthenticationException.

Không nên viết supports() theo tên header, đường URL hay role đã cấp; interface chỉ nhận **Class<?>**, không nhận HttpServletRequest. Việc phân biệt request theo path/HTTP header để tạo đúng kiểu Authentication là trách nhiệm của authentication filter/converter hoặc cách tổ chức SecurityFilterChain.

**Ví dụ sai:**

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return true;
}
~~~

Một provider tự nhận hỗ trợ mọi loại token sẽ bị gọi cho cả token mà nó không hiểu. Nếu implementation tiếp tục ép kiểu UsernamePasswordAuthenticationToken sang token tùy biến, có thể phát sinh ClassCastException hoặc lỗi xử lý không nhất quán. Chỉ trả true cho những kiểu mà provider thật sự biết cách đánh giá.

## 4. authenticate(Authentication): ba kết quả cơ bản

Chữ ký chính:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Một AuthenticationProvider có ba kiểu kết quả có ý nghĩa:

| Kết quả từ provider | Ý nghĩa | ProviderManager thường làm tiếp |
| --- | --- | --- |
| **Trả Authentication khác null** | Provider đã xác thực thành công và đưa ra kết quả. | **Dừng** việc thử provider tiếp theo, trả kết quả sau xử lý cuối. |
| **Trả null** | Provider không thể kết luận/không xử lý được instance này. | Thử provider tiếp theo có supports() phù hợp; có thể xét parent. |
| **Ném AuthenticationException** | Xác thực thất bại hoặc điều kiện liên quan. | Tùy loại exception: có thể ghi nhớ và thử provider tiếp theo; một số loại dừng ngay. |

Lưu ý hai điểm:

1. **null khác với sai mật khẩu**. Một provider trả null đang nói “tôi không quyết định”, không phải “tôi đã xác nhận credential sai”.
2. **supports=true không đồng nghĩa authenticate phải thành công**. Có thể cùng kiểu UsernamePasswordAuthenticationToken nhưng hai provider phục vụ hai nguồn danh tính hoặc realm khác nhau.

Hợp đồng này cho phép ProviderManager hỗ trợ nhiều cơ chế hoặc nhiều nguồn xác thực dưới cùng một AuthenticationManager. Tuy nhiên tính linh hoạt khiến cần thiết kế **thứ tự, điều kiện provider, cách phân loại lỗi và chính sách fail closed** một cách rõ ràng.

### 4.1. Vì sao không nên trả null khi credential chắc chắn sai?

Giả sử một API-key provider hỗ trợ DemoApiKeyAuthenticationToken và đã xác minh rằng key được gửi là không hợp lệ. Nếu nó trả null, một provider khác cùng hỗ trợ kiểu token có thể thử và chấp nhận key theo chính sách khác ngoài dự định.

Trong ví dụ cơ bản, hãy ném **BadCredentialsException** khi key sai. Khi có nhiều provider cùng supports một token, chỉ dựa vào BadCredentialsException để bảo đảm không thử provider khác vẫn chưa đủ: ProviderManager có thể tiếp tục đến provider sau và chấp nhận nếu provider sau thành công. Muốn tách hoàn toàn các miền danh tính, nên dùng **loại Authentication riêng, manager/chain riêng, hoặc điều kiện chọn nguồn xác thực không nhập nhằng**.

### 4.2. ProviderNotFoundException là gì?

Khi không có provider nào xử lý được kiểu token và không có parent đưa ra kết quả, ProviderManager có thể ném:

~~~text
ProviderNotFoundException: No AuthenticationProvider found for ...
~~~

Đây là **lỗi cấu hình/kiểu token**, không phải chứng minh người dùng đã nhập sai password. Ví dụ bạn tạo CustomOtpAuthenticationToken nhưng chỉ đăng ký DaoAuthenticationProvider, nên không có provider phù hợp với token OTP.

Phân biệt:

- **BadCredentialsException**: provider phù hợp đã thử và credential không hợp lệ.
- **ProviderNotFoundException**: không có provider xử lý được kiểu Authentication request theo cấu hình hiện tại.
- **AccessDeniedException**: thường là vấn đề authorization sau hoặc ngoài bước xác thực, không đồng nghĩa ProviderManager không tìm thấy provider.

## 5. Thuật toán lựa chọn theo thứ tự

Giả sử ProviderManager có:

~~~text
ProviderManager
  providers[0] = DemoApiKeyAuthenticationProvider
  providers[1] = DaoAuthenticationProvider
  parent       = null
~~~

Request A là UsernamePasswordAuthenticationToken:

1. API-key provider.supports(UsernamePasswordAuthenticationToken.class) trả false → bỏ qua.
2. DAO provider.supports(...) trả true → thử user/password.
3. Nếu đúng, DAO trả Authentication đã xác thực → ProviderManager dừng.
4. Nếu sai, DAO ném BadCredentialsException → không còn provider phù hợp sau đó → request thất bại.

Request B là DemoApiKeyAuthenticationToken:

1. API-key provider.supports(DemoApiKeyAuthenticationToken.class) trả true.
2. API-key provider kiểm key. Key đúng → trả Authentication đã xác thực → dừng.
3. DAO provider **không bị gọi**, dù vẫn nằm trong danh sách.
4. Key sai → BadCredentialsException; DAO không supports custom token nên không có fallback thành công.

Bảng quyết định:

| Input token | API-key provider | DAO provider | Kết quả mong đợi |
| --- | --- | --- | --- |
| UsernamePasswordAuthenticationToken của alice, password đúng | supports=false | supports=true, thành công | Principal alice, ROLE_USER. |
| UsernamePasswordAuthenticationToken của alice, password sai | supports=false | supports=true, lỗi | BadCredentialsException. |
| DemoApiKeyAuthenticationToken với key demo đúng | supports=true, thành công | Không thử | Principal batch-service, ROLE_SERVICE. |
| DemoApiKeyAuthenticationToken với key sai | supports=true, lỗi | supports=false | BadCredentialsException. |
| Loại Authentication không ai hỗ trợ | supports=false | supports=false | ProviderNotFoundException. |

**Thứ tự thực sự quan trọng** khi **nhiều provider hỗ trợ cùng một kiểu token**. Với hai provider khác kiểu như bảng trên, thứ tự không ảnh hưởng kết quả thông thường, nhưng vẫn nên viết rõ để dễ đọc và kiểm thử.

### 5.1. Pseudocode có chú thích

~~~java
// Pseudocode để hiểu ProviderManager, không phải source code Spring Security.
Authentication authenticate(Authentication request) {
    AuthenticationException lastFailure = null;

    for (AuthenticationProvider provider : providers) {
        if (!provider.supports(request.getClass())) {
            continue;
        }

        try {
            Authentication result = provider.authenticate(request);

            if (result != null) {
                return postProcessSuccessfulAuthentication(result);
            }
        } catch (AccountStatusException critical) {
            throw critical; // Dừng ngay.
        } catch (InternalAuthenticationServiceException critical) {
            throw critical; // Dừng ngay theo cơ chế ProviderManager.
        } catch (AuthenticationException failure) {
            lastFailure = failure;
            // Có thể xét provider kế tiếp.
        }
    }

    // Nếu chưa có result, có thể hỏi parent AuthenticationManager.
    // Sau đó quyết định ném failure hoặc ProviderNotFoundException.
    throw selectFinalFailure(lastFailure);
}
~~~

Pseudocode cố ý bỏ qua một số chi tiết của Spring Security như message source, event publishing, exception parent và eraseCredentials. Đừng chép nó vào dự án rồi coi là implementation của Spring Security.

### 5.2. Nếu provider đầu ném BadCredentialsException?

Một chi tiết dễ gây sai lầm: khi provider đầu **ném BadCredentialsException**, ProviderManager **có thể thử các provider sau**. Nếu một provider sau thành công, kết quả thành công được dùng và lỗi trước có thể bị bỏ qua. Nếu không provider nào thành công, ngoại lệ cuối phù hợp thường được ném.

Vì thế không thể nói “provider đầu có supports=true là người quyết định cuối cùng”. Supports chỉ chọn những provider có khả năng thử; **kết quả thực thi** mới quyết định.

### 5.3. Những exception làm dừng tìm kiếm

Trong ProviderManager của Spring Security 6.x, **AccountStatusException** (ví dụ tài khoản bị khóa/vô hiệu hóa theo cơ chế kiểm tra tương ứng) và **InternalAuthenticationServiceException** thuộc các trường hợp dừng sớm, không tiếp tục thử provider khác như một đường vòng. Điều này ngăn việc vô tình thử một nguồn khác để vượt qua một số trạng thái tài khoản hoặc lỗi dịch vụ nội bộ.

Không tự viết custom provider bắt mọi AuthenticationException rồi trả null, vì nó có thể biến lỗi có ý nghĩa thành một nhánh fallback. Khi một lỗi là từ chối có chủ đích, hãy dùng exception phù hợp và test rằng không có provider khác cho phép lách chính sách.

## 6. ProviderManager với parent AuthenticationManager

ProviderManager có thể có một **parent AuthenticationManager** tùy chọn. Khi danh sách provider cục bộ chưa tạo được kết quả, parent có thể được tham vấn theo hành vi được Spring Security hỗ trợ. Đây là cơ chế hữu ích trong một số hệ thống có nhiều SecurityFilterChain dùng chung nguồn authentication nhưng mỗi chain lại có provider riêng.

~~~text
ProviderManager dành cho /admin/**
  local providers:
    AdminCertificateAuthenticationProvider
  parent:
    SharedProviderManager
      providers:
        DaoAuthenticationProvider
~~~

Mô hình trên chỉ để giải thích **hệ phân cấp manager**; ứng dụng thực tế phải lựa chọn rõ endpoint nào cho phép fallback tới user/password và endpoint nào yêu cầu chứng chỉ. Nếu chính sách admin **bắt buộc client certificate**, việc gắn parent DAO vào chain admin có thể vô tình cho phép đăng nhập bằng mật khẩu thay cho chứng chỉ.

Những nguyên tắc:

- Parent là **AuthenticationManager**, không nhất thiết là một ProviderManager khác.
- Không phải mọi request đều đi qua parent: provider cục bộ có thể thành công trước.
- Parent không có nghĩa là fallback vô điều kiện sau mọi AuthenticationException; có ngoại lệ được dừng sớm.
- Khi cấu hình chain cha/con, cần test đúng **loại token**, thứ tự và các trường hợp credential sai/bị khóa.
- Không tạo vòng lặp parent giữa các manager.

**Có nhiều SecurityFilterChain không tự chứng minh rằng chúng dùng cùng ProviderManager.** Mỗi chain có thể cấu hình AuthenticationManager riêng; muốn hiểu thực tế, hãy xem bean wiring và securityMatcher.

## 7. DaoAuthenticationProvider là ví dụ chuẩn

**DaoAuthenticationProvider** là provider dùng phổ biến khi có username/password. Nó thường được cấu hình với:

- **UserDetailsService**: tìm tài khoản theo username, trả UserDetails hoặc báo không tìm thấy.
- **PasswordEncoder**: kiểm password trong request với password hash đã lưu.
- **UserDetails**: chứa username, hash, account flags (enabled/locked/expired...) và authorities.
- Các policy/cache/checker liên quan theo cấu hình.

Mô hình:

~~~text
UsernamePasswordAuthenticationToken
    principal = username
    credentials = raw password từ request
            |
            v
DaoAuthenticationProvider
    -> UserDetailsService.loadUserByUsername(username)
    -> Kiểm trạng thái account
    -> PasswordEncoder.matches(rawPassword, encodedPassword)
    -> Tạo Authentication đã xác thực và authorities
            |
            v
ProviderManager
    -> Trả Authentication thành công hoặc AuthenticationException
~~~

**DaoAuthenticationProvider không tự truy vấn HTTP body hoặc header**. HttpBasic, formLogin hoặc filter tùy biến chuyển credential HTTP thành UsernamePasswordAuthenticationToken. Nếu dùng HTTP Basic, BasicAuthenticationFilter là một thành phần quan trọng ở lớp trước.

**Không lưu password plain text** vào UserDetails thật. PasswordEncoder thích hợp cho mật khẩu lưu lâu dài có cơ chế hash và chi phí xử lý phù hợp, ví dụ BCrypt hoặc encoder được tổ chức chấp nhận. Lựa chọn thuật toán/cost cần theo chính sách bảo mật và hiệu năng của hệ thống.

### 7.1. HTTP Basic và form login có nhất thiết là hai provider khác nhau?

**Không.** Hai authentication filter khác nhau có thể đều tạo UsernamePasswordAuthenticationToken và sử dụng một DaoAuthenticationProvider chung. Việc filter lấy credential ở Basic header hay HTML form không làm thay đổi bản chất đối chiếu password.

Điều này giúp tách **credential transport mechanism** (Basic, form) khỏi **provider xác thực danh tính** (DAO, LDAP, external service). Không tạo một AuthenticationProvider mới chỉ vì muốn đổi trang login hoặc response JSON.

## 8. Dự án hoàn chỉnh: ProviderManager có hai provider khác loại

Project sau có:

- Một **DaoAuthenticationProvider** kiểm user/password của HTTP Basic.
- Một **DemoApiKeyAuthenticationProvider** tự xây, nhận một kiểu token riêng.
- Một **ProviderManager** chứa hai provider theo thứ tự rõ ràng.
- Một **SecurityFilterChain** dùng chính AuthenticationManager được khai báo.
- Các endpoint GET công khai, GET cần đăng nhập và GET chỉ dành cho ADMIN.
- Bộ test gọi trực tiếp ProviderManager với cả hai kiểu token, đồng thời kiểm HTTP Basic bằng MockMvc.

**Điểm sư phạm quan trọng:** API-key provider được đăng ký để minh họa **lựa chọn theo kiểu token**. Project này **chưa có HTTP filter chuyển X-API-Key thành DemoApiKeyAuthenticationToken**, vì vậy header X-API-Key gửi trực tiếp tới /api/me **không tự tạo đăng nhập**. Đây là hành vi được kiểm thử có chủ đích; phần 12 giải thích cách nối provider vào một HTTP authentication flow nếu cần.

Yêu cầu **JDK 17+, Maven 3.9+** và cổng 8080 trống. Dùng tài khoản/key giả, chỉ chạy trên localhost; nếu triển khai thực tế phải thay cơ chế cấp và quản lý credential phù hợp.

### 8.1. Cấu trúc thư mục

~~~text
provider-manager-demo/
  pom.xml
  src/main/java/com/example/providers/
    ProviderRoutingApplication.java
    ApiController.java
    DemoApiKeyAuthenticationToken.java
    DemoApiKeyAuthenticationProvider.java
    SecurityConfig.java
  src/test/java/com/example/providers/
    ProviderRoutingTests.java
~~~

Các lớp cùng package **com.example.providers** để Spring Boot tìm các bean.

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>provider-manager-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.3.6 quản lý các phiên bản Spring Security 6.x tương thích qua dependency management; ví dụ không ghi đè riêng version của spring-security-core để tránh lệch bộ thư viện.

**Chú ý:** xsd/maven trong dòng schemaLocation là để công cụ hiểu cấu trúc POM. Nếu tạo project Maven mới, có thể sử dụng đúng định dạng schemaLocation chính thức:

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

Dòng trên là mảnh của root element, không phải một thẻ XML độc lập. Trong project thật nên dùng một dạng schemaLocation hợp lệ và nhất quán.

### 8.3. ProviderRoutingApplication.java

~~~java
package com.example.providers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProviderRoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProviderRoutingApplication.class, args);
    }
}
~~~

Class này khởi chạy Spring Boot và quét Controller/Configuration cùng package. Không dùng code trong main để tự xác thực user khi nhận HTTP request.

### 8.4. ApiController.java

~~~java
package com.example.providers;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("name", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
~~~

Controller không kiểm username/password, API key hoặc role từ header thô. Các yêu cầu authorization nằm ở SecurityFilterChain; riêng GET /api/admin cần ROLE_ADMIN.

### 8.5. DemoApiKeyAuthenticationToken.java

Đây là **kiểu Authentication request mới**, khác UsernamePasswordAuthenticationToken. Nó kế thừa AbstractAuthenticationToken và tách constructor token chưa xác thực với factory tạo kết quả đã xác thực:

~~~java
package com.example.providers;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class DemoApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private final String apiKey;

    // Đầu vào chưa tin cậy: chỉ dùng sau khi filter/logic nhận key.
    public DemoApiKeyAuthenticationToken(String apiKey) {
        super(List.of());
        this.principal = "unverified-api-key";
        this.apiKey = apiKey;
        super.setAuthenticated(false);
    }

    // Kết quả chỉ được tạo sau khi một provider đáng tin đã kiểm key.
    private DemoApiKeyAuthenticationToken(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = principal;
        this.apiKey = null;
        super.setAuthenticated(true);
    }

    static DemoApiKeyAuthenticationToken authenticated(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        return new DemoApiKeyAuthenticationToken(
            principal, authorities
        );
    }

    @Override
    public Object getCredentials() {
        return apiKey;
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Only a verified provider may create an authenticated token"
            );
        }
        super.setAuthenticated(false);
    }
}
~~~

Các quyết định bảo mật:

- Constructor public tạo token với **authenticated=false**. Dù người gọi biết key hay không, token mới không được tự coi là đã xác thực.
- Factory authenticated(...) có quyền truy cập trong package, được dùng bởi DemoApiKeyAuthenticationProvider sau khi key được kiểm. Nó không đọc trực tiếp dữ liệu client để tạo authority.
- Override setAuthenticated(true) ngăn code thông thường đổi một token chưa kiểm chứng thành authenticated bằng setter.
- Kết quả được xác thực **không giữ apiKey trong credentials**. Đây là lựa chọn tốt hơn so với giữ raw key trong SecurityContext.
- Tuy nhiên, một factory ở package scope **không phải security boundary chống mã độc cùng tiến trình**; độ tin cậy của Java classpath và Spring bean configuration vẫn phải được kiểm soát.
- Trong production, không dùng một API key cố định hard-code; cần kho secret, vòng đời key, rotation, revocation, hash, audit và rate limit phù hợp.

### 8.6. DemoApiKeyAuthenticationProvider.java

Provider này chỉ nhận DemoApiKeyAuthenticationToken, so sánh key giả và tạo một service principal với ROLE_SERVICE.

~~~java
package com.example.providers;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class DemoApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private static final byte[] EXPECTED_KEY =
        "local-demo-key".getBytes(StandardCharsets.UTF_8);

    @Override
    public Authentication authenticate(Authentication input) {
        String presented = (String) input.getCredentials();

        if (presented == null ||
            !MessageDigest.isEqual(
                EXPECTED_KEY,
                presented.getBytes(StandardCharsets.UTF_8))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return DemoApiKeyAuthenticationToken.authenticated(
            "batch-service",
            List.of(new SimpleGrantedAuthority("ROLE_SERVICE"))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return DemoApiKeyAuthenticationToken.class
            .isAssignableFrom(authenticationType);
    }
}
~~~

**Giải thích chính xác:**

1. ProviderManager gọi supports() trước. Nếu input là UsernamePasswordAuthenticationToken, nó **không gọi** authenticate() của API-key provider.
2. Với DemoApiKeyAuthenticationToken, provider đọc credentials đã được truyền trong token.
3. Key sai → **BadCredentialsException**, không giả vờ trả Authentication thành công và không dùng null để che lỗi credential.
4. Key demo đúng → trả token mới được đánh dấu authenticated và có ROLE_SERVICE.
5. MessageDigest.isEqual giúp giảm khác biệt thời gian của một phép so sánh byte array so với so sánh chuỗi thông thường; **không biến key ngắn trong source thành một mô hình quản lý API key an toàn**.
6. Không ghi giá trị key hoặc Authentication#getCredentials() vào log.

Do đây là provider **đã được ProviderManager chọn bằng supports()**, cast sang DemoApiKeyAuthenticationToken là hợp lệ trong luồng cấu hình. Nếu tự gọi provider.authenticate() trực tiếp với một loại token khác, bạn phá hợp đồng gọi thông thường và có thể gặp lỗi. Một implementation production có thể thêm kiểm tra kiểu phòng vệ rõ ràng.

### 8.7. SecurityConfig.java

Đây là phần tạo một **ProviderManager cụ thể** và cho HttpSecurity sử dụng chính manager đó.

~~~java
package com.example.providers;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {

        DaoAuthenticationProvider dao =
            new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);

        DemoApiKeyAuthenticationProvider apiKey =
            new DemoApiKeyAuthenticationProvider();

        return new ProviderManager(List.of(apiKey, dao));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đọc từng lớp:**

- UserDetailsService giữ hai tài khoản thử nghiệm trong bộ nhớ: alice/demo-alice và admin/demo-admin. BCryptPasswordEncoder tạo hash mật khẩu trước khi đưa vào UserDetails.
- DaoAuthenticationProvider được cấu hình để xác thực UsernamePasswordAuthenticationToken bằng UserDetailsService + PasswordEncoder.
- DemoApiKeyAuthenticationProvider xử lý DemoApiKeyAuthenticationToken; nó **không** kiểm password của alice.
- new ProviderManager(List.of(apiKey, dao)) tạo manager với thứ tự cụ thể. Nó có thể xác thực cả hai kiểu Authentication request theo test.
- http.authenticationManager(manager) **gắn chính manager vào HttpSecurity**, tránh giả định filter mặc nhiên dùng đúng manager mới chỉ vì có bean trong context.
- httpBasic(...) tạo luồng HTTP Basic cho client. Nó đưa username/password tới AuthenticationManager; **không tự đọc X-API-Key**.
- /api/public là public theo chủ đích; /api/me cần authenticated(); /api/admin cần ROLE_ADMIN; anyRequest().denyAll() giới hạn những route không có quy tắc.
- SecurityFilterChain **không tự chuyển role**: authority ROLE_ADMIN được cấp bởi UserDetails đã xác thực. Demo API key chỉ có ROLE_SERVICE nên không tự được phép vào /api/admin.

**Lưu ý theo phiên bản:** ví dụ dùng constructor không tham số của DaoAuthenticationProvider và các setter phù hợp Spring Security 6.3.x. Với các dòng Spring Security mới hơn, API khởi tạo có thể thay đổi; tra Javadoc đúng version đã được dependency management chọn.

**Quan trọng:** phần cấu hình này không bật formLogin và không thiết kế session/browser login. Trong ứng dụng thật, hãy chọn rõ cơ chế phù hợp, session policy, HTTPS, secret handling và CSRF. Bài chỉ dùng các request GET nên không tắt CSRF mặc định.

## 9. Kiểm chứng HTTP Basic bằng curl

Khởi động trong thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Nếu port 8080 trống và ứng dụng khởi động đúng, thử trên localhost. Với Windows PowerShell dùng curl.exe; Linux/macOS thay bằng curl.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/me
curl.exe -i -u alice:wrong http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

Kết quả **dự kiến**:

| HTTP request | Status | Nguyên nhân |
| --- | --- | --- |
| GET /api/public, không credential | 200 | permitAll(), response JSON message=public. |
| GET /api/me, không credential | 401 | Chưa xác thực; HTTP Basic challenge. |
| GET /api/me với alice/demo-alice | 200 | DaoAuthenticationProvider xác thực đúng password. |
| GET /api/me với alice/wrong | 401 | DaoAuthenticationProvider từ chối credential. |
| GET /api/admin với alice/demo-alice | 403 | Alice chỉ có ROLE_USER, không có ROLE_ADMIN. |
| GET /api/admin với admin/demo-admin | 200 | Principal admin có ROLE_ADMIN. |

Status 401 của HTTP Basic thường có **WWW-Authenticate**. Tên realm, body lỗi và các header bổ sung có thể khác giữa các cấu hình; không cần thuộc byte-for-byte những header phụ.

Nếu gửi:

~~~powershell
curl.exe -i -H "X-API-Key: local-demo-key" http://localhost:8080/api/me
~~~

kết quả vẫn **401** trong project hiện tại. Điều này là **đúng theo thiết kế**: API-key provider đã được đăng ký trong ProviderManager, nhưng **chưa có HTTP authentication filter nào tạo DemoApiKeyAuthenticationToken từ X-API-Key**. Đây là ví dụ cho thấy việc thêm provider **không tự mở một phương thức đăng nhập HTTP mới**.

Tương tự, Authorization: Basic ... là cách filter HTTP Basic đọc username/password; thêm một header như X-Username hoặc X-Role không khiến DAO provider tự lấy chúng.

**Cảnh báo trong bài lab:** credentials giả chỉ dùng trên localhost. HTTP Basic dùng Base64, không cung cấp bí mật khi truyền qua HTTP; với hệ thống thật phải dùng HTTPS. Không lưu hoặc gửi mật khẩu/token thật trong screenshot, log hay command history được chia sẻ.

## 10. Kiểm thử ProviderManager và thứ tự lựa chọn bằng JUnit

Tạo **src/test/java/com/example/providers/ProviderRoutingTests.java**:

~~~java
package com.example.providers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProviderRoutingTests {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    @Test
    void daoProviderAuthenticatesUsernamePasswordToken() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-alice");

        Authentication result = manager.authenticate(request);

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("alice");
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_USER");
    }

    @Test
    void daoProviderRejectsWrongPassword() {
        Authentication request =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void apiKeyProviderAuthenticatesItsOwnTokenType() {
        Authentication request =
            new DemoApiKeyAuthenticationToken("local-demo-key");

        Authentication result = manager.authenticate(request);

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("batch-service");
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getAuthorities())
            .extracting(a -> a.getAuthority())
            .contains("ROLE_SERVICE");
    }

    @Test
    void apiKeyProviderRejectsBadKey() {
        Authentication request =
            new DemoApiKeyAuthenticationToken("bad-key");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void unknownTokenHasNoSupportingProvider() {
        Authentication request =
            new TestingAuthenticationToken("nobody", "irrelevant");

        assertThatThrownBy(() -> manager.authenticate(request))
            .isInstanceOf(ProviderNotFoundException.class);
    }

    @Test
    void publicEndpointIsAvailableWithoutCredential()
            throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthUsesDaoProvider() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void badBasicCredentialIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiKeyHeaderAloneDoesNotCreateAuthentication()
            throws Exception {
        mvc.perform(get("/api/me")
                .header("X-API-Key", "local-demo-key"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

**Mười hai test** chứng minh hai lớp điều kiện:

1. **Xác thực trực tiếp với AuthenticationManager:** username/password dùng DAO; custom key dùng custom provider; mật khẩu/key sai bị từ chối; token không ai supports báo ProviderNotFoundException.
2. **Luồng HTTP thực tế ở tầng MockMvc:** Basic thành công và thất bại đúng như kỳ vọng; role ADMIN là điều kiện authorization riêng; X-API-Key không được nhận chỉ vì provider tồn tại.

Bộ test dùng Spring Boot test và Spring Security test như trong pom.xml. Nếu project thật có AuthenticationManager khác hoặc nhiều SecurityFilterChain, cần kiểm chính manager được mỗi filter sử dụng, không chỉ autowire một bean theo tên.

**Giải thích test getCredentials()==null:** ProviderManager mặc định cố xóa credential nhạy cảm từ Authentication kết quả thông qua cơ chế CredentialsContainer/eraseCredentials. Trong trường hợp DAO trả UsernamePasswordAuthenticationToken, credential thường được xóa theo hành vi token class. Token API-key mẫu được thiết kế để không lưu key trong kết quả ngay từ đầu.

### 10.1. Vì sao test này không kiểm được mọi trường hợp production?

- In-memory accounts không kiểm backend LDAP, database, IdP hay trạng thái khóa tài khoản thực tế.
- MockMvc không mở kết nối TLS, không kiểm ingress/gateway hoặc các header trusted proxy.
- API key demo không có rotation, revocation, expiration, limit/quota và chính sách cấp key thật.
- Chưa kiểm nhiều provider cùng supports một token và thứ tự exception; muốn dùng cơ chế đó trong production, cần bổ sung test phù hợp policy của từng nguồn.
- Test đúng status không tự chứng minh các API thay đổi dữ liệu không có side effect trái phép; kiểm DB, message và audit nếu có nghiệp vụ ghi.

## 11. Mở rộng tình huống: hai provider cùng supports một kiểu token

Giả sử có hai nguồn username/password:

~~~text
ProviderManager
  [0] StaffAuthenticationProvider
  [1] CustomerAuthenticationProvider
~~~

Cả hai supports(UsernamePasswordAuthenticationToken.class) có thể trả true. Hãy xem hành vi:

| Provider thứ nhất | Provider thứ hai | Kết luận khả dĩ |
| --- | --- | --- |
| Trả null vì request không thuộc nguồn staff | Kiểm customer, thành công | Đăng nhập thành công bằng nguồn customer. |
| Thành công | Không được thử | Kết quả của staff được dùng. |
| Ném BadCredentialsException | Customer vẫn có thể được thử; nếu thành công thì kết quả sau thắng | Có thể đăng nhập từ nguồn customer. |
| Ném BadCredentialsException | Customer cũng thất bại | Ném AuthenticationException phù hợp; không tự biến thành công. |
| Ném AccountStatusException | Không được thử tiếp | Chặn ngay theo chính sách ProviderManager. |
| Ném InternalAuthenticationServiceException | Không được thử tiếp | Tránh coi lỗi hệ thống là một nhánh chấp nhận khác. |

**Rủi ro:** Nếu một username tồn tại trong cả staff và customer với hai bộ chính sách khác nhau, việc thử nguồn thứ hai sau khi nguồn thứ nhất báo password sai có thể tạo hành vi không mong muốn. Giải pháp phụ thuộc kiến trúc: phân miền định danh rõ, tạo token type riêng, có authenticationManagerResolver đáng tin hoặc tách chain/filter theo giao thức. Không dựa vào thứ tự provider để giải quyết một xung đột danh tính chưa được định nghĩa.

Một provider tùy biến nên sử dụng **supports** đúng loại token, trả null chỉ khi không thể đưa ra quyết định cho request, và ném exception thích hợp khi từ chối credential. Nếu policy yêu cầu dừng ngay vì tài khoản đã khóa, không tự chuyển AccountStatusException thành BadCredentialsException rồi hy vọng manager vẫn dừng.

### 11.1. Bài tập nhỏ về thứ tự

Cho danh sách:

~~~text
[ProviderA, ProviderB, ProviderC]
~~~

Và request có class UsernamePasswordAuthenticationToken:

- A.supports=false.
- B.supports=true, B.authenticate trả null.
- C.supports=true, C.authenticate thành công.

**Kết quả:** A bị bỏ qua; B được thử nhưng không kết luận; C thành công; manager trả Authentication của C.

Nếu B trả Authentication thành công, C không được thử. Nếu B ném BadCredentialsException nhưng C thành công, kết quả thành công của C có thể thay thế lỗi B. Nếu B ném một AccountStatusException, manager dừng và C không được thử theo quy tắc của ProviderManager.

## 12. Đưa custom provider vào HTTP cần thêm gì?

Đăng ký AuthenticationProvider mới **chưa đủ** để một header X-API-Key trở thành cơ chế đăng nhập HTTP. Cần hoàn thiện một luồng tích hợp:

~~~text
HTTP GET /api/me
X-API-Key: ...
       |
       v
Filter/converter đọc header theo quy tắc rõ
       |
       v
DemoApiKeyAuthenticationToken(isAuthenticated=false)
       |
       v
AuthenticationManager.authenticate(token)
       |
       v
ProviderManager chọn DemoApiKeyAuthenticationProvider
       |
       v
Authentication được xác thực
       |
       v
Filter tạo SecurityContext / xử lý thành công
       |
       v
Authorization kiểm authenticated()/authority
       |
       v
Controller
~~~

Những yếu tố quan trọng khi triển khai:

1. **Filter/converter** chỉ áp dụng cho endpoint được thiết kế và đọc header chính xác; xác minh kích thước/định dạng token, tránh ghi log key.
2. **AuthenticationManager** phải là manager chứa đúng provider. Nếu tạo một manager riêng trong filter mà chain khác dùng manager khác, hành vi rất dễ khó hiểu.
3. **Authentication request** phải là kiểu mà provider supports. Không lấy apiKey string rồi tạo UsernamePasswordAuthenticationToken chỉ để tận dụng DAO.
4. **Thành công:** filter cần gắn Authentication vào SecurityContext đúng cơ chế và đảm bảo context lifecycle phù hợp. Nếu dùng session, cần xem SecurityContextRepository và session persistence; nếu stateless, tránh tự giữ Authentication giữa các request.
5. **Thất bại:** trả status 401/challenge theo contract API, xóa context nếu cần; phân biệt thiếu credential với credential đã gửi nhưng sai.
6. **Credential conflict:** nếu client gửi cả Authorization: Basic và X-API-Key, xác định chính sách ưu tiên hoặc từ chối request mơ hồ; đừng mặc định dùng credential nào thuận lợi hơn.
7. **Chính sách quyền:** một service principal với ROLE_SERVICE không tự có quyền xem /api/admin. Scope/permission/object ownership vẫn phải kiểm độc lập.
8. **Thứ tự filter** với BasicAuthenticationFilter, SecurityContextHolderFilter, CsrfFilter và AuthorizationFilter ảnh hưởng kết quả; dùng integration test bao phủ cả thành công và lỗi.
9. **Bảo vệ key production:** key entropy đủ, lưu key dưới dạng hash hoặc cơ chế secret quản lý phù hợp, rotation/revocation, TTL nếu có, rate limit, audit và HTTPS.
10. **Quyền đối tượng:** nếu API key đại diện service, không suy ra nó có quyền đọc mọi dữ liệu của user. Thiết kế service identity và tenant boundary rõ.

Một custom API-key filter **không cần thiết để chứng minh lựa chọn của ProviderManager** trong bài này; project ở mục 8–10 đã test trực tiếp rằng đúng token type được route đúng provider. Khi bổ sung filter, hãy tạo test HTTP thực thay vì chỉ dựa vào supports().

## 13. Authentication thành công không đồng nghĩa request được phép

Một request có thể trải qua:

~~~text
DaoAuthenticationProvider:
  alice + password đúng
  -> Authentication(principal=alice, ROLE_USER)
           |
           v
Authorization for /api/admin:
  requires ROLE_ADMIN
  -> AccessDenied
           |
           v
HTTP 403 (điển hình)
~~~

ProviderManager đã **hoàn thành nhiệm vụ xác thực** khi trả Authentication hợp lệ. Việc GET /api/admin nhận 403 **không phải bằng chứng ProviderManager chọn sai provider**: danh tính đúng nhưng thiếu quyền.

Phân biệt:

| Lỗi/thành công | Tầng liên quan | Điều nên kiểm |
| --- | --- | --- |
| 200 với Basic đúng trên /api/me | Authentication + authorization đều qua | Principal, authorities, body đúng người. |
| 401 vì Basic password sai | Authentication filter/DAO/entry point | Credential, UserDetailsService, PasswordEncoder. |
| 401 vì không có credential | Authentication entry point khi quyền yêu cầu | Request thực sự đã gửi Authorization chưa? |
| 403 vì thiếu ROLE_ADMIN | Authorization | hasRole, authority ROLE_ADMIN, rule order. |
| 403 vì POST thiếu CSRF token | CsrfFilter | Đừng quy ngay là provider từ chối password. |
| ProviderNotFoundException | AuthenticationManager/provider wiring | Token class và supports(), manager được filter sử dụng. |
| InternalAuthenticationServiceException | Backend xác thực/provider | DB/LDAP/IdP lỗi? Không tự fallback sang nguồn yếu. |
| 404 khi tìm đối tượng | Routing/domain hoặc chính sách che giấu | Path, object ownership, policy và body. |

Phân quyền theo URL cũng chưa đủ cho IDOR/BOLA: user hợp lệ chỉ được đọc đơn thuộc quyền của mình. Service/domain phải kiểm owner/tenant/relationship trước khi trả dữ liệu hoặc tạo side effects.

## 14. Credentials erasure và tác động với cache

ProviderManager mặc định cố **xóa dữ liệu credential nhạy cảm** khỏi Authentication kết quả sau khi xác thực thành công, nếu object hỗ trợ CredentialsContainer. Mục đích là tránh mật khẩu/key tồn tại lâu trong SecurityContext, session hoặc các nơi giữ Authentication.

Điều này **không đồng nghĩa toàn bộ dữ liệu bí mật từng được xử lý đã biến mất khỏi bộ nhớ**. Một chuỗi String đầu vào vẫn có thể tồn tại tới khi GC, và bản copy trong log/request có thể tồn tại ngoài Authentication. Vì vậy phải giảm thời gian giữ secret, không log raw credentials và thiết kế lưu trữ phù hợp.

### 14.1. Trường hợp cache UserDetails

Nếu Authentication sau thành công giữ tham chiếu trực tiếp tới UserDetails **đang nằm trong cache** và quá trình eraseCredentials tác động vào object dùng chung, cached UserDetails có thể mất password hash cần thiết cho lần xác thực sau.

Các hướng xử lý đúng:

- Trả/copy **UserDetails riêng** cho Authentication thay vì dùng chung mutable object với cache.
- Thiết kế cache giữ bản giá trị không bị xóa bằng một tham chiếu từ authentication result.
- Kiểm tra implementation cache/provider và test nhiều lần đăng nhập.
- Chỉ cân nhắc thay đổi eraseCredentialsAfterAuthentication khi có lý do rõ ràng và đánh giá rủi ro; **tắt xóa credential làm tăng dữ liệu nhạy cảm được giữ lại**.

Bài demo sử dụng UserDetails in-memory và DaoAuthenticationProvider theo cấu hình cơ bản. Khi đưa cache và nhiều provider vào production, cần kiểm thử lại kết quả và trạng thái credential.

## 15. Mối quan hệ với AuthenticationEntryPoint, FailureHandler và SecurityContext

ProviderManager không phải một HTTP response renderer. Nó trả Authentication hoặc ném AuthenticationException. Thành phần gọi nó chịu trách nhiệm tiếp theo:

- **BasicAuthenticationFilter** nhận HTTP Basic credential, gọi manager và có cách xử lý credential sai/entry point phù hợp.
- **UsernamePasswordAuthenticationFilter** dùng cho form login, gọi manager; thành công hoặc thất bại có thể đi qua AuthenticationSuccessHandler/AuthenticationFailureHandler.
- **Bearer token authentication filter** dùng cơ chế Resource Server/JWT/opaque token phù hợp.
- **SecurityContextHolder/SecurityContextRepository** liên quan đến việc gắn/lưu/khôi phục ngữ cảnh theo phiên và filter.
- **ExceptionTranslationFilter** chuyển một số AuthenticationException/AccessDeniedException phát sinh downstream thành hành vi HTTP. Không phải mọi lỗi từ mọi authentication filter đều đi qua filter đó.
- **AuthenticationEntryPoint** bắt đầu/challenge xác thực khi cần, như 401 Basic hoặc redirect tới login theo stack.

Một luồng form login thành công thường cần cập nhật SecurityContext và có thể ghi session; điều đó **không phải việc ProviderManager tự làm**. Một manager được gọi trực tiếp trong unit test chỉ trả kết quả; nó không tự tạo một HTTP session đăng nhập.

### 15.1. 401, 403 và login redirect

- **401:** thường là thiếu hoặc không có credential hợp lệ với API challenge-based.
- **403:** principal xác thực thành công nhưng thiếu quyền, hoặc cơ chế khác như CSRF từ chối.
- **302 tới /login:** thường xuất hiện khi web app dùng formLogin và người dùng ẩn danh cần xác thực.
- **ProviderNotFoundException:** lỗi ở tầng manager/provider; response HTTP phụ thuộc handler/filter được cấu hình. Không mặc định tuyên bố nó luôn thành một status nhất định.

Khi debug, hãy xác định **thành phần đầu tiên từ chối request** và ghi log có kiểm soát. Chỉ nhìn 401 hoặc 403 không cho biết provider nào đã chạy.

## 16. Các lỗi cấu hình ProviderManager thường gặp

### 16.1. Đăng ký provider nhưng filter không dùng manager đó

Một ứng dụng có thể khai báo AuthenticationManager bean rồi một SecurityFilterChain khác dùng manager riêng. Khi debug, kiểm http.authenticationManager(...) hoặc manager mà cơ chế xác thực thật sử dụng; đừng chỉ nhìn danh sách bean trong ApplicationContext.

### 16.2. supports() sai class

Custom provider viết supports chỉ cho String.class hoặc Jwt.class trong khi filter tạo Authentication subtype khác → ProviderManager không gọi provider. Kiểm **request.getClass()** và token type được filter tạo, không lấy từ tên header suy đoán.

### 16.3. supports() quá rộng

Nếu custom provider supports tất cả Authentication, nó có thể nhận token không hiểu và ném lỗi không phù hợp. Tốt nhất giới hạn theo token class rõ ràng, rồi test request của provider khác không bị ảnh hưởng.

### 16.4. Trả null khi mật khẩu/key sai

Trả null nghĩa là nhường provider khác. Nếu credential đã được kết luận sai, dùng AuthenticationException phù hợp. Với nhiều provider cùng token type, nên có ranh giới nguồn danh tính rõ và test thứ tự provider.

### 16.5. Không phân biệt lỗi tài khoản khóa với credential sai

Khi tài khoản disabled/locked, cơ chế authentication cần bảo toàn ý nghĩa account status. Không chuyển một AccountStatusException thành null để cho nguồn khác “thử lại”.

### 16.6. Tự tin vào provider chỉ vì cùng loại token

Hai nguồn username/password có thể cùng supports UsernamePasswordAuthenticationToken nhưng dựa trên realm khác nhau. Nếu không có cách định tuyến an toàn theo miền danh tính, có thể xảy ra trùng username, cấp nhầm role hoặc xác thực từ nguồn không mong đợi.

### 16.7. Không xóa credential sau xác thực

Trả Authentication chứa password thô hoặc API key trong principal/credentials/details có thể làm lộ dữ liệu khi serialize, log hoặc lưu session. Dùng implementation an toàn và xem cơ chế erasure.

### 16.8. Đặt ROLE_ADMIN trực tiếp từ dữ liệu client

AuthenticationProvider phải xác minh nguồn quyền. Header X-Role: ADMIN hoặc JWT payload chưa kiểm chữ ký không được biến thành ROLE_ADMIN. Provider nên tạo authorities từ nguồn tin cậy và áp dụng ít quyền nhất.

### 16.9. Bỏ qua authorization ở bước sau

Một Authentication hợp lệ không có nghĩa được xem mọi resource. Phải kiểm role/permission/scope/object policy ở URL và Service/domain khi phù hợp.

### 16.10. Sai PasswordEncoder hoặc password hash

PasswordEncoder.matches(rawPassword, storedHash) cần nhận hash theo đúng thuật toán/cấu hình. Nếu code lưu raw password vào UserDetails nhưng encoder chờ BCrypt hash, đăng nhập sẽ thất bại. Không sửa bằng NoOpPasswordEncoder cho production.

### 16.11. Gộp HTTP Basic và API key mà không xử lý credential conflict

Nếu HTTP filter chấp nhận cả Authorization và X-API-Key, quy định rõ logic lựa chọn và trạng thái khi cả hai xuất hiện. Tránh một credential sai vô tình bị “cứu” bởi credential khác khi chính sách yêu cầu một danh tính duy nhất.

### 16.12. Mặc định mở endpoint khi không tìm thấy provider

Nếu manager không thể xác thực, request tới protected endpoint phải không được thực hiện nghiệp vụ. Không catch ProviderNotFoundException rồi permitAll hoặc tự gắn một anonymous principal với role đặc quyền.

## 17. Debug theo thứ tự đúng

Nếu một request nhận 401 và bạn nghi ProviderManager chọn nhầm provider, hãy làm lần lượt:

1. **Xác định SecurityFilterChain:** đường URL/method nào khớp? Có nhiều chain hoặc chain riêng cho API không?
2. **Xác định authentication filter:** HTTP Basic, form login, Bearer/JWT hay custom key? Filter nào thực sự được kích hoạt bởi request?
3. **Xác định Authentication request class:** UsernamePasswordAuthenticationToken, BearerTokenAuthenticationToken hay custom class?
4. **Đọc danh sách provider trong manager thực tế:** manager được filter sử dụng có những provider nào và thứ tự nào?
5. **Kiểm supports():** provider nào trả true cho request.getClass()? Những provider nào chắc chắn bị bỏ qua?
6. **Kiểm authenticate():** kết quả null, thành công hay ném exception nào? Có provider sau có thể override lỗi không?
7. **Kiểm parent AuthenticationManager:** có parent không? Tại sao cần fallback và có phù hợp threat model không?
8. **Kiểm credentials:** sai mật khẩu, password hash/encoder, tài khoản disabled/locked, API key hết hạn hoặc IdP không sẵn sàng?
9. **Kiểm Authentication sau thành công:** principal, authenticated, authorities, credentials erasure; không log secret.
10. **Kiểm authorization:** 401 hay 403? Nếu 403, có thể ProviderManager đã xác thực thành công và lỗi nằm ở quyền.
11. **Kiểm context/session:** filter có lưu SecurityContext đúng khi cần không? Request mới có credential/session phù hợp không?
12. **Viết kiểm thử âm tính:** sai token type, sai mật khẩu, thiếu role, không có provider, key giả, tài nguyên của user khác.

**Gợi ý log:** có thể tăng logging Spring Security ở môi trường local để quan sát filter và authentication decisions, nhưng cần che Authorization, Cookie, raw credentials, API key và token. Không bật verbose security logging trên production chỉ để tìm nhanh lỗi.

## 18. Câu hỏi tự kiểm tra

1. ProviderManager có phải một AuthenticationProvider không? **Đáp án gợi ý:** Không; nó triển khai AuthenticationManager và điều phối AuthenticationProvider.
2. supports() nhận tham số nào? **Đáp án:** Class<?> của Authentication request, không phải HTTP header/path.
3. supports() trả true có bảo đảm authenticate() thành công không? **Đáp án:** Không; có thể trả null hoặc ném AuthenticationException.
4. Provider A trả null, Provider B thành công: manager làm gì? **Đáp án:** Dùng kết quả B, dừng.
5. Provider A ném BadCredentialsException, Provider B cùng supports thành công: kết quả có thể là gì? **Đáp án:** Thành công B có thể được dùng; cần xét thứ tự và policy.
6. Provider đầu ném AccountStatusException: có thử tiếp provider sau không? **Đáp án:** Không theo cơ chế ProviderManager 6.x.
7. Khi nào có ProviderNotFoundException? **Đáp án:** Không có provider/parent phù hợp xử lý được token.
8. Vì sao BasicAuthenticationFilter với DaoAuthenticationProvider không tự hỗ trợ X-API-Key? **Đáp án:** Filter cần chủ động tạo đúng custom Authentication request.
9. Một DAO provider xác thực alice thành công, nhưng /api/admin trả 403. ProviderManager sai không? **Đáp án:** Không; alice không có ROLE_ADMIN.
10. Vì sao nên dùng token type riêng cho API key? **Đáp án:** Giữ supports() chính xác và phân biệt credential với username/password.
11. Tại sao setAuthenticated(true) cho token do client cung cấp là nguy hiểm? **Đáp án:** Bỏ qua bước kiểm chứng credential.
12. Tại sao custom provider không nên trả raw API key trong Authentication đã xác thực? **Đáp án:** Rủi ro rò qua context/session/log; cần xóa hoặc không lưu secret.
13. Nếu dùng nhiều SecurityFilterChain, có thể có nhiều ProviderManager không? **Đáp án:** Có; các chain có thể cấu hình manager riêng hoặc chia sẻ parent.
14. Một hệ thống có JWT và Basic nhưng backend chung UserDetailsService. Có bắt buộc dùng hai DaoAuthenticationProvider không? **Đáp án:** Không; JWT có provider/decoder riêng, Basic dùng DAO; identity mapping tùy thiết kế.
15. Phân biệt BadCredentialsException, ProviderNotFoundException và AccessDeniedException trong một câu cho từng loại.

### Checklist ghi nhớ

- **AuthenticationManager** là interface; **ProviderManager** là implementation dùng danh sách provider.
- **AuthenticationProvider** quyết định supports(Class<?>) và authenticate(Authentication).
- **supports=false** → bỏ qua provider; **supports=true** → có thể thử nhưng chưa bảo đảm thành công.
- **authenticate() trả Authentication khác null** → thành công, dừng; **null** → nhường; **AuthenticationException** → xử lý tùy loại và provider tiếp theo.
- **ProviderNotFoundException** thường chỉ ra không có provider xử lý được token request.
- **AccountStatusException/InternalAuthenticationServiceException** có thể dừng luồng ngay để bảo vệ policy.
- **Thứ tự provider** quan trọng khi có hơn một provider hỗ trợ cùng loại Authentication.
- **Parent AuthenticationManager** là fallback tùy chọn, cần thiết kế để không mở đường xác thực ngoài mong muốn.
- **Credential erasure** giúp hạn chế secret tồn tại trong Authentication thành công.
- **ProviderManager không tự đặt SecurityContext, không tự phát HTTP 401 và không tự cấp quyền**.
- **Custom header cần filter/converter tạo Authentication request đúng kiểu**.
- **Test cả xác thực và phân quyền**, cả trường hợp đúng và sai, không chỉ HTTP 200.

## Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, AuthenticationProvider và tổng quan filter.
- [ProviderManager JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/ProviderManager.html): thứ tự provider, parent, ngoại lệ và credentials erasure.
- [AuthenticationProvider JavaDoc — Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authentication/AuthenticationProvider.html): contract supports/authenticate và trường hợp null.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html): cơ chế xác thực username/password.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): quyền và quyết định authorization sau khi có Authentication.

**Phiên bản:** Project dùng Spring Boot 3.3.6 (Spring Security 6.3.x) để minh họa cơ chế ProviderManager. Với dự án trên Spring Security mới hơn, cần kiểm tài liệu API đúng version, cập nhật bản vá và xác minh lại project bằng build/test thực tế.

## Kết luận

ProviderManager là bộ điều phối AuthenticationProvider cho **một Authentication request cụ thể**. Nó xét supports() theo kiểu token, thử các provider đã đăng ký theo thứ tự, chấp nhận kết quả Authentication thành công, xử lý null/exception và có thể dùng parent theo cấu hình. **Việc chọn provider chỉ là một phần của luồng xác thực**: filter chịu trách nhiệm đưa credential vào đúng token và xử lý SecurityContext/HTTP response, còn authorization quyết định quyền sử dụng endpoint và dữ liệu sau khi danh tính đã được xác minh. Hiểu rành mạch các trách nhiệm này giúp đọc log đúng, cấu hình nhiều cơ chế xác thực an toàn và tránh nhầm 401, ProviderNotFoundException hay 403 với lỗi ở cùng một thành phần.
