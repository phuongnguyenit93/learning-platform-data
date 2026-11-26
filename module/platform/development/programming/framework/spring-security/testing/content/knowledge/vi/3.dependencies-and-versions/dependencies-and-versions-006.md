# Phân biệt static import của Servlet với Reactive

Khi viết test Spring Security bằng Java, một số lời gọi trông rất giống nhau nhưng thuộc **hai bộ API khác nhau**. Với ứng dụng Servlet/MVC, các helper như **user()**, **jwt()** và **csrf()** thường được static import từ **SecurityMockMvcRequestPostProcessors**. Với ứng dụng Reactive/WebFlux, các helper tương ứng thường là **mockUser()**, **mockJwt()**, **csrf()** từ **SecurityMockServerConfigurers**.

Nếu chọn nhầm import, IDE có thể tự động thêm class của stack còn lại; code có thể không biên dịch vì kiểu trả về không khớp, hoặc test được dựng với client/filter chain không đúng. Bài này giúp nhận diện **class sở hữu static method**, hiểu khác biệt kiểu request, và viết test đúng với stack thực tế.

Bài thuộc chương **Phụ thuộc và phiên bản** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng **spring-security-test** trên ứng dụng **Servlet** và **Reactive**, sử dụng **MockMvc**, **WebTestClient**, **@WithMockUser**, **SecurityContext**, JWT/OAuth2/OIDC giả lập cùng các ca được phép hoặc bị từ chối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích static import trong Java và phân biệt nó với import class thông thường.
2. Nhớ đúng package chứa helper Servlet và helper Reactive của Spring Security Test.
3. Phân biệt **user()** với **mockUser()**, **jwt()** với **mockJwt()**, cũng như hai hàm **springSecurity()** có cùng tên nhưng khác class và kiểu cấu hình.
4. Chọn đúng request builder, response matcher và security configurer cho **MockMvc** hoặc **WebTestClient**.
5. Chẩn đoán lỗi do IDE import nhầm stack, dependency thiếu hoặc test client chưa tích hợp security chain.

## 2. Static import là gì?

Java static import cho phép gọi trực tiếp một **static method** hoặc **static field** bằng tên thành viên mà không cần viết tên class ở phía trước.

Không dùng static import:

~~~java
MockMvc mvc = ...;

mvc.perform(
    MockMvcRequestBuilders.get("/api/reports")
        .with(SecurityMockMvcRequestPostProcessors.user("lan").roles("ADMIN"))
).andExpect(
    MockMvcResultMatchers.status().isOk()
);
~~~

Dùng static import:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mvc.perform(get("/api/reports").with(user("lan").roles("ADMIN")))
   .andExpect(status().isOk());
~~~

Static import chỉ rút gọn **cách gọi tên**. Nó không biến một Servlet request thành Reactive request, không tự thêm filter vào client và cũng không thay đổi cách xác thực của ứng dụng. Kiểu trả về của method vẫn thuộc API gốc.

### 2.1. Import thường và static import

| Cú pháp | Dùng để | Ví dụ |
|---|---|---|
| **import org.springframework.test.web.servlet.MockMvc;** | Dùng tên class **MockMvc** trong mã | **MockMvc mvc;** |
| **import static ...SecurityMockMvcRequestPostProcessors.user;** | Gọi static method **user()** trực tiếp | **.with(user("lan"))** |
| **import static ...SecurityMockServerConfigurers.mockUser;** | Gọi static method **mockUser()** trực tiếp | **.mutateWith(mockUser())** |
| **import static ...SecurityMockMvcResultMatchers.authenticated;** | Gọi static result matcher | **.andExpect(authenticated())** |

Một static import phải chỉ rõ **class chứa thành viên**, không chỉ package. IDE có thể đề xuất nhiều method cùng tên; hãy nhìn toàn bộ dòng import để biết API thuộc stack nào.

## 3. Bảng tra nhanh: Servlet và Reactive

Đây là bảng quan trọng nhất của bài:

| Ý định | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Class chứa request/security mutators | **org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors** | **org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers** |
| Tạo user giả lập theo request | **user("lan")** | **mockUser("lan")** |
| Tạo JWT giả lập | **jwt()** | **mockJwt()** |
| Tạo opaque token giả lập | **opaqueToken()** | **mockOpaqueToken()** |
| Tạo OAuth2 Login giả lập | **oauth2Login()** | **mockOAuth2Login()** |
| Tạo OIDC Login giả lập | **oidcLogin()** | **mockOidcLogin()** |
| Tạo OAuth2 authorized client | **oauth2Client()** | **mockOAuth2Client()** |
| Thêm CSRF token | **csrf()** | **csrf()** |
| Tích hợp Spring Security vào client | **SecurityMockMvcConfigurers.springSecurity()** | **SecurityMockServerConfigurers.springSecurity()** |
| HTTP test client | **MockMvc** | **WebTestClient** |
| Gắn helper vào request | **.with(user(...))** | **.mutateWith(mockUser(...))** |
| Gửi request | **mvc.perform(get(...))** | **client.get().uri(...).exchange()** |
| Kiểm tra status | **.andExpect(status().isOk())** | **.expectStatus().isOk()** |

**Điểm dễ nhầm:** **csrf()** và **springSecurity()** có cùng tên ở hai stack, nhưng được khai báo trong **hai class khác nhau** và trả về kiểu dùng cho hai client khác nhau. **user()/jwt()** của Servlet và **mockUser()/mockJwt()** của Reactive còn có tên khác nhau.

## 4. Servlet: static import cho MockMvc

### 4.1. Các class cần nhớ

Với Spring MVC/Servlet, những helper phổ biến đến từ:

~~~java
org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors
org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers
org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers
~~~

| Class | Static method tiêu biểu | Mục đích |
|---|---|---|
| **SecurityMockMvcRequestPostProcessors** | **user()**, **anonymous()**, **authentication()**, **csrf()**, **jwt()**, **opaqueToken()**, **oauth2Login()**, **oidcLogin()**, **oauth2Client()** | Thêm authentication, principal, token hoặc CSRF vào Servlet request |
| **SecurityMockMvcConfigurers** | **springSecurity()** | Tích hợp Spring Security với **MockMvc** khi dựng client từ web context |
| **SecurityMockMvcResultMatchers** | **authenticated()**, **unauthenticated()** | Kiểm tra trạng thái xác thực trong kết quả MockMvc |

Ví dụ các static import tường minh:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Các dòng **get()**, **post()** và **status()** **không** đến từ Spring Security Test: chúng thuộc Spring Framework MockMvc. Phân biệt nguồn gốc này giúp tránh import nhầm một helper security cho request builder hoặc ngược lại.

### 4.2. Ví dụ user và CSRF với MockMvc

Giả định endpoint **GET /api/admin/reports** yêu cầu **ROLE_ADMIN**, endpoint **POST /api/admin/reports** yêu cầu cùng role và CSRF đang bật. **mvc** đã được khởi tạo với security filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AdminMvcSecurityTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void userWithoutAdminRoleIsDenied() throws Exception {
        mvc.perform(get("/api/admin/reports")
                .with(user("lan").roles("USER")))
           .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAndWriteWithCsrf() throws Exception {
        mvc.perform(get("/api/admin/reports")
                .with(user("minh").roles("ADMIN")))
           .andExpect(status().isOk());

        mvc.perform(post("/api/admin/reports")
                .with(user("minh").roles("ADMIN"))
                .with(csrf()))
           .andExpect(status().isCreated());
    }
}
~~~

Ở đây **post()** phải được static import từ **org.springframework.test.web.servlet.request.MockMvcRequestBuilders**, cùng class với **get()**. Không có class request builder tên **SecurityMockMvcRequestBuilders** trong ví dụ này; request builders thuộc Spring Framework MockMvc.

**csrf()** trả về một **RequestPostProcessor** để gắn token vào request Servlet. Có thể tạo token không hợp lệ bằng **csrf().useInvalidToken()**, hoặc đặt token ở header bằng **csrf().asHeader()** nếu muốn kiểm tra cách ứng dụng xử lý các dạng token. Status **201** trong ví dụ phụ thuộc controller; thay bằng status thật mà endpoint trả về.

### 4.3. Ví dụ JWT với MockMvc

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void scopeIsRequired() throws Exception {
    mvc.perform(get("/api/export")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.export"))))
       .andExpect(status().isOk());
}
~~~

**jwt()** thuộc **SecurityMockMvcRequestPostProcessors**. Nó dựng một authentication JWT giả lập để kiểm tra authorization; test này không tự kiểm tra chữ ký, issuer, audience, thời hạn hoặc kết nối JWK của token thật.

## 5. Reactive: static import cho WebTestClient

### 5.1. Class sở hữu các mutator

Với Spring WebFlux, class chính là:

~~~java
org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers
~~~

Các static method tiêu biểu:

| Static method | Mục đích |
|---|---|
| **springSecurity()** | Tích hợp Spring Security vào **WebTestClient.Builder** |
| **mockUser()**, **mockUser("lan")** | Gắn user giả lập vào **ServerWebExchange** |
| **mockJwt()** | Tạo JWT authentication giả lập |
| **mockOpaqueToken()** | Tạo opaque token authentication giả lập |
| **mockOAuth2Login()** | Tạo OAuth2 Login authentication giả lập |
| **mockOidcLogin()** | Tạo OIDC Login authentication giả lập |
| **mockOAuth2Client()** | Tạo OAuth2 authorized client giả lập trong session |
| **csrf()** | Gắn CSRF token vào Reactive exchange |

Static import thường dùng:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
~~~

Ở đây **không** import **SecurityMockMvcRequestPostProcessors**, dù tên một số helper có vẻ tương tự. Các method trả về mutator/configurer dành cho **WebTestClient** và **ServerWebExchange**, không phải **RequestPostProcessor** cho **MockHttpServletRequest**.

### 5.2. Ví dụ user và JWT với WebTestClient

Giả định **client** đã được cấu hình với **SecurityWebFilterChain** của ứng dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveSecurityTest {
    @Autowired
    private WebTestClient client;

    @Test
    void ordinaryUserCannotReadAdminEndpoint() {
        client.mutateWith(mockUser("lan").roles("USER"))
              .get().uri("/api/admin/reports")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void jwtWithExportScopeCanExport() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.export")))
              .get().uri("/api/export")
              .exchange()
              .expectStatus().isOk();
    }
}
~~~

Khác với Servlet, **mockUser()**/**mockJwt()** được gắn bằng **.mutateWith(...)** trên client, sau đó request được tạo bằng **.get()**/**.post()**, chỉ định URI bằng **.uri(...)** và thực thi bằng **.exchange()**.

### 5.3. Cấu hình WebTestClient với security chain

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

**springSecurity()** ở đây được static import từ **SecurityMockServerConfigurers**. Phương thức có cùng tên với Servlet nhưng trả về **MockServerConfigurer** phù hợp với WebFlux. Nếu dùng Boot auto-configuration để inject **WebTestClient**, hãy xác minh cấu hình test thực sự có security chain; không cần tự áp dụng lại configurer một cách máy móc.

### 5.4. Ví dụ CSRF với WebTestClient

Reactive cũng có static method **csrf()**, nhưng nó đến từ **SecurityMockServerConfigurers** và được áp dụng bằng **mutateWith()**:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
      .post()
      .uri("/login")
      .exchange()
      .expectStatus().isOk();
~~~

Ví dụ này minh họa cách gắn token hợp lệ; status thành công phụ thuộc endpoint. Không dùng **.with(csrf())** của Servlet cho WebTestClient.

## 6. Những tên giống nhau nhưng khác kiểu trả về

Một số tên helper giống nhau ở hai stack. **Không được suy luận rằng cùng tên nghĩa là cùng API**:

| Helper | Servlet return type / đối tượng được tác động | Reactive return type / đối tượng được tác động |
|---|---|---|
| **csrf()** | **CsrfRequestPostProcessor**, tác động **MockHttpServletRequest** | **CsrfMutator**, tác động **ServerWebExchange** |
| **springSecurity()** | **MockMvcConfigurer**, cấu hình MockMvc | **MockServerConfigurer**, cấu hình WebTestClient |
| **user(...) / mockUser(...)** | **RequestPostProcessor**, tạo authentication cho request | **UserExchangeMutator**, tạo principal cho exchange |
| **jwt() / mockJwt()** | **JwtRequestPostProcessor** | **JwtMutator** |
| **opaqueToken() / mockOpaqueToken()** | **OpaqueTokenRequestPostProcessor** | **OpaqueTokenMutator** |
| **oauth2Login() / mockOAuth2Login()** | **OAuth2LoginRequestPostProcessor** | **OAuth2LoginMutator** |
| **oidcLogin() / mockOidcLogin()** | **OidcLoginRequestPostProcessor** | **OidcLoginMutator** |

Điểm khác biệt có thể quan sát ngay khi gọi method:

- Servlet: **mvc.perform(request.with(user("lan")))**
- Reactive: **client.mutateWith(mockUser("lan")).get().uri("/...").exchange()**

Đây là hai mô hình request khác nhau. Servlet dùng **MockHttpServletRequest** và **RequestPostProcessor**; Reactive dùng **ServerWebExchange** và **WebTestClientConfigurer**/mutator. IDE không thể tự chuyển một kiểu sang kiểu kia chỉ bằng cách đổi static import.

## 7. Request builder và response matcher không thuộc cùng nhóm với security helper

Đây là nguyên nhân phổ biến khiến người học import nhầm package.

### 7.1. Servlet: builder và matcher từ Spring Framework

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
~~~

Các method **get()**, **post()**, **status()**, **content()** đến từ **Spring Framework MockMvc**. Security helper như **user()**, **csrf()**, **jwt()** đến từ **Spring Security Test**.

Có thể kiểm tra authentication bằng:

~~~java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

mvc.perform(get("/api/profile").with(user("lan")))
   .andExpect(authenticated());
~~~

### 7.2. Reactive: client và expectation là API instance

Với **WebTestClient**, thông thường không có static import cho **get()** hoặc **status()** như MockMvc:

~~~java
client.get()
      .uri("/api/profile")
      .exchange()
      .expectStatus().isOk()
      .expectBody(String.class).isNotEmpty();
~~~

Các method **get()**, **uri()**, **exchange()**, **expectStatus()** và **expectBody()** là method instance trên client/result spec. Security helper được static import từ **SecurityMockServerConfigurers**, rồi gắn bằng **mutateWith(...)**.

## 8. Annotation @WithMockUser dùng chung, không phải static import

Một khác biệt khác cần nhớ: **@WithMockUser** **không phải static method**. Đây là annotation được import thông thường:

~~~java
import org.springframework.security.test.context.support.WithMockUser;
~~~

Annotation có thể sử dụng trong các test tích hợp Spring TestContext cho cả hai stack khi cơ chế test security tương ứng hoạt động:

~~~java
@Test
@WithMockUser(username = "lan", roles = "ADMIN")
void authenticatedUserCanAccess() {
    // Security Test listener thiết lập SecurityContext cho test.
}
~~~

Nếu muốn gắn danh tính riêng cho từng request, Servlet thường dùng **user()**; Reactive dùng **mockUser()**. Đừng static import annotation hoặc cố tìm **WithMockUser.withMockUser()**.

## 9. Ví dụ đầy đủ: so sánh hai bộ import

### 9.1. Bộ import Servlet / MockMvc

~~~java
// Spring Security Test: request post-processors và MockMvc configurer
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

// Spring Framework: request builder và response matcher
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Dùng trong test:

~~~java
mvc.perform(get("/api/reports").with(user("lan").roles("ANALYST")))
   .andExpect(status().isOk());

mvc.perform(post("/api/reports")
        .with(user("minh").roles("ADMIN"))
        .with(csrf()))
   .andExpect(status().isCreated());

mvc.perform(get("/api/export")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.export"))))
   .andExpect(status().isOk());
~~~

### 9.2. Bộ import Reactive / WebTestClient

~~~java
// Spring Security Test: WebTestClient configurers/mutators
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

// Spring Framework: WebTestClient là client instance
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;
~~~

Dùng trong test:

~~~java
client.mutateWith(mockUser("lan").roles("ANALYST"))
      .get().uri("/api/reports")
      .exchange()
      .expectStatus().isOk();

client.mutateWith(mockUser("minh").roles("ADMIN"))
      .mutateWith(csrf())
      .post().uri("/api/reports")
      .exchange()
      .expectStatus().isCreated();

client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.export")))
      .get().uri("/api/export")
      .exchange()
      .expectStatus().isOk();
~~~

Các ví dụ giả định security chain có policy tương ứng và controller trả **201** cho thao tác tạo. Với Reactive, CSRF mutator được áp dụng bằng **mutateWith(csrf())** trên WebTestClient. Hãy kiểm tra cú pháp của version Security đang dùng nếu bạn đang làm việc trên một dòng cũ.

## 10. Lỗi import thường gặp và cách sửa

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| **user()** không có trong class import | Import nhầm **SecurityMockServerConfigurers** (Reactive) hoặc package không đúng | MVC dùng **SecurityMockMvcRequestPostProcessors.user**; WebFlux dùng **SecurityMockServerConfigurers.mockUser** |
| **mockUser()** không tồn tại | Import class Servlet hoặc đang dùng API không đúng stack | Chọn Reactive **SecurityMockServerConfigurers** và kiểm tra version |
| **jwt()** không compile trong WebFlux | Đang dùng helper Servlet **jwt()** | Reactive dùng **mockJwt()** |
| **mockJwt()** không compile trong MVC | Đang dùng helper Reactive | Servlet dùng **jwt()** |
| **csrf()** có type không khớp **.with(...)** | Lấy CSRF mutator Reactive cho MockMvc | Dùng **SecurityMockMvcRequestPostProcessors.csrf()** |
| **springSecurity()** trả về type không phù hợp builder | Static import cùng tên từ class của stack còn lại | MVC: **SecurityMockMvcConfigurers**; WebFlux: **SecurityMockServerConfigurers** |
| **get()** không compile trong MockMvc | Import nhầm request builder hoặc không import static | Dùng **MockMvcRequestBuilders.get** từ Spring Framework |
| **status()** không tìm thấy trong WebTestClient | Đang cố dùng matcher MockMvc | Dùng instance chain **.expectStatus().isOk()** |
| IDE tự import class từ package sai | Có nhiều class/method tương tự trên classpath | Xóa import sai, nhập FQCN đúng hoặc dùng import tường minh |
| Không tìm thấy package **org.springframework.security.test...** | Thiếu **spring-security-test**/starter test hoặc lệch version | Kiểm tra test classpath và dependency management |

### 10.1. Kiểm tra import bằng IDE

Khi IDE tự thêm import:

1. Đặt con trỏ trên tên method **user**, **jwt**, **csrf** hoặc **springSecurity**.
2. Dùng chức năng *Go to Declaration* hoặc *Quick Documentation*.
3. Đọc **fully qualified class name** và kiểu trả về.
4. So sánh với stack của client: **MockMvc** hay **WebTestClient**.
5. Nếu import sai, xóa dòng import rồi thêm đúng class/method bằng autocomplete có kiểm soát.

Không nên giải quyết lỗi bằng wildcard import từ cả hai package:

~~~java
// Không khuyến khích: che khuất nguồn gốc helper
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.*;
~~~

Dùng import tường minh sẽ giúp reviewer nhận ra ngay test đang dùng API của stack nào.

### 10.2. Kiểm tra dependency khi package không tồn tại

Maven:

~~~bash
./mvnw dependency:tree -Dscope=test
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
~~~

Đảm bảo **spring-security-test** thuộc cùng dòng phiên bản với Spring Security runtime. Với Spring Boot, ưu tiên để BOM quản lý. Không ép riêng một bản Spring Security Test khác major chỉ để có method hoặc class trong ví dụ mới.

## 11. Static import trong Kotlin

Từ khóa **static** thuộc cú pháp Java. Kotlin import top-level/static member bằng cú pháp **import** thông thường, ví dụ:

~~~kotlin
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser
~~~

Sau đó gọi **mockUser()** trong test Kotlin theo API phù hợp. Không sao chép nguyên dòng Java **import static ...** vào file **.kt**.

## 12. Bảng chọn nhanh theo câu hỏi

| Bạn đang viết... | Hãy tìm static import... | Kết hợp với... |
|---|---|---|
| Servlet, thêm user vào request | **SecurityMockMvcRequestPostProcessors.user** | **MockMvc.perform(...).with(...)** |
| Servlet, giả lập JWT | **SecurityMockMvcRequestPostProcessors.jwt** | **MockMvc** |
| Servlet, CSRF | **SecurityMockMvcRequestPostProcessors.csrf** | **MockMvc** |
| Servlet, lắp security filter | **SecurityMockMvcConfigurers.springSecurity** | **MockMvcBuilders.webAppContextSetup** |
| Servlet, kiểm tra authenticated | **SecurityMockMvcResultMatchers.authenticated** | **MockMvc.andExpect(...)** |
| Reactive, thêm user vào exchange | **SecurityMockServerConfigurers.mockUser** | **WebTestClient.mutateWith(...)** |
| Reactive, giả lập JWT | **SecurityMockServerConfigurers.mockJwt** | **WebTestClient** |
| Reactive, CSRF | **SecurityMockServerConfigurers.csrf** | **WebTestClient** |
| Reactive, lắp security chain | **SecurityMockServerConfigurers.springSecurity** | **WebTestClient.Builder.apply(...)** |

## 13. Bài tập thực hành

Một ứng dụng có ba endpoint:

- **GET /api/reports**: yêu cầu role **ANALYST**.
- **POST /api/reports**: yêu cầu role **ADMIN** và CSRF khi chính sách áp dụng.
- **GET /api/export**: yêu cầu authority **SCOPE_reports.export**.

Hãy viết hai lớp test độc lập:

**Lớp Servlet / MockMvc**

1. Static import **user()**, **jwt()**, **csrf()** từ **SecurityMockMvcRequestPostProcessors**.
2. Static import **springSecurity()** từ **SecurityMockMvcConfigurers**.
3. Static import **get()**, **post()**, **status()** từ Spring Framework MockMvc.
4. Kiểm tra user thiếu role, user đúng role, request POST thiếu/có CSRF, JWT thiếu/đủ scope.

**Lớp Reactive / WebTestClient**

1. Static import **mockUser()**, **mockJwt()**, **csrf()**, **springSecurity()** từ **SecurityMockServerConfigurers**.
2. Khởi tạo client với **bindToApplicationContext(...).apply(springSecurity())** hoặc auto-configuration tương đương.
3. Kiểm tra role, scope và CSRF theo policy thực tế.
4. Đọc lại toàn bộ import, giải thích kiểu trả về của từng helper và vì sao chúng không thể thay thế helper ở lớp Servlet.

**Tiêu chí đạt:** mỗi lớp test biên dịch với dependency phù hợp, chạy qua đúng security chain, có cả ca được phép và bị từ chối; người học có thể giải thích vì sao **user()** khác **mockUser()** dù cùng tạo principal giả lập.

## 14. Tài liệu tham khảo chính thức

- [Spring Security — Servlet MockMvc Request Post-Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): **user()**, **csrf()**, **jwt()**, **opaqueToken()**, OAuth2/OIDC.
- [Spring Security — Servlet MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): **SecurityMockMvcConfigurers.springSecurity()**.
- [Spring Security — Reactive Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): **mockUser()**, annotation và **mutateWith**.
- [Spring Security — Reactive Test CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): **csrf()** cho **WebTestClient**.
- [Spring Security — Reactive Test Web Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): **SecurityMockServerConfigurers.springSecurity()**.
- [Javadoc — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): API Servlet và kiểu trả về.
- [Javadoc — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): API Reactive và kiểu mutator.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) và [WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): request builder, client và response assertions.

> Trước khi copy một static import, hãy xác nhận **stack của ứng dụng**, **client đang dùng**, **class sở hữu method** và **phiên bản spring-security-test**. Bốn thông tin này ngăn lỗi import nhầm giữa Servlet và Reactive.
