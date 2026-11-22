# Tuần tự hóa principal, attributes và metadata của token

## 1. Vì sao JDBC persistence cần tuần tự hóa?

Trong mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**. Bài này tập trung vào cách Spring Authorization Server chuyển `OAuth2Authorization` thành dữ liệu có thể lưu trong JDBC và khôi phục lại đối tượng đó khi một protocol endpoint cần tra cứu.

Một authorization không chỉ có authorization code, access token hay refresh token. Trong suốt flow, Authorization Server còn giữ thông tin client, principal, authorization request, scope đã cấp, claims và trạng thái của từng token. Các thông tin này cần tồn tại sau khi request HTTP kết thúc, vì những request sau có thể cần:

- đổi authorization code lấy token;
- dùng refresh token để phát hành access token mới;
- introspect hoặc revoke token;
- xử lý OIDC ID Token, device code hoặc các grant khác;
- kiểm tra token đã hết hạn hay bị invalidated;
- khôi phục ngữ cảnh authorization trên một instance khác trong cluster.

Với `JdbcOAuth2AuthorizationService`, Spring Authorization Server ánh xạ một `OAuth2Authorization` thành các cột của bảng `oauth2_authorization`. Những cấu trúc dạng `Map` như authorization attributes và token metadata được tuần tự hóa thành JSON. Khi đọc, `OAuth2AuthorizationRowMapper` giải mã JSON và dựng lại authorization cùng các token tương ứng.

**Phạm vi ví dụ:** các API và code trong bài theo Spring Authorization Server **1.5.x**, đối chiếu API 1.5.8 và Jackson 2. Ở nhánh major mới sử dụng Jackson 3, tên module và mapper thay đổi; không trộn code của hai thế hệ.

Sau bài này, bạn có thể:

1. Phân biệt `principalName`, `attributes` và token metadata trong `OAuth2Authorization`.
2. Hiểu dữ liệu nào được lưu ở cột riêng và dữ liệu nào được lưu dưới dạng JSON.
3. Mô tả vai trò của `OAuth2AuthorizationParametersMapper` và `OAuth2AuthorizationRowMapper`.
4. Cấu hình Jackson modules để lưu và khôi phục principal cùng các security attributes.
5. Tích hợp custom principal hoặc custom attributes theo cách ổn định.
6. Bảo vệ quá trình polymorphic deserialization và quản lý thay đổi schema/type qua nhiều phiên bản.
7. Viết round-trip test để chứng minh authorization có thể được khôi phục chính xác.

## 2. Mô hình dữ liệu OAuth2Authorization

### 2.1. Authorization là aggregate lưu trạng thái của một flow

`OAuth2Authorization` biểu diễn trạng thái authorization đã được cấp cho một client. Đối tượng này gồm định danh authorization, client, principal, grant type, scope, các token và attributes bổ sung.

```java
public class OAuth2Authorization implements Serializable {
    private String id;
    private String registeredClientId;
    private String principalName;
    private AuthorizationGrantType authorizationGrantType;
    private Set<String> authorizedScopes;
    private Map<Class<? extends OAuth2Token>, Token<?>> tokens;
    private Map<String, Object> attributes;
}
```

Các token phụ thuộc grant:

| Grant/flow | Token thường được liên kết |
| --- | --- |
| OAuth2 Authorization Code | Authorization Code, Access Token, tùy chọn Refresh Token |
| OIDC Authorization Code | Authorization Code, ID Token, Access Token, tùy chọn Refresh Token |
| Client Credentials | Access Token |
| Device Authorization | Device Code, User Code và Access Token khi flow hoàn tất |

Mỗi token có thể có thời điểm phát hành, hết hạn, token value và metadata riêng. `OAuth2Authorization.Token` còn cung cấp trạng thái `isExpired()`, `isInvalidated()` và `isActive()`.

### 2.2. principalName không phải toàn bộ Principal

Hai trường dễ bị nhầm:

- `principalName`: chuỗi tên principal, ví dụ username, subject hoặc client ID. Spring dùng giá trị này cho tra cứu và các thao tác liên quan.
- `attributes`: map chứa ngữ cảnh authorization. Trong Authorization Code Flow, map có thể chứa đối tượng `Authentication` đã xác thực và `OAuth2AuthorizationRequest`.

Ví dụ:

```java
OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(authentication.getName())
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizedScopes(authorizedScopes)
        .attribute(Principal.class.getName(), authentication)
        .attribute(
                OAuth2AuthorizationRequest.class.getName(),
                authorizationRequest
        )
        .build();
```

`principal_name` trong SQL chỉ lưu chuỗi `authentication.getName()`. Đối tượng `Authentication` nằm trong `attributes` mới là phần cần serializer/deserializer hiểu được. Khi khôi phục row, `principalName` có thể vẫn đọc được dù object principal trong attributes không deserialize được; khi đó một số bước của authorization flow vẫn có thể lỗi.

Không giả định rằng implement `Serializable` là đủ. `Serializable` chỉ nói về Java native serialization contract. JDBC mapper của Spring Authorization Server 1.5.x dùng Jackson JSON cho các map metadata; custom principal cần tương thích với ObjectMapper được cấu hình.

### 2.3. attributes lưu dữ liệu gì?

`attributes` là map mở rộng cho trạng thái của flow. Những giá trị thường gặp:

| Attribute | Vai trò |
| --- | --- |
| `Principal.class.getName()` | Authentication/Principal đã xác thực |
| `OAuth2AuthorizationRequest.class.getName()` | Authorization request được giữ qua redirect/callback |
| Các thuộc tính grant riêng | Ngữ cảnh bổ sung của custom grant hoặc extension |

Các key phải nhất quán giữa lúc tạo authorization và lúc đọc lại. Nếu code tùy biến tự thêm một object vào map, bạn cũng chịu trách nhiệm bảo đảm object đó có thể tuần tự hóa và khôi phục.

### 2.4. Token metadata khác token value

Mỗi token trong `OAuth2Authorization` được bọc bởi `OAuth2Authorization.Token`, có:

- token value;
- issued-at và expires-at;
- metadata bổ sung, ví dụ claims đã tạo hoặc dấu hiệu invalidated.

Metadata thường được truy cập qua `authorization.getToken(...).getMetadata()`. Claims của JWT/ID Token được lưu trong metadata với key `OAuth2Authorization.Token.CLAIMS_METADATA_NAME`. Token value được lưu riêng ở cột tương ứng.

Vì vậy, lưu metadata không đồng nghĩa lưu toàn bộ JWT object. Mapper lưu token string, thời gian, token type/scope và metadata theo cấu trúc cột của bảng.

## 3. JDBC serialization pipeline

### 3.1. Hai chiều ánh xạ

`JdbcOAuth2AuthorizationService` sử dụng hai thành phần:

| Thành phần | Hướng | Nhiệm vụ |
| --- | --- | --- |
| `OAuth2AuthorizationParametersMapper` | Java → SQL | Chuyển `OAuth2Authorization` thành danh sách `SqlParameterValue` để INSERT/UPDATE |
| `OAuth2AuthorizationRowMapper` | SQL → Java | Đọc `ResultSet`, parse attributes/metadata và dựng lại `OAuth2Authorization` |

Luồng ghi:

```text
OAuth2Authorization
       |
       v
OAuth2AuthorizationParametersMapper
       |
       +-- scalar fields -> VARCHAR / TIMESTAMP
       |
       +-- attributes Map -> JSON
       |
       +-- each token value -> token column
       |
       +-- each token metadata Map -> JSON
       |
       v
JdbcOperations -> INSERT or UPDATE oauth2_authorization
```

Luồng đọc:

```text
ResultSet
   |
   v
OAuth2AuthorizationRowMapper
   |
   +-- registered_client_id -> RegisteredClientRepository
   |
   +-- scalar columns -> builder fields
   |
   +-- attributes JSON -> Map<String, Object>
   |
   +-- token value + timestamps + metadata JSON -> token objects
   |
   v
OAuth2Authorization
```

### 3.2. Cách save hoạt động

Ở mức khái niệm, `save(authorization)` kiểm tra authorization đã tồn tại theo ID hay chưa. Nếu chưa có thì INSERT; nếu đã có thì UPDATE. Mapper tạo tham số SQL theo thứ tự mà câu lệnh của implementation mong đợi.

`findById(...)` và `findByToken(...)` dùng RowMapper để dựng lại object. `findByToken(...)` có thể tìm theo token type cụ thể hoặc dò các loại token được hỗ trợ nếu caller chưa chỉ định loại.

Không tự viết câu SQL INSERT có ít cột hơn rồi gọi mapper mặc định. Danh sách tham số và schema phải tương thích với nhau; nếu thay schema, cần thay cả mapper và câu lệnh tương ứng hoặc dùng implementation `OAuth2AuthorizationService` riêng.

### 3.3. JSON được lưu trong các cột metadata

Các cột quan trọng trong schema chuẩn gồm:

| Cột | Dữ liệu |
| --- | --- |
| `id`, `registered_client_id`, `principal_name`, `authorization_grant_type` | Định danh và thông tin authorization |
| `authorized_scopes`, `state` | Scope và state có dạng scalar/string |
| `attributes` | JSON map chứa principal/authentication và authorization request attributes |
| `authorization_code_value`, `authorization_code_issued_at`, `authorization_code_expires_at` | Authorization code và thời gian |
| `authorization_code_metadata` | JSON metadata của authorization code |
| `access_token_value`, `access_token_issued_at`, `access_token_expires_at`, `access_token_type`, `access_token_scopes` | Access token và thuộc tính truy vấn |
| `access_token_metadata` | JSON metadata/claims của access token |
| `oidc_id_token_value`, `oidc_id_token_issued_at`, `oidc_id_token_expires_at` | ID Token và thời gian |
| `oidc_id_token_metadata` | JSON metadata/claims của ID Token |
| `refresh_token_value`, `refresh_token_issued_at`, `refresh_token_expires_at` | Refresh token và thời gian |
| `refresh_token_metadata` | JSON metadata của refresh token |
| `user_code_value`, `user_code_issued_at`, `user_code_expires_at`, `user_code_metadata` | User Code và metadata |
| `device_code_value`, `device_code_issued_at`, `device_code_expires_at`, `device_code_metadata` | Device Code và metadata |

Schema chuẩn sử dụng kiểu LOB cho các trường dữ liệu lớn. `JdbcOAuth2AuthorizationService` kiểm tra metadata cột và dùng `LobHandler` để đọc/ghi BLOB hoặc CLOB theo kiểu thực tế của database. Khi dùng schema do tổ chức tự thiết kế, cần kiểm tra kiểu cột và khả năng binding của JDBC driver.

## 4. Jackson mặc định trong Spring Authorization Server 1.5.x

### 4.1. Không phải Java ObjectOutputStream

`OAuth2Authorization` triển khai `Serializable`, nhưng `JdbcOAuth2AuthorizationService` 1.5.x không mặc định ghi toàn bộ object bằng `ObjectOutputStream`. Implementation dùng JSON mapper để tuần tự hóa các map `attributes` và token metadata, sau đó bind chuỗi JSON vào cột LOB.

Điều này có một hệ quả quan trọng: một object Java có thể triển khai `Serializable` nhưng vẫn không thể serialize/deserialize bằng Jackson nếu thiếu getter, constructor, creator hoặc serializer phù hợp.

### 4.2. SecurityJackson2Modules

Spring Security cung cấp `SecurityJackson2Modules.getModules(classLoader)` để tìm các Jackson modules dành cho security types trong classpath. Các module này đăng ký mixin/serializer cần thiết cho những kiểu Spring Security như Authentication và các cấu trúc liên quan.

### 4.3. OAuth2AuthorizationServerJackson2Module

Spring Authorization Server cung cấp `OAuth2AuthorizationServerJackson2Module`. Module này đăng ký mixin cho các kiểu của Authorization Server, bao gồm:

- `OAuth2AuthorizationRequest`;
- map/set không sửa đổi;
- `Duration`;
- `JwsAlgorithm`;
- `OAuth2TokenFormat`;
- các kiểu dữ liệu khác được dùng trong authorization attributes/settings.

Module cũng bật default typing khi cần type information để khôi phục object có kiểu cụ thể. Khi map JSON trở lại `Map<String, Object>`, type metadata giúp Jackson biết giá trị thực là kiểu nào, thay vì chỉ khôi phục thành `LinkedHashMap` hoặc một kiểu chung.

Ví dụ khởi tạo ObjectMapper theo hướng dẫn của Spring:

```java
ObjectMapper objectMapper = new ObjectMapper();
ClassLoader classLoader = getClass().getClassLoader();

objectMapper.registerModules(
        SecurityJackson2Modules.getModules(classLoader)
);
objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module()
);
```

Không tạo ObjectMapper hoàn toàn tùy ý rồi bỏ qua các module này nếu authorization attributes chứa các kiểu Spring Security/Spring Authorization Server. JSON có thể ghi được nhưng lỗi khi đọc lại, đặc biệt khi gặp `Authentication`, `OAuth2AuthorizationRequest`, immutable collection hoặc token-specific type.

### 4.4. Type metadata là một phần của định dạng lưu trữ

Với map có kiểu giá trị là `Object`, cùng một key có thể chứa `String`, `Instant`, `Authentication`, `OAuth2AuthorizationRequest` hoặc một custom principal. JSON cần có thông tin kiểu để khôi phục object chính xác.

Ví dụ khái niệm:

```json
{
  "principal": {
    "@class": "com.example.security.ApplicationPrincipal",
    "userId": "u-1001",
    "tenantId": "tenant-a"
  }
}
```

Tên field type marker trong JSON thực tế phụ thuộc ObjectMapper và cấu hình typing; đoạn trên chỉ minh họa ý tưởng. Không dựa vào tên marker cụ thể để viết SQL query hoặc xử lý dữ liệu bằng tay.

## 5. Tuần tự hóa custom principal và attributes

### 5.1. Ưu tiên principal gọn, ổn định

Principal được giữ trong authorization attributes có thể sống lâu hơn request web đã tạo ra nó. Hãy dùng một DTO có các trường cần thiết cho flow, ví dụ user ID, tenant ID và display name. Tránh nhét toàn bộ JPA entity hoặc object phụ thuộc request/session vào attributes.

```java
import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.security.core.AuthenticatedPrincipal;

public final class ApplicationPrincipal implements AuthenticatedPrincipal, Serializable {

    private static final long serialVersionUID = 1L;

    private final String userId;
    private final String tenantId;
    private final String displayName;

    @JsonCreator
    public ApplicationPrincipal(
            @JsonProperty("userId") String userId,
            @JsonProperty("tenantId") String tenantId,
            @JsonProperty("displayName") String displayName) {
        this.userId = userId;
        this.tenantId = tenantId;
        this.displayName = displayName;
    }

    public String getUserId() {
        return userId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getDisplayName() {
        return displayName;
    }

    @Override
    public String getName() {
        return userId;
    }
}
```

`Serializable` trong ví dụ giúp tương thích với các thành phần Java có thể yêu cầu contract này, nhưng khả năng round-trip trong JDBC vẫn đến từ Jackson annotations/module và ObjectMapper. Hãy viết test serialize/deserialize với đúng mapper production đang dùng.

### 5.2. Không lưu credential vào principal

Không đưa password thô, password hash, OTP, recovery code, client secret hoặc credential nhạy cảm vào custom principal chỉ để có thể khôi phục `Authentication`. Security context của authorization flow cần danh tính và authorities cần thiết, không cần giữ bí mật đăng nhập của người dùng trong bản ghi authorization.

Nếu principal hiện tại chứa quá nhiều dữ liệu, hãy tạo principal snapshot đã được làm sạch trước khi đưa vào authorization attributes. Đừng kỳ vọng Jackson tự biết field nào cần loại bỏ.

### 5.3. Đưa custom principal vào authorization

Ví dụ một service có thể lưu Authentication đã được làm sạch trong attributes:

```java
Authentication authorizationPrincipal =
        UsernamePasswordAuthenticationToken.authenticated(
                applicationPrincipal,
                null,
                authorities
        );

OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(authorizationPrincipal.getName())
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizedScopes(authorizedScopes)
        .attribute(Principal.class.getName(), authorizationPrincipal)
        .attribute(
                OAuth2AuthorizationRequest.class.getName(),
                authorizationRequest
        )
        .build();
```

Đây là ví dụ minh họa cách đặt attribute; hãy để Spring Authorization Server tạo/cập nhật authorization trong grant flow chuẩn thay vì tự dựng authorization thay thế các AuthenticationProvider mặc định. Khi customize provider hoặc grant, bảo đảm principal được lưu bằng đúng key mà thành phần đọc lại mong đợi.

### 5.4. Khi nào cần custom serializer/deserializer?

Bạn có thể cần custom serializer khi:

- principal là kiểu domain riêng không có constructor/getter mà Jackson hiểu được;
- principal chứa dữ liệu chỉ có thể khôi phục bằng service lookup;
- cần đổi cấu trúc JSON nhưng vẫn đọc được các row cũ;
- custom authentication token chứa kiểu attribute riêng;
- muốn chỉ lưu một snapshot nhỏ thay vì cả object graph.

Có ba cách thường dùng:

1. Thiết kế DTO dễ serialize, có `@JsonCreator` và `@JsonProperty`.
2. Đăng ký Jackson mixin cho class hiện có mà không sửa source của class đó.
3. Đăng ký custom `JsonSerializer`/`JsonDeserializer` trong `SimpleModule`.

Nếu deserializer cần truy vấn database hoặc service, hãy cân nhắc tạo một principal snapshot rõ ràng thay vì nhúng dependency vào serializer. Serialization nên là phép chuyển đổi dữ liệu có thể kiểm thử, không nên trở thành một service locator ẩn.

## 6. Tùy biến ObjectMapper cho JdbcOAuth2AuthorizationService

### 6.1. Khi nào cần thay ObjectMapper mặc định?

Không cần thay mapper nếu các kiểu principal/attributes đang dùng đã được các Spring Jackson modules hỗ trợ. Chỉ tùy biến khi có custom type hoặc định dạng JSON riêng mà mapper mặc định không thể khôi phục.

`JdbcOAuth2AuthorizationService` 1.5.x cho phép thay cả hai mapper:

- `setAuthorizationParametersMapper(...)` cho chiều ghi;
- `setAuthorizationRowMapper(...)` cho chiều đọc.

Hai chiều phải dùng ObjectMapper tương thích với nhau. Nếu chỉ thay mapper chiều ghi, dữ liệu mới có thể được lưu nhưng không đọc lại được. Nếu chỉ thay mapper chiều đọc, dữ liệu cũ có thể đọc được nhưng lần save kế tiếp lại dùng định dạng khác.

### 6.2. Cấu hình ObjectMapper dùng chung

Ví dụ sau minh họa cấu hình Jackson 2 cho một custom principal. `SecurityJackson2Modules` và `OAuth2AuthorizationServerJackson2Module` giữ các mixin/type support mà Spring cần; `JavaTimeModule` hữu ích nếu custom DTO có trường `Instant`, `LocalDate` hoặc `Duration`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.jackson2.OAuth2AuthorizationServerJackson2Module;

@Configuration
public class AuthorizationPersistenceConfig {

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcOperations jdbcOperations,
            RegisteredClientRepository registeredClientRepository) {

        JdbcOAuth2AuthorizationService service =
                new JdbcOAuth2AuthorizationService(
                        jdbcOperations,
                        registeredClientRepository
                );

        ObjectMapper objectMapper = new ObjectMapper();
        ClassLoader classLoader = getClass().getClassLoader();
        objectMapper.registerModules(
                SecurityJackson2Modules.getModules(classLoader)
        );
        objectMapper.registerModule(
                new OAuth2AuthorizationServerJackson2Module()
        );
        objectMapper.registerModule(new JavaTimeModule());

        JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper
                parametersMapper =
                new JdbcOAuth2AuthorizationService
                        .OAuth2AuthorizationParametersMapper();
        parametersMapper.setObjectMapper(objectMapper);

        JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper rowMapper =
                new JdbcOAuth2AuthorizationService
                        .OAuth2AuthorizationRowMapper(
                                registeredClientRepository
                        );
        rowMapper.setObjectMapper(objectMapper);

        service.setAuthorizationParametersMapper(parametersMapper);
        service.setAuthorizationRowMapper(rowMapper);

        return service;
    }
}
```

Đây là cấu hình đầy đủ cho service riêng. Nếu ứng dụng đã khai báo `OAuth2AuthorizationService` bean hoặc có filter chain Authorization Server, hãy đưa bean này vào cấu hình hiện tại. Ví dụ wiring trong configurer:

```java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.authorizationService(authorizationService)
    );
```

Schema `oauth2_authorization` phải được tạo trước khi service khởi tạo. `JdbcOAuth2AuthorizationService` dùng `JdbcOperations` và `RegisteredClientRepository`; row mapper tra cứu `registered_client_id` để lấy `RegisteredClient` rồi mới dựng `OAuth2Authorization`.

### 6.3. Mixin cho custom principal

Nếu không thể thêm Jackson annotation vào class principal, có thể khai báo mixin:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

abstract class ApplicationPrincipalMixin {

    @JsonCreator
    ApplicationPrincipalMixin(
            @JsonProperty("userId") String userId,
            @JsonProperty("tenantId") String tenantId,
            @JsonProperty("displayName") String displayName) {
    }
}
```

Đăng ký mixin trước khi gắn ObjectMapper vào hai mapper JDBC:

```java
objectMapper.addMixIn(
        ApplicationPrincipal.class,
        ApplicationPrincipalMixin.class
);
```

Nếu class cần serializer/deserializer riêng, đăng ký `SimpleModule`:

```java
SimpleModule applicationModule = new SimpleModule("application-authorization-types");
applicationModule.addSerializer(
        ApplicationPrincipal.class,
        new ApplicationPrincipalSerializer()
);
applicationModule.addDeserializer(
        ApplicationPrincipal.class,
        new ApplicationPrincipalDeserializer()
);
objectMapper.registerModule(applicationModule);
```

`ApplicationPrincipalSerializer` và `ApplicationPrincipalDeserializer` ở đây là các lớp do ứng dụng định nghĩa. Khi dùng custom serializer, hãy bảo đảm JSON có đủ dữ liệu để khôi phục cùng một logical principal và vẫn tương thích với những authorization record đã lưu trước đó.

### 6.4. Không thay mapper chỉ để đổi tên JSON

`OAuth2AuthorizationParametersMapper` phải trả đúng danh sách `SqlParameterValue` theo schema và câu lệnh SQL mà `JdbcOAuth2AuthorizationService` sử dụng. Nếu chỉ muốn đổi cách serialize một custom type, hãy tùy biến ObjectMapper/module trước. Chỉ thay toàn bộ mapper khi thật sự cần thay cách ánh xạ cột, và khi đó phải chịu trách nhiệm giữ đúng thứ tự, SQL type, nullability và đối xứng đọc/ghi.

## 7. Token metadata và claims

### 7.1. Metadata được lưu theo từng token

`OAuth2Authorization.Token` giữ metadata riêng cho token. Các map metadata này được ghi vào cột tương ứng:

| Token | Cột metadata | Nội dung thường gặp |
| --- | --- | --- |
| Authorization Code | `authorization_code_metadata` | Trạng thái và metadata liên quan code |
| Access Token | `access_token_metadata` | Claims, trạng thái invalidated và metadata bổ sung |
| OIDC ID Token | `oidc_id_token_metadata` | ID Token claims và metadata |
| Refresh Token | `refresh_token_metadata` | Metadata liên quan refresh token |
| User Code | `user_code_metadata` | Metadata device authorization |
| Device Code | `device_code_metadata` | Metadata device authorization |

Một số giá trị metadata được Spring quản lý nội bộ. Không tự đặt key trùng với key reserved của framework hoặc ghi đè claims metadata bằng object không tương thích.

### 7.2. Claims của JWT và ID Token

Khi token được tạo bằng `JwtGenerator`, claims có thể được giữ trong `OAuth2Authorization.Token` metadata. Với OIDC, ID Token claims được giữ trong `oidc_id_token_metadata`; khi row mapper dựng lại `OidcIdToken`, mapper đọc claims từ metadata bằng `OAuth2Authorization.Token.CLAIMS_METADATA_NAME`.

Điều này có nghĩa:

- cột `oidc_id_token_value` giữ compact ID Token string;
- cột `oidc_id_token_metadata` giữ metadata/claims cần cho model;
- cột thời gian giữ `issued_at` và `expires_at`.

Tương tự, Access Token có value, type, scopes, issued/expiry và metadata riêng. Không suy ra rằng metadata map là nguồn xác minh chữ ký token; chữ ký và token value vẫn được xử lý theo token format và validator của protocol.

### 7.3. Custom token metadata

Nếu ứng dụng thêm metadata riêng cho token, hãy:

1. Chọn key có namespace riêng, tránh đụng key framework.
2. Chỉ lưu dữ liệu cần thiết để xử lý authorization/introspection/revocation.
3. Dùng kiểu dữ liệu Jackson có thể đọc lại ổn định.
4. Không lưu secret, private key hoặc dữ liệu credential không cần thiết.
5. Bảo đảm các instance trong cluster dùng cùng module và phiên bản DTO.

Ví dụ thêm một metadata value vào token builder chỉ có ý nghĩa khi bạn đang ở extension point tạo/cập nhật authorization phù hợp:

```java
authorizationBuilder.token(accessToken, metadata -> {
    metadata.put("com.example.policy.version", "2026-01");
    metadata.put("com.example.risk.level", "standard");
});
```

Đây là ví dụ minh họa cách đặt metadata trong builder; đừng sửa authorization record trực tiếp ở một nơi không nằm trong lifecycle của grant. Nếu metadata được dùng để ra quyết định bảo mật, cần kiểm tra tính toàn vẹn, nguồn tạo và thời điểm cập nhật của nó.

## 8. Bảo mật khi deserialize authorization data

### 8.1. Database là nguồn dữ liệu có ảnh hưởng tới quá trình khôi phục object

JSON trong `attributes` có thể chứa type metadata. Khi Jackson khôi phục map, nó có thể cần nạp lại một class cụ thể. Vì vậy, người có thể sửa nội dung cột `attributes` hoặc token metadata có thể tác động đến quá trình deserialize.

Các nguyên tắc:

- Chỉ tài khoản service của Authorization Server được ghi vào bảng authorization.
- Giới hạn quyền đọc/ghi trực tiếp database và audit thay đổi ngoài ứng dụng.
- Không nhận JSON authorization từ client rồi deserialize bằng ObjectMapper nội bộ.
- Không bật polymorphic typing tùy tiện trên endpoint nhận dữ liệu không tin cậy.
- Nếu bổ sung custom type, giới hạn class được phép và giữ danh sách type nhỏ.
- Kiểm tra serializer/deserializer trước khi triển khai vào production.

### 8.2. Default typing và allowlist

Spring Security/Spring Authorization Server dùng type metadata vì map có giá trị đa hình cần được khôi phục đúng class. Không nên tự ý tắt typing mà không kiểm tra các security types cần thiết. Đồng thời, không mở rộng typing cho mọi class trong ứng dụng nếu không có lý do.

Với custom principal, ưu tiên DTO rõ ràng và các kiểu scalar. Nếu phiên bản Jackson/security module hỗ trợ polymorphic type validator tùy chỉnh, cấu hình allowlist cho package/class của ứng dụng thay vì cho phép bất kỳ class nào. Đặc biệt tránh deserialization từ JSON do người dùng, client hoặc một nguồn ngoài kiểm soát gửi lên.

### 8.3. Giảm dữ liệu nhạy cảm trong attributes

Không đưa vào authorization attributes:

- password thô hoặc password hash;
- bản sao refresh token hoặc credential khác được nhét vào attributes ngoài token model;
- private key, signing key hoặc client secret;
- HTTP request/response object;
- servlet session, connection, service bean hoặc JPA persistence context;
- object graph chứa quan hệ lazy/cyclic không cần thiết.

Principal snapshot nên chỉ gồm subject, tenant, authorities cần thiết và các thuộc tính ổn định mà flow thực sự dùng. Những thông tin có thể tra lại từ user service nên cân nhắc lưu ID thay vì lưu cả entity.

### 8.4. Bảo vệ token value trong database

Schema authorization lưu token value ở các cột riêng như authorization code, access token, ID Token, refresh token, user code và device code. Các giá trị này là credential có thể bị sử dụng nếu bị lộ; không mặc định rằng JDBC service đã hash hoặc mã hóa từng token trước khi ghi.

- Bật encryption at rest cho database, volume, snapshot và backup theo tiêu chuẩn vận hành của tổ chức.
- Dùng TLS cho kết nối ứng dụng tới database và giới hạn quyền đọc bảng authorization.
- Không log token value, JSON attributes hoặc metadata có thể chứa claims nhạy cảm.
- Không sao chép bảng authorization sang môi trường analytics/dev mà chưa loại bỏ hoặc bảo vệ credential.
- Áp dụng retention/cleanup cho authorization đã hết hạn hoặc bị thu hồi, phù hợp yêu cầu audit và khả năng khôi phục.

## 9. Tương thích phiên bản và thay đổi cấu trúc dữ liệu

### 9.1. Class name cũng có thể trở thành một phần của dữ liệu lưu

Khi JSON chứa type metadata, tên class/package của custom principal có thể xuất hiện trong nội dung đã lưu. Nếu đổi package, đổi tên class hoặc xóa module khỏi classpath, những authorization record cũ có thể không deserialize được.

Trước khi refactor custom principal:

1. Xác định các authorization còn tồn tại có chứa class đó.
2. Giữ class cũ hoặc cung cấp compatibility mixin/deserializer trong giai đoạn chuyển tiếp.
3. Chuyển đổi dữ liệu cũ sang format mới bằng migration có kiểm thử.
4. Chỉ xóa class cũ sau khi không còn row cần đọc bằng format trước.

### 9.2. Rolling deployment trong cluster

Nếu nhiều Authorization Server instance cùng đọc/ghi một database, tất cả instance phải hiểu được format mà instance khác tạo ra. Không triển khai node mới ghi JSON type mới trong khi node cũ không biết class đó.

Quy trình an toàn:

- triển khai phiên bản có thể **đọc cả format cũ và mới** trước;
- sau đó mới chuyển writer sang format mới;
- migrate row còn sống nếu cần;
- cuối cùng mới loại bỏ compatibility reader cũ.

Nếu không thể hỗ trợ dual-read, dùng maintenance window hoặc đảm bảo các authorization cũ hết hạn/được thu hồi trước khi đổi format.

### 9.3. Schema migration và JSON migration là hai việc khác nhau

Thay đổi kiểu cột SQL (ví dụ BLOB sang CLOB) là schema migration. Thay đổi cấu trúc JSON hoặc tên class trong `attributes` là data-format migration. Một migration có thể cần cả hai, nhưng chúng không tự động đồng bộ.

Không chỉnh trực tiếp cột metadata bằng SQL nếu chưa hiểu type information, escaping và mapper đang dùng. Với dữ liệu JSON có polymorphic type, thao tác find/replace trên class name có thể làm hỏng JSON hoặc thay nhầm chuỗi nội dung.

### 9.4. Jackson 2 và Jackson 3

Ví dụ trong bài sử dụng API Jackson 2 của Spring Authorization Server 1.5.x:

- `SecurityJackson2Modules`;
- `OAuth2AuthorizationServerJackson2Module`;
- `OAuth2AuthorizationParametersMapper`;
- `OAuth2AuthorizationRowMapper`.

Ở dòng Spring Security 7 / Authorization Server major mới chuyển sang Jackson 3, các module và mapper tương ứng có tên/API mới, ví dụ `SecurityJacksonModules`, `OAuth2AuthorizationServerJacksonModule` và các mapper `JsonMapper...`. Khi nâng major version, đọc API docs đúng version và chạy migration/round-trip test trước khi dùng chung database với instance cũ.

## 10. Kiểm thử round-trip serialization

### 10.1. Những gì cần chứng minh

Test quan trọng nhất không chỉ kiểm tra JSON có được ghi, mà phải chứng minh object khôi phục được vẫn có cùng logical state:

- `principalName` không đổi;
- custom principal vẫn đúng class và field;
- authorization request attributes vẫn khôi phục;
- authorized scopes vẫn giữ nguyên;
- token value, type, issued-at và expires-at đúng;
- token metadata/claims được giữ lại;
- invalidated metadata không bị mất;
- `findByToken(...)` vẫn tìm được authorization.

### 10.2. Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| JDBC-SER-01 | Lưu và đọc authorization chỉ có scalar fields | ID, client ID, principal name và grant type khớp |
| JDBC-SER-02 | Attributes có `Authentication` chuẩn của Spring Security | Deserialize thành đúng security type |
| JDBC-SER-03 | Attributes có `OAuth2AuthorizationRequest` | Request được khôi phục cùng các parameter cần thiết |
| JDBC-SER-04 | Attributes có custom principal DTO | Khôi phục đúng class và field |
| JDBC-SER-05 | Custom principal thiếu creator/getter phù hợp | Test phát hiện lỗi deserialize |
| JDBC-SER-06 | Token metadata có string/boolean/number/map | JSON round-trip giữ đúng giá trị và kiểu mong đợi |
| JDBC-SER-07 | Access Token có claims metadata | Claims được khôi phục |
| JDBC-SER-08 | OIDC ID Token có claims metadata | `OidcIdToken` được dựng lại với claims |
| JDBC-SER-09 | Token có metadata invalidated | Trạng thái invalidated không bị mất |
| JDBC-SER-10 | Authorization có refresh token | Refresh token value và timestamps khớp |
| JDBC-SER-11 | Authorization có user/device code | Token tương ứng được khôi phục |
| JDBC-SER-12 | Gọi `findByToken` với access token | Trả về đúng authorization |
| JDBC-SER-13 | Gọi `findByToken` với token type cụ thể | Chỉ tìm theo loại token yêu cầu |
| JDBC-SER-14 | `registered_client_id` không còn trong repository | Row mapper báo lỗi khôi phục thay vì dựng authorization thiếu client |
| JDBC-SER-15 | Dùng ObjectMapper chỉ cho chiều ghi | Test đọc lại phát hiện format không tương thích |
| JDBC-SER-16 | Dùng ObjectMapper chỉ cho chiều đọc | Test ghi/đọc phát hiện hai mapper không đồng bộ |
| JDBC-SER-17 | Mapper có SecurityJackson2Modules và SAS module | Spring security attributes khôi phục thành công |
| JDBC-SER-18 | Bỏ OAuth2AuthorizationServerJackson2Module | Test bắt lỗi với authorization request/settings cần mixin |
| JDBC-SER-19 | Thay đổi class/package custom principal | Compatibility test đọc row cũ thành công |
| JDBC-SER-20 | Hai node dùng mapper/version khác nhau | Cluster compatibility test phát hiện lỗi đọc chéo |
| JDBC-SER-21 | Attributes có object không được allowlist | Deserialization bị từ chối theo policy |
| JDBC-SER-22 | Attributes chứa password/credential nhạy cảm | Security test xác nhận dữ liệu không được lưu |
| JDBC-SER-23 | BLOB/CLOB trên database đích | LOB binding và đọc lại hoạt động |
| JDBC-SER-24 | Authorization có attributes lớn | Không cắt cụt dữ liệu; kích thước và latency được đo |
| JDBC-SER-25 | Update authorization đã tồn tại | Các token/metadata mới được cập nhật đúng |
| JDBC-SER-26 | Remove authorization | Row bị xóa và findById/findByToken không còn trả về |

### 10.3. Ví dụ round-trip test ở mức service

Ví dụ khung kiểm thử với Spring JDBC test database:

```java
@SpringBootTest
class JdbcAuthorizationSerializationTests {

    @Autowired
    OAuth2AuthorizationService authorizationService;

    @Test
    void shouldRestoreCustomPrincipalAndTokenMetadata() {
        OAuth2Authorization authorization = createAuthorizationWithCustomPrincipal();

        authorizationService.save(authorization);

        OAuth2Authorization restored =
                authorizationService.findById(authorization.getId());

        assertThat(restored).isNotNull();
        assertThat(restored.getPrincipalName())
                .isEqualTo(authorization.getPrincipalName());

        Object principal = restored.getAttribute(Principal.class.getName());
        assertThat(principal).isInstanceOf(Authentication.class);

        Authentication authentication = (Authentication) principal;
        assertThat(authentication.getPrincipal())
                .isInstanceOf(ApplicationPrincipal.class);

        ApplicationPrincipal restoredPrincipal =
                (ApplicationPrincipal) authentication.getPrincipal();
        assertThat(restoredPrincipal.getUserId()).isEqualTo("u-1001");
        assertThat(restoredPrincipal.getTenantId()).isEqualTo("tenant-a");

        OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
                restored.getToken(OAuth2AccessToken.class);
        assertThat(accessToken).isNotNull();
        assertThat(accessToken.getMetadata())
                .containsEntry("com.example.policy.version", "2026-01");
    }
}
```

`createAuthorizationWithCustomPrincipal()` là fixture do test định nghĩa, phải tạo authorization theo đúng grant và token model của test. Nếu sử dụng database Testcontainers, chạy test với cùng loại database/version mà production dùng để phát hiện khác biệt BLOB/CLOB và SQL dialect.

### 10.4. Kiểm thử mapper riêng

Khi lỗi xảy ra, cô lập mapper trước khi chạy full OAuth flow:

1. Tạo một authorization fixture có attributes và token metadata cần kiểm tra.
2. Dùng `OAuth2AuthorizationParametersMapper.apply(...)` để tạo SQL parameters.
3. Persist và đọc row bằng `OAuth2AuthorizationRowMapper`.
4. So sánh class/value của attributes và metadata.
5. Sau khi round-trip mapper thành công, chạy integration test cho authorization code, refresh token, introspection và revocation.

Không chỉ kiểm tra JSON string bằng snapshot test. Điều quan trọng là object được khôi phục có thể tiếp tục được Spring Authorization Server sử dụng trong protocol flow.

## 11. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `InvalidDefinitionException` khi save | Custom principal không có cấu trúc Jackson có thể serialize | Thêm creator/getter, mixin hoặc serializer |
| `InvalidTypeIdException` khi load | Thiếu type metadata/module hoặc class type không còn trên classpath | Đăng ký đúng modules và giữ compatibility class |
| Principal sau load thành `LinkedHashMap` | Type metadata bị mất hoặc ObjectMapper không dùng typing tương thích | Kiểm tra mapper ở cả hai chiều và JSON cũ |
| Không deserialize được `OAuth2AuthorizationRequest` | Thiếu `OAuth2AuthorizationServerJackson2Module` hoặc security modules | Dùng mapper theo cấu hình Spring |
| Ghi thành công nhưng đọc thất bại | Mapper ghi và đọc khác cấu hình | Dùng chung ObjectMapper/modules |
| `RegisteredClient` không tìm thấy khi map row | `registered_client_id` tham chiếu client đã bị xóa hoặc repository sai | Khôi phục client registration hoặc xử lý retention đúng thứ tự |
| Claims ID Token bị mất | Mapper không lưu/đọc claims metadata đúng key | Kiểm tra `CLAIMS_METADATA_NAME` và `oidc_id_token_metadata` |
| `DataIntegrityViolationException` | Cột quá nhỏ, sai kiểu LOB hoặc dữ liệu vượt giới hạn | Kiểm tra schema, column type và kích thước payload |
| Khôi phục lỗi sau rolling deploy | Node mới ghi type mà node cũ không hiểu | Triển khai compatibility reader trước writer mới |
| Lỗi chỉ xuất hiện trên database production | JDBC driver xử lý BLOB/CLOB khác test database | Kiểm thử với đúng DB engine và `LobHandler` |
| Query authorization chậm khi tải cao | JDBC service mặc định không tối ưu cho throughput rất lớn | Đo query/index/LOB; cân nhắc implementation `OAuth2AuthorizationService` riêng |

### 11.1. Phân biệt lỗi serialization và lỗi lookup

- **Serialization error:** Jackson không ghi được attributes/metadata vào JSON.
- **Deserialization error:** Jackson đọc JSON nhưng không dựng lại được kiểu object.
- **Client lookup error:** RowMapper đọc được `registered_client_id` nhưng `RegisteredClientRepository` không tìm thấy client tương ứng.
- **Schema/LOB error:** JDBC không bind hoặc đọc đúng kiểu cột.

Phân loại đúng giúp sửa đúng tầng. Không giải quyết lỗi deserialize bằng cách xóa `attributes` khỏi database nếu authorization flow còn cần principal hoặc request context đó.

### 11.2. Hiệu năng

Tài liệu Spring mô tả `JdbcOAuth2AuthorizationService` là implementation JDBC đơn giản và lưu ý nó có thể không đáp ứng môi trường cần throughput cao. Đo thực tế:

- số lần gọi `findById`/`findByToken`;
- kích thước JSON trong `attributes` và token metadata;
- chi phí Jackson serialize/deserialize;
- thời gian đọc/ghi LOB;
- index theo token value, authorization ID và các cột filter;
- lock/transaction khi update cùng một authorization.

Nếu cần tối ưu sâu, có thể triển khai `OAuth2AuthorizationService` riêng hoặc mở rộng mapper/query theo workload. Giữ nguyên semantics của save/update/remove/find và trạng thái token; không đánh đổi tính đúng đắn của revocation/introspection để giảm số lần đọc.

## 12. Checklist production và tài liệu đối chiếu

### 12.1. Checklist trước production

- [ ] Đã xác định chính xác Spring Authorization Server version và Jackson major version.
- [ ] `JdbcOAuth2AuthorizationService` dùng schema `oauth2-authorization-schema.sql` tương thích.
- [ ] `RegisteredClientRepository` dùng chung và có đầy đủ client được tham chiếu bởi authorization rows.
- [ ] `SecurityJackson2Modules` và `OAuth2AuthorizationServerJackson2Module` được đăng ký cho Jackson 2 ở nhánh 1.5.x.
- [ ] Cùng ObjectMapper/module được dùng cho parameters mapper và row mapper.
- [ ] Custom principal có serializer/deserializer ổn định và round-trip test.
- [ ] Attributes chỉ chứa dữ liệu cần thiết, không chứa password/secret/private key.
- [ ] Token metadata và claims được kiểm tra sau khi khôi phục.
- [ ] Không deserialize JSON authorization từ nguồn bên ngoài không tin cậy.
- [ ] Type metadata/custom types được giới hạn và quản lý qua phiên bản.
- [ ] Có kế hoạch compatibility cho rolling deployment và class/package rename.
- [ ] Database LOB type đã được kiểm thử với đúng DB engine/JDBC driver.
- [ ] Có round-trip tests cho principal, authorization request, access/refresh/ID token và invalidated metadata.
- [ ] Có metrics về payload size, query latency và serialization latency.
- [ ] Database, volume và backup bảo vệ token values bằng encryption at rest; quyền đọc bảng authorization được giới hạn.
- [ ] Log và telemetry không chứa token value, principal attributes hoặc token metadata nhạy cảm.
- [ ] Có retention/cleanup policy cho authorization rows hết hạn hoặc đã bị thu hồi.

### Bản đồ ghi nhớ

```text
OAuth2Authorization
  |
  +-- id / registeredClientId / principalName / grantType / scopes
  |
  +-- attributes
  |     +-- Authentication / Principal
  |     +-- OAuth2AuthorizationRequest
  |     +-- custom flow attributes
  |
  +-- tokens
        +-- token value + timestamps
        +-- token metadata / claims
                 |
                 v
JdbcOAuth2AuthorizationService
  |
  +-- ParametersMapper
  |      +-- scalar columns
  |      +-- attributes Map -> JSON
  |      +-- token metadata Map -> JSON
  |
  +-- RowMapper
         +-- scalar columns -> builder
         +-- JSON -> typed Map
         +-- registered_client_id -> RegisteredClientRepository
         +-- tokens + metadata -> token objects
                 |
                 v
        OAuth2Authorization restored

Jackson 2 in SAS 1.5.x:
  SecurityJackson2Modules
  + OAuth2AuthorizationServerJackson2Module
  + same ObjectMapper for write and read
```

**Điểm cần nhớ:** `principalName` là chuỗi định danh riêng, còn `Principal`/`Authentication` và `OAuth2AuthorizationRequest` thường được giữ trong `attributes`. Token value, thời gian và token metadata được lưu theo từng loại token. Trong Spring Authorization Server 1.5.x, `JdbcOAuth2AuthorizationService` tuần tự hóa các map này bằng Jackson 2; cần các Spring Security/Spring Authorization Server Jackson modules và cùng ObjectMapper ở cả chiều ghi lẫn chiều đọc. Hãy giữ principal gọn, tránh credential nhạy cảm, quản lý type metadata và kiểm thử round-trip trước khi thay đổi class hoặc format lưu trữ.

## Tài liệu chuẩn để đối chiếu

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization`, attributes, token metadata và `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): constructors, schema requirement, parameters mapper và row mapper.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationParametersMapper API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper.html): ObjectMapper và SQL parameter mapping.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationRowMapper API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper.html): khôi phục `OAuth2Authorization` từ `ResultSet`.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerJackson2Module API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson2/OAuth2AuthorizationServerJackson2Module.html): mixins và type information cần cho JSON serialization.
- [Spring Security — SecurityJackson2Modules API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/jackson2/SecurityJackson2Modules.html): đăng ký các Jackson modules của Spring Security.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình `OAuth2AuthorizationService` trong Authorization Server.

