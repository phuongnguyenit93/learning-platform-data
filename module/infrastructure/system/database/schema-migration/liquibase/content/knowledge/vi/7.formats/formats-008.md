# Kiểm tra mức hỗ trợ cú pháp theo phiên bản và loại changelog

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Định dạng**, việc chọn XML, YAML, JSON hay formatted SQL để viết changelog không chỉ là sở thích trình bày. Một cấu trúc được Liquibase chấp nhận còn phụ thuộc **phiên bản Liquibase thực sự chạy**, **loại changelog**, **tính năng hoặc extension đang sử dụng** và **hệ quản trị cơ sở dữ liệu đích**. Vì thế, trước khi đưa một cú pháp mới vào migration, cần biết nó có được hỗ trợ trong đúng tổ hợp môi trường đang triển khai hay không.

Liquibase giúp quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai, đồng thời phục vụ rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một changelog có cấu trúc hợp lệ nhưng dùng cú pháp chưa được phiên bản triển khai hỗ trợ vẫn có thể khiến pipeline hoặc ứng dụng không khởi động được. Ngược lại, một thay đổi được parser chấp nhận chưa chắc đã sinh SQL phù hợp với DBMS đích.

Mục tiêu bài học là biết **kiểm tra mức hỗ trợ**, phân loại nguyên nhân khi xảy ra lỗi, và xây dựng một quy trình thử nghiệm có thể lặp lại để không phải đoán khả năng tương thích của changelog.

## 1. Một câu hỏi “cú pháp có được hỗ trợ không?” có bốn lớp

Khi gặp một ví dụ Liquibase trên tài liệu hoặc trong pull request, cần tách bốn câu hỏi khác nhau:

1. **Phiên bản Liquibase có hiểu tính năng đó không?** Một thuộc tính, change type hoặc cơ chế có thể được bổ sung, thay đổi hoặc ngừng khuyến nghị giữa các phiên bản. Cú pháp của ví dụ được viết cho phiên bản mới chưa chắc hoạt động với phiên bản cũ trong ứng dụng.
2. **Định dạng changelog có cách biểu diễn tính năng đó không?** XML, YAML, JSON và formatted SQL có quy tắc cú pháp riêng. Ví dụ một thuộc tính của changeset được viết bằng XML attribute, YAML key hoặc comment directive trong formatted SQL; không thể sao chép nguyên văn từ định dạng này sang định dạng khác.
3. **Có yêu cầu edition hoặc extension không?** Một số khả năng phụ thuộc phiên bản thương mại, extension, plugin hay trình thực thi SQL bổ sung. Chỉ đổi đuôi file hoặc thêm thuộc tính sẽ không tự cài khả năng còn thiếu.
4. **DBMS đích có thực thi được thay đổi đó không?** Parser có thể đọc được change nhưng SQL sinh ra không được DBMS hỗ trợ, hoặc hỗ trợ với điều kiện và giới hạn khác nhau.

Có thể biểu diễn bằng bảng sau:

| Lớp kiểm tra | Điều cần xác nhận | Dấu hiệu lỗi thường gặp |
|---|---|---|
| Engine và phiên bản | Phiên bản Liquibase đọc và thực thi changelog | Không nhận diện change type hoặc thuộc tính mới |
| Parser theo định dạng | XML/YAML/JSON/formatted SQL diễn đạt cú pháp như thế nào | Lỗi cấu trúc, tên key, directive hoặc parse |
| Edition/extension | Tính năng và parser/extension đã có trong runtime chưa | Không tìm thấy implementation hoặc thông báo tính năng không khả dụng |
| DBMS, driver và executor | SQL tạo ra có chạy được trên nền tảng đích không | Lỗi SQL, ràng buộc, giao dịch hoặc kiểu dữ liệu |

**Không có kết luận chung kiểu “Liquibase hỗ trợ cú pháp X” nếu chưa xác định bốn lớp này.** Một thay đổi có thể chạy trên PostgreSQL với bản CLI mới nhưng thất bại trên DBMS khác, hoặc chạy khi dùng CLI nhưng không được ứng dụng Spring Boot với dependency Liquibase cũ nhận diện.

## 2. Phân biệt bốn loại changelog thường gặp

Liquibase có thể quản lý cùng một mục tiêu thay đổi bằng những định dạng có cách biểu diễn khác nhau.

| Định dạng | Cách mô tả thay đổi | Cách kiểm tra cấu trúc | Lưu ý quan trọng |
|---|---|---|---|
| **XML** | Các phần tử, thuộc tính, namespace | XML well-formed; XSD của Liquibase; engine validation | XSD được tham chiếu có thể giới hạn các element/attribute được coi là hợp lệ |
| **YAML** | Key, danh sách, cấu trúc thụt lề | YAML parser rồi đến parser/changelog validator của Liquibase | Kiểu scalar và độ thụt lề dễ gây lỗi; không có cơ chế XML XSD tương đương |
| **JSON** | Object, array, các key tương ứng | JSON parser rồi đến Liquibase validator | Dấu phẩy, dấu ngoặc, kiểu dữ liệu và cấu trúc mảng cần chính xác |
| **Formatted SQL** | SQL thuần kèm directive trong comment | Bộ nhận diện formatted SQL và parser tương ứng | Không mặc định hỗ trợ mọi cấu trúc, attribute hoặc precondition giống XML/YAML/JSON |

**Formatted SQL** khác với một file SQL tùy ý được tham chiếu bằng **sqlFile**. Một file bắt đầu bằng directive formatted SQL có thể chứa nhiều changeset được nhận diện riêng. Trong khi đó, file SQL thường được gọi từ một changeset XML/YAML/JSON bằng sqlFile là phần nội dung được changeset bao bọc; chính changeset bao bên ngoài mới mang ID, author và lịch sử thực thi.

Vì vậy, khi cần so sánh mức hỗ trợ, trước hết phải xác định file là **changelog formatted SQL**, **changelog cấu trúc XML/YAML/JSON**, hay **SQL nội dung được nhúng/tham chiếu**.

## 3. Cùng một thay đổi, bốn cú pháp khác nhau

Các ví dụ dưới đây đều minh họa **cùng một mục đích**: tạo bảng kiểm tra cú pháp **lb_syntax_probe** với khóa chính **id**. Chúng là **bốn phương án thay thế**, không phải bốn migration cần chạy cùng lúc. Nếu đưa cả bốn vào một changelog, các lần tạo bảng sau sẽ gặp lỗi vì bảng đã tồn tại.

### 3.1. YAML changelog

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "probe-create-table"
      author: "platform"
      changes:
        - createTable:
            tableName: lb_syntax_probe
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            tableName: lb_syntax_probe
~~~

YAML dùng danh sách dưới **databaseChangeLog**, mỗi item có **changeSet**; các **changes** tiếp tục là một danh sách. Lỗi thường gặp là đặt **changes** sai cấp thụt lề, viết key sai chữ hoa/chữ thường hoặc dùng scalar bị parser suy diễn sai kiểu. Khi một chuỗi trông giống số, ngày hay boolean nhưng cần giữ nguyên như văn bản, nên đặt trong dấu nháy.

### 3.2. JSON changelog

~~~json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "probe-create-table",
        "author": "platform",
        "changes": [
          {
            "createTable": {
              "tableName": "lb_syntax_probe",
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
                }
              ]
            }
          }
        ],
        "rollback": [
          {
            "dropTable": {
              "tableName": "lb_syntax_probe"
            }
          }
        ]
      }
    }
  ]
}
~~~

JSON yêu cầu object và array hợp lệ; phần tử cuối trong object/array không được có dấu phẩy thừa. Trong JSON, **true** là boolean còn **"true"** là chuỗi. Một file có JSON hợp lệ vẫn có thể sai cấu trúc changelog do Liquibase yêu cầu, nên cần thêm bước validation bằng runtime thật.

### 3.3. XML changelog

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.24.xsd">

    <changeSet id="probe-create-table" author="platform">
        <createTable tableName="lb_syntax_probe">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
        </createTable>
        <rollback>
            <dropTable tableName="lb_syntax_probe"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Đường dẫn **dbchangelog-4.24.xsd** trong ví dụ minh họa việc tham chiếu **một phiên bản XSD cụ thể**. Nó không tuyên bố mọi engine sẽ dùng hoặc hỗ trợ XSD này. Dự án phải chọn XSD phù hợp với phiên bản Liquibase và bộ tính năng đang dùng, rồi kiểm tra trực tiếp trong môi trường tương ứng.

### 3.4. Formatted SQL changelog

~~~sql
--liquibase formatted sql

--changeset platform:probe-create-table
CREATE TABLE lb_syntax_probe (
    id BIGINT PRIMARY KEY
);

--rollback DROP TABLE lb_syntax_probe;
~~~

File được nhận diện bằng header formatted SQL và directive **--changeset author:id**. SQL cần tuân thủ cú pháp DBMS. Rollback trong ví dụ được chỉ định bằng directive của formatted SQL, vì Liquibase không thể mặc định suy ra cách đảo ngược mọi câu SQL tự viết.

**Ý nghĩa của so sánh:** Cùng một mục tiêu nhưng bốn cách khai báo và bốn luồng parse khác nhau. Một phiên bản hỗ trợ change type **createTable** trong YAML/XML/JSON không bảo đảm mọi directive bổ sung ở formatted SQL đều có cùng phạm vi hỗ trợ.

## 4. Kiểm tra phiên bản Liquibase thực sự chạy

Bước đầu của mọi cuộc điều tra tương thích là xác định **runtime**, không suy đoán từ file mẫu, trang hướng dẫn hay phiên bản IDE.

Với Liquibase CLI, có thể kiểm tra:

~~~bash
liquibase --version
~~~

Khi ứng dụng Spring Boot chạy Liquibase, phiên bản được sử dụng thường là phiên bản của **dependency Liquibase trên classpath của ứng dụng**. Phiên bản CLI cài trên máy lập trình có thể khác. Vì vậy, cần xác nhận phiên bản thực tế trong cả ba nơi:

- Máy phát triển hoặc công cụ soạn migration.
- CI/CD job thực hiện validation hoặc update.
- Runtime Spring Boot hoặc migration job triển khai vào database.

Một quy trình đáng tin cậy cần ghi nhận cùng lúc **phiên bản Liquibase**, **edition/license**, **extension được nạp**, **DBMS và phiên bản DBMS**, **driver**, cùng **định dạng changelog**. Nếu lỗi chỉ xuất hiện ở một môi trường, các thông số này là điểm so sánh đầu tiên.

Ví dụ một thay đổi được viết bằng cú pháp mới trong YAML có thể vượt qua kiểm tra trên CLI của một lập trình viên nhưng thất bại khi Spring Boot khởi động vì ứng dụng dùng phiên bản Liquibase khác. Đây là lỗi **lệch runtime**, chưa chắc là lỗi YAML.

Không nên “sửa” bằng cách chỉ đổi URL XSD, đổi tên thuộc tính ngẫu nhiên hoặc bỏ qua validation. Việc nâng phiên bản Liquibase cần kiểm tra tương thích changelog hiện có, checksum, hành vi thực thi và driver/DBMS.

## 5. XML XSD không thay thế kiểm tra engine

XML có thêm một lớp quan trọng: **namespace và XSD**. XSD quy định những phần tử, thuộc tính và vị trí cấu trúc được coi là hợp lệ theo schema đó.

Khi XML không hợp lệ, có thể gặp các nhóm lỗi:

- XML chưa well-formed: thiếu thẻ đóng, ký tự chưa escape, thuộc tính bị thiếu dấu nháy.
- Namespace hoặc **schemaLocation** sai, XSD không tải được hay không được trình phân giải nhận diện.
- Element hoặc attribute không có trong XSD đang tham chiếu.
- XSD chấp nhận cấu trúc nhưng runtime Liquibase lại không hỗ trợ tính năng tương ứng, hoặc ngược lại engine có khả năng nhưng XML đang tham chiếu XSD cũ gây lỗi trước khi thực thi.

Ba điều cần nhớ:

1. **Phiên bản XSD không phải lệnh nâng cấp Liquibase.** Đổi từ XSD cũ sang XSD mới không tự làm JAR hoặc binary trong môi trường thay đổi.
2. **XSD kiểm tra cú pháp XML, không kiểm tra đầy đủ khả năng SQL trên DBMS.** Một phần tử đúng schema vẫn có thể không được DBMS đích hỗ trợ hoặc có giới hạn riêng.
3. **XSD latest và XSD ghim phiên bản có mục tiêu khác nhau.** Dùng latest có thể thuận tiện khi thử nghiệm, nhưng môi trường cần tái lập nên thống nhất rõ phiên bản runtime và cách tham chiếu schema; ghim một XSD phù hợp giúp việc review và truy nguyên dễ hơn.

Với các extension có namespace riêng, còn phải kiểm tra namespace và XSD của extension, đồng thời xác nhận extension thực sự được nạp. Việc XML chấp nhận một namespace không bảo đảm runtime có phần implementation cần thiết để chạy nó.

## 6. YAML và JSON: hợp lệ về định dạng vẫn có thể sai Liquibase

YAML hoặc JSON được parse thành cấu trúc dữ liệu trước khi Liquibase diễn giải thành changelog. Vì thế, phải phân biệt:

**Lớp một: cú pháp ngôn ngữ dữ liệu**

- YAML: thụt lề, dấu hai chấm, dấu nháy, danh sách và kiểu scalar.
- JSON: dấu ngoặc, dấu phẩy, string, number, boolean, null và array.

**Lớp hai: mô hình changelog**

- Root phải đúng, ví dụ **databaseChangeLog**.
- Các item phải là dạng Liquibase nhận diện như **changeSet**, **include**, hoặc phần tử thích hợp khác của changelog.
- Tên change type và attribute phải là tên mà engine hỗ trợ.
- Thuộc tính phải nằm đúng vị trí và dùng đúng kiểu dữ liệu.

Ví dụ một đoạn YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-01"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: preferred_name
                  type: VARCHAR(120)
~~~

Nếu lỡ đưa **changes** ra ngang cấp với **changeSet** vì sai thụt lề, YAML vẫn có thể đọc được thành cấu trúc hợp lệ, nhưng Liquibase không diễn giải nó thành changeset mong đợi. Ngược lại, sai kiểu dữ liệu hoặc tên thuộc tính có thể phát sinh thông báo parse/validation tùy phiên bản.

Đặc biệt, không nên sao chép XML attribute sang YAML/JSON mà không xem cách ánh xạ theo định dạng. Một khái niệm có thể cùng tên nhưng vị trí hoặc cấu trúc biểu diễn khác nhau. Cách kiểm tra chắc chắn nhất là tạo changelog tối thiểu bằng định dạng mục tiêu và cho **đúng runtime Liquibase** parse, validate và sinh SQL.

## 7. Formatted SQL: kiểm tra directive theo phiên bản

Formatted SQL hấp dẫn khi nhóm muốn giữ SQL rõ ràng, dùng cú pháp DBMS cụ thể hoặc xem câu lệnh trực tiếp. Tuy nhiên, nó phụ thuộc nhiều vào **comment directive** mà parser của phiên bản đang dùng nhận diện.

Các thành phần cơ bản thường có:

~~~sql
--liquibase formatted sql

--changeset platform:add-customer-code
ALTER TABLE customer ADD COLUMN customer_code VARCHAR(40);

--rollback ALTER TABLE customer DROP COLUMN customer_code;
~~~

Khi cần dùng tính năng nâng cao như **precondition, context/label, include, rollback nhiều câu lệnh, điều khiển delimiter hoặc runWith**, phải xem kỹ phiên bản Liquibase, edition và cú pháp chính xác dành riêng cho formatted SQL. Mức hỗ trợ của một số directive không nhất thiết xuất hiện cùng thời điểm hoặc có cùng giới hạn với XML/YAML/JSON.

Ví dụ, **runOnChange** có thể được cấu hình trong thuộc tính changeset của định dạng cấu trúc; với formatted SQL, nó được diễn đạt qua directive comment và phải tuân đúng chính tả, khoảng trắng, dấu hai chấm và quy tắc parser tương ứng. Không nên suy luận rằng một thuộc tính hợp lệ trong XML có thể được thêm nguyên văn vào dòng SQL rồi tự động hoạt động.

Các kiểm tra quan trọng:

- File có được parser nhận diện thật sự là **formatted SQL** không?
- Header và các directive có ở vị trí hợp lệ không?
- Parser của phiên bản đang dùng có nhận diện đúng attribute/directive mới không?
- Các câu lệnh có dấu chấm phẩy, block, procedure hoặc delimiter đặc biệt có bị tách sai không?
- Rollback có được chỉ định và kiểm thử trên DBMS thực tế không?
- Có yêu cầu extension hoặc executor chuyên dụng không?

Một lỗi thường gặp là chỉ chạy trực tiếp file bằng trình SQL của database thấy thành công, rồi kết luận changelog Liquibase cũng hợp lệ. Trình SQL thông thường bỏ qua hoặc hiểu comment theo cách khác; Liquibase lại phải parse các directive và ghi nhận lịch sử changeset, nên **hai kiểu kiểm tra không tương đương**.

## 8. Những đặc tính dễ bị hiểu nhầm là “cú pháp đã hỗ trợ”

### 8.1. Change type và attribute

Ví dụ **addColumn**, **createIndex**, **modifyDataType** hoặc một thuộc tính của changeset có thể xuất hiện trong mô tả Liquibase. Cần xác minh cả hai cấp: engine có nhận diện change type/attribute và nó có được biểu diễn đúng trong định dạng changelog được chọn không. Một thuộc tính có mặt trong tài liệu hiện tại chưa đủ chứng minh nó khả dụng trong phiên bản cũ của dự án.

### 8.2. Precondition

**preConditions** được dùng để kiểm tra điều kiện trước khi tiếp tục. Tuy nhiên, khả năng khai báo một precondition cụ thể có thể phụ thuộc định dạng, vị trí (changelog hay changeset), phiên bản và các giới hạn parser. Một đoạn XML có **sqlCheck** không thể được chuyển thành dòng formatted SQL theo suy đoán. Hãy kiểm chứng cú pháp của chính định dạng và phiên bản đang dùng.

Ngoài ra, cần phân biệt **parse được điều kiện** với **điều kiện chạy và trả kết quả đúng trên DBMS**. Một câu SQL dùng trong sqlCheck có thể hợp lệ về cú pháp Liquibase nhưng không hợp lệ trên database.

### 8.3. Rollback

XML/YAML/JSON có thể khai báo cấu trúc rollback theo change type. Formatted SQL dùng cú pháp rollback riêng trong comment. Không phải change nào cũng có rollback tự động an toàn, nhất là SQL tùy chỉnh hoặc dữ liệu đã biến đổi. Khả năng parser nhận rollback chỉ chứng minh cấu trúc hợp lệ; rollback vẫn phải được kiểm tra trên database thử nghiệm.

### 8.4. Context, label và điều kiện môi trường

Context/label giúp lựa chọn changeset theo môi trường hoặc mục tiêu phát hành. Tên thuộc tính, biểu thức và cách ghi trong formatted SQL cần được xác nhận theo phiên bản. Nếu một thay đổi dùng **dbms**, phải kiểm tra giá trị DBMS được nhận diện và thực sự áp dụng đúng nền tảng. Không nên trộn “parser chấp nhận thuộc tính” với “pipeline đã cấu hình đúng context/label”.

### 8.5. Include và đường dẫn

**include** và **includeAll** giúp chia changelog thành nhiều file, nhưng khả năng sử dụng và cú pháp phụ thuộc định dạng cùng phiên bản. Còn phải xét **relativeToChangelogFile**, đường dẫn resource/classpath và **logicalFilePath**. Thay đổi đường dẫn hoặc cách nhận diện file có thể ảnh hưởng bộ định danh changeset, tạo nguy cơ Liquibase xem một changeset cũ là mới. Đây là vấn đề lịch sử triển khai, không chỉ là lỗi parser.

### 8.6. Executor, delimiter và SQL đặc thù DBMS

SQL chứa procedure, trigger, block nhiều câu lệnh hoặc cú pháp đặc thù có thể cần cấu hình delimiter hay cách thực thi riêng. Các thuộc tính như **endDelimiter**, **splitStatements**, **stripComments** hoặc **runWith** cần được đánh giá theo change type, edition/extension, định dạng và phiên bản. Nếu parser chấp nhận nhưng chia câu lệnh sai, lỗi có thể chỉ xuất hiện khi update thực tế.

## 9. Quy trình kiểm chứng cú pháp mới trước khi merge

Có thể áp dụng một quy trình ngắn nhưng đủ bằng chứng:

### Bước 1 — Ghi lại tổ hợp môi trường

Tạo một bản ghi trong pull request hoặc tài liệu triển khai:

~~~text
Liquibase CLI/runtime: <phiên bản xác nhận từ hệ thống>
Spring Boot dependency: <phiên bản Liquibase trong ứng dụng, nếu có>
Edition/extension: <tên và phiên bản liên quan>
Changelog type: XML | YAML | JSON | formatted SQL
Target DBMS: <tên và phiên bản>
Driver/executor: <phiên bản hoặc cấu hình>
Feature đang thử: <change type / attribute / directive>
~~~

Các giá trị trong dấu ngoặc nhọn là chỗ điền thông tin thực tế, không phải cú pháp CLI. Mục tiêu là tránh kết luận mơ hồ như “máy tôi chạy được”.

### Bước 2 — Xác nhận nguồn mô tả đúng phiên bản

Đọc tài liệu cú pháp, tài liệu định dạng changelog, release notes hoặc tài liệu extension tương ứng với **phiên bản thực tế**. Khi tài liệu ghi một khả năng mới được bổ sung ở phiên bản nào đó, hãy coi đó là điều kiện phiên bản; đừng suy từ việc một ví dụ trên trang tài liệu hiện tại mà cho rằng mọi bản cũ đều hỗ trợ.

Với XML, kiểm tra cả XSD đang tham chiếu. Với formatted SQL, xác nhận directive thật sự được hỗ trợ, kể cả precondition hoặc include nếu cần. Nếu không thể xác nhận bằng tài liệu phiên bản, thực hiện thử nghiệm tối thiểu và coi kết luận là **đã kiểm tra trên runtime cụ thể**, không mở rộng thành cam kết cho mọi phiên bản.

### Bước 3 — Tạo changelog tối thiểu cho chính tính năng cần thử

Bỏ những thay đổi không liên quan. Nếu mục tiêu là kiểm chứng **runOnChange** trong formatted SQL, dùng một changeset thử nhỏ có thể chạy lại an toàn và quan sát việc chạy lại. Nếu mục tiêu là kiểm chứng một precondition, tạo điều kiện có kết quả dự kiến và quan sát cả trường hợp đạt lẫn không đạt.

Changelog tối thiểu giúp phân biệt “không hỗ trợ cú pháp” với lỗi do phụ thuộc, thứ tự migration, đường dẫn hoặc dữ liệu.

### Bước 4 — Parse và validate bằng đúng binary/JAR

Các lệnh kiểm tra minh họa:

~~~bash
liquibase --version
liquibase --changelog-file=changelog/probe.yaml validate
liquibase --changelog-file=changelog/probe.yaml update-sql
~~~

Đường dẫn **changelog/probe.yaml** chỉ là ví dụ; thay bằng file thật. Cấu hình kết nối và xác thực nên đến từ cấu hình môi trường thử nghiệm của Liquibase, không ghi mật khẩu vào tài liệu hoặc commit. Một số câu lệnh cần database để kiểm tra lịch sử và điều kiện thực thi.

- **validate** kiểm tra khả năng đọc changelog và các quy tắc validation mà phiên bản Liquibase hỗ trợ.
- **update-sql** cho biết các câu SQL dự kiến phát ra trong lần update, giúp phát hiện khác biệt trong việc sinh SQL và lựa chọn changeset.
- Thành công của hai bước trên **chưa chứng minh migration thực thi thành công hoặc rollback an toàn** trên DBMS thật.

Nếu thử XML, dùng đúng XSD đã được chọn trong file. Nếu thử formatted SQL, bảo đảm lệnh đang trỏ tới file formatted SQL thực sự.

### Bước 5 — Thực thi trên database thử nghiệm và kiểm tra rollback

Trên database disposable hoặc bản sao được phép dùng để thử nghiệm:

1. Tạo trạng thái đầu vào giống môi trường dự kiến triển khai.
2. Chạy Liquibase update với đúng cấu hình môi trường.
3. Kiểm tra schema/dữ liệu sau cập nhật và dòng tương ứng trong **DATABASECHANGELOG**.
4. Nếu migration có rollback, thử rollback theo kịch bản cho phép và kiểm tra kết quả.
5. Chạy cập nhật lần nữa khi phù hợp để kiểm tra tính tái lập và cách Liquibase xử lý lịch sử.

Không chạy thử các bước destructive hoặc **rollback** lên production chỉ để xác minh cú pháp.

### Bước 6 — Lặp lại ở runtime phát hành

Nếu CI/CD hoặc Spring Boot dùng binary/JAR khác với máy lập trình, lặp lại kiểm tra bằng **artifact triển khai thực tế**. Cần kiểm tra cả đường cài mới và đường nâng cấp từ database đã có DATABASECHANGELOG; chỉ chạy trên database trống có thể bỏ sót vấn đề checksum, thứ tự hoặc định danh changeset.

## 10. Chẩn đoán lỗi theo giai đoạn, không sửa mò

| Khi lỗi xuất hiện | Khả năng cần kiểm tra trước | Cách xác minh |
|---|---|---|
| Trước khi vào Liquibase | File YAML/JSON/XML không parse được | Kiểm tra cú pháp ngôn ngữ, encoding, ngoặc/thụt lề/namespace |
| Khi Liquibase đọc changelog | Tên element, change type, attribute hoặc directive không được parser hỗ trợ | Kiểm tra định dạng, engine version, extension và changelog tối thiểu |
| Khi XML schema validation | XSD sai phiên bản hoặc element/attribute nằm ngoài XSD | Kiểm tra namespace, schemaLocation, XSD và runtime tương ứng |
| Khi sinh SQL | Change type không sinh được SQL cho DBMS đích hoặc thiếu executor | Dùng update-sql trên đúng DBMS, kiểm tra extension và driver |
| Khi thực thi update | SQL, khóa, giao dịch, quyền hoặc dữ liệu vi phạm ràng buộc | Chạy trên DB thử nghiệm, xem SQL và trạng thái database |
| Khi chạy trên Spring Boot nhưng CLI thành công | Runtime hoặc cấu hình của hai nơi khác nhau | Đối chiếu JAR, extension, changelog path, property, context, driver |
| Khi chỉ một môi trường báo checksum | Định nghĩa changeset hoặc định danh lịch sử đã thay đổi | So sánh artifact, đường dẫn, ID/AUTHOR/FILENAME và DATABASECHANGELOG |

Một thông báo kiểu **unknown attribute** thường gợi ý khác biệt schema/parser/phiên bản hoặc tên thuộc tính sai; một lỗi SQL runtime không nhất thiết liên quan mức hỗ trợ parser. Phải giữ nguyên thông báo lỗi và stack trace liên quan khi điều tra, thay vì chỉ nhìn dòng cuối.

### Cách tránh ba kết luận sai phổ biến

**Sai lầm 1: “XML XSD mới hơn nên Liquibase chắc chắn hỗ trợ.”** XSD không cập nhật engine, và engine còn phải có change implementation phù hợp.

**Sai lầm 2: “validate thành công nghĩa là SQL chạy được trên mọi database.”** Validate kiểm tra cấu trúc và những điều kiện engine có thể xác định ở giai đoạn đó; DBMS và dữ liệu thực tế còn có ràng buộc riêng.

**Sai lầm 3: “Ví dụ XML chạy được nên copy sang formatted SQL cũng được.”** Mỗi định dạng có parser và cách khai báo riêng; những khả năng nâng cao có thể khác nhau theo phiên bản.

## 11. Khi nâng cấp Liquibase hoặc chuyển đổi định dạng

Đổi từ XML sang YAML/JSON hoặc formatted SQL, cũng như nâng phiên bản Liquibase, có thể làm thay đổi nhiều hơn cách trình bày. Một số điểm cần xem xét:

- **Tương đương ngữ nghĩa**: thứ tự change, precondition, context/label, rollback và cách xử lý comment/SQL phải giữ đúng ý nghĩa.
- **Định danh changeset**: nếu đổi đường dẫn changelog mà không quản lý logicalFilePath, Liquibase có thể coi các changeset đã triển khai là changeset mới.
- **Checksum**: biến đổi định dạng hoặc cách parser chuẩn hóa thay đổi có thể ảnh hưởng việc đối chiếu checksum của changeset đã chạy. Không giả định chuyển định dạng là thao tác an toàn chỉ vì kết quả SQL nhìn giống nhau.
- **Khả năng tương thích ngược**: xác định phiên bản Liquibase thấp nhất cần hỗ trợ, tránh vô tình dùng attribute mới khi pipeline cũ vẫn còn được triển khai.
- **Extension và edition**: cập nhật đồng bộ nếu syntax mới cần parser/change/executor riêng.
- **DBMS**: kiểm tra SQL sinh ra và rollback trên từng DBMS thực sự nằm trong phạm vi hỗ trợ của dự án.

Một chiến lược an toàn là giữ bất biến lịch sử migration đã phát hành và áp dụng định dạng hoặc cú pháp mới từ các changeset mới. Nếu buộc phải chuyển toàn bộ changelog cũ, cần một quy trình chuyển đổi riêng, kiểm chứng trên bản sao database có lịch sử thực tế và giải thích rõ cách bảo toàn định danh, checksum cùng thứ tự triển khai. Không dùng **clear-checksums** để che lỗi chuyển đổi chưa được phân tích.

## 12. Checklist review hỗ trợ cú pháp

Trước khi merge một migration dùng cú pháp hoặc tính năng chưa từng có trong dự án, hãy trả lời:

- Đã xác định đúng loại changelog: XML, YAML, JSON, formatted SQL hay SQL được tham chiếu qua sqlFile?
- Đã xác định phiên bản Liquibase thực sự chạy ở local, CI/CD và Spring Boot?
- Có chênh lệch edition, extension, driver hay executor giữa các môi trường không?
- Đã xem tài liệu đúng phiên bản về change type, attribute, precondition hoặc directive đang dùng?
- Với XML, XSD/namespace có tương ứng và được runtime đọc thành công không?
- Với YAML/JSON, cấu trúc danh sách, kiểu dữ liệu và tên key có đúng parser Liquibase không?
- Với formatted SQL, header, directive, delimiter và rollback có được phiên bản đó nhận diện không?
- Đã chạy validate và update-sql bằng đúng binary/JAR sẽ triển khai chưa?
- Đã thực thi trên DBMS thử nghiệm, kiểm tra DATABASECHANGELOG và thử rollback nếu thích hợp chưa?
- Đã kiểm tra trên database có lịch sử để phát hiện khác biệt định danh và checksum chưa?

**Kết luận:** Kiểm tra mức hỗ trợ cú pháp là kiểm tra toàn bộ đường đi từ **định dạng file → parser Liquibase → phiên bản/edition/extension → SQL thực thi trên DBMS → lịch sử triển khai**. Cách làm đáng tin cậy là ghi rõ môi trường, thử tính năng trong changelog tối thiểu, chạy validation và sinh SQL bằng đúng runtime, rồi kiểm chứng update/rollback trên database thử nghiệm. Nhờ vậy, một lựa chọn cú pháp không trở thành sự cố khi migration đi qua các môi trường và pipeline của hệ thống.

