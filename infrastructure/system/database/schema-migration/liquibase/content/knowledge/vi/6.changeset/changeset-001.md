# Cấu trúc changeset và cách đặt id, author

Trong chương **Changeset** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, bài học này tập trung vào đơn vị thay đổi cơ bản của Liquibase: một **changeset**. Nắm vững cấu trúc changeset và cách đặt **id**, **author** là điều kiện để quản lý thay đổi schema và dữ liệu bằng changelog, kiểm tra migration trước khi chạy, theo dõi checksum và lịch sử triển khai, viết rollback, cũng như đưa cùng một bộ migration qua Spring Boot hoặc CI/CD ở nhiều môi trường.

Một changeset mô tả một bước thay đổi được Liquibase quản lý. Khi chạy migration, Liquibase kiểm tra changeset đó đã được ghi nhận trên database đích hay chưa, sau đó quyết định áp dụng hoặc xử lý theo các thuộc tính đã cấu hình. Vì vậy, id và author không chỉ là thông tin để đọc mã nguồn; chúng là thành phần của **định danh lịch sử**.

## 1. Từ changelog đến changeset

Ba khái niệm cần phân biệt:

- **Changelog** là tài liệu khai báo danh sách changeset, hoặc khai báo các tệp changelog con qua include/includeAll.
- **Changeset** là một đơn vị thay đổi có định danh. Nó chứa một hoặc nhiều change, các điều kiện áp dụng và có thể chứa rollback tương ứng.
- **Change** là thao tác cụ thể như createTable, addColumn, createIndex, insert, update, sql.

Sơ đồ quan hệ:

~~~text
db.changelog-master.yaml        (changelog gốc)
├── include changes/001.yaml   (changelog con)
│   ├── changeSet A
│   │   ├── id + author
│   │   ├── changes
│   │   └── rollback
│   └── changeSet B
└── include changes/002.yaml
    └── changeSet C
~~~

Liquibase đọc changelog theo thứ tự được xác định bởi nội dung và các chỉ thị include. Trật tự thực thi phụ thuộc vị trí trong changelog và cách nạp tệp, **không phải** vào việc sắp xếp id theo bảng chữ cái hay giá trị số.

Một changeset nên thể hiện một thay đổi có mục đích rõ ràng, có thể kiểm tra tác động và có hướng rollback hoặc khôi phục thích hợp. Không nhất thiết mỗi câu lệnh SQL phải thành một changeset riêng; nhiều thao tác gắn bó chặt chẽ có thể thuộc cùng một changeset nếu phù hợp với khả năng giao dịch của DBMS và chiến lược khôi phục.

## 2. Cấu trúc changeset tối thiểu bằng YAML

Ví dụ tạo bảng khách hàng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - createTable:
            tableName: customer
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
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

Cấu trúc gồm bốn phần:

1. **databaseChangeLog** là phần tử gốc của tài liệu YAML.
2. **changeSet** mở một đơn vị migration mới.
3. **id** và **author** là hai trường bắt buộc để Liquibase xác định changeset cùng với đường dẫn changelog.
4. **changes** chứa danh sách thao tác; **rollback** mô tả hành động đảo ngược khi cần.

Tất cả thuộc tính nằm trong cùng đối tượng changeSet; YAML nhạy với khoảng trắng và mức thụt lề. Đặt changes hoặc rollback lệch cấp có thể gây lỗi parse hoặc tạo cấu trúc khác dự kiến.

Trong ví dụ, rollback xóa toàn bộ bảng để minh họa cú pháp. Đó là hành động có thể làm mất dữ liệu; trên hệ thống đã phát sinh dữ liệu thật, phải đánh giá kỹ rủi ro và sử dụng chiến lược khôi phục phù hợp. Không xem một đoạn rollback có cú pháp hợp lệ là bằng chứng có thể rollback an toàn.

### Các trường quan trọng

| Trường | Vai trò | Ghi chú |
|---|---|---|
| id | Định danh do người viết đặt | Bắt buộc; nên ổn định và duy nhất trong phạm vi tệp changelog |
| author | Tác giả hoặc định danh nhóm | Bắt buộc; là một phần của khóa nhận diện |
| changes | Các thao tác triển khai | Thường gồm một hoặc nhiều change type |
| rollback | Thao tác khôi phục | Có thể được định nghĩa tường minh; một số change type có hỗ trợ rollback tự động nhưng không nên mặc định mọi thao tác đều có |
| comment | Giải thích mục đích thay đổi | Hữu ích khi review và điều tra lịch sử |
| preConditions | Điều kiện được kiểm tra trước khi chạy | Có thể dừng, cảnh báo, bỏ qua hoặc đánh dấu theo cấu hình phù hợp |
| contextFilter | Chọn changeset theo context | Cần phối hợp với context của lệnh triển khai |
| labels | Gắn nhãn để chọn phạm vi chạy | Không phải cơ chế phân quyền |
| dbms | Chọn loại hệ quản trị cơ sở dữ liệu | Tránh chạy SQL đặc thù trên DBMS không tương thích |
| runInTransaction | Điều khiển giao dịch của changeset | Hành vi thực tế phụ thuộc khả năng DDL transaction của DBMS |
| runOnChange | Cho phép chạy lại khi nội dung thay đổi | Phù hợp với một số đối tượng có thể tái tạo, không nên dùng tùy tiện cho migration dữ liệu |
| runAlways | Chạy lại ở mỗi lần Liquibase xử lý changelog | Chỉ dùng cho trường hợp được thiết kế để lặp an toàn |

Thuộc tính được hỗ trợ và tên biểu diễn có thể khác giữa các phiên bản hoặc định dạng changelog. Khi đưa ví dụ vào dự án cụ thể, dùng tài liệu và lệnh validate của phiên bản Liquibase đang chạy để kiểm chứng.

## 3. Khóa định danh thực tế: id + author + filename

Liquibase xác định một changeset bằng bộ ba:

~~~text
(ID, AUTHOR, FILENAME)
~~~

Trong đó:

- **ID** lấy từ thuộc tính id của changeset.
- **AUTHOR** lấy từ thuộc tính author.
- **FILENAME** là đường dẫn changelog mà Liquibase dùng để ghi nhận changeset, hoặc đường dẫn logic được cấu hình nếu dùng logicalFilePath.

Ví dụ, hai changeset sau có id và author giống nhau:

~~~text
changes/customer/001.yaml  | id=add-phone | author=team-db
changes/order/001.yaml     | id=add-phone | author=team-db
~~~

Nếu FILENAME khác nhau, đây là hai định danh lịch sử khác nhau. Nhưng khi cùng một tệp chứa hai changeset có **cùng id và cùng author**, chúng xung đột định danh và cần sửa trước khi triển khai.

Bảng DATABASECHANGELOG ghi nhận khóa này cùng thông tin như DATEEXECUTED, EXECTYPE và MD5SUM. Có thể tra cứu một changeset bằng SQL:

~~~sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
WHERE ID = '20261119-001-create-customer'
  AND AUTHOR = 'team-db';
~~~

Truy vấn trên có thể trả nhiều dòng nếu id và author được sử dụng ở nhiều tệp. Khi đối chiếu một changeset cụ thể, phải kiểm tra cả FILENAME và, khi cần, thêm điều kiện FILENAME đúng với giá trị được Liquibase lưu. Không chỉ nhìn id để kết luận thay đổi đã chạy.

Một changeset đã được ghi nhận thông thường sẽ không chạy lại chỉ vì lệnh update được gọi lần nữa. Liquibase sẽ đối chiếu bộ ba trên và xử lý các ngoại lệ theo thuộc tính như runOnChange hoặc runAlways.

### Vì sao đường dẫn changelog quan trọng?

Giả sử một changeset được triển khai khi nằm trong:

~~~text
db/changelog/changes/2026/customer.yaml
~~~

Sau đó bạn chuyển tệp sang:

~~~text
db/changelog/customer.yaml
~~~

Nếu Liquibase nhìn thấy FILENAME khác, cùng id và author có thể bị coi là changeset mới và được chọn chạy thêm một lần. Với các thao tác như createTable hoặc addColumn, điều này có thể dẫn đến lỗi đối tượng đã tồn tại hoặc thay đổi dữ liệu ngoài dự kiến.

Khi cần tái cấu trúc thư mục sau khi đã triển khai, phải kiểm soát đường dẫn định danh. Liquibase hỗ trợ cơ chế **logicalFilePath** để tách tên logic dùng trong lịch sử khỏi vị trí vật lý của tệp. Hãy cấu hình đúng phạm vi và cú pháp mà phiên bản Liquibase đang dùng hỗ trợ, rồi so sánh với FILENAME đã lưu trong DATABASECHANGELOG trước khi triển khai lại.

Quy tắc thực tế: **giữ ổn định bộ ba id–author–filename sau khi phát hành**. Việc đổi tên file, đổi author hoặc sửa id sau khi đã chạy đều phải được xem là thay đổi định danh, không phải thao tác dọn mã nguồn vô hại.

## 4. Cách đặt id: duy nhất, ổn định và dễ truy vết

Liquibase không tự yêu cầu id phải là số tăng dần hay UUID. Về mặt ý nghĩa, id là chuỗi do nhóm phát triển tự quy ước. Một quy ước tốt cần đồng thời đạt bốn mục tiêu:

1. **Duy nhất** trong phạm vi changelog có thể xung đột, nhất là trong cùng một tệp.
2. **Bất biến** sau khi đã được triển khai ở bất kỳ môi trường nào.
3. **Dễ đọc và dễ tìm** khi kiểm tra log, PR hoặc DATABASECHANGELOG.
4. **Dễ sinh song song** trên nhiều branch mà ít va chạm.

Có một số chiến lược thường gặp:

| Cách đặt | Ví dụ | Ưu điểm | Cần lưu ý |
|---|---|---|---|
| Số tuần tự | 001, 002, 003 | Ngắn, dễ nhìn trong tệp nhỏ | Dễ trùng giữa các nhánh và dễ bị đổi số khi merge |
| Ngày/giờ + thứ tự | 20261119-001 | Dễ truy vết theo đợt tạo | Vẫn có thể trùng khi nhiều người tạo cùng thời điểm |
| Mã ticket + hành động | DB-184-add-phone | Gắn với yêu cầu nghiệp vụ | Cần thống nhất mã ticket và không tái sử dụng |
| Ngày/giờ + tên ý nghĩa | 20261119-001-add-phone | Dễ tìm trong log, giảm nhầm lẫn | Tên có thể dài; phải giữ nguyên sau triển khai |
| UUID | 8f42... | Khả năng trùng rất thấp | Khó đọc khi điều tra thủ công |

Không có một quy ước duy nhất phù hợp mọi dự án. Với nhóm có nhiều branch phát triển đồng thời, một lựa chọn thực tế là:

~~~text
YYYYMMDD-NNN-action-target
20261119-001-create-customer
20261119-002-add-index-customer-email
20261120-001-add-customer-phone
~~~

Trong dự án có ticket, có thể gắn thêm mã yêu cầu:

~~~text
20261119-DB184-add-customer-phone
~~~

Các chuỗi này là **định danh bất biến**, không phải dữ liệu để sắp xếp. Liquibase chạy theo thứ tự changelog, vì vậy thay đổi hậu tố id từ 001 thành 002 sẽ không làm changeset được chạy sớm hoặc muộn hơn; nó có thể tạo một định danh mới nếu đã có lịch sử.

### Những nguyên tắc tránh trùng id

- Phân công quy ước tạo id trong tài liệu nhóm và áp dụng trong code review.
- Kiểm tra id + author trong chính tệp đang chỉnh sửa, nhất là khi hai branch cùng bổ sung changeset vào một tệp chung.
- Giữ changeset ở các tệp được quản lý ổn định; tránh gom, đổi tên hoặc đánh số lại các changeset đã phát hành.
- Dùng mô tả ngắn gọn về hành động và đối tượng, ví dụ add-customer-phone thay vì fix hoặc update.
- Không tạo id chứa mật khẩu, dữ liệu khách hàng, token hay thông tin bí mật.
- Giữ nguyên chữ hoa/thường và ký tự của id sau khi triển khai. Đừng coi hai biến thể khác chữ hoa là chắc chắn tương đương.
- Không dựa vào việc cùng id ở hai file khác nhau để né quy ước đặt tên; hãy ưu tiên định danh duy nhất, dễ tra cứu trong toàn bộ module.

### Tại sao nên đặt id trong dấu nháy YAML?

Ví dụ:

~~~yaml
id: "001"
id: "20261119-001"
id: "DB-184-add-phone"
~~~

Dùng dấu nháy nhất quán giúp thể hiện rõ id là chuỗi, đặc biệt với các giá trị chỉ gồm chữ số, bắt đầu bằng số 0, hoặc có dạng mà YAML parser có thể diễn giải thành kiểu khác. Nhờ đó, id ghi trong source, log và DATABASECHANGELOG có ý nghĩa nhất quán.

Tránh thay đổi id chỉ để làm đẹp cách viết sau khi đã triển khai. Ví dụ, nếu một migration được ghi nhận bằng id 001, không sửa thành 1 dù hai chuỗi có vẻ chỉ khác cách hiển thị.

## 5. Cách đặt author: người viết hay nhóm sở hữu?

Thuộc tính author xác định ai hoặc nhóm nào chịu trách nhiệm tạo changeset. Liquibase dùng giá trị này trong khóa định danh, nhưng author **không** phải tài khoản đăng nhập database và không quyết định quyền thực thi.

Hai cách quản lý author thông dụng:

**Theo cá nhân:** mỗi thành viên dùng một định danh ổn định, ví dụ minh.nguyen. Cách này cho phép tìm thay đổi theo người tạo, nhưng tổ chức phải giải quyết việc đổi tên tài khoản, chuyển nhóm hoặc nghỉ việc.

**Theo nhóm:** dùng một định danh ổn định như team-db hoặc platform. Cách này phù hợp changelog dùng chung, bền vững trước thay đổi nhân sự; thông tin người mở PR và người review có thể được lưu trong Git để truy vết chi tiết.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-DB184-add-customer-phone"
      author: "team-db"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
~~~

Một số quy tắc nên thống nhất:

- Chọn một chuẩn author ổn định từ đầu dự án; tránh lúc dùng tên riêng, lúc dùng email, lúc dùng tên nhóm mà không có quy ước.
- Không thay author chỉ vì người khác tiếp quản bảo trì.
- Không gán author thành tên môi trường như dev hoặc prod; môi trường được điều khiển qua cấu hình chạy và bộ lọc.
- Không dùng author để phân biệt hai changeset đáng ra phải có id khác nhau trong cùng tệp.
- Nếu cần biết ai triển khai, hãy dùng audit/log CI/CD, tài khoản migration và lịch sử phát hành; author chủ yếu ghi nhận người hoặc nhóm tạo migration.

Ví dụ, nếu changeset ban đầu có author là team-db và đã chạy, sau đó sửa thành platform, Liquibase có thể xem là một changeset khác dù changes và id giữ nguyên. Vì vậy, việc chuẩn hóa tên author phải thực hiện **trước** khi triển khai lần đầu; với dữ liệu lịch sử cũ cần một kế hoạch tương thích có kiểm soát.

## 6. Một changelog có nhiều changeset

Xét ví dụ gồm ba bước để tạo bảng, thêm chỉ mục và thêm dữ liệu tham chiếu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-country"
      author: "team-db"
      comment: "Tạo bảng danh mục quốc gia"
      changes:
        - createTable:
            tableName: country
            columns:
              - column:
                  name: code
                  type: VARCHAR(2)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: country

  - changeSet:
      id: "20261119-002-unique-country-name"
      author: "team-db"
      changes:
        - addUniqueConstraint:
            tableName: country
            columnNames: name
            constraintName: uq_country_name
      rollback:
        - dropUniqueConstraint:
            tableName: country
            constraintName: uq_country_name

  - changeSet:
      id: "20261119-003-insert-country-vn"
      author: "team-db"
      changes:
        - insert:
            tableName: country
            columns:
              - column:
                  name: code
                  value: "VN"
              - column:
                  name: name
                  value: "Viet Nam"
      rollback:
        - delete:
            tableName: country
            where: "code = 'VN'"
~~~

Cần chú ý:

- Cả ba changeset nằm trong một changelog, cùng author nhưng có **id khác nhau**.
- Tệp được duyệt theo thứ tự khai báo: tạo bảng trước, thêm ràng buộc sau, cuối cùng chèn dữ liệu.
- Mỗi changeset có rollback riêng; việc rollback nhiều changeset thường được xử lý theo thứ tự ngược với chiều triển khai.
- Rollback dữ liệu trong ví dụ chỉ là minh họa. Nếu ứng dụng đã sửa bản ghi VN hoặc tạo tham chiếu liên quan, thao tác delete có thể gây mất dữ liệu hoặc thất bại do khóa ngoại.
- Không gom ba bước vào một changeset chỉ vì muốn có ít id; chia thành các bước độc lập giúp theo dõi lịch sử và tác động dễ hơn khi nghiệp vụ cho phép.

Nếu cần điều chỉnh cột hoặc dữ liệu về sau, tạo changeset **mới** thay vì sửa changeset đã chạy. Mỗi lần thêm một changeset, lịch sử cũ vẫn được giữ nguyên để Liquibase biết những gì đã triển khai.

## 7. Cấu trúc trong XML và formatted SQL

Bản chất id, author và changeset không phụ thuộc vào việc chọn YAML, XML, JSON hay SQL định dạng Liquibase. Mỗi định dạng có cách biểu diễn riêng nhưng cùng tham gia cơ chế nhận diện và lịch sử.

### XML

Ví dụ dưới đây minh họa vị trí id và author trong thẻ changeSet. Trong dự án thật, phần databaseChangeLog cần namespace và schemaLocation theo phiên bản Liquibase được sử dụng.

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
                        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-004-add-country-region" author="team-db">
        <addColumn tableName="country">
            <column name="region" type="VARCHAR(50)"/>
        </addColumn>
        <rollback>
            <dropColumn tableName="country" columnName="region"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

### Formatted SQL

Liquibase cũng có thể đọc SQL với chú thích chỉ thị:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-005-create-audit-event
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL
);

--rollback DROP TABLE audit_event;
~~~

Với formatted SQL, cú pháp **--changeset author:id** đặt author trước, id sau dấu hai chấm. Đây là điều dễ nhầm khi chuyển từ YAML/XML sang SQL. Nếu viết ngược thành id:author, Liquibase có thể ghi nhận danh tính khác so với dự kiến.

Không xem SQL thuần không có marker Liquibase là tương đương changelog formatted SQL. Với formatted SQL, các dòng chú thích đặc biệt là một phần cấu trúc điều khiển cần được giữ đúng.

## 8. Thuộc tính điều khiển thực thi gắn với changeset

Ngoài id và author, một changeset có thể có các điều kiện và bộ lọc quyết định thời điểm chạy:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-006-add-debug-note"
      author: "team-db"
      contextFilter: "dev"
      labels: "experimental"
      dbms: "postgresql"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: debug_note
                  type: VARCHAR(200)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: debug_note
~~~

Ở đây:

- **contextFilter: dev** giới hạn việc chọn changeset theo context.
- **labels: experimental** cho phép lọc theo label của lần triển khai.
- **dbms: postgresql** hạn chế changeset vào PostgreSQL.
- **preConditions** kiểm tra bảng customer đã tồn tại trước khi thêm cột.
- **rollback** mô tả cách xóa cột khi cần khôi phục.

Với bộ lọc không phù hợp, changeset có thể không được chọn trong lần chạy, dù chưa có trong DATABASECHANGELOG. Nếu precondition thất bại, cách xử lý còn phụ thuộc onFail hoặc onError; ví dụ HALT dừng triển khai, còn MARK_RAN có thể ghi nhận changeset là đã chạy mà không thực thi phần thay đổi.

Các bộ lọc và precondition **không thay thế** id hay author. Cùng một changeset được nhận diện bằng bộ ba định danh trên mọi môi trường; việc có chạy ở môi trường cụ thể hay không là vấn đề riêng.

## 9. Những thuộc tính khiến changeset được chạy lại

Thông thường changeset đã được ghi nhận sẽ không được chạy lại ở lần update kế tiếp. Hai thuộc tính thay đổi quy tắc đó:

- **runOnChange: true**: Liquibase có thể chạy lại changeset khi nội dung làm checksum thay đổi. Thường được dùng cho định nghĩa đối tượng có thể tái áp dụng, chẳng hạn một số view hoặc stored procedure.
- **runAlways: true**: Liquibase chạy changeset trong mỗi lần update phù hợp, kể cả khi đã ghi nhận trước đó.

Ví dụ minh họa một changeset có thể chạy lại khi nội dung view thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-007-view-customer-email"
      author: "team-db"
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_email
            replaceIfExists: true
            selectQuery: "SELECT id, email FROM customer"
~~~

Hành vi thực tế của replaceIfExists và khả năng triển khai lại view phụ thuộc DBMS, nên phải kiểm chứng trên hệ đang dùng. Không bật runOnChange cho một migration thêm cột hoặc chèn dữ liệu chỉ để tránh tạo id mới; làm như vậy có thể khiến các thao tác không idempotent chạy lặp.

Khi Liquibase ghi lịch sử, **MD5SUM** giúp phát hiện nội dung changeset đã thay đổi so với lần ghi nhận trước. Nếu sửa một changeset đã chạy mà không thiết kế cho phép chạy lại, Liquibase có thể báo lỗi checksum. Đây là cơ chế cảnh báo quan trọng: giải pháp mặc định là khôi phục nội dung changeset cũ và tạo một changeset mới để điều chỉnh, không phải xóa lịch sử hoặc bỏ qua checksum.

## 10. Vòng đời id và author từ pull request đến production

Một quy trình lành mạnh có các bước:

1. **Tạo changeset** trong changelog được phân công, chọn id và author theo quy ước chung.
2. **Review nội dung**: kiểm tra mục tiêu, loại thay đổi, khóa định danh, thứ tự, tương thích dữ liệu và rollback.
3. **Kiểm tra kỹ thuật**: chạy validate, status và update-sql trên database thử nghiệm với cấu hình giống môi trường mục tiêu.
4. **Thực thi ở development**: chạy update, xác minh schema, dữ liệu và DATABASECHANGELOG.
5. **Promote cùng artifact** qua staging rồi production, giữ nguyên id, author, filename và nội dung đã được thử nghiệm.
6. **Theo dõi lịch sử**: lưu log triển khai và kiểm tra EXECTYPE, MD5SUM, thời điểm ghi nhận.
7. **Thay đổi trong tương lai**: nếu cần chỉnh sửa, thêm changeset mới và giữ changeset cũ bất biến.

Cấu hình Spring Boot có thể trỏ tới changelog bằng **spring.liquibase.change-log**; CLI hoặc pipeline chỉ định changelog và kết nối tương ứng. Tất cả đều dựa trên lịch sử của database đích. Do đó, changeset đã chạy ở development vẫn có thể đang chờ ở production, dù id và author giống hệt nhau.

Khi nhiều người phát triển đồng thời, hai nhánh có thể tạo changeset cùng id và author trong một tệp. Lỗi cần được phát hiện khi review/merge, trước khi migration chạy ở môi trường dùng chung. Hãy giải quyết va chạm khi chưa phát hành; sau khi một changeset đã được ghi nhận trên database thật, việc đổi id hoặc author tùy tiện không còn an toàn.

## 11. Cách kiểm tra changeset đã ghi nhận và changeset còn chờ

Giả sử đã cấu hình đúng kết nối database và changelog gốc trong Liquibase CLI:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **validate** kiểm tra cấu trúc changelog và một số lỗi như định danh trùng trong phạm vi được nạp.
- **status --verbose** giúp xem những changeset Liquibase đang coi là chưa áp dụng đối với cấu hình hiện tại.
- **update-sql** tạo SQL dự kiến cho lần update, thuận tiện để review trước khi thực thi.

Sau khi đã xác nhận đúng database và tác động của SQL:

~~~bash
liquibase update
liquibase history
~~~

history cho biết lịch sử Liquibase đã ghi nhận. Có thể kiểm tra trực tiếp với SQL:

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Khi diễn giải:

- **EXECUTED** thường nghĩa là nội dung changeset đã được thực thi.
- **RERAN** có thể xuất hiện khi changeset được chạy lại.
- **MARK_RAN** nghĩa là changeset được ghi nhận mà phần thay đổi có thể đã không được thực thi, ví dụ do precondition hoặc thao tác đồng bộ lịch sử.

Không suy luận rằng schema thực tế chắc chắn đúng chỉ vì một dòng lịch sử tồn tại. Cần kiểm tra đối tượng, ràng buộc và dữ liệu tương ứng. Ngược lại, nếu đối tượng đã tồn tại nhưng changeset chưa có lịch sử, có thể đã có thao tác SQL ngoài Liquibase hoặc quá trình baseline chưa hoàn thành.

## 12. Các lỗi thường gặp khi đặt id và author

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai changeset trong cùng tệp bị coi là trùng | Cùng id và author | Chọn id duy nhất trước khi phát hành; chạy validate |
| Changeset cũ xuất hiện lại trong status | Đã sửa id, author hoặc FILENAME | Đối chiếu ba thành phần với DATABASECHANGELOG; khôi phục định danh lịch sử |
| Migration thất bại vì bảng/cột đã tồn tại | Changeset được xem là mới sau khi đổi đường dẫn hoặc có drift schema | Kiểm tra lịch sử, logicalFilePath và trạng thái schema; tránh chạy lại mù quáng |
| Chỉnh một typo trong changeset cũ gây lỗi checksum | Nội dung migration đã chạy bị sửa | Giữ nguyên lịch sử, viết changeset điều chỉnh mới |
| id trông đúng nhưng bị YAML parser hiểu khác | id là số hoặc có cú pháp đặc biệt không được trích dẫn | Đặt id trong nháy kép ngay từ khi tạo |
| Không truy vết được người chịu trách nhiệm | author đặt tùy tiện hoặc đổi theo người merge | Chuẩn hóa author ổn định và liên kết với PR/ticket qua Git |
| Production không chạy một changeset | Context/label/dbms không phù hợp hoặc changeset đã được ghi nhận | Kiểm tra bộ lọc và DATABASECHANGELOG ở chính production |
| Changeset chạy lại ngoài dự kiến | runAlways hoặc runOnChange được bật không phù hợp | Kiểm tra thuộc tính và thiết kế idempotent, tạo changeset mới khi cần |
| Tác động rollback lớn hơn dự kiến | Rollback xóa bảng/dữ liệu đã được sử dụng | Kiểm tra phụ thuộc, sao lưu, thử khôi phục và chọn chiến lược an toàn |

Không sửa trực tiếp ID, AUTHOR hoặc FILENAME trong DATABASECHANGELOG để che lỗi. Bảng này là lịch sử của Liquibase và việc chỉnh tay có thể làm hỏng khả năng xác định changeset đang chờ, xử lý checksum hoặc rollback. Các trường hợp baseline, đồng bộ lịch sử hoặc đổi đường dẫn cần một quy trình chuyển đổi có kiểm chứng riêng.

## 13. Bài thực hành tự kiểm tra

**Bối cảnh:** ứng dụng cần thêm cột phone vào bảng customer. Nhóm đã thống nhất dùng author là team-db và id dạng ngày + số thứ tự + mô tả.

Hãy tạo changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-008-add-customer-phone"
      author: "team-db"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: phone
~~~

Thực hiện theo trình tự:

1. Đọc changeset và giải thích ba phần của khóa định danh: id, author, đường dẫn tệp.
2. Chạy validate để xác nhận changelog hợp lệ.
3. Chạy status --verbose trên database development và quan sát changeset đang chờ.
4. Chạy update-sql để xem câu lệnh ALTER TABLE dự kiến.
5. Chạy update trên database thử nghiệm, sau đó kiểm tra cột phone và dòng lịch sử trong DATABASECHANGELOG.
6. Chạy lại status. Changeset thông thường không còn trong danh sách pending.
7. Thử **chỉ trên database dùng để học**: đổi id hoặc author của changeset đã ghi nhận, chạy lại status mà **không chạy update**. Quan sát rằng Liquibase có thể coi đây là định danh mới.
8. Khôi phục ngay id/author ban đầu. Không thử thao tác thay đổi định danh như vậy trên production.

Câu hỏi tự kiểm tra: Nếu một thay đổi đã chạy trên development nhưng chưa chạy trên staging, nên sửa id hay giữ nguyên? **Giữ nguyên.** Mỗi database có DATABASECHANGELOG riêng; sự khác biệt trạng thái là điều bình thường.

Một câu hỏi khác: Nếu cần thay đổi kiểu dữ liệu phone sau khi changeset đã triển khai, có sửa changeset 008 không? **Không.** Hãy tạo changeset mới như 20261120-001-alter-customer-phone, có kế hoạch chuyển đổi dữ liệu và rollback phù hợp.

## 14. Checklist khi review changeset

- [ ] Tệp chứa changeset nằm trong changelog gốc hoặc được include đúng cách.
- [ ] id là chuỗi có ý nghĩa, ổn định và không va chạm với changeset khác.
- [ ] author theo quy ước chung của nhóm, không bị đổi theo người review.
- [ ] Đã xét đủ bộ ba id–author–filename, kể cả tác động của logicalFilePath.
- [ ] Thứ tự changeset trong changelog phù hợp với phụ thuộc schema và dữ liệu.
- [ ] Các change nằm đúng cấp YAML/XML/SQL và được validate.
- [ ] Mỗi changeset có mục tiêu rõ ràng, phạm vi hợp lý và cách khôi phục được xem xét.
- [ ] Context, label, dbms, precondition và thuộc tính chạy lại được sử dụng có chủ đích.
- [ ] Không sửa id, author hoặc nội dung của changeset đã triển khai.
- [ ] Đã review update-sql và xác nhận database/schema đích trước khi chạy update.
- [ ] Đã kiểm tra DATABASECHANGELOG và schema thực tế sau triển khai.
- [ ] Cùng artifact và changelog được promote qua các môi trường.

Cấu trúc changeset giúp Liquibase biết **cần thay đổi gì**, còn bộ ba id–author–filename giúp nó biết **đã ghi nhận thay đổi nào** trên database đích. Khi quy ước định danh nhất quán và các changeset đã phát hành được giữ bất biến, lịch sử triển khai trở nên dễ tra cứu, các lần update có thể kiểm chứng, và việc phối hợp migration qua Spring Boot hoặc CI/CD an toàn hơn.
