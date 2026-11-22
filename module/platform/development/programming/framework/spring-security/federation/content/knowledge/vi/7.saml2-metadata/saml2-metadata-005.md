# Địa chỉ metadata mặc định và tùy chỉnh theo phiên bản Spring Security

**SAML 2.0 metadata** là tài liệu XML mô tả các thông số giúp Service Provider (SP) và Identity Provider (IdP) thiết lập quan hệ tin cậy: Entity ID, các endpoint, bindings và public certificate. Trong Spring Security SAML2 Service Provider, ứng dụng Spring là **SP/Relying Party**, có thể phát hành **SP metadata** dựa trên `RelyingPartyRegistration` và cung cấp một URL HTTP để quản trị IdP tải XML.

Câu hỏi "metadata ở URL nào?" chỉ có đáp án chính xác khi biết **phiên bản Spring Security và cách ứng dụng bật tính năng metadata**. Bên cạnh đó, **SP metadata URL, SP Entity ID, ACS URL và IdP metadata URL là bốn khái niệm khác nhau**. Đổi một URL tải metadata không tự đổi Entity ID hoặc nơi nhận SAML Response. Bài học giải thích mặc định của từng thế hệ, các cách tùy chỉnh an toàn và quy trình xác minh bằng HTTP/XML thực.

## 1. Phân biệt bốn địa chỉ quan trọng

Giả sử ứng dụng `https://portal.example.com` tích hợp IdP của đối tác B, dùng `registrationId = partner-b`.

| Loại | Ví dụ | Chức năng |
| --- | --- | --- |
| **SP metadata URL** | `https://portal.example.com/saml2/metadata/partner-b` | Địa chỉ GET trả XML của SP để đưa cho IdP |
| **SP Entity ID** | `https://portal.example.com/saml2/service-provider-metadata/partner-b` | Định danh SAML của SP; IdP dùng làm audience/đối tượng tin cậy |
| **SP ACS URL** | `https://portal.example.com/login/saml2/sso/partner-b` | Nơi trình duyệt gửi SAML Response tới SP, thường qua HTTP POST |
| **IdP metadata URL** | `https://login.partner-b.example/idp/metadata` | Nguồn metadata của IdP mà SP đọc để biết issuer, SSO endpoint, certificate |

Tên miền `.example` là ví dụ, không phải máy chủ có thể truy cập thật.

Một điểm dễ gây nhầm: mặc định `RelyingPartyRegistration.entityId` trong nhiều dòng Spring Security có dạng `{baseUrl}/saml2/service-provider-metadata/{registrationId}`. Chuỗi này **trông giống đường dẫn tải metadata lịch sử**, nhưng bản chất là một định danh giao thức. Entity ID **không bắt buộc** là một URL có thể tải XML bằng HTTP.

**`registrationId` cũng không phải Entity ID.** Nó là khóa nội bộ giúp `RelyingPartyRegistrationRepository` tìm bản cấu hình cặp SP–IdP. Có thể đặt `partner-b`, `corp`, `vendor-01`, miễn trùng khớp cấu hình hệ thống.

## 2. Mốc phiên bản: Spring Security thay đổi gì?

| Thế hệ | Cơ chế phát SP metadata | Endpoint tiêu biểu khi đã cấu hình | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Spring Security SAML Extension đời cũ** | `MetadataGeneratorFilter` và `MetadataDisplayFilter` của extension riêng | `/saml/metadata` | Là stack khác với module SAML2 hiện đại |
| **Spring Security 5.2.x / giai đoạn SAML2 ban đầu** | SAML2 SP chưa có endpoint XML metadata tích hợp như các bản sau | Thường cần cung cấp metadata theo cách riêng | Không coi default SP Entity ID là bằng chứng có endpoint HTTP |
| **Spring Security 5.4–5.8** | `Saml2MetadataFilter` được thêm thủ công vào SecurityFilterChain | `/saml2/service-provider-metadata/{registrationId}` trong các hướng dẫn giai đoạn đó | Không tự có URL chỉ vì dependency SAML2 tồn tại |
| **Spring Security 6.0** | Kiểm API filter đúng patch và cấu hình thủ công | Đường dẫn do filter/matcher thực tế quyết định | `HttpSecurity.saml2Metadata` chưa phải API của 6.0 |
| **Spring Security 6.1–6.5** | `http.saml2Metadata(...)` DSL; có resolver và filter mở rộng | `/saml2/metadata`, `/saml2/metadata/{registrationId}`, cùng alias cũ | DSL `saml2Metadata` xuất hiện từ **6.1** |
| **Spring Security 7.x** | Tiếp tục `saml2Metadata(...)` và metadata response resolver | Cùng các route hiện đại, tùy custom config | Kiểm API version và Servlet stack trước nâng cấp |

Theo Javadoc, `Saml2MetadataFilter` có từ **5.4**. Javadoc `HttpSecurity.saml2Metadata` (6.1, 6.5 và 7.1) mô tả URL chính `/saml2/metadata`, URL theo registration `/saml2/metadata/{registrationId}` và sự hỗ trợ tương thích ngược cho `/saml2/service-provider-metadata/{registrationId}`. Mẫu cấu hình của Spring Security 5.5 sử dụng filter và đường cũ. Spring Security 5.x dùng `javax.servlet`, trong khi 6.x/7.x dùng `jakarta.servlet`.

**"Mặc định" không có nghĩa tự bật.** Ở 6.1+, phải cấu hình `saml2Metadata` hoặc cơ chế tương đương, với `RelyingPartyRegistrationRepository` hợp lệ. Ở nhánh 5.x sử dụng `Saml2MetadataFilter`, phải thêm filter vào chain. Nếu ứng dụng có nhiều chain hoặc đã tự định tuyến, hành vi cuối cùng phụ thuộc chain nhận request.

## 3. Ba địa chỉ mặc định của Spring Security 6.1+ và 7.x

### `GET /saml2/metadata`

Đây là endpoint chung. Khi repository **có thể lặp các registration** (ví dụ `InMemoryRelyingPartyRegistrationRepository`), resolver có thể xuất metadata tổng hợp dưới phần tử `<md:EntitiesDescriptor>`. Trường hợp chỉ có một registration thì hình thức XML có thể là một `EntityDescriptor` theo resolver.

Nếu có các IdP đối tác B và C, hãy cân nhắc có nên xuất tài liệu tổng hợp cho từng IdP hay không. Không phải mọi đối tác đều cần biết toàn bộ SP registrations của hệ thống.

### `GET /saml2/metadata/{registrationId}`

Đây là endpoint theo một registration:

~~~text
https://portal.example.com/saml2/metadata/corp
https://portal.example.com/saml2/metadata/partner-b
~~~

Thành phần trong ngoặc nhọn là **biến đường dẫn**. Endpoint thực sẽ có `partner-b`, không phải chuỗi `{registrationId}` nguyên văn. Repository phải chứa registration tương ứng; unknown ID không được mặc định trỏ tới một IdP khác.

### `GET /saml2/service-provider-metadata/{registrationId}`

Đây là alias **tương thích ngược** được tài liệu các dòng 6.1+/7.x công nhận khi dùng cấu hình mặc định:

~~~text
https://portal.example.com/saml2/service-provider-metadata/partner-b
~~~

Nhiều ứng dụng cũ dùng đường này làm nơi phát XML, đồng thời dùng chính dạng URL ấy làm SP Entity ID. Hai vai trò **vẫn riêng biệt**: một URL là chỗ tải metadata, một chuỗi là SAML issuer/audience. Khi ứng dụng tùy chỉnh `metadataUrl(...)` hay request matcher, cần thử HTTP thật để biết alias cũ còn hoạt động hay không; không suy ra tất cả các alias mặc định tự tồn tại trong cấu hình đã tùy chỉnh.

## 4. Luồng metadata và đăng nhập khác nhau như thế nào?

~~~mermaid
sequenceDiagram
    participant Admin as Quản trị IdP
    participant B as Trình duyệt người dùng
    participant SP as Spring Security SP
    participant IdP as Identity Provider
    Admin->>SP: GET /saml2/metadata/partner-b
    SP-->>Admin: XML SPSSODescriptor, EntityID, ACS, certificate
    Admin->>IdP: Đăng ký SP
    B->>SP: GET /secure
    SP-->>B: AuthnRequest hướng tới IdP
    B->>IdP: Xác thực
    IdP-->>B: SAMLResponse
    B->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Kiểm signature, issuer, audience, recipient, quyền
~~~

Endpoint metadata GET **không xử lý SAML Response**. ACS xử lý SAML Response; endpoint `/saml2/authenticate/{registrationId}` bắt đầu luồng SP-initiated; `/saml2/metadata/{registrationId}` chỉ xuất tài liệu XML. Nếu route metadata trả HTTP 200, mới xác nhận được một phần cấu hình SP; vẫn cần test login đầy đủ.

## 5. Bật metadata với Spring Security 6.1+ bằng JavaConfig

Trong ứng dụng **Servlet** có dependency `spring-security-saml2-service-provider`, đã cấu hình `RelyingPartyRegistrationRepository` hợp lệ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlMetadataConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là file cấu hình trong **dự án Spring Boot/Spring Security**, không phải chương trình Java độc lập chạy bằng `javac`. `saml2Login` mở luồng xác thực SAML; `saml2Metadata` cấu hình endpoint phát SP metadata. Mẫu còn thiếu IdP trust config/keys nên không thể tự đăng nhập.

Một cấu hình registration Spring Boot ở dòng hỗ trợ property `assertingparty.metadata-uri` có thể là:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://login.partner-b.example/idp/metadata"
~~~

`assertingparty.metadata-uri` chỉ **nơi SP đọc metadata của IdP B**, không đặt URL SP metadata được phát ra. Metadata IdP phải đến từ nguồn tin cậy, và cấu hình bổ sung certificate/ký/giải mã phải phù hợp hợp đồng. Các tên property có thể khác ở Spring Boot/Spring Security đời cũ; hãy xem tài liệu của **Boot version đang dùng**.

### Có nhất thiết phải thêm Controller cho `/saml2/metadata`?

Không. DSL dùng filter và metadata resolver chính thức của Spring Security. Thêm một `@GetMapping("/saml2/metadata")` chạy song song có thể gây nhầm chỗ xử lý request hoặc trả XML không đồng nhất với `RelyingPartyRegistration`. Chỉ dùng controller tự xây khi có lý do chuyên biệt, đã kiểm đủ SAML metadata và trách nhiệm bảo mật; thông thường ưu tiên DSL.

### Có thể xuất metadata khi chưa có người dùng đăng nhập?

Thường có: metadata được quản trị IdP tải để thiết lập quan hệ SP–IdP, nên không phụ thuộc session người dùng. Tuy nhiên endpoint thật vẫn nằm dưới security chain; nếu cấu hình path/authorization không phù hợp, request có thể bị 302/401/403. Hãy kiểm HTTP response, không chỉ đoán từ `authorizeHttpRequests`.

## 6. Đổi endpoint trong Spring Security 6.1–6.5 và 7.x

Cách trực tiếp là `Saml2MetadataConfigurer.metadataUrl(String)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomSamlMetadataConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(saml ->
                saml.metadataUrl("/federation/metadata/{registrationId}"));
        return http.build();
    }
}
~~~

Nếu repository chứa `partner-b`, metadata sẽ được yêu cầu tại:

~~~text
GET https://portal.example.com/federation/metadata/partner-b
~~~

Mẫu `{registrationId}` cho phép resolver chọn đúng cấu hình. Nếu muốn một URL không có ID:

~~~java
.saml2Metadata(saml -> saml.metadataUrl("/federation/metadata"))
~~~

Theo Javadoc, với repository **Iterable**, endpoint không ID có thể xuất metadata của toàn bộ registrations dưới một `EntitiesDescriptor`. Nếu muốn logic tìm registration phức tạp hơn (host/domain/tenant được phê duyệt, một registration cố định), hãy dùng `metadataResponseResolver(...)` và xây chính sách ánh xạ rõ ràng.

**Đổi URL xuất XML không đổi:**

- `RelyingPartyRegistration.entityId`;
- `RelyingPartyRegistration.assertionConsumerServiceLocation`;
- IdP Entity ID hoặc IdP metadata URL;
- URL bắt đầu login;
- credential ký/giải mã hoặc vai trò người dùng.

Khi di chuyển link metadata, đội vận hành IdP cần biết địa chỉ mới, nhất là khi IdP tự refresh metadata. Nhưng **không đổi SP Entity ID/ACS nếu không có kế hoạch phối hợp hai phía**.

## 7. Tùy chỉnh sâu với `Saml2MetadataResponseResolver`

Khi một mẫu URL không đủ, Spring Security hiện đại cung cấp `Saml2MetadataResponseResolver` và resolver dựa trên request matcher/registration repository. Các nhu cầu hợp lý:

- Cho IdP A tải metadata từ route cố định mà không có ID, còn IdP B dùng route khác.
- Phân phối metadata theo hostname/tenant **được phía server phê duyệt**.
- Xuất toàn bộ `EntitiesDescriptor` hoặc metadata từng đối tác một cách có chủ đích.
- Tùy chỉnh tên file tải về.
- Tạo metadata từ repository có cập nhật cấu hình, keys hoặc cert theo quy trình rotation.

Ví dụ luồng resolver ở tầng thiết kế:

~~~text
GET /partners/b/sp-metadata
  -> server rule: route B
  -> registrationId = partner-b
  -> RelyingPartyRegistrationRepository.findByRegistrationId("partner-b")
  -> metadata XML từ registration partner-b

GET /partners/c/sp-metadata
  -> server rule: route C
  -> registrationId = partner-c
  -> metadata XML từ registration partner-c

GET /partners/unknown/sp-metadata
  -> không có registration hợp lệ -> từ chối
~~~

**Không tin header/query do browser tùy ý gửi** để quyết định một issuer hoặc trust configuration chưa được cấp phép. Đặc biệt trong ứng dụng nhiều tenant, hostname public và rule tenant phải nằm trong allowlist của server.

Từ 6.1 trở lên, có thể cấu hình response resolver qua API `saml2Metadata(meta -> meta.metadataResponseResolver(...))`. API constructor/package của một số implementation đã thay đổi giữa các major; với snippet copy từ blog, hãy kiểm Javadoc theo **phiên bản cụ thể**. Không trộn `RequestMatcherMetadataResponseResolver` của dòng mới với `OpenSamlMetadataResolver`/constructor cũ nếu chưa kiểm tương thích.

## 8. Ở Spring Security 5.4–5.8, sử dụng `Saml2MetadataFilter`

Các dự án 5.x thường thêm filter xử lý SP metadata vào `SecurityFilterChain`. Một cấu hình theo API **Spring Security 5.8**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.metadata.OpenSamlMetadataResolver;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.Saml2MetadataFilter;
import org.springframework.security.saml2.provider.service.web.Saml2WebSsoAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class MetadataFilterConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {
        var resolver = new DefaultRelyingPartyRegistrationResolver(registrations);
        var metadataFilter = new Saml2MetadataFilter(
                resolver, new OpenSamlMetadataResolver());

        metadataFilter.setRequestMatcher(
                new AntPathRequestMatcher(
                    "/legacy/saml-metadata/{registrationId}", "GET"));

        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        http.addFilterBefore(
                metadataFilter, Saml2WebSsoAuthenticationFilter.class);
        return http.build();
    }
}
~~~

Trong snippet, `/legacy/saml-metadata/{registrationId}` là **route do ứng dụng chọn**, không phải default của mọi 5.x. Nếu không tùy chỉnh filter theo ví dụ lịch sử Spring Security 5.5, tài liệu thường dùng `/saml2/service-provider-metadata/{registrationId}`.

**Khác biệt API:**

- `Saml2MetadataFilter` tồn tại từ 5.4.
- `setRequestMatcher(...)` đặt đường dẫn cần xử lý.
- `setMetadataFilename(...)` tùy chỉnh tên file metadata (ví dụ `saml-{registrationId}-metadata.xml`).
- Một số constructor cũ nhận `Converter<HttpServletRequest, RelyingPartyRegistration>` được deprecated ở 5.8; code trên dùng `RelyingPartyRegistrationResolver`.
- Spring Security 5.8 dùng `javax.servlet.*`; 6.x/7.x dùng `jakarta.servlet.*`.

**Không lấy cấu hình 5.8 này áp nguyên xi cho 6.1+/7.x** khi đã có DSL. Nếu vừa thêm filter cũ vừa bật `saml2Metadata(...)`, có nguy cơ hai filter/đường dẫn cùng xử lý hoặc tạo metadata không nhất quán.

### Riêng Spring Security 6.0

Javadoc ghi `HttpSecurity.saml2Metadata(...)` có từ **6.1**. Dự án 6.0 không được giả định method đó tồn tại; cần tham khảo API `Saml2MetadataFilter` đúng phiên bản và cấu hình thủ công phù hợp, hoặc nâng toàn bộ bộ dependency qua BOM có kiểm thử. Tránh sửa bằng cách chỉ override `spring-security-config` lên 6.1 khi các module còn lại 6.0.

## 9. Vì sao legacy Spring Security SAML Extension dùng `/saml/metadata`?

Trước module `spring-security-saml2-service-provider` hiện đại có **Spring Security SAML Extension** riêng. Mẫu cấu hình cũ sử dụng `MetadataGeneratorFilter` và `MetadataDisplayFilter`, thường phục vụ metadata tại `/saml/metadata`.

Đây là một stack khác. Nếu ứng dụng nâng lên module SAML2 của Spring Security hiện đại, route `/saml/metadata` **không tự xuất hiện**. Muốn tiếp tục hỗ trợ địa chỉ cũ cho IdP đã đăng ký, chủ động đặt:

~~~java
.saml2Metadata(saml -> saml.metadataUrl("/saml/metadata"))
~~~

Cấu hình trên yêu cầu dòng Spring Security có DSL 6.1+; chọn repository/resolver phù hợp nếu nhiều registration. Duy trì route cũ **không đồng nghĩa tái sử dụng được toàn bộ XML metadata cũ**: phải đối chiếu SP Entity ID, ACS, signing certificates, bindings và logout endpoints.

Cách nhận diện stack từ codebase:

| Ký hiệu | Thuộc nhánh |
| --- | --- |
| `MetadataGeneratorFilter`, `MetadataDisplayFilter`, `ExtendedMetadata` | Spring Security SAML Extension cũ |
| `Saml2MetadataFilter` và `OpenSamlMetadataResolver` | Spring Security SAML2, đặc biệt cách cấu hình 5.4–6.0 |
| `saml2Metadata(...)`, `metadataUrl(...)` | Spring Security 6.1 trở lên |
| `RelyingPartyRegistration` | Mô hình cấu hình SP–IdP của SAML2 Service Provider mới |

## 10. Đổi metadata URL nhưng giữ nguyên Entity ID và ACS

Giả sử trước migration:

~~~text
SP metadata GET:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP Entity ID:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

Sau khi đổi cách công bố XML:

~~~text
SP metadata GET:
https://portal.example.com/federation/metadata/partner-b

SP Entity ID:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

Việc này hoàn toàn có ý nghĩa: Entity ID và ACS **giữ ổn định**, chỉ thay đường tải XML. Quản trị IdP cần cập nhật URL metadata nếu bên đó refresh từ URL, nhưng **không cần đổi audience/recipient** nếu không có thay đổi SP contract.

Ngược lại, nếu đổi SP Entity ID/ACS mà không điều phối IdP, dễ có lỗi: IdP không nhận ra SP, `AudienceRestriction` cũ khác Entity ID mới, `Destination`/`Recipient` không khớp, hoặc SAML Response gửi sai ACS. Không tắt validation để che lỗi cấu hình.

## 11. Reverse proxy và base URL rất dễ làm metadata sai

Một ứng dụng Spring chạy trong container tại:

~~~text
http://app:8080
~~~

Nhưng người dùng và IdP nhìn thấy:

~~~text
https://sso.example.com/portal
~~~

Nếu `{baseUrl}` được xây từ request nội bộ hoặc forwarded headers không tin cậy, XML có thể chứa Entity ID/ACS không đúng. Quy trình:

1. Xác định **public URL** thật (HTTPS, hostname, port, context path).
2. Kiểm `RelyingPartyRegistration.entityId` và `assertionConsumerServiceLocation`, có thể khai báo tường minh nếu proxy phức tạp.
3. Chỉ xử lý `Forwarded`/`X-Forwarded-*` từ ingress/reverse proxy được quản trị, không nhận header tự phát từ client.
4. Tải metadata qua **hostname public** và kiểm `EntityDescriptor/@entityID`, `AssertionConsumerService/@Location`.
5. Kiểm IdP đã đăng ký chính xác các giá trị đó.
6. Test SP-initiated SSO, không chỉ GET metadata.
7. Giữ NTP/clock sync, TLS và chứng thư hợp lệ.

**Không dùng `Host`/`X-Forwarded-Host` tùy ý làm Entity ID hoặc ACS**, vì attacker có thể tác động metadata được tạo ra nếu proxy trust không đúng.

## 12. Cách xác minh XML metadata được phát

Tài liệu SP metadata có thể chứa các phần tử sau (ví dụ **giản lược**, không phải output chắc chắn của mọi phiên bản):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://portal.example.com/saml2/service-provider-metadata/partner-b">
    <md:SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://portal.example.com/login/saml2/sso/partner-b"
            index="1" />
    </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

Trong metadata thật có thể có `KeyDescriptor` (public signing/encryption certificates), `SingleLogoutService`, metadata XML signature hoặc nhiều bindings. Nếu có nhiều registration, root có thể là `<md:EntitiesDescriptor>` chứa nhiều EntityDescriptor.

**Kiểm những điểm sau:**

| Trường | Câu hỏi |
| --- | --- |
| HTTP status/Content-Type | Có nhận **metadata XML** hay bị redirect login/trả HTML? |
| `EntityDescriptor/@entityID` | Có khớp Entity ID mà IdP dùng để nhận diện SP? |
| `SPSSODescriptor` | Có thực sự mô tả SP, không nhầm metadata IdP? |
| `AssertionConsumerService/@Location` | Có đúng URL public đã đăng ký ở IdP? |
| `AssertionConsumerService/@Binding` | Có phù hợp cơ chế IdP gửi SAML Response? |
| `KeyDescriptor` | Public certificate có đúng loại/đang còn hiệu lực theo kế hoạch rotate? |
| Metadata signature (nếu có) | Bên tiêu thụ có kiểm theo trust policy? |
| `EntitiesDescriptor` | Có xuất nhiều registration ngoài chủ đích? |

Metadata chứa **public certificate**, không được chứa private signing key/decryption key của SP. Metadata IdP có thể có chữ ký: nếu ứng dụng sử dụng metadata IdP làm nguồn trust, cần lấy từ nguồn tin cậy và kiểm signature theo chính sách. Không tự chấp nhận certificate bất kỳ nằm trong Response.

## 13. Kiểm endpoint bằng HTTP thực tế

Sau khi ứng dụng chạy trên URL public hợp lệ:

~~~bash
curl -i https://portal.example.com/saml2/metadata/partner-b
curl -i https://portal.example.com/saml2/metadata
curl -i https://portal.example.com/saml2/service-provider-metadata/partner-b
~~~

Nếu dùng đường tùy chỉnh:

~~~bash
curl -i https://portal.example.com/federation/metadata/partner-b
~~~

Các lệnh sẽ không có stdout cố định vì mỗi ứng dụng trả XML khác nhau. Đánh giá theo tình huống:

| Kết quả | Hướng điều tra |
| --- | --- |
| `404` | Sai path/context path, chưa bật DSL/filter, sai version hoặc chain không match |
| `302` đến login | Request bị chuyển tới entry point/login thay vì metadata filter |
| `401/403` | Rule hoặc chuỗi security không cho phép truy cập theo thiết kế |
| `500` | Repository, metadata resolver hoặc registration/certificate có lỗi |
| `200` nhưng HTML | Có thể response là trang khác, proxy hoặc controller không đúng |
| `200` với SAML XML | Kiểm các field XML và thử login thực tế |
| ID lạ có metadata của một đối tác khác | Resolver chọn sai registration: cần sửa ngay |

Cần kiểm URL **cũ và mới** khi nâng phiên bản. Sau khi sửa `metadataUrl`, không tự kết luận alias cũ vẫn hoạt động. Nếu cần duy trì hai route trong thời gian migration, thiết kế rõ quy tắc routing và test cả hai.

## 14. Một chương trình Java 17 chạy độc lập để phân biệt các đường dẫn

Đoạn mã dưới đây không chạy Spring Security và không đọc metadata XML. Nó mô phỏng bảng URL theo thế hệ và khẳng định hai chuỗi khác nhau có thể đồng thời đại diện Entity ID và đường tải XML.

Tạo file `SamlMetadataRoutesDemo.java`:

~~~java
public class SamlMetadataRoutesDemo {
    static String resolve(String pattern, String registrationId) {
        return pattern.replace("{registrationId}", registrationId);
    }

    public static void main(String[] args) {
        String legacy = resolve(
                "/saml2/service-provider-metadata/{registrationId}",
                "partner-b");
        String current = resolve(
                "/saml2/metadata/{registrationId}",
                "partner-b");

        String entityId = "https://portal.example.com" + legacy;
        String customMetadataUrl = "https://portal.example.com"
                + "/federation/metadata/partner-b";

        System.out.println("5.8 filter route: " + legacy);
        System.out.println("6.1+ metadata route: " + current);
        System.out.println("Entity ID remains: "
                + entityId.endsWith("/partner-b"));
        System.out.println("Different URL: "
                + !entityId.equals(customMetadataUrl));
    }
}
~~~

Lệnh chạy bằng JDK 17 trở lên:

~~~bash
javac SamlMetadataRoutesDemo.java
java SamlMetadataRoutesDemo
~~~

Stdout chính xác:

~~~text
5.8 filter route: /saml2/service-provider-metadata/partner-b
6.1+ metadata route: /saml2/metadata/partner-b
Entity ID remains: true
Different URL: true
~~~

Đây là ví dụ **xử lý chuỗi**, không phát metadata, không kiểm SAML signature, không kiểm Spring dependency thực tế. Việc route nào hoạt động trong ứng dụng vẫn phải được kiểm bằng filter/DSL và HTTP request.

## 15. Migration endpoint an toàn qua các version

Một kế hoạch thực tế khi nâng từ 5.8 sang 6.5/7.x hoặc muốn đổi URL:

1. **Ghi lại cấu hình hiện tại:** Spring Boot/Security version, registrationId, metadata URL, Entity ID, ACS, certificate và bindings đang dùng.
2. **Kiểm đúng artifact đã resolve** bằng Gradle/Maven. Đừng dựa một mình vào version trong `pom.xml` nếu BOM có override.
3. **Phân loại thay đổi:** chỉ URL tải XML, hay còn Entity ID/ACS/keys?
4. **Chọn cơ chế phù hợp:** 5.8 dùng filter/matcher; 6.1+ dùng DSL `saml2Metadata()/metadataUrl()` hoặc resolver.
5. **Không để filter trùng** giữa cấu hình cũ và mới mà không chủ ý.
6. **Kiểm staging:** GET XML qua public URL, so sánh Entity ID, ACS, certificate và bindings với tài liệu trước deploy.
7. **Phối hợp quản trị IdP:** cập nhật metadata import URL, xem IdP có auto-refresh hoặc chỉ lưu snapshot.
8. **Test SP-initiated login**: AuthnRequest/Response, signature, audience, recipient, InResponseTo, thời hạn và replay.
9. **Test negative cases:** registration không tồn tại, issuer lạ, wrong audience, sai ACS, expired certificate, account bị thu hồi.
10. **Theo dõi và rollback:** giữ route cũ nếu cần tới khi các IdP đã cập nhật, có cảnh báo 404/SSO failure.

Đổi URL metadata phải được xem là thay đổi về onboarding/vận hành. Đổi Entity ID/ACS là thay đổi giao thức cần IdP phê duyệt.

## 16. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| `/saml/metadata` 404 sau nâng phiên bản | Địa chỉ legacy SAML Extension không tự có ở module SAML2 mới | Đặt route qua DSL/resolver phù hợp |
| `/saml2/metadata` 404 trên Security 5.8 | Đang dùng filter cũ và route khác, hoặc chưa thêm filter | Kiểm `Saml2MetadataFilter`/`setRequestMatcher` |
| `saml2Metadata(...)` không compile | Version nhỏ hơn 6.1 | Kiểm dependency graph; dùng filter đúng version hoặc nâng BOM |
| Lỗi `javax.servlet`/`jakarta.servlet` | Trộn thư viện từ các major khác nhau | Đồng bộ Spring Boot/Security/Servlet API |
| URL tổng hợp không hoạt động | Repository không Iterable hoặc resolver tùy chỉnh không hỗ trợ | Dùng route có ID hoặc resolver chủ động |
| GET metadata về HTML | Login redirect, gateway rewrite, controller khác | Kiểm HTTP status, Content-Type, filter ordering |
| Metadata có `http://localhost:8080` | Public base URL/forwarded headers sai | Cấu hình proxy, Entity ID và ACS public |
| Invalid Audience sau thay link | Entity ID đã vô tình thay đổi | So contract cũ/mới với IdP |
| Invalid Recipient/Destination | ACS sai so với URL đã đăng ký | Sửa ACS/IdP, không tắt validation |
| Cert mismatch sau rotation | Chứng thư IdP/SP chưa đồng bộ | Update trust/metadata theo quy trình |
| Login được nhưng không vào trang | Role hoặc tenant authorization thiếu | Kiểm ánh xạ user/role, không đổ lỗi metadata |

Một số đội vận hành nhầm `302` từ URL metadata là “metadata có thể đọc được vì login page mở”. Kết quả đó **không** xác nhận SAML metadata được trả về. Cần XML đúng loại.

## 17. Checklist QA trước khi công bố SP metadata

- [ ] Đã xác định Spring Security runtime version và cơ chế filter/DSL tương ứng.
- [ ] Có `RelyingPartyRegistrationRepository` hợp lệ với `registrationId` cần thiết.
- [ ] GET URL đã công bố trả đúng SP metadata XML.
- [ ] Đối chiếu SP `entityID`, ACS và binding với IdP.
- [ ] Public hostname/HTTPS/context path ổn phía reverse proxy.
- [ ] Public certificate đúng, private key không lộ trong metadata/log.
- [ ] URL mới và alias cũ đã được test theo chính sách migration.
- [ ] Với nhiều registration, không vô ý phát metadata của đối tác khác.
- [ ] IdP nhập metadata, xác minh trust/credentials và chấp nhận SP.
- [ ] SP-initiated login thành công với user test; invalid signature/issuer/audience/recipient đều bị từ chối.
- [ ] Phân quyền tenant/object hoạt động riêng sau khi xác thực.
- [ ] Có tài liệu hóa người sở hữu metadata, lịch rotation, theo dõi lỗi và rollback.

## 18. Tài liệu tham khảo chính thức

Các tài liệu nên được chọn theo **đúng dòng Spring Security**:

1. [Spring Security hiện hành — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): URL mặc định, DSL `saml2Metadata`, `metadataUrl` và resolver.
2. [Javadoc Spring Security 7.1 — HttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html): mốc `saml2Metadata` từ 6.1, alias tương thích ngược.
3. [Javadoc — Saml2MetadataConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2MetadataConfigurer.html): hành vi route có hoặc không có `{registrationId}`.
4. [Javadoc Spring Security 5.8 — Saml2MetadataFilter](https://docs.spring.io/spring-security/site/docs/5.8.0/api/org/springframework/security/saml2/provider/service/web/Saml2MetadataFilter.html): filter, `setRequestMatcher`, phiên bản Servlet cũ.
5. [Reference Spring Security 5.5.6](https://docs.spring.io/spring-security/site/docs/5.5.6/reference/html5/): cách tạo SP metadata bằng filter và URL cũ.
6. [Reference Spring Security 5.2.1](https://docs.spring.io/spring-security/site/docs/5.2.1.RELEASE/reference/html/saml2.html): giai đoạn chưa có endpoint metadata tích hợp.
7. [Spring Security SAML Extension cũ — Metadata](https://docs.spring.io/spring-security-saml/docs/current/reference/html/configuration-metadata.html): đường `/saml/metadata` của extension riêng.
8. [Spring Security hiện hành — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): mối quan hệ Entity ID, ACS và các URL liên quan.
9. [Spring Boot 3.4 — SAML2 Relying Party](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html): property và repository auto-configuration.

**Ghi nhớ:** với **Spring Security 6.1+/7.x**, endpoint chính là `/saml2/metadata` và `/saml2/metadata/{registrationId}`, với alias `/saml2/service-provider-metadata/{registrationId}` trong cấu hình mặc định. **5.4–5.8** dùng `Saml2MetadataFilter`; **Spring Security SAML Extension** cũ dùng `/saml/metadata`. Trong mọi thế hệ, phải tách bạch **URL tải XML**, **SP Entity ID** và **ACS**, rồi kiểm response XML và luồng SAML thật.