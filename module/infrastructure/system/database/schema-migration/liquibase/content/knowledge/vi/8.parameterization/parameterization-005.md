# Kiểm soát thay thế thuộc tính trong SQL và dữ liệu mẫu

## 1. Mục tiêu của bài học

Liquibase cho phép sử dụng **thuộc tính trong changelog** để thay những giá trị như tên schema, tên bảng hoặc một số tham số triển khai. Nhờ đó, cùng một định nghĩa migration có thể được thực thi trên nhiều môi trường mà không phải sao chép toàn bộ SQL. Tuy nhiên, cơ chế này có tính chất **thay thế văn bản**: một giá trị không được kiểm soát có thể làm hỏng SQL, dẫn đến cập nhật sai đối tượng hoặc khiến dữ liệu mẫu lọt vào môi trường production.

Bài thuộc chương **Tham số hóa** trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới việc nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Phạm vi bài này tập trung vào cách **kiểm soát việc thay thế thuộc tính trong SQL và khi tạo dữ liệu mẫu**, đồng thời vẫn giữ được lịch sử changeset đáng tin cậy.

Sau bài học, người học cần có khả năng:

1. Giải thích được dấu giữ chỗ dạng **${propertyName}** được Liquibase thay thế như thế nào.
2. Phân biệt **changelog property** với tham số bind của JDBC, biến môi trường và tham số cấu hình Spring Boot.
3. Chọn thuộc tính có thể thay thế một cách an toàn, đặc biệt là tên schema, tên bảng và giá trị dữ liệu.
4. Thiết kế dữ liệu mẫu có phạm vi môi trường rõ ràng, điều kiện chạy, khóa duy nhất và rollback.
5. Kiểm tra SQL sau thay thế bằng validate, update-sql, kiểm tra database đích và test trên dữ liệu đại diện.
6. Phát hiện các rủi ro về cú pháp SQL, injection, checksum, thay đổi thuộc tính sau khi đã triển khai và rò rỉ thông tin nhạy cảm.

## 2. Vì sao cần tham số hóa migration?

Giả sử một ứng dụng bán hàng triển khai cùng một bảng **app_setting** trên các môi trường:

| Môi trường | Schema ví dụ | Dữ liệu |
|---|---|---|
| Development | dev_app | Có thể có cấu hình thử nghiệm và dữ liệu mẫu |
| Integration test | test_app | Dữ liệu kiểm thử có thể tái tạo |
| Production | app | Chỉ dữ liệu nghiệp vụ, cấu hình và dữ liệu tham chiếu đã phê duyệt |

Viết ba bản SQL độc lập chỉ khác tên schema khiến nhóm phải sửa nhiều nơi khi thay đổi một cột hoặc ràng buộc. Liquibase có thể dùng một changelog với tham số **appSchema** và thay giá trị khi chạy tại môi trường tương ứng.

Ví dụ một dòng SQL có giá trị giữ chỗ:

~~~sql
SELECT COUNT(*) FROM ${appSchema}.app_setting;
~~~

Nếu **appSchema = dev_app**, SQL sau thay thế sẽ là:

~~~sql
SELECT COUNT(*) FROM dev_app.app_setting;
~~~

Nếu **appSchema = app**, SQL sẽ trỏ tới schema khác. Chính vì vậy, thay đổi tham số có thể thay đổi **đối tượng bị tác động**. Một lỗi nhỏ trong file cấu hình hoặc biến môi trường có thể khiến migration cập nhật nhầm database/schema dù nội dung changeset không đổi.

Do đó, mục đích của tham số hóa là **tái sử dụng định nghĩa có kiểm soát**, không phải biến changelog thành nơi nhận SQL tùy ý từ người dùng hoặc từ những nguồn thiếu tin cậy.

## 3. Cơ chế thay thế thuộc tính của Liquibase

### 3.1. Cú pháp giữ chỗ

Trong changelog, Liquibase hỗ trợ biểu thức dạng:

~~~text
${propertyName}
~~~

Khi đọc và xử lý changelog, công cụ dùng giá trị của changelog parameter tương ứng để thay biểu thức tại các vị trí được hỗ trợ. Thay thế có thể xuất hiện trong thuộc tính của change type và trong nội dung SQL mà Liquibase xử lý, tùy loại changelog và cơ chế nạp SQL.

Ví dụ khai báo property trong YAML:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: dev_app

  - changeSet:
      id: 001-create-app-setting
      author: platform-team
      changes:
        - createTable:
            schemaName: ${appSchema}
            tableName: app_setting
            columns:
              - column:
                  name: setting_key
                  type: VARCHAR(100)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: setting_value
                  type: VARCHAR(500)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: ${appSchema}
            tableName: app_setting
~~~

**Giả định:** schema dev_app đã tồn tại và tài khoản migration có quyền tạo bảng trong schema đó. Thuộc tính appSchema được khai báo ngay trong ví dụ để người học thấy cơ chế thay thế; ở dự án thực, giá trị này thường được cấp theo môi trường chạy.

Ở cấu hình YAML có cấu trúc, khai báo **schemaName** rõ ràng thường dễ kiểm soát hơn tự nối chuỗi SQL chứa tên schema ở nhiều vị trí. Tuy nhiên, schemaName vẫn cần được giới hạn bởi allowlist và kiểm tra database đích.

### 3.2. Từ đâu có giá trị property?

Tùy phiên bản và cách tích hợp, các changelog parameter có thể được cấp thông qua:

- Khai báo **property** trong changelog.
- Cấu hình hoặc tham số CLI được Liquibase hỗ trợ.
- Tầng tích hợp ứng dụng, ví dụ **spring.liquibase.parameters** trong Spring Boot.
- Cơ chế nạp cấu hình của pipeline hoặc mã Java dùng Liquibase API.

Không nên mặc định rằng bất kỳ biến môi trường nào có cùng tên cũng tự trở thành changelog parameter. Ví dụ biến môi trường **APP_SCHEMA** cần được ánh xạ đúng qua nguồn cấu hình mà Liquibase/Spring Boot nhận diện; cách ánh xạ phụ thuộc môi trường thực thi.

Thứ tự ưu tiên và quy tắc chỉ nhận giá trị khai báo đầu tiên có thể khác theo cách cấp parameter và phiên bản Liquibase. **Quy tắc vận hành nên chọn một nguồn xác thực cho mỗi property**, không cố ý khai báo cùng tên ở nhiều nơi rồi phụ thuộc vào thứ tự ghi đè. Muốn biết thực sự dùng giá trị nào, hãy kiểm tra SQL được sinh ra trên chính bộ công cụ đang sử dụng.

### 3.3. Property không phải biến SQL hay một tham số JDBC

Ba khái niệm dễ nhầm lẫn:

| Cơ chế | Ví dụ | Thời điểm/ý nghĩa |
|---|---|---|
| Liquibase changelog substitution | ${appSchema} | Liquibase thay giá trị khi xử lý changelog hoặc SQL liên quan |
| JDBC bind parameter | Dấu hỏi **?** trong PreparedStatement | Driver/database bind giá trị dữ liệu cho một câu SQL đã định hình |
| Biến môi trường/ứng dụng | APP_SCHEMA, DB_PASSWORD | Hệ điều hành hoặc framework cung cấp cấu hình cho tiến trình |

Thay thế của Liquibase **không tương đương PreparedStatement**. Nó không tự bảo đảm escape ký tự đặc biệt, không xác định loại dữ liệu như JDBC bind, không ngăn SQL injection khi giá trị đầu vào bị kiểm soát bởi nguồn không tin cậy và không mặc nhiên đặt dấu nháy cho định danh SQL.

Dùng thuộc tính Liquibase cho một số yếu tố cấu hình ổn định, chẳng hạn tên schema đã kiểm tra. Với dữ liệu nhận từ người dùng ở runtime, hãy dùng PreparedStatement hoặc API truy cập dữ liệu của ứng dụng thay vì đưa dữ liệu đó vào SQL migration.

## 4. Phân loại giá trị trước khi cho phép thay thế

Không phải mọi giá trị đều nên được đặt trong placeholder.

| Loại giá trị | Ví dụ | Cách kiểm soát |
|---|---|---|
| Định danh schema | dev_app, app | Chọn từ allowlist, kiểm tra cú pháp và database đích |
| Tên bảng/cột | app_setting, setting_value | Ưu tiên tên cố định trong changelog; nếu thực sự cần tham số hóa thì có allowlist nghiêm ngặt |
| Giá trị cấu hình dữ liệu mẫu | DEMO-001, demo.enabled | Dùng tập giá trị kiểm soát, ràng buộc duy nhất và change type có cấu trúc |
| Giá trị SQL có dấu nháy | O'Brien, chuỗi nhiều ký tự đặc biệt | Không ghép trực tiếp vào chuỗi SQL; xác minh escaping và kiểu giá trị |
| Số, ngày, boolean | 12, 2026-01-01, true | Dùng thuộc tính có kiểu tương ứng khi change type hỗ trợ |
| Mật khẩu, token, khóa API | Bí mật kết nối | Không đặt vào changelog, SQL migration, update-sql hoặc log |
| Cả một biểu thức SQL | WHERE ..., ORDER BY ..., tên hàm | Không cho nguồn tùy ý quyết định; ưu tiên SQL cố định và review được |

**Tên schema/bảng là định danh SQL**. Cơ chế JDBC bind thông thường không thay thế tên bảng/cột như thay một giá trị trong WHERE. Nếu cho phép chọn tên schema, cần xét giá trị đó như một thành phần mã lệnh: kiểm tra nghiêm ngặt và không nhận trực tiếp từ request hoặc input không đáng tin.

Một allowlist có thể được định nghĩa ở lớp pipeline:

~~~text
environment = dev   => appSchema = dev_app
environment = test  => appSchema = test_app
environment = prod  => appSchema = app
~~~

Bảng ánh xạ này là **quy ước minh họa**, không phải tệp cấu hình có thể thực thi trực tiếp. Pipeline nên kiểm tra giá trị đích thực tế thay vì chỉ tin vào tên job.

## 5. Thay thế thuộc tính trong SQL thô

Giả sử bảng app_setting đã tồn tại và chỉ muốn thay đổi một cờ demo trên môi trường dev. Câu SQL có placeholder:

~~~sql
UPDATE ${appSchema}.app_setting
SET setting_value = 'false'
WHERE setting_key = 'demo.banner.enabled';
~~~

Khi appSchema được đặt là dev_app, Liquibase có thể tạo câu SQL cập nhật **dev_app.app_setting**. Phải review SQL sau thay thế, vì tham số không hợp lệ có thể gây lỗi cú pháp hoặc trỏ sai schema.

Có thể đặt SQL trong changeset YAML:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: dev_app

  - changeSet:
      id: 002-disable-demo-banner
      author: training-team
      contextFilter: "@dev"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: ${appSchema}
            tableName: app_setting
      changes:
        - sql:
            sql: |
              UPDATE ${appSchema}.app_setting
              SET setting_value = 'false'
              WHERE setting_key = 'demo.banner.enabled';
      rollback:
        - sql:
            sql: |
              UPDATE ${appSchema}.app_setting
              SET setting_value = 'true'
              WHERE setting_key = 'demo.banner.enabled';
~~~

Ví dụ này **chỉ phù hợp nếu giá trị trước migration thực sự là true**; nếu giá trị ban đầu khác, rollback đặt cố định thành true có thể làm sai dữ liệu. Khi viết migration thực tế, phải biết trạng thái trước đó hoặc có phương án khôi phục thích hợp. Ví dụ còn giả định app_setting đã được tạo, schema tồn tại và SQL này được triển khai trên database học tập.

**contextFilter: "@dev"** yêu cầu ngữ cảnh dev được chỉ định tường minh theo cơ chế context của Liquibase. Điều này giúp giảm nguy cơ SQL demo chạy khi thiếu bộ lọc, nhưng **không phải hàng rào bảo mật tuyệt đối**: nếu pipeline production truyền nhầm context dev hoặc JDBC URL trỏ nhầm, câu SQL vẫn có thể tác động ngoài ý muốn. Phải kết hợp kiểm tra đích và quyền database.

## 6. Không ghép giá trị không đáng tin vào chuỗi SQL

### 6.1. Rủi ro dấu nháy và SQL injection

Xét câu SQL không an toàn:

~~~sql
INSERT INTO app.demo_customer(customer_code, display_name)
VALUES ('${sampleCode}', '${sampleDisplayName}');
~~~

Nếu giá trị sampleDisplayName chứa dấu nháy đơn, ví dụ **O'Brien**, cú pháp sau thay thế có thể sai. Nếu giá trị đến từ một nguồn không đáng tin, nó còn có thể chèn thêm biểu thức SQL ngoài ý muốn. Liquibase không tự biến thao tác thay thế ở đây thành một truy vấn đã bind an toàn.

Không nên tự xây dựng cơ chế escape bằng một vài phép thay chuỗi thủ công, nhất là khi SQL được dùng trên nhiều DBMS. Quy tắc an toàn hơn là:

1. Chỉ chấp nhận những giá trị đã được xác nhận và giới hạn kiểu/độ dài.
2. Ưu tiên **change type có cấu trúc** cho INSERT/UPDATE/DELETE.
3. Tránh đưa toàn bộ biểu thức SQL vào property.
4. Dùng SQL cụ thể, được review cùng changelog, khi cần cú pháp đặc thù DBMS.
5. Xem SQL cuối cùng trước khi thực thi; kiểm tra hành vi trên database thử nghiệm.

### 6.2. Dùng change type có cấu trúc cho dữ liệu mẫu

Liquibase có các change type như **insert**, **update**, **delete**, cho phép khai báo bảng và các cột bằng cấu trúc YAML thay vì tự ghép chuỗi INSERT. Ví dụ:

~~~yaml
databaseChangeLog:
  - property:
      name: appSchema
      value: dev_app

  - property:
      name: demoDisplayName
      value: "Khách hàng mẫu"

  - changeSet:
      id: seed-demo-customer-001
      author: training-team
      contextFilter: "@dev"
      changes:
        - insert:
            schemaName: ${appSchema}
            tableName: demo_customer
            columns:
              - column:
                  name: customer_code
                  value: DEMO-001
              - column:
                  name: display_name
                  value: "${demoDisplayName}"
      rollback:
        - delete:
            schemaName: ${appSchema}
            tableName: demo_customer
            where: "customer_code = 'DEMO-001'"
~~~

Giả định bảng **demo_customer** đã tồn tại, cột customer_code có ràng buộc duy nhất và chưa có bản ghi DEMO-001. Property demoDisplayName là giá trị **được nhóm kiểm soát**, không lấy từ request của người dùng. Khai báo dữ liệu theo cột giúp Liquibase có cơ sở sinh SQL đúng kiểu dữ liệu hơn so với việc tự nối chuỗi SQL thô, nhưng không miễn trừ việc kiểm tra giá trị được thay thế.

**Rollback delete** chỉ an toàn nếu dòng DEMO-001 do chính changeset này tạo và không bị dùng làm dữ liệu nghiệp vụ khác. Việc xóa mọi bản ghi có cùng mã mà không xác nhận nguồn gốc có thể gây mất dữ liệu. Với dữ liệu mẫu, hãy chọn khóa riêng biệt và kiểm tra trước khi chèn.

## 7. Thiết kế dữ liệu mẫu có thể kiểm chứng

Dữ liệu mẫu thường dùng để giúp lập trình viên và bộ test tái hiện các tình huống. Nó khác với **dữ liệu tham chiếu nghiệp vụ bắt buộc** như mã trạng thái đơn hàng hoặc danh mục loại tiền.

| Loại dữ liệu | Ví dụ | Chính sách migration đề xuất |
|---|---|---|
| Dữ liệu tham chiếu bắt buộc | Trạng thái ACTIVE, INACTIVE | Changeset chung, chạy trên môi trường cần dữ liệu đó |
| Dữ liệu demo | Khách hàng DEMO-001 | Chỉ tạo ở dev hoặc môi trường được cho phép tường minh |
| Fixture cho integration test | Đơn hàng dùng để thử một luồng | Có thể nạp bằng bộ công cụ test, reset được |
| Dữ liệu nghiệp vụ production | Khách hàng, giao dịch thật | Chuyển đổi bằng migration có kiểm chứng; không thay thế bằng seed demo |

Các vấn đề thường gặp khi dữ liệu mẫu được tạo thiếu kiểm soát:

- Chèn nhiều lần gây trùng khóa hoặc tạo bản ghi rác.
- Cấu hình context sai làm seed xuất hiện ở production.
- Đổi property làm cùng changeset có dữ liệu mới nhưng lịch sử đã ghi đã chạy.
- Rollback xóa bản ghi đã bị ứng dụng hoặc người kiểm thử sửa.
- Copy dữ liệu production về dev mà không ẩn danh.
- Test phụ thuộc vào một thứ tự chạy dữ liệu mẫu không được ghi lại.

Một bộ dữ liệu mẫu tốt nên có mã nhận diện rõ ràng, tập giá trị cố định, ràng buộc toàn vẹn, tính lặp lại, chính sách xóa và điều kiện môi trường cụ thể.

## 8. Dùng precondition để phát hiện dữ liệu đã tồn tại

Nếu cần dừng migration khi mã DEMO-001 đã tồn tại, có thể bổ sung precondition cho changeset seed:

~~~yaml
preConditions:
  - onFail: HALT
  - tableExists:
      schemaName: ${appSchema}
      tableName: demo_customer
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM ${appSchema}.demo_customer
        WHERE customer_code = 'DEMO-001'
~~~

Đây là **một đoạn cấu hình đặt trong changeset**, không phải changelog độc lập. Nó minh họa việc kiểm tra bảng tồn tại và số dòng có mã cụ thể bằng truy vấn chỉ đọc trước khi INSERT. Trong bài thực hành, phải gắn đoạn này vào changeset seed tương ứng, kiểm tra SQL và dùng schema đúng.

Với **onFail: HALT**, nếu đã có bản ghi, Liquibase dừng và không đánh dấu changeset như đã chạy thành công. Một số lựa chọn khác như MARK_RAN hoặc CONTINUE có thể có ích trong quy trình được thiết kế riêng, nhưng không nên dùng để che giấu tình trạng dữ liệu không khớp hoặc bỏ qua bất thường trên production.

Precondition không phải cơ chế ngăn chặn tranh chấp tuyệt đối: giữa lúc kiểm tra và INSERT, một tiến trình khác vẫn có thể chèn dữ liệu nếu không có biện pháp đồng bộ hay ràng buộc database. **Khóa duy nhất/primary key** và quy trình chạy migration có kiểm soát vẫn rất cần thiết.

## 9. Idempotency và giới hạn của cơ chế changeset

Một changeset thông thường được Liquibase đánh dấu đã thực thi trong **DATABASECHANGELOG**. Khi chạy update lần sau trên cùng database, Liquibase thường bỏ qua changeset đã được ghi nhận, nếu không có thuộc tính đặc biệt yêu cầu chạy lại.

Điều đó giúp tránh chạy INSERT seed lặp lại trong quy trình bình thường nhưng **không đồng nghĩa câu SQL tự có tính idempotent**. Nếu người vận hành xóa dòng lịch sử, đổi danh tính changeset, chạy script bên ngoài hoặc dữ liệu đã tồn tại do nguồn khác, câu INSERT vẫn có thể lỗi hoặc chèn trùng.

Idempotency là tính chất: cùng thao tác được thực hiện nhiều lần vẫn đưa hệ thống về kết quả mong muốn mà không phát sinh tác dụng phụ không hợp lệ. Có một số cách xây dựng tùy DBMS và yêu cầu:

- Khóa duy nhất và precondition để dừng khi dữ liệu không đúng kỳ vọng.
- Lệnh upsert của đúng hệ quản trị, với logic update rõ ràng.
- Xóa/nạp lại dữ liệu trong database test biệt lập khi thiết kế fixture.
- Migration dữ liệu tham chiếu có khóa ổn định, quy tắc cập nhật được review.

Ví dụ PostgreSQL có **INSERT ... ON CONFLICT**; MySQL có cách xử lý khác. Nếu dùng SQL đặc thù, cần kiểm tra trên đúng DBMS và tránh giả định một câu lệnh có thể chạy giống nhau ở mọi nơi.

**Không bật runAlways hoặc runOnChange cho seed dữ liệu chỉ để “tự cập nhật giá trị mẫu”.** Các thuộc tính này có thể khiến DML được chạy lại khi không cần, ghi đè thay đổi hoặc tạo dữ liệu trùng. Khi logic dữ liệu mẫu thay đổi đáng kể, nên tạo changeset mới hoặc quản lý fixture riêng cho môi trường test.

## 10. Phối hợp contexts và labels để giới hạn phạm vi

Liquibase hỗ trợ **contexts** và **labels** để chọn changeset phù hợp với lượt chạy.

**Contexts** thường được dùng để phân biệt môi trường hoặc mục đích chạy, chẳng hạn dev, test và production. **Labels** thường dùng để phân nhóm nghiệp vụ hoặc nhóm thay đổi, ví dụ demo-data hoặc reporting. Hai cơ chế có thể được kết hợp nhưng cần một quy ước thống nhất.

Ví dụ seed dữ liệu mẫu có context bắt buộc và label:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: seed-demo-setting
      author: training-team
      contextFilter: "@dev"
      labels: demo-data
      changes:
        - insert:
            tableName: app_setting
            columns:
              - column:
                  name: setting_key
                  value: demo.banner.enabled
              - column:
                  name: setting_value
                  value: "true"
~~~

Đây là một đoạn minh họa, giả định bảng app_setting đã tồn tại trong schema mặc định chính xác. Để sử dụng trong một dự án thực, cần bổ sung precondition, rollback và lựa chọn schema rõ ràng.

**Lưu ý quan trọng về context:** không thể cho rằng một changeset có context tự động bị loại khi không truyền context filter. Cú pháp **@dev** được dùng để yêu cầu dev được chỉ định tường minh, giúp giảm một dạng sai sót. Tuy nhiên, nếu chính pipeline production truyền dev nhầm, Liquibase không biết đó là sai mục đích. Vì vậy phải kiểm tra database đích và dùng quyền riêng.

**Lưu ý về label:** việc gắn label không có nghĩa changeset được tự động bảo vệ khỏi mọi lệnh update; hành vi phụ thuộc label filter được cung cấp. Đừng dùng label làm cơ chế bảo vệ duy nhất cho dữ liệu mẫu.

Khi một changeset cung cấp **schema cốt lõi** mà ứng dụng cần trên tất cả môi trường, không nên khiến nó bị vô tình loại bởi bộ lọc dành cho seed/demo.

## 11. Kiểm soát vòng đời property qua nhiều môi trường

Một property dùng cho tên schema có thể khác giữa dev/test/prod. Đó là trường hợp hợp lý nếu mỗi môi trường có database riêng hoặc schema tách biệt. Nhưng cần giữ ổn định giá trị **trong suốt vòng đời migration của từng database**, trừ khi nhóm chủ đích thực hiện một kế hoạch chuyển schema.

Ví dụ:

~~~text
DEV  -> database devdb,  appSchema = dev_app
TEST -> database testdb, appSchema = test_app
PROD -> database proddb, appSchema = app
~~~

Đây là dữ liệu ví dụ. Với từng môi trường, Liquibase đọc bảng DATABASECHANGELOG riêng và ghi checksum của changeset đã áp dụng. Nếu thay đổi appSchema giữa hai lần update trên **cùng một database**, không nên giả định Liquibase sẽ tự chuyển bảng hoặc chạy lại toàn bộ changeset ở schema mới.

Tùy cách thay thế và phiên bản Liquibase, việc thay property có thể tác động tới SQL được tính checksum hoặc tới kết quả nhận diện changeset. Kể cả không báo checksum, lịch sử “đã chạy” trên schema cũ vẫn có thể không phản ánh schema mới. Vì vậy:

1. Xác định schema và database đích từ trước.
2. Đặt property theo một nguồn cấu hình đáng tin cậy.
3. Kiểm tra giá trị đã được resolve trước lệnh update.
4. Không đổi tên schema lịch sử một cách âm thầm qua property.
5. Khi chuyển schema thật sự, dùng migration và kế hoạch dữ liệu riêng.

Chỉ cần một lỗi ánh xạ **prod → dev_app** là có thể khiến migration chạy trên schema không mong muốn dù file changelog được review đúng.

## 12. Quản lý property trong Spring Boot

Trong ứng dụng Spring Boot tích hợp Liquibase, các tham số changelog có thể được ánh xạ qua **spring.liquibase.parameters**. Ví dụ khái niệm:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    parameters:
      appSchema: "${APP_SCHEMA}"
~~~

Ở ví dụ này có **hai tầng thay thế khác nhau**:

1. Spring Boot đọc **APP_SCHEMA** từ cấu hình ứng dụng hoặc biến môi trường rồi phân giải placeholder **${APP_SCHEMA}**.
2. Tầng Liquibase nhận tham số changelog **appSchema** và dùng nó để phân giải **${appSchema}** trong changelog.

Hai tên **APP_SCHEMA** và **appSchema** có thể khác nhau. Việc dùng chữ hoa/chữ thường, cách ánh xạ và cơ chế ưu tiên phải được kiểm tra trên phiên bản Spring Boot thực tế. Không nên định nghĩa thêm một giá trị appSchema mâu thuẫn ở changelog nếu ứng dụng đã là nguồn cấu hình chính.

Nếu APP_SCHEMA không được cấp, ứng dụng nên **dừng sớm** thay vì dùng mặc định ngầm thành một schema nguy hiểm. Trong production, nên tránh fallback như một giá trị dev hoặc public nếu điều đó có thể làm migration trỏ sai mục tiêu.

Cấu hình profile của Spring Boot còn có thể điều khiển việc chạy Liquibase hoặc context, ví dụ:

~~~yaml
# application-dev.yaml
spring:
  liquibase:
    contexts: dev
~~~

Nếu pipeline CI/CD chịu trách nhiệm chạy migration production, hãy cân nhắc tắt Liquibase khi ứng dụng production khởi động:

~~~yaml
# application-prod.yaml
spring:
  liquibase:
    enabled: false
~~~

Các đoạn YAML này thuộc **hai file profile khác nhau** trong dự án minh họa. Profile phải thực sự được kích hoạt. Bảng DATABASECHANGELOGLOCK giúp điều phối lượt chạy đồng thời nhưng không thay thế quyết định ai sở hữu migration trong một bản phát hành.

## 13. Cấu hình Liquibase CLI và CI/CD

Với Liquibase CLI, có thể cung cấp đường dẫn changelog và JDBC URL trong cấu hình phát hành. Tham số changelog được cấp theo cơ chế mà phiên bản CLI hỗ trợ; cú pháp cụ thể có thể khác nhau giữa các bản, vì vậy hãy xác minh với tài liệu CLI cùng phiên bản và kiểm tra SQL sinh ra thay vì đoán thứ tự ưu tiên.

Một quy trình CI/CD có thể dùng bảng cấu hình được kiểm soát:

| Job | Database mục tiêu | appSchema | Context dùng cho seed |
|---|---|---|---|
| migration-dev | devdb | dev_app | dev |
| migration-test | testdb | test_app | test, chỉ khi cần |
| migration-prod | proddb | app | prod; không cấp dev |

Trong pipeline, nên giới hạn tập giá trị của appSchema và xác minh tên database, schema, tài khoản đã resolve. **Tên job không đủ để chứng minh kết nối đang ở đúng môi trường**: một biến môi trường sai hoặc secret sai vẫn có thể trỏ migration tới nơi khác.

Các bước kiểm tra thường có:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Ở các bản Liquibase khác nhau, lệnh xem trước SQL có thể được trình bày theo dạng update-sql hoặc updateSQL. Phải dùng đúng cú pháp cho phiên bản đang cài. Trước khi chạy, cần bảo đảm changelog parameter bắt buộc đã được cấp qua cấu hình tích hợp.

**validate** phát hiện một số lỗi changelog; **status** hỗ trợ xem lịch sử/pending changeset; **update-sql** cho phép review SQL dự kiến sau khi resolve thuộc tính. Không có lệnh nào trong ba lệnh này thay thế việc kiểm thử trên dữ liệu đại diện hoặc xác minh quyền/schema production.

Khi cần thực thi, chỉ chạy **update** sau khi đã qua bước kiểm tra và phê duyệt phù hợp. Đối với seed demo, nên có bước riêng hoặc context được chọn tường minh và xác minh đích.

## 14. Cách kiểm tra SQL sau khi thay thế

Không chỉ hỏi “property có tồn tại không”; cần xác minh câu SQL **cuối cùng** thực sự đúng.

Giả sử changelog chứa:

~~~sql
UPDATE ${appSchema}.app_setting
SET setting_value = 'true'
WHERE setting_key = 'demo.banner.enabled';
~~~

Ở dev, reviewer mong đợi:

~~~sql
UPDATE dev_app.app_setting
SET setting_value = 'true'
WHERE setting_key = 'demo.banner.enabled';
~~~

Ở production, nếu đây là changeset demo, kết quả kỳ vọng thường là **changeset không được chọn để chạy**. Nếu vì bất kỳ lý do gì câu SQL demo vẫn xuất hiện trong output dự kiến chạy ở production, pipeline phải dừng và điều tra context, property, schema và thứ tự cấu hình.

Các kiểm tra có thể tự động hóa trong pipeline:

1. Property bắt buộc không rỗng và thuộc allowlist.
2. SQL sau thay thế không còn placeholder chưa được giải quyết.
3. Tên database/schema trong SQL nằm trong danh sách được phép cho môi trường.
4. Không có câu thao tác demo trong job production.
5. Các câu DELETE/UPDATE có phạm vi điều kiện được review rõ.
6. Dữ liệu nhạy cảm không xuất hiện trong file SQL dự kiến hoặc log.
7. Migration đã chạy thử trên DBMS và phiên bản tương ứng.

**Cảnh báo về placeholder chưa giải quyết:** tùy phiên bản và nơi sử dụng, Liquibase có thể báo lỗi, giữ lại biểu thức chưa được thay hoặc gây lỗi SQL khi thực thi. Đừng dựa vào một hành vi mặc định chưa được kiểm chứng. Quy trình nên chủ động phát hiện và từ chối trước khi update.

## 15. SQL identifier, chữ hoa/chữ thường và quoting

Tên schema và bảng có thể nhạy cảm với quy tắc định danh của từng hệ quản trị. Ví dụ PostgreSQL chuyển identifier không đặt trong dấu nháy kép về chữ thường. Nếu appSchema chứa chữ hoa, dấu cách hoặc ký tự đặc biệt, SQL ghép trực tiếp có thể trỏ sai schema hoặc không hợp lệ.

Không nên coi việc bọc giá trị parameter bằng dấu nháy kép là biện pháp phòng SQL injection. Đó là cú pháp SQL của một DBMS, có quy tắc escape riêng. Thay vì cho phép tên schema tùy ý, một dự án nên chọn tên kỹ thuật đơn giản (ví dụ chữ thường và dấu gạch dưới) cùng allowlist rõ ràng.

Nếu tổ chức cần tên schema đặc biệt, hãy sử dụng khả năng khai báo schemaName của change type, kiểm tra SQL sinh ra trên DBMS đích và giới hạn giá trị từ nguồn cấu hình tin cậy.

## 16. Checksum và việc thay đổi property sau triển khai

Liquibase lưu thông tin về changeset đã chạy trong **DATABASECHANGELOG**, bao gồm checksum. Giá trị của một property có thể ảnh hưởng SQL hoặc đối tượng mà changeset tác động; hành vi kiểm tra checksum với giá trị được thay thế tùy vào loại change và phiên bản Liquibase.

Điều quan trọng về thiết kế là **không dùng thay property như một cách ngầm yêu cầu chạy lại changeset cũ**. Ví dụ thay demoDisplayName từ “Khách hàng mẫu” thành “Khách hàng thử nghiệm” trong cấu hình không chắc sẽ cập nhật bản ghi DEMO-001 đã được seed từ trước.

Nếu cần cập nhật dữ liệu tham chiếu đã triển khai, hãy tạo **changeset mới** mô tả thay đổi từ trạng thái cũ sang trạng thái mới và có kế hoạch rollback phù hợp. Không chỉnh sửa tùy tiện changeset lịch sử hoặc gọi clear-checksums để che giấu sự thay đổi.

Tương tự, **runOnChange** chủ yếu phù hợp với đối tượng định nghĩa có thể thay thế như view/function, không phải cách mặc định để cập nhật seed. DML thay đổi khi chạy lại có thể mất dữ liệu hoặc tạo dòng trùng. Nếu dùng runOnChange cho bất kỳ dữ liệu nào, phải chứng minh tính an toàn khi chạy lặp và ảnh hưởng trên từng môi trường.

## 17. Tránh đưa bí mật qua cơ chế thay thế

Property trong changelog có thể xuất hiện trong SQL được sinh ra, log debug, artifact CI hoặc công cụ review migration. Nếu dùng nó chứa mật khẩu, API key hoặc secret của ứng dụng, dữ liệu nhạy cảm có thể bị ghi ra ngoài nơi quản lý secret.

Phân biệt:

- **Thông tin kết nối Liquibase**: JDBC URL, username, password do môi trường thực thi cung cấp; password cần đến driver/database để xác thực.
- **Changelog parameter**: giá trị để định hình changeset, như appSchema, tên schema đối tượng hoặc một tham số được review.
- **Dữ liệu mẫu**: giá trị test hoặc seed được cho phép trong môi trường quy định.

Không đưa password vào một changeset INSERT chỉ vì muốn tiện khởi tạo tài khoản demo. Nếu nghiệp vụ thật sự cần dữ liệu bí mật, nên thiết kế luồng cấp phát và lưu trữ bằng hệ thống quản lý bí mật chuyên dụng, không tạo file SQL chứa secret.

Khi review update-sql, nhớ rằng SQL dự kiến có thể chứa giá trị dữ liệu. Quyền xem artifact và chính sách lưu giữ log phải tương ứng với độ nhạy của dữ liệu được ghi.

## 18. Rollback dữ liệu mẫu và tính nhất quán

Với dữ liệu mẫu, rollback không chỉ là viết một lệnh DELETE. Cần xem xét:

- Dòng được xóa có đúng là dòng mà changeset tạo ra không?
- Có khóa ngoại hoặc dữ liệu test khác phụ thuộc dòng đó không?
- Dòng có bị chỉnh sửa bởi bộ test hoặc người dùng kể từ lúc seed không?
- Có cần giữ một phần dữ liệu để tái hiện lỗi không?
- Có thể reset cả database test theo cơ chế riêng an toàn hơn rollback từng seed không?

Ví dụ rollback chỉ xóa mã DEMO-001:

~~~yaml
rollback:
  - delete:
      schemaName: ${appSchema}
      tableName: demo_customer
      where: "customer_code = 'DEMO-001'"
~~~

Nếu DEMO-001 đã được một tác vụ khác dùng và tạo quan hệ dữ liệu, lệnh xóa có thể thất bại do khóa ngoại hoặc gây mất mát. Với test tự động, cách ổn định thường là tạo database/schema test biệt lập và nạp fixture nhất quán trước mỗi bộ kiểm thử. Với production, dữ liệu thật không nên bị xóa qua rollback của changeset demo.

## 19. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| SQL chứa nguyên ${appSchema} | Parameter chưa được cấp hoặc sai tên | Kiểm tra nguồn cấu hình, tên và SQL đã resolve |
| Changelog chạy đúng nhưng bảng ở schema khác | appSchema hoặc default schema sai | Xác minh current database/schema, allowlist và kết quả update-sql |
| SQL lỗi khi giá trị chứa dấu nháy | Ghép trực tiếp giá trị vào chuỗi SQL | Dùng change type có cấu trúc, dữ liệu được kiểm soát và kiểm thử escaping |
| Dữ liệu demo xuất hiện ở production | Context/label filter hoặc đích kết nối sai | Dùng context bắt buộc, xác minh database, tách quyền và job |
| Chèn seed bị trùng khóa | Dữ liệu đã tồn tại, lịch sử bị thay đổi hoặc seed chạy từ luồng khác | Dùng khóa duy nhất, precondition và kiểm tra dữ liệu trước INSERT |
| Đổi property nhưng dòng seed không thay đổi | Changeset đã được ghi nhận là đã chạy | Tạo changeset mới hoặc quản lý fixture đúng mục đích |
| Rollback xóa cả dữ liệu không mong muốn | Điều kiện DELETE rộng hoặc mã seed không độc quyền | Dùng định danh riêng, kiểm tra nguồn gốc và phụ thuộc |
| Validate thành công nhưng update thất bại | SQL sau thay thế hoặc trạng thái dữ liệu không đúng | Xem update-sql, thử trên DBMS thật, kiểm tra precondition |
| Checksum không khớp | Changeset lịch sử bị sửa hoặc cách thay parameter ảnh hưởng kết quả | Đối chiếu lịch sử/commit; tránh sửa changeset đã triển khai |
| Mật khẩu lộ trong log | Secret bị đặt vào property hoặc dòng lệnh/log | Chuyển secret sang kho riêng, giới hạn log và vòng đời artifact |

Khi có lỗi, xác định **nguồn của giá trị** và **SQL đã được tạo ra**. Đừng sửa trực tiếp DATABASECHANGELOG hoặc dùng clear-checksums như giải pháp mặc định để tránh một lỗi cấu hình. Những thao tác quản trị lịch sử chỉ nên thực hiện khi đã đánh giá đầy đủ ảnh hưởng.

## 20. Quy trình thực hành có kiểm chứng

### Bước 1. Chuẩn bị môi trường an toàn

Tạo hoặc sử dụng một database dành riêng cho học tập, chẳng hạn **labdb**, với schema **dev_app** đã tồn tại. Dùng tài khoản migration có quyền vừa đủ. Không chạy ví dụ dữ liệu mẫu trên production.

### Bước 2. Tạo cấu trúc mẫu

Dùng changeset để tạo bảng demo_customer với khóa **customer_code** duy nhất và cột **display_name**. Chỉ áp dụng trên database học tập, xác minh bảng tạo ở đúng schema dev_app.

### Bước 3. Tạo property và seed

Khai báo appSchema = dev_app, demoDisplayName = “Khách hàng mẫu”; dùng changeset insert có **contextFilter: "@dev"**, id/author rõ ràng và rollback xóa đúng mã DEMO-001. Có thể thêm sqlCheck để dừng khi dữ liệu đã tồn tại.

### Bước 4. Xem kết quả thay thế

Chạy validate và update-sql với context dev. Kiểm tra tên schema trong SQL là dev_app, không có placeholder chưa resolve, không có thao tác nhắm tới bảng ngoài phạm vi.

### Bước 5. Thực thi và xác minh

Chạy update trên labdb và truy vấn:

~~~sql
SELECT customer_code, display_name
FROM dev_app.demo_customer
WHERE customer_code = 'DEMO-001';
~~~

Kết quả mong đợi: đúng một dòng với display_name bằng giá trị được cấp. Kiểm tra thêm dòng lịch sử changeset trong DATABASECHANGELOG.

### Bước 6. Thử chạy lại

Chạy update lần hai với changelog không đổi. Changeset seed thông thường phải được bỏ qua vì đã ghi lịch sử. Không nên tạo thêm dòng DEMO-001.

### Bước 7. Thử tình huống lỗi

Chọn một môi trường lab khác hoặc bản sao sạch để thử: thiếu appSchema, appSchema trỏ sai schema, thiếu context dev, hoặc mã DEMO-001 đã tồn tại. Quan sát validate, update-sql, precondition và lỗi DBMS. Mục tiêu là xác nhận quy trình **dừng trước khi tác động sai dữ liệu**.

### Bước 8. Kiểm thử rollback có điều kiện

Chỉ rollback khi đảm bảo DEMO-001 không có dữ liệu phụ thuộc và đã xác nhận đây là dòng mẫu do changeset tạo. Kiểm tra dòng được xóa đúng phạm vi và bảng lịch sử được Liquibase cập nhật theo hành vi rollback của phiên bản đang dùng.

## 21. Tình huống phân tích

**Tình huống A — Thay property sau khi đã seed:** Dev đã có DEMO-001 với display_name = “Khách hàng mẫu”. Một người đổi demoDisplayName thành “Khách hàng demo 2026” rồi chạy update. Dữ liệu có tự đổi không?

**Phân tích:** Không nên kỳ vọng điều đó. Changeset đã chạy có lịch sử riêng; đổi property không phải cơ chế cập nhật dữ liệu đáng tin cậy. Nếu cần biến đổi dữ liệu, tạo changeset mới hoặc cấu hình fixture test độc lập. Kiểm tra checksum và kết quả trên đúng phiên bản Liquibase.

**Tình huống B — Production lọt context dev:** Pipeline production vô tình truyền context dev và property appSchema = app. Một seed có contextFilter "@dev" liệu được bảo vệ không?

**Phân tích:** Nếu context dev được chọn tường minh, changeset có thể đủ điều kiện chạy. Phải có thêm rào chắn: quyền production không cấp cho job seed, bước xác minh database, kiểm tra allowlist và review SQL. Context không thay thế kiểm soát truy cập.

**Tình huống C — Dùng dữ liệu lạ trong SQL:** Property displayName được lấy từ một CSV do bên ngoài cung cấp. Giá trị có dấu nháy và ký tự đặc biệt, nhóm nối thẳng vào SQL INSERT.

**Phân tích:** Đây là đầu vào không đáng tin. Không đặt nó trong SQL migration bằng cách ghép chuỗi. Cần công cụ nhập dữ liệu có xác thực, kiểm soát kiểu, escaping/bind values phù hợp, xác minh đầu ra và phân quyền. Liquibase property substitution không phải API nhập liệu an toàn.

**Tình huống D — Thay schema trong cùng database:** Changelog đã chạy ở dev_app, sau đó nhóm đổi appSchema sang public rồi chạy update.

**Phân tích:** Không thể suy luận Liquibase tự di chuyển bảng sang public. Lịch sử changeset đã áp dụng vẫn tồn tại và có thể không phản ánh trạng thái schema mới. Cần migration đổi schema riêng, kiểm tra các phụ thuộc và lịch sử.

## 22. Checklist trước khi triển khai

- [ ] Mỗi property có mục đích rõ ràng và một nguồn cấu hình đáng tin cậy.
- [ ] Tên schema/bảng động được giới hạn bởi allowlist; không lấy từ input người dùng.
- [ ] SQL sau thay thế không còn placeholder chưa được giải quyết.
- [ ] Không đưa password, token hay dữ liệu bí mật vào changelog hoặc update-sql.
- [ ] Dữ liệu mẫu có mã ổn định, khóa duy nhất và điều kiện môi trường rõ ràng.
- [ ] Context demo cần được chọn tường minh; pipeline production không có quyền chạy seed demo.
- [ ] Precondition và ràng buộc database cùng bảo vệ dữ liệu khỏi trạng thái trùng hoặc bất thường.
- [ ] Không lạm dụng runOnChange/runAlways để cập nhật seed hoặc dữ liệu nghiệp vụ.
- [ ] Có SQL dự kiến được review và bài kiểm thử trên DBMS, dữ liệu đại diện.
- [ ] Rollback chỉ tác động đúng đối tượng/dòng do changeset chịu trách nhiệm.
- [ ] Changelog và changeset đã triển khai được giữ ổn định; thay đổi tiếp theo dùng changeset mới.
- [ ] Đã xác minh JDBC URL, database/schema thực tế và quyền tài khoản trước khi update.

## 23. Kết luận

Thay thế thuộc tính giúp Liquibase tái sử dụng changelog trên nhiều môi trường, nhưng **${propertyName} là một cơ chế thay thế giá trị trong quá trình xử lý changelog**, không phải cơ chế bind dữ liệu an toàn của JDBC. Rủi ro lớn nhất nằm ở chỗ một giá trị sai có thể thay đổi trực tiếp schema hoặc nội dung SQL mà migration tác động.

Để kiểm soát tốt, hãy giữ tên schema và giá trị động trong **tập cho phép**, dùng **change type có cấu trúc** cho dữ liệu mẫu, giới hạn seed bằng context và quyền, kiểm tra **SQL sau thay thế**, giữ changeset lịch sử ổn định, đồng thời kiểm chứng bằng precondition, ràng buộc database và kết quả thực thi. Khi đó, tham số hóa phục vụ đúng mục tiêu của module DATABASE_SCHEMA_MIGRATION_LIQUIBASE: triển khai schema và dữ liệu có thể dự đoán, truy vết và kiểm chứng qua dev, test, production cũng như trong Spring Boot hoặc CI/CD.

