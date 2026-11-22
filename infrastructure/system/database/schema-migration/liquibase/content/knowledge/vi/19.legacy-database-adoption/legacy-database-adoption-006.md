# Đánh dấu baseline bằng changelog-sync sau khi đối chiếu

Một database legacy có thể đã vận hành nhiều năm với hàng trăm bảng, view, index, sequence, trigger và procedure được tạo bằng script thủ công hoặc công cụ khác. Khi bắt đầu quản lý bằng Liquibase, nhóm không muốn chạy lại toàn bộ CREATE TABLE trên những đối tượng đã tồn tại. Cách tiếp nhận phù hợp là **đối chiếu schema hiện tại với changelog mô tả trạng thái mong muốn, sau đó đánh dấu những changeset baseline đã có là được xử lý**.

Liquibase cung cấp lệnh **changelog-sync** cho mục tiêu này. Lệnh ghi nhận các changeset chưa được áp dụng trong phạm vi được chọn vào lịch sử Liquibase mà **không thực thi những thay đổi schema/data bên trong changeset**. Sau khi đồng bộ baseline, các lần **update** tiếp theo có thể chỉ tập trung vào changeset mới thực sự cần triển khai.

Bài học thuộc chương **Tiếp nhận CSDL** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Mục tiêu học tập:** sau bài này, bạn có thể lập kế hoạch tiếp nhận database legacy, kiểm kê và đối chiếu schema, xây dựng changelog baseline, xem trước SQL đồng bộ, chạy **changelog-sync** đúng phạm vi, xác minh DATABASECHANGELOG và quản lý các changeset mới sau khi tiếp nhận.

## 1. Baseline trong quá trình tiếp nhận database legacy là gì?

**Baseline** là mốc trạng thái đã được xác nhận của database tại thời điểm bắt đầu quản lý bằng Liquibase. Nó mô tả những cấu trúc hoặc dữ liệu nền đã tồn tại và được chấp nhận trước khi Liquibase tiếp quản.

Ví dụ database đơn hàng đã có:

- Bảng **orders**, **customer**, **order_item**.
- Primary key, foreign key, unique constraint và index.
- View báo cáo.
- Sequence hoặc identity.
- Function, procedure và trigger.
- Các cột, kiểu dữ liệu, default, nullability và comment.
- Những thay đổi đã được triển khai qua script cũ.

Nhóm muốn từ thời điểm này mọi thay đổi schema được quản lý qua changelog. Nếu đưa trực tiếp một changelog chứa CREATE TABLE vào lệnh **update**, Liquibase có thể cố tạo lại các bảng đã tồn tại và thất bại.

Thay vào đó, quy trình tiếp nhận gồm:

1. Thu thập trạng thái database thực tế.
2. Tạo hoặc hoàn thiện changelog phản ánh trạng thái đã có.
3. So sánh changelog/schema mong muốn với database đích.
4. Xử lý mọi khác biệt ngoài dự kiến.
5. Chỉ khi xác nhận tương đương mới chạy **changelog-sync** cho phạm vi baseline.
6. Kiểm tra lịch sử Liquibase và chạy update cho changeset mới.

### 1.1. Baseline không có nghĩa là tạo lại database

Có hai mục tiêu cần phân biệt:

| Mục tiêu | Cách xử lý |
|---|---|
| **Tiếp nhận database đã tồn tại** | Đối chiếu schema rồi dùng changelog-sync để ghi nhận baseline mà không chạy lại DDL |
| **Khởi tạo database mới** | Dùng update để thực thi các changeset tạo schema từ đầu |

Cùng một changelog baseline có thể phục vụ hai luồng nếu được thiết kế đúng: database legacy được **sync** các changeset đã có, còn database trống được **update** để tạo các đối tượng. Sau baseline, cả hai có thể tiếp tục dùng cùng những changeset mới.

**Không chạy changelog-sync trên database trống với mục tiêu tạo schema.** Lệnh đó chỉ ghi nhận changeset đã xử lý, không tạo bảng/cột mà chúng mô tả.

## 2. changelog-sync làm gì?

Lệnh **changelog-sync** đánh dấu các changeset chưa được ghi nhận trong database là đã được xử lý theo cơ chế Liquibase, trong phạm vi changelog và các filter được áp dụng. Lệnh này **không thực thi các change bên trong changeset** như CREATE TABLE, ALTER TABLE, INSERT hoặc CREATE INDEX.

Ví dụ:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml changelog-sync
~~~

Sau khi chạy, Liquibase ghi metadata vào **DATABASECHANGELOG** cho các changeset được đồng bộ. Lần **update** tiếp theo sẽ thấy những changeset đó đã được ghi nhận và thông thường không thực thi chúng như migration pending.

Có thể hình dung:

~~~mermaid
flowchart TD
    A[Database legacy đã có schema] --> B[Đối chiếu schema và changelog]
    B --> C{Tương đương theo baseline?}
    C -->|Không| D[Điều tra và sửa khác biệt]
    D --> B
    C -->|Có| E[changelog-sync]
    E --> F[DATABASECHANGELOG ghi nhận baseline]
    F --> G[Thêm changeset mới]
    G --> H[update chỉ áp dụng thay đổi mới]
~~~

### 2.1. Điều changelog-sync không làm

- Không tạo bảng, cột, index, constraint hoặc view được mô tả trong changeset.
- Không sửa schema đang khác changelog.
- Không tự phát hiện mọi drift và tự sửa database.
- Không chứng minh dữ liệu hiện có đúng nghiệp vụ.
- Không thay thế backup, snapshot hoặc quy trình khôi phục.
- Không bảo đảm một changelog baseline sai sẽ an toàn chỉ vì lệnh kết thúc thành công.

**Điều kiện tiên quyết là database đã có trạng thái tương đương với nội dung baseline.** Changelog-sync chỉ ghi nhận mốc đã xác nhận; nó không phải công cụ sửa chữa sai khác.

### 2.2. Những changeset nào sẽ được đồng bộ?

Lệnh có thể xử lý các changeset chưa được ghi nhận trong phạm vi changelog được nạp và các filter runtime tương ứng. Vì vậy, nếu changelog gốc còn chứa cả migration tương lai, lệnh có thể đánh dấu luôn những changeset chưa được thực thi đó.

Đây là rủi ro lớn nhất khi tiếp nhận:

> Nếu baseline và migration tương lai bị trộn trong cùng phạm vi changelog-sync, các thay đổi chưa tồn tại có thể bị ghi nhận là đã xử lý và sẽ bị bỏ qua ở lần update sau.

Cần giới hạn phạm vi bằng một changelog baseline riêng, cấu trúc include hợp lý hoặc filter đã được kiểm chứng. Không dựa vào giả định rằng Liquibase tự biết changeset nào “cũ” và changeset nào “mới”.

## 3. Kiểm kê database trước khi tạo baseline

Không nên bắt đầu bằng việc viết CREATE TABLE theo trí nhớ hoặc chỉ dựa trên một file DDL cũ. Cần kiểm kê database **đang thực sự vận hành**.

### 3.1. Phạm vi schema cần kiểm kê

| Nhóm đối tượng | Thông tin cần xác nhận |
|---|---|
| Table | Tên, schema, cột, kiểu, thứ tự cột khi có ý nghĩa, default, nullability |
| Primary key | Cột tham gia, tên constraint, quy tắc |
| Foreign key | Bảng/cột tham chiếu, hành vi ON DELETE/UPDATE |
| Unique/check constraint | Biểu thức, tên, trạng thái enable/validate |
| Index | Cột, thứ tự, unique, predicate, phương thức, tùy chọn DBMS |
| View/materialized view | Định nghĩa, phụ thuộc và quyền |
| Sequence/identity | Giá trị, increment, cache, liên kết với cột |
| Trigger | Sự kiện, thứ tự, function/procedure liên quan |
| Function/procedure | Signature, body, ngôn ngữ, quyền và dependency |
| Synonym/extension/type | Đối tượng đặc thù DBMS |
| Partition | Cấu trúc cha/con, chiến lược partition, bound |
| Comment/metadata | Mô tả bảng/cột và metadata liên quan |
| Grant/role | Quyền ứng dụng và quyền migration |
| Schema owner | Chủ sở hữu và default schema |

Không phải mọi DBMS hay phiên bản Liquibase đều so sánh hoặc biểu diễn tất cả các đối tượng giống nhau. Hãy lập danh sách những gì thuộc phạm vi baseline và những gì cần quản lý bằng script riêng.

### 3.2. Schema không phải toàn bộ dữ liệu

Một schema diff có thể cho biết cấu trúc bảng khác nhau, nhưng không chứng minh dữ liệu hàng đã giống nhau. Với database legacy, cần phân biệt:

- **Schema baseline:** định nghĩa đối tượng.
- **Reference/seed data:** danh mục chuẩn cần được quản lý có chủ đích.
- **Operational data:** dữ liệu giao dịch phát sinh trong vận hành.
- **Sensitive data:** dữ liệu cần bảo vệ, ẩn danh hóa hoặc hạn chế truy cập.

Không tạo changelog baseline bằng cách xuất toàn bộ dữ liệu production rồi commit vào repository. Nếu có seed data, quản lý nó theo phạm vi, nguồn gốc và chính sách dữ liệu riêng.

## 4. Chọn nguồn tạo changelog baseline

Có một số cách tạo changelog cho database hiện hữu.

### 4.1. Reverse engineer bằng generate-changelog

Liquibase có thể đọc database và tạo changelog ban đầu:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-legacy.internal:5432/orders" \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  generate-changelog
~~~

Lệnh **generate-changelog** tạo mô tả changeset từ những đối tượng mà Liquibase có thể phát hiện và biểu diễn. Kết quả là **điểm khởi đầu cần review**, không phải baseline đã được phê duyệt.

Phải kiểm tra:

- Các bảng và schema có nằm đúng phạm vi không.
- Foreign key và constraint có đầy đủ không.
- Index đặc thù, partial index, function, trigger và view có được biểu diễn không.
- Kiểu dữ liệu và thuộc tính DBMS có bị chuẩn hóa/mất thông tin không.
- Changelog có phụ thuộc vào tên schema hoặc catalog cụ thể không.
- SQL được sinh có thể tạo lại schema trên database trống không.

Không phải mọi đối tượng vendor-specific đều được reverse engineer hoàn chỉnh.

### 4.2. Viết changelog baseline có chủ đích

Đội database có thể viết changelog bằng YAML/XML/JSON hoặc formatted SQL từ tài liệu DDL đã kiểm chứng. Cách này cho phép thể hiện ý định, sắp xếp dependency và thêm rollback/precondition rõ ràng.

Nhưng người viết phải đối chiếu với catalog thực tế. Một file DDL cũ trong repository có thể không phản ánh những thay đổi DBA đã triển khai trực tiếp nhiều năm qua.

### 4.3. Kết hợp hai phương pháp

Một quy trình thường hữu ích:

1. Dùng **generate-changelog** trên bản sao database legacy để có danh sách ban đầu.
2. Review và chuẩn hóa changelog.
3. Bổ sung các đối tượng hoặc thuộc tính bị bỏ sót bằng change type/SQL phù hợp.
4. Dùng **diff** để so sánh với database đích.
5. Kiểm tra thủ công những khác biệt mà công cụ không thể so sánh chắc chắn.
6. Chốt artifact baseline đã review.

Đây là cách tận dụng tự động hóa nhưng vẫn giữ trách nhiệm xác nhận của nhóm sở hữu database.

## 5. Dùng diff và diff-changelog đúng chiều

Liquibase hỗ trợ so sánh database hoặc schema qua **diff**. Thông thường có hai vai trò:

- **Reference:** nguồn trạng thái được xem là chuẩn để so sánh.
- **Target:** database được đem ra đối chiếu với reference.

Ví dụ:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference.internal:5432/orders_model" \
  --url="jdbc:postgresql://legacy.internal:5432/orders" \
  diff
~~~

Ý định ví dụ: lấy schema reference làm mốc so sánh và kiểm tra database target legacy khác ở đâu. Cú pháp kết nối, credentials và các option phải được cấu hình an toàn theo phiên bản thực tế.

**diff-changelog** có thể tạo changelog mô tả các thay đổi để đưa target về gần trạng thái reference. Vì vậy, nếu đặt reference và target ngược chiều, các changeset được sinh cũng có thể ngược với ý định.

### 5.1. diff không phải lệnh sửa database

**diff** là công cụ quan sát khác biệt. Nó không tự áp dụng thay đổi vào database.

**diff-changelog** sinh changelog để review. Không nên chạy update ngay trên output chưa kiểm tra, vì:

- Khác biệt có thể là drift có chủ đích.
- Một số đối tượng không được so sánh đầy đủ.
- SQL sinh có thể phụ thuộc DBMS.
- Có thể thiếu dữ liệu, quyền hoặc dependency.
- Một schema reference không nhất thiết là trạng thái mong muốn của mọi môi trường.

### 5.2. Tách khác biệt cần sửa và khác biệt được chấp nhận

Ví dụ:

| Khác biệt | Cách xử lý |
|---|---|
| Thiếu index bắt buộc | Điều tra rồi tạo migration sửa nếu đúng |
| Cột nullable khác hợp đồng | Xác minh dữ liệu trước khi sửa constraint |
| Comment khác nội dung | Review metadata và chuẩn hóa nếu cần |
| Một bảng legacy chỉ tồn tại ở môi trường cũ | Xác định còn sử dụng không, không tự xóa |
| Khác biệt owner/grant | Kiểm tra chính sách quyền và khả năng so sánh |
| Extension hoặc function vendor-specific | Xem catalog và script riêng |

Không yêu cầu mọi khác biệt đều phải được “sửa cho hết”. Baseline phải phản ánh **trạng thái được chấp nhận**, không phải tạo ra hàng loạt migration vô nghĩa chỉ để diff rỗng.

## 6. Xác định baseline changelog và migration tương lai

Một cấu trúc dễ review là tách changelog baseline khỏi các thay đổi phát sinh sau khi tiếp nhận:

~~~text
db/changelog/
  db.changelog-master.yaml
  baseline/
    001-schema.yaml
    002-views-routines.yaml
  releases/
    2026/
      11/
        001-add-order-status.yaml
        002-index-order-status.yaml
~~~

Changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/001-schema.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/002-views-routines.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/001-add-order-status.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/002-index-order-status.yaml
      relativeToChangelogFile: true
~~~

Đây là ví dụ cấu trúc. Khi thực hiện sync, phải bảo đảm lệnh chỉ đánh dấu **baseline**. Có thể dùng changelog gốc riêng chỉ include baseline, hoặc cơ chế filter/context/label phù hợp đã được thử nghiệm.

### 6.1. Vì sao baseline nên có ranh giới rõ?

Giả sử changelog gốc chứa:

- Changeset A: tạo bảng orders — đã tồn tại.
- Changeset B: tạo index — đã tồn tại.
- Changeset C: thêm cột discount — chưa tồn tại, dự kiến release tới.

Nếu chạy changelog-sync trên cả ba changeset mà không giới hạn, C cũng có thể được ghi nhận đã xử lý. Lần update sau sẽ không tạo cột discount như dự kiến.

**Chỉ đồng bộ những changeset mà trạng thái thực tế đã được đối chiếu.**

### 6.2. Dùng context/label để giới hạn phạm vi

Có thể phân loại baseline bằng context hoặc label nếu cấu trúc dự án và phiên bản hỗ trợ. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-create-orders"
      author: "db-team"
      labels: baseline
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
~~~

Khi dùng filter, cần xác nhận chính xác changeset nào được chọn. **Changeset không có label có thể vẫn được xử lý tùy ngữ nghĩa label filter**, nên không giả định filter là allowlist kín. Một changelog baseline riêng thường dễ kiểm soát hơn nếu phạm vi rất quan trọng.

## 7. Chuẩn hóa identity của changeset trước khi sync

Liquibase thường nhận diện changeset bằng:

~~~text
ID + AUTHOR + FILENAME (hoặc logicalFilePath)
~~~

Ba thành phần này cần ổn định giữa các môi trường.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-create-orders"
      author: "database-platform"
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Lưu ý:

- ID cần duy nhất trong phạm vi quản lý.
- Author nên theo quy ước đội nhóm ổn định.
- Đường dẫn changelog nên được giữ nguyên sau khi đã sync.
- Nếu cần di chuyển file, cân nhắc **logicalFilePath** theo khả năng phiên bản và xác minh giá trị FILENAME trong lịch sử.
- Không tái sử dụng ID/author cho một nội dung khác.

### 7.1. Vì sao identity sai gây vấn đề?

Một changeset đã được sync trên production dưới đường dẫn **baseline/001-schema.yaml**. Sau đó file được chuyển sang **schema/baseline.yaml** mà không duy trì logical path tương thích. Liquibase có thể coi identity mới là changeset chưa chạy và cố thực thi CREATE TABLE lần nữa.

Vì vậy, việc chuẩn hóa đường dẫn và định danh phải hoàn tất **trước** khi sync từng môi trường.

## 8. Precondition khi baseline

Precondition có thể xác nhận những giả định cần thiết trước khi xử lý changeset, ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-orders"
      author: "db-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: orders
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: id
      changes:
        - createTable:
            schemaName: public
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
~~~

Trong quy trình tiếp nhận, các changeset baseline thường mô tả cấu trúc **đã có**. Precondition có thể giúp làm lộ trạng thái không phù hợp nếu changeset được xét chạy, nhưng **changelog-sync không phải phép xác minh schema toàn diện** và không thực thi changes như update.

Không dựa vào precondition đơn giản như tableExists để kết luận bảng đã tương đương hoàn toàn. Cần đối chiếu kiểu cột, constraint, index, default và những thuộc tính khác.

### 8.1. Không dùng MARK_RAN để thay thế đối chiếu

Một cách nguy hiểm là khai báo:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - onError: HALT
  - tableExists:
      tableName: orders
~~~

Điều kiện chỉ nói bảng tồn tại. Nó không chứng minh cấu trúc bảng đúng. Nếu bảng có cùng tên nhưng sai kiểu cột hoặc thiếu foreign key, việc MARK_RAN sẽ che giấu sai lệch.

**Baseline phải dựa trên đối chiếu thực tế và phê duyệt**, không dựa vào một precondition quá yếu.

## 9. Lệnh changelog-sync và cấu hình kết nối

Cú pháp CLI thường dùng:

~~~bash
liquibase \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  --url="jdbc:postgresql://legacy.internal:5432/orders" \
  --username="orders_migrator" \
  changelog-sync
~~~

Trong ví dụ, file được nạp chỉ là changelog baseline đã đối chiếu. Password nên lấy từ secret manager hoặc cơ chế cấu hình an toàn, không viết trực tiếp trong lệnh có thể lưu vào shell history/process list.

Trước khi chạy cần xác nhận:

- URL trỏ đúng database legacy cần tiếp nhận.
- Changelog baseline đúng artifact và đúng phiên bản đã review.
- User có quyền cần thiết để Liquibase đọc schema và ghi metadata.
- Schema metadata Liquibase được cấu hình đúng.
- Không có tiến trình migration khác đang chạy.
- Filter context/label, nếu có, được cố định và đã kiểm chứng.

### 9.1. Liquibase metadata tables

Liquibase thường cần hai bảng metadata:

- **DATABASECHANGELOG**: ghi nhận changeset đã xử lý.
- **DATABASECHANGELOGLOCK**: điều phối lock khi chạy migration.

Nếu database chưa có các bảng này, Liquibase có thể tạo chúng theo cấu hình. Việc tạo bảng metadata là thay đổi thực tế cần tính vào quyền và kế hoạch triển khai, dù các changeset baseline không chạy DDL nghiệp vụ.

### 9.2. changelog-sync không phải update

Một lần sync thành công thường ghi metadata cho changeset nhưng không chạy CREATE TABLE hoặc ALTER TABLE bên trong. Không dùng kết quả sync để kết luận SQL của các changeset baseline đã được kiểm tra thực thi trên database trống.

Để chứng minh changelog baseline có thể khởi tạo một database mới, cần một **database trống riêng** và chạy **update** trên database đó.

## 10. Xem trước bằng changelog-sync-sql

Trước khi ghi history, có thể dùng lệnh **changelog-sync-sql** để xem SQL dự kiến phục vụ việc đồng bộ changelog:

~~~bash
liquibase \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  changelog-sync-sql
~~~

Tên lệnh và khả năng có mặt cần xác nhận với phiên bản Liquibase cụ thể. Nếu phiên bản đang dùng không hỗ trợ lệnh này hoặc có syntax khác, tham khảo **liquibase --help** và tài liệu đúng phiên bản.

SQL preview thường cho thấy các thao tác metadata mà Liquibase dự kiến dùng để ghi nhận changeset. Nó không thực thi schema changes trong baseline.

### 10.1. Review output theo checklist

- Chỉ có changeset baseline được chọn.
- Không có changeset tương lai nằm trong phạm vi sync.
- ID, author và filename đúng.
- Database metadata table/schema đúng.
- Context/label filter được áp dụng như dự định.
- Không có SQL DDL nghiệp vụ như CREATE TABLE/ALTER TABLE phát sinh ngoài dự kiến.
- Những changeset đã ghi nhận trước đó không bị hiểu sai thành pending.
- Output thuộc đúng artifact và Liquibase version đã phê duyệt.

Nếu SQL preview chứa nhiều changeset hơn baseline đã kiểm kê, **dừng và sửa phạm vi** trước khi chạy changelog-sync.

## 11. Chạy changelog-sync trên một database legacy

Sau khi đối chiếu và review SQL preview, thực hiện trên database đã xác nhận:

~~~bash
liquibase \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  changelog-sync
~~~

Sau đó chạy các bước chỉ đọc:

~~~bash
liquibase \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  history

liquibase \
  --changelog-file=db/changelog/baseline/db.baseline.yaml \
  status --verbose
~~~

Kỳ vọng:

- Những changeset baseline thuộc phạm vi sync được ghi nhận trong DATABASECHANGELOG.
- Chúng không còn được coi là pending trong phạm vi changelog tương ứng.
- Không có DDL nghiệp vụ được chạy lại chỉ do thao tác sync.
- Những migration tương lai ngoài phạm vi baseline vẫn pending.

**Đừng đánh giá kết quả chỉ bằng exit code.** Hãy truy vấn DATABASECHANGELOG và đối chiếu schema thực tế.

## 12. Đọc DATABASECHANGELOG sau khi sync

Ví dụ truy vấn chỉ đọc:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Một số cột có thể khác theo phiên bản Liquibase và lịch sử metadata. Nếu bảng nằm ở schema riêng hoặc tên tùy chỉnh, hãy dùng đúng tên được cấu hình.

Cần xác minh:

1. Có đủ identity của changeset baseline không?
2. Filename có khớp đường dẫn được phê duyệt không?
3. Không có changeset tương lai bị sync nhầm không?
4. Checksum được lưu theo artifact hiện tại không?
5. History phản ánh đúng database đích không?
6. Có những bản ghi đã tồn tại từ trước cần giải thích không?

**Không chỉnh sửa DATABASECHANGELOG thủ công** để ép kết quả giống mong muốn. Nếu history khác kỳ vọng, xác định nguyên nhân trước khi sửa.

### 12.1. EXECTYPE và cách diễn giải

Changelog-sync đánh dấu changeset đã được xử lý mà không chạy nội dung changeset. Cách Liquibase thể hiện trạng thái đó trong metadata có thể phụ thuộc command, phiên bản và trường hợp. Không tự suy diễn rằng một dòng history có nghĩa SQL đã thực thi.

Hãy kiểm tra EXECTYPE thực tế và luôn đối chiếu schema catalog. Khi cần audit sự kiện sync, lưu log CLI/pipeline, artifact, thời điểm và người phê duyệt bên ngoài DATABASECHANGELOG.

## 13. Xác minh schema sau khi sync

Sau sync, cần kiểm tra **đối tượng thực tế** để chắc rằng baseline đúng. Ví dụ PostgreSQL:

~~~sql
SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
~~~

Kiểm tra cột:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
~~~

Kiểm tra index:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
~~~

Đây là truy vấn minh họa cho PostgreSQL. Với MySQL, Oracle, SQL Server hoặc DBMS khác, dùng catalog tương ứng.

### 13.1. Đối chiếu theo từng nhóm đối tượng

Không chỉ kiểm tra số lượng bảng. Hai database có cùng số bảng vẫn có thể khác:

- Cột, datatype hoặc độ dài.
- Default và nullability.
- Primary/foreign/unique/check constraint.
- Index và thứ tự cột.
- View definition.
- Trigger/function/procedure.
- Sequence/identity và quyền.

Với đối tượng quan trọng, tạo bảng đối chiếu có trạng thái **khớp / khác biệt đã chấp nhận / cần sửa** và lưu người xác nhận.

## 14. Phân biệt changelog-sync với các lệnh liên quan

| Lệnh | Mục đích | Có chạy DDL changeset không? |
|---|---|---|
| **generate-changelog** | Tạo changelog từ database hiện hữu | Không áp dụng changelog |
| **diff** | So sánh hai database/schema | Không |
| **diff-changelog** | Sinh changelog thể hiện khác biệt để đưa target về reference | Không tự áp dụng |
| **changelog-sync** | Ghi nhận changeset chưa triển khai như đã được xử lý | Không chạy changes bên trong |
| **changelog-sync-sql** | Xem SQL metadata dự kiến cho sync khi phiên bản hỗ trợ | Không |
| **update** | Áp dụng changeset pending | Có |
| **mark-next-changeset-ran** | Đánh dấu changeset tiếp theo theo cơ chế lệnh chuyên biệt | Không chạy change thông thường theo ý nghĩa đánh dấu |
| **clear-checksums** | Xóa checksum đã lưu để Liquibase tính lại ở lần xử lý sau theo quy tắc | Không sửa schema |

**Không dùng các lệnh này thay thế nhau.** Đặc biệt, **clear-checksums** không phải công cụ baseline; nó không tạo cấu trúc và không xác minh schema.

### 14.1. changelog-sync khác mark-next-changeset-ran

**changelog-sync** thường áp dụng cho toàn bộ changeset chưa ghi nhận trong phạm vi lệnh/filter. **mark-next-changeset-ran** tập trung vào changeset tiếp theo theo thứ tự Liquibase xét.

Khi chỉ cần xử lý một changeset trong tình huống đặc biệt, không nên chạy changelog-sync trên toàn changelog nếu các changeset khác chưa được đối chiếu. Chọn lệnh phải theo mục tiêu và kiểm tra phạm vi chính xác.

## 15. Tiếp nhận nhiều môi trường

Một sản phẩm có thể có:

- Production legacy đã tồn tại lâu năm.
- Staging được dựng từ backup cũ.
- Development có schema do nhiều nhóm sửa.
- Một số môi trường khách hàng có biến thể được phê duyệt.

Không giả định một lần sync ở production có thể được sao chép metadata sang môi trường khác. Mỗi database cần được **đối chiếu và sync riêng**.

### 15.1. Ma trận đối soát

| Môi trường | Schema thực tế | Baseline tương đương? | Hành động |
|---|---|---|---|
| Development | Đã kiểm kê | Có | Sync baseline |
| Staging | Có khác biệt index đã được chấp nhận | Cần review | Ghi nhận ngoại lệ, quyết định phạm vi |
| Production | Đã xác nhận theo catalog và diff | Có | Sync sau phê duyệt |
| Customer A | Có đối tượng mở rộng riêng | Chưa | Phân loại extension và chuẩn hóa |

Bảng là ví dụ quản trị. Không dùng changelog-sync để che những khác biệt chưa được giải thích.

### 15.2. Giữ cùng artifact baseline

Sau khi baseline được phê duyệt:

- Dùng cùng artifact changelog trên các môi trường.
- Giữ ổn định ID, author và logical path.
- Ghi lại Liquibase version.
- Lưu log sync riêng cho từng database.
- Không chỉnh sửa baseline changeset sau khi đã sync nếu chưa đánh giá checksum và lịch sử.

Nếu có một môi trường không tương đương, không sync nó chỉ để đồng bộ số dòng history. Trước tiên phải quyết định sửa schema, quản lý extension riêng hay thiết kế một baseline khác có kiểm soát.

## 16. Kiểm tra database mới có thể dựng lại từ baseline không

Đây là bước thường bị bỏ sót.

Sau khi tiếp nhận database legacy, nhóm có thể thấy history và schema đều khớp, nhưng changelog baseline chưa chắc tái tạo được database trống. Có thể thiếu:

- Function hoặc procedure.
- Trigger.
- Sequence hoặc quyền.
- Extension và kiểu dữ liệu tùy chỉnh.
- View phụ thuộc thứ tự.
- Index đặc thù.
- Dữ liệu tham chiếu bắt buộc.
- Đối tượng do DBA tạo ngoài changelog.

Vì vậy, hãy dùng **một database trống riêng** để kiểm chứng:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate

liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update
~~~

Đây là phép thử khởi tạo mới, khác với changelog-sync trên database legacy.

Sau update, so sánh schema được dựng mới với baseline được phê duyệt. Nếu khác, cần bổ sung changelog hoặc tài liệu hóa ngoại lệ trước khi tuyên bố có thể tái tạo môi trường.

### 16.1. Kiểm tra cả dữ liệu tham chiếu

Một database trống có thể có đủ bảng nhưng ứng dụng không chạy vì thiếu danh mục trạng thái, currency, country hoặc cấu hình mặc định. Xác định rõ dữ liệu nào là **reference data** cần quản lý và dữ liệu nào là operational data không thuộc baseline schema.

## 17. Quản lý checksum và thay đổi baseline sau khi sync

Sau khi changeset baseline được ghi vào DATABASECHANGELOG, Liquibase lưu metadata/checksum theo cơ chế của nó. Việc sửa nội dung baseline về sau có thể dẫn đến **checksum mismatch** hoặc thay đổi cách nhận diện changeset.

Ví dụ:

~~~yaml
- changeSet:
    id: "baseline-001-orders"
    author: "db-team"
    changes:
      - createTable:
          tableName: orders
          columns:
            - column:
                name: id
                type: bigint
~~~

Sau khi đã sync nhiều môi trường, người viết sửa changeset thành một cấu trúc khác. Database legacy không tự được ALTER theo nội dung mới, vì changeset đã được đánh dấu là đã xử lý.

**Cách quản lý an toàn:**

1. Giữ baseline changeset bất biến sau khi tiếp nhận.
2. Tạo changeset mới cho mọi thay đổi tiếp theo.
3. Nếu baseline có lỗi, đánh giá từng môi trường và lịch sử trước khi sửa.
4. Xác định liệu cần một changeset correction, forward fix hoặc kế hoạch migration riêng.
5. Không dùng clear-checksums hoặc chỉnh DATABASECHANGELOG thủ công để che sai khác.

### 17.1. Baseline không phải tài liệu có thể chỉnh tùy ý

Changelog baseline vừa là mô tả trạng thái đã có, vừa là một phần lịch sử được Liquibase nhận diện. Một chỉnh sửa “chỉ để đẹp YAML” sau khi sync cũng cần được review theo quy tắc checksum, identity và tương thích giữa các môi trường.

## 18. Precondition và changelog-sync: giới hạn cần nhớ

Precondition hữu ích trong migration thông thường, nhưng không thay thế quy trình so sánh baseline.

Một điều kiện:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      tableName: orders
~~~

chỉ kiểm tra bảng tồn tại. Nó không so sánh đầy đủ:

- Tất cả cột và datatype.
- Nullability/default.
- Constraint/index.
- View/trigger/function.
- Quyền và đặc tính DBMS.
- Dữ liệu nghiệp vụ.

Ngoài ra, cần kiểm tra hành vi precondition cụ thể của command **changelog-sync** trên phiên bản Liquibase đang dùng. Không giả định lệnh sync sẽ thực thi toàn bộ validation giống update hoặc chứng minh nội dung changeset đúng với database.

**Đối chiếu trước sync phải là bước độc lập có bằng chứng.**

## 19. Không sync nhầm changeset tương lai

Đây là kịch bản rủi ro:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-create-orders"
      author: "db-team"
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint

  - changeSet:
      id: "release-2026-11-add-discount"
      author: "orders-team"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: discount
                  type: numeric(12,2)
~~~

Giả sử database legacy đã có bảng orders nhưng **chưa có cột discount**. Nếu changelog-sync được chạy trên cả changelog này mà không giới hạn, changeset thêm discount có thể cũng được ghi nhận đã xử lý. Sau đó update sẽ bỏ qua nó và cột discount không được tạo.

Cách tránh:

- Tách changelog baseline khỏi release mới.
- Hoặc dùng phạm vi filter được kiểm chứng, có quy tắc rõ ràng.
- Xem changelog-sync-sql trước khi sync.
- Sau sync, chạy status và xác nhận changeset tương lai vẫn pending.
- Không chỉ dựa vào việc tên changeset có chữ “baseline”.

## 20. Tiếp nhận database đã có Liquibase metadata

Có thể database legacy không hoàn toàn mới đối với Liquibase: trước đây một nhóm đã dùng Liquibase hoặc đã tạo DATABASECHANGELOG.

Khi đó:

1. Kiểm tra bảng metadata và schema đang dùng.
2. Xem history hiện tại.
3. Xác định artifact changelog cũ và identity changeset.
4. So sánh checksum và trạng thái schema.
5. Không chạy changelog-sync mù quáng vì các changeset có thể đã được ghi nhận hoặc có identity khác.
6. Đối chiếu với trạng thái thực tế trước khi quyết định baseline tiếp.

Nếu metadata đã tồn tại nhưng schema drift, phải giải quyết drift riêng. Changelog-sync không tự sửa history hoặc schema đã lệch.

## 21. Tiếp nhận database đã thay đổi thủ công ngoài Liquibase

Một trong những lý do cần baseline là database có thể có thao tác DBA ngoài changelog.

Ví dụ:

- DBA thêm index để xử lý incident.
- Một bảng được ALTER thủ công trong cửa sổ bảo trì.
- Trigger bị thay đổi để đáp ứng nghiệp vụ.
- Một cột được đổi default nhưng repository không được cập nhật.

Trước khi sync:

1. Thu thập thay đổi thủ công và bằng chứng phê duyệt.
2. Đối chiếu database với changelog hiện tại.
3. Quyết định thay đổi nào trở thành một phần baseline.
4. Chuẩn hóa changelog baseline để phản ánh trạng thái được chấp nhận.
5. Kiểm tra khả năng dựng mới.
6. Chỉ sync khi mọi khác biệt đã được phân loại.

**Không sync để xóa dấu vết thay đổi thủ công.** Hãy biến trạng thái thực tế thành một hợp đồng có thể kiểm tra và quản lý về sau.

## 22. Rủi ro khi sync với sai schema hoặc sai database

Một lỗi cấu hình có thể làm Liquibase ghi DATABASECHANGELOG vào đúng database nhưng schema nghiệp vụ lại được kiểm tra ở schema khác.

Cần xác nhận riêng:

- **URL/database/catalog**: đích kết nối.
- **defaultSchemaName**: schema mặc định cho thay đổi nếu không chỉ rõ.
- **liquibaseSchemaName**: schema lưu metadata nếu cấu hình riêng.
- **username**: principal đang kết nối.
- **schemaName/catalogName** trong từng changeset.
- **search_path** hoặc cơ chế chọn schema tương ứng DBMS.

Không dựa vào tên database trong biến môi trường hoặc tên profile Spring để suy ra schema thật. Kiểm tra metadata/catalog bằng chính connection mà Liquibase sử dụng.

## 23. Bảo vệ database trong quá trình đối chiếu và sync

Changelog-sync không chạy DDL nghiệp vụ, nhưng vẫn **ghi dữ liệu metadata** và có thể tạo bảng Liquibase nếu chưa tồn tại. Vì vậy cần:

- Chỉ dùng tài khoản được cấp phép.
- Có phê duyệt cho lần tiếp nhận production.
- Xác nhận endpoint bằng truy vấn nhận diện database.
- Đảm bảo changelog baseline bất biến trong suốt thao tác.
- Tránh pipeline khác update đồng thời.
- Có log và deployment record.
- Không đưa secret vào command line hoặc artifact.
- Giữ lại kết quả diff và biên bản phê duyệt.

Nếu việc kiểm kê đòi hỏi quyền catalog rộng, hãy dùng tài khoản đọc chuyên biệt và giới hạn quyền theo chính sách tổ chức.

## 24. Tích hợp với Spring Boot

Sau khi baseline được sync, ứng dụng Spring Boot có thể tiếp tục dùng Liquibase với changelog gốc.

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://legacy.internal:5432/orders
    username: orders_migrator
    password: "<inject-from-secret-manager>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
~~~

Đây là ví dụ minh họa, không chứa credential thật.

Điều cần chú ý:

- Artifact ứng dụng phải chứa đúng baseline và changelog release.
- CLI dùng khi tiếp nhận và Spring Boot runtime cần cùng định danh changelog, version và metadata configuration.
- Không chạy **update** lần đầu trên legacy database trước khi baseline được sync.
- Với production, cân nhắc chạy Liquibase như job triển khai riêng thay vì để mọi instance ứng dụng tự khởi động và chạy migration.
- Dùng datasource/tài khoản migration riêng khi quyền DDL không nên cấp cho runtime application.

### 24.1. Kiểm tra sau khi bật Spring Boot

Sau khi cấu hình, kiểm tra log cho thấy Liquibase kết nối đúng database và chỉ áp dụng những changeset release mới. Truy vấn DATABASECHANGELOG và catalog để xác minh. Nếu startup có lỗi, không giả định database chưa đổi; xem xét DDL tự commit và trạng thái thực tế.

## 25. Quy trình CI/CD cho tiếp nhận database legacy

Có thể chia pipeline thành các giai đoạn:

~~~text
Stage 1 — Inventory
  - Thu thập DBMS/version/schema
  - Snapshot hoặc bản sao được phép
  - Kiểm kê objects và permissions

Stage 2 — Baseline authoring
  - Generate changelog hoặc viết changelog có chủ đích
  - Review identity và dependency
  - Phân tách baseline với migration tương lai

Stage 3 — Reconciliation
  - Validate changelog
  - Diff reference/target đúng chiều
  - Phân loại mọi khác biệt
  - Kiểm tra database mới có thể dựng từ baseline

Stage 4 — Sync preview
  - Xác nhận target URL/schema/user
  - Chạy changelog-sync-sql nếu phiên bản hỗ trợ
  - Review chính xác tập changeset sẽ được ghi nhận

Stage 5 — Adoption
  - Phê duyệt
  - Chạy changelog-sync trên từng database đã đối chiếu
  - Đọc history và DATABASECHANGELOG
  - Xác minh schema không đổi ngoài metadata Liquibase

Stage 6 — Normal operation
  - Thêm changeset release mới
  - Status/update-sql
  - Update trên môi trường theo thứ tự
  - Theo dõi history và schema drift
~~~

### 25.1. Artifact và bằng chứng cần lưu

- Liquibase version và JDBC driver.
- DBMS/version, database/schema đã tiếp nhận.
- Artifact baseline và commit hash.
- Kết quả generate-changelog/diff đã review.
- Danh sách khác biệt được chấp nhận.
- SQL preview changelog-sync.
- Danh sách identity changeset được sync.
- Log CLI/pipeline và thời điểm thực hiện.
- Kết quả truy vấn DATABASECHANGELOG.
- Kết quả xác minh catalog sau sync.
- Người phê duyệt và deployment/adoption ID.

Không lưu password, token hoặc dữ liệu nhạy cảm trong bằng chứng.

## 26. Xử lý khi changelog-sync đánh dấu nhầm

Giả sử một changeset **add-discount-column** bị sync nhầm dù cột chưa tồn tại.

Hệ quả: Liquibase có thể coi changeset đã được xử lý; update tiếp theo sẽ không chạy ADD COLUMN như dự định.

Không sửa DATABASECHANGELOG ngay lập tức. Quy trình:

1. Dừng các lần update phụ thuộc.
2. Xác minh changeset identity và EXECTYPE.
3. Kiểm tra cột discount có tồn tại không.
4. Kiểm tra những changeset khác phụ thuộc cột đó.
5. Xác định có phải sync nhầm toàn bộ changelog hay chỉ một changeset.
6. Thiết kế kế hoạch reconciliation: thực thi DDL còn thiếu bằng changeset sửa chữa phù hợp, hoặc điều chỉnh trạng thái lịch sử qua quy trình được phê duyệt nếu thật sự cần.
7. Thử trên bản sao database.
8. Kiểm tra checksum, history, schema và update kế tiếp.
9. Ghi lại sự cố và bổ sung guard trong pipeline.

**Không xóa hàng history hoặc đổi EXECTYPE thủ công như cách mặc định.** Nếu cần sửa metadata, phải hiểu tác động tới identity/checksum và được review như một thao tác phục hồi đặc biệt.

## 27. Lỗi thường gặp khi tiếp nhận database bằng changelog-sync

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Sau sync, database không có bảng trong changelog | Sync chỉ ghi history, không thực thi DDL | Chỉ sync khi schema đã tồn tại; database mới cần update |
| Changeset release mới không chạy | Đã bị sync nhầm vào baseline | Kiểm tra phạm vi sync và history; lập kế hoạch reconciliation |
| History có changeset nhưng cột/index không có | Sync đánh dấu mà không tạo đối tượng | Kiểm tra catalog và EXECTYPE |
| Changeset bị chạy lại sau di chuyển file | FILENAME/logicalFilePath đổi | Ổn định logical path và identity |
| Diff còn nhiều khác biệt sau khi sync | Sync không sửa schema | Xử lý khác biệt trước sync; không dùng sync thay diff |
| Generate-changelog thiếu trigger/function | Reverse engineer không biểu diễn đủ đối tượng | Bổ sung SQL/changelog riêng và kiểm thử |
| Database mới không dựng được từ baseline | Thiếu đối tượng hoặc dependency | Test update trên database trống |
| Một môi trường sync được, môi trường khác không | Schema drift hoặc filter khác | Đối chiếu từng database riêng |
| Changelog-sync-sql chứa changeset ngoài baseline | Changelog/filter phạm vi quá rộng | Dừng, tách baseline hoặc sửa filter |
| Spring Boot cố chạy lại CREATE TABLE | Baseline chưa được sync hoặc metadata khác schema | Xác minh Liquibase metadata và connection |
| Checksum mismatch sau sửa baseline | Changeset đã được sync/triển khai bị sửa | Giữ baseline bất biến; dùng changeset mới |
| DDL thủ công không có trong changelog | Drift từ công cụ ngoài Liquibase | Phân loại và đưa vào baseline/correction có review |
| User không đọc được catalog | Thiếu quyền metadata | Dùng quyền đọc phù hợp, không tăng quyền tùy tiện |
| Sync nhầm database | JDBC URL/profile sai | Xác minh endpoint bằng truy vấn nhận diện trước khi ghi |

## 28. Bài thực hành: tiếp nhận database PostgreSQL đã có schema

**Bối cảnh:** một database PostgreSQL legacy đã có bảng **legacy_customer** với cột **id**, **email** và một index. Nhóm muốn quản lý tiếp bằng Liquibase.

**Điều kiện:** chỉ dùng database thử nghiệm hoặc bản sao được phép; không chạy thao tác sync trên production thật trong bài học.

### 28.1. Bước 1 — Kiểm tra database

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_user;
~~~

Kiểm tra bảng/cột:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'legacy_customer'
ORDER BY ordinal_position;
~~~

Kiểm tra index:

~~~sql
SELECT
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'legacy_customer';
~~~

Ghi nhận kết quả làm baseline hiện tại.

### 28.2. Bước 2 — Tạo changelog baseline

Ví dụ YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-001-legacy-customer"
      author: "adoption-team"
      dbms: postgresql
      changes:
        - createTable:
            schemaName: public
            tableName: legacy_customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
      rollback:
        - dropTable:
            schemaName: public
            tableName: legacy_customer
~~~

Changelog mô tả đối tượng đã tồn tại. Rollback dropTable ở đây chỉ minh họa khả năng biểu diễn change; **không chạy rollback trên database chứa dữ liệu cần giữ**.

### 28.3. Bước 3 — Validate và đối chiếu

~~~bash
liquibase --changelog-file=db/changelog/baseline.yaml validate
~~~

Chạy diff với reference/target được định hướng rõ ràng, hoặc đối chiếu catalog trực tiếp. Xác nhận datatype, nullability, primary key, index và schema tương đương. Nếu có khác biệt, sửa changelog hoặc quyết định baseline theo trạng thái được phê duyệt.

### 28.4. Bước 4 — Xem SQL sync dự kiến

~~~bash
liquibase --changelog-file=db/changelog/baseline.yaml changelog-sync-sql
~~~

Chỉ tiếp tục nếu phiên bản hỗ trợ và output chỉ ghi nhận changeset baseline. Nếu không có lệnh preview tương ứng, dùng cách xác minh được tài liệu phiên bản cung cấp và review phạm vi lệnh sync.

### 28.5. Bước 5 — Chạy changelog-sync

~~~bash
liquibase --changelog-file=db/changelog/baseline.yaml changelog-sync
~~~

Lệnh này không tạo lại bảng legacy_customer. Nó ghi nhận changeset baseline đã được xử lý trong metadata Liquibase.

### 28.6. Bước 6 — Xác minh sau sync

~~~bash
liquibase --changelog-file=db/changelog/baseline.yaml history
liquibase --changelog-file=db/changelog/baseline.yaml status --verbose
~~~

Kiểm tra DATABASECHANGELOG và catalog:

- Có đúng identity baseline không?
- Bảng legacy_customer vẫn giữ nguyên không?
- Index và constraints có còn như trước không?
- Có changeset nào ngoài baseline bị sync không?
- Status có phản ánh đúng những changeset chưa được đồng bộ không?

### 28.7. Bước 7 — Thêm migration mới

Sau baseline, thêm changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "release-001-add-customer-status"
      author: "adoption-team"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: legacy_customer
      changes:
        - addColumn:
            schemaName: public
            tableName: legacy_customer
            columns:
              - column:
                  name: status
                  type: varchar(24)
      rollback:
        - dropColumn:
            schemaName: public
            tableName: legacy_customer
            columnName: status
~~~

Chạy status và update-sql để xác nhận changeset mới vẫn pending và SQL dự kiến đúng. Sau đó mới update trên database thử nghiệm.

**Kết quả mong đợi:** Liquibase đã tiếp nhận cấu trúc cũ qua baseline; thay đổi status mới được triển khai bằng update bình thường.

## 29. Bài thực hành nâng cao: phát hiện sync nhầm changeset tương lai

Giả sử changelog chứa:

~~~text
baseline-001-create-customer
baseline-002-create-orders
release-001-add-discount-column
~~~

Database legacy đã có customer và orders nhưng chưa có discount.

**Yêu cầu:**

1. Nếu chạy changelog-sync trên cả changelog, điều gì có thể xảy ra?
2. Vì sao release-001 không được nằm trong phạm vi sync?
3. Cách kiểm tra nào giúp phát hiện vấn đề trước khi ghi metadata?
4. Sau khi sync baseline, status phải cho biết điều gì?
5. Nếu release-001 đã bị sync nhầm, xử lý thế nào?

**Gợi ý:**

- Sync có thể ghi nhận cả changeset release chưa thực sự tồn tại.
- Chia baseline changelog riêng hoặc giới hạn filter đã kiểm chứng.
- Xem changelog-sync-sql trước.
- Kiểm tra catalog và history sau sync.
- Nếu sync nhầm, dừng rollout, xác minh metadata/schema và thử reconciliation trên bản sao database; không xóa history thủ công ngay.

## 30. Câu hỏi tự kiểm tra

**1. changelog-sync có tạo bảng trong database legacy không?**

Không. Lệnh ghi nhận changeset như đã được xử lý; nó không thực thi CREATE TABLE hoặc các change bên trong.

**2. Khi nào nên chạy changelog-sync?**

Khi database đã có trạng thái tương đương với các changeset baseline trong phạm vi được chọn và nhóm đã đối chiếu/phê duyệt.

**3. Vì sao phải xem changelog-sync-sql trước?**

Để phát hiện phạm vi changeset sẽ được ghi nhận, tránh sync nhầm migration tương lai hoặc nhầm database metadata.

**4. Có thể dùng changelog-sync trên database trống để khởi tạo schema không?**

Không. Dùng update để thực thi changeset tạo schema trên database trống.

**5. generate-changelog có tạo baseline hoàn chỉnh không?**

Không được mặc định như vậy. Nó tạo điểm khởi đầu từ đối tượng mà Liquibase có thể reverse engineer; cần review và bổ sung những đối tượng/thuộc tính còn thiếu.

**6. diff và diff-changelog có giống nhau không?**

Không. Diff so sánh và báo khác biệt; diff-changelog sinh changelog thể hiện các thay đổi theo chiều reference/target đã chọn.

**7. Nếu bảng tồn tại nhưng thiếu foreign key, có nên sync changeset tạo bảng không?**

Không nên kết luận chỉ dựa vào tableExists. Phải xác minh toàn bộ cấu trúc và quyết định baseline/correction trước khi sync.

**8. Vì sao phải kiểm tra DATABASECHANGELOG sau sync?**

Để xác nhận đúng identity changeset đã được ghi nhận, không có changeset tương lai hoặc changeset ngoài phạm vi bị đánh dấu nhầm.

**9. Sau sync, có nên sửa baseline changeset để cập nhật schema không?**

Không nên sửa tùy tiện. Tạo changeset mới cho thay đổi tiếp theo để giữ lịch sử và checksum nhất quán.

**10. Vì sao cần thử update trên database trống?**

Để chứng minh baseline có thể tái tạo schema, thay vì chỉ phản ánh database legacy đã tồn tại.

**11. Nếu history có changeset nhưng object không có thì sao?**

Có thể sync nhầm, schema drift hoặc metadata không tương ứng. Kiểm tra catalog, identity và artifact trước khi reconciliation.

**12. Có thể copy DATABASECHANGELOG từ production sang staging không?**

Không nên. Mỗi database cần được quản lý và đối chiếu riêng; không sao chép metadata lịch sử để giả lập trạng thái.

## 31. Checklist phê duyệt baseline bằng changelog-sync

- [ ] Đã xác nhận đúng DBMS, version, URL, database, schema và user.
- [ ] Có bản sao/snapshot hoặc phương án phục hồi được phê duyệt.
- [ ] Đã kiểm kê table, column, constraint, index, view, routine, trigger, sequence, partition và quyền trong phạm vi cần quản lý.
- [ ] Đã phân biệt schema baseline với reference data và operational data.
- [ ] Changelog baseline được tạo từ trạng thái thật hoặc tài liệu DDL đã xác minh.
- [ ] Đã review những đối tượng mà generate-changelog/diff không thể biểu diễn đầy đủ.
- [ ] Reference/target của diff và diff-changelog đúng chiều.
- [ ] Mọi khác biệt đã được phân loại: cần sửa, chấp nhận hoặc quản lý riêng.
- [ ] Baseline được tách rõ khỏi migration tương lai.
- [ ] ID, AUTHOR, FILENAME/logicalFilePath ổn định.
- [ ] Preconditions không bị dùng như phép so sánh schema toàn diện.
- [ ] Đã chạy validate.
- [ ] Đã xem changelog-sync-sql nếu phiên bản hỗ trợ.
- [ ] Tập changeset được sync chỉ gồm những thay đổi đã tồn tại và được phê duyệt.
- [ ] Đã xác nhận endpoint và metadata schema trước khi ghi.
- [ ] Không có tiến trình Liquibase khác chạy cạnh tranh.
- [ ] Đã chạy changelog-sync riêng trên từng database cần tiếp nhận.
- [ ] Đã đọc history và truy vấn DATABASECHANGELOG sau sync.
- [ ] Đã kiểm tra catalog/schema thực tế không bị thay đổi ngoài metadata Liquibase.
- [ ] Các changeset tương lai vẫn pending.
- [ ] Đã thử update toàn bộ changelog trên database trống riêng.
- [ ] Đã kiểm tra checksum và giữ baseline bất biến sau tiếp nhận.
- [ ] Có log adoption, artifact hash, thời điểm, người phê duyệt và kết quả đối chiếu.
- [ ] Không chỉnh sửa DATABASECHANGELOG thủ công để che sai lệch.
- [ ] CI/CD và Spring Boot sử dụng đúng artifact, datasource và metadata configuration.

**Kết luận:** **changelog-sync** là bước ghi nhận baseline hữu ích khi tiếp nhận database legacy: sau khi xác minh schema hiện tại tương đương changelog, Liquibase có thể đánh dấu các changeset baseline đã được xử lý mà không chạy lại DDL. An toàn phụ thuộc vào chất lượng kiểm kê, chiều so sánh reference/target, phạm vi changeset được sync và việc xác minh cả DATABASECHANGELOG lẫn catalog thực tế. Hãy tách baseline khỏi migration tương lai, xem SQL đồng bộ trước khi ghi history, thử dựng database mới bằng update và giữ baseline ổn định. Khi đó database legacy và database mới có thể cùng tiếp tục một lịch sử migration rõ ràng, có thể kiểm chứng và vận hành qua nhiều môi trường.

