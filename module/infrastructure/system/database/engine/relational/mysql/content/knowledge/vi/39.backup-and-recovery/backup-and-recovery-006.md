# MySQL Shell dump/load utilities và điều kiện tương thích

MySQL Shell cung cấp bộ tiện ích dump và load để xuất dữ liệu logic từ MySQL, chuyển bộ dữ liệu đó sang máy chủ khác hoặc khôi phục vào một môi trường mới. Các tiện ích này phù hợp khi cần chọn phạm vi schema hoặc bảng, chia nhỏ dữ liệu lớn, chạy song song và tiếp tục quá trình nạp sau khi bị gián đoạn.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào sao lưu và phục hồi cơ sở dữ liệu quan hệ trong thực tế. Ta sẽ dùng các tiện ích **util.dumpInstance()**, **util.dumpSchemas()**, **util.dumpTables()** và **util.loadDump()**, đồng thời xem xét khác biệt phiên bản, cấu hình máy chủ, quyền truy cập và cách kiểm tra kết quả.

## 1. Dump/load của MySQL Shell là gì?

Dump/load của MySQL Shell là cơ chế sao lưu và chuyển dữ liệu ở mức logic:

1. MySQL Shell đọc cấu trúc database, metadata và dữ liệu từ máy chủ nguồn.
2. Tiện ích dump ghi cấu trúc và dữ liệu thành một bộ tệp trong thư mục đích hoặc vị trí lưu trữ được hỗ trợ.
3. Bộ tệp được chuyển đến máy chủ đích.
4. Tiện ích load đọc manifest và các tệp, tạo lại đối tượng, nạp dữ liệu và hoàn tất các bước được cấu hình.

Đây không phải bản sao vật lý của thư mục dữ liệu InnoDB. Bộ dump không thay thế backup vật lý, snapshot volume hoặc bản sao lưu do nền tảng lưu trữ cung cấp. Nó cũng không tự lưu toàn bộ cấu hình máy chủ, file chứng thư TLS, khóa mã hóa, cấu hình replication hay mọi trạng thái vận hành bên ngoài database.

Một bộ dump thường gồm manifest mô tả nội dung, các tệp DDL và nhiều tệp dữ liệu đã chia chunk, có thể được nén. Vì vậy, cần giữ nguyên cấu trúc thư mục và toàn bộ tệp đi kèm. Không chỉ sao chép một vài tệp dữ liệu hoặc đổi tên tệp theo ý muốn.

### Khi nào nên dùng?

- Chuyển một instance hoặc một số schema sang máy chủ mới.
- Sao lưu logic để có thể khôi phục chọn lọc schema hoặc bảng.
- Di chuyển môi trường phát triển, kiểm thử và staging.
- Xuất dữ liệu lớn với nhiều luồng đọc và nạp song song.
- Tạo bộ dump tương thích với nền tảng đích theo các kiểm tra và chuyển đổi được hỗ trợ.

Nếu mục tiêu là khôi phục rất nhanh một máy chủ lớn, giữ nguyên toàn bộ file dữ liệu và giảm thời gian xuất/nhập, hãy đánh giá thêm backup vật lý hoặc giải pháp backup của nền tảng. Dump logic phải đọc và ghi lại dữ liệu, do đó thời gian phục hồi phụ thuộc kích thước dữ liệu, số lượng đối tượng, tốc độ lưu trữ, mạng và tài nguyên máy chủ.

## 2. Chọn đúng tiện ích dump

MySQL Shell có ba tiện ích xuất dữ liệu chính:

| Tiện ích | Phạm vi | Trường hợp sử dụng |
|---|---|---|
| **util.dumpInstance()** | Các schema người dùng trong instance và các thành phần tài khoản được cấu hình để xuất | Di chuyển hoặc sao lưu logic ở phạm vi instance |
| **util.dumpSchemas()** | Một danh sách schema được chỉ định | Chỉ chuyển một số database |
| **util.dumpTables()** | Một danh sách bảng trong một schema | Chuyển một phần dữ liệu hoặc một nhóm bảng |

Các schema hệ thống như **mysql**, **sys**, **performance_schema** và **information_schema** không được xử lý như schema ứng dụng thông thường trong bộ dump instance. Tài khoản người dùng và role là phần riêng cần kiểm tra tùy tiện ích, tùy chọn và phiên bản MySQL Shell. Không giả định việc dump schema ứng dụng đồng nghĩa đã xuất toàn bộ tài khoản, grant hoặc cấu hình máy chủ.

### Dump toàn instance

Mở MySQL Shell và kết nối đến máy chủ nguồn:

~~~javascript
shell.connect("backup_user@mysql-source.example:3306");
~~~

Sau đó chạy trong chế độ JavaScript:

~~~javascript
util.dumpInstance("/backup/mysql-instance", {
  threads: 8,
  consistent: true,
  chunking: true,
  bytesPerChunk: "64M",
  showProgress: true
});
~~~

Đường dẫn trên là ví dụ trên máy chạy MySQL Shell. Tài khoản, thư mục và số luồng phải được điều chỉnh theo môi trường thực tế. Có thể chọn một thư mục mới để tránh ghi đè lên bộ dump cũ.

### Dump một số schema

~~~javascript
util.dumpSchemas(
  ["sales", "warehouse"],
  "/backup/business-schemas",
  {
    threads: 4,
    consistent: true,
    showProgress: true
  }
);
~~~

Danh sách schema phải tồn tại trên máy chủ nguồn và người chạy cần có quyền đọc các đối tượng tương ứng.

### Dump một số bảng

~~~javascript
util.dumpTables(
  "sales",
  ["orders", "order_items"],
  "/backup/sales-orders",
  {
    threads: 4,
    consistent: true,
    showProgress: true
  }
);
~~~

Khi chỉ dump một vài bảng, hãy xác định các phụ thuộc giữa chúng. Một bảng có thể tham chiếu khóa ngoại đến bảng khác, view hoặc routine có thể phụ thuộc vào bảng không nằm trong danh sách. Bộ dump bảng không tự bảo đảm rằng tập đối tượng được chọn là một ứng dụng hoàn chỉnh có thể chạy độc lập.

## 3. Các tùy chọn dump quan trọng

### Số luồng và chia chunk

**threads** điều khiển số luồng thực hiện công việc song song. Tăng số luồng có thể tăng tốc độ đọc, nén và ghi dữ liệu, nhưng cũng làm tăng tải CPU, bộ nhớ, I/O và kết nối trên máy chủ nguồn.

**chunking** cho phép chia bảng lớn thành nhiều phần dữ liệu để nhiều luồng xử lý. **bytesPerChunk** đặt kích thước mục tiêu cho chunk. Ví dụ, giá trị **64M** yêu cầu các chunk có kích thước xấp xỉ 64 MB; kích thước thực tế có thể khác do dữ liệu và cách phân chia.

Việc chia chunk hiệu quả phụ thuộc cấu trúc bảng và khóa có thể dùng để phân vùng dữ liệu. Bảng lớn không có primary key hoặc unique index phù hợp có thể không được chia nhỏ như mong muốn, làm giảm khả năng song song. Hãy xem log dump để biết bảng nào được chia chunk và bảng nào được xử lý như một phần lớn.

Không nên đặt threads thật cao ngay từ đầu. Hãy đo CPU, I/O, dung lượng tạm, thời gian truy vấn và tải ứng dụng trên máy chủ nguồn. Dump chạy song song vẫn có thể cạnh tranh tài nguyên với workload production.

### Tính nhất quán của dữ liệu

Tùy chọn **consistent** mặc định được bật trong các tiện ích dump. Mục tiêu là tạo bộ dump phản ánh dữ liệu tại một thời điểm nhất quán. Với InnoDB, cơ chế snapshot giao dịch giúp các luồng đọc nhìn thấy trạng thái dữ liệu nhất quán. Để xử lý metadata và các bảng không hỗ trợ giao dịch, MySQL Shell còn có thể cần các khóa hoặc quyền backup phù hợp với phiên bản máy chủ.

Điều đó không có nghĩa dump nhất quán luôn chạy mà không có tác động khóa. Hoạt động DDL đồng thời, bảng không transactional và các cơ chế khóa trên từng phiên bản có thể ảnh hưởng đến workload. Lên lịch dump trong cửa sổ phù hợp, theo dõi các giao dịch dài và hạn chế thay đổi cấu trúc bảng trong khi dump.

Chỉ tắt **consistent** khi đã hiểu rõ rủi ro và có cơ chế khác để bảo đảm tính nhất quán. Nếu nguồn tiếp tục ghi dữ liệu trong lúc dump không nhất quán, các bảng hoặc các phần dữ liệu có thể phản ánh những thời điểm khác nhau.

### Nén và giới hạn tốc độ

MySQL Shell có thể nén dữ liệu dump để giảm dung lượng lưu trữ và lưu lượng truyền. Nén giúp tiết kiệm băng thông nhưng sử dụng CPU; lựa chọn thuật toán và mức nén phụ thuộc phiên bản MySQL Shell.

Các tùy chọn giới hạn tốc độ như **maxRate** có thể được dùng để tránh dump chiếm quá nhiều băng thông hoặc tài nguyên đọc. Cần kiểm tra đơn vị và phạm vi áp dụng của tùy chọn trong đúng phiên bản Shell trước khi đặt giới hạn.

### Lọc nội dung

Các tiện ích hỗ trợ chọn schema, bảng và trong một số trường hợp lọc theo đối tượng cần xuất. Khi thiết kế bộ dump có chọn lọc:

- Xác nhận bảng được chọn có đủ dữ liệu tham chiếu cần thiết.
- Kiểm tra view, trigger, routine, event và khóa ngoại phụ thuộc vào đối tượng ngoài phạm vi.
- Xác định có cần xuất tài khoản và quyền hay không.
- Lưu lại câu lệnh, bộ lọc và phiên bản công cụ để lần sau có thể tái tạo cùng phạm vi.

Không dùng bộ lọc để bỏ qua dữ liệu mà ứng dụng cần cho tính toàn vẹn hoặc khả năng khởi động.

## 4. Kiểm tra tương thích trước khi dump và load

Một bộ dump được tạo thành công chưa chứng minh rằng nó có thể nạp vào mọi máy chủ MySQL. Cần kiểm tra đồng thời phiên bản MySQL Shell, phiên bản server nguồn, phiên bản server đích, cấu trúc dữ liệu và các tính năng được sử dụng.

### Phiên bản MySQL Shell và MySQL Server

Các tiện ích dump/load được phân phối cùng MySQL Shell; phiên bản Shell quyết định các tùy chọn và định dạng dump mà công cụ hiểu được. Nên dùng phiên bản MySQL Shell bằng hoặc mới hơn phiên bản đã tạo bộ dump khi thực hiện load, đồng thời kiểm tra ghi chú phát hành của cả Shell và MySQL Server.

Server đích phải hỗ trợ các kiểu dữ liệu, cú pháp DDL, collation, engine, plugin xác thực và tính năng mà bộ dump sử dụng. Khi chuyển từ phiên bản mới về phiên bản cũ, có thể gặp cú pháp hoặc tính năng không được hỗ trợ. Không coi việc cùng là MySQL là đủ để bảo đảm tương thích.

Trước khi chạy, ghi lại phiên bản ở cả hai đầu:

~~~sql
SELECT VERSION();
SELECT @@version_comment;
SHOW VARIABLES LIKE 'lower_case_table_names';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Đối chiếu thêm:

- Engine của bảng, kiểu dữ liệu, độ chính xác số và biểu diễn thời gian.
- Character set, collation và quy tắc so sánh chuỗi.
- Tên bảng và tên cột có trùng từ khóa mới ở phiên bản đích hay không.
- View, routine, trigger và event có dùng cú pháp hoặc hàm riêng của phiên bản nguồn hay không.
- Tài khoản, role, authentication plugin và các quyền có được hỗ trợ ở đích hay không.
- DEFINER, tablespace, plugin, component và các cấu hình bên ngoài có cần tạo lại hay điều chỉnh hay không.
- Khác biệt về **lower_case_table_names**, đặc biệt khi chuyển giữa hệ điều hành có quy tắc phân biệt hoa thường khác nhau.

Đối với nâng cấp hoặc chuyển đổi giữa major version, hãy làm theo đường nâng cấp được MySQL hỗ trợ. Thử nạp vào một máy chủ đích có phiên bản và cấu hình tương đương production trước khi thực hiện chuyển đổi thật.

### Kiểm tra tương thích cho MySQL Database Service

Khi đích là MySQL Database Service, tùy chọn **ocimds** của tiện ích dump có thể bật các kiểm tra tương thích dành cho dịch vụ này:

~~~javascript
util.dumpSchemas(
  ["sales"],
  "/backup/sales-for-managed-mysql",
  {
    ocimds: true,
    threads: 4,
    showProgress: true
  }
);
~~~

Các kiểm tra có thể phát hiện những đối tượng hoặc quyền không phù hợp với nền tảng đích. Có thể kết hợp tùy chọn **compatibility** để yêu cầu một số phép biến đổi DDL được hỗ trợ, ví dụ:

~~~javascript
util.dumpInstance("/backup/mysql-for-target", {
  ocimds: true,
  compatibility: [
    "strip_definers",
    "strip_restricted_grants",
    "strip_tablespaces"
  ]
});
~~~

Chỉ dùng các phép biến đổi sau khi đã xem xét tác động:

- **strip_definers** loại bỏ thông tin DEFINER theo quy tắc của tiện ích. Điều này có thể làm thay đổi ngữ cảnh bảo mật khi view, routine hoặc đối tượng khác được thực thi.
- **strip_restricted_grants** xử lý các quyền bị hạn chế trên nền tảng đích. Cần rà soát để chắc chắn ứng dụng vẫn có đủ quyền cần thiết.
- **strip_tablespaces** loại bỏ tham chiếu tablespace theo quy tắc tương thích. Cần kiểm tra thiết kế lưu trữ dự kiến trên máy chủ đích.
- **force_innodb** có thể chuyển định nghĩa bảng sang InnoDB. Chỉ dùng khi chấp nhận được khác biệt về engine và hành vi.

Danh sách phép biến đổi và phạm vi hỗ trợ thay đổi theo phiên bản MySQL Shell. Kiểm tra tài liệu đúng phiên bản trước khi dùng. Không bật **ocimds** như một tùy chọn chung cho mọi đích MySQL; đây là chế độ kiểm tra dành cho nền tảng được chỉ định.

## 5. Chuẩn bị máy chủ đích

Trước khi nạp dữ liệu, chuẩn bị máy chủ đích và xác định rõ phạm vi phục hồi:

1. Cài đặt MySQL Server phiên bản được hỗ trợ và cấu hình tương thích.
2. Cài MySQL Shell phiên bản phù hợp với bộ dump.
3. Kiểm tra dung lượng đĩa cho dữ liệu, index, log, tệp tạm và phần tăng trưởng trong lúc load.
4. Kiểm tra kết nối mạng, TLS và quyền của tài khoản nạp dữ liệu.
5. Xác định schema hoặc đối tượng đã tồn tại và cách xử lý xung đột.
6. Kiểm tra cấu hình **local_infile** theo yêu cầu của phiên bản và quy trình load.
7. Xác định chính sách binary log, GTID và replication nếu máy chủ đích tham gia topology.

Một số tiện ích load sử dụng cơ chế nạp dữ liệu cục bộ qua giao thức MySQL. Vì vậy, **local_infile** có thể phải được bật trên máy chủ đích. Chỉ bật trong phạm vi và thời gian cần thiết theo chính sách bảo mật của hệ thống; kiểm tra lại trạng thái sau khi hoàn tất.

Không dùng tài khoản ứng dụng thông thường để phục hồi. Tài khoản load cần quyền tạo database và đối tượng, ghi dữ liệu, tạo index và các quyền bổ sung nếu có nạp user/role. Cấp quyền theo đúng tiện ích và phiên bản, ưu tiên tài khoản phục hồi chuyên dụng có thời hạn sử dụng rõ ràng.

## 6. Nạp bộ dump bằng util.loadDump()

Kết nối MySQL Shell đến máy chủ đích và chạy:

~~~javascript
shell.connect("restore_user@mysql-target.example:3306");

util.loadDump("/backup/mysql-instance", {
  threads: 8,
  showProgress: true
});
~~~

Đường dẫn phải trỏ đến thư mục dump hoàn chỉnh. Nếu bộ dump nằm trên máy khác, cần chuyển toàn bộ thư mục hoặc cấu hình vị trí lưu trữ từ xa được phiên bản MySQL Shell hỗ trợ.

### Nạp thử bằng dryRun

Trước khi thay đổi máy chủ đích, có thể dùng chế độ chạy thử:

~~~javascript
util.loadDump("/backup/mysql-instance", {
  dryRun: true,
  showProgress: true
});
~~~

Dry run giúp kiểm tra bộ dump và báo cáo các hành động dự kiến mà không thực hiện quá trình nạp dữ liệu đầy đủ. Nó không thay thế một lần phục hồi thử hoàn chỉnh; một số lỗi chỉ xuất hiện khi thực sự tạo đối tượng, ghi dữ liệu hoặc xây index.

### Điều chỉnh song song và index

Với bộ dữ liệu lớn, có thể tăng **threads** để nạp nhiều bảng hoặc chunk cùng lúc. Hãy theo dõi CPU, I/O, redo log, dung lượng đĩa và tải của máy chủ đích. Nếu server bị nghẽn, giảm số luồng hoặc giới hạn tốc độ thay vì tiếp tục tăng song song.

Tùy chọn **deferTableIndexes** cho phép trì hoãn việc tạo một số index cho đến sau khi nạp dữ liệu. Ví dụ:

~~~javascript
util.loadDump("/backup/mysql-instance", {
  threads: 8,
  deferTableIndexes: "all",
  showProgress: true
});
~~~

Tạo secondary index sau khi nạp dữ liệu có thể nhanh hơn trong một số workload lớn, nhưng giai đoạn tạo index cần thêm dung lượng và I/O. Không áp dụng chỉ vì dữ liệu lớn; hãy thử nghiệm và so sánh thời gian tổng thể.

Sau khi load, có thể cần cập nhật thống kê optimizer để kế hoạch thực thi phản ánh dữ liệu mới. Tùy chọn **analyzeTables** của tiện ích load có thể hỗ trợ bước này. Nếu không dùng tùy chọn, DBA có thể chủ động chạy ANALYZE TABLE cho các bảng phù hợp sau khi nạp.

### Tiếp tục sau khi bị gián đoạn

Quá trình load có thể kéo dài và bị gián đoạn do mất kết nối, hết dung lượng hoặc lỗi máy chủ. MySQL Shell duy trì thông tin tiến độ để hỗ trợ tiếp tục load trong các điều kiện được hỗ trợ. Giữ nguyên bộ dump, các tệp tiến độ và môi trường đích; xem thông báo lỗi để quyết định có thể chạy lại hay phải xử lý đối tượng đã tạo.

Không xóa file tiến độ hoặc dùng tùy chọn reset tiến độ theo thói quen. Reset có thể khiến tiện ích thực hiện lại các công việc đã hoàn tất và phát sinh xung đột với đối tượng đã tồn tại. Nếu cần nạp lại từ đầu, xác định rõ cách làm sạch schema hoặc máy chủ đích và bảo đảm dữ liệu hiện có đã được bảo vệ.

## 7. Tài khoản, quyền và dữ liệu bảo mật

Dump schema ứng dụng và dump tài khoản là hai vấn đề cần xem xét riêng. Khi chuyển instance, kiểm tra xem bộ dump có chứa user và role theo lựa chọn đã dùng hay không. Nếu không nạp tài khoản, phải tạo lại người dùng, role và grant bằng quy trình quản trị được phê duyệt.

Khi nạp user/role:

- Rà soát các tài khoản nội bộ hoặc tài khoản không còn cần thiết.
- Kiểm tra host pattern và giới hạn nguồn kết nối ở môi trường đích.
- Kiểm tra authentication plugin và chính sách mật khẩu được máy chủ đích hỗ trợ.
- Rà soát DEFINER của view, routine, trigger và event.
- Không sao chép quyền quản trị rộng hơn mức ứng dụng cần.
- Bảo vệ bộ dump vì nó có thể chứa dữ liệu nhạy cảm, thông tin tài khoản và cấu trúc nội bộ.

Tệp dump có thể được lưu ở thư mục tạm hoặc object storage. Hạn chế quyền đọc, mã hóa khi lưu và khi truyền, quản lý vòng đời bản sao, ghi nhận người tải xuống và xóa bản tạm theo chính sách. Không đưa tệp dump vào kho mã nguồn hoặc chia sẻ qua kênh không được phê duyệt.

## 8. GTID và binary log khi di chuyển

Nếu máy chủ nguồn hoặc đích tham gia replication, việc xử lý GTID cần được lập kế hoạch riêng. Một lần load logic có thể cần mang theo hoặc cập nhật thông tin GTID tùy mục tiêu: tạo máy chủ độc lập, thay thế replica hay khởi tạo topology mới.

Không tự động áp dụng GTID của nguồn vào máy chủ đích chỉ vì muốn phục hồi dữ liệu. Việc thay thế hoặc bổ sung tập GTID đã thực thi có thể ảnh hưởng đến khả năng kết nối replication, phát hiện transaction đã chạy và tính đúng đắn của topology. Trước khi dùng tùy chọn cập nhật GTID của **loadDump**, hãy xác định:

- Máy chủ đích có phải instance mới, replica hay máy chủ đã có workload không?
- Tập GTID hiện có ở nguồn và đích là gì?
- Binary log có cần ghi lại các thay đổi được nạp không?
- Replica sẽ bắt đầu từ vị trí hoặc tập GTID nào?
- Có cần giữ lại lịch sử replication hiện có hay khởi tạo topology mới?

Các tùy chọn như **updateGtidSet** và **skipBinlog** có tác động đến trạng thái replication hoặc binary log. Chỉ dùng sau khi đối chiếu tài liệu phiên bản và có kế hoạch được DBA phê duyệt. Với phục hồi thông thường vào một môi trường độc lập, không thay đổi GTID nếu chưa có yêu cầu cụ thể.

## 9. Kiểm tra kết quả sau khi phục hồi

Một lệnh load kết thúc thành công chỉ xác nhận tiện ích đã hoàn thành các bước mà nó thực hiện. DBA vẫn cần kiểm tra dữ liệu và khả năng hoạt động của ứng dụng.

### Kiểm tra đối tượng và số lượng dữ liệu

~~~sql
SHOW DATABASES;
SHOW TABLES FROM sales;
SHOW CREATE TABLE sales.orders\G
SELECT COUNT(*) FROM sales.orders;
SELECT COUNT(*) FROM sales.order_items;
~~~

So sánh số lượng bản ghi với nguồn tại cùng phạm vi và thời điểm snapshot. Với dữ liệu lớn, có thể so sánh theo từng bảng hoặc theo khoảng khóa để tìm chênh lệch nhanh hơn.

### Kiểm tra cấu trúc và phụ thuộc

- Xác minh bảng, view, routine, trigger và event cần thiết đã tồn tại.
- Kiểm tra khóa chính, khóa ngoại, unique constraint và index.
- Kiểm tra DEFINER, quyền truy cập và tài khoản ứng dụng.
- Kiểm tra charset, collation, SQL mode và engine.
- Kiểm tra event scheduler và các tác vụ nền trước khi cho phép chúng chạy ở môi trường đích.

### Kiểm tra hành vi ứng dụng

Chạy smoke test cho các thao tác đọc và ghi quan trọng, kiểm tra transaction, truy vấn có join, báo cáo, tác vụ nền và kết nối từ các dịch vụ phụ thuộc. Kiểm tra kế hoạch thực thi cho truy vấn trọng yếu nếu phiên bản, thống kê hoặc cấu hình optimizer đã thay đổi.

Không mở lưu lượng production đến máy chủ mới cho đến khi có kết quả xác minh, người chịu trách nhiệm và phương án quay lại máy chủ cũ.

## 10. Lỗi thường gặp và hướng xử lý

### Lỗi quyền khi dump

Người chạy có thể thiếu quyền đọc bảng, view, trigger, event hoặc quyền cần thiết để tạo snapshot/backup. Đọc chính xác thông báo lỗi, xác định đối tượng gây lỗi và cấp quyền tối thiểu cần thiết. Không giải quyết bằng cách dùng tài khoản quản trị rộng trên mọi môi trường.

### Không đủ dung lượng

Kiểm tra dung lượng của thư mục dump, thư mục tạm, volume dữ liệu đích, vùng lưu log và dung lượng cần để tạo index. Nén có thể giảm dung lượng lưu dump nhưng không làm giảm tương ứng dung lượng dữ liệu và index sau phục hồi. Dọn dẹp chỉ những tệp đã xác định an toàn; không xóa bộ dump hoặc file tiến độ đang được sử dụng.

### Lỗi tương thích DDL

Đối chiếu phiên bản nguồn và đích, câu lệnh DDL, collation, tablespace, engine, DEFINER và quyền. Nếu cần dùng **compatibility**, tạo lại bộ dump theo các biến đổi được chọn và rà soát kết quả trước khi nạp. Tránh sửa trực tiếp nhiều tệp DDL sau khi dump vì dễ làm bộ dump không còn nhất quán với manifest.

### Nạp dữ liệu chậm

Kiểm tra số luồng, chunking, tốc độ lưu trữ, CPU, redo log, binary log và việc xây index. Nếu một bảng lớn không chia chunk, xem xét khóa của bảng và khả năng phân chia dữ liệu. Tăng threads không giải quyết được nút thắt nằm ở một bảng đơn lẻ hoặc I/O đã bão hòa.

### Đối tượng đã tồn tại ở đích

Xác định đối tượng đó được tạo từ lần load trước, do triển khai ứng dụng hay do dữ liệu đã có từ trước. Không tùy tiện bỏ qua hoặc ghi đè. Chọn môi trường đích sạch, đổi schema đích hoặc xây quy trình hợp nhất dữ liệu có kiểm soát.

### Tài khoản không đăng nhập được sau chuyển đổi

Kiểm tra user/host, authentication plugin, mật khẩu, trạng thái khóa/hết hạn, grant, TLS và host pattern. Kiểm tra cả DEFINER của đối tượng SQL. Tạo lại hoặc điều chỉnh tài khoản bằng lệnh quản trị có kiểm soát, sau đó thử bằng chính tài khoản ứng dụng.

## 11. Quy trình mẫu cho một lần chuyển instance

Một lần chuyển instance bằng MySQL Shell có thể được tổ chức thành các giai đoạn sau:

**Giai đoạn 1 — Khảo sát**

- Ghi lại phiên bản MySQL Shell và MySQL Server nguồn, đích.
- Liệt kê schema, kích thước dữ liệu, bảng lớn, engine và các đối tượng đặc biệt.
- Kiểm tra tài khoản, role, DEFINER, replication, GTID và binary log.
- Xác định cửa sổ dump, thời gian chuyển đổi và tiêu chí quay lại.

**Giai đoạn 2 — Tạo bộ dump**

- Chọn dumpInstance, dumpSchemas hay dumpTables theo phạm vi.
- Bật consistent nếu cần snapshot nhất quán và xác nhận quyền backup.
- Chọn threads, chunking, bytesPerChunk và compression theo kết quả thử nghiệm.
- Lưu toàn bộ thư mục dump, log và thông tin phiên bản công cụ.

**Giai đoạn 3 — Kiểm tra và chuyển bộ dump**

- Xác nhận manifest và các tệp dữ liệu/DDL hiện diện đầy đủ.
- Bảo vệ bộ dump trong lúc truyền.
- Chạy dryRun trên máy chủ đích.
- Xử lý các vấn đề tương thích trước khi nạp thật.

**Giai đoạn 4 — Nạp và xác minh**

- Chuẩn bị máy chủ đích, quyền và local_infile theo yêu cầu.
- Chạy loadDump với số luồng đã kiểm thử.
- Theo dõi log, tiến độ, dung lượng và tài nguyên.
- Kiểm tra đối tượng, dữ liệu, quyền và hành vi ứng dụng.

**Giai đoạn 5 — Chuyển lưu lượng**

- Chốt trạng thái ghi dữ liệu ở nguồn theo kế hoạch chuyển đổi.
- Hoàn tất đồng bộ phần dữ liệu phát sinh sau snapshot nếu quy trình yêu cầu.
- Xác minh kết nối ứng dụng, giám sát lỗi và hiệu năng.
- Chỉ chuyển lưu lượng sau khi các tiêu chí nghiệm thu đạt yêu cầu.
- Giữ nguồn cũ trong thời gian quay lui đã thống nhất; chỉ xóa khi đã được phê duyệt.

## 12. Checklist trước và sau dump/load

**Trước khi dump**

- [ ] Đã xác định phạm vi instance, schema hoặc bảng.
- [ ] Đã kiểm tra phiên bản Shell và server nguồn.
- [ ] Đã xác nhận quyền đọc và quyền tạo snapshot/backup cần thiết.
- [ ] Đã kiểm tra bảng lớn, engine, khóa và khả năng chunking.
- [ ] Đã đánh giá tác động của consistent và lịch chạy.
- [ ] Đã chuẩn bị dung lượng, vị trí lưu, mã hóa và quyền truy cập bộ dump.

**Trước khi load**

- [ ] Đã kiểm tra phiên bản server đích và khả năng hỗ trợ DDL.
- [ ] Đã kiểm tra charset, collation, SQL mode và lower_case_table_names.
- [ ] Đã chuẩn bị quyền, local_infile và dung lượng cho data/index/log.
- [ ] Đã rà soát user, role, DEFINER, tablespace và compatibility options.
- [ ] Đã xác định chính sách GTID và binary log nếu có replication.
- [ ] Đã chạy dryRun và có phương án xử lý đối tượng đã tồn tại.

**Sau khi load**

- [ ] Đã xác minh schema, bảng, view, routine, trigger và event.
- [ ] Đã so sánh số lượng hoặc checksum dữ liệu theo tiêu chí phù hợp.
- [ ] Đã kiểm tra index, khóa, quyền, tài khoản và kết nối TLS.
- [ ] Đã chạy smoke test và kiểm tra truy vấn quan trọng.
- [ ] Đã kiểm tra log, replication và giám sát sau chuyển đổi.
- [ ] Đã xác nhận phương án quay lui và thời điểm kết thúc lưu giữ bản nguồn.

## Kết luận

MySQL Shell dump/load là công cụ mạnh cho sao lưu logic, chuyển schema và di chuyển instance. Kết quả tốt phụ thuộc vào việc chọn đúng phạm vi dump, tạo snapshot phù hợp, chia chunk và điều chỉnh luồng theo tài nguyên, đồng thời kiểm tra kỹ tương thích giữa Shell, server nguồn và server đích. Hãy xem bộ dump như một artifact cần được bảo vệ, kiểm tra và phục hồi thử định kỳ. Chỉ coi một lần chuyển đổi hoàn tất khi dữ liệu, cấu trúc, quyền, replication và hành vi ứng dụng đều đã được xác minh.
