# Quản lý kiểu dữ liệu, hàm mặc định và tên đối tượng khác nhau giữa các DBMS

## 1. Vì sao cùng một changelog có thể tạo schema khác nhau?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, người học quản lý thay đổi schema và dữ liệu bằng Liquibase qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi một sản phẩm hỗ trợ nhiều hệ quản trị cơ sở dữ liệu (DBMS), nhóm phải xử lý ba nhóm khác biệt thường gặp:

1. **Kiểu dữ liệu:** cùng ý nghĩa nghiệp vụ có thể được biểu diễn bằng kiểu hoặc giới hạn khác nhau, ví dụ boolean, UUID, JSON, ngày giờ, số chính xác và dữ liệu nhị phân.
2. **Hàm/biểu thức mặc định:** cùng yêu cầu “lấy thời điểm hiện tại” có thể dùng `CURRENT_TIMESTAMP`, `NOW()`, `GETDATE()` hoặc `SYSTIMESTAMP`, với ngữ nghĩa và kiểu trả về khác nhau.
3. **Tên đối tượng:** cách viết hoa/thường, quote identifier, giới hạn độ dài tên, schema/catalog, từ khóa dành riêng và cách đặt tên constraint/index không giống nhau.

Liquibase cung cấp change type và kiểu dữ liệu ở mức trừu tượng để giảm phụ thuộc DBMS. Khi không đủ, có thể phân nhánh changeset bằng thuộc tính `dbms`, dùng `modifySql` hoặc viết SQL riêng cho từng hệ quản trị. **Mục tiêu không phải ép mọi DBMS có DDL giống hệt nhau; mục tiêu là giữ cùng ý nghĩa nghiệp vụ và kiểm soát khác biệt một cách tường minh.**

Sau bài học, bạn cần làm được:

- Chọn kiểu Liquibase tổng quát khi các DBMS mục tiêu có ánh xạ tương thích.
- Nhận diện lúc cần kiểu hoặc DDL riêng theo DBMS.
- Dùng `defaultValueComputed` cho biểu thức SQL mặc định và phân biệt nó với giá trị literal.
- Quản lý tên schema, bảng, cột, sequence, index và constraint ổn định giữa các hệ quản trị.
- Tổ chức changelog đa DBMS có thể validate, xem trước SQL, thử thực thi, rollback và phát hành qua CI/CD.

## 2. Bắt đầu từ hợp đồng dữ liệu, không bắt đầu từ cú pháp

### 2.1. Xác định ý nghĩa nghiệp vụ

Trước khi chọn datatype, hãy chốt các bất biến:

| Thuộc tính | Câu hỏi cần chốt | Ví dụ quyết định |
|---|---|---|
| Mã định danh | Có phép tính số học không? Có giữ số 0 đầu? | Mã ngoài hệ thống là chuỗi; khóa nội bộ là số/UUID |
| Số tiền | Cần chính xác bao nhiêu chữ số? Có cho âm? | Decimal chính xác, 2 hoặc 4 chữ số thập phân |
| Cờ trạng thái | Có đúng hai trạng thái hay có unknown? | Boolean hoặc mã trạng thái có kiểm soát |
| JSON | Chỉ lưu văn bản hay truy vấn/index theo cấu trúc? | JSON text hoặc kiểu JSON native |
| Thời điểm | Là ngày lịch, thời điểm UTC hay thời điểm địa phương? | Instant lưu UTC, hoặc ngày nghiệp vụ không có giờ |
| Giá trị mặc định | Áp dụng khi bỏ qua cột hay khi dữ liệu nguồn NULL? | Default schema, backfill và NULL policy tách riêng |
| Tên đối tượng | Có cần quote/case đặc biệt không? | Tên chữ thường, ASCII, không dùng từ khóa |

Một cột được ánh xạ sang các kiểu vật lý khác nhau vẫn có thể đáp ứng cùng hợp đồng, nhưng phải xác minh precision, timezone, nullability, collation, giới hạn độ dài và hành vi so sánh. Nếu hợp đồng nghiệp vụ chưa rõ, một kiểu “portable” không cứu được thiết kế sai.

### 2.2. Ba tầng lựa chọn trong Liquibase

| Tầng | Cách làm | Khi nên dùng |
|---|---|---|
| Tổng quát | Dùng `type` và change type độc lập DBMS như `addColumn`, `addDefaultValue`, `createIndex` | Kiểu/DDL có ánh xạ tương thích trên các DBMS mục tiêu |
| Phân nhánh | Nhiều changeset cùng mục đích, mỗi changeset có `dbms` riêng | Cần datatype, default expression hoặc cú pháp khác nhau |
| SQL native | `sql`, `sqlFile`, formatted SQL hoặc `modifySql` theo DBMS | Change type tổng quát không biểu đạt đủ tính năng/DDL cần thiết |

Nên ưu tiên tầng tổng quát khi không làm mất ngữ nghĩa. Khi cần phân nhánh, hãy giữ các nhánh nhỏ, dễ so sánh và có cùng mục đích nghiệp vụ. Không tạo một changelog khổng lồ chứa nhiều biểu thức điều kiện khó kiểm tra.

## 3. Kiểu dữ liệu tổng quát và ánh xạ theo hệ quản trị

### 3.1. `type` của Liquibase không nhất thiết là tên kiểu vật lý cuối cùng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-add-profile-fields
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: external_id
                  type: VARCHAR(80)
              - column:
                  name: credit_limit
                  type: DECIMAL(19,4)
              - column:
                  name: created_at
                  type: TIMESTAMP
~~~

`VARCHAR`, `DECIMAL` và `TIMESTAMP` là các kiểu SQL phổ biến mà Liquibase có thể dùng làm đầu vào cho SQL generator. Tên kiểu hoặc cú pháp được sinh ra có thể được điều chỉnh theo DBMS. Một hệ quản trị có thể biểu diễn kiểu thời gian bằng tên khác hoặc dùng quy tắc precision riêng.

**Không có nghĩa mọi kiểu tổng quát đều được hỗ trợ đồng nhất ở mọi DBMS.** Kiểu native như `JSONB`, `NVARCHAR2`, `DATETIME2`, `BYTEA`, `UNIQUEIDENTIFIER` hoặc `NUMBER` có thể cần cấu hình riêng. Hãy chạy `update-sql` trên đúng DBMS/version và thử migration thật trên database tương ứng.

### 3.2. Bảng định hướng kiểu dữ liệu

| Ý nghĩa | PostgreSQL | MySQL / InnoDB | SQL Server | Oracle |
|---|---|---|---|---|
| Chuỗi biến độ dài | `VARCHAR(n)` / `TEXT` | `VARCHAR(n)` / `TEXT` | `VARCHAR(n)` / `NVARCHAR(n)` | `VARCHAR2(n)` / `CLOB` |
| Số chính xác | `NUMERIC(p,s)` | `DECIMAL(p,s)` | `DECIMAL(p,s)` | `NUMBER(p,s)` |
| Boolean | `BOOLEAN` | `BOOLEAN` là alias kiểu số nhỏ trong MySQL | Thường dùng `BIT` | Trước Oracle 23c thường mô hình hóa bằng `NUMBER(1)` hoặc `CHAR(1)`; Oracle 23c trở lên có SQL `BOOLEAN` |
| Ngày | `DATE` | `DATE` | `DATE` | `DATE` |
| Thời điểm | `TIMESTAMP` / `TIMESTAMPTZ` | `DATETIME` / `TIMESTAMP` | `DATETIME2` / `DATETIMEOFFSET` | `TIMESTAMP` / `TIMESTAMP WITH TIME ZONE` |
| UUID/GUID | `UUID` | Thường `CHAR(36)` hoặc `BINARY(16)` | `UNIQUEIDENTIFIER` | Có thể dùng `RAW(16)` |
| JSON | `JSON` / `JSONB` | `JSON` | Thường lưu `NVARCHAR` và dùng hàm JSON | Hỗ trợ phụ thuộc phiên bản, kiểu cột và cấu hình |
| Dữ liệu nhị phân | `BYTEA` | `BLOB` | `VARBINARY` / `VARBINARY(MAX)` | `RAW` / `BLOB` |

Bảng chỉ là định hướng. Giới hạn độ dài, encoding, timezone, khả năng index, toán tử và hành vi chuyển đổi còn phụ thuộc phiên bản/edition, cấu hình và driver. Không dùng bảng này như một công cụ tự động chuyển schema.

### 3.3. Boolean và giá trị ba trạng thái

PostgreSQL có kiểu `BOOLEAN`; MySQL chấp nhận `BOOLEAN` như alias cho kiểu số nhỏ trong nhiều ngữ cảnh; SQL Server thường dùng `BIT`. Với Oracle, các phiên bản trước 23c thường mô hình hóa cờ trong cột bằng `NUMBER(1)` hoặc `CHAR(1)`; Oracle 23c trở lên có kiểu SQL `BOOLEAN`. Khi hỗ trợ nhiều phiên bản Oracle, phải chọn nhánh phù hợp hoặc dùng kiểu chung đã được kiểm chứng. Nếu nghiệp vụ chỉ có hai trạng thái, cần xác định representation và constraint:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-add-active-flag
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: true
                  constraints:
                    nullable: false
~~~

Đoạn trên phù hợp khi kiểu `BOOLEAN` và default được generator hỗ trợ cho DBMS đích. Nếu một nhánh cần `BIT` hoặc `NUMBER(1)`, có thể dùng `dbms` branch. Đừng quên rằng `NULL` tạo ra trạng thái thứ ba trong logic SQL; `NOT NULL` chỉ đúng khi “không biết” không phải trạng thái nghiệp vụ hợp lệ.

Nếu dùng `NUMBER(1)` hoặc `CHAR(1)` cho Oracle, có thể cần `CHECK (active IN (0,1))` hoặc `CHECK (active IN ('Y','N'))`. Kiểu cột đơn thuần không đảm bảo chỉ có hai giá trị.

### 3.4. UUID/GUID và tính tương thích

UUID là mã định danh 128-bit; cách lưu có thể khác:

- PostgreSQL có kiểu `UUID`.
- SQL Server có `UNIQUEIDENTIFIER`.
- MySQL thường lưu dạng text `CHAR(36)` hoặc binary `BINARY(16)`.
- Oracle có thể dùng `RAW(16)` hoặc biểu diễn text tùy thiết kế.

Nếu chọn text, cần quy ước format, chữ hoa/thường, dấu gạch nối và collation. Nếu chọn binary, cần xác định thứ tự byte và cách encode/decode nhất quán giữa ứng dụng, driver và hệ thống khác. Không chỉ đổi `type` rồi mặc định các ứng dụng serialize UUID giống nhau.

Ví dụ nhánh theo DBMS:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-add-uuid-postgresql
      author: database-team
      dbms: postgresql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: public_id
                  type: UUID

  - changeSet:
      id: customer-add-uuid-mysql
      author: database-team
      dbms: mysql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: public_id
                  type: BINARY(16)

  - changeSet:
      id: customer-add-uuid-mssql
      author: database-team
      dbms: mssql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: public_id
                  type: UNIQUEIDENTIFIER
~~~

Ví dụ cho thấy các nhánh schema khác nhau về kiểu vật lý; trước khi dùng cần bổ sung rollback, kiểm tra phiên bản/driver và thống nhất cách ứng dụng ghi/đọc UUID ở từng DBMS. Oracle chưa được đưa vào ví dụ này vì nhóm phải chốt cách lưu `RAW(16)` hay text theo hợp đồng riêng.

### 3.5. JSON và kiểu dữ liệu có tính năng riêng

`JSON` và `JSONB` trong PostgreSQL không tương đương hoàn toàn: JSONB lưu dạng đã phân tích và hỗ trợ toán tử/index khác JSON text. MySQL có kiểu JSON riêng. SQL Server có các hàm xử lý JSON nhưng thường lưu văn bản trong cột chuỗi. Oracle có hỗ trợ JSON phụ thuộc phiên bản và kiểu cột được chọn.

Nếu ứng dụng chỉ lưu và trả lại payload, kiểu chuỗi có thể đủ. Nếu cần truy vấn theo thuộc tính, kiểm tra cấu trúc, index path hoặc ràng buộc JSON, hãy thiết kế riêng theo DBMS và kiểm thử query. Không đổi JSONB sang VARCHAR mà không đánh giá chức năng ứng dụng đang dùng.

## 4. Hàm mặc định: literal khác biểu thức SQL

### 4.1. `defaultValue` và `defaultValueComputed`

Liquibase phân biệt:

- `defaultValue`: giá trị literal dùng làm default, chẳng hạn chuỗi `PENDING`.
- `defaultValueNumeric`: literal số.
- `defaultValueBoolean`: literal boolean.
- `defaultValueDate`: giá trị ngày/giờ dạng literal theo quy tắc Liquibase.
- `defaultValueComputed`: biểu thức SQL để database đánh giá khi áp dụng default.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: order-add-created-at
      author: database-team
      changes:
        - addColumn:
            tableName: purchase_order
            columns:
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
~~~

`CURRENT_TIMESTAMP` là biểu thức SQL, không phải chuỗi văn bản cần lưu nguyên chữ. Nếu dùng `defaultValue: CURRENT_TIMESTAMP`, có nguy cơ database lưu literal hoặc Liquibase quote theo kiểu chuỗi, không thực hiện hàm như dự định. Dùng đúng thuộc tính cho đúng ý nghĩa.

### 4.2. Các hàm thời gian thường gặp

| Ý định | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Thời điểm hiện tại | `CURRENT_TIMESTAMP` hoặc `now()` | `CURRENT_TIMESTAMP` / `NOW()` | `CURRENT_TIMESTAMP` / `GETDATE()` | `CURRENT_TIMESTAMP` / `SYSTIMESTAMP` |
| Ngày hiện tại | `CURRENT_DATE` | `CURRENT_DATE` | Thường `CAST(GETDATE() AS date)` | `CURRENT_DATE` hoặc `TRUNC(SYSDATE)` tùy ngữ nghĩa |
| Thời điểm hệ thống | `clock_timestamp()` khác `now()` về thời điểm đánh giá | `CURRENT_TIMESTAMP` theo session/time zone | `SYSDATETIME()` / `SYSUTCDATETIME()` | `SYSTIMESTAMP` / `SYSDATE` |

Các biểu thức không thay thế lẫn nhau hoàn toàn. Ví dụ PostgreSQL `now()`/`CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction; `clock_timestamp()` trả thời điểm thực tại lúc gọi. SQL Server `GETDATE()` trả kiểu `datetime` theo giờ hệ thống của instance; `SYSUTCDATETIME()` trả UTC với độ chính xác khác. Oracle `SYSDATE` và `SYSTIMESTAMP` cũng khác kiểu và thông tin timezone.

Vì vậy, yêu cầu “lưu thời gian hiện tại” cần được cụ thể hóa: cần UTC hay local time; thời điểm bắt đầu transaction hay thời điểm thực tại lúc gọi; có giữ offset/time zone hay không; độ chính xác mili/micro/nanosecond; và default chỉ áp dụng khi insert bỏ qua cột hay không.

### 4.3. Literal, default động và backfill là ba thao tác riêng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: order-add-created-at
      author: database-team
      changes:
        - addColumn:
            tableName: purchase_order
            columns:
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
~~~

Đây là default của cột cho các lần ghi mới theo quy tắc DBMS. Nó không tự trả lời câu hỏi dữ liệu cũ cần mốc thời gian nào. Nếu phải backfill, cần một thay đổi dữ liệu riêng với ý nghĩa được thống nhất, ví dụ lấy thời gian tạo từ một cột lịch sử khác hoặc đánh dấu một mốc migration. Không mặc định tất cả bản ghi cũ đều có CURRENT_TIMESTAMP là thời điểm tạo chính xác.

Default thông thường được áp dụng khi câu `INSERT` bỏ qua cột hoặc yêu cầu `DEFAULT`; nó không mặc nhiên thay thế giá trị `NULL` được ứng dụng gửi tường minh. Nếu muốn biến NULL thành một giá trị, cần backfill/validation hoặc xử lý ở ứng dụng.

## 5. Khai báo default function riêng theo DBMS

### 5.1. Nhiều changeset có `dbms`

Khi các DBMS cần hàm khác nhau hoặc kiểu trả về khác nhau, dùng các changeset tách biệt:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: order-default-created-at-postgresql
      author: database-team
      dbms: postgresql
      changes:
        - addDefaultValue:
            tableName: purchase_order
            columnName: created_at
            columnDataType: TIMESTAMP
            defaultValueComputed: CURRENT_TIMESTAMP
      rollback:
        - dropDefaultValue:
            tableName: purchase_order
            columnName: created_at
            columnDataType: TIMESTAMP

  - changeSet:
      id: order-default-created-at-mssql
      author: database-team
      dbms: mssql
      changes:
        - addDefaultValue:
            tableName: purchase_order
            columnName: created_at
            columnDataType: DATETIME2
            defaultValueComputed: SYSUTCDATETIME()
      rollback:
        - dropDefaultValue:
            tableName: purchase_order
            columnName: created_at
            columnDataType: DATETIME2
~~~

Đây là ví dụ minh họa ý tưởng; cột phải tồn tại trước, datatype và expression phải được xác nhận với version DBMS/Liquibase. Với SQL Server, default thường được quản lý bằng default constraint có tên; khi cần drop, việc nhận diện constraint có thể cần tên rõ ràng hoặc metadata theo hỗ trợ của Liquibase version. Không coi ví dụ trên là script portable đã kiểm thử.

### 5.2. `modifySql` khi cần biến đổi SQL được sinh

`modifySql` có thể áp dụng biến đổi vào SQL được sinh ra theo DBMS, chẳng hạn thêm một mệnh đề hoặc thay đổi cú pháp. Dùng nó khi một biến đổi nhỏ là đủ và đã được kiểm tra trên output thực tế. Không dùng chuỗi thay thế rộng trên toàn bộ SQL nếu có thể vô tình thay literal, tên object hoặc câu lệnh không liên quan.

Ví dụ vị trí khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-audit-table
      author: database-team
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
      modifySql:
        - append:
            value: " ENGINE=InnoDB"
            dbms: mysql
~~~

Ví dụ thêm tùy chọn engine vào DDL tạo bảng trên MySQL. Phải kiểm tra SQL cuối cùng vì cú pháp engine, mặc định storage engine và khả năng của server có thể khác theo phiên bản/cấu hình. Nếu DBMS đã có engine mặc định đúng hoặc change type có lựa chọn phù hợp hơn, không cần thêm `modifySql`.

### 5.3. Khi nào nên dùng SQL native?

Nếu biểu thức mặc định cần hàm đặc thù hoặc DDL không được change type hỗ trợ, có thể tạo nhánh DBMS:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-order-default-postgresql
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            sql: >
              ALTER TABLE purchase_order
              ALTER COLUMN created_at
              SET DEFAULT clock_timestamp()
      rollback:
        - sql:
            sql: >
              ALTER TABLE purchase_order
              ALTER COLUMN created_at DROP DEFAULT

  - changeSet:
      id: add-order-default-mysql
      author: database-team
      dbms: mysql
      changes:
        - sql:
            sql: >
              ALTER TABLE purchase_order
              ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP
      rollback:
        - sql:
            sql: >
              ALTER TABLE purchase_order
              ALTER COLUMN created_at DROP DEFAULT
~~~

Các câu lệnh SQL native phải được kiểm tra trên đúng phiên bản DBMS; MySQL có giới hạn khác nhau cho default expression theo datatype/version. PostgreSQL và MySQL không dùng cùng cú pháp ALTER COLUMN. Không đưa hai nhánh này vào một changeset không có `dbms` filter.

## 6. Tên đối tượng: schema, catalog và quy tắc phân giải

### 6.1. Tên logic trong changelog

Liquibase có các thuộc tính như `catalogName`, `schemaName`, `tableName`, `columnName`, `indexName`, `constraintName`, `sequenceName` và tên object tương ứng với change type. Khi dự án hỗ trợ nhiều DBMS, cần thống nhất quy ước tên logic:

- Dùng tên ASCII, dễ đọc, tránh từ khóa dành riêng.
- Ưu tiên chữ thường và dấu gạch dưới nếu không có lý do khác.
- Tránh phân biệt chỉ bằng chữ hoa/thường.
- Đặt tên constraint/index tường minh thay vì dựa vào tên tự sinh của DBMS.
- Giữ tên ngắn hơn giới hạn của DBMS cũ nhất trong ma trận hỗ trợ.
- Quy định schema owner và schema metadata Liquibase riêng biệt.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-order-index
      author: database-team
      changes:
        - createIndex:
            indexName: idx_purchase_order_tenant_created
            schemaName: app
            tableName: purchase_order
            columns:
              - column:
                  name: tenant_id
              - column:
                  name: created_at
~~~

Tên `app.purchase_order` là đối tượng trong schema ứng dụng. Bảng metadata `DATABASECHANGELOG`/`DATABASECHANGELOGLOCK` có thể nằm trong schema riêng theo cấu hình Liquibase; không nhầm schema metadata với schema ứng dụng.

### 6.2. `defaultSchemaName` và `liquibaseSchemaName`

Hai cấu hình có mục đích khác nhau:

- `defaultSchemaName`: schema mặc định để Liquibase phân giải đối tượng khi changeset không nêu schema cụ thể.
- `liquibaseSchemaName`: schema chứa các bảng quản lý trạng thái của Liquibase như `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.

Nếu bỏ qua hai giá trị này trong hệ thống nhiều schema, cùng một changelog có thể tạo bảng ở schema không mong muốn hoặc không tìm thấy bảng metadata. Hãy xác định rõ chúng trong cấu hình môi trường hoặc khai báo schema cho từng object quan trọng.

`catalogName` thường gắn với khái niệm catalog/database ở các DBMS như SQL Server/MySQL; `schemaName` là namespace bên trong database. Cách ánh xạ và tên qualifier khác nhau giữa hệ quản trị. Không đặt `catalogName` theo thói quen PostgreSQL nếu ứng dụng không có khái niệm tương đương.

## 7. Chữ hoa/thường, quoted identifiers và từ khóa dành riêng

### 7.1. Tên không quote có thể được chuẩn hóa khác nhau

Các DBMS có quy tắc khác nhau khi phân giải identifier không đặt trong dấu quote:

- PostgreSQL thường chuyển identifier không quote về chữ thường.
- Oracle thường chuyển identifier không quote về chữ hoa.
- SQL Server phụ thuộc collation và thiết lập phân biệt hoa/thường.
- MySQL có quy tắc khác nhau cho tên database/table theo nền tảng và cấu hình; tên cột và tên alias có quy tắc riêng.

Ví dụ `CustomerOrder`, `customerorder` và `"CustomerOrder"` có thể không trỏ cùng đối tượng trong mọi DBMS. Một changelog dùng tên mixed-case và quoted identifier có thể hoạt động ở môi trường này nhưng lỗi ở môi trường khác.

### 7.2. Chiến lược đặt tên an toàn

~~~text
table:       purchase_order
column:      created_at
index:       idx_purchase_order_tenant_created
unique:      uk_customer_tenant_external
foreign key: fk_order_customer
sequence:    seq_purchase_order_id
view:        v_customer_summary
~~~

Tránh tên như `Order`, `User`, `Group`, `Date`, `Key` nếu có thể trùng từ khóa hoặc tên hàm của DBMS. Nếu buộc phải dùng identifier đặc biệt, phải xác định quoting strategy và thử trên mọi hệ quản trị.

Liquibase có cấu hình `objectQuotingStrategy` với các lựa chọn phụ thuộc phiên bản. Việc quote mọi identifier có thể giúp giữ mixed-case nhưng cũng làm tên object nhạy với chính xác chữ hoa/thường và dấu quote. Không bật quoting toàn cục chỉ để sửa một tên bảng; hãy thống nhất naming convention và xác minh SQL sinh ra.

### 7.3. Độ dài identifier

Giới hạn tên khác nhau theo DBMS và phiên bản. Một số ví dụ thường gặp:

| DBMS | Giới hạn phổ biến cần chú ý |
|---|---|
| PostgreSQL | Identifier mặc định thường bị giới hạn theo byte, phổ biến 63 byte |
| MySQL | Nhiều loại tên object như database/table/column/index có giới hạn riêng; table/index thường 64 ký tự |
| SQL Server | Nhiều identifier thông dụng tối đa 128 ký tự |
| Oracle | Trước 12.2 thường gặp giới hạn 30 byte; các bản mới hỗ trợ giới hạn dài hơn, thường 128 byte, tùy object/compatibility |

Đây là con số định hướng, phải kiểm tra đúng loại identifier, encoding và version. Tiếng Việt hoặc Unicode có thể chiếm nhiều byte hơn số ký tự nhìn thấy. Tên constraint do Liquibase hoặc DBMS sinh tự động cũng có thể bị cắt hoặc đụng nhau nếu quá dài.

## 8. Đặt tên constraint và index ổn định

### 8.1. Đặt tên constraint khi có thể

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-tenant-external-unique
      author: database-team
      changes:
        - addUniqueConstraint:
            tableName: customer
            columnNames: tenant_id, external_id
            constraintName: uk_customer_tenant_external
        - addForeignKeyConstraint:
            baseTableName: purchase_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_order_customer
~~~

Tên rõ ràng giúp review, chẩn đoán lỗi, rollback và đồng bộ môi trường. Nếu để DBMS tự sinh tên, mỗi hệ quản trị có thể tạo một tên khác, khiến thao tác drop/modify sau này khó portable.

### 8.2. Default constraint trên SQL Server

SQL Server thường lưu default dưới dạng constraint có tên. Nếu không đặt tên, hệ quản trị có thể tạo tên hệ thống không ổn định giữa database. Khi cần thay/xóa default, việc biết tên constraint là quan trọng. Một số phiên bản Liquibase có hỗ trợ thuộc tính tên default constraint trong các change type liên quan; xác nhận tài liệu/version đang dùng. Nếu không, có thể cần SQL native tra catalog hoặc đặt tên constraint tường minh khi tạo.

Không giả định `dropDefaultValue` sẽ luôn tìm thấy đúng default constraint nếu trước đó constraint được tạo thủ công với tên bất thường hoặc schema có drift. Kiểm tra `update-sql` và thử rollback trên SQL Server thật.

### 8.3. Tên index và uniqueness

Tên index không nên chỉ phản ánh một câu query tạm thời; hãy mô tả mục đích và khóa. Nếu index được dùng để thực thi unique constraint, cần phân biệt index độc lập với constraint. Một số DBMS tự tạo hoặc tận dụng index khi thêm unique constraint; tạo thêm index trùng cột có thể làm tăng write amplification mà không có lợi.

## 9. Phân nhánh changeset đúng cách bằng dbms

### 9.1. Mỗi nhánh cần cùng ý nghĩa nghiệp vụ

Ví dụ cần một cột `active` với default false. PostgreSQL dùng boolean, SQL Server dùng bit và Oracle dùng số 0/1:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-active-postgresql
      author: database-team
      dbms: postgresql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: false
                  constraints:
                    nullable: false

  - changeSet:
      id: customer-active-mssql
      author: database-team
      dbms: mssql
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: active
                  type: BIT
                  defaultValueNumeric: 0
                  constraints:
                    nullable: false

  - changeSet:
      id: customer-active-oracle
      author: database-team
      dbms: oracle
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: active
                  type: NUMBER(1)
                  defaultValueNumeric: 0
                  constraints:
                    nullable: false
~~~

Ví dụ minh họa phân nhánh; cần bổ sung rollback và kiểm tra tác động với dữ liệu hiện hữu. Với Oracle, nếu `active` là `NUMBER(1)`, nên bổ sung constraint giới hạn 0/1. Các nhánh phải được kiểm thử để cùng đảm bảo ý nghĩa “không hoạt động” chứ không chỉ có cùng tên cột.

### 9.2. DBMS filter không phải environment filter

`dbms` chọn hệ quản trị, không phải môi trường `dev`, `test` hay `production`. Một changeset `dbms: postgresql` có thể chạy trên mọi môi trường PostgreSQL phù hợp. Dùng context/label cho mục đích chọn môi trường hoặc tính năng; dùng `dbms` cho khác biệt SQL engine. Không dùng context `production` thay cho `dbms: postgresql`.

### 9.3. Tránh chạy hai nhánh cùng lúc

Nếu cùng một logic có ba changeset với ba giá trị `dbms` loại trừ nhau, mỗi database chỉ nên chọn đúng một nhánh. Hãy xác minh tên short name mà Liquibase nhận diện cho từng DBMS và chạy `status --verbose`/`update-sql` trên mỗi engine. Nếu filter sai hoặc một changeset không có `dbms`, có thể phát sinh chạy trùng hoặc bỏ sót.

## 10. Quản lý nhiều kiểu và tên bằng một changelog có cấu trúc

Một cách tổ chức là giữ master changelog chung, tách các nhánh DBMS thành file riêng và include theo cấu trúc rõ:

~~~yaml
databaseChangeLog:
  - include:
      file: common/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: postgresql/010-customer-defaults.yaml
      relativeToChangelogFile: true
  - include:
      file: mysql/010-customer-defaults.yaml
      relativeToChangelogFile: true
  - include:
      file: mssql/010-customer-defaults.yaml
      relativeToChangelogFile: true
  - include:
      file: oracle/010-customer-defaults.yaml
      relativeToChangelogFile: true
~~~

Mỗi file nhánh cần có changeset `dbms` tương ứng. Nếu include toàn bộ file, Liquibase vẫn đọc changelog và áp dụng quy tắc lọc; thứ tự include cần được kiểm soát để tránh phụ thuộc khó hiểu. Không tạo các changeset cùng mục đích nhưng vô tình có thể cùng chạy trên một DBMS.

Một phương án khác là đặt các nhánh trong cùng một file để reviewer nhìn thấy các biến thể cạnh nhau. Chọn cách nào cũng cần giữ `id` duy nhất trong phạm vi cần thiết và không đổi danh tính changeset đã triển khai.

## 11. Kiểm chứng SQL trên tất cả DBMS mục tiêu

### 11.1. Ma trận kiểm thử

Giả sử sản phẩm hỗ trợ PostgreSQL, MySQL, SQL Server và Oracle. Pipeline cần chạy các kiểm tra độc lập trên từng engine:

| Bước | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Validate changelog | Có | Có | Có | Có |
| Status pending | Có | Có | Có | Có |
| Generate update SQL | Có | Có | Có | Có |
| Apply trên DB test | Có | Có | Có | Có |
| Kiểm tra kiểu/default | Có | Có | Có | Có |
| Kiểm tra tên/quote/schema | Có | Có | Có | Có |
| Kiểm tra rollback/forward-fix | Có | Có | Có | Có |
| Smoke test ứng dụng/driver | Có | Có | Có | Có |

Không thay thế một engine bằng H2 chỉ để chạy nhanh nếu sản phẩm phát hành trên PostgreSQL/MySQL/SQL Server/Oracle. H2 hữu ích cho test logic ở phạm vi nhất định nhưng không mô phỏng đầy đủ kiểu, hàm, identifier, lock và DDL của các DBMS khác.

### 11.2. Lệnh CLI mẫu

Với mỗi cấu hình database:

~~~bash
liquibase --defaults-file=config/postgresql.properties validate
liquibase --defaults-file=config/postgresql.properties status --verbose
liquibase --defaults-file=config/postgresql.properties update-sql
~~~

Sau đó lặp lại với properties riêng cho MySQL, SQL Server và Oracle. Không dùng chung một URL/driver rồi chỉ đổi context để mô phỏng DBMS khác. Giữ cùng version Liquibase/extension nếu đó là cấu hình triển khai thực tế.

### 11.3. Kiểm tra schema và default thật

`update-sql` giúp xem SQL dự kiến, nhưng không chứng minh database đã nhận kiểu/default chính xác. Sau khi chạy thử `update`, kiểm tra metadata theo DBMS:

- PostgreSQL: `information_schema.columns`, `pg_catalog` và view định nghĩa object.
- MySQL: `information_schema.columns`, `SHOW CREATE TABLE`.
- SQL Server: `sys.columns`, `sys.types`, `sys.default_constraints`, `sys.schemas`.
- Oracle: `USER_TAB_COLUMNS`, `ALL_TAB_COLUMNS`, `USER_CONSTRAINTS`, `USER_TAB_IDENTITY_COLS`.

Tên catalog và quyền truy cập phụ thuộc DBMS/version. Hãy kiểm tra kiểu thực tế, precision/scale, nullability, default expression, schema owner và tên constraint; đừng chỉ đọc output `DATABASECHANGELOG`.

### 11.4. Kiểm tra dữ liệu biên

Với decimal, thử giá trị lớn nhất, nhỏ nhất, âm và số chữ số thập phân sát giới hạn. Với thời gian, thử UTC, offset khác, thời điểm chuyển DST và độ chính xác. Với UUID, thử round-trip qua ứng dụng/driver. Với tên object, thử schema có chữ hoa hoặc reserved word chỉ khi thiết kế bắt buộc dùng chúng. Ghi kết quả vào CI để phát hiện regression khi nâng DBMS hoặc Liquibase.

## 12. Rollback và lịch sử khi có nhánh DBMS

### 12.1. Mỗi changeset có rollback tương ứng

Một nhánh tạo default bằng SQL native cần rollback đúng cú pháp cùng DBMS. Không viết rollback PostgreSQL rồi mong SQL Server hoặc Oracle hiểu. Với change type tổng quát như `addDefaultValue`, Liquibase có thể sinh rollback phù hợp, nhưng phải xác minh bằng `rollback-sql` và thử thực thi.

### 12.2. Không sửa changeset đã phát hành để đổi datatype/default

Nếu một nhánh PostgreSQL đã chạy với `TIMESTAMP` và nhóm muốn chuyển sang `TIMESTAMPTZ`, hãy tạo changeset mới cho chuyển đổi. Không sửa nội dung changeset cũ rồi chạy `clearCheckSums` để ép áp dụng. Với mỗi DBMS, kiểu chuyển đổi và khả năng giữ dữ liệu có thể khác; cần xác định chuyển đổi tương ứng theo hợp đồng nghiệp vụ.

### 12.3. Tên logic thay đổi cần migration có chủ đích

Đổi tên bảng, cột hoặc constraint không chỉ là sửa chuỗi trong changelog cũ. Dùng change type rename hoặc SQL phù hợp, đánh giá consumer, khóa ngoại, view, trigger, procedure và ứng dụng. Với nhiều DBMS, câu lệnh rename có thể khác; hãy kiểm tra generator hoặc tách nhánh `dbms`.

## 13. Tình huống thực tế: cột thời điểm tạo trên bốn DBMS

Một dịch vụ Spring Boot lưu thời điểm tạo đơn hàng. Yêu cầu: giá trị được database tạo khi `INSERT` bỏ qua cột; thời gian phải biểu diễn cùng một instant UTC khi trao đổi giữa các vùng. Nhóm cần chọn:

1. Kiểu dữ liệu đủ giữ instant và độ chính xác.
2. Default expression phù hợp DBMS.
3. Cách map Java type/driver.
4. Quy tắc đọc/ghi và serialize API.
5. Chiến lược backfill hàng cũ.

Một thiết kế minh họa có thể dùng:

| DBMS | Kiểu ứng viên | Default ứng viên |
|---|---|---|
| PostgreSQL | `TIMESTAMP WITH TIME ZONE` | `CURRENT_TIMESTAMP` |
| MySQL | `TIMESTAMP` hoặc `DATETIME` theo chính sách timezone | `CURRENT_TIMESTAMP` |
| SQL Server | `DATETIME2` nếu lưu UTC theo quy ước ứng dụng; hoặc `DATETIMEOFFSET` nếu cần offset | `SYSUTCDATETIME()` hoặc expression phù hợp |
| Oracle | `TIMESTAMP WITH TIME ZONE` hoặc kiểu được chốt | `SYSTIMESTAMP` |

Không nên copy cùng một `defaultValueComputed` vào mọi nhánh rồi coi như xong. MySQL `TIMESTAMP` có quy tắc chuyển đổi theo session time zone; `DATETIME` không tự mang timezone. SQL Server `DATETIME2` không chứa offset; `DATETIMEOFFSET` có. PostgreSQL `TIMESTAMPTZ` lưu instant và hiển thị theo timezone session. Oracle `SYSTIMESTAMP` trả giá trị có timezone của hệ thống. Cần quyết định chuẩn lưu trữ, cấu hình session/connection và cách Java đọc.

Backfill dữ liệu cũ cũng cần nguồn đáng tin. Nếu không có timestamp lịch sử, dùng mốc migration có thể là quyết định nghiệp vụ riêng; đừng giả mạo thời điểm tạo thật. Sau khi xác định hợp đồng, tạo các changeset theo DBMS, chạy `update-sql`, áp dụng trên từng engine và kiểm thử round-trip từ database qua driver đến API.

## 14. Checklist trước khi merge changelog đa DBMS

- [ ] Đã định nghĩa ý nghĩa nghiệp vụ của từng cột, default và tên object.
- [ ] Đã chọn kiểu tổng quát khi tương thích, hoặc có nhánh DBMS rõ ràng khi cần.
- [ ] Đã kiểm tra precision/scale, length, Unicode, timezone, nullability và constraint.
- [ ] Đã phân biệt `defaultValue*` literal với `defaultValueComputed` expression.
- [ ] Hàm default phù hợp DBMS/version và đúng ngữ nghĩa transaction/timezone.
- [ ] Default schema và schema metadata Liquibase được cấu hình rõ.
- [ ] Tên object tránh reserved word, mixed-case không cần thiết và giới hạn độ dài.
- [ ] Constraint/index có tên ổn định, không phụ thuộc tên tự sinh giữa môi trường.
- [ ] Nhánh `dbms` loại trừ nhau và mỗi database chọn đúng một cách triển khai.
- [ ] `modifySql` chỉ biến đổi phần SQL cần thiết, không thay thế rộng gây tác dụng phụ.
- [ ] Raw SQL có phạm vi DBMS rõ và rollback cùng dialect.
- [ ] Chạy `validate`, `status --verbose`, `update-sql` và `update` thử trên từng DBMS/version hỗ trợ.
- [ ] Đối chiếu metadata schema/default/constraint sau thực thi, không chỉ đọc `DATABASECHANGELOG`.
- [ ] Kiểm thử driver, ứng dụng Spring Boot, dữ liệu biên và round-trip.
- [ ] Có kế hoạch chuyển đổi dữ liệu/rollback/forward-fix; không sửa changeset đã phát hành.
- [ ] CI/CD giữ cùng artifact, Liquibase version, extension và cấu hình với môi trường triển khai.

**Kết luận:** quản lý nhiều DBMS bằng Liquibase cần giữ **một hợp đồng dữ liệu và hành vi nghiệp vụ nhất quán**, đồng thời chấp nhận rằng kiểu vật lý, hàm mặc định, identifier và DDL có thể khác. Dùng kiểu tổng quát khi phù hợp, tách changeset bằng `dbms` khi cần và kiểm soát SQL native/`modifySql` bằng preview cùng thử nghiệm trên từng engine. Đặt tên schema, constraint và index ổn định; phân biệt literal với biểu thức default; xác minh timezone, precision, quoting và giới hạn identifier. Khi kết hợp các quy tắc này với changelog, checksum, lịch sử, rollback và CI/CD, `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` có thể quản lý schema nhất quán về ý nghĩa trên nhiều hệ quản trị.
