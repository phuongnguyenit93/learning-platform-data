# Kiểm soát thông tin nhạy cảm trong log và SQL xem trước

## 1. Vì sao log và SQL xem trước cần được bảo vệ?

Liquibase thường được chạy trong CI/CD, job triển khai hoặc lúc Spring Boot khởi động. Trong quá trình đó, công cụ kết nối database, đọc cấu hình, đánh giá changelog, tạo SQL, thực thi changeset và ghi lịch sử. Log và SQL xem trước giúp điều tra lỗi, review thay đổi và truy vết release. Tuy nhiên, chúng cũng có thể tiết lộ thông tin nhạy cảm nếu được ghi hoặc chia sẻ thiếu kiểm soát.

Một log có thể vô tình chứa JDBC URL, username, đường dẫn nội bộ, nội dung exception hoặc giá trị tham số. SQL preview có thể chứa literal được viết trong changeset, dữ liệu từ loadData/insert, logic nghiệp vụ, tên khách hàng hoặc định danh nội bộ. Một file SQL không nhất thiết chứa mật khẩu kết nối để vẫn được xem là dữ liệu nhạy cảm.

Rủi ro không chỉ đến từ việc in secret trực tiếp. Debug logging có thể mở rộng nội dung được ghi; shell history hoặc process list có thể lộ password truyền qua command line; CI artifact có thể được tải bởi người không có quyền triển khai; file SQL preview lưu lâu hơn nhu cầu; một thông báo lỗi có thể in nguyên câu SQL chứa giá trị nhạy cảm.

Bài học thuộc chương **Bảo mật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm bài này là kiểm soát thông tin nhạy cảm trong log và các bản SQL preview/update/rollback để quy trình review vẫn hữu ích mà không làm lộ bí mật hoặc dữ liệu vượt quyền.

Sau bài học, người đọc có thể:

1. Nhận diện thông tin nhạy cảm có thể xuất hiện trong log, changelog và SQL preview.
2. Phân biệt credential kết nối với literal/dữ liệu được migration sử dụng.
3. Thiết lập nguyên tắc không đưa secret vào changelog, command line, log hoặc artifact công khai.
4. Chọn mức log, cơ chế che dữ liệu, quyền truy cập và thời hạn lưu phù hợp.
5. Bảo vệ file SQL preview, log CI/CD và đầu ra rollback SQL.
6. Xử lý sự cố lộ secret, xác định phạm vi ảnh hưởng và khôi phục an toàn.

## 2. Phân loại dữ liệu cần bảo vệ

Không phải mọi thông tin xuất hiện trong log đều có cùng mức độ nhạy cảm. Hãy phân loại trước khi quyết định có thể ghi, chia sẻ hoặc lưu trữ hay không.

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Bí mật xác thực | Database password, token, private key, certificate private key | Không ghi vào log/changelog/SQL artifact; cấp qua secret manager hoặc cơ chế bảo mật |
| Thông tin kết nối | JDBC URL, hostname, port, database name, username | Phân loại theo môi trường; che hoặc hạn chế truy cập khi có thể hỗ trợ dò tìm hạ tầng |
| Dữ liệu nghiệp vụ | Email, số điện thoại, tên khách hàng, mã đơn hàng, số tài khoản | Không đưa dữ liệu thật vào ví dụ/log; giảm thiểu, mask hoặc dùng dữ liệu giả |
| Giá trị literal trong SQL | Giá trị insert/update, default, mapping, điều kiện WHERE | Review nội dung; loại bỏ dữ liệu cá nhân và secret khỏi changelog |
| Metadata vận hành | Schema, table, column, tên service, đường dẫn nội bộ | Bảo vệ theo mức phân loại nội bộ; tránh công khai artifact |
| Thông tin lỗi | SQL statement, bind value, stack trace, driver exception | Giữ chi tiết ở nơi có quyền; thông báo chung ở kênh rộng hơn |
| Dấu vết release | Commit, changeset id, artifact digest, thời điểm triển khai | Có thể ghi để audit nhưng không kèm credential hoặc payload nhạy cảm |

### 2.1. Credential và dữ liệu trong SQL là hai vấn đề khác nhau

Password của datasource thường được dùng để mở kết nối; nó không phải một phần của câu DDL mà Liquibase sinh ra. Tuy nhiên, việc lưu password trong file cấu hình, truyền trên command line, bật debug hoặc in toàn bộ cấu hình có thể làm lộ nó.

Trong khi đó, SQL preview có thể chứa giá trị literal nếu changeset khai báo INSERT, UPDATE, loadData hoặc SQL thuần. Ví dụ:

~~~sql
INSERT INTO customer_contact (customer_id, email)
VALUES (10021, 'customer@example.invalid');
~~~

Ngay cả khi đây là dữ liệu minh họa, SQL tương tự với dữ liệu production có thể tiết lộ định danh cá nhân. Một file preview vì vậy cần được phân loại theo nội dung thực tế, không mặc định là “chỉ có DDL nên công khai được”.

### 2.2. Phân biệt secret với cấu hình không bí mật

Các giá trị như schema mặc định, changelog path, context hoặc label thường không phải secret. Chúng vẫn có thể tiết lộ cấu trúc nội bộ nhưng không cần xử lý giống password. Tách riêng hai loại giúp tránh ghi quá nhiều thông tin nhạy cảm vào nơi công khai mà vẫn giữ đủ metadata để review.

Một nguyên tắc hữu ích: **changelog mô tả thay đổi database; secret cung cấp quyền thực hiện thay đổi**. Không nhúng secret vào changelog chỉ để migration có thể chạy.

## 3. Những nguồn có thể làm lộ thông tin

Rà soát toàn bộ đường đi của thông tin, không chỉ dòng log do Liquibase trực tiếp ghi.

| Nguồn | Rủi ro thường gặp |
|---|---|
| Liquibase logger | Debug/trace ghi thêm SQL, tham số hoặc chi tiết lỗi |
| Spring Boot startup log | Bean/configuration exception, datasource error hoặc stack trace |
| CLI arguments | Password/URL/token xuất hiện trong shell history, process list hoặc audit |
| Defaults/properties file | File chứa password bị commit, backup hoặc cấp quyền quá rộng |
| Environment variables | Có thể bị đọc bởi process/user có quyền trên host hoặc lộ qua diagnostic dump |
| Changelog | Literal nhạy cảm, property substitution hoặc SQL chứa dữ liệu thật |
| SQL preview | DDL/DML, giá trị insert/update, tên object và logic nội bộ |
| Rollback SQL | Giá trị khôi phục, câu lệnh xóa hoặc nội dung dữ liệu trước đó |
| CI/CD console | Lệnh được in ra, environment dump, shell tracing hoặc exception |
| Build/deployment artifact | SQL, log, properties, report được lưu lâu hoặc chia sẻ rộng |
| Observability platform | Log được chuyển tiếp sang hệ thống có retention và quyền khác |
| Ticket/chat/support bundle | File debug được đính kèm mà không rà soát secret hoặc dữ liệu |

### 3.1. Secret có thể lộ qua nhiều bản sao

Một password từng xuất hiện trong console có thể tiếp tục tồn tại trong:

- Log tập trung và bản sao lưu log.
- Artifact của pipeline.
- Cache hoặc workspace của runner.
- Shell history, transcript và process monitoring.
- Ticket hỗ trợ hoặc ảnh chụp màn hình.
- File tạm được tạo khi sinh SQL preview.

Xóa dòng log trên giao diện không bảo đảm mọi bản sao đã biến mất. Khi secret đã bị lộ, cần đánh giá phạm vi lưu trữ và xoay credential thay vì chỉ xóa một file.

## 4. Không truyền credential trực tiếp qua command line

Một cách làm dễ mắc lỗi là đặt username/password trực tiếp trong lệnh:

~~~bash
liquibase --url=jdbc:postgresql://db-host:5432/orders \
  --username=orders_admin \
  --password=VerySecretValue \
  update
~~~

Ví dụ trên minh họa **cách không an toàn**. Giá trị có thể xuất hiện trong shell history, process list, CI command echo hoặc log của runner. Không dùng password thật theo cách này.

### 4.1. Dùng secret manager hoặc secret injection

Ưu tiên lấy credential từ secret manager của nền tảng hoặc cơ chế secret injection được tổ chức phê duyệt. Pipeline chỉ cấp secret cho đúng job, đúng environment và đúng thời gian cần thiết.

Ví dụ khái niệm:

~~~text
Secret manager
      |
      v
CI/CD job được cấp quyền theo environment
      |
      v
Credential được đưa vào process Liquibase
      |
      v
Liquibase kết nối database
      |
      v
Process kết thúc và quyền truy cập hết hiệu lực
~~~

Không ghi giá trị secret ra console để “xác nhận đã nhận được”. Chỉ kiểm tra biến đã được cấu hình bằng trạng thái có/không hoặc một health check không tiết lộ nội dung.

### 4.2. Environment variable không tự động an toàn tuyệt đối

Environment variable thường giảm nguy cơ lưu password trong shell history và command line, nhưng có thể bị lộ qua process diagnostics, crash dump, debug endpoint hoặc người dùng có quyền trên host. Cần bảo vệ runner, giới hạn quyền truy cập và tránh in toàn bộ environment.

Tên biến và cách Liquibase đọc biến môi trường phụ thuộc phiên bản/cấu hình. Một số CLI hiện đại hỗ trợ biến theo quy ước <code>LIQUIBASE_COMMAND_*</code>; cần kiểm tra tài liệu đúng phiên bản thay vì giả định mọi bản đều hỗ trợ giống nhau.

### 4.3. Defaults file và properties file

Liquibase có thể nhận cấu hình từ defaults/properties file. Nếu file chứa credential:

- Không commit vào repository.
- Cấp quyền đọc tối thiểu cho user chạy migration.
- Đặt trong thư mục bảo vệ hoặc mount tạm của job.
- Không upload vào artifact hoặc lưu vào cache.
- Dùng secret injection để tạo file nếu cần, rồi xóa theo chính sách runner.
- Không in nội dung file khi debug.

Ví dụ command chỉ tham chiếu file cấu hình:

~~~bash
liquibase --defaults-file=./secure/orders-production.properties validate
liquibase --defaults-file=./secure/orders-production.properties update
~~~

Ví dụ giả định file được cấp quyền phù hợp và không nằm trong source control. Chỉ đường dẫn file không làm nó an toàn; quyền filesystem, backup, retention và log vẫn cần được quản lý.

## 5. Không đưa secret vào changelog parameters

Liquibase hỗ trợ property substitution để tái sử dụng changelog. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-tenant-table
      author: platform
      changes:
        - createTable:
            schemaName: ${app.schema}
            tableName: tenant_config
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Property <code>app.schema</code> ở đây là tên schema, không phải secret. Có thể truyền giá trị theo môi trường nếu được kiểm soát và validate.

Không sử dụng property substitution để chèn password, API token, private key hoặc dữ liệu cá nhân vào câu SQL. Khi Liquibase thay property vào SQL, giá trị đã thay thế có thể xuất hiện trong SQL preview, log, exception hoặc lịch sử kiểm tra.

### 5.1. Chọn property phù hợp

| Property có thể chấp nhận trong changelog | Giá trị không nên đặt trong changelog |
|---|---|
| Schema/namespace đã được allowlist | Database password |
| Tên bảng hoặc prefix theo quy ước | Access token/API key |
| Context/label hoặc release marker | Private key/certificate secret |
| Giá trị cấu hình không nhạy cảm | Email/số điện thoại thật của khách hàng |
| Tham số định danh môi trường không bí mật | Dữ liệu cá nhân hoặc credential nhúng trong SQL |

Một property có tên chung như <code>app.schema</code> không cho biết nó có an toàn hay không. Review nguồn cấp và nơi giá trị được sử dụng.

### 5.2. Changelog không phải kho secret

Không lưu secret dưới dạng:

- Literal trong YAML/XML/JSON/SQL.
- Comment trong changelog.
- File CSV được loadData.
- Stored procedure body hoặc SQL function.
- Rollback block.
- Property mặc định trong file cấu hình được commit.

Nếu migration cần tạo một tài khoản hoặc credential mới, thiết kế provisioning bằng secret manager/DBA workflow phù hợp. Changelog có thể tạo cấu trúc quyền hoặc role theo policy, nhưng không nên nhúng password thật vào nội dung được version control.

## 6. Kiểm soát log level

Log level quyết định lượng thông tin được ghi. Tên logger và cách cấu hình có thể thay đổi theo phiên bản Liquibase, Spring Boot và logging backend.

| Mức log | Mục đích | Khuyến nghị |
|---|---|---|
| SEVERE/ERROR | Lỗi cần xử lý | Giữ thông tin đủ điều tra nhưng rà soát exception/SQL nhạy cảm |
| WARNING | Tình trạng bất thường | Tránh đưa payload hoặc credential vào message |
| INFO | Tiến trình, changeset và kết quả tổng quát | Thường phù hợp cho vận hành thường ngày |
| FINE/DEBUG | Chẩn đoán chi tiết | Chỉ bật có thời hạn và ở nơi có quyền hạn chế |
| TRACE | Dấu vết rất chi tiết | Tránh bật lâu dài trong production nếu chưa đánh giá dữ liệu được ghi |

Không mặc định DEBUG luôn in password; cũng không giả định log INFO không thể chứa thông tin nhạy cảm. Mức độ lộ phụ thuộc logger, exception, custom code, driver và cấu hình.

### 6.1. Spring Boot logging

Ví dụ cấu hình mức log tổng quát:

~~~yaml
logging:
  level:
    liquibase: INFO
    org.springframework.boot.autoconfigure.liquibase: INFO
~~~

Tên package/logger cụ thể phụ thuộc dependency và phiên bản. Hãy xác nhận logger thực tế trong ứng dụng. Không tăng toàn bộ root logger lên DEBUG chỉ để điều tra một lỗi migration.

### 6.2. CLI logging

CLI có tùy chọn log level và output format theo phiên bản. Trước khi bật mức chi tiết, hãy xác định:

- Log sẽ đi đâu: console, file, CI log hay log aggregator?
- Ai có thể đọc?
- Có in SQL, parameter, JDBC URL hoặc exception detail không?
- Log có được upload làm artifact không?
- Thời gian bật debug và thời điểm tắt đã được ghi nhận chưa?

Nếu cần debug production, nên giới hạn vào một lần chạy/job, thu thập ở nơi có quyền phù hợp và tắt ngay sau khi có đủ dữ liệu.

## 7. Che dữ liệu trong log: thiết kế ở nguồn trước

Redaction là lớp bảo vệ bổ sung, không phải lý do để ghi secret vào log. Cách an toàn nhất là tránh đưa secret/payload nhạy cảm vào thông điệp ngay từ đầu.

### 7.1. Không log object cấu hình nguyên khối

Tránh:

~~~java
log.debug("Liquibase configuration: {}", liquibaseProperties);
log.info("Datasource: {}", dataSourceProperties);
~~~

Object cấu hình có thể chứa URL, username, password hoặc tham số khác tùy implementation. Thay vào đó, log các trường không nhạy cảm đã chọn:

~~~java
log.info(
    "Starting schema migration: service={}, changelog={}, environment={}",
    serviceName,
    changeLogPath,
    environmentName
);
~~~

Không log password, token hoặc toàn bộ datasource object. Nếu cần xác định đích, dùng tên connection alias đã được phê duyệt hoặc database identifier đã phân loại.

### 7.2. Không log SQL parameter values mặc định

Một câu truy vấn có thể an toàn về mặt cấu trúc nhưng bind parameter chứa email, số tài khoản hoặc thông tin cá nhân. Nếu cần theo dõi query, ưu tiên ghi:

- Tên changeset hoặc operation.
- Loại thao tác (DDL/DML).
- Thời gian thực thi.
- Số hàng ảnh hưởng nếu không nhạy cảm.
- Mã lỗi đã chuẩn hóa.

Không ghi toàn bộ bind values hoặc row contents vào log vận hành. Nếu điều tra cần một giá trị cụ thể, dùng quy trình truy cập dữ liệu có audit.

### 7.3. Redaction theo schema dữ liệu

Nếu log framework có filter/masking, định nghĩa trường nhạy cảm theo tên và ngữ cảnh, ví dụ password, token, authorization, email hoặc account number. Tuy nhiên:

- Redaction dựa trên regex có thể bỏ sót encoding hoặc format khác.
- Một secret có thể xuất hiện trong exception message không theo key đã biết.
- SQL có thể chứa literal không có tên trường.
- Stack trace hoặc nested cause có thể lặp lại nội dung nhạy cảm.

Vì vậy, kiểm tra output thực tế sau masking và giữ nguyên tắc không log payload nhạy cảm ngay từ đầu.

## 8. SQL preview: hữu ích nhưng không phải artifact công khai

Lệnh xem trước SQL cho phép review DDL/DML mà Liquibase dự kiến thực thi. Tùy phiên bản, có thể dùng lệnh <code>update-sql</code> hoặc cách viết tương đương như <code>updateSQL</code>. Ví dụ:

~~~bash
liquibase --defaults-file=./secure/orders.properties update-sql
~~~

SQL preview giúp:

- Xem object/schema đích.
- Phát hiện lệnh DROP/ALTER/UPDATE ngoài dự kiến.
- Review thứ tự changeset và dependency.
- Kiểm tra SQL đặc thù DBMS.
- Đánh giá khả năng lock, thời gian và tác động dữ liệu.

Nhưng file preview cũng có thể tiết lộ:

- Literal được khai báo trong changeset.
- Giá trị mapping hoặc dữ liệu import.
- Tên schema/table/column nội bộ.
- Logic nghiệp vụ hoặc điều kiện truy vấn.
- Câu lệnh rollback/restore và cấu trúc hệ thống.

**Không đưa SQL preview lên artifact công khai hoặc log có quyền truy cập rộng theo mặc định.** Phân loại theo nội dung và chỉ chia sẻ cho reviewer có nhu cầu.

### 8.1. SQL preview có thể chứa dữ liệu thật

Ví dụ changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-reference-value
      author: platform
      changes:
        - insert:
            tableName: system_setting
            columns:
              - column:
                  name: setting_key
                  value: support_contact
              - column:
                  name: setting_value
                  value: support@example.invalid
~~~

Nếu dữ liệu thực được đưa vào các change tương tự, SQL preview có thể thể hiện literal đó. Không dùng dữ liệu production cá nhân trong changelog chỉ để tiện seed hoặc migration. Nếu cần chuyển dữ liệu nhạy cảm, dùng một quy trình dữ liệu có kiểm soát quyền, log và audit riêng.

### 8.2. Preview không xác nhận migration đã chạy

SQL preview mô tả SQL dự kiến theo changelog, cấu hình và trạng thái được Liquibase sử dụng khi tạo output. Nó không chứng minh:

- SQL đã thực thi thành công.
- Database production có đúng trạng thái tại thời điểm thực thi.
- Lock và transaction sẽ diễn ra như dự kiến.
- Dữ liệu sau migration đáp ứng nghiệp vụ.
- Không có writer khác thay đổi dữ liệu sau preview.

Hãy dùng preview để review, sau đó chạy update theo cùng artifact/parameters và xác minh kết quả.

## 9. Bảo vệ file SQL preview và rollback SQL

Khi cần lưu SQL preview thành file, coi file đó là artifact triển khai có kiểm soát:

- Ghi vào workspace tạm có quyền đọc hạn chế.
- Không đặt trong thư mục public, web root hoặc source repository.
- Không upload mặc định vào artifact dùng chung cho mọi project.
- Nếu cần review, cấp quyền cho nhóm reviewer phù hợp và có thời hạn.
- Đặt retention ngắn theo policy; xóa bản sao tạm sau khi hết nhu cầu.
- Không gửi file qua chat/email không được phê duyệt.
- Bảo vệ bản backup và log nếu pipeline tự động tạo chúng.

Rollback SQL có thể chứa dữ liệu cũ được INSERT lại, câu lệnh phục hồi hoặc thao tác xóa. Vì vậy, nó có thể nhạy cảm ngang hoặc hơn update SQL.

### 9.1. Ví dụ quy trình lưu preview an toàn

~~~text
Liquibase update-sql
        |
        v
Output vào file tạm được bảo vệ
        |
        v
Scan secret / review nội dung
        |
        v
Gán quyền reviewer theo release
        |
        v
Review và phê duyệt
        |
        v
Lưu kết quả phê duyệt, không giữ file lâu hơn cần thiết
~~~

Nếu hệ thống cần giữ SQL preview để audit, hãy lưu trong kho artifact có access control, encryption, audit log và retention policy. Không nhúng nội dung SQL vào thông báo release rộng; có thể lưu tham chiếu tới artifact có quyền truy cập.

### 9.2. Băm artifact và tính toàn vẹn

Có thể lưu hash của file preview cùng release manifest để phát hiện file bị thay đổi sau review. Hash chứng minh tính toàn vẹn so với file đã băm, nhưng không chứng minh nội dung không chứa secret hoặc SQL an toàn. Cần cả review nội dung và kiểm soát quyền.

## 10. CI/CD: che secret và hạn chế output

Pipeline thường có các bước validate, status, update-sql, approval và update. Mỗi bước cần có quy tắc output:

| Bước | Thông tin nên lưu | Thông tin cần tránh |
|---|---|---|
| Resolve secrets | Secret reference/version và trạng thái cấp thành công | Giá trị secret hoặc environment dump |
| Validate | Kết quả, changelog path, version công cụ | Toàn bộ config chứa credential |
| Status | Changeset pending và đích đã phân loại | URL/password/token nguyên văn |
| SQL preview | File artifact riêng có quyền hạn chế | In toàn bộ SQL vào console công khai |
| Approval | Reviewer, thời điểm, artifact digest | Đính kèm payload dữ liệu nhạy cảm không cần thiết |
| Update | Changeset id, trạng thái, thời lượng, lỗi đã chuẩn hóa | Bind values, secret hoặc full environment |
| Verify | Kết quả schema/data checks và release id | Bản ghi cá nhân đầy đủ hoặc dữ liệu khách hàng |

### 10.1. Tắt shell tracing và command echo khi xử lý secret

Một số shell/CI runner có chế độ in từng lệnh trước khi chạy (ví dụ shell tracing). Nếu command chứa secret, giá trị có thể bị in dù hệ thống có mask một phần. Không bật trace quanh đoạn lấy/đưa secret vào process. Không giả định masking của CI là hoàn hảo; secret có thể bị encode, chia nhỏ hoặc xuất hiện trong exception.

### 10.2. Không in toàn bộ environment

Tránh lệnh diagnostic như <code>env</code>, <code>printenv</code> hoặc dump toàn bộ process configuration trong job production. Nếu cần debug, chỉ in tên biến không nhạy cảm hoặc trạng thái đã được lọc. Cùng nguyên tắc áp dụng cho Spring Boot actuator/configuration report: giới hạn endpoint và masking theo cấu hình bảo mật.

### 10.3. Giữ preview và update cùng một artifact

SQL preview chỉ có giá trị review nếu nội dung được sinh từ cùng changelog, parameters, DBMS và artifact sẽ thực thi. Pipeline nên lưu:

- Commit/release identifier.
- Digest của image hoặc gói chứa changelog.
- Liquibase version và JDBC driver.
- Database target alias, schema scope và DBMS/version.
- Context/label và parameters không bí mật.
- Hash của SQL preview.
- Người phê duyệt và thời điểm.

Không cần ghi credential vào manifest. Nếu artifact chứa SQL có dữ liệu nhạy cảm, manifest chỉ nên tham chiếu tới artifact được bảo vệ.

## 11. Spring Boot: bảo vệ log startup và datasource

Khi Liquibase chạy lúc Spring Boot startup, thông tin có thể đi qua cả logger của Liquibase, Spring Framework, JDBC driver và connection pool. Một lỗi kết nối có thể kèm URL, hostname, database hoặc stack trace.

Các nguyên tắc:

- Không log toàn bộ <code>Environment</code>, datasource properties hoặc LiquibaseProperties.
- Dùng secret reference/secret injection thay vì ghi password vào application.yaml.
- Giữ log Liquibase ở INFO hoặc mức phù hợp cho production; chỉ bật DEBUG có thời hạn.
- Hạn chế quyền đọc log startup và log aggregator.
- Kiểm tra exception của driver trước khi gửi ra hệ thống log rộng.
- Không bật actuator/configuration endpoint công khai nếu có thể lộ property.
- Tách runtime user và migration user nếu kiến trúc cho phép.

Ví dụ cấu hình không chứa secret:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_runtime
    password: ${ORDERS_DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml

logging:
  level:
    liquibase: INFO
~~~

Ví dụ dùng placeholder minh họa cơ chế cấu hình của Spring; cách resolve secret phải được thiết lập bởi môi trường triển khai. Không commit file có giá trị password thật. Biến môi trường cũng cần được bảo vệ theo quyền host/runner.

### 11.1. Startup failure không phải lý do bật debug vô thời hạn

Khi Liquibase lỗi:

1. Lưu changeset id, release id, DBMS/version và loại lỗi.
2. Kiểm tra chi tiết trong log có quyền hạn phù hợp.
3. Nếu cần tăng log level, giới hạn một lần chạy và một khoảng thời gian.
4. Redact thông tin nhạy cảm trước khi gửi ticket/support.
5. Khôi phục mức log production sau khi điều tra.

Không gửi toàn bộ startup log ra kênh công khai nếu chưa kiểm tra nội dung.

## 12. Changelog và SQL thuần: tránh literal nhạy cảm

### 12.1. DML trong changeset

Các change type như insert, update, loadData, loadUpdateData hoặc SQL thuần có thể làm literal xuất hiện trong SQL preview. Trước khi commit:

- Kiểm tra file CSV/JSON/SQL đi kèm.
- Dùng dữ liệu giả cho test.
- Không seed password/token thật.
- Nếu cần dữ liệu production, dùng quy trình ETL riêng với quyền và audit.
- Không đưa bản ghi cá nhân vào rollback block.

### 12.2. Stored procedure và function

SQL tạo function/procedure có thể chứa literal, URL nội bộ, logic nhạy cảm hoặc credential bị hardcode. Review cả body, comment và chuỗi dynamic SQL. Không coi việc nội dung nằm trong code database là an toàn hơn việc đặt trong application code.

### 12.3. SQL comments và error messages

Comment trong SQL preview có thể được lưu trong artifact. Tránh ghi token, thông tin khách hàng hoặc chi tiết hạ tầng không cần thiết vào comment. Exception do DBMS trả về cũng có thể chứa một phần SQL; hãy xử lý log ở nơi phù hợp.

## 13. Quyền truy cập và retention cho log/artifact

Một file SQL preview nên có owner, mục đích, phạm vi truy cập và thời gian lưu rõ ràng.

| Kiểm soát | Cách áp dụng |
|---|---|
| Least privilege | Chỉ migration owner và reviewer được chỉ định có quyền đọc artifact |
| Encryption at rest | Dùng kho artifact hỗ trợ mã hóa theo policy |
| Encryption in transit | Truyền qua kênh được bảo vệ |
| Access audit | Ghi ai xem/tải file và thời điểm |
| Retention | Giữ theo thời hạn audit cần thiết; xóa bản tạm sớm |
| Immutable approval record | Lưu artifact digest và phê duyệt để chứng minh nội dung được review |
| Segregation | Không dùng chung quyền đọc log ứng dụng với quyền đọc dữ liệu migration nhạy cảm |

Không giữ log vô thời hạn “để phòng khi cần”. Retention quá dài làm tăng lượng dữ liệu có thể bị lộ. Ngược lại, xóa quá sớm có thể làm mất bằng chứng điều tra. Cần chính sách retention được owner bảo mật/vận hành phê duyệt.

### 13.1. Chia sẻ cho support hoặc reviewer

Trước khi đính kèm log/SQL vào ticket:

1. Xác định người nhận có quyền theo môi trường không.
2. Tìm password, token, PII, literal và hostname nội bộ.
3. Redact nội dung không cần thiết.
4. Nếu cần file nguyên bản, gửi qua kho artifact có kiểm soát.
5. Ghi tham chiếu và thời hạn truy cập, không tạo bản sao ngoài policy.

Một ảnh chụp màn hình console cũng có thể lộ command line, username, URL hoặc dữ liệu. Rà soát trước khi chia sẻ.

## 14. Xử lý khi phát hiện secret đã bị lộ

Nếu password/token xuất hiện trong log, command line, SQL preview hoặc artifact:

1. **Cô lập nguồn lộ:** hạn chế quyền truy cập artifact/log, dừng chia sẻ link và vô hiệu hóa public access.
2. **Xác định loại secret:** database password, token, key hay dữ liệu cá nhân; xác định hệ thống và principal liên quan.
3. **Đánh giá phạm vi:** nơi lưu, thời gian tồn tại, ai có thể truy cập, bản sao và backup.
4. **Xoay hoặc thu hồi secret:** thực hiện theo quy trình của hệ thống sở hữu credential; cập nhật secret store và các job phụ thuộc.
5. **Kiểm tra truy cập:** xem audit log database/CI/CD để phát hiện sử dụng bất thường.
6. **Loại bỏ bản sao theo policy:** xử lý artifact, workspace, ticket và log aggregator; lưu bằng chứng cần thiết theo quy định.
7. **Sửa nguồn gốc:** loại secret khỏi changelog/command/logging code và thêm kiểm tra ngăn tái diễn.
8. **Xác minh:** chạy migration test bằng credential mới, kiểm tra output không còn secret.

Không chỉ xóa file mà không xoay credential nếu secret có thể đã bị người khác đọc. Nếu là dữ liệu cá nhân, cần kích hoạt quy trình incident/privacy tương ứng của tổ chức.

### 14.1. Đánh giá ảnh hưởng sau lộ

| Câu hỏi | Bằng chứng cần tìm |
|---|---|
| Secret xuất hiện ở đâu? | CI console, file, shell history, artifact, log aggregator |
| Có thể đọc bởi ai? | Access policy, audit download/view, quyền workspace |
| Còn hiệu lực không? | Secret rotation/revocation status |
| Có sử dụng bất thường không? | Database audit, login history, network logs |
| Có bản sao nào khác? | Cache, backup, ticket, support bundle |
| Nguồn lộ đã được sửa chưa? | Pipeline config, changelog, logger test và review |

## 15. Ví dụ pipeline an toàn ở mức khái niệm

~~~text
1. Resolve secret theo identity của job
                 |
                 v
2. Kiểm tra changelog và parameters không chứa secret
                 |
                 v
3. Validate + status
                 |
                 v
4. Sinh SQL preview vào kho tạm được bảo vệ
                 |
                 v
5. Scan / review nội dung + approval
                 |
                 v
6. Thực thi update bằng cùng artifact/parameters
                 |
                 v
7. Verify schema và DATABASECHANGELOG
                 |
                 v
8. Lưu audit metadata + digest, áp retention cho preview
                 |
                 v
9. Thu hồi secret khỏi job và dọn workspace tạm
~~~

### 15.1. Những gì nên xuất ra console

Ví dụ output tối giản:

~~~text
Migration release: orders-2026.11
Target alias: orders-production
Changelog: db/changelog/db.changelog-master.yaml
Liquibase version: <verified-version>
Validation: PASSED
Pending changesets: 2
SQL preview: stored in restricted artifact
Approval: PASSED
Update: COMPLETED
Verification: PASSED
~~~

Đây là mẫu log khái niệm. Không in URL đầy đủ, password, token, bind values hoặc toàn bộ SQL ra console. Nếu cần truy cập SQL preview, dùng artifact reference được kiểm soát.

### 15.2. Scan secret trước khi publish artifact

Có thể bổ sung secret scanning cho:

- Changelog YAML/XML/JSON/SQL.
- File dữ liệu loadData.
- SQL preview và rollback SQL.
- CI log và artifact manifest.
- File cấu hình được tạo trong workspace.

Secret scanning có thể phát hiện mẫu token/password phổ biến nhưng có false negative và false positive. Không xem scan pass là bằng chứng tuyệt đối; review nguồn dữ liệu và policy vẫn cần thiết.

## 16. Checklist review changelog và SQL preview

Trước khi approve:

- [ ] Không có password, token, private key hoặc credential literal trong changelog.
- [ ] Không có dữ liệu cá nhân/production không cần thiết trong INSERT, UPDATE, loadData hoặc SQL thuần.
- [ ] Property substitution chỉ dùng giá trị được phân loại và kiểm soát.
- [ ] SQL preview được sinh từ đúng artifact, DBMS, schema, context/label và parameters.
- [ ] Đã xem các câu DDL/DML destructive và literal được sinh ra.
- [ ] Rollback SQL được kiểm tra cùng tiêu chuẩn bảo mật.
- [ ] File preview được lưu trong kho hạn chế quyền, không public.
- [ ] Artifact có retention và access audit.
- [ ] Log level phù hợp production; debug/trace không bật vô thời hạn.
- [ ] Logger không in toàn bộ datasource/configuration/environment.
- [ ] Command line và shell trace không làm lộ secret.
- [ ] CI/CD masking được kiểm tra bằng test; không dựa vào masking như lớp bảo vệ duy nhất.
- [ ] Runtime/migration credentials được tách hoặc giới hạn quyền phù hợp.
- [ ] Có quy trình xoay secret và incident response.
- [ ] Sau deploy đã xác minh output và dọn file tạm theo policy.

## 17. Những lỗi thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Truyền password bằng --password | Lộ trong history/process/log | Dùng secret injection hoặc file cấu hình bảo vệ |
| Commit defaults file có credential | Secret tồn tại trong Git history và clone | Đưa secret ra secret manager; thu hồi credential đã lộ |
| In toàn bộ environment khi debug | Lộ nhiều biến secret cùng lúc | Chỉ log các trường allowlist |
| Bật DEBUG/TRACE lâu dài | Log quá nhiều dữ liệu và tăng chi phí | Giới hạn phạm vi/thời gian, kiểm tra output |
| Cho rằng SQL preview không nhạy cảm | Lộ literal hoặc dữ liệu migration | Review và phân loại file preview |
| Upload preview vào artifact công khai | Người ngoài phạm vi có thể đọc SQL | Kho riêng, quyền hạn chế, retention |
| Đưa token vào changelog parameter | Giá trị có thể xuất hiện trong SQL/log | Không dùng changelog làm kho secret |
| Dựa hoàn toàn vào CI masking | Encoding/exception có thể vượt mask | Ngăn secret đi vào output ngay từ nguồn |
| Log exception nguyên bản ra kênh rộng | Có thể chứa SQL, URL hoặc bind values | Chuẩn hóa thông báo, giữ chi tiết ở nơi hạn chế |
| Dùng dữ liệu production trong loadData | Lộ PII trong repository và preview | Dữ liệu giả hoặc pipeline dữ liệu chuyên biệt |
| Lưu preview/rollback SQL vô thời hạn | Tăng thời gian và phạm vi phơi lộ | Retention theo policy và dọn bản tạm |
| Chỉ xóa artifact sau sự cố | Credential có thể đã bị đọc | Xoay/thu hồi secret và điều tra bản sao |
| Không scan file CSV/SQL đi kèm | Secret nằm ngoài YAML chính | Scan toàn bộ input và artifact liên quan |
| Dùng một tài khoản superuser cho runtime và migration | Tăng hậu quả khi credential bị lộ | Tách identity và least privilege |

## 18. Bài thực hành

### Bài A — Kiểm tra command line và secret handling

Trong môi trường local cô lập:

1. Cấu hình Liquibase bằng một credential thử nghiệm.
2. Quan sát cách truyền qua command line và xác định nơi có thể bị lưu.
3. Chuyển sang secret injection hoặc defaults file có quyền hạn chế.
4. Kiểm tra console, process diagnostics và shell history theo policy môi trường.
5. Xác nhận không có giá trị secret trong output được lưu.

Không dùng password production cho bài thực hành và không xuất giá trị thật ra log để kiểm tra.

### Bài B — SQL preview có literal

1. Tạo changeset INSERT một giá trị giả.
2. Sinh update SQL preview.
3. Xác định literal nào xuất hiện trong file.
4. Thử thay bằng dữ liệu giả và kiểm tra lại.
5. Lưu preview trong thư mục/kho có quyền hạn chế.
6. Xác minh artifact không được public và có retention phù hợp.

Mục tiêu: hiểu SQL preview có thể chứa nội dung từ changeset và dữ liệu.

### Bài C — Log level và redaction

1. Chạy Liquibase ở INFO.
2. Bật DEBUG trong môi trường test có dữ liệu giả.
3. So sánh lượng thông tin hai mức log.
4. Kiểm tra logger của Spring Boot, Liquibase và JDBC driver.
5. Thử filter/redaction và xác minh nested exception không làm lộ giá trị.
6. Trả mức log về cấu hình production.

### Bài D — Incident response

Giả lập một artifact test chứa token giả:

1. Hạn chế quyền truy cập artifact.
2. Thu hồi token thử nghiệm.
3. Tìm các bản sao trong workspace/log/ticket giả lập.
4. Sửa pipeline để không in token.
5. Chạy lại scan và xác minh output đã sạch.

Mục tiêu: luyện quy trình xử lý nguồn lộ, xoay secret và phòng ngừa tái diễn.

## 19. Ghi nhớ

Log và SQL xem trước là bằng chứng quan trọng để review và vận hành Liquibase, nhưng chúng có thể chứa credential, literal, dữ liệu nghiệp vụ và metadata nội bộ. **Không đưa secret vào changelog, command line hoặc log; không mặc định SQL preview là artifact công khai.** Dùng secret manager/injection, quyền tối thiểu, log level phù hợp, output allowlist, artifact access control và retention có chủ đích.

Khi cần điều tra, tăng mức log có thời hạn và thu thập chi tiết ở nơi có quyền phù hợp. Khi sinh update/rollback SQL, review nội dung và bảo vệ file như một artifact triển khai. Nếu secret đã lộ, hạn chế truy cập, xoay/thu hồi credential, tìm bản sao và sửa nguồn gốc. Kết hợp changelog ổn định, precondition, checksum, lịch sử DATABASECHANGELOG và kiểm soát output trong Spring Boot/CI/CD giúp migration có thể truy vết mà không làm lộ thông tin vượt nhu cầu.
