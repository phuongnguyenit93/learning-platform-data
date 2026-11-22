# Ảnh hưởng của ORDER BY, DISTINCT, phép nhóm và dữ liệu tràn TEMP

Trong Oracle Database, các thao tác ORDER BY, DISTINCT và GROUP BY có thể cần xử lý một lượng lớn hàng trước khi trả kết quả. Khi dữ liệu cần sắp xếp, loại trùng hoặc gom nhóm vượt quá bộ nhớ workarea được cấp trong PGA, Oracle có thể ghi dữ liệu trung gian ra TEMP tablespace rồi đọc lại để hoàn tất thao tác. Hiện tượng này thường được gọi là **spill to TEMP** hoặc tràn TEMP.

TEMP không phải dấu hiệu chắc chắn rằng câu SQL viết sai. Một phép sort lớn có thể là yêu cầu tất yếu của nghiệp vụ, và việc dùng TEMP có thể là cách Oracle hoàn thành nó an toàn. Tuy nhiên, lượng TEMP lớn, nhiều lượt xử lý hoặc I/O cao có thể làm truy vấn chậm, gây áp lực lên storage và ảnh hưởng các session khác. Muốn tối ưu, cần hiểu từng phép toán tạo ra bao nhiêu hàng, cần giữ bao nhiêu dữ liệu trung gian và Oracle đang xử lý workarea ở chế độ nào.

## 1. ORDER BY, DISTINCT và GROUP BY thực hiện công việc gì?

Ba mệnh đề thường xuất hiện trong truy vấn phân tích nhưng có mục đích khác nhau:

| Mệnh đề | Mục đích | Operation có thể thấy trong execution plan |
|---|---|---|
| ORDER BY | Sắp xếp hàng theo thứ tự được yêu cầu | SORT ORDER BY, SORT ORDER BY STOPKEY hoặc có thể không cần sort nếu access path đã cung cấp thứ tự phù hợp |
| DISTINCT | Loại bỏ các hàng trùng nhau theo danh sách biểu thức được chọn | SORT UNIQUE hoặc HASH UNIQUE |
| GROUP BY | Gom các hàng có cùng giá trị khóa nhóm để tính aggregate | HASH GROUP BY, SORT GROUP BY hoặc biến thể khác |

Các thao tác này có thể tạo workarea trong PGA. Nếu dữ liệu trung gian không vừa bộ nhớ, Oracle có thể dùng TEMP tablespace để lưu các phần dữ liệu và tiếp tục xử lý.

Một điểm quan trọng về ngữ nghĩa SQL:

- ORDER BY là cách chuẩn để yêu cầu thứ tự kết quả cuối cùng.
- DISTINCT không bảo đảm kết quả có thứ tự.
- GROUP BY cũng không bảo đảm thứ tự kết quả, kể cả khi execution plan có operation mang tên SORT GROUP BY.

Nếu ứng dụng cần thứ tự xác định, luôn khai báo ORDER BY ở câu truy vấn ngoài cùng.

## 2. ORDER BY và chi phí sắp xếp

Khi câu SQL có ORDER BY, Oracle phải cung cấp kết quả theo thứ tự đã yêu cầu. Nếu đường truy cập dữ liệu không tạo ra thứ tự phù hợp, optimizer có thể chọn operation SORT ORDER BY.

Ví dụ:

~~~sql
SELECT order_id,
       order_date,
       customer_id,
       total_amount
  FROM orders
 WHERE order_date >= TIMESTAMP '2026-01-01 00:00:00'
 ORDER BY total_amount DESC;
~~~

Nếu Oracle không thể lấy dữ liệu theo thứ tự total_amount từ một access path thích hợp, nó có thể phải sort các hàng thỏa điều kiện. Khối lượng sort phụ thuộc vào:

- Số hàng sau khi áp dụng điều kiện lọc.
- Độ rộng của mỗi hàng cần giữ để sắp xếp.
- Số biểu thức trong ORDER BY và kiểu dữ liệu của chúng.
- Khả năng dùng index hoặc access path đã có thứ tự.
- Bộ nhớ workarea được cấp cho operation.

### ORDER BY có thể tránh sort bằng index không?

Trong một số trường hợp, Oracle có thể dùng index để đọc hàng theo thứ tự cần thiết và loại bỏ operation SORT ORDER BY. Ví dụ:

~~~sql
CREATE INDEX orders_status_amount_ix
    ON orders(status, total_amount DESC);

SELECT order_id,
       total_amount
  FROM orders
 WHERE status = 'PAID'
 ORDER BY total_amount DESC;
~~~

Với điều kiện bằng trên cột dẫn đầu status, index có thể đọc phạm vi PAID theo thứ tự total_amount giảm dần và giúp tránh một operation sort riêng nếu optimizer thấy access path đó có chi phí phù hợp. Tuy nhiên, chỉ tạo index có các cột trong ORDER BY không bảo đảm Oracle sẽ dùng index để tránh sort.

Optimizer phải cân nhắc:

- Cột dẫn đầu của index và điều kiện lọc.
- Thứ tự ASC/DESC của các cột.
- Biểu thức trong ORDER BY có khớp với index hay không.
- Số hàng cần đọc và chi phí table access.
- Các phép join hoặc phép biến đổi khác có làm mất thứ tự hay không.

Một index có thể giúp tránh sort nhưng lại buộc Oracle đọc rất nhiều block hoặc truy cập bảng theo từng rowid. Với truy vấn trả về phần lớn bảng, full table scan rồi sort đôi khi rẻ hơn.

### Top-N và STOPKEY

Nếu chỉ cần một số hàng đầu tiên, hãy thể hiện giới hạn ngay trong SQL:

~~~sql
SELECT order_id,
       total_amount
  FROM orders
 ORDER BY total_amount DESC
 FETCH FIRST 20 ROWS ONLY;
~~~

Oracle có thể dùng các chiến lược top-N như SORT ORDER BY STOPKEY để chỉ giữ phần cần thiết thay vì sắp xếp toàn bộ kết quả theo cách thông thường. Nếu có index phù hợp, optimizer cũng có thể đọc các giá trị lớn nhất theo thứ tự index.

Giới hạn hàng có thể giảm công việc, nhưng không phải lúc nào cũng loại bỏ hoàn toàn sort. Nếu có thêm JOIN, DISTINCT hoặc GROUP BY trước khi giới hạn, Oracle vẫn phải xử lý đủ dữ liệu để xác định đúng 20 hàng cuối cùng.

## 3. DISTINCT và chi phí loại bỏ hàng trùng

DISTINCT trả về các tổ hợp giá trị duy nhất của danh sách biểu thức SELECT:

~~~sql
SELECT DISTINCT customer_id
  FROM orders;
~~~

Oracle cần xác định các customer_id trùng nhau. Tùy dữ liệu và chi phí, optimizer có thể chọn:

- **SORT UNIQUE:** sắp xếp dữ liệu rồi loại các giá trị trùng liền kề.
- **HASH UNIQUE:** dùng cấu trúc băm để nhận diện các giá trị đã xuất hiện.

Hai cách đều có thể cần bộ nhớ. Nếu tập dữ liệu lớn hơn workarea được cấp, operation có thể spill sang TEMP.

### DISTINCT trên nhiều cột

~~~sql
SELECT DISTINCT customer_id,
                status,
                TRUNC(order_date)
  FROM orders;
~~~

Oracle phải loại trùng theo toàn bộ bộ ba customer_id, status và ngày. Số lượng cột, độ rộng dữ liệu và số tổ hợp khác nhau đều ảnh hưởng lượng bộ nhớ và CPU cần dùng.

DISTINCT trên nhiều cột rộng hoặc dữ liệu lớn có thể tốn kém hơn việc loại trùng một khóa nhỏ. Hãy chỉ chọn các cột thật sự cần thiết.

### DISTINCT không phải công cụ sửa JOIN sai

Một lỗi thường gặp là JOIN tạo ra nhiều hàng ngoài dự kiến, sau đó thêm DISTINCT để che số hàng trùng:

~~~sql
SELECT DISTINCT c.customer_id,
                c.customer_name
  FROM customers c
  JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

Nếu mục tiêu chỉ là lấy khách hàng có ít nhất một đơn hàng, EXISTS thể hiện ý định rõ hơn:

~~~sql
SELECT c.customer_id,
       c.customer_name
  FROM customers c
 WHERE EXISTS (
       SELECT 1
         FROM orders o
        WHERE o.customer_id = c.customer_id
 );
~~~

EXISTS cho phép Oracle dùng semi-join hoặc một chiến lược tương đương, không cần tạo toàn bộ hàng join rồi mới loại trùng. Không phải mọi truy vấn DISTINCT đều thay được bằng EXISTS; chỉ dùng khi ngữ nghĩa thực sự là kiểm tra sự tồn tại.

DISTINCT cũng không bảo đảm thứ tự kết quả. Nếu cần sắp xếp:

~~~sql
SELECT DISTINCT customer_id
  FROM orders
 ORDER BY customer_id;
~~~

## 4. GROUP BY và các chiến lược aggregate

GROUP BY gom các hàng theo một hoặc nhiều biểu thức, rồi tính COUNT, SUM, AVG, MIN, MAX hoặc các aggregate khác.

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
  FROM employees
 GROUP BY department_id;
~~~

Oracle thường có thể dùng hai chiến lược chính:

### HASH GROUP BY

Oracle tạo cấu trúc hash theo khóa nhóm, lưu trạng thái aggregate cho mỗi nhóm. Khi đọc một hàng, nó tìm nhóm tương ứng và cập nhật trạng thái COUNT, SUM hoặc các phép tính khác.

HASH GROUP BY thường phù hợp khi không cần kết quả theo thứ tự khóa nhóm. Nó có thể tránh sort toàn bộ dữ liệu đầu vào, nhưng vẫn cần bộ nhớ cho các nhóm. Nếu có quá nhiều nhóm hoặc trạng thái aggregate lớn, operation có thể spill sang TEMP.

### SORT GROUP BY

Oracle sắp xếp dữ liệu theo khóa nhóm rồi xử lý các hàng cùng nhóm liên tiếp. Cách này cần sort nếu đầu vào chưa có thứ tự phù hợp. Khi dữ liệu lớn, phần sort có thể dùng TEMP.

Optimizer chọn chiến lược dựa trên cardinality, thống kê, chi phí và các yếu tố khác. Không nên ép HASH GROUP BY hoặc SORT GROUP BY chỉ vì một chiến lược có vẻ tốt hơn trên một ví dụ nhỏ.

### GROUP BY không tự sắp xếp kết quả

Ví dụ sau không bảo đảm kết quả theo department_id:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
  FROM employees
 GROUP BY department_id;
~~~

Nếu cần thứ tự:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
  FROM employees
 GROUP BY department_id
 ORDER BY department_id;
~~~

Kể cả khi execution plan hiện SORT GROUP BY, không nên dựa vào thứ tự nội bộ đó như một hợp đồng SQL. Chỉ ORDER BY mới bảo đảm thứ tự hiển thị.

## 5. Vì sao ORDER BY, DISTINCT và GROUP BY có thể tràn TEMP?

Oracle thực hiện sort và hash bằng các workarea. Workarea thường sử dụng PGA của process thực thi. Nếu dữ liệu cần xử lý vừa bộ nhớ được cấp, operation có thể chạy hoàn toàn trong bộ nhớ. Nếu không vừa, Oracle ghi các phần dữ liệu trung gian ra TEMP tablespace.

Ví dụ một truy vấn:

~~~sql
SELECT DISTINCT customer_id,
                status
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 ORDER BY customer_id,
          status;
~~~

Truy vấn có thể phải:

1. Đọc các hàng thỏa điều kiện ngày.
2. Loại bỏ các tổ hợp customer_id/status trùng nhau.
3. Sắp xếp tập kết quả theo customer_id/status.

Nếu tập dữ liệu lớn, cả bước unique và sort có thể cần workarea. Oracle có thể chọn một plan kết hợp hoặc tối ưu hóa để chia sẻ công việc, nhưng không thể giả định chỉ có một lần sort.

TEMP tablespace cung cấp vùng lưu trữ tạm cho các operation cần dữ liệu trung gian vượt quá bộ nhớ. Nó thường được dùng cho:

- Sort và merge các run đã sắp xếp.
- Hash join hoặc hash aggregate cần partition dữ liệu.
- DISTINCT và một số phép loại trùng.
- Một số phép biến đổi truy vấn cần lưu kết quả trung gian.
- Temporary table và các thao tác khác cần segment tạm.

TEMP không phải bộ nhớ RAM. Khi operation phải ghi/đọc TEMP, Oracle phát sinh I/O trên tempfile. Nếu storage chậm hoặc nhiều session cùng dùng TEMP, thời gian truy vấn có thể tăng đáng kể.

## 6. Ba chế độ thực thi workarea

Workarea cho sort/hash có thể chạy theo các chế độ phổ biến:

| Chế độ | Cách hoạt động | Hệ quả |
|---|---|---|
| Optimal | Dữ liệu xử lý vừa bộ nhớ được cấp | Không cần spill dữ liệu của operation ra TEMP |
| One-pass | Dữ liệu được chia thành phần; cần ghi/đọc TEMP trong một lượt xử lý bổ sung | Có TEMP I/O nhưng thường ít hơn multi-pass |
| Multi-pass | Dữ liệu phải được chia và xử lý qua nhiều lượt | Có thể tạo nhiều TEMP I/O và làm truy vấn chậm đáng kể |

Đối với sort, Oracle có thể tạo các sorted runs trong bộ nhớ, ghi chúng ra TEMP rồi merge. Với hash operation, dữ liệu có thể được partition để xử lý từng phần.

Chế độ thực tế phụ thuộc kích thước dữ liệu, bộ nhớ workarea được cấp, số operation chạy đồng thời và chính sách quản lý PGA. Một truy vấn chạy optimal trong môi trường ít tải có thể chuyển sang one-pass hoặc multi-pass khi nhiều session cùng chạy báo cáo.

## 7. PGA, WORKAREA_SIZE_POLICY và TEMP

PGA là vùng bộ nhớ riêng của các server process, dùng cho sort, hash, session state và các hoạt động xử lý khác. Với quản lý tự động, các tham số thường cần hiểu gồm:

- **PGA_AGGREGATE_TARGET:** mục tiêu bộ nhớ PGA tổng thể cho instance; Oracle dùng nó để điều chỉnh bộ nhớ cấp cho workarea trong chế độ tự động.
- **PGA_AGGREGATE_LIMIT:** giới hạn cứng tổng PGA của instance; vượt giới hạn có thể dẫn đến việc Oracle hủy một số call/session theo quy tắc của phiên bản.
- **WORKAREA_SIZE_POLICY:** AUTO cho phép Oracle tự quản lý workarea; MANUAL dùng các tham số workarea thủ công.
- **TEMP tablespace:** vùng lưu dữ liệu trung gian khi operation không thể xử lý hoàn toàn trong bộ nhớ.

Trong nhiều hệ thống, WORKAREA_SIZE_POLICY được đặt AUTO. Khi đó không nên tự đặt SORT_AREA_SIZE hoặc HASH_AREA_SIZE theo cách thủ công nếu không có lý do và hiểu rõ cấu hình hiện tại.

PGA_AGGREGATE_TARGET là mục tiêu ở cấp instance, không phải lượng bộ nhớ được cấp cố định cho mỗi câu SQL. Nhiều session và nhiều operation có thể cạnh tranh bộ nhớ. Tăng target có thể giảm spill trong một số workload nhưng cũng làm tăng áp lực RAM và có thể ảnh hưởng các process khác.

Không nên chỉ tăng TEMP để giải quyết mọi truy vấn chậm. TEMP lớn hơn có thể giúp tránh lỗi hết không gian tạm, nhưng nếu sort/hash phải ghi hàng trăm GB thì truy vấn vẫn có thể rất chậm.

## 8. Nhận biết operation dùng TEMP trong execution plan

Có thể thu thập runtime statistics bằng hint GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 GROUP BY customer_id
 ORDER BY customer_id;
~~~

Sau khi chạy hết câu lệnh và fetch toàn bộ kết quả, xem execution plan:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Tùy phiên bản và operation, output có thể hiển thị:

- E-Rows và A-Rows: số hàng ước lượng và thực tế.
- Starts: số lần operation được chạy.
- Buffers và Reads: logical/physical I/O.
- OMem và 1Mem: thông tin bộ nhớ workarea.
- Used-Mem: bộ nhớ thực tế đã dùng.
- Used-Tmp hoặc TempSpc: thông tin liên quan đến TEMP nếu có trong format và operation.

Các cột memory giúp nhận diện sort/hash operation có thể phải dùng TEMP. Không phải mọi plan đều hiển thị đầy đủ thông tin này; cần xem output thực tế của phiên bản Oracle đang dùng.

### Ví dụ các operation thường gặp

| Operation | Công việc |
|---|---|
| SORT ORDER BY | Sắp xếp kết quả theo ORDER BY |
| SORT ORDER BY STOPKEY | Sắp xếp/giữ phần đầu theo giới hạn hàng |
| SORT UNIQUE | Sắp xếp và loại bỏ hàng trùng |
| HASH UNIQUE | Dùng hash để loại trùng |
| SORT GROUP BY | Sắp xếp theo khóa nhóm rồi aggregate |
| HASH GROUP BY | Dùng hash table để aggregate theo nhóm |
| WINDOW SORT | Sắp xếp dữ liệu phục vụ analytic/window function |

Nếu plan có operation trên, điều đó không tự động có nghĩa đã spill. Cần xem thống kê runtime và trạng thái workarea.

## 9. Theo dõi workarea qua các dynamic performance view

Oracle cung cấp các view để quan sát workarea và TEMP. Quyền truy cập phụ thuộc tài khoản; có thể cần quyền SELECT_CATALOG_ROLE hoặc quyền đọc view cụ thể do DBA cấp.

### V$SQL_WORKAREA

View này lưu thông tin workarea của các cursor đã được thực thi. Một số cột hữu ích:

- SQL_ID, CHILD_NUMBER và OPERATION_ID: xác định cursor và operation.
- OPERATION_TYPE: SORT, HASH-JOIN, GROUP BY hoặc loại operation khác.
- POLICY: chính sách cấp workarea.
- LAST_EXECUTION: trạng thái thực thi gần nhất, thường thể hiện OPTIMAL, ONE PASS hoặc MULTI-PASS.
- OPTIMAL_EXECUTIONS, ONEPASS_EXECUTIONS, MULTIPASSES_EXECUTIONS: số lần chạy theo từng chế độ.
- LAST_TEMPSEG_SIZE, MAX_TEMPSEG_SIZE: dung lượng TEMP được ghi nhận cho workarea.

Ví dụ:

~~~sql
SELECT sql_id,
       child_number,
       operation_id,
       operation_type,
       policy,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions,
       last_tempseg_size,
       max_tempseg_size
  FROM v$sql_workarea
 WHERE sql_id = 'your_sql_id'
 ORDER BY child_number, operation_id;
~~~

Thay your_sql_id bằng SQL_ID thực tế. View này hữu ích khi muốn biết cursor đã từng chạy optimal hay phải dùng TEMP.

### V$SQL_WORKAREA_ACTIVE

View này cho biết các workarea đang hoạt động tại thời điểm truy vấn. Nó hữu ích khi cần quan sát một câu SQL đang chạy:

~~~sql
SELECT sid,
       sql_id,
       operation_id,
       operation_type,
       policy,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
  FROM v$sql_workarea_active
 ORDER BY tempseg_size DESC NULLS LAST;
~~~

Nếu truy vấn kết thúc trước khi câu SELECT này chạy, workarea active có thể không còn xuất hiện. Khi cần chụp trạng thái đang chạy, hãy quan sát từ một session DBA hoặc công cụ giám sát riêng.

### V$TEMPSEG_USAGE

View này cho biết các temporary segment đang được session sử dụng:

~~~sql
SELECT username,
       session_num,
       sql_id,
       tablespace,
       segtype,
       extents,
       blocks
  FROM v$tempseg_usage
 ORDER BY blocks DESC;
~~~

SEGTYPE giúp nhận diện loại temporary segment. BLOCKS biểu thị số block đang dùng; muốn quy đổi sang byte cần nhân với kích thước block của tablespace tương ứng. Trong RAC, cần xem xét các view GV$ tương ứng nếu muốn tổng hợp trên nhiều instance.

Các view V$ là thông tin động. Số liệu có thể thay đổi nhanh, và một truy vấn kiểm tra sau khi operation kết thúc có thể không thấy TEMP segment đã được giải phóng.

## 10. Tìm nguyên nhân spill TEMP

Khi phát hiện sort hoặc hash operation dùng TEMP, hãy lần lượt xác định:

1. **Số hàng đầu vào:** operation nhận bao nhiêu hàng sau filter và join?
2. **Độ rộng hàng:** mỗi hàng có chứa nhiều cột hoặc giá trị lớn không cần thiết không?
3. **Cardinality estimate:** E-Rows có lệch nhiều so với A-Rows không?
4. **Số nhóm hoặc giá trị duy nhất:** GROUP BY/DISTINCT tạo ra bao nhiêu nhóm hoặc key?
5. **Số lần chạy:** Starts có lớn do nested loop hoặc correlated operation không?
6. **Workarea mode:** operation chạy optimal, one-pass hay multi-pass?
7. **PGA pressure:** nhiều session có cùng chạy sort/hash lớn không?
8. **TEMP I/O:** tempfile có throughput hoặc latency bất thường không?

Ví dụ, nếu một truy vấn GROUP BY nhận 20 triệu hàng nhưng chỉ tạo 10 nhóm, cần xem có thể giảm dữ liệu đầu vào trước khi aggregate hay không. Nếu tạo 15 triệu nhóm, lượng trạng thái hash lớn có thể là yêu cầu tự nhiên của dữ liệu; lúc đó cần xem lại cách phân tích, phân vùng, hoặc thiết kế workload.

Sai lệch E-Rows/A-Rows có thể khiến optimizer chọn chiến lược không phù hợp. Nếu optimizer nghĩ chỉ có vài trăm hàng nhưng thực tế là hàng triệu, nó có thể chọn join order hoặc aggregate method dựa trên giả định sai.

## 11. Tối ưu ORDER BY

### Lọc dữ liệu trước khi sort

Giảm số hàng trước khi sort thường là cách hiệu quả nhất:

~~~sql
SELECT order_id,
       order_date,
       total_amount
  FROM orders
 WHERE status = 'PAID'
   AND order_date >= DATE '2026-01-01'
 ORDER BY total_amount DESC;
~~~

Nếu điều kiện lọc có thể dùng index hoặc partition pruning, Oracle có thể giảm số hàng phải sort.

### Chỉ lấy cột cần thiết

Không dùng SELECT * nếu kết quả chỉ cần một vài cột:

~~~sql
SELECT order_id,
       total_amount
  FROM orders
 ORDER BY total_amount DESC;
~~~

Hàng càng rộng thì sort càng cần giữ nhiều dữ liệu. Tránh đưa CLOB, BLOB hoặc các cột lớn vào tập dữ liệu trung gian nếu không cần.

### Xem xét index theo thứ tự truy vấn

Nếu truy vấn thường lọc theo một cột và sắp xếp theo cột khác, hãy xem xét composite index theo mẫu truy vấn thực tế. Không nên tạo index chỉ theo thứ tự cột trong ORDER BY mà bỏ qua predicate và độ chọn lọc.

### Dùng giới hạn hàng khi nghiệp vụ cho phép

FETCH FIRST n ROWS ONLY hoặc OFFSET/FETCH có thể giảm lượng kết quả cần trả. Tuy nhiên OFFSET lớn có thể vẫn phải đọc và bỏ qua nhiều hàng; keyset pagination dựa trên khóa sắp xếp có thể phù hợp hơn cho phân trang sâu.

## 12. Tối ưu DISTINCT

Trước khi dùng DISTINCT, hãy xác định vì sao dữ liệu bị trùng:

- JOIN có tạo quan hệ một-nhiều ngoài dự kiến không?
- Có cần lấy một hàng cho mỗi thực thể hay cần một tập hợp các cặp giá trị?
- Có thể dùng EXISTS hoặc semi-join thay cho join rồi DISTINCT không?
- Có thể sửa điều kiện JOIN hoặc lọc dữ liệu trước không?

Nếu DISTINCT là yêu cầu nghiệp vụ thực sự, hãy giảm số hàng và độ rộng dữ liệu trước khi loại trùng:

~~~sql
SELECT DISTINCT customer_id
  FROM orders
 WHERE order_date >= DATE '2026-01-01'
   AND status = 'PAID';
~~~

Nếu chỉ cần khách hàng có đơn hàng đã thanh toán trong khoảng thời gian, EXISTS có thể biểu đạt tốt hơn:

~~~sql
SELECT c.customer_id
  FROM customers c
 WHERE EXISTS (
       SELECT 1
         FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.status = 'PAID'
          AND o.order_date >= DATE '2026-01-01'
 );
~~~

Không xóa DISTINCT chỉ để tránh TEMP nếu việc đó làm thay đổi kết quả. Tối ưu phải giữ đúng ngữ nghĩa nghiệp vụ.

## 13. Tối ưu GROUP BY

### Lọc và thu hẹp dữ liệu trước khi nhóm

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary
  FROM employees
 WHERE hire_date >= DATE '2020-01-01'
 GROUP BY department_id;
~~~

Predicate càng giảm được nhiều hàng trước aggregate thì công việc hash/sort càng ít. Optimizer có thể tự đẩy điều kiện xuống khi phép biến đổi bảo toàn ngữ nghĩa; hãy xác nhận bằng execution plan.

### Chỉ nhóm theo khóa cần thiết

GROUP BY thêm nhiều cột có thể làm tăng số nhóm. Nếu nghiệp vụ chỉ cần tổng theo department_id, không thêm employee_id hoặc các cột chi tiết vào GROUP BY.

### Aggregate trước khi JOIN khi phù hợp

Nếu chỉ cần tổng hợp một bảng con rồi nối kết quả với bảng cha, có thể aggregate trước để giảm số hàng join. Cần kiểm tra logic để không làm thay đổi kết quả khi có quan hệ nhiều-nhiều hoặc điều kiện lọc phụ thuộc bảng khác.

Ví dụ tính tổng doanh thu theo khách hàng rồi nối với khách hàng:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       s.total_amount
  FROM customers c
  JOIN (
       SELECT customer_id,
              SUM(total_amount) AS total_amount
         FROM orders
        WHERE status = 'PAID'
        GROUP BY customer_id
  ) s
    ON s.customer_id = c.customer_id;
~~~

Đây là cách biểu diễn rõ ràng rằng đơn hàng được aggregate theo customer_id trước khi nối. Optimizer có thể biến đổi truy vấn tùy tình huống; hãy dùng plan để hiểu kế hoạch thực tế.

### Dùng partitioning khi dữ liệu lớn và có khóa phân vùng phù hợp

Với bảng rất lớn, partition pruning có thể giảm dữ liệu cần đọc trước khi GROUP BY. Nếu workload thường phân tích theo ngày hoặc tháng, partition theo thời gian có thể hữu ích. Partitioning cần thiết kế theo vòng đời dữ liệu, điều kiện truy vấn và chi phí quản trị; nó không tự động làm mọi phép nhóm nhanh hơn.

## 14. Giảm áp lực TEMP bằng cách thay đổi thiết kế truy vấn

Một số hướng có thể giảm lượng dữ liệu trung gian:

- Áp dụng điều kiện lọc sớm khi không làm thay đổi ngữ nghĩa.
- Chỉ chiếu các cột cần thiết, tránh hàng rộng.
- Tránh DISTINCT không cần thiết hoặc dùng nó để che JOIN sai.
- Dùng EXISTS khi chỉ cần kiểm tra tồn tại.
- Aggregate ở đúng grain trước khi join nếu hợp lý.
- Dùng index phù hợp để cung cấp thứ tự hoặc lọc chọn lọc.
- Dùng partition pruning để giảm phạm vi đọc.
- Chia workload báo cáo rất lớn thành các khoảng hoặc batch nếu nghiệp vụ cho phép.
- Xem xét materialized view hoặc bảng tổng hợp cho báo cáo lặp lại, dữ liệu cập nhật theo lịch.

Không phải lúc nào cũng nên chia truy vấn thành nhiều bước. Việc materialize kết quả trung gian có thể thêm ghi/đọc, tạo TEMP hoặc tăng độ phức tạp. Hãy đo toàn bộ luồng thay vì chỉ một operation.

## 15. Khi nào nên điều chỉnh PGA hoặc TEMP?

Chỉ xem xét thay đổi cấu hình sau khi đã hiểu workload và loại operation đang spill:

### Điều chỉnh PGA

Nếu nhiều truy vấn sort/hash hợp lệ thường xuyên chạy one-pass hoặc multi-pass, PGA_AGGREGATE_TARGET có thể cần được đánh giá cùng tổng RAM, số session đồng thời và các thành phần dùng PGA khác.

Không tăng PGA chỉ để làm một truy vấn thử nghiệm chạy optimal. Thay đổi instance-wide có thể làm các process khác thiếu RAM hoặc chạm PGA_AGGREGATE_LIMIT. Cần DBA xem xét tải toàn hệ thống và theo dõi sau thay đổi.

### Điều chỉnh TEMP tablespace

Nếu TEMP gần hết dung lượng trong workload hợp lệ, DBA có thể cần kiểm tra tempfile, autoextend, dung lượng filesystem/ASM và mức sử dụng đồng thời. TEMP phải đủ để xử lý đỉnh tải hợp lý.

Tăng TEMP giải quyết vấn đề dung lượng, không nhất thiết giải quyết vấn đề hiệu năng. Nếu operation ghi và đọc hàng trăm GB TEMP, truy vấn vẫn có thể chậm dù còn đủ không gian.

### Quản lý đồng thời

Một báo cáo đơn lẻ có thể chạy tốt nhưng nhiều báo cáo cùng chạy có thể cạnh tranh PGA và TEMP. Hãy xem thời điểm chạy, lịch batch, giới hạn concurrency và resource manager nếu workload có tính chu kỳ.

## 16. Ví dụ đọc một tình huống spill

Giả sử một truy vấn báo cáo:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 GROUP BY customer_id, status
 ORDER BY total_amount DESC;
~~~

Sau khi chạy và fetch hết kết quả, xem:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Giả sử plan có HASH GROUP BY và SORT ORDER BY. Thống kê cho thấy:

- Filter đưa vào aggregate 30 triệu hàng.
- HASH GROUP BY tạo 12 triệu nhóm.
- Workarea của aggregate chạy one-pass và dùng TEMP.
- SORT ORDER BY tiếp tục xử lý 12 triệu hàng và cũng dùng TEMP.

Các hướng điều tra:

1. Xác nhận báo cáo có thực sự cần phân nhóm theo cả customer_id và status không.
2. Kiểm tra điều kiện thời gian có thể giảm dữ liệu bằng partition pruning hoặc index không.
3. Xem 12 triệu nhóm có đúng với cardinality nghiệp vụ không.
4. Kiểm tra có thể lọc status hoặc giới hạn khoảng thời gian theo yêu cầu báo cáo không.
5. Nếu chỉ cần top 100 khách hàng theo tổng tiền, xem xét cách biểu đạt top-N để Oracle giảm dữ liệu phải sort sau aggregate.
6. Kiểm tra PGA/TEMP và mức tải đồng thời nếu dữ liệu đầu vào là yêu cầu thực tế không thể giảm.

Không thể kết luận chỉ từ việc có HASH GROUP BY và SORT ORDER BY rằng nên tạo index hay tăng PGA. Cần kiểm tra ngữ nghĩa, plan, cardinality, workarea và số liệu I/O.

## 17. Những hiểu lầm thường gặp

**Có SORT ORDER BY nghĩa là truy vấn chậm:** không nhất thiết. Sort một tập nhỏ có thể rất rẻ. Cần xem số hàng, độ rộng, thời gian và Buffers.

**Không có SORT ORDER BY nghĩa là kết quả đã có thứ tự:** không đúng. Chỉ ORDER BY bảo đảm thứ tự SQL.

**GROUP BY luôn sắp xếp kết quả:** không đúng. GROUP BY gom nhóm; thứ tự phải được yêu cầu riêng.

**DISTINCT luôn dùng sort:** không đúng. Oracle có thể dùng HASH UNIQUE hoặc cách thực thi khác.

**TEMP usage luôn là lỗi cấu hình:** không đúng. TEMP là cơ chế bình thường để xử lý dữ liệu trung gian vượt workarea. Cần đánh giá lượng dùng và tác động hiệu năng.

**Tăng TEMP sẽ làm truy vấn nhanh:** không đúng. Tăng dung lượng giúp tránh hết chỗ, nhưng không loại bỏ I/O của spill.

**Tăng PGA luôn tốt:** không đúng. PGA là tài nguyên toàn instance và có thể bị nhiều session cạnh tranh.

**Tạo index trên mọi cột ORDER BY:** không đúng. Index làm tăng chi phí DML và dung lượng; chỉ tạo khi phù hợp mẫu truy vấn và được đo kiểm.

**Thêm DISTINCT để sửa hàng trùng do JOIN:** có thể che lỗi logic và thêm chi phí sort/hash. Hãy kiểm tra cardinality và quan hệ JOIN.

## 18. Quy trình thử nghiệm và so sánh

Khi điều tra truy vấn dùng TEMP nhiều, nên ghi lại:

1. SQL text, SQL_ID và child cursor.
2. Bộ bind và dữ liệu thử nghiệm.
3. Execution plan và row-source statistics.
4. E-Rows, A-Rows, Starts, Buffers, Reads và A-Time.
5. Workarea mode, số lần optimal/one-pass/multi-pass và TEMP size.
6. PGA/TEMP usage ở thời điểm chạy.
7. Số hàng kết quả và xác nhận tính đúng đắn.
8. Điều kiện session, concurrency và cách client fetch kết quả.

Sau đó thay đổi một yếu tố, ví dụ thêm điều kiện lọc, sửa JOIN, giảm cột, thêm index hoặc thay đổi cách aggregate. Chạy lại với cùng dữ liệu và bind. So sánh cả thời gian, I/O, TEMP, số hàng và kết quả cuối.

Nếu chỉ thay đổi dữ liệu, tham số, cache hoặc mức tải cùng lúc, sẽ khó biết yếu tố nào tạo ra khác biệt. Môi trường thử nghiệm nên càng gần workload mục tiêu càng tốt, nhưng không chạy các thao tác có ảnh hưởng lớn lên production chỉ để thu thập số liệu.

## 19. Kết luận

ORDER BY cần cung cấp thứ tự kết quả; DISTINCT loại bỏ các hàng trùng; GROUP BY gom hàng để tính aggregate. Oracle có thể dùng sort hoặc hash operation cho các yêu cầu này. Khi dữ liệu trung gian không vừa workarea trong PGA, operation có thể spill ra TEMP và tiếp tục xử lý bằng I/O.

Để giảm chi phí, hãy xác định số hàng và độ rộng dữ liệu đầu vào, kiểm tra cardinality, tránh DISTINCT không cần thiết, lọc sớm, nhóm đúng grain và xem xét index hoặc partitioning phù hợp. Dùng DBMS_XPLAN với runtime statistics và các view V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE, V$TEMPSEG_USAGE để xác định operation và mức spill. Chỉ điều chỉnh PGA hoặc TEMP sau khi đã hiểu workload và đánh giá tác động toàn hệ thống. Mục tiêu là giữ đúng kết quả nghiệp vụ đồng thời giảm dữ liệu trung gian, I/O và thời gian thực thi.
