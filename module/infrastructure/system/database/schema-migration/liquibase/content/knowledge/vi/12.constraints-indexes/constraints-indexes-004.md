# Ràng buộc duy nhất và dữ liệu trùng lặp trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một trong những thay đổi schema cần thận trọng nhất là thêm ràng buộc **UNIQUE** vào bảng đã có dữ liệu: câu lệnh có thể thất bại vì các giá trị trùng, hoặc tạo ra một quy tắc duy nhất không đúng với nghiệp vụ.

Bài học thuộc phần **Khóa và chỉ mục**, tập trung vào cách hiểu tính duy nhất, nhận diện và xử lý bản ghi trùng, biểu diễn ràng buộc trong Liquibase, cũng như triển khai an toàn khi ứng dụng vẫn đang ghi dữ liệu. Các ví dụ chính sử dụng changelog YAML và PostgreSQL; những khác biệt giữa các DBMS được chỉ rõ để không áp dụng máy móc.

## 1. Tính duy nhất thực sự bảo vệ điều gì?

Ràng buộc duy nhất (*unique constraint*) yêu cầu database không chấp nhận hai hàng có cùng tổ hợp giá trị khóa theo quy tắc so sánh của DBMS. Nó giúp bảo vệ một **bất biến dữ liệu** ngay cả khi nhiều instance ứng dụng, job nhập liệu hoặc script chạy đồng thời.

Ví dụ hệ thống nhiều khách hàng tổ chức (*multi-tenant*) lưu thành viên ở bảng `app_member`:

| id | tenant_id | email | deleted_at |
|---:|---:|---|---|
| 101 | 10 | `an@example.com` | `NULL` |
| 102 | 10 | `binh@example.com` | `NULL` |
| 103 | 11 | `an@example.com` | `NULL` |

Nếu nghiệp vụ yêu cầu email chỉ duy nhất **trong từng tenant**, thì tổ hợp `(tenant_id, email)` phải duy nhất; hai tenant khác nhau vẫn được phép có cùng email. Ngược lại, đặt `UNIQUE(email)` sẽ áp dụng quy tắc duy nhất cho toàn bảng và có thể chặn một tình huống hợp lệ.

Cần phân biệt:

| Cơ chế | Vai trò chính | Điều cần lưu ý |
|---|---|---|
| **Primary key** | Định danh hàng; kết hợp tính duy nhất với không `NULL` | Một bảng thường có một khóa chính, có thể gồm nhiều cột |
| **Unique constraint** | Ngăn trùng một cột hoặc tổ hợp cột | Hành vi với `NULL`, collation và kiểu dữ liệu tùy DBMS |
| **Unique index** | Cũng có thể cưỡng chế tính duy nhất và hỗ trợ truy vấn | Không đồng nhất hoàn toàn với unique constraint trong mọi DBMS; hỗ trợ biểu thức/index có điều kiện tùy hệ |
| **Kiểm tra tại ứng dụng** | Phản hồi sớm, hiển thị thông báo nghiệp vụ | Không loại trừ race condition giữa hai request nếu thiếu cưỡng chế tại DB |
| **Precondition Liquibase** | Kiểm tra trạng thái trước khi chạy một changeset | Không thay cho unique constraint; không loại trừ dữ liệu mới chèn vào giữa lần kiểm tra và DDL |

**Quy tắc thiết kế:** dùng kiểm tra tại ứng dụng để có trải nghiệm tốt, nhưng dùng cơ chế duy nhất của database cho bất biến phải được bảo đảm trong điều kiện có nhiều tác nhân ghi đồng thời.

## 2. Định nghĩa chính xác thế nào là “trùng”

Không phải mọi bản ghi trông giống nhau đều bị database coi là trùng, và không phải mọi bản ghi khác nhau về mặt ký tự đều khác nhau về nghiệp vụ.

### 2.1. Duy nhất toàn bảng hay theo phạm vi?

- `UNIQUE(email)`: mỗi email chỉ xuất hiện một lần trong toàn bảng theo quy tắc so sánh của DBMS.
- `UNIQUE(tenant_id, email)`: mỗi cặp tenant và email chỉ xuất hiện một lần; email có thể lặp ở tenant khác.
- `UNIQUE(country_code, phone_number)`: kiểm tra tính duy nhất theo một mã quốc gia kết hợp số điện thoại, nhưng vẫn cần chuẩn hóa cách lưu.

Không nên thêm một ràng buộc rộng hơn yêu cầu nghiệp vụ. Một ràng buộc quá chặt có thể ngăn tạo dữ liệu hợp lệ; một ràng buộc quá lỏng có thể cho phép hai bản ghi đại diện cùng một đối tượng thực tế.

### 2.2. `NULL` trong ràng buộc UNIQUE

`UNIQUE` không tự động có nghĩa là `NOT NULL`. Với PostgreSQL ở hành vi mặc định, nhiều hàng có thể mang `NULL` ở một cột có ràng buộc unique, vì các giá trị `NULL` được xử lý là khác nhau cho mục đích cưỡng chế tính duy nhất. Với unique nhiều cột, tổ hợp chứa `NULL` cũng cần được xem xét riêng.

Các DBMS không hoàn toàn giống nhau: MySQL thường cho phép nhiều `NULL` trong unique key, còn SQL Server có quy tắc khác về những tổ hợp chứa `NULL`. PostgreSQL phiên bản mới có các tùy chọn như `NULLS NOT DISTINCT` để thay đổi hành vi mặc định. Không suy từ kết quả trên PostgreSQL ra mọi hệ quản trị.

Nếu nghiệp vụ bắt buộc có email, khai báo cả **`nullable: false`** lẫn unique. Nếu email là tùy chọn, hãy quyết định rõ nhiều hàng chưa có email có được phép cùng tồn tại hay không, rồi chọn ràng buộc phù hợp với DBMS.

### 2.3. Chữ hoa, khoảng trắng, Unicode và collation

Xét ba giá trị:

```text
An@example.com
an@example.com
 an@example.com
```

Chúng khác nhau ở mức ký tự, nhưng có thể cùng một email theo quy tắc nghiệp vụ. Database có coi chúng là trùng hay không phụ thuộc collation, kiểu dữ liệu và biểu thức/index được dùng. Chẳng hạn, so sánh trong PostgreSQL với một kiểu/collation cụ thể có thể phân biệt chữ hoa và chữ thường, trong khi nhiều cấu hình MySQL hoặc SQL Server thường dùng collation không phân biệt hoa thường.

Nếu ứng dụng định nghĩa email bằng giá trị chuẩn hóa, cần thống nhất chính xác quy tắc đó: cắt khoảng trắng ngoài cùng hay không, đổi chữ thường ở phần nào, xử lý Unicode thế nào và có thay đổi cách so sánh khi nâng cấp DBMS không. Không tự động khẳng định việc chuyển mọi email sang chữ thường luôn đúng tuyệt đối cho mọi hệ thống. Dù chọn chiến lược nào, **truy vấn phát hiện trùng phải dùng cùng quy tắc với ràng buộc thực sự được triển khai**.

### 2.4. Dữ liệu xóa mềm (*soft delete*)

Nhiều hệ thống giữ hàng cũ bằng cột `deleted_at` thay vì xóa vật lý. Khi đó có hai chính sách nghiệp vụ khác nhau:

1. Một email chỉ được tồn tại một lần trong tenant, kể cả trên các hàng đã xóa mềm.
2. Một email chỉ được duy nhất trong **các hàng còn hoạt động** (`deleted_at IS NULL`); email ở hàng đã xóa mềm có thể được dùng lại.

`UNIQUE(tenant_id, email)` thực hiện chính sách thứ nhất. Chính sách thứ hai thường cần **unique index có điều kiện** hoặc một giải pháp riêng theo DBMS, không thể chỉ thêm unique constraint thông thường rồi mong Liquibase tự bỏ qua hàng đã xóa mềm.

## 3. Kiểm tra dữ liệu trùng trước khi viết changeset

Đối với bảng đang hoạt động, hãy **kiểm kê trước khi áp dụng DDL**. Đừng phỏng đoán rằng dữ liệu sạch chỉ vì ứng dụng hiện có kiểm tra email. Dữ liệu có thể đã được nhập bởi script cũ, import, thao tác quản trị hoặc những lần chạy đồng thời.

### 3.1. Phát hiện trùng chính xác theo hai cột

Giả sử bảng `app_member` có `tenant_id` và `email` đều `NOT NULL`. Truy vấn SQL cơ bản:

```sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM app_member
GROUP BY tenant_id, email
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, email;
```

Kết quả trả về những **nhóm khóa bị trùng**. Nếu có hàng `(10, 'an@example.com')` hai lần, nhóm đó vi phạm unique trên `(tenant_id, email)`. Hàng ở tenant 11 không làm phát sinh trùng với tenant 10.

Nếu cột cho phép `NULL`, việc `GROUP BY` gom các hàng có `NULL` vào một nhóm không nhất thiết có nghĩa unique constraint của DBMS sẽ coi các hàng đó là vi phạm. Khi rà soát unique theo hành vi PostgreSQL mặc định, có thể bổ sung điều kiện `WHERE tenant_id IS NOT NULL AND email IS NOT NULL`; nhưng không được áp dụng mẹo này cho DBMS có quy tắc unique/NULL khác mà không kiểm chứng.

### 3.2. Phát hiện trùng theo quy tắc chuẩn hóa

Với PostgreSQL, nếu dự định cưỡng chế tính duy nhất theo email sau khi cắt khoảng trắng và chuyển chữ thường:

```sql
SELECT
    tenant_id,
    lower(btrim(email)) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM app_member
WHERE email IS NOT NULL
GROUP BY tenant_id, lower(btrim(email))
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, normalized_email;
```

Đây là **truy vấn nghiệp vụ bổ sung**, không tương đương với việc kiểm tra duplicate cho ràng buộc `UNIQUE(tenant_id, email)` đơn thuần. Ràng buộc duy nhất trên các cột gốc và unique index trên biểu thức `lower(btrim(email))` có thể cho kết quả khác nhau.

### 3.3. Xác định chính xác các hàng cần xử lý

Truy vấn cửa sổ sau hỗ trợ phân loại nhóm trùng theo một chính sách ví dụ, *không tự động xóa hàng*:

```sql
SELECT
    id,
    tenant_id,
    email,
    ROW_NUMBER() OVER (
        PARTITION BY tenant_id, lower(btrim(email))
        ORDER BY id
    ) AS duplicate_rank
FROM app_member
WHERE email IS NOT NULL
ORDER BY tenant_id, lower(btrim(email)), duplicate_rank;
```

`duplicate_rank = 1` chỉ là hàng đứng đầu theo `id` trong ví dụ; nó **không mặc nhiên là bản ghi đúng để giữ**. Chính sách hợp nhất cần xem ngày tạo, tình trạng hoạt động, khóa ngoại, lịch sử nghiệp vụ và nguồn dữ liệu. Có trường hợp phải giữ hàng mới nhất, có trường hợp phải giữ hàng được xác minh, cũng có trường hợp cần chuyển các tham chiếu rồi mới bỏ bản ghi trùng.

**Không áp dụng ngay `DELETE WHERE duplicate_rank > 1` vào production.** Xóa trực tiếp có thể gây mất đơn hàng, lịch sử thanh toán, dữ liệu tham chiếu hoặc vi phạm foreign key.

## 4. Xử lý dữ liệu trùng lặp theo kế hoạch

Trước khi thêm ràng buộc, cần xác định cách giải quyết từng nhóm trùng. Một quy trình thực tế:

1. **Chốt chính sách nghiệp vụ**: toàn bảng hay theo tenant; phân biệt hoa thường không; xử lý `NULL` và soft-delete thế nào.
2. **Đo hiện trạng**: thống kê số nhóm trùng, số hàng liên quan, mức độ phân tán theo tenant; lưu số liệu trước migration.
3. **Xác định bản ghi chuẩn**: nghiệp vụ chọn bản ghi giữ lại theo quy tắc có thể kiểm chứng, không chọn tùy tiện chỉ vì `MIN(id)`.
4. **Kiểm tra quan hệ tham chiếu**: foreign key và dữ liệu ở bảng con có thể cần được chuyển tới bản ghi chuẩn.
5. **Lập kế hoạch khôi phục**: snapshot/backup, log đối chiếu và kịch bản dừng giữa chừng. Với dữ liệu quan trọng, chuẩn bị mapping `old_id → canonical_id`.
6. **Làm sạch theo từng lô** khi cần, hạn chế transaction quá lớn và theo dõi khóa, tải ghi, replication lag.
7. **Chạy lại truy vấn duplicate** theo đúng biểu thức ràng buộc dự định tạo và xác nhận không còn vi phạm.
8. **Đặt cơ chế ngăn tái phát** trong giai đoạn chuyển tiếp, sau đó để database cưỡng chế tính duy nhất.

Các thao tác làm sạch dữ liệu bản chất là thay đổi nghiệp vụ và có thể không đảo ngược hoàn toàn. Chúng nên được kiểm thử, review và, khi thích hợp, đặt trong những changeset riêng có log/rollback hoặc kế hoạch forward-fix. Không chèn một câu lệnh xóa hàng trùng “ngầm” vào changeset tạo unique constraint.

## 5. Tạo UNIQUE ngay khi tạo bảng mới

Khi bảng chưa có dữ liệu, có thể khai báo unique trực tiếp trong `createTable` bằng `constraints` của cột:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-user-account"
      author: "db-team"
      changes:
        - createTable:
            tableName: user_account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: username
                  type: VARCHAR(80)
                  constraints:
                    nullable: false
                    unique: true
                    uniqueConstraintName: uq_user_account_username
      rollback:
        - dropTable:
            tableName: user_account
```

`unique: true` yêu cầu unique constraint cho cột `username`, còn `nullable: false` cấm giá trị `NULL`. `uniqueConstraintName` đặt tên rõ ràng cho ràng buộc. Tên ràng buộc cần được chọn phù hợp giới hạn độ dài và quy tắc đặt tên của DBMS.

Đây là cách khai báo phù hợp khi **một cột** cần unique ngay lúc tạo bảng. Với tính duy nhất **theo tổ hợp cột**, việc dùng một changeset gồm `createTable` rồi `addUniqueConstraint` thường rõ nghĩa và dễ kiểm tra hơn.

## 6. Thêm ràng buộc UNIQUE cho bảng đã tồn tại bằng Liquibase

Trong dự án thực tế, bảng thường đã tồn tại và có dữ liệu trước khi phát sinh yêu cầu unique. Change type được dùng phổ biến là `addUniqueConstraint`; rollback tương ứng có thể dùng `dropUniqueConstraint`.

### 6.1. Ví dụ tạo bảng nền để luyện tập

Nếu chưa có bảng mẫu, changeset sau tạo `app_member`. Đây là bước dành cho **database thử nghiệm mới**, không dùng để tạo lại bảng đã tồn tại trong production:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-app-member"
      author: "db-team"
      changes:
        - createTable:
            tableName: app_member
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: tenant_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
              - column:
                  name: deleted_at
                  type: TIMESTAMP
      rollback:
        - dropTable:
            tableName: app_member
```

Changeset này chưa tạo unique cho `(tenant_id, email)`. Ta cố ý tách việc thêm ràng buộc thành một changeset sau để mô phỏng quy trình nâng cấp một bảng đã có dữ liệu.

### 6.2. Changeset kiểm tra duplicate rồi thêm unique

Với bảng `app_member` đã tồn tại, dữ liệu đang sạch và cả `tenant_id`, `email` đều `NOT NULL`, có thể viết một changeset:

```yaml
databaseChangeLog:
  - changeSet:
      id: "002-add-app-member-tenant-email-unique"
      author: "db-team"
      comment: "Mỗi email duy nhất trong phạm vi một tenant"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |-
              SELECT COUNT(*)
              FROM (
                  SELECT tenant_id, email
                  FROM app_member
                  GROUP BY tenant_id, email
                  HAVING COUNT(*) > 1
              ) duplicate_groups
      changes:
        - addUniqueConstraint:
            tableName: app_member
            columnNames: tenant_id, email
            constraintName: uq_app_member_tenant_email
      rollback:
        - dropUniqueConstraint:
            tableName: app_member
            constraintName: uq_app_member_tenant_email
```

Ý nghĩa từng phần:

- `id` + `author` + đường dẫn changelog góp phần tạo định danh changeset; giữ ổn định khi đã triển khai.
- `sqlCheck` kiểm tra có bao nhiêu **nhóm khóa trùng**. Giá trị mong đợi `"0"` là chuỗi để so với kết quả truy vấn.
- `onFail: HALT` dừng khi truy vấn trả về số nhóm trùng khác 0; `onError: HALT` dừng khi truy vấn kiểm tra gặp lỗi.
- `addUniqueConstraint` yêu cầu database cưỡng chế tính duy nhất của **tổ hợp** `tenant_id, email`.
- `constraintName` đặt tên để kiểm tra metadata, sửa đổi hoặc rollback sau này.
- `dropUniqueConstraint` ở rollback xóa ràng buộc vừa thêm, nhưng **không sửa ngược** bất kỳ dữ liệu nào đã được xử lý trước đó.

Ví dụ giả định precondition query đã được kiểm tra trên DBMS cụ thể và có quyền đọc dữ liệu. Khi bảng nằm ở schema khác mặc định, cần chỉ định `schemaName` nhất quán trên change type, rollback và truy vấn SQL. Các tên và tùy chọn hỗ trợ của `addUniqueConstraint` có thể khác theo phiên bản Liquibase/DBMS; kiểm tra SQL preview trên mục tiêu thực tế.

**Lưu ý về thời điểm:** truy vấn duplicate trong precondition không khóa vĩnh viễn bảng. Một tiến trình khác vẫn có thể thêm hàng trùng sau lúc kiểm tra nhưng trước khi ràng buộc được tạo. Khi đó DDL vẫn có thể thất bại; cần xử lý race condition và trạng thái lỗi một cách có kiểm soát, không coi `sqlCheck` là bảo đảm nguyên tử tuyệt đối.

### 6.3. Thử trên database có dữ liệu trùng

Sau khi triển khai **chỉ** changeset tạo bảng `001` trên database thử nghiệm, nạp dữ liệu giả như sau trước khi đưa `002` vào luồng migration:

```sql
INSERT INTO app_member (id, tenant_id, email)
VALUES
    (101, 10, 'an@example.com'),
    (102, 10, 'an@example.com'),
    (103, 11, 'an@example.com');
```

Truy vấn duplicate ở mục 3 sẽ phát hiện cặp hai hàng `101` và `102` trong tenant 10. Hàng `103` ở tenant 11 là hợp lệ theo khóa ghép. Khi thử changeset `002`, precondition phải dừng vì còn trùng. Sau khi sửa dữ liệu thử nghiệm bằng phương án đã thống nhất và chạy lại truy vấn cho kết quả 0, thay đổi unique mới có cơ hội thành công.

Trong quy trình học tập, bạn có thể tạo lại database giữa các lượt thử. Trong môi trường đã có dữ liệu thật, mọi thao tác cập nhật hoặc xóa bản ghi phải có quy trình phê duyệt và phương án khôi phục tương ứng.

## 7. Unique constraint và unique index: chọn đúng công cụ

Nhiều DBMS triển khai unique constraint dựa trên một chỉ mục duy nhất ở bên dưới. Tuy nhiên, hai khái niệm không hoàn toàn đồng nghĩa:

- Unique constraint diễn đạt **quy tắc toàn vẹn dữ liệu** ở cấp bảng, thường được quản lý qua metadata ràng buộc.
- Unique index diễn đạt cấu trúc chỉ mục có thêm yêu cầu không trùng, đôi khi hỗ trợ **biểu thức**, **điều kiện lọc**, hoặc cơ chế tạo chỉ mục đặc thù DBMS.
- Việc tạo thêm một index thường trên cùng cột sau khi đã có unique constraint có thể là trùng lặp, tăng chi phí ghi và dung lượng lưu trữ mà không đem lại lợi ích tương ứng.

Chọn `addUniqueConstraint` khi cần tính duy nhất trên cột/tổ hợp cột theo ngữ nghĩa chuẩn của DBMS. Nếu cần chuẩn hóa giá trị hoặc chỉ bảo vệ hàng đang hoạt động, hãy xem khả năng **functional/partial unique index** của DBMS, đồng thời chấp nhận giảm tính portable.

### 7.1. Case-insensitive uniqueness bằng biểu thức (PostgreSQL)

Nếu yêu cầu nghiệp vụ là một email duy nhất theo `lower(btrim(email))` trong từng tenant, unique constraint trên hai cột gốc không bảo đảm điều đó trong mọi cấu hình. Một phương án riêng cho PostgreSQL là:

```sql
CREATE UNIQUE INDEX uq_app_member_tenant_email_normalized
ON app_member (tenant_id, lower(btrim(email)));
```

Đây là SQL **đặc thù PostgreSQL**. Cần kiểm tra duplicate với **chính biểu thức** `lower(btrim(email))` trước khi tạo index. Đồng thời cần thống nhất xử lý Unicode và quy tắc normalize ở ứng dụng; không coi `lower` là một giải pháp chuẩn hóa email toàn năng.

Nếu Liquibase quản lý SQL đặc thù này, ví dụ một changeset tùy chọn **thay cho** simple unique constraint ở mục 6:

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-add-normalized-email-unique-pg"
      author: "db-team"
      dbms: postgresql
      changes:
        - sql:
            sql: |-
              CREATE UNIQUE INDEX uq_app_member_tenant_email_normalized
              ON app_member (tenant_id, lower(btrim(email)));
      rollback:
        - sql:
            sql: |-
              DROP INDEX IF EXISTS uq_app_member_tenant_email_normalized;
```

**Không sao chép đồng thời tất cả ví dụ trên vào cùng một changelog mà chưa quyết định chính sách.** `002` bảo đảm không trùng giá trị gốc; `003` bảo đảm không trùng giá trị sau chuẩn hóa. Dùng cả hai có thể là dư thừa và làm phức tạp rollback, trong khi dùng mỗi `002` có thể không đáp ứng nghiệp vụ không phân biệt chữ hoa.

### 7.2. Tính duy nhất chỉ với bản ghi chưa xóa mềm (PostgreSQL)

Nếu muốn cho phép tái sử dụng email khi bản ghi cũ đã `deleted_at IS NOT NULL`:

```sql
CREATE UNIQUE INDEX uq_app_member_active_email
ON app_member (tenant_id, lower(btrim(email)))
WHERE deleted_at IS NULL;
```

Chỉ những hàng đang hoạt động mới nằm trong phạm vi cưỡng chế của index có điều kiện này. Truy vấn kiểm tra duplicate trước migration cũng phải thêm `WHERE deleted_at IS NULL` và nhóm theo đúng biểu thức ở index.

Một thay đổi đáng chú ý: khi khôi phục một hàng đã xóa mềm bằng cách đặt `deleted_at = NULL`, database sẽ kiểm tra unique index và có thể từ chối nếu email đó đã được một hàng hoạt động khác sử dụng. Phải thiết kế quy trình khôi phục theo cùng bất biến nghiệp vụ.

`CREATE INDEX CONCURRENTLY` của PostgreSQL có thể giúp giảm khóa ghi trong một số hoàn cảnh, nhưng yêu cầu vận hành riêng (không chạy bên trong transaction block thông thường, xử lý index không hợp lệ khi thất bại). Nếu dùng Liquibase cho cách tạo chỉ mục này, cần hiểu `runInTransaction` và rollback phù hợp, rồi thử với phiên bản PostgreSQL/Liquibase thực tế. Không tự ý biến ví dụ `CREATE UNIQUE INDEX` thông thường thành `CONCURRENTLY` trên production.

## 8. Thêm uniqueness vào bảng lớn đang có nhiều request ghi

Ràng buộc duy nhất phải được tạo khi dữ liệu sạch và chiến lược ghi đồng thời không phá giả định của migration. Bài toán thực tế có thêm vấn đề về thời gian quét/index, lock và thời điểm chuyển đổi ứng dụng.

Một quy trình triển khai có thể gồm:

1. **Đo dữ liệu và sức tải**: số hàng, số nhóm trùng, tốc độ ghi, replication lag, kích thước bảng và khả năng lock.
2. **Chốt quy tắc duy nhất**: tenant scope, collation, normalize, `NULL`, soft delete; lưu trong tài liệu thiết kế.
3. **Chuẩn bị ứng dụng**: cập nhật validation và xử lý lỗi unique từ database; nếu có thể, chặn dữ liệu mới vi phạm trong giai đoạn dọn dẹp.
4. **Dọn dữ liệu hiện có**: giải quyết duplicate theo chính sách nghiệp vụ, ghi log thao tác và kiểm tra quan hệ tham chiếu.
5. **Chạy lại kiểm tra dữ liệu** sát thời điểm migration, kể cả các bản ghi đến từ job import hoặc service khác.
6. **Triển khai unique constraint/index** bằng kỹ thuật và cửa sổ thay đổi thích hợp DBMS, có kế hoạch xử lý lock/timeout.
7. **Kiểm tra kết quả**: metadata constraint/index, khả năng từ chối insert trùng, truy vấn nghiệp vụ và log ứng dụng.
8. **Theo dõi sau triển khai**: số lỗi conflict, độ trễ ghi, sử dụng index và hành vi retry của các service.

**Race condition:** hai giao dịch có thể cùng thấy email chưa tồn tại khi chỉ thực hiện `SELECT` trước `INSERT`. Cả hai đều thử ghi. Một unique constraint/index hợp lệ giúp database từ chối một lần ghi xung đột, nhưng ứng dụng phải bắt lỗi ràng buộc và trả kết quả phù hợp thay vì coi đó là lỗi không dự đoán được.

Đừng dựa vào precondition Liquibase để ngăn hoàn toàn concurrency. Với bảng lớn hoặc hệ thống yêu cầu zero/low downtime, cần nghiên cứu cách tạo index/ràng buộc trực tuyến và cơ chế khóa của đúng DBMS; thời gian thực hiện và khả năng rollback không giống nhau giữa PostgreSQL, MySQL, SQL Server và Oracle.

## 9. Rollback không có nghĩa là khôi phục toàn bộ dữ liệu

Rollback của changeset `addUniqueConstraint` thường là `dropUniqueConstraint`, có nghĩa **gỡ quy tắc không trùng**. Nó không tự khôi phục bản ghi đã bị xóa, không đảo ngược việc hợp nhất khách hàng và không làm email trở lại cách viết ban đầu.

Một số câu hỏi cần trả lời trước khi thiết kế rollback:

- Việc gỡ ràng buộc có cho phép xuất hiện duplicate trong thời gian chạy phiên bản ứng dụng cũ không?
- Có bước chuẩn hóa hoặc hợp nhất dữ liệu nào đã mất thông tin gốc?
- Các dữ liệu tham chiếu đã được chuyển sang bản ghi nào? Có cần restore từ backup hay bảng mapping không?
- Có bảng/index khác phụ thuộc vào ràng buộc hoặc tên của nó không?
- Khi rollback một chuỗi changeset, thứ tự xóa ràng buộc có an toàn với các thay đổi DDL khác không?

Khi dữ liệu nghiệp vụ quan trọng, **forward-fix** bằng changeset mới đôi khi an toàn hơn rollback phá hủy. Lựa chọn phải dựa trên trạng thái thực tế của database, không chỉ dựa vào việc Liquibase có lệnh rollback hay không.

## 10. Validate, SQL preview và lịch sử Liquibase

Một quy trình tối thiểu trước production:

```bash
# Cấu hình kết nối/JDBC driver/changelog đã được nạp qua defaults file
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status
liquibase --defaults-file=liquibase.properties update-sql

# Chỉ thực hiện sau khi xác minh DB đích, dữ liệu và SQL được sinh
liquibase --defaults-file=liquibase.properties update
```

`validate` giúp kiểm tra cấu trúc changelog và các điều kiện kiểm tra lịch sử mà Liquibase hỗ trợ. Nó **không chứng minh** rằng mọi hàng dữ liệu hiện có đáp ứng unique constraint hay rằng tạo index không gây lock lâu. `update-sql` giúp review SQL trước khi thực thi, nhưng cũng không thay thế phép thử thật trên bản sao dữ liệu có lịch sử tương đương production.

Sau cập nhật, có thể kiểm tra lịch sử changeset:

```sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
WHERE id = '002-add-app-member-tenant-email-unique';
```

Đây là ví dụ truy vấn khi tên bảng/cột metadata được DBMS phân giải theo quy tắc không phân biệt chữ hoa khi không quote, như PostgreSQL mặc định. Trên DBMS khác, điều chỉnh schema và cách viết tên đối tượng phù hợp.

Kiểm tra unique constraint thực sự hiện diện trên PostgreSQL:

```sql
SELECT constraint_name, table_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'public'
  AND table_name = 'app_member'
  AND constraint_type = 'UNIQUE';
```

Nếu dùng **unique index trên biểu thức** hoặc **partial unique index**, không phải tất cả chúng đều xuất hiện dưới dạng `UNIQUE` constraint trong `information_schema.table_constraints`. Khi đó cần kiểm tra danh sách index của DBMS (ví dụ hệ thống catalog `pg_indexes`/`pg_index` của PostgreSQL), không kết luận index vắng mặt chỉ vì truy vấn constraint không trả về dòng.

Chạy lại truy vấn kiểm tra duplicate theo đúng quy tắc đã triển khai và thử một `INSERT` trùng trên database thử nghiệm. Database phải từ chối vi phạm. Trong kiểm thử có transaction, có thể rollback dữ liệu test; tránh thử chèn dữ liệu giả vào production.

### 10.1. Giữ định danh và checksum changeset ổn định

Liquibase nhận diện changeset thông thường theo `id`, `author` và đường dẫn file changelog (hoặc `logicalFilePath` được cấu hình), đồng thời ghi checksum vào `DATABASECHANGELOG`. Sau khi changeset tạo unique đã được triển khai, **không sửa trực tiếp** danh sách cột hay biểu thức của changeset đó để “đổi lại chính sách” ở môi trường khác.

Nếu nghiệp vụ thay đổi từ `UNIQUE(email)` sang `UNIQUE(tenant_id, email)`, tạo các changeset mới theo thứ tự hợp lý, có kiểm tra dữ liệu và phương án rollback. Nếu đổi đường dẫn file changelog hoặc chuyển từ CLI sang Spring Boot, đối chiếu `FILENAME` để không khiến changeset cũ bị nhận diện là mới. Không xóa thủ công `DATABASECHANGELOG` hoặc checksum để che lỗi.

## 11. Phối hợp triển khai qua Spring Boot và CI/CD

Trong Spring Boot, changelog thường được đóng gói tại `src/main/resources/db/changelog/` và cấu hình:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Nếu chọn chạy migration qua Liquibase CLI trong pipeline thay vì lúc khởi động ứng dụng, hãy tắt cơ chế tự chạy tương ứng tại môi trường đó để tránh hai tiến trình migration cùng tranh lịch trình. Các đường chạy phải dùng **cùng artifact, phiên bản Liquibase, changelog và quy tắc định danh changeset**.

Với ràng buộc unique trên bảng có dữ liệu thật, pipeline nên có các bước kiểm soát:

| Bước | Kiểm tra | Điều kiện đạt |
|---|---|---|
| Review yêu cầu | Phạm vi uniqueness, `NULL`, chuẩn hóa, soft delete | Chính sách được nghiệp vụ và kỹ thuật thống nhất |
| Phân tích dữ liệu | SQL thống kê duplicate trên bản sao dữ liệu hoặc môi trường đích theo quy định | Không còn nhóm vi phạm trước DDL |
| Review migration | `validate` và `update-sql`; precondition và rollback | SQL sinh ra phù hợp DBMS, schema và quy tắc unique |
| Staging | Chạy trên dữ liệu/khối lượng gần production | Xác định thời gian thực thi và mức lock chấp nhận được |
| Phát hành | Backup, approval, lịch cập nhật, xác minh DB đích | Có người chịu trách nhiệm và phương án dừng/khôi phục |
| Hậu triển khai | Metadata, thử xung đột an toàn, metric lỗi insert | Unique được thực thi và ứng dụng xử lý conflict đúng |

Đừng nhầm `contexts`/`labels` với quy tắc duy nhất: chúng chỉ lọc changeset theo lần chạy, không bảo vệ dữ liệu khi nhiều ứng dụng cùng ghi. Chính DBMS phải cưỡng chế ràng buộc sau khi thay đổi đã được triển khai thành công.

## 12. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `addUniqueConstraint` thất bại với duplicate key | Bảng đã có nhiều hàng cùng tổ hợp khóa | Truy vấn nhóm duplicate theo đúng quy tắc unique; xử lý dữ liệu trước |
| SQL kiểm tra báo sạch nhưng tạo unique vẫn lỗi | Khác quy tắc collation/`NULL`/normalization, hoặc có ghi mới giữa hai bước | So sánh biểu thức, DBMS và kiểm soát ghi đồng thời |
| Unique đã tạo nhưng vẫn có email khác chữ hoa | Collation hoặc constraint trên dữ liệu gốc có phân biệt chữ hoa | Xem yêu cầu normalize; cân nhắc functional unique index/kiểu dữ liệu phù hợp |
| Thêm ràng buộc khiến ứng dụng gặp nhiều lỗi conflict | Ứng dụng chưa xử lý unique violation hoặc đã dựa vào việc cho phép trùng | Cập nhật logic ứng dụng và trả lỗi nghiệp vụ có kiểm soát |
| Một số hàng có `NULL` vẫn được chèn dù có unique | Unique và nullability là hai quy tắc khác nhau, khác nhau giữa DBMS | Kiểm tra `NOT NULL` và chính sách `NULL` của DBMS |
| Cần cho phép tái sử dụng email sau soft delete | Unique toàn bảng quá chặt | Thiết kế partial index hoặc giải pháp tương đương tùy DBMS |
| Chạy SQL tạo index lâu hoặc gây lock | Bảng lớn, tùy chọn online index không phù hợp hoặc tải ghi cao | Đánh giá lock, phiên bản DBMS và kế hoạch downtime/online DDL |
| Metadata không thấy ràng buộc nhưng index vẫn tồn tại | Đã tạo unique index thay vì unique constraint | Kiểm tra cả catalog constraint và index |
| Lỗi checksum sau sửa changelog | Changeset cũ đã bị thay đổi | Khôi phục nội dung đã triển khai, tạo changeset mới |
| Rollback constraint rồi duplicate quay lại | Gỡ cưỡng chế DB cho phép dữ liệu trùng mới | Xác định chính sách ứng dụng và kế hoạch rollback/forward-fix |

## 13. Thực hành theo từng vòng kiểm chứng

Hãy thực hành trên database có thể tạo lại:

1. **Tạo bảng** `app_member` theo changeset `001` tại mục 6, chưa thêm unique.
2. **Nạp dữ liệu thử**: hai hàng trùng `(tenant_id, email)` ở cùng tenant và một hàng cùng email ở tenant khác.
3. **Thống kê duplicate** bằng `GROUP BY ... HAVING COUNT(*) > 1`; xác nhận chỉ nhóm cùng tenant bị phát hiện.
4. **Thêm changeset `002`** với precondition và `addUniqueConstraint`; chạy `validate`, xem `update-sql` và thử `update`. Dự kiến migration dừng vì còn duplicate.
5. **Sửa dữ liệu thử theo chính sách** (ví dụ đổi email của một hàng khi không có tham chiếu/phụ thuộc); chạy lại truy vấn cho kết quả 0 rồi áp dụng changeset.
6. **Xác minh ràng buộc** bằng metadata DBMS và thử chèn cặp khóa trùng trong một transaction test; kiểm tra DB từ chối và application xử lý lỗi.
7. **Khảo sát khác biệt hoa thường**: thử `An@example.com` và `an@example.com` theo cấu hình DBMS, sau đó so sánh với các nhóm trùng do `lower(btrim(email))` tính ra.
8. **Thử rollback** `dropUniqueConstraint` trên database dùng riêng, kiểm tra metadata và tác động đến tính toàn vẹn dữ liệu.
9. **Thiết kế chính sách soft-delete**: xác định muốn cấm trùng trên toàn bộ bảng hay chỉ trên hàng đang hoạt động. Nếu chọn cách thứ hai, thử unique index có điều kiện trên PostgreSQL thay vì copy đồng thời tất cả ví dụ.
10. **Ghi nhận lịch sử** trong `DATABASECHANGELOG`, chạy lại `update` và xác nhận changeset bình thường không bị thực thi lại.

### Checklist trước khi merge hoặc phát hành

- [ ] Quy tắc duy nhất đã được mô tả theo nghiệp vụ: một cột hay tổ hợp cột, tenant scope, hoa thường, `NULL` và soft delete.
- [ ] Đã kiểm tra dữ liệu trùng theo **chính quy tắc so sánh** mà constraint/index sẽ thực thi.
- [ ] Kế hoạch hợp nhất/xóa/đổi dữ liệu trùng có review nghiệp vụ, kiểm tra foreign key và phương án khôi phục.
- [ ] Không dùng precondition như biện pháp duy nhất để ngăn race condition khi còn có traffic ghi.
- [ ] Đã chọn `addUniqueConstraint` hay unique index có điều kiện/biểu thức phù hợp DBMS.
- [ ] Tên constraint/index rõ ràng và không tạo cấu trúc trùng lặp không cần thiết.
- [ ] Changelog YAML, precondition, `validate` và SQL preview đã được kiểm tra.
- [ ] Đã đo thời gian tạo unique và tác động lock trên database tương đương production.
- [ ] Ứng dụng xử lý đúng lỗi unique violation khi nhiều request đồng thời.
- [ ] Rollback không bị nhầm là thao tác tự phục hồi dữ liệu đã xóa hoặc hợp nhất.
- [ ] Định danh, checksum và lịch sử `DATABASECHANGELOG` được bảo toàn giữa các môi trường.

**Kết luận:** ràng buộc duy nhất là một quy tắc toàn vẹn dữ liệu, không chỉ một tùy chọn để tăng tốc truy vấn. Với bảng mới, có thể định nghĩa ngay unique ở cột hoặc tổ hợp cột; với bảng đã có dữ liệu, phải xác định rõ **thế nào là trùng**, thống kê và xử lý vi phạm, sau đó triển khai bằng Liquibase với precondition, SQL preview, kiểm thử và giám sát thích hợp. Kết hợp một ràng buộc đúng nghiệp vụ với lịch sử changeset ổn định giúp các migration của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` đáng tin cậy hơn trên local, staging, production và trong quy trình Spring Boot/CI/CD.
