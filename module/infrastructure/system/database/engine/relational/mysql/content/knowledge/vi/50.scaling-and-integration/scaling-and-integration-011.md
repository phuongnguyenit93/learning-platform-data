# Dịch vụ MySQL được quản lý và ranh giới quyền vận hành/backup

Dịch vụ MySQL được quản lý (managed MySQL) giúp đội phát triển sử dụng database mà không phải tự vận hành toàn bộ máy chủ, hệ điều hành, storage và quy trình vá hạ tầng. Nhà cung cấp thường chịu trách nhiệm một phần việc như cấp phát máy, thay thế phần cứng, giám sát nền tảng, sao lưu tự động hoặc failover. Tuy nhiên, khách hàng vẫn chịu trách nhiệm với dữ liệu, schema, tài khoản ứng dụng, quyền truy cập, truy vấn, chính sách lưu giữ, khả năng phục hồi và cách ứng dụng phản ứng khi database gián đoạn.

Ranh giới trách nhiệm thay đổi theo sản phẩm, tier, phiên bản và cấu hình đã mua. Không được suy luận rằng chữ “managed” đồng nghĩa nhà cung cấp đã cấu hình backup phù hợp, bảo đảm mọi thao tác DBA đều có thể thực hiện hoặc tự chịu trách nhiệm khôi phục dữ liệu theo RPO/RTO của doanh nghiệp. Cần đọc rõ hợp đồng dịch vụ, ma trận trách nhiệm và giới hạn kỹ thuật trước khi đưa MySQL vào production.

## 1. Managed MySQL là gì?

Managed MySQL là dịch vụ database trong đó nhà cung cấp quản lý một phần hoặc phần lớn lớp hạ tầng và vòng đời vận hành. Khách hàng tạo instance/cluster, chọn phiên bản và cấu hình tài nguyên qua console, API hoặc infrastructure as code; ứng dụng kết nối qua endpoint do dịch vụ cấp.

Các mô hình thường gặp:

| Mô hình | Nhà cung cấp thường quản lý | Khách hàng vẫn quản lý |
|---|---|---|
| MySQL tự cài trên VM | Máy ảo, một phần mạng và storage theo dịch vụ VM | Hệ điều hành, MySQL, backup, patch, HA, bảo mật DB và monitoring |
| Managed MySQL instance | Hạ tầng, provisioning, một phần patch/backup/monitoring và thao tác quản trị nền tảng | Schema, user/grant, SQL, dữ liệu, cấu hình được phép, kiểm thử backup/restore và ứng dụng |
| Managed MySQL cluster/compatible service | Hạ tầng cluster, replication/failover và một số tính năng quản lý riêng | Mô hình dữ liệu, quyền, truy vấn, giới hạn tương thích, backup policy và DR theo nhu cầu |
| Database platform dùng chung nhiều tenant | Nền tảng database và cách ly tenant | Thiết kế tenant, quota, quyền ứng dụng, bảo vệ dữ liệu và truy vấn trong phạm vi được cấp |

Tên sản phẩm không đủ để xác định mô hình. Một số dịch vụ quản lý MySQL nguyên bản; một số dịch vụ tương thích MySQL nhưng dùng kiến trúc storage/replication riêng. Cần xác minh tính tương thích của SQL, engine, plugin, replication, backup và công cụ vận hành mà ứng dụng phụ thuộc.

## 2. Ma trận trách nhiệm giữa provider và khách hàng

Hãy ghi rõ người chịu trách nhiệm cho từng lớp thay vì dùng một câu chung như “provider quản lý database”. Ma trận dưới đây là điểm khởi đầu; phải điều chỉnh theo hợp đồng và sản phẩm thực tế.

| Hạng mục | Provider thường phụ trách | Khách hàng thường phụ trách |
|---|---|---|
| Phần cứng, host, storage nền | Cấp phát, thay thế và bảo trì nền tảng | Chọn tier/capacity, đánh giá vùng triển khai và chi phí |
| Hệ điều hành | Vá và bảo vệ host trong dịch vụ managed | Không có quyền OS trực tiếp; cung cấp yêu cầu vận hành qua cấu hình dịch vụ |
| MySQL process | Khởi chạy, giám sát tiến trình, một phần patch và nâng cấp | Chọn phiên bản, kiểm thử tương thích, cấu hình được phép và theo dõi hành vi SQL |
| HA/failover | Cơ chế health check, chuyển node hoặc thay thế host theo tier | Chọn topology/tier, kiểm thử ứng dụng reconnect, xác định RTO và xử lý sau failover |
| Backup nền tảng | Thực hiện snapshot/backup theo tính năng và retention đã cấu hình | Bật tính năng, chọn retention, bảo vệ quyền/xóa, kiểm tra restore và đáp ứng yêu cầu tuân thủ |
| Phục hồi dữ liệu | Cung cấp chức năng restore hoặc hỗ trợ theo hợp đồng | Chọn thời điểm, yêu cầu restore, xác minh dữ liệu, cutover và đối soát nghiệp vụ |
| Database user và quyền | Cung cấp account quản trị ban đầu hoặc tích hợp IAM | Quản lý user, role, secret, least privilege và audit |
| Schema và query | Cung cấp engine và tài liệu tương thích | Thiết kế schema, index, transaction, migration và tối ưu SQL |
| Mã hóa và khóa | Cung cấp tùy chọn mã hóa nền tảng/KMS tùy dịch vụ | Chọn key policy, quản lý key lifecycle, quyền truy cập và dữ liệu ở tầng ứng dụng |
| Monitoring | Cung cấp metric/log nền tảng | Đặt alert, dashboard, SLO, phân tích query và trực sự cố |
| Bảo mật dữ liệu | Bảo vệ hạ tầng và ranh giới tenant theo cam kết | Phân loại dữ liệu, kiểm soát truy cập, retention, masking và phản ứng sự cố |

Provider có thể chịu trách nhiệm thực hiện backup job nhưng khách hàng vẫn phải chịu trách nhiệm xác định backup có đáp ứng mục tiêu khôi phục hay không. Backup thành công về mặt kỹ thuật không chứng minh ứng dụng có thể restore và hoạt động bình thường.

## 3. Quyền DBA trong managed service có giới hạn

Trên MySQL tự quản lý, DBA có thể có quyền `root` hệ điều hành và quyền MySQL rất cao. Với managed service, account quản trị do provider cấp thường là account có quyền rộng trong database nhưng không phải MySQL `root` toàn quyền. Một số thao tác bị giới hạn vì có thể ảnh hưởng host, replication, backup hoặc tenant khác.

Các giới hạn thường gặp:

- Không truy cập trực tiếp filesystem, process, service manager hoặc file cấu hình host.
- Không dùng `sudo`, SSH vào host database hoặc đọc file tùy ý bằng `LOAD DATA INFILE`/`SELECT ... INTO OUTFILE`.
- Không có đầy đủ `SUPER`, `FILE`, `SHUTDOWN`, `RELOAD`, `PROCESS` hoặc quyền sửa system schema; dịch vụ có thể thay thế bằng dynamic privilege hoặc procedure riêng.
- Không tự cài plugin, component, UDF hoặc storage engine tùy ý.
- Không tự điều khiển replication thread, binary log retention hoặc failover nội bộ theo cách của server tự quản lý.
- Không thay đổi mọi system variable; chỉ các biến được provider cho phép qua parameter group hoặc API.

Vì vậy, không giả định một runbook dành cho MySQL tự cài có thể chạy nguyên trạng trên dịch vụ managed. Trước khi dùng lệnh DBA, kiểm tra quyền thực tế và tài liệu dịch vụ.

Kiểm tra quyền account:

```sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS;
```

`CURRENT_USER()` cho biết account MySQL thực sự được dùng để kiểm tra quyền; `USER()` cho biết danh tính client gửi trong kết nối. Hai giá trị có thể khác do quy tắc match user/host.

Kiểm tra quyền trên một đối tượng cụ thể:

```sql
SHOW GRANTS FOR 'orders_app'@'%';
```

Không đọc hoặc cập nhật trực tiếp bảng hệ thống để tự cấp quyền. Dùng `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE` hoặc giao diện IAM/provider theo chức năng được hỗ trợ.

## 4. Thiết kế quyền theo least privilege

Không dùng account quản trị dịch vụ cho ứng dụng. Tách account theo vai trò và môi trường:

- Account runtime chỉ có quyền đọc/ghi trên schema và bảng cần thiết.
- Account migration có quyền DDL trong cửa sổ triển khai, được quản lý riêng với runtime.
- Account read-only cho báo cáo, có giới hạn tài nguyên hoặc endpoint riêng nếu dịch vụ hỗ trợ.
- Account backup/export có quyền tối thiểu theo công cụ và cơ chế backup.
- Account monitoring chỉ đọc metric hoặc metadata cần thiết.
- Account break-glass dùng cho sự cố, lưu trong secret manager và audit mọi lần sử dụng.

Ví dụ tạo account ứng dụng và cấp quyền trên một schema:

```sql
CREATE USER 'orders_app'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT SELECT, INSERT, UPDATE, DELETE
ON orders_db.*
TO 'orders_app'@'10.20.%';
```

Mật khẩu trong ví dụ là placeholder. Tạo secret qua quy trình an toàn; không commit vào source code hoặc file cấu hình dùng chung. Host pattern cần phù hợp mạng thực tế và chính sách provider. Nếu dịch vụ hỗ trợ IAM database authentication, đánh giá cơ chế token, thời hạn và cách pool làm mới thông tin xác thực.

Account migration có thể cần quyền `CREATE`, `ALTER`, `INDEX`, `REFERENCES`, `DROP` hoặc quyền bổ sung tùy migration. Không cấp quyền DDL cho account runtime chỉ vì Hibernate đang dùng `ddl-auto=update` trong môi trường phát triển. Production nên quản lý schema bằng pipeline migration có kiểm soát.

### Dùng role để quản lý quyền

MySQL hỗ trợ role trong các phiên bản phù hợp:

```sql
CREATE ROLE 'orders_runtime';
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders_db.* TO 'orders_runtime';

GRANT 'orders_runtime' TO 'orders_app'@'10.20.%';
SET DEFAULT ROLE 'orders_runtime' TO 'orders_app'@'10.20.%';
```

Kiểm tra default role và quyền thực tế sau khi đăng nhập bằng account ứng dụng. Cách provider quản lý account quản trị hoặc IAM có thể khác; một số dịch vụ yêu cầu tạo user qua console/API hoặc không hỗ trợ toàn bộ cú pháp MySQL.

## 5. Backup tự động không đồng nghĩa đã có chiến lược backup

Managed MySQL có thể cung cấp một hoặc nhiều loại bảo vệ dữ liệu:

| Cơ chế | Mục tiêu | Giới hạn cần hiểu |
|---|---|---|
| Automated backup | Sao lưu định kỳ và giữ dữ liệu trong retention window | Có thể cần bật; retention, tần suất và phạm vi khác nhau theo tier |
| Point-in-time recovery (PITR) | Phục hồi tới một thời điểm trong cửa sổ hỗ trợ | Phụ thuộc backup nền và transaction log/binlog được lưu; độ chính xác và giới hạn do provider quy định |
| Manual snapshot | Tạo mốc phục hồi theo yêu cầu trước migration hoặc thay đổi lớn | Có thể tồn tại cùng vòng đời instance; cần bảo vệ quyền xóa và retention |
| Cross-region/cross-account copy | Tăng khả năng phục hồi khi vùng hoặc tài khoản gặp sự cố | Có thể có độ trễ, chi phí, giới hạn region và phụ thuộc encryption key |
| Logical export | Tạo bản sao ở mức schema/table/row để di chuyển hoặc lưu trữ | Tốn thời gian, cần quyền và dung lượng; không tự thay thế PITR liên tục |
| Replica | Phục vụ đọc hoặc tăng khả năng sẵn sàng | Không phải backup độc lập; lỗi xóa/sửa logic có thể được replicate |

Hãy kiểm tra backup đã được bật cho đúng instance/cluster, retention thực tế, thời điểm backup gần nhất, trạng thái job và cách restore. Không suy ra từ việc console có nút “Backups” rằng dữ liệu đang được bảo vệ.

## 6. Xác định RPO và RTO

Hai mục tiêu cần thống nhất với nghiệp vụ:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa doanh nghiệp chấp nhận mất, đo bằng khoảng thời gian dữ liệu trước sự cố.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ về trạng thái sử dụng được.

Ví dụ, RPO 5 phút có nghĩa doanh nghiệp chấp nhận mất tối đa khoảng 5 phút dữ liệu theo kịch bản đã xác định; RTO 60 phút có nghĩa dịch vụ phải hoạt động lại trong vòng 60 phút. Đây là mục tiêu, không phải cam kết tự động của mọi gói managed service.

Chọn backup frequency, PITR window, HA topology và DR region theo RPO/RTO. Một snapshot mỗi ngày không đáp ứng RPO 5 phút nếu không có cơ chế log/PITR bổ sung. Một bản backup có thể phục hồi nhưng mất 8 giờ để restore, kiểm tra và cutover sẽ không đáp ứng RTO 60 phút.

Lập bảng cho từng hệ thống:

| Hệ thống | RPO mục tiêu | RTO mục tiêu | Cơ chế dự kiến | Bằng chứng cần có |
|---|---:|---:|---|---|
| Đơn hàng | 5 phút | 60 phút | Automated backup + PITR, HA và bản sao DR | Restore drill, kiểm tra giao dịch và thời gian cutover |
| Báo cáo | 24 giờ | 8 giờ | Snapshot định kỳ hoặc tái tạo từ nguồn | Kiểm tra export/restore và khả năng dựng lại dữ liệu |
| Audit/ledger | Theo chính sách nghiệp vụ | Theo chính sách nghiệp vụ | Backup nhiều lớp, retention dài, kiểm soát xóa | Đối soát, audit log và bằng chứng phục hồi |

Các giá trị chỉ minh họa. Chủ sở hữu dữ liệu và nghiệp vụ phải phê duyệt mục tiêu thực tế.

## 7. Point-in-time recovery và transaction log

PITR cho phép phục hồi database về một thời điểm nằm trong cửa sổ khôi phục được hỗ trợ. Cơ chế thường kết hợp một backup nền với các thay đổi phát sinh sau backup, được ghi lại qua transaction log hoặc binary log theo kiến trúc dịch vụ.

PITR hữu ích khi:

- Một batch update sai đã commit.
- Người dùng xóa nhầm dữ liệu.
- Migration gây thay đổi không mong muốn.
- Cần dựng môi trường tại thời điểm trước sự cố để điều tra.

PITR không phải nút undo cho một bảng. Nhiều dịch vụ restore ra một instance/cluster mới tại thời điểm được chọn; sau đó DBA cần xác minh, trích xuất hoặc chuyển dữ liệu cần thiết và mới cutover ứng dụng. Cách thức, granularity và giới hạn phụ thuộc provider.

Quy trình khái quát:

```text
Phát hiện sự cố và đóng băng thay đổi liên quan
                 |
                 v
Xác định thời điểm cuối cùng dữ liệu còn đúng
                 |
                 v
Chọn backup nền + thời điểm PITR
                 |
                 v
Restore thành instance/cluster cô lập
                 |
                 v
Kiểm tra schema, dữ liệu, quyền và tính toàn vẹn
                 |
                 v
Đối soát hoặc trích xuất phần dữ liệu cần phục hồi
                 |
                 v
Phê duyệt cutover và chuyển ứng dụng
                 |
                 v
Theo dõi, đối soát và lưu biên bản phục hồi
```

Không restore đè lên database production đang hoạt động nếu chưa hiểu hành vi của dịch vụ và chưa có kế hoạch cutover. Giữ lại instance hiện tại để điều tra khi cần, đồng thời tránh để hai nguồn ghi hoạt động song song ngoài dự kiến.

## 8. Snapshot, logical backup và bản sao độc lập

### Snapshot do provider quản lý

Snapshot thường là bản sao ở lớp storage hoặc cơ chế nhất quán do dịch vụ cung cấp. Nó phù hợp để tạo điểm khôi phục nhanh hoặc clone môi trường. Cần xác minh snapshot có nhất quán theo transaction hay không, có bao gồm toàn bộ cluster/database metadata không, thời gian hoàn tất, retention và cách sao chép sang region/account khác.

Snapshot nằm cùng tài khoản và cùng vùng có thể vẫn bị ảnh hưởng bởi lỗi quyền quản trị, xóa nhầm hoặc sự cố tài khoản. Với dữ liệu quan trọng, cân nhắc bản sao độc lập, quyền xóa tách biệt và retention chống xóa theo chính sách tổ chức.

### Logical backup

Logical backup xuất schema và dữ liệu thành SQL hoặc định dạng có thể nạp lại. Nó hữu ích cho migration, phục hồi một phần, kiểm tra dữ liệu và giảm phụ thuộc vào một định dạng snapshot riêng. Đổi lại, export/import bảng lớn có thể chậm, tạo tải đọc/ghi và cần xử lý quyền, routine, trigger, event, charset, GTID cùng các đối tượng ngoài bảng.

Ví dụ `mysqldump` cho bảng InnoDB:

```bash
mysqldump \
  --host=db.example.internal \
  --user=backup_user \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  orders_db > orders_db.sql
```

Đây là ví dụ cơ bản; xác minh quyền cần thiết, phiên bản client/server, GTID policy và các tùy chọn nhất quán theo dịch vụ. `--single-transaction` tạo snapshot nhất quán cho bảng transactional như InnoDB, nhưng không bảo vệ trước DDL đồng thời làm thay đổi cấu trúc trong lúc dump. Nó cũng không tạo snapshot nhất quán cho non-transactional table. Không đặt password trực tiếp trong command line; dùng login path, secret injection hoặc cơ chế credential an toàn của môi trường chạy.

Với database lớn, đánh giá công cụ export song song như MySQL Shell hoặc công cụ backup được provider hỗ trợ. Kiểm tra liệu dịch vụ cho phép kết nối replica để giảm tải backup và liệu replica có lag hay không. Không chạy dump nặng trên production mà không đo tác động.

### Không lưu backup duy nhất cạnh database

Bản sao backup nên có quyền truy cập, vòng đời và phạm vi lỗi độc lập phù hợp với mô hình đe dọa. Cân nhắc:

- Sao chép sang tài khoản hoặc project backup riêng.
- Sao chép sang region khác khi yêu cầu DR cần bảo vệ khỏi sự cố vùng.
- Mã hóa bằng key có policy và vòng đời được quản lý.
- Retention lock/immutability nếu dịch vụ hỗ trợ và chính sách yêu cầu.
- Tài khoản restore riêng, không dùng cùng credential runtime.
- Audit thao tác tạo, copy, restore và xóa backup.

## 9. HA, read replica và backup giải quyết vấn đề khác nhau

High availability và backup không thay thế nhau.

| Cơ chế | Bảo vệ trước | Không bảo vệ đầy đủ trước |
|---|---|---|
| Multi-zone/standby failover | Lỗi host hoặc zone theo thiết kế dịch vụ | Xóa nhầm, cập nhật sai, ransomware hoặc lỗi logic được ghi hợp lệ |
| Read replica | Tăng năng lực đọc, một số kịch bản DR/failover | Dữ liệu sai được replicate; replica có thể lag hoặc cùng vùng lỗi |
| Automated backup/PITR | Khôi phục dữ liệu lịch sử sau lỗi logic hoặc mất dữ liệu | Mọi dạng gián đoạn tức thời; RTO có thể dài hơn HA |
| Snapshot độc lập | Khôi phục về một mốc đã tạo | Các thay đổi sau snapshot nếu không có PITR |
| Logical export | Di chuyển/khôi phục chọn lọc và lưu trữ độc lập | Khôi phục nhanh cho database rất lớn nếu chưa được tối ưu |

Một replica có thể giúp đọc hoặc giảm thời gian chuyển đổi khi primary lỗi, nhưng nếu một câu `DELETE` không có `WHERE` được replicate thì replica cũng nhận lệnh xóa. Cần backup và PITR để phục hồi trạng thái trước thao tác sai.

Tương tự, multi-zone failover giúp dịch vụ tiếp tục hoạt động khi một node lỗi, nhưng không phục hồi bản ghi đã bị xóa hợp lệ về mặt SQL. HA tập trung vào availability; backup tập trung vào recoverability.

## 10. Restore drill là bằng chứng backup có thể dùng

Một backup job màu xanh trong dashboard chỉ chứng minh provider báo job hoàn tất. Nó không chứng minh:

- Bản backup có đủ database, schema, trigger, routine, event và metadata cần thiết.
- Key mã hóa vẫn còn và restore account có quyền sử dụng key.
- Bản restore có thể khởi động với phiên bản MySQL/parameter tương thích.
- Ứng dụng có thể kết nối, đăng nhập và chạy truy vấn quan trọng.
- Dữ liệu khôi phục đáp ứng yêu cầu RPO.
- Tổng thời gian restore, kiểm tra và cutover đáp ứng RTO.

Thực hiện restore drill theo lịch và sau các thay đổi quan trọng:

1. Chọn một backup hoặc mốc PITR trong cửa sổ retention.
2. Restore vào môi trường cô lập, không trỏ traffic production vào đó.
3. Kiểm tra server version, schema, account, grants, charset/collation và parameter cần thiết.
4. Chạy kiểm tra toàn vẹn: số dòng, tổng tiền, khóa ngoại, checksum hoặc đối soát nghiệp vụ.
5. Chạy smoke test ứng dụng và truy vấn quan trọng.
6. Đo thời gian từ lúc bắt đầu restore đến khi dịch vụ sẵn sàng.
7. Ghi nhận dữ liệu gần nhất có thể khôi phục và sai lệch so với RPO.
8. Dọn môi trường test theo quy trình và lưu bằng chứng.

Restore drill nên kiểm tra cả quyền vận hành: người trực có thể tìm backup, yêu cầu restore, truy cập key và thực hiện cutover theo runbook hay không. Không để quy trình chỉ phụ thuộc một cá nhân có quyền đặc biệt.

## 11. Bảo mật backup và encryption key

Backup thường chứa toàn bộ dữ liệu nhạy cảm của database. Mã hóa at-rest không đủ nếu quá nhiều người có quyền restore, export hoặc đọc bản dump đã giải mã.

Kiểm soát cần có:

- Mã hóa backup theo khả năng provider và yêu cầu dữ liệu.
- Phân quyền riêng cho tạo, đọc, copy, restore và xóa backup.
- Tách key quản lý backup khỏi quyền runtime khi phù hợp.
- Xác định key rotation, disable, revoke và recovery policy.
- Kiểm tra backup copy ở region/account khác có dùng key truy cập được tại nơi khôi phục.
- Mã hóa file logical dump khi lưu và truyền; hạn chế thời gian tồn tại của file tạm.
- Không gửi dump qua email, ticket hoặc kho artifact công khai.
- Audit truy cập và thao tác restore/export.
- Áp dụng retention và xóa an toàn theo yêu cầu pháp lý/nghiệp vụ.

Nếu encryption key bị xóa hoặc mất quyền truy cập, backup mã hóa có thể không còn khôi phục được. Key lifecycle là một phần của chiến lược backup, không phải công việc riêng của nhóm security.

## 12. Monitoring và vận hành trong phạm vi được cấp

Managed service thường cung cấp dashboard hoặc API metric. Các metric quan trọng:

- CPU, memory, storage used, storage growth và I/O latency.
- Database connections, active sessions, connection errors và pool saturation.
- Query latency, slow query log, rows examined và deadlock.
- Buffer pool hit/miss, temporary tables, redo/log pressure nếu dịch vụ expose.
- Replica lag, replication health và trạng thái failover.
- Backup status, backup age, retention và dung lượng snapshot.
- Maintenance events, restart, failover và version lifecycle.

Không phải dịch vụ nào cũng expose toàn bộ metric InnoDB hoặc cho phép đọc mọi Performance Schema table. Nếu thiếu quyền hoặc metric, tìm metric tương đương qua provider API, enhanced monitoring hoặc log export. Không cố truy cập host để lấy chỉ số mà dịch vụ không cho phép.

Ví dụ kiểm tra trạng thái trong MySQL nếu quyền được cấp:

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks';
SHOW FULL PROCESSLIST;
```

Kết hợp metric provider với query digest/slow log để phân biệt CPU cao do SQL, connection pool quá lớn, storage chậm hay workload tăng đột biến. Đặt alert theo SLO và xu hướng; một ngưỡng CPU đơn lẻ không đủ để xác định sự cố.

## 13. Parameter group và thay đổi cấu hình

Managed service thường không cho sửa trực tiếp `my.cnf`. Thay vào đó, provider cung cấp parameter group hoặc cấu hình qua API. Biến có thể được phân loại:

- Dynamic: áp dụng ngay hoặc sau khi tạo session mới.
- Static: cần restart instance/cluster hoặc maintenance window.
- Unsupported/locked: provider không cho thay đổi.
- Provider-specific: tên hoặc semantics khác MySQL tự quản lý.

Trước khi thay đổi:

1. Kiểm tra biến có được hỗ trợ trên engine/version/tier hiện tại không.
2. Xác định phạm vi global/session và cần restart hay không.
3. Đọc giá trị hiện tại và giá trị mặc định của provider.
4. Thử trên staging với workload đại diện.
5. Đánh giá tác động tới failover, replica và session đang tồn tại.
6. Lên lịch, thông báo và chuẩn bị phương án khôi phục cấu hình.

Không copy toàn bộ `my.cnf` từ server tự quản lý sang parameter group. Một số biến do provider kiểm soát hoặc không tương thích với kiến trúc dịch vụ. Đổi biến như `max_connections`, `innodb_buffer_pool_size` hoặc redo capacity có thể bị giới hạn bởi tier và memory budget.

## 14. Maintenance, patch và nâng cấp phiên bản

Provider có thể thực hiện patch host, patch MySQL, restart hoặc failover theo maintenance window. Khách hàng cần biết:

- Lịch bảo trì có thể cấu hình hay provider tự lên lịch.
- Có thông báo trước bao lâu và kênh thông báo nào.
- Dịch vụ có thể restart/failover trong lúc bảo trì hay không.
- Minor/major version upgrade có cần thao tác phê duyệt riêng không.
- Có thể trì hoãn maintenance đến giới hạn nào.
- Replica, connector, plugin và migration có tương thích với phiên bản mới không.

Ứng dụng phải chịu được connection reset và reconnect. Không giả định endpoint luôn trỏ tới cùng IP hoặc connection cũ tồn tại sau failover. Dùng DNS/endpoint do provider cấp, connection pool có lifecycle phù hợp và retry idempotent ở ranh giới transaction.

Với major upgrade, kiểm thử SQL mode, authentication plugin, collation, optimizer plan, deprecated/removed features, driver và stored program. Chạy migration trên bản clone có dữ liệu gần production, đo thời gian và chuẩn bị rollback/forward-fix theo giới hạn của dịch vụ. Một số managed service không hỗ trợ downgrade tại chỗ; phương án quay lui có thể là restore backup sang instance cũ và chuyển traffic.

## 15. Network và endpoint của managed MySQL

Dịch vụ managed thường có endpoint DNS thay vì yêu cầu khách hàng dùng địa chỉ IP cố định. Có thể có nhiều endpoint:

- Writer/primary endpoint cho thao tác ghi.
- Reader endpoint phân phối kết nối tới replica.
- Instance endpoint để kết nối một node cụ thể khi điều tra.
- Private endpoint hoặc private IP chỉ truy cập từ network được liên kết.

Tên và semantics khác nhau theo provider. Reader endpoint có thể phân phối theo connection, không nhất thiết theo từng câu query; connection pool giữ session lâu nên phân phối không đồng đều. Replica có thể lag, do đó ứng dụng không nên đọc ngay từ reader endpoint nếu cần read-after-write mạnh mà chưa có cơ chế bảo đảm.

Thiết lập bảo mật mạng:

- Ưu tiên private network/private endpoint nếu kiến trúc cho phép.
- Giới hạn security group/firewall theo source workload và port cần thiết.
- Bật TLS và xác minh CA/hostname theo hướng dẫn provider.
- Không mở MySQL port ra Internet chỉ để thuận tiện kiểm tra.
- Quản lý DNS cache và connection pool để ứng dụng theo kịp failover.
- Tách quyền network khỏi quyền database; cho phép đi tới endpoint không có nghĩa có quyền SQL.

## 16. Chi phí và giới hạn dịch vụ

Managed service giảm công việc vận hành hạ tầng nhưng tạo các chi phí và giới hạn cần dự trù:

- Instance/compute tier và khả năng scale up/down.
- Storage provisioned, autoscaling, IOPS và throughput.
- Automated backup, snapshot retention và backup copy.
- Cross-region replication, network egress và data transfer.
- Log export, monitoring nâng cao và thời gian lưu log.
- Read replica, standby và môi trường DR.
- Support tier, maintenance và các thao tác restore.

Storage autoscaling không đồng nghĩa storage có thể giảm lại khi dữ liệu bị xóa. Một số dịch vụ chỉ tăng dung lượng và không cho thu nhỏ trực tiếp. Backup retention dài có thể làm chi phí tăng theo dung lượng thay đổi. Cần tính cả chi phí bản sao DR và thời gian giữ snapshot cũ.

Đọc quota như số connection tối đa, số replica, kích thước storage, giới hạn IOPS, packet/statement, số database và giới hạn import/export. Thiết kế ứng dụng theo quota thực tế; không coi giới hạn của một tier thử nghiệm là giới hạn chung của mọi tier.

## 17. Kế hoạch backup và DR theo nhiều lớp

Một chiến lược production có thể gồm:

1. Automated backup/PITR đáp ứng RPO vận hành hằng ngày.
2. Snapshot thủ công trước migration, thay đổi lớn hoặc thao tác rủi ro.
3. Copy backup sang vùng/tài khoản độc lập nếu yêu cầu DR và bảo vệ khỏi xóa nhầm.
4. Logical export định kỳ hoặc theo nhu cầu portability/khôi phục chọn lọc.
5. Read replica hoặc standby cho availability/đọc, không tính như bản backup duy nhất.
6. Restore drill định kỳ và sau thay đổi provider, version, key hoặc retention.
7. Runbook khôi phục, danh sách owner, quyền break-glass và quy trình phê duyệt cutover.

Không phải mọi hệ thống đều cần đủ mọi lớp. Chọn theo phân loại dữ liệu, RPO/RTO, chi phí và rủi ro. Điều bắt buộc là mọi lớp được chọn phải có owner, retention, kiểm soát quyền và bằng chứng phục hồi.

## 18. Runbook phục hồi khi managed MySQL gặp sự cố

Khi có sự cố, trước tiên xác định loại lỗi:

| Tình huống | Hướng xử lý ban đầu |
|---|---|
| Instance/host lỗi nhưng HA còn hoạt động | Theo dõi failover, endpoint và ứng dụng reconnect; không tự restore nếu dịch vụ đang phục hồi |
| Xóa nhầm hoặc cập nhật sai dữ liệu | Dừng job gây lỗi, xác định thời điểm cuối đúng, dùng PITR/snapshot để dựng bản cô lập và trích xuất dữ liệu |
| Region hoặc account không truy cập được | Kích hoạt DR plan, kiểm tra backup copy, key, DNS/network và quyền tại vùng đích |
| Backup job thất bại | Xác định khoảng trống bảo vệ, sửa quyền/quota/storage, chạy backup lại và đánh giá RPO |
| Không restore được do key/quyền | Kích hoạt owner key/IAM, không xóa hoặc rotate key tiếp cho tới khi khả năng giải mã được xác minh |
| Replica lag hoặc applier lỗi | Xác định replica có còn phù hợp để đọc/failover; không promote chỉ vì primary chậm |

Trình tự phục hồi dữ liệu:

1. Chỉ định incident commander và người chịu trách nhiệm dữ liệu.
2. Ghi lại thời điểm sự cố, phạm vi ảnh hưởng và thay đổi gần nhất.
3. Dừng hoặc hạn chế writer gây lỗi nếu có thể làm tăng thiệt hại.
4. Xác định mục tiêu restore và nguồn backup phù hợp.
5. Tạo restore target cô lập; giữ nguồn hiện tại để điều tra nếu cần.
6. Kiểm tra quyền, key, version, schema và tính toàn vẹn.
7. Đối soát dữ liệu và phê duyệt điểm cutover.
8. Chuyển endpoint/traffic theo runbook, kiểm tra connection pool và ứng dụng.
9. Theo dõi lỗi, latency, replication, dữ liệu phát sinh và hoàn tất đối soát.
10. Ghi nhận RPO/RTO thực tế, nguyên nhân và hành động phòng ngừa.

## 19. Tình huống thực hành

Một ứng dụng thương mại điện tử dùng managed MySQL single-writer với một reader replica. Đội vận hành giả định provider tự backup nên chưa từng thử restore. Một migration lỗi xóa nhầm dữ liệu đơn hàng trong một khoảng thời gian ngắn; replica cũng đã nhận thao tác xóa.

**Bước 1 — Xác định trách nhiệm.** Kiểm tra hợp đồng dịch vụ, automated backup đang bật hay không, retention window, PITR có sẵn không, ai có quyền restore và backup copy nằm ở đâu.

**Bước 2 — Dừng thiệt hại.** Dừng migration/job gây lỗi, hạn chế writer nếu cần và ghi lại thời điểm bắt đầu thao tác sai. Không promote reader replica vì dữ liệu xóa đã được replicate.

**Bước 3 — Chọn điểm khôi phục.** Xác định thời điểm ngay trước lệnh xóa. Dùng PITR để tạo một instance mới trong network cô lập; giữ database hiện tại để phục vụ điều tra.

**Bước 4 — Kiểm tra dữ liệu.** Đối chiếu số đơn, tổng tiền, trạng thái, foreign key và một số mẫu bản ghi. Xác nhận schema, grants và ứng dụng có thể đọc dữ liệu trên restore target.

**Bước 5 — Phục hồi chọn lọc.** Nếu chỉ một nhóm đơn bị xóa, trích xuất các bản ghi liên quan và quan hệ con từ restore target, rồi nhập lại production bằng quy trình idempotent và đối soát. Nếu cần rollback toàn bộ database, lên kế hoạch cutover và xử lý các giao dịch hợp lệ phát sinh sau thời điểm restore.

**Bước 6 — Đo RPO/RTO.** Ghi lại thời gian dữ liệu cuối cùng được khôi phục, thời gian restore, kiểm tra và cutover. So sánh với mục tiêu đã phê duyệt.

**Bước 7 — Cải thiện.** Thiết lập restore drill định kỳ, snapshot trước migration, quyền xóa backup tách biệt, phê duyệt migration phá hủy và alert khi backup quá hạn hoặc thất bại.

Tình huống cho thấy HA và replica không bảo vệ khỏi lỗi logic đã được replicate. Backup/PITR cùng quy trình restore được diễn tập mới tạo được khả năng phục hồi dữ liệu.

## 20. Checklist trước khi đưa managed MySQL vào production

- [ ] Đã xác định mô hình dịch vụ và tính tương thích MySQL thực tế.
- [ ] Có ma trận trách nhiệm provider/customer cho patch, HA, backup, restore, monitoring và security.
- [ ] Đã xác nhận quyền DBA bị giới hạn và các thao tác thay thế qua provider API/console.
- [ ] Runtime, migration, reporting, backup và monitoring dùng account riêng theo least privilege.
- [ ] Đã xác nhận automated backup được bật, retention đúng và backup job có trạng thái theo dõi.
- [ ] PITR window đáp ứng RPO và đã biết cách chọn thời điểm restore.
- [ ] Snapshot/backup được bảo vệ khỏi xóa nhầm và có bản sao độc lập nếu yêu cầu DR cần thiết.
- [ ] Encryption key còn khả dụng tại nơi và thời điểm restore; quyền key được kiểm thử.
- [ ] Đã thực hiện restore drill trên môi trường cô lập và đo RTO/RPO thực tế.
- [ ] Đã phân biệt HA failover, read replica, snapshot và PITR.
- [ ] Ứng dụng xử lý connection reset, reconnect và retry idempotent sau failover.
- [ ] Đã cấu hình private network, firewall, TLS và endpoint phù hợp.
- [ ] Đã kiểm tra parameter group, maintenance window, version lifecycle và quy trình upgrade.
- [ ] Có metric/alert cho CPU, storage, connections, latency, replica lag và backup status.
- [ ] Đã dự trù chi phí compute, storage, backup retention, replica, DR và data transfer.
- [ ] Có runbook phục hồi, owner, quyền break-glass và quy trình cutover được diễn tập.

Managed MySQL chuyển một phần công việc hạ tầng sang nhà cung cấp nhưng không chuyển toàn bộ trách nhiệm dữ liệu. Khách hàng cần hiểu giới hạn quyền DBA, tự thiết kế quyền ứng dụng, xác nhận backup/PITR, bảo vệ encryption key và diễn tập restore theo RPO/RTO. HA, replica và backup giải quyết các loại rủi ro khác nhau; chỉ khi ranh giới trách nhiệm, quyền vận hành và quy trình phục hồi được xác minh thì dịch vụ managed mới đáp ứng được yêu cầu production.
