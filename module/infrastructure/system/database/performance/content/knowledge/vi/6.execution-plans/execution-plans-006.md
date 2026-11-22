# Phân tích bộ đệm, đọc đĩa và tràn bộ nhớ qua thông tin thực thi

Kế hoạch thực thi cho biết hệ quản trị cơ sở dữ liệu (DBMS) dự định truy cập và xử lý dữ liệu như thế nào. Khi chạy một truy vấn với thống kê thực tế, thông tin bộ đệm, số khối đọc, dữ liệu tạm và cách thực hiện các phép sort hoặc hash giúp giải thích vì sao truy vấn nhanh hay chậm. Những dấu hiệu này đặc biệt quan trọng khi một truy vấn có vẻ đơn giản nhưng phải đọc nhiều trang, khi cache không giữ được tập dữ liệu thường dùng hoặc khi thao tác trung gian vượt quá bộ nhớ và phải ghi ra đĩa.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Kế hoạch thực thi** tập trung vào cách đọc các dấu vết I/O và bộ nhớ trong thông tin thực thi. Người học sẽ biết phân biệt cache hit với đọc khối, hiểu giới hạn của chỉ số đọc đĩa, nhận diện sort/hash spill, đối chiếu số dòng ước lượng với số dòng thực tế và lựa chọn thay đổi SQL, chỉ mục hoặc cấu hình dựa trên bằng chứng.

Sau bài học, người học có thể:

- Giải thích buffer hit, buffer read, dirty buffer, temporary block và I/O timing.
- Phân biệt việc đọc một khối vào bộ đệm của DBMS với việc đọc thực sự từ thiết bị vật lý.
- Đọc các thông tin buffer trong kế hoạch thực thi và tránh cộng trùng số liệu ở các nút cha/con.
- Nhận diện sort hoặc hash operation tràn bộ nhớ qua phương pháp sort, số batch và temporary I/O.
- Kết hợp số dòng ước lượng, số dòng thực tế, số vòng lặp và số khối truy cập để tìm nguyên nhân.
- Chọn cách cải thiện phù hợp và kiểm chứng kết quả dưới tải đại diện.

## 1. Bộ đệm và đường đi của một lần đọc dữ liệu

### 1.1. Trang dữ liệu và bộ đệm

DBMS thường quản lý dữ liệu trên lưu trữ theo các đơn vị trang hoặc khối. Một truy vấn cần đọc một hàng dữ liệu có thể phải truy cập trang chứa hàng đó. Trang có thể chứa nhiều hàng hoặc một phần của cấu trúc chỉ mục. Vì vậy, số hàng được trả về không cho biết trực tiếp số lần đọc trang.

Để tránh đọc lưu trữ lặp đi lặp lại, DBMS sử dụng vùng nhớ đệm. Khi một trang đã nằm trong bộ đệm và truy vấn cần trang đó, DBMS có thể sử dụng nội dung trong RAM. Khi trang chưa có trong bộ đệm, DBMS phải yêu cầu hệ thống lưu trữ cung cấp dữ liệu rồi đưa trang vào vùng đệm thích hợp.

Đường đi đơn giản của một lần đọc có thể mô tả như sau:

~~~text
Truy vấn cần một trang dữ liệu
             |
             v
      Tìm trong buffer
        /        \
       /          \
    Có trang      Không có
      |              |
      v              v
  Buffer hit     Yêu cầu đọc
                     |
                     v
             Hệ điều hành / storage
                     |
                     v
               Đưa vào buffer
                     |
                     v
               Trả dữ liệu
~~~

Một lần buffer hit thường rẻ hơn một lần phải nạp trang vào bộ đệm. Tuy nhiên, hit không đồng nghĩa truy vấn miễn phí: DBMS vẫn phải tìm trang, kiểm tra điều kiện, xử lý hàng dữ liệu và có thể thực hiện phép nối, sắp xếp hoặc tính toán.

### 1.2. Các tầng cache

Một máy chủ cơ sở dữ liệu có thể có nhiều tầng lưu giữ dữ liệu:

- Buffer pool hoặc shared buffer do DBMS quản lý.
- Page cache của hệ điều hành.
- Cache của thiết bị lưu trữ hoặc bộ điều khiển.
- Cache ở tầng lưu trữ mạng hoặc nền tảng cloud.

Khi DBMS cần một trang không có trong buffer pool, hệ điều hành vẫn có thể tìm thấy dữ liệu trong page cache. Trong trường hợp đó, DBMS ghi nhận phải đọc trang vào buffer của mình, nhưng thiết bị vật lý có thể không phải thực hiện một lần đọc đĩa thực sự.

Vì vậy, cần phân biệt:

- **Buffer hit:** trang đã có trong vùng đệm do DBMS quản lý.
- **Buffer read/miss:** DBMS phải nạp trang vào vùng đệm.
- **Physical device read:** thiết bị lưu trữ thực sự phải phục vụ thao tác đọc.

Một chỉ số buffer read không tự chứng minh ổ đĩa đã đọc vật lý. Muốn đánh giá thiết bị, cần đối chiếu thêm I/O timing, số liệu hệ điều hành, số liệu volume hoặc thiết bị lưu trữ và wait event của DBMS.

### 1.3. Buffer hit không phải bằng chứng duy nhất về hiệu năng tốt

Tỷ lệ hit cao thường hữu ích, nhưng không đủ để kết luận truy vấn tốt:

- Một truy vấn có thể hit rất nhiều trang nhưng vẫn xử lý hàng triệu dòng và tốn CPU.
- Một truy vấn có thể đọc một số trang mới trong lần chạy đầu, sau đó nhanh hơn khi cache ấm.
- Một truy vấn có thể hit trang chỉ mục nhưng phải truy cập nhiều trang heap rời rạc để lấy dữ liệu.
- Cache có thể giữ nhiều trang không còn hữu ích, khiến working set của workload bị đẩy ra.
- Hit rate tổng thể của toàn máy có thể che giấu một truy vấn cụ thể có nhiều lần đọc.

Cần xem cả số lượng khối, thời gian, số dòng thực tế, số vòng lặp và loại thao tác trong kế hoạch thực thi. Tỷ lệ hit nên được dùng như một tín hiệu chẩn đoán, không phải mục tiêu tối ưu độc lập.

### 1.4. Buffer là đơn vị khối, không phải số dòng

Trong PostgreSQL, thống kê BUFFERS thường báo số khối (block) được hit, read, dirtied hoặc written. Kích thước khối mặc định thường là 8 KB, nhưng cần kiểm tra cấu hình cụ thể thay vì mặc định quy đổi cho mọi hệ thống.

Ví dụ, một truy vấn trả về 20 dòng có thể phải đọc hàng trăm trang nếu các dòng nằm rải rác hoặc kế hoạch phải quét một vùng dữ liệu lớn. Ngược lại, một truy vấn trả về hàng nghìn dòng có thể dùng ít trang hơn nếu dữ liệu nằm liên tiếp và truy cập hiệu quả.

Do đó, không nên suy ra số lần đọc từ số dòng trả về. Hãy xem kế hoạch và buffer statistics để hiểu lượng dữ liệu mà DBMS đã chạm tới.

## 2. Đọc thông tin BUFFERS trong PostgreSQL

### 2.1. Dùng EXPLAIN ANALYZE với BUFFERS

PostgreSQL cho phép xem kế hoạch dự kiến bằng EXPLAIN và kế hoạch kèm số liệu thực tế bằng EXPLAIN ANALYZE. Tùy chọn BUFFERS bổ sung thống kê truy cập bộ đệm ở các nút của kế hoạch.

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 50;
~~~

Thông tin có thể bao gồm:

- **shared hit:** số khối tìm thấy trong shared buffers.
- **shared read:** số khối được đọc vào shared buffers.
- **shared dirtied:** số khối shared buffer bị thay đổi trong lúc thực hiện.
- **shared written:** số khối được ghi bởi backend trong lúc thực hiện.
- **local hit, local read, local dirtied, local written:** các chỉ số tương tự cho local buffers, thường liên quan đến bảng tạm.
- **temp read, temp written:** số khối tạm được đọc hoặc ghi, thường xuất hiện khi thao tác trung gian sử dụng tệp tạm.

Các trường xuất hiện tùy loại thao tác và hoạt động thực tế. Nếu một loại bộ đệm không được sử dụng, kế hoạch có thể không in nhóm chỉ số tương ứng.

### 2.2. Hiểu shared hit và shared read

Ví dụ một nút có thông tin:

~~~text
Buffers: shared hit=120 read=35
~~~

Có thể diễn giải rằng trong phạm vi thống kê của nút, DBMS đã tìm thấy 120 lần khối trong shared buffers và phải nạp 35 khối vào shared buffers. Đây không nhất thiết là 35 lần thiết bị vật lý đọc đĩa; hệ điều hành hoặc tầng lưu trữ có thể phục vụ một phần từ cache.

Cũng cần xem kích thước khối và bối cảnh kế hoạch. Nếu 35 khối được đọc một lần cho một truy vấn nhỏ, đó có thể là chi phí bình thường. Nếu một nút quét bảng lớn và đọc hàng trăm nghìn khối trong mỗi lần gọi, cần xem lại điều kiện lọc, chỉ mục và số dòng mà kế hoạch xử lý.

### 2.3. Hiểu dirtied và written

**shared dirtied** phản ánh các khối trong shared buffers đã bị thay đổi trong quá trình thực thi. Ví dụ, câu lệnh UPDATE hoặc INSERT có thể làm trang dữ liệu và trang chỉ mục trở thành dirty.

**shared written** phản ánh số khối được ghi bởi backend trong quá trình thực thi. Không nên hiểu nó là tổng số lần ghi vật lý của toàn bộ hệ thống hoặc đồng nhất với mọi hoạt động checkpoint. PostgreSQL có cơ chế ghi nền và checkpoint riêng; backend, background writer và checkpointer có thể tham gia ghi các trang vào những thời điểm khác nhau.

Khi đo truy vấn đọc, các chỉ số dirtied/written thường thấp hoặc không xuất hiện. Với truy vấn ghi, chúng giúp thấy thao tác đã làm thay đổi bao nhiêu khối trong bộ đệm, nhưng cần kết hợp với WAL, commit latency và thống kê I/O để hiểu đầy đủ chi phí ghi.

### 2.4. Hiểu temp read và temp written

**temp read** và **temp written** cho biết các khối trong không gian tạm đã được đọc hoặc ghi. Các thao tác sort, hash join hoặc hash aggregate có thể tạo dữ liệu trung gian lớn. Khi bộ nhớ được cấp cho thao tác không đủ, DBMS có thể chia dữ liệu thành nhiều phần và ghi một phần ra tệp tạm.

Ví dụ:

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: 18432kB
  Buffers: shared hit=240 read=80
  I/O Timings: shared read=12.400
  Buffers: temp read=2200 written=2250
~~~

Đây là dạng đầu ra minh họa. Dòng external merge và thông tin Disk cho thấy sort đã dùng phương pháp ngoài bộ nhớ, còn temporary blocks thể hiện hoạt động đọc/ghi dữ liệu tạm. Cần đọc toàn bộ kế hoạch để xác định vì sao sort nhận nhiều dòng và liệu có thể giảm đầu vào hay thay đổi cách truy cập.

### 2.5. Không cộng trùng buffer ở nút cha và nút con

Trong PostgreSQL, số liệu BUFFERS của một nút kế hoạch bao gồm hoạt động của các nút con bên dưới nó. Vì vậy, nếu cộng shared hit hoặc shared read của tất cả các dòng trong kế hoạch, có thể đếm trùng cùng một hoạt động.

Hãy dùng số liệu ở nút gốc để xem tổng thể truy vấn và đọc các nút con để tìm phần nào đóng góp vào chi phí. Khi phân tích từng nút, luôn nhớ số liệu ở nút cha có thể đã bao gồm phần của con.

## 3. Phân biệt đọc bộ đệm và đọc lưu trữ

### 3.1. Vì sao shared read không đồng nghĩa với đọc vật lý?

Khi PostgreSQL không tìm thấy một block trong shared buffers, nó yêu cầu hệ điều hành đọc block đó. Hệ điều hành có thể lấy dữ liệu từ page cache thay vì thiết bị. Bởi vậy:

- **shared hit** là hit trong shared buffers của PostgreSQL.
- **shared read** là block được đưa vào shared buffers từ đường đọc của hệ điều hành.
- Số liệu thiết bị là bằng chứng ở tầng lưu trữ, cần thu thập riêng.

Điều này giải thích vì sao một truy vấn có shared read nhưng thời gian đọc rất thấp: dữ liệu có thể đã nằm trong page cache. Ngược lại, một truy vấn có ít block read nhưng mỗi lần đọc có độ trễ cao vẫn có thể chậm đáng kể.

### 3.2. Dùng I/O timing để bổ sung ngữ cảnh

PostgreSQL có thể hiển thị thời gian đọc/ghi I/O trong kế hoạch nếu bật theo dõi I/O timing phù hợp, chẳng hạn tham số track_io_timing.

Có thể kiểm tra cấu hình:

~~~sql
SHOW track_io_timing;
~~~

Nếu cần bật trong môi trường thử nghiệm và có quyền phù hợp:

~~~sql
SET track_io_timing = on;
~~~

Khi được hỗ trợ và bật, kế hoạch có thể hiển thị dạng:

~~~text
I/O Timings: shared read=18.732 write=2.115
~~~

Các giá trị này thường được thể hiện bằng mili giây. Chúng giúp nhận biết thời gian DBMS chờ thao tác đọc/ghi, nhưng vẫn cần diễn giải cùng số khối và tầng cache. Bật theo dõi có thể tạo thêm chi phí đo ở một số môi trường; hãy kiểm tra ảnh hưởng và chính sách cấu hình trước khi bật rộng trên production.

### 3.3. Đối chiếu với hệ điều hành và nền tảng lưu trữ

Nếu kế hoạch cho thấy nhiều block read hoặc thời gian I/O cao, hãy quan sát thêm:

- Read latency và write latency của thiết bị.
- IOPS và throughput thực tế so với giới hạn được cấp.
- Queue depth hoặc số yêu cầu I/O đang chờ.
- CPU I/O wait và áp lực bộ nhớ.
- Hoạt động swap, page fault và cache của hệ điều hành.
- Giới hạn IOPS/băng thông của volume, máy ảo hoặc dịch vụ lưu trữ cloud.

Trên Linux, các tiện ích như iostat và vmstat có thể cung cấp một phần dữ liệu:

~~~bash
iostat -xz 1
vmstat 1
~~~

Cần thu thập số liệu cùng thời điểm với truy vấn. Một báo cáo I/O của toàn máy trong khoảng một giờ không đủ để giải thích một truy vấn chạy trong vài trăm mili giây nếu tải nền thay đổi mạnh.

### 3.4. Ví dụ phân tích

Giả sử hai lần chạy cùng một truy vấn:

| Chỉ số | Lần A | Lần B |
|---|---:|---:|
| shared hit | 18.000 | 17.900 |
| shared read | 2.000 | 2.100 |
| I/O read timing | 8 ms | 145 ms |
| Execution time | 75 ms | 220 ms |

Số block gần tương đương nhưng thời gian đọc khác đáng kể. Một giả thuyết hợp lý là lần B gặp độ trễ đọc cao hơn ở tầng hệ điều hành hoặc lưu trữ. Cần đối chiếu số liệu thiết bị, page cache, tải nền và wait event để xác nhận.

Ngược lại, nếu số block read tăng từ 2.000 lên 80.000 nhưng thời gian đọc vẫn thấp, có thể truy vấn đã truy cập nhiều dữ liệu hơn nhưng phần lớn được phục vụ từ cache ở tầng dưới. Khi đó vẫn cần xem CPU, số dòng xử lý và kế hoạch truy cập, vì lượng block lớn có thể tạo chi phí khác ngoài thời gian thiết bị.

## 4. Đọc số dòng ước lượng và số dòng thực tế

### 4.1. Estimate và actual rows

Optimizer dựa vào thống kê để ước lượng số dòng đi qua mỗi nút. Khi dùng EXPLAIN ANALYZE, PostgreSQL hiển thị cả ước lượng và số dòng thực tế.

Ví dụ:

~~~text
Index Scan using idx_orders_customer on orders
  (cost=0.42..120.00 rows=50 width=32)
  (actual time=0.080..18.200 rows=12000 loops=1)
  Index Cond: (customer_id = 123)
  Buffers: shared hit=9000 read=120
~~~

Ở đây, optimizer ước lượng khoảng 50 dòng nhưng thực tế trả về 12.000 dòng. Chênh lệch lớn có thể khiến kế hoạch phía trên chọn sai join strategy, thứ tự join hoặc cách cấp phát bộ nhớ.

Khi loops lớn hơn 1, số dòng và thời gian thực tế được hiển thị theo cách tính trung bình cho mỗi lần lặp ở nhiều trường hợp. Để ước lượng tổng lượng dòng được xử lý, cần xét số dòng mỗi loop nhân với số loops; không nên chỉ nhìn con số rows đơn lẻ.

### 4.2. Vì sao ước lượng sai ảnh hưởng đến I/O và bộ nhớ?

Ước lượng số dòng sai có thể dẫn đến:

- Chọn nested loop cho một tập dữ liệu thực tế lớn, làm lặp truy cập inner relation nhiều lần.
- Chọn hash join với kích thước hash table lớn hơn dự kiến.
- Chọn sort hoặc aggregate cần nhiều bộ nhớ hơn ước lượng.
- Chọn sai thứ tự join, làm các bước trung gian phình to.
- Đánh giá thấp số trang cần đọc hoặc số dòng cần lọc.
- Tạo nhiều temporary I/O khi sort/hash vượt bộ nhớ.

Nếu estimate và actual khác biệt lớn, hãy kiểm tra thống kê bảng, độ chọn lọc của điều kiện, tương quan giữa các cột và phân bố dữ liệu. ANALYZE có thể cập nhật thống kê cho PostgreSQL, nhưng cần chạy theo quy trình vận hành và hiểu ảnh hưởng tới kế hoạch.

### 4.3. Rows Removed by Filter

Một nút scan có thể hiển thị số dòng bị loại bởi điều kiện lọc. Ví dụ:

~~~text
Seq Scan on events
  (actual time=0.050..240.000 rows=300 loops=1)
  Filter: (tenant_id = 9001)
  Rows Removed by Filter: 4500000
  Buffers: shared hit=12000 read=8000
~~~

Kết quả trả về chỉ 300 dòng nhưng scan đã xem xét và loại bỏ hàng triệu dòng. Đây là dấu hiệu cần đánh giá tính chọn lọc của điều kiện, chỉ mục có thể áp dụng, phân vùng dữ liệu hoặc cách viết truy vấn.

Không phải mọi sequential scan đều xấu. Nếu truy vấn cần phần lớn bảng hoặc bảng nhỏ, quét tuần tự có thể rẻ hơn dùng chỉ mục. Hãy so sánh số dòng cần đọc, buffer usage và thời gian thực tế thay vì áp dụng quy tắc “luôn phải dùng index”.

## 5. Nhận diện sort spill và hash spill

### 5.1. Sort trong bộ nhớ và sort ngoài bộ nhớ

Một thao tác ORDER BY, DISTINCT, GROUP BY hoặc một phần của join có thể cần sắp xếp dữ liệu. Nếu lượng dữ liệu vừa với bộ nhớ được cấp, DBMS có thể sort trong RAM. Nếu không, nó có thể chia dữ liệu thành các run hoặc partition, ghi ra tệp tạm rồi đọc lại để hoàn thành.

PostgreSQL có thể hiển thị các phương pháp như:

~~~text
Sort Method: quicksort  Memory: 4096kB
~~~

hoặc:

~~~text
Sort Method: external merge  Disk: 98304kB
~~~

quicksort với Memory cho thấy sort được thực hiện trong bộ nhớ theo phương pháp tương ứng. external merge và Disk cho thấy sort dùng tệp tạm trên lưu trữ.

Tràn ra đĩa thường làm tăng thời gian do phải ghi và đọc dữ liệu trung gian. Tuy nhiên, không phải mọi external sort đều cần được loại bỏ bằng cách tăng bộ nhớ. Cần xem số dòng đầu vào, kích thước dữ liệu, yêu cầu sắp xếp và khả năng giảm dữ liệu trước khi sort.

### 5.2. Hash join và số batch

Hash join thường xây dựng một hash table từ một đầu vào rồi dò tìm bằng đầu vào còn lại. Nếu hash table vượt bộ nhớ có thể sử dụng nhiều batch để xử lý từng phần.

Ví dụ đầu ra minh họa:

~~~text
Hash
  Buckets: 65536  Batches: 8  Memory Usage: 2048kB
  Buffers: shared hit=700 read=150
  Buffers: temp read=900 written=920
~~~

Một hash operation có Batches lớn hơn 1 thường cho thấy dữ liệu được chia thành nhiều batch; temporary read/write có thể là dấu hiệu dữ liệu trung gian được lưu ra tệp tạm. Cần đọc cả nút Hash Join và nút Hash để biết phía nào tạo dữ liệu, số dòng thực tế và kích thước đầu vào.

Hash operation dùng một batch không đồng nghĩa mọi thứ đều tối ưu. Nó vẫn có thể tiêu thụ CPU đáng kể hoặc tạo hash table lớn. Ngược lại, nhiều batch có thể là lựa chọn hợp lệ khi dữ liệu lớn hơn bộ nhớ cho phép; điều cần đánh giá là chi phí và ảnh hưởng đến mục tiêu độ trễ.

### 5.3. Hash aggregate và dữ liệu nhóm

GROUP BY có thể dùng hash aggregate hoặc sort-based aggregate tùy optimizer và hệ quản trị. Khi số nhóm lớn hoặc dữ liệu đầu vào lớn, thao tác hash có thể vượt bộ nhớ và tạo temporary I/O.

Khi phân tích, hãy xem:

- Số dòng đầu vào của aggregate.
- Số nhóm thực tế.
- Ước lượng số nhóm của optimizer.
- Bộ nhớ sử dụng và số batch.
- Temporary blocks read/written.
- Có thể lọc hoặc tổng hợp sớm hơn hay không.

Nếu điều kiện lọc có thể giảm số dòng trước khi aggregate mà vẫn giữ đúng ngữ nghĩa, đó thường là hướng giảm lượng dữ liệu trung gian đáng xem xét.

### 5.4. Temporary I/O không phải lúc nào cũng do một nút duy nhất

Khi kế hoạch có temporary blocks, hãy tìm các nút Sort, Hash, HashAggregate hoặc thao tác khác có khả năng tạo tệp tạm. Trong một số trường hợp, temporary I/O được báo ở nút cha hoặc trong phần thống kê tổng hợp; cần đọc cấu trúc cây và lưu ý số liệu có thể bao gồm các nút con.

Cũng cần phân biệt temporary I/O do truy vấn với I/O của bảng tạm do ứng dụng tạo ra. Thống kê temp trong kế hoạch và thống kê tổng hợp theo database có thể phản ánh nhiều loại hoạt động tạm khác nhau.

## 6. Xác định nguyên nhân và chọn hướng cải thiện

### 6.1. Khi shared read cao

Nếu truy vấn đọc nhiều block, hãy kiểm tra:

1. Kế hoạch có dùng Seq Scan, Index Scan hay Bitmap Heap Scan?
2. Số dòng thực tế có lớn hơn nhiều ước lượng không?
3. Điều kiện lọc có chọn lọc đủ tốt không?
4. Chỉ mục hiện tại có phù hợp với điều kiện lọc và thứ tự sắp xếp không?
5. Truy vấn có lấy nhiều cột không cần thiết không?
6. Working set có vượt khả năng cache hay dữ liệu bị phân tán trên nhiều trang?
7. Độ trễ đọc có cao ở tầng lưu trữ không?

Một chỉ mục phù hợp có thể giảm số trang cần truy cập, nhưng chỉ mục cũng có chi phí lưu trữ và ghi. Nếu truy vấn đọc phần lớn bảng, sequential scan có thể vẫn là kế hoạch hợp lý.

### 6.2. Khi temporary read/write cao

Nếu thấy external sort, nhiều hash batches hoặc temp blocks lớn, hãy xem xét:

- Giảm số dòng trước sort/hash bằng điều kiện lọc hợp lệ.
- Chỉ chọn các cột cần thiết để giảm kích thước tuple trung gian.
- Kiểm tra thứ tự join và ước lượng cardinality.
- Đánh giá chỉ mục có thể đáp ứng ORDER BY hoặc điều kiện lọc hay không.
- Xem có thể phân trang hoặc chia nhỏ công việc mà vẫn bảo đảm ngữ nghĩa không.
- Kiểm tra memory setting và số truy vấn đồng thời trước khi tăng bộ nhớ.

Không nên mặc định mọi sort spill đều cần tăng work_mem. Nếu một truy vấn có nhiều thao tác sort/hash và nhiều phiên cùng chạy, bộ nhớ yêu cầu có thể nhân lên đáng kể.

### 6.3. Khi buffer hit cao nhưng truy vấn vẫn chậm

Hit cao nhưng truy vấn chậm có thể do:

- Xử lý quá nhiều dòng trong RAM.
- Nhiều vòng lặp của nested loop.
- CPU tốn cho biểu thức, join, sort hoặc aggregate.
- Chờ khóa hoặc chốt nội bộ.
- Trả về quá nhiều dữ liệu qua mạng.
- Kế hoạch dùng đường truy cập không phù hợp dù các trang đều đang cache.

Trong tình huống này, hãy xem actual rows, loops, thời gian từng nút, rows removed, wait event và thời gian phía client. Tối ưu bộ đệm không giải quyết được chi phí xử lý hoặc chờ giao dịch.

### 6.4. Khi shared read thấp nhưng I/O latency cao

Một số lượng nhỏ lần đọc với độ trễ rất cao vẫn có thể chi phối thời gian truy vấn. Hãy đối chiếu I/O timing, độ trễ thiết bị và hàng đợi. Nếu chỉ số DBMS không tương quan với thiết bị, có thể có cache ở hệ điều hành hoặc tầng lưu trữ.

Tối ưu truy vấn có thể giảm số lần đọc; nâng năng lực lưu trữ có thể giảm độ trễ của các lần đọc còn lại. Chọn biện pháp sau khi đã xác định tầng nào đang giới hạn.

## 7. Cấu hình bộ nhớ và giới hạn theo mức đồng thời

### 7.1. work_mem không phải ngân sách tổng của một truy vấn

Trong PostgreSQL, work_mem đặt mức bộ nhớ cơ sở cho một số thao tác sort và hash trước khi chúng chuyển sang cơ chế dùng tệp tạm. Đây không phải một khoản bộ nhớ cố định duy nhất dành cho mỗi truy vấn. Một truy vấn có thể có nhiều thao tác cần bộ nhớ; nhiều phiên có thể chạy các thao tác đó cùng lúc; truy vấn song song có thể có nhiều worker.

Do đó, tổng bộ nhớ thực tế có thể lớn hơn nhiều so với giá trị work_mem. Tăng cấu hình quá mức có thể làm máy thiếu RAM, gây swap hoặc khiến tiến trình bị hệ điều hành kết thúc.

PostgreSQL còn có các cấu hình liên quan như hash_mem_multiplier ở những phiên bản hỗ trợ. Cách áp dụng cụ thể phụ thuộc phiên bản và loại thao tác. Luôn kiểm tra tài liệu đúng phiên bản trước khi thay đổi.

### 7.2. Tính đến số thao tác và số phiên

Một cách ước lượng thận trọng là lập danh sách:

- Số phiên có thể chạy đồng thời ở mức tải đỉnh.
- Số sort/hash operation trong một truy vấn điển hình.
- Số worker song song có thể được sử dụng.
- Bộ nhớ nền của DBMS, cache, hệ điều hành và ứng dụng.
- Dự phòng cho checkpoint, autovacuum, backup và tác vụ nền.

Đây là cách xây dựng ngân sách và kịch bản, không phải công thức chính xác cho mọi trường hợp vì mỗi thao tác có thể sử dụng ít hơn hoặc nhiều hơn giới hạn cấu hình. Cần đo bộ nhớ thực tế trong tải đại diện.

### 7.3. Giới hạn spill trong các hệ quản trị khác

Khái niệm tương tự tồn tại ở nhiều DBMS nhưng tên và cách hiển thị khác nhau:

- **PostgreSQL:** Sort Method, Disk, Batches, Memory Usage, temp read/written và BUFFERS.
- **SQL Server:** actual execution plan có thể hiển thị cảnh báo sort/hash spill hoặc memory grant; SET STATISTICS IO, TIME ON cung cấp thêm logical reads, physical reads và thời gian.
- **MySQL:** EXPLAIN ANALYZE cho biết actual rows, loops và thời gian; Performance Schema và thống kê InnoDB hỗ trợ theo dõi temporary table, buffer pool và I/O. Chi tiết phụ thuộc phiên bản và engine.

Không so sánh trực tiếp tên trường giữa các hệ quản trị như thể chúng có cùng định nghĩa. Hãy đọc tài liệu của đúng DBMS và phiên bản, rồi xác định số liệu thuộc tầng buffer, hệ điều hành hay thiết bị.

## 8. Ví dụ phân tích kế hoạch thực thi

### 8.1. Tình huống truy vấn đọc nhiều trang

Một báo cáo lấy các đơn hàng của khách hàng trong khoảng thời gian gần đây:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 123
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 100;
~~~

Giả sử kế hoạch cho thấy:

~~~text
Limit
  (actual time=320.000..321.000 rows=100 loops=1)
  Buffers: shared hit=9000 read=12000
  -> Sort
       Sort Key: created_at DESC
       Sort Method: top-N heapsort  Memory: 40kB
       -> Seq Scan on orders
            (actual time=0.050..280.000 rows=180000 loops=1)
            Filter: (customer_id = 123 AND created_at >= ...)
            Rows Removed by Filter: 2800000
            Buffers: shared hit=9000 read=12000
~~~

Đây là đầu ra minh họa. Truy vấn trả về 100 dòng nhưng Seq Scan đã xem xét gần 3 triệu dòng và đọc nhiều block. Sort dùng top-N heapsort vì có LIMIT, nên không nhất thiết tràn bộ nhớ. Dấu hiệu chính ở đây là lượng dòng phải quét trước khi lọc.

Các hướng kiểm tra:

- Thống kê về customer_id và created_at có phản ánh phân bố dữ liệu không?
- Có chỉ mục phù hợp cho điều kiện lọc và thứ tự sắp xếp không?
- Có thể dùng chỉ mục ghép bắt đầu bằng customer_id rồi đến created_at không?
- Số cột được chọn có cần thiết hết không?
- Truy vấn có thực sự cần tất cả các dòng ứng viên không?

Một chỉ mục ghép có thể là một giả thuyết thử nghiệm, nhưng không nên tạo chỉ mục chỉ dựa trên một lần xem kế hoạch. Cần đo truy vấn đọc, chi phí ghi, kích thước chỉ mục và kế hoạch sau thay đổi.

### 8.2. Tình huống sort tràn bộ nhớ

Giả sử một truy vấn báo cáo sắp xếp hàng triệu dòng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY customer_id
ORDER BY revenue DESC;
~~~

Kế hoạch giả định có thể cho thấy:

~~~text
Sort
  Sort Method: external merge  Disk: 245760kB
  Buffers: shared hit=20000 read=6000
  Buffers: temp read=32000 written=32050
  -> HashAggregate
       Batches: 16  Memory Usage: 8192kB
       Buffers: shared hit=20000 read=6000
~~~

Dữ liệu cho thấy thao tác sort dùng đĩa và hash aggregate có nhiều batch. Cần xem số dòng đầu vào, số khách hàng thực tế, estimate, điều kiện lọc và cấu hình bộ nhớ.

Các hướng thử có thể gồm:

1. Cập nhật hoặc cải thiện thống kê nếu estimate sai.
2. Giảm số dòng đầu vào bằng điều kiện lọc hợp lệ.
3. Xem xét cách tổ chức dữ liệu hoặc chỉ mục hỗ trợ phạm vi lọc.
4. Đánh giá bộ nhớ cho sort/hash dưới mức đồng thời thật.
5. Thử một thay đổi trong môi trường có thể kiểm soát rồi so sánh temp I/O, latency và bộ nhớ.

Không nên chỉ tăng work_mem cho đến khi không còn thấy temp file. Nếu nhiều truy vấn chạy đồng thời, tác động bộ nhớ tổng thể có thể nghiêm trọng hơn lợi ích giảm spill.

### 8.3. Tình huống buffer hit cao nhưng CPU vẫn lớn

Một truy vấn đọc bảng đã được cache nhưng phải xử lý nhiều dòng qua biểu thức hoặc join. Kế hoạch có thể có nhiều shared hit và rất ít shared read, trong khi execution time vẫn cao.

Trong trường hợp này, hãy kiểm tra:

- Actual rows và loops của từng nút.
- Số dòng bị loại sau scan.
- Join method và thứ tự join.
- Hàm hoặc biểu thức được tính trên nhiều dòng.
- Sort/hash trong bộ nhớ có tiêu thụ CPU đáng kể không.
- Thời gian CPU và wait event của phiên.

Nếu mọi block đã cache, thêm RAM hoặc tăng cache size có thể không giúp. Cần giảm lượng dòng phải xử lý, cải thiện kế hoạch hoặc tối ưu biểu thức và join.

## 9. Quy trình đọc và kiểm chứng thông tin thực thi

Một quy trình có thể lặp lại:

1. **Chọn truy vấn đại diện:** xác định fingerprint, tham số, loại giao dịch và tần suất chạy.
2. **Ghi đường cơ sở:** lưu thời gian, throughput, p50/p95/p99, số lỗi và mức tải.
3. **Lấy kế hoạch thực tế:** dùng EXPLAIN ANALYZE và BUFFERS trong môi trường phù hợp.
4. **Đọc từ nút gốc xuống nút gây chi phí:** xem actual rows, loops, buffers, temp I/O và thời gian.
5. **So estimate với actual:** tìm chênh lệch cardinality có thể làm sai lựa chọn join hoặc memory sizing.
6. **Phân loại I/O:** shared hit/read, temp read/write và I/O timing; đối chiếu hệ điều hành và thiết bị.
7. **Nêu giả thuyết:** ví dụ truy vấn quét quá nhiều block, sort spill do đầu vào lớn hoặc hash batches tăng do ước lượng thấp.
8. **Thay đổi có kiểm soát:** điều chỉnh SQL, chỉ mục, thống kê hoặc cấu hình trong phạm vi thử nghiệm.
9. **Đo lại dưới tải tương đương:** giữ dữ liệu, tham số, cache policy, mức đồng thời và cửa sổ đo phù hợp.
10. **Kiểm tra tác dụng phụ:** chi phí ghi, bộ nhớ tổng, temp I/O của truy vấn khác, khóa và tính đúng dữ liệu.

### 9.1. Một truy vấn mẫu xem thống kê pg_stat_statements

Nếu extension pg_stat_statements đã được cài đặt và cấu hình, có thể xem các câu lệnh có nhiều block đọc hoặc temporary I/O:

~~~sql
SELECT
    calls,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    blk_read_time,
    blk_write_time,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY (shared_blks_read + temp_blks_read + temp_blks_written) DESC
LIMIT 20;
~~~

Các bộ đếm là thống kê tích lũy trong khoảng theo dõi của extension, không phải phép đo riêng cho một lần chạy. Cần xem số lần gọi và khoảng thời gian thống kê được thu thập; một câu lệnh chạy rất nhiều lần có thể có tổng block cao dù mỗi lần chạy tương đối nhẹ.

Thời gian đọc/ghi phụ thuộc cấu hình theo dõi I/O timing. Kiểm tra đúng phiên bản PostgreSQL và trạng thái extension trước khi diễn giải các cột.

### 9.2. Kiểm tra temporary file ở cấp database

PostgreSQL có thống kê tạm ở cấp database trong các view thống kê phù hợp. Ví dụ:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_data
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

temp_files và temp_bytes là bộ đếm tích lũy theo database. Chúng giúp nhận biết database nào tạo nhiều dữ liệu tạm trong khoảng theo dõi, nhưng không tự chỉ ra truy vấn cụ thể. Cần ghép với pg_stat_statements, kế hoạch thực thi và thời điểm tải.

Ở các phiên bản PostgreSQL mới có thể có thêm view pg_stat_io với chi tiết I/O theo loại backend, đối tượng và ngữ cảnh. Cấu trúc và cột thay đổi theo phiên bản; hãy tra tài liệu tương ứng.

## 10. Sai lầm thường gặp khi phân tích buffer và spill

**Đồng nhất shared read với đọc vật lý từ đĩa.**  
Shared read cho biết DBMS phải nạp block vào shared buffers. Hệ điều hành hoặc tầng lưu trữ có thể phục vụ từ cache. Hãy đối chiếu I/O timing và số liệu thiết bị.

**Cho rằng buffer hit cao nghĩa là truy vấn nhanh.**  
Truy vấn vẫn có thể xử lý quá nhiều dòng, tốn CPU, chờ khóa hoặc truyền lượng dữ liệu lớn.

**Cộng buffer ở mọi nút kế hoạch.**  
Số liệu ở nút cha PostgreSQL bao gồm hoạt động của nút con. Cộng tất cả có thể đếm trùng.

**Chỉ nhìn số dòng trả về.**  
Một truy vấn trả 100 dòng có thể đã quét hàng triệu dòng. Xem actual rows, rows removed, loops và buffer usage.

**Thấy temp I/O là tăng work_mem ngay.**  
Cần kiểm tra cardinality, số dòng đầu vào, kích thước dữ liệu trung gian và mức đồng thời. Tăng bộ nhớ không có giới hạn có thể gây thiếu RAM.

**Xem một nút Sort mà bỏ qua dữ liệu đầu vào.**  
Sort spill có thể là hệ quả của việc truy vấn đưa quá nhiều dòng hoặc cột vào sort. Giảm đầu vào thường có lợi hơn chỉ tăng bộ nhớ.

**Bỏ qua số vòng lặp.**  
Một inner scan có thể chỉ đọc ít block mỗi lần nhưng được gọi hàng nghìn lần bởi nested loop. Cần xét loops cùng buffer và actual rows.

**So sánh hai kế hoạch với cache và tải khác nhau.**  
Buffer hit/read và thời gian có thể khác do trạng thái cache, tác vụ nền hoặc mức đồng thời. Ghi rõ điều kiện trước/sau.

**Dùng EXPLAIN ANALYZE tùy tiện trên câu lệnh ghi production.**  
EXPLAIN ANALYZE thực sự thực thi câu lệnh. Hãy dùng môi trường và dữ liệu phù hợp, hiểu rõ tác động của trigger, sequence và side effect.

## 11. Mẫu ghi nhận kết quả phân tích

Một báo cáo ngắn nhưng đủ bằng chứng có thể gồm:

| Mục | Nội dung cần ghi |
|---|---|
| Truy vấn | Fingerprint, tham số đại diện, mục tiêu nghiệp vụ |
| Môi trường | DBMS/version, cấu hình, kích thước dữ liệu |
| Tải | Tỷ lệ đọc/ghi, mức đồng thời, cửa sổ đo |
| Kế hoạch | Scan/join/sort/aggregate, estimate và actual rows, loops |
| Buffer | Shared hit/read/dirtied/written, local và temp blocks |
| I/O | I/O timing, độ trễ thiết bị, IOPS, throughput, queue |
| Memory spill | Sort method, Disk, hash batches, temp read/write |
| Kết luận | Nút thắt có bằng chứng, giả thuyết còn mở |
| Thay đổi | SQL, index, statistics hoặc cấu hình được thử |
| Kết quả | Latency, throughput, lỗi, buffer, temp I/O và tác dụng phụ |

Ví dụ kết luận có cơ sở:

“Truy vấn báo cáo trả về ít dòng nhưng Seq Scan đã xử lý gần ba triệu dòng và đọc 20.000 shared blocks. Actual rows lệch lớn so với estimate. Sort dùng top-N heapsort nên không có bằng chứng sort spill trong lần đo này. Cần kiểm tra thống kê và khả năng dùng chỉ mục ghép cho điều kiện lọc trước khi thay đổi cấu hình bộ nhớ.”

Hoặc:

“Truy vấn tổng hợp có HashAggregate nhiều batch và Sort dùng external merge; temporary blocks tăng cùng p95 dưới tải đồng thời. Đây là bằng chứng thao tác trung gian đang dùng temporary I/O. Cần kiểm tra cardinality, số nhóm, kích thước dữ liệu và tổng bộ nhớ theo mức đồng thời trước khi cân nhắc thay đổi work_mem.”

Một báo cáo tốt tách biệt dữ liệu quan sát được với giả thuyết và đề xuất. Điều này giúp người khác kiểm tra lại kết luận mà không phải dựa vào cảm nhận.

## 12. Kết luận

Thông tin buffer và temporary I/O trong kế hoạch thực thi giúp hiểu dữ liệu đã đi qua những tầng nào và thao tác trung gian có vượt bộ nhớ hay không. Shared hit/read cho biết hoạt động ở shared buffers; temp read/write, sort method và hash batches giúp phát hiện dữ liệu tạm; I/O timing và số liệu hệ điều hành giúp đánh giá độ trễ ở tầng lưu trữ.

Để phân tích chính xác, cần đọc actual rows, loops, buffer counts và cấu trúc nút cùng nhau. Không đồng nhất shared read với đọc vật lý, không cộng trùng buffer ở nút cha/con và không tăng bộ nhớ chỉ vì thấy spill. Hãy xác định nguyên nhân từ dữ liệu thực thi, chọn thay đổi phù hợp với SQL, chỉ mục, thống kê hoặc cấu hình, rồi đo lại dưới workload và mức đồng thời tương đương.

## Câu hỏi tự kiểm tra

1. Shared hit và shared read trong PostgreSQL khác nhau thế nào?
2. Vì sao shared read không chứng minh thiết bị lưu trữ đã thực hiện một lần đọc vật lý?
3. Các trường dirtied và written cho biết điều gì, và vì sao chúng không đại diện toàn bộ hoạt động ghi của hệ thống?
4. Temporary read/write có thể xuất hiện trong những loại thao tác nào?
5. Vì sao không nên cộng số buffer ở tất cả các nút trong kế hoạch PostgreSQL?
6. Một truy vấn trả về 100 dòng nhưng có Rows Removed by Filter lên đến hàng triệu. Bạn sẽ kiểm tra gì?
7. Sort Method external merge và Hash Batches lớn gợi ý vấn đề nào?
8. Vì sao tăng work_mem có thể gây áp lực bộ nhớ khi nhiều truy vấn chạy đồng thời?
9. Nếu buffer hit cao nhưng execution time vẫn lớn, những nguyên nhân nào cần kiểm tra?
10. Hãy mô tả cách kết hợp EXPLAIN ANALYZE, pg_stat_statements và số liệu thiết bị để xác nhận một giả thuyết I/O.

Một tối ưu được xác nhận khi phép đo lặp lại cho thấy thời gian hoặc thông lượng cải thiện, temporary I/O và lượng block được truy cập thay đổi theo hướng hợp lý, hệ thống vẫn ổn định dưới tải và tính đúng đắn của dữ liệu được giữ nguyên.

