# Vai trò của `liquibase.properties` và tham số dòng lệnh

## 1. Cấu hình nằm ở đâu trong quy trình Liquibase?

Module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Người thực hiện cần kiểm chứng migration, chuẩn bị rollback, phối hợp nhiều môi trường và tích hợp Liquibase với Spring Boot hoặc CI/CD. Để một changelog có thể chạy đúng ở từng môi trường, ngoài nội dung migration còn phải cung cấp cấu hình kết nối và các tham số thực thi phù hợp.

Hai cơ chế cấu hình thường gặp khi dùng Liquibase CLI là file `liquibase.properties` và tham số dòng lệnh (command-line arguments). Chúng giúp tách thông tin môi trường khỏi changelog: cùng một changelog có thể được chạy trên database phát triển, kiểm thử hoặc production với URL, schema, context, label và tùy chọn vận hành khác nhau.

`liquibase.properties` lưu các giá trị mặc định có thể tái sử dụng cho một môi trường hoặc một nhóm lệnh. Tham số dòng lệnh truyền giá trị cho lần gọi hiện tại, rất hữu ích khi cần ghi đè một cấu hình, chạy một command cụ thể hoặc đưa giá trị từ pipeline vào tiến trình Liquibase. Hai cơ chế bổ sung cho nhau: file giúp chuẩn hóa cấu hình, còn CLI giúp điều khiển lần chạy một cách tường minh.

Các cấu hình này không thay thế changelog và không tự mô tả thay đổi schema. Changelog vẫn định nghĩa changeset cần thực hiện; cấu hình quyết định Liquibase kết nối đến đâu, đọc changelog nào và áp dụng những điều kiện thực thi nào.

## 2. `liquibase.properties` chịu trách nhiệm gì?

`liquibase.properties` là file thuộc định dạng Java Properties, thường được Liquibase CLI dùng làm nguồn cấu hình mặc định. File có thể chứa các nhóm thông tin sau:

| Nhóm | Ví dụ thuộc tính | Vai trò |
|---|---|---|
| Changelog | `changeLogFile` | Chỉ định file changelog gốc mà command sẽ sử dụng. |
| Kết nối | `url`, `username`, `password`, `driver` | Xác định database đích và thông tin kết nối. |
| Schema | `defaultSchemaName`, `liquibaseSchemaName` | Phân biệt schema ứng dụng mặc định với schema chứa bảng metadata Liquibase. |
| Phạm vi changeset | `contexts`, `labels` | Lọc changeset theo ngữ cảnh và nhãn được khai báo trong changelog. |
| Vận hành | `logLevel`, `logFile`, `changelogLockWaitTimeInMinutes` | Điều chỉnh mức log, nơi ghi log hoặc thời gian chờ lock theo nhu cầu. |
| Tài nguyên phụ trợ | `classpath`, `searchPath` | Giúp Liquibase tìm driver, changelog hoặc tài nguyên được tham chiếu khi cần. |

Tên thuộc tính và khả năng hỗ trợ có thể phụ thuộc phiên bản Liquibase, command và cách tích hợp. Hãy kiểm tra tài liệu của đúng phiên bản đang dùng trước khi đưa một thuộc tính vào cấu hình dùng chung.

### 2.1. Ví dụ file cấu hình

Ví dụ dưới đây là cấu hình phát triển với PostgreSQL. Các giá trị URL, schema và context chỉ mang tính minh họa; cần thay bằng thông tin của hệ thống thực tế.

```properties
# Changelog gốc
changeLogFile=db/changelog/db.changelog-master.yaml

# Database đích
url=jdbc:postgresql://localhost:5432/orders
driver=org.postgresql.Driver

# Schema ứng dụng và schema metadata Liquibase
defaultSchemaName=public
liquibaseSchemaName=migration_meta

# Phạm vi changeset áp dụng cho môi trường phát triển
contexts=development
labels=local

# Thông tin log và thời gian chờ lock
logLevel=info
changelogLockWaitTimeInMinutes=5
```

File Properties chấp nhận cách viết cặp khóa/giá trị như `key=value` hoặc `key: value`. Mỗi thuộc tính nên nằm trên một dòng riêng. Dấu `#` ở đầu dòng dùng để ghi chú. Với đường dẫn hoặc giá trị có khoảng trắng, cần tuân thủ quy tắc escape của Java Properties hoặc đặt đường dẫn sao cho không cần khoảng trắng.

Ví dụ không đưa `username` và `password` vào file mẫu. Trong môi trường thật, thông tin xác thực nên được cấp từ secret manager hoặc biến môi trường theo cơ chế được phiên bản Liquibase và pipeline hỗ trợ. Nếu buộc phải lưu bí mật trong file, cần giới hạn quyền đọc, loại file chứa bí mật khỏi Git và có quy trình luân chuyển thông tin xác thực.

### 2.2. File mặc định và file được chỉ định rõ

Liquibase CLI có thể tìm file `liquibase.properties` theo quy ước của môi trường chạy, thường gắn với thư mục làm việc hiện tại. Để tránh phụ thuộc vào việc người dùng đang đứng ở thư mục nào, nên chỉ định rõ file cấu hình bằng tùy chọn `--defaults-file`:

```bash
liquibase --defaults-file=conf/liquibase-dev.properties status --verbose
```

Tùy chọn này cho Liquibase biết file defaults cần đọc cho lần gọi đó. Có thể duy trì các file riêng như `liquibase-dev.properties`, `liquibase-test.properties` và `liquibase-prod.properties`, nhưng phải kiểm soát rõ file nào được dùng ở từng pipeline. Đường dẫn tương đối thường được diễn giải dựa trên thư mục làm việc của tiến trình; trong CI/CD, nên đặt `working-directory` ổn định hoặc dùng đường dẫn tuyệt đối.

Không nên tạo nhiều file cấu hình có nội dung gần giống nhau mà không có quy ước. Khi một giá trị bị thay đổi, nhóm vận hành phải biết file nào là nguồn có hiệu lực và pipeline nào đang tham chiếu file đó.

## 3. Tham số dòng lệnh điều khiển lần chạy

Tham số dòng lệnh là các cặp tùy chọn và giá trị được truyền trực tiếp khi gọi executable `liquibase`. Chúng có thể chọn command, cung cấp thông tin kết nối hoặc ghi đè một số giá trị trong file defaults.

Một số tham số thường dùng:

| Tham số CLI | Mục đích |
|---|---|
| `--defaults-file` | Chọn file cấu hình defaults cho lần chạy. |
| `--url` | Chỉ định JDBC URL của database đích. |
| `--username` | Chỉ định tài khoản kết nối. |
| `--password` | Truyền mật khẩu; cần cân nhắc rủi ro lộ bí mật khi dùng trên dòng lệnh. |
| `--changelog-file` | Chọn changelog gốc. |
| `--default-schema-name` | Chỉ định schema mặc định của database. |
| `--liquibase-schema-name` | Chỉ định schema chứa bảng metadata Liquibase. |
| `--contexts` | Chọn các context cần áp dụng. |
| `--labels` | Chọn các label cần áp dụng. |
| `--log-level` | Điều chỉnh mức độ chi tiết của log. |

Tên tùy chọn có thể có biến thể theo phiên bản và command. Dùng `liquibase --help` hoặc phần trợ giúp của command để xác nhận cú pháp được phiên bản cài đặt hỗ trợ.

### 3.1. Kết hợp file cấu hình và tham số CLI

Ví dụ dùng file cấu hình phát triển nhưng ghi đè context cho một lần chạy:

```bash
liquibase --defaults-file=conf/liquibase-dev.properties --contexts=development,seed update
```

Trong ví dụ này, URL, driver và changelog có thể lấy từ file defaults; `--contexts` cung cấp giá trị cụ thể cho lần gọi. Với các cấu hình trùng nhau, tham số CLI được chỉ định tường minh thường được ưu tiên hơn giá trị mặc định trong file. Tuy nhiên, Liquibase có nhiều nguồn cấu hình và cách ánh xạ thuộc tính đã thay đổi qua các phiên bản; khi kết hợp file, biến môi trường, system property và tham số command-scoped, cần kiểm tra quy tắc ưu tiên của phiên bản đang triển khai thay vì suy rộng một thứ tự duy nhất cho mọi thuộc tính.

Có thể truyền URL trực tiếp để thử kết nối với một database khác mà không phải sửa file defaults:

```bash
liquibase --defaults-file=conf/liquibase-dev.properties --url=jdbc:postgresql://localhost:5432/orders_test status --verbose
```

Đây là cách hữu ích để kiểm tra hoặc chạy một lần trên database thử nghiệm. Trước khi thực hiện command ghi dữ liệu, hãy xác nhận URL, schema và context đang trỏ đúng môi trường. Một URL sai có thể khiến migration hợp lệ chạy nhầm vào database không mong muốn.

### 3.2. Cấu trúc một lời gọi CLI

Một lời gọi thường có dạng:

```text
liquibase [global-options] [command] [command-options]
```

Trong đó:

- `global-options` chứa các lựa chọn áp dụng cho phiên CLI, ví dụ file defaults hoặc cấu hình kết nối.
- `command` xác định công việc như `validate`, `status`, `update`, `update-sql`, `rollback` hoặc `release-locks`.
- `command-options` cung cấp thêm tham số riêng cho command nếu command đó hỗ trợ.

Thứ tự và phạm vi một số tùy chọn có thể phụ thuộc CLI version. Nếu lệnh báo tham số không hợp lệ hoặc bị bỏ qua, hãy kiểm tra `--help` của đúng command. Không nên sao chép cú pháp từ một phiên bản khác mà không kiểm tra.

## 4. Phân chia trách nhiệm giữa file và CLI

Hai cơ chế phục vụ hai nhu cầu khác nhau:

| Tiêu chí | `liquibase.properties` | Tham số dòng lệnh |
|---|---|---|
| Mục đích chính | Lưu cấu hình mặc định có thể tái sử dụng | Điều khiển hoặc ghi đè cho lần gọi hiện tại |
| Khả năng chia sẻ | Có thể được quản lý cùng repository nếu không chứa bí mật | Được ghi trong script, pipeline hoặc lệnh chạy |
| Mức độ tường minh | Cần biết file defaults nào đang được nạp | Giá trị xuất hiện ngay trong lời gọi |
| Thay đổi theo môi trường | Dùng file defaults riêng hoặc nguồn biến môi trường | Truyền giá trị theo biến pipeline khi gọi CLI |
| Rủi ro chính | Dùng nhầm file, cấu hình cũ hoặc lộ bí mật trong file | Lệnh dài, khó bảo trì và có thể lộ bí mật trong lịch sử/process list |

Một cách tổ chức dễ vận hành là đặt các giá trị không bí mật và ít thay đổi trong file defaults, còn các giá trị thay đổi theo lần chạy được truyền qua pipeline. Không nên lặp lại toàn bộ cấu hình trong từng lệnh nếu chúng đã được quản lý tập trung; cũng không nên ẩn những tham số quan trọng đến mức người review không thể xác định database đích và phạm vi changeset.

## 5. Phân biệt cấu hình CLI với cấu hình Spring Boot

Khi chạy Liquibase CLI, `liquibase.properties` và tham số dòng lệnh là các cách cấu hình phổ biến. Khi Liquibase được Spring Boot tự động chạy lúc ứng dụng khởi động, cấu hình thường được khai báo trong `application.yml`, `application.properties` hoặc các profile của Spring Boot bằng tiền tố `spring.liquibase`.

Ví dụ cấu hình trong Spring Boot:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
    liquibase-schema: migration_meta
    contexts: production
    labels: release
```

Spring Boot bind các thuộc tính `spring.liquibase.*` vào cấu hình Liquibase của ứng dụng. Nếu ứng dụng dùng chung `DataSource`, Liquibase thường sử dụng datasource đó; nếu cần datasource migration riêng, có thể cấu hình các thuộc tính kết nối Liquibase tương ứng theo phiên bản Spring Boot. `spring.liquibase.enabled` cho phép bật hoặc tắt quá trình tự động chạy migration khi startup.

Không nên mặc định rằng Spring Boot sẽ tự đọc `liquibase.properties` theo cùng quy tắc như Liquibase CLI. Hai cơ chế có hệ thống cấu hình riêng. Nếu một pipeline chạy CLI trước khi triển khai ứng dụng, pipeline phải cung cấp file defaults và tham số CLI cho command của nó; ứng dụng Spring Boot vẫn nhận cấu hình theo Spring Environment và các thuộc tính `spring.liquibase.*`.

Trong hệ thống nhiều replica, cần thống nhất cấu hình metadata và quyết định rõ migration chạy trong startup hay ở một job triển khai riêng. Nếu cả pipeline và ứng dụng đều có thể chạy migration, cả hai phải cùng target đúng database và cùng bộ bảng metadata để `DATABASECHANGELOGLOCK` có thể điều phối các lượt chạy.

## 6. Quản lý cấu hình theo môi trường

Một hệ thống thường có ít nhất development, test/staging và production. Mỗi môi trường có thể khác URL, tài khoản, schema, context hoặc label. Không nên thay đổi changelog chỉ để chuyển môi trường; hãy cung cấp cấu hình phù hợp cho cùng một changelog.

Ví dụ tổ chức file:

```text
config/
  liquibase-dev.properties
  liquibase-test.properties
  liquibase-prod.properties
db/
  changelog/
    db.changelog-master.yaml
    changes/
```

Các file môi trường có thể dùng cùng cấu trúc thuộc tính nhưng giá trị khác nhau. Ví dụ `url` trỏ đến database riêng, `liquibaseSchemaName` thống nhất schema metadata và `contexts` chọn nhóm changeset phù hợp. Chỉ dùng context để phân biệt nội dung có chủ đích như dữ liệu mẫu hoặc cấu hình đặc thù; không nên dùng context như một cách che giấu migration bắt buộc cần chạy ở production.

Lời gọi tương ứng có thể được khai báo trong các job khác nhau:

```bash
liquibase --defaults-file=config/liquibase-test.properties validate
liquibase --defaults-file=config/liquibase-test.properties status --verbose
liquibase --defaults-file=config/liquibase-test.properties update-sql
```

Trước khi chuyển sang production, pipeline sử dụng file cấu hình production và các secret được cấp riêng cho môi trường đó. Hãy bảo đảm artifact changelog đã được review và giống nhau giữa các môi trường; thay đổi cấu hình kết nối không được làm thay đổi nội dung migration.

### 6.1. Tách cấu hình thường và bí mật

Các giá trị như changelog path, schema mặc định hoặc log level thường không phải bí mật. URL có thể chứa hostname và tên database nội bộ nên vẫn cần được bảo vệ theo chính sách tổ chức. Username, password, token và private key là thông tin nhạy cảm.

Các nguyên tắc thực hành:

1. Không commit password hoặc token thật vào Git, kể cả trong file có tên `liquibase.properties`.
2. Cấp thông tin xác thực từ secret manager hoặc biến môi trường của runner; dùng tên biến và cơ chế mapping được Liquibase version hiện tại hỗ trợ.
3. Hạn chế quyền đọc file secrets và không in giá trị bí mật ra log.
4. Tránh truyền password bằng `--password` trong lệnh có thể lưu vào shell history, nhật ký CI hoặc danh sách tiến trình.
5. Nếu bí mật đã bị commit hoặc xuất hiện trong log, xử lý như một sự cố lộ credential: thu hồi/rotate và rà soát nơi đã phát tán.

Một số phiên bản Liquibase hỗ trợ cấu hình qua biến môi trường, chẳng hạn các biến theo quy ước `LIQUIBASE_COMMAND_...`. Tên biến và thuộc tính được ánh xạ cần đối chiếu tài liệu phiên bản; không tự suy ra tên biến cho mọi thuộc tính bằng cách đổi chữ hoa/thêm tiền tố. Cũng cần kiểm tra cách runner truyền biến để tránh in chúng khi bật debug.

## 7. Đường dẫn, thư mục làm việc và tính tái lập

Một lỗi cấu hình phổ biến là lệnh chạy được trên máy cá nhân nhưng thất bại trong CI/CD vì đường dẫn tương đối được tính từ thư mục làm việc khác. Cần xác định riêng:

- Vị trí file defaults được truyền bằng `--defaults-file`.
- Vị trí changelog được chỉ định bởi `changeLogFile` hoặc `--changelog-file`.
- Các file SQL, YAML, XML, JSON hoặc file include được changelog tham chiếu.
- JDBC driver và thư viện bổ sung cần có trong classpath.

Liquibase có cơ chế tìm tài nguyên và search path; cách phân giải đường dẫn phụ thuộc cách chạy, cấu hình và phiên bản. Không nên giả định mọi đường dẫn đều tương đối với vị trí file `liquibase.properties`. Hãy quy định thư mục làm việc trong script hoặc pipeline, dùng search path có chủ đích và kiểm tra trên đúng môi trường chạy thật.

Để một lệnh có thể tái lập, cần giữ ổn định phiên bản Liquibase, driver database, changelog artifact, file defaults được chọn và các biến đầu vào. Ghi nhận những giá trị cấu hình không bí mật trong log triển khai giúp điều tra khác biệt giữa hai lần chạy; tuyệt đối không ghi password hoặc token.

## 8. Kiểm chứng cấu hình trước khi migration

Cấu hình sai có thể khiến Liquibase kết nối nhầm database, đọc sai changelog hoặc chọn nhầm changeset. Trước command ghi dữ liệu, nên kiểm tra theo thứ tự sau:

1. **Xác nhận phiên bản và cú pháp:** dùng `liquibase --version`, `liquibase --help` và trợ giúp của command để biết CLI đang chạy.
2. **Xác nhận nguồn cấu hình:** kiểm tra chính xác `--defaults-file`, thư mục làm việc và các biến môi trường được cấp.
3. **Xác nhận database đích:** kiểm tra URL, catalog/database, schema và danh tính tài khoản bằng một phương thức phù hợp với DBMS.
4. **Kiểm tra changelog:** chạy `validate` để phát hiện lỗi cấu trúc hoặc tham chiếu mà Liquibase có thể kiểm tra.
5. **Kiểm tra changeset chờ chạy:** dùng `status --verbose` để xem các changeset đang pending theo cấu hình hiện tại.
6. **Xem SQL dự kiến:** chạy `update-sql` và review SQL, đối tượng bị tác động cùng thứ tự thực thi.
7. **Chạy migration:** chỉ chạy `update` sau khi đã xác nhận đúng môi trường và phê duyệt nội dung theo quy trình triển khai.
8. **Đối chiếu kết quả:** kiểm tra log, `DATABASECHANGELOG`, schema thực tế và trạng thái triển khai.

Ví dụ chuỗi kiểm tra trên môi trường thử nghiệm:

```bash
liquibase --defaults-file=config/liquibase-test.properties validate
liquibase --defaults-file=config/liquibase-test.properties status --verbose
liquibase --defaults-file=config/liquibase-test.properties update-sql
```

`validate` và `status` không thay thế việc review SQL. `update-sql` hiển thị SQL Liquibase dự kiến sinh ra theo trạng thái và cấu hình hiện tại; kết quả có thể khác khi trạng thái database, quyền, DBMS hoặc đầu vào thay đổi. Sau khi review, command `update` mới thực sự thực thi migration.

### 8.1. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Không tìm thấy `liquibase.properties` | CLI chạy từ thư mục khác hoặc file không ở vị trí được tìm mặc định | Chỉ định `--defaults-file` bằng đường dẫn rõ ràng. |
| Không tìm thấy changelog | `changeLogFile` sai hoặc đường dẫn/search path khác giữa local và CI | Kiểm tra thư mục làm việc, đường dẫn và các file include. |
| Không kết nối được database | URL, driver, quyền mạng hoặc thông tin xác thực sai | Đối chiếu cấu hình của đúng môi trường và kiểm tra kết nối độc lập. |
| Changeset được chạy ngoài dự kiến | Context/label hoặc nguồn cấu hình bị ghi đè | Kiểm tra giá trị có hiệu lực và điều kiện của changeset. |
| Dùng nhầm schema metadata | `defaultSchemaName` và `liquibaseSchemaName` bị nhầm hoặc cấu hình không đồng nhất | Xác định schema ứng dụng và schema metadata, sau đó thống nhất giữa các runner. |
| Local chạy được nhưng pipeline thất bại | Khác Liquibase version, driver, classpath, working directory hoặc biến môi trường | Chuẩn hóa phiên bản và đầu vào của runner. |
| Pipeline báo chờ lock | Một tiến trình khác đang giữ `DATABASECHANGELOGLOCK` hoặc các runner dùng metadata khác nhau | Xác minh chủ sở hữu lock và cấu hình metadata trước khi xử lý. |

Không nên chữa lỗi bằng cách thêm nhiều tham số CLI một cách thử-và-sai. Hãy xác định nguồn nào cung cấp giá trị, command thực tế nhận giá trị nào và database đích có đúng không.

## 9. Ví dụ một quy trình triển khai có kiểm soát

Giả sử nhóm phát triển một dịch vụ quản lý đơn hàng. Changelog gốc được đóng gói cùng artifact và dùng cho các môi trường. File `liquibase-test.properties` chứa URL test, driver, schema và context test; credential được pipeline cấp từ kho bí mật. Khi job chạy, nó gọi lần lượt `validate`, `status --verbose` và `update-sql` để kiểm tra changelog và xem SQL dự kiến. Người review xác nhận database đích, changeset và SQL, sau đó job thực thi `update`.

Khi phát hành production, pipeline chọn `liquibase-prod.properties`, cấp credential production qua cơ chế secrets, đồng thời dùng cùng phiên bản Liquibase và changelog artifact đã kiểm thử. Job ghi nhận môi trường, phiên bản công cụ, changelog và các tham số không bí mật. Nếu một job khác đang migration cùng database, `DATABASECHANGELOGLOCK` điều phối quyền thực thi giữa các runner dùng chung bảng lock.

Nếu production có lỗi kết nối, nhóm kiểm tra URL, quyền truy cập, driver và schema metadata trước khi thay đổi changelog. Nếu migration đã bắt đầu và thất bại, nhóm đối chiếu `DATABASECHANGELOG` với schema thực tế để xác định trạng thái changeset. Việc chỉnh cấu hình kết nối không tự rollback thay đổi đã thực thi; rollback hoặc forward-fix vẫn phải được lập kế hoạch theo nội dung migration và khả năng của DBMS.

## 10. Checklist quản lý `liquibase.properties` và CLI

- [ ] File defaults được chỉ định rõ trong local script và pipeline bằng `--defaults-file` khi cần.
- [ ] Mỗi môi trường có cấu hình URL, schema, context/label phù hợp và được review.
- [ ] `defaultSchemaName` và `liquibaseSchemaName` được hiểu đúng và nhất quán giữa các runner.
- [ ] Tham số CLI chỉ ghi đè những giá trị có chủ đích; người review xác định được giá trị được dùng cho lần chạy.
- [ ] Cú pháp và tên thuộc tính được kiểm tra với đúng phiên bản Liquibase.
- [ ] Đường dẫn defaults, changelog, include và classpath hoạt động trong thư mục làm việc của CI/CD.
- [ ] Password, token và credential không nằm trong Git, shell history hoặc log pipeline.
- [ ] Spring Boot sử dụng cấu hình `spring.liquibase.*` phù hợp; nhóm không nhầm cấu hình này với file defaults của CLI.
- [ ] Trước `update`, pipeline đã kiểm tra cấu hình đích, chạy validate/status và review SQL dự kiến.
- [ ] Sau migration, kết quả được đối chiếu với log, `DATABASECHANGELOG` và schema thực tế.

`liquibase.properties` tạo một bộ mặc định dễ quản lý và tái sử dụng; tham số dòng lệnh giúp kiểm soát rõ lần thực thi cụ thể. Khi phân tách cấu hình theo môi trường, bảo vệ credential, kiểm soát nguồn ghi đè và kiểm chứng trước `update`, nhóm có thể dùng chung changelog Liquibase xuyên suốt development, staging và production mà vẫn giữ được khả năng truy vết và triển khai có kiểm soát.
