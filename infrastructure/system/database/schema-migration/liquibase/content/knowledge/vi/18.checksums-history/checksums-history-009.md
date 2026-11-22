# Mark-next-changeset-ran và rủi ro bỏ qua thay đổi

Liquibase quản lý migration dựa trên changelog và lịch sử changeset đã áp dụng trong database. Tuy nhiên, có những hệ thống đã tồn tại trước khi Liquibase được đưa vào sử dụng: bảng được tạo thủ công, schema được triển khai bằng một công cụ khác, hoặc một nhóm vận hành đã chạy SQL ngoài pipeline. Khi kết nối Liquibase với database như vậy, nhóm cần đồng bộ **lịch sử mà Liquibase biết** với **trạng thái database đang có**.

Lệnh **mark-next-changeset-ran** cho phép đánh dấu changeset kế tiếp chưa được ghi nhận là đã chạy mà không thực thi các thay đổi của changeset đó. Đây là công cụ có phạm vi hẹp, hữu ích trong một số tình huống baseline hoặc khi thay đổi đã được áp dụng thủ công và đã được xác minh tương đương. Nhưng nếu dùng để bỏ qua migration chưa thực hiện, database sẽ thiếu schema hoặc dữ liệu mà các changeset tiếp theo đang giả định. Một dòng lịch sử “đã chạy” không phải bằng chứng rằng SQL đã chạy.

Bài thuộc chương **Checksum và lịch sử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Nội dung tập trung vào ngữ nghĩa của mark-next-changeset-ran, điều kiện sử dụng, khác biệt với các cơ chế đồng bộ lịch sử khác và cách đánh giá rủi ro trước khi bỏ qua một thay đổi.

## 1. Lệnh mark-next-changeset-ran thực hiện điều gì?

Trong quy trình update thông thường, Liquibase đọc changelog, so sánh các changeset với bảng **DATABASECHANGELOG**, rồi thực thi những changeset chưa được ghi nhận là đã chạy.

Lệnh **mark-next-changeset-ran** thay đổi hành vi ở một điểm cụ thể: nó đánh dấu changeset kế tiếp đang chờ trong phạm vi changelog được chọn là đã chạy **mà không thực thi phần change của changeset đó**. Lịch sử được cập nhật để Liquibase coi changeset này đã được xử lý; ở các lần update thông thường tiếp theo, changeset đã được ghi nhận sẽ không được chạy như một changeset mới.

Ví dụ:

~~~text
Changelog có thứ tự:
  001-create-customer
  002-add-email
  003-create-email-index

Trạng thái database:
  Bảng customer đã được tạo thủ công tương đương 001.
  Cột email chưa có.
  Index email chưa có.

Nếu mark-next-changeset-ran đánh dấu 001:
  Liquibase ghi nhận 001 đã chạy, nhưng không chạy CREATE TABLE.
  Lần update tiếp theo có thể chạy 002 và 003.
~~~

Ví dụ này chỉ an toàn nếu bảng customer hiện có thực sự tương đương với kết quả mà changeset 001 phải tạo. Nếu bảng chỉ có cùng tên nhưng thiếu cột, khác kiểu, thiếu primary key hoặc constraint, việc đánh dấu 001 là đã chạy sẽ che giấu sai lệch và có thể khiến 002 thất bại hoặc tạo ra schema không đúng.

**Điểm cốt lõi:** mark-next-changeset-ran cập nhật lịch sử Liquibase. Nó không tự tạo bảng, thêm cột, nạp CSV, tạo index, backfill dữ liệu hay sửa trạng thái database.

## 2. Phân biệt update, mark-next-changeset-ran và changelogSync

Các lệnh này đều liên quan đến changeset chưa được ghi nhận, nhưng mục tiêu khác nhau.

| Cơ chế | Điều xảy ra với changeset | SQL thay đổi có được thực thi? | Phạm vi khái quát |
|---|---|---|---|
| update | Chạy changeset chưa áp dụng theo thứ tự và điều kiện đã chọn | Có, đối với changeset được thực thi | Các changeset đủ điều kiện còn thiếu |
| mark-next-changeset-ran | Đánh dấu changeset kế tiếp đang chờ là đã chạy | Không chạy phần change của changeset được đánh dấu | Một changeset kế tiếp |
| changelogSync | Đồng bộ lịch sử bằng cách đánh dấu các changeset chưa được ghi nhận là đã chạy | Không thực thi các thay đổi tương ứng | Có thể bao phủ nhiều changeset trong changelog được chọn |
| changelogSyncToTag | Đồng bộ lịch sử tới tag được chỉ định theo phạm vi lệnh | Không thực thi các thay đổi tương ứng | Các changeset thuộc phạm vi tới tag |
| onFail=MARK_RAN | Khi precondition của changeset không đạt theo cấu hình, ghi nhận changeset là đã chạy | Không thực thi phần change của changeset đó | Changeset có precondition tương ứng |

Tên lệnh, tùy chọn và cách chọn changeset có thể phụ thuộc phiên bản Liquibase. Hãy kiểm tra help/tài liệu của đúng runtime trước khi vận hành. Bảng trên mô tả mục đích khái quát, không thay thế việc xác minh các bộ lọc context, label, DBMS và changelog thực tế.

### 2.1. Vì sao không dùng changelogSync thay cho mark-next?

Giả sử database đã được tạo từ trước và chỉ có changeset 001 là đã được áp dụng thủ công; changeset 002 và 003 vẫn cần chạy. Nếu dùng changelogSync cho toàn bộ changelog, nhóm có thể đánh dấu cả 002 và 003 là đã chạy dù các thay đổi tương ứng chưa tồn tại. Khi đó Liquibase bỏ qua các bước tạo cột/index cần thiết.

mark-next-changeset-ran có phạm vi hẹp hơn, nhưng vẫn có rủi ro nếu changeset kế tiếp không đúng hoặc chưa được áp dụng thực tế. Hẹp hơn không đồng nghĩa an toàn tự động.

## 3. Phân biệt lệnh mark-next với onFail=MARK_RAN

Hai cơ chế có cùng hệ quả quan trọng là changeset được ghi nhận là đã chạy mà phần change không được thực thi, nhưng nguyên nhân và thời điểm kích hoạt khác nhau.

**mark-next-changeset-ran** là một lệnh vận hành được gọi có chủ đích để đánh dấu changeset kế tiếp đang chờ.

**onFail=MARK_RAN** là chính sách gắn với precondition của một changeset. Khi precondition được đánh giá và không đạt, Liquibase xử lý theo onFail; nếu là MARK_RAN, changeset được ghi nhận như đã chạy mà không thực thi change.

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-reference-table
      author: database-team
      preConditions:
        - onFail: MARK_RAN
        - tableExists:
            tableName: reference_code
      changes:
        - createTable:
            tableName: reference_code
            columns:
              - column:
                  name: code
                  type: VARCHAR(30)
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ví dụ này yêu cầu xem xét kỹ ý định: precondition tableExists đạt khi bảng đã tồn tại, do đó onFail=MARK_RAN không được kích hoạt chỉ vì bảng tồn tại. Nếu mục tiêu là đánh dấu khi bảng **đã tồn tại**, điều kiện phải được viết theo logic không đạt tương ứng, ví dụ NOT tableExists. Tuy nhiên, chỉ kiểm tra tên bảng vẫn không chứng minh cấu trúc hiện tại tương đương với changeSet.

Không dùng MARK_RAN như một cách chữa lỗi chung. Nếu database đã có bảng, cần kiểm tra đầy đủ cột, kiểu, khóa, constraint, index và dữ liệu trước khi đồng bộ lịch sử.

## 4. Khi nào có thể cân nhắc mark-next-changeset-ran?

Trường hợp điển hình là **baseline một database đã có schema tương đương** với changeset đầu tiên trong changelog. Ví dụ:

- Một hệ thống cũ được tạo bằng script SQL thủ công, nay chuyển sang Liquibase.
- Database mới được cấp từ một bản snapshot đã được kiểm định, trong đó schema đã chứa các đối tượng tương ứng với changeset nền.
- Một migration cụ thể đã được chạy ngoài Liquibase theo một quy trình được ghi nhận, và nhóm muốn đồng bộ lịch sử sau khi đã xác minh kết quả.
- Môi trường được phục hồi từ backup có lịch sử schema/data đã biết, và cần đối chiếu với changelog trước khi tiếp tục.

Trước khi dùng, cần có bằng chứng rằng **thay đổi đã được áp dụng đầy đủ và đúng ý nghĩa**. Bằng chứng có thể gồm:

1. So sánh schema thực tế với định nghĩa mong đợi: bảng, cột, kiểu, default, nullability, khóa và constraint.
2. So sánh index: tên, cột, thứ tự cột, unique, predicate, expression và trạng thái hợp lệ.
3. So sánh dữ liệu do changeset tạo hoặc chuyển đổi: khóa, số lượng, giá trị, quan hệ và điều kiện nghiệp vụ.
4. Xác nhận database đích, schema, user và changelog path.
5. Xác nhận changeset kế tiếp đúng là changeset đã được áp dụng ngoài Liquibase.
6. Lưu lại người xác minh, thời điểm, bằng chứng và lý do đồng bộ lịch sử.

Nếu không thể chứng minh trạng thái tương đương, hãy để Liquibase thực thi migration theo quy trình bình thường hoặc viết một baseline/migration phù hợp sau khi thiết kế lại. Không dùng lệnh đánh dấu để biến một database chưa đạt thành database “có vẻ đã đạt”.

## 5. Trước khi đánh dấu, phải xác định đúng changeset kế tiếp

Lệnh có chữ **next** nên sai thứ tự là rủi ro rất lớn. Changeset kế tiếp phụ thuộc vào changelog đang dùng và cách Liquibase chọn các thay đổi trong lần chạy đó.

Các yếu tố cần rà soát:

- File changelog gốc và các file được include/includeAll.
- Thứ tự khai báo changeset trong các tệp.
- ID, author và đường dẫn changelog.
- Context và label filter.
- DBMS filter.
- Các changeset đã có trong DATABASECHANGELOG.
- Changeset nào bị lọc, bỏ qua hoặc đã được ghi nhận.
- Liquibase runtime và cấu hình kết nối đang sử dụng.

Không suy đoán “next” dựa trên số ID lớn nhất. ID là định danh do nhóm đặt; thứ tự xử lý đến từ cấu trúc changelog và các bộ lọc có hiệu lực, không nhất thiết là thứ tự số học.

Ví dụ:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-baseline.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/010-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/020-order.yaml
      relativeToChangelogFile: true
~~~

Nếu baseline đã được ghi nhận, changeset tiếp theo có thể thuộc customer. Nhưng nếu context/label loại bỏ changeset đó, hoặc database đã có lịch sử khác, changeset được xem là kế tiếp có thể thay đổi. Luôn kiểm tra status và cấu hình thực tế trước khi gọi lệnh.

## 6. Ví dụ baseline: schema đã được tạo bên ngoài Liquibase

Giả sử database legacy đã có bảng customer:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Changelog hiện có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: database-team
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
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false

  - changeSet:
      id: 002-create-customer-email-index
      author: database-team
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
~~~

Database legacy có thể đã có bảng customer đúng cấu trúc nhưng chưa có bảng lịch sử Liquibase hoặc chưa ghi nhận changeset 001. Sau khi so sánh schema thật với kết quả mong đợi của changeset 001, nhóm có thể cân nhắc đánh dấu **changeset kế tiếp** là đã chạy. Sau đó update sẽ xử lý changeset 002 để tạo index nếu index này chưa tồn tại và lịch sử cho phép.

Nếu bảng legacy thiếu NOT NULL, khác kiểu email, thiếu khóa chính hoặc dùng schema khác, việc đánh dấu 001 là sai. Changeset 002 có thể chạy nhưng trạng thái cuối vẫn không đúng. Nếu index đã tồn tại từ trước, phải kiểm tra định nghĩa của index đó trước khi để changeset 002 chạy.

### 6.1. Kiểm tra schema trước khi baseline

Trên PostgreSQL, có thể kiểm tra cột và kiểu:

~~~sql
SELECT table_schema, table_name, column_name,
       data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
ORDER BY ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT tc.constraint_name, tc.constraint_type,
       kcu.column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name = 'customer'
ORDER BY tc.constraint_name, kcu.ordinal_position;
~~~

Kiểm tra index:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'customer'
ORDER BY indexname;
~~~

Các truy vấn này là ví dụ cho PostgreSQL. DBMS khác có catalog và cách biểu diễn metadata khác. Việc so sánh cần bao gồm cả thuộc tính không hiện trong một truy vấn đơn giản, ví dụ expression, partial predicate, collation hoặc storage options khi chúng quan trọng.

## 7. Cách gọi lệnh và kiểm soát cấu hình

Khi đã cấu hình kết nối Liquibase và changelog, lệnh thường có dạng:

~~~bash
liquibase mark-next-changeset-ran
~~~

Có thể truyền các tùy chọn changelog/connection theo phiên bản và cách triển khai, ví dụ dùng file cấu hình riêng hoặc tham số CLI. Không đưa mật khẩu trực tiếp vào lịch sử shell, output pipeline hay tài liệu.

Trước khi gọi lệnh:

1. Xác minh URL và database đích.
2. Xác minh schema chứa DATABASECHANGELOG.
3. Xác minh changelog root và các include.
4. Chạy status --verbose để xem những changeset chưa được ghi nhận.
5. Đọc changeset kế tiếp và đối chiếu với trạng thái database thực tế.
6. Xác nhận context, label và DBMS filter.
7. Lưu bằng chứng review và có người thứ hai xác nhận nếu là môi trường quan trọng.
8. Chỉ sau đó mới chạy mark-next-changeset-ran.

Ví dụ cấu hình kết nối được quản lý ngoài command:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://db-host:5432/application
username=liquibase_migrator
# Password được cấp qua secret store hoặc cơ chế bảo mật của môi trường
~~~

Đây chỉ là ví dụ cấu hình, không phải file cần tạo trong bài. Hãy dùng cơ chế secret của hệ thống và tránh ghi thông tin xác thực thật vào repository.

Tên tham số, cấu hình và hành vi có thể thay đổi theo Liquibase version. Kiểm tra help của chính runtime đang dùng và xác minh changelog path được CLI đọc đúng. Đừng chạy command chỉ vì nó trả exit code thành công; cần xác minh changeset đã được ghi nhận đúng và trạng thái schema không đổi ngoài dự kiến.

## 8. DATABASECHANGELOG sau khi đánh dấu

Liquibase lưu lịch sử changeset trong **DATABASECHANGELOG**. Những cột thường hữu ích khi kiểm tra gồm:

| Cột | Ý nghĩa khái quát |
|---|---|
| ID | ID của changeset |
| AUTHOR | Author khai báo trong changelog |
| FILENAME | Đường dẫn changelog được dùng để nhận diện |
| MD5SUM | Checksum của changeset theo cơ chế Liquibase |
| DATEEXECUTED | Thời điểm ghi nhận thực thi |
| ORDEREXECUTED | Thứ tự ghi nhận trong lịch sử |
| EXECTYPE | Loại kết quả thực thi/ghi nhận |

Sau mark-next-changeset-ran, changeset được ghi nhận như đã chạy mà không chạy change. Tùy phiên bản và ngữ cảnh, EXECTYPE thường thể hiện trạng thái **MARK_RAN**. Không chỉ nhìn một trường EXECTYPE; hãy đối chiếu ID, AUTHOR, FILENAME, checksum và nội dung changelog.

Truy vấn ví dụ trên PostgreSQL:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

**Lịch sử là bằng chứng Liquibase đã ghi nhận một trạng thái, không phải bằng chứng độc lập rằng SQL đã tạo ra kết quả vật lý.** Đặc biệt với changeset bị đánh dấu, phải có bằng chứng schema/data ở bên ngoài bảng lịch sử.

## 9. Checksum có chứng minh thay đổi đã được áp dụng không?

Không. Checksum của changeset giúp Liquibase phát hiện những thay đổi không mong đợi trong nội dung changelog theo cơ chế checksum của phiên bản. Nó không phải checksum của toàn bộ database schema hoặc dữ liệu.

Cần phân biệt:

- **Checksum changeset:** giá trị Liquibase tính cho nội dung changeset theo thuật toán/phiên bản.
- **Trạng thái thực tế:** bảng, cột, index, constraint, dữ liệu và quyền đang tồn tại trong database.
- **Lịch sử DATABASECHANGELOG:** changeset nào đã được ghi nhận, bằng cách nào và khi nào.

Một changeset được mark-ran có thể có checksum được ghi vào lịch sử. Điều đó không có nghĩa phần change đã chạy. Ngược lại, checksum khớp cũng không chứng minh ai đó không chỉnh schema thủ công sau lần triển khai.

Ví dụ: changeset tạo bảng customer được mark-ran; DATABASECHANGELOG có bản ghi và checksum. Sau đó một người sửa cột email từ VARCHAR(255) thành VARCHAR(100) trực tiếp trong database. Checksum changelog vẫn có thể khớp, nhưng schema đã drift. Cần cơ chế kiểm tra schema riêng nếu dự án cần phát hiện drift.

**Không dùng clear-checksums để “sửa” việc thay đổi bị bỏ qua.** Làm mới checksum không thực thi SQL bị bỏ qua và không sửa schema. Nếu changeset cũ cần điều chỉnh, hãy điều tra lịch sử rồi thiết kế changeset bổ sung.

## 10. Rủi ro lớn nhất: đánh dấu thay đổi chưa từng được thực hiện

Giả sử changeset kế tiếp có nội dung:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-customer-email
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email
                  type: VARCHAR(255)
~~~

Nếu database chưa có cột email mà người vận hành chạy mark-next-changeset-ran để vượt qua migration, Liquibase sẽ ghi nhận changeset như đã chạy nhưng **cột email không được thêm**.

Các changeset sau có thể:

- Tạo index trên email và thất bại vì cột không tồn tại.
- Chạy SQL update email nhưng lỗi “column does not exist”.
- Tạo view hoặc procedure tham chiếu email và thất bại.
- Ứng dụng mới khởi động rồi lỗi truy vấn vì schema thiếu cột.
- CI/CD báo migration thành công nhưng kiểm thử tích hợp thất bại ở bước muộn hơn.

Đây là một dạng **lệch giữa lịch sử và trạng thái thật**. Lỗi càng khó phát hiện nếu các bước sau không sử dụng ngay đối tượng bị bỏ qua.

## 11. Những kiểu thay đổi đặc biệt nguy hiểm khi bỏ qua

| Changeset bị bỏ qua | Hậu quả có thể có |
|---|---|
| createTable | Bảng không tồn tại, các bước phụ thuộc thất bại |
| addColumn | Ứng dụng/SQL truy cập cột mới bị lỗi |
| addNotNullConstraint | Dữ liệu vẫn chứa NULL, invariant nghiệp vụ không được bảo vệ |
| addForeignKeyConstraint | Dữ liệu tham chiếu không được kiểm soát |
| createIndex | Truy vấn có thể chậm; unique index không thực thi tính duy nhất |
| loadData | Dữ liệu tham chiếu/seed không có dù lịch sử báo đã xử lý |
| update dữ liệu | Giá trị chưa được chuyển đổi; logic ứng dụng có thể đọc sai |
| createView/procedure | Đối tượng hoặc logic database không tồn tại |
| đổi kiểu hoặc backfill | Dữ liệu cũ chưa đạt định dạng mà ứng dụng mới yêu cầu |

Không đánh giá mức độ rủi ro chỉ bằng kích thước changeset. Một thay đổi một dòng thêm NOT NULL có thể là điều kiện bảo vệ dữ liệu quan trọng; bỏ qua nó có thể gây lỗi lớn hơn bỏ qua một index phụ trợ.

## 12. Ảnh hưởng đến các changeset phụ thuộc

Changeset thường được tổ chức theo thứ tự và có dependency ngầm hoặc tường minh:

~~~text
001-create-customer
        |
        v
002-add-email
        |
        v
003-backfill-email
        |
        v
004-add-email-not-null
        |
        v
005-create-email-index
~~~

Nếu đánh dấu 002 là ran nhưng cột email chưa tồn tại, 003–005 có thể thất bại. Nếu những bước sau không chạm ngay tới cột email, pipeline có thể qua một thời gian rồi mới phát hiện lỗi trong runtime.

Một precondition ở changeset sau có thể ngăn một số thao tác sai, nhưng không phải cơ chế bù đắp cho changeset bị bỏ qua. Ví dụ precondition columnExists có thể dừng 003 với thông báo rõ, nhưng database vẫn thiếu cột và lịch sử 002 vẫn được đánh dấu. Người vận hành vẫn phải sửa trạng thái bằng migration được kiểm chứng.

**Không sắp xếp lại changeset đã phát hành chỉ để thay đổi “next”.** Việc đổi thứ tự có thể làm sai lịch sử, dependency và checksum. Nếu changeset cần baseline không phải changeset kế tiếp, dừng lại và thiết kế cách đồng bộ phù hợp thay vì dịch chuyển changelog để ép command chọn mục tiêu.

## 13. Vì sao mark-next có thể làm các môi trường lệch nhau?

Hãy xem ba môi trường:

| Môi trường | Trạng thái ban đầu | Hành động | Kết quả |
|---|---|---|---|
| Dev | Database mới | update bình thường | SQL của changeset được thực thi |
| Staging | Schema được tạo thủ công tương đương | mark-next sau khi xác minh | Lịch sử được đồng bộ, SQL không chạy |
| Production | Bảng tồn tại nhưng thiếu constraint | mark-next thiếu kiểm chứng | Lịch sử báo đã chạy, constraint vẫn thiếu |

Cùng một changeset ID có thể có bản ghi lịch sử ở cả ba môi trường nhưng nguồn gốc trạng thái khác nhau. Điều đó không nhất thiết sai nếu baseline được kiểm chứng và kết quả schema/data tương đương. Nhưng nếu chỉ dựa vào “cả ba đều có bản ghi trong DATABASECHANGELOG”, ta sẽ bỏ qua khác biệt quan trọng.

Quy trình cần kiểm tra **kết quả cuối** trên mọi môi trường: schema, constraint, index, dữ liệu, quyền và cấu hình. Không lấy lịch sử changeset làm đại diện duy nhất cho trạng thái database.

## 14. Mark-next và rollback: vì sao cần thận trọng?

Khi một changeset được ghi nhận là đã chạy, Liquibase có thể xem nó là một phần của lịch sử đã áp dụng. Nếu sau đó rollback tới changeset đó, Liquibase sẽ sử dụng rollback được khai báo hoặc cơ chế rollback được hỗ trợ.

Điều này tạo ra hai tình huống:

**Tình huống A — Thay đổi đã được áp dụng thủ công tương đương:** rollback có thể đảo ngược đối tượng thủ công đó. Ví dụ bảng customer đã được tạo trước Liquibase, nhưng changeset tạo bảng được mark-ran; rollback changeset có thể DROP TABLE customer nếu rollback khai báo như vậy. Điều này có thể gây mất dữ liệu.

**Tình huống B — Thay đổi chưa được áp dụng:** rollback vẫn có thể cố thực hiện SQL đảo ngược dù đối tượng chưa tồn tại, dẫn đến lỗi hoặc hành vi không như mong đợi.

Vì vậy, trước khi mark-ran phải hiểu cả chiều forward và rollback. Nếu dùng baseline, rollback của baseline changeset thường cần được thiết kế cẩn thận theo ý nghĩa sở hữu dữ liệu. Có trường hợp baseline không nên được rollback như một changeset tạo mới; phương án phát hành cần được định nghĩa rõ.

Không mặc định rollback an toàn chỉ vì changeset đã có trong DATABASECHANGELOG.

## 15. So sánh với baseline và changelogSync

Khi đưa Liquibase vào một database đã tồn tại, mục tiêu thường là **baseline**: xác lập điểm bắt đầu quản lý để các thay đổi tương lai được theo dõi.

Có một số hướng triển khai:

| Hướng | Khi phù hợp | Rủi ro/cân nhắc |
|---|---|---|
| Tạo baseline changeset đại diện schema hiện tại, sau khi kiểm tra | Hệ thống legacy cần bắt đầu quản lý từ trạng thái đã có | Phải chứng minh schema/data thực sự tương ứng |
| mark-next-changeset-ran cho một changeset đã được áp dụng ngoài Liquibase | Chỉ có đúng một changeset kế tiếp tương đương cần ghi nhận | Chọn nhầm next hoặc thiếu bằng chứng sẽ làm lịch sử sai |
| changelogSync cho tập changeset đã được áp dụng tương đương | Có kế hoạch đồng bộ nhiều changeset và kiểm chứng đầy đủ | Có thể đánh dấu nhầm cả thay đổi chưa thực hiện |
| Để Liquibase update thực thi các changeset còn thiếu | Database chưa có thay đổi tương ứng | Có thể xung đột với đối tượng tạo thủ công; cần migration/baseline phù hợp |

Không có một lệnh baseline chung an toàn cho mọi hệ thống. Với database lớn, có thể cần snapshot schema, so sánh metadata, đối chiếu dữ liệu và thử trên bản sao trước khi quyết định.

Nếu nhiều changeset đã được chạy thủ công, cần lập ma trận từng changeset với bằng chứng tương ứng. Không dùng changelogSync toàn bộ chỉ vì database “trông giống” phiên bản hiện tại.

## 16. Quy trình an toàn trước khi gọi mark-next-changeset-ran

Có thể dùng quy trình sau như một cổng vận hành:

### Bước 1 — Đóng băng đúng đầu vào

- Chọn artifact/changelog version đã được review.
- Xác định database URL và schema chính xác.
- Xác định context, label, DBMS filter và file include.
- Xác nhận không có pipeline/instance khác đang thay đổi lịch sử cùng lúc.

### Bước 2 — Xác định changeset kế tiếp

- Chạy status --verbose với cùng cấu hình.
- Đọc chính xác ID, author, path và nội dung changeset kế tiếp.
- Đối chiếu thứ tự include và những bộ lọc đang bật.
- Nếu changeset kế tiếp không phải bước đã áp dụng thủ công, **dừng**.

### Bước 3 — Đối chiếu database thực tế

- So sánh bảng/cột/kiểu/default/nullability.
- So sánh PK, FK, unique/check constraints và index.
- So sánh dữ liệu đã nạp/backfill/chuyển đổi.
- Kiểm tra schema name, collation, extension hoặc thuộc tính DBMS đặc thù nếu liên quan.
- Ghi lại sai lệch còn tồn tại; không đánh dấu khi chưa xử lý.

### Bước 4 — Review và phê duyệt

- Lưu bằng chứng truy vấn/cấu trúc trước khi đồng bộ.
- Xác nhận người chịu trách nhiệm và lý do không chạy SQL qua Liquibase.
- Xem xét tác động rollback và các changeset phụ thuộc.
- Dùng quyền migration được kiểm soát, không dùng tài khoản ứng dụng rộng quyền.

### Bước 5 — Đánh dấu đúng một changeset

- Chạy mark-next-changeset-ran đúng database và changelog.
- Đọc output, xác minh ID/author/filename được ghi nhận.
- Không tự động tiếp tục nếu command chọn nhầm changeset hoặc báo lỗi.

### Bước 6 — Kiểm chứng trạng thái sau đánh dấu

- Đối chiếu DATABASECHANGELOG.
- Xác nhận schema/data vẫn đúng như trước thao tác đồng bộ.
- Chạy update trên môi trường kiểm thử phù hợp để xác nhận changeset kế tiếp hoạt động.
- Xác nhận không có object hoặc dữ liệu bị bỏ sót.

### Bước 7 — Lưu dấu vết

Ghi lại artifact, command, môi trường, thời điểm, changeset, checksum, bằng chứng schema/data và người phê duyệt. Những thông tin này giúp điều tra nếu các môi trường có lịch sử khác nhau.

## 17. Ví dụ truy vấn kiểm tra sau mark-next

Sau khi đánh dấu, xem changeset có trong lịch sử:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
WHERE id = '001-create-customer'
  AND author = 'database-team';
~~~

Kết quả phải được đối chiếu với ID, author và filename thực tế trong changelog. Không chỉ tìm theo ID nếu repository có nhiều author hoặc path khác nhau.

Sau đó kiểm tra cấu trúc bảng, ví dụ PostgreSQL:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
ORDER BY ordinal_position;
~~~

Kiểm tra index:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'customer';
~~~

Nếu changeset được mark-ran để đại diện cho thao tác tạo bảng, các truy vấn phải cho thấy bảng, cột, khóa và các thuộc tính tương đương với kết quả mong đợi. Với changeset dữ liệu, cần truy vấn giá trị và quan hệ; metadata schema không đủ.

**Không có một câu SELECT duy nhất xác minh được mọi thay đổi.** Mỗi loại changeset cần một bộ assertion phù hợp với mục tiêu: DDL, DML, index, view, procedure, permission hay dữ liệu tham chiếu.

## 18. Xử lý khi đã mark nhầm changeset

Nếu phát hiện một changeset đã được mark-ran nhưng thay đổi thực tế chưa tồn tại, cần xử lý như một **sự cố lệch lịch sử/database**, không chỉ là lỗi command.

Trình tự:

1. Tạm dừng các pipeline/instance có thể tiếp tục áp migration phụ thuộc.
2. Xác định chính xác changeset, ID, author, filename, checksum và thời điểm được đánh dấu.
3. Đối chiếu trạng thái schema/data hiện tại với thay đổi đáng lẽ phải có.
4. Kiểm tra các changeset tiếp theo đã chạy hay chưa và có phụ thuộc vào thay đổi bị bỏ qua không.
5. Thiết kế changeset sửa chữa/forward-fix mới để đưa database tới trạng thái mong muốn.
6. Thử trên bản sao có cùng lịch sử và dữ liệu đại diện.
7. Triển khai sửa chữa theo quy trình release; sau đó xác minh schema/data và lịch sử.

Không tự xóa dòng DATABASECHANGELOG hoặc sửa EXECTYPE để biến changeset thành “chưa chạy” nếu chưa có kế hoạch reconcile được kiểm chứng. Xóa lịch sử không tự thực thi SQL và có thể khiến Liquibase chạy lại thao tác trên đối tượng đã tồn tại hoặc dữ liệu đã bị thay đổi.

Nếu cần thực hiện lại một thay đổi, changeset mới thường dễ truy vết hơn việc sửa lịch sử cũ. Nếu cần phục hồi dữ liệu đã mất, có thể phải dùng backup/restore thay vì chỉ thêm DDL.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Changeset được ghi ran nhưng cột không có | mark-next được dùng dù SQL chưa được áp dụng | Viết changeset sửa chữa, xác minh trạng thái thật |
| Changeset không mong đợi được đánh dấu | Hiểu sai thứ tự hoặc bộ lọc context/label | Dừng, đối chiếu changelog root và status |
| Update tiếp theo lỗi object missing | Changeset tiền đề đã bị bỏ qua | Kiểm tra dependency và tạo forward-fix |
| Object already exists khi chạy update | Lịch sử và trạng thái DB không đồng bộ | So sánh schema và DATABASECHANGELOG trước khi retry |
| Checksum mismatch | Nội dung changeset đã triển khai bị sửa | Giữ lịch sử, điều tra diff và tạo changeset bổ sung |
| Staging và production khác nhau | Một môi trường được mark-ran, môi trường khác update thật | So sánh schema/data, không chỉ so lịch sử |
| Rollback xóa đối tượng đã tạo thủ công | Changeset mark-ran có rollback destructive | Kiểm tra rollback trước khi đánh dấu và trước khi chạy rollback |
| ChangelogSync bỏ qua quá nhiều thay đổi | Dùng đồng bộ toàn bộ khi chỉ một bước đã được áp dụng | Lập ma trận baseline và chọn phạm vi hẹp |
| Lệnh chạy trên sai database | Cấu hình URL/profile/secret không đúng | Xác minh kết nối và database identity trước mọi lệnh |
| Pipeline báo thành công nhưng app lỗi | Chỉ kiểm tra lịch sử, không kiểm tra schema/data | Thêm assertion và integration test sau migration |

Một quy tắc điều tra hữu ích là đi theo thứ tự: **đúng database → đúng changelog và bộ lọc → changeset kế tiếp → DATABASECHANGELOG → schema/data thực tế → dependency và phiên bản ứng dụng**.

## 20. Bài thực hành: đánh dấu một changeset đã được áp dụng thủ công

Thực hiện trên database lab riêng, có thể xóa và tạo lại. Không dùng production cho bài thử.

### Kịch bản A — Baseline tương đương

1. Tạo database lab và tạo bảng customer bằng SQL ngoài Liquibase với đầy đủ cột, kiểu và constraint như changeset 001.
2. Tạo changelog chứa changeset 001 tạo bảng customer và changeset 002 tạo index trên email.
3. Kết nối Liquibase vào database lab, chạy status --verbose để xác nhận changeset kế tiếp.
4. Đối chiếu cấu trúc bảng thực tế với định nghĩa changeset 001.
5. Chạy mark-next-changeset-ran theo phiên bản Liquibase đang dùng.
6. Truy vấn DATABASECHANGELOG, xác nhận ID/author/path và EXECTYPE.
7. Chạy update; xác nhận changeset 002 được thực thi và index xuất hiện.
8. So sánh kết quả cuối với một database mới được tạo bằng update từ đầu.

### Kịch bản B — Bỏ qua một thay đổi chưa thực hiện

1. Tạo database lab khác, chưa có bảng customer.
2. Đưa changelog 001/002 vào và xác định changeset kế tiếp.
3. Thử đánh dấu changeset 001 là ran trong môi trường có thể xóa.
4. Xác minh DATABASECHANGELOG đã ghi nhận nhưng bảng customer không xuất hiện.
5. Chạy changeset tiếp theo và quan sát lỗi dependency.
6. Ghi lại sự khác nhau giữa trạng thái lịch sử và trạng thái database.
7. Phục hồi database lab và thiết kế một changeset sửa chữa thay vì xóa lịch sử tùy tiện.

### Kịch bản C — So sánh changelogSync

Trên một database lab riêng, có nhiều changeset chưa áp dụng, thử changelogSync và đối chiếu số bản ghi lịch sử với trạng thái schema. Giải thích vì sao đây là thao tác đồng bộ phạm vi rộng và không phù hợp để bỏ qua một bước duy nhất nếu các bước còn lại chưa được áp dụng.

### Tiêu chí hoàn thành

Người học phải giải thích được lệnh đánh dấu có thực thi SQL hay không, xác định đúng changeset kế tiếp, chứng minh schema/data tương đương trước baseline, đọc được DATABASECHANGELOG và mô tả cách khắc phục khi lịch sử đã đánh dấu nhầm.

## 21. Checklist trước khi sử dụng mark-next-changeset-ran

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Có lý do hợp lệ để không thực thi changeset qua Liquibase? | Hồ sơ baseline hoặc xác nhận thay đổi đã áp dụng thủ công |
| Đúng database/schema và đúng artifact? | JDBC URL, schema, changelog version đã xác minh |
| Changeset kế tiếp đã được xác định chính xác? | status, include order, context/label/DBMS filter |
| Schema hiện tại tương đương kết quả changeset? | So sánh bảng, cột, kiểu, default, constraint |
| Dữ liệu đã được nạp/chuyển đổi tương đương? | Assertion về khóa, số dòng, giá trị và quan hệ |
| Index/view/procedure có đúng định nghĩa? | Kiểm tra catalog và thuộc tính đặc thù DBMS |
| Các changeset phụ thuộc có thể chạy? | Đồ thị dependency và test trên bản sao |
| Đã xem xét rollback của changeset được đánh dấu? | SQL rollback và tác động đến đối tượng có sẵn |
| Có rủi ro checksum hoặc định danh? | ID/author/path ổn định, artifact bất biến |
| Có người xác minh/phê duyệt? | Bằng chứng review và audit trail |
| Sau đánh dấu có kiểm tra lại database? | DATABASECHANGELOG cùng schema/data assertions |
| Có kế hoạch sửa nếu đánh dấu nhầm? | Forward-fix/restore và runbook rõ ràng |

**Nguyên tắc cuối cùng:** chỉ dùng mark-next-changeset-ran khi changeset kế tiếp đã được áp dụng đầy đủ bằng một con đường khác và database thực tế đã được chứng minh tương đương với kết quả mong đợi. Lệnh này đồng bộ lịch sử, không thực hiện thay đổi. Nếu bỏ qua một DDL hoặc DML chưa được áp dụng, DATABASECHANGELOG có thể báo “đã chạy” trong khi schema/dữ liệu vẫn thiếu; lỗi sẽ lan sang các changeset phụ thuộc, ứng dụng và các môi trường khác. Hãy xác minh đúng changeset, đối chiếu trạng thái thật, xem xét rollback và lưu bằng chứng trước khi đánh dấu.

