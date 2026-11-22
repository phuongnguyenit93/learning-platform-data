# Phân biệt kế hoạch chạy nối tiếp với parallel execution

Trong Oracle Database, một câu SQL có thể được thực thi theo hai mô hình chính: chạy nối tiếp (serial execution) hoặc chạy song song (parallel execution). Điểm khác biệt cốt lõi nằm ở cách Oracle phân công công việc cho các tiến trình thực thi. Với serial execution, một tiến trình foreground của phiên làm việc xử lý các bước của câu SQL. Với parallel execution, Query Coordinator (QC) điều phối một nhóm tiến trình Parallel Execution Server (PX server) cùng xử lý các phần việc, sau đó tổng hợp kết quả.

Hai mô hình có thể dùng cùng loại phép toán như full table scan, join, sort hoặc aggregation. Vì vậy, chỉ nhìn tên phép toán chưa đủ để kết luận câu SQL chạy nối tiếp hay song song. Cần đọc cấu trúc execution plan, các toán tử PX, thông tin phân phối dữ liệu và bằng chứng thực thi thực tế.

## 1. Mô hình chạy nối tiếp (serial execution)

Trong serial execution, Oracle thực thi câu SQL bằng tiến trình server phục vụ session. Với cấu hình dedicated server thông thường, đây là một foreground server process. Tiến trình đó đọc dữ liệu, áp dụng điều kiện lọc, thực hiện join, sort, aggregation và trả kết quả cho client theo execution plan đã chọn.

Một execution plan nối tiếp vẫn có thể có nhiều operation. Các operation được tổ chức thành cây row source: operation ở phía dưới cung cấp dòng cho operation ở phía trên. Cây có nhiều nhánh không có nghĩa là Oracle đang dùng nhiều CPU song song. Trong mô hình serial, một tiến trình server xử lý các row source của câu SQL.

Ví dụ, truy vấn sau có thể được thực thi nối tiếp:

~~~sql
SELECT order_id, customer_id, order_date, total_amount
FROM   orders
WHERE  order_date >= DATE '2026-01-01'
AND    status = 'OPEN';
~~~

Một execution plan minh họa có thể có dạng:

~~~text
--------------------------------------------------------------------------------
| Id | Operation          | Name   | Rows | Bytes | Cost (%CPU)| Time         |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT   |        |      |       |  ...        |              |
|* 1 |  TABLE ACCESS FULL | ORDERS |  ... |  ...  |  ...        |              |
--------------------------------------------------------------------------------
Predicate Information:
  1 - filter("ORDER_DATE">=DATE '2026-01-01' AND "STATUS"='OPEN')
~~~

Đây chỉ là hình dạng minh họa; plan thực tế phụ thuộc dữ liệu, thống kê, index, tham số optimizer và phiên bản Oracle. Điểm cần nhận diện là plan không có các operation điều phối PX như PX COORDINATOR, PX SEND hoặc PX RECEIVE. Câu SQL được xử lý theo mô hình serial nếu cursor thực thi thực tế không khởi tạo PX server.

Serial execution thường phù hợp khi:

- Truy vấn trả về ít dòng hoặc có điều kiện lọc rất chọn lọc.
- Phần dữ liệu cần đọc nhỏ và thời gian xử lý không đủ lớn để bù chi phí khởi tạo PX server.
- Công việc có tính tuần tự cao, phụ thuộc kết quả của bước trước.
- Hệ thống đang chịu tải cao và cần hạn chế mức tiêu thụ CPU, I/O hoặc tài nguyên PX.
- Truy vấn chạy thường xuyên với thời gian ngắn, nên chi phí điều phối song song có thể lớn hơn lợi ích.

Serial không đồng nghĩa với chậm. Một index range scan nối tiếp có thể nhanh hơn rất nhiều so với full table scan song song nếu truy vấn chỉ cần một số ít dòng. Lựa chọn mô hình phải dựa trên lượng công việc thực tế và chi phí tổng thể.

## 2. Mô hình parallel execution

Parallel execution chia một câu SQL thành các phần việc có thể xử lý đồng thời. Oracle sử dụng Query Coordinator và các Parallel Execution Server để phân công, trao đổi và tổng hợp dữ liệu.

### Các thành phần chính

**Query Coordinator (QC)** là foreground process của session gửi câu SQL. QC phân tích yêu cầu thực thi song song, phân công công việc cho PX server, điều phối các giai đoạn xử lý, nhận kết quả và gửi kết quả cuối cùng về client. QC cũng có thể thực hiện một số operation nối tiếp.

**Parallel Execution Server (PX server)** là các process được Oracle cấp phát để thực hiện phần việc song song. Mỗi PX server xử lý một phần dữ liệu hoặc một phần phép toán. Một nhóm PX server có thể đọc các vùng dữ liệu khác nhau, thực hiện join, sort, aggregation hoặc gửi dữ liệu cho nhóm server khác.

**Data Flow Operation (DFO)** là một giai đoạn xử lý song song trong kế hoạch. Một câu SQL có thể có nhiều DFO, chẳng hạn giai đoạn đọc và lọc dữ liệu, giai đoạn phân phối dữ liệu theo khóa join, rồi giai đoạn tổng hợp kết quả.

**Table Queue (TQ)** là kênh trao đổi dữ liệu giữa các nhóm PX server hoặc giữa PX server với QC. Table queue không phải bảng lưu trữ nghiệp vụ. Nó là cơ chế truyền các dòng kết quả giữa những phần của execution plan.

**Granule** là đơn vị công việc Oracle giao cho PX server. Với full table scan, Oracle thường chia công việc thành các block range granule. Các server có thể nhận những dải block khác nhau. Với một số thao tác trên bảng partition, partition granule có thể được sử dụng.

### Luồng xử lý điển hình

Một truy vấn parallel scan và join có thể hoạt động theo luồng sau:

1. Client gửi SQL đến QC.
2. QC xác định plan và DOP (Degree of Parallelism), sau đó yêu cầu các PX server.
3. Các PX server đọc những granule được phân công và thực hiện các operation ở phần đầu plan.
4. Nếu bước tiếp theo cần dữ liệu được nhóm theo khóa join, các PX server gửi dòng qua table queue, thường bằng hash distribution.
5. Nhóm PX server nhận dữ liệu, thực hiện join hoặc aggregation.
6. Kết quả được gửi về QC, thường qua operation PX SEND QC.
7. QC hoàn tất phần việc của mình và trả kết quả cho client.

Sơ đồ khái quát:

~~~text
                       Client
                          |
                          v
                  Query Coordinator
                          |
                phân công công việc
                          |
             +------------+------------+
             |            |            |
             v            v            v
          PX server    PX server    PX server
          đọc phần A   đọc phần B   đọc phần C
             |            |            |
             +------------+------------+
                          |
                  Table Queue / PX SEND
                          |
             +------------+------------+
             |            |            |
             v            v            v
          PX server    PX server    PX server
          join nhóm 1  join nhóm 2  join nhóm 3
             |            |            |
             +------------+------------+
                          |
                      PX SEND QC
                          |
                          v
                  Query Coordinator
                          |
                          v
                        Client
~~~

Sơ đồ là ví dụ khái niệm. Plan thực tế có thể dùng một hoặc nhiều DFO, một hoặc hai nhóm PX server hoạt động tại một thời điểm, và có thể chứa các operation serial xen giữa các phần parallel.

## 3. Nhận diện serial và parallel trong execution plan

Không nên kết luận dựa trên một operation đơn lẻ như TABLE ACCESS FULL hoặc HASH JOIN. Những operation này có thể xuất hiện trong cả plan serial lẫn plan parallel. Hãy tìm dấu hiệu của cơ chế PX và xem thông tin phân phối dữ liệu.

### Dấu hiệu thường gặp trong plan parallel

| Operation hoặc thông tin | Ý nghĩa |
|---|---|
| PX COORDINATOR | Điểm điều phối thực thi song song của câu SQL |
| PX SEND | Gửi các dòng từ một nhóm PX server sang nơi nhận khác |
| PX RECEIVE | Nhận dòng được gửi qua table queue |
| PX BLOCK ITERATOR | Phân chia công việc đọc theo block range granule trong nhiều trường hợp |
| PX SEND QC | Gửi kết quả từ PX server về Query Coordinator |
| TQ (Table Queue) | Mã định danh kênh trao đổi dữ liệu giữa các DFO hoặc nhóm server |
| IN-OUT | Mô tả hướng truyền dữ liệu trong phần thông tin parallel của plan |
| PQ Distrib | Kiểu phân phối dòng giữa các PX server |

Một plan parallel minh họa có thể chứa cấu trúc như sau:

~~~text
--------------------------------------------------------------------------------
| Id | Operation              | Name   | TQ  | IN-OUT | PQ Distrib |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT       |        |     |        |            |
|  1 |  PX COORDINATOR        |        |     |        |            |
|  2 |   PX SEND QC (RANDOM)   | :TQ100 | Q1,1| P->S   | QC (RAND)  |
|  3 |    HASH JOIN           |        |     | PCWP   |            |
|  4 |     PX RECEIVE         |        | Q1,1| PCWP   |            |
|  5 |      PX SEND HASH      | :TQ100 | Q1,0| P->P   | HASH       |
|  6 |       PX BLOCK ITERATOR|        |     | PCWC   |            |
|  7 |        TABLE ACCESS FULL| ORDERS|     | PCWP   |            |
--------------------------------------------------------------------------------
~~~

Đây là ví dụ minh họa để nhận diện cấu trúc, không phải output cố định cho mọi phiên bản hoặc mọi truy vấn. Cách hiển thị cột TQ, IN-OUT và PQ Distrib phụ thuộc format của DBMS_XPLAN và phiên bản Oracle.

### Hiểu các kiểu phân phối PX

Các operation PX SEND cho biết Oracle chuyển dữ liệu giữa những phần việc như thế nào:

- **HASH**: phân phối dòng theo hash của một hoặc nhiều biểu thức. Các dòng có cùng khóa hash được gửi về cùng nhóm nhận. Kiểu này thường hữu ích cho hash join hoặc group by theo khóa.
- **BROADCAST**: gửi một tập dữ liệu đến tất cả PX server ở nhóm nhận. Thường phù hợp khi một phía của join nhỏ và việc nhân bản dữ liệu có chi phí chấp nhận được.
- **RANGE**: phân phối theo khoảng giá trị, có thể hỗ trợ sort hoặc operation cần dữ liệu theo thứ tự/range.
- **ROUND-ROBIN**: phân phối lần lượt để cân bằng số dòng tương đối giữa các server, không bảo đảm các dòng cùng khóa về cùng server.
- **QC (RANDOM)**: gửi kết quả từ PX server về Query Coordinator theo cơ chế phân phối thích hợp cho bước nhận kết quả.

Kiểu phân phối ảnh hưởng đến lưu lượng trao đổi, cân bằng tải và chi phí xử lý. Ví dụ, broadcast một tập dữ liệu lớn có thể làm tăng đáng kể lượng dữ liệu truyền. Hash distribution có thể tạo skew nếu một số khóa xuất hiện quá thường xuyên.

### Vì sao plan có operation PX vẫn có thể chứa bước serial?

Một câu SQL parallel không có nghĩa mọi operation đều chạy song song. Optimizer có thể chọn một phần plan chạy tại QC, chẳng hạn xử lý một tập kết quả nhỏ sau khi các PX server đã hoàn thành phần quét hoặc join. Một số operation không thể hoặc không có lợi khi phân chia cũng có thể chạy serial.

Do đó, khi đọc plan, cần xác định ranh giới giữa các DFO, nơi dữ liệu được gửi/nhận và operation nào được thực hiện ở QC. Sự hiện diện của PX COORDINATOR cho thấy plan có cơ chế điều phối song song, nhưng không có nghĩa QC hoàn toàn không làm việc xử lý dữ liệu.

## 4. Degree of Parallelism (DOP)

DOP là mức độ song song Oracle yêu cầu hoặc lựa chọn cho một operation hay câu SQL. Ví dụ DOP 4 thường có nghĩa Oracle sử dụng bốn PX server trong mỗi server set cho operation tương ứng. Trong một số plan có pipeline producer-consumer, hai server set có thể cùng hoạt động; tổng số PX server đang dùng vì thế có thể lớn hơn DOP. Cách cấp phát cụ thể phụ thuộc plan, tài nguyên và chính sách parallel execution.

DOP không phải số CPU core được bảo đảm dành riêng cho câu SQL. Nó là mức song song logic mà Oracle dùng để lập kế hoạch và cấp phát PX server. Số PX server thực tế có thể thấp hơn mức yêu cầu do giới hạn tài nguyên, chính sách, statement queuing hoặc tình trạng hệ thống.

### DOP được xác định từ đâu?

Oracle có thể lấy mức song song từ nhiều nguồn:

- Thuộc tính PARALLEL của table hoặc index.
- SQL hint PARALLEL.
- Chính sách PARALLEL_DEGREE_POLICY và các tham số liên quan.
- Lệnh ALTER SESSION FORCE PARALLEL QUERY.
- Các giới hạn tài nguyên và cấu hình của database hoặc Resource Manager.

Ví dụ, đặt thuộc tính song song cho bảng:

~~~sql
ALTER TABLE sales PARALLEL 8;
~~~

Đặt lại bảng về NOPARALLEL:

~~~sql
ALTER TABLE sales NOPARALLEL;
~~~

Yêu cầu DOP cho một câu SQL bằng hint:

~~~sql
SELECT /*+ PARALLEL(s, 8) */
       s.product_id,
       SUM(s.amount)
FROM   sales s
WHERE  s.sale_date >= DATE '2026-01-01'
GROUP BY s.product_id;
~~~

Tên alias trong hint phải khớp alias được khai báo trong câu SQL. Hint là chỉ dẫn cho optimizer; không nên xem nó như cam kết rằng database chắc chắn cấp đúng số PX server yêu cầu.

Có thể yêu cầu parallel query ở cấp session:

~~~sql
ALTER SESSION FORCE PARALLEL QUERY PARALLEL 8;
~~~

Và tắt chế độ ép parallel query cho session:

~~~sql
ALTER SESSION DISABLE PARALLEL QUERY;
~~~

Cách Oracle chọn DOP còn phụ thuộc PARALLEL_DEGREE_POLICY. Với chính sách tự động, optimizer có thể ước lượng thời gian xử lý và chọn DOP; với chính sách thủ công, thuộc tính object hoặc hint thường đóng vai trò trực tiếp hơn. Giá trị mặc định và hành vi chi tiết có thể khác theo phiên bản, cấu hình và môi trường, nên cần xem tham số thực tế thay vì áp dụng một con số mặc định cho mọi hệ thống.

### DOP yêu cầu và DOP thực tế

Cần phân biệt:

- **Requested DOP**: mức song song mà plan hoặc cấu hình yêu cầu.
- **Actual DOP**: mức song song Oracle thực sự cấp cho câu SQL.

Actual DOP có thể bị giảm (downgrade) khi không đủ PX server hoặc tài nguyên. Câu SQL cũng có thể phải chờ trong parallel statement queue trước khi được cấp tài nguyên. Trong một số trường hợp, câu SQL có thể chạy với DOP thấp hơn hoặc chuyển sang serial tùy chính sách và điều kiện thực thi.

Khi điều tra hiệu năng, không nên chỉ nhìn hint PARALLEL hoặc thuộc tính bảng để kết luận truy vấn đã chạy với DOP đó. Hãy kiểm tra session PX trong lúc chạy, execution plan thực tế và số liệu runtime.

## 5. So sánh serial execution và parallel execution

| Tiêu chí | Serial execution | Parallel execution |
|---|---|---|
| Tiến trình thực thi | Thường một foreground server process của session xử lý câu SQL | QC điều phối một hoặc nhiều nhóm PX server |
| Cách chia công việc | Một tiến trình xử lý các row source theo plan | Công việc được chia thành granule hoặc phần việc có thể chạy đồng thời |
| Giao tiếp giữa worker | Không có trao đổi PX giữa các PX server | Có thể có table queue và PX SEND/RECEIVE |
| Overhead khởi tạo | Thấp hơn, không cần cấp phát nhóm PX server | Có chi phí khởi tạo, điều phối và trao đổi dữ liệu |
| Tài nguyên | Thường giới hạn hơn ở một process/session | Có thể dùng nhiều CPU, I/O, bộ nhớ và PX server cùng lúc |
| Truy vấn phù hợp | Truy vấn nhỏ, chọn lọc cao, thời gian ngắn | Scan, join, sort, aggregation hoặc xử lý dữ liệu lớn có thể chia nhỏ |
| Rủi ro chính | Một process có thể trở thành nút thắt khi công việc lớn | PX contention, data skew, trao đổi dữ liệu lớn, spill ra TEMP và ảnh hưởng workload khác |
| Kết quả | Cùng ngữ nghĩa SQL và kết quả logic | Cùng ngữ nghĩa SQL và kết quả logic; thứ tự dòng chỉ được bảo đảm khi SQL có ORDER BY |

Parallel execution có thể giảm elapsed time bằng cách dùng nhiều process cùng xử lý. Tuy nhiên, tổng CPU time có thể tăng vì nhiều process cùng làm việc và phải trao đổi dữ liệu. Ví dụ, một câu SQL serial mất 40 giây CPU có thể hoàn tất trong 12 giây elapsed khi chạy parallel, nhưng tổng CPU time có thể cao hơn 40 giây do overhead. Đây chỉ là ví dụ minh họa, không phải tỷ lệ tăng tốc cố định.

Một truy vấn trả về một triệu dòng cho client cũng có thể không tăng tốc tương ứng với DOP vì QC vẫn phải nhận và gửi dữ liệu về client. Khi client fetch chậm hoặc mạng là nút thắt, tăng DOP có thể không cải thiện thời gian tổng thể.

## 6. Khi nào nên dùng parallel execution?

Parallel execution thường có lợi khi khối lượng công việc đủ lớn và có thể chia thành nhiều phần tương đối độc lập.

### Trường hợp thường có lợi

- Quét bảng rất lớn hoặc nhiều partition.
- Join hai tập dữ liệu lớn, đặc biệt khi có thể phân phối theo khóa hiệu quả.
- Aggregation, sort hoặc xử lý dữ liệu lớn.
- CTAS, tạo index hoặc một số thao tác DDL có hỗ trợ parallel.
- Batch processing, data warehouse, báo cáo hoặc ETL có cửa sổ xử lý rõ ràng.
- Công việc có thể sử dụng tài nguyên dự phòng mà không ảnh hưởng đáng kể đến workload tương tác.

### Trường hợp nên thận trọng

- Truy vấn OLTP ngắn, chỉ đọc vài dòng qua index.
- Nhiều câu SQL nhỏ chạy đồng thời với tần suất cao.
- Hệ thống đang thiếu CPU, I/O bandwidth hoặc bộ nhớ.
- Join tạo ra tập dữ liệu trung gian lớn hoặc phân phối dữ liệu bị skew.
- Truy vấn cần gửi lượng kết quả rất lớn về client.
- Công việc bị giới hạn bởi một bước serial, một remote source hoặc một dịch vụ bên ngoài.

Không nên bật parallel cho mọi bảng chỉ để tăng tốc. DOP quá cao có thể khiến một truy vấn chiếm nhiều PX server, làm các câu SQL khác phải chờ, tăng context switching, I/O và áp lực TEMP. Tăng DOP cũng không khắc phục được execution plan có cardinality estimate sai hoặc điều kiện lọc không phù hợp.

## 7. Parallel Query, Parallel DML và Parallel DDL

Cần phân biệt ba loại hoạt động:

**Parallel Query** cho phép Oracle xử lý phần đọc và tính toán của câu SELECT bằng PX server. Đây là trường hợp thường gặp nhất khi phân biệt plan serial với parallel.

**Parallel DML** cho phép các thao tác INSERT, UPDATE, DELETE hoặc MERGE được thực hiện song song khi đáp ứng điều kiện. Parallel DML có thể cần được bật trong session:

~~~sql
ALTER SESSION ENABLE PARALLEL DML;
~~~

Sau đó, câu DML có thể dùng hint hoặc thuộc tính phù hợp, ví dụ:

~~~sql
INSERT /*+ APPEND PARALLEL(target_table, 4) */
INTO target_table
SELECT /*+ PARALLEL(source_table, 4) */
       ...
FROM source_table;
~~~

Khả năng parallel DML phụ thuộc loại thao tác, cấu trúc bảng, ràng buộc, trigger, index và các giới hạn của Oracle. Không phải mọi DML đều được thực thi song song chỉ vì bảng có thuộc tính PARALLEL. Một số giới hạn còn liên quan đến việc truy cập lại cùng bảng trong cùng transaction sau parallel DML.

**Parallel DDL** áp dụng cho những thao tác DDL hỗ trợ parallel, chẳng hạn một số thao tác tạo index, CTAS hoặc xử lý partition. Hành vi cụ thể phụ thuộc loại DDL và phiên bản. Không nên suy ra rằng mọi lệnh DDL đều chạy song song khi bảng được đặt PARALLEL.

Việc kiểm tra plan SELECT không đủ để chứng minh một lệnh DML hoặc DDL đã thực sự dùng parallel execution. Cần xem trạng thái session, thuộc tính lệnh, plan và công cụ giám sát phù hợp cho đúng loại thao tác.

## 8. Kiểm tra plan và runtime để xác định mô hình thực thi

### Xem execution plan của cursor

Dùng DBMS_XPLAN.DISPLAY_CURSOR để xem plan của cursor đã thực thi:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => 'sql_id_here',
    format => 'ALL'
  )
);
~~~

Nếu cần xem thống kê thực thi theo operation, chạy truy vấn thử nghiệm với GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       product_id,
       SUM(amount)
FROM   sales
WHERE  sale_date >= DATE '2026-01-01'
GROUP BY product_id;
~~~

Sau đó:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => 'sql_id_here',
    format => 'ALLSTATS LAST'
  )
);
~~~

Đối với plan parallel, hãy xem phần thông tin parallel trong output, gồm các operation PX, table queue, IN-OUT và PQ Distrib nếu format/phiên bản hiển thị. ALLSTATS LAST cho biết số liệu thực thi của lần chạy gần nhất khi cursor đã thu thập plan statistics. Cần đảm bảo đang xem đúng SQL_ID, child cursor và lần thực thi cần phân tích.

### Theo dõi PX server trong lúc SQL chạy

View V$PX_SESSION cho biết session nào đang tham gia parallel execution và liên hệ giữa PX server với QC. Ví dụ:

~~~sql
SELECT sid,
       serial#,
       qcsid,
       qcinst_id,
       server_group,
       server_set,
       server#,
       degree,
       req_degree
FROM   v$px_session
ORDER BY qcsid, server_group, server_set, server#;
~~~

Các cột quan trọng:

- **QCSID**: SID của Query Coordinator.
- **QCINST_ID**: instance chứa QC trong môi trường RAC.
- **SERVER_GROUP** và **SERVER_SET**: nhóm và tập PX server.
- **SERVER#**: số thứ tự PX server trong nhóm.
- **DEGREE**: DOP được cấp cho nhóm.
- **REQ_DEGREE**: DOP được yêu cầu.

Nếu truy vấn đã kết thúc, các PX session có thể biến mất khỏi view rất nhanh. Vì vậy, hãy lấy mẫu trong lúc câu SQL đang chạy. Trong RAC, dùng GV$PX_SESSION để quan sát trên nhiều instance và bổ sung INST_ID khi cần.

### Kiểm tra lượng dữ liệu qua table queue

V$PQ_TQSTAT cung cấp thống kê table queue của parallel execution gần nhất trong session. Có thể xem số dòng và số byte theo TQ và loại server:

~~~sql
SELECT dfo_number,
       tq_id,
       server_type,
       SUM(num_rows) AS total_rows,
       SUM(bytes)    AS total_bytes
FROM   v$pq_tqstat
GROUP BY dfo_number, tq_id, server_type
ORDER BY dfo_number, tq_id, server_type;
~~~

Nếu số dòng hoặc số byte giữa các PX server chênh lệch lớn, có thể có data skew. Khi đó, một số server hoàn thành sớm nhưng server nhận phần dữ liệu lớn vẫn tiếp tục xử lý, làm tổng thời gian bị chi phối bởi worker chậm nhất. V$PQ_TQSTAT phản ánh lần parallel execution gần nhất trong session, vì vậy cần truy vấn đúng session và thực hiện kiểm tra ngay sau câu SQL cần phân tích.

### SQL Monitor và các nguồn runtime khác

Khi tính năng và quyền sử dụng phù hợp, Real-Time SQL Monitoring giúp theo dõi tiến độ, thời gian, CPU, I/O và hoạt động của từng PX server trong một lần thực thi. Có thể dùng SQL Monitor khi cần quan sát một SQL dài hoặc có nhiều DFO. Cần tuân thủ yêu cầu cấp phép Oracle của môi trường đối với các tính năng Diagnostic/Tuning Pack liên quan.

Ngoài ra, có thể kết hợp AWR/ASH (nếu được cấp phép), session wait, SQL statistics và số liệu hệ điều hành. Chỉ xem execution plan tĩnh sẽ không cho biết đầy đủ DOP thực tế, thời gian chờ cấp PX server, độ lệch dữ liệu hoặc mức độ cạnh tranh tài nguyên.

## 9. Các vấn đề thường gặp khi chạy parallel

### PX server không được cấp đủ

Plan có thể yêu cầu một DOP nhưng hệ thống không có đủ PX server khả dụng. Oracle có thể giảm DOP, xếp câu SQL vào hàng đợi hoặc áp dụng hành vi theo chính sách cấu hình. Kiểm tra actual DOP, Resource Manager, giới hạn PX server, mức tải và các câu SQL song song đang chạy cùng lúc.

### Data skew

Nếu một giá trị join key xuất hiện quá nhiều, hash distribution có thể dồn phần lớn dòng vào một hoặc vài PX server. Các server còn lại hoàn thành sớm trong khi một server phải xử lý nhiều dữ liệu hơn. Hãy kiểm tra phân bố khóa, số dòng mỗi worker và các table queue. Giải pháp có thể là điều chỉnh cách phân phối, thay đổi chiến lược join, xử lý dữ liệu lệch hoặc cải thiện mô hình dữ liệu; không nên chỉ tăng DOP.

### Chi phí trao đổi dữ liệu lớn

PX SEND và PX RECEIVE truyền dữ liệu giữa các process. Nếu intermediate result quá lớn, chi phí truyền có thể lớn hơn lợi ích chia nhỏ công việc. Hãy xem PQ Distrib, số byte qua table queue và vị trí có thể lọc dữ liệu sớm hơn. Một bộ lọc có tính chọn lọc cao trước khi redistribute thường giúp giảm lượng dữ liệu cần trao đổi.

### QC trở thành nút thắt

Một số plan có phần xử lý cuối cùng tại QC hoặc phải gửi lượng dữ liệu lớn về client. Khi đó, nhiều PX server không làm bước cuối nhanh hơn. Hãy kiểm tra operation chạy ở QC, số dòng đầu ra và tốc độ fetch của client.

### Tràn bộ nhớ ra TEMP

Sort hoặc hash operation song song có thể cần nhiều bộ nhớ. Khi không đủ PGA, operation có thể spill ra TEMP, làm tăng I/O và elapsed time. Tăng DOP đôi khi làm tổng nhu cầu bộ nhớ tăng thêm. Cần kiểm tra workarea, TEMP usage, wait events và giới hạn bộ nhớ của hệ thống.

### Tác động đến workload khác

Parallel query có thể tiêu thụ CPU, I/O và PX server mà các session khác cần dùng. Nếu nhiều báo cáo lớn chạy đồng thời, hệ thống có thể giảm throughput tổng thể dù từng câu SQL riêng lẻ chạy nhanh hơn. Cân nhắc Resource Manager, parallel statement queuing, giới hạn DOP và lịch chạy batch để kiểm soát cạnh tranh.

## 10. Quy trình phân tích một câu SQL nghi ngờ chạy serial hoặc parallel

1. **Xác định đúng lần thực thi.** Lấy SQL_ID, child number, session và thời điểm chạy. Không dựa vào một plan cũ có thể thuộc lần parse khác.
2. **Xem plan thực tế.** Dùng DBMS_XPLAN.DISPLAY_CURSOR. Tìm PX COORDINATOR, PX SEND, PX RECEIVE, PX BLOCK ITERATOR, TQ và thông tin IN-OUT/PQ Distrib.
3. **Kiểm tra DOP.** So sánh requested DOP với actual DOP. Xem V$PX_SESSION trong lúc SQL đang chạy.
4. **Đánh giá phân phối dữ liệu.** Kiểm tra table queue, số dòng/byte giữa các worker và dấu hiệu skew.
5. **Tìm nút thắt.** Phân biệt thời gian CPU, I/O, chờ PX, trao đổi dữ liệu, TEMP, QC và client fetch.
6. **So sánh với serial khi cần.** Chạy thử cùng SQL, cùng bind value và dữ liệu tương đương dưới điều kiện tải có thể so sánh. Đo elapsed time, CPU time, logical reads, physical reads và tài nguyên tiêu thụ.
7. **Điều chỉnh có kiểm soát.** Chỉ thay đổi DOP, hint, thuộc tính object hoặc chính sách parallel sau khi đã xác định nguyên nhân. Theo dõi tác động đến cả SQL mục tiêu và workload chung.

Khi so sánh serial với parallel, hãy giữ các điều kiện thử nghiệm nhất quán: cùng bind value, cùng dữ liệu, cùng trạng thái cache nếu có thể, cùng mức tải và cùng tiêu chí đo. Một lần chạy đầu có thể chịu ảnh hưởng của physical read, parse hoặc warm-up nên không đại diện đầy đủ. Cũng cần phân biệt elapsed time của client với CPU time tổng của các process.

## 11. Những hiểu lầm thường gặp

- **Thấy TABLE ACCESS FULL là kết luận parallel.** Full table scan có thể chạy serial hoặc parallel. Cần xem các operation PX và runtime.
- **Thấy DOP 8 nghĩa là chỉ có tám process.** DOP là mức song song logic; một plan có thể dùng hai server set và tổng số PX server có thể lớn hơn DOP.
- **Có hint PARALLEL là chắc chắn chạy parallel.** Hint là chỉ dẫn cho optimizer; tài nguyên và chính sách thực thi vẫn ảnh hưởng kết quả thực tế.
- **Parallel luôn nhanh hơn serial.** Overhead, data skew, trao đổi dữ liệu, QC, TEMP và cạnh tranh tài nguyên có thể làm parallel chậm hơn.
- **Plan có PX nghĩa mọi bước đều song song.** Một plan có thể trộn operation serial và parallel.
- **Serial plan có nhiều operation nghĩa là nhiều process.** Số operation trong cây plan không thể hiện số process thực thi.
- **Parallel query đồng nghĩa parallel DML.** Đọc song song và thay đổi dữ liệu song song là hai cơ chế cần phân biệt.
- **Tăng DOP là cách xử lý mọi vấn đề hiệu năng.** Nếu bottleneck nằm ở I/O, skew, network, QC, client hoặc plan không phù hợp, tăng DOP có thể không giúp và còn làm tải nặng hơn.

## 12. Checklist đọc execution plan

Khi nhận một execution plan, hãy lần lượt xác định:

- [ ] Có operation PX COORDINATOR hay các operation PX SEND/PX RECEIVE không?
- [ ] Có table queue và thông tin IN-OUT/PQ Distrib không?
- [ ] Operation nào chạy trong QC và operation nào chạy ở PX server?
- [ ] Requested DOP và actual DOP là bao nhiêu?
- [ ] Plan có bao nhiêu DFO hoặc giai đoạn trao đổi dữ liệu?
- [ ] Dữ liệu được phân phối bằng HASH, BROADCAST, RANGE hay cơ chế khác?
- [ ] Số dòng và số byte giữa các PX server có cân bằng không?
- [ ] Có spill ra TEMP, chờ PX server hoặc dấu hiệu QC bottleneck không?
- [ ] Elapsed time giảm có đi kèm mức tiêu thụ CPU/I/O hợp lý không?
- [ ] Kết quả thử serial và parallel được so sánh trong điều kiện tương đương chưa?

Phân biệt đúng serial execution và parallel execution giúp đọc execution plan chính xác hơn và chọn cách tối ưu phù hợp với workload. Hãy kết hợp dấu hiệu PX trong plan với DOP thực tế, số liệu runtime và tác động đến toàn hệ thống trước khi quyết định sử dụng parallel.
