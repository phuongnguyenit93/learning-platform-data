# Phối hợp nhiều định dạng trong một dự án

## 1. Bối cảnh và mục tiêu

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, người học thực hành quản lý thay đổi schema và dữ liệu bằng Liquibase: tổ chức changelog và changeset, sử dụng precondition, kiểm tra checksum và lịch sử triển khai, chuẩn bị rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một dự án thực tế không nhất thiết chỉ dùng một kiểu file. Nhóm có thể viết migration tạo bảng bằng XML, nạp dữ liệu bằng YAML, định nghĩa thay đổi bằng JSON và dùng SQL khi cần tận dụng cú pháp riêng của hệ quản trị cơ sở dữ liệu.

Liquibase hỗ trợ nhiều **định dạng changelog**. Các định dạng này khác nhau về cú pháp biểu diễn nhưng cuối cùng đều được Liquibase phân tích thành các thay đổi để áp dụng vào database. Kỹ năng quan trọng là ghép chúng thành **một dòng lịch sử triển khai nhất quán**: chỉ định điểm vào, quyết định thứ tự, tham chiếu đúng tài nguyên, giữ ổn định bộ định danh changeset và kiểm chứng kết quả ở mọi môi trường.

Sau bài này, bạn có thể:

- Phân biệt changelog XML, YAML, JSON và formatted SQL với file SQL/CSV chỉ được dùng làm dữ liệu đầu vào.
- Tổ chức một root changelog tham chiếu các changelog con khác định dạng.
- Xác định thứ tự thực thi, đường dẫn tương đối và cách xử lý tài nguyên trong JAR hoặc CLI.
- Hiểu vai trò của `id`, `author`, đường dẫn changelog và checksum khi thay đổi định dạng.
- Thiết kế precondition, rollback và quy trình CI/CD nhất quán cho migration hỗn hợp.

## 2. Các định dạng có thể xuất hiện trong cùng repository

| Dạng file | Vai trò thông thường | Lợi thế | Điều cần cân nhắc |
|---|---|---|---|
| XML changelog (`.xml`) | Khai báo changeset bằng thẻ XML và thuộc tính | Cấu trúc tường minh; schema hỗ trợ công cụ kiểm tra | Nhiều thẻ, dài khi có nhiều cột hoặc thay đổi |
| YAML changelog (`.yaml`, `.yml`) | Khai báo changeset bằng cấu trúc key–value, list | Dễ đọc, ít dấu câu; tiện review | Nhạy với thụt lề và kiểu giá trị |
| JSON changelog (`.json`) | Khai báo changeset bằng object và array | Hợp với công cụ sinh cấu hình, xử lý máy | Nhiều dấu ngoặc; dễ sai kiểu hoặc cấu trúc mảng |
| Formatted SQL changelog (`.sql`) | Viết SQL với chú thích chỉ thị Liquibase | Diễn đạt trực tiếp SQL đặc thù database | Khả năng portable thấp; rollback và tính năng hỗ trợ có thể phụ thuộc phiên bản |
| SQL thường (`.sql`) | Chứa câu lệnh để gọi qua `sqlFile` | Dùng lại script SQL phức tạp | Không tự trở thành changelog chỉ vì có đuôi `.sql` |
| CSV hoặc tài nguyên khác | Dữ liệu nhập qua `loadData`/`loadUpdateData` | Tách dữ liệu khỏi cấu trúc migration | Là tài nguyên phụ thuộc, không phải changelog độc lập |

Một repository có thể chứa cả sáu loại trên. Tuy nhiên, **chỉ các file changelog được Liquibase nạp như changelog mới đóng góp changeset vào lịch sử**. File SQL thường được gọi trong một `sqlFile` là nội dung của changeset bao bọc nó; bản thân file đó không tạo bộ định danh riêng. Tương tự, CSV được sử dụng như nguồn dữ liệu cho một change, không phải một changeset độc lập.

XML, YAML và JSON đều có thể diễn đạt phần lớn các change type chung như `createTable`, `addColumn`, `addForeignKeyConstraint`, `insert` hoặc `createIndex`. Với formatted SQL, các câu lệnh SQL diễn đạt thao tác thực tế, còn chỉ thị trong chú thích giúp Liquibase nhận diện changeset và một số thuộc tính thực thi. Việc tính năng cụ thể có thể được khai báo ở định dạng nào còn phụ thuộc phiên bản và edition Liquibase; nên kiểm tra với phiên bản nhóm thực sự dùng.

## 3. Chọn một changelog gốc làm điểm vào

Ngay cả khi có nhiều định dạng, một lần chạy Liquibase vẫn nên được cấu hình với **một root changelog xác định rõ**. Root changelog là nơi tập hợp các file con và thể hiện trình tự. Một lựa chọn dễ bảo trì là để root ở XML, YAML hoặc JSON, sau đó sử dụng `include` để nạp các file con cùng hoặc khác định dạng.

Ví dụ cấu trúc:

```text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        ├── changes/
        │   ├── 001-create-customer.xml
        │   ├── 002-seed-customer.yaml
        │   ├── 003-index-customer-email.sql
        │   └── 004-add-customer-active.json
        └── resources/
            └── seed-customers.csv
```

Root changelog `db.changelog-master.yaml`:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.xml
      relativeToChangelogFile: true
  - include:
      file: changes/002-seed-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-index-customer-email.sql
      relativeToChangelogFile: true
  - include:
      file: changes/004-add-customer-active.json
      relativeToChangelogFile: true
```

Điểm đáng chú ý:

1. Root dùng YAML, nhưng mỗi file con có thể tự dùng định dạng khác.
2. Liquibase nạp các file theo trình tự khai báo `include`.
3. `relativeToChangelogFile: true` giúp đường dẫn file con được giải quyết từ thư mục chứa root, thay vì ngầm phụ thuộc vào thư mục đang chạy lệnh.
4. Thứ tự đã có chủ đích: tạo bảng trước, sau đó thêm dữ liệu, tạo index và bổ sung cột.
5. Đổi thứ tự include có thể làm hỏng quan hệ phụ thuộc dù nội dung của từng file không đổi.

Với nhiều lớp include lồng nhau, đường dẫn tương đối được tính từ changelog trực tiếp chứa lệnh include. Nếu một file con tiếp tục include file khác, không mặc nhiên lấy root ban đầu làm thư mục gốc cho mọi tham chiếu.

### 3.1. Vì sao không bắt buộc tất cả file cùng định dạng?

Liquibase đọc mỗi changelog bằng parser phù hợp rồi xử lý changeset theo mô hình chung. Do đó, việc chọn định dạng có thể dựa trên đặc tính thay đổi: XML cho ràng buộc schema phức tạp, YAML cho nhiều thay đổi cấu trúc có thể đọc dễ, JSON cho dữ liệu sinh từ công cụ, và formatted SQL cho DDL đặc thù PostgreSQL hoặc hệ quản trị đang dùng. Không cần chuyển toàn bộ lịch sử sang một định dạng duy nhất mới có thể chạy chung.

Dù vậy, số lượng định dạng càng nhiều thì chi phí review và thống nhất quy ước càng cao. Nên chọn một định dạng mặc định cho phần lớn migration và chỉ dùng dạng khác khi có lợi ích rõ ràng. Đây là quy tắc quản trị mã nguồn, không phải hạn chế của Liquibase.

## 4. Ví dụ end-to-end: bốn changelog, bốn định dạng

Ví dụ sử dụng PostgreSQL và giả định schema đích chưa có bảng `customer`. Các mã changeset và tên file là minh họa; khi triển khai thật, hãy dùng quy ước đặt tên thống nhất và giữ các giá trị đã áp dụng ổn định.

### 4.1. XML — tạo bảng

File `changes/001-create-customer.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-create-customer" author="db-team">
        <createTable tableName="customer">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(320)">
                <constraints nullable="false"/>
            </column>
        </createTable>
        <rollback>
            <dropTable tableName="customer"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
```

Trong XML, mỗi change là một phần tử, thuộc tính thể hiện tham số, còn các phần tử con mô tả cấu trúc lồng nhau. Changeset có `id` và `author`; đường dẫn file XML là thành phần thứ ba của danh tính. Rollback minh họa thao tác xóa bảng, nhưng chỉ an toàn khi dữ liệu trong bảng có thể bị xóa theo kế hoạch và các đối tượng phụ thuộc đã được rollback trước.

### 4.2. YAML — nạp một bản ghi mẫu

File `changes/002-seed-customer.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 002-seed-customer
      author: db-team
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 100
              - column:
                  name: email
                  value: demo@example.invalid
      rollback:
        - delete:
            tableName: customer
            where: "id = 100"
```

YAML diễn đạt cùng khái niệm changeset và change bằng danh sách có thụt lề. Bước insert phụ thuộc bảng `customer` đã được tạo ở file XML trước đó. Rollback xóa đúng bản ghi được tạo ra; cần bảo đảm mã `100` được dành riêng cho dữ liệu mẫu này, tránh xóa bản ghi người dùng thật.

Các giá trị chuỗi chứa dấu `:`, `#`, ký tự đặc biệt hoặc dễ bị hiểu thành boolean/number nên được trích dẫn rõ trong YAML. Kiểu dữ liệu của thuộc tính cũng có ý nghĩa: `valueNumeric` để nhập số khác với `value` để nhập chuỗi.

### 4.3. Formatted SQL — tạo index

File `changes/003-index-customer-email.sql`:

```sql
--liquibase formatted sql

--changeset db-team:003-index-customer-email
CREATE INDEX idx_customer_email ON customer (email);

--rollback DROP INDEX idx_customer_email;
```

Dòng đầu `--liquibase formatted sql` giúp Liquibase nhận biết đây là **formatted SQL changelog**, không phải file SQL thường. Dòng `--changeset db-team:003-index-customer-email` xác định `author` và `id`. Lệnh tạo index được nạp như nội dung changeset. Chỉ thị `--rollback` cung cấp SQL hoàn tác.

Ví dụ `DROP INDEX idx_customer_email` phù hợp với PostgreSQL trong cấu hình minh họa; cú pháp xóa index và các tùy chọn như tạo index đồng thời có thể khác trên MySQL, SQL Server hoặc Oracle. SQL đặc thù database nên có thuộc tính/bộ lọc `dbms` phù hợp hoặc được tách theo hệ quản trị để tránh áp dụng nhầm.

**Lưu ý:** Formatted SQL không tự động có mức hỗ trợ mọi chức năng tương đương XML/YAML/JSON ở mọi phiên bản/edition Liquibase. Đặc biệt, việc dùng formatted SQL làm *root* để include các changelog khác cần kiểm tra tính năng có được phiên bản đang dùng hỗ trợ hay không. Trong ví dụ này, YAML làm root còn SQL được include như changelog con.

### 4.4. JSON — bổ sung cột

File `changes/004-add-customer-active.json`:

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "004-add-customer-active",
        "author": "db-team",
        "changes": [
          {
            "addColumn": {
              "tableName": "customer",
              "columns": [
                {
                  "column": {
                    "name": "active",
                    "type": "BOOLEAN",
                    "defaultValueBoolean": true
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

JSON dùng object và array để biểu diễn cây changelog. Các dấu ngoặc, dấu phẩy và kiểu `true`/`false` là thành phần của cú pháp JSON, vì vậy không thể viết thiếu hoặc dùng comment như trong YAML. Ví dụ trên bổ sung cột boolean cho bảng đã tạo ở changeset XML.

Cả bốn file đều có một changeset với bộ định danh riêng. Liquibase không yêu cầu chúng chia sẻ cùng định dạng; điều cần giữ ổn định là **thứ tự**, **đường dẫn logic**, **điều kiện thực thi** và **ngữ nghĩa của thay đổi**.

## 5. Khác biệt giữa formatted SQL và sqlFile

Đây là nguồn nhầm lẫn phổ biến nhất khi trộn định dạng.

**Formatted SQL changelog** chứa chỉ thị Liquibase và tự khai báo changeset:

```sql
--liquibase formatted sql
--changeset db-team:010-create-audit-table
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    message VARCHAR(500) NOT NULL
);
--rollback DROP TABLE audit_event;
```

**SQL thường** chỉ chứa câu lệnh:

```sql
UPDATE customer
SET active = TRUE
WHERE active IS NULL;
```

Để Liquibase chạy SQL thường, cần một changeset ở XML/YAML/JSON (hoặc một định dạng hỗ trợ thay đổi tương đương) tham chiếu file bằng `sqlFile`. Ví dụ YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 011-backfill-customer-active
      author: db-team
      changes:
        - sqlFile:
            path: ../sql/backfill-customer-active.sql
            relativeToChangelogFile: true
            splitStatements: true
            stripComments: true
      rollback:
        - sql: "UPDATE customer SET active = NULL WHERE id IN (100);"
```

Ở đây, `011-backfill-customer-active` là danh tính được Liquibase theo dõi. File SQL được gọi không có bộ định danh changeset riêng. Đường dẫn `../sql/...` được giải quyết từ vị trí của YAML chứa `sqlFile`; trong ví dụ cấu trúc ở phần 3 cần bổ sung thư mục `db/changelog/sql` và file SQL tương ứng khi sử dụng mẫu này.

Cần phân biệt khả năng rollback: lệnh update SQL có thể làm mất thông tin trạng thái ban đầu. Rollback minh họa chỉ phù hợp nếu có chứng cứ rằng bản ghi được chọn trước đó có giá trị NULL; với dữ liệu thực tế, nên ghi lại giá trị trước migration hoặc thiết kế thao tác bù chính xác. Không coi một câu lệnh SQL ngược đơn giản là đủ an toàn trong mọi trường hợp.

Nếu một file SQL thường bị thêm thẳng vào `include` như một changelog mà không có định dạng Liquibase hợp lệ, parser có thể báo lỗi. Ngược lại, một formatted SQL được trỏ tới như `sqlFile` sẽ được coi là SQL để thực thi, không đương nhiên được diễn giải như tập changeset riêng. Hãy chọn cơ chế nạp dựa trên vai trò thực sự của file.

## 6. Thứ tự khai báo và quan hệ phụ thuộc không phụ thuộc định dạng

Liquibase xử lý thứ tự từ changelog và cấu hình thực thi, không dựa vào đuôi file để quyết định XML chạy trước SQL hay YAML chạy sau JSON. Trong root changelog của ví dụ:

```text
001-create-customer.xml       tạo bảng
          |
          v
002-seed-customer.yaml        insert bản ghi mẫu
          |
          v
003-index-customer-email.sql  tạo index
          |
          v
004-add-customer-active.json  thêm cột active
```

Bước 2 phụ thuộc bảng được tạo bởi bước 1; bước 3 phụ thuộc cột `email` của bước 1; bước 4 phụ thuộc bảng `customer`. Đồ thị phụ thuộc có thể có nhiều nhánh, nhưng mỗi thay đổi phải được đặt sau các điều kiện tiên quyết của nó.

`includeAll` có thể gom file tự động theo thư mục:

```yaml
databaseChangeLog:
  - includeAll:
      path: changes
      relativeToChangelogFile: true
```

Liquibase mặc định xử lý những file được `includeAll` phát hiện theo thứ tự tên. Vì thế, tiền tố số và quy tắc đặt tên là quan trọng. Tuy nhiên, nếu thư mục chứa SQL thường, CSV hoặc file không phải changelog, `includeAll` có thể cố xử lý file không hợp lệ hoặc đưa vào những nội dung ngoài dự kiến. Chỉ đặt những file changelog hợp lệ trong thư mục được quét; đặt SQL phụ trợ/CSV sang thư mục riêng.

Với phụ thuộc chặt, `include` tường minh cho phép reviewer thấy ngay file nào được nạp và thứ tự dự kiến. Khi có nhiều định dạng và nhiều nhóm cùng đóng góp migration, đây thường là lựa chọn dễ kiểm soát hơn.

## 7. Đường dẫn, classpath và cách nạp tài nguyên

Đường dẫn có hai vai trò: giúp Liquibase **tìm file** và góp phần xác định **danh tính changeset** trong lịch sử. Hai vai trò liên quan nhưng không đồng nhất.

### 7.1. Đường dẫn tham chiếu

Với `include`, `includeAll`, `sqlFile` hoặc `loadData`, cần phân biệt:

- Đường dẫn tương đối với changelog khai báo tham chiếu khi dùng `relativeToChangelogFile: true` (ở change type hỗ trợ thuộc tính này).
- Đường dẫn được tìm qua resource accessor hoặc search path của Liquibase.
- Đường dẫn classpath khi chạy ứng dụng Java/Spring Boot và tài nguyên đã được đóng gói.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Nội dung trong `src/main/resources/db/changelog` sẽ được nạp dưới đường dẫn tài nguyên `db/changelog` sau khi build, miễn là cấu hình build đóng gói đủ file XML, YAML, JSON và SQL. Không thêm `src/main/resources` vào đường dẫn classpath trong ứng dụng đã đóng gói.

Với Liquibase CLI, đường dẫn root có thể được cung cấp qua `--changelog-file` và search path phù hợp:

```bash
liquibase \
  --search-path=src/main/resources \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate
```

Các tham số kết nối database phải được cấu hình phù hợp trong lệnh, file properties hoặc biến môi trường trước khi chạy các thao tác cần database. Cần bảo đảm CLI và Spring Boot đều tìm ra cùng bộ file, không chỉ trùng tên root.

### 7.2. Đường dẫn logic trong bộ định danh changeset

Liquibase nhận diện changeset bằng tổ hợp `id`, `author` và đường dẫn logic của file changelog chứa changeset. Trong bảng `DATABASECHANGELOG`, thành phần đường dẫn thường được lưu ở cột `FILENAME`.

Giả sử có changeset:

```text
(id=002-seed-customer, author=db-team,
 file=db/changelog/changes/002-seed-customer.yaml)
```

Sau khi file đã chạy, nếu đổi định dạng thành `002-seed-customer.xml` rồi thay đường dẫn include, file path có thể thay đổi và Liquibase có thể coi đó là một changeset khác. Dù `id` và `author` giữ nguyên, việc đổi đường dẫn vật lý có thể ảnh hưởng bộ định danh nếu không duy trì đường dẫn logic phù hợp.

Thuộc tính `logicalFilePath` là cơ chế cho phép duy trì đường dẫn logic đã được ghi trong lịch sử khi cần đổi vị trí hoặc cách nạp file, ở những phạm vi và phiên bản hỗ trợ. Giá trị cần khớp **chính xác** với `FILENAME` của changeset đã triển khai. Không đoán đường dẫn từ tên thư mục mới hay tự sửa bảng `DATABASECHANGELOG` để làm khớp.

## 8. Chuyển đổi định dạng sau khi đã triển khai: rủi ro lớn nhất

Giả sử phiên bản 1 dùng YAML:

```text
db/changelog/changes/020-add-order-status.yaml
```

Bản này đã chạy trên production. Sau đó nhóm quyết định “chuẩn hóa” sang XML:

```text
db/changelog/changes/020-add-order-status.xml
```

Ngay cả khi hai file mô tả cùng thao tác thêm cột, có hai rủi ro độc lập:

1. **Danh tính thay đổi**: phần đường dẫn logic có thể chuyển từ `.yaml` sang `.xml`. Liquibase có thể xem đó là changeset mới và chạy lại thao tác đã áp dụng.
2. **Checksum thay đổi**: khi đã giữ được danh tính, phần nội dung được parser biểu diễn và checksum có thể khác; Liquibase có thể báo checksum không khớp.

Do đó, chuyển đổi định dạng không phải thao tác “đổi đuôi file” vô hại. Không được kết luận hai changeset tương đương chỉ vì SQL cuối cùng trông giống nhau.

### 8.1. Chiến lược được ưu tiên

Giữ nguyên các changelog lịch sử đã chạy và bắt đầu viết **changeset mới** bằng định dạng nhóm muốn sử dụng trong tương lai. Một root changelog hỗn hợp có thể tiếp tục include file YAML cũ bên cạnh XML mới. Cách này vừa tránh thay đổi danh tính, vừa giúp nhóm áp dụng quy ước mới cho phần công việc tiếp theo.

Nếu buộc phải chuyển đổi changelog đã chạy, cần có kế hoạch di chuyển có kiểm chứng:

1. Truy vấn `ID`, `AUTHOR`, `FILENAME` và `MD5SUM` của các changeset liên quan ở từng môi trường.
2. Sao lưu và lưu dấu cấu trúc ban đầu để có thể so sánh.
3. Đánh giá cách giữ đường dẫn logic, ví dụ `logicalFilePath` khi phù hợp.
4. So sánh nội dung parsed changeset và checksum với lịch sử thực tế; không mặc định đổi định dạng sẽ giữ checksum.
5. Chạy `validate`, `status --verbose` và `update-sql` trên bản sao database có lịch sử đại diện.
6. Xác nhận không có changeset cũ bất ngờ xuất hiện trong danh sách pending hoặc SQL dự kiến.
7. Chỉ triển khai sau khi có phương án xử lý cụ thể các xung đột danh tính/checksum.

`clearCheckSums` không sửa được bộ định danh thay đổi do đường dẫn khác nhau. Dùng `runOnChange` hoặc `runAlways` để né lỗi chuyển định dạng cũng có thể dẫn đến thực thi lại thao tác không an toàn. Với migration schema và dữ liệu thông thường, hãy tạo changeset mới thay vì sửa changeset lịch sử.

## 9. Precondition, context, label và tham số dùng chung

Một root changelog hỗn hợp có thể được triển khai cho nhiều môi trường. Liquibase vẫn áp dụng cùng nguyên tắc lọc và điều kiện ở cấp changeset: `dbms`, context, label, precondition và các thuộc tính chạy lại. Khác biệt nằm ở cách khai báo cú pháp của mỗi định dạng.

Ví dụ một changeset YAML dùng precondition:

```yaml
databaseChangeLog:
  - changeSet:
      id: 050-create-customer-audit
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - createTable:
            tableName: customer_audit
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
```

Điều kiện này đảm bảo bảng `customer` tồn tại trước khi tạo bảng audit; nhưng không tự chạy changeset tạo bảng `customer` nếu bị thiếu hoặc bị lọc. Khi dùng context hoặc label, phải đảm bảo changeset tiền đề cũng được chọn ở môi trường cần triển khai.

Trong formatted SQL, precondition và một số thuộc tính có cú pháp chú thích đặc thù; phạm vi hỗ trợ phụ thuộc phiên bản Liquibase. Đừng sao chép nguyên cách khai báo YAML sang chú thích SQL. Khi yêu cầu phức tạp hoặc cần tính portable, có thể viết changeset trong XML/YAML/JSON và dùng `sql`/`sqlFile` để chứa SQL thực thi.

Thuộc tính changelog parameters và placeholder (nếu sử dụng) cần được cung cấp nhất quán từ CLI, Spring Boot hoặc pipeline. Cẩn thận với cách YAML, JSON, XML và SQL diễn giải dấu nháy, escape và kiểu giá trị. Ví dụ `true` trong JSON là boolean, `"true"` là string; còn trong SQL cách biểu diễn boolean phụ thuộc database. Kiểm tra SQL sinh ra trước khi chạy là cách phát hiện nhiều sai lệch kiểu dữ liệu giữa các định dạng.

## 10. Rollback và transaction khi trộn định dạng

Mỗi changeset cần được đánh giá khả năng rollback theo **loại thay đổi**, không theo đuôi file. Liquibase có thể tự sinh rollback cho một số change type, nhưng không thể mặc định đảo ngược mọi SQL tùy ý hoặc mọi thao tác dữ liệu. Với formatted SQL, rollback tường minh thường đặc biệt cần thiết.

Trong ví dụ ở phần 4, thứ tự rollback theo số changeset (trong phạm vi phù hợp) sẽ xét các changeset đã áp dụng theo chiều ngược: thay đổi JSON, index SQL, dữ liệu YAML, rồi đến bảng XML. Từng rollback cần hợp lệ trên database đích. Nếu một changeset có thao tác không thể khôi phục dữ liệu đã mất, cần backup, dữ liệu dự phòng hoặc quy trình phục hồi riêng.

Không nên cho rằng vì XML và YAML đã qua validate nên SQL trong formatted SQL sẽ thực hiện transaction hoặc rollback giống hệt nhau. Các hệ quản trị database khác nhau về khả năng rollback DDL; một số thao tác commit ngầm hoặc không hỗ trợ transaction. Cần xem xét `runInTransaction` và hành vi database cho từng changeset, đặc biệt với lệnh đặc thù PostgreSQL như một số biến thể tạo index.

Sự hỗn hợp định dạng không làm thay đổi nguyên tắc cốt lõi: **migration phải xác định được kết quả mong muốn, điều kiện chạy, dấu vết lịch sử và phương án xử lý khi thất bại**.

## 11. Tích hợp Spring Boot và CI/CD cho changelog hỗn hợp

Một cấu hình Spring Boot chỉ cần trỏ đến root changelog:

```yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    enabled: true
```

Các file XML, YAML, JSON, formatted SQL được root include phải có mặt trong artifact, đúng đường dẫn resource và tương thích với Liquibase version có trong ứng dụng. Lưu ý artifact đóng gói có thể khác filesystem lúc chạy IDE. Để kiểm tra nội dung JAR mà không khởi chạy ứng dụng, có thể dùng công cụ liệt kê archive trong quy trình build:

```bash
jar tf path/to/application.jar
```

Một pipeline CI/CD có thể chuẩn hóa các bước:

1. Chạy static review: kiểm tra chính sách đặt tên, thứ tự file, thay đổi đối với changelog đã triển khai.
2. Kiểm tra root changelog và toàn bộ file con/SQL/CSV được include có mặt trong artifact.
3. Dùng cùng cấu hình Liquibase để chạy `validate`.
4. Xem changeset pending bằng `status --verbose` trên database phù hợp.
5. Sinh SQL dự kiến bằng `update-sql` và review sự khác biệt theo DBMS.
6. Chạy migration trong một bước deploy được kiểm soát.
7. Kiểm tra `DATABASECHANGELOG` và trạng thái schema/dữ liệu sau migration.
8. Thực hành rollback trên môi trường thử nghiệm với lịch sử đại diện trước khi cần rollback thực tế.

Ví dụ lệnh khái niệm sau khi đã cấu hình kết nối và root changelog:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
```

Việc dùng một bộ changelog cho dev, test, staging và production không đảm bảo mọi database có cùng lịch sử. Context/label, database-specific SQL và các lần deploy thất bại có thể khiến lịch sử khác nhau. Trước khi chuyển đổi file hoặc thêm migration phụ thuộc, hãy kiểm tra lịch sử của môi trường đích thay vì suy đoán từ môi trường khác.

Nếu nhiều instance Spring Boot cùng khởi động, Liquibase có cơ chế khóa thông qua `DATABASECHANGELOGLOCK`; tuy vậy, một bước migration riêng trong pipeline giúp thời điểm triển khai rõ ràng hơn và tránh để nhiều instance cùng cạnh tranh áp dụng thay đổi.

## 12. Tình huống thực hành và các quyết định kiến trúc

### Tình huống A: Nhóm cũ dùng XML, nhóm mới thích YAML

Giữ các XML đã triển khai trong cây changelog; thêm file YAML mới cho migration tiếp theo và include từ root. Không đổi nội dung XML cũ chỉ để làm repository đồng nhất. Quy ước cho YAML mới nên quy định thụt lề, cách đặt `id`/`author`, rollback và đường dẫn include.

### Tình huống B: Một migration cần SQL đặc thù PostgreSQL

Dùng formatted SQL nếu toàn bộ thay đổi dễ diễn đạt bằng SQL và nhóm kiểm soát tốt rollback; hoặc dùng YAML/XML/JSON bọc `sqlFile` khi cần precondition phức tạp và chính sách chung. Gắn giới hạn DBMS phù hợp, review SQL trước khi triển khai và kiểm thử với đúng PostgreSQL version của môi trường đích.

### Tình huống C: Muốn dùng includeAll cho mọi định dạng

Chỉ quét thư mục chứa các file changelog hợp lệ, đặt tên có tiền tố thứ tự ổn định, kiểm tra nguy cơ file SQL/CSV phụ trợ bị quét nhầm. Nếu nhiều dependencies nhạy cảm với thứ tự, chuyển sang `include` tường minh. Không dựa vào đuôi file để tự sắp xếp quan hệ phụ thuộc.

### Tình huống D: Đã triển khai YAML, nay muốn chuyển sang JSON

Để yên changeset YAML đã chạy; tạo các changeset JSON mới bên cạnh. Nếu công cụ bắt buộc chuyển đổi file lịch sử, hãy lập kế hoạch bảo toàn danh tính/checksum riêng, thực nghiệm trên database copy và xem `status`/`update-sql` trước khi phát hành.

### Tình huống E: File SQL chạy từ CLI nhưng Spring Boot không tìm thấy

Kiểm tra SQL là formatted SQL changelog hay tài nguyên `sqlFile`; xác nhận đường dẫn tương đối từ changelog chứa tham chiếu; kiểm tra các file đã vào JAR hay chưa. Với Spring Boot, root thường trỏ tới classpath; với CLI, search path quyết định file nào có thể được tìm. Dùng một cấu trúc tài nguyên nhất quán và kiểm tra artifact thật.

## 13. Checklist review trước khi merge

- [ ] Dự án có root changelog rõ ràng, được cả CLI và Spring Boot truy cập đúng.
- [ ] Từng file con là changelog hợp lệ theo định dạng mà Liquibase hỗ trợ; SQL thường được tham chiếu qua change phù hợp.
- [ ] Thứ tự `include` phản ánh đúng phụ thuộc schema và dữ liệu; thư mục `includeAll` không chứa file phụ trợ ngoài ý muốn.
- [ ] `id`, `author` và đường dẫn logic của changeset đã triển khai vẫn ổn định.
- [ ] Không chuyển đổi hoặc đổi đuôi file đã chạy mà thiếu kế hoạch đối chiếu `DATABASECHANGELOG` và checksum.
- [ ] Những tính năng đặc thù formatted SQL đã được xác nhận tương thích với phiên bản/edition Liquibase đang sử dụng.
- [ ] SQL/CSV đi kèm được đóng gói đúng và các đường dẫn `relativeToChangelogFile` được tính từ file tham chiếu.
- [ ] Các thay đổi dữ liệu và SQL đặc thù có rollback khả thi hoặc phương án phục hồi rõ ràng.
- [ ] Context, label, precondition và giới hạn DBMS không làm mất một thay đổi tiền đề.
- [ ] `validate`, `status --verbose` và `update-sql` đã được kiểm tra với cấu hình môi trường đại diện.
- [ ] Pipeline và ứng dụng đều dùng cùng bộ changelog, đã kiểm tra artifact triển khai cuối cùng.

Phối hợp XML, YAML, JSON và formatted SQL cho phép chọn cú pháp phù hợp với từng loại migration mà vẫn duy trì một hệ thống triển khai chung. Điều quyết định độ tin cậy là cách tổ chức root changelog, sự ổn định của danh tính changeset, đường dẫn tài nguyên, thứ tự phụ thuộc và quy trình kiểm chứng — không phải việc ép mọi file về cùng một định dạng.

