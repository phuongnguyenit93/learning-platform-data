# Khởi tạo schema và quản lý migration bằng Flyway hoặc Liquibase

## Mục tiêu bài học

Trong chương **Lưu trữ JDBC** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn khởi tạo và quản lý schema cho Spring Authorization Server bằng **Flyway** hoặc **Liquibase** trong ứng dụng **Spring Boot**.

Khi chuyển Authorization Server từ lưu trữ in-memory sang JDBC, việc tạo bảng chỉ là bước đầu. Schema phải khớp với phiên bản Spring Authorization Server đang chạy; migration phải có thứ tự, được ghi nhận và có thể triển khai lặp lại ở development, test, staging và production.

Spring Authorization Server cung cấp ba JDBC components thường dùng:

- **JdbcRegisteredClientRepository** lưu cấu hình các OAuth2/OIDC clients đã đăng ký.
- **JdbcOAuth2AuthorizationService** lưu authorization và các token/metadata gắn với authorization.
- **JdbcOAuth2AuthorizationConsentService** lưu quyết định consent của người dùng đối với client.

Ba component này phụ thuộc vào ba SQL schema resources do Spring cung cấp. Flyway hoặc Liquibase cần quản lý các DDL đó như migration thuộc source control của ứng dụng. Không nên để nhiều cơ chế cùng tự tạo và sửa một schema.

Sau bài học, bạn có thể:

1. Giải thích vai trò và quan hệ của ba bảng JDBC trong Spring Authorization Server.
2. Tìm đúng ba schema SQL resources trong dependency đang dùng.
3. Tạo versioned migrations với Flyway hoặc changelog/changeset với Liquibase.
4. Chọn thứ tự migration và cấu hình Spring Boot để migration hoàn thành trước khi repository được sử dụng.
5. Điều chỉnh schema theo PostgreSQL, MySQL hoặc hệ quản trị cơ sở dữ liệu mục tiêu.
6. Quản lý checksum, baseline, rollback, schema drift và nâng cấp Spring Authorization Server.
7. Kiểm thử migration trên database sạch và database đã có dữ liệu.
8. Triển khai migration production với quyền tối thiểu, backup, expand/contract và kế hoạch khôi phục.

> **Tình huống xuyên suốt:** nhóm triển khai Authorization Server cho auth.example.com. Môi trường local dùng database rỗng; staging có dữ liệu client và consent thử nghiệm; production đã lưu authorization code, access token và refresh token. Cùng một bộ migration phải tạo được schema mới và nâng cấp schema cũ mà không làm mất các phiên đăng nhập đang còn hiệu lực.

## 1. Vì sao cần quản lý schema bằng migration?

### 1.1. JDBC repository cần bảng có cấu trúc đúng

Các JDBC implementations của Spring Authorization Server không tự tạo bảng mỗi khi khởi động. Chúng thực hiện truy vấn và ghi dữ liệu theo schema mà framework định nghĩa.

| Component | Interface | Bảng chính | Nội dung |
|---|---|---|---|
| **JdbcRegisteredClientRepository** | RegisteredClientRepository | oauth2_registered_client | Client ID, secret, authentication methods, grant types, redirect URIs, scopes, client/token settings. |
| **JdbcOAuth2AuthorizationService** | OAuth2AuthorizationService | oauth2_authorization | Principal, grant type, authorized scopes, attributes, authorization code, access token, refresh token, ID Token, device/user code và metadata. |
| **JdbcOAuth2AuthorizationConsentService** | OAuth2AuthorizationConsentService | oauth2_authorization_consent | Client, principal và các authorities/scopes mà người dùng đã consent. |

Nếu repository truy vấn cột không tồn tại, kiểu dữ liệu không tương thích hoặc tên bảng sai, request OAuth2/OIDC sẽ lỗi ngay tại các luồng client authentication, authorization, token, introspection, revocation hoặc consent.

**Lưu ý:** ba bảng trên là phần persistence dành cho Spring Authorization Server. Chúng không thay thế bảng người dùng, mật khẩu, authorities, tenant, audit hay profile của ứng dụng. Nếu form login dùng JDBC user store, schema của Spring Security là một nhóm riêng và cần được quản lý theo cùng quy trình migration của hệ thống.

### 1.2. Không chỉ tạo bảng một lần

Schema thay đổi theo vòng đời sản phẩm:

- Nâng Spring Authorization Server có thể thay đổi SQL resource hoặc cách repository đọc/ghi.
- Ứng dụng cần thêm index, cột, constraint hoặc bảng audit.
- Database production có dữ liệu cần giữ nguyên.
- Nhiều môi trường phải có schema nhất quán.
- Một lần deploy có thể chạy nhiều application instances cùng lúc.
- Khi lỗi migration xảy ra, cần biết database đã ở trạng thái nào và có thể khôi phục ra sao.

Migration tool lưu lịch sử các thay đổi đã áp dụng. Nhờ đó, một database mới có thể được dựng từ đầu và một database đang chạy có thể được nâng cấp theo các bước đã được review.

### 1.3. Chọn một cơ chế quản lý schema

Spring Boot hỗ trợ SQL script initialization, Flyway và Liquibase. Với schema production, hãy chọn **một cơ chế chính** làm nguồn sự thật.

| Cơ chế | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Flyway | Nhóm muốn quản lý migration tuần tự bằng SQL hoặc Java, mỗi versioned migration chạy một lần. | Giữ migration đã áp dụng bất biến; kiểm checksum. |
| Liquibase | Nhóm muốn changelog có changeset, preconditions, contexts/labels và rollback metadata. | Định danh changeset gồm author, id và file path; giữ changelog ổn định. |
| schema.sql / data.sql | Demo hoặc ứng dụng nhỏ có nhu cầu initialization đơn giản. | Không có lịch sử migration phong phú; không nên chạy song song với Flyway/Liquibase. |
| Hibernate ddl-auto | Schema do JPA entity quản lý trong phạm vi phù hợp. | Không phải công cụ quản lý schema của ba JDBC repositories của Authorization Server. |

Không chạy Flyway và Liquibase cùng quản lý ba bảng này. Cũng không để schema.sql, Hibernate create/update và migration tool cùng sửa các bảng. Việc có nhiều schema owners khiến thứ tự chạy và trạng thái thật của database khó xác định.

## 2. Ba SQL schema resources của Spring Authorization Server

### 2.1. Đường dẫn trong dependency

Các SQL resources được đóng gói cùng Spring Authorization Server. Tên resource classpath là:

| Resource | Repository sử dụng |
|---|---|
| org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql | JdbcRegisteredClientRepository |
| org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql | JdbcOAuth2AuthorizationService |
| org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql | JdbcOAuth2AuthorizationConsentService |

Hãy lấy các resource từ **đúng version dependency đã resolve trong build**. Đừng sao chép schema từ một bài blog, nhánh main hoặc phiên bản Spring Authorization Server khác rồi giả định nó tương thích.

Có thể mở JAR dependency bằng IDE hoặc công cụ archive để xem các file dưới org/springframework/security/oauth2/server/authorization/. Đối với migration, đưa nội dung SQL đã chọn vào source tree của ứng dụng, review thay đổi và commit cùng mã nguồn.

Các resource trong JAR không tự động trở thành Flyway migrations chỉ vì chúng nằm trên classpath. Flyway mặc định tìm migration trong classpath:db/migration; Liquibase đọc changelog đã cấu hình. Cần đưa DDL vào vị trí và định dạng mà migration tool quản lý.

### 2.2. Bảng Registered Client

Bảng oauth2_registered_client lưu metadata của OAuth2/OIDC client. Các cột tiêu biểu:

- id: khóa nội bộ duy nhất của RegisteredClient.
- client_id: định danh client gửi trong protocol request.
- client_id_issued_at: thời điểm cấp client ID.
- client_secret, client_secret_expires_at: secret và thời hạn secret nếu client sử dụng secret.
- client_name: tên hiển thị.
- client_authentication_methods: các phương thức client authentication được phép.
- authorization_grant_types: các grant type được phép.
- redirect_uris, post_logout_redirect_uris: URI callback và logout đã đăng ký.
- scopes: các scope được cấp phép.
- client_settings, token_settings: cấu hình client và token được serialize.

Đây là dữ liệu cấu hình bảo mật. Không dùng client ID làm khóa chính thay cho id nếu schema/repository kỳ vọng hai giá trị riêng biệt. Không lưu client secret dạng plaintext; hãy tạo và lưu secret theo PasswordEncoder phù hợp với cấu hình của ứng dụng.

### 2.3. Bảng Authorization

Bảng oauth2_authorization lưu trạng thái của một authorization. Nó có thể chứa nhiều loại token tùy grant type:

- Authorization code.
- Access token và metadata.
- Refresh token và metadata.
- OIDC ID Token và claims/metadata.
- User code và device code.
- Principal name, registered client ID, grant type, authorized scopes và attributes.

Đây là bảng có payload lớn và nhạy cảm. Các cột token/metadata/attributes có thể chứa dữ liệu dài hoặc dữ liệu serialize; không tùy tiện thay LOB bằng VARCHAR nhỏ.

Một hàng authorization có thể còn refresh token hợp lệ ngay cả khi authorization code đã hết hạn. Không xóa hàng chỉ vì một token trong hàng đã hết hạn nếu các token khác còn cần được kiểm tra hoặc thu hồi.

### 2.4. Bảng Authorization Consent

Bảng oauth2_authorization_consent lưu quyết định consent theo cặp:

- registered_client_id: ID nội bộ của client đã đăng ký.
- principal_name: tên principal của End-User.
- authorities: tập authorities được cấp, thường gồm các scope.

Khóa chính thường là cặp registered_client_id và principal_name. Nếu ứng dụng đổi cách chuẩn hóa principal name hoặc subject mapping, phải đánh giá ảnh hưởng tới consent cũ; không tự đổi khóa theo email hoặc display name.

### 2.5. Thứ tự tạo bảng

Một thứ tự dễ hiểu là:

1. oauth2_registered_client
2. oauth2_authorization
3. oauth2_authorization_consent

Authorization và Consent đều tham chiếu client bằng registered_client_id ở cấp dữ liệu. Các SQL scripts chuẩn có thể không khai báo foreign key giữa những bảng này; thứ tự trên thể hiện quan hệ nghiệp vụ và giúp người đọc hiểu dependency. Nếu tự thêm foreign key hoặc ON DELETE CASCADE, hãy kiểm tra chính sách xóa client, retention của authorization và behavior của repository trước khi triển khai.

## 3. Chuẩn bị migration cho project

### 3.1. Cấu trúc thư mục

Ví dụ với Flyway:

~~~text
src/
  main/
    resources/
      db/
        migration/
          V001__create_oauth2_registered_client.sql
          V002__create_oauth2_authorization.sql
          V003__create_oauth2_authorization_consent.sql
~~~

Ví dụ với Liquibase:

~~~text
src/
  main/
    resources/
      db/
        changelog/
          db.changelog-master.yaml
          sql/
            oauth2-registered-client-schema.sql
            oauth2-authorization-schema.sql
            oauth2-authorization-consent-schema.sql
~~~

Chỉ chọn một trong hai cách tổ chức cho schema này. Đường dẫn và tên file là quy ước của project; migration tool sẽ chạy chúng theo cấu hình tương ứng.

### 3.2. Quy trình chuẩn bị SQL

Với mỗi schema resource:

1. Kiểm tra phiên bản dependency đang dùng.
2. Mở đúng SQL resource trong JAR.
3. So sánh với schema hiện tại của database mục tiêu.
4. Chọn dialect đúng cho database.
5. Đưa DDL vào file migration riêng.
6. Review tên bảng, cột, kiểu dữ liệu, độ dài, khóa và index.
7. Chạy trên database rỗng cùng loại với production.
8. Kiểm tra repository có thể đọc/ghi dữ liệu thực tế.
9. Commit migration; từ thời điểm đã áp dụng ở môi trường lâu dài, không sửa nội dung migration cũ.

Không copy một schema rồi thêm các thay đổi thủ công trực tiếp vào production. Mọi thay đổi cần có migration mới để các môi trường tái tạo được cùng trạng thái.

### 3.3. Schema theo database vendor

SQL resource mặc định không đảm bảo mọi kiểu dữ liệu đều dùng nguyên trạng trên mọi database. Đặc biệt, bảng authorization chứa các cột LOB và timestamp.

Trong schema hiện hành của Spring Security Authorization Server, phần ghi chú ở oauth2-authorization-schema.sql nêu rõ:

- Với **PostgreSQL**, đổi các cột khai báo blob sang text vì PostgreSQL không có kiểu blob tương ứng trong DDL đó.
- Với **PostgreSQL**, đổi các cột timestamp sang timestamptz để lưu các instant chính xác theo múi giờ.
- Với **MySQL Connector/J**, URL kết nối cần cấu hình preserveInstants=true, connectionTimeZone=UTC và forceConnectionTimeZoneToSession=true để xử lý instant đúng.

Hãy đối chiếu comment của resource trong **đúng phiên bản** đang chạy; nếu version đó có hướng dẫn khác, ưu tiên hướng dẫn đi kèm dependency. Không thay đổi kiểu dữ liệu theo phỏng đoán. Kiểm tra cả cách JDBC driver bind và đọc LOB sau khi migration.

Ví dụ URL MySQL minh họa:

~~~properties
spring.datasource.url=jdbc:mysql://db.example.com:3306/authdb?preserveInstants=true&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

Với PostgreSQL, migration phải dùng kiểu dữ liệu tương thích của PostgreSQL cho tất cả cột tương ứng. Hãy tạo bộ migration theo vendor hoặc dùng changelog có điều kiện theo DBMS. Không chạy SQL PostgreSQL trên MySQL chỉ vì tên cột giống nhau.

### 3.4. Không tự ý rút ngắn các cột

Các cột như client_settings, token_settings, attributes, metadata và token values có thể tăng theo cấu hình, claims, grant type hoặc extension của ứng dụng.

Trước khi thay độ dài:
- Xác định giá trị tối đa mà mapper serialize.
- Kiểm tra token format, claims và authorization attributes.
- Kiểm tra database có hỗ trợ LOB/Text phù hợp.
- Test dữ liệu lớn qua chính JDBC repository.
- Xác nhận query lookup token vẫn hoạt động.

Không thêm index lên cột LOB/TEXT theo mẫu chung. Khả năng index và giới hạn độ dài phụ thuộc vendor. Đo query plan trước khi thêm index tùy chỉnh.

## 4. Quản lý schema bằng Flyway

### 4.1. Cách Flyway làm việc

Flyway dùng các migration có version, thường có tên dạng:

~~~text
V001__create_oauth2_registered_client.sql
V002__create_oauth2_authorization.sql
V003__create_oauth2_authorization_consent.sql
~~~

Flyway lưu lịch sử trong bảng flyway_schema_history, gồm version, mô tả, checksum, thời điểm áp dụng và trạng thái migration.

Versioned migration được chạy theo thứ tự version và chỉ áp dụng một lần. Checksum giúp phát hiện migration đã chạy bị sửa nội dung.

**Quy tắc quan trọng:** không chỉnh sửa versioned migration đã được áp dụng ở môi trường lâu dài. Nếu cần thay đổi schema, tạo migration mới có version cao hơn.

### 4.2. Ví dụ Flyway migration

Tạo ba file migration trong src/main/resources/db/migration. Mỗi file chứa toàn bộ DDL của SQL resource tương ứng đã được chọn và điều chỉnh cho vendor mục tiêu.

~~~sql
-- V001__create_oauth2_registered_client.sql
-- Dán toàn bộ DDL tương ứng từ schema resource của đúng version SAS.
-- Không để placeholder hoặc chỉ một phần CREATE TABLE trong migration thực.
~~~

~~~sql
-- V002__create_oauth2_authorization.sql
-- Dán toàn bộ DDL oauth2-authorization-schema.sql đã điều chỉnh dialect.
~~~

~~~sql
-- V003__create_oauth2_authorization_consent.sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

DDL trên minh họa bảng consent nhỏ trong schema resource hiện hành. Với hai bảng Registered Client và Authorization, phải đưa **toàn bộ** DDL từ SQL resource của đúng version vào file tương ứng; các comment ở hai file minh họa vị trí không phải migration có thể tạo schema. Không chạy migration placeholder rồi đánh dấu schema đã được tạo.

Nếu dự án đã có migration V001/V002, hãy chọn version tiếp theo chưa dùng. Version phải duy nhất trong cùng migration location.

### 4.3. Cấu hình Spring Boot

Ví dụ cấu hình:

~~~yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
  sql:
    init:
      mode: never
~~~

spring.flyway.locations xác định nơi tìm migration. Nếu database cần module Flyway riêng theo vendor, thêm module tương ứng theo hướng dẫn của Spring Boot/Flyway version đang dùng và để dependency management quản lý version.

Spring Boot có thể tự gọi Flyway.migrate() khi khởi động. Các bean sử dụng JDBC operations được Spring Boot nhận diện là phụ thuộc database initialization trong cấu hình thông thường. Nếu ứng dụng có custom initializer hoặc DataSource riêng, kiểm tra thứ tự khởi tạo rõ ràng.

Trong production có thể chạy migration như một bước release/job riêng trước khi rollout application. Cách này giúp tách quyền DDL khỏi quyền truy cập dữ liệu runtime và tránh nhiều application instances cùng chịu trách nhiệm thay đổi schema.

### 4.4. Các lệnh Flyway thường dùng

~~~bash
flyway info
flyway validate
flyway migrate
~~~

- info: xem trạng thái migration đã áp dụng, đang chờ và version hiện tại.
- validate: kiểm tra migration đã áp dụng có khớp file đang có, gồm checksum.
- migrate: áp dụng các migration còn pending.

Không chạy repair chỉ để làm mất lỗi checksum. Trước tiên xác định vì sao checksum khác nhau: file đã sửa, migration bị đổi tên, bị xóa hay môi trường dùng sai location. repair chỉ cập nhật metadata schema history theo quyết định đã review; nó không sửa DDL hoặc tự khôi phục dữ liệu.

### 4.5. Baseline cho database đã tồn tại

Nếu production đã có ba bảng trước khi đưa Flyway vào, không chạy migration tạo bảng lần đầu trực tiếp trên database đó. Cần:

1. Backup database.
2. Đối chiếu cấu trúc thật với schema của đúng version.
3. Kiểm tra dữ liệu, index, constraint, kiểu dữ liệu và bảng lịch sử.
4. Chọn version baseline phù hợp với schema đã kiểm chứng.
5. Dùng lệnh baseline có kiểm soát trên database hiện hữu.
6. Đảm bảo database mới vẫn chạy đủ migration tạo schema từ đầu.
7. Chạy validate và kiểm tra repository.

Không bật baseline-on-migrate một cách tùy tiện ở production. Nếu baseline nhầm một schema chưa đầy đủ thành schema đã hoàn tất, Flyway có thể bỏ qua các migration tạo bảng cần thiết.

### 4.6. Repeatable migration

Flyway còn có repeatable migrations, thường dùng để quản lý view, procedure hoặc dữ liệu tham chiếu cần tạo lại khi nội dung thay đổi.

Không dùng repeatable migration để tạo lại ba bảng OAuth2 chính. DDL schema nền tảng nên là versioned migration để thứ tự và trạng thái được kiểm soát rõ ràng.

## 5. Quản lý schema bằng Liquibase

### 5.1. Changelog và changeset

Liquibase lưu các thay đổi trong changelog. Mỗi changeset được định danh bởi **author**, **id** và đường dẫn changelog. Liquibase ghi nhận lịch sử trong DATABASECHANGELOG và dùng DATABASECHANGELOGLOCK để điều phối cập nhật.

Một changeset không được chạy lại mặc định sau khi đã được ghi nhận. Khi cần thay đổi, thêm changeset mới. Không sửa changeset đã được áp dụng ở môi trường lâu dài vì checksum và lịch sử triển khai sẽ không còn nhất quán.

Liquibase thường chạy changeset trong transaction nếu database hỗ trợ. DDL transaction behavior khác nhau giữa các vendor; không giả định một changeset nhiều lệnh luôn có thể rollback nguyên tử trên mọi hệ quản trị.

### 5.2. Changelog YAML dùng sqlFile

Ví dụ file src/main/resources/db/changelog/db.changelog-master.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-oauth2-registered-client
      author: platform
      comment: Create Spring Authorization Server registered client table
      changes:
        - sqlFile:
            path: sql/oauth2-registered-client-schema.sql
            relativeToChangelogFile: true
            splitStatements: true

  - changeSet:
      id: 002-create-oauth2-authorization
      author: platform
      comment: Create Spring Authorization Server authorization table
      changes:
        - sqlFile:
            path: sql/oauth2-authorization-schema.sql
            relativeToChangelogFile: true
            splitStatements: true

  - changeSet:
      id: 003-create-oauth2-authorization-consent
      author: platform
      comment: Create Spring Authorization Server consent table
      changes:
        - sqlFile:
            path: sql/oauth2-authorization-consent-schema.sql
            relativeToChangelogFile: true
            splitStatements: true
~~~

Đặt ba SQL files trong thư mục src/main/resources/db/changelog/sql/. Mỗi file chứa toàn bộ DDL lấy từ resource đúng phiên bản và đã điều chỉnh cho database mục tiêu.

Nếu muốn dùng Liquibase Change Types thay cho SQL file, có thể mô tả bảng bằng createTable, addColumn, addPrimaryKey và các change types tương ứng. Tuy nhiên, bảng Authorization có nhiều cột LOB và kiểu dữ liệu đặc thù; dùng SQL resource làm baseline giúp dễ so sánh với schema framework hơn. Liquibase vẫn quản lý thứ tự và lịch sử changeset.

### 5.3. Cấu hình Spring Boot

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  sql:
    init:
      mode: never
~~~

Spring Boot tự khởi chạy Liquibase khi starter/module tương ứng có trên classpath và cấu hình được bật. Có thể thay đổi đường dẫn changelog qua spring.liquibase.change-log.

Nếu ứng dụng cần DataSource riêng cho migration, Spring Boot hỗ trợ cấu hình @LiquibaseDataSource hoặc các thuộc tính kết nối Liquibase riêng. Tương tự Flyway, không nhất thiết phải dùng cùng một database credential với application runtime.

### 5.4. Preconditions, contexts và DBMS

Liquibase hỗ trợ preconditions để kiểm tra điều kiện trước khi chạy changeset, ví dụ database vendor, schema tồn tại hoặc một bảng/cột chưa tồn tại. Có thể dùng contexts/labels để kiểm soát migration dành cho test hoặc môi trường cụ thể.

Ví dụ thay đổi SQL theo vendor nên được thể hiện tường minh:
- Changelog PostgreSQL dùng DDL với text/timestamptz theo hướng dẫn của schema resource.
- Changelog MySQL dùng kiểu dữ liệu tương thích và cấu hình timezone của JDBC driver.
- Không để một changeset chung âm thầm chạy DDL chỉ đúng trên một vendor.

Nếu dùng sqlFile, kiểm tra relativeToChangelogFile, statement splitting và delimiter. Chạy Liquibase trên đúng database engine trước khi phát hành.

### 5.5. Rollback với Liquibase

Liquibase hỗ trợ rollback theo tag, thời điểm hoặc số changesets. Một số Change Types có rollback tự động; SQL changeset và các thao tác không có phép nghịch đảo rõ ràng cần rollback được viết thủ công.

Tuy nhiên, **rollback DDL không đồng nghĩa khôi phục dữ liệu**. Nếu changeset tạo bảng rồi production đã ghi token/authorization vào đó, rollback bằng DROP TABLE sẽ xóa dữ liệu xác thực. Với ba bảng Authorization Server, phương án thường an toàn hơn là backup/restore theo kế hoạch hoặc tạo migration tiến về phía trước (roll-forward) để sửa lỗi.

Không viết rollback xóa bảng vào pipeline production rồi xem đó là phương án khôi phục mặc định.

## 6. Chọn Flyway hay Liquibase?

Cả hai đều có thể quản lý ba schema resources. Chọn theo cách làm việc của nhóm và chuẩn migration đã có trong hệ thống.

| Tiêu chí | Flyway | Liquibase |
|---|---|---|
| Đơn vị quản lý | Versioned/repeatable migration. | Changelog và changeset. |
| Định danh | Version, description và checksum. | Author, id, changelog path và checksum. |
| Cách viết DDL | SQL hoặc Java migration. | Change Types, SQL hoặc sqlFile. |
| Thứ tự | Theo version; repeatable chạy sau versioned. | Theo thứ tự changelog/include. |
| Điều kiện | Cấu hình locations, vendor locations và callbacks. | Preconditions, contexts, labels, dbms. |
| Rollback | Tùy edition/kiểu migration; cần thiết kế trước. | Có rollback tự động cho một số Change Types; SQL cần rollback thủ công. |
| Phù hợp | Nhóm thích SQL migration đơn giản, tuần tự. | Nhóm cần mô tả thay đổi, điều kiện và rollback trong changelog. |

Đừng chọn cả hai để “tăng an toàn”. Một nguồn lịch sử duy nhất giúp mọi môi trường có cùng cách hiểu về trạng thái schema.

## 7. Kết nối JDBC repositories với schema đã migration

Sau khi migration tạo đủ ba bảng, cấu hình Spring Authorization Server dùng JDBC implementations thay vì in-memory services.

### 7.1. Khai báo JDBC beans

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
class JdbcAuthorizationPersistenceConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationService(
                jdbcTemplate, registeredClientRepository);
    }

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationConsentService(
                jdbcTemplate, registeredClientRepository);
    }
}
~~~

JdbcTemplate triển khai JdbcOperations, vì vậy có thể truyền vào các constructors của JDBC components. RegisteredClientRepository được dùng chung bởi Authorization Service và Consent Service để phân giải RegisteredClient.

RegisteredClientRepository là component bắt buộc của Authorization Server. OAuth2AuthorizationService và OAuth2AuthorizationConsentService có thể dùng implementation in-memory mặc định nếu ứng dụng không cấu hình; vì vậy hãy xác nhận hai bean JDBC ở trên thực sự được inject, nếu không dữ liệu authorization/consent sẽ mất khi process restart. Tài liệu API cũng mô tả các JDBC implementations đơn giản và cảnh báo chúng có thể không đáp ứng môi trường throughput cao; benchmark tải thực tế trước khi chọn chúng cho deployment lớn.

### 7.2. Kết nối vào Authorization Server configurer

Ví dụ cấu trúc:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2AuthorizationConsentService authorizationConsentService)
        throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer -> authorizationServer
            .registeredClientRepository(registeredClientRepository)
            .authorizationService(authorizationService)
            .authorizationConsentService(authorizationConsentService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là phần cấu hình các services vào Authorization Server. Ứng dụng hoàn chỉnh còn cần RegisteredClientRepository, JWK source, JwtDecoder, issuer, login chain, session và các endpoint OIDC/OAuth2 theo phạm vi sản phẩm.

### 7.3. Đăng ký client ban đầu

Schema chỉ tạo bảng; nó không tự tạo client cho ứng dụng. Cần provision RegisteredClient bằng migration dữ liệu có kiểm soát, một bootstrap job idempotent hoặc quy trình quản trị client riêng.

Không chèn client production bằng tay vào database với secret plaintext. Nếu seed client qua SQL, hãy tạo secret bằng đúng PasswordEncoder và lưu giá trị encoded tương ứng. Với client có secret rotation, dùng quy trình quản trị và audit thay vì chỉnh sửa trực tiếp dữ liệu trong production.

## 8. Thứ tự khởi động và cấu hình Spring Boot

### 8.1. Migration phải chạy trước repository access

Trình tự cần đạt:

~~~mermaid
flowchart TD
    A[Application or Release Job starts] --> B[Connect to target DataSource]
    B --> C[Flyway migrate or Liquibase update]
    C --> D[Verify migration history and schema]
    D --> E[Create JDBC repositories and services]
    E --> F[Start Authorization Server endpoints]
    F --> G[Accept OAuth2 and OIDC traffic]
~~~

Spring Boot nhận diện Flyway/Liquibase như database initializers và có dependency detection cho nhiều JDBC beans. Nếu ứng dụng có custom initialization code, bean tự tạo hoặc nhiều DataSources, cần bảo đảm repository không query trước khi migration hoàn tất.

### 8.2. Chỉ dùng một schema initializer

Ví dụ khi chọn Flyway:

~~~yaml
spring:
  flyway:
    enabled: true
  liquibase:
    enabled: false
  sql:
    init:
      mode: never
~~~

Ví dụ khi chọn Liquibase:

~~~yaml
spring:
  flyway:
    enabled: false
  liquibase:
    enabled: true
  sql:
    init:
      mode: never
~~~

Nếu không dùng JPA, không cần thêm cấu hình Hibernate. Nếu project có JPA cho domain khác, không để ddl-auto=create, create-drop hoặc update sửa cùng schema được migration tool quản lý. Chọn validate hoặc none theo vai trò JPA và quy trình của project.

### 8.3. Tách quyền migration và quyền runtime

Một cách triển khai production an toàn:

| Tài khoản | Quyền |
|---|---|
| Migration user | DDL cần thiết cho migration, đọc schema history/changelog, quyền tạo index/alter table theo release. |
| Application user | Chỉ CRUD cần thiết trên bảng runtime, không có quyền tùy tiện drop/alter schema. |
| Read-only/audit user | Chỉ đọc dữ liệu được phép phục vụ kiểm tra, báo cáo hoặc audit. |

Có thể cấu hình Flyway/Liquibase dùng DataSource riêng qua @FlywayDataSource, @LiquibaseDataSource hoặc thuộc tính kết nối riêng. Không ghi password vào source control; dùng secret manager/environment variables.

### 8.4. Bảo vệ dữ liệu OAuth2 trong database

Bảng Authorization có thể chứa authorization code, access token, refresh token, ID Token và metadata. Hãy xem database này như một credential store:

- Bật encryption at rest cho database, volume và backup theo tiêu chuẩn của tổ chức.
- Giới hạn quyền SELECT trực tiếp vào bảng authorization; không cấp quyền đọc rộng cho analyst hoặc ứng dụng không liên quan.
- Không ghi token, authorization payload hoặc client secret vào application logs, SQL logs hay tracing.
- Mã hóa đường truyền JDBC bằng TLS khi database nằm ngoài trust boundary của process.
- Bảo vệ snapshot/backup và kiểm tra quy trình restore có cùng mức bảo vệ.
- Theo dõi quyền truy cập và thay đổi client registration bằng audit phù hợp.

Không giả định việc dùng JDBC repository tự động mã hóa toàn bộ token values ở tầng ứng dụng. Kiểm tra implementation và yêu cầu bảo mật của deployment; nếu cần encryption riêng cho từng cột, phải thiết kế đồng bộ với cách repository serialize, tìm kiếm và đọc token.

## 9. Nâng cấp schema và rollout production

### 9.1. Schema phải tương thích với application version

Khi nâng Spring Authorization Server:
1. Xác định chính xác version dependency cũ và mới.
2. So sánh ba SQL schema resources giữa hai version.
3. Kiểm tra source code repository/row mapper nếu có thay đổi kiểu dữ liệu hoặc cột.
4. Xác định migration cần thiết cho dữ liệu hiện có.
5. Kiểm thử upgrade từ schema cũ có dữ liệu thực.
6. Triển khai migration theo release plan.
7. Sau migration, chạy smoke tests trước khi nhận traffic.

Không giả định framework tự migrate database chỉ vì dependency được nâng version. Schema migration là trách nhiệm của ứng dụng/deployment.

### 9.2. Expand/contract cho deployment nhiều instance

Nếu thay đổi schema trong khi nhiều phiên bản ứng dụng cùng chạy, dùng chiến lược expand/contract:

1. **Expand:** thêm cột hoặc cấu trúc mới theo cách tương thích với app cũ; thường cho phép null hoặc có default an toàn.
2. **Deploy compatibility code:** ứng dụng mới có thể đọc dữ liệu cũ và mới, ghi dữ liệu theo quy tắc chuyển tiếp.
3. **Backfill:** chuyển dữ liệu cũ theo batch có thể resume và có metric.
4. **Switch:** chuyển đọc/ghi sang cấu trúc mới sau khi mọi instance đã tương thích.
5. **Contract:** chỉ xóa cột/constraint cũ ở release sau, khi không còn instance hoặc job sử dụng nó.

Không drop/rename cột trong cùng release mà một instance cũ vẫn còn chạy query cũ. Với authorization data, migration phải đặc biệt cẩn trọng vì request token có thể đang được xử lý trong lúc rollout.

### 9.3. Backup và khôi phục

Trước migration có thay đổi phá hủy hoặc chuyển đổi LOB:
- Backup database và kiểm tra khả năng restore.
- Ghi lại migration version hiện tại.
- Đo thời gian chạy, lock và dung lượng dự kiến.
- Xác nhận retention của authorization/refresh token.
- Có người chịu trách nhiệm quyết định tiếp tục, dừng hoặc roll-forward.
- Giữ logs của migration nhưng redaction dữ liệu nhạy cảm.

Nếu migration thất bại một phần, không chạy lại theo cảm tính. Kiểm tra transaction behavior của database, trạng thái history table, DDL đã áp dụng và dữ liệu bị ảnh hưởng trước khi tiếp tục.

### 9.4. Không xóa token data để “làm sạch schema”

Bảng Authorization chứa credential và metadata có giá trị bảo mật. Xóa toàn bộ bảng để xử lý migration lỗi sẽ làm hỏng authorization đang còn hiệu lực và có thể gây gián đoạn đăng nhập/refresh.

Nếu cần cleanup:
- Xác định token đã hết hạn, revoked và không còn cần cho protocol flow.
- Xem xét refresh token, device/user code và authorization state còn liên quan.
- Chạy batch có giới hạn và có thể resume.
- Có audit/metric về số hàng bị xóa.
- Kiểm tra chính sách revocation, introspection và retention trước khi purge.

## 10. Kiểm thử migration và JDBC persistence

### 10.1. Test trên database rỗng

Mỗi migration phải chạy được trên database mới đúng vendor/version mà hệ thống hỗ trợ.

Checklist:

- Migration hoàn tất không lỗi.
- Ba bảng được tạo đúng tên.
- Các cột và primary keys đúng schema.
- Không có bảng nào được tạo hai lần.
- Migration history ghi đúng version/changeset.
- Khởi động Spring context với JDBC repositories thành công.

### 10.2. Test trên database đã có dữ liệu

Migration test không chỉ dừng ở CREATE TABLE. Hãy tạo dữ liệu qua repository rồi kiểm tra sau migration hoặc nâng cấp:

| Thao tác | Điều cần xác minh |
|---|---|
| RegisteredClientRepository.save() và findByClientId() | Client metadata, scopes, settings và secret encoding được giữ. |
| OAuth2AuthorizationService.save() và findByToken() | Authorization, token values, timestamps, metadata và attributes đọc lại được. |
| OAuth2AuthorizationConsentService.save() và findById() | Consent theo registered client và principal vẫn chính xác. |
| Restart application | Dữ liệu còn sau khi process dừng và khởi động lại. |
| Refresh/revoke/introspection | Các luồng đọc/ghi authorization tiếp tục hoạt động. |
| Device authorization (nếu bật) | User code/device code được lưu và truy vấn được. |

### 10.3. Dùng Testcontainers hoặc database thật tương đương

H2 tiện cho test nhanh, nhưng không thay thế được kiểm thử vendor production. LOB, timestamp, index, locking, transaction DDL và collation có thể khác nhau.

Nếu production dùng PostgreSQL, chạy migration và repository integration tests trên PostgreSQL. Nếu hỗ trợ MySQL, thêm một job/test suite MySQL riêng. Dùng cùng migration files như production; không tạo schema test bằng một bộ DDL khác.

### 10.4. Kiểm tra migration lặp lại

- Lần đầu trên database sạch: migration được áp dụng.
- Lần hai: không tạo lại bảng hoặc chạy lại versioned changeset.
- validate/history check: không có checksum drift.
- Upgrade từ version cũ: chỉ chạy migration mới còn pending.
- Test thất bại giữa chừng: biết chính xác database ở trạng thái nào và cách khôi phục.

Không dùng CREATE TABLE IF NOT EXISTS để che mọi lỗi migration. Nó có thể bỏ qua một bảng đã tồn tại nhưng sai cấu trúc, khiến ứng dụng tiếp tục chạy với schema không tương thích.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| relation/table does not exist | Migration chưa chạy, sai schema/catalog hoặc sai DataSource. | Kiểm migration history, database/schema và URL mà migration tool thực sự dùng. |
| column not found | SQL resource không khớp version dependency hoặc migration bị thiếu. | So sánh resource trong JAR với migration đã áp dụng; tạo migration bổ sung. |
| BLOB type không được hỗ trợ | Dùng schema mặc định trên PostgreSQL mà chưa đổi kiểu theo hướng dẫn. | Chọn DDL PostgreSQL phù hợp, kiểm LOB mapping. |
| Timestamp lệch giờ | Database/JDBC driver không thống nhất UTC/instant handling. | Áp dụng kiểu timestamp và JDBC URL theo hướng dẫn vendor/resource. |
| Duplicate table khi startup | Cùng lúc dùng schema.sql, Hibernate DDL và Flyway/Liquibase. | Chọn một schema owner; tắt initializer còn lại. |
| Flyway checksum mismatch | Versioned migration đã bị sửa sau khi áp dụng. | Khôi phục file cũ hoặc tạo migration mới; chỉ dùng repair sau khi review lịch sử. |
| Liquibase checksum mismatch | Changeset đã áp dụng bị sửa hoặc path/identity thay đổi. | Khôi phục changeset hoặc thêm changeset mới; không xóa history tùy tiện. |
| Repository trả null dù bảng có dữ liệu | Dùng sai DataSource/schema, mapper/version mismatch hoặc dữ liệu được chèn sai format. | Kiểm constructor, SQL, registered client ID và cách serialize dữ liệu. |
| Token mất sau restart | Vẫn dùng InMemory service/repository. | Đăng ký JDBC beans và xác minh chúng được inject vào configurer. |
| Migration lock lâu | DDL/index/backfill gây lock hoặc migration đang chạy ở node khác. | Kiểm session/lock DB, kế hoạch migration và thời gian chạy; không xóa lock/history row bằng tay. |
| Query authorization chậm | JDBC implementation hoặc index chưa phù hợp tải. | Đo query plan, benchmark; đánh giá index vendor-specific hoặc repository tùy chỉnh. |
| Nâng version làm đọc token lỗi | Schema resource hoặc serialization contract thay đổi. | So sánh version, test upgrade với dữ liệu thực và bổ sung migration tương thích. |

## 12. Bài tập thực hành

**Bối cảnh:** Authorization Server có ba môi trường local, staging và production. Local dùng PostgreSQL container. Production đã có client registrations, authorization codes, access/refresh tokens và consent.

### Yêu cầu

1. Xác định version Spring Authorization Server trong dependency.
2. Lấy ba SQL resources tương ứng từ đúng JAR.
3. Tạo migration Flyway với version duy nhất hoặc Liquibase changelog với ba changesets.
4. Chuyển DDL sang dialect PostgreSQL theo ghi chú schema resource, bao gồm LOB và timestamp.
5. Cấu hình Spring Boot chỉ dùng migration tool đã chọn.
6. Tạo JDBC beans cho RegisteredClient, Authorization và Consent.
7. Khởi động Authorization Server trên database rỗng.
8. Tạo client, thực hiện Authorization Code Flow, cấp token và lưu consent.
9. Restart application và xác minh client/authorization/consent vẫn còn.
10. Thêm một migration mới có tính tương thích ngược, chạy trên staging có dữ liệu.
11. Kiểm tra Flyway validate hoặc Liquibase changelog history.
12. Thử nâng cấp Spring Authorization Server trong nhánh test, so sánh schema resources và ghi lại migration cần thiết.
13. Thiết kế backup/roll-forward plan cho production.
14. Tách migration credentials khỏi runtime credentials.

**Tiêu chí hoàn thành:** database mới được tạo đúng; database cũ nâng cấp không mất dữ liệu; JDBC repositories đọc/ghi được; migration history nhất quán; application runtime không có quyền DDL không cần thiết.

## 13. Checklist trước khi production

- [ ] Đã chốt version Spring Authorization Server/Spring Security.
- [ ] Ba SQL resources được lấy từ đúng dependency version.
- [ ] Migration files được lưu trong source control.
- [ ] Chỉ một tool quản lý schema: Flyway hoặc Liquibase.
- [ ] Không có initializer khác cùng sửa các bảng OAuth2.
- [ ] Thứ tự tạo Registered Client, Authorization và Consent rõ ràng.
- [ ] DDL đã được điều chỉnh và test trên database vendor mục tiêu.
- [ ] BLOB/TEXT và timestamp/timezone đã được kiểm chứng.
- [ ] Không rút ngắn token/metadata columns nếu chưa benchmark và kiểm giới hạn.
- [ ] Flyway version/checksum hoặc Liquibase changeset identity ổn định.
- [ ] Không sửa migration/changeset đã áp dụng ở môi trường lâu dài.
- [ ] Database đã có sẵn được baseline sau khi so sánh schema, không tự động bỏ qua migration.
- [ ] Có migration riêng cho mọi thay đổi schema mới.
- [ ] Có test trên database rỗng và database có dữ liệu.
- [ ] Có integration tests cho cả ba JDBC repositories.
- [ ] Restart application không mất client, authorization và consent.
- [ ] Migration chạy trước khi Authorization Server nhận traffic.
- [ ] Có backup và restore rehearsal trước migration rủi ro.
- [ ] Có kế hoạch expand/contract cho rolling deployment.
- [ ] Migration user và application user được tách quyền.
- [ ] Logs không ghi token, client secret hoặc authorization payload.
- [ ] Có retention/cleanup policy cho authorization đã hết hạn hoặc revoked.
- [ ] Có runbook xử lý checksum mismatch, failed migration và database lock.

## Tổng kết

Spring Authorization Server cung cấp ba JDBC schema resources cho Registered Client, Authorization và Authorization Consent. Các JDBC components phụ thuộc trực tiếp vào cấu trúc những bảng này; vì vậy, schema phải khớp với version framework và database vendor đang chạy.

Flyway quản lý versioned migrations theo thứ tự và checksum; Liquibase quản lý changelog/changeset với lịch sử, preconditions và rollback. Cả hai đều có thể triển khai ba SQL resources, nhưng mỗi schema chỉ nên có một migration owner. Spring Boot hỗ trợ chạy migration trong startup; với production, có thể tách migration thành release job dùng credential DDL riêng.

Phần khó nhất thường nằm ở tương thích database và nâng cấp dữ liệu đang tồn tại: LOB, timestamp/timezone, schema drift, application instances chạy đồng thời và token còn hiệu lực. Hãy kiểm thử bằng chính database engine production, giữ migration bất biến sau khi áp dụng, backup trước thay đổi rủi ro và ưu tiên roll-forward khi rollback có thể làm mất authorization data.

## Tài liệu tham khảo

1. [Spring Authorization Server 1.5.8 — JdbcRegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/JdbcRegisteredClientRepository.html): classpath schema resource và JDBC repository cho RegisteredClient.
2. [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): schema resource, JDBC operations, LobHandler và giới hạn throughput.
3. [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationConsentService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationConsentService.html): schema resource và consent persistence.
4. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClientRepository, OAuth2AuthorizationService và OAuth2AuthorizationConsentService.
5. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway, Liquibase, SQL initialization và database initialization ordering.
6. [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): version, ordering, checksum và tính bất biến của migration đã áp dụng.
7. [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): kiểm tra migration đã áp dụng với file migration hiện có.
8. [Flyway — Schema History Table](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table): lịch sử, checksum và trạng thái migration.
9. [Liquibase Community — What is a Changeset?](https://docs.liquibase.com/community/user-guide-5-0/what-is-a-changeset): định danh changeset, checksum và thứ tự áp dụng.
10. [Liquibase Community — YAML Changelog Example](https://docs.liquibase.com/community/user-guide-5-0/yaml-changelog-example): cấu trúc changelog YAML.
11. [Liquibase Community — sqlFile](https://docs.liquibase.com/community/reference-guide-5-0/change-types/sqlfile): dùng SQL file trong changeset.
12. [Liquibase Community — Preconditions](https://docs.liquibase.com/oss/user-guide-4-33/what-are-preconditions): điều kiện kiểm soát việc chạy changeset.
13. [Liquibase Community — Rollback](https://docs.liquibase.com/community/reference-guide-5-0/init-update-and-rollback-commands/rollback): rollback theo tag và yêu cầu rollback thủ công cho SQL changesets.
14. [Spring Security source — oauth2-authorization-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): ví dụ DDL authorization và ghi chú PostgreSQL/MySQL; luôn đối chiếu resource của dependency version đang dùng.
15. [Spring Security source — oauth2-registered-client-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql): ví dụ DDL Registered Client và ghi chú timestamp theo vendor.
16. [Spring Security source — oauth2-authorization-consent-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): DDL Authorization Consent.

