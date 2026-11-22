# JdbcOAuth2AuthorizationService và schema authorization

Authorization Server phải ghi nhớ trạng thái của các authorization đã cấp để tiếp tục xử lý những request đến sau. Khi client đổi authorization code, refresh access token, introspect token, revoke token hoặc hoàn thành một protocol flow nhiều bước, server cần tìm lại đúng authorization và các token liên quan. Nếu dữ liệu chỉ nằm trong bộ nhớ của một JVM, trạng thái sẽ mất khi process restart và các node khác trong cluster không thể nhìn thấy nó.

Spring Authorization Server cung cấp abstraction **OAuth2AuthorizationService** để lưu và truy vấn **OAuth2Authorization**. **JdbcOAuth2AuthorizationService** là implementation dùng Spring JDBC để ghi authorization vào relational database. Nó đi kèm schema SQL chuẩn và hai mapper để chuyển đổi giữa object model với các cột trong bảng.

Bài học thuộc chương **Lưu trữ JDBC**, module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm ở đây là cấu trúc authorization record, cách cấu hình JdbcOAuth2AuthorizationService, schema oauth2_authorization, vòng đời token và các yêu cầu khi đưa persistence vào production.

> **Điểm cốt lõi:** JdbcOAuth2AuthorizationService lưu một OAuth2Authorization cùng trạng thái của các token gắn với authorization đó. Nó không thay thế RegisteredClientRepository, OAuth2AuthorizationConsentService, session store hay signing-key store. Mỗi thành phần quản lý một loại dữ liệu riêng.

## 1. Vì sao Authorization Server cần persistence?

Một Authorization Server có nhiều protocol flows cần trạng thái bền vững:

- Authorization Code Flow tạo authorization code rồi chờ client đổi code tại token endpoint.
- Refresh Token Flow tìm authorization chứa refresh token, kiểm tra trạng thái và cập nhật token mới.
- Token Introspection tìm authorization theo access token để xác định token còn active hay không.
- Token Revocation tìm authorization và đánh dấu token bị invalidated theo semantics của endpoint.
- Device Authorization Flow lưu device code, user code, thời điểm hết hạn và trạng thái phê duyệt.
- OIDC lưu ID Token và claims liên quan đến authorization.
- Các extension/custom grant có thể lưu thêm attributes hoặc token metadata.

Nếu dùng InMemoryOAuth2AuthorizationService, dữ liệu nằm trong process memory. Sau restart, authorization cũ biến mất. Trong cluster, node A và node B có thể có các bản ghi khác nhau. Điều đó gây ra lỗi như authorization code không tìm thấy, refresh token không được nhận diện hoặc introspection trả inactive dù token vừa được cấp ở node khác.

JDBC persistence giúp các node đọc cùng nguồn dữ liệu và duy trì trạng thái qua restart. Đổi lại, ứng dụng phải thiết kế schema, transaction, index, connection pool, backup, migration và kiểm soát truy cập database.

### 1.1. In-memory và JDBC

| Tiêu chí | InMemoryOAuth2AuthorizationService | JdbcOAuth2AuthorizationService |
|---|---|---|
| Nơi lưu | Heap của JVM | Relational database |
| Restart | Mất authorization | Dữ liệu còn theo database |
| Nhiều node | Mỗi node có state riêng | Có thể dùng chung database |
| Thiết lập | Đơn giản | Cần schema và DataSource |
| Khả năng truy vấn | In-memory lookup | SQL lookup theo ID/token |
| Vận hành | Phù hợp development/test | Phù hợp persistence lâu dài, cần tuning |
| Throughput | Không có network/database round-trip | Phụ thuộc database, schema và query plan |

Spring Authorization Server dùng InMemoryOAuth2AuthorizationService làm default nếu ứng dụng không cung cấp OAuth2AuthorizationService. Đây là lựa chọn tiện cho development và testing. Với production, cần đánh giá persistence dùng chung và vòng đời authorization.

### 1.2. Authorization không chỉ là một access token

Một authorization record có thể chứa nhiều token và trạng thái:

~~~text
OAuth2Authorization
  id
  registeredClientId
  principalName
  authorizationGrantType
  authorizedScopes
  attributes
  tokens
    authorizationCode
    accessToken
    oidcIdToken
    refreshToken
    userCode
    deviceCode
~~~

Không phải grant nào cũng tạo tất cả các token. Ví dụ Client Credentials thường chỉ có access token; Authorization Code có authorization code, access token và có thể có refresh token; OIDC Authorization Code còn có ID Token.

## 2. Ranh giới giữa các thành phần persistence

Authorization Server có nhiều loại dữ liệu cần lưu bền vững. Không nên gom mọi thứ vào một bảng authorization.

~~~mermaid
flowchart TD
    AS[Authorization Server] --> RC[RegisteredClientRepository]
    AS --> AU[OAuth2AuthorizationService]
    AS --> CO[OAuth2AuthorizationConsentService]
    AS --> JK[JWKSource / Key Store]
    AS --> SS[HTTP Session Store]
    RC --> RDB[(Relational Database)]
    AU --> RDB
    CO --> RDB
    JK --> KS[(Protected Key Store)]
    SS --> SDB[(Session Store)]
    AU --> TOK[Authorization + token state]
    RC --> CLI[Client registrations]
    CO --> COT[Granted authorities / consent]
~~~

| Thành phần | Dữ liệu quản lý | JDBC implementation |
|---|---|---|
| RegisteredClientRepository | Client ID, secret, grant types, redirect URIs, scopes, token/client settings | JdbcRegisteredClientRepository |
| OAuth2AuthorizationService | Authorization, token values, token metadata, grant-specific attributes | JdbcOAuth2AuthorizationService |
| OAuth2AuthorizationConsentService | Authorities/scopes người dùng đã chấp thuận cho client | JdbcOAuth2AuthorizationConsentService |
| JWKSource / key store | Private/public signing keys | Cơ chế key management riêng |
| Session repository | HTTP session và SecurityContext | Servlet container hoặc Spring Session |

JdbcOAuth2AuthorizationService cần RegisteredClientRepository để khôi phục RegisteredClient khi đọc authorization. Nếu record tham chiếu tới registered_client_id không còn tồn tại, row mapper không thể tạo OAuth2Authorization đầy đủ.

### 2.1. Ba repository JDBC thường đi cùng nhau

Trong production, thường cần ít nhất:

1. JdbcRegisteredClientRepository để lưu client registrations;
2. JdbcOAuth2AuthorizationService để lưu authorization và token state;
3. JdbcOAuth2AuthorizationConsentService để lưu consent nếu ứng dụng sử dụng authorization consent.

Mỗi repository có schema riêng. Tạo bảng oauth2_authorization không tự tạo bảng registered client hoặc consent. Hãy dùng đúng schema resource của từng component theo phiên bản thư viện đang triển khai.

### 2.2. Vì sao RegisteredClientRepository là dependency bắt buộc?

Bảng oauth2_authorization lưu registered_client_id, không lặp toàn bộ metadata của client trong mỗi authorization. Khi đọc một hàng, JdbcOAuth2AuthorizationService gọi RegisteredClientRepository.findById(...) để tìm client registration, rồi dùng nó tạo OAuth2Authorization.Builder.

Do đó:

- registered_client_id phải tham chiếu một RegisteredClient tồn tại;
- Client registration cần được lưu bền vững và dùng chung giữa các node;
- Không xóa client registration khi vẫn còn authorization cần được đọc;
- Khi migrate client ID nội bộ, phải cập nhật hoặc migrate authorization records liên quan.

## 3. OAuth2Authorization lưu những gì?

OAuth2Authorization là model đại diện cho một authorization được cấp cho client bởi resource owner hoặc bởi chính client, như Client Credentials grant. Nó chứa trạng thái chung và các token phụ thuộc grant type.

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| id | ID duy nhất của authorization record |
| registeredClientId | ID nội bộ của RegisteredClient |
| principalName | Principal name của resource owner hoặc client |
| authorizationGrantType | Grant đã thực hiện |
| authorizedScopes | Các scopes đã được cấp cho client |
| tokens | Các OAuth2Token và metadata tương ứng |
| attributes | Trạng thái bổ sung của grant, ví dụ Principal hoặc OAuth2AuthorizationRequest |

### 3.1. Các token phụ thuộc grant type

| Grant/flow | Token hoặc state thường gắn với authorization |
|---|---|
| Authorization Code | Authorization Code, Access Token, Refresh Token tùy cấu hình |
| OIDC Authorization Code | Authorization Code, OIDC ID Token, Access Token, Refresh Token tùy cấu hình |
| Client Credentials | Access Token |
| Refresh Token | Authorization được cập nhật với token state mới |
| Device Authorization | Device Code, User Code và Access Token sau khi được phê duyệt |
| Custom grant | Các token/attributes do implementation của grant tạo ra |

### 3.2. Authorized scopes khác access token scopes

authorized_scopes là các scopes được cấp trong authorization. access_token_scopes là scopes gắn với access token cụ thể. Hai tập có thể giống nhau trong flow đơn giản, nhưng không nên coi chúng luôn đồng nhất nếu token customization hoặc policy tạo access token có phạm vi hẹp hơn.

### 3.3. Token metadata chứa trạng thái vòng đời

Mỗi token trong OAuth2Authorization được bọc bởi OAuth2Authorization.Token và có metadata riêng. Các trạng thái quan trọng gồm:

- isExpired(): token đã qua expiresAt;
- isInvalidated(): token đã bị đánh dấu invalidated;
- isActive(): token chưa expired và chưa invalidated;
- getClaims(): claims gắn với token nếu token có claims.

Token value, issuedAt, expiresAt và metadata được lưu để khôi phục object tương ứng. Khi revocation xảy ra, authorization thường được cập nhật metadata token để thể hiện invalidation; không phải lúc nào cũng xóa toàn bộ authorization record.

## 4. OAuth2AuthorizationService contract

OAuth2AuthorizationService là abstraction trung tâm để lưu authorization mới và truy vấn authorization đã tồn tại. Các protocol components gọi service này trong client authentication, authorization grant processing, token introspection, token revocation, dynamic client registration và những flow liên quan.

Contract chính:

~~~java
public interface OAuth2AuthorizationService {

    void save(OAuth2Authorization authorization);

    void remove(OAuth2Authorization authorization);

    OAuth2Authorization findById(String id);

    OAuth2Authorization findByToken(
        String token,
        OAuth2TokenType tokenType
    );
}
~~~

Đây là chữ ký khái niệm của API. findByToken nhận tokenType để giới hạn loại token cần tìm; tokenType có thể null khi caller chưa biết loại.

### 4.1. save

save ghi trạng thái authorization hiện tại. Nó được gọi khi grant tạo authorization, khi token được phát hành, khi refresh token rotation cập nhật token, hoặc khi metadata token thay đổi.

Không nên tự gọi save với một object cũ sau khi đã cập nhật authorization bằng một flow khác. Nếu dùng dữ liệu stale, ứng dụng có thể ghi đè trạng thái mới hơn.

### 4.2. findById

findById lấy authorization theo ID duy nhất. Phương thức trả null nếu không tìm thấy.

~~~java
OAuth2Authorization authorization =
    authorizationService.findById(authorizationId);

if (authorization == null) {
    // Không có authorization record tương ứng.
}
~~~

ID này là ID của authorization record, không phải client ID, user ID hay token value.

### 4.3. findByToken

findByToken tìm authorization chứa credential được truyền vào. tokenType là hint để repository chỉ tìm trong cột phù hợp, ví dụ access token, refresh token, authorization code, ID Token, user code hoặc device code.

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        presentedToken,
        OAuth2TokenType.ACCESS_TOKEN
    );
~~~

Phương thức này chỉ tìm authorization record. Caller vẫn phải kiểm tra token có active, đúng loại, đúng client, đúng scope và đáp ứng policy của endpoint. Tìm thấy một hàng không đồng nghĩa token hợp lệ.

### 4.4. remove

remove xóa toàn bộ OAuth2Authorization record theo implementation. Đây là thao tác khác với invalidating một token cụ thể. Nếu chỉ muốn revoke một token trong authorization có nhiều token, thường phải cập nhật token metadata và save lại authorization theo semantics của grant/endpoint.

Không dùng remove tùy tiện để thay thế token revocation. Xóa record có thể khiến server mất cả code, refresh token, access token metadata và trạng thái cần thiết để xử lý các flow tiếp theo.

## 5. JdbcOAuth2AuthorizationService

JdbcOAuth2AuthorizationService là implementation của OAuth2AuthorizationService sử dụng JdbcOperations để persist OAuth2Authorization. Constructor cần:

- JdbcOperations để thực hiện SQL;
- RegisteredClientRepository để khôi phục client registration;
- Tùy chọn LobHandler để đọc/ghi large binary hoặc large text fields.

Constructor thông dụng:

~~~java
JdbcOAuth2AuthorizationService(
    JdbcOperations jdbcOperations,
    RegisteredClientRepository registeredClientRepository
)
~~~

Overload khác nhận thêm LobHandler:

~~~java
JdbcOAuth2AuthorizationService(
    JdbcOperations jdbcOperations,
    RegisteredClientRepository registeredClientRepository,
    LobHandler lobHandler
)
~~~

### 5.1. Cấu hình bean cơ bản

~~~java
@Configuration
public class AuthorizationPersistenceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcOperations jdbcOperations,
            RegisteredClientRepository registeredClientRepository) {

        return new JdbcOAuth2AuthorizationService(
            jdbcOperations,
            registeredClientRepository
        );
    }
}
~~~

Spring Boot có thể cung cấp DataSource và JdbcTemplate khi dependency JDBC, driver và datasource properties đã được cấu hình. JdbcTemplate triển khai JdbcOperations nên có thể inject trực tiếp vào constructor.

### 5.2. Kết hợp JdbcRegisteredClientRepository

Trong môi trường production, RegisteredClientRepository cũng nên dùng persistence bền vững:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcOperations jdbcOperations) {
    return new JdbcRegisteredClientRepository(jdbcOperations);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {
    return new JdbcOAuth2AuthorizationService(
        jdbcOperations, registeredClientRepository);
}
~~~

Đoạn code thể hiện quan hệ dependency. Ứng dụng phải chạy schema RegisteredClient và schema Authorization tương ứng trước khi khởi động service.

### 5.3. Đăng ký qua OAuth2AuthorizationServerConfigurer

Có thể cấu hình service trực tiếp qua configurer:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationService authorizationService)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .authorizationService(authorizationService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Khi service được khai báo là bean OAuth2AuthorizationService, auto-configuration hoặc cấu hình tường minh của ứng dụng có thể sử dụng bean đó. Nếu có nhiều implementation, cần chỉ rõ bean nào được inject vào Authorization Server.

### 5.4. OAuth2AuthorizationService là optional nhưng production persistence không nên để mặc định

Framework có thể tự dùng InMemoryOAuth2AuthorizationService khi ứng dụng không đăng ký service. Điều này thuận tiện cho ví dụ nhỏ và test, nhưng trạng thái sẽ mất khi process restart và không được chia sẻ giữa các nodes.

Một cấu hình production cần xác minh:

- Bean JdbcOAuth2AuthorizationService được tạo đúng;
- Authorization Server thực sự dùng bean đó;
- Schema đã được migrate;
- RegisteredClientRepository có thể tìm lại client ID;
- Mọi node dùng cùng database/schema;
- Connection pool và transaction manager phù hợp.

## 6. Schema chuẩn oauth2_authorization

JdbcOAuth2AuthorizationService phụ thuộc vào bảng được định nghĩa trong resource:

~~~text
classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

Schema phải tồn tại trong database trước khi service được sử dụng. Đây là schema của authorization records, không phải schema cho registered clients hoặc consent.

### 6.1. Cấu trúc bảng

Schema chuẩn của Spring Authorization Server 1.5.x tạo bảng oauth2_authorization với các nhóm cột sau:

| Nhóm | Cột | Nội dung |
|---|---|---|
| Identity | id | Primary key của authorization |
| Client/principal | registered_client_id, principal_name | Client registration và resource owner/client |
| Grant | authorization_grant_type | Grant type đã thực hiện |
| Scope | authorized_scopes | Scopes đã được cấp |
| Attributes | attributes | Các attributes bổ sung của authorization |
| State | state | Authorization request state nếu có |
| Authorization Code | authorization_code_value, authorization_code_issued_at, authorization_code_expires_at, authorization_code_metadata | Code và metadata |
| Access Token | access_token_value, access_token_issued_at, access_token_expires_at, access_token_metadata, access_token_type, access_token_scopes | Access token và thông tin liên quan |
| OIDC ID Token | oidc_id_token_value, oidc_id_token_issued_at, oidc_id_token_expires_at, oidc_id_token_metadata | ID Token và claims metadata |
| Refresh Token | refresh_token_value, refresh_token_issued_at, refresh_token_expires_at, refresh_token_metadata | Refresh token |
| User Code | user_code_value, user_code_issued_at, user_code_expires_at, user_code_metadata | Device Authorization user code |
| Device Code | device_code_value, device_code_issued_at, device_code_expires_at, device_code_metadata | Device code |

Các cột token có thể null vì một authorization không nhất thiết chứa tất cả các loại token. Ví dụ Client Credentials không tạo authorization code, ID Token, user code hay device code.

### 6.2. DDL rút gọn để đọc cấu trúc

Đoạn dưới đây chỉ minh họa các nhóm cột và kiểu dữ liệu trong schema mặc định. Khi triển khai, dùng resource SQL đi kèm đúng phiên bản dependency và điều chỉnh kiểu dữ liệu cho database vendor.

~~~sql
CREATE TABLE oauth2_authorization (
    id varchar(100) NOT NULL,
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorization_grant_type varchar(100) NOT NULL,
    authorized_scopes varchar(1000) DEFAULT NULL,
    attributes blob DEFAULT NULL,
    state varchar(500) DEFAULT NULL,

    authorization_code_value blob DEFAULT NULL,
    authorization_code_issued_at timestamp DEFAULT NULL,
    authorization_code_expires_at timestamp DEFAULT NULL,
    authorization_code_metadata blob DEFAULT NULL,

    access_token_value blob DEFAULT NULL,
    access_token_issued_at timestamp DEFAULT NULL,
    access_token_expires_at timestamp DEFAULT NULL,
    access_token_metadata blob DEFAULT NULL,
    access_token_type varchar(100) DEFAULT NULL,
    access_token_scopes varchar(1000) DEFAULT NULL,

    oidc_id_token_value blob DEFAULT NULL,
    oidc_id_token_issued_at timestamp DEFAULT NULL,
    oidc_id_token_expires_at timestamp DEFAULT NULL,
    oidc_id_token_metadata blob DEFAULT NULL,

    refresh_token_value blob DEFAULT NULL,
    refresh_token_issued_at timestamp DEFAULT NULL,
    refresh_token_expires_at timestamp DEFAULT NULL,
    refresh_token_metadata blob DEFAULT NULL,

    user_code_value blob DEFAULT NULL,
    user_code_issued_at timestamp DEFAULT NULL,
    user_code_expires_at timestamp DEFAULT NULL,
    user_code_metadata blob DEFAULT NULL,

    device_code_value blob DEFAULT NULL,
    device_code_issued_at timestamp DEFAULT NULL,
    device_code_expires_at timestamp DEFAULT NULL,
    device_code_metadata blob DEFAULT NULL,

    PRIMARY KEY (id)
);
~~~

Schema đầy đủ là hợp đồng giữa service, parameter mapper và row mapper. Không tự đổi tên cột hoặc bỏ một nhóm token nếu vẫn dùng mapper mặc định.

### 6.3. Không có một cột expires_at chung

Schema lưu issued_at và expires_at riêng theo từng loại token. Điều này phản ánh việc authorization có thể chứa nhiều token với vòng đời khác nhau. Không giả định có một authorization_expires_at để cleanup toàn bộ record.

Nếu cần cleanup theo expiry, phải định nghĩa rõ loại token nào quyết định thời điểm authorization record có thể bị xóa và policy retention cho authorization code, refresh token, user/device code cùng metadata phục vụ audit.

### 6.4. Bảng mặc định có primary key nhưng không thay thế index chiến lược

Schema chuẩn tối thiểu tạo primary key trên id. Những truy vấn lookup theo token có thể tìm theo nhiều cột token value. Với dữ liệu lớn, cần đo query plan và thiết kế index phù hợp database. Không giả định schema mặc định đã tối ưu cho mọi tải production.

## 7. Database vendor và kiểu dữ liệu LOB

Schema mặc định dùng BLOB cho các giá trị lớn như token value, attributes và token metadata. Không phải database nào cũng hỗ trợ cùng kiểu dữ liệu.

### 7.1. PostgreSQL

PostgreSQL không có kiểu BLOB theo cú pháp SQL resource mặc định. Tài liệu schema yêu cầu đổi **tất cả các cột được khai báo BLOB sang TEXT** khi dùng PostgreSQL. Không chỉ đổi token value mà quên các cột metadata/attributes.

Ví dụ:

~~~sql
attributes text DEFAULT NULL,
authorization_code_value text DEFAULT NULL,
authorization_code_metadata text DEFAULT NULL,
access_token_value text DEFAULT NULL,
access_token_metadata text DEFAULT NULL
~~~

Áp dụng cùng điều chỉnh cho các cột OIDC ID Token, refresh token, user code và device code. Giữ tên cột và semantics; kiểu dữ liệu cần tương thích với LobHandler và parameter mapper.

### 7.2. CLOB và VARCHAR

Một số database hoặc schema tùy chỉnh có thể dùng CLOB hoặc VARCHAR với độ dài phù hợp thay cho BLOB. JdbcOAuth2AuthorizationService có LobHandler và kiểm tra column metadata để map các giá trị LOB. Tuy nhiên, không tự đổi BLOB sang VARCHAR ngắn mà không kiểm tra token/JWT/metadata có thể dài hơn giới hạn.

### 7.3. Timestamp và múi giờ

Issued-at/expires-at được chuyển qua java.sql.Timestamp. Hãy thống nhất timezone giữa application, JDBC driver và database. Với PostgreSQL, có thể chọn timestamptz trong migration nếu kiến trúc cần lưu Instant rõ ràng; việc thay kiểu phải được kiểm thử với driver và mapper đang dùng.

Với MySQL, cấu hình JDBC connection timezone và driver để bảo toàn instant theo hướng dẫn của Connector/J. Tránh để mỗi node dùng timezone khác nhau vì có thể tạo lỗi token expiry hoặc truy vấn cleanup.

### 7.4. Migration phải bám theo version

Không copy schema từ Spring Authorization Server 1.5.x sang Spring Security 7.x rồi giả định mọi mapper và serializer đều giống nhau. Hãy lấy schema và API theo đúng BOM đang dùng, lưu thành migration versioned và test upgrade trên database clone.

## 8. Khởi tạo schema và quản lý migration

Schema SQL được đóng gói trong JAR của Spring Authorization Server. Có thể dùng resource này trong development/test hoặc dùng làm nguồn tham khảo để tạo migration riêng.

### 8.1. Khởi tạo bằng Spring Boot SQL initialization

Ví dụ cấu hình cho môi trường local:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations:
        - classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

Đoạn cấu hình chỉ khởi tạo schema authorization. Nếu ứng dụng dùng JdbcRegisteredClientRepository hoặc JdbcOAuth2AuthorizationConsentService, cần schema tương ứng. Không bật schema initialization mù quáng ở production vì DDL có thể chạy lại hoặc xung đột với dữ liệu đã tồn tại.

### 8.2. Dùng Flyway hoặc Liquibase trong production

Một quy trình migration có kiểm soát:

1. Chọn đúng schema resource từ phiên bản Spring Authorization Server đang deploy.
2. Điều chỉnh BLOB/CLOB/TEXT, timestamp và độ dài cột theo database vendor.
3. Lưu DDL thành migration có version trong source control.
4. Chạy migration ở pipeline hoặc release job có quyền DDL.
5. Kiểm tra schema version và các cột bắt buộc trước khi khởi động node mới.
6. Chạy integration tests với database engine tương ứng.
7. Giữ rollback/restore plan và backup trước migration phá hủy.

Không để mỗi application node tự chạy một tập DDL không đồng bộ khi nhiều node deploy cùng lúc.

### 8.3. Schema là hợp đồng, không phải chỉ là bảng cùng tên

Service sử dụng tên bảng, tên cột, kiểu dữ liệu và thứ tự tham số SQL được xác định trong implementation. Nếu đổi tên bảng hoặc cột, đổi schema một mình sẽ khiến service lỗi. Khi cần custom schema, phải thay cả SQL/query và mapping logic bằng implementation phù hợp hoặc custom service.

## 9. Default parameter mapper và row mapper

JdbcOAuth2AuthorizationService chuyển object model thành SQL parameters khi ghi, rồi chuyển ResultSet thành OAuth2Authorization khi đọc. Hai điểm mở rộng chính là:

- **authorizationParametersMapper:** Function từ OAuth2Authorization sang List<SqlParameterValue>;
- **authorizationRowMapper:** RowMapper từ ResultSet sang OAuth2Authorization.

Trong Spring Authorization Server 1.5.x, hai implementation mặc định là:

- OAuth2AuthorizationParametersMapper;
- OAuth2AuthorizationRowMapper.

### 9.1. Parameter mapper

Parameter mapper đọc:

- Authorization ID, registered client ID, principal name và grant type;
- Authorized scopes;
- Attributes và state;
- Token values, issuedAt, expiresAt và metadata cho từng token type;
- Access token type và access token scopes.

Các map như attributes và token metadata được serialize thành JSON bằng ObjectMapper đã đăng ký Spring Security Jackson modules và OAuth2AuthorizationServerJackson2Module. Token/LOB values được chuyển thành bytes hoặc text phù hợp kiểu cột.

### 9.2. Row mapper

Row mapper:

1. Đọc registered_client_id;
2. Tìm RegisteredClient từ RegisteredClientRepository;
3. Khôi phục id, principal, grant type, scopes và attributes;
4. Khôi phục từng token nếu token value tương ứng không null;
5. Khôi phục issuedAt/expiresAt và token metadata;
6. Tạo OAuth2Authorization hoàn chỉnh.

Nếu RegisteredClient không còn tồn tại, row mapper không thể dựng authorization và sẽ báo lỗi truy xuất dữ liệu.

### 9.3. Vì sao cần Jackson modules?

Attributes và metadata có thể chứa các kiểu dữ liệu Spring Security/OAuth2 không được Jackson mặc định serialize/deserialize theo đúng semantics. Security Jackson modules và OAuth2AuthorizationServerJackson2Module cung cấp mixins/serializers cần thiết cho những kiểu đó.

Nếu thay ObjectMapper tùy tiện, một số attribute có thể không deserialize được hoặc bị mất kiểu. Hãy test round-trip cho mọi custom attribute mà ứng dụng lưu trong OAuth2Authorization.

### 9.4. Custom mapper khi nào?

Chỉ thay mapper khi cần:

- Custom schema hoặc tên cột;
- Custom data types;
- Custom authorization attributes cần serializer riêng;
- LOB handling theo database driver;
- Tối ưu SQL mapping cho workload cụ thể;
- Tương thích dữ liệu giữa các version ứng dụng.

Nếu chỉ muốn thêm một claim vào JWT, đừng sửa JDBC mapper. Token customization thuộc OAuth2TokenCustomizer; JDBC mapper có nhiệm vụ persist authorization object và metadata.

## 10. Cấu hình mapper tùy chỉnh

JdbcOAuth2AuthorizationService cho phép cài parameter mapper và row mapper qua setter:

~~~java
authorizationService.setAuthorizationParametersMapper(parametersMapper);
authorizationService.setAuthorizationRowMapper(rowMapper);
~~~

Hai setter này cần được gọi trong quá trình khởi tạo bean, trước khi service nhận request. Không thay mapper giữa lúc server đang xử lý request.

Ví dụ minh họa:

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository,
        AuthorizationParametersMapper parametersMapper,
        AuthorizationRowMapper rowMapper) {

    JdbcOAuth2AuthorizationService service =
        new JdbcOAuth2AuthorizationService(
            jdbcOperations, registeredClientRepository);

    service.setAuthorizationParametersMapper(parametersMapper);
    service.setAuthorizationRowMapper(rowMapper);
    return service;
}
~~~

AuthorizationParametersMapper và AuthorizationRowMapper ở đây là abstraction do ứng dụng định nghĩa, triển khai các contract Function và RowMapper tương ứng. Chúng phải khớp hoàn toàn với SQL schema và thứ tự parameters của service. Đây là ví dụ về wiring, không phải class có sẵn của framework.

### 10.1. Mapper hai chiều phải đối xứng

Nếu parameter mapper ghi JSON attributes theo một format nhưng row mapper đọc format khác, dữ liệu sẽ không round-trip. Cần kiểm thử:

- Save rồi findById;
- Save rồi findByToken với từng token type;
- Các custom attributes;
- Token claims và metadata;
- Null/empty values;
- Timestamp chính xác;
- Cả dữ liệu mới và dữ liệu cũ sau migration.

### 10.2. Thay LobHandler

Constructor overload nhận LobHandler để xử lý large binary/text fields theo database. Dùng khi driver/database cần cách binding LOB riêng. Trước khi thay, kiểm tra schema column types và các bài test đọc/ghi token dài.

## 11. Lưu trữ token và trạng thái revocation

Authorization table lưu token value và metadata để các protocol providers có thể tìm authorization và kiểm tra trạng thái. Cần hiểu sự khác biệt giữa xóa authorization, xóa token value và đánh dấu token invalidated.

### 11.1. Token active/inactive

Một token thường active khi chưa hết hạn và chưa bị invalidated. Khi token bị revoke, authorization có thể được cập nhật metadata token để đánh dấu invalidated. Introspection hoặc các provider liên quan kiểm tra trạng thái đó.

### 11.2. Revocation không nhất thiết xóa cả authorization

Một authorization code đã được đổi thành access token có thể vẫn cần authorization record để lưu access/refresh token. Xóa toàn bộ hàng chỉ vì code đã được sử dụng sẽ làm mất trạng thái của token khác.

Tương tự, revoke refresh token không có nghĩa xóa mọi token khác trong authorization nếu policy chỉ thu hồi refresh token. Hãy để protocol provider cập nhật token state đúng semantics.

Ví dụ minh họa đánh dấu access token bị invalidated rồi lưu lại authorization:

~~~java
OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
    authorization.getAccessToken();

if (accessToken != null) {
    OAuth2Authorization updated = OAuth2Authorization.from(authorization)
        .token(accessToken.getToken(), metadata ->
            metadata.put(
                OAuth2Authorization.Token.INVALIDATED_METADATA_NAME,
                true
            )
        )
        .build();

    authorizationService.save(updated);
}
~~~

Đây là minh họa cho token metadata lifecycle; trong ứng dụng thật, hãy để revocation provider của framework xử lý protocol validation, client authorization và loại token được thu hồi. Không gọi đoạn code này từ một API quản trị không được bảo vệ.

### 11.3. Token value trong database là credential nhạy cảm

Database có thể chứa authorization code, opaque access token, refresh token, ID Token, user code và device code. Người có quyền đọc bảng có thể lấy được credential còn hiệu lực nếu dữ liệu được lưu trực tiếp.

Kiểm soát:

- Hạn chế database roles theo nguyên tắc least privilege;
- Bật encryption at rest và bảo vệ backup;
- Dùng TLS cho JDBC connections;
- Không log token values hoặc SQL bind parameters chứa credential;
- Kiểm soát quyền truy cập console/BI/analytics;
- Có quy trình rotate DB credentials;
- Theo dõi truy vấn bất thường vào bảng authorization.

Không mặc định rằng BLOB đồng nghĩa dữ liệu đã được mã hóa. Kiểu cột chỉ mô tả cách lưu, không phải cơ chế bảo vệ bí mật.

## 12. Save, update, remove và truy vấn token

Hiểu cách service thực hiện CRUD giúp chẩn đoán lỗi persistence và tránh thao tác SQL trực tiếp làm hỏng authorization state.

### 12.1. save phân biệt insert và update

Trong implementation JDBC chuẩn, save kiểm tra authorization ID đã tồn tại chưa. Nếu chưa có, service insert một hàng mới; nếu đã có, service update hàng tương ứng.

~~~java
authorizationService.save(authorization);
~~~

Vì authorization ID là primary key, cùng một authorization có thể được lưu nhiều lần khi token metadata thay đổi. Không tự tạo một authorization ID mới mỗi lần refresh token nếu flow cần cập nhật record hiện tại.

### 12.2. remove xóa authorization theo ID

~~~java
authorizationService.remove(authorization);
~~~

Implementation chuẩn xóa hàng theo authorization ID. Đây là thao tác xóa cả authorization record. Trước khi dùng, xác định rõ mọi token liên quan đã hết hiệu lực hoặc không còn cần tra cứu.

### 12.3. findById

Truy vấn theo primary key:

~~~sql
SELECT *
FROM oauth2_authorization
WHERE id = ?;
~~~

Đây là lookup phù hợp khi một component đã biết authorization ID.

### 12.4. findByToken với token type cụ thể

Với access token:

~~~sql
SELECT *
FROM oauth2_authorization
WHERE access_token_value = ?;
~~~

Các token type khác tương ứng với cột riêng: authorization_code_value, oidc_id_token_value, refresh_token_value, user_code_value và device_code_value. State được lưu trong cột state.

Khi caller truyền tokenType, service chọn filter tương ứng. Khi tokenType là null, implementation chuẩn còn kiểm tra cột state cùng các cột authorization code, access token, ID Token, refresh token, user code và device code. Điều này hữu ích khi caller chưa biết loại credential, nhưng truy vấn phải so sánh nhiều cột hơn.

### 12.5. Custom token type không tự động được hỗ trợ

Schema chuẩn chỉ có các cột token đã liệt kê. Nếu custom grant tạo loại credential riêng, không giả định findByToken sẽ tự tìm được token đó. Cần quyết định cách lưu token và metadata, rồi cung cấp custom OAuth2AuthorizationService/mapper/query phù hợp.

Không ghi custom token vào cột access_token_value chỉ để tận dụng query có sẵn nếu token đó có semantics khác access token.

## 13. Index, query plan và hiệu năng

Schema chuẩn có primary key trên id, nhưng workload Authorization Server còn tra cứu theo token value. Với số lượng authorization lớn, truy vấn findByToken có thể trở thành bottleneck nếu database phải scan nhiều hàng.

### 13.1. Xác định các query path thực tế

| Query | Cột lọc | Thành phần sử dụng |
|---|---|---|
| findById | id | Các component đã có authorization ID |
| Authorization Code lookup | authorization_code_value | Token endpoint |
| Access Token lookup | access_token_value | Introspection, revocation và resource flows |
| ID Token lookup | oidc_id_token_value | OIDC/logout flows tùy provider |
| Refresh Token lookup | refresh_token_value | Refresh Token grant/revocation |
| User Code lookup | user_code_value | Device verification |
| Device Code lookup | device_code_value | Device Authorization grant |
| State lookup | state | Authorization request correlation |

### 13.2. Đánh giá index theo database vendor

Không tạo index trên mọi cột một cách máy móc. Token values có thể được lưu dưới dạng BLOB/TEXT và một số database không hỗ trợ index trực tiếp hoặc hiệu quả trên LOB. Dùng EXPLAIN/EXPLAIN ANALYZE với dữ liệu gần production để xác định query nào cần tối ưu.

Các hướng có thể cân nhắc:

- Index riêng cho cột token có kiểu dữ liệu hỗ trợ;
- Index cho principal_name hoặc registered_client_id nếu có query quản trị/cleanup tương ứng;
- Cột digest/hash bổ sung cho token lookup khi LOB không index được;
- Custom service/query dùng digest để tìm record, sau đó xác minh token value đầy đủ;
- Phân vùng hoặc archive authorization records theo policy và database capability.

Nếu bổ sung digest column, phải cập nhật cả ghi token, query, rotation/migration và collision handling. Hash không thay thế kiểm tra token gốc; sau khi tìm ứng viên vẫn cần so sánh credential đầy đủ theo thiết kế.

### 13.3. High throughput

Tài liệu API của Spring Authorization Server mô tả JdbcOAuth2AuthorizationService là simplified JDBC implementation và lưu ý nó có thể không đáp ứng môi trường cần throughput cao. Khi workload tăng, consuming application được kỳ vọng cung cấp implementation OAuth2AuthorizationService riêng phù hợp deployment.

Đo các chỉ số:

- P50/P95/P99 latency của save/findByToken/findById;
- Số truy vấn trên mỗi authorization flow;
- Connection pool active/idle/wait;
- Database CPU, lock wait và I/O;
- Số hàng authorization và tỷ lệ token hết hạn;
- Kích thước attributes/token metadata;
- Query plan trước và sau khi thêm index.

### 13.4. Không cache authorization tùy tiện

Cache có thể giảm database reads nhưng authorization state thay đổi khi refresh, revoke hoặc token invalidation. Cache stale có thể khiến introspection trả active cho token đã revoked hoặc refresh flow chấp nhận token cũ.

Nếu triển khai cache, cần invalidation đồng bộ hoặc consistency model có giới hạn rõ. Với security-sensitive lookups, ưu tiên correctness của token state hơn cache hit ratio.

## 14. Transaction và tính nhất quán

Authorization grant thường thực hiện nhiều thao tác có quan hệ: xác thực client, xác minh grant, tạo token, lưu authorization và trả response. Database state phải nhất quán nếu một bước thất bại.

### 14.1. Dùng cùng DataSource và transaction manager

JdbcOAuth2AuthorizationService nhận JdbcOperations. Trong Spring application, JdbcTemplate và transaction manager nên dùng cùng DataSource để các thao tác JDBC tham gia cùng transaction context.

Ví dụ một service nghiệp vụ tùy chỉnh:

~~~java
@Service
public class AuthorizationMaintenanceService {

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationMaintenanceService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    @Transactional
    public void updateAuthorization(
            OAuth2Authorization authorization) {
        authorizationService.save(authorization);
    }
}
~~~

Ví dụ này minh họa transaction boundary cho một thao tác ứng dụng. Không cần bọc mọi protocol filter bằng một transaction lớn. Chọn boundary theo nghiệp vụ và tránh giữ transaction mở trong lúc chờ browser, gọi network chậm hoặc tương tác người dùng.

### 14.2. Insert race và primary key

Vì save có thể kiểm tra findById rồi mới insert, hai request đồng thời cùng cố tạo một authorization ID có thể cạnh tranh. Primary key giúp database ngăn hai hàng trùng ID, nhưng ứng dụng cần xác định cách xử lý duplicate-key/retry nếu flow có thể phát lại.

Không tự retry mọi lỗi SQL. Chỉ retry lỗi transient đã được nhận diện, với thao tác idempotent và dữ liệu authorization mới nhất.

### 14.3. Tránh ghi đè trạng thái mới bằng object stale

Một request refresh token có thể cập nhật authorization trong khi một tác vụ quản trị khác đang thao tác cùng record. Nếu cả hai dùng object được đọc từ thời điểm khác nhau, lần save sau có thể ghi đè metadata mới hơn.

Nếu có thao tác cập nhật song song, cần kiểm soát concurrency bằng transaction isolation, optimistic locking/version column trong custom schema hoặc một service implementation có update semantics rõ. Schema mặc định không có version column.

### 14.4. Không sửa SQL trực tiếp khi application đang chạy

Không nên update token metadata bằng SQL thủ công trong khi service có thể đang đọc/ghi cùng authorization. Một script quản trị phải có transaction, backup, audit và hiểu serialization format. Ưu tiên dùng protocol endpoints hoặc service API được bảo vệ.

## 15. Authorization Consent là persistence riêng

OAuth2AuthorizationConsent lưu quyết định consent của resource owner cho một client, thường gồm registered_client_id, principal_name và authorities được cấp. Dữ liệu này không đồng nhất với authorization record.

Schema consent chuẩn có bảng riêng:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

JdbcOAuth2AuthorizationConsentService là implementation riêng, sử dụng schema oauth2-authorization-consent-schema.sql.

### 15.1. Consent và authorized scopes

Consent mô tả authorities mà người dùng đã cấp cho client. OAuth2Authorization ghi lại scopes/authorization state của một flow cụ thể. Một bên có thể tồn tại lâu hơn một authorization record riêng lẻ.

Không dùng oauth2_authorization làm bảng duy nhất để suy ra mọi quyết định consent lịch sử. Nếu application cần audit consent changes, có thể cần audit log/domain table riêng.

### 15.2. Registered Client persistence cũng là schema riêng

JdbcRegisteredClientRepository dùng bảng oauth2_registered_client. Bảng này lưu client secret đã encode, grant types, authentication methods, redirect URIs, scopes và settings. Authorization row chỉ lưu registered_client_id để tìm lại registration.

Production cần migration cho cả ba nhóm dữ liệu khi sử dụng:

~~~text
oauth2_registered_client
oauth2_authorization
oauth2_authorization_consent
~~~

Không xóa registered client row khi authorization records còn tham chiếu tới nó. Nếu cần decommission client, có thể disable/rotate credentials trước, giữ registration metadata trong retention window, rồi cleanup theo kế hoạch.

## 16. Retention, cleanup và dữ liệu hết hạn

Token hết hạn không có nghĩa authorization row tự biến mất. JdbcOAuth2AuthorizationService không phải background cleanup scheduler. Hệ thống phải quyết định giữ authorization records bao lâu để hỗ trợ introspection, revocation, audit, refresh token và xử lý incident.

### 16.1. Cleanup cần xét tất cả token trong authorization

Một authorization có thể chứa access token đã hết hạn nhưng refresh token còn hiệu lực. Nếu cleanup chỉ nhìn access_token_expires_at rồi xóa cả hàng, refresh token sẽ không thể được tìm thấy.

Tương tự, authorization code hết hạn nhưng access token đã được cấp vẫn có thể cần record. Device/user codes có vòng đời khác với access token.

### 16.2. Thiết kế cleanup theo policy

Một job cleanup an toàn nên:

1. Xác định authorization không còn token active và không còn state cần cho protocol;
2. Áp dụng retention window phục vụ audit/incident;
3. Loại trừ các authorization còn refresh token active;
4. Xóa theo batch nhỏ để tránh lock lớn;
5. Có metric số hàng được kiểm tra/xóa;
6. Ghi audit và hỗ trợ dry-run;
7. Chạy trong transaction ngắn và có thể tiếp tục sau lỗi.

Schema mặc định không có một cột expires_at tổng hợp. Muốn cleanup nhanh theo một query đơn giản, có thể bổ sung cột/index trong custom schema, nhưng phải cập nhật service/migration và định nghĩa chính xác cách tính expiry của authorization.

### 16.3. Archive và quyền riêng tư

Authorization attributes có thể chứa principal, authorization request hoặc thông tin context. Retention cần cân nhắc PII, dữ liệu consent và yêu cầu audit. Archive không có nghĩa chuyển nguyên access/refresh tokens sang kho analytics có quyền truy cập rộng.

## 17. Kiểm thử JdbcOAuth2AuthorizationService

Kiểm thử phải dùng database thật hoặc engine tương thích với production schema. H2 hữu ích cho test nhanh nhưng không thay thế hoàn toàn PostgreSQL/MySQL integration tests vì kiểu LOB, timestamp, collation và SQL behavior khác nhau.

### 17.1. Test context và schema

Một Spring Boot integration test có thể cấu hình schema resource:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:authorization-test;DB_CLOSE_DELAY=-1
    username: sa
    password:
  sql:
    init:
      mode: always
      schema-locations:
        - classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

Đây là cấu hình minh họa cho test với H2 tương thích kiểu schema. Cần tạo thêm registered client schema hoặc seed một RegisteredClientRepository phù hợp. Với PostgreSQL, dùng migration đã đổi BLOB thành TEXT.

### 17.2. Round-trip save/findById

~~~java
@SpringBootTest
class JdbcAuthorizationServiceTests {

    @Autowired
    OAuth2AuthorizationService authorizationService;

    @Test
    void savesAndLoadsAuthorizationById() {
        OAuth2Authorization authorization =
            authorizationFixture();

        authorizationService.save(authorization);

        OAuth2Authorization loaded =
            authorizationService.findById(authorization.getId());

        assertThat(loaded).isNotNull();
        assertThat(loaded.getRegisteredClientId())
            .isEqualTo(authorization.getRegisteredClientId());
        assertThat(loaded.getPrincipalName())
            .isEqualTo(authorization.getPrincipalName());
        assertThat(loaded.getAuthorizedScopes())
            .isEqualTo(authorization.getAuthorizedScopes());
    }
}
~~~

authorizationFixture() là fixture do test định nghĩa, phải dùng RegisteredClient đã được đăng ký trong repository. Test nên xác minh cả token values, timestamps, claims và metadata chứ không chỉ ba trường cơ bản.

### 17.3. Test findByToken cho từng token type

Tạo authorization fixture có authorization code, access token, ID Token và refresh token. Sau khi save, kiểm tra:

- findByToken(code, code token type) trả đúng authorization;
- findByToken(accessToken, ACCESS_TOKEN) trả đúng authorization;
- findByToken(idToken, id token type) trả đúng authorization;
- findByToken(refreshToken, REFRESH_TOKEN) trả đúng authorization;
- Token không tồn tại trả null;
- Token type không khớp trả null;
- tokenType null có thể tìm token theo các cột chuẩn mà implementation hỗ trợ.

Với Device Authorization, thêm user code/device code fixture và test hai lookup riêng.

### 17.4. Test update và remove

~~~java
@Test
void updatesAndRemovesAuthorization() {
    OAuth2Authorization original = authorizationFixture();
    authorizationService.save(original);

    OAuth2Authorization updated = OAuth2Authorization
        .from(original)
        .attribute("test.marker", "updated")
        .build();

    authorizationService.save(updated);

    OAuth2Authorization loaded =
        authorizationService.findById(updated.getId());
    assertThat(loaded.getAttribute("test.marker"))
        .isEqualTo("updated");

    authorizationService.remove(updated);
    assertThat(authorizationService.findById(updated.getId()))
        .isNull();
}
~~~

Đây là skeleton minh họa update/remove. Trong test thực, bảo đảm builder giữ nguyên token state và các attributes cần thiết; xác minh token lookup cũng không còn trả record sau remove.

### 17.5. Test token invalidation metadata

Tạo authorization có access token active, đánh dấu token metadata invalidated bằng API phù hợp của OAuth2Authorization.Builder, save lại rồi đọc từ JDBC. Xác minh token state sau round-trip vẫn là inactive. Đây là test quan trọng vì revocation/introspection phụ thuộc metadata được persist chính xác.

### 17.6. Test database vendor

Dùng Testcontainers hoặc database instance tương đương production để kiểm tra:

- PostgreSQL TEXT LOB mapping;
- Timestamp/Instant round-trip;
- Token value dài;
- JSON attributes/metadata;
- Index và query plan;
- Transaction rollback;
- Concurrent save/update;
- Connection pool failure/recovery.

## 18. Hiệu năng và vận hành production

JdbcOAuth2AuthorizationService thực hiện JDBC reads/writes trong đường xử lý protocol. Database chậm hoặc connection pool cạn có thể làm token endpoint, introspection và revocation tăng latency.

### 18.1. Connection pool

- Đặt pool size theo concurrency và capacity database;
- Đặt connection acquisition timeout;
- Theo dõi pool pending threads;
- Không đặt pool lớn hơn khả năng xử lý của database;
- Dùng TLS và credentials riêng cho ứng dụng;
- Kiểm tra connection validation và failover behavior.

### 18.2. Database observability

Theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| save latency | Thời gian ghi authorization |
| findByToken latency | Thời gian lookup token |
| findById latency | Thời gian lookup theo ID |
| rows in oauth2_authorization | Quy mô authorization store |
| expired/inactive records | Dữ liệu cần retention/cleanup |
| lock wait/deadlocks | Cạnh tranh cập nhật |
| slow queries | Thiếu index hoặc query plan xấu |
| connection pool wait | Database/pool không đáp ứng tải |
| serialization failures | Attributes/metadata không round-trip |

### 18.3. Backup và restore

Database authorization là thành phần quan trọng để hệ thống phục hồi hoạt động. Backup cần nhất quán với registered clients và consent. Nếu restore authorization table nhưng thiếu registered client rows, row mapper không thể khôi phục authorization.

Kiểm thử restore định kỳ, bao gồm:

- Khôi phục schema và dữ liệu;
- Khôi phục registered client repository;
- Kiểm tra token/authorization lookups;
- Xác minh signing keys vẫn tương thích với JWT còn hạn;
- Kiểm tra refresh và introspection flows.

### 18.4. Rolling deployment và schema compatibility

Khi nâng Spring Authorization Server/Spring Security, không deploy schema mới trước khi hiểu mapper cũ/mới có tương thích không. Dùng expand-and-contract:

1. Thêm cột/kiểu mới tương thích với phiên bản đang chạy;
2. Deploy code có thể đọc cả format cũ/mới;
3. Chuyển ghi sang format mới;
4. Migrate dữ liệu cũ theo batch;
5. Xác minh mọi node đã dùng format mới;
6. Chỉ sau đó mới loại bỏ cột/format cũ.

Không đổi Jackson serialization hoặc custom attributes format mà không có migration và round-trip tests.

## 19. Khác biệt phiên bản và khả năng tương thích dữ liệu

Spring Authorization Server 1.5.x là thế hệ cuối trước khi Authorization Server được tích hợp vào Spring Security 7.0. Khi nâng cấp, cần xem đồng thời:

- Package/API của dependency đang dùng;
- Jackson generation;
- Default row mapper và parameter mapper;
- Schema SQL;
- Security Jackson modules;
- Runtime hints/native image support;
- Custom attributes đã persist từ các phiên bản cũ.

### 19.1. Spring Authorization Server 1.5.x

Trong API 1.5.8, các mapper mặc định là:

- JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper;
- JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper.

Chúng sử dụng Jackson 2 ObjectMapper được cấu hình với Spring Security Jackson modules và OAuth2AuthorizationServerJackson2Module. Nếu ứng dụng custom ObjectMapper, phải giữ các module cần thiết để serialize/deserialize OAuth2 authorization attributes và token metadata.

### 19.2. Spring Security 7.0+

Ở thế hệ Spring Security 7, mapper Jackson 3 được bổ sung với tên JsonMapperOAuth2AuthorizationParametersMapper và JsonMapperOAuth2AuthorizationRowMapper. Các mapper Jackson 2 cũ được đánh dấu deprecated để hỗ trợ chuyển đổi.

Không trộn code sample Jackson 3 với dependency Spring Authorization Server 1.5.x. Cũng không giả định dữ liệu JSON đã persist bởi Jackson 2 tự động tương thích trong mọi custom type với Jackson 3. Hãy thử đọc dữ liệu thật đã migrate trên database clone trước khi nâng cấp production.

### 19.3. Schema và mapper phải được nâng cấp cùng nhau

Một schema có thể giữ nguyên tên bảng nhưng format metadata hoặc mapper behavior thay đổi theo version. Compatibility phải được xác minh bằng:

1. Snapshot dữ liệu authorization đại diện từ version cũ;
2. Khởi động ứng dụng version mới trên bản sao database;
3. findById và findByToken cho từng loại token;
4. Kiểm tra custom attributes, claims, token metadata;
5. Chạy refresh, introspection và revocation flows;
6. So sánh token state trước/sau migration.

Nếu custom mapper đã được dùng, migration cần kiểm thử cả format riêng của ứng dụng, không chỉ mapper mặc định.

## 20. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Startup báo thiếu bảng oauth2_authorization | Schema chưa được migrate | Kiểm tra migration history và datasource/schema |
| save thất bại với lỗi kiểu cột | BLOB/CLOB/TEXT không tương thích | Đối chiếu database vendor và LobHandler |
| findById không tìm thấy authorization | Record chưa được save, sai ID hoặc transaction rollback | Kiểm tra ID, transaction và commit |
| findByToken trả null | Sai tokenType, token value khác hoặc cột custom không được query | Kiểm tra token type và cột lookup |
| Row mapper báo RegisteredClient không tồn tại | registered_client_id mồ côi | Kiểm tra JdbcRegisteredClientRepository và client lifecycle |
| Lỗi JSON deserialize attributes | Thiếu Security Jackson module hoặc custom type không tương thích | Kiểm tra ObjectMapper và stored JSON |
| Token metadata bị mất sau restart | Mapper/schema không ghi đủ metadata hoặc migration thiếu cột | Round-trip test token metadata |
| PostgreSQL báo type BLOB không tồn tại | Dùng nguyên schema mặc định | Đổi tất cả BLOB columns thành TEXT |
| Timestamp lệch giờ hoặc token expired sớm | Driver/database timezone không thống nhất | Kiểm tra Timestamp mapping, UTC và JDBC URL |
| Refresh token dùng lại không đúng | Save/update race hoặc state stale | Kiểm tra transaction, authorization ID và rotation |
| Introspection trả active sau revoke | Cache stale hoặc invalidation metadata không được save | Kiểm tra OAuth2Authorization.Token metadata và cache |
| Latency token endpoint tăng | findByToken scan lớn, DB/pool bận | EXPLAIN, index, pool metrics |
| Node A thấy authorization nhưng node B không thấy | Node dùng database/schema khác hoặc transaction chưa commit | Kiểm tra datasource và topology |
| Sau nâng cấp không đọc được dữ liệu cũ | Jackson/schema/mapper incompatibility | Restore snapshot và test migration |

### 20.1. Quy trình chẩn đoán

1. Xác định bean OAuth2AuthorizationService đang được inject.
2. Xác định datasource, database/schema và migration version.
3. Kiểm tra RegisteredClientRepository có tìm được client ID liên quan.
4. Kiểm tra authorization row theo ID bằng quyền DB read-only được kiểm soát.
5. Xác định token type và cột mà findByToken sử dụng.
6. Kiểm tra mapper, LOB type và JSON metadata.
7. Kiểm tra transaction commit, lock wait và query plan.
8. Tái hiện trên database clone trước khi sửa dữ liệu production.

Không giải quyết lỗi lookup bằng cách log token value hoặc copy credential vào ticket. Dùng authorization ID, correlation ID và token fingerprint đã được bảo vệ.

## 21. Checklist production

1. **Service bean:** Authorization Server đang dùng JdbcOAuth2AuthorizationService?
2. **DataSource:** JdbcOperations và transaction manager trỏ đúng database?
3. **Registered clients:** RegisteredClientRepository có persistence và resolve được mọi registered_client_id?
4. **Schema:** oauth2-authorization-schema.sql đúng version đã được migrate?
5. **Vendor types:** BLOB/CLOB/TEXT và timestamp types phù hợp database?
6. **OIDC:** Các cột ID Token được giữ nếu server phát hành OIDC?
7. **Other grants:** User code/device code columns có mặt nếu dùng Device Authorization?
8. **Mapper:** Parameter mapper và row mapper round-trip được attributes/metadata?
9. **Jackson:** Đã đăng ký Security modules và OAuth2 module đúng version?
10. **Token state:** Expiry/invalidation metadata được persist và đọc lại đúng?
11. **Lookup:** findByToken hỗ trợ mọi token type đang dùng?
12. **Custom grant:** Có custom query/mapper nếu credential không thuộc schema chuẩn?
13. **Index:** Query plan cho token lookup đạt yêu cầu throughput?
14. **Transactions:** Save/update có transaction semantics phù hợp và xử lý race?
15. **Consent:** Consent persistence dùng service/schema riêng khi cần?
16. **Security:** Token values, attributes và backups được bảo vệ; logs không lộ credential?
17. **Cleanup:** Retention job không xóa authorization còn token active?
18. **Testing:** Có round-trip, findByToken, update/remove, revoke và vendor-specific tests?
19. **Operations:** Có backup/restore test, pool metrics, slow query alert?
20. **Upgrade:** Có migration plan cho schema, mapper và Jackson version?

## 22. Bài tập vận dụng

**Tình huống A — Restart làm mất refresh token:** Authorization Server đang dùng InMemoryOAuth2AuthorizationService. Sau khi deploy lại, client refresh token nhận invalid_grant. Hãy giải thích nguyên nhân và đề xuất cách cấu hình JDBC persistence.

**Tình huống B — PostgreSQL không tạo được schema:** Migration dùng nguyên resource DDL và thất bại vì BLOB. Xác định tất cả các cột phải đổi và thiết kế test round-trip LOB.

**Tình huống C — Client registration bị xóa:** Một authorization row vẫn tồn tại nhưng RegisteredClientRepository không tìm được registered_client_id. Vì sao row mapper không thể khôi phục authorization? Đề xuất lifecycle cho decommission client.

**Tình huống D — Revocation không có hiệu lực:** Endpoint trả success nhưng introspection vẫn active. Hãy phân tích khác biệt giữa remove authorization, invalidated token metadata và save lại authorization.

**Tình huống E — High throughput:** findByToken chậm khi bảng có hàng chục triệu records. Hãy xác định query path, dùng EXPLAIN, xem LOB indexing và đề xuất custom digest lookup nếu cần.

**Tình huống F — Nâng cấp Jackson:** Ứng dụng chuyển từ Spring Authorization Server 1.5.x sang Spring Security 7.0. Các custom authorization attributes không deserialize được. Hãy thiết kế compatibility test và migration.

**Tình huống G — Cleanup sai:** Job xóa authorization khi access token hết hạn nhưng refresh token vẫn active. Hãy sửa điều kiện retention để không làm mất khả năng refresh.

**Gợi ý:** A cần JdbcOAuth2AuthorizationService và schema; B đổi tất cả BLOB thành TEXT trên PostgreSQL; C giữ registration metadata tới khi authorization liên quan hết vòng đời; D đánh dấu token invalidated và persist đúng authorization; E tối ưu lookup theo token column hoặc digest với custom service; F kiểm thử JSON mapper và stored data trên database clone; G xét trạng thái mọi token trong authorization.

## 23. Tổng kết

JdbcOAuth2AuthorizationService là implementation JDBC của OAuth2AuthorizationService. Nó lưu và truy vấn OAuth2Authorization, bao gồm client reference, principal, grant type, authorized scopes, attributes, token values và metadata. Các protocol components dựa vào service này trong authorization grant processing, refresh, introspection, revocation và các flow liên quan.

Schema oauth2_authorization được đóng gói trong Spring Authorization Server và phải được tạo đúng phiên bản. Bảng có các nhóm cột riêng cho authorization code, access token, OIDC ID Token, refresh token, user code và device code. Database vendor có thể yêu cầu điều chỉnh LOB và timestamp types; PostgreSQL cần đổi tất cả cột BLOB sang TEXT.

JdbcOAuth2AuthorizationService cần JdbcOperations và RegisteredClientRepository. Default parameter mapper và row mapper chuyển object model sang SQL parameters và ngược lại. Trong Spring Authorization Server 1.5.x, các mapper mặc định dùng Jackson 2 cùng Spring Security/OAuth2 Jackson modules; khi nâng cấp lên Spring Security 7, cần kiểm tra mapper Jackson 3 và compatibility của dữ liệu đã lưu.

Để vận hành production, cần lưu registered clients và consent bằng repository riêng khi sử dụng, quản lý migration có version, bảo vệ token values/metadata, tối ưu findByToken, kiểm soát transaction/concurrency, đặt retention đúng vòng đời của mọi token và kiểm thử với database vendor thật. Khi throughput vượt khả năng simplified JDBC implementation, hãy triển khai OAuth2AuthorizationService tùy chỉnh dựa trên workload và consistency requirements.

## 24. Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 API — JdbcOAuth2AuthorizationService](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): constructor, CRUD/query methods, mapper setters, schema requirement và high-throughput note.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClientRepository, OAuth2Authorization, OAuth2AuthorizationService, token state và consent.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): các protocol components sử dụng authorization service.
- [Spring Authorization Server 1.5.x — Authorization Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): DDL bảng oauth2_authorization và lưu ý PostgreSQL.
- [Spring Authorization Server — Registered Client Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql): schema client registration.
- [Spring Authorization Server — Authorization Consent Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): schema consent riêng.
- [Spring Security 7 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): API và mapper trong thế hệ tích hợp Spring Security 7.
- [Spring Framework — JDBC and Data Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcOperations, JdbcTemplate và transaction integration.
- [PostgreSQL — Character Types](https://www.postgresql.org/docs/current/datatype-character.html): TEXT và các kiểu chuỗi trong PostgreSQL.
- [MySQL Connector/J — Preserving Time Instants](https://dev.mysql.com/doc/connector-j/en/connector-j-time-instants.html): cấu hình timezone và lưu timestamp chính xác.
