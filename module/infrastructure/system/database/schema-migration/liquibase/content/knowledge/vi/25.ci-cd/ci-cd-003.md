# Truyền cấu hình môi trường và bí mật trong pipeline

## 1. Mục tiêu và bối cảnh

Một pipeline CI/CD cần biết phải kết nối database nào, chạy changelog nào, dùng schema nào, chọn context/label nào và xác thực bằng danh tính nào. Những giá trị này thay đổi theo môi trường. Database URL của local khác staging và production; schema có thể khác nhau; tài khoản migration của production thường có quyền DDL riêng. Nếu đưa tất cả vào source code hoặc truyền tùy tiện qua command line, pipeline dễ chạy nhầm database hoặc làm lộ credential.

Trong một quy trình Liquibase, cần phân biệt hai nhóm đầu vào:

- **Cấu hình môi trường:** các giá trị mô tả đích và cách chạy, chẳng hạn JDBC URL hoặc target alias, schema, changelog path, context, label, timeout và tùy chọn DBMS.
- **Bí mật:** database password, access token, private key, certificate private key hoặc thông tin xác thực để lấy secret từ hệ thống khác.

Cấu hình có thể được lưu trong file version control nếu không nhạy cảm và không chứa secret. Bí mật phải được cấp ở thời điểm chạy từ secret store hoặc identity của pipeline, có quyền tối thiểu và vòng đời ngắn phù hợp.

Bài học thuộc chương **CI/CD** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module giúp nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm bài là truyền đúng cấu hình và bí mật tới job migration, bảo đảm cùng một artifact được kiểm chứng trước khi cập nhật từng môi trường.

Sau bài học, người đọc có thể:

1. Phân loại cấu hình không bí mật và secret trong pipeline.
2. Tách cấu hình development, staging, production khỏi changelog và source code.
3. Cấp credential qua CI secret store, secret manager hoặc workload identity.
4. Truyền tham số cho Liquibase CLI và Spring Boot mà không đưa secret vào log.
5. Xác minh database/schema đích trước khi chạy update.
6. Kiểm soát quyền, masking, artifact, approval, rotation và xử lý sự cố lộ secret.

## 2. Mô hình cấu hình của một lần migration

Một lần chạy Liquibase cần đủ thông tin để tái hiện và kiểm toán:

| Nhóm | Ví dụ | Nguồn thường dùng |
|---|---|---|
| Artifact | Commit, image digest, changelog root | Build pipeline/release manifest |
| Kết nối | JDBC URL hoặc connection alias, driver | Environment configuration |
| Định danh | Username, workload identity, certificate | Secret manager/identity provider |
| Phạm vi schema | Default schema, catalog nếu DBMS hỗ trợ | Environment configuration/allowlist |
| Bộ lọc | Context, label, DBMS filter | Release configuration |
| Thực thi | Command, timeout, lock wait, log level | Pipeline definition |
| Kiểm chứng | DBMS/version, schema state, changeset history | Preflight và postflight |

Luồng tổng quát:

~~~text
Release artifact đã được build
          |
          v
Chọn environment (dev / staging / production)
          |
          +------> Nạp cấu hình không bí mật
          |
          +------> Xác thực pipeline identity
                         |
                         v
                  Lấy secret đúng scope
                         |
                         v
               Tạo process Liquibase có kiểm soát
                         |
                         v
             Validate / status / SQL preview
                         |
                         v
                    Approval
                         |
                         v
                      Update
                         |
                         v
              Verify + audit + cleanup
~~~

Không nên để developer tự gõ một URL và password bất kỳ trong bước production. Đích kết nối phải được pipeline chọn từ environment đã phê duyệt, còn secret phải được cấp cho đúng job đó.

## 3. Phân biệt cấu hình và bí mật

### 3.1. Cấu hình không bí mật

Ví dụ:

- Tên environment: development, staging, production.
- Target alias: orders-staging hoặc orders-production.
- Changelog root và đường dẫn file.
- Schema mặc định đã được allowlist.
- Context/label được release owner phê duyệt.
- DBMS type/version kỳ vọng.
- Thời gian chờ lock và timeout theo chính sách.
- Tên secret reference, không phải giá trị secret.

Các giá trị này vẫn có thể tiết lộ kiến trúc nội bộ. Hãy phân loại theo chính sách tổ chức, nhưng không cần đối xử với chúng giống password nếu chúng không cấp quyền truy cập.

### 3.2. Bí mật

Ví dụ:

- Database password.
- Access token dùng để truy cập secret manager.
- Private key hoặc nội dung private certificate.
- Cloud credential tĩnh.
- Token của hệ thống artifact hoặc deployment.
- Thông tin xác thực dùng cho proxy hoặc tunnel.

Không đặt secret trong:

- Changelog YAML/XML/JSON/SQL.
- File cấu hình được commit.
- Dockerfile hoặc image layer.
- Command line argument.
- Build log, debug log hoặc release note.
- SQL preview, rollback SQL hoặc comment trong changeset.
- Test fixture được đóng gói vào artifact.

Một nguyên tắc quan trọng: changelog mô tả thay đổi database; secret cấp quyền thực hiện thay đổi. Hai trách nhiệm này cần được quản lý riêng.

### 3.3. Không coi mọi biến môi trường là secret

Biến môi trường chỉ là một cách truyền giá trị vào process. Tên biến, giá trị và quyền đọc của nó mới quyết định mức độ nhạy cảm. Ví dụ DB_SCHEMA có thể là cấu hình; DB_PASSWORD là secret. Tuy nhiên, cả hai đều có thể bị lộ nếu pipeline in toàn bộ environment.

## 4. Thiết kế cấu hình theo môi trường

Một cách tổ chức là giữ cấu hình không bí mật trong các file riêng:

~~~text
config/
  liquibase/
    common.properties
    development.properties
    staging.properties
    production.properties
db/
  changelog/
    db.changelog-master.yaml
    changes/
~~~

Ví dụ file cấu hình staging chỉ chứa giá trị không bí mật:

~~~properties
changelog-file=db/changelog/db.changelog-master.yaml
default-schema-name=orders
liquibase-schema-name=migration_control
liquibase-log-level=info
contexts=staging
labels=release
~~~

Ví dụ trên không chứa URL hoặc password. Có thể lưu trong repository nếu chính sách cho phép và nội dung không tiết lộ thông tin cần bảo vệ. Nếu URL được coi là thông tin nội bộ, lưu nó trong cấu hình environment được kiểm soát thay vì file dùng chung.

### 4.1. Một nguồn chuẩn cho mỗi giá trị

Mỗi tham số nên có một nguồn có thẩm quyền:

| Tham số | Nguồn đề xuất |
|---|---|
| Environment name | Deployment environment của CI/CD |
| JDBC URL/target | Environment configuration được phê duyệt |
| Database username/password | Secret store hoặc workload identity |
| Changelog root | Artifact đã build |
| Schema mặc định | Allowlist của service/environment |
| Context/label | Release manifest |
| Liquibase version | Dependency/toolchain đã khóa phiên bản |

Tránh khai báo cùng một giá trị ở nhiều nơi với các giá trị mặc định khác nhau. Nếu pipeline, file properties và command line cùng đặt URL, cần hiểu rõ thứ tự ưu tiên của phiên bản Liquibase và integration đang dùng. Một giá trị ghi đè ngoài dự kiến có thể khiến migration chạy nhầm database.

### 4.2. Tách cấu hình chung và cấu hình riêng

Thông tin chung như changelog root hoặc log level có thể được dùng lại. JDBC URL, schema, credential và context có thể khác theo environment. Tách cấu hình giúp tránh sao chép cả bộ file rồi vô tình giữ URL production trong cấu hình staging.

Không tạo file properties production có password rồi commit với lý do repository private. Git history, clone, cache và bản sao vẫn có thể tồn tại sau khi xóa file.

## 5. Quản lý nhiều môi trường mà không sửa changelog

Changelog nên mô tả thay đổi schema có thể áp dụng qua các môi trường. Cấu hình kết nối và tham số môi trường được truyền khi chạy.

Ví dụ property không nhạy cảm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-orders
      author: orders-team
      changes:
        - createTable:
            schemaName: ${app.schema}
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Pipeline có thể truyền app.schema theo môi trường nếu property được hỗ trợ bởi cấu hình Liquibase đang dùng. Tên schema cần lấy từ allowlist đã phê duyệt; không nhận identifier tùy ý từ request hoặc branch name.

Không viết một changelog riêng chứa password cho từng environment. Cũng không thay URL production vào file changelog. JDBC URL xác định kết nối database; schema property xác định namespace object trong connection đó. Hai mục đích khác nhau.

### 5.1. Context và label không phải bí mật

Context/label có thể chọn nhóm changeset theo môi trường hoặc giai đoạn. Chúng không phải cơ chế bảo vệ credential và không tự tách lịch sử DATABASECHANGELOG.

Nếu một changeset có context production, việc chọn context chỉ quyết định changeset có đủ điều kiện chạy hay không theo cấu hình; nó không xác thực người chạy có quyền production. Quyền truy cập phải được kiểm soát bởi CI/CD environment, identity và database grants.

### 5.2. Không đưa secret vào property substitution

Liquibase property substitution có thể đưa giá trị vào SQL được sinh. Nếu property là password, token hoặc dữ liệu cá nhân, giá trị có thể xuất hiện trong SQL preview, log hoặc exception. Chỉ dùng property cho cấu hình cần thiết và đã phân loại, không dùng changelog làm secret store.

## 6. Nguồn cấp secret cho pipeline

### 6.1. Secret store tích hợp của CI/CD

Nhiều nền tảng CI/CD cung cấp secret theo repository, project, environment hoặc deployment scope. Cần:

- Tách secret development, staging và production.
- Chỉ cấp production secret cho job thuộc environment production.
- Hạn chế ai được sửa workflow và ai được phê duyệt deployment.
- Không cho fork hoặc pull request không tin cậy nhận secret production.
- Mask giá trị trong log, nhưng vẫn tránh in secret từ nguồn.
- Thu hồi secret khi job hoàn tất nếu nền tảng hỗ trợ credential tạm thời.

Secret store tích hợp thuận tiện cho quy trình vừa phải. Với tổ chức nhiều hệ thống, secret manager tập trung có thể quản lý rotation, audit và policy tốt hơn.

### 6.2. Secret manager tập trung

Pipeline có thể xác thực với secret manager rồi lấy credential đúng environment. Cần giới hạn:

- Identity của job được phép đọc secret nào.
- Secret path/project/environment nào được truy cập.
- Thời hạn token và credential.
- Các thao tác được audit.
- Cách thu hồi khi runner hoặc job bị xâm nhập.

Không dùng một token có quyền đọc toàn bộ secret của tổ chức cho mọi pipeline.

### 6.3. Workload identity và OIDC

Nếu nền tảng hỗ trợ OIDC federation hoặc workload identity, job có thể chứng minh danh tính với cloud/secret manager mà không lưu một cloud access key dài hạn trong CI. Provider xác thực token dựa trên issuer, audience, repository/project, branch, environment hoặc claim được cấu hình.

Nguyên tắc:

1. Giới hạn issuer và audience đúng provider.
2. Chỉ cho phép repository/project và branch/environment được tin cậy.
3. Cấp quyền đọc đúng secret hoặc lấy credential database cần thiết.
4. Dùng token ngắn hạn.
5. Ghi audit identity và lần truy cập.

OIDC không tự cấp quyền database. Sau khi xác thực, policy vẫn phải quyết định job được đọc secret nào hoặc nhận database identity nào.

### 6.4. Credential ngắn hạn và certificate

Nếu DBMS và nền tảng hỗ trợ, ưu tiên token hoặc certificate có thời hạn ngắn thay cho password tĩnh. Khi dùng TLS:

- Xác minh server certificate và hostname.
- Bảo vệ private key.
- Theo dõi thời hạn certificate.
- Có quy trình rotate trước khi hết hạn.
- Không tắt certificate validation để khắc phục lỗi kết nối.

Không giả định mọi JDBC driver/DBMS hỗ trợ cùng cơ chế token hoặc certificate. Kiểm tra tài liệu và thử nghiệm với đúng driver/version.

## 7. Truyền secret vào Liquibase CLI

Liquibase CLI có thể nhận cấu hình từ defaults file, environment variables, command options hoặc các integration được hỗ trợ. Tên biến, cách ánh xạ và thứ tự ưu tiên phụ thuộc phiên bản CLI. Hãy khóa phiên bản và kiểm tra tài liệu hoặc liquibase --help của toolchain đang chạy.

### 7.1. Tránh password trong command line

Không làm như sau:

~~~bash
liquibase --url=jdbc:postgresql://db-host:5432/orders \
  --username=orders_admin \
  --password=real-password \
  update
~~~

Password truyền trực tiếp có thể xuất hiện trong shell history, process list, command echo hoặc log runner. Không thay bằng cách nối secret vào chuỗi lệnh rồi giả định CI masking sẽ che hết.

### 7.2. Dùng environment variable được Liquibase hỗ trợ

Ví dụ khái niệm với CLI có hỗ trợ quy ước environment variables tương ứng:

~~~bash
export LIQUIBASE_COMMAND_URL="$DB_JDBC_URL"
export LIQUIBASE_COMMAND_USERNAME="$DB_MIGRATION_USERNAME"
export LIQUIBASE_COMMAND_PASSWORD="$DB_MIGRATION_PASSWORD"

liquibase --defaults-file=config/liquibase/staging.properties validate
liquibase --defaults-file=config/liquibase/staging.properties status --verbose
liquibase --defaults-file=config/liquibase/staging.properties update
~~~

Các tên biến trong ví dụ cần được xác nhận với phiên bản Liquibase CLI cụ thể. Không giả định một bản CLI cũ hoặc wrapper nội bộ hỗ trợ cùng quy ước. Không bật shell tracing quanh đoạn đọc secret; không in environment để kiểm tra.

Sau khi process hoàn tất, xóa hoặc unset biến trong phạm vi job nếu runner tái sử dụng process/workspace. Environment variable vẫn có thể bị đọc bởi process hoặc user đủ quyền trên cùng host; bảo vệ runner và giới hạn quyền truy cập.

### 7.3. Defaults file tạm

Một số pipeline cần tạo file properties tạm để truyền cấu hình. Khi làm vậy:

- Tạo trong workspace tạm riêng của job.
- Đặt quyền đọc chỉ cho user chạy migration.
- Không ghi nội dung ra stdout.
- Không upload file vào artifact.
- Không đưa file vào cache.
- Xóa sau khi hoàn tất, kể cả khi job thất bại.
- Đảm bảo shell tracing không in nội dung được mở rộng.

Properties file có thể cần escaping với ký tự đặc biệt như dấu hai chấm, dấu bằng hoặc backslash. Dùng cơ chế tạo file đã được kiểm thử thay vì nối chuỗi tùy tiện; ưu tiên environment integration nếu CLI hỗ trợ.

### 7.4. Không trộn nhiều nguồn cấu hình không kiểm soát

Nếu URL được đặt trong defaults file nhưng username/password được đặt qua environment, cần xác nhận Liquibase thực sự nhận đúng giá trị. Trước khi update, ghi lại target alias và kiểm tra database identity mà không in secret. Tránh trường hợp biến môi trường rỗng khiến công cụ dùng nhầm giá trị mặc định.

## 8. Truyền cấu hình cho Spring Boot

Với migration chạy trong Spring Boot startup, Liquibase thường dùng datasource được cấu hình cho ứng dụng, trừ khi dự án khai báo bean/datasource riêng. Cấu hình có thể được externalize:

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_RUNTIME_USERNAME}
    password: ${DB_RUNTIME_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: ${DB_DEFAULT_SCHEMA}
    liquibase-schema: ${LIQUIBASE_METADATA_SCHEMA}
~~~

Các placeholder được resolve từ environment hoặc nguồn cấu hình Spring được thiết lập. Không ghi giá trị secret trực tiếp vào file YAML được commit. Nếu dùng migration job riêng, runtime application thường tắt auto-run Liquibase bằng cấu hình profile có kiểm soát, còn job chịu trách nhiệm cập nhật schema.

### 8.1. Runtime datasource và migration datasource

Trong production, runtime user thường chỉ cần quyền nghiệp vụ; migration user cần quyền DDL và cập nhật bảng history/lock. Có thể tách datasource:

| Datasource | Principal | Mục đích |
|---|---|---|
| Runtime | orders_runtime | Truy vấn và ghi dữ liệu nghiệp vụ |
| Migration | orders_migrator | Chạy Liquibase và cập nhật metadata |

Nếu dùng migration datasource trong Spring, phải gắn đúng bean bằng qualifier và bảo đảm auto-configuration không tạo thêm một Liquibase instance ngoài dự kiến. Với CI/CD job riêng, credential migration chỉ được cấp cho job và không được đóng gói vào image ứng dụng.

### 8.2. Không nhầm Spring property với Liquibase property

spring.datasource.* cấu hình datasource của ứng dụng. spring.liquibase.* cấu hình Liquibase integration. Khi dùng nhiều datasource hoặc bean custom, nguồn kết nối thực tế có thể khác cấu hình mặc định. Hãy xác minh bean và target trong môi trường test trước khi chạy production.

## 9. Pipeline ví dụ với GitHub Actions

Ví dụ sau minh họa cách gắn secret của environment vào job migration. Tên secret là ví dụ; cần tạo chúng trong environment phù hợp và giới hạn quyền người có thể thay đổi workflow.

~~~yaml
name: database-migration

on:
  workflow_dispatch:

jobs:
  migrate:
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
    env:
      LIQUIBASE_COMMAND_URL: ${{ secrets.DB_JDBC_URL }}
      LIQUIBASE_COMMAND_USERNAME: ${{ secrets.DB_MIGRATION_USERNAME }}
      LIQUIBASE_COMMAND_PASSWORD: ${{ secrets.DB_MIGRATION_PASSWORD }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Validate changelog
        run: liquibase --defaults-file=config/liquibase/staging.properties validate

      - name: Check pending changesets
        run: liquibase --defaults-file=config/liquibase/staging.properties status --verbose

      - name: Apply migration
        run: liquibase --defaults-file=config/liquibase/staging.properties update
~~~

Đây là ví dụ minh họa, không phải workflow hoàn chỉnh cho mọi repository. Hãy pin action về commit SHA đã review trong production, cài đúng Liquibase/JDBC driver, kiểm tra biến môi trường theo phiên bản CLI và cấu hình approval cho environment. Không đưa secret vào run expression hoặc echo command. Với production, thêm gate review SQL preview và xác minh sau update.

### 9.1. Tách job theo environment

Có thể tạo job staging và production với environment riêng:

- Staging nhận secret staging và URL staging.
- Production nhận secret production sau approval.
- Mỗi job dùng cùng release artifact và changelog.
- Không cho job staging truy cập secret production.

Không dùng một biến DB_PASSWORD chung cho mọi environment nếu nền tảng có thể cấp secret theo scope. Tách tên secret giúp audit và giảm nguy cơ job sai environment nhận credential mạnh.

### 9.2. Không cấp secret cho pull request không tin cậy

Pull request từ fork hoặc branch không được tin cậy có thể thay đổi workflow/script để đọc và gửi secret ra ngoài. Không cấp secret production cho build/test chạy trên mã chưa được review. Tách CI validation không cần secret khỏi deployment job có quyền truy cập database.

## 10. Pipeline ví dụ với GitLab CI

Ví dụ khái niệm:

~~~yaml
stages:
  - validate
  - migrate

liquibase_validate:
  stage: validate
  image: liquibase/liquibase:latest
  script:
    - liquibase --defaults-file=config/liquibase/staging.properties validate
  rules:
    - if: '$CI_COMMIT_BRANCH'

liquibase_migrate_staging:
  stage: migrate
  image: liquibase/liquibase:latest
  environment:
    name: staging
  script:
    - liquibase --defaults-file=config/liquibase/staging.properties status --verbose
    - liquibase --defaults-file=config/liquibase/staging.properties update
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

Trong cấu hình thực tế, các biến kết nối phải được tạo thành CI/CD variables có masking/protection và được giới hạn theo environment/branch phù hợp. Image latest chỉ để minh họa; production cần pin Liquibase version hoặc image digest đã kiểm chứng. Không giả định masking ngăn mọi hình thức lộ secret.

## 11. Xác minh đúng đích trước khi chạy update

Một pipeline có thể dùng secret hợp lệ nhưng kết nối nhầm database. Vì vậy, cần kiểm tra target identity trước khi thực thi DDL.

### 11.1. Kiểm tra từ database

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_schema() AS current_schema;
~~~

Đối chiếu kết quả với environment manifest hoặc target alias. Không in credential; database name/user có thể được ghi trong log nội bộ nếu chính sách cho phép, nhưng URL đầy đủ và thông tin mạng nên được phân loại.

Với DBMS khác, dùng hàm/catalog tương ứng. Không dùng câu SQL PostgreSQL cho mọi database.

### 11.2. Kiểm tra allowlist

Trước update, xác minh:

- Environment được chọn là environment được phê duyệt.
- Target alias nằm trong allowlist của service.
- JDBC host/database tương ứng target alias.
- Schema nằm trong danh sách được phép.
- DBMS/version đúng với release.
- Migration username đúng principal của environment.
- Changelog root và context/label đúng.

Nếu bất kỳ giá trị nào thiếu hoặc mâu thuẫn, dừng pipeline. Không tự fallback sang URL mặc định hoặc database local.

### 11.3. Tránh đưa identifier tùy ý vào changelog

Schema/table/catalog là identifier SQL, không phải bind value thông thường. Nếu property substitution được dùng cho identifier, chỉ nhận từ allowlist hoặc kiểm tra theo quy tắc tên chặt chẽ. Không lấy trực tiếp tên schema từ input người dùng hoặc branch name rồi đưa vào SQL.

## 12. Quyền database và nguyên tắc least privilege

Migration pipeline cần quyền DDL nhưng không nhất thiết cần quyền quản trị toàn server.

| Principal | Quyền đề xuất |
|---|---|
| CI validate không kết nối DB | Không cần database credential |
| CI status/preview | Có thể dùng quyền đọc metadata phù hợp nếu command cần kết nối |
| Migration principal | DDL/DML cần thiết trong schema thuộc service và quyền metadata Liquibase |
| Runtime principal | Quyền nghiệp vụ cần cho ứng dụng, không cần quyền DDL thường xuyên |
| DBA/break-glass | Quyền quản trị đặc biệt, dùng theo quy trình phê duyệt và audit |

Một số changeset có thể cần quyền đặc biệt để tạo extension, role, tablespace hoặc object cấp database. Tách provisioning đặc quyền thành bước DBA được kiểm soát nếu migration user không cần các quyền đó thường xuyên.

Không dùng cùng một superuser credential cho mọi service và mọi environment. Nếu một pipeline bị xâm nhập, phạm vi quyền của credential quyết định mức độ ảnh hưởng.

## 13. Secret masking và log hygiene

Masking của CI/CD giúp che giá trị secret khi nó xuất hiện đúng định dạng trong log, nhưng không phải lớp bảo vệ duy nhất. Secret có thể bị encode, nối chuỗi, cắt đoạn hoặc xuất hiện trong exception theo cách không được mask.

Các nguyên tắc:

- Không echo secret để xác nhận đã nhận.
- Không chạy env, printenv hoặc dump toàn bộ configuration.
- Không bật shell tracing quanh bước sử dụng secret.
- Không truyền password qua command line.
- Không log datasource object hoặc Liquibase properties nguyên khối.
- Không ghi SQL preview có literal nhạy cảm ra console công khai.
- Giữ debug/trace ở mức tối thiểu và chỉ bật có thời hạn.
- Hạn chế người có quyền đọc CI logs và artifacts.

### 13.1. Log những gì cần cho audit

Có thể ghi:

- Release id/commit.
- Target alias và environment.
- Liquibase version.
- Changelog path.
- Context/label không bí mật.
- Changeset id và trạng thái.
- Thời gian bắt đầu/kết thúc và kết quả.
- Artifact digest và approval reference.

Tránh ghi:

- Password/token/private key.
- Full environment dump.
- JDBC URL chứa credential.
- Bind values hoặc bản ghi khách hàng.
- SQL preview đầy đủ vào log có quyền truy cập rộng.

### 13.2. Bảo vệ SQL preview và rollback SQL

SQL preview có thể chứa literal từ insert/update/loadData hoặc dữ liệu được thay thế qua property. Lưu file trong artifact store hạn chế quyền, có encryption, audit và retention. Nếu chỉ cần bằng chứng review, lưu hash, metadata và approval reference; không nhất thiết lưu nội dung SQL ở kho mở.

Rollback SQL có thể chứa dữ liệu khôi phục hoặc câu lệnh destructive. Áp dụng cùng tiêu chuẩn bảo mật như update SQL.

## 14. Quản lý secret theo vòng đời

### 14.1. Cấp phát

Tạo credential riêng cho migration pipeline theo environment và service. Ghi rõ owner, scope, database, quyền và ngày hết hạn. Nếu có thể, dùng credential ngắn hạn được cấp khi job chạy.

### 14.2. Sử dụng

Chỉ cấp secret cho bước thực sự cần. Ví dụ, lint/parse changelog có thể không cần database credential; validate/status/preview có thể cần kết nối tùy command và cấu hình; update cần quyền thực thi. Tách job giúp giảm thời gian secret tồn tại trong runner.

### 14.3. Rotation

Khi xoay password:

1. Tạo credential mới hoặc cập nhật principal theo quy trình DBMS.
2. Cập nhật secret store.
3. Kiểm tra job mới kết nối thành công trong môi trường an toàn.
4. Thu hồi credential cũ sau khi mọi consumer đã chuyển.
5. Theo dõi lỗi authentication sau rotation.

Không thay secret production ngay trước migration quan trọng mà chưa kiểm tra job, runner và connection pool sử dụng credential mới.

### 14.4. Revocation và cleanup

Sau job:

- Kết thúc process Liquibase.
- Xóa file tạm chứa secret theo policy.
- Thu hồi token ngắn hạn nếu nền tảng hỗ trợ.
- Không cache credential.
- Dọn workspace tạm.
- Giữ audit metadata không chứa secret.

Runner dùng chung cần được làm sạch giữa các job; không dựa vào việc job kết thúc để giả định mọi file và environment đã biến mất.

## 15. Quản lý nhiều database hoặc tenant

Nếu một release cập nhật nhiều database, mỗi đích cần cấu hình và secret scope riêng:

| Đích | Cấu hình | Secret/identity | History |
|---|---|---|---|
| orders-staging | URL/schema staging | Migration identity staging | DATABASECHANGELOG staging |
| orders-production | URL/schema production | Migration identity production | DATABASECHANGELOG production |
| billing-production | URL/schema billing | Migration identity billing | DATABASECHANGELOG billing |

Không dùng một credential có quyền trên mọi database nếu service có thể được tách quyền. Không giả định một update thành công trên database A có nghĩa database B đã được cập nhật.

### 15.1. Tenant schema

Với schema-per-tenant, pipeline có thể lặp cùng changelog cho từng tenant. Cần xác định:

- Tenant được phép migrate trong đợt này.
- Schema name từ registry/allowlist.
- History và lock scope theo tenant.
- Credential có quyền đúng tenant.
- Checkpoint và kết quả từng tenant.
- Concurrency và cách resume sau lỗi.

Không dùng một DATABASECHANGELOG chung cho nhiều tenant độc lập nếu mỗi tenant cần tiến độ riêng; changeset đã ghi nhận ở history chung có thể bị bỏ qua ở tenant sau.

### 15.2. Partial failure

Nếu tenant A, B thành công nhưng C thất bại:

- Lưu trạng thái riêng từng tenant.
- Không chạy lại mù quáng trên A/B.
- Kiểm tra history/object của C trước retry.
- Xác định ứng dụng có tương thích trạng thái không đồng đều hay cần pause traffic.
- Resume từ checkpoint theo đúng tenant.

## 16. Kiểm tra cấu hình trước khi migration

Một preflight pipeline nên kiểm tra:

1. Artifact và changelog root tồn tại.
2. Liquibase/JDBC driver version đúng.
3. Environment được chọn hợp lệ.
4. URL/target alias không rỗng và thuộc allowlist.
5. Secret đã được cấp nhưng không được in.
6. Connection tới đúng database và user.
7. Schema tồn tại hoặc có bước provisioning rõ ràng.
8. Context/label đúng với release.
9. DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm đúng scope.
10. Migration principal có quyền cần thiết.

Sau preflight:

~~~bash
liquibase --defaults-file=config/liquibase/staging.properties validate
liquibase --defaults-file=config/liquibase/staging.properties status --verbose
liquibase --defaults-file=config/liquibase/staging.properties update-sql
~~~

Tên lệnh SQL preview có thể là update-sql hoặc updateSQL tùy phiên bản. Dùng đúng CLI đã khóa phiên bản. Validate kiểm tra changelog theo khả năng của công cụ; status cho biết changeset pending; preview cho biết SQL dự kiến. Không bước nào tự chứng minh database production sẽ thực thi không lock hoặc dữ liệu sẽ đúng.

## 17. Giữ cùng cấu hình giữa preview và update

Một lỗi thường gặp là review SQL preview với URL/schema/context này rồi chạy update với một bộ biến khác. Để tránh:

- Tạo một release manifest bất biến cho lần chạy.
- Gắn target alias, environment, DBMS/version và schema.
- Gắn artifact digest và Liquibase version.
- Gắn context/label và parameters không bí mật.
- Ghi hash của SQL preview nếu lưu artifact.
- Sau approval, dùng đúng artifact và cấu hình đã review.

Secret có thể được cấp mới khi job chạy, nhưng identity và quyền phải tương đương scope đã phê duyệt. Nếu target, parameters hoặc artifact thay đổi, cần chạy lại review.

## 18. Xử lý sự cố cấu hình và bí mật

### 18.1. Sai environment hoặc chạy nhầm database

1. Dừng pipeline hoặc các bước tiếp theo.
2. Xác định database thực tế qua connection/audit log và catalog.
3. Xác định changeset nào đã chạy.
4. Đánh giá tác động và khả năng tương thích ứng dụng.
5. Không tự xóa history để chạy lại.
6. Tạo kế hoạch forward fix/restore theo trạng thái thật.
7. Sửa allowlist và preflight để ngăn lặp lại.

### 18.2. Authentication thất bại sau rotation

- Xác nhận job nhận đúng secret version.
- Kiểm tra username, endpoint và quyền principal.
- Kiểm tra secret chưa hết hạn hoặc bị revoke.
- Xác nhận runner không dùng cache/config cũ.
- Không in password ra log để so sánh.

### 18.3. Secret xuất hiện trong log/artifact

1. Hạn chế quyền đọc log/artifact và dừng chia sẻ.
2. Xác định loại secret, phạm vi và bản sao.
3. Xoay hoặc thu hồi credential.
4. Kiểm tra audit log database, CI/CD và secret manager.
5. Xử lý các bản sao theo retention/incident policy.
6. Sửa pipeline, logger hoặc changelog gây lộ.
7. Chạy lại test để xác minh output không còn secret.

Chỉ xóa một dòng console không đủ nếu secret đã được lưu ở artifact, log aggregator, backup hoặc ticket.

## 19. Bài thực hành

### Bài A — Tách cấu hình và secret

1. Tạo file staging properties chỉ chứa changelog path, schema và context.
2. Đặt JDBC URL, username và password trong secret/configuration store của môi trường thử nghiệm.
3. Cấp các giá trị cho Liquibase CLI qua cơ chế được phiên bản hỗ trợ.
4. Chạy validate và status.
5. Xác nhận console không in secret.
6. Thay target staging bằng database lab thứ hai và xác minh preflight phát hiện đúng đích.

Mục tiêu: cấu hình thay đổi theo environment trong khi changelog vẫn giữ nguyên.

### Bài B — Truyền secret trong CI

1. Tạo CI environment staging và secret dành riêng cho database lab.
2. Gắn secret vào job migration dưới dạng environment variables.
3. Không echo biến hoặc bật shell tracing.
4. Chạy validate, status và update trong database lab.
5. Kiểm tra log/artifact không chứa credential.
6. Tách một environment production giả lập và xác nhận job staging không đọc được secret đó.

Mục tiêu: hiểu secret scope và quyền truy cập theo environment.

### Bài C — Approval và artifact

1. Sinh SQL preview từ changelog.
2. Lưu preview trong artifact store thử nghiệm có quyền hạn chế.
3. Review nội dung và ghi hash.
4. Approval đúng artifact digest.
5. Chạy update với cùng changelog/parameters/target.
6. Verify schema và ghi release manifest.

Mục tiêu: bảo đảm SQL được review chính là SQL thuộc lần triển khai.

### Bài D — Rotation

1. Tạo credential migration thử nghiệm mới.
2. Cập nhật secret store.
3. Chạy preflight bằng credential mới.
4. Thu hồi credential cũ.
5. Kiểm tra job không còn tham chiếu secret cũ.

Mục tiêu: luyện rotation mà không đưa giá trị secret vào log.

## 20. Checklist trước khi chạy migration trong pipeline

- [ ] Environment được chọn từ cấu hình triển khai được phê duyệt.
- [ ] JDBC target/alias, DBMS và schema đúng môi trường.
- [ ] Cấu hình không bí mật tách khỏi credential.
- [ ] Secret nằm trong CI secret store/secret manager, không ở repository.
- [ ] Production secret chỉ được cấp cho job/environment được phép.
- [ ] Pull request hoặc branch không tin cậy không nhận secret production.
- [ ] Có thể dùng workload identity/OIDC hoặc credential ngắn hạn nếu nền tảng hỗ trợ.
- [ ] Không truyền password trực tiếp qua command line.
- [ ] Tên environment variables và precedence đã được xác nhận theo phiên bản Liquibase.
- [ ] Không bật shell tracing hoặc in toàn bộ environment.
- [ ] Migration principal có least privilege và tách khỏi runtime principal khi phù hợp.
- [ ] Changelog không chứa secret hoặc dữ liệu production nhạy cảm.
- [ ] Schema/catalog identifier lấy từ allowlist.
- [ ] Preflight xác minh đúng database/user/schema trước update.
- [ ] Validate/status/SQL preview chạy với cùng artifact và parameters.
- [ ] Preview/rollback SQL được bảo vệ bằng quyền và retention.
- [ ] Production có approval và audit trail.
- [ ] Postflight kiểm tra schema, dữ liệu và DATABASECHANGELOG.
- [ ] Secret được rotate/revoke và workspace tạm được cleanup theo policy.
- [ ] Có quy trình xử lý sai target, authentication failure và secret leak.

## 21. Ghi nhớ

Pipeline Liquibase cần truyền hai loại thông tin có trách nhiệm khác nhau: cấu hình xác định môi trường/đích chạy, còn secret cấp quyền kết nối và thực thi. Giữ cấu hình không bí mật trong environment configuration hoặc release manifest; cấp credential từ CI secret store, secret manager hoặc workload identity đúng scope. Không đưa password vào changelog, source control, command line, log hay SQL artifact.

Trước khi update, xác minh target alias, database identity, user, schema, DBMS/version, context và artifact. Dùng cùng changelog/parameters đã được preview và phê duyệt. Tách migration principal khỏi runtime principal khi phù hợp, giới hạn quyền theo database/tenant và quản lý rotation. Nếu secret lộ, hạn chế truy cập, thu hồi credential, điều tra bản sao và sửa nguồn gốc. Kết hợp precondition, checksum, DATABASECHANGELOG, kiểm chứng sau migration và CI/CD approval giúp mỗi thay đổi có thể truy vết mà vẫn bảo vệ cấu hình và bí mật của từng môi trường.
