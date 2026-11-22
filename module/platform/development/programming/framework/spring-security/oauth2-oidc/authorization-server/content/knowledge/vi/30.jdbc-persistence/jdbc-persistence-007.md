# Cấu hình Jackson module cần thiết và kiểm soát deserialization

## 1. Vì sao JDBC persistence cần cấu hình Jackson đúng?

Spring Authorization Server lưu nhiều đối tượng có cấu trúc phức tạp. JdbcRegisteredClientRepository lưu cấu hình của RegisteredClient; JdbcOAuth2AuthorizationService lưu trạng thái của OAuth2Authorization. Các implementation JDBC chuyển một số thuộc tính, settings và token metadata thành JSON để ghi vào các cột trong database, rồi đọc JSON trở lại thành Java object.

Một ObjectMapper thuần có thể không biết cách xử lý các kiểu dữ liệu và collection mà Spring Security/Spring Authorization Server sử dụng. Ví dụ, authorization attributes có thể chứa Authentication, authorization request hoặc collection không sửa đổi; client settings có thể chứa Duration, thuật toán JWS và token format. Nếu mapper thiếu module/mixin tương ứng, ứng dụng có thể gặp lỗi serialize, deserialize hoặc không khôi phục đúng kiểu dữ liệu sau khi restart.

Spring cung cấp hai nhóm module cần phân biệt:

- **SecurityJackson2Modules**: tìm các Jackson module do Spring Security cung cấp trên classpath.
- **OAuth2AuthorizationServerJackson2Module**: đăng ký các mixin cần cho kiểu dữ liệu của Spring Authorization Server.

Bài học thuộc chương **Lưu trữ JDBC**, tập trung cấu hình các module Jackson cần thiết, nối mapper vào cả hai chiều ghi/đọc của JDBC repositories và kiểm soát rủi ro polymorphic deserialization.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định phần dữ liệu nào của RegisteredClient và OAuth2Authorization được lưu dưới dạng JSON.
2. Giải thích vai trò của SecurityJackson2Modules và OAuth2AuthorizationServerJackson2Module.
3. Tạo một ObjectMapper riêng cho persistence.
4. Cấu hình mapper cho RegisteredClientRowMapper và RegisteredClientParametersMapper.
5. Cấu hình mapper cho OAuth2AuthorizationRowMapper và OAuth2AuthorizationParametersMapper.
6. Hiểu vì sao phải cấu hình đồng bộ serialization và deserialization.
7. Kiểm soát polymorphic type metadata và ranh giới dữ liệu tin cậy.
8. Bổ sung module/mixin cho custom attributes một cách có chủ đích.
9. Kiểm thử round-trip và tương thích dữ liệu qua các lần nâng cấp.
10. Nhận diện khác biệt giữa Jackson 2 và Jackson 3 trong các phiên bản Spring mới.

## 2. Jackson tham gia vào JDBC persistence ở đâu?

Quá trình lưu trữ có hai chiều:

~~~mermaid
flowchart LR
    A[RegisteredClient / OAuth2Authorization] --> B[ParametersMapper]
    B --> C[ObjectMapper]
    C --> D[JSON columns]
    D --> E[RowMapper]
    E --> F[ObjectMapper]
    F --> G[RegisteredClient / OAuth2Authorization]
~~~

ParametersMapper chuyển Java object thành các tham số SQL. Khi cần lưu map/settings/metadata, mapper dùng Jackson để tạo JSON. RowMapper đọc các cột JSON và khôi phục map hoặc settings cần thiết để dựng domain object.

Có hai cặp mapper:

| JDBC component | Chiều ghi | Chiều đọc |
|---|---|---|
| JdbcRegisteredClientRepository | RegisteredClientParametersMapper | RegisteredClientRowMapper |
| JdbcOAuth2AuthorizationService | OAuth2AuthorizationParametersMapper | OAuth2AuthorizationRowMapper |

Mỗi cặp phải hiểu cùng một định dạng JSON. Nếu chiều ghi và chiều đọc dùng cấu hình khác nhau, một record có thể ghi thành công nhưng không đọc lại được.

### 2.1. RegisteredClient có dữ liệu JSON nào?

RegisteredClient chứa các field đơn giản như client ID, client secret, client name, redirect URI và scope. Hai cấu trúc settings có dữ liệu linh hoạt hơn:

- clientSettings: các thiết lập như yêu cầu PKCE, consent và các setting mở rộng.
- tokenSettings: TTL, token format, refresh token reuse và các setting token khác.

JDBC repository lưu settings thành JSON. Kiểu dữ liệu bên trong có thể không chỉ là chuỗi; một số giá trị là Duration, enum/kiểu Spring Security hoặc kiểu settings chuyên biệt.

### 2.2. OAuth2Authorization có dữ liệu JSON nào?

OAuth2Authorization lưu trạng thái grant, principal, authorized scopes, attributes và metadata của từng token. Trong schema JDBC chuẩn, token value và thời gian phát hành/hết hạn thường nằm ở các cột riêng; các map như authorization attributes và token metadata được serialize thành JSON.

Ví dụ dữ liệu có thể cần lưu:

- Authorization attributes, trong đó có thể có authentication hoặc authorization request.
- Metadata của authorization code.
- Metadata của access token.
- Metadata của refresh token.
- Claims và metadata liên quan ID Token.
- Metadata của user code hoặc device code nếu grant sử dụng chúng.

Không phải toàn bộ OAuth2Authorization được biến thành một JSON blob duy nhất. JDBC implementation trải dữ liệu ra nhiều cột và dùng JSON cho các map/metadata.

## 3. Hai nhóm Jackson module cần đăng ký

### 3.1. SecurityJackson2Modules

SecurityJackson2Modules.getModules(ClassLoader) tìm các Jackson module do những Spring Security module có mặt trên classpath cung cấp. Ví dụ có thể gồm module cho Spring Security Core, Web, Servlet, OAuth2 Client, CAS hoặc SAML tùy dependency.

Các module này cung cấp mixin/serializer cần thiết cho những kiểu Spring Security. Ví dụ, CoreJackson2Module đăng ký mixin cho các kiểu như SimpleGrantedAuthority, User, UsernamePasswordAuthenticationToken và các collection không sửa đổi.

Không cần tự đăng ký từng module Spring Security bằng tay khi đã dùng utility này.

### 3.2. OAuth2AuthorizationServerJackson2Module

Đây là module riêng của Spring Authorization Server. Trong dòng Jackson 2, module đăng ký các mixin cho những kiểu như:

- UnmodifiableMap và HashSet.
- OAuth2AuthorizationRequest.
- OAuth2TokenExchangeCompositeAuthenticationToken.
- Duration.
- JwsAlgorithm.
- OAuth2TokenFormat.
- String[] trong các cấu trúc cần thiết.

Các mixin giúp Jackson xử lý kiểu dữ liệu mà default bean introspection không thể khôi phục chính xác. Module này cũng bật default typing khi mapper chưa có type information mechanism, vì một số cấu trúc cần thông tin kiểu để serialize/deserialize.

### 3.3. Vì sao cần cả hai?

OAuth2AuthorizationServerJackson2Module xử lý kiểu đặc thù của Authorization Server. SecurityJackson2Modules xử lý kiểu Spring Security nền tảng xuất hiện trong attributes hoặc metadata. Chỉ đăng ký một nhóm có thể làm các kiểu thuộc nhóm còn lại không được hỗ trợ.

## 4. Tạo ObjectMapper riêng cho persistence

Ví dụ dưới đây dùng Spring Authorization Server 1.5.x và Jackson 2 (com.fasterxml.jackson.databind.ObjectMapper):

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.jackson2
    .OAuth2AuthorizationServerJackson2Module;

ObjectMapper authorizationPersistenceObjectMapper() {
    ObjectMapper objectMapper = new ObjectMapper();

    ClassLoader classLoader =
        JdbcOAuth2AuthorizationService.class.getClassLoader();

    List<Module> securityModules =
        SecurityJackson2Modules.getModules(classLoader);

    objectMapper.registerModules(securityModules);
    objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module());

    return objectMapper;
}
~~~

Thứ tự trên theo cách cấu hình được dùng trong Spring Authorization Server: đăng ký các module Spring Security trước, sau đó đăng ký module Authorization Server.

### 4.1. Đăng ký một lần trước khi dùng

Cấu hình xong mapper trước khi repositories xử lý request đầu tiên. ObjectMapper có thể được dùng đồng thời sau khi cấu hình hoàn tất, nhưng không nên tiếp tục thay đổi module, mixin hoặc feature trong lúc nhiều thread đang serialize/deserialize.

Đặt mapper trong một bean có vòng đời ứng dụng và inject vào các JDBC mapper. Không tạo một mapper mới cho mỗi lần đọc/ghi database.

### 4.2. Dùng qualifier thay vì thay ObjectMapper toàn ứng dụng

Nên đặt tên bean rõ mục đích:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationPersistenceJacksonConfiguration {

    @Bean
    @Qualifier("authorizationPersistenceObjectMapper")
    ObjectMapper authorizationPersistenceObjectMapper() {
        ObjectMapper objectMapper = new ObjectMapper();

        ClassLoader classLoader =
            JdbcOAuth2AuthorizationService.class.getClassLoader();

        objectMapper.registerModules(
            SecurityJackson2Modules.getModules(classLoader));
        objectMapper.registerModule(
            new OAuth2AuthorizationServerJackson2Module());

        return objectMapper;
    }
}
~~~

Bean này dành cho JSON được lưu trong các bảng authorization. Không cần đánh dấu nó là Primary hoặc thay mapper mà Spring MVC dùng để đọc request JSON từ browser/API.

Giữ mapper persistence tách biệt giúp giới hạn nơi có polymorphic deserialization và tránh vô tình áp dụng cấu hình này cho JSON không tin cậy từ HTTP.

## 5. Cấu hình JdbcRegisteredClientRepository ở cả hai chiều

JdbcRegisteredClientRepository cho phép thay RegisteredClientRowMapper và RegisteredClientParametersMapper. Cần truyền cùng ObjectMapper vào cả hai.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcOperations jdbcOperations,
        @Qualifier("authorizationPersistenceObjectMapper")
        ObjectMapper objectMapper) {

    JdbcRegisteredClientRepository repository =
        new JdbcRegisteredClientRepository(jdbcOperations);

    JdbcRegisteredClientRepository.RegisteredClientRowMapper rowMapper =
        new JdbcRegisteredClientRepository.RegisteredClientRowMapper();
    rowMapper.setObjectMapper(objectMapper);

    JdbcRegisteredClientRepository.RegisteredClientParametersMapper
        parametersMapper =
            new JdbcRegisteredClientRepository
                .RegisteredClientParametersMapper();
    parametersMapper.setObjectMapper(objectMapper);

    repository.setRegisteredClientRowMapper(rowMapper);
    repository.setRegisteredClientParametersMapper(parametersMapper);

    return repository;
}
~~~

### 5.1. RowMapper chịu trách nhiệm gì?

RegisteredClientRowMapper đọc các cột settings từ ResultSet và dựng lại RegisteredClient. Khi đọc JSON settings, nó sử dụng ObjectMapper đã được gắn qua setObjectMapper.

Nếu settings chứa một kiểu cần mixin nhưng mapper không có module tương ứng, lỗi thường xuất hiện ở bước khởi động Authorization Server hoặc khi client được truy vấn.

### 5.2. ParametersMapper chịu trách nhiệm gì?

RegisteredClientParametersMapper chuyển RegisteredClient thành danh sách SqlParameterValue để ghi xuống database. Các settings được serialize thành JSON bằng ObjectMapper của mapper này.

Nếu chỉ cấu hình RowMapper mà không cấu hình ParametersMapper, hai chiều có thể sử dụng hai định dạng khác nhau. Với custom module hoặc custom metadata, cần cấu hình cả hai.

## 6. Cấu hình JdbcOAuth2AuthorizationService ở cả hai chiều

JdbcOAuth2AuthorizationService cũng có cặp mapper riêng. Row mapper còn cần RegisteredClientRepository để dựng authorization từ registration đã lưu.

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository,
        @Qualifier("authorizationPersistenceObjectMapper")
        ObjectMapper objectMapper) {

    JdbcOAuth2AuthorizationService service =
        new JdbcOAuth2AuthorizationService(
            jdbcOperations, registeredClientRepository);

    JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper rowMapper =
        new JdbcOAuth2AuthorizationService
            .OAuth2AuthorizationRowMapper(registeredClientRepository);
    rowMapper.setObjectMapper(objectMapper);

    JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper
        parametersMapper =
            new JdbcOAuth2AuthorizationService
                .OAuth2AuthorizationParametersMapper();
    parametersMapper.setObjectMapper(objectMapper);

    service.setAuthorizationRowMapper(rowMapper);
    service.setAuthorizationParametersMapper(parametersMapper);

    return service;
}
~~~

### 6.1. RowMapper dựng lại authorization

Khi đọc một authorization, row mapper:

1. Đọc registered client ID.
2. Tìm RegisteredClient tương ứng qua RegisteredClientRepository.
3. Đọc principal, grant type và authorized scopes.
4. Đọc các cột token, issued-at, expires-at và metadata.
5. Dùng ObjectMapper để parse các JSON map.
6. Dựng lại OAuth2Authorization cùng token metadata.

Vì thế, RegisteredClientRepository phải hoạt động trước khi authorization service được sử dụng. Nếu registration tham chiếu không còn tồn tại, row mapper không thể dựng authorization đầy đủ.

### 6.2. ParametersMapper ghi lại authorization

OAuth2AuthorizationParametersMapper chuyển authorization thành các tham số SQL. Những map attributes và token metadata được serialize bằng ObjectMapper.

Nếu application lưu custom attribute, custom authentication hoặc object mở rộng trong authorization, mapper ghi và mapper đọc phải hiểu cùng kiểu dữ liệu đó.

## 7. Cấu hình hoàn chỉnh: thứ tự phụ thuộc giữa các bean

Hai repository có quan hệ phụ thuộc:

~~~mermaid
flowchart TD
    M[authorizationPersistenceObjectMapper]
    R[JdbcRegisteredClientRepository]
    A[JdbcOAuth2AuthorizationService]
    M --> R
    M --> A
    R --> A
~~~

RegisteredClientRepository cần được tạo trước để JdbcOAuth2AuthorizationService dùng nó khi đọc authorization. ObjectMapper được chia sẻ cho các mapper ghi/đọc của cả hai repository.

Không tạo hai mapper persistence riêng với cấu hình khác nhau nếu chúng cùng đọc/ghi các kiểu JSON tương thích. Một mapper dùng chung giúp tránh sai lệch module, mixin và feature.

### 7.1. Bảo đảm application dùng đúng bean

Trong Authorization Server configuration, các bean core services phải tham chiếu tới repository JDBC đã cấu hình. Nếu vẫn có một bean in-memory khác được inject do cấu hình trùng hoặc qualifier sai, ứng dụng có thể khởi động nhưng dữ liệu không được đọc/ghi như mong đợi.

Kiểm tra dependency injection trong ApplicationContext và xác minh một record được ghi có thể được đọc lại từ cùng repository.

## 8. Chỉ thay mapper khi có lý do

Các JDBC implementation của Spring Authorization Server đã cung cấp default row mapper và parameter mapper. Ở các phiên bản tương ứng, chúng đã có cấu hình Jackson cần thiết cho các kiểu framework được hỗ trợ.

Nếu chỉ dùng các kiểu chuẩn và không cần custom serialization, hãy ưu tiên mapper mặc định của đúng phiên bản dependency. Tạo mapper riêng khi bạn cần:

- Bổ sung custom attribute type.
- Đăng ký module/mixin cho kiểu ứng dụng.
- Chuẩn hóa ObjectMapper dùng chung giữa nhiều persistence service.
- Kiểm soát chính sách deserialization theo yêu cầu của hệ thống.
- Di chuyển định dạng JSON hoặc tương thích với dữ liệu cũ.

Khi thay mapper mặc định, phải giữ lại đầy đủ các module Spring Security và Authorization Server mà dữ liệu đang lưu cần.

## 9. Hiểu polymorphic type metadata

Một JSON map có thể chứa nhiều kiểu Java khác nhau. Ví dụ, authorization attributes có thể chứa một chuỗi, một boolean, một map, một set hoặc một đối tượng Authentication. Khi serialize thành JSON, chỉ có cấu trúc JSON cơ bản chưa đủ để luôn khôi phục đúng Java type.

Polymorphic type metadata lưu thêm thông tin kiểu để Jackson biết đối tượng cụ thể cần dựng lại. Spring Security và Authorization Server dùng cơ chế này cho một số object/collection.

Ví dụ minh họa về ý tưởng (không phải JSON cố định mà ứng dụng nên tự tạo):

~~~json
{
  "@class": "some.trusted.package.SomeSupportedType",
  "value": "example"
}
~~~

Tên property và cấu trúc thực tế phụ thuộc mapper/module. Không dựa vào ví dụ này để viết tay JSON vào cột database.

### 9.1. Vì sao default typing xuất hiện?

SecurityJackson2Modules và OAuth2AuthorizationServerJackson2Module hỗ trợ type information cần thiết cho các kiểu framework. Trong Jackson 2, việc đăng ký security modules có thể bật default typing cho non-final types; module Authorization Server cũng tự bật default typing nếu mapper chưa bật.

Điều đó giúp round-trip các object polymorphic, nhưng đồng thời mở rộng bề mặt deserialization. Vì vậy, mapper này chỉ nên đọc dữ liệu persistence thuộc trust boundary mà ứng dụng kiểm soát.

### 9.2. Không dùng default typing toàn cục một cách tùy tiện

Không bật default typing rộng trên mapper dùng cho mọi request/response JSON. Tránh các cấu hình cho phép mọi subtype, ví dụ validator kiểu permissive hoặc chấp nhận tùy ý class name do input điều khiển.

Dùng mapper persistence chuyên biệt và chỉ đăng ký các module cần thiết. Không deserialize payload JSON do browser, public API hoặc tenant không tin cậy gửi bằng mapper này.

## 10. Xác định trust boundary của JSON trong database

Dữ liệu trong database thường được ứng dụng xem là dữ liệu nội bộ, nhưng database không tự động trở thành nguồn đáng tin trong mọi tình huống. JSON có thể bị sửa bởi:

- Tài khoản database có quyền ghi quá rộng.
- Script vận hành hoặc migration chạy nhầm.
- Công cụ quản trị trực tiếp sửa cột metadata.
- Một lỗ hổng SQL injection.
- Một dịch vụ khác ghi vào cùng schema nhưng không tuân theo contract.

Nếu attacker có thể kiểm soát type metadata rồi ứng dụng deserialize bằng default typing, hậu quả có thể nghiêm trọng hơn lỗi parse JSON thông thường.

### 10.1. Giới hạn quyền database

- Chỉ service account cần thiết được ghi vào bảng authorization/client.
- Tách quyền đọc và ghi nếu kiến trúc cho phép.
- Không cấp quyền DDL hoặc quyền quản trị schema cho runtime account.
- Không cho ứng dụng không liên quan ghi vào các cột JSON này.
- Theo dõi thay đổi bất thường ở bảng registration và authorization.
- Bảo vệ backup, snapshot và môi trường staging có dữ liệu production.

### 10.2. Không coi token là bảo vệ JSON trong database

OAuth token bảo vệ protocol endpoints. Chúng không thay thế quyền truy cập database. Một dịch vụ có thể được xác thực hợp lệ qua OAuth nhưng vẫn không nên có quyền ghi tùy ý vào bảng JSON persistence của Authorization Server.

## 11. Custom attributes: lưu kiểu đơn giản trước

OAuth2Authorization.Builder cho phép lưu attributes tùy biến. Dù tiện lợi, tránh đưa cả object graph lớn hoặc kiểu framework bất kỳ vào attributes.

Ưu tiên các kiểu ổn định và dễ tương thích:

- String.
- Boolean và kiểu số.
- List/Set của giá trị đơn giản.
- Map<String, Object> với cấu trúc được kiểm soát.
- DTO nhỏ, có schema/version rõ ràng nếu thật sự cần.

Ví dụ:

~~~java
OAuth2Authorization authorization =
    OAuth2Authorization.withRegisteredClient(registeredClient)
        .principalName("user-42")
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .attribute("tenant_id", "tenant-17")
        .attribute("login_channel", "web")
        .build();
~~~

Các giá trị trên dễ hiểu và ít phụ thuộc class name hơn một object custom phức tạp.

### 11.1. Tránh lưu đối tượng không cần thiết

Không lưu toàn bộ HttpServletRequest, EntityManager, JDBC Connection, service bean, application context hoặc object có vòng tham chiếu vào authorization attributes. Các object này không phải dữ liệu persistence và có thể không serialize được.

Không lưu raw password, client secret chưa encode, private key hoặc dữ liệu xác thực không cần thiết trong JSON attributes.

## 12. Khi cần lưu custom Java type

Nếu ứng dụng thực sự cần một custom type, hãy xác định contract trước:

1. Kiểu dữ liệu có phải là một phần cần tồn tại qua restart không?
2. Có thể chuyển nó thành primitive/map/DTO ổn định hơn không?
3. Có serializer/deserializer rõ ràng không?
4. Class có thể đổi package hoặc đổi tên trong tương lai không?
5. Có migration cho các JSON cũ không?
6. Type có nằm trong phạm vi được phép deserialize không?

Có thể dùng Jackson mixin hoặc custom module để định nghĩa cách serialize/deserialize kiểu đó. Chỉ đăng ký kiểu cần thiết; không mở rộng sang toàn bộ package ứng dụng nếu không có lý do.

Ví dụ khái niệm:

~~~java
objectMapper.addMixIn(
    ApplicationAuthenticationContext.class,
    ApplicationAuthenticationContextMixin.class);
~~~

ApplicationAuthenticationContextMixin là mixin do ứng dụng định nghĩa. Nó phải mô tả đúng constructor/creator, property hoặc custom serializer cần dùng; tên class trong ví dụ không phải API của Spring.

### 12.1. Tên class có thể trở thành ràng buộc dữ liệu

Khi polymorphic typing lưu class name, JSON đã ghi có thể phụ thuộc package và tên class. Nếu refactor class hoặc chuyển package, dữ liệu cũ có thể không deserialize được.

Đối với dữ liệu sống lâu, nên cân nhắc schema/version riêng cho custom DTO, serializer/deserializer tương thích ngược hoặc migration JSON trước khi xóa class cũ.

## 13. Java Time và các module bổ sung

OAuth2AuthorizationServerJackson2Module có mixin cho Duration. Điều này không đồng nghĩa mọi kiểu thuộc Java Time API hoặc mọi custom type đều tự động được hỗ trợ.

Nếu custom attributes lưu Instant, LocalDate, OffsetDateTime hoặc kiểu JDK khác, hãy xác minh Jackson module cần thiết trong phiên bản đang dùng. Với Jackson 2, JavaTimeModule từ jackson-datatype-jsr310 có thể cần thiết cho các kiểu Java Time chưa được module khác xử lý.

Ví dụ nếu custom attribute thực sự cần Java Time:

~~~java
objectMapper.registerModule(new JavaTimeModule());
~~~

Không thêm module theo kiểu “cứ đăng ký hết cho chắc”. Mỗi module mở rộng tập kiểu dữ liệu được mapper hiểu; chỉ thêm dependency/serializer khi có dữ liệu cụ thể cần hỗ trợ.

## 14. Tương thích JSON khi nâng cấp phiên bản

JSON persistence có thể tồn tại lâu hơn một lần deploy. Nâng cấp Spring Security hoặc Spring Authorization Server có thể thay đổi:

- Các class hoặc mixin được hỗ trợ.
- Kiểu dữ liệu trong settings và metadata.
- Cách ghi type information.
- Module Jackson và API mapper.
- Các giá trị enum/algorithm mới.
- Cấu trúc custom attributes do ứng dụng thêm.

Một phiên bản mới có thể đọc dữ liệu cũ nhưng không có nghĩa mọi JSON mới sẽ đọc được bởi phiên bản cũ. Tránh rollout mixed-version kéo dài khi các node có serializer/deserializer khác nhau mà chưa xác nhận tương thích.

### 14.1. Migration theo hướng tương thích

Trước khi nâng cấp:

1. Backup các bảng client, authorization và consent.
2. Lấy snapshot JSON đại diện cho từng grant/token type.
3. Kiểm tra phiên bản mới đọc được dữ liệu cũ.
4. Kiểm tra phiên bản mới ghi dữ liệu và đọc lại được.
5. Kiểm tra rollback: phiên bản cũ có đọc được JSON đã ghi bởi phiên bản mới không.
6. Nếu không, lên kế hoạch migration và thời điểm cutover rõ ràng.

Không sửa tay type metadata trong database nếu không có migration tool và test round-trip.

## 15. Phân biệt lỗi serialize và lỗi deserialize

| Triệu chứng | Giai đoạn | Nguyên nhân thường gặp |
|---|---|---|
| InvalidDefinitionException khi save | Serialization | Không có serializer/creator phù hợp hoặc object graph không hỗ trợ |
| Không ghi được Duration/kiểu settings | Serialization | Thiếu module/mixin phù hợp |
| InvalidTypeIdException khi read | Deserialization | Type metadata không được nhận diện hoặc class không còn trên classpath |
| MismatchedInputException | Deserialization | JSON shape khác kiểu mapper mong đợi |
| UnrecognizedPropertyException | Deserialization | JSON chứa property mới mà model/mapper hiện tại không xử lý |
| Không khôi phục được Authentication | Deserialization | Thiếu Spring Security module hoặc type metadata |
| ClassNotFoundException | Deserialization | Dữ liệu lưu class name của package/class đã bị đổi hoặc gỡ |
| Dữ liệu bị cắt hoặc JSON malformed | Database/read | Column length, encoding hoặc migration sai |

### 15.1. Đọc root cause, không chỉ exception ngoài cùng

JDBC mapper có thể bọc lỗi Jackson thành exception khác khi đọc/ghi database. Khi điều tra, tìm root cause và xác định cột JSON cụ thể: clientSettings, tokenSettings, attributes hoặc token metadata.

Đừng xử lý mọi lỗi bằng cách tắt validation hoặc bật permissive default typing. Trước tiên xác định kiểu dữ liệu nào cần serializer/deserializer.

## 16. Kiểm thử round-trip cho RegisteredClient

Một test cần chứng minh client sau khi save có thể được đọc lại bằng chính repository:

~~~java
@Test
void registeredClientCanBeSavedAndReadBack() {
    RegisteredClient original = RegisteredClient
        .withId("registered-client-1")
        .clientId("orders-web")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.NONE)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://orders.example.com/login/oauth2/code/oidc")
        .scope(OidcScopes.OPENID)
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(5))
            .build())
        .build();

    registeredClientRepository.save(original);

    RegisteredClient restored =
        registeredClientRepository.findByClientId("orders-web");

    assertThat(restored).isNotNull();
    assertThat(restored.getId()).isEqualTo(original.getId());
    assertThat(restored.getTokenSettings().getAccessTokenTimeToLive())
        .isEqualTo(Duration.ofMinutes(5));
}
~~~

Đây là test integration với database test. Không mock JDBC mapper nếu mục tiêu là xác minh Jackson serialization/deserialization.

## 17. Kiểm thử round-trip cho OAuth2Authorization

Authorization test nên có attributes và token metadata thực tế mà ứng dụng sử dụng. Ví dụ khung:

~~~java
@Test
void authorizationAttributesCanBePersistedAndRestored() {
    OAuth2Authorization original =
        OAuth2Authorization.withRegisteredClient(registeredClient)
            .id("authorization-1")
            .principalName("user-42")
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("openid", "orders.read"))
            .attribute("tenant_id", "tenant-17")
            .attribute("login_channel", "web")
            .build();

    authorizationService.save(original);

    OAuth2Authorization restored =
        authorizationService.findById("authorization-1");

    assertThat(restored).isNotNull();
    assertThat(restored.getAttribute("tenant_id"))
        .isEqualTo("tenant-17");
    assertThat(restored.getAuthorizedScopes())
        .containsExactlyInAnyOrder("openid", "orders.read");
}
~~~

Test đầy đủ nên tạo token/metadata hợp lệ bằng builder/provider tương ứng, sau đó kiểm tra token value, issued-at, expires-at, claims và metadata sau khi đọc lại.

### 17.1. Test custom types

Nếu authorization attributes có custom DTO hoặc Authentication, thêm test cho:

- Save rồi đọc lại trong cùng process.
- Save, đóng ApplicationContext, khởi động lại rồi đọc.
- Đọc dữ liệu JSON cũ sau khi nâng cấp.
- JSON có type không được phép bị từ chối.
- Class cũ bị đổi tên có migration/compatibility path.

## 18. Kiểm thử âm cho deserialization

Không chỉ test trường hợp hợp lệ. Tạo dữ liệu sai có kiểm soát trong database test:

| Dữ liệu thử | Kết quả mong đợi |
|---|---|
| JSON malformed | Read thất bại rõ ràng, có root cause |
| Type ID không nằm trong contract | Bị từ chối |
| Class không còn trên classpath | Phát hiện lỗi tương thích |
| Property có kiểu không khớp | Bị từ chối hoặc xử lý theo migration đã định |
| JSON có custom class không đăng ký | Không tự động instantiate tùy ý |
| Cột JSON bị truncate | Phát hiện trong test persistence |
| Type metadata từ payload bên ngoài | Không được đưa vào mapper persistence |

Test âm nên chạy trên database cô lập; không thử sửa trực tiếp dữ liệu production.

## 19. Jackson 2 và Jackson 3: không trộn API

Spring Security 7 chuyển hướng hỗ trợ Jackson 3. Các API Jackson 2 như SecurityJackson2Modules và các mapper dùng com.fasterxml.jackson.databind.ObjectMapper được đánh dấu deprecated for removal trong dòng mới.

Các tên tương ứng ở Jackson 3 gồm:

| Jackson 2 | Jackson 3 |
|---|---|
| com.fasterxml.jackson.databind.ObjectMapper | tools.jackson.databind.json.JsonMapper |
| SecurityJackson2Modules | SecurityJacksonModules |
| OAuth2AuthorizationServerJackson2Module | OAuth2AuthorizationServerJacksonModule |
| RegisteredClientRowMapper | JsonMapperRegisteredClientRowMapper |
| RegisteredClientParametersMapper | JsonMapperRegisteredClientParametersMapper |
| OAuth2AuthorizationRowMapper | JsonMapperOAuth2AuthorizationRowMapper |
| OAuth2AuthorizationParametersMapper | JsonMapperOAuth2AuthorizationParametersMapper |

Trong Jackson 3, Spring Security cung cấp SecurityJacksonModules để đăng ký module, thêm type information và cấu hình PolymorphicTypeValidator. Có thể mở rộng validator với custom type cụ thể khi ứng dụng thực sự cần.

Ví dụ khái niệm Jackson 3:

~~~java
BasicPolymorphicTypeValidator.Builder validator =
    BasicPolymorphicTypeValidator.builder()
        .allowIfSubType(ApplicationPersistedAttribute.class);

JsonMapper jsonMapper = JsonMapper.builder()
    .addModules(SecurityJacksonModules.getModules(
        getClass().getClassLoader(), validator))
    .build();
~~~

Đây là hướng tiếp cận cho stack Jackson 3 tương ứng. Constructor và nested mapper class cần đối chiếu API Spring Security/Spring Authorization Server đúng phiên bản.

**Không truyền ObjectMapper của Jackson 2 vào constructor nhận JsonMapper của Jackson 3.** Hai thư viện có package và kiểu API khác nhau.

## 20. Checklist deserialization an toàn

- Chỉ dùng mapper persistence để đọc JSON từ kho dữ liệu thuộc trust boundary của Authorization Server.
- Không dùng mapper này cho HTTP request body hoặc file người dùng upload.
- Không bật default typing toàn cục cho mapper web/API.
- Không dùng validator cho phép mọi subtype.
- Giới hạn tài khoản database có quyền ghi vào các bảng authorization.
- Giới hạn custom attribute type và giữ schema nhỏ.
- Không lưu object graph không cần thiết trong authorization attributes.
- Dùng mixin/serializer/deserializer có chủ đích cho custom type.
- Kiểm tra dữ liệu cũ khi đổi package/class hoặc nâng cấp dependency.
- Có test round-trip, test âm và test qua restart.
- Redact token, secret và PII khỏi log lỗi persistence.
- Theo dõi lỗi type ID, class not found và JSON parse failures.

## 21. Vận hành và observability

Theo dõi các chỉ số:

- Lỗi serialize khi lưu RegisteredClient.
- Lỗi serialize khi lưu OAuth2Authorization.
- Lỗi deserialize theo từng repository.
- Tỷ lệ authorization/client record đọc thất bại.
- JSON parse error và unknown type ID.
- Kích thước JSON trong các cột settings/attributes/metadata.
- Số lượng record có custom attribute version cũ.
- Sự thay đổi lỗi sau khi deploy phiên bản mới.

Không log nguyên văn authorization attributes hoặc token metadata nếu chúng có thể chứa token, subject, email, client secret hoặc dữ liệu nhạy cảm.

### 21.1. Runbook khi restart xong không đọc được authorization

1. Xác nhận đúng ObjectMapper bean được inject vào cả row và parameters mapper.
2. Kiểm tra hai Jackson module đã đăng ký.
3. Xác định cột JSON đầu tiên gây lỗi.
4. Kiểm tra type ID có class tương ứng trên classpath không.
5. Kiểm tra module/mixin có thay đổi sau nâng cấp không.
6. Kiểm tra dữ liệu JSON có bị ghi bởi node phiên bản khác không.
7. Kiểm tra column length, encoding và migration.
8. Khôi phục từ backup hoặc chạy migration có kiểm thử nếu JSON đã hỏng.

Không khắc phục bằng cách bỏ toàn bộ type validation hoặc xóa authorization record khi chưa xác định ảnh hưởng tới grant/token đang hoạt động.

## 22. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đăng ký module Spring Security | Kiểu riêng của Authorization Server không được xử lý | Đăng ký thêm module Authorization Server |
| Chỉ đăng ký module Authorization Server | Một số Authentication/collection của Spring Security không khôi phục được | Đăng ký SecurityJackson2Modules |
| Chỉ cấu hình RowMapper | JSON ghi ra có thể không cùng contract với mapper đọc | Cấu hình cả ParametersMapper |
| Chỉ cấu hình ParametersMapper | Ghi thành công nhưng không đọc lại được | Cấu hình cả RowMapper |
| Dùng mapper web chung | Polymorphic deserialization lan sang dữ liệu HTTP | Tách mapper persistence |
| Lưu custom object graph lớn | JSON khó tương thích và khó kiểm soát | Lưu DTO/primitive nhỏ |
| Refactor class name | JSON cũ có thể không tìm thấy class | Migration hoặc compatibility type |
| Dùng Jackson 2 API với Jackson 3 | Lỗi compile/runtime và dependency mismatch | Chọn API đúng phiên bản |
| Column JSON quá ngắn | Dữ liệu bị cắt hoặc save thất bại | Điều chỉnh schema và test kích thước |
| Ghi JSON thủ công vào DB | Type metadata không đúng contract | Dùng repository/mapper hoặc migration có kiểm thử |

## 23. Checklist triển khai production

- [ ] Đã xác định đúng phiên bản Spring Authorization Server, Spring Security và Jackson.
- [ ] Đã chọn Jackson 2 hoặc Jackson 3 nhất quán.
- [ ] ObjectMapper/JsonMapper persistence được cấu hình một lần.
- [ ] Có module Spring Security phù hợp với classpath.
- [ ] Có module Spring Authorization Server phù hợp phiên bản.
- [ ] RegisteredClient RowMapper và ParametersMapper dùng cùng mapper.
- [ ] OAuth2Authorization RowMapper và ParametersMapper dùng cùng mapper.
- [ ] RegisteredClientRepository được inject vào OAuth2AuthorizationService.
- [ ] Mapper persistence không được dùng để đọc HTTP input không tin cậy.
- [ ] Database write permissions được giới hạn.
- [ ] Custom types được allowlist và có schema/version.
- [ ] Không dùng permissive default typing trên mapper dùng chung.
- [ ] Có round-trip tests cho RegisteredClient và OAuth2Authorization.
- [ ] Có test sau restart và test dữ liệu JSON cũ.
- [ ] Có test âm cho type ID không hợp lệ.
- [ ] Column length đủ chứa settings/attributes/metadata.
- [ ] Log/metrics không làm lộ token, secret hoặc PII.
- [ ] Có runbook cho deserialize failure và version migration.

### Kiến thức cốt lõi

JDBC persistence của Spring Authorization Server dùng Jackson để chuyển các settings, attributes và token metadata thành JSON và khôi phục chúng khi đọc database. Với stack Jackson 2, cấu hình thường cần cả SecurityJackson2Modules và OAuth2AuthorizationServerJackson2Module. Cả JdbcRegisteredClientRepository lẫn JdbcOAuth2AuthorizationService có mapper cho chiều ghi và chiều đọc; nếu thay mapper, hãy cấu hình đủ cả hai chiều bằng cùng một ObjectMapper.

Các module Spring cung cấp mixin và type metadata để khôi phục những kiểu polymorphic cần thiết. Cơ chế này cũng làm deserialization trở thành ranh giới bảo mật: chỉ dùng mapper persistence cho dữ liệu database được kiểm soát, giới hạn quyền ghi, không dùng nó cho JSON từ client và không bật permissive default typing toàn ứng dụng. Khi lưu custom attributes, ưu tiên kiểu nhỏ, ổn định và có version.

Spring Security 7 chuyển sang Jackson 3 với SecurityJacksonModules, OAuth2AuthorizationServerJacksonModule và các JsonMapper JDBC mappers. Cần chọn API theo dependency thực tế, không trộn Jackson 2 và Jackson 3.

## Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html)
- [Spring Authorization Server 1.5.8 — JdbcRegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/JdbcRegisteredClientRepository.html)
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerJackson2Module API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson2/OAuth2AuthorizationServerJackson2Module.html)
- [Spring Security 6.5 — Jackson Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/jackson.html)
- [Spring Security 6.5 — SecurityJackson2Modules API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/jackson2/SecurityJackson2Modules.html)
- [Spring Security 7.1 — Jackson Support and PolymorphicTypeValidator](https://docs.spring.io/spring-security/reference/features/integrations/jackson.html)
- [Spring Security 7.1 — SecurityJacksonModules API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/jackson/SecurityJacksonModules.html)
- [Spring Security 7.1 — OAuth2AuthorizationServerJacksonModule API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson/OAuth2AuthorizationServerJacksonModule.html)
