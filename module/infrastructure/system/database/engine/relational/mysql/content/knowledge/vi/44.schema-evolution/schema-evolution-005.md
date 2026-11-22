# ALGORITHM INSTANT/INPLACE/COPY và điều kiện từng loại thay đổi

Khi thay đổi cấu trúc bảng MySQL bằng ALTER TABLE, thuật toán thực hiện ảnh hưởng trực tiếp đến thời gian chạy DDL, dung lượng đĩa, mức khóa và khả năng ứng dụng tiếp tục đọc/ghi. Ba thuật toán thường gặp là INSTANT, INPLACE và COPY. Chúng mô tả cách MySQL thực hiện thay đổi ở tầng lưu trữ; tên thuật toán không tự bảo đảm rằng thao tác hoàn toàn không khóa hoặc không ảnh hưởng đến workload.

INSTANT chủ yếu thay đổi metadata, không cần dựng lại toàn bộ dữ liệu bảng. INPLACE thực hiện thay đổi trong cấu trúc lưu trữ hiện có và có thể cho phép DML đồng thời, nhưng một số thao tác vẫn phải rebuild bảng hoặc xây dựng lại index. COPY tạo bảng tạm với cấu trúc mới rồi sao chép dữ liệu sang; cách này thường tốn thời gian, I/O và dung lượng hơn, đồng thời hạn chế ghi đồng thời.

Điều kiện hỗ trợ phụ thuộc phiên bản MySQL, storage engine, loại bảng, cấu trúc hiện tại và chính xác thao tác DDL. Bài học tập trung vào InnoDB trong MySQL hiện đại, đồng thời nhấn mạnh cách kiểm tra trên đúng phiên bản trước khi thay đổi production.

## 1. Ba thuật toán DDL hoạt động như thế nào?

### 1.1. ALGORITHM=INSTANT

INSTANT thay đổi metadata để MySQL diễn giải cấu trúc bảng theo định nghĩa mới. Với các thao tác được hỗ trợ, MySQL không phải đọc và ghi lại toàn bộ hàng trong bảng. Vì vậy thời gian thực hiện thường rất ngắn, mức sử dụng I/O thấp và DML có thể tiếp tục trong phần lớn thời gian thao tác.

Ví dụ thêm một cột nullable vào bảng InnoDB khi phiên bản và cấu trúc bảng hỗ trợ:

~~~sql
ALTER TABLE customers
  ADD COLUMN nickname VARCHAR(80) NULL,
  ALGORITHM=INSTANT;
~~~

Trong trường hợp được hỗ trợ, giá trị của cột mới được hiểu theo metadata cho các hàng cũ; MySQL không cần ghi lại từng hàng chỉ để thêm cột. Khi ứng dụng bắt đầu ghi giá trị mới, các hàng được cập nhật theo cách thông thường.

INSTANT không có nghĩa là không cần metadata lock. MySQL vẫn cần lấy metadata lock để bảo vệ định nghĩa bảng khi bắt đầu và hoàn tất DDL. Một transaction dài đang sử dụng bảng có thể khiến DDL phải chờ; một DDL đang chờ metadata lock cũng có thể làm các truy vấn mới xếp hàng phía sau. Vì vậy, một thay đổi instant vẫn có thể gây gián đoạn nếu có transaction lâu hoặc lock queue.

INSTANT cũng có giới hạn về loại thao tác và cấu trúc bảng. Không thể giả định mọi ADD COLUMN, DROP COLUMN, đổi kiểu dữ liệu hoặc thay đổi index đều thực hiện instant. Với InnoDB, hỗ trợ instant được mở rộng qua các phiên bản. Ví dụ, khả năng thêm cột ở vị trí bất kỳ và drop column instant được mở rộng trong MySQL 8.0.29; các phiên bản trước có giới hạn khác. Bảng có cấu trúc đặc biệt, index hoặc thuộc tính không tương thích có thể không hỗ trợ.

### 1.2. ALGORITHM=INPLACE

INPLACE thực hiện thay đổi mà không dùng quy trình tạo bảng tạm rồi sao chép toàn bộ hàng theo cách COPY. Tuy nhiên, tên INPLACE dễ gây hiểu nhầm: một thao tác INPLACE vẫn có thể xây dựng lại bảng hoặc index bên trong InnoDB. Điều quan trọng là xem loại thao tác cụ thể có rebuild hay không và nó cho phép mức đồng thời nào.

Ví dụ thêm secondary index:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Với thao tác và cấu trúc bảng hỗ trợ, InnoDB có thể tạo index trong khi ứng dụng tiếp tục đọc và ghi. MySQL thu thập các thay đổi phát sinh đồng thời để cập nhật cấu trúc mới trước khi hoàn tất. Quá trình này vẫn tiêu thụ CPU, I/O, dung lượng tạm và có thể làm tăng độ trễ truy vấn.

Một số thao tác INPLACE có rebuild bảng. Ví dụ, thêm primary key có thể phải sắp xếp và tổ chức lại dữ liệu theo clustered index mới. Vì vậy, INPLACE không đồng nghĩa với metadata-only, cũng không đồng nghĩa với thời gian chạy luôn ngắn.

LOCK=NONE là yêu cầu cho phép DML đồng thời trong quá trình DDL. Nếu thao tác không hỗ trợ mức khóa này, câu lệnh có thể thất bại thay vì tự giảm xuống mức khóa nghiêm ngặt hơn. Tuy nhiên, ngay cả khi LOCK=NONE được hỗ trợ, DDL vẫn cần metadata lock ở một số giai đoạn, đặc biệt khi bắt đầu và hoàn tất.

### 1.3. ALGORITHM=COPY

COPY tạo một bảng mới với cấu trúc đích, sao chép dữ liệu từ bảng cũ sang bảng mới rồi thay thế bảng cũ. Đây là cách tổng quát hơn và có thể hỗ trợ một số thay đổi mà INSTANT hoặc INPLACE không thực hiện được.

Ví dụ minh họa đổi kiểu dữ liệu trong trường hợp phiên bản/engine yêu cầu COPY:

~~~sql
ALTER TABLE customers
  MODIFY COLUMN phone_number VARCHAR(40),
  ALGORITHM=COPY;
~~~

Quá trình copy có thể đọc toàn bộ bảng, ghi toàn bộ dữ liệu và xây dựng lại index. Với bảng lớn, cần dự trù dung lượng cho bảng mới, index, tệp tạm, binary log và khoảng trống an toàn. Tác động có thể gồm I/O tăng, replication lag, thời gian DDL dài và hạn chế ghi vào bảng.

Mức khóa mặc định phụ thuộc thao tác và engine. COPY không hỗ trợ DML đồng thời như INPLACE với LOCK=NONE. Trong thực tế, cần giả định thao tác COPY có thể chặn ghi trong thời gian dài và xác nhận chính xác hành vi đọc/ghi theo phiên bản trước khi lập kế hoạch production.

## 2. So sánh nhanh ba thuật toán

| Thuộc tính | INSTANT | INPLACE | COPY |
|---|---|---|---|
| Cách thực hiện | Thay đổi metadata | Thay đổi cấu trúc tại chỗ; có thể rebuild | Tạo bảng mới và sao chép dữ liệu |
| Đọc/ghi lại toàn bộ hàng | Thường không | Tùy thao tác; một số thao tác rebuild | Có |
| Thời gian | Thường rất ngắn nếu được hỗ trợ | Từ ngắn đến dài tùy thao tác | Có thể dài với bảng lớn |
| I/O | Thường thấp | Có thể cao khi tạo index hoặc rebuild | Thường cao |
| DML đồng thời | Thường được hỗ trợ cho thao tác instant | Phụ thuộc LOCK và thao tác | Hạn chế; không dùng như online DDL với LOCK=NONE |
| Metadata lock | Vẫn cần | Vẫn cần | Vẫn cần |
| Dung lượng bổ sung | Thường thấp | Có thể cần không gian cho index/rebuild/log | Thường cần không gian cho bản sao và index |
| Rủi ro vận hành | Chờ metadata lock, giới hạn phiên bản/cấu trúc | Tải tài nguyên, online alter log, rebuild và metadata lock | Thời gian, dung lượng, khóa và replication lag |

Thứ tự ưu tiên thông thường là chọn thao tác INSTANT nếu thực sự được hỗ trợ, cân nhắc INPLACE với mức khóa phù hợp, và lập kế hoạch bảo trì rõ ràng nếu chỉ có COPY. Tuy nhiên, không nên chọn thuật toán chỉ theo tên: một thao tác INPLACE rebuild bảng lớn có thể tốn kém hơn một thao tác COPY trên bảng nhỏ.

## 3. Phân biệt ALGORITHM và LOCK

ALGORITHM quyết định cách MySQL thực hiện thay đổi cấu trúc. LOCK xác định mức đồng thời được phép trong khi DDL chạy. Đây là hai lựa chọn liên quan nhưng không thay thế nhau.

Các mức LOCK phổ biến:

| Mức khóa | Ý nghĩa |
|---|---|
| DEFAULT | MySQL chọn mức khóa tối đa mà thao tác hỗ trợ |
| NONE | Cho phép đọc và ghi đồng thời trong giai đoạn online mà thao tác hỗ trợ |
| SHARED | Cho phép đọc đồng thời nhưng chặn ghi |
| EXCLUSIVE | Chặn cả đọc và ghi trong thời gian khóa có hiệu lực |

Ví dụ yêu cầu MySQL tạo index theo INPLACE và cho phép DML đồng thời:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Nếu MySQL báo không thể thực hiện thao tác với LOCK=NONE, hãy xem đó là tín hiệu cần đánh giá lại thiết kế. Không xóa LOCK=NONE chỉ để câu lệnh chạy được nếu chưa hiểu mức gián đoạn mà DEFAULT hoặc mức khóa khác sẽ gây ra.

Với ALGORITHM=INSTANT, các phiên bản MySQL hiện đại giới hạn mức khóa ở chế độ mặc định; không nên cố yêu cầu LOCK=NONE, SHARED hoặc EXCLUSIVE cho thao tác instant. Dùng cú pháp INSTANT đơn giản và xác minh hành vi theo tài liệu phiên bản đang chạy.

LOCK=NONE cũng không có nghĩa là không khóa trong toàn bộ vòng đời câu lệnh. Metadata lock vẫn có thể chặn ở đầu/cuối DDL. Ứng dụng có thể gặp chờ nếu một transaction giữ metadata lock lâu hoặc DDL đang đợi lock và các truy vấn mới bị xếp hàng.

## 4. Những thay đổi thường gặp và thuật toán có thể sử dụng

Bảng dưới đây là hướng dẫn định hướng cho InnoDB, không phải ma trận hỗ trợ áp dụng cho mọi phiên bản:

| Thay đổi | Thuật toán thường gặp | Điều cần kiểm tra |
|---|---|---|
| Thêm cột nullable ở cuối bảng | INSTANT trên phiên bản hỗ trợ | Phiên bản, row format, cấu trúc bảng và giới hạn instant row version |
| Thêm cột ở vị trí bất kỳ | INSTANT trên MySQL 8.0.29+ nếu đủ điều kiện | Phiên bản và giới hạn cấu trúc bảng |
| Drop column | INSTANT trên MySQL 8.0.29+ trong trường hợp hỗ trợ; trước đó thường cần cách khác | Index, generated column, partition và giới hạn row version |
| Đổi giá trị DEFAULT của cột | Thường có thể INSTANT với thay đổi metadata được hỗ trợ | Kiểu cột, biểu thức default và phiên bản |
| Thêm secondary index | Thường INPLACE | LOCK=NONE có được hỗ trợ không; dung lượng và tải tạo index |
| Drop secondary index | Thường INPLACE | Phụ thuộc loại index và cấu trúc bảng |
| Thêm primary key | Có thể INPLACE nhưng thường rebuild dữ liệu | Kích thước bảng, clustered index và dung lượng |
| Đổi kiểu dữ liệu cột | Có thể INPLACE hoặc cần COPY | Khả năng chuyển đổi vật lý, nguy cơ mất dữ liệu và phiên bản |
| Đổi row format hoặc thuộc tính lưu trữ | Có thể cần rebuild hoặc COPY | Engine, row format đích, compression và kích thước dữ liệu |

Không dùng bảng này thay cho thử nghiệm. Ví dụ, thêm một cột có vẻ đơn giản nhưng có thể không instant nếu bảng đã chạm giới hạn row version hoặc có cấu trúc không tương thích. Ngược lại, một thao tác có thể INPLACE ở một phiên bản nhưng cần COPY ở phiên bản khác.

### 4.1. Thêm cột và giới hạn instant row version

InnoDB có thể lưu một số thay đổi instant dưới dạng phiên bản hàng (row version) thay vì viết lại toàn bộ hàng. Mỗi thao tác thêm hoặc xóa cột instant có thể làm tăng số row version của bảng. MySQL giới hạn tổng số row version; khi chạm giới hạn, thao tác instant tiếp theo có thể không thực hiện được cho đến khi bảng được rebuild theo cách phù hợp.

Trên MySQL 8.0.29 trở lên, có thể xem thông tin row version trong metadata InnoDB qua các cột được phiên bản đó cung cấp, chẳng hạn TOTAL_ROW_VERSIONS trong INFORMATION_SCHEMA.INNODB_TABLES. Trước khi dựa vào cột này, kiểm tra nó có tồn tại trong đúng phiên bản đang chạy.

Ví dụ truy vấn trên phiên bản có cột metadata tương ứng:

~~~sql
SELECT
  NAME,
  TOTAL_ROW_VERSIONS
FROM INFORMATION_SCHEMA.INNODB_TABLES
WHERE NAME = 'app_db/customers';
~~~

Nếu số row version đã gần giới hạn, cần lên kế hoạch rebuild có kiểm soát để hợp nhất cấu trúc vật lý trước khi tiếp tục các thay đổi instant. Rebuild có thể tốn tài nguyên và thời gian, vì vậy nên tính đến trong kế hoạch schema evolution thay vì chờ đến lúc DDL thất bại.

### 4.2. Thêm index

Thêm secondary index thường dùng INPLACE và có thể cho phép LOCK=NONE. Dù vậy, MySQL phải đọc dữ liệu để xây dựng index, sắp xếp khóa và ghi cấu trúc index mới. Với bảng lớn, thao tác có thể làm tăng I/O và ảnh hưởng latency của truy vấn khác.

Trước khi tạo index, xác nhận index chưa tồn tại, thứ tự cột phù hợp với truy vấn và dung lượng đĩa đủ. Sau khi tạo, kiểm tra truy vấn bằng EXPLAIN và theo dõi thời gian phản hồi. Không tạo nhiều index lớn cùng lúc trên một máy production nếu chưa đánh giá cạnh tranh I/O.

## 5. Cách yêu cầu thuật toán một cách có chủ đích

Nếu muốn MySQL chỉ thực hiện bằng INSTANT và báo lỗi khi không hỗ trợ:

~~~sql
ALTER TABLE customers
  ADD COLUMN preferred_name VARCHAR(100) NULL,
  ALGORITHM=INSTANT;
~~~

Nếu muốn tránh fallback sang COPY nhưng chấp nhận INPLACE:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_status_created (status, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Nếu không chỉ định ALGORITHM, MySQL dùng DEFAULT và tự chọn phương pháp mà nó cho là phù hợp. Điều đó tiện lợi nhưng có thể không phù hợp với yêu cầu kiểm soát thời gian khóa của production. Đối với thay đổi nhạy cảm, chỉ định rõ thuật toán và mức khóa mong muốn giúp câu lệnh thất bại sớm khi điều kiện không đạt, thay vì bất ngờ chạy một thao tác tốn kém hơn dự kiến.

Không ép ALGORITHM=INPLACE hoặc INSTANT chỉ để tránh COPY nếu thao tác không hỗ trợ. Lỗi từ MySQL là cơ hội dừng để đánh giá lại, không phải lý do để bỏ qua điều kiện an toàn.

## 6. Metadata lock và transaction dài

MySQL sử dụng metadata lock (MDL) để bảo vệ định nghĩa đối tượng khi truy vấn và DDL cùng truy cập bảng. Một transaction có thể giữ metadata lock đến khi transaction kết thúc, kể cả khi câu lệnh truy vấn đã chạy xong nhưng transaction vẫn mở.

Ví dụ:

1. Session A mở transaction và truy vấn bảng customers.
2. Session A chưa COMMIT hoặc ROLLBACK.
3. Session B chạy ALTER TABLE customers ADD COLUMN ...
4. DDL phải chờ metadata lock của Session A.
5. Các truy vấn mới có thể xếp hàng sau DDL đang chờ, làm hệ thống tưởng như bị treo.

Vì vậy, DDL INSTANT vẫn có thể bị chậm bởi transaction lâu. Trước khi chạy, kiểm tra transaction mở, truy vấn dài, lock wait và process list.

Có thể xem các metadata lock đang được cấp hoặc chờ trên các phiên bản có Performance Schema phù hợp:

~~~sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app_db'
  AND OBJECT_NAME = 'customers';
~~~

Nếu có lock đang chờ, tìm session sở hữu lock và xác định liệu transaction có thể kết thúc an toàn không. Không kill session hoặc transaction tùy tiện; trước hết cần xác nhận chủ sở hữu và tác động nghiệp vụ.

Có thể giới hạn thời gian chờ metadata lock bằng biến lock_wait_timeout ở phạm vi session:

~~~sql
SET SESSION lock_wait_timeout = 10;
~~~

Đặt timeout giúp DDL thoát ra thay vì chờ không giới hạn khi không lấy được metadata lock. Giá trị cụ thể cần dựa vào cửa sổ triển khai. Timeout thấp có thể khiến DDL thất bại khi hệ thống đang bận; cần xử lý lỗi và thử lại vào thời điểm phù hợp.

## 7. Online DDL vẫn có chi phí

Với một số thao tác INPLACE cho phép DML đồng thời, InnoDB ghi nhận thay đổi phát sinh trong lúc xây dựng cấu trúc mới bằng online alter log. Nếu lượng thay đổi vượt quá giới hạn innodb_online_alter_log_max_size, DDL có thể thất bại. Tăng giới hạn không miễn phí: nó tiêu thụ thêm dung lượng và có thể kéo dài giai đoạn hoàn tất.

Một số tác động cần theo dõi:

- CPU và I/O tăng do quét bảng, sắp xếp khóa hoặc rebuild.
- Dung lượng đĩa tăng do index mới, tệp tạm hoặc online alter log.
- Replication lag tăng do DDL hoặc thay đổi phát sinh trong lúc thao tác.
- Latency ứng dụng tăng do cạnh tranh tài nguyên.
- Metadata lock ở giai đoạn bắt đầu và hoàn tất.
- DDL kéo dài làm thay đổi kế hoạch bảo trì và thời gian rollback.

Online DDL không bảo đảm mọi truy vấn đều không bị ảnh hưởng. Cần chạy thử với kích thước dữ liệu và tốc độ ghi gần production, theo dõi các chỉ số và xác định ngưỡng dừng.

## 8. Lựa chọn thuật toán theo ví dụ thực tế

### Tình huống A: Thêm cột mô tả tùy chọn

Yêu cầu thêm cột nickname nullable vào bảng customers. Nếu phiên bản InnoDB hỗ trợ instant cho cấu trúc này, dùng ALGORITHM=INSTANT. Trước khi chạy, xác nhận bảng không vướng giới hạn row version và không có transaction dài giữ MDL.

### Tình huống B: Thêm index cho truy vấn báo cáo

Yêu cầu thêm index trên (status, created_at). Kiểm tra thứ tự cột theo điều kiện WHERE và ORDER BY. Nếu thao tác hỗ trợ, dùng INPLACE, LOCK=NONE để cho phép DML đồng thời. Đo I/O, dung lượng, lag và latency trong khi index được xây dựng.

### Tình huống C: Đổi kiểu dữ liệu làm thay đổi cách lưu

Yêu cầu chuyển một cột số từ INT sang kiểu có phạm vi lớn hơn hoặc chuyển chuỗi sang kiểu khác. Khả năng INPLACE phụ thuộc phép chuyển đổi cụ thể và phiên bản. Nếu MySQL yêu cầu COPY, hãy ước tính thời gian và dung lượng, chọn cửa sổ bảo trì hoặc công cụ online schema change đã được kiểm thử. Kiểm tra giá trị ngoài phạm vi và khả năng mất dữ liệu trước khi chạy.

### Tình huống D: Thêm primary key cho bảng lớn

Thêm primary key có thể yêu cầu InnoDB tổ chức lại clustered index. Dù câu lệnh chấp nhận INPLACE, thao tác có thể rebuild toàn bộ bảng và tốn I/O đáng kể. Cần đo thời gian trên bản sao gần production, đánh giá không gian đĩa và tác động replication.

## 9. Quy trình triển khai ALTER TABLE an toàn

Một quy trình thực tế nên có các bước sau:

1. **Xác định thay đổi:** ghi rõ bảng, cột/index, kiểu dữ liệu trước và sau, tác động ứng dụng và yêu cầu tương thích.
2. **Kiểm tra phiên bản và engine:** xác định đúng MySQL version, InnoDB, cấu trúc bảng, partition, index và các điều kiện có thể hạn chế algorithm.
3. **Chọn algorithm và lock:** ưu tiên INSTANT khi được hỗ trợ; nếu không, đánh giá INPLACE và LOCK=NONE; nếu chỉ còn COPY, lập kế hoạch dung lượng và downtime.
4. **Thử trên bản sao:** dùng dữ liệu có kích thước, index và workload tương đương production; ghi thời gian, I/O, lock và replication lag.
5. **Kiểm tra metadata lock:** phát hiện transaction dài và session đang giữ lock trước khi triển khai.
6. **Chuẩn bị backup và phương án phục hồi:** xác nhận backup có thể restore; chuẩn bị DDL ngược nếu có thể và đánh giá dữ liệu có bị mất khi đổi kiểu hay không.
7. **Chạy có giới hạn:** chỉ định algorithm/lock rõ ràng khi cần, đặt lock_wait_timeout phù hợp và chạy trong cửa sổ đã thống nhất.
8. **Theo dõi:** quan sát process list, Performance Schema, CPU, I/O, dung lượng, replication lag và lỗi ứng dụng.
9. **Xác minh sau DDL:** dùng SHOW CREATE TABLE, kiểm tra index và chạy EXPLAIN cho truy vấn liên quan.
10. **Đóng thay đổi:** ghi nhận kết quả, thời gian, thuật toán thực tế, lock và các điểm cần theo dõi tiếp.

Ví dụ kiểm tra cấu trúc trước và sau:

~~~sql
SHOW CREATE TABLE customers\G
SHOW INDEX FROM customers;
~~~

Không chạy nhiều DDL lớn đồng thời nếu chúng cạnh tranh tài nguyên hoặc metadata lock. Trong hệ thống có replication, xác minh DDL đã được áp dụng ở các replica và kiểm tra lag trước khi định tuyến workload đọc quan trọng.

## 10. Rollback và giới hạn của DDL

ALTER TABLE thường gây implicit commit và không thể hoàn tác bằng ROLLBACK của transaction SQL thông thường. Atomic DDL trong MySQL bảo vệ tính nhất quán của một số thao tác DDL khi có sự cố máy chủ, nhưng không có nghĩa người vận hành có thể rollback schema về định nghĩa trước bằng lệnh ROLLBACK.

Trước khi thay đổi, chuẩn bị một trong các phương án:

- DDL ngược đã được kiểm thử, nếu phép chuyển đổi không làm mất thông tin.
- Restore từ backup hoặc snapshot khi schema/data bị hỏng nghiêm trọng.
- Chạy migration bổ sung để sửa schema và dữ liệu theo hướng tiến lên.
- Với thay đổi không tương thích hoặc khó rollback, dùng chiến lược expand-and-contract: thêm cấu trúc mới, triển khai ứng dụng tương thích cả hai dạng, backfill dữ liệu, chuyển đọc/ghi, rồi mới loại bỏ cấu trúc cũ ở một đợt riêng.

Đổi kiểu dữ liệu có thể làm mất dữ liệu nếu giá trị không biểu diễn được trong kiểu mới. Drop column hoặc drop index có thể ảnh hưởng ứng dụng và truy vấn. Một DDL hoàn tất thành công không chứng minh ứng dụng tương thích. Cần kiểm tra cả code đang chạy và phiên bản ứng dụng sẽ được triển khai.

## 11. Tình huống thực hành

Một bảng orders có 80 triệu hàng. Nhóm phát triển yêu cầu thêm cột delivery_note, tạo index theo (customer_id, created_at) và đổi cột legacy_code từ VARCHAR(20) sang VARCHAR(80). Hệ thống có traffic ghi liên tục và một replica phục vụ báo cáo.

Hãy xây dựng kế hoạch:

1. Kiểm tra phiên bản MySQL, engine, cấu trúc bảng và khả năng instant add column cho delivery_note.
2. Nếu được hỗ trợ, thêm delivery_note bằng ALGORITHM=INSTANT; kiểm tra metadata lock và row version.
3. Đánh giá index mới bằng INPLACE, LOCK=NONE nếu được hỗ trợ; đo I/O và replication lag trong quá trình build.
4. Kiểm tra phép đổi legacy_code có cần rebuild hoặc COPY không; kiểm tra dữ liệu hiện có và dung lượng đĩa.
5. Nếu đổi kiểu dữ liệu cần COPY, tách thành một cửa sổ bảo trì hoặc dùng chiến lược online schema change phù hợp đã diễn tập.
6. Sau mỗi DDL, xác minh schema, index, truy vấn EXPLAIN và trạng thái replica trước khi tiếp tục bước tiếp theo.

Không nên gộp ba thay đổi vào một câu ALTER TABLE chỉ để giảm số lần triển khai nếu chúng có thuật toán, lock và chi phí khác nhau. Tách bước giúp xác định rõ thay đổi nào gây tải hoặc lỗi và giảm phạm vi ảnh hưởng khi cần dừng.

## 12. Câu hỏi tự kiểm tra

1. INSTANT khác INPLACE ở điểm nào về cách thay đổi metadata và dữ liệu vật lý?
2. Vì sao ALGORITHM=INPLACE vẫn có thể rebuild bảng?
3. ALGORITHM và LOCK kiểm soát hai khía cạnh nào của ALTER TABLE?
4. Vì sao INSTANT vẫn có thể phải chờ metadata lock?
5. Khi nào thêm index có thể dùng INPLACE với LOCK=NONE và chi phí nào vẫn tồn tại?
6. Vì sao cần kiểm tra phiên bản trước khi dùng instant ADD/DROP COLUMN?
7. Online alter log có vai trò gì khi DML diễn ra đồng thời?
8. Vì sao ALTER TABLE không thể được hoàn tác bằng ROLLBACK SQL thông thường?

Chọn thuật toán ALTER TABLE là quyết định về cách thay đổi được thực hiện, mức đồng thời, tài nguyên và rủi ro vận hành. Hãy xác minh hỗ trợ trên đúng phiên bản, yêu cầu thuật toán và mức khóa rõ ràng khi cần, diễn tập trên dữ liệu tương đương production và kiểm tra cả schema lẫn ứng dụng sau khi DDL hoàn tất.
