# Kiểm tra cấu hình hiệu lực trước khi thực thi Liquibase

## 1. Vì sao phải kiểm tra cấu hình hiệu lực?

Một changelog Liquibase đúng vẫn có thể gây sự cố nếu được chạy với cấu hình sai. Ví dụ, nhóm phát triển chuẩn bị migration cho staging nhưng một biến môi trường trong runner trỏ tới production; hoặc kết nối đúng database nhưng default schema lại là schema của tenant khác. Trong cả hai trường hợp, changeset không có lỗi cú pháp nhưng hậu quả có thể nghiêm trọng.

**Cấu hình hiệu lực (effective configuration)** là tập giá trị mà tiến trình Liquibase **thực sự sử dụng tại thời điểm thực thi**, sau khi kết hợp tệp cấu hình, tham số dòng lệnh, biến môi trường, Java system properties, giá trị mặc định và cơ chế tích hợp. Cấu hình nhìn thấy trong một tệp chưa chắc là cấu hình cuối cùng.

Bài học thuộc chương **Cấu hình** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, nơi người học nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Mục tiêu ở đây là xác nhận **Liquibase sẽ kết nối tới đâu, đọc changelog nào, chọn changeset nào và chạy bằng quyền nào** trước khi cho phép lệnh thay đổi cơ sở dữ liệu.

Sau bài học, người học cần:

- Phân biệt giá trị được khai báo và giá trị đã được resolve ở runtime.
- Xác định nguồn có thể ghi đè cấu hình khi dùng Liquibase CLI, Spring Boot và CI/CD.
- Kiểm chứng JDBC URL, database/catalog, schema, changelog, context, label, tham số và tài khoản migration.
- Dùng các thao tác kiểm tra như <code>validate</code>, <code>status</code>, <code>update-sql</code> trước <code>update</code>.
- Xây dựng điều kiện dừng khi cấu hình hoặc SQL dự kiến khác kế hoạch triển khai.

## 2. Cấu hình hiệu lực được hình thành như thế nào?

Liquibase cần các thông tin kết nối, vị trí changelog, bộ lọc changeset và tùy chọn hoạt động. Chúng có thể đến từ nhiều nguồn:

| Nguồn | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|
| Tham số CLI | URL, username, changelog, context filter truyền khi gọi lệnh | Script truyền giá trị khác với tệp cấu hình |
| Tệp defaults/properties | Tệp chọn bằng <code>--defaults-file</code> | Dùng nhầm tệp của môi trường khác; đường dẫn tương đối sai |
| Biến môi trường | Biến Liquibase hoặc biến do wrapper chuyển thành tham số | Giá trị cũ kế thừa từ shell, máy build hoặc container |
| Java system properties | Thuộc tính cấp cho JVM | Ghi đè hoặc bổ sung giá trị ngoài tệp defaults |
| Spring Boot | <code>spring.liquibase.*</code>, datasource, active profiles | Giá trị cuối do Spring resolve khác file <code>application.yml</code> |
| Plugin/wrapper | Maven, Gradle, script triển khai | Plugin có tệp cấu hình và quy tắc ưu tiên riêng |
| Secret manager / CI/CD | Credentials và endpoint do job cung cấp | Secret cấp sai môi trường hoặc sai vai trò |
| Giá trị mặc định | Schema, tìm kiếm tài nguyên, hành vi khi không truyền filter | Mặc định không giống giữa các phiên bản/cách tích hợp |

Trong các phiên bản Liquibase CLI phổ biến, tham số dòng lệnh có thể ghi đè giá trị cùng tên lấy từ nguồn ưu tiên thấp hơn. Tuy nhiên, **không tự suy ra một thứ tự ưu tiên duy nhất áp dụng cho tất cả phiên bản, plugin và Spring Boot**. Cần đọc trợ giúp/tài liệu của phiên bản công cụ mà dự án thực sự đóng gói, đồng thời kiểm chứng đích kết nối.

Ví dụ một tình huống cần cảnh giác:

| Thành phần | Giá trị |
|---|---|
| Tệp defaults dự định sử dụng | <code>jdbc:postgresql://staging-db:5432/orders</code> |
| Biến môi trường runner đang giữ | <code>jdbc:postgresql://prod-db:5432/orders</code> |
| Lệnh CLI | Không truyền URL tường minh |
| Rủi ro | Nếu biến môi trường thắng tệp defaults, migration sẽ hướng tới production |
| Bằng chứng bắt buộc | Nguồn giá trị cuối cùng, tên database/role thực tế và SQL dự kiến |

Vì vậy, kiểm tra tệp defaults rồi nhìn thấy chữ *staging* là chưa đủ. Cần đối chiếu toàn bộ đường đi từ cấu hình tới kết nối mà tiến trình sử dụng.

### 2.1. Bốn câu hỏi chính

1. **Chạy ở đâu?** Đúng hostname, port, database/catalog, schema nghiệp vụ và schema chứa bảng lịch sử chưa?
2. **Chạy cái gì?** Changelog, chuỗi include, contexts, labels và changelog parameters có chọn đúng thay đổi dự kiến chưa?
3. **Chạy bằng ai?** Tài khoản migration có đúng vai trò và phạm vi quyền được cấp không?
4. **Chạy bằng cơ chế nào?** CLI, CI/CD job hay Spring Boot auto-run? Có nguy cơ nhiều nơi cùng thực hiện migration không?

Nếu chưa xác minh được một câu trả lời quan trọng, không nên thực hiện <code>update</code>.

## 3. Những giá trị phải đối chiếu

Một preflight đáng tin cậy so sánh ba lớp thông tin: **giá trị mong đợi**, **giá trị cấp cho tiến trình** và **bằng chứng thực tế**.

| Nhóm | Trường hoặc cấu hình | Vì sao phải kiểm tra |
|---|---|---|
| Đích kết nối | JDBC URL, host, port, database/catalog | Quyết định cơ sở dữ liệu bị tác động |
| Vai trò | Username, cơ chế xác thực, quyền DDL/DML | Quyết định khả năng thao tác trên đối tượng |
| Schema nghiệp vụ | Default schema/catalog, schema ghi trong SQL | Đảm bảo bảng, chỉ mục, ràng buộc được tạo đúng nơi |
| Schema Liquibase | Liquibase schema/catalog, tên bảng lịch sử và bảng khóa | Quyết định Liquibase tìm/gửi lịch sử ở đâu |
| Changelog | Changelog gốc, search path, include, logicalFilePath | Xác định tập changeset và định danh lịch sử |
| Lọc changeset | Context filter, label filter | Có thể chọn thiếu hoặc thừa migration |
| Tham số thay thế | Changelog parameters, biến dùng trong SQL | Có thể làm đổi tên schema/bảng hoặc nội dung câu lệnh |
| Runtime | Liquibase version, JDBC driver, DBMS version | Ảnh hưởng cú pháp, khả năng hỗ trợ và mặc định |
| Thời điểm chạy | Auto-run, job riêng, nhiều instance | Ảnh hưởng startup, khóa và kiểm soát triển khai |

**Default schema** thường là schema đích của đối tượng nghiệp vụ nếu change không chỉ rõ schema. **Liquibase schema** là schema đặt các bảng theo dõi lịch sử như <code>DATABASECHANGELOG</code> và <code>DATABASECHANGELOGLOCK</code> khi được cấu hình riêng. Hai schema có thể trùng hoặc khác nhau.

Cùng một database có thể chứa nhiều schema hay tenant. Vì vậy, việc URL đúng chưa chứng minh đối tượng sẽ được tạo hoặc cập nhật đúng chỗ.

## 4. Quy trình kiểm tra an toàn bằng Liquibase CLI

Các ví dụ sau dùng PostgreSQL và dữ liệu giả lập. Người học cần kiểm tra cú pháp CLI của phiên bản đã cố định trong dự án vì tên tùy chọn hoặc cách sắp xếp tham số có thể khác nhau giữa các phiên bản.

### 4.1. Xác định ngữ cảnh thực thi

Trước tiên hãy ghi nhận phiên bản Liquibase, JDBC driver, thư mục làm việc, đường dẫn tệp defaults, artifact chứa changelog và môi trường đích.

~~~bash
liquibase --version
liquibase --help
~~~

Kiểm tra job/runner đang thực sự gọi bản Liquibase nào. Không suy từ bản cài trên máy lập trình viên rằng CI cũng dùng bản đó. Nếu dùng đường dẫn tương đối, cần biết chúng được resolve theo thư mục làm việc hoặc cơ chế tìm tài nguyên nào.

### 4.2. Kiểm tra tệp defaults và nguồn ghi đè

Ví dụ tệp <code>config/liquibase-staging.properties</code>:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://staging-db:5432/orders
username=liquibase_runner
defaultSchemaName=app
liquibaseSchemaName=liquibase_meta
~~~

Tệp minh họa không chứa mật khẩu. Trong dự án thật, mật khẩu và các secret phải được cấp bằng kênh bảo mật, tránh commit vào repository hoặc đưa trực tiếp vào lệnh có thể bị lưu trong shell history.

Kiểm tra theo thứ tự:

1. Lệnh đã truyền đúng <code>--defaults-file</code> chưa? Đường dẫn trỏ tới tệp nào khi chạy ở máy CI?
2. Có tham số CLI hoặc system property nào ghi đè URL, changelog, username, schema hay không?
3. Có biến môi trường Liquibase hoặc biến của wrapper script được kế thừa ngoài dự kiến không?
4. Changelog gốc và các tệp include có tồn tại trong artifact, đúng đường dẫn tìm tài nguyên không?
5. Giá trị được cấp cho tiến trình có khớp với manifest môi trường không?

Ở nhiều phiên bản Liquibase hiện đại, CLI có biến như <code>LIQUIBASE_COMMAND_URL</code> và <code>LIQUIBASE_COMMAND_CHANGELOG_FILE</code>. Cần kiểm tra tên biến chính xác theo phiên bản, kể cả biến của hệ thống build chuyển thành CLI argument. Việc không thấy biến trong tệp properties không có nghĩa là tiến trình không sử dụng nó.

### 4.3. Validate changelog

~~~bash
liquibase --defaults-file=./config/liquibase-staging.properties validate
~~~

<code>validate</code> hỗ trợ phát hiện lỗi định nghĩa và cấu trúc changelog trong phạm vi mà phiên bản Liquibase kiểm tra. Cần đọc mã thoát và lỗi/cảnh báo.

**Validate thành công không chứng minh** rằng URL đúng môi trường, tài khoản có quyền thực hiện mọi DDL, tất cả precondition chắc chắn đạt, hay thay đổi dữ liệu sẽ an toàn với quy mô production.

### 4.4. Xem danh sách changeset chưa triển khai

~~~bash
liquibase --defaults-file=./config/liquibase-staging.properties status --verbose
~~~

<code>status</code> đối chiếu changelog với lịch sử trên database đang kết nối. Hãy hỏi:

- Số lượng và định danh changeset chờ chạy có phù hợp release không?
- Có changeset không thuộc phạm vi phát hành không?
- Có thay đổi mong đợi nhưng bị loại do contexts/labels hoặc changelog chưa include không?
- Có dấu hiệu đổi id, author, đường dẫn changelog khiến Liquibase nhận diện changeset là mới không?

Status không mô phỏng đầy đủ precondition và cũng không bảo đảm SQL thực thi thành công. Nếu môi trường chưa từng chạy Liquibase, bảng lịch sử có thể chưa tồn tại; không được tự tạo/sửa lịch sử để ép kết quả kiểm tra.

### 4.5. Sinh SQL dự kiến

~~~bash
liquibase --defaults-file=./config/liquibase-staging.properties update-sql
~~~

Một số tài liệu/công cụ cũ sử dụng tên <code>updateSQL</code>; hãy dùng dạng được hỗ trợ trong phiên bản đang chạy. Mục đích ở đây là xem trước SQL, chưa thực hiện cập nhật schema.

Cần review:

- Schema và tên đối tượng thực tế được nhắc tới.
- Câu lệnh DROP, chuyển kiểu, NOT NULL, thêm ràng buộc hoặc cập nhật số lượng lớn bản ghi.
- Thứ tự tạo bảng, chỉ mục, khóa ngoại và chuyển đổi dữ liệu.
- Tác động khóa, thời gian chạy, transaction và yêu cầu quyền theo DBMS.
- Các SQL phụ thuộc dữ liệu thực tế hoặc precondition, có thể biến đổi vào thời điểm update.

SQL preview chỉ phản ánh cấu hình và trạng thái tại lúc sinh. Nó **không phải bảo đảm** rằng update thực tế sẽ thành công hoặc rollback được mọi thay đổi. Nếu changelog, filter, kết nối hoặc dữ liệu thay đổi sau preview thì phải đánh giá lại.

### 4.6. Xác minh danh tính kết nối trên database

Với PostgreSQL, dùng phiên kết nối có cùng thông tin với migration job để thực hiện truy vấn chỉ đọc:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema()   AS active_schema,
    current_user       AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port;
~~~

So sánh kết quả với database, schema và vai trò đã được phê duyệt. Trường địa chỉ máy chủ có thể là NULL trong một số kiểu kết nối như Unix socket; khi đó cần đối chiếu bằng bằng chứng thích hợp khác. Những DBMS khác dùng hàm kiểm tra tương ứng, không sao chép truy vấn PostgreSQL một cách máy móc.

Đối với PostgreSQL có nhiều schema, nên kiểm tra thêm:

~~~sql
SHOW search_path;
SELECT current_schema() AS active_schema;
~~~

Cần phân biệt schema đang hoạt động theo kết nối với schema mà Liquibase hoặc chính câu lệnh SQL tường minh sẽ nhắm tới. Kết hợp truy vấn danh tính và SQL preview mới đưa ra kết luận đáng tin cậy.

## 5. Đừng bỏ qua contexts, labels và changelog parameters

Changelog có thể chứa changeset dùng chung, changeset cho môi trường kiểm thử hoặc các nhóm thay đổi theo mục đích triển khai. Context filter và label filter được dùng để điều khiển lựa chọn đó; tham số changelog có thể ảnh hưởng nội dung SQL.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-orders
      author: db-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false

  - changeSet:
      id: 011-demo-orders
      author: db-team
      context: test
      changes:
        - insert:
            tableName: orders
            columns:
              - column:
                  name: id
                  valueNumeric: 1
~~~

Changeset 011 gắn context <code>test</code>. Không nên mặc định rằng chỉ có thuộc tính context là chắc chắn ngăn changeset chạy trong production khi **không truyền context filter**; hành vi lựa chọn phải được hiểu và kiểm chứng theo cú pháp/phiên bản Liquibase sử dụng. Với thay đổi chỉ dành cho kiểm thử, hãy đặt quy tắc lọc rõ ràng và xác minh changeset thực tế được chọn.

Đối chiếu năm điểm:

1. Context filter và label filter được truyền cho lệnh là biểu thức nào? Có bị rỗng do biến môi trường không?
2. Biểu thức có AND, OR, phủ định, dấu ngoặc hoặc điều kiện bắt buộc có đúng ý định không?
3. Bộ lọc dùng lúc status và preview có giống bộ lọc của update không?
4. Có changeset bị chọn ngoài kế hoạch hoặc bị bỏ sót không?
5. Changelog parameters đã resolve có đổi schema, tên bảng, điều kiện truy vấn hoặc dữ liệu không?

Trước update, nên ghi lại biểu thức filter và danh sách pending changesets; chỉ ghi tên môi trường “production” chưa chứng minh bộ lọc thật sự có hiệu lực.

## 6. Khi Liquibase chạy trong Spring Boot

Trong ứng dụng Spring Boot, Liquibase có thể được tự động kích hoạt khi dependency tương ứng có mặt và tính năng được bật. Cấu hình cuối chịu ảnh hưởng của **cơ chế resolve property của Spring Boot**, bao gồm các cấu hình theo profile, biến môi trường, tham số khởi động và nguồn cấu hình bên ngoài.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${APP_JDBC_URL}
    username: ${APP_JDBC_USER}
    password: ${APP_JDBC_PASSWORD}

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: liquibase_meta
    contexts: staging
~~~

Spring Boot có thể cho Liquibase dùng datasource của ứng dụng hoặc một datasource riêng. Vì vậy, **không suy ra URL migration chỉ từ <code>spring.datasource.url</code>** khi ứng dụng còn cấu hình kết nối Liquibase riêng, datasource được đánh dấu cho Liquibase hoặc custom bean. Hãy xác minh nguồn kết nối Liquibase thực sự nhận được.

| Câu hỏi | Cần kiểm tra |
|---|---|
| Liquibase có bật không? | <code>spring.liquibase.enabled</code> hiệu lực ở profile đang chạy |
| Changelog ở đâu? | <code>spring.liquibase.change-log</code> và tài nguyên thật trong artifact |
| Dùng kết nối nào? | <code>spring.datasource.*</code>, <code>spring.liquibase.*</code> hoặc datasource tùy biến |
| Chọn changeset nào? | Context/label filter và quy tắc trong changelog |
| Ghi lịch sử ở đâu? | Default schema, Liquibase schema và cấu hình tên bảng lịch sử |
| Ai kích hoạt migration? | Mỗi instance ứng dụng hay một job CI/CD chuyên trách |

Không được bật auto-run trên production chỉ để “kiểm tra cấu hình”, vì khởi động ứng dụng có thể kích hoạt migration thật. Thay vào đó, dùng cơ chế chẩn đoán nội bộ có bảo vệ/che secret, kiểm tra các property đã bind, artifact, và kết nối. Nếu pipeline riêng chạy Liquibase, có thể đặt <code>spring.liquibase.enabled=false</code> trong cấu hình hiệu lực của các instance production để tránh một đường chạy bổ sung.

## 7. Tạo bước preflight bắt buộc trong CI/CD

Pipeline nên tách giai đoạn **kiểm tra không thay đổi schema** khỏi bước cập nhật và chỉ tiếp tục khi bằng chứng khớp release.

Một manifest minh họa:

~~~yaml
release: orders-service-2026.11
environment: staging
expected:
  host: staging-db
  database: orders
  businessSchema: app
  historySchema: liquibase_meta
  changelog: db/changelog/db.changelog-master.yaml
  contexts: staging
  liquibaseVersion: "<pinned-version>"
checks:
  databaseIdentityMatched: pending
  changelogValidated: pending
  pendingChangesetsReviewed: pending
  updateSqlReviewed: pending
~~~

Đây là mẫu **ghi bằng chứng**, không phải định dạng cấu hình Liquibase. Các trạng thái chỉ được chuyển từ pending sang đạt sau khi kiểm tra thực tế, không điền PASS sẵn.

Trình tự CI/CD đề xuất:

1. Cố định commit, artifact digest, changelog và phiên bản Liquibase/driver.
2. Nạp secret đúng môi trường qua cơ chế được quản lý; không in toàn bộ biến môi trường hoặc token ra log.
3. Kiểm tra CLI, tệp defaults, biến môi trường và các nguồn ghi đè.
4. Đối chiếu danh tính database, schema, role và quyền migration.
5. Validate changelog, xem status và SQL preview; review các thay đổi có rủi ro.
6. So sánh kết quả với manifest. Nếu URL, schema, filter hoặc changeset khác dự kiến thì **dừng job**.
7. Chỉ sau khi đạt các điều kiện phát hành, chạy update bằng **cùng artifact và cấu hình đã được kiểm tra**.
8. Kiểm tra lại lịch sử DATABASECHANGELOG, log triển khai và tình trạng ứng dụng.

Cần tránh tình huống preview dùng bộ biến môi trường staging còn update lại dùng production, hoặc code/changelog mới đã được build lại giữa hai bước. Nếu một giá trị quan trọng thay đổi sau preflight, phải kiểm tra lại các kết quả phụ thuộc vào giá trị đó.

### 7.1. Quyền và bảo vệ secret

Tài khoản migration thường cần quyền tạo/sửa cấu trúc dữ liệu cao hơn tài khoản runtime của ứng dụng. Hãy kiểm tra đúng role, schema mà role được cấp quyền và cách cấp credentials. Tốt nhất hạn chế quyền theo nhu cầu thay vì dùng tài khoản quản trị database cho mọi thao tác.

Không lưu password, token hoặc URL chứa credentials trong changelog, báo cáo preflight hay log CI. Nếu cần in thông tin đích để review, chỉ lưu host, database, schema và username/role ở mức không nhạy cảm; luôn che phần secret. Kiểm tra nguồn được dùng để lấy mật khẩu, không xuất bí mật ra màn hình chỉ để chứng minh biến đã tồn tại.

## 8. Tình huống thực hành: đúng database, sai schema

Giả sử database PostgreSQL <code>orders</code> chứa hai schema:

- <code>app</code>: schema nghiệp vụ phục vụ khách hàng.
- <code>app_test</code>: schema chỉ phục vụ kiểm thử.

Yêu cầu migration là thêm chỉ mục cho <code>app.orders</code>. Pipeline kết nối đúng database <code>orders</code>, nhưng kết nối có <code>search_path</code> ưu tiên <code>app_test</code> và changeset tạo chỉ mục không chỉ rõ schema.

Nếu chỉ so sánh URL, preflight có thể báo thành công dù SQL tác động lên bảng khác hoặc thất bại. Các bước cần làm:

1. Xác định <code>defaultSchemaName</code>, <code>liquibaseSchemaName</code> và schema ghi tường minh trong changelog.
2. Kiểm tra <code>current_schema()</code>, <code>search_path</code> bằng đúng kết nối migration.
3. Sinh SQL preview và xác nhận đối tượng đích nằm trong schema <code>app</code>.
4. Kiểm tra nơi lưu DATABASECHANGELOG cũng đúng với schema metadata dự kiến.
5. Chỉ thực hiện update khi cả đích nghiệp vụ lẫn lịch sử Liquibase đã được xác nhận.

Bài học rút ra là **xác minh database không đủ để xác minh đối tượng**. Một database có thể có nhiều đối tượng cùng tên ở các schema khác nhau.

## 9. Tình huống thực hành: context không đúng ở production

Changelog có ba changeset:

| Changeset | Mục đích | Phạm vi dự định |
|---|---|---|
| 020 | Tạo bảng phân loại sản phẩm | Mọi môi trường |
| 021 | Nạp dữ liệu danh mục chuẩn | Mọi môi trường |
| 022 | Nạp dữ liệu giả lập nhiều bản ghi | Chỉ kiểm thử |

Trong staging, job có thể chọn cả ba changeset. Ở production, release chỉ được phép chạy 020 và 021. Nếu biến context filter của job production bị rỗng, không được tự cho rằng 022 bị bỏ qua.

Preflight phải đối chiếu biểu thức context/label hiệu lực, danh sách changeset đang chờ và SQL preview. Nếu xuất hiện lệnh INSERT dữ liệu giả lập ở production, dừng phát hành và sửa nguồn cấu hình hoặc logic lựa chọn, sau đó chạy lại kiểm tra. Không chỉnh bảng DATABASECHANGELOG bằng tay để khiến kết quả nhìn có vẻ hợp lệ.

## 10. Phân biệt các hình thức kiểm tra

| Kiểm tra | Chứng minh được | Không tự bảo đảm |
|---|---|---|
| Đọc tệp defaults | Giá trị khai báo trong tệp | Giá trị cuối sau khi bị ghi đè |
| Đọc CLI/biến môi trường | Đầu vào của tiến trình | Danh tính database thực tế nếu chưa kết nối |
| Truy vấn database | Database, schema và role trên phiên kết nối | Mọi changeset sẽ chạy thành công |
| <code>validate</code> | Cấu trúc changelog hợp lệ trong phạm vi công cụ kiểm tra | DDL an toàn, đủ quyền, không ảnh hưởng dữ liệu |
| <code>status --verbose</code> | Những changeset chưa được ghi nhận theo kết nối/changelog hiện tại | SQL và precondition trong quá trình thực thi |
| <code>update-sql</code> | SQL xem trước tại thời điểm sinh | Thời gian chạy, lock, khả năng rollback, dữ liệu lúc update |
| Thử trên database kiểm thử | Migration áp dụng được với dữ liệu và DBMS đang thử | Mọi điều kiện production |
| Kiểm tra sau update | Lịch sử và trạng thái sau triển khai | Khả năng phục hồi dữ liệu khi không có phương án backup |

Không có một lệnh đơn lẻ nào thay thế được toàn bộ preflight. Nhãn “validate passed” là một phần bằng chứng, chưa phải phê duyệt đầy đủ.

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Kiểm tra cần làm |
|---|---|---|
| Migration chạy vào database khác | URL bị ghi đè bởi env/CLI | Xác định nguồn thắng, kiểm tra kết nối thật |
| Đối tượng được tạo sai schema | Default schema, search path hoặc SQL tường minh không đúng | So sánh schema hiệu lực và SQL preview |
| Rất nhiều changeset bất ngờ bị coi là mới | Bảng lịch sử ở schema khác hoặc đường dẫn changelog thay đổi | Kiểm tra DATABASECHANGELOG và định danh id/author/path |
| Changeset mong đợi không xuất hiện | Include thiếu, context/label lọc đi, tham số sai | Kiểm tra artifact, filter và status |
| Dữ liệu kiểm thử xuất hiện trong production preview | Context/label bị rỗng hoặc sai | Review biểu thức và SQL preview |
| Checksum không khớp | Changeset đã triển khai bị sửa hoặc cách resolve nội dung thay đổi | So sánh changelog với bản đã phát hành; không xóa checksum vội |
| Không tìm được changelog/driver | Sai working directory, classpath/search path hoặc thiếu dependency | Kiểm tra artifact và đường dẫn runtime |
| Thiếu quyền DDL | Role không có quyền trên schema đích | Kiểm tra đúng tài khoản và quyền cần thiết |
| DATABASECHANGELOGLOCK đang bận | Có job khác chạy hoặc tiến trình dừng bất thường | Kiểm tra tiến trình, log và trạng thái khóa trước khi xử lý |
| Startup ứng dụng tự chạy migration ngoài kế hoạch | Spring Boot auto-run vẫn bật | Kiểm tra property hiệu lực và quy trình CI/CD |
| Preview khác SQL chạy thật | Đổi artifact, filter, cấu hình hoặc trạng thái database | Đối chiếu digest và manifest preflight |
| Secret bị in ra log | Dump toàn bộ env hoặc truyền password trên CLI | Che/redact và sửa cách cấp credentials |

## 12. Biên bản và điều kiện dừng trước triển khai

Một biên bản preflight tối thiểu nên ghi:

| Mục | Bằng chứng cần lưu |
|---|---|
| Release / artifact digest | Định danh chính xác của changelog sẽ được chạy |
| Môi trường, pipeline, người chịu trách nhiệm | Job nào được phép chạy, vào môi trường nào |
| Phiên bản Liquibase, driver, DBMS | Version đã được dùng lúc kiểm tra |
| Kết nối | Host/cổng, database/catalog, role, schema nghiệp vụ |
| Lịch sử Liquibase | Schema đặt DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| Changelog | Đường dẫn hiệu lực trong artifact |
| Filter và tham số | Context/label và tham số changelog đã resolve, không kèm secret |
| Kiểm tra | Validate; danh sách pending changesets; review SQL preview |
| Rủi ro | DDL phá hủy dữ liệu, khóa, thời gian chạy, backup/rollback cần thiết |
| Quyết định | APPROVE hoặc STOP, căn cứ và thời điểm xác nhận |

**Phải dừng trước <code>update</code>** nếu chưa xác minh đúng database/schema/role, changelog hoặc artifact khác bản đã review, có nguồn ghi đè chưa giải thích được, bộ lọc chọn changeset sai, validate thất bại, SQL preview có thao tác ngoài phạm vi, hay cấu hình của update thay đổi so với cấu hình đã preflight.

Khi gặp sai khác, hãy sửa nguồn cấu hình hoặc kế hoạch triển khai và chạy lại các bước kiểm tra liên quan. Tránh chỉnh sửa lịch sử Liquibase, làm mới checksum hoặc vô hiệu hóa precondition chỉ để đổi trạng thái kiểm tra sang “thành công”.

## 13. Ghi nhớ

Kiểm tra cấu hình hiệu lực nghĩa là xác nhận **Liquibase thực sự sẽ làm gì với database đích**, chứ không chỉ xem một tệp properties. Phải đối chiếu mọi nguồn có khả năng ghi đè giá trị, kiểm chứng danh tính kết nối, phân biệt schema nghiệp vụ với schema lịch sử, xác minh changelog và bộ lọc changeset, đồng thời giữ nguyên artifact và cấu hình từ lúc preview đến lúc update.

Trình tự đáng tin cậy là: **kiểm tra nguồn cấu hình → xác minh kết nối và quyền → validate → status → review update-sql → phê duyệt → update → kiểm tra lịch sử**. Quy trình này giúp migration có thể kiểm chứng, truy vết và quản lý nhất quán giữa local, test, staging, production và các mô hình tích hợp Spring Boot hoặc CI/CD.
