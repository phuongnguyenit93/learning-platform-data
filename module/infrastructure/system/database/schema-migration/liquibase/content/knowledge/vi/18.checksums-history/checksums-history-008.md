# Changelog-sync và việc ghi nhận thay đổi mà không thực thi DDL

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Checksum và lịch sử** này tập trung vào lệnh **changelog-sync**: cách Liquibase ghi nhận một tập changeset là đã được xử lý trong lịch sử database **mà không thực thi nội dung thay đổi của chúng**.

Changelog-sync thường xuất hiện khi một nhóm tiếp quản database đã có schema, khi chuyển từ SQL thủ công hoặc một công cụ migration khác sang Liquibase, hoặc khi cần thiết lập baseline cho một môi trường đã được tạo sẵn. Đây là thao tác quản lý lịch sử rất hữu ích, nhưng cũng có rủi ro lớn: nếu database thực tế chưa đạt trạng thái mà changelog mô tả, Liquibase vẫn có thể đánh dấu changeset là đã chạy. Những lần update sau đó có thể bỏ qua DDL còn thiếu và làm lịch sử không phản ánh đúng cấu trúc database.

Mục tiêu của bài là hiểu chính xác changelog-sync làm gì, phân biệt nó với update và MARK_RAN, xây dựng baseline có bằng chứng, kiểm tra DATABASECHANGELOG/checksum, giới hạn changeset được đồng bộ và tích hợp an toàn vào CI/CD.

## 1. Changelog-sync là gì?

Lệnh **changelog-sync** yêu cầu Liquibase ghi nhận các changeset chưa được đánh dấu là đã chạy trong database như đã được xử lý. Điểm quan trọng là Liquibase **không thực thi các change bên trong changeset** như lệnh **update**.

Ví dụ changelog có ba changeset:

~~~text
001-create-customer
    changes: CREATE TABLE customer ...
002-add-customer-status
    changes: ALTER TABLE customer ADD status ...
003-create-customer-index
    changes: CREATE INDEX ...
~~~

Nếu database đã được tạo thủ công và schema thực tế đã có đủ bảng, cột và index đúng như ba changeset mô tả, chạy changelog-sync có thể ghi nhận ba changeset trong lịch sử Liquibase mà không chạy lại các câu CREATE/ALTER.

Có thể hình dung:

~~~text
Trước changelog-sync:
  Schema thực tế: customer + status + index đã tồn tại
  DATABASECHANGELOG: chưa có lịch sử tương ứng

Chạy changelog-sync:
  Không chạy CREATE TABLE / ALTER TABLE / CREATE INDEX
  Ghi nhận changeset trong DATABASECHANGELOG

Sau changelog-sync:
  Schema thực tế: giữ nguyên
  DATABASECHANGELOG: thể hiện changeset đã được đánh dấu xử lý
~~~

**Changelog-sync không phải lệnh xác minh schema.** Nó không chứng minh rằng database đã có đúng cột, kiểu dữ liệu, constraint, index, default, quyền hoặc dữ liệu mà changeset dự định tạo. Người vận hành phải kiểm tra trạng thái thật trước khi đồng bộ lịch sử.

Changelog-sync cũng không phải backup, snapshot, rollback hay cách sửa database drift. Nó là một thao tác **ghi nhận trạng thái trong metadata Liquibase**.

## 2. Phân biệt update, changelog-sync và MARK_RAN

Ba cơ chế này có mục đích khác nhau:

| Cơ chế | Điều xảy ra với changeset | Có thực thi phần changes? | Lịch sử |
|---|---|---|---|
| **update** | Chạy changeset chưa được ghi nhận, nếu được chọn và đủ điều kiện | Có | Ghi nhận sau khi thực thi thành công |
| **changelog-sync** | Đánh dấu các changeset chưa được ghi nhận trong phạm vi lệnh là đã xử lý | Không | Ghi nhận các changeset trong DATABASECHANGELOG |
| **onFail: MARK_RAN** | Khi precondition của một changeset thất bại theo cấu hình, bỏ qua changes và đánh dấu changeset đã xử lý | Không chạy changes của changeset đó | Ghi nhận trạng thái MARK_RAN theo cơ chế Liquibase |

Ví dụ:

- **update**: database chưa có bảng customer; Liquibase chạy CREATE TABLE.
- **changelog-sync**: bảng customer đã có và đã được xác minh đúng; Liquibase chỉ ghi nhận changeset tạo bảng.
- **MARK_RAN**: một changeset được đánh giá qua precondition; nếu điều kiện không đạt và onFail được đặt MARK_RAN, Liquibase bỏ qua changeset rồi ghi nhận nó theo trạng thái tương ứng.

Không dùng ba cơ chế thay thế nhau chỉ vì muốn lệnh triển khai không báo lỗi. Chọn sai sẽ làm mất khả năng tin cậy của lịch sử.

### Changelog-sync khác mark-next-changeset-ran

Một số phiên bản Liquibase có lệnh **mark-next-changeset-ran** để đánh dấu changeset kế tiếp trong thứ tự changelog là đã chạy. Nó có phạm vi hẹp hơn changelog-sync, hữu ích trong tình huống có kiểm soát khi chỉ một changeset cần được ghi nhận. Nó không có nghĩa là đã kiểm tra toàn bộ schema.

Hãy kiểm tra lệnh và options theo phiên bản Liquibase CLI đang dùng; không dùng lệnh đánh dấu một changeset để thay thế kế hoạch baseline cho cả database.

## 3. Khi nào nên dùng changelog-sync?

Changelog-sync phù hợp nhất khi **database thực tế đã ở trạng thái tương ứng với changelog nhưng lịch sử Liquibase chưa được thiết lập hoặc chưa phản ánh đầy đủ trạng thái đó**.

Một số tình huống:

1. **Tiếp quản database cũ:** schema được tạo từ lâu bằng SQL thủ công, ứng dụng đang chạy ổn định, nhóm muốn đưa các thay đổi tương lai vào Liquibase.
2. **Chuyển công cụ migration:** trước đây dùng Flyway hoặc quy trình DBA riêng; cần xây dựng baseline Liquibase sau khi đã đối chiếu trạng thái hiện tại.
3. **Khởi tạo lịch sử cho môi trường được provision sẵn:** database staging hoặc production được tạo từ snapshot đã kiểm tra, cần đánh dấu các migration nền đã được áp dụng.
4. **Đồng bộ một phạm vi changeset có kiểm soát:** database đã thực hiện các thay đổi bằng một quy trình ngoài Liquibase và có bằng chứng tương đương với changelog.
5. **Thiết lập baseline cho nhiều môi trường:** mỗi môi trường đã được chuẩn hóa về cùng trạng thái schema, nhưng metadata Liquibase chưa có cùng lịch sử.

Changelog-sync **không phù hợp** trong những trường hợp sau:

- Database mới, chưa có schema mà changelog yêu cầu.
- Chỉ một số bảng/cột tồn tại, phần còn lại chưa được tạo.
- Không biết chính xác thay đổi thủ công đã được áp dụng đến đâu.
- Database có schema drift, index hoặc constraint sai định nghĩa.
- Muốn bỏ qua migration bị lỗi mà không hiểu nguyên nhân.
- Muốn chữa checksum mismatch hoặc làm sạch DATABASECHANGELOG.
- Muốn tạo bản sao hoặc rollback database.

Nếu database mới hoàn toàn, thông thường dùng **update** để Liquibase tạo schema. Nếu database đã có dữ liệu và schema một phần, phải lập kế hoạch baseline theo trạng thái thực tế; không chạy changelog-sync toàn bộ một cách mặc định.

## 4. Nguyên tắc baseline: changelog phải mô tả trạng thái đã tồn tại

Một baseline đáng tin cậy phải trả lời được: **nếu chạy toàn bộ changeset trước mốc baseline trên một database rỗng, kết quả schema/data có tương đương với database đang tiếp quản hay không?**

Không nhất thiết phải tạo lại database production để kiểm chứng trực tiếp. Có thể dựng database dùng một lần từ changelog nền trên cùng DBMS/version, sau đó đối chiếu với database hiện có qua metadata, snapshot/diff và các truy vấn kiểm tra dữ liệu.

Ví dụ database hiện tại có:

- Bảng customer với id BIGINT PRIMARY KEY.
- Cột email VARCHAR(255) NOT NULL.
- Cột status VARCHAR(30) NULL.
- Index idx_customer_email trên email.
- Foreign key fk_order_customer từ purchase_order.customer_id đến customer.id.

Changelog baseline cần phản ánh đúng các đối tượng và thuộc tính đó. Nếu changelog mô tả status NOT NULL nhưng database thực tế vẫn cho phép NULL, không được đồng bộ changeset này như đã hoàn tất.

**Tên đối tượng giống nhau chưa đủ.** Cần đối chiếu:

- Schema và tên bảng/cột.
- Kiểu dữ liệu, độ dài, precision/scale.
- Nullability và default.
- Primary key, unique, foreign key và hành động ON DELETE/ON UPDATE.
- Index: cột, thứ tự cột, uniqueness, expression, predicate, phương thức và trạng thái hợp lệ.
- View, function, trigger, sequence, quyền và đối tượng phụ thuộc.
- Dữ liệu hiện có và các quy tắc nghiệp vụ mà migration giả định.

Nếu chỉ có một phần thay đổi được áp dụng, hãy tách baseline thành các nhóm có thể xác minh. Đừng đánh dấu changeset chưa thực hiện chỉ vì các changeset trước nó đã chạy.

## 5. Ví dụ changelog baseline

Giả sử database hiện tại đã có bảng customer và index email đúng như mong muốn. Changelog có hai changeset:

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
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(255)
                  constraints:
                    nullable: false
              - column:
                  name: status
                  type: varchar(30)
      rollback:
        - dropTable:
            tableName: customer

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
      rollback:
        - dropIndex:
            tableName: customer
            indexName: idx_customer_email
~~~

Trên database mới, **update** sẽ thực thi hai changeset để tạo bảng và index.

Trên database cũ, nếu đã xác minh bảng, cột, constraint và index tương đương với định nghĩa trên, có thể dùng **changelog-sync** để ghi nhận chúng mà không tạo lại đối tượng. Nếu database chỉ có bảng nhưng thiếu index, đồng bộ cả hai changeset sẽ sai: Liquibase sẽ đánh dấu cả index là đã xử lý, rồi những lần update sau bỏ qua việc tạo index còn thiếu.

Vì vậy, nếu database hiện tại chỉ tương ứng changeset 001, cần đồng bộ riêng phạm vi 001 theo cách được hỗ trợ và giữ changeset 002 pending để **update** thực thi. Có thể tổ chức baseline/changelog theo mốc rõ ràng, dùng bộ lọc phù hợp hoặc tách changelog nền khỏi các thay đổi tiếp theo. Phải thử cách lọc và kết quả thực tế trên phiên bản Liquibase đang dùng trước khi áp dụng production.

## 6. Cách chạy changelog-sync

Với Liquibase CLI, lệnh cơ bản thường là:

~~~shell
liquibase changelog-sync
~~~

Cần có cấu hình changelog, JDBC driver, URL, tài khoản và schema metadata đúng. Một luồng kiểm tra minh họa:

~~~shell
liquibase --version
liquibase validate
liquibase status --verbose
liquibase changelog-sync-sql
~~~

**changelog-sync-sql** (nếu được hỗ trợ ở phiên bản/edition đang dùng) sinh SQL dự kiến để ghi nhận changeset vào metadata; nó hữu ích để review phạm vi và các câu lệnh metadata sẽ thực thi. Nó không phải SQL DDL tạo bảng/index từ nội dung changeset. Hãy kiểm tra cú pháp lệnh và options theo CLI cụ thể bằng `liquibase --help`.

Sau khi review và xác minh database tương đương, mới thực thi:

~~~shell
liquibase changelog-sync
liquibase status --verbose
~~~

Changelog-sync có thể áp dụng bộ lọc **contexts**, **labels** và các tham số khác tùy phiên bản. Những changeset không được chọn có thể vẫn chưa được ghi nhận. Điều đó có thể là chủ đích hoặc là sai sót cấu hình; cần kiểm tra chính xác tập changeset thuộc phạm vi baseline.

**Không chạy lệnh changelog-sync trên production lần đầu chỉ dựa vào việc nó không thực thi DDL.** Nó vẫn thay đổi lịch sử database và ảnh hưởng mọi lần update sau đó.

## 7. Xác định phạm vi changeset được đồng bộ

Một changelog lớn có thể chứa nhiều giai đoạn:

~~~text
baseline/
  001-create-core-tables
  002-create-core-indexes

release-1/
  010-add-customer-status
  011-backfill-customer-status

release-2/
  020-add-customer-status-not-null
  021-create-report-view
~~~

Giả sử database cũ đã có các bảng core, nhưng chưa có status. Mục tiêu là ghi nhận nhóm baseline, để update sau đó tiếp tục từ release-1.

Không được đồng bộ toàn bộ changelog vì khi đó 010, 011, 020 và 021 cũng có thể bị ghi nhận đã chạy dù chưa thực hiện. Cần chọn một chiến lược phạm vi rõ ràng:

- Dùng **contexts/labels** đã được thiết kế từ trước để xác định nhóm baseline.
- Tách changelog baseline và changelog thay đổi tiếp theo bằng include có chủ đích.
- Dùng một lệnh đồng bộ phạm vi hẹp được Liquibase phiên bản đang dùng hỗ trợ.
- Với tình huống chỉ một changeset cần ghi nhận, cân nhắc lệnh đánh dấu changeset kế tiếp đã chạy hoặc cơ chế tương ứng, sau khi đã xác minh chính xác thứ tự.

Bộ lọc phải được dùng nhất quán giữa các lệnh preview và changelog-sync. Không giả định rằng một label/context có nghĩa giống nhau nếu pipeline truyền giá trị khác hoặc changelog có logic filter khác.

### Cẩn thận với includeAll

Nếu changelog master sử dụng **includeAll**, thư mục được quét có thể chứa nhiều file hơn dự kiến. Thêm một file baseline hoặc file tạm có thể làm thay đổi tập changeset được nạp. Trước khi sync, hãy xác định đầy đủ thứ tự include và nội dung thực tế của changelog root. Đừng đặt file thử nghiệm trong thư mục includeAll của production.

## 8. Changelog-sync ghi gì vào DATABASECHANGELOG?

Liquibase dùng **DATABASECHANGELOG** làm lịch sử changeset. Khi changelog-sync ghi nhận changeset, bảng metadata sẽ có bản ghi tương ứng với định danh changeset và thông tin triển khai. Tùy phiên bản và kiểu lệnh, các cột metadata được điền theo quy tắc Liquibase; hãy đọc trạng thái thực tế thay vì tự suy đoán từ tên lệnh.

Trên PostgreSQL với metadata nằm trong schema public, có thể kiểm tra:

~~~sql
SELECT
    id,
    author,
    filename,
    dateexecuted,
    orderexecuted,
    exectype,
    md5sum,
    tag,
    deployment_id
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Các trường hữu ích:

- **ID/AUTHOR/FILENAME**: xác định changeset đã được ghi nhận. Đường dẫn file có thể được ảnh hưởng bởi logicalFilePath.
- **DATEEXECUTED/ORDEREXECUTED**: thông tin thời điểm và thứ tự ghi nhận.
- **EXECTYPE**: loại thực thi mà Liquibase ghi nhận. Không nên tự mặc định changelog-sync sẽ luôn cho một giá trị giống MARK_RAN trong mọi phiên bản.
- **MD5SUM**: checksum của định nghĩa changeset theo quy tắc Liquibase.
- **TAG**: nhãn lịch sử nếu có.
- **DEPLOYMENT_ID**: có thể hỗ trợ nhóm các thao tác trong một lần triển khai, tùy phiên bản.

Nếu tên bảng metadata hoặc schema đã được cấu hình khác, hãy truy vấn đúng vị trí. Không chỉnh trực tiếp các dòng trong DATABASECHANGELOG để giả lập kết quả changelog-sync.

**DATABASECHANGELOGLOCK** điều phối các tiến trình Liquibase cùng cập nhật metadata/database. Khi chạy changelog-sync, đây vẫn là một thay đổi lịch sử cần tránh chạy đồng thời với các thao tác Liquibase khác trên cùng database. Không tự giải phóng lock nếu chưa xác nhận tiến trình giữ lock đã dừng.

## 9. Checksum sau changelog-sync có ý nghĩa gì?

Liquibase tính checksum dựa trên nội dung changeset theo quy tắc của phiên bản và change type. Checksum được lưu trong lịch sử để phát hiện một changeset đã ghi nhận bị thay đổi ngoài dự kiến.

Khi changelog-sync ghi nhận một changeset, metadata checksum có thể được lưu cho định nghĩa đang được đồng bộ. Điều này **không có nghĩa Liquibase đã chạy và kiểm chứng nội dung DDL**. Nó chỉ liên kết lịch sử với định nghĩa changeset mà Liquibase đang đọc.

Ví dụ:

- Changelog định nghĩa cột customer.status là VARCHAR(30) NULL.
- Database hiện tại có customer.status là VARCHAR(30) NOT NULL.
- Changelog-sync ghi nhận changeset.
- Lần update tiếp theo, Liquibase có thể bỏ qua changeset vì lịch sử cho biết đã xử lý và checksum hiện tại khớp.
- Nhưng trạng thái thật vẫn NOT NULL, không giống định nghĩa nullable của changelog.

Checksum không phải công cụ diff schema. Một checksum hợp lệ không chứng minh schema đúng; schema giống nhau cũng không chứng minh dữ liệu giống nhau.

Nếu changeset đã được đồng bộ rồi sau đó bị sửa nội dung, Liquibase có thể báo checksum mismatch. Cách xử lý thông thường là giữ nguyên changeset đã ghi nhận và tạo changeset mới mô tả thay đổi tiếp theo. Không dùng **clear-checksums** hoặc **validCheckSum** để che một baseline sai.

## 10. Quy trình baseline cho database đã tồn tại

Một quy trình thực tế có thể gồm tám bước:

1. **Đóng băng phạm vi thay đổi:** xác định database, schema, phiên bản ứng dụng, release/commit và thời điểm chụp trạng thái. Điều phối các writer/DBA để tránh schema thay đổi trong khi kiểm kê.
2. **Kiểm kê schema:** lấy metadata bảng, cột, kiểu, nullability, default, PK, FK, unique, index, view, sequence, function, trigger, quyền và đối tượng đặc thù.
3. **Kiểm tra dữ liệu:** chạy truy vấn xác nhận không có dữ liệu vi phạm giả định của changelog; ghi lại số lượng và quy tắc kiểm tra.
4. **Xây dựng baseline changelog:** mô tả đúng trạng thái đã tồn tại. Không đưa những thay đổi chưa có trong database vào nhóm sẽ được sync.
5. **Dựng database dùng một lần:** chạy changelog baseline bằng update trên database rỗng cùng DBMS/version; so sánh schema kết quả với database cũ.
6. **Review phạm vi sync:** dùng validate/status/changelog-sync-sql và kiểm tra bộ lọc; xác nhận chính xác những changeset sẽ được ghi nhận.
7. **Thực hiện changelog-sync có kiểm soát:** chạy trên database đích với một tiến trình Liquibase duy nhất, theo dõi log và DATABASECHANGELOG.
8. **Postflight và bàn giao:** so sánh lại schema/data, kiểm tra lịch sử, chạy smoke test ứng dụng và xác nhận changeset tiếp theo còn pending đúng như dự kiến.

Nếu database có nhiều schema hoặc nhiều dịch vụ dùng chung, baseline cần được chia theo quyền sở hữu. Không nên để một changelog đánh dấu những đối tượng thuộc dịch vụ khác là đã quản lý nếu nhóm không có quyền và trách nhiệm duy trì chúng.

### Sơ đồ baseline

~~~text
Database hiện hữu
   |
   v
Inventory schema + data
   |
   v
So sánh với baseline changelog
   |
   +---- Không tương đương ----> Sửa baseline hoặc tạo migration chuyển đổi
   |
   v
Dựng DB sạch từ changelog để đối chiếu
   |
   v
Review tập changeset và SQL metadata
   |
   v
changelog-sync (chỉ ghi lịch sử)
   |
   v
Postflight: schema + data + DATABASECHANGELOG
   |
   v
Cho phép Liquibase update tiếp từ changeset kế tiếp
~~~

## 11. Trường hợp database chỉ tương đương một phần

Không phải database cũ nào cũng ở cùng một mốc. Ví dụ:

| Đối tượng | Database hiện hữu | Baseline changelog | Quyết định |
|---|---|---|---|
| customer table | Đúng cột và PK | Khớp | Có thể ghi nhận sau kiểm tra |
| customer.status | Chưa tồn tại | Changelog mô tả đã có | Không sync changeset tạo cột |
| idx_customer_email | Tồn tại nhưng không UNIQUE | Changelog yêu cầu UNIQUE | Không sync changeset tạo unique index |
| fk_order_customer | Tồn tại nhưng ON DELETE khác | Changelog yêu cầu CASCADE | Không sync changeset tạo FK |
| customer.created_at default | Khác biểu thức | Changelog có default khác | Cần migration điều chỉnh hoặc sửa baseline trước |

Trong tình huống này, cần chia lịch sử thành phần đã có và phần còn thiếu, hoặc viết một migration chuyển đổi đưa database đến trạng thái baseline thống nhất. Sau đó mới đồng bộ các changeset tương ứng.

**Không dùng precondition kiểu tableExists/columnExists để suy ra toàn bộ changeset đã được thực hiện.** Kiểm tra tồn tại không xác nhận định nghĩa, constraint, index, dữ liệu hoặc hành vi. Nếu cần đánh dấu một changeset đã được thực hiện, phải có bằng chứng trạng thái tương đương với kết quả mà changeset định tạo.

## 12. Context, label và khác biệt môi trường

Liquibase có thể chọn changeset theo **contexts** hoặc **labels**. Khi dùng changelog-sync, tập changeset được xét cũng có thể bị giới hạn bởi bộ lọc được truyền vào. Vì vậy, baseline phải nêu rõ bộ lọc được dùng và ý nghĩa của chúng.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-shared-tables
      author: database-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false

  - changeSet:
      id: 002-load-demo-data
      author: database-team
      context: dev
      changes:
        - loadData:
            tableName: customer_demo
            file: data/customer-demo.csv
            separator: ","
~~~

Nếu môi trường production không chọn context dev, changeset demo có thể không thuộc phạm vi update/sync của production. Không được dùng kết quả status hoặc changelog-sync trên dev để kết luận production có cùng lịch sử.

Một số quy tắc:

- Ghi rõ context/label filter của từng môi trường trong pipeline.
- Không để changeset baseline quan trọng bị gắn context chỉ có một môi trường chọn.
- Kiểm tra changeset còn pending sau sync, đảm bảo đó là những thay đổi thực sự chưa áp dụng.
- Không sync các changeset data/demo hoặc test fixture lên production chỉ vì chúng nằm trong cùng master changelog.
- Dùng cùng commit changelog khi promote; không sửa file baseline riêng cho từng môi trường.

## 13. Changelog-sync không sửa schema: vậy rollback có tác dụng gì?

Vì changelog-sync chỉ ghi lịch sử mà không chạy nội dung changes, cần phân biệt **rollback các changeset đã thực thi thật** với **rollback các changeset chỉ được đánh dấu qua sync**.

Nếu một changeset tạo bảng được changelog-sync ghi nhận trên database đã có bảng, rồi sau đó rollback tới mốc trước changeset, Liquibase có thể chạy rollback định nghĩa của changeset (ví dụ DROP TABLE) và xóa bảng đang chứa dữ liệu thật. Điều này đặc biệt nguy hiểm: database chưa từng được Liquibase tạo bảng nhưng rollback vẫn có thể thực thi câu lệnh đảo ngược của changeset đã được đánh dấu.

Vì vậy, **baseline qua changelog-sync làm cho rollback về trước baseline trở thành một thao tác có rủi ro rất cao**. Cần thiết kế rõ ranh giới baseline, tag, rollback policy và dữ liệu được giữ lại.

Một chiến lược thường an toàn hơn:

- Xác định baseline là **điểm bắt đầu quản lý** của Liquibase.
- Đặt tag/mốc release sau baseline theo cách đã kiểm chứng.
- Chỉ rollback các changeset mới phát sinh sau baseline, với rollback được review.
- Không rollback ngược qua những changeset baseline tạo đối tượng cốt lõi, trừ khi đã có kế hoạch backup/restore và xác minh tác động.
- Nếu cần sửa trạng thái baseline, dùng changeset forward-fix thay vì xóa các đối tượng nền chỉ vì lịch sử có thể rollback chúng.

Tag chỉ giúp xác định ranh giới; nó không tự chặn rollback vượt qua baseline. Pipeline hoặc runbook phải giới hạn phạm vi thao tác.

## 14. So sánh với các cơ chế khác

| Cơ chế | Mục đích | Thay đổi schema/data? | Ghi lịch sử? |
|---|---|---|---|
| **update** | Thực thi changeset chưa chạy | Có, theo changes | Có |
| **changelog-sync** | Baseline, ghi nhận changeset chưa chạy | Không chạy changes | Có |
| **changelog-sync-sql** | Xem SQL metadata dự kiến cho thao tác sync | Không thực thi | Không, chỉ preview |
| **mark-next-changeset-ran** | Đánh dấu một changeset kế tiếp là đã chạy | Không chạy changeset đó | Có |
| **onFail: MARK_RAN** | Xử lý precondition fail tại changeset | Không chạy changes của changeset đó | Có |
| **clear-checksums** | Xóa checksum đã lưu để Liquibase tính lại khi cần | Không | Thay đổi metadata checksum |
| **changelog-sync sau baseline sai** | Che khoảng trống giữa changelog và schema | Không sửa schema thiếu/sai | Có, nhưng làm lịch sử sai lệch |

Bảng này cho thấy **changelog-sync không phải công cụ sửa schema**. Nó chỉ phù hợp khi trạng thái database đã tương ứng với thay đổi mà lịch sử sắp ghi nhận.

## 15. Kiểm chứng sau changelog-sync

Sau khi sync, không dừng ở việc thấy lệnh CLI trả mã thành công. Hãy xác minh ba lớp:

### A. Lịch sử

- Changeset thuộc phạm vi baseline xuất hiện trong DATABASECHANGELOG.
- id, author, filename/logical path đúng.
- Checksum và kiểu thực thi được ghi nhận theo hành vi phiên bản.
- Changeset nằm ngoài phạm vi baseline vẫn pending như dự kiến.
- Không có changeset bất ngờ được ghi nhận do filter/includeAll sai.

### B. Schema và dữ liệu

- Bảng/cột/constraint/index/view/sequence có định nghĩa tương đương changelog.
- Dữ liệu thỏa các điều kiện nghiệp vụ và constraint.
- Quyền và default/trigger/function có hiệu lực đúng.
- Các đối tượng không bị thay đổi bởi thao tác sync.

Có thể dùng truy vấn metadata DBMS, SQL assertions và công cụ diff/snapshot phù hợp. Kết quả diff cần được review, đặc biệt khi DBMS chuẩn hóa metadata khác nhau.

### C. Ứng dụng

- Spring Boot/Hibernate khởi động và mapping validate thành công.
- Role runtime có quyền cần thiết.
- Luồng đọc/ghi trọng yếu hoạt động với dữ liệu hiện tại.
- Các bản ghi lịch sử và log có thể truy vết về release baseline.
- Changeset tiếp theo chạy bằng update tạo ra trạng thái mong muốn mà không đụng lại các đối tượng baseline.

Một database có lịch sử đầy đủ nhưng schema thiếu index vẫn là baseline không đạt. Một database schema khớp nhưng tài khoản runtime không có quyền sequence cũng không đạt.

## 16. Quy trình thử nghiệm trên database cô lập

Giả sử cần tiếp quản database customer đã có bảng và index.

**Bước 1 — Tạo database test từ changelog baseline.** Chạy update trên database dùng một lần để tạo trạng thái chuẩn mà changelog mô tả. Lưu metadata schema làm mốc đối chiếu.

**Bước 2 — Tạo database legacy tương đương.** Dùng DDL được kiểm soát để dựng cấu trúc giống database cũ, hoặc dùng snapshot đã ẩn dữ liệu nhạy cảm. Đảm bảo không có Liquibase history nếu mục tiêu là thử baseline.

**Bước 3 — Đối chiếu hai database.** So sánh schema, constraint, index, default, sequence, view và quyền; chạy truy vấn dữ liệu kiểm tra. Sửa khác biệt trước khi sync.

**Bước 4 — Xem phạm vi sync.**

~~~shell
liquibase validate
liquibase status --verbose
liquibase changelog-sync-sql
~~~

Review SQL metadata dự kiến, xác định những changeset sẽ được ghi nhận và bảo đảm không có release migration mới lọt vào baseline.

**Bước 5 — Chạy changelog-sync trên legacy test.**

~~~shell
liquibase changelog-sync
liquibase status --verbose
~~~

Kiểm tra DATABASECHANGELOG. Không được xuất hiện DDL tạo bảng/index từ changeset đã sync.

**Bước 6 — Chạy update tiếp theo.** Thêm một changeset mới vào changelog, chẳng hạn thêm cột status; chạy update và xác minh đúng changeset mới được thực thi. Các changeset baseline đã ghi nhận không được chạy lại.

**Bước 7 — Thử rollback trong test.** Xác định rollback tới mốc sau baseline và đảm bảo không vô tình rollback qua changeset đã ghi nhận bằng sync. Kiểm tra schema/data trước và sau. Không dùng dữ liệu production để thử.

**Bước 8 — Viết runbook.** Ghi rõ phạm vi baseline, release commit, tag, filter, truy vấn kiểm chứng, lệnh sync và điều kiện dừng. Chỉ sau khi thử toàn chu trình mới áp dụng cho môi trường dùng chung.

## 17. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Update sau sync không tạo cột | Changeset tạo cột đã bị sync dù cột thực tế thiếu | Đối chiếu schema; tạo migration forward-fix và sửa chiến lược baseline |
| Index có tên đúng nhưng định nghĩa sai | Sync dựa trên assumption/tồn tại tên | So sánh cột, uniqueness, predicate, method và trạng thái index |
| Changeset mới bị bỏ qua | Context/label hoặc sync đã ghi nhận rộng hơn dự kiến | Kiểm tra filter và DATABASECHANGELOG |
| Checksum mismatch sau baseline | Changelog đã bị sửa hoặc đường dẫn/định nghĩa thay đổi | So sánh commit và lịch sử; tạo changeset mới khi cần |
| Rollback xóa bảng cũ | Changeset tạo bảng được sync rồi rollback qua baseline | Dừng; xác minh tác động, phục hồi backup hoặc forward-fix |
| Một môi trường có lịch sử khác | Sync chạy với filter hoặc changelog khác | Chuẩn hóa commit, filter và kiểm kê từng môi trường |
| DATABASECHANGELOG không như dự kiến | Metadata schema khác, lệnh chạy vào database sai hoặc version khác | Xác minh target, metadata table/schema và log |
| Pipeline xanh nhưng ứng dụng lỗi | Sync không thực thi DDL, role hoặc mapping chưa được kiểm tra | Bổ sung postflight schema/data/runtime test |

Đừng xử lý các lỗi này bằng cách xóa toàn bộ DATABASECHANGELOG, sửa MD5SUM trực tiếp hoặc chạy changelog-sync thêm lần nữa mà chưa xác định trạng thái thật. Những hành động đó có thể làm mất khả năng truy vết và khiến changeset chưa thực thi bị đánh dấu hoàn tất.

## 18. Tích hợp changelog-sync vào CI/CD

Changelog-sync là thao tác có rủi ro vì nó ghi lịch sử mà không thay đổi schema. Do đó không nên đặt nó vào pipeline triển khai thông thường như một bước mặc định. Hãy dùng một **job baseline riêng**, có quyền và phê duyệt phù hợp:

~~~text
Inventory database hiện hữu
        |
        v
Compare schema/data với baseline changelog
        |
        v
Validate + preview changelog-sync-sql
        |
        v
Review tập changeset sẽ được đánh dấu
        |
        v
Approval baseline
        |
        v
Run changelog-sync
        |
        v
Verify DATABASECHANGELOG
        |
        v
Verify schema + data + application
        |
        v
Ghi nhận baseline release/tag
        |
        v
Cho phép các update tiếp theo
~~~

Các guardrails nên có:

- Chỉ chạy trên database và schema được phê duyệt.
- Chốt changelog commit và Liquibase version.
- Dùng context/label filter được review.
- Không có pipeline Liquibase khác chạy đồng thời.
- Lưu SQL preview, output, log, người phê duyệt và kết quả hậu kiểm.
- Nếu bất kỳ kiểm tra schema/data nào không đạt, dừng và sửa baseline hoặc migration.
- Tách job baseline khỏi job update thường ngày; tránh ai đó vô tình chạy sync trên database mới.

Với Spring Boot, nếu CI/CD chịu trách nhiệm baseline/sync, ứng dụng runtime không nên tự động chạy changelog trên cùng database trong lúc job đang thực hiện. Khi baseline hoàn tất và lịch sử đã xác minh, chuyển quyền sở hữu migration sang mô hình vận hành được chọn và cấu hình `spring.liquibase.enabled` phù hợp.

## 19. Bài tập tình huống

Một công ty có database production đã chạy ba năm. Bảng customer, order và payment đã tồn tại; DBA từng thêm index bằng SQL trực tiếp. Nhóm muốn đưa Liquibase vào quản lý.

**Tình huống A:** database có customer và order đúng cấu trúc, nhưng thiếu index mới mà changelog mô tả. Không sync changeset tạo index; baseline chỉ bao gồm trạng thái đã có. Sau đó update chạy changeset tạo index.

**Tình huống B:** database có index cùng tên nhưng dùng cột khác. Không sync changeset tạo index; phải xác định có cần thay thế index bằng migration riêng hay sửa baseline dựa trên thiết kế được duyệt.

**Tình huống C:** changelog hiện tại gồm cả migration năm đầu và các thay đổi chưa triển khai của release mới. Không changelog-sync toàn bộ; tách baseline/nhóm changeset và xác định filter chính xác.

**Tình huống D:** sau changelog-sync, ứng dụng vẫn lỗi vì role runtime thiếu quyền. Đây không phải lỗi schema history; bổ sung kiểm tra privilege và cấp quyền tối thiểu theo quy trình.

Câu hỏi tự kiểm tra: **Nếu changelog-sync chạy thành công, có thể kết luận database đã đạt schema mà changelog mô tả không?** Không. Lệnh này ghi nhận lịch sử; kết luận đó chỉ được đưa ra sau khi kiểm tra độc lập schema, dữ liệu, quyền và hành vi ứng dụng.

## 20. Checklist trước khi dùng changelog-sync

- [ ] Xác nhận đúng database, schema, DBMS/version, role và changelog root.
- [ ] Chốt commit changelog và phiên bản Liquibase.
- [ ] Kiểm kê schema/data hiện hữu, bao gồm index, constraint, sequence và object phụ thuộc.
- [ ] Chứng minh baseline changelog tương đương với trạng thái database sẽ sync.
- [ ] Xác định changeset nào thuộc baseline, changeset nào còn phải update.
- [ ] Kiểm tra contexts, labels, include/includeAll và thứ tự changeset.
- [ ] Chạy validate, status và changelog-sync-sql nếu phiên bản hỗ trợ; review SQL metadata.
- [ ] Đánh giá rollback qua baseline có thể xóa đối tượng/dữ liệu thật hay không.
- [ ] Có approval và điều phối để không có Liquibase process khác chạy đồng thời.
- [ ] Chạy changelog-sync chỉ trong phạm vi được duyệt.
- [ ] Đọc lại DATABASECHANGELOG và kiểm tra checksum/EXECTYPE theo thực tế.
- [ ] Đối chiếu schema, dữ liệu, quyền và ứng dụng sau sync.
- [ ] Xác nhận changeset tiếp theo còn pending và update thực thi đúng.
- [ ] Lưu log, SQL preview, commit, release ID và bằng chứng baseline.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, hãy xem **changelog-sync** là công cụ thiết lập lịch sử cho database đã được xác minh, không phải công cụ tạo hoặc sửa schema. Chỉ đánh dấu những changeset mà trạng thái database thực sự tương đương với kết quả mong muốn; giữ các thay đổi còn thiếu ở trạng thái pending để update thực thi. Kết hợp kiểm kê schema/data, changelog bất biến, checksum, DATABASECHANGELOG, preview, kiểm tra hậu điều kiện và job CI/CD có phê duyệt sẽ giúp tiếp quản database hiện hữu mà vẫn duy trì được lịch sử migration đáng tin cậy.
