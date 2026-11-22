# Lỗi cú pháp XML, YAML, JSON và formatted SQL

## 1. Nhận diện đúng loại lỗi trước khi sửa

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Changelog có thể được viết bằng XML, YAML, JSON hoặc formatted SQL. Khi một lần migration thất bại, lỗi cú pháp của file changelog thường bị nhầm với lỗi SQL do database trả về. Hai nhóm lỗi xuất hiện ở các giai đoạn khác nhau và cần cách xử lý khác nhau.

**Lỗi cú pháp hoặc parse** xảy ra khi Liquibase không thể đọc file, hiểu cấu trúc hoặc nhận diện chỉ thị changeset. Ví dụ: XML thiếu thẻ đóng, YAML sai thụt lề, JSON có dấu phẩy thừa hoặc formatted SQL thiếu dòng khai báo đầu file. Trong trường hợp này, Liquibase có thể chưa tạo được mô hình changeset để thực thi.

**Lỗi thực thi** xảy ra sau khi changelog đã được đọc và Liquibase gửi câu lệnh đến DBMS. Ví dụ: thiếu quyền tạo bảng, tên cột đã tồn tại, kiểu dữ liệu không được hỗ trợ, vi phạm unique constraint hoặc câu SQL không hợp lệ với hệ quản trị đích.

Một lần chạy có thể chứa cả hai nhóm vấn đề. Chẳng hạn, sửa được YAML để parser đọc thành công nhưng sau đó database từ chối câu SQL. Vì vậy, hãy phân loại lỗi theo giai đoạn, đọc thông báo gốc và xác định changeset nào thực sự đã được áp dụng.

Bài học này hướng dẫn cách viết và kiểm tra bốn định dạng changelog, đọc lỗi parser, phân biệt chúng với lỗi DBMS, kiểm tra include/resource và xử lý an toàn sau một lần migration thất bại. Mục tiêu là sửa đúng nguyên nhân mà vẫn giữ lịch sử changeset và dữ liệu nhất quán.

## 2. Vòng đời đọc changelog và nơi lỗi có thể xuất hiện

Một quy trình Liquibase thường đi qua các bước khái quát:

```text
Tải root changelog
        |
        v
Giải quyết include / includeAll / resource
        |
        v
Parse XML / YAML / JSON / formatted SQL
        |
        v
Xây dựng changeset và kiểm tra cấu trúc
        |
        v
Kết nối database, đọc DATABASECHANGELOG
        |
        v
Xác định changeset pending
        |
        v
Kiểm tra precondition / checksum / filter
        |
        v
Sinh và thực thi SQL hoặc change type
        |
        v
Ghi lịch sử thực thi
```

Vị trí lỗi giúp thu hẹp nguyên nhân:

| Giai đoạn | Dấu hiệu thường gặp | Nhóm lỗi |
|---|---|---|
| Tải root changelog | Không tìm thấy file, sai classpath | Resource/configuration |
| Giải quyết include | File con thiếu, relative path sai | Resource/changelog graph |
| Parse XML/YAML/JSON | Parser báo line/column, token hoặc node không hợp lệ | Syntax/format |
| Parse formatted SQL | Thiếu header, directive sai định dạng | Changelog format |
| Kiểm tra changeset | Thiếu id/author, cấu trúc change không hợp lệ | Changelog validation |
| Đọc history | Không có quyền metadata, sai schema | Database access |
| Kiểm tra checksum/precondition | Checksum mismatch, HALT | Migration validation |
| Thực thi SQL | SQLState, syntax error, constraint, permission denied | DBMS execution |

Thông báo “syntax error” chưa đủ để kết luận lỗi nằm ở changelog. Cần xem lỗi do parser XML/YAML/JSON hay do DBMS parser nhận câu SQL. Log thường có stack trace và nguyên nhân lồng bên trong; hãy tìm exception gốc, file, dòng, changeset và câu lệnh liên quan.

## 3. Nguyên tắc chung khi viết changelog

Bốn định dạng đều biểu diễn root changelog và danh sách changeset, nhưng cách thể hiện cấu trúc khác nhau. Một file đúng cú pháp vẫn có thể mô tả sai migration, vì vậy cần kiểm tra cả syntax lẫn semantics.

Một changeset nên có:

- **id** ổn định và duy nhất trong phạm vi phù hợp.
- **author** theo quy ước nhóm.
- Đường dẫn logic ổn định của changelog.
- Danh sách change hoặc SQL rõ ràng.
- Precondition khi cần xác minh trạng thái đầu vào.
- Rollback phù hợp với tác động và khả năng của DBMS.
- Context, label, dbms hoặc thuộc tính thực thi khi thực sự cần.

Ví dụ cùng một ý tưởng tạo bảng có thể được biểu diễn bằng XML, YAML hoặc JSON. Với formatted SQL, changeset được khai báo bằng comment directive. Không trộn cú pháp của định dạng này vào định dạng khác.

**Quy tắc đọc file:** kiểm tra đúng root changelog mà ứng dụng/pipeline sử dụng, sau đó lần theo từng include. Một file con có cú pháp hoàn hảo nhưng không được include thì không được chạy; ngược lại, một file nháp vô tình bị include có thể làm migration thất bại.

## 4. XML: namespace, thẻ và ký tự đặc biệt

XML có cấu trúc phân cấp chặt chẽ. Mỗi thẻ mở phải có thẻ đóng tương ứng, tên thẻ phân biệt chữ hoa/thường và thuộc tính phải đặt trong dấu nháy. Liquibase XML changelog thường khai báo namespace và schema location ở phần tử gốc.

Ví dụ tối giản:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.30.xsd">

    <changeSet id="001-create-customer" author="platform-team">
        <createTable tableName="customer_account">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(320)"/>
        </createTable>
    </changeSet>
</databaseChangeLog>
```

Phiên bản XSD trong ví dụ phải phù hợp với phiên bản Liquibase của dự án và cách dự án quản lý schema. Không nên thay số phiên bản một cách máy móc khi nâng cấp. Namespace phải đúng URI của Liquibase; namespace sai có thể khiến parser không nhận diện các phần tử changelog dù XML nhìn có vẻ hợp lệ.

### 4.1. Những lỗi XML thường gặp

| Lỗi | Ví dụ sai | Cách sửa |
|---|---|---|
| Thiếu thẻ đóng | Mở changeSet nhưng không đóng | Đóng đúng thẻ và đúng thứ tự lồng nhau |
| Đóng sai tên | createTable mở, createTables đóng | Tên thẻ mở/đóng phải khớp |
| Sai chữ hoa/thường | changeset thay cho changeSet | Dùng đúng tên phần tử Liquibase |
| Thiếu dấu nháy | id=001 | Viết id="001" |
| Namespace sai | URI tự đặt hoặc thiếu namespace | Dùng namespace Liquibase chính xác |
| Thuộc tính đặt sai cấp | Đặt tableName trên changeSet | Đặt thuộc tính trong phần tử change tương ứng |
| Ký tự đặc biệt chưa escape | name="A & B" | Dùng &amp;, hoặc CDATA khi phù hợp |
| Thẻ lồng sai | Đặt column bên ngoài createTable | Tuân theo cấu trúc XSD |

Trong XML, các ký tự ampersand và dấu nhỏ hơn trong nội dung/thuộc tính thường cần escape thành &amp; và &lt;. Nếu câu SQL hoặc biểu thức có nhiều ký tự đặc biệt, có thể dùng CDATA trong vị trí XML cho phép, nhưng CDATA không thay thế việc kiểm tra cấu trúc Liquibase.

### 4.2. Kiểm tra namespace và schema location

Hai khai báo có vai trò khác nhau:

- xmlns xác định namespace của các phần tử.
- xsi:schemaLocation liên kết namespace với XSD để kiểm tra cấu trúc.

Một URL XSD sai phiên bản có thể làm IDE báo lỗi hoặc validation không như mong đợi. Hãy dùng mẫu được tạo/khuyến nghị cho phiên bản Liquibase của dự án và kiểm tra bằng đúng runtime dependency. Đừng xóa namespace chỉ để IDE hết gạch đỏ; việc đó có thể khiến Liquibase không nhận dạng changelog.

### 4.3. XML well-formed chưa chắc là changelog hợp lệ

Một XML parser chỉ xác nhận tài liệu có cấu trúc XML hợp lệ. Liquibase còn cần các phần tử và thuộc tính đúng schema changelog. Ví dụ, một thẻ XML tự đặt có thể well-formed nhưng không phải change type Liquibase hỗ trợ.

Khi gặp lỗi, phân biệt:

1. XML không well-formed: lỗi đóng/mở thẻ, quote, entity.
2. XML không hợp lệ theo XSD: phần tử/thuộc tính không đúng vị trí hoặc không được hỗ trợ.
3. Changelog parse được nhưng DBMS từ chối SQL khi thực thi.

## 5. YAML: thụt lề và kiểu dữ liệu

YAML biểu diễn cấu trúc bằng indentation và dấu gạch đầu dòng. Chỉ một cấp thụt lề sai cũng có thể thay đổi quan hệ giữa changeSet, changes, createTable, columns và column.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer"
      author: "platform-team"
      changes:
        - createTable:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
```

Cấu trúc cần đọc từ ngoài vào trong:

- databaseChangeLog là root.
- Dấu gạch đầu dòng mở một phần tử trong danh sách changeset.
- changeSet chứa metadata và danh sách changes.
- createTable chứa tableName và columns.
- columns là danh sách các column.
- constraints thuộc về column tương ứng.

### 5.1. Các lỗi YAML thường gặp

| Lỗi | Biểu hiện | Cách sửa |
|---|---|---|
| Dùng tab | Parser báo character không hợp lệ | Chỉ dùng dấu cách |
| Sai indentation | Node bị lồng sai hoặc thành sibling | Căn lại cấp thụt lề nhất quán |
| Thiếu dấu gạch đầu dòng | Phần tử danh sách không được nhận diện | Thêm dấu - đúng cấp |
| Sai vị trí dấu hai chấm | Parser hiểu key/value sai | Dùng key: value |
| Chuỗi có : hoặc # | Giá trị bị tách hoặc comment ngoài ý muốn | Đặt chuỗi trong quote |
| Quote không đóng | Parser báo unexpected end | Đóng dấu nháy tương ứng |
| Boolean/null ngoài ý muốn | Giá trị bị parse thành kiểu khác | Quote khi muốn giữ chuỗi |
| Block SQL sai | SQL bị gộp hoặc mất newline | Dùng | cho block giữ dòng |
| Duplicate key | Parser/loader có thể từ chối hoặc ghi đè | Xóa key trùng, giữ một giá trị rõ ràng |

YAML dùng dấu cách, không dùng tab để thụt lề. Nên thống nhất hai dấu cách mỗi cấp trong changelog. Đừng căn theo mắt bằng tab vì editor có thể hiển thị tab với độ rộng khác nhau.

### 5.2. Quote chuỗi có ý nghĩa đặc biệt

Các giá trị như yes, no, on, off, null, chuỗi có dấu hai chấm hoặc dấu thăng có thể được parser diễn giải theo quy tắc YAML và phiên bản parser. Nếu mục tiêu là một chuỗi literal, đặt trong quote.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-210-add-label"
      author: "platform-team"
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: label
                  type: VARCHAR(100)
                  defaultValue: "on: hold"
```

ID dạng số có thể được parser hiểu là numeric nếu không quote. Đặt ID trong dấu nháy giúp giữ đúng chuỗi và tránh mất số 0 đầu.

### 5.3. Block scalar cho SQL nhiều dòng

YAML dùng | để giữ nội dung theo nhiều dòng và > để fold dòng thành khoảng trắng. Với SQL nhiều dòng, thường nên dùng | để giữ định dạng:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-211-backfill-status"
      author: "platform-team"
      changes:
        - sql:
            sql: |
              UPDATE customer_account
              SET status_code = 'ACTIVE'
              WHERE status_code IS NULL;
```

Nếu dùng > hoặc thụt lề sai, SQL có thể bị gộp dòng theo cách ngoài ý muốn. Hãy xem nội dung thực tế được parser đưa vào change và kiểm tra SQL preview.

### 5.4. Comment và document separator

Comment YAML bắt đầu bằng # khi ký tự đó được parser nhận diện ngoài chuỗi. Nếu giá trị chứa #, hãy quote. YAML không dùng dấu phẩy cuối danh sách như JSON; mỗi phần tử list được biểu diễn bằng dấu gạch đầu dòng.

Nếu file có nhiều document separator ---, hãy kiểm tra định dạng và parser mà Liquibase version hỗ trợ. Với changelog thông thường, giữ một cấu trúc root rõ ràng để tránh loader nhận nhiều document không mong muốn.

## 6. JSON: dấu nháy kép, dấu phẩy và kiểu dữ liệu

JSON có cú pháp nghiêm ngặt:

- Key và string phải dùng dấu nháy kép.
- Không có dấu phẩy sau phần tử cuối.
- Không hỗ trợ comment // hoặc /* ... */.
- Boolean là true/false không quote.
- Null là null không quote.
- Mảng dùng [] và object dùng {}.

Ví dụ changelog JSON:

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "001-create-customer",
        "author": "platform-team",
        "changes": [
          {
            "createTable": {
              "tableName": "customer_account",
              "columns": [
                {
                  "column": {
                    "name": "id",
                    "type": "BIGINT",
                    "constraints": {
                      "primaryKey": true,
                      "nullable": false
                    }
                  }
                },
                {
                  "column": {
                    "name": "email",
                    "type": "VARCHAR(320)"
                  }
                }
              ]
            }
          }
        ]
      }
    }
  ]
}
```

Đây là ví dụ cấu trúc cho JSON changelog; thuộc tính change type vẫn phải theo schema Liquibase của phiên bản sử dụng.

### 6.1. Những lỗi JSON thường gặp

| Lỗi | Ví dụ sai | Cách sửa |
|---|---|---|
| Dùng nháy đơn | 'id': '001' | Dùng "id": "001" |
| Dấu phẩy cuối | "author": "team",} | Bỏ dấu phẩy cuối |
| Comment | // add customer | Xóa comment hoặc ghi chú ngoài JSON |
| Thiếu dấu đóng | Thiếu ] hoặc } | Ghép cặp mọi ngoặc |
| Sai kiểu | "nullable": "false" | Dùng boolean false nếu thuộc tính yêu cầu boolean |
| Key trùng | Hai thuộc tính id | Giữ một key duy nhất |
| Escape sai | Chuỗi chứa quote chưa escape | Dùng \" hoặc cách biểu diễn hợp lệ |
| Root sai | Thiếu databaseChangeLog | Dùng cấu trúc root đúng |

JSON parser có thể báo vị trí gần nơi phát hiện lỗi, không nhất thiết đúng ký tự gây lỗi. Khi báo lỗi tại dấu }, hãy kiểm tra dấu phẩy, quote và ngoặc ở vài dòng ngay trước đó.

### 6.2. Escape chuỗi JSON

Ví dụ chuỗi SQL có dấu nháy kép hoặc newline phải được escape đúng JSON. Không tự chèn newline thô vào giữa string; dùng \n nếu cần biểu diễn ký tự xuống dòng trong JSON string.

Không dùng cú pháp YAML như block scalar | trong JSON. Không dùng comment để ghi chú changeset; nếu cần metadata, dùng thuộc tính changelog mà Liquibase hỗ trợ.

## 7. Formatted SQL: header và directive là một phần cú pháp changelog

Formatted SQL là file SQL có comment directive để Liquibase nhận diện changeset. Nó không giống một file SQL thuần được tham chiếu bằng change type sqlFile.

Một file formatted SQL cơ bản:

```sql
--liquibase formatted sql

--changeset platform-team:001-create-customer
CREATE TABLE customer_account (
    id BIGINT NOT NULL PRIMARY KEY,
    email VARCHAR(320)
);

--rollback DROP TABLE customer_account;
```

Các thành phần:

- Dòng --liquibase formatted sql khai báo định dạng file.
- Dòng --changeset author:id bắt đầu một changeset.
- Các câu SQL tiếp theo thuộc changeset đó cho đến directive changeset tiếp theo hoặc hết file.
- --rollback cung cấp câu lệnh rollback tường minh.

Directive phải được viết đúng định dạng comment Liquibase nhận diện. Nếu thiếu header hoặc viết sai chính tả, Liquibase có thể không coi file là formatted SQL changelog.

### 7.1. Lỗi directive thường gặp

| Lỗi | Hậu quả có thể gặp | Cách sửa |
|---|---|---|
| Thiếu header | File không được nhận diện như formatted SQL | Thêm --liquibase formatted sql ở đầu |
| Sai chữ trong header | Liquibase không nhận diện directive | Dùng đúng chuỗi directive |
| Thiếu --changeset | Không xác định được changeset | Khai báo author và id |
| Thiếu dấu hai chấm | Author và ID không được phân tách | Dùng author:id |
| Đặt directive giữa câu SQL | Directive không ở vị trí parser mong đợi | Đặt directive trên dòng comment riêng |
| Dùng --rollback sai vị trí | Rollback gắn sai hoặc không được nhận diện | Đặt trong phạm vi changeset tương ứng |
| Đổi author/id sau triển khai | Identity khác history | Giữ identity đã chạy, tạo changeset mới nếu cần |

Một dòng comment SQL thông thường không phải directive. Không đặt một dòng --changeset trong block comment hoặc trong chuỗi SQL và mong Liquibase nhận diện nó.

### 7.2. Nhiều changeset trong một file

Một file formatted SQL có thể chứa nhiều changeset:

```sql
--liquibase formatted sql

--changeset platform-team:001-create-customer
CREATE TABLE customer_account (
    id BIGINT NOT NULL PRIMARY KEY
);
--rollback DROP TABLE customer_account;

--changeset platform-team:002-add-customer-email
ALTER TABLE customer_account
    ADD COLUMN email VARCHAR(320);
--rollback ALTER TABLE customer_account DROP COLUMN email;
```

Mỗi directive --changeset mở một identity riêng. Hãy giữ ID duy nhất theo quy ước, author ổn định và không sửa nội dung changeset đã triển khai. Đường dẫn logic của file cũng tham gia identity; di chuyển file có thể ảnh hưởng lịch sử.

### 7.3. splitStatements và endDelimiter

Liquibase có thể tách nội dung SQL thành nhiều statement. Các thuộc tính như splitStatements và endDelimiter hữu ích khi file chứa procedure, function hoặc câu lệnh có dấu chấm phẩy bên trong body.

Ví dụ minh họa directive có thuộc tính:

```sql
--liquibase formatted sql
--changeset platform-team:020-create-report-function splitStatements:false
CREATE FUNCTION report_total()
RETURNS INTEGER
LANGUAGE SQL
RETURN 0;
```

Cú pháp SQL function và delimiter phụ thuộc DBMS. Ví dụ trên chỉ minh họa việc điều khiển tách statement; cần viết body theo đúng DBMS đích và kiểm tra hành vi của Liquibase version đang dùng. Không đặt splitStatements:false như cách chữa mọi lỗi dấu chấm phẩy.

Khi statement bị tách sai, lỗi có thể xuất hiện ở DBMS execution chứ không phải parser formatted SQL. Hãy xem SQL preview để biết Liquibase gửi những statement nào.

### 7.4. Comment và directive

Các dòng comment SQL bình thường có thể được giữ hoặc loại khỏi SQL theo cách Liquibase xử lý. Đừng viết directive bên trong comment block hoặc phụ thuộc vào một comment bị strip. Nếu dùng stripComments, splitStatements hay endDelimiter, hãy kiểm tra đúng tác động của thuộc tính đối với changeset và DBMS đích.

## 8. Phân biệt formatted SQL với sql và sqlFile

Ba cách sau có mục đích khác nhau:

| Cách dùng | Vai trò |
|---|---|
| Formatted SQL changelog | File SQL tự khai báo changeset bằng Liquibase directives |
| Change type sql trong XML/YAML/JSON | Đưa câu SQL trực tiếp vào một changeset được khai báo ở định dạng đó |
| Change type sqlFile | Tham chiếu file SQL bên ngoài từ changeset trong changelog |

Ví dụ dùng sqlFile trong YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: "030-refresh-customer-view"
      author: "platform-team"
      changes:
        - sqlFile:
            path: sql/refresh_customer_view.sql
            relativeToChangelogFile: true
            splitStatements: false
```

File refresh_customer_view.sql trong trường hợp này là nội dung SQL được changeset gọi. Nó không tự động trở thành formatted SQL changelog chỉ vì phần mở rộng là .sql. Nếu muốn file tự định nghĩa changeset, cần dùng đúng định dạng formatted SQL và cấu hình root changelog phù hợp.

Nhầm hai kiểu này có thể dẫn đến việc Liquibase không tìm thấy changeset hoặc cố thực thi directive như SQL. Hãy xác định ai sở hữu identity: root changelog và change type sqlFile, hay chính formatted SQL file.

## 9. Encoding, BOM, line ending và ký tự Unicode

Changelog nên được lưu với encoding thống nhất, thường là UTF-8. Những vấn đề có thể gặp:

- File lưu bằng encoding khác nhưng runtime đọc như UTF-8.
- Ký tự tiếng Việt bị biến thành dấu hỏi hoặc chuỗi lỗi.
- Byte Order Mark (BOM) xuất hiện ở vị trí parser không mong đợi.
- Copy/paste ký tự quote cong thay cho quote ASCII trong cú pháp.
- File bị cắt do conflict marker hoặc thao tác merge.
- Line ending không đồng nhất làm khó review hoặc ảnh hưởng script xử lý ngoài Liquibase.

Với XML, khai báo encoding trong XML declaration phải khớp encoding thực tế. YAML/JSON cũng cần được lưu đúng UTF-8 theo chuẩn và parser hỗ trợ. Formatted SQL cần đảm bảo directive không bị ký tự lạ đứng trước khiến Liquibase không nhận ra header.

Ví dụ lỗi dễ bỏ qua:

```text
“--changeset platform-team:001”
^ quote cong trong nội dung copy

--liquibase formatted sql
^ dòng header phải bắt đầu đúng directive
```

Quote cong trong comment có thể vô hại, nhưng quote cong thay thế dấu nháy ASCII trong JSON/XML/YAML hoặc SQL string có thể làm parser/DBMS lỗi. Dùng editor hiển thị encoding và kiểm tra ký tự đầu file khi header không được nhận diện.

## 10. Lỗi include và đường dẫn thường bị nhầm với lỗi cú pháp

Một root changelog có thể parse đúng nhưng Liquibase vẫn không tìm thấy file được include. Ví dụ:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-email.yaml
      relativeToChangelogFile: true
```

Nếu file thực tế nằm ở thư mục khác hoặc không được đóng gói trong artifact, Liquibase báo lỗi resource. Đây không phải lỗi indentation hay SQL.

Hãy kiểm tra:

1. Đường dẫn root changelog trong cấu hình ứng dụng/CLI.
2. Đường dẫn include tương đối với root hay classpath theo cấu hình.
3. Chữ hoa/thường trong tên file khi chạy trên filesystem phân biệt case.
4. File có được đóng gói vào JAR/WAR hay migration artifact không.
5. Có file bị đổi tên khi merge nhưng include chưa cập nhật không.
6. includeAll có vô tình nạp file nháp, backup hoặc file không phải changelog không.

Với includeAll, quy tắc sắp xếp và phạm vi thư mục phải được kiểm soát. Không đặt file SQL thuần, file backup hoặc tài liệu cạnh changelog trong thư mục includeAll nếu loader có thể coi chúng là resource cần nạp.

## 11. Lỗi parse, validation và lỗi thực thi DBMS khác nhau thế nào?

| Nhóm | Ví dụ thông báo/hiện tượng | Cách xác minh |
|---|---|---|
| XML parser | Mismatched tag, entity reference, SAX parse error | Xem file và line/column XML |
| YAML parser | Mapping values are not allowed, tab character, unexpected token | Kiểm tra indentation, quote và list |
| JSON parser | Unexpected character, expected comma/end object | Kiểm tra quote, comma và ngoặc |
| Formatted SQL parser | Không tìm thấy changeset/header hoặc directive | Kiểm tra dòng header và --changeset |
| Liquibase validation | Thiếu ID/author, cấu trúc change không hợp lệ | Kiểm tra changelog schema và phiên bản |
| Resource loader | File not found, cannot open changelog | Kiểm tra classpath/include/encoding |
| DBMS parser | SQL syntax error, SQLState | Xem SQL thực tế và dialect DBMS |
| DBMS constraint | Duplicate key, FK violation, NOT NULL | Kiểm tra dữ liệu và constraint |
| Permission | Permission denied, insufficient privileges | Kiểm tra quyền của tài khoản migration |

Một thông báo parser có line/column thường chỉ ra vị trí parser không thể tiếp tục. Nhưng vị trí đó có thể nằm sau ký tự gây lỗi thật, ví dụ dấu phẩy thừa ở dòng trước. Hãy kiểm tra vùng lân cận, không chỉ sửa đúng ký tự được nêu trong thông báo.

## 12. Quy trình chẩn đoán theo từng bước

Khi Liquibase báo lỗi changelog, có thể làm theo trình tự:

1. **Ghi nhận đúng đầu vào.** Lưu tên root changelog, file include, phiên bản Liquibase, DBMS, profile/context/label và artifact đang chạy.
2. **Đọc exception gốc.** Tìm parser, resource loader hay JDBC/DBMS exception; ghi lại file, line/column và changeset nếu đã xác định.
3. **Phân loại giai đoạn.** Xác định lỗi xảy ra lúc tải file, parse, validation, kiểm tra history hay thực thi SQL.
4. **Kiểm tra file được nêu.** Đọc đúng file và phần dòng liên quan; kiểm tra vài dòng trước/sau.
5. **Kiểm tra cấu trúc định dạng.** XML tag/namespace, YAML indentation/type, JSON quote/comma/bracket hoặc formatted SQL directives.
6. **Kiểm tra include.** Xác nhận resource path và thứ tự nạp.
7. **Kiểm tra phiên bản.** Đối chiếu change type, thuộc tính và syntax với Liquibase version của artifact.
8. **Sinh SQL preview khi changelog parse được.** Dùng đúng URL, root changelog và filters.
9. **Thử trên DBMS đại diện.** Đặc biệt với SQL đặc thù hoặc DDL khác nhau giữa các engine.
10. **Đối chiếu history và schema sau lần thất bại.** Xác định changeset trước đó đã commit hay chưa và có partial effect không.
11. **Sửa tối thiểu và chạy lại trong môi trường kiểm thử.** Chỉ phát hành sau khi kiểm chứng artifact thực tế.

Không chỉnh nhiều nhóm lỗi cùng lúc. Nếu vừa đổi format, include path, identity và SQL, sẽ khó xác định thay đổi nào giải quyết nguyên nhân và có thể tạo lỗi mới.

## 13. Sử dụng validate, status và update-sql đúng mục đích

Các lệnh sau thường hữu ích:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
```

- **validate** kiểm tra tính hợp lệ của changelog theo những kiểm tra Liquibase hỗ trợ, như cấu trúc và tham chiếu resource.
- **status --verbose** cho biết changeset pending theo database và cấu hình đang dùng.
- **update-sql** sinh SQL dự kiến cho changeset pending mà không thực hiện update.

Các lệnh phải dùng đúng root changelog, URL, credentials, schema, context, label, parameters, driver và phiên bản Liquibase. Một lần validate thành công không chứng minh DBMS sẽ thực thi SQL thành công. Một lần update-sql sinh được SQL cũng không chứng minh dữ liệu hiện tại đáp ứng precondition hoặc constraint.

Nếu validate thất bại, xử lý parser/changelog/resource trước. Nếu validate thành công nhưng update-sql hoặc update thất bại, đọc SQL và DBMS error để điều tra tiếp.

### 13.1. Đọc SQL preview

SQL preview giúp kiểm tra:

- Change type đã sinh câu SQL nào.
- SQL có đúng schema/catalog không.
- Statement có bị tách sai không.
- Thứ tự tạo bảng, cột, index và constraint có hợp lý không.
- Filter context/label/dbms có chọn đúng changeset không.

Đối với formatted SQL, preview cũng giúp xác nhận Liquibase hiểu directive và ranh giới changeset đúng như mong đợi.

## 14. Kiểm tra cú pháp độc lập trước khi chạy migration

Editor và parser/linter phù hợp có thể phát hiện lỗi định dạng sớm. Quy trình kiểm tra nên phù hợp từng file:

| Định dạng | Kiểm tra nhanh | Kiểm tra bằng Liquibase |
|---|---|---|
| XML | XML parser, IDE inspection, XSD-aware editor | validate với đúng runtime |
| YAML | YAML parser/linter, kiểm tra indentation | validate với đúng changelog |
| JSON | JSON parser/linter | validate với đúng changelog |
| Formatted SQL | Kiểm tra header/directive, SQL editor | validate, update-sql, thử trên DBMS đích |

Parser độc lập có thể xác nhận cú pháp định dạng, nhưng không biết toàn bộ quy tắc Liquibase. Ví dụ YAML parser có thể đọc được một file nhưng Liquibase từ chối vì change type hoặc thuộc tính không hợp lệ.

Ngược lại, Liquibase parse được formatted SQL không có nghĩa câu SQL hợp lệ với DBMS đích. Cần cả hai tầng kiểm tra.

### 14.1. Giảm phạm vi để tìm lỗi

Nếu root changelog lớn, hãy xác định file mới thêm hoặc file vừa sửa trong commit gần nhất. Tạo một test database riêng và thử với đúng artifact. Có thể kiểm tra riêng file con bằng một root changelog lab nếu dự án có quy trình cho phép, nhưng không thay đổi root production chỉ để debug.

Không xóa các include cũ hoặc comment hàng loạt changeset trong production branch nhằm tìm lỗi; điều đó có thể làm thay đổi tập migration được chọn.

## 15. Sửa cú pháp mà không làm thay đổi lịch sử changeset

Nếu lỗi nằm trong changeset chưa từng được triển khai ở môi trường dùng chung, sửa cú pháp và kiểm thử lại thường là bước phù hợp.

Nếu changeset đã được triển khai, cần phân biệt:

- **Sửa lỗi định dạng nhưng không thay nội dung logic:** vẫn có thể làm checksum hoặc parser interpretation thay đổi tùy nội dung và định dạng; phải kiểm tra lịch sử.
- **Sửa SQL/change logic:** không sửa changeset đã chạy để thay đổi kết quả mong muốn; tạo changeset mới.
- **Di chuyển file:** logical file path có thể là một phần identity; giữ đường dẫn logic cũ nếu cần và được hỗ trợ.
- **Đổi id/author:** làm thay đổi identity; không làm tùy tiện sau triển khai.

Nếu chỉ thay whitespace hoặc format, đừng mặc định checksum không đổi. Hãy so sánh checksum thực tế theo Liquibase version và history. Không sửa trực tiếp MD5SUM, xóa record DATABASECHANGELOG hoặc dùng clear-checksums như một cách chữa lỗi cú pháp.

### 15.1. Một lần update thất bại có thể đã chạy changeset trước

Nếu changelog chứa 001, 002 và 003, trong đó 001/002 thành công còn 003 lỗi, history có thể đã ghi nhận 001/002. Liquibase không mặc định rollback toàn bộ root changelog về trạng thái ban đầu.

Sau lỗi, kiểm tra DATABASECHANGELOG có changeset nào, schema thực tế có object nào, changeset gây lỗi có transaction không, DBMS có implicit commit đối với DDL đó không và có câu SQL nào đã thực thi một phần không.

Không xóa history để buộc chạy lại từ đầu. Nếu có partial effect, thiết kế migration bù hoặc phục hồi dựa trên trạng thái thật.

## 16. Ví dụ chẩn đoán bốn tình huống thường gặp

### 16.1. XML báo mismatched tag

**Hiện tượng:** Liquibase báo lỗi parse tại thẻ đóng createTable.

**Nguyên nhân:** Một thẻ column hoặc constraints chưa được đóng đúng, hoặc thẻ đóng bị đặt sai cấp.

**Cách xử lý:**

1. Mở file XML và xem vùng trước dòng lỗi.
2. Ghép cặp từng thẻ mở/đóng.
3. Kiểm tra namespace và XSD.
4. Chạy validate.
5. Nếu parse thành công, chạy update-sql và thử trên DBMS lab.

### 16.2. YAML báo mapping values are not allowed

**Hiện tượng:** Parser báo lỗi gần dòng có tableName hoặc sql.

**Nguyên nhân có thể:** Sai indentation, tab, thiếu quote hoặc chuỗi chứa dấu hai chấm chưa được quote.

**Cách xử lý:**

1. Chuyển tab thành spaces.
2. Kiểm tra cấu trúc list và mapping.
3. Quote giá trị có ký tự đặc biệt.
4. Dùng block scalar | cho SQL nhiều dòng.
5. Chạy parser/linter và Liquibase validate.

### 16.3. JSON báo unexpected character

**Hiện tượng:** Parser dừng tại } hoặc ].

**Nguyên nhân có thể:** Dấu phẩy cuối, nháy đơn, comment, dấu quote chưa đóng hoặc thiếu ngoặc trước đó.

**Cách xử lý:** kiểm tra vài dòng trước vị trí báo lỗi, ghép cặp {} và [], xác nhận mọi string/key dùng dấu nháy kép và bỏ comment/trailing comma.

### 16.4. Formatted SQL không nhận changeset

**Hiện tượng:** Liquibase không tìm thấy changeset hoặc file bị xử lý như SQL không đúng định dạng.

**Nguyên nhân có thể:** Thiếu --liquibase formatted sql, directive bị viết sai, header không ở đầu file hoặc dòng --changeset không đúng mẫu.

**Cách xử lý:** đặt header đúng ở đầu file, khai báo --changeset author:id trên dòng riêng, kiểm tra encoding/ký tự đầu file và chạy validate. Sau đó xem update-sql để xác nhận Liquibase nhận đúng changeset.

## 17. Quy tắc cho SQL nhiều statement, procedure và trigger

SQL đơn giản thường kết thúc bằng dấu chấm phẩy. Nhưng procedure/function/trigger có thể chứa nhiều dấu chấm phẩy bên trong body. Nếu Liquibase tách statement tại từng dấu ;, DBMS có thể nhận các đoạn SQL không hoàn chỉnh.

Khi gặp lỗi kiểu unexpected end, missing expression hoặc parser DBMS dừng giữa body, hãy kiểm tra ranh giới statement trước khi sửa nội dung function.

Các thuộc tính có thể liên quan:

- **splitStatements:** có tách SQL thành nhiều statement hay không.
- **endDelimiter:** delimiter dùng để xác định ranh giới statement.
- **stripComments:** có loại comment khỏi SQL trước khi gửi hay không.

Chúng có thể xuất hiện trong formatted SQL directive hoặc change type sql/sqlFile theo cú pháp và phiên bản hỗ trợ. Chọn giá trị dựa trên DBMS và cấu trúc câu lệnh. Không dùng delimiter đặc biệt theo thói quen của một DBMS cho engine khác.

### 17.1. SQL file thuần và formatted SQL

Nếu một YAML changeset dùng sqlFile, file SQL được tham chiếu là nội dung của change. Nếu file đó chứa header formatted SQL và directive changeset, nhóm có thể đang trộn hai mô hình.

Hãy chọn một cách sở hữu rõ ràng:

- Root changelog YAML/XML/JSON định nghĩa changeset, rồi gọi sqlFile để chạy SQL.
- Hoặc formatted SQL file tự định nghĩa changeset và được nạp như changelog.

Không để cùng một thay đổi được include và tham chiếu theo hai cách khiến nó chạy hai lần.

## 18. Tích hợp Spring Boot và CI/CD để bắt lỗi sớm

Với Spring Boot, root changelog thường được cấu hình như sau:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

File root và các file include phải được đóng gói trong artifact. Một đường dẫn đúng trên máy developer có thể sai khi chạy từ JAR nếu file không nằm trong classpath hoặc chữ hoa/thường khác.

Pipeline nên có các bước:

1. Parse/lint XML, YAML, JSON và kiểm tra formatted SQL directives.
2. Kiểm tra file include và resource trong artifact.
3. Chạy Liquibase validate với đúng phiên bản dependency.
4. Sinh update-sql để review SQL và ranh giới statement.
5. Chạy migration trên database cùng engine production.
6. Kiểm tra precondition, dữ liệu, constraint và rollback.
7. Lưu artifact changelog cùng commit/image digest.
8. Chỉ triển khai sau khi các cổng kiểm tra đạt.

### 18.1. Không để lỗi parse làm ứng dụng khởi động với schema cũ

Nếu Spring Boot tự chạy Liquibase khi khởi tạo context và changelog parse thất bại, bean tích hợp thường khởi tạo lỗi, khiến application context không hoàn tất. Đây là fail-fast phù hợp nếu schema mới là điều kiện bắt buộc.

Nếu migration chạy trong job riêng, pipeline phải dừng rollout khi job lỗi. Không tắt Liquibase ở application runtime rồi quên chạy migration job trước khi deploy.

### 18.2. Kiểm tra đúng artifact sẽ phát hành

Một lỗi phổ biến là validate chạy trên working tree nhưng artifact đóng gói thiếu file hoặc chứa phiên bản changelog khác. Hãy chạy validation trên đúng artifact đã build hoặc trên nội dung resource tương đương artifact.

Ghi nhận phiên bản Liquibase, root changelog, DBMS và driver. Các thuộc tính được hỗ trợ có thể khác giữa phiên bản; một changelog parse trên máy developer không đảm bảo runtime production dùng cùng parser.

## 19. Checklist xử lý lỗi cú pháp changelog

- [ ] Đã xác định lỗi xảy ra ở resource loading, parser, Liquibase validation hay DBMS execution.
- [ ] Đã đọc exception gốc và ghi lại file, line/column, changeset.
- [ ] Đã kiểm tra đúng root changelog và toàn bộ include.
- [ ] XML có namespace, schema location, thẻ mở/đóng và entity hợp lệ.
- [ ] YAML dùng spaces, indentation/list/mapping đúng và quote chuỗi đặc biệt.
- [ ] JSON dùng quote kép, không comment/trailing comma và đủ cặp ngoặc.
- [ ] Formatted SQL có header và directive changeset đúng vị trí/cú pháp.
- [ ] SQL nhiều statement có splitStatements/endDelimiter phù hợp.
- [ ] File dùng encoding thống nhất, không có ký tự lạ trước header.
- [ ] Change type và thuộc tính tương thích với Liquibase version đang chạy.
- [ ] Đã chạy validate và xem update-sql với đúng cấu hình.
- [ ] Đã thử SQL trên DBMS đích nếu có cú pháp hoặc DDL đặc thù.
- [ ] Sau lần chạy lỗi đã kiểm tra DATABASECHANGELOG và schema thực tế.
- [ ] Không xóa history, sửa checksum hoặc đánh dấu changeset chạy chỉ để bỏ qua lỗi.
- [ ] Changeset đã triển khai được giữ identity và ý nghĩa; thay đổi logic mới được thêm bằng changeset mới.
- [ ] Artifact phát hành chứa đúng root changelog và resource include.

## 20. Bài thực hành: sửa bốn lỗi cú pháp trong môi trường lab

**Mục tiêu:** phân loại và sửa lỗi XML, YAML, JSON và formatted SQL mà không tác động database dùng chung.

### Bước 1. Tạo một changelog XML sai có chủ đích

Bỏ một thẻ đóng trong ví dụ tạo bảng. Chạy validate, ghi nhận parser báo file và vị trí. Sửa thẻ, chạy lại và xác nhận lỗi parse biến mất.

### Bước 2. Tạo một changelog YAML sai indentation

Đẩy columns lệch khỏi createTable hoặc dùng tab. Chạy parser/validate, sửa indentation bằng spaces và xác nhận cấu trúc changeset đúng.

### Bước 3. Tạo JSON có trailing comma

Thêm dấu phẩy sau thuộc tính cuối hoặc phần tử cuối của array. Xác nhận JSON parser báo lỗi, bỏ dấu phẩy và kiểm tra lại.

### Bước 4. Tạo formatted SQL thiếu header

Tạo file chỉ có --changeset team:001 và SQL nhưng thiếu --liquibase formatted sql. Quan sát cách Liquibase xử lý, thêm header đúng và xác nhận changeset được nhận diện. Không chạy file lỗi lên database dùng chung.

### Bước 5. Phân biệt parser với DBMS error

Dùng một formatted SQL có header đúng nhưng cố ý viết tên bảng không hợp lệ hoặc SQL sai với DBMS lab. Quan sát rằng lỗi xuất hiện ở giai đoạn thực thi SQL chứ không phải parse file. Ghi lại SQLState và changeset gây lỗi.

### Bước 6. Kiểm tra history sau thất bại

Chạy một chuỗi gồm changeset hợp lệ trước lỗi và changeset gây lỗi sau. Kiểm tra DATABASECHANGELOG, schema và dữ liệu để xác định thay đổi nào đã commit. Không xóa record để chạy lại từ đầu.

### Bước 7. Đưa kiểm tra vào pipeline

Thiết lập lint/parse, Liquibase validate, update-sql và migration test trên DBMS tương ứng. Đảm bảo pipeline dừng nếu parser hoặc migration test thất bại.

**Tiêu chí hoàn thành:** nhận diện được bốn lỗi định dạng, phân biệt lỗi parser với lỗi SQL của DBMS, sửa đúng file và chứng minh trạng thái history/schema sau lần chạy lỗi.

**Kết luận:** XML, YAML, JSON và formatted SQL có quy tắc cú pháp khác nhau, nhưng đều phải tạo ra changelog mà Liquibase hiểu đúng. Hãy xác định lỗi nằm ở parser, validation, resource hay DBMS execution; kiểm tra namespace/indent/quote/directive/encoding và include theo đúng định dạng. Sau khi sửa, chạy validate, xem SQL preview và thử trên DBMS đích. Nếu lần chạy trước đã áp dụng một phần changeset, hãy đối chiếu history và schema thực tế trước khi retry để bảo toàn dữ liệu và lịch sử triển khai.

