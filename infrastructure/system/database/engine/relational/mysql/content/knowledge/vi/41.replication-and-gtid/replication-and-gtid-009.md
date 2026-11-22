# Row-based replication, statement không xác định và khác biệt dữ liệu

MySQL replication có thể truyền thay đổi dưới dạng câu lệnh SQL hoặc dưới dạng các thay đổi hàng dữ liệu. Row-based replication (RBR) ghi lại những hàng thực tế đã được thêm, sửa hoặc xóa trên nguồn, nhờ đó replica áp dụng đúng kết quả mà nguồn đã tạo ra. Cách này đặc biệt hữu ích khi câu lệnh SQL có kết quả không xác định, phụ thuộc môi trường hoặc có thể cho kết quả khác nhau giữa hai máy chủ.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào vận hành replication và GTID: hiểu **binlog_format**, nhận diện statement không an toàn, lựa chọn row image, kiểm tra khác biệt dữ liệu và xử lý lỗi khi replica áp dụng row event. Các ví dụ dùng MySQL 8.0; cú pháp và tên trạng thái có thể khác ở các bản cũ hoặc MySQL 8.4.

## 1. Ba định dạng binary log

MySQL hỗ trợ ba giá trị cho biến **binlog_format**:

| Định dạng | Nội dung ghi vào binary log | Đặc điểm |
|---|---|---|
| **STATEMENT** | Câu lệnh SQL đã thực thi | Ít dữ liệu hơn trong một số workload, nhưng cần câu lệnh cho kết quả nhất quán trên nguồn và replica |
| **ROW** | Các row event mô tả hàng được thay đổi | Ghi lại kết quả thực tế, phù hợp với phần lớn workload và tránh nhiều vấn đề do SQL không xác định |
| **MIXED** | Kết hợp statement event và row event | MySQL tự chọn row format cho các câu lệnh được nhận diện là không an toàn với statement format |

Trong MySQL 8.0, mặc định của **binlog_format** là **ROW**. Đây thường là lựa chọn phù hợp cho hệ thống mới vì replica nhận các thay đổi dữ liệu đã xảy ra trên nguồn. Tuy nhiên, RBR có thể tạo binary log lớn hơn đối với những câu lệnh cập nhật rất nhiều hàng hoặc thay đổi các cột có kích thước lớn.

Kiểm tra định dạng hiện tại:

~~~sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
~~~

### Statement-based replication

Với statement format, binary log lưu câu lệnh SQL. Replica thực thi lại câu lệnh đó trên dữ liệu của mình. Ví dụ:

~~~sql
UPDATE account
SET balance = balance - 100
WHERE account_id = 42;
~~~

Nguồn ghi câu lệnh vào binary log; replica thực thi câu lệnh tương ứng. Cách này gọn khi một câu lệnh thay đổi rất nhiều hàng và cùng một câu lệnh chắc chắn tạo ra cùng kết quả ở mọi máy chủ.

Rủi ro xuất hiện khi kết quả phụ thuộc vào thời gian, dữ liệu cục bộ, thứ tự hàng không được bảo đảm, trạng thái phiên hoặc hàm không xác định. Nếu nguồn và replica đánh giá câu lệnh khác nhau, dữ liệu có thể lệch mà không phải lúc nào replication cũng báo lỗi.

### Row-based replication

Với row format, MySQL ghi các row event. Ví dụ câu lệnh trên có thể tạo một event mô tả hàng **account_id = 42** với giá trị balance trước và sau thay đổi. Replica áp dụng thay đổi hàng đã ghi, không cần tính lại biểu thức **balance - 100**.

Điều này giảm phụ thuộc vào cách biểu thức SQL được đánh giá tại replica. Đổi lại, binary log có thể chứa nhiều dữ liệu hơn, đặc biệt khi câu lệnh sửa một số lượng lớn hàng.

### Mixed replication

Với mixed format, MySQL dùng statement event cho câu lệnh được coi là an toàn và chuyển sang row event khi phát hiện câu lệnh không an toàn cho statement-based replication. Việc phân loại do máy chủ thực hiện; không nên giả định mọi trường hợp không xác định đều được phát hiện đầy đủ.

Nếu hệ thống cần hành vi dễ dự đoán, có nhiều CDC consumer hoặc phải điều tra thay đổi ở cấp hàng, **ROW** thường là lựa chọn rõ ràng hơn.

## 2. Vì sao một số statement không an toàn?

Một câu lệnh SQL có thể hợp lệ và cho kết quả đúng trên nguồn nhưng không tái tạo chính xác kết quả khi chạy lại ở replica. Những câu lệnh như vậy được gọi là unsafe đối với statement-based replication.

### Hàm không xác định hoặc phụ thuộc môi trường

Một số hàm trả kết quả khác nhau theo lần gọi, máy chủ hoặc ngữ cảnh:

- **UUID()** tạo giá trị định danh mới ở mỗi lần gọi.
- **UUID_SHORT()** phụ thuộc trạng thái và định danh máy chủ.
- **RAND()** tạo giá trị ngẫu nhiên; việc đồng bộ phụ thuộc cách seed và ngữ cảnh thực thi.
- Các hàm UDF hoặc stored function có thể phụ thuộc dữ liệu bên ngoài, trạng thái tiến trình hoặc hành vi không được MySQL kiểm soát.
- Hàm đọc file hoặc trạng thái máy chủ có thể cho kết quả khác nhau nếu môi trường nguồn và replica khác nhau.

Không phải mọi hàm có vẻ biến thiên đều luôn unsafe. Ví dụ, MySQL có cơ chế ghi nhận giá trị thời gian của một số hàm như **NOW()** trong statement event để replica sử dụng cùng thời điểm. Hãy dựa vào cảnh báo và tài liệu của phiên bản, không phân loại chỉ theo cảm giác.

### Dựa vào thứ tự hàng không được bảo đảm

**LIMIT** mà không có **ORDER BY** không xác định hàng nào sẽ được chọn. Hai máy chủ có thể có thứ tự truy xuất khác nhau do index, thống kê hoặc kế hoạch thực thi.

~~~sql
-- Không xác định rõ hàng nào sẽ bị cập nhật
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
LIMIT 10;
~~~

Nếu cần chọn đúng một nhóm hàng, hãy tạo thứ tự ổn định dựa trên khóa duy nhất:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
ORDER BY job_id
LIMIT 10;
~~~

Thêm **ORDER BY** giúp xác định thứ tự lựa chọn, nhưng vẫn cần kiểm tra tính duy nhất của khóa sắp xếp và điều kiện dữ liệu ở hai máy chủ.

### Statement phụ thuộc dữ liệu hoặc cấu hình cục bộ

Các câu lệnh có thể cho kết quả khác khi:

- Nguồn và replica có dữ liệu ban đầu khác nhau.
- SQL mode, character set, collation hoặc múi giờ phiên khác nhau.
- Trình tự thực thi hoặc trạng thái transaction khác nhau.
- Câu lệnh tham chiếu đối tượng bên ngoài, file hoặc hàm do người dùng tự định nghĩa.
- Trigger hoặc stored program ở hai máy chủ không giống nhau.

Một câu lệnh unsafe không nhất thiết làm replication dừng. Với statement format, MySQL có thể phát cảnh báo khi nhận diện được rủi ro nhưng vẫn ghi câu lệnh. Nếu câu lệnh được thực thi ở hai nơi và tạo kết quả khác nhau, replica có thể lệch dữ liệu.

## 3. Bật row-based replication và kiểm tra session

Kiểm tra cấu hình toàn cục và cấu hình của phiên hiện tại:

~~~sql
SELECT
  @@GLOBAL.binlog_format AS global_format,
  @@SESSION.binlog_format AS session_format,
  @@GLOBAL.binlog_row_image AS global_row_image,
  @@SESSION.binlog_row_image AS session_row_image;
~~~

Để đặt mặc định cho các kết nối mới và lưu qua lần khởi động:

~~~sql
SET PERSIST binlog_format = 'ROW';
SET PERSIST binlog_row_image = 'FULL';
~~~

Hoặc khai báo trong cấu hình máy chủ:

~~~ini
[mysqld]
binlog_format=ROW
binlog_row_image=FULL
~~~

**binlog_format** có phạm vi global và session. Thay đổi global tác động đến giá trị mặc định của các session mới; các kết nối ứng dụng đã tồn tại có thể tiếp tục dùng giá trị session cũ. Khi thay đổi cấu hình, cần kiểm tra session của ứng dụng và có kế hoạch tái kết nối phù hợp. Không thay đổi giữa chừng một cách tùy tiện trong khi transaction hoặc stored program đang hoạt động.

Một session có thể đặt riêng định dạng nếu người dùng có quyền và phiên bản cho phép:

~~~sql
SET SESSION binlog_format = 'ROW';
~~~

Thiết lập ở cấp session chỉ ảnh hưởng các thay đổi được ghi từ session đó. Nó không thay thế cấu hình toàn máy chủ khi mục tiêu là thống nhất hành vi replication.

## 4. Row event chứa những gì?

Khi sử dụng RBR, binary log có các loại event chính:

- **TABLE_MAP_EVENT** mô tả bảng liên quan và metadata cột cần thiết để diễn giải row event.
- **WRITE_ROWS_EVENT** mô tả hàng được thêm.
- **UPDATE_ROWS_EVENT** chứa hình ảnh trước và sau thay đổi của hàng.
- **DELETE_ROWS_EVENT** chứa hình ảnh hàng trước khi xóa.

Một lệnh **UPDATE** có thể tạo nhiều row event nếu cập nhật nhiều hàng hoặc dữ liệu được chia thành nhiều event. Với row-based logging, câu SQL gốc không phải nội dung chính dùng để tái thực thi thay đổi.

Đọc binary log dạng row:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000123
~~~

Đầu ra giải mã thường hiển thị các chú thích **###** mô tả thao tác trên hàng. Đây là cách hữu ích để điều tra thay đổi, nhưng không phải lúc nào cũng hiển thị đầy đủ câu lệnh SQL ban đầu. Có thể bật **binlog_rows_query_log_events** để ghi thêm query event phục vụ truy vết trong những phiên bản hỗ trợ; query event này chỉ mang tính thông tin, không thay thế row event.

## 5. Chọn binlog_row_image: FULL, MINIMAL và NOBLOB

**binlog_row_image** quyết định MySQL ghi bao nhiêu cột trong hình ảnh hàng của row event. Lựa chọn này ảnh hưởng kích thước binary log, khả năng phân tích sự kiện và tương thích với công cụ downstream.

| Giá trị | Nội dung row image | Đặc điểm |
|---|---|---|
| **FULL** | Ghi tất cả cột trong before image và after image theo loại event | Dễ kiểm tra, tương thích rộng, có thể tạo log lớn |
| **MINIMAL** | Chỉ ghi cột cần để nhận diện hàng và các cột thay đổi | Giảm dung lượng, nhưng công cụ đọc log cần hiểu row image tối giản |
| **NOBLOB** | Ghi đầy đủ các cột, trừ cột BLOB/TEXT không thay đổi | Giảm log khi bảng có cột lớn ít thay đổi |

Ví dụ:

~~~sql
SET PERSIST binlog_row_image = 'FULL';
~~~

### FULL

Với **UPDATE**, before image và after image chứa đầy đủ các cột. Với **DELETE**, before image chứa toàn bộ hàng; với **INSERT**, after image chứa toàn bộ hàng. Điều này giúp công cụ kiểm toán hoặc CDC có thêm ngữ cảnh, nhưng có thể làm tăng đáng kể dung lượng nếu bảng có nhiều cột lớn.

### MINIMAL

Với **UPDATE**, before image chứa các cột cần thiết để nhận diện hàng; after image chỉ chứa cột được thay đổi. Với **DELETE**, before image chứa các cột cần để xác định hàng. Với **INSERT**, after image biểu diễn dữ liệu hàng được thêm theo quy tắc row event.

Nếu bảng có primary key hoặc unique key phù hợp, MySQL có thể dùng khóa đó để nhận diện hàng. Nếu không có khóa duy nhất phù hợp, có thể phải ghi nhiều hoặc toàn bộ cột trong before image để xác định hàng. Vì vậy, thêm primary key tốt cho mô hình dữ liệu cũng giúp row-based replication định vị hàng hiệu quả hơn.

### NOBLOB

**NOBLOB** ghi các cột như **FULL**, ngoại trừ cột BLOB/TEXT không thay đổi. Nếu một cột BLOB/TEXT được cập nhật, giá trị của nó vẫn cần được ghi. Cách này hữu ích khi bảng có cột nội dung lớn nhưng phần lớn câu lệnh không sửa các cột đó.

### Chọn theo nhu cầu

- Dùng **FULL** khi ưu tiên tương thích, khả năng điều tra và công cụ CDC cần before/after image đầy đủ.
- Cân nhắc **MINIMAL** khi log quá lớn và toàn bộ consumer downstream đã được xác nhận hỗ trợ.
- Cân nhắc **NOBLOB** nếu bảng có cột BLOB/TEXT lớn, thường không thay đổi.

Không đổi **binlog_row_image** chỉ để tiết kiệm đĩa mà chưa kiểm tra các consumer như CDC, audit, công cụ đồng bộ dữ liệu hoặc hệ thống phân tích. Một số consumer cần các cột đầy đủ để dựng lại bản ghi hoặc kiểm toán thay đổi.

## 6. RBR xử lý trigger, stored program và DDL thế nào?

Với row-based replication, trigger được kích hoạt trên nguồn khi câu lệnh thay đổi dữ liệu chạy. Những thay đổi do trigger tạo ra cũng được ghi thành row event và chuyển đến replica. Replica áp dụng row event mà không kích hoạt lại trigger cho các row event đó. Điều này tránh việc trigger chạy hai lần cho cùng một thay đổi.

Stored procedure và function được gọi trên nguồn; các thay đổi dữ liệu do chúng thực hiện được ghi lại theo định dạng binary log đang dùng. Không cần chạy lại procedure trên replica để tái tạo các thay đổi hàng đã ghi.

DDL như **CREATE TABLE**, **ALTER TABLE**, **DROP TABLE**, **CREATE VIEW** vẫn được ghi và áp dụng dưới dạng statement event, kể cả khi **binlog_format=ROW**. Vì vậy, RBR không loại bỏ yêu cầu giữ schema nguồn và replica tương thích. Nếu DDL được thực hiện khác nhau ở hai phía hoặc có thay đổi thủ công trên replica, row event sau đó có thể không áp dụng được.

Đây là một điểm cần nhớ khi vận hành: row format bảo vệ tính nhất quán của thay đổi dữ liệu, còn cấu trúc đối tượng và các thao tác DDL vẫn cần được quản lý có kỷ luật.

## 7. Vì sao dữ liệu nguồn và replica có thể khác nhau?

RBR làm giảm rủi ro do câu lệnh không xác định, nhưng không bảo đảm hai máy chủ luôn giống nhau trong mọi hoàn cảnh. Một số nguyên nhân phổ biến:

1. Dữ liệu trên replica đã bị sửa thủ công hoặc ứng dụng ghi trực tiếp.
2. Replica bị bỏ qua transaction hoặc được khởi tạo từ backup sai thời điểm.
3. DDL chạy thủ công khiến cấu trúc bảng khác nguồn.
4. Replication filter loại bỏ một phần database hoặc bảng.
5. Lỗi phần cứng, lỗi lưu trữ hoặc sự cố khiến transaction không được áp dụng đúng.
6. Người vận hành bỏ qua lỗi replication hoặc khởi động lại luồng sau khi sửa dữ liệu không đầy đủ.
7. Khác biệt cấu hình hoặc plugin ảnh hưởng cách tạo và áp dụng đối tượng.

### Dấu hiệu khác biệt dữ liệu

- Replica báo lỗi duplicate key khi áp dụng một row insert.
- Replica không tìm thấy hàng cần cập nhật hoặc xóa.
- Số lượng bản ghi hoặc checksum giữa nguồn và replica khác nhau.
- Truy vấn ứng dụng trả kết quả khác nhau khi chạy trên hai máy chủ.
- Một số bảng không theo kịp dù luồng replication vẫn báo đang chạy.

Hai lỗi thường gặp khi áp dụng row event:

- **1032 (HA_ERR_KEY_NOT_FOUND):** replica không tìm thấy hàng cần cập nhật hoặc xóa.
- **1062 (ER_DUP_ENTRY):** replica thêm một hàng nhưng vi phạm khóa duy nhất do hàng đó đã tồn tại.

Những lỗi này thường cho thấy dữ liệu nền giữa nguồn và replica đã khác nhau, hoặc có thay đổi ngoài luồng replication. Không nên chỉ bỏ qua transaction lỗi để làm cho luồng chạy tiếp; làm vậy có thể tạo thêm khác biệt về sau.

## 8. Chẩn đoán lỗi row-based replication

### Kiểm tra trạng thái replica

Trên MySQL 8.0.22 trở lên:

~~~sql
SHOW REPLICA STATUS\G
~~~

Trên các bản cũ hơn, có thể cần dùng:

~~~sql
SHOW SLAVE STATUS\G
~~~

Tập trung vào:

- **Replica_IO_Running** và **Replica_SQL_Running**.
- **Last_IO_Errno**, **Last_IO_Error**, **Last_SQL_Errno**, **Last_SQL_Error**.
- **Source_Log_File**, **Read_Source_Log_Pos**.
- **Relay_Source_Log_File**, **Exec_Source_Log_Pos**.
- **Retrieved_Gtid_Set** và **Executed_Gtid_Set** khi dùng GTID.

Nếu có nhiều worker áp dụng song song, kiểm tra thêm trạng thái worker:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_worker;
~~~

Trên nguồn, kiểm tra binary log tương ứng:

~~~sql
SHOW BINARY LOGS;
SHOW MASTER STATUS;
~~~

Trong MySQL 8.4, dùng **SHOW BINARY LOG STATUS** thay cho **SHOW MASTER STATUS**.

### Đọc row event quanh vị trí lỗi

Khi đã xác định file và position từ thông báo lỗi, dùng **mysqlbinlog** để xem event:

~~~bash
mysqlbinlog --base64-output=DECODE-ROWS -vv --start-position=12000 --stop-position=16000 mysql-bin.000123
~~~

Đối chiếu bảng, primary key, before image và after image với dữ liệu hiện tại trên nguồn và replica. Nếu cần truy vấn trực tiếp, dùng đúng khóa chính hoặc unique key để kiểm tra hàng liên quan. Ghi lại transaction/GTID gây lỗi trước khi sửa.

### Kiểm tra cấu trúc bảng

~~~sql
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;
~~~

So sánh định nghĩa bảng ở hai máy chủ: thứ tự cột, kiểu dữ liệu, độ dài, signed/unsigned, charset, collation, generated column, index và khóa. DDL khác biệt có thể khiến row event không thể ánh xạ đúng hoặc tạo ra kết quả sai.

## 9. Khắc phục data drift an toàn

Khi phát hiện nguồn và replica đã khác nhau, xử lý theo trình tự:

1. Ghi nhận lỗi, file/position hoặc GTID, bảng và khóa của hàng liên quan.
2. Xác định replica có còn phục vụ đọc ứng dụng hay không; nếu có nguy cơ trả dữ liệu sai, chuyển hướng đọc hoặc cô lập theo quy trình.
3. So sánh dữ liệu và cấu trúc giữa nguồn và replica.
4. Xác định nguyên nhân: ghi trực tiếp, lọc replication, backup sai thời điểm, DDL lệch hay transaction bị bỏ qua.
5. Chọn phương án sửa hàng cụ thể hoặc dựng lại replica từ backup nhất quán.
6. Xác minh dữ liệu sau sửa và khởi động lại replication từ điểm đúng.
7. Theo dõi đến khi replica bắt kịp và kiểm tra lại tính nhất quán.

Nếu chỉ sai một vài hàng, DBA có thể sửa có kiểm soát sau khi hiểu chính xác trạng thái mong muốn và tác động đến khóa ngoại, trigger, transaction. Với drift diện rộng hoặc không thể xác định đầy đủ phạm vi, dựng lại replica từ một backup mới thường đáng tin cậy hơn.

Không dùng thao tác bỏ qua lỗi như **sql_slave_skip_counter** hoặc tăng GTID executed set một cách tùy tiện. Với GTID, bỏ qua transaction bằng cách đánh dấu đã thực thi có thể khiến dữ liệu không nhận thay đổi tương ứng. Mọi quyết định skip phải có phân tích transaction, ghi nhận phê duyệt và kế hoạch bù dữ liệu.

## 10. Giám sát tính nhất quán định kỳ

Replication status cho biết luồng truyền và áp dụng, nhưng không chứng minh mọi hàng dữ liệu đều giống nhau. Cần bổ sung kiểm tra tính nhất quán:

- So sánh số lượng hàng ở các bảng quan trọng.
- Tính checksum theo bảng hoặc theo khoảng khóa để khoanh vùng chênh lệch.
- Dùng công cụ kiểm tra consistency phù hợp với quy mô, tải và phiên bản.
- Theo dõi các thay đổi ghi trực tiếp vào replica.
- Rà soát replication filters và các DDL triển khai ngoài quy trình.
- Lưu kết quả kiểm tra để nhận diện drift kéo dài.

Với hệ thống lớn, tránh chạy phép so sánh toàn bảng vào giờ cao điểm mà không đánh giá tải. Có thể chia theo primary key, chạy theo lịch và giới hạn tài nguyên. Một phép kiểm tra phải so sánh cùng phạm vi và thời điểm hợp lý; nếu nguồn đang thay đổi trong khi replica còn lag, kết quả khác nhau chưa chắc là drift.

### Một số nguyên tắc vận hành

- Không cho ứng dụng ghi trực tiếp vào replica nếu kiến trúc không chủ đích hỗ trợ multi-source hoặc multi-primary.
- Không thay đổi schema thủ công trên replica.
- Quản lý DDL qua cùng quy trình triển khai và kiểm tra trên các node.
- Bảo đảm replica có đủ dung lượng relay log và binary log cần thiết.
- Theo dõi lỗi worker và lag thay vì chỉ nhìn một chỉ số độ trễ.
- Thử khôi phục replica từ backup và kiểm tra lại luồng replication định kỳ.

## 11. Ví dụ thực hành: unsafe statement và row event

Giả sử bảng hàng đợi có nhiều bản ghi ở trạng thái **pending**:

~~~sql
CREATE TABLE job_queue (
  job_id BIGINT PRIMARY KEY,
  status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL
) ENGINE=InnoDB;
~~~

Một câu lệnh cập nhật 10 hàng mà không sắp xếp rõ ràng có thể chọn nhóm hàng khác nhau nếu chạy lại trên hai máy chủ:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
LIMIT 10;
~~~

Trong môi trường dùng statement format, câu lệnh có thể bị đánh dấu unsafe vì thứ tự hàng được chọn không xác định. Với mixed format, MySQL có thể ghi row event thay cho statement event khi nhận diện trường hợp này. Với row format, replica nhận chính xác các hàng nguồn đã cập nhật.

Có thể viết lại câu lệnh để lựa chọn ổn định hơn:

~~~sql
UPDATE job_queue
SET status = 'expired'
WHERE status = 'pending'
ORDER BY job_id
LIMIT 10;
~~~

Khóa **job_id** là duy nhất nên thứ tự lựa chọn được xác định. Dù vậy, khi có nhiều session cùng sửa bảng, transaction isolation và khóa vẫn quyết định hàng nào thỏa điều kiện tại thời điểm thực thi. RBR giúp replica nhận kết quả cuối cùng mà nguồn đã tạo ra.

## 12. Checklist triển khai và xử lý sự cố

**Trước khi chọn binlog format**

- [ ] Đã xác định workload và mức độ phụ thuộc vào statement determinism.
- [ ] Đã kiểm tra **binlog_format** ở cả global và session.
- [ ] Đã đánh giá dung lượng binary log khi chuyển sang ROW.
- [ ] Đã kiểm tra replication filters và các công cụ downstream.
- [ ] Đã xác định row image phù hợp với nhu cầu CDC/audit.

**Khi vận hành RBR**

- [ ] Nguồn và replica có schema tương thích.
- [ ] Mỗi bảng quan trọng có primary key hoặc khóa duy nhất phù hợp.
- [ ] Không có ứng dụng ghi trực tiếp vào replica ngoài thiết kế.
- [ ] Trigger và stored program được triển khai nhất quán.
- [ ] Binary log và relay log có đủ dung lượng.

**Khi có lỗi hoặc nghi ngờ data drift**

- [ ] Đã lưu thông tin lỗi, file/position hoặc GTID.
- [ ] Đã kiểm tra trạng thái I/O thread và applier worker.
- [ ] Đã giải mã row event quanh vị trí lỗi.
- [ ] Đã so sánh cấu trúc và dữ liệu của hàng liên quan.
- [ ] Đã xác định nguyên nhân trước khi sửa hoặc skip transaction.
- [ ] Đã kiểm tra consistency sau khi xử lý và xác nhận replica bắt kịp.

## Kết luận

Row-based replication ghi lại các hàng thực tế mà nguồn đã thay đổi, giúp tránh nhiều sai lệch do câu lệnh không xác định khi chạy lại ở replica. **binlog_format=ROW** thường là lựa chọn phù hợp cho MySQL hiện đại; **binlog_row_image** quyết định mức chi tiết của row event và cần được chọn theo nhu cầu phục hồi, điều tra và consumer downstream. RBR vẫn cần schema tương thích, quy trình DDL nhất quán và giám sát data drift. Khi replica gặp lỗi 1032 hoặc 1062, hãy điều tra row event và trạng thái dữ liệu trước khi quyết định sửa hay dựng lại replica.
