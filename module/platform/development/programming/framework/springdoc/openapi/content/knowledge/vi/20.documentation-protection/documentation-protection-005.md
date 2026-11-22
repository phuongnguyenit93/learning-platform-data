# Tài liệu công khai so với tài liệu chỉ dùng trong mạng nội bộ

Đặc tả OpenAPI và Swagger UI giúp developer hiểu cách gọi API, nhưng bản thân tài liệu cũng là một bề mặt thông tin cần quản lý. Một tài liệu công khai có thể giúp đối tác tích hợp nhanh; tài liệu nội bộ có thể chứa endpoint quản trị, luồng vận hành, hostname riêng, schema hoặc quy ước chỉ dành cho hệ thống trong công ty.

Với Spring Boot và springdoc-openapi, cần phân biệt ba lớp: **API nghiệp vụ**, **tài liệu OpenAPI JSON/YAML**, và **giao diện Swagger UI**. Bảo vệ Swagger UI không tự bảo vệ file đặc tả; ẩn file đặc tả không bảo vệ endpoint nghiệp vụ. Quyền truy cập tài liệu cần được thiết kế riêng, đồng thời phản ánh đúng ranh giới mạng và chính sách xác thực của môi trường triển khai.

## 1. Công khai tài liệu hay chỉ cho phép truy cập nội bộ?

Tài liệu API có thể được chia theo đối tượng sử dụng:

| Loại tài liệu | Đối tượng | Nội dung thường phù hợp |
|---|---|---|
| Public API docs | Developer bên ngoài, đối tác, khách hàng | Endpoint công khai, schema request/response, authentication flow, giới hạn, lỗi và ví dụ đã được duyệt. |
| Partner docs | Đối tác được cấp quyền | API dành riêng cho hợp đồng tích hợp, sandbox, scope, quota và hướng dẫn onboarding. |
| Internal docs | Nhân viên, service nội bộ, đội vận hành | Endpoint nội bộ, API quản trị, server private, luồng vận hành và quy ước liên service. |
| Restricted/admin docs | Nhóm quản trị hoặc security | Operation nhạy cảm, công cụ hỗ trợ, thao tác vận hành đặc quyền và endpoint chỉ dành cho quản trị. |

Không phải mọi API đều cần tài liệu công khai. Việc quyết định nên dựa trên đối tượng cần tích hợp và mức độ thông tin mà tài liệu tiết lộ, không chỉ dựa vào việc endpoint có yêu cầu đăng nhập hay không.

### 1.1. Tài liệu công khai mang lại điều gì?

Public docs phù hợp khi tổ chức muốn developer bên ngoài tự tìm hiểu và tích hợp API. Tài liệu công khai thường cần:

- Base URL và môi trường sử dụng rõ ràng.
- Authentication scheme và cách lấy credential.
- Request/response schema, status code và error format.
- Rate limit, pagination, versioning và deprecation policy.
- Ví dụ không chứa dữ liệu thật hoặc bí mật.
- Hướng dẫn liên hệ hỗ trợ và điều khoản sử dụng.

Một API vẫn có thể yêu cầu token dù tài liệu của nó công khai. **Public documentation không có nghĩa là public API không cần authentication.** Client đọc được hợp đồng trước, sau đó vẫn phải xác thực khi gọi endpoint được bảo vệ.

### 1.2. Tài liệu nội bộ chứa những thông tin nào?

Internal docs có thể mô tả:

- Endpoint chỉ được gọi từ service hoặc mạng private.
- Hostname, port, route hoặc server URL không được công bố ra Internet.
- API quản trị, debug, support hoặc thao tác vận hành.
- Chi tiết scope, role, tenant và quy trình cấp quyền nội bộ.
- Schema hoặc field chỉ phục vụ tích hợp giữa các service.
- Ví dụ chứa mã định danh, dữ liệu nghiệp vụ hoặc quy ước nội bộ.

Không mặc định rằng tài liệu nội bộ luôn an toàn để chia sẻ trong toàn công ty. Một số operation có thể chỉ phù hợp với nhóm vận hành hoặc security. Hãy phân loại theo đối tượng và quyền thực tế cần có.

## 2. Ba bề mặt cần bảo vệ riêng

Springdoc thường cung cấp các URL sau (có thể thay đổi theo cấu hình):

| Bề mặt | URL mặc định thường gặp | Nội dung |
|---|---|---|
| OpenAPI JSON | /v3/api-docs | Đặc tả OpenAPI của tài liệu mặc định. |
| OpenAPI theo group | /v3/api-docs/{group} | Đặc tả của một GroupedOpenApi. |
| OpenAPI YAML | /v3/api-docs.yaml (nếu bật endpoint YAML) | Cùng hợp đồng OpenAPI ở định dạng YAML. |
| Swagger UI | /swagger-ui.html và /swagger-ui/** | Trang HTML, JavaScript, CSS và tài nguyên giao diện. |
| Swagger UI configuration | /v3/api-docs/swagger-config | Cấu hình URL tài liệu mà giao diện sẽ tải. |

Ba điểm cần kiểm tra:

1. **Swagger UI** là giao diện để xem và thử API. Nếu trang HTML bị bảo vệ nhưng JSON vẫn mở công khai, người dùng vẫn có thể tải trực tiếp đặc tả.
2. **OpenAPI JSON/YAML** chứa toàn bộ thông tin hợp đồng được xuất. Bảo vệ giao diện mà quên endpoint JSON không tạo ra ranh giới truy cập thực sự.
3. **API nghiệp vụ** vẫn cần security policy riêng. Tắt hoặc khóa tài liệu không làm endpoint nghiệp vụ tự động an toàn hơn.

Sơ đồ luồng truy cập:

~~~mermaid
flowchart TD
    D[Developer] --> U[Swagger UI]
    D --> J[OpenAPI JSON/YAML]
    U --> J
    D --> A[Business API]
    J --> I[Thông tin hợp đồng]
    A --> S[Spring Security / API Gateway]
    I --> P{Policy tài liệu}
    P -->|Public| PUB[Internet / Developer portal]
    P -->|Internal| VPN[Private ingress / VPN / SSO]
    P -->|Restricted| ADM[Nhóm được cấp quyền]
~~~

Swagger UI thường tải JSON từ một URL riêng. Do đó, nếu UI và JSON có policy khác nhau, phải kiểm tra request tải đặc tả trong trình duyệt, không chỉ kiểm tra trang UI ban đầu.

## 3. Phân nhóm tài liệu bằng GroupedOpenApi

Springdoc cho phép chia operation thành các tài liệu riêng. Ví dụ, nhóm public và internal:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**", "/api/admin/**")
                .build();
    }
}
~~~

Với cấu hình này, springdoc có thể xuất các tài liệu riêng tại:

- /v3/api-docs/public
- /v3/api-docs/internal

pathsToMatch chọn operation theo path để đưa vào từng tài liệu. Có thể kết hợp pathsToExclude, packagesToScan, packagesToExclude hoặc các predicate phù hợp với phiên bản springdoc.

### 3.1. Group không phải cơ chế phân quyền

GroupedOpenApi chỉ chia nội dung đặc tả. Nó không tự đặt authentication, không giới hạn người tải JSON và không tạo network boundary. Nếu /v3/api-docs/internal vẫn được phép truy cập ẩn danh, bất kỳ ai biết URL đều có thể lấy tài liệu nội bộ.

Tương tự, ẩn một operation khỏi public group không bảo vệ endpoint nghiệp vụ. Endpoint đó vẫn phải được Spring Security hoặc gateway kiểm soát.

### 3.2. Chọn nội dung public theo allow-list

Với tài liệu công khai, nên chọn các path đã được duyệt:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch(
                    "/api/catalog/**",
                    "/api/orders/**"
            )
            .pathsToExclude(
                    "/api/catalog/internal/**",
                    "/api/orders/*/admin/**"
            )
            .build();
}
~~~

Allow-list giúp tránh vô tình công bố endpoint mới chỉ vì một controller được thêm vào package chung. Sau mỗi thay đổi path, kiểm tra public spec để chắc rằng operation được đưa vào đúng nhóm.

Không dựa duy nhất vào tên path như /internal hoặc tag Internal để bảo vệ dữ liệu. Chúng chỉ là tiêu chí chọn tài liệu; authorization phải được cấu hình ở lớp truy cập.

## 4. Bảo vệ OpenAPI và Swagger UI bằng Spring Security

Nếu toàn bộ tài liệu chỉ dành cho nhân viên, có thể yêu cầu authority riêng khi truy cập các URL tài liệu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                "/v3/api-docs",
                                "/v3/api-docs/**",
                                "/v3/api-docs.yaml",
                                "/swagger-ui.html",
                                "/swagger-ui/**"
                        ).hasAuthority("DOCS_READ")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Trong ví dụ, người dùng cần authority DOCS_READ mới tải được OpenAPI JSON, Swagger UI và Swagger UI configuration. HTTP Basic chỉ là ví dụ dễ nhìn thấy trong request; production có thể dùng SSO, OAuth2 Login, Bearer token hoặc cơ chế xác thực tổ chức đang sử dụng.

Hãy kiểm tra thứ tự matcher. Rule cụ thể phải đứng trước rule tổng quát để không bị một permitAll() hoặc matcher rộng hơn mở quyền ngoài ý muốn.

### 4.1. Public spec và internal spec trong cùng ứng dụng

Nếu muốn public group được tải ẩn danh nhưng internal group cần quyền riêng, đặt matcher public cụ thể trước matcher bảo vệ phần còn lại:

~~~java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            "/v3/api-docs/public",
                            "/v3/api-docs/public/**"
                    ).permitAll()
                    .requestMatchers(
                            "/v3/api-docs",
                            "/v3/api-docs/**",
                            "/v3/api-docs.yaml",
                            "/swagger-ui.html",
                            "/swagger-ui/**"
                    ).hasAuthority("DOCS_READ")
                    .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Với cấu hình này, public JSON có thể được tải ẩn danh; các tài liệu JSON khác và Swagger UI yêu cầu DOCS_READ. Swagger UI được bảo vệ vì cấu hình giao diện có thể liệt kê cả group nội bộ. Nếu muốn có giao diện Swagger UI công khai riêng, hãy triển khai một UI/config chỉ trỏ tới public spec, hoặc phục vụ UI public từ portal riêng. Không mở chung UI có danh sách internal group rồi kỳ vọng group tự được bảo vệ.

Các URL thực tế có thể khác khi đổi springdoc.api-docs.path, context path, servlet path hoặc Swagger UI path. Điều chỉnh matcher theo URL sau khi cấu hình và kiểm tra cả /v3/api-docs/swagger-config cùng endpoint YAML nếu ứng dụng bật endpoint đó. Nếu cấu hình public và internal group dùng chung một URL YAML với query parameter hoặc content negotiation, cần kiểm tra cách gateway/Spring Security phân biệt audience; tách host hoặc deployment sẽ rõ ràng hơn khi không thể phân quyền theo path.

### 4.2. Tách security chain khi cần policy riêng

Ứng dụng lớn có thể dùng nhiều SecurityFilterChain với @Order và securityMatcher để áp dụng policy khác nhau cho docs và business API. Cách này hữu ích khi tài liệu dùng SSO hoặc Basic riêng, còn API nghiệp vụ dùng Bearer JWT.

Khi có nhiều chain:

- Chain có matcher hẹp cho docs phải có thứ tự ưu tiên cao hơn chain chung.
- Chain docs phải bao phủ JSON, group JSON, swagger config, HTML và asset UI cần bảo vệ.
- Chain business API vẫn phải bảo vệ các endpoint nghiệp vụ.
- Không để một URL tài liệu rơi vào chain không có authorization rule.

Không cần tạo nhiều chain chỉ để đổi một matcher. Dùng cấu hình đơn giản nếu cùng một authentication mechanism và authority có thể áp dụng cho toàn bộ docs.

## 5. Kết hợp ranh giới mạng với xác thực

Đối với tài liệu nội bộ hoặc restricted, có thể đặt docs sau một hoặc nhiều lớp:

| Lớp | Ví dụ | Mục đích |
|---|---|---|
| Private network | Private subnet, internal load balancer, private DNS | Không định tuyến trực tiếp từ Internet. |
| Remote access | VPN hoặc Zero Trust access gateway | Xác minh thiết bị/người dùng trước khi vào mạng nội bộ. |
| Identity | SSO, OAuth2/OIDC, mTLS | Xác định danh tính người hoặc service. |
| Authorization | Role/authority như DOCS_READ, DOCS_ADMIN | Giới hạn nhóm nào được đọc tài liệu. |
| Application | Spring Security hoặc gateway policy | Bảo vệ chính URL docs và UI. |
| Audit | Access log, identity, timestamp, request ID | Truy vết ai đã tải tài liệu và khi nào. |

Network allow-list hoặc VPN có thể giảm khả năng tiếp cận từ bên ngoài nhưng không thay thế authorization. Một máy đã vào VPN vẫn có thể thuộc nhóm không được xem tài liệu admin. Với tài liệu nhạy cảm, kết hợp private ingress với xác thực và quyền riêng.

### 5.1. Tách hostname hoặc deployment

Một thiết kế rõ ràng là dùng host riêng:

- developer.example.com: portal và public API docs.
- api-docs.intra.example: internal docs sau private ingress/SSO.
- admin-docs.intra.example: restricted docs cho nhóm vận hành.

Host riêng giúp cấu hình DNS, TLS, gateway, logging và policy độc lập. Có thể triển khai cùng ứng dụng hoặc tách thành portal đọc artifact OpenAPI đã xuất. Nếu dùng chung application, vẫn phải bảo vệ path tương ứng ở Spring Security hoặc gateway.

Không xem hostname khó đoán là biện pháp bảo mật. Quyền truy cập phải được kiểm tra ở network/gateway và ứng dụng.

## 6. Những thông tin cần rà soát trước khi công khai

Trước khi xuất public spec, review nội dung như một artifact có thể được tải, lưu cache và đưa vào source control:

- **Server URL**: không để lộ hostname, IP, port hoặc route private.
- **Operation**: không đưa endpoint admin, debug, health nội bộ hoặc thao tác hỗ trợ vào public group.
- **Schema**: loại bỏ field nội bộ, tên bảng, cấu trúc persistence hoặc thuộc tính không dành cho client.
- **Example**: không dùng access token, API key, email, số điện thoại hoặc dữ liệu khách hàng thật.
- **Description**: loại bỏ ghi chú triển khai, tên service nội bộ, chi tiết hạ tầng và thông tin chưa được duyệt.
- **Security**: mô tả đúng authentication flow, scope và quyền mà client bên ngoài có thể dùng.
- **Error response**: không công bố stack trace, exception class, SQL hoặc thông tin debug.
- **Extension**: rà soát vendor extension x-* vì chúng có thể chứa owner, ticket, hostname hoặc metadata nội bộ.
- **Links và callback**: xác nhận URL không dẫn tới hệ thống private hoặc môi trường test.
- **Version/deprecation**: chỉ công bố version và lịch ngừng hỗ trợ đã được phê duyệt.

Một tài liệu không chứa dữ liệu bí mật vẫn có thể tiết lộ cấu trúc hệ thống, chức năng quản trị hoặc các điểm tích hợp. Cần đánh giá theo threat model và đối tượng nhận tài liệu.

## 7. Cấu hình môi trường production

Không phải hệ thống nào cũng cần phục vụ Swagger UI trực tiếp trong production. Có một số lựa chọn:

| Lựa chọn | Cách triển khai | Phù hợp khi |
|---|---|---|
| Tắt UI, giữ OpenAPI JSON có bảo vệ | springdoc.swagger-ui.enabled=false, giữ springdoc.api-docs.enabled=true và áp dụng security | Internal portal hoặc công cụ cần đọc spec nhưng không cần UI đi kèm service. |
| Tắt cả docs runtime | Tắt springdoc.api-docs.enabled và springdoc.swagger-ui.enabled | Tài liệu được build/export ở pipeline riêng hoặc production không cần endpoint docs. |
| Giữ UI và JSON nội bộ | Bật cả hai, đặt sau SSO/VPN/Spring Security | Đội nội bộ cần thử API từ môi trường production. |
| Phát hành public artifact tĩnh | Export OpenAPI đã review rồi publish lên developer portal | Public docs cần versioning, approval và cache độc lập với ứng dụng. |

Ví dụ tắt docs runtime trong profile production:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Hai cờ này tắt endpoint tài liệu do springdoc cung cấp; chúng không tắt hoặc bảo vệ API nghiệp vụ. Nếu cần internal docs ở production, không bật cấu hình tắt này cho profile đó; thay vào đó giữ docs hoạt động và khóa truy cập đúng cách.

### 7.1. Không nhầm Actuator với tài liệu OpenAPI

Spring Boot Actuator có các endpoint quản trị/quan sát như health, info, metrics, env hoặc mappings tùy cấu hình. Đây là bề mặt riêng với /v3/api-docs và Swagger UI. Không mở toàn bộ Actuator chỉ vì muốn health check công khai.

Nếu bật tích hợp springdoc để đưa Actuator endpoint vào tài liệu, hãy phân biệt:

- Việc operation Actuator xuất hiện trong OpenAPI.
- Việc endpoint Actuator có thể truy cập ở runtime.
- Việc tài liệu mô tả endpoint đó được phép tải bởi ai.

Mỗi lớp cần policy riêng. Các endpoint nhạy cảm như env, configprops, beans, mappings hoặc shutdown (nếu có) cần được đánh giá và bảo vệ theo cấu hình Actuator, không chỉ bằng việc ẩn chúng khỏi Swagger UI.

## 8. Xuất và phát hành OpenAPI artifact

Với public docs, có thể tách thời điểm tạo tài liệu khỏi thời điểm service đang chạy:

1. Build ứng dụng hoặc khởi động môi trường kiểm thử có cấu hình tương ứng.
2. Lấy OpenAPI JSON từ /v3/api-docs hoặc từng group.
3. Validate schema và kiểm tra $ref, security, server URL, examples.
4. Review public/internal classification và thông tin nhạy cảm.
5. Lưu artifact theo version, ví dụ openapi-public-1.4.0.json.
6. Publish lên developer portal hoặc static hosting đã cấu hình.

Cách này giúp public docs được duyệt trước khi phát hành và không cần mở endpoint tài liệu trên service production. Với internal docs, có thể lưu artifact trong registry/repository nội bộ có access control.

### 8.1. Quản lý phiên bản artifact

Đặt version rõ ràng và lưu lịch sử thay đổi:

- Gắn version API trong info.version hoặc quy ước version artifact.
- Không ghi đè artifact cũ nếu client còn dùng.
- Lưu commit/build number tạo ra spec.
- Review breaking change trước khi publish.
- Đặt ngày deprecation và ngày sunset nếu API cũ sẽ ngừng.
- Giữ public và internal artifact ở repository hoặc permission scope phù hợp.

Artifact OpenAPI có thể được chia sẻ độc lập với service. Vì vậy, quyền tải artifact và quyền truy cập endpoint API là hai quyết định riêng.

## 9. Cache, indexing và URL tài liệu

Tài liệu public có thể được cache tại CDN hoặc static hosting. Điều này giúp tải nhanh nhưng cần invalidation khi phát hành version mới. Tài liệu nội bộ thường không nên được cache bởi shared proxy nếu cache key không tách biệt theo danh tính.

Với tài liệu nhạy cảm:

- Cân nhắc Cache-Control: private, no-store cho response docs nếu không muốn lưu ở browser/shared cache.
- Không đưa URL docs nội bộ vào sitemap public.
- Có thể dùng X-Robots-Tag: noindex, nofollow để hướng dẫn crawler không index; đây không phải biện pháp authorization.
- Không dựa vào robots.txt, URL khó đoán hoặc trang UI bị ẩn để bảo vệ JSON.
- Kiểm tra redirect và CDN origin để tránh public cache vô tình lưu bản nội bộ.

Với tài liệu public, chính sách cache có thể dùng public, max-age=... hoặc immutable URL có version. Chọn TTL phù hợp với cách phát hành và rollback.

## 10. Kiểm thử quyền truy cập tài liệu

Security test cần xác minh cả JSON, Swagger UI, swagger-config và từng group:

| Request | Danh tính | Kết quả mong đợi ví dụ |
|---|---|---|
| GET /v3/api-docs/public | Anonymous | 200 nếu public spec được phép công khai. |
| GET /v3/api-docs/internal | Anonymous | 401 hoặc 403 theo authentication entry point/policy. |
| GET /v3/api-docs/internal | Có DOCS_READ | 200. |
| GET /swagger-ui.html | Anonymous | Bị chặn nếu UI liệt kê internal docs. |
| GET /v3/api-docs/swagger-config | Anonymous | Bị chặn nếu config có URL nội bộ. |
| GET /api/admin/** | Anonymous hoặc user thường | Bị chặn theo security policy nghiệp vụ, bất kể docs bị tắt hay không. |

Ví dụ MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentationAccessTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsAnonymousAccessToPublicSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
                .andExpect(status().isOk());
    }

    @Test
    void deniesAnonymousAccessToInternalSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "DOCS_READ")
    void allowsAuthorizedUserToReadInternalSpecification() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal"))
                .andExpect(status().isOk());
    }
}
~~~

Ví dụ giả định cấu hình dùng authentication entry point trả 401 cho anonymous. Nếu ứng dụng redirect tới login page hoặc trả 403, điều chỉnh assertion theo contract thật. Test cũng cần chạy với group đã được tạo và endpoint docs thực tế của dự án.

### 10.1. Kiểm tra nội dung public spec

Ngoài authorization, cần kiểm tra public artifact không chứa path nội bộ:

~~~java
@Test
void publicSpecificationDoesNotExposeInternalOperations() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/internal/health']").doesNotExist())
            .andExpect(jsonPath("$.paths['/api/admin/reindex']").doesNotExist());
}
~~~

Trong test thực tế, thay hai path minh họa bằng path nội bộ thật của ứng dụng. Có thể parse JSON rồi assert tập path được phép để kiểm tra allow-list một cách tổng quát.

## 11. Những lỗi thường gặp

- **Chỉ khóa Swagger UI nhưng để /v3/api-docs công khai**: người dùng vẫn có thể tải spec trực tiếp.
- **Chỉ khóa JSON nhưng quên swagger-config hoặc UI assets**: giao diện có thể lộ danh sách group hoặc tải tài liệu không đúng policy.
- **Cho rằng GroupedOpenApi là access control**: group chỉ lọc nội dung, không xác thực người tải.
- **Cho rằng tắt docs sẽ bảo vệ API**: endpoint nghiệp vụ vẫn phải có security policy.
- **Dùng một Swagger UI chung cho public và internal docs**: config có thể liệt kê group nội bộ; bảo vệ UI hoặc tách UI/config theo audience.
- **Chỉ dựa vào VPN hoặc IP allow-list**: người trong mạng vẫn cần role/authority phù hợp.
- **Công bố server URL private**: client ngoài mạng không truy cập được và có thể biết cấu trúc nội bộ.
- **Đưa dữ liệu thật vào example**: spec có thể được lưu hoặc chia sẻ ngoài dự kiến.
- **Mở toàn bộ Actuator**: các endpoint quản trị/quan sát có policy riêng.
- **Dùng robots.txt hoặc URL khó đoán làm bảo mật**: crawler policy không ngăn truy cập trực tiếp.
- **Không kiểm tra CDN cache**: artifact nội bộ có thể bị lưu ở cache dùng chung.
- **Không kiểm thử path docs sau khi đổi context path**: security matcher có thể bỏ sót URL mới.

## 12. Quy trình chọn chính sách tài liệu

1. **Phân loại audience**: public, partner, internal hoặc restricted.
2. **Chọn operation**: tạo allow-list cho public group và nhóm riêng cho nội bộ.
3. **Rà soát nội dung**: server URL, schema, examples, extensions, security và error details.
4. **Chọn cách phân phối**: endpoint runtime, private portal hay static artifact đã review.
5. **Thiết lập network boundary**: public ingress, private ingress, VPN hoặc Zero Trust gateway theo audience.
6. **Thiết lập authentication/authorization**: role hoặc authority riêng cho docs.
7. **Bảo vệ mọi URL**: OpenAPI JSON, group JSON, Swagger UI, assets và swagger-config.
8. **Tách Actuator policy**: không để tài liệu docs mở rộng quyền truy cập management endpoints.
9. **Thiết lập cache và audit**: kiểm tra CDN, Cache-Control và access logs.
10. **Kiểm thử**: anonymous, user nội bộ, user không đủ quyền và nội dung public spec.

## 13. Checklist review

- [ ] Public, partner, internal và restricted docs có audience được xác định.
- [ ] Public group chỉ chứa operation đã được duyệt.
- [ ] Group nội bộ không thể tải ẩn danh.
- [ ] Swagger UI và swagger-config có policy phù hợp với các group mà chúng liệt kê.
- [ ] OpenAPI JSON/YAML được bảo vệ độc lập với giao diện.
- [ ] API nghiệp vụ vẫn có security policy riêng.
- [ ] Network boundary được kết hợp với authentication và authorization.
- [ ] Server URL, schema, example, description và extension đã được rà soát.
- [ ] Actuator endpoints có policy riêng.
- [ ] Artifact tĩnh có version, review và quyền truy cập phù hợp.
- [ ] Cache/CDN không làm lộ tài liệu nội bộ.
- [ ] Test bao phủ anonymous, authorized, unauthorized và public content allow-list.

## 14. Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [OpenAPI Specification 3.1.2](https://spec.openapis.org/oas/v3.1.2.html)
- [MDN – HTTP Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)
- [Google Search Central – Robots meta tag and X-Robots-Tag](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)

Tài liệu công khai và nội bộ nên có audience, nội dung và policy truy cập rõ ràng. GroupedOpenApi giúp tách hợp đồng; Spring Security và gateway kiểm soát ai tải được JSON/UI; private ingress giới hạn đường mạng; quy trình review và versioning kiểm soát nội dung được phát hành. Bảo vệ đủ các lớp này giúp developer nhận được tài liệu cần thiết mà không vô tình công bố cấu trúc và operation chỉ dành cho nội bộ.
