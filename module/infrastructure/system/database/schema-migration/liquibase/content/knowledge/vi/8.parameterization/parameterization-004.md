# Tách giá trị khác nhau giữa các môi trường

Trong chương **Tham số hóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là sử dụng cùng một bộ changelog và changeset Liquibase cho development, testing, staging và production, đồng thời cung cấp **giá trị phù hợp với từng môi trường** ở thời điểm triển khai. Liquibase giúp quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Việc tham số hóa đúng cách là một phần quan trọng để chạy migration có kiểm chứng, chuẩn bị rollback và tích hợp với Spring Boot hoặc CI/CD.

Ví dụ, bảng customer cần được tạo ở schema app_dev trên development, schema app_stage trên staging và schema app trên production. Nếu nhân bản ba tệp changelog chỉ để đổi schemaName, nhóm sẽ phải bảo trì ba bản nội dung migration, dễ lệch định danh changeset hoặc sửa một môi trường mà quên môi trường khác. Thay vào đó, changelog chỉ khai báo ý định tạo bảng; tên schema đích được truyền từ cấu hình triển khai.

**Nguyên tắc cốt lõi:** giữ ổn định mã migration, quản lý khác biệt môi trường ở nguồn cấu hình thích hợp, và lưu lại giá trị đã dùng khi triển khai để có thể kiểm chứng về sau.

## 1. Phân biệt bốn loại thông tin

Không phải mọi giá trị trông giống nhau đều nên được đặt trong changelog parameter.

| Loại giá trị | Ví dụ | Vị trí quản lý phù hợp |
|---|---|---|
| Kết nối đến database | JDBC URL, username, password, driver | Cấu hình CLI, ứng dụng, secret store của môi trường |
| Thuộc tính thay đổi schema/dữ liệu | Tên schema, một mã dữ liệu tham chiếu ổn định | Changelog parameter nếu thật sự phải khác giữa môi trường |
| Bộ lọc chọn changeset | Context dev/prod, labels, dbms | Cấu hình phạm vi chạy và thuộc tính changeset |
| Cấu hình runtime của ứng dụng | API endpoint, mức logging, feature flag thay đổi thường xuyên | Biến môi trường, config service hoặc application configuration; tránh đóng băng vào migration nếu không cần |

Một ví dụ dễ nhầm: JDBC URL dùng để Liquibase **kết nối** vào database, còn tham số appSchema trong changelog dùng để Liquibase quyết định **tạo đối tượng tại schema nào**. Hai giá trị có thể cùng chứa tên môi trường nhưng thuộc hai tầng cấu hình khác nhau.

Tương tự, contextFilter trên một changeset có nghĩa là chọn hoặc bỏ qua cả changeset theo context. Nó không tự động thay thế giá trị appSchema bằng app_dev. Muốn cùng một changeset chạy với giá trị khác nhau, cần cung cấp changelog parameter rõ ràng.

## 2. Changelog parameter hoạt động như thế nào?

Liquibase hỗ trợ **property substitution**: trong các vị trí được hỗ trợ của changelog, biểu thức dạng ${tenThamSo} được thay bằng giá trị đã khai báo hoặc được truyền vào cho lần chạy.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-release-note"
      author: "team-db"
      changes:
        - createTable:
            schemaName: "${appSchema}"
            tableName: release_note
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: title
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: "${appSchema}"
            tableName: release_note
~~~

Khi Liquibase nhận appSchema=app_dev, changeset được dùng để tạo bảng app_dev.release_note. Khi nhận appSchema=app, nó hướng đến app.release_note. Nội dung tệp changelog, id và author vẫn giữ nguyên.

Điều này khác với **prepared statement parameter** trong JDBC. Biểu thức ${appSchema} là cơ chế thay thế giá trị khi Liquibase xử lý changelog; nó không phải dấu hỏi ? được DBMS bind an toàn như dữ liệu câu truy vấn. Với những tham số được chèn vào SQL, phải xem đó là đầu vào ảnh hưởng đến câu lệnh và xác thực chặt chẽ trước khi chạy.

Một tham số chưa được cung cấp có thể khiến Liquibase không giải quyết được tên schema hoặc sinh ra lệnh không mong muốn, tùy vị trí sử dụng và phiên bản. Vì vậy, pipeline cần kiểm tra sự tồn tại và tính hợp lệ của mọi tham số bắt buộc **trước** lệnh update, không trông chờ lỗi SQL ở database để phát hiện thiếu cấu hình.

## 3. Quy tắc thiết kế tên và phạm vi tham số

Đặt tên tham số theo ý nghĩa nghiệp vụ hoặc vị trí sử dụng, thay vì gắn cứng tên môi trường:

- appSchema: schema chứa các đối tượng ứng dụng.
- lookupSchema: schema chứa dữ liệu tra cứu dùng chung, nếu hệ thống thật sự có schema này.
- seedRegionCode: mã vùng tham chiếu được dùng trong một migration xác định.
- archiveTableSuffix: hậu tố bảng lưu trữ nếu DBMS hoặc kiến trúc bắt buộc.

Đừng đặt tên như productionSchema nếu cùng tham số sẽ được dùng ở development và staging. Một bộ tên chung giúp cùng một changelog nhận giá trị riêng của từng môi trường mà không đổi cấu trúc.

Với tham số định danh schema/table/index, quy ước nên gồm:

1. **Chủ sở hữu:** ai có quyền khai báo hoặc thay đổi giá trị trong pipeline.
2. **Nguồn:** CLI, Spring Boot, tệp thuộc tính hay secret/config store.
3. **Giá trị hợp lệ:** danh sách cho phép hoặc quy tắc kiểm tra định danh DBMS.
4. **Giá trị bắt buộc:** có được thiếu hay để rỗng không.
5. **Tác động khi thay đổi:** ảnh hưởng đến checksum, rollback và đường dẫn đối tượng hay không.
6. **Dấu vết triển khai:** log hoặc metadata nào ghi lại giá trị không nhạy cảm đã dùng.

Chẳng hạn, schemaName là một tên đối tượng SQL. Nhiều DBMS có quy tắc phân biệt chữ hoa/thường, cần quote identifier hoặc giới hạn ký tự khác nhau. Nếu nhóm chỉ cho phép app_dev, app_stage và app, hãy dùng allowlist trong pipeline. Không ghép tùy tiện giá trị người dùng đưa vào tên schema hoặc chuỗi SQL.

## 4. Tách changelog khỏi cấu hình môi trường

Tổ chức dự án mẫu:

~~~text
db/
  changelog/
    db.changelog-master.yaml
    changes/
      20261119-001-create-release-note.yaml
config/
  liquibase-dev.properties
  liquibase-stage.properties
  liquibase-prod.properties
~~~

Đây là **cấu trúc minh họa**, không bắt buộc phải tạo ba tệp properties. Một pipeline cũng có thể dùng cùng một tệp cấu hình chung, còn giá trị theo môi trường được cấp bằng variables hoặc secrets của hệ thống CI/CD.

Changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/20261119-001-create-release-note.yaml
      relativeToChangelogFile: true
~~~

Tệp changeset con dùng appSchema như ví dụ ở phần 2. Khi chuyển từ staging lên production, **không nhân bản hoặc sửa tệp changeset**; thay cấu hình appSchema và thông tin kết nối, sau đó xác nhận database đích.

Có thể dùng thuộc tính property trong changelog để định nghĩa một giá trị:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: app_dev
~~~

Nhưng một giá trị hard-code như app_dev trong changelog dùng chung sẽ làm yếu mục tiêu tách môi trường. Hơn nữa, các property trùng tên hoặc được khai báo ở nhiều nguồn có quy tắc ưu tiên/ghi nhận tùy cách cấu hình. Để tránh mơ hồ, nên chọn **một nguồn có thẩm quyền** cho mỗi tham số môi trường và không khai báo nhiều giá trị cạnh tranh trong changelog.

Nếu thực sự cần giá trị mặc định cho môi trường local, hãy làm rõ cách áp dụng mặc định ấy và kiểm chứng rằng production **không thể** vô tình dùng nó. Đối với các tham số chọn database/schema production, việc fail sớm khi thiếu cấu hình thường an toàn hơn âm thầm quay về giá trị development.

## 5. Truyền tham số khi chạy Liquibase CLI

Liquibase CLI hỗ trợ cung cấp changelog parameters qua tùy chọn dạng **-DtenThamSo=giaTri**. Ví dụ minh họa khi URL, username, password và driver đã được cấu hình riêng:

~~~bash
liquibase -DappSchema=app_dev   --changelog-file=db/changelog/db.changelog-master.yaml   validate

liquibase -DappSchema=app_dev   --changelog-file=db/changelog/db.changelog-master.yaml   status --verbose

liquibase -DappSchema=app_dev   --changelog-file=db/changelog/db.changelog-master.yaml   update-sql
~~~

Sau khi review SQL sinh ra và xác nhận database đúng là development, có thể chạy:

~~~bash
liquibase -DappSchema=app_dev   --changelog-file=db/changelog/db.changelog-master.yaml   update
~~~

Ví dụ trên dùng cách xuống dòng của shell bash. Trên PowerShell, có thể viết trên một dòng để tránh khác biệt quy tắc nối dòng:

~~~powershell
liquibase -DappSchema=app_dev --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
~~~

Cách truyền -D và cách cấu hình tham số có thể thay đổi theo phiên bản CLI; xác nhận cú pháp với bản Liquibase đang dùng trước khi chốt pipeline. Trong quy trình tự động, các tham số của validate, status, update-sql và update phải nhất quán. Nếu review update-sql với appSchema=app_stage nhưng chạy update với appSchema=app, câu SQL triển khai thực tế có thể khác hẳn bản được review.

Liquibase còn hỗ trợ cấu hình qua tệp defaults như liquibase.properties. Với các phiên bản hỗ trợ **parameter.** trong tệp properties, ví dụ:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
parameter.appSchema=app_dev
~~~

Ví dụ này chỉ chứa giá trị không nhạy cảm. Tên thuộc tính và cơ chế ưu tiên giữa file, CLI, JVM và môi trường cần được đối chiếu theo phiên bản. Quan trọng hơn việc học thuộc toàn bộ thứ tự ưu tiên là tránh khai báo cùng một tham số ở nhiều nguồn khi không có lý do rõ ràng, và kiểm tra giá trị đã được giải quyết trước khi update.

## 6. Phân biệt biến môi trường của CLI với changelog parameter

Một lỗi phổ biến là nghĩ rằng chỉ cần đặt biến hệ điều hành APP_SCHEMA thì Liquibase tự thay ${appSchema} trong mọi changelog. Không nên giả định như vậy: **biến môi trường của hệ điều hành** và **changelog parameter của Liquibase** là hai khái niệm cần có cơ chế truyền hoặc ánh xạ phù hợp.

Ví dụ shell:

~~~bash
export APP_SCHEMA=app_dev

liquibase -DappSchema="$APP_SCHEMA"   --changelog-file=db/changelog/db.changelog-master.yaml   status --verbose
~~~

Ở đây, shell mở rộng APP_SCHEMA trước; đối số -D truyền giá trị đó vào tham số appSchema của Liquibase. Việc ánh xạ được viết **tường minh** nên dễ hiểu và kiểm thử.

Các biến môi trường như LIQUIBASE_COMMAND_URL và LIQUIBASE_COMMAND_USERNAME dùng để cấu hình **kết nối/chức năng của Liquibase CLI**, không phải tự động trở thành mọi property substitution tên bất kỳ trong changelog.

Có thể có cơ chế truyền changelog parameter trực tiếp từ môi trường ở phiên bản hoặc wrapper cụ thể. Khi lựa chọn cách này, hãy xác nhận tên biến, phạm vi, ưu tiên và cách chuyển kiểu theo tài liệu phiên bản đang chạy. Tránh đặt một biến trông có vẻ đúng rồi giả định Liquibase đã nhận được nó.

## 7. Truyền tham số từ Spring Boot

Khi Liquibase được tích hợp vào Spring Boot, Spring Boot quản lý các nguồn cấu hình ứng dụng. Ngoài URL và thông tin datasource, nó có nhóm thuộc tính dùng để chuyển parameters đến Liquibase.

Ví dụ application.yml dùng placeholder từ môi trường:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    parameters:
      appSchema: ${APP_SCHEMA}
~~~

Với cấu hình này:

- DB_URL/DB_USERNAME/DB_PASSWORD chọn database và thông tin kết nối của ứng dụng.
- APP_SCHEMA được Spring giải quyết rồi truyền vào map spring.liquibase.parameters.
- Tại changelog, ${appSchema} được Liquibase thay thành giá trị tương ứng.

Spring Boot dùng cơ chế externalized configuration và relaxed binding của chính nó. Không áp dụng trực tiếp toàn bộ quy tắc ưu tiên của Liquibase CLI cho một ứng dụng Spring Boot. Nếu cấu hình spring.liquibase.url hoặc thông tin đăng nhập riêng cho Liquibase, kết nối migration cũng có thể khác datasource runtime; cần xác minh đúng cả hai.

Ví dụ biến trên Linux:

~~~bash
export DB_URL="jdbc:postgresql://localhost:5432/customer_dev"
export DB_USERNAME="app_runner"
export DB_PASSWORD="<provided-by-secret-store>"
export APP_SCHEMA="app_dev"
~~~

Trong dự án triển khai thực tế, password nên được inject từ secret manager, không viết trực tiếp vào script hoặc commit lên Git. Ở production, cân nhắc tài khoản migration riêng có quyền DDL phù hợp, tách khỏi tài khoản chạy ứng dụng với quyền hạn hẹp hơn.

Có thể sử dụng Spring profile để quản lý cấu hình không nhạy cảm:

~~~yaml
# application-staging.yml
spring:
  liquibase:
    parameters:
      appSchema: app_stage
~~~

Tuy nhiên, nếu cũng có biến môi trường hoặc tùy chọn dòng lệnh ghi đè cùng property, cần kiểm tra nguồn có ưu tiên cao hơn. Với giá trị quyết định môi trường đích, nên kiểm tra profile đang active và giá trị được cấp thay vì chỉ nhìn tệp YAML.

## 8. Ma trận cấu hình để triển khai cùng một artifact

Giả sử có cùng changelog tạo bảng release_note. Một cấu hình minh họa:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| Database đích | customer_dev | customer_stage | customer_prod |
| appSchema | app_dev | app_stage | app |
| Tài khoản migration | migrator_dev | migrator_stage | migrator_prod |
| Context | dev | staging | prod |
| Label filter | test | release-candidate | release |
| Changelog | Cùng artifact A | Cùng artifact A | Cùng artifact A |
| Password | Secret dev | Secret staging | Secret prod |

Bảng này cho thấy bốn kiểu khác biệt:

1. **Kết nối**: URL và tài khoản migration thay đổi theo môi trường.
2. **Thay thế giá trị**: appSchema khác nhau nhưng changeset giữ nguyên.
3. **Chọn phạm vi**: context hoặc label có thể chọn tập changeset khác nhau.
4. **Bảo mật**: mỗi môi trường có secret và quyền riêng.

Context và label không phải thông số thay thế trực tiếp cho appSchema. Có thể cùng dùng contextFilter=prod và appSchema=app, nhưng hai thuộc tính giải quyết hai vấn đề khác nhau. Việc chọn context đúng cũng không bù được lỗi URL đang trỏ nhầm database.

Để bảo đảm một bản phát hành được kiểm chứng, artifact từ bước build/test nên được promote nguyên vẹn giữa các môi trường, cùng bộ thay đổi schema đã được review. Chỉ cấu hình theo môi trường mới thay đổi, còn id, author, filename và nội dung của changeset đã phát hành phải được giữ ổn định.

## 9. Khi nào nên tham số hóa, khi nào nên tách changeset?

**Nên tham số hóa** khi mục đích migration giống nhau trên mọi môi trường và sự khác biệt được thiết kế từ trước:

- Tên schema đích của cùng một đối tượng.
- Một định danh đối tượng khác nhau theo kiến trúc được kiểm soát.
- Dữ liệu tham chiếu ổn định có giá trị khác nhau theo môi trường và thực sự cần nằm trong database.

**Nên tách hoặc lọc changeset** khi *bản chất thay đổi* khác nhau:

- Development cần dữ liệu giả lập, production không được tạo.
- DBMS khác nhau đòi hỏi câu lệnh SQL không tương đương về tính năng.
- Một môi trường có feature chưa được phát hành và cần kiểm soát phạm vi.
- Migration phải đi qua nhiều bước chuyển tiếp có phụ thuộc khác nhau.

Ví dụ seed dữ liệu thử nghiệm có thể dùng contextFilter:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-seed-demo-customer"
      author: "team-db"
      contextFilter: "dev"
      changes:
        - insert:
            schemaName: "${appSchema}"
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 999999
              - column:
                  name: email
                  value: "demo@example.test"
~~~

Changeset này phục vụ development; không nên chỉ đổi email thành một giá trị khác bằng parameter rồi cho nó chạy trên production nếu mục đích dữ liệu là thử nghiệm.

Với DBMS khác nhau, thuộc tính dbms hoặc changeset riêng có thể rõ ràng hơn một chuỗi ${sqlStatement} chứa nguyên câu SQL. Tham số hóa toàn bộ SQL khiến ý nghĩa thay đổi khó review, tăng nguy cơ chèn SQL và gây sai khác triển khai.

## 10. Tham số hóa dữ liệu tham chiếu và giới hạn cần biết

Liquibase có thể thay thế property trong giá trị change type; tuy nhiên không phải giá trị môi trường nào cũng phù hợp để đưa vào migration.

Ví dụ một bảng app_setting đã tồn tại và cần lưu public endpoint cố định cho đợt khởi tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-seed-public-endpoint"
      author: "team-db"
      changes:
        - insert:
            schemaName: "${appSchema}"
            tableName: app_setting
            columns:
              - column:
                  name: setting_key
                  value: PUBLIC_API_BASE_URL
              - column:
                  name: setting_value
                  value: "${publicApiBaseUrl}"
      rollback:
        - delete:
            schemaName: "${appSchema}"
            tableName: app_setting
            where: "setting_key = 'PUBLIC_API_BASE_URL'"
~~~

Lệnh này chỉ hợp lý nếu dữ liệu được thiết kế như **dữ liệu khởi tạo có vòng đời migration**. Nếu URL cần được đổi thường xuyên để vận hành ứng dụng, dùng application configuration hoặc config service sẽ phù hợp hơn. Không tạo một changeset mới mỗi lần đổi URL runtime chỉ vì có thể dùng property substitution.

Một giới hạn nữa: DATABASECHANGELOG lưu lịch sử changeset, checksum và những thông tin triển khai tiêu chuẩn, nhưng không nên coi đó là kho lưu **mọi giá trị parameter đã giải quyết**. Để audit chính xác, pipeline nên ghi nhận các giá trị **không nhạy cảm** đã dùng, ví dụ appSchema và mã artifact, trong bản ghi triển khai riêng.

Không ghi password, token, private key hay secret vào cột dữ liệu chỉ để tiện thay thế bằng ${...}. Nếu một thao tác bảo trì thật sự cần secret, phải dùng cơ chế cấp phát an toàn, giới hạn quyền và tuyệt đối tránh để secret xuất hiện trong generated SQL hoặc log.

## 11. Checksum và rủi ro khi đổi tham số sau triển khai

Định danh changeset của Liquibase dựa trên **ID + AUTHOR + FILENAME**. Property substitution không làm thay đổi id hoặc author được khai báo, nhưng giá trị đã giải quyết có thể ảnh hưởng đến nội dung mà Liquibase dùng để kiểm tra checksum và thực thi, tùy change type và phiên bản.

Cần phân biệt hai trường hợp:

**Khác giá trị ở hai database độc lập.** Nếu staging lần đầu triển khai với appSchema=app_stage và production lần đầu triển khai với appSchema=app, đây có thể là thiết kế bình thường. Mỗi database có DATABASECHANGELOG và lịch sử riêng; phải kiểm thử tính phù hợp của changeset với từng môi trường.

**Đổi giá trị trên chính database đã chạy.** Nếu một changeset trước đây tạo app_stage.release_note rồi chạy lại với appSchema=app_archive, Liquibase không tự hiểu rằng bạn muốn di chuyển bảng. Nó có thể báo checksum khác hoặc xử lý theo quy tắc của changeset, và nếu không phát hiện được thì trạng thái lịch sử vẫn không chứng minh bảng mới đã tồn tại. Cách an toàn là coi changeset đã triển khai là bất biến và tạo một **changeset mới** cho việc đổi schema, tên đối tượng hoặc chuyển dữ liệu.

Không dùng clear-checksums, validCheckSum, runOnChange hoặc runAlways như cách mặc định để hợp thức hóa việc đổi giá trị môi trường sau triển khai. Các cơ chế ấy có mục đích riêng và có thể làm một thao tác DDL/DML chạy lại. Khi thay đổi giá trị ảnh hưởng đến hành vi đã triển khai, cần xác định rõ đây là cấu hình cho **lần triển khai mới** hay là **migration bổ sung**.

Một quy tắc thực tế: **bất kỳ parameter nào có thể thay đổi SQL/đối tượng mà changeset cũ đã tạo đều phải được quản lý bằng quy trình thay đổi schema có kiểm chứng**, chứ không chỉ cập nhật biến môi trường.

## 12. Tham số và rollback có thể lệch nhau

Ở phần 2, rollback dùng cùng ${appSchema} với createTable. Điều này hợp lý nếu giá trị luôn được bảo đảm đúng trong lần rollback. Nhưng giả sử migration đầu tiên chạy với appSchema=app_dev, sau đó operator đổi thành app_test rồi mới chạy rollback, Liquibase có thể giải quyết rollback theo **giá trị hiện tại**, không phải giá trị bạn tưởng tượng đã dùng lúc update.

Khi đó rollback có nguy cơ nhắm sai schema hoặc không tìm thấy đối tượng. Bài học quan trọng:

1. Ghi lại parameter không nhạy cảm được dùng cho từng lần triển khai.
2. Khi chuẩn bị rollback, xác nhận đúng database, changelog revision và giá trị parameter tương ứng với lần update.
3. Xem trước SQL rollback bằng công cụ/command phù hợp với phiên bản Liquibase đang dùng.
4. Kiểm tra schema, phụ thuộc và dữ liệu thực tế trước khi chạy rollback.
5. Đừng giả định rollback kỹ thuật luôn có thể khôi phục dữ liệu: dropTable hoặc dropColumn có thể xóa dữ liệu mới phát sinh.

Một số change type có thể có rollback tự động, nhưng SQL tự viết, dữ liệu phức tạp hoặc thao tác không thể đảo ngược thường cần rollback tường minh và kế hoạch khôi phục. Trường hợp môi trường production đã sinh dữ liệu quan trọng có thể cần phương án forward fix hoặc backup/restore được kiểm soát.

## 13. Changelog parameters với SQL thuần và formatted SQL

Khi dùng change type sql hoặc sqlFile, có thể cần thay thế giá trị trong nội dung SQL, nhưng mức hỗ trợ và cú pháp phụ thuộc ngữ cảnh nạp tệp và phiên bản Liquibase. Ví dụ SQL chứa định danh schema:

~~~sql
CREATE TABLE ${appSchema}.audit_event (
    id BIGINT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL
);
~~~

Đây là **thay thế văn bản vào SQL**. Giá trị appSchema phải được kiểm tra bằng allowlist hoặc quy tắc định danh DBMS trước khi đưa vào câu SQL. Không cho phép người dùng hoặc request bên ngoài trực tiếp kiểm soát tham số này.

Với formatted SQL changelog:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-004-create-audit-event
CREATE TABLE ${appSchema}.audit_event (
    id BIGINT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL
);
--rollback DROP TABLE ${appSchema}.audit_event;
~~~

Trong dự án thực tế, hãy xác minh Liquibase version và khả năng property substitution của loại changelog đang dùng bằng validate, status và update-sql. Không giả định việc DBMS chấp nhận chuỗi SQL cũng có nghĩa Liquibase đã thay đúng parameter.

Nếu cần một câu SQL hoàn toàn khác trên PostgreSQL và Oracle, khai báo changeset có bộ lọc dbms hoặc tệp SQL tương ứng có thể dễ review và an toàn hơn việc đưa cả câu SQL vào một parameter. Không nên dùng parameter hóa để che giấu thay đổi về logic migration.

## 14. Kiểm soát thứ tự ưu tiên khi có nhiều nguồn giá trị

Các nguồn cung cấp tham số có thể bao gồm tùy chọn CLI, tệp properties, cấu hình ứng dụng, thuộc tính changelog và cơ chế môi trường của wrapper hoặc CI/CD. **Không nên suy diễn rằng thứ tự ưu tiên của cấu hình kết nối và thứ tự ưu tiên của changelog parameters luôn giống nhau.** Chi tiết áp dụng có thể phụ thuộc phiên bản Liquibase và cách gọi (CLI hoặc Spring Boot).

Một thiết kế dễ kiểm soát là:

- Mỗi tham số môi trường có một nguồn chính thức trong từng job.
- Đối với CLI, ánh xạ rõ biến pipeline sang -DtenThamSo=giaTri hoặc cơ chế cấu hình được phiên bản hỗ trợ.
- Đối với Spring Boot, truyền vào spring.liquibase.parameters bằng property source của Spring.
- Không đặt giá trị mặc định production nhạy cảm trong changelog.
- Không viết thêm property trùng tên ở changelog con để mong nó ghi đè property đã có.
- Ghi lại cấu hình không nhạy cảm hiệu lực của job để phục vụ điều tra sự cố.

Nếu phát hiện hai giá trị cạnh tranh cho appSchema, hãy giải quyết tại cấu hình trước khi tiếp tục. Không chọn một giá trị chỉ vì status vẫn chạy được: status có thể kết nối thành công nhưng đang kiểm tra schema khác dự kiến.

Ngoài ra, chú ý **thời điểm thay thế**. Tham số được giải quyết khi Liquibase xử lý changelog, không phải là biến runtime có thể đổi trong khi một changeset đang chạy. Việc thay đổi biến môi trường sau khi một tiến trình Liquibase đã khởi động không phải cách cập nhật migration đang thực thi.

## 15. Bảo mật và kiểm tra giá trị tham số

Property substitution không phải cơ chế bind tham số SQL an toàn. Với tên schema, bảng hoặc các mảnh SQL, cần bảo đảm đầu vào đã qua kiểm tra. Ví dụ pipeline cho ba giá trị schema hợp lệ:

~~~bash
case "$APP_SCHEMA" in
  app_dev|app_stage|app) ;;
  *)
    echo "APP_SCHEMA không hợp lệ" >&2
    exit 1
    ;;
esac
~~~

Mẫu này chỉ minh họa allowlist cho schema. Trong hệ thống thật, tốt hơn nữa là ánh xạ environment -> schema trong cấu hình quản trị được kiểm soát, hạn chế người vận hành nhập chuỗi tùy ý.

Không truyền vào parameter các chuỗi lấy trực tiếp từ URL, form hoặc input chưa tin cậy. Không ghi toàn bộ bộ biến môi trường ra log vì có thể chứa secret. Với thông tin như password, nên cấu hình kết nối qua secret manager và thuộc tính chuyên dụng thay vì cho vào changelog parameter.

Khi review SQL được sinh ra, kiểm tra cả **identifier** và **literal**:

- Định danh: schema, table, index cần đúng quy tắc quote/case của DBMS.
- Giá trị dữ liệu: literal có thể chứa dấu nháy hoặc ký tự đặc biệt, phải được công cụ/DBMS xử lý đúng.
- Quyền: tài khoản migration chỉ được cấp quyền cần thiết.
- Môi trường: URL, host, database, schema và context phải đồng nhất với môi trường dự kiến.

Một giá trị tham số có cú pháp đúng vẫn có thể gây lỗi nghiệp vụ, ví dụ trỏ tới schema của tenant khác. Do đó, xác thực phải kiểm tra tính hợp lệ **và** ý nghĩa môi trường.

## 16. Pipeline CI/CD có kiểm chứng

Một pipeline điển hình có thể nhận appSchema từ biến triển khai đã kiểm soát, nhận URL và tài khoản từ secret store, rồi gọi Liquibase:

~~~bash
# URL, USERNAME và PASSWORD phải được inject bởi secret store của pipeline.
export APP_SCHEMA="$DEPLOY_APP_SCHEMA"

case "$APP_SCHEMA" in
  app_dev|app_stage|app) ;;
  *) echo "Schema không nằm trong allowlist" >&2; exit 1 ;;
esac

liquibase -DappSchema="$APP_SCHEMA"   --changelog-file=db/changelog/db.changelog-master.yaml   validate

liquibase -DappSchema="$APP_SCHEMA"   --changelog-file=db/changelog/db.changelog-master.yaml   status --verbose

liquibase -DappSchema="$APP_SCHEMA"   --changelog-file=db/changelog/db.changelog-master.yaml   update-sql
~~~

Sau khi review SQL, xác nhận target database và hoàn thành các cổng kiểm soát của quy trình phát hành, chạy:

~~~bash
liquibase -DappSchema="$APP_SCHEMA"   --changelog-file=db/changelog/db.changelog-master.yaml   update
~~~

Ở pipeline thật, cần bảo đảm bốn lệnh dùng **cùng artifact, cùng changelog revision, cùng target database và cùng giá trị parameter**. Các bước chạy ở job/container khác nhau phải nhận lại variables và secrets qua cơ chế chính thức; biến export trong một job không tự động tồn tại trong job khác.

Sau khi update:

1. Kiểm tra DATABASECHANGELOG của database đích để xác nhận changeset đã được ghi nhận.
2. Kiểm tra đối tượng trong đúng schema, ví dụ app_stage.release_note ở staging.
3. Ghi lại artifact ID, phiên bản changelog, appSchema, context/label và thời điểm chạy (không ghi secret).
4. Đối chiếu các kết quả với SQL đã được review.
5. Chuẩn bị dữ liệu cần thiết cho rollback hoặc kế hoạch sửa tiến.

Liquibase sử dụng DATABASECHANGELOGLOCK để điều phối các tiến trình migration cùng database. Cơ chế khóa giúp hạn chế chạy đồng thời nhưng không thay thế việc kiểm soát pipeline và xác minh giá trị theo môi trường.

## 17. Chẩn đoán các lỗi tách giá trị môi trường

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Tạo bảng vào schema không mong muốn | appSchema sai, bị ghi đè hoặc giá trị mặc định không phù hợp | Xem parameter hiệu lực, generated SQL, default schema và target database |
| Biểu thức ${appSchema} không được thay | Thiếu tham số, sai tên/chữ hoa-thường, cú pháp hoặc định dạng không hỗ trợ | Kiểm tra nguồn cấp parameter, tên chính xác và SQL được sinh |
| Development chạy được, staging báo permission denied | Tài khoản migration staging thiếu quyền trên schema đích | Kiểm tra user, schema và quyền DDL thực tế |
| Thay APP_SCHEMA nhưng bảng cũ không chuyển | Đổi parameter không tạo changeset chuyển đối tượng | Thiết kế migration mới, đối chiếu history và schema thực tế |
| Kiểm tra bằng update-sql ra schema khác với update | Hai lệnh nhận cấu hình/parameter khác nhau | So sánh input và artifact của từng job, khóa giá trị giữa các bước |
| Checksum thay đổi sau khi đổi parameter | Giá trị đã giải quyết ảnh hưởng nội dung changeset đã ghi nhận | Kiểm tra chính xác thay đổi; giữ changeset cũ và tạo changeset mới nếu cần |
| Rollback nhắm nhầm schema | Dùng parameter khác lần triển khai ban đầu | Khôi phục tham số đã dùng, review rollback SQL và database đích |
| Chỉ một môi trường có dữ liệu demo | Context/label làm changeset chỉ chạy trong môi trường đó | Kiểm tra phạm vi bộ lọc, không nhầm với parameter substitution |
| Spring Boot đọc APP_SCHEMA nhưng Liquibase không nhận | Thiếu binding spring.liquibase.parameters hoặc property source bị ghi đè | Kiểm tra cấu hình Spring Boot, profile và tham số map |
| SQL được sinh có tên schema lạ hoặc có ký tự bất thường | Parameter không được kiểm tra hoặc bị chèn chuỗi không tin cậy | Dừng triển khai, kiểm tra allowlist và nguồn cấu hình |

Khi xử lý lỗi, xác định **đúng lớp xảy ra lỗi**: kết nối, binding parameter, parse changelog, bộ lọc changeset, checksum hay thực thi SQL. Đừng vội chạy clear-checksums, sửa DATABASECHANGELOG hoặc thử update lặp lại khi chưa xác định schema đích và nguyên nhân.

## 18. Bài thực hành: cùng changeset trên hai môi trường thử nghiệm

**Đề bài:** tạo bảng release_note ở hai database thử nghiệm độc lập. Database A dùng schema app_dev, database B dùng schema app_stage. Cả hai dùng cùng changelog YAML có id "20261119-001-create-release-note" và author "team-db".

### Chuẩn bị

- Hai database thử nghiệm có schema tương ứng đã tồn tại hoặc được tạo bởi bước setup riêng.
- Tài khoản migration được cấp quyền phù hợp cho từng database.
- Changelog chung giống hệt trên cả hai lần chạy.
- Cấu hình kết nối riêng; appSchema lần lượt là app_dev và app_stage.

### Thực hiện trên database A

1. Cấu hình kết nối tới A và cấp appSchema=app_dev.
2. Chạy validate, status --verbose.
3. Chạy update-sql; kiểm tra SQL nhắm đến app_dev.release_note.
4. Chạy update trên A.
5. Truy vấn DATABASECHANGELOG và kiểm tra bảng thực tế trong app_dev.

### Thực hiện trên database B

1. Cấu hình kết nối tới B và cấp appSchema=app_stage.
2. Chạy validate, status --verbose.
3. Chạy update-sql; kiểm tra SQL nhắm đến app_stage.release_note.
4. Chạy update trên B.
5. Truy vấn DATABASECHANGELOG và kiểm tra bảng thực tế trong app_stage.

### Đối chiếu kết quả

| Điểm so sánh | Database A | Database B |
|---|---|---|
| Changelog source | Giống nhau | Giống nhau |
| id/author | Giống nhau | Giống nhau |
| appSchema | app_dev | app_stage |
| Đối tượng kỳ vọng | app_dev.release_note | app_stage.release_note |
| DATABASECHANGELOG | Lịch sử riêng của A | Lịch sử riêng của B |

Câu hỏi: Nếu sau khi hoàn thành, thay appSchema=app_test và chạy lại update trên database A thì bảng có tự được chuyển sang app_test không? **Không.** Changelog parameter chỉ thay giá trị dùng khi giải quyết changelog; việc di chuyển đối tượng đã tồn tại cần một migration được thiết kế riêng.

Câu hỏi: Nếu cần thêm cột published_at vào bảng release_note trên cả hai môi trường, nên sửa changeset tạo bảng hay thêm changeset mới? **Thêm changeset mới** và tiếp tục dùng appSchema như một parameter, sau đó kiểm thử trên từng database.

Câu hỏi: Nếu rollback trên A nhưng cấu hình hiện tại lại có appSchema=app_stage, rủi ro là gì? SQL rollback có thể nhắm sai schema hoặc thất bại. Cần xác nhận lại giá trị parameter và generated rollback SQL trước khi thực thi.

## 19. Checklist khi thiết kế tham số hóa

- [ ] Đã phân biệt cấu hình kết nối, changelog parameter, bộ lọc và runtime configuration.
- [ ] Chỉ tham số hóa những giá trị thật sự phải khác giữa môi trường.
- [ ] Changelog chung giữ nguyên id, author, filename và nội dung đã phát hành.
- [ ] Đã đặt tên parameter nhất quán, rõ mục đích, có chủ sở hữu.
- [ ] Mỗi parameter có một nguồn cấp chính thức và quy tắc kiểm tra.
- [ ] Không dựa vào giá trị development mặc định cho production.
- [ ] Biến môi trường được ánh xạ tường minh tới changelog parameter.
- [ ] Spring Boot dùng đúng spring.liquibase.parameters khi tích hợp ứng dụng.
- [ ] Các giá trị schema/table/SQL được kiểm tra theo allowlist hoặc quy tắc DBMS.
- [ ] Secret không nằm trong changelog, Git, generated SQL hoặc log.
- [ ] Context/label được dùng để chọn changeset, không bị nhầm là cơ chế thay giá trị.
- [ ] Đã kiểm tra tác động checksum khi thay parameter của changeset đã ghi nhận.
- [ ] SQL update và rollback được review với đúng parameter môi trường.
- [ ] Cùng artifact, database, schema và parameter được dùng nhất quán qua các bước CI/CD.
- [ ] Đã kiểm chứng DATABASECHANGELOG và schema thực tế sau triển khai.
- [ ] Đã lưu lại giá trị không nhạy cảm dùng cho lần update để hỗ trợ audit và rollback.

Việc tách giá trị khác nhau giữa các môi trường không chỉ nhằm giảm số lượng tệp cấu hình. Nó giúp **một thay đổi schema hoặc dữ liệu có cùng ý nghĩa** được triển khai nhất quán lên các database khác nhau, trong khi URL, schema, tài khoản và phạm vi chạy được cấp có kiểm soát ở từng môi trường. Khi Liquibase property substitution được sử dụng đúng chỗ, kết hợp với review SQL, quản lý checksum, kiểm chứng lịch sử và kế hoạch rollback, nhóm có thể vận hành migration qua Spring Boot hoặc CI/CD mà vẫn giữ changelog rõ ràng và dễ bảo trì.
