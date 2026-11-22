# Xem trước SQL hoàn tác bằng các lệnh rollback tương ứng

## 1. Vì sao cần xem SQL hoàn tác trước khi thực thi?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Ngoài việc chạy migration và tích hợp Spring Boot hoặc CI/CD trên nhiều môi trường, người vận hành phải biết **database sẽ thay đổi thế nào nếu cần quay lại một mốc trước đó**. Đây là mục tiêu của chương **Hoàn tác**, đặc biệt là thao tác **xem trước SQL hoàn tác**.

Giả sử một lần phát hành vừa thêm cột `customer_account.status_code`, nạp dữ liệu tham chiếu và tạo index. Ứng dụng mới có lỗi nên nhóm muốn rollback. Trước khi thực hiện, cần trả lời:

1. Những changeset nào sẽ bị chọn để hoàn tác?
2. Liquibase dự định sinh những câu `DROP`, `ALTER`, `DELETE` hoặc SQL nào?
3. Thứ tự SQL có tôn trọng phụ thuộc giữa bảng, cột và constraint không?
4. Có câu lệnh nào làm mất dữ liệu hoặc ảnh hưởng bản ghi tạo sau migration không?
5. Rollback có khả thi trên DBMS, phiên bản Liquibase và lịch sử database hiện tại không?
6. Có cần rollback ứng dụng, tạm ngừng writer, phục hồi backup hoặc tiến hành migration bù không?

Những lệnh như `rollback-sql`, `rollback-count-sql` và `rollback-to-date-sql` được sử dụng để **sinh SQL dự kiến của thao tác rollback**, trước khi thực hiện các lệnh rollback tương ứng. Chúng giúp review, kiểm tra và phê duyệt; **không phải lời bảo đảm rằng SQL đó chạy thành công, khôi phục đầy đủ dữ liệu hoặc an toàn trong mọi điều kiện runtime**.

Bài này tập trung vào cách chọn đúng lệnh preview, xác minh phạm vi changeset, đọc SQL sinh ra, xử lý trường hợp không có rollback phù hợp và đưa bước preview thành cổng kiểm soát trong pipeline triển khai.

## 2. Phân biệt preview rollback với rollback thực sự

Liquibase có hai nhóm thao tác:

| Nhóm | Ví dụ | Hành vi |
|---|---|---|
| **Xem trước** | `rollback-sql`, `rollback-count-sql`, `rollback-to-date-sql` | Tính phạm vi rollback dựa trên changelog và lịch sử, sau đó xuất SQL dự kiến; không chủ động áp dụng các câu SQL rollback lên dữ liệu nghiệp vụ |
| **Thực thi** | `rollback`, `rollback-count`, `rollback-to-date` | Thực hiện rollback theo điều kiện được chỉ định và cập nhật lịch sử theo cơ chế Liquibase |

Các tên lệnh trên theo dạng kebab-case của những phiên bản Liquibase CLI hiện đại. Một số phiên bản/tài liệu cũ có cách viết camelCase như `rollbackSQL`, `rollbackCountSQL` hoặc `rollbackToDateSQL`. Phải đối chiếu cú pháp và tính năng bằng tài liệu/trợ giúp **cùng phiên bản Liquibase đang được dự án khóa**, thay vì trộn cách viết của hai phiên bản.

Một câu lệnh preview thường cần **kết nối đến database đích** vì Liquibase phải đọc `DATABASECHANGELOG` và thông tin liên quan để xác định changeset đã triển khai. Việc xem trước không đồng nghĩa chạy SQL hoàn tác, nhưng vẫn cần cấu hình kết nối, quyền truy cập metadata và tuân thủ quy trình bảo mật.

### 2.1. Preview không giống dry-run của toàn bộ hệ thống

Một file SQL được sinh ra chưa mô phỏng được:

- Lock thực tế, timeout, mức tranh chấp và tác động đến giao dịch đang chạy.
- Dữ liệu mới hoặc dữ liệu thay đổi kể từ thời điểm tạo bản preview.
- Ảnh hưởng ứng dụng đang sử dụng bảng, cột, index, view hoặc constraint sẽ bị thay đổi.
- Tác động downstream như CDC, báo cáo, cache, đồng bộ sự kiện hoặc dữ liệu đã xuất sang hệ thống khác.
- Khả năng DBMS rollback DDL trong transaction hay commit ngầm.
- Giá trị bị mất do thao tác DROP, DELETE hoặc chuyển đổi dữ liệu không đảo ngược.

Vì vậy, quy trình đúng không phải **preview → tin tưởng tuyệt đối → chạy**, mà là **xác định phạm vi → preview → review SQL và dữ liệu → kiểm thử → phê duyệt → thực thi có giám sát → hậu kiểm**.

## 3. Ba cách xác định phạm vi rollback thường gặp

| Mục tiêu | Lệnh preview | Lệnh thực thi tương ứng | Ranh giới cần xác định |
|---|---|---|---|
| Quay về một tag được gắn trong lịch sử | `rollback-sql --tag=...` | `rollback --tag=...` | Những changeset sau mốc tag |
| Hoàn tác một số changeset gần nhất | `rollback-count-sql --count=...` | `rollback-count --count=...` | Số changeset cần hoàn tác |
| Quay về trạng thái tại một thời điểm | `rollback-to-date-sql --date=...` | `rollback-to-date --date=...` | Thời gian thực thi trong lịch sử |

Đây là **ba kiểu lựa chọn khác nhau**. Chúng có thể cho ra cùng một tập changeset trên một database cụ thể, nhưng không thể mặc nhiên coi tag, count và timestamp là tương đương. Chỉ khi đã kiểm tra lịch sử và danh sách changeset bị ảnh hưởng mới có thể khẳng định phạm vi giống nhau.

### 3.1. Chọn cách nào trong thực tế?

- **Tag:** thường phù hợp với mốc phát hành đã được đặt và quản lý rõ ràng, ví dụ sau lần deploy ổn định.
- **Count:** hữu ích khi biết chính xác số changeset cuối cần đảo và lịch sử không bị tác động bởi những bước phát sinh khác.
- **Date:** hữu ích khi cần nhắm tới một thời điểm, nhưng nhạy với timezone, timestamp và những triển khai xen kẽ.

Không dùng count chỉ vì lần trước đã gọi `update-count --count=2`. Những changeset khác có thể đã được áp dụng sau đó, khiến `rollback-count --count=2` nhắm vào một tập khác.

## 4. Chuẩn bị một ví dụ có lịch sử rõ ràng

Giả sử database thử nghiệm có bảng `customer_account(id, email)`. Một root changelog có ba changeset:

- `001`: tạo bảng danh mục `account_status_catalog`.
- `002`: nạp mã trạng thái `ACTIVE`.
- `003`: thêm cột nullable `status_code` vào `customer_account`.

Ví dụ YAML tự chứa về ba bước này:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-status-catalog
      author: migration-team
      changes:
        - createTable:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  type: varchar(20)
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            tableName: account_status_catalog

  - changeSet:
      id: 002-seed-active-status
      author: migration-team
      changes:
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: ACTIVE
      rollback:
        - delete:
            tableName: account_status_catalog
            where: "code = 'ACTIVE'"

  - changeSet:
      id: 003-add-status-code
      author: migration-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: varchar(20)
      rollback:
        - dropColumn:
            tableName: customer_account
            columnName: status_code
```

Các đoạn `rollback` tường minh giúp dễ hình dung SQL được sinh ra. Tuy nhiên, **chúng chỉ an toàn theo giả định của một database lab**:

- `dropColumn` sẽ làm mất dữ liệu trong `status_code` nếu ứng dụng đã bắt đầu ghi vào đó.
- `delete` mã `ACTIVE` có thể bị khóa ngoại ngăn cản hoặc làm sai dữ liệu tham chiếu nếu có bản ghi dùng mã đó.
- `dropTable` không phù hợp nếu bảng đã được ứng dụng dùng hoặc có đối tượng phụ thuộc.

Khi xây dựng bài thực hành, không sử dụng bảng production thật. Một ví dụ rollback *có thể sinh SQL* chưa chứng minh rollback *có thể khôi phục nghiệp vụ*.

### 4.1. Lịch sử sau khi áp dụng cả ba changeset

Trong database lab, `DATABASECHANGELOG` có thể chứa các bản ghi như sau:

| ID | AUTHOR | FILENAME | EXECTYPE |
|---|---|---|---|
| `001-create-status-catalog` | `migration-team` | Đường dẫn logic của changelog | `EXECUTED` |
| `002-seed-active-status` | `migration-team` | Đường dẫn logic của changelog | `EXECUTED` |
| `003-add-status-code` | `migration-team` | Đường dẫn logic của changelog | `EXECUTED` |

Giá trị `FILENAME` thực tế phụ thuộc đường dẫn logic khi Liquibase nạp file, không được tự suy từ ví dụ. Ba thành phần `id`, `author` và `FILENAME` tạo bộ định danh changeset; `MD5SUM` giúp kiểm tra nội dung thay đổi.

Trước mọi rollback, hãy truy vấn lịch sử thực tế và xác định schema/tên bảng metadata của dự án. Nếu ứng dụng kết nối tới nhiều database, mỗi database có lịch sử riêng; không dùng lịch sử staging để quyết định phạm vi rollback production.

## 5. Xem trước theo số lượng bằng rollback-count-sql

Giả sử ba changeset ví dụ đã được áp dụng và muốn đảo hai bước cuối: nạp mã `ACTIVE` và thêm cột `status_code`.

### 5.1. Cú pháp

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count-sql --count=2
```

Trong đó:

- `--changelog-file` chọn đúng root changelog đang quản lý lịch sử.
- `rollback-count-sql` yêu cầu xuất SQL của thao tác rollback theo số changeset.
- `--count=2` chỉ định hai changeset sẽ được xét để hoàn tác theo lịch sử và cấu hình hiện hành.

Cần cung cấp kết nối database và các tùy chọn ngữ cảnh tương ứng, nhưng không đưa username/password vào ví dụ hoặc log chia sẻ công khai.

### 5.2. SQL dự kiến có thể trông như thế nào?

Nếu hai changeset gần nhất đúng là `003` và `002`, phạm vi hợp lý sẽ là **đảo 003 trước, rồi 002**:

```sql
-- Minh họa ý tưởng SQL, KHÔNG phải output nguyên văn của Liquibase.
ALTER TABLE customer_account DROP COLUMN status_code;
DELETE FROM account_status_catalog WHERE code = 'ACTIVE';
```

Tùy DBMS, Liquibase có thể sinh SQL khác, bổ sung schema, quoting, delimiter, thao tác lịch sử hoặc câu lệnh điều phối. Không dùng đoạn minh họa này để thay thế SQL preview thực tế; cần đọc output mà Liquibase tạo ra từ chính database và changelog đích.

**Hai vấn đề phải review:** thứ nhất, xóa cột có thể mất dữ liệu; thứ hai, DELETE có thể vi phạm khóa ngoại. Nếu có phụ thuộc mới phát sinh sau lần update, tập rollback ban đầu có thể không an toàn dù cú pháp SQL hợp lệ.

### 5.3. So sánh với lệnh thực thi

Lệnh thực hiện tương ứng là:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count --count=2
```

Không chạy lệnh thực thi này chỉ để “kiểm tra thử” trên production. Trước đó phải review preview, xác nhận tập changeset, backup, điều kiện vận hành và thử rollback trên môi trường đại diện.

### 5.4. Count không phải số câu SQL và không phải số thay đổi nghiệp vụ

Một changeset có thể tạo ba index và thêm hai constraint; `count=1` vẫn có thể sinh nhiều câu SQL rollback. Một changeset dữ liệu có thể cập nhật hàng triệu dòng; count cũng chỉ xem đó là một đơn vị thay đổi.

Ngoài ra, các cơ chế `runAlways`, `runOnChange`, precondition với `MARK_RAN` hoặc thay đổi lịch sử có thể khiến quan hệ giữa số changeset, số câu SQL và số bản ghi thay đổi khó suy ra từ count đơn thuần. Cần xem `EXECTYPE`, danh tính và thứ tự lịch sử thay vì chỉ tin con số.

## 6. Xem trước theo tag bằng rollback-sql

Tag là một mốc được gắn trong lịch sử database để diễn đạt trạng thái triển khai, ví dụ trước một phiên bản ứng dụng quan trọng.

### 6.1. Tạo mốc tag có chủ đích

Một cách đánh dấu mốc là lệnh `tag` của Liquibase khi database đã ở trạng thái mong muốn. Minh họa cú pháp:

```bash
liquibase tag --tag=baseline-before-status-migration
```

Các thay đổi được áp dụng **sau mốc này** là ứng viên để rollback trở về tag. Cần xác minh tag đã được ghi nhận thành công và nó đặt đúng sau changeset nào trong `DATABASECHANGELOG`. Trong changelog cũng có thể dùng change type `tagDatabase` khi phù hợp; cách tag xuất hiện trong lịch sử và hành vi rollback cần được kiểm tra theo phiên bản Liquibase sử dụng.

Không coi tên tag là một nhánh Git hoặc snapshot dữ liệu. **Tag chỉ đánh dấu một mốc lịch sử**, không sao lưu nội dung bảng.

### 6.2. Xem SQL để quay về tag

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-sql --tag=baseline-before-status-migration
```

Ý định là sinh SQL để đảo những thay đổi đã áp dụng sau tag được chỉ định. Lệnh thực thi tương ứng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback --tag=baseline-before-status-migration
```

Trong ví dụ, nếu tag được đặt ngay sau `001`, rồi lần lượt chạy `002` và `003`, preview rollback tới tag có thể chọn `003` và `002`. Nhưng nếu tag đặt sau `002`, phạm vi chỉ còn `003`. Vì vậy **vị trí lịch sử của tag quan trọng hơn tên tag**.

### 6.3. Khi nào tag tốt hơn count?

Tag hữu ích khi:

- Nhiều changeset có thể được thêm vào giữa các lần phát hành, khiến count khó đoán.
- Muốn xác định một mốc phát hành thay vì “N bước cuối”.
- Cần quy trình review và phê duyệt dựa trên các release boundary.

Tuy nhiên, không đặt tag trùng tên hoặc không kiểm chứng giá trị tag trên từng môi trường. Hai database có thể mang cùng tên tag nhưng có tập changeset đã áp dụng khác nhau trước/sau mốc. Khi rollback production, kiểm tra `DATABASECHANGELOG.TAG` trên database production, không dựa vào trạng thái dev.

## 7. Xem trước theo thời điểm bằng rollback-to-date-sql

Lệnh rollback theo thời điểm xác định changeset liên quan đến lịch sử thực thi so với một mốc ngày giờ.

### 7.1. Cú pháp

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-to-date-sql --date="2026-11-18 10:30:00"
```

Lệnh thực thi tương ứng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-to-date --date="2026-11-18 10:30:00"
```

Thời điểm trên chỉ là **giá trị giả định trong bài học**, không phải mốc phù hợp với bất kỳ database thật nào. Trước khi dùng lệnh, cần xác nhận cú pháp ngày giờ của phiên bản Liquibase, timezone của môi trường chạy, cách lưu/hiển thị `DATEEXECUTED` và ý nghĩa chính xác của mốc lựa chọn.

### 7.2. Rủi ro của timestamp

Có thể xảy ra các trường hợp:

- Nhiều changeset cùng được ghi trong một giây hoặc gần sát mốc.
- Pipeline và database hiển thị giờ theo timezone khác.
- Lệnh chạy trên môi trường A và B với cùng chuỗi ngày giờ nhưng lịch sử khác nhau.
- Đã có changeset mới được áp dụng giữa lúc preview và thực thi.
- Cần rollback đúng một release nhưng mốc thời gian lại cắt ngang hai giai đoạn phụ thuộc nhau.

Vì vậy, trước khi tin vào một mốc ngày giờ, hãy truy vấn `DATEEXECUTED`/`ORDEREXECUTED` và xem chính xác các changeset nằm trước và sau mốc. Nếu mục tiêu là quay về một release đã được đánh dấu chính thức, tag thường dễ diễn giải hơn timestamp.

## 8. Những lệnh preview khác: hiểu đúng phạm vi và khả năng hỗ trợ

Ba lệnh chính ở trên xử lý **các changeset đã triển khai** theo lịch sử. Một số phiên bản/edition Liquibase còn hỗ trợ các lệnh tạo SQL rollback cho những trường hợp khác, chẳng hạn:

- `future-rollback-sql`: dùng để xem SQL rollback giả định cho các changeset còn pending, trước khi chúng được áp dụng. Đây là công cụ đánh giá khả năng phục hồi của migration tương lai, **không** thay thế rollback thực tế của những thay đổi đã chạy.
- Những biến thể tập trung vào **một changeset cụ thể**, như lệnh preview một changeset ở các phiên bản/edition có hỗ trợ, có thể yêu cầu định danh, tác giả, file và các tùy chọn đặc biệt.

Không nên coi những lệnh chuyên biệt này luôn có sẵn trong mọi bản Liquibase Community/Secure hoặc mọi phiên bản. Khi cần, kiểm tra CLI thực tế và chính sách license. **Trọng tâm của bài này** vẫn là ba cặp lệnh theo tag, count và date vì chúng mô tả ba cách chọn ranh giới rollback phổ biến.

## 9. Liquibase lấy SQL rollback từ đâu?

SQL được sinh ra tùy loại change và cách khai báo rollback:

1. **Rollback tự động theo change type**: một số thay đổi như tạo bảng hoặc thêm cột có thể có thao tác đảo được Liquibase hỗ trợ.
2. **Rollback tường minh trong changelog**: người viết cung cấp các change đảo hoặc SQL rollback.
3. **Không có cách đảo tự động an toàn**: nhiều thao tác dữ liệu/SQL tùy ý hoặc thay đổi phá hủy cần rollback tường minh, migration bù hoặc phục hồi dữ liệu.

Ví dụ phần rollback YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-customer-note
      author: migration-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: note
                  type: varchar(500)
      rollback:
        - dropColumn:
            tableName: customer_account
            columnName: note
```

Đoạn rollback có thể sinh `ALTER TABLE ... DROP COLUMN ...`, nhưng nếu ứng dụng đã ghi dữ liệu `note` thì giá trị này sẽ bị mất. Tính đảo ngược của **cấu trúc** không đồng nghĩa dữ liệu được bảo toàn.

### 9.1. DML cần rollback theo phạm vi chính xác

Ví dụ một changeset thêm mã tham chiếu:

```yaml
databaseChangeLog:
  - changeSet:
      id: 011-seed-reference-status
      author: migration-team
      changes:
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: PENDING
      rollback:
        - delete:
            tableName: account_status_catalog
            where: "code = 'PENDING'"
```

DELETE chỉ an toàn khi mã này chưa được dữ liệu nghiệp vụ tham chiếu và không bị sử dụng như một giá trị bắt buộc của ứng dụng hiện tại. Không viết rollback dạng `DELETE FROM account_status_catalog` không có điều kiện, vì nó có thể xóa cả dữ liệu không thuộc changeset.

### 9.2. Formatted SQL cần cú pháp rollback phù hợp

Với changelog formatted SQL:

```sql
--liquibase formatted sql
--changeset migration-team:012-create-audit-index
CREATE INDEX idx_audit_created_at ON audit_event (created_at);
--rollback DROP INDEX idx_audit_created_at;
```

Chỉ thị `--rollback` thể hiện câu lệnh đảo. Ví dụ `DROP INDEX ...` có cú pháp phụ thuộc DBMS; hãy kiểm tra trên đúng hệ quản trị. Một file SQL thường được nạp bằng `sqlFile` không mặc nhiên có các chỉ thị changeset/rollback giống formatted SQL. Phải cung cấp rollback ở changeset bao bọc hoặc chọn cơ chế hỗ trợ khác.

### 9.3. rollback-sql không thể tự phục hồi dữ liệu đã mất

Các trường hợp rủi ro:

| Thay đổi đã chạy | SQL rollback có thể có | Vấn đề cần giải quyết |
|---|---|---|
| `createTable` | `DROP TABLE` | Xóa cả dữ liệu được ghi sau đó và có thể gây đứt phụ thuộc |
| `addColumn` | `DROP COLUMN` | Mất dữ liệu mới trong cột |
| `dropColumn` | Không thể tự khôi phục chính xác từ DDL | Cần dữ liệu gốc từ backup/snapshot |
| `UPDATE` quy đổi nhiều giá trị về một mã | Có thể có SQL cập nhật ngược | Không suy được giá trị gốc nếu phép ánh xạ nhiều-một |
| `INSERT` dữ liệu tham chiếu | `DELETE` bản ghi thêm vào | Có thể bị FK chặn hoặc gây lỗi nghiệp vụ |
| Thay kiểu `VARCHAR → NUMERIC` | ALTER ngược kiểu cũ | Mất biểu diễn như số 0 đầu chuỗi, định dạng tiền |
| Replace view | SQL thay lại định nghĩa cũ nếu có | DBMS có thể hạn chế bỏ/đổi kiểu cột; quyền và dependency |

Preview có thể cho thấy SQL phá hủy rất rõ ràng nhưng **không cảnh báo đầy đủ mọi hậu quả nghiệp vụ**. Reviewer phải hiểu loại dữ liệu nào có thể mất và có phương án phục hồi tương ứng.

## 10. Cách đọc và review output rollback SQL

Đừng chỉ xem lệnh có sinh SQL hay không. Hãy kiểm tra theo thứ tự:

### 10.1. Đúng danh sách changeset và đúng chiều đảo

Từ `DATABASECHANGELOG`, lập danh sách changeset đã áp dụng theo thời điểm/thứ tự. Đối chiếu từng changeset dự định rollback với từng phần SQL. Các bước phụ thuộc thường phải đảo theo thứ tự ngược, ví dụ bỏ FK trước, bỏ cột sau và cuối cùng mới bỏ bảng danh mục nếu an toàn.

Nếu SQL preview thiếu một bước bắt buộc hoặc chứa thay đổi ngoài release cần rollback, **dừng** và điều tra. Không điều chỉnh `count` tùy tiện cho đến khi bản preview “trông hợp lý”.

### 10.2. DDL có xóa hoặc đổi ràng buộc không?

Tìm các lệnh:

```sql
DROP TABLE ...
ALTER TABLE ... DROP COLUMN ...
ALTER TABLE ... DROP CONSTRAINT ...
DROP VIEW ...
DROP INDEX ...
```

Đây là những dạng câu lệnh đáng review, **không phải một script hợp lệ để thực thi nguyên khối**. Với mỗi thao tác, trả lời: còn đối tượng nào phụ thuộc? Có cần GRANT lại không? Ứng dụng phiên bản cũ/mới có chịu được không? Dữ liệu trong cột/bảng sẽ đi đâu?

### 10.3. DML có ảnh hưởng nhiều hàng hơn dự kiến không?

Tìm `DELETE`, `UPDATE`, `TRUNCATE` và điều kiện `WHERE`. Xem liệu một lệnh dữ liệu có:

- Giới hạn đúng ID/marker được changeset quản lý.
- Vô tình xóa dữ liệu do ứng dụng tạo sau migration.
- Vi phạm FK, trigger, chính sách audit hoặc logic downstream.
- Đưa giá trị về mặc định không còn phản ánh nghiệp vụ.
- Có thể chạy lại một cách an toàn nếu quá trình thất bại.

Với dữ liệu quan trọng, cần truy vấn chỉ đọc để ước lượng số hàng bị ảnh hưởng và chuẩn bị backup. Không mặc định rollback dữ liệu là phép đảo chính xác.

### 10.4. Quoting, schema và cú pháp DBMS

Đối chiếu tên bảng/cột có cần quoting, schema mặc định, catalog, kiểu dữ liệu và câu SQL riêng DBMS. Một bản preview tạo trên PostgreSQL không bảo đảm dùng được trên SQL Server. Các lệnh phải được sinh và thử trên đúng loại database/phiên bản của môi trường đích.

### 10.5. Transaction, khóa và khoảng dừng

Kiểm tra các thao tác có thể giữ lock mạnh hoặc rewrite bảng. Liquibase có thể chạy một số changeset trong transaction khi DBMS hỗ trợ, nhưng không được coi rollback nhiều changeset là một transaction toàn cục. Nếu nửa đợt rollback thành công rồi đợt còn lại lỗi, database có thể nằm ở trạng thái trung gian cần xử lý có kiểm chứng.

## 11. Kiểm tra lịch sử trước khi preview rollback

Một truy vấn SQL chỉ đọc trên bảng metadata mặc định:

```sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM,
       TAG
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED DESC, DATEEXECUTED DESC;
```

Mục tiêu:

1. Xác nhận database đang ở trạng thái nào.
2. Xác định tag hoặc timestamp thực tế, không đoán từ tên release.
3. Xác định N changeset gần nhất theo lịch sử khi muốn dùng count.
4. Kiểm tra danh tính `ID`, `AUTHOR`, `FILENAME` và các lần chạy đặc biệt.
5. Phát hiện các thay đổi ngoài đợt deploy dự kiến.

Tên bảng và schema của `DATABASECHANGELOG` có thể tùy chỉnh. Nếu dự án dùng tên/schema khác mặc định, phải truy vấn đúng metadata của kết nối đích. Đừng suy diễn lịch sử từ trạng thái source code: changeset tồn tại trong repository chưa chắc đã chạy trên database đó.

### 11.1. Vì sao không thể chỉ so sánh với changelog mới nhất?

Một rollback cần definition và SQL đảo của các changeset **đã được triển khai**. Nếu nhóm xóa file changelog cũ, đổi `id`/`author` hoặc di chuyển đường dẫn mà không bảo toàn `logicalFilePath`, Liquibase có thể không còn tìm hoặc nhận diện chính xác thay đổi cần đảo.

Do đó, changelog phải được quản lý phiên bản và giữ khả năng truy xuất lịch sử. Không chỉnh các changeset đã chạy chỉ để “đổi rollback” mà không đánh giá checksum và các môi trường. Những điều chỉnh bắt buộc cần theo quy trình được review riêng, có thử nghiệm.

## 12. Preview và lệnh thực thi phải dùng cùng cấu hình

Giả sử pipeline muốn rollback hai changeset trên database staging. Tập cấu hình ảnh hưởng kết quả gồm:

- Root changelog và toàn bộ file include.
- Phiên bản Liquibase, edition và extension.
- JDBC URL, database, schema/catalog, driver.
- Context filter, label filter và những điều kiện chọn changeset liên quan.
- Properties, variables, search path/classpath.
- Trạng thái `DATABASECHANGELOG` tại thời điểm thực thi.

Ví dụ, lệnh preview có filter:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=staging \
  --label-filter=release-candidate \
  rollback-count-sql --count=2
```

Nếu chạy thật, phải xác nhận cùng môi trường và phạm vi:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=staging \
  --label-filter=release-candidate \
  rollback-count --count=2
```

Tên và ý nghĩa tùy chọn context/label có thể khác theo phiên bản Liquibase; không thay đổi tham số một cách tùy tiện giữa hai lệnh. Hơn nữa, ngay cả khi cú pháp giống nhau, **lịch sử có thể thay đổi** nếu pipeline khác chạy migration trong khoảng thời gian giữa preview và rollback. Cần kiểm tra lại lịch sử và kiểm soát quyền chạy song song.

### 12.1. Không dùng preview từ môi trường khác làm chứng cứ đủ

Staging có thể đã chạy thêm một changeset so với production; production có dữ liệu nhiều hơn hoặc DBMS khác. Vì vậy:

- Preview trên staging hữu ích để thử quy trình.
- Preview chính thức trước rollback production phải dùng đúng lịch sử production.
- Test khôi phục dữ liệu nên diễn ra trên bản sao có dữ liệu đại diện, không phải truy vấn thử trực tiếp rồi rollback sản xuất.

Bản preview lưu trong artifact cần ghi kèm thời điểm, commit, môi trường, phiên bản Liquibase, tag/count/date và danh sách ID liên quan để reviewer hiểu nó áp dụng cho trạng thái nào.

## 13. Khác biệt giữa update-sql và rollback-sql

Trong các quy trình migration, hai nhóm xem trước thường đi cùng nhau nhưng khác mục tiêu:

| Tiêu chí | `update-sql` | `rollback-sql` và biến thể |
|---|---|---|
| Hướng thay đổi | Tiến từ trạng thái hiện tại tới tập changeset pending | Lùi về một mốc lịch sử |
| Nguồn logic | Changeset chưa áp dụng và cấu hình thực thi | Những changeset đã áp dụng cùng rollback được Liquibase xác định |
| Câu hỏi chính | “Nếu deploy, SQL nào sẽ chạy?” | “Nếu hoàn tác, SQL nào sẽ chạy?” |
| Rủi ro cần review | Tạo/sửa schema, backfill, constraints | Xóa/thay đối tượng, mất dữ liệu, khôi phục compatibility |
| Điều kiện đủ an toàn? | Không, phải test | Không, phải test |

Với một release cần rollback mạnh, lý tưởng là **review khả năng rollback trước cả khi chạy update**. Ví dụ chạy kiểm thử update trên bản sao rồi xem `rollback-count-sql` của những changeset vừa áp dụng; điều này cho thấy rollback có tồn tại và có thể thử trong môi trường gần thực tế.

## 14. Rollback theo tag, count và date trong cùng một ví dụ

Giả sử một database lab có lịch sử:

| Thứ tự | Thay đổi | Thời điểm giả định |
|---|---|---|
| 001 | Tạo bảng danh mục | 09:00 |
| Tag `before-status-feature` | Đánh dấu trạng thái ổn định | 09:05 |
| 002 | Nạp mã `ACTIVE` | 09:10 |
| 003 | Thêm cột `status_code` | 09:15 |

Không có changeset khác trong khoảng này. Khi đó:

- `rollback-sql --tag=before-status-feature` dự kiến nhắm những thay đổi sau tag: 003 và 002.
- `rollback-count-sql --count=2` dự kiến cũng nhắm 003 và 002, **nếu** 003 và 002 là hai thay đổi gần nhất phù hợp với lần rollback.
- `rollback-to-date-sql --date="2026-11-18 09:05:00"` có thể cho phạm vi tương ứng **nếu** mốc được diễn giải đúng theo lịch sử, timezone và độ chính xác timestamp.

Sự tương đương này **chỉ là giả định của ví dụ**. Nếu 004 đã được áp dụng lúc 09:17, count=2 có thể chọn 004 và 003; tag hoặc date còn có thể chọn cả 004. Nếu một precondition làm `MARK_RAN` hoặc lịch sử chứa hành vi chạy lại, người vận hành cần xem kết quả thực tế thay vì đoán theo tên thay đổi.

Vì thế, không xây pipeline rollback chỉ bằng việc đổi qua lại giữa tag, count và date; luôn cố định một cơ chế cho release và kiểm tra danh tính các changeset.

## 15. Tích hợp Spring Boot: rollback không nên phụ thuộc vào startup

Spring Boot thường tích hợp Liquibase như sau:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Cấu hình này chủ yếu phục vụ **update khi ứng dụng khởi động**, không phải cơ chế phê duyệt và thực thi rollback có kiểm soát theo tag/count/date.

Với rollback ở môi trường production, thường nên:

1. Tách job rollback/migration khỏi quá trình khởi động của các replica ứng dụng.
2. Dùng artifact changelog đúng phiên bản và cấu hình Liquibase thống nhất.
3. Có quyền và phê duyệt chuyên biệt để chỉ định database đích.
4. Tạm kiểm soát các writer/instance ứng dụng phụ thuộc schema sẽ bị rollback.
5. Review SQL và thử rollback trên môi trường đại diện.
6. Thực hiện rollback khi hệ thống đã có kế hoạch tương thích ứng dụng.
7. Chỉ cho ứng dụng khởi động/tiếp tục ghi sau khi hậu kiểm đạt.

Cần đặc biệt cảnh giác với tình huống: pipeline rollback schema xong, nhưng một instance Spring Boot mới khởi động với Liquibase tự động bật và tiếp tục chạy những changeset còn pending theo changelog đang đóng gói. `DATABASECHANGELOGLOCK` giúp điều phối migration đồng thời, **không tự ngăn việc triển khai lại một changeset sau rollback**. Quyền sở hữu và thời điểm chạy migration phải được thiết kế thống nhất.

## 16. CI/CD: biến preview SQL thành release gate

Một quy trình rollback có thể theo sơ đồ:

```text
Phát hiện cần rollback
          |
          v
Xác nhận lỗi + mốc khôi phục
          |
          v
Chọn tag / count / date
          |
          v
Đọc DATABASECHANGELOG thực tế
          |
          v
Sinh rollback-sql tương ứng
          |
          v
Review ID bị ảnh hưởng + SQL + dữ liệu + dependency
          |
          v
Kiểm thử rollback trên database đại diện
          |
          v
Phê duyệt và kiểm soát ứng dụng/writer
          |
          v
Thực thi rollback tương ứng
          |
          v
Đối chiếu lịch sử, schema, dữ liệu, ứng dụng
```

### 16.1. Thông tin nên ghi trong phiếu phê duyệt

| Thông tin | Ví dụ hoặc yêu cầu |
|---|---|
| Môi trường đích | Production của hệ thống cụ thể, không ghi mơ hồ “database chính” |
| Root changelog | Đường dẫn resource và commit/artifact đã triển khai |
| Version | Liquibase/driver/DBMS version, extension nếu có |
| Cách chọn mốc | Tag, count hoặc timestamp đúng cú pháp phiên bản |
| Changeset bị chọn | ID + AUTHOR + FILENAME, thứ tự rollback |
| SQL dự kiến | Output của lệnh preview từ đúng database đích |
| Đánh giá rủi ro | DROP, DELETE, mất dữ liệu, index, FK, lock, ứng dụng |
| Phương án phục hồi | Backup, point-in-time recovery, migration bù hoặc hướng xử lý dữ liệu |
| Kết quả thử nghiệm | Log, thời gian chạy, kiểm tra schema/dữ liệu/consumer |
| Người phê duyệt | Vai trò kỹ thuật/vận hành theo quy định dự án |

SQL preview có thể chứa tên bảng, dữ liệu tham chiếu hoặc thông tin hạ tầng. Chỉ lưu vào hệ thống artifact/log có quyền truy cập phù hợp. Không in credentials/secret trong file hoặc báo cáo.

### 16.2. Recheck ngay trước khi rollback

Giữa bước review và thực thi, cần xác nhận database không có changeset mới làm đổi phạm vi. Nếu có, **hủy phê duyệt cũ, tạo preview mới**, đối chiếu lại ID và SQL. Đây là nguyên tắc tương tự việc chống retry vô thức của `update-count`: cùng một count không bảo đảm cùng một tập changeset khi lịch sử đã đổi.

## 17. Các lỗi thường gặp khi preview SQL rollback

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lệnh `rollback-sql` không tìm thấy tag | Tag chưa được ghi, sai tên, sai database/schema lịch sử | Kiểm tra `DATABASECHANGELOG.TAG` trên đúng đích |
| Preview count chọn sai changeset | Có thay đổi mới sau đợt release hoặc lịch sử khác dự kiến | Đối chiếu ID/author/file/thứ tự, không chỉ count |
| Preview theo date khác kỳ vọng | Sai timezone, timestamp hoặc điểm cắt | Kiểm tra `DATEEXECUTED` và phạm vi gần mốc |
| SQL rollback không được sinh | Change không có rollback hỗ trợ, thiếu khai báo hoặc cấu hình không đúng | Bổ sung kế hoạch rollback/migration bù, kiểm thử |
| SQL chứa DROP TABLE/DROP COLUMN không mong muốn | Rollback cấu trúc có thể phá dữ liệu mới | Kiểm tra dữ liệu và ứng dụng, cân nhắc backup hoặc forward fix |
| Preview thành công nhưng rollback chạy lỗi | Dependency, FK, quyền, lock, dữ liệu hoặc DBMS không tương thích | Kiểm thử trên bản sao, kiểm tra quyền và trạng thái thực |
| Không tìm được changeset trong changelog | File cũ bị xóa/di chuyển, id/author/path đổi | Khôi phục changelog lịch sử, kiểm tra `logicalFilePath` |
| Staging và production sinh SQL khác nhau | Khác DBMS, lịch sử, cấu hình hoặc dữ liệu | Preview riêng cho từng môi trường, không tái sử dụng kết quả |
| Rollback xong rồi tự update trở lại | Ứng dụng/worker khác còn bật Liquibase update tự động | Thống nhất quyền sở hữu migration và lịch phát hành |
| Rollback-count không đảo đúng lần update-count cuối | Hai tập thay đổi không còn tương ứng | Xác định phạm vi từ lịch sử, chọn tag/mốc phù hợp |
| Một phần rollback đã được áp dụng | DDL không giao dịch như kỳ vọng hoặc lỗi giữa các changeset | Dừng, kiểm tra schema/dữ liệu và lịch sử, lập phương án tiếp tục |
| Xem trước SQL nhưng vẫn chưa biết mất bao nhiêu dữ liệu | Preview là cú pháp SQL, không phải data quality report | Truy vấn số hàng dự kiến ảnh hưởng, backup và đối soát độc lập |

Không giải quyết các lỗi trên bằng cách xóa dòng `DATABASECHANGELOG`, chỉnh checksum hoặc chuyển từ lệnh preview sang lệnh thực thi khi chưa hiểu phạm vi. Những thao tác đó có thể làm lịch sử Liquibase sai lệch với trạng thái database.

## 18. Bài thực hành: so sánh ba kiểu rollback preview

**Mục tiêu:** trên một database PostgreSQL thử nghiệm riêng, dùng cùng changelog ba changeset ở phần 4 để sinh và so sánh SQL hoàn tác theo count, tag và date. Không thực hành trên database production.

### Bước 1. Tạo dữ liệu và mốc lịch sử

1. Chuẩn bị bảng `customer_account(id, email)` trong database lab.
2. Dùng changelog có ba changeset 001–003; xác định rollback cho từng bước.
3. Áp dụng `001` và ghi một tag ở đúng mốc sau 001.
4. Áp dụng `002` và `003`, ghi lại `DATEEXECUTED` và `ORDEREXECUTED` của từng changeset.
5. Xác nhận `DATABASECHANGELOG` chứa đúng những bản ghi mong đợi và tên tag có thể truy vấn được.

### Bước 2. Sinh SQL theo count

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count-sql --count=2
```

Ghi lại hai bộ định danh dự kiến bị đảo, thứ tự câu SQL và các lệnh `DROP COLUMN`/`DELETE`.

### Bước 3. Sinh SQL theo tag

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-sql --tag=before-status-feature
```

Tên tag trong lệnh phải được thay bằng **tên thực đã gắn ở bước 1**. So sánh danh sách changeset và SQL với kết quả count. Nếu khác, giải thích khác biệt từ vị trí tag hoặc lịch sử.

### Bước 4. Sinh SQL theo thời điểm

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-to-date-sql --date="2026-11-18 09:05:00"
```

Đây là mốc minh họa: phải thay bằng thời điểm thực tế thuộc lịch sử lab và chú ý timezone. So sánh phạm vi với hai lệnh trước, không giả định chúng luôn giống nhau.

### Bước 5. Đánh giá tính an toàn

Tạo dữ liệu thử nghiệm mới trong cột `status_code` và một bản ghi có thể tham chiếu mã `ACTIVE`. Xem liệu SQL preview có làm mất dữ liệu hoặc bị khóa ngoại chặn không. Giải thích vì sao một câu `DROP COLUMN` có thể được Liquibase sinh đúng nhưng vẫn không phù hợp để thực thi.

### Bước 6. Kiểm thử rollback chỉ khi đủ điều kiện

Sau khi đã xác định cách xử lý dữ liệu và phụ thuộc, thử rollback trên **bản sao lab** đã sao lưu. Kiểm tra schema, dữ liệu, lịch sử, quyền và hành vi ứng dụng thử nghiệm. Không dùng kết quả preview đơn lẻ làm căn cứ cho rollback production.

### Bước 7. Thử tình huống lịch sử bị thay đổi

Thêm một changeset 004 vào database lab sau khi đã tạo preview count=2; chạy lại preview. Trả lời vì sao count có thể nhắm vào 004 và 003 thay vì 003 và 002, và tại sao pipeline phải lấy lại phê duyệt khi lịch sử đã đổi.

**Tiêu chí hoàn thành:** nêu đúng phạm vi theo từng cơ chế tag/count/date, đọc được SQL nguy hiểm, chỉ ra giới hạn rollback dữ liệu và biết khi nào nên dừng để thiết kế migration bù hoặc phục hồi từ backup.

## 19. Checklist trước khi chấp thuận rollback

- [ ] Đã xác định lý do rollback và trạng thái ứng dụng/database cần quay về.
- [ ] Đã chọn đúng cơ chế tag, count hoặc date thay vì dùng một con số tùy ý.
- [ ] Đã đọc lịch sử `DATABASECHANGELOG` trên chính database đích.
- [ ] Đã xác minh tag hoặc timestamp, ID/AUTHOR/FILENAME và thứ tự changeset.
- [ ] Đã khóa đúng root changelog, artifact, Liquibase/DBMS version và bộ lọc.
- [ ] Đã chạy lệnh `rollback-*-sql` tương ứng và lưu output an toàn để review.
- [ ] Đã kiểm tra danh sách changeset được chọn trước khi xem từng câu SQL.
- [ ] Đã rà soát các thao tác DROP, DELETE, ALTER, index, FK và view phụ thuộc.
- [ ] Đã ước lượng dữ liệu sẽ bị ảnh hưởng và xác nhận khả năng khôi phục.
- [ ] Đã đánh giá dữ liệu mới phát sinh sau migration, không chỉ dữ liệu ban đầu.
- [ ] Đã thử rollback trên database đại diện và kiểm tra transaction/lock.
- [ ] Đã chuẩn bị backup, migration bù hoặc kế hoạch forward fix nếu rollback không đảo ngược.
- [ ] Đã phối hợp rollback ứng dụng và kiểm soát writer, job/replica Spring Boot.
- [ ] Đã kiểm tra lại lịch sử ngay trước khi thực thi, tránh thay đổi giữa preview và rollback.
- [ ] Đã định nghĩa hậu kiểm schema, dữ liệu, quyền, hiệu năng và `DATABASECHANGELOG`.
- [ ] Chỉ tiến hành lệnh rollback thực sự khi phạm vi, SQL và kế hoạch phục hồi đã được phê duyệt.

**Kết luận:** xem trước SQL hoàn tác là bước bắt buộc về tư duy an toàn trước khi đảo migration trên database quan trọng. `rollback-sql` dùng mốc tag, `rollback-count-sql` dùng số changeset, còn `rollback-to-date-sql` dùng thời điểm; mỗi lựa chọn cần đối chiếu với lịch sử triển khai thực tế. SQL preview giúp nhìn thấy những thao tác dự kiến nhưng không tự chứng minh tính đúng đắn về dữ liệu, phụ thuộc và ứng dụng. Phải kết hợp preview, review, thử trên môi trường đại diện, kiểm soát triển khai và hậu kiểm để rollback thực sự đáng tin cậy.

