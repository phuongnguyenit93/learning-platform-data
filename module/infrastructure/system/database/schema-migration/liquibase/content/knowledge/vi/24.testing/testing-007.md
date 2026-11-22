# Kiểm thử chạy lại, runOnChange và runAlways

## 1. Vì sao phải kiểm thử hành vi chạy lại?

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, người học nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một changeset thông thường được thiết kế để chạy một lần trên một database. Tuy nhiên, một số đối tượng cần được cập nhật lại khi định nghĩa thay đổi; một số thao tác vận hành cần được thực thi trong mỗi lần Liquibase chạy update. Liquibase cung cấp hai thuộc tính riêng cho hai nhu cầu đó: `runOnChange` và `runAlways`.

Dùng sai hai thuộc tính này có thể tạo tác dụng phụ lặp lại. Một changeset nạp dữ liệu có thể tạo bản ghi trùng; một câu lệnh cộng dồn có thể tăng số dư nhiều lần; một migration chạy mỗi lần Spring Boot khởi động có thể cập nhật hàng loạt dữ liệu hoặc tạo tải không cần thiết. Ngược lại, nếu không kiểm thử đúng hành vi chạy lại, nhóm có thể sửa định nghĩa view hoặc procedure nhưng database vẫn giữ định nghĩa cũ.

Bài học tập trung vào cách kiểm thử có chủ đích:

- Changeset mặc định chạy một lần và được ghi nhận trong lịch sử.
- `runOnChange` chạy lại khi nội dung changeset thay đổi theo cơ chế checksum của Liquibase.
- `runAlways` chạy lại mỗi lần operation `update` phù hợp được thực hiện, kể cả khi nội dung không đổi.
- Khi kết hợp hai thuộc tính, changeset có thể vừa chạy mỗi lần update vừa chấp nhận thay đổi nội dung theo cơ chế runOnChange.
- Cả hai thuộc tính vẫn chịu ảnh hưởng của changelog root, định danh, filter, precondition, database target và lỗi thực thi.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt changeset một lần, `runOnChange` và `runAlways`.
2. Giải thích checksum quyết định việc chạy lại như thế nào.
3. Chọn đúng loại changeset cho view, stored procedure, cấu hình hoặc thao tác lặp.
4. Thiết kế test chứng minh lần đầu, lần chạy không đổi, lần nội dung thay đổi và lần update lặp.
5. Đánh giá idempotency, transaction, concurrency và side effect của thao tác chạy lại.
6. Kiểm tra lịch sử trong `DATABASECHANGELOG` và kết quả thực tế trên database.
7. Phát hiện rủi ro khi Spring Boot có nhiều replica hoặc nhiều pipeline cùng gọi Liquibase.
8. Đưa kiểm thử chạy lại vào CI/CD và quản lý thay đổi qua nhiều môi trường.

**Nguyên tắc:** Chỉ bật chế độ chạy lại khi đã xác định rõ sự kiện nào làm changeset chạy lại, tác dụng phụ nào được phép lặp và bằng chứng nào chứng minh hành vi đó đúng.

## 2. Hành vi mặc định của changeset

Một changeset Liquibase thường được nhận diện bằng `id`, `author` và đường dẫn changelog logic. Khi thực thi thành công, Liquibase ghi lịch sử vào `DATABASECHANGELOG`. Ở lần `update` tiếp theo, changeset đã được ghi nhận với định danh tương ứng thường không chạy lại.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 100-create-customer-table
      author: customer-team
      changes:
        - createTable:
            schemaName: app
            tableName: customers
            columns:
              - column:
                  name: customer_id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: varchar(160)
```

Hành vi thông thường:

1. Lần update đầu tiên: Liquibase thấy changeset chưa có trong lịch sử và thực thi.
2. Lần update tiếp theo với cùng changelog và database: changeset đã được ghi nhận nên không thực thi lại.
3. Nếu nội dung changeset đã chạy bị sửa: Liquibase kiểm tra checksum và có thể báo lỗi validation thay vì tự coi đó là migration mới.

Cơ chế mặc định bảo vệ lịch sử migration: thay đổi schema đã triển khai được giữ nguyên trong lịch sử; thay đổi tiếp theo nên được thể hiện bằng changeset mới.

### 2.1. Vì sao không nên xem mọi changeset như script khởi tạo có thể chạy lại?

SQL có thể có tác dụng khác nhau khi chạy lần thứ hai:

- `CREATE TABLE` có thể lỗi vì bảng đã tồn tại.
- `INSERT` có thể tạo bản ghi trùng hoặc vi phạm unique constraint.
- `UPDATE balance = balance + amount` có thể cộng tiền nhiều lần.
- `ALTER TABLE ADD COLUMN` có thể lỗi vì cột đã tồn tại.
- `CREATE OR REPLACE VIEW` có thể thay định nghĩa view theo nội dung mới.
- `GRANT` có thể được lặp an toàn trong một số DBMS, nhưng quyền thực tế vẫn cần kiểm tra.

Một thay đổi có thể chạy lặp về mặt cú pháp nhưng không an toàn về mặt nghiệp vụ. Vì vậy cần phân biệt **chạy lại được**, **không gây tác dụng phụ ngoài dự kiến** và **khôi phục được trạng thái cũ**. Ba khái niệm này không đồng nghĩa.

## 3. Phân biệt runOnChange và runAlways

| Tiêu chí | Mặc định | `runOnChange: true` | `runAlways: true` |
|---|---|---|---|
| Lần đầu chưa có trong history | Chạy | Chạy | Chạy |
| Update sau, nội dung không đổi | Không chạy lại | Không chạy lại | Chạy lại |
| Nội dung changeset thay đổi | Checksum validation có thể thất bại | Chạy lại nếu checksum thay đổi theo quy tắc Liquibase | Cần kết hợp runOnChange để chấp nhận thay đổi nội dung đã triển khai |
| Mục đích chính | Migration một lần | Đồng bộ định nghĩa thay đổi theo nội dung | Thực thi một thao tác ở mỗi lần update |
| Rủi ro chính | Sửa nhầm changeset cũ | Tác dụng phụ khi định nghĩa thay đổi | Tác dụng phụ lặp ở mọi lần update |

### 3.1. runOnChange

`runOnChange: true` yêu cầu Liquibase chạy lại changeset khi checksum của nội dung changeset thay đổi theo cơ chế của Liquibase. Khi nội dung không đổi, changeset không được chạy lại chỉ vì có một lệnh update mới.

Nó thường phù hợp với định nghĩa có thể thay thế, chẳng hạn:

- View.
- Stored procedure.
- Function.
- Một số đối tượng SQL mà nội dung mới đại diện cho định nghĩa hoàn chỉnh cần cài đặt lại.

Thay đổi chỉ về khoảng trắng hoặc comment thường không làm changeset chạy lại vì Liquibase không xem chúng là thay đổi checksum có ý nghĩa trong cơ chế này. Hãy kiểm tra hành vi trên phiên bản và loại change cụ thể của dự án.

### 3.2. runAlways

`runAlways: true` yêu cầu Liquibase thực thi changeset trong mỗi lần `update` phù hợp, kể cả khi nội dung không đổi và changeset đã có trong lịch sử.

Nó có thể phù hợp với thao tác cần được áp dụng lại mỗi lần release database, ví dụ bảo đảm một quyền truy cập hoặc một trạng thái cấu hình luôn được đặt về giá trị mong muốn. Tuy nhiên, thao tác phải được thiết kế để chạy lặp an toàn.

`runAlways` không có nghĩa chạy liên tục theo thời gian. Nó chạy khi có một operation Liquibase phù hợp, chẳng hạn CLI `update` hoặc ứng dụng Spring Boot khởi tạo Liquibase và gọi update. Một lần khởi động ứng dụng mới có thể là một lần update mới.

### 3.3. Kết hợp hai thuộc tính

Nếu changeset vừa có `runAlways: true` vừa có `runOnChange: true`:

- Nó được thực thi trong mỗi lần update phù hợp.
- Thay đổi nội dung đã triển khai được xử lý theo cơ chế runOnChange thay vì chỉ gây checksum validation error.
- Mỗi lần chạy vẫn cần thỏa điều kiện nạp changelog, filter, precondition và kết nối database.

Chỉ kết hợp khi thực sự cần cả hai hành vi. Không bật cả hai theo thói quen hoặc để né một lỗi checksum chưa được điều tra.

## 4. Checksum và điều kiện chạy lại

Liquibase tính checksum cho changeset và lưu giá trị tương ứng trong `DATABASECHANGELOG`. Ở lần chạy sau, checksum giúp phát hiện nội dung đã thay đổi so với nội dung được ghi nhận.

Với changeset mặc định, nội dung thay đổi có thể làm validation thất bại. Với `runOnChange`, thay đổi checksum là tín hiệu để chạy lại changeset. Với `runAlways`, changeset được chạy lại mỗi lần update; nếu nội dung của changeset runAlways đã triển khai cần được sửa, cấu hình runOnChange cũng cần được xem xét để Liquibase chấp nhận thay đổi checksum.

### 4.1. Không phải mọi chỉnh sửa file đều kích hoạt runOnChange

Những chỉnh sửa thường không làm Liquibase xem changeset thay đổi về mặt checksum gồm khoảng trắng hoặc comment. Do đó, không dùng thay đổi format để kiểm tra runOnChange.

Một test đúng phải thay đổi nội dung có ý nghĩa, ví dụ:

- Thay biểu thức SELECT của view.
- Thay logic trong procedure/function.
- Thay một định nghĩa SQL được tham chiếu bởi changeset.
- Thay nội dung change type thực sự tham gia checksum.

### 4.2. Checksum không phải hash của toàn bộ trạng thái database

Checksum phản ánh nội dung changeset theo thuật toán/version Liquibase. Nó không chứng minh object database hiện tại đúng với định nghĩa đó, không phát hiện mọi chỉnh sửa thủ công trên database và không xác nhận dữ liệu nghiệp vụ đã đạt.

Vì vậy, kiểm thử phải quan sát cả:

1. Lịch sử changeset và checksum.
2. SQL/DDL thực tế đã thực thi.
3. Object hoặc dữ liệu sau khi chạy.
4. Hành vi ứng dụng sử dụng object đó.

### 4.3. Định danh phải ổn định

`runOnChange` và `runAlways` không thay thế định danh changeset. Giữ ổn định `id`, `author` và filename logic. Nếu đổi tên/di chuyển changelog hoặc thay `logicalFilePath`, Liquibase có thể xem nó là định danh khác và đánh giá như một changeset mới.

Không tạo một file mới với ID/author giống file cũ để ép chạy lại. Hãy quản lý một changeset có định danh ổn định và test thay đổi nội dung trên database thử nghiệm.

## 5. Chọn đúng loại thay đổi

| Loại thay đổi | Cách thường phù hợp | Lý do |
|---|---|---|
| Tạo bảng, thêm cột, thêm FK | Changeset mặc định | Migration cấu trúc một lần |
| Backfill dữ liệu lịch sử | Changeset mặc định hoặc job riêng | Cần kiểm soát phạm vi, tiến độ và lịch sử |
| Cập nhật định nghĩa view | `runOnChange` | Nội dung view là định nghĩa cần thay thế |
| Cập nhật procedure/function | `runOnChange` | Cần cài đặt lại khi logic thay đổi |
| Bảo đảm một thao tác lặp mỗi lần update | `runAlways` | Có yêu cầu thực thi theo từng update |
| Vừa luôn thực thi vừa cho phép sửa nội dung | Cân nhắc cả hai | Chỉ khi hai yêu cầu đều thực sự cần |
| Tạo dữ liệu mẫu một lần | Changeset mặc định | Tránh nạp trùng |
| Gửi email/call API/tạo message | Thường không đặt trong runAlways | Side effect ngoài database khó kiểm soát và dễ lặp |

Quyết định phải dựa trên semantics của thay đổi. Không chọn thuộc tính chỉ vì muốn lệnh update “tự xử lý mọi thứ”.

## 6. Kiểm thử runOnChange với view

Một ví dụ phù hợp là view tổng hợp thông tin khách hàng. Khi định nghĩa view thay đổi, database cần thay thế định nghĩa cũ.

### 6.1. Changeset

```yaml
databaseChangeLog:
  - changeSet:
      id: 200-refresh-customer-summary
      author: customer-team
      runOnChange: true
      changes:
        - createView:
            schemaName: app
            viewName: v_customer_summary
            replaceIfExists: true
            selectQuery: >
              SELECT customer_id, display_name
              FROM app.customers
```

`replaceIfExists` và khả năng thay thế view phụ thuộc DBMS, change type và phiên bản Liquibase. Nếu DBMS không hỗ trợ cách thay thế được sinh ra, cần dùng SQL phù hợp và test trên đúng engine.

### 6.2. Kịch bản test lần đầu

1. Tạo database/schema thử nghiệm sạch.
2. Chuẩn bị bảng `app.customers` và dữ liệu mẫu.
3. Chạy `validate`.
4. Chạy `update-sql`, kiểm tra SQL tạo view.
5. Chạy `update`.
6. Truy vấn `app.v_customer_summary`, xác nhận cột và dữ liệu đúng.
7. Kiểm tra changeset đã được ghi trong `DATABASECHANGELOG`.

Kết quả mong đợi: view được tạo và changeset được ghi nhận là đã thực thi.

### 6.3. Kịch bản test update không đổi

1. Không sửa nội dung changeset.
2. Chạy `status` và `update-sql`.
3. Chạy `update` lần thứ hai.
4. Xác nhận view không bị thay thế lại chỉ vì update được gọi lần nữa.
5. Xác nhận kết quả truy vấn vẫn đúng.

Kết quả mong đợi: `runOnChange` không làm changeset chạy mỗi lần update khi checksum không đổi.

### 6.4. Kịch bản test nội dung thay đổi

Trong một changelog test riêng hoặc database dùng riêng, sửa định nghĩa view có ý nghĩa, ví dụ bổ sung `created_at` vào projection. Sau đó:

1. Giữ nguyên ID, author và logical filename.
2. Xác nhận chỉ nội dung định nghĩa thay đổi.
3. Chạy `validate` và `update-sql`.
4. Xác nhận Liquibase nhận ra changeset cần chạy lại.
5. Chạy `update`.
6. Kiểm tra view đã có định nghĩa mới và trả kết quả mong đợi.
7. Kiểm tra lịch sử/checksum và loại thực thi được ghi nhận.

Không sửa changeset đã triển khai ở production chỉ để thử. Thực hiện trên database cô lập và dùng bản changelog thử nghiệm có kiểm soát.

### 6.5. Kịch bản chỉ đổi comment hoặc khoảng trắng

Tạo một lần thử riêng chỉ thay đổi comment hoặc formatting. Quan sát checksum và trạng thái để xác nhận thay đổi đó không được dùng làm tín hiệu cập nhật view. Không dựa vào một lần chạy để suy rộng cho mọi loại change hoặc phiên bản; lưu lại kết quả với phiên bản Liquibase đang kiểm thử.

## 7. Kiểm thử runAlways với thao tác có thể lặp

`runAlways` phù hợp khi mỗi lần update đều cần thực hiện lại một thao tác. Bản thân thuộc tính không làm câu SQL trở nên idempotent.

Ví dụ PostgreSQL minh họa một thay đổi bảo đảm quyền SELECT:

```yaml
databaseChangeLog:
  - changeSet:
      id: 300-ensure-report-reader-grant
      author: platform
      runAlways: true
      dbms: postgresql
      changes:
        - sql:
            sql: GRANT SELECT ON app.orders TO report_reader;
```

Lặp lại GRANT trong PostgreSQL thường không tạo một bản ghi quyền trùng như INSERT; tuy vậy cần xác minh role, object, schema, quyền kế thừa và chính sách bảo mật. Ví dụ này dành cho hệ thống có yêu cầu thực sự kiểm tra/đặt quyền trong mỗi lần update, không phải lời khuyên đưa mọi GRANT vào startup của tất cả replica.

Một ví dụ DML khác trong database thử nghiệm:

```yaml
databaseChangeLog:
  - changeSet:
      id: 301-ensure-feature-enabled
      author: platform
      runAlways: true
      changes:
        - sql:
            sql: >
              UPDATE app.feature_flags
              SET enabled = TRUE
              WHERE feature_key = 'new-checkout'
                AND enabled = FALSE;
```

Câu lệnh chỉ đổi các hàng đang false sang true. Khi đã true, lần chạy sau không cập nhật lại hàng đó. Cần có khóa/unique constraint bảo đảm mỗi feature key chỉ có một hàng; nếu nghiệp vụ muốn có thể tắt feature, thao tác runAlways này sẽ bật lại nó ở lần update tiếp theo. Điều đó phải là chủ đích được phê duyệt.

### 7.1. Kịch bản test runAlways

Dùng database/schema cô lập và chọn một thay đổi có thể quan sát số lần thực thi, ví dụ một bảng audit thử nghiệm:

1. Chạy update lần đầu, xác nhận thao tác được thực hiện.
2. Không thêm changeset mới và không sửa changelog.
3. Chạy update lần hai, xác nhận changeset được thực thi lại.
4. Chạy update lần ba, xác nhận hành vi tiếp tục lặp.
5. Kiểm tra dữ liệu sau mỗi lần và đánh giá side effect.
6. Chạy với precondition/filter không phù hợp để xác nhận changeset vẫn tuân theo điều kiện chọn/chạy.

Nếu dùng bộ đếm để chứng minh số lần chạy, chỉ dùng trong database thử nghiệm. Một câu `counter = counter + 1` cố ý không idempotent; nó giúp quan sát số lần chạy nhưng không phải mẫu production an toàn.

### 7.2. Kiểm thử thao tác lặp an toàn

Với mỗi changeset runAlways, cần test:

- Chạy lần đầu.
- Chạy lại không đổi cấu hình.
- Chạy khi dữ liệu đã ở trạng thái mong muốn.
- Chạy khi object hoặc role không tồn tại.
- Chạy khi quyền thiếu.
- Chạy sau khi có thay đổi nghiệp vụ hợp lệ.
- Chạy đồng thời từ nhiều Liquibase process.
- Chạy khi một lần trước thất bại giữa chừng.

Một câu lệnh lặp an toàn phải có điều kiện, constraint và transaction phù hợp; không chỉ dựa vào hy vọng rằng database sẽ bỏ qua lỗi trùng.

## 8. Idempotency, atomicity và side effect

### 8.1. Idempotency

Một operation idempotent khi thực hiện nhiều lần tạo ra cùng trạng thái cuối như thực hiện một lần, với cùng điều kiện đầu vào.

Ví dụ:

```sql
UPDATE app.feature_flags
SET enabled = TRUE
WHERE feature_key = 'new-checkout'
  AND enabled = FALSE;
```

Sau lần đầu, hàng đã true nên lần tiếp theo không đổi nó. Ngược lại:

```sql
UPDATE app.accounts
SET balance = balance + 100
WHERE account_id = 42;
```

mỗi lần chạy làm số dư tăng thêm 100. Đặt câu thứ hai trong changeset runAlways có thể gây lỗi nghiệp vụ nghiêm trọng.

Idempotency phải được đánh giá cả ở cấp DBMS trigger, audit, CDC và event. Một UPDATE không đổi giá trị có thể vẫn kích hoạt trigger hoặc ghi log tùy hệ thống.

### 8.2. Atomicity và transaction

Nếu changeset gồm nhiều lệnh, cần xác định chúng có được thực thi trong cùng transaction hay không. DBMS và loại DDL có thể có quy tắc transaction khác nhau. `runInTransaction` điều khiển một phần hành vi của Liquibase nhưng không biến mọi lệnh DBMS thành transactional.

Khi operation chạy lại thất bại giữa chừng, kiểm tra:

- Câu lệnh nào đã commit?
- History đã được cập nhật chưa?
- Có object/dữ liệu được tạo một phần không?
- Retry có thể chạy an toàn từ trạng thái hiện tại không?
- Có cần precondition, repair hoặc forward-fix?

Không coi lần chạy lại là một transaction có thể tự đảo ngược trong mọi DBMS.

### 8.3. Side effect ngoài database

Không đặt gửi email, gọi HTTP, publish message hoặc thao tác file trong changeset runAlways nếu không có cơ chế idempotency và deduplication riêng. Mỗi lần ứng dụng khởi động hoặc pipeline chạy update có thể lặp side effect.

Nếu cần phát sự kiện sau migration, dùng một bước triển khai riêng có event key, outbox hoặc cơ chế xác nhận đã xử lý. Liquibase quản lý schema/history; nó không tự cung cấp exactly-once delivery cho hệ thống bên ngoài.

## 9. Tác động khi chạy qua Spring Boot nhiều replica

Spring Boot có thể tự khởi tạo Liquibase và gọi update trong startup. Nếu một ứng dụng có nhiều replica và changeset được đặt `runAlways: true`, mỗi lần một replica khởi động và thực hiện Liquibase update đều có thể kích hoạt changeset đó.

Liquibase lock giúp tuần tự hóa các operation dùng cùng lock table. Lock không biến runAlways thành “một lần cho cả deployment”. Nếu bốn replica lần lượt khởi động và mỗi replica gọi update, changeset runAlways có thể được thực thi nhiều lần theo các lần update đó.

### 9.1. Mô hình nên cân nhắc

- Với migration cấu trúc một lần, có thể dùng một migration job riêng hoặc cơ chế startup được kiểm soát.
- Với runAlways, ưu tiên một tiến trình migration owner rõ ràng nếu thao tác có side effect đáng kể.
- Nếu app replicas vẫn tự chạy update, chứng minh thao tác runAlways an toàn khi lặp theo số lần startup.
- Không dựa vào lock để chống lặp nghiệp vụ.
- Ghi nhận số lần update và changeset thực thi để phát hiện tần suất ngoài dự kiến.

### 9.2. Test nhiều instance

Trên môi trường kiểm thử:

1. Khởi động hai instance cùng trỏ tới một database test.
2. Bảo đảm chúng dùng cùng changelog và lock table.
3. Quan sát thứ tự lấy lock và số lần changeset runAlways thực thi.
4. Xác nhận không có SQL cạnh tranh hoặc dữ liệu sai.
5. Khởi động lại một instance và kiểm tra changeset có chạy thêm lần nữa không.
6. Đối chiếu kết quả với mô hình production dự kiến.

Không chạy thử concurrency này trên production. Nếu có nhiều pipeline hoặc công cụ DBA ngoài Spring Boot, phải tính chúng vào mô hình owner.

## 10. Preconditions, context, label và DBMS vẫn có hiệu lực

`runOnChange` và `runAlways` không bỏ qua những điều kiện khác của changeset.

Một changeset có thể không chạy vì:

- Không được nạp từ root changelog.
- Đã được history nhận diện và không có điều kiện chạy lại phù hợp.
- Bị context hoặc label filter loại.
- Thuộc tính DBMS không khớp.
- Precondition dừng hoặc bỏ qua theo onFail/onError.
- Liquibase không kết nối được database hoặc gặp lỗi validation.

Ví dụ runAlways có context:

```yaml
- changeSet:
    id: 400-refresh-report-permissions
    author: platform
    context: reporting
    runAlways: true
    changes:
      - sql:
          sql: GRANT SELECT ON app.order_summary TO report_reader;
```

Nếu lần update không chọn context reporting, không được giả định runAlways sẽ buộc changeset chạy. Kiểm thử phải dùng cùng filter và cấu hình với môi trường đích.

### 10.1. Precondition cần được kiểm thử ở nhiều trạng thái

- Điều kiện đạt: changeset thực thi theo chế độ runOnChange/runAlways.
- Điều kiện fail với HALT: operation dừng theo cấu hình.
- Điều kiện fail với CONTINUE: changeset có thể được xét lại ở lần chạy sau.
- Điều kiện fail với MARK_RAN: lịch sử có thể ghi nhận changeset mà nội dung không chạy.
- Lỗi khi đánh giá precondition: xử lý theo onError.

Đặc biệt với runAlways, không dùng MARK_RAN để che trạng thái không đúng. Nếu thao tác cần chạy mỗi lần update, việc đánh dấu ran khi điều kiện chưa đạt có thể làm mất mục tiêu vận hành.

## 11. Kiểm thử lịch sử trong DATABASECHANGELOG

`DATABASECHANGELOG` giúp xác nhận Liquibase đã ghi nhận lần thực thi. Những trường thường cần xem:

- `ID`, `AUTHOR`, `FILENAME`: định danh changeset.
- `DATEEXECUTED`, `ORDEREXECUTED`: thời điểm và thứ tự ghi nhận.
- `EXECTYPE`: loại thực thi được ghi nhận, ví dụ EXECUTED, RERAN hoặc MARK_RAN.
- `MD5SUM`: checksum theo cơ chế Liquibase.

Ví dụ truy vấn:

```sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
WHERE ID IN (
    '200-refresh-customer-summary',
    '300-ensure-report-reader-grant'
)
ORDER BY DATEEXECUTED, ORDEREXECUTED;
```

Tên bảng/schema và cột cần xác minh với cấu hình thực tế. Một số thay đổi có thể cập nhật bản ghi lịch sử hiện tại thay vì tạo một dòng mới cho mỗi lần chạy; do đó không chỉ đếm số dòng để xác định số lần runAlways đã chạy. Hãy kết hợp log Liquibase, kết quả SQL và một audit marker có kiểm soát trong test.

### 11.1. Không sửa history để tạo test chạy lại

Không xóa dòng `DATABASECHANGELOG`, chỉnh `MD5SUM` hoặc chạy `changelog-sync` để ép một changeset chạy lại. Những thao tác đó thay đổi cách Liquibase diễn giải lịch sử và có thể khiến DDL/DML thực thi lần nữa.

Để test runOnChange, dùng database thử nghiệm và thay đổi nội dung changeset có chủ đích. Để test runAlways, chạy nhiều lần update trên database cô lập và quan sát side effect. Giữ history nguyên vẹn để test phản ánh đúng vận hành.

## 12. Bộ kịch bản kiểm thử đầy đủ

Một test suite tốt nên kiểm tra ít nhất các trường hợp sau:

| ID | Chế độ | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| T01 | Mặc định | Update lần đầu | Chạy và ghi history |
| T02 | Mặc định | Update lần hai, không đổi | Không chạy lại |
| T03 | Mặc định | Sửa nội dung đã chạy | Validation phát hiện checksum mismatch theo cấu hình |
| T04 | runOnChange | Update lần đầu | Chạy |
| T05 | runOnChange | Update lần hai, nội dung không đổi | Không chạy lại |
| T06 | runOnChange | Thay đổi nội dung có ý nghĩa | Chạy lại |
| T07 | runOnChange | Chỉ đổi whitespace/comment | Thường không chạy lại |
| T08 | runAlways | Update lần đầu | Chạy |
| T09 | runAlways | Update lần hai, không đổi | Chạy lại |
| T10 | runAlways | Update lần ba | Tiếp tục chạy lại |
| T11 | Kết hợp | runAlways + runOnChange, nội dung thay đổi | Chạy theo cả hai yêu cầu |
| T12 | Filter | Context/label/DBMS không khớp | Không được chọn |
| T13 | Precondition | Điều kiện fail | Hành vi đúng onFail/onError |
| T14 | Concurrency | Hai instance gọi update | Lock tuần tự hóa; side effect vẫn phải an toàn |
| T15 | Recovery | Một lần chạy thất bại | History/schema được kiểm tra trước retry |

Không nhất thiết tất cả trường hợp phải nằm trong một test class. Có thể chia thành unit test cho cấu hình, integration test với DBMS và test pipeline cho thứ tự release.

## 13. Thiết kế test integration với database cô lập

### 13.1. Mỗi kịch bản cần trạng thái ban đầu xác định

Dùng database hoặc schema riêng cho mỗi kịch bản để tránh kết quả phụ thuộc test trước. Ghi lại:

- DBMS và phiên bản.
- Liquibase version.
- Root changelog và artifact revision.
- Context/label/DBMS filter.
- Schema history ban đầu.
- Dữ liệu fixture.
- Cấu hình precondition.

Test runOnChange cần kiểm soát nội dung ở từng lần chạy. Test runAlways cần gọi update nhiều lần trên cùng history để chứng minh nó thực thi lại.

### 13.2. Test trên DBMS phù hợp

Nếu production dùng PostgreSQL, hãy chạy test trên PostgreSQL phù hợp thay vì chỉ dùng H2. SQL, view replacement, procedure delimiter, transaction và lock có thể khác giữa DBMS.

Với changeset dbms riêng, chạy test cho từng DBMS được hỗ trợ. Đối với SQL file, xác minh file có trong artifact và encoding/path đúng.

### 13.3. Test upgrade path và fresh install

- Fresh install: database rỗng, chạy toàn bộ changelog.
- Upgrade path: database đã có các changeset cũ, chạy phần cập nhật mới.
- Repeated update: chạy update nhiều lần để kiểm tra runAlways và runOnChange.
- App restart: khởi động Spring Boot nhiều lần với cùng database.
- Concurrency: nhiều instance hoặc pipeline cùng yêu cầu update trong môi trường test.

Chỉ test database rỗng không chứng minh behavior chạy lại đúng trên một database đã có history.

## 14. Quan sát kết quả bằng CLI

Các lệnh dưới đây là ví dụ; tham số và cách gọi có thể khác theo phiên bản Liquibase. Hãy dùng cùng URL, changelog, filter và schema như môi trường đang kiểm thử.

### 14.1. Validate changelog

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate
```

Validate giúp kiểm tra cấu trúc changelog và tham chiếu resource theo khả năng phiên bản. Nó không chứng minh SQL runtime hoặc tác dụng phụ chạy lại an toàn.

### 14.2. Xem trạng thái

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="jdbc:postgresql://localhost:5432/liquibase_test" \
  --username=migration_user \
  status --verbose
```

Status giúp xem changeset pending theo cấu hình hiện tại. Với runAlways, cần xem thêm hành vi của lệnh update và log; đừng chỉ suy luận số lần thực thi từ danh sách pending.

### 14.3. Xem SQL dự kiến

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="jdbc:postgresql://localhost:5432/liquibase_test" \
  --username=migration_user \
  update-sql
```

`update-sql` giúp xem SQL dự kiến mà Liquibase sẽ chạy. Với runOnChange, thay đổi nội dung có thể làm SQL xuất hiện lại; với runAlways, changeset được thiết kế chạy mỗi update có thể xuất hiện lại trong kế hoạch. Xác minh bằng output thực tế của phiên bản đang dùng.

### 14.4. Chạy update và hậu kiểm

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="jdbc:postgresql://localhost:5432/liquibase_test" \
  --username=migration_user \
  update
```

Sau mỗi lần update, ghi lại log, kiểm tra object/dữ liệu và đối chiếu history. Không dùng update trên production chỉ để thử một changeset runAlways có side effect chưa được đánh giá.

## 15. Kiểm thử qua Spring Boot

Khi dùng Spring Boot, Liquibase có thể chạy trong startup thông qua bean auto-configured. Điều này tạo một lần gọi update mỗi khi application context khởi tạo theo cấu hình.

### 15.1. Test context khởi động

Một integration test có thể khởi tạo Spring context với database test và xác nhận Liquibase hoàn tất. Kiểm tra:

- `spring.liquibase.enabled` có bật trong test profile cần migration không.
- Root changelog đúng.
- Context/label được truyền như dự kiến.
- Database target là test database.
- Các bean phụ thuộc schema chỉ khởi tạo sau khi migration hoàn tất theo lifecycle của Spring Boot.

### 15.2. Test restart

Để test runAlways, khởi động context, đóng context rồi khởi động lại với cùng database. Changeset runAlways có thể chạy lại trong lần startup thứ hai. Dùng audit marker hoặc SQL effect có thể quan sát để chứng minh.

Với runOnChange, restart mà nội dung không đổi không nên làm changeset chạy lại. Sau đó thay đổi định nghĩa trong test fixture, khởi động context mới và xác minh object được cập nhật.

### 15.3. Nhiều replica

Không mặc định mỗi deployment chỉ gọi Liquibase một lần. Trong production nhiều replica, mỗi context có thể gọi update; lock chỉ tuần tự hóa. Nếu runAlways thay đổi dữ liệu hoặc quyền, cần chứng minh lặp nhiều lần không gây lỗi và cân nhắc chuyển migration sang job riêng.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| runOnChange không chạy sau khi sửa | Chỉ đổi comment/whitespace hoặc checksum không đổi | Thay đổi nội dung có ý nghĩa và xem update-sql |
| runOnChange báo checksum error | Thiếu thuộc tính hoặc identity/config không như dự kiến | Kiểm tra changeset đã chạy, runOnChange và phiên bản |
| runAlways không chạy | Changeset không được nạp/chọn, filter loại hoặc update chưa được gọi | Kiểm tra root changelog, context, label, DBMS và log |
| runAlways chạy nhiều hơn dự kiến | Nhiều app context/replica/pipeline gọi update | Xác định migration owner, xem số lần startup/update |
| runAlways tạo dữ liệu trùng | INSERT không idempotent hoặc thiếu unique constraint | Thiết kế upsert/guard và kiểm tra dữ liệu |
| runAlways làm thay đổi dữ liệu liên tục | DML có side effect ở mọi lần chạy | Chuyển sang changeset một lần hoặc job chuyên trách |
| View không đổi sau runOnChange | SQL file/resource sai, DBMS không hỗ trợ replace như giả định | Kiểm tra artifact, SQL thực thi và định nghĩa view |
| Test lần hai thất bại | Dữ liệu test không được reset hoặc thao tác không idempotent | Cô lập schema và xác định trạng thái trước mỗi test |
| Hai instance gây chờ lock | Cùng chạy Liquibase trên một database | Kiểm tra lock, operation owner và concurrency policy |
| History có RERAN nhưng kết quả sai | Changeset được chạy lại nhưng logic không đúng | Kiểm tra SQL, dữ liệu, transaction và hậu kiểm |

### 16.1. Khi nào tạo changeset mới?

Nếu thay đổi là migration một lần đã triển khai, cách thông thường là tạo changeset mới. Không biến một changeset DML cũ thành runOnChange chỉ để sửa logic đã chạy. Với view/procedure được thiết kế là định nghĩa có thể thay thế, runOnChange có thể phù hợp từ đầu và được kiểm thử qua các lần thay nội dung.

Nếu cần thay đổi thuộc tính runAlways hoặc runOnChange của changeset đã chạy, phải kiểm tra behavior/version và thử trên bản sao database đại diện trước khi triển khai.

## 17. Rollback và phục hồi cho changeset chạy lại

Rollback của runOnChange hoặc runAlways cần được đánh giá theo nội dung thực thi thực tế.

- Với view/procedure, rollback có thể khôi phục định nghĩa trước nếu đã lưu và test.
- Với thao tác GRANT, rollback có thể là REVOKE nhưng phải cân nhắc quyền được cấp bởi một hệ thống khác.
- Với DML cập nhật trạng thái, rollback cần biết giá trị trước và phân biệt thay đổi do migration với thay đổi nghiệp vụ sau đó.
- Với side effect ngoài database, rollback SQL không tự thu hồi email/message/API đã gửi.

Một changeset runAlways được chạy nhiều lần không có nghĩa rollback sẽ được gọi tương ứng nhiều lần. Hãy xem rollback như một operation độc lập, xác định trạng thái hiện tại và dữ liệu có thể đã thay đổi kể từ lần chạy trước.

Không dùng release-locks, clear-checksums hoặc xóa history để phục hồi một changeset chạy lặp. Những lệnh đó không hoàn tác side effect.

## 18. CI/CD: quality gate cho hành vi chạy lại

Một pipeline kiểm thử runOnChange/runAlways nên có các bước:

1. Build artifact chứa changelog và SQL resource.
2. Validate changelog.
3. Chạy integration test trên DBMS phù hợp.
4. Test update lần đầu và update lặp không đổi.
5. Với runOnChange, thay đổi nội dung có ý nghĩa trong fixture và xác nhận rerun.
6. Với runAlways, chạy update nhiều lần và xác nhận side effect mong muốn.
7. Test filter/precondition và trường hợp lỗi.
8. Review update-sql và history.
9. Chạy migration job có ownership rõ ràng.
10. Hậu kiểm schema/dữ liệu trước khi rollout ứng dụng.

### 18.1. Artifact phải nhất quán

Changelog và SQL file phải đến từ cùng commit/artifact. Nếu CI kiểm thử source tree nhưng production chạy JAR thiếu SQL resource, hành vi có thể khác. Kiểm tra resource path, encoding, checksum và Liquibase version.

### 18.2. Không dùng test để xóa history production

Các test cần database cô lập hoặc schema riêng. Không chạy clear-checksums, xóa dòng DATABASECHANGELOG hoặc changelog-sync trên production chỉ để tạo lại điều kiện test.

### 18.3. Ghi nhận bằng chứng

Lưu:

- DBMS/version và Liquibase version.
- Artifact/changelog revision.
- Filter/context/label.
- Số lần gọi update.
- Changeset ID/author/filename.
- EXECTYPE/checksum phù hợp.
- Log thực thi và kết quả hậu kiểm.
- Số lần side effect quan sát được.
- Kết quả concurrency/restart nếu có.

## 19. Bài thực hành: kiểm thử ba chế độ chạy lại

**Bối cảnh:** Nhóm quản lý view báo cáo khách hàng và một thao tác bảo đảm quyền đọc cho role báo cáo. Cần chứng minh một view cập nhật theo nội dung, một thao tác quyền chạy lại mỗi lần update và migration tạo bảng chỉ chạy một lần.

### 19.1. Chuẩn bị

Tạo database test riêng với bảng `app.customers`, role thử nghiệm và changelog gồm:

- Changeset mặc định tạo bảng fixture.
- Changeset view có `runOnChange: true`.
- Changeset GRANT có `runAlways: true`, giới hạn DBMS phù hợp.

Không dùng role hoặc database production. Ghi lại Liquibase version và DBMS version.

### 19.2. Thực hiện

1. Chạy update lần đầu; xác nhận cả ba changeset thực thi.
2. Chạy update lần hai không đổi; changeset mặc định không chạy lại, view runOnChange không chạy lại, GRANT runAlways chạy lại.
3. Sửa SELECT của view trong changelog test, giữ identity; chạy update và xác nhận view đổi.
4. Chỉ sửa comment/whitespace trong một thử nghiệm riêng; xác nhận không dựa vào thay đổi format để kích hoạt runOnChange.
5. Chạy update thêm lần nữa; GRANT vẫn được áp dụng, view không chạy lại nếu checksum không đổi.
6. Khởi động hai Spring context lần lượt cùng database test; quan sát runAlways được gọi theo mỗi lần update.
7. Kiểm tra history, định nghĩa view, quyền role và dữ liệu fixture.

### 19.3. Tiêu chí đạt

- Changeset mặc định chạy một lần và không bị chạy lại.
- runOnChange không chạy lại khi nội dung không đổi, nhưng chạy lại khi định nghĩa có thay đổi ý nghĩa.
- runAlways chạy lại trong mỗi lần update phù hợp.
- Filter và precondition vẫn điều khiển việc chọn/chạy.
- Không có dữ liệu trùng, side effect ngoài ý muốn hoặc lock cạnh tranh.
- History và kết quả database khớp với bằng chứng test.

## 20. Checklist trước khi đưa changeset chạy lại vào release

### Thiết kế

- [ ] Đã xác định changeset cần mặc định, runOnChange hay runAlways.
- [ ] ID, author và logical filename ổn định.
- [ ] runOnChange dùng cho định nghĩa có thể thay thế, không dùng tùy tiện cho DML.
- [ ] runAlways có lý do vận hành rõ ràng và tần suất update đã biết.
- [ ] Nếu nội dung runAlways có thể thay đổi, đã đánh giá kết hợp runOnChange.
- [ ] Không đặt side effect ngoài database vào changeset lặp nếu thiếu idempotency/deduplication.

### Kiểm thử

- [ ] Test lần đầu trên database sạch.
- [ ] Test update lần hai khi nội dung không đổi.
- [ ] Test thay đổi nội dung có ý nghĩa cho runOnChange.
- [ ] Test comment/whitespace riêng.
- [ ] Test nhiều lần update cho runAlways.
- [ ] Test precondition, context, label và DBMS filter.
- [ ] Test failure/retry và transaction.
- [ ] Test restart/nhiều replica nếu Spring Boot auto-run.
- [ ] Test trên DBMS/version phù hợp production.

### Vận hành

- [ ] Migration owner và concurrency policy rõ ràng.
- [ ] SQL preview và log được review.
- [ ] Database target và artifact đúng.
- [ ] History/checksum được hậu kiểm.
- [ ] Có metric để phát hiện số lần chạy ngoài dự kiến.
- [ ] Có kế hoạch rollback/forward-fix.
- [ ] Không thao tác history production để giả lập test.

## 21. Câu hỏi tự kiểm tra

1. Changeset mặc định được xử lý thế nào ở lần update thứ hai?
2. runOnChange khác runAlways ở điều kiện kích hoạt nào?
3. Vì sao thay đổi comment/whitespace thường không kích hoạt runOnChange?
4. Những loại object nào thường phù hợp với runOnChange?
5. Vì sao runAlways cần thao tác idempotent?
6. Điều gì có thể xảy ra nếu runAlways chứa balance = balance + amount?
7. Khi nào nên kết hợp runAlways và runOnChange?
8. Vì sao lock Liquibase không ngăn runAlways thực thi ở mỗi lần update của replica?
9. Context, label và precondition có bị runAlways bỏ qua không?
10. Vì sao không nên xóa dòng DATABASECHANGELOG để test chạy lại?
11. Cần quan sát gì ngoài EXECTYPE/checksum để chứng minh view đã đổi?
12. Khi nào tạo changeset mới an toàn hơn sửa changeset cũ?
13. Vì sao test database rỗng chưa đủ cho hành vi restart?
14. Side effect ngoài database cần cơ chế gì để tránh lặp?

## 22. Nguyên tắc ghi nhớ

- Changeset mặc định là migration một lần; history ngăn nó chạy lại trong update thông thường.
- runOnChange chạy lại khi nội dung changeset thay đổi theo checksum; nội dung không đổi thì không chạy mỗi lần update.
- Thay đổi chỉ về comment/whitespace thường không kích hoạt runOnChange.
- runAlways chạy lại trong mỗi lần update phù hợp, kể cả khi nội dung không đổi.
- Nếu cần vừa chạy mỗi lần vừa chấp nhận thay đổi nội dung đã triển khai, cân nhắc cả hai thuộc tính và test trên đúng version.
- runOnChange thường phù hợp với view/procedure/function; runAlways cần lý do vận hành và thao tác an toàn khi lặp.
- Idempotency phải được đánh giá ở cả SQL, trigger, audit, CDC và side effect.
- Lock tuần tự hóa Liquibase operation nhưng không biến runAlways thành một lần cho cả deployment.
- Spring Boot nhiều replica có thể tạo nhiều lần gọi update; cân nhắc migration job riêng.
- Filter và precondition vẫn có hiệu lực với changeset chạy lại.
- Checksum không chứng minh trạng thái object/data thực tế đúng.
- Kiểm thử lần đầu, lần lặp không đổi, lần nội dung thay đổi, failure, retry và concurrency.
- Không sửa history hoặc dùng clear-checksums/changelog-sync để ép chạy lại.
- Với migration một lần đã triển khai, tạo changeset mới thường an toàn hơn sửa nội dung cũ.

**Kết luận:** runOnChange và runAlways giải quyết hai nhu cầu khác nhau. runOnChange đồng bộ lại định nghĩa khi nội dung thay đổi; runAlways thực thi một thao tác ở mỗi lần update phù hợp. Kiểm thử phải chứng minh cả điều kiện kích hoạt lẫn kết quả database, side effect, history và hành vi khi Spring Boot khởi động nhiều lần. Chọn đúng chế độ, giữ định danh ổn định và kiểm tra tính an toàn khi lặp giúp Liquibase duy trì lịch sử migration có thể truy vết mà vẫn hỗ trợ các đối tượng cần được cập nhật thường xuyên.

