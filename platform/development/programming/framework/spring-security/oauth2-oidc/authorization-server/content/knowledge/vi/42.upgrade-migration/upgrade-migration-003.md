# Phân biệt lịch sử Spring Authorization Server độc lập với tích hợp trong Spring Security

Spring Authorization Server (SAS) từng được phát triển và phát hành như một dự án riêng của nhóm Spring Security. Từ Spring Security 7.0, phần Authorization Server được đưa vào chính dự án Spring Security. Đây là thay đổi về nơi phát triển, phát hành và tài liệu hóa; nó không có nghĩa là ứng dụng phải thay toàn bộ mô hình OAuth 2.0, viết lại client hoặc chuyển Authorization Server thành một dịch vụ khác.

Với module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, các khái niệm như RegisteredClient, authorization, consent, token endpoint, PKCE, refresh token, JWK và OIDC vẫn là nền tảng. Bài thuộc chương **Nâng cấp và chuyển đổi**, giúp nhận diện đúng hai thế hệ thư viện, chọn dependency phù hợp và lập kế hoạch chuyển ứng dụng từ nhánh SAS độc lập 1.x sang Spring Security 7.x.

## 1. Lịch sử phát triển và mốc chuyển đổi

Trước SAS, hệ sinh thái Spring có dự án Spring Security OAuth, thường được nhận diện qua các artifact thuộc nhóm Spring Security OAuth cũ. Dự án này đã bị thay thế cho nhu cầu xây dựng Authorization Server hiện đại. Spring Authorization Server là dự án kế nhiệm, do nhóm Spring Security dẫn dắt, được phát triển để cung cấp nền tảng OAuth 2.1 Authorization Server cho cộng đồng Spring.

SAS 1.0 được phát hành chính thức vào tháng 11 năm 2022. Việc phát triển độc lập giúp dự án hoàn thiện nhanh các tính năng OAuth 2.0 và OpenID Connect, đồng thời ổn định API trước khi tích hợp sâu vào Spring Security. Dòng 1.5.x là thế hệ cuối của dự án SAS độc lập.

Tháng 9 năm 2025, nhóm Spring thông báo chuyển Spring Authorization Server vào Spring Security 7.0. Từ thế hệ này, mã nguồn, Javadoc, tài liệu tham chiếu, issue và pull request của OAuth2 Authorization Server được quản lý cùng Spring Security. Spring Security 7.0 ghi nhận Authorization Server là một module của chính dự án.

| Giai đoạn | Nơi phát triển và phát hành | Dòng phiên bản | Cách hiểu |
|---|---|---|---|
| Spring Security OAuth cũ | Dự án Spring Security OAuth trước đây | Các dòng 2.x cũ | Công nghệ tiền nhiệm, không phải SAS |
| Spring Authorization Server độc lập | Repository Spring Authorization Server | 1.0.x đến 1.5.x | Dự án riêng do nhóm Spring Security duy trì |
| Authorization Server trong Spring Security | Repository và tài liệu Spring Security | Bắt đầu từ 7.0 | Module Authorization Server được tích hợp vào Spring Security |

Không nên gọi Spring Authorization Server 1.5.x là Spring Security 6.5 Authorization Server. Hai dự án có quan hệ chặt chẽ và được phát hành theo ma trận tương thích, nhưng chúng có số phiên bản và chu kỳ phát hành riêng. Tương tự, Spring Security OAuth cũ và Spring Authorization Server 1.x là hai thế hệ khác nhau.

Một cách đọc ma trận generation thường gặp là SAS 1.5.x đi cùng Spring Security 6.5.x và Spring Framework 6.2.x; Spring Security 7.0.x đi cùng Spring Framework 7.0.x và thường được dùng với Spring Boot 4.0.x. Đây là cặp generation để định hướng, không phải quy tắc thay thế BOM. Hãy kiểm tra dependency management của đúng bản Spring Boot hoặc Spring Security mà ứng dụng chọn.

## 2. “Dự án độc lập” có nghĩa gì?

Ở giai đoạn 1.x, Spring Authorization Server có repository, tài liệu tham chiếu, issue tracker và phiên bản phát hành riêng. Ứng dụng thêm dependency của SAS vào Spring application để tạo các endpoint OAuth/OIDC. “Độc lập” mô tả cách tổ chức phát triển và phát hành thư viện; nó không có nghĩa SAS là một máy chủ chạy tách khỏi ứng dụng Spring của bạn.

Một ứng dụng dùng SAS 1.x vẫn chạy trong Spring Boot hoặc Spring Framework, dùng Spring Security filter chain, RegisteredClientRepository, OAuth2AuthorizationService, JWKSource và các thành phần lưu trữ do ứng dụng cấu hình. Cách triển khai có thể là một ứng dụng độc lập về mặt vận hành, nhưng thư viện SAS là dependency nằm trong ứng dụng đó.

Khi chuyển sang Spring Security 7.0, các thành phần Authorization Server tiếp tục được cung cấp như một module và artifact. Thay đổi chính là quyền sở hữu mã nguồn, tài liệu và phát hành chuyển về Spring Security. Không có yêu cầu phải tạo một process riêng hoặc đổi giao thức giữa client và Authorization Server.

## 3. Dependency trước và sau khi tích hợp

Một điểm được Spring công bố rõ là Maven coordinates của thư viện Authorization Server giữ nguyên groupId và artifactId; phần thay đổi là version. Artifact trực tiếp có dạng:

~~~groovy
dependencies {
    // Ví dụ dùng một bản phát hành thuộc dòng SAS độc lập 1.5.x
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:1.5.0")
}
~~~

Khi dùng Authorization Server thuộc Spring Security 7.0, artifact trực tiếp vẫn giữ tọa độ đó và chuyển sang version 7.0.x:

~~~groovy
dependencies {
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:7.0.0")
}
~~~

Các version 1.5.0 và 7.0.0 minh họa hai generation, không phải khuyến nghị ghim patch đầu tiên trong production. Hãy dùng patch phù hợp với chính sách hỗ trợ và để Spring Security BOM hoặc Spring Boot dependency management chọn phiên bản đồng bộ.

Nếu dùng Spring Boot theo cách được khuyến nghị trong tài liệu Spring Security 7, có thể thêm starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
}
~~~

Hoặc với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

Starter giúp quản lý dependency và auto-configuration theo phiên bản Spring Boot tương ứng. Nếu ứng dụng không dùng Spring Boot, có thể khai báo trực tiếp artifact Spring Security Authorization Server.

Không thêm đồng thời nhiều phiên bản của artifact Authorization Server hoặc trộn starter với một dependency phiên bản khác được khai báo thủ công. Hãy kiểm tra dependency tree để xác định chỉ có một dòng Authorization Server và các module Spring Security cùng một generation.

## 4. Khác biệt trong cấu hình và API

Phần lớn class của Spring Authorization Server được giữ nguyên tên và package khi chuyển sang Spring Security 7.0. Nhóm Spring cho biết chỉ có một số thay đổi package nhỏ. Vì vậy, phần lớn ứng dụng có thể giữ nguyên các thành phần như RegisteredClient, RegisteredClientRepository, OAuth2AuthorizationService, OAuth2AuthorizationConsentService, AuthorizationServerSettings, JWKSource và token customizer.

Tuy nhiên, Spring Security 7.0 đưa Authorization Server DSL vào HttpSecurity. Cấu hình filter chain của Authorization Server theo DSL mới có dạng:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .oauth2AuthorizationServer(authorizationServer -> {
            http.securityMatcher(authorizationServer.getEndpointsMatcher());
            authorizationServer.oidc(Customizer.withDefaults());
        })
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .exceptionHandling(exceptions ->
            exceptions.defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
            )
        );

    return http.build();
}
~~~

Đây là cấu hình filter chain cho protocol endpoints. Ứng dụng vẫn cần một filter chain phù hợp để xử lý form login, user authentication và các request còn lại. Nếu ứng dụng đã có nhiều SecurityFilterChain, phải giữ đúng thứ tự và matcher để endpoint Authorization Server được xử lý bởi chain chuyên biệt.

Một số cấu hình ở dự án SAS 1.x dùng API cấu hình riêng của Authorization Server, chẳng hạn gọi cấu hình mặc định hoặc dùng configurer của SAS. Khi chuyển sang 7.0, hãy chuyển sang DSL tích hợp được tài liệu Spring Security 7 mô tả. Không thay đổi hàng loạt tên class theo phỏng đoán; đọc lỗi compile, kiểm tra import và Javadoc của đúng version.

Ngoài DSL Authorization Server, đây còn là một lần nâng cấp major của Spring Security. Những thay đổi chung của Spring Security 7 có thể ảnh hưởng đến cùng ứng dụng, ví dụ API cấu hình HttpSecurity đã deprecated bị loại bỏ, các matcher cũ được thay thế, và một số API serialization thay đổi. Cần thực hiện cả hướng dẫn migration của Spring Security, không chỉ sửa import của Authorization Server.

## 5. Lộ trình nâng cấp từ SAS 1.5.x sang Spring Security 7.0

Nên thực hiện nâng cấp theo các bước nhỏ để xác định thay đổi nào thuộc dependency, API hay hành vi giao thức.

### Bước 1: Ghi nhận baseline đang chạy

Thu thập các thông tin sau từ build và môi trường triển khai:

- Phiên bản Spring Boot, Spring Framework và Spring Security.
- Phiên bản SAS độc lập đang dùng và dependency tree thực tế.
- Java runtime, database driver và các thư viện OAuth/OIDC liên quan.
- Các SecurityFilterChain, thứ tự chain và endpoint matcher.
- Các customizer, authentication provider, token generator và JWKSource.
- Loại persistence đang dùng cho RegisteredClient, authorization và consent.

Không chỉ nhìn version khai báo trong build file. Dependency management hoặc dependency constraint có thể thay đổi version được resolve khi build.

### Bước 2: Chọn generation đích

Nếu ứng dụng còn ở hệ Spring Security 6.x, có thể tiếp tục dùng dòng SAS 1.x tương thích với generation đó trong khi chuẩn bị nâng cấp. Nếu chuyển sang Spring Security 7.0, hãy nâng cấp cả nền Spring Security và Authorization Server như một thay đổi đồng bộ.

Spring Security 7 yêu cầu Java 17 trở lên. Trong hệ Spring Boot, việc chuyển sang Spring Security 7 thường đi cùng generation Spring Boot mới tương thích với Spring Framework 7. Hãy chọn phiên bản Boot, Framework, Security và Authorization Server theo BOM chính thức; tránh tự nâng một module Security riêng lẻ vượt khỏi generation của ứng dụng.

### Bước 3: Sửa dependency và loại bỏ phiên bản trùng

Chuyển version của artifact trực tiếp sang dòng 7.0.x hoặc dùng Spring Boot starter tương ứng. Sau đó chạy dependency insight để xác minh:

- Không còn SAS 1.5.x trong runtime classpath.
- Không có hai version của Authorization Server.
- Các module Spring Security có cùng generation.
- Không có dependency cũ kéo Spring Security 6.x vào ứng dụng.

Nếu build dùng version catalog, dependency constraints hoặc BOM nội bộ, cập nhật đúng nơi quản lý phiên bản để lần build sau không đưa version cũ trở lại.

### Bước 4: Chuyển cấu hình filter chain

Chuyển Authorization Server SecurityFilterChain sang DSL tích hợp trong Spring Security 7. Kiểm tra lại:

- Matcher chỉ bao phủ protocol endpoints của Authorization Server.
- Chain có thứ tự ưu tiên phù hợp.
- OIDC được bật nếu ứng dụng cung cấp OpenID Connect.
- Request HTML chưa xác thực được chuyển đến login page phù hợp.
- Các endpoint application khác vẫn thuộc chain tương ứng.

Nếu ứng dụng có custom endpoint hoặc endpoint URI đã thay đổi, kiểm tra lại matcher và AuthorizationServerSettings.

### Bước 5: Xử lý thay đổi package và compile

Nhóm Spring dự kiến chỉ có một số package relocation nhỏ. Dùng compiler để xác định chính xác import nào cần đổi. Sau khi sửa:

- Xóa import cũ không còn tồn tại.
- Kiểm tra bean type và method signature của customizer.
- Kiểm tra các extension point kế thừa class của Authorization Server.
- Kiểm tra test source và test fixture vì chúng cũng có thể tham chiếu package cũ.

Không tạo class adapter trùng tên chỉ để giữ import cũ. Nếu một API bị chuyển package, dùng class chính thức ở package mới.

### Bước 6: Kiểm tra các thay đổi hành vi

Spring Security 7.0 bật PKCE mặc định trong OAuth 2.0 Authorization Server. Điều này có thể làm thay đổi kết quả đối với client trước đây không gửi code challenge. Kiểm tra lại tất cả RegisteredClient và client integration:

- Public client phải gửi PKCE theo S256.
- Confidential client cũng có thể bị ảnh hưởng bởi mặc định mới; kiểm tra cấu hình client settings và yêu cầu của từng loại client.
- Test authorization request thiếu code_challenge và token request có code_verifier sai.
- Không vô hiệu hóa PKCE toàn cục chỉ để làm cho một client cũ tiếp tục hoạt động.

Đồng thời rà soát các thay đổi major khác của Spring Security 7 như loại bỏ API deprecated, thay đổi HttpSecurity DSL và các thay đổi Jackson serialization. PKCE mặc định liên quan đến client dùng Authorization Code flow, kể cả confidential client nếu client đó dùng Authorization Code; nó không phải một bước của Client Credentials grant.

### Bước 7: Kiểm thử persistence và dữ liệu đã cấp

Nếu dùng JDBC, kiểm tra schema và cách serialize dữ liệu authorization. Nếu ứng dụng có custom ObjectMapper, custom JdbcOAuth2AuthorizationService hoặc lưu authorization JSON theo định dạng riêng, kiểm tra khả năng đọc dữ liệu được tạo bởi phiên bản cũ.

Spring Security 7 chuyển Spring Authorization Server sang Jackson 3 theo mặc định. Tài liệu migration cho biết định dạng serialization của hỗ trợ Jackson 3 tương thích với định dạng Jackson 2 đã deprecated, nên dữ liệu được serialize bằng Jackson 2 có thể được đọc bằng hỗ trợ Jackson 3. Nếu ứng dụng tự cấu hình ObjectMapper, chuyển từ SecurityJackson2Modules sang JsonMapper.Builder và SecurityJacksonModules theo hướng dẫn. Nếu cần tiếp tục dùng hỗ trợ Jackson 2 đã deprecated, phải chủ động xử lý dependency Jackson 3 và Jackson 2 theo migration guide.

Khả năng tương thích định dạng mặc định không bảo đảm mọi custom serializer, subtype hoặc database schema của ứng dụng đều tương thích. Sao lưu database trước khi nâng cấp, thử đọc các record đã tạo bằng phiên bản cũ, rồi kiểm tra việc ghi mới và đọc lại bằng phiên bản mới.

Nếu có rolling deployment nhiều instance, không để hai generation dùng chung database trong thời gian dài nếu serialization hoặc transaction behavior chưa được chứng minh tương thích. Chọn cửa sổ nâng cấp, chiến lược deploy và khả năng rollback phù hợp.

## 6. Ma trận kiểm thử sau nâng cấp

| Khu vực | Kiểm tra cần chạy | Điều kiện đạt |
|---|---|---|
| Discovery | Metadata OAuth/OIDC và JWKS | Issuer, endpoint và public key đúng |
| Client registration | Đọc RegisteredClient cũ và tạo client mới | Client ID, grant, scope, redirect URI và authentication method được giữ |
| Authorization Code | Đăng nhập, consent, state và redirect URI | Authorization code chỉ được cấp cho client hợp lệ |
| PKCE | S256 hợp lệ, thiếu challenge, verifier sai | Chính sách PKCE được áp dụng đúng |
| Client Credentials | Client secret hợp lệ và không hợp lệ | Token chỉ được cấp cho client đã xác thực |
| Refresh Token | Refresh, rotation và replay | Token mới/cũ tuân thủ chính sách đã cấu hình |
| OIDC | ID Token, UserInfo, logout nếu được bật | Claim, issuer, signature và endpoint đúng |
| Signing key | Ký JWT và xác minh qua JWKS | Key ID và public key khớp, token cũ vẫn được xử lý theo chính sách |
| Persistence | Đọc dữ liệu cũ, ghi dữ liệu mới, restart | RegisteredClient, authorization và consent vẫn truy xuất được |
| Security chain | Login page, protocol endpoint và API khác | Không có request bị xử lý nhầm chain |

Nên có cả integration test chạy qua HTTP filter chain và test persistence trên database test. Unit test cho token customizer hoặc validator không thay thế được kiểm thử protocol endpoint.

## 7. Kế hoạch triển khai và rollback

Trước khi triển khai production:

1. Tạo bản build có thể lặp lại từ commit đã kiểm tra.
2. Sao lưu database và cấu hình signing key.
3. Kiểm tra issuer, client registration và redirect URI ở môi trường staging.
4. Chạy đầy đủ test authorization, token, refresh, OIDC và persistence.
5. Xác minh Resource Server và client hiện tại tiếp tục xác minh token do Authorization Server mới phát hành.
6. Theo dõi tỷ lệ lỗi token endpoint, invalid_client, invalid_grant, latency và lỗi xác minh chữ ký sau triển khai.

Rollback không chỉ là đổi dependency về version cũ. Nếu phiên bản mới đã ghi dữ liệu theo format khác hoặc đã thay đổi trạng thái authorization, cần biết phiên bản cũ có đọc được dữ liệu đó hay không. Giữ backup và kiểm tra khả năng đọc ngược trong staging. Nếu không bảo đảm được tương thích dữ liệu, dùng chiến lược deploy có điểm khôi phục rõ ràng thay vì chạy hai generation cùng ghi một kho dữ liệu.

Giữ nguyên issuer và signing key theo chính sách vận hành khi chuyển phiên bản. Nếu đồng thời thay issuer hoặc key, client và Resource Server có thể từ chối token đang còn hiệu lực. Hãy tách thay đổi nền tảng khỏi thay đổi trust configuration nếu muốn khoanh vùng rủi ro dễ hơn.

## 8. Các nhầm lẫn cần tránh

- **Nhầm SAS độc lập với Spring Security OAuth cũ:** Spring Authorization Server là dự án kế nhiệm cho Authorization Server thế hệ cũ, không phải chỉ là đổi tên artifact.
- **Nghĩ rằng SAS 1.5.x là một máy chủ riêng:** đây là thư viện được nhúng trong Spring application.
- **Nghĩ rằng chuyển vào Spring Security 7 làm đổi toàn bộ API:** phần lớn class và package được giữ, nhưng có một số package relocation và thay đổi DSL cần xử lý.
- **Đổi artifactId theo phỏng đoán:** artifact trực tiếp giữ groupId và artifactId, version thay đổi theo generation.
- **Chỉ nâng dependency SAS:** Spring Security 7 là major generation, cần nâng đồng bộ các module và xử lý migration của toàn framework.
- **Bỏ qua PKCE mặc định:** client cũ có thể gặp lỗi authorization nếu không đáp ứng chính sách mới.
- **Cho rằng database tự động tương thích:** phải kiểm thử schema, serialized authorization và custom persistence.
- **Đưa Spring Security 6.x và 7.x vào cùng runtime:** tránh classpath có nhiều generation của cùng module.

## 9. Checklist hoàn tất migration

- Đã xác định đúng ứng dụng đang dùng Spring Security OAuth cũ hay Spring Authorization Server 1.x.
- Đã ghi nhận phiên bản Spring Boot, Spring Framework, Spring Security, SAS và Java runtime.
- Đã chọn rõ giữ SAS 1.x tương thích hay chuyển sang Spring Security 7.x.
- Dependency tree chỉ có một generation Authorization Server và Spring Security.
- Authorization Server filter chain dùng DSL phù hợp với generation mới.
- Các package relocation đã được cập nhật dựa trên compiler và tài liệu chính thức.
- PKCE được kiểm thử với public client và các client còn lại.
- RegisteredClient, consent, authorization, token signing và OIDC endpoints hoạt động sau nâng cấp.
- Database và serialized authorization cũ đã được kiểm thử với phiên bản mới.
- Resource Server và OAuth2 Client hiện hữu tiếp tục làm việc với token được cấp.
- Có backup, kế hoạch triển khai và phương án rollback đã được xác minh.

## 10. Tài liệu tham khảo chính thức

- [Spring Authorization Server moving to Spring Security 7.0](https://spring.io/blog/2025/09/11/spring-authorization-server-moving-to-spring-security-7-0/) — thông báo lịch sử, lý do chuyển dự án, Maven coordinates và phạm vi thay đổi package.
- [What’s New in Spring Security 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) — xác nhận Authorization Server là module của Spring Security 7.0 và các thay đổi hành vi liên quan.
- [Spring Security 7.0: Getting Started with Authorization Server](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/authorization-server/getting-started.html) — dependency, starter, filter chain và các bean cần thiết.
- [Spring Security Migration Guide](https://docs.spring.io/spring-security/reference/migration/) — các bước chuẩn bị và chuyển đổi khi nâng cấp generation Spring Security.

Khi hiểu rõ ranh giới giữa dự án SAS độc lập và module Authorization Server trong Spring Security, nhóm phát triển có thể chọn dependency đúng generation, giữ ổn định giao thức và kiểm soát các thay đổi thực sự cần thiết trong quá trình nâng cấp.
