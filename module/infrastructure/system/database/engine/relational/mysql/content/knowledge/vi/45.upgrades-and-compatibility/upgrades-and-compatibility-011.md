# Nâng cấp và tương thích

## Kiểm tra plugin/component, stored object và công cụ vận hành

Một lần nâng cấp MySQL không chỉ thay binary của máy chủ. Ứng dụng còn phụ thuộc vào plugin, component, stored object và các công cụ kết nối, backup, replication, giám sát, quản trị schema. Máy chủ có thể khởi động thành công nhưng một plugin không nạp được, một view dùng DEFINER đã mất, một event không chạy hoặc công cụ backup không còn tương thích với định dạng mới. Vì vậy, kiểm tra tương thích phải bao gồm toàn bộ những thành phần tham gia vào vòng đời dữ liệu.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Những kỹ năng này giúp bạn đánh giá tác động nâng cấp ở cả tầng server, metadata, bảo mật và quy trình vận hành.

Bài này tập trung vào ba nhóm cần kiểm tra trước và sau nâng cấp: plugin/component được nạp vào máy chủ, stored object được thực thi trong database, và công cụ vận hành/client kết nối với MySQL. Các ví dụ chủ yếu dùng MySQL 8.0/8.4; cú pháp và khả năng hỗ trợ phải được xác minh theo đúng phiên bản, edition, hệ điều hành và nhà cung cấp.

### 1. Lập bản đồ phụ thuộc trước khi nâng cấp

Không thể kiểm tra tương thích nếu chưa biết hệ thống đang dùng gì. Hãy lập inventory trên máy chủ nguồn và lưu cùng kế hoạch nâng cấp.

Các nhóm cần kiểm kê:

| Nhóm | Nội dung cần ghi nhận | Rủi ro khi nâng cấp |
|---|---|---|
| Plugin | Tên, loại, trạng thái, thư viện, phiên bản, nguồn cung cấp và cách nạp | Plugin không có binary tương thích, bị deprecated hoặc không còn được hỗ trợ |
| Component | Component đã cài, thư viện, dependency và cấu hình nạp khi startup | Component không khởi tạo, service dependency thay đổi hoặc registry khác |
| Stored object | View, procedure, function, trigger, event, DEFINER, SQL mode và security type | Object tạo được nhưng chạy lỗi, thiếu quyền hoặc có hành vi khác |
| Client/driver | mysql client, connector, ORM, driver version, auth plugin và TLS | Không đăng nhập được hoặc không tương thích giao thức/xác thực |
| Backup/restore | mysqldump, MySQL Shell, Enterprise Backup, XtraBackup và mysqlbinlog | Backup không restore được hoặc không đọc được binlog sau nâng cấp |
| Replication/HA | Router, Group Replication, Shell AdminAPI, proxy và orchestrator | Topology không hoạt động hoặc failover/metadata upgrade sai |
| Schema tooling | Migration runner, pt-online-schema-change, gh-ost và script DDL | Công cụ không hỗ trợ phiên bản, trigger, FK hoặc binlog format mới |
| Monitoring | Agent, exporter, dashboard, alert và Performance Schema query | Metric đổi tên, instrument khác hoặc cảnh báo sai |

Ghi rõ phiên bản MySQL đầy đủ, edition, hệ điều hành, kiến trúc CPU, package repository và đường dẫn plugin directory. Một plugin được biên dịch cho Linux x86-64 không thể mặc định dùng trên Windows hoặc ARM; binary của Community và Enterprise cũng không thể mặc định thay thế cho nhau.

### 2. Phân biệt plugin và component

Plugin và component đều mở rộng khả năng của MySQL Server, nhưng dùng các giao diện và cơ chế quản lý khác nhau.

| Đặc điểm | Plugin | Component |
|---|---|---|
| Mô hình | Plugin API truyền thống, thường đăng ký một loại chức năng như authentication, storage engine hoặc audit | Component service architecture, có thể cung cấp và sử dụng các service nội bộ |
| Đăng ký | Có metadata trong bảng hệ thống mysql.plugin khi cài bằng INSTALL PLUGIN | Có registry riêng trong mysql.component |
| Cài đặt | INSTALL PLUGIN với tên plugin và thư viện | INSTALL COMPONENT với URI component |
| Gỡ cài đặt | UNINSTALL PLUGIN | UNINSTALL COMPONENT |
| Nạp lúc khởi động | Có thể dùng plugin-load-add hoặc cơ chế tương ứng | Có thể cấu hình component_load_add hoặc cơ chế startup được phiên bản hỗ trợ |
| Tương thích | Phụ thuộc plugin API/ABI, binary, server version và vendor | Phụ thuộc component service API, dependency và phiên bản server |

Component architecture được giới thiệu để các phần mở rộng có thể tương tác thông qua service interface có cấu trúc hơn. Không nên coi component là một cách viết khác của plugin hoặc giả định hai loại có cùng vòng đời.

### 3. Kiểm kê plugin trên máy chủ nguồn

Trước nâng cấp, lấy danh sách plugin và trạng thái:

~~~sql
SHOW PLUGINS;
~~~

Có thể truy vấn metadata chi tiết:

~~~sql
SELECT
  PLUGIN_NAME,
  PLUGIN_VERSION,
  PLUGIN_STATUS,
  PLUGIN_TYPE,
  PLUGIN_LIBRARY,
  LOAD_OPTION
FROM INFORMATION_SCHEMA.PLUGINS
ORDER BY PLUGIN_TYPE, PLUGIN_NAME;
~~~

Các cột và giá trị có thể khác theo phiên bản. Lưu cả plugin đang ACTIVE, INACTIVE và plugin có trạng thái lỗi; một plugin không hoạt động vẫn có thể được cấu hình để nạp ở lần khởi động sau.

Kiểm tra cách nạp plugin và thư mục thư viện:

~~~sql
SHOW VARIABLES LIKE 'plugin_dir';
SHOW VARIABLES LIKE 'plugin_load%';
~~~

Đối chiếu cấu hình server trên filesystem, bao gồm các tùy chọn plugin-load-add. Không chỉ dựa vào SHOW PLUGINS vì cấu hình startup và thư viện trên đĩa có thể ảnh hưởng lần khởi động tiếp theo.

Các câu lệnh quản lý plugin truyền thống:

~~~sql
INSTALL PLUGIN plugin_name SONAME 'plugin_library.so';

UNINSTALL PLUGIN plugin_name;
~~~

Đây là cú pháp minh họa. Thay plugin_name và tên thư viện bằng giá trị do nhà cung cấp cung cấp cho đúng nền tảng. Trên Windows, thư viện thường có phần mở rộng DLL. Không tự đổi tên hoặc sao chép một shared library từ phiên bản server khác.

Plugin cài bằng INSTALL PLUGIN được đăng ký để MySQL nạp lại khi khởi động. Cấu hình plugin-load-add cũng có thể nạp thư viện lúc startup; hãy hiểu rõ cách nạp hiện tại để không tạo cấu hình trùng hoặc xung đột. Nếu plugin là bắt buộc để khởi động hoặc giải mã dữ liệu, hãy kiểm thử startup trên bản sao trước khi thay đổi.

### 4. Kiểm kê component và dependency

Trên phiên bản hỗ trợ component, xem registry:

~~~sql
SELECT * FROM mysql.component;
~~~

Bảng registry cho biết các component đã được đăng ký; cấu trúc cột có thể thay đổi theo phiên bản. Kết hợp kết quả với cấu hình startup, log khởi động và tài liệu nhà cung cấp để xác định component thực sự được khởi tạo.

Component có thể được cài đặt bằng URI thư viện:

~~~sql
INSTALL COMPONENT 'file://component_name';

UNINSTALL COMPONENT 'file://component_name';
~~~

Tên component và vị trí thư viện phải đúng với gói cài đặt. Một số component cần service khác hoặc cấu hình riêng; cài đặt thành công chưa chắc component đã cung cấp đầy đủ chức năng mà ứng dụng mong đợi.

Để nạp component khi khởi động, MySQL có tùy chọn component_load_add ở các phiên bản hỗ trợ. Kiểm tra cú pháp và cách khai báo trong file cấu hình của đúng phiên bản; đừng sao chép nguyên cấu hình giữa các dòng MySQL mà chưa kiểm tra.

Khi gỡ component, trước tiên xác định component nào đang phụ thuộc vào service của nó. Nếu component cung cấp chức năng mã hóa, quản lý key, authentication hoặc audit, gỡ bỏ có thể làm dữ liệu không đọc được hoặc làm thay đổi chính sách bảo mật. Không uninstall trong production chỉ để thử xem máy chủ có còn khởi động hay không.

### 5. Những nhóm plugin/component cần chú ý

#### 5.1. Authentication

Authentication plugin quyết định cách MySQL xác thực tài khoản. Khi nâng cấp server, kiểm tra:

- Plugin xác thực được tài khoản sử dụng có còn được hỗ trợ và nạp thành công không.
- Driver/connector của ứng dụng có hỗ trợ phương thức xác thực đó không.
- TLS, certificate, RSA key exchange và cấu hình mật khẩu có tương thích không.
- Tài khoản quản trị, replication user, backup user và tài khoản ứng dụng có thể đăng nhập sau nâng cấp không.

Ví dụ kiểm kê plugin xác thực của tài khoản:

~~~sql
SELECT
  user,
  host,
  plugin,
  account_locked,
  password_expired
FROM mysql.user
ORDER BY user, host;
~~~

Quyền đọc mysql.user bị giới hạn; dùng tài khoản quản trị phù hợp và không xuất password hash vào báo cáo không được bảo vệ.

MySQL 8.0 dùng caching_sha2_password làm phương thức xác thực mặc định cho tài khoản mới. mysql_native_password bị deprecated từ MySQL 8.0.34, bị tắt mặc định trong MySQL 8.4 và đã bị loại bỏ trong MySQL 9.0. Trước khi nâng cấp, xác định tài khoản còn dùng plugin cũ, kiểm tra connector và lập kế hoạch chuyển đổi. Không bật lại phương thức cũ trên toàn server chỉ để xử lý một client chưa được nâng cấp.

#### 5.2. Keyring và mã hóa

Keyring plugin/component có thể quản lý key dùng cho tablespace encryption, redo/undo encryption hoặc chức năng bảo mật khác. Khả năng truy cập key là điều kiện để đọc dữ liệu đã mã hóa.

Trước khi nâng cấp:

1. Xác định keyring implementation đang dùng và cách nạp lúc startup.
2. Lưu cấu hình, vị trí key store, quyền filesystem và dependency.
3. Xác minh backup của key store và quy trình phục hồi key độc lập với backup data.
4. Thử khởi động bản nâng cấp bằng bản sao data directory và bản sao key store phù hợp.
5. Xác nhận dữ liệu mã hóa vẫn đọc được sau khi restart và sau restore thử nghiệm.

Không gỡ hoặc thay keyring chỉ vì tên plugin/component đã đổi. Không xóa, ghi đè hoặc di chuyển key store trước khi có bản sao có thể khôi phục. Backup database mà thiếu key cần thiết có thể không có giá trị phục hồi.

#### 5.3. Audit và kiểm tra mật khẩu

Audit plugin/component có thể ghi sự kiện bảo mật như kết nối, câu lệnh hoặc hoạt động trên đối tượng. Kiểm tra phiên bản, edition, filter, đường dẫn log, quyền ghi và cách chuyển log tập trung.

Nếu nâng cấp làm đổi tên biến, cấu trúc filter hoặc định dạng log, pipeline SIEM và parser có thể không đọc được dữ liệu như trước. Hãy tạo sự kiện thử nghiệm, kiểm tra log mới và xác minh alert vẫn kích hoạt.

Validate password có thể được triển khai qua plugin hoặc component tùy phiên bản và cách cài đặt. Kiểm tra chính sách hiện tại, biến cấu hình và hành vi tạo/đổi mật khẩu. Đừng chỉ kiểm tra plugin ACTIVE; hãy thử tạo một tài khoản lab với mật khẩu đạt và không đạt chính sách.

### 6. Stored object có thể bị ảnh hưởng khi nâng cấp

Stored object gồm view, stored procedure, stored function, trigger và event. Stored routine, trigger và event lưu SQL mode tại thời điểm tạo; view lưu DEFINER/security context và ngữ cảnh charset/collation. Tất cả đều có thể tham chiếu đến tên cột hoặc hàm đã thay đổi.

Một số lỗi chỉ xuất hiện khi object được gọi hoặc khi event chạy theo lịch. Vì vậy, kiểm tra object sau upgrade cần bao gồm cả metadata và hành vi thực thi.

#### 6.1. Lập inventory object

Liệt kê routine:

~~~sql
SELECT
  ROUTINE_SCHEMA,
  ROUTINE_NAME,
  ROUTINE_TYPE,
  DEFINER,
  SECURITY_TYPE,
  SQL_MODE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION,
  DATABASE_COLLATION
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY ROUTINE_SCHEMA, ROUTINE_NAME;
~~~

Liệt kê trigger:

~~~sql
SELECT
  TRIGGER_SCHEMA,
  TRIGGER_NAME,
  EVENT_MANIPULATION,
  EVENT_OBJECT_TABLE,
  ACTION_TIMING,
  DEFINER,
  SQL_MODE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY TRIGGER_SCHEMA, EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

Liệt kê event:

~~~sql
SELECT
  EVENT_SCHEMA,
  EVENT_NAME,
  DEFINER,
  STATUS,
  TIME_ZONE,
  SQL_MODE,
  ON_COMPLETION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY EVENT_SCHEMA, EVENT_NAME;
~~~

Liệt kê view:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  DEFINER,
  SECURITY_TYPE,
  CHARACTER_SET_CLIENT,
  COLLATION_CONNECTION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA NOT IN
  ('mysql', 'information_schema', 'performance_schema', 'sys')
ORDER BY TABLE_SCHEMA, TABLE_NAME;
~~~

Các truy vấn INFORMATION_SCHEMA phụ thuộc quyền nhìn metadata và phiên bản. Đối với object quan trọng, lưu thêm định nghĩa bằng SHOW CREATE VIEW, SHOW CREATE PROCEDURE, SHOW CREATE FUNCTION, SHOW CREATE TRIGGER và SHOW CREATE EVENT. Không dựa duy nhất vào ROUTINE_DEFINITION vì metadata text có thể bị giới hạn hoặc không đủ để tái tạo object.

#### 6.2. Kiểm tra DEFINER và quyền thực thi

DEFINER là tài khoản mà một số stored object dùng làm security context. Nếu tài khoản này không tồn tại sau restore/upgrade, object có thể báo lỗi khi gọi, hoặc hoạt động khác khi quyền của tài khoản thay đổi.

Các object dùng SQL SECURITY DEFINER chạy với quyền của definer; SQL SECURITY INVOKER chạy theo quyền của người gọi trong những ngữ cảnh hỗ trợ. View, routine và một số object có thể mang security type khác nhau. Kiểm tra từng object thay vì mặc định tất cả đều dùng cùng một chính sách.

Tìm definer và xác minh tài khoản:

~~~sql
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb'
UNION
SELECT DISTINCT DEFINER
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'appdb';
~~~

Đối chiếu từng giá trị user@host với tài khoản được quản lý trên máy chủ đích. Tránh tạo một tài khoản definer có quyền rộng chỉ để object hết lỗi. Tạo tài khoản chuyên biệt với quyền tối thiểu, hoặc chuyển sang INVOKER nếu mô hình bảo mật và hành vi ứng dụng cho phép.

Khi dump/restore, xem xét tùy chọn xử lý DEFINER của công cụ. Loại bỏ DEFINER có thể khiến object dùng ngữ cảnh mặc định hoặc thay đổi security semantics; giữ nguyên DEFINER lại có thể tạo tham chiếu đến tài khoản không tồn tại. Đây là quyết định bảo mật cần kiểm thử, không phải thao tác thay chuỗi máy móc.

#### 6.3. SQL mode được lưu cùng stored program

MySQL lưu SQL_MODE có hiệu lực tại thời điểm tạo stored procedure, function, trigger và event. Khi object thực thi, nó có thể sử dụng mode đã lưu thay vì mode hiện tại của session gọi.

Do đó, hai máy chủ có cùng @@GLOBAL.sql_mode nhưng stored program vẫn có thể hành xử khác nếu object được tạo ở hai thời điểm hoặc dưới mode khác nhau.

Đối chiếu:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode;

SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';

SELECT TRIGGER_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'appdb';

SELECT EVENT_NAME, SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
~~~

Trước khi tạo lại object, thiết lập SQL mode theo baseline đã thống nhất trong session triển khai. Sau đó đọc lại metadata và chạy test để xác nhận object mang mode mong muốn. Không thay đổi global SQL mode chỉ để làm một routine cũ chạy được.

#### 6.4. Charset, collation và tên đối tượng

Stored object lưu ngữ cảnh charset/collation tại thời điểm tạo; view cũng có metadata về client charset và connection collation. Nếu nâng cấp đồng thời đổi collation, kết quả so sánh chuỗi trong view/routine có thể khác.

Kiểm tra:

- Charset/collation của database, table và column được object tham chiếu.
- CHARACTER_SET_CLIENT và COLLATION_CONNECTION của object.
- Tên cột, tên hàm hoặc từ khóa có thể trở thành reserved word trong phiên bản mới.
- Kiểu dữ liệu, độ chính xác và phép ép kiểu trong biểu thức.
- Hành vi so sánh, sắp xếp và unique key dưới collation mới.

Đối chiếu SHOW CREATE và chạy các ca kiểm thử có dấu, chữ hoa/thường, NULL, ngày giờ và giá trị biên. Nếu cần sửa định nghĩa, tạo migration mới có thể review và rollback theo chính sách thay đổi schema.

#### 6.5. Event scheduler và tác vụ tự động

Event có thể chạy theo lịch sau khi máy chủ được khởi động lại. Kiểm tra event scheduler và trạng thái từng event:

~~~sql
SHOW VARIABLES LIKE 'event_scheduler';

SELECT
  EVENT_SCHEMA,
  EVENT_NAME,
  STATUS,
  LAST_EXECUTED,
  TIME_ZONE,
  DEFINER
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'appdb';
~~~

Trước cutover, quyết định rõ event nào được bật trên primary mới. Nếu cả source cũ và target mới cùng chạy event ghi dữ liệu, tác vụ có thể chạy hai lần. Nếu event bị tắt ngoài dự kiến, dữ liệu tổng hợp, cleanup hoặc job định kỳ có thể ngừng cập nhật.

Xác minh timezone của event, definer, quyền và lịch chạy tiếp theo. Chạy thử logic trong môi trường kiểm thử hoặc gọi thủ tục nền theo cách có kiểm soát; không chờ đến lịch production để phát hiện lỗi.

### 7. Kiểm tra tương thích của client và connector

Một server mới có thể từ chối kết nối của client cũ do authentication plugin, TLS protocol, cipher, certificate hoặc thay đổi giao thức. Kiểm tra các thành phần:

- MySQL command-line client và thư viện client được ứng dụng sử dụng.
- Connector/J, Connector/NET, Node.js, Python, Go và driver của ORM.
- Connection pool, proxy và health check.
- Authentication plugin của từng tài khoản.
- TLS CA, certificate, hostname verification và cipher suite.
- Charset mặc định, timezone và SQL mode ở session.

Ghi phiên bản client:

~~~bash
mysql --version
mysqlsh --version
~~~

Kiểm tra kết nối bằng đúng binary/driver mà ứng dụng sẽ dùng, không chỉ dùng mysql client mới cài trên máy DBA. Test ít nhất các luồng đăng nhập, truy vấn, transaction, prepared statement, bulk load và reconnect sau failover.

Nếu dùng caching_sha2_password, xác minh driver hỗ trợ phương thức này và cơ chế trao đổi khóa phù hợp với TLS hoặc cấu hình RSA. Đừng hạ phương thức xác thực của toàn hệ thống chỉ để giữ lại một client quá cũ; nâng connector và kiểm thử là hướng xử lý bền vững hơn.

### 8. Kiểm tra công cụ backup, restore và replication

#### 8.1. Công cụ backup logic

mysqldump và MySQL Shell dump/load utilities có vòng đời và khả năng khác nhau. Trước nâng cấp, xác minh client tool có thể kết nối server đích, hiểu kiểu dữ liệu/collation và tạo dump có thể import vào phiên bản mục tiêu.

Với mysqldump, kiểm tra các tùy chọn đang dùng như single-transaction, routines, triggers, events, source-data/master-data, set-gtid-purged và cách xử lý DEFINER. Một tùy chọn có thể đổi tên, deprecated hoặc thay đổi hành vi theo phiên bản.

MySQL Shell cung cấp tiện ích dump/load cho schema lớn, song song hóa và chuyển dữ liệu giữa các phiên bản. Kiểm tra phiên bản MySQL Shell, target version, tùy chọn tương thích và output của upgrade checker. Không giả định dump được tạo bởi một MySQL Shell mới luôn nạp được vào server cũ.

#### 8.2. Công cụ backup vật lý

MySQL Enterprise Backup và Percona XtraBackup có ma trận tương thích theo phiên bản server, định dạng dữ liệu, plugin mã hóa và nền tảng. Physical backup phụ thuộc cấu trúc file, redo/undo, data dictionary và tính năng storage engine.

Trước nâng cấp:

1. Kiểm tra đúng phiên bản công cụ backup/prepare/restore cho phiên bản server nguồn.
2. Xác minh hỗ trợ cho phiên bản đích và đường nâng cấp dự kiến.
3. Kiểm tra plugin mã hóa, keyring, compression và page size.
4. Thực hiện backup đầy đủ, prepare và restore thử nghiệm trên môi trường cô lập.
5. Ghi lại thời gian backup/restore, lỗi và kết quả kiểm tra dữ liệu.

Không dùng một bản physical backup như thể đó là logical dump có thể nạp vào bất kỳ phiên bản nào. Khi nâng cấp major version, tuân thủ đường nâng cấp và hướng dẫn của công cụ.

#### 8.3. Binlog và replication

mysqlbinlog phải đọc được định dạng binlog do server tạo ra. Khi thay đổi major version, row event, checksum, GTID hoặc tên lệnh replication, kiểm tra client utility tương thích và thử phát lại một đoạn log trên instance lab.

Các lệnh trạng thái/điều khiển replication đã đổi tên trong các phiên bản MySQL:

| Mục đích | Phiên bản cũ | Phiên bản mới |
|---|---|---|
| Xem trạng thái source binlog | SHOW MASTER STATUS | SHOW BINARY LOG STATUS trong MySQL 8.4 |
| Xem trạng thái replica | SHOW SLAVE STATUS | SHOW REPLICA STATUS từ MySQL 8.0.22 |
| Bắt đầu/dừng replica | START SLAVE / STOP SLAVE | START REPLICA / STOP REPLICA |
| Cấu hình source | CHANGE MASTER TO | CHANGE REPLICATION SOURCE TO từ MySQL 8.0.23 |

Script vận hành cần kiểm tra phiên bản trước khi gọi lệnh. Một câu lệnh cũ có thể vẫn tồn tại nhưng đã deprecated trong bản chuyển tiếp; đến bản mới hơn, lệnh có thể bị loại bỏ.

### 9. Router, Shell và công cụ HA

Nếu hệ thống dùng InnoDB Cluster hoặc Group Replication, kiểm tra tương thích đồng bộ giữa MySQL Server, MySQL Shell và MySQL Router.

Các điểm cần kiểm tra:

- MySQL Shell AdminAPI nhận diện đúng phiên bản server và metadata schema.
- MySQL Router hỗ trợ phiên bản metadata của cluster và topology đang triển khai.
- Router bootstrap/configuration trỏ đúng metadata server và endpoint.
- TLS, authentication và user metadata của Router vẫn hợp lệ.
- Upgrade metadata được thực hiện theo hướng dẫn của MySQL Shell khi phiên bản yêu cầu.
- Health check và routing read/write vẫn phân biệt primary với secondary.

Không nâng cấp riêng Router hoặc Shell trong production mà chưa thử với cluster metadata thực tế. Một Router cũ có thể không hiểu metadata mới; một Shell mới có thể yêu cầu nâng cấp metadata trước khi dùng một số AdminAPI.

### 10. Công cụ schema migration và online DDL

Các công cụ như pt-online-schema-change và gh-ost có thể thay đổi cách thực hiện DDL: tạo bảng mới, copy dữ liệu theo chunk, đồng bộ thay đổi rồi đổi tên bảng. Chúng có các giới hạn riêng liên quan đến trigger, foreign key, partition, binlog format, GTID, replication topology và quyền.

Trước khi dùng trên phiên bản mới:

- Kiểm tra ma trận hỗ trợ chính thức của phiên bản công cụ.
- Xác định bảng có trigger, foreign key, generated column hoặc partition không.
- Xác minh binlog format, GTID và replica có nhận đúng thay đổi không.
- Đánh giá metadata lock ở bước cutover/rename.
- Kiểm tra quyền tạo/drop/rename table, trigger và replication.
- Chạy thử với bản sao có kích thước và workload gần production.

Không coi online schema change là không downtime. Các công cụ thường giảm thời gian khóa dài nhưng vẫn có bước cutover cần metadata lock; tải copy và đồng bộ cũng có thể làm replica lag tăng.

### 11. Upgrade checker và quy trình kiểm tra

MySQL Shell có Upgrade Checker Utility để rà soát một số vấn đề tương thích trước nâng cấp. Có thể chạy trong MySQL Shell:

~~~javascript
util.checkForServerUpgrade(
  'admin@mysql-source.example.net:3306',
  { targetVersion: '8.4.0' }
);
~~~

Thay tài khoản, host và targetVersion theo kế hoạch thật. Kết quả phụ thuộc phiên bản MySQL Shell, quyền truy cập và target version. Đọc từng warning/error, lưu báo cáo và xử lý các blocker trước khi tiếp tục. Upgrade checker không thay thế kiểm tra plugin riêng của vendor, stored object, ứng dụng hoặc công cụ backup.

Đối với MySQL 8.0.16 trở lên, server tự xử lý phần nâng cấp system tables/data dictionary khi khởi động theo quy trình được hỗ trợ; không giả định phải chạy mysql_upgrade thủ công như các phiên bản cũ. Kiểm tra tài liệu phiên bản và trạng thái log startup thay vì thêm một bước cũ vào runbook.

Quy trình khuyến nghị:

1. **Inventory:** ghi phiên bản server, plugin/component, stored object, driver, tool, Router và monitoring.
2. **Compatibility matrix:** đánh dấu supported, unsupported, deprecated, cần cấu hình hoặc chưa kiểm chứng cho từng thành phần.
3. **Pre-upgrade checks:** chạy Upgrade Checker, kiểm tra deprecated feature, reserved word, collation và định dạng dữ liệu.
4. **Backup và rehearsal:** backup đầy đủ, giữ keyring, restore thử trên bản sao và chạy test ứng dụng.
5. **Upgrade thử:** nâng cấp môi trường staging có cùng plugin, object, tool và workload quan trọng.
6. **Post-upgrade inventory:** so sánh plugin/component status, DEFINER, SQL mode, charset/collation và công cụ.
7. **Functional tests:** gọi routine, view, trigger, event; thử authentication, backup/restore, replication, monitoring và failover.
8. **Cutover:** chỉ triển khai production khi các blocker đã xử lý và có phương án phục hồi được kiểm chứng.

### 12. Kiểm thử stored object sau nâng cấp

Kiểm tra metadata là bước đầu. Mỗi object quan trọng cần có test case xác nhận kết quả và quyền.

| Object | Ca kiểm thử gợi ý |
|---|---|
| View | SELECT bằng tài khoản ứng dụng; kiểm tra SQL SECURITY, DEFINER, cột và collation |
| Procedure | Gọi với input hợp lệ, NULL, biên dữ liệu; kiểm tra transaction và quyền |
| Function | Kiểm tra giá trị trả về, ép kiểu, SQL mode và deterministic behavior nếu có |
| Trigger | INSERT/UPDATE/DELETE vào bảng thử; xác minh tác động phụ đúng một lần |
| Event | Kiểm tra scheduler, trạng thái, timezone, definer và tác vụ được thực hiện đúng lịch |

Test bằng đúng tài khoản ứng dụng. Một object chạy được dưới DBA không chứng minh tài khoản production có quyền cần thiết. Với trigger và event, xác minh không tạo dữ liệu lặp khi hệ thống cũ và mới cùng hoạt động.

### 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Server không khởi động sau upgrade | Plugin/component binary không tương thích hoặc thiếu dependency | Đọc error log, kiểm tra plugin_dir và startup option; dùng binary đúng phiên bản hoặc rollback theo kế hoạch |
| Plugin chuyển sang trạng thái lỗi | Thư viện thiếu, sai ABI, sai quyền hoặc không hỗ trợ server mới | Xác minh package/vendor support, đường dẫn và quyền; không copy library tùy tiện |
| Component không được khởi tạo | URI, dependency hoặc component_load_add sai | Kiểm tra registry, startup log và cấu hình đúng phiên bản |
| Client báo authentication plugin cannot be loaded | Driver cũ hoặc auth plugin không tương thích | Nâng connector, kiểm tra plugin tài khoản và TLS; tránh hạ bảo mật toàn server |
| View/procedure báo definer does not exist | Tài khoản DEFINER không có trên target | Xác định security semantics, tạo definer least-privilege hoặc điều chỉnh object có kiểm soát |
| Stored routine có kết quả khác | SQL_MODE hoặc charset/collation lưu lúc tạo khác | Đối chiếu INFORMATION_SCHEMA và SHOW CREATE; tạo lại object trong session có cấu hình chuẩn |
| Event không chạy hoặc chạy hai lần | event_scheduler, timezone hoặc hai node cùng kích hoạt event | Chỉ bật event trên node có vai trò phù hợp; xác minh scheduler và trạng thái event |
| Backup không prepare/restore được | Tool không tương thích server, format hoặc keyring | Dùng phiên bản công cụ được hỗ trợ; kiểm tra key và thực hiện restore rehearsal |
| Router không nhận diện primary | Metadata version, Router version hoặc cluster state không tương thích | Kiểm tra Shell/Router/metadata, upgrade theo runbook và xác minh routing |
| Online schema tool bị lỗi | Trigger, FK, binlog, GTID hoặc quyền không phù hợp | Đối chiếu giới hạn công cụ, thử staging và dùng phương án DDL phù hợp |

### 14. Checklist nghiệm thu nâng cấp

- [ ] Đã lưu phiên bản MySQL, edition, OS, architecture và plugin_dir.
- [ ] Đã kiểm kê plugin và component, bao gồm trạng thái, thư viện và cách nạp startup.
- [ ] Binary của plugin/component được nhà cung cấp xác nhận tương thích với target.
- [ ] Keyring và dữ liệu mã hóa đã được backup, restore thử và xác minh đọc được.
- [ ] Authentication plugin của tài khoản và connector ứng dụng tương thích.
- [ ] View, routine, trigger và event đã được kiểm kê; DEFINER tồn tại và có quyền tối thiểu.
- [ ] SQL_MODE, charset/collation và security type của stored object đã được đối chiếu.
- [ ] Event scheduler và lịch chạy chỉ hoạt động trên node được chỉ định.
- [ ] mysqldump/MySQL Shell/physical backup/mysqlbinlog đã được kiểm tra với phiên bản target.
- [ ] MySQL Router, Shell, AdminAPI và cluster metadata tương thích.
- [ ] Công cụ online schema change, migration runner và monitoring agent đã được thử nghiệm.
- [ ] Upgrade Checker và rehearsal không còn blocker chưa xử lý.
- [ ] Backup/restore, authentication, replication, stored object và ứng dụng đã qua functional test.
- [ ] Có log, báo cáo tương thích, phương án rollback/recovery và người chịu trách nhiệm.

### 15. Bài tập thực hành

Một hệ thống đang chạy MySQL 8.0 và dự kiến nâng cấp lên MySQL 8.4. Hệ thống dùng một authentication plugin cũ, component quản lý key, một audit plugin, nhiều procedure có DEFINER là tài khoản DBA cũ, event chạy mỗi giờ, MySQL Router và công cụ physical backup.

1. Bạn sẽ lấy inventory plugin và component bằng những truy vấn nào? Vì sao cần kiểm tra cả startup configuration?
2. Cần xác minh điều gì về binary và vendor support trước khi nạp plugin trên MySQL 8.4?
3. Vì sao phải kiểm tra keyring backup và restore độc lập với backup dữ liệu?
4. Làm thế nào xác định các procedure đang phụ thuộc vào DEFINER không còn tồn tại?
5. Tại sao global SQL mode giống nhau vẫn chưa bảo đảm stored routine có cùng hành vi?
6. Làm thế nào ngăn event chạy hai lần trong lúc cutover?
7. Những thành phần nào trong bộ MySQL Shell, Router và backup cần nâng cấp hoặc kiểm thử cùng server?
8. Hãy lập test matrix cho authentication, stored object, backup/restore, replication và monitoring trước khi phê duyệt nâng cấp.

### 16. Nguyên tắc vận hành

Nâng cấp MySQL là thay đổi một hệ sinh thái phụ thuộc, không chỉ là thay phiên bản server. Plugin và component cần đúng binary, dependency và cách nạp; stored object cần DEFINER, quyền, SQL mode và charset/collation phù hợp; client và công cụ vận hành cần hiểu giao thức, định dạng dữ liệu và metadata của phiên bản mới. Hãy inventory trước, đối chiếu ma trận tương thích, restore thử backup và kiểm thử từng chức năng trên staging. Chỉ đưa hệ thống vào hoạt động khi các thành phần quan trọng đã được xác minh bằng bằng chứng thực tế.
