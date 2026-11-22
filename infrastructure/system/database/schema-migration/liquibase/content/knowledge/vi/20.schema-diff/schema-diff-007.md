# Lọc schema, loại đối tượng và phạm vi so sánh trong Liquibase

Khi dùng Liquibase để so sánh hai database, kết quả diff có thể chứa hàng trăm khác biệt: bảng hệ thống, schema do extension tạo, bảng archive, view nội bộ, index và những đối tượng chỉ phục vụ một môi trường. Nếu không xác định phạm vi trước, nhóm dễ bỏ sót thay đổi quan trọng giữa biển kết quả hoặc sinh ra changelog có tác động ngoài dự kiến.

Bài học thuộc chương **So sánh lược đồ** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài này tập trung vào cách **chọn schema, loại đối tượng và tập đối tượng được so sánh** khi dùng Liquibase **diff** và **diff-changelog**. Mục tiêu không phải làm cho báo cáo diff càng ngắn càng tốt, mà là làm cho kết quả phản ánh đúng câu hỏi kỹ thuật đang cần trả lời.

Sau bài học, bạn có thể:

1. Phân biệt database, catalog, schema và default schema trong phạm vi so sánh.
2. Xác định đúng **reference database** và **target database**, không đảo chiều.
3. Chọn schema cần so sánh ở mỗi phía, kể cả khi tên schema khác nhau.
4. Giới hạn loại đối tượng bằng **diff-types** và lọc đối tượng bằng **include-objects / exclude-objects** theo phiên bản hỗ trợ.
5. Hiểu giới hạn của diff đối với dữ liệu, quyền, routine, extension và đặc tính riêng của DBMS.
6. Đọc báo cáo diff, kiểm tra tập đối tượng bị bỏ qua và tạo diff-changelog an toàn.
7. Xây dựng quy trình so sánh có thể lặp lại trong CI/CD và nhiều môi trường.

## 1. Vì sao phải kiểm soát phạm vi so sánh?

Một database thực tế hiếm khi chỉ có các bảng nghiệp vụ mà ứng dụng tự tạo. Nó có thể chứa:

- Schema mặc định của ứng dụng.
- Schema phục vụ audit, báo cáo hoặc tích hợp.
- Schema của extension và công cụ quản trị.
- Bảng tạm, bảng staging hoặc archive.
- View, materialized view, sequence, function, procedure và trigger.
- Các đối tượng do DBA tạo thủ công.
- Bảng metadata của Liquibase như **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK**.
- Những đối tượng riêng theo môi trường hoặc theo khách hàng.

Nếu so sánh toàn bộ mà không lọc, báo cáo có thể quá nhiễu. Nếu lọc quá chặt, một cột hoặc constraint quan trọng có thể bị bỏ qua.

**Phạm vi so sánh là một phần của định nghĩa kiểm thử.** Một kết luận “hai database không có khác biệt” chỉ có ý nghĩa khi biết rõ schema nào, loại đối tượng nào và quy tắc include/exclude nào đã được áp dụng.

### 1.1. Ba trục lọc chính

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| **Schema scope** | So sánh namespace nào ở reference và target? | public, app, reporting |
| **Object type scope** | Quan tâm loại đối tượng nào? | tables, columns, indexes, views |
| **Object name scope** | Quan tâm hoặc loại trừ đối tượng cụ thể nào? | chỉ bảng orders, bỏ bảng *_archive |

Ba trục này bổ sung cho nhau. Chọn schema **public** không đồng nghĩa chỉ so sánh bảng; trong schema đó vẫn có thể có view, sequence, routine và nhiều loại đối tượng khác tùy DBMS và khả năng Liquibase.

## 2. Phân biệt database, catalog và schema

Trước khi lọc, cần hiểu namespace mà DBMS sử dụng.

| Khái niệm | Ý nghĩa tổng quát | Ví dụ |
|---|---|---|
| **Database** | Một đơn vị database được kết nối | orders_prod |
| **Catalog** | Namespace cấp cao hơn hoặc tập metadata theo DBMS | catalog trong một số hệ quản trị |
| **Schema** | Namespace chứa bảng, view, routine và các đối tượng | public, sales, reporting |
| **Object** | Một đối tượng cụ thể trong schema | sales.orders, sales.idx_orders_created |

Cách phân cấp không giống nhau giữa PostgreSQL, MySQL, Oracle và SQL Server. Ví dụ:

- PostgreSQL có database riêng, bên trong có nhiều schema như public và reporting.
- MySQL thường dùng database và schema gần như đồng nghĩa trong nhiều thao tác.
- SQL Server có database và schema như dbo, sales.
- Oracle có schema gắn với user và các đối tượng thuộc schema đó.

Vì vậy, không sao chép nguyên tên tham số hoặc giả định namespace của DBMS này sang DBMS khác mà chưa kiểm tra.

### 2.1. Default schema có thể làm thay đổi kết quả

Nếu không chỉ định schema rõ ràng, công cụ có thể sử dụng **default schema** của connection hoặc cấu hình Liquibase. Hai connection cùng trỏ đến một database nhưng có default schema khác nhau có thể tạo phạm vi so sánh khác nhau.

Trước khi diff, xác nhận:

- Database/service thực tế.
- Username.
- Default schema.
- Schema metadata của Liquibase.
- Schema cần so sánh.
- Những schema hệ thống cần loại trừ.

Đừng suy ra schema đích từ tên profile Spring Boot hoặc tên thư mục changelog.

## 3. Reference và target quyết định chiều so sánh

Liquibase diff cần hai đầu vào:

- **Reference:** nguồn chuẩn hoặc trạng thái mong muốn để so sánh.
- **Target:** database được đối chiếu với reference.

Ví dụ, nhóm muốn biết production có khác schema chuẩn trong staging đã được phê duyệt hay không:

~~~text
Reference: schema chuẩn đã được review
Target:   production cần kiểm tra
~~~

Nếu muốn tạo changelog đưa target về gần reference, chiều này rất quan trọng. **diff-changelog** tạo thay đổi dựa trên chênh lệch theo hướng reference/target được cấu hình. Đảo hai phía có thể sinh changelog theo hướng ngược lại.

### 3.1. Ví dụ kết nối

Cú pháp minh họa:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --reference-username="schema_reader" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --username="schema_reader" \
  diff
~~~

Password nên lấy từ secret manager hoặc cấu hình được bảo vệ, không viết trực tiếp vào command line/log.

Ở đây reference là **orders_model**, target là **orders**. Khi đọc kết quả, luôn hỏi khác biệt đang mô tả đối tượng thiếu ở phía nào. Đừng chỉ thấy tên bảng trong output rồi mặc định target cần tạo bảng đó.

### 3.2. Cách ghi nhớ chiều diff-changelog

Giả sử:

- Reference có bảng **orders**.
- Target chưa có bảng **orders**.

Một diff có thể báo bảng tồn tại ở reference nhưng không tồn tại ở target. Diff-changelog theo chiều này có thể tạo changeset để **target** có thêm bảng tương ứng.

Nếu đảo reference và target, changelog được sinh có thể mô tả thao tác ngược lại. Vì vậy, trước khi sinh changelog, viết rõ bằng văn bản: **“Tôi muốn đưa target về gần trạng thái reference.”**

## 4. Lọc schema ở hai phía

Liquibase hỗ trợ cấu hình schema cần so sánh thông qua các tham số schema dành cho reference và target. Tên tham số thường gặp trong CLI gồm:

- **--reference-schemas**: schema cần xem xét ở reference.
- **--schemas**: schema cần xem xét ở target.

Khả năng và tên option phải được xác nhận bằng phiên bản Liquibase đang dùng. Một số phiên bản hoặc loại lệnh có thể có cách cấu hình namespace khác.

Ví dụ:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --reference-schemas=app,reporting \
  --schemas=app,reporting \
  diff
~~~

Mục tiêu ví dụ là so sánh schema **app** và **reporting** ở cả hai phía. Nếu hai database dùng tên schema khác nhau, cần xác định cách ánh xạ/đối chiếu phù hợp thay vì giả định hai tên khác nhau sẽ tự được coi là cùng namespace.

### 4.1. Reference và target có tên schema khác nhau

Giả sử:

~~~text
Reference: orders_model.app
Target:    orders_prod.sales
~~~

Về nghiệp vụ, hai schema có thể chứa cùng một mô hình dữ liệu nhưng tên namespace khác. Trước khi so sánh, cần xác minh Liquibase có hỗ trợ cách ánh xạ schema theo cấu hình/phiên bản hiện tại hay không.

Không tự động đổi tên object hoặc schema trong output để ép báo cáo trông giống nhau. Cần xác định:

- Schema nào là nguồn chuẩn.
- Schema nào là đích.
- Có chủ ý giữ tên khác nhau không.
- Công cụ có xem chúng là các namespace riêng không.
- Diff-changelog có sinh lệnh CREATE/DROP ngoài dự kiến không.

### 4.2. Schema metadata Liquibase không phải schema nghiệp vụ

Các bảng **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK** có thể nằm trong schema metadata riêng. Khi so sánh schema ứng dụng, thường không muốn coi chúng là đối tượng nghiệp vụ.

Tuy nhiên, không loại trừ chúng bằng một bộ lọc quá rộng nếu mục tiêu là kiểm tra chính việc cấu hình Liquibase. Phạm vi phải dựa trên câu hỏi kiểm tra, không dựa trên quy tắc “luôn bỏ qua schema metadata”.

## 5. Lọc theo loại đối tượng bằng diff-types

Sau khi chọn schema, có thể giới hạn **loại đối tượng** mà Liquibase so sánh. Tham số thường gặp là **--diff-types** với danh sách loại được phân tách bằng dấu phẩy.

Ví dụ minh họa:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes,uniqueconstraints,views,sequences \
  diff
~~~

Danh sách loại đối tượng hợp lệ và tên gọi chính xác phụ thuộc phiên bản Liquibase, edition và DBMS. Hãy kiểm tra **help** và tài liệu đúng phiên bản trước khi dùng trong automation.

### 5.1. Những loại đối tượng thường quan tâm

| Loại | Câu hỏi kiểm tra |
|---|---|
| **tables** | Bảng nào thiếu hoặc khác? |
| **columns** | Kiểu dữ liệu, nullability, default có khớp? |
| **primarykeys** | Khóa chính có đúng cột và cấu hình? |
| **foreignkeys** | Quan hệ tham chiếu có đủ? |
| **uniqueconstraints** | Quy tắc duy nhất có tồn tại? |
| **indexes** | Index có đúng tên, cột và đặc tính? |
| **views** | View có được định nghĩa và cập nhật? |
| **sequences** | Sequence có tồn tại và đúng cấu hình? |
| **stored logic/routines** | Function, procedure hoặc logic lưu trong DB có được hỗ trợ so sánh? |
| **data** | Có cần so sánh dữ liệu trong phạm vi được hỗ trợ? |

Không phải mọi phiên bản hoặc DBMS đều hỗ trợ mọi loại. Một số đối tượng có thể được phát hiện nhưng chỉ so sánh một phần thuộc tính. Hãy đọc tài liệu hỗ trợ và kiểm tra kết quả trên database thực tế.

### 5.2. Vì sao nên chọn loại đối tượng rõ ràng?

Ví dụ mục tiêu chỉ kiểm tra cấu trúc bảng trong một pull request. Có thể chọn tables, columns, primary keys, foreign keys và indexes. Khi đó thay đổi quyền, routine hoặc dữ liệu không nằm trong câu hỏi kiểm tra.

Ngược lại, nếu mục tiêu là kiểm toán toàn diện, bỏ qua views hoặc sequences có thể che giấu khác biệt quan trọng. Không dùng diff-types quá hẹp rồi kết luận **toàn bộ schema giống nhau**.

## 6. Lọc đối tượng bằng include-objects và exclude-objects

Ngoài schema và loại đối tượng, Liquibase có thể hỗ trợ lọc theo **tên/định danh đối tượng** thông qua các tham số như:

- **--include-objects**
- **--exclude-objects**

Các bộ lọc này thường sử dụng biểu thức/pattern theo cú pháp mà phiên bản hỗ trợ. Cần kiểm tra tài liệu của đúng phiên bản, đặc biệt cách chỉ định object type, tên schema và dấu phân cách.

Ví dụ dạng minh họa:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --schemas=app \
  --reference-schemas=app \
  --include-objects="table:orders,table:order_item" \
  diff
~~~

Mục tiêu là chỉ tập trung vào hai bảng quan trọng nếu cú pháp include filter của phiên bản đang dùng chấp nhận biểu thức đó. **Đây là mẫu minh họa cần xác nhận**, không phải cam kết cú pháp đồng nhất trên mọi bản Liquibase.

Ví dụ exclude:

~~~bash
liquibase \
  --schemas=app \
  --reference-schemas=app \
  --exclude-objects="table:.*_archive" \
  diff
~~~

Ý định là loại những bảng có hậu tố archive khỏi phạm vi so sánh, nếu pattern syntax và object naming của phiên bản hỗ trợ đúng như mong muốn.

### 6.1. Include và exclude khác nhau thế nào?

| Bộ lọc | Mục tiêu |
|---|---|
| **include-objects** | Chỉ đưa những đối tượng khớp điều kiện vào phạm vi |
| **exclude-objects** | Loại những đối tượng khớp điều kiện khỏi phạm vi |

Khi dùng đồng thời, cần kiểm tra thứ tự ưu tiên và quy tắc tương tác của phiên bản Liquibase. Không giả định include luôn thắng exclude hoặc ngược lại nếu chưa xác minh.

### 6.2. Pattern quá rộng gây hậu quả gì?

Ví dụ:

~~~text
table:.*order.*
~~~

Có thể khớp cả:

- orders
- order_item
- order_audit
- archived_order
- reporting_order_summary

Nếu chỉ muốn **orders** và **order_item**, nên dùng pattern chặt hơn theo cú pháp hỗ trợ. Luôn xem kết quả diff và đối chiếu danh sách đối tượng thực tế trước khi sinh changelog.

### 6.3. Đừng lọc chỉ vì kết quả có nhiều khác biệt

Nếu bảng archive hoặc schema reporting có khác biệt ngoài dự kiến, câu hỏi cần trả lời là **khác biệt đó có thuộc phạm vi được quản lý không**. Loại bỏ bằng exclude-objects có thể che giấu drift thật.

Ghi lại lý do mỗi nhóm đối tượng bị bỏ qua, người phê duyệt và thời hạn xem xét lại nếu ngoại lệ chỉ có hiệu lực tạm thời.

## 7. Kết hợp schema, diff-types và object filters

Ba trục lọc có thể được dùng đồng thời.

Ví dụ mục tiêu: chỉ kiểm tra bảng và index trong schema **app**, bỏ qua bảng archive.

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,indexes,primarykeys,foreignkeys \
  --exclude-objects="table:.*_archive" \
  diff
~~~

Trước khi chạy trong CI, xác nhận:

1. Schema **app** có tồn tại ở cả hai phía.
2. Reference và target đúng chiều.
3. diff-types được hỗ trợ.
4. Pattern archive khớp đúng những đối tượng cần bỏ.
5. Không có đối tượng nghiệp vụ quan trọng vô tình bị loại.
6. Kết quả diff hiển thị đúng tập đối tượng mong muốn.

**Phạm vi thực tế là giao của các điều kiện được áp dụng theo quy tắc của Liquibase**, nhưng chi tiết thứ tự filter và cách xử lý namespace phải được kiểm tra bằng phiên bản đang dùng.

## 8. Phân biệt object filter với precondition và changelog filter

Đây là những lớp khác nhau:

| Cơ chế | Tác động ở đâu? | Mục đích |
|---|---|---|
| **diff schema/object filters** | Trong thao tác so sánh | Chọn đối tượng được đưa vào báo cáo diff |
| **context / label filter** | Khi Liquibase chọn changeset để thực thi hoặc xét trong lệnh liên quan | Chọn nhóm migration |
| **precondition** | Trước khi một changeset được thực thi/đánh giá theo command | Kiểm tra giả định schema/data |
| **dbms** | Chọn changeset theo loại database | Tránh chạy SQL không phù hợp DBMS |

Một object bị loại khỏi diff không có nghĩa changeset tạo nó sẽ bị loại khỏi update. Ngược lại, label filter không tự động giới hạn diff theo những bảng mang label tương ứng.

**Đừng dùng diff filter như một cơ chế bảo vệ update.** Diff và update là hai hoạt động khác nhau.

## 9. Default schema, liquibase schema và schema nghiệp vụ

Một kết quả diff sai thường bắt nguồn từ cấu hình namespace hơn là từ bản thân object.

Ví dụ PostgreSQL:

~~~text
Database: orders
  public
    orders
    customer
  reporting
    customer_summary
  liquibase_meta
    DATABASECHANGELOG
    DATABASECHANGELOGLOCK
~~~

Các vai trò:

- **public/app/reporting**: schema nghiệp vụ hoặc tích hợp.
- **liquibase_meta**: nơi lưu metadata của Liquibase nếu được cấu hình riêng.
- **default schema**: schema mặc định mà connection hoặc Liquibase dùng khi object không ghi rõ schema.
- **reference schema/target schema**: phạm vi schema được chọn cho mỗi phía diff.

Nếu reference có default schema **app** nhưng target default schema **public**, một lệnh không chỉ định schema có thể cho kết quả khác mong đợi.

### 9.1. Tránh dùng schemaName không nhất quán

Trong changelog:

~~~yaml
- createTable:
    schemaName: app
    tableName: orders
    columns:
      - column:
          name: id
          type: bigint
~~~

Nếu diff được giới hạn ở **public**, bảng app.orders sẽ không nằm trong phạm vi. Điều này không có nghĩa Liquibase không biết bảng tồn tại; nó chỉ nằm ngoài câu hỏi đang so sánh.

### 9.2. Metadata schema có cần so sánh không?

Nếu mục tiêu là so sánh schema nghiệp vụ, thường không đưa metadata Liquibase vào cùng phạm vi. Nếu mục tiêu là kiểm tra khả năng vận hành Liquibase, cần kiểm tra riêng các bảng metadata, quyền và cấu hình schema của chúng.

Không nên vừa loại bỏ liquibase_meta khỏi diff vừa kết luận **toàn bộ database đã đồng nhất**. Kết luận phải nêu phạm vi.

## 10. Đối tượng hệ thống và schema do extension tạo

Nhiều DBMS có schema/catalog dành cho hệ thống hoặc extension. Ví dụ PostgreSQL có các schema hệ thống như **pg_catalog** và **information_schema**; một số extension có schema riêng.

Trong ứng dụng, không phải mọi schema đều thuộc phạm vi migration. Nhưng không nên loại trừ toàn bộ schema ngoài public mà không kiểm kê.

Cách làm:

1. Liệt kê schema và chủ sở hữu.
2. Xác định schema do DBMS tạo.
3. Xác định schema do extension/công cụ tạo.
4. Xác định schema do ứng dụng hoặc DBA quản lý.
5. Chọn phạm vi theo ownership và trách nhiệm triển khai.
6. Ghi lý do exclude và cách kiểm tra riêng nếu cần.

Một schema extension có thể chứa function hoặc type mà ứng dụng phụ thuộc. Loại khỏi diff không đồng nghĩa có thể bỏ qua dependency khi dựng database mới.

## 11. Những loại đối tượng diff có thể không so sánh đầy đủ

Một báo cáo diff không phải lúc nào cũng là bản kiểm kê hoàn chỉnh mọi metadata. Tùy DBMS và phiên bản, có thể gặp giới hạn với:

- Trigger và stored logic.
- Function/procedure body.
- Package hoặc module.
- Materialized view.
- Partitioning và partition bound.
- Synonym, extension và custom type.
- Quyền, role, grant và owner.
- Tablespace, storage option và physical attribute.
- Index đặc thù như partial, expression, operator class hoặc online option.
- Check constraint có biểu thức phức tạp.
- Sequence value hiện tại.
- Data ngoài phạm vi diff data được hỗ trợ.

Nếu đối tượng quan trọng không được hỗ trợ, cần kiểm tra bằng catalog hoặc script đặc thù DBMS. Không diễn giải **diff không báo khác biệt** thành **mọi đối tượng hoàn toàn giống nhau**.

### 11.1. Dữ liệu và schema là hai phạm vi riêng

Diff schema thường tập trung vào cấu trúc. Nếu cần so sánh dữ liệu, phải xác định loại dữ liệu, bảng, khóa, cách chuẩn hóa và phạm vi an toàn.

Ví dụ dữ liệu giao dịch có thể khác tự nhiên giữa staging và production; so sánh toàn bộ row có thể tạo báo cáo nhiễu hoặc lộ thông tin nhạy cảm. Thường chỉ so sánh **reference data** hoặc tập dữ liệu được phê duyệt.

## 12. So sánh theo loại đối tượng để trả lời câu hỏi cụ thể

Không có một diff-types duy nhất phù hợp mọi tình huống.

| Câu hỏi | Phạm vi có thể chọn |
|---|---|
| Bảng/cột có giống nhau không? | tables, columns |
| Constraint có đủ không? | primarykeys, foreignkeys, uniqueconstraints và loại hỗ trợ |
| Index có khác không? | indexes |
| View có được cập nhật không? | views |
| Sequence có cấu hình phù hợp không? | sequences |
| Routine có thay đổi không? | loại stored logic nếu phiên bản hỗ trợ, cộng kiểm tra catalog |
| Toàn bộ schema nghiệp vụ có khác không? | Tập loại đối tượng rộng đã được xác minh |
| Reference data có khác không? | data và bảng được chỉ định, nếu phiên bản/cấu hình hỗ trợ |

Một câu hỏi cụ thể nên dẫn tới một bộ lọc cụ thể, nhưng báo cáo phải nói rõ phạm vi đã bỏ qua. Ví dụ: “Diff tables/columns/indexes trong app; không bao gồm data, grants và stored logic.”

## 13. Ví dụ: chỉ so sánh bảng orders và order_item

Giả sử database reference là schema mô hình đã duyệt; target là database staging. Nhóm chỉ muốn kiểm tra hai bảng trọng tâm trong đợt phát hành.

Mẫu CLI:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://staging.internal:5432/orders" \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes \
  --include-objects="table:orders,table:order_item" \
  diff
~~~

Trước khi sử dụng, kiểm tra syntax object filter của bản Liquibase thực tế. Nếu cú pháp include pattern không khớp định dạng được hỗ trợ, công cụ có thể báo lỗi hoặc chọn phạm vi không như mong đợi.

Sau khi chạy, review:

- Báo cáo chỉ chứa orders và order_item hay không.
- Foreign key giữa hai bảng có được đưa vào phạm vi không.
- Index và constraint có xuất hiện đầy đủ không.
- Có dependency tới bảng khác bị bỏ qua không.
- Tên schema và object có đúng case/quoting không.

**Lưu ý:** chỉ chọn hai bảng có thể làm mất ngữ cảnh của foreign key tham chiếu tới bảng thứ ba. Nếu relationship là một phần của câu hỏi, mở rộng include scope hoặc kiểm tra dependency riêng.

## 14. Ví dụ: loại bảng archive nhưng vẫn so sánh các đối tượng khác

Một hệ thống lưu archive trong cùng schema app:

~~~text
app.orders
app.order_item
app.orders_2024_archive
app.orders_2025_archive
app.customer
~~~

Nếu mục tiêu là so sánh cấu trúc ứng dụng đang hoạt động, nhóm có thể loại những bảng archive đã được xác nhận không còn thuộc hợp đồng triển khai:

~~~bash
liquibase \
  --reference-schemas=app \
  --schemas=app \
  --exclude-objects="table:.*_archive" \
  diff
~~~

Nhưng cần xác minh:

- Pattern có khớp chỉ bảng hay cả tên đối tượng khác.
- Có view hoặc routine phụ thuộc bảng archive không.
- Bảng archive có cần được tạo trong môi trường mới không.
- Dữ liệu archive có nằm trong retention hoặc audit requirement không.

Nếu database mới phải tái tạo cả archive schema, loại chúng khỏi diff ứng dụng có thể hợp lý cho một kiểm tra cụ thể, nhưng cần một bài kiểm tra khác đảm bảo khả năng dựng mới.

## 15. Sinh diff-changelog sau khi đã giới hạn phạm vi

**diff-changelog** tạo changelog từ khác biệt giữa reference và target. Trước khi chạy, phạm vi schema, diff-types và object filter phải được cố định.

Ví dụ:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders" \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes,views \
  --exclude-objects="table:.*_archive" \
  --changelog-file=db/changelog/generated/target-to-reference.yaml \
  diff-changelog
~~~

Ý định: tạo changelog để đưa target gần trạng thái reference trong phạm vi được chọn. Tên option output và command có thể khác theo phiên bản; xác nhận với help và tài liệu đúng bản.

### 15.1. Không chạy ngay changelog được sinh

Output diff-changelog là **bản nháp cần review**. Nó có thể:

- Sinh CREATE/DROP/ALTER dựa trên khác biệt quan sát.
- Bỏ qua những thuộc tính không được hỗ trợ.
- Tạo SQL phụ thuộc DBMS.
- Chứa thứ tự thay đổi cần điều chỉnh theo dependency.
- Không có rollback đủ an toàn.
- Đưa ra thay đổi đúng về cấu trúc nhưng sai về nghiệp vụ.

Trước update, phải review từng changeset, precondition, SQL, rollback và tác động dữ liệu.

### 15.2. Diff-changelog có thể đề xuất xóa đối tượng

Nếu reference không có bảng nhưng target có, diff-changelog theo chiều target-to-reference có thể tạo thay đổi xóa bảng ở target. Điều đó có thể đúng với mục tiêu đồng bộ schema nhưng phá hủy dữ liệu.

Không sinh changelog từ production rồi áp dụng chỉ vì diff output có vẻ hợp lý. Mọi DROP/DELETE hoặc thay đổi phá hủy cần phê duyệt và kế hoạch backup/forward fix.

## 16. Lọc đối tượng không thay thế việc đọc diff report

Một bộ lọc chính xác vẫn có thể tạo kết quả sai nếu reference/target, schema mapping hoặc object naming không đúng.

Khi đọc report, hãy ghi lại:

- Database reference và target.
- Schema ở từng phía.
- diff-types được dùng.
- Include/exclude patterns.
- Liquibase version và DBMS version.
- Những object type không được hỗ trợ hoặc không đưa vào.
- Tổng số object được so sánh nếu công cụ cung cấp.
- Các khác biệt quan trọng theo nhóm.
- Những khác biệt được chấp nhận và lý do.

Một báo cáo chỉ có tiêu đề **No differences found** mà không kèm phạm vi so sánh là bằng chứng yếu.

## 17. Phạm vi và schema mapping khi tên khác nhau

Một vấn đề thường gặp khi so sánh database đã chuẩn hóa tên schema khác nhau:

~~~text
Reference: app.orders
Target:    sales.orders
~~~

Nếu mục tiêu là so sánh cấu trúc của hai namespace có ý nghĩa tương đương, phải xem khả năng **schema mapping** hoặc các tham số reference/target schema của phiên bản Liquibase đang dùng.

Không tự đặt:

~~~text
--reference-schemas=app
--schemas=sales
~~~

rồi mặc định kết quả sẽ coi app và sales là cùng schema logic. Tùy công cụ, chúng có thể được so sánh như hai namespace khác nhau hoặc không được ánh xạ như mong đợi.

Hãy thử với một database nhỏ có một bảng, một index và một constraint để xác nhận hành vi trước khi áp dụng trên toàn schema.

### 17.1. Phân biệt schema selection và schema mapping

- **Selection:** chọn schema nào được đưa vào so sánh.
- **Mapping:** xác định schema bên reference tương ứng schema nào bên target.

Hai việc này không giống nhau. Một option chỉ chọn schema không nhất thiết thực hiện mapping. Nếu Liquibase version không hỗ trợ mapping cần thiết, có thể phải chuẩn hóa tên schema trong database thử nghiệm hoặc dùng công cụ/kiểm tra bổ sung.

## 18. Case sensitivity, quoting và tên đối tượng

DBMS xử lý chữ hoa/thường và định danh có quote khác nhau.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE public.orders (...);
CREATE TABLE public."OrderHistory" (...);
~~~

Tên **orders** và **"OrderHistory"** có quy tắc case khác nhau. Khi lọc object bằng regex/pattern, cần hiểu cách Liquibase đọc tên và cách DBMS chuẩn hóa định danh.

Kiểm tra:

- Tên có được quote không.
- Tên object có chữ hoa hoặc ký tự đặc biệt không.
- Pattern filter có phân biệt case không theo implementation.
- Schema/object name có cần escape ký tự regex không.
- Catalog output có hiển thị tên đã chuẩn hóa không.

Không dùng regex rộng rồi cho rằng tên có quote sẽ luôn được match theo dạng bạn nhìn thấy trong SQL.

## 19. Quyền truy cập có ảnh hưởng đến diff

Liquibase chỉ có thể so sánh metadata mà user kết nối có quyền đọc và driver/DBMS cho phép truy cập.

Nếu user không nhìn thấy một object, diff có thể không phản ánh nó như mong đợi. Một kết quả “không có khác biệt” có thể do:

- Reference user thiếu quyền metadata.
- Target user thiếu quyền đọc catalog.
- Một schema không nằm trong search path hoặc scope.
- View/function bị ẩn bởi quyền.
- Driver trả metadata không đầy đủ.

Nên sử dụng principal có quyền đọc schema cần so sánh ở cả hai phía, nhưng không cần cấp quyền DDL nếu chỉ chạy diff.

### 19.1. Đừng dùng user khác nhau mà không ghi nhận

Nếu reference dùng admin user còn target dùng user ứng dụng hạn chế quyền, kết quả có thể không so sánh cùng một tập đối tượng. Để kết luận đáng tin cậy, dùng quyền đọc metadata tương đương hoặc tài liệu hóa rõ chênh lệch quyền.

## 20. Lọc schema hệ thống và đối tượng nội bộ

Một số schema không thuộc ứng dụng nhưng vẫn có thể ảnh hưởng tới kết quả. Ví dụ:

- PostgreSQL: pg_catalog, information_schema và schema extension.
- SQL Server: các schema hệ thống và schema do công cụ tạo.
- Oracle: schema của hệ thống hoặc sản phẩm.
- MySQL: database hệ thống và metadata.

Không nên đưa tất cả schema hệ thống vào diff ứng dụng. Nhưng cũng không nên exclude rộng đến mức bỏ qua schema extension mà ứng dụng phụ thuộc.

Tạo một danh sách ownership:

| Schema | Chủ sở hữu | Có trong diff ứng dụng? | Kiểm tra riêng |
|---|---|---|---|
| app | Nhóm ứng dụng | Có | Liquibase diff |
| reporting | Nhóm dữ liệu | Theo mục tiêu | Diff riêng |
| liquibase_meta | Nhóm nền tảng | Thường không | Kiểm tra metadata riêng |
| extension_x | DBA/nền tảng | Tùy dependency | Kiểm tra extension/version |
| system schemas | DBMS | Không trong diff ứng dụng | Theo dõi bằng công cụ DBMS |

Đây là ví dụ phân loại, không phải quy tắc mặc định cho mọi tổ chức.

## 21. Data diff: khi nào nên đưa dữ liệu vào phạm vi?

Một số phiên bản/edition và cấu hình Liquibase hỗ trợ so sánh dữ liệu cho những loại bảng và khóa phù hợp. Nếu dùng **data** trong diff-types, cần xác định:

- Bảng nào được so sánh.
- Khóa chính/unique key nào dùng để ghép hàng.
- Dữ liệu nào là reference data.
- Cột nào cần bỏ qua hoặc chuẩn hóa.
- Có dữ liệu nhạy cảm không.
- Thứ tự hàng và kiểu dữ liệu được so sánh thế nào.
- Có giới hạn hiệu năng hoặc khối lượng không.

Không nên so sánh toàn bộ bảng giao dịch production với staging rồi xem mọi khác biệt là lỗi. Hai môi trường có dữ liệu vận hành khác nhau theo thiết kế.

### 21.1. Chỉ so sánh dữ liệu có hợp đồng ổn định

Ví dụ phù hợp hơn:

- Danh mục quốc gia hoặc tiền tệ chuẩn.
- Bảng mã trạng thái dùng chung.
- Bảng cấu hình hệ thống được quản lý qua migration.

Ví dụ không phù hợp để diff dữ liệu trực tiếp nếu không có chính sách:

- Giao dịch khách hàng.
- Nhật ký audit.
- Dữ liệu cá nhân.
- Bảng sự kiện thay đổi liên tục.

Với dữ liệu nhạy cảm, chỉ dùng dữ liệu giả lập/ẩn danh hóa và quyền truy cập được phê duyệt.

## 22. Diff và baseline database legacy

Khi tiếp nhận database legacy, phạm vi diff phải được xác định trước khi dùng **generate-changelog**, **diff** hoặc **diff-changelog**.

Một quy trình:

1. Kiểm kê schema và ownership.
2. Chọn schema nghiệp vụ được quản lý.
3. Chọn loại đối tượng cần quản lý bằng Liquibase.
4. Loại trừ có chủ đích các đối tượng hệ thống/nội bộ.
5. Generate changelog hoặc xây baseline.
6. Diff reference/target theo chiều đã xác định.
7. Điều tra mọi khác biệt.
8. Chỉ sau khi baseline tương đương mới dùng changelog-sync.

**Changelog-sync không thay thế diff.** Nó không xác minh rằng bảng/cột/index hiện tại khớp với changelog; nó chỉ ghi nhận changeset trong phạm vi lệnh.

### 22.1. Không bỏ qua đối tượng chỉ vì Liquibase khó so sánh

Nếu function, trigger hoặc index đặc thù không được diff đầy đủ, hãy kiểm tra bằng catalog/DDL script và đưa vào quy trình review riêng. Một baseline có thể gồm change type Liquibase và SQL tùy chỉnh theo DBMS, miễn là được kiểm thử trên database mới và database legacy.

## 23. Tích hợp vào CI/CD

Một pipeline diff có thể hoạt động như quality gate trước khi merge hoặc triển khai.

~~~text
1. Chọn reference và target có chủ đích.
2. Xác nhận database/schema và user ở hai phía.
3. Nạp cấu hình schema scope.
4. Chọn diff-types theo câu hỏi kiểm tra.
5. Áp dụng include/exclude object filters.
6. Chạy diff.
7. Lưu báo cáo cùng metadata phạm vi.
8. Review khác biệt quan trọng.
9. Nếu sinh diff-changelog, review toàn bộ SQL và rollback.
10. Chạy validate, update-sql và thử trên database cách ly.
~~~

### 23.1. Không biến diff thành gate mù

Một pipeline có thể fail khi có bất kỳ khác biệt nào, nhưng chỉ hợp lý nếu:

- Reference là artifact/schema chuẩn ổn định.
- Target là database được kiểm soát.
- Filter không bỏ qua đối tượng cần kiểm tra.
- Những khác biệt có chủ đích được quản lý bằng allowlist có review.
- Output có thể tái lập theo cùng Liquibase version/driver.

Nếu mỗi môi trường có schema mở rộng hợp lệ riêng, gate “diff phải rỗng” sẽ liên tục báo lỗi giả. Cần định nghĩa rõ phần schema chung và phần extension riêng.

### 23.2. Lưu bằng chứng so sánh

Nên lưu:

- Reference/target identifiers đã được ẩn thông tin nhạy cảm.
- Liquibase version và DBMS/driver.
- Schema list của hai phía.
- diff-types.
- Include/exclude patterns.
- Kết quả diff.
- Commit hash hoặc artifact changelog.
- Thời điểm, pipeline run ID và người phê duyệt.
- Những object type không được so sánh.

Không lưu password hoặc dữ liệu hàng nhạy cảm trong artifact diff.

## 24. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Diff báo quá nhiều schema | Chưa giới hạn schema hoặc default schema sai | Xác nhận endpoint/default schema và dùng schema scope rõ |
| Không thấy bảng quan trọng | Schema/table bị loại khỏi filter hoặc thiếu quyền | Kiểm tra schema list, include/exclude và quyền catalog |
| Diff báo mọi object khác nhau khi tên schema khác | Reference/target không được mapping như mong đợi | Xác minh schema mapping; thử trên database nhỏ |
| Diff không báo khác biệt nhưng object thực tế khác | Object type không được chọn/hỗ trợ hoặc user không nhìn thấy | Mở rộng diff-types, kiểm tra catalog và quyền |
| Diff-changelog sinh DROP TABLE | Chiều reference/target hoặc schema scope không đúng | Dừng, xác minh chiều và review tác động dữ liệu |
| Include filter không chọn đúng bảng | Regex/object filter syntax không khớp phiên bản | Kiểm tra help/tài liệu, thử pattern đơn giản |
| Exclude pattern loại quá nhiều | Regex quá rộng hoặc match sai object type | Thu hẹp pattern, đối chiếu danh sách object |
| Diff giữa hai lần chạy không ổn định | Schema thay đổi đồng thời hoặc filter khác | Chụp snapshot/đóng băng thay đổi, cố định cấu hình |
| View/routine không xuất hiện | Loại object không hỗ trợ đầy đủ hoặc thiếu quyền | Kiểm tra catalog và script DBMS riêng |
| Chỉ khác metadata Liquibase | Metadata schema bị đưa vào phạm vi | Tách schema metadata khỏi diff nghiệp vụ nếu phù hợp |
| Dữ liệu khác quá nhiều | Đưa operational data vào data diff | Giới hạn reference data và bảng được phép |
| SQL diff-changelog không chạy trên target | DBMS dialect hoặc feature không tương thích | Review SQL, thử đúng DBMS/driver |
| Kết quả thiếu index đặc thù | Driver/DBMS không biểu diễn đầy đủ thuộc tính | Kiểm tra catalog/DDL và test riêng |
| Pipeline diff fail dù thay đổi hợp lệ | Không có chính sách allowlist/extension | Phân loại khác biệt và quản lý ngoại lệ có review |

## 25. Bài thực hành: giới hạn diff vào schema app

**Bối cảnh:** có hai database PostgreSQL thử nghiệm:

~~~text
Reference database: orders_model
Target database:    orders_test

Mỗi database có:
  app.orders
  app.order_item
  app.customer
  reporting.customer_summary
  liquibase_meta.DATABASECHANGELOG
~~~

Yêu cầu: chỉ kiểm tra cấu trúc bảng và index trong schema **app**, bỏ qua schema reporting và liquibase_meta trong bài diff này.

### 25.1. Xác nhận kết nối và schema

Chạy trên từng database bằng connection tương ứng:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_user;
~~~

Liệt kê schema:

~~~sql
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;
~~~

Xác nhận schema **app** tồn tại và user đọc được metadata.

### 25.2. Chạy diff theo phạm vi

Mẫu CLI (cần xác nhận option trên phiên bản Liquibase của dự án):

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://target.internal:5432/orders_test" \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes \
  diff
~~~

### 25.3. Đọc kết quả

Ghi nhận:

- Có những bảng nào được so sánh?
- Có cột nào thiếu hoặc sai kiểu?
- Primary key/foreign key có khớp không?
- Index có thiếu hoặc định nghĩa khác không?
- View reporting có xuất hiện không? Nếu không, có đúng phạm vi yêu cầu không?
- DATABASECHANGELOG có xuất hiện không? Nếu không, có đúng vì schema metadata nằm ngoài phạm vi không?

### 25.4. Mở rộng kiểm tra

Chạy một lần diff riêng cho schema **reporting** và chọn **views** nếu loại đối tượng được hỗ trợ. So sánh kết quả để hiểu vì sao một lần diff giới hạn app không thể chứng minh reporting đã đồng nhất.

**Không chạy diff-changelog rồi update tự động** trong bài này. Mục tiêu là học cách kiểm soát phạm vi và đọc báo cáo.

## 26. Bài thực hành nâng cao: kiểm tra include/exclude

**Bối cảnh:** schema app có:

~~~text
orders
order_item
orders_2024_archive
orders_2025_archive
customer
~~~

Yêu cầu:

1. Chỉ include orders và order_item.
2. So sánh tables, columns, indexes và foreign keys.
3. Chạy một lần khác để exclude các bảng có hậu tố archive.
4. Đối chiếu object list thực tế với kết quả diff.
5. Ghi nhận khác biệt nào bị loại và lý do.

Mẫu lệnh minh họa:

~~~bash
liquibase \
  --reference-schemas=app \
  --schemas=app \
  --diff-types=tables,columns,indexes,foreignkeys \
  --include-objects="table:orders,table:order_item" \
  diff
~~~

Và:

~~~bash
liquibase \
  --reference-schemas=app \
  --schemas=app \
  --exclude-objects="table:.*_archive" \
  diff
~~~

Cú pháp object filter cần xác nhận trên đúng Liquibase version. Sau khi chạy, không chỉ dựa vào câu “diff thành công”; cần xác nhận tập object được chọn đúng.

## 27. Câu hỏi tự kiểm tra

**1. Vì sao cần giới hạn schema trước khi diff?**

Để so sánh đúng namespace nghiệp vụ và tránh nhiễu từ schema hệ thống, extension hoặc metadata không thuộc mục tiêu.

**2. Reference và target khác nhau thế nào?**

Reference là nguồn chuẩn để đối chiếu; target là database được xem xét so với reference. Chiều này ảnh hưởng tới ý nghĩa diff-changelog.

**3. --schemas và --reference-schemas có vai trò gì?**

Chúng chỉ định schema được đưa vào phạm vi ở phía target và reference theo khả năng phiên bản hỗ trợ.

**4. Chọn schema app có nghĩa chỉ so sánh bảng không?**

Không. Schema có thể chứa nhiều loại đối tượng; cần thêm diff-types nếu muốn giới hạn loại.

**5. diff-types có bảo đảm mọi thuộc tính của object được so sánh không?**

Không. Phạm vi hỗ trợ phụ thuộc DBMS, driver, phiên bản và loại đối tượng.

**6. include-objects khác exclude-objects thế nào?**

Include chọn những đối tượng cần giữ trong phạm vi; exclude loại những đối tượng khớp pattern khỏi phạm vi.

**7. Có nên exclude mọi bảng archive?**

Chỉ khi đã xác nhận archive không thuộc hợp đồng đang kiểm tra và có cách quản lý riêng nếu cần.

**8. Diff không báo khác biệt có chứng minh toàn bộ database giống nhau không?**

Không. Chỉ chứng minh trong phạm vi schema/object type/filter và metadata mà công cụ có thể so sánh.

**9. Vì sao không chạy diff-changelog ngay sau diff?**

Vì output cần review chiều reference/target, SQL sinh, dependency, rollback và nguy cơ DROP/ALTER.

**10. Context/label filter có thay thế object filter không?**

Không. Context/label chọn changeset; object filter chọn đối tượng trong thao tác diff.

**11. Có nên dùng user không đủ quyền catalog để diff production?**

Không nên nếu muốn kết luận toàn diện. Dùng quyền đọc metadata phù hợp ở cả hai phía hoặc ghi rõ giới hạn quyền.

**12. Nếu reference và target dùng tên schema khác nhau thì sao?**

Cần xác minh cơ chế mapping được hỗ trợ; chỉ chọn hai schema không đồng nghĩa Liquibase tự coi chúng tương đương.

## 28. Checklist trước khi chấp nhận báo cáo diff

- [ ] Reference và target được ghi rõ, không đảo chiều.
- [ ] Host/database/service của cả hai phía đã được xác minh.
- [ ] Username và quyền đọc metadata đủ tương đương.
- [ ] Default schema và Liquibase metadata schema đã được xác nhận.
- [ ] Schema scope của reference và target đã được khai báo rõ.
- [ ] Nếu tên schema khác nhau, schema mapping đã được kiểm thử.
- [ ] diff-types phù hợp với câu hỏi và được phiên bản hỗ trợ.
- [ ] Include/exclude patterns đã được thử trên danh sách object thực tế.
- [ ] Không loại nhầm bảng/constraint/index nghiệp vụ.
- [ ] Schema hệ thống/extension được phân loại theo ownership.
- [ ] Data diff chỉ dùng cho dữ liệu được phê duyệt.
- [ ] Những object type không được hỗ trợ đã có cách kiểm tra riêng.
- [ ] Kết quả diff được đọc theo chiều reference/target.
- [ ] Không kết luận toàn bộ schema giống nhau khi phạm vi chỉ là một phần.
- [ ] diff-changelog được review trước update, đặc biệt các DROP/DELETE/ALTER.
- [ ] SQL và rollback được thử trên DBMS/driver đích.
- [ ] CI/CD lưu cấu hình scope, version, artifact và báo cáo.
- [ ] Mọi khác biệt được bỏ qua đều có lý do và chủ sở hữu.
- [ ] Không lưu secret hoặc dữ liệu nhạy cảm trong log/artifact diff.

**Kết luận:** Một báo cáo Liquibase diff chỉ đáng tin khi phạm vi được định nghĩa rõ: **database nào là reference, database nào là target, schema nào được chọn, loại đối tượng nào được so sánh và object nào bị include/exclude**. Lọc quá rộng làm nhiễu; lọc quá hẹp có thể che giấu drift. Hãy cố định cấu hình scope, kiểm tra quyền và khả năng hỗ trợ theo DBMS, đọc kết quả theo đúng chiều, rồi review diff-changelog trước khi áp dụng. Khi đó so sánh schema trở thành một bước kiểm chứng có thể lặp lại và có giá trị trong tiếp nhận database legacy, review migration và CI/CD.

