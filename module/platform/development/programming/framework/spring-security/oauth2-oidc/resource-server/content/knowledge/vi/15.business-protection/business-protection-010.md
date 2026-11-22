# Tách chính sách nghiệp vụ khỏi tên claim riêng của một nhà phát hành

## 1. Vấn đề: cùng một quyền nghiệp vụ, nhiều cách biểu diễn trong access token

Một **Spring Security OAuth 2.0 Resource Server** nhận access token từ **Authorization Server (AS)**. Token có thể mang scope, role, group hoặc claim do nhà phát hành tự định nghĩa. Tuy nhiên, **tên claim và cấu trúc JSON không phải mô hình quyền nghiệp vụ của ứng dụng**.

Giả sử API quản lý đơn hàng có yêu cầu:

> Một chủ thể được xem đơn hàng khi có quyền đọc; được sửa đơn hàng khi có quyền sửa **và** đang có quyền đối với đơn hàng cụ thể.

Những nhà phát hành khác nhau có thể biểu diễn các quyền này theo nhiều định dạng.

**Issuer A** dùng một claim tài nguyên dạng nested, thường thấy trong các hệ thống có resource roles:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "sub": "u-101",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-reader", "order-editor"]
    }
  },
  "exp": 1910003600
}
~~~

**Issuer B** cung cấp claim permissions dạng mảng:

~~~json
{
  "iss": "https://login-b.example.com/",
  "sub": "person-918",
  "aud": ["orders-api"],
  "permissions": ["read:orders", "update:orders"],
  "exp": 1910003600
}
~~~

**Issuer C** dùng một scope string:

~~~json
{
  "iss": "https://login-c.example.com/tenant-1",
  "sub": "user-222",
  "aud": ["orders-api"],
  "scp": "Orders.Read Orders.Update",
  "exp": 1910003600
}
~~~

Đây là **các ví dụ minh họa hợp đồng tùy biến**, không khẳng định mọi sản phẩm/phiên bản issuer luôn phát hành các claim giống vậy. Thực tế, mỗi issuer, client, resource và token profile có thể khác.

Nếu service nghiệp vụ viết trực tiếp:

~~~java
if (jwt.getClaimAsMap("resource_access")
        .containsKey("orders-api")) {
    // Cho phép chỉnh sửa đơn hàng?
}
~~~

thì service đã bị buộc chặt vào schema của issuer A. Thay issuer, bổ sung tenant hoặc đổi cấu hình quyền tại AS sẽ khiến logic nghiệp vụ phải sửa theo. Nguy hiểm hơn, điều kiện trên chỉ kiểm tra **có một resource entry** chứ chưa chứng minh được cấp role sửa.

**Mục tiêu của bài:** tạo một **ranh giới chuyển đổi** từ claims đã xác thực sang mô hình **principal, quyền và ngữ cảnh chuẩn hóa do ứng dụng định nghĩa**. Các quy tắc nghiệp vụ ổn định như **ORDER_READ**, **ORDER_EDIT**, **ORDER_APPROVE** không nên phụ thuộc vào việc nhà phát hành gọi chúng là **role**, **scope**, **permissions**, **groups** hay một claim JSON tùy biến nào.

## 2. Sự khác biệt giữa claim, authority và quyền nghiệp vụ

Bốn khái niệm thường bị trộn lẫn:

| Khái niệm | Ví dụ | Thuộc trách nhiệm của ai? |
|---|---|---|
| **JWT claim** | resource_access, permissions, scp, roles, tid | Nhà phát hành token và token profile |
| **OAuth scope** | orders.read, read:orders | Phạm vi quyền mà AS cấp cho access token |
| **Spring GrantedAuthority** | SCOPE_orders.read, PERM_ORDER_EDIT | Cách Spring Security biểu diễn quyền cho request đã xác thực |
| **Domain permission/policy** | EDIT_ORDER đối với order 42 thuộc tenant-blue | Ứng dụng nghiệp vụ, nguồn policy/permission đáng tin |
| **Principal identity** | (iss, sub), local account ID, service principal | Biên xác thực và hệ thống định danh nội bộ |

Một claim không mặc nhiên là permission. Chẳng hạn:

- **groups** có thể là danh sách nhóm, chứ không phải thao tác nghiệp vụ được phép làm.
- **roles** có thể là role cấp client, realm hoặc application, với nghĩa khác nhau.
- **scp** có thể chỉ các delegated scopes, trong khi một token app-only có claim khác.
- **permissions** có thể là entitlement nhưng còn phụ thuộc **audience** và token profile.
- **tenant_id** mô tả ngữ cảnh tenant; nó không tự cho phép đọc mọi bản ghi trong tenant.
- **sub** nhận diện chủ thể theo issuer; nó không phải role hay account ID toàn cục.

Một API nên định nghĩa các khái niệm chính trong **ngôn ngữ nghiệp vụ của chính nó**, ví dụ:

~~~text
Domain permissions:
  ORDER_READ
  ORDER_EDIT
  ORDER_APPROVE
  ORDER_CANCEL

Actions:
  VIEW_ORDER
  MODIFY_ORDER
  APPROVE_ORDER
  CANCEL_ORDER

Context:
  issuer, external subject, local actor, tenant, resource state
~~~

Các tên này cần có semantics rõ: **ORDER_EDIT** có thể cho sửa bản nháp của một order thuộc tenant mà actor có membership hợp lệ, nhưng không cho sửa order đã được phê duyệt. Khi đổi Identity Provider, semantics nghiệp vụ **không đổi**.

## 3. Hai lớp ranh giới: token acceptance và domain authorization

Không thể tách claim names khỏi nghiệp vụ một cách an toàn nếu trước đó Resource Server chấp nhận nhầm token.

~~~text
HTTP Authorization: Bearer <access-token>
            |
            v
[1] Authentication boundary
    - Verify chữ ký JWT hoặc introspection
    - Issuer đúng trust domain
    - Audience/resource đúng API
    - Token chưa hết hạn
    - Token đúng purpose/profile
            |
            v
[2] Issuer-specific adapter
    - Đọc những claim đã xác thực đúng contract
    - Map external roles/scopes -> canonical permissions
    - Map (iss, sub) -> actor identity
    - Thiếu/mâu thuẫn claim: deny, không đoán
            |
            v
[3] Application authorization
    - Kiểm tra quyền chuẩn hóa
    - Kiểm tra tenant, owner, trạng thái resource
    - Kiểm tra quyền hiện hành khi yêu cầu
            |
            v
[4] Domain operation
    - Đọc/sửa/phê duyệt order trong transaction
~~~

**Không cấp quyền chỉ vì payload JWT có một chuỗi trông giống role.** JWT được Base64URL decode có thể đọc được trước khi chữ ký được xác minh. Việc chuyển đổi claims thành authorities chỉ nên xảy ra **sau khi JwtDecoder và validators đã chấp nhận token**, hoặc từ một introspection response đã được kiểm chứng theo hợp đồng AS.

Tách lớp trách nhiệm:

- **Authentication** xác nhận token được tin cậy và liên kết với đúng issuer, audience, profile.
- **Claim adapter / authority converter** biến những biểu diễn đã được xác thực thành tên chuẩn hóa.
- **Authorization policy** quyết định action của actor trên resource cụ thể.
- **Business service** thi hành hành động và bảo vệ tính nhất quán dữ liệu.

## 4. Phụ thuộc claim trực tiếp tạo ra vấn đề gì?

### 4.1. Vendor lock-in trong service

Ví dụ code đọc thẳng schema:

~~~java
// KHÔNG NÊN để code nghiệp vụ phụ thuộc cấu trúc này.
Map<String, Object> realmAccess =
        jwt.getClaimAsMap("realm_access");
~~~

Khi ứng dụng chuyển từ một realm-based issuer sang nhà phát hành dùng scope string, các method xử lý order bị ảnh hưởng dù quy tắc “chỉ người có quyền sửa order mới được sửa” **không thay đổi**.

### 4.2. Trùng tên role nhưng khác ý nghĩa

Hai issuer cùng có role **admin**:

~~~text
Issuer A: admin = quản lý cấu hình đăng nhập
Issuer B: admin = quản trị đơn hàng
~~~

Nếu converter làm:

~~~text
"admin" -> ROLE_ADMIN -> toàn quyền mọi API
~~~

thì có thể tạo **privilege escalation** vì trùng tên role không đồng nghĩa quyền nghiệp vụ tương đương. Phải map theo **issuer + token type + audience/resource + tên role**, với hợp đồng đã được người chịu trách nhiệm xác nhận.

### 4.3. Claim từ resource khác bị hiểu là quyền của API hiện tại

Một JWT có thể chứa:

~~~json
{
  "resource_access": {
    "billing-api": {
      "roles": ["billing-admin"]
    },
    "orders-api": {
      "roles": ["order-reader"]
    }
  }
}
~~~

Nếu ứng dụng lấy tất cả nested roles rồi quy về **ADMIN**, role quản trị hóa đơn có thể bị dùng sai trong API đơn hàng. Adapter phải đọc **đúng phần dành cho orders-api**, và JWT còn phải có audience tương ứng theo access-token contract.

### 4.4. Khó thay đổi chính sách cấp quyền

Nếu endpoint dùng một string riêng của issuer:

~~~java
.hasAuthority("SCOPE_https://provider.example/scopes/editOrder")
~~~

thì logic HTTP bị gắn vào cách issuer đặt tên scope. Một lần đổi issuer hoặc URI scope có thể đòi sửa hàng loạt controllers, annotations và tests.

Giữ tên nội bộ bền vững:

~~~java
.hasAuthority("PERM_ORDER_EDIT")
~~~

và đổi mapping ở **adapter của issuer**, không đổi domain semantics.

### 4.5. Không phân biệt identity, token grant và object ownership

Một access token có role **order-editor** không tự chứng minh actor được sửa **order 42**. Người đó có thể:

- Không còn membership tại tenant của order.
- Chỉ được sửa order thuộc phòng ban mình.
- Có token được phát trước khi role bị thu hồi.
- Chỉ được sửa order trạng thái DRAFT, không được sửa APPROVED.
- Đang dùng client-credentials token không được phép thực hiện user-delegated action.

**Canonical permission là điều kiện cần, không phải quyết định cuối** khi domain có quyền theo đối tượng.

## 5. Từ ngữ của issuer và từ ngữ của domain nên được quản lý riêng

Ví dụ một bảng mapping được xây dựng có chủ ý:

| Issuer / token profile | External claim | Giá trị từ issuer | Permission nội bộ |
|---|---|---|---|
| Realm issuer A, audience orders-api | resource_access.orders-api.roles | order-reader | PERM_ORDER_READ |
| Realm issuer A, audience orders-api | resource_access.orders-api.roles | order-editor | PERM_ORDER_EDIT |
| Issuer B, audience orders-api | permissions | read:orders | PERM_ORDER_READ |
| Issuer B, audience orders-api | permissions | update:orders | PERM_ORDER_EDIT |
| Issuer C, audience orders-api | scp | Orders.Read | PERM_ORDER_READ |
| Issuer C, audience orders-api | scp | Orders.Update | PERM_ORDER_EDIT |

**Các mapping trên chỉ là hợp đồng ví dụ**. Chúng không thể được suy ra tự động từ tên role hay scope; đội sở hữu API cần xác nhận semantics thực tế.

Nguyên tắc:

1. **Mapping allow-list**, không tự động chuyển mọi role thành quyền ứng dụng.
2. Mỗi mapping có **nguồn issuer/profile rõ ràng**.
3. Có thể yêu cầu scope OAuth tối thiểu **cùng với** role nếu grant và business permission là hai điều kiện khác nhau.
4. Không cấp quyền cho unknown claim/unknown value.
5. Xác định hệ quả của claim thiếu, null, sai type hoặc mâu thuẫn.
6. Theo dõi version mapping khi nhà phát hành đổi contract.
7. Chặn khả năng một issuer cấp quyền vượt phạm vi mà hệ thống đã ủy quyền cho issuer đó.

Một role **unknown** không được tự đi qua theo quy tắc:

~~~text
externalRole.toUpperCase() -> PERM_ + role
~~~

Cách này khiến một giá trị do issuer thêm vào có thể trở thành quyền nội bộ ngoài dự kiến.

## 6. Nhà phát hành khác nhau có thể cung cấp role/scope khác nhau

Các ví dụ dưới đây giúp nhận diện mức độ đa dạng, **không phải cam kết schema mặc định của mọi sản phẩm**.

| Hệ sinh thái | Claim có thể gặp | Điểm cần kiểm soát |
|---|---|---|
| Keycloak | realm_access.roles; resource_access.[client].roles | Realm role và client/resource role khác nhau; không cộng gộp tùy tiện |
| Microsoft Entra ID | scp, roles, groups, tid, oid | Delegated scopes và app roles có semantics khác; group overage có thể không liệt kê đầy đủ groups trong JWT |
| Auth0 | scope, permissions hoặc custom namespaced claims | Claim permissions phụ thuộc RBAC/API configuration và token audience |
| Amazon Cognito | scope, cognito:groups, client_id, token_use | Resource Server phải phân biệt access token với ID token; group không tự đồng nghĩa app permission |
| Provider nội bộ | entitlements, grants, authorities, roles, resource_permissions | Phải có contract độc lập và versioning |

Ví dụ **groups** không tồn tại trong JWT không nhất thiết có nghĩa user **không có nhóm nào**. Một số nhà cung cấp có thể cung cấp group memberships qua endpoint khác hoặc dùng claim báo overage. Nếu policy dựa vào groups, adapter phải hiểu rõ trường hợp **thiếu do giới hạn token** so với **thực sự không có quyền**.

Tương tự, **roles** trong machine-to-machine token có thể biểu diễn app roles; nó không tự chứng minh có end user. Phải phân biệt **principal type** trước khi gán chính sách nghiệp vụ.

## 7. Thiết kế mô hình quyền nội bộ ổn định

Thay vì để domain service dùng các role nhà phát hành, tạo vocabulary riêng:

~~~java
public enum BusinessPermission {
    ORDER_READ,
    ORDER_EDIT,
    ORDER_APPROVE,
    ORDER_CANCEL
}
~~~

Nếu Spring Security cần authorities dạng string, có thể định nghĩa naming convention:

~~~text
BusinessPermission.ORDER_READ    -> PERM_ORDER_READ
BusinessPermission.ORDER_EDIT    -> PERM_ORDER_EDIT
BusinessPermission.ORDER_APPROVE -> PERM_ORDER_APPROVE
BusinessPermission.ORDER_CANCEL  -> PERM_ORDER_CANCEL
~~~

Một số nguyên tắc mô hình hóa:

- **Tên quyền nên mô tả hành động nghiệp vụ**, không mô tả IdP nào đã cấp role.
- Không xem permission **ORDER_EDIT** là sự bảo đảm cho phép sửa mọi order; domain resource checks vẫn có thể cần.
- Tránh dùng role thô **ADMIN** như quyền toàn cục nếu domain gồm nhiều phân hệ.
- Xác định role/permission nào dành cho user token, service token hoặc cả hai.
- Tên permission và version mapping nên được kiểm soát trong code/config có review.
- Cân nhắc tách quyền **coarse-grained** (API route/action) và quyền **fine-grained** (object, tenant, trạng thái).

### Permission khác capability

Một **permission** thường là tên quyền ổn định trong domain, ví dụ **ORDER_APPROVE**. Một **capability** cụ thể có thể được ràng buộc với một order ID, thời gian, tenant hoặc workflow state.

Ví dụ:

~~~text
Principal có ORDER_APPROVE:
  Có khả năng bước đầu để xét phê duyệt.

Nhưng order 42:
  status = CANCELLED
  => policy không cho phê duyệt.
~~~

Không đưa mọi biến thể của trạng thái resource vào JWT role chỉ để đơn giản hóa một expression. Điều đó tạo token lớn, dữ liệu nhanh lỗi thời và phát sinh nhiều trường hợp concurrency.

## 8. Lớp chuyển đổi là một anti-corruption layer

Trong thiết kế domain-driven, một **anti-corruption layer** ngăn mô hình bên ngoài lấn sang mô hình bên trong.

Đối với Resource Server:

~~~text
Issuer-specific token claims
   resource_access / permissions / scp / groups
                       |
                       v
        Trusted token adapter
        - schema validation
        - issuer-specific mapping
        - role/scope allow-list
        - principal kind
                       |
                       v
       Canonical authorization model
       - BusinessPermission
       - ExternalPrincipalKey
       - ApplicationActor
                       |
                       v
             Domain policies
       canReadOrder(actor, order)
       canEditOrder(actor, order)
       canApproveOrder(actor, order)
~~~

Thay đổi của provider nên được xử lý ở **adapter**, không phát tán tới repository, order service và business rules.

### Những gì adapter phải biết

- Issuer nào đã được Resource Server tin cậy.
- Token có đúng loại **access token** và đúng resource/audience không.
- Claim path và data type nào được contract quy định.
- External role/scope nào được map sang permission nội bộ.
- Role được cấp theo user, client, tenant hay resource nào.
- Claim thiếu/unknown nên deny hay cần introspection/external lookup.
- Có cần giữ provenance (nguồn issuer, client, grant) cho policy không.

### Những gì domain policy không nên biết

Domain policy nên nói:

~~~text
canEditOrder(actor, order)
~~~

không nên nói:

~~~text
if provider is Keycloak and resource_access.orders-api.roles
   contains order-editor ...
~~~

Nó có thể cần hiểu **local tenant**, **order ownership** và **permission chuẩn hóa**, nhưng không phải cách một provider đặt tên trường JSON.

## 9. Ví dụ cụ thể: chuyển client roles thành authorities chuẩn hóa

Giả sử chỉ có một issuer được tin:

~~~text
https://login-a.example.com/realms/shop
~~~

và access token cho **orders-api** chứa:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "sub": "user-101",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-reader", "order-editor"]
    }
  }
}
~~~

Ta có thể tạo một **Converter<Jwt, Collection<GrantedAuthority>>** chỉ đọc đúng resource role dành cho **orders-api**. Converter chạy **sau** khi JwtDecoder xác minh token.

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrdersPermissionsConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String API_RESOURCE = "orders-api";

    private static final Map<String, String> ALLOWED_ROLE_MAPPING =
            Map.of(
                    "order-reader", "PERM_ORDER_READ",
                    "order-editor", "PERM_ORDER_EDIT",
                    "order-approver", "PERM_ORDER_APPROVE"
            );

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Map<String, Object> resourceAccess =
                jwt.getClaimAsMap("resource_access");

        if (resourceAccess == null) {
            return Set.of(); // Không tự cho quyền khi claim thiếu.
        }

        Object resourceObject = resourceAccess.get(API_RESOURCE);
        if (!(resourceObject instanceof Map<?, ?> resource)) {
            return Set.of();
        }

        Object rolesObject = resource.get("roles");
        if (!(rolesObject instanceof Collection<?> roles)) {
            return Set.of();
        }

        Set<GrantedAuthority> granted = new LinkedHashSet<>();

        for (Object item : roles) {
            if (!(item instanceof String role)) {
                continue;
            }

            String mappedAuthority = ALLOWED_ROLE_MAPPING.get(role);
            if (mappedAuthority != null) {
                granted.add(
                        new SimpleGrantedAuthority(mappedAuthority));
            }
        }

        return Set.copyOf(granted);
    }
}
~~~

Ý nghĩa bảo mật:

1. Claim được đọc từ **Jwt đã được decoder xác thực**.
2. Converter chỉ xét **resource_access.orders-api.roles**, không lấy role của resource khác.
3. Chỉ có những giá trị **được allow-list** mới trở thành authorities.
4. Claim thiếu, sai type hoặc role không nhận diện sẽ **không được cấp quyền tương ứng**.
5. Converter không tự suy ra **ROLE_ADMIN** hoặc **PERM_ORDER_APPROVE** từ một role tên gần giống.
6. Nó không truy vấn quyền hiện hành; nếu quyền có thể bị thu hồi sau khi token được phát hành, domain policy vẫn phải kiểm tra freshness theo yêu cầu.

**Giới hạn của ví dụ:** cần xác thực issuer, audience và token purpose trước khi dùng converter. Một số issuer có thể không phát hành dạng nested claim như trên; hãy dùng adapter theo hợp đồng provider, không ép token khác vào schema này.

### Đăng ký converter trong Spring Security Resource Server

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(
            new OrdersPermissionsConverter());

    converter.setPrincipalClaimName("sub");

    return converter;
}
~~~

Sau đó gắn vào security chain:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(
                jwtAuthenticationConverter())))
~~~

Converter xây **JwtAuthenticationToken** với authorities đã chuẩn hóa. Ở tầng HTTP:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("PERM_ORDER_READ")
.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("PERM_ORDER_EDIT")
~~~

Domain không cần biết role gốc tên **order-reader** hay **order-editor**. Nếu issuer thay role name thành **orders.viewer** và **orders.editor**, chỉ adapter phải cập nhật mapping sau khi đã review ý nghĩa.

### Không vô tình đánh mất scope bắt buộc

Trong ví dụ, đặt **setJwtGrantedAuthoritiesConverter** thay converter mặc định bằng một converter custom. Vì vậy, **SCOPE_...** từ scope mặc định có thể không còn xuất hiện trong Authentication nếu custom converter không tạo nó.

Nếu policy cần **cả OAuth scope lẫn business permission**, phải kết hợp rõ ràng từ hai nguồn đã được xác thực, rồi xét AND theo contract. Không cho rằng dùng converter mới sẽ tự giữ toàn bộ scope cũ.

## 10. Cấu hình xác thực token không được bị bỏ qua vì đã có converter

Một token giả có thể tự khai đúng:

~~~json
{
  "iss": "https://login-a.example.com/realms/shop",
  "aud": ["orders-api"],
  "resource_access": {
    "orders-api": {
      "roles": ["order-editor"]
    }
  }
}
~~~

Nếu Resource Server tin claim mà không xác minh JWT, attacker có thể tự cấp quyền cho mình. Converter chỉ an toàn khi JWT đã đi qua **decoder và validators** đáng tin.

Ví dụ cấu hình decoder cho một issuer cụ thể với audience **orders-api**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TokenValidationConfig {

    private static final String ISSUER =
            "https://login-a.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> apiAudience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Access token is not for orders-api",
                                    null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, apiAudience));
        return decoder;
    }
}
~~~

Cấu hình này tập trung **issuer và audience**; Resource Server cũng phải xác nhận **token-purpose/profile**, thuật toán JWS tin cậy và các điều kiện hợp đồng khác. Nếu provider phát hành RFC 9068 JWT access token, cần xử lý các yêu cầu profile (ví dụ **typ=at+jwt**) bằng cơ chế phù hợp. Nếu provider có claim **token_use=access** hoặc profile riêng, không mặc định các trường đó tồn tại ở mọi issuer.

**Lưu ý:** khi gọi **setJwtValidator(...)**, bộ validators đang gắn với decoder được thay thế. Phải giữ validators mặc định cần thiết về issuer, thời gian và các quy tắc riêng. Audience validator không tự kiểm tra signature.

### Vì sao chỉ kiểm tra issuer vẫn chưa đủ?

Một issuer có thể phát hành:

- **ID token** cho web client, có **aud=web-client**.
- **Access token** cho orders-api, có **aud=orders-api**.
- Access token cho billing-api với quyền invoice.

Ba token có thể cùng issuer hoặc cùng JWKS, nhưng **không cùng mục đích**. Nếu converter đọc claim roles của một ID token, API không được chấp nhận token đó làm bearer access token chỉ vì claim có tên giống.

## 11. Từ token adapter sang local actor

Không nên để toàn bộ domain service cầm đối tượng **Jwt** và tự đọc claims. Hãy ánh xạ danh tính bên ngoài thành **ApplicationActor** do hệ thống định nghĩa.

Một mô hình khái niệm:

~~~java
public record ExternalPrincipalKey(
        String issuer,
        String subject) {
}

public enum PrincipalKind {
    USER,
    SERVICE
}

public record ApplicationActor(
        java.util.UUID localId,
        PrincipalKind kind,
        java.util.Set<BusinessPermission> permissions) {
}
~~~

Giải thích:

- **(issuer, subject)** giữ phạm vi định danh của AS/OP; **sub** riêng lẻ không độc nhất qua nhiều issuer.
- **localId** là định danh nội bộ; không phụ thuộc cách một provider đặt **sub**.
- **kind** phân biệt user với service/client principal. Không giả định mọi token đều đại diện một người dùng.
- **permissions** là từ ngữ domain; chúng có thể đến từ grant đã xác thực, permission store hoặc tổ hợp chính sách được kiểm soát.

Đường ánh xạ:

~~~text
Verified JWT / trusted introspection
         |
         v
Issuer-specific claim adapter
         |
         v
ExternalPrincipalKey(iss, sub)
         |
         v
IdentityDirectory:
  (issuer, subject) -> local account/service
         |
         v
ApplicationActor(localId, kind, permissions)
         |
         v
Domain policy:
  mayEditOrder(actor, order)
~~~

Với nhiều issuer, cặp **(iss, sub)** giúp tránh nhầm danh tính:

~~~text
Issuer A, sub=123 -> local account Alice
Issuer B, sub=123 -> local account Bob

Nếu chỉ tìm user theo sub=123:
  có thể cấp quyền và dữ liệu sai người.
~~~

**Không tự liên kết tài khoản theo email hoặc username** giữa các issuer. Account linking cần quy trình và bằng chứng đáng tin riêng.

### 11.1. Local identity mapping không phải permission mapping

Hai thao tác độc lập:

1. **Identity mapping:** token đã xác thực đang đại diện cho local actor nào?
2. **Permission mapping:** external claims/entitlements và policy nội bộ trao quyền gì cho actor đó?

Chỉ có identity mapping không có nghĩa actor được phép làm mọi hành động. Ngược lại, role claim trông hợp lệ cũng không đủ để bỏ qua trạng thái local account đã bị disable.

### 11.2. OIDC pairwise subject

OIDC có thể phát hành **pairwise subject identifiers** khác nhau cho cùng người dưới các sector khác nhau. Vì thế một người có thể có nhiều **sub** hợp lệ ở cùng OP tùy ngữ cảnh client.

ApplicationActor local mapping có thể hỗ trợ liên kết identity, nhưng **không tự suy ra** pairwise subjects thuộc cùng người bằng email hoặc tên hiển thị. Privacy boundary của OP cần được tôn trọng.

## 12. Domain policy không cần biết claim path

Một order có thể sửa khi các điều kiện sau cùng đúng:

~~~text
Principal được xác thực
AND có PERM_ORDER_EDIT
AND local account đang active
AND actor còn membership tenant của order
AND order đang ở trạng thái được phép sửa
AND actor không đang bị conflict-of-interest policy chặn
~~~

Lớp chính sách nên có interface theo domain:

~~~java
public interface OrderAuthorizationPolicy {
    boolean mayEditOrder(ApplicationActor actor, Order order);
    boolean mayApproveOrder(ApplicationActor actor, Order order);
}
~~~

Một cách triển khai khái niệm:

~~~java
public boolean mayEditOrder(ApplicationActor actor, Order order) {
    return actor.permissions().contains(
                    BusinessPermission.ORDER_EDIT)
            && membershipStore.hasActiveMembership(
                    actor.localId(), order.tenantId())
            && order.status() == OrderStatus.DRAFT
            && !order.isLocked();
}
~~~

**MembershipStore**, **Order** và **OrderStatus** là thành phần domain giả định cần định nghĩa trong project thực tế. Ví dụ muốn thể hiện: quyền trên resource phải dựa vào **ngôn ngữ nghiệp vụ và trạng thái hiện hành**, không dựa vào tên claim của issuer.

Không nên có code:

~~~java
if ("login-a.example.com".equals(provider)
        && jwt.getClaimAsMap("resource_access") != null) {
    return true;
}
~~~

trong domain policy. Cả hai lỗi đều xuất hiện: phụ thuộc provider và cho quyền quá rộng.

### 12.1. Tích hợp với Spring Method Security

Có thể dùng method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Trong application service:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import java.util.UUID;

@Service
public class OrderService {

    @PreAuthorize(
        "hasAuthority('PERM_ORDER_EDIT') " +
        "and @orderGuard.mayEdit(authentication, #orderId)")
    public void editOrder(
            @P("orderId") UUID orderId,
            OrderPatch patch) {
        // Thực hiện thao tác trong transaction phù hợp.
    }
}
~~~

Một **orderGuard** ở lớp ứng dụng:

~~~java
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderGuard")
public class OrderGuard {

    private final CurrentActorResolver actorResolver;
    private final OrderRepository orders;
    private final OrderAuthorizationPolicy policy;

    public OrderGuard(
            CurrentActorResolver actorResolver,
            OrderRepository orders,
            OrderAuthorizationPolicy policy) {
        this.actorResolver = actorResolver;
        this.orders = orders;
        this.policy = policy;
    }

    public boolean mayEdit(
            Authentication authentication, UUID orderId) {

        ApplicationActor actor =
                actorResolver.resolve(authentication).orElse(null);

        if (actor == null) {
            return false;
        }

        return orders.findById(orderId)
                .map(order -> policy.mayEditOrder(actor, order))
                .orElse(false);
    }
}
~~~

Đây là **mô hình tích hợp**: các kiểu **OrderPatch**, **CurrentActorResolver**, **OrderRepository** cần được định nghĩa trong ứng dụng. Mục đích là chỉ **CurrentActorResolver/claim adapter** cần biết cách lấy principal từ Authentication, còn **OrderAuthorizationPolicy** chỉ biết ApplicationActor và Order.

Một số lưu ý khi dùng thực tế:

- **@PreAuthorize** cần method security được bật, lời gọi đi qua Spring AOP proxy và tên tham số trong SpEL khả dụng.
- Domain authorization cần được thực thi gần thao tác, nhất là khi order status có thể đổi giữa lúc kiểm tra và lúc ghi. Có thể cần transaction, version hoặc locking.
- Quyền đọc một endpoint không tự chứng minh actor có quyền với **từng order** được truy xuất.
- **PERM_ORDER_EDIT** là coarse permission; kiểm tra order/tenant là fine-grained policy.

## 13. Không chỉ normalize permission: còn phải phân biệt user và service principal

Access token của OAuth 2.0 có thể thuộc hai trường hợp:

**User-delegated token:**

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

**Client-credentials token:**

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "inventory-sync",
  "client_id": "inventory-sync",
  "aud": "orders-api",
  "scope": "orders.sync",
  "exp": 1910003600
}
~~~

Một token có **sub** không có nghĩa chủ thể là con người. Tùy AS/profile, **sub** ở client credentials có thể là service/client principal. Adapter phải biết loại principal được contract cho phép và map sang đúng local actor.

Ví dụ:

| Hành động | User token | Service token |
|---|---|---|
| Xem đơn hàng của chính user | Có thể được xét theo ownership | Không mặc nhiên |
| Chạy đồng bộ dữ liệu tồn kho | Không mặc nhiên | Có thể được xét với permission dành cho service |
| Phê duyệt order thủ công | Cần user identity + workflow policy | Có thể bị cấm |
| Xem trạng thái kỹ thuật của job | Tùy scope và domain | Tùy service permission |

Nếu adapter chuyển **mọi token có role manager** thành một human **ADMIN**, có thể vô tình nâng quyền service principal. **PrincipalKind** nên được chuẩn hóa theo token profile/claims đã được xác thực, không phỏng đoán từ kiểu chuỗi **sub**.

## 14. Multi-issuer: mỗi issuer cần một trust và mapping contract

Khi API chấp nhận token từ nhiều issuer, vấn đề không chỉ là thêm một nhánh **switch** trong converter. **Mỗi issuer cần được xác thực bằng key source và validators phù hợp**.

~~~text
Issuer A (trusted)
  -> JWKS A
  -> JWT validation A
  -> Claim adapter A
  -> PERM_ORDER_READ / PERM_ORDER_EDIT
                                |
                                v
                         Domain policy
                                ^
                                |
Issuer B (trusted)              |
  -> JWKS B                     |
  -> JWT validation B           |
  -> Claim adapter B -----------+
  -> PERM_ORDER_READ / PERM_ORDER_EDIT

Issuer lạ
  -> Reject, không tự khám phá rồi tin JWKS mới
~~~

Trong Spring Security Servlet, có thể dùng nhiều **SecurityFilterChain** theo route hoặc **AuthenticationManagerResolver<HttpServletRequest>** với cấu hình multi-tenant/multi-issuer. Nếu cần đọc **iss** chưa xác minh để chọn manager, giá trị đó chỉ là **routing hint** và chỉ được chọn từ **allow-list issuer đã cấu hình trước**. Decoder tương ứng vẫn phải xác minh chữ ký và issuer.

### Không dùng decoder của issuer A cho mọi issuer

Sai:

~~~text
Token iss=B
  -> dùng JWKS A chỉ vì alg/kid nhìn tương tự
  -> bỏ kiểm tra issuer
  -> chấp nhận roles của B
~~~

Đúng:

~~~text
Token iss=B
  -> issuer B phải nằm trong trusted issuers
  -> decoder B dùng JWKS B
  -> kiểm tra iss=B, aud=orders-api, time, profile
  -> claim adapter B map từ contract B
~~~

Hai issuer có thể cùng **kid**, **sub** hoặc role name; đó không phải bằng chứng chúng có cùng key, cùng principal hoặc cùng ý nghĩa quyền.

### Không gộp role names của hai issuer chỉ vì cùng chữ

Ví dụ **admin** của issuer A là quản trị login realm, còn **admin** của issuer B là quản trị merchant profile. Không map cả hai thành **PERM_ORDER_APPROVE** trừ khi policy doanh nghiệp xác nhận **mỗi issuer có thẩm quyền cấp quyền approve**.

## 15. Thiết kế policy theo nguồn thẩm quyền, không chỉ tên claim

Một câu hỏi bảo mật cốt lõi:

> Issuer này có được **ủy quyền cấp quyền nghiệp vụ này** cho Resource Server hay không?

Một issuer có thể phát hành JWT đúng chữ ký và audience nhưng chỉ được phép xác thực identity, không được phép tự tạo quyền quản trị domain.

Ví dụ:

~~~text
Issuer A:
  Được dùng để chứng thực nhân viên.
  Không có thẩm quyền cấp quyền phê duyệt thanh toán.

Domain application:
  PERM_PAYMENT_APPROVE được quản lý bởi hệ thống nội bộ.

Kết luận:
  Issuer A có role="payment-admin"
  -> không được tự map thành PERM_PAYMENT_APPROVE
     nếu chưa có hợp đồng phân quyền cho issuer A.
~~~

Mô hình tối thiểu:

~~~text
Trusted token source
   AND issuer được phép cấp loại grant này
   AND JWT đúng audience/profile
   AND external permission được allow-list
   AND account/tenant policy hiện hành
        => action có thể được xem xét
~~~

Với quyền nhạy cảm, có thể để token **chỉ chứng minh identity và một scope tối thiểu**, còn quyền cấp phê duyệt do **local authorization store/PDP** quyết định. Đây là cách ngăn một identity provider trở thành điểm có thể tự cấp quyền nghiệp vụ ngoài phạm vi ủy quyền.

## 16. Token scope và app permission cần kết hợp thế nào?

Có hai chiến lược phổ biến:

### Chiến lược A: một quyền chuẩn hóa đã đủ cho bước coarse authorization

Nếu hợp đồng token từ AS nói role **order-editor** đã là entitlement dành cho orders-api, adapter có thể chuyển nó thành **PERM_ORDER_EDIT**, sau đó policy bổ sung kiểm tra tenant/order.

~~~text
allow coarse = PERM_ORDER_EDIT
allow final = coarse AND domain conditions
~~~

### Chiến lược B: OAuth scope là giới hạn trên, app permission là điều kiện thêm

Nếu issuer cấp scope như grant của client, còn domain policy quản lý role/user:

~~~text
allow =
    token có SCOPE_orders.write
    AND actor có PERM_ORDER_EDIT
    AND object policy chấp nhận
~~~

Ví dụ:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and hasAuthority('PERM_ORDER_EDIT') " +
    "and @orderGuard.mayEdit(authentication, #orderId)")
~~~

Trong chiến lược này, custom authorities converter cần **giữ cả hai bộ authority** nếu muốn dùng đồng thời. Nếu chỉ gọi **setJwtGrantedAuthoritiesConverter** với một converter trả **PERM_...**, **SCOPE_...** không tự xuất hiện nữa.

Đừng vô tình biến mô hình **scope AND permission** thành **scope OR permission**. Một service token có scope rất rộng hoặc role không đầy đủ có thể vượt quyền nếu policy dùng toán tử OR không đúng mục đích.

## 17. Opaque access token: adapter nhận metadata đã introspection

Nếu AS phát hành opaque token, JWT converter không phù hợp vì Resource Server không thể lấy JWT claims trực tiếp. Thay vào đó Spring Security dùng **OAuth2 Token Introspection** theo hợp đồng với AS.

Ví dụ response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "custom_permissions": ["order:edit"],
  "exp": 1910003600
}
~~~

**active=true** không tự cấp mọi quyền. Tùy contract, introspection response có thể có ít hoặc nhiều metadata; **iss** không phải trường bắt buộc trong mọi introspection response theo RFC 7662.

Ở biên adapter:

1. Chỉ tin response từ **introspection endpoint được cấu hình và xác thực**.
2. Xác định issuer/resource binding theo contract của AS.
3. Chuẩn hóa các attributes thành identity/permission model của ứng dụng.
4. Thiếu dữ liệu quyết định thì **không suy đoán cho phép**.
5. Domain policy tiếp tục kiểm tra quyền hiện hành khi cần.

Có thể tùy biến **OpaqueTokenIntrospector** hoặc converter/adapter sau introspection để tạo một mô hình chung. **Không để domain service phụ thuộc trực tiếp vào format JSON của introspection response**.

### Introspection có cập nhật quyền mới nhất không?

Không tự bảo đảm. AS có thể trả scope snapshot lúc token được cấp hoặc tính lại quyền hiện hành; cache introspection ở API cũng có thể bị stale. Cần làm rõ semantics của AS, cache TTL, revocation SLA và quyền domain, đặc biệt với thao tác nhạy cảm.

## 18. Thay đổi quyền sau phát token: canonical permissions vẫn có thể stale

Tách claim names là cần thiết nhưng **không tự giải quyết độ mới của quyền**.

~~~text
09:00 AS phát JWT:
  external role=order-editor

09:05 Admin thu hồi role.
  External authorization store đã thay đổi.

09:06 Client dùng JWT cũ:
  JWT vẫn còn external role=order-editor.

Converter:
  order-editor -> PERM_ORDER_EDIT

Nếu API chỉ kiểm tra PERM_ORDER_EDIT:
  có thể vẫn cho phép đến khi token hết hạn.
~~~

Vì vậy, với domain yêu cầu thu hồi quyền nhanh, cần kết hợp:

- JWT lifetime ngắn và AS đánh giá lại role khi cấp token mới.
- Token revocation/introspection/denylist hay versioning theo contract.
- Local account status, tenant membership hoặc PDP ở request time.
- Cache invalidation và max staleness được quy định rõ.
- Enforcement gần thao tác nghiệp vụ trong transaction.

Tách **tên claim** khỏi **policy** giúp thay issuer dễ hơn; nhưng chính sách quyền hiện hành còn cần nguồn dữ liệu và SLA riêng.

## 19. Chính sách deny-by-default khi claim không như kỳ vọng

Khi adapter nhận dữ liệu không đúng contract, **không nên cố đoán**.

| Dữ liệu nhận được | Hành vi bảo thủ |
|---|---|
| Thiếu claim role/scope mà permission yêu cầu | Không cấp permission tương ứng |
| Claim có type sai, ví dụ string thay vì mảng được cam kết | Từ chối quyền hoặc token theo profile/validator phù hợp |
| Role mới chưa có trong allow-list mapping | Không cấp permission mới |
| Role name trùng nhưng từ issuer khác | Dùng mapping riêng của issuer đó; không copy quyền |
| JWT đúng chữ ký nhưng sai audience | Từ chối token ở validator, trước adapter |
| JWT không rõ access-token purpose | Từ chối theo profile/contract |
| Claim nói một role nhưng local account đã disabled | Domain/account policy từ chối |
| Claim chứa group ID chưa biết | Không suy ra role; xử lý theo hợp đồng group mapping |
| Claim nhóm bị overage/truncated | Không tự coi là có mọi group; dùng nguồn quyền phù hợp hoặc deny |
| Adapter mapping version chưa tương thích token | Từ chối quyền không được chứng minh; quy trình migration rõ |
| Policy service không truy cập được | Hành vi fail-closed với thao tác nhạy cảm |
| External issuer không thuộc allow-list | Không tạo trust mới từ JWT |

Có hai mức fail-closed:

- **Token invalid:** resource server từ chối authentication (thường 401).
- **Token được xác thực nhưng không đủ permission:** authorization từ chối (thường 403).

Không nhất thiết biến mọi claim thiếu thành **invalid_token** nếu claim đó chỉ dùng cấp một permission tùy chọn. Nhưng **không được mặc định cho phép** khi thiếu thông tin cần để quyết định.

## 20. Anti-pattern: tự động chuyển mọi role thành authority

Ví dụ thiết kế rủi ro:

~~~java
// TRÁNH: role do provider đặt tên nào cũng trở thành quyền của API.
for (String role : rolesFromJwt) {
    authorities.add(
            new SimpleGrantedAuthority("PERM_" + role.toUpperCase()));
}
~~~

Một nhà cung cấp có thể thêm role mới **SUPERUSER** để quản lý công việc khác; nếu application vô tình có **hasAuthority("PERM_SUPERUSER")**, nó có thể biến role ngoài ý muốn thành quyền nội bộ.

Nên dùng **mapping explicit**:

~~~text
issuer A + orders-api + order-reader
    -> PERM_ORDER_READ

issuer A + orders-api + order-editor
    -> PERM_ORDER_EDIT

mọi external role khác
    -> không có quyền domain bổ sung
~~~

Mỗi mapping cần được review về **semantics**, không chỉ chính tả. Có thể ghi metadata: owner, purpose, version, hiệu lực và các API được phép tin.

## 21. Anti-pattern: đọc trực tiếp claim trong controller hoặc repository

Không nên:

~~~java
@GetMapping("/api/orders/{id}")
OrderDto get(
        @PathVariable String id,
        @AuthenticationPrincipal Jwt jwt) {

    if (jwt.getClaimAsStringList("groups").contains("manager")) {
        return orderRepository.load(id);
    }
    throw new AccessDeniedException("Denied");
}
~~~

Các vấn đề:

- Controller phụ thuộc claim **groups** của provider.
- String **manager** không xác định có nghĩa gì với orders-api.
- Không kiểm tra nhóm đó thuộc issuer/tenant nào.
- Không kiểm tra ownership của order.
- Thiếu claim có thể gây lỗi null hoặc kết quả không nhất quán.
- Thay provider sẽ buộc sửa controller.

Cách tốt hơn:

~~~text
Controller gọi application service.
Application service lấy ApplicationActor đã xác thực.
OrderAuthorizationPolicy.canReadOrder(actor, order).
Repository truy vấn dữ liệu theo tenant/owner đã được policy xác định.
~~~

Điều này không bắt buộc tất cả authorization phải nằm trong một class duy nhất. Mục tiêu là **business policy có vocabulary ổn định và được thực thi thống nhất** ở các điểm vào REST API, background job hoặc message consumer.

## 22. Tránh rò rỉ tên claim vào annotations và database schema

Tách claim names chỉ ở controller chưa đủ nếu chúng còn nằm ở:

- Annotation **@PreAuthorize** khắp codebase.
- Tên column như **keycloak_realm_role** trong bảng authorization domain.
- Business event như **PermissionGrantedFromCognitoGroup** nhưng được dùng như sự kiện quyền chung.
- Service API như **isKeycloakOrderEditor(jwt)**.
- Cache keys chỉ dựa vào provider group name.
- Audit log dùng provider claim làm duy nhất user ID.

Một mô hình rõ ràng hơn:

~~~text
Integration adapters:
  ProviderAClaimReader
  ProviderBClaimReader
  ExternalPrincipalResolver

Application:
  ApplicationActor
  BusinessPermission
  OrderAuthorizationPolicy
  OrderCommandService

Persistence:
  external_identity(issuer, subject, local_actor_id)
  membership(local_actor_id, tenant_id, status)
  permission_grant(local_actor_id, permission_code, context)
~~~

Bảng **external_identity** có thể dùng unique key **(issuer, subject)**. Bảng **permission_grant** dùng mã permission nội bộ. Database có thể lưu provenance của external grants riêng nếu cần audit, nhưng không biến tên claim của provider thành public domain API.

## 23. Quy trình thay nhà phát hành mà không viết lại domain policy

Giả sử hệ thống chuyển từ issuer A sang issuer B. Trước khi thay:

~~~text
Issuer A:
  resource_access.orders-api.roles = [order-editor]

Adapter A:
  order-editor -> PERM_ORDER_EDIT

Domain:
  canEditOrder(actor, order)
~~~

Sau khi thay:

~~~text
Issuer B:
  permissions = [update:orders]

Adapter B:
  update:orders -> PERM_ORDER_EDIT

Domain:
  canEditOrder(actor, order)
~~~

**Domain policy vẫn giữ nguyên**. Nhưng việc đổi issuer không chỉ là đổi claim path; còn cần migration **identity và trust**:

1. Xác định issuer mới được tin, JWKS/introspection và audience hợp lệ.
2. Định nghĩa mapping mới với semantics tương đương hoặc khác biệt có chủ đích.
3. Kiểm tra ID token/access token purpose; không dùng token login làm API credential.
4. Mapping **(issuer, sub)** mới vào local actor cũ qua quy trình đáng tin, không auto-link theo email.
5. Xử lý thời gian chuyển đổi khi hai issuer cùng được chấp nhận.
6. Bảo đảm không tồn tại role ngoài ý muốn cấp quyền quản trị cao hơn.
7. Cập nhật audit/provenance, vận hành, cache và rollback plan.
8. Chặn issuer cũ sau cutoff nếu hợp đồng không còn tin cậy.

### Contract mapping có thể version hóa

Ví dụ dữ liệu config mang tính minh họa:

~~~yaml
authorization-mapping:
  version: 3
  issuers:
    issuer-a:
      issuer-uri: https://login-a.example.com/realms/shop
      resource: orders-api
      source: resource_access.orders-api.roles
      mapping:
        order-reader: PERM_ORDER_READ
        order-editor: PERM_ORDER_EDIT
    issuer-b:
      issuer-uri: https://login-b.example.com/
      resource: orders-api
      source: permissions
      mapping:
        read:orders: PERM_ORDER_READ
        update:orders: PERM_ORDER_EDIT
~~~

**YAML trên chỉ là format tự thiết kế**, không phải Spring Boot properties có sẵn. Trong YAML thực tế, các khóa có dấu hai chấm như **read:orders** nên được trích dẫn khi cần để tránh parse không như mong đợi. Các permission/mapping quan trọng cần code review và kiểm soát thay đổi, không cho token hoặc request tự cung cấp cấu hình mapping.

## 24. Test theo contract, không chỉ test tên claim

Một adapter nên có các tình huống kiểm thử theo **kết quả permission chuẩn hóa**:

| Tình huống | Input token/claim | Kỳ vọng |
|---|---|---|
| Role đọc hợp lệ từ issuer A | order-reader | PERM_ORDER_READ |
| Role sửa hợp lệ từ issuer A | order-editor | PERM_ORDER_EDIT |
| Role không biết | unexpected-admin | Không có quyền bổ sung |
| Token sai audience | aud=billing-api | Bị từ chối trước permission mapping |
| Role dành cho resource khác | billing-api.roles=admin | Không tạo quyền orders-api |
| Issuer B có role trùng tên issuer A | admin | Map theo contract B hoặc không cấp |
| Thiếu claim resource_access | null | Không cấp quyền từ claim |
| Claim roles không phải collection | "order-editor" | Không tự đoán, theo fail-closed policy |
| Token từ issuer chưa được tin | iss=attacker | Không chấp nhận token |
| JWT hết hạn | exp cũ | Không tạo authenticated principal |
| OIDC ID token có claims giống access token | aud=web-client | Không nhận làm API access token |
| Client-credentials token | sub=service-id | Actor type SERVICE theo contract |
| User đổi membership sau khi phát JWT | role cũ còn trong JWT | Current domain policy từ chối nếu yêu cầu |
| Actor có PERM_ORDER_EDIT nhưng order đã APPROVED | status=APPROVED | Domain policy từ chối |
| Hai issuer cùng sub=123 | iss khác nhau | ExternalPrincipalKey khác nhau |

Phân biệt hai loại test:

- **Converter/unit tests:** cho converter nhận một **Jwt object giả lập đã chuẩn bị** rồi kiểm tra mapping quyền. Đây không kiểm chứng signature/issuer.
- **Resource Server integration tests:** đi qua JwtDecoder/validator/AuthenticationManager thực để kiểm chứng signature, issuer, audience, token purpose và filter chain.

Spring Security Test có thể tạo JWT authentication giả cho authorization tests; điều đó không tự chứng minh production đã xác minh JWT signature. **Các trường hợp trên chỉ mô tả kỳ vọng thiết kế; không có bộ test nào được chạy trong STEP 4.**

## 25. Đảm bảo hành vi trước thay đổi quyền và khi role bị thu hồi

Các claim trong JWT được **chụp tại thời điểm AS phát hành token**. Khi một người mất role sau đó, JWT cũ vẫn có thể chứa role và được adapter map sang **PERM_ORDER_EDIT**.

Do đó:

~~~text
Token đã phát hành:
  role=order-editor
       |
       v
Adapter:
  PERM_ORDER_EDIT
       |
       v
Domain policy:
  Kiểm tra current membership + order ownership
       |
       v
Cho phép hoặc từ chối theo quyền hiện tại
~~~

Nếu nghiệp vụ chấp nhận stale quyền trong cửa sổ ngắn, có thể dùng JWT thời hạn ngắn cùng chính sách cấp mới token phù hợp. Nếu phải thu hồi gần tức thời, cần current permission store, introspection, denylist, token versioning hoặc PDP theo kiến trúc.

**Không được coi claim adapter là nguồn sự thật về quyền hiện hành**; nó chỉ chuyển nghĩa dữ liệu đã được token issuer chứng thực tại thời điểm phát hành.

## 26. Xử lý lỗi và logging khi mapping không hợp lệ

Đừng lộ token hoặc chi tiết roles nhạy cảm trong HTTP response. Thường:

- Token không hợp lệ, sai issuer, sai audience hoặc sai mục đích: **authentication failure**, thường 401 với Bearer challenge.
- Token hợp lệ nhưng thiếu **PERM_ORDER_EDIT**: **authorization failure**, thường 403.
- Token hợp lệ và có permission nhưng không có quyền trên order/tenant: domain authorization từ chối, thường 403 theo policy.
- Adapter thiếu optional claim: có thể **không cấp permission**, rồi HTTP authorization từ chối; không nhất thiết phải biến thành lỗi parse toàn bộ token.

Ví dụ challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

và:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Response chính xác phụ thuộc Spring Security entry point/denied handler và loại chính sách. Với lỗi chỉ do permission nghiệp vụ không có trong scope, **insufficient_scope** có thể không phải mô tả chính xác; nên dùng error contract rõ ràng, tránh tiết lộ chi tiết tài nguyên.

Logging nên dùng:

~~~text
request_id
trusted_issuer_id
local_actor_id (nếu policy cho phép)
provider_adapter_version
canonical_permission_checked
policy_decision
reason_code
~~~

Không log raw bearer access token, toàn bộ JWT payload, credentials, secret introspection hoặc private signing key. Claims chưa xác thực có thể bị attacker điều khiển, không nên đưa chúng vào log dưới dạng thông tin tin cậy.

## 27. Danh sách câu hỏi thiết kế cho đội API và IAM

Trước khi cho một issuer mới cấp permission nội bộ, cần hỏi:

1. Issuer nào được Resource Server tin và cấu hình ở đâu?
2. API chấp nhận **JWT access token** hay **opaque access token**?
3. Kiểm tra signature, algorithm, issuer, audience, expiration và token profile thế nào?
4. Claim nào thực sự mang **grant/entitlement dành cho API**, không phải role quản trị của issuer?
5. Claim đó có thuộc **access token** hay chỉ **ID token**?
6. Tên role/scope được version hóa và sở hữu bởi team nào?
7. Issuer có thẩm quyền cấp từng **BusinessPermission** cụ thể hay chỉ xác thực identity?
8. Có cần phân biệt delegated user token và client-credentials service token không?
9. Thiếu claim, sai type hoặc issuer thay schema có được fail-closed không?
10. Ai chịu trách nhiệm mapping **(issuer, sub)** sang local actor và account linking?
11. Scope OAuth là upper bound hay chỉ là một phần của permission mapping?
12. Những quyền nào cần kiểm tra membership/tenant/owner ở request time?
13. Nếu role bị thu hồi sau phát token, khi nào API phải ngừng cho phép?
14. Các cache authorization/introspection có staleness và failure mode thế nào?
15. Domain service hoặc event consumers nào vẫn đang đọc trực tiếp provider claims?
16. Có test contract đủ cho issuer cũ, issuer mới và role không xác định không?
17. Có ghi audit nguồn quyền, mapping version và quyết định chính sách không?
18. Việc đổi issuer có kéo theo migration account IDs hoặc thay đổi privacy boundary không?

Đây là các câu hỏi cho **thiết kế hợp đồng xác thực và phân quyền**, không phải câu hỏi mà controller phải tự giải quyết ở mọi request.

## 28. Kết luận: adapter biết issuer, domain chỉ biết nghiệp vụ

Có thể ghi nhớ bằng một nguyên tắc:

~~~text
Issuer-specific claim names:
  realm_access, resource_access, scp, permissions, groups
                  |
                  v
     Trusted integration/adapter boundary
                  |
                  v
Application vocabulary:
  ApplicationActor
  BusinessPermission.ORDER_EDIT
  BusinessPermission.ORDER_APPROVE
                  |
                  v
Domain authorization:
  mayEditOrder(actor, order)
  mayApproveOrder(actor, order)
~~~

Những điểm cần giữ:

1. **Không viết chính sách nghiệp vụ dựa trên tên claim riêng của issuer.**
2. **Để JwtDecoder/introspection xác thực token trước khi đọc claims như quyền đáng tin.**
3. **Map external roles/scopes bằng allow-list có nguồn issuer và audience rõ ràng.**
4. **Giữ mô hình permission và principal nội bộ ổn định**, kể cả khi provider đổi tên claim.
5. **Không suy ra quyền chỉ từ role string giống nhau** giữa những issuer khác nhau.
6. **Phân biệt identity, token grant và domain permission**, đặc biệt với multi-tenant và client credentials.
7. **Tách coarse permission khỏi object-level authorization**; một role không cho phép mọi hành động với mọi bản ghi.
8. **Quyền trong token có thể lỗi thời**; nếu cần thu hồi nhanh, phải có current policy/revocation mechanism.
9. **Thiếu hoặc không hiểu claim thì không tự cấp quyền**, và không tải issuer/JWKS bất kỳ từ token chưa xác thực.
10. **Khi thay Identity Provider, sửa adapter và trust config**; giữ quy tắc nghiệp vụ trong domain không phụ thuộc vendor.

**Kết luận:** Resource Server có nhiệm vụ xác minh **ai đã phát hành credential, credential dành cho API nào và được phép mang quyền nào**. Lớp adapter chuyển những claim đặc thù thành mô hình chuẩn hóa. Domain policy chỉ dùng **ngữ nghĩa quyền của hệ thống** và dữ liệu tài nguyên để quyết định hành động. Nhờ vậy, đổi nhà phát hành không làm đổi cách bảo vệ nghiệp vụ, đồng thời tránh những lỗi cấp quyền từ claim sai ngữ cảnh.

## 29. Tài liệu tham khảo

- **Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet):** cấu hình JWT, converter authorities, issuer/audience validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — OAuth 2.0 Resource Server Opaque Token:** introspection và principal/authorities cho opaque token. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Method Security:** @EnableMethodSecurity, @PreAuthorize và domain policy. https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- **Spring Security API — JwtAuthenticationConverter:** ánh xạ Jwt thành Authentication. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- **Spring Security API — JwtGrantedAuthoritiesConverter:** quy tắc ánh xạ scope sang authorities. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- **RFC 6749 — OAuth 2.0 Authorization Framework:** scope và ý nghĩa access token. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách sử dụng bearer access token và lỗi. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** các claim iss, sub, aud, exp. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** issuer/audience validation và tránh token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** các điều kiện JWT access token profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác thực token thông qua AS và metadata liên quan. https://www.rfc-editor.org/rfc/rfc7662
