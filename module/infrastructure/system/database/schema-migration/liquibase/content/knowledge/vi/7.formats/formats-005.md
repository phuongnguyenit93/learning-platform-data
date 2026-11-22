# Đối chiếu khả năng biểu đạt giữa XML, YAML, JSON và formatted SQL trong Liquibase

## 1. Vì sao cần so sánh các định dạng changelog?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase qua **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một quyết định kiến trúc quan trọng là chọn **định dạng changelog**: XML, YAML, JSON hay formatted SQL.

Liquibase có cùng mô hình cốt lõi cho các định dạng: một changelog chứa các changeset có danh tính, điều kiện thực thi và nội dung thay đổi; trạng thái thực thi được theo dõi trong `DATABASECHANGELOG` và các runner được điều phối bằng `DATABASECHANGELOGLOCK`. Nhưng **khả năng diễn đạt**, mức phụ thuộc vào hệ quản trị cơ sở dữ liệu (DBMS), cách kiểm tra cú pháp và khả năng tổ chức file của từng định dạng không hoàn toàn giống nhau.

Điều cần phân biệt ngay từ đầu:

- **XML, YAML, JSON** là các định dạng changelog có cấu trúc. Chúng có thể biểu đạt những *change type* do Liquibase cung cấp, như `createTable`, `addColumn`, `addForeignKeyConstraint`, `createIndex`, `insert` hoặc `sql`; Liquibase từ đó sinh SQL tương ứng nếu change type được DBMS hỗ trợ.
- **Formatted SQL** là tệp SQL có các comment chỉ thị đặc biệt để Liquibase nhận biết changelog và ranh giới changeset. Nhà phát triển viết trực tiếp SQL của DBMS; Liquibase quản lý việc phát hiện changeset, checksum, lịch sử, phạm vi chạy và rollback được khai báo theo cú pháp supported của phiên bản.

Không có quy tắc “định dạng A luôn tốt hơn B”. Việc lựa chọn phụ thuộc vào độ phức tạp của migration, số DBMS cần hỗ trợ, yêu cầu review, công cụ của nhóm, quy tắc tổ chức changelog và phiên bản Liquibase đang sử dụng.

## 2. Mô hình chung trước khi nhìn vào cú pháp

Một changelog được thiết kế tốt phải trả lời được những câu hỏi giống nhau ở cả bốn định dạng:

| Thành phần | Câu hỏi thiết kế | Tác động khi chạy |
|---|---|---|
| Điểm vào changelog | File gốc nào được Liquibase nạp? | Xác định tập tin và thứ tự changeset được xét |
| Định danh changeset | `id`, `author`, danh tính file là gì? | Đối chiếu lịch sử trong `DATABASECHANGELOG` |
| Thao tác thay đổi | Tạo bảng, thêm cột, cập nhật dữ liệu hay SQL nào? | Quyết định DDL/DML sẽ được gửi xuống DBMS |
| Điều kiện | Cần precondition, context, label hoặc `dbms` nào? | Chặn, chọn lọc hoặc giới hạn việc thực thi |
| Transaction | Changeset có thể chạy nguyên tử không? | Ảnh hưởng cách khôi phục khi thất bại |
| Rollback | Có thể đảo ngược thao tác một cách an toàn không? | Xác định cách quay lại trạng thái trước thay đổi |
| Lịch sử và checksum | Có thay đổi nội dung/danh tính changeset đã triển khai không? | Ảnh hưởng phát hiện thay đổi và nguy cơ chạy lại |

Trong ba định dạng có cấu trúc, Liquibase đọc các node/thuộc tính thành đối tượng changelog và change type. Trong formatted SQL, Liquibase tách file theo các directive comment như `--changeset`, sau đó xử lý các câu SQL tương ứng. Hai cách đều tạo changeset mà Liquibase theo dõi, nhưng **không đồng nghĩa mọi tính năng có cùng cú pháp hoặc cùng mức hỗ trợ**.

## 3. Cùng một migration được viết bằng bốn định dạng

Giả sử dùng **PostgreSQL**, đã có bảng `customer`, và muốn thêm cột tùy chọn `preferred_name VARCHAR(120)`. Bốn ví dụ dưới đây minh họa **cùng mục đích schema**, không phải bốn changeset cần chạy nối tiếp. Khi thực hành, chỉ chọn **một** ví dụ trên một database thử nghiệm; nếu chạy cả bốn, lần thứ hai sẽ gặp lỗi cột đã tồn tại.

### 3.1. XML: thay đổi biểu đạt bằng thẻ và thuộc tính

```xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="add-preferred-name" author="database-team">
        <addColumn tableName="customer">
            <column name="preferred_name" type="VARCHAR(120)"/>
        </addColumn>
        <rollback>
            <dropColumn tableName="customer" columnName="preferred_name"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
```

XML dùng cấu trúc lồng nhau dễ nhận diện qua thẻ: `<changeSet>`, `<addColumn>`, `<column>` và `<rollback>`. Khai báo namespace và schema là thành phần quan trọng trong các ví dụ XML chuẩn; địa chỉ XSD và các thuộc tính được chấp nhận phụ thuộc phiên bản Liquibase. Một số nhóm cố định XSD theo phiên bản để dễ kiểm soát thay đổi schema, thay vì luôn dùng `dbchangelog-latest.xsd`.

Điểm mạnh của XML là cấu trúc hiển thị rõ và có thể được IDE hỗ trợ kiểm tra theo XSD. Điểm yếu thường gặp là cú pháp dài, nhiều thẻ đóng/mở và khó đọc khi một changeset có nhiều thuộc tính lồng nhau. Ngoài XML hợp lệ, còn phải bảo đảm **ngữ nghĩa Liquibase** hợp lệ; việc XML parser chấp nhận cú pháp không tự bảo đảm migration chạy được.

### 3.2. YAML: cùng change type với cấu trúc thụt lề

```yaml
databaseChangeLog:
  - changeSet:
      id: add-preferred-name
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: preferred_name
                  type: VARCHAR(120)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: preferred_name
```

YAML thể hiện hierarchy bằng thụt lề và danh sách bằng dấu `-`. Nó ngắn hơn XML, khá thuận tiện cho review trong Git và cho nhóm đã dùng YAML trong Spring Boot, Kubernetes hoặc pipeline. Tuy vậy, sai thụt lề có thể đưa thuộc tính sang một node khác hoặc khiến changelog không parse được; kiểu scalar (chuỗi, boolean, số) cũng có thể bị diễn giải không như dự kiến. Khi giá trị chứa ký tự đặc biệt, dấu `:`, `#` hoặc có dạng dễ gây nhầm kiểu, nên trích dẫn/escape thích hợp.

YAML không tự làm migration “mềm dẻo” hơn XML. Trong hai ví dụ trên, Liquibase đều nhận change type `addColumn` và `dropColumn`; mức tương thích DBMS chủ yếu đến từ change type, kiểu dữ liệu và khả năng của cơ sở dữ liệu.

### 3.3. JSON: cấu trúc rõ ràng, phù hợp sinh tự động

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "add-preferred-name",
        "author": "database-team",
        "changes": [
          {
            "addColumn": {
              "tableName": "customer",
              "columns": [
                {
                  "column": {
                    "name": "preferred_name",
                    "type": "VARCHAR(120)"
                  }
                }
              ]
            }
          }
        ],
        "rollback": [
          {
            "dropColumn": {
              "tableName": "customer",
              "columnName": "preferred_name"
            }
          }
        ]
      }
    }
  ]
}
```

JSON có cấu trúc object/array và quy tắc trích dẫn chặt chẽ, thuận lợi khi changelog được sinh, chuyển đổi hoặc kiểm tra bằng công cụ thao tác JSON. Mọi tên key và giá trị chuỗi phải được đặt trong dấu ngoặc kép; **JSON chuẩn không cho phép comment và dấu phẩy thừa ở phần tử cuối**. Vì vậy việc thêm ghi chú trực tiếp cho người đọc kém thuận tiện hơn YAML/XML, và file thường dài khi nhiều change type có các node lồng sâu.

Tương tự XML/YAML, JSON chứa change type Liquibase, vì thế có thể tận dụng cơ chế sinh SQL và metadata changeset của Liquibase. Sự khác biệt chủ yếu là biểu diễn, trải nghiệm biên tập và xử lý cú pháp.

### 3.4. Formatted SQL: viết SQL trực tiếp và đánh dấu changeset bằng comment

```sql
--liquibase formatted sql

--changeset database-team:add-preferred-name
ALTER TABLE customer ADD COLUMN preferred_name VARCHAR(120);

--rollback ALTER TABLE customer DROP COLUMN preferred_name;
```

Dòng `--liquibase formatted sql` khai báo file là changelog SQL của Liquibase. Dòng `--changeset author:id` mở một changeset; câu SQL bên dưới là nội dung thay đổi. Dòng `--rollback` chỉ ra SQL đảo ngược cho changeset. Các directive dùng cú pháp comment đặc biệt, cần giữ chính xác để Liquibase nhận diện chúng; chúng không phải comment SQL thông thường về mặt xử lý của Liquibase.

Với formatted SQL, người viết chủ động chọn cú pháp `ALTER TABLE` cụ thể cho PostgreSQL. Đó là lợi thế nếu nhóm cần SQL đặc thù hoặc tối ưu hóa rõ ràng, nhưng cũng là trách nhiệm: lệnh có thể không chạy trên một DBMS khác hoặc một phiên bản DBMS cũ. Liquibase **không chuyển một câu SQL PostgreSQL tùy ý thành câu SQL tương đương cho Oracle, SQL Server hay MySQL**.

Nếu không khai báo rollback thích hợp, đừng mặc định Liquibase có thể tự suy ra câu đảo ngược từ SQL tự viết. Hơn nữa, dù có `DROP COLUMN`, rollback vẫn có thể làm mất dữ liệu đã ghi vào cột sau khi triển khai. Bài thực hành cần xác nhận mức độ an toàn của rollback bằng kiểm thử dữ liệu đại diện.

### 3.5. Bốn file có cùng mục đích nhưng không có cùng danh tính lịch sử

Các ví dụ dùng cùng `id` và `author` để dễ đối chiếu, nhưng trong thực tế **danh tính changeset còn xét đến đường dẫn/danh tính file changelog** (hoặc `logicalFilePath` nếu cấu hình). Vì vậy `changes/001.xml`, `changes/001.yaml`, `changes/001.json` và `changes/001.sql` có thể được Liquibase xem là các changeset khác nhau. Không được nạp cả bốn vào cùng một changelog với ý nghĩ Liquibase sẽ tự hiểu chúng là các bản dịch tương đương.

Một khi changeset đã triển khai, đổi định dạng hoặc chuyển đường dẫn là một thay đổi cần kiểm soát lịch sử, không chỉ là chỉnh phong cách trình bày.

## 4. Ma trận khả năng biểu đạt và giới hạn

| Nhu cầu | XML | YAML | JSON | Formatted SQL |
|---|---|---|---|---|
| Khai báo change type như `createTable`, `addColumn`, `createIndex` | Có, qua phần tử | Có, qua mapping/danh sách | Có, qua object/array | Không dùng change type dạng khai báo; thường viết SQL tương đương |
| Viết SQL thủ công | Có, qua các change type SQL được hỗ trợ | Có | Có | Là nội dung chính của changeset |
| Chia file changelog bằng `include`/`includeAll` | Hỗ trợ theo cấu trúc XML | Hỗ trợ theo cấu trúc YAML | Hỗ trợ theo cấu trúc JSON | Mức hỗ trợ directive phụ thuộc phiên bản; phải kiểm tra trước khi dùng |
| Precondition | Cấu trúc có khả năng biểu đạt nhiều loại điều kiện | Cấu trúc tương đương | Cấu trúc tương đương | Dùng comment directive cho các điều kiện được hỗ trợ; không mặc định tương đương 1:1 |
| Context, label, giới hạn DBMS | Thuộc tính/node changeset | Trường changeset | Thuộc tính object | Directive/thuộc tính changeset được phiên bản hỗ trợ |
| Khai báo rollback | `<rollback>` chứa thay đổi hoặc SQL | `rollback` chứa change type hoặc SQL | `rollback` dưới dạng cấu trúc | Thường viết câu rollback bằng `--rollback` hoặc cơ chế SQL được hỗ trợ |
| Tận dụng SQL do Liquibase sinh theo DBMS | Có, với change type tương ứng | Có | Có | Không đối với câu SQL tùy ý do tác giả viết |
| Kiểm tra cú pháp | XML parser, XSD và Liquibase validation | YAML parser và Liquibase validation | JSON parser và Liquibase validation | Nhận diện directive của formatted SQL và parse/validate Liquibase; SQL còn phải được DBMS chấp nhận |
| Khả năng đọc diff | Tường minh nhưng dài | Gọn, phụ thuộc thụt lề | Cấu trúc máy dễ xử lý nhưng nhiều dấu | SQL gần với kết quả trên DBMS, dễ review cho DBA quen SQL |

**Lưu ý về phiên bản:** bảng so sánh các khả năng phổ biến, không phải hợp đồng hỗ trợ cho mọi bản Liquibase Community, Pro hay mọi release. Một tính năng có trong XML không có nghĩa bản CLI hiện dùng đã hỗ trợ cùng cú pháp trong formatted SQL. Hãy kiểm tra tài liệu của đúng phiên bản, plugin đang cài và DBMS mục tiêu.

## 5. Các chủ đề dễ có khác biệt về khả năng biểu đạt

### 5.1. Precondition: điều kiện cấu trúc so với điều kiện viết bằng SQL

Trong XML, có thể gắn điều kiện tồn tại bảng trực tiếp lên changeset:

```xml
<changeSet id="add-preferred-name" author="database-team">
    <preConditions onFail="HALT">
        <tableExists tableName="customer"/>
    </preConditions>
    <addColumn tableName="customer">
        <column name="preferred_name" type="VARCHAR(120)"/>
    </addColumn>
</changeSet>
```

Trong YAML, cùng ý tưởng được biểu đạt bằng danh sách `preConditions`:

```yaml
databaseChangeLog:
  - changeSet:
      id: add-preferred-name
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: preferred_name
                  type: VARCHAR(120)
```

Trong JSON, cùng metadata có dạng object/array:

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "add-preferred-name",
        "author": "database-team",
        "preConditions": [
          { "onFail": "HALT" },
          { "tableExists": { "tableName": "customer" } }
        ],
        "changes": [
          {
            "addColumn": {
              "tableName": "customer",
              "columns": [
                { "column": { "name": "preferred_name", "type": "VARCHAR(120)" } }
              ]
            }
          }
        ]
      }
    }
  ]
}
```

Formatted SQL hỗ trợ một số precondition qua dòng comment định dạng riêng. Chẳng hạn, trên PostgreSQL có thể dùng một điều kiện SQL trả về kết quả kỳ vọng:

```sql
--liquibase formatted sql
--changeset database-team:add-preferred-name
--preconditions onFail:HALT
--precondition-sql-check expectedResult:1 SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'customer';
ALTER TABLE customer ADD COLUMN preferred_name VARCHAR(120);
--rollback ALTER TABLE customer DROP COLUMN preferred_name;
```

Điều kiện SQL trên mang tính PostgreSQL và chỉ kiểm tra bảng trong schema hiện hành. Nó minh họa **cách viết điều kiện khác nhau**, không có nghĩa SQL check là bản sao hoàn toàn của `tableExists` (đặc biệt khi chạy với schema khác, quyền truy cập khác hoặc DBMS khác). Danh sách precondition được phép dùng trong formatted SQL cần được kiểm tra theo phiên bản. Nếu một chính sách yêu cầu các precondition phức tạp gồm nhiều nhánh `and`/`or`, kiểm tra metadata trừu tượng hoặc xử lý lỗi có cấu trúc, XML/YAML/JSON thường dễ biểu đạt và review hơn.

`onFail: HALT` giúp dừng khi tiền đề chưa thỏa. Tránh dùng `MARK_RAN` để che đi một bước schema bắt buộc đang thiếu: changeset có thể bị đánh dấu mà chưa hề áp dụng SQL, khiến môi trường sau đó phân kỳ.

### 5.2. Chọn changeset theo context, label và DBMS

Các trường như context, label và `dbms` giúp điều khiển phạm vi changeset. Trong dạng có cấu trúc, chúng thường là metadata đặt trên `changeSet`. Ví dụ YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: seed-customer-development
      author: database-team
      contextFilter: development
      labels: seed
      dbms: postgresql
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 1001
```

Một formatted SQL changeset cũng có thể mang các thuộc tính như `dbms`, context/label theo cú pháp mà phiên bản Liquibase hỗ trợ; ví dụ hình thức thường gặp:

```sql
--liquibase formatted sql
--changeset database-team:seed-customer-development dbms:postgresql contextFilter:development labels:seed
INSERT INTO customer (id) VALUES (1001);
--rollback DELETE FROM customer WHERE id = 1001;
```

Tham số lọc của CLI/Spring Boot và cú pháp context trên changeset có thể thay đổi theo phiên bản (có release dùng `context`, release mới dùng `contextFilter`). Quan trọng hơn, context/label là **bộ lọc thực thi**, không phải cách Liquibase tự suy ra quan hệ phụ thuộc: changeset thêm khóa ngoại không được chạy nếu changeset tạo bảng tiền đề bị lọc khỏi môi trường hiện tại.

### 5.3. Thao tác schema trừu tượng so với cú pháp phụ thuộc DBMS

Với `addColumn` dạng XML/YAML/JSON, Liquibase biết đây là thao tác thêm cột và có thể dùng SQL generator thích hợp với từng DBMS được hỗ trợ. Tuy vậy, tính portable không tuyệt đối: kiểu `VARCHAR(120)`, thuộc tính identity, default expression, generated column, index, ràng buộc hoặc transaction DDL vẫn có khác biệt giữa DBMS. Một change type có thể không được hỗ trợ trên một DBMS cụ thể hoặc sinh SQL cần điều chỉnh.

Với formatted SQL, tác giả chủ động viết cú pháp PostgreSQL, MySQL, Oracle hoặc SQL Server. Cách này phù hợp cho biểu thức chuyên biệt, chỉ mục đặc thù, CTE hoặc backfill phức tạp; đổi DBMS thường đòi hỏi viết nhánh SQL khác hoặc sử dụng bộ changelog tách biệt có điều kiện rõ ràng.

Ngay cả trong XML/YAML/JSON, tác giả vẫn có thể viết SQL thủ công qua change type `sql` hoặc `sqlFile`. Do đó sự khác biệt là **mức độ dựa vào các change type của Liquibase**, không đơn thuần là file có chứa câu SQL hay không.

### 5.4. Transaction, câu lệnh chứa dấu chấm phẩy và `runInTransaction`

Changeset thường chạy trong transaction khi DBMS và loại thao tác cho phép. Liquibase có metadata `runInTransaction` trong các định dạng hỗ trợ. Việc đặt `runInTransaction: false` có thể cần cho một số câu lệnh đặc thù, nhưng làm tăng khả năng migration dở dang nếu có nhiều lệnh và lệnh sau thất bại. Không nên đổi tùy chọn này chỉ để vượt lỗi mà chưa hiểu đặc điểm DBMS.

Trong formatted SQL, còn có khác biệt giữa **Liquibase tách câu SQL** và **DBMS thực thi câu SQL**. Một function, stored procedure hoặc block có dấu `;` bên trong có thể cần cấu hình delimiter/splitStatements theo cú pháp phiên bản, hoặc cách thực thi phù hợp với native executor nếu được sử dụng. Với SQL thủ công trong XML/YAML/JSON, thay đổi kiểu `sql`/`sqlFile` cũng có những tùy chọn tách lệnh liên quan. Vì vậy không được suy rằng cứ đổi phần mở rộng sang `.sql` là xử lý được mọi stored procedure.

## 6. Rollback và khả năng phục hồi

### 6.1. Mọi định dạng đều cần thiết kế rollback theo dữ liệu thực tế

Một số change type dạng khai báo cho phép Liquibase sinh rollback tương ứng trên các DBMS được hỗ trợ. Nhưng không phải thay đổi nào cũng tự đảo ngược được, đặc biệt là `dropTable`, `dropColumn`, migration dữ liệu hay SQL tùy chỉnh. Trong formatted SQL, rollback cho SQL thủ công thường phải được **viết rõ** qua các directive hỗ trợ như `--rollback`.

Ví dụ thêm cột `preferred_name` có thể rollback bằng xóa cột, nhưng khi ứng dụng đã ghi dữ liệu vào cột, việc xóa cột làm mất những dữ liệu ấy. Một câu rollback hợp lệ về cú pháp chưa chắc là phương án phục hồi an toàn. Với update dữ liệu hoặc chuẩn hóa nhiều bảng, cần cân nhắc backup, forward-fix, bảng ánh xạ hoặc ghi lại giá trị cũ trước khi thay đổi.

### 6.2. So sánh cách biểu đạt rollback

| Vấn đề | XML/YAML/JSON | Formatted SQL |
|---|---|---|
| Đảo ngược `addColumn` | Có thể khai báo `dropColumn` hoặc dựa vào khả năng auto rollback của change type nếu DBMS hỗ trợ | Viết SQL `ALTER TABLE ... DROP COLUMN` qua directive rollback |
| Đảo ngược `UPDATE` dữ liệu | Có thể khai báo `update`/`sql`, nhưng cần biết giá trị cũ | Thường phải viết SQL đảo ngược cụ thể hoặc chiến lược phục hồi dữ liệu |
| Rollback nhiều bước | Có cấu trúc thay đổi nối tiếp trong `rollback` | Có thể cần nhiều directive/dòng SQL theo cú pháp Liquibase hỗ trợ |
| Kiểm tra trước triển khai | Dùng công cụ rollback SQL và chạy thử trên DB thử nghiệm | Cũng phải tạo/xem rollback SQL và chạy thử trên DB thử nghiệm |

Một chiến lược hợp lý cho production là ưu tiên thay đổi tương thích ngược kiểu expand–migrate–contract. Khi cần rollback ứng dụng, schema mới vẫn còn đủ để ứng dụng phiên bản cũ hoạt động trong giai đoạn chuyển đổi; bước xóa cấu trúc cũ chỉ diễn ra sau khi chắc chắn không còn phụ thuộc.

## 7. Include, includeAll và tổ chức nhiều file

Với XML/YAML/JSON, changelog gốc có thể tổ chức các file con bằng `include` và `includeAll`. Ví dụ YAML:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-preferred-name.yaml
      relativeToChangelogFile: true
```

Trong XML, có thể biểu đạt cùng cách nạp bằng `<include file="..." relativeToChangelogFile="true"/>`. Trong JSON, phần tử tương ứng thường là object `include` có `file` và `relativeToChangelogFile`.

Khả năng diễn đạt `include` và `includeAll` ngay trong formatted SQL đã được mở rộng theo các phiên bản Liquibase. Không nên mặc định mọi phiên bản đều hỗ trợ cùng tập directive, filtering, đường dẫn tương đối hoặc hành vi đệ quy. Trước khi quyết định dùng formatted SQL như master changelog của một repository lớn, cần xác minh **tính năng include của phiên bản đang khóa trong CI/CD**; nếu không đủ, có thể dùng master XML/YAML/JSON để nạp các file formatted SQL con.

Khi dùng nhiều file, cả bốn định dạng đều phải lưu ý:

1. **Tránh vòng tham chiếu:** changelog A nạp B thì B không được nạp trở lại A.
2. **Tránh nạp trùng:** một file changeset nên có một đường nạp có chủ đích từ master.
3. **Thứ tự tường minh:** changeset tạo bảng phải xuất hiện trước changeset thêm khóa ngoại phụ thuộc vào bảng.
4. **Đường dẫn ổn định:** tránh đổi tên hoặc chuyển file sau khi đã chạy mà chưa có kế hoạch giữ danh tính.
5. **Kiểm chứng theo môi trường:** cùng master nhưng context/label khác nhau có thể tạo tập changeset thực thi khác nhau.

Định dạng file không tự giải quyết được những vấn đề cấu trúc. Một repository YAML vẫn có thể `includeAll` nạp trùng; một repository XML vẫn có thể tạo vòng; một master nạp nhiều formatted SQL vẫn có thể chứa SQL phụ thuộc sai thứ tự.

## 8. Checksum, `DATABASECHANGELOG` và chuyển đổi định dạng sau triển khai

Khi Liquibase thực thi changeset, nó ghi thông tin vào `DATABASECHANGELOG`, bao gồm các trường nhận diện thường gặp là `ID`, `AUTHOR`, `FILENAME`, cùng checksum (`MD5SUM`), thời gian và kiểu thực thi. Danh tính changeset được xác định thông thường từ **id + author + danh tính file changelog**. `logicalFilePath` có thể được dùng để giữ danh tính logic theo cơ chế được phiên bản hỗ trợ.

Giả sử `db/changelog/changes/002-add-preferred-name.xml` đã chạy. Nếu thay nó bằng `002-add-preferred-name.yaml`, dù thay đổi schema về mặt ý tưởng tương đương, Liquibase vẫn có thể nhận diện thành changeset mới vì `FILENAME` đã khác. Nếu cố giữ danh tính cũ bằng `logicalFilePath`, còn phải kiểm tra **checksum của changeset được tính từ nội dung logic như thế nào**; việc chuyển cách biểu đạt có thể làm checksum thay đổi tùy change type và cách chuyển đổi. Không thể kết luận “cùng SQL sinh ra thì checksum sẽ giống nhau” nếu chưa kiểm tra thực tế.

Để chuyển định dạng một cách an toàn khi hệ thống đã chạy migration:

1. **Ưu tiên giữ nguyên changeset đã triển khai.** Có thể sử dụng định dạng mới cho changeset tương lai mà không cần dịch lại lịch sử.
2. Nếu bắt buộc di chuyển file, ghi nhận `ID`, `AUTHOR`, `FILENAME`, `MD5SUM` của các changeset cũ từ bản sao database đại diện.
3. Xác định cách giữ danh tính logic và kiểm tra xem version Liquibase hiện tại hỗ trợ `logicalFilePath` ở vị trí khai báo cần dùng hay không.
4. Chạy `validate`, `status --verbose`, `update-sql` trên database đã có lịch sử, xác nhận changeset cũ không bị đưa vào danh sách pending ngoài ý định.
5. Thử trên database sạch để xác nhận thay đổi về cấu trúc include không làm mất changeset hoặc đảo thứ tự.
6. Nếu checksum khác, phân tích lý do và chọn quy trình chuyển đổi có kiểm soát; không tự động sửa `DATABASECHANGELOG`, đổi `id` hoặc dùng `clear-checksums` để che một chuyển đổi chưa được xác minh.

**Bài học then chốt:** quyết định định dạng nên được đưa ra sớm và nhất quán. Đổi định dạng changelog đã triển khai là công việc liên quan đến lịch sử migration, cần kiểm chứng cả trên database sạch lẫn database đã có bản ghi `DATABASECHANGELOG`.

## 9. Chọn định dạng nào cho từng tình huống?

| Tình huống | Điểm xuất phát hợp lý | Lý do và điều kiện |
|---|---|---|
| Ứng dụng Java/Spring Boot dùng một DBMS và nhóm muốn changelog gọn, dễ review | YAML | Dễ đọc và có change type, precondition, rollback; yêu cầu kỷ luật thụt lề |
| Tổ chức cần cấu trúc tường minh, schema validation và công cụ XML | XML | XSD có thể hỗ trợ IDE; phù hợp file có nhiều thuộc tính phức tạp, chấp nhận cú pháp dài |
| Changelog sinh từ công cụ tự động hoặc pipeline xử lý JSON | JSON | Object/array dễ thao tác máy; quy tắc cú pháp nghiêm ngặt, không hỗ trợ comment chuẩn |
| DBA review và tối ưu PostgreSQL/SQL Server/Oracle cụ thể, nhiều câu SQL đặc thù | Formatted SQL | SQL tường minh, dễ so với execution plan; cần tự kiểm soát khác biệt DBMS và rollback |
| Cần hỗ trợ nhiều DBMS mà thay đổi chủ yếu là DDL phổ thông | XML/YAML/JSON với change type | Tận dụng SQL generator; vẫn kiểm thử từng DBMS, nhất là datatype và constraint |
| Có thư viện SQL dùng lại nhưng muốn metadata/precondition có cấu trúc | XML/YAML/JSON với `sqlFile` hoặc `sql` | Giữ metadata Liquibase rõ, thực thi SQL thủ công khi cần |
| Nhiều nhóm triển khai song song, nhiều release, include phức tạp | Master XML/YAML/JSON hoặc cách khác được version xác nhận | Thứ tự include rõ ràng, kiểm soát ownership và danh tính changeset |

Quyết định không nhất thiết áp dụng một định dạng duy nhất cho tất cả file. Ví dụ, changelog gốc YAML có thể nạp một file SQL formatted cho migration PostgreSQL phức tạp. Tuy nhiên, kết hợp định dạng cần có quy ước về vị trí file, review, naming và cách kiểm tra để không làm tập changeset trở nên khó dự đoán.

### 9.1. Gợi ý quy chuẩn cho repository

Một nhóm có thể thống nhất:

```text
db/changelog/
  db.changelog-master.yaml
  releases/
    2026-01.yaml
    2026-02.yaml
  changes/
    2026-01/
      001-create-customer.yaml
      002-add-preferred-name.yaml
    2026-02/
      001-backfill-preferred-name.sql
```

Master YAML nạp các release theo thứ tự; mỗi release nạp đúng file mà release đó sở hữu. File `001-backfill-preferred-name.sql` chỉ được sử dụng dưới dạng **formatted SQL** nếu chứa các directive hợp lệ hoặc được nạp bằng cơ chế `sqlFile` tương ứng, tùy thiết kế; hai trường hợp này khác nhau về cách xác định ranh giới changeset và rollback. Đừng chỉ nhìn phần mở rộng `.sql` để suy ra Liquibase sẽ hiểu file đó theo chế độ nào.

Quy chuẩn nên định nghĩa `id`, `author`, vị trí file, cách dùng rollback, chính sách precondition, tiêu chí chọn context/label và cách review migration dữ liệu lớn. Việc này có giá trị hơn tranh luận định dạng nào ngắn hơn vài dòng.

## 10. Quy trình kiểm chứng khi dùng XML, YAML, JSON hoặc SQL

### 10.1. Kiểm chứng bằng cùng một bộ tiêu chí

Một bài thực hành có kiểm chứng không dừng ở việc file parse được. Quy trình cơ bản:

1. **Chọn DBMS và version Liquibase** cố định cho bài thực hành; xác nhận driver, quyền truy cập và cấu hình metadata.
2. **Chọn một trong bốn file tương đương**, cấu hình `changeLogFile` hoặc `--changelog-file` tới file đó; dùng database thử nghiệm ban đầu có bảng `customer` và chưa có cột `preferred_name`.
3. Chạy `validate` để bắt lỗi cấu trúc và tham chiếu mà Liquibase có thể phát hiện.
4. Chạy `status --verbose` để xác định changeset pending.
5. Chạy `update-sql` và review SQL dự kiến; so sánh phần SQL của ba change type khai báo với câu SQL formatted.
6. Chạy `update`, sau đó đọc trạng thái schema và `DATABASECHANGELOG` để xác nhận `id`, `author`, `FILENAME` và kiểu thực thi.
7. Thử đường rollback theo cơ chế phù hợp của phiên bản đang dùng trên database test, rồi xác minh cột được xóa và đánh giá dữ liệu bị ảnh hưởng.
8. Lặp lại quy trình trên database mới và trên bản sao database đã có lịch sử nếu đang chuẩn bị chuyển đổi định dạng hoặc phát hành sản phẩm thật.

Ví dụ chuỗi lệnh đọc/kiểm tra trên môi trường thử nghiệm:

```bash
liquibase --defaults-file=config/liquibase-test.properties validate
liquibase --defaults-file=config/liquibase-test.properties status --verbose
liquibase --defaults-file=config/liquibase-test.properties update-sql
```

Các lệnh minh họa giả định file defaults đã trỏ tới một changelog thích hợp và database thử nghiệm. Nếu lệnh CLI hoặc tham số cụ thể thay đổi theo phiên bản, dùng `liquibase --help` và phần trợ giúp của command tương ứng. `update-sql` hiển thị SQL dự kiến nhưng chưa thực thi DDL; chỉ `update` mới thay đổi schema. Thử rollback phải dùng bản sao an toàn vì rollback có thể xóa dữ liệu.

### 10.2. Tách kiểm tra cú pháp, ngữ nghĩa và trạng thái database

| Tầng kiểm tra | Điều cần biết | Ví dụ lỗi không được tầng đó đảm bảo phát hiện |
|---|---|---|
| Parser XML/YAML/JSON hoặc directive formatted SQL | File có đúng cú pháp biểu diễn không? | Bảng đích chưa tồn tại, thiếu quyền ALTER TABLE |
| `liquibase validate` | Changelog và nhiều quy tắc Liquibase có hợp lệ không? | Dữ liệu không đáp ứng khóa ngoại, SQL không tương thích trạng thái runtime |
| `update-sql` | SQL dự kiến được sinh ra theo cấu hình và DBMS là gì? | Transaction DDL không được hỗ trợ, lock đang giữ, lỗi dữ liệu thực tế |
| Thực thi trên DB test | Migration có chạy được trên trạng thái thử nghiệm không? | Khác biệt dữ liệu và quyền giữa test và production |
| Kiểm tra trên bản sao dữ liệu thật | Migration và rollback có phù hợp trường hợp thực tế không? | Biến động tải hoặc thay đổi ngoài quy trình sau khi sao chép |

Nhờ phân tầng, nhóm tránh hiểu nhầm rằng chuyển sang XML là có thể bỏ kiểm thử SQL, hoặc chọn formatted SQL là không cần `validate` và kiểm tra `DATABASECHANGELOG`.

## 11. Các sai lầm thường gặp khi đối chiếu định dạng

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| XML, YAML và JSON là ba engine migration khác nhau | Chúng thường biểu đạt cùng mô hình change type và metadata của Liquibase; khác nhau chủ yếu ở cú pháp và công cụ biên tập |
| Formatted SQL chỉ là file `.sql` thuần | Nó cần header/directive đúng để Liquibase nhận biết changeset; `.sql` thuần được gọi bằng `sqlFile` có cách xử lý khác |
| Dùng change type khai báo thì luôn chạy được trên mọi DBMS | Liquibase sinh SQL theo khả năng của DBMS; không phải mọi change type, datatype và option đều portable |
| Formatted SQL không có changeset, checksum hay rollback | Nó có thể khai báo changeset, được theo dõi lịch sử và hỗ trợ rollback theo directive; khả năng cụ thể tùy phiên bản |
| Cùng `id`/`author` thì đổi XML sang YAML chắc chắn là cùng changeset | Danh tính còn có đường dẫn logic; đổi file có thể làm changeset xuất hiện như mới |
| Cùng SQL tạo ra thì checksum chắc chắn không đổi | Checksum phụ thuộc cách Liquibase xử lý nội dung changeset; cần kiểm tra thực tế khi chuyển đổi |
| Có precondition nghĩa là thứ tự phụ thuộc không còn quan trọng | Precondition bảo vệ điều kiện; tiền đề schema và thứ tự nạp vẫn phải được tổ chức đúng |
| Rollback sinh ra được là rollback an toàn | Rollback có thể mất dữ liệu hoặc không phù hợp trạng thái ứng dụng hiện tại |
| Một file YAML parse được là changelog chắc chắn hợp lệ | Còn phải validate, kiểm tra DBMS, SQL sinh ra, trạng thái dữ liệu và lịch sử |

## 12. Checklist lựa chọn và quản lý định dạng changelog

- [ ] Nhóm đã xác định DBMS, phiên bản Liquibase và các extension/edition thực tế.
- [ ] Mọi người hiểu XML/YAML/JSON dùng change type, còn formatted SQL đặt SQL thủ công làm trung tâm.
- [ ] Đã chọn cú pháp changelog nhất quán và có tiêu chí rõ ràng cho trường hợp cần formatted SQL.
- [ ] Các ví dụ, property name, precondition và directive được kiểm tra trên phiên bản hiện dùng.
- [ ] `id`, `author`, danh tính file và `logicalFilePath` được quản lý ổn định sau khi triển khai.
- [ ] Không đưa nhiều bản biểu đạt tương đương của cùng migration vào một luồng nạp.
- [ ] Trình tự include/includeAll và các tiền đề của changeset được review bằng cùng một tiêu chí ở mọi định dạng.
- [ ] Các thay đổi SQL đặc thù DBMS có chiến lược scope qua DBMS/context/label phù hợp.
- [ ] Mỗi changeset có kế hoạch rollback hoặc forward-fix được đánh giá theo dữ liệu thực tế.
- [ ] CI/CD chạy `validate`, `status` và review `update-sql` với đúng changelog, connection và context/label.
- [ ] Đã kiểm thử trên database sạch và database có lịch sử trước khi đổi định dạng của migration đã triển khai.
- [ ] Các khác biệt giữa cấu hình Liquibase CLI và Spring Boot được ghi rõ để tránh chạy nhầm changelog hoặc database.

XML, YAML và JSON đều phù hợp khi muốn viết **changelog khai báo** với metadata phong phú và tận dụng các change type của Liquibase. Formatted SQL phù hợp khi SQL cụ thể là nội dung cần kiểm soát và review trực tiếp. Độ tin cậy của migration không đến từ phần mở rộng file, mà từ danh tính changeset ổn định, thứ tự phụ thuộc rõ ràng, precondition phù hợp, rollback có kiểm chứng và quy trình triển khai nhất quán giữa môi trường. Đây là nền tảng để module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` quản lý schema và dữ liệu một cách có thể kiểm tra, truy vết và vận hành an toàn.
