# 22.1. Xác định grant được Spring Security hỗ trợ theo phiên bản

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, câu hỏi “Spring Security có hỗ trợ grant X không?” nghe có vẻ đơn giản nhưng thực ra cần kiểm tra nhiều lớp. Một grant có thể được định nghĩa trong RFC, được Authorization Server (AS) hỗ trợ, có class provider trong một phiên bản Spring Security, nhưng **chưa được bật** trong `OAuth2AuthorizedClientManager` của ứng dụng.

Vấn đề càng quan trọng với **grant mở rộng** như **JWT Bearer** hoặc **Token Exchange**, vì API và cách cấu hình thay đổi theo phiên bản. Một ví dụ cho Spring Security 6.5 có thể không biên dịch ở 6.1; một ví dụ cũ sử dụng `password()` còn tồn tại trong 6.5 nhưng không còn phù hợp với Spring Security 7.

Sau bài học, bạn có thể:

1. Phân biệt **grant được giao thức định nghĩa**, **AS chấp nhận**, **Spring Security có implementation**, và **ứng dụng đã bật**.
2. Xác định đúng phiên bản `spring-security-oauth2-client` đang chạy, không nhầm với phiên bản Spring Boot hoặc Spring Framework.
3. Đọc versioned Reference Documentation, Javadoc, `@Since`, `@Deprecated`, release notes và mã nguồn tương ứng.
4. Sử dụng một bảng mốc phiên bản cho `authorization_code`, `refresh_token`, `client_credentials`, `password`, `jwt-bearer` và `token-exchange`.
5. Giải thích sự khác nhau giữa grant type, client authentication method và tính năng bổ trợ như PKCE/OIDC.
6. Hiểu `OAuth2AuthorizedClientProviderBuilder`, `ReactiveOAuth2AuthorizedClientProviderBuilder` và cách thêm provider mở rộng.
7. Phân biệt hỗ trợ trên **Servlet** và **Reactive/WebFlux**, cùng cách chọn manager thích hợp.
8. Xử lý bài toán nâng cấp từ Spring Security 5.x/6.x lên 7.x mà không giữ grant đã bị loại bỏ.
9. Kiểm tra khả năng hỗ trợ của một grant mới mà không suy luận từ việc YAML chấp nhận chuỗi `authorization-grant-type`.
10. Thiết kế integration test chứng minh grant thực sự hoạt động với Authorization Server được cấu hình.

## 1. Vì sao “hỗ trợ một grant” có nhiều nghĩa?

Giả sử bạn được yêu cầu tích hợp một dịch vụ với Authorization Server bằng `urn:ietf:params:oauth:grant-type:token-exchange`. Developer thử thêm:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          downstream-api:
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
~~~

Ứng dụng khởi động không báo lỗi. Có thể kết luận Token Exchange đã hoạt động chưa?

**Chưa.** Việc binder chấp nhận một `AuthorizationGrantType` tùy biến chỉ xác nhận **một phần cấu hình**. Chưa chứng minh:

- Dependency có implementation phù hợp.
- Manager đã có provider thực hiện Token Exchange.
- Provider tìm được `subject_token` hợp lệ.
- Token response client gửi request đúng format.
- Authorization Server hỗ trợ Token Exchange cho client này.
- Token được cấp có audience/scope phù hợp Resource Server.
- Thành công/thất bại được lưu và xử lý đúng.

Cần đánh giá tuần tự.

### 1.1. Bốn lớp cần xác nhận

| Lớp | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| **A — OAuth protocol** | Grant X có được đặc tả hoặc được AS định nghĩa không? | RFC/spec hoặc tài liệu provider |
| **B — Authorization Server** | AS có hỗ trợ và **cho phép client này** sử dụng grant không? | Metadata, client registration, docs, token endpoint |
| **C — Spring Security library** | Phiên bản thư viện có provider/token response client tương ứng không? | Javadoc đúng version, release notes, dependency |
| **D — Runtime configuration** | Ứng dụng có wiring provider/manager, context và store đúng không? | Cấu hình bean, startup, integration test |

**Cả bốn lớp đều phải phù hợp** trước khi nói “grant X được hỗ trợ trong hệ thống”.

### 1.2. Sơ đồ ra quyết định

~~~mermaid
flowchart TD
    A["Cần grant X"] --> B{"Spec / AS định nghĩa grant?"}
    B -->|Không| C["Không thể tự dùng grant tùy ý"]
    B -->|Có| D{"AS cho phép client dùng grant?"}
    D -->|Không| E["Sửa chính sách/registration ở AS"]
    D -->|Có| F{"Version Spring có provider?"}
    F -->|Có| G{"Provider được bật trong manager?"}
    F -->|Không| H["Nâng phiên bản hoặc viết extension provider"]
    G -->|Không| I["Đăng ký/wiring provider"]
    G -->|Có| J{"Context, assertion/token và API phù hợp?"}
    J -->|Không| K["Bổ sung token resolver / response client"]
    J -->|Có| L["Integration test với AS và API"]
    L --> M{"Token endpoint và Resource Server chấp nhận?"}
    M -->|Có| N["Grant hoạt động trong hệ thống"]
    M -->|Không| O["Chẩn đoán client auth, audience, scope, policy"]
~~~

## 2. Grant type là gì?

**Authorization grant** là cơ chế để OAuth client nhận access token từ Authorization Server hoặc nhận/cập nhật sự ủy quyền phù hợp.

Các giá trị quen thuộc:

~~~text
authorization_code
refresh_token
client_credentials
password
urn:ietf:params:oauth:grant-type:jwt-bearer
urn:ietf:params:oauth:grant-type:token-exchange
~~~

Nhưng những giá trị này có vòng đời hỗ trợ rất khác nhau.

### 2.1. Core grant và extension grant

Ba cơ chế thường gặp trong ứng dụng Spring Security hiện đại:

- `authorization_code`: người dùng tương tác qua authorization endpoint; client đổi authorization code lấy token.
- `refresh_token`: khi có refresh token được cấp trước đó, client xin token mới.
- `client_credentials`: client/service dùng danh tính của chính nó để xin access token.

Các grant mở rộng:

- `urn:ietf:params:oauth:grant-type:jwt-bearer`: dùng JWT assertion làm authorization grant theo profile tương ứng.
- `urn:ietf:params:oauth:grant-type:token-exchange`: trao đổi security token để nhận token dành cho mục đích/resource khác theo chính sách AS.
- Những grant khác như device authorization, CIBA hoặc grant riêng của provider **phải được xác minh từng phiên bản**; không mặc định Spring Security OAuth2 Client có sẵn provider chỉ vì có RFC.

### 2.2. `password`: có lịch sử hỗ trợ nhưng không còn phù hợp

Resource Owner Password Credentials grant (`password`) cho client trực tiếp nhận username/password của resource owner và đổi token.

Đây là cách thiết kế không phù hợp với hướng dẫn bảo mật OAuth hiện đại. **Spring Security đã deprecated API password grant ở dòng 5.8 và loại bỏ hỗ trợ ở 7.0**.

Điều đó tạo ra khác biệt lớn giữa một codebase cũ 5.8/6.5 và ứng dụng mới 7.x.

### 2.3. Refresh token là grant để gia hạn, không phải login flow độc lập

Muốn dùng `refresh_token`, client thường phải có `OAuth2AuthorizedClient` chứa refresh token đã được AS cấp từ trước.

Việc provider `refreshToken()` có mặt không bảo đảm AS cấp refresh token ban đầu. Nếu client chưa có R1, provider này không tự tạo một refresh token giả.

### 2.4. OpenID Connect không phải một grant type mới

OIDC thường sử dụng Authorization Code flow với scope `openid`; ID token bổ sung lớp xác thực End-User.

Do đó:

~~~text
authorization_code + openid
~~~

khác với:

~~~text
grant_type = oidc
~~~

Không mặc định có một `AuthorizationGrantType("oidc")` được manager hỗ trợ.

### 2.5. PKCE cũng không phải grant riêng

PKCE là cơ chế bảo vệ Authorization Code flow bằng code verifier/challenge. Nó không thêm một OAuth grant type tên `pkce`.

Khi hỏi một phiên bản có hỗ trợ PKCE hay không, cần xem tính năng Authorization Code, resolver và client registration, không đi tìm `OAuth2AuthorizedClientProviderBuilder.pkce()`.

## 3. Trước tiên phải biết chính xác phiên bản thư viện

Một ứng dụng có thể khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Nhưng **Spring Boot version không đồng nhất với Spring Security version**. Boot thường quản lý một tập phiên bản dependency tương thích; ứng dụng có thể override version hoặc phụ thuộc bắc cầu gây khác biệt.

### 3.1. Các con số cần ghi nhận

Khi điều tra, nên có:

~~~text
Java version:
Spring Boot version:
Spring Framework version:
spring-security-config version:
spring-security-oauth2-client version:
Spring Security reference doc version:
Servlet hay Reactive stack:
Authorization Server product/version:
~~~

Không nên so sánh duy nhất theo “Spring Boot 3.x” rồi kết luận grant nào đã tồn tại. Mọi `@Since` của Spring Security là mốc theo **Spring Security**, không theo Boot.

### 3.2. Maven: xem dependency tree

Chạy trong một dự án Maven thật khi cần kiểm tra:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-client
~~~

Hoặc xem các dependency liên quan:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Kết quả cho biết phiên bản `spring-security-oauth2-client` được resolve bởi Maven. Khi có dependency management/override, đây là dữ liệu có ý nghĩa hơn việc chỉ đọc version của starter trong source.

### 3.3. Maven: xem effective POM

~~~bash
mvn help:effective-pom
~~~

Effective POM cho biết dependency management và các property đã được Maven kết hợp theo parent/BOM/profile.

Nếu cần chẩn đoán dependency version, đừng sửa BOM hoặc ép version chỉ để một đoạn code biên dịch; phải xét toàn bộ mức tương thích của Spring Boot/Spring Framework/Spring Security.

### 3.4. Gradle: xem dependencyInsight

~~~bash
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

Ở Windows có thể sử dụng:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

Để xem nhóm dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu dự án có nhiều module, chạy task trên module thực sự chứa OAuth2 client. Kết quả Gradle cho biết dependency được chọn sau conflict resolution/platform constraints.

### 3.5. Nhận diện dependency sai package

Có các module mang tên gần nhau:

~~~text
spring-security-oauth2-client
spring-security-oauth2-resource-server
spring-security-oauth2-jose
spring-security-oauth2-authorization-server (tùy dự án)
~~~

- **OAuth2 Client**: xin, lưu và sử dụng token để gọi API.
- **Resource Server**: kiểm tra token được gửi tới API.
- **Authorization Server**: cấp token và quản lý grant theo AS.

**Có một class grant ở Authorization Server không chứng minh OAuth2 Client có provider tương ứng**. Cần kiểm tra module và package đúng.

## 4. Bảng mốc phiên bản quan trọng

Các mốc dưới đây là **mốc chức năng/API**, không phải lời hứa cấu hình nào cũng được bật mặc định. Với dự án thực tế, luôn đối chiếu Javadoc **đúng bản patch/minor đang dùng**.

| Dòng Spring Security | Các điểm cần biết khi đánh giá grant |
|---|---|
| **5.2** | `OAuth2AuthorizedClientProviderBuilder` và reactive counterpart có từ 5.2; builder hỗ trợ nhóm `authorization_code`, `refresh_token`, `client_credentials`, `password` trong các bản 5.x tương ứng |
| **5.5** | `JwtBearerOAuth2AuthorizedClientProvider` có mặt từ 5.5 (theo Javadoc `Since`); grant JWT Bearer là extension, cần cấu hình |
| **5.8** | API `password()` bắt đầu bị **deprecated**, theo hướng dẫn OAuth Security Best Current Practice |
| **6.2** | Cấu hình component-based có thể nhận `OAuth2AuthorizedClientProvider` bean để bổ sung extension vào manager mặc định, theo điều kiện tự động cấu hình |
| **6.3** | `TokenExchangeOAuth2AuthorizedClientProvider` và reactive counterpart được giới thiệu (Javadoc `Since: 6.3`) |
| **6.5** | Có ba grant thông dụng, provider JWT Bearer và Token Exchange; `password` vẫn xuất hiện nhưng deprecated/for removal |
| **7.0** | **Loại bỏ password grant**; builder chính còn `authorization_code`, `refresh_token`, `client_credentials`, có hook `provider(...)` cho extension |

**Cách đọc:** không nên diễn giải “6.5 hỗ trợ password” thành khuyến nghị triển khai password grant mới. Ở dòng 6.5, API này đã deprecated và có kế hoạch loại bỏ.

### 4.1. Sơ đồ tiến hóa

~~~mermaid
timeline
    title Mốc API của Spring Security OAuth2 Client
    5.2 : AuthorizedClientProviderBuilder
        : authorization_code / refresh_token / client_credentials / password
    5.5 : JwtBearerOAuth2AuthorizedClientProvider
    5.8 : password grant API deprecated
    6.2 : Provider bean integration thuận tiện hơn
    6.3 : TokenExchangeOAuth2AuthorizedClientProvider
    6.5 : password vẫn có nhưng deprecated
    7.0 : password grant removed
~~~

Bảng và timeline giúp xác định hướng triển khai, nhưng **class/method cụ thể phải được xác minh ở artifact thực tế**.

## 5. Bảng grant theo các dòng phiên bản

Để không nhầm ba tình trạng “có API / mặc định bật / phải cấu hình”, bảng dùng các ký hiệu:

- **Có API**: tồn tại implementation/provider trong dòng version tương ứng.
- **Extension**: có API nhưng thường phải khai báo provider theo cách phù hợp.
- **Deprecated**: API còn đó nhưng không nên dùng và có thể bị xóa.
- **Không còn**: không có API hỗ trợ chuẩn tương ứng ở dòng đó.

| Grant | 5.8 | 6.2 | 6.3–6.5 | 7.0 |
|---|---|---|---|---|
| `authorization_code` | Có API | Có API | Có API | Có API |
| `refresh_token` | Có API | Có API | Có API | Có API |
| `client_credentials` | Có API | Có API | Có API | Có API |
| `password` | Deprecated | Deprecated | Deprecated | **Đã loại bỏ** |
| `jwt-bearer` | Extension có provider | Extension có provider | Extension có provider | Extension có provider |
| `token-exchange` | Chưa có provider tích hợp từ 6.3 | Chưa có provider tích hợp từ 6.3 | Extension có provider | Extension có provider |
| Grant riêng của AS | Cần extension nếu không có sẵn | Cần extension nếu không có sẵn | Cần extension nếu không có sẵn | Cần extension nếu không có sẵn |

**Chú thích quan trọng:** hàng `token-exchange` nói về **provider tích hợp của Spring Security**. Một ứng dụng ở phiên bản cũ vẫn có thể tự viết custom provider hoặc dùng thư viện khác nếu AS hỗ trợ; điều đó không làm provider `TokenExchangeOAuth2AuthorizedClientProvider` tồn tại trước mốc `Since: 6.3`.

### 5.1. Vì sao không ghi “mặc định bật” trong bảng?

“Bật mặc định” phụ thuộc:

- Servlet hay Reactive.
- `HttpSecurity.oauth2Client()`, `oauth2Login()` hoặc WebFlux DSL.
- Manager được tạo tự động hay bean do ứng dụng tự định nghĩa.
- Provider chain do ứng dụng thay thế.
- Context token/assertion được cung cấp.
- Phần extension có được đăng ký hay không.

Một class trên classpath **không tự bảo đảm grant hoạt động**.

### 5.2. Bản 7.x cần kiểm tra riêng

Khi nâng lên Spring Security 7.x, API `password()` không còn. Nếu code vẫn gọi:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
        .password()
        .build();
~~~

đó là một trong những nơi cần migration. Không cố thay thế bằng workaround thu nhận username/password của user để giả lập lại ROPC.

## 6. Nguồn nào có độ tin cậy cao để xác định grant?

Thứ tự nên theo nhu cầu:

1. **Dependency thực tế** được Maven/Gradle resolve.
2. **Versioned Spring Security Reference Documentation** khớp major/minor.
3. **Javadoc** đúng version, đặc biệt `Since`, `Deprecated` và chữ ký API.
4. **What's New / Migration Guide** cho nâng cấp major/minor.
5. **Source/jar** đúng artifact nếu tài liệu chưa rõ hành vi.
6. **Integration test** với Authorization Server mà dự án sử dụng.

### 6.1. Tài liệu có nhãn version rõ ràng

Ví dụ những đường dẫn chính thức:

- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security 6.5 — Authorization Grant Support](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorization-grants.html)
- [Spring Security 7.0 — OAuth2 Client](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/client/index.html)
- [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)

Không đọc trang `/reference/servlet/oauth2/client/` không có version rồi mặc định nó mô tả bản 5.8 đang chạy.

### 6.2. Javadoc của builder theo version

- [6.5 — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [7.0 — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [6.5 — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html)
- [7.0 — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html)

So sánh các method giữa hai bản sẽ thấy `password()` hiện diện và deprecated ở 6.5 nhưng không còn trong builder 7.0.

### 6.3. Javadoc `Since` của extension provider

- [JWT Bearer provider — Since 5.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/JwtBearerOAuth2AuthorizedClientProvider.html)
- [Token Exchange provider — Since 6.3](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html)
- [Reactive Token Exchange provider — Since 6.3](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/TokenExchangeReactiveOAuth2AuthorizedClientProvider.html)

`Since` chỉ chứng minh **lớp API có từ phiên bản đó**. Nó không tự chứng minh Spring Boot đã auto-wire bean hay Authorization Server chấp nhận grant.

### 6.4. Nếu gặp tài liệu cũ?

Một blog viết cho Spring Security 5.3 có thể sử dụng API cũ hoặc tự triển khai extension. Một bài cho 6.5 có thể dùng `password()` dù đã deprecated.

Khi tham khảo:

- Ghi ngày và phiên bản của ví dụ.
- Kiểm tra package/import và class hiện hành.
- Đối chiếu phương thức với Javadoc thực tế.
- Xem migration guide nếu copy code qua major version.
- Đừng dùng code từ một bản snapshot khác làm tài liệu chính thức cho production.

## 7. Đọc `OAuth2AuthorizedClientProviderBuilder` đúng cách

Trong Servlet stack, Spring Security có:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder
~~~

Với Spring Security 6.5 và 7.0, ba grant cốt lõi thường được chọn:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

Điều này tạo một `DelegatingOAuth2AuthorizedClientProvider` với các provider tương ứng.

### 7.1. Builder hỗ trợ gì không phải manager đã bật gì

Một builder có method `clientCredentials()` nghĩa là phiên bản thư viện cung cấp cách cấu hình provider này. Nếu ứng dụng thực tế tạo manager chỉ với:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build();
~~~

thì manager tùy biến này **không tự có `client_credentials`**, dù class provider nằm trên classpath.

### 7.2. Hook mở rộng `provider(...)`

Từ những bản hỗ trợ builder, có thể thêm một implementation `OAuth2AuthorizedClientProvider`:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(customExtensionProvider)
                .build();
~~~

Trong ví dụ, `customExtensionProvider` phải là object provider thực sự được tạo bằng API của version đang dùng.

Đây là cách extension grant được ghép vào manager; không phải mọi grant đều cần có method builder riêng như `tokenExchange()`.

### 7.3. Tìm class chưa đủ để biết token request thực hiện đúng

Cần xem thêm:

- `OAuth2AccessTokenResponseClient` tương ứng grant.
- Token request converter/header converter.
- Assertion/subject token resolver.
- Client authentication method.
- Error response parsing.
- Success/failure handlers của manager.

Một provider có mặt nhưng không có assertion hợp lệ vẫn có thể không authorize được.

## 8. Spring Security 6.5: nhóm grant cốt lõi

### 8.1. `authorization_code`

Thích hợp cho interactive browser login hoặc flow Authorization Code tương ứng.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

`authorization_code` yêu cầu authorization endpoint, redirect/callback và token endpoint phù hợp. Trong OIDC, `openid` kích hoạt yêu cầu ID token và những kiểm tra OIDC.

Không coi `OAuth2AuthorizedClientManager.authorize(...)` là API có thể tự mở browser trong background job.

### 8.2. `refresh_token`

Provider `refreshToken()` có thể xin access token mới khi có refresh token đang lưu và điều kiện refresh được thỏa mãn.

Không phải AS nào cũng phát refresh token sau Authorization Code. Nếu không có R1, provider không tự tạo R1.

Khi refresh response không có refresh token mới, client thông thường giữ refresh token cũ; nếu AS cấp R2 thì thay R1 bằng R2.

### 8.3. `client_credentials`

Dùng cho machine-to-machine service identity:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Client có thể xin token lần đầu và xin token mới khi hết hạn. Không cần End-User OIDC Login hay ID token.

### 8.4. Provider có API không nghĩa AS cho phép

Nếu AS không cho client `reporting-service` dùng `client_credentials`, token endpoint có thể trả `unauthorized_client`. Sửa provider ở Spring Security không thay thế việc đăng ký grant ở AS.

## 9. Extension grant: JWT Bearer

### 9.1. Không nhầm với JWT client authentication

Đây là một trong những lỗi kiến thức phổ biến nhất.

| Khái niệm | Dùng JWT để làm gì? |
|---|---|
| **JWT Bearer authorization grant** | JWT assertion là grant để xin access token |
| **`private_key_jwt` client authentication** | JWT assertion chứng minh danh tính **OAuth client** tại token endpoint |
| **OIDC ID token** | Chứng minh kết quả xác thực End-User cho Relying Party |
| **JWT access token** | Credential được Resource Server xác minh theo issuer/audience/scope |

Một ứng dụng có thể dùng grant `authorization_code` nhưng client authentication là `private_key_jwt`. Điều đó **không** biến grant thành `jwt-bearer`.

### 9.2. Grant URN

Giá trị của JWT Bearer grant:

~~~text
urn:ietf:params:oauth:grant-type:jwt-bearer
~~~

Ví dụ token request về mặt khái niệm:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=<JWT_ASSERTION>
~~~

Client authentication riêng vẫn có thể được yêu cầu theo hợp đồng AS. Không log raw assertion vì có thể là credential nhạy cảm.

### 9.3. Provider đã có từ 5.5

Lớp:

~~~java
org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider
~~~

Javadoc ghi **`Since: 5.5`**. Điều này có nghĩa class có trong dòng 5.5 và sau đó khi tương thích, nhưng **không tự được bật trong mọi manager**.

### 9.4. Ví dụ cấu hình registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          jwt-delegation:
            provider: company-auth
            client-id: ${JWT_GRANT_CLIENT_ID}
            client-secret: ${JWT_GRANT_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:jwt-bearer
            scope:
              - orders.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Đây là cấu hình client giả định. AS phải cho phép grant JWT Bearer và thỏa thuận issuer, audience, signature, subject của assertion.

### 9.5. Thêm provider vào manager

Trong Servlet app có thể cấu hình:

~~~java
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(new JwtBearerOAuth2AuthorizedClientProvider())
                .build();
~~~

Điều này chỉ thêm khả năng xử lý grant vào chain. Client phải có JWT assertion hợp lệ và token response client/provider phải biết lấy assertion từ đâu.

Trong một số tình huống, `JwtBearerOAuth2AuthorizedClientProvider` lấy JWT assertion từ principal phù hợp (ví dụ `JwtAuthenticationToken`). Nếu nguồn JWT khác, cấu hình `setJwtAssertionResolver(...)` theo Javadoc của phiên bản đang dùng.

Không dùng ID token của người dùng như assertion tùy ý nếu AS không cho phép.

### 9.6. Phân biệt grant và audience

Một JWT assertion có thể được cấp cho một mục đích rất cụ thể. AS chỉ chấp nhận nó khi signature, issuer, subject, audience, expiry và policy đúng.

Không tự gắn một JWT đang có vào tham số `assertion` với hy vọng AS đổi thành access token dành cho mọi API.

## 10. Extension grant: Token Exchange

### 10.1. Ý nghĩa

Token Exchange theo RFC 8693 cho phép client gửi một **subject token** và có thể có **actor token**, xin token mới theo các ràng buộc của AS.

Ví dụ kiến trúc:

~~~text
Browser / Alice
   |
   v
Gateway (có user access token A1)
   |
   | Token Exchange request
   v
Authorization Server
   |
   | access token B1 dành cho Payments API
   v
Gateway -> Payments API
~~~

Token mới không mặc định có cùng scope/audience với token ban đầu. AS là bên quyết định quyền được trao đổi và policy delegation/impersonation.

### 10.2. Mốc tích hợp trong Spring Security

`TokenExchangeOAuth2AuthorizedClientProvider` có Javadoc **`Since: 6.3`**. Reactive counterpart cũng có `Since: 6.3`.

Vì vậy:

- Trên Spring Security 6.1/6.2: không dựa vào class provider tích hợp này.
- Từ 6.3: có thể sử dụng provider được Spring Security cung cấp.
- Spring Security 6.5 và 7.0: có thể dùng provider phù hợp khi wiring đúng.

### 10.3. Grant URN

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

Một token request khái niệm có thể gồm:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<SUBJECT_TOKEN>&subject_token_type=urn:ietf:params:oauth:token-type:access_token
~~~

Phần client authentication, requested token type, audience/resource, scope và actor token tùy hợp đồng cụ thể với AS.

### 10.4. Cấu hình registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          payments-exchange:
            provider: company-auth
            client-id: ${EXCHANGE_CLIENT_ID}
            client-secret: ${EXCHANGE_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - payments.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Ở đây `payments.read` chỉ là scope minh họa. AS cần cho phép exchange và cấp access token phù hợp Payments API.

### 10.5. Thêm Token Exchange provider (6.3+)

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;

TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
        new TokenExchangeOAuth2AuthorizedClientProvider();

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(exchangeProvider)
                .build();
~~~

**Cấu hình provider chưa hoàn thành toàn bộ use case.** Còn phải bảo đảm `subject_token` hợp lệ, subject/actor resolver và token response client phù hợp.

### 10.6. Subject token resolver

Theo Javadoc các phiên bản hỗ trợ, Token Exchange provider có extension points như:

~~~java
exchangeProvider.setSubjectTokenResolver(context -> {
    // Tìm token nguồn đã được xác minh từ ngữ cảnh tin cậy.
    // Trả về OAuth2Token phù hợp theo contract.
    throw new UnsupportedOperationException(
            "Configure a trusted subject token resolver");
});
~~~

Đoạn code chỉ phác thảo API, không phải resolver sẵn sàng dùng production.

Trong ví dụ chính thức, provider có thể lấy token từ principal `JwtAuthenticationToken` trong những ngữ cảnh phù hợp. Không cho browser tự nhập `subject_token` tùy ý rồi backend trao đổi bằng quyền của client.

### 10.7. Actor token và delegation

Actor token không phải lúc nào cũng có; một số flow cần thể hiện actor đang thực hiện hành động thay subject.

Khi dùng token exchange:

- Xác định ai là subject.
- Xác định actor là ai nếu cần.
- Xác định resource/audience đích.
- Áp policy chống tăng quyền.
- Kiểm tra token mới ở Resource Server.
- Không log raw subject/actor token.

## 11. Component-based configuration từ Spring Security 6.2

Đây là một mốc dễ nhầm vì nó là thay đổi **cách wiring provider**, không phải ngày mọi extension grant được phát minh.

Tài liệu Spring Security từ 6.2 mô tả rằng có thể khai báo bean `OAuth2AuthorizedClientProvider` để được cấu hình tự động với manager phù hợp trong những điều kiện framework quản lý manager mặc định.

### 11.1. Ví dụ bean JWT Bearer

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;

@Configuration
public class ExtensionGrantConfiguration {

    @Bean
    OAuth2AuthorizedClientProvider jwtBearerProvider() {
        return new JwtBearerOAuth2AuthorizedClientProvider();
    }
}
~~~

Trong cấu hình Spring Security phù hợp, provider bean được thêm vào manager mặc định cùng những grant thường dùng.

### 11.2. Không suy ra mọi custom manager tự thu thập bean

Nếu ứng dụng tự tạo:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
~~~

thì manager này chỉ dùng provider đã được bạn thiết lập, trừ khi ứng dụng tự ghép/thu thập bean khác.

Do đó, câu “từ 6.2 chỉ cần khai báo provider bean” phải được hiểu **trong cơ chế tự động cấu hình tương ứng**, không phải quy tắc áp dụng cho mọi manager tùy biến.

### 11.3. Trước 6.2

Khi không có cơ chế component-based thuận tiện như trên, cách cấu hình rõ ràng là:

1. Tạo `OAuth2AuthorizedClientProvider` composite.
2. Bổ sung các grant cốt lõi cần thiết.
3. Thêm extension provider bằng `provider(...)`.
4. Tạo/configure `OAuth2AuthorizedClientManager`.
5. Thiết lập provider chain lên manager.

Nếu thay manager mặc định mà chỉ giữ extension grant, có thể làm mất `authorization_code`, `refresh_token` hoặc `client_credentials` đã dùng trước đó.

## 12. Ví dụ manager Servlet với grant mở rộng

Mẫu cấu hình cho Spring Security **6.3+**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.JwtBearerOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class ServletGrantConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider chain =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .provider(
                                new JwtBearerOAuth2AuthorizedClientProvider())
                        .provider(
                                new TokenExchangeOAuth2AuthorizedClientProvider())
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(chain);
        return manager;
    }
}
~~~

### 12.1. Điều kiện để ví dụ thực sự chạy

- Spring Security version có các provider extension được import.
- ClientRegistrationRepository có registration tương ứng.
- Token Exchange/JWT Bearer provider nhận assertion/token nguồn hợp lệ.
- AS cho phép những grant và client authentication được đăng ký.
- Resource Server đích chấp nhận token được cấp.
- Authorized client repository/service lưu state theo principal phù hợp.

### 12.2. Tại sao không đưa `password()` vào?

Ở 6.5, `password()` đã deprecated; lên 7.0 không còn API. Cấu hình ví dụ này dùng các grant khuyến nghị hiện đại và không dựa vào ROPC.

### 12.3. Không nhầm manager với token request client

Manager điều phối provider và authorized client; provider gọi `OAuth2AccessTokenResponseClient` để tương tác token endpoint.

Một extension grant có thể cần token response client riêng, đặc biệt khi AS yêu cầu tham số, header hoặc định dạng response đặc thù.

Tự thêm một value `AuthorizationGrantType` mà không có provider và token response client không đủ.

## 13. Servlet và Reactive phải kiểm tra riêng

Spring Security có hai mô hình lớn:

| Khía cạnh | Servlet | Reactive |
|---|---|---|
| Manager interface | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Kết quả `authorize` | `OAuth2AuthorizedClient` hoặc `null` | `Mono<OAuth2AuthorizedClient>` |
| Provider interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Builder | `OAuth2AuthorizedClientProviderBuilder` | `ReactiveOAuth2AuthorizedClientProviderBuilder` |
| Web request | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange` |
| Authorized client storage | `OAuth2AuthorizedClientRepository/Service` | `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` |
| Client HTTP | `RestClient`, có thể WebClient trên Servlet | `WebClient` |

### 13.1. Reactive extension providers

Trong Spring Security 6.5, có những lớp như:

~~~java
org.springframework.security.oauth2.client.JwtBearerReactiveOAuth2AuthorizedClientProvider
org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider
~~~

Tên lớp không hoàn toàn trùng cách đặt từ phía Servlet, vì reactive suffix được thêm vào giữa tên.

### 13.2. Reactive provider builder

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.JwtBearerReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider;

ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .provider(
                        new JwtBearerReactiveOAuth2AuthorizedClientProvider())
                .provider(
                        new TokenExchangeReactiveOAuth2AuthorizedClientProvider())
                .build();
~~~

**Token Exchange reactive provider có từ Spring Security 6.3.** Ví dụ này cần phiên bản phù hợp, và còn phải được gắn vào một reactive manager.

### 13.3. Đừng bọc Servlet provider trong Reactor để “tạo hỗ trợ reactive”

Ví dụ sai về kiến trúc:

~~~java
Mono.fromCallable(() -> servletProvider.authorize(context));
~~~

Cách này không biến HTTP token exchange blocking thành reactive non-blocking đúng nghĩa, cũng không thay thế contract `ReactiveOAuth2AuthorizedClientProvider`.

Nếu ứng dụng WebFlux, dùng API reactive và token response client reactive tương ứng.

### 13.4. Password grant và reactive

Spring Security 6.5 còn API password provider/reactive password provider ở trạng thái deprecated. Ở 7.0, builder reactive cũng không còn `password()`.

Do đó kế hoạch migration phải kiểm tra **cả Servlet và Reactive call sites**, không chỉ một builder.

## 14. Xác minh grant không chỉ qua Javadoc provider

Một provider có thể tồn tại mà client vẫn thất bại vì **không có dữ liệu đầu vào**.

Ví dụ với Token Exchange:

~~~text
ClientRegistration:
  grantType = token-exchange

Provider:
  TokenExchangeOAuth2AuthorizedClientProvider tồn tại

OAuth2AuthorizationContext:
  subject token không có

AS:
  hỗ trợ token-exchange
~~~

Kết quả vẫn không thể authorize. Provider cần token nguồn hợp lệ theo contract.

### 14.1. Kiểm tra context resolver

- JWT Bearer: JWT assertion lấy từ đâu?
- Token Exchange: subject token/actor token lấy từ đâu?
- Authorization Code: browser callback, code/state/PKCE được xử lý ở đâu?
- Refresh Token: authorized client có refresh token không?
- Client Credentials: client authentication tại token endpoint là gì?

### 14.2. Kiểm tra token response client

Ở các phiên bản Spring Security mới, một extension grant có thể có token response client dựa trên `RestClient` hoặc `WebClient` phù hợp.

Không dùng API token response client có tên mới với bản dependency cũ mà chưa xem Javadoc. Một grant được hỗ trợ trong bản 5.5 có thể dùng implementation client khác với bản 6.5.

### 14.3. Client authentication khác grant

Ví dụ:

~~~yaml
client-authentication-method: private_key_jwt
authorization-grant-type: authorization_code
~~~

Đây là **Authorization Code** với JWT client authentication. Nó **không** dùng JWT Bearer authorization grant.

Ngược lại:

~~~yaml
authorization-grant-type: urn:ietf:params:oauth:grant-type:jwt-bearer
client-authentication-method: client_secret_basic
~~~

đây có thể là JWT Bearer grant cộng với client authentication HTTP Basic, nếu AS cho phép.

Bảng:

| Grant | Client authentication có thể gặp | Có phải cùng khái niệm? |
|---|---|---|
| Authorization Code | `client_secret_basic`, `private_key_jwt`, mTLS, public client `none` | Không |
| Client Credentials | `client_secret_basic`, `private_key_jwt`, mTLS | Không |
| JWT Bearer grant | Tùy AS, có thể cần client authentication riêng | Không |
| Token Exchange | Tùy AS, có thể cần client authentication riêng | Không |

## 15. Kiểm tra hỗ trợ từ Authorization Server

Ngay cả khi Spring Security có provider, AS vẫn có thể trả lỗi.

### 15.1. Metadata `grant_types_supported`

Nếu AS cung cấp OAuth Authorization Server Metadata, bạn có thể thấy trường:

~~~json
{
  "issuer": "https://id.example.com",
  "token_endpoint": "https://id.example.com/oauth2/token",
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials",
    "urn:ietf:params:oauth:grant-type:token-exchange"
  ]
}
~~~

Đây là **JSON minh họa**, không phải dữ liệu provider thật.

Metadata hữu ích để khám phá grant mà AS công bố, nhưng cần nhớ:

- Không phải mọi AS công bố đầy đủ các extension qua metadata.
- Metadata không chứng minh **client cụ thể** được phép dùng grant.
- AS có thể cần bật cấu hình riêng hoặc policy/audience phù hợp.
- Tài liệu của AS và integration test vẫn cần thiết.

### 15.2. Client registration tại AS

AS có thể hỗ trợ Token Exchange chung nhưng từ chối client `employee-portal` vì client chưa được cho phép.

Ví dụ lỗi:

~~~json
{
  "error": "unauthorized_client"
}
~~~

Không thể sửa bằng cách thêm `provider(new TokenExchangeOAuth2AuthorizedClientProvider())` nếu vấn đề nằm ở policy của AS.

### 15.3. Các lỗi cần phân biệt

| Lỗi | Khả năng nguyên nhân |
|---|---|
| `unsupported_grant_type` | AS không nhận grant, tên grant sai hoặc endpoint/profile chưa bật |
| `unauthorized_client` | AS nhận grant nhưng client chưa được phép dùng |
| `invalid_client` | Client authentication sai |
| `invalid_grant` | Grant/assertion/subject token không hợp lệ, hết hạn hoặc không phù hợp |
| `invalid_scope` | Scope yêu cầu không được cho phép |
| HTTP 401/403 từ Resource Server | Access token cuối cùng không được chấp nhận hoặc thiếu quyền |

Không kết luận “Spring Security không hỗ trợ grant” chỉ vì token endpoint trả `invalid_client`.

## 16. Tìm một grant chưa quen: quy trình 10 bước

Khi gặp `urn:example:params:oauth:grant-type:custom-delegation`, có thể đi theo quy trình:

1. **Ghi đúng grant value** theo protocol/AS; tránh viết sai URN.
2. **Xác nhận phiên bản dependency thực tế** `spring-security-oauth2-client`.
3. **Xác định Servlet hay Reactive**.
4. **Xem Javadoc version đó** có provider class không.
5. **Xem builder** có method chuyên dụng hay hook `provider(...)`.
6. **Xem `Since`/`Deprecated`** và migration notes.
7. **Xem token response client, resolver và context requirements**.
8. **Kiểm tra AS** hỗ trợ và cấp quyền dùng grant cho client.
9. **Cấu hình provider/manager/repository đúng**, không làm mất grant khác.
10. **Integration test** với AS test tenant và Resource Server, không dùng token thật trong log.

### 16.1. Quyết định tích hợp hay custom extension

~~~mermaid
flowchart TD
    A["Cần grant mở rộng X"] --> B{"Có built-in provider ở version hiện tại?"}
    B -->|Có| C["Dùng provider hiện có"]
    B -->|Không| D{"Có thể nâng Spring Security tương thích?"}
    D -->|Có| E["Nâng phiên bản được kiểm soát"]
    D -->|Không| F["Thiết kế custom OAuth2AuthorizedClientProvider"]
    C --> G["Cung cấp context/assertion/token resolver"]
    E --> G
    F --> G
    G --> H["AS policy + token endpoint integration test"]
    H --> I["Resource Server audience/scope validation"]
~~~

### 16.2. Không bỏ qua tương thích Spring Boot

Nâng riêng Spring Security để lấy một provider mới có thể làm lệch dependency stack. Cần xem Spring Boot BOM, Spring Framework, Java baseline và security configuration migration.

Không override hàng loạt version khi chưa có kế hoạch kiểm thử và tương thích.

## 17. Viết custom extension provider khi chưa có built-in

### 17.1. Khi nào cần?

Có thể cần nếu:

- AS sử dụng một grant custom thật sự.
- Version framework không cung cấp built-in provider.
- Do yêu cầu tương thích không thể nâng phiên bản.
- Grant cần token request/response format đặc thù.

Nhưng **tự viết provider là lựa chọn sau khi đã xác minh rõ** không có implementation phù hợp. Tự quản lý token endpoint và credential làm tăng bề mặt lỗi bảo mật.

### 17.2. Contract `OAuth2AuthorizedClientProvider`

Ở Servlet:

~~~java
public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context);
}
~~~

Đây là chữ ký rút gọn để giải thích contract.

Một provider custom cần:

- Kiểm tra grant của `ClientRegistration` có khớp mình hỗ trợ không.
- Trả `null` khi không xử lý được grant/ngữ cảnh, không tự cấp token giả.
- Lấy dữ liệu đầu vào tin cậy từ `OAuth2AuthorizationContext`.
- Gọi token endpoint bằng client authentication đúng.
- Parse/validate response và tạo `OAuth2AuthorizedClient` phù hợp.
- Xử lý expiry/reauthorize và refresh khi có contract.
- Bảo vệ token source, không log assertion, access token hoặc client secret.

### 17.3. Pseudocode provider

~~~java
public final class CustomGrantProvider
        implements OAuth2AuthorizedClientProvider {

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        ClientRegistration registration =
                context.getClientRegistration();

        if (!"urn:example:grant:custom-delegation".equals(
                registration.getAuthorizationGrantType().getValue())) {
            return null;
        }

        // 1. Kiểm tra authorized client hiện tại và expiry.
        // 2. Lấy subject/assertion từ nguồn tin cậy.
        // 3. Gọi token endpoint theo contract của AS.
        // 4. Parse token response.
        // 5. Trả OAuth2AuthorizedClient đúng registration/principal.
        // Không tạo token giả và không tự đưa raw token vào log.

        throw new UnsupportedOperationException(
                "Implement using the AS contract and token client");
    }
}
~~~

Đây là **phác thảo cấu trúc**, không phải một implementation đủ để chạy production. Các import và dependency cần bổ sung theo dự án thật.

### 17.4. Không lạm dụng `ClientRegistration.authorizationGrantType`

Bạn có thể tạo:

~~~java
AuthorizationGrantType customGrant =
        new AuthorizationGrantType(
                "urn:example:grant:custom-delegation");
~~~

Nhưng object này chỉ chứa **tên grant**. Nó không định nghĩa cách gọi token endpoint, payload, client auth hay semantics của grant.

## 18. Nâng cấp từ 6.5 sang 7.0: tình huống password grant

### 18.1. Mã cũ

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .password()
                .refreshToken()
                .build();
~~~

Trong dòng 6.5, `password()` đã deprecated. Trong 7.0, method bị loại bỏ nên code dựa vào nó không còn biên dịch.

### 18.2. Không sửa bằng cách cố truyền username/password theo đường khác

Đổi từ builder `password()` sang tự POST:

~~~text
grant_type=password
username=...
password=...
~~~

không phải giải pháp migration bảo mật đúng. OAuth Security Best Current Practice không cho phép Resource Owner Password Credentials grant trong thiết kế hiện đại.

### 18.3. Hướng thay thế

Tùy use case:

| Use case | Hướng thay thế có thể phù hợp |
|---|---|
| User đăng nhập web | Authorization Code + PKCE/OIDC Login |
| Native/public client | Authorization Code + PKCE |
| Service-to-service | Client Credentials nếu quyền thuộc service |
| Đổi/ủy quyền token giữa services | Token Exchange nếu AS hỗ trợ |
| Thiết bị hạn chế input | Device Authorization flow nếu stack/AS hỗ trợ và được tích hợp |
| Yêu cầu đăng nhập headless bằng username/password | Thiết kế lại flow và ranh giới danh tính; không giả lập ROPC |

Không có một grant thay thế trực tiếp cho mọi trường hợp. Cần đánh giá vai trò **End-User** và **client/service** trước khi chọn.

### 18.4. Dấu hiệu cần tìm khi migration

- `OAuth2AuthorizedClientProviderBuilder.password()`.
- `ReactiveOAuth2AuthorizedClientProviderBuilder.password()`.
- `PasswordOAuth2AuthorizedClientProvider`.
- `PasswordReactiveOAuth2AuthorizedClientProvider`.
- Token response client/cấu hình cũ cho password grant.
- Properties `authorization-grant-type: password`.
- Code thu thập username/password của user để đổi token.

Không dừng ở lỗi biên dịch đầu tiên: có thể còn config/runtime paths liên quan password grant.

## 19. Spring Security 7.0: builder còn gì?

Trong Javadoc 7.0, `OAuth2AuthorizedClientProviderBuilder` công bố những method grant chính:

~~~java
.authorizationCode()
.refreshToken()
.clientCredentials()
.provider(extensionProvider)
~~~

Không có `password()`.

Reactive counterpart cũng có:

~~~java
ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .provider(reactiveExtensionProvider)
        .build();
~~~

**Không nhầm “builder chỉ có ba method chuyên dụng” thành “framework không hỗ trợ extension grant”.** Hook `provider(...)` cho phép tích hợp provider JWT Bearer, Token Exchange hoặc custom grant phù hợp.

### 19.1. Extension không mặc định được bật

Dù class `TokenExchangeOAuth2AuthorizedClientProvider` có trên classpath, manager không nhất thiết tự sử dụng nó. Hãy xác định provider bean hoặc composite provider đã được wiring đúng.

### 19.2. Không sao chép API 7.x về 5.x

Một token response client mới dựa trên `RestClient` có thể không có trong dòng 5.x. Cần kiểm tra Javadoc của đúng phiên bản thay vì sao chép class name từ tài liệu mới.

### 19.3. Cẩn trọng với các thay đổi API khác

Chuyển major version có thể thay đổi package, Java baseline, component model, DSL hoặc deprecated APIs ngoài grant. Hãy dùng migration guide phù hợp và một dependency stack được hỗ trợ.

## 20. Ví dụ kiểm tra “có class” ở artifact thực tế

Khi cần xác minh code thực sự biên dịch:

### 20.1. Import class vào project

Ví dụ với Token Exchange:

~~~java
import org.springframework.security.oauth2.client
        .TokenExchangeOAuth2AuthorizedClientProvider;
~~~

Nếu class không tồn tại ở version đang resolve, IDE/compiler sẽ báo lỗi.

Điều đó đáng tin hơn việc đọc một trang Javadoc phiên bản khác. Nhưng compile thành công vẫn không chứng minh provider đã được dùng trong manager.

### 20.2. Kiểm tra method qua Javadoc và IDE

Ví dụ có thể xem:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
        .provider(new TokenExchangeOAuth2AuthorizedClientProvider())
        .build();
~~~

và đối chiếu method signature `provider(OAuth2AuthorizedClientProvider)`.

Không dùng reflection runtime như một cơ chế chính để “thử xem class có không” trong business logic. Grant hỗ trợ là quyết định kiến trúc nên được khai báo, kiểm thử và kiểm soát dependency.

### 20.3. Xem source jar

Khi Javadoc chưa giải thích behavior, có thể đọc source của đúng version để hiểu:

- Grant value được so sánh thế nào?
- Provider trả `null` khi nào?
- Lấy assertion/subject token từ đâu?
- Khi access token hết hạn thì reauthorize ra sao?
- Provider có sửa refresh token không?
- Token endpoint request được xây thế nào?

Đừng dựa vào source ở nhánh main của framework nếu runtime đang dùng bản phát hành cũ.

## 21. Bằng chứng hoạt động ở runtime

Một grant thực sự dùng được cần kiểm tra ở môi trường test với AS tương ứng.

### 21.1. Test cấp token lần đầu

Với client được phép dùng grant:

1. Gọi manager bằng registration và principal thích hợp.
2. Provider tìm đúng grant.
3. AS chấp nhận client authentication.
4. Token request có đúng `grant_type`, assertion/subject token và parameters.
5. AS trả token response hợp lệ.
6. Manager lưu `OAuth2AuthorizedClient`.
7. API đích chấp nhận access token cho audience/scope tương ứng.

### 21.2. Test tình huống không được bật

Ví dụ:

~~~text
Registration:
  grantType = token-exchange

Manager:
  chỉ có authorizationCode + refreshToken + clientCredentials
~~~

Manager có thể không tạo authorized client mới cho grant này. Điều đó là **lỗi wiring provider**, không có nghĩa AS không hỗ trợ Token Exchange.

### 21.3. Test AS từ chối grant

Nếu token endpoint trả `unsupported_grant_type`:

- Xem grant value đúng chưa.
- AS có hỗ trợ extension không?
- Client endpoint đúng chưa?
- Feature/tenant policy đã bật chưa?
- Token request có đúng content type/parameters không?

### 21.4. Test quyền của token được cấp

Token Exchange thành công không chứng minh token mới có quyền sử dụng ở mọi API. Resource Server có thể trả 401/403 vì audience, issuer hoặc scope không phù hợp.

Không “chữa” bằng cách gửi token tới API khác cho đến khi nơi nào chấp nhận. Cần AS/API contract rõ ràng.

## 22. Mẫu ghi quyết định tương thích trong dự án

Có thể lưu một bảng quyết định trong tài liệu kiến trúc:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Client | `payments-exchange` |
| Spring Boot | Version dự án thực tế |
| Spring Security | `6.5.x` (ví dụ) |
| Runtime stack | Servlet |
| Grant | `urn:ietf:params:oauth:grant-type:token-exchange` |
| Provider implementation | `TokenExchangeOAuth2AuthorizedClientProvider` |
| Mốc API | Since 6.3 |
| Wiring | Bean provider hoặc manager composite |
| Subject token source | JwtAuthenticationToken đã xác minh |
| Client authentication | Theo cấu hình AS |
| Target Resource Server | Payments API |
| Audience/scope | Theo hợp đồng Payments API |
| Integration test | Có, dùng AS test tenant |
| Secret/token logging | Bị vô hiệu hóa/redact |

Bảng này giúp những người nâng version hiểu vì sao grant hoạt động, thay vì chỉ lưu một property YAML.

## 23. Các trường hợp dễ nhầm

### 23.1. “YAML chấp nhận grant URN, vậy Spring hỗ trợ”

**Sai.** Cần provider và token response client phù hợp, được wiring vào manager, cộng với AS cho phép.

### 23.2. “Class có trong Javadoc latest, chắc chắn có trong project”

**Sai.** Javadoc latest có thể là 7.x còn project dùng 6.1. So sánh dependency resolved version.

### 23.3. “Provider có trong classpath là tự động bật”

**Sai hoặc thiếu điều kiện.** Cần xem component-based configuration, bean collection và manager thực tế. Với custom manager, có thể cần set composite provider rõ ràng.

### 23.4. “JWT Bearer grant giống `private_key_jwt`”

**Sai.** Một bên là authorization grant, một bên là client authentication.

### 23.5. “OIDC là grant mới”

**Sai.** OIDC thường kết hợp Authorization Code grant và ID token, không phải `grant_type=oidc`.

### 23.6. “PKCE là grant”

**Sai.** PKCE bảo vệ Authorization Code flow.

### 23.7. “Có `refreshToken()` nghĩa AS luôn cấp refresh token”

**Sai.** AS quyết định có cấp refresh token hay không.

### 23.8. “Spring Security 6.5 còn `password()` nên nên dùng”

**Sai.** API đã deprecated; dòng 7.0 loại bỏ hỗ trợ. Không tạo tích hợp ROPC mới.

### 23.9. “Token Exchange có trong 6.2 vì provider bean auto pickup từ 6.2”

**Sai.** 6.2 là mốc cải thiện wiring; provider tích hợp Token Exchange có `Since: 6.3`.

### 23.10. “JWT Bearer từ 6.2 vì cách cấu hình bean mới”

**Sai.** `JwtBearerOAuth2AuthorizedClientProvider` có từ 5.5; 6.2 là cải thiện cách tích hợp bean.

### 23.11. “Có JWT access token là dùng được JWT Bearer grant”

**Không tự động.** JWT assertion dùng làm grant phải đáp ứng contract AS và mục đích phù hợp. Không lấy JWT bất kỳ để đổi token.

### 23.12. “Authorization Server hỗ trợ grant thì Spring tự xử lý”

**Sai.** Client phải có implementation và cấu hình thích hợp.

## 24. Bảo mật khi dùng grant mở rộng

### 24.1. Không log token và assertion

Những dữ liệu cần bảo vệ:

~~~text
access_token
refresh_token
id_token
subject_token
actor_token
jwt_assertion
client_secret
private_key
authorization_code
code_verifier
session_cookie
~~~

Chỉ log registration ID, grant type, correlation ID, trạng thái cấp token và mã lỗi đã chuẩn hóa khi được phép.

### 24.2. Least privilege

Token Exchange không được dùng để tăng quyền ngoài policy AS. Token mới cần audience/scope cho Resource Server cụ thể. Client Credentials token là quyền service, không phải quyền End-User.

### 24.3. Không tự chấp nhận assertion do browser cung cấp

Nếu backend nhận một JWT từ user và tự đổi lấy token với client secret của tổ chức, có nguy cơ confused deputy. Phải xác minh nguồn token, issuer, audience, subject, expiry và quyền exchange trước khi gọi AS.

### 24.4. Xác định credential owner

Một `OAuth2AuthorizedClient` có principalName và registration. Với multi-issuer/tenant, không dùng email hoặc `sub` đơn lẻ làm khóa toàn cục nếu có thể trùng.

### 24.5. Token endpoint và Resource Server là hai nơi khác nhau

Không gửi refresh token hoặc client secret đến Resource Server. Không dùng ID token thay access token. Token response client chỉ gửi grant/assertion tới AS token endpoint đã được xác minh.

### 24.6. Không tự làm fallback sang grant kém bảo mật

Khi AS không cho Token Exchange hoặc Authorization Code, không fallback sang `password` hoặc tự thu thập username/password của user để tránh ràng buộc bảo mật.

## 25. Bài tập tình huống

### Tình huống A: ứng dụng Spring Security 6.1 muốn Token Exchange

Bạn tìm thấy bài blog dùng:

~~~java
new TokenExchangeOAuth2AuthorizedClientProvider();
~~~

**Phân tích:** provider tích hợp này có `Since: 6.3`, nên không giả định 6.1 có class đó. Cần nâng phiên bản có kiểm soát hoặc tự triển khai extension nếu không thể nâng, với AS contract rõ ràng.

### Tình huống B: Spring Security 5.8 muốn JWT Bearer

**Phân tích:** `JwtBearerOAuth2AuthorizedClientProvider` có từ 5.5. Có thể xem extension provider API và cấu hình manager đúng version. Không dùng ví dụ `RestClientJwtBearerTokenResponseClient` của 7.x nếu class đó chưa tồn tại ở bản đang dùng.

### Tình huống C: Spring Security 6.5 có code `password()`

**Phân tích:** API có thể còn biên dịch nhưng deprecated. Cần lên kế hoạch migration trước Spring Security 7.

### Tình huống D: Spring Security 7.0 build lỗi `password()`

**Phân tích:** Hỗ trợ password grant đã bị loại bỏ. Không tạo workaround ROPC; thiết kế lại bằng Authorization Code + PKCE/OIDC hoặc grant service phù hợp.

### Tình huống E: thêm `authorization-grant-type: token-exchange` nhưng manager không trả token

**Phân tích:** Có thể grant value không đúng URN, provider chưa được bật, thiếu subject token hoặc AS không cho phép. Kiểm tra từng lớp.

### Tình huống F: Spring Security 6.2 có bean JWT Bearer nhưng manager custom không dùng

**Phân tích:** Custom manager có thể ghi đè provider chain. Phải kiểm tra logic cấu hình thực sự, không chỉ sự tồn tại của bean.

### Tình huống G: AS trả `unauthorized_client`

**Phân tích:** Đây thường là policy/client registration của AS, không tự chứng minh thư viện thiếu grant provider.

### Tình huống H: token exchange trả access token nhưng API trả 403

**Phân tích:** Grant có thể đã hoạt động; token mới thiếu scope/authority/ownership. Cần kiểm tra API authorization, không chỉ manager.

### Tình huống I: WebFlux dùng Servlet Token Exchange provider

**Phân tích:** Chọn reactive counterpart, manager reactive và token response client reactive; đừng bọc blocking provider bằng Mono để coi như non-blocking.

### Tình huống J: metadata AS không liệt kê grant custom

**Phân tích:** Metadata có thể không đầy đủ cho extension đặc thù; cần tài liệu AS, cấu hình client và integration test thực tế. Không tự khẳng định grant không tồn tại chỉ dựa vào một trường metadata vắng mặt.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Một grant có trong RFC có nghĩa Spring Security tự hỗ trợ không?

**Trả lời:** Không. Cần implementation/provider ở version dùng, cấu hình manager, AS support và integration test.

**Câu 2.** Một chuỗi `authorization-grant-type` được Spring Boot bind thành công có chứng minh token endpoint gọi được không?

**Trả lời:** Không. Nó chỉ chứng minh cấu hình có thể được biểu diễn; chưa có bằng chứng provider được bật hoặc AS chấp nhận.

**Câu 3.** Làm sao biết dự án thực tế đang dùng Spring Security version nào?

**Trả lời:** Xem resolved dependency bằng Maven dependency tree hoặc Gradle dependencyInsight, kết hợp effective POM/BOM khi cần.

**Câu 4.** `OAuth2AuthorizedClientProviderBuilder` có từ dòng nào?

**Trả lời:** Javadoc nêu `Since: 5.2`.

**Câu 5.** `JwtBearerOAuth2AuthorizedClientProvider` có từ dòng nào?

**Trả lời:** `Since: 5.5`.

**Câu 6.** `TokenExchangeOAuth2AuthorizedClientProvider` có từ dòng nào?

**Trả lời:** `Since: 6.3`.

**Câu 7.** Spring Security 6.2 thay đổi gì đáng chú ý với extension provider?

**Trả lời:** Có cơ chế component-based thuận tiện hơn để tích hợp provider bean vào manager mặc định theo điều kiện cấu hình.

**Câu 8.** Spring Security 7.0 còn `password()` trong provider builder không?

**Trả lời:** Không. Password grant support đã bị loại bỏ.

**Câu 9.** `private_key_jwt` có phải JWT Bearer authorization grant?

**Trả lời:** Không. Đó là client authentication; JWT Bearer grant sử dụng JWT assertion như grant để xin token.

**Câu 10.** PKCE có phải một grant?

**Trả lời:** Không. PKCE bảo vệ Authorization Code flow.

**Câu 11.** OIDC Login có phải grant `oidc`?

**Trả lời:** Không. Thông thường OIDC dùng Authorization Code với `openid` và ID token.

**Câu 12.** Token Exchange provider có trên classpath đã đủ chưa?

**Trả lời:** Chưa. Cần wiring provider, subject token/resolver, AS policy, token response và API validation.

**Câu 13.** Có thể dùng Servlet provider trong WebFlux qua `Mono.fromCallable(...)` để giải quyết tương thích không?

**Trả lời:** Không nên. Dùng reactive provider/manager và token response client tương ứng.

**Câu 14.** AS trả `invalid_client` có nghĩa Spring Security không hỗ trợ grant?

**Trả lời:** Không. Có thể client authentication sai; cần chẩn đoán đúng tầng.

**Câu 15.** AS trả `unsupported_grant_type` cần kiểm tra gì?

**Trả lời:** Grant value, endpoint, AS feature/client policy, request format và version provider.

**Câu 16.** JWT assertion có thể lấy từ bất kỳ ID token nào không?

**Trả lời:** Không. AS phải cho phép JWT được dùng làm assertion, và client phải xác minh/ràng buộc nguồn theo contract.

**Câu 17.** Nâng Spring Security có đồng nghĩa mọi API của Spring Boot tương thích ngay không?

**Trả lời:** Không. Cần kiểm tra BOM, dependency, Java baseline, migration guide và test.

**Câu 18.** Test nào mới chứng minh end-to-end grant hoạt động?

**Trả lời:** Integration test với AS test tenant, provider/manager phù hợp, token endpoint response và Resource Server kiểm tra audience/scope.

## Ghi nhớ

- **“Spring Security hỗ trợ grant” phải được hiểu theo phiên bản và nhiều lớp:** protocol, AS policy, library API/provider và runtime wiring.
- **Xác minh chính xác `spring-security-oauth2-client` version** bằng resolved dependencies trước khi tra Javadoc và code examples.
- **Ba grant thông dụng hiện đại:** `authorization_code`, `refresh_token` và `client_credentials`; không nhầm OIDC/PKCE thành grant mới.
- **JWT Bearer provider có từ 5.5; Token Exchange provider có từ 6.3.** Đây là extension grants, thường phải được bật và cung cấp assertion/subject token phù hợp.
- **Từ 6.2 có cơ chế tích hợp provider bean thuận tiện hơn**, nhưng không tự áp dụng cho mọi custom manager.
- **`password` bị deprecated từ 5.8 và loại bỏ ở 7.0**; không triển khai ROPC mới hoặc tự viết workaround nhận password của End-User.
- **Servlet và Reactive có manager/provider riêng**. Không copy class từ stack này sang stack kia mà không kiểm tra.
- **`ClientRegistration.authorizationGrantType` chấp nhận một giá trị không đồng nghĩa grant chạy được.** Cần provider, response client, context và AS grant permission.
- **Javadoc versioned, `Since`, `Deprecated`, migration notes và integration test** là căn cứ xác định khả năng tương thích đáng tin cậy.
- **Token được cấp vẫn phải đúng audience, scope, principal và Resource Server**, không được log assertion/token hoặc dựa vào extension grant để tự tăng quyền.
