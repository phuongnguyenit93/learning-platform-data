# Kiểm tra trước nâng cấp bằng công cụ phù hợp với phiên bản

Nâng cấp MySQL có thể thay đổi hành vi SQL, cấu hình, authentication plugin, data dictionary, storage engine và cách máy chủ xử lý các đối tượng hiện có. Một instance khởi động được sau nâng cấp chưa chắc ứng dụng vẫn hoạt động đúng. Vì vậy, trước khi nâng cấp cần đánh giá phiên bản nguồn, phiên bản đích, đường nâng cấp được hỗ trợ và các vấn đề tương thích trong dữ liệu, schema, cấu hình cũng như ứng dụng.

Công cụ phù hợp cho việc đánh giá trước nâng cấp là **MySQL Shell Upgrade Checker** (`util.checkForServerUpgrade`). Công cụ kiểm tra instance hiện tại theo phiên bản MySQL đích và đưa ra các lỗi, cảnh báo hoặc thông tin cần xử lý. Một số kiểm tra bổ sung có thể dùng `mysqlcheck` với `--check-upgrade`, nhưng kiểm tra bảng không thay thế được Upgrade Checker. Công cụ kiểm tra cũng không thực hiện nâng cấp máy chủ.

Trong module `DATABASE_MYSQL`, bài học này kết nối quản trị phiên bản, schema, cấu hình, replication, backup và vận hành. Sau bài học, bạn có thể:

- Chọn đúng phiên bản MySQL Shell và target version cho lần kiểm tra.
- Chạy Upgrade Checker trên instance nguồn và lưu báo cáo.
- Phân loại lỗi, cảnh báo và thông tin theo mức độ ảnh hưởng.
- Kiểm tra thêm bảng, cấu hình, plugin, ứng dụng và topology.
- Chuẩn bị môi trường staging, backup và kế hoạch diễn tập trước khi nâng cấp production.
- Xác định điều kiện cần đạt trước khi cho phép bắt đầu nâng cấp.

## 1. Vì sao cần kiểm tra tương thích trước nâng cấp?

Một phiên bản MySQL mới có thể loại bỏ cú pháp, biến cấu hình, plugin hoặc tính năng đã lỗi thời. Một số tên từ khóa có thể trở thành từ khóa dành riêng; kiểu dữ liệu, collation, authentication hoặc hành vi SQL có thể thay đổi. Schema hợp lệ ở phiên bản nguồn có thể không còn phù hợp với phiên bản đích.

Các nhóm rủi ro thường gặp:

| Nhóm | Ví dụ | Hậu quả |
|---|---|---|
| Phiên bản và đường nâng cấp | Phiên bản nguồn không nằm trong đường nâng cấp trực tiếp được hỗ trợ | Nâng cấp bị từ chối hoặc cần nâng qua phiên bản trung gian |
| Cấu hình | Biến hoặc tùy chọn đã bị loại bỏ/đổi tên | Máy chủ không khởi động hoặc dùng giá trị khác dự kiến |
| Schema và dữ liệu | Tên cột xung đột từ khóa mới, partition hoặc kiểu dữ liệu không còn tương thích | Lỗi kiểm tra hoặc không mở được đối tượng |
| SQL và stored program | View, routine, trigger dùng cú pháp hoặc hành vi cũ | Truy vấn hoặc tác vụ nền lỗi sau nâng cấp |
| Plugin và authentication | Plugin không còn được hỗ trợ hoặc client không tương thích | Người dùng không đăng nhập được |
| Ứng dụng và driver | Connector/client cũ không hỗ trợ giao thức hoặc authentication mới | Ứng dụng lỗi kết nối hoặc thay đổi hành vi |
| Replication và HA | Replica, Router, Shell hoặc công cụ quản trị khác phiên bản không tương thích | Topology mất khả năng đồng bộ hoặc chuyển vai trò |

Kiểm tra trước nâng cấp giúp phát hiện sớm các vấn đề mà có thể xử lý khi hệ thống vẫn đang chạy phiên bản cũ. Việc này giảm rủi ro phải sửa schema hoặc cấu hình trong lúc cửa sổ nâng cấp đã bắt đầu.

## 2. Xác định phiên bản nguồn, phiên bản đích và đường nâng cấp

Trước khi chạy công cụ, ghi nhận chính xác phiên bản đang chạy và phiên bản dự kiến:

```sql
SELECT VERSION() AS server_version,
       @@version_comment AS distribution;

SHOW VARIABLES LIKE 'version_compile%';
```

Xác định thêm:

- MySQL Community Server hay một bản phân phối tương thích khác.
- Phiên bản patch đầy đủ, không chỉ số major/minor.
- Hệ điều hành, kiến trúc CPU và cách cài đặt.
- Phiên bản MySQL Shell, Router, connector/driver và các plugin đang dùng.
- Phiên bản nguồn và phiên bản đích của từng node trong topology.

### 2.1. Không suy luận đường nâng cấp từ số phiên bản

Đường nâng cấp được hỗ trợ phụ thuộc phiên bản nguồn, phiên bản đích và hướng dẫn của từng dòng phát hành. Không mặc định rằng có thể nâng cấp trực tiếp qua mọi major release. Đọc hướng dẫn nâng cấp của phiên bản đích và release notes của các phiên bản liên quan để xác định:

- Phiên bản nguồn có được phép nâng cấp trực tiếp hay phải nâng qua bản trung gian.
- Có yêu cầu chạy một phiên bản patch tối thiểu trước khi chuyển major hay không.
- Có thay đổi định dạng dữ liệu, data dictionary hoặc yêu cầu cấu hình trước nâng cấp không.
- Có giới hạn khi nâng cấp từ fork hoặc bản phân phối của nhà cung cấp khác không.
- Có yêu cầu thứ tự nâng cấp riêng cho source, replica, Router, Shell hoặc plugin không.

Ví dụ, `8.4.0` có thể được dùng làm target minh họa trong lệnh bên dưới. Khi triển khai thật, thay bằng đúng phiên bản đích mà tổ chức đã chọn và xác nhận đường nâng cấp chính thức hỗ trợ phiên bản nguồn hiện tại.

### 2.2. Chọn phiên bản MySQL Shell phù hợp

MySQL Shell có Upgrade Checker utility từ dòng 8.0.13. Hãy dùng một bản MySQL Shell đủ mới để nhận diện target version và hỗ trợ các kiểm tra tương ứng. Với target thuộc dòng phát hành mới hơn, không nên dùng Shell quá cũ rồi kết luận instance không có vấn đề chỉ vì công cụ không biết các kiểm tra mới.

Kiểm tra phiên bản Shell:

```bash
mysqlsh --version
```

Nên dùng MySQL Shell được hỗ trợ và tương thích với phiên bản MySQL đích. Đọc ghi chú phát hành của Shell nếu cần chạy checker trên một server cũ để chuẩn bị cho một target mới.

## 3. MySQL Shell Upgrade Checker

Upgrade Checker phân tích một MySQL Server instance để tìm các vấn đề có thể cản trở hoặc ảnh hưởng tới việc nâng cấp lên phiên bản được chỉ định. Các nhóm kiểm tra có thể bao gồm:

- Phiên bản server và điều kiện nâng cấp.
- Biến cấu hình, tùy chọn đã lỗi thời hoặc bị loại bỏ.
- Tên database, bảng, cột hoặc routine xung đột với từ khóa mới.
- Kiểu dữ liệu, partitioning, engine và thuộc tính schema cần chú ý.
- View, stored procedure, function, trigger và event có vấn đề tương thích.
- Các tính năng hoặc cú pháp không còn được hỗ trợ trong target.
- Những điều kiện cấu hình hoặc dữ liệu mà phiên bản đích yêu cầu.

Phạm vi kiểm tra thay đổi theo phiên bản MySQL Shell và target version. Hãy xem danh sách kiểm tra của bản Shell đang sử dụng và đọc toàn bộ báo cáo thay vì chỉ nhìn dòng kết quả tổng quan.

### 3.1. Chạy từ command line

Ví dụ chạy checker từ máy có cài MySQL Shell:

```bash
mysqlsh upgrade_check@mysql-source.example:3306 \
  -- util check-for-server-upgrade \
  --target-version=8.4.0 \
  --output-format=JSON
```

Lệnh sẽ kết nối tới instance được chỉ định và kiểm tra theo target version. Tài khoản `upgrade_check` cần quyền đọc metadata và thực hiện các truy vấn kiểm tra mà utility yêu cầu. Không dùng tài khoản `root` nếu có thể cấp một tài khoản chuyên dụng với quyền tối thiểu theo tài liệu của phiên bản Shell.

Nếu cần kiểm tra file cấu hình server, có thể chỉ định đường dẫn cấu hình theo tùy chọn được phiên bản utility hỗ trợ, ví dụ:

```bash
mysqlsh upgrade_check@mysql-source.example:3306 \
  -- util check-for-server-upgrade \
  --target-version=8.4.0 \
  --config-path=/etc/my.cnf \
  --output-format=JSON
```

Đường dẫn `/etc/my.cnf` chỉ là ví dụ trên Linux. Trên Windows hoặc hệ thống cài đặt khác, chỉ định đúng file cấu hình mà instance thực sự sử dụng. Nếu server được khởi động với nhiều file cấu hình hoặc tham số dòng lệnh, cần kiểm tra đầy đủ nguồn cấu hình thay vì chỉ đưa một file không đại diện.

Tên tùy chọn command-line có thể thay đổi giữa các bản MySQL Shell. Nếu lệnh không nhận tùy chọn, chạy phần trợ giúp của đúng bản Shell:

```bash
mysqlsh -- util check-for-server-upgrade --help
```

### 3.2. Chạy qua JavaScript API

Có thể kết nối bằng MySQL Shell rồi gọi utility trong JavaScript mode:

```javascript
util.checkForServerUpgrade(null, {
    targetVersion: "8.4.0",
    outputFormat: "TEXT"
});
```

Đối số `null` dùng kết nối hiện tại của Shell. Nếu truyền thông tin kết nối riêng, dùng dạng `util.checkForServerUpgrade(connectionData, options)` theo API của phiên bản Shell. Kiểm tra tài liệu API khi dùng các tùy chọn như `configPath`, `include` hoặc `exclude`, vì danh sách và cách hỗ trợ có thể thay đổi theo bản phát hành.

### 3.3. Chọn định dạng báo cáo

`TEXT` thuận tiện để đọc trực tiếp trong terminal. `JSON` hữu ích cho việc lưu artifact, xử lý tự động hoặc so sánh kết quả giữa các lần chạy.

Nên lưu báo cáo cùng các thông tin:

- Host/instance được kiểm tra và thời điểm chạy.
- Phiên bản server nguồn.
- Phiên bản MySQL Shell.
- Target version.
- File cấu hình được phân tích (nếu có).
- Tài khoản hoặc danh tính chạy kiểm tra, theo chính sách kiểm toán.
- Kết quả lỗi, cảnh báo, thông tin và các mục đã loại trừ.

Báo cáo có thể chứa hostname, tên schema, tên bảng và chi tiết cấu hình. Lưu ở nơi có quyền truy cập phù hợp; không đính kèm mật khẩu hoặc secret.

## 4. Đọc và phân loại kết quả

Không nên chỉ nhìn thông báo “upgrade check completed”. Hãy đọc từng mục và phân loại theo mức độ ảnh hưởng.

| Kết quả | Cách hiểu | Hành động |
|---|---|---|
| ERROR | Vấn đề có thể ngăn nâng cấp hoặc khiến target không hoạt động đúng | Điều tra và khắc phục trước khi tiếp tục |
| WARNING | Rủi ro hoặc thay đổi cần đánh giá; không phải lúc nào cũng chặn nâng cấp | Xác định ứng dụng/đối tượng bị ảnh hưởng, thử nghiệm và ghi quyết định |
| NOTICE/INFO | Thông tin về thay đổi hoặc điểm cần biết | Đọc release notes, cập nhật runbook và kiểm tra nếu liên quan |
| Check không thực hiện được | Thiếu quyền, cấu hình không đọc được hoặc điều kiện kiểm tra không đáp ứng | Khắc phục quyền/kết nối rồi chạy lại; không coi mục này là PASS |

Tên mức độ và cách trình bày phụ thuộc phiên bản. Một số báo cáo có thể dùng các nhãn khác nhau. Điều quan trọng là hiểu nội dung, phạm vi và yêu cầu khắc phục của từng phát hiện.

### 4.1. Tạo danh sách xử lý

Với mỗi phát hiện, ghi:

1. Mã hoặc tiêu đề phát hiện trong báo cáo.
2. Database, bảng, cột, routine hoặc biến cấu hình liên quan.
3. Phiên bản nguồn và target version.
4. Hậu quả nếu giữ nguyên.
5. Cách khắc phục và migration/configuration change tương ứng.
6. Người chịu trách nhiệm và môi trường đã xác minh.
7. Kết quả checker sau khi khắc phục.

Ví dụ bảng theo dõi:

| Phát hiện | Phân loại | Việc cần làm | Tiêu chí đóng |
|---|---|---|---|
| Tên cột trùng từ khóa target | ERROR/WARNING tùy phát hiện | Đổi tên theo migration tương thích | Checker không còn phát hiện; ứng dụng đã chuyển sang tên mới |
| Biến cấu hình bị loại bỏ | ERROR/WARNING | Xóa hoặc thay bằng biến tương đương được hỗ trợ | Cấu hình mới được thử trên staging và server khởi động đúng |
| Plugin không còn hỗ trợ | ERROR/WARNING | Thay plugin hoặc xác nhận phương án tương thích | Đăng nhập và chức năng liên quan hoạt động trên target |
| Cú pháp routine cũ | WARNING | Sửa và chạy test nghiệp vụ | Routine, trigger và event hoạt động đúng trên target |

Không đóng phát hiện chỉ vì đã sửa file cấu hình hoặc schema. Chạy lại checker và thực hiện kiểm thử chức năng để xác nhận.

## 5. Kiểm tra bổ sung ở cấp bảng

Trong một số trường hợp, cần kiểm tra tương thích của bảng riêng biệt. MySQL cung cấp `CHECK TABLE ... FOR UPGRADE` và công cụ `mysqlcheck` có tùy chọn `--check-upgrade` ở các phiên bản hỗ trợ.

Ví dụ kiểm tra một bảng:

```sql
CHECK TABLE shop.orders FOR UPGRADE;
```

Hoặc kiểm tra các bảng trong các database:

```bash
mysqlcheck --all-databases --check-upgrade \
  --user=upgrade_check --password
```

`mysqlcheck` có thể yêu cầu mật khẩu tương tác. Không đưa mật khẩu trực tiếp vào command line. Chạy kiểm tra với tài khoản có quyền phù hợp và đọc kết quả cho từng bảng.

Kiểm tra bảng có phạm vi hẹp hơn Upgrade Checker. Nó không thay thế việc kiểm tra biến cấu hình, plugin, từ khóa, stored program, driver hoặc đường nâng cấp. Với hệ thống lớn, đánh giá tải và thời gian chạy trước khi kiểm tra toàn bộ bảng trên production.

## 6. Những hạng mục cần kiểm tra ngoài báo cáo tự động

Upgrade Checker là một công cụ quan trọng, nhưng không biết đầy đủ mọi hành vi của ứng dụng và hạ tầng. Hãy bổ sung các kiểm tra sau.

### 6.1. Cấu hình server

Lưu lại các biến cấu hình quan trọng:

```sql
SHOW VARIABLES;
```

Trong thực tế, xuất kết quả có kiểm soát rồi tập trung vào các nhóm:

- `sql_mode`, charset và collation.
- InnoDB buffer pool, redo log, undo, flush và durability.
- Binary log, GTID, retention và replication.
- TLS, authentication plugin và giới hạn kết nối.
- Đường dẫn data directory, temporary directory, log và plugin directory.
- Các biến đã deprecated hoặc có thay đổi mặc định giữa hai phiên bản.

Không sao chép nguyên file cấu hình cũ sang target rồi chỉ sửa những dòng gây lỗi. So sánh từng tùy chọn với tài liệu phiên bản đích và giữ lại những cấu hình thực sự cần thiết.

### 6.2. Schema và dữ liệu

Kiểm tra các đối tượng có thể bị ảnh hưởng:

- Tên database, bảng, cột, index, constraint và routine có thể trùng từ khóa mới.
- Kiểu dữ liệu cũ, giá trị ngoài miền mong đợi và dữ liệu không hợp lệ.
- Partitioning, storage engine và index.
- View, trigger, event, stored procedure và stored function.
- Charset/collation và quy tắc so sánh chuỗi.
- Foreign key, CHECK constraint và generated column.

Các truy vấn metadata ở `INFORMATION_SCHEMA` giúp kiểm kê schema. Với bảng quan trọng, lưu `SHOW CREATE TABLE` và so sánh trước/sau trong môi trường thử nghiệm.

### 6.3. Plugin và authentication

Lập danh sách plugin/component đang sử dụng:

```sql
SHOW PLUGINS;
```

Kiểm tra khả năng tương thích của authentication plugin, audit plugin, keyring, storage engine bổ sung, UDF và các component bên thứ ba. Xác nhận client library của ứng dụng hỗ trợ phương thức xác thực mà target sử dụng. Đặc biệt, thử đăng nhập bằng tài khoản ứng dụng thực tế thay vì chỉ kiểm tra tài khoản quản trị.

### 6.4. Ứng dụng và driver

Liệt kê mọi thành phần kết nối MySQL:

- JDBC driver, PHP driver, Python connector, Node.js driver hoặc client native.
- ORM, migration framework và query builder.
- Job nền, ETL, CDC connector và công cụ backup.
- Dashboard, BI tool, monitoring agent và script quản trị.

Kiểm tra phiên bản driver có hỗ trợ target, authentication, TLS và kiểu dữ liệu đang dùng không. Chạy test truy vấn quan trọng với `sql_mode`, collation và cấu hình tương đương target. Một checker ở server không thể chứng minh mã ứng dụng không phụ thuộc hành vi cũ.

### 6.5. Replication và HA

Với topology source-replica, InnoDB Cluster hoặc ClusterSet, cần kiểm tra:

- Đường nâng cấp được hỗ trợ cho từng node và thứ tự nâng cấp.
- Khả năng tương thích giữa phiên bản source, replica, MySQL Shell và Router.
- GTID, replication channel, plugin Group Replication và trạng thái quorum.
- CDC connector có hỗ trợ binlog event và phiên bản target không.
- Kế hoạch chuyển vai trò, failover và rollback theo topology.

Không chạy checker trên một node rồi xem kết quả đó đại diện cho toàn bộ topology. Kiểm tra từng instance và từng loại thành phần theo kế hoạch nâng cấp.

## 7. Công cụ cũ và giới hạn sử dụng

### 7.1. `mysql_upgrade`

Từ MySQL 8.0.16, nhiều tác vụ nâng cấp hệ thống được server thực hiện tự động khi khởi động bằng phiên bản mới; tiện ích `mysql_upgrade` đã bị deprecated và không còn là bước bắt buộc theo quy trình MySQL 8.0 mới. Trong MySQL 8.4, `mysql_upgrade` đã bị loại bỏ.

Không dùng `mysql_upgrade` như công cụ đánh giá tương thích trước nâng cấp. Hãy dùng MySQL Shell Upgrade Checker để tìm các vấn đề cần xử lý trước khi khởi động target. Với phiên bản cũ hơn, tuân thủ đúng tài liệu nâng cấp của phiên bản đó.

### 7.2. `mysqlcheck --check-upgrade`

Tùy chọn này hỗ trợ kiểm tra tương thích ở cấp bảng trên các phiên bản có hỗ trợ. Nó hữu ích như một bước bổ sung, nhưng không thay thế checker vì không phân tích đầy đủ cấu hình, plugin, stored program và hành vi ứng dụng.

### 7.3. Không nhầm checker với công cụ nâng cấp

Upgrade Checker đánh giá khả năng tương thích và báo vấn đề. Nó không tự sửa mọi vấn đề, không chuyển dữ liệu sang phiên bản mới, không bảo đảm ứng dụng tương thích và không thay thế backup. Một báo cáo không có lỗi là điều kiện quan trọng, nhưng chưa phải giấy chứng nhận rằng nâng cấp chắc chắn thành công.

## 8. Quy trình kiểm tra trước nâng cấp

Một quy trình có thể lặp lại gồm các bước sau:

1. **Kiểm kê:** ghi phiên bản, cấu hình, schema, plugin, ứng dụng, driver, topology và dung lượng dữ liệu.
2. **Chọn target:** xác nhận phiên bản đích và đường nâng cấp chính thức được hỗ trợ.
3. **Chuẩn bị công cụ:** cài MySQL Shell phù hợp và kiểm tra quyền tài khoản dùng cho checker.
4. **Chụp trạng thái:** lưu cấu hình, danh sách plugin, schema DDL, GTID/replication status và backup hiện tại.
5. **Chạy Upgrade Checker:** kiểm tra từng instance theo target version, lưu output TEXT/JSON và file cấu hình nếu cần.
6. **Chạy kiểm tra bổ sung:** kiểm tra bảng, ứng dụng, driver, authentication, plugin, replication và các tích hợp.
7. **Phân loại phát hiện:** xử lý ERROR, đánh giá WARNING, ghi nhận NOTICE và các mục không kiểm tra được.
8. **Khắc phục:** dùng migration/configuration change có review; không sửa trực tiếp mà không ghi lại.
9. **Chạy lại checker:** xác nhận các vấn đề đã xử lý và lưu báo cáo mới.
10. **Diễn tập staging:** restore bản backup hoặc clone gần production, thực hiện nâng cấp theo đúng quy trình dự kiến và chạy test nghiệp vụ.
11. **Đánh giá readiness:** xác nhận backup/restore, thời gian, dung lượng, monitoring, rollback/failover và người chịu trách nhiệm.
12. **Quyết định cửa sổ production:** chỉ bắt đầu khi các điều kiện chấp nhận đã đạt và có kế hoạch xử lý sự cố.

## 9. Kiểm tra trên môi trường staging

Checker không thay thế một lần nâng cấp thử. Staging nên phản ánh gần production về phiên bản, cấu hình, plugin, schema, dung lượng và dữ liệu. Có thể dùng bản backup đã được xử lý dữ liệu nhạy cảm hoặc clone phù hợp với chính sách bảo mật.

Trong lần diễn tập:

- Thực hiện đúng thứ tự nâng cấp dự kiến.
- Đo thời gian dừng, thời gian khởi động và thời gian hoàn tất tác vụ hậu nâng cấp.
- Kiểm tra error log và warning sau lần khởi động đầu tiên.
- Chạy smoke test kết nối, truy vấn đọc/ghi, transaction và stored program.
- Chạy test luồng nghiệp vụ quan trọng như tạo đơn, thanh toán, hoàn tiền và báo cáo.
- Kiểm tra job nền, event scheduler, replication, CDC, backup và monitoring.
- Đo hiệu năng truy vấn quan trọng và so sánh với baseline trước nâng cấp.
- Thử restore backup vào môi trường riêng để xác nhận khả năng phục hồi.

Không chỉ dùng một database trống để diễn tập. Một số lỗi chỉ xuất hiện khi dữ liệu thực có giá trị đặc biệt, bảng lớn, partition hoặc số lượng đối tượng lớn.

## 10. Backup, rollback và kế hoạch phục hồi

Trước khi nâng cấp production:

- Có backup đầy đủ và đã kiểm tra tính toàn vẹn.
- Có bản sao keyring/KMS cần thiết nếu dữ liệu được mã hóa.
- Đã thử khôi phục backup vào môi trường độc lập.
- Xác định binlog/GTID cần giữ nếu có yêu cầu PITR.
- Ghi nhận cấu hình, tài khoản, plugin và phiên bản trước nâng cấp.
- Xác định cách quay lại phiên bản cũ được hỗ trợ.

Không mặc định có thể hạ phiên bản bằng cách cài lại binary MySQL cũ trên data directory đã được phiên bản mới nâng cấp. Downgrade có thể không được hỗ trợ hoặc yêu cầu quy trình riêng. Phương án an toàn thường là phục hồi backup trước nâng cấp vào một môi trường dùng phiên bản cũ, sau đó chuyển dịch vụ theo kế hoạch được kiểm chứng.

Nếu dùng replication để hỗ trợ chuyển đổi phiên bản, phải kiểm tra giới hạn tương thích source/replica và cách failover trong từng giai đoạn. Không cho một node phiên bản mới nhận ghi rồi kỳ vọng node phiên bản cũ có thể tiếp tục làm primary mà không có quy trình được hỗ trợ.

## 11. Tiêu chí sẵn sàng trước khi nâng cấp

Có thể dùng các điều kiện sau làm cổng quyết định:

| Điều kiện | Bằng chứng cần có |
|---|---|
| Đường nâng cấp được hỗ trợ | Tài liệu target xác nhận phiên bản nguồn và các bước trung gian |
| Công cụ phù hợp | MySQL Shell có Upgrade Checker hỗ trợ target và báo cáo được lưu |
| Không còn lỗi chặn | Tất cả ERROR đã được xử lý và checker chạy lại |
| Cảnh báo đã đánh giá | Mỗi WARNING có chủ sở hữu, quyết định và test tương ứng |
| Cấu hình tương thích | File cấu hình đã được rà soát theo target và thử trên staging |
| Ứng dụng tương thích | Driver, plugin, query và luồng nghiệp vụ đã được kiểm thử |
| Topology sẵn sàng | Từng node, replication, Router và failover plan đã được đánh giá |
| Backup có thể dùng | Backup hoàn tất, checksum/kiểm tra hợp lệ và restore thử thành công |
| Runbook rõ ràng | Có thứ tự thao tác, giám sát, tiêu chí dừng và phương án phục hồi |
| Người chịu trách nhiệm | Có người vận hành, người xác nhận nghiệp vụ và kênh liên lạc |

Không đánh dấu PASS cho mục không thể kiểm tra. Ghi rõ giới hạn và quyết định chấp nhận rủi ro theo quy trình của tổ chức.

## 12. Sự cố thường gặp khi chạy Upgrade Checker

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Utility không nhận target version | MySQL Shell quá cũ hoặc target không được utility hỗ trợ | Cài Shell phù hợp và xác minh target release |
| Không kết nối được server | Sai endpoint, TLS, firewall hoặc authentication | Kiểm tra kết nối và thử bằng client tương thích |
| Checker báo thiếu quyền | Tài khoản không đọc được metadata cần kiểm tra | Cấp quyền tối thiểu theo tài liệu utility rồi chạy lại |
| Không phân tích được config | Sai đường dẫn hoặc file không phản ánh cấu hình thực tế | Xác định file cấu hình đang dùng và các tham số khởi động |
| Có nhiều warning | Server dùng tính năng deprecated hoặc hành vi sắp thay đổi | Đánh giá từng phát hiện theo target, sửa và test |
| Checker không phát hiện lỗi ứng dụng | Checker chỉ đánh giá server/schema/config trong phạm vi hỗ trợ | Bổ sung test driver, query, stored program và nghiệp vụ |
| Kết quả khác giữa các node | Cấu hình hoặc schema của topology bị drift | Chạy checker riêng trên từng node và so sánh báo cáo |
| `mysqlcheck --check-upgrade` báo lỗi bảng | Bảng hoặc định dạng cần xử lý trước target | Đọc chi tiết, kiểm tra backup và làm theo hướng dẫn phiên bản |

Giữ nguyên báo cáo gốc trước khi sửa để có thể so sánh. Không bỏ qua phát hiện chỉ vì nó xuất hiện ở một node ít được sử dụng; node đó có thể trở thành primary sau failover.

## 13. Tình huống thực hành

Một hệ thống thương mại đang chạy MySQL 8.0 và dự kiến chuyển sang MySQL 8.4. Hệ thống có một source, hai replica, MySQL Router, một connector CDC và nhiều ứng dụng dùng JDBC. Nhóm vận hành cần xác nhận tương thích trước khi lên lịch nâng cấp.

Thực hiện trong môi trường lab:

1. Ghi lại phiên bản đầy đủ của tất cả MySQL Server, MySQL Shell, Router, JDBC driver và CDC connector.
2. Đọc tài liệu nâng cấp của target để xác nhận đường nâng cấp từ phiên bản nguồn.
3. Cài MySQL Shell tương thích và chạy `mysqlsh --version`.
4. Chạy Upgrade Checker trên source và từng replica với target version đã chọn; lưu báo cáo JSON.
5. Nếu có file cấu hình, chạy thêm checker với `--config-path` trỏ tới file đúng của từng instance.
6. Phân loại mọi ERROR, WARNING, NOTICE và mục kiểm tra không thực hiện được.
7. Dùng `mysqlcheck --all-databases --check-upgrade` hoặc `CHECK TABLE ... FOR UPGRADE` cho các bảng phù hợp.
8. Kiểm tra plugin, authentication, view, routine, trigger, event, SQL mode, collation và các query quan trọng.
9. Khắc phục vấn đề bằng migration/configuration change có review rồi chạy lại checker.
10. Restore backup vào staging, nâng cấp thử, chạy smoke test, kiểm tra replication/Router/CDC và thử restore backup trước nâng cấp.
11. Lập báo cáo readiness với thời gian, rủi ro còn lại, RPO/RTO và người xác nhận.

**Câu hỏi tự đánh giá:**

- Vì sao phải xác định đường nâng cấp được hỗ trợ trước khi chạy checker?
- MySQL Shell Upgrade Checker kiểm tra điều gì và không chứng minh được điều gì?
- Vì sao `mysqlcheck --check-upgrade` không thay thế Upgrade Checker?
- Tại sao cần chạy checker trên từng node của topology?
- Vì sao báo cáo không có ERROR vẫn chưa đủ để cho phép nâng cấp production?
- Từ MySQL 8.0.16, vai trò của `mysql_upgrade` thay đổi như thế nào?
- Vì sao không nên mặc định downgrade bằng cách cài lại binary cũ trên data directory mới?
- Những bằng chứng nào cần có trước khi đánh dấu hệ thống sẵn sàng nâng cấp?

## Kết luận

Kiểm tra trước nâng cấp cần kết hợp MySQL Shell Upgrade Checker, kiểm tra bảng, rà soát cấu hình và plugin, kiểm thử ứng dụng cùng đánh giá topology. Hãy xác nhận đường nâng cấp được hỗ trợ, xử lý và chạy lại mọi phát hiện, diễn tập trên staging với dữ liệu gần production, đồng thời chứng minh backup có thể khôi phục. Chỉ bắt đầu nâng cấp khi báo cáo, kiểm thử và runbook cùng cho thấy hệ thống đã sẵn sàng.
