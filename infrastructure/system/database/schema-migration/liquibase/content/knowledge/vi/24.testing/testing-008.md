# Kiểm thử preconditions, lỗi giữa chừng và phục hồi

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một migration chỉ đáng tin cậy khi nhóm đã kiểm tra cả điều kiện đầu vào, hành vi khi có lỗi và khả năng đưa database về trạng thái nhất quán sau khi tiến trình bị gián đoạn.

Bài học thuộc chương **Kiểm thử**, tập trung vào ba năng lực: kiểm thử `preConditions` trong nhiều trạng thái database; mô phỏng và phân tích lỗi xảy ra giữa quá trình thực thi changeset; và phục hồi dựa trên trạng thái schema, dữ liệu cùng lịch sử Liquibase thực tế. Nội dung áp dụng cho `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, bao gồm changelog, changeset, checksum, rollback và quy trình chạy trong Spring Boot hoặc CI/CD.

## 1. Vì sao phải kiểm thử cả precondition và lỗi giữa chừng?

`preConditions` xác minh một số giả định trước khi Liquibase chạy changeset. Ví dụ: bảng cần thay đổi đã tồn tại, cột chưa tồn tại, database đang dùng đúng DBMS, hoặc dữ liệu không có bản ghi trùng trước khi tạo unique constraint.

Tuy nhiên, precondition chỉ là một phần của kiểm soát. Nó không chứng minh toàn bộ migration sẽ thành công. Sau khi điều kiện được kiểm tra, DDL/DML vẫn có thể thất bại vì:

- Quyền database không đủ.
- Dữ liệu thay đổi đồng thời sau lúc kiểm tra.
- Lock timeout, deadlock hoặc transaction bị hủy.
- Hết dung lượng disk, transaction log, WAL hoặc redo log.
- SQL không tương thích DBMS/phiên bản thực tế.
- Constraint, trigger hoặc dependency phát sinh lỗi.
- Kết nối bị mất, tiến trình runner bị dừng hoặc máy chủ khởi động lại.
- Một statement trong changeset thành công nhưng statement tiếp theo thất bại.

Vì vậy, kế hoạch kiểm thử phải trả lời ba câu hỏi riêng:

1. **Điều kiện nào cho phép changeset chạy?** Kiểm thử precondition đúng và sai.
2. **Nếu thực thi thất bại ở từng điểm thì database còn trạng thái nào?** Kiểm thử transaction, lock và thay đổi đã ghi.
3. **Làm sao tiếp tục hoặc phục hồi mà không chạy lặp gây hỏng dữ liệu?** Kiểm thử rollback, forward-fix và quy trình đối soát.

Không dùng một lần `validate` thành công để thay cho các bài kiểm thử này. `validate` kiểm tra một số vấn đề về changelog và tính nhất quán lịch sử; nó không mô phỏng đầy đủ dữ liệu, lock, quyền, lỗi mạng hoặc hành vi transaction trên production.

## 2. Vòng đời thực thi và vị trí của precondition

Ở mức khái quát, một lần `update` của Liquibase thực hiện các bước:

1. Đọc master changelog và nạp các file được include.
2. Xác định changeset, filter và lịch sử trong `DATABASECHANGELOG`.
3. Lấy quyền điều phối qua `DATABASECHANGELOGLOCK`.
4. Kiểm tra điều kiện ở phạm vi changelog hoặc changeset.
5. Thực thi các change/SQL theo thứ tự.
6. Ghi nhận changeset đã chạy trong `DATABASECHANGELOG`.
7. Giải phóng lock khi kết thúc theo cơ chế của Liquibase.

Chi tiết nội bộ có thể khác theo phiên bản, DBMS và cách cấu hình. Khi điều tra sự cố, phải kiểm tra trạng thái thực tế thay vì giả định rằng mọi bước đều là một transaction nguyên tử duy nhất.

Precondition có thể nằm ở hai phạm vi:

| Phạm vi | Mục đích | Tác động khi không đạt |
|---|---|---|
| Changelog-level | Kiểm tra điều kiện chung trước khi xử lý changelog | Có thể dừng hoặc cảnh báo toàn bộ luồng update |
| Changeset-level | Kiểm tra giả định riêng của một thay đổi | Có thể dừng, cảnh báo, bỏ qua hoặc đánh dấu changeset theo cấu hình |

Đặt precondition ở phạm vi nhỏ nhất có thể diễn đạt đúng ý nghĩa. Một điều kiện về bảng `customer` không nên vô tình ngăn các changeset độc lập trên bảng `invoice` chạy nếu đó không phải yêu cầu.

## 3. Các loại precondition thường dùng

Liquibase cung cấp nhiều precondition có cấu trúc để kiểm tra metadata database:

| Precondition | Điều kiện kiểm tra | Tình huống |
|---|---|---|
| `dbms` | DBMS hiện tại | SQL hoặc change chỉ hỗ trợ một DBMS |
| `runningAs` | Tài khoản kết nối hiện tại | Xác minh danh tính DB được cấu hình |
| `tableExists` | Bảng có tồn tại | Thêm cột vào bảng hiện hữu |
| `columnExists` | Cột có tồn tại | Đổi kiểu hoặc tạo index |
| `viewExists` | View có tồn tại | Thay định nghĩa hoặc phụ thuộc |
| `sequenceExists` | Sequence có tồn tại | Kiểm tra đối tượng cấp ID |
| `indexExists` | Index có tồn tại | Tránh tạo lại hoặc kiểm tra prerequisite |
| `primaryKeyExists` | Primary key có tồn tại | Kiểm tra cấu trúc khóa |
| `foreignKeyConstraintExists` | Foreign key có tồn tại | Kiểm tra quan hệ giữa bảng |
| `uniqueConstraintExists` | Unique constraint có tồn tại | Kiểm tra ràng buộc duy nhất |
| `changeLogPropertyDefined` | Property đã được định nghĩa | Bảo đảm cấu hình bắt buộc có mặt |
| `sqlCheck` | Kết quả một câu SQL so với giá trị kỳ vọng | Kiểm tra dữ liệu, số lượng hoặc trạng thái tùy biến |

Không phải mọi precondition đều được hỗ trợ giống nhau trên mọi DBMS hoặc phiên bản Liquibase. Kiểm tra tài liệu đúng phiên bản, schema/catalog mà tài khoản có quyền đọc và khả năng của JDBC driver.

### 3.1. Kết hợp điều kiện logic

Có thể kết hợp precondition bằng `and`, `or`, `not`. Ví dụ: chỉ cho phép thêm cột khi bảng tồn tại và cột chưa tồn tại:

```yaml
databaseChangeLog:
  - changeSet:
      id: "TEST-4101-add-customer-review-state"
      author: "customer-platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: customer
            - not:
                - columnExists:
                    tableName: customer
                    columnName: review_state
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: review_state
                  type: VARCHAR(20)
                  constraints:
                    nullable: true
```

Ý nghĩa: nếu bảng không tồn tại hoặc cột đã tồn tại thì điều kiện `and` không đạt và changeset dừng theo `onFail: HALT`. Cần xác minh cách parser của phiên bản đang dùng chấp nhận cấu trúc `not` trong YAML; có thể viết precondition tương đương theo format changelog của dự án.

### 3.2. sqlCheck cho quy tắc dữ liệu

Ví dụ kiểm tra không có nhóm email trùng trước khi tạo unique constraint:

```yaml
databaseChangeLog:
  - changeSet:
      id: "TEST-4102-add-customer-email-unique"
      author: "customer-platform"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |-
              SELECT COUNT(*)
              FROM (
                  SELECT tenant_id, email
                  FROM customer
                  WHERE email IS NOT NULL
                  GROUP BY tenant_id, email
                  HAVING COUNT(*) > 1
              ) duplicate_groups
      changes:
        - addUniqueConstraint:
            tableName: customer
            columnNames: tenant_id, email
            constraintName: uq_customer_tenant_email
```

`sqlCheck` cần trả về một kết quả đơn có thể so sánh với `expectedResult`. Query phải nhẹ, xác định và phù hợp với DBMS. Trên bảng lớn, một truy vấn kiểm tra duplicate có thể tốn scan, sort hoặc memory; cần đo trên dữ liệu tương đương trước khi đưa vào đường triển khai production.

Precondition không thay thế unique constraint. Một tiến trình khác vẫn có thể ghi duplicate sau lúc kiểm tra và trước lúc DDL được thực thi. Constraint của DBMS mới là nơi cưỡng chế tính duy nhất; nếu có ghi đồng thời, phải thiết kế thêm cách phối hợp writer hoặc xử lý race condition.

## 4. Phân biệt precondition fail và precondition error

Hai trường hợp này có ý nghĩa khác nhau:

- **Fail:** Liquibase đánh giá được điều kiện nhưng kết quả không đúng kỳ vọng. Ví dụ `tableExists` trả về false hoặc `sqlCheck` trả về 3 trong khi kỳ vọng 0.
- **Error:** Liquibase không thể đánh giá điều kiện. Ví dụ query không chạy được do thiếu quyền, sai tên cột, kết nối lỗi hoặc SQL không hợp lệ.

Không nên coi `error` là một dạng `fail` có thể bỏ qua. Một precondition báo lỗi có thể chỉ ra cấu hình sai hoặc thiếu quyền, trong khi một precondition fail có thể phản ánh database đang ở trạng thái chưa sẵn sàng.

| Thuộc tính | Xử lý trường hợp | Câu hỏi khi review |
|---|---|---|
| `onFail` | Điều kiện trả về false | Trạng thái hiện tại có thực sự không đạt yêu cầu không? |
| `onError` | Không thể đánh giá điều kiện | Có lỗi kết nối, quyền, SQL hoặc metadata không? |

Với migration production, `HALT` thường là lựa chọn an toàn khi điều kiện quan trọng không đạt hoặc không thể xác minh. Chỉ dùng hành vi tiếp tục/bỏ qua khi có lý do nghiệp vụ rõ, có kiểm thử và có cơ chế chứng minh trạng thái database tương đương.

## 5. Hiểu đúng các hành vi onFail và onError

Các hành vi thường gặp:

| Giá trị | Hành vi | Rủi ro/cách dùng |
|---|---|---|
| `HALT` | Dừng quá trình update với lỗi | Phù hợp khi prerequisite bắt buộc không đạt |
| `WARN` | Ghi cảnh báo và tiếp tục theo semantics của Liquibase | Chỉ dùng khi điều kiện không phải hàng rào bắt buộc |
| `CONTINUE` | Bỏ qua changeset hiện tại, để có thể được xét lại ở lần update sau | Chỉ hợp lệ ở phạm vi changeset; cần tránh bỏ qua âm thầm |
| `MARK_RAN` | Không thực thi changeset nhưng ghi nhận như đã chạy | Nguy hiểm nếu database chưa thực sự có kết quả mong muốn |

`CONTINUE` và `MARK_RAN` chỉ phù hợp trong precondition ở cấp changeset; không dùng chúng như hành vi chung ở cấp changelog. Kiểm tra quy tắc của phiên bản Liquibase đang triển khai nếu có khác biệt.

### 5.1. Khi nào MARK_RAN có thể hợp lý?

Một trường hợp có thể cân nhắc: một đối tượng đã được DBA tạo trước, và nhóm muốn Liquibase ghi nhận changeset tương ứng là đã được đáp ứng. Nhưng trước khi dùng:

1. Xác minh đối tượng có đúng định nghĩa mong muốn, không chỉ trùng tên.
2. Xác minh constraint/index có đúng cột, thứ tự, predicate, collation và trạng thái validation.
3. Xác minh nguồn gốc thay đổi và môi trường nào đã tạo đối tượng.
4. Ghi lại bằng chứng và phê duyệt.
5. Kiểm tra `DATABASECHANGELOG` sau khi chạy.

Nếu precondition chỉ kiểm tra `indexExists` theo tên mà index cùng tên có cấu hình sai, `MARK_RAN` có thể che giấu sai lệch. Tên tồn tại không đồng nghĩa định nghĩa đúng.

### 5.2. Tránh dùng WARN để che prerequisite quan trọng

Nếu changeset thêm cột bắt buộc mà bảng không tồn tại, cảnh báo rồi tiếp tục không tạo ra trạng thái hợp lệ. `WARN` chỉ phù hợp khi nhóm có thể chứng minh việc bỏ qua điều kiện không gây sai dữ liệu hoặc sai schema. Với điều kiện bảo vệ dữ liệu, hãy ưu tiên dừng.

## 6. Thiết kế test matrix cho precondition

Không chỉ chạy thử một lần với database ở trạng thái “đúng”. Mỗi precondition cần được kiểm tra ở trạng thái đạt, không đạt và không thể đánh giá.

Ví dụ test matrix cho changeset thêm cột:

| Ca kiểm thử | Trạng thái database | Kết quả kỳ vọng |
|---|---|---|
| P1 | Bảng tồn tại, cột chưa tồn tại | Precondition đạt; changeset được thực thi |
| P2 | Bảng không tồn tại | `HALT`; không chạy DDL |
| P3 | Bảng tồn tại, cột đã tồn tại | Điều kiện `not columnExists` không đạt; dừng |
| P4 | Tài khoản không đọc được metadata cần thiết | Error; dừng và ghi nhận quyền thiếu |
| P5 | Sai database/schema | Điều kiện hoặc kiểm tra target phát hiện; không chạy nhầm |
| P6 | Property bắt buộc chưa được định nghĩa | Dừng trước thay đổi phụ thuộc property |
| P7 | DBMS khác DBMS được hỗ trợ | Filter/precondition xử lý đúng; không chạy SQL không tương thích |
| P8 | Database đúng nhưng dữ liệu vi phạm quy tắc | `sqlCheck` fail; changeset không chạy |
| P9 | Query precondition không hợp lệ | `onError` được kích hoạt; không coi như điều kiện đạt |
| P10 | Dữ liệu bị thay đổi đồng thời | Kiểm thử race condition và xác nhận constraint cuối cùng vẫn bảo vệ dữ liệu |

Mỗi ca cần lưu: database fixture/version, Liquibase version, command, output, trạng thái schema trước/sau và hàng lịch sử được ghi nhận hay không.

## 7. Tạo database fixture có thể lặp lại

Một bộ test tốt phải tái tạo được trạng thái database. Có thể chuẩn bị các fixture độc lập:

- **Empty database:** chưa có bảng nghiệp vụ và chưa có changeset.
- **Baseline database:** schema đúng ở release trước.
- **Precondition satisfied:** đủ bảng/cột/constraint và dữ liệu hợp lệ.
- **Precondition failed:** thiếu bảng, thiếu cột, có duplicate hoặc NULL không cho phép.
- **Precondition error:** tài khoản thiếu quyền hoặc query tham chiếu sai đối tượng.
- **Partially migrated:** trạng thái mô phỏng lỗi giữa chừng, có thể chứa một số đối tượng đã tạo.
- **Already migrated:** changeset đã có trong `DATABASECHANGELOG`.

Dùng container database, schema dùng riêng hoặc database tạm theo pipeline. Mỗi ca nên khởi tạo từ trạng thái đã biết và dọn dẹp sau khi chạy. Không dùng một database dùng chung cho nhiều test song song nếu chúng có thể tranh `DATABASECHANGELOGLOCK` hoặc làm thay đổi fixture của nhau.

## 8. Kiểm thử precondition bằng Liquibase CLI

Một chuỗi lệnh thường dùng:

```bash
# Kiểm tra changelog và một số vấn đề cấu trúc
liquibase --defaults-file=liquibase.properties validate

# Xem changeset còn pending
liquibase --defaults-file=liquibase.properties status

# Sinh SQL dự kiến
liquibase --defaults-file=liquibase.properties update-sql

# Thực thi trên database test
liquibase --defaults-file=liquibase.properties update
```

`validate` không chứng minh mọi precondition sẽ đạt trên database đích. `status` không mô phỏng DDL/DML. `update-sql` giúp review SQL nhưng không tái hiện đầy đủ lock, transaction, lỗi quyền, tải hoặc thay đổi đồng thời. Muốn kiểm tra `sqlCheck`, metadata và hành vi `onFail`/`onError`, phải chạy trong database fixture thực sự.

Sau mỗi lần chạy, kiểm tra:

- Output có đúng hành vi `HALT`, `WARN`, `CONTINUE` hoặc `MARK_RAN` không?
- Changeset có được thêm vào `DATABASECHANGELOG` không?
- Schema/data có thay đổi đúng phạm vi không?
- Có lock còn giữ bất thường trong `DATABASECHANGELOGLOCK` không?
- Có statement nào được thực thi trước khi điều kiện thất bại không?

## 9. Kiểm thử lỗi giữa chừng trong một changeset

Một changeset có thể chứa nhiều change hoặc nhiều statement. Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "TEST-4201-create-customer-audit"
      author: "database-platform"
      changes:
        - createTable:
            tableName: customer_audit
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
        - sql:
            sql: "INSERT INTO table_that_does_not_exist(id) VALUES (1)"
```

Đây là ví dụ lỗi có chủ đích để thử nghiệm trên database disposable. Statement đầu có thể tạo bảng, statement sau cố tình tham chiếu bảng không tồn tại. Kết quả cuối phụ thuộc DBMS, loại DDL, transaction và cấu hình `runInTransaction`; không giả định mọi database đều tự rollback toàn bộ changeset.

### 9.1. Transaction mặc định và runInTransaction

Liquibase thường chạy changeset trong transaction nếu DBMS và change type hỗ trợ, với `runInTransaction` mặc định là true. Tuy nhiên:

- Không phải mọi DBMS đều hỗ trợ transactional DDL.
- Một số DDL tự commit hoặc không thể rollback theo transaction thông thường.
- Một số lệnh như tạo index concurrent có giới hạn không chạy trong transaction block.
- Nếu đặt `runInTransaction: false`, statement có thể commit riêng hoặc để lại thay đổi trước khi lỗi.
- Một changeset gồm nhiều statement với `runInTransaction: false` có thể để database ở trạng thái dở dang.

Không đặt `runInTransaction: false` chỉ để tránh một lỗi lock hay timeout. Chỉ dùng khi DBMS/command bắt buộc, sau khi thiết kế cách phát hiện và phục hồi trạng thái một phần.

### 9.2. Chia changeset theo ranh giới phục hồi

Nếu mỗi bước có thể kiểm chứng độc lập, tách thành changeset nhỏ:

1. Tạo bảng/cột nền tảng.
2. Nạp hoặc backfill dữ liệu.
3. Kiểm tra dữ liệu.
4. Thêm constraint/index.
5. Chuyển ứng dụng sang cấu trúc mới.

Việc tách giúp biết bước nào đã hoàn thành và giới hạn phạm vi điều tra. Nhưng mỗi changeset riêng vẫn cần có ID ổn định, precondition, rollback hoặc forward-fix phù hợp.

## 10. Mô phỏng lỗi có kiểm soát

Nên mô phỏng lỗi trên database disposable hoặc bản sao cô lập, với snapshot có thể tạo lại. Một số cách kiểm thử:

| Loại lỗi | Cách mô phỏng trong test | Điều cần quan sát |
|---|---|---|
| Precondition fail | Tạo fixture thiếu bảng hoặc có duplicate | Changeset dừng đúng thời điểm |
| Precondition error | Dùng tài khoản test thiếu quyền đọc metadata hoặc query test sai | `onError` xử lý, không tiếp tục |
| Permission denied | Thu hồi quyền DDL trên schema test | Schema không bị thay đổi ngoài dự kiến |
| SQL error | Dùng statement test có lỗi xác định | Transaction/partial state theo DBMS |
| Lock timeout | Giữ lock bằng session test khác rồi chạy migration | Thời gian chờ và trạng thái sau timeout |
| Deadlock | Hai transaction test khóa tài nguyên theo thứ tự khác nhau | Log, retry và trạng thái changeset |
| Connection interruption | Ngắt kết nối runner trong môi trường cô lập | Xác định statement đã commit hay chưa |
| Process termination | Dừng tiến trình test tại điểm kiểm soát | Lock và metadata sau khi tiến trình dừng |
| Disk/log capacity | Dùng môi trường có quota giới hạn được kiểm soát | Lỗi và khả năng tiếp tục sau khi khắc phục |

Không cố tình gây lỗi, kill process hoặc làm đầy disk trên production. Bài test phải có cách khôi phục fixture, log đầy đủ và không dùng dữ liệu thật ngoài phạm vi được phép.

## 11. Hiểu DATABASECHANGELOG và trạng thái sau lỗi

`DATABASECHANGELOG` là lịch sử changeset mà Liquibase ghi nhận. Khi điều tra lỗi, phải đối chiếu bảng này với trạng thái schema/data thật.

Các tình huống có thể gặp:

- Changeset chưa chạy: chưa có hàng lịch sử; không có nghĩa schema chắc chắn chưa thay đổi nếu một thao tác ngoài Liquibase đã thực hiện.
- Changeset chạy thành công: thường có hàng với ID, author, filename, checksum và execution type tương ứng.
- Changeset được đánh dấu `MARK_RAN`: lịch sử ghi nhận changeset đã được đánh dấu, nhưng các change bên trong không nhất thiết đã được Liquibase thực thi.
- Changeset chạy lại theo cấu hình như `runOnChange`: lịch sử có thể phản ánh lần chạy lại tùy semantics và phiên bản.
- DDL không transactional thất bại giữa chừng: schema có thể đã đổi một phần trong khi changeset chưa có bản ghi thành công như người vận hành mong đợi.

Không suy ra trạng thái schema chỉ từ một hàng lịch sử. Kiểm tra catalog/metadata DBMS, dữ liệu và log thực thi.

Ví dụ truy vấn lịch sử:

```sql
SELECT
    id,
    author,
    filename,
    md5sum,
    exectype,
    dateexecuted,
    orderexecuted
FROM databasechangelog
ORDER BY orderexecuted DESC;
```

Tên bảng/schema có thể khác theo cấu hình. Tránh chỉnh/xóa hàng lịch sử trực tiếp bằng SQL để làm Liquibase chạy lại; điều đó phá vỡ mối liên hệ giữa lịch sử và trạng thái database.

## 12. Phân tích lock sau khi tiến trình bị gián đoạn

Liquibase dùng `DATABASECHANGELOGLOCK` để ngăn nhiều tiến trình cùng chạy update trên một database tại một thời điểm. Nếu runner bị kill, máy mất kết nối hoặc tiến trình dừng bất thường, lock có thể cần được kiểm tra.

Trước tiên, xác định:

- Có job Liquibase nào còn chạy không?
- Có session database tương ứng còn hoạt động không?
- Lock được giữ từ thời điểm nào và bởi tiến trình nào?
- Runner dừng trước, trong hay sau statement nào?
- Có một tiến trình khác đang thực hiện migration cùng database không?

Không xóa hàng lock bằng SQL ngay khi thấy `LOCKED=1`. Nếu tiến trình cũ vẫn chạy, giải phóng lock thủ công có thể cho phép hai lần migration cạnh tranh.

Sau khi xác nhận không còn tiến trình update đang hoạt động và đã kiểm tra trạng thái DB, có thể dùng lệnh Liquibase:

```bash
liquibase --defaults-file=liquibase.properties list-locks
liquibase --defaults-file=liquibase.properties release-locks
```

Kiểm tra cú pháp theo phiên bản CLI. `release-locks` chỉ giải phóng trạng thái khóa của Liquibase; nó **không rollback DDL/DML đã chạy**, không sửa changeset lỗi và không xác nhận database đã nhất quán. Sau khi giải phóng, phải tiếp tục điều tra schema/data trước khi chạy update lại.

## 13. Phục hồi sau lỗi giữa chừng: quy trình từng bước

### Bước 1: Dừng các lần triển khai cạnh tranh

Tạm dừng job tự động, rolling deployment hoặc pipeline khác có thể chạy Liquibase trên cùng database. Không retry liên tục để “thử xem có qua không”.

### Bước 2: Lưu bằng chứng

Giữ lại:

- Log đầy đủ của Liquibase và runner.
- Artifact, commit, digest, master changelog và các file SQL/CSV.
- Phiên bản Liquibase, JDBC driver, DBMS và cấu hình.
- Thời điểm lỗi, command, changeset ID/author.
- Trạng thái `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.
- Thông tin session, lock, transaction và câu SQL cuối cùng đã chạy nếu có.

### Bước 3: Đọc trạng thái database thật

Kiểm tra bảng/cột/index/constraint/view có tồn tại không; định nghĩa có đúng không; dữ liệu có được insert/update một phần không; số hàng nào bị tác động; trigger/sequence có thay đổi không. Dùng catalog DBMS và query đối soát, không chỉ dựa vào output CLI.

### Bước 4: Phân loại trạng thái

| Trạng thái | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Chưa có thay đổi | Không có đối tượng/data mới; không có changeset history | Khắc phục nguyên nhân rồi chạy lại sau kiểm chứng |
| Đã rollback bởi transaction | Các thay đổi trong transaction không còn | Xác minh DDL/DML thực sự transactional rồi chạy lại |
| Thay đổi một phần | Một số statement/đối tượng đã tồn tại hoặc dữ liệu đã ghi | Thiết kế forward-fix/cleanup có điều kiện; không chạy lại mù |
| Thay đổi hoàn tất nhưng history không rõ | Schema/data đã đạt nhưng history thiếu hoặc khác | Đối chiếu artifact, kiểm tra nguyên nhân và xử lý metadata theo quy trình được duyệt |
| History đã ghi nhưng schema sai | Changeset được ghi nhận nhưng đối tượng không đúng | Điều tra drift, thêm changeset sửa hoặc phục hồi có kiểm soát |

### Bước 5: Chọn cách phục hồi

Chọn một trong các hướng sau sau khi hiểu trạng thái:

- **Retry:** chỉ khi đã chứng minh thao tác trước không để lại thay đổi hoặc changeset được thiết kế idempotent và trạng thái đã đáp ứng điều kiện.
- **Forward-fix:** tạo changeset mới để đưa schema/data từ trạng thái hiện tại về trạng thái đích.
- **Rollback:** chỉ khi rollback đã được kiểm chứng, dữ liệu phát sinh có thể bảo toàn và DBMS hỗ trợ hành vi cần thiết.
- **Restore/PITR:** khi dữ liệu bị hỏng/mất và rollback logic không thể khôi phục chính xác.
- **Manual reconciliation:** DBA thực hiện bước khôi phục đặc thù, có audit và sau đó đồng bộ lịch sử Liquibase theo quy trình được phê duyệt.

### Bước 6: Kiểm chứng sau phục hồi

Chạy lại query kiểm tra, so sánh schema, đối chiếu số hàng, constraint/index và ứng dụng. Kiểm tra `DATABASECHANGELOG`/lock, chạy `validate`, `status`, `update-sql` với đúng artifact và xác nhận lần update kế tiếp không chạy lại một thay đổi đã áp dụng ngoài dự kiến.

## 14. Thiết kế changeset để retry an toàn

Một migration dễ phục hồi thường có phạm vi nhỏ, điều kiện rõ và khả năng phát hiện trạng thái đã đạt.

Nguyên tắc:

- Giữ changeset đã triển khai bất biến; sửa lỗi bằng changeset mới.
- Dùng ID duy nhất, filename và `logicalFilePath` ổn định.
- Đặt precondition kiểm tra prerequisite thực sự cần thiết.
- Dùng constraint của DBMS để bảo vệ invariant, không dựa riêng vào precondition.
- Tách DDL, backfill và constraint thành bước có thể kiểm tra khi cần.
- Backfill theo batch có checkpoint và điều kiện lọc rõ.
- Tránh statement không idempotent nếu có khả năng retry.
- Nếu không thể idempotent, xây runbook xác định chính xác trạng thái trước khi retry.
- Ghi rollback hoặc forward-fix thực tế; không khai báo rollback giả chỉ để changelog trông đầy đủ.

### 14.1. Ví dụ backfill có điều kiện

Ví dụ cập nhật cột mới chỉ cho những hàng chưa có giá trị:

```yaml
databaseChangeLog:
  - changeSet:
      id: "TEST-4301-backfill-customer-display-name"
      author: "customer-platform"
      changes:
        - sql:
            sql: |-
              UPDATE customer
              SET display_name = name
              WHERE display_name IS NULL
```

Điều kiện `WHERE display_name IS NULL` có thể giúp tránh ghi đè giá trị đã được cập nhật, nhưng chưa đủ để khẳng định toàn bộ backfill an toàn. Phải xem quy tắc nghiệp vụ, dữ liệu được ghi đồng thời, null semantics, transaction size và khả năng chạy lại. Với bảng lớn, tách batch/job có checkpoint thường phù hợp hơn một changeset chạy lâu.

## 15. Kiểm thử rollback và phục hồi riêng biệt

Rollback là một đường thực thi khác với update; không được coi là đã kiểm thử chỉ vì changeset có khai báo `rollback`.

Các mức kiểm thử:

1. **Sinh SQL rollback:** xem câu lệnh sẽ chạy.
2. **Thực thi rollback trên database test:** kiểm tra đối tượng và dữ liệu sau rollback.
3. **Rollback sau khi ứng dụng đã ghi dữ liệu mới:** đánh giá có mất dữ liệu hay không.
4. **Rollback trong trạng thái một phần:** xác định rollback có xử lý được các statement đã commit trước lỗi không.
5. **Khôi phục từ backup/PITR:** đo thời gian và kiểm tra tính toàn vẹn.

Liquibase có lệnh `update-testing-rollback` để thực hiện update rồi thử rollback các changeset trên môi trường thử nghiệm. Đây là công cụ hữu ích cho một số changelog, nhưng không thay thế test dữ liệu thực tế và không nên chạy trên production. Một số change type hoặc SQL tùy chỉnh có thể không có rollback tự sinh; cần khai báo rollback hoặc quy trình phục hồi riêng.

Ví dụ các lệnh kiểm tra:

```bash
# Sinh SQL rollback theo tag đã được tạo trong fixture
liquibase --defaults-file=liquibase.properties rollback-sql --tag=before-test

# Thử update rồi rollback trên database disposable
liquibase --defaults-file=liquibase.properties update-testing-rollback
```

Cú pháp option và khả năng của command tùy phiên bản Liquibase. Tạo tag đúng thời điểm, xác nhận target database và lưu output trước khi thực thi.

## 16. Test lock, timeout và transaction

Một bộ test nên bao gồm:

- Giữ lock trên bảng mục tiêu từ session A, chạy migration ở session B và quan sát timeout.
- Chạy transaction dài để xác định DDL phải chờ hay bị từ chối.
- Tạo deadlock có kiểm soát giữa hai session test và kiểm tra log.
- Hủy connection trong lúc statement đang chạy, sau đó kiểm tra commit/rollback.
- Thử thay đổi có DDL transactional và DDL không transactional trên đúng DBMS.
- Kiểm tra `DATABASECHANGELOGLOCK` sau khi lệnh kết thúc bình thường và bất thường.

Đừng suy luận từ PostgreSQL sang MySQL/Oracle/SQL Server. DDL transaction, implicit commit, online index và lock mode khác nhau theo DBMS và phiên bản. Ghi lại kết quả riêng cho từng môi trường triển khai.

## 17. Tích hợp kiểm thử precondition và phục hồi vào CI/CD

Một pipeline phù hợp có thể gồm:

```text
Pull request
    |
    v
Validate changelog + review preconditions
    |
    v
Khởi tạo DB fixture theo từng test case
    |
    v
Test điều kiện đạt / fail / error
    |
    v
Test update + rollback
    |
    v
Mô phỏng lỗi giữa chừng trong DB disposable
    |
    v
Đối chiếu schema + data + DATABASECHANGELOG + lock
    |
    v
Rehearsal trên DB tương đương
    |
    v
Approval và deploy
```

Các nguyên tắc vận hành:

- Mỗi job test dùng database/schema cô lập, không chia sẻ lịch sử Liquibase.
- Dùng cùng Liquibase version, driver, extension và changelog với artifact release.
- Test trên đúng DBMS production; nếu hỗ trợ nhiều DBMS, có matrix riêng.
- Không cấp secret production cho pipeline chạy code từ nhánh chưa tin cậy.
- Lưu log, SQL preview, kết quả fixture và phiên bản artifact.
- Production migration chỉ có một luồng điều phối rõ ràng; tránh nhiều instance Spring Boot cùng chạy changelog khác nhau.

Spring Boot có thể tự chạy Liquibase khi ứng dụng khởi động. Nếu chọn cách này, kiểm tra thứ tự khởi tạo datasource, profile, changelog và số instance. Với thay đổi cần kiểm soát thời điểm hoặc mô phỏng lỗi, một job migration riêng thường dễ quan sát và điều phối hơn.

## 18. Runbook khi migration thất bại giữa chừng

**Ngay khi phát hiện lỗi**

- Dừng retry tự động và tạm dừng các release cạnh tranh.
- Ghi nhận changeset ID, author, artifact, Liquibase version và lỗi đầu tiên.
- Xác định job còn sống hay đã dừng; kiểm tra session và lock.
- Không sửa `DATABASECHANGELOG`/`DATABASECHANGELOGLOCK` trực tiếp.

**Trong quá trình điều tra**

- Xác định statement cuối cùng được xác nhận thành công.
- Kiểm tra trạng thái schema/data thực tế và mức transaction.
- Đối chiếu `DATABASECHANGELOG` với output/log.
- Xác định có thay đổi ngoài Liquibase hay thao tác thủ công không.
- Phân loại lỗi precondition fail, precondition error hay lỗi trong change execution.

**Trước khi chạy lại**

- Chọn retry, forward-fix, rollback hoặc restore.
- Xác minh hành động có thể chạy lặp và không ghi đè dữ liệu hợp lệ.
- Nếu lock còn tồn tại, xác nhận không có tiến trình update đang chạy rồi mới dùng `release-locks`.
- Chạy validate/status/update-sql và query đối soát trên bản sao.
- Ghi approval và người chịu trách nhiệm tiếp tục.

**Sau phục hồi**

- Kiểm tra schema, dữ liệu, constraint/index và lịch sử changeset.
- Kiểm tra metric, ứng dụng, job nền và replication.
- Lưu artifact, log, quyết định và nguyên nhân gốc để bổ sung test regression.

## 19. Các lỗi thiết kế kiểm thử thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ test precondition ở trạng thái đúng | Không biết hành vi khi fail/error | Có fixture đạt, không đạt và lỗi đánh giá |
| Dùng `MARK_RAN` chỉ để pipeline xanh | History ghi đã chạy trong khi schema chưa đạt | Kiểm tra định nghĩa đối tượng và chỉ dùng có bằng chứng |
| Dùng `WARN` cho điều kiện bắt buộc | Migration tiếp tục với prerequisite thiếu | Dùng `HALT` và sửa trạng thái trước |
| Tin rằng precondition ngăn race | Dữ liệu có thể đổi sau lần kiểm tra | Dùng constraint và phối hợp writer |
| Giả định DDL luôn rollback | Schema có thể thay đổi một phần | Test theo DBMS/version và từng statement |
| Đặt `runInTransaction: false` tùy tiện | Có thể để lại trạng thái dở dang | Chỉ dùng khi bắt buộc và có recovery plan |
| Retry changeset không kiểm tra trạng thái | Tạo object trùng hoặc ghi dữ liệu lặp | Đối chiếu schema/data/history trước retry |
| Giải phóng lock khi job còn chạy | Hai tiến trình có thể chạy cạnh tranh | Xác nhận session/process đã dừng |
| Chỉ test rollback SQL được sinh | Không biết dữ liệu có thực sự được khôi phục | Thực thi rollback trên fixture có dữ liệu |
| Sửa history bằng SQL để vượt lỗi | Mất tính tin cậy của metadata | Khôi phục bằng quy trình có audit và approval |

## 20. Bài thực hành tổng hợp

Tạo một database test có bảng `customer` và một changeset dự định thêm unique constraint cho `(tenant_id, email)`.

1. Tạo fixture sạch với bảng tồn tại và không có duplicate.
2. Viết `preConditions` gồm `tableExists` và `sqlCheck`; chạy và xác nhận changeset được áp dụng.
3. Tạo fixture có duplicate; chạy lại và xác nhận `onFail: HALT` ngăn DDL.
4. Tạo fixture thiếu quyền đọc metadata hoặc chạy query precondition; xác nhận `onError` dừng đúng cách.
5. Tạo một fixture có unique index cùng tên nhưng định nghĩa sai; chứng minh chỉ kiểm tra tên là chưa đủ để `MARK_RAN`.
6. Tạo changeset test có hai statement, statement thứ hai cố ý lỗi; chạy với cấu hình transaction mặc định trên DBMS thử nghiệm và ghi trạng thái sau lỗi.
7. Lặp lại trong fixture riêng với `runInTransaction: false`; so sánh phần thay đổi còn lại và lịch sử.
8. Kiểm tra lock bằng session thứ hai, sau đó mô phỏng runner bị dừng trong môi trường disposable.
9. Xác minh `DATABASECHANGELOGLOCK`, xác nhận không còn tiến trình sống rồi thử `release-locks`.
10. Thiết kế forward-fix hoặc rollback phù hợp với trạng thái thật; không xóa history bằng SQL.
11. Chạy `update-testing-rollback` trên fixture phù hợp và kiểm tra dữ liệu sau rollback.
12. Đưa các test case vào CI để mỗi pull request có thể tái tạo kết quả.

### Checklist phê duyệt migration

- [ ] Precondition đúng phạm vi changelog/changeset và kiểm tra đúng prerequisite.
- [ ] Đã test điều kiện đạt, fail và error.
- [ ] `onFail`/`onError` được chọn theo rủi ro; không dùng `MARK_RAN`/`CONTINUE` tùy tiện.
- [ ] `sqlCheck` trả kết quả đơn, có hiệu năng phù hợp và không tạo race assumption sai.
- [ ] Constraint database vẫn bảo vệ invariant sau precondition.
- [ ] Đã test trên DBMS/version tương ứng với production.
- [ ] Đã mô phỏng lỗi giữa các statement trong môi trường cô lập.
- [ ] Đã xác minh hành vi transaction và `runInTransaction`.
- [ ] Đã kiểm tra `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` sau lỗi.
- [ ] Có tiêu chí retry, forward-fix, rollback hoặc restore theo trạng thái thực tế.
- [ ] Rollback đã được thực thi trên fixture có dữ liệu, không chỉ sinh SQL.
- [ ] Có runbook, log, metric và owner quyết định dừng/tiếp tục.
- [ ] CI dùng artifact, Liquibase version và driver nhất quán với release.

**Kết luận:** kiểm thử preconditions, lỗi giữa chừng và phục hồi giúp nhóm hiểu migration sẽ phản ứng thế nào khi database đúng, sai hoặc không thể xác minh điều kiện; đồng thời biết trạng thái nào có thể còn lại khi DDL/DML thất bại. Hãy tạo fixture cho fail/error, mô phỏng lỗi trên database cô lập, kiểm tra transaction theo DBMS, đối chiếu `DATABASECHANGELOG` cùng `DATABASECHANGELOGLOCK`, và chỉ retry/rollback/forward-fix sau khi đã xác minh schema và dữ liệu thật. Đây là nền tảng để quy trình `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` triển khai đáng tin cậy qua nhiều môi trường, Spring Boot và CI/CD.
