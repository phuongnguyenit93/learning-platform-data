# Đọc kết quả lệnh, mã thoát và nhật ký thực thi Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, người học cần quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường, đồng thời tích hợp Spring Boot hoặc CI/CD. Ở chương **Kiểm tra và cập nhật**, việc hiểu **kết quả lệnh, mã thoát (exit code) và nhật ký thực thi (execution log)** quyết định liệu một đợt migration có thể được xác nhận thành công, cần dừng phát hành hay phải điều tra trạng thái database thực tế.

**Nguyên tắc trọng tâm:** kết quả được in ra màn hình, mã thoát của tiến trình và trạng thái database là **ba nguồn tín hiệu khác nhau**. Chúng bổ sung cho nhau; không được xem một dòng thông báo “success” hoặc mã thoát 0 là bằng chứng duy nhất rằng schema và dữ liệu đã đáp ứng yêu cầu nghiệp vụ.

## 1. Mục tiêu và mô hình đọc kết quả

Sau bài học, bạn có thể:

1. Phân biệt kết quả chuẩn đầu ra, đầu ra lỗi, mức độ ghi log và exit code của Liquibase CLI.
2. Hiểu một lệnh validate, status, update-sql, update hoặc history thực sự kiểm tra và thực hiện điều gì.
3. Nhận biết khác biệt giữa **lệnh thành công**, **changeset được ghi nhận** và **đối tượng/dữ liệu thực tế đúng**.
4. Điều tra các lỗi như checksum mismatch, lock, precondition, SQL, kết nối và thiếu quyền.
5. Xây dựng cổng kiểm tra CI/CD không nuốt lỗi, không tiết lộ credentials hay dữ liệu nhạy cảm.
6. Đối chiếu log ứng dụng Spring Boot với log và lịch sử Liquibase, rồi lập biên bản triển khai có thể kiểm toán.

Mô hình ba lớp:

~~~text
Lớp 1: Quy trình thực thi
  Lệnh nào được gọi? Mã thoát? stdout / stderr / log?
                         |
                         v
Lớp 2: Lịch sử Liquibase
  Changeset nào pending, EXECUTED, RERAN, MARK_RAN?
  Checksum, thời điểm, kết quả, lock?
                         |
                         v
Lớp 3: Database và ứng dụng
  Bảng/cột/index thực tế đúng chưa? Dữ liệu đủ chưa?
  Hậu điều kiện và smoke test ứng dụng có đạt không?
~~~

Một lớp đạt không bảo đảm hai lớp còn lại đạt. Ví dụ, **validate thành công không có nghĩa update đã chạy**; **update thành công không có nghĩa bảng dự kiến tồn tại ở đúng schema** nếu runner kết nối nhầm database hoặc changeset bị lọc.

## 2. Các loại thông tin Liquibase cung cấp

Khi sử dụng Liquibase CLI, có ít nhất bốn kênh cần xem:

| Kênh | Dấu hiệu | Cách dùng |
|---|---|---|
| **stdout** | Nội dung in ra đầu ra chuẩn | Thông báo tiến trình, kết quả lệnh, nội dung SQL preview tùy lệnh và cấu hình |
| **stderr** | Nội dung in ra đầu ra lỗi | Thường dùng cho thông báo lỗi; không phải cứ có stderr là luôn có lỗi nghiêm trọng |
| **Exit code** | Số nguyên tiến trình trả về cho shell/CI | Tín hiệu máy đọc được để quyết định tiếp tục hoặc dừng pipeline |
| **Log file / logging framework** | Các sự kiện ở mức INFO, WARNING, chi tiết hơn tùy cấu hình | Điều tra nguyên nhân, thứ tự thực thi, vị trí lỗi và mối liên hệ giữa các bước |

Không suy ra kết quả chỉ từ việc một dòng nằm ở stdout hay stderr. Cách log hiển thị thay đổi theo **phiên bản Liquibase, driver JDBC, nền tảng shell, trình bao gọi lệnh và cấu hình logging**. Nên xác định trạng thái bằng exit code và bằng chứng trên database thay vì chỉ tìm một chuỗi cố định trong console.

### 2.1. Những thông tin nào nên thu thập khi đọc log?

Với mỗi lần migration, cố gắng trả lời:

- **Đối tượng đích:** DBMS, host/database, catalog, schema ứng dụng, schema chứa bảng metadata Liquibase; trình bày dạng đã che thông tin nhạy cảm.
- **Nguồn thay đổi:** changelog path, artifact/version, commit/tag phát hành.
- **Chế độ chạy:** validate, status, update-sql, update, history hay rollback; bộ lọc context và label.
- **Thời điểm:** bắt đầu/kết thúc, timezone, thời gian chạy và khoảng thời gian bất thường.
- **Nội dung:** changeset id/author/file path, thay đổi pending, đã chạy, bị bỏ qua hoặc được đánh dấu đã xử lý.
- **Tín hiệu:** exit code, lỗi đầu tiên có ý nghĩa, nguyên nhân gốc, SQL/constraint cụ thể.
- **Kết quả vật lý:** schema/data sau migration và hậu điều kiện đã kiểm tra.

Không lưu lại mật khẩu, token, JDBC URL có thông tin xác thực hoặc toàn bộ payload SQL chứa dữ liệu cá nhân trong báo cáo để “đủ log”.

## 3. Đọc mã thoát (exit code) chính xác

Với một chương trình CLI thông thường:

- **0:** tiến trình báo hoàn tất thành công theo tiêu chí của lệnh đã gọi.
- **Khác 0:** chương trình báo lỗi hoặc dừng không thành công; pipeline phải xem đây là tín hiệu cần điều tra.

Không cần thuộc lòng một bảng mã lỗi cố định cho Liquibase: ý nghĩa và mã số cụ thể có thể phụ thuộc phiên bản, command runner hoặc lỗi Java/JDBC. **Không gán một mã số bất kỳ cho “checksum mismatch”, “lock” hay “thiếu quyền” nếu chưa có tài liệu chính xác cho phiên bản đang dùng.**

### 3.1. Mã thoát 0 không đồng nghĩa “migration mới đã chạy”

Các trường hợp cùng có thể trả về thành công:

- validate thành công, nhưng không chạy migration nào;
- status hoàn tất việc liệt kê changeset pending;
- update-sql tạo ra SQL preview mà không triển khai DDL/DML dự kiến;
- update chạy và áp dụng một hoặc nhiều changeset;
- update chạy nhưng **không có changeset mới cần áp dụng**;
- history truy xuất lịch sử thành công.

Do đó, cần nhìn **lệnh đã gọi** và **số changeset thực thi thực tế**. Không báo “đã deploy schema mới” chỉ vì lệnh validate có exit code 0.

### 3.2. Khi lệnh thất bại nhưng database đã bị thay đổi một phần

Một số DBMS tự commit DDL hoặc có những lệnh không chạy được trong transaction. Với changeset runInTransaction: false, một câu SQL có thể đã hoàn thành trước khi câu tiếp theo thất bại. Khi đó CLI trả lỗi nhưng database có thể đã thay đổi một phần.

Quy trình an toàn sau exit code khác 0:

1. Dừng bước tiếp theo của deployment.
2. Không mặc định tự động chạy lại toàn bộ job.
3. Kiểm tra log để xác định changeset và SQL thất bại.
4. Đối chiếu DATABASECHANGELOG với schema/data thật, cùng khả năng transaction của DBMS.
5. Chỉ retry sau khi đã chọn kế hoạch phục hồi hoặc sửa chữa có kiểm chứng.

**Không chỉnh tay DATABASECHANGELOG, MD5SUM hoặc DATABASECHANGELOGLOCK để biến trạng thái thành “thành công”.**

## 4. Đọc mã thoát trong shell và pipeline

### 4.1. Bash và hệ shell tương thích POSIX

Ví dụ khi kết nối Liquibase đã được cấu hình qua nguồn bảo mật:

~~~bash
liquibase validate
code=$?

printf 'validate exit code: %s\n' "$code"

if [ "$code" -ne 0 ]; then
  echo "Liquibase validation failed" >&2
  exit "$code"
fi
~~~

Phải lấy **$? ngay sau lệnh cần kiểm tra**. Nếu chạy echo, grep hoặc một chương trình khác trước, $? sẽ mang exit code của chương trình mới nhất, không còn là của Liquibase.

Một cách dùng trong pipeline:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

set -e giúp script dừng trong nhiều tình huống lệnh lỗi; set -u phát hiện biến chưa định nghĩa; pipefail làm pipeline có thể phản ánh lỗi của lệnh ở giữa chuỗi pipe. Tuy nhiên, các quy tắc set -e có ngoại lệ trong if, command substitution và một số ngữ cảnh shell. Với các bước quyết định phát hành, nên kiểm tra exit code tường minh hoặc chạy script được kiểm thử.

### 4.2. Không để tee/grep che lỗi Liquibase

Ví dụ nguy hiểm:

~~~bash
liquibase update | tee liquibase-output.log
~~~

Trong một số shell, exit code của pipeline mặc định là exit code của **tee**, nên Liquibase có thể thất bại nhưng pipeline vẫn thành công.

Với Bash:

~~~bash
set -o pipefail
liquibase update 2>&1 | tee liquibase-output.log
code=$?
exit "$code"
~~~

Dấu 2>&1 gộp stderr vào stdout trước khi chuyển đến tee. File log được tạo bởi ví dụ này là một **artifact của pipeline thực tế**, không phải yêu cầu tạo file phụ trong bài học. Trong production, phải kiểm soát quyền đọc và retention của log vì có thể chứa SQL hoặc thông tin kết nối.

Cũng không nên xác định thành công bằng lệnh grep tìm chữ success. Log có thể thay đổi cách diễn đạt, và một lần chạy thất bại có thể chứa thông báo “success” của bước trước.

### 4.3. Windows PowerShell

Khi gọi một chương trình native như Liquibase CLI từ PowerShell, đọc $LASTEXITCODE ngay sau lần gọi:

~~~powershell
liquibase validate
$liquibaseCode = $LASTEXITCODE

Write-Host "Liquibase validate exit code: $liquibaseCode"

if ($liquibaseCode -ne 0) {
    exit $liquibaseCode
}
~~~

Không lẫn $LASTEXITCODE với biến $?: $? thể hiện trạng thái thành công của câu lệnh gần nhất trong PowerShell, còn $LASTEXITCODE thường dùng để lấy mã trả về của chương trình native. Nếu chạy một command khác giữa hai bước, hãy lưu mã trước.

### 4.4. Khi runner bắt exception thay vì dùng exit code

Nếu Liquibase được gọi qua **Java API, Gradle/Maven plugin hoặc Spring Boot**, wrapper có thể bắt exception và tự quyết định mã thoát của tiến trình cha. Không phải mọi lỗi bên trong Liquibase đều tự động đến được CI như một mã khác 0 nếu wrapper nuốt lỗi hoặc chạy dạng best-effort.

Nguyên tắc: lỗi migration bắt buộc phải được **propagate** tới hệ điều phối và đánh dấu job thất bại. Không bắt exception rồi log một dòng WARNING và tiếp tục cho ứng dụng khởi động như không có vấn đề, trừ khi đó là hành vi được thiết kế, đánh giá rủi ro và giám sát có chủ đích.

## 5. Đọc kết quả các lệnh kiểm tra phổ biến

Các ví dụ bên dưới giả định Liquibase đã có URL, credentials, changelog và bộ lọc môi trường phù hợp. Cấu hình có thể đến từ CLI options, defaults file, biến môi trường hoặc tích hợp ứng dụng, nhưng **không đưa mật khẩu thật vào command history**.

### 5.1. validate: kiểm tra định nghĩa và lịch sử

~~~bash
liquibase validate
~~~

Cần hiểu:

- Lệnh kiểm tra tính hợp lệ của changelog và các điều kiện validation do Liquibase hỗ trợ, bao gồm các trường hợp checksum không nhất quán trên changeset đã ghi nhận.
- Lệnh **không thực thi changeset pending**.
- Exit code 0 có nghĩa validation vượt qua phạm vi kiểm tra; **không chứng minh câu SQL đặc thù DBMS sẽ chạy được**, dữ liệu hợp lệ hoặc schema không drift.
- Nếu lỗi, tìm changeset id, author, file, vị trí cấu hình và nội dung chẩn đoán đầu tiên có ý nghĩa.

Ví dụ thông điệp **minh họa**, không phải chuỗi đầu ra chính xác cho mọi phiên bản:

~~~text
[INFO] Reading changelog db/changelog/master.yaml
[INFO] Validation completed successfully
Process exit code: 0
~~~

Một log validation thành công cần được đọc cùng kết quả status, SQL preview và kiểm tra schema/data, không dùng riêng để tuyên bố deployment đã hoàn tất.

### 5.2. status --verbose: điều gì còn pending?

~~~bash
liquibase status --verbose
~~~

Mục đích là xem những changeset Liquibase xác định **chưa được triển khai theo changelog, database và bộ lọc hiện tại**.

Có hai tình huống cần tách:

- Có changeset pending: kiểm tra danh sách id/author/file path và xem chúng có đúng với bản phát hành không.
- Không có changeset pending: có thể đúng vì mọi thay đổi đã áp dụng; cũng có thể do runner trỏ sai database, dùng sai changelog hoặc context/label lọc mất changeset mong muốn.

**Không có changeset pending không phải tự thân là lỗi**, và không chứng minh một thay đổi mới đã được phát hành. Khi kỳ vọng có migration mà status trả về rỗng, phải kiểm tra cấu hình và lịch sử trước khi chạy lại.

### 5.3. update-sql: xem kế hoạch trước khi chạy

~~~bash
liquibase update-sql
~~~

Lệnh này tạo ra các câu SQL dự kiến cho update theo cấu hình hiện tại. Cần kiểm tra:

1. Schema/catalog và tên đối tượng đúng.
2. DDL, DML, constraint, index hoặc đối tượng được tạo/xóa như mong đợi.
3. Không có câu DROP/DELETE hoặc thao tác phá hủy ngoài phạm vi được phê duyệt.
4. Giá trị changelog properties đã được phân giải đúng.
5. Thứ tự changeset phù hợp dependency và precondition.
6. SQL đặc thù DBMS có cú pháp được engine đích hỗ trợ.
7. Câu SQL có chứa dữ liệu cá nhân, secret hoặc literal nhạy cảm không.

**update-sql không thay thế update.** Kết quả preview không xác nhận câu SQL sẽ thực thi thành công trên dữ liệu thực, không bảo đảm hành vi lock và transaction, và không xác nhận hậu điều kiện.

Đối với một số precondition hoặc thay đổi phụ thuộc trạng thái database, kết quả preview cần được hiểu trong ngữ cảnh dữ liệu và cấu hình hiện tại; không xem script preview là một bản mô phỏng chính xác mọi tác động runtime.

### 5.4. update: thực thi migration

~~~bash
liquibase update
~~~

Khi chạy update, cần phân biệt:

- Các changeset được lựa chọn và chuẩn bị.
- Các changeset thực sự được thực thi thành công.
- Những changeset đã ghi nhận từ trước và được bỏ qua.
- Những changeset được đánh dấu MARK_RAN do quy tắc thích hợp mà SQL chưa hề chạy.
- Những changeset runOnChange/runAlways được thực thi lại theo cấu hình.
- Những thay đổi bị dừng vì validation, precondition, lock, SQL hoặc kết nối.

Không suy luận từ một con số “completed” hoặc “processed” nếu chưa biết phiên bản Liquibase dùng định nghĩa nào. Nếu phiên bản hỗ trợ update summary, hãy đọc **số đã chạy, số được lọc, số đã có và loại thực thi**; đối chiếu với danh sách pending trước khi triển khai.

Ví dụ log **minh họa**, không cam kết format thực tế:

~~~text
[INFO] Starting update for database commerce_stage
[INFO] Running changeset: db/changelog/017-index.yaml::017-index-orders::db-team
[INFO] ChangeSet executed
[INFO] Update command completed
Process exit code: 0
~~~

Log như trên chỉ là bằng chứng Liquibase báo đã thực thi. Cần kiểm tra index thực tế ở schema mong đợi, tình trạng hợp lệ của index và hậu điều kiện ứng dụng.

### 5.5. history: kiểm tra những gì đã ghi nhận

~~~bash
liquibase history
~~~

history hữu ích để xem Liquibase đã ghi nhận những changeset nào trên database hiện tại. Nó **không phải** bản sao chính xác của mọi DDL/DML đã thực sự chạy: nếu changeset MARK_RAN, nội dung có thể không thực thi; nếu có thao tác thủ công ngoài Liquibase, history không biết; nếu một DDL thất bại sau khi commit một phần, trạng thái thực tế có thể khác lịch sử.

Khi điều tra, kết hợp history với truy vấn DATABASECHANGELOG và metadata schema cụ thể.

## 6. Cách đọc một bản ghi DATABASECHANGELOG

Liquibase duy trì lịch sử trong bảng **DATABASECHANGELOG** (tên và vị trí có thể được cấu hình khác với mặc định). Một truy vấn SQL minh họa trên DBMS hỗ trợ cú pháp tương ứng:

~~~sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM,
       DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED DESC;
~~~

Nếu hệ thống đặt bảng metadata trong schema riêng, truy vấn phải trỏ đúng schema đó. Các cột có thể thay đổi theo phiên bản Liquibase hoặc quy tắc đặt tên/case của DBMS; hãy xác nhận schema thật trước khi đưa truy vấn vào công cụ vận hành.

| Trường | Ý nghĩa chẩn đoán |
|---|---|
| ID | Mã changeset |
| AUTHOR | Người/nhóm khai báo changeset |
| FILENAME | Đường dẫn logic của changelog được dùng trong định danh |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận lần thực thi theo cơ chế của database |
| ORDEREXECUTED | Thứ tự thực thi/ghi nhận theo lịch sử của database |
| EXECTYPE | Kiểu trạng thái thực thi được ghi nhận, chẳng hạn EXECUTED, RERAN, MARK_RAN |
| MD5SUM | Checksum đã ghi nhận, dùng để phát hiện khác biệt định nghĩa changeset |
| DEPLOYMENT_ID | Giá trị hỗ trợ nhóm các changeset được thực thi trong cùng lượt triển khai theo cơ chế Liquibase |

### 6.1. EXECUTED, RERAN và MARK_RAN

- **EXECUTED:** changeset được Liquibase ghi nhận đã thực thi.
- **RERAN:** một changeset có cơ chế chạy lại phù hợp được thực thi thêm lần nữa, tùy quy tắc của phiên bản/changelog.
- **MARK_RAN:** Liquibase ghi nhận changeset là đã chạy theo cơ chế được chọn **mà không thực thi SQL nghiệp vụ tương ứng**.

Đây là khác biệt quan trọng: **MARK_RAN không đồng nghĩa đối tượng dự kiến đã được tạo**. Nếu một precondition dùng onFail: MARK_RAN, cần kiểm tra vì sao được đánh dấu và liệu schema đã có trạng thái tương ứng hay chưa.

Một số kiểu trạng thái khác có thể được ghi nhận tùy phiên bản và tính năng. Không mặc định một hàng FAILED luôn tồn tại nếu SQL gặp lỗi: một thay đổi bị rollback transaction hoặc thất bại giữa chừng có thể không được ghi nhận hoàn tất theo cách dễ dự đoán từ log.

### 6.2. Không đồng nhất checksum với trạng thái schema

MD5SUM giúp kiểm tra tính nhất quán của định nghĩa changeset, **không phải checksum của toàn bộ database**. Một DBA có thể chỉnh trực tiếp bảng sau migration; MD5SUM của changeset vẫn khớp. Khi log xác nhận checksum đúng nhưng ứng dụng báo thiếu cột, phải kiểm tra schema và thay đổi ngoài Liquibase.

Không sửa SQL trong một changeset đã chạy để “sửa lỗi cho nhanh”. Giữ lịch sử bất biến và thêm changeset điều chỉnh, trừ trường hợp được thiết kế từ đầu để chạy lại như runOnChange với đối tượng thích hợp.

## 7. Đọc trạng thái khóa bằng DATABASECHANGELOGLOCK

Liquibase dùng **DATABASECHANGELOGLOCK** để điều phối việc chạy migration trên cùng bộ metadata. Khi log báo không lấy được lock hoặc phải chờ quá lâu, cần xem tiến trình khác đang chạy hay không.

Ví dụ truy vấn chỉ đọc:

~~~sql
SELECT ID,
       LOCKED,
       LOCKGRANTED,
       LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Các trường thường giúp biết lock đang được đánh dấu hay không, thời điểm và thông tin tiến trình giữ lock. Cần đối chiếu thêm log CI, process đang chạy, kết nối database và các tác vụ migration do Spring Boot tự khởi động.

**Không xóa dòng lock, update LOCKED trực tiếp hay chạy release-locks ngay chỉ vì thấy lock lâu.** Một tiến trình migration thực sự còn hoạt động có thể đang thay đổi schema; ép giải phóng khóa có thể khiến hai tiến trình chạy cùng lúc.

Quy trình khi nghi lock bị bỏ quên:

1. Xác định job/instance nào đang chạy và thời điểm bắt đầu.
2. Kiểm tra DB session, DDL đang thực thi và tình trạng transaction.
3. Xác nhận tiến trình gốc thực sự đã kết thúc và không còn thao tác dở dang.
4. Xác minh database/schema hiện tại, lịch sử và kế hoạch retry.
5. Chỉ dùng công cụ giải phóng khóa được Liquibase hỗ trợ theo quy trình vận hành được phê duyệt.
6. Sau giải phóng, kiểm tra lại lock và thực hiện bước validate/status trước khi update.

Lock là cơ chế điều phối, không phải cơ chế sửa checksum hoặc tự phục hồi mọi DDL dang dở.

## 8. Nhận diện lỗi qua các dấu hiệu trong log

Các ví dụ dưới đây là **nhóm dấu hiệu**, không phải chuỗi log cố định hoặc mã lỗi quy định cho mọi bản Liquibase.

| Nhóm lỗi | Dấu hiệu thường thấy | Nên kiểm tra |
|---|---|---|
| Changelog sai cấu trúc | Parse/validation error, không xác định được change type | File, YAML/XML/SQL format, vị trí lỗi, phiên bản Liquibase |
| Checksum mismatch | Validation Failed, checksum đã lưu khác hiện tại | Changeset id/author/path, commit cũ, nội dung đã sửa, MD5SUM |
| Trùng định danh changeset | Duplicate changeset identifier | id, author, đường dẫn logic sau include/move file |
| Kết nối database | Connection refused, timeout, authentication failed | URL, DNS, network, TLS, credential, driver, DBMS |
| Thiếu quyền | Permission denied, insufficient privileges | Tài khoản migration, schema, quyền DDL/DML/sequence |
| Lỗi SQL | Syntax error, object already exists, constraint violation | SQL được sinh, DBMS/version, dữ liệu thực, transaction |
| Precondition | Precondition failed/error | Điều kiện, onFail/onError, dữ liệu, context/label |
| Lock | Waiting for changelog lock, cannot acquire lock | Job đang chạy, LOCKED/LOCKGRANTED/LOCKEDBY |
| Không thấy changeset pending | Status rỗng trong khi dự kiến có migration | Database sai, changelog sai, filter sai, history đã có |
| Rollback thất bại | SQL đảo ngược lỗi, dependency hoặc dữ liệu không còn | Phạm vi rollback, SQL, khả năng phục hồi, backup |
| Lỗi ghi log/artifact | Không tạo được log file hoặc mất stdout | Quyền filesystem, redirect, dung lượng, runner |

### 8.1. Đọc lỗi từ dưới lên hay từ trên xuống?

Trong stack trace Java, lỗi bọc ngoài có thể là “LiquibaseException”, bên trong là DatabaseException, và sâu hơn nữa là lỗi JDBC của DBMS. Nên:

1. Đọc thông điệp đầu tiên chỉ ra lệnh/changeset đang chạy.
2. Xác định **root cause** có ý nghĩa (ví dụ constraint cụ thể, SQLSTATE hoặc permission).
3. Đối chiếu SQL và đối tượng bị lỗi.
4. Xác định SQL đã thực thi một phần hay chưa.
5. Kết luận phương án sửa thay vì chỉ sao chép toàn bộ stack trace.

Không chỉ tìm từ “ERROR” cuối log và bỏ qua phần liên quan đến changeset hoặc DBMS phía trên.

### 8.2. Checksum mismatch không phải lỗi kết nối

Nếu validate báo checksum không khớp, database đã cung cấp được lịch sử để đối chiếu. Cần kiểm tra có ai sửa changeset đã triển khai, thay id/author/path, di chuyển file, đổi phiên bản Liquibase hoặc thay đổi thuật toán/định dạng hay không.

**Không dùng clear-checksums như phản xạ đầu tiên.** Lệnh này không sửa schema và có thể làm mất tín hiệu phát hiện thay đổi lịch sử. Ưu tiên khôi phục changeset cũ, thêm changeset mới; chỉ áp dụng cơ chế chấp nhận checksum khi có bằng chứng và phê duyệt phù hợp.

### 8.3. Precondition thất bại: phân biệt HALT, CONTINUE, MARK_RAN

Precondition có thể được cấu hình để dừng, bỏ qua theo quy tắc hoặc đánh dấu changeset đã xử lý. Khi đọc log, phải xác định **onFail** và **onError** của changeset, cũng như trạng thái thực tế của database.

Nếu onFail: HALT, migration có thể dừng có chủ đích để bảo vệ dữ liệu. Nếu MARK_RAN, SQL có thể chưa chạy. Với migration bắt buộc, một lần update không lỗi nhưng có changeset MARK_RAN không được tự động xem là đạt yêu cầu; cần xem lý do và hậu điều kiện.

## 9. Ghi log đủ để điều tra nhưng không làm lộ dữ liệu

CLI thường hỗ trợ các tùy chọn như log level và log file. Ví dụ minh họa khi đường dẫn lưu log đã được phê duyệt:

~~~bash
liquibase --log-level=INFO --log-file=liquibase-run.log validate
~~~

Chú ý:

- Tên/tính sẵn có của tùy chọn và mức log cần kiểm tra theo phiên bản Liquibase trong dự án.
- Mức INFO thường hữu ích cho vận hành; mức chi tiết hơn chỉ nên bật khi cần điều tra trên môi trường có kiểm soát.
- Lệnh trên không cần mật khẩu xuất hiện trực tiếp trong tham số; credentials nên đến từ nguồn bí mật được quản lý.
- Log file có thể chứa đường dẫn, tên database, câu SQL hoặc thông tin nhạy cảm; phải hạn chế quyền đọc, thời hạn lưu và nơi upload.
- Khi ghi log CI/CD, cần che thông tin xác thực và tránh in toàn bộ INSERT/UPDATE có dữ liệu thật.

### 9.1. Phân loại mức độ log

| Mức khái niệm | Mục đích | Ví dụ thông tin |
|---|---|---|
| Lỗi nghiêm trọng | Báo sự cố cần dừng hoặc xử lý | SQL lỗi, không kết nối được, validation thất bại |
| Cảnh báo | Dấu hiệu cần xem xét | Tùy chọn bị bỏ qua, bất thường cấu hình, điều kiện vận hành |
| Thông tin vận hành | Theo dõi tiến trình | Changelog, thay đổi đang xử lý, thời gian hoàn tất |
| Chi tiết/debug | Điều tra sâu | Thành phần nội bộ, SQL, cấu hình, stack trace |

Các tên mức log cụ thể không đồng nhất giữa mọi logger. Không khẳng định có một tập tên hoặc định dạng JSON cố định nếu chưa xác định phiên bản Liquibase và logging backend.

### 9.2. Log không phải nguồn chân lý duy nhất

Một file log có thể bị thiếu do process bị kill, disk đầy hoặc CI timeout. Ngược lại, một dòng “changeset succeeded” có thể xuất hiện trước khi một bước tiếp theo của cùng deployment thất bại. Vì vậy, log cần được đối chiếu với **exit code, lịch sử DATABASECHANGELOG và truy vấn thực tế**.

Không chỉnh sửa bản ghi lịch sử để làm “khớp log”. Nếu log thiếu, đánh dấu bằng chứng chưa đủ và tái dựng trạng thái từ metadata và DBMS một cách có kiểm chứng.

## 10. Bản ghi triển khai có thể kiểm toán

Đối với một đợt production, nên có một biên bản tối thiểu:

~~~text
Deployment:
  Application/version: service-orders 2.x.y
  Artifact/commit: <commit-id>
  Liquibase version: <actual-version>
  DBMS/database: PostgreSQL / commerce-prod (redacted host)
  Changelog: db/changelog/master.yaml
  Context/labels: prod / <configured-labels>
  Start/end: <UTC timestamps>
  Commands: validate -> status -> update-sql -> update -> history
  Exit code of each command: <captured code>
  Planned changesets: <count and IDs>
  Executed/marked/rerun changesets: <verified details>
  Deployment ID: <if available>
  Schema/data postconditions: PASS/FAIL with evidence
  Application smoke test: PASS/FAIL
  Approver / incident reference: <reference if applicable>
~~~

Đây là **mẫu biên bản**, không phải định dạng đầu ra có sẵn của Liquibase. Dùng giá trị từ công cụ và database thật, không tự điền số hoặc kết luận khi chưa kiểm chứng.

### 10.1. Tại sao cần lưu artifact và commit?

Nếu migration ở staging chạy thành công nhưng production gặp checksum mismatch, cần biết chính xác **cùng một changelog đã được đóng gói hay chưa**. Chỉ có tên file là chưa đủ khi file đã thay đổi theo commit.

Các trường id, author, filename và checksum liên kết history với source control. Một artifact bất biến giúp điều tra migration nào được phát hành, thông số nào được dùng và những khác biệt từ ngoài Liquibase.

### 10.2. Log timestamps và múi giờ

CI runner, JVM và database có thể dùng múi giờ khác nhau. Nên lưu timestamp theo UTC trong biên bản vận hành và ghi rõ timezone khi báo cáo địa phương. Không chỉ nhìn thời gian hiển thị trong log để kết luận một changeset đã chạy trước hay sau nếu các nguồn không đồng bộ.

## 11. Tình huống thực tế A: update báo thành công nhưng không có thay đổi mới

Giả sử pipeline kỳ vọng có changeset 021-add-index. Lệnh update kết thúc exit code 0 nhưng không thấy index. Các khả năng:

1. Pipeline đang trỏ tới database khác.
2. Root changelog được dùng không include file chứa changeset.
3. Context/label hoặc dbms lọc mất changeset.
4. Changeset được đánh dấu MARK_RAN do precondition.
5. DATABASECHANGELOG ghi nhận changeset đã chạy, nhưng schema thực tế bị sửa thủ công.
6. Index được tạo ở schema khác với schema đang kiểm tra.
7. Update chưa thực sự được gọi; pipeline chỉ chạy validate hoặc update-sql.

Quy trình:

~~~text
Kiểm tra job thực sự gọi update?
                 |
                 v
Xác nhận DB URL + schema + changelog effective
                 |
                 v
status --verbose với cùng filter
                 |
                 v
history / DATABASECHANGELOG
                 |
                 v
Kiểm tra catalog/index trên database đúng
                 |
                 v
Kết luận: filtered, MARK_RAN, drift, wrong target
hoặc migration chưa nằm trong artifact
~~~

**Không chạy lại bằng cách xóa dòng DATABASECHANGELOG.** Khi thiếu index vì drift, cần lập changeset sửa chữa có kiểm chứng; khi sai bộ lọc hoặc artifact, sửa pipeline rồi review kế hoạch trước khi update.

## 12. Tình huống thực tế B: update trả lỗi ở giữa batch

Giả sử changeset A thêm cột thành công, changeset B cập nhật dữ liệu thất bại và changeset C chưa chạy.

Không thể kết luận đơn giản là “toàn bộ migration chưa chạy”. Tùy DBMS và transaction, A có thể đã commit và B có thể đã thay đổi một phần. Cần:

1. Lưu exit code khác 0 và dừng release.
2. Đọc log để xác định ranh giới giữa A/B/C.
3. Kiểm tra DATABASECHANGELOG cho A/B/C.
4. Kiểm tra schema và dữ liệu thực tế, đặc biệt những thay đổi DDL đã commit.
5. Xác định transaction và runInTransaction của changeset.
6. Kiểm tra lock và session vẫn chạy.
7. Chọn rollback được kiểm chứng hoặc forward-fix.
8. Chỉ retry bằng artifact phù hợp sau khi đã hiểu trạng thái.

Nếu B là SQL UPDATE lớn, một rollback “đặt lại giá trị” có thể không khôi phục được dữ liệu trước migration. Cần backup hoặc kế hoạch sửa tiến về phía trước; không coi một lần rerun tự động là đủ.

## 13. Tình huống thực tế C: lock và nhiều instance Spring Boot

Một hệ thống Spring Boot có ba instance cùng khởi động, mỗi instance bật Liquibase. Log của một instance cho thấy đang chờ changelog lock. Điều này không tự động là lỗi; một instance khác có thể đang thực thi migration.

Phân biệt:

- **Chờ hợp lệ:** một instance đang chạy update; những instance khác chờ theo cơ chế lock.
- **Chờ bất thường:** process gốc bị mất nhưng metadata còn khóa; hoặc tiến trình migration rất lâu do DDL/lock của DBMS.
- **Sai cấu hình:** các instance dùng root changelog/schema metadata khác nhau hoặc kết nối nhầm database.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
    contexts: prod
~~~

Trong ứng dụng Java, lỗi Liquibase có thể xuất hiện dưới dạng exception khi khởi tạo Spring context, với thông điệp từ lớp Liquibase và nguyên nhân JDBC sâu hơn. Cần đọc **chuỗi cause**, log của instance đang giữ lock và trạng thái DATABASECHANGELOGLOCK.

Nếu hệ thống có CI/CD, một thiết kế thường dễ kiểm soát hơn là chạy migration bằng **job chuyên trách** trước khi rollout ứng dụng, rồi cấu hình runtime không tự chạy migration nếu phù hợp kiến trúc. Khi đó pipeline phải kiểm tra exit code của migration job và chỉ triển khai instance mới khi hậu điều kiện đạt.

## 14. CI/CD: cổng kiểm tra dựa trên tín hiệu nào?

Một pipeline an toàn cần có nhiều cổng:

~~~text
Artifact được phê duyệt
        |
        v
Xác minh DB đích / schema / phiên bản changelog
        |
        v
validate -> exit code 0?
        | no: STOP
        v
status --verbose -> pending đúng kế hoạch?
        | no: REVIEW
        v
update-sql -> SQL đúng mục tiêu?
        | no: STOP
        v
Phê duyệt vận hành / thay đổi phá hủy
        |
        v
update -> exit code 0?
        | no: STOP + INVESTIGATE PARTIAL STATE
        v
history + DATABASECHANGELOG / LOCK
        |
        v
Schema/data postconditions + application smoke test
        | no: INCIDENT / FORWARD-FIX
        v
Release PASS
~~~

### 14.1. Ví dụ Bash cho các bước bắt buộc

~~~bash
#!/usr/bin/env bash
set -euo pipefail

echo "Step 1: validate"
liquibase validate

echo "Step 2: inspect pending changes"
liquibase status --verbose

echo "Step 3: preview SQL"
liquibase update-sql

# Chỉ bước đã phê duyệt mới được gọi update.
echo "Step 4: apply approved migration"
liquibase update

echo "Step 5: inspect history"
liquibase history

# Hậu điều kiện schema/data và smoke test phải được chạy riêng.
~~~

Đoạn này minh họa luồng, **không tự bảo đảm** update-sql được review bởi con người, DB đích đúng hoặc hậu điều kiện đã kiểm tra. Trong CI/CD thực tế, cần các bước kiểm soát quyền, thay đổi phá hủy, config và xác nhận test riêng.

Nếu chạy nhiều lệnh trong một job, không dùng mẫu “liquibase update; echo success” mà không kiểm tra exit code. Đừng tạo điều kiện always() hoặc continue-on-error cho migration bắt buộc rồi vẫn phát hành nếu nó đã thất bại.

### 14.2. Khi cần dùng log trong CI/CD

Nên ghi các thông tin **không nhạy cảm**: commit, artifact, command, exit code, thời điểm, số changeset, schema đích và kết quả hậu kiểm. Đối với chi tiết SQL, chọn mức lưu an toàn; SQL preview và log debug có thể chứa dữ liệu thật hoặc thông tin truy cập.

Cần giới hạn quyền xem log, thời hạn lưu, masking và chính sách tải artifact. Không copy nguyên stack trace có thông tin nhạy cảm vào kênh công khai.

### 14.3. Cảnh báo “không có thay đổi”

Nếu deploy phiên bản mới kỳ vọng có migration nhưng status/update cho biết không có gì cần làm, pipeline có thể cần kiểm tra expected changeset IDs so với history và artifact. Tuy nhiên, với một bản phát hành chỉ thay đổi code mà không thay đổi database, **0 changeset** là kết quả bình thường. Điều kiện quyết định phải đến từ manifest/plan của bản phát hành, không phải từ quy tắc cứng “mỗi update phải có ít nhất một changeset”.

## 15. Kiểm chứng schema và dữ liệu sau lệnh

Bất kỳ lệnh nào báo thành công cũng cần được đối chiếu với hậu điều kiện cụ thể. Ví dụ một migration tạo index cho bảng orders ở PostgreSQL:

~~~sql
SELECT schemaname,
       tablename,
       indexname,
       indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

Với một cột vừa thêm:

~~~sql
SELECT column_name,
       data_type,
       is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Hai truy vấn trên chỉ minh họa **metadata**, không thực thi migration. Đối với backfill dữ liệu:

~~~sql
SELECT COUNT(*) AS pending_count
FROM app.orders
WHERE new_status IS NULL;
~~~

Truy vấn hậu kiểm cần phù hợp invariant thật và phải biết các trường hợp NULL hợp lệ. Một count bằng 0 chỉ nói lên điều kiện cụ thể đó, không chứng minh toàn bộ dữ liệu không lỗi.

Nếu update tạo index CONCURRENTLY, kiểm tra index hợp lệ, vì PostgreSQL có thể để lại index invalid khi thao tác thất bại. Nếu update thay đổi dữ liệu lớn, kiểm tra số hàng, phân bố, foreign key và phản ứng của ứng dụng.

### 15.1. Kết quả “đã ghi trong lịch sử” không thay thế quan sát thật

DATABASECHANGELOG phản ánh lịch sử Liquibase. Database có thể có schema drift do SQL bên ngoài, migration lỗi một phần hoặc thao tác DBA. Khi có khác biệt, phải ghi rõ:

- Lịch sử Liquibase ghi nhận gì.
- Database thực tế đang có gì.
- Ứng dụng mong đợi điều gì.
- Changeset bổ sung hoặc kế hoạch phục hồi nào đưa các lớp về nhất quán.

Không tự đồng bộ history bằng cách thêm/xóa dòng để bỏ qua bước điều tra.

## 16. Đọc log của rollback và phương án phục hồi

Khi rollback, kết quả lệnh và exit code cũng chỉ phản ánh **mức thành công của quy trình rollback**, không tự bảo đảm dữ liệu trước đó được phục hồi đầy đủ.

Có thể preview rollback theo cơ chế Liquibase hỗ trợ, ví dụ rollback-sql về một tag cụ thể:

~~~bash
liquibase rollback-sql --tag=before-release
~~~

Cú pháp tham số nên được xác nhận với phiên bản CLI đang dùng. Chỉ áp dụng rollback thực tế khi đã biết database có tag đó, phạm vi changeset sẽ đảo ngược, thứ tự phụ thuộc, mức hỗ trợ transaction và SQL rollback có thể phục hồi đúng trạng thái.

Cần đọc:

- Những changeset được chọn để rollback.
- SQL đảo ngược được phát sinh hoặc khai báo tường minh.
- Các cảnh báo về thao tác không thể tự động đảo ngược.
- Mã thoát của rollback command.
- Lịch sử và schema sau rollback.
- Dữ liệu nghiệp vụ, đặc biệt phần DELETE/DROP không thể tự khôi phục.

Một rollback thành công về mặt kỹ thuật vẫn có thể làm mất dữ liệu nếu trước đó đã xóa cột chứa thông tin và không có backup. Khi rollback không an toàn, có thể cần **forward-fix changeset** và phục hồi từ snapshot được kiểm chứng.

## 17. Bài thực hành: đọc kết quả ở ba tình huống

**Môi trường:** database thử nghiệm riêng, có quyền tạo bảng, không chứa dữ liệu thật. Liquibase CLI được cấu hình đúng database thử nghiệm. Không dùng production để cố ý tạo lỗi.

### 17.1. Tình huống A – thay đổi mới hợp lệ

Tạo changelog thử nghiệm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-audit
      author: learner
      changes:
        - createTable:
            tableName: lab_audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: message
                  type: VARCHAR(255)
~~~

Sau đó chạy lần lượt:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

**Báo cáo kết quả thực hành** cần có:

1. Exit code của từng lệnh.
2. Trước update có bao nhiêu changeset pending.
3. SQL tạo bảng xuất hiện trong update-sql.
4. Sau update, lịch sử có lab-001-create-audit không.
5. Bảng lab_audit_event có thực sự tồn tại và đúng hai cột không.

### 17.2. Tình huống B – chạy update lại không có thay đổi

Không sửa changelog, gọi lại:

~~~bash
liquibase status --verbose
liquibase update
liquibase history
~~~

Kết quả kỳ vọng: changeset đã ghi nhận không tự tạo bảng lại; status có thể không có changeset pending và update hoàn tất mà không áp dụng migration mới. **Đừng xem “không có migration mới” là lỗi** khi history và mục tiêu đều đã đúng.

### 17.3. Tình huống C – cố ý tạo checksum mismatch trong lab

Chỉ trong lab, sửa type của cột message trong changeset lab-001 từ VARCHAR(255) sang VARCHAR(512) **sau khi đã chạy lab-001**, rồi chạy:

~~~bash
liquibase validate
~~~

Ghi lại:

- Exit code và thông điệp validation.
- Changeset id/author/file path liên quan.
- Checksum cũ và mới nếu log cung cấp.
- Schema database thực tế có được sửa bởi validate không.
- Vì sao đây không phải cách hợp lệ để mở rộng cột đã tồn tại.

Khôi phục định nghĩa lab-001 về VARCHAR(255), sau đó **thêm một changeset mới** để thay đổi type thay vì sửa lịch sử:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-audit
      author: learner
      changes:
        - createTable:
            tableName: lab_audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: message
                  type: VARCHAR(255)

  - changeSet:
      id: lab-002-expand-message
      author: learner
      changes:
        - modifyDataType:
            tableName: lab_audit_event
            columnName: message
            newDataType: VARCHAR(512)
~~~

Hãy chạy validate, status, update-sql trước khi update. Khả năng hỗ trợ modifyDataType phụ thuộc DBMS; chỉ tiếp tục trên engine thử nghiệm khi SQL được sinh hợp lệ và đã review. Sau update, xác nhận chỉ lab-002 chạy thêm và cột message có độ dài mới.

### 17.4. Mẫu bảng ghi nhận kết quả

| Lần chạy | Lệnh | Exit code thực tế | Changeset pending/đã chạy | Nhận xét |
|---|---|---|---|---|
| A1 | validate | Ghi từ shell | Không đổi DB | Kiểm tra định nghĩa |
| A2 | status --verbose | Ghi từ shell | Ghi pending | Kiểm tra kế hoạch |
| A3 | update-sql | Ghi từ shell | Chưa thực thi thay đổi | Review SQL |
| A4 | update | Ghi từ shell | Ghi executed | Kiểm tra schema |
| B | update lần 2 | Ghi từ shell | Có thể 0 changeset mới | Không được tạo trùng bảng |
| C1 | validate sau khi sửa lịch sử | Ghi từ shell | Không đổi DB | Điều tra mismatch |
| C2 | update sau khi thêm lab-002 | Ghi từ shell | Chỉ changeset mới | Kiểm tra kiểu cột |

Không điền sẵn exit code giả làm kết quả quan sát. Sinh viên cần thu thập mã từ tiến trình của chính mình và đối chiếu metadata database.

## 18. Checklist đọc kết quả lệnh trước khi ký duyệt phát hành

- [ ] Xác nhận chính xác lệnh đã gọi: validate, status, update-sql, update, history hay rollback.
- [ ] Ghi lại exit code trực tiếp của Liquibase, không để grep/tee/wrapper che lỗi.
- [ ] Xác nhận URL/DBMS, database, catalog/schema và tài khoản migration đúng môi trường.
- [ ] Xác nhận root changelog, commit/artifact và context/label khớp với kế hoạch.
- [ ] Đọc changeset pending và số đã thực thi; phân biệt 0 changeset với thất bại.
- [ ] Kiểm tra message/stack trace theo root cause; không chỉ tìm chuỗi success.
- [ ] Đối chiếu id, author, filename, checksum và EXECTYPE trong DATABASECHANGELOG.
- [ ] Kiểm tra MARK_RAN/RERAN nếu có, thay vì coi mọi bản ghi lịch sử đều có SQL mới chạy.
- [ ] Khi gặp lock, xác định tiến trình đang chạy trước khi cân nhắc giải phóng.
- [ ] Khi exit code khác 0, dừng rollout và kiểm tra khả năng DDL/DML đã áp dụng một phần.
- [ ] Review update-sql và SQL rollback trên DBMS đích với cấu hình tương ứng.
- [ ] Thực thi hậu kiểm schema, index, constraint, dữ liệu và ứng dụng.
- [ ] Hạn chế log chứa credential, secret, PII và SQL literal nhạy cảm.
- [ ] Giữ timestamp, commit, artifact, Liquibase version và kết quả CI/CD để kiểm toán.
- [ ] Không sửa trực tiếp bảng lịch sử để hợp thức hóa lần chạy bị lỗi.
- [ ] Chỉ kết luận PASS khi **exit code, lịch sử và hậu điều kiện** đều phù hợp mục tiêu phát hành.

## 19. Kết luận

Khi vận hành Liquibase, đọc log không chỉ là tìm chữ thành công hay thất bại. Cần hiểu **một lệnh được thiết kế để làm gì**, mã thoát của chính tiến trình đó là gì, changeset nào được chọn hoặc ghi nhận, và database thực tế có đáp ứng hậu điều kiện hay không. Exit code 0 là tín hiệu kỹ thuật quan trọng nhưng không thay thế việc kiểm chứng schema, dữ liệu và ứng dụng; exit code khác 0 có thể đi kèm thay đổi đã commit một phần cần điều tra.

Kết hợp validate, status --verbose, update-sql, update và history với truy vấn DATABASECHANGELOG/DATABASECHANGELOGLOCK, kiểm tra SQL/transaction và log có kiểm soát giúp xác định vấn đề chính xác. Trong Spring Boot và CI/CD, hãy bảo đảm lỗi migration được truyền thành trạng thái thất bại của job, lưu đủ bằng chứng để kiểm toán, bảo vệ dữ liệu nhạy cảm và chỉ triển khai tiếp khi hậu điều kiện thực sự đạt.
