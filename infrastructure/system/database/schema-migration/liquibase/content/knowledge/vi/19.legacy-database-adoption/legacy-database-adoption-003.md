# Tạo bản nháp changelog từ cơ sở dữ liệu bằng generate-changelog

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Tiếp nhận CSDL**, một tình huống phổ biến là hệ thống đã có database hoạt động từ lâu nhưng chưa quản lý schema bằng Liquibase. Bảng, cột, khóa ngoại, chỉ mục và view được tạo qua script thủ công, công cụ quản trị hoặc các đợt triển khai trước đây. Khi muốn đưa Liquibase vào quy trình, nhóm cần mô tả được **schema hiện tại** mà không vô tình chạy lại những lệnh tạo đối tượng đã tồn tại.

Liquibase cung cấp lệnh **generate-changelog** để đọc cấu trúc của một database và tạo một changelog mô tả những đối tượng mà công cụ nhận diện được. Đây là bước **reverse-engineer schema** hữu ích khi tiếp nhận database legacy. Kết quả là **bản nháp cần review**, không phải lịch sử migration hoàn chỉnh và cũng không phải bản sao lưu dữ liệu.

Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trong bối cảnh tiếp nhận database có sẵn, cần kết hợp generate-changelog với quy trình kiểm tra, chuẩn hóa baseline và đồng bộ lịch sử Liquibase để các lần cập nhật tiếp theo an toàn.

Sau bài học, người học có thể giải thích generate-changelog làm gì, chuẩn bị kết nối và phạm vi snapshot, đọc và chỉnh bản changelog được sinh, phân biệt nó với diff-changelog, đưa database hiện hữu vào quản lý bằng baseline/changelog-sync, kiểm tra nhiều môi trường và tránh chạy lại DDL trên các đối tượng đã tồn tại.

## 1. Vì sao cần tạo changelog từ database legacy?

Giả sử một ứng dụng đang chạy nhiều năm với database có các đối tượng:

- Bảng **customer**, **sales_order**, **payment** và các bảng liên quan.
- Primary key, foreign key, unique constraint, check constraint.
- Index phục vụ truy vấn.
- View, sequence, trigger hoặc procedure tùy theo DBMS.
- Nhiều schema hoặc owner khác nhau.
- Các thay đổi đã được thực hiện qua script SQL, nhưng không có một lịch sử tập trung.

Nhóm muốn đưa Liquibase vào để những thay đổi tiếp theo được review, triển khai lặp lại và truy nguyên bằng **DATABASECHANGELOG**. Trước khi viết migration mới, cần biết chính xác database hiện đang có gì. Nếu bắt đầu với changelog trống rồi chạy **update**, Liquibase có thể cố tạo lại bảng hoặc constraint đã tồn tại, dẫn đến lỗi hoặc trạng thái không nhất quán.

**generate-changelog** giúp chụp lại một phần cấu trúc database tại thời điểm hiện tại và biểu diễn thành changelog. Nhờ đó, nhóm có một điểm xuất phát có thể version-control. Tuy nhiên, snapshot này không thể tự khôi phục toàn bộ ý định lịch sử: nó cho biết cấu trúc đang tồn tại, không cho biết ai đã tạo, vì sao tạo, thay đổi nào từng được áp dụng, hay dữ liệu đã được chuyển đổi qua các bước nào.

Cần phân biệt các mục tiêu:

| Mục tiêu | Câu hỏi | Công cụ/quy trình phù hợp |
|---|---|---|
| Ghi nhận schema hiện tại | Database đang có những đối tượng nào? | **generate-changelog** |
| So sánh hai database/schema | Target khác reference ở đâu? | **diff** hoặc công cụ so sánh phù hợp |
| Tạo migration từ khác biệt | Cần thay đổi gì để target khớp reference? | **diff-changelog** |
| Đưa database hiện hữu vào lịch sử Liquibase | Làm sao đánh dấu schema baseline đã có mà không chạy lại DDL? | Review baseline rồi dùng **changelog-sync** phù hợp |
| Quản lý dữ liệu lịch sử | Dữ liệu cũ cần chuẩn hóa hoặc chuyển đổi thế nào? | Changeset/job data migration riêng, có kiểm chứng |

Không được nhầm **generate-changelog** với một lệnh tự động áp dụng migration. Nó đọc metadata database và tạo file changelog; nhóm vẫn phải review, thử nghiệm và quyết định cách đưa kết quả vào lịch sử triển khai.

## 2. generate-changelog hoạt động ở mức nào?

Ở mức khái niệm, lệnh thực hiện các bước:

1. Kết nối tới database đích bằng JDBC URL và thông tin xác thực được cấu hình.
2. Dùng database metadata/snapshot để khám phá các schema và đối tượng mà Liquibase cùng database implementation nhận diện được.
3. Chuyển cấu trúc đã đọc thành những change type/changeset tương ứng trong changelog.
4. Ghi kết quả ra file theo định dạng và đường dẫn được chỉ định.
5. Không tự động áp dụng các changeset vừa tạo vào database đang được đọc.

Kết quả có thể mô tả những đối tượng như table, column, primary key, foreign key, unique constraint, index, sequence hoặc view tùy DBMS, phiên bản Liquibase, quyền truy cập, extension và loại đối tượng. Mức độ hỗ trợ không đồng đều: trigger, stored procedure, package, grant/permission, synonym, materialized view, partitioning, database-specific option hoặc metadata đặc thù có thể cần xử lý riêng.

**Một snapshot không phải lịch sử thay đổi.** Ví dụ, database hiện có cột **status VARCHAR(30) NOT NULL DEFAULT 'NEW'**. generate-changelog có thể mô tả cột với các thuộc tính hiện tại, nhưng không thể tự biết trước đó cột từng nullable, từng có default khác hay dữ liệu đã được chuyển đổi ra sao.

Công cụ cũng không thể tự suy luận ý nghĩa nghiệp vụ của tên bảng/cột. Một cột **legacy_code** có thể đang được ứng dụng bên ngoài sử dụng; việc thấy nó trong snapshot không chứng minh rằng có thể xóa hoặc đổi tên an toàn.

## 3. Chuẩn bị trước khi chạy

### 3.1. Chọn database nguồn có trạng thái đại diện

Xác định database nào sẽ làm **nguồn baseline**. Có thể chọn production làm nguồn phản ánh schema chuẩn, hoặc một bản sao production đã được kiểm chứng. Không nên chọn một môi trường dev đã bị thay đổi thủ công và mặc định rằng mọi môi trường khác giống hệt.

Nếu có nhiều môi trường, cần so sánh trước để phát hiện drift:

- Schema nào là chuẩn?
- Có bảng/cột chỉ tồn tại ở một môi trường không?
- Có constraint/index bị thiếu hoặc đặt tên khác không?
- Có object do DBA tạo ngoài quy trình không?
- Có sự khác nhau do phiên bản DBMS hoặc extension không?

Nếu schema giữa các môi trường khác nhau, không nên tạo một baseline riêng tùy tiện cho từng nơi rồi gọi chúng là cùng một phiên bản. Hãy xác định drift, nguyên nhân và kế hoạch chuẩn hóa.

### 3.2. Dùng quyền chỉ đọc khi có thể

generate-changelog chủ yếu cần đọc metadata và catalog của database. Tài khoản kết nối nên có quyền đọc metadata cần thiết trong các schema được khảo sát. Nếu có thể, dùng tài khoản **read-only** cho bước snapshot để giảm nguy cơ thao tác nhầm trên database legacy.

Tài khoản này cần đủ quyền nhìn thấy các đối tượng cần đưa vào baseline. Nếu thiếu quyền, kết quả có thể không đầy đủ dù lệnh kết thúc thành công. Hãy kiểm tra quyền truy cập theo schema/owner và đối chiếu kết quả với inventory database.

### 3.3. Xác định schema và phạm vi

Cần biết rõ database/catalog và schema mặc định; những schema ứng dụng cần quản lý; schema hệ thống hoặc schema của công cụ cần bỏ qua; có cần giữ tên object, schemaName, catalogName và tablespace không; và những object được quản lý bởi hệ thống khác mà không nên đưa vào baseline.

Việc chọn phạm vi ảnh hưởng trực tiếp đến nội dung snapshot. Nếu bỏ sót schema, changelog sinh ra không thể được coi là mô tả đầy đủ database.

### 3.4. Ghi nhận phiên bản công cụ và DBMS

Lưu lại phiên bản Liquibase, edition/license, JDBC driver, DBMS và phiên bản DBMS. Snapshot từ hai phiên bản công cụ hoặc hai DBMS khác nhau có thể tạo đầu ra khác nhau, đặc biệt với metadata đặc thù.

## 4. Chạy generate-changelog bằng CLI

Cú pháp tổng quát:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-host:5432/appdb" \
  --username="liquibase_reader" \
  --changelog-file="db/changelog/baseline/db.changelog.yaml" \
  generate-changelog
~~~

Ví dụ dùng PostgreSQL để minh họa. URL, schema, user và đường dẫn cần thay bằng cấu hình thật. Không đưa password trực tiếp vào lệnh trong lịch sử shell, log CI hoặc tài liệu. Dùng cơ chế cấu hình/secret được dự án phê duyệt như defaults file được bảo vệ, biến môi trường hoặc secret manager.

Một cách khác là cấu hình tham số trong defaults file, sau đó gọi:

~~~bash
liquibase --defaults-file=liquibase.properties \
  --changelog-file=db/changelog/baseline/db.changelog.yaml \
  generate-changelog
~~~

Nội dung defaults file không nên commit nếu chứa credential. Có thể lưu một mẫu không có bí mật và cung cấp thông tin thật qua secret của môi trường.

**Đường dẫn changelog đầu ra phải rõ ràng và thuộc repository của dự án.** Trước khi chạy, bảo đảm file đích chưa chứa nội dung cần giữ. Nếu phiên bản CLI có tùy chọn ghi đè, chỉ sử dụng khi đã kiểm tra chính xác file đích và có bản sao lưu; không để một lần generate vô tình thay thế baseline đã được review hoặc đã phát hành.

Tên command và tham số có thể thay đổi theo phiên bản Liquibase. Luôn xác nhận:

~~~bash
liquibase --version
liquibase --help
~~~

Nếu dùng Liquibase chạy trong container hoặc build tool, phải kiểm tra đúng binary/JAR mà pipeline sẽ dùng, không chỉ phiên bản cài trên máy lập trình.

## 5. Kết quả sinh ra là bản nháp, cần review

Một changelog sinh tự động thường có nhiều changeset, tên ID/author và thứ tự được tạo dựa trên snapshot. Không nên commit ngay mà không đọc nội dung.

Những điểm cần review:

1. **Đúng phạm vi**: có đủ schema/object mong muốn, không lẫn object hệ thống hoặc object ngoài quyền quản lý.
2. **Đúng tên và kiểu dữ liệu**: kiểm tra column type, length, precision, scale, default, nullability.
3. **Đúng constraint**: primary key, unique, foreign key, check và thứ tự phụ thuộc.
4. **Đúng index**: tên, cột, thứ tự cột, uniqueness, điều kiện/option đặc thù.
5. **Đúng view và SQL**: truy vấn view có đầy đủ nội dung, schema qualification và phụ thuộc.
6. **Đúng object đặc thù DBMS**: sequence, trigger, procedure, partition, synonym, tablespace, quyền hoặc extension.
7. **Không có object trùng hoặc thiếu**: đối chiếu với catalog và công cụ quản trị database.
8. **Có thể chạy trên database trống**: changelog baseline phải tạo được cấu trúc tương đương nguồn trong môi trường thử nghiệm.

Một số đầu ra có thể chứa những changeset khó đọc hoặc metadata lặp lại. Có thể chuẩn hóa ID, author, comment, tách file hoặc sắp xếp lại **trước khi baseline được ghi nhận**. Sau khi changeset đã được triển khai và ghi vào DATABASECHANGELOG, không tùy tiện sửa ID, author, nội dung hay đường dẫn vì có thể làm thay đổi định danh và checksum.

### Ví dụ một phần changelog được sinh hoặc chuẩn hóa

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-create-customer"
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
              - column:
                  name: status
                  type: VARCHAR(30)
                  defaultValue: NEW
                  constraints:
                    nullable: false

  - changeSet:
      id: "baseline-002-create-sales-order"
      author: "platform"
      changes:
        - createTable:
            tableName: sales_order
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
      id: "baseline-003-fk-sales-order-customer"
      author: "platform"
      changes:
        - addForeignKeyConstraint:
            baseTableName: sales_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_sales_order_customer
~~~

Đây là **ví dụ minh họa cấu trúc**, không phải đầu ra được xác nhận của một phiên bản Liquibase cụ thể. Changelog thực tế có thể khác về cách tạo constraint, ID, author, schemaName, default và thứ tự. Không chép ví dụ này đè lên kết quả snapshot mà chưa đối chiếu catalog database.

## 6. Chọn định dạng đầu ra và tổ chức file

Liquibase hỗ trợ nhiều định dạng changelog như XML, YAML, JSON và formatted SQL tùy command/version. Hãy dùng định dạng được runtime của dự án hỗ trợ và thống nhất trong repository.

Một cách tổ chức dễ bảo trì:

~~~text
db/
└── changelog/
    ├── db.changelog-master.yaml
    ├── baseline/
    │   └── db.changelog-baseline.yaml
    ├── changes/
    │   ├── 2026/
    │   │   ├── 001-add-customer-region.yaml
    │   │   └── 002-create-audit-table.yaml
    └── data/
        └── reference-data.yaml
~~~

Master changelog có thể include baseline trước rồi include những thay đổi mới:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/db.changelog-baseline.yaml
      relativeToChangelogFile: true
  - includeAll:
      path: changes
      relativeToChangelogFile: true
~~~

Ví dụ trên cần được kiểm tra với phiên bản Liquibase và cấu trúc thư mục thực tế. **Đường dẫn changelog là một phần của định danh changeset** trong lịch sử; giữ ổn định vị trí hoặc sử dụng logicalFilePath có chủ đích trước khi triển khai. Đổi tên/di chuyển file sau baseline có thể khiến Liquibase nhận diện changeset khác với lịch sử cũ nếu không quản lý logical path đúng cách.

Không nên include thư mục chứa cả file baseline và các bản export thử nghiệm. Nếu dùng includeAll, hãy bảo đảm mọi file trong thư mục đều được kiểm soát và thứ tự được xác định theo quy tắc của Liquibase/phiên bản đang dùng.

## 7. generate-changelog khác diff và diff-changelog thế nào?

### 7.1. generate-changelog: chụp trạng thái hiện tại

Lệnh đọc một database và tạo changelog mô tả các object được nhận diện. Nó trả lời:

> “Schema hiện tại của database này gồm những gì?”

Đây là lựa chọn tự nhiên khi bắt đầu tiếp nhận một database legacy chưa có baseline Liquibase.

### 7.2. diff: so sánh reference và target

**diff** so sánh hai database/schema theo vai trò reference và target, rồi báo các khác biệt được nhận diện. Nó trả lời:

> “Hai trạng thái schema đang khác nhau ở đâu?”

Cần xác định đúng hướng reference/target và cấu hình kết nối. Nếu đảo nhầm, diễn giải “đối tượng thiếu” và “đối tượng thừa” cũng có thể bị đảo.

### 7.3. diff-changelog: tạo migration từ khác biệt

**diff-changelog** dùng kết quả so sánh để tạo changelog biểu diễn những thay đổi cần thiết nhằm đưa một phía về gần phía tham chiếu theo hướng command hỗ trợ. Nó trả lời:

> “Cần tạo những changeset nào để mô tả khác biệt giữa hai trạng thái?”

Đầu ra cũng là bản nháp cần review. Không được chạy diff-changelog lên production rồi tự động update mà chưa xem SQL và tác động dữ liệu.

| Tiêu chí | generate-changelog | diff | diff-changelog |
|---|---|---|---|
| Nguồn đầu vào chính | Một database | Reference và target | Reference và target |
| Kết quả | Changelog mô tả schema hiện tại | Báo cáo khác biệt | Changelog mô tả thay đổi từ khác biệt |
| Mục tiêu thường dùng | Tạo baseline cho legacy DB | Phát hiện drift | Tạo bản nháp migration |
| Có tự áp DDL không? | Không | Không | Không |
| Cần review? | Có | Có | Có, đặc biệt trước update |

Để tiếp nhận một database legacy, generate-changelog thường là bước đầu. Khi cần xác minh các môi trường đã drift sau khi baseline được thiết lập, diff hoặc công cụ so sánh schema phù hợp có thể hữu ích.

## 8. Phạm vi đối tượng và giới hạn snapshot

Không nên giả định generate-changelog bao quát mọi đặc điểm của database. Kết quả phụ thuộc DBMS và phiên bản database; Liquibase core version, edition và license; JDBC driver; extension hoặc snapshot generator bổ sung; quyền đọc metadata của user; schema/catalog được chỉ định; loại object và khả năng introspection của database implementation.

Các object thường cần kiểm tra riêng:

| Loại object | Điều cần xem lại |
|---|---|
| Table/column | Kiểu dữ liệu, identity, generated column, default, nullability |
| Primary key/unique | Tên, cột, thứ tự, constraint ownership |
| Foreign key | Bảng/cột tham chiếu, onDelete/onUpdate, deferrability |
| Index | Cột, thứ tự, uniqueness, expression/partial index |
| View/materialized view | SQL definition, dependency, refresh behavior |
| Sequence | Start/increment/cache, ownership với cột |
| Trigger | Timing, event, function được gọi, body SQL |
| Procedure/function/package | Body, delimiter, language, dependency và quyền |
| Grant/role/permission | Principal, privilege, default privilege |
| Partition/table options | Cấu trúc partition, storage, engine-specific metadata |
| Synonym/type/domain | Hỗ trợ snapshot và biểu diễn changelog theo DBMS |

Nếu một object không được sinh ra, không nên mặc định nó không tồn tại. Hãy so sánh với catalog database, script quản trị và tài liệu của DBMS. Có thể cần viết SQL/extension riêng cho những object đặc thù.

### 8.1. Schema snapshot không phải data migration

generate-changelog chủ yếu được dùng để mô tả cấu trúc schema. **Không coi file baseline sinh ra là bản sao toàn bộ các hàng dữ liệu hoặc lịch sử chuyển đổi dữ liệu**. Nếu cần tiếp nhận dữ liệu tham chiếu, dữ liệu seed hoặc chuyển đổi hàng cũ, hãy thiết kế bước riêng bằng loadData, insert/update changeset hoặc job backfill có kiểm chứng.

Ví dụ, snapshot có thể thể hiện bảng **country** với các cột id/code/name, nhưng không tự quyết định bộ dữ liệu currency/country nào là chuẩn nghiệp vụ. Việc quản lý dữ liệu tham chiếu cần nguồn dữ liệu, version và quy trình riêng.

## 9. Đưa database hiện hữu vào quản lý: baseline và changelog-sync

Đây là bước dễ gây sự cố nhất khi tiếp nhận database legacy.

Sau khi generate-changelog, changelog mô tả các đối tượng **đang tồn tại**. Nếu kết nối tới chính database đó rồi chạy **update**, Liquibase thấy các changeset baseline chưa có trong DATABASECHANGELOG và có thể cố thực hiện CREATE TABLE/ADD CONSTRAINT lần nữa. Điều này thường dẫn đến lỗi “already exists” hoặc thay đổi ngoài dự kiến.

### Hướng A — Database trống: thực thi baseline

Với một database mới, chưa có các đối tượng ứng dụng, chạy:

~~~bash
liquibase --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml update
~~~

Liquibase thực thi các changeset baseline để dựng schema. Đây là phép thử quan trọng: changelog sinh từ legacy DB có thực sự tái tạo được cấu trúc mong muốn trên database trống hay không?

### Hướng B — Database legacy đã có schema: đồng bộ lịch sử

Với database đã có đúng cấu trúc được mô tả bởi baseline, dùng **changelog-sync** để đánh dấu các changeset chưa được ghi nhận là đã thực thi, **mà không chạy các change DDL/DML của chúng**:

~~~bash
liquibase --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml changelog-sync
~~~

Cần xác nhận cú pháp và khả năng của phiên bản Liquibase thực tế. Có thể xem trước SQL bằng **changelog-sync-sql** nếu phiên bản cung cấp:

~~~bash
liquibase --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml changelog-sync-sql
~~~

**changelog-sync không sửa schema để khớp changelog.** Nó chỉ đồng bộ lịch sử: ghi nhận các changeset như đã chạy. Nếu baseline mô tả cột A NOT NULL nhưng database thực tế vẫn nullable, việc sync có thể làm Liquibase tin rằng baseline đã hoàn tất dù schema còn sai. Do đó, **chỉ sync sau khi đã chứng minh schema thật khớp baseline**.

### Tách baseline khỏi thay đổi mới

Một quy trình dễ kiểm soát:

1. Tạo changelog baseline từ database nguồn.
2. Review và chuẩn hóa baseline.
3. Thử update baseline trên database trống, so sánh schema kết quả với database legacy.
4. Trên mỗi database legacy đã được xác minh khớp, chạy changelog-sync chỉ với baseline.
5. Giữ baseline bất biến và include nó trong master changelog.
6. Đưa thay đổi mới vào changeset mới sau baseline.
7. Những database mới chạy update sẽ thực thi baseline rồi thay đổi mới; database legacy đã sync baseline sẽ chỉ thực thi thay đổi mới.

**Không chạy changelog-sync trên master chứa cả changeset mới chưa triển khai.** Lệnh có thể đánh dấu cả những thay đổi mới đó là đã chạy dù DDL chưa được áp dụng. Nếu dùng master file, phải giới hạn chính xác phạm vi bằng cách được phiên bản hỗ trợ và đã kiểm chứng; cách đơn giản hơn là dùng file baseline riêng khi đồng bộ.

## 10. Ví dụ tiếp nhận một database legacy

Giả sử database **appdb** đã có schema **app** với bảng customer, sales_order và payment. Chưa có DATABASECHANGELOG của Liquibase.

### Bước 1 — Chụp schema

Kết nối bằng user có quyền đọc metadata và chạy generate-changelog vào file baseline:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-host:5432/appdb" \
  --username="liquibase_reader" \
  --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml \
  generate-changelog
~~~

Không đưa password vào lệnh. Dùng secret/cấu hình được bảo vệ. Kiểm tra changelog sinh ra có mô tả đúng schema app và không lẫn schema không thuộc ứng dụng.

### Bước 2 — Review và thử dựng mới

Tạo database thử nghiệm trống trên cùng DBMS/version, rồi chạy:

~~~bash
liquibase \
  --url="jdbc:postgresql://test-host:5432/appdb_empty" \
  --username="migration_user" \
  --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml \
  update
~~~

Sau khi update, so sánh catalog schema mới với database legacy. Kiểm tra table, column, PK/FK, index, sequence, view và object đặc thù. Nếu baseline không tái tạo được một object quan trọng, phải bổ sung migration/SQL hỗ trợ trước khi coi baseline hoàn chỉnh.

### Bước 3 — Xác minh database legacy

Trên database legacy, kiểm tra schema thực tế có khớp changelog đã review. Có thể dùng catalog DBMS, công cụ so sánh schema hoặc snapshot/diff phù hợp. Kiểm tra cả kiểu dữ liệu, default, constraint, index và object đặc thù, không chỉ tên bảng.

Nếu có khác biệt, phân loại:

- **Drift không mong muốn**: cần sửa môi trường hoặc migration để đưa về chuẩn.
- **Khác biệt có chủ đích**: phải mô tả rõ điều kiện môi trường hoặc tách thay đổi theo DBMS.
- **Object không được snapshot**: bổ sung SQL/extension và kiểm chứng riêng.
- **Khác biệt dữ liệu**: xử lý bằng quy trình data migration, không sửa baseline schema để che vấn đề.

### Bước 4 — Đồng bộ lịch sử baseline

Chỉ khi schema khớp, chạy:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-host:5432/appdb" \
  --username="migration_user" \
  --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml \
  changelog-sync
~~~

Lệnh không tạo lại bảng. Nó ghi nhận baseline changeset trong DATABASECHANGELOG. Trước khi chạy trên môi trường thật, xem changelog-sync-sql nếu có, kiểm tra phạm vi changeset, quyền truy cập và kế hoạch phục hồi.

### Bước 5 — Thêm thay đổi mới bằng changeset riêng

Sau baseline, một yêu cầu mới như thêm cột **region** được thể hiện bằng changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-add-customer-region"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region
                  type: VARCHAR(40)
~~~

Trên database legacy đã sync baseline, changeset mới sẽ được thực thi. Trên database mới, update sẽ chạy baseline rồi chạy changeset mới. Cần thử cả hai đường để chứng minh trạng thái cuối tương đương.

## 11. Quản lý nhiều môi trường sau khi tạo baseline

Giả sử có development, staging và production. Tất cả đều được dự định quản lý bởi một changelog baseline.

Không nên tạo baseline độc lập từ từng môi trường rồi đặt cùng tên release mà không so sánh. Nếu development có một cột debug hoặc production thiếu index, ba file baseline sẽ mô tả ba schema khác nhau và lịch sử khó hợp nhất.

Một cách làm:

| Môi trường | Kiểm tra trước | Hành động baseline |
|---|---|---|
| Development | So sánh với schema chuẩn, xác định object thử nghiệm | Chuẩn hóa hoặc loại object ngoài phạm vi rồi sync |
| Staging | Xác minh tương đương schema release | Sync baseline sau review |
| Production | Xác minh đầy đủ schema, quyền, object đặc thù và backup | Chạy sync theo change window được duyệt |
| Database mới | Đảm bảo chưa có object ứng dụng | Chạy update baseline |

Nếu production có khác biệt cần thiết, không nên che bằng một changeset baseline được sync mà không giải thích. Có thể cần một nhánh migration riêng, precondition hoặc changeset theo DBMS/context/label; tuy nhiên mọi khác biệt phải có lý do và bằng chứng.

Sau khi baseline được ghi nhận, **không thay đổi baseline để phản ánh một schema mới**. Thay đổi tiếp theo phải được ghi bằng changeset mới để bảo toàn lịch sử và checksum. Nếu buộc phải sửa baseline trước khi bất kỳ môi trường nào sync, hãy thống nhất phiên bản baseline đầu tiên và kiểm thử lại toàn bộ.

## 12. Đặt tên, định danh và checksum của baseline

Liquibase nhận diện changeset bằng tổ hợp ID, author và đường dẫn changelog (có thể dùng **logicalFilePath** để quản lý đường dẫn logic). Snapshot sinh tự động có thể tạo ID/author chưa phù hợp quy ước của tổ chức. Nên chuẩn hóa **trước khi baseline được áp dụng**:

- ID có ý nghĩa hoặc theo quy ước dễ truy vết.
- Author phản ánh nhóm sở hữu migration, không phụ thuộc tài khoản cá nhân của máy chạy snapshot.
- Đường dẫn changelog ổn định trong repository.
- Tên schema/table/constraint/index rõ ràng, giữ nguyên tên hiện tại nếu đó là contract đang được sử dụng.
- Các object đặc thù được tách hoặc chú thích để reviewer hiểu lý do.
- Baseline có commit/tag riêng để biết snapshot xuất phát từ trạng thái nào.

Khi changeset baseline được changelog-sync hoặc update và ghi vào DATABASECHANGELOG, Liquibase lưu checksum cho định nghĩa được ghi nhận. Sửa nội dung, ID, author hoặc đường dẫn sau đó có thể gây thay đổi định danh/checksum và khiến các môi trường đã sync không còn khớp.

Vì vậy, baseline cần được xem là **mốc bất biến sau khi đã đưa vào lịch sử**. Nếu phát hiện thiếu object sau khi sync, hãy tạo changeset mới bổ sung object đó hoặc thực hiện kế hoạch đồng bộ lịch sử có kiểm soát; không chỉnh baseline cũ tùy tiện và không chạy clear-checksums để che lỗi.

## 13. generate-changelog có tạo rollback không?

Changelog sinh từ schema hiện tại thường biểu diễn cách **tạo** các object hiện có. Điều đó không có nghĩa rollback sinh tự động luôn là cách an toàn để quay lại trạng thái trước khi tiếp nhận.

Ví dụ, baseline có createTable customer; rollback có thể là dropTable customer. Trên database legacy chứa dữ liệu khách hàng thật, rollback đó có thể xóa toàn bộ bảng. Vì vậy:

- **Database mới**: rollback baseline có thể phù hợp để dọn môi trường thử nghiệm nếu chấp nhận xóa toàn bộ object.
- **Database legacy đã sync baseline**: không nên rollback baseline như một thao tác “undo việc tiếp nhận”. Changelog-sync chỉ ghi lịch sử, còn schema/dữ liệu đã tồn tại từ trước; dropTable sẽ phá hủy dữ liệu thật.
- **Release mới sau baseline**: rollback những changeset mới cần xem xét tác động và thứ tự phụ thuộc riêng; không rollback lẫn baseline nếu không có kế hoạch phá hủy rõ ràng.
- **Khôi phục khi có sự cố**: backup/PITR và roll-forward có thể phù hợp hơn việc drop/recreate schema.

Một baseline là bản mô tả trạng thái ban đầu, không phải snapshot dữ liệu có thể phục hồi. Cần có backup và phương án disaster recovery độc lập.

## 14. Dữ liệu tham chiếu và dữ liệu nghiệp vụ khi tiếp nhận

Schema snapshot không giải quyết toàn bộ câu chuyện dữ liệu:

- **Dữ liệu nghiệp vụ** như customer, invoice, payment phải được bảo toàn; không đưa chúng vào một rollback baseline phá hủy.
- **Dữ liệu tham chiếu** như country code, currency hoặc trạng thái có thể cần quản lý phiên bản, nhưng phải xác định nguồn chuẩn và chính sách cập nhật.
- **Dữ liệu cấu hình** có thể khác theo môi trường; không đưa secret hoặc endpoint cụ thể vào changelog.
- **Dữ liệu lịch sử** có thể cần chuẩn hóa hoặc chuyển đổi; cần job/changeset DML riêng có precondition, checkpoint, audit và kế hoạch phục hồi.

Ví dụ, bảng **currency** tồn tại với các mã ISO. generate-changelog có thể mô tả cấu trúc bảng và constraint, nhưng không tự quyết định bộ dữ liệu currency nào là chuẩn. Nếu nhóm cần đưa dữ liệu tham chiếu vào Liquibase, có thể sử dụng loadData, insert hoặc một quy trình nạp dữ liệu có version. Trước khi triển khai, kiểm tra khóa tự nhiên, dữ liệu trùng, thứ tự phụ thuộc và hành vi khi chạy lại.

Không nên đưa hàng triệu dòng nghiệp vụ vào changelog baseline chỉ để “Liquibase biết chúng tồn tại”. Điều đó làm artifact nặng, tăng rủi ro lộ dữ liệu và khó triển khai qua môi trường.

## 15. Precondition và các kiểm tra bảo vệ khi áp dụng baseline

Sau khi baseline được đồng bộ, các changeset mới có thể sử dụng precondition để kiểm tra trạng thái dự kiến. Ví dụ một migration thêm cột chỉ chạy khi bảng tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-add-customer-region"
      author: "platform"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region
                  type: VARCHAR(40)
~~~

Precondition giúp phát hiện thiếu phụ thuộc hoặc kết nối nhầm database, nhưng không thay thế kiểm tra schema toàn diện. Nếu dùng **MARK_RAN**, Liquibase có thể ghi nhận changeset mà không chạy change; chỉ dùng khi trạng thái đích thực sự đã tồn tại và có kiểm chứng. Nếu không, lịch sử có thể nói đã triển khai trong khi object vẫn thiếu.

Với database legacy có drift, không nên dùng precondition để “cho qua” mọi sai khác. Hãy phân loại nguyên nhân và quyết định một changeset sửa chữa hoặc chuẩn hóa rõ ràng.

## 16. Kiểm tra baseline bằng validate, status, update-sql và diff

~~~bash
liquibase --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml validate
liquibase --changelog-file=db/changelog/baseline/db.changelog-baseline.yaml status --verbose
~~~

- **validate** kiểm tra cấu trúc changelog và những quy tắc validation mà phiên bản hỗ trợ.
- **status --verbose** giúp xem changeset nào Liquibase xem là chưa được triển khai trên database đang kết nối.
- Trên database trống, **update-sql** có thể xem SQL dự kiến để dựng baseline.
- Trên database legacy, **changelog-sync-sql** nếu khả dụng giúp xem SQL/metadata sẽ dùng để đồng bộ lịch sử thay vì tạo lại schema.
- **diff** hoặc công cụ so sánh phù hợp giúp kiểm tra trạng thái schema giữa database nguồn và database dựng từ baseline.

Các lệnh phải dùng đúng connection và đúng file. Không lấy kết quả validate trên database trống làm bằng chứng database legacy đã khớp. Không lấy status trên một database đã sync làm bằng chứng mọi object thật sự đúng nếu baseline chưa được đối chiếu.

Một kiểm chứng tốt có ba phần:

1. **Nguồn legacy**: catalog/schema hiện có đã được chụp và review.
2. **Database mới**: update baseline tạo được schema tương đương.
3. **Database legacy**: changelog-sync chỉ đánh dấu lịch sử sau khi schema đã khớp, rồi những changeset mới có thể chạy đúng.

## 17. Tích hợp với Spring Boot và CI/CD

Sau khi baseline được đưa vào repository, ứng dụng Spring Boot có thể dùng changelog master:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Nhưng cần phân biệt **hai loại database**:

- Database mới: Liquibase chạy update, thực thi baseline để tạo schema, sau đó chạy các changeset mới.
- Database legacy: trước lần để ứng dụng tự update, baseline phải được đồng bộ vào DATABASECHANGELOG bằng quy trình được kiểm soát. Nếu không, ứng dụng có thể cố chạy lại CREATE TABLE trên các object đã tồn tại.

Không nên để mỗi instance ứng dụng tự xử lý việc tiếp nhận baseline trong lần khởi động đầu tiên nếu chưa có kế hoạch điều phối. Có thể dùng một migration job riêng trong CI/CD để xác minh kết nối, sync baseline trên database legacy, sau đó mới bật cơ chế update bình thường cho các release tiếp theo.

Một pipeline có thể gồm:

1. Đóng gói baseline và master changelog cùng artifact có commit xác định.
2. Chạy validate và kiểm tra file đầu ra đã được review.
3. Trên database mới, thử update baseline và so sánh schema.
4. Trên bản sao database legacy, xác minh schema và thử changelog-sync.
5. Kiểm tra DATABASECHANGELOG sau sync: baseline changeset đã được ghi nhận, không có DDL tạo lại object.
6. Chạy changeset mới trên bản sao để kiểm tra đường nâng cấp sau baseline.
7. Triển khai theo từng môi trường, lưu log, phiên bản Liquibase và bằng chứng schema.
8. Sau khi baseline ổn định, chỉ thêm changeset mới cho các thay đổi tiếp theo.

Pipeline phải phân biệt rõ **generate**, **review**, **sync** và **update**. Không tự động generate changelog mới từ production trong mỗi lần deploy rồi chạy ngay; cách đó khiến artifact thay đổi theo trạng thái môi trường và phá tính tái lập.

## 18. Những lỗi thường gặp khi tiếp nhận database legacy

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Changelog thiếu bảng/cột | User không có quyền đọc metadata, sai schema hoặc snapshot không hỗ trợ object | Kiểm tra quyền, schema/catalog, DBMS và object support |
| Changelog có object hệ thống | Phạm vi snapshot quá rộng | Giới hạn schema/object, review và loại object ngoài phạm vi |
| update trên database legacy báo already exists | Chưa sync baseline; Liquibase xem changeset là pending | Xác minh schema rồi dùng changelog-sync đúng phạm vi |
| changelog-sync xong nhưng schema vẫn thiếu object | Đã sync dù baseline không khớp thực tế hoặc precondition MARK_RAN | So sánh catalog, bổ sung changeset sửa chữa, không sửa lịch sử mù quáng |
| Database mới dựng không giống legacy | Snapshot thiếu object, DDL đặc thù, dependency/ordering | Kiểm thử trên cùng DBMS, bổ sung SQL/extension |
| Staging chạy được, production khác | Schema drift, version/driver/permissions khác | So sánh từng môi trường và chuẩn hóa baseline |
| Changelog tạo quá nhiều changeset khó review | Snapshot lớn, object name/ID tự sinh | Chia file theo nhóm, chuẩn hóa trước khi sync |
| Sau khi đổi tên file xuất hiện changeset mới | Đường dẫn filename tham gia định danh | Giữ path ổn định hoặc dùng logicalFilePath có kế hoạch |
| Rollback baseline có nguy cơ xóa dữ liệu | Rollback createTable thường dropTable | Không rollback baseline trên legacy; dùng backup/restore hoặc kế hoạch khác |
| Dữ liệu tham chiếu bị thiếu | Schema snapshot không đại diện đầy đủ data migration | Quản lý dữ liệu riêng bằng changeset/job |
| View/procedure không đầy đủ | DBMS/extension/snapshot không nhận diện toàn bộ definition | Kiểm tra catalog và bổ sung SQL có kiểm thử |
| Checksum mismatch sau khi sửa baseline | Changeset đã được sync/deploy bị chỉnh sửa | Giữ nguyên lịch sử, tạo changeset mới và điều tra checksum |

## 19. Checklist review trước khi chấp nhận baseline

Trước khi đưa changelog được sinh vào repository và đồng bộ lịch sử:

- Đã chọn đúng database nguồn đại diện và xác định schema chuẩn?
- Đã ghi lại phiên bản Liquibase, edition, JDBC driver và DBMS/version?
- User kết nối có quyền đọc đầy đủ metadata của mọi schema cần quản lý?
- Phạm vi snapshot có bỏ qua schema hệ thống và object ngoài quyền quản lý?
- Đã review table, column, type, default, nullability, PK, FK, unique, check và index?
- Đã kiểm tra view, sequence, trigger, procedure và object đặc thù DBMS?
- Đã xác định những object snapshot không hỗ trợ hoặc không sinh đủ?
- Đã phân biệt schema baseline với dữ liệu nghiệp vụ/reference data?
- Changelog có ID/author/filename ổn định trước khi ghi lịch sử?
- Database trống đã dựng được schema từ baseline và được so sánh với nguồn?
- Database legacy đã được chứng minh khớp baseline trước khi changelog-sync?
- Changelog-sync chỉ chạy trên baseline, không vô tình đánh dấu changeset mới là đã triển khai?
- Đã kiểm tra DATABASECHANGELOG sau sync và xác minh không chạy lại DDL?
- Có kế hoạch riêng cho drift giữa dev/staging/production?
- Baseline đã được giữ bất biến sau khi đưa vào lịch sử?
- Rollback baseline có được hiểu rõ là có thể phá hủy dữ liệu và không dùng như thao tác undo thông thường?
- Pipeline phân biệt rõ generate, review, sync, update và kiểm chứng hậu triển khai?

**Kết luận:** **generate-changelog** là bước khởi đầu hữu ích để tiếp nhận một database legacy bằng cách tạo bản nháp changelog từ schema hiện tại. Đầu ra phải được review và kiểm chứng trên database mới lẫn database đã tồn tại. Với database legacy, sau khi chứng minh schema khớp baseline, **changelog-sync** giúp ghi nhận các changeset baseline mà không chạy lại DDL; sau đó các thay đổi mới được quản lý bằng changeset mới. Giữ baseline ổn định, quản lý dữ liệu riêng, kiểm tra drift giữa môi trường và hiểu rõ rủi ro rollback sẽ giúp đưa Liquibase vào hệ thống hiện hữu mà không làm gián đoạn dữ liệu và lịch sử vận hành.

