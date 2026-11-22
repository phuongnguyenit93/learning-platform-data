# Mức nhất quán Group Replication và ảnh hưởng độ trễ

MySQL Group Replication phân phối transaction giữa các thành viên trong một group. Sau khi transaction được chứng nhận và commit theo thứ tự chung, các member còn lại vẫn cần thời gian để applier thực thi thay đổi lên dữ liệu cục bộ. Trong khoảng thời gian đó, một client đọc từ member khác có thể nhìn thấy trạng thái cũ. Đây là đặc tính quan trọng của replication bất đồng bộ và là lý do MySQL cung cấp các mức nhất quán cho Group Replication.

Biến `group_replication_consistency` cho phép chọn mức chờ trước khi transaction chạy, sau khi transaction commit hoặc cả hai. Mức chờ mạnh hơn có thể bảo đảm một số kiểu read-after-write và giảm nguy cơ đọc dữ liệu cũ, nhưng thường làm tăng thời gian phản hồi, đặc biệt khi một member có tốc độ áp dụng chậm. Chọn mức phù hợp là bài toán cân bằng giữa tính nhất quán mà ứng dụng cần và độ trễ mà hệ thống có thể chấp nhận.

## 1. Vì sao Group Replication có thể trả về dữ liệu cũ?

Group Replication sử dụng group communication để phân phối transaction và thực hiện certification nhằm phát hiện xung đột ghi. Các transaction được sắp xếp theo một thứ tự chung. Tuy vậy, việc transaction được commit ở member nhận yêu cầu không có nghĩa tất cả member đã áp dụng transaction đó vào bảng cục bộ.

Luồng xử lý khái quát:

```text
Client gửi transaction tới member A
              |
              v
      Thực thi và tạo writeset
              |
              v
   Group communication / certification
              |
              v
     Transaction được commit
              |
        +-----+-----+
        |           |
        v           v
   Member A      Member B, C
   áp dụng       nhận và xếp hàng
   cục bộ        cho applier
                    |
                    v
              Áp dụng sau đó
```

Ví dụ, ứng dụng cập nhật trạng thái đơn hàng trên member A rồi ngay lập tức gửi một truy vấn đọc tới member B. Nếu applier ở B chưa xử lý transaction vừa commit, truy vấn có thể thấy trạng thái cũ. Điều này thường được gọi là replication lag hoặc độ trễ áp dụng.

Trong single-primary mode, ghi thường được gửi tới primary còn truy vấn đọc có thể được phân phối tới secondary. Trong multi-primary mode, nhiều member có thể nhận ghi, nhưng mỗi member vẫn có thể có hàng đợi áp dụng riêng. Certification giải quyết xung đột transaction; nó không tự bảo đảm mọi truy vấn đọc ở mọi member đều nhìn thấy mọi commit mới nhất.

## 2. `group_replication_consistency` điều khiển điều gì?

`group_replication_consistency` xác định mức đồng bộ mà transaction yêu cầu từ Group Replication. Biến này có phạm vi GLOBAL và SESSION, với giá trị mặc định là `EVENTUAL` trong cấu hình MySQL tiêu chuẩn.

| Mức | Hành vi chính | Tác động thường gặp |
|---|---|---|
| `EVENTUAL` | Không chờ transaction trước đó được áp dụng trước khi transaction hiện tại chạy, và không chờ transaction hiện tại được áp dụng trên các member khác trước khi trả kết quả commit | Độ trễ thấp hơn; ứng dụng có thể đọc dữ liệu cũ trên member khác |
| `BEFORE` | Chờ các transaction trước đó trong thứ tự group được áp dụng trên member đang thực thi trước khi transaction hiện tại chạy | Tăng thời gian bắt đầu transaction khi member còn backlog; hỗ trợ đọc thấy các commit trước đó trên member này |
| `AFTER` | Chờ transaction hiện tại được áp dụng trên các member trong group trước khi transaction trả kết quả commit | Tăng thời gian commit theo tốc độ áp dụng của các member; hỗ trợ read-after-write khi client chuyển sang member khác sau khi commit trả về |
| `BEFORE_AND_AFTER` | Kết hợp điều kiện chờ trước và sau transaction | Bảo đảm mạnh hơn nhưng có thể tăng cả thời gian bắt đầu lẫn commit |
| `BEFORE_ON_PRIMARY_FAILOVER` | Trên single-primary mode, primary mới chờ backlog transaction từ primary cũ được áp dụng trước khi xử lý transaction mới | Có thể làm chậm giao dịch sau failover; tránh phục vụ đọc/ghi từ primary mới khi dữ liệu cũ còn chưa được áp dụng |

Các mức này điều khiển thời điểm transaction được phép tiếp tục trong Group Replication. Chúng không biến Group Replication thành hệ thống đồng bộ theo nghĩa mọi thao tác SQL luôn có cùng thời gian hoàn tất trên tất cả máy chủ. Độ trễ thực tế vẫn phụ thuộc group communication, mạng, certification, tải CPU, tốc độ storage và hàng đợi applier.

## 3. Hiểu rõ từng mức nhất quán

### EVENTUAL — ưu tiên độ trễ

`EVENTUAL` không thêm điều kiện chờ để đồng bộ các transaction trước hoặc transaction hiện tại giữa các member. Đây là lựa chọn mặc định phù hợp với workload có thể chấp nhận dữ liệu đọc trễ trong một khoảng ngắn.

Ví dụ:

```sql
-- Kết nối A: ghi trên primary
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;

-- Kết nối B: đọc trên member khác với EVENTUAL
SET SESSION group_replication_consistency = 'EVENTUAL';
SELECT status
FROM sales.orders
WHERE order_id = 1001;
```

Nếu truy vấn SELECT được thực thi trên member chưa áp dụng transaction cập nhật, kết quả có thể vẫn là `PENDING`. Ứng dụng phải chấp nhận khả năng đọc trễ hoặc tự thiết kế cơ chế đọc nhất quán hơn.

### BEFORE — chờ backlog cục bộ trước khi chạy

`BEFORE` yêu cầu member thực thi transaction chờ cho tới khi các transaction đi trước nó trong thứ tự group đã được áp dụng trên chính member đó. Sau khi điều kiện này thỏa mãn, transaction mới được thực thi.

Mức này hữu ích khi một session cần đọc dữ liệu đã được commit trước đó trên một member. Ví dụ, sau khi ứng dụng biết một transaction đã được commit trong group, nó gửi một transaction đọc tới member B với `BEFORE`; B sẽ chờ áp dụng các transaction trước đó trước khi chạy truy vấn.

```sql
SET SESSION group_replication_consistency = 'BEFORE';

START TRANSACTION READ ONLY;
SELECT status
FROM sales.orders
WHERE order_id = 1001;
COMMIT;
```

`BEFORE` không chờ transaction hiện tại được áp dụng trên tất cả member trước khi trả kết quả. Nó cũng không tự làm cho member khác đồng bộ ngay lập tức. Nếu member đang xử lý có backlog lớn, thời gian chờ trước khi transaction bắt đầu có thể tăng đáng kể.

### AFTER — chờ thay đổi lan tới group

`AFTER` cho transaction chờ cho tới khi các thay đổi của chính transaction đó được áp dụng trên các member trong group trước khi commit trả về cho client.

Mức này hữu ích cho luồng ghi rồi đọc trên member khác. Khi lệnh ghi trả về thành công, ứng dụng có thể chuyển sang đọc trên một member khác mà không gặp khoảng trễ áp dụng của transaction vừa ghi, trong phạm vi group và điều kiện thành viên hiện tại.

```sql
SET SESSION group_replication_consistency = 'AFTER';

START TRANSACTION;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;
COMMIT;
```

Khi `COMMIT` trả về, transaction đã được áp dụng trên các member cần đáp ứng điều kiện nhất quán của group. Đổi lại, thời gian commit chịu ảnh hưởng của member áp dụng chậm nhất. Một member có storage chậm, CPU quá tải hoặc hàng đợi applier lớn có thể làm tăng độ trễ của transaction đang chờ.

### BEFORE_AND_AFTER — chờ cả hai phía

`BEFORE_AND_AFTER` kết hợp hai điều kiện: member thực thi chờ áp dụng transaction trước đó trước khi chạy transaction hiện tại, sau đó chờ transaction hiện tại được áp dụng trên group trước khi commit trả về.

Mức này phù hợp với các thao tác nhạy cảm cần quan sát trạng thái đã cập nhật trước đó và yêu cầu thay đổi mới được lan truyền trước khi báo thành công. Tuy nhiên, việc chờ cả trước lẫn sau làm tăng thời gian phản hồi và có thể làm giảm throughput khi tải cao. Chỉ nên áp dụng cho workload thực sự cần bảo đảm này.

### BEFORE_ON_PRIMARY_FAILOVER — tránh đọc trạng thái cũ sau chuyển primary

Trong single-primary mode, khi primary cũ rời group và một member khác được bầu làm primary, member mới có thể còn backlog các transaction đã được group chấp nhận trước khi failover. Nếu ứng dụng gửi giao dịch mới ngay lập tức, primary mới có nguy cơ xử lý giao dịch trong khi một phần dữ liệu cũ vẫn đang chờ áp dụng.

`BEFORE_ON_PRIMARY_FAILOVER` làm cho giao dịch trên primary mới chờ backlog từ primary cũ được áp dụng trước khi tiếp tục. Nhờ đó, ứng dụng tránh một khoảng thời gian mà primary mới phục vụ trạng thái cũ sau failover. Đổi lại, giao dịch đầu tiên sau chuyển primary có thể phải chờ đáng kể nếu backlog lớn.

Đây là mức dành cho tình huống single-primary failover, không phải lựa chọn thay thế chung cho `BEFORE` hoặc `AFTER` trong mọi workload. Kiểm tra phiên bản MySQL và chế độ Group Replication đang sử dụng trước khi cấu hình.

## 4. Mức nhất quán ảnh hưởng độ trễ ra sao?

Mỗi mức thêm một điểm đồng bộ khác nhau vào đường đi của transaction:

| Mức | Điểm có thể phải chờ | Yếu tố chi phối độ trễ |
|---|---|---|
| `EVENTUAL` | Không thêm chờ áp dụng theo consistency level | Thời gian xử lý cục bộ, group communication và certification |
| `BEFORE` | Trước khi transaction chạy | Số transaction đang chờ applier trên member hiện tại và tốc độ apply |
| `AFTER` | Trước khi commit trả về | Member cần áp dụng transaction chậm nhất trong group, mạng và tải applier |
| `BEFORE_AND_AFTER` | Trước khi chạy và trước khi commit trả về | Tổng thời gian chờ backlog cục bộ và chờ áp dụng trên group |
| `BEFORE_ON_PRIMARY_FAILOVER` | Trên primary mới sau failover | Kích thước backlog còn lại từ primary cũ và tốc độ apply của primary mới |

Có thể hình dung độ trễ bổ sung như sau:

```text
EVENTUAL
  Thực thi -> certification/commit -> trả kết quả

BEFORE
  Chờ backlog cục bộ -> thực thi -> certification/commit -> trả kết quả

AFTER
  Thực thi -> certification/commit -> chờ các member áp dụng -> trả kết quả

BEFORE_AND_AFTER
  Chờ backlog cục bộ -> thực thi -> commit -> chờ các member áp dụng -> trả kết quả
```

Đây là mô hình khái niệm, không phải công thức thời gian cố định. Các bước nội bộ có thể chồng lấp và phụ thuộc phiên bản, topology cùng trạng thái group.

Trong thực tế, `AFTER` thường làm tăng tail latency rõ hơn khi một member chậm hơn các member còn lại. Nếu một member có độ trễ apply cao, transaction trên các session yêu cầu chờ toàn group có thể bị kéo dài dù primary đang khỏe. `BEFORE` có thể làm một member đọc chậm tự chờ backlog của chính nó mà không nhất thiết buộc mọi transaction trên các member khác phải chờ cùng thời gian.

### Ví dụ so sánh

Giả sử group có ba member A, B, C. A nhận transaction ghi. B áp dụng thay đổi sau 15 ms, C sau 90 ms.

| Cấu hình | Thời điểm client có thể nhận kết quả (mô tả đơn giản) |
|---|---|
| `EVENTUAL` | Sau khi transaction hoàn tất các bước commit cần thiết tại A; B và C có thể vẫn đang áp dụng |
| `AFTER` | Chỉ sau khi B và C đã áp dụng transaction, nên bị chi phối bởi member C trong ví dụ |
| `BEFORE` trên B | Một transaction mới chạy ở B phải chờ backlog trước đó tại B; không phải chờ transaction mới của A được áp dụng trên C |
| `BEFORE_AND_AFTER` | Có cả chờ backlog tại member thực thi và chờ áp dụng transaction hiện tại trên group |

Các con số chỉ minh họa. Không dùng chúng làm dự báo production; hãy đo trên topology thực tế với kích thước transaction, tải và mạng gần với môi trường chạy thật.

## 5. Chọn mức theo loại workload

Không nhất thiết mọi session phải dùng cùng một mức. Có thể chọn theo yêu cầu của từng luồng ứng dụng:

| Workload | Mức có thể cân nhắc | Lý do |
|---|---|---|
| Báo cáo chấp nhận dữ liệu trễ ngắn | `EVENTUAL` | Giữ độ trễ thấp và chấp nhận replica chưa áp dụng hết |
| Đọc sau khi một transaction trước đó đã commit trên member hiện tại | `BEFORE` | Chờ backlog cục bộ trước khi đọc |
| Ghi xong cần đọc ngay từ member khác | `AFTER` | Commit chỉ trả về sau khi thay đổi được áp dụng trên group |
| Giao dịch quan trọng cần cả trạng thái trước và thay đổi mới được lan truyền | `BEFORE_AND_AFTER` | Chờ cả trước và sau transaction |
| Hệ thống single-primary cần tránh trạng thái cũ sau failover | `BEFORE_ON_PRIMARY_FAILOVER` | Primary mới chờ backlog từ primary cũ |

Ví dụ một ứng dụng thương mại điện tử có thể dùng `EVENTUAL` cho dashboard tổng hợp, `BEFORE` cho truy vấn đọc trên secondary sau khi nhận thông báo một transaction đã commit, và `AFTER` cho thao tác ghi mà ngay sau đó ứng dụng chuyển truy vấn sang member khác. Việc lựa chọn phải được kiểm tra với đường định tuyến thực tế: nếu ứng dụng đọc lại trên cùng session/member, nhu cầu chờ có thể khác với trường hợp chuyển sang member khác.

Mức consistency không thay thế transaction isolation của InnoDB. `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` điều khiển khả năng nhìn thấy thay đổi bên trong transaction theo quy tắc isolation; `group_replication_consistency` điều khiển sự chờ giữa các transaction và member trong group. Hai cơ chế giải quyết hai lớp vấn đề khác nhau.

## 6. Cấu hình ở cấp server và session

Kiểm tra giá trị hiện tại:

```sql
SHOW GLOBAL VARIABLES LIKE 'group_replication_consistency';
SHOW SESSION VARIABLES LIKE 'group_replication_consistency';
```

Đặt mức cho session cụ thể:

```sql
SET SESSION group_replication_consistency = 'BEFORE';
```

Đặt mặc định toàn server cho các session mới:

```sql
SET GLOBAL group_replication_consistency = 'EVENTUAL';
```

`SET SESSION` chỉ ảnh hưởng kết nối hiện tại. `SET GLOBAL` thay đổi giá trị mặc định toàn cục nhưng không tự thay đổi giá trị session đã được thiết lập trong các kết nối đang tồn tại. Nếu dùng connection pool, phải đặt lại session variable khi cấp connection cho request và reset khi trả connection về pool, tránh một request cần consistency mạnh làm thay đổi hành vi của request kế tiếp.

Có thể đặt mặc định khi khởi động bằng file cấu hình:

```ini
[mysqld]
group_replication_consistency=EVENTUAL
```

Hoặc dùng `SET PERSIST` nếu phiên bản và chính sách quản lý cấu hình cho phép:

```sql
SET PERSIST group_replication_consistency = 'EVENTUAL';
```

Các lệnh ví dụ cần được chạy với quyền phù hợp và xác nhận trên đúng phiên bản MySQL. Trước khi thay đổi global setting, đánh giá ảnh hưởng tới toàn bộ ứng dụng đang kết nối tới member.

## 7. Quan sát backlog và độ trễ

Để hiểu vì sao một mức consistency gây chờ, cần theo dõi trạng thái thành viên và hàng đợi áp dụng.

Liệt kê member trong group:

```sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Xem thống kê transaction của từng member:

```sql
SELECT
  MEMBER_ID,
  COUNT_TRANSACTIONS_IN_QUEUE,
  COUNT_TRANSACTIONS_REMOTE_IN_APPLIER_QUEUE,
  COUNT_TRANSACTIONS_REMOTE_APPLIED,
  COUNT_TRANSACTIONS_LOCAL_PROPOSED,
  COUNT_CONFLICTS_DETECTED
FROM performance_schema.replication_group_member_stats;
```

Các cột thống kê cho biết số transaction trong các hàng đợi và hoạt động áp dụng/certification. Ý nghĩa chính xác của từng bộ đếm cần đọc theo phiên bản. So sánh xu hướng qua thời gian thường hữu ích hơn một lần chụp đơn lẻ.

Ngoài ra, kiểm tra worker applier:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;
```

Khi điều tra độ trễ, kết hợp các nguồn sau:

- Trạng thái `ONLINE`/`RECOVERING` của member trong `replication_group_members`.
- Hàng đợi remote applier và tốc độ tăng/giảm của các bộ đếm trong `replication_group_member_stats`.
- CPU, I/O, buffer pool, lock wait và thời gian commit của từng member.
- Độ trễ mạng, mất gói và chênh lệch hiệu năng giữa các vùng triển khai.
- Histogram thời gian commit và read latency ở p50, p95, p99 của ứng dụng.

Đừng dùng một chỉ số `Seconds_Behind_Source` của asynchronous replication như đại diện duy nhất cho Group Replication. Hãy theo dõi Performance Schema và số liệu ứng dụng tương ứng với cơ chế group đang chạy.

## 8. Flow control và consistency level

Group Replication có cơ chế flow control để điều tiết member tạo transaction nhanh hơn khả năng member khác áp dụng. Khi hàng đợi vượt ngưỡng, flow control có thể yêu cầu các member giảm tốc độ tạo transaction để group bắt kịp.

Flow control và `group_replication_consistency` có liên quan tới độ trễ nhưng không giống nhau:

- Consistency level xác định một transaction phải chờ ở điểm nào để đạt mức quan sát dữ liệu yêu cầu.
- Flow control điều tiết tốc độ phát sinh transaction khi một hoặc nhiều member bị tụt lại.

Nếu một member thường xuyên chậm, `AFTER` có thể làm tăng thời gian commit của session yêu cầu chờ; flow control có thể đồng thời giảm throughput toàn group để hạn chế backlog. Chỉ tăng ngưỡng flow control để che độ trễ không giải quyết nguyên nhân như storage chậm, transaction quá lớn hoặc thiếu worker applier.

Khi tuning, xem xét cả kích thước transaction, số worker applier, CPU, IOPS và cấu hình flow control. Thay đổi một tham số mỗi lần, đo p95/p99 và kiểm tra trạng thái group trước khi đưa vào production.

## 9. Xử lý failover và member chậm

Trong single-primary mode, primary mới được bầu sau khi primary cũ rời group hoặc không còn đủ điều kiện. Một số transaction đã được group chấp nhận có thể vẫn đang chờ applier trên member mới. Nếu ứng dụng lập tức gửi request đọc/ghi tới primary mới, kết quả có thể không như kỳ vọng nếu backlog chưa được xử lý.

`BEFORE_ON_PRIMARY_FAILOVER` giải quyết khoảng trống này bằng cách yêu cầu chờ backlog từ primary cũ trên primary mới trước khi giao dịch mới được xử lý. Ứng dụng nên tính tới thời gian chờ sau failover trong RTO và health check. Một health check chỉ xác nhận cổng TCP mở không chứng minh backlog đã được áp dụng.

Nếu member chậm làm các transaction `AFTER` chờ lâu:

1. Xác định member nào có hàng đợi remote applier tăng liên tục.
2. Kiểm tra CPU, storage latency, lock contention và kích thước transaction trên member đó.
3. Kiểm tra mạng giữa các member và trạng thái group.
4. Đánh giá member có thể bắt kịp hay cần được loại khỏi group theo quy trình vận hành.
5. Đo lại commit latency và tính sẵn sàng sau khi xử lý nguyên nhân.

Không tùy tiện loại một member khỏi group chỉ để giảm latency. Thay đổi membership ảnh hưởng quorum, khả năng chịu lỗi và dữ liệu cần đồng bộ lại khi member gia nhập lần nữa. Thực hiện theo quy trình Group Replication và đánh giá số member còn lại trước khi thay đổi.

## 10. Tình huống thực hành

Một hệ thống đặt hàng dùng Group Replication ba member ở single-primary mode. Ứng dụng ghi đơn hàng vào primary, sau đó một dịch vụ khác đọc trạng thái từ secondary. Dashboard có thể chấp nhận dữ liệu trễ, nhưng API trả kết quả xác nhận thanh toán cần bảo đảm lần đọc tiếp theo thấy trạng thái mới.

**Bước 1 — Đo baseline.** Để session dùng `EVENTUAL`, ghi nhận p50/p95/p99 của commit và truy vấn đọc. Theo dõi hàng đợi applier trên từng member.

**Bước 2 — Đặt consistency cho luồng nhạy cảm.** Với session ghi cần bảo đảm thay đổi đã lan tới group trước khi phản hồi, đặt `AFTER`:

```sql
SET SESSION group_replication_consistency = 'AFTER';

UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;
```

Ứng dụng đợi commit trả về rồi mới gửi yêu cầu đọc tới secondary. Kiểm tra secondary trả về trạng thái `PAID`.

**Bước 3 — Giữ dashboard ở EVENTUAL.** Các session báo cáo đặt `EVENTUAL` để tránh buộc mọi truy vấn dashboard chờ member chậm. Kết quả dashboard được mô tả là có thể trễ trong giới hạn workload.

**Bước 4 — Mô phỏng member chậm.** Tạo tải I/O hoặc workload kiểm thử trên một member trong môi trường staging. So sánh commit latency khi dùng `EVENTUAL` và `AFTER`; quan sát hàng đợi applier và p99. Không tạo tải gây ảnh hưởng production để thử nghiệm.

**Bước 5 — Diễn tập failover.** Chuyển primary theo quy trình kiểm thử. Nếu dùng `BEFORE_ON_PRIMARY_FAILOVER`, đo thời gian primary mới chờ backlog và xác nhận API chỉ nhận giao dịch sau khi điều kiện nhất quán được đáp ứng.

Kết quả mong đợi là chỉ các luồng cần read-after-write mới chịu chi phí chờ mạnh hơn, còn workload báo cáo tiếp tục ưu tiên độ trễ thấp. Nhóm vận hành cần đặt ngân sách latency cho thời gian chờ sau failover và theo dõi member chậm để tránh tail latency tăng ngoài dự kiến.

## 11. Checklist trước khi đưa vào production

- [ ] Đã xác định yêu cầu nhất quán của từng workload: có chấp nhận stale read hay cần read-after-write.
- [ ] Đã phân biệt `EVENTUAL`, `BEFORE`, `AFTER`, `BEFORE_AND_AFTER` và `BEFORE_ON_PRIMARY_FAILOVER`.
- [ ] Đã xác nhận phiên bản MySQL, chế độ single-primary/multi-primary và phạm vi hỗ trợ của consistency level.
- [ ] Đã thử `SET SESSION` trên từng loại session và xác minh connection pool reset biến đúng cách.
- [ ] Đã đo p50, p95, p99 và throughput với từng mức consistency trên topology gần production.
- [ ] Đã kiểm tra member chậm, applier backlog, CPU, storage và độ trễ mạng.
- [ ] Đã phân biệt tác động của consistency level với flow control và transaction isolation.
- [ ] Đã diễn tập failover và đo thời gian chờ backlog trên primary mới nếu dùng `BEFORE_ON_PRIMARY_FAILOVER`.
- [ ] Đã có cảnh báo khi member chuyển trạng thái, hàng đợi applier tăng hoặc commit latency vượt ngân sách.
- [ ] Đã xác nhận timeout, retry và hành vi ứng dụng khi transaction phải chờ lâu hoặc thất bại.

Mức nhất quán Group Replication là một lựa chọn ở cấp transaction để điều chỉnh điểm đồng bộ giữa các member. `EVENTUAL` ưu tiên độ trễ, `BEFORE` chờ backlog cục bộ, `AFTER` chờ thay đổi lan tới group, còn `BEFORE_AND_AFTER` kết hợp cả hai. Với single-primary failover, `BEFORE_ON_PRIMARY_FAILOVER` giúp primary mới xử lý backlog trước khi nhận giao dịch mới. Chọn đúng mức theo workload và đo độ trễ trên từng member giúp ứng dụng đạt yêu cầu nhất quán mà vẫn giữ hiệu năng có thể dự đoán.
