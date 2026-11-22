# read_only, super_read_only và ngăn ghi nhầm lên replica

Trong module **DATABASE_MYSQL**, replication phân phối dữ liệu từ máy chủ nguồn đến một hoặc nhiều replica. Replica thường phục vụ truy vấn đọc, báo cáo hoặc dự phòng khi máy chủ chính gặp sự cố. Nếu ứng dụng hoặc người vận hành vô tình gửi lệnh ghi đến replica, dữ liệu có thể lệch khỏi nguồn và làm phức tạp quá trình đồng bộ hoặc failover.

MySQL cung cấp hai biến toàn cục **read_only** và **super_read_only** để hạn chế ghi từ client. Hiểu đúng khác biệt giữa chúng, ngoại lệ dành cho luồng replication và cách chuyển vai trò primary/replica là điều cần thiết để bảo vệ topology.

Bài học này thuộc module **DATABASE_MYSQL**, bổ sung cho các kỹ năng thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và mô hình

Sau bài học, bạn có thể:

- Giải thích tác dụng và khác biệt giữa read_only và super_read_only.
- Bật chế độ chỉ đọc trên replica mà vẫn cho phép replication applier cập nhật dữ liệu.
- Nhận diện tài khoản có thể vượt qua read_only và lý do nên bật super_read_only.
- Kiểm tra trạng thái máy chủ, trạng thái replication và quyền của tài khoản ứng dụng.
- Thiết kế quy trình chuyển replica thành primary mà không tạo ra hai máy chủ cùng nhận ghi.
- Điều tra lỗi ghi bị từ chối và các tình huống cấu hình chỉ đọc không như mong đợi.

Một topology phổ biến:

~~~text
                 Ứng dụng ghi
                      |
                      v
                +-----------+
                |  Primary  |
                | read_only |
                |    OFF    |
                +-----------+
                      |
                Binary log
                      |
             +--------+--------+
             |                 |
             v                 v
       +-----------+     +-----------+
       | Replica A |     | Replica B |
       | read_only |     | read_only |
       |   ON      |     |   ON      |
       | super RO  |     | super RO  |
       +-----------+     +-----------+
          đọc/báo cáo       đọc/dự phòng
~~~

Primary nhận ghi từ ứng dụng và tạo binary log. Replica nhận log, ghi relay log và để replication applier áp dụng thay đổi. Các biến chỉ đọc bảo vệ replica trước thao tác ghi từ client; chúng không có nhiệm vụ ngăn replication applier cập nhật dữ liệu.

Cần phân biệt ba luồng:

1. **Client nghiệp vụ:** ứng dụng, công cụ báo cáo hoặc người quản trị kết nối SQL và gửi lệnh.
2. **Replication receiver:** nhận binary log từ nguồn và ghi vào relay log.
3. **Replication applier:** đọc relay log rồi áp dụng thay đổi lên replica.

Mục tiêu là chặn luồng ghi ngoài ý muốn từ client trong khi vẫn duy trì luồng replication hợp lệ.

## 2. read_only hoạt động thế nào?

read_only là biến hệ thống toàn cục. Khi bật, MySQL hạn chế các thao tác thay đổi dữ liệu và cấu trúc trên máy chủ. Các cập nhật do replication applier thực hiện vẫn được phép.

Bật ở thời điểm chạy:

~~~sql
SET GLOBAL read_only = ON;
~~~

Kiểm tra:

~~~sql
SELECT @@GLOBAL.read_only;
~~~

Tuy nhiên, read_only=ON vẫn cho phép client có quyền SYSTEM_VARIABLES_ADMIN hoặc quyền SUPER (đã deprecated trong các phiên bản MySQL mới) thực hiện cập nhật. Đây là ngoại lệ dành cho các tài khoản quản trị có đặc quyền cao.

Vì vậy, read_only hữu ích để ngăn ứng dụng thông thường hoặc tài khoản không có quyền quản trị ghi nhầm lên replica. Nó không phải hàng rào đủ mạnh nếu trên máy chủ vẫn có tài khoản ứng dụng hoặc tài khoản vận hành mang đặc quyền vượt qua chế độ này.

Ví dụ, tài khoản báo cáo chỉ có SELECT sẽ bị từ chối khi cố chạy:

~~~sql
INSERT INTO shop.orders(order_id, status)
VALUES (9001, 'NEW');
~~~

MySQL thường trả lỗi dạng:

~~~text
ERROR 1290 (HY000): The MySQL server is running with the --read-only option so it cannot execute this statement
~~~

Thông báo cụ thể có thể thay đổi theo phiên bản và biến đang bật. Hãy kiểm tra cả trạng thái máy chủ và quyền hiệu lực của tài khoản trước khi kết luận lỗi do replication.

## 3. super_read_only bảo vệ mạnh hơn

super_read_only bổ sung một lớp bảo vệ: khi bật, MySQL cấm client thực hiện cập nhật ngay cả khi tài khoản có SYSTEM_VARIABLES_ADMIN hoặc SUPER. Các cập nhật do replication applier thực hiện vẫn được cho phép.

Bật chế độ này:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

Khi bật super_read_only, MySQL tự động bật read_only. Kiểm tra cả hai biến:

~~~sql
SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Kết quả kỳ vọng trên replica được bảo vệ:

| Biến | Giá trị |
|---|---|
| read_only | 1 |
| super_read_only | 1 |

Khác biệt chính:

| Hành vi | read_only=ON | super_read_only=ON |
|---|---|---|
| Client thông thường ghi dữ liệu | Bị chặn | Bị chặn |
| Client có SYSTEM_VARIABLES_ADMIN hoặc SUPER ghi dữ liệu | Có thể được phép | Bị chặn |
| Replication applier áp dụng thay đổi | Được phép | Được phép |
| Tự động bật read_only | Không | Có |
| Bảo vệ replica trước thao tác ghi nhầm của tài khoản quản trị | Chưa đủ | Mạnh hơn |

Khi super_read_only được tắt, read_only vẫn có thể tiếp tục ở trạng thái ON nếu trước đó đã bật. Ngược lại, đặt read_only=OFF sẽ đồng thời tắt super_read_only. Vì thế, khi thay đổi trạng thái, hãy đọc lại cả hai biến thay vì chỉ suy luận từ lệnh vừa chạy.

super_read_only vẫn có thể bị một quản trị viên có quyền thay đổi biến hệ thống tắt đi. Nó bảo vệ trước câu lệnh ghi nhầm từ client, kể cả client có đặc quyền ghi, nhưng không thay thế việc kiểm soát quyền quản trị, kiểm toán và quy trình thay đổi cấu hình.

## 4. Ngoại lệ dành cho replication và bảng tạm

### 4.1. Replication vẫn tiếp tục

Bật read_only hoặc super_read_only trên replica không có nghĩa là dừng replication.

Luồng thông thường vẫn hoạt động:

1. Receiver thread nhận sự kiện từ primary.
2. Sự kiện được ghi vào relay log.
3. Applier thread đọc relay log.
4. Applier áp dụng thay đổi lên các bảng trên replica.
5. Trạng thái thực thi được cập nhật để replica tiếp tục đồng bộ.

Đây là ngoại lệ có chủ đích. Nếu các biến chỉ đọc chặn cả replication applier, replica sẽ không thể theo kịp primary.

Có thể kiểm tra replication:

~~~sql
SHOW REPLICA STATUS\G
~~~

Trên phiên bản cũ, câu lệnh tương ứng có thể là SHOW SLAVE STATUS. Kiểm tra tối thiểu:

- Replica_IO_Running và Replica_SQL_Running có trạng thái mong đợi.
- Không có lỗi receiver hoặc applier chưa xử lý.
- Nguồn replication đúng máy chủ dự kiến.
- GTID đã nhận và đã thực thi tiến triển phù hợp.
- Độ trễ replication nằm trong ngưỡng vận hành.

Tên cột và trạng thái hiển thị phụ thuộc phiên bản và loại replication. Với multi-source replication, kiểm tra từng channel thay vì chỉ dựa trên một dòng trạng thái tổng quát.

### 4.2. Bảng TEMPORARY là ngoại lệ

Chế độ chỉ đọc không áp dụng theo cách thông thường cho bảng tạm TEMPORARY. Client có thể tạo, thay đổi và xóa bảng tạm trong phiên làm việc ngay cả khi máy chủ bật chế độ chỉ đọc.

Ví dụ:

~~~sql
CREATE TEMPORARY TABLE tmp_report (
  order_id BIGINT PRIMARY KEY,
  total_amount DECIMAL(12,2)
);

INSERT INTO tmp_report(order_id, total_amount)
VALUES (1001, 250000.00);

DROP TEMPORARY TABLE tmp_report;
~~~

Các thao tác này không ghi dữ liệu bền vững vào bảng nghiệp vụ trên replica. Do đó, việc một phiên SQL tạo được bảng tạm không chứng minh rằng read_only hoặc super_read_only đang tắt.

Nếu mục tiêu là ngăn dữ liệu nghiệp vụ bị thay đổi, hãy kiểm tra bảng đích thực tế và trạng thái biến. Nếu mục tiêu là cô lập hoàn toàn client khỏi máy chủ, cần kiểm soát thêm quyền kết nối, quyền truy vấn và lớp mạng; chế độ chỉ đọc không phải chế độ cấm mọi câu lệnh SQL.

## 5. Cấu hình replica an toàn

### 5.1. Cấu hình khi khởi động

Để replica luôn khởi động trong trạng thái chỉ đọc, có thể cấu hình trong tệp cấu hình MySQL:

~~~ini
[mysqld]
read_only=ON
super_read_only=ON
~~~

super_read_only=ON tự bật read_only, nhưng khai báo rõ cả hai biến giúp người vận hành dễ nhận diện ý định cấu hình.

Với thay đổi runtime, dùng:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

Thay đổi bằng SET GLOBAL có hiệu lực trong lần chạy hiện tại. Nếu không cấu hình tại startup hoặc dùng cơ chế lưu cấu hình phù hợp, trạng thái có thể trở lại giá trị khác sau khi máy chủ khởi động lại.

Một số môi trường dùng cấu hình được quản lý tập trung, dịch vụ cơ sở dữ liệu managed hoặc Group Replication có thể tự điều khiển biến này. Hãy dùng cơ chế cấu hình và failover do nền tảng cung cấp; tránh ghi đè thủ công lên trạng thái do hệ thống tự động quản lý.

### 5.2. Kiểm tra sau khi cấu hình

Sau khi bật, kiểm tra:

~~~sql
SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;

SHOW REPLICA STATUS\G
~~~

Đồng thời xác minh:

- Máy chủ có đúng vai trò replica trong topology.
- Replica đang nhận và áp dụng log từ nguồn mong muốn.
- Ứng dụng báo cáo chỉ kết nối tới endpoint đọc.
- Tài khoản ứng dụng không mang quyền quản trị vượt qua read_only.
- Không có job, cron, migration hoặc công cụ quản trị đang gửi ghi vào replica.
- Cảnh báo và giám sát có thể phát hiện khi biến bị thay đổi ngoài quy trình.

### 5.3. Kiểm soát quyền tài khoản

super_read_only là lớp bảo vệ cấp máy chủ. Quyền SQL vẫn cần được thiết kế theo nguyên tắc tối thiểu.

Ví dụ, tài khoản báo cáo chỉ cần SELECT trên schema đọc:

~~~sql
CREATE USER 'report_reader'@'10.%'
IDENTIFIED BY 'use-a-secret-manager';

GRANT SELECT ON shop.* TO 'report_reader'@'10.%';
SHOW GRANTS FOR 'report_reader'@'10.%';
~~~

Chuỗi mật khẩu trong ví dụ chỉ là chỗ giữ chỗ minh họa. Khi triển khai, tạo và phân phối bí mật bằng hệ thống quản lý bí mật của tổ chức; không ghi mật khẩu thật vào script, Git hoặc tài liệu dùng chung.

Tránh cấp cho tài khoản ứng dụng các quyền quản trị như SYSTEM_VARIABLES_ADMIN hoặc SUPER nếu nghiệp vụ không cần. Không dùng chung một tài khoản giữa ứng dụng, báo cáo và quản trị vận hành. Việc phân quyền theo vai trò giúp giảm số đường có thể vô tình tắt chế độ bảo vệ.

## 6. Quy trình bật chỉ đọc trên replica

Một quy trình vận hành nên gồm các bước sau:

1. **Xác nhận vai trò:** kiểm tra hostname, server UUID, server_id, nguồn replication và channel.
2. **Kiểm tra sức khỏe replication:** xác nhận receiver/applier đang chạy, không có lỗi và GTID tiến triển bình thường.
3. **Kiểm tra workload:** xác định ứng dụng, báo cáo, migration và job nền đang kết nối đến máy chủ.
4. **Bật bảo vệ:** đặt super_read_only=ON; biến read_only sẽ được bật theo.
5. **Xác minh:** đọc lại cả hai biến và kiểm tra replication vẫn áp dụng sự kiện.
6. **Kiểm tra định tuyến:** xác nhận endpoint ghi trỏ về primary; endpoint đọc mới trỏ đến replica.
7. **Theo dõi:** giám sát lỗi ghi bị từ chối, độ trễ replication và thay đổi cấu hình.

Nếu một replica cần được bảo trì, có thể bật chỉ đọc trước khi bắt đầu thao tác để giảm nguy cơ client gửi ghi nhầm. Tuy nhiên, hãy kiểm tra các công cụ backup, kiểm tra dữ liệu hoặc migration có yêu cầu ghi hay không; chúng có thể cần được chuyển sang môi trường phù hợp.

## 7. Chuyển replica thành primary khi failover

Khi failover, một replica có thể được thăng cấp thành primary. Đây là thời điểm đặc biệt nhạy cảm vì thay đổi super_read_only cho phép máy chủ nhận ghi từ ứng dụng.

Một quy trình chuyển vai trò an toàn cần bảo đảm chỉ có một primary được phép nhận ghi.

### 7.1. Trước khi mở quyền ghi

- Xác định primary cũ đã dừng ghi hoặc đã được fence khỏi ứng dụng.
- Xác nhận replica được chọn có dữ liệu đủ mới theo mục tiêu RPO.
- Kiểm tra GTID đã nhận và đã thực thi; xác định các giao dịch còn thiếu nếu có.
- Xác nhận topology mới và các replica còn lại sẽ theo primary nào.
- Đảm bảo router, proxy hoặc cấu hình ứng dụng sẽ gửi ghi đến đúng máy chủ.
- Ghi lại trạng thái trước failover để có thể điều tra nếu phát sinh sai lệch.

**Fencing** là hành động ngăn primary cũ tiếp tục nhận ghi, chẳng hạn dừng dịch vụ, chặn kết nối ghi ở tầng mạng hoặc dùng cơ chế điều phối có bảo đảm. Chỉ đổi DNS hoặc chuyển proxy chưa chắc đã ngăn mọi client cũ kết nối trực tiếp đến primary trước đó.

### 7.2. Thăng cấp máy chủ được chọn

Chỉ sau khi xác nhận máy chủ được chọn là writer duy nhất và primary cũ đã được fence, quản trị viên mới tắt chế độ chỉ đọc:

~~~sql
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;

SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Kết quả kỳ vọng trên primary mới:

| Biến | Giá trị |
|---|---|
| read_only | 0 |
| super_read_only | 0 |

Sau đó, hoàn tất cấu hình replication cho topology mới theo kế hoạch GTID hoặc file/position. Kiểm tra ứng dụng chỉ ghi vào primary mới và các replica còn lại nhận log từ đúng nguồn.

Thứ tự thao tác cụ thể phụ thuộc công cụ failover, phiên bản MySQL và mô hình GTID. Nếu dùng Orchestrator, Group Replication, InnoDB Cluster hoặc dịch vụ managed, hãy tuân theo quy trình promotion chính thức của nền tảng. Không tự ý tắt super_read_only trong khi bộ điều phối còn xem máy chủ là replica.

### 7.3. Hạ cấp primary cũ thành replica

Khi primary cũ được đưa trở lại topology, cần bảo đảm nó không tiếp tục nhận ghi từ ứng dụng:

- Fence hoặc ngắt endpoint ghi cũ.
- Kiểm tra dữ liệu của primary cũ có phân kỳ hay chứa giao dịch ngoài luồng không.
- Đồng bộ lại theo quy trình được chọn; có thể cần dựng lại replica từ primary mới nếu không thể chứng minh hai bên nhất quán.
- Cấu hình nguồn replication mới và kiểm tra GTID.
- Bật super_read_only=ON.
- Chỉ đưa máy chủ vào pool đọc sau khi replication và trạng thái chỉ đọc được xác minh.

Không chỉ bật super_read_only rồi mặc định dữ liệu cũ đã đồng bộ. Biến này chặn client ghi; nó không tự giải quyết xung đột dữ liệu hoặc giao dịch đã phát sinh trong thời gian split-brain.

## 8. Giám sát và cảnh báo

Nên theo dõi cả trạng thái biến lẫn hành vi thực tế:

| Chỉ số hoặc tín hiệu | Ý nghĩa | Hành động khi bất thường |
|---|---|---|
| @@GLOBAL.read_only | Trạng thái hạn chế ghi cơ bản | Kiểm tra vai trò máy chủ và thay đổi cấu hình |
| @@GLOBAL.super_read_only | Trạng thái bảo vệ ghi mạnh hơn | Cảnh báo nếu replica dự kiến lại có giá trị OFF |
| Replica IO/applier status | Kết nối và áp dụng replication | Điều tra lỗi channel, relay log hoặc nguồn |
| GTID received/executed | Tiến độ nhận và áp dụng giao dịch | Xác định khoảng thiếu hoặc độ trễ |
| Replication lag | Độ trễ so với primary | Kiểm tra tải, mạng, transaction dài và applier |
| Lỗi ghi từ client | Ứng dụng đang gửi ghi đến replica | Sửa routing hoặc cấu hình connection pool |
| Thay đổi biến hệ thống | Có người hoặc automation đổi trạng thái | Đối chiếu audit log và sự kiện failover |

Ví dụ kiểm tra nhanh:

~~~sql
SELECT
  @@hostname AS host_name,
  @@server_id AS server_id,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Kết quả này giúp ghép trạng thái biến với danh tính máy chủ. Trong hệ thống nhiều replica, hãy thu thập định kỳ từ từng máy và đối chiếu với vai trò được lưu trong hệ thống điều phối.

Một cảnh báo hữu ích là: nếu máy chủ đang được đăng ký với vai trò replica nhưng super_read_only=OFF, phát cảnh báo ngay. Cũng nên cảnh báo khi một replica ngừng nhận hoặc áp dụng log, vì trạng thái chỉ đọc không bảo đảm dữ liệu của nó còn mới.

## 9. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng ghi vào replica nhận lỗi 1290 | read_only hoặc super_read_only đang bật | Kiểm tra endpoint kết nối, hostname và hai biến toàn cục |
| Tài khoản quản trị vẫn ghi được khi read_only=ON | Tài khoản có SYSTEM_VARIABLES_ADMIN hoặc SUPER | Kiểm tra SHOW GRANTS; bật super_read_only nếu máy chủ phải khóa ghi từ client |
| Tài khoản quản trị bị từ chối ghi khi super_read_only=ON | Đây là hành vi dự kiến của chế độ bảo vệ mạnh | Thực hiện thay đổi trên primary hoặc theo quy trình bảo trì đã duyệt |
| Replica không cập nhật dữ liệu dù biến chỉ đọc đang bật | Replication receiver/applier có thể gặp lỗi độc lập | Kiểm tra SHOW REPLICA STATUS, lỗi channel và relay log |
| Replica vẫn tạo được bảng TEMPORARY | Bảng tạm là ngoại lệ của chế độ chỉ đọc | Xác minh không nhầm bảng tạm với bảng nghiệp vụ bền vững |
| Replica trở thành writer ngoài ý muốn sau restart | Trạng thái runtime không được lưu trong cấu hình startup hoặc automation đổi biến | Kiểm tra file cấu hình, persisted variables và công cụ điều phối |
| Sau failover có hai máy chủ nhận ghi | Primary cũ chưa được fence hoặc routing chưa nhất quán | Dừng ghi, cô lập một phía, đối soát GTID và phục hồi topology |
| Không thể tắt chế độ chỉ đọc khi promotion | Thiếu quyền quản trị biến hoặc automation đang quản lý trạng thái | Kiểm tra quyền SYSTEM_VARIABLES_ADMIN, nhật ký và cơ chế failover |

Khi ứng dụng báo lỗi ghi, đừng lập tức tắt super_read_only. Trước hết, xác nhận máy chủ mà ứng dụng đang kết nối, vai trò mong muốn và trạng thái replication. Nếu đây là replica, sửa connection string hoặc routing của ứng dụng về primary. Chỉ thay đổi vai trò máy chủ trong một quy trình failover hoặc bảo trì có kiểm soát.

## 10. Tự kiểm tra

**Tình huống 1:** Replica bật read_only=ON. Một tài khoản có quyền SYSTEM_VARIABLES_ADMIN vẫn thực hiện được lệnh cập nhật. Vì sao?

**Gợi ý:** read_only có ngoại lệ cho tài khoản mang quyền quản trị biến hệ thống hoặc SUPER. Dùng super_read_only=ON để chặn cả cập nhật từ các client có đặc quyền đó.

**Tình huống 2:** Replica bật super_read_only=ON, nhưng dữ liệu vẫn tăng theo thay đổi từ primary. Có phải cấu hình chỉ đọc đã thất bại?

**Gợi ý:** Không. Replication applier được phép áp dụng sự kiện từ relay log. Chế độ chỉ đọc chủ yếu chặn cập nhật do client khởi tạo.

**Tình huống 3:** Một client tạo và ghi được vào bảng TEMPORARY trên replica. Điều đó có chứng minh replica đang nhận ghi vào bảng nghiệp vụ không?

**Gợi ý:** Không. Bảng TEMPORARY là ngoại lệ; cần kiểm tra loại bảng và trạng thái hai biến toàn cục.

**Tình huống 4:** Khi failover, replica được chọn đã bắt kịp primary nhưng primary cũ vẫn có thể truy cập từ một số máy ứng dụng. Có nên tắt super_read_only trên replica mới ngay không?

**Gợi ý:** Chưa. Phải fence primary cũ và bảo đảm chỉ một writer tồn tại trước khi mở quyền ghi trên primary mới. Chỉ đổi proxy hoặc DNS có thể chưa đủ nếu client vẫn kết nối trực tiếp.

**Tình huống 5:** Sau khi tắt super_read_only, read_only vẫn là ON. Đây có phải trạng thái không hợp lệ không?

**Gợi ý:** Không. Tắt super_read_only không tự động tắt read_only. Nếu máy chủ đã được promotion và phải nhận ghi, kiểm tra rồi tắt cả read_only theo quy trình.

## 11. Điểm cần ghi nhớ

- read_only=ON chặn phần lớn thao tác ghi từ client nhưng có ngoại lệ cho tài khoản mang quyền SYSTEM_VARIABLES_ADMIN hoặc SUPER.
- super_read_only=ON chặn ghi từ client kể cả tài khoản có đặc quyền quản trị; nó tự bật read_only.
- Replication receiver và applier vẫn hoạt động; replica tiếp tục nhận và áp dụng thay đổi từ primary.
- Bảng TEMPORARY là ngoại lệ, vì vậy tạo bảng tạm thành công không chứng minh chế độ chỉ đọc đã tắt.
- Kiểm tra cả read_only, super_read_only, hostname, server_id, trạng thái replication và quyền của tài khoản.
- Khi promotion, fence primary cũ trước khi mở ghi trên primary mới để tránh split-brain.
- Khi đưa primary cũ trở lại làm replica, xác minh dữ liệu và GTID trước khi đưa vào pool đọc.
- Chế độ chỉ đọc là một lớp bảo vệ; phân quyền tối thiểu, giám sát và quy trình failover vẫn cần thiết.
