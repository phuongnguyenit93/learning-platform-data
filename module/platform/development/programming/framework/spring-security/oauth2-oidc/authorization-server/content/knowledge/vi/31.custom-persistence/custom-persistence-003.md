# Triển khai OAuth2AuthorizationConsentService

Authorization Server cần lưu lại quyết định đồng ý của người dùng khi một OAuth2 Client yêu cầu quyền truy cập. Khi người dùng chấp thuận một số scopes hoặc authorities cho một client, server phải nhớ quyết định đó để xử lý những authorization requests tiếp theo. Nếu consent chỉ nằm trong bộ nhớ của một JVM, quyết định sẽ mất sau restart và các node khác trong cluster không thể dùng chung trạng thái.

Spring Authorization Server cung cấp abstraction **OAuth2AuthorizationConsentService** để lưu, tìm và xóa **OAuth2AuthorizationConsent**. Framework có implementation in-memory và JDBC; ứng dụng có thể triển khai service riêng để dùng JPA, Redis, document database hoặc một hệ thống consent bên ngoài.

Bài học thuộc chương **Lưu trữ tùy chỉnh**, module **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm là hiểu consent domain model, triển khai OAuth2AuthorizationConsentService, kết nối service với authorization endpoint và bảo đảm dữ liệu consent nhất quán, an toàn.

> **Phân biệt quan trọng:** OAuth2AuthorizationConsent lưu quyết định quyền mà resource owner cấp cho một RegisteredClient. OAuth2Authorization lưu trạng thái của một authorization flow và các token được phát hành. Hai model có liên quan nhưng có vòng đời và mục đích riêng.

## 1. Consent giải quyết vấn đề gì?

Trong Authorization Code Flow, client có thể yêu cầu các scopes như profile, email hoặc orders.read. OP xác thực End-User rồi quyết định có cần hiển thị consent screen hay không. Người dùng có thể đồng ý toàn bộ hoặc chỉ một phần những quyền được yêu cầu, tùy chính sách và giao diện của ứng dụng.

Ví dụ client portal-web yêu cầu:

~~~text
openid
profile
email
orders.read
~~~

Người dùng đồng ý cho client đọc thông tin hồ sơ và email, nhưng từ chối quyền đọc đơn hàng. OP cần lưu quyết định đã cấp để những lần authorization tiếp theo có thể so sánh quyền đã đồng ý với quyền client đang yêu cầu.

Consent không phải một checkbox UI tạm thời. Nó là dữ liệu bảo mật có tác động đến việc client có được tiếp tục authorization mà không hỏi lại người dùng hay không.

### 1.1. Consent là quyết định giữa principal và client

Một consent record của Spring Authorization Server được định danh bằng hai giá trị:

| Field | Ý nghĩa |
|---|---|
| registeredClientId | ID nội bộ duy nhất của RegisteredClient |
| principalName | Tên principal của resource owner |
| authorities | Các authorities mà principal đã cấp cho client |

Vì vậy, cùng một người dùng có thể có consent khác nhau cho từng client. Cùng một client cũng có thể có consent riêng cho nhiều người dùng.

Ví dụ:

| Registered client | Principal | Authorities được cấp |
|---|---|---|
| portal-web | user-42 | SCOPE_openid, SCOPE_profile |
| mobile-app | user-42 | SCOPE_openid, SCOPE_profile, SCOPE_email |
| portal-web | user-84 | SCOPE_openid, SCOPE_email |

Không dùng client_id công khai thay cho registeredClientId trong khóa lưu trữ. Model sử dụng ID của RegisteredClient; service có thể tra cứu registration tương ứng để xác minh record.

### 1.2. Consent có thể chứa nhiều loại authority

OAuth2AuthorizationConsent lưu Set<GrantedAuthority>, không chỉ một danh sách scopes. Một authority có thể đại diện cho:

- OAuth2 scope, thường có prefix SCOPE_;
- Quyền truy cập một nhóm claims;
- Permission nghiệp vụ do OP định nghĩa;
- Role hoặc authority mở rộng theo policy.

Builder có phương thức scope(String) để thêm scope và tự chuyển thành SimpleGrantedAuthority với prefix SCOPE_. Phương thức authority(GrantedAuthority) cho phép lưu một authority tổng quát.

### 1.3. Consent không phải access token

Consent ghi lại quyết định đã cấp quyền. Access token là credential được phát hành trong một authorization cụ thể. Consent có thể tồn tại lâu hơn một access token; một access token hết hạn không có nghĩa consent tự động bị xóa.

Ngược lại, thu hồi consent cũng không tự động chứng minh mọi access token đã phát hành bị vô hiệu hóa. Nếu cần thu hồi token đang tồn tại, ứng dụng phải áp dụng token revocation hoặc authorization lifecycle policy riêng.

## 2. OAuth2AuthorizationConsent và OAuth2AuthorizationConsentService

OAuth2AuthorizationConsent là domain object bất biến, Serializable, gồm registered client ID, principal name và tập authorities. Service quản lý các object này trong một kho lưu trữ.

~~~mermaid
flowchart TD
    U[Resource Owner] --> UI[Consent UI]
    UI --> EP[Authorization Endpoint]
    EP --> AP[Consent Authentication Provider]
    AP --> CS[OAuth2AuthorizationConsentService]
    CS --> DB[(Custom Consent Store)]
    CS --> AP
    AP --> AU[OAuth2AuthorizationService]
    AU --> CODE[Authorization Code]
    CODE --> RP[OAuth2 Client]
~~~

Luồng này cho thấy consent service là một dependency của authorization request processing. Consent được đọc để xác định quyền đã cấp và được ghi khi người dùng chấp thuận các authorities.

### 2.1. Domain model

Các accessor quan trọng:

| API | Kết quả |
|---|---|
| getRegisteredClientId() | ID của RegisteredClient |
| getPrincipalName() | Principal name của resource owner |
| getAuthorities() | Set<GrantedAuthority> đã được cấp |
| getScopes() | Các scope được suy ra từ authorities có prefix SCOPE_ |
| withId(registeredClientId, principalName) | Tạo builder với composite identity |
| from(consent) | Tạo builder từ consent hiện tại |

Ví dụ tạo consent:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId(
            registeredClient.getId(),
            authentication.getName())
        .scope("openid")
        .scope("profile")
        .scope("orders.read")
        .build();
~~~

Builder yêu cầu có ít nhất một GrantedAuthority khi build. Nếu người dùng từ chối toàn bộ quyền, không tạo consent rỗng; hãy xử lý từ chối theo authorization flow và policy của ứng dụng.

### 2.2. Scope được lưu dưới dạng authority

Khi gọi:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId("client-internal-id", "user-42")
        .scope("profile")
        .build();
~~~

Authority được lưu là:

~~~text
SCOPE_profile
~~~

Khi cần đọc scope, getScopes() lấy những authority có prefix SCOPE_ và loại bỏ prefix. Các authority tùy chỉnh không phải scope vẫn nằm trong getAuthorities().

### 2.3. Service contract

OAuth2AuthorizationConsentService có ba phương thức:

~~~java
public interface OAuth2AuthorizationConsentService {

    void save(OAuth2AuthorizationConsent authorizationConsent);

    void remove(OAuth2AuthorizationConsent authorizationConsent);

    OAuth2AuthorizationConsent findById(
        String registeredClientId,
        String principalName
    );
}
~~~

Hợp đồng nhỏ này cố ý dùng cặp registeredClientId và principalName làm định danh. findById trả null khi không có consent. Nó không trả Optional và cũng không tìm theo client_id công khai.

## 3. Ba thao tác service và semantics

### 3.1. findById

findById tìm quyết định consent theo cặp:

~~~java
OAuth2AuthorizationConsent consent =
    consentService.findById(
        registeredClient.getId(),
        principal.getName()
    );

if (consent == null) {
    // Principal chưa có consent cho RegisteredClient này.
}
~~~

Đây là lookup mà authorization request processing dùng để so sánh authorities đã được cấp với authorities client yêu cầu.

### 3.2. save

save lưu một consent mới hoặc thay thế/cập nhật consent hiện tại theo semantics của implementation:

~~~java
OAuth2AuthorizationConsent updatedConsent =
    OAuth2AuthorizationConsent.withId(
            registeredClient.getId(),
            principal.getName())
        .scope("openid")
        .scope("profile")
        .build();

consentService.save(updatedConsent);
~~~

Trong consent flow, provider có thể xây dựng một consent từ authorities người dùng chấp thuận rồi gọi save. Implementation custom nên xác định rõ save là insert hay upsert và bảo đảm cùng một composite key không tạo nhiều record.

### 3.3. remove

remove xóa consent của đúng client và principal:

~~~java
consentService.remove(consent);
~~~

Đây là thao tác thu hồi toàn bộ consent record của cặp đó. Nếu cần chỉ thu hồi một authority, hãy tạo consent mới với tập authorities còn lại rồi save; không xóa record nếu người dùng vẫn giữ các quyền khác.

### 3.4. Idempotency và null handling

Service contract không bắt buộc implementation phải ném lỗi khi xóa record không tồn tại. Trong hệ thống production, remove thường nên idempotent: gọi nhiều lần vẫn cho kết quả nhất quán.

Đối với save và findById:

- Từ chối input null;
- Từ chối registeredClientId/principalName rỗng;
- Không tự đổi chữ hoa/thường hoặc trim principal name nếu identity provider không định nghĩa phép chuẩn hóa đó;
- Không trả consent thuộc client hoặc principal khác;
- Phát hiện dữ liệu lưu trữ sai định dạng thay vì âm thầm cấp quyền.

## 4. InMemory và JDBC implementation có sẵn

Spring Authorization Server cung cấp hai implementation phổ biến:

| Implementation | Cơ chế | Mục đích |
|---|---|---|
| InMemoryOAuth2AuthorizationConsentService | Lưu object trong bộ nhớ JVM | Development và test |
| JdbcOAuth2AuthorizationConsentService | Lưu qua JdbcOperations | Relational database |
| Custom implementation | JPA, Redis, document store hoặc service ngoài | Kiến trúc persistence riêng |

OAuth2AuthorizationConsentService là component optional. Nếu ứng dụng không cung cấp bean, Spring Authorization Server mặc định dùng InMemoryOAuth2AuthorizationConsentService. Điều này thuận tiện cho demo nhưng consent sẽ mất sau restart và không chia sẻ giữa các nodes.

### 4.1. Khi nào cần custom service?

Custom implementation có thể cần khi:

- Ứng dụng chuẩn hóa persistence bằng JPA;
- Consent được lưu trong một database đã có sẵn;
- Cần đồng bộ quyết định với hệ thống privacy/consent management;
- Hệ thống chạy nhiều node và cần shared store;
- Cần lưu tenant, version, timestamp hoặc audit metadata bổ sung;
- Cần tối ưu query, transaction hoặc retention theo workload.

Nếu JdbcOAuth2AuthorizationConsentService đáp ứng schema, database và vận hành của ứng dụng, không cần viết lại service. Custom implementation làm tăng trách nhiệm về transaction, migration, concurrency, serialization và bảo mật dữ liệu.

### 4.2. Đừng nhầm consent service với authorization service

| Service | Lưu dữ liệu |
|---|---|
| OAuth2AuthorizationConsentService | Quyết định authorities được principal cấp cho client |
| OAuth2AuthorizationService | Authorization flow, token values, token metadata và attributes |
| RegisteredClientRepository | Client registrations, grant types, scopes, redirect URIs và settings |

Một consent record có thể tồn tại trước hoặc sau nhiều authorization records. Không dùng OAuth2AuthorizationService để thay thế consent store.

## 5. Thiết kế custom persistence với JPA

Để triển khai service riêng, bắt đầu từ domain model và ba thao tác của interface. Với JPA, một consent record có thể được lưu thành một entity có composite primary key gồm registered client ID và principal name.

Schema tham khảo:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    authorities varchar(4000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

Composite primary key bảo đảm mỗi client chỉ có tối đa một consent record cho một principal. Khi consent thay đổi, service cập nhật tập authorities của record hiện tại.

### 5.1. Vì sao dùng composite key?

Một user có thể đồng ý với nhiều clients; một client có thể có consent của nhiều users. Khóa đơn chỉ là principalName sẽ làm các client ghi đè consent của nhau. Khóa đơn chỉ là registeredClientId sẽ làm người dùng này ghi đè người dùng khác.

Khóa đúng là:

~~~text
(registered_client_id, principal_name)
~~~

Không dùng email làm principal key nếu username/subject là giá trị mà Authentication thực sự sử dụng. Nếu principal name có thể thay đổi, cần thiết kế identity key ổn định và migration các consent records khi identity được đổi.

### 5.2. Lưu authorities dạng chuỗi hay bảng con?

Có hai cách phổ biến:

| Cách lưu | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| Một cột authorities dạng comma-delimited hoặc JSON | Entity đơn giản, ít join | Cần giới hạn độ dài và serializer ổn định |
| Bảng con một dòng mỗi authority | Chuẩn hóa, query từng quyền dễ hơn | Thêm join, mapping và transaction |

Spring Authorization Server JPA guide minh họa một cột authorities dạng comma-delimited. Đây là cấu trúc gọn cho authority names đơn giản. Nếu ứng dụng có custom authority có thể chứa dấu phẩy, hoặc cần truy vấn/filter theo từng authority, nên dùng JSON có serializer chuẩn hoặc bảng con thay vì delimiter không escape.

### 5.3. Entity với composite primary key

Ví dụ entity theo hướng đơn giản:

~~~java
@Entity
@Table(name = "oauth2_authorization_consent")
@IdClass(AuthorizationConsentEntity.ConsentId.class)
public class AuthorizationConsentEntity {

    @Id
    @Column(name = "registered_client_id", length = 255)
    private String registeredClientId;

    @Id
    @Column(name = "principal_name", length = 255)
    private String principalName;

    @Column(name = "authorities", nullable = false, length = 4000)
    private String authorities;

    protected AuthorizationConsentEntity() {
    }

    public String getRegisteredClientId() {
        return registeredClientId;
    }

    public void setRegisteredClientId(String registeredClientId) {
        this.registeredClientId = registeredClientId;
    }

    public String getPrincipalName() {
        return principalName;
    }

    public void setPrincipalName(String principalName) {
        this.principalName = principalName;
    }

    public String getAuthorities() {
        return authorities;
    }

    public void setAuthorities(String authorities) {
        this.authorities = authorities;
    }

    public static class ConsentId implements Serializable {
        private String registeredClientId;
        private String principalName;

        public ConsentId() {
        }

        public ConsentId(String registeredClientId, String principalName) {
            this.registeredClientId = registeredClientId;
            this.principalName = principalName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConsentId that)) {
                return false;
            }
            return Objects.equals(registeredClientId, that.registeredClientId)
                && Objects.equals(principalName, that.principalName);
        }

        @Override
        public int hashCode() {
            return Objects.hash(registeredClientId, principalName);
        }
    }
}
~~~

Đây là entity minh họa với Jakarta Persistence. Composite ID class phải Serializable và định nghĩa equals/hashCode dựa trên cả hai trường. Trong code thực tế, bổ sung imports và cân nhắc dùng @EmbeddedId nếu nhóm muốn đóng gói khóa trong một value object.

### 5.4. Spring Data repository

~~~java
public interface AuthorizationConsentRepository
        extends JpaRepository<
            AuthorizationConsentEntity,
            AuthorizationConsentEntity.ConsentId> {

    Optional<AuthorizationConsentEntity>
    findByRegisteredClientIdAndPrincipalName(
        String registeredClientId,
        String principalName
    );

    void deleteByRegisteredClientIdAndPrincipalName(
        String registeredClientId,
        String principalName
    );
}
~~~

Repository cung cấp thao tác theo composite key. Có thể dùng findById(new ConsentId(...)) thay cho derived query nếu đã có constructor của key class.

## 6. Triển khai JpaOAuth2AuthorizationConsentService

Service adapter chuyển đổi giữa domain model Spring Authorization Server và entity JPA. Nó cần hai dependencies:

- AuthorizationConsentRepository để lưu và truy vấn entity;
- RegisteredClientRepository để xác nhận registered client được tham chiếu còn tồn tại.

Việc kiểm tra RegisteredClient giúp phát hiện consent record mồ côi thay vì trả về một consent không còn gắn với client registration hợp lệ.

### 6.1. Implementation đầy đủ

~~~java
@Service
@Transactional(readOnly = true)
public class JpaOAuth2AuthorizationConsentService
        implements OAuth2AuthorizationConsentService {

    private final AuthorizationConsentRepository repository;
    private final RegisteredClientRepository registeredClientRepository;

    public JpaOAuth2AuthorizationConsentService(
            AuthorizationConsentRepository repository,
            RegisteredClientRepository registeredClientRepository) {
        Assert.notNull(repository, "repository cannot be null");
        Assert.notNull(registeredClientRepository,
            "registeredClientRepository cannot be null");
        this.repository = repository;
        this.registeredClientRepository = registeredClientRepository;
    }

    @Override
    @Transactional
    public void save(OAuth2AuthorizationConsent consent) {
        Assert.notNull(consent, "consent cannot be null");
        assertRegisteredClientExists(consent.getRegisteredClientId());
        repository.save(toEntity(consent));
    }

    @Override
    @Transactional
    public void remove(OAuth2AuthorizationConsent consent) {
        Assert.notNull(consent, "consent cannot be null");
        repository.deleteByRegisteredClientIdAndPrincipalName(
            consent.getRegisteredClientId(),
            consent.getPrincipalName()
        );
    }

    @Override
    public OAuth2AuthorizationConsent findById(
            String registeredClientId,
            String principalName) {
        Assert.hasText(registeredClientId,
            "registeredClientId cannot be empty");
        Assert.hasText(principalName, "principalName cannot be empty");

        return repository.findByRegisteredClientIdAndPrincipalName(
                registeredClientId, principalName)
            .map(this::toObject)
            .orElse(null);
    }

    private AuthorizationConsentEntity toEntity(
            OAuth2AuthorizationConsent consent) {
        AuthorizationConsentEntity entity =
            new AuthorizationConsentEntity();
        entity.setRegisteredClientId(consent.getRegisteredClientId());
        entity.setPrincipalName(consent.getPrincipalName());

        Set<String> authorities = consent.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toCollection(TreeSet::new));

        entity.setAuthorities(
            StringUtils.collectionToCommaDelimitedString(authorities));
        return entity;
    }

    private OAuth2AuthorizationConsent toObject(
            AuthorizationConsentEntity entity) {
        String registeredClientId = entity.getRegisteredClientId();
        assertRegisteredClientExists(registeredClientId);

        if (!StringUtils.hasText(entity.getAuthorities())) {
            throw new DataRetrievalFailureException(
                "Stored consent has no authorities");
        }

        OAuth2AuthorizationConsent.Builder builder =
            OAuth2AuthorizationConsent.withId(
                registeredClientId, entity.getPrincipalName());

        for (String authority :
                StringUtils.commaDelimitedListToSet(entity.getAuthorities())) {
            builder.authority(new SimpleGrantedAuthority(authority));
        }

        return builder.build();
    }

    private void assertRegisteredClientExists(String registeredClientId) {
        if (registeredClientRepository.findById(registeredClientId) == null) {
            throw new DataRetrievalFailureException(
                "RegisteredClient with id '" + registeredClientId
                    + "' was not found");
        }
    }
}
~~~

Đoạn code thể hiện adapter hoàn chỉnh cho schema comma-delimited ở phần trước. Imports cần có gồm Jakarta/Spring annotations, Assert, StringUtils, DataRetrievalFailureException, GrantedAuthority, SimpleGrantedAuthority, OAuth2AuthorizationConsent, OAuth2AuthorizationConsentService, RegisteredClientRepository, JpaRepository và các collection types.

### 6.2. Vì sao findById trả null?

Interface định nghĩa null khi không tìm thấy. Service không nên ném EntityNotFoundException cho trường hợp consent chưa từng được cấp; authorization endpoint cần phân biệt consent chưa tồn tại với lỗi database.

Ngược lại, nếu record tồn tại nhưng RegisteredClient bị xóa, đó là lỗi integrity. Ví dụ trên ném DataRetrievalFailureException để không âm thầm bỏ qua một record mồ côi.

### 6.3. Vì sao save là upsert theo composite key?

Spring Data JPA save sẽ persist hoặc merge entity theo trạng thái ID. Với entity có composite key, repository phải nhận diện đúng key để cập nhật consent đã tồn tại. Nếu custom persistence dùng insert-only, cần xử lý duplicate key bằng update/merge trong transaction.

### 6.4. Vì sao remove xóa theo cả hai trường?

Consent được định danh bằng cặp registeredClientId và principalName. Xóa theo mỗi principalName sẽ có nguy cơ xóa consent của nhiều clients. Xóa theo mỗi registeredClientId có thể ảnh hưởng đến nhiều resource owners.

## 7. Đăng ký custom service với Authorization Server

Khi service được tạo thành Spring bean, có thể truyền nó vào OAuth2AuthorizationServerConfigurer:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationConsentService authorizationConsentService)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .authorizationConsentService(authorizationConsentService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình Authorization Server. Ứng dụng vẫn cần RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, token generator/signing keys và application login chain. Phương thức authorizationConsentService(...) là extension point chính thức của configurer.

### 7.1. Dùng một implementation duy nhất

Nếu có nhiều bean cùng implement OAuth2AuthorizationConsentService, hãy dùng @Qualifier hoặc cấu hình tường minh để tránh inject nhầm. Đặc biệt, không để framework âm thầm dùng InMemory implementation trong khi ứng dụng tưởng rằng JPA bean đang hoạt động.

### 7.2. Kiểm tra wiring lúc khởi động

Có thể kiểm tra bean thực tế trong integration test hoặc application context test:

~~~java
assertThat(applicationContext.getBean(
        OAuth2AuthorizationConsentService.class))
    .isInstanceOf(JpaOAuth2AuthorizationConsentService.class);
~~~

Kiểm tra kiểu bean chưa chứng minh authorization endpoint sử dụng đúng bean. Cần chạy một consent flow thực tế và xác minh record xuất hiện trong database.

## 8. Consent trong Authorization Code Flow

Consent service được sử dụng chủ yếu trong Authorization Code Flow. Authorization request provider tra consent hiện tại để quyết định có cần hiển thị consent page hay không. Khi resource owner gửi lựa chọn, consent authentication provider xây dựng consent mới/cập nhật rồi gọi service để lưu.

### 8.1. Vai trò của hai authentication providers

| Provider | Trách nhiệm liên quan đến consent |
|---|---|
| OAuth2AuthorizationCodeRequestAuthenticationProvider | Xử lý authorization request, đọc consent đã cấp và xác định có cần yêu cầu consent |
| OAuth2AuthorizationConsentAuthenticationProvider | Xử lý quyết định consent được gửi về, tạo/cập nhật OAuth2AuthorizationConsent và lưu qua service |

Hai provider được wiring trong Authorization Server filter chain. Chúng nhận OAuth2AuthorizationConsentService cùng các dependency như RegisteredClientRepository và OAuth2AuthorizationService.

### 8.2. Luồng consent mới

1. Client gửi authorization request với client_id, redirect_uri, response_type, scope và state.
2. OP xác thực resource owner.
3. Authorization request provider tìm RegisteredClient và consent hiện có theo registeredClientId + principalName.
4. Nếu policy yêu cầu consent và các quyền cần cấp chưa được chấp thuận, OP chuyển browser đến consent page.
5. Consent page hiển thị client, scopes và thông tin cần thiết để người dùng quyết định.
6. Browser POST lựa chọn về authorization endpoint cùng state và client_id.
7. Consent authentication provider xác minh request context, xây dựng consent và gọi save.
8. Authorization Server tiếp tục flow, tạo authorization code và trả response cho client.

### 8.3. Consent đã tồn tại

Nếu người dùng đã cấp đủ authorities theo policy, authorization endpoint có thể tiếp tục mà không hiển thị lại consent screen. Nếu client yêu cầu thêm quyền, OP có thể yêu cầu consent bổ sung.

Ví dụ lần đầu user-42 cấp:

~~~text
SCOPE_openid
SCOPE_profile
~~~

Lần sau client yêu cầu thêm:

~~~text
SCOPE_email
~~~

Sau khi người dùng đồng ý, consent record có thể chứa cả authorities cũ và authority mới:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

Service phải persist toàn bộ tập authorities có trong object được truyền vào. Không tự merge bằng cách union mọi giá trị với record cũ, vì thao tác đó có thể làm quyền đã bị thu hồi quay trở lại.

## 9. Tích hợp consent page tùy chỉnh

Có thể cấu hình Authorization Endpoint chuyển browser tới một consent page riêng:

~~~java
http.with(authorizationServer, server -> server
    .authorizationEndpoint(endpoint -> endpoint
        .consentPage("/oauth2/consent")
    )
);
~~~

Đây là fragment trong Authorization Server SecurityFilterChain đầy đủ. Khi dùng consentPage tùy chỉnh, ứng dụng phải tự render trang và xử lý form.

### 9.1. Query parameters của consent page

Theo cấu hình Authorization Endpoint, query string chuyển đến consent page có thể chứa:

| Parameter | Ý nghĩa |
|---|---|
| client_id | Client ID công khai để hiển thị client |
| scope | Các scopes trong authorization request |
| state | Giá trị bảo vệ/correlation của consent request |

Consent page có thể tra RegisteredClient để hiển thị client name và thông tin UX. Việc tra cứu này chỉ phục vụ giao diện; server vẫn phải xác thực client/request khi form được submit.

### 9.2. Form phải POST về authorization endpoint

Consent form phải gửi HTTP POST tới endpoint được cấu hình bởi AuthorizationServerSettings.getAuthorizationEndpoint(). Form cần có:

- client_id nhận được từ authorization request;
- state nhận được từ authorization request;
- Các scope mà resource owner chấp thuận;
- CSRF token theo cấu hình Spring Security.

Ví dụ HTML minh họa:

~~~html
<form method="post" action="/oauth2/authorize">
  <input type="hidden" name="client_id" value="portal-web">
  <input type="hidden" name="state" value="STATE_FROM_REQUEST">

  <label>
    <input type="checkbox" name="scope" value="openid" checked>
    Định danh OpenID
  </label>
  <label>
    <input type="checkbox" name="scope" value="profile" checked>
    Thông tin hồ sơ
  </label>
  <label>
    <input type="checkbox" name="scope" value="email">
    Địa chỉ email
  </label>

  <button type="submit">Chấp thuận</button>
</form>
~~~

Đây là HTML rút gọn để minh họa các field giao thức. Trong ứng dụng thực, render bằng template engine, encode mọi giá trị, thêm CSRF hidden field và xử lý lựa chọn từ chối rõ ràng.

### 9.3. Không tin dữ liệu form

Client ID và scopes từ browser đều có thể bị sửa. Consent UI không được tự ghi trực tiếp xuống repository chỉ dựa trên form values. Hãy POST về Authorization Endpoint để provider xác minh state token, RegisteredClient, authorization request, principal hiện tại và các scopes được phép.

Không cho phép form thêm scope mà client không yêu cầu hoặc client không được đăng ký. Provider phải duy trì validation và policy trước khi gọi consent service.

### 9.4. Từ chối consent

Nếu resource owner từ chối toàn bộ request, không tạo OAuth2AuthorizationConsent với authorities rỗng vì builder yêu cầu ít nhất một authority. Hãy để Authorization Endpoint xử lý quyết định từ chối theo protocol và UX của ứng dụng.

Nếu người dùng chấp thuận một phần, chỉ các authorities được chấp thuận mới được lưu. Những scopes bị từ chối không được thêm vào consent record.

## 10. Consent customizer và policy mở rộng

OAuth2AuthorizationConsentAuthenticationProvider có extension point setAuthorizationConsentCustomizer(...) nhận Consumer<OAuth2AuthorizationConsentAuthenticationContext>. Context cung cấp builder trước khi consent được lưu cùng thông tin request.

Context có thể cung cấp:

- OAuth2AuthorizationConsent.Builder đang được xây dựng;
- Authentication của consent request;
- RegisteredClient liên quan;
- OAuth2Authorization liên kết với state token;
- OAuth2AuthorizationRequest gốc.

### 10.1. Khi nào cần customizer?

Có thể dùng customizer để:

- Thêm authority nghiệp vụ sau khi policy xác minh;
- Loại bỏ authority không được tenant cho phép;
- Gắn quyết định consent với context bổ sung;
- Thực hiện kiểm tra policy riêng theo RegisteredClient;
- Tạo audit metadata bên ngoài consent domain model.

Không dùng customizer để cấp thêm scope chỉ vì scope tồn tại trong RegisteredClient. Quyết định phải phù hợp authorization request, lựa chọn người dùng và policy.

### 10.2. Không biến consent customizer thành persistence layer

Customizer thay đổi builder; consent service vẫn chịu trách nhiệm lưu domain object. Giữ logic persistence trong service/repository để dễ test, quản lý transaction và thay đổi backend.

### 10.3. Consent có thể bao gồm authority ngoài scope

Ví dụ ứng dụng cần lưu thêm permission:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId(registeredClientId, principalName)
        .scope("openid")
        .scope("profile")
        .authority(new SimpleGrantedAuthority("PERMISSION_invoice.read"))
        .build();
~~~

Authority mở rộng phải có namespace và policy rõ ràng. Không để tên authority tùy ý từ browser được thêm vào consent mà không kiểm tra.

## 11. Thiết kế cập nhật và thu hồi consent

Consent record thường là snapshot của tập authorities đã cấp. Mỗi lần người dùng thay đổi quyết định, service cần lưu tập kết quả mới.

### 11.1. Cập nhật một phần quyền

Ví dụ consent hiện tại:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

Người dùng thu hồi email nhưng vẫn giữ openid và profile. Tạo consent mới:

~~~java
OAuth2AuthorizationConsent updated =
    OAuth2AuthorizationConsent.withId(registeredClientId, principalName)
        .scope("openid")
        .scope("profile")
        .build();

consentService.save(updated);
~~~

Không thêm lại email từ record cũ. save phải ghi tập authority đúng như object mới.

### 11.2. Thu hồi toàn bộ consent

~~~java
OAuth2AuthorizationConsent current =
    consentService.findById(registeredClientId, principalName);

if (current != null) {
    consentService.remove(current);
}
~~~

Đây là cách xóa consent record. API quản trị phải xác thực End-User và xác minh người gọi chỉ được thao tác trên consent của chính họ hoặc có quyền admin rõ ràng.

### 11.3. Thu hồi consent không tự thu hồi token

Xóa consent ngăn consent record cũ được dùng cho các authorization requests tiếp theo. Nó không tự động xóa OAuth2Authorization, revoke access token hoặc refresh token đã cấp trước đó.

Nếu privacy policy yêu cầu khi thu hồi consent phải chấm dứt quyền đang tồn tại, workflow cần phối hợp:

1. Cập nhật/xóa consent;
2. Tìm authorization records liên quan theo principal và client;
3. Revoke authorization/token theo policy;
4. Xử lý refresh token và access token state;
5. Ghi audit event;
6. Thông báo Resource Server/RP nếu kiến trúc có cơ chế propagation.

Không xóa mọi authorization của principal chỉ vì một client bị thu hồi consent. Phạm vi phải gắn đúng client và quyền được thu hồi.

### 11.4. Re-consent sau khi client đổi scopes

Khi RegisteredClient được cấp thêm scope, consent cũ không tự bao gồm quyền mới. Authorization request tiếp theo phải so sánh quyền đã cấp với quyền được yêu cầu và hỏi lại người dùng khi cần.

Khi client bị giảm scope hoặc decommission, cần quyết định giữ consent để audit hay xóa theo retention policy. Không xóa consent chỉ vì client tạm thời không dùng một scope.

## 12. Lựa chọn persistence khác

Interface service nhỏ nên có thể triển khai trên nhiều backend. Điều quan trọng là giữ đúng composite identity, authority set và semantics của ba thao tác.

### 12.1. Redis

Redis có thể phù hợp khi Authorization Server đã sử dụng Redis cho dữ liệu chia sẻ giữa các node:

~~~text
key: oauth2:consent:{registeredClientId}:{principalName}
value: serialized set of authority names
~~~

Thiết kế Redis cần:

- Encode hoặc length-prefix key components để tránh collision khi giá trị có ký tự phân cách;
- Serialize authority set bằng format versioned;
- Save thay thế toàn bộ set theo consent object mới;
- Find trả null nếu key không tồn tại;
- Remove xóa đúng một composite key;
- Không đặt TTL tùy tiện nếu consent không có expiry theo policy;
- Dùng atomic command/script khi cần cập nhật đồng thời.

Không nối client ID và principal name bằng một dấu phân cách rồi giả định dữ liệu không bao giờ chứa dấu đó. Có thể dùng Base64URL hoặc hash có namespace để tạo key ổn định.

### 12.2. Document database

Một document có thể lưu:

~~~json
{
  "registeredClientId": "client-internal-123",
  "principalName": "user-42",
  "authorities": [
    "SCOPE_openid",
    "SCOPE_profile",
    "PERMISSION_invoice.read"
  ],
  "schemaVersion": 1
}
~~~

Tạo unique compound index trên registeredClientId và principalName. Dùng array thay cho chuỗi delimiter giúp giữ nguyên authority names. Nếu cần lịch sử consent, lưu audit events ở collection riêng; document hiện tại chỉ là trạng thái đang có hiệu lực.

### 12.3. Dịch vụ consent bên ngoài

Một tổ chức có thể lưu consent trong privacy/consent management platform. Adapter triển khai OAuth2AuthorizationConsentService gọi API của hệ thống đó.

Adapter cần xác định:

- Timeout và retry policy;
- Idempotency key cho save/remove;
- Authentication giữa các service;
- Consistency và read-after-write guarantees;
- Mapping giữa registeredClientId/principalName với external identifiers;
- Cách xử lý service ngoài unavailable.

Không retry vô hạn một thao tác consent. Authorization endpoint cần fail closed nếu không thể xác định consent state đáng tin cậy.

## 13. Mô hình bảng authority chuẩn hóa

Nếu authority names có thể chứa dấu phẩy hoặc tập quyền có thể lớn, dùng bảng con để lưu từng authority. Cấu trúc tham khảo:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);

CREATE TABLE oauth2_authorization_consent_authority (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    authority varchar(500) NOT NULL,
    PRIMARY KEY (
        registered_client_id,
        principal_name,
        authority
    ),
    FOREIGN KEY (registered_client_id, principal_name)
        REFERENCES oauth2_authorization_consent (
            registered_client_id,
            principal_name
        )
        ON DELETE CASCADE
);
~~~

Với JPA, bảng con có thể ánh xạ bằng @ElementCollection:

~~~java
@ElementCollection(fetch = FetchType.EAGER)
@CollectionTable(
    name = "oauth2_authorization_consent_authority",
    joinColumns = {
        @JoinColumn(
            name = "registered_client_id",
            referencedColumnName = "registered_client_id"),
        @JoinColumn(
            name = "principal_name",
            referencedColumnName = "principal_name")
    }
)
@Column(name = "authority", nullable = false, length = 500)
private Set<String> authorities = new HashSet<>();
~~~

Entity chính vẫn giữ composite key gồm registered client ID và principal name. Khi dùng mapping này, service chuyển Set<String> sang SimpleGrantedAuthority khi đọc và ngược lại khi ghi. Xóa parent record có thể cascade xuống authority rows theo foreign key.

### 13.1. Ưu điểm của bảng con

- Không cần escape dấu phẩy trong authority;
- Không có giới hạn tổng độ dài một cột authorities;
- Có thể query hoặc thống kê theo từng authority;
- Unique key ngăn duplicate authority trong một consent;
- Foreign key bảo đảm authority row không mồ côi.

### 13.2. Chi phí của chuẩn hóa

Read cần load authority collection; write có thể delete/insert nhiều child rows; transaction phải bao phủ parent và children. Với số lượng consent lớn, đo query count và batch behavior. Không dùng EAGER mặc định cho mọi quan hệ trong hệ thống; lựa chọn fetch strategy theo đường đọc thực tế.

## 14. Multi-tenant và identity boundaries

OAuth2AuthorizationConsentService chỉ nhận hai tham số định danh: registeredClientId và principalName. Nó không có tenantId riêng. Nếu hệ thống multi-tenant, thiết kế phải bảo đảm hai giá trị này không gây collision giữa tenants.

Các hướng có thể dùng:

- RegisteredClient internal IDs được namespace theo tenant và globally unique;
- Principal name dùng immutable subject có tenant namespace;
- Adapter lấy tenant từ security context đã xác thực và thêm vào storage key;
- Mỗi tenant dùng schema/database riêng;
- Có một registry trung tâm mapping external client/subject sang cặp key chuẩn.

Không nhận tenant ID từ query/form và dùng trực tiếp để truy vấn consent. Tenant context phải đến từ nguồn xác thực đáng tin cậy.

### 14.1. Principal name phải nhất quán

Giả sử login trước dùng principalName là email, nhưng lần sau Authentication trả về user UUID. Service sẽ tìm hai consent khác nhau. Chọn một canonical principal identifier ổn định ngay từ đầu và dùng nhất quán qua authentication, consent và authorization.

### 14.2. Không dùng client_id thay cho registeredClientId

RegisteredClient có cả id nội bộ và clientId công khai. OAuth2AuthorizationConsent dùng RegisteredClient.getId(). Nếu storage dùng clientId công khai, phải có mapping rõ ràng và không được truyền nhầm clientId vào findById.

## 15. Transaction và xử lý concurrent consent updates

Consent có thể được cập nhật đồng thời từ nhiều browser sessions hoặc node khác nhau. Ví dụ hai tab cùng mở consent page và gửi lựa chọn khác nhau. Nếu service dùng read-modify-write mà không có concurrency policy, thao tác sau có thể ghi đè thay đổi của thao tác trước.

### 15.1. Transaction boundary

Với JPA, save/remove nên chạy trong transaction để entity và authority rows được ghi/xóa cùng nhau. findById có thể dùng read-only transaction nếu repository cần load lazy associations.

Không giữ database transaction mở trong toàn bộ thời gian người dùng đọc consent page. Authorization request, browser interaction và form submission là các request riêng biệt.

### 15.2. Optimistic locking

Có thể thêm version column vào entity:

~~~java
@Version
private long version;
~~~

Khi hai request cùng cập nhật một record, JPA có thể phát hiện stale update và ném OptimisticLockException. Ứng dụng cần quyết định hiển thị lỗi, reload consent state hoặc yêu cầu người dùng xác nhận lại.

OAuth2AuthorizationConsentService không mang version trong domain object, vì vậy version là chi tiết persistence. Không âm thầm retry bằng cách union authorities của hai request; cách đó có thể khôi phục quyền mà một request vừa thu hồi.

### 15.3. Unique constraint và first insert race

Hai request đầu tiên của cùng một cặp client/principal có thể cùng thấy chưa có consent rồi cùng insert. Composite primary key bảo vệ tính duy nhất. Implementation cần xử lý duplicate-key race bằng cách reload/update trong transaction mới nếu semantics của ứng dụng cho phép.

Không bắt tất cả lỗi database rồi coi như save thành công. Chỉ xử lý lỗi duplicate key đã nhận diện; các lỗi connection, constraint khác và serialization phải được báo lên.

### 15.4. Save là snapshot, không phải merge mù

Service nhận một OAuth2AuthorizationConsent hoàn chỉnh. Hãy lưu chính xác authorities của object đó. Nếu service tự merge với record hiện tại, quyền bị xóa trong request mới có thể không bao giờ biến mất.

## 16. Bảo mật dữ liệu consent

Consent record thể hiện quyền mà resource owner đã cấp. Đây là dữ liệu security-sensitive dù không chứa access token.

Kiểm soát cần có:

- Database role chỉ cho phép ứng dụng đọc/ghi bảng consent cần thiết;
- TLS cho kết nối database/cache;
- Encryption at rest và backup protection theo policy;
- Không log toàn bộ authorities hoặc thông tin người dùng nếu không cần;
- Không cho người dùng sửa consent của principal khác;
- Không cho client tự gọi service hoặc repository;
- Validate RegisteredClient và principal trước khi lưu;
- Audit thay đổi consent với actor, thời điểm, client và kết quả;
- Giới hạn quyền admin khi xem/xóa consent.

### 16.1. Consent UI chống CSRF và request tampering

Consent form là POST có tác động bảo mật. Giữ CSRF protection của Spring Security, xác minh state token và để Authorization Endpoint xử lý. Không tạo endpoint POST riêng chỉ nhận client_id/principalName/scopes rồi gọi save trực tiếp mà bỏ qua protocol validation.

### 16.2. Không suy diễn quyền từ dữ liệu client

RegisteredClient scopes cho biết client có thể yêu cầu những scopes nào. Consent record cho biết principal đã cấp những authorities nào. Hai tập này khác nhau. Không tự cấp mọi scopes đã đăng ký chỉ vì client hợp lệ.

### 16.3. Audit history tách khỏi current state

OAuth2AuthorizationConsent chỉ biểu diễn quyết định hiện tại. Nếu cần lịch sử ai đã cấp/thu hồi quyền, lưu audit event riêng với event type, principal, registered client, authority delta, timestamp, actor và correlation ID.

Không ghi password, session cookie, access token, refresh token hoặc raw authentication object vào audit event.

## 17. Kiểm thử custom consent service

Kiểm thử phải xác minh cả mapping domain/entity và cách Authorization Endpoint sử dụng service. Unit test cho một mapper không chứng minh consent flow thật đang gọi đúng bean.

### 17.1. Round-trip save/find

~~~java
@SpringBootTest
class JpaOAuth2AuthorizationConsentServiceTests {

    @Autowired
    OAuth2AuthorizationConsentService consentService;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    @Test
    void savesAndLoadsConsentByClientAndPrincipal() {
        RegisteredClient client =
            registeredClientRepository.findByClientId("portal-web");

        OAuth2AuthorizationConsent consent =
            OAuth2AuthorizationConsent.withId(
                    client.getId(), "user-42")
                .scope("openid")
                .scope("profile")
                .authority(new SimpleGrantedAuthority(
                    "PERMISSION_invoice.read"))
                .build();

        consentService.save(consent);

        OAuth2AuthorizationConsent loaded =
            consentService.findById(client.getId(), "user-42");

        assertThat(loaded).isNotNull();
        assertThat(loaded.getRegisteredClientId()).isEqualTo(client.getId());
        assertThat(loaded.getPrincipalName()).isEqualTo("user-42");
        assertThat(loaded.getScopes())
            .containsExactlyInAnyOrder("openid", "profile");
        assertThat(loaded.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("PERMISSION_invoice.read");
    }
}
~~~

Đây là integration test skeleton. Test database cần có schema consent và RegisteredClient đã seed trước. Với implementation comma-delimited, dùng authority names không chứa dấu phẩy hoặc test rõ serializer/escaping đã chọn.

### 17.2. Test composite-key isolation

Tạo hai consent:

- Cùng principalName nhưng khác registeredClientId;
- Cùng registeredClientId nhưng khác principalName.

Sau đó xác minh findById trả đúng authorities cho từng cặp. Đây là test ngăn lỗi dùng nhầm một phần của composite key.

### 17.3. Test update thay thế tập authorities

1. Save consent có openid, profile và email.
2. Save consent mới chỉ có openid và profile.
3. Đọc lại record.
4. Xác minh email không còn trong authorities.

Test này phát hiện implementation save tự union quyền cũ và mới.

### 17.4. Test remove và missing consent

Kiểm tra:

- findById trả null khi record chưa tồn tại;
- remove record tồn tại;
- remove lần thứ hai không làm hỏng service nếu implementation chọn idempotent semantics;
- findById sau remove trả null;
- Remove của client A không xóa consent của client B.

### 17.5. Test integrity của RegisteredClient

Tạo consent row tham chiếu registeredClientId không tồn tại rồi gọi findById. Implementation nên phát hiện record mồ côi theo policy, thay vì trả về một consent không thể gắn với RegisteredClient hợp lệ.

Đồng thời test save từ chối client ID không tồn tại nếu service áp dụng kiểm tra này.

### 17.6. Test transaction rollback

Tạo một lỗi sau khi ghi entity hoặc authority rows nhưng trước khi transaction commit. Xác minh parent record và child rows cùng rollback. Với bảng con chuẩn hóa, không được để parent tồn tại mà thiếu authorities hoặc child rows mồ côi.

### 17.7. Test concurrent updates

Chạy hai transaction cùng đọc một consent rồi ghi hai tập authorities khác nhau. Xác minh optimistic locking hoặc policy conflict được thực thi. Không để kết quả cuối cùng là hợp của hai tập nếu người dùng đã chủ động thu hồi một quyền.

Với JPA integration tests, có thể dùng Testcontainers để chạy trên cùng database engine với production. H2 phù hợp cho test nhanh nhưng không thay thế kiểm tra dialect, composite key, locking và transaction behavior trên database thật.

## 18. Kiểm thử authorization consent flow end-to-end

Một integration test đầy đủ nên chạy qua Authorization Server filter chain:

1. Seed RegisteredClient với authorization_code, redirect URI và scopes;
2. Đăng nhập resource owner;
3. Gửi authorization request yêu cầu openid/profile/email;
4. Xác nhận consent page xuất hiện khi policy yêu cầu;
5. POST form với state hợp lệ và chỉ chấp thuận openid/profile;
6. Xác nhận consent record chỉ chứa authorities đã chọn;
7. Gửi lại authorization request tương ứng;
8. Xác nhận consent service được tra cứu và behavior phù hợp policy;
9. Thu hồi consent rồi gửi request lại;
10. Xác nhận consent được yêu cầu lại theo policy.

Có thể dùng MockMvc để gửi authorization request và consent POST qua SecurityFilterChain thật. MockMvc kiểm tra filter/provider wiring; Testcontainers kiểm tra persistence engine. Hai lớp test bổ sung cho nhau.

### 18.1. Test state và CSRF

Gửi consent POST với state sai, thiếu CSRF token hoặc client ID không khớp. Request phải bị từ chối. Không để custom consent controller gọi consentService.save trực tiếp trước khi Authorization Endpoint xác thực state.

### 18.2. Test scope không được client đăng ký

Gửi form cố tình thêm scope mà RegisteredClient không được phép yêu cầu. Provider phải từ chối hoặc bỏ qua theo validation contract; consent store không được lưu scope ngoài request/registration policy.

### 18.3. Test partial consent

Client yêu cầu nhiều scopes, resource owner chỉ chấp thuận một phần. Kiểm tra:

- Consent lưu đúng authorities được chọn;
- Authorization response tuân thủ flow và policy;
- Scope bị từ chối không xuất hiện trong consent record;
- Lần sau yêu cầu thêm scope sẽ kích hoạt consent bổ sung nếu cần.

## 19. Hiệu năng và vận hành

Consent lookup thường nằm trên authorization request path. Database chậm hoặc cache không nhất quán có thể làm login/SSO chậm hoặc dẫn đến quyết định consent sai.

### 19.1. Index

Composite primary key trên registered_client_id và principal_name hỗ trợ lookup chính của service. Với bảng con authorities, index/fk trên cùng hai cột hỗ trợ load collection và cleanup.

Không tạo index theo authority nếu không có query path quản trị hoặc analytics cụ thể. Dùng EXPLAIN với database và dữ liệu gần production.

### 19.2. Cache

Cache có thể giảm database reads, nhưng consent thay đổi khi người dùng cấp hoặc thu hồi quyền. Cache stale có thể khiến OP tiếp tục bỏ qua consent screen hoặc tiếp tục tin quyền đã bị thu hồi.

Nếu cache:

- Key phải chứa cả registeredClientId và principalName;
- Save/remove phải invalidate hoặc cập nhật cache atomically;
- Đặt TTL phù hợp với consent freshness requirement;
- Không cache cross-tenant;
- Có cơ chế xử lý cache outage;
- Đo read-after-write consistency.

Không dùng cache local per-node mà không có invalidation giữa các nodes.

### 19.3. Retention

Consent không nhất thiết có expiresAt. Policy có thể giữ tới khi người dùng thu hồi, client bị decommission hoặc tài khoản bị xóa. Nếu có consent expiration, cần lưu timestamp/expiry ở custom entity và định nghĩa cách authorization endpoint xử lý consent đã hết hạn.

Không tự đặt TTL ngắn cho Redis chỉ để giải phóng bộ nhớ nếu điều đó làm người dùng liên tục bị hỏi consent lại.

### 19.4. Metrics và audit

Theo dõi các chỉ số không chứa PII:

| Metric/event | Ý nghĩa |
|---|---|
| oauth2_consent_find_total | Số lookup consent |
| oauth2_consent_not_found_total | Consent chưa tồn tại |
| oauth2_consent_save_total | Số lần cấp/cập nhật consent |
| oauth2_consent_remove_total | Số lần thu hồi consent |
| oauth2_consent_store_latency | Độ trễ persistence |
| oauth2_consent_store_errors | Lỗi database/cache/external store |
| oauth2_consent_conflicts | Concurrent update conflicts |
| oauth2_consent_authority_count | Số authorities trong record |

Không dùng principalName hoặc raw authority set làm metric labels có cardinality cao. Audit log có thể ghi principal đã pseudonymize, client ID, authority delta, actor, timestamp và correlation ID theo policy.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Consent screen luôn xuất hiện | Service luôn trả null hoặc principal key thay đổi | Kiểm tra composite key và principalName |
| Consent screen không xuất hiện dù user chưa cấp quyền | Service trả nhầm record/client hoặc merge quyền sai | Kiểm tra registeredClientId và authorities |
| Scope mới không được hỏi consent | Implementation tự union authorities cũ hoặc policy sai | Kiểm tra consent comparison và update semantics |
| Save thành công nhưng restart mất consent | Vẫn dùng InMemory implementation | Kiểm tra bean wiring và database |
| Node A thấy consent, node B không thấy | Mỗi node dùng store/cache riêng | Shared persistence và cache invalidation |
| Record bị ghi đè giữa các clients | Key chỉ dùng principalName | Composite key |
| Record bị ghi đè giữa users | Key chỉ dùng registeredClientId | Composite key |
| findById báo RegisteredClient không tồn tại | Consent record mồ côi hoặc client bị xóa | Client lifecycle và migration |
| Authorities bị cắt ngắn | Column length quá nhỏ | Đo kích thước, TEXT/JSON hoặc child table |
| Authority bị tách sai | Comma-delimited chứa delimiter trong value | Dùng JSON/normalized table |
| Remove consent nhưng token vẫn active | Consent và token lifecycle khác nhau | Revoke authorization/token theo policy |
| Hai tab ghi đè quyết định | Concurrent update không có conflict policy | Optimistic lock hoặc serialized update |
| Consent POST bị lỗi CSRF/state | Form thiếu token hoặc state không khớp | Template và Authorization Endpoint |
| JPA không load authorities | Fetch strategy hoặc mapping sai | SQL, transaction và entity mapping |

### 20.1. Quy trình chẩn đoán

1. Xác định OAuth2AuthorizationConsentService bean thực tế.
2. Kiểm tra registeredClientId nội bộ và principalName từ authentication.
3. Kiểm tra row bằng truy vấn read-only có kiểm soát.
4. Xác minh composite key và authority serialization.
5. Kiểm tra transaction commit và unique constraint.
6. Kiểm tra cache invalidation giữa các nodes.
7. Tái hiện trên test database clone trước khi sửa dữ liệu production.

Không log consent form state token, session cookie hoặc dữ liệu xác thực để chẩn đoán.

## 21. Checklist production

1. **Service:** Authorization Server dùng đúng custom OAuth2AuthorizationConsentService?
2. **Identity:** registeredClientId và principalName ổn định, nhất quán?
3. **Key:** Storage dùng composite key của cả client và principal?
4. **Authorities:** Serializer bảo toàn mọi authority và không cắt ngắn?
5. **Save:** save lưu đúng snapshot, không union quyền cũ ngoài ý muốn?
6. **Find:** findById trả null khi không có consent và phát hiện dữ liệu mồ côi?
7. **Remove:** remove chỉ xóa đúng client/principal và idempotent theo policy?
8. **Authorization flow:** Authorization Code provider dùng đúng service?
9. **Consent UI:** POST về Authorization Endpoint, có state và CSRF?
10. **Validation:** Client ID/scopes được xác minh với RegisteredClient và request?
11. **Partial consent:** Chỉ lưu authorities người dùng thực sự cấp?
12. **Revocation:** Có policy riêng cho token/authorization đang tồn tại sau khi consent bị thu hồi?
13. **Transactions:** Parent/authority rows và updates cùng transaction?
14. **Concurrency:** Có conflict policy cho hai consent updates đồng thời?
15. **Multi-node:** Shared store và cache invalidation nhất quán?
16. **Tenant:** Tenant context không bị caller giả mạo hoặc gây key collision?
17. **Security:** DB access, TLS, backup, admin APIs và audit được bảo vệ?
18. **Retention:** Consent expiry/deletion policy được định nghĩa?
19. **Testing:** Có round-trip, composite isolation, partial consent, revoke, CSRF/state và cluster tests?
20. **Operations:** Có metrics, alert và backup/restore procedure?

## 22. Bài tập vận dụng

**Tình huống A — Consent bị mất sau restart:** Authorization Server dùng InMemoryOAuth2AuthorizationConsentService. Người dùng đã đồng ý profile nhưng sau deploy lại phải consent lần nữa. Hãy thay bằng JPA service và kiểm tra database persistence.

**Tình huống B — Hai clients dùng chung một principal:** portal-web và mobile-app ghi đè consent của nhau. Xác định lỗi key và thiết kế composite primary key.

**Tình huống C — Partial consent:** Người dùng cấp openid/profile nhưng từ chối email. Sau đó client yêu cầu thêm email. Xây dựng test chứng minh service không tự cấp scope mới.

**Tình huống D — Thu hồi consent:** Người dùng xóa consent cho một client nhưng access token cũ vẫn được Resource Server chấp nhận. Giải thích ranh giới giữa consent state và token lifecycle, rồi đề xuất revoke policy.

**Tình huống E — Concurrent updates:** Hai tab cập nhật cùng một consent, một tab thêm email, tab kia thu hồi profile. Thiết kế optimistic locking và xử lý conflict mà không khôi phục quyền đã thu hồi.

**Tình huống F — Authority có dấu phẩy:** Một custom authority chứa dấu phẩy làm comma-delimited serialization không round-trip. Hãy thay schema bằng JSON hoặc bảng authority chuẩn hóa.

**Tình huống G — Multi-tenant:** Hai tenant có principalName giống nhau và client IDs giống nhau. Vì sao service interface chưa đủ tenant key? Thiết kế namespace hoặc store partition.

**Gợi ý:** A dùng persistent custom bean và verify wiring; B dùng (registeredClientId, principalName); C lưu đúng authority snapshot; D revoke token/authorization riêng; E dùng @Version hoặc serialized updates; F dùng JSON/child table; G namespace client/principal hoặc tách schema/store theo tenant.

## 23. Tổng kết

OAuth2AuthorizationConsentService quản lý các quyết định consent đã cấp cho một RegisteredClient bởi một resource owner. Domain model OAuth2AuthorizationConsent có composite identity gồm registeredClientId và principalName, cùng Set<GrantedAuthority>. Ba thao tác của service là save, remove và findById.

Spring Authorization Server mặc định dùng InMemoryOAuth2AuthorizationConsentService nếu ứng dụng không cung cấp service. Implementation này phù hợp development/test; production thường cần JDBC hoặc custom persistence dùng chung. Với JPA, có thể ánh xạ composite key vào entity, lưu authority set, dùng repository để truy vấn và triển khai adapter chuyển đổi domain model.

Authorization Code request provider dùng consent service để đọc quyết định hiện có; consent authentication provider lưu quyết định được người dùng gửi về. Consent page phải POST về Authorization Endpoint với client_id, state và scopes đã chọn, đồng thời giữ CSRF protection và protocol validation.

Custom implementation phải giữ đúng composite key, persist snapshot authorities, xử lý transaction/concurrency, xác minh RegisteredClient và bảo đảm read-after-write consistency giữa các nodes. Thu hồi consent không tự động thu hồi access token/refresh token đã cấp; cần policy token lifecycle riêng. Khi các ranh giới này rõ ràng, consent persistence trở thành một phần bền vững và có thể kiểm thử của Authorization Server.

## 24. Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 API — OAuth2AuthorizationConsentService](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html): contract save, remove và findById.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2AuthorizationConsent, authorities và consent service.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): schema, entity, repository và JpaOAuth2AuthorizationConsentService.
- [Spring Authorization Server API — OAuth2AuthorizationConsent](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsent.html): builder, withId, authorities và scopes.
- [Spring Authorization Server API — OAuth2AuthorizationServerConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerConfigurer.html): cấu hình authorizationConsentService.
- [Spring Authorization Server API — OAuth2AuthorizationCodeRequestAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationCodeRequestAuthenticationProvider.html): authorization request provider và consent-required predicate.
- [Spring Authorization Server API — OAuth2AuthorizationConsentAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationConsentAuthenticationProvider.html): xử lý consent request và consent customizer.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived query methods và repository semantics.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): entity mapping, composite identifiers, transactions và optimistic locking.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative transaction boundaries.
