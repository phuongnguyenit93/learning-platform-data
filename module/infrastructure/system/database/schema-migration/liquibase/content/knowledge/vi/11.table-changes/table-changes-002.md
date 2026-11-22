# Ánh xạ kiểu dữ liệu giữa Liquibase và hệ quản trị

Khi viết `type: VARCHAR(100)`, `type: DECIMAL(19,4)` hoặc `type: BOOLEAN` trong một changelog Liquibase, ta đang mô tả **ý định lưu trữ dữ liệu**. Liquibase phải biến ý định đó thành SQL hợp lệ với hệ quản trị cơ sở dữ liệu (DBMS) đang kết nối. Cùng một changeset có thể sinh những tên kiểu, câu lệnh DDL và cách biểu diễn dữ liệu khác nhau trên PostgreSQL, MySQL, Oracle Database hay SQL Server. Vì vậy, **chạy thành công cùng một changelog không đồng nghĩa mọi database có cấu trúc và ngữ nghĩa hoàn toàn giống nhau**.

Bài học thuộc chương **Thay đổi bảng** của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Riêng bài này tập trung vào **ánh xạ kiểu dữ liệu**: chọn kiểu chung hay kiểu riêng DBMS, hiểu hậu quả của việc chuyển đổi và kiểm chứng schema thực tế sau migration.

## 1. Ba tầng kiểu dữ liệu

Một hệ thống Java dùng Liquibase thường có ba tầng ánh xạ:

1. **Kiểu ứng dụng:** `String`, `Long`, `BigDecimal`, `LocalDate`, `Instant`, `Boolean`, `UUID`.
2. **Kiểu khai báo trong changelog:** `VARCHAR(80)`, `BIGINT`, `DECIMAL(19,4)`, `DATE`, `TIMESTAMP`, `BOOLEAN`, đôi khi là kiểu chuyên biệt như `JSONB`.
3. **Kiểu vật lý DBMS:** ví dụ `VARCHAR2` hoặc `NUMBER` của Oracle, `NUMERIC` hoặc `BYTEA` của PostgreSQL, `DATETIME2` hoặc `BIT` của SQL Server.

~~~mermaid
flowchart TD
    A["Java: BigDecimal amount"] --> B["Liquibase: DECIMAL(19,4)"]
    B --> C["PostgreSQL: NUMERIC(19,4)"]
    B --> D["MySQL: DECIMAL(19,4)"]
    B --> E["Oracle: NUMBER(19,4)"]
    B --> F["SQL Server: DECIMAL(19,4)"]
    C --> G["JDBC driver đọc/ghi giá trị"]
    D --> G
    E --> G
    F --> G
    G --> H["Java: BigDecimal"]
~~~

Sơ đồ nêu các cách biểu diễn thường gặp, **không phải cam kết SQL chính xác** của mọi phiên bản Liquibase. Phiên bản Liquibase Core, driver JDBC, extension, cấu hình và phiên bản server có thể ảnh hưởng kết quả. Liquibase chịu trách nhiệm phân tích changelog và sinh SQL; JDBC chịu trách nhiệm giao tiếp và chuyển giá trị lúc ứng dụng đọc/ghi.

### 1.1. Kiểu chung và kiểu native

- **Kiểu chung** (`BIGINT`, `VARCHAR(80)`, `DECIMAL(19,4)`, `BOOLEAN`, `TIMESTAMP`): nên ưu tiên khi muốn dùng cùng một định nghĩa changelog cho nhiều DBMS. Liquibase áp dụng quy tắc chuyển đổi mà engine/database integration hỗ trợ.
- **Kiểu native** (`JSONB`, `NVARCHAR2(100)`, `DATETIME2(6)`, `VARBINARY(MAX)`, các kiểu do extension cung cấp): diễn đạt một tính năng riêng, có thể không tồn tại trên DBMS khác.

Liquibase hỗ trợ tính di động của **khai báo migration** nhưng không đảm bảo mọi cơ chế DDL, kiểu dữ liệu hoặc hàm SQL trên các DBMS có ý nghĩa tương đương.

## 2. Bảng đối chiếu các nhóm kiểu

Bảng chỉ đưa ra **dạng SQL điển hình** để thấy khác biệt; không phải ma trận ánh xạ chính thức cho mọi phiên bản Liquibase. Phải xem SQL thực tế do đúng bản Liquibase và DBMS đích sinh ra.

| Ý định lưu trữ | Kiểu trong Liquibase | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|---|
| Số nguyên | `INT` | `INTEGER` | `INT` | `INT` | Thường một dạng `NUMBER` có precision phù hợp |
| Số nguyên lớn | `BIGINT` | `BIGINT` | `BIGINT` | `BIGINT` | Thường một dạng `NUMBER` có precision phù hợp |
| Số thập phân chính xác | `DECIMAL(19,4)` | `NUMERIC(19,4)` | `DECIMAL(19,4)` | `DECIMAL(19,4)` | `NUMBER(19,4)` |
| Chuỗi giới hạn | `VARCHAR(120)` | `VARCHAR(120)` | `VARCHAR(120)` | `VARCHAR(120)` | `VARCHAR2(120)` |
| Chuỗi Unicode theo loại riêng | `NVARCHAR(120)` khi hỗ trợ | Thường dùng `VARCHAR` trên DB UTF-8 | Phụ thuộc charset/collation | `NVARCHAR(120)` | `NVARCHAR2(120)` |
| Boolean | `BOOLEAN` | `BOOLEAN` | Thường `TINYINT(1)` | `BIT` | Tùy đời DBMS; hệ cũ thường dùng `NUMBER(1)` |
| Ngày lịch | `DATE` | `DATE` | `DATE` | `DATE` | `DATE` có thể chứa cả phần giờ |
| Ngày giờ | `TIMESTAMP` hoặc `DATETIME` | `TIMESTAMP` | `DATETIME`/`TIMESTAMP` có khác biệt semantics | `DATETIME2`/`DATETIME` | `TIMESTAMP` |
| Văn bản lớn | `CLOB` | Thường `TEXT` | Một dạng `TEXT`/`LONGTEXT` | `VARCHAR(MAX)` hoặc `NVARCHAR(MAX)` | `CLOB` |
| Nhị phân lớn | `BLOB` | Thường `BYTEA` | Một dạng `BLOB` | `VARBINARY(MAX)` | `BLOB` |

Những khác biệt cần nhớ:

- Oracle trong nhiều phiên bản trước khi hỗ trợ kiểu `BOOLEAN` SQL native không có boolean SQL giống PostgreSQL; khi triển khai thật phải kiểm tra DBMS và bản Liquibase cụ thể.
- `DATE` trên Oracle có thể chứa thành phần giờ, khác giả định “ngày không có giờ” ở nhiều DBMS khác.
- `TIMESTAMP` không mặc định có múi giờ và không mặc định có cùng độ chính xác phần giây.
- `NVARCHAR`, `VARCHAR` và `CLOB` không chỉ khác độ dài: chúng còn ảnh hưởng charset, collation, indexing và JDBC.
- Một số kiểu native không nằm trong tập ánh xạ portable; Liquibase có thể chuyển nguyên tên kiểu vào SQL, và DBMS khác sẽ từ chối.

## 3. Kiểu số: phạm vi, precision và scale

### 3.1. INT và BIGINT

`INT` thường biểu diễn số nguyên có phạm vi nhỏ hơn `BIGINT`. PostgreSQL, MySQL và SQL Server có kiểu số nguyên native; Oracle thường dùng `NUMBER` với độ chính xác phù hợp. Không thể kết luận mọi DBMS sẽ chấp nhận chính xác cùng một tập giá trị chỉ từ tên kiểu trong changelog.

Ứng dụng Java thường dùng `Integer` cho số nguyên 32 bit và `Long` cho số nguyên 64 bit. Nếu ID sắp vượt phạm vi cột `INT`, chỉ thay `Integer` thành `Long` trong entity chưa đủ: cần kiểm tra kiểu cột, identity/sequence, foreign key, index và các cột tham chiếu.

### 3.2. DECIMAL(p,s)

Với `DECIMAL(p,s)`:

- `p` (*precision*) là tổng số chữ số.
- `s` (*scale*) là số chữ số ở bên phải dấu thập phân.
- `DECIMAL(19,4)` là giá trị thập phân có tối đa 19 chữ số, trong đó 4 chữ số thuộc phần thập phân theo quy tắc của DBMS.

Ví dụ một cột tiền tệ trong `createTable`:

~~~yaml
- column:
    name: total_amount
    type: DECIMAL(19,4)
    constraints:
      nullable: false
~~~

Đây là một phần tử trong danh sách `columns`, chưa phải changelog độc lập. Trên ứng dụng Java, nên dùng `BigDecimal` và quy tắc `RoundingMode` có chủ đích nếu nghiệp vụ đòi hỏi số thập phân chính xác. Dùng `FLOAT` hoặc `DOUBLE` để biểu diễn tiền có thể tạo sai lệch do nhiều phân số thập phân không thể lưu chính xác dưới dạng dấu phẩy động nhị phân.

### 3.3. Đổi precision/scale có thể mất dữ liệu

Đổi `DECIMAL(19,4)` thành `DECIMAL(12,2)` có hai tác động: giảm phạm vi số nguyên và giảm số chữ số thập phân. Một số giá trị sẽ bị làm tròn, không biểu diễn được hoặc khiến câu DDL thất bại. Trước khi thay đổi phải thống kê dữ liệu hiện có, thiết kế làm tròn và kiểm tra ứng dụng/JDBC.

Mặt khác, mở rộng precision không có nghĩa lệnh DDL không khóa bảng. Kiểm tra thời gian thực thi và hành vi của đúng phiên bản DBMS vẫn là bắt buộc.

## 4. Chuỗi: VARCHAR, Unicode và collation

### 4.1. Độ dài theo byte hay ký tự?

`VARCHAR(100)` **không luôn có nghĩa giống nhau** trên mọi DBMS:

- Một số loại và cấu hình giới hạn theo **số ký tự**; số byte dùng để lưu UTF-8 có thể lớn hơn.
- Oracle có ngữ nghĩa độ dài `BYTE`/`CHAR` tùy cấu hình và cách khai báo.
- SQL Server phân biệt `VARCHAR` và `NVARCHAR`; encoding và sức chứa Unicode cần được kiểm tra.
- MySQL chịu ảnh hưởng charset và collation của database, bảng hoặc cột.

Với dữ liệu tiếng Việt, hãy test chuỗi có dấu, emoji, ký tự kết hợp và độ dài ở biên. Một cột được tạo thành công vẫn có thể từ chối giá trị thật khi runtime.

### 4.2. CHAR, VARCHAR, NVARCHAR và CLOB

| Kiểu | Đặc tính cần xem xét | Ví dụ |
|---|---|---|
| `CHAR(n)` | Độ dài cố định, có thể padding khoảng trắng. | Mã cố định sau khi xác minh quy tắc so sánh. |
| `VARCHAR(n)` | Chuỗi độ dài biến đổi, có giới hạn. | Email, mã hóa đơn, tên người dùng. |
| `NVARCHAR(n)` | Kiểu chuỗi quốc tế hóa trong DBMS có phân biệt loại chuỗi. | Văn bản Unicode theo quy tắc SQL Server/Oracle. |
| `CLOB`/`TEXT` | Văn bản lớn; thao tác index và hàm SQL có thể khác. | Nội dung mô tả hoặc tài liệu văn bản dài. |

`CLOB` không phải lựa chọn mặc định cho mọi chuỗi chưa rõ độ dài; nó có thể thay đổi chiến lược index, API đọc/ghi và chi phí truy vấn.

### 4.3. Collation ảnh hưởng unique

Hai cột cùng `VARCHAR(100)` có thể so sánh không phân biệt chữ hoa, không phân biệt dấu hoặc phân biệt hoàn toàn tùy collation. Unique index có thể coi `User@example.com` và `user@example.com` là trùng nhau hoặc khác nhau. Liquibase tạo đúng kiểu nhưng **không tự bảo đảm quy tắc so sánh phù hợp nghiệp vụ**.

## 5. Kiểu thời gian: DATE, TIMESTAMP và múi giờ

### 5.1. DATE không luôn giống Java LocalDate

Ngày sinh, ngày hiệu lực hoặc ngày xuất hóa đơn thường là **ngày lịch**, không cần múi giờ. `DATE` là kiểu phù hợp trong nhiều DBMS, nhưng Oracle `DATE` truyền thống còn có phần giờ/phút/giây. Nếu ứng dụng đọc sang `LocalDate`, thông tin giờ có thể bị bỏ qua.

### 5.2. TIMESTAMP không nhất thiết lưu offset

Đối với thời điểm thực:

- PostgreSQL phân biệt `TIMESTAMP WITHOUT TIME ZONE` với `TIMESTAMP WITH TIME ZONE` (`timestamptz`).
- SQL Server có `DATETIME2` và `DATETIMEOFFSET` với semantics khác nhau.
- Oracle có `TIMESTAMP` cùng các biến thể `WITH TIME ZONE`.
- MySQL phân biệt `DATETIME` và `TIMESTAMP`, trong đó cách chuyển timezone và phạm vi giá trị khác nhau.

Không suy ra `type: TIMESTAMP` luôn tương đương Java `Instant`. Cần quy định rõ lưu UTC, local time hay thời điểm kèm offset, cùng timezone của JDBC session và ứng dụng. Với lịch hẹn theo địa phương, đôi khi phải lưu **timezone ID** riêng để xử lý thay đổi DST.

### 5.3. Độ chính xác phần giây

Một cột chỉ giữ millisecond có thể làm tròn hoặc cắt phần microsecond của giá trị đầu vào. Cùng từ khóa `TIMESTAMP` có thể tạo ra precision mặc định khác nhau trên các DBMS. Hãy kiểm thử round-trip (ghi qua JDBC, đọc lại) với thời điểm có phần giây và giá trị gần ranh giới ngày.

## 6. BOOLEAN, UUID, JSON, BLOB và các kiểu đặc thù

### 6.1. BOOLEAN

Về nghiệp vụ, boolean chỉ có đúng/sai. Nhưng DBMS có thể dùng `BOOLEAN`, `BIT` hoặc một dạng số. Khi cột được lưu bằng số và không có constraint phù hợp, giá trị ngoài `0/1` có thể tồn tại dù ứng dụng Java chỉ hiểu `Boolean`.

Ví dụ khai báo trong danh sách cột:

~~~yaml
- column:
    name: is_enabled
    type: BOOLEAN
    defaultValueBoolean: true
    constraints:
      nullable: false
~~~

`defaultValueBoolean` thể hiện ý định boolean thay vì tự viết chuỗi SQL `TRUE`/`FALSE` có thể không portable. Vẫn cần kiểm tra DDL và cách driver chuyển giá trị.

### 6.2. UUID

PostgreSQL có kiểu `UUID` native; database khác có thể lưu UUID ở `CHAR(36)`, dạng nhị phân 16 byte hoặc kiểu native riêng. Lựa chọn ảnh hưởng kích thước index, cách sắp xếp, chuyển đổi JDBC và khả năng migration. Không mặc định `type: UUID` được mọi DBMS hỗ trợ và ánh xạ giống nhau. Quy ước text hay binary phải được thống nhất với ứng dụng.

### 6.3. JSON/JSONB, ENUM, ARRAY

`JSONB` của PostgreSQL, `JSON` của MySQL và các cơ chế JSON của Oracle/SQL Server không có cùng toàn bộ toán tử và khả năng indexing. Các kiểu `ARRAY`, `ENUM`, kiểu địa lý hoặc kiểu do extension cấp thường càng phụ thuộc DBMS.

Chỉ dùng kiểu native khi thật sự cần tính năng của nó. Khi đó khai báo `dbms` phù hợp hoặc có migration riêng cho từng DBMS, và kiểm thử phần ứng dụng dùng JDBC/hàm SQL chuyên biệt. Không giả định một tên kiểu mà Liquibase chấp nhận lúc parse sẽ chạy được ở mọi hệ quản trị.

### 6.4. CLOB và BLOB

`CLOB` lưu văn bản lớn, `BLOB` lưu nhị phân lớn. Khác biệt nằm ở cách lưu, API stream, giới hạn kích thước, sao lưu và lập chỉ mục, không chỉ ở dung lượng. Hãy cân nhắc lưu tệp lớn trong database hay object storage tùy yêu cầu giao dịch và vận hành.

## 7. Kiểu dữ liệu khác constraint, default và identity

| Thuộc tính Liquibase | Vai trò | Không nên suy diễn |
|---|---|---|
| `autoIncrement: true` | Yêu cầu DB sinh khóa tự động khi hỗ trợ. | Không bảo đảm cùng cú pháp `IDENTITY`, `SERIAL` hoặc sequence. |
| `constraints.primaryKey: true` | Định nghĩa primary key. | Không tự chọn kiểu dữ liệu tối ưu. |
| `constraints.nullable: false` | Không cho phép NULL. | Không tự xử lý giá trị NULL đã có trước khi đổi kiểu. |
| `constraints.unique: true` | Ràng buộc duy nhất. | Không quyết định cách so sánh khi collation khác nhau. |
| `defaultValue` | Giá trị mặc định dạng literal. | Không giống biểu thức SQL chạy tại database. |
| `defaultValueComputed` | Biểu thức mặc định khi DBMS hỗ trợ. | Không đảm bảo cùng cú pháp và hàm trên mọi DBMS. |

Kiểu dữ liệu quy định cách lưu giá trị; constraint/default/identity quy định **các luật bổ sung**. Nếu đổi `INT` thành `BIGINT` cho primary key, phải kiểm tra cả sequence/identity, foreign key và các cột tham chiếu, không chỉ sửa một thuộc tính `type`.

## 8. Ví dụ changelog YAML tạo bảng với kiểu chung

Ví dụ thiết kế bảng hóa đơn với số tiền thập phân chính xác, ngày lịch, thời điểm và cờ thanh toán:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-invoice
      author: db-team
      changes:
        - createTable:
            tableName: invoice
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: invoice_code
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: total_amount
                  type: DECIMAL(19,4)
                  constraints:
                    nullable: false
              - column:
                  name: issued_on
                  type: DATE
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
              - column:
                  name: is_paid
                  type: BOOLEAN
                  defaultValueBoolean: false
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: invoice
~~~

Đây là một changelog mẫu hoàn chỉnh về mặt cấu trúc. Tuy vậy, phiên bản Liquibase, DBMS và quy ước ứng dụng sẽ quyết định có cần sửa cú pháp tạo ID, precision cho timestamp hoặc chiến lược unique/collation hay không.

Ý nghĩa của các cột:

- `id`: số nguyên lớn, primary key, do DBMS cấp; cách cấp có thể là identity hoặc sequence.
- `invoice_code`: chuỗi có giới hạn và unique; cần kiểm tra quy tắc Unicode/collation.
- `total_amount`: số thập phân có độ chính xác xác định.
- `issued_on`: ngày nghiệp vụ; `created_at`: ngày giờ ghi nhận, cần quy ước timezone ngoài tên kiểu chung.
- `is_paid`: boolean, mặc định false, không được null.

**Cảnh báo:** rollback ở ví dụ dùng `dropTable` sẽ xóa bảng và **toàn bộ dữ liệu hóa đơn**; không dùng nó trên dữ liệu thật khi chưa có kế hoạch backup/restore và phê duyệt tác động.

## 9. Khi cần kiểu native theo DBMS

Giả sử bảng `event_store` đã tồn tại. Ứng dụng muốn lưu JSON; một hệ thống hỗ trợ cả PostgreSQL và MySQL có thể cần hai cách khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-payload-postgresql
      author: db-team
      dbms: postgresql
      changes:
        - addColumn:
            tableName: event_store
            columns:
              - column:
                  name: payload
                  type: JSONB
  - changeSet:
      id: 003-add-payload-mysql
      author: db-team
      dbms: mysql
      changes:
        - addColumn:
            tableName: event_store
            columns:
              - column:
                  name: payload
                  type: JSON
~~~

`dbms` ở đây là **bộ lọc**: changeset dành cho PostgreSQL không chạy trên MySQL và ngược lại. Changelog mẫu chỉ hỗ trợ hai nhánh này, không tự tạo cột trên Oracle hoặc SQL Server. Do đó cần xác định rõ tập DBMS hỗ trợ và bảo đảm ứng dụng hiểu kiểu payload thực của mỗi DBMS.

Trường hợp dùng SQL native tương tự phải có chiến lược kiểm tra rollback, lịch sử `DATABASECHANGELOG` và nhánh thay thế cho các DBMS khác nếu chúng thuộc phạm vi sản phẩm.

## 10. Xem SQL được sinh trên từng DBMS

Không nên dự đoán SQL chỉ từ tên kiểu. Trong CI hoặc trên máy thử, dùng đúng bộ Liquibase Core/CLI, JDBC driver, extension và kết nối tới database đại diện để kiểm tra:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml validate
liquibase --changelog-file=db/changelog/master.yaml status --verbose
liquibase --changelog-file=db/changelog/master.yaml update-sql
~~~

Cần cung cấp URL JDBC, user và thông tin xác thực từ cấu hình/secret của môi trường; không đưa mật khẩu thật vào changelog. Tên lệnh sinh SQL có thể được viết khác ở một số phiên bản cũ (ví dụ `updateSQL`), nên tra cứu cú pháp của CLI đã khóa.

`validate` kiểm tra cấu trúc và một số quy tắc của changelog, **không bảo đảm** DDL sẽ chạy thành công. `update-sql` tạo SQL dự kiến theo trạng thái hiện tại mà không thực hiện change, nhưng vẫn có thể cần kết nối database để xác định những changeset chưa triển khai và biết loại DBMS.

### 10.1. Đối chiếu metadata sau khi chạy thử

Sau khi chạy `update` trên database thử, dùng metadata để xác minh tên kiểu thực, precision, scale, độ dài và default. Ví dụ PostgreSQL:

~~~sql
SELECT column_name,
       data_type,
       character_maximum_length,
       numeric_precision,
       numeric_scale,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
ORDER BY ordinal_position;
~~~

`information_schema` hữu ích nhưng không bao trùm mọi đặc tính native của từng DBMS như một số kiểu extension, collation, identity hoặc constraint cụ thể. Khi cần, hãy đọc thêm system catalog của đúng DBMS đang dùng.

Kiểm tra thêm:

| Cần kiểm tra | Câu hỏi |
|---|---|
| Kiểu vật lý | Có đúng họ kiểu và chức năng ứng dụng cần? |
| Precision/scale | Có lưu được giá trị biên và không mất số lẻ? |
| Charset/độ dài | Có chứa được tên tiếng Việt và chuỗi Unicode? |
| Date/time/timezone | Có giữ đúng thời điểm, offset, precision giây? |
| Constraint | Nullable, unique, PK, FK có hoạt động đúng? |
| Identity/default | INSERT không truyền cột có tạo giá trị đúng? |
| JDBC round-trip | Java ghi rồi đọc lại có cùng giá trị nghiệp vụ? |

### 10.2. Dữ liệu biên cần thử

- `DECIMAL(19,4)`: số âm, số lớn gần giới hạn, giá trị nhiều hơn 4 chữ số thập phân.
- `BIGINT`: ID vượt phạm vi `INT`.
- Chuỗi: tiếng Việt có dấu, emoji, độ dài ngay biên và vượt giới hạn.
- Thời gian: thời điểm gần nửa đêm, offset múi giờ khác, microsecond/nanosecond.
- Boolean: false/true, NULL và giá trị không hợp lệ nếu DBMS lưu dưới dạng số.
- UUID: text/native/binary và quá trình chuyển sang kiểu Java.

Đừng chỉ test DDL. Bài kiểm chứng cần **round-trip**: Java ghi qua JDBC và đọc lại, so sánh theo hợp đồng dữ liệu.

## 11. Đổi kiểu cột đã có dữ liệu bằng modifyDataType

Đổi kiểu trên bảng đang chạy production thường rủi ro hơn tạo bảng mới. Lệnh DDL có thể phải viết lại dữ liệu, khóa bảng, xây lại index hoặc sửa những foreign key liên quan.

| Thay đổi | Nguy cơ | Kiểm tra bắt buộc |
|---|---|---|
| `VARCHAR(80)` → `VARCHAR(160)` | Thường ít mất dữ liệu nhưng có thể cần lock hoặc rebuild. | Chi phí DDL và semantics byte/char. |
| `INT` → `BIGINT` | Đổi kiểu khóa, index hoặc FK. | Tất cả cột tham chiếu, identity, Java type. |
| `DECIMAL(18,4)` → `DECIMAL(18,2)` | Mất precision hoặc làm tròn. | Phần thập phân của dữ liệu thật. |
| `DECIMAL(18,2)` → `DECIMAL(12,2)` | Overflow vì giảm số chữ số. | Giá trị max/min và các ràng buộc. |
| `TIMESTAMP` → kiểu timezone-aware | Thay đổi ngữ nghĩa thời điểm. | Timezone của dữ liệu gốc và driver. |
| `VARCHAR(36)` → `UUID`/`BINARY(16)` | Giá trị không hợp lệ hoặc đổi representation. | Encoding, thứ tự byte, rollback. |
| `TEXT` → `JSON`/`JSONB` | Giá trị không phải JSON hợp lệ. | Parse tất cả hàng, query và index. |
| Nullable → NOT NULL | Các hàng đang chứa NULL. | Backfill trước khi thêm constraint. |

Ví dụ nâng số tiền:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-expand-invoice-amount
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: invoice
        - columnExists:
            tableName: invoice
            columnName: total_amount
      changes:
        - modifyDataType:
            tableName: invoice
            columnName: total_amount
            newDataType: DECIMAL(19,4)
~~~

Ví dụ giả định cột đã có kiểu cũ phù hợp, chẳng hạn `DECIMAL(12,2)`. `tableExists` và `columnExists` chỉ kiểm tra cột **có tồn tại**, không xác minh kiểu hiện tại hoặc dữ liệu đã sẵn sàng. Nếu database giữa các môi trường bị drift, cần thêm bước đối chiếu metadata hoặc `sqlCheck` riêng cho DBMS để không áp dụng sai.

Khả năng hỗ trợ `modifyDataType`, cú pháp DDL, khóa bảng và rollback khác nhau theo DBMS. **Không giả định Liquibase tự động đảo ngược chính xác việc đổi kiểu**; cần xác minh hỗ trợ và thiết kế rollback hoặc khôi phục dữ liệu rõ ràng.

### 11.1. Expand–migrate–contract

Với thay đổi có nguy cơ mất dữ liệu hoặc cần hỗ trợ ứng dụng đang chạy, nên cân nhắc:

1. **Expand:** thêm cột mới với kiểu mục tiêu, có thể tạm cho NULL.
2. **Migrate:** backfill theo lô, chuyển dữ liệu có kiểm chứng; lưu danh sách giá trị không chuyển được.
3. **Chuyển ứng dụng:** hỗ trợ giai đoạn đọc/ghi đồng thời hai cột hoặc triển khai qua các phiên bản tương thích.
4. **Validate:** so sánh số lượng bản ghi, giá trị biên, checksum nghiệp vụ, quy tắc precision và NULL.
5. **Contract:** thêm constraint cuối cùng, ngừng dùng cột cũ và chỉ sau đó xóa cột cũ.

Mỗi giai đoạn nên là changeset riêng có ID ổn định. `DATABASECHANGELOG` ghi nhận tiến độ migration của Liquibase, nhưng không chứng minh mọi giá trị nghiệp vụ đã được chuyển chính xác nếu không có bước kiểm tra dữ liệu.

## 12. Spring Boot, Hibernate/JPA và JDBC phải đồng bộ

Ứng dụng có thể dùng Liquibase để sinh DDL và Hibernate/JPA để ánh xạ Java entity. Đây là hai cơ chế có quy tắc độc lập:

| Java | SQL thường kỳ vọng | Rủi ro cần kiểm tra |
|---|---|---|
| `String` | `VARCHAR`/`NVARCHAR`/`TEXT` | `@Column(length=...)`, Unicode, collation. |
| `Integer` | `INT` hoặc kiểu số tương đương | Tràn miền giá trị. |
| `Long` | `BIGINT` hoặc kiểu số tương đương | Identity/sequence, FK, giới hạn driver. |
| `BigDecimal` | `DECIMAL(p,s)`/`NUMERIC(p,s)` | Precision/scale, làm tròn. |
| `Boolean` | `BOOLEAN`/`BIT`/số | NULL/default và giá trị ngoài 0/1. |
| `LocalDate` | `DATE` | Oracle DATE có thể chứa giờ. |
| `LocalDateTime` | Ngày giờ không nhất thiết có offset | Cách lưu/đọc timezone. |
| `Instant`/`OffsetDateTime` | Kiểu hoặc chiến lược lưu thời điểm | Offset, session timezone, precision. |
| `UUID` | UUID native, text hoặc binary | Converter/JDBC binding và index. |
| `byte[]` | Nhị phân/BLOB | Kích thước, streaming, hiệu năng. |

Ví dụ Liquibase tạo `DECIMAL(19,4)` nhưng entity JPA khai báo precision/scale khác; ORM có thể báo mismatch hoặc chuyển dữ liệu khác kỳ vọng. Tránh để Hibernate tự cập nhật schema production (`ddl-auto=update`) đồng thời với Liquibase, vì sẽ khó xác định nguồn sở hữu DDL và lịch sử triển khai.

Đối với `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, nên coi Liquibase là nguồn DDL được kiểm soát và dùng schema validation cùng các bài test JDBC để bảo đảm entity khớp kiểu SQL thật.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Data truncation` / `value too long` | Giới hạn VARCHAR, charset, byte/char semantics. | Metadata thật và chuỗi Unicode biên. |
| `Numeric value out of range` | Số vượt miền `INT` hoặc `DECIMAL(p,s)`. | Min/max, precision/scale, kế hoạch widen. |
| Tiền lệch vài đơn vị nhỏ | Dùng FLOAT/DOUBLE hoặc rounding sai. | BigDecimal, scale, ứng dụng và driver. |
| Lệch giờ khi đọc timestamp | Sai timezone hoặc loại cột thời gian. | JDBC session, DB timezone, kiểu Java. |
| Boolean trả ra dạng số bất ngờ | DBMS lưu `BIT`/số, converter không khớp. | Kiểu SQL thật và driver. |
| Changelog chạy ở PostgreSQL nhưng lỗi Oracle | Kiểu native hoặc DDL không tương thích. | SQL preview Oracle và DBMS filter. |
| UUID không đọc được về Java | Binary/text/native không khớp mapping. | Representation và converter. |
| `modifyDataType` thất bại | Dữ liệu không chuyển được, DDL không hỗ trợ hoặc lock. | Dữ liệu thật, SQL và quyền/transaction. |
| JPA báo schema mismatch | Liquibase và ORM kỳ vọng kiểu khác nhau. | Entity, dialect, metadata và version. |
| `validate` đạt nhưng update lỗi | Validation không đảm bảo DDL an toàn. | Chạy trên database thử đại diện. |

Ví dụ một cột boolean cũ dùng `NUMBER(1)` mà không có check constraint: một tiến trình ngoài ứng dụng có thể ghi giá trị `2`. Khi đổi sang `BOOLEAN` native, dữ liệu ấy có thể bị từ chối. Bài học là **kiểu, constraint và tính hợp lệ của dữ liệu phải được kiểm chứng riêng**.

## 14. Checklist trước khi phát hành

- [ ] Đã xác định miền giá trị nghiệp vụ và kiểu Liquibase phù hợp.
- [ ] Đã kiểm tra hỗ trợ của phiên bản Liquibase/extension/DBMS đang dùng.
- [ ] Đã xem SQL do Liquibase sinh trên **từng DBMS** được hỗ trợ.
- [ ] Đã kiểm tra precision/scale, Unicode, charset, byte/char semantics và collation.
- [ ] Đã quy định timezone và precision cho các giá trị thời gian.
- [ ] Boolean, UUID, JSON và LOB có cách lưu/đọc qua JDBC được kiểm chứng.
- [ ] Auto-increment, default, nullability, unique, PK và FK được xét riêng khỏi type.
- [ ] Đã kiểm tra dữ liệu hiện có trước khi đổi kiểu, kể cả overflow và rounding.
- [ ] Đã đánh giá lock, thời gian DDL, index rebuild và downtime.
- [ ] Đã thử migration trên database đại diện, có dữ liệu biên và lịch sử cũ.
- [ ] Đã xác minh `DATABASECHANGELOG`, checksum và cách rollback/restore.
- [ ] JPA/Hibernate/JDBC thống nhất với kiểu SQL đã tạo; không có nguồn khác âm thầm thay schema.
- [ ] Nhánh migration DBMS-specific có test riêng và không bỏ sót DBMS được hỗ trợ.

## 15. Bài thực hành có kiểm chứng

**Bối cảnh:** service hóa đơn Java phải triển khai trên hai DBMS thử nghiệm. Mục tiêu là chứng minh cùng changelog có thể sinh DDL khác nhau nhưng vẫn đáp ứng hợp đồng dữ liệu nghiệp vụ.

**Giai đoạn A — Khai báo:** dùng ví dụ `invoice` ở mục 8. Quy định rõ `id` 64 bit, `invoice_code` chứa Unicode, `total_amount` có 4 chữ số thập phân, `issued_on` là ngày lịch và `created_at` có quy tắc timezone.

**Giai đoạn B — Xem SQL:** với mỗi DBMS, chạy `validate`, `status`, `update-sql`; ghi lại type thực, identity, default, khóa chính, unique, precision và scale. Đối chiếu những khác biệt có thể làm sai hợp đồng dữ liệu.

**Giai đoạn C — Chạy thử:** tạo database trống, chạy `update`, đọc metadata và ghi/đọc lại qua JDBC các giá trị: số tiền `1234567890.1234`, chuỗi tiếng Việt có dấu, false/true, thời điểm có microsecond. Thử giá trị vượt giới hạn và ghi nhận cách DBMS phản hồi.

**Giai đoạn D — Nâng kiểu:** giả định bản cũ có `total_amount DECIMAL(12,2)`. Thiết kế nâng thành `DECIMAL(19,4)`: kiểm tra dữ liệu và index, xem SQL `modifyDataType` trên từng DBMS, chọn đổi trực tiếp hay expand–migrate–contract, rồi kiểm chứng lại dữ liệu và Java `BigDecimal`.

**Tiêu chí đạt:** xác định được kiểu SQL thực tế, giải thích được khác biệt ngữ nghĩa, kiểm tra được dữ liệu biên, đánh giá được hậu quả của việc đổi kiểu và đưa ra phương án rollback/restore có kiểm chứng.

## 16. Câu hỏi tự kiểm tra

1. Kiểu dữ liệu Java, Liquibase và SQL vật lý khác nhau ở trách nhiệm nào?
2. Vì sao `DECIMAL(19,4)` thường phù hợp với tiền hơn `DOUBLE`?
3. `VARCHAR(100)` có bảo đảm lưu đủ 100 ký tự Unicode trên mọi DBMS không?
4. Vì sao `DATE` cần được đánh giá riêng khi dùng Oracle?
5. `TIMESTAMP` có luôn giữ thông tin timezone không? Khi nào dùng `Instant`?
6. Vì sao boolean lưu dưới dạng số có thể cần check constraint?
7. Khi nào dùng `JSONB` cùng `dbms` thay vì cố dùng một kiểu JSON chung?
8. `autoIncrement` và `nullable` có phải tên kiểu dữ liệu không?
9. `validate` thành công có chứng minh `modifyDataType` an toàn với production không?
10. Đổi khóa chính từ `INT` sang `BIGINT` ảnh hưởng thành phần nào?
11. Vì sao nên kiểm thử Java/JDBC round-trip sau khi tạo schema bằng Liquibase?
12. Khi nào nên dùng expand–migrate–contract thay cho đổi kiểu trực tiếp?

## Kết luận

Ánh xạ kiểu dữ liệu là quá trình chuyển **ý định lưu trữ** trong changelog thành **cấu trúc và hành vi cụ thể** của DBMS. Một migration chỉ thực sự đáng tin cậy khi kiểu Liquibase được so sánh với SQL sinh ra, metadata thực tế, dữ liệu biên, JDBC mapping và ràng buộc nghiệp vụ. Làm tốt các bước này giúp quản lý thay đổi bảng nhất quán, bảo toàn dữ liệu và hỗ trợ phát hành Liquibase qua nhiều môi trường.
