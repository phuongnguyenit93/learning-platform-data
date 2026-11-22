# Cấu hình qua biến môi trường và cơ chế ưu tiên giá trị

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, cấu hình quyết định Liquibase kết nối đến database nào, nạp changelog nào, dùng tài khoản nào và chọn changeset thuộc phạm vi triển khai nào. Khi đưa migration vào nhiều môi trường, các giá trị này cần thay đổi theo môi trường mà không buộc nhóm phát triển sửa nội dung changelog hoặc tạo những bản build khác nhau.

Biến môi trường là một cách phổ biến để truyền cấu hình từ hệ điều hành, container hoặc pipeline CI/CD vào tiến trình Liquibase. Để dùng đúng, cần hiểu cách đặt tên biến, nguồn cấu hình và thứ tự ưu tiên khi một thuộc tính xuất hiện ở nhiều nơi. Cũng cần phân biệt cấu hình của Liquibase CLI với cấu hình Spring Boot: chúng có cơ chế binding và namespace riêng, dù cùng có thể nhận giá trị từ biến môi trường.

## 1. Cấu hình gồm những nhóm giá trị nào?

Một lần chạy Liquibase thường cần các nhóm cấu hình sau:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Kết nối | URL JDBC, driver, username, password | Chọn database đích và xác thực |
| Changelog | Tệp changelog gốc, search path | Xác định tập changeset cần đọc |
| Phạm vi chạy | Context, label, dbms | Chọn changeset phù hợp với lần triển khai |
| Schema | Default schema, Liquibase schema | Xác định nơi chứa đối tượng ứng dụng và bảng quản lý lịch sử |
| Hành vi lệnh | Log level, timeout, output | Điều khiển cách lệnh vận hành và báo cáo |
| Bảo mật | Tài khoản migration, secret, certificate | Giới hạn quyền và bảo vệ thông tin kết nối |

Ví dụ, cùng một artifact có thể được triển khai vào ba database khác nhau:

- Development dùng database thử nghiệm và context dev.
- Staging dùng database kiểm thử tích hợp và context staging.
- Production dùng database vận hành và tài khoản migration được cấp quyền có kiểm soát.

Các thay đổi về URL, thông tin xác thực và phạm vi chạy nên được cung cấp từ cấu hình của môi trường. Changelog đã phát hành cần được giữ ổn định để cùng một artifact có thể đi qua các giai đoạn triển khai.

## 2. Các nguồn cấu hình của Liquibase CLI

Liquibase có thể nhận một thuộc tính từ nhiều nguồn. Với cấu hình CLI thông dụng, thứ tự ưu tiên từ cao xuống thấp là:

| Ưu tiên | Nguồn | Ví dụ |
|---:|---|---|
| 1 — cao nhất | Đối số dòng lệnh | --url=jdbc:postgresql://... |
| 2 | Thuộc tính hệ thống JVM | -Dliquibase.command.url=... |
| 3 | Biến môi trường | LIQUIBASE_COMMAND_URL |
| 4 | Tệp thuộc tính Liquibase | url=jdbc:postgresql://... |
| 5 — thấp nhất | Giá trị mặc định | Giá trị mặc định của Liquibase hoặc driver |

Nếu cùng một thuộc tính được khai báo ở nhiều nguồn, nguồn có ưu tiên cao hơn sẽ quyết định giá trị hiệu lực. Chẳng hạn, URL trong đối số CLI sẽ ghi đè URL lấy từ biến môi trường; biến môi trường sẽ ghi đè URL trong tệp liquibase.properties.

Thứ tự này giúp phân chia trách nhiệm rõ ràng: tệp cấu hình có thể chứa các giá trị ít thay đổi, môi trường cung cấp thông tin của từng nơi triển khai, còn đối số CLI dùng cho lần chạy cần ghi đè có chủ đích. Tuy nhiên, ghi đè tạm thời cũng có thể khiến lệnh chạy vào database khác dự kiến. Trước khi chạy update, cần xác nhận giá trị kết nối thực tế và lệnh đang được gọi.

Thứ tự ưu tiên nêu trên áp dụng cho cấu hình Liquibase CLI. Khi chạy Liquibase thông qua Spring Boot, Spring Boot quản lý nguồn cấu hình ứng dụng theo quy tắc riêng; không nên lấy bảng này để suy ra toàn bộ thứ tự binding của Spring.

## 3. Đặt biến môi trường cho Liquibase CLI

Tên biến môi trường của Liquibase thường được tạo từ tên thuộc tính cấu hình bằng cách viết hoa và thay dấu chấm hoặc dấu gạch nối bằng dấu gạch dưới. Với các thuộc tính thuộc nhóm command, tên biến thường có tiền tố LIQUIBASE_COMMAND_.

Một số biến thường dùng:

| Thuộc tính cần cấu hình | Biến môi trường thường dùng |
|---|---|
| URL kết nối | LIQUIBASE_COMMAND_URL |
| Username | LIQUIBASE_COMMAND_USERNAME |
| Password | LIQUIBASE_COMMAND_PASSWORD |
| Changelog file | LIQUIBASE_COMMAND_CHANGELOG_FILE |
| Driver | LIQUIBASE_COMMAND_DRIVER |
| Default schema | LIQUIBASE_COMMAND_DEFAULT_SCHEMA_NAME |
| Liquibase schema | LIQUIBASE_COMMAND_LIQUIBASE_SCHEMA_NAME |
| Contexts | LIQUIBASE_COMMAND_CONTEXTS |
| Labels | LIQUIBASE_COMMAND_LABELS |
| Log level | LIQUIBASE_LOG_LEVEL |

Tên thuộc tính và biến môi trường được hỗ trợ có thể phụ thuộc phiên bản Liquibase và cách đóng gói CLI. Hãy đối chiếu tài liệu của phiên bản đang cài đặt và trợ giúp của lệnh trước khi đưa tên biến vào pipeline dùng chung. Không nên đoán một tên biến chỉ bằng cách ghép từ; cần xác nhận nó được phiên bản đó nhận diện.

### Ví dụ trên PowerShell

Các biến dưới đây chỉ có hiệu lực trong phiên PowerShell hiện tại và các tiến trình con được khởi chạy từ đó:

~~~powershell
$env:LIQUIBASE_COMMAND_URL = "jdbc:postgresql://localhost:5432/customer_db"
$env:LIQUIBASE_COMMAND_USERNAME = "liquibase_runner"
$env:LIQUIBASE_COMMAND_PASSWORD = "<secret-from-secure-store>"
$env:LIQUIBASE_COMMAND_CHANGELOG_FILE = "db/changelog/db.changelog-master.yaml"
$env:LIQUIBASE_COMMAND_CONTEXTS = "dev"
$env:LIQUIBASE_LOG_LEVEL = "info"

liquibase status --verbose
liquibase validate
liquibase update-sql
~~~

Sau khi xem xét SQL dự kiến và quyết định triển khai, có thể chạy:

~~~powershell
liquibase update
~~~

Khi hoàn tất, xóa biến nhạy cảm khỏi phiên hiện tại:

~~~powershell
Remove-Item Env:LIQUIBASE_COMMAND_PASSWORD
~~~

Không cần dùng setx cho một lần chạy thông thường. setx ghi biến vào môi trường người dùng hoặc hệ thống để các tiến trình mới nhận được; điều này có thể làm cấu hình tồn tại lâu hơn dự kiến và khiến những lần chạy sau vô tình dùng lại giá trị cũ.

### Ví dụ trên Linux hoặc macOS

~~~bash
export LIQUIBASE_COMMAND_URL="jdbc:postgresql://localhost:5432/customer_db"
export LIQUIBASE_COMMAND_USERNAME="liquibase_runner"
export LIQUIBASE_COMMAND_PASSWORD="<secret-from-secure-store>"
export LIQUIBASE_COMMAND_CHANGELOG_FILE="db/changelog/db.changelog-master.yaml"
export LIQUIBASE_COMMAND_CONTEXTS="dev"
export LIQUIBASE_LOG_LEVEL="info"

liquibase status --verbose
liquibase validate
liquibase update-sql
~~~

Có thể xóa biến khỏi shell hiện tại bằng:

~~~bash
unset LIQUIBASE_COMMAND_PASSWORD
~~~

Biến môi trường phân biệt chữ hoa và chữ thường trên nhiều hệ điều hành Unix. Hãy dùng đúng tên được tài liệu Liquibase quy định. Khi URL hoặc giá trị có ký tự đặc biệt, đặt trong dấu nháy phù hợp với shell để tránh shell tách chuỗi hoặc diễn giải ký tự ngoài ý muốn.

## 4. Kết hợp biến môi trường với liquibase.properties

Tệp liquibase.properties thích hợp để lưu các giá trị cấu hình ít nhạy cảm và dùng chung trong một dự án, chẳng hạn changelog mặc định, driver hoặc schema. Ví dụ:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
driver=org.postgresql.Driver
defaultSchemaName=app
liquibaseSchemaName=liquibase
logLevel=info
~~~

URL, username và password có thể được truyền từ môi trường triển khai để tệp không gắn chặt với một database hoặc chứa bí mật. Ví dụ, tệp properties cung cấp changelog và schema mặc định, còn pipeline đặt LIQUIBASE_COMMAND_URL, LIQUIBASE_COMMAND_USERNAME và LIQUIBASE_COMMAND_PASSWORD trước khi gọi Liquibase.

Có thể chỉ định tệp cấu hình cụ thể khi chạy CLI:

~~~bash
liquibase --defaults-file=./config/liquibase.properties status --verbose
~~~

Đường dẫn tương đối thường được tính từ thư mục làm việc của tiến trình. Trong CI/CD, hãy xác định rõ working directory hoặc dùng đường dẫn phù hợp với workspace của job. Nếu có nhiều tệp properties cho từng mục đích, hãy ghi rõ tệp nào được dùng ở mỗi lệnh để tránh phụ thuộc vào một tệp mặc định được tìm thấy ngẫu nhiên.

Không nên đưa password thật vào tệp properties được commit lên Git. Nếu dự án có tệp mẫu, chỉ lưu tên biến hoặc giá trị minh họa; secret thực tế cần được cấp từ kho bí mật hoặc cơ chế bảo mật của nền tảng chạy.

## 5. Cơ chế ưu tiên trong Spring Boot

Khi Liquibase chạy cùng ứng dụng Spring Boot, cấu hình thường được khai báo dưới namespace spring.liquibase và datasource của ứng dụng nằm dưới spring.datasource. Spring Boot dùng cơ chế externalized configuration để hợp nhất giá trị từ application.yml, tệp theo profile, biến môi trường, thuộc tính JVM và đối số dòng lệnh.

Một cách khái quát, nguồn có ưu tiên cao thường gồm đối số dòng lệnh, thuộc tính hệ thống JVM, biến môi trường của hệ điều hành, cấu hình application theo profile, cấu hình application mặc định và giá trị mặc định trong ứng dụng. Các nguồn như test properties, cấu hình được import hoặc property source tùy chỉnh có thể bổ sung thứ tự riêng; khi cần xác định chính xác, hãy kiểm tra tài liệu đúng phiên bản Spring Boot và môi trường đang chạy.

Ví dụ cấu hình application.yml:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: ${LIQUIBASE_CONTEXTS:dev}
    labels: ${LIQUIBASE_LABELS:}
~~~

Spring có thể lấy placeholder từ biến môi trường hoặc property source khác. Cú pháp ${LIQUIBASE_CONTEXTS:dev} có nghĩa là dùng giá trị LIQUIBASE_CONTEXTS nếu được cung cấp, nếu không thì dùng dev. Đây là giá trị dự phòng của placeholder; một biến được đặt nhưng có giá trị rỗng có thể tạo kết quả khác với trường hợp biến không tồn tại.

Một số biến môi trường thường dùng cho Spring Boot:

~~~bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:5432/customer_db"
export SPRING_DATASOURCE_USERNAME="app_runner"
export SPRING_DATASOURCE_PASSWORD="<secret-from-secure-store>"
export SPRING_LIQUIBASE_ENABLED="true"
export SPRING_LIQUIBASE_CONTEXTS="dev"
~~~

Spring Boot dùng relaxed binding để ánh xạ tên biến môi trường sang thuộc tính. Quy tắc phổ biến là viết hoa, thay dấu chấm bằng dấu gạch dưới và bỏ dấu gạch nối trong tên thuộc tính. Ví dụ, spring.liquibase.change-log được ánh xạ thành SPRING_LIQUIBASE_CHANGELOG. Hãy xác nhận cách ánh xạ với phiên bản Spring Boot của dự án, nhất là khi tên thuộc tính có nhiều từ hoặc cấu trúc lồng nhau.

Nếu không đặt cấu hình kết nối riêng cho Liquibase, Spring Boot thường dùng datasource mà ứng dụng đã cấu hình. Khi khai báo spring.liquibase.url hoặc thông tin đăng nhập Liquibase riêng, migration có thể sử dụng một kết nối riêng với datasource của ứng dụng. Điều này hữu ích khi tài khoản chạy migration cần quyền DDL cao hơn tài khoản ứng dụng, nhưng phải quản lý rõ hai bộ thông tin xác thực và quyền hạn.

Các thuộc tính thường gặp dưới spring.liquibase gồm enabled, change-log, url, user, password, contexts, labels, default-schema, liquibase-schema, drop-first và clear-checksums. Một số thuộc tính có thể tạo tác động lớn đến database; chỉ bật chúng trong cấu hình đã được xem xét. Đặc biệt, không bật drop-first trong môi trường có dữ liệu cần giữ lại.

## 6. Phân biệt hai hệ biến môi trường

Một dự án có thể dùng Liquibase CLI trong pipeline và cũng dùng Liquibase tích hợp Spring Boot khi ứng dụng khởi động. Hai cách chạy có thể cùng trỏ đến một database nhưng tên cấu hình không giống nhau:

| Mục đích | Liquibase CLI | Spring Boot |
|---|---|---|
| URL | LIQUIBASE_COMMAND_URL | SPRING_LIQUIBASE_URL hoặc SPRING_DATASOURCE_URL |
| Username | LIQUIBASE_COMMAND_USERNAME | SPRING_LIQUIBASE_USER hoặc SPRING_DATASOURCE_USERNAME |
| Password | LIQUIBASE_COMMAND_PASSWORD | SPRING_LIQUIBASE_PASSWORD hoặc SPRING_DATASOURCE_PASSWORD |
| Changelog | LIQUIBASE_COMMAND_CHANGELOG_FILE | SPRING_LIQUIBASE_CHANGELOG |
| Context | LIQUIBASE_COMMAND_CONTEXTS | SPRING_LIQUIBASE_CONTEXTS |
| Labels | LIQUIBASE_COMMAND_LABELS | SPRING_LIQUIBASE_LABELS |

Bảng trên mô tả cách đặt tên thường dùng; tên chính xác cần đối chiếu với phiên bản Liquibase, phiên bản Spring Boot và cách dự án binding cấu hình. LIQUIBASE_COMMAND_URL không tự động thay thế SPRING_DATASOURCE_URL trong một ứng dụng Spring Boot, và SPRING_LIQUIBASE_URL không mặc nhiên là biến cấu hình của Liquibase CLI.

Cần chọn đúng namespace theo tiến trình thực thi. Nếu CI/CD gọi Liquibase CLI, hãy cung cấp các biến LIQUIBASE_COMMAND_ tương ứng. Nếu pipeline khởi động ứng dụng Spring Boot để migration chạy lúc startup, hãy cấu hình spring.liquibase.* và datasource tương ứng. Tránh đặt cả hai bộ biến với các giá trị khác nhau mà không ghi rõ bước nào sử dụng bộ nào.

## 7. Thiết kế cấu hình cho nhiều môi trường

Một cấu hình triển khai tốt phân tách ba loại dữ liệu:

1. **Cấu hình chung:** changelog mặc định, driver và các tùy chọn ít thay đổi; có thể lưu trong liquibase.properties hoặc application.yml.
2. **Cấu hình theo môi trường:** URL, schema, context, label và các tham số kết nối; cấp qua biến môi trường hoặc tệp cấu hình profile.
3. **Bí mật:** password, token, private key và thông tin xác thực; lấy từ secret manager hoặc kho bí mật của CI/CD.

Ví dụ ma trận môi trường:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| JDBC URL | Database dev | Database staging | Database production |
| Tài khoản migration | liquibase_dev | liquibase_stage | liquibase_prod |
| Context | dev | staging | prod |
| Label | dev-test | release-candidate | release |
| Nguồn password | Secret của dev | Secret của staging | Secret production có kiểm soát |

Các giá trị trong bảng chỉ là ví dụ định hướng. Tên database, tài khoản và quy tắc context thực tế cần theo kiến trúc của dự án.

Giữ nguyên artifact và changelog khi promote từ staging sang production. Pipeline chỉ thay cấu hình kết nối và phạm vi môi trường đã được phê duyệt. Nếu sửa changelog giữa hai lần triển khai, kết quả kiểm thử staging không còn đại diện cho nội dung sẽ chạy ở production.

Context và label là bộ lọc chọn changeset, không phải cơ chế phân quyền database. Người có thể đổi biến context hoặc label có thể thay đổi tập changeset được chọn. Vì vậy, quyền chạy migration và quyền truy cập database phải được kiểm soát độc lập bằng tài khoản, quyền trên pipeline và quy trình phê duyệt.

## 8. Bảo vệ thông tin xác thực

Biến môi trường giúp tránh ghi password trực tiếp trong changelog hoặc tệp cấu hình được commit, nhưng không tự động biến secret thành dữ liệu an toàn tuyệt đối. Tiến trình có thể đọc môi trường của chính nó; quyền quản trị máy, log chẩn đoán, dump tiến trình hoặc cấu hình CI sai có thể làm lộ giá trị.

Áp dụng các nguyên tắc sau:

- Không commit password, token hoặc private key vào Git, liquibase.properties, application.yml hay script.
- Dùng secret manager, secret store của CI/CD hoặc cơ chế cấp thông tin xác thực ngắn hạn.
- Chỉ cấp secret cho job cần chạy migration và giới hạn người có quyền xem hoặc sửa cấu hình pipeline.
- Không in toàn bộ môi trường ra log; tránh lệnh debug có thể hiển thị password.
- Không đưa secret vào URL JDBC nếu URL có thể bị ghi vào log hoặc thông báo lỗi.
- Hạn chế truyền password trực tiếp qua đối số dòng lệnh vì danh sách tiến trình hoặc log thực thi có thể làm lộ đối số.
- Dùng tài khoản migration riêng, chỉ có quyền cần thiết cho thay đổi schema và dữ liệu trong phạm vi được giao.
- Xoay vòng secret theo chính sách vận hành và thu hồi ngay khi nghi ngờ bị lộ.

Với production, có thể tách tài khoản chạy migration khỏi tài khoản runtime của ứng dụng. Tài khoản migration được dùng trong job phát hành và có quyền DDL cần thiết; tài khoản runtime chỉ nhận quyền truy cập dữ liệu mà ứng dụng cần. Việc tách này làm giảm tác động nếu thông tin xác thực của ứng dụng bị lộ.

## 9. Kiểm tra cấu hình hiệu lực trước khi update

Một lỗi thường gặp là biến môi trường đã được đặt nhưng tiến trình Liquibase vẫn dùng giá trị khác. Nguyên nhân có thể là tên biến sai, biến được đặt trong shell khác, pipeline không truyền biến vào container, profile Spring Boot không đúng hoặc đối số CLI ghi đè biến môi trường.

Trước khi chạy migration:

1. Xác nhận phiên bản Liquibase hoặc Spring Boot đang thực thi.
2. Xác nhận đúng working directory và đúng tệp liquibase.properties nếu dùng CLI.
3. Kiểm tra tên biến theo tài liệu phiên bản; xác nhận biến có trong môi trường của tiến trình chạy.
4. Kiểm tra có đối số CLI hoặc JVM system property nào ghi đè giá trị không.
5. Xác nhận URL, database, schema và tài khoản bằng cách kiểm tra cấu hình không nhạy cảm; không in password.
6. Xác nhận changelog gốc, context, label và dbms.
7. Chạy status --verbose và validate.
8. Tạo SQL bằng update-sql, đọc kỹ nội dung và xác nhận đúng môi trường trước khi chạy update.

Có thể kiểm tra một số biến không nhạy cảm trong PowerShell:

~~~powershell
$env:LIQUIBASE_COMMAND_URL
$env:LIQUIBASE_COMMAND_CHANGELOG_FILE
$env:LIQUIBASE_COMMAND_CONTEXTS
~~~

Trên Linux hoặc macOS:

~~~bash
printf '%s\n' "$LIQUIBASE_COMMAND_URL"
printf '%s\n' "$LIQUIBASE_COMMAND_CHANGELOG_FILE"
printf '%s\n' "$LIQUIBASE_COMMAND_CONTEXTS"
~~~

Không dùng lệnh tương tự để in password hoặc toàn bộ môi trường. Việc xác nhận URL vẫn cần đối chiếu host, port, database và schema dự kiến; một URL có cú pháp hợp lệ vẫn có thể trỏ nhầm môi trường.

## 10. Xử lý lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Liquibase kết nối nhầm database | Biến URL sai, giá trị CLI ghi đè, shell hoặc container không nhận biến | Kiểm tra nguồn cấu hình theo thứ tự ưu tiên và URL hiệu lực |
| Báo thiếu URL hoặc driver | Tên biến sai, chưa export, sai namespace hoặc tệp defaults không được nạp | Đối chiếu tên thuộc tính với biến môi trường của phiên bản đang dùng |
| Password bị từ chối | Secret sai, hết hạn, sai user hoặc secret không được truyền vào job | Kiểm tra secret reference và tài khoản; không ghi password ra log |
| Chạy sai changelog | Working directory khác dự kiến, đường dẫn tương đối sai hoặc profile khác | Dùng đường dẫn rõ ràng, xác nhận changelog gốc và artifact |
| Changeset không chạy như dự kiến | Context, label hoặc dbms lọc changeset ra khỏi lần chạy | Kiểm tra bộ lọc hiệu lực và precondition |
| Giá trị trong application.yml không có hiệu lực | Biến môi trường, JVM property hoặc command-line argument ghi đè | Kiểm tra nguồn cấu hình Spring Boot và tên biến theo relaxed binding |
| Development chạy được nhưng production lỗi | Khác quyền, extension, schema, phiên bản DBMS hoặc giá trị cấu hình | So sánh cấu hình không nhạy cảm và kiểm tra tương thích database |
| Job migration dùng cấu hình cũ | Runner hoặc container tái sử dụng môi trường cũ, secret không được refresh | Tạo job/container với biến được cấp mới và xác nhận cấu hình đầu vào |

Khi chẩn đoán, hãy phân biệt lỗi binding cấu hình với lỗi kết nối và lỗi thực thi changeset. Nếu Liquibase không nhận được URL, cần xử lý nguồn cấu hình. Nếu kết nối thành công nhưng changeset không được chọn, hãy xem changelog, context, label và precondition. Nếu changeset được chọn nhưng SQL thất bại, cần điều tra quyền, trạng thái schema, dữ liệu và khả năng tương thích database.

## 11. Ví dụ quy trình CI/CD

Một job migration trong pipeline có thể nhận URL và tài khoản từ secret store, còn changelog và các giá trị không nhạy cảm đến từ artifact hoặc tệp cấu hình:

~~~bash
# Các biến bí mật được pipeline inject từ secret store.
export LIQUIBASE_COMMAND_URL="$MIGRATION_JDBC_URL"
export LIQUIBASE_COMMAND_USERNAME="$MIGRATION_DB_USER"
export LIQUIBASE_COMMAND_PASSWORD="$MIGRATION_DB_PASSWORD"

# Các giá trị theo môi trường được cấu hình rõ ràng.
export LIQUIBASE_COMMAND_CHANGELOG_FILE="db/changelog/db.changelog-master.yaml"
export LIQUIBASE_COMMAND_CONTEXTS="$DEPLOY_CONTEXT"
export LIQUIBASE_LOG_LEVEL="info"

liquibase status --verbose
liquibase validate
liquibase update-sql
~~~

Sau bước review SQL và điều kiện phát hành, pipeline thực hiện update trong job được kiểm soát:

~~~bash
liquibase update
~~~

Job cần bảo đảm các biến được inject vào đúng container hoặc runner chạy Liquibase. Không nên giả định biến được khai báo ở một stage sẽ tự động tồn tại trong stage khác; nhiều nền tảng tạo tiến trình hoặc container độc lập cho mỗi job. Cần truyền dữ liệu qua cơ chế variables, secrets hoặc artifacts đúng cách và tuân thủ phạm vi quyền.

Sau khi chạy, pipeline nên lưu kết quả status, validate, SQL đã review và log triển khai theo chính sách lưu trữ. Không đưa password hoặc giá trị bí mật vào artifact. Có thể xác minh lịch sử trong DATABASECHANGELOG và kiểm tra schema sau khi update để có bằng chứng migration đã hoàn thành.

## 12. Checklist cấu hình trước khi triển khai

- [ ] Đã xác định tiến trình chạy là Liquibase CLI hay Spring Boot.
- [ ] Đã xác nhận phiên bản công cụ và tên biến môi trường được hỗ trợ.
- [ ] Đã biết nguồn cấu hình nào có thể ghi đè nguồn khác.
- [ ] Đã xác nhận URL, database, schema và tài khoản đích.
- [ ] Đã nạp đúng liquibase.properties hoặc application profile.
- [ ] Đã xác nhận changelog gốc và working directory.
- [ ] Context, label và dbms khớp với môi trường triển khai.
- [ ] Secret được cấp từ kho bảo mật và không xuất hiện trong Git hoặc log.
- [ ] Tài khoản migration có đúng quyền cần thiết.
- [ ] Đã chạy status, validate và review update-sql.
- [ ] Đã xác nhận pipeline truyền cấu hình vào đúng job/container.
- [ ] Sau update, đã kiểm tra DATABASECHANGELOG và schema thực tế.

Cơ chế ưu tiên giúp Liquibase hợp nhất cấu hình từ nhiều nguồn, nhưng chỉ an toàn khi nhóm vận hành biết rõ tiến trình đang dùng namespace nào và giá trị nào đang thắng. Hãy giữ cấu hình chung ở tệp phù hợp, đưa giá trị theo môi trường qua biến môi trường hoặc profile, cấp bí mật qua secret store và kiểm tra cấu hình hiệu lực trước khi chạy migration. Khi áp dụng nhất quán, cùng một changelog có thể được triển khai có kiểm chứng qua development, staging và production, đồng thời tích hợp rõ ràng với Spring Boot và CI/CD.
