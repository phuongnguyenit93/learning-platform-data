# Tách dữ liệu thử nghiệm khỏi thay đổi cấu trúc trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, người học tìm hiểu cách quản lý thay đổi schema và dữ liệu với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một yêu cầu đặc biệt quan trọng của chương **Bộ lọc thực thi** là **tách dữ liệu thử nghiệm khỏi các thay đổi cấu trúc cần áp dụng ở mọi môi trường**.

Một bảng khách hàng phải được tạo ở cả development, test, staging và production. Nhưng những bản ghi khách hàng giả lập, email dùng cho kiểm thử hoặc tài khoản demo không nên được đưa vào production. Liquibase cung cấp **contexts**, **labels**, cơ chế tổ chức **changelog riêng** và các điều kiện thực thi để giải quyết bài toán này. Cần kết hợp đúng các lớp bảo vệ: filter giúp chọn changeset, còn cấu trúc changelog và quy trình phát hành giúp giảm nguy cơ vô tình chọn nhầm.

## 1. Trước hết, phân loại thay đổi trong database

Không phải mọi câu INSERT đều là dữ liệu thử nghiệm, và không phải mọi changeset SQL đều là thay đổi cấu trúc.

| Loại thay đổi | Ví dụ | Môi trường nên chạy | Nguyên tắc quản lý |
|---|---|---|---|
| **Schema/DDL** | CREATE TABLE, ADD COLUMN, CREATE INDEX, ADD CONSTRAINT | Tất cả môi trường cần cùng mô hình nghiệp vụ | Changeset dùng chung, không ràng buộc vào test |
| **Dữ liệu tham chiếu bắt buộc** | Danh mục trạng thái ACTIVE/SUSPENDED, loại tiền tệ được hệ thống hỗ trợ | Mọi môi trường dùng chức năng đó, bao gồm production | Changeset tham chiếu được review, có kiểm soát phiên bản |
| **Dữ liệu thử nghiệm/fixture** | Khách hàng giả lập, email example.invalid, dữ liệu phục vụ integration test | Chỉ môi trường test/dev được cho phép | Changelog/changeset riêng, filter rõ ràng, có cơ chế dọn dẹp |
| **Dữ liệu demo tùy chọn** | Tài khoản trình diễn, bộ mẫu cho sandbox | Môi trường demo được chỉ định | Không tự động đưa vào production |
| **Dữ liệu vận hành thật** | Đơn hàng của khách hàng, dữ liệu giao dịch | Tùy chính sách ứng dụng và quy trình vận hành | Không coi là fixture và không xóa bởi script test |

**Mục tiêu không phải “cấm DML trên production”.** DML dùng để khởi tạo dữ liệu tham chiếu cần thiết vẫn có thể là một phần của migration production. Mục tiêu là nhận diện và loại trừ những bản ghi chỉ phục vụ kiểm thử, tránh làm bẩn dữ liệu thật hoặc tạo lỗ hổng vận hành.

### 1.1. Điều gì xảy ra nếu dữ liệu thử nghiệm lọt vào production?

Các hậu quả thường gặp:

- Báo cáo doanh thu, số lượng khách hàng hoặc thống kê vận hành bị sai do dữ liệu giả.
- Tài khoản demo vô tình nhận quyền, tương tác với API hoặc được hiển thị cho người dùng thật.
- Dữ liệu mẫu bị ứng dụng gửi thông báo, tính phí, đồng bộ hoặc xử lý như dữ liệu nghiệp vụ.
- Migration tiếp theo phụ thuộc vào những fixture đáng lẽ không tồn tại ở production.
- Quy trình dọn dữ liệu có thể xóa nhầm bản ghi thật nếu không có định danh an toàn.
- Không thể dễ dàng phân biệt bản ghi do test tạo với bản ghi production sau khi dữ liệu lan sang hệ thống khác.

Vì vậy, cần ngăn dữ liệu thử nghiệm **ngay tại điểm lựa chọn changeset**, đồng thời kiểm tra kết quả cuối cùng của quá trình triển khai.

## 2. Bốn lớp để tách thay đổi cấu trúc và dữ liệu thử nghiệm

Có thể thiết kế theo các lớp bổ trợ nhau:

1. **Tách file:** thay đổi schema, dữ liệu tham chiếu và dữ liệu thử nghiệm nằm ở các changelog khác nhau.
2. **Tách root changelog:** production chỉ include schema và dữ liệu tham chiếu; môi trường test mới include test seed.
3. **Gắn execution filter:** changeset fixture khai báo context và label dành cho test, đồng thời runner truyền filter phù hợp.
4. **Kiểm soát quy trình:** pipeline xác thực môi trường đích, review update-sql, chạy hậu kiểm và giới hạn quyền kết nối.

Mỗi lớp phục vụ một mục đích khác nhau. Nếu chỉ dùng context nhưng production chạy Liquibase mà **không truyền context filter**, các changeset có context thông thường vẫn có thể được xét chạy. Nếu chỉ phân tách file nhưng pipeline dùng nhầm root changelog, fixture cũng có thể được đưa vào database đích. Kết hợp các lớp giảm xác suất sai sót.

## 3. Execution contexts: chọn changeset theo mục đích

Một changeset có thể gắn context expression. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: test-001-seed-customer
      author: migration-team
      contextFilter: test
      changes:
        - insert:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  valueNumeric: 900000001
              - column:
                  name: email
                  value: liquibase-fixture-001@example.invalid
              - column:
                  name: status
                  value: ACTIVE
~~~

Khi runner dùng **--context-filter=test**, changeset gắn context test sẽ phù hợp để thực thi. Khi runner dùng **--context-filter=prod**, changeset này bị loại khỏi tập changeset dự kiến.

Tuy nhiên, có một điểm dễ gây nhầm lẫn:

> **Không truyền context filter không đồng nghĩa với chỉ chạy những changeset không có context.** Với context thông thường, Liquibase có thể cho phép chạy các changeset đó khi không có filter tương ứng.

Do đó, chỉ đặt contextFilter: test **không đủ để bảo đảm** một root changelog chứa cả fixture sẽ an toàn khi production quên truyền filter.

### 3.1. Context bắt buộc khai báo tường minh bằng tiền tố @

Liquibase hỗ trợ tiền tố **@** trong context expression để yêu cầu context được cung cấp tường minh khi chạy. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: test-001-seed-customer
      author: migration-team
      contextFilter: "@test"
      changes:
        - insert:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  valueNumeric: 900000001
              - column:
                  name: email
                  value: liquibase-fixture-001@example.invalid
              - column:
                  name: status
                  value: ACTIVE
~~~

Với biểu thức @test, changeset được thiết kế để không chạy khi runner bỏ qua context filter; nó chỉ phù hợp khi context test được chỉ định. Kiểm tra cú pháp, khả năng hỗ trợ thuộc tính contextFilter và cách đánh giá expression trong phiên bản Liquibase đang dùng; các phiên bản cũ có thể dùng tên thuộc tính context.

Cần hiểu rõ đây là **hàng rào cấu hình**, không phải ranh giới bảo mật tuyệt đối. Một người có quyền chạy migration với context test trên production vẫn có thể chọn sai changeset. Vì vậy, hãy tiếp tục tách root changelog và xác thực môi trường tại pipeline.

### 3.2. Changeset cấu trúc để không gắn context

Thông thường, thay đổi schema bắt buộc cho ứng dụng không cần context dành riêng cho môi trường:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: schema-001-create-customer
      author: migration-team
      changes:
        - createTable:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
~~~

Nhờ đó, nếu cùng file schema được include trong root dành cho test và production, changeset cấu trúc có thể chạy trên cả hai. Filter context test dùng để bổ sung dữ liệu fixture, **không biến schema thành đối tượng chỉ tồn tại trong test**.

## 4. Labels: phân loại changeset theo chức năng

Context thường mô tả môi trường hoặc hoàn cảnh thực thi: test, dev, prod, integration. **Label** dùng để gắn nhãn theo mục đích hoặc nhóm chức năng: fixture, demo-data, audit, migration-group.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: test-001-seed-customer
      author: migration-team
      contextFilter: "@test"
      labels: test-data
      changes:
        - insert:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  valueNumeric: 900000001
              - column:
                  name: email
                  value: liquibase-fixture-001@example.invalid
              - column:
                  name: status
                  value: ACTIVE
~~~

Runner test có thể chọn:

~~~bash
liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  update-sql
~~~

Hai filter là hai chiều lựa chọn riêng, đều phải được thỏa theo quy tắc Liquibase. Changeset schema **không có context và không có label** vẫn thường đủ điều kiện chạy; changeset fixture có @test và test-data cần filter đúng để được chọn.

**Lưu ý quan trọng:** cũng như context thông thường, chỉ gắn labels: test-data không bảo đảm changeset bị bỏ qua nếu người chạy **không truyền label filter**. Label filter là công cụ lựa chọn, không phải một cơ chế cách ly tự động.

### 4.1. Khi nào dùng context, khi nào dùng label?

| Câu hỏi | Cơ chế thường phù hợp |
|---|---|
| Changeset này chỉ dành cho môi trường test? | Context @test và root changelog test riêng |
| Changeset phục vụ dữ liệu integration fixture? | Label test-data hoặc fixture |
| Chỉ chạy chức năng audit trên môi trường được chỉ định? | Context và/hoặc label, tùy chính sách triển khai |
| Changeset thuộc luồng nghiệp vụ nhưng cần chạy mọi nơi? | Không cần filter chỉ để đặt tên nhóm |
| Kiểm tra điều kiện bảng đã tồn tại? | Precondition, không thay thế bằng context |

Cả context và label hỗ trợ biểu thức logic trong trường hợp cần chọn nhiều nhóm. Khi sử dụng biểu thức AND, OR hoặc NOT, cần đặt ngoặc và kiểm thử bộ lọc cụ thể theo phiên bản. Đừng biến hệ thống filter thành tập biểu thức phức tạp khó đọc nếu chỉ cần một quy tắc test rõ ràng.

## 5. Kiến trúc changelog đề xuất: chung phần lõi, tách phần test

Một cách tổ chức dễ review:

~~~text
db/changelog/
├── prod-root.yaml
├── test-root.yaml
├── schema.yaml
├── reference-data.yaml
└── test-seed.yaml
~~~

Các file có vai trò:

- **schema.yaml:** tạo và thay đổi cấu trúc cần ở cả test và production.
- **reference-data.yaml:** dữ liệu danh mục bắt buộc để ứng dụng hoạt động, có thể triển khai production.
- **test-seed.yaml:** dữ liệu giả lập chỉ phục vụ test, có context và label bảo vệ.
- **prod-root.yaml:** chỉ include schema và dữ liệu tham chiếu.
- **test-root.yaml:** include cùng schema/dữ liệu tham chiếu, sau đó include test seed.

### 5.1. Root changelog dùng cho production

~~~yaml
databaseChangeLog:
  - include:
      file: schema.yaml
      relativeToChangelogFile: true

  - include:
      file: reference-data.yaml
      relativeToChangelogFile: true
~~~

File này **không include test-seed.yaml**. Dù runner có quên context filter, những changeset fixture trong test-seed.yaml vẫn không được nạp qua root production.

### 5.2. Root changelog dùng cho test

~~~yaml
databaseChangeLog:
  - include:
      file: schema.yaml
      relativeToChangelogFile: true

  - include:
      file: reference-data.yaml
      relativeToChangelogFile: true

  - include:
      file: test-seed.yaml
      relativeToChangelogFile: true
~~~

Hai root đặt cùng thư mục và include cùng những file schema/reference. Điều này giúp định danh đường dẫn của changeset dùng chung ổn định hơn so với việc sao chép toàn bộ nội dung sang hai cây changelog khác nhau.

**Không nhân bản changeset schema thành hai bản riêng cho prod và test.** Duy trì hai phiên bản DDL dễ dẫn đến schema drift và tăng công sức kiểm thử.

### 5.3. Vì sao không chỉ dùng một root và context test?

Một root chứa cả schema và test seed vẫn có thể hoạt động nếu pipeline luôn truyền đúng filter; tuy nhiên chỉ cần thiếu filter hoặc chọn nhầm context là có nguy cơ đưa fixture vào production. Với một root riêng không include fixture, production có thêm lớp bảo vệ độc lập với cách runner truyền tham số.

Nếu tổ chức có lý do sử dụng một root chung, cần áp dụng context @test, label, điều kiện môi trường, guard trong CI/CD và kiểm thử chặt chẽ. Trong các hệ thống cần giảm rủi ro, cách tách root thường dễ hiểu và dễ kiểm toán hơn.

## 6. Ví dụ dữ liệu tham chiếu và dữ liệu thử nghiệm

### 6.1. Dữ liệu tham chiếu bắt buộc

Giả sử schema còn có bảng account_status_catalog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: schema-002-create-status-catalog
      author: migration-team
      changes:
        - createTable:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  type: VARCHAR(20)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
~~~

File reference-data.yaml cung cấp các trạng thái cần thiết cho ứng dụng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: ref-001-account-statuses
      author: migration-team
      changes:
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: ACTIVE
              - column:
                  name: display_name
                  value: Active
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: SUSPENDED
              - column:
                  name: display_name
                  value: Suspended
~~~

Các bản ghi ACTIVE/SUSPENDED phục vụ nghiệp vụ, vì vậy có thể được include ở cả hai root. Chúng không phải dữ liệu test chỉ vì được tạo bằng lệnh INSERT.

Khi danh mục thay đổi về sau, tạo changeset mới để cập nhật dữ liệu tham chiếu; không âm thầm chỉnh sửa changeset đã triển khai.

### 6.2. Dữ liệu fixture chỉ dành cho test

File test-seed.yaml chứa dữ liệu giả lập được nhận diện rõ ràng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fixture-001-customer
      author: migration-team
      contextFilter: "@test"
      labels: test-data
      changes:
        - insert:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  valueNumeric: 900000001
              - column:
                  name: email
                  value: liquibase-fixture-001@example.invalid
              - column:
                  name: status
                  value: ACTIVE
      rollback:
        - delete:
            tableName: customer_account
            where: "id = 900000001 AND email = 'liquibase-fixture-001@example.invalid'"
~~~

Ví dụ sử dụng email ở miền example.invalid để tránh nhầm với địa chỉ liên hệ thật và một ID được dành riêng cho fixture. Trong hệ thống thực tế, nên có quy tắc dành riêng dải ID hoặc marker cho dữ liệu thử nghiệm; không giả định một ID bất kỳ chắc chắn chưa được dùng.

Phần rollback xóa đúng bản ghi fixture do changeset thêm vào. **Không dùng WHERE mơ hồ** như email LIKE '%test%' để dọn dữ liệu, vì có thể ảnh hưởng bản ghi thật. Nếu fixture tạo nhiều bảng và quan hệ khóa ngoại, cần thiết kế thứ tự rollback phù hợp; không tự xem câu DELETE đơn lẻ là đủ.

### 6.3. Không trộn DDL và fixture trong một changeset

Không nên viết một changeset vừa tạo bảng customer_account vừa chèn người dùng giả. Vì khi production cần tạo bảng, nó không thể tách phần INSERT test khỏi changeset đó một cách sạch sẽ.

Mẫu tách:

~~~text
schema-001-create-customer  [DDL; mọi môi trường]
ref-001-account-statuses   [Reference DML; mọi môi trường cần dùng]
fixture-001-customer       [Test DML; @test + test-data; chỉ test root]
~~~

Mỗi changeset có trách nhiệm riêng, dễ review, kiểm chứng và rollback. Khi một fixture cần cập nhật, dùng changeset fixture mới hoặc reset một database test dùng một lần, thay vì sửa migration schema lịch sử.

## 7. Bộ lọc không đồng nghĩa precondition

Một số nhóm dùng precondition để kiểm tra tên database hoặc schema trước khi chèn dữ liệu. Đây có thể là lớp kiểm tra bổ sung, nhưng khác bản chất so với context và label:

- **Context/label:** quyết định changeset nào được chọn theo bộ lọc của Liquibase.
- **Precondition:** kiểm tra trạng thái hoặc môi trường ở thời điểm changeset được xét thực thi.
- **Root changelog:** quyết định file nào được đưa vào tập changeset ban đầu.
- **Quyền kết nối/pipeline:** giới hạn nơi job thực sự được phép thay đổi.

Ví dụ, với **PostgreSQL** và quy ước database test có tên bắt đầu bằng integration_test_, một changeset fixture có thể thêm guard:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fixture-002-extra-customer
      author: migration-team
      contextFilter: "@test"
      labels: test-data
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "1"
            sql: "SELECT CASE WHEN current_database() LIKE 'integration_test_%' THEN 1 ELSE 0 END"
      changes:
        - insert:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  valueNumeric: 900000002
              - column:
                  name: email
                  value: liquibase-fixture-002@example.invalid
              - column:
                  name: status
                  value: ACTIVE
~~~

Điều kiện chỉ có ý nghĩa khi quy ước tên database được tổ chức thực thi thật sự bảo đảm. Hàm current_database() và biểu thức SQL ví dụ là của PostgreSQL; cần điều chỉnh khi dùng DBMS khác. Không sao chép guard này vào hệ thống có tên database khác mà chưa kiểm tra.

Ở đây onFail: HALT giúp **dừng migration** nếu guard không đạt, thay vì đánh dấu fixture là đã chạy. Nhưng nó không ngăn người có quyền cấu hình sai hoặc sửa source code. Precondition không phải thay thế cho quyền database và chính sách triển khai.

## 8. Chạy Liquibase theo đúng bộ lọc

Giả sử runner đã được cấu hình kết nối đến database đích bằng secret manager hoặc cấu hình được cấp quyền phù hợp. Các lệnh dưới đây chỉ minh họa tham số changelog và filter; không nên đưa mật khẩu vào command history.

### 8.1. Kiểm tra và chạy production

~~~bash
liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  validate

liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  status --verbose

liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  update-sql
~~~

Sau khi đã review SQL và database đích, job production có thể thực thi:

~~~bash
liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  update
~~~

Vì prod-root.yaml không include test-seed.yaml, không có fixture từ file đó trong tập changeset của job. Context prod còn giúp việc sử dụng filter tại production trở thành hành vi tường minh, dễ kiểm toán.

### 8.2. Kiểm tra và chạy test

~~~bash
liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  validate

liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  update-sql
~~~

Kiểm tra SQL dự kiến gồm cả các thay đổi schema/reference và INSERT của fixture. Nếu đúng database test, chạy:

~~~bash
liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  update
~~~

Với những changeset schema và reference không gắn context/label, Liquibase vẫn xét thực thi khi không bị loại bởi bộ lọc. Changeset fixture được chọn nhờ cả context test và label test-data.

**Nguyên tắc nhất quán:** tập filter dùng để preview SQL phải là tập được dùng cho update thực tế. Không xem update-sql với context=test rồi chạy update với filter trống hoặc context=prod. Mọi job cần xác nhận URL/catalog/schema trước khi thực thi.

### 8.3. Bảng hành vi cần ghi nhớ

| Changelog và filter | Schema/reference | Fixture @test + test-data | Ghi chú |
|---|---|---|---|
| prod-root.yaml, context=prod | Có | Không | Fixture không được include từ root |
| test-root.yaml, context=test, label=test-data | Có | Có | Luồng test dự kiến |
| test-root.yaml, context=prod | Có | Không | @test không phù hợp |
| test-root.yaml, không có context filter | Có | Không, nhờ @test | Kiểm tra theo phiên bản hỗ trợ @ |
| Root chung có fixture context thường test, không truyền filter | Có | **Có thể có** | Thiết kế rủi ro, không nên dùng cho production |

Bảng trên minh họa ý nghĩa của cấu trúc đề xuất. Kết quả thực tế phải được thử với đúng phiên bản Liquibase, DBMS, các biểu thức context/label và cấu hình đã sử dụng. Không dùng bảng như thay thế cho kiểm tra SQL thực tế.

## 9. Cấu hình theo môi trường trong Spring Boot

Spring Boot có thể chạy Liquibase khi khởi động ứng dụng, với đường dẫn changelog và context lấy từ cấu hình theo profile.

Ví dụ cấu hình cho production, trong application-prod.yml:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/prod-root.yaml
    contexts: prod
~~~

Cấu hình cho một môi trường integration test được kiểm soát, trong application-test.yml:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/test-root.yaml
    contexts: test
    label-filter: test-data
~~~

Những điểm cần hiểu:

- **Spring profile** chọn cấu hình Spring được nạp; nó không tự biến thành Liquibase context nếu không cấu hình ánh xạ.
- **spring.liquibase.change-log** quyết định root changelog.
- **spring.liquibase.contexts** cung cấp context filter cho Liquibase.
- **spring.liquibase.label-filter** có thể cung cấp label filter trong các phiên bản Spring Boot hỗ trợ thuộc tính đó; cần đối chiếu tài liệu phiên bản dự án.
- Khi các instance cùng database chạy Liquibase, chúng phải dùng cùng bộ bảng metadata và cấu hình migration nhất quán; lock không sửa sai lệch root changelog hoặc filter.

Trong nhiều hệ thống production, chạy migration bằng **một job CI/CD riêng** thường dễ kiểm soát hơn để ứng dụng tự chạy ở mỗi replica. Khi pipeline đã phụ trách migration, cân nhắc tắt tự động chạy Liquibase ở instance production theo kiến trúc đã chọn. Không bật đồng thời hai luồng cấu hình khác nhau cùng cập nhật một database.

### 9.1. Thực thi test bằng database tạm

Đối với integration test, có thể tạo database mới cho từng pipeline hoặc bộ kiểm thử. Quy trình:

1. Cấp database tạm với schema rỗng.
2. Chạy test-root.yaml cùng context=test và label=test-data.
3. Chạy integration tests với fixture xác định trước.
4. Kiểm tra kết quả.
5. Hủy database tạm theo chính sách môi trường.

Cách này giảm nguy cơ dữ liệu fixture tồn tại dai dẳng và giúp phát hiện lỗi migration từ đầu. Tuy nhiên cần bảo đảm job test không thể nhận URL production hoặc thông tin xác thực production.

## 10. CI/CD: ngăn sai sót từ cấu hình pipeline

Một pipeline có thể tách các job:

~~~text
                     Commit changelog
                             |
                             v
                   Validate + review thay đổi
                             |
              +--------------+--------------+
              |                             |
              v                             v
        TEST MIGRATION                 PROD MIGRATION
        Database tạm                   Database thật
        test-root.yaml                 prod-root.yaml
        context=test                   context=prod
        label=test-data                không include test seed
              |                             |
              v                             v
        update-sql                    update-sql
              |                             |
              v                             v
        update + test                 Phê duyệt / update
              |                             |
              v                             v
        Kiểm tra fixture              Xác nhận fixture vắng mặt
~~~

Điểm kiểm soát nên có:

- Job production chỉ cho phép root changelog production theo cấu hình version-controlled.
- URL/database/schema đích được xác nhận trước khi chạy; không lấy tùy ý từ tham số chưa kiểm soát.
- Secret và database role được tách giữa test và production.
- Job production không tự nạp cấu hình môi trường test hoặc dùng context=test.
- Review diff của changelog để thấy rõ changeset nào là schema/reference, changeset nào là fixture.
- Chạy update-sql với chính xác cấu hình sẽ dùng cho update và kiểm tra không có INSERT fixture.
- Ghi log phiên bản ứng dụng, commit changelog, bộ lọc, thời điểm và kết quả triển khai.
- Có hậu kiểm dữ liệu để phát hiện việc fixture vô tình tồn tại ở production.

**Bộ lọc Liquibase không phải cơ chế phân quyền.** Người có quyền truy cập production và được phép chạy changelog test vẫn có thể gây tác động. Vì vậy, cần giới hạn quyền kết nối, môi trường chạy và cơ chế phê duyệt ngoài bản thân Liquibase.

## 11. Cách kiểm chứng sau migration

Việc lệnh Liquibase update thành công không đủ để khẳng định dữ liệu đã được tách đúng. Cần kiểm tra cả lịch sử và dữ liệu thực tế.

### 11.1. Kiểm tra các changeset đã được ghi nhận

Liquibase có thể liệt kê lịch sử:

~~~bash
liquibase history
liquibase status --verbose
~~~

Có thể truy vấn DATABASECHANGELOG trên database đích để kiểm tra id, author, filename, dateexecuted và exectype của những changeset liên quan. Cấu trúc bảng metadata và vị trí schema phụ thuộc cấu hình, nên xác định chính xác schema chứa DATABASECHANGELOG trước khi truy vấn.

Kỳ vọng:

- Production ghi nhận changeset schema và reference cần thiết, **không có fixture-001-customer**.
- Test ghi nhận schema, reference và fixture phù hợp.
- Không có changeset cũ bất ngờ trở lại trạng thái pending do đổi id/author/file path hoặc dùng sai bộ metadata.

### 11.2. Kiểm tra dữ liệu trong bảng nghiệp vụ

Với ví dụ customer_account:

~~~sql
SELECT COUNT(*) AS fixture_count
FROM customer_account
WHERE id = 900000001
  AND email = 'liquibase-fixture-001@example.invalid';
~~~

Kỳ vọng fixture_count = 0 trên production và = 1 trên database test sau khi seed thành công. Với hệ thống thực tế, nên có nhiều chỉ báo hơn một ID, chẳng hạn cột đánh dấu dữ liệu fixture, danh sách ID dành riêng hoặc kiểm tra tập dữ liệu đã định nghĩa.

Cần tránh truy vấn hoặc điều kiện dựa trên những từ khóa chung như tên LIKE '%test%' vì có thể có dữ liệu thật trùng mẫu. Các kết quả hậu kiểm quan trọng nên được tự động hóa và lưu cùng log migration.

### 11.3. Kiểm tra schema tương đương giữa môi trường

Tách fixture **không có nghĩa test và production phải có schema khác nhau**. Schema nghiệp vụ chính nên được tạo từ cùng changelog, để integration test phản ánh cấu trúc sẽ dùng ở production.

Có thể kiểm tra snapshot/diff hoặc truy vấn catalog để xác nhận các bảng, cột, constraint và index cần thiết tương đương; không nhất thiết toàn bộ dữ liệu hoặc thông số hiệu năng là như nhau. Khi có khác biệt có chủ đích, cần ghi nhận và tránh để test phụ thuộc vào schema chỉ tồn tại ở test mà production không có.

## 12. Rollback và dọn dữ liệu thử nghiệm

Fixture cần có chính sách vòng đời rõ ràng. Có hai chiến lược phổ biến:

- **Database thử nghiệm dùng một lần:** tạo database trống, chạy migration và fixture, chạy test rồi hủy toàn bộ database. Đây thường là phương án đơn giản nhất cho integration test cô lập.
- **Database test dùng lâu dài:** thiết kế changeset rollback hoặc quy trình reset dữ liệu có kiểm soát. Xác định rõ bảng phụ thuộc, ID fixture, thứ tự xóa và tác động đến dữ liệu do test tạo thêm.

Cần phân biệt rollback changeset fixture với rollback thay đổi schema. Nếu rollback schema xóa bảng chứa dữ liệu thật hoặc dữ liệu kiểm thử đang dùng, hậu quả có thể rộng hơn dự kiến.

Trước khi dùng rollback của ví dụ, kiểm tra:

1. Bản ghi được xóa đúng là bản ghi fixture do changeset quản lý.
2. Không có bản ghi khác tham chiếu fixture bằng khóa ngoại hoặc quan hệ nghiệp vụ.
3. Điều kiện WHERE đủ cụ thể để không xóa dữ liệu khác.
4. Các thay đổi sau fixture không khiến việc khôi phục về trạng thái cũ trở nên không an toàn.
5. Nếu rollback không khả thi, có phương án reset database test và tạo lại từ changelog.

**Không dùng rollback dữ liệu test như biện pháp khẩn cấp mặc định ở production** nếu trước đó đã vô tình chèn fixture. Cần đánh giá liệu fixture đã được ứng dụng xử lý, sao chép hoặc liên kết với dữ liệu thật hay chưa, rồi lập một kế hoạch loại bỏ có kiểm chứng.

## 13. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý ưu tiên |
|---|---|---|
| Fixture xuất hiện ở production | Root production include test seed, thiếu filter hoặc dùng nhầm context | Dừng triển khai, xác định phạm vi tác động, lập phương án sửa dữ liệu có kiểm chứng |
| Test chạy schema nhưng không có fixture | Test-root chưa include seed, context/label không khớp hoặc precondition HALT | Kiểm tra root, filter, SQL dự kiến và log |
| Test dùng schema khác production | Tách đôi DDL rồi mỗi bên phát triển riêng | Dùng chung file schema và kiểm tra drift |
| Dữ liệu danh mục bị bỏ qua ở production | Nhầm reference data thành test seed | Chuyển reference data vào changelog dùng chung và có migration hợp lệ |
| Production báo lỗi checksum | Sửa changeset lịch sử sau khi đã deploy hoặc thay đổi file path | Điều tra lịch sử, khôi phục changeset cũ và thêm changeset mới |
| Seed bị trùng ID/unique key | Dữ liệu fixture đã có, database test không được reset | Dùng database tạm hoặc quản lý dữ liệu fixture theo cách có kiểm chứng |
| Chạy không truyền context nhưng vẫn có test data | Dùng context thường mà không có @ hoặc tách root | Dùng root không include fixture và yêu cầu context tường minh |
| Rollback fixture xóa quá nhiều dòng | Điều kiện DELETE mơ hồ | Khôi phục từ backup hoặc quy trình phục hồi; sửa chiến lược marker |
| DBMS khác không hiểu SQL guard | Precondition dùng hàm riêng PostgreSQL | Điều chỉnh theo DBMS hoặc bỏ guard khi đã có cơ chế an toàn tương đương |
| Chạy đúng filter nhưng sai database | URL/credential trỏ sai môi trường | Kiểm tra và giới hạn quyền kết nối trong pipeline |

### 13.1. Nếu dữ liệu test đã lọt vào production

Không tự ý chạy câu DELETE rộng. Hãy:

1. Dừng job tiếp theo có nguy cơ lặp lại thao tác.
2. Xác nhận những changeset fixture đã chạy và bản ghi nào được tạo.
3. Kiểm tra các hệ thống downstream, bảng phụ thuộc, log và tác động nghiệp vụ.
4. Xác định ID/marker chính xác của dữ liệu test, có backup và kế hoạch hoàn tác nếu cần.
5. Thực hiện chỉnh sửa có kiểm soát (changeset sửa chữa hoặc thủ tục dữ liệu được phê duyệt) và hậu kiểm.
6. Sửa root changelog, filter, guard và quyền pipeline để ngăn tái diễn.
7. Ghi nhận sự cố; không xóa tùy tiện lịch sử DATABASECHANGELOG để tạo cảm giác migration “chưa từng chạy”.

## 14. Bài thực hành end-to-end

**Mục tiêu:** cùng một bộ schema tạo ra bảng customer_account trên hai database thử nghiệm độc lập; chỉ database test có fixture. Không chạy thử nghiệm này trên production.

### Bước 1. Chuẩn bị các file changelog

Tạo cấu trúc theo phần 5. Trong schema.yaml định nghĩa bảng customer_account và account_status_catalog. Trong reference-data.yaml thêm các trạng thái nghiệp vụ ACTIVE và SUSPENDED. Trong test-seed.yaml định nghĩa fixture-001-customer với contextFilter: "@test", labels: test-data và rollback cụ thể.

Hai root phải cùng include các file schema và reference; chỉ test-root.yaml include test-seed.yaml.

### Bước 2. Chạy môi trường A như production giả lập

Trên database thử nghiệm A, dùng prod-root.yaml và context prod:

~~~bash
liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  validate

liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  update-sql

liquibase --changelog-file=db/changelog/prod-root.yaml \
  --context-filter=prod \
  update
~~~

Kiểm tra bảng customer_account tồn tại và **không có** email fixture. Xác nhận danh mục trạng thái có dữ liệu tham chiếu cần thiết.

### Bước 3. Chạy môi trường B như test

Trên database thử nghiệm B độc lập, dùng test-root.yaml và hai filter:

~~~bash
liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  validate

liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  update-sql

liquibase --changelog-file=db/changelog/test-root.yaml \
  --context-filter=test \
  --label-filter=test-data \
  update
~~~

Kiểm tra customer_account có fixture-001, dữ liệu tham chiếu được tạo và schema tương đương với database A trong những đối tượng dùng chung.

### Bước 4. Thử thay đổi filter một cách an toàn

Trên database test mới hoặc bản sao rỗng, dùng test-root.yaml nhưng chỉ định --context-filter=prod. Quan sát update-sql và xác nhận fixture @test không nằm trong những changeset được chọn. Không sử dụng URL production thật để thử hành vi này.

Sau đó thử bỏ hẳn context filter trên một database lab mới, kiểm tra hành vi @test của phiên bản Liquibase đang dùng. So sánh với một changeset contextFilter: test thông thường để thấy vì sao filter trống là rủi ro nếu không có @ hoặc không tách root.

### Bước 5. Tổng kết

Trả lời được các câu hỏi:

- Tại sao cả A và B đều cần các changeset schema?
- Dữ liệu ACTIVE/SUSPENDED thuộc reference hay fixture?
- Vì sao prod-root.yaml an toàn hơn chỉ dùng một root kèm context=test?
- Điều gì xảy ra nếu CI/CD dùng sai context, label hoặc sai database URL?
- Khi fixture đã được ghi nhận trong DATABASECHANGELOG, vì sao không xóa dòng lịch sử để chạy lại tùy tiện?
- Cách kiểm tra chính xác sau migration là gì?

## 15. Checklist cho production và integration test

- [ ] Phân loại rõ thay đổi schema, dữ liệu tham chiếu và fixture.
- [ ] Thay đổi schema dùng chung một nguồn changelog cho các môi trường tương ứng.
- [ ] Production root không include file test seed.
- [ ] File test seed có context yêu cầu tường minh và label đủ rõ.
- [ ] Job migration luôn truyền filter, changelog root và database URL được kiểm soát.
- [ ] Những changeset không gắn filter được hiểu đúng là có thể áp dụng ở các môi trường cần thiết.
- [ ] Không dựa vào labels hoặc context thường như lớp bảo vệ duy nhất.
- [ ] Precondition chỉ bổ sung kiểm tra; không thay thế phân quyền và tách changelog.
- [ ] Fixture dùng dữ liệu giả có ID/marker riêng, không chứa thông tin nhạy cảm.
- [ ] Rollback fixture hoặc quy trình reset database test được thiết kế trước.
- [ ] update-sql production không chứa INSERT dữ liệu giả.
- [ ] Lịch sử DATABASECHANGELOG không ghi nhận fixture ở production.
- [ ] Hậu kiểm production xác nhận không có dữ liệu fixture theo các marker đã định.
- [ ] Spring Boot profile và Liquibase context được cấu hình riêng, không suy diễn tự động.
- [ ] Chỉ một cơ chế triển khai được chỉ định chạy migration tại một thời điểm.
- [ ] Kết quả kiểm chứng và thông số triển khai không nhạy cảm được lưu cùng bản phát hành.

## 16. Kết luận

**Tách dữ liệu thử nghiệm khỏi thay đổi cấu trúc** là một nguyên tắc về kiến trúc changelog và vận hành, không chỉ là việc thêm một nhãn test vào changeset. Schema và dữ liệu tham chiếu cần thiết nên nằm trong các changeset dùng chung; fixture được cô lập trong changelog riêng, kèm context/label có chủ đích. Root changelog production không nên include test seed, ngay cả khi pipeline đã cấu hình filter.

Bằng cách kết hợp tách file, execution filters, precondition khi phù hợp, quyền truy cập, review update-sql và hậu kiểm DATABASECHANGELOG cùng dữ liệu thật, nhóm có thể triển khai Liquibase nhất quán qua Spring Boot hoặc CI/CD, giữ được lịch sử migration rõ ràng và tránh đưa dữ liệu giả lập vào môi trường sản xuất.
