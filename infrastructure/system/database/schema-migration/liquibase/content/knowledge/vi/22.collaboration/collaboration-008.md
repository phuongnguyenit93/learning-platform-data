# Quy trình hotfix và đưa thay đổi trở lại các nhánh liên quan

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Cộng tác** này trình bày quy trình xử lý **hotfix** khi production gặp lỗi, đồng thời đưa cùng thay đổi trở lại các nhánh phát triển và các nhánh release còn được duy trì.

Hotfix thường bắt đầu từ một phiên bản đã phát hành, cần sửa nhanh để giảm tác động đến người dùng. Khi thay đổi liên quan database, nhóm phải phối hợp hai lịch sử: **lịch sử mã nguồn Git** và **lịch sử migration của Liquibase trong từng database**. Một bản sửa được triển khai trực tiếp trên nhánh release nhưng không được backport về nhánh chính có thể khiến lần phát hành tiếp theo thiếu migration hoặc triển khai lại một thay đổi đã có. Ngược lại, đưa cùng một thay đổi vào changelog với định danh khác có thể khiến Liquibase xem đó là changeset mới và thực thi lần nữa.

Mục tiêu của bài là tạo hotfix từ đúng phiên bản đang chạy, viết migration an toàn, kiểm thử và phát hành có kiểm soát, sau đó backport thay đổi sang các nhánh liên quan mà vẫn giữ ổn định định danh changeset, checksum, thứ tự changelog và trạng thái từng môi trường.

## 1. Hotfix là gì và khi nào cần?

**Hotfix** là một thay đổi có phạm vi hẹp, được ưu tiên xử lý để khắc phục sự cố hoặc rủi ro nghiêm trọng trên phiên bản đang vận hành. Ví dụ:

- Một truy vấn production chậm bất thường do thiếu index.
- Một cột mới gây lỗi vì default hoặc nullability không phù hợp.
- Một foreign key có hành vi xóa dây chuyền ngoài ý muốn.
- Một migration trước đó bỏ sót bước backfill, khiến thao tác ghi dữ liệu thất bại.
- Một stored procedure hoặc view có lỗi làm gián đoạn nghiệp vụ.
- Một bản phát hành làm ứng dụng không tương thích với schema hiện tại.

Hotfix thường có ba đặc điểm: **phạm vi nhỏ**, **thời gian phản hồi ngắn**, **rủi ro hồi quy cao nếu không kiểm tra đúng trạng thái production**. “Nhanh” không có nghĩa bỏ qua review hoặc chạy SQL trực tiếp mà không lưu lịch sử.

Với Liquibase, hotfix cần được thể hiện thành changeset có định danh ổn định, có precondition phù hợp, có kế hoạch rollback hoặc forward-fix và được kiểm tra trên database tương thích trước khi triển khai.

### Hotfix ứng dụng và hotfix database

Không phải mọi hotfix ứng dụng đều cần migration. Nếu chỉ sửa logic Java và schema hiện tại đã hỗ trợ, không tạo changeset chỉ để gắn với release. Ngược lại, nếu sửa lỗi đòi hỏi thêm index, cột, constraint hoặc sửa dữ liệu, migration phải được quản lý cùng release.

Cần ghi rõ thay đổi gồm những phần nào:

| Thành phần | Ví dụ | Nơi quản lý |
|---|---|---|
| Code ứng dụng | Sửa truy vấn dùng cột status | Nhánh Git và artifact ứng dụng |
| Schema migration | Tạo index hoặc thêm constraint | Liquibase changelog |
| Data migration | Backfill status cho dữ liệu cũ | Changeset dữ liệu hoặc job được quản lý |
| Cấu hình | Feature flag, timeout, connection pool | Config/secret management |
| Vận hành | Dừng writer, maintenance window | Runbook và pipeline |

Không nên để một thao tác SQL thủ công trở thành “hotfix bí mật” không có commit, không có bằng chứng và không được đưa về changelog.

## 2. Xác định phiên bản production trước khi tạo nhánh hotfix

Điểm bắt đầu phải là **đúng commit hoặc tag Git đang tạo ra phiên bản production bị ảnh hưởng**. Không tạo hotfix từ nhánh main mới nhất nếu main đã chứa những thay đổi chưa được phát hành.

Một mô hình nhánh minh họa:

~~~text
main
  |
  +---- feature A ---- feature B ---- release/2.x
                                      |
                                      +---- release 2.4.0
                                      |
                                      +---- hotfix/2.4.1
                                                |
                                                +---- fix + Liquibase changeset
                                                |
                                                +---- release 2.4.1
                                                         |
                                                         +---- backport -> main
                                                         +---- backport -> release/1.x (nếu còn hỗ trợ)
~~~

Quy trình:

1. Xác định phiên bản ứng dụng và commit đã phát hành.
2. Xác định nhánh release tương ứng hoặc tạo nhánh từ đúng tag/commit production.
3. Kiểm tra changelog trong nhánh đó: master changelog, include, includeAll, logical path và các changeset đã có.
4. Kiểm tra trạng thái database của môi trường bị ảnh hưởng qua DATABASECHANGELOG và schema thực tế.
5. Tạo nhánh hotfix với phạm vi thay đổi tối thiểu.

**Không suy ra database đã chạy tới changeset nào chỉ từ Git tag.** Git tag mô tả mã nguồn/artifact; DATABASECHANGELOG mô tả những changeset Liquibase đã ghi nhận trên một database cụ thể. Hai nguồn phải được đối chiếu.

Nếu production được nâng cấp theo nhiều tenant hoặc nhiều database, kiểm tra từng đơn vị triển khai trong phạm vi sự cố. Một tenant có thể đã nhận migration trong khi tenant khác chưa chạy.

## 3. Đánh giá trạng thái database trước khi sửa

Trước khi viết hotfix, thu thập trạng thái từ database bị ảnh hưởng:

- DBMS và phiên bản server.
- Database, catalog, schema và tài khoản migration.
- Các changeset đã ghi nhận trong DATABASECHANGELOG.
- Checksum, EXECTYPE và thời điểm triển khai của changeset liên quan.
- Cấu trúc bảng/cột/index/constraint hiện tại.
- Dữ liệu liên quan và số lượng bản ghi bị ảnh hưởng.
- Tiến trình migration khác, DATABASECHANGELOGLOCK và writer đang hoạt động.
- Các thay đổi thủ công hoặc hotfix trước đó chưa được đưa vào changelog.

Ví dụ truy vấn lịch sử trên PostgreSQL, giả sử metadata ở schema public:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Để kiểm tra một changeset cụ thể:

~~~sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM public.databasechangelog
WHERE id = '20261119-add-invoice-status-index'
  AND author = 'billing-team';
~~~

Định danh changeset cần xét **id + author + đường dẫn changelog** (bao gồm logical path nếu được cấu hình). Không chỉ tìm theo id vì nhiều file có thể sử dụng id giống nhau.

Lịch sử không đủ để kết luận schema đúng. Nếu DATABASECHANGELOG ghi nhận đã chạy nhưng index bị DBA xóa sau đó, database vẫn thiếu index. Ngược lại, object có thể đã được tạo thủ công nhưng changeset chưa được ghi nhận. Phải kiểm tra metadata DBMS và dữ liệu thực tế.

**Điều kiện dừng:** không xác định được commit production, database đích, trạng thái migration hoặc tác động dữ liệu. Không viết changeset dựa trên giả định schema chưa được xác minh.

## 4. Thiết kế hotfix theo hướng tiến về phía trước

Một hotfix database nên ưu tiên **forward-fix**: tạo thay đổi mới để đưa trạng thái hiện tại về đúng, thay vì sửa changeset cũ đã triển khai.

Ví dụ production thiếu index phục vụ truy vấn invoice theo status. Nếu index chưa tồn tại và dữ liệu/schema đúng, hotfix có thể thêm changeset mới tạo index. Không sửa changeset cũ tạo bảng invoice để chèn thêm index, vì các môi trường đã chạy changeset đó có checksum khác nhau.

Một changeset hotfix cần xác định:

- ID duy nhất, author và file path ổn định.
- Mục đích và đối tượng được thay đổi.
- DBMS hoặc version được hỗ trợ.
- Precondition kiểm tra đúng giả định.
- Thay đổi DDL/DML tối thiểu.
- Rollback có ý nghĩa hoặc ghi rõ giới hạn.
- Hậu điều kiện để xác minh.
- Tương thích với phiên bản ứng dụng cũ và mới.

Không gộp nhiều thay đổi không liên quan vào một hotfix. Mỗi changeset nên có phạm vi đủ nhỏ để review, triển khai và xử lý khi lỗi.

## 5. Ví dụ hotfix tạo index cho PostgreSQL

Giả sử bảng `invoice` có cột `status`, truy vấn production thường lọc theo cột này và nhóm đã xác nhận index chưa tồn tại. Với bảng lớn, PostgreSQL có thể dùng **CREATE INDEX CONCURRENTLY** để giảm mức chặn thao tác ghi so với tạo index thông thường.

Ví dụ changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-create-invoice-status-index
      author: billing-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: invoice
        - columnExists:
            schemaName: public
            tableName: invoice
            columnName: status
        - not:
            - indexExists:
                schemaName: public
                tableName: invoice
                indexName: idx_invoice_status
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_invoice_status
              ON public.invoice (status);
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS public.idx_invoice_status;
~~~

Các quyết định cần review:

- **dbms: postgresql** giới hạn câu lệnh theo hệ quản trị.
- **runInTransaction: false** vì PostgreSQL không cho CREATE INDEX CONCURRENTLY chạy trong transaction block.
- **onFail/onError: HALT** dừng nếu điều kiện sai hoặc không kiểm tra được; không tự đánh dấu đã chạy khi index cùng tên xuất hiện.
- **Một câu SQL trong changeset** giảm nguy cơ một phần thao tác thành công trước khi câu khác lỗi.
- **Rollback** là đề xuất đảo ngược, nhưng DROP INDEX CONCURRENTLY cũng có giới hạn; phải thử trên database tương thích.

Nếu lệnh tạo index concurrent thất bại, PostgreSQL có thể để lại index không hợp lệ. Khi đó `indexExists` chỉ cho biết có object cùng tên, không chứng minh index dùng được. Trước khi retry, kiểm tra metadata:

~~~sql
SELECT
    ns.nspname AS schema_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_class AS idx
JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace
JOIN pg_index AS i ON i.indexrelid = idx.oid
WHERE ns.nspname = 'public'
  AND idx.relname = 'idx_invoice_status';
~~~

Nếu index invalid, cần xác định tiến trình tạo đã kết thúc, xem log và dependency, rồi mới quyết định drop/recreate hoặc một phương án phục hồi khác. Không dùng MARK_RAN chỉ vì tên index tồn tại.

## 6. Không sửa changeset đã triển khai

Một nguyên tắc quan trọng trong cộng tác với Liquibase: **changeset đã triển khai ở bất kỳ môi trường dùng chung nào phải được xem là bất biến**.

Nếu changeset cũ có lỗi:

- Giữ nguyên nội dung lịch sử.
- Tạo changeset mới để sửa trạng thái.
- Ghi rõ vì sao cần sửa và môi trường nào đã chịu tác động.
- Kiểm tra thay đổi mới trên database có trạng thái giống production.
- Đưa thay đổi mới vào mọi nhánh còn được hỗ trợ.

Ví dụ changeset 010 đã thêm cột `invoice.status` với kiểu VARCHAR(20), nhưng yêu cầu mới cần VARCHAR(30). Không sửa 010 thành VARCHAR(30). Tạo changeset 025 để ALTER COLUMN. Database đã chạy 010 sẽ thực hiện 025; database chưa chạy 010 sẽ theo thứ tự 010 rồi 025.

Nếu changeset cũ bị sửa, Liquibase có thể báo **checksum mismatch** ở môi trường đã ghi nhận checksum trước đó. Không dùng `clear-checksums`, `validCheckSum` hoặc sửa trực tiếp MD5SUM để làm pipeline xanh mà chưa có quyết định reconcile được review. Các công cụ đó không tự sửa schema.

## 7. Định danh changeset phải được giữ nguyên khi backport

Liquibase nhận diện changeset thông qua **id**, **author** và **filename/path**; checksum dùng để kiểm tra định nghĩa đã ghi nhận. Vì vậy, khi đưa hotfix từ nhánh release trở lại main hoặc nhánh release khác, phải bảo toàn định danh migration.

Ví dụ changeset hotfix nằm ở:

~~~text
db/changelog/releases/2.x/2026/20261119-create-invoice-status-index.yaml
~~~

Và có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-create-invoice-status-index
      author: billing-team
      changes:
        - createIndex:
            tableName: invoice
            indexName: idx_invoice_status
            columns:
              - column:
                  name: status
~~~

Khi cherry-pick commit chứa file này sang main:

- Giữ nguyên nội dung changeset.
- Giữ nguyên id và author.
- Giữ nguyên đường dẫn/logical path để Liquibase nhận diện cùng một changeset.
- Đảm bảo master changelog của nhánh đích include file đó đúng một lần.
- Không tạo một changeset khác với id mới nhưng cùng DDL chỉ vì đang ở nhánh khác.

Nếu production đã chạy changeset này và main sau đó được triển khai lên cùng database, Liquibase có thể nhận ra changeset đã được ghi nhận và bỏ qua, **nếu định danh id/author/path và checksum tương ứng vẫn khớp**. Đây là cơ sở để cùng một migration được backport mà không chạy DDL lần nữa.

### Vai trò của filename và logicalFilePath

Đường dẫn changelog là một phần của định danh changeset. Di chuyển file từ thư mục này sang thư mục khác có thể khiến Liquibase coi changeset là một định danh khác nếu đường dẫn logic thay đổi.

Liquibase hỗ trợ **logicalFilePath** để giữ định danh logic ổn định trong những trường hợp cần tổ chức lại file, tùy cách khai báo và phiên bản. Hãy quyết định sớm và kiểm thử. Không tự đổi logicalFilePath sau khi migration đã được triển khai mà không có kế hoạch tương thích lịch sử.

Để backport an toàn nhất, thường nên giữ nguyên file path và nội dung migration từ commit hotfix. Nếu nhánh đích có cấu trúc changelog khác, phải review cách include và logical path trước khi merge.

## 8. Quy trình backport bằng Git

Giả sử hotfix được tạo từ nhánh `release/2.x`, đã triển khai thành công cho production. Nhóm cần đưa cùng thay đổi về `main` và `release/1.x` nếu nhánh 1.x còn được hỗ trợ.

Quy trình minh họa:

~~~shell
git switch release/2.x
git switch -c hotfix/2.4.1
# Sửa code và thêm changeset hotfix
git add .
git commit -m "fix: add invoice status index"

# Sau khi kiểm thử và phát hành hotfix:
git switch main
git cherry-pick <hotfix-commit>

# Nếu release/1.x còn được hỗ trợ:
git switch release/1.x
git cherry-pick <hotfix-commit>
~~~

Đây là ví dụ về thao tác Git; tên branch và commit placeholder cần thay bằng giá trị thực tế của dự án. Trước cherry-pick, kiểm tra nhánh đích đã có thay đổi tương đương hay chưa. Nếu có, không áp dụng mù quáng cùng DDL lần nữa.

Sau cherry-pick:

1. Xác nhận file migration có cùng nội dung và đường dẫn.
2. Xác nhận id/author không đổi.
3. Xác nhận master changelog của nhánh đích nạp file đúng một lần.
4. Chạy validate và kiểm tra SQL dự kiến trên database test phù hợp với nhánh.
5. Kiểm tra code tương ứng đã được backport đầy đủ.
6. Xác nhận changeset được ghi nhận hoặc còn pending đúng với trạng thái từng database.
7. Mở PR để review thay đổi nhánh đích và ghi rõ hotfix commit gốc.

Không nhất thiết phải cherry-pick toàn bộ commit nếu commit chứa các thay đổi không liên quan hoặc nhánh đích không tương thích. Khi tách commit, phải bảo đảm file migration giữ nguyên identity và không làm mất phần code cần thiết.

## 9. Đưa hotfix vào master changelog đúng một lần

Một file changeset tồn tại trong repository nhưng không được master changelog nạp thì Liquibase sẽ không thực thi nó qua changelog root đó. Ngược lại, include cùng một file nhiều lần hoặc đồng thời include tường minh và includeAll có thể làm nạp changeset trùng.

Ví dụ master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2.x/2026/20261119-create-invoice-status-index.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2.x/2026/20261120-fix-invoice-query.yaml
      relativeToChangelogFile: true
~~~

Khi backport, nhánh đích có thể có master changelog riêng. Cần đưa include vào đúng vị trí để thứ tự migration phù hợp. Không thêm include thứ hai nếu file đã được nạp qua includeAll.

**Thứ tự changeset quan trọng.** Một hotfix có thể phụ thuộc cột hoặc bảng do changeset trước tạo. Nếu backport vào nhánh cũ chưa có dependency, việc thêm include đơn lẻ sẽ không đủ. Phải backport cả migration prerequisite hoặc thiết kế hotfix tương thích với schema của nhánh đó.

Trước khi merge, review đồ thị phụ thuộc:

~~~text
001-create-invoice
       |
       v
010-add-invoice-status
       |
       v
025-hotfix-invoice-status-index
~~~

Nếu nhánh release cũ chưa có 010, không thể chạy 025 một cách an toàn. Chọn giải pháp tương thích: backport prerequisite, tạo migration riêng phù hợp nhưng không bị chạy lại trên database đã nhận hotfix, hoặc không hỗ trợ nhánh đó nếu không thể bảo đảm an toàn.

## 10. Khi nhánh đích đã có một thay đổi tương đương

Đây là tình huống khó: nhánh main đã có một changeset khác giải quyết cùng vấn đề, nhưng hotfix production đã được triển khai với định danh riêng.

Ví dụ:

- Hotfix production: id `20261119-create-invoice-status-index`, author `billing-team`, file path A.
- Main đã có changeset `030-add-invoice-index`, author `platform-team`, file path B, tạo index tương tự.

Không được đơn giản merge cả hai rồi kỳ vọng Liquibase tự nhận ra chúng tương đương. Với định danh khác nhau, Liquibase có thể xem đó là hai changeset độc lập và cố tạo index lần nữa.

Cần đối chiếu:

1. Hai thay đổi có thực sự cùng cấu trúc, schema, tên và thuộc tính không?
2. Main changeset đã được triển khai ở môi trường nào?
3. Production đã ghi nhận hotfix identity nào?
4. Các môi trường còn lại có thể đang ở trạng thái khác nhau không?
5. Có thể giữ một định danh chung và loại bỏ thay đổi trùng trước khi phát hành không?

Chiến lược thường dễ truy vết nhất là **hợp nhất lịch sử mã nguồn để cùng một changeset identity đại diện cho cùng thay đổi**, khi điều đó tương thích với các môi trường đã triển khai. Nếu không thể, cần một kế hoạch reconcile theo từng trạng thái database và kiểm chứng bằng metadata/precondition đầy đủ.

Không đặt `onFail: MARK_RAN` cho `indexExists` một cách chung chung để né lỗi duplicate. Index cùng tên có thể khác cột, uniqueness, predicate hoặc trạng thái hợp lệ. Nếu cần đánh dấu một thay đổi đã tồn tại do thao tác ngoài Liquibase, phải chứng minh đối tượng hoàn toàn tương đương và ghi nhận quyết định baseline có kiểm soát.

## 11. Backport không có nghĩa sửa nội dung changeset theo nhánh

Một hotfix có thể cần code khác nhau giữa release/2.x và main do API hoặc cấu trúc ứng dụng khác nhau. Tuy nhiên, nếu cùng một database đã nhận một migration, cần giữ migration identity nhất quán.

Phân biệt:

- **Code ứng dụng khác nhau:** có thể cần adapter hoặc cách gọi khác theo phiên bản.
- **Schema migration giống nhau:** giữ cùng changeset identity/nội dung nếu cùng một thay đổi đã được triển khai.
- **Schema migration thực sự khác nhau:** cần định nghĩa riêng có chủ đích, kiểm soát nhánh nào nạp changeset nào và tránh hai định nghĩa cùng được chạy trên một database.
- **DBMS khác nhau:** có thể dùng thuộc tính `dbms`, contexts/labels hoặc changelog phân nhánh đã review; không sửa changeset đã chạy để thích ứng tùy tiện.

Nếu một nhánh cũ không thể dùng migration hotfix do thiếu tính năng DBMS hoặc schema prerequisite, hãy ghi rõ nhánh đó cần một migration tương thích riêng. Khi cùng database có thể được nâng cấp qua nhiều nhánh theo thời gian, cần bảo đảm lịch sử Liquibase vẫn nhận diện đúng các thay đổi đã áp dụng.

## 12. Kiểm tra checksum và lịch sử sau backport

Sau khi backport, chạy validate và kiểm tra lịch sử ở các môi trường có trạng thái khác nhau:

~~~shell
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Với database đã nhận hotfix, changeset có cùng định danh và checksum phải được Liquibase nhận diện là đã chạy. Với database chưa nhận hotfix, changeset phải xuất hiện trong tập pending nếu nhánh/changelog và filter chọn nó.

Đối chiếu DATABASECHANGELOG:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted
FROM public.databasechangelog
WHERE id = '20261119-create-invoice-status-index'
  AND author = 'billing-team';
~~~

Kết quả cần được diễn giải theo từng database:

| Database | Trạng thái mong đợi |
|---|---|
| Production đã nhận hotfix | Có bản ghi đúng identity; checksum tương ứng |
| Staging chưa nhận hotfix | Changeset pending, sẽ được update khi release |
| Database test mới | Changeset chạy từ đầu và tạo đúng index |
| Nhánh cũ thiếu prerequisite | Không được chạy cho đến khi dependency được giải quyết |

Nếu checksum mismatch, so sánh nội dung changeset, file path/logical path và phiên bản Liquibase. Không chỉnh MD5SUM trực tiếp, không dùng clear-checksums để xóa dấu vết và không thêm validCheckSum chỉ để bỏ qua sai khác chưa hiểu.

**Checksum giống nhau không chứng minh schema thật đúng.** Nếu production có người xóa index sau hotfix, DATABASECHANGELOG vẫn có bản ghi; cần kiểm tra metadata index trước khi kết luận.

## 13. Kiểm thử hotfix trên database tương thích production

Trước khi triển khai, kiểm thử theo trạng thái thực tế của nhánh release:

- Dựng database từ đúng changelog của release production.
- Áp dụng các migration đã triển khai đến commit đó.
- Tạo dữ liệu đại diện và workload có liên quan.
- Chạy hotfix update, xem SQL dự kiến và log.
- Xác minh hậu điều kiện schema/dữ liệu.
- Kiểm thử code hotfix với schema sau migration.
- Kiểm thử tương thích ứng dụng cũ nếu rollout theo kiểu rolling.
- Thử rollback hoặc forward-fix trên bản sao nếu rủi ro yêu cầu.

Đối với PostgreSQL index concurrent, ngoài việc index tồn tại, xác minh `pg_index.indisvalid`, định nghĩa cột và query plan nếu hotfix nhằm cải thiện hiệu năng. Đối với thay đổi constraint, kiểm tra dữ liệu hiện tại có đáp ứng và ứng dụng xử lý lỗi đúng.

**Không dùng database trống làm môi trường kiểm thử duy nhất.** Hotfix được áp dụng lên database production đã tích lũy dữ liệu và migration; cần thử trên bản sao hoặc database dựng theo lịch sử release tương ứng.

## 14. Triển khai production và ghi nhận release

Một trình tự phát hành hotfix:

1. Chốt commit/tag production và nhánh hotfix.
2. Xác nhận database/tenant trong phạm vi sự cố.
3. Chạy preflight: target, DBMS, DATABASECHANGELOG, checksum, schema và dữ liệu.
4. Review changelog và SQL dự kiến.
5. Kiểm tra backup/restore hoặc phương án forward-fix phù hợp.
6. Phê duyệt release hotfix.
7. Chạy Liquibase bằng một tiến trình migration được chỉ định.
8. Theo dõi DATABASECHANGELOGLOCK, log, thời gian và lỗi.
9. Chạy postflight schema/data/app smoke tests.
10. Ghi nhận release artifact, commit, changeset identity và kết quả.
11. Chỉ sau khi đạt hậu kiểm mới đánh dấu hotfix hoàn tất.

Với nhiều tenant hoặc nhiều database, trạng thái phải được kiểm tra theo từng đơn vị. Không kết luận release hoàn tất chỉ vì một database canary đã thành công.

Có thể đặt **Git tag** cho hotfix commit và **Liquibase tag** cho trạng thái database đã nghiệm thu. Hai tag có mục đích khác nhau; cần ghi mapping giữa commit/artifact, Liquibase changeset và môi trường. Không dùng Liquibase tag để thay thế Git tag hoặc ngược lại.

## 15. Đưa thay đổi trở lại main và các release branch

Sau khi hotfix đã được kiểm chứng, cần đưa thay đổi trở lại mọi nhánh còn hoạt động để tránh lỗi tái xuất hiện trong lần phát hành tiếp theo.

Một quy trình:

1. Liệt kê các nhánh cần nhận hotfix: main, release đang hỗ trợ, maintenance branch.
2. Kiểm tra mỗi nhánh đã có thay đổi tương đương chưa.
3. Cherry-pick commit hotfix hoặc mở PR backport phù hợp.
4. Giữ nguyên file migration, id, author, nội dung và logical path nếu cùng một changeset.
5. Giải quyết conflict ở master changelog/include mà không đổi định danh migration.
6. Kiểm tra prerequisite và thứ tự changeset của nhánh đích.
7. Chạy validate, status, update-sql và test trên database tương ứng.
8. Review code ứng dụng và migration cùng nhau.
9. Merge sau khi kiểm tra đạt, ghi liên kết tới hotfix gốc và release đã phát hành.
10. Kiểm tra lại các nhánh sau merge để bảo đảm không còn nhánh được hỗ trợ thiếu bản sửa.

Không backport tới nhánh đã hết hỗ trợ nếu chính sách sản phẩm không yêu cầu; nhưng phải ghi rõ phạm vi nhánh và quyết định. Nếu một nhánh không thể nhận hotfix vì schema khác biệt, tạo kế hoạch riêng thay vì cherry-pick cưỡng ép.

## 16. Đồng bộ các nhánh theo thứ tự an toàn

Khi có nhiều release branch, nên duy trì một quy ước rõ ràng, ví dụ:

~~~text
hotfix/2.4.1
   |
   +--> PR -> release/2.x
   |
   +--> backport -> main
   |
   +--> backport -> release/1.x (nếu còn hỗ trợ)
~~~

Một số nhóm chọn hướng khác: hotfix merge vào release branch trước, sau đó merge release branch lên main. Cách nào cũng được nếu giữ được lịch sử và không kéo theo những thay đổi chưa phát hành.

Điều cần tránh:

- Cherry-pick nhiều lần cùng một commit gây duplicate hoặc conflict khó giải thích.
- Merge toàn bộ main mới nhất vào release branch chỉ để lấy một hotfix nhỏ.
- Chép lại SQL bằng tay rồi tạo changeset id mới không cần thiết.
- Đổi đường dẫn changelog khi backport mà không xem filename identity.
- Thêm cùng file qua cả include và includeAll.
- Thay đổi thứ tự include khiến migration phụ thuộc chưa tồn tại.
- Bỏ qua checksum mismatch bằng cách xóa metadata.

Nếu merge commit có cả feature chưa phát hành, dùng cherry-pick commit hotfix nhỏ hoặc PR chỉ chứa phần cần backport. Giữ commit có nội dung tập trung giúp audit và rollback mã nguồn dễ hơn.

## 17. Rollback hotfix hay tạo forward-fix?

Không phải mọi hotfix lỗi đều nên rollback database. Quyết định phụ thuộc vào dữ liệu đã phát sinh và tương thích ứng dụng.

| Tình huống | Hướng xử lý có thể phù hợp |
|---|---|
| Hotfix chỉ thêm index và index có thể drop an toàn | Rollback index hoặc tạo index sửa nếu định nghĩa sai |
| Hotfix thêm cột nullable, chưa có code phụ thuộc | Có thể giữ schema và rollback ứng dụng |
| Hotfix backfill dữ liệu một chiều | Thường cần forward-fix hoặc restore; rollback SQL có thể không khôi phục giá trị cũ |
| Hotfix đổi constraint khiến ứng dụng mới phụ thuộc | Đánh giá tương thích trước khi rollback schema |
| Changeset ngoài transaction thất bại một phần | Reconcile object và DATABASECHANGELOG trước retry |
| Hotfix làm mất dữ liệu | Dừng writer, đánh giá backup/PITR và quy trình phục hồi |

Rollback Liquibase chạy logic đảo ngược của changeset; nó không tự khôi phục dữ liệu đã bị xóa hoặc các side effect bên ngoài database. Một migration đã được backport vào main nhưng chưa deploy vẫn có thể tồn tại trong code; rollback production không có nghĩa xóa migration khỏi các nhánh.

Nếu cần sửa hotfix, ưu tiên một **changeset forward-fix mới**. Không sửa changeset hotfix đã được áp dụng ở production vì điều đó tạo checksum mismatch và làm lịch sử giữa các môi trường không nhất quán.

## 18. Xử lý khi backport conflict

Conflict thường xảy ra ở ba nơi:

1. **Master changelog:** hai nhánh cùng thêm include ở cuối file.
2. **File migration:** hai thay đổi chạm cùng nội dung hoặc cùng tên file.
3. **Code ứng dụng:** hotfix dựa trên API hoặc cấu trúc đã khác ở nhánh đích.

Khi conflict ở master changelog, giữ mỗi include đúng một lần và đặt thứ tự theo dependency. Không giải quyết bằng cách bỏ include hotfix chỉ để merge thành công.

Khi conflict ở migration, ưu tiên giữ nguyên changeset đã triển khai. Nếu thay đổi trên nhánh đích thực sự khác, tạo migration riêng có định danh mới và đánh giá xem database đã nhận hotfix có đi qua nhánh này hay không. Không thay nội dung changeset cũ đã được ghi nhận.

Khi conflict code, có thể cần viết adapter hoặc port logic hotfix sang API cũ. Tách phần code khác nhau khỏi changeset nếu schema effect giống nhau; migration nên được dùng chung khi có thể.

Sau mỗi lần resolve conflict, chạy lại validate và kiểm tra SQL trên database test. Một merge Git không conflict vẫn có thể tạo changelog include sai thứ tự hoặc nạp trùng file.

## 19. Phối hợp với contexts, labels và DBMS

Một hotfix có thể chỉ áp dụng cho PostgreSQL hoặc một nhóm tenant/feature. Khi đó cần dùng filter có chủ đích:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-postgresql-invoice-index
      author: billing-team
      dbms: postgresql
      context: production
      changes:
        - createIndex:
            tableName: invoice
            indexName: idx_invoice_status
            columns:
              - column:
                  name: status
~~~

Ví dụ chỉ minh họa filter; trong thực tế, phải bảo đảm changeset được chọn ở mọi môi trường cần nhận hotfix. Nếu staging không dùng context production, cần có một cách kiểm thử tương đương được thiết kế rõ ràng; không để filter khiến hotfix chỉ chạy ở production mà chưa qua test.

Contexts/labels là cơ chế chọn changeset, không phải cơ chế kiểm tra schema đã tồn tại. Nếu hotfix phụ thuộc DBMS version hoặc feature, hãy kiểm tra version và capability trong preflight, đồng thời thử trên đúng loại database.

Khi backport sang nhánh có DBMS khác, không đổi cùng changeset đã chạy thành SQL khác. Tách migration DBMS-specific và bảo đảm mỗi database chỉ chọn đúng một đường triển khai tương ứng.

## 20. Mẫu runbook hotfix

Một runbook có thể được tổ chức theo cấu trúc:

~~~text
INCIDENT:
  incident_id:
  severity:
  affected_service:
  affected_tenants/environments:

SOURCE:
  production_release:
  production_commit:
  hotfix_branch:
  hotfix_commit:

DATABASE:
  dbms/version:
  database/schema:
  migration_identity:
  current_DATABASECHANGELOG_state:
  current_schema_state:

CHANGE:
  application_fix:
  changelog_file:
  changeset_id:
  author:
  preconditions:
  expected_postconditions:
  rollback_or_forward_fix:

VALIDATION:
  validate:
  update_sql_review:
  test_database_result:
  production_preflight:
  production_postflight:

RELEASE:
  deployment_job:
  start/end:
  result:
  evidence_links:

BACKPORT:
  main:
  active_release_branches:
  equivalent_change_check:
  cherry_pick_or_PR:
  validation_results:

DECISION:
  completed / blocked / follow_up
~~~

Đây là mẫu thông tin để đội vận hành ghi nhận, không phải file bắt buộc trong repository. Không đưa password, token, dữ liệu cá nhân hoặc URL kết nối chứa secret vào runbook.

## 21. Tích hợp CI/CD cho hotfix và backport

Một pipeline phù hợp có thể gồm hai luồng liên kết:

~~~text
Hotfix PR
   |
   v
Validate + unit/integration tests
   |
   v
Build immutable artifact
   |
   v
Test migration trên DB tương thích release
   |
   v
Review update-sql + approval
   |
   v
Deploy hotfix release
   |
   v
Postflight + record release
   |
   v
Backport PRs to main/active release branches
   |
   v
Validate each target branch + DB compatibility tests
   |
   v
Merge and preserve changeset identity
~~~

Các gate quan trọng:

- Chỉ build và triển khai từ commit đã review.
- Changelog artifact phải đúng với code hotfix.
- Validate và update-sql dùng đúng DBMS, version và filter.
- Test database phải đại diện cho trạng thái release bị ảnh hưởng.
- Production update do một job/owner được xác định thực hiện.
- Sau update kiểm tra DATABASECHANGELOG, schema, dữ liệu và ứng dụng.
- Backport phải chạy lại validation trên từng nhánh đích.
- Báo cáo release phải liên kết hotfix commit với các PR backport.

Nếu Spring Boot tự chạy Liquibase khi khởi động, cần xác định rõ có cho ứng dụng sở hữu migration hay dùng job CI/CD riêng. Tránh để job pipeline và nhiều replica cùng chủ động chạy hotfix migration không được điều phối. DATABASECHANGELOGLOCK giúp đồng bộ các tiến trình Liquibase trên cùng metadata database nhưng không thay thế quy trình release lock ở tầng pipeline.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Hotfix chạy production nhưng main không có migration | Quên backport commit/changelog | Mở PR backport ngay sau khi phát hành |
| Main chạy lại DDL trên production | Changeset được tạo lại với id/author/path khác | Bảo toàn identity hoặc reconcile có kiểm soát |
| Checksum mismatch sau cherry-pick | Nội dung changeset đã sửa hoặc file path thay đổi | So sánh commit, khôi phục nội dung đã triển khai, không clear-checksums tùy tiện |
| Changeset không chạy ở nhánh đích | Master changelog thiếu include hoặc filter loại bỏ | Kiểm tra root changelog, contexts/labels và update-sql |
| Migration chạy trước prerequisite | Thứ tự include/backport sai | Bổ sung dependency hoặc thiết kế migration tương thích |
| Index tồn tại nhưng không dùng được | CREATE INDEX CONCURRENTLY thất bại để lại index invalid | Kiểm tra metadata PostgreSQL trước retry |
| Một số tenant đã hotfix, tenant khác chưa | Rollout không đồng nhất | Theo dõi trạng thái từng tenant và reconcile trước retry |
| Rollback làm mất dữ liệu mới | Không đánh giá tác động data migration | Dùng forward-fix hoặc restore có kế hoạch |
| Hai pipeline chạy migration đồng thời | Không điều phối deployment | Một owner migration, theo dõi DATABASECHANGELOGLOCK |
| Hotfix được merge nhưng code thiếu dependency | Chỉ backport migration hoặc chỉ backport code | Review code và schema cùng nhau trên nhánh đích |

## 23. Checklist hoàn tất hotfix và backport

**Trước hotfix:**

- [ ] Xác định đúng production release, commit và nhánh gốc.
- [ ] Kiểm tra DATABASECHANGELOG và schema thực tế của từng database/tenant bị ảnh hưởng.
- [ ] Phân loại thay đổi: code, schema, data, config và vận hành.
- [ ] Tạo changeset mới; không sửa migration đã triển khai.
- [ ] Xác định id/author/file path/logical path ổn định.
- [ ] Có precondition, hậu điều kiện và rollback/forward-fix.
- [ ] Test trên database có trạng thái tương đương production.

**Khi triển khai:**

- [ ] Review update-sql và target identity.
- [ ] Xác nhận quyền, lock, backup/restore và maintenance window.
- [ ] Chạy một tiến trình Liquibase được chỉ định.
- [ ] Theo dõi log, DATABASECHANGELOGLOCK và lỗi partial failure.
- [ ] Postflight kiểm tra changeset, checksum, schema, dữ liệu và ứng dụng.

**Sau triển khai:**

- [ ] Ghi nhận release commit, Liquibase changeset identity và kết quả.
- [ ] Backport commit/PR tới main và mọi release branch còn hỗ trợ.
- [ ] Giữ nguyên nội dung, id, author và path/logical path của cùng migration.
- [ ] Kiểm tra include đúng một lần và đúng thứ tự.
- [ ] Kiểm tra nhánh đích đã có thay đổi tương đương chưa.
- [ ] Chạy validate, update-sql và migration tests trên từng nhánh.
- [ ] Không tạo changeset trùng hoặc sửa checksum để né lịch sử.
- [ ] Ghi rõ nhánh không nhận backport và lý do.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, hotfix chỉ hoàn tất khi thay đổi đã được kiểm chứng trên môi trường bị ảnh hưởng và được đưa trở lại các nhánh còn hoạt động. Git quản lý commit/branch; Liquibase quản lý changeset identity, checksum và lịch sử ở từng database. Giữ nguyên migration đã triển khai, bảo toàn id/author/path khi backport cùng một thay đổi, kiểm tra include/dependency và xác minh trạng thái từng môi trường sẽ giúp bản sửa khẩn cấp không biến thành một lỗi triển khai lặp lại trong release kế tiếp.
