# Adaptive hash index, change buffer và điều kiện tính năng theo phiên bản

## Mục tiêu

Trong module `DATABASE_MYSQL`, bạn làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Hiệu năng hệ thống**, bài học này giải thích hai cơ chế nội bộ của InnoDB là adaptive hash index và change buffer, cách chúng tác động đến đọc/ghi, cách quan sát chúng và những thay đổi mặc định theo phiên bản MySQL.

Sau bài học, bạn có thể:

- Phân biệt adaptive hash index với B-tree index do người dùng tạo.
- Giải thích cách change buffer trì hoãn cập nhật trang secondary index để giảm I/O ngẫu nhiên.
- Nhận diện workload phù hợp, chi phí và dấu hiệu nghẽn của từng cơ chế.
- Đọc các biến cấu hình và chỉ số giám sát liên quan trong InnoDB.
- Đối chiếu khác biệt giữa MySQL 8.0, 8.4 và 9.7 trước khi nâng cấp hoặc thay đổi cấu hình.

## 1. Hai cơ chế nội bộ trong bức tranh hiệu năng InnoDB

InnoDB tổ chức dữ liệu bằng clustered index và secondary index, thường dựa trên cấu trúc B-tree. Buffer pool giữ các trang dữ liệu và trang index thường được truy cập trong bộ nhớ. Khi trang cần thiết không nằm trong buffer pool, InnoDB có thể phải đọc trang từ thiết bị lưu trữ. Với workload có nhiều truy cập ngẫu nhiên, chi phí I/O và việc đồng bộ giữa các luồng có thể trở thành nút thắt.

Adaptive hash index (AHI) bổ sung đường tra cứu dạng hash cho những mẫu tìm kiếm B-tree lặp lại và thường xuyên. Change buffer giữ tạm thay đổi đối với một số trang secondary index chưa có trong buffer pool, rồi hợp nhất thay đổi khi trang được nạp hoặc khi InnoDB có thời gian xử lý nền.

Hai cơ chế giải quyết hai vấn đề khác nhau:

| Cơ chế | Trọng tâm | Tác động kỳ vọng |
|---|---|---|
| Adaptive hash index | Tăng tốc một số thao tác đọc lặp lại trên index | Giảm chi phí đi qua B-tree cho các mẫu lookup phù hợp |
| Change buffer | Trì hoãn một số thao tác ghi vào secondary index page chưa ở buffer pool | Giảm các lần đọc/ghi ngẫu nhiên nhỏ, gom việc cập nhật để xử lý sau |

Chúng là tối ưu hóa nội bộ của InnoDB. Không cơ chế nào thay thế thiết kế index đúng, câu SQL có thể dùng index, buffer pool phù hợp hoặc phép đo trên workload thực tế.

## 2. Adaptive hash index (AHI)

### 2.1. Cách AHI được hình thành

AHI là cấu trúc hash do InnoDB tự quản lý. InnoDB theo dõi mẫu tìm kiếm trên B-tree; khi nhận thấy một số trang index được truy cập thường xuyên và mẫu tìm kiếm có lợi, engine tự xây dựng hash entry dựa trên một prefix của khóa index. Chỉ những phần dữ liệu phù hợp mới được đưa vào AHI. Người vận hành không tạo AHI bằng `CREATE INDEX` và không chỉ định từng cột cho cấu trúc này.

Ví dụ, ứng dụng liên tục tìm một đơn hàng theo `order_id`:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE order_id = 900001;
```

Nếu index và trang liên quan thường xuyên được truy cập, AHI có thể giúp InnoDB tra cứu nhanh hơn sau khi mẫu truy cập được nhận diện. Truy vấn vẫn dựa trên index B-tree gốc; AHI là đường tăng tốc bổ sung do engine xây dựng khi có ích.

AHI có xu hướng hữu ích khi:

- Workload có nhiều lookup lặp lại trên cùng vùng khóa hoặc prefix khóa.
- Các trang index thường xuyên dùng đã nằm trong buffer pool.
- Hệ thống có đủ bộ nhớ cho buffer pool và mẫu truy cập ổn định.
- Chi phí tiết kiệm được từ lookup lớn hơn chi phí theo dõi và duy trì hash table.

AHI có thể ít hữu ích hoặc gây thêm chi phí khi:

- Workload chủ yếu là scan, range scan rộng hoặc truy cập phân tán, ít lặp lại.
- Truy vấn dùng `LIKE` với wildcard đầu chuỗi như `LIKE '%abc'`.
- Nhiều luồng đồng thời tranh chấp latch bảo vệ AHI, ví dụ workload join có concurrency cao.
- Dữ liệu và index liên tục thay đổi khiến chi phí cập nhật cấu trúc hash không bù được lợi ích đọc.

Không nên kết luận AHI tốt hay xấu chỉ từ loại ứng dụng. Cùng một hệ thống có thể cải thiện với AHI trong giờ đọc cao điểm nhưng bị tranh chấp khi số luồng tăng mạnh. Cần đo thông lượng, p95/p99 latency, CPU và thời gian chờ latch trong cùng một kịch bản tải.

### 2.2. Partition và tranh chấp latch

AHI được chia thành nhiều partition; mỗi partition có latch riêng để giảm tranh chấp khi nhiều luồng truy cập đồng thời. Biến `innodb_adaptive_hash_index_parts` điều khiển số partition. Trong MySQL 8.4, giá trị mặc định là `8`, phạm vi cho phép là `1` đến `512`; biến này không dynamic nên cần cấu hình khi khởi động máy chủ.

Nếu AHI có lợi về lookup nhưng nhiều luồng chờ rw-latch liên quan đến `btr0sea.c`, có thể thử tăng số partition hoặc tắt AHI. Tăng partition không đảm bảo cải thiện: cần đo lại vì nó cũng làm thay đổi cách phân chia và quản lý cấu trúc hash. Khi AHI không giúp workload, tắt hẳn có thể giảm chi phí theo dõi và đồng bộ.

Biến `innodb_adaptive_hash_index` có thể đổi động ở phạm vi GLOBAL. Khi tắt, InnoDB làm rỗng hash table và truy vấn tiếp tục đi theo B-tree; khi bật lại, hash table được xây dựng dần theo hoạt động bình thường. Vì vậy, benchmark phải có giai đoạn warm-up và không nên so sánh một lượt chạy đã ổn định với một lượt chạy vừa bật AHI.

## 3. Change buffer

### 3.1. Vấn đề mà change buffer giải quyết

Khi `INSERT`, `UPDATE` hoặc `DELETE` thay đổi secondary index, trang index chứa entry cần sửa có thể không nằm trong buffer pool. Nếu cập nhật ngay, InnoDB có thể phải đọc trang từ đĩa chỉ để thay đổi một phần nhỏ, tạo I/O ngẫu nhiên. Điều này đặc biệt tốn kém khi index lớn hơn vùng cache và workload ghi phân tán trên nhiều giá trị khóa.

Change buffer là cấu trúc lưu các thay đổi đủ điều kiện đối với secondary index page khi trang đó chưa có trong buffer pool. Khi trang được nạp vào buffer pool bởi một thao tác đọc, InnoDB hợp nhất (merge) các thay đổi đang chờ vào trang. Tiến trình nền cũng có thể hợp nhất khi hệ thống gần idle hoặc trong quá trình shutdown chậm.

Ví dụ, một bảng có nhiều secondary index và các dòng mới được thêm với giá trị khóa phân tán. Thay vì buộc mỗi lần ghi phải đọc ngay các secondary index page khác nhau từ đĩa, InnoDB có thể ghi nhận thay đổi trong change buffer và xử lý chúng theo lô khi trang tương ứng được nạp.

Change buffer không phải cache kết quả truy vấn, không giữ toàn bộ bản ghi mới của bảng và không thay thế redo/undo log. Nó tối ưu việc cập nhật một số secondary index page. Trong bộ nhớ, change buffer dùng một phần buffer pool; trên đĩa, cấu trúc này thuộc system tablespace nên các thay đổi đang chờ vẫn tồn tại qua lần restart.

### 3.2. Phạm vi hỗ trợ và giới hạn

Change buffering chỉ áp dụng cho secondary index. Clustered index, FULLTEXT index và SPATIAL index không được change buffer hỗ trợ. Có một số điều kiện quan trọng:

- INSERT vào unique secondary index không được buffer vì InnoDB phải xác minh tính duy nhất trước khi thêm entry. Các loại thao tác change buffering khác như delete marking và purge vẫn có thể áp dụng cho unique index khi đủ điều kiện.
- Change buffering không được hỗ trợ cho secondary index có cột index theo chiều giảm dần (descending index column), hoặc khi primary key có cột descending.
- Chỉ những trang secondary index chưa nằm trong buffer pool mới là ứng viên. Nếu trang đã ở trong buffer pool, InnoDB cập nhật trang trong bộ nhớ theo đường thông thường.
- UPDATE có thể tạo ra cả thao tác thêm entry mới và đánh dấu entry cũ để xóa; vì vậy nó liên quan đến nhiều loại change buffering.

Các giới hạn này khiến change buffer không tăng tốc mọi thao tác ghi. Đặc biệt, không nên kỳ vọng nó cải thiện bulk insert vào unique index hoặc các bảng có index không thuộc phạm vi hỗ trợ.

### 3.3. Lợi ích và chi phí

Change buffer thường có ích khi dữ liệu lớn hơn buffer pool, có nhiều secondary index được cập nhật thường xuyên và workload bị giới hạn bởi I/O ngẫu nhiên. Nó có thể giảm số lần phải đọc trang index chỉ để cập nhật một entry, sau đó gom nhiều thay đổi để ghi hiệu quả hơn.

Đổi lại, change buffer chiếm dung lượng buffer pool và tạo công việc merge về sau. Nếu merge không theo kịp lượng thay đổi mới, backlog có thể tăng. Khi merge diễn ra, I/O nền có thể tăng và làm truy vấn đọc bị chậm, nhất là khi hệ thống đã bị giới hạn bởi đĩa. Merge có thể tiếp tục sau khi transaction đã commit và thậm chí sau khi máy chủ restart; điều này không có nghĩa transaction chưa commit, mà là một phần cập nhật secondary index đang được xử lý theo cơ chế trì hoãn của InnoDB.

Hãy cân nhắc tắt change buffering hoặc giữ ở mức thấp khi:

- Working set vừa khít hoặc gần vừa khít buffer pool và việc dành thêm bộ nhớ cho change buffer làm giảm cache dữ liệu hữu ích.
- Bảng có ít secondary index hoặc tỷ lệ cập nhật index thấp.
- Thiết bị lưu trữ có độ trễ random read thấp, làm lợi ích tránh đọc ngẫu nhiên nhỏ hơn.
- Hệ thống thường xuyên chịu áp lực I/O do merge, recovery hoặc tác vụ ghi lớn.

SSD không tự động khiến change buffer luôn vô ích. Cần đo với loại thiết bị, kích thước dữ liệu, index và tải đồng thời của chính hệ thống.

## 4. Điều kiện tính năng và thay đổi mặc định theo phiên bản

Điểm dễ gây lỗi khi nâng cấp là nhầm lẫn giữa **tính năng còn tồn tại** và **giá trị mặc định đã thay đổi**. AHI và change buffering vẫn có trong các dòng MySQL hiện đại được nêu dưới đây, nhưng mặc định của chúng không giống nhau.

| Phiên bản MySQL | `innodb_adaptive_hash_index` mặc định | `innodb_change_buffering` mặc định | `innodb_change_buffer_max_size` mặc định |
|---|---:|---|---:|
| 8.0 | `ON` | `all` | `25` |
| 8.4 | `OFF` | `none` | `25` |
| 9.7 | `OFF` | `none` | `5` |

Các giá trị trên là mặc định được tài liệu tham chiếu cho từng dòng phiên bản công bố. Cần kiểm tra patch release, bản phân phối và cấu hình thực tế của máy chủ trước khi áp dụng. Nếu option file đã đặt biến tường minh, giá trị cấu hình đó có thể ghi đè mặc định của phiên bản.

Một số mốc và điều kiện cần nhớ:

- MySQL 5.5 mở rộng change buffer để hỗ trợ buffering cho thay đổi do `UPDATE` và `DELETE`; trước đó cơ chế này chủ yếu phục vụ `INSERT` và thường được gọi là insert buffer.
- MySQL 5.6 bổ sung `innodb_change_buffer_max_size`, cho phép đặt giới hạn dung lượng change buffer theo phần trăm buffer pool.
- Từ MySQL 8.4, mặc định AHI chuyển từ `ON` sang `OFF`; mặc định `innodb_change_buffering` chuyển từ `all` sang `none`. Đây là thay đổi mặc định, không phải tuyên bố hai tính năng đã bị loại bỏ.
- Trong MySQL 8.4, `innodb_adaptive_hash_index_parts` mặc định là `8`, tối đa `512` và không dynamic. `innodb_adaptive_hash_index` là biến GLOBAL dynamic.
- `innodb_change_buffering` và `innodb_change_buffer_max_size` là biến GLOBAL dynamic. Đổi `innodb_change_buffering` chỉ ảnh hưởng các thao tác mới; những entry đã có vẫn cần được merge.
- Trong tài liệu MySQL 9.7 hiện hành, `innodb_change_buffer_max_size` có mặc định `5`; không mang giá trị mặc định `25` từ cấu hình 8.0/8.4 sang mà không kiểm tra.

Khi nâng cấp từ 8.0 lên 8.4 hoặc 9.7, hãy kiểm tra cả cấu hình tệp và giá trị đang chạy. Không suy ra rằng máy chủ đã bật AHI hay change buffering chỉ vì trước đây bản 8.0 sử dụng các mặc định đó. Ngược lại, nếu file cấu hình có chỉ định `ON` hoặc `all`, máy chủ có thể tiếp tục dùng các giá trị ấy sau nâng cấp.

## 5. Đọc cấu hình và quan sát hoạt động

### 5.1. Xác định phiên bản và biến đang chạy

Trước khi đánh giá hiệu năng, ghi lại phiên bản và giá trị biến thực tế:

```sql
SELECT VERSION();

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'innodb_adaptive_hash_index',
  'innodb_adaptive_hash_index_parts',
  'innodb_change_buffering',
  'innodb_change_buffer_max_size'
);
```

Kết quả `SHOW GLOBAL VARIABLES` phản ánh giá trị đang chạy, có tính đến option file và thay đổi runtime. Dùng nó làm căn cứ trước khi so sánh với bảng mặc định theo phiên bản.

### 5.2. Quan sát AHI

Chạy lệnh sau trong MySQL client để xem InnoDB Standard Monitor:

```sql
SHOW ENGINE INNODB STATUS\G
```

Ở phần `INSERT BUFFER AND ADAPTIVE HASH INDEX`, chú ý các số liệu như số hash search và non-hash search. Đây là dữ liệu để xem AHI có được sử dụng hay không; tỷ lệ hash search cao tự nó chưa chứng minh hiệu năng tổng thể tốt hơn.

Trong phần `SEMAPHORES`, tìm các luồng chờ rw-latch có liên quan đến `btr0sea.c`. Nếu có nhiều luồng chờ, AHI có thể trở thành điểm tranh chấp. Đối chiếu thời gian chờ với CPU, throughput, p95/p99 latency và tải đồng thời. Tùy kết quả, thử so sánh AHI bật/tắt hoặc tăng partition trong một lần thử nghiệm có kiểm soát.

### 5.3. Quan sát change buffer

Trong cùng output `SHOW ENGINE INNODB STATUS`, phần `INSERT BUFFER AND ADAPTIVE HASH INDEX` có các dòng `Ibuf` và `merged operations` để theo dõi kích thước, số lần merge và các loại thao tác đã được hợp nhất. Chụp số liệu theo khoảng thời gian để xem backlog có tăng liên tục hay được xử lý đều.

Có thể xem tên và mô tả metric của InnoDB bằng:

```sql
SELECT NAME, COMMENT
FROM information_schema.innodb_metrics
WHERE NAME LIKE '%ibuf%';
```

Nếu cần kiểm tra instrumentation mutex của change buffer:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE '%wait/synch/mutex/innodb/ibuf%';
```

Chỉ bật thêm instrumentation theo quy trình quan sát của môi trường vì việc thu thập timing cũng có chi phí. Tránh truy vấn `INFORMATION_SCHEMA.INNODB_BUFFER_PAGE` trên production chỉ để đếm change buffer page: bảng này có thể gây overhead đáng kể. Nếu cần phân tích chi tiết loại page, hãy tái hiện trên máy thử nghiệm.

## 6. Thay đổi cấu hình có kiểm soát

Các ví dụ dưới đây minh họa cách thay đổi biến GLOBAL trong lúc máy chủ đang chạy. Cần có quyền thích hợp và đánh giá tác động trước khi chạy trên production.

Tắt AHI:

```sql
SET GLOBAL innodb_adaptive_hash_index = OFF;
```

Bật AHI để thử nghiệm:

```sql
SET GLOBAL innodb_adaptive_hash_index = ON;
```

Chọn phạm vi change buffering:

```sql
-- Không buffer thao tác mới
SET GLOBAL innodb_change_buffering = 'none';

-- Chỉ buffer insert nếu workload và phiên bản hỗ trợ, có lợi qua benchmark
SET GLOBAL innodb_change_buffering = 'inserts';
```

Các giá trị hợp lệ của `innodb_change_buffering` gồm:

| Giá trị | Thao tác được buffer |
|---|---|
| `none` | Không buffer thao tác nào |
| `inserts` | Insert |
| `deletes` | Delete marking, tức đánh dấu bản ghi index để xóa về sau |
| `changes` | Insert và delete marking |
| `purges` | Xóa vật lý trong quá trình purge nền |
| `all` | Insert, delete marking và purge |

`UPDATE` là tổ hợp thay đổi có thể liên quan đến insert và delete marking. Việc chọn một giá trị phải dựa trên workload thực tế và giá trị hỗ trợ của phiên bản đang chạy.

`innodb_change_buffer_max_size` biểu thị phần trăm tổng dung lượng buffer pool dành tối đa cho change buffer. Trong MySQL 8.4, mặc định là `25`, phạm vi `0`–`50`; trong MySQL 9.7, mặc định là `5`. Chỉ cân nhắc tăng khi workload ghi nặng và merge không theo kịp khiến change buffer chạm giới hạn. Cân nhắc giảm khi change buffer chiếm bộ nhớ cần cho trang dữ liệu hoặc máy chủ chủ yếu phục vụ báo cáo với dữ liệu ít thay đổi. Không tăng giới hạn chỉ vì thấy số liệu change buffer lớn; trước hết phải xác định merge backlog, I/O và buffer pool pressure.

Ví dụ thay đổi giới hạn trong runtime:

```sql
SET GLOBAL innodb_change_buffer_max_size = 20;
```

Con số `20` chỉ là ví dụ cấu hình, không phải khuyến nghị mặc định. Biến `innodb_adaptive_hash_index_parts` không dynamic trong MySQL 8.4; nếu thay đổi, cần đặt trong option file hoặc startup option rồi khởi động lại theo quy trình bảo trì. Luôn kiểm tra tài liệu đúng phiên bản trước khi dùng biến này.

## 7. Quy trình benchmark để quyết định bật hay tắt

Không thay đổi đồng thời AHI, change buffering, buffer pool size và nhiều biến I/O trong cùng một lần thử. Nếu thay đổi nhiều yếu tố, rất khó xác định nguyên nhân của kết quả.

Quy trình so sánh gợi ý:

1. Ghi phiên bản MySQL, cấu hình biến, dung lượng buffer pool, loại lưu trữ và schema/index liên quan.
2. Chọn workload đại diện: tỷ lệ đọc/ghi, kiểu lookup, số secondary index, concurrency, kích thước working set và phân bố khóa.
3. Đo baseline trong khoảng thời gian ổn định: throughput, p95/p99 latency, CPU, read/write IOPS, buffer pool hit behavior, semaphore/latch waits và change buffer merge.
4. Thay đổi một cơ chế hoặc một biến trong môi trường thử nghiệm; giữ nguyên dữ liệu, truy vấn và mức tải.
5. Chạy warm-up đủ lâu, đặc biệt sau khi bật AHI vì hash table được xây dựng dần. Với change buffer, theo dõi cả thời gian chạy tải lẫn giai đoạn merge sau tải.
6. Lặp lại nhiều lần và so sánh cùng loại thống kê. Nếu kết quả dao động lớn, tăng thời gian thử hoặc giảm biến động tải nền.
7. Chỉ áp dụng khi cải thiện mục tiêu mà không làm xấu đáng kể p99 latency, I/O nền, memory pressure hoặc độ ổn định.

Ví dụ diễn giải kết quả:

| Quan sát | Hướng điều tra |
|---|---|
| AHI bật làm throughput đọc tăng và latch wait thấp | AHI có thể phù hợp với lookup lặp lại của workload |
| AHI bật làm CPU hoặc rw-latch wait tăng, p99 xấu đi | Thử tăng partition trong môi trường test hoặc tắt AHI |
| Change buffer giảm random reads trong tải ghi và merge ổn định | Cơ chế có thể giúp workload I/O-bound |
| Change buffer tăng liên tục, merge tạo I/O nền và truy vấn đọc chậm | Kiểm tra tỷ lệ ghi, secondary index, giới hạn buffer và thử giảm/tắt buffering |
| 8.0 và 8.4 có kết quả khác dù không đổi ứng dụng | Đối chiếu các default đã đổi và option file sau nâng cấp |

## 8. Checklist vận hành

Trước và sau khi thay đổi cấu hình, hãy xác nhận:

- [ ] Đã ghi nhận `SELECT VERSION()` và giá trị thực tế của các biến liên quan.
- [ ] Đã phân biệt giá trị mặc định của phiên bản với giá trị được đặt trong option file hoặc runtime.
- [ ] Đã đánh giá AHI trên workload lookup thực tế, bao gồm contention và p95/p99 latency.
- [ ] Đã xem `SEMAPHORES` trong InnoDB status nếu nghi ngờ AHI gây latch contention.
- [ ] Đã xác định workload có đủ điều kiện dùng change buffer: secondary index page chưa ở buffer pool và loại index được hỗ trợ.
- [ ] Đã tính đến merge backlog, I/O nền và dung lượng buffer pool khi đánh giá change buffer.
- [ ] Đã kiểm tra thay đổi mặc định từ MySQL 8.0 sang 8.4 và từ 8.4 sang 9.7 nếu có nâng cấp.
- [ ] Đã benchmark từng thay đổi riêng biệt, có warm-up và theo dõi giai đoạn merge.
- [ ] Có phương án rollback và theo dõi sau khi áp dụng trên production.

## Kết luận

Adaptive hash index tăng tốc một số mẫu đọc lặp lại bằng cấu trúc hash do InnoDB tự xây dựng, nhưng có thể gây tranh chấp latch khi concurrency cao. Change buffer trì hoãn một số cập nhật secondary index page chưa có trong buffer pool để giảm I/O ngẫu nhiên, đổi lại tạo nhu cầu merge và sử dụng bộ nhớ. Hai cơ chế cần được đánh giá riêng theo workload, loại index, thiết bị lưu trữ và mức đồng thời. Khi vận hành hoặc nâng cấp, hãy kiểm tra giá trị biến thực tế: MySQL 8.4 đổi mặc định AHI sang `OFF` và change buffering sang `none`; MySQL 9.7 tiếp tục dùng các mặc định đó và đặt mặc định `innodb_change_buffer_max_size` là `5`. Chỉ thay đổi sau khi đã đo, hiểu điều kiện hỗ trợ và chuẩn bị cách theo dõi hoặc rollback.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Adaptive Hash Index](https://dev.mysql.com/doc/refman/8.4/en/innodb-adaptive-hash.html)
- [MySQL 8.4 Reference Manual: Change Buffer](https://dev.mysql.com/doc/refman/8.4/en/innodb-change-buffer.html)
- [MySQL 8.4 Reference Manual: InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual: Changes in MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/upgrading-from-previous-series.html)
- [MySQL 9.7 Reference Manual: InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/9.7/en/innodb-parameters.html)
- [MySQL 9.7 Reference Manual: Change Buffer](https://dev.mysql.com/doc/refman/9.7/en/innodb-change-buffer.html)
