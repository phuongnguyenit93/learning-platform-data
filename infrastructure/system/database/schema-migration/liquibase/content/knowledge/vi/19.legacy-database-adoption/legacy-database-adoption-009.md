
# Lập kế hoạch chuyển giao từ script SQL hoặc công cụ migration khác sang Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase giúp quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một hệ thống đã có nhiều năm sử dụng SQL script thủ công, migration chạy trong pipeline riêng hoặc một công cụ như Flyway, việc chuyển sang Liquibase không đơn giản là đổi phần mở rộng file. Nhóm phải bảo toàn trạng thái database hiện tại, tránh chạy lại thay đổi cũ, giữ bằng chứng lịch sử và thống nhất công cụ nào được quyền thay đổi schema từ thời điểm chuyển giao.

Bài thuộc chương **Tiếp nhận CSDL** này trình bày cách lập kế hoạch chuyển giao từ script SQL hoặc công cụ migration khác. Nội dung đi từ kiểm kê lịch sử và trạng thái từng môi trường đến thiết kế baseline, sử dụng `changelog-sync` có kiểm soát, tổ chức changelog mới, chuyển đổi data migration, thử nghiệm, cutover và phương án khôi phục. Các nguyên tắc áp dụng cho cả hệ thống chạy Spring Boot lẫn pipeline CI/CD độc lập.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Mục tiêu là chuyển giao theo cách **một thay đổi cũ không bị chạy lại, một thay đổi mới không bị bỏ sót và mỗi database có thể giải thích được vì sao lịch sử Liquibase phản ánh đúng trạng thái thực tế**.

## 1. Chuyển công cụ migration là thay đổi quy trình vận hành

Một hệ thống có thể đang dùng một hoặc nhiều cách sau:

- Các file SQL được DBA chạy thủ công theo phiếu thay đổi.
- Script SQL được sắp xếp theo số phiên bản trong repository.
- Flyway hoặc công cụ migration khác chạy từ Maven, Gradle, CLI hoặc lúc ứng dụng khởi động.
- ORM tự cập nhật schema qua cấu hình như Hibernate DDL.
- Một số bảng do công cụ quản lý, phần còn lại được thay đổi thủ công.
- Các job ETL/data migration riêng thay đổi dữ liệu nhưng không ghi vào lịch sử schema.

Khi chuyển sang Liquibase, nhóm thay đổi **nguồn sự thật cho migration**, cách ghi nhận lịch sử, cách review, quyền tài khoản triển khai và quy trình phát hành. Nếu chỉ thêm Liquibase dependency mà vẫn để script cũ hoặc ORM tự sửa schema, database có thể bị nhiều chủ thể thay đổi đồng thời.

Hãy xem đây là một dự án chuyển giao có mốc bắt đầu, phạm vi database, chủ sở hữu và tiêu chí nghiệm thu. Không nên triển khai dần bằng cách để hai công cụ cùng chạy một bộ migration mà chưa có ranh giới rõ.

## 2. Xác định phạm vi và chủ sở hữu database

Trước khi viết changelog, lập danh sách các database và schema mà hệ thống quản lý:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Sản phẩm/DBMS | PostgreSQL, MySQL, MariaDB, Oracle, SQL Server hay DBMS khác? |
| Phiên bản | Phiên bản tối thiểu, phiên bản đang chạy ở từng môi trường? |
| Database/schema | Tên database, schema mặc định, schema chứa bảng lịch sử? |
| Ứng dụng sở hữu | Service nào đọc/ghi những bảng nào? |
| Chủ sở hữu vận hành | DBA, platform team hay nhóm ứng dụng phê duyệt DDL? |
| Công cụ hiện tại | SQL thủ công, Flyway, Liquibase cũ, ORM hay kết hợp? |
| Môi trường | Local, test, staging, production, tenant hoặc region nào? |
| Mức độ quan trọng | Dữ liệu có yêu cầu khôi phục, retention, audit hoặc SLA đặc biệt? |

Phạm vi phải bao gồm cả các đối tượng không phải bảng: sequence, view, materialized view, procedure, function, trigger, index, constraint, extension, synonym, grant và quyền. Một snapshot chỉ liệt kê bảng/cột chưa chắc mô tả đủ những gì ứng dụng cần.

Nếu nhiều service cùng dùng một database, xác định rõ **schema ownership** và ranh giới thay đổi. Không để hai nhóm cùng quản lý một bảng bằng hai changelog độc lập mà không có quy tắc điều phối.

## 3. Kiểm kê lịch sử từ SQL script hoặc công cụ cũ

Thu thập tất cả bằng chứng có thể truy vết:

- Tên và nội dung script SQL đã phát hành.
- Phiên bản, ngày chạy, môi trường và database đích.
- Người hoặc pipeline thực thi, pull request và commit liên quan.
- Kết quả thành công/thất bại, log, ticket và phê duyệt.
- Bản sửa nóng chạy ngoài quy trình chuẩn.
- Script được chạy lại nhiều lần hoặc chỉ chạy ở một môi trường.
- Data migration, backfill và thao tác thủ công không nằm trong repository.
- Các thay đổi bị bỏ qua hoặc được DBA áp dụng theo cách khác.

Không coi danh sách file trong Git là bằng chứng đầy đủ rằng tất cả file đã chạy trên mọi database. Một script có thể đã merge nhưng chưa deploy; một script khác có thể đã chạy production nhưng không có trong repository.

Lập bảng ánh xạ lịch sử:

| Migration cũ | Trạng thái thực tế | Database/môi trường | Bằng chứng | Quyết định |
|---|---|---|---|---|
| V001 create customer | Đã áp dụng | Dev/test/staging/prod | Lịch sử tool + schema | Đưa vào baseline/history mapping |
| V002 add status | Đã áp dụng một phần | Production | Log và kiểm tra cột | Điều tra trước khi đồng bộ |
| V003 backfill status | Khác nhau theo môi trường | Dev/prod | Row count, dữ liệu | Xác minh data migration |
| V004 create index | Chỉ có ở staging | Staging | Snapshot schema | Lập kế hoạch reconcile |

Nếu trạng thái không rõ, đánh dấu **unknown** và điều tra. Không dùng `changelog-sync` để biến một trạng thái chưa biết thành “đã áp dụng”.

## 4. Phân biệt lịch sử công cụ cũ và trạng thái database hiện tại

Lịch sử migration là bằng chứng về những gì công cụ đã ghi nhận. Trạng thái schema/data hiện tại là bằng chứng về database đang có gì. Hai thứ có thể khác nhau.

Ví dụ:

- Flyway ghi V12 thành công, nhưng một DBA đã xóa index sau đó.
- SQL script V15 được chạy trên production nhưng không được ghi vào bảng lịch sử.
- Một migration thêm cột thất bại giữa chừng do DDL autocommit; bảng đã có một phần thay đổi.
- Staging được tạo mới từ script đã chỉnh sửa, còn production vẫn giữ phiên bản cũ.
- Một job được đánh dấu thành công nhưng data backfill chỉ xử lý một phần.

Vì vậy, kiểm kê cần hai trục:

1. **Lịch sử:** công cụ cũ nói migration nào đã chạy, vào lúc nào và kết quả gì?
2. **Thực tế:** schema, đối tượng và dữ liệu của từng database hiện ra sao?

Không được suy ra trạng thái database chỉ từ bảng lịch sử, cũng không suy ra lịch sử triển khai chỉ từ snapshot schema. Một bảng hiện có không cho biết nó được tạo bởi script nào hoặc có cấu trúc giống hoàn toàn với thiết kế cũ hay không.

## 5. Chọn chiến lược chuyển giao

Thông thường có ba chiến lược, tùy mức độ đáng tin của lịch sử và sự khác biệt giữa môi trường.

| Chiến lược | Mô tả | Phù hợp khi | Chi phí/rủi ro |
|---|---|---|---|
| **Baseline trạng thái hiện tại** | Tạo changelog mô tả schema/data nền đã có, sau đó đồng bộ lịch sử để Liquibase không chạy lại phần đó | Hệ thống cũ đã có lịch sử hoặc cần tiếp nhận nhanh nhưng trạng thái hiện tại được xác minh | Không tái tạo toàn bộ lịch sử thay đổi trong Liquibase |
| **Chuyển từng migration lịch sử** | Chuyển các script cũ thành changeset, đánh dấu các thay đổi đã có là đã xử lý | Lịch sử script đầy đủ, thứ tự và kết quả từng môi trường rõ | Nhiều công việc mapping, dễ sai identity hoặc thiếu thay đổi thủ công |
| **Dựng lại database theo changelog mới** | Thiết kế changelog từ trạng thái đích và migrate/reconcile database cũ | Hệ thống nhỏ, có thể tạo lại hoặc chấp nhận một dự án chuẩn hóa lớn | Rủi ro cao với dữ liệu production và các khác biệt chưa biết |

Không có một chiến lược tối ưu cho mọi hệ thống. **Baseline** thường thực tế khi database đã vận hành lâu và lịch sử cũ được giữ ở hệ thống riêng. Chuyển từng migration có lợi khi cần truy vết chi tiết trong một công cụ, nhưng chỉ nên làm khi dữ liệu lịch sử đủ tin cậy.

Có thể kết hợp: lưu archive lịch sử cũ, baseline schema hiện tại trong Liquibase, sau đó tạo changeset mới cho mọi thay đổi kể từ mốc chuyển giao.

## 6. Baseline là gì?

**Baseline** là mốc xác định trạng thái database mà Liquibase bắt đầu chịu trách nhiệm. Một baseline tốt mô tả những đối tượng và điều kiện cần có tại thời điểm tiếp nhận, đồng thời xác nhận database đã đạt trạng thái đó.

Ví dụ cấu trúc changelog:

~~~text
db/changelog/
  db.changelog-master.yaml
  baseline/
    0001-existing-schema.yaml
  changes/
    0002-add-customer-status.yaml
    0003-create-order-index.yaml
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/0001-existing-schema.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/0002-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/0003-create-order-index.yaml
      relativeToChangelogFile: true
~~~

Baseline có thể chứa các changeset mô tả bảng, cột, index, constraint và đối tượng đã tồn tại. Nhưng nếu database hiện tại có những khác biệt, baseline không tự sửa chúng. Nhóm phải reconcile hoặc dừng để điều tra trước khi ghi nhận baseline.

**Baseline không phải backup và cũng không phải toàn bộ lịch sử nghiệp vụ.** Nó là hợp đồng về trạng thái bắt đầu của Liquibase.

## 7. Tạo baseline từ schema hiện tại

Liquibase có thể hỗ trợ tạo changelog từ database hiện tại bằng các lệnh như `generate-changelog`, hoặc so sánh reference database và target database để tạo diff changelog tùy phiên bản và cấu hình.

Các công cụ này hữu ích để thu thập cấu trúc, nhưng kết quả sinh tự động phải được review:

- Có bỏ sót object type mà ứng dụng cần không?
- Có đưa vào object thuộc schema hệ thống hoặc extension không?
- Có giữ đúng thứ tự tạo sequence, table, constraint, view và function không?
- Có nhận diện đúng schema/catalog và default schema không?
- Có chứa định nghĩa DBMS-specific không?
- Có tái hiện quyền, grant, trigger, synonym, partition hoặc object phụ thuộc không?
- Có tạo ra tên định danh/đường dẫn ổn định không?

Một schema snapshot không tự tái tạo được **lý do** một thay đổi đã được thực hiện, data migration đã chuyển dữ liệu thế nào, hoặc script cũ có side effect nào. Các bước đó phải lấy từ lịch sử script, log và tài liệu thiết kế.

Ví dụ lệnh khái niệm:

~~~text
liquibase generate-changelog
~~~

Cú pháp, option schema, output path, reference URL và khả năng của extension phụ thuộc phiên bản Liquibase. Không chạy lệnh sinh changelog trực tiếp trên production mà chưa xác định đúng database và nơi ghi output. Với quy trình chuyển giao, thường nên dùng một bản sao hoặc kết nối chỉ đọc để khảo sát, sau đó review file sinh ra trong pull request.

## 8. So sánh baseline với từng môi trường

Một baseline duy nhất chỉ có ý nghĩa nếu những database được tiếp nhận thực sự phù hợp với trạng thái mà nó mô tả.

Có thể tạo snapshot/diff cho từng môi trường và lập bảng:

| Đối tượng | Dev | Staging | Production | Xử lý |
|---|---|---|---|---|
| customer | Đúng | Đúng | Đúng | Đưa vào baseline |
| customer.status | Có | Có | Chưa có | Reconcile production trước |
| idx_customer_email | Có | Thiếu | Có | Tạo changeset sửa staging hoặc xử lý riêng |
| v_customer_active | Định nghĩa mới | Định nghĩa cũ | Thiếu | Xác minh ứng dụng và thống nhất |
| grant SELECT | Có | Có | Thiếu | Review quyền và chủ sở hữu |

Không chạy baseline sync cho tất cả môi trường chỉ vì một database đã đạt. Mỗi database có thể cần một kế hoạch reconcile riêng. Nếu một object thiếu, việc đánh dấu changeset tạo object là đã chạy sẽ khiến Liquibase không tạo nó; nếu object tồn tại sai định nghĩa, việc chỉ kiểm tra tên có thể che giấu drift.

Khi có nhiều tenant/database, tạo ma trận trạng thái và phê duyệt riêng cho từng nhóm hoặc từng database theo cách tổ chức triển khai.

## 9. Changelog-sync: đánh dấu đã xử lý mà không thực thi thay đổi

Lệnh **changelog-sync** của Liquibase được dùng để đánh dấu các changeset chưa được ghi nhận trong lịch sử là đã được xử lý, mà không thực thi nội dung thay đổi của chúng. Nó thường hữu ích trong quy trình baseline/adoption khi schema hiện tại **đã có kết quả tương đương** với các changeset trong changelog.

Ví dụ dạng lệnh CLI:

~~~text
liquibase changelog-sync
~~~

Tên command và option kết nối phụ thuộc phiên bản CLI/plugin. Có thể có lệnh preview SQL tương ứng, chẳng hạn `changelog-sync-sql`, tùy phiên bản. Luôn xác nhận command và cú pháp bằng đúng Liquibase version của dự án.

Điều phải hiểu rõ:

- `changelog-sync` **không tạo bảng, cột, index hay dữ liệu**.
- Nó ghi nhận changeset như đã chạy trong DATABASECHANGELOG theo cơ chế đồng bộ lịch sử.
- Sau đó update thông thường sẽ không thực hiện lại những changeset đã được ghi nhận theo định danh đó.
- Nếu schema/data thực tế thiếu thay đổi mà changelog mô tả, việc sync có thể làm Liquibase bỏ qua thay đổi còn thiếu.
- Một changeset data migration được sync cũng không chạy backfill của nó.

Vì vậy, chỉ dùng changelog-sync khi có bằng chứng database hiện tại đã đạt **đầy đủ kết quả** của những changeset sẽ được đánh dấu. Không dùng nó để làm cho status hết pending hoặc để né lỗi migration.

## 10. Baseline changelog nên chứa gì trước khi sync?

Một baseline thường mô tả cấu trúc hiện có tại thời điểm tiếp nhận. Tùy phạm vi ứng dụng, có thể gồm:

- Schema và các bảng thuộc quyền sở hữu.
- Cột, kiểu dữ liệu, default, nullable.
- Primary key, unique, foreign key và check constraint.
- Index, partition, sequence và identity.
- View, materialized view, function, procedure và trigger.
- Các đối tượng hỗ trợ như synonym, type hoặc extension khi Liquibase/DBMS hỗ trợ.
- Quyền và grant nếu chúng nằm trong phạm vi quản lý.
- Dữ liệu tham chiếu cốt lõi nếu nhóm chọn quản lý bằng changelog.

Không nhất thiết baseline phải chứa mọi object của toàn database. Có thể giới hạn schema/đối tượng thuộc ứng dụng, nhưng phải ghi rõ phạm vi và những object nằm ngoài quyền quản lý. Tránh tạo một baseline quá rộng gồm cả object hệ thống hoặc object do DBA/ứng dụng khác sở hữu.

Một changeset baseline chỉ nên mô tả **trạng thái đã tồn tại**. Các thay đổi mới sau thời điểm tiếp nhận phải nằm trong changeset tiếp theo, không được trộn lẫn vào baseline đã đồng bộ.

## 11. Hai cách quản lý lịch sử cũ: archive hay chuyển thành changeset

Khi chuyển từ SQL script/Flyway, nhóm cần quyết định có muốn toàn bộ lịch sử cũ xuất hiện trong DATABASECHANGELOG hay không.

### Cách A — Giữ lịch sử cũ bên ngoài, baseline trạng thái hiện tại

- Giữ repository, bảng lịch sử cũ, log và release record như bằng chứng.
- Tạo baseline changelog mô tả trạng thái database khi bàn giao.
- Đồng bộ baseline đã được xác minh.
- Từ mốc tiếp nhận, mọi thay đổi mới do Liquibase quản lý.

Ưu điểm: đơn giản, giảm công việc chuyển đổi lịch sử và ít nguy cơ chạy lại script cũ. Hạn chế: DATABASECHANGELOG không hiển thị từng migration lịch sử trước thời điểm chuyển giao; cần liên kết baseline với archive cũ.

### Cách B — Chuyển các migration cũ thành changeset

- Ánh xạ từng script cũ sang id, author, filename và thứ tự ổn định.
- Xác minh database đã thực hiện các thay đổi đó.
- Dùng cơ chế đồng bộ lịch sử để đánh dấu những changeset đã được áp dụng.
- Giữ script/changelog cũ bất biến sau khi tiếp nhận.

Ưu điểm: có thể tra cứu lịch sử theo cấu trúc Liquibase. Hạn chế: mapping phức tạp, có thể thiếu log, dữ liệu đã thay đổi hoặc môi trường có trạng thái khác nhau. Việc chuyển đổi không tự biến checksum của công cụ cũ thành checksum Liquibase tương đương.

Nếu cần audit lịch sử cũ, **không xóa hoặc sửa bảng history của công cụ trước**. Giữ bản archive và tài liệu mapping, kể cả khi Liquibase chỉ bắt đầu theo dõi từ baseline hiện tại.

## 12. Chuyển từ Flyway: không giả định Liquibase tự hiểu schema history

Flyway và Liquibase có mô hình lưu lịch sử riêng. Flyway thường dùng bảng lịch sử schema với thông tin phiên bản migration, mô tả, loại, script, checksum, thời điểm và trạng thái theo phiên bản/cấu hình. Liquibase dùng DATABASECHANGELOG với bộ định danh changeset và checksum của riêng nó.

**Liquibase không mặc nhiên nhập và chuyển đổi bảng lịch sử Flyway thành DATABASECHANGELOG.** Cần thiết kế mapping hoặc giữ history cũ như archive.

Một kế hoạch chuyển từ Flyway có thể gồm:

1. Chụp trạng thái bảng lịch sử Flyway ở từng database.
2. Thu thập mọi migration versioned/repeatable đã áp dụng, checksum, script và release liên quan.
3. Xác minh trạng thái schema/data thực tế, đặc biệt các migration thất bại hoặc repair/baseline.
4. Chọn baseline hiện tại hoặc chuyển lịch sử thành changeset.
5. Chuẩn bị changelog Liquibase và kiểm tra id/author/filename.
6. Thử changelog-sync trên clone để đánh dấu các thay đổi đã tồn tại.
7. Dừng Flyway auto-migration ở đúng mốc cutover.
8. Bật một chủ thể Liquibase duy nhất và kiểm chứng update mới.

Không để Flyway và Liquibase cùng chạy migration trên một schema sau cutover. Hai công cụ không dùng chung một khóa điều phối và có thể không biết thay đổi của nhau. Nếu một pipeline dùng Flyway còn một pod Spring Boot dùng Liquibase, DATABASECHANGELOGLOCK không thể ngăn Flyway sửa database đồng thời.

## 13. Chuyển từ script SQL thủ công

Khi lịch sử được DBA chạy bằng tay, thường không có một bảng history đầy đủ. Quy trình cần dựa vào log change request, file SQL, backup, schema snapshot và xác nhận của DBA.

Các bước quan trọng:

- Lập danh sách script đã chạy ở mỗi database.
- Đối chiếu nội dung script với schema/data hiện tại.
- Xác định script nào chạy nhiều lần, chạy một phần hoặc được sửa trước khi chạy.
- Ghi lại các hotfix ngoài repository.
- Xác định thay đổi không thể tái tạo từ snapshot, đặc biệt data migration.
- Chốt mốc đóng băng DDL và người có quyền thay đổi database trong lúc chuyển giao.

Nếu không có bằng chứng rằng script cũ đã chạy, không tự động đưa nó vào baseline và đánh dấu sync. Có thể phải tạo changeset mới để reconcile trạng thái thật, hoặc dùng một runbook DBA riêng trước khi Liquibase tiếp quản.

Một số script thủ công có thể chứa lệnh client như `DELIMITER`, `GO`, `SET ECHO`, `PROMPT` hoặc lệnh shell. Khi chuyển thành Liquibase changelog, phải phân biệt SQL server hiểu với chỉ thị của client; lựa chọn sql/sqlFile, splitStatements, endDelimiter hoặc native executor phù hợp.

## 14. Không chuyển nguyên xi script cũ mà chưa review

Một file SQL từng chạy tốt trong môi trường thủ công có thể không tương thích với JDBC hoặc Liquibase parser. Kiểm tra:

- SQL dialect và DBMS đích.
- Delimiter, batch separator và client directive.
- Transaction/implicit commit của DDL.
- Quyền và default schema.
- Đường dẫn file, encoding và newline.
- Tham số được thay thế từ shell/CI.
- Các câu lệnh không idempotent.
- SQL phụ thuộc trạng thái môi trường hoặc dữ liệu.
- Side effect từ trigger, procedure, job hoặc extension.

Ví dụ script MySQL CLI:

~~~sql
DELIMITER $$
CREATE PROCEDURE sp_rebuild_summary()
BEGIN
    UPDATE summary_table SET refreshed_at = CURRENT_TIMESTAMP;
END$$
DELIMITER ;
~~~

Các dòng `DELIMITER` là chỉ thị của MySQL client, không phải SQL server thông thường gửi qua JDBC. Khi chuyển sang Liquibase JDBC, thường cần loại chỉ thị client và cấu hình endDelimiter phù hợp trong changeset, sau đó thử trên đúng phiên bản MySQL. Với native executor, quy tắc có thể khác và phải theo công cụ thực thi.

Không copy/paste hàng loạt script rồi chỉ đổi phần mở rộng thành .sql hoặc .yaml.

## 15. Data migration cũ cần được xác minh riêng

Snapshot schema không mô tả đầy đủ dữ liệu đã được chuyển đổi. Ví dụ một script cũ:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Sau khi chạy, không thể nhìn vào schema hiện tại để biết:

- Có bao nhiêu hàng đã được cập nhật?
- Trước đó có bao nhiêu hàng NULL?
- Script đã chạy trên mọi môi trường chưa?
- Một phần dữ liệu đã được sửa thủ công sau đó chưa?
- Có ứng dụng ghi lại NULL sau khi migration không?

Khi chuyển data migration:

1. Lấy script và lịch sử thực thi cũ.
2. Định nghĩa invariant dữ liệu sau migration.
3. Đối chiếu row count, khóa và giá trị thực tế theo từng database.
4. Phân loại đã hoàn thành, chưa chạy, chạy một phần hoặc không rõ.
5. Chỉ sync changeset nếu kết quả đã được xác minh tương đương.
6. Nếu còn thiếu, tạo changeset mới hoặc job batch để reconcile.
7. Kiểm thử rollback/forward fix và ảnh hưởng dữ liệu trước cutover.

Không dùng changelog-sync để đánh dấu một data migration là đã chạy chỉ vì câu SQL có vẻ đơn giản hoặc vì schema đã giống nhau.

## 16. Định danh changeset phải ổn định từ mốc chuyển giao

Liquibase nhận diện changeset thông thường bằng **id + author + filename**. Checksum kiểm tra nội dung theo quy tắc Liquibase; nó không thay thế bộ định danh.

Ví dụ baseline:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: baseline-001-customer-table
      author: database-platform
      comment: >-
        Baseline tại mốc tiếp nhận từ hệ thống SQL scripts cũ.
        Cấu trúc được đối chiếu trên database trước khi đồng bộ lịch sử.
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
                  type: varchar(320)
                  constraints:
                    nullable: false
~~~

Ví dụ chỉ mô tả một bảng và không nên được coi là baseline hoàn chỉnh. Nếu database đã có bảng customer, không chạy update changeset này như migration tạo bảng; phải chọn quy trình baseline/sync phù hợp sau khi xác minh.

Khi đã đồng bộ và triển khai, giữ ổn định id, author, filename logic và nội dung. Nếu di chuyển tệp, xem xét logicalFilePath theo phiên bản Liquibase để giữ FILENAME đã ghi nhận. Không đổi định danh cũ chỉ để đổi tên nhóm hoặc tổ chức lại thư mục.

## 17. Changelog-sync không phải repair schema

Một nhầm lẫn thường gặp là thấy database có vài bảng nhưng status báo nhiều changeset pending, rồi chạy changelog-sync để “đồng bộ”.

Điều này nguy hiểm vì một changeset có thể gồm nhiều thay đổi: bảng, index, constraint, view hoặc dữ liệu. Chỉ nhìn thấy bảng tồn tại không chứng minh tất cả phần còn lại đã áp dụng.

Trước sync, lập bảng đối chiếu:

| Changeset | Kết quả mong đợi | Bằng chứng thực tế | Có thể sync? |
|---|---|---|---|
| create customer | Bảng, cột, PK | Snapshot + metadata | Có nếu đầy đủ |
| add customer status | Cột status đúng kiểu/default | Snapshot | Chỉ khi xác minh đủ |
| create index | Index đúng cột/thứ tự/unique | Metadata index | Không chỉ dựa vào tên |
| backfill status | Không còn NULL theo điều kiện | Query dữ liệu | Chỉ khi invariant đạt |
| add foreign key | Constraint đúng nguồn/đích | Metadata constraint | Có nếu cấu trúc đúng |

Nếu một changeset có hai change và chỉ một change đã có, không sync cả changeset như thể đã hoàn thành. Hãy reconcile trạng thái còn thiếu trước, hoặc thiết kế changeset sửa tiếp với lịch sử rõ ràng.

## 18. Quản lý khác biệt giữa môi trường trước cutover

Một dự án có thể có production đã áp dụng script V20, staging mới ở V19, còn development dùng database được tạo lại từ nhánh mới. Không thể lấy một database làm đại diện rồi sync cùng một bộ changeset cho tất cả.

Tạo ma trận:

| Môi trường | Mốc cũ | Schema/data hiện tại | Mốc Liquibase mục tiêu | Việc cần làm |
|---|---|---|---|---|
| Development | Script V20 | Mới nhất | Baseline + future changes | Rebuild/validate |
| Test | Script V20 | Thiếu index | Baseline + reconcile index | Sửa trước hoặc changeset bổ sung |
| Staging | Script V19 | Thiếu cột status | Mốc V20 | Áp dụng thay đổi còn thiếu có kiểm soát |
| Production | Script V20 + hotfix | Có object ngoài repo | Baseline theo trạng thái đã duyệt | Kiểm tra hotfix và sync |

Không đồng bộ lịch sử một cách đồng loạt khi các database đang lệch nhau. Chọn thứ tự triển khai, thời điểm freeze và cách xử lý từng chênh lệch trước khi bật Liquibase ở production.

Nếu cần giữ nhiều mốc tạm thời, ghi lại từng môi trường đã cutover ở revision nào. Không để một pipeline assume tất cả database đã baseline chỉ vì một môi trường test thành công.

## 19. Single-writer: chỉ một công cụ được quyền thay đổi schema

Trong giai đoạn cutover, cần quy định **một chủ thể migration duy nhất** cho mỗi database/schema.

Trước cutover:

- SQL script/Flyway/ORM cũ đang là nguồn thay đổi.
- Liquibase chỉ được chạy trên clone hoặc trong giai đoạn thử nghiệm được kiểm soát.
- Không cho hai hệ thống cùng áp dụng migration thật.

Tại cutover:

1. Dừng lịch chạy migration của công cụ cũ.
2. Xác nhận không còn job hoặc ứng dụng tự cập nhật schema.
3. Chốt revision cuối cùng và trạng thái database.
4. Chạy baseline/sync theo kế hoạch đã duyệt.
5. Kiểm tra DATABASECHANGELOG và schema thực tế.
6. Bật Liquibase cho những thay đổi tiếp theo.

Sau cutover:

- Liquibase là nguồn sự thật cho schema/data migration trong phạm vi đã thống nhất.
- Công cụ cũ ở trạng thái disabled/read-only hoặc chỉ giữ để tham khảo, không còn thực thi migration.
- Thay đổi khẩn cấp ngoài Liquibase phải có runbook ghi nhận và được đưa trở lại changelog bằng quy trình reconcile được review.
- ORM nên dùng chế độ validate/none phù hợp, tránh tự động sửa schema song song.

**DATABASECHANGELOGLOCK chỉ điều phối các tiến trình Liquibase dùng cùng bảng lock. Nó không ngăn Flyway hoặc DBA chạy SQL đồng thời.**

## 20. Tài khoản và quyền sau khi chuyển giao

Tài khoản dùng bởi công cụ cũ có thể có quyền rộng hoặc được chia sẻ. Khi chuyển sang Liquibase, hãy thiết kế quyền riêng:

- Quyền đọc metadata cần thiết để kiểm tra schema/precondition.
- Quyền tạo/cập nhật DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Quyền DDL/DML đúng với các changeset được phê duyệt.
- Quyền quản lý schema/object thuộc phạm vi ứng dụng.
- Không cấp quyền DBA toàn cục nếu migration không cần.
- Không lưu mật khẩu trong changelog hoặc repository.
- Quản lý credential qua secret store/CI environment.
- Tách tài khoản migration khỏi tài khoản runtime của ứng dụng khi phù hợp.

Một số DBMS cần quyền đặc biệt để tạo extension, procedure, schema hoặc cấp grant. Nếu quyền bị thiếu, migration có thể thất bại giữa chừng. Phải thử bằng **đúng tài khoản deployment** trên database tương đương, không chỉ thử bằng tài khoản DBA.

## 21. Precondition và kiểm soát trạng thái tiếp nhận

Precondition có thể xác nhận database đáp ứng tiền đề trước khi changeset chạy. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-add-customer-status
      author: database-platform
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
                  constraints:
                    nullable: true
~~~

Ở đây changeset yêu cầu bảng customer tồn tại; nếu không, dừng thay vì âm thầm bỏ qua. Trong chuyển giao, có thể cần thêm sqlCheck hoặc kiểm tra cấu trúc trước khi đánh dấu baseline.

Một số chính sách:

- **HALT:** khi trạng thái không đúng phải dừng cutover.
- **WARN:** chỉ dùng khi điều kiện không mang tính bắt buộc và việc tiếp tục thực sự an toàn.
- **CONTINUE:** bỏ qua changeset trong lần này để có thể xét lại sau, khi thiết kế có chủ đích.
- **MARK_RAN:** đánh dấu changeset như đã xử lý mà không thực thi changes; chỉ dùng khi kết quả đã có sẵn và được xác minh.

MARK_RAN không phải cách chữa database thiếu đối tượng. Nếu điều kiện chỉ kiểm tra tableExists nhưng bảng sai cột/constraint, việc sync/mark-ran có thể che giấu drift.

## 22. Dữ liệu tham chiếu và dữ liệu nghiệp vụ khi tiếp nhận

Không phải dữ liệu nào cũng nên được chuyển thành insert changeset.

| Loại dữ liệu | Ví dụ | Chiến lược |
|---|---|---|
| Reference data | Mã trạng thái, loại khách hàng | Có thể quản lý bằng changeset với khóa ổn định |
| Configuration | Feature flag, ngưỡng theo môi trường | Tách cấu hình môi trường hoặc nguồn quản lý riêng |
| Test fixture | Người dùng giả, đơn hàng giả | Chỉ áp dụng ở test với filter/guard rõ ràng |
| Transactional data | Khách hàng, đơn hàng, giao dịch | Không đưa dữ liệu production vào changelog; migration có phạm vi riêng |
| Derived data | Bảng tổng hợp, cache | Xem xét rebuild hoặc job tái tạo |

Nếu công cụ cũ đã insert mã danh mục, không nên chuyển nguyên script insert vào changelog mới rồi chạy trên database hiện có. Có thể đưa các thay đổi lịch sử vào baseline/history mapping và đồng bộ sau khi xác minh. Với mã mới kể từ cutover, dùng changeset insert có khóa ổn định, unique constraint và rollback được đánh giá.

Không lưu PII, secret hoặc bản dump production trong file SQL/YAML. Nếu cần test với dữ liệu đại diện, ẩn danh hoặc tạo fixture giả.

## 23. Kiểm tra DBMS, schema và thứ tự triển khai

Changelog có thể chứa các change type chung hoặc SQL riêng DBMS. Khi chuyển từ công cụ cũ, phải xác định script trước đây dựa vào dialect nào:

- Kiểu dữ liệu như JSONB, NVARCHAR, NUMBER, identity/serial.
- Cú pháp tạo index online/concurrently.
- Stored procedure, function, trigger và delimiter.
- Sequence, synonym, partition, extension.
- Default schema, quoting và case sensitivity.
- Transaction/implicit commit của DDL.
- Quyền tạo object và owner.

Nếu dự án hỗ trợ nhiều DBMS, dùng change type chung khi thích hợp và tách changeset theo dbms khi SQL thực sự khác. Không giả định script cũ chạy trên MySQL thì tự chạy được trên MariaDB, PostgreSQL hoặc H2.

Thứ tự include/master changelog phải thể hiện dependency. Ví dụ tạo bảng trước, tạo foreign key sau, insert reference data trước khi backfill khóa ngoại, và chỉ siết constraint sau khi dữ liệu đã đạt yêu cầu.

## 24. Cutover từ công cụ cũ: kế hoạch theo giai đoạn

Một kế hoạch mẫu:

~~~text
Giai đoạn 1 — Khảo sát
  Inventory tool/scripts, DBMS, database, môi trường, schema và data
             |
             v
Giai đoạn 2 — Reconcile
  So sánh history với trạng thái thực, phân loại drift và hotfix
             |
             v
Giai đoạn 3 — Baseline
  Tạo changelog nền, review object và mapping lịch sử
             |
             v
Giai đoạn 4 — Rehearsal
  Clone DB, thử sync, kiểm tra DATABASECHANGELOG và schema/data
             |
             v
Giai đoạn 5 — Freeze và cutover
  Dừng tool cũ, xác nhận single-writer, baseline/sync có kiểm soát
             |
             v
Giai đoạn 6 — Verify
  Validate/status/updateSQL, kiểm tra object, dữ liệu và ứng dụng
             |
             v
Giai đoạn 7 — Operate
  Chỉ Liquibase quản lý thay đổi mới, theo dõi và audit
~~~

Không nên gộp khảo sát, baseline và cutover vào một lần chạy production. Mỗi giai đoạn cần owner, bằng chứng hoàn thành, điều kiện dừng và người phê duyệt.

Trong ngày cutover, chuẩn bị danh sách các database đích, thời gian freeze, runner được phép chạy, revision changelog, câu lệnh chính xác và kế hoạch khôi phục. Không chạy đồng thời hai migration tool để “đảm bảo không sót”.

## 25. Kiểm chứng baseline và cutover

Trước khi thực hiện sync/update trên database đích, cần có checklist kiểm chứng:

1. Kết nối đúng database, DBMS, schema và tài khoản.
2. Changelog master và mọi file include có trong artifact.
3. Changelog được validate bằng đúng phiên bản Liquibase.
4. Schema snapshot khớp với baseline mong đợi.
5. Các index, constraint, view, routine và grant quan trọng đã được kiểm tra.
6. Dữ liệu tham chiếu và invariant nghiệp vụ đạt.
7. Những migration lịch sử đã chạy không bị đưa thành pending ngoài ý muốn.
8. SQL preview không có DDL/DML cũ sẽ chạy lại.
9. DATABASECHANGELOG và DATABASECHANGELOGLOCK được đặt ở schema/tên dự kiến.
10. Có backup/PITR và thời gian restore đã được kiểm chứng.
11. Công cụ cũ đã dừng, không còn job hoặc ứng dụng tự migration.
12. Sau sync, status phản ánh đúng những thay đổi còn pending; schema/data vẫn đúng.
13. Chạy một changeset mới nhỏ trên môi trường thử nghiệm để chứng minh Liquibase tiếp quản được.
14. Ứng dụng khởi động và truy vấn đúng với schema được quản lý.

`validate` thành công không chứng minh database đã baseline đúng. `changelog-sync` thành công cũng không chứng minh schema/data tương đương. Cần kiểm tra cả **lịch sử và thực tế**.

## 26. Rollback kế hoạch chuyển giao

Cutover có thể thất bại do thiếu object, checksum mismatch, quyền không đủ hoặc schema giữa các môi trường không đồng nhất. Phải chuẩn bị trước:

- Nếu chưa sync: có thể dừng và điều tra, giữ nguyên tool cũ nhưng phải xác nhận không có DDL mới từ Liquibase.
- Nếu đã sync nhưng chưa có thay đổi schema: không coi việc xóa DATABASECHANGELOG là rollback mặc định; xác định tác động của lịch sử đã ghi và dùng quy trình được duyệt.
- Nếu đã thực thi changeset mới: đánh giá rollback tường minh, dữ liệu phát sinh và khả năng forward fix.
- Nếu schema đã bị thay đổi một phần: đối chiếu DBMS transaction, DDL autocommit và session trước khi retry.
- Nếu phải quay lại công cụ cũ: xác nhận nó hiểu trạng thái database hiện tại và không chạy lại migration đã được Liquibase áp dụng.
- Nếu cần restore: xác định điểm phục hồi và những giao dịch hợp lệ sau điểm đó có thể bị mất.

**Không xóa bảng DATABASECHANGELOG/LOCK để quay lại trạng thái cũ.** Những bảng này ghi lịch sử/điều phối của Liquibase; xóa chúng không khôi phục schema hoặc dữ liệu. Một lần restore database phải đi cùng kế hoạch đồng bộ lịch sử công cụ.

## 27. Bài thực hành: tiếp nhận database đang được quản lý bằng SQL scripts

Thực hành trên database disposable hoặc clone đã ẩn danh, không dùng production.

### Bước 1 — Chuẩn bị database hiện có

Giả lập một database được quản lý bằng script SQL cũ. Database có bảng customer, customer_type, index và một số dữ liệu tham chiếu. Lưu lại script cũ và bằng chứng đã chạy.

### Bước 2 — Kiểm kê và chụp trạng thái

Dùng công cụ DBMS hoặc Liquibase để lấy snapshot schema. Ghi lại cột, kiểu dữ liệu, constraint, index, view, routine và các object ứng dụng cần thiết. Kiểm tra dữ liệu tham chiếu bằng truy vấn chỉ đọc.

### Bước 3 — Tạo baseline changelog

Tạo một baseline changelog từ trạng thái đã xác minh. Có thể dùng generate-changelog làm điểm bắt đầu rồi review. Loại bỏ object ngoài phạm vi, bổ sung phần thiếu và giữ file/changeset identity ổn định.

### Bước 4 — Thử sync trên clone

Chạy validate, status và preview changelog-sync nếu phiên bản hỗ trợ. Xác nhận tất cả changeset sắp được đánh dấu đều đã có kết quả tương đương. Thực hiện sync trên clone, rồi kiểm tra DATABASECHANGELOG và schema.

### Bước 5 — Thêm thay đổi mới

Tạo changeset mới thêm một cột optional hoặc một index có kiểm soát. Chạy update-sql, review và update trên clone. Xác nhận changeset mới được ghi nhận, còn baseline không bị chạy lại.

### Bước 6 — Thử database có drift

Tạo bản clone thứ hai thiếu index hoặc có kiểu cột khác baseline. Chạy status và kiểm tra trước sync. Không sync mù quáng; tạo kế hoạch reconcile hoặc changeset sửa trạng thái. So sánh kết quả với clone chuẩn.

### Bước 7 — Mô phỏng cutover

Tắt job script SQL cũ, chạy migration Liquibase theo quy trình duy nhất, kiểm tra ứng dụng và lưu mapping từ phiên bản script cũ sang baseline. Sau đó thử update một changeset mới để chứng minh Liquibase là chủ thể quản lý từ mốc bàn giao.

## 28. Bài thực hành: chuyển từ Flyway sang Liquibase

Trên một database thử nghiệm có Flyway history:

1. Chụp lại bảng lịch sử Flyway và lưu các file migration đúng revision.
2. Xác nhận những version đã chạy, migration thất bại, repair/baseline và trạng thái schema.
3. Chọn chiến lược giữ history Flyway bên ngoài hoặc chuyển các migration đã xác minh thành changeset.
4. Tạo Liquibase baseline và review id/author/filename.
5. Thử changelog-sync trên clone; kiểm tra không thực thi lại SQL cũ.
6. Tắt Flyway migration runner trong cấu hình cutover.
7. Chỉ bật một Liquibase runner, xác nhận DATABASECHANGELOG và trạng thái schema.
8. Tạo một changeset mới để chứng minh migration sau cutover được Liquibase quản lý.
9. Thử khởi động Spring Boot với cấu hình Liquibase phù hợp; không để Flyway và Liquibase cùng auto-run.
10. Lưu tài liệu mapping lịch sử cũ, baseline tag/revision, owner và runbook.

Không cần xóa bảng Flyway history sau cutover. Giữ nó như bằng chứng lịch sử theo chính sách lưu trữ; chỉ tắt cơ chế thực thi của Flyway sau khi nhóm xác nhận không còn runner nào sử dụng.

## 29. Những lỗi thường gặp khi tiếp nhận database cũ

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Liquibase định tạo lại bảng đã có | Changelog lịch sử đang pending hoặc identity khác | Dừng update, đối chiếu FILENAME/id/author và baseline strategy |
| Changelog-sync thành công nhưng ứng dụng lỗi | Changeset được đánh dấu dù object/data chưa tương đương | Kiểm tra snapshot và invariant; reconcile bằng thay đổi mới |
| Staging thành công, production thiếu index | Các môi trường khác trạng thái trước cutover | Ma trận trạng thái riêng, xử lý drift trước sync |
| Flyway và Liquibase cùng chạy | Hai runner chưa được tắt/boundary không rõ | Thiết lập single-writer, dừng tool cũ trước cutover |
| Checksum mismatch sau khi chuyển file | Chỉnh nội dung hoặc identity không ổn định | So sánh revision, giữ identity, tạo changeset mới nếu cần |
| Script cũ chạy qua CLI nhưng lỗi qua JDBC | Client directive, delimiter hoặc transaction khác | Chuyển cú pháp, splitStatements/endDelimiter và thử executor |
| Dữ liệu production khác staging | Backfill/SQL thủ công chưa đồng nhất | Kiểm tra data invariant và log, không sync chỉ dựa vào schema |
| DATABASECHANGELOG bị tạo ở sai schema | defaultSchema/catalog hoặc quyền không đúng | Xác minh cấu hình bảng lịch sử và tài khoản |
| Baseline thiếu procedure/trigger/grant | Snapshot không thu thập đủ object | Bổ sung object được quản lý và kiểm thử quyền |
| Migration mới bị áp dụng hai lần | Công cụ cũ còn chạy hoặc identity Liquibase bị đổi | Dừng runner cạnh tranh, bảo toàn id/author/filename |
| Rollback không khôi phục dữ liệu cũ | Script cũ đã xóa/chuyển dữ liệu mà không lưu snapshot | Dùng backup/PITR hoặc forward fix, không tạo rollback giả |
| Không biết script nào đã chạy | Thiếu lịch sử hoặc log thủ công | Đánh dấu unknown, điều tra từng môi trường trước baseline |

Khi gặp lỗi, ưu tiên xác định database, revision, lịch sử cũ, schema thực và chủ thể đã chạy thay đổi. Không xóa history để làm pipeline “xanh” trở lại.

## 30. Checklist nghiệm thu chuyển giao

- [ ] Phạm vi database/schema và owner đã được xác định.
- [ ] Đã kiểm kê SQL scripts, công cụ cũ, job, ORM auto-DDL và thay đổi thủ công.
- [ ] Có mapping lịch sử theo từng môi trường/database.
- [ ] Đã phân biệt history tool với schema/data hiện tại.
- [ ] Đã xác định chiến lược baseline hoặc chuyển từng migration.
- [ ] Baseline bao phủ đủ object thuộc phạm vi: bảng, cột, constraint, index, view, routine, sequence, trigger và grant.
- [ ] Data migration, backfill và reference data được xác minh riêng.
- [ ] Changelog identity ổn định: id, author, filename/logicalFilePath.
- [ ] Đã review file sinh từ generate-changelog/diff-changelog.
- [ ] Changelog-sync chỉ được dùng khi mọi kết quả được đánh dấu đã có sẵn và được kiểm chứng.
- [ ] Không sync changeset có thao tác hoặc data migration còn thiếu.
- [ ] Mỗi môi trường có ma trận trạng thái và kế hoạch reconcile.
- [ ] Có một chủ thể migration duy nhất sau cutover.
- [ ] Flyway/script runner/ORM auto-DDL cũ đã được dừng theo kế hoạch.
- [ ] Liquibase version, driver, changelog master, schema history và quyền đã được ghim/kiểm tra.
- [ ] Đã thử trên clone có lịch sử và dữ liệu đại diện.
- [ ] Đã kiểm tra validate, status, SQL preview, DATABASECHANGELOG và schema thực tế.
- [ ] Có backup/PITR và runbook phục hồi đã kiểm chứng.
- [ ] Đã thử một thay đổi mới sau baseline để chứng minh Liquibase tiếp quản.
- [ ] Ứng dụng Spring Boot và pipeline dùng cùng revision, không chạy migration cạnh tranh.
- [ ] Lưu archive lịch sử cũ, quyết định cutover, người phê duyệt và bằng chứng hậu kiểm.

**Ghi nhớ:** Chuyển giao sang Liquibase cần đồng bộ **lịch sử công cụ, trạng thái schema/data và quyền thực thi migration**. Baseline mô tả điểm bắt đầu; `changelog-sync` chỉ ghi nhận những thay đổi đã có mà không thực thi chúng; changeset mới quản lý mọi thay đổi sau cutover. Chỉ chuyển quyền khi từng database đã được đối chiếu, tool cũ đã ngừng ghi, Liquibase có một chủ thể triển khai rõ ràng và quy trình rollback/forward fix đã được diễn tập. Đó là nền tảng để quản lý thay đổi schema và dữ liệu có kiểm chứng, nhất quán giữa các môi trường và tích hợp an toàn với Spring Boot hoặc CI/CD.

