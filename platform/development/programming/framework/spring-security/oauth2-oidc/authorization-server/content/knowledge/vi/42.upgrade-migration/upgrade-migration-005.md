# Chuyển schema, dữ liệu client, consent và authorization

> **Chương: Nâng cấp và chuyển đổi.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bao quát thiết kế và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Authorization Server. Trọng tâm là nâng cấp phiên bản ứng dụng hoặc database mà vẫn bảo toàn cấu hình client, quyết định consent, authorization transaction và trạng thái token. Một migration đúng phải giữ nguyên ý nghĩa bảo mật của dữ liệu, không chỉ làm cho các câu lệnh SQL chạy thành công.

Authorization Server lưu nhiều loại trạng thái có quan hệ với nhau. Client được tham chiếu bởi authorization và consent; authorization chứa token cùng metadata phục vụ refresh, revoke và introspection. Nếu chuyển từng bảng độc lập, thay đổi ID, diễn giải sai dữ liệu serialized hoặc bỏ sót token còn hiệu lực, hệ thống có thể phát hành token sai, làm mất khả năng thu hồi hoặc mở rộng quyền đã được cấp.

## 1. Mục tiêu và phạm vi migration

Migration trong Authorization Server thường gồm hai công việc khác nhau:

- **Schema migration:** thay đổi cấu trúc database như bảng, cột, kiểu dữ liệu, index, constraint và quyền truy cập.
- **Data migration:** chuyển đổi bản ghi hiện có sang cấu trúc hoặc mô hình dữ liệu mới, đồng thời bảo toàn quan hệ và trạng thái nghiệp vụ.

Hai công việc thường liên quan nhưng không thể thay thế nhau. Thêm cột mới không tự chuyển dữ liệu cũ sang ý nghĩa mới. Ngược lại, copy dữ liệu sang database mới không đảm bảo schema đích tương thích với JDBC mapper của phiên bản Spring Authorization Server đang chạy.

Các nhóm dữ liệu chính trong bài:

| Nhóm dữ liệu | Service/repository | Ví dụ |
|---|---|---|
| Client registry | RegisteredClientRepository | client_id, secret đã mã hóa, redirect URI, grant type, scope, client settings, token settings |
| Authorization | OAuth2AuthorizationService | principal, authorization code, access token, refresh token, ID token, device/user code và metadata tùy flow |
| Consent | OAuth2AuthorizationConsentService | principal, registered client và các authority/scope đã được chấp thuận |

Mục tiêu sau migration:

1. Mỗi client vẫn giữ đúng danh tính, credential và policy đã được phê duyệt.
2. Mỗi authorization còn được giữ lại có thể được đọc và xử lý theo đúng trạng thái trước migration.
3. Consent không bị mất, nhân đôi hoặc vô tình cấp thêm scope.
4. Quan hệ giữa authorization/consent và registered client vẫn hợp lệ.
5. Mọi instance mới dùng cùng schema và cùng nguồn dữ liệu.
6. Có thể chứng minh migration bằng số lượng, checksum, kiểm tra quan hệ và kiểm thử protocol.
7. Có phương án rollback thực tế nếu cutover thất bại.

## 2. Hiểu mô hình dữ liệu trước khi thay đổi

Spring Authorization Server cung cấp ba abstraction persistence thường được dùng:

- **RegisteredClientRepository:** tìm và lưu client đã đăng ký.
- **OAuth2AuthorizationService:** tìm, lưu và xóa authorization cùng token state.
- **OAuth2AuthorizationConsentService:** tìm, lưu và xóa consent của principal đối với client.

Các JDBC implementation mặc định thường sử dụng những bảng:

| Bảng | Vai trò | Quan hệ cần bảo toàn |
|---|---|---|
| oauth2_registered_client | Cấu hình OAuth client | Khóa nội bộ của client được tham chiếu từ authorization và consent |
| oauth2_authorization | Authorization transaction và token state | Phải tham chiếu đúng registered client; giữ principal, token và metadata |
| oauth2_authorization_consent | Quyết định consent | Gắn với registered client và principal |

Tên bảng và các cột chi tiết phải được đối chiếu với schema resource trong đúng artifact/version đang dùng. Không coi tên bảng hoặc cấu trúc của một phiên bản là hợp đồng bất biến cho mọi phiên bản.

### 2.1. Registered client

Một bản ghi RegisteredClient có thể chứa:

- ID nội bộ của bản ghi và client_id dùng trong OAuth protocol.
- Client secret đã được mã hóa nếu client dùng shared secret.
- Client authentication methods và authorization grant types.
- Redirect URI, post-logout redirect URI và scope.
- Client settings, ví dụ yêu cầu PKCE hoặc consent.
- Token settings, ví dụ thời hạn token và chính sách refresh token rotation.

ID nội bộ của client thường được các bản ghi authorization và consent tham chiếu. Khi chuyển dữ liệu, hãy giữ nguyên ID nếu có thể. Nếu bắt buộc ánh xạ sang ID mới, phải tạo bảng mapping ổn định và dùng mapping đó cho tất cả bản ghi phụ thuộc.

Không tạo lại client secret chỉ vì chuyển database. Secret đã mã hóa thường không thể giải mã ngược để lấy lại giá trị gốc. Nếu giữ nguyên hash và PasswordEncoder mới vẫn xác minh được hash cũ, client tiếp tục dùng secret hiện tại. Nếu thuật toán hoặc định dạng hash cũ không còn được hỗ trợ, hãy lập kế hoạch rotate secret qua quy trình quản trị.

### 2.2. Authorization và token state

OAuth2Authorization có thể lưu:

- ID authorization, registered client ID và principal name.
- Grant type và các scope đã được authorize.
- Attributes cần thiết để tiếp tục hoặc kiểm tra flow.
- Authorization code, access token, refresh token, ID token, user code hoặc device code tùy grant.
- Thời điểm phát hành, hết hạn, loại token, scope và metadata.
- Trạng thái token như invalidated hoặc các dấu hiệu đã được tiêu thụ.

Không phải mọi authorization đều có tất cả các token trên. Schema và dữ liệu cụ thể phụ thuộc flow và phiên bản. Cần bảo toàn những giá trị mà phiên bản đích cần để xử lý đúng token còn hiệu lực.

Token value và metadata có thể là dữ liệu nhạy cảm. Quyền truy cập database, backup, staging export và file trung gian phải được bảo vệ như secret. Không ghi token hoặc authorization code ra log để đối chiếu.

### 2.3. Consent

Consent thường gắn với cặp registered client và principal. Dữ liệu authorities biểu diễn các quyền mà người dùng đã chấp thuận. Khi chuyển consent:

- Giữ đúng principal name và quy tắc phân biệt hoa/thường.
- Giữ đúng registered client identity.
- Giữ đúng tập authority đã được chấp thuận.
- Không tự thêm scope vì phiên bản mới hỗ trợ scope mới.
- Không biến consent bị thu hồi hoặc đã xóa thành consent đang hoạt động.

Consent không đồng nghĩa với một authorization/token cụ thể. Xóa token không tự động rút consent; xóa consent cũng không bảo đảm JWT đã phát hành bị vô hiệu tức thì. Migration cần bảo toàn hai loại trạng thái riêng biệt.

## 3. Xác định nguồn, đích và bất biến dữ liệu

Trước khi viết migration, lập inventory cho cả database nguồn và đích:

| Nội dung cần xác định | Câu hỏi |
|---|---|
| Phiên bản ứng dụng | Spring Authorization Server và Spring Security hiện tại là phiên bản nào? |
| Phiên bản đích | Dependency đích và schema resource tương ứng là gì? |
| Database engine | PostgreSQL, MySQL, Oracle, SQL Server hay engine khác? |
| Schema | Có custom schema, column, index, trigger hoặc naming convention nào? |
| Client | Có bao nhiêu client, bao nhiêu confidential/public client, credential dùng encoder nào? |
| Authorization | Bao nhiêu bản ghi còn active, expired, invalidated hoặc đang trong flow? |
| Consent | Principal name và authority được chuẩn hóa ra sao? |
| Token | Có opaque token, JWT, refresh token, device flow hay token custom không? |
| Tích hợp | Có resource server, introspection, admin console hoặc job đọc trực tiếp bảng không? |
| Khả năng dừng dịch vụ | Có thể maintenance window hay cần cutover gần như không gián đoạn? |

Định nghĩa bất biến trước khi chuyển:

- client_id không bị trùng và không đổi ngoài kế hoạch đã duyệt.
- Client secret sau migration vẫn được xác minh bởi PasswordEncoder.
- Redirect URI, grant type, authentication method và scope không bị mở rộng ngoài ý muốn.
- Mỗi authorization còn giữ lại tham chiếu đúng client và principal.
- Token value, thời hạn, scope và trạng thái được bảo toàn nếu token tiếp tục được chấp nhận.
- Consent authority không tăng ngoài tập đã được người dùng chấp thuận.
- Không có authorization hoặc consent mồ côi sau migration.

Đặt các bất biến này thành tiêu chí nghiệm thu. Không chỉ dựa vào việc số hàng trong bảng đích bằng số hàng nguồn.

## 4. Chọn chiến lược migration

Chọn chiến lược dựa trên mức độ thay đổi schema, lượng dữ liệu và thời gian dừng dịch vụ.

| Chiến lược | Khi phù hợp | Ưu điểm | Rủi ro/chú ý |
|---|---|---|---|
| In-place schema migration | Database giữ nguyên, schema thay đổi nhỏ và tương thích | Ít phải sao chép dữ liệu | Rollback DDL có thể khó; cần backup và migration tương thích |
| Offline export/import | Có maintenance window và dữ liệu vừa phải | Dễ kiểm soát snapshot và xác minh | Dịch vụ phải dừng ghi trong thời gian chuyển |
| Shadow database + backfill | Database đích mới hoặc dữ liệu lớn | Có thể chuẩn bị và kiểm tra trước cutover | Cần theo kịp thay đổi phát sinh trong lúc backfill |
| Replication/CDC | Yêu cầu downtime thấp và có hạ tầng hỗ trợ | Đồng bộ delta liên tục | Phức tạp về ordering, delete, transaction và schema mapping |
| Application-level migration | Cần chuyển đổi format/model phức tạp | Dùng domain model và serializer đúng phiên bản | Cần utility riêng, kiểm soát tương thích và hiệu năng |

Đối với Authorization Server, offline migration có maintenance window thường dễ chứng minh tính đúng đắn nhất. Nếu cần online migration, hãy dùng quy trình backfill và đồng bộ delta được thiết kế rõ ràng. Không triển khai dual-write tùy tiện ở hai database: một lần ghi thành công ở nguồn nhưng thất bại ở đích sẽ tạo hai trạng thái khác nhau.

~~~mermaid
flowchart TD
    A[Inventory source and target] --> B[Choose migration strategy]
    B --> C[Backup and rehearse]
    C --> D[Prepare target schema]
    D --> E[Copy or transform client records]
    E --> F[Copy authorization and consent]
    F --> G[Validate counts, relations and security invariants]
    G --> H{Validation passes?}
    H -->|No| I[Stop cutover and reconcile]
    I --> E
    H -->|Yes| J[Freeze writes and apply final delta]
    J --> K[Switch application to target]
    K --> L[Run protocol smoke tests]
    L --> M{Smoke tests pass?}
    M -->|No| N[Rollback using runbook]
    M -->|Yes| O[Monitor and close migration]
~~~

## 5. Schema migration với Flyway hoặc Liquibase

Spring Authorization Server cung cấp schema SQL mẫu trong artifact tương ứng với phiên bản dependency. Các resource thường có tên:

- oauth2-registered-client-schema.sql
- oauth2-authorization-schema.sql
- oauth2-authorization-consent-schema.sql

Hãy lấy schema từ đúng phiên bản đích đang triển khai, so sánh với schema hiện tại và chuyển thay đổi thành migration có version. Không chỉnh sửa trực tiếp resource trong thư viện dependency và không giả định schema mới chỉ là schema cũ cộng thêm một vài cột.

### 5.1. Quy trình tạo migration

1. Ghi nhận schema hiện tại bằng migration history hoặc schema diff.
2. Lấy schema mẫu từ đúng artifact đích.
3. So sánh bảng, cột, kiểu dữ liệu, độ dài, nullability, index và constraint.
4. Xác định thay đổi nào là DDL và thay đổi nào cần chuyển đổi dữ liệu.
5. Viết migration có version, review và chạy trên bản sao database.
6. Đo thời gian chạy, lock, dung lượng tạm và tác động tới replication.
7. Kiểm tra ứng dụng cũ và mới có thể cùng hoạt động trong giai đoạn rolling deploy hay không.

### 5.2. Expand-migrate-contract

Với hệ thống cần rolling deployment, dùng chiến lược ba pha:

**Expand:** thêm bảng/cột/index mới theo cách tương thích ngược. Code cũ vẫn chạy được trên schema đã mở rộng.

**Migrate:** backfill dữ liệu và triển khai code mới có thể đọc cấu trúc mới. Nếu cần chuyển đổi dần, xác định rõ nguồn dữ liệu có thẩm quyền trong từng giai đoạn.

**Contract:** chỉ xóa cột/bảng cũ sau khi không còn node hoặc job nào sử dụng chúng, dữ liệu đã được xác minh và rollback window đã kết thúc.

Không xóa cột ngay trong cùng lần deploy khi phiên bản cũ còn chạy. Điều đó có thể làm node cũ lỗi giữa rolling deployment.

### 5.3. Kiểu dữ liệu và index

Đặc biệt chú ý:

- Cột lưu attributes, metadata, settings hoặc token value có thể cần độ dài lớn.
- Một số database phân biệt kiểu text, CLOB, JSON và giới hạn index trên cột dài.
- Kiểu timestamp/time zone cần thống nhất cách diễn giải và precision.
- Unique constraint trên client_id và khóa consent cần phù hợp với collation/case sensitivity.
- Index phục vụ lookup token và client phải được giữ hoặc tạo theo schema resource.
- Không đổi charset/collation theo cách làm hai client_id khác nhau trở thành một giá trị giống nhau.

Schema custom cần được kiểm tra bằng đúng database engine production. H2 hoặc một database khác dialect không đủ để chứng minh DDL sẽ chạy giống production.

## 6. Migration dữ liệu RegisteredClient

Registered client thường là nhóm dữ liệu cần được chuyển trước vì authorization và consent tham chiếu tới nó.

### 6.1. Giữ danh tính client

Ưu tiên bảo toàn:

- Internal ID.
- client_id.
- Client name.
- Encoded client secret.
- Authentication method và grant type.
- Redirect URI, post-logout redirect URI và scope.
- Client settings và token settings.

Nếu ID nội bộ phải đổi, tạo mapping đầy đủ:

| Source client ID | Target client ID | client_id |
|---|---|---|
| old-client-001 | new-client-001 | web-portal |
| old-client-002 | new-client-002 | orders-service |

Mapping phải được lưu bền vững trong migration workspace hoặc staging table có kiểm soát, không chỉ nằm trong memory của script. Dùng mapping này khi chuyển authorization và consent.

### 6.2. Bảo toàn client secret

Client secret được lưu dưới dạng encoded value. Cần:

1. Xác định PasswordEncoder và format hash ở nguồn.
2. Copy nguyên encoded value nếu phiên bản đích vẫn xác minh được.
3. Chạy kiểm tra với bộ test credential được kiểm soát bằng PasswordEncoder.matches.
4. Không ghi raw secret hoặc encoded secret ra log.
5. Nếu encoder cũ không còn được hỗ trợ, lập kế hoạch rotate secret và phối hợp với chủ sở hữu client.

Hash mật khẩu/client secret là một chiều. Không thể lấy lại raw secret để mã hóa lại bằng encoder mới. Việc đổi encoder không thể hoàn tất chỉ bằng một câu lệnh SQL.

Nếu dùng DelegatingPasswordEncoder, kiểm tra prefix và encoder ID của hash. Không xóa prefix hoặc thay chuỗi hash theo suy đoán.

### 6.3. Settings và redirect URI

Client settings và token settings có thể được lưu dưới dạng JSON/serialized representation. Hãy dùng serializer/mapper tương ứng với phiên bản nguồn và đích khi format thay đổi. Không dùng replace chuỗi JSON hàng loạt nếu chưa xác định cấu trúc và ý nghĩa của từng thuộc tính.

Kiểm tra chính xác tập redirect URI. Một URI bị thiếu có thể làm login callback thất bại; một URI mới được thêm ngoài kế hoạch có thể mở rộng bề mặt redirect. Không tự chuẩn hóa scheme, host, path hoặc dấu slash trong lúc migration nếu chưa có quy tắc đã được duyệt.

### 6.4. Client registry validation

Sau khi chuyển:

- Số lượng client theo loại public/confidential phải khớp với inventory.
- client_id không trùng.
- Tất cả grant type và authentication method nằm trong tập đã duyệt.
- Redirect URI và scope khớp với snapshot nguồn.
- Mọi encoded secret có thể được encoder đích xác minh bằng test credential được kiểm soát.
- Không có client ngoài inventory hoặc client bị tạo lặp.

## 7. Migration dữ liệu OAuth2Authorization

Đây thường là phần rủi ro nhất vì chứa trạng thái protocol và token.

### 7.1. Giữ quan hệ và trạng thái

Với mỗi authorization được chuyển, kiểm tra:

- Authorization ID.
- Registered client ID sau khi áp dụng mapping.
- Principal name và grant type.
- Authorized scopes.
- Attributes và metadata.
- Token values, issued-at, expires-at, type, scopes và trạng thái invalidated.

Nếu chuyển qua database khác, không chỉ copy bảng authorization trước rồi mới xử lý client. Target phải có client mà authorization tham chiếu. Có thể dùng thứ tự client trước, authorization sau, consent cuối hoặc theo constraint thực tế của schema.

### 7.2. Serialized attributes và metadata

Attributes có thể chứa dữ liệu được serialize theo các class của Spring Security hoặc Spring Authorization Server. Nâng cấp dependency có thể làm thay đổi class, type alias hoặc cách serialize.

- Xác định format thật của dữ liệu nguồn.
- Đọc bằng phiên bản/serializer tương thích với nguồn.
- Chuyển sang representation đích qua mapping rõ ràng.
- Giữ lại các field không hiểu nếu schema và ứng dụng đích yêu cầu chúng; không tự xóa để làm migration chạy qua.
- Không deserialize dữ liệu không tin cậy bằng cơ chế Java native serialization tùy tiện.
- Thử nghiệm với dữ liệu đại diện cho tất cả grant/token type đang dùng.

Nếu không thể chuyển an toàn một loại authorization attribute, hãy quyết định rõ có giữ nguyên bằng adapter tương thích hay chủ động vô hiệu hóa các authorization liên quan. Không lặng lẽ bỏ field rồi tiếp tục phát hành token.

### 7.3. Xử lý token còn hiệu lực

Phân loại authorization trước migration:

| Trạng thái | Hướng xử lý thường dùng |
|---|---|
| Authorization/token đã hết hạn | Có thể bỏ qua hoặc giữ theo retention/audit policy |
| Authorization/token đã invalidated hoặc revoked | Giữ trạng thái thu hồi nếu cần audit; không khôi phục thành active |
| Authorization code còn hiệu lực | Chỉ chuyển nếu giữ được đầy đủ metadata, trạng thái one-time và thời hạn; nếu không, để flow hoàn tất trước maintenance hoặc buộc client bắt đầu lại |
| Access token còn hiệu lực | Giữ nguyên token value và metadata nếu muốn tiếp tục chấp nhận token |
| Refresh token còn hiệu lực | Giữ nguyên trạng thái rotation/replay và liên kết authorization; kiểm thử refresh sau cutover |
| Device/user code đang chờ | Chuyển đầy đủ state/expiry nếu hỗ trợ; nếu không, hết hiệu lực có kiểm soát và yêu cầu client khởi tạo flow mới |

Không phát hành token mới chỉ để thay thế giá trị trong bảng mà không cập nhật client/resource server. Không đổi token value, token hash hoặc metadata theo cách làm token cũ không thể tra cứu.

Với JWT access token, resource server có thể tiếp tục xác minh chữ ký độc lập với database cho đến khi token hết hạn. Nếu migration thay issuer hoặc signing key, phải có kế hoạch xác minh token cũ, công bố JWK cũ trong giai đoạn chuyển tiếp hoặc chấp nhận thu hồi/đăng nhập lại theo chính sách đã công bố.

Với opaque token, việc tra cứu thường phụ thuộc authorization store. Nếu bản ghi/token value không được chuyển đúng, resource server có thể nhận kết quả inactive sau cutover.

### 7.4. Quyết định giữ hay loại bỏ authorization cũ

Không nhất thiết mọi authorization lịch sử đều phải chuyển. Có thể loại bỏ bản ghi đã hết hạn theo retention policy nếu không còn cần cho audit hoặc vận hành. Nhưng quyết định phải được đưa ra trước migration:

- Xác định ngưỡng thời gian và trạng thái được giữ.
- Giữ lại audit evidence theo yêu cầu.
- Không xóa token còn active chỉ để giảm dung lượng.
- Không biến bản ghi revoked thành active.
- Ghi số lượng và lý do của bản ghi bị loại bỏ.

Nếu chọn không chuyển authorization còn hiệu lực, phải thông báo trước tác động: phiên hoặc token hiện tại có thể cần đăng nhập/ủy quyền lại. Đây là quyết định sản phẩm và bảo mật, không phải side effect ngầm của ETL.

## 8. Migration OAuth2AuthorizationConsent

Consent thường ít hơn authorization nhưng có ảnh hưởng trực tiếp tới quyền mà người dùng đã chấp thuận.

### 8.1. Ánh xạ client và principal

Mỗi consent cần ánh xạ:

- registered_client_id sang client ID nội bộ đích.
- principal_name theo cùng quy tắc nhận diện người dùng.
- authorities giữ nguyên tập quyền đã chấp thuận.

Nếu hệ thống đổi user ID, tenant ID hoặc canonicalization, phải có mapping chính thức. Không tự lowercase principal name nếu identity store phân biệt chữ hoa/thường hoặc có nhiều tenant.

### 8.2. Không mở rộng consent

Khi phiên bản mới bổ sung scope, không tự thêm scope đó vào consent cũ. Người dùng phải được hỏi lại hoặc consent phải được cập nhật theo chính sách được phê duyệt.

Một phép kiểm tra hữu ích là so sánh tập authority trước và sau:

- Không mất authority ngoài các thay đổi được duyệt.
- Không có authority mới xuất hiện nếu chưa có consent hợp lệ.
- Mỗi consent trỏ tới client tồn tại.
- Không có bản ghi trùng cặp client/principal.

### 8.3. Consent và token đã cấp

Nếu consent bị rút hoặc thay đổi trong migration, xác định riêng cách xử lý các authorization đã phát hành từ consent đó. Có thể cần revoke refresh token, đánh dấu authorization invalidated hoặc yêu cầu introspection theo policy. Chỉ xóa hàng consent không tự động thực hiện những hành động này.

## 9. Dùng service API hay SQL/ETL trực tiếp?

Không có một cách duy nhất phù hợp cho mọi migration.

| Cách làm | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| Versioned SQL migration | Schema và format dữ liệu tương thích, thay đổi chủ yếu là DDL/SQL | Vendor dialect, transaction, locking và dữ liệu serialized |
| ETL theo bảng | Chuyển database hoặc cần mapping quan hệ rõ ràng | Mapping ID, thứ tự bảng, batch, retry và reconciliation |
| Application-level migration | Cần chuyển đổi domain model/serialized attributes | Serializer hai phiên bản, API service và token semantics |
| Export/import qua neutral format | Source và target khác phiên bản lớn | Định nghĩa format trung gian, version, encoding và kiểm tra đầy đủ field |

Các interface RegisteredClientRepository, OAuth2AuthorizationService và OAuth2AuthorizationConsentService là abstraction runtime hữu ích, nhưng không tự tạo ra một migration protocol tương thích giữa mọi phiên bản. Nếu dùng service API để import, hãy bảo đảm đối tượng được tạo bằng model/serializer đúng phiên bản đích và test đầy đủ trước khi chạy production.

Với ETL trực tiếp, tránh INSERT SELECT * giữa hai schema khác version. Luôn liệt kê cột tường minh và ánh xạ từng field. Với dữ liệu serialized, cần hiểu representation trước khi chuyển; không sửa blob/JSON bằng thao tác chuỗi mù.

### 9.1. Quy trình ETL theo batch

Một migration job có thể triển khai theo chu kỳ:

~~~text
1. Đọc một batch có thứ tự ổn định từ nguồn.
2. Kiểm tra bản ghi và quan hệ cần thiết.
3. Áp dụng mapping client/principal/field.
4. Ghi vào staging hoặc bảng đích trong transaction ngắn.
5. Ghi checkpoint và số lượng đã xử lý.
6. Commit rồi chuyển sang batch kế tiếp.
7. Khi retry, nhận diện bản ghi đã import để không tạo duplicate.
~~~

Chọn batch size theo latency, transaction log, lock và khả năng phục hồi. Không giữ một transaction duy nhất cho toàn bộ hàng triệu bản ghi nếu database không được thiết kế cho việc đó.

Migration job phải idempotent hoặc có cơ chế resume rõ ràng. Dùng source primary key và migration version để nhận diện bản ghi đã xử lý. Không chỉ dựa vào số hàng đã chạy vì một batch có thể commit thành công nhưng job mất kết nối trước khi ghi checkpoint.

## 10. Kế hoạch cutover có downtime

Đây là cách dễ kiểm soát nhất khi có thể dành maintenance window.

### 10.1. Trước maintenance

1. Inventory client, authorization, consent và token state.
2. Tạo backup nhất quán và kiểm thử restore trên môi trường riêng.
3. Chuẩn bị schema đích bằng migration versioned.
4. Chạy thử toàn bộ data migration trên snapshot gần với production.
5. Ghi thời gian thực hiện, dung lượng, số lượng bản ghi và kết quả validation.
6. Chuẩn bị endpoint/maintenance page và thông báo cho các client owner.
7. Chuẩn bị runbook rollback với người chịu trách nhiệm và điều kiện kích hoạt.

### 10.2. Trong maintenance

1. Ngừng nhận authorization request/token request mới hoặc chuyển traffic sang maintenance response.
2. Dừng các job quản trị, client provisioning và background writer.
3. Chờ request đang xử lý kết thúc trong giới hạn đã định.
4. Tạo snapshot cuối cùng hoặc backup nhất quán.
5. Chạy schema migration và data migration.
6. Chạy reconciliation và kiểm tra quan hệ.
7. Chuyển cấu hình ứng dụng sang database đích.
8. Chạy smoke test trước khi mở traffic.

### 10.3. Sau cutover

- Mở traffic theo từng bước nếu nền tảng hỗ trợ.
- Theo dõi lỗi login, invalid_client, invalid_grant, invalid_scope và introspection.
- Kiểm tra refresh token và consent bằng client test.
- Theo dõi database pool, slow query và replication.
- Giữ backup nguồn và log migration theo retention policy.
- Chỉ kết thúc rollback window sau khi owner chấp nhận số liệu vận hành.

## 11. Online migration và cutover downtime thấp

Online migration phù hợp khi không thể dừng ghi trong thời gian dài, nhưng phức tạp hơn đáng kể.

Một quy trình thường gồm:

1. Tạo schema đích tương thích với phiên bản ứng dụng mới.
2. Chụp snapshot nhất quán ở thời điểm T0.
3. Backfill dữ liệu từ snapshot sang đích.
4. Đồng bộ thay đổi sau T0 bằng CDC, transaction log hoặc cơ chế outbox được thiết kế riêng.
5. So sánh số lượng và trạng thái nguồn/đích liên tục.
6. Chuẩn bị ứng dụng có thể đọc dữ liệu đích trong môi trường staging.
7. Đến thời điểm cutover, khóa writer ở nguồn trong thời gian ngắn.
8. Áp dụng delta cuối, xác nhận watermark và reconciliation.
9. Chuyển traffic sang đích.
10. Theo dõi và chỉ cho phép ghi ở một nơi có thẩm quyền.

### 11.1. Ordering và delete

CDC phải bảo toàn thứ tự cần thiết. Ví dụ, client được tạo trước authorization tham chiếu client đó. Nếu sự kiện delete đến trước sự kiện insert do partition/order không phù hợp, dữ liệu đích có thể sai.

Phải xử lý cả:

- Insert, update và delete.
- Thay đổi client ID mapping.
- Revoke/invalidated token state.
- Consent removal.
- Retry và duplicate event.
- Transaction nhiều bảng.

### 11.2. Không dual-write thiếu kiểm soát

Nếu ứng dụng ghi đồng thời vào database nguồn và đích mà không có transaction phân tán hoặc outbox, có thể xảy ra:

- Nguồn commit, đích thất bại.
- Đích commit, nguồn timeout nhưng thực tế đã commit.
- Hai nơi xử lý cùng request theo thứ tự khác nhau.
- Revoke ở một nơi nhưng refresh ở nơi kia vẫn thành công.

Chỉ dùng dual-write khi có cơ chế idempotency, reconciliation, retry và xác định nguồn có thẩm quyền. Với dữ liệu token, sai lệch nhỏ cũng có thể ảnh hưởng tới quyền truy cập.

## 12. Validation và reconciliation

Validation cần nhiều lớp. Count bằng nhau chỉ là bước đầu.

### 12.1. So sánh số lượng

Ví dụ truy vấn tổng quan trên schema JDBC mặc định:

~~~sql
SELECT COUNT(*) FROM oauth2_registered_client;
SELECT COUNT(*) FROM oauth2_authorization;
SELECT COUNT(*) FROM oauth2_authorization_consent;
~~~

So sánh theo từng loại dữ liệu và trạng thái nếu schema cho phép. Nếu có lọc bỏ bản ghi hết hạn, ghi rõ điều kiện và số lượng bị loại.

### 12.2. Kiểm tra quan hệ

Kiểm tra authorization tham chiếu tới registered client tồn tại:

~~~sql
SELECT a.registered_client_id
FROM oauth2_authorization a
LEFT JOIN oauth2_registered_client c
    ON c.id = a.registered_client_id
WHERE c.id IS NULL;
~~~

Kiểm tra consent tham chiếu tới client tồn tại:

~~~sql
SELECT s.registered_client_id
FROM oauth2_authorization_consent s
LEFT JOIN oauth2_registered_client c
    ON c.id = s.registered_client_id
WHERE c.id IS NULL;
~~~

Tên cột cần đối chiếu với schema thực tế của phiên bản đang dùng. Kết quả mong đợi là không có bản ghi mồ côi, trừ khi migration có mapping/exception được ghi nhận rõ ràng.

### 12.3. Checksum và so sánh semantic

Với dữ liệu không nhạy cảm hoặc đã được bảo vệ, tạo checksum theo từng nhóm field ổn định:

- Client: client_id, redirect URI, grant type, scope và settings.
- Authorization: ID, client mapping, principal, grant type, token timestamps và trạng thái.
- Consent: client mapping, principal và tập authority.

Chuẩn hóa thứ tự tập hợp trước khi hash để tránh khác biệt do thứ tự lưu trữ. Không đưa raw secret/token vào báo cáo hoặc log checksum. Với giá trị nhạy cảm, có thể dùng HMAC key quản lý riêng để so sánh mà không lộ dữ liệu.

### 12.4. Protocol smoke test

Sau khi dữ liệu được chuyển:

1. Client confidential xác thực thành công bằng secret hiện tại.
2. Client public thực hiện authorization code + PKCE.
3. Authorization code chỉ đổi được một lần.
4. Consent hiện tại được áp dụng đúng.
5. Refresh token hoạt động theo chính sách rotation.
6. Token revoke được phản ánh qua introspection nếu flow sử dụng.
7. Resource server xác minh JWT phát hành trước và sau migration theo chính sách key/issuer.
8. Một instance tạo dữ liệu và instance khác đọc/tiếp tục xử lý được.

Không dùng production user credential hoặc token thật trong test. Tạo client/principal test có phạm vi và thời hạn rõ ràng.

## 13. Rollback và phục hồi

Rollback không đơn giản là chạy migration SQL ngược. Sau khi ứng dụng mới bắt đầu ghi dữ liệu, database nguồn có thể đã lỗi thời.

### 13.1. Trước cutover

Nếu validation thất bại trước khi mở traffic, dừng migration, giữ nguyên nguồn, xóa hoặc khôi phục database đích từ snapshot và sửa ETL. Không cần chuyển traffic nếu nguồn chưa bị thay đổi.

### 13.2. Sau cutover

Trước cutover phải quyết định cách rollback:

- **Rollback ứng dụng:** chỉ khả thi nếu schema/data mới vẫn tương thích với phiên bản cũ.
- **Rollback database:** cần snapshot hoặc backup trước cutover; các ghi mới sau cutover có thể bị mất nếu restore nguồn cũ.
- **Forward fix:** sửa lỗi trên database đích có thể an toàn hơn nếu đã phát sinh giao dịch mới.
- **Reverse replication:** chỉ khả thi nếu đã thiết kế chiều đồng bộ ngược và kiểm thử trước.

Nếu đã phát sinh authorization, token refresh, revoke hoặc consent update trên đích, không chuyển traffic về nguồn cũ mà không đồng bộ các thay đổi này. Đặc biệt, một refresh token đã bị rotate hoặc revoke trên đích không được trở lại trạng thái active do rollback.

Runbook phải nêu rõ ngưỡng kích hoạt rollback, người quyết định, nguồn dữ liệu có thẩm quyền và cách xử lý các token/consent phát sinh trong cửa sổ cutover.

## 14. Bảo mật và vận hành trong quá trình migration

- Dùng tài khoản database có quyền tối thiểu cho migration job.
- Bảo vệ backup, export file, staging table và temporary directory.
- Mã hóa dữ liệu khi truyền và khi lưu theo chính sách môi trường.
- Không log raw password, client secret, authorization code, access token, refresh token hoặc session cookie.
- Hạn chế quyền truy cập vào dữ liệu principal và consent.
- Không đưa production dump vào laptop hoặc CI artifact công khai.
- Xóa hoặc làm sạch file tạm theo retention policy sau khi nghiệm thu.
- Ghi audit ai chạy migration, phiên bản nào, snapshot nào và kết quả nào.
- Dùng migration lock hoặc cơ chế đảm bảo chỉ một job chạy migration tại một thời điểm.
- Theo dõi thời gian lock, replication lag, transaction log và dung lượng database.

Nếu cần sample dữ liệu để phát triển migration, ưu tiên dữ liệu tổng hợp hoặc đã được ẩn danh. Việc ẩn danh phải giữ đủ quan hệ để kiểm thử mapping và constraint.

## 15. Các tình huống thường gây lỗi

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client tồn tại nhưng xác thực secret thất bại | Encoded secret bị đổi, encoder prefix mất hoặc encoder đích không hỗ trợ hash cũ | So sánh encoded value an toàn, kiểm tra PasswordEncoder và lập kế hoạch rotation |
| Authorization không được tìm thấy sau migration | ID/token value bị đổi hoặc field lookup không được chuyển | Kiểm tra authorization ID, token value và mapper của phiên bản đích |
| Authorization trỏ tới client không tồn tại | Chuyển client thiếu hoặc mapping ID sai | Chuyển client trước, kiểm tra orphan và mapping table |
| Người dùng bị hỏi consent lại | Consent bị bỏ, principal name khác hoặc authority mapping sai | So sánh principal/client mapping và tập authorities |
| Scope được cấp rộng hơn trước | Migration tự thêm scope mới vào consent cũ | Khôi phục tập quyền đã chấp thuận và yêu cầu consent mới theo policy |
| Refresh token cũ hoạt động trở lại | Trạng thái invalidated/rotation bị mất hoặc rollback về snapshot cũ | Khóa traffic, xác minh token state và revoke credential bị ảnh hưởng |
| Opaque token trở thành inactive | Authorization/token row hoặc token value không được chuyển chính xác | Kiểm tra token lookup và metadata trong authorization store |
| JWT cũ không xác minh được | Issuer thay đổi hoặc public key cũ bị gỡ quá sớm | Duy trì JWK overlap hoặc thực hiện chính sách re-auth có kiểm soát |
| Migration chạy lặp tạo duplicate | Job không idempotent hoặc checkpoint không đáng tin | Dùng source key/version marker và unique constraint |
| Schema migration treo | Lock lớn, index build hoặc transaction quá dài | Chia batch, chọn chiến lược online index phù hợp database |
| Node cũ lỗi sau expand | Migration không tương thích ngược | Khôi phục schema tương thích hoặc rollout đồng bộ theo runbook |
| Count khớp nhưng flow thất bại | Dữ liệu serialized, quan hệ hoặc token metadata sai | Bổ sung semantic validation và protocol smoke test |

## 16. Ma trận kiểm thử migration

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Migrate confidential client với encoded secret | Client xác thực được bằng secret cũ |
| 2 | Migrate public client | Client ID, redirect URI, grant và PKCE policy giữ nguyên |
| 3 | Migrate client có nhiều redirect URI/scope | Tập giá trị đích khớp snapshot nguồn |
| 4 | Migrate client settings/token settings | Policy không bị nới lỏng ngoài kế hoạch |
| 5 | Migrate authorization code còn hiệu lực | Code chỉ được dùng một lần hoặc được chủ động hết hạn theo kế hoạch |
| 6 | Migrate access token active | Token được xử lý đúng theo format và issuer |
| 7 | Migrate refresh token đã rotate | Token cũ vẫn invalidated, token mới hoạt động |
| 8 | Migrate token đã revoke | Trạng thái revoked không bị khôi phục |
| 9 | Migrate consent của principal | Client, principal và authorities được bảo toàn |
| 10 | Principal name có khác biệt case/tenant | Mapping không gộp hai principal ngoài ý muốn |
| 11 | Authorization tham chiếu client không có mapping | Migration dừng hoặc đưa vào exception queue |
| 12 | ETL bị dừng giữa batch | Resume không duplicate và không bỏ sót |
| 13 | ETL chạy lại sau commit nhưng trước checkpoint | Bản ghi đã xử lý được nhận diện an toàn |
| 14 | Serialized attribute từ phiên bản cũ | Được đọc/convert hoặc từ chối có kiểm soát |
| 15 | Cutover sang database mới | Instance mới đọc được client, authorization và consent |
| 16 | Database đích không khả dụng | Authorization Server không cấp quyền bằng local fallback |
| 17 | Rollback sau khi có refresh/revoke mới | Không khôi phục token đã rotate/revoke thành active |
| 18 | JWT cũ trong thời gian chuyển key | Resource server xác minh theo chính sách overlap |
| 19 | Opaque token sau cutover | Introspection trả active/inactive đúng trạng thái |
| 20 | Rolling deployment với schema expand | Node cũ và mới cùng hoạt động trong giai đoạn cho phép |

### 16.1. Ví dụ validation query

Các truy vấn sau là ví dụ cho schema JDBC mặc định; cần điều chỉnh tên cột nếu tổ chức đã custom schema:

~~~sql
-- Client IDs phải duy nhất.
SELECT client_id, COUNT(*)
FROM oauth2_registered_client
GROUP BY client_id
HAVING COUNT(*) > 1;

-- Authorization phải tham chiếu tới client tồn tại.
SELECT COUNT(*)
FROM oauth2_authorization a
LEFT JOIN oauth2_registered_client c
    ON c.id = a.registered_client_id
WHERE c.id IS NULL;

-- Consent phải tham chiếu tới client tồn tại.
SELECT COUNT(*)
FROM oauth2_authorization_consent s
LEFT JOIN oauth2_registered_client c
    ON c.id = s.registered_client_id
WHERE c.id IS NULL;
~~~

Kết quả mong đợi là không có client_id trùng và không có authorization/consent mồ côi. Những truy vấn này chưa xác minh token metadata hoặc consent semantics; cần kết hợp kiểm tra ở service/API và protocol test.

## 17. Checklist production

- [ ] Đã xác định phiên bản Spring Authorization Server nguồn và đích.
- [ ] Đã lấy schema resource từ đúng artifact đích.
- [ ] Đã inventory client, authorization, consent, token và custom extension.
- [ ] Đã định nghĩa bất biến và tiêu chí nghiệm thu.
- [ ] Đã backup nhất quán và thử restore.
- [ ] Schema migration được version hóa và review.
- [ ] DDL đã được thử trên đúng database engine/version.
- [ ] Client ID và mapping ID được bảo toàn.
- [ ] Encoded client secret được giữ nguyên hoặc có kế hoạch rotation.
- [ ] Redirect URI, grant type, authentication method và scope được so sánh.
- [ ] Serialized settings, attributes và token metadata được xử lý có hiểu biết.
- [ ] Authorization code, access token, refresh token và revoke state được phân loại.
- [ ] Consent giữ nguyên principal và authority; không tự mở rộng scope.
- [ ] ETL có batch, checkpoint, retry và idempotency.
- [ ] Có kiểm tra orphan, duplicate, count và semantic checksum.
- [ ] Có protocol smoke test qua nhiều instance.
- [ ] Có kế hoạch issuer/signing key/JWK overlap nếu thay đổi.
- [ ] Có maintenance/cutover plan và runbook rollback.
- [ ] Không dual-write thiếu cơ chế reconciliation.
- [ ] Log và file tạm không làm lộ credential/token.
- [ ] Có người chịu trách nhiệm quyết định cutover và kết thúc rollback window.

## 18. Câu hỏi tự đánh giá

1. Schema migration khác data migration ở điểm nào?
2. Vì sao cần lấy schema resource từ đúng phiên bản Spring Authorization Server đích?
3. Vì sao phải chuyển RegisteredClient trước authorization và consent?
4. Tại sao nên giữ internal ID của RegisteredClient?
5. Có thể giải mã client secret đã hash để mã hóa lại bằng encoder mới không?
6. Khi nào cần rotate client secret thay vì copy encoded value?
7. Những loại token/metadata nào có thể nằm trong OAuth2Authorization?
8. Vì sao serialized attributes cần được xử lý bằng serializer tương thích?
9. Khi nào có thể loại bỏ authorization đã hết hạn?
10. Điều gì xảy ra nếu migration làm mất trạng thái refresh token đã invalidated?
11. Vì sao consent không được tự động mở rộng khi có scope mới?
12. Khi nào dùng SQL migration, ETL hoặc application-level migration?
13. Vì sao INSERT SELECT * nguy hiểm giữa hai schema khác phiên bản?
14. Online migration cần xử lý ordering, duplicate event và delete như thế nào?
15. Vì sao dual-write có thể làm lệch trạng thái revoke?
16. Count bằng nhau đã đủ chứng minh migration đúng chưa?
17. JWT và opaque token chịu ảnh hưởng khác nhau ra sao khi chuyển authorization store?
18. Vì sao rollback sau khi cutover cần đồng bộ refresh/revoke state?
19. Expand-migrate-contract giúp rolling deployment như thế nào?
20. Những smoke test nào cần chạy trước khi mở lại traffic?

## Tài liệu tham khảo

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): mô hình RegisteredClient, OAuth2Authorization, consent và các service/repository.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình và thành phần nền tảng của Authorization Server.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization, token, introspection và revocation endpoint.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cách cấu hình các thành phần Authorization Server.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, JdbcOperations và truy cập database.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundary và @Transactional.
- [Flyway Documentation](https://documentation.red-gate.com/flyway): versioned schema migration và migration history.
- [Liquibase Documentation](https://docs.liquibase.com/): quản lý changeset, schema và data migration.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và JWK Set.
