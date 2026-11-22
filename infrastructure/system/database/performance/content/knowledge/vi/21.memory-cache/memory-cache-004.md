# Ngân sách bộ nhớ toàn hệ thống khi nhiều truy vấn chạy đồng thời

Bộ nhớ của một hệ quản trị cơ sở dữ liệu được chia sẻ giữa nhiều mục đích: cache trang dữ liệu và index, metadata, kết nối, vùng làm việc của truy vấn, thao tác sắp xếp và băm, tiến trình nền, replication và các thành phần nội bộ khác. Khi chỉ có một truy vấn chạy, một vùng nhớ lớn có thể giúp truy vấn hoàn thành nhanh. Nhưng khi nhiều truy vấn cùng chạy, nhu cầu bộ nhớ của từng truy vấn cộng dồn; hệ thống có thể phải ghi dữ liệu tạm ra đĩa, thu hẹp cache, chờ cấp phát bộ nhớ hoặc thậm chí bị hệ điều hành kết thúc tiến trình.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Bộ nhớ và bộ đệm** giúp người học xây dựng ngân sách bộ nhớ toàn hệ thống khi nhiều truy vấn chạy đồng thời. Bài học giải thích cách phân biệt vùng nhớ dùng chung và vùng nhớ theo truy vấn, cách concurrency làm nhân nhu cầu memory workspace, cách đọc memory grant và dấu hiệu spill, cũng như cách đặt giới hạn kết nối, kiểm soát đồng thời và phân bổ tài nguyên cho workload hỗn hợp.

Sau bài học, người học có thể:

- Phân loại các nhóm bộ nhớ của DBMS, tiến trình truy vấn, hệ điều hành và cache.
- Ước lượng nhu cầu bộ nhớ tổng thể thay vì chỉ tính theo một truy vấn đơn lẻ.
- Giải thích vì sao work_mem, sort/hash workspace hoặc memory grant có thể được cấp nhiều lần trong một truy vấn.
- Tính ảnh hưởng của số truy vấn đồng thời và nhóm workload đến ngân sách RAM.
- Nhận diện memory pressure, cache eviction, spill, paging và nguy cơ OOM.
- Đọc các chỉ số bộ nhớ trên PostgreSQL, SQL Server, MySQL InnoDB và Oracle.
- Thiết kế admission control, giới hạn concurrency và pool kết nối theo ngân sách.
- Kiểm chứng cấu hình bằng benchmark tải hỗn hợp, p95/p99, I/O tạm và độ ổn định.

## 1. Vì sao phải lập ngân sách bộ nhớ toàn hệ thống?

### 1.1. Bộ nhớ là tài nguyên dùng chung

Một máy chủ cơ sở dữ liệu không chỉ dành RAM cho dữ liệu được cache. RAM còn được sử dụng bởi:

- Cache trang dữ liệu và index.
- Metadata, catalog, lock table và cấu trúc quản lý giao dịch.
- Vùng làm việc cho sort, hash join, hash aggregate và các toán tử khác.
- Bộ nhớ theo kết nối hoặc theo session.
- Tiến trình nền như checkpoint, vacuum, purge, replication và backup.
- Thư viện, runtime, thread stack và vùng nhớ nội bộ của engine.
- Hệ điều hành, filesystem cache, agent giám sát và dịch vụ phụ trợ.

Nếu chỉ lấy tổng RAM rồi cấu hình cache chiếm gần hết, các truy vấn có thể thiếu workspace. Ngược lại, nếu dành quá nhiều RAM cho từng truy vấn, nhiều truy vấn đồng thời có thể chiếm hết bộ nhớ và làm hệ thống mất ổn định.

Mục tiêu của ngân sách bộ nhớ là duy trì đủ không gian cho cache có ích, các truy vấn đang chạy, tiến trình nền và hệ điều hành, kể cả khi tải tăng cao.

### 1.2. Một truy vấn riêng lẻ không đại diện cho tải đồng thời

Giả sử một truy vấn báo cáo cần khoảng 1,5 GB workspace để hash join và sort. Nếu chạy một mình, máy chủ có thể cấp đủ bộ nhớ và truy vấn hoàn thành nhanh.

Nếu 12 truy vấn tương tự chạy cùng lúc, nhu cầu workspace có thể lên đến khoảng 18 GB, chưa tính cache, session và tiến trình nền. Nếu RAM khả dụng không đủ, engine có thể giảm memory grant, cho phép spill ra đĩa, xếp hàng chờ hoặc từ chối cấp phát tùy hệ quản trị.

Vì vậy, câu hỏi vận hành không chỉ là “một truy vấn cần bao nhiêu RAM?” mà còn là:

- Có bao nhiêu truy vấn loại đó chạy cùng lúc?
- Những toán tử nào cần workspace trong mỗi truy vấn?
- Workspace có được cấp đồng thời hay theo từng giai đoạn?
- Bao nhiêu truy vấn có thể chạy đồng thời trong giờ cao điểm?
- Những workload khác còn cần bao nhiêu bộ nhớ?
- Khi vượt ngân sách, hệ thống sẽ chờ, spill, giảm grant hay bị OOM?

### 1.3. RAM lớn không tự động giải quyết mọi vấn đề

Tăng RAM có thể giúp tăng cache và giảm spill, nhưng không giải quyết mọi nút thắt:

- Query plan có thể xử lý quá nhiều dòng do cardinality estimate sai.
- Hash join có thể tạo bảng băm quá lớn do join fanout.
- Sort có thể sắp xếp tập dữ liệu lớn không cần thiết.
- Connection pool có thể cho phép quá nhiều truy vấn nặng cùng chạy.
- Một truy vấn có thể bị giới hạn bởi CPU, I/O hoặc lock thay vì bộ nhớ.
- Cache lớn hơn có thể không giúp nếu workload truy cập dữ liệu ngẫu nhiên và working set quá lớn.

Trước khi tăng bộ nhớ, cần xác định vùng nhớ nào thiếu, truy vấn nào tiêu thụ nhiều, có spill hay không và concurrency có vượt khả năng máy chủ hay không.

## 2. Phân loại các nhóm bộ nhớ

### 2.1. Bộ nhớ dùng chung của DBMS

Bộ nhớ dùng chung phục vụ nhiều session hoặc nhiều truy vấn. Tùy engine, nhóm này có thể gồm:

- Buffer pool hoặc shared buffers chứa trang dữ liệu và index.
- Shared metadata và catalog cache.
- Shared plan cache hoặc procedure cache.
- Lock manager, transaction table và cấu trúc đồng bộ.
- Shared memory cho communication giữa worker hoặc process.
- Các cấu trúc phục vụ replication và logging.

Bộ nhớ dùng chung giúp nhiều truy vấn tận dụng cùng một bản sao dữ liệu hoặc metadata. Nhưng nó cũng có thể cạnh tranh với workspace riêng của các truy vấn.

### 2.2. Bộ nhớ theo truy vấn hoặc theo session

Một truy vấn có thể cần vùng làm việc riêng cho:

- Sort và ORDER BY.
- Hash join.
- Hash aggregate hoặc GROUP BY.
- DISTINCT và set operation.
- Window function.
- Materialization hoặc spool.
- Temporary table và intermediate result.
- Các thao tác xử lý dữ liệu theo batch.

Một session cũng có thể giữ bộ nhớ cho cursor, prepared statement, biến session, temporary object và trạng thái giao dịch. Chi phí này phụ thuộc DBMS, driver và ứng dụng.

Không phải mọi vùng nhớ đều được cấp ngay khi kết nối mở. Nhiều engine cấp phát theo nhu cầu khi câu lệnh thực thi. Vì vậy, số kết nối không bằng số workspace đang hoạt động, nhưng số kết nối lớn vẫn tạo overhead và có thể cho phép quá nhiều truy vấn đồng thời.

### 2.3. Bộ nhớ của hệ điều hành

DBMS chạy trong môi trường hệ điều hành, nên cần để lại RAM cho:

- Kernel và các cấu trúc hệ thống.
- Filesystem cache hoặc page cache nếu engine dựa vào nó.
- Agent giám sát, backup, antivirus hoặc dịch vụ phụ trợ.
- Runtime, thư viện và tiến trình quản trị.
- Container runtime và các dịch vụ cùng máy nếu có.

Nếu DBMS được chạy trong container, cần xét memory limit của cgroup/container thay vì chỉ nhìn RAM vật lý của host. Tiến trình có thể bị OOM killer kết thúc khi vượt giới hạn container dù host vẫn còn RAM.

### 2.4. Cache dữ liệu và workspace có mục tiêu khác nhau

Cache giữ các trang đã đọc để giảm I/O khi truy cập lại. Workspace phục vụ tính toán tạm thời trong một truy vấn. Hai nhóm có cách sử dụng và vòng đời khác nhau.

Ví dụ:

- Buffer pool giữ trang bảng và index.
- Sort workspace giữ các run hoặc vùng dữ liệu cần sắp xếp.
- Hash workspace giữ bảng băm để nối hoặc tổng hợp.
- Temp memory có thể lưu intermediate result.
- OS page cache có thể giữ file data hoặc file tạm tùy cơ chế I/O.

Nếu workspace tăng đột biến, nó có thể làm giảm RAM còn lại cho cache. Nếu cache bị thu hẹp, truy vấn khác phải đọc lại dữ liệu từ storage, làm tăng I/O và độ trễ.

### 2.5. Không cộng trùng các chỉ số bộ nhớ

Khi đọc số liệu, cần hiểu phạm vi của từng chỉ số:

- Một số số liệu là memory committed hoặc reserved.
- Một số là memory resident thực sự trong RAM.
- Một số là memory grant được yêu cầu hoặc được cấp.
- Một số là cache capacity, không phải lượng trang đang dùng.
- Một số bộ đếm là tổng của process con hoặc worker.
- Một số vùng shared memory có thể xuất hiện trong nhiều góc nhìn.

Không cộng máy móc RSS của mọi process với shared memory nếu hệ điều hành đang tính chung vùng được ánh xạ. Tương tự, không cộng memory grant, buffer pool và cache theo cách làm trùng một vùng nhớ. Hãy xác định đơn vị, phạm vi và semantics trước khi lập ngân sách.

## 3. Mô hình ngân sách RAM

### 3.1. Chia ngân sách theo nhóm

Một mô hình khái quát:

\[
RAM_{total} =
RAM_{OS} +
RAM_{engine} +
RAM_{workspace} +
RAM_{reserve}
\]

Trong đó:

- \(RAM_{OS}\): hệ điều hành và dịch vụ phụ trợ.
- \(RAM_{engine}\): bộ nhớ dùng chung và overhead nền của DBMS.
- \(RAM_{workspace}\): vùng làm việc có thể phát sinh từ các truy vấn đồng thời.
- \(RAM_{reserve}\): phần dự phòng cho dao động tải, backup, checkpoint, maintenance và tình huống bất thường.

Đây là cách phân nhóm để lập kế hoạch, không phải công thức cấu hình trực tiếp cho mọi engine. Một số engine quản lý workspace bên trong vùng nhớ tổng thể; một số vùng dùng chung hoặc cache có thể co giãn theo tải.

### 3.2. Tính theo tải đồng thời

Với các nhóm truy vấn khác nhau, có thể ước lượng:

\[
RAM_{workspace} \approx
\sum_{i=1}^{n}
Concurrency_i \times PeakWorkspace_i
\]

Trong đó:

- \(Concurrency_i\): số truy vấn nhóm i có thể hoạt động đồng thời.
- \(PeakWorkspace_i\): workspace đỉnh quan sát được của một truy vấn thuộc nhóm i.

Phép tính này là mô hình bảo thủ nếu các đỉnh không xảy ra đồng thời hoặc workspace được cấp theo từng giai đoạn. Nhưng nó hữu ích để nhận diện nguy cơ khi cho phép nhiều truy vấn nặng cùng chạy.

Không nên lấy giá trị trung bình rồi bỏ qua đỉnh. Một số báo cáo có thể cần bộ nhớ lớn hơn nhiều so với truy vấn OLTP thông thường.

### 3.3. Ví dụ lập ngân sách cho máy chủ 64 GB

Giả sử một máy chủ có 64 GB RAM. Nhóm vận hành đưa ra ngân sách ban đầu như sau:

| Nhóm | Ngân sách giả định |
|---|---:|
| Hệ điều hành và agent | 8 GB |
| Bộ nhớ dùng chung và overhead DBMS | 36 GB |
| Dự phòng cho dao động và tác vụ nền | 4 GB |
| Workspace truy vấn còn lại | 16 GB |
| **Tổng** | **64 GB** |

Workspace 16 GB được chia theo workload:

| Nhóm truy vấn | Concurrency tối đa | Workspace đỉnh mỗi truy vấn | Nhu cầu ước lượng |
|---|---:|---:|---:|
| OLTP nhẹ | 20 | 128 MB | 2,5 GB |
| Báo cáo trung bình | 4 | 1 GB | 4 GB |
| Phân tích nặng | 2 | 3 GB | 6 GB |
| **Tổng** | **26** |  | **12,5 GB** |

Trong ví dụ này còn khoảng 3,5 GB workspace chưa sử dụng trong ngân sách 16 GB. Phần còn lại là khoảng an toàn cho sai số và dao động trong các nhóm.

Nếu cho phép thêm 2 truy vấn phân tích nặng, nhu cầu có thể tăng thêm 6 GB và vượt ngân sách. Hệ thống có thể spill, thu hẹp cache hoặc chịu áp lực RAM. Khi đó, cần giới hạn concurrency, xếp hàng truy vấn nặng hoặc điều chỉnh truy vấn trước khi nâng mức cấp phát.

Các con số chỉ minh họa cách tính. Khi vận hành, dùng số liệu peak theo workload thực tế, không lấy cấu hình ví dụ làm khuyến nghị cố định.

### 3.4. Dự phòng không phải bộ nhớ lãng phí

Không nên lập ngân sách sao cho tổng mức sử dụng dự kiến luôn bằng 100% RAM. Hệ thống cần khoảng trống để hấp thụ:

- Tăng đột biến số truy vấn.
- Hash hoặc sort lớn hơn estimate.
- Backup, restore, checkpoint hoặc vacuum.
- Tăng số worker song song.
- Tải nền và tiến trình hệ điều hành.
- Cache warm-up sau restart.
- Tác vụ quản trị hoặc triển khai.

Dự phòng cần dựa trên biến động đo được và mức rủi ro chấp nhận được. Không có một tỷ lệ dự phòng đúng cho mọi hệ thống.

### 3.5. Peak, percentile và headroom

Để lập ngân sách, hãy ghi nhận nhiều mức:

- Trung bình trong giờ bình thường.
- p95 và p99 của bộ nhớ theo truy vấn hoặc workload.
- Peak trong giờ cao điểm.
- Peak khi chạy báo cáo, backup hoặc maintenance.
- Peak khi tăng concurrency.
- Mức sử dụng khi cache lạnh hoặc sau restart.

Một truy vấn hiếm có thể có peak lớn nhưng không cần giữ chỗ liên tục nếu admission control bảo đảm chỉ chạy một hoặc hai truy vấn cùng lúc. Ngược lại, nhiều truy vấn nhỏ nhưng chạy đồng thời cao có thể tạo tổng nhu cầu lớn.

## 4. Concurrency làm nhân nhu cầu bộ nhớ như thế nào?

### 4.1. Nhiều toán tử trong một truy vấn

Một truy vấn có thể chứa nhiều toán tử cần workspace:

- Hash join ở một nhánh.
- Sort trước window function.
- Hash aggregate ở phía trên.
- Materialization hoặc spool.
- Sort cuối cùng cho ORDER BY.

Không phải mọi toán tử đều nhất thiết giữ bộ nhớ đỉnh cùng lúc. Một số có thể hoạt động theo pipeline, một số có thể cần giữ dữ liệu cho đến khi node cha tiêu thụ xong. Vì vậy, không nên lấy số node nhân thẳng với một tham số rồi coi đó là lượng RAM chính xác.

Hãy dùng actual memory grant, operator memory, peak memory hoặc số liệu runtime của DBMS khi có. Nếu chỉ có cấu hình giới hạn như work_mem, hãy tính cả số node có thể dùng đồng thời và số truy vấn đồng thời như một upper-bound để kiểm soát rủi ro.

### 4.2. Một truy vấn có thể tạo nhiều vùng workspace

Ví dụ truy vấn:

~~~sql
SELECT
    customer_id,
    product_category,
    SUM(amount) AS revenue
FROM sales
WHERE sale_date >= :start_date
  AND sale_date < :end_date
GROUP BY customer_id, product_category
ORDER BY revenue DESC
LIMIT 100;
~~~

Kế hoạch có thể cần:

1. Scan dữ liệu trong khoảng ngày.
2. Hash aggregate theo customer_id và product_category.
3. Sort hoặc top-N theo revenue.

Nếu dữ liệu đầu vào lớn, hash table có thể tăng đáng kể. Nếu kết quả aggregate vẫn lớn, bước sort cũng cần workspace. Cấu hình cho một operator không phải lúc nào cũng là giới hạn tổng của cả truy vấn.

### 4.3. Parallel query tăng số worker và vùng nhớ

Một truy vấn song song có thể dùng nhiều worker. Mỗi worker có thể có workspace riêng hoặc được tính vào memory grant chung theo quy tắc của engine. Vì vậy, tăng degree of parallelism có thể làm tăng tổng memory consumption và CPU usage.

Cần kiểm tra:

- Số worker thực tế được khởi chạy.
- Memory grant hoặc workspace theo worker.
- Dữ liệu có được chia đều không.
- Có worker nào bị skew và giữ dữ liệu lớn hơn không.
- Số truy vấn song song chạy cùng lúc.
- Tác động đến các truy vấn OLTP khác.

Parallelism giúp giảm elapsed time trong một số truy vấn nhưng có thể tăng tài nguyên tổng và làm giảm số truy vấn có thể chạy đồng thời.

### 4.4. Số kết nối khác số truy vấn đang tiêu thụ workspace

Một connection idle thường tiêu thụ ít hơn một query đang chạy hash join, nhưng vẫn có overhead session, process/thread, stack, trạng thái transaction và cache riêng. Nhiều connection có thể làm tăng:

- Bộ nhớ cố định theo session.
- Số thread hoặc process.
- Lock và transaction metadata.
- Khả năng nhiều query cùng được gửi xuống DBMS.
- Context switching và contention.

Connection pool cần giới hạn số kết nối hoạt động và tách số kết nối chờ khỏi số truy vấn thực sự chạy. Pool quá lớn có thể làm tăng concurrency vượt ngân sách.

### 4.5. Little's Law và hàng đợi

Một cách nhìn đơn giản về tải:

\[
ActiveConcurrency \approx Throughput \times AverageLatency
\]

Nếu hệ thống xử lý 200 truy vấn/giây và thời gian trung bình mỗi truy vấn là 0,1 giây, mức concurrency trung bình xấp xỉ 20 truy vấn đang hoạt động. Khi latency tăng lên 0,5 giây trong khi throughput vẫn được yêu cầu giữ 200/giây, số truy vấn đồng thời có thể tăng lên khoảng 100 nếu không có admission control.

Đây là quan hệ theo trung bình của hệ thống ổn định, không phải dự báo chính xác cho peak hoặc p99. Nó cho thấy khi truy vấn chậm lại, số truy vấn đang tồn tại có thể tăng, kéo theo bộ nhớ theo session và workspace tăng thêm.

## 5. Memory grant và workspace của truy vấn

### 5.1. Vì sao DBMS cấp phát workspace?

Sort, hash join và hash aggregate thường cần bộ nhớ để giữ dữ liệu trung gian. DBMS ước lượng số dòng, row width và cấu trúc toán tử để xác định lượng workspace cần thiết.

Nếu cấp quá ít:

- Sort có thể tạo nhiều run và merge từ đĩa.
- Hash join có thể chia nhiều batch.
- Hash aggregate có thể spill partition ra temp storage.
- Query latency và temp I/O tăng.

Nếu cấp quá nhiều:

- Ít truy vấn có thể được cấp grant đồng thời.
- Memory pressure tăng.
- Cache có thể bị thu hẹp.
- Query khác phải chờ memory grant.
- Một truy vấn ước lượng sai có thể giữ bộ nhớ lớn trong thời gian dài.

Cấp phát hợp lý cần cân bằng giữa khả năng tránh spill và khả năng cho nhiều truy vấn chạy đồng thời.

### 5.2. Memory grant khác với bộ nhớ thực sự dùng

Một số DBMS yêu cầu hoặc cấp một memory grant trước khi thực hiện một truy vấn. Grant có thể lớn hơn lượng bộ nhớ thực tế truy vấn sử dụng. Vì vậy, cần phân biệt:

- Requested memory: truy vấn yêu cầu.
- Granted memory: engine cấp.
- Used/peak memory: truy vấn thực sự dùng.
- Memory wait: thời gian chờ được cấp grant.
- Spill: dữ liệu phải ghi ra vùng tạm vì workspace không đủ.

Một truy vấn có grant lớn nhưng dùng ít có thể làm giảm concurrency nếu grant được giữ trong thời gian thực thi. Cần theo dõi chênh lệch giữa granted và used, cùng thời gian chờ grant.

### 5.3. Ước lượng sai làm grant sai

Nếu optimizer ước lượng số dòng thấp hơn thực tế, nó có thể cấp grant quá nhỏ và gây spill. Nếu estimate quá cao, nó có thể cấp grant lớn hơn cần thiết và hạn chế concurrency.

Nguyên nhân có thể gồm:

- Statistics cũ.
- Phân bố lệch.
- Tương quan giữa nhiều cột.
- Parameter sniffing hoặc parameter sensitivity.
- Predicate phức tạp.
- Join fanout.
- Row width thực tế lớn hơn estimate.

Khi thấy spill hoặc grant bất thường, kiểm tra estimated rows so với actual rows trước khi chỉ tăng bộ nhớ.

### 5.4. Spill là cơ chế bảo vệ nhưng có chi phí

Spill cho phép truy vấn tiếp tục khi workspace không đủ bằng cách ghi dữ liệu trung gian ra đĩa hoặc temp storage. Đây không nhất thiết là lỗi, nhưng có thể làm latency tăng mạnh.

Dấu hiệu thường gặp:

- Sort spill hoặc external merge.
- Hash join nhiều batch.
- Temporary blocks read/written.
- Tempdb hoặc temporary tablespace tăng I/O.
- Query latency tăng khi concurrency cao.
- Disk latency tăng ở volume lưu dữ liệu tạm.

Một spill nhỏ ở truy vấn ít quan trọng có thể chấp nhận được. Spill thường xuyên trên truy vấn quan trọng hoặc spill đồng thời của nhiều query có thể trở thành nút thắt.

## 6. PostgreSQL: shared_buffers, work_mem và concurrency

### 6.1. Shared buffers

PostgreSQL dùng shared_buffers làm vùng cache trang dữ liệu dùng chung. Đây là một phần bộ nhớ lớn của instance, nhưng hệ điều hành cũng có thể cache file data. Vì vậy, tổng cache hiệu quả không chỉ là shared_buffers.

Khi tăng shared_buffers:

- Có thể tăng số trang DBMS giữ trực tiếp.
- Có thể giảm một số lần đọc từ storage.
- Có thể tăng RAM resident của PostgreSQL.
- Có thể làm giảm RAM còn lại cho workspace và OS page cache nếu tổng ngân sách không thay đổi.

Không đặt shared_buffers theo một tỷ lệ cố định mà bỏ qua RAM cho connection, work_mem, parallel workers và hệ điều hành.

### 6.2. work_mem không phải ngân sách của cả server

Trong PostgreSQL, work_mem là lượng bộ nhớ cơ sở tối đa cho một thao tác sort hoặc hash trước khi chuyển sang phương thức dùng tệp tạm, theo semantics của từng node. Nó không phải một vùng nhớ duy nhất được chia đều cho toàn server.

Một truy vấn có thể có nhiều sort/hash node; nhiều session có thể chạy cùng lúc; parallel worker cũng có thể phát sinh workspace riêng. Với hash operation, hash_mem_multiplier có thể điều chỉnh giới hạn tương ứng so với work_mem theo phiên bản.

Vì vậy, đặt work_mem quá cao có thể làm tổng bộ nhớ tăng vượt RAM khi nhiều truy vấn phức tạp đồng thời.

### 6.3. Ví dụ rủi ro work_mem

Giả sử:

- work_mem = 64 MB.
- 30 truy vấn cùng chạy.
- Mỗi truy vấn có 3 thao tác sort/hash có thể cần workspace.
- Một số thao tác hoạt động đồng thời.

Một upper-bound đơn giản có thể lên tới:

\[
30 \times 3 \times 64\ MB = 5.760\ MB
\]

Tức khoảng 5,6 GiB, chưa tính hash_mem_multiplier, parallel worker, shared buffers và các vùng khác. Đây không phải dự báo chính xác vì mọi node có thể không đạt giới hạn cùng lúc, nhưng cho thấy work_mem không nên được nhân với một con số session đơn giản rồi bỏ qua số operator.

### 6.4. Điều chỉnh theo vai trò truy vấn

Có thể giữ work_mem mặc định tương đối thận trọng và điều chỉnh riêng cho một transaction hoặc session báo cáo khi đã đo rõ nhu cầu:

~~~sql
BEGIN;
SET LOCAL work_mem = '128MB';

SELECT
    customer_id,
    SUM(amount)
FROM sales
GROUP BY customer_id
ORDER BY SUM(amount) DESC;

COMMIT;
~~~

SET LOCAL chỉ có hiệu lực trong transaction hiện tại. Cần giới hạn số báo cáo đồng thời và đánh giá tổng workspace nếu nhiều session dùng mức cao.

Không nâng work_mem toàn cục chỉ để chữa một truy vấn riêng lẻ. Trước tiên xem plan, cardinality, index, sort/hash spill và khả năng giảm dữ liệu đầu vào.

### 6.5. Theo dõi spill và temporary I/O

PostgreSQL có thể hiển thị thông tin sort method, memory hoặc disk trong EXPLAIN ANALYZE. BUFFERS có thể cho thấy temporary blocks read/written. Statistics về temp files và temp_bytes giúp xác định workload tạo nhiều dữ liệu tạm.

Cần xem theo truy vấn và cửa sổ đo. Tổng temp_bytes của instance cho biết xu hướng nhưng không tự chỉ ra query nào gây ra.

## 7. SQL Server: memory grant và Resource Semaphore

### 7.1. Query memory grant

SQL Server cấp memory grant cho các truy vấn cần workspace như sort và hash. Grant được ước lượng từ execution plan, cardinality, row width, operator và degree of parallelism.

Nếu bộ nhớ cho query grant đang cạn, truy vấn có thể chờ trên resource semaphore. Một truy vấn có thể có latency cao dù CPU chưa bão hòa vì đang đợi grant.

### 7.2. Requested, granted và used memory

Actual execution plan và các DMV có thể cung cấp thông tin về memory grant. Cần so sánh requested, granted, ideal và used memory nếu phiên bản hỗ trợ.

Một grant quá lớn có thể làm ít truy vấn khác được chạy đồng thời. Một grant quá nhỏ có thể gây spill vào tempdb.

### 7.3. Memory grant feedback

Một số phiên bản SQL Server có memory grant feedback để điều chỉnh grant dựa trên hành vi thực thi trước đó. Cơ chế này có thể giảm overgrant hoặc undergrant trong một số workload.

Tuy nhiên, feedback không thay thế việc sửa thống kê, cardinality estimate và query shape. Với parameter-sensitive workload hoặc phân bố biến động, grant có thể vẫn khó ổn định. Cần quan sát qua nhiều lần thực thi và phiên bản đang dùng.

### 7.4. Theo dõi query memory

Có thể xem truy vấn đang chờ memory grant và lượng bộ nhớ liên quan qua các DMV như:

~~~sql
SELECT
    session_id,
    requested_memory_kb,
    granted_memory_kb,
    required_memory_kb,
    used_memory_kb,
    max_used_memory_kb,
    wait_time_ms,
    queue_id,
    wait_order
FROM sys.dm_exec_query_memory_grants;
~~~

Tên cột và quyền truy cập phụ thuộc phiên bản SQL Server. Cần lọc theo session/query phù hợp và chụp dữ liệu trong giờ cao điểm.

Theo dõi thêm:

- RESOURCE_SEMAPHORE waits.
- Sort/hash spill warnings trong actual plan.
- Tempdb I/O và dung lượng.
- Memory clerks và buffer pool.
- Target/Total Server Memory.
- Query Store để tìm query có grant và latency bất thường.

### 7.5. max server memory không phải giới hạn mọi byte của SQL Server

max server memory điều khiển phần bộ nhớ SQL Server được phép quản lý trong phạm vi quy định, nhưng không có nghĩa mọi thành phần ngoài phạm vi đó đều bằng không. Hệ điều hành, driver, thread stack, backup và một số allocation khác vẫn cần RAM.

Khi đặt max server memory, phải để lại headroom cho OS và dịch vụ phụ trợ. Nếu SQL Server chạy cùng ứng dụng khác trên một host, ngân sách phải tính cả chúng.

## 8. MySQL InnoDB: buffer pool và bộ nhớ theo kết nối

### 8.1. InnoDB buffer pool

InnoDB buffer pool giữ trang dữ liệu và index. Đây thường là vùng bộ nhớ lớn nhất của một instance MySQL chuyên dụng.

Tăng buffer pool có thể cải thiện cache hit nếu working set thường xuyên được truy cập. Nhưng vẫn phải để RAM cho:

- Connection và thread.
- Sort/join/read buffers.
- Temporary table.
- Table metadata và dictionary.
- Performance Schema.
- Redo log buffer và các cấu trúc nội bộ.
- OS và các tiến trình khác.

### 8.2. Bộ nhớ theo session và operation

Một số buffer của MySQL được cấp khi cần cho từng connection hoặc operation. Ví dụ sort buffer, join buffer, read buffer và read-rnd buffer có thể phát sinh theo loại truy vấn. Một số biến cấu hình có thể được cấp cho mỗi thread hoặc mỗi operation, tùy cơ chế và phiên bản.

Nếu tăng các buffer này lên cao rồi cho hàng trăm connection hoạt động, tổng bộ nhớ có thể tăng nhanh. Không nên nhân tất cả biến cấu hình với max_connections như một con số chính xác, nhưng đây là phép kiểm tra upper-bound hữu ích để phát hiện cấu hình rủi ro.

### 8.3. max_connections và connection pool

max_connections đặt giới hạn kết nối, nhưng không bảo đảm tất cả kết nối đều tiêu thụ bộ nhớ giống nhau. Một connection idle vẫn có overhead; connection chạy sort hoặc temporary table có thể dùng nhiều hơn.

Cần đặt pool ở tầng ứng dụng để tránh mở quá nhiều session, đồng thời theo dõi active threads và số truy vấn thực sự chạy. Tăng max_connections để xử lý hàng đợi có thể làm bộ nhớ và context switching xấu hơn.

### 8.4. Temporary table và spill

MySQL có thể dùng internal temporary table cho một số truy vấn GROUP BY, DISTINCT, UNION, window function hoặc sort. Khi dữ liệu vượt ngưỡng hoặc không phù hợp với memory engine, temporary data có thể chuyển sang storage tạm tùy phiên bản và cấu hình.

Theo dõi temporary tables, temporary tables on disk, sort merge passes, Created_tmp_disk_tables và I/O của thư mục tạm. Tên và cách tính các status variable cần kiểm tra theo phiên bản MySQL.

### 8.5. Theo dõi buffer pool

Các chỉ số cần quan sát gồm:

- Buffer pool size và free pages.
- Database pages và dirty pages.
- Buffer pool reads và read requests.
- Page flushing và checkpoint pressure.
- Active connections và running threads.
- Temporary tables on disk.
- Sort merge passes.
- Process RSS và memory limit của container.

Buffer pool hit ratio cao không có nghĩa hệ thống không thiếu RAM. Cần xem cả query workspace, temporary I/O, OS pressure và latency.

## 9. Oracle: SGA, PGA và vùng nhớ session

### 9.1. SGA dùng chung

System Global Area (SGA) là vùng nhớ dùng chung của Oracle instance, bao gồm các thành phần như database buffer cache, shared pool, redo log buffer và các cấu trúc khác tùy cấu hình.

SGA hỗ trợ cache dữ liệu, SQL/PLSQL và metadata. Tăng SGA có thể giúp một số workload nhưng làm giảm RAM khả dụng cho PGA, process và OS nếu tổng RAM cố định.

### 9.2. PGA theo process và work area

Program Global Area (PGA) là vùng nhớ riêng của server process hoặc background process. Work area cho sort, hash join, bitmap operation và một số thao tác khác thường nằm trong PGA.

Khi work area không đủ, Oracle có thể dùng temporary tablespace. Một truy vấn song song có thể có nhiều process và vùng nhớ liên quan. Vì vậy, PGA aggregate có thể tăng theo số query và worker đồng thời.

### 9.3. PGA_AGGREGATE_TARGET và giới hạn

PGA_AGGREGATE_TARGET là mục tiêu quản lý tổng PGA cho instance, không phải lúc nào cũng là một hard cap tuyệt đối. Cấu hình giới hạn cứng và hành vi phụ thuộc phiên bản, tham số và chế độ quản lý bộ nhớ.

Cần theo dõi tổng PGA allocated, PGA in use, work area executions optimal/one-pass/multipass và temporary I/O. Một tỷ lệ lớn one-pass hoặc multipass có thể cho thấy work area thiếu so với nhu cầu.

### 9.4. Theo dõi work area

Các dynamic performance views như V$PGASTAT, V$SQL_WORKAREA và V$SQL_WORKAREA_ACTIVE có thể giúp quan sát PGA và work area. AWR/ASH có thể cung cấp lịch sử nếu môi trường được cấp quyền và sử dụng tính năng phù hợp.

Cần kiểm tra license và chính sách tổ chức khi dùng các tính năng chẩn đoán có điều kiện license. Không giả định mọi môi trường Oracle đều được phép dùng mọi báo cáo.

## 10. Áp lực bộ nhớ, cache eviction và OOM

### 10.1. Memory pressure

Memory pressure xảy ra khi tổng nhu cầu RAM tiến gần hoặc vượt lượng khả dụng. Hệ thống có thể phản ứng bằng cách:

- Thu hẹp cache hoặc đẩy trang ít dùng ra ngoài.
- Spill workspace xuống đĩa.
- Chờ cấp memory grant.
- Tăng page fault hoặc paging.
- Từ chối allocation.
- Kích hoạt OOM killer hoặc làm process bị kết thúc.

Mỗi DBMS và OS có cơ chế riêng. Cần xem cả số liệu engine lẫn hệ điều hành.

### 10.2. Cache eviction không giống OOM

Cache eviction là việc thay thế trang cache để nhường chỗ cho trang khác. Đây là hành vi bình thường của cache. Nó trở thành vấn đề khi working set nóng bị đẩy ra liên tục, dẫn đến đọc storage lặp lại và tăng latency.

OOM xảy ra khi hệ điều hành hoặc container không thể đáp ứng thêm nhu cầu bộ nhớ và phải kết thúc tiến trình hoặc container. OOM là sự cố nghiêm trọng hơn nhiều so với cache miss thông thường.

### 10.3. Paging và swap

Swap có thể giúp hệ điều hành duy trì hoạt động khi RAM thiếu, nhưng database workload nhạy với latency. Nếu các trang đang hoạt động của DBMS bị swap ra/vào, thời gian truy cập có thể tăng mạnh.

Không nên xem swap như phần mở rộng RAM có hiệu năng tương đương. Cần theo dõi swap-in/swap-out, major page faults, memory pressure và OOM events. Cấu hình swap phù hợp phụ thuộc OS và chính sách vận hành.

### 10.4. Container memory limit

Trong môi trường container, DBMS có thể nhìn thấy host RAM nhưng bị giới hạn bởi cgroup memory.max hoặc giới hạn tương đương. Một cấu hình cache dựa trên RAM host có thể vượt giới hạn container.

Cần kiểm tra:

- Memory limit và current usage của container.
- Memory usage của process DBMS.
- Cgroup OOM events.
- Shared memory mount và giới hạn IPC nếu có.
- Memory request/limit trong hệ thống điều phối container.
- Headroom cho sidecar, agent và tiến trình trong cùng container/pod.

Nếu container bị OOM kill, tăng RAM host mà không tăng limit có thể không giải quyết vấn đề.

### 10.5. NUMA và phân bố bộ nhớ

Trên máy chủ nhiều socket, NUMA có thể làm latency truy cập bộ nhớ khác nhau tùy node. Một process hoặc worker có thể truy cập RAM ở node xa, gây chi phí bổ sung.

Cần xem NUMA topology, CPU affinity và memory policy khi có bằng chứng latency bộ nhớ hoặc phân bố không cân bằng. Không thay đổi binding hoặc interleave chỉ dựa trên suy đoán; cần benchmark trên phần cứng thật.

## 11. Admission control và giới hạn concurrency

### 11.1. Vì sao cần admission control?

Nếu mọi request đều được chạy ngay khi đến, một đợt tăng tải có thể làm quá nhiều query nặng đồng thời chiếm workspace. Admission control quyết định truy vấn nào được phép bắt đầu, truy vấn nào phải chờ, bị giới hạn hoặc chuyển sang hàng đợi khác.

Mục tiêu là giữ tổng nhu cầu tài nguyên trong ngân sách, bảo vệ latency của workload quan trọng và tránh hệ thống rơi vào trạng thái quá tải kéo dài.

### 11.2. Phân nhóm workload

Có thể chia workload thành:

| Nhóm | Ví dụ | Đặc điểm tài nguyên |
|---|---|---|
| OLTP nhẹ | Tra cứu theo khóa, cập nhật một hàng | Workspace nhỏ, latency nhạy |
| OLTP phức tạp | Nhiều join, aggregate nhỏ | Workspace vừa, cần kiểm soát p95 |
| Báo cáo | GROUP BY, ORDER BY, join lớn | Có thể cần memory grant lớn |
| Phân tích nặng | Scan lớn, hash join, window | CPU, RAM và I/O cao |
| Bảo trì | Backup, vacuum, index rebuild | Có thể tạo tải nền và I/O lớn |

Mỗi nhóm có thể có concurrency cap, timeout, queue riêng hoặc mức ưu tiên khác nhau.

### 11.3. Connection pool không phải admission control hoàn chỉnh

Connection pool giới hạn số kết nối, nhưng một kết nối có thể chạy query rất nặng và nhiều kết nối có thể chạy nhiều query khác nhau. Cần kết hợp:

- Giới hạn connection.
- Giới hạn active query theo workload.
- Hàng đợi ở ứng dụng hoặc proxy.
- Timeout và cancellation.
- Resource group hoặc workload management của DBMS nếu có.
- Giới hạn parallelism cho query nặng.
- Lịch chạy báo cáo và bảo trì.

Một pool 100 connection không có nghĩa hệ thống nên cho phép 100 hash join lớn chạy đồng thời.

### 11.4. Hạn mức theo ngân sách

Một mô hình admission đơn giản:

~~~text
Khi request đến:
  Xác định workload class
  Ước lượng mức tài nguyên hoặc dùng quota của class
  Nếu còn ngân sách và concurrency:
      Cho phép query bắt đầu
  Nếu vượt giới hạn:
      Đưa vào queue, giảm mức xử lý hoặc từ chối có kiểm soát
  Khi query kết thúc:
      Thu hồi quota và đánh thức request đang chờ
~~~

Trong hệ thống thật, cần xử lý timeout trong queue, hủy request từ client, fairness giữa tenant, retry storm và request có thời gian chạy dài. Không giữ slot vô hạn cho một request đã bị client bỏ.

### 11.5. Ưu tiên workload quan trọng

OLTP có thể cần latency thấp và ổn định, trong khi báo cáo có thể chấp nhận chờ. Nếu hai nhóm dùng chung tài nguyên, nên xác định SLO và quota phù hợp.

Ví dụ:

- Dành phần concurrency nhất định cho OLTP.
- Giới hạn số báo cáo nặng.
- Chạy batch vào giờ thấp điểm.
- Giới hạn parallel workers cho workload phân tích.
- Đặt timeout khác nhau theo nhóm.
- Ngăn một tenant chiếm toàn bộ query slots.

Các mức cụ thể cần dựa trên đo tải, không sao chép nguyên xi giữa các môi trường.

## 12. Tối ưu query trước khi tăng ngân sách

### 12.1. Giảm cardinality và row width

Hash join hoặc sort trên nhiều triệu dòng có thể cần nhiều bộ nhớ. Trước khi tăng memory grant, xem có thể:

- Lọc dữ liệu sớm theo điều kiện hợp lệ.
- Chỉ chọn các cột cần thiết.
- Tránh SELECT *.
- Tổng hợp trước khi nối nếu bảo toàn semantics.
- Dùng EXISTS khi chỉ cần kiểm tra tồn tại.
- Loại bỏ JOIN không cần thiết.
- Dùng index để giảm số dòng đầu vào.
- Tránh sort hoặc DISTINCT không cần thiết.

Giảm số dòng và độ rộng dòng có thể làm workspace giảm mạnh.

### 12.2. Sửa cardinality estimate

Nếu estimate thấp hơn actual rows nhiều lần, memory grant có thể không đủ. Nếu estimate quá cao, grant có thể lãng phí. Hãy kiểm tra:

- Statistics có mới không?
- Có data skew hoặc correlation giữa các cột không?
- Parameter value có phân bố khác nhau không?
- Join condition có thiếu cột không?
- Có implicit cast hoặc expression làm optimizer khó ước lượng không?
- Có thể dùng extended statistics, histogram hoặc cơ chế tương ứng không?

Sửa estimate thường giúp cả lựa chọn join algorithm và memory grant.

### 12.3. Giảm parallelism khi workspace bị nhân lên

Nếu parallel query tạo nhiều worker và mỗi worker dùng workspace riêng, tổng RAM có thể tăng. Giảm degree of parallelism có thể giảm peak memory nhưng tăng elapsed time của query.

Cần đo throughput toàn hệ thống. Một truy vấn riêng chạy nhanh hơn nhưng làm giảm số truy vấn OLTP được phục vụ có thể không phải kết quả tốt.

### 12.4. Giới hạn dữ liệu trung gian

Một truy vấn có thể materialize tập dữ liệu lớn mà ứng dụng chỉ cần một phần. Hãy xem có thể dùng keyset pagination, top-N, filter sớm hoặc xử lý theo batch không.

Tuy nhiên, thêm LIMIT vào truy vấn tổng hợp có thể thay đổi kết quả nghiệp vụ. Mọi biến đổi phải giữ đúng semantics và được kiểm chứng.

## 13. Đo bộ nhớ theo truy vấn và toàn hệ thống

### 13.1. Bộ chỉ số toàn hệ thống

Ghi nhận theo chu kỳ và trong giờ cao điểm:

- RAM total, available và committed.
- Process RSS/working set của DBMS.
- Shared memory và vùng cache.
- Buffer pool/shared buffer hit/read.
- Workspace hoặc memory grant đang dùng.
- Memory grant wait và queue.
- Temp file/tempdb/temp tablespace I/O.
- Swap-in/swap-out và major page faults.
- OOM events và container memory pressure.
- Số connection, active session và running query.
- Số worker song song.
- CPU utilization và storage latency.

Cần ghi cùng timestamp để liên hệ memory pressure với query latency, spill và I/O.

### 13.2. Bộ chỉ số theo truy vấn

Khi DBMS hỗ trợ, thu thập:

- Query fingerprint hoặc plan identifier.
- Estimated rows và actual rows.
- Requested/granted/used/peak memory.
- Số sort/hash operator.
- Spill count, spill bytes hoặc temp blocks.
- Logical reads và physical reads.
- CPU time và elapsed time.
- Parallel worker count.
- Wait time, memory grant wait.
- Số lần thực thi và mức concurrency.

Không phải engine nào cũng cung cấp mọi chỉ số. Hãy dùng công cụ phù hợp và ghi rõ giới hạn của dữ liệu.

### 13.3. PostgreSQL

Các nguồn hữu ích gồm:

- pg_stat_activity để xem session và query đang chạy.
- pg_stat_database để theo dõi temp_files và temp_bytes.
- EXPLAIN (ANALYZE, BUFFERS) để xem sort method, memory/disk, hash batches và temporary blocks.
- pg_stat_statements để tổng hợp thời gian, calls và block I/O.
- pg_buffercache nếu extension được cài và được phép dùng để xem trạng thái buffer.
- OS metrics để quan sát RSS, swap và cgroup memory.

Một số thông tin workspace chỉ xuất hiện chi tiết trong EXPLAIN của truy vấn thử. Temp_bytes tích lũy ở cấp database không tự xác định truy vấn nào gây ra; cần kết hợp query fingerprint hoặc logging phù hợp.

### 13.4. SQL Server

Các nguồn hữu ích gồm:

- sys.dm_exec_query_memory_grants.
- sys.dm_os_memory_clerks.
- sys.dm_os_process_memory.
- sys.dm_exec_requests và wait statistics.
- Actual execution plan với spill warnings.
- Query Store và Extended Events cho workload history.
- Tempdb file I/O và allocation metrics.

DMV có quyền truy cập và semantics phụ thuộc phiên bản. Cần lấy snapshot theo thời điểm và phân biệt memory committed, target, granted và used.

### 13.5. MySQL

Các nguồn hữu ích gồm:

- Performance Schema memory summary.
- Global status variables về connection, temporary table và sort.
- InnoDB buffer pool status.
- SHOW ENGINE INNODB STATUS.
- sys schema và statement digest.
- OS process memory, cgroup và swap metrics.

Instrumentation của Performance Schema có thể chưa bật cho mọi allocation. Một số chỉ số không bao phủ toàn bộ memory của process. Cần đọc tài liệu đúng phiên bản và kết hợp số liệu OS.

### 13.6. Oracle

Các nguồn hữu ích gồm:

- V$SGAINFO và V$SGASTAT cho SGA.
- V$PGASTAT cho PGA.
- V$SQL_WORKAREA và V$SQL_WORKAREA_ACTIVE cho work area.
- V$PROCESS_MEMORY cho một số vùng nhớ process.
- V$SESSION và V$SQL để liên hệ session với SQL.
- AWR/ASH nếu môi trường có quyền và license phù hợp.
- OS metrics cho process memory, swap và paging.

Các view có phạm vi và quyền truy cập riêng. Không suy ra PGA của một câu SQL bằng cách cộng các số liệu session mà không kiểm tra định nghĩa.

## 14. Tình huống thực tế: giờ cao điểm xuất hiện spill và latency tăng

### 14.1. Hiện tượng

Một hệ thống thương mại có 64 GB RAM. Ban ngày, OLTP thường ổn định. Khi chạy báo cáo cuối ngày, nhiều truy vấn GROUP BY và hash join cùng bắt đầu. Sau đó:

- p95 của API tăng từ 80 ms lên 450 ms.
- Temp I/O tăng mạnh.
- Buffer cache hit giảm.
- Một số query báo cáo có hash spill.
- Một số query chờ memory grant hoặc bị timeout.
- RAM available xuống thấp.

### 14.2. Giả thuyết ban đầu

Có thể có nhiều nguyên nhân cùng lúc:

1. Số truy vấn báo cáo đồng thời vượt workspace budget.
2. Query plan ước lượng thiếu số dòng, cấp grant quá nhỏ.
3. Báo cáo đọc nhiều cột và tạo intermediate result rộng.
4. Parallel workers làm tăng tổng bộ nhớ.
5. Cache bị workspace chiếm chỗ, khiến OLTP phải đọc storage.
6. Backup hoặc maintenance cùng lúc làm tăng áp lực.
7. Connection pool không giới hạn query nặng.

Không kết luận ngay rằng máy thiếu RAM. Cần xác định phần bộ nhớ nào tăng và truy vấn nào tạo áp lực.

### 14.3. Cách điều tra

- Lấy snapshot RAM, process memory, cache và workspace trong giờ cao điểm.
- Xác định query có grant lớn, spill hoặc temp I/O cao.
- So sánh estimated rows với actual rows.
- Xem số query báo cáo chạy đồng thời và parallel workers.
- Kiểm tra buffer cache reads của workload OLTP.
- Kiểm tra wait events và memory grant queue.
- Đối chiếu thời điểm backup, checkpoint và batch job.

### 14.4. Thử thay đổi

Một kế hoạch thử có thể gồm:

1. Giới hạn báo cáo nặng tối đa hai truy vấn đồng thời.
2. Đưa báo cáo vào queue riêng.
3. Tối ưu query để giảm row width và intermediate cardinality.
4. Sửa thống kê hoặc query plan gây grant sai.
5. Giảm parallelism của báo cáo nếu tổng workspace vượt ngân sách.
6. Điều chỉnh memory workspace riêng cho một số truy vấn sau khi đo.
7. Chạy lại workload hỗn hợp cùng OLTP để đánh giá tác động.

### 14.5. Kết quả minh họa

| Chỉ số | Trước | Sau thử nghiệm |
|---|---:|---:|
| Báo cáo nặng đồng thời | 8 | 2 |
| Temp I/O mỗi phút | 14 GB | 4 GB |
| OLTP p95 | 450 ms | 105 ms |
| Query báo cáo p95 | 38 s | 44 s |
| RAM available tối thiểu | 0,8 GB | 5,5 GB |
| Query timeout mỗi giờ | 12 | 1 |

Các con số chỉ minh họa. Trong ví dụ, báo cáo chậm hơn do được xếp hàng và ít chạy đồng thời hơn, nhưng OLTP ổn định hơn và timeout giảm. Đây có thể là lựa chọn đúng nếu SLO của OLTP quan trọng hơn thời gian hoàn thành đồng thời của mọi báo cáo.

Không đánh giá thành công chỉ bằng query báo cáo hoặc chỉ bằng RAM available. Cần xem cả throughput, p95/p99, số job hoàn tất, queue time và chất lượng dịch vụ.

## 15. Những sai lầm thường gặp

**Cấp RAM cho cache đến sát mức tổng RAM.**  
Các truy vấn và hệ điều hành vẫn cần workspace và headroom. Cần lập ngân sách cho tất cả nhóm.

**Coi work_mem là giới hạn của một query hoặc toàn server.**  
Trong PostgreSQL, nhiều operator và session có thể sử dụng work_mem; concurrency làm tổng nhu cầu tăng.

**Nhân max_connections với một con số rồi xem đó là RAM chính xác.**  
Không phải mọi connection dùng cùng lượng memory; nhưng số session lớn tạo overhead và có thể tăng active concurrency.

**Tăng memory grant hoặc buffer lên mức cao để chữa spill.**  
Grant lớn có thể làm ít query được chạy đồng thời. Hãy kiểm tra estimate, row width và số dòng trước.

**Chỉ xem RAM available.**  
Cần liên hệ memory pressure với spill, cache hit, temp I/O, swap, wait và latency.

**Cho rằng cache hit cao nghĩa là không thiếu bộ nhớ.**  
Một workload cụ thể vẫn có thể spill hoặc chờ grant; hit ratio tổng thể che giấu vấn đề theo query.

**Tăng parallelism mà không tính workspace theo worker.**  
Parallel query có thể tăng bộ nhớ tổng và làm giảm concurrency của workload khác.

**Tăng connection pool khi request bị chậm.**  
Nhiều connection hơn có thể tạo thêm truy vấn đồng thời và làm tình trạng quá tải nặng hơn.

**Tăng RAM trước khi giảm dữ liệu trung gian.**  
Query plan không tốt có thể tiếp tục tiêu thụ bộ nhớ lớn sau khi nâng cấp.

**Không tính giới hạn container.**  
DBMS có thể bị OOM kill theo cgroup dù host còn RAM.

**Cộng trùng memory metrics.**  
Shared memory, RSS và committed/granted memory có thể có phạm vi chồng lấn. Phải hiểu định nghĩa trước khi cộng.

**Benchmark một query đơn lẻ.**  
Cấu hình chỉ tốt khi một query chạy riêng có thể thất bại khi nhiều workload chạy cùng lúc.

## 16. Quy trình xây dựng và xác nhận ngân sách bộ nhớ

Có thể áp dụng quy trình sau:

1. **Xác định giới hạn vật lý:** RAM host, container limit, NUMA, OS và dịch vụ cùng máy.
2. **Phân loại bộ nhớ:** shared cache, engine overhead, session, query workspace, temp và OS.
3. **Phân loại workload:** OLTP, báo cáo, phân tích, batch và maintenance.
4. **Đo peak theo truy vấn:** memory grant, used/peak memory, spill, temp I/O và parallel workers.
5. **Đo concurrency:** số query active theo từng nhóm ở p95/p99 và giờ cao điểm.
6. **Lập ngân sách:** tính nhu cầu theo concurrency class và dành headroom.
7. **Đặt quota:** connection pool, active query cap, resource group hoặc queue.
8. **Tối ưu query:** giảm cardinality, row width, sort/hash và sửa estimate.
9. **Benchmark hỗn hợp:** chạy OLTP cùng báo cáo, batch và tác vụ nền.
10. **Kiểm tra failure mode:** tăng tải từng bước, quan sát spill, wait, swap và OOM.
11. **Điều chỉnh:** thay đổi một nhóm cấu hình mỗi lần và lưu số liệu.
12. **Theo dõi liên tục:** cập nhật ngân sách khi dữ liệu, query shape hoặc concurrency thay đổi.

### 16.1. Bảng ngân sách mẫu

| Thành phần | Ngân sách | Cách xác minh |
|---|---:|---|
| OS và dịch vụ | Theo đo đạc và yêu cầu vận hành | Available RAM, process memory, swap |
| DBMS shared cache | Theo working set | Buffer/cache metrics, hit/read |
| Engine overhead | Theo process và cấu hình | RSS, memory clerks, SGA/metadata |
| Query workspace | Theo concurrency class | Grant, work area, sort/hash, spill |
| Session/connection | Theo active và idle sessions | Connection count, per-process/thread memory |
| Background jobs | Theo lịch và peak | Backup, vacuum, checkpoint, replication |
| Headroom | Theo biến động và failure mode | RAM available, cgroup limit, OOM history |

### 16.2. Tiêu chí chấp nhận

Một cấu hình có thể được chấp nhận khi:

- Không có OOM hoặc paging kéo dài dưới tải mục tiêu.
- Memory grant waits hoặc workspace queue nằm trong SLO.
- Spill không tăng bất thường trên query quan trọng.
- Buffer cache không bị churn nghiêm trọng.
- OLTP p95/p99 đạt mục tiêu trong khi báo cáo chạy.
- Throughput tổng thể không giảm vượt ngưỡng.
- Queue time và timeout nằm trong giới hạn.
- Backup, checkpoint và maintenance vẫn có đủ tài nguyên.
- Có headroom cho peak và thao tác vận hành.

Không yêu cầu mọi truy vấn phải có zero spill. Mục tiêu là kiểm soát chi phí spill và giữ SLO toàn hệ thống.

## 17. Kết luận

Ngân sách bộ nhớ phải được lập cho toàn bộ hệ thống và workload đồng thời. RAM được chia giữa cache dùng chung, engine overhead, session, workspace của sort/hash, tiến trình nền và hệ điều hành. Một truy vấn đơn lẻ có thể chạy tốt nhưng nhiều truy vấn nặng cùng lúc có thể làm tổng workspace vượt ngân sách, gây spill, memory grant wait, cache eviction, paging hoặc OOM.

Cách tiếp cận hiệu quả là đo peak memory theo query và concurrency class, hiểu semantics cấu hình của đúng DBMS, rồi đặt giới hạn số truy vấn hoạt động và mức cấp phát phù hợp. PostgreSQL work_mem, SQL Server memory grant, MySQL buffer pool và buffer theo session, Oracle SGA/PGA có cơ chế khác nhau; không áp dụng một công thức cấu hình chung cho tất cả.

Khi tối ưu, hãy giảm cardinality và row width trước, sửa thống kê và execution plan, kiểm soát parallelism và admission control, sau đó mới điều chỉnh cache hoặc workspace. Kiểm chứng bằng benchmark hỗn hợp có OLTP, báo cáo và tác vụ nền; theo dõi latency, throughput, memory pressure, temp I/O, cache và headroom.

Một cấu hình bộ nhớ tốt không tối đa hóa RAM cho một truy vấn. Nó duy trì được hiệu năng và độ ổn định của toàn hệ thống khi nhiều truy vấn và tác vụ cùng hoạt động.

## Câu hỏi tự kiểm tra

1. Vì sao ngân sách bộ nhớ của DBMS phải tính cả workspace theo truy vấn và hệ điều hành?
2. Shared cache và query workspace khác nhau về mục đích và vòng đời như thế nào?
3. Vì sao work_mem trong PostgreSQL không phải giới hạn RAM cho một query hoặc toàn server?
4. Một query có ba sort/hash operator và 20 session chạy đồng thời. Vì sao không thể chỉ lấy work_mem nhân 20 rồi coi đó là peak chính xác?
5. Requested memory, granted memory và used memory khác nhau thế nào?
6. Underestimate cardinality có thể dẫn đến spill theo cách nào?
7. Vì sao tăng parallel workers có thể làm giảm concurrency toàn hệ thống?
8. Memory grant wait trong SQL Server khác spill như thế nào?
9. Vì sao max_connections hoặc connection pool lớn có thể làm tăng memory pressure?
10. InnoDB buffer pool cần chia sẻ RAM với những nhóm nào khác?
11. SGA và PGA của Oracle phục vụ những mục đích khác nhau nào?
12. Cache eviction, swap và OOM khác nhau như thế nào?
13. Khi DBMS chạy trong container, cần tính memory limit ra sao?
14. Hãy lập ngân sách cho một máy chủ có 64 GB RAM với OLTP, báo cáo và phân tích nặng, nêu concurrency cap và headroom.
15. Thiết kế benchmark hỗn hợp để xác nhận cấu hình bộ nhớ không làm OLTP suy giảm khi báo cáo chạy đồng thời.

Khi đánh giá một cấu hình bộ nhớ, hãy hỏi: nhóm nào đang sử dụng RAM, mỗi truy vấn có thể giữ bao nhiêu workspace, có bao nhiêu truy vấn chạy đồng thời và hệ thống còn bao nhiêu headroom khi đạt peak. Những câu hỏi đó giúp bảo vệ hiệu năng của toàn workload thay vì chỉ tối ưu một câu SQL.

