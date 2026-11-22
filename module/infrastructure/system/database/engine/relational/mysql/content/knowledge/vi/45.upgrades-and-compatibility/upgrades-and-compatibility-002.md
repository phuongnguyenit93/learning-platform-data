# Release note, tính năng bị loại bỏ và biến cấu hình thay đổi

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này hướng dẫn đọc release note và chuyển các thông tin về tính năng mới, tính năng lỗi thời, tính năng bị loại bỏ cùng thay đổi biến cấu hình thành kế hoạch nâng cấp có thể kiểm thử.

Nâng cấp MySQL không chỉ là thay binary server. Một phiên bản mới có thể loại bỏ tùy chọn khởi động, đổi tên câu lệnh, thay plugin xác thực, thay giá trị mặc định của biến hoặc thay đổi hành vi optimizer. Những thay đổi này có thể làm server không khởi động, ứng dụng không đăng nhập được, replication dừng hoặc workload có hiệu năng khác trước. Vì vậy, cần đối chiếu release note theo từng phiên bản, kiểm kê cấu hình đang có hiệu lực và kiểm thử tương thích trước khi nâng cấp production.

## 1. Release note cho biết điều gì?

Release note là tài liệu ghi lại các thay đổi của một bản phát hành. Với MySQL, cần đọc cả release note của server, Reference Manual và tài liệu của connector hoặc plugin mà hệ thống đang sử dụng.

Các mục quan trọng thường gồm:

| Nhóm thay đổi | Ý nghĩa | Câu hỏi cần trả lời khi nâng cấp |
|---|---|---|
| Added | Tính năng, câu lệnh, biến hoặc tùy chọn mới. | Tính năng nào có thể giúp hệ thống? Có yêu cầu cấu hình hoặc quyền mới không? |
| Changed | Hành vi, giá trị mặc định, giới hạn hoặc cách thực thi thay đổi. | Workload hiện tại có bị ảnh hưởng dù không sửa cấu hình không? |
| Deprecated | Tính năng vẫn còn nhưng đã bị đánh dấu lỗi thời và có thể bị loại bỏ ở bản sau. | Mã nguồn, script, config và công cụ nào còn dùng tính năng này? |
| Removed | Tính năng, biến, tùy chọn hoặc cú pháp đã bị loại bỏ. | Thành phần nào sẽ lỗi ngay khi chạy trên phiên bản đích? |
| Fixed | Lỗi đã được sửa. | Bản sửa có thay đổi hành vi mà ứng dụng hoặc quy trình đang dựa vào không? |
| Security | Lỗ hổng hoặc thay đổi bảo mật. | Có cần thay plugin, chứng chỉ, quyền, giao thức hoặc quy trình vận hành không? |

Không chỉ đọc phần “What is New”. Cần đọc các mục deprecation/removal, configuration notes, security notes, replication notes, InnoDB notes, SQL syntax notes và các bug fix liên quan đến workload đang chạy. Một thay đổi mặc định có thể quan trọng ngang với một tính năng bị xóa, dù không tạo lỗi cú pháp.

## 2. Xác định đúng phiên bản nguồn và phiên bản đích

Trước khi so sánh release note, ghi lại phiên bản chính xác của từng môi trường:

```sql
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;
```

Kiểm tra thêm phiên bản binary của server và client:

```bash
mysqld --version
mysql --version
```

Hai giá trị này có thể khác nhau vì client và server được cài từ các gói hoặc lịch nâng cấp khác nhau. Trong hệ thống có nhiều node, cần lập danh sách phiên bản của source, replica, máy chủ backup, công cụ quản trị và các connector ứng dụng.

### Đọc release note theo từng bước nâng cấp

Không chỉ so sánh release note của bản nguồn với bản đích nếu quá trình nâng cấp đi qua nhiều nhánh. Hãy đọc thay đổi của từng phiên bản trung gian mà quy trình hỗ trợ, đặc biệt khi đi từ MySQL 5.7 lên 8.0 hoặc từ 8.0 lên 8.4.

Ví dụ, một hệ thống nâng từ 8.0.22 lên 8.4 cần rà soát thay đổi từ các bản 8.0 tiếp theo, các thay đổi trong dòng 8.1/8.2/8.3 nếu chúng nằm trong lộ trình đã chọn, và các yêu cầu riêng của 8.4. Không được giả định rằng tính năng còn hoạt động ở bản nguồn sẽ còn tồn tại trong bản đích.

MySQL có các dòng phát hành với chính sách hỗ trợ khác nhau. Cần xác định dòng LTS hoặc Innovation phù hợp với chính sách vận hành, sau đó chọn đúng tài liệu của dòng đó. Đọc trang release note tương ứng với phiên bản thực tế, không sao chép cấu hình từ một bài viết cũ chỉ vì số phiên bản có cùng major.

## 3. Phân biệt deprecated, removed và changed default

Ba trạng thái này có mức độ ảnh hưởng khác nhau:

1. **Deprecated:** tính năng còn dùng được nhưng đã có cảnh báo hoặc tài liệu khuyến nghị chuyển sang cách mới. Đây là thời điểm thích hợp để sửa code và config trước khi nâng cấp tiếp.
2. **Removed:** tính năng không còn được server cung cấp. Câu lệnh, biến hoặc tùy chọn có thể gây lỗi khi khởi động hoặc khi ứng dụng thực thi.
3. **Changed default:** tên biến vẫn hợp lệ nhưng giá trị mặc định thay đổi. Server có thể khởi động bình thường, trong khi hiệu năng, hành vi replication, bảo mật hoặc sử dụng tài nguyên thay đổi.

Không nên coi cảnh báo deprecation là lỗi có thể bỏ qua mãi. Nếu tiếp tục dùng tính năng lỗi thời, mỗi lần nâng cấp sau sẽ tăng rủi ro và chi phí xử lý gấp. Hãy lập danh sách deprecation, người phụ trách, phiên bản cần thay thế và thời hạn hoàn thành.

## 4. Một số thay đổi thực tế cần biết khi đi từ MySQL 8.0 lên 8.4

Các ví dụ sau minh họa cách đọc mốc phiên bản. Danh sách không thay thế release note đầy đủ của phiên bản đích.

### Câu lệnh replication đổi thuật ngữ

Từ MySQL 8.0.23, `CHANGE MASTER TO` được đánh dấu deprecated; câu lệnh mới là `CHANGE REPLICATION SOURCE TO`. Các tên như `START SLAVE`, `STOP SLAVE`, `SHOW SLAVE STATUS` cũng có tên mới tương ứng:

| Cú pháp cũ | Cú pháp mới nên dùng |
|---|---|
| `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` |
| `START SLAVE` | `START REPLICA` |
| `STOP SLAVE` | `STOP REPLICA` |
| `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` |
| `RESET SLAVE` | `RESET REPLICA` |

Ví dụ cấu hình kết nối replica bằng cú pháp mới:

```sql
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST = 'mysql-source.example.net',
    SOURCE_USER = 'replication_user',
    SOURCE_PASSWORD = 'LAY_TU_KHO_BI_MAT',
    SOURCE_AUTO_POSITION = 1;

START REPLICA;
SHOW REPLICA STATUS\G
```

Mật khẩu trong ví dụ chỉ là chỗ giữ chỗ. Hãy lấy bí mật từ secret manager và tránh ghi thông tin xác thực vào file migration hoặc log. Khi nâng cấp, tìm cả câu lệnh cũ trong script triển khai, runbook, job định kỳ, công cụ monitoring và tài liệu vận hành. Một lệnh có thể không nằm trong mã ứng dụng nhưng vẫn được chạy mỗi khi DBA xử lý sự cố.

### Plugin xác thực mysql_native_password

`mysql_native_password` được đánh dấu deprecated từ MySQL 8.0.34, bị tắt mặc định từ MySQL 8.4.0 và bị loại bỏ khỏi server ở MySQL 9.0.0. Một tài khoản vẫn dùng plugin này có thể không đăng nhập được sau khi nâng cấp lên 8.4 nếu plugin không được bật lại.

Kiểm tra tài khoản đang dùng plugin nào:

```sql
SELECT user, host, plugin
FROM mysql.user
ORDER BY user, host;
```

Kiểm tra danh sách plugin đang hoạt động:

```sql
SHOW PLUGINS;
```

Kế hoạch chuyển đổi thường là xác nhận driver/client hỗ trợ `caching_sha2_password`, nâng cấp connector nếu cần, sau đó đổi tài khoản trong môi trường thử nghiệm:

```sql
ALTER USER 'app_user'@'10.20.5.18'
    IDENTIFIED WITH caching_sha2_password
    BY 'MAT_KHAU_MOI_LAY_TU_VAULT';
```

Kiểm thử kết nối TLS, cơ chế lấy public key khi cần, pool kết nối và các tác vụ nền trước khi áp dụng cho tài khoản production. Không bật lại plugin cũ như một giải pháp lâu dài nếu mục tiêu là nâng cấp lên phiên bản đã loại bỏ plugin đó.

### Biến default_authentication_plugin bị loại bỏ

Biến `default_authentication_plugin` được đánh dấu deprecated từ MySQL 8.0.27 và bị loại bỏ trong MySQL 8.4.0. Tài liệu MySQL 8.4 hướng dẫn dùng `authentication_policy` thay thế.

Nếu file cấu hình còn dòng:

```ini
[mysqld]
default_authentication_plugin=caching_sha2_password
```

cần rà soát và chuyển sang cấu hình chính sách xác thực phù hợp với yêu cầu thực tế của phiên bản đích. Không thay tên biến máy móc mà chưa hiểu cú pháp và chính sách của `authentication_policy`; hãy đọc mô tả biến trong Reference Manual của đúng phiên bản. Đồng thời kiểm tra cách tạo user trong provisioning script vì plugin xác thực của tài khoản hiện có không tự thay đổi chỉ vì default của server thay đổi.

### Biến expire_logs_days bị loại bỏ

`expire_logs_days` bị loại bỏ từ MySQL 8.2.0. Cấu hình giữ binary log nên dùng `binlog_expire_logs_seconds`:

```ini
[mysqld]
binlog_expire_logs_seconds=1209600
```

Giá trị trên tương ứng 14 ngày. Chọn thời hạn dựa trên thời gian replica có thể offline, thời gian dựng lại, delayed replica, consumer CDC và nhu cầu point-in-time recovery. Trước khi nâng cấp, kiểm tra mọi file cấu hình, automation và dashboard còn đọc/ghi `expire_logs_days`.

### Tùy chọn SSL cũ và biến trạng thái TLS

Các tùy chọn server `--ssl`, `--admin-ssl` và các biến `have_ssl`, `have_openssl` được đánh dấu deprecated trong MySQL 8.0.26 và bị loại bỏ ở MySQL 8.4.0. Release note hướng dẫn dùng `--tls-version` và `--admin-tls-version` cho cấu hình phiên bản giao thức TLS. Khi kiểm tra trạng thái kết nối, hãy dùng các biến và chỉ số TLS hiện được hỗ trợ trong phiên bản đích thay vì phụ thuộc vào `have_ssl` hoặc `have_openssl`.

Đối với kết nối ứng dụng, kiểm tra CA, certificate, private key, TLS version, cipher và xác minh danh tính máy chủ. Không chỉ xóa tùy chọn cũ rồi cho rằng kết nối vẫn được mã hóa như mong đợi.

## 5. Thay đổi giá trị mặc định của InnoDB trong MySQL 8.4

Một nâng cấp có thể không báo lỗi nhưng vẫn làm workload thay đổi vì các biến giữ nguyên tên nhưng có default khác. Ví dụ, một số giá trị mặc định InnoDB trong MySQL 8.4 khác MySQL 8.0:

| Biến | Mặc định MySQL 8.0 | Mặc định MySQL 8.4 | Khía cạnh cần kiểm thử |
|---|---:|---:|---|
| `innodb_change_buffering` | `all` | `none` | Hành vi ghi và I/O với secondary index. |
| `innodb_adaptive_hash_index` | `ON` | `OFF` | Hiệu năng workload đọc có truy cập lặp lại. |
| `innodb_log_buffer_size` | 16 MiB | 64 MiB | Bộ nhớ sử dụng và transaction ghi lớn. |
| `innodb_io_capacity` | 200 | 10000 | Tốc độ background I/O và khả năng của storage. |
| `innodb_flush_method` trên Linux | `fsync` | `O_DIRECT` nếu được hỗ trợ, nếu không thì `fsync` | Hành vi I/O, cache hệ điều hành và thiết bị lưu trữ. |
| `temptable_max_ram` | 1 GiB | 3% tổng bộ nhớ, giá trị mặc định nằm trong khoảng 1–4 GiB | Mức dùng RAM của temporary table. |

Các giá trị trong bảng là mặc định của các phiên bản được nêu, không phải khuyến nghị áp dụng giống nhau cho mọi máy chủ. Nếu file cấu hình không đặt biến, phiên bản mới có thể dùng default mới. Nếu file cấu hình có giá trị tường minh, server có thể tiếp tục dùng giá trị đó, miễn biến vẫn còn được hỗ trợ. Vì vậy, phải so sánh cả giá trị mặc định lẫn giá trị runtime thực tế.

## 6. Kiểm kê biến cấu hình đang có hiệu lực

Không nên chỉ tìm trong `my.cnf` hoặc `my.ini`. Giá trị cấu hình có thể đến từ file include, command line, biến runtime, `SET PERSIST` hoặc giá trị mặc định của server.

### Lấy danh sách biến runtime

```sql
SHOW GLOBAL VARIABLES;
```

Hoặc truy vấn có thể sắp xếp/lọc:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_variables
ORDER BY VARIABLE_NAME;
```

### Tìm nguồn thiết lập biến

Trên phiên bản hỗ trợ `performance_schema.variables_info`, có thể xem nguồn của giá trị hiện tại:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'default_authentication_plugin',
    'binlog_expire_logs_seconds',
    'innodb_change_buffering',
    'innodb_adaptive_hash_index'
)
ORDER BY VARIABLE_NAME;
```

Tên biến đã bị loại bỏ có thể không xuất hiện trong runtime view của phiên bản đích. Trên phiên bản cũ, `VARIABLE_SOURCE` và `VARIABLE_PATH` giúp xác định giá trị đến từ command line, option file, persisted value hoặc default. Hãy kiểm tra cấu trúc Performance Schema theo đúng bản server.

### Kiểm tra giá trị được lưu bằng SET PERSIST

```sql
SELECT *
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
```

Các giá trị persist được lưu riêng với file cấu hình thông thường. Một biến không còn tồn tại có thể gây cảnh báo hoặc làm server không khởi động tùy phiên bản và cách cấu hình. Hãy kiểm tra danh sách này trước khi nâng cấp, đồng thời lưu lại bản sao để đối chiếu và xử lý có kiểm soát.

### Tìm option trong file cấu hình và script

Kiểm kê toàn bộ file cấu hình chính, file include, service unit, container entrypoint, Helm chart, Ansible/Terraform, script backup/restore, provisioning, monitoring và runbook. Ví dụ tìm các tên đã biết trong thư mục cấu hình Linux:

```bash
grep -RniE 'default_authentication_plugin|expire_logs_days|have_ssl|have_openssl|master_info_repository|relay_log_info_repository' /etc/mysql /etc/my.cnf* 2>/dev/null
```

Trên Windows, kiểm tra file `my.ini`, thư mục cấu hình MySQL và service command line. Lệnh grep chỉ là ví dụ cho Linux; hãy dùng công cụ tìm kiếm phù hợp với hệ điều hành và cấu trúc triển khai thực tế.

## 7. Kiểm tra tương thích trước khi nâng cấp

### Dùng MySQL Shell Upgrade Checker

MySQL Shell có tiện ích `util.checkForServerUpgrade()` để kiểm tra một máy chủ nguồn với phiên bản đích, phát hiện một số vấn đề về cấu trúc, cú pháp, tính năng và cấu hình có thể cản trở nâng cấp.

Ví dụ trong MySQL Shell ở chế độ JavaScript, sau khi kết nối đến máy chủ nguồn:

```javascript
util.checkForServerUpgrade({
    targetVersion: "8.4.0"
});
```

Thay `8.4.0` bằng phiên bản đích thực tế. Đọc toàn bộ kết quả và xử lý từng lỗi/cảnh báo. Upgrade Checker không thay thế việc đọc release note, kiểm thử ứng dụng, kiểm tra plugin bên thứ ba hoặc thử phục hồi backup.

### Kiểm tra cấu hình server trước khi restart

Với phiên bản hỗ trợ, có thể dùng:

```bash
mysqld --defaults-file=/etc/my.cnf --validate-config
```

Lệnh này giúp kiểm tra một số lỗi trong option file mà không cần khởi động server bình thường. Cú pháp đường dẫn phải điều chỉnh theo hệ điều hành và vị trí file cấu hình. Kết quả kiểm tra cấu hình không chứng minh toàn bộ plugin, ứng dụng hoặc replication sẽ tương thích.

### Kiểm tra kết nối và plugin

Lập danh sách driver và connector theo ứng dụng: Java Connector/J, .NET, Python, Node.js, PHP, ODBC, JDBC pool, ORM, proxy và công cụ quản trị. Xác minh phiên bản driver hỗ trợ giao thức xác thực, TLS và server version mục tiêu. Kiểm tra plugin, component, UDF và engine bên thứ ba vì một số plugin có thể bị đổi API hoặc loại bỏ giữa các phiên bản.

## 8. Quy trình chuyển đổi cấu hình an toàn

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Chụp trạng thái nguồn.** Ghi phiên bản, biến runtime, persisted variables, plugin, component, tài khoản và cấu hình file.
2. **Đọc release note từng chặng.** Lập bảng added/changed/deprecated/removed cho mọi phiên bản trên lộ trình.
3. **Lập ma trận cấu hình.** Với mỗi biến, ghi giá trị hiện tại, nguồn thiết lập, trạng thái ở bản đích, giá trị thay thế, người phụ trách và kiểm thử cần chạy.
4. **Sửa trước các deprecation.** Đổi câu lệnh, plugin, biến và tùy chọn đã lỗi thời trong code, script, automation và runbook khi còn có thể kiểm thử trên bản nguồn.
5. **Xử lý removed.** Xóa hoặc thay các tùy chọn không còn được hỗ trợ; xác minh cấu hình mới theo tài liệu bản đích.
6. **Đánh giá changed defaults.** So sánh runtime value với default mới, chạy benchmark và điều chỉnh có căn cứ thay vì giữ mọi giá trị cũ một cách máy móc.
7. **Kiểm thử staging.** Restore bản sao dữ liệu production, nâng cấp theo đúng đường dẫn dự kiến, chạy Upgrade Checker và kiểm thử ứng dụng/replication/backup.
8. **Chuẩn bị quay lui.** Xác minh backup có thể restore, lưu binary log, giữ bản cấu hình trước nâng cấp và xác định điều kiện dừng. Không giả định có thể downgrade data directory trực tiếp về phiên bản cũ.
9. **Triển khai production.** Theo runbook, giám sát startup log, error log, kết nối ứng dụng, replication lag, hiệu năng và dung lượng.
10. **Đối chiếu sau nâng cấp.** Xác nhận phiên bản, plugin, biến runtime, dữ liệu, backup mới và khả năng phục hồi; cập nhật tài liệu vận hành.

## 9. Ma trận tương thích cấu hình mẫu

Ví dụ ma trận khi chuẩn bị chuyển một hệ thống từ MySQL 8.0 sang 8.4:

| Thành phần | Trạng thái/thay đổi | Hành động trước nâng cấp | Bằng chứng hoàn tất |
|---|---|---|---|
| `CHANGE MASTER TO` | Deprecated từ 8.0.23 | Đổi sang `CHANGE REPLICATION SOURCE TO` trong script và runbook. | Replication được cấu hình và khởi động trên staging. |
| `mysql_native_password` | Deprecated 8.0.34; disabled by default 8.4 | Kiểm kê user, nâng connector và chuyển tài khoản sang plugin phù hợp. | Tất cả ứng dụng đăng nhập thành công bằng tài khoản thật. |
| `default_authentication_plugin` | Deprecated 8.0.27; removed 8.4 | Chuyển chính sách sang `authentication_policy`, rà soát provisioning. | Server khởi động và tài khoản mới được tạo đúng plugin. |
| `expire_logs_days` | Removed 8.2 | Chuyển sang `binlog_expire_logs_seconds`. | Retention đúng yêu cầu replica và PITR. |
| `have_ssl`, `have_openssl` | Removed 8.4 | Cập nhật monitoring sang kiểm tra TLS hiện hành. | Dashboard và cảnh báo phản ánh trạng thái TLS thực tế. |
| InnoDB defaults | Nhiều giá trị mặc định thay đổi trong 8.4 | Benchmark workload, xem xét buffer, I/O và temporary table. | So sánh latency, throughput, I/O và memory trước/sau. |

Đây là ma trận mẫu. Cần thêm mọi biến, plugin và tùy chọn đang có trong hệ thống cụ thể. Không đánh dấu một hàng hoàn tất chỉ vì dòng cấu hình cũ đã bị xóa; cần có kiểm thử chứng minh hành vi mới đáp ứng yêu cầu.

## 10. Lỗi thường gặp khi nâng cấp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Server không khởi động sau nâng cấp | Option hoặc biến đã bị loại bỏ, sai tên, giá trị không hợp lệ hoặc plugin không tồn tại. | Đọc error log, kiểm tra file cấu hình và persisted variables, thay bằng tùy chọn được hỗ trợ. |
| Ứng dụng báo lỗi xác thực | Tài khoản dùng plugin đã bị tắt hoặc client không hỗ trợ plugin mới. | Kiểm tra `mysql.user.plugin`, driver version và TLS; thử chuyển tài khoản trên staging. |
| Replication không chạy | Script còn cú pháp cũ, plugin hoặc biến replication đã đổi, hoặc cấu hình kết nối không tương thích. | Dùng câu lệnh source/replica mới, kiểm tra error fields và GTID state. |
| Binary log hết hạn sớm hoặc cấu hình không còn hiệu lực | Dùng `expire_logs_days` đã bị loại bỏ hoặc retention mới không được chuyển đổi đúng. | Cấu hình `binlog_expire_logs_seconds`, xác minh runtime value và chính sách retention. |
| Hiệu năng thay đổi dù không đổi config | Giá trị mặc định InnoDB hoặc hành vi optimizer thay đổi. | So sánh runtime variables, benchmark cùng workload và điều chỉnh có kiểm soát. |
| Monitoring báo trạng thái TLS không xác định | Dashboard dựa vào `have_ssl` hoặc `have_openssl` đã bị loại bỏ. | Chuyển sang các biến, trạng thái kết nối và metric TLS còn hỗ trợ. |
| Staging chạy nhưng production lỗi | Staging thiếu plugin, dữ liệu, cấu hình, connector hoặc workload tương tự. | Tăng độ tương đồng môi trường và diễn tập lại trên bản sao gần production hơn. |

## 11. Bài tập thực hành

Một hệ thống đang chạy MySQL 8.0, dự kiến nâng lên MySQL 8.4. Cấu hình còn `default_authentication_plugin`, `expire_logs_days`, một số tài khoản dùng `mysql_native_password` và script replication dùng `CHANGE MASTER TO`. Hãy thực hiện trên môi trường thử nghiệm:

1. Ghi phiên bản nguồn bằng `SELECT VERSION()` và xuất danh sách biến runtime, persisted variables, plugin và tài khoản xác thực.
2. Đọc release note từ phiên bản nguồn đến phiên bản đích; ghi lại mốc deprecated, removed và changed default có liên quan.
3. Lập ma trận tương thích cho bốn thành phần nêu trên, xác định thay thế và chủ sở hữu.
4. Chuyển script replication sang cú pháp source/replica mới; cấu hình binary log retention bằng biến còn hỗ trợ.
5. Nâng connector ứng dụng nếu cần, chuyển một tài khoản thử nghiệm sang `caching_sha2_password` và kiểm tra kết nối.
6. Kiểm tra chính sách xác thực bằng `authentication_policy`; loại bỏ biến cũ khỏi cấu hình và provisioning.
7. Chạy MySQL Shell Upgrade Checker, kiểm tra option file, nâng cấp staging và thực hiện smoke test.
8. Benchmark một workload đại diện trước/sau, đặc biệt với các biến InnoDB có default thay đổi.
9. Thử restore backup và xác minh replication, binary log, quyền, TLS, dữ liệu và ứng dụng.
10. Hoàn thiện báo cáo gồm vấn đề phát hiện, thay đổi cấu hình, kết quả kiểm thử, rủi ro còn lại và tiêu chí cho phép nâng cấp production.

Sau bài tập, người học cần giải thích được vì sao release note phải được đọc theo từng chặng, vì sao deprecated khác removed, vì sao thay đổi default có thể ảnh hưởng hiệu năng mà không gây lỗi khởi động, và vì sao kiểm kê runtime/persisted configuration quan trọng hơn chỉ tìm một dòng trong file `my.cnf`. Đây là nền tảng để biến việc nâng cấp MySQL thành một quy trình có thể dự đoán, kiểm thử và kiểm soát.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual: What Is New in MySQL 8.4 since MySQL 8.0](https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html)
- [MySQL 8.4 Reference Manual: Server and Status Variables and Options Added, Deprecated, or Removed](https://dev.mysql.com/doc/refman/8.4/en/added-deprecated-removed.html)
- [MySQL 8.0 Release Notes: Changes in MySQL 8.0.23](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-23.html)
- [MySQL 8.4 Reference Manual: Native Pluggable Authentication](https://dev.mysql.com/doc/refman/8.4/en/native-pluggable-authentication.html)
