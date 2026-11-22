# Kế hoạch cắt chuyển, ngừng ghi và quay lui khi kiểm tra thất bại

Di chuyển cơ sở dữ liệu chỉ hoàn tất khi ứng dụng sử dụng đúng máy đích, dữ liệu được xác minh và đội vận hành biết cách xử lý nếu kiểm tra sau chuyển đổi không đạt. Cắt chuyển (cutover) là thời điểm chuyển luồng đọc/ghi từ hệ thống nguồn sang hệ thống đích. Ngừng ghi (write freeze) tạo ra một mốc dữ liệu ổn định để đồng bộ phần thay đổi cuối cùng. Quay lui (rollback) đưa dịch vụ về trạng thái đã được xác định trước nếu điều kiện chấp nhận không đạt.

Một kế hoạch tốt phải xác định rõ nguồn dữ liệu chuẩn ở từng giai đoạn, cách ngăn hai nơi cùng nhận ghi, tiêu chí quyết định tiếp tục hay dừng, và cách xử lý dữ liệu phát sinh sau khi target bắt đầu nhận giao dịch. Nội dung này áp dụng cho các đợt chuyển MySQL giữa máy chủ, cụm, môi trường cloud hoặc phiên bản triển khai khác nhau.

## 1. Xác định phạm vi và mục tiêu chuyển đổi

Trước khi chọn công cụ, cần xác định điều gì sẽ thay đổi và điều gì phải giữ nguyên:

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Source và target | Máy chủ, phiên bản, topology và endpoint nào đang là nguồn và đích? |
| Dữ liệu | Chuyển toàn bộ instance, một số database hay một tập bảng? |
| Schema | Có thay đổi kiểu dữ liệu, collation, index, partition hoặc cấu trúc bảng không? |
| Workload | Ứng dụng nào đọc, ghi, chạy batch, báo cáo hoặc dùng scheduled event? |
| Tích hợp | Có ETL, CDC consumer, queue worker, BI, backup agent hoặc dịch vụ ngoài kết nối trực tiếp không? |
| Thời gian dừng | Downtime tối đa mà nghiệp vụ chấp nhận là bao lâu? |
| RPO | Mức dữ liệu tối đa có thể mất nếu phải quay lui là bao nhiêu? |
| RTO | Dịch vụ phải phục hồi trong khoảng thời gian tối đa nào? |
| Quyết định | Ai là người xác nhận go/no-go và ai có quyền dừng cutover? |

Lập danh sách endpoint kết nối, tài khoản, secret, DNS, proxy, MySQL Router, connection pool và các tác vụ nền. Một ứng dụng có thể không phải nơi duy nhất ghi dữ liệu: cron job, event scheduler, script vận hành hoặc hệ thống tích hợp có thể vẫn ghi vào source sau khi API đã được chuyển.

Xác định trước tiêu chí thành công có thể đo được, ví dụ:

- Tất cả schema và đối tượng bắt buộc đã tồn tại trên target.
- Dữ liệu tại mốc cutover được đối chiếu trong phạm vi đã thống nhất.
- Target bắt kịp transaction cuối cùng của source trước khi ngừng ghi.
- Các luồng đọc/ghi đi đến đúng endpoint.
- Các truy vấn nghiệp vụ quan trọng và tác vụ nền chạy thành công.
- Không xuất hiện lỗi dữ liệu, lỗi kết nối hoặc độ trễ vượt ngưỡng trong thời gian theo dõi.

Không để tiêu chí như "ứng dụng có vẻ chạy được" thay thế cho phép kiểm tra định lượng.

## 2. Chọn phương pháp di chuyển và đồng bộ thay đổi

Có hai kiểu triển khai thường gặp:

**Chuyển có downtime:** dừng ghi trên source, tạo bản dump hoặc snapshot nhất quán, restore sang target, kiểm tra rồi chuyển ứng dụng. Cách này đơn giản hơn nếu dữ liệu vừa phải và thời gian dừng được chấp nhận.

**Chuyển downtime thấp:** nạp bản dữ liệu ban đầu sang target trong khi source vẫn phục vụ, sau đó dùng MySQL replication, binary log CDC hoặc công cụ di chuyển để chuyển tiếp các thay đổi. Đến thời điểm cutover, đóng luồng ghi, chờ target bắt kịp và chuyển traffic. Cách này rút ngắn write freeze nhưng cần vận hành thêm một luồng đồng bộ và kiểm soát lag.

| Phương pháp | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| Logical dump/restore | Dữ liệu nhỏ hoặc cần chọn database/table | Thời gian dump/restore, snapshot nhất quán, routines, triggers, events và quyền |
| Physical backup/restore | Dữ liệu lớn và môi trường tương thích | Phiên bản, định dạng backup, metadata GTID/binlog và quyền tệp |
| MySQL replication/CDC | Cần đồng bộ thay đổi trong khi source vẫn hoạt động | Binlog retention, GTID hoặc file/position, schema compatibility, lag và lỗi apply |
| Công cụ migration chuyên dụng | Có yêu cầu chuyển đổi nền tảng hoặc tự động hóa phức tạp | Cơ chế capture thay đổi, giới hạn kiểu dữ liệu, kiểm tra nhất quán và chi phí vận hành |

Không nên bắt đầu nạp dữ liệu trước khi xác minh target có đủ dung lượng, phiên bản hỗ trợ schema và cấu hình tương thích. Với migration có thay đổi schema, cần thiết kế ánh xạ và thứ tự biến đổi riêng; không giả định replication có thể tự chuyển đổi mọi thay đổi cấu trúc.

## 3. Chuẩn bị source và target

### 3.1. Kiểm tra tương thích

So sánh cấu hình và đối tượng giữa hai môi trường:

- Phiên bản MySQL và các tính năng SQL được sử dụng.
- Storage engine, character set, collation và độ dài index.
- SQL mode, time zone, transaction isolation và cấu hình liên quan đến ngày giờ.
- Kiểu dữ liệu, generated column, expression index, partition và constraint.
- Trigger, view, stored procedure, function, event và DEFINER.
- Tài khoản, role, grants, plugin xác thực và chính sách TLS.
- Auto-increment, foreign key, unique constraint và tên đối tượng có phân biệt hoa/thường.

Các biến như lower_case_table_names có thể ảnh hưởng cách tên bảng được lưu và so sánh giữa hệ điều hành. Cần kiểm tra trước khi restore hoặc chạy ứng dụng trên target. Đặc biệt, không thay đổi biến này tùy tiện trên một instance đã có dữ liệu.

Đảm bảo target có đủ CPU, RAM, IOPS, dung lượng lưu trữ, network throughput và giới hạn kết nối. Tính dung lượng cho cả dữ liệu, index, temporary files, relay/binlog, backup và khoảng tăng trưởng trong thời gian cutover.

### 3.2. Kiểm tra bảo mật và quyền

Tạo hoặc xác minh tài khoản ứng dụng trên target với quyền tối thiểu cần thiết. Kiểm tra tài khoản replication/CDC riêng, quyền vận hành, chứng chỉ TLS và cách cấp secret. Không sao chép tài khoản quản trị rộng chỉ để làm cho ứng dụng kết nối được.

Kiểm tra firewall, security group, DNS nội bộ, route, proxy và kết nối từ từng subnet ứng dụng. Target có thể hoạt động trong mạng riêng khi kiểm thử nhưng không truy cập được từ production subnet; hãy thử từ đúng nơi sẽ chạy ứng dụng sau cutover.

### 3.3. Chuẩn bị khôi phục

Tạo backup có thể restore của source trước khi thay đổi. Kiểm tra bản backup bằng một lần restore thử hoặc quy trình xác minh tương đương. Ghi nhận thời điểm, GTID set hoặc binary log coordinates, cấu hình và phiên bản. Backup cần được lưu ở miền lỗi và quyền truy cập tách biệt với source.

Target cũng nên có snapshot trước cutover nếu cần bảo toàn trạng thái để điều tra. Xác định thời gian lưu binlog đủ dài để hoàn tất migration và có thể khắc phục một lần gián đoạn kéo dài.

## 4. Diễn tập trước ngày cutover

Một lần diễn tập giúp đo thời gian thực tế và phát hiện các bước bị thiếu. Hãy dùng dữ liệu có kích thước và phân bố gần production; nếu dùng dữ liệu ẩn danh, vẫn cần giữ các đặc tính quan trọng như số lượng hàng, index, độ dài chuỗi và phân bố khóa.

Trong buổi diễn tập:

1. Tạo target từ đầu theo đúng cấu hình dự kiến.
2. Chạy nạp dữ liệu ban đầu và đo thời gian.
3. Bật luồng CDC/replication và tạo workload ghi đại diện trên source.
4. Đo tốc độ phát sinh thay đổi và tốc độ target áp dụng.
5. Thực hiện write freeze giả lập, ghi nhận mốc GTID hoặc binlog position và chờ target bắt kịp.
6. Chạy kiểm tra schema, checksum, truy vấn nghiệp vụ và smoke test.
7. Thử chuyển endpoint ứng dụng, drain connection pool và khôi phục endpoint cũ.
8. Đo thời gian từng bước, xác định điểm có thể thất bại và cập nhật runbook.

Nếu tốc độ phát sinh thay đổi trên source lớn hơn tốc độ target áp dụng trong thời gian dài, target sẽ không bắt kịp. Cần cải thiện năng lực target, mạng, cấu hình applier hoặc giảm tải trước khi chọn ngày chuyển đổi.

## 5. Kế hoạch write freeze

Write freeze là điểm kiểm soát quan trọng nhất của cutover. Mục tiêu là bảo đảm không còn transaction nghiệp vụ mới được ghi vào source trong khi phần thay đổi cuối cùng được áp dụng trên target.

Một write freeze đầy đủ cần bao phủ:

1. Tạm dừng API hoặc chức năng ghi theo kế hoạch; trả thông báo bảo trì hoặc đưa ứng dụng vào chế độ chỉ đọc.
2. Tạm dừng worker, queue consumer, cron job, ETL, event scheduler và script có thể ghi vào source.
3. Dừng hoặc drain các batch đang chạy; xác nhận các message chưa xử lý được giữ an toàn để chạy lại.
4. Chờ transaction đang mở hoàn tất hoặc xử lý theo quy trình đã phê duyệt.
5. Ngăn tài khoản ứng dụng và tài khoản tích hợp mở thêm luồng ghi mới vào source.
6. Ghi nhận thời điểm freeze và xác nhận từ từng chủ hệ thống.

Có thể kiểm tra transaction InnoDB còn mở trên source:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Kết quả cần được đối chiếu với process list và các job đang chạy. Không kết luận đã freeze chỉ vì không thấy transaction trong một lần truy vấn; ứng dụng hoặc job có thể mở transaction mới ngay sau đó.

Sau khi đã dừng các luồng ghi ở tầng ứng dụng, có thể bật chế độ chỉ đọc trên source như một lớp bảo vệ bổ sung:

~~~sql
SET GLOBAL super_read_only = ON;

SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Chế độ này không thay thế việc dừng ứng dụng, worker và các nguồn ghi ngoài luồng. Tài khoản quản trị có quyền cao vẫn có thể thay đổi cấu hình hoặc gỡ chế độ bảo vệ; vì vậy cần kiểm soát quyền và endpoint mạng trong suốt cửa sổ cutover. Luồng replication có thể vẫn cần đọc binlog từ source để target bắt kịp.

Ghi lại một mốc cuối cùng sau khi write freeze thực sự có hiệu lực. Với GTID, lấy tập đã thực thi trên source:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

Với replication dùng file/position, lấy trạng thái binary log theo cú pháp của phiên bản, chẳng hạn SHOW BINARY LOG STATUS hoặc SHOW MASTER STATUS trên phiên bản cũ. Lưu lại tên file và position cùng thời điểm thu thập. Không lấy mốc trước khi các transaction cuối cùng hoàn tất.

## 6. Chờ target bắt kịp và xác minh mốc dữ liệu

Nếu dùng GTID, có thể yêu cầu target chờ đến khi thực thi tập GTID đã ghi nhận từ source:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'GTID_SET_CAPTURED_FROM_SOURCE',
  60
);
~~~

Thay chuỗi minh họa bằng đúng GTID set đã thu thập. Kết quả 0 nghĩa là target đã thực thi tập GTID đó; kết quả 1 nghĩa là hết thời gian chờ; kết quả NULL cho biết hàm gặp lỗi. Nếu timeout hoặc có lỗi, không chuyển traffic ghi. Kiểm tra receiver/applier, lỗi SQL, lỗi I/O, kết nối và binlog retention.

Với replication dùng file/position, đối chiếu vị trí đã nhận và đã áp dụng trong trạng thái replica. Dùng SHOW REPLICA STATUS trên phiên bản mới hoặc cú pháp tương ứng của phiên bản cũ. Target chỉ bắt kịp khi applier đã áp dụng đến mốc cuối cùng, không chỉ khi receiver đã đọc đến mốc đó.

Nếu source đã purge binary log mà target cần, luồng replication có thể không thể tiếp tục. Không bỏ qua sự kiện hoặc tự đặt position để vượt qua khoảng trống. Cần khôi phục từ backup nhất quán và thiết lập lại tọa độ đồng bộ.

## 7. Kiểm tra trước khi chuyển traffic

Chỉ tiếp tục khi các kiểm tra được định nghĩa trước đều đạt. Nên chia thành nhiều lớp để phát hiện đúng loại sai lệch.

### 7.1. Schema và đối tượng database

So sánh:

- Database, table, column, kiểu dữ liệu, nullability và default.
- Primary key, unique key, foreign key, index và partition.
- Trigger, view, procedure, function và event.
- DEFINER, role, user, grants và quyền thực thi.
- Character set, collation, SQL mode và các biến ảnh hưởng hành vi truy vấn.

Với migration có biến đổi schema, xác minh ánh xạ từng cột và cách xử lý dữ liệu không tương thích. Ví dụ chuyển cột chuỗi sang số phải có báo cáo các giá trị không chuyển đổi được; không để lỗi chỉ xuất hiện khi ứng dụng ghi dữ liệu thật.

### 7.2. Đối soát dữ liệu

Kiểm tra theo nhiều mức:

| Phạm vi | Phép kiểm tra |
|---|---|
| Database/table | Danh sách đối tượng và số lượng bảng |
| Bảng | Row count, min/max khóa chính và số liệu tổng hợp |
| Chunk | Checksum theo dải khóa để khoanh vùng sai lệch |
| Hàng | So sánh bản ghi thiếu, thừa hoặc khác giá trị theo khóa |
| Nghiệp vụ | Tổng đơn hàng, tổng thanh toán, tồn kho, số dư hoặc chỉ số quan trọng khác |

Số hàng bằng nhau không chứng minh nội dung bằng nhau. Với bảng lớn, có thể dùng checksum theo chunk hoặc công cụ như pt-table-checksum, nhưng cần chạy trên snapshot tương đương và đánh giá tải I/O. Khi source đã freeze, việc đối chiếu thường dễ diễn giải hơn vì dữ liệu không còn thay đổi trong lúc so sánh.

### 7.3. Smoke test trên target

Kiểm tra kết nối bằng đúng tài khoản ứng dụng và TLS. Chạy các truy vấn đọc quan trọng, truy vấn có join, truy vấn phân trang, truy vấn báo cáo và các luồng phụ thuộc vào stored procedure hoặc view.

Không tạo dữ liệu production thật trong target trước khi quyết định cutover nếu chưa có kế hoạch xử lý những ghi thử đó. Nếu cần thử ghi, dùng schema/tenant kiểm thử riêng hoặc giao dịch kiểm thử được nhận diện và dọn theo quy trình.

### 7.4. Xác nhận tiêu chí go/no-go

Lập bảng ký xác nhận:

| Tiêu chí | Điều kiện GO |
|---|---|
| Đồng bộ cuối | Target đã áp dụng đến mốc GTID hoặc binlog cuối |
| Schema | Không còn sai lệch chưa được chấp thuận |
| Dữ liệu | Checksum và số liệu nghiệp vụ đạt ngưỡng đã thống nhất |
| Kết nối | Ứng dụng và job cần thiết kết nối được đến target |
| Bảo mật | Tài khoản, grants, TLS và network policy đúng |
| Hiệu năng | Thời gian phản hồi và tải target nằm trong ngưỡng |
| Khôi phục | Backup và phương án quay lui đã sẵn sàng |

Nếu bất kỳ tiêu chí bắt buộc nào không đạt, giữ ứng dụng ở trạng thái freeze hoặc khôi phục source theo phương án đã chuẩn bị. Không chuyển traffic vì áp lực thời gian khi chưa biết dữ liệu đang thiếu hay sai.

## 8. Chuyển traffic sang target

Sau khi có quyết định GO:

1. Xác nhận source vẫn bị khóa ghi và target là bản dữ liệu đã được kiểm tra.
2. Chuyển endpoint ghi sang target thông qua proxy, MySQL Router, service discovery hoặc cấu hình ứng dụng.
3. Cập nhật endpoint đọc theo kế hoạch; không gửi truy vấn cần read-after-write đến một replica chưa bắt kịp.
4. Cập nhật secret hoặc tài khoản kết nối nếu target sử dụng thông tin xác thực riêng.
5. Drain và tạo lại connection pool để tránh kết nối cũ tiếp tục trỏ đến source.
6. Khởi động lại worker và scheduled job theo thứ tự đã thống nhất.
7. Thực hiện smoke test đọc/ghi có kiểm soát trên target.
8. Theo dõi log và chỉ số trong khoảng giám sát tăng cường.

DNS có thể bị cache bởi JVM, thư viện client, proxy hoặc hệ điều hành. Chỉ đổi DNS không bảo đảm mọi connection pool lập tức dùng target. Cần xác minh endpoint thực tế từ từng dịch vụ và kiểm tra số kết nối trên cả source lẫn target.

Sau khi target bắt đầu nhận ghi production, target trở thành nguồn dữ liệu chuẩn mới. Source cũ phải tiếp tục được fence để tránh ứng dụng, job cũ hoặc người vận hành vô tình ghi vào đó.

## 9. Theo dõi sau cutover

Trong thời gian giám sát tăng cường, theo dõi:

- Tỷ lệ lỗi kết nối, lỗi xác thực, timeout và deadlock.
- Latency truy vấn, slow query, CPU, memory, IOPS và dung lượng.
- Số lượng connection, connection pool và luồng ghi.
- Số liệu nghiệp vụ như đơn hàng, thanh toán, tồn kho và số dư.
- Queue backlog, job retry, event scheduler và tác vụ tích hợp.
- Binlog, backup, replication hoặc CDC consumer còn lại.

So sánh với baseline trước cutover và ngưỡng đã thống nhất. Một hệ thống có thể trả HTTP 200 nhưng ghi thiếu dữ liệu do job nền chưa được khởi động; cần kiểm tra cả luồng đồng bộ và các tác vụ không chạy qua API.

Giữ source cũ ở trạng thái có thể phục hồi nhưng không nhận ghi. Duy trì backup và binlog theo chính sách. Không xóa source cũ hoặc snapshot ngay sau khi ứng dụng hoạt động; thời gian giữ lại phải theo quy định lưu trữ và thời gian xác nhận ổn định.

## 10. Thiết kế rollback và điểm không thể quay lui đơn giản

Rollback cần được định nghĩa theo từng giai đoạn. Khả năng quay lại phụ thuộc vào việc target đã nhận ghi production hay chưa.

### 10.1. Trước khi target nhận ghi

Nếu target chưa nhận bất kỳ transaction production nào, việc quay lại thường đơn giản hơn:

1. Dừng quá trình chuyển traffic.
2. Giữ target ở trạng thái không nhận ghi.
3. Chuyển endpoint ứng dụng về source.
4. Xác nhận connection pool đã kết nối lại source.
5. Gỡ write freeze trên source theo đúng thứ tự và chỉ khi đã xác nhận không có target-only write.
6. Khởi động lại worker/job và chạy smoke test.

Vì source vẫn là bản dữ liệu chuẩn và target chưa phát sinh dữ liệu nghiệp vụ mới, có thể quay lại mà không cần hợp nhất hai nhánh ghi.

### 10.2. Sau khi target đã nhận ghi

Khi target đã nhận transaction production, source cũ có thể đã lỗi thời. Chuyển ứng dụng quay lại source ngay lập tức có thể làm mất các transaction đã được xác nhận trên target.

Trước cutover, nếu yêu cầu rollback nhanh sau khi target đã nhận ghi, phải thiết kế và diễn tập một đường đồng bộ ngược được hỗ trợ. Đường này cần xác định:

- Cách ghi và giữ binlog trên target.
- Cách source cũ nhận thay đổi từ target.
- Tính tương thích schema và topology.
- Cách ngăn ghi hai chiều ngoài kế hoạch.
- Xử lý transaction xung đột và khóa chính/auto-increment.
- Điều kiện GTID và khả năng thiết lập lại replication.
- Cách xác minh dữ liệu sau đồng bộ ngược.

Không bật replication hai chiều một cách tùy tiện. Hai máy cùng nhận ghi có thể tạo transaction xung đột, vòng lặp replication hoặc hai nhánh dữ liệu không thể hợp nhất tự động.

Nếu không có reverse replication đã được kiểm thử, lựa chọn an toàn thường là giữ target làm nguồn ghi và sửa lỗi theo hướng forward-fix. Nếu bắt buộc quay lui, cần freeze ghi trên target, ghi nhận GTID/binlog cuối, đánh giá dữ liệu phát sinh và lập kế hoạch hợp nhất có kiểm chứng trước khi mở source cũ.

### 10.3. Bảng quyết định rollback

| Thời điểm phát hiện lỗi | Điều kiện dữ liệu | Hướng xử lý |
|---|---|---|
| Trước write freeze | Source vẫn là nơi ghi duy nhất | Hủy migration hoặc tiếp tục ở lần khác |
| Trong write freeze, chưa chuyển traffic | Source đã bị freeze, target chưa nhận ghi | Nếu target kiểm tra thất bại, gỡ freeze source và khởi động lại dịch vụ theo runbook |
| Sau đổi endpoint nhưng chưa có production write | Target chưa nhận dữ liệu nghiệp vụ mới | Chuyển endpoint về source, xác nhận pool rồi mở lại ghi |
| Sau khi target đã nhận production write | Target có transaction mới | Không chuyển về source cũ ngay; forward-fix hoặc đồng bộ ngược và đối soát trước |
| Phát hiện dữ liệu sai trên target | Cần xác định phạm vi transaction sai và bản chuẩn | Freeze ghi, bảo toàn log/backup, phân tích và chọn phục hồi có kiểm chứng |

## 11. Runbook cutover mẫu

### Trước cửa sổ chuyển đổi

- [ ] Chốt source, target, phạm vi dữ liệu và người quyết định GO/NO-GO.
- [ ] Hoàn thành ít nhất một lần diễn tập với dữ liệu và workload đại diện.
- [ ] Xác minh backup source có thể restore.
- [ ] Kiểm tra schema, phiên bản, cấu hình, quyền, TLS và network.
- [ ] Nạp dữ liệu ban đầu và bật CDC/replication nếu sử dụng.
- [ ] Xác nhận target có thể bắt kịp tốc độ phát sinh transaction.
- [ ] Chuẩn bị thay đổi endpoint, connection pool và phương án rollback.
- [ ] Thông báo cửa sổ bảo trì cho các chủ hệ thống liên quan.

### Trong cửa sổ chuyển đổi

- [ ] Tạm dừng API ghi, worker, queue consumer, cron và event có ghi dữ liệu.
- [ ] Drain transaction đang chạy và xác nhận không còn nguồn ghi mới.
- [ ] Bật write protection trên source sau khi các luồng ghi ứng dụng đã dừng.
- [ ] Ghi nhận GTID set hoặc binary log file/position cuối.
- [ ] Chờ target áp dụng hết thay đổi đến mốc cuối.
- [ ] Kiểm tra schema, checksum, số liệu nghiệp vụ và truy vấn quan trọng.
- [ ] Ra quyết định GO/NO-GO theo tiêu chí đã thống nhất.
- [ ] Nếu GO, chuyển endpoint, tạo lại connection pool và smoke test.
- [ ] Khởi động worker/job và theo dõi các luồng tích hợp.

### Sau khi chuyển đổi

- [ ] Theo dõi lỗi, latency, tải, deadlock và số liệu nghiệp vụ.
- [ ] Xác nhận mọi ứng dụng dùng đúng target.
- [ ] Giữ source cũ không nhận ghi trong thời gian xác nhận.
- [ ] Tạo backup target và kiểm tra quy trình restore.
- [ ] Lưu GTID/binlog marker, kết quả checksum, thời gian và người phê duyệt.
- [ ] Chỉ kết thúc thời gian giữ source cũ sau khi đạt điều kiện lưu trữ và vận hành.

## 12. Tình huống thực hành

Một cửa hàng trực tuyến chuyển database từ máy chủ MySQL cũ sang target mới. Bản dump ban đầu đã được restore và replication đang đồng bộ. Trong giờ cutover, nhóm vận hành tạm dừng API ghi nhưng phát hiện một queue consumer vẫn cập nhật trạng thái thanh toán trên source.

Hãy xử lý theo trình tự:

1. Không ghi nhận write freeze hoàn tất khi queue consumer vẫn còn ghi.
2. Tạm dừng consumer, xác nhận message chưa xử lý được giữ trong queue và kiểm tra transaction đang mở.
3. Chờ transaction cuối hoàn tất, bật write protection trên source và ghi nhận GTID set cuối.
4. Chờ target thực thi đến GTID set đó, sau đó đối chiếu số đơn hàng, thanh toán và checksum các bảng liên quan.
5. Nếu target đạt tiêu chí, chuyển endpoint và khởi động consumer để tiếp tục xử lý message trên target.
6. Nếu target không đạt tiêu chí trước khi nhận production write, quay lại source theo runbook.
7. Nếu lỗi chỉ được phát hiện sau khi target đã xử lý thanh toán mới, freeze target và phân tích transaction phát sinh trước khi quyết định forward-fix hay đồng bộ ngược.

Tình huống này cho thấy write freeze phải bao phủ mọi nguồn ghi, không chỉ giao diện người dùng. Đồng thời, rollback sau khi target nhận ghi cần xử lý dữ liệu mới, không thể chỉ đổi DNS về máy chủ cũ.

## 13. Câu hỏi tự kiểm tra

1. Write freeze cần dừng những thành phần nào ngoài API của ứng dụng?
2. Vì sao phải ghi nhận GTID hoặc binary log position sau khi transaction cuối cùng hoàn tất?
3. Receiver đã nhận đến mốc cuối có đồng nghĩa applier đã áp dụng đến mốc đó không?
4. Vì sao số lượng hàng bằng nhau chưa đủ chứng minh dữ liệu giống nhau?
5. Trước khi target nhận production write, rollback khác gì so với rollback sau khi target đã nhận ghi?
6. Vì sao không nên bật replication hai chiều tùy tiện để giữ khả năng quay lui?
7. Những điều kiện nào phải đạt trước khi quyết định GO?
8. Sau cutover, vì sao cần giữ source cũ ở trạng thái không nhận ghi trong thời gian xác nhận?

Một cutover MySQL có thể kiểm soát được khi mỗi giai đoạn có mốc dữ liệu, chủ sở hữu, tiêu chí kiểm tra và phương án xử lý lỗi rõ ràng. Write freeze tạo mốc đồng bộ cuối; đối soát chứng minh target đủ đúng; chuyển traffic đưa target thành nguồn ghi mới; rollback phải tính đến mọi transaction đã phát sinh sau thời điểm đó.
