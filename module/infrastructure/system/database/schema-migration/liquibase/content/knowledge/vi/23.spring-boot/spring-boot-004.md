# Cấu hình contexts, labels và schema theo profile trong Spring Boot

## 1. Mục tiêu và bối cảnh

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, nhóm sử dụng Liquibase để quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời cần migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một ứng dụng thường chạy ở local, development, test, staging và production. Các môi trường có thể dùng chung changelog nhưng cần chọn changeset, schema, datasource và quyền khác nhau.

Spring Boot profile chọn cấu hình runtime. Liquibase context và label lọc changeset. Thuộc tính schema xác định namespace của đối tượng nghiệp vụ và nơi lưu metadata Liquibase. Hiểu đúng vai trò của từng lớp giúp một artifact được phát hành nhất quán mà vẫn áp dụng đúng thay đổi cho từng môi trường.

Sau bài học, bạn cần:

- Phân biệt Spring profile, Liquibase context, label và thuộc tính DBMS.
- Cấu hình context/label filter trong application configuration theo profile.
- Phân biệt default schema của object nghiệp vụ với schema lưu lịch sử Liquibase.
- Truyền schema theo profile vào changelog bằng parameter.
- Xác minh tập changeset và SQL dự kiến trước khi chạy update.
- Thiết kế datasource, quyền và quy trình production an toàn.

## 2. Bốn cơ chế khác nhau

### 2.1. Spring profile chọn cấu hình ứng dụng

Profile là cơ chế Spring để chọn property source phù hợp. Ví dụ `dev` dùng datasource development và schema `app_dev`; `test` dùng database kiểm thử; `prod` dùng endpoint production và schema nghiệp vụ production. Profile không phải thuộc tính changeset. Nó ảnh hưởng Liquibase khi Spring Boot ánh xạ các giá trị vào `spring.liquibase.*` hoặc Liquibase parameters.

### 2.2. Context chọn tình huống triển khai

Changeset có thể khai báo `context` như `common`, `dev` hoặc `test`. Spring Boot truyền bộ lọc qua `spring.liquibase.contexts`. Context hữu ích để tách schema chung, dữ liệu mẫu development/test hoặc một nhóm migration chỉ dùng trong quy trình nhất định.

Context không phải cơ chế phân quyền. Khi không truyền context filter, Liquibase có thể chọn cả changeset được gắn context theo quy tắc mặc định. Vì vậy, không gắn context `prod` rồi giả định changeset sẽ tự bị loại khỏi môi trường khác.

### 2.3. Label nhóm thay đổi theo release hoặc tính năng

Label là nhãn trên changeset, thường dùng để nhóm baseline, tính năng hoặc đợt phát hành. Ví dụ `baseline`, `billing`, `release-2026-11` và `seed`. Spring Boot truyền label filter qua `spring.liquibase.label-filter` ở các phiên bản hỗ trợ.

Label filter có cú pháp biểu thức riêng của Liquibase; xác nhận cú pháp AND/OR/NOT và khả năng của phiên bản đang dùng. Label không tự chọn profile và không thay thế context. Một changeset có thể mang cả context lẫn label, và phải thỏa các điều kiện lọc có liên quan.

### 2.4. DBMS filter chọn hệ quản trị

Thuộc tính `dbms` chọn engine như `postgresql`, `mysql`, `mssql` hoặc `oracle`. Nó không có nghĩa `dev` hay `prod`. Changeset `dbms: postgresql` có thể chạy ở mọi môi trường PostgreSQL phù hợp nếu những điều kiện khác cho phép.

| Cơ chế | Vai trò | Ví dụ |
|---|---|---|
| Spring profile | Chọn cấu hình runtime | `dev`, `test`, `prod` |
| Liquibase context | Chọn tình huống triển khai | `common`, `dev-seed` |
| Liquibase label | Chọn nhóm release/tính năng | `baseline`, `billing` |
| Liquibase `dbms` | Chọn hệ quản trị | `postgresql`, `mssql` |

## 3. Cấu hình Liquibase trong Spring Boot

Ví dụ cấu hình gốc trong `application.yml`:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: ${DB_APP_SCHEMA:app}
    liquibase-schema: ${DB_LIQUIBASE_SCHEMA:liquibase_meta}
    parameters:
      appSchema: ${DB_APP_SCHEMA:app}
      auditSchema: ${DB_AUDIT_SCHEMA:audit}
~~~

Các thuộc tính chính:

- `enabled` bật/tắt Liquibase auto-configuration.
- `change-log` trỏ tới master changelog trong classpath của artifact.
- `default-schema` là schema mặc định cho object nghiệp vụ khi changeset không chỉ rõ schema.
- `liquibase-schema` là schema lưu `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.
- `parameters` cung cấp biến thay thế trong changelog, ví dụ ${appSchema}`.

Các biến môi trường và giá trị mặc định trong ví dụ chỉ để minh họa. Production nên nhận giá trị rõ ràng từ cấu hình triển khai/secret store; không để hệ thống âm thầm rơi về schema mặc định nếu đó không phải schema được phê duyệt.

### 3.1. Datasource dùng cho Liquibase

Nếu không cấu hình kết nối Liquibase riêng, Spring Boot thường dùng datasource đã được auto-configure cho ứng dụng. Khi cần user migration riêng, có thể cấu hình `spring.liquibase.url`, `spring.liquibase.user` và `spring.liquibase.password` theo phiên bản Spring Boot.

Tài khoản runtime thường chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ; tài khoản migration có thể cần quyền tạo/sửa bảng, index, constraint và ghi metadata. Tách hai tài khoản giúp giảm quyền của ứng dụng sau khi migration hoàn tất.

Không commit password vào Git hoặc file profile. Dùng biến môi trường, secret manager hay cơ chế cấp credential của nền tảng. Với nhiều datasource, phải chỉ rõ datasource Liquibase sử dụng, ví dụ bean được đánh dấu `@LiquibaseDataSource` hoặc kết nối Liquibase riêng. Không giả định datasource đầu tiên luôn là database cần migration.

### 3.2. Quyền và schema metadata

`liquibase-schema` chỉ định nơi lưu metadata; nó không bảo đảm Liquibase tự tạo schema bất kể quyền. Tùy DBMS, schema có thể cần được DBA/provisioning tạo trước hoặc được bootstrap bởi một bước có quyền phù hợp. User Liquibase cần quyền:

- Tạo, đọc và cập nhật `DATABASECHANGELOG` cùng `DATABASECHANGELOGLOCK`.
- Tạo/sửa object nghiệp vụ trong schema đích.
- Đọc metadata mà các precondition cần truy vấn.

Không cấp quyền owner/admin rộng cho tài khoản ứng dụng chỉ để migration chạy được. Hãy phân định quyền bootstrap, migration và runtime.

## 4. Cấu hình theo profile

Spring Boot nạp cấu hình gốc rồi áp dụng các property source của profile đang hoạt động. Ví dụ:

### application-dev.yml

~~~yaml
spring:
  config:
    activate:
      on-profile: dev
  liquibase:
    contexts: common,dev
    label-filter: baseline,dev
    default-schema: app_dev
    liquibase-schema: liquibase_dev
    parameters:
      appSchema: app_dev
      auditSchema: audit_dev
~~~

### application-test.yml

~~~yaml
spring:
  config:
    activate:
      on-profile: test
  liquibase:
    contexts: common,test
    label-filter: baseline,test
    default-schema: app_test
    liquibase-schema: liquibase_test
    parameters:
      appSchema: app_test
      auditSchema: audit_test
~~~

### application-prod.yml

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  liquibase:
    contexts: common,prod
    label-filter: baseline,prod
    default-schema: app
    liquibase-schema: liquibase_meta
    parameters:
      appSchema: app
      auditSchema: audit
~~~

Đây là cấu hình minh họa; tên profile và schema phải theo môi trường thật. Các thuộc tính scalar như `contexts` và `label-filter` bị override theo quy tắc property source của Spring, không tự nối với giá trị ở file gốc. Vì vậy, khai báo đầy đủ bộ lọc mong muốn trong từng profile, ví dụ `common,prod` nếu changeset chung mang context `common`.

### 4.1. Kích hoạt profile từ bên ngoài

~~~bash
SPRING_PROFILES_ACTIVE=dev
~~~

Hoặc tham số chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Trong Kubernetes, profile thường được cấp từ Deployment, ConfigMap/Secret hoặc biến môi trường container. Tránh đặt `spring.profiles.active` cố định trong `application-prod.yml`; profile nên được chọn từ môi trường chạy.

Spring cho phép nhiều profile cùng hoạt động, ví dụ `dev,metrics`. Khi đó nhiều file cấu hình có thể cùng đóng góp property; biến môi trường hoặc property source ưu tiên cao hơn cũng có thể ghi đè schema/context. Trước deploy, kiểm tra cấu hình hiệu lực đã loại secrets: profile active, datasource target, schema nghiệp vụ, schema metadata, contexts, label filter và changelog.

## 5. Khai báo context và label trong changelog

Ví dụ master changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-customer-table
      author: database-team
      context: common
      labels: baseline
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false

  - changeSet:
      id: insert-development-customer
      author: database-team
      context: dev
      labels: dev
      changes:
        - insert:
            schemaName: ${appSchema}
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 900001
              - column:
                  name: full_name
                  value: Development Example

  - changeSet:
      id: add-customer-search-index
      author: database-team
      context: common
      labels: release-2026-11
      changes:
        - createIndex:
            schemaName: ${appSchema}
            tableName: customer
            indexName: idx_customer_full_name
            columns:
              - column:
                  name: full_name
~~~

Với cấu hình dev ở phần trước, context filter gồm `common` và `dev`, label filter gồm `baseline` và `dev`. Changeset tạo bảng và dữ liệu mẫu được chọn; changeset index mang label `release-2026-11` không được chọn bởi label filter đó. Muốn index thuộc đợt release, cần đưa label phù hợp vào filter.

### 5.1. Changeset không gắn context hoặc label

Changeset không khai báo context thường vẫn được xem xét chạy dù có context filter. Tương tự, changeset không có label thường không bị loại chỉ vì label filter được chỉ định. Đừng coi field bỏ trống là cách ẩn migration khỏi production.

### 5.2. Biểu thức context

Liquibase hỗ trợ biểu thức context với OR/AND/NOT và nhóm; cú pháp cụ thể phụ thuộc phiên bản. Dạng đơn giản `common,prod` thường thể hiện OR giữa các context. Khi dùng biểu thức phức tạp, hãy xác nhận parser của phiên bản và kiểm tra bằng `status`/`update-sql` với đúng filter.

Tiền tố `@` trong context có ý nghĩa yêu cầu context được chỉ định tường minh trong filter ở những trường hợp Liquibase hỗ trợ. Nó có thể giảm nguy cơ changeset đặc biệt chạy khi người vận hành quên filter, nhưng **không phải ranh giới bảo mật** và không thay thế kiểm soát quyền/deploy.

### 5.3. Label expression

Label filter có thể biểu đạt OR, AND, NOT và ngoặc theo phiên bản. Ví dụ:

~~~text
baseline AND (billing OR customer-api)
~~~

Xác nhận label gắn trên changeset và phiên bản Liquibase trước khi dùng biểu thức. Filter sai có thể làm thiếu migration hoặc chọn thêm changeset ngoài dự kiến. Label không kiểm tra người phát hành có quyền chạy release hay không.

## 6. Schema theo profile: hai namespace khác nhau

### 6.1. Schema nghiệp vụ và schema metadata

Phân biệt:

- **Default schema / schema ứng dụng:** nơi Liquibase tạo bảng, view, index hoặc constraint nghiệp vụ khi changeset không nêu schema.
- **Liquibase schema:** nơi lưu bảng theo dõi changeset và lock, thường là `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.

Ví dụ trên PostgreSQL:

~~~text
app_dev.customer
app_dev.purchase_order
liquibase_dev.databasechangelog
liquibase_dev.databasechangeloglock
~~~

Trong production, schema nghiệp vụ có thể là `app` và metadata là `liquibase_meta`. Tách metadata giúp phân quyền và quản lý vòng đời rõ hơn; không bắt buộc mọi hệ thống phải tách nếu chính sách vận hành không cần.

### 6.2. Default schema và Liquibase schema

~~~yaml
spring:
  liquibase:
    default-schema: app_prod
    liquibase-schema: liquibase_meta
~~~

`default-schema` là schema mặc định cho object nghiệp vụ; `liquibase-schema` chỉ schema metadata. Tên property Spring Boot khác cách viết thuộc tính cấu hình Liquibase core/CLI.

Nếu changeset khai báo `schemaName` tường minh, nó xác định schema cho object đó. Điều này hữu ích với changelog nhiều schema hoặc khi cần tránh phụ thuộc schema mặc định. Tuy nhiên, hard-code `app_dev` trong changelog có thể khiến production tạo object vào schema dev nếu filter không ngăn changeset; hãy dùng parameter hoặc default schema theo môi trường.

### 6.3. Schema không có cùng ý nghĩa trên mọi DBMS

| DBMS | Ý nghĩa thường gặp |
|---|---|
| PostgreSQL | Schema là namespace bên trong database; search_path ảnh hưởng phân giải tên không qualify |
| MySQL | Schema thường đồng nghĩa database trong cú pháp và metadata |
| SQL Server | Schema là namespace trong database, ví dụ `dbo` hoặc `app` |
| Oracle | Schema gắn với user sở hữu object; user/schema có quan hệ chặt |

Vì vậy `default-schema: app` không có nghĩa thao tác giống nhau trên cả bốn DBMS. Xác nhận user, quyền, database/catalog và schema owner theo hệ quản trị cụ thể.

## 7. Truyền tên schema vào changelog bằng parameter

Khi cùng một changelog cần dùng schema khác theo profile, có thể truyền parameter:

~~~yaml
spring:
  liquibase:
    parameters:
      appSchema: app_dev
      auditSchema: audit_dev
~~~

Trong changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-audit-event
      author: database-team
      context: common
      changes:
        - createTable:
            schemaName: ${auditSchema}
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: event_type
                  type: VARCHAR(80)
~~~

Liquibase thay ${auditSchema}` bằng giá trị parameter khi xử lý changelog. Nếu parameter thiếu, kết quả có thể lỗi hoặc giữ placeholder tùy cấu hình/phiên bản; production không nên tự rơi về schema mặc định ngoài ý muốn.

Parameter phù hợp với giá trị triển khai được kiểm soát như schema name hoặc tablespace. Không ghép parameter tùy ý từ đầu vào người dùng thành SQL identifier/fragment. Với identifier động, giới hạn bằng allowlist và kiểm thử quoting; với dữ liệu, dùng change type và bind phù hợp thay vì nối chuỗi SQL.

### 7.1. Schema cần được bootstrap

Nếu schema đích chưa tồn tại, xác định ai tạo nó:

- Hạ tầng/DBA tạo schema và owner trước khi ứng dụng khởi động.
- Một bước bootstrap riêng có quyền phù hợp tạo schema.
- Liquibase tạo schema qua changeset nếu DBMS và quyền cho phép; schema metadata cần được chuẩn bị để Liquibase ghi lịch sử.

Không giả định `default-schema` tự tạo schema. Với PostgreSQL, quyền `CREATE` trên database và quyền trong schema có vai trò khác nhau; SQL Server, Oracle và MySQL có mô hình owner/privilege riêng. Kiểm tra quyền thực tế trên từng engine.

## 8. Ví dụ cấu hình theo profile

### 8.1. Cấu hình gốc

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    parameters:
      appSchema: ${DB_APP_SCHEMA:app}
      auditSchema: ${DB_AUDIT_SCHEMA:audit}
~~~

### 8.2. Development

~~~yaml
spring:
  config:
    activate:
      on-profile: dev
  datasource:
    url: ${DEV_DB_URL}
    username: ${DEV_DB_USER}
    password: ${DEV_DB_PASSWORD}
  liquibase:
    contexts: common,dev
    label-filter: baseline,dev
    default-schema: app_dev
    liquibase-schema: liquibase_dev
    parameters:
      appSchema: app_dev
      auditSchema: audit_dev
~~~

### 8.3. Production

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  datasource:
    url: ${PROD_DB_URL}
    username: ${PROD_DB_USER}
    password: ${PROD_DB_PASSWORD}
  liquibase:
    contexts: common,prod
    label-filter: baseline,prod
    default-schema: app
    liquibase-schema: liquibase_meta
    parameters:
      appSchema: app
      auditSchema: audit
~~~

Các giá trị tên user/schema chỉ minh họa; production credentials phải đến từ secret store và có quyền tối thiểu. Nếu dùng datasource riêng cho Liquibase, đặt URL/user/password Liquibase riêng và bảo đảm nó trỏ đúng database. Nếu dùng datasource ứng dụng, Liquibase sẽ dùng quyền của datasource đó.

## 9. An toàn khi triển khai production

### 9.1. Context và label không phải cơ chế bảo mật

Không dựa duy nhất vào `contexts` hoặc `label-filter` để ngăn changeset nguy hiểm chạy ở production. Nếu filter không được truyền, bị ghi đè hoặc profile chọn sai, tập changeset có thể khác kỳ vọng. Một số changeset không gắn context/label vẫn có thể được chọn. Vì vậy:

- Pipeline production truyền filter tường minh và kiểm tra cấu hình hiệu lực.
- Tài khoản Liquibase chỉ có quyền trong phạm vi schema cần thiết.
- Chỉ artifact đã review được triển khai.
- Kiểm tra URL/database/schema trước khi chạy.
- Có phê duyệt cho migration nguy cơ mất dữ liệu, lock dài hoặc thay đổi lớn.

### 9.2. Tránh profile mặc định nguy hiểm

Nếu ứng dụng không có profile rõ ràng, đừng để cấu hình mặc định trỏ tới production. Cấu hình local/dev nên dùng database an toàn; production phải được kích hoạt rõ bởi nền tảng triển khai. Có thể yêu cầu biến môi trường schema/URL không rỗng ở production và fail-fast khi thiếu.

### 9.3. Hibernate không nên cạnh tranh quản lý DDL

Nếu Liquibase là nguồn quản lý schema, cấu hình Hibernate để kiểm tra hoặc không tự sửa schema:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

`validate` yêu cầu Hibernate kiểm tra mapping với schema; `none` có thể được chọn nếu tổ chức không muốn Hibernate xác minh lúc startup. Tránh để Hibernate `update` đồng thời với Liquibase, vì hai cơ chế thay đổi schema có thể tạo kết quả không được quản lý trong cùng lịch sử.

## 10. Kiểm tra cấu hình trước khi update

Với profile và cấu hình đúng môi trường, chạy các bước kiểm tra trong pipeline hoặc môi trường an toàn:

~~~bash
liquibase --defaults-file=config/liquibase-dev.properties validate
liquibase --defaults-file=config/liquibase-dev.properties status --verbose
liquibase --defaults-file=config/liquibase-dev.properties update-sql
~~~

Trong Spring Boot, CLI dùng file properties riêng chỉ có ý nghĩa nếu cùng changelog, DBMS, contexts, label filter, schema, parameters và version Liquibase với runtime.

### 10.1. Ma trận cấu hình

| Thuộc tính | Development | Production |
|---|---|---|
| Spring profile | `dev` | `prod` |
| Liquibase contexts | `common,dev` | `common,prod` |
| Label filter | `baseline,dev` | `baseline,prod` |
| Default schema | `app_dev` | `app` |
| Liquibase schema | `liquibase_dev` | `liquibase_meta` |
| Datasource | DB development | DB production |

Trước khi `update`, đối chiếu profile active thực tế, URL/database, user Liquibase, default schema, metadata schema, contexts, label filter, parameter schema, danh sách pending từ `status --verbose` và SQL từ `update-sql`.

### 10.2. Kiểm tra sau update

Sau khi chạy migration trên database test hoặc môi trường đích được phê duyệt:

- Đọc `DATABASECHANGELOG` trong đúng schema metadata để xác nhận changeset, `EXECTYPE`, thời điểm và checksum.
- Kiểm tra object nghiệp vụ trong schema đích, không chỉ nhìn bảng lịch sử.
- Kiểm tra số hàng, constraint, default, index và quyền.
- Chạy smoke test ứng dụng bằng đúng datasource runtime.
- Xác minh changeset dev-only không xuất hiện trên production và dữ liệu production không chứa seed giả lập.

Một changeset trong `DATABASECHANGELOG` chứng minh Liquibase đã ghi nhận lần xử lý theo lịch sử; nó không tự chứng minh dữ liệu nghiệp vụ hoàn toàn đúng hoặc object chưa bị sửa thủ công sau đó.

## 11. Nhiều datasource và nhiều database

Một ứng dụng có thể kết nối database nghiệp vụ, audit hoặc reporting. Không giả định một cấu hình `spring.liquibase.*` tự động chạy changelog lên mọi datasource. Cần xác định changelog cho từng database, datasource/credentials của mỗi runner, schema metadata, bộ lọc, thứ tự migration và cách xử lý khi một database thành công còn database khác thất bại.

Spring Boot có thể dùng bean datasource được đánh dấu `@LiquibaseDataSource` cho Liquibase trong cấu hình phù hợp. Với nhiều runner, thường cần cấu hình rõ từng `SpringLiquibase` bean, changelog và datasource; tránh tạo hai runner cùng áp dụng một master changelog lên cùng database ngoài ý muốn.

Migration trên nhiều database không tự trở thành giao dịch phân tán nguyên tử. Nếu database A cập nhật thành công nhưng database B thất bại, phải có kế hoạch retry/forward-fix và kiểm tra lịch sử độc lập.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Dev chạy seed không mong muốn | Không truyền context filter hoặc changeset thiếu context | Kiểm tra `spring.liquibase.contexts` và `status` |
| Prod không chạy changeset common | Profile override contexts thành chỉ prod | Khai báo đầy đủ `common,prod` |
| Label filter loại mất migration | Label trên changeset không khớp filter | Đối chiếu labels và `label-filter` |
| Migration tạo bảng sai schema | `default-schema`/parameter/schemaName bị ghi đè | Kiểm tra cấu hình hiệu lực và SQL preview |
| Metadata nằm trong schema nghiệp vụ | `liquibase-schema` chưa cấu hình hoặc user/schema mặc định khác | Chốt metadata schema và quyền |
| Schema không tồn tại | Nghĩ rằng `default-schema` tự tạo schema | Bootstrap schema trước hoặc tạo changeset phù hợp |
| Local chạy, production thiếu quyền | User runtime bị dùng nhầm làm user migration | Tách credentials và cấp quyền theo vai trò |
| CLI và Spring Boot chọn changeset khác | Khác version, contexts, labels, parameters hoặc changelog | Đồng bộ toàn bộ cấu hình |
| Liquibase chạy nhầm database | Profile/URL bị override bởi biến môi trường/property source | Kiểm tra target an toàn trước migration |
| Hai runner cạnh tranh | Nhiều datasource/bean cùng dùng changelog hoặc metadata | Gán runner, datasource, schema và lock rõ ràng |
| Hibernate tạo schema ngoài lịch sử | `ddl-auto=update` chạy đồng thời | Chuyển sang validate/none khi Liquibase quản lý DDL |

## 13. Tình huống thực tế: cùng artifact cho dev và production

Một dịch vụ quản lý đơn hàng phát hành một artifact Spring Boot cho development và production. Nhóm cần tạo bảng `customer`, index tìm kiếm và dữ liệu mẫu để developer thao tác. Production cần bảng/index nhưng không được có dữ liệu khách hàng giả.

Thiết kế:

1. Changeset tạo bảng mang context `common` và label `baseline`.
2. Changeset index mang context `common` và label của release.
3. Changeset seed mang context `dev` và label `dev`.
4. `application-dev.yml` chọn contexts `common,dev`, label filter `baseline,dev`, schema `app_dev`.
5. `application-prod.yml` chọn contexts `common,prod`, label filter `baseline,prod`, schema `app`.
6. Cả hai profile truyền `appSchema` vào changelog và dùng schema metadata riêng.
7. CI tạo preview trên database dev và production-like, so sánh danh sách changeset.
8. Production pipeline chỉ chạy artifact đã review, với user migration và phê duyệt riêng.

Kết quả mong muốn: cùng source changelog nhưng mỗi môi trường chọn đúng changeset và schema; thay đổi chung vẫn được triển khai; seed dev bị loại ở production; lịch sử Liquibase của từng database phản ánh đúng changeset thực tế.

## 14. Checklist trước khi merge cấu hình

- [ ] Đã phân biệt rõ Spring profile, Liquibase context, label và `dbms`.
- [ ] `spring.liquibase.change-log` trỏ đúng master changelog trong artifact.
- [ ] Profile dev/test/prod khai báo đầy đủ contexts và label filter mong muốn.
- [ ] Đã hiểu hành vi của changeset không có context/label; không dùng filter làm ranh giới bảo mật.
- [ ] Schema nghiệp vụ và schema metadata Liquibase được cấu hình riêng, có lý do rõ.
- [ ] `default-schema`, `liquibase-schema` và parameters không bị property source ghi đè ngoài ý muốn.
- [ ] Schema đích đã tồn tại hoặc có bước bootstrap và quyền phù hợp.
- [ ] Datasource Liquibase trỏ đúng database; tài khoản migration tách khỏi runtime khi cần.
- [ ] Secrets không nằm trong Git hoặc log; profile không chứa password thật.
- [ ] Changelog dùng parameter schema có allowlist, không ghép SQL tùy ý từ đầu vào.
- [ ] Đã chạy `validate`, `status --verbose`, `update-sql` bằng đúng cấu hình từng môi trường.
- [ ] Đã kiểm tra lịch sử `DATABASECHANGELOG`, schema và dữ liệu sau lần update thử.
- [ ] Hibernate không đồng thời tự cập nhật schema ngoài Liquibase.
- [ ] Với nhiều datasource, từng runner có changelog, datasource, schema và lịch sử riêng rõ ràng.
- [ ] Production deploy có xác nhận target, phê duyệt và quyền tối thiểu.

**Kết luận:** cấu hình contexts, labels và schema theo profile giúp Spring Boot chọn đúng nhóm changeset và namespace cho từng môi trường. Spring profile cung cấp cấu hình runtime; Liquibase context và label lọc thay đổi; `default-schema` xác định schema mặc định của object nghiệp vụ; `liquibase-schema` xác định nơi lưu lịch sử và lock. Chúng phải được kiểm tra cùng datasource, quyền, parameters và DBMS. Kết hợp `validate`, `status`, `update-sql`, thử nghiệm trên database đại diện và đối chiếu sau `update` giúp `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` triển khai nhất quán qua Spring Boot/CI/CD mà vẫn kiểm soát được khác biệt giữa development, test, staging và production.
