# Tạo bảng, định nghĩa cột và chọn kiểu dữ liệu bằng Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học quản lý thay đổi schema và dữ liệu bằng **changelog, changeset, precondition, checksum và lịch sử triển khai**; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Tạo bảng là một thay đổi schema cơ bản nhưng ảnh hưởng lâu dài đến khả năng lưu trữ, tính toàn vẹn dữ liệu, hiệu năng truy vấn và tính tương thích giữa các hệ quản trị cơ sở dữ liệu (DBMS).

Bài học này thuộc phần **Thay đổi bảng**, tập trung vào ba việc: biểu diễn lệnh tạo bảng bằng change type `createTable`, khai báo từng cột cùng ràng buộc phù hợp, và chọn kiểu dữ liệu dựa trên ý nghĩa nghiệp vụ thay vì chỉ chọn kiểu dễ viết. Các ví dụ dùng YAML và PostgreSQL để minh họa; khi chạy trên MySQL, SQL Server, Oracle hoặc DBMS khác, phải kiểm tra các kiểu dữ liệu, cách cấp khóa tự tăng và SQL Liquibase sinh ra trên phiên bản cụ thể.

## 1. Tư duy trước khi tạo một bảng

Trước khi viết changelog, hãy trả lời những câu hỏi thiết kế sau:

1. **Bảng lưu thực thể hay sự kiện gì?** Ví dụ `customer_account` chứa thông tin tài khoản khách hàng, không nên đồng thời chứa danh sách đơn hàng dưới dạng một chuỗi phân tách tùy ý.
2. **Mỗi hàng được nhận diện bằng gì?** Chọn khóa chính ổn định, chẳng hạn `id` kiểu số nguyên lớn; xác định ai sinh giá trị khóa.
3. **Những thuộc tính nào bắt buộc?** `email` có thể phải có giá trị, trong khi `display_name` là tùy chọn.
4. **Dữ liệu có những giới hạn nào?** Tên người có độ dài bao nhiêu; tiền có bao nhiêu chữ số; dấu thời gian cần timezone hay không?
5. **Có quy tắc duy nhất hay tham chiếu không?** Địa chỉ email có bắt buộc duy nhất; các bảng khác sẽ tham chiếu khóa nào?
6. **Giá trị mặc định được tính ở đâu?** Tại ứng dụng, ở database bằng `DEFAULT`, hay bằng một migration backfill?
7. **Độ lớn dữ liệu và truy vấn dự kiến?** Những cột thường được lọc, sắp xếp hay join có thể cần index; không mặc định tạo index cho mọi cột.

Một bảng hoạt động được về cú pháp nhưng có kiểu dữ liệu sai vẫn tạo ra nợ kỹ thuật. Ví dụ, lưu tiền vào `FLOAT` có thể dẫn đến sai số nhị phân; lưu mã bưu chính vào `INTEGER` làm mất số 0 đầu; lưu thời điểm sự kiện thành `VARCHAR` khiến so sánh và xử lý múi giờ phức tạp hơn.

## 2. Cấu trúc `createTable` trong YAML

Change type `createTable` yêu cầu tên bảng và danh sách `columns`. Mỗi phần tử `column` khai báo tên, kiểu và có thể có constraints, default, chú thích hoặc tùy chọn khác.

```text
databaseChangeLog
  └── changeSet (id + author)
      ├── preConditions (nếu cần)
      ├── changes
      │   └── createTable
      │       ├── tableName
      │       ├── schemaName (nếu chỉ định schema)
      │       └── columns
      │           ├── column: name + type + constraints + default...
      │           └── column: name + type + constraints + default...
      └── rollback (nếu được thiết kế)
```

Ví dụ tối giản:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-category"
      author: "db-team"
      changes:
        - createTable:
            tableName: category
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: category
```

Phân biệt các cấp YAML:

- `databaseChangeLog` là danh sách các thành phần changelog; `- changeSet` mở một phần tử.
- `changes` là một **danh sách**; `- createTable` là một change trong danh sách đó.
- `tableName` và `columns` cùng nằm trong `createTable`.
- `columns` cũng là một **danh sách**; mỗi `- column` có `name`, `type` và `constraints` của riêng mình.
- `constraints` thuộc về **cột tương ứng**. Không đặt `nullable` ngang cấp với `createTable` rồi kỳ vọng nó áp dụng cho mọi cột.
- `id` và `author` không phải tên bảng/cột; chúng phục vụ định danh changeset trong lịch sử Liquibase.

`createTable` được Liquibase chuyển thành DDL của hệ quản trị đang kết nối, ví dụ `CREATE TABLE ...`. **Định nghĩa YAML không bảo đảm SQL giống nhau giữa các DBMS.** Mọi giả định về cú pháp khóa tự tăng, kiểu dữ liệu, default hay ràng buộc đều cần được xác nhận bằng bản SQL preview thực tế.

## 3. Changelog mẫu đầy đủ cho bảng tài khoản khách hàng

Giả sử yêu cầu nghiệp vụ là: mỗi tài khoản có một mã nội bộ, một email bắt buộc và duy nhất, tên hiển thị có thể để trống, số dư tiền tệ cố định bốn chữ số sau dấu thập phân, trạng thái kích hoạt và thời điểm tạo bản ghi.

Lưu nội dung sau vào một changelog YAML của dự án, ví dụ `db/changelog/changes/001-create-customer-account.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer-account"
      author: "db-team"
      comment: "Tạo bảng tài khoản khách hàng"
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: customer_account
      changes:
        - createTable:
            tableName: customer_account
            remarks: "Thông tin tài khoản khách hàng"
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer_account
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
                    unique: true
                    uniqueConstraintName: uq_customer_account_email
              - column:
                  name: display_name
                  type: VARCHAR(150)
                  constraints:
                    nullable: true
              - column:
                  name: balance
                  type: DECIMAL(19,4)
                  defaultValueNumeric: 0
                  constraints:
                    nullable: false
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: true
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer_account
```

### 3.1. Giải thích từng quyết định

| Cột | Kiểu và ràng buộc | Lý do |
|---|---|---|
| `id` | `BIGINT`, `autoIncrement`, primary key, `NOT NULL` | Mã nội bộ để tham chiếu giữa các bảng; chiến lược tự tăng là lựa chọn triển khai, không phải bắt buộc cho mọi hệ thống |
| `email` | `VARCHAR(255)`, `NOT NULL`, unique | Giới hạn độ dài và ngăn trùng theo quy tắc so sánh của DBMS/index đang dùng |
| `display_name` | `VARCHAR(150)`, nullable | Chưa có tên hiển thị vẫn tạo được tài khoản |
| `balance` | `DECIMAL(19,4)`, `DEFAULT 0`, `NOT NULL` | Tránh sai số từ số thực nhị phân; phải thống nhất đơn vị tiền và quy tắc làm tròn |
| `active` | `BOOLEAN`, `DEFAULT true`, `NOT NULL` | Biểu diễn trạng thái nhị phân rõ nghĩa |
| `created_at` | `TIMESTAMP`, `DEFAULT CURRENT_TIMESTAMP` | Ghi thời điểm tạo ở database; vẫn cần quyết định quy ước timezone |

`primaryKeyName` và `uniqueConstraintName` đặt tên ràng buộc rõ ràng, giúp thông báo lỗi và migration sau dễ đọc hơn. Việc khai báo unique cho `email` **không giải quyết hoàn toàn** quy tắc email có phân biệt chữ hoa/chữ thường hay chuẩn hóa Unicode. Quy tắc so sánh còn phụ thuộc collation, kiểu index và DBMS. Nếu ứng dụng yêu cầu email không phân biệt chữ hoa, hãy thiết kế bước chuẩn hóa hoặc ràng buộc phù hợp với DBMS, rồi thử dữ liệu như `A@example.com` và `a@example.com`.

`autoIncrement: true` yêu cầu cơ chế tăng tự động qua Liquibase. Hành vi cụ thể có thể là identity/sequence/cơ chế khác theo DBMS và phiên bản. Trước khi dùng cho dữ liệu quy mô lớn, xác định dải giá trị của `BIGINT`, chiến lược sinh khóa, hành vi khi import dữ liệu có id sẵn và cách ứng dụng nhận id mới. Không tự suy luận rằng hệ quản trị nào cũng cho phép kết hợp `autoIncrement` với mọi kiểu cột.

`defaultValueComputed: CURRENT_TIMESTAMP` được Liquibase xử lý như một biểu thức database thay vì chuỗi văn bản `"CURRENT_TIMESTAMP"`. Tuy nhiên `TIMESTAMP` đơn thuần không mang cùng ý nghĩa timezone trên mọi DBMS. Với dữ liệu thời điểm tuyệt đối, cần thống nhất cách lưu và truy xuất UTC, chọn kiểu DBMS thích hợp khi cần (ví dụ PostgreSQL `TIMESTAMP WITH TIME ZONE`), và kiểm tra behavior của JDBC/ORM.

### 3.2. Vai trò của precondition và rollback

Precondition `not: tableExists` giúp dừng có chủ đích nếu bảng đã tồn tại. `onFail: HALT` là lựa chọn phù hợp khi việc bảng tồn tại có thể cho thấy schema đã bị tạo ngoài luồng hoặc migration đã bị áp dụng không đồng nhất. **Đừng tự động dùng `MARK_RAN` để bỏ qua thay đổi chưa được kiểm chứng**, vì bảng có cùng tên không nhất thiết có đúng cột, kiểu dữ liệu và ràng buộc.

Rollback `dropTable` được khai báo tường minh để minh họa cách đảo ngược việc tạo bảng. Nó xóa luôn dữ liệu đã tích lũy trong bảng; nếu các bảng khác có khóa ngoại tham chiếu vào bảng, thao tác xóa còn có thể thất bại hoặc cần xử lý phụ thuộc. Chỉ thực hành rollback này ở database thử nghiệm có thể tạo lại hoặc khi đã xác định chắc chắn được phép mất dữ liệu.

## 4. Chọn kiểu dữ liệu từ ý nghĩa nghiệp vụ

Kiểu dữ liệu không chỉ quyết định dung lượng lưu trữ mà còn quyết định miền giá trị hợp lệ, phép toán, hành vi sắp xếp, index và chuyển đổi qua JDBC. Một bảng hướng dẫn thực hành:

| Nhu cầu | Kiểu thường gặp trong Liquibase | Lưu ý thiết kế |
|---|---|---|
| Mã số nguyên | `INTEGER`, `BIGINT` | Chọn theo dải giá trị và tuổi thọ hệ thống; không dùng số nếu cần giữ số 0 đầu |
| Mã nghiệp vụ, tên, email | `VARCHAR(n)` | Chọn độ dài hợp lý; cân nhắc Unicode, collation và normalization |
| Văn bản dài | `CLOB` hoặc kiểu văn bản riêng DBMS | So sánh hỗ trợ/giới hạn và khả năng index; không biến mọi chuỗi thành cột văn bản không giới hạn |
| Tiền và số thập phân chính xác | `DECIMAL(p,s)` / `NUMERIC(p,s)` | Chọn precision `p`, scale `s` theo miền dữ liệu; xác định cách làm tròn |
| Số đo gần đúng | `FLOAT`, `DOUBLE` | Phù hợp một số bài toán khoa học; không ưu tiên cho tiền hoặc số cần tính đúng tuyệt đối |
| Cờ bật/tắt | `BOOLEAN` | Một số DBMS ánh xạ khác nhau hoặc cần biểu diễn bằng số/bit |
| Ngày lịch | `DATE` | Lưu ngày không kèm giờ; phù hợp ngày sinh, hạn theo lịch |
| Giờ trong ngày | `TIME` | Cần xác định có timezone hay không; hỗ trợ phụ thuộc DBMS |
| Thời điểm | `TIMESTAMP` và biến thể DBMS | Phân biệt thời điểm tuyệt đối với giờ địa phương; kiểm tra quy tắc timezone |
| Dữ liệu nhị phân | `BLOB`, `VARBINARY` hoặc kiểu DBMS | Cân nhắc kích thước dữ liệu và lưu trữ object ngoài database |
| Định danh UUID | `UUID` hoặc kiểu ký tự/binary phù hợp | Không phải DBMS nào cũng hỗ trợ cùng kiểu native; chọn cách sinh và lưu nhất quán |
| Dữ liệu JSON | `JSON`, `JSONB` hoặc kiểu khác theo DBMS | Là kiểu đặc thù; kiểm tra extension, index và đường nâng cấp khi đổi DBMS |

Liquibase có một số kiểu dữ liệu tổng quát được ánh xạ theo DBMS, nhưng **không phải mọi tên kiểu hay tính năng đều portable**. Chẳng hạn, PostgreSQL có `JSONB`, còn nhiều DBMS khác có cơ chế JSON khác biệt. Nếu dùng kiểu DBMS-specific, ghi rõ ràng lựa chọn đó trong tài liệu migration, dùng `dbms`/precondition khi cần và kiểm thử trên đúng engine.

### 4.1. `VARCHAR(n)` và độ dài thực tế

Chọn độ dài cột dựa trên giới hạn nghiệp vụ, không theo cảm giác. Một tên người hoặc địa chỉ có thể dài hơn dự tính. Những DBMS khác nhau có cách xử lý ký tự và byte, collation và Unicode khác nhau. Đặc biệt với tiếng Việt, emoji và dữ liệu quốc tế, đừng mặc định `VARCHAR(100)` luôn cho phép cùng lượng byte lưu trữ trên mọi engine.

Ví dụ:

```yaml
- column:
    name: external_customer_code
    type: VARCHAR(24)
    constraints:
      nullable: false
```

`external_customer_code` có thể chứa `"00001234"`: đó là **mã** chứ không phải số để cộng trừ. Dùng `VARCHAR`, và khi nạp dữ liệu hãy khai báo `value: "00001234"` thay vì `valueNumeric`.

### 4.2. `DECIMAL(p,s)` và số thực gần đúng

Với `DECIMAL(19,4)`, `p` là tổng số chữ số thập phân có thể biểu diễn, `s` là số chữ số sau dấu thập phân theo kiểu đã chọn. Kiểu này phù hợp với các giá trị cần độ chính xác thập phân cố định như giá tiền, nhưng phải xác định nghiệp vụ cần bao nhiêu chữ số nguyên và thập phân, có số âm hay không, và quy tắc làm tròn ở cả Java lẫn database.

Trong ứng dụng Java, giá trị tiền thường được xử lý bằng `BigDecimal`, không bằng `double` nếu cần bảo toàn phép tính thập phân. Kiểu SQL và kiểu Java phải được chọn nhất quán. Nếu nghiệp vụ dùng đơn vị nhỏ nhất (ví dụ số xu), cũng có thể lưu số nguyên và quy định rõ đơn vị; khi đó cần đánh giá overflow và chuyển đổi.

### 4.3. Ngày, giờ và múi giờ

`DATE` phù hợp cho một ngày lịch không gắn thời điểm; `TIMESTAMP` mô tả ngày giờ nhưng ý nghĩa timezone tùy engine và biến thể kiểu. Dữ liệu `created_at` thường là **thời điểm sự kiện**. Quy định rõ timestamp do ai tạo, dùng timezone nào khi ghi, lưu trữ và trả qua API. Nếu hệ thống phân tán nhiều vùng giờ, kiểm thử đường đi từ Java/JDBC đến database trước khi quyết định kiểu cuối cùng.

Không lưu ngày giờ dưới `VARCHAR` chỉ vì dễ hiển thị. Chuỗi có thể trông giống ISO 8601 nhưng khác offset hoặc độ chính xác, gây lỗi so sánh và sắp xếp. `defaultValueComputed: CURRENT_TIMESTAMP` là một biểu thức SQL phụ thuộc database; không phải giá trị thời gian cố định tại lúc build changelog.

## 5. `constraints` và giá trị mặc định: tránh nhầm nghĩa

Trong `createTable`, các thuộc tính khai báo cấu trúc khác với giá trị được ghi khi chạy DML:

| Thuộc tính | Tác dụng |
|---|---|
| `constraints.nullable: false` | Cột không chấp nhận `NULL` |
| `constraints.primaryKey: true` | Cột là một phần khóa chính |
| `constraints.primaryKeyName` | Đặt tên khóa chính nếu được change type/DBMS hỗ trợ |
| `constraints.unique: true` | Đề nghị ràng buộc duy nhất; ngữ nghĩa liên quan đến `NULL` và collation tùy DBMS |
| `constraints.uniqueConstraintName` | Đặt tên ràng buộc unique |
| `autoIncrement: true` | Yêu cầu database tạo giá trị tự tăng cho cột |
| `defaultValue` | Giá trị mặc định dạng chuỗi cho cột |
| `defaultValueNumeric` | Giá trị mặc định dạng số |
| `defaultValueBoolean` | Giá trị mặc định boolean |
| `defaultValueComputed` | Biểu thức database dùng làm mặc định |

Ví dụ phân biệt **default** với **giá trị insert**:

```yaml
# Trích đoạn nằm bên trong createTable.columns
- column:
    name: active
    type: BOOLEAN
    defaultValueBoolean: true
    constraints:
      nullable: false
```

Khi một hàng mới được insert mà không cung cấp giá trị `active`, database có thể dùng default `true`. Nhưng khi bạn viết một changeset `insert` với `valueBoolean: false`, đó là giá trị thực tế cho hàng được chèn, không phải thay đổi default của schema. Tương tự, `defaultValue: "0"` có ý nghĩa chuỗi, khác với `defaultValueNumeric: 0` về cách Liquibase xử lý giá trị.

`nullable: false` không tương đương với ràng buộc giá trị hợp lệ của nghiệp vụ. Một cột `balance DECIMAL` không chấp nhận null vẫn có thể lưu giá trị âm nếu không có điều kiện bổ sung. Khi cần kiểm soát miền giá trị, cân nhắc check constraint hoặc cơ chế riêng của DBMS, kiểm chứng SQL và không dựa hoàn toàn vào validation ở application.

## 6. Khóa chính, khóa duy nhất và quan hệ giữa bảng

**Primary key** định danh duy nhất mỗi hàng. Một bảng thông thường nên có khóa chính rõ ràng để thao tác update/delete chính xác, tham chiếu qua foreign key và phối hợp ORM. **Unique constraint** đảm bảo một giá trị hoặc tổ hợp giá trị không trùng theo ngữ nghĩa DBMS, nhưng không thay thế primary key một cách tự động.

Với khóa chính một cột, cách khai báo trực tiếp trong `createTable` như ví dụ `id` ở trên thường đơn giản. Với khóa chính tổng hợp (ví dụ `(order_id, line_no)`), có thể tạo bảng rồi khai báo `addPrimaryKey` trong **cùng changeset** để diễn đạt rõ tổ hợp khóa:

```yaml
databaseChangeLog:
  - changeSet:
      id: "002-create-order-line"
      author: "db-team"
      changes:
        - createTable:
            tableName: order_line
            columns:
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: line_no
                  type: INTEGER
                  constraints:
                    nullable: false
              - column:
                  name: quantity
                  type: INTEGER
                  constraints:
                    nullable: false
        - addPrimaryKey:
            tableName: order_line
            columnNames: order_id, line_no
            constraintName: pk_order_line
      rollback:
        - dropTable:
            tableName: order_line
```

Lưu ý: khai báo `addPrimaryKey` là một change type khác, chạy **sau** `createTable` trong cùng changeset. Ở ví dụ này, khóa chính tổng hợp ngăn hai dòng cùng `(order_id, line_no)`, nhưng chưa kiểm tra `quantity > 0`; đó là ràng buộc nghiệp vụ riêng. Nếu cần foreign key từ `order_line.order_id` sang một bảng đơn hàng, sử dụng change type `addForeignKeyConstraint` sau khi bảng cha tồn tại, và xem xét tác động của rollback phụ thuộc.

Đừng chọn khóa chính là một thông tin nghiệp vụ dễ thay đổi như email hay tên người chỉ vì giá trị đó đang unique. Nếu dùng surrogate key, vẫn cần unique constraint riêng cho những giá trị nghiệp vụ bắt buộc duy nhất.

## 7. Tạo bảng ở schema xác định và quản lý tên đối tượng

Liquibase hỗ trợ chỉ định `schemaName` ở một số change type, ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-create-audit-entry"
      author: "db-team"
      changes:
        - createTable:
            schemaName: app
            tableName: audit_entry
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: audit_entry
```

Ví dụ giả định schema `app` **đã tồn tại** và tài khoản Liquibase có quyền tạo bảng trong schema đó. Nếu bạn không chỉ định schema, kết quả còn phụ thuộc schema mặc định, search path, cấu hình Liquibase và DBMS. Việc `schemaName` xuất hiện trong changelog không tự tạo schema hay cấp quyền cho user.

Không dùng tên bảng/cột trùng từ khóa của SQL như `user`, `order` nếu có thể tránh; không trộn chữ hoa và chữ thường tùy tiện. Quy tắc quote identifier khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Chọn tên rõ nghĩa (`customer_account`, `order_line`), dùng nhất quán các tên ràng buộc và đánh giá giới hạn độ dài tên identifier của DBMS.

Trong ứng dụng chạy nhiều môi trường, cấu trúc changelog nên giống nhau; những phần thực sự thay đổi theo môi trường là JDBC URL, schema mục tiêu, tài khoản và secret. Nếu cần parameter hóa `schemaName`, kiểm tra giá trị đã phân giải, quyền truy cập và tính nhất quán của rollback. Không biến mọi tên bảng thành tham số chỉ để tránh thiết kế schema ngay từ đầu.

## 8. Những sai lầm phổ biến khi viết YAML tạo bảng

### 8.1. Thụt dòng sai cấp

**Sai:**

```yaml
changes:
  - createTable:
      tableName: customer_account
    columns:
      - column:
          name: id
          type: BIGINT
```

Trong cấu trúc trên, `columns` không nằm bên trong `createTable` theo đúng mức thụt. Một YAML parser có thể đọc được file nhưng Liquibase không nhận cấu trúc như dự định.

**Đúng:**

```yaml
changes:
  - createTable:
      tableName: customer_account
      columns:
        - column:
            name: id
            type: BIGINT
```

### 8.2. Nhầm danh sách cột với mapping

**Sai:**

```yaml
columns:
  column:
    name: id
    type: BIGINT
  column:
    name: email
    type: VARCHAR(255)
```

Ở đây `column` xuất hiện hai lần như khóa trùng nhau trong một mapping; có YAML parser từ chối, có parser bỏ qua một giá trị. **Đúng** là mỗi cột có `- column:` riêng trong sequence. Không phụ thuộc vào hành vi ghi đè khóa trùng.

### 8.3. Nhầm null, default và chuỗi

- `nullable: false` là thuộc tính ràng buộc của cột, không phải giá trị ban đầu.
- `defaultValue: "false"` là giá trị dạng chuỗi; `defaultValueBoolean: false` là giá trị boolean.
- `"00123"` là chuỗi có số 0 đầu; `00123` không nên được dựa vào để giữ nguyên chữ số dưới các YAML parser.
- `defaultValueComputed: CURRENT_TIMESTAMP` là biểu thức database; `defaultValue: "CURRENT_TIMESTAMP"` không có cùng ý nghĩa.
- `value`/`valueNumeric`/`valueDate` là những thuộc tính dùng trong các change type thao tác dữ liệu như `insert`; không dùng thay `type` khi tạo cột.

### 8.4. Cố tạo lại bảng đã có

Nếu một changeset đã chạy thành công và được ghi trong `DATABASECHANGELOG`, Liquibase bình thường sẽ không chạy lại changeset đó. Nhưng nếu bảng được tạo thủ công ngoài Liquibase, changeset chưa được ghi lịch sử có thể thất bại với lỗi bảng đã tồn tại. Precondition giúp phát hiện trạng thái này; nó không tự đối chiếu rằng schema thực tế hoàn toàn tương thích với kỳ vọng. Đừng xóa lịch sử hoặc dùng `MARK_RAN` chỉ để làm lệnh `update` báo xanh.

## 9. Tránh phá dữ liệu khi sửa cấu trúc bảng đã triển khai

Tạo một bảng mới thường dễ hơn thay đổi bảng có hàng triệu bản ghi. Sau khi bảng đã tồn tại ở staging hoặc production, **không sửa trực tiếp nội dung changeset tạo bảng cũ để thêm cột**. Liquibase lưu checksum của changeset đã chạy; chỉnh cấu trúc có thể gây lỗi kiểm tra, đồng thời làm lịch sử giữa các môi trường khác nhau.

Ví dụ, nếu sau này cần thêm cột `phone_number`, hãy tạo changeset mới:

```yaml
databaseChangeLog:
  - changeSet:
      id: "004-add-customer-phone"
      author: "db-team"
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: phone_number
                  type: VARCHAR(32)
      rollback:
        - dropColumn:
            tableName: customer_account
            columnName: phone_number
```

Ví dụ `addColumn` là phần mở rộng tự nhiên sau bài tạo bảng, không phải thay thế `createTable`. Khi thêm một cột bắt buộc vào bảng đã có dữ liệu, đừng áp dụng ngay `nullable: false` nếu các hàng cũ chưa có giá trị. Cách tiếp cận thường là:

1. Thêm cột có thể null hoặc có default đã được xem xét tác động.
2. Backfill giá trị cho dữ liệu cũ theo lô và kiểm tra trạng thái.
3. Đổi ứng dụng để ghi giá trị mới ổn định.
4. Thêm `NOT NULL` trong changeset tiếp theo sau khi dữ liệu đáp ứng điều kiện.

Tách các giai đoạn giúp giảm rủi ro lock và cho phép kiểm soát sự tương thích giữa các phiên bản ứng dụng. Với hệ thống có tải cao, đánh giá thời gian DDL, transaction, lock, backup và phương án forward-fix theo DBMS cụ thể.

## 10. Kiểm chứng thay đổi bảng trước khi chạy thật

Giả sử bạn đã cấu hình kết nối trong `liquibase.properties`, đã đưa changelog mẫu vào file master phù hợp, và CLI có JDBC driver. Thực hiện lần lượt:

```bash
# Kiểm tra cú pháp và cấu trúc changelog, đối chiếu metadata lịch sử
liquibase --defaults-file=liquibase.properties validate

# Xem những changeset còn chờ chạy
liquibase --defaults-file=liquibase.properties status

# Xem SQL dự kiến, không thực thi DDL
liquibase --defaults-file=liquibase.properties update-sql

# Chỉ chạy trên database thử nghiệm sau khi đã review SQL
liquibase --defaults-file=liquibase.properties update
```

Trong `update-sql`, kiểm tra ít nhất: tên schema/bảng, loại khóa tự tăng, tên ràng buộc, `NOT NULL`, `UNIQUE`, precision/scale của `DECIMAL`, kiểu timestamp, biểu thức mặc định và những câu DDL đặc thù DBMS. `validate` không chứng minh rằng DDL có thể chạy trên database thật hoặc thỏa mọi quy tắc nghiệp vụ.

Sau khi chạy ở database thử nghiệm, kiểm tra cấu trúc và dữ liệu. Với PostgreSQL, ví dụ:

```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer_account'
ORDER BY ordinal_position;

SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
WHERE id = '001-create-customer-account';
```

Nếu bạn triển khai bảng trong schema `app` thay vì `public`, phải đổi điều kiện truy vấn cho đúng schema. Khi dùng DBMS khác, chọn catalog hoặc metadata view phù hợp. Bảng `DATABASECHANGELOG` chứa thông tin lịch sử và checksum; nó không thay thế kiểm chứng schema hiện có bằng metadata DBMS.

Chạy lại `update` để kiểm tra tính lặp an toàn ở cấp changeset: nếu không có changeset mới, Liquibase không nên thực thi lại `createTable` đã ghi nhận thành công. Nếu phát sinh lỗi checksum, khác biệt đường dẫn changelog hoặc lịch sử bất thường, dừng triển khai để tìm nguyên nhân thay vì tự xóa checksum hay sửa bảng metadata.

## 11. Đưa thay đổi bảng qua Spring Boot và CI/CD

Changelog nên là một tài nguyên được quản lý phiên bản và đóng gói cùng artifact migration. Ví dụ trong Spring Boot:

```text
src/main/resources/
└── db/changelog/
    ├── master.yaml
    └── changes/
        ├── 001-create-customer-account.yaml
        └── 004-add-customer-phone.yaml
```

File master có thể dùng `include`:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer-account.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-add-customer-phone.yaml
      relativeToChangelogFile: true
```

Và cấu hình Spring Boot:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Khi đổi từ CLI sang Spring Boot hoặc thay đổi cấu trúc đường dẫn, cần giữ định danh changeset nhất quán: Liquibase nhận diện changeset theo `id`, `author` và đường dẫn file changelog (hoặc `logicalFilePath` được cấu hình). Việc đổi đường dẫn vật lý có thể khiến một changeset cũ bị nhận diện thành mới. Với database đã có lịch sử, đối chiếu `FILENAME` trong `DATABASECHANGELOG` trước khi đổi cách đóng gói.

Trong CI/CD, pipeline nên cố định phiên bản Liquibase và driver, dùng secret manager cho thông tin kết nối, chạy `validate`, xem `update-sql`, thử migration trên database tương đương production và chỉ thực thi `update` sau bước phê duyệt thích hợp. Không để cả job CLI và ứng dụng Spring Boot tự chạy cùng migration một cách thiếu kiểm soát. Cơ chế khóa của Liquibase giúp phối hợp thực thi, nhưng không giải quyết thay cho kế hoạch triển khai hay kiểm tra đúng database đích.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `createTable` hoặc `columns` không được nhận diện | YAML sai cấp hoặc thiếu dấu `-` | Kiểm tra sequence, mapping; chạy `validate` |
| Tên bảng đã tồn tại | Bảng tạo ngoài lịch sử Liquibase hoặc changeset bị nhận diện lại | Kiểm tra schema thực và `DATABASECHANGELOG`; không bỏ qua bừa bãi |
| Kiểu dữ liệu không được DBMS hỗ trợ | Dùng kiểu đặc thù, version engine khác hoặc driver không phù hợp | Xem `update-sql`, kiểm tra type mapping và DBMS mục tiêu |
| Lỗi permission/schema | User thiếu quyền `CREATE`/`USAGE`, schema chưa tồn tại hoặc default schema sai | Kiểm tra JDBC URL, schema và quyền migration |
| Lỗi `NOT NULL`/unique | Dữ liệu thực tế không đáp ứng ràng buộc | Kiểm tra dữ liệu và thứ tự thêm ràng buộc; cân nhắc backfill |
| Giá trị tiền làm tròn sai | Chọn `FLOAT`, scale không đủ hoặc ứng dụng dùng kiểu gần đúng | Xác nhận `DECIMAL(p,s)` và kiểu Java xử lý |
| Khóa tự tăng không hoạt động như mong đợi | Khác biệt identity/sequence/DBMS | Kiểm tra SQL sinh ra và hành vi insert/return id |
| Timestamp lệch giờ | Không thống nhất timezone, kiểu cột hoặc timezone session | Kiểm tra Java/JDBC/DBMS và chuẩn UTC đã chọn |
| Checksum validation failed | Changeset đã chạy bị sửa hoặc cách nạp file thay đổi | So sánh nội dung gốc, định danh và lịch sử trước khi xử lý |
| Rollback xóa mất dữ liệu | Dùng `dropTable` trên bảng đã có dữ liệu | Đánh giá kế hoạch backup/forward-fix; thử rollback ở database riêng |

## 13. Bài tập thực hành và tiêu chí nghiệm thu

Trên một database có thể tạo lại, hãy thực hiện theo thứ tự:

1. Thiết kế bảng `customer_account` theo ví dụ ở mục 3, xác định vì sao mỗi cột có kiểu và constraint đó.
2. Chạy `validate`; chạy `update-sql` và so sánh SQL với các thuộc tính YAML (`BIGINT`, `VARCHAR`, `DECIMAL`, `BOOLEAN`, timestamp, default, unique).
3. Chạy `update`; kiểm tra bảng có đủ các cột và ràng buộc; thử insert một hàng chỉ cung cấp email để xem cách xử lý default của những cột khác.
4. Thử insert hai hàng có email trùng nhau và giải thích lỗi unique. Thử insert email null để kiểm tra `NOT NULL`.
5. Kiểm tra `DATABASECHANGELOG`; chạy lại `update` và xác nhận changeset tạo bảng không chạy lần hai.
6. Tạo changeset mới `addColumn` cho số điện thoại; không sửa changeset tạo bảng đã chạy.
7. Thử rollback trên database riêng và xác minh tác động xóa bảng/cột; không thử lệnh phá hủy trên dữ liệu cần giữ.
8. Nếu dự án cần hỗ trợ thêm DBMS, xem trước SQL cho DBMS đó và ghi nhận những điểm không portable như auto increment, timestamp hoặc JSON.

### Checklist trước khi đưa migration tạo bảng vào pull request

- [ ] Mỗi bảng có mục đích rõ ràng, tên nhất quán và chính sách schema đã xác định.
- [ ] Khóa chính được chọn theo tính ổn định, khả năng mở rộng và cách sinh giá trị.
- [ ] Kiểu số, chuỗi, tiền, ngày giờ được chọn theo miền giá trị nghiệp vụ.
- [ ] Có độ dài/precision/scale cụ thể khi cần; không dùng `FLOAT` cho dữ liệu tiền chính xác.
- [ ] Mọi `nullable`, `unique`, `default` và tên constraint được review.
- [ ] Changelog YAML có `databaseChangeLog`, `changeSet`, `changes`, `columns` đúng cấp.
- [ ] Có kế hoạch phát hiện bảng đã tồn tại và xử lý lịch sử ngoài luồng.
- [ ] `validate` thành công, SQL preview được xem trên DBMS mục tiêu.
- [ ] Migration và rollback đã được thử ở database có thể tạo lại.
- [ ] Changelog và thay đổi schema đã triển khai không bị sửa trực tiếp; bổ sung changeset mới khi nâng cấp.
- [ ] Đường dẫn, phiên bản và cách gọi Liquibase nhất quán giữa máy phát triển, Spring Boot và CI/CD.

**Kết luận:** `createTable` giúp biểu diễn việc tạo bảng một cách có phiên bản, nhưng chất lượng migration phụ thuộc vào thiết kế cột, chọn kiểu dữ liệu, ràng buộc và cách xác minh kết quả. Hãy dùng Liquibase để giữ một lịch sử thay đổi minh bạch, chọn kiểu theo nghĩa dữ liệu và DBMS thực tế, xem SQL trước khi chạy, rồi bổ sung changeset mới thay vì sửa lịch sử đã triển khai. Đó là nền tảng cho những migration có kiểm chứng và rollback có trách nhiệm trong `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`.
