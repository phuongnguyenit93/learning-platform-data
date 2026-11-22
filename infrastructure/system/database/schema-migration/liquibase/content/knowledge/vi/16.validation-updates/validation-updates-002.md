# Xem changeset đang chờ bằng `status`

Trước khi cho Liquibase cập nhật schema, người vận hành cần trả lời câu hỏi: **“Nếu chạy migration với cấu hình hiện tại, Liquibase đang nhận diện những changeset nào là chưa triển khai?”** Lệnh `status` giúp xem tập changeset còn chờ (*undeployed/pending*) mà **không trực tiếp áp dụng** những change như `createTable`, `addColumn` hoặc `insert`. Đây là bước kiểm tra quan trọng trước mỗi lần `update` trên development, staging và production.

Bài học thuộc chương **Kiểm tra và cập nhật** của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Mục tiêu module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm bài này là cách gọi `status`, hiểu kết quả, đối chiếu `DATABASECHANGELOG` và nhận ra những tình huống mà “không còn pending” **không đồng nghĩa** database đã đúng cấu trúc mong muốn.

## 1. `status` đang đo điều gì?

Liquibase đọc changelog, chọn các changeset phù hợp với cấu hình thực thi và đối chiếu định danh của chúng với lịch sử đã lưu trong database đích. Trong trường hợp thông thường, changeset **chưa có bản ghi tương ứng** trong `DATABASECHANGELOG` được xem là chưa triển khai.

| Changeset trong changelog | Mục tiêu | Lịch sử trên staging | Dự kiến trong `status` |
|---|---|---|---|
| `001-create-customer` | Tạo bảng khách hàng. | Đã ghi `EXECUTED`. | Không còn chờ. |
| `002-add-customer-email` | Thêm cột email. | Đã ghi `EXECUTED`. | Không còn chờ. |
| `003-create-customer-index` | Tạo index trên email. | Chưa có bản ghi. | Đang chờ. |

Giả sử cả ba đều thuộc phạm vi triển khai, `status` sẽ phản ánh **một** changeset đang chờ: `003-create-customer-index`. Lệnh `status` không tạo index; nó chỉ hỗ trợ quyết định cần review gì trước khi cập nhật.

### 1.1. Pending không phải là lỗi

Ngay trước một release có năm changeset mới, việc báo **5 pending** có thể là kết quả hoàn toàn đúng. Sau khi `update` thành công, danh sách chờ của những changeset thông thường được mong đợi sẽ giảm. Điều đáng quan tâm không chỉ là con số, mà là **các ID nào** đang chờ và chúng có đúng kế hoạch phát hành hay không.

### 1.2. Những điều `status` không khẳng định

- Không chứng minh bảng/cột/index thực tế còn tồn tại hoặc có đúng kiểu và constraint.
- Không chứng minh một precondition sẽ đạt tại thời điểm `update`.
- Không kiểm thử SQL thực sự chạy được với dữ liệu, quyền, transaction và lock của DBMS.
- Không chứng minh không còn schema drift do can thiệp SQL ngoài Liquibase.
- Không chứng minh mọi `runAlways` hoặc `runOnChange` sẽ hoàn toàn không hoạt động trong lần update tiếp theo.
- Không kiểm tra chất lượng rollback, khả năng restore dữ liệu hoặc độ an toàn trong production.

**Nguyên tắc:** `status` là phép **quan sát lựa chọn và lịch sử changeset**, không phải phép tổng kiểm định schema và dữ liệu.

## 2. Cách chạy `status` và `status --verbose`

Cú pháp minh họa với Liquibase CLI:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml status
liquibase --changelog-file=db/changelog/master.yaml status --verbose
~~~

`--changelog-file` trỏ tới changelog gốc. Từ đây, Liquibase đọc cả những changelog con được nạp qua `include`, `includeAll` hoặc cơ chế được hỗ trợ. Tùy chọn `--verbose` cung cấp danh sách chi tiết hơn để nhận diện những changeset đang chờ thay vì chỉ số lượng tổng quát.

Tên cờ, vị trí tham số và hình thức output có thể khác theo phiên bản CLI. Luôn sử dụng bản Liquibase đã khóa trong dự án, đọc hướng dẫn `liquibase status --help` của chính bản đó và không giả định console output được chuẩn hóa giữa mọi phiên bản.

### 2.1. Database đích là một phần của câu hỏi

Để biết changeset đã chạy chưa, Liquibase phải đọc **lịch sử của database đích**. Vì vậy, kết quả `status` phụ thuộc vào:

1. JDBC URL, database/catalog và default schema.
2. Tài khoản, quyền truy cập metadata và kết nối.
3. Changelog root và cách giải quyết đường dẫn resource.
4. Context filter, label filter và DBMS được kết nối.
5. Tên bảng history nếu ứng dụng tùy biến metadata Liquibase.
6. Phiên bản Liquibase Core/CLI, driver JDBC và các extension.

Ví dụ minh họa trên PostgreSQL thử nghiệm:

~~~bash
liquibase --url=jdbc:postgresql://localhost:5432/customer_test --username=migration_reader --changelog-file=db/changelog/master.yaml status --verbose
~~~

Kết nối và credentials phải được lấy từ cấu hình hoặc secret quản lý an toàn; không nhúng mật khẩu thật trong bài học, source control hoặc CI log. Người dùng cần có quyền truy cập phù hợp. Với database chưa từng chạy Liquibase, một số cách khởi tạo metadata trong quá trình thiết lập có thể cần quyền ghi tùy phiên bản/cấu hình; không nên đánh đồng “không áp dụng change nghiệp vụ” với cam kết mọi lệnh nội bộ chỉ đọc.

### 2.2. Đọc output thế nào?

| Cách gọi | Cần kiểm tra |
|---|---|
| `status` | Số lượng changeset Liquibase nhận diện là còn chờ trong phạm vi hiện tại. |
| `status --verbose` | ID, author, đường dẫn changelog của từng changeset chờ, và các thông tin chi tiết do phiên bản hỗ trợ. |

Ví dụ bên dưới chỉ **minh họa ý nghĩa**, không phải output chính xác của bất kỳ bản CLI cố định nào:

~~~text
Status summary: 1 undeployed changeset

Pending:
  db/changelog/changes/003-index.yaml
  db-team :: 003-create-customer-index
~~~

Khi làm pipeline, không nên viết parser phụ thuộc từng khoảng trắng hoặc dấu phân cách của ví dụ. Nếu cần tự động hóa, hãy chọn giao diện hoặc dạng output có cấu trúc thực sự được phiên bản đang dùng hỗ trợ và kiểm tra hành vi trong CI.

## 3. Liquibase nhận diện changeset đã triển khai bằng gì?

Changeset thường được nhận diện bằng bộ ba:

1. `id` — mã changeset.
2. `author` — tác giả hoặc nhóm sở hữu.
3. **Đường dẫn định danh changelog** — thông thường là đường dẫn tệp, có thể giữ ổn định bằng `logicalFilePath`.

Khi changeset chạy và được ghi nhận, bảng `DATABASECHANGELOG` lưu các trường như:

| Cột lịch sử | Vai trò |
|---|---|
| `ID` | Mã changeset. |
| `AUTHOR` | Tác giả. |
| `FILENAME` | Đường dẫn định danh dùng đối chiếu lịch sử. |
| `DATEEXECUTED` | Thời điểm ghi nhận. |
| `EXECTYPE` | Trạng thái như `EXECUTED`, `MARK_RAN`, `RERAN` theo tình huống. |
| `MD5SUM` | Checksum phục vụ kiểm tra thay đổi định nghĩa. |
| `ORDEREXECUTED` | Thứ tự ghi nhận thực thi trong lịch sử. |

Truy vấn chỉ đọc để đối chiếu:

~~~sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED,
       EXECTYPE, MD5SUM, ORDEREXECUTED
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED DESC;
~~~

Nếu tên bảng lịch sử đã được tùy biến, điều chỉnh truy vấn cho phù hợp. Truy vấn bảng `DATABASECHANGELOG` trả lời **“đã ghi nhận gì?”**, còn `status` trả lời **“changelog hiện hành còn gì cần xét?”**. Chúng không thay thế nhau.

### 3.1. Đổi tên hoặc di chuyển changelog có thể tạo pending giả

Giả sử history chứa:

~~~text
ID: 001-create-customer
AUTHOR: db-team
FILENAME: db/changelog/changes/001-customer.yaml
~~~

Sau đó nhóm chuyển tệp sang:

~~~text
db/changelog/archive/001-customer.yaml
~~~

Nếu Liquibase dùng đường dẫn mới làm định danh, bộ ba không còn khớp history cũ. Changeset có thể bị nhận diện là chưa chạy, dù SQL không đổi. Khi di chuyển file đã triển khai, cần đọc **nguyên văn** `FILENAME` của database thực, cập nhật đường dẫn `include` để nạp file vật lý và giữ định danh bằng `logicalFilePath` nếu cần.

Không sửa bừa `DATABASECHANGELOG` hoặc dùng `MARK_RAN` để che vấn đề định danh. Đặc biệt, một `CREATE TABLE` bị nhận nhầm là mới có thể chạy lại và gây lỗi hoặc làm dữ liệu trùng.

### 3.2. Checksum khác định danh

Checksum `MD5SUM` giúp kiểm tra thay đổi nội dung của changeset đã ghi nhận. Dù SQL không đổi, bộ ba định danh thay đổi vẫn có thể khiến Liquibase xem như một changeset mới. Ngược lại, nếu định danh giữ nguyên nhưng code cũ bị sửa trái quy tắc, Liquibase có thể báo lỗi checksum khi validation/update.

Vì vậy, đừng dùng `clearCheckSums` như cách chữa mặc định khi thấy pending bất thường. Hãy xác định đúng nguyên nhân: sai đích kết nối, sai include, sai `id`/`author`/`FILENAME`, hay sai checksum.

## 4. Ví dụ changelog có ba changeset

Giả sử changelog YAML đơn giản:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: db-team
      changes:
        - createTable:
            tableName: customer_record
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
  - changeSet:
      id: 002-add-customer-email
      author: db-team
      changes:
        - addColumn:
            tableName: customer_record
            columns:
              - column:
                  name: email
                  type: VARCHAR(255)
  - changeSet:
      id: 003-index-customer-email
      author: db-team
      changes:
        - createIndex:
            tableName: customer_record
            indexName: idx_customer_record_email
            columns:
              - column:
                  name: email
~~~

Đây là ví dụ changelog hoàn chỉnh về mặt cấu trúc để thực hành trên database mới. Trên database đã có `001` và `002` trong `DATABASECHANGELOG`, `status --verbose` sẽ hỗ trợ nhận ra `003` còn chờ. Trên database chưa có history, cả ba thường là ứng viên chờ nếu không bị filter loại. Trên database đã chạy cả ba, bình thường không còn changeset mới cần chạy.

### 4.1. Kiểm tra thứ tự có quan trọng không?

Có. `003` cần cột `email` do `002` tạo, còn `002` cần bảng do `001` tạo. Dù `status` cho bạn danh sách chờ, không nên coi số pending là đủ để khẳng định thứ tự phụ thuộc đúng. Người viết changelog chịu trách nhiệm sắp xếp `include` hoặc nội dung theo thứ tự phù hợp, kiểm chứng SQL preview và thử thực thi.

### 4.2. Lịch sử đã chạy không chứng minh object còn tồn tại

Nếu `002` từng được đánh dấu `EXECUTED`, sau đó cột `email` bị xóa bằng SQL thủ công, `status` không tự nhận ra schema drift ấy để đưa `002` vào pending. Cần kiểm tra metadata thật, có thể dùng snapshot/diff hoặc truy vấn đặc thù DBMS, rồi thiết kế migration sửa trạng thái đúng cách.

## 5. Tập pending thay đổi theo context, label và DBMS

Một kết quả `status` chỉ có ý nghĩa trong **phạm vi lựa chọn** của lần gọi hiện tại. Những bộ lọc context, label và DBMS có thể khiến hai lần kiểm tra trên cùng database cho ra danh sách khác nhau.

### 5.1. Context filter

Ví dụ XML:

~~~xml
<changeSet id="seed-dev-users" author="db-team"
           contextFilter="development">
    <insert tableName="demo_user">
        <column name="username" value="sample-user"/>
    </insert>
</changeSet>
~~~

Khi lần chạy chọn context `production`, changeset chỉ thuộc `development` sẽ không được chọn theo biểu thức lọc tương ứng.

**Chú ý:** ở những phiên bản/cú pháp Liquibase, **không cung cấp context filter** có thể khiến changeset có context vẫn được xét chạy. Đừng mặc định “bỏ trống context” là “chặn mọi changeset gắn context”. Hãy cấu hình và kiểm chứng chính sách lọc thực sự, đặc biệt với seed data hoặc thao tác chỉ dành cho development.

### 5.2. Label filter

Labels phân nhóm changeset theo tính năng hoặc release:

~~~xml
<changeSet id="add-reporting-index" author="db-team"
           labels="reporting,release-42">
    <createIndex tableName="report_event"
                 indexName="idx_report_event_created">
        <column name="created_at"/>
    </createIndex>
</changeSet>
~~~

Việc chọn label/filter phù hợp quyết định changeset có thuộc phạm vi cần xét không. Labels **không kiểm tra bảng** `report_event` đã tồn tại và không đảm bảo tạo index an toàn.

### 5.3. DBMS filter

~~~xml
<changeSet id="create-pg-index" author="db-team"
           dbms="postgresql">
    <sql>
        CREATE INDEX idx_event_payload_gin
        ON event_log USING gin (payload)
    </sql>
</changeSet>
~~~

Changeset trên chỉ dành cho PostgreSQL; không dùng kết quả `status` ở PostgreSQL làm bằng chứng danh sách pending trên SQL Server hoặc Oracle tương đương.

### 5.4. Dùng đúng bộ lọc cho `status` và `update`

Ví dụ minh họa CLI có context production và label release:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml --context-filter=production --label-filter=release-42 status --verbose
~~~

Trong pipeline thực, gọi `update` với **cùng** JDBC URL, default schema, changelog artifact, context, labels và phiên bản công cụ. Nếu `status` dùng một cấu hình nhưng `update` dùng cấu hình khác, kết quả kiểm tra không còn dự đoán đáng tin cậy lần triển khai.

## 6. Pending không bảo đảm một changeset sẽ thực thi thành công

Một changeset có thể được liệt kê là chờ nhưng không chạy thành công vì:

- Precondition không đạt và `onFail="HALT"` dừng lệnh.
- Precondition `CONTINUE` bỏ qua tạm thời hoặc `MARK_RAN` ghi nhận không thực thi change.
- Changeset trước đó thất bại; Liquibase dừng trước khi đến changeset đang xem.
- DDL/SQL lỗi vì bảng thiếu, dữ liệu vi phạm constraint, lock, thiếu quyền hoặc khác biệt DBMS.
- Database thay đổi giữa lúc xem `status` và lúc triển khai.
- Cấu hình context, label, changelog hoặc JDBC URL thay đổi.

Ví dụ precondition bảo vệ index:

~~~xml
<changeSet id="004-add-email-index" author="db-team">
    <preConditions onFail="HALT" onError="HALT">
        <tableExists tableName="customer_record"/>
        <columnExists tableName="customer_record"
                      columnName="email"/>
    </preConditions>
    <createIndex tableName="customer_record"
                 indexName="idx_customer_email">
        <column name="email"/>
    </createIndex>
</changeSet>
~~~

Changeset chưa chạy có thể được `status` liệt kê, nhưng nếu bảng hoặc cột không tồn tại vào lúc `update`, precondition khiến migration dừng. `status` **không phải cam kết** mọi precondition đều sẽ đạt.

### 6.1. `runAlways` và `runOnChange` cần đánh giá riêng

- `runAlways="true"`: changeset có thể được chạy lại ở mỗi lần `update` đủ điều kiện theo quy tắc Liquibase.
- `runOnChange="true"`: changeset có thể được chạy lại khi nội dung thay đổi theo cơ chế checksum.
- Changeset bình thường đã `EXECUTED` và không thuộc trường hợp chạy lại sẽ không được xử lý như changeset chưa từng chạy.

Không giả định kết quả “0 pending” nghĩa là `update` chắc chắn sẽ không tạo SQL khi có `runAlways`/`runOnChange`. Cách hiển thị những changeset này trong `status` cần được kiểm chứng với **phiên bản Liquibase cụ thể**; hãy kết hợp `validate`, SQL preview và đọc thuộc tính changeset.

## 7. `status` khác `validate`, `update-sql` và `update` thế nào?

| Công cụ | Câu hỏi chính | Có chủ đích thực thi DDL/DML thay đổi nghiệp vụ? | Giới hạn |
|---|---|---|---|
| `status` | Có những changeset nào chờ trong phạm vi hiện tại? | Không. | Không khẳng định schema/data đúng hoặc SQL sẽ thành công. |
| `status --verbose` | ID, author, file của changeset chờ là gì? | Không. | Vẫn là kết quả quan sát tại thời điểm chạy. |
| `validate` | Changelog có qua các kiểm tra Liquibase thực hiện không? | Không nhằm áp dụng change nghiệp vụ. | Không chứng minh DDL chạy được với dữ liệu production. |
| `update-sql` | SQL nào dự kiến được sinh khi cập nhật? | Không thực thi change như `update`. | Preview không thay thế kiểm thử thực tế. |
| `update` | Thực thi các changeset đủ điều kiện. | Có. | Làm thay đổi schema/dữ liệu thật, có thể thất bại giữa chừng. |
| `SELECT` trên `DATABASECHANGELOG` | Lịch sử đã ghi gì? | Không. | Không tự đọc tập changeset mới của changelog hiện tại. |

Một chuỗi kiểm chứng phổ biến:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml validate
liquibase --changelog-file=db/changelog/master.yaml status --verbose
liquibase --changelog-file=db/changelog/master.yaml update-sql
~~~

Phải dùng cùng cấu hình database, filter, schema, artifact và phiên bản đã khóa. Sau đó thử `update` trên database đại diện trước khi cho phép production chạy.

### 7.1. Vì sao phải xem SQL preview khi đã biết pending?

Một changeset có thể chứa nhiều change, bao gồm SQL riêng DBMS, tạo trigger hoặc backfill dữ liệu. “1 pending” có thể là tạo một index nhỏ hoặc cập nhật hàng triệu hàng. Chỉ có `status` không cho biết kích thước tác động, transaction, thời gian lock hay khả năng rollback. SQL preview và kiểm thử trên dữ liệu đại diện giúp trả lời các câu hỏi còn thiếu.

## 8. Các tình huống kết quả `status` dễ gây hiểu nhầm

### 8.1. Không có pending vì kết nối nhầm database

CLI trỏ tới development thay vì staging; cả hai cùng có changelog nhưng lịch sử khác nhau. “0 pending” chỉ là kết quả của development. Hãy xác minh database, schema, user và URL đích, tránh ghi lộ thông tin xác thực.

### 8.2. File mới chưa được include

Một file `004-new-discount.yaml` đã được commit nhưng changelog root không `include` nó. Vì file không nằm trong tập được nạp, `status` không hiển thị changeset của file đó. Kiểm tra graph include và artifact/classpath.

### 8.3. Changeset cũ xuất hiện lại

Có thể `id`/`author` hoặc `FILENAME` đã đổi khi di chuyển file. Có thể database/schema đang dùng không phải đích cũ hoặc trước đây SQL được chạy thủ công mà không ghi history. Không retry ngay: đối chiếu bộ ba định danh trước.

### 8.4. `MARK_RAN` làm pending biến mất nhưng object vẫn thiếu

Precondition `onFail="MARK_RAN"` có thể tạo bản ghi `EXECTYPE=MARK_RAN` mà không chạy DDL. Sau đó `status` có thể không còn coi changeset là chưa triển khai, dù đối tượng mục tiêu chưa thật sự tồn tại. Vì vậy cần truy vấn schema thật.

### 8.5. Changeset đã rollback trở thành pending

Khi rollback theo quy trình Liquibase, bản ghi history của changeset đã rollback thông thường bị loại tương ứng. Nếu changelog vẫn chứa nó và filter vẫn chọn, changeset có thể xuất hiện lại là chưa triển khai. Hành vi cụ thể tùy phiên bản và cách rollback.

### 8.6. Hai lần `status` cho kết quả khác nhau

Giữa hai lần kiểm tra có thể có một pipeline khác chạy `update`, thay đổi history hoặc người vận hành đổi bộ lọc. `status` là **snapshot theo thời điểm**, không đóng băng database và không giữ một đảm bảo trạng thái không đổi cho lần triển khai tương lai.

## 9. Bảng chẩn đoán khi kết quả bất thường

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Quá nhiều changeset pending | Sai database/schema; history trống; đổi `FILENAME`; changelog khác. | Xác minh JDBC URL, metadata và bộ ba định danh. |
| Ít pending hơn dự kiến | File chưa include; filter loại changeset; `MARK_RAN`; nhầm đích. | Kiểm tra include tree, context/label/dbms và history. |
| 0 pending nhưng schema sai | Schema drift, thay đổi thủ công, `MARK_RAN`. | Kiểm tra metadata và dữ liệu, thiết kế remediation. |
| `status` có pending nhưng `validate` lỗi | Changelog/định danh/checksum không hợp lệ. | Sửa lỗi validation trước `update`. |
| SQL preview khác số changeset dự đoán | Một changeset có nhiều change, DBMS/filter/precondition ảnh hưởng. | Dùng cùng cấu hình, đọc SQL preview thật. |
| Không đọc được changelog | Sai đường dẫn hoặc thiếu file trong classpath. | Kiểm tra root path, include và đóng gói artifact. |
| Không đọc được history | Quyền/schema/bảng metadata không phù hợp. | Kiểm tra kết nối, quyền và cấu hình Liquibase. |
| Changeset cũ xuất hiện sau khi đổi chỗ file | Logical file path đã thay đổi. | Đối chiếu `FILENAME` và `logicalFilePath`. |
| CI báo lỗi chỉ vì có pending | Tiêu chí kiểm soát không phù hợp giai đoạn pre-deploy. | So sánh danh sách mong đợi thay vì mặc định đòi 0. |

Khi điều tra, lưu lại thời điểm, ID, author, filename, bộ lọc và environment; tuyệt đối không đưa thông tin nhạy cảm vào log công khai.

## 10. Tích hợp `status` vào CI/CD

Một quy trình phát hành có kiểm chứng có thể theo thứ tự:

~~~mermaid
flowchart TD
    A[Checkout changelog đã review] --> B[Validate với Liquibase version đã khóa]
    B --> C[Status --verbose trên database dự kiến]
    C --> D[So khớp danh sách pending với release]
    D --> E[Xem update-sql và ảnh hưởng khóa]
    E --> F[Thử migration trên DB đại diện]
    F --> G[Phê duyệt và chạy update]
    G --> H[Status lại, xem history và schema thực]
    H --> I[Smoke test ứng dụng]
~~~

### 10.1. Đầu vào phải thống nhất

| Thành phần | Vì sao cần giữ đồng nhất? |
|---|---|
| Commit/artifact changelog | Thay code sẽ thay danh sách hoặc checksum changeset. |
| Liquibase CLI/Core version | Parsing, validation và SQL generation có thể thay đổi. |
| Driver JDBC, extension | Quyết định tích hợp DBMS và cách gửi SQL. |
| JDBC URL, database/schema | Quyết định history được đối chiếu. |
| Context và label filters | Quyết định tập changeset được chọn. |
| Resource/classpath | Ảnh hưởng include và `FILENAME`. |
| Quyền kết nối | Ảnh hưởng đọc history và khả năng triển khai. |

### 10.2. Có pending trước deploy không phải tự động thất bại

Nếu release có **5 changeset mới**, `status` báo 5 có thể là đúng, còn 0 có thể là bất thường vì pipeline đang dùng nhầm commit hoặc DB. Điều kiện kiểm soát phải so sánh **danh sách ID/author/file mong đợi**, không chỉ số pending với 0.

Kiểm tra ít nhất những điều sau: có changeset bất ngờ; có changeset dự kiến bị thiếu; thứ tự phụ thuộc có hợp lý; file đã di chuyển có giữ định danh; có DDL nhạy cảm với dữ liệu lớn, lock hoặc downtime không.

### 10.3. Sau khi deploy vẫn phải kiểm chứng

Chạy `status` với cùng config trên cùng database sau `update`, rồi đối chiếu `DATABASECHANGELOG`, metadata schema, tính đúng đắn dữ liệu và smoke test ứng dụng. Đừng kết luận toàn bộ thành công chỉ từ “status = 0”, đặc biệt khi có `MARK_RAN`, `runAlways` hoặc thay đổi ngoài Liquibase.

## 11. Spring Boot và việc xem `status`

Spring Boot có thể được cấu hình chạy Liquibase khi khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/master.yaml
~~~

Đây là cấu hình **triển khai migration lúc khởi động**, không phải “chỉ xem status”. Nếu muốn kiểm tra pending **trước** khi khởi động sản phẩm, dùng CLI hoặc tích hợp Liquibase được quản lý riêng trên đúng changelog và database đích; không khởi động ứng dụng production chỉ để xem còn bao nhiêu pending.

Điểm cần quản lý:

1. Changelog và các tệp include có được đóng gói đủ trong JAR/artifact không?
2. Đường dẫn tài nguyên của CLI có cho cùng `FILENAME` logic như Spring Boot không?
3. Nếu nhiều instance khởi động đồng thời, `DATABASECHANGELOGLOCK` giúp điều phối hoạt động Liquibase nhưng không khóa mọi DML của ứng dụng.
4. Nếu CI/CD đã chạy `update` trước deploy, ứng dụng có tiếp tục tự chạy Liquibase khi khởi động không? Phải có chính sách rõ ràng.
5. Nếu một `update` thất bại sau DDL tự commit, history có thể thiếu bản ghi dù schema đã thay đổi: `status` có thể còn liệt kê changeset đó. **Không chạy lại một cách mù quáng.**

## 12. Khóa, giao dịch và giới hạn của một kết quả `status`

Liquibase sử dụng `DATABASECHANGELOGLOCK` để tránh nhiều tiến trình Liquibase cùng thay đổi changelog/history trên một database. DBMS lại có row locks, table locks và DDL/schema locks cho các giao dịch thật. Hai loại khóa phục vụ mục tiêu khác nhau.

Truy vấn chỉ đọc khi điều tra:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Nếu thấy `LOCKED=true` hoặc lệnh đang chờ, cần xác minh tiến trình migration hiện tại trước khi hành động. Không tự ý chạy `releaseLocks` hoặc sửa bảng khóa chỉ vì status chậm; giải phóng khóa khi tiến trình cũ còn hoạt động có thể dẫn đến triển khai chồng nhau.

Một `status` không tự đóng băng schema/history; database có thể đổi sau khi lệnh kết thúc. Khi deployment có điều kiện khắt khe, cần quy trình phê duyệt, bảo vệ môi trường và kiểm tra lại gần thời điểm `update`.

## 13. Thực hành có kiểm chứng

**Mục tiêu:** quan sát pending trên database mới, đã triển khai một phần và đã triển khai đầy đủ; xác nhận `status` không tự tạo bảng nghiệp vụ.

### Giai đoạn A — Database mới

1. Tạo database thử nghiệm riêng, không chứa dữ liệu production.
2. Lưu changelog ba changeset ở mục 4 trong một project thực hành.
3. Cấu hình Liquibase, JDBC driver và tài khoản test.
4. Chạy `validate`, sau đó `status` và `status --verbose`.
5. Ghi lại danh sách chờ, kiểm tra bảng nghiệp vụ `customer_record` chưa được tạo bởi bước status.

**Kỳ vọng:** cả ba changeset thường đang chờ trên database mới nếu không bị filter loại. Khởi tạo metadata Liquibase có thể phụ thuộc phiên bản/cấu hình, nên ở bước này chỉ khẳng định **không áp dụng changeset nghiệp vụ**.

### Giai đoạn B — Đã triển khai một phần

1. Trên database thử, thực hiện có kiểm chứng hai changeset `001` và `002` trước; sử dụng một changelog test chỉ chứa chúng nhưng giữ nguyên định danh logic.
2. Sử dụng lại changelog đủ ba changeset rồi chạy `status --verbose`.
3. Dự đoán `003` là changeset còn chờ, đối chiếu `DATABASECHANGELOG`.
4. Kiểm tra bảng và cột thật có tương ứng với `001`, `002` không.

### Giai đoạn C — Triển khai đủ

1. Chạy `update-sql` và review câu SQL tạo index.
2. Chạy `update` trên database thử.
3. Chạy lại `status --verbose` và truy vấn history; xác minh `003` được ghi nhận.
4. Kiểm tra index `idx_customer_record_email` thực sự tồn tại.
5. Chạy lại `update` nếu an toàn và xác nhận không tạo lại index của changeset thông thường đã hoàn tất.

### Giai đoạn D — Phát hiện vấn đề

Trên **bản sao dữ liệu thử**:

- Di chuyển changelog mà không giữ định danh: quan sát vì sao changeset có thể xuất hiện lại.
- Loại file mới khỏi include: quan sát vì sao `status` không thấy changeset mới.
- Thay context/label filter: quan sát tập pending thay đổi.
- Xóa thủ công một index trên bản sao: quan sát rằng `status` có thể vẫn báo không pending dù index đã mất.

### Tiêu chí đạt

- Giải thích quan hệ `status` và `DATABASECHANGELOG`, nhận diện bộ ba định danh.
- Biết sử dụng `--verbose` để đối chiếu danh sách pending với release.
- Phân biệt kết quả trên database mới, đã chạy một phần và đã chạy đầy đủ.
- Hiểu ảnh hưởng context, label, DBMS, include và `logicalFilePath`.
- Không nhầm `status` với `validate`, SQL preview, schema inspection hoặc `update`.
- Không coi pending là lý do đủ để retry sau một lỗi DDL tự commit.

## 14. Checklist trước mỗi lần phát hành

- [ ] Xác minh JDBC URL, database, schema, tài khoản và môi trường.
- [ ] Dùng đúng root changelog, commit, artifact và version Liquibase/driver.
- [ ] Giữ bộ context/label/DBMS filters thống nhất giữa kiểm tra và update.
- [ ] Chạy `validate` và xử lý lỗi checksum/cấu trúc trước cập nhật.
- [ ] Chạy `status --verbose`, lưu danh sách ID/author/file cho review.
- [ ] So sánh danh sách pending với release dự kiến, không chỉ nhìn số đếm.
- [ ] Kiểm tra graph `include`/`includeAll` và file đóng gói trong artifact.
- [ ] Đối chiếu `FILENAME` nếu changelog từng đổi tên/di chuyển.
- [ ] Đọc các changeset có `runAlways`, `runOnChange` và preconditions.
- [ ] Xem `update-sql` và thử migration trên database có lịch sử/dữ liệu đại diện.
- [ ] Xác định rủi ro lock/transaction và kế hoạch rollback/restore.
- [ ] Sau deploy, xem lại `status`, `DATABASECHANGELOG`, schema và dữ liệu.
- [ ] Không tự sửa history hoặc giải phóng khóa để làm kết quả status “đẹp”.

## 15. Câu hỏi tự kiểm tra

1. `status` trả lời câu hỏi gì và có tự chạy DDL/DML nghiệp vụ không?
2. `status --verbose` giúp review release tốt hơn như thế nào?
3. Bộ ba định danh changeset mà Liquibase dùng đối chiếu history gồm gì?
4. Vì sao đổi `FILENAME` sau khi chuyển changelog có thể tạo pending giả?
5. `status` báo 0 pending có bảo đảm bảng và index vẫn tồn tại không?
6. Context/label/DBMS filters tác động đến kết quả status ra sao?
7. Vì sao phải dùng cùng kết nối và filters cho `status` và `update`?
8. `validate`, `update-sql` và `status` khác nhau ở mục tiêu nào?
9. Khi precondition `MARK_RAN` được áp dụng, kết quả `status` có thể gây hiểu nhầm gì?
10. Vì sao `runAlways`/`runOnChange` cần được xét riêng?
11. Tại sao không retry ngay một changeset sau khi DDL có thể đã tự commit?
12. Làm thế nào phát hiện file changelog mới chưa được include?
13. Vì sao số pending khác giữa development và staging có thể hoàn toàn hợp lệ?
14. Trong CI/CD, vì sao 5 pending trước release có thể là đúng nhưng 0 pending lại đáng nghi?

## Kết luận

`status` là công cụ quan sát cốt lõi trước và sau khi triển khai: nó giúp nhận diện **những changeset Liquibase xem là đang chờ trong changelog và phạm vi hiện tại**. Khi kết hợp `--verbose`, bộ ba `id`/`author`/`FILENAME` và cấu hình context/label/DBMS nhất quán, nhóm có thể phát hiện nhiều sai sót trước khi chạy `update`. Tuy nhiên, chỉ kết luận migration an toàn khi đã xem thêm `validate`, SQL preview, lịch sử `DATABASECHANGELOG`, schema/dữ liệu thật và kiểm thử trên database đại diện. Đây là nền tảng để `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` hỗ trợ triển khai có kiểm chứng, truy vết và giảm rủi ro trên nhiều môi trường.
