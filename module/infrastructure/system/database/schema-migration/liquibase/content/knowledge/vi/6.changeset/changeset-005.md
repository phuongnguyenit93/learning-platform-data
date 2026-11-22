# Điều khiển thực thi lặp bằng `runAlways` trong Liquibase

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào thuộc tính **`runAlways`** của **changeset**: khi nào Liquibase chạy lại một changeset đã được ghi nhận, dữ liệu lịch sử được cập nhật ra sao, và cần thiết kế thay đổi thế nào để việc lặp không tạo tác dụng phụ nguy hiểm.

Sau bài học, người đọc có thể:

- Giải thích sự khác nhau giữa changeset mặc định, `runAlways` và `runOnChange`.
- Dự đoán changeset có được thực thi trong các lần gọi `update` liên tiếp hay không.
- Viết YAML changeset có `runAlways: true` và precondition thích hợp.
- Đọc kết quả trong `DATABASECHANGELOG`, hiểu checksum và trường hợp sửa nội dung đã triển khai.
- Thiết kế thao tác lặp có kiểm soát, kiểm thử, khôi phục và quyết định cách chạy qua nhiều môi trường.

**Ý chính:** `runAlways` yêu cầu Liquibase **thực thi changeset mỗi lần quy trình cập nhật xem xét changeset đó**, miễn là changeset được chọn bởi các bộ lọc áp dụng và không bị điều kiện khác chặn. Đây là tính năng của hệ thống triển khai migration, không phải cron job hay bộ lập lịch chạy SQL liên tục.

## 2. Cơ chế mặc định của changeset và lý do tồn tại `runAlways`

Liquibase nhận diện một changeset dựa chủ yếu trên tổ hợp **`id` + `author` + định danh đường dẫn changelog** (có thể bị ảnh hưởng bởi cấu hình logical file path). Với changeset thông thường, Liquibase so sánh danh tính và checksum với bản ghi lịch sử trong bảng `DATABASECHANGELOG` để quyết định cần chạy hay kiểm tra tính toàn vẹn.

Xét ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-products
      author: team
      changes:
        - createTable:
            tableName: products
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
```

Ở lần `update` đầu tiên, changeset tạo bảng `products` nếu chưa được triển khai. Sau khi Liquibase ghi nhận thành công, lần `update` sau với changelog không đổi thường bỏ qua changeset đó. Điều này phù hợp với DDL: tạo một bảng nhiều lần thường gây lỗi “table already exists”.

Tuy nhiên, có những thao tác cần **thực hiện ở mỗi lượt triển khai**, dù mã migration không đổi, chẳng hạn cập nhật mốc thời gian kiểm tra schema vào một bản ghi điều hành hoặc đồng bộ một trạng thái được phép ghi đè. Nếu đặt thao tác ấy trong changeset thông thường, nó chỉ chạy lần đầu. `runAlways` cho phép tái thực thi có chủ đích.

### 2.1. Khai báo `runAlways`

Trong YAML changelog, đặt thuộc tính ở cùng cấp với `id`, `author` và `changes`:

```yaml
databaseChangeLog:
  - changeSet:
      id: refresh-migration-marker
      author: team
      runAlways: true
      changes:
        - sql:
            sql: >
              UPDATE migration_execution_marker
              SET last_run_at = CURRENT_TIMESTAMP
              WHERE marker_key = 'liquibase_update'
```

Ví dụ trên **giả định bảng và bản ghi đã tồn tại**. Phần thực hành sau sẽ cung cấp changelog tự chứa để tạo chúng.

Lưu ý viết đúng `runAlways: true`, không đặt thuộc tính bên trong `changes` hay `sql`. Cú pháp tương đương trong XML là `runAlways="true"` trên phần tử `changeSet`. Mặc định, nếu không khai báo `runAlways`, Liquibase xử lý changeset theo cơ chế chạy một lần và ghi nhận lịch sử.

### 2.2. `runAlways` chạy khi nào?

Giả sử có một changeset `runAlways: true`, không có bộ lọc hay precondition chặn và mỗi lệnh đều hoàn tất:

| Sự kiện | Changeset thông thường | Changeset có `runAlways: true` |
|---|---|---|
| Chạy `update` lần 1 | Chạy nếu chưa triển khai | Chạy |
| Chạy `update` lần 2, changelog không đổi | Bỏ qua | Chạy lại |
| Chạy `update` lần 3, không có changeset mới | Bỏ qua | Chạy lại |
| Ứng dụng thực hiện một SQL query thông thường | Không tự chạy | Không tự chạy |
| Tiến trình Liquibase không được khởi chạy | Không chạy | Không chạy |

“Always” nghĩa là **mỗi lần Liquibase xử lý changeset trong quy trình cập nhật**; không có nghĩa “mọi thời điểm”, “mỗi phút”, “mỗi request” hay “mỗi lần database thay đổi”.

Nếu changeset bị loại bởi context/label/DBMS filter, không nằm trong changelog được nạp, hoặc bị điều kiện thực thi ngăn chặn, `runAlways` không ép nó chạy. Vì vậy không thể kết luận “bật `runAlways` thì chắc chắn lệnh SQL sẽ chạy trong mọi lần deploy” mà không xem cấu hình lựa chọn và trạng thái của lần triển khai.

## 3. So sánh `runAlways` và `runOnChange`

Hai thuộc tính có mục đích khác nhau:

| Cấu hình | Thời điểm tái thực thi | Trường hợp phù hợp |
|---|---|---|
| Mặc định (không có hai cờ) | Không chạy lại nếu changeset đã triển khai và hợp lệ | DDL, dữ liệu khởi tạo chạy một lần |
| `runAlways: true` | Mỗi lần Liquibase `update` xem xét changeset được chọn | Cập nhật trạng thái điều hành có chủ đích |
| `runOnChange: true` | Khi nội dung có ý nghĩa đối với checksum thay đổi | Định nghĩa view, stored procedure hoặc logic cần cập nhật |
| Cả hai đều `true` | Mỗi lần cập nhật; cho phép định nghĩa thay đổi được xử lý theo cơ chế `runOnChange` | Trường hợp đặc biệt vừa phải chạy mỗi lần vừa có chủ đích chỉnh sửa changeset |

**Ví dụ:** Nếu dùng `runOnChange: true` trên changeset tạo hoặc thay thế một view, Liquibase chỉ cần thực thi lại khi nội dung view đổi. Nếu dùng `runAlways: true`, thao tác đó được thực thi trong mọi lần `update` kể cả khi view không đổi; như vậy có thể gây thêm lock, chi phí hoặc tác dụng phụ không mong muốn.

Không dùng `runAlways` để “sửa” một DDL không có tính lặp. Ví dụ, thêm cột bằng `addColumn` sẽ thất bại trong lần thứ hai nếu cột đã tồn tại, trừ khi có logic bảo vệ phù hợp. `runAlways` không tự biến câu lệnh thành `IF NOT EXISTS` và cũng không làm thay đổi ngữ nghĩa SQL của DBMS.

## 4. Ví dụ hoàn chỉnh: ghi mốc thời gian mỗi lần Liquibase cập nhật

Giả sử nhóm muốn lưu một mốc thời gian cho biết quy trình migration đã chạy đến bước kiểm tra cập nhật trạng thái trong database. Sử dụng bảng riêng với một hàng được định danh bằng khóa chính. Changelog dưới đây dành cho môi trường hỗ trợ `CURRENT_TIMESTAMP` và kiểu `timestamp`; cần kiểm thử trên DBMS đích.

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-migration-marker
      author: team
      changes:
        - createTable:
            tableName: migration_execution_marker
            columns:
              - column:
                  name: marker_key
                  type: varchar(64)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: last_run_at
                  type: timestamp
        - insert:
            tableName: migration_execution_marker
            columns:
              - column:
                  name: marker_key
                  value: liquibase_update

  - changeSet:
      id: 002-refresh-marker
      author: team
      runAlways: true
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: migration_execution_marker
        - sqlCheck:
            expectedResult: "1"
            sql: >
              SELECT COUNT(*)
              FROM migration_execution_marker
              WHERE marker_key = 'liquibase_update'
      changes:
        - sql:
            sql: >
              UPDATE migration_execution_marker
              SET last_run_at = CURRENT_TIMESTAMP
              WHERE marker_key = 'liquibase_update'
```

### 4.1. Vai trò của từng changeset

**Changeset `001-create-migration-marker`** chỉ chạy một lần theo mặc định:

1. Tạo bảng `migration_execution_marker`.
2. Tạo hàng `marker_key = 'liquibase_update'`.
3. Nhờ khóa chính, bảng chỉ cho phép một hàng với khóa này.

**Changeset `002-refresh-marker`** được đánh dấu `runAlways: true`:

1. Mỗi lần `update` chọn changeset này, Liquibase kiểm tra bảng có tồn tại hay không.
2. Precondition `sqlCheck` xác nhận có đúng một hàng với khóa đã quy định.
3. Khi điều kiện đạt, câu `UPDATE` đặt `last_run_at` theo thời gian do DBMS tính.
4. Liquibase xử lý lịch sử thực thi của changeset theo cơ chế dành cho changeset chạy lại.

`onFail: HALT` yêu cầu dừng nếu precondition không đạt, giúp tránh việc lệnh `UPDATE` âm thầm tác động 0 hàng khi bản ghi đã bị xóa. Precondition này **không** chứng minh thay đổi sẽ luôn thành công: sau bước kiểm tra vẫn có thể có lock, lỗi kết nối hoặc thay đổi đồng thời. DBMS quyết định kết quả thực thi thực tế.

Nếu chỉ muốn ghi lại một mốc thời gian khi deploy, điều này minh họa `runAlways` khá tốt. Nếu cần chứng minh chính xác phiên bản nào đã được triển khai, ai phê duyệt hay toàn bộ thứ tự triển khai, nên dùng thêm hệ thống release/audit chuyên trách; một cột thời gian là chưa đủ.

### 4.2. Điều gì xảy ra qua ba lần cập nhật?

Giả sử gọi `update` ba lần với cùng changelog trên cùng database, không có lỗi và không có bộ lọc:

| Lần gọi | Changeset 001 | Changeset 002 | Trạng thái bảng marker |
|---|---|---|---|
| Thứ nhất | Tạo bảng và hàng | Cập nhật thời gian | Có một hàng; `last_run_at` đã được gán |
| Thứ hai | Bỏ qua | Cập nhật thời gian lần nữa | Vẫn một hàng; giá trị được cập nhật |
| Thứ ba | Bỏ qua | Cập nhật thời gian lần nữa | Vẫn một hàng; giá trị được cập nhật |

Có thể quan sát bằng SQL:

```sql
SELECT marker_key, last_run_at
FROM migration_execution_marker
WHERE marker_key = 'liquibase_update';
```

Một số DBMS tính `CURRENT_TIMESTAMP` theo thời điểm bắt đầu transaction, và thời gian hiển thị còn tùy độ chính xác của cột/công cụ. Hai lần chạy quá sát nhau có thể hiển thị thời gian giống nhau. Vì thế, muốn xác minh **chắc chắn** changeset được chọn và thực thi thì cần đối chiếu log và lịch sử Liquibase thay vì chỉ nhìn chênh lệch timestamp.

### 4.3. Lệnh chạy minh họa

Với Liquibase CLI, sau khi cấu hình URL, username, password và driver từ nguồn an toàn của môi trường, có thể thực hiện hai lần liên tiếp:

```bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
```

Đặt ví dụ changelog vào đường dẫn mà tham số `--changelog-file` trỏ tới. Hai lệnh trên chỉ là **minh họa thao tác**, không phải kết quả đã được thực thi trong bài viết. Không đưa mật khẩu thật vào changelog hoặc mã nguồn; có thể cấp secret từ môi trường CI/CD hay secret manager theo quy trình hệ thống.

## 5. `DATABASECHANGELOG` ghi nhận lần chạy lại ra sao?

Liquibase lưu lịch sử changeset trong bảng `DATABASECHANGELOG`. Với changeset có `runAlways`, bản ghi lịch sử tương ứng thường được **cập nhật thông tin lần thực thi gần nhất** khi changeset chạy lại, thay vì thêm một bản ghi mới cho mỗi lượt chạy.

Ví dụ kiểm tra lịch sử, với tên bảng/cột mặc định:

```sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
WHERE ID = '002-refresh-marker'
  AND AUTHOR = 'team';
```

Các cột có ý nghĩa chính:

- `ID`, `AUTHOR`, `FILENAME`: tạo danh tính của changeset trong changelog.
- `DATEEXECUTED`: thời điểm được Liquibase ghi nhận cho lần thực thi tương ứng.
- `EXECTYPE`: loại thực thi được ghi nhận; sau khi chạy lại có thể thấy trạng thái như `RERAN`.
- `MD5SUM`: checksum của định nghĩa changeset mà Liquibase dùng để theo dõi tính toàn vẹn và phát hiện thay đổi nội dung.

Không nên dùng số hàng trong `DATABASECHANGELOG` để suy ra số lần changeset `runAlways` đã chạy. Chẳng hạn, dù đã chạy lại mười lần, một changeset thường vẫn có một bản ghi nhận diện duy nhất. Nếu cần đếm số lượt thực thi đầy đủ, thiết kế nhật ký riêng hoặc dùng log/audit của pipeline; phải chấp nhận và kiểm soát rủi ro ghi lặp khi thử lại.

### 5.1. Khóa triển khai

Liquibase dùng `DATABASECHANGELOGLOCK` để điều phối các tiến trình Liquibase cùng áp dụng changelog lên một database. Nếu hai tiến trình khởi chạy gần nhau, chúng không nên sửa lịch sử đồng thời một cách tự do. Tuy vậy, sau khi một tiến trình kết thúc và tiến trình khác bắt đầu, changeset `runAlways` có thể chạy lại **lần nữa**.

Khóa Liquibase không thay thế transaction/lock của DBMS, và không khóa các truy cập trực tiếp của ứng dụng hay công cụ SQL bên ngoài. Vì vậy, nếu changeset thay đổi dữ liệu mà ứng dụng cũng ghi, cần thiết kế chiến lược đồng thời và quyền truy cập phù hợp.

## 6. `runAlways` và checksum khi chỉnh sửa changeset

Một hiểu nhầm phổ biến là “đã có `runAlways` thì sửa nội dung changeset đã chạy thế nào cũng được”. Không đúng: Liquibase vẫn theo dõi checksum và kiểm tra tính toàn vẹn của changeset đã triển khai.

Giả sử changeset `002-refresh-marker` đã từng chạy. Sau đó người phát triển sửa câu SQL hoặc thay đổi logic của chính changeset mà vẫn giữ `id`, `author` và file. Khi đó Liquibase có thể phát hiện checksum không khớp và báo lỗi xác thực changeset, dù `runAlways: true` vẫn được khai báo.

Có hai cách xử lý, tùy mục đích:

**Cách ưu tiên khi cần bảo toàn lịch sử:** Giữ changeset đã triển khai ổn định và tạo changeset mới với ID khác để thực hiện phiên bản logic tiếp theo. Điều này giúp người vận hành nhìn được quá trình thay đổi qua các lần deploy.

**Cách chủ động cho changeset được phép thay đổi:** Nếu nghiệp vụ và quy trình đã xác nhận có thể thay đổi nội dung cùng một changeset, kết hợp `runOnChange: true` với `runAlways: true`:

```yaml
databaseChangeLog:
  - changeSet:
      id: refresh-migration-marker
      author: team
      runAlways: true
      runOnChange: true
      changes:
        - sql:
            sql: >
              UPDATE migration_execution_marker
              SET last_run_at = CURRENT_TIMESTAMP
              WHERE marker_key = 'liquibase_update'
```

Khi dùng cả hai cờ, `runAlways` vẫn khiến changeset được thực thi trong mỗi lượt cập nhật có chọn nó; `runOnChange` cho phép Liquibase xử lý các thay đổi nội dung theo cơ chế tương ứng. Việc bật cờ này không đồng nghĩa mọi sửa đổi đều an toàn: câu SQL mới vẫn có thể ghi sai dữ liệu hoặc tạo chi phí lớn. Tính hợp lệ phải được xem xét ở cả mức checksum lẫn hành vi database.

Không thay đổi ID/author/đường dẫn để ép Liquibase coi một changeset cũ là mới nếu không chủ ý tạo migration mới. Không xóa dòng `DATABASECHANGELOG` hay dùng thao tác làm mới checksum một cách tùy tiện chỉ để bỏ qua lỗi. Những thao tác đó ảnh hưởng đến lịch sử và khả năng dự đoán triển khai.

## 7. Thiết kế phép lặp an toàn: idempotency và tác dụng phụ

**Idempotency** là tính chất của thao tác mà sau khi áp dụng nhiều lần, trạng thái mong muốn vẫn tương đương với việc áp dụng một lần, xét theo phạm vi quan tâm. Với `runAlways`, đặc tính này đặc biệt quan trọng vì việc chạy lại là hành vi được thiết kế sẵn.

Ví dụ tương đối an toàn, khi hàng và bảng được bảo đảm tồn tại:

```sql
UPDATE feature_settings
SET enabled = TRUE
WHERE feature_key = 'new_checkout';
```

Lặp câu lệnh có thể vẫn tạo thêm ghi log hoặc lock, nhưng mục tiêu dữ liệu cuối cùng ổn định. Tuy nhiên, câu lệnh này còn có thể ghi đè thay đổi do người vận hành hoặc ứng dụng thực hiện, nên cần xác định rõ nguồn sự thật trước khi áp dụng.

Các ví dụ thường **không an toàn để chạy lại mà không bảo vệ**:

```sql
-- Mỗi lần chạy sẽ cộng thêm 100; rất dễ cộng trùng.
UPDATE account_balance
SET balance = balance + 100
WHERE account_id = 42;

-- Có thể gây trùng dòng hoặc lỗi unique ở lần thứ hai.
INSERT INTO notification_queue(event_type)
VALUES ('SEND_WELCOME_EMAIL');

-- Thường lỗi khi cột đã tồn tại.
ALTER TABLE orders ADD COLUMN status VARCHAR(20);
```

Không nên dùng `runAlways` cho thay đổi tiền, phát thông báo, tạo nhiệm vụ bên ngoài hoặc thao tác có hệ quả một lần nếu không có khóa nghiệp vụ, điều kiện chống trùng và cơ chế khôi phục chặt chẽ. Một lần cập nhật bị lỗi rồi được thử lại có thể khiến thao tác không nguyên tử chạy nhiều lần.

### 7.1. Nguyên tắc viết changeset lặp

1. **Mục đích rõ ràng:** Giải thích tại sao phải chạy ở mỗi lần cập nhật, thay vì chỉ khi nội dung đổi hoặc chỉ một lần.
2. **Chọn thao tác bền vững:** Ưu tiên gán trạng thái mục tiêu ổn định, kiểm tra điều kiện, hoặc `UPSERT` có kiểm soát nếu DBMS hỗ trợ.
3. **Kiểm tra các tiền đề:** Dùng precondition để phát hiện bảng/cột/đối tượng hoặc bản ghi không tồn tại; xem xét `HALT` cho điều kiện thiết yếu.
4. **Giới hạn phạm vi dữ liệu:** Dùng `WHERE`, khóa chính, schema rõ ràng và quyền đúng mức.
5. **Đánh giá chi phí mỗi lần chạy:** Thao tác có scan bảng lớn, rebuild index hoặc lock rộng không nên vô tình chạy khi ứng dụng khởi động.
6. **Phân biệt lặp và khôi phục:** Một câu lệnh chạy lại được chưa chắc có rollback an toàn.

Precondition không tự bảo đảm idempotency. Một `INSERT` có precondition “bảng tồn tại” vẫn có thể thêm trùng dữ liệu mỗi lần; việc kiểm tra điều kiện và hành vi SQL phải tương thích với nhau.

### 7.2. Hạn chế của precondition

Precondition được Liquibase kiểm tra trước khi chạy changeset theo chính sách đã cấu hình. Khi `onFail: HALT`, Liquibase dừng nếu điều kiện thất bại. Các cách xử lý khác như `WARN`, `CONTINUE`, `MARK_RAN` có tác động đến việc chạy hoặc ghi nhận changeset và cần được hiểu rõ trước khi dùng.

Đặc biệt, `MARK_RAN` có thể khiến changeset được đánh dấu xử lý dù các thay đổi bên trong không thực thi. Với changeset cần chạy lại để bảo đảm trạng thái vận hành, hành vi ấy có thể che giấu lỗi nếu không có quan sát bổ sung.

Precondition cũng có rủi ro thay đổi trạng thái giữa lúc kiểm tra và khi DBMS thực thi câu lệnh (race condition). Khi yêu cầu chống ghi trùng thực sự quan trọng, cần dùng constraint, transaction hoặc cơ chế đồng bộ do DBMS hỗ trợ, bên cạnh precondition.

## 8. Transaction, lỗi giữa chừng và rollback

### 8.1. Transaction của changeset

Liquibase thường cố gắng xử lý một changeset trong transaction khi DBMS và loại câu lệnh hỗ trợ; `runInTransaction` ảnh hưởng đến cơ chế này. Nhưng một số DBMS hoặc một số DDL có implicit commit, hạn chế transaction, hoặc không hỗ trợ hoàn tác hoàn toàn. JDBC chuyển lệnh transaction; DBMS mới quyết định ngữ nghĩa thực tế.

Với `runAlways`, một lỗi ở lần chạy sau có thể để lại trạng thái cần kiểm tra:

- Thay đổi dữ liệu đã commit nhưng bản ghi lịch sử chưa cập nhật thành công.
- Một số câu trong changeset thực thi, số khác thất bại do không có transaction nguyên tử.
- Lần thử lại thực thi lại cùng một lệnh có tác dụng phụ.

Không được suy ra rằng vì changeset trước đó đã ghi trong `DATABASECHANGELOG`, lần thực thi hiện tại chắc chắn sẽ không còn rủi ro. `runAlways` cố ý đi qua đường thực thi lại.

### 8.2. Rollback của Liquibase khác rollback giao dịch

`liquibase rollback` là quy trình hoàn nguyên migration dựa trên các thay đổi hoặc khối `rollback` mà Liquibase hỗ trợ; nó không giống lời gọi JDBC `Connection.rollback()` đối với một transaction chưa commit.

Với ví dụ cập nhật `last_run_at`, thực hiện lại `UPDATE` sẽ ghi đè thời gian cũ. Nếu muốn hoàn nguyên **đúng giá trị thời gian trước đó**, phải có cơ chế lưu giá trị cũ hoặc thiết kế bù phù hợp. Một rollback đơn giản đặt `last_run_at = NULL` không thực sự phục hồi được thông tin trước khi thay đổi; vì vậy đừng tuyên bố thao tác có khả năng rollback đầy đủ nếu chưa xây dựng chiến lược khôi phục.

Các thao tác lặp cập nhật số dư, gửi sự kiện hoặc tác động bên ngoài gần như không thể khôi phục chỉ bằng SQL đảo chiều đơn giản. Cần thiết kế giao dịch, audit và quy trình phục hồi riêng. Nếu một changeset có `runAlways` không nên được rollback như migration schema, cũng phải xác định rõ quy ước cho nhóm và kiểm thử hành vi rollback trên DBMS sử dụng.

## 9. Bộ lọc, context, label và điều kiện môi trường

`runAlways` là thuộc tính về tần suất thực thi **trong tập changeset được Liquibase chọn**. Việc chọn changeset còn phụ thuộc changelog, context filter, label filter, DBMS và các tham số triển khai.

Ví dụ một changeset dành cho môi trường kiểm thử:

```yaml
databaseChangeLog:
  - changeSet:
      id: test-only-refresh-marker
      author: team
      contextFilter: test
      runAlways: true
      changes:
        - sql:
            sql: >
              UPDATE migration_execution_marker
              SET last_run_at = CURRENT_TIMESTAMP
              WHERE marker_key = 'liquibase_update'
```

Khi cấu hình Liquibase lựa chọn context `test` phù hợp, changeset có thể chạy lại mỗi lượt. Khi context bị loại trừ, `runAlways` không tự bỏ qua bộ lọc để cưỡng bức chạy. Với một số kiểu biểu thức context, label và tham số phiên bản Liquibase, cách đánh giá có chi tiết riêng; luôn kiểm thử bằng đúng phiên bản và lệnh thực tế.

Không dùng context/label làm biện pháp bảo vệ duy nhất cho một thao tác có nguy cơ cao. Nên có cả quyền database theo môi trường, pipeline chuyên trách, cấu hình kết nối được bảo vệ và bước phê duyệt tương ứng.

Nếu changeset dùng SQL đặc thù một DBMS, cân nhắc giới hạn bằng `dbms` hoặc viết các nhánh riêng. `runAlways` không làm SQL của PostgreSQL tương thích với Oracle, MySQL hay SQL Server.

## 10. Tích hợp với Spring Boot và CI/CD

### 10.1. Liquibase chạy khi Spring Boot khởi động

Khi một ứng dụng Spring Boot tích hợp Liquibase và cho phép chạy migration lúc khởi động, mỗi lần ứng dụng thực hiện chu trình Liquibase update có thể kích hoạt lại changeset `runAlways`. Điều này có các hệ quả:

- Khởi động lại ứng dụng dù mã changelog không đổi vẫn có thể thực thi SQL.
- Môi trường có nhiều replica có thể phát sinh nhiều lượt update tuần tự; khóa Liquibase điều phối truy cập nhưng không biến chúng thành một lượt duy nhất trên toàn bộ lần phát hành.
- Changeset tốn thời gian có thể kéo dài thời gian khởi động ứng dụng hoặc tăng mức cạnh tranh lock.
- Một lần retry khởi động có thể tác động lại vào dữ liệu.

Ví dụ, nếu hệ thống có ba replica và mỗi replica gọi Liquibase trong khi khởi động, một changeset `runAlways` có thể chạy ba lần tùy cấu hình và quy trình khởi động. Do đó, “một lần deploy” không nhất thiết đồng nghĩa “một lần chạy Liquibase”.

Với production, có thể tổ chức migration trong một job chuyên trách trước khi tăng số replica, tùy kiến trúc. Khi đó ứng dụng chạy bằng tài khoản DML hạn chế còn migration job dùng tài khoản có quyền DDL theo nhu cầu. Quyết định này cần gắn với thứ tự triển khai và khả năng tương thích của schema với phiên bản ứng dụng.

### 10.2. Pipeline CI/CD

Trong pipeline, `runAlways` chạy lại mỗi khi job thực sự thực hiện `liquibase update` và changeset được chọn. Nếu pipeline bị retry, re-run thủ công hoặc chạy lại cùng artifact, SQL cũng có thể chạy lại. Quy trình nên xác minh:

- Database URL, schema, danh tính và phiên bản DBMS đúng môi trường.
- Changelog và changeset được kiểm soát phiên bản; ID, author, đường dẫn ổn định.
- Các câu SQL lặp đã được đánh giá về tính lặp an toàn.
- Không có thay đổi checksum ngoài quy trình.
- Log đủ xác định lần chạy mà không làm lộ secret.
- Có kế hoạch xử lý khi thay đổi đã áp dụng một phần.

Với bảng lớn hoặc SQL tốn tài nguyên, đừng coi `runAlways` là lựa chọn mặc định cho mọi deploy. Nếu mục tiêu là công việc theo lịch hay xử lý dữ liệu thường xuyên, scheduler hoặc hệ thống job nghiệp vụ với trạng thái riêng có thể phù hợp hơn. Liquibase được thiết kế chủ yếu để điều phối lịch sử thay đổi database.

## 11. Quan sát, kiểm thử và xử lý sự cố

### 11.1. Kịch bản kiểm thử tối thiểu

Trong database thử nghiệm, kiểm tra theo trình tự:

1. Chuẩn bị một database sạch với quyền migration cần thiết.
2. Nạp changelog ví dụ và chạy `update` lần đầu.
3. Kiểm tra bảng `migration_execution_marker` và các dòng tương ứng trong `DATABASECHANGELOG`.
4. Chạy `update` lần hai mà không sửa changelog.
5. Đối chiếu log: changeset `001` bị bỏ qua còn changeset `002` được thực thi lại.
6. Kiểm tra `DATABASECHANGELOG` để thấy changeset `002` vẫn có danh tính cũ và thông tin thực thi đã cập nhật.
7. Chạy thử với context/label không chọn changeset (nếu có cấu hình bộ lọc) để xác minh nó không bị cưỡng bức chạy.
8. Thử tình huống thiếu hàng marker và xác minh precondition dừng trước khi lệnh `UPDATE` được thực thi.
9. Đánh giá thay đổi nội dung changeset đã triển khai trong môi trường thử nghiệm: kiểm tra lỗi checksum khi chỉ có `runAlways`, sau đó kiểm thử trường hợp cố ý dùng thêm `runOnChange`.
10. Kiểm tra log và trạng thái cuối cùng sau mỗi lần thử; không suy diễn kết quả từ riêng số dòng `DATABASECHANGELOG`.

Các bước trên là hướng dẫn thực hành; bài viết không khẳng định đã chạy lệnh trên database thật.

### 11.2. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Changeset không chạy lại | Thiếu `runAlways: true`, khai báo sai cấp, changeset bị lọc hoặc không được nạp | Kiểm tra YAML thực tế, bộ lọc, changelog root và log |
| Lần chạy thứ hai lỗi “already exists” | SQL/DDL không thể chạy lặp | Chuyển về changeset chạy một lần, hoặc thiết kế lại thao tác lặp có điều kiện |
| Changelog báo lỗi checksum | Đã sửa nội dung changeset từng chạy | Tạo changeset mới; nếu chủ đích cập nhật định nghĩa thì đánh giá `runOnChange` |
| SQL chạy nhưng không cập nhật hàng nào | Bảng/hàng mục tiêu thiếu, `WHERE` sai hoặc dùng schema khác | Thêm kiểm tra tiền đề, xác minh schema và dữ liệu |
| Giá trị thời gian không đổi như mong đợi | Transaction timestamp, độ chính xác hiển thị hoặc changeset không được chọn | Xem log, lịch sử và thời điểm thực thi thực tế |
| Chạy nhiều lần hơn một deploy | Nhiều replica, nhiều pipeline job hoặc retry | Tập trung job migration, giám sát số lần gọi `update` |
| Deploy chậm hoặc bị lock | SQL lặp tốn thời gian, giữ transaction lâu | Đo thời gian/lock, tối ưu SQL, cân nhắc không dùng `runAlways` |
| Rollback không khôi phục dữ liệu trước đó | Không có giá trị cũ hoặc rollback không tương ứng | Thiết kế bù, backup và kiểm thử khôi phục trước khi deploy |

Không “chữa” các lỗi lặp bằng cách xóa lịch sử trong `DATABASECHANGELOG`, đổi ID tùy tiện, hay vô hiệu hóa checksum. Những hành động ấy có thể làm Liquibase hiểu sai về các migration đã áp dụng.

## 12. Quy tắc lựa chọn `runAlways`

Trước khi khai báo `runAlways: true`, trả lời lần lượt:

1. **Có cần chạy lại ở mỗi lần Liquibase update không?** Nếu chỉ cần khi SQL thay đổi, cân nhắc `runOnChange`. Nếu chỉ cần tạo/đổi schema một lần, dùng changeset mặc định.
2. **Thao tác có an toàn khi chạy hai, ba hoặc nhiều lần không?** Kiểm tra cả dữ liệu, constraint, concurrency và tác dụng phụ bên ngoài.
3. **Một lần update thất bại rồi retry có an toàn không?** Cân nhắc transaction, DBMS, trạng thái giữa chừng và audit.
4. **Có khả năng nhiều tiến trình cùng khởi chạy Liquibase không?** Kiểm tra Spring Boot multi-replica và pipeline song song.
5. **Changeset có cần thay đổi nội dung về sau không?** Ưu tiên changeset mới; nếu có lý do giữ cùng changeset, xem xét `runOnChange` có kiểm soát.
6. **Có cần rollback đúng dữ liệu cũ không?** Nếu có, phải lưu dữ liệu cần khôi phục hoặc xây dựng cơ chế bù phù hợp.
7. **Đã có bằng chứng kiểm thử trên đúng DBMS và môi trường tương tự production chưa?** Không chỉ kiểm tra YAML hợp lệ mà còn kiểm tra SQL, quyền và lock.

`runAlways` là công cụ hữu ích khi mục tiêu thực sự là lặp một thay đổi ở mỗi lượt triển khai Liquibase. Sử dụng đúng đòi hỏi hiểu rõ danh tính changeset, checksum, lịch sử trong `DATABASECHANGELOG`, precondition, transaction và tác động khi CI/CD hoặc Spring Boot gọi `update` nhiều lần. Khi một hành vi chỉ nên xảy ra một lần hoặc theo lịch nghiệp vụ, hãy chọn cơ chế phù hợp thay vì bật `runAlways` theo thói quen.

