# Chuẩn bị năng lực hạ tầng PostgreSQL: CPU, RAM, IOPS, dung lượng và tốc độ tăng dữ liệu

Triển khai PostgreSQL ổn định bắt đầu từ việc hiểu hệ thống sẽ xử lý loại tải nào, cần đáp ứng thời gian phản hồi ra sao và dữ liệu sẽ tăng như thế nào. CPU, RAM, tốc độ lưu trữ và dung lượng đĩa liên quan chặt chẽ với nhau. Một máy chủ có nhiều CPU vẫn có thể chậm nếu truy vấn phải chờ đọc đĩa; một ổ đĩa có IOPS cao vẫn không giải quyết được tình trạng thiếu RAM khiến hệ điều hành liên tục phải nạp lại dữ liệu; một cụm đang chạy tốt hôm nay vẫn có thể hết dung lượng khi WAL, bảng, chỉ mục hoặc dữ liệu tạm tăng nhanh.

Vì vậy, việc chuẩn bị hạ tầng cần dựa trên số liệu tải thực tế, có dự phòng cho giờ cao điểm, bảo trì và tăng trưởng. Không có một cấu hình CPU, RAM hay IOPS cố định phù hợp với mọi hệ thống PostgreSQL.

## 1. Xác định tải công việc trước khi chọn máy chủ

Trước khi chọn cấu hình, hãy mô tả cách ứng dụng sử dụng cơ sở dữ liệu. Cùng một lượng dữ liệu nhưng hai hệ thống có thể cần tài nguyên rất khác nhau.

| Đặc điểm tải | Hành vi thường gặp | Tài nguyên cần chú ý |
|---|---|---|
| OLTP, nhiều giao dịch nhỏ | Nhiều truy vấn ngắn, cập nhật từng bản ghi, nhiều kết nối đồng thời | CPU đơn nhân, độ trễ đĩa, RAM cho working set và chỉ mục |
| Đọc nhiều | Tra cứu, tìm kiếm, báo cáo đọc lặp lại | RAM, cache, IOPS đọc, CPU |
| Ghi nhiều | INSERT/UPDATE liên tục, phát sinh WAL lớn | CPU, độ trễ ghi và fsync, thông lượng ghi, dung lượng WAL |
| Phân tích dữ liệu | Quét bảng lớn, JOIN, GROUP BY, sắp xếp | RAM cho hash/sort, CPU đa nhân, thông lượng đọc, dung lượng tạm |
| Hỗn hợp OLTP và phân tích | Giao dịch trực tuyến cạnh tranh tài nguyên với báo cáo | Cô lập tải, giới hạn truy vấn, replica hoặc tài nguyên riêng |

Hãy thu thập ít nhất các thông tin sau:

- Số giao dịch hoặc truy vấn mỗi giây ở mức trung bình và giờ cao điểm.
- Số kết nối đồng thời, số phiên thực sự chạy truy vấn và số kết nối nhàn rỗi.
- Tỷ lệ đọc/ghi, kích thước giao dịch và các đợt ghi theo lô.
- Độ trễ truy vấn ở các phân vị P50, P95 và P99, không chỉ thời gian trung bình.
- Kích thước dữ liệu, chỉ mục, bảng lớn nhất và phần dữ liệu thường xuyên được truy cập.
- Lịch chạy báo cáo, ETL, backup, VACUUM, tạo chỉ mục và các tác vụ bảo trì.
- Mục tiêu RPO/RTO, thời gian lưu dữ liệu, chính sách backup và số lượng replica.

Nếu chưa có hệ thống chạy thật, hãy xây dựng kịch bản tải đại diện. Kịch bản cần có dữ liệu với phân bố và kích thước gần thực tế; thử nghiệm trên vài nghìn bản ghi nhỏ thường không phản ánh đúng hành vi của hệ thống có hàng trăm triệu bản ghi.

## 2. Chuẩn bị CPU

CPU xử lý lập kế hoạch và thực thi truy vấn, biểu thức, JOIN, sắp xếp, mã hóa, nén, kiểm tra ràng buộc, VACUUM và nhiều công việc nền khác. Khi CPU không đủ, truy vấn có thể phải chờ dù ổ đĩa vẫn còn khả năng phục vụ.

### 2.1. Số lõi và tốc độ từng lõi

PostgreSQL thường chạy nhiều tiến trình backend; mỗi kết nối được phục vụ bởi một tiến trình riêng. Một truy vấn thông thường không tự động chia đều công việc lên tất cả lõi CPU. Một số truy vấn có thể dùng parallel query, nhưng khả năng song song phụ thuộc loại truy vấn, kế hoạch thực thi, cấu hình và chi phí ước lượng.

Do đó, cần xem xét cả:

- **Hiệu năng mỗi lõi:** quan trọng với giao dịch ngắn, truy vấn tuần tự hoặc các bước thực thi không thể song song hóa.
- **Tổng số lõi:** hữu ích khi có nhiều truy vấn đồng thời, nhiều tiến trình nền hoặc truy vấn phân tích có thể chạy song song.
- **Hiệu năng CPU thực tế:** vCPU trên máy ảo có thể chia sẻ tài nguyên với máy khác; CPU burst có thể bị giới hạn sau khi dùng hết credit. Cần kiểm tra giới hạn của nhà cung cấp.
- **Tài nguyên dành cho hệ điều hành:** PostgreSQL không phải tiến trình duy nhất sử dụng CPU. Hệ điều hành, agent giám sát, backup, nén và mã hóa cũng tiêu thụ tài nguyên.

Không nên chọn CPU chỉ dựa trên tổng số kết nối. Hãy phân biệt kết nối đang mở với truy vấn thực sự chạy. Connection pool giúp giới hạn số backend hoạt động và giảm chi phí chuyển đổi ngữ cảnh khi ứng dụng tạo quá nhiều kết nối.

### 2.2. Nhận biết CPU là nút thắt

Một số dấu hiệu cần theo dõi:

- CPU sử dụng cao kéo dài trong khi độ trễ truy vấn tăng.
- Hàng đợi chạy của hệ điều hành thường xuyên lớn hơn khả năng xử lý của CPU.
- Nhiều backend đang thực thi nhưng ít thời gian chờ I/O.
- Các truy vấn tốn CPU như JOIN lớn, biểu thức phức tạp, sort hoặc aggregate chiếm phần lớn thời gian.
- Tăng số lõi làm throughput cải thiện trong thử nghiệm có kiểm soát.

CPU cao trong một khoảng ngắn chưa chắc là vấn đề. Cần đối chiếu với latency, throughput, wait event và thời gian cao điểm. Nếu CPU thấp nhưng truy vấn chậm, nguyên nhân có thể là I/O, khóa, thiếu tài nguyên bộ nhớ, mạng hoặc kế hoạch truy vấn chưa tốt.

### 2.3. Cách ước lượng và kiểm chứng

Không có công thức đáng tin cậy kiểu “mỗi 1.000 giao dịch cần một lõi”. Chi phí CPU phụ thuộc câu SQL, dữ liệu, chỉ mục, cache và mức đồng thời. Cách làm thực tế là:

1. Chạy workload đại diện trên cấu hình thử nghiệm.
2. Đo throughput, latency P95/P99, CPU và run queue ở giờ cao điểm.
3. Tăng tải theo từng bước để tìm điểm mà latency bắt đầu tăng nhanh hoặc throughput không còn tăng tương ứng.
4. Lặp lại với cấu hình CPU khác để xác định lợi ích của thêm lõi hoặc CPU có xung nhịp cao hơn.
5. Chừa năng lực cho backup, VACUUM, tạo chỉ mục, failover và tăng trưởng tải.

Với truy vấn phân tích, kiểm tra parallel query và giới hạn số parallel worker để tránh nhiều truy vấn đồng thời tạo quá nhiều worker, cạnh tranh CPU và RAM.

## 3. Chuẩn bị RAM

RAM giúp PostgreSQL giữ các trang dữ liệu và chỉ mục thường dùng trong bộ nhớ, giảm số lần phải đọc từ thiết bị lưu trữ. RAM còn được sử dụng cho tiến trình backend, sắp xếp, hash join, bảo trì và cache của hệ điều hành.

Cần phân biệt các nhóm bộ nhớ chính:

| Thành phần | Mục đích | Cách tính khi lập kế hoạch |
|---|---|---|
| shared_buffers | Bộ nhớ chia sẻ để cache các trang dữ liệu của PostgreSQL | Cấu hình toàn instance |
| Cache của hệ điều hành | Cache file và trang dữ liệu ngoài shared_buffers | Cần để lại RAM cho hệ điều hành |
| work_mem | Bộ nhớ cho mỗi thao tác sort hoặc hash của một truy vấn | Có thể được cấp nhiều lần trong một truy vấn và cho nhiều truy vấn đồng thời |
| maintenance_work_mem | Bộ nhớ cho một số thao tác bảo trì như tạo chỉ mục và VACUUM | Ước lượng theo số tác vụ bảo trì chạy đồng thời |
| autovacuum_work_mem | Bộ nhớ cho mỗi worker autovacuum khi được cấu hình riêng | Tính theo số worker autovacuum hoạt động |
| Bộ nhớ backend | Bộ nhớ riêng của từng tiến trình kết nối | Tăng theo số backend và đặc điểm truy vấn |
| wal_buffers | Bộ đệm WAL trong shared memory | Cấu hình theo nhu cầu ghi và phiên bản |

### 3.1. shared_buffers và cache hệ điều hành

shared_buffers là vùng bộ nhớ PostgreSQL dùng chung cho các tiến trình. Trên máy chủ chuyên dụng, tỷ lệ khoảng 25% RAM thường được dùng làm điểm bắt đầu thử nghiệm, nhưng đây không phải định mức bắt buộc. Kích thước phù hợp phụ thuộc tổng RAM, working set, loại tải và khả năng cache của hệ điều hành.

Không nên cấp toàn bộ RAM cho shared_buffers. Hệ điều hành vẫn cần bộ nhớ cho page cache, tiến trình nền và các dịch vụ vận hành. Tăng shared_buffers quá mức có thể làm giảm phần RAM dành cho các mục đích khác và không bảo đảm truy vấn nhanh hơn.

effective_cache_size là tham số ước lượng cho bộ lập kế hoạch về lượng cache có thể sẵn có từ PostgreSQL và hệ điều hành. Tham số này không cấp phát RAM. Đặt giá trị quá thấp hoặc quá cao có thể làm bộ lập kế hoạch đánh giá sai chi phí đọc dữ liệu.

### 3.2. work_mem là bộ nhớ theo thao tác

Một nhầm lẫn phổ biến là xem work_mem như một khoản bộ nhớ cố định cho mỗi kết nối. Trên thực tế, nó được dùng cho từng thao tác sort hoặc hash trong kế hoạch truy vấn. Một truy vấn có thể có nhiều thao tác như vậy; nhiều truy vấn đồng thời có thể cùng sử dụng bộ nhớ.

Ví dụ minh họa: nếu work_mem là 32 MB, 30 truy vấn cùng chạy và mỗi truy vấn có trung bình 3 thao tác sort/hash đang cần bộ nhớ, mức sử dụng lý thuyết có thể lên đến:

32 MB × 30 × 3 = 2.880 MB

Đây chỉ là phép ước lượng rủi ro, không phải mức cấp phát chắc chắn: các thao tác không phải lúc nào cũng đạt giới hạn tối đa hoặc hoạt động đồng thời. Tuy vậy, ví dụ cho thấy việc tăng work_mem toàn cục có thể gây thiếu RAM khi tải đồng thời tăng.

Nên đo số truy vấn có sort/hash tràn ra đĩa, kiểm tra kế hoạch thực thi và cân nhắc đặt work_mem theo phiên hoặc theo vai trò cho nhóm truy vấn đặc biệt. Không tăng work_mem chỉ vì thấy một truy vấn đơn lẻ chạy nhanh hơn khi được cấp nhiều RAM.

### 3.3. Số kết nối và connection pooling

Mỗi backend PostgreSQL có chi phí bộ nhớ riêng. Đặt max_connections quá cao có thể làm tăng RAM nền và khiến nhiều truy vấn cùng cạnh tranh CPU, bộ nhớ, I/O. Không nên dùng max_connections như cách xử lý mọi vấn đề kết nối.

Với ứng dụng có nhiều instance hoặc tạo kết nối ngắn, hãy cân nhắc connection pool ở ứng dụng hoặc PgBouncer. Pool giới hạn số kết nối thực sự đến PostgreSQL và tái sử dụng backend. Chọn chế độ pooling phù hợp với cách ứng dụng sử dụng session, transaction, prepared statement và các tính năng phụ thuộc trạng thái phiên.

### 3.4. Dấu hiệu thiếu RAM

- Hệ điều hành bắt đầu swap thường xuyên hoặc có áp lực bộ nhớ.
- Tiến trình bị OOM killer kết thúc.
- Nhiều thao tác sort/hash ghi dữ liệu tạm ra đĩa.
- Cache hit giảm cùng lúc với số lần đọc đĩa và latency tăng.
- Hiệu năng giảm mạnh khi working set vượt quá bộ nhớ cache.

Cache hit ratio cao không tự động chứng minh RAM đủ. PostgreSQL có thể đọc từ page cache của hệ điều hành sau khi không tìm thấy trang trong shared_buffers. Cần kết hợp số liệu PostgreSQL, hệ điều hành và độ trễ truy vấn.

## 4. Đánh giá lưu trữ: dung lượng, IOPS, thông lượng và độ trễ

Bốn khái niệm này liên quan nhưng không thể thay thế cho nhau:

- **Dung lượng (capacity):** tổng lượng dữ liệu có thể lưu.
- **IOPS:** số thao tác đọc/ghi mỗi giây mà thiết bị có thể phục vụ trong điều kiện xác định.
- **Thông lượng (throughput):** lượng dữ liệu đọc/ghi trong một giây, thường tính bằng MB/s hoặc GB/s.
- **Độ trễ (latency):** thời gian hoàn thành một thao tác I/O; cần theo dõi cả phân vị cao như P95/P99.

Một ổ đĩa có thông lượng tuần tự cao chưa chắc có IOPS ngẫu nhiên cao. Một thiết bị đạt IOPS lớn trong benchmark cũng chưa chắc đáp ứng tốt nếu độ trễ tăng mạnh khi hàng đợi dài hoặc khi chạy đồng thời với backup.

### 4.1. PostgreSQL tạo ra những loại I/O nào?

Các hoạt động thường gặp gồm:

- Đọc trang bảng và chỉ mục, thường theo truy cập ngẫu nhiên trong OLTP.
- Ghi các trang dữ liệu đã thay đổi xuống storage.
- Ghi WAL để bảo đảm khả năng phục hồi sau sự cố.
- Đồng bộ WAL với thiết bị lưu trữ bằng thao tác fsync hoặc cơ chế tương đương.
- Đọc/ghi file tạm khi sort hoặc hash không vừa bộ nhớ.
- Đọc dữ liệu tuần tự khi quét bảng, backup hoặc chạy báo cáo.
- I/O do checkpoint, VACUUM, tạo chỉ mục và các tác vụ bảo trì.

WAL thường có tính tuần tự hơn so với truy cập trang dữ liệu. Tuy nhiên, độ trễ ghi và đồng bộ WAL rất quan trọng với giao dịch cần commit bền vững. Một thiết bị có throughput lớn nhưng fsync chậm vẫn có thể làm tăng thời gian commit.

### 4.2. Ước lượng IOPS từ workload

Không nên suy ra IOPS bằng cách lấy số truy vấn mỗi giây nhân với một con số cố định. Một truy vấn có thể được phục vụ hoàn toàn từ cache, đọc một trang, hoặc quét hàng triệu trang. Kích thước trang, tỷ lệ cache hit, pattern truy cập, checkpoint và mức đồng thời đều ảnh hưởng đến I/O.

Hãy đo trên workload đại diện:

1. Ghi nhận lượng đọc/ghi mỗi giây và kích thước I/O.
2. Theo dõi độ trễ đọc, ghi và fsync.
3. Quan sát độ sâu hàng đợi I/O; hàng đợi tăng kéo dài thường cho thấy storage đang bị bão hòa hoặc bị giới hạn.
4. Đo riêng giờ cao điểm, backup, checkpoint và bảo trì.
5. Thử nghiệm với kích thước dữ liệu gần production và mức đồng thời dự kiến.

Với storage cloud, cần kiểm tra IOPS và throughput tối đa theo dung lượng volume, giới hạn burst, credit, giới hạn theo instance và giới hạn tổng của máy ảo. Mức hiệu năng được quảng cáo có thể chỉ đạt trong một điều kiện cấu hình cụ thể.

### 4.3. Chọn loại thiết bị và bố trí dữ liệu

SSD hoặc NVMe thường phù hợp với workload PostgreSQL có nhiều truy cập ngẫu nhiên và yêu cầu độ trễ thấp. Tuy nhiên, cần đánh giá độ bền, độ ổn định, khả năng bảo vệ dữ liệu khi mất điện và chất lượng dịch vụ của nhà cung cấp.

Tách WAL và data sang thiết bị riêng có thể hữu ích khi hai luồng I/O cạnh tranh đáng kể và hạ tầng cho phép kiểm soát độc lập. Việc tách thư mục không tự động tăng hiệu năng nếu chúng vẫn nằm trên cùng thiết bị vật lý hoặc cùng giới hạn IOPS. Chỉ nên triển khai sau khi đo được điểm nghẽn và kiểm chứng lợi ích.

Backup, archive WAL và file tạm cũng tạo tải I/O. Hãy tính chúng vào thiết kế, giới hạn băng thông hoặc bố trí lịch phù hợp để tránh backup làm chậm giao dịch trực tuyến.

## 5. Tính dung lượng lưu trữ cần thiết

Dung lượng database không chỉ là tổng kích thước dữ liệu nghiệp vụ. Khi lập kế hoạch, cần tính các thành phần sau:

| Thành phần | Nội dung cần tính |
|---|---|
| Bảng dữ liệu | Dữ liệu chính, các cột lớn và dữ liệu TOAST |
| Chỉ mục | Primary key, unique index, index phục vụ truy vấn |
| WAL | Mức phát sinh trong giờ cao điểm, thời gian lưu và nguy cơ tích tụ |
| Dữ liệu tạm | Sort/hash tràn đĩa, bảng tạm và công việc ETL |
| Log | Log PostgreSQL, log hệ điều hành và log giám sát nếu đặt cùng volume |
| Không gian bảo trì | Dư địa cho VACUUM, tạo/rebuild index, migration và thao tác thay thế bảng |
| Backup và archive | Bản backup cục bộ, snapshot, WAL archive; xác định rõ nơi lưu |
| Dự phòng vận hành | Khoảng trống để xử lý tăng trưởng bất thường và sự cố |

Backup có thể được lưu trên hệ thống riêng. Nếu lưu ngoài volume dữ liệu, không cộng toàn bộ backup vào dung lượng volume database; nhưng vẫn phải lập kế hoạch dung lượng và chi phí cho nơi lưu backup, thời gian retention và tốc độ khôi phục.

### 5.1. Công thức lập kế hoạch

Có thể dùng mô hình ước lượng ban đầu:

Dung lượng cần cấp = Dữ liệu dự kiến + WAL dự phòng + Dữ liệu tạm và log + Khoảng trống vận hành

Trong đó:

Dữ liệu dự kiến = Dữ liệu hiện tại + Tốc độ tăng ròng mỗi ngày × Số ngày dự báo

Nếu tốc độ tăng thay đổi theo mùa hoặc theo số người dùng, hãy dùng kịch bản thấp, cơ sở và cao. Với tăng trưởng theo tỷ lệ phần trăm, có thể dùng mô hình tăng trưởng lũy kế thay vì giả định số GB mỗi ngày không đổi.

Khoảng trống vận hành phải đủ để xử lý peak WAL, tạo lại chỉ mục, migration, VACUUM và biến động bất thường. Không nên đợi filesystem gần đầy mới mở rộng: PostgreSQL có thể không ghi được WAL hoặc file dữ liệu khi volume hết chỗ, khiến dịch vụ gián đoạn.

### 5.2. Ví dụ tính dung lượng

Giả sử một hệ thống có số liệu sau:

- Bảng, TOAST và chỉ mục hiện tại: 1,0 TB.
- Tốc độ tăng ròng đo được: 8 GB/ngày.
- Thời gian dự báo: 180 ngày.
- WAL dự phòng cho giai đoạn tải cao: 80 GB.
- Dữ liệu tạm và log dự kiến trên cùng volume: 40 GB.
- Khoảng trống vận hành: 25% phần dữ liệu dự kiến.

Phần dữ liệu sau 180 ngày:

1,0 TB + (8 GB × 180) = khoảng 2,44 TB

Khoảng trống vận hành:

2,44 TB × 25% = khoảng 0,61 TB

Tổng dung lượng ước lượng:

2,44 TB + 0,08 TB + 0,04 TB + 0,61 TB = khoảng 3,17 TB

Có thể chọn volume có dung lượng sử dụng được lớn hơn mức này, sau đó xác minh lại bằng cách tính theo đơn vị GB/TB mà nhà cung cấp sử dụng. Ví dụ này giả định tốc độ tăng 8 GB/ngày đã bao gồm tăng trưởng của bảng và chỉ mục, còn backup được lưu ở nơi khác. Trong triển khai thật, cần cộng thêm thành phần bị bỏ qua nếu chúng nằm trên cùng volume.

### 5.3. Theo dõi tốc độ tăng dữ liệu

Đừng chỉ nhìn tổng dung lượng một lần. Hãy lưu số đo định kỳ theo ngày hoặc tuần để tính tốc độ tăng ròng và phát hiện bảng tăng bất thường.

Kích thước từng database:

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Các bảng lớn, tính cả chỉ mục và dữ liệu TOAST:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_indexes_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 20;
~~~

Lưu kết quả theo thời gian để tính:

Tốc độ tăng trung bình mỗi ngày = (Dung lượng cuối kỳ − Dung lượng đầu kỳ) / Số ngày

Nên theo dõi riêng bảng, chỉ mục, WAL và filesystem. Dung lượng database có thể tăng do dữ liệu mới, index mới, bloat hoặc thay đổi cách lưu trữ; các nguyên nhân này cần cách xử lý khác nhau.

## 6. Quản lý WAL và các tình huống làm đầy đĩa

WAL được dùng để phục hồi và hỗ trợ replication. Dung lượng WAL có thể tăng nhanh khi workload ghi lớn, checkpoint hoặc archive gặp vấn đề, replica chậm hoặc replication slot giữ lại WAL chưa được tiêu thụ.

Cần theo dõi:

- Tốc độ phát sinh WAL theo thời gian và trong giờ cao điểm.
- Dung lượng WAL đang chiếm trên filesystem.
- Trạng thái WAL archiving và lỗi archive.
- Replication lag của standby.
- Replication slot không hoạt động hoặc giữ lại lượng WAL lớn.
- Checkpoint quá thường xuyên hoặc có thời gian ghi kéo dài.

Một replication slot bị bỏ quên có thể giữ WAL lâu hơn dự kiến và làm đầy ổ đĩa. Không xóa slot hoặc file WAL thủ công để giải phóng dung lượng; hãy xác định consumer, kiểm tra trạng thái replication và xử lý theo quy trình vận hành PostgreSQL. Xóa file trong thư mục dữ liệu có thể làm hỏng khả năng phục hồi của cụm.

## 7. Đo lường bằng số liệu PostgreSQL và hệ điều hành

Capacity planning chỉ đáng tin cậy khi có dữ liệu đo liên tục. Nên kết hợp thống kê bên trong PostgreSQL với metrics của máy chủ và storage.

### 7.1. Thống kê I/O trong PostgreSQL

Trên PostgreSQL 16 trở lên, view pg_stat_io cung cấp thống kê I/O theo loại backend, đối tượng và ngữ cảnh:

~~~sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Các cột thời gian có ý nghĩa khi track_io_timing được bật. Hãy đánh giá chi phí đo đạc trong môi trường của bạn và so sánh số liệu theo cùng một khoảng thời gian. View này là thống kê tích lũy, nên cần lấy mẫu định kỳ và tính chênh lệch giữa các lần lấy mẫu.

Trên các phiên bản cũ hơn, có thể bắt đầu từ pg_stat_database:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks
FROM pg_stat_database
ORDER BY datname;
~~~

Tỷ lệ hit trong shared buffers có thể tính gần đúng bằng:

100 × blks_hit / (blks_hit + blks_read)

Đây chỉ là chỉ số tham khảo. blks_read là số block PostgreSQL phải yêu cầu đọc vào shared buffers, không đồng nghĩa mọi block đều phải đọc từ thiết bị vật lý; hệ điều hành có thể phục vụ từ page cache. Không dùng tỷ lệ này riêng lẻ để kết luận storage hoặc RAM đang đủ.

### 7.2. Theo dõi WAL

Có thể xem thống kê WAL bằng pg_stat_wal trên các phiên bản hỗ trợ view này:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal;
~~~

Lấy mẫu định kỳ để tính lượng WAL phát sinh trong một phút hoặc một giờ. Khi so sánh, lưu ý thống kê có thể được reset và số liệu thời gian phụ thuộc cấu hình đo I/O.

### 7.3. Theo dõi kết nối và thời gian chờ

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Truy vấn này giúp phân biệt backend đang chạy, đang nhàn rỗi và đang chờ một sự kiện. Cần đọc wait event cùng SQL, thời gian chờ và bối cảnh tải; một loại wait xuất hiện không tự động có nghĩa là lỗi.

Nếu đã cài pg_stat_statements, hãy dùng nó để tìm các câu SQL tiêu thụ tổng thời gian thực thi lớn, có số lần gọi cao hoặc có độ biến động lớn. Tối ưu truy vấn và chỉ mục thường có thể giảm nhu cầu CPU, RAM và I/O hiệu quả hơn việc chỉ tăng cấu hình máy chủ.

### 7.4. Metrics ở hệ điều hành và nhà cung cấp

Tối thiểu nên giám sát:

- CPU utilization, CPU steal trên máy ảo, run queue và load.
- RAM khả dụng, swap, page fault và dấu hiệu OOM.
- IOPS đọc/ghi, throughput, latency, queue depth và giới hạn/burst của volume.
- Dung lượng filesystem, inode và tốc độ tăng theo thời gian.
- Network throughput, packet loss và latency giữa ứng dụng, primary và replica.
- Backup duration, WAL archive lag, replication lag và thời gian hoàn tất VACUUM.

Công cụ như iostat, vmstat, sar hoặc hệ thống metrics của nhà cung cấp giúp đối chiếu PostgreSQL với hoạt động của máy chủ. Khi database báo thời gian đọc tăng, metrics storage giúp xác định đó là độ trễ thiết bị, giới hạn IOPS hay tải cạnh tranh từ tiến trình khác.

## 8. Kiểm thử tải và xác định cấu hình phù hợp

Một cấu hình chỉ nên được chốt sau khi thử nghiệm trên workload đại diện. Có thể dùng pgbench cho thử nghiệm cơ bản hoặc công cụ phát lại workload của ứng dụng để giữ gần đúng phân bố truy vấn thực tế.

Quy trình thử nghiệm:

1. Chuẩn bị dữ liệu có kích thước và phân bố gần production.
2. Dùng cùng phiên bản PostgreSQL, tham số quan trọng và loại storage dự kiến.
3. Chạy tải tăng dần, ghi lại throughput và latency P95/P99.
4. Tạo tình huống đọc/ghi đồng thời, báo cáo, backup và bảo trì.
5. Theo dõi CPU, RAM, IOPS, throughput, latency storage, WAL và dung lượng tạm.
6. Thử khi working set lớn hơn cache để quan sát hành vi I/O.
7. Kiểm tra khả năng phục hồi và thời gian khôi phục từ backup nếu đây là yêu cầu triển khai.
8. Lặp lại sau khi thay đổi một nhóm tài nguyên để biết thay đổi đó thực sự cải thiện điều gì.

Không nên thay đổi đồng thời CPU, RAM, storage và nhiều tham số PostgreSQL rồi kết luận cấu hình nào tạo ra cải thiện. Thay đổi từng yếu tố hoặc từng nhóm có kiểm soát sẽ giúp xác định nguyên nhân rõ hơn.

## 9. Chừa năng lực cho vận hành và tăng trưởng

Tài nguyên cần phục vụ cả tải nghiệp vụ lẫn các công việc vận hành. Hãy đưa các tình huống sau vào kế hoạch:

- Backup toàn phần và backup gia tăng chạy cùng giờ cao điểm.
- VACUUM, autovacuum, ANALYZE và tạo lại chỉ mục.
- Migration tạo bảng hoặc chỉ mục lớn.
- Báo cáo cuối ngày, ETL và batch import.
- Tăng tải theo mùa, chiến dịch hoặc số lượng người dùng.
- Primary chuyển vai trò hoặc replica được nâng cấp thành primary.
- Khôi phục dữ liệu, replay WAL và đồng bộ lại replica.

Với hệ thống có standby, mỗi replica cũng cần CPU, RAM và storage đủ cho vai trò dự kiến. Read replica có thể chuyển một phần truy vấn đọc, nhưng không tự động giải quyết tải ghi trên primary. Replication còn tạo thêm chi phí mạng, WAL và lưu trữ.

Có thể chọn mở rộng theo chiều dọc bằng cách tăng CPU, RAM hoặc storage; hoặc mở rộng kiến trúc bằng connection pooling, read replica, partitioning, lưu trữ dữ liệu lịch sử và tách workload phân tích. Mỗi phương án có chi phí và giới hạn riêng. Chỉ dùng partitioning khi có khóa phân vùng, truy vấn và chiến lược vòng đời dữ liệu phù hợp; partitioning không tự động làm mọi truy vấn nhanh hơn.

## 10. Thiết lập cảnh báo theo thời gian xử lý được

Cảnh báo dung lượng cần dựa trên tốc độ tăng và thời gian đội vận hành cần để mở rộng volume hoặc dọn dữ liệu hợp lệ. Ví dụ, ngưỡng cảnh báo 70% và ngưỡng nghiêm trọng 85% có thể là điểm khởi đầu để thảo luận, nhưng phải điều chỉnh theo tốc độ tăng, quy trình cấp thêm dung lượng và giới hạn của nền tảng.

Nên cảnh báo trước khi hết chỗ đối với:

- Filesystem data và filesystem chứa WAL.
- WAL tăng bất thường hoặc archive bị lỗi.
- Replication slot giữ WAL lâu.
- Replication lag vượt ngưỡng nghiệp vụ.
- IOPS, throughput hoặc latency storage tiến sát giới hạn.
- CPU và RAM bị sử dụng cao kéo dài.
- Swap tăng, OOM hoặc dung lượng tạm tăng bất thường.
- Tốc độ tăng dữ liệu vượt dự báo.

Cảnh báo tốt phải cho biết chỉ số nào vượt ngưỡng, bắt đầu từ khi nào, tốc độ thay đổi và thời gian ước tính đến khi chạm giới hạn. Với dung lượng, có thể tính số ngày còn lại dựa trên dung lượng trống chia cho tốc độ tăng ròng trung bình; nên dùng thêm tốc độ tăng ở giờ cao điểm hoặc kịch bản cao để tránh đánh giá quá lạc quan.

## 11. Những sai lầm thường gặp

- **Chọn máy theo dung lượng database hiện tại:** bỏ qua chỉ mục, WAL, file tạm, bảo trì và tăng trưởng.
- **Chỉ nhìn CPU trung bình:** bỏ lỡ đỉnh tải ngắn, CPU steal hoặc một lõi bị bão hòa.
- **Tăng work_mem cho toàn hệ thống:** nhiều truy vấn đồng thời có thể làm tổng bộ nhớ vượt RAM.
- **Tăng max_connections để xử lý mọi lỗi kết nối:** có thể làm tăng backend và cạnh tranh tài nguyên; cần xem xét pooling.
- **Dùng IOPS quảng cáo làm số liệu duy nhất:** không kiểm tra latency, throughput, queue depth, burst và giới hạn theo instance.
- **Coi blks_read là số lần đọc đĩa vật lý:** bỏ qua cache của hệ điều hành.
- **Không tính WAL và replication slot:** có thể khiến volume đầy dù dữ liệu nghiệp vụ tăng chậm.
- **Chỉ benchmark với dữ liệu nhỏ:** working set và pattern truy cập không giống production.
- **Không dự phòng cho bảo trì và khôi phục:** hệ thống hoạt động ở trạng thái bình thường nhưng thất bại khi backup, migration hoặc failover.

## 12. Checklist trước khi triển khai

- [ ] Đã mô tả loại workload, throughput, concurrency và giờ cao điểm.
- [ ] Đã xác định mục tiêu latency P95/P99, RPO, RTO và retention.
- [ ] Đã benchmark CPU với dữ liệu và truy vấn đại diện.
- [ ] Đã tính RAM cho shared_buffers, hệ điều hành, backend, work_mem và bảo trì.
- [ ] Đã quyết định giới hạn kết nối và cơ chế connection pooling.
- [ ] Đã đo IOPS, throughput, latency và queue depth trên loại storage dự kiến.
- [ ] Đã tính bảng, TOAST, chỉ mục, WAL, file tạm, log và khoảng trống vận hành.
- [ ] Đã dự báo tăng trưởng theo ít nhất một khoảng thời gian vận hành phù hợp.
- [ ] Đã xác định nơi lưu backup và WAL archive, cùng dung lượng retention.
- [ ] Đã có metrics, cảnh báo và quy trình xử lý khi storage hoặc WAL tăng bất thường.
- [ ] Đã thử backup/restore, bảo trì và tình huống failover theo yêu cầu dịch vụ.
- [ ] Đã ghi lại cấu hình, giả định, số liệu benchmark và thời điểm cần đánh giá lại.

## Kết luận

Chuẩn bị CPU, RAM, IOPS và dung lượng cho PostgreSQL là một quá trình đo lường và dự báo. CPU cần phù hợp với mức đồng thời và kiểu truy vấn; RAM cần đủ cho working set nhưng vẫn dành chỗ cho hệ điều hành và các thao tác theo truy vấn; storage phải đáp ứng đồng thời IOPS, throughput và độ trễ; dung lượng phải tính cả dữ liệu, chỉ mục, WAL, file tạm, bảo trì và tăng trưởng.

Hãy bắt đầu bằng workload và số liệu đo được, kiểm thử trên cấu hình gần production, sau đó đặt ngưỡng cảnh báo đủ sớm để đội vận hành có thời gian xử lý. Khi tải và dữ liệu thay đổi, cần đo lại và cập nhật kế hoạch thay vì xem cấu hình ban đầu là cố định.
