# Labels và cách gắn nhãn thay đổi trong Liquibase

Trong dự án dùng Liquibase, không phải changeset nào cũng thích hợp để thực thi ở mọi đợt triển khai. Một thay đổi có thể thuộc tính năng thanh toán, một nhóm cải tiến báo cáo, hoặc một bước chuyển đổi dữ liệu cần bật có chủ đích. **Labels** cung cấp metadata để phân loại changeset và kết hợp với **label filter** tại thời điểm thực thi. Nhờ đó, đội phát triển có thể chọn tập thay đổi phù hợp với mục tiêu triển khai mà không phải sao chép changelog cho mỗi môi trường.

Bài học thuộc chương **Bộ lọc thực thi** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Mục tiêu học tập:** sau bài này, bạn có thể giải thích labels là gì, gắn nhãn vào changeset bằng YAML/XML/JSON/formatted SQL, xây dựng biểu thức label filter, phân biệt labels với contexts và database tag, kiểm chứng những changeset sẽ chạy, và thiết kế cách triển khai an toàn khi có nhiều nhóm phát triển hoặc nhiều môi trường.

## 1. Labels là gì và giải quyết vấn đề nào?

**Label** là một tên hoặc thuộc tính phân loại được gắn cho changeset. Ví dụ:

- **billing**: thay đổi thuộc miền nghiệp vụ thanh toán.
- **customer**: thay đổi thuộc miền dữ liệu khách hàng.
- **reporting**: thay đổi phục vụ báo cáo.
- **feature_invoice_v2**: thay đổi thuộc một nhóm chức năng cụ thể.
- **data_backfill**: thay đổi dành cho chuyển đổi dữ liệu.
- **release_2026_11**: thay đổi được nhóm vào một đợt phát hành dự kiến.

Khi chạy Liquibase, **label filter** là biểu thức do người triển khai cung cấp để xác định changeset có nhãn nào phù hợp với lần chạy. Trong nhiều thiết lập Liquibase thông dụng, nếu không cung cấp label filter thì changeset có label thông thường **vẫn có thể được thực thi**; label không mặc nhiên có nghĩa là “chỉ chạy khi được bật”. Đây là điểm đặc biệt quan trọng đối với migration nhạy cảm.

Hãy hình dung:

~~~mermaid
flowchart TD
    A[Changelog chứa các changeset] --> B[Đọc ID, author, labels]
    B --> C{Đã ghi nhận trong DATABASECHANGELOG?}
    C -->|Có| D[Không chạy lại theo mặc định]
    C -->|Chưa| E{Phù hợp bộ lọc và điều kiện?}
    E -->|Không| F[Chưa áp dụng trong lần update này]
    E -->|Có| G[Kiểm tra precondition]
    G --> H[Thực thi thay đổi khi đủ điều kiện]
    H --> I[Cập nhật DATABASECHANGELOG]
~~~

Sơ đồ này mô tả ý tưởng cơ bản, chưa bao quát các ngoại lệ như **runAlways**, **runOnChange**, **MARK_RAN** và cơ chế quản lý lock. Labels là một trong nhiều điều kiện Liquibase xem xét, không thay thế lịch sử triển khai hoặc precondition.

### 1.1. Vấn đề không nên giải quyết bằng labels

Labels không phải:

- Cách chọn JDBC URL, database, schema hoặc tài khoản kết nối.
- Cơ chế phân quyền truy cập database.
- Công cụ thay thế các bước bảo đảm tương thích ngược giữa hai phiên bản ứng dụng.
- Bằng chứng một changeset đã chạy thành công.
- Cơ chế tự động rollback thay đổi không phù hợp.
- Phương pháp bảo đảm một changeset chỉ chạy đúng một lần nếu cấu hình runAlways/runOnChange cho phép hành vi khác.

Nhãn giúp **lựa chọn**, nhưng kết quả cuối cùng vẫn phụ thuộc kết nối, lịch sử DATABASECHANGELOG, bộ lọc khác và trạng thái database.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Được khai báo ở đâu? | Mục đích |
|---|---|---|
| **labels** | Metadata của changeset, hoặc phạm vi được Liquibase hỗ trợ | Mô tả changeset thuộc nhóm nào |
| **label filter** | Lệnh update, cấu hình CLI, Spring Boot hoặc pipeline | Chọn nhóm changeset tương ứng cho lần thực thi |
| **contexts/contextFilter** | Metadata changeset và tham số runtime | Điều kiện thực thi theo ngữ cảnh như dev, test, seed |
| **dbms** | Metadata changeset | Giới hạn theo hệ quản trị cơ sở dữ liệu |
| **precondition** | Trong changelog/changeset | Kiểm tra điều kiện thật của database trước khi chạy |
| **tag database** | Điểm đánh dấu lịch sử triển khai | Hỗ trợ các quy trình như rollback tới một mốc |
| **DATABASECHANGELOG** | Bảng nội bộ trong database đích | Ghi changeset được xử lý và metadata lịch sử |

**Labels khác database tag.** Chỉ thị gắn nhãn changeset bằng **labels** không tự tạo một mốc rollback trong database. Ngược lại, tag database dành cho lịch sử triển khai không được dùng làm label filter.

**Labels khác contexts.** Cả hai có khả năng lọc changeset, nhưng được dùng theo những ngữ nghĩa và quy tắc đánh giá riêng. Một cách tổ chức phổ biến là dùng context cho ngữ cảnh triển khai và label cho tính năng hoặc nhóm thay đổi; đây là **quy ước đội nhóm**, không phải ràng buộc kỹ thuật bắt buộc.

## 3. Gắn labels trong changelog YAML

Ví dụ thay đổi schema cho tính năng hóa đơn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001"
      author: "billing-team"
      labels: "billing,feature_invoice_v2"
      comment: "Create invoice table for invoice v2"
      changes:
        - createTable:
            tableName: invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: invoice_code
                  type: varchar(80)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: invoice
~~~

Ở đây, changeset có hai nhãn **billing** và **feature_invoice_v2**. Nhãn giúp quá trình triển khai lựa chọn nhóm thay đổi nhưng không quyết định một mình khả năng tạo bảng.

Các yếu tố cần xem khi review:

1. **id** và **author** xác định changeset cùng với đường dẫn changelog.
2. **labels** ghi nhận nhóm nghiệp vụ hoặc mục đích.
3. **changes** chứa thay đổi thực tế.
4. **rollback** mô tả cách đảo ngược nếu thích hợp.
5. Changelog gốc phải include tệp hoặc changeset nằm trong luồng đang chạy.
6. Database đích phải được chọn đúng trước khi đánh giá label.

Tên label **feature_invoice_v2** chỉ mang ý nghĩa phân loại. Nó không ép Liquibase kiểm tra ứng dụng có hỗ trợ invoice v2 hay không. Nếu cần kiểm tra trạng thái schema thực tế, hãy bổ sung precondition phù hợp.

### 3.1. Một changeset có nhiều nhãn

Thay đổi có thể cùng thuộc nhiều nhóm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002"
      author: "billing-team"
      labels: "billing,reporting"
      changes:
        - createIndex:
            tableName: invoice
            indexName: idx_invoice_code
            columns:
              - column:
                  name: invoice_code
      rollback:
        - dropIndex:
            tableName: invoice
            indexName: idx_invoice_code
~~~

Việc gắn nhiều nhãn cho một changeset tạo điều kiện kết hợp các thuộc tính như miền nghiệp vụ và loại công việc. Hãy dùng quy ước thống nhất cho dấu phân tách và biểu thức, đồng thời kiểm tra cách phiên bản Liquibase hiện tại phân tích danh sách nhãn.

## 4. Gắn labels trong XML, JSON và formatted SQL

Liquibase hỗ trợ nhiều định dạng changelog. Ý nghĩa phân loại bằng labels vẫn tương tự, dù cú pháp biểu diễn khác nhau.

### 4.1. XML

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
    http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-003"
               author="customer-team"
               labels="customer,feature_profile">
        <addColumn tableName="customer">
            <column name="profile_note" type="varchar(255)"/>
        </addColumn>
        <rollback>
            <dropColumn tableName="customer" columnName="profile_note"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Với XML, thuộc tính **labels** nằm trên phần tử **changeSet**. Cần sử dụng namespace và XSD phù hợp với phiên bản Liquibase đang được triển khai.

### 4.2. JSON

~~~json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "20261119-004",
        "author": "customer-team",
        "labels": "customer,feature_profile",
        "changes": [
          {
            "addColumn": {
              "tableName": "customer",
              "columns": [
                {
                  "column": {
                    "name": "preferred_locale",
                    "type": "varchar(16)"
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
~~~

Ví dụ JSON minh họa khai báo label và change type. Khi dùng trong dự án, nên chạy **validate** với phiên bản Liquibase và schema cấu hình thực tế thay vì giả định mọi ví dụ cấu trúc đều tương thích với mọi phiên bản.

### 4.3. Formatted SQL

Trong formatted SQL, labels có thể được khai báo ngay trên marker changeset:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-005 labels:customer,feature_profile
ALTER TABLE customer
ADD COLUMN preferred_timezone VARCHAR(64);

--rollback ALTER TABLE customer DROP COLUMN preferred_timezone;
~~~

Lưu ý:

- Dòng đầu nhận diện formatted SQL.
- Marker **--changeset author:id** xác định changeset.
- Thuộc tính **labels:** ghi metadata phân loại.
- **--rollback** ghi câu lệnh đảo ngược; độ an toàn của rollback vẫn cần được đánh giá.
- SQL phải phù hợp với DBMS mục tiêu. Với thay đổi dữ liệu và DDL có cú pháp đặc thù, có thể thêm thuộc tính **dbms**.

Những đoạn ví dụ trong bài là tình huống minh họa độc lập; không nên ghép tất cả vào một changelog rồi thực thi nối tiếp khi các bảng hoặc schema tiền đề chưa tồn tại.

## 5. Label filter được cung cấp ở thời điểm nào?

Có hai việc khác nhau cần phối hợp:

**Giai đoạn phát triển:** người viết gắn labels cho changeset trong changelog.

**Giai đoạn thực thi:** người triển khai cấu hình **label filter** cho lệnh chạy Liquibase, ứng dụng Spring Boot hoặc pipeline.

Ví dụ changelog chứa:

~~~text
changeset A: labels = billing
changeset B: labels = reporting
changeset C: labels = billing,feature_invoice_v2
changeset D: không có labels
~~~

Nếu runtime cung cấp bộ lọc **billing**, các changeset gắn nhãn phù hợp có thể được xét để chạy. Tuy nhiên, đừng bỏ qua changeset D: trong cách vận hành Liquibase thường gặp, **changeset không gắn nhãn vẫn được xử lý ngay cả khi một label filter được đặt**. Đây là lý do không thể xem label filter đơn thuần là allowlist kín đối với toàn bộ changelog.

Tương tự, nếu runtime **không cung cấp label filter**, Liquibase thông thường không tự bỏ qua các changeset chỉ vì chúng có nhãn. Cần kiểm tra đúng ngữ nghĩa phiên bản đang dùng và kiểm chứng tập pending thực tế.

### 5.1. Điều kiện cần để một changeset được áp dụng

Một changeset được Liquibase thực thi khi những điều kiện tương ứng đều phù hợp, ví dụ:

- Có trong luồng changelog được nạp.
- Chưa được đánh dấu đã chạy, hoặc thuộc trường hợp chạy lại được hỗ trợ.
- Phù hợp DBMS, contexts và label filter.
- Precondition đạt hoặc được xử lý theo chính sách đã khai báo.
- Kết nối tới đúng database và user có quyền.
- Không có lỗi cú pháp, lock hoặc lỗi thực thi khác ngăn cản.

Labels **không vượt qua** những điều kiện khác.

## 6. Biểu thức logic trong label filter

Label filter có thể dùng biểu thức để chọn nhóm changeset theo các nhãn. Các toán tử và cấu trúc thông dụng gồm:

| Biểu thức | Mục đích |
|---|---|
| **billing** | Chọn changeset phù hợp nhãn billing |
| **billing OR reporting** | Chọn billing hoặc reporting |
| **billing AND feature_invoice_v2** | Chọn nhóm mang đồng thời các điều kiện phân loại |
| **billing AND NOT experimental** | Chọn billing nhưng loại experimental theo ngữ nghĩa parser |
| **(billing OR reporting) AND release_2026_11** | Kết hợp nhóm nghiệp vụ với đợt phát hành |

Dấu ngoặc giúp làm rõ ý định khi biểu thức chứa nhiều toán tử. Một số phiên bản/cú pháp cho phép dấu phẩy như một cách viết phép OR; để tài liệu dễ review, nên ưu tiên biểu thức rõ ràng và xác minh qua **status** hoặc **update-sql**.

### 6.1. Ví dụ bảng phân loại và lựa chọn

Giả sử:

| Changeset | Labels |
|---|---|
| A | billing,release_2026_11 |
| B | reporting,release_2026_11 |
| C | billing,experimental |
| D | customer,release_2026_10 |

Filter dự kiến:

~~~text
(billing OR reporting) AND release_2026_11
~~~

Ý định của biểu thức là chọn **A** và **B**, không chọn **C** hoặc **D**. Tuy nhiên, kết quả cuối cùng phụ thuộc vào đúng cú pháp và cách trình phân tích của phiên bản Liquibase diễn giải labels gắn cho changeset và filter. Trước khi phát hành, phải xác nhận bằng đầu ra của Liquibase thay vì coi bảng minh họa là một phép kiểm chứng thực thi.

### 6.2. Dùng NOT có rủi ro gì?

Biểu thức phủ định như:

~~~text
NOT experimental
~~~

có thể được hiểu khác với mong đợi về **changeset không có nhãn**, hoặc khi changeset có nhiều nhãn. Do đó, đừng dùng một filter phủ định duy nhất để khẳng định mọi thay đổi còn lại đều an toàn.

Nếu một migration rất nhạy cảm, hãy thiết kế **nhóm được phép chạy** theo quy trình kiểm soát, kiểm tra tất cả changeset pending, và cân nhắc tách pipeline hoặc điểm vào changelog khi cần kiểm soát chặt hơn.

### 6.3. Không nhầm nhãn của changeset với filter

Hai dòng sau mang vai trò khác nhau:

~~~yaml
labels: "billing,release_2026_11"
~~~

~~~text
--label-filter="billing AND release_2026_11"
~~~

Dòng YAML là **metadata của changeset**. Dòng CLI là **yêu cầu lựa chọn ở thời điểm thực thi**. Không nên đặt biểu thức filter phức tạp vào trường labels một cách tùy tiện nếu nhóm chưa thống nhất và kiểm chứng quy tắc parser, vì mục tiêu của labels thường là phân loại rõ ràng, còn quyền lựa chọn thuộc bên triển khai.

## 7. Các quy tắc quan trọng khi không có nhãn hoặc không có filter

Đây là nhóm lỗi tư duy dễ gây sự cố nhất.

### Trường hợp 1: Changeset có labels nhưng không truyền label filter

Ví dụ:

~~~yaml
labels: "experimental"
~~~

Không nên suy luận rằng changeset chắc chắn sẽ bị bỏ qua chỉ vì có chữ **experimental**. Trong cấu hình mặc định thông dụng, một changeset đã được gắn label vẫn có thể chạy khi **không có filter**. Vì vậy:

- Không dựa vào labels như một cơ chế “tắt mặc định” cho migration nguy hiểm.
- Áp dụng quy trình review và phê duyệt ngoài labels.
- Kiểm tra kết quả thực tế với phiên bản Liquibase đang triển khai.

### Trường hợp 2: Changeset không có labels nhưng có filter

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001"
      author: "db-team"
      changes:
        - createTable:
            tableName: application_version
            columns:
              - column:
                  name: id
                  type: bigint
~~~

Trong ngữ nghĩa Liquibase thông dụng, changeset không có labels vẫn có thể thực thi dù runtime truyền một label filter. Vì thế bộ lọc **billing** không đồng nghĩa rằng mọi changeset không phải billing đều được bỏ qua.

### Trường hợp 3: Changeset đã chạy trước đó

Nếu một changeset đã được ghi nhận trong DATABASECHANGELOG, đổi filter cho lần chạy tiếp theo **không tự động rollback** changeset ấy. Labels điều khiển tập thay đổi được xét ở thời điểm chạy, không đảo ngược trạng thái đã áp dụng.

### Trường hợp 4: Một changeset bị loại ở lần chạy này

Changeset không khớp filter thường không được ghi nhận là EXECUTED chỉ vì nó bị lọc. Nó có thể được xem xét lại trong những lần chạy sau, nếu filter và các điều kiện khác thay đổi.

Những nguyên tắc này giải thích vì sao labels giúp linh hoạt nhưng không thay thế kiểm soát triển khai.

## 8. Thiết kế quy ước đặt tên label

Các nhãn nên:

1. **Ngắn và có ý nghĩa:** billing, reporting, customer.
2. **Ổn định:** không đổi tên label chỉ vì đổi tên team nếu không có lý do nghiệp vụ.
3. **Không mơ hồ:** tránh nhãn chung chung như new, fix, test2.
4. **Dễ nhập trong CLI:** nên ưu tiên chữ thường, số, dấu gạch dưới hoặc quy ước đã được thử nghiệm.
5. **Phân biệt được chiều phân loại:** miền nghiệp vụ, nhóm tính năng, đợt phát hành hoặc tính chất thay đổi.
6. **Không trộn dữ liệu bí mật:** labels không được dùng để lưu password, token hoặc thông tin người dùng.

Có thể áp dụng một bảng quy ước:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Miền nghiệp vụ | billing, identity, catalog | Chủ sở hữu hoặc khu vực tác động |
| Nhóm tính năng | feature_invoice_v2 | Thay đổi phục vụ tính năng cụ thể |
| Mục đích kỹ thuật | reporting, performance | Thay đổi hiệu năng hoặc báo cáo |
| Dữ liệu | reference_data, backfill | Khởi tạo dữ liệu tham chiếu hoặc chuyển đổi |
| Đợt phát hành | release_2026_11 | Nhóm thay đổi dự kiến theo release |

Tránh đặt nhiều loại ngữ nghĩa vào cùng một tên mơ hồ như **prod_billing_final**. Môi trường thực thi nên được xác định bằng cấu hình kết nối và chính sách phát hành; label chỉ là một chiều metadata nếu tổ chức thật sự cần nó.

### 8.1. Quy ước nên có tài liệu vận hành

Một chính sách label có ích cần trả lời:

- Ai được tạo nhãn mới?
- Khi nào dùng label mới thay vì tái sử dụng nhãn hiện có?
- Có bắt buộc gắn nhãn cho mọi changeset không?
- Những thay đổi không có nhãn sẽ được xử lý thế nào?
- Label nào được dùng trong development, staging và production?
- Ai phê duyệt filter trong CI/CD?
- Làm cách nào kiểm tra danh sách changeset thật sự được chọn?

Thiếu những câu trả lời này, label dễ trở thành metadata chỉ mang tính trang trí.

## 9. Labels, contexts và DBMS phối hợp như thế nào?

Một changeset có thể được khai báo đồng thời:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "seed-customer-001"
      author: "seed-team"
      labels: "customer,reference_data"
      contextFilter: "dev"
      dbms: "postgresql"
      changes:
        - insert:
            tableName: customer_category
            columns:
              - column:
                  name: code
                  value: DEMO
              - column:
                  name: display_name
                  value: Demo customer
~~~

Cần hiểu ba chiều khác nhau:

- **dbms: postgresql** chỉ cho phép thay đổi này được xét khi kết nối dùng PostgreSQL.
- **contextFilter: dev** giới hạn ngữ cảnh theo cơ chế context của Liquibase.
- **labels: customer,reference_data** phân loại thay đổi để lọc theo nhãn khi runtime cung cấp label filter.

Ba điều kiện này không tự suy ra nhau. Nếu kết nối nhầm vào database PostgreSQL production nhưng truyền context và labels phù hợp, chúng có thể vẫn thỏa các điều kiện lọc. Do vậy, bảo vệ quan trọng nhất vẫn là **endpoint, quyền tài khoản, quy trình phê duyệt và kiểm chứng database đích**.

Ở những phiên bản Liquibase khác nhau, cú pháp **context** và **contextFilter** có thể tồn tại dưới dạng tên cũ/mới. Nên xác minh theo tài liệu và công cụ thực tế của dự án.

### 9.1. Nên dùng nhãn cho điều gì?

Một quy ước dễ vận hành:

- Dùng **contexts** cho cách chạy như dev, test, seed hoặc những ngữ cảnh vận hành mà đội quy định.
- Dùng **labels** cho miền nghiệp vụ, feature hoặc nhóm migration.
- Dùng **dbms** cho những SQL đặc thù DBMS.
- Dùng **preconditions** khi cần kiểm tra cấu trúc hay dữ liệu thật trước khi áp dụng.

Đây là gợi ý tổ chức, không có nghĩa Liquibase bắt buộc contexts chỉ dùng cho môi trường hoặc labels chỉ dùng cho tính năng.

## 10. Gắn label cho changeset thay đổi dữ liệu

Data migration thường rủi ro hơn DDL đơn giản vì có thể thay đổi hàng triệu dòng hoặc làm mất dữ liệu gốc. Labels giúp reviewer phân biệt một nhóm **backfill** hoặc **reference_data**, nhưng không khiến SQL tự động an toàn.

Ví dụ formatted SQL:

~~~sql
--liquibase formatted sql

--changeset billing-team:20261119-010 labels:billing,backfill dbms:postgresql
--comment: Populate payment status for rows created before status migration
UPDATE payment
SET status = 'PENDING'
WHERE status IS NULL;
~~~

Trước khi chạy phải trả lời:

- Bảng payment và cột status đã tồn tại chưa?
- UPDATE có giới hạn đúng tập dữ liệu cần sửa không?
- SQL có thể khóa bảng hoặc gây áp lực lên database không?
- Có nhiều hàng đã có trạng thái khác không?
- Có cần chia batch hoặc thực hiện ngoài giờ cao điểm không?
- Nếu rollback, có cách phân biệt dữ liệu vừa backfill với dữ liệu vốn có không?

Bộ lọc **billing AND backfill** có thể chọn nhóm này, nhưng không tự cung cấp khả năng rollback. Nếu dữ liệu thay đổi không thể đảo ngược an toàn, phải có phương án khôi phục hoặc forward fix được xác định trước.

## 11. Labels trong chuỗi thay đổi schema an toàn

Xét một tính năng bổ sung trạng thái hóa đơn theo mô hình **expand–migrate–contract**:

1. **Expand:** thêm cột mới tương thích ngược.
2. **Migrate:** backfill dữ liệu cũ.
3. **Switch:** ứng dụng bắt đầu sử dụng cột mới, theo quy trình phát hành phù hợp.
4. **Contract:** bỏ cấu trúc cũ sau khi xác nhận không còn phụ thuộc.

Có thể gắn nhãn:

| Changeset | Labels | Mục đích |
|---|---|---|
| add-invoice-status | billing,invoice_v2,expand | Thêm cột mới |
| backfill-invoice-status | billing,invoice_v2,backfill | Chuyển dữ liệu |
| add-invoice-status-constraint | billing,invoice_v2,validate | Thêm ràng buộc khi dữ liệu sẵn sàng |
| drop-legacy-invoice-state | billing,invoice_v2,contract | Gỡ cấu trúc cũ |

Mục tiêu là dễ nhìn thấy loại thay đổi trong code review và báo cáo phát hành. Tuy nhiên, **labels không tự tạo thứ tự rollout an toàn**:

- Nếu một thay đổi có phụ thuộc vào bước trước đó, người triển khai phải bảo đảm thứ tự changeset và trạng thái schema.
- Nếu filter chỉ chọn **backfill** mà bỏ **expand**, migration có thể thất bại.
- Nếu filter chọn **contract** quá sớm, ứng dụng cũ có thể lỗi.
- Nếu changeset không có filter và các label thông thường vẫn chạy, một bước contract nhạy cảm có thể được chọn ngoài ý muốn.

Với các bước rủi ro cao, nên có **điểm kiểm soát phát hành rõ ràng**, precondition và/hoặc tách changelog/pipeline để buộc review riêng. Không dùng label như “nút khóa” duy nhất.

## 12. Chạy label filter từ Liquibase CLI

Ví dụ dùng một changelog đã cấu hình kết nối PostgreSQL:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --label-filter="billing" \
  status --verbose
~~~

Trước khi thực thi, nên sinh SQL dự kiến:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --label-filter="billing AND release_2026_11" \
  update-sql
~~~

Sau khi xác nhận kết quả:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --label-filter="billing AND release_2026_11" \
  update
~~~

Trong các ví dụ, JDBC URL, username, password và driver được giả định lấy từ cấu hình bảo mật của môi trường. Không nên ghi secret trực tiếp trong dòng lệnh nếu có nguy cơ bị lưu lại trong shell history, process list hoặc CI log.

**Lưu ý phiên bản:** Tên tham số dòng lệnh thường được sử dụng trong Liquibase hiện đại là **--label-filter**; ở hệ thống cũ có thể gặp tên hoặc cách đặt tham số khác. Cú pháp cờ và thứ tự tham số cần được kiểm tra với **liquibase --help** của phiên bản đang chạy.

### 12.1. Khi filter chứa toán tử logic

Nên đặt toàn bộ biểu thức trong dấu nháy thích hợp với shell:

~~~bash
--label-filter="(billing OR reporting) AND release_2026_11"
~~~

Với bash, PowerShell hoặc Windows CMD, quy tắc xử lý dấu nháy có thể khác nhau. Tránh để shell tách biểu thức thành nhiều đối số. Nếu pipeline hỗ trợ truyền filter bằng biến cấu hình an toàn, có thể giảm lỗi escaping, nhưng vẫn phải kiểm tra giá trị cuối cùng Liquibase nhận được.

### 12.2. Cần kiểm tra trước mọi lần update

Một trình tự vận hành gợi ý:

1. Xác nhận URL, database, schema và user kết nối.
2. Xác nhận đúng artifact changelog và phiên bản Liquibase.
3. Chạy **validate**.
4. Chạy **status --verbose** với chính label filter dự định sử dụng.
5. Chạy **update-sql** với cùng filter để review SQL.
6. Đối chiếu tập changeset được chọn với danh sách thay đổi đã được phê duyệt.
7. Chỉ sau đó mới chạy **update**.
8. Xác minh DATABASECHANGELOG và schema/dữ liệu sau khi hoàn tất.

Một lệnh status thành công chưa chứng minh migration an toàn về hiệu năng, khóa bảng hoặc dữ liệu. SQL thực thi cần được đánh giá độc lập.

## 13. Cấu hình labels khi dùng Spring Boot

Spring Boot cung cấp cấu hình Liquibase riêng; thông thường có thể đặt **spring.liquibase.label-filter** để truyền filter vào quá trình Liquibase khởi chạy.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-from-secret-manager>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    label-filter: "billing AND release_2026_11"
~~~

Ví dụ minh họa cách tổ chức cấu hình, không chứa password thật. Cần xác nhận Spring Boot và Liquibase phiên bản dự án có thuộc tính trên với đúng ngữ nghĩa.

Nếu ứng dụng có **Spring profiles**, có thể thay đổi filter theo môi trường:

~~~yaml
# application-staging.yml
spring:
  liquibase:
    label-filter: "billing AND release_2026_11"
~~~

Nhưng phải thận trọng:

- Filter không thay đổi datasource hay endpoint đích.
- Profile sai có thể gây migration ngoài dự kiến.
- Không nên biến mọi lần khởi động ứng dụng thành cơ hội chạy một tập migration nhạy cảm thiếu phê duyệt.
- Nếu cần tài khoản có quyền DDL, cân nhắc DataSource riêng cho Liquibase hoặc bước migration độc lập trong pipeline.
- Nếu bỏ cấu hình label-filter trong một môi trường, tập changeset có thể rộng hơn dự kiến.

Khi có nhiều instance ứng dụng khởi động song song, Liquibase có cơ chế lock metadata, nhưng vẫn cần phân tích kiến trúc triển khai để tránh các tác động vận hành và phụ thuộc không mong muốn.

## 14. Labels trong CI/CD và quản trị phát hành

Một pipeline triển khai có thể nhận cấu hình:

~~~text
TARGET_ENV=staging
DATABASE_ENDPOINT=db-staging.internal
LIQUIBASE_LABEL_FILTER=(billing OR reporting) AND release_2026_11
CHANGELOG_ARTIFACT=orders-service-2026.11
~~~

Đây là ví dụ metadata pipeline, không phải secret hoặc định dạng cấu hình Liquibase bắt buộc. Pipeline cần thực hiện các bước:

1. Xác định artifact changelog đã được review và bất biến.
2. Lấy endpoint và credential từ cấu hình môi trường/secret store.
3. Hiển thị môi trường đích và label filter dự kiến trong báo cáo triển khai.
4. Chạy kiểm tra trạng thái, validation và sinh SQL dự kiến.
5. Kiểm tra danh sách changeset được chọn, bao gồm **changeset không có labels**.
6. Yêu cầu phê duyệt phù hợp với mức rủi ro.
7. Chạy update với đúng artifact và đúng filter đã được kiểm tra.
8. Ghi lại deployment ID, kết quả và thông tin phục vụ điều tra.

### 14.1. Không dùng label như một hàng rào bảo mật

Giả sử một nhóm chỉ đặt nhãn **production** cho những changeset cần chạy production rồi dựa vào filter để ngăn môi trường development chạy chúng. Cách làm này yếu nếu pipeline có thể bỏ quên filter, thay đổi cách xử lý filter, hoặc có changeset không có nhãn.

Một thiết kế an toàn hơn cần kết hợp:

- Tài khoản kết nối được giới hạn quyền theo môi trường.
- Quyền phê duyệt deployment production rõ ràng.
- Đường dẫn và artifact changelog được review.
- Kiểm tra trạng thái database đích trước update.
- Các ràng buộc độc lập cho thao tác nguy hiểm.
- Kịch bản rollback hoặc forward fix và khả năng khôi phục dữ liệu.

Labels hữu ích để **định tuyến tập thay đổi**, không để thay thế các lớp kiểm soát đó.

### 14.2. Giữ cùng changelog giữa nhiều môi trường

Khi phát hành theo chuỗi development → test → staging → production, lý tưởng là dùng cùng artifact changelog đã kiểm chứng. Mỗi môi trường có kết nối riêng, lịch sử DATABASECHANGELOG riêng và bộ filter được phê duyệt riêng khi cần.

Không sửa nội dung changeset cũ ở mỗi môi trường chỉ để phù hợp label. Việc sửa SQL sau khi changeset đã chạy có thể gây checksum mismatch và làm lệch lịch sử. Nếu có thay đổi mới, nên thêm changeset mới, hoặc sử dụng cơ chế được hỗ trợ và kiểm chứng rõ ràng.

## 15. Labels ảnh hưởng thế nào tới DATABASECHANGELOG?

Liquibase ghi lại những changeset đã được xử lý trong **DATABASECHANGELOG**. Tùy DBMS, tên schema metadata và phiên bản Liquibase, bảng có thể có các cột như:

- **ID**, **AUTHOR**, **FILENAME**: định danh changeset.
- **DATEEXECUTED**, **ORDEREXECUTED**: thời điểm và thứ tự ghi nhận.
- **EXECTYPE**: kiểu xử lý, ví dụ EXECUTED, RERAN hoặc MARK_RAN.
- **MD5SUM**: checksum được lưu.
- **LABELS**, **CONTEXTS**: metadata được ghi nhận trong lịch sử.
- **DEPLOYMENT_ID**: định danh nhóm thao tác triển khai theo cách Liquibase quản lý.

Ví dụ truy vấn PostgreSQL hoặc DBMS hỗ trợ cú pháp tương ứng:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    LABELS,
    CONTEXTS,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Nếu bảng được đặt trong schema riêng, thêm schema qualifier thích hợp, ví dụ **liquibase_meta.DATABASECHANGELOG**.

Các điểm cần nhớ:

- Một changeset bị filter loại bỏ không tự trở thành EXECUTED chỉ do lần update đó được chạy.
- Khi thay đổi filter, Liquibase có thể xét lại các changeset còn pending.
- Một changeset đã chạy không tự rollback khi filter không còn khớp.
- Metadata LABELS trong lịch sử giúp điều tra, nhưng vẫn cần đối chiếu với artifact changelog và cấu hình từng lần chạy.

**Không chỉnh sửa DATABASECHANGELOG thủ công** chỉ để làm lịch sử “khớp” với nhãn mong muốn. Đây là bảng quản lý trạng thái của Liquibase, không phải tệp cấu hình filter.

## 16. Labels và checksum: những điều dễ hiểu nhầm

Labels là metadata, nhưng thay đổi phần metadata hay nội dung changeset sau khi triển khai cần được đánh giá cẩn thận. Cơ chế checksum có quy tắc riêng tùy định dạng changelog và phiên bản Liquibase.

Không nên suy luận:

- “Đổi label chắc chắn không ảnh hưởng gì tới lịch sử.”
- “Đổi label tức là changeset cũ phải chạy lại.”
- “Thay filter là đủ để sửa trạng thái schema.”
- “Đổi tên file và giữ nguyên SQL thì Liquibase luôn nhận ra changeset cũ.”

Về vận hành, nên thực hiện như sau:

1. Xác định changeset đã chạy ở những database nào.
2. So sánh artifact đã triển khai với changelog hiện tại.
3. Kiểm tra ID, AUTHOR, FILENAME/logicalFilePath và checksum.
4. Xem tác động của filter mới trên tập changeset pending.
5. Nếu cần sửa schema/dữ liệu, ưu tiên thêm changeset mới.
6. Kiểm chứng trên bản sao database đại diện trước production.

**runOnChange** và **runAlways** là cơ chế chạy lại chuyên biệt của Liquibase, không phải chức năng của labels. Không bật hai thuộc tính này chỉ để “giải quyết” việc filter không chọn đúng tập thay đổi.

## 17. Lỗi thường gặp khi gắn và lọc labels

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Changeset có label nhưng chạy dù không truyền filter | Label không nhất thiết bắt buộc phải bật filter mới chạy | Xác định ngữ nghĩa runtime, dùng kiểm soát rollout phù hợp |
| Filter billing nhưng một changeset khác vẫn chạy | Changeset đó không có labels hoặc thỏa điều kiện khác theo parser | Kiểm tra metadata toàn bộ changeset pending |
| Filter không chọn changeset mong đợi | Sai chính tả nhãn, biểu thức hoặc escaping ở CLI | Kiểm tra labels thực tế và filter mà Liquibase nhận được |
| Label filter quá rộng | Dùng OR khi muốn AND hoặc thiếu dấu ngoặc | Viết lại biểu thức, review kết quả status/update-sql |
| Chạy trên sai database | Cấu hình JDBC hoặc DataSource sai | Xác minh endpoint, database, schema và user |
| Changeset đã chạy không thay đổi khi filter đổi | DATABASECHANGELOG đã ghi nhận changeset | Không kỳ vọng filter gây rollback hoặc rerun |
| Changeset pending bị thiếu khỏi changelog | Tệp chưa được include hoặc includeAll không quét đến | Kiểm tra changelog gốc, đường dẫn và loại tệp |
| Changeset chạy lại ngoài ý muốn | runAlways/runOnChange hoặc đổi đường dẫn/định danh | Xem metadata và FILENAME lịch sử |
| Validate báo checksum mismatch | Nội dung changeset đã chạy bị sửa | So sánh artifact cũ, ưu tiên changeset mới |
| SQL có nhãn phù hợp nhưng vẫn thất bại | Precondition, quyền, schema hoặc SQL không hợp lệ | Phân tích lỗi database và SQL dự kiến |
| Staging và production chọn tập khác nhau | Chênh lệch filter, artifact hoặc lịch sử | Ghi rõ artifact/filter và so sánh pending theo môi trường |
| Có LABELS trong DATABASECHANGELOG nhưng không nhớ filter nào đã dùng | Không lưu báo cáo triển khai | Lưu log CI/CD và metadata deployment có kiểm soát |

Khi điều tra, nên kiểm tra theo thứ tự: **database đích → phiên bản changelog → danh sách changeset thực sự được nạp → label/context filter → trạng thái lịch sử → SQL/precondition**. Cách này tránh nhầm lỗi cấu hình kết nối với lỗi lọc nhãn.

## 18. Bài thực hành: gắn nhãn và kiểm chứng ba nhóm thay đổi

**Bối cảnh:** Dịch vụ đơn hàng dùng PostgreSQL và Liquibase, đang chuẩn bị ba thay đổi:

- Tạo bảng cho tính năng hóa đơn mới.
- Tạo view báo cáo.
- Thêm index hỗ trợ tra cứu khách hàng.

Mục tiêu là gắn labels nhất quán và kiểm tra filter trước khi chạy.

### Bước 1: Tạo changelog minh họa

Ví dụ một changelog YAML với ba changeset; giả định các bảng nguồn tương ứng đã tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-001"
      author: "training-team"
      labels: "billing,release_2026_11"
      changes:
        - createTable:
            tableName: training_invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            tableName: training_invoice

  - changeSet:
      id: "practice-002"
      author: "training-team"
      labels: "reporting,release_2026_11"
      changes:
        - createView:
            viewName: training_customer_count
            selectQuery: "SELECT COUNT(*) AS total FROM customer"
      rollback:
        - dropView:
            viewName: training_customer_count

  - changeSet:
      id: "practice-003"
      author: "training-team"
      labels: "customer,performance"
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email_training
            columns:
              - column:
                  name: email
      rollback:
        - dropIndex:
            tableName: customer
            indexName: idx_customer_email_training
~~~

Đây là ví dụ học tập. Cần kiểm tra bảng **customer** và cột **email** có tồn tại, bảng **training_invoice** chưa tồn tại và tên index chưa trùng. Trước khi chạy ở database thật, nên dùng một database thử nghiệm biệt lập và validate với phiên bản Liquibase phù hợp.

### Bước 2: Đặt các filter thử nghiệm

Hãy kiểm tra ít nhất ba filter:

~~~text
billing
~~~

~~~text
reporting OR customer
~~~

~~~text
(billing OR reporting) AND release_2026_11
~~~

Dự đoán nhóm thay đổi được chọn theo ý định biểu thức, rồi so sánh với đầu ra **status --verbose** và **update-sql**. Không thực thi update trước khi kết quả khớp với thiết kế.

### Bước 3: Thêm changeset không có labels

Thêm một changeset thử nghiệm nhỏ không khai báo labels. Chạy lại status hoặc update-sql với filter **billing**. Quan sát xem nó có được chọn hay không. Mục đích là kiểm nghiệm trực tiếp hành vi của Liquibase đối với changeset không gắn nhãn, thay vì chỉ ghi nhớ một quy tắc mà không thử.

### Bước 4: Thực thi trên database development

Sau khi review:

1. Chọn filter đã được xác nhận.
2. Chạy update trên database thử nghiệm.
3. Kiểm tra bảng/view/index nào được tạo.
4. Truy vấn DATABASECHANGELOG để ghi nhận ID, LABELS, EXECTYPE.
5. Chạy cùng lệnh lần thứ hai; quan sát changeset đã chạy không tự chạy lại theo mặc định.
6. Đổi filter để chọn nhóm chưa chạy; xem lại status trước khi update.
7. Khi thử rollback, chỉ làm trên database thử nghiệm và kiểm tra các đối tượng phụ thuộc.

Kết quả mong đợi là bạn nắm được labels ảnh hưởng **tập changeset mới được chọn**, nhưng không tự thay đổi lịch sử của những changeset đã chạy.

## 19. Các câu hỏi tự kiểm tra

**Câu 1. Labels được khai báo trong changelog hay CLI?**

Labels được gắn vào changeset trong changelog. **Label filter** thường được truyền ở thời điểm chạy thông qua CLI, Spring Boot hoặc pipeline.

**Câu 2. Một changeset có label experimental có chắc chắn bị bỏ qua khi chạy update mà không có label filter không?**

Không. Với cách hoạt động thông dụng, labels thông thường không tự động khóa changeset khi không có filter. Cần xác minh hành vi của phiên bản đang dùng và áp dụng kiểm soát phát hành phù hợp.

**Câu 3. Chạy với filter billing có chắc chắn không chạy changeset không gắn nhãn không?**

Không. Changeset không có labels thường vẫn có thể chạy. Vì vậy phải xem danh sách changeset pending thực tế.

**Câu 4. Label có thể chọn database production thay cho JDBC URL không?**

Không. Database đích được quyết định bởi kết nối. Label chỉ ảnh hưởng quá trình lựa chọn changeset trên kết nối đó.

**Câu 5. Labels và database tag có giống nhau không?**

Không. Labels là metadata phân loại và lọc changeset; database tag là mốc lịch sử được dùng trong các quy trình như rollback theo tag.

**Câu 6. Sau khi changeset đã chạy, bỏ nhãn khỏi filter có tự động rollback không?**

Không. Những thay đổi đã áp dụng vẫn tồn tại, trừ khi có thao tác migration hoặc rollback phù hợp được thực hiện riêng.

**Câu 7. Có thể dùng labels để bảo đảm quy trình expand–migrate–contract luôn an toàn không?**

Không. Labels không thay thế thứ tự phụ thuộc, compatibility giữa ứng dụng và schema, precondition, kiểm tra dữ liệu hay phê duyệt phát hành.

**Câu 8. Tại sao phải chạy update-sql với đúng filter trước update?**

Vì cùng một changelog có thể chọn các tập changeset khác nhau theo filter và lịch sử của từng database. Review SQL dự kiến giúp phát hiện thay đổi ngoài mong đợi trước khi tác động database.

## 20. Checklist áp dụng labels trong dự án thực tế

- [ ] Mỗi nhãn có ý nghĩa và phạm vi được đội phát triển thống nhất.
- [ ] Changelog dùng cú pháp labels phù hợp định dạng và phiên bản Liquibase.
- [ ] Các changeset không có labels được kiểm tra, không mặc nhiên coi là bị loại.
- [ ] Cách xử lý khi không có label filter đã được kiểm chứng.
- [ ] Biểu thức filter dùng AND/OR/NOT và dấu ngoặc có chủ đích.
- [ ] Filter được ghi lại cùng artifact và môi trường triển khai.
- [ ] Labels được phân biệt với contexts, dbms và database tag.
- [ ] Không dùng label thay thế cấu hình JDBC hoặc cơ chế phân quyền.
- [ ] Những thay đổi nhạy cảm có precondition và lớp kiểm soát độc lập phù hợp.
- [ ] Đã chạy validate, status --verbose và update-sql với filter thực tế.
- [ ] Đã đối chiếu tất cả changeset pending, kể cả changeset không gắn nhãn.
- [ ] Đã kiểm tra SQL, ảnh hưởng dữ liệu, rollback và quan hệ phụ thuộc.
- [ ] Không sửa changeset đã triển khai tùy tiện để đổi nhãn hoặc né checksum.
- [ ] Khi triển khai nhiều môi trường, endpoint, quyền, filter và artifact đều được xác nhận.
- [ ] Có cách truy vết kết quả trong DATABASECHANGELOG và log CI/CD.

**Kết luận:** Labels giúp mô tả và lựa chọn nhóm changeset một cách linh hoạt, nhất là khi một changelog phục vụ nhiều tính năng hoặc nhiều đợt phát hành. Muốn sử dụng an toàn, phải hiểu sự khác biệt giữa metadata **labels** và tham số runtime **label filter**, biết rằng changeset không có nhãn hay không có filter có thể tạo hành vi bất ngờ, và luôn xác minh tập SQL sẽ được áp dụng trên đúng database. Kết hợp labels với lịch sử DATABASECHANGELOG, precondition, kiểm soát phát hành và kiểm thử migration sẽ tạo nên quy trình thay đổi schema và dữ liệu có thể giải thích, kiểm chứng và vận hành.

