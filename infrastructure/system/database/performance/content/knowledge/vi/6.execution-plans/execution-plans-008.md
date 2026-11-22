# Chạy EXPLAIN ANALYZE an toàn: câu lệnh thực sự chạy và có thể làm thay đổi dữ liệu

## Vì sao EXPLAIN ANALYZE cần được dùng cẩn trọng?

Khi tối ưu hiệu năng cơ sở dữ liệu, kế hoạch thực thi cho biết hệ quản trị dự định truy cập dữ liệu như thế nào: quét bảng, tìm kiếm chỉ mục, kết hợp bảng, sắp xếp, tổng hợp hoặc truy xuất hàng. Lệnh EXPLAIN thường giúp xem lựa chọn của bộ tối ưu mà không cần thực hiện truy vấn theo cách thông thường. Tuy nhiên, EXPLAIN ANALYZE có ý nghĩa khác: hệ quản trị thực sự chạy câu lệnh để thu thập số hàng, số vòng lặp và thời gian thực tế.

Sự khác biệt này rất quan trọng. Với một câu SELECT thông thường, việc chạy truy vấn vẫn có thể tiêu tốn CPU, bộ nhớ, I/O, giữ kết nối và khóa trong thời gian dài. Với câu INSERT, UPDATE, DELETE hoặc MERGE, việc chạy để đo có thể ghi, sửa hoặc xóa dữ liệu thật. Trigger, hàm, thủ tục, sequence, lời gọi dịch vụ bên ngoài và các tác dụng phụ khác cũng có thể được kích hoạt.

Trong tối ưu hiệu năng cơ sở dữ liệu, đo đạc phải phản ánh đúng workload nhưng không được tạo ra một sự cố mới. Người thực hiện cần hiểu chính xác công cụ đang chạy câu lệnh nào, dữ liệu nào có thể thay đổi, transaction có thể hoàn tác những gì, và giới hạn tài nguyên nào cần đặt trước khi bắt đầu.

Bài học này trình bày cách phân biệt EXPLAIN với EXPLAIN ANALYZE, đánh giá rủi ro của câu lệnh được thực thi, chọn môi trường và transaction phù hợp, cũng như đọc kết quả thực tế để kiểm chứng kế hoạch truy vấn.

## EXPLAIN và EXPLAIN ANALYZE khác nhau thế nào?

### EXPLAIN: xem kế hoạch được ước lượng

EXPLAIN yêu cầu bộ tối ưu phân tích câu lệnh và trình bày kế hoạch dự kiến. Kế hoạch được xây dựng từ cú pháp SQL, schema, chỉ mục, thống kê, tham số và cấu hình của hệ quản trị.

Kế hoạch ước lượng có thể cho biết:

- Loại truy cập bảng hoặc chỉ mục.
- Thứ tự join và thuật toán join.
- Điều kiện tìm kiếm và điều kiện lọc.
- Số hàng và chi phí mà bộ tối ưu ước lượng.
- Các bước sort, aggregate, materialize hoặc truy xuất hàng.
- Những chỉ mục mà optimizer dự định sử dụng.

EXPLAIN thường không chạy phần truy vấn dữ liệu như một lần thực thi thông thường. Dù vậy, nó vẫn có thể cần phân tích metadata, lấy khóa metadata hoặc thực hiện một số công việc chuẩn bị. Không nên coi mọi biến thể EXPLAIN ở mọi hệ quản trị là hoàn toàn không có tác động.

### EXPLAIN ANALYZE: thực thi để đo số liệu thật

EXPLAIN ANALYZE chạy câu lệnh và bổ sung số liệu thực tế. Tùy hệ quản trị, kết quả có thể gồm:

- Actual Rows: số hàng toán tử thực sự tạo ra.
- Loops hoặc số lần thực thi: số lần toán tử được gọi.
- Actual Time: thời gian đo ở từng toán tử hoặc toàn câu lệnh.
- Buffers hoặc logical/physical reads: hoạt động đọc bộ nhớ và lưu trữ.
- WAL hoặc thông tin ghi log giao dịch.
- Sort method, memory usage và spill ra vùng lưu trữ tạm.
- Các cảnh báo hoặc thông tin về hàng bị loại bởi bộ lọc.

Đổi lại, câu lệnh thực sự được chạy. EXPLAIN ANALYZE không chỉ mô phỏng kế hoạch. Nếu câu lệnh là UPDATE, dữ liệu có thể bị cập nhật; nếu là DELETE, hàng có thể bị xóa; nếu là INSERT, hàng mới có thể được thêm. Trigger và các cơ chế đi kèm có thể chạy như khi ứng dụng thực hiện câu lệnh.

### Kế hoạch ước lượng và kế hoạch thực tế phục vụ hai câu hỏi khác nhau

| Công cụ hoặc kết quả | Câu hỏi được trả lời | Giới hạn cần nhớ |
|---|---|---|
| EXPLAIN | Optimizer dự định thực hiện câu lệnh ra sao? | Số hàng và chi phí chủ yếu là ước lượng |
| EXPLAIN ANALYZE | Khi chạy, các toán tử thực tế xử lý bao nhiêu hàng và mất bao lâu? | Câu lệnh được thực thi và có thể tạo tác động thật |
| Actual Execution Plan trong SQL Server | Câu lệnh đã chạy theo kế hoạch nào và có số liệu thực tế gì? | Bật chế độ này đồng nghĩa câu lệnh vẫn được thực thi |
| EXPLAIN ANALYZE trong MySQL | Truy vấn được thực thi ra sao theo iterator và số liệu thực tế? | Có thể tiêu tốn tài nguyên; phạm vi câu lệnh hỗ trợ phụ thuộc phiên bản |

Không thể thay thế số liệu thực tế bằng phần trăm cost ước lượng. Cũng không nên lấy một kế hoạch thực tế từ môi trường thử nghiệm rồi mặc định nó sẽ giống production nếu dữ liệu, thống kê, tham số, cache, concurrency hoặc cấu hình khác nhau.

## Nhận diện rủi ro trước khi chạy

Trước khi chạy EXPLAIN ANALYZE hoặc bật actual plan, hãy phân loại câu lệnh và các tác dụng phụ có thể xảy ra.

### Câu SELECT không mặc nhiên vô hại

Một SELECT thông thường không ghi hàng vào bảng, nhưng vẫn có thể:

- Quét hàng triệu hàng hoặc trang dữ liệu, làm tăng CPU và I/O.
- Cấp phát bộ nhớ lớn cho sort, hash join hoặc aggregate.
- Tạo dữ liệu trung gian và spill ra đĩa.
- Giữ connection lâu, làm cạn connection pool.
- Chờ khóa hoặc giữ khóa tùy isolation level và loại truy vấn.
- Đọc dữ liệu nhạy cảm trong kết quả hoặc log.
- Gọi hàm có tác dụng phụ, truy cập hệ thống ngoài hoặc thực hiện công việc tốn kém.
- Dùng SELECT FOR UPDATE hoặc cơ chế khóa tương đương để khóa hàng.

Một câu SELECT có thể làm tăng độ trễ của các workload khác khi nó tiêu thụ tài nguyên dùng chung. Vì vậy, cần đặt giới hạn thời gian, chọn cửa sổ tải phù hợp và cân nhắc replica hoặc môi trường thử nghiệm.

### Câu lệnh thay đổi dữ liệu

Các câu lệnh sau cần được xem là có khả năng thay đổi trạng thái:

- INSERT thêm hàng.
- UPDATE sửa hàng.
- DELETE xóa hàng.
- MERGE kết hợp chèn, cập nhật hoặc xóa theo điều kiện.
- Các câu lệnh gọi stored procedure hoặc function có tác dụng phụ.
- Những câu lệnh tạo bảng, ghi file, gửi thông báo hoặc gọi hệ thống ngoài.

EXPLAIN ANALYZE trên DML trong PostgreSQL thực thi thao tác DML. Nếu đo một UPDATE hoặc DELETE trên dữ liệu thật, dữ liệu có thể bị thay đổi ngay trong lúc đo. Một transaction có thể hoàn tác phần lớn thay đổi transactional, nhưng không phải mọi tác dụng phụ đều được hoàn tác.

Với SQL Server, bật Actual Execution Plan cũng không biến câu lệnh DML thành mô phỏng. Câu lệnh vẫn chạy và thực hiện thao tác ghi. Với MySQL, phạm vi câu lệnh được EXPLAIN ANALYZE hỗ trợ phụ thuộc phiên bản; ở những phiên bản chỉ hỗ trợ phân tích thực thi SELECT, hãy dùng EXPLAIN cho kế hoạch DML và kiểm tra tài liệu đúng phiên bản. Không suy luận rằng một câu lệnh an toàn chỉ vì công cụ từ chối chạy nó ở chế độ ANALYZE.

### Những tác dụng phụ khó hoàn tác

ROLLBACK không phải nút khôi phục toàn diện. Một số ví dụ cần lưu ý:

- Sequence hoặc identity có thể tiêu thụ giá trị và không quay lại số cũ sau rollback.
- Trigger hoặc function có thể gửi HTTP request, email, gọi dịch vụ ngoài, ghi file hoặc thực hiện hành động ngoài transaction.
- Bảng dùng storage engine không hỗ trợ transaction có thể không hoàn tác được thay đổi.
- Một số câu lệnh DDL có thể gây implicit commit hoặc không được rollback theo cách người dùng kỳ vọng.
- Giao dịch có thể giữ khóa trong lúc chạy, làm phiên khác bị chặn dù cuối cùng rollback.
- Các thao tác có thể tạo WAL/binlog, tăng replication lag hoặc làm đầy vùng lưu trữ log.
- Stored procedure có thể thực hiện nhiều câu lệnh khác nhau mà người chạy không nhìn thấy từ dòng lệnh gọi ban đầu.

Trước khi chạy, hãy tìm hiểu trigger, constraint, function, procedure, foreign table, external integration và loại bảng liên quan nếu chúng có thể ảnh hưởng đến phạm vi thử nghiệm. Không dựa vào một lệnh ROLLBACK để biện minh cho việc chạy DML tùy ý trên production.

## Quy trình an toàn trước khi thực thi

### Bước 1: xác định chính xác câu lệnh

Lấy đúng SQL mà ứng dụng thực thi, bao gồm điều kiện, kiểu dữ liệu tham số và cách bind tham số. Không tự ý thay tham số bằng một giá trị dễ đo nếu giá trị đó làm thay đổi độ chọn lọc và kế hoạch.

Kiểm tra xem câu lệnh có chứa:

- INSERT, UPDATE, DELETE, MERGE hoặc SELECT INTO.
- SELECT FOR UPDATE, khóa advisory hoặc hint khóa.
- Hàm, thủ tục hoặc biểu thức có tác dụng phụ.
- Gọi linked server, foreign data wrapper, UDF bên ngoài hoặc dịch vụ tích hợp.
- DDL, thao tác file hoặc lệnh quản trị.
- Nhiều câu lệnh được ghép trong một batch.

Nếu SQL gọi procedure, cần hiểu procedure thực hiện những thao tác nào. Chỉ nhìn câu CALL hoặc EXEC không đủ để xác định tác động.

### Bước 2: chọn môi trường phù hợp

Thứ tự ưu tiên khi kiểm tra câu lệnh có khả năng thay đổi dữ liệu:

1. Môi trường thử nghiệm với dữ liệu mô phỏng phù hợp.
2. Bản sao hoặc bản phục hồi từ dữ liệu production, đã loại bỏ hoặc cô lập tác dụng phụ bên ngoài.
3. Replica đọc dành cho phân tích SELECT, sau khi xác nhận tải đọc và độ trễ đồng bộ cho phép.
4. Production chỉ khi có quy trình vận hành được phê duyệt, giới hạn rõ ràng và biện pháp giảm thiểu tác động.

Replica đọc không phải lựa chọn an toàn tuyệt đối. Một truy vấn SELECT nặng vẫn có thể làm tăng CPU/I/O và replication lag. Một số replica còn có cơ chế cancel truy vấn xung đột với apply WAL hoặc replay. Không chạy DML để thử nghiệm trên replica chỉ đọc.

Nếu cần kiểm tra câu lệnh ghi, nên dùng dữ liệu có thể khôi phục và môi trường cô lập. Dữ liệu thử phải có phân bố và quy mô gần workload thật; một bảng vài trăm hàng không thể đại diện cho bảng hàng chục triệu hàng.

### Bước 3: xác định phạm vi tác động

Ghi lại:

- Bảng, partition, tenant hoặc nhóm hàng bị tác động.
- Điều kiện WHERE và số hàng dự kiến bị ảnh hưởng.
- Trigger, cascade, foreign key và các bảng phụ liên quan.
- Số lần chạy, concurrency và tần suất truy vấn.
- Dung lượng dữ liệu tạm, WAL/binlog và log có thể phát sinh.
- Tác động tới các phiên khác, connection pool và replication.

Với DML, hãy xác định trước số hàng dự kiến bị thay đổi bằng một truy vấn kiểm tra phù hợp trong môi trường an toàn. Không mặc định điều kiện lọc sẽ khớp số hàng như dự kiến khi dữ liệu thay đổi.

### Bước 4: đặt giới hạn thời gian và tài nguyên

Một phép đo nên có giới hạn rõ ràng:

- Statement timeout hoặc query timeout.
- Lock timeout hoặc giới hạn chờ khóa.
- Giới hạn số lần chạy và concurrency.
- Giới hạn bộ nhớ, sort hoặc vùng lưu trữ tạm nếu hệ quản trị hỗ trợ.
- Theo dõi CPU, I/O, số phiên hoạt động và hàng đợi.
- Cơ chế hủy truy vấn và người chịu trách nhiệm theo dõi.

Timeout không bảo đảm mọi tác động đều được ngăn chặn. Khi bị hủy, hệ quản trị có thể cần thời gian rollback hoặc dọn dẹp; khóa và tài nguyên có thể tiếp tục bị giữ trong giai đoạn đó.

### Bước 5: lưu baseline trước khi đo

Ghi lại thời gian, tham số, workload, số hàng dự kiến, phiên bản schema, thống kê và cấu hình liên quan. Baseline nên gồm p50/p95/p99, throughput, CPU, logical reads, physical reads, lock wait, I/O latency và các chỉ số phù hợp với truy vấn.

Nếu thay đổi dữ liệu hoặc cấu hình giữa hai lần đo, kết quả trước/sau có thể không còn so sánh trực tiếp được.

## Ví dụ sử dụng theo từng hệ quản trị

### PostgreSQL: phân tích SELECT trong transaction chỉ đọc

Với truy vấn đọc thuần túy, có thể kết hợp transaction read-only, statement timeout và EXPLAIN ANALYZE:

~~~sql
BEGIN READ ONLY;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 315
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00';

COMMIT;
~~~

BEGIN READ ONLY giúp PostgreSQL từ chối nhiều thao tác ghi trong transaction. SET LOCAL giới hạn thời gian áp dụng trong transaction hiện tại. BUFFERS cung cấp thông tin về hoạt động buffer; TIMING OFF giảm chi phí đo thời gian ở từng node trong một số tình huống, trong khi vẫn thu thập số hàng và tổng thời gian.

Read-only transaction không ngăn mọi tác dụng phụ có thể xảy ra trong function. Hàm được gọi từ SELECT vẫn có thể thực hiện hành động ngoài cơ chế mà hệ quản trị không kiểm soát được. Cần xem xét hàm và extension được gọi, cũng như các truy vấn khóa như SELECT FOR UPDATE.

Nếu lệnh bị lỗi và transaction rơi vào trạng thái aborted, dùng ROLLBACK để kết thúc transaction. Không giữ transaction mở trong lúc phân tích kết quả hoặc trao đổi với nhóm.

### PostgreSQL: DML chỉ trong môi trường có thể khôi phục

EXPLAIN ANALYZE trên DML thực sự chạy thao tác. Ví dụ sau chỉ minh họa cấu trúc kiểm thử trên dữ liệu thử nghiệm, với điều kiện đã xác nhận phạm vi hàng:

~~~sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < TIMESTAMP '2024-01-01 00:00:00'
  AND status = 'CLOSED';

ROLLBACK;
~~~

UPDATE ở trên được thực thi. ROLLBACK hoàn tác các thay đổi transactional trong bảng và các thao tác transactional liên quan. Tuy nhiên, sequence đã được gọi, lời gọi ngoài, side effect của function, hành động tới hệ thống khác hoặc các tác động không thuộc transaction có thể không được hoàn tác. Trigger cũng được thực thi trong lúc UPDATE chạy.

Không chạy ví dụ DML này trên production chỉ vì cuối cùng có ROLLBACK. Hãy dùng môi trường thử nghiệm hoặc bản sao cô lập, xác nhận trigger và function, giới hạn số hàng, theo dõi WAL và khóa.

### SQL Server: Actual Execution Plan và thống kê IO/TIME

Trong SQL Server Management Studio, bật Include Actual Execution Plan khiến truy vấn được thực thi và kế hoạch thực tế được thu thập. Có thể kết hợp thống kê IO và TIME cho truy vấn đọc:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT order_id, created_at, total_amount
FROM dbo.orders
WHERE customer_id = 315
  AND created_at >= '20261101'
  AND created_at <  '20261120';

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
~~~

Actual Execution Plan bổ sung thông tin số hàng thực tế và số lần thực hiện. STATISTICS IO cung cấp số liệu đọc; STATISTICS TIME cung cấp thời gian CPU và thời gian elapsed. Các số liệu này cần được đọc cùng kế hoạch và điều kiện tải.

Với DML, actual plan vẫn đi kèm việc câu lệnh thực sự thay đổi dữ liệu. Trong môi trường thử nghiệm, có thể dùng transaction và rollback để kiểm tra các thay đổi transactional:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.orders
SET status = 'ARCHIVED'
WHERE created_at < '20240101'
  AND status = 'CLOSED';

ROLLBACK TRANSACTION;
~~~

Đây chỉ là minh họa cách cô lập thay đổi transactional. Nếu bật actual plan cho UPDATE, UPDATE vẫn chạy trước khi rollback. Identity và sequence có thể tiêu thụ giá trị không hoàn lại; trigger có thể gọi hệ thống ngoài; tác vụ khác có thể bị chặn trong thời gian transaction. Vì vậy, không dùng mẫu này như giấy phép chạy DML không kiểm soát trên production.

Nếu cần kiểm tra kế hoạch mà không thực thi, hãy dùng Estimated Execution Plan hoặc cơ chế SHOWPLAN phù hợp. Lưu ý một số chế độ SHOWPLAN có thể yêu cầu batch chỉ chứa lệnh thiết lập kế hoạch và không chạy câu truy vấn theo cách thông thường. Hãy tuân theo hướng dẫn của phiên bản SQL Server đang sử dụng.

### MySQL: EXPLAIN và EXPLAIN ANALYZE

EXPLAIN cho biết kế hoạch dự kiến. EXPLAIN ANALYZE thực thi truy vấn được hỗ trợ và hiển thị số liệu thực tế theo iterator. Ví dụ với truy vấn đọc:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 315
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-11-20';
~~~

Kết quả có thể cho biết thời gian khởi động, thời gian thực hiện, số hàng và số vòng lặp ở từng iterator. Hãy kiểm tra xem số hàng thực tế có lệch nhiều so với ước lượng và iterator nào đang lặp nhiều.

EXPLAIN ANALYZE không biến truy vấn thành một phép mô phỏng. SELECT vẫn tiêu thụ tài nguyên và có thể gọi function có tác dụng phụ hoặc thực hiện khóa theo câu lệnh. Với DML, khả năng hỗ trợ và hành vi của EXPLAIN khác nhau theo phiên bản. Hãy kiểm tra tài liệu đúng phiên bản; dùng EXPLAIN để xem kế hoạch khi ANALYZE không hỗ trợ loại câu lệnh đó.

Trong MySQL, rollback chỉ có thể hoàn tác thay đổi thuộc transaction và storage engine hỗ trợ transaction. Bảng dùng engine không transactional, câu lệnh DDL có implicit commit, hoặc side effect bên ngoài có thể không được hoàn tác như mong đợi. Không chạy thử DML trên dữ liệu thật dựa vào giả định rằng mọi bảng đều là InnoDB và mọi tác động đều transactional.

## Đọc kết quả EXPLAIN ANALYZE

### So sánh Estimated Rows và Actual Rows

Chênh lệch lớn giữa số hàng ước lượng và số hàng thực tế là tín hiệu cần điều tra. Ví dụ optimizer dự đoán 20 hàng nhưng thực tế tạo ra 80.000 hàng. Kế hoạch có thể chọn Nested Loops với số lần lặp lớn hoặc cấp phát bộ nhớ không phù hợp.

Các nguyên nhân thường gặp:

- Thống kê lỗi thời hoặc chưa đủ chi tiết.
- Phân bố dữ liệu lệch (skew).
- Tương quan giữa nhiều cột không được thống kê đầy đủ.
- Giá trị tham số có độ chọn lọc khác nhau.
- Biểu thức, kiểu dữ liệu hoặc phép chuyển đổi làm khó ước lượng.
- Dữ liệu thay đổi mạnh kể từ lần cập nhật thống kê gần nhất.

Hãy xem số hàng ở từng node, không chỉ node cuối. Sai lệch ở một node sớm có thể lan truyền đến các node join, sort và aggregate phía trên.

### Hiểu Loops và thời gian ở node

Trong một số hệ quản trị, thời gian và số hàng hiển thị tại node có thể là số trung bình mỗi lần lặp hoặc số tổng hợp tùy định dạng. Khi Loops lớn, cần nhân hoặc diễn giải theo đúng quy ước của công cụ trước khi kết luận tổng chi phí. Tránh cộng trực tiếp thời gian của mọi node nếu các node cha đã bao gồm thời gian của node con.

Trong PostgreSQL, EXPLAIN ANALYZE thường hiển thị actual time theo khoảng thời gian ở mỗi node và loops. Thời gian của node cha có thể bao gồm công việc của node con. Hãy đọc theo cấu trúc cây và dùng Execution Time ở cuối để đánh giá thời gian toàn câu lệnh. Trong các công cụ khác, cách trình bày có thể khác.

### BUFFERS, IO và spill

Trong PostgreSQL, BUFFERS có thể cho biết shared/local/temp blocks hit, read, dirtied hoặc written tùy node và tùy tùy chọn. Buffer hit nghĩa là trang đã có trong shared buffers; read biểu thị cần đọc trang vào bộ đệm, nhưng không nhất thiết tương đương một lần đọc vật lý từ thiết bị vì cache của hệ điều hành có thể tham gia.

Các dấu hiệu cần kiểm tra:

- Nhiều buffer read ở node truy cập bảng hoặc chỉ mục.
- Temp read/write tăng do sort hoặc hash spill.
- Logical reads tăng mạnh dù physical reads không tăng.
- I/O timing tăng cùng hàng đợi hoặc độ trễ thiết bị.
- WAL tăng đáng kể trong truy vấn ghi.
- Số hàng bị loại bởi filter rất lớn so với số hàng trả về.

Một truy vấn có thời gian thực thi thấp trong lần chạy cache nóng có thể chậm hơn đáng kể khi dữ liệu không nằm trong cache. Hãy đo nhiều lần và ghi rõ trạng thái cache; không cố ý xóa cache production để tạo phép đo lạnh.

### Actual Time và tải đồng thời

Actual Time là thời gian đo trong bối cảnh thực thi cụ thể. Nó chịu ảnh hưởng của CPU, cache, I/O, lock wait, concurrency, scheduler và các tiến trình khác. Một lần chạy đơn lẻ trong môi trường nhàn rỗi không đại diện cho độ trễ dưới tải cao.

Nếu mục tiêu là tối ưu cho workload thực, hãy chạy phép đo với dữ liệu, tham số, concurrency và tỷ lệ đọc/ghi đại diện. Dùng p50/p95/p99 và throughput để đánh giá phân phối, đồng thời theo dõi lỗi, timeout, lock wait và tác động lên workload khác.

## Cách kiểm tra mà không gây rủi ro không cần thiết

### Dùng EXPLAIN trước khi dùng ANALYZE

Bắt đầu với EXPLAIN khi câu lệnh có thể thay đổi dữ liệu hoặc khi chưa rõ phạm vi tác động. Kế hoạch ước lượng thường đủ để phát hiện đường scan, join, sort, điều kiện không dùng chỉ mục và những bất thường rõ ràng.

Chỉ dùng EXPLAIN ANALYZE khi cần số liệu thực tế để trả lời một câu hỏi cụ thể, ví dụ:

- Ước lượng số hàng có chính xác không?
- Toán tử nào tạo nhiều hàng hơn dự kiến?
- Một lookup được lặp lại bao nhiêu lần?
- Sort hoặc hash có spill không?
- Thời gian thực tế tập trung ở node nào?
- Số trang đọc có phù hợp với giả thuyết không?

Đừng chạy ANALYZE chỉ để “xem thử” khi chưa biết câu lệnh sẽ làm gì.

### Giảm phạm vi dữ liệu một cách có ý thức

Trong môi trường thử nghiệm, có thể dùng một tập dữ liệu nhỏ hơn để xác nhận cú pháp hoặc hiểu sơ bộ kế hoạch. Tuy nhiên, thêm LIMIT hoặc thay đổi tham số có thể làm optimizer chọn một kế hoạch khác, nên kết quả không nhất thiết đại diện cho truy vấn ban đầu.

Nếu mục tiêu là đo kế hoạch của workload production, hãy giữ nguyên cấu trúc điều kiện và tham số đại diện. Có thể tạo bản sao dữ liệu đủ lớn, dùng snapshot hoặc replay tải đã ẩn dữ liệu nhạy cảm. Ghi lại mọi khác biệt so với production.

### Không chạy đồng thời quá nhiều phép đo nặng

EXPLAIN ANALYZE truy vấn lớn có thể cạnh tranh CPU, bộ nhớ, I/O và connection pool với ứng dụng. Chạy nhiều bản sao cùng lúc còn làm thay đổi chính workload đang đo. Hãy giới hạn concurrency, theo dõi hệ thống và chỉ mở rộng khi có lý do.

Nếu truy vấn bị timeout hoặc hủy, đừng lập tức chạy lại nhiều lần. Xác định nó đã bị hủy ở tầng nào, có đang rollback hoặc giải phóng tài nguyên hay không, và kiểm tra trạng thái hệ thống trước khi thử lại.

### Lưu bằng chứng đo lường

Lưu câu SQL đã chuẩn hóa, tham số đã ẩn dữ liệu nhạy cảm, phiên bản hệ quản trị, thời điểm đo, cấu hình, kế hoạch, số hàng thực tế, số vòng lặp, buffers/IO, thời gian và trạng thái tải. Không lưu thông tin xác thực hoặc dữ liệu cá nhân trong báo cáo kế hoạch.

Khi so sánh trước và sau, giữ cách đo nhất quán. Một kế hoạch có thể thay đổi sau khi thống kê được cập nhật hoặc dữ liệu tăng lên; ghi nhận thay đổi này để người khác hiểu vì sao kết quả khác.

## Những tình huống cần dừng và đánh giá lại

Dừng phép đo hoặc chuyển sang môi trường thử nghiệm khi gặp một trong các tình huống:

- Câu lệnh có thể cập nhật hoặc xóa phạm vi dữ liệu lớn hơn dự kiến.
- Chưa xác định được trigger, cascade hoặc function có tác dụng phụ.
- Transaction giữ khóa lâu hoặc làm tăng blocking trên workload quan trọng.
- CPU, I/O, memory pressure hoặc replication lag tăng đến ngưỡng vận hành.
- Vùng lưu trữ tạm, WAL/binlog hoặc transaction log tăng nhanh.
- Query timeout nhưng phiên vẫn đang dọn dẹp hoặc rollback.
- Kết quả thực tế khác xa giả định về số hàng và phạm vi tác động.
- Không có cách khôi phục dữ liệu hoặc không xác định được tác động ngoài transaction.

Nếu đã chạy nhầm DML, không tiếp tục chạy các lệnh sửa chữa theo phỏng đoán. Ghi lại câu lệnh, transaction, thời điểm, số hàng và tác động quan sát được; báo người phụ trách cơ sở dữ liệu theo quy trình sự cố để xác định khả năng khôi phục.

## Checklist trước khi chạy EXPLAIN ANALYZE

- [ ] Đã phân biệt rõ EXPLAIN với EXPLAIN ANALYZE và actual execution plan.
- [ ] Đã xác định câu lệnh là SELECT, DML, DDL hay gọi procedure/function.
- [ ] Đã kiểm tra trigger, cascade, sequence, external side effect và storage engine.
- [ ] Đã chọn môi trường thử nghiệm, bản sao hoặc replica phù hợp.
- [ ] Đã xác nhận transaction và rollback chỉ được dùng trong giới hạn có thể hoàn tác.
- [ ] Đã đặt statement timeout, lock timeout và giới hạn concurrency.
- [ ] Đã ghi baseline, tham số, workload và phạm vi dữ liệu.
- [ ] Đã có người theo dõi CPU, I/O, bộ nhớ, khóa và replication.
- [ ] Đã xác định điều kiện dừng và cách xử lý khi truy vấn bị hủy.
- [ ] Đã lưu kế hoạch và số liệu mà không làm lộ dữ liệu nhạy cảm.

## Kết luận kỹ thuật cần ghi lại

Một báo cáo EXPLAIN ANALYZE có thể kiểm chứng nên trả lời:

1. Câu lệnh và bộ tham số nào đã được chạy?
2. Công cụ nào đã thực thi câu lệnh và trên hệ quản trị/phiên bản nào?
3. Môi trường, transaction và giới hạn an toàn được sử dụng ra sao?
4. Câu lệnh có khả năng thay đổi dữ liệu hoặc tạo tác dụng phụ nào?
5. Kế hoạch thực tế khác kế hoạch ước lượng ở đâu?
6. Node nào xử lý nhiều hàng, lặp nhiều lần hoặc tiêu tốn nhiều thời gian?
7. Buffers, I/O, WAL, sort, spill và lock wait cho thấy điều gì?
8. Kết quả có đại diện cho workload mục tiêu không?
9. Thay đổi tiếp theo dựa trên giả thuyết nào và sẽ được kiểm chứng ra sao?

EXPLAIN ANALYZE là công cụ đo rất hữu ích khi người vận hành hiểu rằng nó thực thi câu lệnh. Dùng EXPLAIN để xem kế hoạch trước, chọn môi trường phù hợp, cô lập tác động, đặt giới hạn và đọc số liệu thực tế giúp tối ưu SQL và chỉ mục có căn cứ. Đặc biệt với DML, hãy xem việc đo như một lần chạy thật có khả năng thay đổi dữ liệu; chỉ thực hiện khi phạm vi, khả năng khôi phục và tác dụng phụ đã được kiểm soát.