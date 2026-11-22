# Phân biệt cơ sở dữ liệu đã có cấu trúc với cơ sở dữ liệu mới

Khi đưa Liquibase vào một hệ thống, câu hỏi đầu tiên không chỉ là “changelog nào cần chạy?” mà là **database đích đang ở trạng thái nào?** Một database mới thường chưa có bảng nghiệp vụ và chưa có lịch sử Liquibase. Một database đã tồn tại có thể chứa nhiều bảng, dữ liệu, trigger, view, quyền và thay đổi thủ công qua nhiều năm. Chạy cùng một changelog tạo bảng lên cả hai nơi mà không phân biệt trạng thái có thể gây lỗi trùng đối tượng, bỏ sót cấu trúc hoặc làm sai lệch dữ liệu.

Bài học thuộc chương **Tiếp nhận CSDL** của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này giải thích cách nhận diện database mới và database đã có cấu trúc, lựa chọn quy trình khởi tạo tương ứng và tiếp nhận hệ thống cũ vào lịch sử Liquibase một cách có kiểm soát.

## 1. Hai trạng thái xuất phát khác nhau

**Database mới (fresh database)** là database hoặc schema được chuẩn bị để ứng dụng khởi tạo từ đầu. Thông thường chưa có các bảng nghiệp vụ, dữ liệu vận hành và lịch sử changeset. Liquibase có thể thực thi chuỗi migration ban đầu để tạo schema.

**Database đã có cấu trúc (existing/legacy database)** là database đã có một phần hoặc toàn bộ schema cần cho ứng dụng. Nó có thể được tạo bởi DBA, script SQL cũ, framework ORM, công cụ triển khai trước đây hoặc nhiều quy trình khác nhau. Database có thể đã có dữ liệu quan trọng và chưa có bảng lịch sử Liquibase.

Hai trạng thái này không chỉ khác nhau ở việc “có bảng hay chưa”. Cần xét đồng thời ít nhất ba lớp:

1. **Schema thực tế:** bảng, cột, kiểu dữ liệu, khóa, index, view, trigger, routine, sequence, partition, synonym, quyền và các đối tượng khác.
2. **Dữ liệu thực tế:** bản ghi nghiệp vụ, dữ liệu danh mục, giá trị mặc định, dữ liệu đã backfill, sequence hiện tại và những bất biến cần giữ.
3. **Lịch sử thay đổi:** bảng `DATABASECHANGELOG` có tồn tại không, đã ghi những changeset nào, đường dẫn `FILENAME` và checksum ra sao.

| Đặc điểm | Database mới | Database đã có cấu trúc |
|---|---|---|
| Bảng nghiệp vụ | Thường chưa có. | Có thể đã có một phần hoặc đầy đủ. |
| Dữ liệu | Trống hoặc chỉ có dữ liệu khởi tạo được kiểm soát. | Có thể chứa dữ liệu thật, không thể xóa để chạy lại từ đầu. |
| `DATABASECHANGELOG` | Thường chưa có lịch sử. | Có thể chưa tồn tại, đã tồn tại hoặc chỉ ghi một phần lịch sử. |
| Cách bắt đầu | Chạy baseline/schema creation migrations theo thứ tự. | Kiểm kê, đối chiếu và thiết lập baseline/history trước khi chạy thay đổi mới. |
| Rủi ro nổi bật | Changelog thiếu đối tượng, sai thứ tự, cấu hình môi trường. | Trùng đối tượng, schema drift, mất dữ liệu, lịch sử không khớp. |
| Bằng chứng cần có | Schema sau migration khớp thiết kế. | Schema và dữ liệu trước/sau tiếp nhận được đối chiếu, không bị ghi đè ngoài ý muốn. |

**Lưu ý:** database mới nhưng đã có bảng quản trị hoặc schema dùng chung vẫn cần kiểm tra trước khi chạy. Database cũ có thể chưa có bảng nghiệp vụ nào nếu từng bị xóa hoặc tạo dang dở. Tên môi trường “dev”, “staging” hay “production” không tự chứng minh trạng thái xuất phát.

## 2. Nhận diện trạng thái trước khi chạy Liquibase

Không nên chọn chiến lược chỉ dựa trên việc `DATABASECHANGELOG` có tồn tại hay không. Hãy thu thập bằng chứng từ kết nối và schema đích.

### 2.1. Kiểm tra kết nối và phạm vi schema

Trước tiên xác minh:

- JDBC URL trỏ đúng server, database/catalog và port.
- User kết nối có đúng quyền và default schema dự kiến.
- Database engine và phiên bản thực tế.
- Tên schema mà ứng dụng sử dụng, bao gồm schema mặc định của user.
- Liquibase sẽ tạo hoặc đọc bảng history trong schema nào.
- Các môi trường có đang trỏ vào cùng một database dùng chung hay không.

Một lệnh `status` chạy thành công trên nhầm database không phải bằng chứng rằng database cần triển khai đã sẵn sàng. Cần ghi nhận tên môi trường và database đích theo cách không làm lộ credentials.

### 2.2. Kiểm tra bảng lịch sử Liquibase

Theo cấu hình mặc định, Liquibase dùng hai bảng:

- `DATABASECHANGELOG`: ghi nhận changeset đã được xử lý, ID, author, filename, checksum, thời điểm và execution type.
- `DATABASECHANGELOGLOCK`: điều phối để nhiều tiến trình Liquibase không đồng thời cập nhật cùng lịch sử.

Truy vấn chỉ đọc khi bảng đã tồn tại và user có quyền:

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Kiểm tra khóa:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Nếu dự án tùy biến tên bảng history hoặc schema metadata, cần dùng đúng tên thực tế. **Không thấy `DATABASECHANGELOG` chưa đủ kết luận đây là database mới**: database cũ có thể được quản lý bằng công cụ khác hoặc DBA chưa từng bật Liquibase.

Ngược lại, thấy bảng history cũng chưa đủ chứng minh schema đang đúng. Bảng có thể thuộc ứng dụng khác, changelog khác hoặc ghi nhận changeset bằng `MARK_RAN` mà không thực thi SQL.

### 2.3. Kiểm kê schema thực tế

Trước khi tiếp nhận database cũ, lập danh mục đối tượng và đối chiếu ít nhất:

| Nhóm | Nội dung kiểm kê |
|---|---|
| Bảng và cột | Tên, schema, kiểu, độ dài, precision/scale, nullability, default, identity. |
| Ràng buộc | Primary key, foreign key, unique, check, thứ tự và tên constraint. |
| Index | Tên, cột, thứ tự, unique, expression, predicate/partial index nếu có. |
| Sequence/identity | Cách cấp ID, giá trị hiện tại, cache và quan hệ với cột. |
| View/materialized view | Định nghĩa SQL, phụ thuộc và quyền truy cập. |
| Procedure/function/trigger | Body, chữ ký, timing, event, owner và quyền thực thi. |
| Đối tượng DBMS | Extension, type, partition, synonym, schema, collation, tablespace. |
| Quyền | User/role, grant, owner, quyền mặc định và quyền trên object. |
| Dữ liệu | Số hàng, dữ liệu danh mục, bất biến nghiệp vụ, giá trị biên và trạng thái backfill. |

Không phải mọi công cụ diff đều so sánh đầy đủ mọi loại đối tượng hoặc dữ liệu. Hãy xác định phạm vi nào được công cụ kiểm tra và phần nào cần truy vấn hoặc kiểm toán riêng.

## 3. Quy trình cho database mới

Với database mới, mục tiêu là **xây schema từ lịch sử migration có thể tái tạo**. Changelog cần mô tả thứ tự tạo bảng, khóa, index, routine và dữ liệu khởi tạo. Một chuỗi ví dụ:

~~~text
001-create-schema-and-tables
002-add-primary-and-foreign-keys
003-create-indexes
004-create-views-and-routines
005-insert-reference-data
006-add-application-constraints
~~~

Đây là thứ tự minh họa; trong dự án thật, mỗi changeset cần ID ổn định và phụ thuộc được sắp xếp theo thiết kế.

### 3.1. Khởi tạo từ changelog

Một changelog YAML tối giản cho database mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: db-team
      changes:
        - createTable:
            tableName: customer_record
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
                    unique: true
~~~

Đây là một changeset mẫu; cú pháp identity, kiểu chuỗi, unique và SQL sinh ra cần được kiểm chứng trên DBMS cụ thể. Database mới không có dữ liệu để bảo vệ không có nghĩa có thể bỏ qua kiểm tra kiểu, constraint, thứ tự hoặc quyền.

Các bước thường dùng:

1. Tạo database/schema và user migration theo quy trình hạ tầng.
2. Cấu hình JDBC URL, default schema, changelog root và quyền cần thiết.
3. Chạy `validate` để kiểm tra cấu trúc changelog.
4. Chạy `status --verbose` để xem changeset chờ.
5. Xem SQL dự kiến bằng `update-sql` theo cú pháp phiên bản Liquibase đang dùng.
6. Chạy `update` trên database mới.
7. Đối chiếu schema và `DATABASECHANGELOG`, sau đó chạy smoke test ứng dụng.

### 3.2. Dữ liệu khởi tạo

Dữ liệu tham chiếu như loại trạng thái, đơn vị đo hoặc danh mục hệ thống có thể được nạp bằng changeset riêng. Cần phân biệt:

- **Reference data do ứng dụng sở hữu:** có thể nằm trong migration nếu được quản lý cùng phiên bản ứng dụng.
- **Dữ liệu người dùng hoặc dữ liệu vận hành:** không nên nhúng vào migration tạo schema như thể database luôn trống.
- **Dữ liệu bí mật/cá nhân:** không đưa vào changelog đã commit.

Nếu cần insert dữ liệu khởi tạo, hãy dùng ID/khóa ổn định, xác định unique key và chính sách khi database đã có dữ liệu. Không dùng `MARK_RAN` để bỏ qua một changeset insert khi chưa chứng minh dữ liệu tham chiếu đã tồn tại đúng giá trị.

## 4. Quy trình cho database đã có cấu trúc

Database cũ cần được tiếp nhận như một hệ thống đang vận hành. Mục tiêu không phải tạo lại bảng mà là **xác lập một điểm xuất phát có thể kiểm chứng**, sau đó để Liquibase quản lý các thay đổi tiếp theo.

### 4.1. Không chạy changelog tạo bảng lên database cũ một cách trực tiếp

Giả sử changelog có `createTable customer_record`, trong khi bảng này đã tồn tại trên production. Nếu Liquibase chưa có history ghi nhận changeset tạo bảng, nó có thể xem changeset là pending và thử chạy. Kết quả thường là lỗi “table already exists”, hoặc gây ảnh hưởng nghiêm trọng nếu có script cleanup/drop.

Trước khi chạy `update`, phải xác định:

1. Đối tượng hiện tại có đúng với định nghĩa changelog không?
2. Có thiếu hoặc thừa cột, index, constraint hay routine không?
3. Dữ liệu hiện tại có đáp ứng giả định của changeset tiếp theo không?
4. Có lịch sử từ công cụ khác hoặc script SQL cũ để đối chiếu không?
5. Changelog nào mô tả chính xác schema đang tồn tại tại thời điểm tiếp nhận?

### 4.2. Chọn một baseline có ý nghĩa

**Baseline** là mốc ghi nhận trạng thái schema đã được chấp nhận làm điểm bắt đầu quản lý bằng Liquibase. Baseline không nhất thiết là một câu lệnh SQL duy nhất; nó là sự kết hợp giữa mô tả schema, bằng chứng đối chiếu và lịch sử mà nhóm thống nhất.

Một baseline tốt:

- Mô tả chính xác các đối tượng mà nhóm muốn quản lý.
- Phân biệt đối tượng hiện có với những thay đổi tương lai.
- Được kiểm tra trên đúng DBMS/version.
- Có ID/author/path ổn định và nằm trong version control.
- Có tài liệu về những đối tượng ngoài phạm vi quản lý.
- Không giả vờ rằng dữ liệu hoặc schema đã được tạo bởi Liquibase nếu thực tế không phải vậy.

### 4.3. Các cách tiếp nhận thường gặp

| Cách làm | Khi phù hợp | Lưu ý |
|---|---|---|
| Tạo changelog mô tả schema hiện tại, sau đó đồng bộ lịch sử | Có thể mô tả đầy đủ các object đang có và muốn Liquibase quản lý những thay đổi tiếp theo. | Cần xác minh baseline khớp schema trước khi ghi nhận changeset là đã chạy. |
| Dùng `generate-changelog` để sinh bản nháp từ database | Cần nhanh chóng thu thập định nghĩa object hiện tại. | Output cần review; không đảm bảo mọi object, quyền, dữ liệu hoặc DBMS feature đều được sinh đầy đủ. |
| Dùng `diff`/`diff-changelog` so sánh database với reference/schema mong đợi | Có database tham chiếu đáng tin cậy hoặc muốn xác định chênh lệch. | Cần chọn đúng reference và kiểm tra phạm vi object được so sánh. |
| Baseline marker được kiểm soát, sau đó chỉ quản lý thay đổi mới | Có quy trình ghi nhận trạng thái hiện tại độc lập và không muốn tái tạo toàn bộ lịch sử cũ. | Marker không tự chứng minh mọi object đã được kiểm kê; phải lưu bằng chứng baseline ở quy trình quản trị. |

Không có một cách phù hợp cho mọi database cũ. Chọn cách nào phải dựa vào mức độ tin cậy của schema hiện tại, lịch sử script cũ, yêu cầu audit và số lượng môi trường cần tiếp nhận.

## 5. Dùng generate-changelog và diff có kiểm soát

### 5.1. generate-changelog

`generate-changelog` có thể đọc metadata database và tạo changelog mô tả các đối tượng mà Liquibase nhận diện được. Ví dụ lệnh CLI khái quát:

~~~bash
liquibase --url=jdbc:postgresql://localhost:5432/legacy_db --username=migration_user generate-changelog --changelog-file=baseline.yaml
~~~

Tên lệnh và cú pháp tùy phiên bản CLI; một số bản dùng cách viết/cấu trúc tham số khác. Ví dụ chỉ mô tả thao tác trên database legacy thử nghiệm, không phải lệnh được chạy trong assignment này.

Changelog được sinh **là bản nháp**, không phải baseline đã được phê duyệt. Cần review:

- Có thiếu view, trigger, routine, sequence, partition, extension hoặc quyền không?
- Có tên kiểu dữ liệu native mà DBMS khác không hỗ trợ không?
- Có giữ được precision/scale, default expression, identity và constraint không?
- Có đưa nhầm bảng hệ thống hoặc bảng metadata vào phạm vi không?
- Các đối tượng có được sắp thứ tự phụ thuộc đúng không?
- Có chứa dữ liệu nhạy cảm hoặc literal không nên commit không?

### 5.2. diff và diff-changelog

Khi có một database tham chiếu đáng tin cậy, `diff` có thể cho biết khác biệt giữa reference và target; `diff-changelog` có thể sinh changeset để biểu diễn một số chênh lệch. Những lệnh này hữu ích trong việc tìm schema drift nhưng không nên được xem là “máy tự sửa production”.

Ví dụ một bảng được sinh thêm index không có nghĩa index ấy chắc chắn an toàn khi tạo trên production: cần đánh giá kích thước bảng, lock, dữ liệu, index hiện tại và DBMS. Tương tự, một cột có kiểu khác có thể do cấu hình DBMS, collation hoặc schema reference sai.

### 5.3. Không dùng diff để bỏ qua hiểu biết nghiệp vụ

Hai schema có cấu trúc giống nhau nhưng dữ liệu có thể khác hoàn toàn. Một cột `status` tồn tại không nói lên mọi bản ghi có giá trị hợp lệ. Một bảng audit có cấu trúc giống nhau không chứng minh lịch sử audit đã được giữ. Diff schema không thay thế kiểm tra dữ liệu, quyền, behavior của trigger hoặc quy tắc ứng dụng.

## 6. ChangelogSync: ghi nhận baseline mà không chạy DDL

Một cơ chế Liquibase thường được sử dụng trong quy trình baseline là lệnh `changelog-sync` (tên lệnh có thể được viết khác ở một số phiên bản cũ). Lệnh này **ghi nhận các changeset được chọn như đã được thực hiện mà không thực thi các change SQL tương ứng**.

Điều này có thể phù hợp khi:

1. Database legacy đã có schema tương đương chính xác với những changeset baseline.
2. Nhóm đã kiểm tra object, kiểu dữ liệu, constraint và các thuộc tính cần thiết.
3. Changelog baseline chỉ chứa những thay đổi đã tồn tại trên database đó.
4. Nhóm có bằng chứng review, backup và phê duyệt trước khi đồng bộ history.

Ví dụ cú pháp CLI khái quát:

~~~bash
liquibase --changelog-file=db/changelog/baseline.yaml changelog-sync
~~~

Hãy kiểm tra tên lệnh, tùy chọn filter và hành vi chính xác theo phiên bản Liquibase đã khóa. Không chạy lệnh này trên database đích chỉ để làm cho `status` báo không còn pending.

### 6.1. ChangelogSync không tạo object

Giả sử changelog baseline chứa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: db-team
      changes:
        - createTable:
            tableName: customer_record
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Nếu chạy `changelog-sync` trên database chưa có bảng `customer_record`, Liquibase có thể ghi history mà **không tạo bảng**. Khi đó history nói changeset đã được đồng bộ, nhưng schema thật vẫn thiếu object. Lần sau `update` sẽ không tự chạy lại changeset baseline thông thường vì nó đã được ghi nhận.

Đây là lý do phải đối chiếu baseline với database trước khi đồng bộ. ChangelogSync là thao tác **đồng bộ lịch sử**, không phải thao tác dựng schema.

### 6.2. Chỉ đồng bộ phạm vi baseline

Một changelog dài có cả baseline và thay đổi mới:

~~~text
root.yaml
  001 ... 050 : mô tả schema hiện có tại thời điểm tiếp nhận
  051 ...     : thay đổi mới sau khi Liquibase tiếp quản
~~~

Nếu chạy `changelog-sync` với phạm vi bao gồm cả `051` trở đi, các migration mới có thể bị đánh dấu đã chạy dù database chưa có thay đổi đó. Vì vậy, cần thiết kế cách tách phạm vi baseline và thay đổi tương lai (ví dụ changelog baseline riêng, changelog gốc include rõ ràng hoặc bộ lọc đã kiểm chứng). Không dựa vào một lệnh đồng bộ không giới hạn rồi hy vọng chỉ những changeset cũ được chọn.

### 6.3. ChangelogSync và MARK_RAN không giống nhau hoàn toàn

`changelog-sync` là một thao tác ở mức lệnh để đồng bộ một tập changeset theo phạm vi cấu hình. `MARK_RAN` thường là chính sách của precondition changeset khi điều kiện không đạt, ghi nhận changeset đã chạy mà không thực hiện change. Cả hai đều có thể tạo history mà không chạy DDL, nhưng **ngữ cảnh, lý do và phạm vi khác nhau**.

Không dùng `MARK_RAN` cho từng bảng chỉ vì “đã tồn tại” nếu chưa so sánh schema. Đối tượng tồn tại có thể sai kiểu, thiếu khóa hoặc chứa dữ liệu không tương thích.

## 7. Chiến lược baseline cho hệ thống đang vận hành

Một quy trình tiếp nhận an toàn có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Chọn database legacy và cửa sổ kiểm kê] --> B[Backup và xác nhận kết nối/schema]
    B --> C[Kiểm kê schema, dữ liệu và lịch sử script cũ]
    C --> D[Sinh hoặc viết changelog baseline]
    D --> E[Review object, quyền, type và phụ thuộc]
    E --> F[So sánh baseline với schema thật]
    F --> G{Khớp hoàn toàn trong phạm vi quản lý?}
    G -->|Không| H[Điều tra drift, sửa baseline hoặc lập remediation]
    H --> F
    G -->|Có| I[Chọn phạm vi baseline cần đồng bộ]
    I --> J[ChangelogSync trên môi trường đã phê duyệt]
    J --> K[Đối chiếu DATABASECHANGELOG và schema]
    K --> L[Áp dụng changeset mới bằng update]
    L --> M[Kiểm tra ứng dụng và vận hành]
~~~

### 7.1. Chuẩn bị trước khi baseline

- Chọn database đại diện, xác định owner và người phê duyệt.
- Tạo backup/restore point có thể kiểm chứng.
- Xác định thời điểm snapshot và kiểm soát thay đổi schema song song.
- Thu thập script SQL cũ, ticket thay đổi, tài liệu DBA và lịch sử deploy.
- Chọn chính xác schema/object thuộc phạm vi Liquibase quản lý.
- Xác định object nào được tạo bởi hệ thống khác và ai tiếp tục sở hữu chúng.

Nếu database vẫn được DBA hoặc công cụ khác thay đổi trong lúc kiểm kê, snapshot có thể đã lỗi thời khi baseline được áp dụng. Cần quy định cửa sổ freeze hoặc quy trình phát hiện drift ngay trước khi đồng bộ.

### 7.2. Review baseline

Đối chiếu theo từng nhóm object:

1. Bảng và cột: type, length, precision, scale, nullability, default.
2. Constraint: PK, FK, unique, check và thứ tự tạo.
3. Index: cột, thứ tự, predicate, unique và đặc điểm native.
4. Sequence/identity: giá trị hiện tại và liên kết.
5. View, function, procedure, trigger: định nghĩa và dependencies.
6. Quyền, role, owner, synonym, extension và cấu hình DBMS.
7. Dữ liệu tham chiếu và bất biến dữ liệu cần giữ.

Baseline chỉ nên đồng bộ khi các khác biệt được giải thích và xử lý. Nếu schema hiện tại không khớp changelog, có hai lựa chọn: sửa bản mô tả baseline để phản ánh chính xác trạng thái đã được chấp nhận, hoặc tạo remediation changeset để đưa schema tới trạng thái chuẩn. Không đánh dấu history như thể một thay đổi đã xảy ra khi thực tế chưa có.

### 7.3. Chạy thử trên bản sao trước khi chạm database thật

Tạo bản sao database legacy hoặc môi trường staging có schema/dữ liệu đại diện. Thử:

- `validate` baseline và changelog gốc.
- `status --verbose` trước khi đồng bộ.
- `changelog-sync` trên đúng phạm vi baseline đã chọn.
- Truy vấn `DATABASECHANGELOG` để kiểm tra những ID/author/filename được ghi.
- Chạy `status` sau baseline để xác nhận tập changeset tương lai vẫn còn chờ.
- Chạy `update-sql` cho migration tương lai và review SQL.
- Chạy migration mới trên bản sao, đối chiếu schema/data sau đó.

Chỉ khi quy trình này cho kết quả mong đợi mới lập kế hoạch áp dụng cho database vận hành.

## 8. Trường hợp database cũ đã có lịch sử Liquibase

Một database đã có `DATABASECHANGELOG` không nhất thiết phải baseline lại. Trước hết xác định nó có đang dùng **cùng changelog và cùng định danh** với repository hiện tại không.

### 8.1. Cùng lịch sử và cùng nguồn changelog

Nếu database đã được quản lý bởi Liquibase của cùng dự án:

- Giữ nguyên `id`, `author`, `FILENAME` hoặc `logicalFilePath`.
- Kiểm tra checksum của changeset đã chạy.
- Xem các changeset đang pending theo đúng context/label/DBMS.
- Đối chiếu schema thật để phát hiện drift ngoài Liquibase.
- Tiếp tục thêm changeset mới theo chuỗi lịch sử hiện có.

Không tạo baseline mới chỉ vì đổi nhóm phát triển hoặc thay pipeline. Việc này có thể tạo định danh trùng hoặc history song song.

### 8.2. Có history nhưng đến từ changelog khác

Nếu bảng history tồn tại nhưng `FILENAME`/ID/author không khớp với repository hiện tại, có thể đây là:

- Một dự án Liquibase khác dùng chung database.
- Một bản changelog cũ đã di chuyển mà không bảo toàn logical path.
- Một nhánh triển khai cũ hoặc công cụ migration khác ghi metadata.

Không xóa history và chạy lại baseline. Hãy thu thập changelog cũ, xác định quyền sở hữu và xây dựng kế hoạch hợp nhất định danh có thể kiểm toán. Khi nhiều ứng dụng cùng dùng database, có thể cần schema history riêng hoặc một quy trình sở hữu migration chung được thống nhất.

### 8.3. History có nhưng schema không khớp

Đây là **schema drift**. Ví dụ `DATABASECHANGELOG` ghi changeset tạo cột `email` đã `EXECUTED` nhưng cột thực tế bị xóa thủ công. `status` có thể không liệt kê changeset ấy là pending vì lịch sử vẫn ghi đã chạy.

Xử lý theo thứ tự:

1. Kiểm tra database/schema và bảng history đúng.
2. Xác minh object thực tế bằng metadata.
3. Tìm thay đổi thủ công, script ngoài Liquibase hoặc lỗi DDL tự commit.
4. Đánh giá dữ liệu và ứng dụng phụ thuộc.
5. Tạo changeset remediation mới hoặc khôi phục theo quy trình được phê duyệt.

Không xóa bản ghi `DATABASECHANGELOG` để buộc Liquibase chạy lại một `CREATE TABLE` cũ. Nếu dữ liệu vẫn còn ở object khác, thao tác tạo lại có thể làm hỏng hoặc nhân đôi cấu trúc.

## 9. Precondition trong tiếp nhận database cũ

Precondition có thể bảo vệ migration tiếp theo bằng cách xác minh đối tượng hoặc dữ liệu đang ở trạng thái mong muốn. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 051-add-customer-index
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_record
        - columnExists:
            tableName: customer_record
            columnName: email
      changes:
        - createIndex:
            tableName: customer_record
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
~~~

Ví dụ này giả định bảng và cột đã được baseline/tiếp nhận. Nếu thiếu một trong hai, `HALT` giúp dừng thay đổi để điều tra. Nhưng `tableExists`/`columnExists` chỉ kiểm tra sự tồn tại; chúng **không chứng minh** cột có đúng kiểu, collation, nullability hoặc dữ liệu hợp lệ.

### 9.1. Khi nào MARK_RAN có thể hợp lệ?

Có thể có tình huống database legacy đã được DBA tạo sẵn một index đúng hoàn toàn như changeset sắp tạo. Sau khi đối chiếu tên, cột, thứ tự, uniqueness, predicate và metadata liên quan, nhóm có thể cân nhắc policy phù hợp để ghi nhận changeset mà không tạo trùng.

Không dùng:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - tableExists:
      tableName: customer_record
~~~

như một shortcut tổng quát cho việc tiếp nhận bảng cũ. Bảng tồn tại không chứng minh cấu trúc đúng, và `MARK_RAN` có thể khiến history cho biết changeset đã xử lý trong khi schema thực còn thiếu cột/constraint/index.

### 9.2. Precondition không thay thế baseline

Nếu hàng trăm bảng đã tồn tại, viết một precondition cho từng changeset cũ rồi dùng `MARK_RAN` không tạo ra một lịch sử baseline rõ ràng. Nó cũng không chứng minh những đối tượng không được nhắc tới đã được kiểm kê. Baseline cần một **mốc quản trị** và bằng chứng đối chiếu; precondition chỉ bảo vệ giả định của một lần thay đổi cụ thể.

## 10. Dữ liệu legacy cần được bảo vệ riêng

Changelog schema thường không chứa toàn bộ dữ liệu vận hành. Tiếp nhận database cũ phải xác định rõ:

- Dữ liệu nào là dữ liệu nghiệp vụ cần giữ nguyên.
- Dữ liệu tham chiếu nào cần được quản lý phiên bản.
- Có dữ liệu NULL, duplicate, sai format hoặc vượt giới hạn mới không.
- Sequence/identity hiện tại có thể sinh ID trùng với dữ liệu đã import không.
- Có trigger hoặc default đang thay đổi dữ liệu trong lúc kiểm kê không.
- Backfill có thể chạy trong thời gian ứng dụng vẫn ghi dữ liệu hay cần cửa sổ bảo trì.

Ví dụ database legacy có cột `customer_id` và sequence. Sau khi import dữ liệu có ID lớn nhất là 90000, sequence vẫn đang ở 500. Nếu không đồng bộ sequence, lần insert tiếp theo có thể sinh ID trùng. Một baseline schema không tự sửa giá trị sequence; cần kiểm tra và có changeset/SQL điều chỉnh phù hợp DBMS.

### 10.1. Không trộn baseline schema với seed data tùy tiện

Baseline có thể ghi nhận bảng đã tồn tại nhưng không nên giả định mọi dữ liệu trong bảng cũng đã được chuẩn hóa. Dữ liệu tham chiếu, dữ liệu nghiệp vụ và dữ liệu chuyển đổi nên có chiến lược riêng:

| Loại dữ liệu | Chiến lược |
|---|---|
| Danh mục hệ thống ổn định | Có thể version hóa trong changeset riêng, kiểm tra khóa duy nhất và giá trị hiện có. |
| Dữ liệu khách hàng/giao dịch | Bảo toàn, kiểm kê và backup; không tái tạo từ seed. |
| Dữ liệu cần chuyển đổi | Backfill bằng changeset mới, có điều kiện và đo số hàng bị tác động. |
| Dữ liệu nhạy cảm | Không commit vào changelog; xử lý bằng cơ chế secret/secure import. |
| Sequence/identity | Đối chiếu giá trị hiện tại với khóa lớn nhất và quy tắc sinh ID. |

## 11. Kế hoạch triển khai đồng thời database mới và database cũ

Một sản phẩm có thể cần hai luồng:

**Luồng A — Database mới:** chạy đầy đủ baseline/schema creation changesets theo thứ tự, sau đó chạy các changeset mới.

**Luồng B — Database legacy:** xác minh schema hiện tại khớp baseline, đồng bộ đúng phạm vi history, rồi chạy các changeset mới.

Ví dụ sơ đồ:

~~~mermaid
flowchart TD
    A[Changelog chuẩn: baseline + forward changes] --> B{Trạng thái database?}
    B -->|Database mới| C[Thực thi baseline changesets]
    B -->|Database legacy| D[Kiểm kê và đối chiếu schema]
    D --> E{Baseline khớp?}
    E -->|Không| F[Remediation hoặc xử lý drift]
    F --> D
    E -->|Có| G[Đồng bộ history baseline có kiểm soát]
    C --> H[Chạy forward changesets]
    G --> H
    H --> I[Đối chiếu schema, dữ liệu và DATABASECHANGELOG]
~~~

### 11.1. Bảng kiểm chứng hai luồng

| Bước | Database mới | Database legacy |
|---|---|---|
| Kết nối và xác định schema | Bắt buộc. | Bắt buộc, cần kiểm tra owner/default schema kỹ hơn. |
| Kiểm kê object | Xác nhận trạng thái ban đầu sạch trong phạm vi dự kiến. | Kiểm kê đầy đủ schema, quyền và dependencies. |
| Baseline | Chạy các changeset tạo schema. | Đối chiếu baseline với object đang tồn tại. |
| Đồng bộ history | History được ghi sau khi migration thực thi. | Có thể cần `changelog-sync` cho phạm vi đã tồn tại và được xác minh. |
| Forward changesets | Chạy sau baseline. | Chạy sau khi history baseline nhất quán. |
| Dữ liệu | Seed/reference data theo chính sách. | Bảo toàn dữ liệu cũ, backfill riêng nếu cần. |
| Xác minh cuối | Schema/data theo thiết kế mới. | Schema/data tương thích với baseline và thay đổi mới. |

**Điểm bắt buộc:** hai luồng phải hội tụ về cùng trạng thái schema cuối cùng. Nếu database mới tạo bảng theo định nghĩa hiện tại nhưng database legacy được đồng bộ history dựa trên schema cũ không tương thích, hai môi trường sẽ tiếp tục khác nhau dù `status` đều báo không còn pending.

## 12. Rollback và phục hồi khi tiếp nhận database cũ

Baseline là ghi nhận một trạng thái đang tồn tại; rollback baseline không có nghĩa “xóa tất cả bảng legacy”. Nếu database chứa dữ liệu vận hành, thao tác `dropTable` hoặc rollback một changeset baseline có thể phá hủy dữ liệu.

Phân biệt:

- **Rollback changeset tạo mới:** có thể đảo ngược một thay đổi vừa thêm, nếu rollback được thiết kế và thử.
- **Rollback changeset baseline:** có thể tương đương xóa các đối tượng đã tồn tại trước khi Liquibase tiếp quản; thường không phải mục tiêu mong muốn.
- **Restore backup:** khôi phục database về một thời điểm/ảnh chụp trước sự cố, có thể bao gồm dữ liệu và cấu trúc.
- **Forward remediation:** thêm changeset mới để sửa trạng thái sai mà không xóa lịch sử.

Với database legacy, thường cần backup/restore plan được thử trước khi đồng bộ history hoặc áp dụng migration đầu tiên. Không coi rollback SQL tự động là thay thế cho backup.

### 12.1. Khi baseline bị ghi nhận nhầm

Nếu đã chạy `changelog-sync` nhưng sau đó phát hiện baseline không khớp schema, **không tự xóa các hàng history** rồi chạy lại. Trước tiên:

1. Dừng pipeline và khóa thay đổi ngoài kế hoạch.
2. Thu thập bản changelog, output lệnh, commit và history hiện tại.
3. Kiểm tra schema/data thật, so sánh với baseline.
4. Xác định chính xác object thiếu/thừa và tác động tới ứng dụng.
5. Chọn remediation changeset hoặc quy trình restore có phê duyệt.
6. Xác minh kết quả trên bản sao trước khi xử lý database vận hành.

History đã ghi là một phần bằng chứng vận hành; sửa history trực tiếp mà không có kế hoạch sẽ khiến những lần deploy sau khó dự đoán.

## 13. Các lỗi thường gặp khi phân biệt hai trạng thái

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chạy `update` trên legacy báo table already exists | Changelog tạo bảng chưa được baseline hoặc history chưa ghi. | Dừng, kiểm kê schema và thiết lập baseline đúng. |
| `status` báo nhiều changeset chờ trên database cũ | Chưa có history, sai filename/ID hoặc kết nối nhầm DB. | Đối chiếu schema và định danh trước `changelog-sync`. |
| `status` bằng 0 nhưng thiếu object | History được đồng bộ nhầm, `MARK_RAN`, schema drift. | Kiểm tra metadata thật và lập remediation. |
| `changelog-sync` chạy xong nhưng ứng dụng không hoạt động | Lệnh chỉ ghi history, không tạo object hay seed dữ liệu. | Khôi phục/hoàn thiện schema và dữ liệu theo kế hoạch. |
| Database mới và legacy khác nhau sau deploy | Baseline không phản ánh cùng trạng thái hoặc forward changes thiếu. | So sánh schema cuối của hai luồng và sửa changelog tương lai. |
| `generate-changelog` thiếu trigger/routine | Công cụ hoặc quyền metadata không thu thập đủ object. | Kiểm kê riêng, thêm SQL/changeset tương ứng. |
| Foreign key hoặc index tạo thất bại | Dữ liệu legacy có duplicate/orphan hoặc thứ tự dependency sai. | Kiểm tra dữ liệu, làm sạch có phê duyệt và sắp xếp migration. |
| Sequence sinh ID trùng | Sequence chưa đồng bộ với dữ liệu đã import. | Kiểm tra max ID và điều chỉnh sequence theo DBMS. |
| Baseline bao gồm migration tương lai | Phạm vi `changelog-sync` quá rộng. | Tách baseline và forward changes, kiểm tra filter trước sync. |
| Schema thay đổi trong khi kiểm kê | DBA/app khác tiếp tục DDL trong lúc snapshot. | Freeze có kiểm soát hoặc kiểm tra drift ngay trước baseline. |

## 14. Bài thực hành có kiểm chứng

**Mục tiêu:** đưa một database khách hàng đã có cấu trúc vào quản lý Liquibase, đồng thời bảo đảm database mới cũng dựng được cùng schema cuối.

### Giai đoạn A — Xác định hai trạng thái

1. Tạo database thử nghiệm mới.
2. Chuẩn bị một database legacy thử có bảng `customer_record`, khóa chính, cột email và dữ liệu giả lập.
3. Xác nhận database legacy chưa có `DATABASECHANGELOG` hoặc ghi nhận chính xác history nếu đã có.
4. Kiểm kê object, dữ liệu, schema, sequence và quyền của hai database.

### Giai đoạn B — Tạo và review baseline

1. Sinh hoặc viết changelog baseline mô tả đúng bảng và đối tượng hiện có.
2. Review type, precision/scale, default, constraint, index, trigger và dependencies.
3. Đối chiếu baseline với database legacy bằng công cụ diff/snapshot và truy vấn metadata.
4. Liệt kê những object hoặc quyền chưa được quản lý trong baseline.
5. Tạo backup/restore point cho database legacy thử.

### Giai đoạn C — Tiếp nhận legacy

1. Chạy `validate` và `status --verbose` trên database legacy.
2. Xác nhận chính xác changeset baseline nào đã tồn tại trong schema.
3. Chạy `changelog-sync` chỉ trên phạm vi baseline đã được duyệt.
4. Đọc `DATABASECHANGELOG` để xác minh ID/author/FILENAME/EXECTYPE.
5. Chạy `status` lại và xác nhận các forward changesets vẫn được liệt kê đúng.

### Giai đoạn D — Dựng database mới

1. Chạy đầy đủ baseline changesets trên database mới bằng `update`.
2. Chạy tiếp forward changesets giống luồng legacy.
3. So sánh schema cuối và kiểm tra dữ liệu tham chiếu cần thiết.
4. Xác nhận hai database đạt cùng hợp đồng schema dù lịch sử ban đầu khác nhau.

### Giai đoạn E — Thử lỗi và khôi phục

Trên bản sao lab, cố tình tạo một khác biệt như thiếu index hoặc kiểu cột không khớp. Quan sát cách baseline review phát hiện vấn đề. Không chạy `changelog-sync` để che sai khác. Thiết kế remediation changeset hoặc khôi phục database từ backup, rồi lặp lại đối chiếu.

**Tiêu chí đạt:** phân biệt được database mới và legacy bằng bằng chứng; baseline mô tả chính xác schema; `changelog-sync` chỉ ghi nhận thay đổi đã tồn tại; hai luồng hội tụ cùng schema cuối; dữ liệu cũ được bảo toàn.

## 15. Checklist trước khi tiếp nhận database legacy

- [ ] Xác minh đúng database, schema, DBMS, phiên bản và tài khoản.
- [ ] Kiểm tra `DATABASECHANGELOG`/`DATABASECHANGELOGLOCK` và lịch sử từ công cụ cũ.
- [ ] Kiểm kê bảng, cột, constraint, index, sequence, view, routine, trigger, quyền và extension.
- [ ] Đối chiếu dữ liệu thật, số hàng, duplicate, orphan, NULL và sequence value.
- [ ] Xác định object nào nằm trong phạm vi Liquibase quản lý.
- [ ] Changelog baseline đã được review trên đúng DBMS/version.
- [ ] Đã xác minh baseline khớp schema thực tế trước `changelog-sync`.
- [ ] Phạm vi đồng bộ history không bao gồm các forward changesets chưa chạy.
- [ ] Đã backup/restore thử và có người chịu trách nhiệm phê duyệt.
- [ ] Đã thử quy trình trên bản sao có schema và dữ liệu đại diện.
- [ ] Có kế hoạch remediation cho schema drift và trạng thái DDL dở dang.
- [ ] Có quy trình freeze/kiểm tra thay đổi song song trong thời điểm baseline.
- [ ] Đã kiểm tra database mới chạy đầy đủ changelog tạo cùng schema cuối.
- [ ] Đã kiểm tra ứng dụng Spring Boot/JDBC và quyền runtime sau tiếp nhận.

## 16. Câu hỏi tự kiểm tra

1. Database mới và database đã có cấu trúc khác nhau ở ba lớp schema, dữ liệu và lịch sử như thế nào?
2. Vì sao không thể kết luận database là mới chỉ vì chưa có `DATABASECHANGELOG`?
3. Baseline là gì và cần bằng chứng nào trước khi đồng bộ?
4. `generate-changelog` có bảo đảm thu thập mọi object, quyền và dữ liệu legacy không?
5. `changelog-sync` thực hiện điều gì và không thực hiện điều gì?
6. Vì sao đồng bộ toàn bộ changelog có thể đánh dấu nhầm các migration tương lai là đã chạy?
7. `MARK_RAN` khác `changelog-sync` như thế nào về ngữ cảnh sử dụng?
8. Một bảng đã tồn tại có đủ để đánh dấu changeset tạo bảng là đã chạy không? Cần kiểm tra thêm những gì?
9. Làm sao để database mới và database legacy hội tụ về cùng schema cuối?
10. Nếu history ghi changeset đã chạy nhưng cột thực tế bị xóa, vì sao `status` có thể không phát hiện?
11. Vì sao cần kiểm tra sequence/identity khi tiếp nhận dữ liệu đã import?
12. Baseline schema có tự bảo đảm dữ liệu tham chiếu và dữ liệu nghiệp vụ đúng không?
13. Khi baseline bị ghi nhận nhầm, vì sao không nên xóa hàng `DATABASECHANGELOG` rồi chạy lại?
14. Khi nào nên tạo remediation changeset, khi nào cần restore backup?

## Kết luận

Phân biệt database mới với database đã có cấu trúc là bước nền tảng khi tiếp nhận Liquibase. Database mới thường **thực thi** các changeset tạo schema; database legacy cần **kiểm kê, đối chiếu và ghi nhận baseline** trước khi áp dụng thay đổi tiếp theo. `changelog-sync` chỉ đồng bộ lịch sử, không tạo object; `generate-changelog` và `diff` hỗ trợ kiểm kê nhưng vẫn cần review; precondition bảo vệ giả định của từng migration chứ không thay thế baseline. Khi schema, dữ liệu và `DATABASECHANGELOG` được xác minh riêng, hai luồng có thể hội tụ về cùng trạng thái cuối, bảo toàn dữ liệu cũ và tạo nền tảng triển khai có kiểm chứng cho `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` qua nhiều môi trường.
