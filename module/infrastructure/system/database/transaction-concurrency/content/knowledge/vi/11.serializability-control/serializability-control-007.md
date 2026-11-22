# Giao dịch chỉ đọc dài và các lựa chọn bảo vệ ảnh chụp

Một giao dịch chỉ đọc thường được xem là nhẹ vì nó không sửa dữ liệu. Tuy nhiên, khi giao dịch cần đọc một tập dữ liệu nhất quán trong thời gian dài, hệ quản trị cơ sở dữ liệu phải bảo vệ ảnh chụp (snapshot) mà giao dịch đang sử dụng. Những phiên bản dữ liệu cũ có thể vẫn cần thiết cho đến khi ảnh chụp kết thúc. Vì vậy, một báo cáo chỉ đọc chạy hàng giờ vẫn có thể ảnh hưởng đến vacuum, purge, dung lượng lưu trữ và khả năng hoàn tất của các giao dịch khác.

Trong chương kiểm soát khả tuần tự, vấn đề còn có một khía cạnh khác: một transaction đọc dài ở mức `SERIALIZABLE` phải được bảo đảm rằng kết quả của nó có thể nằm trong một thứ tự thực thi tương đương tuần tự. Một số hệ quản trị dùng cơ chế theo dõi xung đột để phát hiện nguy cơ bất thường và có thể hủy transaction. PostgreSQL cung cấp lựa chọn `SERIALIZABLE READ ONLY DEFERRABLE` để transaction chỉ đọc chờ đến khi có một snapshot an toàn trước khi bắt đầu đọc.

Bài này dùng PostgreSQL để giải thích cơ chế `DEFERRABLE` và theo dõi snapshot, đồng thời đối chiếu với MySQL InnoDB để làm rõ tác động của read view và undo history. Cú pháp và chi tiết nội bộ khác nhau giữa các hệ quản trị; cần áp dụng theo đúng hệ thống đang chạy.

## 1. Giao dịch chỉ đọc vẫn có thể giữ tài nguyên

`READ ONLY` mô tả ý định của transaction: ứng dụng chỉ đọc dữ liệu và không thực hiện các thao tác ghi thông thường. Thuộc tính này không có nghĩa transaction không giữ snapshot, không lấy khóa hoặc không ảnh hưởng đến hoạt động nền của database.

Một truy vấn báo cáo có thể cần đọc hàng triệu bản ghi trong khi các transaction khác vẫn tiếp tục cập nhật và xóa dữ liệu. Để trả về kết quả nhất quán, hệ quản trị phải xác định phiên bản nào được phép hiển thị tại snapshot của truy vấn. Nếu phiên bản hiện tại được tạo sau snapshot, hệ thống có thể cần giữ hoặc dựng lại phiên bản cũ.

Các tác động có thể xuất hiện gồm:

- Phiên bản hàng cũ phải được giữ lại lâu hơn vì snapshot vẫn có thể cần chúng.
- Công việc dọn dữ liệu cũ như PostgreSQL `VACUUM` hoặc InnoDB `purge` không thể loại bỏ những phiên bản vẫn còn cần thiết.
- Undo history, dead tuples hoặc dung lượng bảng có thể tăng trong lúc transaction giữ snapshot lâu.
- Một transaction `SERIALIZABLE` có thể tham gia vào chuỗi phụ thuộc đọc/ghi và bị hủy nếu hệ thống phát hiện kết quả không thể sắp xếp thành lịch tuần tự hợp lệ.
- Kết nối, cursor, khóa bảng và các tài nguyên khác có thể được giữ lâu hơn dự kiến.

Do đó, khi thiết kế báo cáo dài, cần trả lời hai câu hỏi: ứng dụng có thật sự cần một snapshot duy nhất xuyên suốt toàn bộ báo cáo không, và nếu cần thì có thể giữ snapshot đó trong bao lâu?

## 2. Ảnh chụp được bảo vệ như thế nào?

MVCC cho phép transaction đọc một trạng thái dữ liệu nhất quán trong khi transaction khác tiếp tục ghi. Một snapshot mô tả ranh giới hiển thị của dữ liệu: phiên bản nào đã commit đủ sớm để được nhìn thấy, phiên bản nào còn đang thay đổi hoặc được tạo sau snapshot thì chưa được nhìn thấy.

Ví dụ, số dư ban đầu là 500. Transaction A bắt đầu một báo cáo và lấy snapshot. Transaction B cập nhật số dư thành 700 rồi commit. A vẫn có thể đọc 500 trong snapshot cũ, trong khi transaction bắt đầu sau đó đọc 700.

```text
Thời gian       Transaction A (báo cáo)       Transaction B (cập nhật)
---------       ------------------------       ------------------------
t1              BEGIN
t2              SELECT balance -> 500
                snapshot A được tạo
t3                                             UPDATE balance = 700
t4                                             COMMIT
t5              SELECT balance -> 500
                vẫn dùng snapshot A
t6              COMMIT
```

Snapshot giúp kết quả của A không thay đổi giữa các câu đọc theo quy tắc isolation level. Đổi lại, database phải giữ đủ lịch sử để có thể trả về phiên bản 500 cho đến khi A không còn cần snapshot đó.

### Snapshot theo câu lệnh và theo transaction

Thời điểm tạo snapshot phụ thuộc isolation level và hệ quản trị.

| Cách đọc | Hành vi điển hình | Khi phù hợp |
|---|---|---|
| Snapshot theo câu lệnh | Mỗi câu đọc nhận một snapshot mới; dữ liệu commit giữa hai câu có thể xuất hiện ở câu sau | Dashboard hoặc truy vấn độc lập chấp nhận dữ liệu mới ở mỗi lần đọc |
| Snapshot theo transaction | Các câu đọc nhất quán trong cùng transaction tiếp tục dùng cùng snapshot | Báo cáo cần tổng hợp nhiều truy vấn trên một trạng thái dữ liệu thống nhất |
| Snapshot được tạo tường minh | Ứng dụng yêu cầu snapshot ở thời điểm bắt đầu hoặc phối hợp nhiều transaction dùng cùng snapshot | Quy trình báo cáo hoặc phân tích có yêu cầu thời điểm chụp rõ ràng |

Trong PostgreSQL, `READ COMMITTED` tạo snapshot mới cho mỗi câu lệnh, còn `REPEATABLE READ` và `SERIALIZABLE` giữ snapshot của transaction sau khi snapshot được lấy. Trong MySQL InnoDB, consistent read ở `READ COMMITTED` thường lấy read view mới cho mỗi câu đọc; ở `REPEATABLE READ`, các consistent read thường dùng lại read view được tạo ở lần đọc đầu tiên. Không nên suy luận rằng mọi hệ quản trị có cùng thời điểm tạo snapshot chỉ vì chúng dùng tên isolation level giống nhau.

## 3. Tác động của transaction đọc dài đến dọn dẹp dữ liệu

### PostgreSQL: snapshot cũ có thể giữ dead tuples

PostgreSQL dùng MVCC và đánh dấu phiên bản hàng đã bị cập nhật hoặc xóa là không còn phiên bản hiện tại. Phiên bản cũ chỉ có thể được `VACUUM` thu hồi khi không còn transaction nào có thể cần nhìn thấy nó.

Nếu một transaction giữ snapshot cũ trong thời gian dài, `VACUUM` có thể phải giữ lại các dead tuples mà snapshot đó còn có thể nhìn thấy. Khi workload vẫn tiếp tục cập nhật và xóa dữ liệu, dead tuples tích lũy và bảng hoặc index có thể phình to. Autovacuum có thể chạy nhưng không thể thu hồi những phiên bản bị snapshot cũ bảo vệ.

Một transaction đang chạy câu SELECT lâu có thể giữ snapshot trong suốt câu lệnh. Transaction `REPEATABLE READ` hoặc `SERIALIZABLE` còn có thể giữ snapshot xuyên suốt nhiều câu lệnh cho đến khi kết thúc. Cursor hoặc transaction để mở cũng cần được kiểm tra vì chúng có thể kéo dài thời gian sống của snapshot hoặc giữ khóa.

### MySQL InnoDB: read view cũ có thể giữ undo history

InnoDB lưu thông tin undo để dựng lại phiên bản trước cho consistent read. Khi một transaction giữ read view cũ, purge không thể loại bỏ undo record mà read view đó có thể cần. Nếu các transaction khác liên tục cập nhật hoặc xóa, history list có thể tăng.

Vì vậy, transaction chỉ đọc trong InnoDB cũng có thể làm undo history tồn tại lâu. Một connection ở trạng thái nhàn rỗi nhưng vẫn mở transaction có thể tiếp tục giữ read view đã tạo. `SHOW ENGINE INNODB STATUS` và `information_schema.innodb_trx` là các nguồn quan sát hữu ích.

### Tác động không giống nhau giữa các hệ

| Vấn đề | PostgreSQL | MySQL InnoDB |
|---|---|---|
| Lịch sử cũ được giữ | Dead tuples và các phiên bản cần cho snapshot | Undo record / undo history cần cho read view |
| Cơ chế dọn | `VACUUM` và autovacuum | Purge thread |
| Dấu hiệu theo dõi | `backend_xmin`, transaction age, dead tuples, tiến độ vacuum | Transaction age, `History list length`, trạng thái InnoDB |
| Hệ quả thường thấy | Table/index bloat, vacuum không thu hồi được phiên bản cũ | History list tăng, undo tablespace cần nhiều không gian hơn |

Tên chỉ số và chi tiết vòng đời dữ liệu khác nhau, nhưng nguyên tắc chung giống nhau: database không thể xóa một phiên bản mà một snapshot đang hoạt động vẫn có thể cần đọc.

## 4. `SERIALIZABLE` và nguy cơ serialization failure

Isolation level `SERIALIZABLE` yêu cầu kết quả của các transaction đồng thời tương đương với một thứ tự chạy tuần tự nào đó. Đây là mức bảo vệ mạnh hơn việc chỉ giữ một snapshot nhất quán.

PostgreSQL triển khai `SERIALIZABLE` bằng Serializable Snapshot Isolation (SSI). Hệ thống theo dõi các phụ thuộc đọc/ghi giữa transaction để phát hiện cấu trúc xung đột có thể dẫn đến kết quả không tuần tự hóa được. Một số predicate lock nội bộ, hiển thị dưới dạng `SIReadLock`, được dùng để ghi nhận vùng dữ liệu đã đọc; chúng không hoạt động như khóa độc quyền chặn writer thông thường.

Khi hệ thống phát hiện một cấu trúc phụ thuộc nguy hiểm, một transaction có thể bị hủy với lỗi serialization failure. Ứng dụng phải sẵn sàng chạy lại toàn bộ transaction từ đầu. Transaction đọc dài có thể sống qua nhiều hoạt động ghi đồng thời, làm tăng thời gian tồn tại của các phụ thuộc mà SSI cần theo dõi và tăng khả năng transaction phải thử lại.

Một transaction `READ ONLY` vẫn có thể tham gia vào các phụ thuộc đọc/ghi. Chỉ vì nó không ghi dữ liệu không có nghĩa là nó tự động miễn khỏi quy tắc `SERIALIZABLE`.

## 5. PostgreSQL `SERIALIZABLE READ ONLY DEFERRABLE`

PostgreSQL cung cấp chế độ transaction đặc biệt dành cho công việc chỉ đọc cần tính tuần tự hóa:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

-- Các câu SELECT của báo cáo
SELECT count(*) FROM orders;
SELECT sum(total_amount) FROM orders;

COMMIT;
```

`DEFERRABLE` chỉ có ý nghĩa khi transaction đồng thời là `SERIALIZABLE` và `READ ONLY`. Khi transaction cần lấy snapshot, PostgreSQL có thể phải chờ cho đến khi có **safe snapshot**. Safe snapshot là snapshot mà transaction chỉ đọc có thể sử dụng mà không có nguy cơ bị hủy do serialization failure phát sinh từ các transaction đồng thời.

Sau khi lấy được safe snapshot, transaction có thể thực hiện phần đọc mà không có nguy cơ bị hủy do serialization failure. Đổi lại, thời điểm bắt đầu đọc có thể bị trì hoãn. Nếu hệ thống đang có workload ghi kéo dài hoặc liên tục, thời gian chờ lấy safe snapshot có thể đáng kể.

Trình tự khái quát:

```text
Ứng dụng bắt đầu transaction
             |
             v
SERIALIZABLE + READ ONLY + DEFERRABLE
             |
             v
PostgreSQL chờ snapshot an toàn nếu cần
             |
             v
Nhận safe snapshot
             |
             v
Thực hiện các câu đọc nhất quán
             |
             v
COMMIT
```

Lựa chọn này phù hợp với báo cáo hoặc phân tích cần tính nhất quán tuần tự hóa và có thể chấp nhận chờ trước khi bắt đầu. Nó không làm transaction đọc chạy nhanh hơn và không loại bỏ chi phí giữ snapshot lâu đối với vacuum. Một khi đã có safe snapshot, nếu báo cáo chạy hàng giờ, snapshot vẫn có thể giữ các phiên bản dữ liệu cũ trong khoảng thời gian đó.

### So sánh với các lựa chọn khác

| Cấu hình PostgreSQL | Snapshot | Serialization failure | Đặc điểm vận hành |
|---|---|---|---|
| `READ COMMITTED READ ONLY` | Mới cho từng câu lệnh | Không áp dụng SSI serializable | Mỗi câu đọc có thể thấy dữ liệu commit mới hơn; phù hợp khi không cần một snapshot duy nhất cho toàn báo cáo |
| `REPEATABLE READ READ ONLY` | Một snapshot cho transaction | Có thể gặp lỗi serialization trong một số trường hợp như cập nhật đồng thời làm transaction không thể tiếp tục theo snapshot | Giữ snapshot ổn định; transaction dài có thể gây áp lực lên vacuum |
| `SERIALIZABLE READ ONLY` | Snapshot theo transaction và SSI theo dõi phụ thuộc | Có thể bị hủy do serialization failure | Cung cấp bảo vệ tuần tự hóa; ứng dụng phải xử lý retry |
| `SERIALIZABLE READ ONLY DEFERRABLE` | Chờ safe snapshot rồi dùng snapshot đó | Không bị hủy do serialization failure sau khi có safe snapshot | Có thể chậm ở giai đoạn bắt đầu; thích hợp cho workload đọc dài cần tính tuần tự hóa |

`REPEATABLE READ` trong PostgreSQL cũng có thể phát sinh serialization failure khi transaction cố cập nhật hàng đã bị transaction khác thay đổi sau snapshot. Cột so sánh trên nhấn mạnh khác biệt của SSI và chế độ deferrable, không phải danh sách đầy đủ mọi lỗi có thể xảy ra ở mỗi isolation level.

## 6. Khi nào nên dùng từng lựa chọn?

Trước khi chọn cấu hình, hãy xác định mức nhất quán mà báo cáo thực sự cần.

### Chọn READ COMMITTED khi từng câu đọc độc lập

Nếu báo cáo chỉ hiển thị các số liệu gần thời gian thực và chấp nhận mỗi câu lệnh có thể phản ánh thời điểm hơi khác nhau, `READ COMMITTED` thường giúp tránh giữ một snapshot xuyên suốt toàn bộ transaction. Trong PostgreSQL, ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY;

SELECT count(*) FROM orders;
-- Câu lệnh tiếp theo có thể nhận snapshot mới.
SELECT sum(total_amount) FROM orders;

COMMIT;
```

Không dùng cách này nếu hai số liệu phải mô tả cùng một trạng thái dữ liệu tại cùng một thời điểm. Nếu có transaction tường minh kéo dài, vẫn cần đóng transaction đúng lúc và kiểm soát cursor, khóa cùng tài nguyên đang giữ.

### Chọn REPEATABLE READ khi cần một snapshot ổn định

Nếu nhiều truy vấn cần đọc cùng một trạng thái dữ liệu, `REPEATABLE READ READ ONLY` có thể phù hợp:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM orders;
SELECT sum(total_amount) FROM orders;
SELECT max(created_at) FROM orders;

COMMIT;
```

Các câu đọc trong transaction dùng cùng snapshot. Điều này giúp các phép tính liên quan không bị lệch thời điểm, nhưng snapshot có thể tồn tại đến khi transaction kết thúc. Hãy giới hạn phạm vi báo cáo và không để ứng dụng chờ thao tác bên ngoài khi transaction còn mở.

### Chọn SERIALIZABLE READ ONLY DEFERRABLE khi cần an toàn tuần tự hóa

Với báo cáo tài chính hoặc phép phân tích cần bảo đảm kết quả tương đương một thứ tự transaction tuần tự, PostgreSQL `SERIALIZABLE READ ONLY DEFERRABLE` có thể là lựa chọn phù hợp. Ứng dụng cần chấp nhận độ trễ ban đầu để chờ safe snapshot và vẫn cần đặt giới hạn thời gian chạy báo cáo.

### Chạy báo cáo trên replica khi phù hợp

Một read replica có thể chuyển tải truy vấn phân tích khỏi primary. Tuy nhiên, replica thường có độ trễ áp dụng thay đổi; dữ liệu đọc có thể cũ hơn primary. Trên PostgreSQL, hot standby còn có thể hủy truy vấn dài khi xung đột recovery buộc replica phải áp dụng thay đổi từ primary. Một số cấu hình cho phép trì hoãn recovery conflict, nhưng điều đó có thể làm replica tụt lại phía sau.

Replica giúp tách tải đọc, nhưng không tự động bảo đảm snapshot mới nhất hoặc loại bỏ mọi tác động của truy vấn dài. Cần xác định rõ yêu cầu về độ trễ dữ liệu, tính nhất quán và hành vi khi truy vấn bị hủy.

### Tạo dữ liệu báo cáo riêng khi snapshot phải sống quá lâu

Nếu báo cáo cần nhiều giờ hoặc nhiều ngày để xử lý, cân nhắc tạo bản chụp dữ liệu riêng, bảng tổng hợp, materialized view hoặc một tập dữ liệu xuất tại thời điểm xác định. Cách này chuyển chi phí từ việc giữ transaction mở lâu sang việc tạo và quản lý dữ liệu báo cáo.

Đổi lại, cần quản lý thời điểm làm mới, dung lượng, quyền truy cập và cách công bố rằng dữ liệu báo cáo phản ánh thời điểm nào. Đây thường là lựa chọn phù hợp hơn khi người dùng cần tải xuống hoặc phân tích lặp lại cùng một bộ dữ liệu lớn.

## 7. Snapshot được chia sẻ giữa nhiều transaction

Một số công việc song song cần nhiều worker đọc cùng một trạng thái dữ liệu. PostgreSQL hỗ trợ xuất và nhập snapshot bằng `pg_export_snapshot()` và `SET TRANSACTION SNAPSHOT`.

Transaction xuất snapshot phải giữ transaction mở trong khi các transaction khác nhập snapshot đó. Các transaction nhận snapshot phải nhập nó trước khi thực hiện truy vấn đầu tiên hoặc thay đổi trạng thái transaction không còn cho phép nhập snapshot.

Ví dụ minh họa:

```sql
-- Session A: tạo và xuất snapshot
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
-- Giả sử trả về chuỗi snapshot '00000003-0000001B-1'.
-- Giữ session A mở trong khi worker nhập snapshot.
```

```sql
-- Session B: nhập snapshot do Session A xuất
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT count(*) FROM orders;
COMMIT;
```

Session A chỉ được commit sau khi các worker đã nhập snapshot cần thiết. Sau khi transaction xuất kết thúc, transaction mới không thể tiếp tục nhập snapshot đó. Cơ chế này giúp các worker nhìn cùng một trạng thái dữ liệu, nhưng transaction xuất có thể giữ snapshot lâu và làm vacuum phải giữ lịch sử tương ứng.

Không nên xuất snapshot rồi để transaction nguồn mở vô thời hạn. Cần có điều phối rõ ràng: worker nào đã nhập, worker nào thất bại, khi nào có thể kết thúc transaction nguồn và cách xử lý khi một worker bị treo.

## 8. Chia nhỏ báo cáo mà vẫn giữ đúng ý nghĩa dữ liệu

Một giải pháp thường gặp là chia báo cáo lớn thành nhiều truy vấn nhỏ để giảm thời gian mỗi truy vấn. Cách này chỉ giữ được cùng một trạng thái dữ liệu nếu các phần truy vấn dùng chung snapshot hoặc dữ liệu đã được cố định trước.

Ví dụ, phân trang theo khóa chính:

```sql
SELECT id, total_amount
FROM orders
WHERE id > :last_id
ORDER BY id
LIMIT 10000;
```

Ứng dụng lấy trang kế tiếp bằng `last_id`. Cách này giảm kích thước kết quả mỗi lần và tránh chi phí của offset lớn. Tuy nhiên, nếu mỗi trang chạy trong transaction riêng ở `READ COMMITTED`, dữ liệu được thêm, sửa hoặc xóa giữa các trang có thể khiến tổng báo cáo không phản ánh một snapshot duy nhất.

Có ba hướng lựa chọn:

1. **Chấp nhận dữ liệu thay đổi giữa các trang:** dùng transaction ngắn cho từng trang, phù hợp với danh sách vận hành mà tính nhất quán toàn báo cáo không bắt buộc.
2. **Giữ snapshot chung:** dùng một transaction snapshot dài hoặc snapshot được chia sẻ giữa các worker, đồng thời giới hạn thời gian và giám sát tác động lên vacuum/purge.
3. **Đóng băng dữ liệu báo cáo:** tạo bảng snapshot hoặc tập dữ liệu xuất theo một mốc thời gian, sau đó chia nhỏ việc đọc trên dữ liệu đã cố định.

Nếu báo cáo dùng tổng hợp, thứ tự phân trang hoặc điều kiện lọc phải ổn định. Tránh dùng `OFFSET` lớn trên tập dữ liệu đang thay đổi nếu việc thêm/xóa hàng có thể làm bản ghi bị lặp hoặc bỏ sót giữa các trang.

## 9. Theo dõi transaction đọc dài trong PostgreSQL

### Tìm transaction và snapshot lâu

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Các cột cần chú ý:

- `xact_start`: thời điểm transaction hiện tại bắt đầu; giá trị cũ cho thấy transaction có thể đã mở lâu.
- `query_start`: thời điểm câu lệnh hiện tại bắt đầu; có thể khác xa `xact_start` nếu transaction chạy nhiều câu lệnh.
- `state`: phân biệt `active` với `idle in transaction`.
- `backend_xmin`: giới hạn xmin mà backend đang giữ; giá trị cũ có thể khiến vacuum phải bảo toàn phiên bản cũ.
- `wait_event_type` và `wait_event`: giúp nhận biết backend đang chờ tài nguyên nào.

`backend_xmin` có thể là `NULL` tùy trạng thái và loại transaction; không nên dùng một cột đơn lẻ để kết luận snapshot có đang bị ghim hay không. Hãy kết hợp trạng thái, thời gian transaction, isolation level và workload.

### Xem vacuum đang làm gì

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
```

View này cho biết tiến độ các lệnh vacuum đang hoạt động. Nếu vacuum đã chạy nhưng dead tuples không được thu hồi như kỳ vọng, hãy kiểm tra transaction hoặc replication slot giữ xmin cũ.

### Kiểm tra predicate lock của SSI

```sql
SELECT
    locktype,
    relation::regclass AS relation_name,
    page,
    tuple,
    mode,
    pid
FROM pg_locks
WHERE mode = 'SIReadLock';
```

Các `SIReadLock` là dấu vết theo dõi đọc của SSI. Chúng không giống khóa hàng `FOR UPDATE` và thông thường không chặn writer theo cách khóa độc quyền. Số lượng và mức chi tiết của predicate lock có thể thay đổi theo cấu hình và khả năng nâng cấp lock của PostgreSQL.

## 10. Theo dõi transaction và undo history trong MySQL InnoDB

### Tìm transaction mở lâu

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_isolation_level,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Transaction đọc có thể đang ở trạng thái nhàn rỗi giữa hai câu SQL. `trx_query` rỗng không có nghĩa transaction đã kết thúc. Đối chiếu connection id với process list và thông tin ứng dụng để xác định ai đang sở hữu transaction.

### Xem history list length

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `TRANSACTIONS`, xem transaction đang hoạt động và `History list length`. Đây là chỉ số về độ dài undo history đang chờ purge, không phải số transaction hoặc số hàng cũ chính xác. Lấy nhiều mẫu theo thời gian để xác định history list đang tăng hay giảm.

Với InnoDB, transaction `REPEATABLE READ` giữ read view lâu có thể ngăn purge loại bỏ undo cần thiết cho snapshot. Nếu workload ghi tiếp tục, history list có thể tăng dù transaction giữ snapshot không hề ghi dữ liệu.

## 11. Quản lý vòng đời của transaction đọc dài

### Đặt giới hạn thời gian có chủ đích

- Đặt timeout cho truy vấn hoặc transaction theo SLA của báo cáo.
- Thiết lập giới hạn ở cả database và ứng dụng; bảo đảm khi timeout xảy ra, transaction được rollback hoặc đóng đúng cách.
- Theo dõi `idle in transaction` và các kết nối không hoạt động nhưng vẫn giữ transaction.
- Hủy truy vấn hoặc kết nối theo quy trình có kiểm soát, tránh kết thúc nhầm transaction đang phục vụ nghiệp vụ quan trọng.

Trong PostgreSQL, có thể dùng `statement_timeout` để giới hạn thời gian một câu lệnh và `idle_in_transaction_session_timeout` để đóng session nằm idle trong transaction quá lâu. `transaction_timeout` có ở các phiên bản PostgreSQL mới hơn; hãy kiểm tra phiên bản triển khai trước khi dùng. Timeout không thay thế thiết kế transaction đúng: ứng dụng vẫn cần xử lý lỗi và giải phóng tài nguyên.

### Giữ phần đọc nhất quán càng ngắn càng tốt

Nếu báo cáo cần nhiều phép tính, hãy cân nhắc gom chúng vào một truy vấn hoặc một transaction ngắn để giảm thời gian snapshot tồn tại. Tuy nhiên, tối ưu SQL không đủ nếu ứng dụng tiếp tục giữ transaction mở trong lúc truyền kết quả qua mạng hoặc chờ người dùng tải file.

Với báo cáo lớn, có thể đọc theo batch, ghi kết quả sang vùng staging hoặc file trung gian, rồi kết thúc transaction đọc ngay khi dữ liệu đã được chụp. Việc truyền file và xử lý định dạng nên diễn ra sau khi snapshot đã được giải phóng nếu nghiệp vụ cho phép.

### Không thay đổi isolation level chỉ để né lỗi

Hạ từ `SERIALIZABLE` xuống `READ COMMITTED` có thể làm giảm thời gian giữ snapshot hoặc tránh một số serialization failure, nhưng nó cũng làm yếu bảo đảm nhất quán. Chỉ thực hiện khi nghiệp vụ chấp nhận kết quả có thể phản ánh nhiều thời điểm khác nhau và không dựa vào giả định tuần tự hóa.

Tương tự, `DEFERRABLE` có thể tránh serialization failure cho PostgreSQL read-only serializable transaction sau khi nhận safe snapshot, nhưng không loại bỏ tác động của snapshot dài đến vacuum. Cần quản lý cả thời gian chờ safe snapshot và thời gian chạy báo cáo.

## 12. Quy trình chọn giải pháp

Khi thiết kế một tác vụ đọc dài, có thể đi theo trình tự sau:

1. **Xác định yêu cầu nhất quán:** từng câu đọc độc lập có được phép thấy dữ liệu mới ở thời điểm khác nhau không, hay toàn bộ báo cáo phải dùng một snapshot?
2. **Xác định yêu cầu tuần tự hóa:** kết quả có cần tương đương một thứ tự transaction tuần tự hay chỉ cần snapshot nhất quán?
3. **Chọn isolation level:** `READ COMMITTED` cho các câu đọc độc lập; `REPEATABLE READ` cho snapshot theo transaction; `SERIALIZABLE` khi cần bảo đảm tuần tự hóa.
4. **Cân nhắc chế độ deferrable:** trên PostgreSQL, chọn `SERIALIZABLE READ ONLY DEFERRABLE` nếu có thể chờ safe snapshot và muốn tránh serialization failure trong phần đọc.
5. **Đánh giá thời gian sống snapshot:** đo thời gian truy vấn, thời gian transaction, thời gian idle và lượng dữ liệu cần đọc.
6. **Chọn nơi thực thi:** primary, replica, bảng snapshot hoặc materialized view tùy yêu cầu độ mới và mức tải.
7. **Đặt giới hạn và giám sát:** theo dõi transaction lâu, xmin/history list, vacuum/purge và hành vi retry hoặc timeout.
8. **Kiểm thử dưới tải đồng thời:** xác nhận báo cáo có kết quả đúng khi writer chạy song song, đồng thời đo tác động đến dọn dẹp dữ liệu và độ trễ ứng dụng.

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `READ ONLY` nghĩa là transaction không gây tác động lên database. | Transaction vẫn có thể giữ snapshot, khóa và tài nguyên; nó có thể làm chậm vacuum hoặc purge. |
| Snapshot nhất quán luôn đồng nghĩa với SERIALIZABLE. | Snapshot cung cấp một góc nhìn nhất quán; SERIALIZABLE còn bảo đảm kết quả tương đương một thứ tự chạy tuần tự. |
| `DEFERRABLE` làm truy vấn nhanh hơn. | Nó có thể khiến transaction chờ trước khi lấy safe snapshot; lợi ích là tránh serialization failure sau đó. |
| `SERIALIZABLE READ ONLY` luôn miễn khỏi serialization failure. | PostgreSQL vẫn có thể hủy transaction read-only serializable; `DEFERRABLE` với safe snapshot mới cung cấp hành vi tránh lỗi đó sau khi snapshot được lấy. |
| Chạy báo cáo trên replica loại bỏ mọi vấn đề snapshot. | Replica có thể trễ dữ liệu và truy vấn dài có thể xung đột với recovery. |
| Chia truy vấn thành nhiều trang luôn giữ cùng một snapshot. | Transaction riêng cho từng trang có thể thấy trạng thái dữ liệu khác nhau. Muốn cùng snapshot cần cơ chế chia sẻ snapshot hoặc dữ liệu được cố định. |
| Transaction đã idle thì snapshot chắc chắn đã được giải phóng. | Điều này phụ thuộc isolation level, cursor và hệ quản trị; phải kiểm tra trạng thái thực tế. Transaction idle vẫn có thể giữ khóa hoặc tài nguyên khác. |

## 14. Tự kiểm tra

**Vì sao một transaction chỉ đọc có thể làm PostgreSQL autovacuum không thu hồi được dead tuples?**

Nếu transaction giữ snapshot cũ, các phiên bản hàng mà snapshot đó còn có thể nhìn thấy phải được bảo toàn. Vacuum không thể loại bỏ chúng cho đến khi snapshot không còn cần thiết.

**`SERIALIZABLE READ ONLY DEFERRABLE` làm gì trước khi bắt đầu đọc?**

PostgreSQL có thể chờ để lấy safe snapshot. Sau khi nhận snapshot an toàn, transaction chỉ đọc có thể chạy mà không có nguy cơ bị hủy do serialization failure.

**Chế độ deferrable có loại bỏ chi phí của transaction đọc dài không?**

Không. Nó giải quyết nguy cơ serialization failure cho transaction phù hợp, nhưng snapshot vẫn tồn tại trong lúc transaction chạy và có thể tiếp tục giữ lịch sử dữ liệu cũ.

**Khi nào nên dùng READ COMMITTED thay cho REPEATABLE READ?**

Khi mỗi câu đọc độc lập và nghiệp vụ chấp nhận các câu lệnh có thể nhìn thấy dữ liệu commit ở những thời điểm khác nhau. Nếu các phép tính phải cùng một snapshot, cần isolation hoặc cơ chế snapshot phù hợp hơn.

**Chia báo cáo thành nhiều trang có bảo đảm toàn bộ kết quả đến từ cùng thời điểm không?**

Không nếu mỗi trang chạy trong transaction riêng và nhận snapshot mới. Cần giữ snapshot chung, chia sẻ snapshot hoặc tạo một tập dữ liệu báo cáo đã cố định.

Khi lựa chọn cách chạy báo cáo dài, hãy cân bằng ba yêu cầu: **kết quả cần nhất quán đến mức nào, snapshot phải tồn tại bao lâu và database có thể giữ lịch sử cũ trong thời gian đó với chi phí ra sao**. Cấu hình isolation level chỉ là một phần của quyết định; vòng đời transaction, cách phân trang, nơi chạy báo cáo và giám sát vacuum/purge cũng quyết định hệ thống có vận hành ổn định hay không.
