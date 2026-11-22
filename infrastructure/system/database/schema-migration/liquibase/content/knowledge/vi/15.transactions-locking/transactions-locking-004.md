# Rủi ro trạng thái dở dang khi changeset không có giao dịch

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Người học cần biết thực hiện migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Giao dịch và khóa** và giải quyết một câu hỏi then chốt: **điều gì xảy ra nếu changeset chạy ngoài transaction, một số lệnh đã có hiệu lực nhưng lệnh tiếp theo thất bại hoặc tiến trình Liquibase bị ngắt?**

Đây là tình huống nguy hiểm hơn một lỗi cú pháp đơn thuần. Database có thể đã thay đổi, trong khi Liquibase không ghi nhận changeset đã hoàn tất trong **DATABASECHANGELOG**. Nếu pipeline thử lại một cách mù quáng, nó có thể tạo trùng đối tượng, cập nhật dữ liệu lần thứ hai hoặc thất bại ở trạng thái khó phục hồi hơn.

Sau bài học, bạn cần có thể:

- Hiểu **runInTransaction** và ranh giới giao dịch ở cấp changeset, không nhầm với toàn bộ changelog.
- Nhận diện khác biệt giữa lỗi **trước commit**, lỗi **sau một phần thao tác có hiệu lực** và lỗi **ghi nhận lịch sử**.
- Giải thích vì sao một changeset không có transaction có thể để lại trạng thái dở dang dù DATABASECHANGELOG chưa ghi EXECUTED.
- Phân biệt **DATABASECHANGELOGLOCK** với transaction và hiểu vì sao khóa Liquibase không bảo vệ tính nguyên tử của SQL.
- Thiết kế changeset nhỏ, SQL phù hợp DBMS, precondition, quy trình kiểm tra, xử lý retry, rollback hoặc forward fix.
- Xây dựng quy trình ứng phó sự cố có thể áp dụng cho Spring Boot, CI/CD và production.

## 2. Giao dịch trong Liquibase: phạm vi thực sự ở đâu?

**Transaction** là cơ chế cho phép một nhóm thao tác được xác nhận bằng commit hoặc hoàn tác bằng rollback, trong giới hạn mà hệ quản trị cơ sở dữ liệu hỗ trợ. Nếu các thao tác cùng nằm trong một transaction thực sự và lỗi xảy ra trước commit, database có thể hoàn tác thay đổi chưa commit.

**Changeset** là đơn vị thực thi và ghi lịch sử cốt lõi của Liquibase. Thông thường, Liquibase xử lý changeset theo thứ tự changelog, kiểm tra lịch sử DATABASECHANGELOG rồi áp dụng các thay đổi cần thiết.

Với **runInTransaction: true** (mặc định), Liquibase cố gắng thực thi từng changeset trong transaction khi database hỗ trợ. Nhưng **mỗi changeset không đồng nghĩa toàn bộ release**:

~~~text
Changelog
  |
  +-- Changeset A (tạo bảng)           --> commit A
  |
  +-- Changeset B (thêm dữ liệu chuẩn) --> commit B
  |
  +-- Changeset C (tạo index)          --> lỗi
  |
  +-- Changeset D                      --> chưa được xử lý
~~~

Nếu C lỗi, A và B đã commit trước đó không tự động bị rollback. Việc muốn trở về trước cả đợt phát hành phải là một kế hoạch rollback có kiểm chứng, không phải một tính chất ngầm định của changelog.

Khi một changeset có **runInTransaction: false**, Liquibase không bao các thao tác của changeset trong transaction do nó quản lý. Từng SQL có hiệu lực như thế nào còn phụ thuộc database, driver, autocommit, câu lệnh DDL/DML và trạng thái connection. **False không phải chỉ thị để database luôn commit sau từng dòng SQL theo một quy tắc duy nhất trên mọi hệ quản trị.**

## 3. Ba lớp bảo đảm cần phân biệt

Một thay đổi Liquibase có ít nhất ba lớp trạng thái:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Câu lệnh SQL** | DDL/DML đã được database thực thi và có hiệu lực chưa? | Cột status đã được thêm; các dòng đã được UPDATE |
| **Changeset** | Tất cả change trong một changeset đã hoàn tất chưa? | UPDATE thành công nhưng INSERT thất bại |
| **Lịch sử Liquibase** | DATABASECHANGELOG đã ghi nhận kết quả changeset chưa? | Có bản ghi EXECUTED hoặc chưa có bản ghi |

**Tính nguyên tử** mong muốn là trạng thái ứng dụng và lịch sử triển khai không rơi vào tình huống “một nửa đã áp dụng, một nửa chưa được ghi”. Nhưng một câu lệnh có thể được database commit mà quá trình Liquibase sau đó gặp lỗi trước khi hoàn tất ghi lịch sử.

Vì vậy, khi gặp sự cố không được chỉ xem **mã thoát của pipeline** hoặc chỉ kiểm tra **DATABASECHANGELOG**. Cần kiểm tra cả **schema/dữ liệu thực** và log của quá trình thực thi.

## 4. runInTransaction: true và false

Ví dụ khai báo rõ hai lựa chọn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: migration-team
      runInTransaction: true
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: loyalty_tier
                  type: VARCHAR(30)

  - changeSet:
      id: 2026-11-19-002
      author: migration-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: >
              CREATE INDEX CONCURRENTLY idx_customer_loyalty_tier
              ON customer (loyalty_tier)
      rollback:
        - sql:
            sql: >
              DROP INDEX CONCURRENTLY IF EXISTS idx_customer_loyalty_tier
~~~

**Ý nghĩa:**

- Changeset đầu tiên theo mặc định giao dịch của Liquibase. Khả năng rollback DDL phụ thuộc DBMS và loại thao tác.
- Changeset thứ hai dùng **CREATE INDEX CONCURRENTLY** của PostgreSQL, một lệnh không được thực thi bên trong transaction block thông thường. Đây là lý do hợp lệ để chọn false.
- Câu lệnh tạo index ngoài transaction không có nghĩa toàn bộ công việc xây dựng index là một bước luôn nguyên tử và không có trạng thái trung gian. Nếu lỗi, PostgreSQL có thể để lại index không hợp lệ.
- Phần rollback trong changeset mô tả cách hoàn tác khi chủ động rollback một changeset phù hợp; **Liquibase không mặc định tự chạy khối rollback được khai báo chỉ vì lệnh update ở giữa thất bại**.

### Khi nào không nên dùng false?

- Vì migration chạy chậm hoặc gây lock: cần tìm hiểu SQL, dung lượng bảng và quy trình triển khai trước.
- Vì muốn bỏ qua lỗi dữ liệu: thay transaction mode không sửa điều kiện dữ liệu bị vi phạm.
- Vì changeset chứa nhiều thao tác không liên quan: nên tách thay đổi thay vì tắt transaction.
- Vì muốn “cho pipeline đi tiếp”: đây là cách dễ che giấu lỗi và tạo drift.
- Vì hy vọng rollback dễ hơn: trái lại, false thường làm việc khôi phục khó hơn.

**Nguyên tắc mặc định:** giữ runInTransaction=true; chỉ chọn false khi có yêu cầu kỹ thuật rõ ràng, đã kiểm chứng trên DBMS đích và có kế hoạch xử lý phần việc dở dang.

## 5. Kịch bản điển hình: lệnh thứ nhất đã commit, lệnh thứ hai thất bại

Giả sử bảng **customer** đã có cột status, còn bảng **migration_audit** chưa tồn tại. Changeset sau cố cập nhật dữ liệu rồi ghi nhật ký:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003
      author: migration-team
      runInTransaction: false
      changes:
        - sql:
            sql: >
              UPDATE customer
              SET status = 'ACTIVE'
              WHERE status IS NULL
        - sql:
            sql: >
              INSERT INTO migration_audit(event_name)
              VALUES ('CUSTOMER_STATUS_BACKFILL')
~~~

Trên DBMS/connection mà UPDATE thứ nhất được commit riêng và INSERT lỗi, trạng thái có thể là:

1. UPDATE đã thay đổi những khách hàng có status NULL.
2. INSERT thất bại vì không có bảng migration_audit.
3. Liquibase báo lỗi của changeset.
4. DATABASECHANGELOG không có bản ghi hoàn tất cho changeset này, dù UPDATE đã có tác động.
5. Lần chạy sau có thể tiếp tục gặp lỗi INSERT; nếu thay đổi đầu tiên không idempotent, dữ liệu có thể bị sửa lặp.

**Đây là ví dụ minh họa rủi ro, không phải mẫu changeset được khuyến khích.** Không nên đặt hai câu lệnh không đồng nhất về mục đích trong một changeset ngoài transaction.

### Tại sao ngay cả UPDATE có điều kiện cũng chưa đủ an toàn?

Trong ví dụ, WHERE status IS NULL khiến các dòng đã chuyển sang ACTIVE không bị sửa lần nữa. Đây là một yếu tố tốt, nhưng chưa đủ để khẳng định toàn bộ quy trình idempotent:

- Có dữ liệu mới được tạo sau lần chạy đầu không?
- Có dịch vụ khác thay đổi status trong lúc migration không?
- Một dòng NULL có phải luôn được gán ACTIVE không?
- Cơ chế kiểm tra và ghi nhật ký có thể lặp an toàn không?
- Số hàng được cập nhật có được đối soát với tiêu chí nghiệp vụ không?

Cần đánh giá **cả chuỗi thay đổi và dữ liệu thật**, không chỉ một mệnh đề WHERE.

## 6. Các dạng trạng thái dở dang

Trạng thái dở dang không chỉ là “có một cột rồi nhưng chưa có cột thứ hai”.

### 6.1. Schema dở dang

- Đã tạo bảng nhưng chưa thêm foreign key.
- Đã thêm cột mới nhưng chưa backfill dữ liệu.
- Đã đổi tên một đối tượng nhưng ứng dụng vẫn dùng tên cũ.
- Đã tạo index một phần hoặc index không hợp lệ.
- Đã xóa constraint nhưng chưa tạo constraint thay thế.

### 6.2. Dữ liệu dở dang

- Một phần hàng đã cập nhật, phần còn lại chưa.
- Bản ghi tham chiếu đã thêm nhưng dữ liệu nghiệp vụ chưa chuyển sang mã mới.
- Một số bảng đã đổi ID trong khi bảng liên quan chưa cập nhật khóa ngoại.
- Một câu SQL có hiệu lực nhưng audit hoặc checkpoint tiếp theo chưa được ghi.

### 6.3. Lịch sử dở dang

- Thay đổi thực tế có hiệu lực, nhưng changeset vẫn xuất hiện trong danh sách pending.
- Một changeset được đánh dấu MARK_RAN dù thay đổi thực tế chưa tương đương.
- Một thao tác sửa tay khiến DATABASECHANGELOG không còn phản ánh quá trình triển khai.
- Pipeline cho rằng migration hoàn tất trong khi constraint/index chưa thực sự hợp lệ.

### 6.4. Ứng dụng dở dang

- Phiên bản ứng dụng mới đã triển khai nhưng migration chưa đủ điều kiện.
- Một số instance đang ghi vào cột cũ, các instance khác ghi vào cột mới.
- Job nền vẫn dùng cấu trúc cũ trong lúc bảng bị thay đổi.
- Tính năng được bật trước khi backfill và hậu kiểm hoàn tất.

Những dạng trạng thái này có thể xuất hiện đồng thời. Vì vậy, khôi phục sự cố đòi hỏi đánh giá **database, ứng dụng và lịch sử triển khai**, không chỉ sửa một câu SQL.

## 7. Vì sao runInTransaction=true cũng không bảo đảm tuyệt đối?

Tính nguyên tử DDL là đặc tính phụ thuộc DBMS và từng lệnh. Liquibase có thể yêu cầu transaction nhưng database vẫn có những thao tác gây implicit commit hoặc không rollback được như DML.

| DBMS | Điều cần đánh giá |
|---|---|
| **PostgreSQL** | Nhiều DDL hỗ trợ transaction; một số lệnh như CREATE INDEX CONCURRENTLY yêu cầu ngoài transaction block |
| **MySQL** | Nhiều DDL gây implicit commit; khả năng atomic DDL của engine không đồng nghĩa có thể rollback cả chuỗi changeset |
| **Oracle** | Nhiều DDL có implicit commit; rollback theo transaction không thể hoàn tác những DDL đã commit |
| **SQL Server** | Nhiều DDL hỗ trợ transaction, nhưng tùy loại lệnh và phiên bản vẫn có hạn chế |
| **SQLite** | Có transaction cho nhiều thay đổi schema, nhưng ALTER TABLE và locking có giới hạn riêng |

**Atomic DDL** ở một số engine có thể bảo đảm một câu DDL không để lại cấu trúc hỏng sau crash, nhưng không đồng nghĩa một lệnh DDL sẽ cùng rollback với toàn bộ những câu lệnh khác trong changeset. Không được suy từ tên tính năng sang phạm vi đảm bảo vượt quá tài liệu của DBMS.

Vì vậy, bảng đánh giá thực tế phải ghi **DBMS/phiên bản, loại SQL, engine, phiên bản Liquibase và driver**. Thử nghiệm trên H2 hoặc SQLite không thay thế kiểm chứng trên MySQL/PostgreSQL production nếu hành vi DDL là điểm rủi ro.

## 8. PostgreSQL CREATE INDEX CONCURRENTLY: một lệnh vẫn có thể để lại dấu vết

Một trường hợp quan trọng là CREATE INDEX CONCURRENTLY. Lệnh này giúp giảm mức độ chặn ghi trong một số tình huống nhưng phải chạy ngoài transaction block và có thể mất thời gian đáng kể.

Khi lệnh thất bại, PostgreSQL có thể còn một **index invalid**. Khi đó:

- Index có thể hiện diện trong catalog dù chưa sử dụng được đúng mục tiêu.
- Lần CREATE INDEX cùng tên có thể báo lỗi trùng tên.
- Precondition chỉ kiểm tra **indexExists** có thể trả kết quả index tồn tại, nhưng chưa xác nhận index hợp lệ.
- Một chính sách tự động MARK_RAN dựa trên tên index có thể che giấu việc index vẫn không dùng được.

Có thể kiểm tra PostgreSQL catalog bằng truy vấn chỉ đọc:

~~~sql
SELECT n.nspname AS schema_name,
       t.relname AS table_name,
       c.relname AS index_name,
       i.indisvalid,
       i.indisready
FROM pg_index AS i
JOIN pg_class AS c ON c.oid = i.indexrelid
JOIN pg_class AS t ON t.oid = i.indrelid
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'idx_customer_loyalty_tier';
~~~

**indisvalid** giúp nhận biết index có được xem là hợp lệ cho mục tiêu sử dụng hay không; **indisready** liên quan khả năng index được duy trì khi có ghi dữ liệu. Cần phân tích cả log và trạng thái tiến trình tạo index để kết luận nên chờ, cleanup hay tạo lại.

Nếu cần dọn một index invalid, hành động DROP INDEX hoặc tạo lại phải được xác nhận theo trạng thái thực tế và thực hiện bằng một quy trình kiểm soát riêng. Không chạy lệnh xóa dựa duy nhất vào một cảnh báo của Liquibase.

## 9. DATABASECHANGELOG không phải nhật ký từng câu lệnh SQL

Liquibase sử dụng **DATABASECHANGELOG** để theo dõi changeset đã chạy. Mỗi changeset được nhận diện thông qua **id, author và đường dẫn changelog** (hoặc logicalFilePath đã cấu hình) cùng thông tin lịch sử khác như thời điểm và loại thực thi.

Bảng này không phải bản ghi chi tiết bảo đảm từng câu SQL đã có hiệu lực:

- **Không có row** cho changeset chưa chắc nghĩa là database không bị thay đổi bởi changeset ấy.
- **Có row EXECUTED** là lịch sử Liquibase đã ghi nhận changeset hoàn tất, không thay thế hậu kiểm nghiệp vụ.
- **Có row MARK_RAN** thường nghĩa là changeset được ghi nhận mà không thực hiện các change trong trường hợp đó.
- **Có row RERAN** liên quan những changeset được phép chạy lại theo cơ chế tương ứng.

### Cửa sổ rủi ro khi lịch sử được ghi sau SQL

Khi một hoặc nhiều thao tác đã commit bên ngoài transaction chung, nhưng tiến trình lỗi trước bước ghi lịch sử, lần update sau có thể vẫn xem changeset là pending. Điều này giải thích vì sao **retry không được thực hiện mù quáng** ngay sau khi nhận lỗi.

Nếu muốn sửa lệch lịch sử, phải có bằng chứng đầy đủ về những thay đổi đã có hiệu lực; không tự chèn row vào DATABASECHANGELOG, không đổi checksum hoặc dùng clear-checksums như một cách che giấu trạng thái không nhất quán.

## 10. DATABASECHANGELOGLOCK không giải quyết vấn đề này

**DATABASECHANGELOGLOCK** giúp Liquibase điều phối để tránh nhiều tiến trình Liquibase cùng update một database theo cơ chế lock của nó.

Lock này **không tương đương transaction của migration**:

- Nó không rollback phần SQL đã có hiệu lực.
- Nó không bảo đảm một changeset nhiều lệnh sẽ nguyên tử.
- Nó không khóa mọi thao tác của ứng dụng đối với các bảng nghiệp vụ.
- Nó không ngăn một DBA hay công cụ khác thay đổi schema ngoài Liquibase.
- Nó không bảo đảm index hoặc constraint được tạo đầy đủ.

Nếu Liquibase bị ngắt, lock có thể còn ở trạng thái cần điều tra. Trước khi xử lý khóa, phải xác minh **không còn tiến trình migration đang chạy hoặc đang chờ**, đặc biệt khi có DDL dài. Việc release lock khi một tiến trình vẫn còn thực thi có thể khiến tình trạng chồng lấn trở nên nghiêm trọng.

### Hai tầng khóa cần phân biệt

| Tầng | Mục đích | Có giải quyết partial migration? |
|---|---|---|
| DATABASECHANGELOGLOCK | Điều phối các lần chạy Liquibase | Không |
| Khóa do DBMS quản lý | Bảo vệ tính nhất quán đồng thời của bảng, DDL/DML | Chỉ trong giới hạn loại khóa, transaction và SQL cụ thể |

Tắt transaction không có nghĩa SQL không còn dùng bất kỳ khóa database nào. CREATE INDEX CONCURRENTLY, UPDATE, ALTER TABLE và các thao tác khác vẫn có thể cần khóa hoặc chờ những transaction khác.

## 11. Dấu hiệu nhận biết trạng thái dở dang

Trong quá trình vận hành, các dấu hiệu sau cần được điều tra thay vì thử lại ngay:

1. Liquibase báo lỗi sau khi đã in log thực thi một số lệnh.
2. Changeset vẫn pending trong status, nhưng bảng/cột/index được kỳ vọng đã tồn tại.
3. Lần chạy lại báo duplicate table, duplicate column hoặc duplicate index.
4. Có sự khác biệt giữa DATABASECHANGELOG và catalog thực tế.
5. Số bản ghi backfill tăng một phần, các bản ghi còn lại chưa chuyển.
6. Index có tên đúng nhưng **invalid**, constraint chưa được validate hoặc dữ liệu vi phạm còn tồn tại.
7. Pipeline thất bại do timeout, process bị kill, restart container hoặc mất kết nối.
8. Ứng dụng ghi dữ liệu lỗi vì có giai đoạn schema mới chưa hoàn chỉnh.

Một thay đổi bên ngoài Liquibase cũng có thể gây hiện tượng tương tự. Cần dựa vào thời gian, log, lịch sử deployment và metadata database để xác định nguồn gốc trước khi xử lý.

## 12. Quy trình xử lý sự cố: dừng, quan sát, đối soát, quyết định

Khi một changeset ngoài transaction thất bại, nên thực hiện quy trình có kiểm soát:

### Bước 1: dừng việc retry và các deployment phụ thuộc

Tạm dừng lần chạy Liquibase kế tiếp, tránh pipeline tự động chạy lại. Nếu ứng dụng mới phụ thuộc schema chưa hoàn tất, cân nhắc giữ ở phiên bản tương thích hoặc tắt tính năng theo kế hoạch vận hành.

**Không mặc định restart Spring Boot là an toàn** khi ứng dụng cấu hình tự chạy Liquibase: restart có thể dẫn đến nỗ lực update lại cùng changeset.

### Bước 2: xác định trạng thái của tiến trình

- Tiến trình Liquibase hoặc câu DDL dài còn hoạt động không?
- Có transaction, lock, session hoặc tác vụ tạo index đang chạy không?
- Database có đang chịu lock hoặc replication lag bất thường không?
- Có nhiều pipeline/instance cùng tìm cách chạy update không?

Nếu có tiến trình còn hoạt động, không tự ý dọn đối tượng hoặc giải phóng lock chỉ để đưa pipeline về trạng thái xanh.

### Bước 3: thu thập bằng chứng

Ghi lại:

- Tên database/schema, DBMS và phiên bản.
- Git commit chứa changelog, phiên bản Liquibase và driver.
- **id, author, file path** của changeset lỗi.
- runInTransaction, dbms filter, context/label và các tham số triển khai.
- SQL thực tế, log, thời điểm lỗi, thời gian trước khi ngắt.
- Bản ghi DATABASECHANGELOG liên quan.
- Danh sách đối tượng đã được tạo/sửa và dữ liệu đã thay đổi.

Không ghi credential hoặc dữ liệu nhạy cảm không cần thiết vào báo cáo sự cố.

### Bước 4: kiểm tra trực tiếp database

Đối với DDL: kiểm tra bảng, cột, index, constraint, default và trạng thái validation theo catalog DBMS. Đối với dữ liệu: kiểm tra số hàng, phân bố giá trị, độ toàn vẹn, bản ghi còn thiếu và phần đã chuyển đổi.

Với những thao tác ảnh hưởng lớn, nên thực hiện truy vấn chẩn đoán chỉ đọc trước. Không dựa vào việc một tên đối tượng tồn tại để kết luận mọi SQL của changeset đã xong.

### Bước 5: phân loại mức độ hoàn tất

| Tình trạng xác minh | Hướng xử lý |
|---|---|
| Chưa thay đổi gì có hiệu lực | Có thể sửa nguyên nhân rồi chạy lại sau khi kiểm chứng |
| Đã áp dụng một phần, có thể hoàn tác an toàn | Thực hiện cleanup/rollback có kiểm soát rồi retry |
| Đã áp dụng một phần, không thể hoàn tác an toàn | Thiết kế forward fix và đối soát dữ liệu |
| Tất cả thay đổi đã có hiệu lực, chỉ lịch sử bị thiếu | Đối chiếu đầy đủ và dùng quy trình điều chỉnh lịch sử được phê duyệt; không tự ghi DATABASECHANGELOG |
| Không xác định rõ | Giữ dừng, thu thập thêm bằng chứng và bảo toàn dữ liệu |

### Bước 6: thực hiện thay đổi phục hồi ở môi trường thử nghiệm trước

Kiểm tra trên bản sao có lịch sử và dữ liệu tương tự khi khả thi. Với production, thay đổi phục hồi phải có người chịu trách nhiệm, SQL được review và điểm dừng khi kết quả khác kỳ vọng.

### Bước 7: hậu kiểm và mở lại triển khai

Chỉ tiếp tục khi database, lịch sử Liquibase và ứng dụng ở trạng thái thống nhất. Ghi nhận root cause và điều chỉnh thiết kế changeset để giảm rủi ro lặp lại.

## 13. Chọn rollback, cleanup hay forward fix?

Ba lựa chọn không thay thế nhau.

**Rollback transaction** là cơ chế database hoàn tác thao tác chưa commit. Nếu changeset đã chạy ngoài transaction và một phần đã có hiệu lực, rollback transaction của kết nối hiện tại không nhất thiết lấy lại được phần đó.

**Rollback Liquibase** dùng định nghĩa rollback của changeset đã được ghi nhận phù hợp trong lịch sử. Nếu changeset thất bại và **không được ghi nhận là đã chạy**, đừng giả định lệnh rollback thông thường sẽ tự chạy chính xác những thao tác đã có hiệu lực dở dang.

**Cleanup thủ công có kiểm soát** là việc xác minh rồi xóa/sửa phần còn sót để đưa database về trạng thái có thể tiếp tục theo đúng kế hoạch. Ví dụ dọn index invalid. Cleanup phải có bằng chứng, không phải thử xóa đối tượng cho tới khi hết lỗi.

**Forward fix** là tạo thay đổi mới hoặc quy trình sửa tiến về phía trước để đưa database tới trạng thái mong muốn mà không cố đảo ngược dữ liệu đã được sử dụng. Đây có thể là phương án phù hợp hơn khi migration đã thay đổi dữ liệu nghiệp vụ mà các giao dịch mới tiếp tục phát sinh.

### Vì sao rollback tự động có thể nguy hiểm?

Giả sử changeset thêm cột status_code, sau đó ứng dụng mới đã ghi hàng nghìn giá trị vào cột đó. DROP COLUMN để “trả về như cũ” sẽ làm mất dữ liệu vừa phát sinh, kể cả khi cú pháp rollback hợp lệ.

Đừng chỉ hỏi **có câu SQL đảo ngược không?**. Hãy hỏi **dữ liệu hiện tại có còn tương thích với thao tác đảo ngược không?**.

## 14. Thiết kế changeset ngoài transaction: nhỏ và có khả năng kiểm tra

Một changeset ngoài transaction tốt nên thỏa mãn các điểm:

1. **Có lý do bắt buộc hoặc có kiểm chứng** để chạy ngoài transaction.
2. **Phạm vi hẹp**, lý tưởng là một thao tác chính như CREATE INDEX CONCURRENTLY.
3. **DBMS tường minh** khi SQL phụ thuộc cú pháp riêng.
4. **Precondition chặt**, đánh giá trạng thái trước và phát hiện sai lệch có thể gây tác hại.
5. **Không dùng MARK_RAN mù quáng** chỉ vì đối tượng cùng tên tồn tại.
6. **Có bước hậu kiểm** xác nhận kết quả thật, ví dụ index valid hay dữ liệu đủ hàng.
7. **Có phương án cleanup/forward fix** nếu thao tác lỗi, không chỉ câu rollback.
8. **Có log và dữ liệu quan sát đủ** để xác định SQL nào đã có hiệu lực.
9. **Không sửa changeset đã chạy**, bảo toàn định danh và checksum.

Ví dụ một changeset index duy nhất với precondition mang tính bảo thủ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-004-create-customer-index
      author: migration-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - not:
            - indexExists:
                tableName: customer
                indexName: idx_customer_loyalty_tier
      changes:
        - sql:
            sql: >
              CREATE INDEX CONCURRENTLY idx_customer_loyalty_tier
              ON customer (loyalty_tier)
      rollback:
        - sql:
            sql: >
              DROP INDEX CONCURRENTLY IF EXISTS idx_customer_loyalty_tier
~~~

**Cảnh báo:** ví dụ chỉ minh họa điều kiện tối thiểu. Trước production phải xác nhận cột loyalty_tier tồn tại, đúng kiểu, index cùng tên chưa được dùng với định nghĩa khác và không có index invalid do lần chạy trước. Precondition indexExists đơn thuần **không chứng minh index hợp lệ**. Nếu precondition thất bại, HALT là chủ ý để điều tra thay vì MARK_RAN.

Không nên đưa các thao tác DML backfill hoặc DDL phụ thuộc sau CREATE INDEX CONCURRENTLY vào cùng changeset runInTransaction=false. Hãy tách chúng, có bước kiểm chứng trước khi tiếp tục.

## 15. Precondition không chữa được trạng thái dở dang

Precondition là bộ lọc và bước kiểm tra trước thay đổi; nó không phải cơ chế transaction.

| Hành vi precondition | Rủi ro nếu trạng thái đã dở dang |
|---|---|
| **HALT** | Dừng để điều tra; thường là lựa chọn an toàn khi không rõ database |
| **WARN** | Vẫn có thể chạy SQL khi điều kiện không đạt; có thể làm hỏng thêm |
| **CONTINUE** | Bỏ qua changeset trong lần chạy hiện tại nhưng để pending; có thể khiến release thiếu bước bắt buộc |
| **MARK_RAN** | Ghi nhận changeset đã chạy dù SQL bị bỏ qua; dễ che giấu trạng thái thực chưa đúng |

Nếu changeset tạo index lỗi và chỉ còn một index invalid cùng tên, cấu hình precondition kiểu “indexExists thì MARK_RAN” là đặc biệt nguy hiểm. Liquibase có thể ghi nhận lịch sử hoàn tất trong khi index vẫn invalid.

**onFail** xử lý điều kiện trả kết quả không đạt. **onError** xử lý lỗi khi đánh giá điều kiện. Với migration nhạy cảm, nên có chính sách onError: HALT để không biến lỗi quyền truy cập hoặc lỗi truy vấn metadata thành quyết định bỏ qua.

Các hành vi CONTINUE và MARK_RAN chỉ dùng được ở **changeset-level preconditions**, không dùng ở cấp global/changelog. HALT và WARN có phạm vi rộng hơn. Bất kể lựa chọn nào, precondition không tự xử lý dữ liệu đã có hiệu lực ngoài transaction.

## 16. runOnChange, runAlways và failOnError có giúp không?

Ba cơ chế này thường bị hiểu nhầm thành “giải pháp retry”.

- **runOnChange:** cho phép một số changeset được chạy lại khi nội dung có thay đổi theo cơ chế Liquibase. Nó không phải cách sửa một changeset ngoài transaction đã áp dụng dở dang, vì việc sửa lịch sử có thể khiến SQL chạy trong trạng thái khó dự đoán.
- **runAlways:** cho phép changeset chạy ở mỗi lần update phù hợp. Với thao tác không có giao dịch, khả năng chạy lại phải được thiết kế và kiểm chứng rõ; không nên dùng cho CREATE TABLE hoặc DML không idempotent.
- **failOnError:** thay đổi cách Liquibase phản ứng với lỗi thực thi changeset. Dùng failOnError=false để tránh pipeline thất bại có thể che giấu tình trạng database dở dang; không biến những thao tác đã xảy ra thành nguyên tử.

Nếu đã có một changeset chạy lỗi trên production, phương án đầu tiên là **xác định trạng thái thực tế**, không phải bật một cờ để thử lại cho nhanh.

## 17. Trường hợp có nhiều lệnh SQL: nên tách thế nào?

Giả sử release cần thực hiện:

1. Thêm cột mới.
2. Backfill cột từ dữ liệu hiện có.
3. Tạo index concurrently.
4. Thêm constraint hoặc bật tính năng mới của ứng dụng.

Cách bố trí hợp lý thường là **mỗi mục tiêu một changeset**, với ranh giới transaction phù hợp:

~~~mermaid
flowchart TD
    A["Changeset A: thêm cột (mặc định transaction)"] --> B["Changeset B: backfill có kiểm chứng"]
    B --> C["Đối soát số bản ghi và giá trị"]
    C --> D["Changeset C: CREATE INDEX CONCURRENTLY (false)"]
    D --> E["Kiểm tra index hợp lệ"]
    E --> F["Changeset D: constraint hoặc bước contract"]
    F --> G["Bật tính năng ở ứng dụng"]
~~~

Ưu điểm:

- Nếu index lỗi, có thể xác định rõ index là thao tác dở dang mà không phải điều tra một loạt DML trong cùng changeset.
- Nếu backfill chưa xong, không nhất thiết phải rollback cấu trúc cột mới.
- CI/CD có thể dừng trước khi bật tính năng nếu hậu kiểm chưa đạt.
- Mỗi bước có owner, log và kế hoạch phục hồi riêng.

Nhưng **tách changeset không tạo atomicity xuyên changeset**. Khi A và B đã commit, C lỗi, release vẫn có thể ở trạng thái nâng cấp một phần. Vì vậy phải thiết kế tương thích ứng dụng và điều kiện nghiệm thu phù hợp.

## 18. Backfill lớn: transaction ngắn và checkpoint

Với hàng triệu bản ghi, backfill thường là một trong những nơi dễ tạo trạng thái dở dang nhất. Một UPDATE duy nhất trong transaction dài có thể gây khóa và tăng tải; chạy ngoài transaction mà không có checkpoint lại dễ bỏ sót dữ liệu khi tiến trình lỗi.

Một job backfill có kiểm soát cần:

- **Phạm vi theo lô** dựa trên ID hoặc điều kiện ổn định.
- **Checkpoint rõ ràng**, ghi nhận mốc và số bản ghi xử lý.
- **Idempotency**, bảo đảm lô được chạy lại không gây cập nhật lặp sai.
- **Không ghi đè bản ghi mới**, xem xét version/timestamp hoặc điều kiện về trạng thái cũ.
- **Giới hạn tải**, độ song song và khả năng tạm dừng.
- **Hậu kiểm**, so sánh số hàng nguồn, số hàng đã chuyển, số lỗi và số chưa chuyển.
- **Quy trình điều tra ngoại lệ**, không tự ép mọi giá trị lạ về một default.

Đối với backfill lớn phải xử lý dần trong lúc ứng dụng đang hoạt động, một job có checkpoint và điều phối riêng có thể phù hợp hơn một changeset dài. Liquibase vẫn quản lý schema và những mốc chuyển trạng thái cần thiết.

Không coi DATABASECHANGELOG là hệ thống checkpoint chi tiết cho từng lô xử lý dữ liệu nghiệp vụ: nó theo dõi changeset, không thay thế nhật ký tiến độ của một job ETL.

## 19. Tính tương thích ứng dụng và mô hình expand–migrate–contract

Dù Liquibase được chạy hoàn hảo, deployment vẫn có thể lỗi nếu ứng dụng mới hoặc cũ không tương thích với trạng thái schema ở giữa các bước.

Một kế hoạch thường an toàn:

### Expand

- Thêm cột hoặc bảng mới theo hướng tương thích với ứng dụng cũ.
- Không xóa cột cũ ngay.
- Nếu có index ngoài transaction, tạo riêng và kiểm chứng trước khi phụ thuộc vào nó.

### Migrate

- Di chuyển dữ liệu theo quy tắc và checkpoint.
- Cho phép ứng dụng đọc/ghi theo cơ chế đồng bộ đã thiết kế, tránh bỏ sót bản ghi phát sinh trong quá trình migration.
- Đối soát và xử lý ngoại lệ.

### Contract

- Chỉ siết NOT NULL/FK hoặc bỏ cột cũ khi dữ liệu và ứng dụng đã sẵn sàng.
- Tạo changeset mới và review SQL riêng.
- Chuẩn bị forward fix nếu một bước không thể rollback an toàn.

Với **rolling deployment**, có thể tồn tại đồng thời nhiều phiên bản ứng dụng. Vì vậy, cần xác định trạng thái trung gian nào **được phép tồn tại tạm thời** và trạng thái nào bắt buộc pipeline phải HALT.

## 20. Quy trình kiểm chứng trước khi chạy production

Trong CI/CD, nên có ít nhất ba lớp kiểm tra.

### 20.1. Kiểm tra changelog và SQL

Các lệnh Liquibase điển hình khi đã cấu hình connection và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **validate** giúp phát hiện những vấn đề Liquibase có thể kiểm tra trước thực thi.
- **status** cho biết những changeset được xem là đang chờ.
- **update-sql** hỗ trợ review SQL dự kiến; không mô phỏng đầy đủ tình huống deadlock, timeout, mất kết nối hoặc trạng thái dở dang.

Từ changelog, xác định rõ changeset nào đặt runInTransaction=false, lý do kỹ thuật và SQL thực tế của nó.

### 20.2. Kiểm thử hai đường đi

1. **Database mới:** chạy toàn bộ changelog để kiểm tra thứ tự và phụ thuộc từ đầu.
2. **Database có lịch sử:** nâng cấp bản sao từ phiên bản cũ, có DATABASECHANGELOG và dữ liệu tương đương.

Với changeset ngoài transaction, cần xem xét thử nghiệm sự cố trong môi trường cô lập: quá trình bị ngắt sau thao tác đầu, timeout trong lúc DDL và thử chạy lại. Chỉ làm thử nghiệm phá hoại trên môi trường được phép kiểm thử, không trên production.

### 20.3. Hậu kiểm thực tế

Sau khi update, đối chiếu:

- DATABASECHANGELOG và changeset mong đợi.
- Schema, kiểu cột, constraint, index và trạng thái hợp lệ.
- Kết quả backfill, số hàng thay đổi và ngoại lệ.
- Khả năng truy vấn/ghi dữ liệu của ứng dụng.
- Tải, thời gian khóa, lỗi kết nối và replication lag nếu có.

Chỉ khi hậu kiểm đạt mới coi đợt migration hoàn tất về mặt vận hành. **Exit code 0 hoặc dòng log “update successful” không thay thế tiêu chí nghiệp vụ và schema thực tế.**

## 21. Spring Boot và CI/CD: tránh retry vô tình

Spring Boot có thể chạy Liquibase lúc khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Trong một cụm nhiều instance, nếu các instance cùng khởi động và đều được cấu hình chạy Liquibase, cơ chế lock Liquibase hỗ trợ điều phối lần update. Tuy nhiên, khi một changeset ngoài transaction lỗi và instance bị restart, Liquibase có thể lại gặp changeset pending trong một trạng thái database đã thay đổi một phần.

Vì vậy, cần lựa chọn có chủ đích:

- Cho ứng dụng tự chạy Liquibase khi hệ thống đơn giản và những changeset an toàn, thời gian chạy có thể dự đoán.
- Dùng **job migration chuyên trách trong CI/CD** khi thay đổi nhạy cảm cần giám sát, review SQL và kiểm tra hậu triển khai.
- Tách DDL dài hoặc backfill lớn thành quy trình có người/đơn vị chịu trách nhiệm.
- Không cho phép tự động restart liên tục dẫn đến **retry dồn dập** một changeset đang lỗi.
- Phân biệt lỗi startup ứng dụng với lỗi migration và bảo toàn log để điều tra.

Nếu pipeline dùng automation để rollback ứng dụng khi migration thất bại, phải nhớ rằng **rollback ứng dụng không tự rollback database**. Phiên bản ứng dụng cũ phải được thiết kế tương thích với trạng thái schema đã áp dụng một phần.

## 22. Checklist review cho changeset ngoài transaction

| Câu hỏi | Nếu không trả lời được |
|---|---|
| Vì sao cần runInTransaction=false? | Giữ mặc định true và điều tra nhu cầu |
| DBMS/phiên bản có yêu cầu lệnh chạy ngoài transaction không? | Chưa đủ cơ sở thay đổi transaction mode |
| Changeset có một mục tiêu chính, ít SQL và phụ thuộc rõ ràng không? | Nên tách nhỏ |
| Có thể còn đối tượng hoặc dữ liệu dở dang sau lỗi không? | Phải thiết kế kiểm tra và cleanup |
| Precondition có kiểm tra đúng trạng thái, không chỉ tên đối tượng không? | Không dùng MARK_RAN tự động |
| Retry có idempotent và an toàn với dữ liệu mới không? | Cấm retry tự động |
| Rollback có khả thi, hay cần forward fix? | Phải xác định trước deployment |
| Có cơ chế phân biệt lỗi precondition với lỗi SQL không? | Bổ sung log và điều kiện dừng |
| DATABASECHANGELOG sẽ phản ánh thế nào khi lỗi? | Tăng kiểm chứng lịch sử và catalog |
| Có khả năng quan sát DDL dài, lock và tiến trình khác không? | Chưa sẵn sàng chạy production |
| Có thử nghiệm trên database có lịch sử thực tế chưa? | Không coi test database mới là đủ |
| Ứng dụng cũ/mới có tương thích với trạng thái trung gian không? | Cần thiết kế expand–migrate–contract |

## 23. Tình huống thực hành

### Đề bài

Hệ thống thương mại điện tử dùng PostgreSQL. Bảng purchase_order có nhiều triệu hàng, các dịch vụ vẫn ghi liên tục. Release mới cần tạo index trên created_at bằng CREATE INDEX CONCURRENTLY. Liquibase dùng một changeset runInTransaction=false. Sau khi chạy được một lúc, pipeline bị ngắt và restart. Trong catalog xuất hiện index cùng tên, nhưng Liquibase status vẫn cho rằng changeset chưa hoàn tất.

### Câu hỏi

1. Có thể khẳng định changeset chưa tác động database vì không có row DATABASECHANGELOG không?
2. Có nên bật MARK_RAN khi indexExists trả TRUE không?
3. DATABASECHANGELOGLOCK có giải quyết được index invalid không?
4. Có nên lập tức chạy lại update không?
5. Cần kiểm tra những gì trước khi cleanup hoặc retry?
6. Nếu index valid và đúng định nghĩa nhưng lịch sử thiếu, có nên tự chèn row DATABASECHANGELOG?
7. Nên thay đổi thiết kế changeset hoặc pipeline ra sao để giảm rủi ro tái diễn?

### Hướng giải

1. **Không.** SQL có thể đã có hiệu lực một phần hoặc để lại đối tượng dù changeset chưa được ghi nhận.
2. **Không.** Index cùng tên có thể invalid hoặc có định nghĩa không đúng; cần xác minh trạng thái bằng catalog và log.
3. **Không.** Lock Liquibase điều phối các lần chạy; nó không làm index invalid trở thành valid.
4. **Không nên.** Trước hết phải dừng retry tự động, kiểm tra tiến trình, đối tượng và lịch sử.
5. Kiểm tra phiên chạy Liquibase còn hoạt động, index indisvalid/indisready, định nghĩa index, lock, số lần thử và lỗi thực tế.
6. **Không tự chèn.** Đây là vấn đề đồng bộ lịch sử phải có quy trình quản trị và bằng chứng tương đương đầy đủ; lựa chọn cụ thể phụ thuộc trạng thái database và chính sách vận hành.
7. Giữ một thao tác chính trong changeset false; bổ sung kiểm tra hậu triển khai, alert, cơ chế dừng tự động khi thất bại và runbook phục hồi index invalid.

### Bài tập mở rộng

Một changeset runInTransaction=false chạy hai câu SQL: UPDATE dữ liệu khách hàng và INSERT bản ghi audit. UPDATE thành công, INSERT thất bại. Hãy chỉ ra vì sao việc sửa lỗi bằng cách tạo bảng audit rồi **chạy lại nguyên changeset** chưa chắc an toàn, kể cả khi lần thứ hai trả success.

Gợi ý: kiểm tra logic UPDATE có idempotent không; số hàng đã sửa trước đó; dữ liệu mới xuất hiện trong lúc lỗi; quy tắc audit cần phản ánh một hay hai lần thực thi; và liệu DATABASECHANGELOG tương ứng với kết quả nghiệp vụ cuối cùng chưa.

## 24. Những sai lầm phổ biến cần tránh

| Sai lầm | Hệ quả | Cách thay thế |
|---|---|---|
| Tin rằng changeset lỗi thì database chắc chắn chưa đổi | Retry gây duplicate hoặc ghi đè dữ liệu | Kiểm tra catalog và dữ liệu thực tế |
| Tắt transaction để “chạy nhanh hơn” | Dễ để lại trạng thái dở dang | Phân tích SQL/lock, giữ true khi có thể |
| Đưa nhiều DDL/DML vào một changeset false | Khó xác định phần đã commit | Tách một thao tác chính mỗi changeset |
| Chỉ xem DATABASECHANGELOG | Bỏ sót đối tượng/data đã tạo | Đối chiếu lịch sử với schema/dữ liệu |
| Dùng MARK_RAN khi đối tượng cùng tên tồn tại | Che giấu index invalid hoặc constraint sai | HALT và xác minh tương đương |
| Tự release DATABASECHANGELOGLOCK ngay khi thấy lỗi | Có thể chồng lấn với migration còn chạy | Kiểm tra session, DDL và tiến trình trước |
| Cho CI/CD retry vô hạn | Có thể lặp side effect | Dừng, điều tra và thiết kế retry an toàn |
| Coi rollback block sẽ tự chạy khi SQL lỗi | Phần đã áp dụng không được dọn như dự tính | Runbook cleanup/forward fix riêng |
| Dùng clear-checksums để bỏ qua mismatch | Che giấu việc sửa lịch sử | Bảo toàn changeset, tạo migration mới |
| Chỉ kiểm tra startup thành công | Bỏ sót drift và dữ liệu nghiệp vụ sai | Kiểm chứng DATABASECHANGELOG, catalog, data |
| Bỏ qua ứng dụng đang ghi đồng thời | Có thể mất/ghi đè dữ liệu mới | Expand–migrate–contract và checkpoint |

## 25. Ghi nhớ

**runInTransaction=false** có thể là yêu cầu bắt buộc với một số SQL như PostgreSQL CREATE INDEX CONCURRENTLY, nhưng nó cũng làm mất kỳ vọng về một transaction do Liquibase quản lý bao trọn các thao tác của changeset. Một hoặc nhiều thao tác có thể đã có hiệu lực trước khi changeset thất bại, khiến **database thực tế và DATABASECHANGELOG không nhất quán**.

Ba nguyên tắc cốt lõi:

1. **Thu hẹp ranh giới thay đổi:** một mục tiêu chính trong changeset ngoài transaction; hạn chế nhiều câu lệnh phụ thuộc.
2. **Đối chiếu trạng thái thật:** sau lỗi, dừng retry, kiểm tra SQL đã có hiệu lực, đối tượng, dữ liệu, tiến trình và lịch sử; không coi tên đối tượng hay exit code là đủ.
3. **Chuẩn bị khôi phục:** thiết kế precondition bảo thủ, hậu kiểm, cleanup hoặc forward fix có kiểm soát, cùng kế hoạch tương thích ứng dụng.

Quản lý migration an toàn bằng Liquibase không chỉ là đưa SQL qua changelog, mà còn là kiểm soát những trạng thái trung gian có thể tồn tại và bảo đảm mỗi lần triển khai có thể được kiểm tra, giải thích và phục hồi một cách có trách nhiệm.
