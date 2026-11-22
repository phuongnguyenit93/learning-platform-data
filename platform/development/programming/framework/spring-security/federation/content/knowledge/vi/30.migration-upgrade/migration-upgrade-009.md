# Chạy song song nhà cung cấp cũ và mới mà không trộn khóa hoặc quyền

## 1. Mục tiêu và bối cảnh chuyển đổi

Một ứng dụng sử dụng **Spring Security - federation** có thể cần tiếp tục cho đăng nhập qua nhà cung cấp danh tính cũ trong khi triển khai nhà cung cấp mới. Chuyển đổi thường trải qua **pilot, dual run, canary, cutover, drain và retirement**, thay vì thay toàn bộ cấu hình trong một đêm. Nhưng thêm hai nút đăng nhập không đủ an toàn: người dùng có thể bị nhầm danh tính, token từ issuer này được verify bằng key issuer kia, hoặc các quyền cũ/mới bị cộng dồn.

Bài thuộc nhóm **Chuyển đổi và nâng cấp**, tập trung vào các ranh giới phải giữ:

1. **Mỗi IdP/Authorization Server có issuer/EntityID, verification public keys, metadata/JWKS và client/registration riêng.**
2. **Một SAML Response/OIDC ID Token/JWT phải được xác minh bằng chính trust configuration thuộc provider của nó**, không tìm key trong một global pool từ tất cả IdPs.
3. **Danh tính người dùng phải có provenance:** `(issuer hoặc registration, stable subject, tenant)`. Email, short username hay display name không tự chứng minh hai người là một.
4. **Quyền do application policy cấp**, sau khi identity được liên kết hợp lệ. Không cấp ROLE_ADMIN chỉ vì IdP mới đưa claim `admin`.
5. Callback `state`, OIDC `nonce`, SAML `InResponseTo`, `Recipient`, `Audience`, `Issuer`, chữ ký và thời gian không được bỏ trong giai đoạn migration.
6. Login sessions, authorized clients, refresh tokens, logout và rollback phải giữ đúng provider context, không trộn credentials.
7. Khi nhà cung cấp mới lỗi, fallback chỉ được bắt đầu bằng **authentication flow mới đã được phép**, không dùng token cũ kiểm bằng key khác.

Môi trường minh họa: **Java 17, Spring Boot 3.3.5, Spring Security 6.3.x**. Có thể áp dụng cho migration từ SAML2 sang OIDC, SAML2 sang SAML2 hoặc OIDC sang OIDC. Các host **example.org** và identifiers bên dưới chỉ là ví dụ kỹ thuật.

### Hai provider giả định

~~~text
Legacy Identity Provider:
  alias      = legacy
  issuer     = https://idp-old.example.org/realms/corp
  samlEntity = https://idp-old.example.org/saml
  keys       = LEGACY_VERIFICATION_KEYS

Next Identity Provider:
  alias      = next
  issuer     = https://idp-new.example.org/realms/corp
  samlEntity = https://idp-new.example.org/saml
  keys       = NEXT_VERIFICATION_KEYS

Application:
  public origin = https://app.example.org
  tenant        = corp
  resource aud  = api://orders
~~~

## 2. Ba lớp cách ly: trust, identity và authorization

~~~text
                   Application / Login selector
                              |
                  +-----------+-----------+
                  |                       |
         Legacy registration       Next registration
                  |                       |
           Legacy metadata           Next metadata
           Legacy signing cert       Next signing cert
           Legacy JWKS               Next JWKS
           Legacy client secret      Next client secret
                  |                       |
            VERIFIED ISSUER / SUBJECT / TENANT
                  |                       |
                  +-----------+-----------+
                              |
                     Approved identity link
                              |
                        Local account ID
                              |
                      Local RBAC / ABAC policy
                              |
                       Business permissions
~~~

**Lớp tin cậy (trust):** Public keys chỉ thuộc issuer/registration đã duyệt. Signing certificate của IdP khác, dù còn hạn hay do CA cấp, **không đủ** để verify Response cho một IdP không thuộc sở hữu key đó.

**Lớp nhận diện (identity):** Khi đã verify token/Assertion, mới được dùng stable subject của issuer tương ứng. Với OIDC, cặp **`(iss, sub)`** có ý nghĩa nhận diện. Với SAML, cần **đúng asserting-party registration và stable NameID hoặc immutable attribute** theo contract. Transient NameID có thể không bền.

**Lớp trao quyền (authorization):** Application tra local account/tenant và entitlement policy. Một `roles=admins` hợp lệ về chữ ký chỉ có nghĩa IdP thực sự gửi claim ấy; **không tự cho phép gọi API quản trị**.

### Ví dụ identity links

| Verified nguồn | Stable subject | Tenant | Approved local account |
| --- | --- | --- | --- |
| Legacy SAML, EntityID legacy | `employee-4821` | corp | `account-0042` |
| Next OIDC, issuer next | `7f2b9c` | corp | `account-0042` |
| Next OIDC, issuer next | `employee-4821` | corp | **Chưa liên kết** |
| Next OIDC, issuer next | `7f2b9c` | partner | **Chưa liên kết** |

Hai danh tính đầu trỏ tới cùng account **chỉ sau quy trình approved linking** (ví dụ HR immutable ID, account administrator review, verified dual-login linking). Không dựa vào email, displayName hoặc subject string trùng nhau. Mỗi link nên có status, evidence, approver, timestamps, revocation và policy version.

**Lưu ý:** Legacy và next có thể sử dụng các user directories khác nhau. Cùng email đôi khi là hai chủ thể khác, email có thể đổi hoặc được tái sử dụng. Đừng tạo user mới với quyền của user cũ chỉ bằng so email.

## 3. Bảng registry để quản trị nhiều provider

| Trường | Legacy | Next |
| --- | --- | --- |
| Provider ID nội bộ | `legacy` | `next` |
| SAML registrationId | `legacy-saml` | `next-saml` |
| OIDC registrationId | `legacy-oidc` | `next-oidc` |
| OIDC issuer | Legacy issuer chính xác | Next issuer chính xác |
| SAML IdP EntityID | Legacy EntityID | Next EntityID |
| SAML verification keys | Legacy public certificates | Next public certificates |
| JWKS URL | Legacy trusted JWKS | Next trusted JWKS |
| Client ID/secret | Legacy confidential client | Next confidential client |
| SP EntityID / ACS | Legacy registration values | Next registration values |
| Policy assurance | Legacy MFA/ACR contract | Next MFA/ACR contract |
| Active cohorts | default | pilot |
| IAM owner | legacy team | migration team |
| Lifecycle | enabled, drain, retired | pilot, enabled |

Không cần bật cả hai protocols ở cả hai IdPs. Nếu legacy là SAML và next là OIDC, chỉ tạo hai registrations **tương ứng giao thức thực**, không cấu hình thừa một IdP/OP không có thật.

Provider registry phải được triển khai bằng config/secret store/DB có change approval. Không tạo JWKS URI bằng cách lấy untrusted `iss` rồi nối endpoint tùy ý; có thể gây **SSRF** và token trust injection. Bất kỳ dynamic tenant registration nào cũng cần allowlist hoặc nguồn định danh được phê duyệt.

## 4. SAML2: tách RelyingPartyRegistration theo từng IdP

Spring Security biểu diễn một cặp **SP–IdP** bằng `RelyingPartyRegistration`. Với hai IdP, phải có hai registrations và mỗi registration có **IdP EntityID/SSO endpoint/trusted signing certificates** tương ứng. `registrationId` chỉ là mã định tuyến, không thay cryptographic issuer validation.

### 4.1. Endpoint thông thường

~~~text
GET  /saml2/authenticate/legacy-saml
GET  /saml2/authenticate/next-saml

POST /login/saml2/sso/legacy-saml
POST /login/saml2/sso/next-saml

GET  /saml2/metadata/legacy-saml
GET  /saml2/metadata/next-saml
~~~

Spring có thể hỗ trợ ACS không có registrationId nếu lookup từ request state/response issuer. Trong migration, đường có `registrationId` rõ ràng giúp trace/correlation. Tuy nhiên URL path chưa chứng minh issuer: Response phải được verify qua đúng IdP signing cert, Issuer và AudienceRestriction, Recipient/Destination, time và InResponseTo.

### 4.2. Spring Boot 3.3.5 YAML chính xác cho hai IdPs

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          legacy-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/legacy-saml"
            assertingparty:
              entity-id: "https://idp-old.example.org/saml"
              sso-url: "https://idp-old.example.org/saml/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:trust/legacy-idp-signing.pem"

          next-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/next-saml"
            assertingparty:
              entity-id: "https://idp-new.example.org/saml"
              sso-url: "https://idp-new.example.org/saml/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:trust/next-idp-signing.pem"
~~~

Đây là ví dụ Boot configuration trên cơ sở hỗ trợ nhiều registrations. Các public certificate PEM phải được lấy từ **trusted IdP metadata/approved inventory** và fingerprint được IAM xác nhận. Không đưa private keys vào classpath mà không có secret lifecycle; trên production ưu tiên secret volumes/managed credentials với quyền chặt.

**Không dùng một `verification.credentials` pool chứa certificates của cả hai IdPs trong cả hai registrations.** Nếu cần trust old và new signing certificates **trong quá trình IdP legacy tự xoay keys**, cả hai certificates có thể thuộc **legacy** trong approved overlap, chứ không lấy certificate của next làm candidate.

Còn phải cấu hình với hai IdPs:
- SP EntityID và ACS URL chính xác theo registration; IdP phải cấp Assertion cho đúng SP/audience.
- Signed AuthnRequest nếu IdP yêu cầu, dùng SP signing private key cùng certificate đăng ký tại đúng IdP.
- EncryptedAssertion nếu dùng, có SP decryption private key đúng registration, khác IdP signing verification key.
- Logout URLs/SessionIndex/issuer ký đúng provider; không chuyển SLO giữa IdPs.
- Metadata refresh/repository cache độc lập từng IdP và key fingerprints/rotation có audit.

### 4.3. SecurityFilterChain để Spring xử lý SAML

Đây là snippet cho **một ứng dụng SAML2-only** đã có dependencies `spring-boot-starter-security` và `spring-security-saml2-service-provider`, file YAML/certificate phù hợp:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/choose-idp").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Boot tạo `RelyingPartyRegistrationRepository` từ YAML khi không bị bean khác override. Nếu tự triển khai `InMemoryRelyingPartyRegistrationRepository`, phải chứa cả legacy và next registrations. Static repository dựng từ metadata tại startup **không mặc nhiên tự refresh** khi IdP đổi certificate; có kế hoạch rebuild/cache refresh và kiểm từng node.

**Cross-provider SAML negative test:** gửi Response next-signed tới legacy ACS; phải fail vì issuer/trust/correlation. Gửi Response có signed Assertion hợp lệ nhưng audience là SP legacy vào next registration; phải fail. Không chấp nhận untrusted `<ds:KeyInfo>` certificate do Response mang tới. Không tự parse XML rồi cấp principal khác signed element (XML Signature Wrapping).

### 4.4. SP-initiated và IdP-initiated

Trong giai đoạn song song, ưu tiên **SP-initiated login** để có AuthnRequest/state và registration rõ ràng. IdP-initiated SSO không có AuthnRequest tương ứng, nên có profile và login-CSRF considerations riêng; không nới `InResponseTo`/Issuer/Recipient checks để cho flow chưa được review chạy. Dù cho phép IdP-initiated theo contract, key isolation và SAML signature vẫn bắt buộc.

## 5. OIDC: hai ClientRegistration với state/nonce riêng

### 5.1. OAuth2/OIDC flow khi có hai issuer

~~~text
User chọn legacy:
  /oauth2/authorization/legacy-oidc
  -> legacy authorization endpoint
  -> /login/oauth2/code/legacy-oidc
  -> token endpoint legacy
  -> ID Token verified with legacy issuer/JWKS and legacy client_id

User chọn next:
  /oauth2/authorization/next-oidc
  -> next authorization endpoint
  -> /login/oauth2/code/next-oidc
  -> token endpoint next
  -> ID Token verified with next issuer/JWKS and next client_id
~~~

Mỗi flow có OAuth authorization request được server lưu, **`state` chống CSRF**, OIDC **`nonce` để chống token replay/mix-up** khi profile sử dụng, PKCE theo client/profile, redirect URI registered và issuer/client ID đúng. **Không giải mã ID Token next bằng legacy client registration** khi callback path bị đổi.

### 5.2. Spring Boot 3.3.5 YAML

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-oidc:
            provider: legacy-provider
            client-id: "legacy-web-client"
            client-secret: "${LEGACY_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          next-oidc:
            provider: next-provider
            client-id: "next-web-client"
            client-secret: "${NEXT_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]

        provider:
          legacy-provider:
            issuer-uri: "https://idp-old.example.org/realms/corp"
          next-provider:
            issuer-uri: "https://idp-new.example.org/realms/corp"
~~~

Mỗi secret phải thuộc một client ở đúng OP, lấy từ secret manager/môi trường đã quản trị; không copy secret legacy cho next. Issuer URI phải chính xác theo trusted discovery, không tự thêm client-supplied hostname, query string hoặc trailing slash. URLs trên là placeholder kỹ thuật, không là endpoints thật.

### 5.3. OIDC login SecurityFilterChain

~~~java
package com.example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/choose-idp").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Với một ứng dụng cần **đồng thời SAML2 login và OAuth2 login**, không copy hai `SecurityFilterChain` catch-all cùng matcher vào một app rồi kỳ vọng Spring chọn đúng. Có thể dùng một chain cấu hình cả `.saml2Login(...)` và `.oauth2Login(...)`, hoặc nhiều chains có `@Order`/`securityMatcher` rõ. Kiểm callbacks bị chặn bởi chain khác, session cookie và CSRF.

### 5.4. Provenance sau OIDC authentication

Trong Spring Security 6.3, **`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()`** cho biết client registration nào đã được dùng. Với verified OIDC user, cần thêm issuer của ID Token và stable subject, rồi tra local identity link. Không lấy `provider` từ query parameter hoặc một attribute chưa verify để gán vào `SecurityContext`.

Một ví dụ conceptual:

~~~text
protocol             = OIDC
registration         = next-oidc
verified_issuer      = https://idp-new.example.org/realms/corp
verified_sub         = 7f2b9c
tenant               = corp
local_account_id     = account-0042
effective_permissions= ORDERS_READ
~~~

Các trường trên là **mô hình nội bộ**, không phải claims Spring tự log. Tất cả được tính sau signature/issuer/audience/state/nonce validation. OIDC ID Token audience phải là **web client_id**, không phải `api://orders` của business API.

## 6. API JWT: issuer-specific keysets, không một global JWKS

Trong một migration API có thể tạm thời chấp nhận access tokens từ hai Authorization Servers. Việc chấp nhận hai issuers **không có nghĩa** chấp nhận token có signature hợp lệ từ bất kỳ public key nào của hai bên.

~~~text
Incoming Bearer JWT
     |
Parse unverified iss for exact allowlist lookup ONLY
     |
     +-- old issuer -> OLD decoder -> OLD JWKS, old alg policy
     |
     +-- new issuer -> NEW decoder -> NEW JWKS, new alg policy
     |
Verify signature WITH SELECTED ISSUER KEYSET
Check iss exactly, aud=api://orders, exp/nbf, token type
     |
Verified (issuer, sub, tenant) -> approved link -> local roles
     |
Resource authorization
~~~

`kid` có thể trùng ở hai issuers. Không viết `Map<String kid, PublicKey>` global; key selector phải nằm trong **issuer-scoped trusted decoder**. JWT header `jku`/`x5u` do token khai không được dùng để tải arbitrary key URL. Nếu JWT có `iss=old` nhưng chữ ký từ private key của next, old decoder phải reject.

### 6.1. Cấu hình đơn giản từ Spring Security 6.3

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-old.example.org/realms/corp",
        "https://idp-new.example.org/realms/corp");

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
~~~

Đoạn này là **fragment**, không phải đầy đủ app. Resolver chỉ coi hai issuer là trusted; việc đọc `iss` trước xác minh được dùng cho **routing vào allowlist**, rồi decoder của issuer đó xác minh signature/issuer/time. Còn phải validate **API audience**, token type và authorization. Nếu dynamic tenant registration, chỉ thêm issuer sau admin approval, không dùng token input để auto-create decoder.

### 6.2. Full per-issuer Spring Resource Server Java config

Ứng dụng API riêng có Maven dependencies:
- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-oauth2-resource-server`

Cấu hình dưới dùng **hai known JWKS URIs riêng và hai decoders riêng**, mặc định chấp nhận **RS256** theo minh họa. Thay URLs bằng `jwks_uri` thật từ trusted discovery và điều chỉnh algorithm theo approved policy. Không dùng code này như endpoint nhận ID Tokens từ web.

**MultiIssuerApiSecurity.java**:

~~~java
package com.example.api;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerApiSecurity {
    private static final String OLD =
        "https://idp-old.example.org/realms/corp";
    private static final String NEXT =
        "https://idp-new.example.org/realms/corp";
    private static final String AUD = "api://orders";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> resolver() {
        Map<String, AuthenticationManager> approved = Map.of(
            OLD, newManager(OLD,
                "https://idp-old.example.org/realms/corp/keys"),
            NEXT, newManager(NEXT,
                "https://idp-new.example.org/realms/corp/keys"));
        return new JwtIssuerAuthenticationManagerResolver(approved::get);
    }

    private static AuthenticationManager newManager(
            String issuer, String trustedJwksUri) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(AUD)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer), audience));

        JwtAuthenticationConverter authorityConverter =
            new JwtAuthenticationConverter();
        authorityConverter.setJwtGrantedAuthoritiesConverter(
            jwt -> localAuthorities(jwt));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        provider.setJwtAuthenticationConverter(authorityConverter);
        return provider::authenticate;
    }

    private static Collection<GrantedAuthority> localAuthorities(
            Jwt verifiedJwt) {
        String issuer = verifiedJwt.getIssuer().toString();
        String sub = verifiedJwt.getSubject();

        // Demo only: approved links của hai identities.
        boolean linked =
            (OLD.equals(issuer) && "old-user-17".equals(sub))
            || (NEXT.equals(issuer) && "new-sub-98".equals(sub));

        if (!linked) return List.of();
        return List.of(new SimpleGrantedAuthority("ORDERS_READ"));
    }

    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders").hasAuthority("ORDERS_READ")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver));
        return http.build();
    }
}
~~~

**Giới hạn của mẫu code:**

- JWKS URLs `/keys` chỉ là **ví dụ**; các sản phẩm OP khác có endpoint khác. Chỉ dùng URI thực theo issuer discovery/approved configuration.
- `JwtValidators.createDefaultWithIssuer` giữ `iss` và `exp/nbf` checks; thêm custom aud validator, không thay default validators.
- Nếu new issuer đưa role `admin` trong signed JWT, converter vẫn chỉ cấp `ORDERS_READ` theo approved local link. Production thay hardcoded map bằng identity-link DB và permission service, có tenant, role revocation, step-up và audit.
- Unknown subjects vẫn có thể được framework authenticated nếu chữ ký/claims hợp lệ, nhưng không có local business permission; API `/api/orders` từ chối. Nếu policy đòi reject tất cả unlinked accounts ở authentication layer, cần thêm explicit reject logic.
- Đoạn code là full Spring bean config **cho một API app**; không copy cùng các web SAML/OIDC catch-all chains nếu chưa thiết kế `securityMatcher`.
- JWKS fetch/cache phải tách theo issuer; không fallback sang keyset khác khi lỗi.
- Header `iss`/`kid` chưa verify chỉ dùng làm key selection trong known registry; final signature và claim validation mới quyết định Authentication.
- Thiết kế token type check riêng để tránh **JWT access token vs OIDC ID Token confusion**. Audience validation một mình không thể chứng minh token purpose nếu issuer/token formats không đủ phân biệt.

## 7. Java 17 runnable: mô phỏng tách khóa và local privileges

Chương trình dưới đây dùng **RSA SHA256 signature thật** cho hai keypairs nhưng **không phải SAML/JWT verifier**. Nó ký một cấu trúc demonstration được nối bằng dấu `|`, không có chuẩn JOSE/canonicalization; **không dùng serialization này trong production**. Nhiệm vụ của nó là cho thấy verifier phải chọn key theo issuer, tiếp tục kiểm aud/time/tenant và chỉ dùng **approved local identity links** để cấp quyền.

**ParallelProviderLab.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Map;
import java.util.Set;

public class ParallelProviderLab {
    static final String OLD =
        "https://idp-old.example.org/realms/corp";
    static final String NEXT =
        "https://idp-new.example.org/realms/corp";
    static final String AUDIENCE = "api://orders";
    static final long NOW = 2_000_000_000L;

    record Provider(String code, PublicKey key, String tenant) {}
    record Account(String id, Set<String> permissions) {}
    record Message(String issuer, String audience, String subject,
                   String tenant, String claimedRole, long expiresAt,
                   byte[] signature) {
        String dataForDemo() {
            return String.join("|", issuer, audience, subject,
                tenant, claimedRole, Long.toString(expiresAt));
        }
    }

    static Message signed(String issuer, String audience, String subject,
            String tenant, String claimedRole, long expires,
            PrivateKey key) throws GeneralSecurityException {
        Message unsigned = new Message(issuer, audience, subject,
            tenant, claimedRole, expires, new byte[0]);

        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(key);
        sig.update(
            unsigned.dataForDemo().getBytes(StandardCharsets.UTF_8));
        return new Message(issuer, audience, subject, tenant,
            claimedRole, expires, sig.sign());
    }

    static String validate(Message m, Map<String, Provider> providers,
            Map<String, Account> links, String permission)
            throws GeneralSecurityException {
        Provider p = providers.get(m.issuer());
        if (p == null) return "REJECT UNKNOWN_ISSUER";

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(p.key());
        signature.update(
            m.dataForDemo().getBytes(StandardCharsets.UTF_8));
        if (!signature.verify(m.signature())) {
            return "REJECT WRONG_PROVIDER_KEY";
        }

        if (!AUDIENCE.equals(m.audience()))
            return "REJECT AUDIENCE";
        if (NOW >= m.expiresAt())
            return "REJECT EXPIRED";
        if (!p.tenant().equals(m.tenant()))
            return "REJECT TENANT";

        String identity = p.code() + "|" + m.subject()
            + "|" + m.tenant();
        Account a = links.get(identity);
        if (a == null) return "REJECT UNLINKED_SUBJECT";

        // Role trong token không tự biến thành application role.
        if (!a.permissions().contains(permission))
            return "DENY LOCAL_PRIVILEGE";
        return "ALLOW " + a.id() + " " + permission;
    }

    static void show(String label, Message m,
            Map<String, Provider> trust, Map<String, Account> links,
            String permission) throws GeneralSecurityException {
        System.out.println(label + ": " +
            validate(m, trust, links, permission));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        KeyPair oldKey = g.generateKeyPair();
        KeyPair nextKey = g.generateKeyPair();

        Map<String, Provider> trust = Map.of(
            OLD, new Provider("old", oldKey.getPublic(), "corp"),
            NEXT, new Provider("next", nextKey.getPublic(), "corp"));

        Account employee = new Account(
            "account-0042", Set.of("ORDERS_READ"));
        Map<String, Account> links = Map.of(
            "old|old-user-17|corp", employee,
            "next|new-sub-98|corp", employee);

        Message oldOk = signed(
            OLD, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, oldKey.getPrivate());
        Message nextOk = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        Message claimsAdmin = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "ADMIN",
            NOW + 300, nextKey.getPrivate());

        show("old valid", oldOk, trust, links, "ORDERS_READ");
        show("next linked", nextOk, trust, links, "ORDERS_READ");
        show("new claims admin", claimsAdmin, trust, links,
            "ORDERS_READ");
        show("admin endpoint", claimsAdmin, trust, links, "ADMIN");

        Message unknown = signed(
            "https://evil.example.org", AUDIENCE, "old-user-17",
            "corp", "reader", NOW + 300, oldKey.getPrivate());
        show("unknown issuer", unknown, trust, links, "ORDERS_READ");

        Message crossKey = signed(
            OLD, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        show("cross provider key", crossKey, trust, links, "ORDERS_READ");

        Message sameName = signed(
            NEXT, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        show("same subject unlinked", sameName, trust, links,
            "ORDERS_READ");

        Message modified = new Message(
            NEXT, AUDIENCE, "new-sub-98", "corp", "ADMIN",
            NOW + 300, nextOk.signature());
        show("tampered role", modified, trust, links, "ORDERS_READ");

        Message wrongAud = signed(
            OLD, "api://other", "old-user-17", "corp", "reader",
            NOW + 300, oldKey.getPrivate());
        show("wrong audience", wrongAud, trust, links, "ORDERS_READ");

        Message wrongTenant = signed(
            NEXT, AUDIENCE, "new-sub-98", "partner", "reader",
            NOW + 300, nextKey.getPrivate());
        show("wrong tenant", wrongTenant, trust, links, "ORDERS_READ");

        Message expired = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "reader",
            NOW - 1, nextKey.getPrivate());
        show("expired", expired, trust, links, "ORDERS_READ");
    }
}
~~~

Chạy độc lập trên Java 17:

~~~bash
javac ParallelProviderLab.java
java ParallelProviderLab
~~~

**Stdout chính xác** khi chạy trong JDK 17 bình thường; RSA keypairs được sinh ngẫu nhiên nhưng kết quả luôn nhất quán:

~~~text
old valid: ALLOW account-0042 ORDERS_READ
next linked: ALLOW account-0042 ORDERS_READ
new claims admin: ALLOW account-0042 ORDERS_READ
admin endpoint: DENY LOCAL_PRIVILEGE
unknown issuer: REJECT UNKNOWN_ISSUER
cross provider key: REJECT WRONG_PROVIDER_KEY
same subject unlinked: REJECT UNLINKED_SUBJECT
tampered role: REJECT WRONG_PROVIDER_KEY
wrong audience: REJECT AUDIENCE
wrong tenant: REJECT TENANT
expired: REJECT EXPIRED
~~~

**Diễn giải các negative cases:**

- Token tuyên bố `issuer=old` nhưng ký bằng private key next bị reject vì public key phải lấy từ registry old.
- Subject `old-user-17` ở issuer next không tự có account link dù chuỗi subject giống old.
- Next signer ký hợp lệ claim `ADMIN`, nhưng local policy chỉ cho ORDERS_READ nên admin endpoint bị deny.
- Một signed token có audience/tenant/time không đúng vẫn bị reject sau khi chữ ký pass.
- Thay role sau khi ký làm chữ ký sai.
- Mã này chỉ làm rõ trust and policy model; không thay thế SAML XML-DSig, JWT/JWS parser, PKIX, nonce, InResponseTo, scopes, cookie session hoặc IdP SSO integration.

## 8. Role mapping và privilege isolation

Bất kỳ người dùng nào chuyển từ legacy sang next đều cần **effective authority mapping được phê duyệt**, không chỉ kiểm login success.

| Verified issuer | External group/claim | Local quyền đề xuất | Điều kiện |
| --- | --- | --- | --- |
| Legacy | `groups=CN=OrdersRead` | `ORDERS_READ` | Linked active account, tenant corp. |
| Next | `roles=orders-reader` | `ORDERS_READ` | IAM migration mapping approved. |
| Legacy | `groups=CN=OrdersAdmin` | `ORDERS_ADMIN` | Privileged review, MFA/step-up. |
| Next | `roles=admins` | **Không auto-map** | Kiểm group semantics/approval riêng. |
| Next | `email=alice@example.org` | **Không cấp quyền** | Email không phải entitlement. |

Một IdP có thể xác nhận thuộc tính nhưng không tự có thẩm quyền cấp quyền ứng dụng. Nếu được phép dùng nhóm làm nguồn entitlement, mapping phải bao gồm **provider issuer, claim namespace/value, tenant, application, permission, approval và expiry**. Quyền nhạy cảm nên từ local IAM/IGA hoặc policy engine có kiểm soát.

**Không union authorities giữa sessions:** Người dùng login bằng old IdP có admin rights theo policy cũ rồi chuyển sang next reader; app phải tái tính effective permissions từ local account/current policy. Không giữ ROLE_ADMIN trong SecurityContext chỉ vì nó từng xuất hiện trong session trước.

Account linking phải có chống chiếm quyền: tài khoản bị disable ở legacy hoặc next không được tự phục hồi bằng email trùng; reset password ở IdP mới không tự chứng minh ownership của account legacy; privileged linking cần re-verification.

## 9. Routing migration và chống mix-up

### 9.1. Pilot / canary feature flags

Có thể dùng server-side cohort selector:

~~~text
tenant=corp, cohort=default -> legacy
tenant=corp, cohort=pilot   -> next
tenant=corp, approvedUserChoice=true -> one of allowlisted providers
~~~

Một query parameter `provider=next` chỉ là **yêu cầu bắt đầu flow qua known registration**, không phải lệnh thay JWKS URI, EntityID hay quyền. Trước redirect, lưu original registration và `state`/nonce hoặc SAML AuthnRequest ID/correlation theo session/TTL. Sau callback, phải verify chính original registration đó **dù feature flag đã thay đổi giữa hai thời điểm**.

Nếu tenant routing dựa vào subdomain hoặc proxy headers, chỉ tin host/Forwarded headers sau khi reverse proxy strip user-supplied headers và app kiểm approved hostname allowlist. Sau authentication vẫn phải kiểm tenant của local account; host header không tạo quyền.

### 9.2. Login fail không đồng nghĩa thử nhà cung cấp còn lại với cùng token

Khi next token signature fail hoặc `state` mismatch, **không** chạy decoder old để “thử may”. Nếu policy cho fallback, app chỉ đưa user trở lại login chooser và bắt đầu **flow mới** với AuthnRequest/state/code riêng. Không dùng lại SAMLResponse, OAuth authorization code, CAS single-use ticket hoặc access token dưới provider khác.

### 9.3. OIDC issuer mix-up

Khi hai OPs cùng phục vụ một RP, phải ràng buộc endpoint trả authorization response với **issuer và client registration đã chọn trước khi redirect**, rồi validate code/ID Token bằng đúng OP. Dù `state` được kiểm, cần xử lý issuer mix-up theo OAuth/OIDC profile và provider support. Không tạo redirect URI động từ untrusted input hoặc cho callback code được exchange ở token endpoint khác.

### 9.4. MFA/assurance

Legacy có thể dùng phishing-resistant MFA còn next chỉ password; không được coi account migration tự bảo toàn assurance. Gắn local sensitive operations với approved MFA/ACR/AMR policy và verified provider claims. Nếu assurance của next chưa đạt, vẫn có thể cho low-risk login nhưng không cấp privileged action.

## 10. Session, tokens và logout khi hai IdP hoạt động

Phân biệt ba lớp session:

~~~text
Legacy IdP SSO session          Next IdP SSO session
          \                              /
           \                            /
                  Application HttpSession
                   Spring SecurityContext

OAuth2 authorized clients:
  legacy-oidc client -> legacy access/refresh tokens
  next-oidc client   -> next access/refresh tokens
~~~

**Local logout** có thể invalidate Spring HttpSession nhưng không mặc nhiên logout cả hai IdP browser sessions. OIDC RP-initiated logout phải dùng đúng issuer end_session_endpoint/ID Token hint/redirect contract; SAML Single Logout cần đúng registration, signed request/response, SessionIndex. Không gửi next refresh token tới legacy token endpoint.

Các quy tắc vận hành:

1. Lưu verified authentication provenance ở server-side session: protocol, provider alias, issuer, local account link, tenant và policy version.
2. Khi switch provider, không cộng quyền cũ vào quyền mới; tái tạo Authentication và thay đổi session ID theo session fixation protection.
3. Lưu/đọc OAuth2 authorized clients theo đúng client registration. Khi unlink/revoke provider, dọn tokens/cookies liên quan theo policy.
4. `remember-me` hoặc persistent login nếu có phải được audit; không tự tái tạo account có quyền cao từ provider đã retire.
5. Cookie Secure, HttpOnly, SameSite/CSRF state, HTTPS proxy và callback paths phải đúng. Không bỏ CSRF chỉ vì IdP đã ký assertion.
6. Nếu có active sessions từ old trước cutover, ra quyết định **giữ đến TTL hay revoke bắt đăng nhập lại**, không tự xem disable login route là đã revoke session.
7. Trên nhiều nodes, session store đồng nhất, metadata/JWKS cache versions được quan sát và không có authorization stale policy.
8. Logout global phải do đúng OP/IdP hỗ trợ; app không tự tuyên bố workstation/IdP đã logout toàn bộ.
9. Tách token type: OIDC ID Token dành cho RP; JWT access token dành cho API, có aud/resource policy riêng.
10. Nếu signing private key của một issuer bị compromise, đánh giá revoke sessions/tokens liên quan, không giữ shared authorities indefinite.

## 11. Key rotation trong mỗi IdP khác migration hai IdPs

Phân biệt:

~~~text
Planned rollover thuộc legacy issuer:
  legacy -> [legacy-sign-v1, legacy-sign-v2]

Planned rollover thuộc next issuer:
  next   -> [next-sign-v1, next-sign-v2]

Sai:
  legacy -> [legacy-sign-v1, next-sign-v1]
  next   -> [legacy-sign-v1, next-sign-v1]
~~~

Một IdP có thể publish old+new public keys trong approved overlap window trước khi đổi signing private key. **Overlap đó chỉ nằm trong cùng trusted issuer/registration.** Không lấy key từ next để verify Response/token claiming issuer old.

Đừng dùng chung private signing key giữa hai IdPs nếu không có security architecture phê duyệt: tăng blast radius compromise và làm mất crypto isolation. Nếu cùng `kid`, hai JWK Sets vẫn phải ở namespace issuer riêng. Nếu một node có cached metadata cũ, node khác metadata mới, phải cập nhật theo planned refresh/rollout, không nới trust sang tất cả keys của mọi provider.

## 12. Giai đoạn chuyển đổi và quality gates

### Giai đoạn 0 — Inventory

Ghi owner, SAML EntityID/metadata, OIDC issuer/client IDs, signing cert fingerprints, JWKS URIs, SP EntityID/ACS, redirect URIs, logout, service accounts, API audiences, group mapping, local account store, session TTL, MFA và clients chưa hỗ trợ new OP. Không xuất private keys/secrets ra bảng inventory.

### Giai đoạn 1 — Shadow provisioning / test

Tạo next client/registration bên IdP mới, import approved public verification credentials, test signed fixtures. Xây identity-link table và local authority policy, đặc biệt privileged users. Mọi test nên nằm ở sandbox với keypairs riêng.

### Giai đoạn 2 — Pilot

Chỉ định cohort được phép qua next, giữ default legacy. So local account ID/permissions của cùng người dùng đã được linked, không chỉ username/email. Kiểm callback loops, browser policies, session handling và MFA assurance.

### Giai đoạn 3 — Canary ramp

Tăng tỷ lệ cho user mới theo các đợt (ví dụ 1% → 5% → 25% → 50% → 100%, **không có tỷ lệ bắt buộc**). Mỗi đợt chỉ mở rộng nếu:
- Login success rate và latency đạt SLO.
- **Cross-provider token acceptance bằng 0.**
- **Unlinked subject có business permission bằng 0.**
- Privileged role drift không có sự tăng ngoài approvals.
- State/nonce/InResponseTo/audience/issuer negative tests vẫn reject.
- Có rollback route an toàn và alerts.

### Giai đoạn 4 — Cutover default

Đổi default cho **login mới** sang next, không đổi registration của callbacks đang pending. Giữ legacy cho cohorts được phê duyệt nếu chưa hoàn tất migrating service accounts, old browser integrations, admin workflows hoặc session drain.

### Giai đoạn 5 — Drain/retire legacy

Lập deadline cho old login, JWT issuance và app sessions/tokens. Thống nhất TTL/revocation behavior. Sau khi tất cả clients đã chuyển, remove legacy issuer khỏi API trust allowlist, gỡ legacy SAML registration/metadata/keys, thu hồi client secret và IdP integration theo change approval. Không giữ trust/key/privilege fallback lâu vô hạn.

## 13. Rollback không phải trộn khóa

Khi next IdP xảy ra outage, rollback an toàn là chuyển **new login routing** về legacy theo approval, không cho legacy verifier chấp nhận next signed token. Một bản runbook:

1. Freeze rollout, xác định thời điểm và cohorts, mã lỗi, node/region.
2. Phân loại lỗi: trust/key mismatch, redirect/state, identity link, role mapping, IdP availability.
3. Khôi phục default login route về legacy nếu legacy còn trusted/operational và policy cho phép.
4. Các callbacks đã pending vẫn phải check original registration/state; không ép qua provider mới bằng flag.
5. Xử lý next sessions hiện hữu theo risk: invalidate/re-authenticate hoặc giữ đến TTL nếu policy cho phép.
6. Không merge audiences, keys, issuer allowlists hay privileged roles.
7. Chạy smoke + negative tests và kiểm business permissions.
8. Ghi audit, RCA, corrective actions và điều kiện tiếp tục canary.

Nếu rollback do **private signing key compromise** ở next issuer, phải revoke trust/key theo incident policy và xử lý impacted sessions; không được dùng lý do availability để giữ compromised issuer/key.

## 14. Ma trận kiểm thử SAML, OIDC, JWT và quyền

Nên dùng **synthetic signed fixtures**: để test issuer/audience validator độc lập, tạo message/token được ký hợp lệ nhưng có issuer/audience không đúng. Nếu sửa payload sau khi ký, signature sẽ fail trước và chưa chứng minh claim validator.

| # | Kịch bản | Kết quả an toàn |
| --- | --- | --- |
| 1 | Legacy SAML signed đúng issuer/ACS/conditions | Pass, local policy cho phép. |
| 2 | Next SAML signed đúng issuer/ACS/conditions | Pass. |
| 3 | Next SAMLResponse gửi vào legacy ACS | Reject cross-provider. |
| 4 | Legacy SAMLResponse gửi vào next ACS | Reject cross-provider. |
| 5 | SAML signed đúng nhưng AudienceRestriction sai | Reject. |
| 6 | SAML Recipient/Destination sai | Reject. |
| 7 | SAML InResponseTo không khớp AuthnRequest | Reject. |
| 8 | SAML Assertion replay | Reject. |
| 9 | SAML NameID bị sửa sau ký | Reject signature. |
| 10 | XML Signature Wrapping: signed Alice, unsigned Mallory | Không cấp Mallory principal. |
| 11 | Attacker X509 certificate trong SAML KeyInfo | Không tự trust. |
| 12 | Legacy ký bằng rollover key legacy được approved | Pass trong overlap. |
| 13 | Next public key thêm nhầm vào legacy trust | Security QA FAIL. |
| 14 | IdP-initiated SAML chưa được policy phê duyệt | Reject/unavailable, không bỏ checks. |
| 15 | OIDC login legacy đúng issuer/client_id/nonce | Pass. |
| 16 | OIDC login next đúng issuer/client_id/nonce | Pass. |
| 17 | Callback legacy dùng state next | Reject. |
| 18 | Callback next dùng authorization code legacy | Reject. |
| 19 | OIDC ID Token có issuer đúng nhưng aud của client khác | Reject. |
| 20 | OIDC nonce không khớp | Reject. |
| 21 | Provider URL do client cung cấp, ngoài allowlist | Reject routing. |
| 22 | Feature flag đổi giữa redirect và callback | Giữ original registration/correlation. |
| 23 | JWT legacy signed old key, iss old, aud API đúng | Pass nếu local entitlement cho phép. |
| 24 | JWT next signed new key, iss next, aud API đúng | Pass nếu local entitlement cho phép. |
| 25 | JWT `iss=old` ký bằng next private key | Reject. |
| 26 | JWT `iss=next` ký bằng old private key | Reject. |
| 27 | JWT issuer chưa allowlist | Reject; không tạo arbitrary decoder. |
| 28 | JWT kid trùng ở old và next | Chỉ chọn key thuộc issuer đã allowlist. |
| 29 | JWT jku trỏ attacker host | Không download arbitrary JWKS. |
| 30 | JWT alg=none hoặc không được phép | Reject. |
| 31 | JWT aud của API khác | Reject dù signature đúng. |
| 32 | JWT exp hết hạn hoặc nbf future | Reject time. |
| 33 | JWKS new issuer lỗi timeout | Không fallback sang old signing keys. |
| 34 | Hai IdPs có cùng email nhưng chưa linked | Không auto merge account. |
| 35 | Hai issuers có cùng short subject | Không coi là một identity. |
| 36 | Approved link old/new tới một local account | Permissions consistent theo local policy. |
| 37 | New provider gửi role Admin | Không tự cấp ROLE_ADMIN. |
| 38 | Legacy admin đăng nhập rồi next reader login | Không union old+new authorities. |
| 39 | Next subject verified nhưng chưa link | Không nhận ORDERS_READ. |
| 40 | Tenant corp identity truy cập partner resource | Deny tenant. |
| 41 | Old refresh token gửi tới next token endpoint | Reject. |
| 42 | OAuth authorized clients lưu old/new tokens | Đúng registration, không reuse lẫn. |
| 43 | SAML SLO legacy tác động session next | Không được coi request cross-provider là trusted. |
| 44 | Logout app nhưng IdP sessions còn | Không tuyên bố global logout. |
| 45 | Next outage, fallback legacy được phê duyệt | Flow mới, state/nonce mới. |
| 46 | Rollback default route | Key/issuer isolation giữ nguyên. |
| 47 | Legacy JWT sau khi retire issuer khỏi API trust | Reject. |
| 48 | Private signing key next bị compromise | Revoke đúng issuer, review sessions. |
| 49 | Pod A và B có metadata/JWKS khác phiên bản | Phát hiện và sửa cache parity. |
| 50 | Raw SAMLResponse/JWT/secret xuất hiện trong logs | Security QA FAIL. |
| 51 | Local account bị disabled dù identity valid | Deny. |
| 52 | Verified identity thiếu local business role | 403/deny. |
| 53 | Host/Forwarded headers giả để đổi tenant | Không vượt trusted routing + post-auth tenant checks. |
| 54 | Callback/auth code bị replay | Reject. |
| 55 | New issuer MFA thấp hơn requirement admin | Step-up/deny privileged action. |

**Nghiệm thu phải dựa vào cả negative cases**, không chỉ login success. Cross-issuer acceptance và privilege escalation là lỗi dừng rollout ngay.

## 15. Troubleshooting

| Hiện tượng | Hướng điều tra |
| --- | --- |
| Next SAML chữ ký không hợp lệ | Next EntityID, trusted signing public cert, metadata refresh; không lấy legacy cert. |
| SAMLResponse đi sai ACS | IdP callback registration, SP EntityID, reverse proxy, correlation. |
| OIDC callback invalid state | Session cookie, state repository, wrong registration, feature flag thay giữa flow. |
| OIDC ID Token aud mismatch | Client ID/registration bị trộn. |
| JWT issuer unknown | Exact allowlist, không dùng arbitrary JWT claim làm issuer config. |
| JWT invalid signature dù kid giống nhau | Kiểm issuer-specific JWKS, key bytes/rotation/cache. |
| JWT valid nhưng API 403 | Approved account link/entitlements/tenant; không tự mở wildcard roles. |
| Cùng email login thành tài khoản khác | Không auto-link bằng email; kiểm immutable ID và approved links. |
| Admin role tăng sau migration | Role converter, group mapping namespace, stale SecurityContext. |
| Session old còn sống sau next login | Session lifecycle và authorities union, invalidate/reauth. |
| Chỉ một node next login fail | Cache/metadata/keyset parity, SSL trust, deployment. |
| Logout next không logout legacy | Hai IdP sessions độc lập, SLO contract riêng. |
| Rollback gây login loop | Pending state/nonce, cookie SameSite, correct issuer callback. |

## 16. Observability và audit

Nên ghi **sau khi authentication được xác minh**, không ghi raw assertion/token:

~~~text
event=federation.authentication.completed
trace_id=trace-demo-a91
protocol=OIDC
provider_alias=next-oidc
issuer_alias=next
client_registration=next-oidc
tenant=corp
local_account_id=account-0042
identity_link_version=v3
entitlement_policy_version=policy-2026-11
result=SUCCESS
~~~

Các giá trị chỉ minh họa, không phải Spring auto logs. Không ghi raw SAMLResponse, ID Token, JWT access token, refresh token, cookies, private keys, full group attributes, DN hoặc PII không cần thiết.

Metrics hữu ích:
- `federation_logins_total` theo provider alias/protocol/result.
- `federation_auth_failures_total` theo provider/reason (signature, wrong issuer, audience, state, nonce).
- `federation_identity_link_failures_total` theo cohort/provider.
- `federation_permissions_changed_total` để phát hiện privilege drift.
- `federation_jwks_metadata_age_seconds` theo issuer alias/node.
- `federation_sessions_active` theo provider/cohort.
- `federation_rollback_events_total` theo migration phase.

Không dùng email, subject, token, arbitrary kid, issuer URL tùy user hay high-cardinality trace ID làm metric labels. Audit có thể ghi trace ID ở event-level trong log bảo vệ. Alert khi một provider lỗi nhiều, một node thiếu key, identity link fail tăng, signature/issuer rejects tăng, hoặc bất kỳ unauthorized privilege grant nào.

## 17. Checklist nghiệm thu và anti-pattern

**Trust & protocol**
- [ ] Legacy/next SAML EntityID hoặc OIDC issuer khác và chính xác.
- [ ] Mỗi registration có trusted verification certificates/JWKS riêng.
- [ ] JWT decoder/issuer allowlist/aud/time/algorithm tách theo issuer.
- [ ] SAML Issuer/Audience/Recipient/Destination/InResponseTo/signature/time vẫn được kiểm.
- [ ] OIDC client_id/secret/redirect_uri/state/nonce/ID Token issuer/aud đúng.
- [ ] Không tải keys từ arbitrary jku/x5u, không verify bằng global union pool.
- [ ] Key rotation old+new chỉ trong cùng issuer đã phê duyệt.

**Identity & authorization**
- [ ] Links dùng issuer/provider + stable subject + tenant + local account.
- [ ] Cùng email/username không tự merge account.
- [ ] Group/role claims chỉ map theo approved local entitlement policy.
- [ ] Privileged roles có security approval và MFA assurance policy.
- [ ] Session switch không union authorities, token stores không reuse refresh token lẫn issuer.
- [ ] Disabled/unlinked accounts không được cấp business permission.

**Operations**
- [ ] Pilot/canary/cutover/drain/retire có owner và gates rõ.
- [ ] Callback luôn ràng buộc registration lúc bắt đầu flow, kể cả flag thay.
- [ ] Có rollback runbook mà không trộn issuer/keys.
- [ ] Session TTL/revocation policy khi retire issuer rõ ràng.
- [ ] Có positive+negative fixtures, audit logs và alerts.
- [ ] Không tiết lộ bearer tokens, assertions hoặc secrets.

**Anti-pattern tiêu biểu:**
- Gộp legacy và next keys vào cùng một verifier không biết issuer.
- Tự map `roles=admin` thành ROLE_ADMIN ở mọi provider.
- Coi trùng email là approved identity link.
- Dùng `JwtIssuerAuthenticationManagerResolver` cho arbitrary issuer từ token.
- Tắt kiểm audience/nonce/state vì callback “đã đến đúng URL”.
- Dùng old refresh token với new token endpoint.
- Giữ quyền admin từ legacy session sau new login.
- Mượn old metadata/keys khi next JWKS timeout.
- Rollback bằng cách cho old verifier chấp nhận new signed token.
- Giữ legacy trust vô thời hạn sau retirement.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao phải tách verification keys theo issuer?**  
Để một IdP không thể tạo chữ ký mà API coi như do IdP khác phát. Key selection chỉ từ trust set của issuer đã chọn.

**2. Có thể đọc JWT iss chưa verify không?**  
Có thể để chọn trong exact allowlist của server, nhưng phải verify signature và kiểm lại iss/aud/time bằng issuer-bound decoder. Không xây JWKS URL từ iss tùy ý.

**3. Kid có thể trùng giữa hai issuers không?**  
Có. Kid chỉ là selector trong JWKS của issuer, không là identity/global trust anchor.

**4. Hai nhà cung cấp cùng email có thể auto-link account không?**  
Không. Cần issuer-qualified immutable subject, tenant và verified migration approval.

**5. Claim role Admin có chữ ký đúng đã đủ cho ROLE_ADMIN chưa?**  
Chưa. Phải có trusted authority mapping và local business authorization policy.

**6. SAML Response next đến legacy ACS có được dùng next certificate để verify tạm không?**  
Không. Registration/IdP EntityID, signature key, SP audience và correlation phải thuộc legacy flow; không trộn keysets.

**7. OIDC callback next đã chứng minh ID Token thuộc next chưa?**  
Chưa. Cần state/nonce, issuer, signature, client_id audience và verified client registration.

**8. Khi switch provider, có nên cộng quyền từ hai sessions?**  
Không. Recompute từ current verified identity/local IAM policy và quản lý session lifecycle.

**9. Trong planned key rollover của legacy, có thể tạm trust hai legacy signing keys không?**  
Có, trong approved overlap của **cùng legacy issuer**, không dùng key next.

**10. Next IdP outage có thể fallback như thế nào?**  
Nếu policy cho phép, bắt đầu authentication flow mới qua legacy; không reuse next token/Assertion hoặc thay issuer giữa callback.

**11. API cần audience validator dù signature/issuer đã đúng?**  
Có. Cùng issuer có thể ký tokens cho nhiều API và clients.

**12. Khi default đổi sang next, legacy sessions đã tự hết hiệu lực chưa?**  
Không. Phải có session TTL/revocation/drain plan riêng.

**13. Khi retire legacy issuer khỏi API trust, legacy tokens còn hạn thì sao?**  
API sẽ reject chúng, nên cần chuyển clients và quản lý validity/retirement window.

**14. Verified identity nhưng local account disabled thì sao?**  
Deny access. Login proof không thay entitlements/authorization.

## 19. Nguồn tham khảo

1. [Spring Boot 3.3 SAML2 Multiple Relying Parties](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): nhiều SAML registrations và IdP certificates.
2. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, registrationId, ACS và signature checks.
3. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): authentication converter và registration resolution.
4. [Spring Security OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration và callbacks.
5. [Spring Security 6.3 OAuth2AuthenticationToken API](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html): authorized client registration ID.
6. [Spring Security Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): JwtIssuerAuthenticationManagerResolver/trusted issuers.
7. [Spring Security JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): signature/issuer/timestamp/JWKS.
8. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Response/Assertion, Issuer, Conditions.
9. [OASIS SAML2 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityDescriptor, KeyDescriptor.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer/subject/audience/nonce.
11. [RFC 6749 OAuth2](https://www.rfc-editor.org/rfc/rfc6749): redirect URI, authorization code/state.
12. [RFC 7636 PKCE](https://www.rfc-editor.org/rfc/rfc7636): authorization code hardening.
13. [RFC 7517 JWK](https://www.rfc-editor.org/rfc/rfc7517): JWKS/kid/key usage.
14. [RFC 7519 JWT](https://www.rfc-editor.org/rfc/rfc7519): iss/aud/sub/exp/nbf.
15. [RFC 8725 JWT Best Practices](https://www.rfc-editor.org/rfc/rfc8725): alg/key/issuer/audience confusion.
16. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping/trust.
17. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): CSRF/state, issuer mix-up, redirect.
18. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session lifecycle/fixation.

**Kết luận:** Chạy song song IdP cũ và mới là hai vùng trust độc lập cùng phục vụ một ứng dụng. Hãy luôn liên kết **registration/issuer → trusted keys → validated subject → approved identity link → local permissions**, bảo vệ callbacks và sessions, có rollback/cutover/retirement. Không chấp nhận token bằng khóa issuer khác hoặc tự chuyển claims thành quyền quản trị chỉ để giảm lỗi trong giai đoạn migration.