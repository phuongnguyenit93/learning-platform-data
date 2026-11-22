# Xử lý khác biệt giữa các môi trường trước khi tiếp nhận

## 1. Bối cảnh và mục tiêu

Một hệ thống lâu năm thường có nhiều database cùng phục vụ một ứng dụng: development, integration test, staging và production. Qua thời gian, các môi trường có thể được tạo vào những thời điểm khác nhau, nâng cấp theo lịch khác nhau hoặc nhận thay đổi thủ công từ DBA và đội vận hành. Vì vậy, dù cùng mang tên một sản phẩm, chúng có thể **khác nhau về schema, dữ liệu, quyền, đối tượng hỗ trợ và lịch sử triển khai**.

Khi bắt đầu quản lý một database legacy bằng Liquibase, việc đầu tiên không phải là chạy update ngay. Nhóm cần xác định trạng thái thực tế của từng môi trường, phân loại những khác biệt có chủ đích và ngoài dự kiến, rồi chọn một trạng thái chuẩn để quản lý bằng changelog. Nếu bỏ qua bước này, Liquibase có thể cố tạo lại bảng đã tồn tại, đánh dấu sai lịch sử changeset hoặc khiến một môi trường bị thay đổi ngoài kế hoạch.

Bài thuộc chương **Tiếp nhận CSDL** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới việc nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **xử lý khác biệt giữa các môi trường trước khi tiếp nhận**, để nhóm có thể đưa một hệ thống legacy vào quy trình migration có thể lặp lại và truy vết.

Sau bài học, bạn cần có khả năng:

1. Lập danh mục database, schema, phiên bản DBMS, extension, quyền và lịch sử của từng môi trường.
2. Phân biệt khác biệt được thiết kế, khác biệt do dữ liệu, schema drift và thay đổi thủ công chưa được ghi nhận.
3. So sánh database bằng snapshot/diff và kiểm tra kết quả thay vì dựa vào tên môi trường.
4. Chọn một baseline có chủ đích, tạo changelog phù hợp và xác minh nội dung trước khi đồng bộ lịch sử.
5. Dùng đúng vai trò của generate-changelog, diff-changelog, changelogSync và update.
6. Chuẩn hóa dev/test/staging/production mà không xóa dữ liệu hoặc đánh dấu changeset sai trạng thái.
7. Đưa quy trình tiếp nhận vào CI/CD với phê duyệt, kiểm chứng và kế hoạch phục hồi.

## 2. Vì sao các môi trường thường không giống nhau?

Một khác biệt có thể xuất hiện vì nhiều lý do. Không phải mọi khác biệt đều là lỗi; cũng không phải khác biệt nào nhìn có vẻ hợp lý đều nên giữ lại.

| Nguồn khác biệt | Ví dụ | Rủi ro khi tiếp nhận |
|---|---|---|
| Khởi tạo ở thời điểm khác nhau | Test có cột mới, production chưa có | Changelog baseline có thể không đại diện cho mọi môi trường |
| Migration thủ công | DBA thêm index trực tiếp trên production | Lịch sử Liquibase không ghi nhận thay đổi |
| Hotfix ngoài quy trình | Sửa function để xử lý sự cố | Dev/staging có thể còn định nghĩa cũ |
| Phiên bản DBMS khác nhau | PostgreSQL ở staging mới hơn production | Cú pháp, kiểu dữ liệu và tính năng có thể khác |
| Cấu hình theo môi trường | Tablespace, schema, owner, extension | Một số thuộc tính là chủ đích, không nên ép giống nhau |
| Dữ liệu khác nhau | Test có dữ liệu giả, production có dữ liệu thật | Không thể so sánh số hàng rồi kết luận schema đúng/sai |
| Quyền khác nhau | Runtime role ở production bị giới hạn hơn dev | Test bằng owner có thể che lỗi quyền |
| Quy trình khôi phục | Production được restore từ backup cũ | Schema và DATABASECHANGELOG có thể không cùng mốc |
| Nhiều phiên bản ứng dụng | Rolling deployment còn instance cũ | Schema phải tương thích đồng thời với nhiều phiên bản |

Mục tiêu của tiếp nhận không phải là làm cho mọi database có cùng dữ liệu hoặc cùng cấu hình vận hành. Mục tiêu là xác định **phần nào cần đồng nhất để ứng dụng hoạt động**, phần nào được phép khác theo môi trường và phần nào phải được đưa về chuẩn trước khi Liquibase quản lý.

## 3. Phân loại khác biệt trước khi quyết định sửa

Nên phân loại từng sai khác vào một trong bốn nhóm.

### 3.1. Khác biệt được thiết kế

Đây là khác biệt có chủ đích, được ghi nhận trong kiến trúc hoặc cấu hình:

- Database name và hostname.
- Tên schema theo môi trường, nếu hệ thống chủ đích tách biệt.
- Tài khoản kết nối, quyền runtime và secret.
- Thông số vận hành như tablespace, storage, backup policy.
- Context/label hoặc dữ liệu kiểm thử chỉ dùng trong môi trường nhất định.

Không nên tạo migration chỉ để đổi hostname, mật khẩu hoặc dữ liệu nghiệp vụ giữa các môi trường. Các giá trị cấu hình nên được cấp từ cấu hình triển khai và kho bí mật phù hợp.

### 3.2. Khác biệt về dữ liệu

Dữ liệu dev/test và production vốn không giống nhau. Khi tiếp nhận, hãy phân biệt:

- Dữ liệu nghiệp vụ thật.
- Dữ liệu tham chiếu bắt buộc như trạng thái, loại tiền hoặc mã danh mục.
- Dữ liệu demo/fixture dành cho test.
- Dữ liệu đã được ẩn danh hoặc tạo tổng hợp.
- Dữ liệu tồn tại do thao tác thủ công chưa có quy trình.

Không dùng schema diff để kết luận dữ liệu giữa các môi trường phải giống nhau. Nếu cần so sánh dữ liệu tham chiếu, xác định tập bảng, khóa và quy tắc so sánh riêng; không xuất hoặc so sánh dữ liệu nhạy cảm tùy tiện.

### 3.3. Schema drift đã biết

Schema drift là trạng thái database khác với trạng thái mà mã nguồn migration hoặc baseline được phê duyệt mô tả. Ví dụ:

- Production có index bổ sung chưa được đưa vào changelog.
- Staging có cột do một hotfix tạo ra.
- Một bảng bị đổi kiểu dữ liệu thủ công.
- Một constraint bị drop để xử lý sự cố rồi chưa được khôi phục.
- View/function ở các môi trường có định nghĩa khác nhau.

Drift có thể là hợp lệ tạm thời, là hotfix cần đưa vào mã nguồn hoặc là lỗi cần khắc phục. Phải tìm nguồn gốc trước khi hòa giải.

### 3.4. Trạng thái chưa rõ

Nếu không biết ai tạo đối tượng, vì sao có quyền đặc biệt hoặc một cột có được ứng dụng sử dụng không, hãy xếp vào nhóm chưa rõ. Không tự động drop hoặc sửa một đối tượng chỉ vì nó không xuất hiện trong changelog hiện tại.

Một bảng quyết định hữu ích:

| Phân loại | Quyết định |
|---|---|
| Khác biệt được thiết kế | Giữ lại và ghi nhận trong cấu hình/runbook |
| Dữ liệu theo môi trường | Giữ theo chính sách dữ liệu; quản lý fixture/reference data riêng |
| Drift có chủ đích | Xác nhận, review và đưa thành changeset mới hoặc baseline được phê duyệt |
| Drift không hợp lệ | Lập kế hoạch chuẩn hóa, kiểm thử và phục hồi |
| Chưa rõ | Điều tra, tìm owner và bằng chứng trước khi thay đổi |

## 4. Lập inventory cho từng môi trường

Trước khi chạy bất kỳ lệnh thay đổi nào, lập một bảng inventory. Có thể dùng biểu mẫu trong tài liệu vận hành của nhóm; không cần lưu mọi thông tin nhạy cảm vào changelog.

| Nhóm thông tin | Cần thu thập | Vì sao quan trọng |
|---|---|---|
| Đích kết nối | Host/cluster, port, database, schema metadata | Tránh so sánh hoặc sửa nhầm môi trường |
| DBMS | Sản phẩm, phiên bản, compatibility level | Xác định cú pháp và khả năng hỗ trợ |
| Liquibase | Phiên bản CLI/library, JDBC driver | So sánh đúng cách công cụ xử lý changelog |
| Schema | Bảng, cột, kiểu, default, constraint, index | Xác định trạng thái cấu trúc |
| Đối tượng SQL | View, function, procedure, trigger, sequence, type | Tìm khác biệt ngoài bảng |
| Extension/module | Extension và phiên bản cài đặt | Phát hiện phụ thuộc DBMS |
| Bảo mật | Owner, role, grants, RLS, default privileges | Tránh kiểm thử bằng quyền quá rộng |
| Dữ liệu | Bảng tham chiếu, fixture, chất lượng dữ liệu | Xác định điều kiện thêm constraint/backfill |
| Lịch sử | DATABASECHANGELOG, DATABASECHANGELOGLOCK | Biết database đã được Liquibase quản lý hay chưa |
| Vận hành | Backup, restore, replication, maintenance window | Đánh giá khả năng tiếp nhận an toàn |

### 4.1. Xác minh đúng database trước khi so sánh

Tên môi trường trong pipeline không đủ chứng minh JDBC URL đang trỏ đúng database. Trên PostgreSQL, một bước chỉ đọc có thể là:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS database_user,
    version() AS database_version;
~~~

Câu lệnh này chỉ là ví dụ PostgreSQL. Với DBMS khác, dùng hàm metadata tương ứng. So sánh host/cluster và thông tin định danh kết nối ở tầng hạ tầng, vì hai server có thể cùng có database name giống nhau.

Không đưa password, token hoặc chuỗi kết nối có secret vào inventory, changelog, log hay báo cáo so sánh.

### 4.2. Kiểm tra lịch sử Liquibase hiện có

Nếu database đã có DATABASECHANGELOG, hãy xác định:

- Bảng lịch sử nằm ở schema nào.
- Các changeset được nhận diện theo ID, AUTHOR và FILENAME ra sao.
- Có checksum mismatch hay không.
- Có bản ghi thực thi bị lỗi hoặc trạng thái đặc biệt không.
- DATABASECHANGELOGLOCK có đang bị khóa hay không.
- Changelog hiện tại có cùng revision với artifact từng triển khai không.

Không tạo lại hoặc xóa bảng lịch sử chỉ để bắt đầu tiếp nhận cho “sạch”. Một database có lịch sử Liquibase cũ cần được đánh giá như một nguồn sự thật riêng.

## 5. Chọn database tham chiếu và định nghĩa baseline

Một baseline là mốc mô tả trạng thái schema đã được chấp nhận để bắt đầu quản lý tiếp bằng migration. Nó không nhất thiết là database production mới nhất, cũng không phải database có nhiều đối tượng nhất.

Chọn database tham chiếu dựa trên:

1. Trạng thái được chủ sở hữu sản phẩm xác nhận là đúng.
2. Đã bao gồm các hotfix hợp lệ hoặc có danh sách ngoại lệ rõ ràng.
3. Không chứa đối tượng thử nghiệm hoặc dữ liệu tạm.
4. Phiên bản DBMS phù hợp với ma trận môi trường được hỗ trợ.
5. Có thể giải thích và truy vết nguồn gốc thay đổi.
6. Đã được kiểm thử với ứng dụng và các đối tượng phụ thuộc.

Nếu production có một hotfix cần thiết nhưng staging chưa có, không nên bỏ qua chỉ vì staging được chọn làm tham chiếu trước đó. Cần quyết định hotfix có phải một phần baseline mới hay phải được triển khai có kiểm soát lên các môi trường còn lại.

### 5.1. Một baseline không phải là ảnh chụp dữ liệu

Baseline schema thường mô tả đối tượng và ràng buộc. Nó không mặc nhiên chứa toàn bộ dữ liệu production, dữ liệu cá nhân, secret hoặc trạng thái runtime. Những loại dữ liệu khác nhau cần chính sách riêng:

- DDL: quản lý bằng changelog.
- Dữ liệu tham chiếu: changeset có khóa ổn định và quy tắc cập nhật.
- Fixture/test data: quản lý theo môi trường test.
- Dữ liệu nghiệp vụ: giữ trong database, chuyển đổi bằng migration có kiểm soát khi cần.
- Secret: cung cấp qua hệ thống quản lý bí mật.

## 6. So sánh schema giữa các môi trường

Liquibase cung cấp các khả năng so sánh database như **diff** và tạo changelog từ khác biệt như **diff-changelog**. Chúng hữu ích để phát hiện chênh lệch, nhưng kết quả cần được review bởi người hiểu schema và nghiệp vụ.

Ở mức khái quát:

- **Reference database**: trạng thái chuẩn dùng làm mốc so sánh.
- **Target database**: database cần kiểm tra hoặc cần đưa về trạng thái tương ứng.
- **diff**: báo cáo những khác biệt giữa reference và target theo loại đối tượng được chọn.
- **diff-changelog**: có thể sinh changelog mô tả thay đổi để đưa target gần hơn với reference, tùy cấu hình và hướng so sánh.

**Hướng reference/target rất quan trọng.** Nếu chọn nhầm chiều, changelog được sinh ra có thể chứa DROP hoặc CREATE ngược với mục tiêu. Trước khi dùng diff-changelog, phải xác nhận rõ database nào là chuẩn và database nào là đối tượng cần thay đổi.

### 6.1. Ví dụ lệnh so sánh

Cú pháp CLI phụ thuộc phiên bản Liquibase và cách cung cấp thông tin kết nối. Một dạng thường gặp:

~~~bash
liquibase \
  --reference-url="jdbc:postgresql://reference-host:5432/shop" \
  --reference-username=diff_reader \
  --reference-password=<secret-from-secure-store> \
  --url="jdbc:postgresql://target-host:5432/shop" \
  --username=diff_reader \
  --password=<secret-from-secure-store> \
  diff
~~~

Đây là ví dụ minh họa cấu trúc tham số; không đưa secret thật vào lịch sử shell hoặc log CI. Hãy dùng secret injection theo nền tảng triển khai và kiểm tra cú pháp của phiên bản CLI đang chạy. Một số cách gọi dùng defaults file, environment variables hoặc command options khác nhau.

Kết quả diff nên được lưu trong artifact review theo chính sách của tổ chức. Nếu output có tên đối tượng nội bộ, cần giới hạn quyền truy cập.

### 6.2. Diff không chứng minh mọi thứ giống nhau

Một báo cáo schema diff không thay thế kiểm tra:

- Dữ liệu nghiệp vụ.
- Quyền hiệu lực qua role membership và PUBLIC.
- Cấu hình ứng dụng, secret và biến môi trường.
- Replication, extension ngoài phạm vi snapshot.
- Trigger/job bên ngoài database.
- Tính tương thích của SQL với phiên bản DBMS.
- Hiệu năng hoặc trạng thái khóa khi triển khai.

Hãy dùng diff như một công cụ phát hiện khác biệt, sau đó kiểm tra bằng catalog/metadata và các bài test phù hợp.

## 7. Review diff-changelog trước khi áp dụng

Không đưa changelog được sinh tự động vào production mà chưa review. Một diff có thể sinh các thao tác:

- CREATE TABLE, ADD COLUMN hoặc CREATE INDEX.
- DROP COLUMN, DROP TABLE hoặc DROP CONSTRAINT.
- Thay đổi kiểu dữ liệu.
- Tạo lại view/function.
- Thay đổi default hoặc nullable.
- Thay đổi quyền hoặc đối tượng phụ thuộc, nếu loại so sánh/công cụ hỗ trợ.

Những thao tác **DROP**, đổi kiểu hoặc thay constraint có thể gây mất dữ liệu hay gián đoạn ứng dụng. Cần phân loại từng thay đổi:

| Loại diff | Câu hỏi review |
|---|---|
| Đối tượng thiếu ở target | Có thực sự cần tạo? Có phụ thuộc trước đó? |
| Đối tượng thừa ở target | Có phải hotfix, đối tượng dùng chung hay thử nghiệm? Có được phép drop? |
| Cột khác kiểu/default/nullability | Có dữ liệu không chuyển đổi được? Ứng dụng nào phụ thuộc? |
| Index khác | Có phục vụ workload đặc thù? Tạo lại có khóa bảng không? |
| View/function khác | Khác biệt nghiệp vụ hay chỉ khác cách định nghĩa? |
| Quyền khác | Có chủ đích theo môi trường? Ai sở hữu quyền? |
| Constraint khác | Dữ liệu hiện tại có đáp ứng ràng buộc không? |

Không phải mọi khác biệt đều nên sửa bằng một changeset duy nhất. Một số cần chuẩn hóa cấu hình, một số cần backfill theo giai đoạn, một số cần giữ nguyên như ngoại lệ môi trường.

## 8. Chiến lược tiếp nhận database chưa có Liquibase

Nếu database legacy **chưa có DATABASECHANGELOG**, cần chọn cách đưa nó vào quản lý.

Một chiến lược thường dùng:

1. Chọn trạng thái schema chuẩn đã được review.
2. Tạo changelog baseline mô tả những đối tượng thuộc phạm vi quản lý.
3. Kiểm tra changelog trên database rỗng hoặc database dựng lại được.
4. So sánh schema của từng database legacy với baseline.
5. Chuẩn hóa những sai khác cần thiết hoặc ghi nhận ngoại lệ được phê duyệt.
6. Trên database legacy đã đúng baseline, dùng cơ chế đồng bộ lịch sử phù hợp để đánh dấu các changeset baseline đã được áp dụng mà không thực thi lại DDL.
7. Trên database mới/rỗng, chạy update để thực sự tạo đối tượng từ baseline.
8. Sau khi các môi trường có cùng điểm bắt đầu, chỉ dùng changeset mới cho thay đổi tiếp theo.

Lệnh **changelogSync** có thể được dùng trong trường hợp đã xác minh database hiện tại thực sự tương ứng với những changeset sẽ được đánh dấu. Lệnh này ghi nhận changeset như đã chạy mà **không thực thi SQL của chúng**.

Ví dụ dạng lệnh:

~~~bash
liquibase --defaults-file=liquibase.properties changelog-sync
~~~

Tên lệnh có thể được viết theo kiểu camel case trong một số tài liệu/phiên bản. Phải kiểm tra chính xác cú pháp CLI đang sử dụng.

**Không chạy changelogSync trên database legacy chỉ vì muốn tạo DATABASECHANGELOG.** Nếu changelog chứa 50 changeset nhưng database chỉ có 45 thay đổi tương ứng, việc đánh dấu tất cả đã chạy sẽ khiến lịch sử sai và các đối tượng còn thiếu không được tạo.

## 9. Dùng generate-changelog để chụp trạng thái hiện có

Liquibase có khả năng sinh changelog từ schema database hiện tại thông qua **generate-changelog**. Đây có thể là điểm khởi đầu để tiếp nhận một database legacy khi chưa có mã nguồn mô tả schema.

Ví dụ:

~~~bash
liquibase --defaults-file=liquibase.properties generate-changelog
~~~

Tùy phiên bản và cấu hình, có thể cần chỉ rõ output file, schema, loại đối tượng và bộ lọc. Không giả định lệnh mặc định sẽ sinh mọi đối tượng cần thiết hoặc tạo changelog sẵn sàng đưa production.

### 9.1. Vì sao phải review changelog được sinh?

Changelog tự sinh có thể cần chỉnh sửa có kiểm soát vì:

- Tên constraint/index có thể được chuẩn hóa khác nhau.
- Đối tượng đặc thù DBMS có thể chưa được biểu diễn đầy đủ.
- SQL function/procedure, trigger, extension hoặc quyền có thể cần xử lý riêng.
- Thứ tự phụ thuộc có thể cần điều chỉnh.
- Changelog có thể chứa thông tin môi trường không nên đưa vào baseline chung.
- Một số thuộc tính mặc định có thể khác do phiên bản DBMS.

Không chỉnh sửa tùy tiện changelog sau khi đã dùng nó làm baseline và triển khai ở một môi trường. Khi baseline đã được phát hành, hãy coi nó là lịch sử bất biến và dùng changeset mới cho thay đổi sau này.

### 9.2. Changelog baseline và migration tiếp diễn

Một cấu trúc có thể chia baseline và migration mới:

~~~text
db/changelog/
  db.changelog-master.yaml
  baseline/
    0001-initial-schema.yaml
  changes/
    0002-add-order-status.yaml
    0003-create-order-summary.yaml
~~~

Đây là cấu trúc minh họa, không yêu cầu tạo file/folder trong bài học. Master changelog include các file theo thứ tự được review. Cần giữ đường dẫn/định danh changeset ổn định; nếu di chuyển tệp sau triển khai, xem xét logicalFilePath và kiểm thử nhận diện lịch sử.

## 10. Chọn giữa generate-changelog, diff-changelog và changelogSync

| Công cụ | Câu hỏi nó trả lời | Nó không làm gì |
|---|---|---|
| generate-changelog | Schema hiện tại của database gồm những đối tượng nào có thể biểu diễn thành changelog? | Không tự chứng minh schema đúng hoặc đồng bộ các môi trường |
| diff | Reference và target khác nhau ở đâu? | Không tự sửa database |
| diff-changelog | Có thể mô tả thay đổi nào để đưa target gần reference? | Không quyết định thay đổi nào an toàn về nghiệp vụ |
| changelogSync | Đánh dấu các changeset phù hợp là đã chạy trong lịch sử | Không thực thi DDL/DML của changeset được đánh dấu |
| update | Thực thi các changeset pending phù hợp | Không tự giải quyết drift hoặc dữ liệu không đáp ứng điều kiện |
| validate | Kiểm tra changelog và một số vấn đề cấu trúc/checksum | Không chứng minh schema/data thực tế hoàn toàn đúng |

Chọn công cụ theo trạng thái:

- Database chưa được Liquibase quản lý: inventory, generate/review baseline, diff và quyết định cách sync.
- Database đã có lịch sử: giữ lịch sử, xác minh checksum, so sánh schema và tạo changeset tiếp theo.
- Database mới: chạy update từ changelog baseline đã được kiểm thử.
- Database có drift: điều tra và hòa giải trước khi đánh dấu trạng thái.
- Database cần đồng bộ lịch sử sau thay đổi ngoài Liquibase: chỉ dùng changelogSync/markNextChangeSetRan theo bằng chứng và quy trình được phê duyệt.

## 11. Xử lý môi trường có schema mới hơn hoặc cũ hơn baseline

Giả sử baseline đã được xác nhận ở phiên bản **V1**:

| Môi trường | Trạng thái thực tế | Hướng xử lý |
|---|---|---|
| Dev | V1 + thay đổi thử nghiệm V2 chưa review | Loại thay đổi thử nghiệm khỏi baseline hoặc đưa thành changeset được duyệt |
| Test | V1 | Có thể dùng làm nơi xác minh baseline |
| Staging | V1 + hotfix V2 hợp lệ | Xác định hotfix có trở thành changeset chuẩn; không xóa bỏ |
| Production | V1 + một index thủ công | Điều tra owner/mục đích; quyết định đưa vào changelog hay giữ ngoại lệ có tài liệu |

Không chọn “database mới nhất” làm chuẩn một cách máy móc. Một thay đổi có thể mới hơn nhưng sai hoặc chỉ phục vụ điều tra tạm thời. Cần xác nhận **trạng thái mong muốn của sản phẩm** với DBA, owner ứng dụng và người chịu trách nhiệm dữ liệu.

### 11.1. Môi trường thiếu thay đổi

Nếu test thiếu một changeset đã có ở production, trước tiên xác minh:

- DATABASECHANGELOG có bản ghi không?
- Changelog revision và FILENAME có giống nhau không?
- Đối tượng có được tạo thủ công hay từ một quy trình khác?
- Có bị loại do context/label filter không?
- Database có restore từ backup cũ không?

Sau đó chọn update để áp dụng changeset pending nếu database thật sự thiếu thay đổi và changelog có thể thực thi an toàn.

### 11.2. Môi trường có thêm thay đổi

Nếu production có cột/index/view không có trong baseline:

- Tìm commit/ticket/owner của thay đổi.
- Xác minh ứng dụng có đang sử dụng không.
- Kiểm tra phụ thuộc và dữ liệu.
- Nếu hợp lệ, mô tả nó trong một changeset mới hoặc baseline được phê duyệt trước khi tiếp tục.
- Nếu tạm thời, ghi ngoại lệ, người chịu trách nhiệm và thời hạn loại bỏ.

Không tạo changelog DROP tự động chỉ để diff báo hai môi trường giống nhau.

## 12. Xử lý khác biệt về quyền, role và owner

Schema diff thường không đủ để mô tả chính xác quyền hiệu lực. Mỗi môi trường có thể có login role khác nhau, role membership, default privileges và RLS policy riêng.

Nên tách:

- Role/nhóm quyền chuẩn của ứng dụng.
- Login role và secret được cấp theo môi trường.
- Owner của schema/đối tượng.
- Quyền runtime tối thiểu.
- Quyền migration cần để thực hiện DDL/GRANT.
- Những quyền đặc biệt được phê duyệt.

Trên PostgreSQL, ví dụ kiểm tra quyền có thể dùng has_schema_privilege hoặc has_table_privilege; trên DBMS khác cần công cụ metadata tương ứng. Không so sánh tên username rồi kết luận hai môi trường có quyền tương đương.

Một môi trường test thường được cấp owner hoặc quyền rộng để tiện phát triển. Điều đó không chứng minh production role runtime có quyền đúng. Sau tiếp nhận, cần kiểm thử bằng danh tính gần production, không chỉ bằng superuser.

## 13. Xử lý extension và phiên bản DBMS khác nhau

Database legacy có thể dùng extension, kiểu dữ liệu, collation, timezone database, function hoặc tính năng riêng của một phiên bản DBMS. Nếu staging mới hơn production, một câu lệnh chạy được trên staging có thể không tương thích production.

Trước khi tạo baseline:

1. Ghi nhận sản phẩm và phiên bản DBMS của từng môi trường.
2. Kiểm tra extension/module và phiên bản.
3. Xác định tính năng tối thiểu mà ứng dụng yêu cầu.
4. Chọn ma trận DBMS được hỗ trợ.
5. Tách changeset theo DBMS khi SQL đặc thù.
6. Thử migration trên phiên bản thấp nhất còn được hỗ trợ.
7. Xác minh thứ tự nâng cấp DBMS và nâng cấp schema.

Không ép tất cả môi trường cài cùng extension hoặc nâng DBMS chỉ bằng một changeset ứng dụng nếu thao tác đó cần quyền quản trị hoặc có tác động hạ tầng. Có thể cần bước bootstrap riêng do DBA/Platform thực hiện, sau đó changelog ứng dụng kiểm tra sự hiện diện.

## 14. Dữ liệu legacy và điều kiện trước khi thêm constraint

Schema có thể gần giống nhau nhưng chất lượng dữ liệu rất khác. Trước khi thêm NOT NULL, UNIQUE, FOREIGN KEY hoặc CHECK, cần chạy kiểm tra dữ liệu trên **từng môi trường**.

Ví dụ trước khi thêm UNIQUE cho email:

~~~sql
SELECT email, COUNT(*) AS occurrences
FROM app.customer
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Ví dụ kiểm tra NULL:

~~~sql
SELECT COUNT(*)
FROM app.customer
WHERE customer_code IS NULL;
~~~

Ví dụ kiểm tra orphan FK:

~~~sql
SELECT COUNT(*)
FROM app.order_item AS child
LEFT JOIN app.orders AS parent
  ON parent.order_id = child.order_id
WHERE child.order_id IS NOT NULL
  AND parent.order_id IS NULL;
~~~

Những truy vấn trên là ví dụ SQL cần điều chỉnh theo DBMS và mô hình dữ liệu. Nếu kết quả vi phạm khác nhau giữa môi trường, không thể chạy cùng một changeset thêm constraint một cách mù quáng.

Quy trình phù hợp:

1. Định nghĩa bất biến nghiệp vụ.
2. Đo dữ liệu vi phạm trên mỗi database.
3. Xác định cách làm sạch hoặc chuyển đổi có thể kiểm chứng.
4. Backfill theo lô nếu dữ liệu lớn.
5. Kiểm tra lại điều kiện.
6. Thêm constraint trong một changeset mới.
7. Kiểm tra hậu triển khai và theo dõi lỗi ghi dữ liệu.

Precondition như sqlCheck có thể dừng migration khi dữ liệu chưa đạt, nhưng nó không tự giải quyết dữ liệu trùng hoặc orphan.

## 15. Tách cấu hình theo môi trường khỏi baseline schema

Không nên đưa các giá trị chỉ khác theo môi trường vào baseline như thể chúng là cấu trúc chung. Ví dụ:

- Tên host, port, database.
- Password và token.
- Đường dẫn lưu trữ.
- Tham số vận hành.
- Cấu hình endpoint của dịch vụ ngoài.
- Dữ liệu demo riêng cho test.

Các giá trị cần thiết cho DDL có thể được cấp qua changelog parameter, nhưng phải kiểm soát allowlist và tránh ghép SQL từ đầu vào không đáng tin. Với các khác biệt thuần cấu hình, dùng profile/secret/config management của môi trường.

**Context và label** có thể chọn changeset chỉ dành cho một nhóm môi trường, nhưng không nên dùng chúng để che giấu drift. Nếu một thay đổi schema là bắt buộc cho ứng dụng, cần bảo đảm nó được chạy ở mọi môi trường liên quan.

## 16. Tạo baseline dùng chung cho database mới và database legacy

Một mục tiêu thường gặp là để database mới và database legacy đi đến cùng trạng thái, nhưng đường đi ban đầu khác nhau.

| Loại database | Cách tiếp cận |
|---|---|
| Database mới/rỗng | Chạy update để thực thi baseline changelog, tạo các đối tượng |
| Database legacy đã khớp baseline | Sau xác minh, dùng changelogSync để ghi nhận changeset baseline đã được áp dụng |
| Database legacy thiếu đối tượng | Lập migration bổ sung hoặc chuẩn hóa; không sync như thể đối tượng đã tồn tại |
| Database legacy có đối tượng khác | Điều tra drift, quyết định giữ/sửa/loại bỏ theo phê duyệt |
| Database đã có Liquibase history | Tiếp tục từ lịch sử hiện có sau khi xác minh ID/author/FILENAME/checksum; tránh tạo baseline trùng |

### 16.1. Điều kiện bắt buộc trước changelogSync

Trước khi chạy changelogSync, phải xác nhận:

- Mọi changeset sẽ được đánh dấu đã chạy tương ứng với trạng thái thật.
- Không có bảng/cột/index/function quan trọng bị thiếu.
- Không có khác biệt chưa xử lý khiến ứng dụng sai.
- Đúng changelog master, đúng revision và đúng database.
- Không có job Liquibase khác đang chạy.
- Có bằng chứng schema và người phê duyệt.
- Đã thử quy trình trên bản sao database đại diện.

Nếu một baseline chứa 100 changeset nhưng database chỉ tương ứng 98 changeset, không nên đánh dấu cả 100 là ran. Hãy chia baseline hoặc sửa trạng thái theo một kế hoạch có thể chứng minh.

### 16.2. Một changelog mới cho giai đoạn sau baseline

Sau khi mọi môi trường đã được xác nhận ở baseline V1, thay đổi tiếp theo nên là changeset mới V2. Không sửa baseline để thêm cột hoặc thay constraint đã triển khai.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 0002-add-order-source
      author: platform-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: orders
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: source_system
                  type: VARCHAR(50)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: orders
            columnName: source_system
~~~

Ví dụ giả định cột chưa tồn tại và có thể nullable. Nếu cột bắt buộc, cần thiết kế default/backfill và chuyển đổi ứng dụng; rollback dropColumn sẽ xóa dữ liệu mới ghi vào cột.

## 17. Schema history không đồng nghĩa trạng thái schema thật

Sau khi tiếp nhận, một database có thể có DATABASECHANGELOG giống môi trường khác nhưng schema thật vẫn khác do thay đổi thủ công sau đó. Ngược lại, hai database có schema giống nhau nhưng lịch sử khác nhau vì được khởi tạo bằng cách khác.

| DATABASECHANGELOG | Schema thực tế | Cách diễn giải |
|---|---|---|
| Giống nhau | Giống nhau | Có dấu hiệu đồng nhất, vẫn cần kiểm tra quyền/dữ liệu |
| Giống nhau | Khác nhau | Có thể drift ngoài Liquibase hoặc trạng thái history bị đánh dấu sai |
| Khác nhau | Giống nhau | Có thể được tạo bằng quy trình khác hoặc history chưa đồng bộ |
| Khác nhau | Khác nhau | Cần điều tra toàn bộ lịch sử và trạng thái thực tế |

Checksum giúp phát hiện changeset bị thay đổi so với nội dung hiện tại, nhưng không phải công cụ phát hiện mọi schema drift. Cần kết hợp:

- Changelog được lưu trong Git.
- DATABASECHANGELOG.
- Schema diff/snapshot.
- Metadata về quyền và đối tượng hỗ trợ.
- Kiểm tra dữ liệu.
- Test ứng dụng và truy vấn quan trọng.

Không dùng clear-checksums, changelogSync hoặc sửa trực tiếp bảng lịch sử để che giấu sự khác biệt chưa hiểu rõ.

## 18. Lập kế hoạch chuẩn hóa theo từng giai đoạn

Một kế hoạch tiếp nhận có thể chia thành năm giai đoạn:

### Giai đoạn A — Khảo sát

- Lập inventory từng môi trường.
- Xác minh DBMS, version, schema, owner và role.
- Thu thập DATABASECHANGELOG nếu đã tồn tại.
- Lập danh sách khác biệt và người sở hữu.

### Giai đoạn B — Chọn baseline

- Chọn trạng thái chuẩn có phê duyệt.
- Tạo snapshot hoặc generate-changelog.
- Review đối tượng và thứ tự phụ thuộc.
- Tách cấu hình và dữ liệu riêng môi trường.

### Giai đoạn C — Phân loại và hòa giải

- Xác định drift hợp lệ, không hợp lệ và chưa rõ.
- Tạo changeset mới cho thay đổi cần chuẩn hóa.
- Làm sạch/backfill dữ liệu nếu cần.
- Kiểm tra FK, quyền, view/function và extension.

### Giai đoạn D — Đồng bộ lịch sử

- Database mới chạy update từ baseline.
- Database legacy đã khớp mới dùng changelogSync theo kế hoạch.
- Database đã có history tiếp tục từ history đó sau khi xác minh.
- Kiểm tra checksum và DATABASECHANGELOG sau thao tác.

### Giai đoạn E — Vận hành thường xuyên

- Chỉ thay đổi qua changeset mới.
- Promote cùng artifact qua môi trường.
- Chạy validate, status và update-sql trước phát hành.
- Kiểm tra schema/data sau update.
- Theo dõi drift và lưu bằng chứng.

Không nên cố hoàn tất cả năm giai đoạn trong một lần deploy production. Có thể cần một cửa sổ tiếp nhận riêng, một nhánh release đặc biệt và sự phối hợp DBA, ứng dụng, bảo mật, vận hành.

## 19. Tích hợp Spring Boot và CI/CD

Khi ứng dụng Spring Boot sử dụng Liquibase, migration có thể chạy lúc khởi động. Trong giai đoạn tiếp nhận legacy, điều này có thể nguy hiểm nếu ứng dụng tự chạy update trước khi nhóm xác minh trạng thái từng môi trường.

Một số lựa chọn:

- Tắt auto migration trong môi trường tiếp nhận và dùng job Liquibase riêng.
- Dùng profile riêng cho dev/test, staging và production.
- Cấp changelog parameter qua cấu hình có kiểm soát.
- Tách tài khoản migration khỏi tài khoản runtime.
- Chỉ cho job đã phê duyệt có secret production.
- Đảm bảo một chủ sở hữu migration cho mỗi database trong một lượt phát hành.

Ví dụ cấu hình Spring Boot khi migration được điều phối bằng job riêng:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Đây chỉ là đoạn cấu hình minh họa cho profile production trong kiến trúc mà pipeline sở hữu migration. Nếu ứng dụng được thiết kế để tự migrate khi khởi động, không áp dụng tắt tùy tiện; cần xem xét readiness, concurrency và quyền của datasource.

### 19.1. Pipeline tiếp nhận database

1. Xác minh environment, JDBC URL, host, database, schema và user.
2. Thu thập inventory và kiểm tra lịch sử Liquibase.
3. So sánh reference/target bằng diff.
4. Review diff-changelog hoặc baseline được sinh.
5. Chạy validate và status.
6. Thử update trên bản sao hoặc staging đại diện.
7. Xác nhận dữ liệu, quyền và đối tượng hỗ trợ.
8. Chọn update hoặc changelogSync đúng trạng thái database.
9. Hậu kiểm DATABASECHANGELOG, schema và ứng dụng.
10. Lưu artifact, kết quả so sánh, phê duyệt và ngoại lệ.

Các lệnh CLI minh họa:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties diff
liquibase --defaults-file=liquibase.properties diff-changelog
~~~

Tên tùy chọn, cách cấu hình reference/target và lệnh có thể khác theo phiên bản Liquibase. Chạy diff/diff-changelog phải xác định chính xác reference và target; review SQL sinh ra trước khi thực thi.

## 20. Rollback và phục hồi trong giai đoạn tiếp nhận

Tiếp nhận database legacy khác với triển khai một changeset nhỏ trên hệ thống đã được quản lý. Trước khi chuẩn hóa, nhóm có thể chưa hiểu đầy đủ nguồn gốc dữ liệu và phụ thuộc. Vì vậy, **backup/restore có kiểm chứng** thường quan trọng hơn một rollback YAML đơn giản.

Trước khi thay đổi:

- Xác định RPO/RTO và phương án restore.
- Kiểm tra backup có thể khôi phục trên môi trường tương ứng.
- Lưu snapshot schema và bằng chứng lịch sử.
- Xác định đối tượng có dữ liệu hoặc phụ thuộc không thể tạo lại.
- Thử rollback/forward fix trên bản sao.
- Xác định điểm không thể rollback nếu ứng dụng bắt đầu ghi theo cấu trúc mới.

**changelogSync không phải rollback**; nó ghi nhận changeset như đã chạy mà không thực thi SQL. Nếu sync sai, việc xóa dòng DATABASECHANGELOG bằng tay không phải phương án mặc định. Cần điều tra trạng thái schema, lịch sử và dùng quy trình hòa giải được phê duyệt.

Với changeset đã chạy, giữ nguyên nội dung lịch sử. Nếu cần sửa trạng thái database, tạo changeset mới hoặc thực hiện phục hồi theo runbook. Không dùng clear-checksums để biến một database chưa khớp baseline thành trạng thái hợp lệ.

## 21. Ví dụ tình huống: ba môi trường khác nhau

Một hệ thống bán hàng có ba database:

- **dev:** có cột app.orders.source_system do lập trình viên thử nghiệm.
- **staging:** có index ix_orders_created_at do một hotfix đã được kiểm thử.
- **production:** chưa có cột source_system nhưng có view active_orders với định nghĩa cũ.

Nhóm muốn bắt đầu quản lý cả ba bằng Liquibase.

### Bước 1. Xác định ý nghĩa từng khác biệt

- source_system: thử nghiệm hay yêu cầu sản phẩm? Nếu không được duyệt, không đưa vào baseline.
- ix_orders_created_at: hotfix hợp lệ hay index trùng? Kiểm tra query plan, owner và ticket.
- active_orders: định nghĩa cũ có đang được ứng dụng sử dụng? Có cần thay đổi tương thích không?

### Bước 2. Chọn baseline có chủ đích

Giả sử nhóm xác nhận index staging là cần thiết, view active_orders cần định nghĩa mới và source_system chưa được phát hành. Baseline phải phản ánh trạng thái chuẩn đã duyệt, không lấy nguyên dev hoặc production.

### Bước 3. Hòa giải

- Loại bỏ source_system thử nghiệm khỏi phạm vi baseline hoặc giữ lại dưới ngoại lệ tạm thời có phê duyệt.
- Đưa index hợp lệ vào changelog.
- Lập changeset cập nhật view theo cách tương thích.
- Thử các thay đổi trên database bản sao của cả ba môi trường.

### Bước 4. Đồng bộ lịch sử

Chỉ database nào đã được xác minh tương ứng với baseline mới được đánh dấu bằng changelogSync. Database thiếu đối tượng phải được chuẩn hóa trước hoặc dùng một chuỗi migration phù hợp. Không đánh dấu tất cả changeset như đã chạy chỉ để làm lịch sử giống nhau.

### Bước 5. Hậu kiểm

So sánh lại schema, quyền, dữ liệu tham chiếu và hành vi ứng dụng. Ghi rõ ngoại lệ còn tồn tại, owner và thời hạn xử lý.

## 22. Lỗi thường gặp khi tiếp nhận

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| update báo bảng đã tồn tại | Chạy baseline lên database legacy chưa sync hoặc changelog sai | Xác minh schema/history; không drop bảng để chạy lại |
| changelogSync xong nhưng ứng dụng thiếu cột | Đánh dấu changeset ran dù database chưa có thay đổi | Điều tra lịch sử và schema, lập migration hòa giải |
| diff-changelog sinh nhiều DROP | Chọn sai reference/target hoặc baseline không phù hợp | Kiểm tra chiều so sánh và review từng thao tác phá hủy |
| Diff không phát hiện quyền sai | Phạm vi so sánh không bao gồm hoặc không phản ánh quyền hiệu lực | Kiểm tra role membership, grants, RLS riêng |
| Staging chạy được nhưng production lỗi cú pháp | DBMS/version khác hoặc extension thiếu | Thử trên phiên bản thấp nhất được hỗ trợ |
| Checksum mismatch sau khi đổi đường dẫn | FILENAME/logicalFilePath thay đổi | Khôi phục định danh lịch sử và kiểm tra quy tắc path |
| Database mới chạy được nhưng legacy lỗi | Dữ liệu legacy có NULL/trùng/orphan | Kiểm tra dữ liệu trước constraint và backfill |
| Cùng changelog nhưng trạng thái schema khác | Có thao tác ngoài Liquibase hoặc history bị sync sai | So sánh DATABASECHANGELOG với schema thật |
| Production có object thừa | Hotfix/đối tượng dùng chung chưa được ghi nhận | Tìm owner và quyết định giữ, đưa vào changelog hoặc loại bỏ |
| Runtime lỗi quyền sau tiếp nhận | Test dùng owner, production dùng role hạn chế | Kiểm thử bằng role runtime thật |
| Nhiều job cùng tiếp nhận database | Thiếu điều phối migration | Chọn một job chủ sở hữu, kiểm tra DATABASECHANGELOGLOCK |
| Dữ liệu test bị lẫn production | Seed/context hoặc nguồn dữ liệu không được phân tách | Tách fixture, context và quy trình dữ liệu |

## 23. Checklist trước khi đưa database legacy vào Liquibase

- [ ] Đã xác minh đúng host/cluster, database, schema và user của từng môi trường.
- [ ] Đã ghi nhận DBMS/version, Liquibase/JDBC driver và extension.
- [ ] Đã kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK nếu đã tồn tại.
- [ ] Đã chọn database tham chiếu có phê duyệt và có lý do rõ ràng.
- [ ] Đã phân loại khác biệt thành thiết kế, dữ liệu, drift hợp lệ, drift không hợp lệ hoặc chưa rõ.
- [ ] Đã so sánh schema bằng diff/snapshot và review hướng reference/target.
- [ ] Đã review changelog được sinh từ generate-changelog/diff-changelog.
- [ ] Không đưa secret, dữ liệu nghiệp vụ hoặc cấu hình riêng môi trường vào baseline chung.
- [ ] Đã kiểm tra dữ liệu NULL/trùng/orphan trước khi thêm constraint.
- [ ] Đã xác minh quyền/owner/role bằng danh tính gần production.
- [ ] Đã chọn rõ database legacy nào có thể changelogSync và vì sao.
- [ ] Database mới và database legacy có quy trình khởi tạo riêng nhưng cùng mốc baseline đã kiểm chứng.
- [ ] Đã thử quy trình trên bản sao hoặc staging đại diện.
- [ ] Có backup/restore và kế hoạch rollback/forward fix.
- [ ] Changeset lịch sử bất biến; thay đổi sau baseline dùng changeset mới.
- [ ] Có một chủ sở hữu migration trong CI/CD và hậu kiểm sau triển khai.
- [ ] Các ngoại lệ môi trường có owner, lý do và thời hạn xử lý.

## 24. Kết luận

Xử lý khác biệt giữa các môi trường là bước nền tảng trước khi tiếp nhận database legacy bằng Liquibase. Nhóm cần **khảo sát từng môi trường, phân loại drift, chọn baseline có phê duyệt, so sánh schema đúng chiều, review changelog được sinh và xác minh dữ liệu/quyền/phụ thuộc** trước khi đồng bộ lịch sử.

**generate-changelog** giúp mô tả schema hiện tại; **diff/diff-changelog** giúp phát hiện và diễn đạt khác biệt; **changelogSync** chỉ ghi nhận changeset đã được áp dụng mà không thực thi SQL; còn **update** thực sự thực thi changeset pending. Dùng đúng từng công cụ và kiểm tra đúng database là điều kiện để tránh tạo lại đối tượng, đánh dấu lịch sử sai hoặc làm mất dữ liệu.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, một quy trình tiếp nhận đáng tin cậy giúp dev, test, staging và production có chung một điểm quản lý rõ ràng, đồng thời vẫn giữ các khác biệt cấu hình và dữ liệu hợp lệ. Khi baseline được xác minh và phát hành, mọi thay đổi tiếp theo cần đi qua changeset mới, kiểm thử, rollback/forward fix và CI/CD có truy vết.

