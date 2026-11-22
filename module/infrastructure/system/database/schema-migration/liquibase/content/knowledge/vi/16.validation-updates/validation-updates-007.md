# Cập nhật tới mốc gắn thẻ bằng update-to-tag

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Kiểm tra và cập nhật**, không phải lần triển khai nào cũng nên chạy tất cả changeset mới nhất trong changelog. Một release có thể chỉ được phê duyệt tới một ranh giới rõ ràng; các changeset sau đó đã được commit vào cùng repository nhưng chưa sẵn sàng chạy. Liquibase cung cấp cơ chế **gắn thẻ một mốc trong changelog** bằng change type **tagDatabase**, sau đó **cập nhật đến mốc ấy** bằng lệnh **update-to-tag** trên những phiên bản/edition hỗ trợ.

Đây là một công cụ kiểm soát phạm vi migration, không phải chức năng gắn nhãn tùy ý cho từng changeset. Hiểu sai sự khác nhau giữa **tagDatabase** và lệnh **tag** có thể khiến không tìm thấy mốc đích; hiểu sai update-to-tag với rollback có thể tạo kỳ vọng nguy hiểm rằng database sẽ tự quay về phiên bản cũ.

Bài học này trình bày cách dùng update-to-tag, cách xác định ranh giới changeset, kiểm tra lịch sử **DATABASECHANGELOG**, các tình huống môi trường không đồng nhất, giới hạn về phiên bản/giấy phép, rủi ro khi kết hợp với context/label filter, cùng cách tích hợp vào Spring Boot hoặc CI/CD. Đây là một phần của quy trình quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum, rollback và triển khai có kiểm chứng.

## 1. Bài toán: chỉ triển khai tới một release cụ thể

Giả sử changelog đang có các bước:

~~~text
db.changelog.yaml
|
+-- 001  Tạo bảng customer
+-- 002  Thêm cột customer.status
+-- 003  TAG: release-2026.11.1
+-- 004  Tạo bảng customer_audit
+-- 005  Thêm cột customer.region
+-- 006  TAG: release-2026.11.2
+-- 007  Thử nghiệm một thay đổi cho release sau
~~~

Mục tiêu của đợt phát hành **release-2026.11.1** là triển khai các thay đổi tới bước 003, **không chạy các bước 004–007**, dù chúng có mặt trong cùng changelog.

- Nếu chạy **update** thông thường và mọi changeset đều đủ điều kiện, Liquibase sẽ xem xét các changeset chờ xử lý tới cuối changelog.
- Nếu chạy **update-to-tag** với tag **release-2026.11.1**, Liquibase sẽ áp dụng các changeset cần thiết theo thứ tự tới changeset chứa mốc tag đó rồi dừng.
- Nếu muốn tiến lên **release-2026.11.2** về sau, có thể chạy update-to-tag đến mốc tiếp theo theo quy trình triển khai.
- Nếu database đã áp dụng changeset 007, chạy update-to-tag về tag 003 **không tự xóa** các thay đổi 004–007. Nó là thao tác **tiến lên có giới hạn**, không phải rollback.

Suy ra nguyên tắc quan trọng: **tag xác định ranh giới lịch sử được phép cập nhật tới; nó không tự tạo một bản sao trạng thái database, cũng không cam kết mọi môi trường có cùng dữ liệu sau khi chạy**.

## 2. Ba khái niệm phải phân biệt: changeset, tagDatabase và tag

### 2.1. Changeset là đơn vị được Liquibase quản lý

Một changeset thường được nhận diện bởi **id + author + đường dẫn changelog** (có thể chịu ảnh hưởng của logicalFilePath). Liquibase lưu lịch sử trong **DATABASECHANGELOG**, bao gồm thông tin chạy và checksum. Khi chạy update-to-tag, cơ chế quản lý changeset đã chạy/chưa chạy vẫn giữ nguyên.

### 2.2. tagDatabase là một change trong changelog

**tagDatabase** tạo một **mốc tag có thể tìm thấy trong chính chuỗi thay đổi được khai báo**. Thường nên đặt nó trong một changeset riêng, không ghép với những thay đổi schema hoặc dữ liệu khác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-tag-release-2026-11-1"
      author: "platform"
      changes:
        - tagDatabase:
            tag: "release-2026.11.1"
~~~

Một tagDatabase **không tự tạo hoặc sửa bảng nghiệp vụ**. Vai trò của nó là đánh dấu vị trí trong chuỗi migration và ghi nhận mốc trong lịch sử triển khai khi changeset tag được thực thi.

Lý do đặt riêng: một thay đổi có mục đích rõ ràng, dễ review, dễ đối chiếu mốc, không bị trộn với thao tác có khóa lâu, DML lớn hoặc rollback phức tạp.

### 2.3. Lệnh tag đánh dấu trạng thái hiện tại, không thay thế mốc khai báo

Liquibase còn có lệnh dạng:

~~~bash
liquibase tag --tag=release-2026.11.1
~~~

Lệnh **tag** được sử dụng để **gắn nhãn cho trạng thái database hiện tại trong lịch sử**. Nó không thêm một tagDatabase changeset vào changelog đã được version-control.

Đối với **update-to-tag**, điểm đích phải được định nghĩa bằng **tagDatabase trong changelog** theo cơ chế lệnh này hỗ trợ. Không nên giả định có thể dùng một tag được tạo thủ công bằng lệnh **tag** làm ranh giới tương lai cho update-to-tag. Hai cơ chế phục vụ các nhu cầu khác nhau: một bên tạo marker khai báo trong chuỗi migration, một bên gắn nhãn trạng thái đang tồn tại.

**Tag không phải label và không phải context.** Label/context filter quyết định changeset nào đủ điều kiện chạy; tagDatabase quyết định mốc dừng của một lệnh cập nhật có giới hạn.

## 3. Cấu trúc changelog YAML với hai mốc phát hành

Ví dụ dưới đây minh họa một chuỗi migration có thể đọc độc lập. Giả sử database chưa có các đối tượng ví dụ và DBMS đích hỗ trợ các change type cơ bản được sử dụng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "platform"
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
                  name: full_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false

  - changeSet:
      id: "20261119-002-add-status"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(30)

  - changeSet:
      id: "20261119-003-tag-release-1"
      author: "platform"
      changes:
        - tagDatabase:
            tag: "release-2026.11.1"

  - changeSet:
      id: "20261119-004-create-customer-audit"
      author: "platform"
      changes:
        - createTable:
            tableName: customer_audit
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false

  - changeSet:
      id: "20261119-005-add-region"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region
                  type: VARCHAR(40)

  - changeSet:
      id: "20261119-006-tag-release-2"
      author: "platform"
      changes:
        - tagDatabase:
            tag: "release-2026.11.2"

  - changeSet:
      id: "20261119-007-next-release"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: internal_note
                  type: VARCHAR(200)
~~~

Các changeset ở đây được sắp theo trình tự phụ thuộc. **Hai marker tagDatabase thuộc hai changeset riêng** và có tên khác nhau. Với database trống, lần chạy tới tag thứ nhất dự kiến sẽ áp dụng các changeset 001, 002, 003, còn 004–007 chưa được chạy. Khi tiếp tục tới tag thứ hai, các bước 004, 005, 006 có thể được áp dụng tiếp; 001–003 không chạy lại trong trường hợp thông thường.

Ví dụ chỉ phục vụ giảng giải; không nên đưa tên bảng/ID này vào production mà không kiểm tra xung đột và quy ước của dự án.

## 4. Cú pháp lệnh update-to-tag và điều kiện sử dụng

Cách gọi phổ biến trong các bản Liquibase hỗ trợ lệnh là:

~~~bash
liquibase \
  --changelog-file=db.changelog.yaml \
  update-to-tag \
  --tag=release-2026.11.1
~~~

Các tham số kết nối database như URL, username và thông tin xác thực cần được cấp qua cấu hình Liquibase hoặc secret của pipeline; không đưa mật khẩu vào changelog hay commit.

**Điều kiện tiên quyết:** xác nhận **phiên bản và edition/license** của Liquibase thực sự chạy có cung cấp **update-to-tag**. Tính sẵn có của lệnh này có thể phụ thuộc gói sản phẩm và phiên bản; không giả định rằng mọi bản Community CLI hoặc dependency Liquibase trong Spring Boot đều hỗ trợ. Cần đối chiếu tài liệu của chính phiên bản được triển khai và danh sách lệnh của binary/JAR thực tế. Nếu lệnh không khả dụng, không tự “chữa” bằng cách đổi tên flag ngẫu nhiên hoặc thay bằng update thông thường trên production, vì điều đó có thể thay đổi phạm vi migration.

Kiểm tra phiên bản:

~~~bash
liquibase --version
liquibase --help
~~~

Tùy phiên bản, cú pháp thứ tự đối số và tên tùy chọn có thể thay đổi. **--tag** ở đây là **tên mốc đích**, không phải label filter. Các lệnh ví dụ dùng cú pháp xuống dòng của shell POSIX; trên PowerShell hoặc CMD có thể viết trên một dòng hoặc dùng ký hiệu xuống dòng phù hợp.

Trước khi chạy thật, xác nhận đường dẫn changelog trỏ tới **đúng artifact version-controlled**, môi trường, credentials, schema, edition/license và DBMS cần triển khai.

## 5. update-to-tag chọn những changeset nào?

Có thể tóm tắt cơ chế ở mức ý nghĩa như sau:

1. Liquibase đọc changelog và chuỗi các changeset theo thứ tự được xác định, kể cả các file include.
2. Tìm mốc **tagDatabase** có tên khớp với giá trị **--tag** trong changelog.
3. Xác định phạm vi đến changeset chứa marker tag đó; changeset sau marker không thuộc phạm vi update-to-tag này.
4. Trong phạm vi, Liquibase dùng lịch sử **DATABASECHANGELOG** và các quy tắc thực thi để quyết định changeset nào cần chạy.
5. Áp dụng những changeset cần thiết theo thứ tự và ghi lịch sử khi thành công, rồi dừng ở mốc yêu cầu.

Sơ đồ khái niệm:

~~~text
Changelog có thứ tự:
    C001 -> C002 -> TAG R1 -> C004 -> C005 -> TAG R2 -> C007
                     ^
                     |
             update-to-tag R1
                     |
            Chỉ xét tới marker này

DATABASECHANGELOG:
    C001 chưa chạy? -> áp dụng nếu đủ điều kiện
    C002 chưa chạy? -> áp dụng nếu đủ điều kiện
    TAG R1          -> ghi mốc theo cơ chế tagDatabase
    C004 trở đi     -> không áp dụng trong lệnh này
~~~

**Phạm vi đến tag không đồng nghĩa mọi changeset trước tag chắc chắn đã chạy.** Context, label filter, dbms, precondition, trạng thái lịch sử hoặc lỗi thực thi có thể làm thay đổi tập changeset thực tế. Muốn khẳng định release đạt trạng thái mong đợi, cần xác minh rõ điều kiện và dữ liệu, không chỉ dựa vào việc lệnh trả mã thoát thành công.

Một tagDatabase nên nằm ở ranh giới release thật sự và có thứ tự rõ ràng. Nếu thay đổi cấu trúc include, đường dẫn hay thứ tự marker, cần đánh giá tác động đến cả phạm vi cập nhật và định danh changeset.

## 6. Hành vi khi database đã có lịch sử

Khác biệt giữa database trống và database đã chạy một phần là cốt lõi của Liquibase.

### Trường hợp A — Database chưa chạy thay đổi nào

Với ví dụ mục 3, chạy update-to-tag tới **release-2026.11.1** thường dẫn đến:

| Changeset | Kết quả mong đợi |
|---|---|
| 001 — create customer | Được áp dụng |
| 002 — add status | Được áp dụng |
| 003 — tagDatabase R1 | Được ghi nhận |
| 004 — create audit | Chưa nằm trong phạm vi |
| 005 — add region | Chưa nằm trong phạm vi |
| 006 — tagDatabase R2 | Chưa nằm trong phạm vi |
| 007 — next release | Chưa nằm trong phạm vi |

### Trường hợp B — Đã chạy tới R1, triển khai tiếp tới R2

Khi chạy update-to-tag **release-2026.11.2**:

- 001–003 đã được ghi nhận sẽ không chạy lại theo cơ chế bình thường.
- 004–006 được xem xét và áp dụng nếu đủ điều kiện.
- 007 vẫn nằm sau mốc đích nên chưa được áp dụng.

Một số changeset có **runAlways** hoặc **runOnChange** có thể có ngữ nghĩa chạy lại riêng; cần đánh giá chúng theo phiên bản và điều kiện của changelog thay vì coi toàn bộ các changeset đã chạy là bất biến tuyệt đối về thực thi.

### Trường hợp C — Database đã cập nhật vượt mốc R1

Giả sử database đã chạy 001–007, sau đó operator thực hiện:

~~~bash
liquibase --changelog-file=db.changelog.yaml \
  update-to-tag --tag=release-2026.11.1
~~~

Lệnh này **không rollback 004–007**. Nếu mục tiêu là đưa database về trạng thái trước các thay đổi đó, phải nghiên cứu một **quy trình rollback riêng**, kèm đánh giá tác động dữ liệu, khả năng hỗ trợ và điều kiện an toàn của ứng dụng.

**Không nên sử dụng update-to-tag để “hạ version”** hay coi tag là snapshot có thể khôi phục tức thời.

### Trường hợp D — Changeset trước tag bị bỏ qua vì filter

Giả sử C002 có context **dev** nhưng pipeline chạy khác cấu hình. Một marker tag có thể được ghi nhận trong khi một số thay đổi có điều kiện chưa chạy; về sau thay filter, một changeset trước mốc có thể trở thành đủ điều kiện. Vì vậy mốc tag không tự chứng minh tính đồng nhất của schema giữa dev, staging và production. Cần kiểm tra context, label và trạng thái đã áp dụng của từng changeset cần thiết.

## 7. Phân biệt update, update-count, update-to-tag và rollback

| Thao tác | Mục tiêu chính | Cách giới hạn |
|---|---|---|
| **update** | Áp dụng changeset chờ chạy theo changelog | Không có mốc dừng tag; còn phụ thuộc filter/điều kiện |
| **update-count** | Áp dụng một số lượng changeset giới hạn | Dựa trên số changeset, không dựa trên release marker |
| **update-to-tag** | Áp dụng changeset chờ chạy đến mốc tagDatabase trong changelog | Dựa trên tên tag đích |
| **tag** | Gắn nhãn trạng thái hiện tại của database | Không phải lệnh update tiến tới marker trong changelog |
| **rollback-to-tag** hoặc quy trình rollback tương ứng | Hoàn tác các thay đổi theo mốc lịch sử | Là thao tác khác, phải kiểm tra rollback của từng changeset |

**Đừng nhầm số lượng với mốc nghiệp vụ.** update-count có thể hữu ích cho thử nghiệm có kiểm soát, nhưng khi một nhóm thêm changeset mới vào đầu changelog hoặc thay context, “chạy 5 changeset” không tự mang nghĩa “tới release R1”. Marker tagDatabase rõ ràng thường giúp review phạm vi release hơn.

**Đừng nhầm update-to-tag với rollback-to-tag.** Update có hướng tiến lên; rollback có hướng hoàn tác và có thể làm mất dữ liệu hoặc thất bại nếu changeset không có rollback hợp lệ. Khả năng rollback-to-tag, cú pháp và edition cũng cần xác nhận trên runtime đang dùng.

## 8. Vì sao marker tagDatabase nên là changeset riêng?

Marker riêng có các lợi ích:

- **Mục đích đơn nhất**: tên changeset thể hiện việc đóng mốc release, không che lẫn DDL/DML.
- **Lịch sử dễ đọc**: có thể tìm marker bằng ID và trường TAG trong DATABASECHANGELOG.
- **Review phạm vi rõ ràng**: mọi thay đổi muốn thuộc release phải đứng đúng phía trước marker.
- **Rollback dễ đánh giá hơn**: marker không chứa SQL nghiệp vụ vô tình bị đảo cùng thao tác gắn tag.
- **Giảm sai khác checksum**: marker được giữ bất biến sau triển khai như một changeset lịch sử.

Một số quy tắc đặt tên:

~~~text
tagDatabase.tag      = release-2026.11.1
changeSet.id         = 20261119-003-tag-release-2026-11-1
changeSet.author     = platform
changelog file path  = db/changelog/db.changelog.yaml
~~~

Nên dùng tên tag **duy nhất trong chuỗi changelog liên quan**, ổn định, không đổi sau khi phát hành. Nếu sử dụng lại cùng tên tag ở nhiều marker, việc xác định mốc đích trở nên khó giải thích và có thể phụ thuộc cách engine xử lý; tránh thiết kế mơ hồ này.

Không nên gắn một marker cho mỗi thay đổi nhỏ nếu mục tiêu của tổ chức là release theo nhóm. Mốc tag nên phản ánh ranh giới có thể xác minh và vận hành, không phải trang trí changelog.

## 9. Có thể gắn tag bằng những định dạng changelog nào?

Ví dụ ở trên dùng **YAML**, trong đó tagDatabase được khai báo như một change dưới changeset. XML và JSON cũng có thể biểu diễn change type trong những phiên bản Liquibase hỗ trợ.

Ví dụ XML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.24.xsd">

    <changeSet id="20261119-003-tag-release-1"
               author="platform">
        <tagDatabase tag="release-2026.11.1"/>
    </changeSet>
</databaseChangeLog>
~~~

Trong ví dụ, **dbchangelog-4.24.xsd** chỉ là một tham chiếu minh họa đến XSD cụ thể, không phải yêu cầu nâng cấp hoặc chứng nhận tính tương thích cho mọi bản Liquibase. Khi dùng XML, chọn XSD phù hợp với runtime; khi dùng YAML/JSON, kiểm tra đúng tên trường và cấu trúc của change type.

Với **formatted SQL**, các directive có mức hỗ trợ khác nhau theo phiên bản/edition. Không tự giả định rằng viết một comment như **--tagDatabase** sẽ tạo được marker tương đương. Nếu dự án dùng formatted SQL làm changelog chính nhưng cần tagDatabase, hãy kiểm tra khả năng hỗ trợ của bản Liquibase và thiết kế file changelog cấu trúc được include phù hợp nếu cần. Không chèn một dòng SQL tùy ý rồi coi đó là lịch sử tagDatabase.

Tương tự, file SQL tham chiếu bằng **sqlFile** trong changeset khác với **changelog formatted SQL**. Ranh giới tagDatabase thuộc cấu trúc changelog mà Liquibase parse, không phải một chuỗi SQL ngẫu nhiên.

## 10. Preflight trước khi cập nhật tới tag

Một quy trình triển khai an toàn cần trả lời các câu hỏi sau trước khi gọi update-to-tag.

### 10.1. Đang chạy phiên bản/edition nào?

~~~bash
liquibase --version
liquibase --help
~~~

Xác nhận lệnh **update-to-tag** khả dụng, bản quyền/extension cần thiết đã được cấu hình nếu phiên bản yêu cầu và changelog đang được parser hỗ trợ.

Nếu local dùng CLI khác với Spring Boot hoặc CI/CD, không dựa vào “máy lập trình chạy được” làm bằng chứng cho production. Ưu tiên kiểm chứng bằng đúng container/JAR/binary dùng để triển khai.

### 10.2. Marker đích có trong changelog không?

Mở **changelog đã được phê duyệt** và xác nhận có changeset chứa:

~~~yaml
- tagDatabase:
    tag: "release-2026.11.1"
~~~

Kiểm tra thứ tự include và vị trí của marker so với các thay đổi cần chạy. Nếu marker chưa có trong file, hoặc đặt sau những thay đổi không được phép chạy, cần sửa thiết kế changelog **trước khi phát hành**; không dùng update thường để “lách” sự thiếu marker.

Lệnh kiểm tra tag trong lịch sử database (nếu phiên bản hỗ trợ) không nhất thiết chứng minh một tag chưa áp dụng đang tồn tại trong changelog. Vì vậy, việc kiểm tra lịch sử và việc kiểm tra **marker khai báo** phải được tách riêng.

### 10.3. Tình trạng database có đúng kỳ vọng không?

Cần xác nhận:

- URL/schema/catalog của môi trường đích.
- Các changeset đã được ghi trong DATABASECHANGELOG.
- Có thay đổi thủ công ngoài Liquibase làm lệch schema không.
- Có bản phát hành trước nào bị lỗi hoặc chỉ chạy một phần không.
- Context/label filter, DBMS và precondition có làm thay đổi phạm vi được chọn không.
- Những thay đổi dữ liệu lớn hoặc DDL có khóa lâu đã được review chưa.

Không chạy migration vào production khi chưa biết **chính xác database và phạm vi changeset** sẽ bị tác động.

## 11. Validate và xem trước SQL

Có thể dùng các lệnh kiểm tra cơ bản:

~~~bash
liquibase --changelog-file=db.changelog.yaml validate
liquibase --changelog-file=db.changelog.yaml status --verbose
~~~

**validate** kiểm tra khả năng đọc changelog cùng những quy tắc validation mà phiên bản hỗ trợ; **status --verbose** giúp đối chiếu changeset chờ triển khai. Tuy nhiên, status thông thường không nhất thiết chỉ hiển thị tập bị giới hạn bởi update-to-tag, nên không nên lấy danh sách đầy đủ làm kết luận rằng lệnh cập nhật tới tag sẽ chạy toàn bộ.

Nếu phiên bản/edition cung cấp lệnh **update-to-tag-sql** hoặc chế độ preview tương đương, nên dùng chính lệnh đó để xem SQL **đến tag**:

~~~bash
liquibase --changelog-file=db.changelog.yaml \
  update-to-tag-sql --tag=release-2026.11.1
~~~

Lệnh này được nêu **có điều kiện**: cần kiểm tra danh sách lệnh và cú pháp của phiên bản thực tế, vì tính sẵn có có thể khác nhau. Nếu không có preview chuyên dụng, phải dùng một quy trình thử nghiệm an toàn trên database đại diện với đúng artifact/flags, **không thay bằng update-sql toàn changelog rồi coi như cùng phạm vi**.

Trước update thật, đối chiếu các thay đổi dự kiến với release manifest và chú ý:

1. Có changeset sau tag nào bị đưa vào phạm vi không?
2. Các changeset trước tag nhưng thuộc môi trường khác có được lọc đúng không?
3. Có changeset DML lớn, xóa cột hoặc ràng buộc có nguy cơ phá tương thích ứng dụng không?
4. Có precondition hay bước phải chờ backfill ngoài Liquibase không?
5. Tag marker có đứng đúng vị trí và mang tên chuẩn của release không?

**Preview SQL không chứng minh DDL/DML sẽ chạy nhanh, không khóa lâu hoặc rollback thành công**. Vẫn phải thử trên database đại diện trước khi phát hành.

## 12. Ví dụ thực hành: hai lần cập nhật tới hai mốc

Dùng changelog mục 3 trên **database thử nghiệm riêng**. Nếu có thể, tạo lại cùng trạng thái ban đầu khi thử kịch bản khác nhau.

### Lần 1 — Cập nhật tới release-2026.11.1

~~~bash
liquibase --changelog-file=db.changelog.yaml \
  update-to-tag --tag=release-2026.11.1
~~~

Kỳ vọng:

- Bảng **customer** được tạo.
- Cột **status** được thêm.
- Changeset tag R1 được ghi nhận.
- Chưa có bảng **customer_audit**, cột **region** hoặc **internal_note**.

Nếu một trong các đối tượng sau R1 đã tồn tại từ trước, không được kết luận update-to-tag chạy sai ngay lập tức. Có thể database đã được thay đổi thủ công hoặc đã chạy migration trước đó; cần xem DATABASECHANGELOG và lịch sử thực tế.

### Lần 2 — Tiến lên release-2026.11.2

~~~bash
liquibase --changelog-file=db.changelog.yaml \
  update-to-tag --tag=release-2026.11.2
~~~

Kỳ vọng:

- Các changeset 004 và 005 được chạy nếu chưa được áp dụng và đủ điều kiện.
- Tag R2 được ghi nhận.
- Changeset 007 vẫn chưa nằm trong phạm vi.
- Changeset 001 và 002 không bị thực thi lại ở tình huống thông thường.

### Lần 3 — Gọi lại tới cùng tag

Nếu chạy lại update-to-tag tới R2 sau khi tất cả changeset đến R2 đã hoàn thành, Liquibase thông thường không thực thi lại các changeset đã chạy. Tuy nhiên, phải đọc log/SQL thực tế nếu changelog có **runAlways** hoặc **runOnChange**; không mặc định mọi lần gọi đều không làm gì.

Mục tiêu thực hành là so sánh **phạm vi kỳ vọng**, **lịch sử changeset** và **schema thực tế**, không chỉ tin vào mã thoát của CLI.

## 13. Kiểm tra DATABASECHANGELOG và giá trị TAG

Sau mỗi lần chạy, nên kiểm tra bảng lịch sử Liquibase bằng truy vấn phù hợp với DBMS:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    ORDEREXECUTED,
    DATEEXECUTED,
    EXECTYPE,
    TAG,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Trong mô hình ví dụ, sau R1 kỳ vọng thấy những changeset đã thực thi tới marker và thông tin TAG tương ứng ở lịch sử. Sau R2, có thêm thay đổi đến mốc mới. Những changeset chưa chạy không xuất hiện như những bản ghi **đã thực thi thành công**.

Cần hiểu rõ:

- **TAG** là metadata lịch sử, không phải cột thuộc bảng nghiệp vụ.
- **MD5SUM** chứa checksum Liquibase dùng để đối chiếu định nghĩa changeset đã được áp dụng.
- **FILENAME** và ID/AUTHOR góp phần nhận diện changeset; đổi đường dẫn changelog mà không quản lý logicalFilePath có thể khiến Liquibase coi changeset cũ như mới.
- **EXECTYPE** giúp phân biệt một số trạng thái thực thi; phải xem cùng log và schema, không chỉ đếm số dòng.

Ví dụ truy vấn xác minh sau R1:

~~~sql
SELECT ID, TAG, ORDEREXECUTED
FROM DATABASECHANGELOG
WHERE TAG IS NOT NULL
ORDER BY ORDEREXECUTED;
~~~

Nếu tag không xuất hiện như dự kiến, phải điều tra marker đã được thực thi hay chưa, có bị filter/precondition ảnh hưởng hay không, và lệnh có chạy trên đúng database không. Không tự thêm hoặc sửa trực tiếp các dòng DATABASECHANGELOG để giả lập thành công.

## 14. Những yếu tố có thể làm mốc tag không phản ánh trạng thái mong muốn

Một marker không phải một cam kết tuyệt đối rằng tất cả cấu trúc và dữ liệu đều đúng.

### 14.1. Context và label filter

Các changeset có context hoặc label có thể được chọn khác nhau theo bộ lọc lúc chạy. Một changeset không gắn filter thường được coi là dùng chung; thiếu filter không nhất thiết là “không chạy gì”. Nếu pipeline dùng filter khác nhau giữa staging và production, hai database cùng có tag R1 vẫn có thể không chứa cùng bộ changeset hoặc dữ liệu.

**Giải pháp:** giữ cấu hình filter tường minh, kiểm chứng toàn bộ tập thay đổi kỳ vọng theo từng môi trường và không sử dụng tag thay thế cho context/label policy.

### 14.2. Precondition

Một precondition có thể **HALT**, **WARN** hoặc **MARK_RAN** tùy cấu hình và hỗ trợ. MARK_RAN có thể ghi nhận changeset là đã được xử lý nhưng không thực thi phần changes. Vì vậy, nếu những ràng buộc quan trọng chưa có mà changeset vẫn được đánh dấu, cần điều tra cấu hình precondition và trạng thái thật.

**Giải pháp:** dùng HALT cho những điều kiện bắt buộc, kiểm tra schema sau update và tránh dùng MARK_RAN chỉ để vượt lỗi.

### 14.3. Backfill ngoài Liquibase chưa hoàn tất

Giả sử marker R2 nằm sau một changeset thêm NOT NULL, nhưng công việc backfill chạy ngoài Liquibase vẫn còn dữ liệu thiếu. Nếu thứ tự release không được kiểm soát, lệnh update-to-tag R2 có thể tới bước contract quá sớm và thất bại.

**Giải pháp:** tách release thành nhiều giai đoạn có bằng chứng **job VERIFIED**, precondition dữ liệu và điểm dừng thật ở orchestration. Chỉ gắn tag tại mốc đã được định nghĩa là hoàn thành theo điều kiện release.

### 14.4. Khác biệt DBMS và transaction

Một changeset có thể chạy được trên một DBMS nhưng lỗi trên DBMS khác, hoặc DDL có implicit commit khiến trạng thái sau lỗi phức tạp. update-to-tag không tự chuyển mọi changeset thành một transaction bao trùm cả release.

**Giải pháp:** thử update tới tag trên DBMS và phiên bản đại diện, đánh giá từng changeset có DDL/DML rủi ro cao, chuẩn bị hướng phục hồi.

### 14.5. Can thiệp schema ngoài Liquibase

Một DBA có thể đã ALTER TABLE trực tiếp trước khi Liquibase chạy. Database có thể có tag phù hợp nhưng schema lệch hoặc tồn tại đối tượng ngoài lịch sử.

**Giải pháp:** phối hợp kiểm tra schema, quyền thay đổi database và lịch sử release; không coi số tag là bằng chứng thay thế cho kiểm chứng thực tế.

## 15. Những lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CLI báo không nhận lệnh update-to-tag | Phiên bản/edition không hỗ trợ hoặc tên cú pháp khác | Kiểm tra --version, --help, license, tài liệu đúng bản |
| Không tìm thấy tag đích | Chưa có tagDatabase trong changelog, sai tên, marker chưa được include | Kiểm tra changelog artifact, vị trí tagDatabase và tên tag chính xác |
| Có tag trong DATABASECHANGELOG nhưng update-to-tag không tìm thấy | Tag được tạo bằng lệnh tag, không phải marker khai báo trong changelog | Phân biệt tag runtime và tagDatabase; thiết kế mốc release có version-control |
| Chạy update-to-tag nhưng thấy nhiều thay đổi hơn kỳ vọng | Marker đặt sau những changeset ngoài release hoặc thiếu filter | Review thứ tự changelog/include, context/label, preview SQL |
| Một số thay đổi trước tag không chạy | Đã chạy trước đó, bị filter/dbms/precondition loại hoặc update lỗi | Đối chiếu log, DATABASECHANGELOG, schema và cấu hình |
| Database đã vượt tag mà không “quay lại” | update-to-tag không phải rollback | Xem quy trình rollback riêng, đánh giá dữ liệu và tương thích ứng dụng |
| Chạy trên staging được, production thất bại | Lệch DBMS/driver/runtime, dữ liệu hoặc quyền/lock | So sánh phiên bản, precondition, hiện trạng dữ liệu và SQL |
| Tag có nhưng schema chưa đúng | MARK_RAN, DDL thủ công, job dữ liệu chưa hoàn tất | Kiểm chứng metadata, dữ liệu, log và lịch sử changeset |
| Checksum validation error | Có changeset đã chạy bị sửa hoặc thay đường dẫn/định danh | Khôi phục nội dung lịch sử, tạo changeset mới, điều tra logicalFilePath |
| Tag bị trùng hoặc khó phân biệt | Dùng tên tag không duy nhất | Đặt quy ước tên theo release, giữ marker ổn định và độc lập |
| Preview update-sql trông vượt tag | Đang xem SQL update toàn bộ changelog thay vì update-to-tag-sql | Dùng preview tương ứng nếu khả dụng hoặc kiểm tra trên DB thử nghiệm |

Điểm quan trọng khi chẩn đoán là lưu **đúng thông báo lỗi**, phiên bản Liquibase, tag yêu cầu, đường dẫn changelog, DBMS và cấu hình filter. Không nên chỉ dựa vào việc tag có xuất hiện trong bảng lịch sử hay không để kết luận nguyên nhân duy nhất.

## 16. Tích hợp update-to-tag vào CI/CD

Một pipeline có kiểm soát nên định nghĩa rõ các đầu vào:

~~~text
RELEASE_TAG          = release-2026.11.1
CHANGELOG_ARTIFACT   = commit/build đã được phê duyệt
LIQUIBASE_VERSION    = phiên bản đã xác minh hỗ trợ update-to-tag
TARGET_DATABASE      = môi trường và schema cần triển khai
CONTEXT_FILTER       = giá trị được duyệt hoặc không áp dụng có chủ đích
LABEL_FILTER         = giá trị được duyệt hoặc không áp dụng có chủ đích
~~~

Đây là **mô hình cấu hình**, không phải cú pháp Liquibase. Các giá trị phải đến từ quy trình release đã phê duyệt; thông tin xác thực phải lưu ở secret manager.

Quy trình đề xuất:

1. **Đóng băng artifact**: chọn commit và changelog cụ thể, không để pipeline lấy “nhánh main mới nhất” không kiểm soát.
2. **Xác minh công cụ**: binary/JAR hỗ trợ update-to-tag, edition/license phù hợp.
3. **Xác minh marker**: changelog chứa đúng một tagDatabase theo tên release yêu cầu, ở vị trí dự kiến.
4. **Xác minh môi trường**: URL/schema, lịch sử DATABASECHANGELOG, context, label, dbms, precondition và dữ liệu.
5. **Validate và preview**: nếu hỗ trợ update-to-tag-sql, xem tập thay đổi đến mốc; nếu không, thử trên bản sao đại diện.
6. **Phê duyệt phạm vi**: đối chiếu các changeset với release manifest và kiểm tra các tác động phá tương thích/lock.
7. **Chạy update-to-tag**: triển khai một lần có giám sát với cấu hình đã duyệt.
8. **Kiểm tra hậu triển khai**: xác minh TAG, danh sách changeset, schema và dữ liệu theo tiêu chí nghiệm thu.
9. **Lưu bằng chứng**: tag đích, commit, binary version, thời điểm, database identifier, kết quả log và kiểm tra.

Nếu pipeline thiếu **RELEASE_TAG**, phải dừng trước khi gọi Liquibase. Không tự động chuyển từ update-to-tag sang update toàn bộ changelog khi thiếu tag, vì hành vi đó có thể triển khai nhiều hơn phạm vi được phê duyệt.

Trong trường hợp Liquibase được gọi khi **Spring Boot** khởi động, cấu hình tích hợp thường triển khai theo lệnh update chung của quá trình khởi tạo. Không mặc định rằng chỉ đặt một property tag nào đó là Spring Boot sẽ tự gọi update-to-tag. Nếu cần đúng chức năng này, dùng **migration job/CLI chuyên trách** có khả năng hỗ trợ và điều phối thứ tự với rollout ứng dụng. Cần kiểm soát nhiều instance khởi động đồng thời và bảo đảm mọi instance nhìn cùng schema tương thích.

## 17. Hạn chế, rollback và quy tắc giữ nguyên lịch sử

Sau khi tag R1 được áp dụng, việc chèn changeset mới **trước** marker R1 trong changelog đang dùng chung có thể làm thay đổi ý nghĩa “R1 bao gồm những gì” ở các môi trường chưa chạy. Mặt khác, những database đã có marker R1 không tự nhiên áp dụng changeset mới nếu đang chạy theo logic lịch sử/phiên bản khác. Điều này dễ tạo ra sai lệch giữa môi trường.

**Khuyến nghị vận hành:**

- Giữ chuỗi changeset và marker đã phát hành **ổn định**.
- Đưa yêu cầu mới vào **changeset mới** sau marker phù hợp, thay vì viết lại migration cũ.
- Không đổi tên tag hoặc ID/author/đường dẫn của changeset đã chạy tùy tiện.
- Nếu cần cherry-pick/hotfix, thiết kế chiến lược changelog và tag riêng có kiểm chứng, không chỉ di chuyển marker.
- Không dùng **clear-checksums** để bỏ qua lỗi do sửa lịch sử chưa được điều tra.
- Không coi rollback-to-tag là thao tác an toàn mặc định: các changeset chứa data migration, drop column hoặc DDL không hỗ trợ rollback có thể không thể hoàn tác chính xác.

Một lệnh update-to-tag **không hứa hẹn tính nguyên tử toàn bộ release**. Một changeset trước marker có thể đã commit trước khi changeset sau lỗi. Khi triển khai lại, Liquibase dựa vào lịch sử để tiếp tục, nhưng operator vẫn cần đánh giá xem DBMS có để lại thay đổi dở dang trong changeset thất bại hay không.

## 18. Bài thực hành có kiểm chứng

Thực hành trên database tạm riêng, sử dụng changelog mẫu mục 3 và một runtime Liquibase có lệnh update-to-tag được xác minh hỗ trợ.

**Giai đoạn 1 — Lập giả thuyết**

- Liệt kê changeset sẽ chạy tới **release-2026.11.1**.
- Liệt kê changeset sẽ chạy tiếp khi tiến tới **release-2026.11.2**.
- Dự đoán điều gì xảy ra nếu chạy update-to-tag R1 trên database đã vượt R2.
- Phân biệt marker tagDatabase với lệnh tag.

**Giai đoạn 2 — Kiểm tra công cụ và changelog**

- Xác nhận Liquibase version/edition.
- Chạy validate cho changelog mẫu.
- Kiểm tra sự hiện diện của hai marker tagDatabase và thứ tự của chúng.
- Nếu có update-to-tag-sql, xem trước SQL của R1 và xác nhận không có thay đổi thuộc R2.

**Giai đoạn 3 — Cập nhật tới R1**

- Chạy update-to-tag --tag=release-2026.11.1 trên database mới.
- Kiểm tra bảng customer và cột status.
- Xác nhận chưa có bảng customer_audit và chưa có region/internal_note.
- Truy vấn DATABASECHANGELOG để thấy lịch sử chạy tới marker R1.

**Giai đoạn 4 — Cập nhật tới R2**

- Chạy update-to-tag --tag=release-2026.11.2.
- Kiểm tra sự tồn tại của bảng customer_audit và cột region.
- Xác nhận internal_note vẫn chưa được tạo do nằm sau R2.
- Đối chiếu ORDEREXECUTED, TAG và EXECTYPE của lịch sử.

**Giai đoạn 5 — Các thử nghiệm lỗi an toàn**

- Trên database thử nghiệm riêng, yêu cầu một tên tag không tồn tại và ghi lại thông báo lỗi.
- Thử tình huống marker đặt sai vị trí trước khi phát hành, xem vì sao phạm vi không đúng kỳ vọng.
- Nếu môi trường hỗ trợ context/label, kiểm tra một changeset có điều kiện trước marker để hiểu tại sao cùng tag không chứng minh cùng trạng thái schema.
- Không dùng production để thử rollback hoặc các tình huống có khả năng phá dữ liệu.

**Giai đoạn 6 — Đánh giá**

Người học cần trả lời được: **tagDatabase nằm ở đâu trong changelog, update-to-tag giới hạn những gì, những điều kiện nào vẫn có thể khiến changeset trước tag không chạy, và bằng chứng nào chứng minh database thực sự đã đạt trạng thái mong đợi?**

## 19. Checklist review trước khi deploy tới tag

- Đã xác định đúng phiên bản/edition Liquibase và xác nhận lệnh update-to-tag khả dụng?
- Tag đích được định nghĩa bằng **tagDatabase** trong changelog đang dùng, không chỉ bằng lệnh tag runtime?
- Tên tag duy nhất, ổn định và tương ứng chính xác release cần triển khai?
- Marker nằm sau toàn bộ thay đổi được duyệt và trước mọi thay đổi chưa được phép chạy?
- Đã xem lại thứ tự file include, đường dẫn và khả năng ảnh hưởng logicalFilePath?
- Có context/label/dbms/precondition khiến changeset trước tag bị chọn khác nhau giữa các môi trường không?
- Đã đối chiếu DATABASECHANGELOG với trạng thái schema/dữ liệu trước triển khai?
- Đã dùng validate và chế độ preview tương ứng nếu runtime hỗ trợ?
- Đã kiểm chứng trên database có lịch sử và cấu hình gần môi trường thực tế?
- Đã có kế hoạch cho DDL/DML chạy lâu, lock và các migration dữ liệu theo giai đoạn?
- Pipeline có fail-closed khi thiếu tag, sai artifact hoặc sai quyền/edition không?
- Đã kiểm tra rõ update-to-tag **không rollback** database đã vượt mốc?
- Đã chuẩn bị phương án rollback/roll-forward được kiểm chứng độc lập?
- Đã lưu được kết quả cập nhật, tag, commit, phiên bản Liquibase và bằng chứng hậu triển khai?
- Các changeset và marker đã phát hành có được giữ nguyên để bảo toàn lịch sử/checksum không?

**Kết luận:** **update-to-tag** là cách cập nhật Liquibase tới **một ranh giới được khai báo bằng tagDatabase trong changelog**, giúp kiểm soát phạm vi thay đổi thuộc từng release. Lệnh không tự thay thế context/label filter, precondition, quản lý DATABASECHANGELOG hay quy trình rollback. Muốn triển khai an toàn cần đặt marker đúng vị trí, xác nhận runtime hỗ trợ lệnh, review SQL và lịch sử ở đúng database, rồi kiểm chứng schema/dữ liệu thực tế sau khi chạy. Khi kết hợp các bước đó với CI/CD và ứng dụng Spring Boot, mốc tag trở thành một **điểm kiểm soát phát hành có thể truy nguyên**, chứ không chỉ là một nhãn đặt tên cho database.

